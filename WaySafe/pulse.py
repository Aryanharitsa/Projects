"""Pulse — Today's Outlook brief for WaySafe.

The question no other surface answers
-------------------------------------
Compass picks **where** to go.
StaySafe picks **where to sleep**.
Plan Route picks **how** to get there.
Tempo picks **when** to leave.
Forecast shows a single point's 24-h risk curve.
Sentinel tells you which clusters are escalating.
Refuge plans an egress in a panic.

None of them answer the most common *morning* question a traveller
asks of a safety app: *"I'm awake, what do I need to know about my day,
and what has actually changed since yesterday?"*. Pulse is the temporal
*delta* surface that closes that gap. It treats a traveller's day as a
small portfolio of **watched points** — their stay, the two or three
places they're planning to go — and produces a one-page brief that:

  1. Re-scores every watched point at **now** *and* at **now − 24 h**,
     surfacing the signed safety delta and the biggest mover.
  2. Re-runs the forecast curve for **today** and for **yesterday**
     (same point, prior-day DOW) so a "calm yesterday → restless today"
     swing is visible at a glance.
  3. Finds the best **3-hour outdoor window** today by minimising the
     *joint* forecast risk across all watched points
     (`joint(h) = max_p curve_p(h)`).
  4. Intersects active Sentinel clusters with each watched point's
     ~1.5 km halo so the brief names *which* hotspots are touching the
     day's plan and how their velocity has shifted.
  5. Confirms **refuge readiness** at the stay — is the closest help
     POI still scored Safe / Caution band? (Reuses `refuge.find_refuge`
     so the answer agrees with the SOS tab.)
  6. Drains the per-point findings into a ranked **change log** ("what
     actually changed since yesterday") and a prioritised **plan-of-day
     checklist** ("what I'd do today, in order").

Pulse is pure composition — it adds zero new physics. Every number comes
from an engine that already ships:
`safety.compute_safety` · `forecast.HazardForecaster` ·
`sentinel.cluster_incidents` · `refuge.find_refuge`. The *new* thing
Pulse adds is the *time-delta* dimension: WaySafe up to Day 55 was a
suite of *forward-looking planners*; Pulse is the first surface that
asks "**what's different now than 24 hours ago**" — the signal that
makes a daily brief actually worth opening.

Outputs
-------
- `PulseSnapshot` per watched point (score now/24h-ago, delta, curve,
  best-3h window, cluster intersections, refuge band, changes).
- `PulseDay` aggregates the day: biggest mover, overall mood, joint
  risk curve, best & worst outdoor windows, ranked change log, action
  checklist, `waysafe.pulse.v1` JSON envelope, markdown digest.

Pure-Python, zero new deps.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Iterable, List, Mapping, Optional, Sequence, Tuple

from utils import haversine_km
from safety import compute_safety, SafetyResult
from forecast import HazardForecaster
import sentinel as sn
import refuge as rfg


# ---------------- bands / moods ----------------

# Aggregate mood ladder. Drives the hero hue and headline tone.
PULSE_MOODS: Tuple[Tuple[str, str], ...] = (
    ("Calm",     "#53E3A6"),
    ("Watch",    "#F9C440"),
    ("Active",   "#FF9F43"),
    ("Critical", "#FF3D60"),
)
_MOOD_ORDER = {m: i for i, (m, _) in enumerate(PULSE_MOODS)}

# Bands per point — borrowed from safety so the two surfaces agree.
POINT_BAND_HUE: dict[str, str] = {
    "Safe":      "#53E3A6",
    "Caution":   "#F9C440",
    "High Risk": "#FF7F50",
    "Danger":    "#FF3D60",
}

# Geometry knobs (kept explicit so the brief can quote them).
NEW_INCIDENT_RADIUS_KM    = 1.0
CLUSTER_INTERSECT_KM      = 1.5
OUTDOOR_WINDOW_HOURS      = 3
SIGNIFICANT_DELTA_PTS     = 5
MAJOR_DELTA_PTS           = 10


# ---------------- dataclasses ----------------

@dataclass
class WatchedPoint:
    kind: str               # "stay" | "destination" | "custom"
    label: str
    lat: float
    lon: float

    @property
    def glyph(self) -> str:
        return {"stay": "🏠", "destination": "📍", "custom": "🧭"}.get(self.kind, "📍")


@dataclass
class ClusterPing:
    cluster_id: int
    label: str              # human label, e.g. "Baga night cluster"
    dominant_category: str
    status_now: str
    velocity: float
    distance_km: float       # edge distance from watched point to cluster halo
    recent_count: int
    is_escalating: bool      # status in {Critical, Emerging}


@dataclass
class PulseSnapshot:
    point: WatchedPoint
    score_now: int
    score_24h_ago: int
    delta_score: int
    band_now: str
    band_24h_ago: str
    new_incidents_24h: int
    dominant_new_category: Optional[str]
    intersecting_clusters: List[ClusterPing] = field(default_factory=list)
    hour_curve_today: List[float] = field(default_factory=list)        # 24 floats in [0,1]
    hour_curve_yesterday: List[float] = field(default_factory=list)    # 24 floats in [0,1]
    best_window: Tuple[int, int] = (10, 13)                            # [start_hour, end_hour)
    best_window_risk: float = 0.0
    worst_window: Tuple[int, int] = (22, 1)
    worst_window_risk: float = 0.0
    refuge_band: str = "Unknown"
    refuge_score: int = 0
    refuge_label: Optional[str] = None
    refuge_distance_km: Optional[float] = None
    changes: List[str] = field(default_factory=list)
    signal: float = 0.0                                                 # absolute "mover" score

    @property
    def band_hue(self) -> str:
        return POINT_BAND_HUE.get(self.band_now, "#8892A6")

    @property
    def delta_label(self) -> str:
        if self.delta_score > 0:
            return f"+{self.delta_score} pts"
        if self.delta_score < 0:
            return f"{self.delta_score} pts"
        return "±0"

    @property
    def delta_arrow(self) -> str:
        if self.delta_score >= MAJOR_DELTA_PTS:  return "▲▲"
        if self.delta_score >= SIGNIFICANT_DELTA_PTS:  return "▲"
        if self.delta_score <= -MAJOR_DELTA_PTS: return "▼▼"
        if self.delta_score <= -SIGNIFICANT_DELTA_PTS: return "▼"
        return "→"

    @property
    def band_changed(self) -> bool:
        return self.band_now != self.band_24h_ago


@dataclass
class PulseDay:
    now: datetime
    snapshots: List[PulseSnapshot]
    biggest_mover: Optional[PulseSnapshot]
    overall_band: str
    overall_mood: str
    overall_mood_hue: str
    joint_curve: List[float]
    best_outdoor_window: Tuple[int, int]
    best_outdoor_window_risk: float
    worst_outdoor_window: Tuple[int, int]
    worst_outdoor_window_risk: float
    sentinel_intersections: List[ClusterPing] = field(default_factory=list)
    change_log: List[str] = field(default_factory=list)
    actions: List[str] = field(default_factory=list)
    headline: str = ""
    advisory_line: str = ""
    # Diagnostics so the brief is reproducible.
    n_incidents_24h_total: int = 0
    n_clusters_active: int = 0

    # ---- serialisation ----

    def to_dict(self) -> dict:
        def snap(s: PulseSnapshot) -> dict:
            return {
                "point": {
                    "kind": s.point.kind,
                    "label": s.point.label,
                    "lat": s.point.lat, "lon": s.point.lon,
                },
                "score_now": s.score_now,
                "score_24h_ago": s.score_24h_ago,
                "delta_score": s.delta_score,
                "band_now": s.band_now,
                "band_24h_ago": s.band_24h_ago,
                "band_changed": s.band_changed,
                "new_incidents_24h": s.new_incidents_24h,
                "dominant_new_category": s.dominant_new_category,
                "intersecting_clusters": [
                    {
                        "id": c.cluster_id, "label": c.label,
                        "dominant_category": c.dominant_category,
                        "status": c.status_now, "velocity": c.velocity,
                        "distance_km": c.distance_km,
                        "recent_count": c.recent_count,
                        "escalating": c.is_escalating,
                    }
                    for c in s.intersecting_clusters
                ],
                "hour_curve_today": s.hour_curve_today,
                "hour_curve_yesterday": s.hour_curve_yesterday,
                "best_window": list(s.best_window),
                "best_window_risk": s.best_window_risk,
                "worst_window": list(s.worst_window),
                "worst_window_risk": s.worst_window_risk,
                "refuge": {
                    "band": s.refuge_band,
                    "score": s.refuge_score,
                    "label": s.refuge_label,
                    "distance_km": s.refuge_distance_km,
                },
                "changes": list(s.changes),
                "signal": s.signal,
            }
        return {
            "schema": "waysafe.pulse.v1",
            "now": self.now.isoformat(),
            "overall_band": self.overall_band,
            "overall_mood": self.overall_mood,
            "headline": self.headline,
            "advisory_line": self.advisory_line,
            "joint_curve": self.joint_curve,
            "best_outdoor_window": list(self.best_outdoor_window),
            "best_outdoor_window_risk": self.best_outdoor_window_risk,
            "worst_outdoor_window": list(self.worst_outdoor_window),
            "worst_outdoor_window_risk": self.worst_outdoor_window_risk,
            "biggest_mover_label": self.biggest_mover.point.label if self.biggest_mover else None,
            "biggest_mover_delta": self.biggest_mover.delta_score if self.biggest_mover else 0,
            "snapshots": [snap(s) for s in self.snapshots],
            "sentinel_intersections": [
                {
                    "id": c.cluster_id, "label": c.label,
                    "dominant_category": c.dominant_category,
                    "status": c.status_now, "velocity": c.velocity,
                    "distance_km": c.distance_km,
                    "recent_count": c.recent_count,
                    "escalating": c.is_escalating,
                }
                for c in self.sentinel_intersections
            ],
            "change_log": list(self.change_log),
            "actions": list(self.actions),
            "n_incidents_24h_total": self.n_incidents_24h_total,
            "n_clusters_active": self.n_clusters_active,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    def to_markdown(self) -> str:
        out: List[str] = []
        out.append(f"# Pulse — Today's Outlook")
        out.append(
            f"_{self.now.strftime('%a %d %b · %H:%M')}_ · mood **{self.overall_mood}** "
            f"· overall band **{self.overall_band}**"
        )
        out.append("")
        if self.headline:
            out.append(f"> {self.headline}")
            out.append("")
        if self.advisory_line:
            out.append(self.advisory_line)
            out.append("")

        bw_start, bw_end = self.best_outdoor_window
        out.append(
            f"**Best outdoor window today**: {bw_start:02d}:00 – {bw_end:02d}:00 "
            f"· joint risk {self.best_outdoor_window_risk:.2f}"
        )
        ww_start, ww_end = self.worst_outdoor_window
        out.append(
            f"**Avoid**: {ww_start:02d}:00 – {ww_end:02d}:00 "
            f"· joint risk {self.worst_outdoor_window_risk:.2f}"
        )
        out.append("")

        out.append("## Watched points")
        out.append("")
        out.append("| Point | Score now | Δ 24h | Band | New inc. (1 km) | Best 3 h |")
        out.append("|---|---:|---:|---|---:|---|")
        for s in self.snapshots:
            best_lbl = f"{s.best_window[0]:02d}:00–{s.best_window[1]:02d}:00"
            out.append(
                f"| {s.point.glyph} {s.point.label} | {s.score_now} "
                f"| {s.delta_label} | {s.band_now} | {s.new_incidents_24h} | {best_lbl} |"
            )
        out.append("")

        if self.sentinel_intersections:
            out.append("## Sentinel intersections")
            for c in self.sentinel_intersections:
                badge = " (escalating)" if c.is_escalating else ""
                out.append(
                    f"- {c.label} · {c.status_now}{badge} · velocity ×{c.velocity:.1f} "
                    f"· {c.recent_count} recent · edge {c.distance_km:.2f} km"
                )
            out.append("")

        if self.change_log:
            out.append("## What changed since yesterday")
            for line in self.change_log:
                out.append(f"- {line}")
            out.append("")

        if self.actions:
            out.append("## Plan of day")
            for i, a in enumerate(self.actions, 1):
                out.append(f"{i}. {a}")
            out.append("")

        return "\n".join(out)


# ---------------- helpers ----------------

def _parse_ts(s) -> Optional[datetime]:
    if isinstance(s, datetime):
        return s.replace(tzinfo=None)
    if s is None:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "")).replace(tzinfo=None)
    except Exception:
        return None


def _coerce_records(obj) -> List[Mapping]:
    """Accept a pandas DataFrame or list-of-dicts, normalise to a plain list."""
    if obj is None:
        return []
    if isinstance(obj, list):
        return obj
    try:
        return obj.to_dict("records")
    except Exception:
        return list(obj)


def _band_for_score(score: int) -> str:
    if score >= 80: return "Safe"
    if score >= 60: return "Caution"
    if score >= 35: return "High Risk"
    return "Danger"


def _consecutive_window(curve: Sequence[float], width: int, *,
                        kind: str = "min") -> Tuple[Tuple[int, int], float]:
    """Find the K-hour consecutive window minimising (or maximising) mean risk.

    Returns ((start_hour, end_hour_exclusive), mean_risk). The end-hour is
    `start + width` modulo 24 — so a window starting at 22:00 with width=3
    reports as (22, 1).
    """
    if not curve:
        return ((0, width % 24), 0.0)
    n = len(curve)
    best_h = 0
    best_v = float("inf") if kind == "min" else float("-inf")
    for h in range(n):
        s = sum(curve[(h + i) % n] for i in range(width)) / width
        if kind == "min" and s < best_v:
            best_v = s; best_h = h
        elif kind == "max" and s > best_v:
            best_v = s; best_h = h
    return ((best_h, (best_h + width) % n), float(best_v))


def _cluster_label(c: sn.Cluster) -> str:
    """Stable, readable label for a Sentinel cluster."""
    return f"Cluster #{c.id + 1} · {c.dominant_category.title()}"


def _intersecting_clusters(
    lat: float, lon: float,
    clusters: Sequence[sn.Cluster],
    *, radius_km: float = CLUSTER_INTERSECT_KM,
) -> List[ClusterPing]:
    pings: List[ClusterPing] = []
    for c in clusters:
        d = haversine_km(lat, lon, c.center_lat, c.center_lon)
        edge = max(0.0, d - c.radius_km)
        if edge > radius_km:
            continue
        pings.append(ClusterPing(
            cluster_id=c.id,
            label=_cluster_label(c),
            dominant_category=c.dominant_category,
            status_now=c.status,
            velocity=float(c.velocity),
            distance_km=round(edge, 2),
            recent_count=int(c.recent_count),
            is_escalating=c.status in {"Critical", "Emerging"},
        ))
    # Closest, escalating-first.
    pings.sort(key=lambda p: (0 if p.is_escalating else 1, p.distance_km))
    return pings


def _filter_incidents_before(rows: Sequence[Mapping], cutoff: datetime) -> List[Mapping]:
    """Drop incidents whose `created_at` is *after* the cutoff. Used to build
    the 'yesterday's safety score' counterfactual cleanly."""
    out: List[Mapping] = []
    for r in rows:
        t = _parse_ts(r.get("created_at"))
        if t is None or t <= cutoff:
            out.append(r)
    return out


def _incidents_within(
    rows: Sequence[Mapping], lat: float, lon: float,
    *, radius_km: float, since: Optional[datetime] = None,
) -> List[Mapping]:
    out: List[Mapping] = []
    for r in rows:
        try:
            ilat = float(r.get("lat")); ilon = float(r.get("lon"))
        except (TypeError, ValueError):
            continue
        if haversine_km(lat, lon, ilat, ilon) > radius_km:
            continue
        if since is not None:
            t = _parse_ts(r.get("created_at"))
            if t is None or t < since:
                continue
        out.append(r)
    return out


def _dominant_category(rows: Sequence[Mapping]) -> Optional[str]:
    counts: dict[str, int] = {}
    for r in rows:
        cat = str(r.get("category", "other")).lower()
        counts[cat] = counts.get(cat, 0) + 1
    if not counts:
        return None
    return max(counts.items(), key=lambda x: x[1])[0]


def _signal(snapshot: PulseSnapshot) -> float:
    """Heuristic 'how much should this snapshot pull the day's attention'.

    Weights the visible levers: absolute Δscore (most legible), then new
    incidents, then escalating cluster pressure.
    """
    s = abs(snapshot.delta_score) * 1.0
    s += snapshot.new_incidents_24h * 4.0
    for c in snapshot.intersecting_clusters:
        if c.is_escalating:
            s += 6.0 + 2.0 * (c.velocity - 1.0)
        else:
            s += 1.5
    if snapshot.band_changed:
        s += 6.0
    if snapshot.refuge_band in {"High Risk", "Danger"}:
        s += 4.0
    return float(s)


def _mood_for(snapshots: Sequence[PulseSnapshot],
              cluster_intersections: Sequence[ClusterPing]) -> str:
    """Aggregate mood across the day.

    Rules (first match wins):
      - **Critical**: any watched point is Danger, or any intersecting cluster Critical.
      - **Active**:   any watched point is High Risk, or any cluster Emerging, or
                      ≥2 watched points slipped >=10 pts in 24h.
      - **Watch**:    any Caution band, any cluster Steady, or any
                      watched point dropped >=5 pts in 24h.
      - **Calm**:     otherwise.
    """
    if any(s.band_now == "Danger" for s in snapshots):
        return "Critical"
    if any(c.status_now == "Critical" for c in cluster_intersections):
        return "Critical"
    if any(s.band_now == "High Risk" for s in snapshots):
        return "Active"
    if any(c.status_now == "Emerging" for c in cluster_intersections):
        return "Active"
    if sum(1 for s in snapshots if s.delta_score <= -MAJOR_DELTA_PTS) >= 2:
        return "Active"
    if any(s.band_now == "Caution" for s in snapshots):
        return "Watch"
    if any(s.delta_score <= -SIGNIFICANT_DELTA_PTS for s in snapshots):
        return "Watch"
    return "Calm"


def _headline(day_now: datetime,
              snapshots: Sequence[PulseSnapshot],
              best_window: Tuple[int, int],
              biggest_mover: Optional[PulseSnapshot],
              mood: str) -> str:
    """Single-sentence summary — the phone-banner version of the brief."""
    parts: List[str] = []
    if mood == "Critical":
        parts.append("Critical morning")
    elif mood == "Active":
        parts.append("Active morning — watch your day")
    elif mood == "Watch":
        parts.append("Mixed signals overnight")
    else:
        parts.append("Calm morning")

    if biggest_mover and abs(biggest_mover.delta_score) >= SIGNIFICANT_DELTA_PTS:
        arrow = "down" if biggest_mover.delta_score < 0 else "up"
        parts.append(
            f"{biggest_mover.point.label} {arrow} {abs(biggest_mover.delta_score)} pts"
        )

    bw_s, bw_e = best_window
    parts.append(f"best window {bw_s:02d}:00–{bw_e:02d}:00")
    return " · ".join(parts) + "."


def _advisory_line(snapshots: Sequence[PulseSnapshot],
                   cluster_intersections: Sequence[ClusterPing],
                   mood: str) -> str:
    """One-line elaboration under the headline.

    Picks the single most-actionable thread among: a Critical/Emerging
    cluster intersection, a stay-band drop, or a fresh-incident spike.
    Falls back to a neutral 'nothing changed materially' line.
    """
    crit = next((c for c in cluster_intersections if c.status_now == "Critical"), None)
    emrg = next((c for c in cluster_intersections if c.status_now == "Emerging"), None)
    if crit is not None:
        return (
            f"{crit.label} is **Critical** — velocity ×{crit.velocity:.1f}, "
            f"{crit.recent_count} recent incidents, edge {crit.distance_km:.2f} km "
            f"from your day's plan. Re-route around it."
        )
    if emrg is not None:
        return (
            f"{emrg.label} is **Emerging** (×{emrg.velocity:.1f}). "
            f"Worth a wide berth until it cools."
        )
    worst = min(snapshots, key=lambda s: s.score_now, default=None)
    if worst is not None and worst.score_now < 60:
        return (
            f"{worst.point.label} is in **{worst.band_now}** band "
            f"(score {worst.score_now}). Treat any outing through it as a focused trip."
        )
    spike = max(snapshots, key=lambda s: s.new_incidents_24h, default=None)
    if spike is not None and spike.new_incidents_24h >= 3:
        return (
            f"{spike.new_incidents_24h} fresh incidents within 1 km of "
            f"{spike.point.label} in the last 24 h — consider tighter timing."
        )
    if mood == "Calm":
        return "Nothing material changed in your day's plan overnight."
    return "Soft tilt down overnight — nothing actionable yet, but worth a check at lunch."


def _changes_for_snapshot(s: PulseSnapshot) -> List[str]:
    """Plain-English bullet list per snapshot. Used both inline and folded
    into the day's change log."""
    out: List[str] = []
    if s.delta_score <= -MAJOR_DELTA_PTS:
        out.append(
            f"{s.point.label}: safety down **{abs(s.delta_score)} pts** overnight "
            f"({s.score_24h_ago} → {s.score_now})."
        )
    elif s.delta_score <= -SIGNIFICANT_DELTA_PTS:
        out.append(
            f"{s.point.label}: safety eased {abs(s.delta_score)} pts overnight "
            f"({s.score_24h_ago} → {s.score_now})."
        )
    elif s.delta_score >= MAJOR_DELTA_PTS:
        out.append(
            f"{s.point.label}: safety improved **+{s.delta_score} pts** overnight "
            f"({s.score_24h_ago} → {s.score_now})."
        )
    if s.band_changed:
        out.append(
            f"{s.point.label}: band shifted **{s.band_24h_ago} → {s.band_now}**."
        )
    if s.new_incidents_24h >= 1:
        cat = f" (mostly {s.dominant_new_category})" if s.dominant_new_category else ""
        out.append(
            f"{s.point.label}: **{s.new_incidents_24h} new incident"
            f"{'s' if s.new_incidents_24h != 1 else ''}** "
            f"within {NEW_INCIDENT_RADIUS_KM:g} km in the last 24 h{cat}."
        )
    for c in s.intersecting_clusters:
        if c.is_escalating:
            out.append(
                f"{s.point.label}: **{c.label}** is {c.status_now} "
                f"(×{c.velocity:.1f}) — edge {c.distance_km:.2f} km."
            )
    return out


def _actions_for_day(day: "PulseDay") -> List[str]:
    """Prioritised plan-of-day checklist. Top item first."""
    acts: List[str] = []

    # 1) If any cluster intersects and is escalating, that's the headline action.
    crit = next((c for c in day.sentinel_intersections if c.status_now == "Critical"), None)
    if crit is not None:
        acts.append(
            f"Re-plan any leg through {crit.label} — pick a corridor "
            f"≥{CLUSTER_INTERSECT_KM:g} km away and prefer the Tempo winner over a now-departure."
        )
    elif any(c.is_escalating for c in day.sentinel_intersections):
        emrg = next(c for c in day.sentinel_intersections if c.is_escalating)
        acts.append(
            f"Hold a wide berth around {emrg.label} (velocity ×{emrg.velocity:.1f}) "
            f"until it cools — re-check Pulse at lunch."
        )

    # 2) Time the day around the best outdoor window.
    bw_s, bw_e = day.best_outdoor_window
    if day.best_outdoor_window_risk <= 0.4:
        acts.append(
            f"Front-load outdoor plans into **{bw_s:02d}:00–{bw_e:02d}:00** "
            f"(joint risk {day.best_outdoor_window_risk:.2f}). Keep markets, beaches, walks here."
        )
    else:
        acts.append(
            f"No quiet 3-h window today (best is {bw_s:02d}:00–{bw_e:02d}:00 "
            f"at joint risk {day.best_outdoor_window_risk:.2f}). Keep outings short and pick "
            f"the safest single hour from the ribbon."
        )

    # 3) Worst window — avoid.
    ww_s, ww_e = day.worst_outdoor_window
    acts.append(
        f"Avoid outdoor plans in **{ww_s:02d}:00–{ww_e:02d}:00** "
        f"(joint risk {day.worst_outdoor_window_risk:.2f})."
    )

    # 4) Per-point follow-ups.
    if day.biggest_mover and abs(day.biggest_mover.delta_score) >= SIGNIFICANT_DELTA_PTS:
        mover = day.biggest_mover
        if mover.delta_score < 0:
            acts.append(
                f"Re-check {mover.point.label} before heading out — "
                f"safety slid {abs(mover.delta_score)} pts overnight to {mover.band_now}."
            )
        else:
            acts.append(
                f"{mover.point.label} improved {mover.delta_score} pts overnight — "
                f"good to lock it in for today's plan."
            )

    # 5) Spike fallback.
    spike = max(day.snapshots, key=lambda s: s.new_incidents_24h, default=None)
    if spike is not None and spike.new_incidents_24h >= 3:
        acts.append(
            f"Skim the Map tab around {spike.point.label} — "
            f"{spike.new_incidents_24h} new incidents within "
            f"{NEW_INCIDENT_RADIUS_KM:g} km overnight."
        )

    # 6) Refuge sanity.
    stay = next((s for s in day.snapshots if s.point.kind == "stay"), None)
    if stay is not None and stay.refuge_band in {"High Risk", "Danger"}:
        acts.append(
            f"Memorise the nearest non-stay refuge before evening — "
            f"the stay's closest help POI is in {stay.refuge_band} band."
        )

    # 7) Calm-day default.
    if not acts:
        acts.append("Day looks clean — no special precautions beyond the usual.")
    return acts[:6]


# ---------------- public entrypoint ----------------

def compose_pulse(
    *,
    watched: Sequence[WatchedPoint],
    incidents: Iterable[Mapping] | None,
    geofences: Mapping,
    pois: Iterable[Mapping] | None,
    forecaster: Optional[HazardForecaster] = None,
    now: Optional[datetime] = None,
    clusters: Optional[Sequence[sn.Cluster]] = None,
) -> PulseDay:
    """Single entrypoint. Composes every engine, returns a `PulseDay`.

    `watched` is the list of points the brief is *about* — typically the
    user's stay plus 1–3 planned destinations. Order is preserved in the
    output. `forecaster` is optional; if absent the curves are zeros and
    the best-window picker falls back to mid-morning.

    `clusters` may be passed in (so callers that already ran Sentinel for
    the Map / Sentinel tab don't pay for a re-cluster). Otherwise the
    function runs `sentinel.cluster_incidents` itself.
    """
    now = now or datetime.utcnow()
    inc_now  = _coerce_records(incidents)
    pois_all = _coerce_records(pois)
    geofences = geofences or {"features": []}

    # Pre-compute the 24h-ago incident view (drop incidents created after cutoff).
    cutoff = now - timedelta(hours=24)
    inc_24h_ago = _filter_incidents_before(inc_now, cutoff)

    # Cluster the *now* world if the caller didn't.
    if clusters is None:
        clusters_now, _ = sn.cluster_incidents(inc_now, now=now)
    else:
        clusters_now = list(clusters)

    snapshots: List[PulseSnapshot] = []
    for wp in watched:
        snap = _snapshot_for(
            wp, now=now, cutoff=cutoff,
            inc_now=inc_now, inc_24h_ago=inc_24h_ago,
            pois_all=pois_all, geofences=geofences,
            forecaster=forecaster, clusters_now=clusters_now,
        )
        snapshots.append(snap)

    # Biggest mover by signed Δ magnitude, tiebreak: most-escalating cluster.
    biggest_mover: Optional[PulseSnapshot] = None
    if snapshots:
        biggest_mover = max(
            snapshots,
            key=lambda s: (abs(s.delta_score), s.signal),
        )
        if abs(biggest_mover.delta_score) < 1 and biggest_mover.signal < 1:
            biggest_mover = None

    overall_band = min(
        (s.band_now for s in snapshots),
        key=lambda b: ["Safe", "Caution", "High Risk", "Danger"].index(b)
            if b in ["Safe", "Caution", "High Risk", "Danger"] else 99,
        default="Safe",
    )
    # The mood ladder reads the worst band as "worst" — invert it here.
    band_rank = {"Safe": 0, "Caution": 1, "High Risk": 2, "Danger": 3}
    overall_band = max(
        (s.band_now for s in snapshots),
        key=lambda b: band_rank.get(b, -1),
        default="Safe",
    )

    # Joint risk curve: max forecast over watched points per hour.
    joint_curve: List[float] = [0.0] * 24
    for h in range(24):
        joint_curve[h] = max((s.hour_curve_today[h] for s in snapshots if s.hour_curve_today),
                              default=0.0)
    best_window, best_risk = _consecutive_window(joint_curve, OUTDOOR_WINDOW_HOURS, kind="min")
    worst_window, worst_risk = _consecutive_window(joint_curve, OUTDOOR_WINDOW_HOURS, kind="max")

    # De-dupe cluster intersections across watched points; keep nearest occurrence.
    seen: dict[int, ClusterPing] = {}
    for s in snapshots:
        for c in s.intersecting_clusters:
            prev = seen.get(c.cluster_id)
            if prev is None or c.distance_km < prev.distance_km:
                seen[c.cluster_id] = c
    sentinel_intersections = sorted(
        seen.values(),
        key=lambda c: (0 if c.is_escalating else 1, c.distance_km),
    )

    mood = _mood_for(snapshots, sentinel_intersections)
    mood_hue = dict(PULSE_MOODS).get(mood, "#8892A6")
    headline = _headline(now, snapshots, best_window, biggest_mover, mood)
    advisory_line = _advisory_line(snapshots, sentinel_intersections, mood)

    # Change log: collect per-snapshot changes, then rank by signal magnitude.
    change_log: List[Tuple[float, str]] = []
    for s in snapshots:
        for line in _changes_for_snapshot(s):
            # Rank by the snapshot signal so the highest-mover's lines float to top.
            change_log.append((s.signal + 0.01 * len(line), line))
    change_log.sort(key=lambda t: -t[0])
    flat_log = [line for _, line in change_log][:8]

    day = PulseDay(
        now=now,
        snapshots=snapshots,
        biggest_mover=biggest_mover,
        overall_band=overall_band,
        overall_mood=mood,
        overall_mood_hue=mood_hue,
        joint_curve=joint_curve,
        best_outdoor_window=best_window,
        best_outdoor_window_risk=best_risk,
        worst_outdoor_window=worst_window,
        worst_outdoor_window_risk=worst_risk,
        sentinel_intersections=sentinel_intersections,
        change_log=flat_log,
        headline=headline,
        advisory_line=advisory_line,
        n_incidents_24h_total=sum(s.new_incidents_24h for s in snapshots),
        n_clusters_active=len(clusters_now),
    )
    day.actions = _actions_for_day(day)
    return day


# ---------------- per-watched-point composer ----------------

def _snapshot_for(
    wp: WatchedPoint, *,
    now: datetime,
    cutoff: datetime,
    inc_now: Sequence[Mapping],
    inc_24h_ago: Sequence[Mapping],
    pois_all: Sequence[Mapping],
    geofences: Mapping,
    forecaster: Optional[HazardForecaster],
    clusters_now: Sequence[sn.Cluster],
) -> PulseSnapshot:
    # 1) Safety now & 24h-ago, computed under the same engine for self-consistency.
    safe_now: SafetyResult  = compute_safety(wp.lat, wp.lon, inc_now,     geofences, pois_all, now=now)
    safe_24h: SafetyResult  = compute_safety(wp.lat, wp.lon, inc_24h_ago, geofences, pois_all, now=cutoff)
    delta = int(safe_now.score) - int(safe_24h.score)

    # 2) New incidents within radius, last 24h.
    new_inc = _incidents_within(inc_now, wp.lat, wp.lon,
                                radius_km=NEW_INCIDENT_RADIUS_KM, since=cutoff)
    dom_cat = _dominant_category(new_inc)

    # 3) Cluster intersections.
    pings = _intersecting_clusters(wp.lat, wp.lon, clusters_now)

    # 4) Hour curves today & yesterday-DOW. Yesterday gives the temporal-delta lens.
    curve_today: List[float] = []
    curve_yesterday: List[float] = []
    if forecaster is not None:
        today_base = now.replace(hour=0, minute=0, second=0, microsecond=0)
        yesterday_base = today_base - timedelta(days=1)
        curve_today = list(forecaster.risk_curve(wp.lat, wp.lon, day=today_base))
        curve_yesterday = list(forecaster.risk_curve(wp.lat, wp.lon, day=yesterday_base))
    else:
        curve_today = [0.0] * 24
        curve_yesterday = [0.0] * 24

    best_window, best_risk   = _consecutive_window(curve_today, OUTDOOR_WINDOW_HOURS, kind="min")
    worst_window, worst_risk = _consecutive_window(curve_today, OUTDOOR_WINDOW_HOURS, kind="max")

    # 5) Refuge readiness — only material for the stay point but cheap to compute.
    refuge_band = "Unknown"
    refuge_score = 0
    refuge_label: Optional[str] = None
    refuge_distance_km: Optional[float] = None
    try:
        rr = rfg.find_refuge(
            wp.lat, wp.lon,
            pois=pois_all, incidents=inc_now, geofences=geofences,
            now=now, max_radius_km=4.0, max_results=1,
        )
        top = rr.options[0] if rr.options else None
        if top is not None:
            refuge_band  = top.band
            refuge_score = int(top.refuge_score)
            refuge_label = top.poi_name
            refuge_distance_km = round(top.distance_km, 2)
    except Exception:
        # Refuge is optional context — never break the brief.
        pass

    snap = PulseSnapshot(
        point=wp,
        score_now=int(safe_now.score),
        score_24h_ago=int(safe_24h.score),
        delta_score=delta,
        band_now=safe_now.band,
        band_24h_ago=safe_24h.band,
        new_incidents_24h=len(new_inc),
        dominant_new_category=dom_cat,
        intersecting_clusters=pings,
        hour_curve_today=curve_today,
        hour_curve_yesterday=curve_yesterday,
        best_window=best_window,
        best_window_risk=best_risk,
        worst_window=worst_window,
        worst_window_risk=worst_risk,
        refuge_band=refuge_band,
        refuge_score=refuge_score,
        refuge_label=refuge_label,
        refuge_distance_km=refuge_distance_km,
    )
    snap.signal = _signal(snap)
    snap.changes = _changes_for_snapshot(snap)
    return snap
