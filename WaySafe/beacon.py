"""Beacon — Group Safety Coordinator for WaySafe (Day 61).

Every other WaySafe surface treats the traveller as a single point. **Beacon
is the first surface that thinks in terms of a *group*** — a family, a
student trip, a business team, a tour party of 2–6 people who have
temporarily split up and need to regroup safely.

Beacon answers three questions a single-point engine can't:

  1. **How is the group as a whole doing right now?** Not just the worst
     member, not just the average — a composite that penalises *spread*
     (a group whose members are 4 km apart in different risk bands is
     materially less coordinated than the same members 200 m apart).
  2. **Where should we meet?** Not the centroid (that's a geometric trick
     that ignores risk) and not the nearest help POI (that's only safe
     if the *paths* to it are safe). Beacon evaluates every plausible
     meet-point — the centroid, top help POIs, and a coarse safe-grid
     sample — and ranks them by a four-factor blend: **safety at the
     point**, the **worst path-risk** any member faces walking there,
     the **max walk** for the slowest member, and the **sum of walks**
     (load-shedding).
  3. **What's the per-member plan?** For the chosen meet-point we draw
     a rendezvous **corridor** from each member, sampled at 8 waypoints
     so the UI can paint it as a risk-graded polyline, and we surface
     per-member alerts — who's in danger, who's most isolated, whose
     corridor crosses a geofence.

Pure-stdlib + reuse of `safety.compute_safety` and `safety.point_risk` —
zero new physics. Beacon is a *composer* in the same family as Pulse
(Day 56) and the Day-59/60 Pulses in SynapseOS and Titan: every number
comes from an engine that already shipped. The new thing it brings is
the **group lens**.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from safety import (
    CATEGORY_SEVERITY, HELP_POI_TYPES, _band, compute_safety, point_risk,
)
from utils import haversine_km, point_in_polygon


# ----------------------------------------------------------------- constants

WALK_SPEED_KMH: float = 4.5             # average steady walking pace
MAX_MEET_RADIUS_KM: float = 4.0         # candidates must lie within this of centroid
CORRIDOR_WAYPOINTS: int = 8             # samples per rendezvous corridor
PATH_SAMPLES: int = 5                   # samples for candidate path-risk scoring
SAFE_GRID_SIDE: int = 5                 # 5x5 grid for safe-pocket sampling
SAFE_GRID_KEEP: int = 3                 # keep top-N safe-pocket candidates
TOP_HELP_POI_KEEP: int = 5              # keep top-N help POIs as candidates
SPREAD_FREE_KM: float = 0.8             # spread up to here costs nothing
SPREAD_FULL_KM: float = 3.8             # spread at/above here costs everything
ISOLATION_FLAG_KM: float = 2.5          # member flagged "isolated" past this
CORRIDOR_RISK_FLAG: float = 0.55        # corridor flagged risky past this
PATH_BLEND_ALPHA: float = 0.35          # path-risk weight in candidate score

KIND_GLYPH: Dict[str, str] = {
    "lead":      "★",
    "traveller": "●",
    "minor":     "◐",
    "elder":     "◇",
    "guide":     "▲",
}

KIND_WEIGHT: Dict[str, float] = {
    "lead":      1.00,
    "traveller": 1.00,
    "minor":     1.25,   # extra protection weight
    "elder":     1.20,
    "guide":     0.90,
}

CANDIDATE_HUE: Dict[str, str] = {
    "help_poi":     "#3DA9FC",
    "centroid":     "#A78BFA",
    "safe_pocket":  "#53E3A6",
    "stable_member":"#F9C440",
}


# ------------------------------------------------------------------- dataclasses

@dataclass
class Member:
    id: str
    label: str
    lat: float
    lon: float
    kind: str = "traveller"


@dataclass
class MemberSnapshot:
    member: Member
    score: int = 0
    band: str = "Unknown"
    nearest_help_km: Optional[float] = None
    incidents_nearby: int = 0
    factors: List[dict] = field(default_factory=list)
    isolation_km: float = 0.0   # distance to nearest other member

    @property
    def glyph(self) -> str:
        return KIND_GLYPH.get(self.member.kind, "●")


@dataclass
class Arrival:
    member_id: str
    walk_km: float
    walk_minutes: float
    mean_path_risk: float       # 0..1 — average over PATH_SAMPLES waypoints
    peak_path_risk: float       # max waypoint risk along the corridor
    geofence_crossings: int

    def to_dict(self) -> dict:
        return {
            "member_id": self.member_id,
            "walk_km": round(self.walk_km, 3),
            "walk_minutes": round(self.walk_minutes, 1),
            "mean_path_risk": round(self.mean_path_risk, 3),
            "peak_path_risk": round(self.peak_path_risk, 3),
            "geofence_crossings": int(self.geofence_crossings),
        }


@dataclass
class MeetPointCandidate:
    label: str
    source: str                 # 'help_poi' | 'centroid' | 'safe_pocket' | 'stable_member'
    lat: float
    lon: float
    arrivals: List[Arrival] = field(default_factory=list)
    max_walk_km: float = 0.0
    sum_walk_km: float = 0.0
    max_path_risk: float = 0.0
    mean_path_risk: float = 0.0
    safety_at: int = 0
    score: int = 0
    eta_min_minutes: float = 0.0
    eta_max_minutes: float = 0.0
    extras: Dict[str, Any] = field(default_factory=dict)

    @property
    def hue(self) -> str:
        return CANDIDATE_HUE.get(self.source, "#A4ADC2")

    def to_dict(self) -> dict:
        return {
            "label": self.label,
            "source": self.source,
            "lat": round(self.lat, 6),
            "lon": round(self.lon, 6),
            "score": int(self.score),
            "safety_at": int(self.safety_at),
            "max_walk_km": round(self.max_walk_km, 3),
            "sum_walk_km": round(self.sum_walk_km, 3),
            "max_path_risk": round(self.max_path_risk, 3),
            "mean_path_risk": round(self.mean_path_risk, 3),
            "eta_min_minutes": round(self.eta_min_minutes, 1),
            "eta_max_minutes": round(self.eta_max_minutes, 1),
            "arrivals": [a.to_dict() for a in self.arrivals],
            "extras": self.extras,
        }


@dataclass
class Corridor:
    member_id: str
    coords: List[Tuple[float, float]] = field(default_factory=list)
    risk_samples: List[float] = field(default_factory=list)
    distance_km: float = 0.0
    eta_minutes: float = 0.0
    mean_risk: float = 0.0
    peak_risk: float = 0.0
    risky: bool = False

    def to_dict(self) -> dict:
        return {
            "member_id": self.member_id,
            "coords": [(round(la, 6), round(lo, 6)) for la, lo in self.coords],
            "risk_samples": [round(r, 3) for r in self.risk_samples],
            "distance_km": round(self.distance_km, 3),
            "eta_minutes": round(self.eta_minutes, 1),
            "mean_risk": round(self.mean_risk, 3),
            "peak_risk": round(self.peak_risk, 3),
            "risky": bool(self.risky),
        }


@dataclass
class BeaconReport:
    now: datetime
    mood: str
    group_score: int
    group_band: str
    group_spread_km: float
    headline: str
    advisory_line: str
    members: List[MemberSnapshot] = field(default_factory=list)
    biggest_concern: Optional[str] = None     # member id
    candidates: List[MeetPointCandidate] = field(default_factory=list)
    chosen: Optional[MeetPointCandidate] = None
    secondary: Optional[MeetPointCandidate] = None
    corridors: List[Corridor] = field(default_factory=list)
    alerts: List[str] = field(default_factory=list)
    plan_of_action: List[str] = field(default_factory=list)

    # ---- serialisation -------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "$schema": "waysafe.beacon.v1",
            "composed_at": self.now.isoformat(timespec="seconds") + "Z",
            "mood": self.mood,
            "headline": self.headline,
            "advisory_line": self.advisory_line,
            "group": {
                "score": int(self.group_score),
                "band": self.group_band,
                "spread_km": round(self.group_spread_km, 3),
                "size": len(self.members),
                "biggest_concern_id": self.biggest_concern,
            },
            "members": [{
                "id": s.member.id,
                "label": s.member.label,
                "kind": s.member.kind,
                "lat": round(s.member.lat, 6),
                "lon": round(s.member.lon, 6),
                "score": int(s.score),
                "band": s.band,
                "isolation_km": round(s.isolation_km, 3),
                "nearest_help_km": s.nearest_help_km,
                "incidents_nearby": int(s.incidents_nearby),
                "factors": s.factors,
            } for s in self.members],
            "candidates": [c.to_dict() for c in self.candidates],
            "chosen": self.chosen.to_dict() if self.chosen else None,
            "secondary": self.secondary.to_dict() if self.secondary else None,
            "corridors": [c.to_dict() for c in self.corridors],
            "alerts": list(self.alerts),
            "plan_of_action": list(self.plan_of_action),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, default=str)

    def to_markdown(self) -> str:
        lines: List[str] = []
        lines.append(f"# Beacon brief · {self.now.strftime('%a %d %b %H:%M')} UTC")
        lines.append("")
        lines.append(f"**{self.headline}**")
        lines.append("")
        lines.append(f"_{self.advisory_line}_")
        lines.append("")
        lines.append("| metric | value |")
        lines.append("|---|---|")
        lines.append(f"| Group score | **{self.group_score}** · {self.group_band} |")
        lines.append(f"| Group spread | {self.group_spread_km:.2f} km |")
        lines.append(f"| Members | {len(self.members)} |")
        lines.append(f"| Mood | **{self.mood}** |")
        if self.chosen:
            lines.append(f"| Meet at | **{self.chosen.label}** (score {self.chosen.score}) |")
            lines.append(f"| Slowest arrival | {self.chosen.eta_max_minutes:.0f} min "
                         f"({self.chosen.max_walk_km:.2f} km) |")
            lines.append(f"| Worst corridor risk | {self.chosen.max_path_risk:.2f} |")
        lines.append("")
        lines.append("## Members")
        lines.append("")
        lines.append("| member | kind | score | band | isolated | nearest help |")
        lines.append("|---|---|---|---|---|---|")
        for s in self.members:
            nh = f"{s.nearest_help_km:.2f} km" if s.nearest_help_km is not None else "—"
            iso = f"{s.isolation_km:.2f} km"
            lines.append(
                f"| {s.member.label} | {s.member.kind} | **{s.score}** | "
                f"{s.band} | {iso} | {nh} |"
            )
        lines.append("")
        if self.alerts:
            lines.append("## Alerts")
            lines.append("")
            for a in self.alerts:
                lines.append(f"- {a}")
            lines.append("")
        if self.candidates:
            lines.append("## Meet-point candidates")
            lines.append("")
            lines.append("| rank | label | score | safety | max walk | sum walk | worst corridor |")
            lines.append("|---:|---|---:|---:|---:|---:|---:|")
            for i, c in enumerate(self.candidates[:6], 1):
                lines.append(
                    f"| {i} | {c.label} | **{c.score}** | {c.safety_at} | "
                    f"{c.max_walk_km:.2f} km | {c.sum_walk_km:.2f} km | "
                    f"{c.max_path_risk:.2f} |"
                )
            lines.append("")
        if self.plan_of_action:
            lines.append("## Plan of action")
            lines.append("")
            for i, p in enumerate(self.plan_of_action, 1):
                lines.append(f"{i}. {p}")
            lines.append("")
        return "\n".join(lines).rstrip() + "\n"


# ----------------------------------------------------------------- math helpers

def _great_circle_waypoints(
    lat1: float, lon1: float, lat2: float, lon2: float, n: int,
) -> List[Tuple[float, float]]:
    """Linearly interpolated lat/lon waypoints, including endpoints.

    `n >= 2`. For Goa-scale corridors (≤ 4 km) plain linear interpolation
    matches the great-circle to within ~1 m — cheap and good enough.
    """
    n = max(2, int(n))
    return [
        (lat1 + (lat2 - lat1) * (i / (n - 1)),
         lon1 + (lon2 - lon1) * (i / (n - 1)))
        for i in range(n)
    ]


def _count_geofence_crossings(
    coords: Sequence[Tuple[float, float]], geofences: Mapping,
) -> int:
    """How many distinct geofence polygons does the path's waypoint set hit?"""
    if not coords:
        return 0
    hit_ids: set = set()
    for feat in geofences.get("features", []):
        poly = feat["geometry"]["coordinates"][0]
        name = feat.get("properties", {}).get("name", id(feat))
        for la, lo in coords:
            if point_in_polygon(la, lo, poly):
                hit_ids.add(name)
                break
    return len(hit_ids)


def _isolation_km(idx: int, members: Sequence[Member]) -> float:
    """Min great-circle distance from members[idx] to any other member."""
    if len(members) <= 1:
        return 0.0
    me = members[idx]
    best = float("inf")
    for j, other in enumerate(members):
        if j == idx:
            continue
        d = haversine_km(me.lat, me.lon, other.lat, other.lon)
        if d < best:
            best = d
    return 0.0 if math.isinf(best) else best


def _group_spread_km(members: Sequence[Member]) -> float:
    """Max pairwise great-circle distance — a proxy for how splintered the group is."""
    if len(members) <= 1:
        return 0.0
    best = 0.0
    for i in range(len(members)):
        for j in range(i + 1, len(members)):
            d = haversine_km(
                members[i].lat, members[i].lon,
                members[j].lat, members[j].lon,
            )
            if d > best:
                best = d
    return best


def _spread_penalty(spread_km: float) -> float:
    """0.0 at SPREAD_FREE_KM or below, 1.0 at SPREAD_FULL_KM or above (linear)."""
    if spread_km <= SPREAD_FREE_KM:
        return 0.0
    if spread_km >= SPREAD_FULL_KM:
        return 1.0
    return (spread_km - SPREAD_FREE_KM) / (SPREAD_FULL_KM - SPREAD_FREE_KM)


def _kind_weighted_mean(scores: Sequence[Tuple[int, float]]) -> float:
    """Weighted mean of `[(score, weight), ...]`."""
    if not scores:
        return 0.0
    num = sum(s * w for s, w in scores)
    den = sum(w for _, w in scores)
    return num / den if den > 0 else 0.0


# ---------------------------------------------------------------- core engine

def _score_member(
    m: Member,
    *,
    incidents: Sequence[Mapping],
    geofences: Mapping,
    pois: Sequence[Mapping],
    now: datetime,
) -> MemberSnapshot:
    res = compute_safety(m.lat, m.lon, incidents, geofences, pois, now=now)
    return MemberSnapshot(
        member=m,
        score=res.score,
        band=res.band,
        nearest_help_km=res.nearest_help_km,
        incidents_nearby=res.incidents_nearby,
        factors=res.factors,
    )


def _safety_at(
    lat: float, lon: float,
    *,
    incidents: Sequence[Mapping],
    geofences: Mapping,
    pois: Sequence[Mapping],
    now: datetime,
) -> int:
    return compute_safety(lat, lon, incidents, geofences, pois, now=now).score


def _evaluate_candidate(
    cand: MeetPointCandidate,
    *,
    members: Sequence[MemberSnapshot],
    incidents: Sequence[Mapping],
    geofences: Mapping,
    pois: Sequence[Mapping],
    now: datetime,
) -> MeetPointCandidate:
    """Fill in walk + path-risk + score for a candidate against the member roster."""
    arrivals: List[Arrival] = []
    max_walk = 0.0
    sum_walk = 0.0
    max_risk = 0.0
    risk_acc = 0.0
    risk_n = 0
    for s in members:
        d = haversine_km(s.member.lat, s.member.lon, cand.lat, cand.lon)
        # Sample path-risk along the line from member → candidate.
        waypoints = _great_circle_waypoints(
            s.member.lat, s.member.lon, cand.lat, cand.lon, PATH_SAMPLES,
        )
        path_risks = [
            point_risk(la, lo, incidents, geofences, pois, now=now)
            for la, lo in waypoints
        ]
        peak = max(path_risks) if path_risks else 0.0
        mean = sum(path_risks) / len(path_risks) if path_risks else 0.0
        crossings = _count_geofence_crossings(waypoints, geofences)
        arrivals.append(Arrival(
            member_id=s.member.id,
            walk_km=d,
            walk_minutes=(d / WALK_SPEED_KMH) * 60.0,
            mean_path_risk=mean,
            peak_path_risk=peak,
            geofence_crossings=crossings,
        ))
        max_walk = max(max_walk, d)
        sum_walk += d
        max_risk = max(max_risk, peak)
        risk_acc += mean
        risk_n += 1
    safety_here = _safety_at(
        cand.lat, cand.lon,
        incidents=incidents, geofences=geofences, pois=pois, now=now,
    )

    # Composite candidate score:
    #   40% safety AT the point
    #   25% inverse of worst corridor path-risk (the chain is only as strong as its riskiest member-walk)
    #   20% inverse of max walk (slowest member dominates a real-world rendezvous)
    #   15% inverse of total walk (load-shedding — small bonus for not making everyone trek)
    mean_risk = (risk_acc / risk_n) if risk_n else 0.0
    inv_corridor = max(0.0, 1.0 - max_risk)
    inv_max_walk = max(0.0, 1.0 - min(1.0, max_walk / MAX_MEET_RADIUS_KM))
    inv_sum_walk = max(0.0, 1.0 - min(1.0, sum_walk / (MAX_MEET_RADIUS_KM * max(1, len(members)))))

    composite = (
        0.40 * (safety_here / 100.0)
        + 0.25 * inv_corridor
        + 0.20 * inv_max_walk
        + 0.15 * inv_sum_walk
    )
    cand.arrivals = arrivals
    cand.max_walk_km = max_walk
    cand.sum_walk_km = sum_walk
    cand.max_path_risk = max_risk
    cand.mean_path_risk = mean_risk
    cand.safety_at = safety_here
    cand.score = int(round(max(0.0, min(1.0, composite)) * 100))
    if arrivals:
        cand.eta_min_minutes = min(a.walk_minutes for a in arrivals)
        cand.eta_max_minutes = max(a.walk_minutes for a in arrivals)
    return cand


def _gen_candidates(
    members: Sequence[MemberSnapshot],
    *,
    incidents: Sequence[Mapping],
    geofences: Mapping,
    pois: Sequence[Mapping],
    now: datetime,
) -> List[MeetPointCandidate]:
    raw: List[MeetPointCandidate] = []

    # 1. Centroid (geometric mean) — the obvious "fair" pick.
    if members:
        c_lat = sum(s.member.lat for s in members) / len(members)
        c_lon = sum(s.member.lon for s in members) / len(members)
        raw.append(MeetPointCandidate(
            label="Group centroid",
            source="centroid",
            lat=c_lat, lon=c_lon,
        ))
    else:
        return []

    # 2. Top-N help POIs within radius of the centroid. We rank by raw
    #    safety score so we don't waste a slot on a gated hospital next
    #    to a midnight roadblock.
    c_lat, c_lon = raw[0].lat, raw[0].lon
    poi_cands: List[Tuple[int, str, float, float, dict]] = []
    seen_keys: set = set()
    for poi in pois:
        try:
            la, lo = float(poi.get("lat")), float(poi.get("lon"))
        except (TypeError, ValueError):
            continue
        ptype = str(poi.get("ptype", "")).lower()
        if ptype not in HELP_POI_TYPES:
            continue
        d = haversine_km(c_lat, c_lon, la, lo)
        if d > MAX_MEET_RADIUS_KM:
            continue
        key = (round(la, 4), round(lo, 4))
        if key in seen_keys:
            continue
        seen_keys.add(key)
        name = str(poi.get("name", ptype.title())) or ptype.title()
        s_here = _safety_at(
            la, lo,
            incidents=incidents, geofences=geofences, pois=pois, now=now,
        )
        poi_cands.append((s_here, name, la, lo, {"ptype": ptype, "centroid_km": round(d, 2)}))
    poi_cands.sort(key=lambda t: -t[0])
    for s_here, name, la, lo, extras in poi_cands[:TOP_HELP_POI_KEEP]:
        raw.append(MeetPointCandidate(
            label=f"{name} · {extras['ptype']}",
            source="help_poi",
            lat=la, lon=lo,
            extras=extras,
        ))

    # 3. Safe-grid sampling — a coarse SAFE_GRID_SIDE×SAFE_GRID_SIDE grid
    #    centred on the centroid covers the offbeat pockets that aren't
    #    near an institutional refuge but are still genuinely safe.
    spread = _group_spread_km([s.member for s in members])
    half = max(spread / 2.0, 0.6) * 1.2 / 111.0   # ~degrees lat
    half_lon = half / max(0.2, math.cos(math.radians(c_lat)))
    grid_cells: List[Tuple[int, float, float]] = []
    for i in range(SAFE_GRID_SIDE):
        for j in range(SAFE_GRID_SIDE):
            la = c_lat + (i - (SAFE_GRID_SIDE - 1) / 2) * (2 * half / (SAFE_GRID_SIDE - 1))
            lo = c_lon + (j - (SAFE_GRID_SIDE - 1) / 2) * (2 * half_lon / (SAFE_GRID_SIDE - 1))
            # Skip cells too close to existing candidates to keep variety.
            collide = any(haversine_km(la, lo, c.lat, c.lon) < 0.25 for c in raw)
            if collide:
                continue
            s_here = _safety_at(
                la, lo,
                incidents=incidents, geofences=geofences, pois=pois, now=now,
            )
            grid_cells.append((s_here, la, lo))
    grid_cells.sort(key=lambda t: -t[0])
    keep = 0
    pocket_letters = "ABCDEFG"
    for s_here, la, lo in grid_cells:
        if keep >= SAFE_GRID_KEEP:
            break
        # Drop any pocket too close to a previously-kept pocket.
        if any(c.source == "safe_pocket" and haversine_km(la, lo, c.lat, c.lon) < 0.30
               for c in raw):
            continue
        raw.append(MeetPointCandidate(
            label=f"Safe pocket {pocket_letters[keep]}",
            source="safe_pocket",
            lat=la, lon=lo,
        ))
        keep += 1

    # 4. "Stay with X" — if one member is already in a Safe band AND has
    #    nobody else within 100 m of them, they themselves are a real
    #    candidate (avoids dragging the safest person somewhere else).
    for s in members:
        if s.score < 80:
            continue
        # Avoid duplicating one of the existing candidates.
        if any(haversine_km(s.member.lat, s.member.lon, c.lat, c.lon) < 0.10
               for c in raw):
            continue
        raw.append(MeetPointCandidate(
            label=f"Stay with {s.member.label}",
            source="stable_member",
            lat=s.member.lat, lon=s.member.lon,
        ))

    return raw


def _build_corridors(
    chosen: MeetPointCandidate,
    members: Sequence[MemberSnapshot],
    *,
    incidents: Sequence[Mapping],
    geofences: Mapping,
    pois: Sequence[Mapping],
    now: datetime,
) -> List[Corridor]:
    corridors: List[Corridor] = []
    for s in members:
        coords = _great_circle_waypoints(
            s.member.lat, s.member.lon, chosen.lat, chosen.lon, CORRIDOR_WAYPOINTS,
        )
        risks = [
            point_risk(la, lo, incidents, geofences, pois, now=now)
            for la, lo in coords
        ]
        dist = haversine_km(s.member.lat, s.member.lon, chosen.lat, chosen.lon)
        peak = max(risks) if risks else 0.0
        mean = sum(risks) / len(risks) if risks else 0.0
        corridors.append(Corridor(
            member_id=s.member.id,
            coords=coords,
            risk_samples=risks,
            distance_km=dist,
            eta_minutes=(dist / WALK_SPEED_KMH) * 60.0,
            mean_risk=mean,
            peak_risk=peak,
            risky=peak >= CORRIDOR_RISK_FLAG,
        ))
    return corridors


def _compose_mood(
    *,
    group_score: int,
    members: Sequence[MemberSnapshot],
    spread_km: float,
    chosen: Optional[MeetPointCandidate],
) -> str:
    """First-match-wins ladder. Critical > Active > Watch > Calm."""
    has_danger = any(s.band == "Danger" for s in members)
    has_highrisk = any(s.band == "High Risk" for s in members)
    has_caution = any(s.band == "Caution" for s in members)
    worst_corridor = chosen.max_path_risk if chosen else 0.0

    if has_danger or group_score < 35 or worst_corridor >= 0.65:
        return "Critical"
    if has_highrisk or group_score < 60 or spread_km > 2.5:
        return "Active"
    if has_caution or group_score < 80 or spread_km > 1.2:
        return "Watch"
    return "Calm"


def _biggest_concern(members: Sequence[MemberSnapshot]) -> Optional[MemberSnapshot]:
    """Member with the most signal — band weight + isolation + kind multiplier."""
    if not members:
        return None
    band_weight = {"Danger": 60, "High Risk": 40, "Caution": 20, "Safe": 0, "Unknown": 0}
    def signal(s: MemberSnapshot) -> float:
        return (
            band_weight.get(s.band, 0)
            + max(0.0, s.isolation_km - ISOLATION_FLAG_KM) * 10.0
            + max(0, 70 - s.score) * 0.4
            + (8.0 if s.member.kind in ("minor", "elder") else 0.0)
        )
    return max(members, key=signal)


def _compose_alerts(
    members: Sequence[MemberSnapshot],
    chosen: Optional[MeetPointCandidate],
    corridors: Sequence[Corridor],
    spread_km: float,
) -> List[str]:
    out: List[str] = []
    for s in members:
        if s.band in ("Danger", "High Risk"):
            out.append(
                f"**{s.member.label}** is in **{s.band}** territory "
                f"(score {s.score}) — pull them out first."
            )
    for s in members:
        if s.isolation_km >= ISOLATION_FLAG_KM:
            out.append(
                f"**{s.member.label}** is isolated — "
                f"{s.isolation_km:.2f} km from the nearest group member."
            )
    if chosen and corridors:
        cor_by_id = {c.member_id: c for c in corridors}
        for s in members:
            cor = cor_by_id.get(s.member.id)
            if cor is None:
                continue
            if cor.peak_risk >= CORRIDOR_RISK_FLAG:
                out.append(
                    f"**{s.member.label}**'s corridor to *{chosen.label}* peaks at "
                    f"risk {cor.peak_risk:.2f} — re-route or escort."
                )
    if chosen:
        # Geofence-crossing alerts from the candidate's per-member arrivals.
        for ar in chosen.arrivals:
            if ar.geofence_crossings >= 1:
                lab = next((s.member.label for s in members if s.member.id == ar.member_id), ar.member_id)
                out.append(
                    f"**{lab}**'s path to *{chosen.label}* enters "
                    f"**{ar.geofence_crossings}** geofenced zone(s)."
                )
    if spread_km > SPREAD_FULL_KM * 0.85:
        out.append(
            f"Group spread is **{spread_km:.2f} km** — the squad is fragmented. "
            f"Regroup before any onward leg."
        )
    # De-dupe while preserving order.
    seen: set = set()
    deduped: List[str] = []
    for line in out:
        if line not in seen:
            seen.add(line)
            deduped.append(line)
    return deduped


def _compose_plan(
    members: Sequence[MemberSnapshot],
    chosen: Optional[MeetPointCandidate],
    secondary: Optional[MeetPointCandidate],
    corridors: Sequence[Corridor],
    biggest: Optional[MemberSnapshot],
) -> List[str]:
    """Prioritised checklist that references other WaySafe tabs by name."""
    out: List[str] = []
    if chosen is None or not members:
        return ["No actionable meet-point under current conditions — re-Beacon after 10 min."]

    # 1. Anchor action: where + slowest-member ETA.
    slowest = max(corridors, key=lambda c: c.eta_minutes) if corridors else None
    slow_label = next(
        (s.member.label for s in members if slowest and s.member.id == slowest.member_id),
        "the slowest member",
    )
    if slowest is not None:
        out.append(
            f"Converge at **{chosen.label}** — ETA **{slowest.eta_minutes:.0f} min** "
            f"for the slowest member ({slow_label})."
        )
    else:
        out.append(f"Converge at **{chosen.label}**.")

    # 2. Lead-member action — designated lead departs first to establish presence.
    lead = next((s for s in members if s.member.kind == "lead"), None) or members[0]
    if chosen.source == "stable_member" and lead is not None and lead.member.id != biggest.member.id if biggest else False:
        # Lead is already at the meet-point — flip the script.
        out.append(
            f"**{lead.member.label}** stays put — others home to their position."
        )
    elif lead is not None:
        out.append(
            f"**{lead.member.label}** (lead) departs **first** — establish presence "
            f"at *{chosen.label}* and confirm the rendezvous over the **Alerts** tab."
        )

    # 3. Per-vulnerable-member pull lines.
    for s in members:
        if s.band == "Danger":
            out.append(
                f"**{s.member.label}** is in **Danger** — pause their movement; "
                f"dispatch help to their current location instead."
            )
            break  # only one such line — the user will see the rest in Alerts

    # 4. Refuge / Live Trip wiring.
    out.append(
        f"Open the **Refuge** tab on the meet-point to memorise the nearest 3 help POIs."
    )
    out.append(
        f"Enable **Live Trip** geofence pings on every member while corridors are in motion."
    )

    # 5. Secondary fallback.
    if secondary is not None:
        out.append(
            f"If a split happens en route, fall back to **{secondary.label}** "
            f"(secondary meet-point · score {secondary.score})."
        )

    # 6. Re-Beacon cadence — group conditions move fast.
    out.append("Re-Beacon every **15 min** — incidents & member positions drift.")

    return out


def _compose_headline(
    *,
    mood: str,
    group_score: int,
    group_band: str,
    biggest: Optional[MemberSnapshot],
    chosen: Optional[MeetPointCandidate],
    n_members: int,
) -> Tuple[str, str]:
    """Returns (headline, advisory_line). Single-sentence each."""
    if n_members == 0:
        return ("No members on the roster.", "Add 2+ members to compose a Beacon brief.")

    biggest_lab = biggest.member.label if biggest else "the group"
    if mood == "Critical":
        head = f"Critical · **{biggest_lab}** needs immediate help — group score {group_score} ({group_band})"
    elif mood == "Active":
        head = f"Active morning · group score {group_score} ({group_band}) · regroup at **{chosen.label}**" if chosen else f"Active morning · group score {group_score}"
    elif mood == "Watch":
        head = f"Watch · group score {group_score} · meet at **{chosen.label}** in **{chosen.eta_max_minutes:.0f} min**" if chosen else f"Watch · group score {group_score}"
    else:
        head = f"Calm · group score {group_score} ({group_band})" + (f" · easy meet at **{chosen.label}**" if chosen else "")

    if chosen:
        adv = (
            f"{n_members} member(s) · spread {biggest.isolation_km:.2f} km · "
            f"slowest member {chosen.eta_max_minutes:.0f} min from *{chosen.label}* · "
            f"worst corridor risk {chosen.max_path_risk:.2f}."
            if biggest else
            f"{n_members} member(s) · meet at *{chosen.label}*."
        )
    else:
        adv = f"{n_members} member(s) — no meet-point candidate inside {MAX_MEET_RADIUS_KM:g} km."
    return head, adv


# --------------------------------------------------------------- main entry

def compute_beacon(
    members_raw: Sequence[Mapping],
    *,
    incidents: Sequence[Mapping],
    geofences: Mapping,
    pois: Sequence[Mapping],
    now: Optional[datetime] = None,
) -> BeaconReport:
    """Compose a full Beacon brief from a roster + the rest of the world.

    `members_raw` rows accept `id`, `label`, `lat`, `lon`, `kind`. Missing
    ids get a stable synthetic one. NaN / non-numeric coords are dropped.
    """
    now = now or datetime.utcnow()

    # ---- 1. Normalise the roster ----------------------------------------
    members: List[Member] = []
    for i, r in enumerate(members_raw):
        try:
            la = float(r.get("lat"))
            lo = float(r.get("lon"))
            if la != la or lo != lo:   # NaN guard
                continue
        except (TypeError, ValueError):
            continue
        mid = str(r.get("id") or f"m{i+1}")
        lab = str(r.get("label") or f"Member {i+1}") or f"Member {i+1}"
        kind = str(r.get("kind") or "traveller") or "traveller"
        members.append(Member(id=mid, label=lab, lat=la, lon=lo, kind=kind))

    if not members:
        return BeaconReport(
            now=now, mood="Calm",
            group_score=0, group_band="Unknown", group_spread_km=0.0,
            headline="No members on the roster.",
            advisory_line="Add 2+ members to compose a Beacon brief.",
        )

    # ---- 2. Score each member ------------------------------------------
    snapshots: List[MemberSnapshot] = [
        _score_member(
            m,
            incidents=incidents, geofences=geofences, pois=pois, now=now,
        )
        for m in members
    ]
    # Isolation per member (uses members list, not snapshots — same indices).
    for i, snap in enumerate(snapshots):
        snap.isolation_km = _isolation_km(i, members)

    # ---- 3. Group-level composite --------------------------------------
    spread = _group_spread_km(members)
    weighted = [
        (snap.score, KIND_WEIGHT.get(snap.member.kind, 1.0))
        for snap in snapshots
    ]
    mean_score = _kind_weighted_mean(weighted)
    min_score = min(snap.score for snap in snapshots)
    spread_score = 100.0 * (1.0 - _spread_penalty(spread))
    group_score = int(round(
        0.50 * min_score + 0.30 * mean_score + 0.20 * spread_score
    ))
    group_band = _band(group_score)

    # ---- 4. Candidate generation + evaluation --------------------------
    raw_cands = _gen_candidates(
        snapshots,
        incidents=incidents, geofences=geofences, pois=pois, now=now,
    )
    cands = [
        _evaluate_candidate(
            c,
            members=snapshots,
            incidents=incidents, geofences=geofences, pois=pois, now=now,
        )
        for c in raw_cands
    ]
    cands.sort(key=lambda c: -c.score)
    chosen = cands[0] if cands else None
    secondary = cands[1] if len(cands) > 1 else None

    # ---- 5. Rendezvous corridors for the chosen point ------------------
    corridors: List[Corridor] = []
    if chosen is not None:
        corridors = _build_corridors(
            chosen, snapshots,
            incidents=incidents, geofences=geofences, pois=pois, now=now,
        )

    # ---- 6. Mood + headline + alerts + plan ----------------------------
    mood = _compose_mood(
        group_score=group_score, members=snapshots,
        spread_km=spread, chosen=chosen,
    )
    biggest = _biggest_concern(snapshots)
    headline, advisory = _compose_headline(
        mood=mood, group_score=group_score, group_band=group_band,
        biggest=biggest, chosen=chosen, n_members=len(snapshots),
    )
    alerts = _compose_alerts(snapshots, chosen, corridors, spread)
    plan = _compose_plan(snapshots, chosen, secondary, corridors, biggest)

    return BeaconReport(
        now=now,
        mood=mood,
        group_score=group_score,
        group_band=group_band,
        group_spread_km=spread,
        headline=headline,
        advisory_line=advisory,
        members=snapshots,
        biggest_concern=biggest.member.id if biggest else None,
        candidates=cands,
        chosen=chosen,
        secondary=secondary,
        corridors=corridors,
        alerts=alerts,
        plan_of_action=plan,
    )
