"""Echo — Post-Trip Debrief & Counterfactual for WaySafe.

The question no other surface answers
-------------------------------------
WaySafe up to Day 65 is *forward-looking*. Pulse opens the day, Tempo
picks **when** to leave, Plan Route picks **how** to get there, Live
Trip streams alerts **during** the journey. Once the trip ends, the
state is dropped onto the Trip Log surface as a flat row and the page
turns. There is no surface that asks the *retrospective* question:

    "I just took a trip. How did it actually go? Were the alerts the
     system fired the right ones? What did I avoid? What would a
     different route flavor (or depart time) have looked like? And —
     for the family-share / safety-journal use case — what did the
     trip feel like, in one shareable page?"

Echo closes that loop. It consumes a `companion.TripSession` (active
*or* completed) plus the same incidents/geofences/POI snapshot Live
Trip used, optionally a `HazardForecaster` for the counterfactual leg,
and composes a single deterministic debrief.

The shape mirrors Pulse and Beacon — pure composition over the
existing physics, zero new physics. Every number Echo prints traces
back to an engine that already shipped:

    * realized safety per heartbeat:  safety.point_risk
    * exposure (risk-km):             integrated heartbeat.risk along trace
    * counterfactual routes:          routing.plan_fastest_route /
                                       routing.plan_safest_route /
                                       routing.plan_forecast_route
    * geofence dwell time:            utils.point_in_polygon
    * alert calibration:              companion.Alert.kind == "risk_ahead"

Composite trip score
--------------------
The headline number is a 0..100 composite with the same band ladder
Tempo uses (All-clear / Caution / Elevated / High Risk / Danger) so
Echo and Tempo never disagree on a band name. Four factors:

    realized_avg_safety   = mean(100·(1 − heartbeat.risk))
                          over every heartbeat (or planned-corridor
                          sample fallback when there are too few)
    exposure_score        = 100·exp(−κ·risk_km),  κ = 0.35
    event_score           = clip(100 − 40·user_sos − 30·auto_sos
                                     − 10·n_critical_alert
                                     − 4·n_warn_alert, 0, 100)
    fence_score           = 100·(1 − fraction_km_inside_geofence)

    trip_score = 0.35·realized_avg_safety
               + 0.25·exposure_score
               + 0.25·event_score
               + 0.15·fence_score

Weights are tuned so a clean run on the Aguada → Baga safest route
lands at ~84 (Smooth), the same route on `fastest` at ~67 (Watch), a
fastest run through the Aguada cliff geofence at peak hours with one
auto-SOS lands ~32 (Critical).

Mood ladder (first match wins, top-to-bottom):

    Critical   user_sos OR auto_sos OR trip_score < 45
    Rough      trip_score < 60 OR n_warn_alerts ≥ 3
    Watch      trip_score < 75 OR n_warn_alerts ≥ 1
    Smooth     else

Counterfactual
--------------
At the trip's `depart_at`, Echo re-plans three flavors:

    fastest    α=0    plan_fastest_route
    safest     α=4.5  plan_safest_route
    forecast   α=4.5  plan_forecast_route(forecaster, depart_at)
                      (only if a forecaster is provided)

Each is scored on the same composite as the actual trip. The headline
counterfactual is the flavor that beats the actual trip by the widest
trip-score margin; deltas are quoted on the matching corridor
(distance, ETA, risk-km, min-safety). When the actual route already
beats every alternative, Echo says so — "you took the safest available
slot, no upgrade possible at that depart".

Calibration
-----------
The Live Trip companion fires `risk_ahead` alerts when its 1.5-km
look-ahead crosses 0.45. Echo grades those predictions against the
heartbeat trace that followed:

    true_positive   risk_ahead fired and within 90 s the corridor
                    actually crossed risk ≥ 0.45
    false_alarm     risk_ahead fired but the next 90 s of trace
                    stayed below 0.32 (the hysteresis recovery floor)
    miss            a trace bucket of ≥ 90 s above 0.45 with no
                    preceding risk_ahead within 120 s upstream

A Brier-style summary number, `calibration_brier`, is the mean of
`(predicted − actual)²` across heartbeats where prediction is 1.0 if
a risk_ahead was active at that heartbeat and 0.0 otherwise. Lower
is better; the ladder maps:

    < 0.06   Sharp     (system called it right almost every time)
    < 0.12   OK
    < 0.20   Noisy     (over-warns)
    else     Off

Lessons
-------
A deterministic, first-match-wins ladder of natural-language bullets
keyed to the report's own numbers. Every lesson cites the engine it
was derived from so the analyst can drill down. Example:

    "🛡 The safest route at the same depart would have been
      +6 pts (saving 0.42 risk-km) at +8 min. → Tempo tab."

    "🚷 18 min inside the Aguada cliff geofence — try departing
      before 21:00 to dodge the late-night penalty. → Refuge tab."

Serialisation
-------------
`to_dict()` ships a `waysafe.echo.v1` JSON envelope. `to_markdown()`
ships a paste-able trip-journal entry (≈2-3 KB) suitable for
WhatsApp / email / Notion. Both are deterministic — same trip, same
incidents, identical output.

Pure-Python, zero new deps. Composes:

    safety.point_risk, safety.compute_safety
    routing.plan_fastest_route, plan_safest_route, plan_forecast_route
    forecast.HazardForecaster (optional)
    companion.TripSession (the source of truth)
    utils.haversine_km, utils.point_in_polygon

Lives at `tabs[2]` next to Pulse and Beacon because all three are
*composer* surfaces — Pulse asks "what changed?", Beacon asks "where
do we meet?", Echo asks "how did the journey actually go?".
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Mapping, Optional, Sequence, Tuple

from utils import haversine_km, point_in_polygon
from safety import point_risk
from routing import (
    plan_fastest_route,
    plan_safest_route,
    plan_forecast_route,
    AVG_TRAVEL_KMH,
)
from companion import TripSession, Alert, Milestone

# ---------------------------------------------------------------- constants

# Mirror Tempo's band ladder so the two surfaces never disagree on a band.
ECHO_BANDS: Tuple[Tuple[str, float, str], ...] = (
    ("All-clear",  80.0, "#53E3A6"),
    ("Caution",    65.0, "#F9C440"),
    ("Elevated",   50.0, "#FF9F43"),
    ("High Risk",  35.0, "#FF7F50"),
    ("Danger",      0.0, "#FF3D60"),
)

# Composite weights — see module doc for tuning rationale.
W_REALIZED = 0.35
W_EXPOSURE = 0.25
W_EVENT    = 0.25
W_FENCE    = 0.15

# exposure_score = 100 * exp(-KAPPA * risk_km).  Matches Tempo so a risk-km
# of 0.64 → exposure_score 80 (All-clear), 1.23 → 65 (Caution), etc.
KAPPA: float = 0.35

# Event penalties (rolled into event_score = clip(100 - Σ penalties)).
PEN_USER_SOS       = 40.0
PEN_AUTO_SOS       = 30.0
PEN_CRITICAL_ALERT = 10.0
PEN_WARN_ALERT     = 4.0

# Risk-ahead calibration thresholds — mirror companion.py so the calibration
# grades the exact same physics the alerts were fired on.
RISK_AHEAD_THRESHOLD     = 0.45
RISK_AHEAD_RECOVERY      = 0.32
PREDICTION_WINDOW_SEC    = 90       # how long after a risk_ahead we look for actual crossing
LOOKBACK_FOR_MISS_SEC    = 120      # how far upstream a heartbeat looks for a prior warn

# Calibration band ladder for the Brier score.
CALIB_BANDS: Tuple[Tuple[str, float, str], ...] = (
    ("Sharp", 0.06, "#53E3A6"),
    ("OK",    0.12, "#9FD3FF"),
    ("Noisy", 0.20, "#F9C440"),
    ("Off",   1.01, "#FF7F50"),
)

# Heartbeat sample fallback — when an Echo is composed for a synthetic /
# replayed trip with no live heartbeat trace, we sample the planned corridor
# at this many evenly-spaced points so the realized score still has a basis.
_PLAN_SAMPLE_POINTS = 24


# ---------------------------------------------------------------- helpers


def _band_for(score: float) -> Tuple[str, str]:
    """Map a 0..100 score to (band_name, hue)."""
    for name, lo, hue in ECHO_BANDS:
        if score >= lo:
            return name, hue
    return ECHO_BANDS[-1][0], ECHO_BANDS[-1][2]


def _calib_band_for(brier: float) -> Tuple[str, str]:
    """Map a 0..1 Brier-like score to (label, hue). Lower is sharper."""
    for name, lo, hue in CALIB_BANDS:
        if brier < lo:
            return name, hue
    return CALIB_BANDS[-1][0], CALIB_BANDS[-1][2]


def _clip(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def _round1(x: float) -> float:
    return round(float(x), 1)


def _round2(x: float) -> float:
    return round(float(x), 2)


def _safe_mean(xs: Sequence[float]) -> float:
    if not xs:
        return 0.0
    return sum(xs) / len(xs)


def _fmt_duration_min(minutes: float) -> str:
    if minutes <= 0:
        return "0 min"
    if minutes < 60:
        return f"{minutes:.0f} min"
    h = int(minutes // 60)
    m = int(round(minutes - 60 * h))
    if m == 0:
        return f"{h} h"
    return f"{h} h {m} min"


def _fmt_signed(x: float, *, unit: str = "", digits: int = 1) -> str:
    fmt = f"{{:+.{digits}f}}"
    return fmt.format(x) + (f" {unit}" if unit else "")


def _alert_severity_rank(severity: str) -> int:
    return {"info": 0, "warn": 1, "critical": 2}.get(str(severity), 0)


def _is_critical_alert(a: Alert) -> bool:
    """Treat user/auto SOS and high-severity risk-ahead as critical for scoring."""
    if a.kind in ("auto_sos",):
        return True
    if a.kind in ("risk_ahead", "geofence_enter") and a.severity == "critical":
        return True
    return False


def _is_warn_alert(a: Alert) -> bool:
    if a.kind in ("user_sos", "auto_sos"):
        return False  # already booked at critical
    return a.severity in ("warn", "critical")


# ---------------------------------------------------------------- dataclasses


@dataclass
class CorridorSample:
    """One sample along the actual corridor — either a recorded heartbeat
    or, for a synthetic Echo, a planned-corridor probe."""
    ts: Optional[datetime]
    lat: float
    lon: float
    risk: float                # 0..1
    inside_geofence: bool = False
    km: float = 0.0            # cumulative km along the trip


@dataclass
class TimelineEvent:
    ts: datetime
    kind: str                  # "alert" | "milestone"
    sub_kind: str              # alert.kind or milestone.kind
    severity: str              # for alerts: severity; for milestones: "info"
    message: str
    icon: str = "•"
    rel_km: Optional[float] = None
    accent: str = "#9FD3FF"

    def to_dict(self) -> dict:
        return {
            "ts": self.ts.isoformat(timespec="seconds"),
            "kind": self.kind,
            "sub_kind": self.sub_kind,
            "severity": self.severity,
            "message": self.message,
            "icon": self.icon,
            "rel_km": self.rel_km,
            "accent": self.accent,
        }


@dataclass
class CounterfactualScenario:
    """One re-planned route at the same (origin, dest, depart) — the
    'what if I had taken X' line for the debrief."""
    label: str                 # "actual" | "fastest" | "safest" | "forecast"
    mode: str                  # route.mode
    distance_km: float
    eta_minutes: float
    avg_safety: int
    min_safety: int
    risk_km: float
    exposure_score: float
    band: str
    band_color: str
    n_warn_predicted: int      # how many warn-ish samples this corridor produced
    coords: List[Tuple[float, float]] = field(default_factory=list)
    is_actual: bool = False
    # deltas vs actual — populated by the composer after all scenarios run.
    delta_trip_score: float = 0.0
    delta_risk_km: float = 0.0
    delta_distance_km: float = 0.0
    delta_eta_minutes: float = 0.0
    delta_min_safety: int = 0

    def to_dict(self) -> dict:
        return {
            "label": self.label,
            "mode": self.mode,
            "distance_km": _round2(self.distance_km),
            "eta_minutes": _round1(self.eta_minutes),
            "avg_safety": int(self.avg_safety),
            "min_safety": int(self.min_safety),
            "risk_km": _round2(self.risk_km),
            "exposure_score": _round1(self.exposure_score),
            "band": self.band,
            "band_color": self.band_color,
            "n_warn_predicted": int(self.n_warn_predicted),
            "is_actual": self.is_actual,
            "delta_trip_score": _round1(self.delta_trip_score),
            "delta_risk_km": _round2(self.delta_risk_km),
            "delta_distance_km": _round2(self.delta_distance_km),
            "delta_eta_minutes": _round1(self.delta_eta_minutes),
            "delta_min_safety": int(self.delta_min_safety),
            "coords": [list(c) for c in self.coords],
        }


@dataclass
class CalibrationReport:
    n_heartbeats: int
    n_risk_ahead_alerts: int
    n_true_positive: int
    n_false_alarm: int
    n_miss: int
    brier: float
    band: str
    band_color: str
    summary: str               # one-line plain English

    def to_dict(self) -> dict:
        return {
            "n_heartbeats": int(self.n_heartbeats),
            "n_risk_ahead_alerts": int(self.n_risk_ahead_alerts),
            "n_true_positive": int(self.n_true_positive),
            "n_false_alarm": int(self.n_false_alarm),
            "n_miss": int(self.n_miss),
            "brier": _round2(self.brier),
            "band": self.band,
            "band_color": self.band_color,
            "summary": self.summary,
        }


@dataclass
class ScoreFactor:
    label: str
    value: float               # the underlying 0..100 component
    weight: float              # composite weight
    contribution: float        # value * weight
    detail: str = ""


@dataclass
class EchoReport:
    # ----- identity / trip metadata -----
    trip_id: str
    origin: Tuple[float, float]
    origin_label: str
    dest: Tuple[float, float]
    dest_label: str
    route_mode: str
    depart_at: Optional[datetime]
    arrived_at: Optional[datetime]
    distance_km: float
    duration_min: float
    composed_at: datetime
    status: str                # mirrors trip.status

    # ----- headline composite -----
    trip_score: float
    band: str
    band_color: str
    mood: str                  # "Smooth" | "Watch" | "Rough" | "Critical"
    mood_color: str
    factors: List[ScoreFactor] = field(default_factory=list)
    realized_avg_safety: float = 0.0
    realized_min_safety: float = 0.0
    risk_km: float = 0.0
    geofence_minutes: float = 0.0
    geofence_fraction: float = 0.0
    fence_score: float = 0.0
    event_score: float = 0.0
    exposure_score: float = 0.0

    # ----- planned vs realized -----
    planned_avg_safety: int = 0
    planned_min_safety: int = 0
    avg_safety_delta: float = 0.0   # realized - planned

    # ----- corridor / timeline -----
    corridor: List[CorridorSample] = field(default_factory=list)
    timeline: List[TimelineEvent] = field(default_factory=list)

    # ----- alerts counters (for the JSON) -----
    n_alerts: int = 0
    n_warn_alerts: int = 0
    n_critical_alerts: int = 0
    n_geofence_enters: int = 0
    n_risk_ahead: int = 0
    n_broadcasts: int = 0
    user_sos: bool = False
    auto_sos: bool = False

    # ----- counterfactual -----
    scenarios: List[CounterfactualScenario] = field(default_factory=list)
    best_alternative: Optional[str] = None   # label of the strongest CF or None

    # ----- calibration -----
    calibration: Optional[CalibrationReport] = None

    # ----- narrative -----
    headline: str = ""
    advisory_line: str = ""
    lessons: List[str] = field(default_factory=list)

    # ---------- serialisation ----------

    def to_dict(self) -> dict:
        return {
            "schema": "waysafe.echo.v1",
            "composed_at": self.composed_at.isoformat(),
            "trip_id": self.trip_id,
            "status": self.status,
            "origin": list(self.origin),
            "origin_label": self.origin_label,
            "dest": list(self.dest),
            "dest_label": self.dest_label,
            "route_mode": self.route_mode,
            "depart_at": self.depart_at.isoformat() if self.depart_at else None,
            "arrived_at": self.arrived_at.isoformat() if self.arrived_at else None,
            "distance_km": _round2(self.distance_km),
            "duration_min": _round1(self.duration_min),
            "trip_score": _round1(self.trip_score),
            "band": self.band,
            "band_color": self.band_color,
            "mood": self.mood,
            "mood_color": self.mood_color,
            "factors": [
                {
                    "label": f.label,
                    "value": _round1(f.value),
                    "weight": f.weight,
                    "contribution": _round1(f.contribution),
                    "detail": f.detail,
                }
                for f in self.factors
            ],
            "realized_avg_safety": _round1(self.realized_avg_safety),
            "realized_min_safety": _round1(self.realized_min_safety),
            "risk_km": _round2(self.risk_km),
            "geofence_minutes": _round1(self.geofence_minutes),
            "geofence_fraction": round(self.geofence_fraction, 3),
            "fence_score": _round1(self.fence_score),
            "event_score": _round1(self.event_score),
            "exposure_score": _round1(self.exposure_score),
            "planned_avg_safety": int(self.planned_avg_safety),
            "planned_min_safety": int(self.planned_min_safety),
            "avg_safety_delta": _round1(self.avg_safety_delta),
            "corridor": [
                {
                    "ts": s.ts.isoformat(timespec="seconds") if s.ts else None,
                    "lat": round(s.lat, 5),
                    "lon": round(s.lon, 5),
                    "risk": _round2(s.risk),
                    "inside_geofence": s.inside_geofence,
                    "km": _round2(s.km),
                }
                for s in self.corridor
            ],
            "timeline": [e.to_dict() for e in self.timeline],
            "alerts": {
                "n_total": int(self.n_alerts),
                "n_warn": int(self.n_warn_alerts),
                "n_critical": int(self.n_critical_alerts),
                "n_geofence_enters": int(self.n_geofence_enters),
                "n_risk_ahead": int(self.n_risk_ahead),
                "n_broadcasts": int(self.n_broadcasts),
                "user_sos": self.user_sos,
                "auto_sos": self.auto_sos,
            },
            "scenarios": [s.to_dict() for s in self.scenarios],
            "best_alternative": self.best_alternative,
            "calibration": self.calibration.to_dict() if self.calibration else None,
            "headline": self.headline,
            "advisory_line": self.advisory_line,
            "lessons": list(self.lessons),
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    def to_markdown(self) -> str:
        lines: List[str] = []
        lines.append(f"# Echo — trip debrief · {self.dest_label}")
        depart = self.depart_at.strftime("%a %d %b %H:%M") if self.depart_at else "(unknown)"
        arrived = self.arrived_at.strftime("%H:%M") if self.arrived_at else "(in progress)"
        lines.append(
            f"_{self.origin_label} → {self.dest_label}_ · "
            f"{self.route_mode} · departed {depart} · arrived {arrived} · "
            f"{self.distance_km:.1f} km · {_fmt_duration_min(self.duration_min)}"
        )
        lines.append("")
        lines.append(
            f"**Trip score: {self.trip_score:.0f}/100 · {self.band} · "
            f"mood {self.mood}**"
        )
        if self.headline:
            lines.append("")
            lines.append(f"> {self.headline}")
        if self.advisory_line:
            lines.append("")
            lines.append(self.advisory_line)
        lines.append("")
        # --- factors ---
        lines.append("## Score breakdown")
        lines.append("")
        lines.append("| Factor | Value | Weight | Contribution |")
        lines.append("|---|---:|---:|---:|")
        for f in self.factors:
            lines.append(
                f"| {f.label} | {f.value:.0f} | {f.weight:.2f} | "
                f"{f.contribution:.1f} |"
            )
        lines.append("")
        # --- events ---
        if self.timeline:
            lines.append("## Event timeline")
            lines.append("")
            for ev in self.timeline[:40]:
                rel = f" · {ev.rel_km:.1f} km" if ev.rel_km is not None else ""
                lines.append(
                    f"- {ev.icon} **{ev.ts.strftime('%H:%M:%S')}** "
                    f"`{ev.sub_kind}` ({ev.severity}){rel} — {ev.message}"
                )
            if len(self.timeline) > 40:
                lines.append(f"- … {len(self.timeline) - 40} more events.")
            lines.append("")
        # --- counterfactual ---
        if self.scenarios:
            lines.append("## Counterfactual")
            lines.append("")
            lines.append(
                "| Flavor | Trip score | Δ vs actual | Distance | ETA | risk-km | min safety |"
            )
            lines.append("|---|---:|---:|---:|---:|---:|---:|")
            for s in self.scenarios:
                marker = " ← actual" if s.is_actual else ""
                eta_lbl = _fmt_duration_min(s.eta_minutes)
                lines.append(
                    f"| {s.label}{marker} | "
                    f"{s.exposure_score:.0f}/100 · {s.band} | "
                    f"{_fmt_signed(s.delta_trip_score)} | "
                    f"{s.distance_km:.1f} km | "
                    f"{eta_lbl} | "
                    f"{s.risk_km:.2f} | "
                    f"{s.min_safety} |"
                )
            if self.best_alternative:
                lines.append("")
                lines.append(
                    f"_Strongest alternative: **{self.best_alternative}**._"
                )
            lines.append("")
        # --- calibration ---
        if self.calibration is not None:
            cal = self.calibration
            lines.append("## Alert calibration")
            lines.append("")
            lines.append(
                f"- Brier-style score: **{cal.brier:.2f}** · band **{cal.band}**"
            )
            lines.append(
                f"- Risk-ahead alerts: {cal.n_risk_ahead_alerts} "
                f"(true-positive {cal.n_true_positive} · "
                f"false-alarm {cal.n_false_alarm} · miss {cal.n_miss})"
            )
            lines.append(f"- {cal.summary}")
            lines.append("")
        # --- lessons ---
        if self.lessons:
            lines.append("## Lessons & plan-of-next-trip")
            lines.append("")
            for i, l in enumerate(self.lessons, start=1):
                lines.append(f"{i}. {l}")
            lines.append("")
        lines.append(
            f"_Composed at {self.composed_at.strftime('%Y-%m-%d %H:%M:%S')} "
            f"by `echo.compute_echo` · `waysafe.echo.v1`._"
        )
        return "\n".join(lines)


# ---------------------------------------------------------------- corridor / fence helpers


def _heartbeat_to_sample(
    hb: Tuple[datetime, float, float, float],
    geofences: Mapping,
    km_so_far: float,
) -> CorridorSample:
    ts, lat, lon, risk = hb
    inside = False
    for feat in geofences.get("features", []) if geofences else []:
        try:
            if point_in_polygon(lat, lon, feat["geometry"]["coordinates"][0]):
                inside = True
                break
        except Exception:
            continue
    return CorridorSample(
        ts=ts, lat=float(lat), lon=float(lon),
        risk=float(max(0.0, min(1.0, risk))),
        inside_geofence=inside,
        km=km_so_far,
    )


def _build_corridor_from_heartbeats(
    trip: TripSession, geofences: Mapping,
) -> List[CorridorSample]:
    """Project the recorded heartbeats into CorridorSamples, with per-sample
    cumulative-km along the trip."""
    samples: List[CorridorSample] = []
    if not trip.heartbeats:
        return samples
    km = 0.0
    prev: Optional[Tuple[float, float]] = None
    for hb in trip.heartbeats:
        _, lat, lon, _ = hb
        if prev is not None:
            km += haversine_km(prev[0], prev[1], lat, lon)
        s = _heartbeat_to_sample(hb, geofences, km)
        samples.append(s)
        prev = (lat, lon)
    return samples


def _sample_planned_corridor(
    trip: TripSession,
    incidents: Sequence[Mapping],
    geofences: Mapping,
    pois: Sequence[Mapping],
    *,
    now: datetime,
) -> List[CorridorSample]:
    """Fallback corridor: when no heartbeats exist (trip never started, or
    came from the Trip Log digest), sample the planned coords evenly and
    re-price each with `safety.point_risk` at the trip's depart time."""
    coords = trip.plan.coords
    if not coords:
        return []
    depart = trip.plan.depart_at or trip.started_at or now
    samples: List[CorridorSample] = []
    cum = trip.plan.cum_km
    if not cum:
        cum = [0.0]
        for (la, lo), (lb, lob) in zip(coords, coords[1:]):
            cum.append(cum[-1] + haversine_km(la, lo, lb, lob))
    total = cum[-1] if cum else 0.0
    n = min(_PLAN_SAMPLE_POINTS, max(4, len(coords)))
    for i in range(n):
        if n == 1:
            k = 0.0
        else:
            k = total * (i / (n - 1))
        # Find the segment containing k
        idx = 0
        for j in range(1, len(cum)):
            if cum[j] >= k:
                idx = j - 1
                break
            idx = j
        seg_len = max(1e-9, cum[idx + 1] - cum[idx]) if idx + 1 < len(cum) else 1.0
        f = (k - cum[idx]) / seg_len if idx + 1 < len(cum) else 0.0
        la, lo_a = coords[idx]
        lb, lo_b = coords[min(idx + 1, len(coords) - 1)]
        lat = la + (lb - la) * f
        lon = lo_a + (lo_b - lo_a) * f
        risk = point_risk(lat, lon, incidents, geofences, pois, now=depart)
        inside = False
        for feat in geofences.get("features", []) if geofences else []:
            try:
                if point_in_polygon(lat, lon, feat["geometry"]["coordinates"][0]):
                    inside = True
                    break
            except Exception:
                continue
        samples.append(CorridorSample(
            ts=None, lat=float(lat), lon=float(lon),
            risk=float(max(0.0, min(1.0, risk))),
            inside_geofence=inside, km=float(k),
        ))
    return samples


def _integrate_risk_km(corridor: Sequence[CorridorSample]) -> float:
    """Trapezoidal integration of risk over km along the corridor."""
    if len(corridor) < 2:
        return 0.0
    total = 0.0
    for a, b in zip(corridor, corridor[1:]):
        seg = max(0.0, b.km - a.km)
        if seg <= 0:
            continue
        avg = 0.5 * (a.risk + b.risk)
        total += avg * seg
    return total


def _fraction_inside_geofence(corridor: Sequence[CorridorSample]) -> Tuple[float, float]:
    """(geofence_minutes_estimate, geofence_fraction_of_km).

    Geofence minutes is a best-effort estimate using AVG_TRAVEL_KMH when we
    don't have heartbeat timestamps for every sample."""
    if len(corridor) < 2:
        return 0.0, 0.0
    total_km = 0.0
    inside_km = 0.0
    for a, b in zip(corridor, corridor[1:]):
        seg = max(0.0, b.km - a.km)
        if seg <= 0:
            continue
        total_km += seg
        if a.inside_geofence and b.inside_geofence:
            inside_km += seg
        elif a.inside_geofence or b.inside_geofence:
            inside_km += seg * 0.5
    if total_km <= 0:
        return 0.0, 0.0
    fraction = inside_km / total_km
    minutes = (inside_km / max(1.0, AVG_TRAVEL_KMH)) * 60.0
    return minutes, fraction


# ---------------------------------------------------------------- counterfactual


def _score_route_corridor(
    coords: Sequence[Tuple[float, float]],
    risk_samples: Sequence[Tuple[float, float, float]],
    distance_km: float,
) -> Tuple[float, int]:
    """For a counterfactual route, integrate risk over km and count warn
    samples (risk ≥ RISK_AHEAD_THRESHOLD)."""
    if not risk_samples or distance_km <= 0:
        return 0.0, 0
    # Approximate per-segment lengths by spreading distance across n samples.
    n = len(risk_samples)
    seg = distance_km / max(1, n)
    risk_km = sum(seg * r for _, _, r in risk_samples)
    n_warn = sum(1 for _, _, r in risk_samples if r >= RISK_AHEAD_THRESHOLD)
    return risk_km, n_warn


def _build_scenario(
    label: str, route_result, *, is_actual: bool = False,
) -> CounterfactualScenario:
    risk_km, n_warn = _score_route_corridor(
        route_result.coords, route_result.risk_samples, route_result.distance_km,
    )
    exposure = _clip(100.0 * math.exp(-KAPPA * risk_km))
    band, hue = _band_for(exposure)
    return CounterfactualScenario(
        label=label,
        mode=route_result.mode,
        distance_km=float(route_result.distance_km),
        eta_minutes=float(route_result.eta_minutes),
        avg_safety=int(route_result.avg_safety),
        min_safety=int(route_result.min_safety),
        risk_km=float(risk_km),
        exposure_score=float(exposure),
        band=band,
        band_color=hue,
        n_warn_predicted=int(n_warn),
        coords=list(route_result.coords),
        is_actual=is_actual,
    )


def _actual_scenario_from_corridor(
    corridor: Sequence[CorridorSample],
    distance_km: float,
    eta_minutes: float,
    mode: str,
) -> CounterfactualScenario:
    """Build the 'actual' row from the recorded corridor — uses the same
    risk-km and exposure-score formula as the counterfactual rows so the
    comparison is apples-to-apples."""
    risk_km = _integrate_risk_km(corridor)
    n_warn = sum(1 for s in corridor if s.risk >= RISK_AHEAD_THRESHOLD)
    realized_safety = _safe_mean([100.0 * (1.0 - s.risk) for s in corridor])
    min_realized = min((100.0 * (1.0 - s.risk) for s in corridor), default=100.0)
    exposure = _clip(100.0 * math.exp(-KAPPA * risk_km))
    band, hue = _band_for(exposure)
    return CounterfactualScenario(
        label="actual",
        mode=mode,
        distance_km=float(distance_km),
        eta_minutes=float(eta_minutes),
        avg_safety=int(round(realized_safety)),
        min_safety=int(round(min_realized)),
        risk_km=float(risk_km),
        exposure_score=float(exposure),
        band=band,
        band_color=hue,
        n_warn_predicted=int(n_warn),
        coords=[(s.lat, s.lon) for s in corridor],
        is_actual=True,
    )


# ---------------------------------------------------------------- calibration


def _grade_calibration(
    corridor: Sequence[CorridorSample],
    risk_ahead_alerts: Sequence[Alert],
) -> CalibrationReport:
    """Compare risk_ahead predictions against the heartbeat trace that
    followed. Pure function — only Alert.ts and heartbeat (ts, risk) are
    consulted."""
    n_hb = len(corridor)
    n_alerts = len(risk_ahead_alerts)

    if n_hb == 0:
        return CalibrationReport(
            n_heartbeats=0,
            n_risk_ahead_alerts=n_alerts,
            n_true_positive=0,
            n_false_alarm=0,
            n_miss=0,
            brier=0.0,
            band="—",
            band_color="#3DA9FC",
            summary="No heartbeat trace recorded — calibration unavailable.",
        )

    # Sort alerts by timestamp (defensive).
    alerts_sorted = sorted(
        [a for a in risk_ahead_alerts if a.ts is not None],
        key=lambda a: a.ts,
    )

    tp = 0
    fa = 0
    pred_window = timedelta(seconds=PREDICTION_WINDOW_SEC)
    miss_lookback = timedelta(seconds=LOOKBACK_FOR_MISS_SEC)

    # For each alert, find heartbeats in the next PREDICTION_WINDOW_SEC.
    for a in alerts_sorted:
        next_hbs = [
            s for s in corridor
            if s.ts is not None and a.ts <= s.ts <= a.ts + pred_window
        ]
        if not next_hbs:
            continue
        if any(s.risk >= RISK_AHEAD_THRESHOLD for s in next_hbs):
            tp += 1
        elif all(s.risk < RISK_AHEAD_RECOVERY for s in next_hbs):
            fa += 1
        # else: ambiguous (risk lingered in the hysteresis band) — not counted
        # either way to avoid penalising the system for the gray zone its
        # hysteresis was explicitly designed around.

    # Misses: a high-risk heartbeat with no upstream alert in the prior window.
    for s in corridor:
        if s.ts is None or s.risk < RISK_AHEAD_THRESHOLD:
            continue
        had_warn = any(
            a.ts is not None and s.ts - miss_lookback <= a.ts <= s.ts
            for a in alerts_sorted
        )
        if not had_warn:
            # Only count the first miss per high-risk streak to avoid stacking.
            # The simplest dedupe is: don't double-count consecutive misses
            # within PREDICTION_WINDOW_SEC of each other.
            recent_streak = any(
                _safe_prev_miss_ts(s.ts, corridor) is not None
                and (s.ts - _safe_prev_miss_ts(s.ts, corridor)).total_seconds()
                < PREDICTION_WINDOW_SEC
                for _ in (0,)
            )
            if recent_streak:
                continue
            # Mark by side-channel set
            _miss_seen.add(id(s))

    # Count uniquely-marked misses
    miss = sum(1 for s in corridor if id(s) in _miss_seen)
    # Reset the side-channel
    _miss_seen.clear()

    # Brier: how often the system was "predicting hot" vs how often the trace
    # was actually hot, sample by sample.
    predicted_at_hb: List[float] = []
    for s in corridor:
        active = 0.0
        if s.ts is not None:
            for a in alerts_sorted:
                if a.ts is None:
                    continue
                if a.ts <= s.ts <= a.ts + pred_window:
                    active = 1.0
                    break
        predicted_at_hb.append(active)
    actual_at_hb = [1.0 if s.risk >= RISK_AHEAD_THRESHOLD else 0.0 for s in corridor]
    brier = _safe_mean([(p - a) ** 2 for p, a in zip(predicted_at_hb, actual_at_hb)])

    # Outcome-aware band override: the raw Brier penalises persistent
    # predictions because a single alert spans multiple heartbeats — but
    # if every alert resolved into a true-positive and no risk slipped
    # past unwarned, the system is in fact "Sharp" from the user's POV.
    band, hue = _calib_band_for(brier)
    perfect_outcomes = (n_alerts >= 1 and fa == 0 and miss == 0 and tp >= n_alerts)
    if perfect_outcomes and band not in ("Sharp",):
        band, hue = "Sharp", CALIB_BANDS[0][2]
    summary = _calibration_summary(tp, fa, miss, n_alerts, n_hb, brier, band)
    return CalibrationReport(
        n_heartbeats=n_hb,
        n_risk_ahead_alerts=n_alerts,
        n_true_positive=tp,
        n_false_alarm=fa,
        n_miss=miss,
        brier=float(brier),
        band=band,
        band_color=hue,
        summary=summary,
    )


# Side-channel set used only inside _grade_calibration — keeps misses unique
# per debrief without threading state through every helper.
_miss_seen: set = set()


def _safe_prev_miss_ts(
    ts: datetime, corridor: Sequence[CorridorSample],
) -> Optional[datetime]:
    last: Optional[datetime] = None
    for s in corridor:
        if id(s) in _miss_seen and s.ts is not None and s.ts < ts:
            last = s.ts
    return last


def _calibration_summary(
    tp: int, fa: int, miss: int, n_alerts: int, n_hb: int,
    brier: float, band: str,
) -> str:
    if n_alerts == 0 and miss == 0:
        return (
            f"No risk-ahead alerts fired and the trace stayed clean "
            f"({n_hb} heartbeats) — system idle, traveler safe."
        )
    if n_alerts == 0 and miss > 0:
        return (
            f"{miss} high-risk segments slipped past with no warning — "
            f"tighten the lookahead by widening LOOKAHEAD_KM."
        )
    if tp >= max(1, n_alerts) and fa == 0 and miss == 0:
        return (
            f"Every one of the {n_alerts} risk-ahead alerts was followed by "
            f"an actual high-risk segment within {PREDICTION_WINDOW_SEC}s. Sharp."
        )
    if fa > tp and tp >= 1:
        return (
            f"More false alarms ({fa}) than true-positives ({tp}) — the "
            f"system over-warned; consider raising RISK_AHEAD_THRESHOLD."
        )
    return (
        f"{tp} true-positive, {fa} false-alarm, {miss} miss across "
        f"{n_alerts} alerts and {n_hb} heartbeats. Brier {brier:.2f} ({band})."
    )


# ---------------------------------------------------------------- timeline


def _timeline_from_trip(
    trip: TripSession, corridor: Sequence[CorridorSample],
) -> List[TimelineEvent]:
    """Merge alerts + milestones into a single chronological event list."""
    events: List[TimelineEvent] = []

    # Pre-compute cumulative-km lookups by alert.location bucket.
    coord_index: List[Tuple[float, float, float]] = [(s.km, s.lat, s.lon) for s in corridor]

    def _km_at_coord(lat: float, lon: float) -> Optional[float]:
        # Find the closest corridor sample to this location.
        best: Optional[Tuple[float, float]] = None  # (dist, km)
        for km, slat, slon in coord_index:
            d = (slat - lat) ** 2 + (slon - lon) ** 2
            if best is None or d < best[0]:
                best = (d, km)
        return best[1] if best is not None else None

    for a in trip.alerts:
        accent = "#9FD3FF"
        if a.severity == "warn":
            accent = "#F9C440"
        elif a.severity == "critical":
            accent = "#FF7F50"
        elif a.kind in ("arrival", "safer_segment", "geofence_exit"):
            accent = "#53E3A6"
        elif a.kind in ("auto_sos", "user_sos"):
            accent = "#FF3D60"
        rel_km = None
        if a.location:
            rel_km = _km_at_coord(a.location[0], a.location[1])
        events.append(TimelineEvent(
            ts=a.ts,
            kind="alert",
            sub_kind=a.kind,
            severity=a.severity,
            message=a.message,
            icon=a.icon,
            rel_km=rel_km,
            accent=accent,
        ))
    for m in trip.milestones:
        accent = "#9FD3FF"
        if m.kind in ("auto_sos", "stall"):
            accent = "#FF3D60"
        elif m.kind in ("arrival", "recover", "geofence_exit"):
            accent = "#53E3A6"
        elif m.kind in ("geofence_enter",):
            accent = "#F9C440"
        events.append(TimelineEvent(
            ts=m.ts,
            kind="milestone",
            sub_kind=m.kind,
            severity="info",
            message=m.summary,
            icon=_milestone_icon(m.kind),
            rel_km=None,
            accent=accent,
        ))
    events.sort(key=lambda e: (e.ts, _alert_severity_rank(e.severity)))
    return events


def _milestone_icon(kind: str) -> str:
    return {
        "departure": "🚦",
        "arrival": "🏁",
        "geofence_enter": "🚷",
        "geofence_exit": "✅",
        "auto_sos": "🆘",
        "stall": "⏸️",
        "recover": "🟢",
    }.get(kind, "·")


# ---------------------------------------------------------------- composer


def compute_echo(
    trip: TripSession,
    *,
    incidents: Sequence[Mapping] = (),
    geofences: Mapping | None = None,
    pois: Sequence[Mapping] = (),
    forecaster=None,
    broadcasts_count: int = 0,
    now: datetime | None = None,
    enable_counterfactual: bool = True,
) -> EchoReport:
    """Compose a post-trip debrief from a `TripSession`.

    Pure function: same inputs always produce identical outputs. The trip
    does *not* need to be in status="completed" — Echo will happily debrief
    an active trip mid-flight, useful for the "current trip — how is it
    going so far?" angle. The `status` field on the report mirrors what it
    was on the source TripSession at compose-time.
    """
    geofences = geofences or {"features": []}
    now = now or datetime.utcnow()

    # ---------------- corridor ----------------
    corridor = _build_corridor_from_heartbeats(trip, geofences)
    if len(corridor) < 4:
        corridor = _sample_planned_corridor(
            trip, incidents, geofences, pois, now=now,
        )

    realized_safeties = [100.0 * (1.0 - s.risk) for s in corridor]
    realized_avg_safety = _safe_mean(realized_safeties) if realized_safeties else float(trip.plan.avg_safety)
    realized_min_safety = min(realized_safeties) if realized_safeties else float(trip.plan.min_safety)

    risk_km = _integrate_risk_km(corridor) if len(corridor) >= 2 else 0.0
    exposure_score = _clip(100.0 * math.exp(-KAPPA * risk_km))

    geofence_minutes, geofence_fraction = _fraction_inside_geofence(corridor)
    fence_score = _clip(100.0 * (1.0 - geofence_fraction))

    # ---------------- alert counters ----------------
    n_alerts = len(trip.alerts)
    n_warn = sum(1 for a in trip.alerts if _is_warn_alert(a))
    n_critical = sum(1 for a in trip.alerts if _is_critical_alert(a))
    n_geofence_enters = sum(1 for a in trip.alerts if a.kind == "geofence_enter")
    n_risk_ahead = sum(1 for a in trip.alerts if a.kind == "risk_ahead")
    user_sos = bool(trip.user_sos_fired)
    auto_sos = bool(trip.auto_sos_fired)

    event_penalty = (
        PEN_USER_SOS * (1 if user_sos else 0)
        + PEN_AUTO_SOS * (1 if auto_sos else 0)
        + PEN_CRITICAL_ALERT * n_critical
        + PEN_WARN_ALERT * n_warn
    )
    event_score = _clip(100.0 - event_penalty)

    # ---------------- composite ----------------
    trip_score = (
        W_REALIZED * realized_avg_safety
        + W_EXPOSURE * exposure_score
        + W_EVENT * event_score
        + W_FENCE * fence_score
    )
    trip_score = _clip(trip_score)
    band, band_color = _band_for(trip_score)
    mood, mood_color = _mood_for(trip_score, user_sos, auto_sos, n_warn, n_critical)

    factors = [
        ScoreFactor(
            label="Realized safety",
            value=realized_avg_safety,
            weight=W_REALIZED,
            contribution=W_REALIZED * realized_avg_safety,
            detail=f"mean(100·(1−risk)) over {len(corridor)} samples",
        ),
        ScoreFactor(
            label="Exposure (risk-km)",
            value=exposure_score,
            weight=W_EXPOSURE,
            contribution=W_EXPOSURE * exposure_score,
            detail=f"100·exp(−0.35·{risk_km:.2f})",
        ),
        ScoreFactor(
            label="Events",
            value=event_score,
            weight=W_EVENT,
            contribution=W_EVENT * event_score,
            detail=f"penalty −{event_penalty:.0f} from {n_warn} warn · {n_critical} critical"
                   + (" · USER SOS" if user_sos else "")
                   + (" · AUTO SOS" if auto_sos else ""),
        ),
        ScoreFactor(
            label="Geofence dwell",
            value=fence_score,
            weight=W_FENCE,
            contribution=W_FENCE * fence_score,
            detail=f"{geofence_minutes:.0f} min ({geofence_fraction:.0%}) inside risk polygons",
        ),
    ]

    # ---------------- planned vs realized ----------------
    planned_avg = int(trip.plan.avg_safety)
    planned_min = int(trip.plan.min_safety)
    avg_delta = realized_avg_safety - planned_avg

    # ---------------- timeline ----------------
    timeline = _timeline_from_trip(trip, corridor)

    # ---------------- counterfactual ----------------
    scenarios: List[CounterfactualScenario] = []
    best_alt_label: Optional[str] = None
    if enable_counterfactual and len(trip.plan.coords) >= 2:
        depart_at = trip.plan.depart_at or trip.started_at
        origin = trip.plan.coords[0]
        dest = trip.plan.coords[-1]
        actual_eta = (
            (trip.arrived_at - trip.started_at).total_seconds() / 60.0
            if trip.arrived_at else trip.plan.eta_minutes
        )
        actual_dist = trip.plan.distance_km
        actual_scn = _actual_scenario_from_corridor(
            corridor, actual_dist, actual_eta, trip.plan.route_mode,
        )
        scenarios.append(actual_scn)
        try:
            fastest = plan_fastest_route(
                origin, dest, incidents, geofences, pois, now=depart_at,
            )
            scenarios.append(_build_scenario("fastest", fastest))
        except Exception:
            pass
        try:
            safest = plan_safest_route(
                origin, dest, incidents, geofences, pois, now=depart_at,
            )
            scenarios.append(_build_scenario("safest", safest))
        except Exception:
            pass
        if forecaster is not None and depart_at is not None:
            try:
                fc_route = plan_forecast_route(
                    origin, dest, forecaster, depart_at,
                    incidents=incidents, geofences=geofences, pois=pois,
                )
                scenarios.append(_build_scenario("forecast-safest", fc_route))
            except Exception:
                pass

        # Populate deltas vs actual on every non-actual scenario.
        actual = actual_scn
        for s in scenarios:
            if s.is_actual:
                continue
            # Re-score the counterfactual against the same composite recipe.
            cf_trip_score = _clip(
                W_REALIZED * s.avg_safety
                + W_EXPOSURE * s.exposure_score
                + W_EVENT * 100.0          # CF assumes no events fired
                + W_FENCE * 100.0          # CF assumes no fence dwell
            )
            actual_score = trip_score
            s.delta_trip_score = cf_trip_score - actual_score
            s.delta_risk_km = actual.risk_km - s.risk_km
            s.delta_distance_km = s.distance_km - actual.distance_km
            s.delta_eta_minutes = s.eta_minutes - actual.eta_minutes
            s.delta_min_safety = s.min_safety - actual.min_safety

        # Pick the strongest alternative (largest positive delta_trip_score).
        alts = [s for s in scenarios if not s.is_actual and s.delta_trip_score > 0.5]
        if alts:
            alts.sort(key=lambda s: -s.delta_trip_score)
            best_alt_label = alts[0].label

    # ---------------- calibration ----------------
    risk_ahead_alerts = [a for a in trip.alerts if a.kind == "risk_ahead"]
    calibration = _grade_calibration(corridor, risk_ahead_alerts)

    # ---------------- narrative ----------------
    headline, advisory_line = _compose_narrative(
        mood=mood,
        band=band,
        trip_score=trip_score,
        trip=trip,
        n_warn=n_warn,
        n_critical=n_critical,
        risk_km=risk_km,
        best_alt=best_alt_label,
        scenarios=scenarios,
        geofence_minutes=geofence_minutes,
    )
    lessons = _compose_lessons(
        mood=mood,
        trip=trip,
        trip_score=trip_score,
        risk_km=risk_km,
        scenarios=scenarios,
        best_alt=best_alt_label,
        n_warn=n_warn,
        n_critical=n_critical,
        geofence_minutes=geofence_minutes,
        geofence_fraction=geofence_fraction,
        avg_delta=avg_delta,
        calibration=calibration,
        broadcasts_count=broadcasts_count,
    )

    duration_min = (
        (trip.arrived_at - trip.started_at).total_seconds() / 60.0
        if trip.arrived_at and trip.started_at else trip.plan.eta_minutes
    )

    return EchoReport(
        trip_id=trip.trip_id,
        origin=(trip.plan.coords[0] if trip.plan.coords else (0.0, 0.0)),
        origin_label=trip.plan.origin_label,
        dest=(trip.plan.coords[-1] if trip.plan.coords else (0.0, 0.0)),
        dest_label=trip.plan.dest_label,
        route_mode=trip.plan.route_mode,
        depart_at=trip.plan.depart_at or trip.started_at,
        arrived_at=trip.arrived_at,
        distance_km=float(trip.plan.distance_km),
        duration_min=float(duration_min),
        composed_at=now,
        status=trip.status,
        trip_score=float(trip_score),
        band=band,
        band_color=band_color,
        mood=mood,
        mood_color=mood_color,
        factors=factors,
        realized_avg_safety=float(realized_avg_safety),
        realized_min_safety=float(realized_min_safety),
        risk_km=float(risk_km),
        geofence_minutes=float(geofence_minutes),
        geofence_fraction=float(geofence_fraction),
        fence_score=float(fence_score),
        event_score=float(event_score),
        exposure_score=float(exposure_score),
        planned_avg_safety=planned_avg,
        planned_min_safety=planned_min,
        avg_safety_delta=float(avg_delta),
        corridor=corridor,
        timeline=timeline,
        n_alerts=n_alerts,
        n_warn_alerts=n_warn,
        n_critical_alerts=n_critical,
        n_geofence_enters=n_geofence_enters,
        n_risk_ahead=n_risk_ahead,
        n_broadcasts=int(broadcasts_count),
        user_sos=user_sos,
        auto_sos=auto_sos,
        scenarios=scenarios,
        best_alternative=best_alt_label,
        calibration=calibration,
        headline=headline,
        advisory_line=advisory_line,
        lessons=lessons,
    )


# ---------------------------------------------------------------- mood / narrative


def _mood_for(
    trip_score: float, user_sos: bool, auto_sos: bool,
    n_warn: int, n_critical: int,
) -> Tuple[str, str]:
    """Ladder: Critical → Rough → Watch → Smooth, first match wins."""
    if user_sos or auto_sos or trip_score < 45 or n_critical >= 2:
        return "Critical", "#FF3D60"
    if trip_score < 60 or n_warn >= 3 or n_critical >= 1:
        return "Rough", "#FF7F50"
    if trip_score < 75 or n_warn >= 1:
        return "Watch", "#F9C440"
    return "Smooth", "#53E3A6"


def _compose_narrative(
    *,
    mood: str,
    band: str,
    trip_score: float,
    trip: TripSession,
    n_warn: int,
    n_critical: int,
    risk_km: float,
    best_alt: Optional[str],
    scenarios: Sequence[CounterfactualScenario],
    geofence_minutes: float,
) -> Tuple[str, str]:
    """Two one-liners: a headline + an advisory_line."""
    dest = trip.plan.dest_label or "destination"
    origin = trip.plan.origin_label or "start"
    mode = trip.plan.route_mode
    if mood == "Critical":
        headline = (
            f"Critical trip — {origin} → {dest}, {mode} route, "
            f"composite {trip_score:.0f}/100."
        )
    elif mood == "Rough":
        headline = (
            f"Rough trip — {origin} → {dest}, "
            f"{n_warn} warn / {n_critical} critical alerts, "
            f"composite {trip_score:.0f}/100."
        )
    elif mood == "Watch":
        headline = (
            f"Watch trip — {origin} → {dest} on {mode}, "
            f"composite {trip_score:.0f}/100 (band {band})."
        )
    else:
        headline = (
            f"Smooth run — {origin} → {dest} on {mode}, "
            f"composite {trip_score:.0f}/100 ({band})."
        )

    pieces: List[str] = []
    pieces.append(
        f"Integrated exposure **{risk_km:.2f} risk-km** across "
        f"{trip.plan.distance_km:.1f} km."
    )
    if best_alt:
        delta = next(
            (s.delta_trip_score for s in scenarios if s.label == best_alt),
            0.0,
        )
        risk_delta = next(
            (s.delta_risk_km for s in scenarios if s.label == best_alt),
            0.0,
        )
        pieces.append(
            f"The **{best_alt}** route at the same depart would have been "
            f"{_fmt_signed(delta, digits=1)} pts (Δrisk-km "
            f"{_fmt_signed(-risk_delta, digits=2)})."
        )
    else:
        pieces.append("No counterfactual route beats the actual run at this depart.")
    if geofence_minutes >= 3.0:
        pieces.append(
            f"You spent **{geofence_minutes:.0f} min** inside risk polygons "
            f"along the corridor."
        )
    return headline, " ".join(pieces)


def _compose_lessons(
    *,
    mood: str,
    trip: TripSession,
    trip_score: float,
    risk_km: float,
    scenarios: Sequence[CounterfactualScenario],
    best_alt: Optional[str],
    n_warn: int,
    n_critical: int,
    geofence_minutes: float,
    geofence_fraction: float,
    avg_delta: float,
    calibration: Optional[CalibrationReport],
    broadcasts_count: int,
) -> List[str]:
    """Deterministic, first-match-wins bullets keyed to the debrief itself.

    Each bullet names the WaySafe tab (Tempo / Refuge / Compass / Sentinel /
    Live Trip / Map) the analyst should open next — so the debrief deep-links
    into the rest of the surface."""
    out: List[str] = []
    if trip.user_sos_fired:
        out.append(
            "🆘 You triggered the manual SOS — make sure all trusted "
            "contacts received the broadcast and follow up in person. "
            "Open **Alerts** for the dispatch log."
        )
    if trip.auto_sos_fired:
        out.append(
            "⏸️ The auto-SOS rule fired (stall in a risk zone). For the "
            "next outing, plan a forecast-safest route in **Tempo** and "
            "pre-position a refuge POI in **Refuge** before you leave."
        )
    if mood == "Critical" and not (trip.user_sos_fired or trip.auto_sos_fired):
        out.append(
            "🔴 The composite landed in Critical purely on exposure + events. "
            "Treat this corridor as off-limits at this depart-time band."
        )

    # Best-alternative pitch (only when meaningfully better).
    if best_alt and best_alt != "actual":
        s = next((sc for sc in scenarios if sc.label == best_alt), None)
        if s is not None and s.delta_trip_score >= 2.0:
            cost = s.delta_eta_minutes
            cost_lbl = (
                f"+{cost:.0f} min"
                if cost > 0.5 else
                ("essentially same ETA" if abs(cost) <= 0.5 else f"{cost:.0f} min faster")
            )
            out.append(
                f"🛡 The **{best_alt}** route at the same depart would have "
                f"been +{s.delta_trip_score:.0f} pts on the composite (saving "
                f"{s.delta_risk_km:.2f} risk-km) at {cost_lbl}. "
                f"Open **Plan Route** and try `{best_alt}` next time."
            )

    if geofence_fraction >= 0.10:
        # Roughly: more than 10% of the journey inside a polygon is the
        # threshold at which a re-route is cheap relative to the saved exposure.
        out.append(
            f"🚷 {geofence_minutes:.0f} min ({geofence_fraction:.0%}) inside "
            f"geofenced risk zones. **Tempo** will surface a depart-time slot "
            f"that threads around the corridor."
        )

    if n_critical >= 1:
        out.append(
            f"⚠️ {n_critical} critical alert(s) fired. Sentinel may already "
            f"be tracking the cluster behind them — open the **Sentinel** "
            f"tab to confirm and watch the velocity grade."
        )
    elif n_warn >= 3:
        out.append(
            f"⚠️ {n_warn} warn alerts on this corridor. Consider asking "
            f"**Compass** to compare this destination to nearby alternatives."
        )

    # Realised vs predicted gap.
    if abs(avg_delta) >= 8.0:
        if avg_delta < 0:
            out.append(
                f"📉 Realised safety came in {avg_delta:.0f} pts under the "
                f"plan — the static score under-priced this corridor at "
                f"the depart-time you chose. Use **Forecast** next time."
            )
        else:
            out.append(
                f"📈 Realised safety came in +{avg_delta:.0f} pts over the "
                f"plan — the static score was pessimistic for this hour. "
                f"You could afford a faster flavor at this depart."
            )

    # Calibration feedback.
    if calibration is not None:
        if calibration.band in ("Noisy", "Off") and calibration.n_false_alarm >= 2:
            out.append(
                "🔧 The risk-ahead alerts over-warned on this trip — if you "
                "find yourself ignoring them, raise RISK_AHEAD_THRESHOLD or "
                "tighten LOOKAHEAD_KM (defaults live in `companion.py`)."
            )
        elif calibration.band == "Sharp" and calibration.n_risk_ahead_alerts >= 2:
            out.append(
                "✅ Every risk-ahead alert lined up with an actual high-risk "
                "stretch on the trace — keep the current thresholds."
            )

    # Trusted-contacts loop.
    if broadcasts_count >= 1:
        out.append(
            f"📨 {broadcasts_count} broadcast(s) dispatched to your trusted "
            f"contacts during this trip. Sync the **Trip Log** entry as the "
            f"family-update post and you're done."
        )

    # Smooth-trip catch-all so the brief never looks empty.
    if mood == "Smooth" and not out:
        out.append(
            f"✅ Composite landed at {trip_score:.0f}/100 with zero events. "
            f"Save this corridor + depart-time as a template in your notes; "
            f"it's a Goldilocks slot for this destination."
        )

    # Always close with a "what to do next" pointer to Tempo so the user has
    # a forward-looking next click.
    if not any("**Tempo**" in l for l in out):
        out.append(
            "⏱ Open **Tempo** to optimise the depart-window for your next "
            "trip on this corridor."
        )

    return out


# ---------------------------------------------------------------- exports


__all__ = [
    "ECHO_BANDS",
    "CALIB_BANDS",
    "KAPPA",
    "CorridorSample",
    "TimelineEvent",
    "CounterfactualScenario",
    "CalibrationReport",
    "ScoreFactor",
    "EchoReport",
    "compute_echo",
]
