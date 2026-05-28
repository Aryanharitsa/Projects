"""Compass — the "where should I go tonight?" engine for WaySafe.

The Advisory tab answers *"is this one place safe?"*. But tourists rarely
have one fixed destination — they choose between options: *Baga or Anjuna
for dinner? Stay in Calangute or move to Panaji?* Compass answers that
**comparative** question. It runs every engine in the repo over 2–5
candidate destinations at a chosen depart time and returns a single ranked
verdict with a clear winner, a margin, and a side-by-side factor matrix.

For each candidate it fuses:

  * `safety.compute_safety`            — the static 0–100 score + factors
  * `forecaster.risk_at(depart)`       — predicted risk *at the hour you'd arrive*
  * `forecaster.risk_curve`            — the safer hour to visit *that* spot
  * `sentinel` cluster overlap          — is something *escalating* near here?
  * geofence membership + nearest help — context the score already uses

into one forward-looking **Compass score** (0–100, higher = safer):

    compass = clip( safety_score
                    − FORECAST_WEIGHT · forecast_risk_at_depart
                    − cluster_penalty ,
                    0, 100 )

The safety score is a static snapshot. The forecast term prices *when*
you're going (a calm beach at 03:00 is not the same beach at noon), and the
cluster term folds in **velocity** — the advisory's "things are moving"
signal — so an escalating hotspot drags a destination down even if its
historical score looks fine.

Pure stdlib + reuse of the project's own modules. No new dependencies.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from typing import Any, List, Mapping, Optional, Sequence, Tuple

from utils import haversine_km, point_in_polygon
from safety import HELP_POI_TYPES, SafetyResult, compute_safety


# ---------------------------------------------------------------- constants

DEFAULT_RADIUS_KM = 2.0

# How hard a maximally-risky forecast hour (risk → 1.0) drags the score down.
FORECAST_WEIGHT = 16.0

# Per-cluster penalty by velocity status, scaled by severity_mean / 5,
# summed over every cluster overlapping the destination's scan disc, capped.
_STATUS_WEIGHT = {"Critical": 12.0, "Emerging": 6.0, "Steady": 2.0, "Cooling": 0.0}
CLUSTER_PENALTY_CAP = 20.0

# Advisory levels — mirrors `advisory._LEVEL_TABLE` so Compass and the
# Advisory tab never disagree about what "Elevated" means. Each tuple is
# (name, color, score-lower-bound, score-upper-bound).
_LEVEL_TABLE: List[Tuple[str, str, int, int]] = [
    ("Critical",  "#EF4444",  0,  35),
    ("Elevated",  "#F59E0B", 35,  60),
    ("Caution",   "#FBBF24", 60,  80),
    ("All clear", "#10B981", 80, 101),
]
_LEVEL_RANK: dict[str, int] = {n: i for i, (n, *_r) in enumerate(_LEVEL_TABLE)}

# Goodness normalisers (used for the comparison-matrix heat colours).
_INCIDENT_RED_AT = 10.0   # this many incidents nearby reads fully red
_HELP_RED_AT_KM = 5.0     # nearest help this far reads fully red


# ---------------------------------------------------------------- dataclasses


@dataclass
class FactorScore:
    """One comparable row in the showdown matrix for one destination."""
    key: str          # safety | forecast | incidents | help | clusters
    label: str
    display: str      # human-readable cell value, e.g. "1.4 km"
    goodness: float   # 0..1, 1 = safest (drives the heat colour)


@dataclass
class DestinationVerdict:
    label: str
    lat: float
    lon: float

    compass_score: int          # 0..100 blended, higher = safer
    safety_score: int
    band: str
    advisory_level: str
    level_color: str

    incidents_nearby: int = 0
    nearest_help_km: Optional[float] = None
    nearest_help_name: Optional[str] = None
    active_geofences: List[str] = field(default_factory=list)

    forecast_risk: float = 0.0          # 0..1 at the depart hour
    best_hour_label: Optional[str] = None
    best_hour_risk: Optional[float] = None

    cluster_penalty: float = 0.0
    nearby_cluster_count: int = 0
    severe_cluster_count: int = 0
    top_cluster_status: Optional[str] = None

    factors: List[FactorScore] = field(default_factory=list)
    safety_result: Optional[SafetyResult] = None
    headline: str = ""

    rank: int = 0
    is_winner: bool = False


@dataclass
class ComparisonResult:
    generated_at: datetime
    depart: datetime
    radius_km: float
    destinations: List[DestinationVerdict]  # ranked best → worst
    winner: Optional[DestinationVerdict]
    runner_up: Optional[DestinationVerdict]
    margin: int
    verdict_headline: str
    verdict_detail: str
    factor_order: List[Tuple[str, str]] = field(default_factory=list)  # (key, label)
    schema: str = "waysafe.compass.v1"


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


def _level_for(score: int) -> Tuple[str, str]:
    for name, color, lo, hi in _LEVEL_TABLE:
        if lo <= score < hi:
            return name, color
    return "All clear", "#10B981"


def _escalate(level: str, severe_clusters: int) -> Tuple[str, str]:
    """Bump the level when escalating clusters overlap — mirrors advisory."""
    rank = _LEVEL_RANK[level]
    if severe_clusters >= 2:
        rank = min(rank, _LEVEL_RANK["Critical"])
    elif severe_clusters >= 1:
        rank = min(rank, _LEVEL_RANK["Elevated"])
    name, color, _lo, _hi = _LEVEL_TABLE[rank]
    return name, color


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _cluster_pressure(
    lat: float, lon: float, radius_km: float, clusters: Sequence
) -> Tuple[float, int, int, Optional[str]]:
    """Penalty, overlap count, severe count and worst status for one point."""
    penalty = 0.0
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
        if d > radius_km + c.radius_km:
            continue
        overlap += 1
        w = _STATUS_WEIGHT.get(c.status, 0.0)
        penalty += w * (float(c.severity_mean) / 5.0)
        if c.status in ("Critical", "Emerging") and c.severity_mean >= 3.5:
            severe += 1
        r = status_order.get(c.status, 9)
        if r < worst_rank:
            worst_rank = r
            worst_status = c.status
    return min(penalty, CLUSTER_PENALTY_CAP), overlap, severe, worst_status


def _best_hour(forecaster: Any, lat: float, lon: float, depart: datetime):
    """Lowest-risk hour to visit *this* spot on the depart day."""
    try:
        curve = forecaster.risk_curve(lat, lon, day=depart)
    except Exception:
        return None, None
    if not curve:
        return None, None
    best_h = min(range(len(curve)), key=lambda h: curve[h])
    label = depart.replace(hour=best_h, minute=0).strftime("%a %H:%M")
    return label, round(float(curve[best_h]), 3)


def _dest_headline(level: str, v_label: str) -> str:
    return {
        "Critical":  "Avoid for now — acute risk on the ground.",
        "Elevated":  "Real risk factors active — go with care.",
        "Caution":   "Mostly safe — stay alert, prefer daylight.",
        "All clear": "Conditions look good — standard precautions.",
    }.get(level, "")


# ---------------------------------------------------------------- core


def assess_destination(
    lat: float,
    lon: float,
    label: str,
    *,
    incidents: Sequence[Mapping],
    pois: Sequence[Mapping],
    geofences: Mapping,
    forecaster: Any = None,
    sentinel_clusters: Optional[Sequence] = None,
    now: datetime,
    depart: datetime,
    radius_km: float = DEFAULT_RADIUS_KM,
) -> DestinationVerdict:
    """Score a single candidate. `compare_destinations` calls this per target."""
    safety = compute_safety(lat, lon, incidents, geofences, pois, now=depart)

    # Geofence membership at the target.
    geo_names: List[str] = []
    for feat in geofences.get("features", []):
        coords = feat.get("geometry", {}).get("coordinates", [[]])
        if coords and point_in_polygon(lat, lon, coords[0]):
            geo_names.append(feat.get("properties", {}).get("name", "risk zone"))

    # Nearest help POI (name + distance).
    nearest_km: Optional[float] = None
    nearest_name: Optional[str] = None
    for p in pois:
        if str(p.get("ptype", "")).lower() not in HELP_POI_TYPES:
            continue
        try:
            d = haversine_km(lat, lon, float(p.get("lat")), float(p.get("lon")))
        except (TypeError, ValueError):
            continue
        if nearest_km is None or d < nearest_km:
            nearest_km = round(d, 2)
            nearest_name = str(p.get("name", ""))

    # Forecast risk at the depart hour + the safer hour to come here.
    fc_risk = 0.0
    best_label = best_risk = None
    if forecaster is not None:
        try:
            fc_risk = float(forecaster.risk_at(lat, lon, when=depart))
        except Exception:
            fc_risk = 0.0
        best_label, best_risk = _best_hour(forecaster, lat, lon, depart)

    # Sentinel cluster pressure overlapping the scan disc.
    clu_pen, clu_n, clu_severe, clu_status = _cluster_pressure(
        lat, lon, radius_km, sentinel_clusters or []
    )

    # Blended forward-looking compass score.
    raw = safety.score - FORECAST_WEIGHT * fc_risk - clu_pen
    compass = int(round(max(0.0, min(100.0, raw))))

    base_level, _ = _level_for(safety.score)
    level, level_color = _escalate(base_level, clu_severe)

    # Comparison-matrix factor rows (all 0..1 goodness, 1 = safest).
    help_good = (
        _clamp01(1.0 - nearest_km / _HELP_RED_AT_KM) if nearest_km is not None else 0.0
    )
    factors = [
        FactorScore("safety", "Safety score", f"{safety.score}/100", safety.score / 100.0),
        FactorScore("forecast", "Forecast risk", f"{int(round(fc_risk * 100))}%", _clamp01(1.0 - fc_risk)),
        FactorScore("incidents", "Incidents nearby", str(safety.incidents_nearby),
                    _clamp01(1.0 - safety.incidents_nearby / _INCIDENT_RED_AT)),
        FactorScore("help", "Nearest help",
                    f"{nearest_km:.1f} km" if nearest_km is not None else "—", help_good),
        FactorScore("clusters", "Live clusters",
                    f"{clu_n}" + (f" · {clu_severe}!" if clu_severe else ""),
                    _clamp01(1.0 - clu_pen / CLUSTER_PENALTY_CAP)),
    ]

    return DestinationVerdict(
        label=label, lat=lat, lon=lon,
        compass_score=compass,
        safety_score=safety.score,
        band=safety.band,
        advisory_level=level,
        level_color=level_color,
        incidents_nearby=safety.incidents_nearby,
        nearest_help_km=nearest_km,
        nearest_help_name=nearest_name,
        active_geofences=geo_names,
        forecast_risk=round(fc_risk, 3),
        best_hour_label=best_label,
        best_hour_risk=best_risk,
        cluster_penalty=round(clu_pen, 2),
        nearby_cluster_count=clu_n,
        severe_cluster_count=clu_severe,
        top_cluster_status=clu_status,
        factors=factors,
        safety_result=safety,
        headline=_dest_headline(level, label),
    )


def _verdict(ranked: List[DestinationVerdict]) -> Tuple[str, str]:
    """Top-line + one-line rationale for the comparison."""
    if not ranked:
        return "No destinations to compare.", ""
    if len(ranked) == 1:
        only = ranked[0]
        return (
            f"{only.label}: {only.advisory_level} ({only.compass_score}/100).",
            "Add a second destination to run a head-to-head showdown.",
        )
    win, run = ranked[0], ranked[1]
    margin = win.compass_score - run.compass_score
    if margin >= 15:
        head = f"{win.label} is the clear safe pick — {margin} pts clear of {run.label}."
    elif margin >= 5:
        head = f"{win.label} edges it — {margin} pts over {run.label}."
    elif margin >= 1:
        head = f"{win.label} just shades it — only {margin} pt{'s' if margin != 1 else ''} over {run.label}."
    else:
        head = f"{win.label} and {run.label} are neck-and-neck — pick on the factors below."

    # Deciding factor: largest goodness gap in the winner's favour.
    detail = ""
    best_gap = 0.0
    best_label = ""
    for fw, fr in zip(win.factors, run.factors):
        gap = fw.goodness - fr.goodness
        if gap > best_gap:
            best_gap = gap
            best_label = fw.label
    if best_label and best_gap > 0.05:
        detail = f"{win.label} wins mainly on **{best_label.lower()}**."
    elif win.advisory_level == "All clear":
        detail = f"{win.label} is the only all-clear option."
    else:
        detail = f"All options carry some risk — {win.label} is the least exposed."
    return head, detail


def compare_destinations(
    targets: Sequence[Tuple[float, float, str]],
    *,
    inc_df: Any = None,
    poi_df: Any = None,
    geofences: Optional[Mapping] = None,
    forecaster: Any = None,
    sentinel_clusters: Optional[Sequence] = None,
    now: Optional[datetime] = None,
    depart: Optional[datetime] = None,
    radius_km: float = DEFAULT_RADIUS_KM,
) -> ComparisonResult:
    """Rank 2–5 candidate destinations into one Compass verdict."""
    now = now or datetime.utcnow()
    depart = depart or now
    incidents = _as_records(inc_df)
    pois = _as_records(poi_df)
    geo = geofences or {"features": []}

    verdicts = [
        assess_destination(
            lat, lon, label,
            incidents=incidents, pois=pois, geofences=geo,
            forecaster=forecaster, sentinel_clusters=sentinel_clusters,
            now=now, depart=depart, radius_km=radius_km,
        )
        for lat, lon, label in targets
    ]

    # Rank: compass score desc, then fewer incidents, then closer help.
    verdicts.sort(
        key=lambda v: (
            -v.compass_score,
            v.incidents_nearby,
            v.nearest_help_km if v.nearest_help_km is not None else 99.0,
        )
    )
    for i, v in enumerate(verdicts):
        v.rank = i + 1
        v.is_winner = i == 0

    head, detail = _verdict(verdicts)
    factor_order = [(f.key, f.label) for f in verdicts[0].factors] if verdicts else []

    return ComparisonResult(
        generated_at=now,
        depart=depart,
        radius_km=radius_km,
        destinations=verdicts,
        winner=verdicts[0] if verdicts else None,
        runner_up=verdicts[1] if len(verdicts) > 1 else None,
        margin=(verdicts[0].compass_score - verdicts[1].compass_score) if len(verdicts) > 1 else 0,
        verdict_headline=head,
        verdict_detail=detail,
        factor_order=factor_order,
    )


# ---------------------------------------------------------------- exports


def comparison_to_json(result: ComparisonResult) -> dict:
    """Stable, diffable JSON — share, store, or feed a downstream bot."""
    def _dest(v: DestinationVerdict) -> dict:
        return {
            "rank": v.rank,
            "label": v.label,
            "lat": v.lat,
            "lon": v.lon,
            "compass_score": v.compass_score,
            "safety_score": v.safety_score,
            "band": v.band,
            "advisory_level": v.advisory_level,
            "incidents_nearby": v.incidents_nearby,
            "nearest_help_km": v.nearest_help_km,
            "nearest_help_name": v.nearest_help_name,
            "active_geofences": list(v.active_geofences),
            "forecast_risk": v.forecast_risk,
            "best_hour": {"label": v.best_hour_label, "risk": v.best_hour_risk},
            "clusters": {
                "nearby": v.nearby_cluster_count,
                "severe": v.severe_cluster_count,
                "penalty": v.cluster_penalty,
                "top_status": v.top_cluster_status,
            },
            "factors": [asdict(f) for f in v.factors],
            "headline": v.headline,
        }

    return {
        "schema": result.schema,
        "generated_at": result.generated_at.isoformat(timespec="seconds") + "Z",
        "depart": result.depart.isoformat(timespec="minutes"),
        "radius_km": result.radius_km,
        "verdict": {
            "winner": result.winner.label if result.winner else None,
            "margin": result.margin,
            "headline": result.verdict_headline,
            "detail": result.verdict_detail,
        },
        "destinations": [_dest(v) for v in result.destinations],
    }


def comparison_to_markdown(result: ComparisonResult) -> str:
    """WhatsApp / email / Notion-paste format with a verdict + comparison table."""
    lines: List[str] = []
    lines.append("# 🧭 WaySafe Compass — Destination Showdown")
    lines.append("")
    lines.append(f"**{result.verdict_headline}**")
    if result.verdict_detail:
        lines.append("")
        lines.append(result.verdict_detail.replace("**", "*"))
    lines.append("")
    lines.append(f"_Depart {result.depart:%a %d %b %H:%M} · scan {result.radius_km:g} km_")
    lines.append("")

    # Leaderboard table
    lines.append("| # | Destination | Compass | Level | Incidents | Nearest help | Forecast |")
    lines.append("|--:|---|--:|---|--:|---|--:|")
    for v in result.destinations:
        crown = "🏆 " if v.is_winner else ""
        help_s = f"{v.nearest_help_km:.1f} km" if v.nearest_help_km is not None else "—"
        lines.append(
            f"| {v.rank} | {crown}{v.label} | **{v.compass_score}** | {v.advisory_level} "
            f"| {v.incidents_nearby} | {help_s} | {int(round(v.forecast_risk * 100))}% |"
        )
    lines.append("")

    for v in result.destinations:
        lines.append(f"## {v.rank}. {v.label} — {v.compass_score}/100 · {v.advisory_level}")
        lines.append(f"- {v.headline}")
        if v.active_geofences:
            lines.append(f"- Inside risk zone: {', '.join(v.active_geofences)}")
        if v.nearby_cluster_count:
            extra = f" ({v.severe_cluster_count} escalating)" if v.severe_cluster_count else ""
            lines.append(f"- {v.nearby_cluster_count} live cluster(s) overlapping{extra}")
        if v.best_hour_label:
            lines.append(
                f"- Safer hour here: {v.best_hour_label} "
                f"(risk {int(round((v.best_hour_risk or 0) * 100))}%)"
            )
        if v.nearest_help_name:
            lines.append(f"- Nearest help: {v.nearest_help_name} ({v.nearest_help_km:.1f} km)")
        lines.append("")

    lines.append("---")
    lines.append("_Generated by WaySafe Compass. Defer to local authorities in an emergency._")
    return "\n".join(lines)


# ---------------------------------------------------------------- self-test

if __name__ == "__main__":
    import json
    from pathlib import Path

    import pandas as pd

    from forecast import HazardForecaster
    import sentinel as sn

    root = Path(__file__).resolve().parent
    data = root / "data"
    inc = pd.read_csv(data / "incidents.csv")
    poi = pd.read_csv(data / "poi.csv")
    with open(data / "goa_geofences.geojson") as f:
        gj = json.load(f)

    now = datetime(2026, 4, 27, 22, 0)  # Sat 22:00, matches README demos
    fc = HazardForecaster(inc.to_dict("records"), now=now)
    clusters, _noise = sn.cluster_incidents(inc.to_dict("records"))

    targets = [
        (15.5500, 73.7700, "Baga"),
        (15.5387, 73.7626, "Calangute"),
        (15.5850, 73.7440, "Anjuna"),
        (15.4966, 73.8262, "Panaji"),
        (15.4020, 74.0080, "Ponda"),
    ]
    res = compare_destinations(
        targets, inc_df=inc, poi_df=poi, geofences=gj,
        forecaster=fc, sentinel_clusters=clusters,
        now=now, depart=now, radius_km=2.0,
    )
    print(f"VERDICT: {res.verdict_headline}")
    print(f"         {res.verdict_detail}\n")
    print(f"{'#':>2} {'destination':<12} {'compass':>7} {'safety':>6} "
          f"{'inc':>4} {'help':>6} {'fc%':>4}  level")
    for v in res.destinations:
        help_s = f"{v.nearest_help_km:.1f}" if v.nearest_help_km is not None else "—"
        print(f"{v.rank:>2} {v.label:<12} {v.compass_score:>7} {v.safety_score:>6} "
              f"{v.incidents_nearby:>4} {help_s:>6} "
              f"{int(round(v.forecast_risk*100)):>4}  {v.advisory_level}")
    print()
    js = comparison_to_json(res)
    assert js["schema"] == "waysafe.compass.v1"
    assert len(js["destinations"]) == 5
    assert res.destinations[0].compass_score >= res.destinations[-1].compass_score
    print("markdown bytes:", len(comparison_to_markdown(res)))
    print("json keys:", list(js.keys()))
    print("OK")
