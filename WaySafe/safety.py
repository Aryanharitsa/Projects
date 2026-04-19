"""Safety Intelligence engine for WaySafe.

Computes a 0-100 composite safety score for a location using geofences,
recent incidents (recency-decayed, severity-weighted, verification-boosted),
time-of-day, and help-POI density. Also emits weighted points for a
pydeck HeatmapLayer.

Pure-Python, no heavy deps — only stdlib + the project's utils helpers.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Mapping, Sequence

from utils import haversine_km, point_in_polygon

CATEGORY_SEVERITY: dict[str, int] = {
    "landslide": 5,
    "flooding":  4,
    "accident":  4,
    "roadblock": 2,
    "other":     2,
}

RECENCY_HALF_LIFE_H = 72.0
INCIDENT_RADIUS_KM  = 3.0
POI_RADIUS_KM       = 2.0
HELP_POI_TYPES      = {"hospital", "police", "clinic", "fire", "tourist_help_desk"}


@dataclass
class SafetyResult:
    score: int
    band: str
    factors: List[dict] = field(default_factory=list)
    nearest_help_km: float | None = None
    incidents_nearby: int = 0


def _parse_ts(s: str) -> datetime:
    try:
        return datetime.fromisoformat(str(s).replace("Z", "")).replace(tzinfo=None)
    except Exception:
        return datetime.utcnow()


def _recency_weight(ts: str, now: datetime) -> float:
    hours = max(0.0, (now - _parse_ts(ts)).total_seconds() / 3600.0)
    return 0.5 ** (hours / RECENCY_HALF_LIFE_H)


def _distance_weight(d_km: float, radius_km: float) -> float:
    if d_km >= radius_km:
        return 0.0
    return 0.5 * (1.0 + math.cos(math.pi * (d_km / radius_km)))


def _band(score: int) -> str:
    if score >= 80: return "Safe"
    if score >= 60: return "Caution"
    if score >= 35: return "High Risk"
    return "Danger"


def compute_safety(
    lat: float,
    lon: float,
    incidents: Sequence[Mapping],
    geofences: Mapping,
    pois: Sequence[Mapping],
    now: datetime | None = None,
) -> SafetyResult:
    now = now or datetime.utcnow()
    factors: List[dict] = []
    penalty = 0.0

    geo_hits = [
        feat.get("properties", {}).get("name", "risk zone")
        for feat in geofences.get("features", [])
        if point_in_polygon(lat, lon, feat["geometry"]["coordinates"][0])
    ]
    if geo_hits:
        p = 25.0
        penalty += p
        factors.append({"label": f"Geofenced risk zone ({', '.join(geo_hits)})", "impact": -p})

    inc_pen = 0.0
    inc_count = 0
    for r in incidents:
        try:
            ilat = float(r.get("lat")); ilon = float(r.get("lon"))
        except (TypeError, ValueError):
            continue
        d = haversine_km(lat, lon, ilat, ilon)
        if d > INCIDENT_RADIUS_KM:
            continue
        inc_count += 1
        sev = CATEGORY_SEVERITY.get(str(r.get("category", "other")).lower(), 2)
        rec = _recency_weight(str(r.get("created_at", "")), now)
        dist_w = _distance_weight(d, INCIDENT_RADIUS_KM)
        verified_bump = 1.5 if str(r.get("status")) == "verified" else 1.0
        inc_pen += sev * rec * dist_w * verified_bump * 1.6
    inc_pen = min(inc_pen, 55.0)
    if inc_pen > 0:
        penalty += inc_pen
        factors.append({
            "label": f"{inc_count} recent incident(s) within {INCIDENT_RADIUS_KM:g} km",
            "impact": -round(inc_pen, 1),
        })

    if now.hour >= 22 or now.hour < 5:
        p = 8.0
        penalty += p
        factors.append({"label": "Late-night travel window", "impact": -p})

    nearest = None
    help_near = 0
    for poi in pois:
        try:
            plat = float(poi.get("lat")); plon = float(poi.get("lon"))
        except (TypeError, ValueError):
            continue
        d = haversine_km(lat, lon, plat, plon)
        nearest = d if nearest is None else min(nearest, d)
        if str(poi.get("ptype", "")).lower() in HELP_POI_TYPES and d <= POI_RADIUS_KM:
            help_near += 1
    bonus = min(help_near * 3.0, 9.0)
    if bonus > 0:
        penalty -= bonus
        factors.append({
            "label": f"{help_near} help POI(s) within {POI_RADIUS_KM:g} km",
            "impact": +bonus,
        })

    score = int(round(max(0.0, min(100.0, 100.0 - penalty))))
    factors.sort(key=lambda f: -abs(f["impact"]))
    return SafetyResult(
        score=score,
        band=_band(score),
        factors=factors,
        nearest_help_km=round(nearest, 2) if nearest is not None else None,
        incidents_nearby=inc_count,
    )


def heatmap_points(incidents: Sequence[Mapping], now: datetime | None = None) -> List[dict]:
    """Severity × recency × verified-bump weighted points for pydeck HeatmapLayer."""
    now = now or datetime.utcnow()
    out: List[dict] = []
    for r in incidents:
        try:
            lat = float(r.get("lat")); lon = float(r.get("lon"))
        except (TypeError, ValueError):
            continue
        sev = CATEGORY_SEVERITY.get(str(r.get("category", "other")).lower(), 2)
        rec = _recency_weight(str(r.get("created_at", "")), now)
        bump = 1.4 if str(r.get("status")) == "verified" else 1.0
        out.append({"lat": lat, "lon": lon, "weight": sev * rec * bump})
    return out
