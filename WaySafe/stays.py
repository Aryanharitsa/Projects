"""StaySafe — Accommodation Safety Picker for WaySafe.

Compass answers *"where should I go tonight?"* — a one-time visit. StaySafe
answers a fundamentally different question: *"where should I sleep?"* You
are physically at a stay for **16+ hours** of every day — across the sleep
window, the walk back from dinner, and the early-morning step-out — so the
safety calculation has to be **time-of-stay weighted**, not depart-time.

For each candidate stay it computes, for the chosen check-in date:

  * `sleep`     — averaged forecast risk 22:00 → 06:00 (weight 0.30)
  * `evening`   — averaged forecast risk 19:00 → 22:00 (weight 0.20)
  * `morning`   — averaged forecast risk 06:00 → 09:00 (weight 0.10)
  * `walkability` — walk-time-equivalent distance to the 3 nearest help POIs
                     (hospital + police + clinic/pharmacy), normalised
                     against a 1.5 km "safe walk" ceiling (weight 0.18)
  * `quiet`     — inverse Sentinel cluster-pressure within 0.8 km, with
                   night-active clusters weighted heavier (weight 0.12)
  * `reach`     — distance from the area's tourist centroid: penalises
                   "too isolated" stays equally with "too central, crowded"
                   stays via a U-shaped function (weight 0.10)

Each sub-score is 0..1 (1 = safest). The composite **Stay safety score** is
the weighted sum × 100, clipped 0..100. A **traveller profile** (solo,
couple, family-with-kids, business) rebalances the weights — e.g. families
get extra weight on `walkability` and `quiet`; solo travellers on `sleep`
and `evening`.

`compare_stays(...)` ranks 2..8 candidates and returns a
`StayComparisonResult` with the leaderboard, a heat-mapped factor matrix,
per-stay 24-hour risk strips, exports as JSON (`waysafe.staysafe.v1`) and
markdown — plus the *deciding factor* (largest goodness gap in the
winner's favour) so users see *why* one stay wins, not just the numbers.

Pure stdlib + reuse of `safety`, `forecast`, `sentinel`. Zero new deps.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from typing import Any, List, Mapping, Optional, Sequence, Tuple

from utils import haversine_km, point_in_polygon
from safety import HELP_POI_TYPES, compute_safety, point_risk


# ---------------------------------------------------------------- constants

DEFAULT_NIGHTS = 1

# Time windows (start_hour_inclusive, end_hour_exclusive). Wrap-around (e.g.
# sleep 22..06) is handled in `_window_hours`.
WINDOWS: dict[str, Tuple[int, int]] = {
    "sleep":   (22, 6),
    "evening": (19, 22),
    "morning": (6,  9),
}

# Per-window weight defaults — sum across all dimensions = 1.0.
DEFAULT_WEIGHTS: dict[str, float] = {
    "sleep":       0.30,
    "evening":     0.20,
    "morning":     0.10,
    "walkability": 0.18,
    "quiet":       0.12,
    "reach":       0.10,
}

# Traveller-profile reweightings. Each profile redistributes the
# `DEFAULT_WEIGHTS` mass without changing the dimensions or the 1.0 sum.
PROFILES: dict[str, dict[str, float]] = {
    "Solo traveller":    {"sleep": 0.32, "evening": 0.24, "morning": 0.08,
                          "walkability": 0.18, "quiet": 0.10, "reach": 0.08},
    "Couple":            DEFAULT_WEIGHTS,
    "Family with kids":  {"sleep": 0.28, "evening": 0.18, "morning": 0.10,
                          "walkability": 0.22, "quiet": 0.16, "reach": 0.06},
    "Business / solo F": {"sleep": 0.34, "evening": 0.22, "morning": 0.10,
                          "walkability": 0.18, "quiet": 0.10, "reach": 0.06},
}

# Walkability ceilings (kilometres). At or beyond this distance, that help
# leg scores 0; at 0 it scores 1; linear interpolation in between.
WALK_CEILING_KM: dict[str, float] = {
    "hospital": 4.0,
    "police":   2.0,
    "clinic":   1.5,
}

# Sentinel-cluster sweep around each stay. Clusters that overlap this disc
# contribute to the `quiet` penalty; night-active clusters (peak_hour in the
# late-evening / late-night range) get a multiplier.
QUIET_SWEEP_KM = 0.8
QUIET_STATUS_WEIGHT = {"Critical": 1.0, "Emerging": 0.55, "Steady": 0.18, "Cooling": 0.0}
QUIET_NIGHT_MULTIPLIER = 1.6        # multiplies status weight if peak_hour ∈ [20..3]

# Reach term — distance from a centroid of interest, with a U-shape so both
# "too far" and "too central" are penalised. Sweet spot at 1.5 km, ceiling
# at 6.0 km (full penalty), centre over-density penalty at <0.2 km.
REACH_SWEET_KM = 1.5
REACH_CEILING_KM = 6.0
REACH_TOO_CENTRAL_KM = 0.20

# Bands → human level. Mirrors compass / advisory tables.
_LEVEL_TABLE: List[Tuple[str, str, int, int]] = [
    ("Critical",  "#EF4444",  0,  35),
    ("Elevated",  "#F59E0B", 35,  60),
    ("Caution",   "#FBBF24", 60,  80),
    ("All clear", "#10B981", 80, 101),
]


# ---------------------------------------------------------------- dataclasses


@dataclass
class StayCandidate:
    """One candidate accommodation to be scored."""
    name: str
    lat: float
    lon: float
    kind: str = "hotel"            # hotel | hostel | homestay | villa | resort
    price_band: str = ""           # premium | mid | budget | ""
    tags: str = ""                 # free-text comma-separated tags


@dataclass
class FactorScore:
    """One row of the heat-mapped comparison matrix."""
    key: str
    label: str
    display: str
    goodness: float                # 0..1, 1 = safest
    weight: float = 0.0            # share of the 0..1 composite this row owns
    contribution: float = 0.0      # goodness × weight × 100, the actual pts


@dataclass
class HelpLeg:
    """Walk to one help POI category, scored for the walkability dimension."""
    category: str                  # "hospital" | "police" | "clinic"
    name: Optional[str]
    distance_km: Optional[float]
    walk_min: Optional[int]        # naive @ 4.8 km/h
    goodness: float                # 0..1


@dataclass
class StayVerdict:
    """Full scored verdict for one candidate stay."""
    candidate: StayCandidate

    stay_score: int                # 0..100 composite
    level: str
    level_color: str
    band: str

    # Per-window sub-scores (0..1 goodness, 1 = safest). Stored alongside
    # the underlying mean risk so the UI can show both.
    sleep_goodness: float = 0.0
    sleep_risk_mean: float = 0.0
    evening_goodness: float = 0.0
    evening_risk_mean: float = 0.0
    morning_goodness: float = 0.0
    morning_risk_mean: float = 0.0

    walkability_goodness: float = 0.0
    quiet_goodness: float = 0.0
    reach_goodness: float = 0.0

    # Context for cards / matrix.
    help_legs: List[HelpLeg] = field(default_factory=list)
    cluster_overlap: int = 0
    severe_cluster_count: int = 0
    nearest_cluster_status: Optional[str] = None
    reach_km: Optional[float] = None
    safety_score_now: int = 0       # static safety.compute_safety at check-in
    incidents_nearby: int = 0

    # Per-hour risks across the full stay day (24-h sparkline for the UI).
    hourly_risk: List[float] = field(default_factory=list)

    # Matrix-ready factor rows.
    factors: List[FactorScore] = field(default_factory=list)

    rank: int = 0
    is_winner: bool = False
    headline: str = ""
    why_pick: str = ""              # 1-line plain-English rationale


@dataclass
class StayComparisonResult:
    """The full StaySafe showdown returned by `compare_stays`."""
    generated_at: datetime
    check_in: datetime
    nights: int
    profile: str
    weights: dict[str, float]
    stays: List[StayVerdict]
    winner: Optional[StayVerdict]
    runner_up: Optional[StayVerdict]
    margin: int
    verdict_headline: str
    verdict_detail: str
    factor_order: List[Tuple[str, str]] = field(default_factory=list)
    deciding_factor: Optional[str] = None
    schema: str = "waysafe.staysafe.v1"


# ---------------------------------------------------------------- helpers


def _as_records(obj: Any) -> List[Mapping]:
    if obj is None:
        return []
    if hasattr(obj, "to_dict"):
        try:
            return obj.to_dict("records")
        except Exception:
            pass
    return list(obj)


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _level_for(score: int) -> Tuple[str, str, str]:
    """Return (level_name, hex_colour, short band-text)."""
    for name, color, lo, hi in _LEVEL_TABLE:
        if lo <= score < hi:
            return name, color, name
    return "All clear", "#10B981", "All clear"


def _window_hours(start: int, end: int) -> List[int]:
    """Hours in a window; handles wrap-around (e.g. 22..06 → 22,23,0,1,..,5)."""
    if end > start:
        return list(range(start, end))
    return list(range(start, 24)) + list(range(0, end))


def _window_risk_mean(forecaster: Any, lat: float, lon: float,
                      base_day: datetime, hours: Sequence[int],
                      incidents: Sequence[Mapping], geofences: Mapping,
                      pois: Sequence[Mapping]) -> float:
    """Mean risk across the hours, on `base_day`. 0..1.

    Blends temporal *forecast* risk (patterns over DOW × hour, sparse early
    on) with the *static* `point_risk` physics (incident proximity +
    geofence + late-night + help-POI) at 0.45 / 0.55 — so a stay that's
    surrounded by recent verified incidents is *always* downgraded even if
    the forecaster has no late-night history for that cell.
    """
    if not hours:
        return 0.0
    vals: List[float] = []
    for h in hours:
        when = base_day.replace(hour=h, minute=0, second=0, microsecond=0)
        fc = 0.0
        if forecaster is not None:
            try:
                fc = float(forecaster.risk_at(lat, lon, when=when))
            except Exception:
                fc = 0.0
        st = point_risk(lat, lon, incidents, geofences, pois, now=when)
        vals.append(0.45 * fc + 0.55 * st)
    return sum(vals) / max(1, len(vals))


def _hourly_curve(forecaster: Any, lat: float, lon: float,
                  base_day: datetime,
                  incidents: Sequence[Mapping], geofences: Mapping,
                  pois: Sequence[Mapping]) -> List[float]:
    """Full 24-hour blended risk strip for the sparkline (same blend as
    `_window_risk_mean`)."""
    out: List[float] = []
    for h in range(24):
        when = base_day.replace(hour=h, minute=0, second=0, microsecond=0)
        fc = 0.0
        if forecaster is not None:
            try:
                fc = float(forecaster.risk_at(lat, lon, when=when))
            except Exception:
                fc = 0.0
        st = point_risk(lat, lon, incidents, geofences, pois, now=when)
        out.append(0.45 * fc + 0.55 * st)
    return out


def _nearest_of_category(lat: float, lon: float, pois: Sequence[Mapping],
                         wanted: Sequence[str]) -> Tuple[Optional[float], Optional[str]]:
    """Closest POI of any of the wanted ptypes (set/list of strings)."""
    best_d: Optional[float] = None
    best_name: Optional[str] = None
    wanted_l = {w.lower() for w in wanted}
    for p in pois:
        if str(p.get("ptype", "")).lower() not in wanted_l:
            continue
        try:
            d = haversine_km(lat, lon, float(p.get("lat")), float(p.get("lon")))
        except (TypeError, ValueError):
            continue
        if best_d is None or d < best_d:
            best_d = d
            best_name = str(p.get("name", "")) or None
    return (round(best_d, 2) if best_d is not None else None), best_name


def _walk_minutes(km: Optional[float]) -> Optional[int]:
    if km is None:
        return None
    return int(round(km * 60.0 / 4.8))   # 4.8 km/h walking pace


def _help_legs(lat: float, lon: float,
               pois: Sequence[Mapping]) -> Tuple[List[HelpLeg], float]:
    """Three legs (hospital, police, clinic) → goodness 0..1.

    Each leg's goodness is `1 − distance / ceiling`, clipped. The composite
    is the **mean of the legs we actually have data for** — so a missing
    clinic in the dataset doesn't sink the whole walkability score
    (gracefully degrades to a 2-leg average). At least one leg must resolve
    or composite is 0.
    """
    cat_groups: dict[str, Sequence[str]] = {
        "hospital": ("hospital",),
        "police":   ("police",),
        # Clinic-equivalent: include fire stations + tourist help desks so
        # this leg has a sane default when no clinics are in the dataset.
        "clinic":   ("clinic", "fire", "tourist_help_desk"),
    }
    legs: List[HelpLeg] = []
    resolved_goodness: List[float] = []
    for cat, wanted in cat_groups.items():
        d, name = _nearest_of_category(lat, lon, pois, wanted)
        ceiling = WALK_CEILING_KM.get(cat, 3.0)
        if d is None:
            g = None
        else:
            g = _clamp01(1.0 - (d / ceiling))
            resolved_goodness.append(g)
        legs.append(HelpLeg(
            category=cat,
            name=name,
            distance_km=d,
            walk_min=_walk_minutes(d),
            goodness=round(g, 3) if g is not None else 0.0,
        ))
    composite = (sum(resolved_goodness) / len(resolved_goodness)
                 if resolved_goodness else 0.0)
    return legs, composite


def _quiet_pressure(lat: float, lon: float,
                    clusters: Sequence) -> Tuple[float, int, int, Optional[str]]:
    """Quiet-pressure penalty in [0..1] and overlap stats.

    Night-active clusters (peak_hour ∈ [20..3]) get a 1.6× multiplier so a
    stay that's quiet by day but sits on top of a night-loud hotspot is
    correctly downgraded.
    """
    pen = 0.0
    overlap = 0
    severe = 0
    worst_rank = 99
    worst_status: Optional[str] = None
    status_order = {"Critical": 0, "Emerging": 1, "Steady": 2, "Cooling": 3}
    for c in clusters or []:
        try:
            d = haversine_km(lat, lon, c.center_lat, c.center_lon)
        except AttributeError:
            continue
        if d > QUIET_SWEEP_KM + c.radius_km:
            continue
        overlap += 1
        w = QUIET_STATUS_WEIGHT.get(c.status, 0.0)
        peak = getattr(c, "peak_hour", None)
        if peak is not None and (peak >= 20 or peak <= 3):
            w *= QUIET_NIGHT_MULTIPLIER
        pen += w * (float(getattr(c, "severity_mean", 3.0)) / 5.0)
        if c.status in ("Critical", "Emerging") and getattr(c, "severity_mean", 0) >= 3.5:
            severe += 1
        r = status_order.get(c.status, 9)
        if r < worst_rank:
            worst_rank = r
            worst_status = c.status
    # Normalise to 0..1: 3.0 raw pressure = full red.
    return min(1.0, pen / 3.0), overlap, severe, worst_status


def _reach_goodness(lat: float, lon: float,
                    pois: Sequence[Mapping],
                    centroid: Optional[Tuple[float, float]] = None,
                    ) -> Tuple[float, Optional[float]]:
    """U-shaped scoring around an area-of-interest centroid.

    Prefers an explicit `centroid` (compare_stays defaults this to the mean
    of the candidate stays themselves — the trip's own centre of gravity).
    Falls back to attraction/market POIs, then to *any* POI. Sweet spot at
    `REACH_SWEET_KM`; full penalty beyond `REACH_CEILING_KM` *or* under
    `REACH_TOO_CENTRAL_KM` (too central → crowd / nightlife noise).
    """
    if centroid is None:
        pts: List[Tuple[float, float]] = []
        for p in pois:
            if str(p.get("ptype", "")).lower() in {"attraction", "market",
                                                    "tourist_help_desk"}:
                try:
                    pts.append((float(p["lat"]), float(p["lon"])))
                except (TypeError, ValueError, KeyError):
                    continue
        if not pts:
            for p in pois:
                try:
                    pts.append((float(p["lat"]), float(p["lon"])))
                except (TypeError, ValueError, KeyError):
                    continue
        if not pts:
            return 0.5, None
        clat = sum(p[0] for p in pts) / len(pts)
        clon = sum(p[1] for p in pts) / len(pts)
    else:
        clat, clon = centroid
    d = haversine_km(lat, lon, clat, clon)
    if d <= REACH_TOO_CENTRAL_KM:
        g = 0.55                                # too central / dense
    elif d <= REACH_SWEET_KM:
        g = 0.55 + 0.45 * (d - REACH_TOO_CENTRAL_KM) / (
            REACH_SWEET_KM - REACH_TOO_CENTRAL_KM)
    elif d >= REACH_CEILING_KM:
        g = 0.0
    else:
        g = 1.0 - (d - REACH_SWEET_KM) / (REACH_CEILING_KM - REACH_SWEET_KM)
    return _clamp01(g), round(d, 2)


def _why_pick(verdict: StayVerdict) -> str:
    """One-line plain-English rationale tailored to the verdict."""
    parts: List[str] = []
    if verdict.severe_cluster_count >= 1:
        parts.append(f"{verdict.severe_cluster_count} severe cluster"
                     f"{'s' if verdict.severe_cluster_count != 1 else ''} on the doorstep")
    if verdict.help_legs:
        hosp = next((l for l in verdict.help_legs if l.category == "hospital"), None)
        if hosp and hosp.distance_km is not None and hosp.distance_km <= 2.0:
            parts.append(f"hospital {hosp.distance_km:.1f} km away")
    if verdict.sleep_risk_mean <= 0.15:
        parts.append("calm sleep window")
    elif verdict.sleep_risk_mean >= 0.45:
        parts.append("loud nights forecast")
    if verdict.evening_risk_mean >= 0.45:
        parts.append("risky evening walk home")
    if not parts:
        if verdict.level == "All clear":
            return "Solid across the board — no red flags."
        return "Mixed picture — see the factor matrix."
    return "; ".join(parts[:3]).capitalize() + "."


# ---------------------------------------------------------------- core


def score_stay(
    candidate: StayCandidate,
    *,
    incidents: Sequence[Mapping],
    pois: Sequence[Mapping],
    geofences: Mapping,
    forecaster: Any,
    sentinel_clusters: Optional[Sequence],
    check_in: datetime,
    weights: Mapping[str, float],
    reach_centroid: Optional[Tuple[float, float]] = None,
) -> StayVerdict:
    """Score a single candidate. `compare_stays` calls this per candidate."""
    base_day = check_in.replace(hour=0, minute=0, second=0, microsecond=0)

    # Per-window mean risks → goodness = 1 − risk_mean.
    sleep_risk = _window_risk_mean(
        forecaster, candidate.lat, candidate.lon, base_day,
        _window_hours(*WINDOWS["sleep"]), incidents, geofences, pois,
    )
    even_risk = _window_risk_mean(
        forecaster, candidate.lat, candidate.lon, base_day,
        _window_hours(*WINDOWS["evening"]), incidents, geofences, pois,
    )
    morn_risk = _window_risk_mean(
        forecaster, candidate.lat, candidate.lon, base_day,
        _window_hours(*WINDOWS["morning"]), incidents, geofences, pois,
    )
    sleep_g = _clamp01(1.0 - sleep_risk)
    even_g  = _clamp01(1.0 - even_risk)
    morn_g  = _clamp01(1.0 - morn_risk)

    # Walkability / quiet / reach.
    legs, walk_g = _help_legs(candidate.lat, candidate.lon, pois)
    quiet_pen, clu_n, clu_severe, clu_status = _quiet_pressure(
        candidate.lat, candidate.lon, sentinel_clusters or [])
    quiet_g = _clamp01(1.0 - quiet_pen)
    reach_g, reach_km = _reach_goodness(candidate.lat, candidate.lon, pois,
                                        centroid=reach_centroid)

    # Static safety snapshot at check-in time (context, not weighted into composite).
    safety = compute_safety(candidate.lat, candidate.lon,
                            incidents, geofences, pois, now=check_in)

    # Composite. Weights are normalised so any custom mix that doesn't quite
    # sum to 1.0 still produces a sane 0..100.
    wsum = sum(weights.get(k, 0.0) for k in DEFAULT_WEIGHTS) or 1.0
    w = {k: weights.get(k, DEFAULT_WEIGHTS[k]) / wsum for k in DEFAULT_WEIGHTS}
    goodness_by_key = {
        "sleep":       sleep_g,
        "evening":     even_g,
        "morning":     morn_g,
        "walkability": walk_g,
        "quiet":       quiet_g,
        "reach":       reach_g,
    }
    composite = sum(w[k] * goodness_by_key[k] for k in w)
    stay_score = int(round(_clamp01(composite) * 100.0))

    # If the stay sits inside a geofenced risk zone, cap the level at
    # Elevated regardless of score — the static safety also reflects this
    # but the composite is forecast-heavy, so we force a floor here.
    geo_hits: List[str] = []
    for feat in geofences.get("features", []):
        coords = feat.get("geometry", {}).get("coordinates", [[]])
        if coords and point_in_polygon(candidate.lat, candidate.lon, coords[0]):
            geo_hits.append(feat.get("properties", {}).get("name", "risk zone"))
    if geo_hits and stay_score > 59:
        stay_score = 59      # forced to Elevated band

    level, color, band = _level_for(stay_score)

    # Matrix-ready factor rows.
    def _disp_pct(g: float) -> str: return f"{int(round(g * 100))}%"
    def _disp_risk(r: float) -> str: return f"{int(round(r * 100))}% risk"

    hosp_leg = next((l for l in legs if l.category == "hospital"), None)
    if hosp_leg and hosp_leg.distance_km is not None:
        walk_disp = f"{hosp_leg.distance_km:.1f} km hosp · {hosp_leg.walk_min}m walk"
    else:
        walk_disp = "no hospital nearby"
    quiet_disp = (
        f"{clu_n} cluster{'s' if clu_n != 1 else ''}"
        + (f" · {clu_severe}!" if clu_severe else "")
        + (f" · {clu_status}" if clu_status else "")
    )
    reach_disp = f"{reach_km:.1f} km to centre" if reach_km is not None else "—"

    factor_specs: List[Tuple[str, str, str, float]] = [
        ("sleep",       "Sleep window (22–06)", _disp_risk(sleep_risk), sleep_g),
        ("evening",     "Evening return (19–22)", _disp_risk(even_risk), even_g),
        ("morning",     "Morning depart (06–09)", _disp_risk(morn_risk), morn_g),
        ("walkability", "Walk to help",            walk_disp,            walk_g),
        ("quiet",       "Quiet score (800 m)",     quiet_disp,           quiet_g),
        ("reach",       "Reach to centre",         reach_disp,           reach_g),
    ]
    factors = [
        FactorScore(
            key=key, label=label, display=display, goodness=round(g, 3),
            weight=round(w[key], 3),
            contribution=round(w[key] * g * 100.0, 1),
        )
        for key, label, display, g in factor_specs
    ]

    hourly = _hourly_curve(forecaster, candidate.lat, candidate.lon,
                           base_day, incidents, geofences, pois)

    verdict = StayVerdict(
        candidate=candidate,
        stay_score=stay_score,
        level=level,
        level_color=color,
        band=band,
        sleep_goodness=round(sleep_g, 3),
        sleep_risk_mean=round(sleep_risk, 3),
        evening_goodness=round(even_g, 3),
        evening_risk_mean=round(even_risk, 3),
        morning_goodness=round(morn_g, 3),
        morning_risk_mean=round(morn_risk, 3),
        walkability_goodness=round(walk_g, 3),
        quiet_goodness=round(quiet_g, 3),
        reach_goodness=round(reach_g, 3),
        help_legs=legs,
        cluster_overlap=clu_n,
        severe_cluster_count=clu_severe,
        nearest_cluster_status=clu_status,
        reach_km=reach_km,
        safety_score_now=safety.score,
        incidents_nearby=safety.incidents_nearby,
        hourly_risk=[round(x, 3) for x in hourly],
        factors=factors,
    )
    verdict.why_pick = _why_pick(verdict)
    verdict.headline = {
        "Critical":  "Avoid — multiple acute risks on the doorstep.",
        "Elevated":  "Real risk factors active — book with eyes open.",
        "Caution":   "Mostly fine — prefer daylight returns.",
        "All clear": "Solid stay — standard precautions.",
    }.get(level, "")
    return verdict


def _verdict_text(ranked: List[StayVerdict]) -> Tuple[str, str, Optional[str]]:
    """Top-line + rationale + deciding-factor label for the showdown."""
    if not ranked:
        return "No candidates compared.", "", None
    if len(ranked) == 1:
        only = ranked[0]
        return (
            f"{only.candidate.name}: {only.level} ({only.stay_score}/100).",
            "Add a second stay to run a head-to-head showdown.",
            None,
        )
    win, run = ranked[0], ranked[1]
    margin = win.stay_score - run.stay_score
    if margin >= 15:
        head = f"Recommend **{win.candidate.name}** — {margin} pts clear of {run.candidate.name}."
    elif margin >= 5:
        head = f"**{win.candidate.name}** edges it — {margin} pts over {run.candidate.name}."
    elif margin >= 1:
        head = f"**{win.candidate.name}** just shades it — {margin} pt{'s' if margin != 1 else ''} over {run.candidate.name}."
    else:
        head = f"**{win.candidate.name}** and {run.candidate.name} are neck-and-neck — pick on the matrix."

    # Deciding factor: largest goodness gap in the winner's favour, weighted.
    detail = ""
    deciding: Optional[str] = None
    best_gap = 0.0
    best_label = ""
    for fw, fr in zip(win.factors, run.factors):
        gap = (fw.goodness - fr.goodness) * fw.weight
        if gap > best_gap:
            best_gap = gap
            best_label = fw.label
            deciding = fw.key
    if best_label and best_gap > 0.005:
        detail = f"{win.candidate.name} wins mainly on **{best_label.lower()}**."
    elif win.level == "All clear":
        detail = f"{win.candidate.name} is the only all-clear option."
    else:
        detail = f"All options carry some risk — {win.candidate.name} is the least exposed."
    return head, detail, deciding


def compare_stays(
    candidates: Sequence[StayCandidate],
    *,
    inc_df: Any = None,
    poi_df: Any = None,
    geofences: Optional[Mapping] = None,
    forecaster: Any = None,
    sentinel_clusters: Optional[Sequence] = None,
    check_in: Optional[datetime] = None,
    nights: int = DEFAULT_NIGHTS,
    profile: str = "Couple",
    weights: Optional[Mapping[str, float]] = None,
) -> StayComparisonResult:
    """Rank 2..8 candidate stays into one StaySafe verdict."""
    check_in = check_in or datetime.utcnow().replace(hour=15, minute=0, second=0, microsecond=0)
    incidents = _as_records(inc_df)
    pois = _as_records(poi_df)
    geo = geofences or {"features": []}

    w = dict(weights) if weights is not None else dict(
        PROFILES.get(profile, DEFAULT_WEIGHTS))

    # Trip's own centre of gravity = mean of the candidate stays. Beats a
    # POI-derived centroid when the dataset has no attractions.
    if candidates:
        reach_centroid: Optional[Tuple[float, float]] = (
            sum(c.lat for c in candidates) / len(candidates),
            sum(c.lon for c in candidates) / len(candidates),
        )
    else:
        reach_centroid = None

    verdicts = [
        score_stay(
            c,
            incidents=incidents, pois=pois, geofences=geo,
            forecaster=forecaster, sentinel_clusters=sentinel_clusters,
            check_in=check_in, weights=w, reach_centroid=reach_centroid,
        )
        for c in candidates
    ]

    # Rank: score desc, then better worst-window, then closer hospital.
    def _hosp_km(v: StayVerdict) -> float:
        h = next((l for l in v.help_legs if l.category == "hospital"), None)
        return h.distance_km if (h and h.distance_km is not None) else 99.0

    def _worst_window(v: StayVerdict) -> float:
        return -max(v.sleep_risk_mean, v.evening_risk_mean, v.morning_risk_mean)

    verdicts.sort(key=lambda v: (-v.stay_score, _worst_window(v), _hosp_km(v)))
    for i, v in enumerate(verdicts):
        v.rank = i + 1
        v.is_winner = i == 0

    head, detail, deciding = _verdict_text(verdicts)
    factor_order = (
        [(f.key, f.label) for f in verdicts[0].factors] if verdicts else []
    )

    return StayComparisonResult(
        generated_at=datetime.utcnow(),
        check_in=check_in,
        nights=max(1, int(nights)),
        profile=profile,
        weights={k: round(w.get(k, 0.0), 3) for k in DEFAULT_WEIGHTS},
        stays=verdicts,
        winner=verdicts[0] if verdicts else None,
        runner_up=verdicts[1] if len(verdicts) > 1 else None,
        margin=(verdicts[0].stay_score - verdicts[1].stay_score) if len(verdicts) > 1 else 0,
        verdict_headline=head,
        verdict_detail=detail,
        factor_order=factor_order,
        deciding_factor=deciding,
    )


# ---------------------------------------------------------------- exports


def comparison_to_json(result: StayComparisonResult) -> dict:
    """Stable, diffable JSON for `waysafe.staysafe.v1`."""
    def _stay(v: StayVerdict) -> dict:
        return {
            "rank": v.rank,
            "name": v.candidate.name,
            "kind": v.candidate.kind,
            "price_band": v.candidate.price_band,
            "tags": v.candidate.tags,
            "lat": v.candidate.lat,
            "lon": v.candidate.lon,
            "stay_score": v.stay_score,
            "level": v.level,
            "band": v.band,
            "safety_score_now": v.safety_score_now,
            "incidents_nearby": v.incidents_nearby,
            "windows": {
                "sleep":   {"risk_mean": v.sleep_risk_mean,   "goodness": v.sleep_goodness},
                "evening": {"risk_mean": v.evening_risk_mean, "goodness": v.evening_goodness},
                "morning": {"risk_mean": v.morning_risk_mean, "goodness": v.morning_goodness},
            },
            "walkability": {
                "goodness": v.walkability_goodness,
                "legs": [asdict(l) for l in v.help_legs],
            },
            "quiet": {
                "goodness": v.quiet_goodness,
                "cluster_overlap": v.cluster_overlap,
                "severe_clusters": v.severe_cluster_count,
                "nearest_cluster_status": v.nearest_cluster_status,
            },
            "reach": {
                "goodness": v.reach_goodness,
                "km_to_centre": v.reach_km,
            },
            "factors": [asdict(f) for f in v.factors],
            "hourly_risk": list(v.hourly_risk),
            "headline": v.headline,
            "why_pick": v.why_pick,
        }

    return {
        "schema": result.schema,
        "generated_at": result.generated_at.isoformat(timespec="seconds") + "Z",
        "check_in": result.check_in.isoformat(timespec="minutes"),
        "nights": result.nights,
        "profile": result.profile,
        "weights": result.weights,
        "verdict": {
            "winner": result.winner.candidate.name if result.winner else None,
            "margin": result.margin,
            "headline": result.verdict_headline,
            "detail": result.verdict_detail,
            "deciding_factor": result.deciding_factor,
        },
        "stays": [_stay(v) for v in result.stays],
    }


def comparison_to_markdown(result: StayComparisonResult) -> str:
    """WhatsApp / email / Notion-paste format with verdict + matrix."""
    lines: List[str] = []
    lines.append("# 🛏️ WaySafe StaySafe — Accommodation Safety Picker")
    lines.append("")
    # Headline already contains its own **bold** spans for the stay name —
    # don't double-bold.
    lines.append(result.verdict_headline)
    if result.verdict_detail:
        lines.append("")
        lines.append(result.verdict_detail)
    lines.append("")
    lines.append(
        f"_Check-in {result.check_in:%a %d %b %H:%M} · {result.nights} "
        f"night{'s' if result.nights != 1 else ''} · profile: **{result.profile}**_"
    )
    lines.append("")

    # Leaderboard table
    lines.append("| # | Stay | Score | Level | Sleep | Evening | Walk to hospital |")
    lines.append("|---:|---|---:|---|---:|---:|---|")
    for v in result.stays:
        hosp = next((l for l in v.help_legs if l.category == "hospital"), None)
        hosp_s = f"{hosp.distance_km:.1f} km" if (hosp and hosp.distance_km is not None) else "—"
        crown = " 👑" if v.is_winner else ""
        lines.append(
            f"| {v.rank} | {v.candidate.name}{crown} | {v.stay_score} | {v.level} | "
            f"{int(round(v.sleep_risk_mean*100))}% | "
            f"{int(round(v.evening_risk_mean*100))}% | {hosp_s} |"
        )
    lines.append("")

    # Per-pick rationale
    for v in result.stays[:3]:
        lines.append(f"### #{v.rank} · {v.candidate.name}")
        lines.append(f"*{v.headline}*  ")
        lines.append(f"_Why:_ {v.why_pick}")
        lines.append("")
        lines.append(
            f"- Sleep window risk: **{int(round(v.sleep_risk_mean*100))}%** "
            f"· Evening risk: **{int(round(v.evening_risk_mean*100))}%** "
            f"· Morning risk: **{int(round(v.morning_risk_mean*100))}%**"
        )
        if v.help_legs:
            legs_s = " · ".join(
                f"{l.category} {l.distance_km:.1f} km" if l.distance_km is not None
                else f"{l.category} —"
                for l in v.help_legs
            )
            lines.append(f"- Walk to help: {legs_s}")
        if v.cluster_overlap:
            lines.append(
                f"- Live clusters within {QUIET_SWEEP_KM:g} km: **{v.cluster_overlap}**"
                + (f" (severe: {v.severe_cluster_count})" if v.severe_cluster_count else "")
            )
        lines.append("")

    lines.append(
        "_Generated by WaySafe StaySafe · `waysafe.staysafe.v1`_  "
    )
    return "\n".join(lines)


# ---------------------------------------------------------------- CSV loader


def load_stays_csv(path: str) -> List[StayCandidate]:
    """Tiny CSV loader so the app can ship a Goa demo set without pandas."""
    import csv
    out: List[StayCandidate] = []
    with open(path, newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            try:
                out.append(StayCandidate(
                    name=row["name"].strip(),
                    lat=float(row["lat"]),
                    lon=float(row["lon"]),
                    kind=row.get("kind", "hotel").strip() or "hotel",
                    price_band=row.get("price_band", "").strip(),
                    tags=row.get("tags", "").strip(),
                ))
            except (KeyError, ValueError):
                continue
    return out
