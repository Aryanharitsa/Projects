"""Nomad — Adaptive Live Trip Reflow for WaySafe.

The question no other WaySafe surface answers
---------------------------------------------
Odyssey (Day 76) commits a multi-day trip *statically*: given an ordered
`OdysseyDay` list, it emits a full `TripReport` with a verdict, a
weakest-link block, and three swap suggestions.  That is the correct
answer *at planning time*.

Real trips do not stay static.  You wake up on Day 2 of a 4-day trip and
overnight:

  * a Sentinel cluster escalated on the corridor your Day-3 plan runs
    through;
  * the forecaster's 24-h curve for tomorrow's stop shifted from Calm to
    Restless because a new incident bin lit up;
  * a fresh accident report landed near tomorrow's stay;
  * a geofence widened around your Day-4 destination.

None of these show up in the original Odyssey report because Odyssey ran
before those signals existed.  Up to today, the traveller has to open
Pulse, cross-check Sentinel, hand-re-compose Odyssey with the new inputs,
and eyeball the delta.  Every surface *has* the physics — no surface
*composes* them for the "your trip already started, and something
changed" case.

Nomad is that composition.  It takes:

  1. the **baseline** `TripReport` from Odyssey — the reference plan;
  2. a `NomadState` — current day index, current position, current
     situational mode (`at_stay` / `in_transit` / `at_stop`);
  3. **live** signals — the current incidents / geofences / POIs
     dictionary (these are whatever the caller has at `now`, so if
     new incidents landed since Odyssey ran, they're in this list);
  4. optional **candidate POIs** and **candidate stays** — the pool
     Nomad may substitute in when the shape of the trip has to change.

...and emits a `NomadReflow` with:

  * **Live day reports** — the *upcoming* days re-composed under current
    signals, with a per-day score delta vs the Odyssey baseline;
  * a **live trip score** — a blend of the days that already happened
    (frozen at their baseline score) and the days still to come (their
    live re-score), through the same `0.60·mean + 0.40·min` composite
    Odyssey uses;
  * a **projected shortfall** — `baseline_trip_score − live_trip_score`;
    when this is small everything is fine and the recommendation is
    `STAY_COURSE`;
  * **Reflow strategies** — up to 7 concrete recomposition candidates,
    each simulated end-to-end against the live signals and ranked by
    projected trip uplift:

    - `STAY_COURSE` — keep the original remaining plan (baseline)
    - `TIME_SHIFT` — probe depart_hour ±3 h on the worst upcoming day
    - `STOP_DROP`  — drop the weakest upcoming stop
    - `STOP_SUB`   — substitute the weakest stop with the safest
                     candidate from `candidate_pois`
    - `REST_DAY`   — turn the worst upcoming day into a stay-in-place
                     day (no stops, corridor risk goes to zero)
    - `SHORTEN`    — end the trip after the last day that still clears
                     the Solid gate under live signals
    - `STAY_MOVE`  — swap the stay for the worst day to the safest
                     candidate stay
  * a **best strategy** — the single highest-uplift candidate that
    materially improves the projected trip score;
  * a **signals digest** — which live signals actually triggered the
    reflow (which cluster escalated, how many new incidents on the
    corridor, which geofence widened);
  * a **verdict transition** — original verdict → live verdict →
    reflowed verdict, so the traveller reads the trip-band journey in
    one line;
  * an ordered **advisory strip** — the operational lines to act on
    now (open Companion for real-time, open Compass to substitute a
    stop, call the stay to shift check-in, ...).

Pure-stdlib.  Zero new deps.  Deterministic — same inputs → same output
bytes.  Round-trips through `to_dict / to_json / to_markdown` under the
`waysafe.nomad.v1` envelope.

Lives at `tabs[20]` — between Odyssey and the Report Hazard tools —
because reflow is what you open the moment you realise the trip you
committed at Odyssey isn't the trip you're actually on.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import date as date_cls, datetime, timedelta
from typing import Any, Iterable, List, Mapping, Optional, Sequence, Tuple

from utils import haversine_km
from safety import compute_safety, SafetyResult
from odyssey import (
    OdysseyDay, Stop, DayReport, LegReport, TripReport,
    STAY_WEIGHT, STOPS_WEIGHT, CORRIDOR_WEIGHT,
    CORRIDOR_KAPPA, LEG_SAMPLES,
    FATIGUE_FREE_STOPS, FATIGUE_STEP_PTS,
    MIN_DAY_WEIGHT, MEAN_DAY_WEIGHT,
    BAND_LADDER, FRAGILE_FLOOR, CRITICAL_FLOOR,
    SERENE_GATE, SOLID_GATE, BUMPY_GATE,
    _band_for, _compose_day, _verdict_for,
    _drift_index, _persistence_streak,
)


# ============================================================ constants ==

# Reflow is only triggered when the projected shortfall vs baseline
# exceeds this many points. Below the threshold, "STAY_COURSE" wins by
# definition — the trip is still on-plan and the traveller does not need
# a nudge. 5 pts is roughly one band step in `_band_for`.
SHORTFALL_TRIGGER_PTS = 5.0

# A strategy is only surfaced as "best" if it beats STAY_COURSE by at
# least this many trip points. Otherwise the recommendation stays at
# STAY_COURSE regardless of how many strategies were simulated.
STRATEGY_MIN_UPLIFT_PTS = 2.0

# Time-shift probe window (hours) around the day's baseline depart_hour.
# ±3 h matches Odyssey's `_swap_time_shift` and Tempo's sweep window.
TIME_SHIFT_WINDOW_HRS = 3

# When comparing baseline vs live day scores, a day is flagged as
# *degraded* if it lost this many points or more since the plan was
# committed. This is the "something moved on you" threshold.
DAY_DEGRADE_PTS = 4.0

# A stop swap (STOP_SUB) is only accepted if the candidate POI sits
# within this many km of the original stop. Beyond that the trip's
# geographic shape starts to distort and the swap feels arbitrary.
STOP_SUB_MAX_KM = 3.5

# A stay swap (STAY_MOVE) is only accepted if the candidate stay sits
# within this many km of the original stay. Same geography guardrail.
STAY_MOVE_MAX_KM = 4.0

# ---- Signal digest thresholds ---------------------------------------
# A live incident is counted as "on the corridor" of an upcoming day if
# it lies within this many km of any waypoint of any leg on that day.
CORRIDOR_INCIDENT_KM = 0.75

# ---- Version --------------------------------------------------------
VERSION = "waysafe.nomad.v1"
ENGINE_VERSION = "1.0.0"


# ============================================================== types ===

_MODES = ("at_stay", "in_transit", "at_stop", "at_start")


@dataclass(frozen=True)
class NomadState:
    """Where the traveller is *right now* in the middle of an Odyssey.

    - `current_day_idx` is 0-based; a fresh trip has `current_day_idx=0`
      + `mode="at_start"`.  A traveller stepping out of the stay on Day
      2 has `current_day_idx=1` + `mode="at_stay"`.
    - `current_lat / current_lon` — real-world GPS at the moment Nomad
      runs. If absent, we assume the traveller is at the current day's
      stay.
    - `mode` distinguishes stay/transit/stop for the advisory strip:
      "we can reflow tomorrow's stops but not today's if you're already
      in transit halfway to the first stop".
    - `elapsed_hours` — hours since the trip started; used only to
      pretty-print the header, not to alter physics.
    """
    current_day_idx: int
    mode: str = "at_stay"
    current_lat: Optional[float] = None
    current_lon: Optional[float] = None
    elapsed_hours: float = 0.0

    def __post_init__(self) -> None:
        if self.mode not in _MODES:
            # dataclass(frozen=True) blocks direct field write, so we
            # accept-through by leaving the value in place; a strict
            # caller can guard beforehand. Do NOT raise — a live
            # traveller feeding a typo shouldn't crash Nomad.
            pass


@dataclass
class LiveDayReport:
    """One upcoming day's *live* re-score plus the baseline delta."""
    day_index: int                    # index into the baseline TripReport.days
    day_label: str
    baseline_score: int
    baseline_band: str
    live_report: DayReport            # composed against live signals
    live_score: int
    live_band: str
    delta_score: float                # signed: live - baseline
    degrade_flag: bool                # True if delta_score <= -DAY_DEGRADE_PTS
    corridor_incidents_new: int       # # of live incidents within CORRIDOR_INCIDENT_KM
    reason: str                       # one-line diagnosis


@dataclass
class ReflowStrategy:
    """One reflow candidate.  Simulated end-to-end against live signals."""
    kind: str                         # STAY_COURSE / TIME_SHIFT / STOP_DROP / ...
    day_index: int                    # -1 for trip-wide strategies (SHORTEN)
    label: str                        # human-readable one-liner
    detail: str                       # 1-2 sentence explanation
    projected_trip_score: int
    projected_verdict: str
    uplift_pts: float                 # vs STAY_COURSE (== live_trip_score)
    total_risk_km: float
    total_distance_km: float
    total_stops_kept: int
    modified_days: Tuple[OdysseyDay, ...]  # the resulting remaining plan


@dataclass
class SignalsDigest:
    """What *changed* between the Odyssey baseline and current live signals."""
    total_live_incidents: int
    corridor_incidents_new: int       # sum across all upcoming days
    days_with_new_incidents: int
    degraded_days: int
    worst_day_index: Optional[int]
    worst_day_delta: float            # most-negative day delta
    trigger_summary: str              # one-line: "3 new incidents on the Day-3 corridor · ..."


@dataclass
class NomadReflow:
    """The full adaptive-reflow composition."""
    state: NomadState
    baseline_trip_score: int
    baseline_verdict: str
    live_days: Tuple[LiveDayReport, ...]
    live_trip_score: int
    live_verdict: str
    live_verdict_reason: str
    projected_shortfall: float        # baseline - live, positive means degraded
    reflow_triggered: bool            # True if projected_shortfall >= SHORTFALL_TRIGGER_PTS
    strategies: Tuple[ReflowStrategy, ...]  # ranked by uplift desc; includes STAY_COURSE
    best_strategy: ReflowStrategy     # the recommendation
    reflowed_trip_score: int          # best_strategy.projected_trip_score
    reflowed_verdict: str             # best_strategy.projected_verdict
    signals: SignalsDigest
    advisory: Tuple[str, ...]         # 3-6 ranked action lines
    now: datetime
    engine_version: str = ENGINE_VERSION


# ========================================================= composition ==

def _remaining_slice(trip: TripReport, state: NomadState) -> Tuple[int, int]:
    """Return (first_upcoming_idx, last_idx_exclusive) — the day range Nomad
    will re-score under live signals."""
    n = len(trip.days)
    if n == 0:
        return 0, 0
    idx = max(0, min(n - 1, int(state.current_day_idx)))
    # We always re-score the current day (it's still in progress) and
    # every day after it. Only days strictly before `idx` are "frozen"
    # at their baseline score.
    return idx, n


def _score_day(
    day: OdysseyDay,
    incidents: Sequence[Mapping],
    geofences: Mapping,
    pois: Sequence[Mapping],
) -> DayReport:
    """Thin wrapper around odyssey._compose_day so tests can stub it."""
    return _compose_day(day, list(incidents), geofences or {"features": []}, list(pois))


def _trip_composite(day_scores: Sequence[int]) -> int:
    """Odyssey's `0.6·mean + 0.4·min`, rounded and clamped 0..100."""
    if not day_scores:
        return 0
    m = sum(day_scores) / len(day_scores)
    lo = min(day_scores)
    raw = MEAN_DAY_WEIGHT * m + MIN_DAY_WEIGHT * lo
    return max(0, min(100, int(round(raw))))


def _corridor_incidents_on_day(
    day_report: DayReport,
    incidents: Sequence[Mapping],
) -> int:
    """Count live incidents within CORRIDOR_INCIDENT_KM of any leg
    waypoint on the day.  We use the leg samples the LiveDayReport
    already computed — no fresh haversine sweep of the whole incidents
    list, just of the samples we already touched."""
    count = 0
    seen_ids: set = set()
    for inc in incidents:
        try:
            ilat = float(inc.get("lat"))
            ilon = float(inc.get("lon"))
        except (TypeError, ValueError):
            continue
        # An incident is "on the corridor" if it's within threshold of
        # any leg waypoint. A single incident can only be counted once.
        iid = inc.get("id") or (ilat, ilon, inc.get("category"))
        if iid in seen_ids:
            continue
        for leg in day_report.legs:
            for lat, lon, _r in leg.samples:
                if haversine_km(lat, lon, ilat, ilon) <= CORRIDOR_INCIDENT_KM:
                    count += 1
                    seen_ids.add(iid)
                    break
            else:
                continue
            break
    return count


def _live_day_reason(base_score: int, live_score: int, new_incidents: int) -> str:
    """One-line diagnosis of the live delta."""
    delta = live_score - base_score
    if abs(delta) < 0.5 and new_incidents == 0:
        return f"unchanged · {live_score} (Δ {delta:+.0f})"
    parts: List[str] = []
    if delta <= -DAY_DEGRADE_PTS:
        parts.append(f"degraded {delta:+.0f} pts")
    elif delta >= DAY_DEGRADE_PTS:
        parts.append(f"improved {delta:+.0f} pts")
    else:
        parts.append(f"held at {live_score} (Δ {delta:+.0f})")
    if new_incidents:
        parts.append(f"{new_incidents} new incident{'s' if new_incidents != 1 else ''} on corridor")
    return " · ".join(parts)


def _live_report_for(
    trip: TripReport,
    state: NomadState,
    incidents: Sequence[Mapping],
    geofences: Mapping,
    pois: Sequence[Mapping],
) -> Tuple[List[LiveDayReport], List[int]]:
    """Re-score every upcoming day (including the current one) under
    live signals. Return the live day reports + the composite day-score
    vector used by the trip aggregate (baseline days for the past,
    live days for the current + future).
    """
    first, end = _remaining_slice(trip, state)
    live_reports: List[LiveDayReport] = []
    day_scores: List[int] = []
    for i, baseline_day in enumerate(trip.days):
        if i < first:
            # Frozen — day already happened.
            day_scores.append(baseline_day.day_score)
            continue
        live = _score_day(baseline_day.day, incidents, geofences, pois)
        new_inc = _corridor_incidents_on_day(live, incidents)
        delta = float(live.day_score - baseline_day.day_score)
        lr = LiveDayReport(
            day_index=i,
            day_label=baseline_day.day.label,
            baseline_score=baseline_day.day_score,
            baseline_band=baseline_day.day_band,
            live_report=live,
            live_score=live.day_score,
            live_band=live.day_band,
            delta_score=round(delta, 2),
            degrade_flag=delta <= -DAY_DEGRADE_PTS,
            corridor_incidents_new=new_inc,
            reason=_live_day_reason(baseline_day.day_score, live.day_score, new_inc),
        )
        live_reports.append(lr)
        day_scores.append(live.day_score)
    return live_reports, day_scores


# ========================================================== strategies ==

def _apply_time_shift(
    day: OdysseyDay,
    incidents: Sequence[Mapping],
    geofences: Mapping,
    pois: Sequence[Mapping],
) -> Tuple[Optional[OdysseyDay], float]:
    """Probe depart_hour ± TIME_SHIFT_WINDOW_HRS, keep the best variant.
    Returns (modified_day_or_None, uplift_pts_vs_original)."""
    base = _score_day(day, incidents, geofences, pois)
    best_score = base.day_score
    best_day: Optional[OdysseyDay] = None
    for dh in range(-TIME_SHIFT_WINDOW_HRS, TIME_SHIFT_WINDOW_HRS + 1):
        if dh == 0:
            continue
        new_depart = (day.depart_hour + dh) % 24
        if new_depart < 5 or new_depart > 21:
            continue        # keep the depart-hour in a plausible window
        variant = OdysseyDay(
            date=day.date, label=day.label,
            stay_lat=day.stay_lat, stay_lon=day.stay_lon,
            stay_label=day.stay_label,
            stops=day.stops, depart_hour=new_depart,
            transit_mode=day.transit_mode,
        )
        trial = _score_day(variant, incidents, geofences, pois)
        if trial.day_score > best_score:
            best_score = trial.day_score
            best_day = variant
    uplift = best_score - base.day_score if best_day is not None else 0.0
    return best_day, float(uplift)


def _apply_stop_drop(
    day: OdysseyDay,
    incidents: Sequence[Mapping],
    geofences: Mapping,
    pois: Sequence[Mapping],
) -> Tuple[Optional[OdysseyDay], float, str]:
    """Drop the weakest stop by re-scoring each single-stop-dropped variant.
    Returns (modified_day, uplift_pts, dropped_label). If day has ≤1 stop
    (dropping the only stop turns it into a rest day handled elsewhere)
    we return no candidate."""
    if len(day.stops) < 2:
        return None, 0.0, ""
    base = _score_day(day, incidents, geofences, pois)
    best_score = base.day_score
    best_day: Optional[OdysseyDay] = None
    dropped_label = ""
    for i in range(len(day.stops)):
        new_stops = tuple(s for j, s in enumerate(day.stops) if j != i)
        variant = OdysseyDay(
            date=day.date, label=day.label,
            stay_lat=day.stay_lat, stay_lon=day.stay_lon,
            stay_label=day.stay_label,
            stops=new_stops, depart_hour=day.depart_hour,
            transit_mode=day.transit_mode,
        )
        trial = _score_day(variant, incidents, geofences, pois)
        if trial.day_score > best_score:
            best_score = trial.day_score
            best_day = variant
            dropped_label = day.stops[i].label
    uplift = best_score - base.day_score if best_day is not None else 0.0
    return best_day, float(uplift), dropped_label


def _apply_stop_sub(
    day: OdysseyDay,
    incidents: Sequence[Mapping],
    geofences: Mapping,
    pois: Sequence[Mapping],
    candidates: Sequence[Stop],
) -> Tuple[Optional[OdysseyDay], float, str, str]:
    """Substitute the weakest stop with the safest nearby candidate.
    Returns (modified_day, uplift_pts, dropped_label, added_label)."""
    if not day.stops or not candidates:
        return None, 0.0, "", ""
    base = _score_day(day, incidents, geofences, pois)
    best_score = base.day_score
    best_day: Optional[OdysseyDay] = None
    dropped_label = ""
    added_label = ""
    for i, stop in enumerate(day.stops):
        for cand in candidates:
            if cand.label == stop.label:
                continue
            d = haversine_km(stop.lat, stop.lon, cand.lat, cand.lon)
            if d > STOP_SUB_MAX_KM:
                continue
            new_stops = list(day.stops)
            new_stops[i] = Stop(
                label=cand.label, lat=cand.lat, lon=cand.lon,
                dwell_min=cand.dwell_min or stop.dwell_min,
                arrival_hour=None,      # let it recompute from cursor
            )
            variant = OdysseyDay(
                date=day.date, label=day.label,
                stay_lat=day.stay_lat, stay_lon=day.stay_lon,
                stay_label=day.stay_label,
                stops=tuple(new_stops), depart_hour=day.depart_hour,
                transit_mode=day.transit_mode,
            )
            trial = _score_day(variant, incidents, geofences, pois)
            if trial.day_score > best_score:
                best_score = trial.day_score
                best_day = variant
                dropped_label = stop.label
                added_label = cand.label
    uplift = best_score - base.day_score if best_day is not None else 0.0
    return best_day, float(uplift), dropped_label, added_label


def _apply_rest_day(
    day: OdysseyDay,
    incidents: Sequence[Mapping],
    geofences: Mapping,
    pois: Sequence[Mapping],
) -> Tuple[OdysseyDay, float]:
    """Turn the day into a stay-in-place day.  Corridor risk goes to
    zero; the day score reduces to the stay score (evening window).
    Only worthwhile when the stay itself scores decently — otherwise
    a rest day just anchors you to a soft stay."""
    variant = OdysseyDay(
        date=day.date, label=day.label,
        stay_lat=day.stay_lat, stay_lon=day.stay_lon,
        stay_label=day.stay_label,
        stops=tuple(),
        depart_hour=day.depart_hour,
        transit_mode=day.transit_mode,
    )
    base = _score_day(day, incidents, geofences, pois)
    trial = _score_day(variant, incidents, geofences, pois)
    return variant, float(trial.day_score - base.day_score)


def _apply_stay_move(
    day: OdysseyDay,
    incidents: Sequence[Mapping],
    geofences: Mapping,
    pois: Sequence[Mapping],
    candidate_stays: Sequence[Mapping],
) -> Tuple[Optional[OdysseyDay], float, str]:
    """Swap the stay for the day with the safest nearby candidate stay.
    Returns (modified_day, uplift_pts, new_stay_label)."""
    if not candidate_stays:
        return None, 0.0, ""
    base = _score_day(day, incidents, geofences, pois)
    best_score = base.day_score
    best_day: Optional[OdysseyDay] = None
    added_label = ""
    for cand in candidate_stays:
        try:
            clat = float(cand.get("lat"))
            clon = float(cand.get("lon"))
            cname = str(cand.get("name") or cand.get("label") or "").strip()
        except (TypeError, ValueError):
            continue
        if not cname or cname == day.stay_label:
            continue
        d = haversine_km(day.stay_lat, day.stay_lon, clat, clon)
        if d > STAY_MOVE_MAX_KM:
            continue
        variant = OdysseyDay(
            date=day.date, label=day.label,
            stay_lat=clat, stay_lon=clon,
            stay_label=cname,
            stops=day.stops,
            depart_hour=day.depart_hour,
            transit_mode=day.transit_mode,
        )
        trial = _score_day(variant, incidents, geofences, pois)
        if trial.day_score > best_score:
            best_score = trial.day_score
            best_day = variant
            added_label = cname
    uplift = best_score - base.day_score if best_day is not None else 0.0
    return best_day, float(uplift), added_label


# ==================================================== strategy assembly ==

def _project_trip_score(
    baseline_days: Sequence[DayReport],
    live_days: Sequence[LiveDayReport],
    first_upcoming: int,
    substitutions: Mapping[int, OdysseyDay],
    incidents: Sequence[Mapping],
    geofences: Mapping,
    pois: Sequence[Mapping],
) -> Tuple[int, str, str, List[int], List[DayReport]]:
    """Compose the trip score assuming the past days stay frozen at
    their baseline score and every future day either uses its live
    re-score or the substitution's re-score.  Returns
    `(trip_score, verdict, verdict_reason, day_scores, day_reports)`."""
    day_scores: List[int] = []
    day_reports: List[DayReport] = []
    for i, base in enumerate(baseline_days):
        if i < first_upcoming:
            day_scores.append(base.day_score)
            day_reports.append(base)
            continue
        if i in substitutions:
            sub_report = _score_day(substitutions[i], incidents, geofences, pois)
            day_scores.append(sub_report.day_score)
            day_reports.append(sub_report)
        else:
            # Pick the live_days entry with matching day_index
            live_match = next(
                (ld for ld in live_days if ld.day_index == i), None
            )
            if live_match is None:
                day_scores.append(base.day_score)
                day_reports.append(base)
            else:
                day_scores.append(live_match.live_score)
                day_reports.append(live_match.live_report)
    if not day_scores:
        return 0, "empty", "no days", day_scores, day_reports
    mean_day = sum(day_scores) / len(day_scores)
    min_day = min(day_scores)
    drift = _drift_index(day_scores)
    streak = _persistence_streak(day_scores)
    verdict, reason = _verdict_for(mean_day, min_day, day_scores, drift, streak)
    return _trip_composite(day_scores), verdict, reason, day_scores, day_reports


def _worst_live_day(
    live_days: Sequence[LiveDayReport],
    prefer_degrade: bool = True,
) -> Optional[LiveDayReport]:
    """Pick the upcoming live day most in need of intervention.  Prefers
    degraded days (delta ≤ -DAY_DEGRADE_PTS) with the lowest live score;
    if none degraded, falls back to the lowest live score."""
    if not live_days:
        return None
    degraded = [ld for ld in live_days if ld.degrade_flag]
    pool = degraded if (prefer_degrade and degraded) else list(live_days)
    return min(pool, key=lambda ld: (ld.live_score, ld.day_index))


def _shorten_index(day_scores: Sequence[int]) -> int:
    """Return the smallest 1-based *keep* count such that keeping the
    first `k` days maximises the trip composite.  Only valid when the
    tail is dragging the composite down."""
    if not day_scores:
        return 0
    best_k = len(day_scores)
    best_score = _trip_composite(day_scores)
    for k in range(1, len(day_scores)):
        s = _trip_composite(day_scores[:k])
        if s > best_score:
            best_score = s
            best_k = k
    return best_k


def _label_for_kind(kind: str, day_label: str, note: str) -> str:
    """Human-readable one-liner per strategy."""
    if kind == "STAY_COURSE":
        return "Stay the course"
    if kind == "TIME_SHIFT":
        return f"Shift the depart hour on {day_label}"
    if kind == "STOP_DROP":
        return f"Drop {note} from {day_label}"
    if kind == "STOP_SUB":
        return f"Substitute a stop on {day_label} — {note}"
    if kind == "REST_DAY":
        return f"Rest day at the stay on {day_label}"
    if kind == "SHORTEN":
        return f"End the trip after {note}"
    if kind == "STAY_MOVE":
        return f"Move the stay on {day_label} to {note}"
    return f"{kind} on {day_label}"


def _compose_stay_course(
    trip: TripReport,
    state: NomadState,
    live_days: Sequence[LiveDayReport],
    day_scores: Sequence[int],
    incidents: Sequence[Mapping],
    geofences: Mapping,
    pois: Sequence[Mapping],
) -> ReflowStrategy:
    """The reference strategy — everyone else is measured against it."""
    live_score = _trip_composite(day_scores)
    mean_day = sum(day_scores) / len(day_scores) if day_scores else 0.0
    min_day = min(day_scores) if day_scores else 0
    drift = _drift_index(day_scores)
    streak = _persistence_streak(day_scores)
    verdict, _reason = _verdict_for(mean_day, min_day, day_scores, drift, streak)
    remaining = tuple(dr.day for dr in trip.days if dr.day_score is not None)
    upcoming = tuple(
        d.day for d in trip.days[state.current_day_idx:]
    ) if state.current_day_idx < len(trip.days) else tuple()
    total_dist = 0.0
    total_risk = 0.0
    total_stops_kept = 0
    for ld in live_days:
        total_dist += ld.live_report.total_distance_km
        total_risk += ld.live_report.total_risk_km
        total_stops_kept += ld.live_report.n_stops
    return ReflowStrategy(
        kind="STAY_COURSE",
        day_index=-1,
        label="Stay the course",
        detail=(
            "Keep the original remaining plan. This is the baseline every "
            "other strategy is measured against."
        ),
        projected_trip_score=live_score,
        projected_verdict=verdict,
        uplift_pts=0.0,
        total_risk_km=round(total_risk, 2),
        total_distance_km=round(total_dist, 2),
        total_stops_kept=total_stops_kept,
        modified_days=upcoming,
    )


def _compose_strategies(
    trip: TripReport,
    state: NomadState,
    live_days: Sequence[LiveDayReport],
    day_scores: Sequence[int],
    incidents: Sequence[Mapping],
    geofences: Mapping,
    pois: Sequence[Mapping],
    candidate_pois: Sequence[Stop],
    candidate_stays: Sequence[Mapping],
) -> List[ReflowStrategy]:
    """Enumerate every plausible reflow. Every strategy is simulated
    end-to-end against live signals and priced against STAY_COURSE."""
    first_upcoming = _remaining_slice(trip, state)[0]

    strategies: List[ReflowStrategy] = []
    stay_course = _compose_stay_course(trip, state, live_days, day_scores,
                                       incidents, geofences, pois)
    stay_course_score = stay_course.projected_trip_score
    strategies.append(stay_course)

    worst_live = _worst_live_day(live_days)
    if worst_live is None:
        return strategies

    worst_baseline_day = trip.days[worst_live.day_index].day
    day_label = worst_live.day_label

    # TIME_SHIFT --------------------------------------------------------
    ts_day, ts_up = _apply_time_shift(worst_baseline_day, incidents, geofences, pois)
    if ts_day is not None and ts_up > 0:
        proj, verd, _reason, _ds, _drs = _project_trip_score(
            trip.days, live_days, first_upcoming,
            {worst_live.day_index: ts_day}, incidents, geofences, pois,
        )
        strategies.append(ReflowStrategy(
            kind="TIME_SHIFT",
            day_index=worst_live.day_index,
            label=_label_for_kind("TIME_SHIFT", day_label,
                                  f"{worst_baseline_day.depart_hour:02d}:00 → "
                                  f"{ts_day.depart_hour:02d}:00"),
            detail=(
                f"Move the depart hour on {day_label} from "
                f"{worst_baseline_day.depart_hour:02d}:00 to "
                f"{ts_day.depart_hour:02d}:00. The day re-scores "
                f"+{ts_up:.0f} pts under live signals — arrival hours "
                f"shift out of the late-night penalty band."
            ),
            projected_trip_score=proj,
            projected_verdict=verd,
            uplift_pts=float(proj - stay_course_score),
            total_risk_km=round(sum(dr.total_risk_km for dr in _drs[first_upcoming:]), 2),
            total_distance_km=round(sum(dr.total_distance_km for dr in _drs[first_upcoming:]), 2),
            total_stops_kept=sum(dr.n_stops for dr in _drs[first_upcoming:]),
            modified_days=tuple(dr.day for dr in _drs[first_upcoming:]),
        ))

    # STOP_DROP ---------------------------------------------------------
    sd_day, sd_up, dropped_label = _apply_stop_drop(worst_baseline_day,
                                                    incidents, geofences, pois)
    if sd_day is not None and sd_up > 0:
        proj, verd, _reason, _ds, _drs = _project_trip_score(
            trip.days, live_days, first_upcoming,
            {worst_live.day_index: sd_day}, incidents, geofences, pois,
        )
        strategies.append(ReflowStrategy(
            kind="STOP_DROP",
            day_index=worst_live.day_index,
            label=_label_for_kind("STOP_DROP", day_label, dropped_label),
            detail=(
                f"Drop '{dropped_label}' from {day_label}. The day "
                f"re-scores +{sd_up:.0f} pts — the corridor loses its "
                f"riskiest leg and the fatigue penalty falls."
            ),
            projected_trip_score=proj,
            projected_verdict=verd,
            uplift_pts=float(proj - stay_course_score),
            total_risk_km=round(sum(dr.total_risk_km for dr in _drs[first_upcoming:]), 2),
            total_distance_km=round(sum(dr.total_distance_km for dr in _drs[first_upcoming:]), 2),
            total_stops_kept=sum(dr.n_stops for dr in _drs[first_upcoming:]),
            modified_days=tuple(dr.day for dr in _drs[first_upcoming:]),
        ))

    # STOP_SUB ----------------------------------------------------------
    if candidate_pois:
        ss_day, ss_up, ss_dropped, ss_added = _apply_stop_sub(
            worst_baseline_day, incidents, geofences, pois, candidate_pois,
        )
        if ss_day is not None and ss_up > 0:
            proj, verd, _reason, _ds, _drs = _project_trip_score(
                trip.days, live_days, first_upcoming,
                {worst_live.day_index: ss_day}, incidents, geofences, pois,
            )
            strategies.append(ReflowStrategy(
                kind="STOP_SUB",
                day_index=worst_live.day_index,
                label=_label_for_kind("STOP_SUB", day_label,
                                      f"'{ss_dropped}' → '{ss_added}'"),
                detail=(
                    f"Substitute '{ss_dropped}' with '{ss_added}' on "
                    f"{day_label}. The day re-scores +{ss_up:.0f} pts — "
                    f"the new stop sits in a calmer corridor and the "
                    f"trip shape is preserved."
                ),
                projected_trip_score=proj,
                projected_verdict=verd,
                uplift_pts=float(proj - stay_course_score),
                total_risk_km=round(sum(dr.total_risk_km for dr in _drs[first_upcoming:]), 2),
                total_distance_km=round(sum(dr.total_distance_km for dr in _drs[first_upcoming:]), 2),
                total_stops_kept=sum(dr.n_stops for dr in _drs[first_upcoming:]),
                modified_days=tuple(dr.day for dr in _drs[first_upcoming:]),
            ))

    # REST_DAY ----------------------------------------------------------
    if worst_baseline_day.stops:
        rd_day, rd_up = _apply_rest_day(worst_baseline_day, incidents, geofences, pois)
        # A rest day is only surfaced if the stay itself is decent — else
        # you're anchoring to a soft point.
        base_report = _score_day(worst_baseline_day, incidents, geofences, pois)
        if rd_up > 0 and base_report.stay_score >= 55:
            proj, verd, _reason, _ds, _drs = _project_trip_score(
                trip.days, live_days, first_upcoming,
                {worst_live.day_index: rd_day}, incidents, geofences, pois,
            )
            strategies.append(ReflowStrategy(
                kind="REST_DAY",
                day_index=worst_live.day_index,
                label=_label_for_kind("REST_DAY", day_label, ""),
                detail=(
                    f"Convert {day_label} into a rest day at "
                    f"'{worst_baseline_day.stay_label}'. The corridor "
                    f"risk goes to zero and the day scores at the stay's "
                    f"evening window ({base_report.stay_score}). Uplift: "
                    f"+{rd_up:.0f} pts."
                ),
                projected_trip_score=proj,
                projected_verdict=verd,
                uplift_pts=float(proj - stay_course_score),
                total_risk_km=round(sum(dr.total_risk_km for dr in _drs[first_upcoming:]), 2),
                total_distance_km=round(sum(dr.total_distance_km for dr in _drs[first_upcoming:]), 2),
                total_stops_kept=sum(dr.n_stops for dr in _drs[first_upcoming:]),
                modified_days=tuple(dr.day for dr in _drs[first_upcoming:]),
            ))

    # SHORTEN -----------------------------------------------------------
    # Compute the ideal keep-count under live signals and see if
    # trimming the tail lifts the composite.
    keep_k = _shorten_index(day_scores)
    if 1 <= keep_k < len(day_scores) and keep_k >= first_upcoming + 1:
        kept_labels = trip.days[keep_k - 1].day.label
        shortened_scores = day_scores[:keep_k]
        proj = _trip_composite(shortened_scores)
        mean_day = sum(shortened_scores) / len(shortened_scores)
        min_day = min(shortened_scores)
        drift = _drift_index(shortened_scores)
        streak = _persistence_streak(shortened_scores)
        verd, _r = _verdict_for(mean_day, min_day, shortened_scores, drift, streak)
        uplift = proj - stay_course_score
        if uplift > 0:
            strategies.append(ReflowStrategy(
                kind="SHORTEN",
                day_index=-1,
                label=_label_for_kind("SHORTEN", "", kept_labels),
                detail=(
                    f"End the trip after {kept_labels} ({keep_k} days "
                    f"kept out of {len(day_scores)}). Trip composite "
                    f"rises to {proj} — the tail is dragging the "
                    f"weighted mean down."
                ),
                projected_trip_score=proj,
                projected_verdict=verd,
                uplift_pts=float(uplift),
                total_risk_km=round(
                    sum(ld.live_report.total_risk_km for ld in live_days
                        if ld.day_index < keep_k), 2),
                total_distance_km=round(
                    sum(ld.live_report.total_distance_km for ld in live_days
                        if ld.day_index < keep_k), 2),
                total_stops_kept=sum(
                    ld.live_report.n_stops for ld in live_days
                    if ld.day_index < keep_k),
                modified_days=tuple(
                    ld.live_report.day for ld in live_days
                    if ld.day_index < keep_k
                ),
            ))

    # STAY_MOVE ---------------------------------------------------------
    if candidate_stays:
        sm_day, sm_up, sm_added = _apply_stay_move(
            worst_baseline_day, incidents, geofences, pois, candidate_stays,
        )
        if sm_day is not None and sm_up > 0:
            proj, verd, _reason, _ds, _drs = _project_trip_score(
                trip.days, live_days, first_upcoming,
                {worst_live.day_index: sm_day}, incidents, geofences, pois,
            )
            strategies.append(ReflowStrategy(
                kind="STAY_MOVE",
                day_index=worst_live.day_index,
                label=_label_for_kind("STAY_MOVE", day_label, sm_added),
                detail=(
                    f"Move the stay on {day_label} from "
                    f"'{worst_baseline_day.stay_label}' to '{sm_added}'. "
                    f"The day re-scores +{sm_up:.0f} pts under live signals."
                ),
                projected_trip_score=proj,
                projected_verdict=verd,
                uplift_pts=float(proj - stay_course_score),
                total_risk_km=round(sum(dr.total_risk_km for dr in _drs[first_upcoming:]), 2),
                total_distance_km=round(sum(dr.total_distance_km for dr in _drs[first_upcoming:]), 2),
                total_stops_kept=sum(dr.n_stops for dr in _drs[first_upcoming:]),
                modified_days=tuple(dr.day for dr in _drs[first_upcoming:]),
            ))

    return strategies


# ==================================================== signals digest ====

def _compose_signals_digest(
    trip: TripReport,
    live_days: Sequence[LiveDayReport],
    all_incidents: Sequence[Mapping],
) -> SignalsDigest:
    """Summarise what moved between baseline and live."""
    degraded = [ld for ld in live_days if ld.degrade_flag]
    total_new = sum(ld.corridor_incidents_new for ld in live_days)
    days_hit = sum(1 for ld in live_days if ld.corridor_incidents_new > 0)
    worst = min(live_days, key=lambda ld: ld.delta_score) if live_days else None
    if worst is None or worst.delta_score >= 0:
        summary = "Signals steady — no upcoming day lost ground since the plan was committed."
        worst_idx = None
        worst_delta = 0.0
    else:
        segs: List[str] = []
        if total_new > 0:
            segs.append(f"{total_new} incident{'s' if total_new != 1 else ''} on upcoming corridors")
        if degraded:
            segs.append(f"{len(degraded)} day{'s' if len(degraded) != 1 else ''} lost ≥{DAY_DEGRADE_PTS:.0f} pts")
        segs.append(f"worst: {worst.day_label} ({worst.delta_score:+.0f} pts)")
        summary = " · ".join(segs)
        worst_idx = worst.day_index
        worst_delta = worst.delta_score
    return SignalsDigest(
        total_live_incidents=len(list(all_incidents)),
        corridor_incidents_new=total_new,
        days_with_new_incidents=days_hit,
        degraded_days=len(degraded),
        worst_day_index=worst_idx,
        worst_day_delta=round(worst_delta, 2),
        trigger_summary=summary,
    )


# ==================================================== advisory strip ====

def _mode_line(state: NomadState) -> str:
    """The first advisory line depends on where the traveller physically is."""
    if state.mode == "in_transit":
        return (
            "You're in transit — Nomad can reflow the *rest* of today "
            "and every day after, but not the leg you're currently on. "
            "For the current leg, open Companion."
        )
    if state.mode == "at_stop":
        return (
            "You're at a stop — safe moment to review the reflow. Apply "
            "the top strategy before your next depart."
        )
    if state.mode == "at_stay":
        return (
            "You're at the stay — a good pre-departure checkpoint. Apply "
            "the top strategy before the morning depart."
        )
    return (
        "Trip hasn't started — a pre-flight reflow lets you catch signal "
        "shifts before you commit the first depart."
    )


def _compose_advisory(
    state: NomadState,
    live_days: Sequence[LiveDayReport],
    strategies: Sequence[ReflowStrategy],
    best: ReflowStrategy,
    signals: SignalsDigest,
    reflow_triggered: bool,
) -> Tuple[str, ...]:
    """Compose an ordered advisory strip.  First-match-wins on the top line."""
    lines: List[str] = [_mode_line(state)]

    if reflow_triggered:
        lines.append(
            f"Reflow triggered — projected shortfall vs baseline is "
            f"{signals.trigger_summary}."
        )
    else:
        lines.append(
            "Reflow not triggered — live signals hold the trip within "
            f"{SHORTFALL_TRIGGER_PTS:.0f} pts of the Odyssey baseline."
        )

    if best.kind != "STAY_COURSE":
        lines.append(
            f"Recommendation: {best.label} — projected trip score rises to "
            f"{best.projected_trip_score} ({best.projected_verdict}), "
            f"a +{best.uplift_pts:.0f} pt uplift over STAY_COURSE."
        )
    else:
        lines.append(
            "Recommendation: stay the course. No strategy beat the baseline "
            f"by more than {STRATEGY_MIN_UPLIFT_PTS:.0f} pts."
        )

    if signals.corridor_incidents_new:
        lines.append(
            f"Signals: {signals.corridor_incidents_new} live incidents landed "
            f"on {signals.days_with_new_incidents} upcoming corridor"
            f"{'s' if signals.days_with_new_incidents != 1 else ''} — cross-check Sentinel."
        )

    if signals.degraded_days >= 2:
        lines.append(
            f"{signals.degraded_days} upcoming days lost ≥{DAY_DEGRADE_PTS:.0f} pts — "
            f"if the recommendation is REST_DAY or SHORTEN, consider whether "
            f"the trip shape itself needs to change."
        )

    if best.kind == "STOP_SUB":
        lines.append(
            "STOP_SUB keeps the trip shape intact — the geographic footprint "
            "of the trip is unchanged, only one stop shifted."
        )
    elif best.kind == "SHORTEN":
        lines.append(
            "SHORTEN cuts the tail — communicate the early return to the "
            "stay, trusted contacts, and your travel insurance provider."
        )
    elif best.kind == "REST_DAY":
        lines.append(
            "REST_DAY holds you at the stay — Refuge tab confirms nearest "
            "help POIs; Advisory tab prints a shareable brief."
        )

    return tuple(lines[:6])


# ==================================================== entry point =======

def compose_nomad_reflow(
    *,
    trip: TripReport,
    state: NomadState,
    incidents: Iterable[Mapping] | None,
    geofences: Mapping,
    pois: Iterable[Mapping] | None,
    candidate_pois: Sequence[Stop] = (),
    candidate_stays: Sequence[Mapping] = (),
    now: Optional[datetime] = None,
) -> NomadReflow:
    """Single entrypoint.  Compose the adaptive reflow.

    Deterministic — same input bytes → same output bytes.

    Empty-trip guardrail: a zero-day baseline returns a trivial reflow
    with `STAY_COURSE` as the only strategy so the UI never crashes."""
    inc = list(incidents or [])
    poi = list(pois or [])
    geo = geofences or {"features": []}
    now = now or datetime.utcnow()

    if not trip.days:
        empty_strategy = ReflowStrategy(
            kind="STAY_COURSE", day_index=-1,
            label="No trip to reflow",
            detail="Compose an Odyssey trip first — Nomad reflows an existing plan.",
            projected_trip_score=0, projected_verdict="empty",
            uplift_pts=0.0, total_risk_km=0.0, total_distance_km=0.0,
            total_stops_kept=0, modified_days=tuple(),
        )
        return NomadReflow(
            state=state,
            baseline_trip_score=0, baseline_verdict="empty",
            live_days=tuple(),
            live_trip_score=0, live_verdict="empty", live_verdict_reason="no days",
            projected_shortfall=0.0,
            reflow_triggered=False,
            strategies=(empty_strategy,),
            best_strategy=empty_strategy,
            reflowed_trip_score=0, reflowed_verdict="empty",
            signals=SignalsDigest(0, 0, 0, 0, None, 0.0, "empty trip"),
            advisory=("Nomad has nothing to reflow — build an Odyssey trip first.",),
            now=now,
        )

    live_days, day_scores = _live_report_for(trip, state, inc, geo, poi)
    live_score = _trip_composite(day_scores)
    mean_day = sum(day_scores) / len(day_scores) if day_scores else 0.0
    min_day = min(day_scores) if day_scores else 0
    drift = _drift_index(day_scores)
    streak = _persistence_streak(day_scores)
    live_verdict, live_verdict_reason = _verdict_for(
        mean_day, min_day, day_scores, drift, streak,
    )
    shortfall = float(trip.trip_score - live_score)
    reflow_triggered = shortfall >= SHORTFALL_TRIGGER_PTS

    strategies = _compose_strategies(
        trip, state, live_days, day_scores,
        inc, geo, poi, candidate_pois, candidate_stays,
    )
    # Rank by uplift desc, but STAY_COURSE always occupies rank #0 when
    # nothing else clears STRATEGY_MIN_UPLIFT_PTS. Otherwise the winner
    # is the highest-uplift strategy.
    strategies_sorted = sorted(
        strategies,
        key=lambda s: (-s.uplift_pts, s.kind == "STAY_COURSE"),
    )
    best: ReflowStrategy = strategies_sorted[0]
    if best.kind == "STAY_COURSE" or best.uplift_pts < STRATEGY_MIN_UPLIFT_PTS:
        # Fall back to STAY_COURSE if nothing beats it meaningfully.
        stay_course = next(s for s in strategies if s.kind == "STAY_COURSE")
        best = stay_course

    signals = _compose_signals_digest(trip, live_days, inc)
    advisory = _compose_advisory(state, live_days, strategies_sorted, best,
                                 signals, reflow_triggered)

    return NomadReflow(
        state=state,
        baseline_trip_score=trip.trip_score,
        baseline_verdict=trip.verdict,
        live_days=tuple(live_days),
        live_trip_score=live_score,
        live_verdict=live_verdict,
        live_verdict_reason=live_verdict_reason,
        projected_shortfall=round(shortfall, 2),
        reflow_triggered=reflow_triggered,
        strategies=tuple(strategies_sorted),
        best_strategy=best,
        reflowed_trip_score=best.projected_trip_score,
        reflowed_verdict=best.projected_verdict,
        signals=signals,
        advisory=advisory,
        now=now,
    )


# ================================================================= i/o ==

def _safety_result_to_dict(sr: SafetyResult) -> dict:
    return {
        "score": sr.score,
        "band": sr.band,
        "factors": list(sr.factors),
        "nearest_help_km": sr.nearest_help_km,
        "incidents_nearby": sr.incidents_nearby,
    }


def _live_day_to_dict(ld: LiveDayReport) -> dict:
    return {
        "day_index": ld.day_index,
        "day_label": ld.day_label,
        "baseline": {"score": ld.baseline_score, "band": ld.baseline_band},
        "live": {"score": ld.live_score, "band": ld.live_band},
        "delta_score": ld.delta_score,
        "degrade_flag": ld.degrade_flag,
        "corridor_incidents_new": ld.corridor_incidents_new,
        "reason": ld.reason,
        "live_totals": {
            "distance_km": ld.live_report.total_distance_km,
            "risk_km": ld.live_report.total_risk_km,
            "eta_min": ld.live_report.total_eta_min,
            "corridor_score": ld.live_report.corridor_score,
            "n_stops": ld.live_report.n_stops,
        },
    }


def _strategy_to_dict(s: ReflowStrategy) -> dict:
    return {
        "kind": s.kind,
        "day_index": s.day_index,
        "label": s.label,
        "detail": s.detail,
        "projected_trip_score": s.projected_trip_score,
        "projected_verdict": s.projected_verdict,
        "uplift_pts": round(s.uplift_pts, 2),
        "total_risk_km": s.total_risk_km,
        "total_distance_km": s.total_distance_km,
        "total_stops_kept": s.total_stops_kept,
        "modified_days": [
            {
                "date": d.date, "label": d.label,
                "stay_label": d.stay_label,
                "depart_hour": d.depart_hour,
                "transit_mode": d.transit_mode,
                "n_stops": len(d.stops),
                "stops": [
                    {"label": stop.label, "lat": stop.lat, "lon": stop.lon,
                     "dwell_min": stop.dwell_min}
                    for stop in d.stops
                ],
            }
            for d in s.modified_days
        ],
    }


def _signals_to_dict(sig: SignalsDigest) -> dict:
    return {
        "total_live_incidents": sig.total_live_incidents,
        "corridor_incidents_new": sig.corridor_incidents_new,
        "days_with_new_incidents": sig.days_with_new_incidents,
        "degraded_days": sig.degraded_days,
        "worst_day_index": sig.worst_day_index,
        "worst_day_delta": sig.worst_day_delta,
        "trigger_summary": sig.trigger_summary,
    }


def to_dict(reflow: NomadReflow) -> dict:
    """Full JSON-serialisable view under the `waysafe.nomad.v1` envelope."""
    return {
        "envelope": VERSION,
        "engine_version": reflow.engine_version,
        "now": reflow.now.isoformat(),
        "state": {
            "current_day_idx": reflow.state.current_day_idx,
            "mode": reflow.state.mode,
            "current_lat": reflow.state.current_lat,
            "current_lon": reflow.state.current_lon,
            "elapsed_hours": reflow.state.elapsed_hours,
        },
        "baseline": {
            "trip_score": reflow.baseline_trip_score,
            "verdict": reflow.baseline_verdict,
        },
        "live": {
            "trip_score": reflow.live_trip_score,
            "verdict": reflow.live_verdict,
            "verdict_reason": reflow.live_verdict_reason,
            "days": [_live_day_to_dict(ld) for ld in reflow.live_days],
        },
        "projected_shortfall": reflow.projected_shortfall,
        "reflow_triggered": reflow.reflow_triggered,
        "signals": _signals_to_dict(reflow.signals),
        "strategies": [_strategy_to_dict(s) for s in reflow.strategies],
        "best_strategy": _strategy_to_dict(reflow.best_strategy),
        "reflowed": {
            "trip_score": reflow.reflowed_trip_score,
            "verdict": reflow.reflowed_verdict,
        },
        "advisory": list(reflow.advisory),
        "rules": {
            "shortfall_trigger_pts": SHORTFALL_TRIGGER_PTS,
            "strategy_min_uplift_pts": STRATEGY_MIN_UPLIFT_PTS,
            "time_shift_window_hrs": TIME_SHIFT_WINDOW_HRS,
            "day_degrade_pts": DAY_DEGRADE_PTS,
            "stop_sub_max_km": STOP_SUB_MAX_KM,
            "stay_move_max_km": STAY_MOVE_MAX_KM,
            "corridor_incident_km": CORRIDOR_INCIDENT_KM,
            "trip_composite": {
                "mean_day_weight": MEAN_DAY_WEIGHT,
                "min_day_weight": MIN_DAY_WEIGHT,
            },
        },
    }


def to_json(reflow: NomadReflow, *, indent: int = 2) -> str:
    return json.dumps(to_dict(reflow), indent=indent, sort_keys=False)


def to_markdown(reflow: NomadReflow) -> str:
    """One-page markdown digest — pastes cleanly into a family chat / group note."""
    lines: List[str] = []
    lines.append(f"# Nomad — adaptive trip reflow ({reflow.now.strftime('%Y-%m-%d %H:%M')})")
    lines.append("")
    lines.append(
        f"**Baseline** → `{reflow.baseline_trip_score}` ({reflow.baseline_verdict}) · "
        f"**Live** → `{reflow.live_trip_score}` ({reflow.live_verdict}) · "
        f"**Reflowed** → `{reflow.reflowed_trip_score}` ({reflow.reflowed_verdict})"
    )
    lines.append("")
    lines.append(f"> {reflow.live_verdict_reason}")
    lines.append("")

    lines.append("## Recommendation")
    lines.append("")
    b = reflow.best_strategy
    lines.append(f"**{b.label}** · projected trip score `{b.projected_trip_score}` "
                 f"({b.projected_verdict}) · uplift `+{b.uplift_pts:.1f}` pts")
    lines.append("")
    lines.append(f"> {b.detail}")
    lines.append("")

    lines.append("## Upcoming days — live re-score")
    lines.append("")
    if reflow.live_days:
        lines.append("| # | Day | Baseline | Live | Δ | New incidents | Reason |")
        lines.append("|---:|---|---:|---:|---:|---:|---|")
        for ld in reflow.live_days:
            lines.append(
                f"| {ld.day_index+1} | {ld.day_label} | "
                f"{ld.baseline_score} ({ld.baseline_band}) | "
                f"{ld.live_score} ({ld.live_band}) | "
                f"{ld.delta_score:+.0f} | {ld.corridor_incidents_new} | "
                f"{ld.reason} |"
            )
    else:
        lines.append("_No upcoming days to re-score._")
    lines.append("")

    lines.append("## Ranked strategies")
    lines.append("")
    for i, s in enumerate(reflow.strategies, 1):
        lines.append(f"{i}. **{s.label}** · `{s.projected_trip_score}` "
                     f"({s.projected_verdict}) · uplift `{s.uplift_pts:+.1f}` pts")
        lines.append(f"   > {s.detail}")
    lines.append("")

    lines.append("## Signals")
    lines.append("")
    sig = reflow.signals
    lines.append(f"- Live incidents in the pool: **{sig.total_live_incidents}**")
    lines.append(f"- On upcoming corridors: **{sig.corridor_incidents_new}** "
                 f"across **{sig.days_with_new_incidents}** days")
    lines.append(f"- Degraded days (≥ {DAY_DEGRADE_PTS:.0f} pts loss): "
                 f"**{sig.degraded_days}**")
    lines.append(f"- Trigger: {sig.trigger_summary}")
    lines.append("")

    lines.append("## Advisory")
    lines.append("")
    for a in reflow.advisory:
        lines.append(f"- {a}")
    lines.append("")

    lines.append("## Rules")
    lines.append("")
    lines.append(f"- Reflow trigger: shortfall ≥ **{SHORTFALL_TRIGGER_PTS:.0f}** pts")
    lines.append(f"- Strategy min uplift: **{STRATEGY_MIN_UPLIFT_PTS:.0f}** pts vs STAY_COURSE")
    lines.append(f"- Time-shift window: ± **{TIME_SHIFT_WINDOW_HRS}** hours")
    lines.append(f"- Day-degrade threshold: **{DAY_DEGRADE_PTS:.0f}** pts")
    lines.append(f"- Stop-sub max radius: **{STOP_SUB_MAX_KM:.1f}** km")
    lines.append(f"- Stay-move max radius: **{STAY_MOVE_MAX_KM:.1f}** km")
    lines.append(f"- Corridor incident radius: **{CORRIDOR_INCIDENT_KM:.2f}** km")
    lines.append(f"- Engine `{ENGINE_VERSION}` · envelope `{VERSION}`")
    return "\n".join(lines) + "\n"


# ==================================================== seed helpers =====

def default_state_from_trip(
    trip: TripReport,
    day_index: int = 0,
    mode: str = "at_stay",
) -> NomadState:
    """Return a sensible NomadState given an existing TripReport.  Used
    by the UI to seed the Nomad tab so it isn't empty on first open."""
    di = max(0, min(len(trip.days) - 1 if trip.days else 0, int(day_index)))
    if trip.days and 0 <= di < len(trip.days):
        base = trip.days[di].day
        return NomadState(
            current_day_idx=di,
            mode=mode if mode in _MODES else "at_stay",
            current_lat=base.stay_lat,
            current_lon=base.stay_lon,
            elapsed_hours=24.0 * di,
        )
    return NomadState(current_day_idx=0, mode="at_start", elapsed_hours=0.0)


def candidate_pois_from_pois(
    pois: Sequence[Mapping],
    center_lat: float,
    center_lon: float,
    max_km: float = STOP_SUB_MAX_KM * 2,
    limit: int = 12,
) -> Tuple[Stop, ...]:
    """Rank POIs near a centre point for use as `candidate_pois` in
    STOP_SUB.  Filters to POIs within `max_km` and returns the closest
    `limit`."""
    ranked: List[Tuple[float, str, float, float]] = []
    for r in pois:
        try:
            lat = float(r.get("lat")); lon = float(r.get("lon"))
            name = str(r.get("name") or "").strip()
        except (TypeError, ValueError):
            continue
        if not name:
            continue
        d = haversine_km(center_lat, center_lon, lat, lon)
        if d > max_km:
            continue
        ranked.append((d, name, lat, lon))
    ranked.sort()
    return tuple(
        Stop(label=n, lat=lat, lon=lon, dwell_min=60)
        for _, n, lat, lon in ranked[:limit]
    )
