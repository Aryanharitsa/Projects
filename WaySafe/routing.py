"""Risk-aware route planner for WaySafe.

A pure-Python A* search over a regular lat/lon grid that snaps origin and
destination to the nearest cell. Edge cost is

    cost(u, v) = haversine_km(u, v) * (1 + alpha * risk(midpoint))

where `risk` is the point-risk in [0, 1] returned by `safety.point_risk`
and `alpha >= 0` controls how strongly the planner avoids unsafe areas.

`alpha = 0`  -> shortest path (a great-circle staircase on the grid).
`alpha ~ 2`  -> "safest" path: detours noticeably to dodge geofences and
                clusters of recent verified incidents, hugs help-POIs
                because they reduce risk locally.

Two route modes are exposed: `plan_fastest_route` and `plan_safest_route`.
Both return the same `RouteResult` shape so the UI can compare them
side-by-side.
"""
from __future__ import annotations

import heapq
import math
import xml.sax.saxutils as _xml
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, List, Mapping, Sequence, Tuple

from utils import haversine_km
from safety import point_risk


GRID_TARGET_CELLS = 56
GRID_PADDING_KM = 1.5
GRID_MIN_SPAN_DEG = 0.012
AVG_TRAVEL_KMH = 32.0


@dataclass
class RouteResult:
    mode: str                       # "fastest" | "safest"
    coords: List[Tuple[float, float]]   # [(lat, lon), ...]
    distance_km: float
    eta_minutes: float
    avg_safety: int                 # 0..100 (higher = safer)
    min_safety: int                 # along the path
    max_risk_segment_km: float      # length of the riskiest 200m+ stretch
    risk_samples: List[Tuple[float, float, float]] = field(default_factory=list)
    # ^ (lat, lon, risk_0_1) sampled along path — used for the heatmap overlay
    notes: List[str] = field(default_factory=list)


def _grid_axes(
    lat1: float, lon1: float, lat2: float, lon2: float,
) -> Tuple[List[float], List[float], float]:
    """Build a square-ish grid bounding (origin, dest) padded by ~1.5 km."""
    lat_lo, lat_hi = sorted((lat1, lat2))
    lon_lo, lon_hi = sorted((lon1, lon2))
    lat_pad = GRID_PADDING_KM / 111.0
    lon_pad = GRID_PADDING_KM / (111.0 * max(0.2, math.cos(math.radians((lat_lo + lat_hi) / 2))))
    lat_lo -= lat_pad; lat_hi += lat_pad
    lon_lo -= lon_pad; lon_hi += lon_pad
    span_lat = max(GRID_MIN_SPAN_DEG, lat_hi - lat_lo)
    span_lon = max(GRID_MIN_SPAN_DEG, lon_hi - lon_lo)
    n = GRID_TARGET_CELLS
    step = max(span_lat / n, span_lon / n)
    lat_steps = max(8, int(math.ceil(span_lat / step)))
    lon_steps = max(8, int(math.ceil(span_lon / step)))
    lats = [lat_lo + i * span_lat / lat_steps for i in range(lat_steps + 1)]
    lons = [lon_lo + j * span_lon / lon_steps for j in range(lon_steps + 1)]
    return lats, lons, step


def _snap(value: float, axis: List[float]) -> int:
    lo, hi = 0, len(axis) - 1
    while lo < hi:
        mid = (lo + hi) // 2
        if axis[mid] < value:
            lo = mid + 1
        else:
            hi = mid
    if lo > 0 and abs(axis[lo - 1] - value) < abs(axis[lo] - value):
        return lo - 1
    return lo


def _neighbours(i: int, j: int, ni: int, nj: int):
    for di, dj in ((-1, 0), (1, 0), (0, -1), (0, 1),
                   (-1, -1), (-1, 1), (1, -1), (1, 1)):
        ii, jj = i + di, j + dj
        if 0 <= ii < ni and 0 <= jj < nj:
            yield ii, jj


def _astar(
    lats: List[float], lons: List[float],
    start: Tuple[int, int], goal: Tuple[int, int],
    risk_fn: Callable[[float, float], float],
    alpha: float,
) -> List[Tuple[int, int]]:
    ni, nj = len(lats), len(lons)
    g_lat, g_lon = lats[goal[0]], lons[goal[1]]
    open_heap: List[Tuple[float, int, Tuple[int, int]]] = []
    counter = 0
    heapq.heappush(open_heap, (0.0, counter, start))
    came_from: dict = {}
    g_score: dict = {start: 0.0}

    while open_heap:
        _, _, current = heapq.heappop(open_heap)
        if current == goal:
            path = [current]
            while current in came_from:
                current = came_from[current]
                path.append(current)
            path.reverse()
            return path
        ci, cj = current
        c_lat, c_lon = lats[ci], lons[cj]
        for ni_, nj_ in _neighbours(ci, cj, ni, nj):
            n_lat, n_lon = lats[ni_], lons[nj_]
            mid_lat = (c_lat + n_lat) / 2
            mid_lon = (c_lon + n_lon) / 2
            edge_km = haversine_km(c_lat, c_lon, n_lat, n_lon)
            r_mid = risk_fn(mid_lat, mid_lon)
            cost = edge_km * (1.0 + alpha * r_mid)
            tentative = g_score[current] + cost
            key = (ni_, nj_)
            if tentative < g_score.get(key, float("inf")):
                came_from[key] = current
                g_score[key] = tentative
                h = haversine_km(n_lat, n_lon, g_lat, g_lon)
                counter += 1
                heapq.heappush(open_heap, (tentative + h, counter, key))
    return []


def _summarise(
    coords: List[Tuple[float, float]],
    risk_fn: Callable[[float, float], float],
) -> Tuple[float, int, int, float, List[Tuple[float, float, float]]]:
    if len(coords) < 2:
        return 0.0, 100, 100, 0.0, []
    samples: List[Tuple[float, float, float]] = []
    total_km = 0.0
    risks: List[float] = []
    seg_lengths: List[float] = []
    for (la, lo), (lb, lob) in zip(coords, coords[1:]):
        seg = haversine_km(la, lo, lb, lob)
        mid_lat = (la + lb) / 2
        mid_lon = (lo + lob) / 2
        r = risk_fn(mid_lat, mid_lon)
        samples.append((mid_lat, mid_lon, r))
        risks.append(r)
        seg_lengths.append(seg)
        total_km += seg

    if total_km <= 0:
        return 0.0, 100, 100, 0.0, samples

    weighted_risk = sum(r * s for r, s in zip(risks, seg_lengths)) / total_km
    avg_safety = int(round(max(0.0, min(100.0, 100.0 * (1.0 - weighted_risk)))))
    min_safety = int(round(max(0.0, min(100.0, 100.0 * (1.0 - max(risks))))))

    danger_km = sum(s for r, s in zip(risks, seg_lengths) if r >= 0.45)
    return total_km, avg_safety, min_safety, danger_km, samples


def _route_notes(distance_km: float, danger_km: float, avg_safety: int) -> List[str]:
    notes: List[str] = []
    if avg_safety >= 80:
        notes.append("Safe corridor end-to-end.")
    elif avg_safety >= 60:
        notes.append("Mostly safe — exercise normal caution.")
    elif avg_safety >= 35:
        notes.append("Risky stretches — daylight travel advised.")
    else:
        notes.append("High-risk path — consider postponing or escort.")
    if danger_km >= 0.5:
        notes.append(f"~{danger_km:.1f} km through elevated-risk segments.")
    if distance_km < 0.4:
        notes.append("Short hop — within walking range.")
    return notes


def _plan(
    origin: Tuple[float, float],
    dest: Tuple[float, float],
    incidents: Sequence[Mapping],
    geofences: Mapping,
    pois: Sequence[Mapping],
    *,
    mode: str,
    alpha: float,
    now: datetime | None = None,
) -> RouteResult:
    now = now or datetime.utcnow()

    cache: dict = {}

    def risk_fn(lat: float, lon: float) -> float:
        key = (round(lat, 4), round(lon, 4))
        v = cache.get(key)
        if v is None:
            v = point_risk(lat, lon, incidents, geofences, pois, now=now)
            cache[key] = v
        return v

    lats, lons, _ = _grid_axes(origin[0], origin[1], dest[0], dest[1])
    s = (_snap(origin[0], lats), _snap(origin[1], lons))
    g = (_snap(dest[0], lats),   _snap(dest[1], lons))

    if s == g:
        coords = [origin, dest]
    else:
        path_idx = _astar(lats, lons, s, g, risk_fn, alpha)
        if not path_idx:
            coords = [origin, dest]
        else:
            coords = [origin]
            coords.extend((lats[i], lons[j]) for i, j in path_idx[1:-1])
            coords.append(dest)

    total_km, avg_safety, min_safety, danger_km, samples = _summarise(coords, risk_fn)
    eta = (total_km / max(1.0, AVG_TRAVEL_KMH)) * 60.0
    notes = _route_notes(total_km, danger_km, avg_safety)
    return RouteResult(
        mode=mode,
        coords=coords,
        distance_km=round(total_km, 2),
        eta_minutes=round(eta, 1),
        avg_safety=avg_safety,
        min_safety=min_safety,
        max_risk_segment_km=round(danger_km, 2),
        risk_samples=samples,
        notes=notes,
    )


def plan_fastest_route(origin, dest, incidents, geofences, pois, now=None) -> RouteResult:
    return _plan(origin, dest, incidents, geofences, pois,
                 mode="fastest", alpha=0.0, now=now)


def plan_safest_route(origin, dest, incidents, geofences, pois, now=None) -> RouteResult:
    return _plan(origin, dest, incidents, geofences, pois,
                 mode="safest", alpha=4.5, now=now)


def to_gpx(route: RouteResult, name: str = "WaySafe route") -> str:
    """Serialise a route to GPX 1.1 — works with every map app."""
    pts = "\n".join(
        f'    <trkpt lat="{lat:.6f}" lon="{lon:.6f}"/>'
        for lat, lon in route.coords
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<gpx version="1.1" creator="WaySafe" '
        'xmlns="http://www.topografix.com/GPX/1/1">\n'
        f'  <metadata><name>{_xml.escape(name)}</name></metadata>\n'
        f'  <trk><name>{_xml.escape(route.mode)}</name><trkseg>\n'
        f'{pts}\n'
        '  </trkseg></trk>\n'
        '</gpx>\n'
    )
