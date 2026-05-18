"""Sentinel — live cluster detection + emerging-hotspot alerts.

Where the heatmap tells you *where* incidents are dense, Sentinel tells you
*what's escalating right now*. It groups raw incidents into discrete events
with DBSCAN over haversine distance, then compares each cluster's recent
incident rate against its own historical baseline to flag the ones that
are getting hotter (or cooling off).

Pure-stdlib — only depends on `utils.haversine_km` and the project's
data shapes. No sklearn, no numpy.

Pipeline
--------
1. `cluster_incidents(incidents, eps_km, min_samples, now)` →  List[Cluster]
   - DBSCAN over (lat, lon) with haversine distance.
   - For every cluster: weighted centroid (severity × recency), radius,
     dominant category, severity mean, verified frac, recent/baseline
     counts, velocity, status.
2. `compute_risk_pulse(clusters, incidents, now)` → RiskPulse
   - Global situational-awareness summary across all clusters.
3. `nearest_cluster(clusters, lat, lon)` → (cluster, distance_km)
   - For routing the "is the user near a hotspot?" question.
4. `recommended_action(cluster, lat, lon)` → str
   - Plain-English tip per cluster, tailored to the user's distance.
5. `cluster_polygon(cluster, n=32)` → list of [lon, lat]
   - Approximate halo for pydeck PolygonLayer rendering.

Velocity model
--------------
    recent_rate   = recent_count   / recent_days
    baseline_rate = baseline_count / baseline_days
    velocity      = (recent_rate + ε) / (baseline_rate + ε)         ε=0.005

    velocity ≥ 2.5         → Critical    (now > 2.5× historical)
    1.3 ≤ velocity < 2.5   → Emerging    (heating up)
    0.6 ≤ velocity < 1.3   → Steady      (active at baseline pace)
    velocity < 0.6         → Cooling     (slowing down)

A previously-dormant cluster that fires several recent incidents reads as
high velocity because the baseline floor is small — exactly what you want
for emergent-pattern detection.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Mapping, Optional, Sequence, Tuple

from utils import haversine_km

CATEGORY_SEVERITY: dict[str, int] = {
    "landslide": 5,
    "flooding":  4,
    "accident":  4,
    "roadblock": 2,
    "other":     2,
}

CATEGORY_ICON: dict[str, str] = {
    "accident":  "🚧",
    "roadblock": "🚦",
    "landslide": "⛰️",
    "flooding":  "🌊",
    "other":     "⚠️",
}

STATUS_HUE: dict[str, str] = {
    "Critical": "#FF3D60",
    "Emerging": "#FF7F50",
    "Steady":   "#F9C440",
    "Cooling":  "#53E3A6",
}

STATUS_ORDER: dict[str, int] = {"Critical": 0, "Emerging": 1, "Steady": 2, "Cooling": 3}

PULSE_ORDER: dict[str, int] = {"Critical": 0, "Active": 1, "Watch": 2, "Calm": 3}

PULSE_HUE: dict[str, str] = {
    "Critical": "#FF3D60",
    "Active":   "#FF7F50",
    "Watch":    "#F9C440",
    "Calm":     "#53E3A6",
}

DEFAULT_EPS_KM      = 0.6
DEFAULT_MIN_SAMPLES = 3
DEFAULT_RECENT_DAYS  = 14
DEFAULT_BASELINE_DAYS = 30
RECENCY_HALF_LIFE_H  = 72.0
RATE_FLOOR           = 0.005


# ---------------------------------------------------------------- helpers


def _parse_ts(s) -> Optional[datetime]:
    if isinstance(s, datetime):
        return s.replace(tzinfo=None)
    if s is None:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "")).replace(tzinfo=None)
    except Exception:
        return None


def _coerce_points(incidents: Sequence[Mapping]) -> List[dict]:
    """Filter to incidents that parse cleanly and stamp normalized fields."""
    out: List[dict] = []
    for r in incidents:
        try:
            lat = float(r.get("lat"))
            lon = float(r.get("lon"))
        except (TypeError, ValueError):
            continue
        ts = _parse_ts(r.get("created_at", ""))
        if ts is None:
            continue
        cat = str(r.get("category", "other")).lower()
        out.append({
            "id":         r.get("id"),
            "lat":        lat,
            "lon":        lon,
            "category":   cat,
            "severity":   CATEGORY_SEVERITY.get(cat, 2),
            "status":     str(r.get("status", "")).lower(),
            "verified":   str(r.get("status", "")).lower() == "verified",
            "note":       r.get("note", ""),
            "created_at": ts,
            "_raw":       r,
        })
    return out


def _recency_weight(ts: datetime, now: datetime) -> float:
    hours = max(0.0, (now - ts).total_seconds() / 3600.0)
    return 0.5 ** (hours / RECENCY_HALF_LIFE_H)


# ---------------------------------------------------------------- DBSCAN


def dbscan_haversine(
    points: Sequence[Tuple[float, float]],
    eps_km: float,
    min_samples: int,
) -> List[int]:
    """Pure-stdlib DBSCAN over haversine distance.

    Returns one integer label per input point. -1 means *noise* (no cluster).
    Cluster ids are 0, 1, 2, ... in discovery order.

    Standard textbook DBSCAN: pick an unvisited point, find its ε-neighbours.
    If it's a core point (≥ min_samples in its ε-ball, counting itself), grow
    a cluster by transitively absorbing every reachable point. Border points
    are absorbed by the first cluster that reaches them.
    """
    n = len(points)
    labels = [-1] * n
    visited = [False] * n

    def neighbors(i: int) -> List[int]:
        out: List[int] = []
        lat_i, lon_i = points[i]
        for j in range(n):
            if i == j:
                continue
            lat_j, lon_j = points[j]
            if haversine_km(lat_i, lon_i, lat_j, lon_j) <= eps_km:
                out.append(j)
        return out

    cid = 0
    for i in range(n):
        if visited[i]:
            continue
        visited[i] = True
        nbrs = neighbors(i)
        if len(nbrs) + 1 < min_samples:
            # noise for now — may get reabsorbed as a border point below
            labels[i] = -1
            continue

        labels[i] = cid
        # grow the cluster via a worklist of indices to inspect
        seeds = list(nbrs)
        seen = set(seeds)
        seen.add(i)
        k = 0
        while k < len(seeds):
            j = seeds[k]
            k += 1
            if not visited[j]:
                visited[j] = True
                jnbrs = neighbors(j)
                if len(jnbrs) + 1 >= min_samples:
                    for jn in jnbrs:
                        if jn not in seen:
                            seen.add(jn)
                            seeds.append(jn)
            if labels[j] < 0:
                labels[j] = cid
        cid += 1
    return labels


# ---------------------------------------------------------------- Cluster


@dataclass
class Cluster:
    id: int
    center_lat: float
    center_lon: float
    radius_km: float
    members: List[dict] = field(default_factory=list)

    # demographics
    count: int = 0
    dominant_category: str = "other"
    category_mix: List[Tuple[str, int]] = field(default_factory=list)
    severity_mean: float = 0.0
    verified_frac: float = 0.0

    # temporal
    recent_count: int = 0
    baseline_count: int = 0
    recent_window_days: int = DEFAULT_RECENT_DAYS
    baseline_window_days: int = DEFAULT_BASELINE_DAYS
    recent_rate: float = 0.0
    baseline_rate: float = 0.0
    velocity: float = 0.0
    status: str = "Steady"
    last_seen: Optional[datetime] = None
    days_since_last: float = 0.0

    # presentational
    peak_hour: Optional[int] = None
    daily_counts: List[int] = field(default_factory=list)  # last recent_window_days, oldest→newest

    @property
    def status_hue(self) -> str:
        return STATUS_HUE.get(self.status, "#8892A6")

    @property
    def icon(self) -> str:
        return CATEGORY_ICON.get(self.dominant_category, "⚠️")

    @property
    def label(self) -> str:
        return f"Cluster #{self.id + 1} · {self.dominant_category.title()}"


def _centroid_weighted(members: Sequence[dict], now: datetime) -> Tuple[float, float]:
    """Severity × recency weighted mean. Falls back to plain mean if all
    weights are zero (e.g. very old incidents)."""
    sw = lw_lat = lw_lon = 0.0
    for m in members:
        w = m["severity"] * _recency_weight(m["created_at"], now)
        sw += w
        lw_lat += w * m["lat"]
        lw_lon += w * m["lon"]
    if sw <= 1e-9:
        sw = len(members) or 1
        lw_lat = sum(m["lat"] for m in members)
        lw_lon = sum(m["lon"] for m in members)
    return lw_lat / sw, lw_lon / sw


def _classify_velocity(velocity: float, recent_count: int) -> str:
    if recent_count == 0:
        return "Cooling"
    if velocity >= 2.5:
        return "Critical"
    if velocity >= 1.3:
        return "Emerging"
    if velocity >= 0.6:
        return "Steady"
    return "Cooling"


def _daily_counts(members: Sequence[dict], now: datetime, days: int) -> List[int]:
    """Per-day counts over the last `days` days, oldest first."""
    out = [0] * days
    for m in members:
        age_days = (now - m["created_at"]).total_seconds() / 86400.0
        if age_days < 0 or age_days >= days:
            continue
        bucket = days - 1 - int(age_days)
        if 0 <= bucket < days:
            out[bucket] += 1
    return out


def _peak_hour(members: Sequence[dict]) -> Optional[int]:
    if not members:
        return None
    buckets = [0] * 24
    for m in members:
        buckets[m["created_at"].hour] += 1
    if max(buckets) == 0:
        return None
    return buckets.index(max(buckets))


def _summarize_cluster(
    cid: int,
    members: List[dict],
    *,
    now: datetime,
    recent_days: int,
    baseline_days: int,
) -> Cluster:
    members = sorted(members, key=lambda m: m["created_at"], reverse=True)

    c_lat, c_lon = _centroid_weighted(members, now)
    radius = max((haversine_km(c_lat, c_lon, m["lat"], m["lon"]) for m in members), default=0.0)

    # category mix
    cat_count: dict[str, int] = {}
    for m in members:
        cat_count[m["category"]] = cat_count.get(m["category"], 0) + 1
    mix = sorted(cat_count.items(), key=lambda kv: -kv[1])
    dominant = mix[0][0] if mix else "other"

    sev_mean = sum(m["severity"] for m in members) / len(members)
    verified_frac = sum(1 for m in members if m["verified"]) / len(members)

    # temporal split
    recent_cut = now.timestamp() - recent_days * 86400
    baseline_cut = recent_cut - baseline_days * 86400
    recent_count = sum(1 for m in members if m["created_at"].timestamp() >= recent_cut)
    baseline_count = sum(
        1 for m in members
        if baseline_cut <= m["created_at"].timestamp() < recent_cut
    )
    recent_rate = recent_count / max(recent_days, 1)
    baseline_rate = baseline_count / max(baseline_days, 1)
    velocity = (recent_rate + RATE_FLOOR) / (baseline_rate + RATE_FLOOR)

    status = _classify_velocity(velocity, recent_count)

    last_seen = members[0]["created_at"]
    days_since = max(0.0, (now - last_seen).total_seconds() / 86400.0)

    return Cluster(
        id=cid,
        center_lat=round(c_lat, 6),
        center_lon=round(c_lon, 6),
        radius_km=round(radius, 3),
        members=members,
        count=len(members),
        dominant_category=dominant,
        category_mix=mix,
        severity_mean=round(sev_mean, 2),
        verified_frac=round(verified_frac, 3),
        recent_count=recent_count,
        baseline_count=baseline_count,
        recent_window_days=recent_days,
        baseline_window_days=baseline_days,
        recent_rate=round(recent_rate, 4),
        baseline_rate=round(baseline_rate, 4),
        velocity=round(velocity, 3),
        status=status,
        last_seen=last_seen,
        days_since_last=round(days_since, 2),
        peak_hour=_peak_hour(members),
        daily_counts=_daily_counts(members, now, recent_days),
    )


def cluster_incidents(
    incidents: Sequence[Mapping],
    *,
    eps_km: float = DEFAULT_EPS_KM,
    min_samples: int = DEFAULT_MIN_SAMPLES,
    recent_days: int = DEFAULT_RECENT_DAYS,
    baseline_days: int = DEFAULT_BASELINE_DAYS,
    now: Optional[datetime] = None,
) -> Tuple[List[Cluster], List[dict]]:
    """Top-level Sentinel entry point.

    Returns (clusters, noise_incidents). The noise list lets the UI still show
    the unclustered points faintly on the map.
    """
    now = now or datetime.utcnow()
    pts = _coerce_points(incidents)
    if not pts:
        return [], []

    coords = [(p["lat"], p["lon"]) for p in pts]
    labels = dbscan_haversine(coords, eps_km=eps_km, min_samples=min_samples)

    buckets: dict[int, List[dict]] = {}
    noise: List[dict] = []
    for label, p in zip(labels, pts):
        if label < 0:
            noise.append(p)
        else:
            buckets.setdefault(label, []).append(p)

    clusters: List[Cluster] = []
    for label, members in buckets.items():
        clusters.append(_summarize_cluster(
            label, members, now=now,
            recent_days=recent_days, baseline_days=baseline_days,
        ))

    # Stable, useful sort: status priority, then recent count desc, then total count desc
    clusters.sort(key=lambda c: (STATUS_ORDER.get(c.status, 9), -c.recent_count, -c.count))
    # Re-number ids 1..n by display order so the UI shows them tidily
    for i, c in enumerate(clusters):
        c.id = i

    return clusters, noise


# ---------------------------------------------------------------- pulse


@dataclass
class RiskPulse:
    status: str = "Calm"
    n_clusters: int = 0
    n_critical: int = 0
    n_emerging: int = 0
    n_steady: int = 0
    n_cooling: int = 0

    last_24h_count: int = 0
    last_72h_count: int = 0
    recent_window_count: int = 0
    baseline_window_count: int = 0
    velocity: float = 0.0

    dominant_category: Optional[str] = None
    headline: str = ""
    recent_days: int = DEFAULT_RECENT_DAYS
    baseline_days: int = DEFAULT_BASELINE_DAYS

    @property
    def hue(self) -> str:
        return PULSE_HUE.get(self.status, "#8892A6")


def compute_risk_pulse(
    clusters: Sequence[Cluster],
    incidents: Sequence[Mapping],
    *,
    now: Optional[datetime] = None,
    recent_days: int = DEFAULT_RECENT_DAYS,
    baseline_days: int = DEFAULT_BASELINE_DAYS,
) -> RiskPulse:
    now = now or datetime.utcnow()

    n_critical = sum(1 for c in clusters if c.status == "Critical")
    n_emerging = sum(1 for c in clusters if c.status == "Emerging")
    n_steady   = sum(1 for c in clusters if c.status == "Steady")
    n_cooling  = sum(1 for c in clusters if c.status == "Cooling")

    pts = _coerce_points(incidents)
    last_24h = sum(1 for p in pts if (now - p["created_at"]).total_seconds() <= 86400)
    last_72h = sum(1 for p in pts if (now - p["created_at"]).total_seconds() <= 3 * 86400)

    recent_cut = now.timestamp() - recent_days * 86400
    baseline_cut = recent_cut - baseline_days * 86400
    rwc = sum(1 for p in pts if p["created_at"].timestamp() >= recent_cut)
    bwc = sum(
        1 for p in pts
        if baseline_cut <= p["created_at"].timestamp() < recent_cut
    )
    recent_rate = rwc / max(recent_days, 1)
    baseline_rate = bwc / max(baseline_days, 1)
    velocity = (recent_rate + RATE_FLOOR) / (baseline_rate + RATE_FLOOR)

    # category mix across emerging+critical clusters; falls back to all-recent mix
    cat_count: dict[str, int] = {}
    target = [c for c in clusters if c.status in ("Critical", "Emerging")]
    for c in target:
        for cat, n in c.category_mix:
            cat_count[cat] = cat_count.get(cat, 0) + n
    if not cat_count:
        for p in pts:
            if p["created_at"].timestamp() >= recent_cut:
                cat_count[p["category"]] = cat_count.get(p["category"], 0) + 1
    dominant = max(cat_count.items(), key=lambda kv: kv[1])[0] if cat_count else None

    # overall status
    if n_critical >= 1:
        status = "Critical"
    elif n_emerging >= 2:
        status = "Active"
    elif n_emerging >= 1 or n_steady >= 3:
        status = "Watch"
    else:
        status = "Calm"

    headline_bits = []
    if n_critical:
        headline_bits.append(f"{n_critical} critical")
    if n_emerging:
        headline_bits.append(f"{n_emerging} emerging")
    if not headline_bits:
        if n_steady:
            headline_bits.append(f"{n_steady} steady")
        else:
            headline_bits.append("no live clusters")
    headline = " · ".join(headline_bits)
    if dominant and (n_critical or n_emerging):
        headline += f" · mostly {CATEGORY_ICON.get(dominant, '')} {dominant}"

    return RiskPulse(
        status=status,
        n_clusters=len(clusters),
        n_critical=n_critical,
        n_emerging=n_emerging,
        n_steady=n_steady,
        n_cooling=n_cooling,
        last_24h_count=last_24h,
        last_72h_count=last_72h,
        recent_window_count=rwc,
        baseline_window_count=bwc,
        velocity=round(velocity, 3),
        dominant_category=dominant,
        headline=headline,
        recent_days=recent_days,
        baseline_days=baseline_days,
    )


# ---------------------------------------------------------------- utilities


def nearest_cluster(
    clusters: Sequence[Cluster],
    lat: float,
    lon: float,
) -> Optional[Tuple[Cluster, float]]:
    """Return (cluster, edge_distance_km) — edge distance is haversine to the
    *boundary* of the cluster (0 if the user is inside), so a downstream UI
    can say "you're 0.4 km from the nearest hotspot edge"."""
    if not clusters:
        return None
    best: Optional[Tuple[Cluster, float]] = None
    for c in clusters:
        d_center = haversine_km(lat, lon, c.center_lat, c.center_lon)
        d_edge = max(0.0, d_center - c.radius_km)
        if best is None or d_edge < best[1]:
            best = (c, round(d_edge, 3))
    return best


def recommended_action(cluster: Cluster, lat: float, lon: float) -> str:
    d_center = haversine_km(lat, lon, cluster.center_lat, cluster.center_lon)
    inside = d_center <= cluster.radius_km
    if inside and cluster.status in ("Critical", "Emerging"):
        return (
            f"⚠️  You are **inside** a {cluster.status.lower()} {cluster.dominant_category} hotspot — "
            f"leave the area or move toward the nearest help POI."
        )
    if inside:
        return f"You are inside a {cluster.status.lower()} cluster — stay alert and avoid lingering."
    if d_center - cluster.radius_km <= 1.5 and cluster.status in ("Critical", "Emerging"):
        return (
            f"You're {d_center - cluster.radius_km:.2f} km from a {cluster.status.lower()} hotspot — "
            f"reroute via Plan Route (safest) to skirt it."
        )
    if cluster.status == "Cooling":
        return "Cluster is cooling off — historically active, currently quiet."
    if cluster.status == "Steady":
        return "Stable activity at historical baseline — exercise normal caution."
    return f"Monitor — {cluster.status.lower()} at {cluster.velocity:.1f}× baseline."


def cluster_polygon(c: Cluster, n: int = 32, *, min_radius_km: float = 0.18) -> List[List[float]]:
    """Approximate circle around the cluster centroid in [lon, lat] order for
    pydeck PolygonLayer. Bumped to a floor radius so single-point or
    tightly-packed clusters still render as a visible halo."""
    r = max(c.radius_km, min_radius_km)
    lat0 = c.center_lat
    lon0 = c.center_lon
    lat_per_km = 1.0 / 110.574
    lon_per_km = 1.0 / (111.320 * max(0.01, math.cos(math.radians(lat0))))
    out: List[List[float]] = []
    for k in range(n):
        ang = 2 * math.pi * k / n
        dlat = r * math.sin(ang) * lat_per_km
        dlon = r * math.cos(ang) * lon_per_km
        out.append([lon0 + dlon, lat0 + dlat])
    out.append(out[0])
    return out


def cluster_brief_md(c: Cluster) -> str:
    """Compact markdown briefing for a single cluster."""
    mix = ", ".join(f"{CATEGORY_ICON.get(cat, '·')} {cat} ×{n}" for cat, n in c.category_mix[:4])
    last = c.last_seen.strftime("%a %d %b · %H:%M") if c.last_seen else "—"
    peak = f"{c.peak_hour:02d}:00" if c.peak_hour is not None else "—"
    return (
        f"### {c.icon} {c.label}  ·  *{c.status}*  ·  ×{c.velocity:.2f} baseline\n\n"
        f"- **Center**: `{c.center_lat:.4f}, {c.center_lon:.4f}` · radius **{c.radius_km:g} km**\n"
        f"- **Members**: {c.count} ({c.recent_count} in last {c.recent_window_days}d "
        f"vs {c.baseline_count} in prior {c.baseline_window_days}d)\n"
        f"- **Mix**: {mix}\n"
        f"- **Avg severity**: {c.severity_mean:.1f}/5 · **verified**: {c.verified_frac*100:.0f}%\n"
        f"- **Last seen**: {last} ({c.days_since_last:.1f} d ago) · peak hour {peak}\n"
    )
