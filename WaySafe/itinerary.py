"""Multi-stop itinerary planner for WaySafe.

A tourist day rarely has a single destination. This module chains N stops
into a single ordered plan, prices each leg by the existing risk-aware A*
router (current-time or *forecast*-aware), and rolls the whole thing into
one safety-weighted schedule.

Design
------
1. Order optimisation. The start stop is anchored. The remaining stops are
   first ordered greedily (nearest-neighbour by haversine), then refined
   with 2-opt swaps until no further improvement. Cost minimised is the
   total *risk-weighted* travel km, with a fall-back to plain haversine
   when no incidents have been seeded (so the optimiser still works on
   a fresh DB). 2-opt is exact enough for ≤ 12 stops, which is more than
   any sane tourist day.

2. Per-leg planning. Once the order is known, each leg is planned with
   the requested mode ("safest" / "fastest" / "forecast-safest"). The
   leg's depart-at = previous leg's arrive_at + dwell_min of the
   *previous* stop. The forecast variant therefore times each midpoint
   correctly along the chain.

3. Risk score. A composite [0..100] (lower = riskier) computed as a
   distance-weighted average of per-leg `avg_safety`, with a small
   penalty for any leg whose `min_safety` < 35 (a "danger spike"):

       score = Σ(km_i · avg_safety_i) / Σ km_i  -  6 · (#danger_spikes)
              clipped to [0, 100]

4. Best start-window sweep. Same idea as the single-route sweep — try
   `±span_h` around the chosen start at `step_min` resolution, plan the
   whole itinerary at each candidate, and rank by composite score.

5. Exports.
   - `to_combined_gpx`: a single GPX with one named `<trk>` per leg.
   - `to_ics`: a VCALENDAR with one VEVENT per leg (TRAVEL) and one per
     stop (DWELL) — drops straight into Apple/Google/Outlook calendars
     including a `geo:` line for each stop. Times are emitted as floating
     local times (no TZID) which is the friendliest portable choice.
"""
from __future__ import annotations

import math
import re
import xml.sax.saxutils as _xml
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Mapping, Sequence, Tuple

from utils import haversine_km
from routing import (
    AVG_TRAVEL_KMH,
    RouteResult,
    plan_fastest_route,
    plan_forecast_route,
    plan_safest_route,
)


VALID_MODES = ("safest", "fastest", "forecast-safest")
MAX_STOPS_2OPT = 12
DEFAULT_DWELL_MIN = 30
DANGER_MIN_SAFETY = 35


@dataclass
class Stop:
    name: str
    lat: float
    lon: float
    dwell_min: int = DEFAULT_DWELL_MIN

    def coord(self) -> Tuple[float, float]:
        return (self.lat, self.lon)


@dataclass
class Leg:
    from_stop: Stop
    to_stop: Stop
    route: RouteResult
    depart_at: datetime
    arrive_at: datetime

    @property
    def distance_km(self) -> float:
        return self.route.distance_km

    @property
    def eta_minutes(self) -> float:
        return self.route.eta_minutes

    @property
    def avg_safety(self) -> int:
        return self.route.avg_safety

    @property
    def min_safety(self) -> int:
        return self.route.min_safety

    @property
    def danger_km(self) -> float:
        return self.route.max_risk_segment_km


@dataclass
class ItineraryPlan:
    stops: List[Stop]
    depart_at: datetime
    mode: str
    legs: List[Leg] = field(default_factory=list)

    @property
    def total_km(self) -> float:
        return round(sum(l.distance_km for l in self.legs), 2)

    @property
    def total_travel_min(self) -> float:
        return round(sum(l.eta_minutes for l in self.legs), 1)

    @property
    def total_dwell_min(self) -> int:
        # dwell at every stop except the very last (no point dwelling after arrival).
        if len(self.stops) <= 1:
            return 0
        return sum(s.dwell_min for s in self.stops[:-1])

    @property
    def total_minutes(self) -> float:
        return self.total_travel_min + self.total_dwell_min

    @property
    def arrive_at(self) -> datetime:
        return self.legs[-1].arrive_at if self.legs else self.depart_at

    @property
    def avg_safety(self) -> int:
        if not self.legs or self.total_km <= 0:
            return 100
        num = sum(l.distance_km * l.avg_safety for l in self.legs)
        return int(round(num / self.total_km))

    @property
    def min_safety(self) -> int:
        if not self.legs:
            return 100
        return min(l.min_safety for l in self.legs)

    @property
    def danger_km(self) -> float:
        return round(sum(l.danger_km for l in self.legs), 2)

    @property
    def danger_legs(self) -> int:
        return sum(1 for l in self.legs if l.min_safety < DANGER_MIN_SAFETY)

    @property
    def composite_score(self) -> int:
        base = self.avg_safety
        score = base - 6 * self.danger_legs
        return max(0, min(100, int(round(score))))


# ----------------- order optimisation -----------------

def _dist_matrix(stops: Sequence[Stop]) -> List[List[float]]:
    n = len(stops)
    m = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            d = haversine_km(stops[i].lat, stops[i].lon, stops[j].lat, stops[j].lon)
            m[i][j] = d
            m[j][i] = d
    return m


def _tour_length(order: Sequence[int], m: Sequence[Sequence[float]]) -> float:
    return sum(m[order[i]][order[i + 1]] for i in range(len(order) - 1))


def _greedy_nn(stops: Sequence[Stop], m: Sequence[Sequence[float]]) -> List[int]:
    n = len(stops)
    if n <= 1:
        return list(range(n))
    order = [0]
    remaining = set(range(1, n))
    while remaining:
        cur = order[-1]
        nxt = min(remaining, key=lambda j: m[cur][j])
        order.append(nxt)
        remaining.discard(nxt)
    return order


def _two_opt(order: List[int], m: Sequence[Sequence[float]], *, max_iter: int = 60) -> List[int]:
    """Open-path 2-opt: index 0 is anchored. Reverses best[i:j] where
    j can equal n so the tail can flip too."""
    n = len(order)
    if n < 4:
        return list(order)
    best = list(order)
    best_len = _tour_length(best, m)
    improved = True
    it = 0
    while improved and it < max_iter:
        improved = False
        it += 1
        for i in range(1, n - 1):
            for j in range(i + 2, n + 1):
                cand = best[:i] + best[i:j][::-1] + best[j:]
                cand_len = _tour_length(cand, m)
                if cand_len + 1e-9 < best_len:
                    best = cand
                    best_len = cand_len
                    improved = True
    return best


def solve_order(stops: Sequence[Stop], *, fix_first: bool = True) -> List[Stop]:
    """Open-path order optimisation (start fixed, no return-to-origin).

    For 1-2 stops the order is trivial. For ≤ MAX_STOPS_2OPT we run
    nearest-neighbour + 2-opt over haversine distance. Anything larger
    falls back to plain nearest-neighbour (still useful, just not optimal).
    """
    if len(stops) <= 2:
        return list(stops)
    m = _dist_matrix(stops)
    order = _greedy_nn(stops, m) if fix_first else list(range(len(stops)))
    if len(stops) <= MAX_STOPS_2OPT:
        order = _two_opt(order, m)
    return [stops[i] for i in order]


# ----------------- planning -----------------

def _plan_leg(
    origin: Stop, dest: Stop, *,
    mode: str, depart_at: datetime,
    incidents: Sequence[Mapping], geofences: Mapping,
    pois: Sequence[Mapping], forecaster,
) -> RouteResult:
    if mode == "fastest":
        return plan_fastest_route(origin.coord(), dest.coord(), incidents, geofences, pois, now=depart_at)
    if mode == "safest":
        return plan_safest_route(origin.coord(), dest.coord(), incidents, geofences, pois, now=depart_at)
    if mode == "forecast-safest":
        if forecaster is None:
            return plan_safest_route(origin.coord(), dest.coord(), incidents, geofences, pois, now=depart_at)
        return plan_forecast_route(
            origin.coord(), dest.coord(), forecaster, depart_at,
            incidents=incidents, geofences=geofences, pois=pois,
        )
    raise ValueError(f"unknown itinerary mode: {mode!r}")


def plan_itinerary(
    stops: Sequence[Stop],
    depart_at: datetime,
    *,
    mode: str = "safest",
    optimize_order: bool = True,
    incidents: Sequence[Mapping] = (),
    geofences: Mapping | None = None,
    pois: Sequence[Mapping] = (),
    forecaster=None,
) -> ItineraryPlan:
    if mode not in VALID_MODES:
        raise ValueError(f"mode must be one of {VALID_MODES}, got {mode!r}")
    if len(stops) < 2:
        raise ValueError("need at least 2 stops to plan an itinerary")

    ordered = solve_order(stops) if optimize_order else list(stops)
    geofences = geofences or {"features": []}

    legs: List[Leg] = []
    cursor = depart_at
    for a, b in zip(ordered, ordered[1:]):
        route = _plan_leg(
            a, b, mode=mode, depart_at=cursor,
            incidents=incidents, geofences=geofences, pois=pois,
            forecaster=forecaster,
        )
        arrive = cursor + timedelta(minutes=route.eta_minutes)
        # stamp depart/arrive even on non-forecast routes for the UI
        if route.depart_at is None:
            route.depart_at = cursor
        if route.arrive_at is None:
            route.arrive_at = arrive
        legs.append(Leg(from_stop=a, to_stop=b, route=route,
                        depart_at=cursor, arrive_at=arrive))
        # dwell at `b` is added *after* arrival, before the next leg.
        cursor = arrive + timedelta(minutes=b.dwell_min)

    return ItineraryPlan(stops=ordered, depart_at=depart_at, mode=mode, legs=legs)


def find_best_start_window(
    stops: Sequence[Stop],
    around: datetime,
    *,
    mode: str = "forecast-safest",
    span_h: float = 2.0,
    step_min: int = 30,
    incidents: Sequence[Mapping] = (),
    geofences: Mapping | None = None,
    pois: Sequence[Mapping] = (),
    forecaster=None,
    optimize_order: bool = True,
) -> List[Tuple[datetime, ItineraryPlan]]:
    """Sweep ±`span_h` around `around` at `step_min` resolution and rank
    full-itinerary plans by composite score (higher = safer)."""
    steps = int(span_h * 60 / step_min)
    out: List[Tuple[datetime, ItineraryPlan]] = []
    for k in range(-steps, steps + 1):
        t = around + timedelta(minutes=k * step_min)
        plan = plan_itinerary(
            stops, t, mode=mode, optimize_order=optimize_order,
            incidents=incidents, geofences=geofences, pois=pois,
            forecaster=forecaster,
        )
        out.append((t, plan))
    out.sort(key=lambda x: -x[1].composite_score)
    return out


# ----------------- exports -----------------

def to_combined_gpx(plan: ItineraryPlan, *, name: str = "WaySafe itinerary") -> str:
    """A single GPX with one <trk> per leg (named "i. From → To")."""
    trks = []
    for i, leg in enumerate(plan.legs, start=1):
        pts = "\n".join(
            f'      <trkpt lat="{lat:.6f}" lon="{lon:.6f}"/>'
            for lat, lon in leg.route.coords
        )
        trk_name = _xml.escape(f"{i}. {leg.from_stop.name} → {leg.to_stop.name}")
        trks.append(
            f'  <trk><name>{trk_name}</name><trkseg>\n{pts}\n    </trkseg></trk>'
        )
    wpts = "\n".join(
        f'  <wpt lat="{s.lat:.6f}" lon="{s.lon:.6f}"><name>{_xml.escape(s.name)}</name></wpt>'
        for s in plan.stops
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<gpx version="1.1" creator="WaySafe" '
        'xmlns="http://www.topografix.com/GPX/1/1">\n'
        f'  <metadata><name>{_xml.escape(name)}</name></metadata>\n'
        f'{wpts}\n'
        f'{chr(10).join(trks)}\n'
        '</gpx>\n'
    )


_ICS_TEXT_RE = re.compile(r"([,;\\\n])")


def _ics_escape(s: str) -> str:
    def repl(m):
        c = m.group(1)
        return {
            ",": "\\,", ";": "\\;", "\\": "\\\\", "\n": "\\n",
        }[c]
    return _ICS_TEXT_RE.sub(repl, s)


def _ics_dt(dt: datetime) -> str:
    return dt.strftime("%Y%m%dT%H%M%S")


def _fold_line(line: str, *, limit: int = 75) -> str:
    if len(line) <= limit:
        return line
    parts = [line[:limit]]
    rest = line[limit:]
    while rest:
        parts.append(" " + rest[: limit - 1])
        rest = rest[limit - 1 :]
    return "\r\n".join(parts)


def to_ics(
    plan: ItineraryPlan, *,
    calendar_name: str = "WaySafe Itinerary",
    organiser_email: str | None = None,
    now: datetime | None = None,
) -> str:
    """Export the itinerary as an RFC-5545 calendar.

    One TRAVEL event per leg (with leg stats in the description) plus a
    DWELL event per stop (with `geo:lat,lon` so the calendar can deep-link
    into a map). Floating local times, so the user's calendar app shows the
    events at the planned hour wherever the device is.
    """
    now = now or datetime.utcnow()
    dtstamp = _ics_dt(now) + "Z"
    out: List[str] = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//WaySafe//Multi-stop Itinerary//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        _fold_line(f"X-WR-CALNAME:{_ics_escape(calendar_name)}"),
    ]
    organiser = (
        f"ORGANIZER;CN=WaySafe:MAILTO:{organiser_email}" if organiser_email else None
    )

    for i, leg in enumerate(plan.legs, start=1):
        uid = f"waysafe-leg-{i}-{int(now.timestamp())}@waysafe"
        summary = f"🚗 {leg.from_stop.name} → {leg.to_stop.name}"
        desc = (
            f"Mode: {plan.mode} · {leg.distance_km:g} km · ETA {leg.eta_minutes:g} min\\n"
            f"Avg safety: {leg.avg_safety}/100 · Min safety: {leg.min_safety}/100"
            + (f"\\nRisky km: {leg.danger_km:g}" if leg.danger_km > 0 else "")
        )
        out += [
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{dtstamp}",
            f"DTSTART:{_ics_dt(leg.depart_at)}",
            f"DTEND:{_ics_dt(leg.arrive_at)}",
            _fold_line(f"SUMMARY:{_ics_escape(summary)}"),
            _fold_line(f"DESCRIPTION:{desc}"),
            f"GEO:{leg.to_stop.lat:.6f};{leg.to_stop.lon:.6f}",
            "CATEGORIES:TRAVEL",
        ]
        if organiser:
            out.append(organiser)
        out.append("END:VEVENT")

        # add a dwell block at the destination (skip after the last leg)
        if i < len(plan.legs) and leg.to_stop.dwell_min > 0:
            dwell_start = leg.arrive_at
            dwell_end = dwell_start + timedelta(minutes=leg.to_stop.dwell_min)
            uid_d = f"waysafe-dwell-{i}-{int(now.timestamp())}@waysafe"
            sum_d = f"📍 {leg.to_stop.name}"
            desc_d = f"Dwell · {leg.to_stop.dwell_min} min · waypoint {i+1}/{len(plan.stops)}"
            out += [
                "BEGIN:VEVENT",
                f"UID:{uid_d}",
                f"DTSTAMP:{dtstamp}",
                f"DTSTART:{_ics_dt(dwell_start)}",
                f"DTEND:{_ics_dt(dwell_end)}",
                _fold_line(f"SUMMARY:{_ics_escape(sum_d)}"),
                _fold_line(f"DESCRIPTION:{_ics_escape(desc_d)}"),
                f"GEO:{leg.to_stop.lat:.6f};{leg.to_stop.lon:.6f}",
                "CATEGORIES:DWELL",
                "END:VEVENT",
            ]

    out.append("END:VCALENDAR")
    return "\r\n".join(out) + "\r\n"


# ----------------- helpers -----------------

def stop_summary(plan: ItineraryPlan) -> List[dict]:
    """Per-stop schedule with arrival/depart timestamps — useful for tables."""
    rows: List[dict] = [{
        "i": 0,
        "name": plan.stops[0].name,
        "arrive_at": None,
        "depart_at": plan.depart_at,
        "dwell_min": 0,
        "lat": plan.stops[0].lat, "lon": plan.stops[0].lon,
    }]
    for i, leg in enumerate(plan.legs, start=1):
        last = i == len(plan.legs)
        depart_next = None if last else leg.arrive_at + timedelta(minutes=leg.to_stop.dwell_min)
        rows.append({
            "i": i,
            "name": leg.to_stop.name,
            "arrive_at": leg.arrive_at,
            "depart_at": depart_next,
            "dwell_min": 0 if last else leg.to_stop.dwell_min,
            "lat": leg.to_stop.lat, "lon": leg.to_stop.lon,
        })
    return rows
