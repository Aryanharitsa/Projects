"""Prism — Persona-Aware Risk Lens for WaySafe.

Every prior WaySafe surface (Safety, Forecast, Sentinel, Refuge, Compass,
Advisory, StaySafe, Pulse, Beacon, Tempo, Echo, …) treats the traveller as
a single, uniform profile — the corridor either scores 78 for *everyone* or
it doesn't. That is the biggest blind spot in the product: a corridor that
reads *Caution* for two business travellers on a Wednesday afternoon reads
*High Risk* for a solo woman at 22:00 and *Danger* for a family with two
under-fives.  Same physics, same incidents, same geofence — different
context, different verdict.

`Prism` is the *persona lens*.  It re-prices the point/route already scored
by `safety.py` under one of six preset traveller personas:

    solo-woman ·  family-kids ·  senior ·  business ·  adventure ·  group

and returns a `PersonaLens` per point (persona score, band, delta vs base,
rescaled factors, extras, an advisory-bump verdict) plus a `PrismReport`
(cross-point aggregate, persona-tuned lessons, packing checklist, broadcast
cadence, suggested route α).  Nothing new is measured — every quantity ties
back to `safety.compute_safety`'s factor list or the geofence/incident/POI
tables the rest of the app is already loading — so the surface adds *lens*,
not *physics*.

Pure-stdlib.  No new deps.  Deterministic.  Round-trips through
`to_dict / to_json / to_markdown` under the `waysafe.prism.v1` envelope.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from typing import Any, Callable, Iterable, List, Mapping, Optional, Sequence, Tuple

from utils import haversine_km
from safety import SafetyResult, compute_safety, CATEGORY_SEVERITY, HELP_POI_TYPES

# --- Types ----------------------------------------------------------------

@dataclass
class PersonaProfile:
    """A traveller persona — the knobs that re-price base WaySafe safety.

    All *_mult defaults are 1.0 and default `band_thresholds = (80, 60, 35)`
    are exactly the numbers `safety._band()` bakes in, so `PersonaProfile()`
    is a no-op lens (base safety survives byte-for-byte).  Presets in
    `PERSONAS` deviate from these defaults only where a real behavioural
    difference exists in the traveller-safety literature; each deviation
    is called out inline so the number is auditable, not vibes.
    """
    id: str
    label: str
    icon: str
    blurb: str

    # Penalty multipliers applied to the base `safety.compute_safety` factors.
    # `factor.impact` (a negative number for a penalty) is scaled by these.
    geofence_mult: float = 1.0
    incident_mult: float = 1.0
    late_night_mult: float = 1.0
    help_poi_mult: float = 1.0  # applied to positive (bonus) impact

    # Category-level severity bumps.  Additive to the base severity so a
    # persona-1.5 on "accident" reads a base-4 accident as sev=4·1.5=6.
    # Missing categories default to 1.0.
    severity_bumps: Mapping[str, float] = field(default_factory=dict)

    # Extra persona-only penalties (non-negative).
    remote_penalty: float = 0.0        # applied when nearest help POI > remote_help_km
    remote_help_km: float = 4.0

    # Depart-hour comfort: hours outside this set add a small persona penalty.
    # An empty set means "no preference"; the check is skipped.
    preferred_hours: Tuple[int, ...] = ()
    off_hour_penalty: float = 0.0

    # Band ladder — a tuple (safe_min, caution_min, high_risk_min).  A
    # conservative persona shifts these upward (safer scores required to
    # earn the same band); a tolerant persona shifts them down.
    band_thresholds: Tuple[int, int, int] = (80, 60, 35)

    # Route-planner α — persona's default safety weight for A* edge cost.
    # Anchored on `routing.plan_safest_route`'s α=4.5.  Family bumps it,
    # adventure lowers it.
    route_alpha: float = 4.5

    # Broadcast cadence (minutes between contact updates).  Family/senior
    # personas tighten it; adventure loosens.
    broadcast_minutes: int = 30

    # Advisory bump: how many rungs to force the Advisory brief upward for
    # this persona (0..2).  Applied by the Advisory tab if the persona is
    # active; also surfaced in the Prism report for transparency.
    advisory_bump_level: int = 0

    # Which help POI types matter most.  Ordering used in the checklist +
    # broadcast card.  Default = the safety.HELP_POI_TYPES set as a list.
    help_poi_priority: Tuple[str, ...] = tuple()

    # Deterministic packing / prep checklist for this persona.
    checklist: Tuple[str, ...] = tuple()


# Preset personas.  Six is the sweet spot — enough for real coverage without
# turning the UI into a menu of a hundred edge cases.  Each `route_alpha`
# / bumps below has a one-line justification in the trailing comment.

PERSONAS: dict[str, PersonaProfile] = {
    "solo-woman": PersonaProfile(
        id="solo-woman",
        label="Solo woman traveller",
        icon="♀",
        blurb=(
            "Late-night penalties weighted heavier, help-POI proximity matters more, "
            "geofenced zones are hard-avoid.  Broadcast cadence tightened to 20 min."
        ),
        geofence_mult=1.35,        # a geofenced sector is a harder no-go
        incident_mult=1.20,        # sexual-assault / harassment reports are under-counted
        late_night_mult=2.10,      # 22:00-05:00 is the single largest solo-female-risk factor
        help_poi_mult=1.30,        # nearby help asymmetrically valuable
        severity_bumps={"other": 1.35, "roadblock": 1.10},
        remote_penalty=6.0,
        remote_help_km=3.0,
        preferred_hours=tuple(range(7, 20)),
        off_hour_penalty=4.5,
        band_thresholds=(85, 70, 45),   # tighter bands
        route_alpha=6.0,
        broadcast_minutes=20,
        advisory_bump_level=1,
        help_poi_priority=("police", "tourist_help_desk", "hospital", "clinic", "fire"),
        checklist=(
            "Share live location with 2+ trusted contacts (see Beacon tab).",
            "Screenshot the two nearest police POIs before leaving.",
            "Set a 20-min broadcast cadence in Live Trip — WaySafe auto-pings.",
            "Avoid depart windows between 22:00-05:00 unless corridor is Safe (≥85).",
            "Carry a whistle and keep one hand free on transit.",
            "Note the nearest 24/7 tourist help desk on arrival.",
        ),
    ),
    "family-kids": PersonaProfile(
        id="family-kids",
        label="Family with children",
        icon="👨‍👩‍👧",
        blurb=(
            "Medical-POI proximity dominates.  Geofenced areas are hard-avoid; "
            "route α favours safest over fastest.  Broadcast cadence 15 min."
        ),
        geofence_mult=1.50,        # kids don't recover from a mistake as fast
        incident_mult=1.15,
        late_night_mult=1.30,
        help_poi_mult=1.40,
        severity_bumps={"accident": 1.30, "landslide": 1.20, "flooding": 1.25},
        remote_penalty=9.0,
        remote_help_km=2.5,
        preferred_hours=tuple(range(6, 20)),
        off_hour_penalty=3.5,
        band_thresholds=(85, 70, 50),
        route_alpha=7.5,
        broadcast_minutes=15,
        advisory_bump_level=1,
        help_poi_priority=("hospital", "clinic", "police", "fire", "tourist_help_desk"),
        checklist=(
            "Pre-plan the two nearest paediatric-capable hospitals.",
            "Pack: ORS, thermometer, child-dose paracetamol, phone chargers.",
            "Route via safest, not fastest — Prism suggests α ≥ 7.5.",
            "Set 15-min broadcast cadence; add both parents to Beacon.",
            "Book stays scored StaySafe ≥80 with a 24/7 desk.",
            "Skip depart windows 21:00-06:00 unless corridor is Safe.",
        ),
    ),
    "senior": PersonaProfile(
        id="senior",
        label="Senior / mobility-conscious",
        icon="🧓",
        blurb=(
            "Reach-to-medical dominates; walkability short-radius.  Route α favours "
            "safest.  Broadcast cadence 25 min to match slower pace."
        ),
        geofence_mult=1.25,
        incident_mult=1.10,
        late_night_mult=1.60,
        help_poi_mult=1.50,
        severity_bumps={"accident": 1.25, "landslide": 1.30, "flooding": 1.20},
        remote_penalty=10.0,
        remote_help_km=2.0,       # walkability short
        preferred_hours=tuple(range(7, 19)),
        off_hour_penalty=4.0,
        band_thresholds=(85, 70, 50),
        route_alpha=6.5,
        broadcast_minutes=25,
        advisory_bump_level=1,
        help_poi_priority=("hospital", "clinic", "police", "tourist_help_desk", "fire"),
        checklist=(
            "Pre-flag two hospitals within 2 km of stay + route.",
            "Carry medication list + emergency contacts in phone lock-screen.",
            "Route via safest — Prism suggests α ≥ 6.5.",
            "Avoid depart windows 19:00-07:00; heat dips help.",
            "Enable 25-min broadcast cadence — matches slower travel pace.",
        ),
    ),
    "business": PersonaProfile(
        id="business",
        label="Business / punctual",
        icon="💼",
        blurb=(
            "Baseline lens.  Speed matters — route α leans fastest.  ETA "
            "reliability trumps sight-seeing detours.  Broadcast cadence 45 min."
        ),
        geofence_mult=1.10,
        incident_mult=1.00,
        late_night_mult=1.15,
        help_poi_mult=1.00,
        severity_bumps={},
        remote_penalty=2.0,
        remote_help_km=5.0,
        preferred_hours=tuple(range(6, 22)),
        off_hour_penalty=1.5,
        band_thresholds=(80, 60, 35),
        route_alpha=3.0,           # closer to fastest
        broadcast_minutes=45,
        advisory_bump_level=0,
        help_poi_priority=("tourist_help_desk", "police", "hospital", "clinic", "fire"),
        checklist=(
            "Book stays with reliable Wi-Fi + 24/7 desk (StaySafe ≥75).",
            "Set 45-min broadcast cadence; add company duty-of-care contact.",
            "Route via fastest; Prism suggests α ≈ 3.0 unless corridor Elevated.",
            "Screenshot meeting-venue → nearest help POI mapping.",
        ),
    ),
    "adventure": PersonaProfile(
        id="adventure",
        label="Adventure / solo",
        icon="🎒",
        blurb=(
            "Higher tolerance — bands loosened, α relaxed.  Off-hour depart OK "
            "but broadcast cadence *tightens* because remote = out of help range."
        ),
        geofence_mult=0.90,
        incident_mult=0.95,
        late_night_mult=1.20,
        help_poi_mult=0.85,
        severity_bumps={"landslide": 1.30, "flooding": 1.25},  # nature > urban
        remote_penalty=12.0,       # if far from ANY help, penalise hard
        remote_help_km=3.5,
        preferred_hours=tuple(range(5, 24)),
        off_hour_penalty=1.0,
        band_thresholds=(75, 55, 30),
        route_alpha=3.0,
        broadcast_minutes=20,      # remote = broadcast MORE, not less
        advisory_bump_level=0,
        help_poi_priority=("hospital", "police", "clinic", "fire", "tourist_help_desk"),
        checklist=(
            "Download offline map tiles for the corridor before leaving Wi-Fi.",
            "Set 20-min broadcast cadence — remote means help is slower.",
            "Carry: first-aid, headlamp, water, whistle, offline map.",
            "Register the itinerary with Beacon; add satellite-comms contact if possible.",
            "Landslide/flood severity is bumped 30% — respect Sentinel escalations.",
        ),
    ),
    "group": PersonaProfile(
        id="group",
        label="Backpacker / student group",
        icon="🧑‍🤝‍🧑",
        blurb=(
            "Crowd = safety.  Bands slightly loosened, help-POI weighted less "
            "(there are more of you)."
        ),
        geofence_mult=1.10,
        incident_mult=0.95,
        late_night_mult=1.00,
        help_poi_mult=0.90,
        severity_bumps={},
        remote_penalty=3.0,
        remote_help_km=4.5,
        preferred_hours=tuple(range(5, 24)),
        off_hour_penalty=0.5,
        band_thresholds=(78, 58, 33),
        route_alpha=3.5,
        broadcast_minutes=60,
        advisory_bump_level=0,
        help_poi_priority=("tourist_help_desk", "hospital", "police", "clinic", "fire"),
        checklist=(
            "Nominate a group lead in Beacon — one broadcast covers the party.",
            "Set a common 60-min check-in cadence.",
            "Split evening returns into 2+ subgroups; regroup at Safe ≥80 pin.",
            "Buddy-up any solo detour — Prism's tolerance assumes the group is together.",
        ),
    ),
}


DEFAULT_PERSONA = "solo-woman"


# --- Point-level lens -----------------------------------------------------

@dataclass
class LensFactor:
    """One re-priced factor in a persona lens."""
    label: str
    base_impact: float
    persona_impact: float
    delta: float
    reason: str = ""


@dataclass
class PersonaLens:
    """One point's safety under a persona.

    `base_score` is the untouched `SafetyResult.score`; `persona_score` is
    the same corridor after persona multipliers, extras and band-threshold
    ladder are applied.  `delta = persona_score - base_score` (negative when
    the persona feels less safe than the average traveller).
    """
    label: str
    lat: float
    lon: float
    base_score: int
    base_band: str
    persona_score: int
    persona_band: str
    delta: int
    factors: List[LensFactor] = field(default_factory=list)
    extras: List[LensFactor] = field(default_factory=list)
    headline: str = ""
    advisory_level: str = "All clear"
    nearest_help_km: Optional[float] = None
    incidents_nearby: int = 0

    def to_dict(self) -> dict:
        return {
            "label": self.label,
            "lat": self.lat, "lon": self.lon,
            "base_score": self.base_score, "base_band": self.base_band,
            "persona_score": self.persona_score, "persona_band": self.persona_band,
            "delta": self.delta,
            "factors": [asdict(f) for f in self.factors],
            "extras": [asdict(f) for f in self.extras],
            "headline": self.headline,
            "advisory_level": self.advisory_level,
            "nearest_help_km": self.nearest_help_km,
            "incidents_nearby": self.incidents_nearby,
        }


def _persona_band(score: int, thresholds: Tuple[int, int, int]) -> str:
    safe, caution, high = thresholds
    if score >= safe:    return "Safe"
    if score >= caution: return "Caution"
    if score >= high:    return "High Risk"
    return "Danger"


def _base_penalty_for_factor(f: dict) -> float:
    """Convert a `safety.compute_safety` factor back to its unsigned penalty."""
    return -float(f.get("impact", 0.0)) if f.get("impact", 0.0) < 0 else 0.0


def _base_bonus_for_factor(f: dict) -> float:
    """Convert a `safety.compute_safety` factor back to its bonus."""
    return float(f.get("impact", 0.0)) if f.get("impact", 0.0) > 0 else 0.0


def compute_persona_lens(
    label: str,
    lat: float,
    lon: float,
    persona: PersonaProfile,
    incidents: Sequence[Mapping],
    geofences: Mapping,
    pois: Sequence[Mapping],
    now: Optional[datetime] = None,
    base: Optional[SafetyResult] = None,
) -> PersonaLens:
    """Re-price one point's safety under a persona.

    Recomputes the penalty ledger from `safety.compute_safety`'s factors
    with the persona's multipliers, adds persona-only extras (remote
    penalty, off-hour penalty), then bands under the persona threshold
    ladder.  Score-order semantics are preserved: higher = safer, 0..100.
    """
    now = now or datetime.utcnow()
    if base is None:
        base = compute_safety(lat, lon, incidents, geofences, pois, now=now)

    # Start from a clean penalty ledger — we rebuild it under the persona so
    # each factor can be tracked separately (base vs persona vs delta).
    factors: List[LensFactor] = []
    total_persona_penalty = 0.0
    total_base_penalty = 0.0

    for f in base.factors:
        label_f = str(f.get("label", ""))
        impact = float(f.get("impact", 0.0))
        base_pen = _base_penalty_for_factor(f)
        base_bonus = _base_bonus_for_factor(f)
        if base_pen > 0:
            # Which multiplier applies?  Match on the label prefix — the same
            # keys `safety.compute_safety` uses.  Missing → 1.0 (no-op).
            if "Geofenced risk zone" in label_f:
                mult = persona.geofence_mult
                reason = f"geofence ×{mult:.2f}"
            elif "recent incident" in label_f:
                # Fold both incident-count multiplier and severity bumps.
                mult = persona.incident_mult
                # Severity bumps are approximated by the population average:
                # take a weighted mean of the persona severity_bumps.
                # This is an intentional simplification — for a per-incident
                # accurate rescale you'd redo the distance kernel; for a
                # persona lens the averaged bump is honest and cheap.
                if persona.severity_bumps:
                    mult *= sum(persona.severity_bumps.values()) / len(persona.severity_bumps)
                reason = f"incidents ×{mult:.2f}"
            elif "Late-night" in label_f:
                mult = persona.late_night_mult
                reason = f"late-night ×{mult:.2f}"
            else:
                mult = 1.0
                reason = "unchanged"
            persona_pen = base_pen * mult
            factors.append(LensFactor(
                label=label_f,
                base_impact=-round(base_pen, 2),
                persona_impact=-round(persona_pen, 2),
                delta=round(-(persona_pen - base_pen), 2),
                reason=reason,
            ))
            total_base_penalty += base_pen
            total_persona_penalty += persona_pen
        elif base_bonus > 0:
            mult = persona.help_poi_mult if "help POI" in label_f else 1.0
            persona_bonus = base_bonus * mult
            factors.append(LensFactor(
                label=label_f,
                base_impact=round(base_bonus, 2),
                persona_impact=round(persona_bonus, 2),
                delta=round(persona_bonus - base_bonus, 2),
                reason=f"help POI ×{mult:.2f}" if mult != 1.0 else "unchanged",
            ))
            # Note: bonuses reduce penalty, so subtract.
            total_base_penalty -= base_bonus
            total_persona_penalty -= persona_bonus

    # Extras: remote-help penalty + off-hour penalty.
    extras: List[LensFactor] = []
    if persona.remote_penalty > 0 and base.nearest_help_km is not None:
        if base.nearest_help_km > persona.remote_help_km:
            total_persona_penalty += persona.remote_penalty
            extras.append(LensFactor(
                label=f"Nearest help {base.nearest_help_km:.1f} km > {persona.remote_help_km:.1f} km",
                base_impact=0.0,
                persona_impact=-round(persona.remote_penalty, 2),
                delta=-round(persona.remote_penalty, 2),
                reason=f"remote-help penalty for {persona.label}",
            ))
    if persona.preferred_hours and persona.off_hour_penalty > 0:
        if now.hour not in persona.preferred_hours:
            total_persona_penalty += persona.off_hour_penalty
            extras.append(LensFactor(
                label=f"Depart at {now.hour:02d}:00 outside preferred window",
                base_impact=0.0,
                persona_impact=-round(persona.off_hour_penalty, 2),
                delta=-round(persona.off_hour_penalty, 2),
                reason=f"off-hour penalty for {persona.label}",
            ))

    # Persona score.  The formula mirrors `safety.compute_safety`'s clamp.
    persona_score = int(round(max(0.0, min(100.0, 100.0 - total_persona_penalty))))
    base_score = base.score
    delta = persona_score - base_score
    persona_band = _persona_band(persona_score, persona.band_thresholds)

    # Headline — first-match ladder keyed to the delta.
    if delta <= -20:
        headline = f"{persona.label}: same corridor reads {abs(delta)} pts lower."
    elif delta <= -10:
        headline = f"{persona.label}: notable downgrade ({delta} pts) — see extras below."
    elif delta <= -3:
        headline = f"{persona.label}: mild downgrade ({delta} pts)."
    elif delta >= 5:
        headline = f"{persona.label}: reads {delta:+d} pts vs the average traveller."
    else:
        headline = f"{persona.label}: reads roughly the same as the base score."

    # Advisory level — the same 4-rung ladder as `advisory.py`.
    def _advisory_from_band(band: str) -> str:
        return {"Safe": "All clear", "Caution": "Caution",
                "High Risk": "Elevated", "Danger": "Critical"}[band]
    advisory_level = _advisory_from_band(persona_band)
    # Persona-driven bump: nudge one rung up if the persona's `advisory_bump_level` says so.
    if persona.advisory_bump_level > 0:
        ladder = ["All clear", "Caution", "Elevated", "Critical"]
        idx = ladder.index(advisory_level)
        advisory_level = ladder[min(len(ladder) - 1, idx + persona.advisory_bump_level)]

    return PersonaLens(
        label=label,
        lat=float(lat), lon=float(lon),
        base_score=base_score,
        base_band=base.band,
        persona_score=persona_score,
        persona_band=persona_band,
        delta=delta,
        factors=factors,
        extras=extras,
        headline=headline,
        advisory_level=advisory_level,
        nearest_help_km=base.nearest_help_km,
        incidents_nearby=base.incidents_nearby,
    )


# --- Multi-point report ---------------------------------------------------

@dataclass
class PrismReport:
    """A persona lens across multiple watched points.

    Aggregates each point's `PersonaLens`, composes a persona-tuned lesson
    stack + checklist, and quotes the recommended route α and broadcast
    cadence.  Serialises under `waysafe.prism.v1`.
    """
    composed_at: str
    persona_id: str
    persona_label: str
    persona_icon: str
    persona_blurb: str
    points: List[PersonaLens]
    avg_base_score: int
    avg_persona_score: int
    worst: Optional[PersonaLens]
    strongest_downgrade: Optional[PersonaLens]
    route_alpha: float
    broadcast_minutes: int
    advisory_bump_level: int
    band_thresholds: Tuple[int, int, int]
    lessons: List[str]
    checklist: List[str]
    help_poi_priority: List[str]
    headline: str
    advisory: str

    def to_dict(self) -> dict:
        return {
            "envelope": "waysafe.prism.v1",
            "composed_at": self.composed_at,
            "persona": {
                "id": self.persona_id,
                "label": self.persona_label,
                "icon": self.persona_icon,
                "blurb": self.persona_blurb,
            },
            "points": [p.to_dict() for p in self.points],
            "aggregate": {
                "avg_base_score": self.avg_base_score,
                "avg_persona_score": self.avg_persona_score,
                "worst_label": self.worst.label if self.worst else None,
                "strongest_downgrade_label":
                    self.strongest_downgrade.label if self.strongest_downgrade else None,
            },
            "profile": {
                "route_alpha": self.route_alpha,
                "broadcast_minutes": self.broadcast_minutes,
                "advisory_bump_level": self.advisory_bump_level,
                "band_thresholds": list(self.band_thresholds),
                "help_poi_priority": list(self.help_poi_priority),
            },
            "lessons": list(self.lessons),
            "checklist": list(self.checklist),
            "headline": self.headline,
            "advisory": self.advisory,
        }

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    def to_markdown(self) -> str:
        lines: List[str] = []
        lines.append(f"# 🔎 Prism — Persona Lens")
        lines.append("")
        lines.append(f"**{self.persona_icon}  {self.persona_label}** — {self.persona_blurb}")
        lines.append("")
        lines.append(f"_Composed at {self.composed_at}_")
        lines.append("")
        lines.append(f"> **{self.headline}**")
        lines.append("")
        lines.append(f"**Advisory:** {self.advisory}")
        lines.append("")
        lines.append(f"**Profile knobs** — route α {self.route_alpha:.1f} · "
                     f"broadcast every {self.broadcast_minutes} min · "
                     f"band ladder Safe ≥{self.band_thresholds[0]} · "
                     f"Caution ≥{self.band_thresholds[1]} · "
                     f"High Risk ≥{self.band_thresholds[2]}")
        lines.append("")
        lines.append("## Watched points")
        lines.append("")
        lines.append("| Point | Base | Persona | Δ | Band | Advisory |")
        lines.append("|---|---:|---:|---:|---|---|")
        for p in self.points:
            arrow = "→" if p.delta == 0 else ("↑" if p.delta > 0 else "↓")
            lines.append(
                f"| {p.label} | {p.base_score} | {p.persona_score} | "
                f"{p.delta:+d} {arrow} | {p.persona_band} | {p.advisory_level} |"
            )
        lines.append("")
        if self.worst:
            lines.append(f"**Worst point under this lens:** {self.worst.label} "
                         f"({self.worst.persona_score}/100 · {self.worst.persona_band}).")
        if self.strongest_downgrade and self.strongest_downgrade.delta < -2:
            lines.append(
                f"**Strongest downgrade vs base:** {self.strongest_downgrade.label} "
                f"({self.strongest_downgrade.delta:+d} pts)."
            )
        lines.append("")
        lines.append("## Lessons")
        for i, l in enumerate(self.lessons, 1):
            lines.append(f"{i}. {l}")
        lines.append("")
        lines.append("## Pre-departure checklist")
        for item in self.checklist:
            lines.append(f"- [ ] {item}")
        lines.append("")
        return "\n".join(lines)


def _compose_lessons(
    persona: PersonaProfile,
    lenses: Sequence[PersonaLens],
    now: datetime,
) -> List[str]:
    """First-match-wins lesson ladder keyed to the persona + lens ledger."""
    out: List[str] = []
    if not lenses:
        return out

    n_danger = sum(1 for l in lenses if l.persona_band == "Danger")
    n_high   = sum(1 for l in lenses if l.persona_band == "High Risk")
    n_bumped = sum(1 for l in lenses if l.delta <= -8)
    n_remote = sum(1 for l in lenses if l.extras and any(
        "Nearest help" in e.label for e in l.extras
    ))
    off_hour_hits = sum(1 for l in lenses if l.extras and any(
        "outside preferred window" in e.label for e in l.extras
    ))
    max_downgrade = min((l.delta for l in lenses), default=0)

    if n_danger:
        out.append(
            f"🔴 {n_danger} point(s) drop to Danger under the {persona.label} lens — "
            f"reconsider the itinerary or wait for the advisory to clear."
        )
    if n_high and not n_danger:
        out.append(
            f"🟠 {n_high} point(s) sit at High Risk under this lens — "
            f"open Advisory for the per-point break-down and depart windows."
        )
    if n_bumped >= 2:
        out.append(
            f"📉 {n_bumped} points read ≥8 pts lower than the base traveller — "
            f"the corridor is more sensitive to who is walking it than the raw score suggests."
        )
    elif max_downgrade <= -10:
        out.append(
            f"📉 Strongest downgrade is {max_downgrade:+d} pts — check the Extras "
            f"column below for the persona-only cost drivers."
        )
    if n_remote:
        out.append(
            f"🚑 {n_remote} point(s) are outside the {persona.remote_help_km:.1f} km "
            f"help-POI ring — pre-flag the nearest hospital before leaving."
        )
    if off_hour_hits:
        pref = ", ".join(f"{h:02d}" for h in persona.preferred_hours[:1] + persona.preferred_hours[-1:])
        out.append(
            f"⏱ You're outside the persona's preferred depart window "
            f"(hours {persona.preferred_hours[0]:02d}-{persona.preferred_hours[-1]:02d}). "
            f"Open Tempo to sweep for a safer slot."
        )
    if persona.route_alpha >= 6.0:
        out.append(
            f"🛡 This persona favours safest over fastest — Plan Route α = "
            f"{persona.route_alpha:.1f} (base is 4.5)."
        )
    elif persona.route_alpha <= 3.5:
        out.append(
            f"🏃 Persona defaults to fast-first (α = {persona.route_alpha:.1f}); "
            f"if the corridor is Elevated, override to safest in Plan Route."
        )
    out.append(
        f"📡 Broadcast cadence recommendation: every {persona.broadcast_minutes} min "
        f"— set it in Live Trip Companion so Beacon receives regular pings."
    )
    if persona.advisory_bump_level > 0:
        out.append(
            f"⚠️ Advisory forced +{persona.advisory_bump_level} rung(s) for this persona — "
            f"the base level would understate the risk for you."
        )
    if not out:
        out.append(
            "🟢 Every watched point reads Safe/Caution under this lens — "
            "no persona-specific action items today."
        )
    return out


def compute_prism_report(
    watched: Sequence[Mapping],
    persona: PersonaProfile,
    incidents: Sequence[Mapping],
    geofences: Mapping,
    pois: Sequence[Mapping],
    now: Optional[datetime] = None,
) -> PrismReport:
    """Compose a Prism report for one persona across N watched points.

    Each `watched` entry: {"label": str, "lat": float, "lon": float}.
    """
    now = now or datetime.utcnow()
    lenses: List[PersonaLens] = []
    for w in watched:
        try:
            lat = float(w["lat"]); lon = float(w["lon"])
        except (KeyError, TypeError, ValueError):
            continue
        label = str(w.get("label", f"({lat:.3f}, {lon:.3f})"))
        lens = compute_persona_lens(
            label, lat, lon, persona, incidents, geofences, pois, now=now,
        )
        lenses.append(lens)

    if lenses:
        avg_base = int(round(sum(l.base_score for l in lenses) / len(lenses)))
        avg_persona = int(round(sum(l.persona_score for l in lenses) / len(lenses)))
        worst = min(lenses, key=lambda l: l.persona_score)
        strongest_dg = min(lenses, key=lambda l: l.delta)
    else:
        avg_base = avg_persona = 0
        worst = strongest_dg = None

    lessons = _compose_lessons(persona, lenses, now)

    # Headline: names the persona + the aggregate delta.
    if lenses:
        agg_delta = avg_persona - avg_base
        if agg_delta <= -10:
            headline = (
                f"{persona.label} reads the current watch-list {abs(agg_delta)} pts lower "
                f"on average ({avg_persona} vs {avg_base})."
            )
        elif agg_delta <= -3:
            headline = (
                f"{persona.label} sees a mild downgrade ({agg_delta:+d} pts on average) "
                f"across the watch-list."
            )
        elif agg_delta >= 3:
            headline = (
                f"{persona.label} reads the corridor {agg_delta:+d} pts more forgiving on average."
            )
        else:
            headline = (
                f"{persona.label} lens tracks the base score within ±3 pts on average."
            )
    else:
        headline = f"{persona.label}: no watched points."

    # Advisory: the WORST persona-advisory in the list is the aggregate.
    ladder = ["All clear", "Caution", "Elevated", "Critical"]
    if lenses:
        max_rung = max(ladder.index(l.advisory_level) for l in lenses)
        advisory = ladder[max_rung]
    else:
        advisory = "All clear"

    return PrismReport(
        composed_at=now.isoformat(timespec="seconds"),
        persona_id=persona.id,
        persona_label=persona.label,
        persona_icon=persona.icon,
        persona_blurb=persona.blurb,
        points=lenses,
        avg_base_score=avg_base,
        avg_persona_score=avg_persona,
        worst=worst,
        strongest_downgrade=strongest_dg,
        route_alpha=persona.route_alpha,
        broadcast_minutes=persona.broadcast_minutes,
        advisory_bump_level=persona.advisory_bump_level,
        band_thresholds=persona.band_thresholds,
        lessons=lessons,
        checklist=list(persona.checklist),
        help_poi_priority=list(persona.help_poi_priority),
        headline=headline,
        advisory=advisory,
    )


# --- Cross-persona comparison --------------------------------------------

def compute_persona_matrix(
    watched: Sequence[Mapping],
    incidents: Sequence[Mapping],
    geofences: Mapping,
    pois: Sequence[Mapping],
    now: Optional[datetime] = None,
    persona_ids: Optional[Sequence[str]] = None,
) -> dict:
    """Score every watched point under EVERY persona.

    Answers *"who does this corridor work for?"* — a matrix with rows =
    watched points, columns = personas, cells = the persona score.  The
    caller can pass a subset of `persona_ids` to restrict the columns.
    """
    now = now or datetime.utcnow()
    keys = list(persona_ids) if persona_ids else list(PERSONAS.keys())
    cols: List[dict] = []
    for pid in keys:
        p = PERSONAS.get(pid)
        if not p:
            continue
        cols.append({
            "id": p.id, "label": p.label, "icon": p.icon,
            "route_alpha": p.route_alpha,
            "broadcast_minutes": p.broadcast_minutes,
        })
    rows: List[dict] = []
    for w in watched:
        try:
            lat = float(w["lat"]); lon = float(w["lon"])
        except (KeyError, TypeError, ValueError):
            continue
        label = str(w.get("label", f"({lat:.3f}, {lon:.3f})"))
        base = compute_safety(lat, lon, incidents, geofences, pois, now=now)
        cells: List[dict] = []
        for pid in keys:
            p = PERSONAS.get(pid)
            if not p:
                continue
            lens = compute_persona_lens(
                label, lat, lon, p, incidents, geofences, pois, now=now, base=base,
            )
            cells.append({
                "persona_id": pid,
                "persona_score": lens.persona_score,
                "persona_band": lens.persona_band,
                "delta": lens.delta,
                "advisory_level": lens.advisory_level,
            })
        rows.append({
            "label": label, "lat": lat, "lon": lon,
            "base_score": base.score, "base_band": base.band,
            "cells": cells,
        })

    # Per-persona aggregate — mean persona score across all watched points.
    col_aggs: List[dict] = []
    for pid in keys:
        p = PERSONAS.get(pid)
        if not p:
            continue
        scores = []
        for r in rows:
            for c in r["cells"]:
                if c["persona_id"] == pid:
                    scores.append(c["persona_score"])
        avg = int(round(sum(scores) / len(scores))) if scores else 0
        col_aggs.append({
            "persona_id": pid,
            "persona_label": p.label,
            "persona_icon": p.icon,
            "avg_persona_score": avg,
            "route_alpha": p.route_alpha,
        })
    col_aggs.sort(key=lambda c: -c["avg_persona_score"])

    return {
        "envelope": "waysafe.prism.matrix.v1",
        "composed_at": now.isoformat(timespec="seconds"),
        "columns": cols,
        "rows": rows,
        "column_aggregates": col_aggs,
        "best_persona_id": col_aggs[0]["persona_id"] if col_aggs else None,
        "worst_persona_id": col_aggs[-1]["persona_id"] if col_aggs else None,
    }


__all__ = [
    "PersonaProfile", "PERSONAS", "DEFAULT_PERSONA",
    "PersonaLens", "LensFactor", "PrismReport",
    "compute_persona_lens", "compute_prism_report", "compute_persona_matrix",
]
