"""Tempo — Departure-Window Optimizer for WaySafe.

The question no other surface answers
-------------------------------------
Compass picks **where** to go.
Plan Route picks **how** to get there for a chosen depart-time.
Forecast shows risk-vs-hour at **a single point**.
Refuge picks the best **egress** in a panic.

None of them answer the most common real-world planning question:

    "I want to be at the destination between 17:00 and 19:00 today —
     when should I leave, and which route flavor should I take?"

Tempo is the optimisation layer that closes that gap. It sweeps the joint
(arrival_minute, route_flavor) grid, runs `routing.plan_forecast_route`
once per cell, scores each candidate by **integrated forecast risk-distance**
along the actual corridor, and picks the minute that minimises it. Then
compares the winner to three meaningful baselines — "depart now",
"earliest arrival", "latest arrival" — and writes a concrete rationale
that names the risk pocket the winner avoids.

Physics
-------
For each (arrival_t, alpha):

    eta_alpha = baseline ETA for that alpha (probed at the window mid-point)
    depart_t  = arrival_t - eta_alpha
    route     = plan_forecast_route(origin, dest, forecaster, depart_t, alpha)
    risk_km   = mean(forecast_blended_risk along corridor) * distance_km
    composite = 100 * exp(-kappa * risk_km)            # 0..100, higher = better
    band      = All-clear >=80 · Caution 65 · Elevated 50 · High Risk 35 · Danger <35

`risk_km` is the integrated exposure the traveller will *actually* absorb
on that corridor at that time — it folds in distance, hour-conditional
forecast, geofences, and live-incident proximity in one number. The
exponential keeps the score curve gentle for small differences (so a
0.1 risk-km improvement doesn't flip the band) and steep for big ones.

Selection
---------
- Winner: highest `composite`. Ties broken by lower `risk_km`, then
  higher `min_safety`, then shorter ETA.
- Runners-up: next-best two (arrival, flavor) combos within 6 pts of
  the winner. Always distinct cells.
- A candidate whose `depart_t < now` is marked **infeasible** and
  excluded from winner selection (you can't leave in the past) but is
  still scored and rendered in the heatmap.

Comparisons
-----------
For the winner's flavor, Tempo names three baselines:

- **Depart now**: arrival slot whose `depart_t` is closest to `now`.
- **Earliest arrival**: first slot in the window.
- **Latest arrival**: last slot in the window.

Each carries a `delta_composite` (winner - baseline) and `delta_risk_km`
(baseline - winner) so the rationale can quote the concrete saving.

Outputs
-------
- `TempoCandidate` per grid cell.
- `TempoResult` aggregates the grid, winner, runners-up, comparisons,
  headline + advisory + rationale lines, and serialises to a
  `waysafe.tempo.v1` JSON envelope plus a markdown digest suitable for
  WhatsApp / email / Notion paste.

Pure-Python, zero new deps. Engines reused: `forecast.HazardForecaster`,
`routing.plan_forecast_route`, `safety.point_risk`.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Mapping, Sequence, Tuple

from utils import haversine_km
from routing import plan_forecast_route, RouteResult, AVG_TRAVEL_KMH


# ---------------- bands ----------------

# (label, lower-bound, hue). Walked top-to-bottom: first match wins.
TEMPO_BANDS: Tuple[Tuple[str, float, str], ...] = (
    ("All-clear",  80.0, "#53E3A6"),
    ("Caution",    65.0, "#F9C440"),
    ("Elevated",   50.0, "#FF9F43"),
    ("High Risk",  35.0, "#FF7F50"),
    ("Danger",      0.0, "#FF3D60"),
)

# 100 * exp(-KAPPA * risk_km): tuned so risk_km=0.64→80, 1.23→65, 1.98→50, 3.0→35.
KAPPA: float = 0.35


def _band_for(score: float) -> Tuple[str, str]:
    for name, lo, hue in TEMPO_BANDS:
        if score >= lo:
            return name, hue
    return TEMPO_BANDS[-1][0], TEMPO_BANDS[-1][2]


# ---------------- dataclasses ----------------

@dataclass
class TempoCandidate:
    arrival: datetime
    depart: datetime
    eta_minutes: float
    alpha: float
    flavor: str                 # "safest" | "balanced" | "fastest"
    composite: float            # 0..100, higher = better
    band: str
    band_color: str
    risk_km: float              # integrated forecast risk * distance_km
    distance_km: float
    avg_safety: int
    min_safety: int
    max_risk_segment_km: float
    forecast_at_dest: float     # forecaster.risk_at(dest, arrival)
    forecast_at_origin: float   # forecaster.risk_at(origin, depart)
    coords: List[Tuple[float, float]] = field(default_factory=list)
    feasible: bool = True
    notes: List[str] = field(default_factory=list)
    rank: int = 0               # 1-based, across all cells, composite desc

    @property
    def depart_label(self) -> str:
        return self.depart.strftime("%a %H:%M")

    @property
    def arrival_label(self) -> str:
        return self.arrival.strftime("%H:%M")


@dataclass
class TempoComparison:
    label: str
    candidate: TempoCandidate | None
    delta_composite: float       # winner - baseline (positive = winner is better)
    delta_risk_km: float         # baseline - winner (positive = winner saves exposure)
    same_as_winner: bool = False


@dataclass
class TempoResult:
    origin: Tuple[float, float]
    dest: Tuple[float, float]
    dest_label: str
    arrive_window: Tuple[datetime, datetime]
    step_min: int
    now: datetime
    flavors: List[Tuple[float, str]]
    arrival_slots: List[datetime]
    grid: List[List[TempoCandidate]]      # rows = flavors, cols = arrival slots
    winner: TempoCandidate | None
    runners_up: List[TempoCandidate] = field(default_factory=list)
    comparisons: List[TempoComparison] = field(default_factory=list)
    headline: str = ""
    advisory_line: str = ""
    rationale: List[str] = field(default_factory=list)
    feasibility_note: str = ""

    # ----- serialisation -----

    def to_dict(self) -> dict:
        def cand(c: TempoCandidate | None) -> dict | None:
            if c is None:
                return None
            return {
                "arrival": c.arrival.isoformat(),
                "depart": c.depart.isoformat(),
                "eta_minutes": c.eta_minutes,
                "alpha": c.alpha,
                "flavor": c.flavor,
                "composite": c.composite,
                "band": c.band,
                "risk_km": c.risk_km,
                "distance_km": c.distance_km,
                "avg_safety": c.avg_safety,
                "min_safety": c.min_safety,
                "max_risk_segment_km": c.max_risk_segment_km,
                "forecast_at_dest": c.forecast_at_dest,
                "forecast_at_origin": c.forecast_at_origin,
                "feasible": c.feasible,
                "notes": list(c.notes),
                "rank": c.rank,
            }
        return {
            "schema": "waysafe.tempo.v1",
            "origin": list(self.origin),
            "dest": list(self.dest),
            "dest_label": self.dest_label,
            "arrive_window": [self.arrive_window[0].isoformat(), self.arrive_window[1].isoformat()],
            "step_min": self.step_min,
            "now": self.now.isoformat(),
            "flavors": [{"alpha": a, "label": l} for a, l in self.flavors],
            "winner": cand(self.winner),
            "runners_up": [cand(c) for c in self.runners_up],
            "comparisons": [
                {
                    "label": cmp.label,
                    "delta_composite": cmp.delta_composite,
                    "delta_risk_km": cmp.delta_risk_km,
                    "same_as_winner": cmp.same_as_winner,
                    "candidate": cand(cmp.candidate),
                }
                for cmp in self.comparisons
            ],
            "grid": [[cand(c) for c in row] for row in self.grid],
            "headline": self.headline,
            "advisory_line": self.advisory_line,
            "rationale": list(self.rationale),
            "feasibility_note": self.feasibility_note,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    def to_markdown(self) -> str:
        w = self.winner
        lines: List[str] = []
        lines.append(f"# Tempo — depart-window optimizer")
        lines.append(f"_{self.dest_label}_ · window "
                     f"{self.arrive_window[0].strftime('%a %H:%M')} – "
                     f"{self.arrive_window[1].strftime('%H:%M')} · "
                     f"step {self.step_min} min · now {self.now.strftime('%a %H:%M')}")
        lines.append("")
        if w is None:
            lines.append("> No feasible departure found.")
            return "\n".join(lines)

        lines.append(f"**Depart {w.depart.strftime('%a %H:%M')}** "
                     f"({_relative_minutes(self.now, w.depart)}) "
                     f"· arrive **{w.arrival.strftime('%H:%M')}** "
                     f"· {w.flavor} route · ETA {w.eta_minutes:.0f} min · "
                     f"{w.distance_km:.1f} km")
        lines.append("")
        lines.append(f"**Composite {w.composite:.0f}/100 · {w.band}** "
                     f"· risk-km {w.risk_km:.2f} · avg safety {w.avg_safety} "
                     f"· min safety {w.min_safety}")
        lines.append("")

        if self.headline:
            lines.append(f"> {self.headline}")
            lines.append("")
        if self.advisory_line:
            lines.append(self.advisory_line)
            lines.append("")

        if self.rationale:
            lines.append("**Why this minute**")
            for r in self.rationale:
                lines.append(f"- {r}")
            lines.append("")

        if self.comparisons:
            lines.append("**Comparison**")
            lines.append("")
            lines.append("| Choice | Depart | Arrive | Composite | risk-km | vs winner |")
            lines.append("|---|---|---|---:|---:|---:|")
            for cmp in self.comparisons:
                c = cmp.candidate
                if c is None:
                    continue
                vs = "—" if cmp.same_as_winner else f"−{cmp.delta_composite:.0f} pts"
                lines.append(
                    f"| {cmp.label} | {c.depart.strftime('%H:%M')} "
                    f"| {c.arrival.strftime('%H:%M')} | {c.composite:.0f} "
                    f"| {c.risk_km:.2f} | {vs} |"
                )
            lines.append("")

        if self.runners_up:
            lines.append("**Runners-up**")
            for c in self.runners_up:
                lines.append(
                    f"- Depart {c.depart.strftime('%H:%M')} · arrive {c.arrival.strftime('%H:%M')} "
                    f"· {c.flavor} · {c.composite:.0f} ({c.band}) · risk-km {c.risk_km:.2f}"
                )
            lines.append("")

        if self.feasibility_note:
            lines.append(f"_{self.feasibility_note}_")

        return "\n".join(lines)


# ---------------- core ----------------

def _integrated_risk_km(route: RouteResult) -> float:
    """Mean forecast-blended risk along corridor × distance_km."""
    if not route.risk_samples or route.distance_km <= 0.0:
        return 0.0
    risks = [r for _, _, r in route.risk_samples]
    if not risks:
        return 0.0
    mean = sum(risks) / len(risks)
    return mean * route.distance_km


def _relative_minutes(now: datetime, t: datetime) -> str:
    delta = int(round((t - now).total_seconds() / 60.0))
    if delta == 0:
        return "now"
    if delta > 0:
        if delta < 60:
            return f"in {delta} min"
        h, m = divmod(delta, 60)
        return f"in {h}h{m:02d}m" if m else f"in {h}h"
    delta = -delta
    if delta < 60:
        return f"{delta} min ago"
    h, m = divmod(delta, 60)
    return f"{h}h{m:02d}m ago" if m else f"{h}h ago"


def optimize_departure(
    origin: Tuple[float, float],
    dest: Tuple[float, float],
    *,
    forecaster,
    arrive_window: Tuple[datetime, datetime],
    now: datetime | None = None,
    incidents: Sequence[Mapping] = (),
    geofences: Mapping | None = None,
    pois: Sequence[Mapping] = (),
    step_min: int = 10,
    flavors: Sequence[Tuple[float, str]] = ((4.5, "safest"), (2.5, "balanced"), (0.0, "fastest")),
    dest_label: str = "destination",
) -> TempoResult:
    """Sweep arrival_window × flavors and return a fully-rendered TempoResult."""
    now = now or datetime.utcnow()
    w_start, w_end = arrive_window
    if w_end <= w_start:
        w_end = w_start + timedelta(minutes=max(30, step_min * 3))
    geofences = geofences or {"features": []}
    flavors = list(flavors)

    # Arrival slot list — at least 2 slots so the optimisation is meaningful.
    span_min = max(int(round((w_end - w_start).total_seconds() / 60.0)), step_min * 2)
    n_slots = max(2, span_min // step_min + 1)
    n_slots = min(n_slots, 16)  # hard cap so the grid stays interactive
    actual_step = span_min // (n_slots - 1) if n_slots > 1 else step_min
    arrival_slots = [w_start + timedelta(minutes=i * actual_step) for i in range(n_slots)]
    mid_arrival = w_start + (w_end - w_start) / 2

    # Step 1: probe each flavor at the window midpoint to get a baseline ETA.
    # The depart we use for the probe is just `mid - rough_eta`; the route's
    # actual `eta_minutes` is what we believe.
    rough_eta_min = max(
        5.0,
        haversine_km(origin[0], origin[1], dest[0], dest[1]) / max(1.0, AVG_TRAVEL_KMH) * 60.0,
    )
    base_depart = mid_arrival - timedelta(minutes=rough_eta_min)

    eta_per_flavor: dict[float, float] = {}
    for alpha, _flavor in flavors:
        probe = plan_forecast_route(
            origin, dest, forecaster, base_depart,
            incidents=incidents, geofences=geofences, pois=pois,
            alpha=alpha,
        )
        eta_per_flavor[alpha] = max(1.0, probe.eta_minutes)

    # Step 2: build the grid.
    grid: List[List[TempoCandidate]] = []
    all_candidates: List[TempoCandidate] = []
    n_infeasible = 0

    for alpha, flavor in flavors:
        row: List[TempoCandidate] = []
        eta_base = eta_per_flavor[alpha]
        for arrival_t in arrival_slots:
            depart_t = arrival_t - timedelta(minutes=eta_base)
            r = plan_forecast_route(
                origin, dest, forecaster, depart_t,
                incidents=incidents, geofences=geofences, pois=pois,
                alpha=alpha,
            )
            risk_km = _integrated_risk_km(r)
            composite = 100.0 * math.exp(-KAPPA * risk_km)
            band, hue = _band_for(composite)
            f_origin = float(forecaster.risk_at(origin[0], origin[1], when=depart_t))
            f_dest = float(forecaster.risk_at(dest[0], dest[1], when=arrival_t))
            feasible = depart_t >= now - timedelta(seconds=30)
            if not feasible:
                n_infeasible += 1
            cand = TempoCandidate(
                arrival=arrival_t,
                depart=depart_t,
                eta_minutes=round(r.eta_minutes, 1),
                alpha=alpha,
                flavor=flavor,
                composite=round(composite, 1),
                band=band,
                band_color=hue,
                risk_km=round(risk_km, 3),
                distance_km=round(r.distance_km, 2),
                avg_safety=int(r.avg_safety),
                min_safety=int(r.min_safety),
                max_risk_segment_km=round(r.max_risk_segment_km, 2),
                forecast_at_dest=round(f_dest, 3),
                forecast_at_origin=round(f_origin, 3),
                coords=list(r.coords),
                feasible=feasible,
                notes=list(r.notes),
            )
            row.append(cand)
            all_candidates.append(cand)
        grid.append(row)

    # Step 3: pick winner from the feasible set (or fall back).
    feasibles = [c for c in all_candidates if c.feasible]
    pool = feasibles or list(all_candidates)
    pool.sort(key=lambda c: (-c.composite, c.risk_km, -c.min_safety, c.eta_minutes))
    winner = pool[0] if pool else None

    runners_up: List[TempoCandidate] = []
    if winner is not None:
        seen = {(winner.arrival, winner.alpha)}
        for c in pool[1:]:
            key = (c.arrival, c.alpha)
            if key in seen:
                continue
            if c.composite >= winner.composite - 6.0:
                runners_up.append(c)
                seen.add(key)
            if len(runners_up) >= 2:
                break

    # Rank everyone (composite desc) for badges.
    for i, c in enumerate(sorted(all_candidates, key=lambda x: -x.composite), start=1):
        c.rank = i

    # Step 4: baselines for comparison (winner's flavor row, feasible-preferred).
    comparisons: List[TempoComparison] = []
    if winner is not None:
        flavor_idx = next(i for i, (a, _l) in enumerate(flavors) if a == winner.alpha)
        same_flavor_row = grid[flavor_idx]
        same_feasible = [c for c in same_flavor_row if c.feasible]
        baseline_pool = same_feasible or same_flavor_row

        # depart-now: feasible candidate whose depart_t is closest to `now`.
        depart_now: TempoCandidate | None = None
        if baseline_pool:
            depart_now = min(
                baseline_pool,
                key=lambda c: abs((c.depart - now).total_seconds()),
            )

        # Earliest / latest arrival within the window (prefer feasible).
        earliest_arr = baseline_pool[0] if baseline_pool else None
        latest_arr = baseline_pool[-1] if baseline_pool else None

        triples = [
            ("Winner", winner),
            ("Depart now", depart_now),
            ("Earliest arrival", earliest_arr),
            ("Latest arrival", latest_arr),
        ]
        seen_keys: set[Tuple[str, str]] = set()
        for label, cand in triples:
            if cand is None:
                continue
            key = (cand.arrival.isoformat(), cand.flavor)
            same = (cand.arrival == winner.arrival and cand.alpha == winner.alpha)
            if label != "Winner" and key in seen_keys:
                # Skip baselines that coincide with the winner cell (e.g.
                # depart-now happens to be the optimal slot — that's already
                # the winner row).
                continue
            seen_keys.add(key)
            comparisons.append(TempoComparison(
                label=label,
                candidate=cand,
                delta_composite=round(winner.composite - cand.composite, 1),
                delta_risk_km=round(cand.risk_km - winner.risk_km, 3),
                same_as_winner=same,
            ))

    # Step 5: headline + rationale (deterministic plain English).
    headline = ""
    advisory_line = ""
    rationale: List[str] = []
    if winner is not None:
        rel = _relative_minutes(now, winner.depart)
        headline = (
            f"Depart **{winner.depart.strftime('%a %H:%M')}** ({rel}) "
            f"— **{winner.flavor}** route arrives "
            f"**{winner.arrival.strftime('%H:%M')}** at {dest_label}."
        )
        if winner.band == "All-clear":
            advisory_line = (
                f"Composite **{winner.composite:.0f}/100 · {winner.band}** — "
                f"the corridor reads calm at that ETA. "
                f"Distance {winner.distance_km:.1f} km · risk-km {winner.risk_km:.2f}."
            )
        elif winner.band in ("Caution", "Elevated"):
            advisory_line = (
                f"Composite **{winner.composite:.0f}/100 · {winner.band}** — "
                f"best available in the window, but the corridor is not pristine. "
                f"Watch the {winner.max_risk_segment_km:.1f} km warm stretch."
            )
        else:
            advisory_line = (
                f"Composite **{winner.composite:.0f}/100 · {winner.band}** — "
                f"every slot in this window prices risk-km > 2. "
                f"Consider widening the arrival window or picking a different destination."
            )

        # Rationale bullets compare winner to each non-trivial baseline.
        for cmp in comparisons:
            if cmp.same_as_winner or cmp.candidate is None:
                continue
            base = cmp.candidate
            delta = cmp.delta_composite
            risk_delta = cmp.delta_risk_km
            if delta < 0.5 and abs(risk_delta) < 0.05:
                rationale.append(
                    f"{cmp.label} ({base.depart.strftime('%H:%M')}→{base.arrival.strftime('%H:%M')}) "
                    f"scores **{base.composite:.0f}/100** — essentially a tie with the winner "
                    f"({winner.composite:.0f}); pick by preference."
                )
                continue
            saving = f"saves **{risk_delta:.2f} risk-km**" if risk_delta > 0 else (
                f"costs {-risk_delta:.2f} risk-km extra"
            )
            rationale.append(
                f"vs {cmp.label} ({base.depart.strftime('%H:%M')}→{base.arrival.strftime('%H:%M')}, "
                f"composite {base.composite:.0f}): winner {saving} along the "
                f"{base.distance_km:.1f} km corridor, "
                f"+{delta:.0f} pts on the composite."
            )

        # Cross-flavor note: if a different flavor at the winner's arrival
        # would have come close, surface that — it tells the user how much
        # routing choice matters at this minute.
        same_arrival_alts = [
            c for row in grid for c in row
            if c.arrival == winner.arrival and c.alpha != winner.alpha
        ]
        if same_arrival_alts:
            best_alt = max(same_arrival_alts, key=lambda c: c.composite)
            gap = winner.composite - best_alt.composite
            if gap >= 4.0:
                rationale.append(
                    f"At {winner.arrival.strftime('%H:%M')}, the **{winner.flavor}** "
                    f"flavor beats **{best_alt.flavor}** by {gap:.0f} pts "
                    f"({winner.composite:.0f} vs {best_alt.composite:.0f}) — routing matters "
                    f"more than departure timing here."
                )

        # Forecast endpoint colour — call out evening peak / dawn calm if extreme.
        if winner.forecast_at_dest >= 0.55:
            rationale.append(
                f"Destination cell is forecast-hot at {winner.arrival.strftime('%H:%M')} "
                f"({winner.forecast_at_dest:.2f}); the winner threads around it with a "
                f"min-safety of {winner.min_safety}."
            )
        elif winner.forecast_at_dest <= 0.15:
            rationale.append(
                f"Destination cell sits in a quiet forecast pocket at "
                f"{winner.arrival.strftime('%H:%M')} ({winner.forecast_at_dest:.2f}) — "
                f"that pocket is why this slot wins."
            )

    feasibility_note = ""
    if n_infeasible:
        total = len(all_candidates)
        feasibility_note = (
            f"{n_infeasible}/{total} cells would require leaving in the past "
            f"and are dimmed in the grid."
        )

    return TempoResult(
        origin=origin,
        dest=dest,
        dest_label=dest_label,
        arrive_window=(w_start, w_end),
        step_min=actual_step,
        now=now,
        flavors=flavors,
        arrival_slots=arrival_slots,
        grid=grid,
        winner=winner,
        runners_up=runners_up,
        comparisons=comparisons,
        headline=headline,
        advisory_line=advisory_line,
        rationale=rationale,
        feasibility_note=feasibility_note,
    )
