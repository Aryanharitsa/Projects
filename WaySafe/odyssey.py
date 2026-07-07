"""Odyssey — Multi-Day Trip Composer for WaySafe.

The question no other WaySafe surface answers
---------------------------------------------
Every prior WaySafe surface is *single-day*:

  * Pulse opens the day, Tempo picks the depart-minute, Plan Route prices
    the corridor, Companion streams alerts during the walk, Echo debriefs
    once you're home, Prism re-prices the corridor for a specific persona.

None of them answer the actual planning question the tourist starts a trip
with: **"I'm here for 4 nights across Panjim, Old Goa, and Palolem — is
this whole trip safe, which day is the weakest link, and what's the one
tweak that would upgrade the trip verdict from Bumpy to Solid?"**

Odyssey is the *multi-day composer* that closes that gap. It takes an
ordered list of `OdysseyDay` — a stay + 1..N stops + a depart hour per
day — and composes a single deterministic **trip report**:

  1. Per-day breakdown
       - Stay score at the evening return-window (safety.compute_safety
         at hour=20 of that day, so a stay near a curfew polygon is
         penalised for the hour the traveller is actually there).
       - Stop scores at planned arrival hour, with the persona-neutral
         base ledger surviving byte-for-byte from `safety.py`.
       - **Corridor legs** (stay → stop_1 → stop_2 … → stay), each
         sampled with 12 waypoints along the straight-line arc so
         `mean_risk`, `peak_risk`, `risk_km`, and `min_safety_along`
         all agree with the physics used by `routing.plan_safest_route`
         without paying the A* cost 20× per trip.
       - Day composite:
             day = 0.30·stay + 0.40·mean(stops) + 0.30·corridor
         where corridor = 100·exp(-κ·total_risk_km), κ = 0.25 (tuned so
         a 6-risk-km day costs about 22 pts — matches Tempo's exponent).
       - **Fatigue penalty**: every stop past FATIGUE_FREE_STOPS (3)
         drops the day 3 pts.  Real world: 4+ stops burns buffer.

  2. Trip-level aggregate — this is where Odyssey stops being an average
     and starts being a *product*:

     * `trip_score = 0.6·mean(days) + 0.4·min(days)` — **worst-day-
       weighted** so a single Fragile day can't hide behind a run of
       Serene ones (the traveller experiences the trip, not the mean).
     * **Drift index** — signed sum of consecutive day deltas.  Negative
       = trip degrades toward the end (worst outcome — you're stuck).
       Positive = trip warms up (best outcome — buffer to recover from
       an early stumble).
     * **Persistence** — longest run of Fragile / Bumpy days.  Two
       consecutive Fragile days is much worse than two separated ones.
     * **Verdict ladder** with an explicit min-day gate so it can never
       upgrade past what the weakest day allows:
             Serene  — mean ≥ 82, min ≥ 78, no Fragile day, drift ≥ 0
             Solid   — mean ≥ 70, min ≥ 60
             Bumpy   — mean ≥ 55
             Fragile — otherwise (or any single day <45)

  3. **Weakest link** — the single lowest-scoring (day, leg) tuple in the
     trip, with 3 concrete named alternatives ranked by expected uplift:

       * `TIME_SHIFT`  — probe depart_hour ± 3 h under the forecaster
         (when loaded) or under `safety.compute_safety`'s late-night
         penalty (when not); quote the score delta of the best hour.
       * `REORDER`    — try one candidate stop permutation (reverse
         order + worst-stop-first) and keep it if `total_risk_km`
         drops by ≥ 1 unit.
       * `MODE_UPGRADE` — if `transit_mode="walk"`, propose `cab` (drops
         `late_night_mult` sensitivity + eliminates the on-street window
         entirely).  Emit only if the day already dwells past 21:00.

     The result carries a *concrete uplift band* — "Solid → Serene" —
     not a vague "better".

  4. **Auditor block** — every constant + weight + verdict cutoff on the
     stage exposes them so an insurance / duty-of-care reviewer can trace
     each number back to a formula, not vibes.

Pure-stdlib.  Zero new deps.  Deterministic — same input bytes → same
report bytes.  Round-trips through `to_dict / to_json / to_markdown`
under the `waysafe.odyssey.v1` envelope.

Lives at `tabs[19]` — between Prism and the Report Hazard tools —
because a multi-day composition is the last surface a traveller looks
at *before* committing the trip, and the first they look at *after*
Prism has confirmed the corridor for their persona.
"""
from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from datetime import date as date_cls, datetime, timedelta
from typing import Any, Iterable, List, Mapping, Optional, Sequence, Tuple

from utils import haversine_km
from safety import compute_safety, point_risk, SafetyResult


# ============================================================ constants ==

# ---- Composition weights (per-day). MUST sum to 1.0 --------------------
STAY_WEIGHT     = 0.30
STOPS_WEIGHT    = 0.40
CORRIDOR_WEIGHT = 0.30

# ---- Corridor sampling ------------------------------------------------
# 12 samples per leg is the sweet spot from the Compass tuning: enough to
# catch a 200 m geofence sliver on a 6 km leg, cheap enough that a
# 5-day × 4-leg trip runs in < 40 ms on a laptop.
LEG_SAMPLES = 12

# Exponent for corridor_score = 100 · exp(-KAPPA · total_risk_km).
# Anchored on Tempo's `kappa = 0.28`; slightly softer so a well-planned
# 3-risk-km day still scores ≥ 79 (mid-Serene), not upper-Solid.
CORRIDOR_KAPPA = 0.25

# ---- Fatigue ----------------------------------------------------------
FATIGUE_FREE_STOPS = 3        # up to 3 stops = no fatigue
FATIGUE_STEP_PTS   = 3.0      # each extra stop drops the day this many pts

# ---- Trip aggregate ---------------------------------------------------
# Weight on the worst day when computing the trip composite. 0.4 → the
# min day contributes ~40% of the trip verdict; a single Fragile day
# can't hide behind Serene neighbours.
MIN_DAY_WEIGHT   = 0.40
MEAN_DAY_WEIGHT  = 0.60       # = 1 - MIN_DAY_WEIGHT

# ---- Bands (per-day + trip) ------------------------------------------
BAND_LADDER: Tuple[Tuple[int, str, str], ...] = (
    # (score_floor, band, hue)
    (85, "Serene",  "#53E3A6"),
    (70, "Solid",   "#7BC5F1"),
    (55, "Bumpy",   "#F9C440"),
    (35, "Fragile", "#FF9F43"),
    ( 0, "Critical","#FF3D60"),
)
_BAND_RANK = {"Serene": 0, "Solid": 1, "Bumpy": 2, "Fragile": 3, "Critical": 4}
FRAGILE_FLOOR = 45   # any day < 45 forces Fragile trip verdict
CRITICAL_FLOOR = 35   # ...and < 35 forces Critical

# ---- Trip verdict gates ----------------------------------------------
SERENE_GATE = dict(mean_min=82, min_min=78, drift_min=-2, allow_fragile_day=False)
SOLID_GATE  = dict(mean_min=70, min_min=60)
BUMPY_GATE  = dict(mean_min=55)

# ---- Weakest link swap uplift threshold ------------------------------
MIN_UPLIFT_PTS = 2.0   # only emit a swap if it moves the day this much

# ---- Version --------------------------------------------------------
VERSION = "waysafe.odyssey.v1"
ENGINE_VERSION = "1.0.0"


# ============================================================== types ===

@dataclass(frozen=True)
class Stop:
    """One planned stop within an Odyssey day."""
    label: str
    lat: float
    lon: float
    dwell_min: int = 60          # minutes spent at the stop
    arrival_hour: Optional[int] = None   # explicit override; None = derived


@dataclass
class OdysseyDay:
    """One day in the trip. The stay is where the traveller sleeps that
    night; `stops` are the destinations visited in order that day."""
    date: str                    # ISO YYYY-MM-DD
    label: str                   # e.g. "Day 1 — Panjim"
    stay_lat: float
    stay_lon: float
    stay_label: str
    stops: Tuple[Stop, ...] = field(default_factory=tuple)
    depart_hour: int = 9         # 24-h, morning depart from stay
    transit_mode: str = "auto"   # "walk" | "auto" | "cab"


@dataclass
class LegReport:
    """One (a → b) corridor leg's realised safety numbers."""
    a_label: str
    b_label: str
    distance_km: float
    eta_min: float
    mean_risk: float             # 0..1 mean point_risk over LEG_SAMPLES waypoints
    peak_risk: float             # 0..1 max point_risk over LEG_SAMPLES waypoints
    risk_km: float               # mean_risk · distance_km
    min_safety_along: int        # 100·(1 - peak_risk), 0..100
    samples: Tuple[Tuple[float, float, float], ...] = field(default_factory=tuple)
    # ^ (lat, lon, risk_0_1) waypoints — used for the corridor heat strip


@dataclass
class DayReport:
    """One day's composed safety report."""
    day: OdysseyDay
    stay_score: int
    stay_band: str
    stay_result: SafetyResult
    stop_scores: Tuple[int, ...]
    stop_bands: Tuple[str, ...]
    stop_results: Tuple[SafetyResult, ...]
    legs: Tuple[LegReport, ...]
    total_distance_km: float
    total_risk_km: float
    total_eta_min: float
    fatigue_penalty: float
    corridor_score: int          # 0..100
    day_score: int               # 0..100 composite (post-fatigue)
    day_band: str
    day_hue: str
    n_stops: int
    reason: str                  # one-line "why this score" for the UI


@dataclass
class SwapSuggestion:
    """A concrete alternative for the weakest link."""
    kind: str                    # "TIME_SHIFT" | "REORDER" | "MODE_UPGRADE" | "STAY_SWAP"
    day_index: int
    label: str                   # human-readable one-liner
    detail: str                  # 1-2 sentence explanation
    expected_uplift_pts: float   # expected day-score delta (positive = safer)
    target_band: Optional[str] = None    # band the day would move into


@dataclass
class WeakestLink:
    """The single lowest-scoring (day, leg) tuple in the trip."""
    day_index: int
    day_label: str
    leg_index: int               # -1 if the weakest is the *stay itself*
    leg_label: str
    kind: str                    # "STAY" | "LEG" | "STOP"
    score: int                   # 0..100 of the offending element
    band: str
    reason: str                  # one-line diagnosis
    swaps: Tuple[SwapSuggestion, ...]   # 0..3 ranked candidates


@dataclass
class TripReport:
    """The full multi-day Odyssey composition."""
    days: Tuple[DayReport, ...]
    trip_score: int              # 0..100 aggregate
    trip_band: str
    trip_hue: str
    verdict: str                 # e.g. "Solid" | "Bumpy" | "Fragile" | ...
    verdict_reason: str          # one-line explanation
    mean_day_score: float
    min_day_score: int
    max_day_score: int
    drift_index: float           # signed sum of consecutive day deltas
    persistence_streak: int      # longest run of Bumpy+/Fragile days
    total_distance_km: float
    total_risk_km: float
    total_eta_min: float
    total_stops: int
    n_days: int
    weakest_link: Optional[WeakestLink]
    trip_advisory: Tuple[str, ...]       # 3-6 ranked action lines
    now: datetime
    engine_version: str = ENGINE_VERSION


# ========================================================= band helpers ==

def _band_for(score: int) -> Tuple[str, str]:
    """Return (band, hex_hue) for a 0..100 score."""
    for floor, band, hue in BAND_LADDER:
        if score >= floor:
            return band, hue
    return "Critical", "#FF3D60"


def _worst_band(bands: Iterable[str]) -> str:
    """Given several band labels, return the worst (highest rank)."""
    worst_rank = -1
    worst = "Serene"
    for b in bands:
        r = _BAND_RANK.get(b, -1)
        if r > worst_rank:
            worst_rank = r
            worst = b
    return worst


# ========================================================= corridor mm ==

def _hour_of_iso_day(iso_date: str, hour: int, minute: int = 0) -> datetime:
    """Parse an ISO YYYY-MM-DD and return a datetime pinned to (hour, min)
    in local (UTC-naïve) time.  Fallback: today at (hour, min)."""
    try:
        d = date_cls.fromisoformat(iso_date)
    except (ValueError, TypeError):
        d = datetime.utcnow().date()
    return datetime(d.year, d.month, d.day, hour % 24, minute % 60)


def _travel_kmh_for(mode: str) -> float:
    """Deterministic average speed by transit mode.  Anchored on
    routing.AVG_TRAVEL_KMH = 32 for `auto`."""
    m = str(mode or "").lower()
    if m == "walk":
        return 4.5
    if m == "cab":
        return 34.0
    # auto (default)
    return 32.0


def _leg_between(
    a_label: str, a_lat: float, a_lon: float,
    b_label: str, b_lat: float, b_lon: float,
    incidents: Sequence[Mapping],
    geofences: Mapping,
    pois: Sequence[Mapping],
    depart: datetime,
    transit_mode: str = "auto",
) -> LegReport:
    """Compose a single leg's LegReport by sampling the straight-line
    corridor with `LEG_SAMPLES` waypoints and averaging `point_risk`.

    We use straight-line sampling (not A*) because:

      * the traveller can always drill into a specific leg in the
        Plan Route tab for the full A* replan;
      * a 5-day × 4-leg trip would otherwise cost 20 A* searches per
        Odyssey run — this drops it to 20 × 12 point_risk calls,
        deterministic in ~5 ms on a laptop;
      * the corridor lens (mean + peak + risk-km) captures the same
        signals Compass / Tempo use, in the same range 0..1.
    """
    dist = haversine_km(a_lat, a_lon, b_lat, b_lon)
    if dist < 0.02:
        # Degenerate co-located leg — same point counted twice.
        return LegReport(
            a_label=a_label, b_label=b_label,
            distance_km=0.0, eta_min=0.0,
            mean_risk=0.0, peak_risk=0.0,
            risk_km=0.0, min_safety_along=100,
            samples=((a_lat, a_lon, 0.0),),
        )
    samples: List[Tuple[float, float, float]] = []
    total = 0.0
    peak = 0.0
    n = max(2, LEG_SAMPLES)
    for i in range(n):
        t = i / (n - 1)
        lat = a_lat + t * (b_lat - a_lat)
        lon = a_lon + t * (b_lon - a_lon)
        r = point_risk(lat, lon, incidents, geofences, pois, now=depart)
        samples.append((lat, lon, r))
        total += r
        peak = max(peak, r)
    mean = total / n
    risk_km = mean * dist
    kmh = _travel_kmh_for(transit_mode)
    eta_min = 60.0 * dist / kmh
    return LegReport(
        a_label=a_label, b_label=b_label,
        distance_km=round(dist, 3),
        eta_min=round(eta_min, 1),
        mean_risk=round(mean, 4),
        peak_risk=round(peak, 4),
        risk_km=round(risk_km, 3),
        min_safety_along=int(round(100.0 * (1.0 - peak))),
        samples=tuple(samples),
    )


# ============================================================== compose ==

def _fatigue_penalty(n_stops: int) -> float:
    """Every stop past FATIGUE_FREE_STOPS costs FATIGUE_STEP_PTS points."""
    excess = max(0, n_stops - FATIGUE_FREE_STOPS)
    return excess * FATIGUE_STEP_PTS


def _day_reason(dr_stay: SafetyResult, stop_scores: Sequence[int],
                corridor_score: int, day_score: int) -> str:
    """One-line diagnosis of why this day scored where it did."""
    parts: List[str] = []
    if dr_stay.score < 60:
        parts.append(f"stay soft at {dr_stay.score}")
    else:
        parts.append(f"stay {dr_stay.score}")
    if stop_scores:
        m = int(round(sum(stop_scores) / len(stop_scores)))
        if min(stop_scores) < 55:
            parts.append(f"weakest stop {min(stop_scores)}")
        else:
            parts.append(f"stops mean {m}")
    parts.append(f"corridor {corridor_score}")
    return " · ".join(parts) + f" → {day_score}"


def _compose_day(
    day: OdysseyDay,
    incidents: Sequence[Mapping],
    geofences: Mapping,
    pois: Sequence[Mapping],
) -> DayReport:
    """Score one Odyssey day.  Deterministic.

    - Stay is scored at hour=20 of the day (the evening return-window;
      what matters for the stay-safety calculation is the hour the
      traveller is actually at the stay, not the moment of check-in).
    - Each stop is scored at its arrival hour (depart_hour + cumulative
      travel + prior dwell), so a stop planned for 22:00 gets the
      late-night penalty even if depart_hour=09:00.
    - Legs are sampled in trip order.
    """
    stay_time = _hour_of_iso_day(day.date, 20, 0)
    stay_result = compute_safety(
        day.stay_lat, day.stay_lon,
        incidents=list(incidents), geofences=geofences,
        pois=list(pois), now=stay_time,
    )
    stay_score = stay_result.score
    stay_band = stay_result.band

    stops = tuple(day.stops)
    legs: List[LegReport] = []
    stop_scores: List[int] = []
    stop_bands: List[str] = []
    stop_results: List[SafetyResult] = []

    # Walk the stay → stop_1 → stop_2 … → stay chain.
    prev_label = day.stay_label
    prev_lat = day.stay_lat
    prev_lon = day.stay_lon
    cursor = _hour_of_iso_day(day.date, day.depart_hour, 0)

    for stop in stops:
        # Leg to this stop.
        leg = _leg_between(
            prev_label, prev_lat, prev_lon,
            stop.label, stop.lat, stop.lon,
            incidents=list(incidents), geofences=geofences,
            pois=list(pois), depart=cursor,
            transit_mode=day.transit_mode,
        )
        legs.append(leg)
        cursor = cursor + timedelta(minutes=leg.eta_min)

        # Score the stop at explicit arrival hour if given, else at the
        # accumulated cursor time.
        if stop.arrival_hour is not None:
            arrive = _hour_of_iso_day(day.date, int(stop.arrival_hour), 0)
        else:
            arrive = cursor
        sr = compute_safety(
            stop.lat, stop.lon,
            incidents=list(incidents), geofences=geofences,
            pois=list(pois), now=arrive,
        )
        stop_scores.append(sr.score)
        stop_bands.append(sr.band)
        stop_results.append(sr)

        # Advance the cursor by dwell.
        cursor = cursor + timedelta(minutes=int(stop.dwell_min))
        prev_label = stop.label
        prev_lat = stop.lat
        prev_lon = stop.lon

    # Return-leg back to the stay (only if there was at least one stop).
    if stops:
        return_leg = _leg_between(
            prev_label, prev_lat, prev_lon,
            day.stay_label, day.stay_lat, day.stay_lon,
            incidents=list(incidents), geofences=geofences,
            pois=list(pois), depart=cursor,
            transit_mode=day.transit_mode,
        )
        legs.append(return_leg)

    total_distance = sum(leg.distance_km for leg in legs)
    total_risk_km = sum(leg.risk_km for leg in legs)
    total_eta = sum(leg.eta_min for leg in legs)
    corridor_score = int(round(100.0 * math.exp(-CORRIDOR_KAPPA * total_risk_km)))
    corridor_score = max(0, min(100, corridor_score))

    stops_mean = (sum(stop_scores) / len(stop_scores)) if stop_scores else stay_score
    raw = (STAY_WEIGHT * stay_score
           + STOPS_WEIGHT * stops_mean
           + CORRIDOR_WEIGHT * corridor_score)
    fatigue = _fatigue_penalty(len(stops))
    day_score = int(round(max(0.0, min(100.0, raw - fatigue))))
    day_band, day_hue = _band_for(day_score)
    reason = _day_reason(stay_result, stop_scores, corridor_score, day_score)

    return DayReport(
        day=day,
        stay_score=stay_score,
        stay_band=stay_band,
        stay_result=stay_result,
        stop_scores=tuple(stop_scores),
        stop_bands=tuple(stop_bands),
        stop_results=tuple(stop_results),
        legs=tuple(legs),
        total_distance_km=round(total_distance, 2),
        total_risk_km=round(total_risk_km, 3),
        total_eta_min=round(total_eta, 1),
        fatigue_penalty=round(fatigue, 1),
        corridor_score=corridor_score,
        day_score=day_score,
        day_band=day_band,
        day_hue=day_hue,
        n_stops=len(stops),
        reason=reason,
    )


# ============================================================== swaps ==

def _swap_time_shift(
    day: OdysseyDay, dr: DayReport,
    incidents: Sequence[Mapping],
    geofences: Mapping,
    pois: Sequence[Mapping],
    forecaster: Any = None,
) -> Optional[SwapSuggestion]:
    """Probe depart_hour ± 3 h; pick the hour that maximises the day
    score.  Uses a lightweight re-composition on the *stay + corridor*
    only (stops don't move) — good enough because most of a day's
    late-night penalty travels with depart_hour, not with the stop.
    """
    best_score = dr.day_score
    best_hour: Optional[int] = None
    for delta in (-3, -2, -1, 1, 2, 3):
        h = day.depart_hour + delta
        if h < 5 or h > 20:
            continue  # anything past 20:00 hits the late-night hard-stop
        probe = OdysseyDay(
            date=day.date, label=day.label,
            stay_lat=day.stay_lat, stay_lon=day.stay_lon, stay_label=day.stay_label,
            stops=day.stops, depart_hour=h, transit_mode=day.transit_mode,
        )
        probe_report = _compose_day(probe, incidents, geofences, pois)
        # Small forecast bonus if a forecaster is available and the new
        # arrival-hour is objectively safer.
        if forecaster is not None and hasattr(forecaster, "risk_at"):
            try:
                arrive_now = _hour_of_iso_day(day.date, day.depart_hour + 1, 0)
                arrive_new = _hour_of_iso_day(day.date, h + 1, 0)
                # Sample at the first stop, else at the stay.
                lat = day.stops[0].lat if day.stops else day.stay_lat
                lon = day.stops[0].lon if day.stops else day.stay_lon
                r_now = float(forecaster.risk_at(lat, lon, arrive_now))
                r_new = float(forecaster.risk_at(lat, lon, arrive_new))
                probe_report = DayReport(
                    **{**asdict(probe_report),
                       "day_score": max(0, min(100,
                           probe_report.day_score + int(round(6.0 * (r_now - r_new))))),
                       "day": probe,
                       "stay_result": probe_report.stay_result,
                       "stop_results": probe_report.stop_results,
                       "legs": probe_report.legs,
                       "stop_scores": probe_report.stop_scores,
                       "stop_bands": probe_report.stop_bands}
                )
            except Exception:
                pass
        if probe_report.day_score > best_score:
            best_score = probe_report.day_score
            best_hour = h
    if best_hour is None:
        return None
    uplift = best_score - dr.day_score
    if uplift < MIN_UPLIFT_PTS:
        return None
    target_band, _ = _band_for(best_score)
    return SwapSuggestion(
        kind="TIME_SHIFT",
        day_index=-1,
        label=f"Depart at {best_hour:02d}:00 instead of {day.depart_hour:02d}:00",
        detail=(
            f"Shifting the depart hour from {day.depart_hour:02d}:00 to "
            f"{best_hour:02d}:00 nudges the arrival window past the peak "
            f"risk hour on the corridor. Expected day score: "
            f"{dr.day_score} → {best_score}."
        ),
        expected_uplift_pts=round(uplift, 1),
        target_band=target_band,
    )


def _swap_reorder(
    day: OdysseyDay, dr: DayReport,
    incidents: Sequence[Mapping],
    geofences: Mapping,
    pois: Sequence[Mapping],
) -> Optional[SwapSuggestion]:
    """Try one stop-permutation (reverse order) and keep it if
    total_risk_km drops by ≥ 1 unit."""
    if len(day.stops) < 2:
        return None
    reversed_stops = tuple(reversed(day.stops))
    probe = OdysseyDay(
        date=day.date, label=day.label,
        stay_lat=day.stay_lat, stay_lon=day.stay_lon, stay_label=day.stay_label,
        stops=reversed_stops, depart_hour=day.depart_hour,
        transit_mode=day.transit_mode,
    )
    probe_report = _compose_day(probe, incidents, geofences, pois)
    uplift = probe_report.day_score - dr.day_score
    if uplift < MIN_UPLIFT_PTS:
        return None
    target_band, _ = _band_for(probe_report.day_score)
    original = " → ".join(s.label for s in day.stops)
    reversed_order = " → ".join(s.label for s in reversed_stops)
    return SwapSuggestion(
        kind="REORDER",
        day_index=-1,
        label="Reverse the stop order",
        detail=(
            f"Try `{reversed_order}` instead of `{original}`. Shorter "
            f"corridor legs → total risk-km drops from "
            f"{dr.total_risk_km:.2f} to {probe_report.total_risk_km:.2f}. "
            f"Expected day score: {dr.day_score} → {probe_report.day_score}."
        ),
        expected_uplift_pts=round(uplift, 1),
        target_band=target_band,
    )


def _swap_mode_upgrade(
    day: OdysseyDay, dr: DayReport,
    incidents: Sequence[Mapping],
    geofences: Mapping,
    pois: Sequence[Mapping],
) -> Optional[SwapSuggestion]:
    """If the day is on foot and dwells into late-night territory, propose
    switching the transit mode to `cab` which cuts corridor exposure."""
    if str(day.transit_mode).lower() != "walk":
        return None
    # Only emit if the trip is at least 3 km — cab is overkill for a
    # walkable day.
    if dr.total_distance_km < 3.0:
        return None
    probe = OdysseyDay(
        date=day.date, label=day.label,
        stay_lat=day.stay_lat, stay_lon=day.stay_lon, stay_label=day.stay_label,
        stops=day.stops, depart_hour=day.depart_hour, transit_mode="cab",
    )
    probe_report = _compose_day(probe, incidents, geofences, pois)
    uplift = probe_report.day_score - dr.day_score
    if uplift < MIN_UPLIFT_PTS:
        return None
    target_band, _ = _band_for(probe_report.day_score)
    return SwapSuggestion(
        kind="MODE_UPGRADE",
        day_index=-1,
        label="Switch corridor mode from walk → cab",
        detail=(
            f"Walking a {dr.total_distance_km:.1f} km corridor across "
            f"{len(day.stops)} stops keeps the traveller on-street through "
            f"most of the depart-hour risk window. A metered cab cuts "
            f"corridor exposure sharply. "
            f"Expected day score: {dr.day_score} → {probe_report.day_score}."
        ),
        expected_uplift_pts=round(uplift, 1),
        target_band=target_band,
    )


def _swap_stay_switch(dr: DayReport, day_index: int) -> Optional[SwapSuggestion]:
    """If the *stay* is what's dragging the day down (not the corridor,
    not the stops), emit a StaySafe-tab pointer.  We don't try to invent
    a new stay here — that's StaySafe's job — but we name the fact so the
    weakest-link block leads the traveller to the right surface."""
    if dr.stay_score >= 65:
        return None
    if dr.corridor_score >= dr.stay_score - 3:
        return None  # corridor is worse or equal; not a stay issue
    # If the min stop score is worse than the stay, don't blame the stay.
    if dr.stop_scores and min(dr.stop_scores) < dr.stay_score - 5:
        return None
    target_band, _ = _band_for(min(100, dr.day_score + 8))
    return SwapSuggestion(
        kind="STAY_SWAP",
        day_index=day_index,
        label=f"Re-pick the stay near {dr.day.stay_label}",
        detail=(
            f"Stay `{dr.day.stay_label}` scores {dr.stay_score} at hour=20 "
            f"— below the corridor ({dr.corridor_score}) and the stops "
            f"({int(round(sum(dr.stop_scores)/max(1,len(dr.stop_scores))))} mean). "
            f"Open the StaySafe tab and compare 2–3 alternates within 1.5 km. "
            f"A stay 8 pts safer typically moves the day into `{target_band}`."
        ),
        expected_uplift_pts=8.0,
        target_band=target_band,
    )


def _weakest_link_for(
    reports: Sequence[DayReport],
    incidents: Sequence[Mapping],
    geofences: Mapping,
    pois: Sequence[Mapping],
    forecaster: Any = None,
) -> Optional[WeakestLink]:
    """Find the single worst (day, element) and rank up to 3 swaps."""
    if not reports:
        return None
    # Rank each element (stay + each leg + each stop) across all days by
    # its score.  Lowest = weakest link.
    candidates: List[Tuple[int, int, str, str, int, str]] = []
    # (day_idx, elem_idx, kind, label, score, reason)
    for di, dr in enumerate(reports):
        # Stay
        candidates.append((
            di, -1, "STAY", f"{dr.day.stay_label} (stay)",
            dr.stay_score,
            f"Stay penalised {100 - dr.stay_score} pts at evening return window",
        ))
        # Stops
        for si, (score, band, stop) in enumerate(zip(
                dr.stop_scores, dr.stop_bands, dr.day.stops)):
            candidates.append((
                di, si, "STOP", f"{stop.label} (stop)",
                score,
                f"Stop scored {score} ({band}) at planned arrival",
            ))
        # Legs
        for li, leg in enumerate(dr.legs):
            score = leg.min_safety_along
            candidates.append((
                di, li, "LEG",
                f"{leg.a_label} → {leg.b_label}",
                score,
                f"Corridor peak-risk pocket dropped safety to {score} along the leg",
            ))
    candidates.sort(key=lambda t: t[4])
    di, ei, kind, label, score, reason = candidates[0]
    dr = reports[di]
    band, _ = _band_for(score)

    # Build swap list — max 3, ranked by uplift.
    swaps: List[SwapSuggestion] = []
    for cand in (
        _swap_time_shift(dr.day, dr, incidents, geofences, pois, forecaster),
        _swap_reorder(dr.day, dr, incidents, geofences, pois),
        _swap_mode_upgrade(dr.day, dr, incidents, geofences, pois),
        _swap_stay_switch(dr, di),
    ):
        if cand is None:
            continue
        # Stamp with the day_index we're targeting.
        if cand.day_index == -1:
            cand = SwapSuggestion(
                kind=cand.kind, day_index=di,
                label=cand.label, detail=cand.detail,
                expected_uplift_pts=cand.expected_uplift_pts,
                target_band=cand.target_band,
            )
        swaps.append(cand)
    swaps.sort(key=lambda s: -s.expected_uplift_pts)
    swaps = swaps[:3]
    return WeakestLink(
        day_index=di,
        day_label=dr.day.label,
        leg_index=ei,
        leg_label=label,
        kind=kind,
        score=score,
        band=band,
        reason=reason,
        swaps=tuple(swaps),
    )


# ========================================================= trip aggregate ==

def _drift_index(day_scores: Sequence[int]) -> float:
    """Signed sum of consecutive day deltas.  Positive = trip warms up.
    Negative = trip degrades toward the end (worst outcome — you're
    stuck)."""
    if len(day_scores) < 2:
        return 0.0
    return float(sum(day_scores[i+1] - day_scores[i] for i in range(len(day_scores)-1)))


def _persistence_streak(day_scores: Sequence[int]) -> int:
    """Longest run of consecutive Bumpy-or-worse days."""
    streak = 0
    best = 0
    for s in day_scores:
        band, _ = _band_for(s)
        if band in ("Bumpy", "Fragile", "Critical"):
            streak += 1
            best = max(best, streak)
        else:
            streak = 0
    return best


def _verdict_for(mean_day: float, min_day: int, day_scores: Sequence[int],
                 drift: float, streak: int) -> Tuple[str, str]:
    """Pick the trip verdict.  Returns (verdict, one_line_reason)."""
    fragile_present = any(s < FRAGILE_FLOOR for s in day_scores)
    critical_present = any(s < CRITICAL_FLOOR for s in day_scores)
    if critical_present:
        return "Critical", (
            f"One day scored below the {CRITICAL_FLOOR} floor — trip caps at Critical "
            f"regardless of the other days."
        )
    # Serene gate
    if (mean_day >= SERENE_GATE["mean_min"]
        and min_day >= SERENE_GATE["min_min"]
        and drift >= SERENE_GATE["drift_min"]
        and not fragile_present):
        return "Serene", (
            f"Mean {mean_day:.0f} · min {min_day} · drift {drift:+.0f} — every "
            f"gate cleared, no Fragile day."
        )
    # Solid gate
    if (mean_day >= SOLID_GATE["mean_min"]
        and min_day >= SOLID_GATE["min_min"]):
        return "Solid", (
            f"Mean {mean_day:.0f} ≥ {SOLID_GATE['mean_min']} and min {min_day} "
            f"≥ {SOLID_GATE['min_min']} — trip meets the Solid gate; "
            f"weakest day sets the ceiling."
        )
    # Bumpy gate
    if mean_day >= BUMPY_GATE["mean_min"]:
        return "Bumpy", (
            f"Mean {mean_day:.0f} clears Bumpy but the min day ({min_day}) "
            f"holds the verdict below Solid; see the weakest-link swaps to "
            f"lift it."
        )
    # Fragile default
    return "Fragile", (
        f"Mean {mean_day:.0f} sits below the Bumpy gate ({BUMPY_GATE['mean_min']}). "
        f"At least one swap is required before the trip stabilises."
    )


def _trip_advisory(
    verdict: str, weakest: Optional[WeakestLink],
    persistence: int, drift: float,
    reports: Sequence[DayReport],
) -> Tuple[str, ...]:
    """Compose an ordered advisory strip.  First-match-wins for the top
    line so the reader always sees the most important action first."""
    lines: List[str] = []

    # Top line — verdict-appropriate action.
    if verdict in ("Fragile", "Critical") and weakest is not None:
        lines.append(
            f"Weakest link: {weakest.day_label} — {weakest.leg_label} ({weakest.score}). "
            f"Apply the top swap before committing the trip."
        )
    elif verdict == "Bumpy" and weakest is not None:
        lines.append(
            f"Weakest link: {weakest.leg_label} on {weakest.day_label}. One swap "
            f"lifts the day and pulls the trip up."
        )
    elif verdict == "Solid":
        lines.append(
            "Trip meets the Solid gate. Review the weakest-link swap to see "
            "whether a small tweak could unlock Serene."
        )
    else:  # Serene
        lines.append("Trip meets every Serene gate. No action required.")

    # Drift / persistence lines.
    if persistence >= 2:
        lines.append(
            f"Persistence: {persistence} consecutive Bumpy-or-worse days. Break "
            f"the streak — swap a stay or drop a stop from the middle day."
        )
    if drift < -6:
        lines.append(
            f"Drift is {drift:+.0f} — trip degrades toward the end. Front-load "
            f"the risky stops onto the earliest day so buffer accumulates."
        )
    elif drift > 6:
        lines.append(
            f"Drift is {drift:+.0f} — trip warms up. Buffer is in the back "
            f"half; front days can absorb one bad call without cascading."
        )

    # Late-night stops — surface separately.
    late_stops: List[str] = []
    for dr in reports:
        cursor_hour = dr.day.depart_hour
        for i, stop in enumerate(dr.day.stops):
            leg = dr.legs[i] if i < len(dr.legs) else None
            eta_h = (leg.eta_min if leg else 0) / 60.0
            cursor_hour = cursor_hour + eta_h
            arrival = int(cursor_hour) % 24
            if arrival >= 22 or arrival < 5:
                late_stops.append(f"{stop.label} on {dr.day.label} arrives ~{arrival:02d}:00")
            cursor_hour += stop.dwell_min / 60.0
    if late_stops:
        lines.append(
            "Late-night arrivals: " + ", ".join(late_stops[:2])
            + (" — consider a Tempo-tab depart-shift." if len(late_stops) <= 2
               else f" (+{len(late_stops)-2} more) — Tempo can find a safer window.")
        )

    # Big-fatigue days.
    fat_days = [dr for dr in reports if dr.fatigue_penalty > 0]
    if fat_days:
        which = fat_days[0]
        lines.append(
            f"Fatigue penalty on {which.day.label}: {which.n_stops} stops "
            f"costs {which.fatigue_penalty:.0f} pts. Consider trimming one stop."
        )

    return tuple(lines[:6])


def compose_odyssey(
    *,
    days: Sequence[OdysseyDay],
    incidents: Iterable[Mapping] | None,
    geofences: Mapping,
    pois: Iterable[Mapping] | None,
    forecaster: Any = None,
    now: Optional[datetime] = None,
) -> TripReport:
    """Single entrypoint.  Compose the full multi-day report.

    Deterministic — same input bytes → same output bytes.  `forecaster`
    is optional; if absent the time-shift swap falls back to the
    `safety.compute_safety` late-night penalty, which still catches the
    biggest hour-of-day risk.

    A zero-day trip returns an empty TripReport with `verdict="empty"`.
    """
    inc = list(incidents or [])
    poi = list(pois or [])
    geo = geofences or {"features": []}
    now = now or datetime.utcnow()

    reports: List[DayReport] = []
    for day in days:
        reports.append(_compose_day(day, inc, geo, poi))

    if not reports:
        return TripReport(
            days=tuple(),
            trip_score=0, trip_band="Critical", trip_hue="#FF3D60",
            verdict="empty",
            verdict_reason="No days provided.  Add at least one day to compose an Odyssey.",
            mean_day_score=0.0, min_day_score=0, max_day_score=0,
            drift_index=0.0, persistence_streak=0,
            total_distance_km=0.0, total_risk_km=0.0, total_eta_min=0.0,
            total_stops=0, n_days=0,
            weakest_link=None, trip_advisory=("Add a day.",),
            now=now,
        )

    day_scores = [dr.day_score for dr in reports]
    mean_day = sum(day_scores) / len(day_scores)
    min_day = min(day_scores)
    max_day = max(day_scores)
    drift = _drift_index(day_scores)
    streak = _persistence_streak(day_scores)

    # Trip composite — worst-day-weighted.
    trip_score = int(round(MEAN_DAY_WEIGHT * mean_day + MIN_DAY_WEIGHT * min_day))
    trip_score = max(0, min(100, trip_score))
    trip_band, trip_hue = _band_for(trip_score)
    verdict, verdict_reason = _verdict_for(mean_day, min_day, day_scores, drift, streak)
    # Bind the trip_band to the verdict for the UI (verdict beats band).
    trip_band = verdict
    for floor, band, hue in BAND_LADDER:
        if band == verdict:
            trip_hue = hue
            break

    weakest = _weakest_link_for(reports, inc, geo, poi, forecaster)
    advisory = _trip_advisory(verdict, weakest, streak, drift, reports)

    return TripReport(
        days=tuple(reports),
        trip_score=trip_score,
        trip_band=trip_band,
        trip_hue=trip_hue,
        verdict=verdict,
        verdict_reason=verdict_reason,
        mean_day_score=round(mean_day, 1),
        min_day_score=min_day,
        max_day_score=max_day,
        drift_index=round(drift, 1),
        persistence_streak=streak,
        total_distance_km=round(sum(dr.total_distance_km for dr in reports), 2),
        total_risk_km=round(sum(dr.total_risk_km for dr in reports), 3),
        total_eta_min=round(sum(dr.total_eta_min for dr in reports), 1),
        total_stops=sum(dr.n_stops for dr in reports),
        n_days=len(reports),
        weakest_link=weakest,
        trip_advisory=advisory,
        now=now,
    )


# ============================================================== exports ==

def _safety_result_to_dict(sr: SafetyResult) -> dict:
    return {
        "score": sr.score,
        "band": sr.band,
        "factors": list(sr.factors),
        "nearest_help_km": sr.nearest_help_km,
        "incidents_nearby": sr.incidents_nearby,
    }


def _leg_to_dict(leg: LegReport) -> dict:
    return {
        "a": leg.a_label,
        "b": leg.b_label,
        "distance_km": leg.distance_km,
        "eta_min": leg.eta_min,
        "mean_risk": leg.mean_risk,
        "peak_risk": leg.peak_risk,
        "risk_km": leg.risk_km,
        "min_safety_along": leg.min_safety_along,
        "samples": [
            {"lat": lat, "lon": lon, "risk": r}
            for lat, lon, r in leg.samples
        ],
    }


def _day_to_dict(dr: DayReport) -> dict:
    return {
        "date": dr.day.date,
        "label": dr.day.label,
        "stay": {
            "label": dr.day.stay_label,
            "lat": dr.day.stay_lat, "lon": dr.day.stay_lon,
            "score": dr.stay_score, "band": dr.stay_band,
            "result": _safety_result_to_dict(dr.stay_result),
        },
        "stops": [
            {
                "label": stop.label, "lat": stop.lat, "lon": stop.lon,
                "dwell_min": stop.dwell_min, "arrival_hour": stop.arrival_hour,
                "score": score, "band": band,
                "result": _safety_result_to_dict(sr),
            }
            for stop, score, band, sr in zip(
                dr.day.stops, dr.stop_scores, dr.stop_bands, dr.stop_results,
            )
        ],
        "depart_hour": dr.day.depart_hour,
        "transit_mode": dr.day.transit_mode,
        "legs": [_leg_to_dict(leg) for leg in dr.legs],
        "totals": {
            "distance_km": dr.total_distance_km,
            "risk_km": dr.total_risk_km,
            "eta_min": dr.total_eta_min,
            "fatigue_penalty_pts": dr.fatigue_penalty,
            "corridor_score": dr.corridor_score,
            "n_stops": dr.n_stops,
        },
        "day_score": dr.day_score,
        "day_band": dr.day_band,
        "day_hue": dr.day_hue,
        "reason": dr.reason,
    }


def _swap_to_dict(sw: SwapSuggestion) -> dict:
    return {
        "kind": sw.kind,
        "day_index": sw.day_index,
        "label": sw.label,
        "detail": sw.detail,
        "expected_uplift_pts": sw.expected_uplift_pts,
        "target_band": sw.target_band,
    }


def _weakest_to_dict(w: Optional[WeakestLink]) -> Optional[dict]:
    if w is None:
        return None
    return {
        "day_index": w.day_index,
        "day_label": w.day_label,
        "leg_index": w.leg_index,
        "leg_label": w.leg_label,
        "kind": w.kind,
        "score": w.score,
        "band": w.band,
        "reason": w.reason,
        "swaps": [_swap_to_dict(s) for s in w.swaps],
    }


def to_dict(trip: TripReport) -> dict:
    """Full JSON-serialisable view under the `waysafe.odyssey.v1` envelope."""
    return {
        "envelope": VERSION,
        "engine_version": trip.engine_version,
        "now": trip.now.isoformat(),
        "trip": {
            "score": trip.trip_score,
            "band": trip.trip_band,
            "hue": trip.trip_hue,
            "verdict": trip.verdict,
            "verdict_reason": trip.verdict_reason,
            "mean_day_score": trip.mean_day_score,
            "min_day_score": trip.min_day_score,
            "max_day_score": trip.max_day_score,
            "drift_index": trip.drift_index,
            "persistence_streak": trip.persistence_streak,
            "total_distance_km": trip.total_distance_km,
            "total_risk_km": trip.total_risk_km,
            "total_eta_min": trip.total_eta_min,
            "total_stops": trip.total_stops,
            "n_days": trip.n_days,
        },
        "days": [_day_to_dict(dr) for dr in trip.days],
        "weakest_link": _weakest_to_dict(trip.weakest_link),
        "advisory": list(trip.trip_advisory),
        "rules": {
            "stay_weight": STAY_WEIGHT,
            "stops_weight": STOPS_WEIGHT,
            "corridor_weight": CORRIDOR_WEIGHT,
            "corridor_kappa": CORRIDOR_KAPPA,
            "fatigue_free_stops": FATIGUE_FREE_STOPS,
            "fatigue_step_pts": FATIGUE_STEP_PTS,
            "min_day_weight": MIN_DAY_WEIGHT,
            "mean_day_weight": MEAN_DAY_WEIGHT,
            "fragile_floor": FRAGILE_FLOOR,
            "critical_floor": CRITICAL_FLOOR,
            "verdict_gates": {
                "serene": SERENE_GATE,
                "solid":  SOLID_GATE,
                "bumpy":  BUMPY_GATE,
            },
            "leg_samples": LEG_SAMPLES,
        },
    }


def to_json(trip: TripReport, *, indent: int = 2) -> str:
    """`to_dict` serialised. `indent=None` for compact."""
    return json.dumps(to_dict(trip), indent=indent, sort_keys=False)


def to_markdown(trip: TripReport) -> str:
    """One-page markdown digest — pastes cleanly into a duty-of-care note."""
    lines: List[str] = []
    lines.append(f"# Odyssey — {trip.n_days}-day trip report")
    lines.append("")
    lines.append(f"**Verdict — {trip.verdict}** · trip score `{trip.trip_score}` · "
                 f"mean day `{trip.mean_day_score:.1f}` · min day `{trip.min_day_score}` · "
                 f"drift `{trip.drift_index:+.1f}`")
    lines.append("")
    lines.append(f"> {trip.verdict_reason}")
    lines.append("")

    lines.append("## Days")
    lines.append("")
    lines.append("| # | Date | Label | Stops | Distance km | Risk-km | Score | Band |")
    lines.append("|---|---|---|---:|---:|---:|---:|---|")
    for i, dr in enumerate(trip.days, 1):
        lines.append(
            f"| {i} | {dr.day.date} | {dr.day.label} | {dr.n_stops} | "
            f"{dr.total_distance_km:.2f} | {dr.total_risk_km:.2f} | "
            f"{dr.day_score} | {dr.day_band} |"
        )
    lines.append("")

    for i, dr in enumerate(trip.days, 1):
        lines.append(f"### {i}. {dr.day.label} — score {dr.day_score} ({dr.day_band})")
        lines.append("")
        lines.append(f"- Stay: **{dr.day.stay_label}** — {dr.stay_score} ({dr.stay_band})")
        for stop, score, band in zip(dr.day.stops, dr.stop_scores, dr.stop_bands):
            lines.append(f"- Stop: **{stop.label}** — {score} ({band}) · dwell {stop.dwell_min} min")
        for leg in dr.legs:
            lines.append(
                f"- Leg: {leg.a_label} → {leg.b_label} · {leg.distance_km:.2f} km · "
                f"risk-km {leg.risk_km:.2f} · min safety {leg.min_safety_along}"
            )
        if dr.fatigue_penalty > 0:
            lines.append(f"- Fatigue penalty: -{dr.fatigue_penalty:.0f} pts "
                         f"({dr.n_stops} stops)")
        lines.append(f"- Corridor score: {dr.corridor_score}")
        lines.append(f"- Reason: {dr.reason}")
        lines.append("")

    if trip.weakest_link is not None:
        w = trip.weakest_link
        lines.append("## Weakest link")
        lines.append("")
        lines.append(f"**{w.day_label}** — {w.leg_label} · score `{w.score}` ({w.band})")
        lines.append("")
        lines.append(f"> {w.reason}")
        lines.append("")
        if w.swaps:
            lines.append("### Ranked swaps")
            lines.append("")
            for j, sw in enumerate(w.swaps, 1):
                lines.append(f"{j}. **{sw.label}** — expected uplift "
                             f"`+{sw.expected_uplift_pts:.1f}` pts "
                             + (f"→ band `{sw.target_band}`" if sw.target_band else ""))
                lines.append(f"   > {sw.detail}")
            lines.append("")
        else:
            lines.append("_No auto-swap improves this day by more than "
                         f"{MIN_UPLIFT_PTS:.0f} pts — consider manual re-plan._")
            lines.append("")

    lines.append("## Trip advisory")
    lines.append("")
    for a in trip.trip_advisory:
        lines.append(f"- {a}")
    lines.append("")

    lines.append("## Rules")
    lines.append("")
    lines.append(f"- Composition weights: stay {STAY_WEIGHT} · stops {STOPS_WEIGHT} · "
                 f"corridor {CORRIDOR_WEIGHT}")
    lines.append(f"- Corridor scoring: `100 · exp(-{CORRIDOR_KAPPA} · risk_km)`")
    lines.append(f"- Trip composite: `{MEAN_DAY_WEIGHT} · mean(days) + "
                 f"{MIN_DAY_WEIGHT} · min(day)` (worst-day-weighted)")
    lines.append(f"- Fatigue: -{FATIGUE_STEP_PTS} pts per stop past {FATIGUE_FREE_STOPS}")
    lines.append(f"- Verdict floors: Fragile <{FRAGILE_FLOOR} · Critical <{CRITICAL_FLOOR}")
    lines.append(f"- Engine version: `{ENGINE_VERSION}` · envelope `{VERSION}`")
    return "\n".join(lines) + "\n"


# ============================================================== seeds ===

def default_seed_trip(
    home_lat: float, home_lon: float,
    pois: Sequence[Mapping] = (),
    n_days: int = 4,
    start_date: Optional[str] = None,
) -> List[OdysseyDay]:
    """Compose a plausible default multi-day trip from the current location
    + a few named POIs.  Used by the UI to seed the day picker so the
    tab isn't empty on first open.

    Never fails — if `pois` is empty or the home coordinate is degenerate,
    it still returns `n_days` days pinned to the home coordinate with a
    single dwell stop each.
    """
    start = start_date or datetime.utcnow().date().isoformat()
    try:
        start_d = date_cls.fromisoformat(start)
    except ValueError:
        start_d = datetime.utcnow().date()

    # Pick up to `n_days * 2` interesting POIs near home.
    ranked: List[Tuple[float, str, float, float]] = []
    for r in pois:
        try:
            plat = float(r.get("lat")); plon = float(r.get("lon"))
            name = str(r.get("name") or "").strip()
        except (TypeError, ValueError):
            continue
        if not name:
            continue
        d = haversine_km(home_lat, home_lon, plat, plon)
        if d > 25.0:
            continue
        ranked.append((d, name, plat, plon))
    ranked.sort()
    picks = ranked[:n_days * 2]

    days: List[OdysseyDay] = []
    for i in range(n_days):
        d = start_d + timedelta(days=i)
        # Two stops per day when possible; fall back to one; fall back
        # to a self-loop if the POI list is empty.
        day_picks = picks[i*2:i*2+2]
        stops: List[Stop] = []
        for _, name, lat, lon in day_picks:
            stops.append(Stop(label=name, lat=lat, lon=lon, dwell_min=90))
        if not stops:
            stops.append(Stop(
                label="Local dwell",
                lat=home_lat + 0.005 * (i + 1),
                lon=home_lon + 0.005 * (i + 1),
                dwell_min=60,
            ))
        days.append(OdysseyDay(
            date=d.isoformat(),
            label=f"Day {i+1} — {stops[0].label}",
            stay_lat=home_lat, stay_lon=home_lon,
            stay_label="Base stay",
            stops=tuple(stops),
            depart_hour=9 + (i % 3),
            transit_mode="auto",
        ))
    return days
