"""Travel Advisory engine for WaySafe.

Fuses every engine in the repo — `safety.compute_safety`, the `forecast`
module, `sentinel.cluster_incidents` / `compute_risk_pulse`, the geofence
GeoJSON, and the POI table — into a single pre-trip brief tourists can
read in 30 seconds, share as JSON, or print as a polished PDF.

The brief answers four questions a tourist actually has the moment they
plan a stop:

  1. Is it safe to go there *right now*?           (advisory level + score)
  2. *Why* — what's recently happened around it?    (incident snippets + 7d trend)
  3. When would be *safer*?                        (forecast-driven depart windows)
  4. Where is the nearest help if it goes wrong?   (ranked POIs + active clusters)

Pure stdlib + reuse of project modules. No new dependencies beyond
reportlab (already in `requirements.txt` for the legacy trip PDF).
"""
from __future__ import annotations

import io
import math
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from typing import Any, Iterable, List, Mapping, Optional, Sequence, Tuple

from utils import haversine_km, point_in_polygon
from safety import (
    CATEGORY_SEVERITY,
    HELP_POI_TYPES,
    SafetyResult,
    compute_safety,
)


# ---------------------------------------------------------------- constants

# Advisory levels: ordered from worst → best, each tuple is
# (name, color, lower-bound, upper-bound) on the safety score (0–100).
_LEVEL_TABLE: List[Tuple[str, str, int, int]] = [
    ("Critical",  "#EF4444",  0,  35),
    ("Elevated",  "#F59E0B", 35,  60),
    ("Caution",   "#FBBF24", 60,  80),
    ("All clear", "#10B981", 80, 101),
]

_LEVEL_HEADLINES: dict[str, str] = {
    "Critical":  "Do not travel here right now without local authority guidance.",
    "Elevated":  "Real risk factors are active — go with care or wait for a safer window.",
    "Caution":   "Mostly safe with isolated concerns. Stay alert and prefer daylight.",
    "All clear": "Conditions look good. Standard travel precautions are enough.",
}

_LEVEL_RANK: dict[str, int] = {n: i for i, (n, *_r) in enumerate(_LEVEL_TABLE)}

DEFAULT_RADIUS_KM = 2.0
DEFAULT_LOOKBACK_DAYS = 7
DEFAULT_FORECAST_HOURS = 12


# ---------------------------------------------------------------- dataclasses


@dataclass
class IncidentSnippet:
    when: str            # human-friendly "3h ago"
    category: str
    severity: int        # 2..5
    distance_km: float
    status: str          # "verified" | "pending"
    note: str = ""
    age_hours: float = 0.0


@dataclass
class POISnippet:
    name: str
    ptype: str            # hospital | police | clinic | fire | tourist_help_desk
    distance_km: float
    lat: float
    lon: float


@dataclass
class ClusterSnippet:
    dominant_category: str
    velocity_status: str  # Critical | Emerging | Steady | Cooling
    severity_mean: float
    members: int
    distance_km: float    # centroid → target, minus cluster radius (clamped ≥0)
    radius_km: float
    days_since_last: float


@dataclass
class DepartWindow:
    start: datetime
    risk: float           # 0..1, top-cell forecast risk at this hour
    label: str            # "Mon 21:00"


@dataclass
class AdvisoryBrief:
    target_label: str
    target_lat: float
    target_lon: float
    generated_at: datetime

    advisory_level: str
    level_color: str
    level_headline: str

    safety: SafetyResult

    recent_incidents: List[IncidentSnippet] = field(default_factory=list)
    incidents_by_category: List[Tuple[str, int]] = field(default_factory=list)
    incident_trend: List[int] = field(default_factory=list)  # last `lookback_days`, oldest→newest

    active_geofences: List[str] = field(default_factory=list)
    help_pois: List[POISnippet] = field(default_factory=list)
    nearby_clusters: List[ClusterSnippet] = field(default_factory=list)

    best_windows: List[DepartWindow] = field(default_factory=list)

    risk_pulse_status: str = "Unknown"
    risk_pulse_headline: str = ""
    severe_cluster_count: int = 0

    recommendations: List[str] = field(default_factory=list)

    radius_km: float = DEFAULT_RADIUS_KM
    lookback_days: int = DEFAULT_LOOKBACK_DAYS

    @property
    def is_safe_to_go(self) -> bool:
        return self.advisory_level in ("All clear", "Caution")

    @property
    def headline(self) -> str:
        return f"{self.advisory_level} · {self.target_label}"


# ---------------------------------------------------------------- helpers


def _level_for(score: int) -> Tuple[str, str]:
    for name, color, lo, hi in _LEVEL_TABLE:
        if lo <= score < hi:
            return name, color
    return "All clear", "#10B981"


def _escalate_level(level: str, severe_clusters: int) -> Tuple[str, str]:
    """Bump the level when escalating clusters overlap the target.

    Two or more severe clusters force *Critical* even when the local
    safety score happens to be high — clusters mean things are *moving*,
    and a static score won't reflect that until the next incident.
    """
    rank = _LEVEL_RANK[level]
    if severe_clusters >= 2:
        rank = min(rank, _LEVEL_RANK["Critical"])
    elif severe_clusters >= 1:
        rank = min(rank, _LEVEL_RANK["Elevated"])
    new_level, color, _lo, _hi = _LEVEL_TABLE[rank]
    return new_level, color


def _parse_ts(s: Any) -> Optional[datetime]:
    if isinstance(s, datetime):
        return s.replace(tzinfo=None)
    try:
        return datetime.fromisoformat(str(s).replace("Z", "")).replace(tzinfo=None)
    except Exception:
        return None


def _humanize_age(dt: datetime, now: datetime) -> str:
    secs = max(0.0, (now - dt).total_seconds())
    if secs < 60:
        return "just now"
    if secs < 3600:
        return f"{int(secs // 60)}m ago"
    if secs < 86400:
        return f"{int(secs // 3600)}h ago"
    return f"{int(secs // 86400)}d ago"


def _as_records(obj: Any) -> List[Mapping]:
    if obj is None:
        return []
    if hasattr(obj, "to_dict"):
        try:
            return obj.to_dict("records")
        except Exception:
            pass
    return list(obj)


def _build_recommendations(
    *,
    level: str,
    safety: SafetyResult,
    geofences: Sequence[str],
    help_pois: Sequence[POISnippet],
    clusters: Sequence[ClusterSnippet],
    windows: Sequence[DepartWindow],
    late_night: bool,
) -> List[str]:
    """Human-actionable, ranked checklist. Ordered most-urgent first."""
    recs: List[str] = []
    if level == "Critical":
        recs.append("Postpone this trip — risk is acute. Wait for an authority all-clear or move 5+ km away.")
    elif level == "Elevated":
        recs.append("Delay if you can. If you must go, share your live location with two contacts first.")
    if geofences:
        recs.append(
            f"Inside risk zone: {', '.join(geofences)}. Detour around or contact local help before entering."
        )
    if any(c.velocity_status in ("Critical", "Emerging") for c in clusters):
        bad = next(c for c in clusters if c.velocity_status in ("Critical", "Emerging"))
        recs.append(
            f"Live activity is {bad.velocity_status.lower()} {bad.distance_km:.1f} km away "
            f"({bad.dominant_category}). Re-check the Advisory just before departure."
        )
    if help_pois:
        nearest = help_pois[0]
        recs.append(
            f"Pin the nearest {nearest.ptype.replace('_', ' ')}: **{nearest.name}** "
            f"({nearest.distance_km:.1f} km)."
        )
    if late_night and level in ("Caution", "Elevated", "Critical"):
        recs.append("Late-night window — prefer well-lit, busy streets and licensed transport.")
    if windows and level in ("Caution", "Elevated", "Critical"):
        w = windows[0]
        recs.append(
            f"Forecast best depart window: **{w.label}** "
            f"(top-cell risk {int(w.risk * 100)}%)."
        )
    if safety.incidents_nearby == 0 and not geofences and level == "All clear":
        recs.append("Standard precautions — hydration, charged phone, and a shared trip plan.")
    if not recs:
        recs.append("No critical actions. Carry ID, share your destination, and trust local signage.")
    return recs


# ---------------------------------------------------------------- build


def build_brief(
    target_lat: float,
    target_lon: float,
    target_label: str,
    *,
    inc_df: Any = None,
    poi_df: Any = None,
    geofences: Optional[Mapping] = None,
    forecaster: Any = None,
    sentinel_clusters: Optional[Sequence] = None,
    risk_pulse: Any = None,
    now: Optional[datetime] = None,
    radius_km: float = DEFAULT_RADIUS_KM,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    forecast_hours: int = DEFAULT_FORECAST_HOURS,
) -> AdvisoryBrief:
    """Build a full advisory brief around a single (lat, lon) target."""
    now = now or datetime.utcnow()
    incidents = _as_records(inc_df)
    pois = _as_records(poi_df)
    geo = geofences or {"features": []}

    safety = compute_safety(target_lat, target_lon, incidents, geo, pois, now=now)

    # Active geofences at the target
    geo_names: List[str] = []
    for feat in geo.get("features", []):
        coords = feat.get("geometry", {}).get("coordinates", [[]])
        if not coords:
            continue
        ring = coords[0]
        if point_in_polygon(target_lat, target_lon, ring):
            geo_names.append(feat.get("properties", {}).get("name", "risk zone"))

    # Recent incidents within radius + category roll-up + 7-day daily trend
    horizon = now - timedelta(days=lookback_days)
    inc_snips: List[IncidentSnippet] = []
    cat_counts: dict[str, int] = {}
    daily = [0] * lookback_days
    for r in incidents:
        try:
            ilat = float(r.get("lat")); ilon = float(r.get("lon"))
        except (TypeError, ValueError):
            continue
        d = haversine_km(target_lat, target_lon, ilat, ilon)
        if d > radius_km:
            continue
        ts = _parse_ts(r.get("created_at"))
        if ts is None or ts < horizon:
            continue
        cat = str(r.get("category", "other")).lower()
        sev = int(CATEGORY_SEVERITY.get(cat, 2))
        status = str(r.get("status", "pending"))
        age_h = max(0.0, (now - ts).total_seconds() / 3600.0)
        inc_snips.append(IncidentSnippet(
            when=_humanize_age(ts, now),
            category=cat,
            severity=sev,
            distance_km=round(d, 2),
            status=status,
            note=(str(r.get("note", "")) or "")[:160],
            age_hours=round(age_h, 1),
        ))
        cat_counts[cat] = cat_counts.get(cat, 0) + 1
        # Snap to the trend array so the daily counts always match
        # `len(inc_snips)` — incidents right at the horizon edge would
        # otherwise compute `bucket == lookback_days` and silently drop.
        bucket = int((now - ts).total_seconds() // 86400)
        bucket = max(0, min(bucket, lookback_days - 1))
        daily[lookback_days - 1 - bucket] += 1
    # Ranking: most-recent first, then by severity desc
    inc_snips.sort(key=lambda s: (s.age_hours, -s.severity))
    cat_ranked = sorted(cat_counts.items(), key=lambda kv: -kv[1])

    # Help POIs — only safety-relevant types, ranked by distance, top 5
    help_snips: List[POISnippet] = []
    for p in pois:
        try:
            lat = float(p.get("lat")); lon = float(p.get("lon"))
        except (TypeError, ValueError):
            continue
        if str(p.get("ptype", "")).lower() not in HELP_POI_TYPES:
            continue
        d = haversine_km(target_lat, target_lon, lat, lon)
        help_snips.append(POISnippet(
            name=str(p.get("name", "")),
            ptype=str(p.get("ptype", "")),
            distance_km=round(d, 2),
            lat=lat, lon=lon,
        ))
    help_snips.sort(key=lambda s: s.distance_km)
    help_snips = help_snips[:5]

    # Nearby Sentinel clusters whose disc overlaps the target's brief radius
    cluster_snips: List[ClusterSnippet] = []
    severe = 0
    for c in (sentinel_clusters or []):
        try:
            d = haversine_km(target_lat, target_lon, c.center_lat, c.center_lon)
        except AttributeError:
            continue
        if d > radius_km + c.radius_km:
            continue
        # Distance shown to the user is the *edge* distance, clamped at 0.
        edge_km = max(0.0, d - c.radius_km)
        cluster_snips.append(ClusterSnippet(
            dominant_category=c.dominant_category,
            velocity_status=c.status,
            severity_mean=float(c.severity_mean),
            members=int(c.count),
            distance_km=round(edge_km, 2),
            radius_km=round(c.radius_km, 2),
            days_since_last=round(float(c.days_since_last), 1),
        ))
        if c.status in ("Critical", "Emerging") and c.severity_mean >= 3.5:
            severe += 1
    cluster_snips.sort(key=lambda s: (s.distance_km, -s.severity_mean))

    # Forecast — top 3 lowest-risk depart hours in the next N hours
    windows: List[DepartWindow] = []
    if forecaster is not None:
        base = now.replace(minute=0, second=0, microsecond=0)
        cands: List[Tuple[float, datetime]] = []
        for k in range(1, forecast_hours + 1):
            t = base + timedelta(hours=k)
            top_risk = 0.0
            try:
                hs = forecaster.hotspots(t, k=1)
                if hs:
                    top_risk = float(hs[0].get("risk", 0.0))
            except Exception:
                top_risk = 0.0
            cands.append((top_risk, t))
        cands.sort(key=lambda x: x[0])
        for risk, t in cands[:3]:
            windows.append(DepartWindow(
                start=t,
                risk=round(risk, 3),
                label=t.strftime("%a %H:%M"),
            ))

    # Advisory level — start from local safety, escalate on severe clusters
    base_level, base_color = _level_for(safety.score)
    level, color = _escalate_level(base_level, severe)
    headline = _LEVEL_HEADLINES[level]

    late_night = now.hour >= 22 or now.hour < 5
    recs = _build_recommendations(
        level=level, safety=safety, geofences=geo_names,
        help_pois=help_snips, clusters=cluster_snips,
        windows=windows, late_night=late_night,
    )

    rp_status = "Unknown"
    rp_headline = ""
    if risk_pulse is not None:
        rp_status = getattr(risk_pulse, "status", "Unknown")
        rp_headline = getattr(risk_pulse, "headline", "") or ""

    return AdvisoryBrief(
        target_label=target_label,
        target_lat=target_lat,
        target_lon=target_lon,
        generated_at=now,
        advisory_level=level,
        level_color=color,
        level_headline=headline,
        safety=safety,
        recent_incidents=inc_snips,
        incidents_by_category=cat_ranked,
        incident_trend=daily,
        active_geofences=geo_names,
        help_pois=help_snips,
        nearby_clusters=cluster_snips,
        best_windows=windows,
        risk_pulse_status=rp_status,
        risk_pulse_headline=rp_headline,
        severe_cluster_count=severe,
        recommendations=recs,
        radius_km=radius_km,
        lookback_days=lookback_days,
    )


# ---------------------------------------------------------------- exports


def brief_to_json(brief: AdvisoryBrief) -> dict:
    """Stable JSON shape — safe to share, store, or diff between briefs."""
    return {
        "schema": "waysafe.advisory.v1",
        "target": {
            "label": brief.target_label,
            "lat": brief.target_lat,
            "lon": brief.target_lon,
        },
        "generated_at": brief.generated_at.isoformat(timespec="seconds") + "Z",
        "advisory": {
            "level": brief.advisory_level,
            "color": brief.level_color,
            "headline": brief.level_headline,
            "is_safe_to_go": brief.is_safe_to_go,
        },
        "safety": {
            "score": brief.safety.score,
            "band": brief.safety.band,
            "factors": list(brief.safety.factors),
            "nearest_help_km": brief.safety.nearest_help_km,
            "incidents_nearby": brief.safety.incidents_nearby,
        },
        "scan": {
            "radius_km": brief.radius_km,
            "lookback_days": brief.lookback_days,
            "trend_daily_counts": brief.incident_trend,
        },
        "incidents": [asdict(i) for i in brief.recent_incidents],
        "incidents_by_category": brief.incidents_by_category,
        "active_geofences": brief.active_geofences,
        "help_pois": [asdict(p) for p in brief.help_pois],
        "nearby_clusters": [asdict(c) for c in brief.nearby_clusters],
        "best_windows": [
            {"start": w.start.isoformat(timespec="minutes"),
             "risk": w.risk, "label": w.label}
            for w in brief.best_windows
        ],
        "risk_pulse": {
            "status": brief.risk_pulse_status,
            "headline": brief.risk_pulse_headline,
            "severe_cluster_count": brief.severe_cluster_count,
        },
        "recommendations": brief.recommendations,
    }


def brief_to_markdown(brief: AdvisoryBrief) -> str:
    """A compact markdown view — copy-paste-share friendly."""
    lines: List[str] = []
    push = lines.append
    push(f"# Travel Advisory · {brief.target_label}")
    push(f"_Generated {brief.generated_at:%Y-%m-%d %H:%M} UTC · "
         f"scan radius {brief.radius_km:g} km · lookback {brief.lookback_days} days_")
    push("")
    push(f"## {brief.advisory_level}")
    push(brief.level_headline)
    push("")
    push(f"- **Safety score:** {brief.safety.score} ({brief.safety.band})")
    if brief.safety.nearest_help_km is not None:
        push(f"- **Nearest help:** {brief.safety.nearest_help_km:.1f} km")
    push(f"- **Incidents in scan radius (last {brief.lookback_days}d):** "
         f"{brief.safety.incidents_nearby}")
    if brief.active_geofences:
        push(f"- **Active risk zones:** {', '.join(brief.active_geofences)}")
    push("")
    if brief.recent_incidents:
        push("## Recent incidents")
        for s in brief.recent_incidents[:8]:
            badge = "✅" if s.status == "verified" else "⏳"
            push(f"- {badge} **{s.category}** · sev {s.severity} · "
                 f"{s.distance_km:.1f} km · {s.when}")
            if s.note:
                push(f"  > {s.note}")
        push("")
    if brief.nearby_clusters:
        push("## Nearby clusters (Sentinel)")
        for c in brief.nearby_clusters[:5]:
            push(f"- **{c.dominant_category}** · {c.velocity_status} · "
                 f"{c.members} reports · {c.distance_km:.1f} km away "
                 f"· last seen {c.days_since_last:g}d ago")
        push("")
    if brief.best_windows:
        push("## Forecast — safest depart windows")
        for w in brief.best_windows:
            push(f"- **{w.label}** · top-cell risk {int(w.risk * 100)}%")
        push("")
    if brief.help_pois:
        push("## Nearest help")
        for p in brief.help_pois:
            push(f"- {p.name} · {p.ptype} · {p.distance_km:.1f} km")
        push("")
    push("## Recommendations")
    for r in brief.recommendations:
        push(f"- {r}")
    return "\n".join(lines)


# ---------------------------------------------------------------- PDF


def _hex_to_rgb01(hex_color: str) -> Tuple[float, float, float]:
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return (int(h[0:2], 16) / 255.0, int(h[2:4], 16) / 255.0, int(h[4:6], 16) / 255.0)


def brief_to_pdf(brief: AdvisoryBrief) -> bytes:
    """Render the brief as a single-page A4 PDF — clean, printable, brand-aware."""
    # Imported lazily so unit tests that only touch the JSON path don't need reportlab.
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    from reportlab.lib.units import cm

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    W, H = A4
    margin = 1.6 * cm

    # ---- Header band -- advisory color strip across the top
    band_h = 1.6 * cm
    r, g, b = _hex_to_rgb01(brief.level_color)
    c.setFillColorRGB(r, g, b)
    c.rect(0, H - band_h, W, band_h, stroke=0, fill=1)
    c.setFillColorRGB(1, 1, 1)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(margin, H - band_h + 0.45 * cm,
                 f"Travel Advisory · {brief.advisory_level}")
    c.setFont("Helvetica", 9)
    c.drawRightString(W - margin, H - band_h + 0.45 * cm,
                      f"WaySafe · {brief.generated_at:%Y-%m-%d %H:%M} UTC")

    # ---- Title block
    y = H - band_h - 0.9 * cm
    c.setFillColorRGB(0.07, 0.10, 0.16)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(margin, y, brief.target_label)
    y -= 0.55 * cm
    c.setFillColorRGB(0.30, 0.34, 0.40)
    c.setFont("Helvetica", 9)
    c.drawString(margin, y, f"({brief.target_lat:.4f}, {brief.target_lon:.4f})  "
                            f"·  scan {brief.radius_km:g} km  "
                            f"·  lookback {brief.lookback_days}d")
    y -= 0.8 * cm

    # ---- Headline
    c.setFillColorRGB(0.07, 0.10, 0.16)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(margin, y, brief.level_headline)
    y -= 0.8 * cm

    # ---- Score bar
    bar_w = W - 2 * margin
    bar_h = 0.55 * cm
    c.setFillColorRGB(0.92, 0.93, 0.96)
    c.roundRect(margin, y, bar_w, bar_h, 0.18 * cm, stroke=0, fill=1)
    pct = max(0.0, min(1.0, brief.safety.score / 100.0))
    c.setFillColorRGB(r, g, b)
    c.roundRect(margin, y, max(0.4 * cm, bar_w * pct), bar_h,
                0.18 * cm, stroke=0, fill=1)
    c.setFillColorRGB(1, 1, 1)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(margin + 0.3 * cm, y + 0.16 * cm,
                 f"Safety {brief.safety.score} / 100  ·  {brief.safety.band}")
    y -= 0.9 * cm

    # ---- Two-column layout: factors (left), help POIs (right)
    col_w = (bar_w - 0.8 * cm) / 2.0
    left_x = margin
    right_x = margin + col_w + 0.8 * cm
    col_y = y

    def _section_title(x: float, yv: float, text: str) -> float:
        c.setFillColorRGB(0.30, 0.34, 0.40)
        c.setFont("Helvetica-Bold", 8)
        c.drawString(x, yv, text.upper())
        return yv - 0.35 * cm

    # Left col: factors + geofences
    ly = _section_title(left_x, col_y, "Why this score")
    c.setFillColorRGB(0.20, 0.22, 0.28)
    c.setFont("Helvetica", 9)
    if brief.safety.factors:
        for f in brief.safety.factors[:5]:
            sign = "+" if f["impact"] > 0 else "−"
            c.drawString(left_x, ly,
                         f"{sign} {abs(f['impact']):.1f}  {f['label']}")
            ly -= 0.42 * cm
    else:
        c.drawString(left_x, ly, "No major risk factors detected.")
        ly -= 0.42 * cm

    if brief.active_geofences:
        ly = _section_title(left_x, ly - 0.1 * cm, "Risk zones at this point")
        c.setFont("Helvetica", 9)
        for name in brief.active_geofences[:4]:
            c.drawString(left_x, ly, f"• {name}")
            ly -= 0.42 * cm

    # Right col: help POIs
    ry = _section_title(right_x, col_y, "Nearest help")
    c.setFont("Helvetica", 9)
    if brief.help_pois:
        for p in brief.help_pois[:5]:
            c.drawString(right_x, ry,
                         f"• {p.name}  ({p.ptype}, {p.distance_km:.1f} km)")
            ry -= 0.42 * cm
    else:
        c.drawString(right_x, ry, "No help POIs in dataset.")
        ry -= 0.42 * cm

    if brief.best_windows:
        ry = _section_title(right_x, ry - 0.1 * cm, "Safer depart windows")
        c.setFont("Helvetica", 9)
        for w in brief.best_windows:
            c.drawString(right_x, ry,
                         f"• {w.label}  ·  top-cell risk {int(w.risk * 100)}%")
            ry -= 0.42 * cm

    y = min(ly, ry) - 0.2 * cm

    # ---- Recent incidents table
    if brief.recent_incidents:
        y = _section_title(margin, y, f"Recent incidents in scan radius (last {brief.lookback_days}d)")
        c.setFont("Helvetica", 9)
        for s in brief.recent_incidents[:6]:
            badge = "✓" if s.status == "verified" else "·"
            line = (f"{badge} {s.category:<10s}  sev {s.severity}  "
                    f"{s.distance_km:>4.1f} km   {s.when}")
            c.drawString(margin, y, line)
            if s.note:
                c.setFillColorRGB(0.40, 0.43, 0.49)
                c.setFont("Helvetica-Oblique", 8)
                c.drawString(margin + 0.4 * cm, y - 0.32 * cm, s.note[:90])
                c.setFillColorRGB(0.20, 0.22, 0.28)
                c.setFont("Helvetica", 9)
                y -= 0.74 * cm
            else:
                y -= 0.42 * cm

    # ---- Nearby clusters
    if brief.nearby_clusters:
        y = _section_title(margin, y - 0.2 * cm, "Live clusters near here")
        c.setFont("Helvetica", 9)
        for cl in brief.nearby_clusters[:4]:
            c.drawString(
                margin, y,
                f"• {cl.dominant_category:<10s}  {cl.velocity_status:<9s}  "
                f"{cl.members:>2d} reports  "
                f"{cl.distance_km:>4.1f} km away  "
                f"(r={cl.radius_km:.1f} km, last {cl.days_since_last:g}d ago)"
            )
            y -= 0.42 * cm

    # ---- Recommendations
    y = _section_title(margin, y - 0.2 * cm, "What to do")
    c.setFont("Helvetica", 9)
    for rec in brief.recommendations[:6]:
        # Strip markdown bold for PDF; reportlab doesn't render it.
        clean = rec.replace("**", "")
        # Wrap long lines manually at ~95 chars.
        if len(clean) <= 95:
            c.drawString(margin, y, f"☐  {clean}")
            y -= 0.42 * cm
        else:
            head, tail = clean[:95], clean[95:]
            c.drawString(margin, y, f"☐  {head}")
            y -= 0.42 * cm
            c.drawString(margin + 0.6 * cm, y, tail[:95])
            y -= 0.42 * cm
        if y < margin + 1.4 * cm:
            break

    # ---- Footer
    c.setFillColorRGB(0.55, 0.58, 0.62)
    c.setFont("Helvetica", 7)
    c.drawString(margin, margin,
                 "WaySafe · advisory.v1 · This brief is informational. "
                 "Always defer to local authorities in an emergency.")

    c.showPage()
    c.save()
    buf.seek(0)
    return buf.read()


# ---------------------------------------------------------------- convenience


def severity_dot(sev: int) -> str:
    """Map an incident severity 2..5 to a small colored dot character."""
    palette = {5: "🟥", 4: "🟧", 3: "🟨", 2: "🟦"}
    return palette.get(int(sev), "⬜")


def category_icon(cat: str) -> str:
    icons = {
        "accident":  "🚗",
        "flooding":  "🌊",
        "landslide": "⛰️",
        "roadblock": "🚧",
        "other":     "⚠️",
    }
    return icons.get(str(cat).lower(), "⚠️")
