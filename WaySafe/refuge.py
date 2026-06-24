"""Refuge — Safe-Haven Escape Engine for WaySafe.

Every other WaySafe surface answers a *planning* question: Compass picks a
neighbourhood, StaySafe picks a hotel, Advisory writes a brief, Companion
guides a planned trip. **Refuge answers the question every tourist hopes
they never have to ask**: *"Something feels wrong RIGHT NOW — where do I
go in the next five minutes?"*.

The pre-existing `SOS` tab in `app.py` was a placeholder: it flipped a
boolean and listed the three closest help POIs sorted by raw great-circle
distance. That ranking is wrong in the only moments it matters:

  * A hospital 400m away through an unlit, geofenced corridor is **worse**
    than a 24/7 store 600m away on a busy main road.
  * A fire station that's gated at midnight is **worse** than a police
    chowki 200m further that's actually staffed.
  * A hotel front desk is a refuge **only** if it's 24/7-attended.
  * Trust tiers exist: police > hospital > embassy > fire > 24/7 retail
    > hotel front desk > petrol pump.

Refuge ranks every help POI inside `max_radius_km` by a deterministic
composite **Refuge Score** (0..100, higher = safer to flee to):

    refuge = 100 · ( 0.35 · proximity
                   + 0.25 · path_safety
                   + 0.20 · trust_tier
                   + 0.15 · open_confidence
                   + 0.05 · crowd_proxy )

* `proximity`        — 1.0 at 0 km, linear down to 0.0 at `max_radius_km`.
* `path_safety`      — average of `1 − safety.point_risk` over 5 evenly
                       spaced waypoints along the great-circle line from
                       the user to the candidate POI. This is the engine's
                       cheapest answer to "is the *corridor* safe?"
                       without re-running the full A* router.
* `trust_tier`       — institutional weight: police 1.00 · embassy 0.95
                       · hospital 0.92 · fire 0.85 · tourist help-desk
                       0.78 · 24/7 mart 0.62 · hotel front desk 0.55
                       · 24/7 petrol 0.50.
* `open_confidence`  — 1.0 for 24/7 tiers (police, hospital ER, fire,
                       allnight_store, petrol_24h). Tourist help-desks
                       and hotels degrade by hour: full confidence in
                       business hours, soft-cap at night.
* `crowd_proxy`      — 1.0 if any non-help POI sits within 0.5 km of the
                       midpoint of the corridor (well-lit, populated);
                       0.0 if the corridor is empty. A rough proxy for
                       "main road" vs "dark lane".

The engine **also returns**:

  * **Bearing & cardinal label** ("260° → W") so the user can move before
    even reading the map.
  * **Geofence-crossing count** along the path (point-in-polygon over the
    same waypoints used by `path_safety`).
  * **Per-tier arrival scripts** — one-line instructions for what to ask
    for the moment they walk in (police, hospital, embassy, hotel, etc.).
  * **Country-specific emergency card** — a pre-localised quick-dial
    panel (India 100/101/102/1091/1363; falls back to 112 EU and 911 US
    by lat/lon hemisphere). Render even when there's no help POI in
    radius — the worst case still has phone numbers.
  * **Quiet Beacon payload** — a single ready-to-copy SMS string and a
    Google-Maps deeplink to the top refuge. The "quiet" part: no audible
    alarm, no visible flash — designed for the threat model where being
    visibly using a panic button makes things worse.

Pure-stdlib + reuse of `safety.point_risk` and `utils.haversine_km`.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, List, Mapping, Optional, Sequence, Tuple

from safety import point_risk
from utils import haversine_km, point_in_polygon


# ---------------------------------------------------------------- constants

DEFAULT_MAX_RADIUS_KM = 4.0
DEFAULT_MAX_RESULTS = 5
WALKING_KMPH = 5.0
PATH_SAMPLES = 5                 # waypoints sampled along the corridor (incl. endpoints)
CROWD_RADIUS_KM = 0.5            # any non-help POI within this of the midpoint = populated
GOOD_PATH_BONUS_NOTE = 80        # path_safety ≥ this/100 → "well-lit corridor" note

WEIGHTS = {
    "proximity":  0.35,
    "path":       0.25,
    "trust":      0.20,
    "open":       0.15,
    "crowd":      0.05,
}

# Refuge bands — higher = safer to flee to.
_BAND_TABLE: List[Tuple[str, str, int, int]] = [
    ("Strong refuge", "#10B981",  72, 101),
    ("Viable refuge", "#FBBF24",  55,  72),
    ("Last resort",   "#F59E0B",  35,  55),
    ("Not a refuge",  "#EF4444",   0,  35),
]

# Compass cardinal helpers for the "go this way" line.
_CARDINALS = [
    ("N",   348.75, 360.0),
    ("N",     0.0,  11.25),
    ("NNE", 11.25,  33.75),
    ("NE",  33.75,  56.25),
    ("ENE", 56.25,  78.75),
    ("E",   78.75, 101.25),
    ("ESE",101.25, 123.75),
    ("SE", 123.75, 146.25),
    ("SSE",146.25, 168.75),
    ("S",  168.75, 191.25),
    ("SSW",191.25, 213.75),
    ("SW", 213.75, 236.25),
    ("WSW",236.25, 258.75),
    ("W",  258.75, 281.25),
    ("WNW",281.25, 303.75),
    ("NW", 303.75, 326.25),
    ("NNW",326.25, 348.75),
]


# ---------------------------------------------------------------- trust tiers


@dataclass(frozen=True)
class TrustTier:
    """Static metadata about a category of refuge."""
    key: str                # internal key
    label: str              # human-readable
    icon: str               # emoji
    weight: float           # 0..1 — drives the `trust_tier` factor
    is_24x7: bool           # True → `open_confidence` is always 1.0
    open_window: Tuple[int, int]   # (hr_open, hr_close) when not 24/7
    arrival_script: str     # what to say when you arrive
    nav_note: str           # one-line strategic tip


TIERS: dict[str, TrustTier] = {
    "police": TrustTier(
        key="police", label="Police station", icon="🛡️", weight=1.00,
        is_24x7=True, open_window=(0, 24),
        arrival_script="Walk in. Ask for the duty officer. Show this screen for your location & beacon ID.",
        nav_note="Police presence deters; even unstaffed chowkis usually have a buzzer to the on-call constable.",
    ),
    "embassy": TrustTier(
        key="embassy", label="Embassy / Consulate", icon="🏛️", weight=0.95,
        is_24x7=False, open_window=(9, 18),
        arrival_script="Show passport at the security booth. After-hours: ring the consular night line.",
        nav_note="Sovereign ground for your nationals — strong refuge if you can reach it.",
    ),
    "hospital": TrustTier(
        key="hospital", label="Hospital", icon="🏥", weight=0.92,
        is_24x7=True, open_window=(0, 24),
        arrival_script="Walk to the Emergency / Casualty wing. Tell triage you don't feel safe — they will hold you in waiting.",
        nav_note="ERs run 24/7, are well-lit, have CCTV and security guards on the door.",
    ),
    "clinic": TrustTier(
        key="clinic", label="Clinic", icon="🩺", weight=0.62,
        is_24x7=False, open_window=(8, 22),
        arrival_script="Reception desk. Most clinics will let you wait inside until conditions change.",
        nav_note="Day-hours only — use a hospital after dark instead.",
    ),
    "fire": TrustTier(
        key="fire", label="Fire & rescue", icon="🚒", weight=0.85,
        is_24x7=True, open_window=(0, 24),
        arrival_script="Ring the night-bell at the gate. Crews are bunked on-site — someone always answers.",
        nav_note="Always staffed but the gate is locked at night — use the bell, not the main door.",
    ),
    "tourist_help_desk": TrustTier(
        key="tourist_help_desk", label="Tourist help desk", icon="ℹ️", weight=0.78,
        is_24x7=False, open_window=(8, 21),
        arrival_script="Hand over your passport copy. They have direct tourist-police hotlines.",
        nav_note="Best refuge for non-medical distress (lost, scammed, harassed) during day hours.",
    ),
    "allnight_store": TrustTier(
        key="allnight_store", label="24/7 store", icon="🏪", weight=0.62,
        is_24x7=True, open_window=(0, 24),
        arrival_script="Walk in, buy something cheap, sit by the counter. Ask the cashier to call a cab.",
        nav_note="Bright lights, CCTV, attendant, and a phone — a surprisingly strong public refuge.",
    ),
    "hotel": TrustTier(
        key="hotel", label="Hotel front desk", icon="🏨", weight=0.55,
        is_24x7=False, open_window=(0, 24),  # most listed hotels have 24h reception
        arrival_script="Tell the night manager you need sanctuary. Show a booking on your phone if you have one.",
        nav_note="Reception desks are 24/7 but discretionary — yours is stronger if you hold a booking.",
    ),
    "petrol_24h": TrustTier(
        key="petrol_24h", label="24/7 petrol pump", icon="⛽", weight=0.50,
        is_24x7=True, open_window=(0, 24),
        arrival_script="Walk to the attendant booth. Ask to wait while you call someone.",
        nav_note="Lit, staffed, on main roads — last-resort refuge but always available.",
    ),
}

# Ptype → tier key (lowercased ptype as written in poi.csv).
_PTYPE_ALIAS: dict[str, str] = {
    "police": "police",
    "embassy": "embassy",
    "consulate": "embassy",
    "hospital": "hospital",
    "er": "hospital",
    "clinic": "clinic",
    "fire": "fire",
    "fire_station": "fire",
    "tourist_help_desk": "tourist_help_desk",
    "tourist_help": "tourist_help_desk",
    "allnight_store": "allnight_store",
    "24h_store": "allnight_store",
    "petrol_24h": "petrol_24h",
    "petrol": "petrol_24h",
    "hotel": "hotel",
    "resort": "hotel",
    "hostel": "hotel",
}

NON_HELP_TIERS = {"hotel", "petrol_24h", "allnight_store"}  # used for the crowd proxy too


# ---------------------------------------------------------------- dataclasses


@dataclass
class FactorScore:
    """One row in the per-option factor matrix."""
    key: str
    label: str
    display: str
    goodness: float    # 0..1, 1 = best for that factor


@dataclass
class PathSample:
    """A single waypoint along the corridor from user → refuge."""
    lat: float
    lon: float
    risk: float        # 0..1
    in_geofence: bool


@dataclass
class RefugeOption:
    """One ranked candidate."""
    rank: int
    poi_name: str
    ptype: str
    tier_key: str
    tier_label: str
    tier_icon: str

    lat: float
    lon: float
    distance_km: float
    eta_min: float

    refuge_score: int          # 0..100, higher = better refuge
    band: str
    band_color: str

    proximity: float           # 0..1
    path_safety: float         # 0..1 — avg (1 − point_risk) along corridor
    open_confidence: float     # 0..1
    trust_weight: float        # 0..1
    crowd_proxy: float         # 0..1
    geofence_crossings: int    # waypoints inside any geofence

    bearing_deg: int           # 0..359
    bearing_label: str         # "NNE"
    arrival_script: str
    nav_note: str
    notes: List[str] = field(default_factory=list)

    path_samples: List[PathSample] = field(default_factory=list)
    factors: List[FactorScore] = field(default_factory=list)
    nav_url: str = ""
    is_top: bool = False


@dataclass
class EmergencyCard:
    """Country-specific quick-dial card."""
    country: str
    flag_emoji: str
    numbers: List[Tuple[str, str]]   # [(label, number)]
    note: str = ""


@dataclass
class QuietBeacon:
    """A copy-and-go panic message and deeplink to the top refuge."""
    here_lat: float
    here_lon: float
    refuge_name: str
    refuge_lat: float
    refuge_lon: float
    nav_url: str
    ts: datetime
    payload_text: str


@dataclass
class RefugeResult:
    here_lat: float
    here_lon: float
    here_score: int            # safety score *at* the user's location
    here_band: str
    now: datetime
    radius_km: float
    options: List[RefugeOption]
    fallback: bool             # True if zero candidates inside radius
    emergency_card: EmergencyCard
    quiet_beacon: Optional[QuietBeacon]
    advisory_line: str
    headline: str
    factor_order: List[Tuple[str, str]] = field(default_factory=list)
    schema: str = "waysafe.refuge.v1"


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
    return max(0.0, min(1.0, float(x)))


def _band_for(score: int) -> Tuple[str, str]:
    for name, color, lo, hi in _BAND_TABLE:
        if lo <= score < hi:
            return name, color
    return "Not a refuge", "#EF4444"


def _bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> int:
    """Initial great-circle bearing user → refuge, in [0, 360)."""
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    deg = (math.degrees(math.atan2(y, x)) + 360.0) % 360.0
    return int(round(deg)) % 360


def _bearing_label(deg: float) -> str:
    deg = deg % 360.0
    for label, lo, hi in _CARDINALS:
        if lo <= deg < hi:
            return label
    return "N"


def _sample_corridor(lat1: float, lon1: float, lat2: float, lon2: float,
                     n: int = PATH_SAMPLES) -> List[Tuple[float, float]]:
    """Evenly-spaced waypoints along the great-circle (linear lat/lon for short hops)."""
    n = max(2, n)
    out: List[Tuple[float, float]] = []
    for i in range(n):
        t = i / (n - 1)
        out.append((lat1 + t * (lat2 - lat1), lon1 + t * (lon2 - lon1)))
    return out


def _tier_for(ptype: str) -> Optional[TrustTier]:
    key = _PTYPE_ALIAS.get(str(ptype).strip().lower())
    return TIERS.get(key) if key else None


def _open_confidence(tier: TrustTier, now: datetime) -> float:
    if tier.is_24x7:
        return 1.0
    hr = now.hour
    lo, hi = tier.open_window
    if lo <= hr < hi:
        return 1.0
    # Outside hours: hotels keep a 24h reception (front desk) but lower
    # confidence; everything else drops to 0.25.
    if tier.key == "hotel":
        return 0.85
    return 0.25


def _maps_deeplink(here_lat: float, here_lon: float,
                   to_lat: float, to_lon: float) -> str:
    return (
        "https://www.google.com/maps/dir/?api=1"
        f"&origin={here_lat:.6f},{here_lon:.6f}"
        f"&destination={to_lat:.6f},{to_lon:.6f}"
        "&travelmode=walking"
    )


# ---------------------------------------------------------------- emergency cards


def _emergency_card(here_lat: float, here_lon: float) -> EmergencyCard:
    """Pick a country card from latitude/longitude. Defaults to India for the demo."""
    # India by default — the demo dataset is Goa.
    if 6.0 < here_lat < 37.0 and 68.0 < here_lon < 98.0:
        return EmergencyCard(
            country="India",
            flag_emoji="🇮🇳",
            numbers=[
                ("Police",            "100"),
                ("Fire",              "101"),
                ("Ambulance",         "102"),
                ("Women's helpline",  "1091"),
                ("Tourist helpline",  "1363"),
                ("Disaster mgmt",     "108"),
            ],
            note="112 works as a unified emergency number across India since 2019.",
        )
    # Continental EU rough box (very loose).
    if 35.0 < here_lat < 71.0 and -10.0 < here_lon < 40.0:
        return EmergencyCard(
            country="European Union",
            flag_emoji="🇪🇺",
            numbers=[
                ("Unified emergency", "112"),
                ("Police (national)", "112"),
                ("Ambulance",         "112"),
                ("Fire",              "112"),
            ],
            note="112 reaches dispatch in every EU member state.",
        )
    # North America rough box.
    if 24.0 < here_lat < 60.0 and -125.0 < here_lon < -66.0:
        return EmergencyCard(
            country="United States / Canada",
            flag_emoji="🇺🇸",
            numbers=[
                ("Emergency",         "911"),
                ("Poison control",    "1-800-222-1222"),
                ("Crisis lifeline",   "988"),
            ],
            note="911 dispatches police, fire and EMS together.",
        )
    return EmergencyCard(
        country="International",
        flag_emoji="🌐",
        numbers=[("Unified emergency", "112"), ("US/Canada", "911")],
        note="112 and 911 reach an operator on most cellular networks worldwide.",
    )


# ---------------------------------------------------------------- core


def _evaluate_option(
    poi: Mapping,
    *,
    here_lat: float,
    here_lon: float,
    incidents: Sequence[Mapping],
    geofences: Mapping,
    pois_all: Sequence[Mapping],
    max_radius_km: float,
    now: datetime,
) -> Optional[RefugeOption]:
    """Score a single help POI as a refuge candidate.

    Returns None when the POI sits outside `max_radius_km` (or its ptype
    has no known tier) — the caller drops it from the result set.
    """
    tier = _tier_for(poi.get("ptype", ""))
    if tier is None:
        return None
    try:
        lat = float(poi.get("lat"))
        lon = float(poi.get("lon"))
    except (TypeError, ValueError):
        return None

    d = haversine_km(here_lat, here_lon, lat, lon)
    if d > max_radius_km:
        return None

    # 1. Proximity (linear; closer is better).
    proximity = _clamp01(1.0 - d / max_radius_km)

    # 2. Path safety — sample N waypoints and average (1 − point_risk).
    waypoints = _sample_corridor(here_lat, here_lon, lat, lon)
    samples: List[PathSample] = []
    in_fence = 0
    risk_sum = 0.0
    for wlat, wlon in waypoints:
        r = float(point_risk(wlat, wlon, incidents, geofences, pois_all, now=now))
        in_any = False
        for feat in geofences.get("features", []):
            coords = feat.get("geometry", {}).get("coordinates", [[]])
            if coords and point_in_polygon(wlat, wlon, coords[0]):
                in_any = True
                break
        if in_any:
            in_fence += 1
        samples.append(PathSample(lat=wlat, lon=wlon, risk=r, in_geofence=in_any))
        risk_sum += r
    path_safety = _clamp01(1.0 - risk_sum / len(waypoints))

    # 3. Trust weight (already 0..1).
    trust_weight = tier.weight

    # 4. Open confidence — hour-aware.
    open_conf = _open_confidence(tier, now)

    # 5. Crowd proxy — non-help POI within CROWD_RADIUS_KM of the midpoint.
    mid_lat, mid_lon = waypoints[len(waypoints) // 2]
    populated = False
    for p in pois_all:
        if p is poi:
            continue
        try:
            mlat = float(p.get("lat"))
            mlon = float(p.get("lon"))
        except (TypeError, ValueError):
            continue
        if haversine_km(mid_lat, mid_lon, mlat, mlon) <= CROWD_RADIUS_KM:
            populated = True
            break
    crowd = 1.0 if populated else 0.0

    # Composite refuge score.
    refuge = (
        WEIGHTS["proximity"] * proximity
        + WEIGHTS["path"]     * path_safety
        + WEIGHTS["trust"]    * trust_weight
        + WEIGHTS["open"]     * open_conf
        + WEIGHTS["crowd"]    * crowd
    )
    refuge_score = int(round(_clamp01(refuge) * 100.0))
    band, band_color = _band_for(refuge_score)

    # Notes — surfaced as plain-English bullets in the UI.
    notes: List[str] = []
    if in_fence >= 2:
        notes.append(f"Path crosses {in_fence} risk-zone waypoints — try another tier if possible.")
    elif in_fence == 1:
        notes.append("Path clips a geofenced risk zone briefly.")
    if path_safety * 100 >= GOOD_PATH_BONUS_NOTE:
        notes.append("Corridor reads as well-lit and low-incident.")
    if not populated:
        notes.append("Quiet corridor — no other POIs near the midpoint; walk briskly.")
    if open_conf < 1.0 and tier.key != "hotel":
        notes.append(
            f"{tier.label} normally closes by {tier.open_window[1]:02d}:00 — "
            "expect a locked main door, ring the night-bell or call before walking up."
        )
    if d <= 0.25:
        notes.append("Practically on top of you — head straight in.")

    bearing = _bearing_deg(here_lat, here_lon, lat, lon)
    bearing_lbl = _bearing_label(bearing)

    eta_min = (d / WALKING_KMPH) * 60.0

    factors = [
        FactorScore("proximity", "Proximity",    f"{d * 1000:.0f} m",   proximity),
        FactorScore("path",      "Path safety",  f"{int(round(path_safety * 100))}%", path_safety),
        FactorScore("trust",     "Trust tier",   tier.label,            trust_weight),
        FactorScore("open",      "Open now",     "yes" if open_conf >= 0.99 else f"{int(round(open_conf*100))}%", open_conf),
        FactorScore("crowd",     "Corridor crowd", "populated" if crowd >= 0.5 else "empty", crowd),
    ]

    return RefugeOption(
        rank=0,
        poi_name=str(poi.get("name", "Unnamed")),
        ptype=str(poi.get("ptype", "")),
        tier_key=tier.key,
        tier_label=tier.label,
        tier_icon=tier.icon,
        lat=lat, lon=lon,
        distance_km=round(d, 3),
        eta_min=round(eta_min, 1),
        refuge_score=refuge_score,
        band=band, band_color=band_color,
        proximity=round(proximity, 3),
        path_safety=round(path_safety, 3),
        open_confidence=round(open_conf, 3),
        trust_weight=round(trust_weight, 3),
        crowd_proxy=round(crowd, 3),
        geofence_crossings=in_fence,
        bearing_deg=bearing,
        bearing_label=bearing_lbl,
        arrival_script=tier.arrival_script,
        nav_note=tier.nav_note,
        notes=notes,
        path_samples=samples,
        factors=factors,
        nav_url=_maps_deeplink(here_lat, here_lon, lat, lon),
    )


def _advisory_line(here_score: int, here_band: str,
                   options: Sequence[RefugeOption]) -> Tuple[str, str]:
    """One-line headline + a longer advisory for the hero card."""
    if not options:
        return (
            "No registered help POI within scan radius.",
            "Use the emergency card below. Move toward main-road traffic until you find lit, populated space.",
        )
    top = options[0]
    dist_m = top.distance_km * 1000
    when = f"{int(round(top.eta_min))} min on foot"
    headline = (
        f"Head {top.bearing_label} · {top.tier_label.lower()} "
        f"in {dist_m:.0f} m ({when})."
    )
    if here_score < 35 or here_band in ("Danger", "High Risk"):
        detail = (
            f"You're standing in a {here_band.lower()} zone (score {here_score}/100). "
            f"Top refuge: **{top.poi_name}** — refuge score {top.refuge_score}/100, "
            f"{top.band.lower()}. Move now."
        )
    elif top.refuge_score >= 72:
        detail = (
            f"Strong refuge close by: **{top.poi_name}** "
            f"({top.refuge_score}/100). Activate the quiet beacon before you start walking."
        )
    else:
        detail = (
            f"Best available refuge: **{top.poi_name}** — "
            f"{top.band.lower()} ({top.refuge_score}/100). "
            "Check the next options if conditions look worse on the ground."
        )
    return headline, detail


def _quiet_beacon(top: RefugeOption, here_lat: float, here_lon: float,
                  now: datetime, user: str = "tourist") -> QuietBeacon:
    payload = (
        f"[WaySafe Beacon · {now:%H:%M %Z}] {user} feels unsafe at "
        f"({here_lat:.5f}, {here_lon:.5f}). "
        f"Walking to: {top.poi_name} ({top.lat:.5f}, {top.lon:.5f}) — "
        f"{top.distance_km*1000:.0f} m {top.bearing_label}. "
        f"Track: {top.nav_url}"
    )
    return QuietBeacon(
        here_lat=here_lat, here_lon=here_lon,
        refuge_name=top.poi_name,
        refuge_lat=top.lat, refuge_lon=top.lon,
        nav_url=top.nav_url,
        ts=now,
        payload_text=payload,
    )


# ---------------------------------------------------------------- entrypoint


def find_refuge(
    lat: float,
    lon: float,
    *,
    pois: Any,
    incidents: Any = None,
    geofences: Optional[Mapping] = None,
    now: Optional[datetime] = None,
    max_radius_km: float = DEFAULT_MAX_RADIUS_KM,
    max_results: int = DEFAULT_MAX_RESULTS,
    user: str = "tourist",
) -> RefugeResult:
    """Rank refuges around (lat, lon). The single Refuge-engine entrypoint.

    Parameters mirror the rest of the project: `pois` and `incidents` can
    be a pandas DataFrame *or* a list-of-dicts; `geofences` is the GeoJSON
    FeatureCollection used by `safety.point_risk`.
    """
    now = now or datetime.utcnow()
    geofences = geofences or {"features": []}

    inc = _as_records(incidents)
    pois_all = _as_records(pois)

    # Score every viable POI in radius.
    raw: List[RefugeOption] = []
    for p in pois_all:
        opt = _evaluate_option(
            p,
            here_lat=lat, here_lon=lon,
            incidents=inc,
            geofences=geofences,
            pois_all=pois_all,
            max_radius_km=max_radius_km,
            now=now,
        )
        if opt is not None:
            raw.append(opt)

    # Best-first; rank and flag the top.
    raw.sort(key=lambda o: (-o.refuge_score, o.distance_km))
    options: List[RefugeOption] = raw[:max_results]
    for i, o in enumerate(options, start=1):
        o.rank = i
        o.is_top = (i == 1)

    # Caller's own location safety score (for the advisory line).
    here_risk = float(point_risk(lat, lon, inc, geofences, pois_all, now=now))
    here_score = int(round(max(0.0, min(100.0, 100.0 - here_risk * 100.0))))
    if here_score >= 80:
        here_band = "Safe"
    elif here_score >= 60:
        here_band = "Caution"
    elif here_score >= 35:
        here_band = "High Risk"
    else:
        here_band = "Danger"

    headline, advisory = _advisory_line(here_score, here_band, options)

    quiet = _quiet_beacon(options[0], lat, lon, now, user=user) if options else None

    return RefugeResult(
        here_lat=lat, here_lon=lon,
        here_score=here_score, here_band=here_band,
        now=now,
        radius_km=max_radius_km,
        options=options,
        fallback=(not options),
        emergency_card=_emergency_card(lat, lon),
        quiet_beacon=quiet,
        advisory_line=advisory,
        headline=headline,
        factor_order=[
            ("proximity", "Proximity"),
            ("path",      "Path safety"),
            ("trust",     "Trust tier"),
            ("open",      "Open now"),
            ("crowd",     "Corridor crowd"),
        ],
    )


__all__ = [
    "TIERS",
    "TrustTier",
    "FactorScore",
    "PathSample",
    "RefugeOption",
    "EmergencyCard",
    "QuietBeacon",
    "RefugeResult",
    "find_refuge",
]
