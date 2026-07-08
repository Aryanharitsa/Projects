"""Interviewer Handoff Composer (Day 77 · Brief).

Python mirror of `frontend/src/lib/brief.ts`. Every physics constant here
is duplicated in TypeScript so the API and the browser produce
byte-identical briefs.

Given a Role's QueryPlan, a candidate, an optional InterviewRecord, and a
target stage, produce a deterministic packet: focus dims for THIS stage,
candidate-specific probes, filtered questions from the interview kit,
"do not re-cover" dims, flags, tiles, and headline metrics.

No LLM, no I/O.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Literal

from app.services.interview import (
    RubricDim,
    Stage,
    STAGE_LABEL,
    STAGES,
    build_questions,
    build_rubric,
)
from app.services.match import MatchResult, QueryPlan, match_candidate

# ─────────── physics constants (mirrored 1:1 with brief.ts) ───────────

TIME_BUDGET_BY_STAGE: dict[Stage, int] = {
    "phone_screen": 30,
    "technical": 60,
    "system_design": 60,
    "behavioral": 45,
}

STAGE_AFFINITY: dict[Stage, dict[str, float]] = {
    "phone_screen": {
        "communication": 0.35,
        "motivation": 0.30,
        "collaboration": 0.10,
        "ownership": 0.10,
        "frontend_depth": 0.03,
        "backend_depth": 0.03,
        "data_systems": 0.03,
        "cloud_infra": 0.02,
        "ml_systems": 0.02,
        "language_craft": 0.02,
    },
    "technical": {
        "frontend_depth": 0.20,
        "backend_depth": 0.20,
        "data_systems": 0.15,
        "language_craft": 0.15,
        "ml_systems": 0.10,
        "cloud_infra": 0.08,
        "communication": 0.06,
        "ownership": 0.06,
    },
    "system_design": {
        "system_design_skill": 0.35,
        "backend_depth": 0.15,
        "data_systems": 0.15,
        "cloud_infra": 0.15,
        "frontend_depth": 0.06,
        "ml_systems": 0.06,
        "scope_influence": 0.05,
        "communication": 0.03,
    },
    "behavioral": {
        "collaboration": 0.30,
        "ownership": 0.25,
        "communication": 0.20,
        "motivation": 0.15,
        "scope_influence": 0.10,
    },
}

COVERED_RATING_FLOOR = 4
PARTIAL_MIN_RATING = 3
DIM_FOCUS_WEIGHT_FLOOR = 0.05
MAX_FOCUS_DIMS = 4
MAX_QUESTIONS = 5
MAX_PROBES = 6
MAX_TALKING = 3

CoverageState = Literal["covered", "partial", "open"]

COVERAGE_HEX: dict[CoverageState, str] = {
    "covered": "#22c55e",
    "partial": "#f59e0b",
    "open": "#f43f5e",
}

COVERAGE_LABEL: dict[CoverageState, str] = {
    "covered": "Covered",
    "partial": "Partial signal",
    "open": "Open",
}

ProbeKind = Literal[
    "missing_skill",
    "matched_deepen",
    "seniority_scope",
    "location_fit",
    "motivation",
    "ownership_probe",
]

PROBE_HEX: dict[ProbeKind, str] = {
    "missing_skill": "#f43f5e",
    "matched_deepen": "#22c55e",
    "seniority_scope": "#a855f7",
    "location_fit": "#0ea5e9",
    "motivation": "#f59e0b",
    "ownership_probe": "#6366f1",
}

PROBE_LABEL: dict[ProbeKind, str] = {
    "missing_skill": "Missing skill",
    "matched_deepen": "Deepen",
    "seniority_scope": "Scope",
    "location_fit": "Location",
    "motivation": "Motivation",
    "ownership_probe": "Ownership",
}

BriefFlag = Literal[
    "low_match_score",
    "missing_required_skill",
    "seniority_mismatch",
    "location_partial",
    "thin_signal",
    "no_prior_stages",
    "key_dim_open",
]

FLAG_LABEL: dict[BriefFlag, str] = {
    "low_match_score": "Low match score",
    "missing_required_skill": "Missing required skill",
    "seniority_mismatch": "Seniority mismatch",
    "location_partial": "Location partial",
    "thin_signal": "Thin prior signal",
    "no_prior_stages": "No prior stages",
    "key_dim_open": "Key dim still open",
}

FLAG_TONE: dict[BriefFlag, str] = {
    "low_match_score": "rose",
    "missing_required_skill": "rose",
    "seniority_mismatch": "amber",
    "location_partial": "sky",
    "thin_signal": "amber",
    "no_prior_stages": "slate",
    "key_dim_open": "rose",
}

SENIORITY_TIER: dict[str, int] = {
    "intern": 0,
    "junior": 1,
    "mid": 2,
    "senior": 3,
    "lead": 3,
    "staff": 4,
    "principal": 5,
}


# ─────────── data classes ───────────


@dataclass
class DimStatus:
    key: str
    label: str
    description: str
    weight: float
    state: CoverageState
    best_rating: int | None
    rated_in_stages: list[Stage]


@dataclass
class FocusDim:
    key: str
    label: str
    weight: float
    gap: float
    affinity: float
    priority: float
    minutes: int
    why_line: str


@dataclass
class Probe:
    kind: ProbeKind
    angle: str
    reason: str
    signal_dim: str | None = None


@dataclass
class TalkingPoint:
    hook: str
    reference: str


@dataclass
class BriefFlagEntry:
    kind: BriefFlag
    label: str
    detail: str


@dataclass
class BriefQuestion:
    id: str
    prompt: str
    followup: str | None
    signal_dim: str
    difficulty: int
    source: str
    priority: float


@dataclass
class BriefTile:
    key: str
    label: str
    value: str
    sub: str | None = None


@dataclass
class BriefBundle:
    version: str = "credicrew.brief.v1"
    role_id: str = ""
    role_name: str = ""
    candidate_id: int = 0
    candidate_name: str = ""
    stage: Stage = "technical"
    stage_label: str = ""
    intro: str = ""
    headline: str = ""
    match: MatchResult | None = None
    time_budget_min: int = 60
    dim_statuses: list[DimStatus] = field(default_factory=list)
    focus: list[FocusDim] = field(default_factory=list)
    probes: list[Probe] = field(default_factory=list)
    talking_points: list[TalkingPoint] = field(default_factory=list)
    questions: list[BriefQuestion] = field(default_factory=list)
    do_not_re_cover: list[DimStatus] = field(default_factory=list)
    flags: list[BriefFlagEntry] = field(default_factory=list)
    tiles: list[BriefTile] = field(default_factory=list)
    criticality: int = 0
    decision_confidence: int = 0
    issued_at: int = 0
    rubric: list[RubricDim] = field(default_factory=list)


# ─────────── helpers ───────────


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _first_name(name: str | None) -> str:
    if not name:
        return "candidate"
    return name.split()[0] if name.split() else "candidate"


def _tier(rank: str | None) -> int | None:
    if not rank:
        return None
    return SENIORITY_TIER.get(rank.lower())


# ─────────── dim coverage ───────────


def analyze_coverage(
    rubric: list[RubricDim],
    interview: dict | None,
) -> list[DimStatus]:
    out: list[DimStatus] = []
    for dim in rubric:
        best: int | None = None
        staged: list[Stage] = []
        if interview:
            for stage in interview.get("stages") or []:
                stage_name = stage.get("stage")
                for sc in stage.get("scores") or []:
                    if sc.get("key") == dim.key and sc.get("rating") is not None:
                        r = int(sc["rating"])
                        if best is None or r > best:
                            best = r
                        if stage_name and stage_name not in staged:
                            staged.append(stage_name)
        if best is not None and best >= COVERED_RATING_FLOOR:
            state: CoverageState = "covered"
        elif best is not None and best >= PARTIAL_MIN_RATING:
            state = "partial"
        else:
            state = "open"
        out.append(
            DimStatus(
                key=dim.key,
                label=dim.label,
                description=dim.description,
                weight=dim.weight,
                state=state,
                best_rating=best,
                rated_in_stages=staged,
            )
        )
    return out


# ─────────── focus ───────────


def _state_gap(state: CoverageState) -> float:
    if state == "covered":
        return 0.0
    if state == "partial":
        return 0.4
    return 1.0


def _why_line(dim: DimStatus, stage: Stage, aff: float) -> str:
    stage_word = STAGE_LABEL[stage].lower()
    if dim.state == "open":
        state_word = "no prior signal"
    elif dim.state == "partial":
        state_word = f"only {dim.best_rating}/5 so far"
    else:
        state_word = "already saturated"
    if aff >= 0.2:
        aff_word = "core to this stage"
    elif aff >= 0.1:
        aff_word = "fits this stage"
    else:
        aff_word = "adjacent to this stage"
    return f"{dim.label.lower()} — {state_word}; {aff_word} ({stage_word})."


def pick_focus_dims(
    statuses: list[DimStatus],
    stage: Stage,
) -> list[FocusDim]:
    affinity_map = STAGE_AFFINITY.get(stage, {})
    scored: list[tuple[DimStatus, float, float, float]] = []
    for s in statuses:
        aff = affinity_map.get(s.key, 0.02)
        gap = _state_gap(s.state)
        priority = s.weight * gap * (0.5 + aff)
        if priority > 0:
            scored.append((s, aff, gap, priority))
    scored.sort(key=lambda x: -x[3])
    top = scored[:MAX_FOCUS_DIMS]
    total_priority = sum(x[3] for x in top) or 1.0
    budget = TIME_BUDGET_BY_STAGE[stage]
    out: list[FocusDim] = []
    for s, aff, gap, priority in top:
        share = priority / total_priority
        minutes = max(5, round(share * budget * 0.85))
        out.append(
            FocusDim(
                key=s.key,
                label=s.label,
                weight=round(s.weight, 3),
                gap=round(gap, 3),
                affinity=round(aff, 3),
                priority=round(priority, 4),
                minutes=minutes,
                why_line=_why_line(s, stage, aff),
            )
        )
    return out


# ─────────── probes ───────────


_SKILL_DIM_MAP: dict[str, str] = {
    "react": "frontend_depth", "next.js": "frontend_depth", "vue": "frontend_depth",
    "svelte": "frontend_depth", "angular": "frontend_depth", "tailwind": "frontend_depth",
    "typescript": "language_craft", "javascript": "language_craft", "python": "language_craft",
    "go": "language_craft", "rust": "language_craft", "java": "language_craft",
    "fastapi": "backend_depth", "flask": "backend_depth", "django": "backend_depth",
    "express": "backend_depth", "nest.js": "backend_depth",
    "postgres": "data_systems", "mysql": "data_systems", "mongodb": "data_systems",
    "redis": "data_systems", "kafka": "data_systems", "rabbitmq": "data_systems",
    "aws": "cloud_infra", "gcp": "cloud_infra", "azure": "cloud_infra",
    "docker": "cloud_infra", "kubernetes": "cloud_infra", "terraform": "cloud_infra",
    "pytorch": "ml_systems", "tensorflow": "ml_systems", "llm": "ml_systems",
    "nlp": "ml_systems", "ml": "ml_systems",
}


def _dim_for_skill(skill: str) -> str:
    return _SKILL_DIM_MAP.get(skill, "language_craft")


def build_probes(
    plan: QueryPlan,
    candidate: dict,
    match: MatchResult,
    stage: Stage,
) -> list[Probe]:
    out: list[Probe] = []
    bag = {
        t.lower()
        for t in (candidate.get("tags") or []) + (candidate.get("keywords") or [])
    }

    # Missing-skill probes.
    if stage != "behavioral":
        for skill in match.missing_skills[:3]:
            out.append(
                Probe(
                    kind="missing_skill",
                    angle=f"Probe {skill} familiarity — not on resume, but plan-required.",
                    reason=f"Candidate did not list {skill}; ask for the closest thing they have shipped and how long the ramp would be.",
                    signal_dim=_dim_for_skill(skill),
                )
            )

    # Matched-skill deep-dive.
    if stage != "behavioral":
        for skill in match.matched_skills[:3]:
            src = "tag" if skill in bag else "headline"
            out.append(
                Probe(
                    kind="matched_deepen",
                    angle=f"Deepen {skill} — candidate signals it; test depth vs. name-drop.",
                    reason=f"{skill} appears on candidate profile ({src}); probe the hardest bug they shipped in it.",
                    signal_dim=_dim_for_skill(skill),
                )
            )

    # Seniority scope probe.
    if stage in ("behavioral", "system_design", "phone_screen"):
        want_tier = _tier(plan.seniority)
        have_tier = _tier(match.seniority_candidate)
        if want_tier is not None:
            if have_tier is None:
                out.append(
                    Probe(
                        kind="seniority_scope",
                        angle=f"Establish scope — plan wants {plan.seniority}; candidate seniority unread.",
                        reason="Ask about the largest project they owned end-to-end and how many people they influenced.",
                        signal_dim="scope_influence",
                    )
                )
            elif have_tier < want_tier:
                out.append(
                    Probe(
                        kind="seniority_scope",
                        angle=f"Stretch check — candidate presents {match.seniority_candidate}, plan wants {plan.seniority}.",
                        reason="Ask how they would ramp into a role one tier above their current — do they name specific gaps or wave vaguely?",
                        signal_dim="scope_influence",
                    )
                )
            elif have_tier > want_tier:
                out.append(
                    Probe(
                        kind="seniority_scope",
                        angle=f"Over-tier — candidate {match.seniority_candidate}, plan {plan.seniority}; probe motivation.",
                        reason="Ask why the level down — comp, learning, life? A crisp answer is a good sign.",
                        signal_dim="motivation",
                    )
                )

    # Location probe.
    if stage in ("phone_screen", "behavioral"):
        if match.location_match == "partial":
            out.append(
                Probe(
                    kind="location_fit",
                    angle="Location — hybrid signal; confirm expectation.",
                    reason="Ask how many onsite days they can hit and their commute reality.",
                    signal_dim="motivation",
                )
            )
        elif match.location_match == "none" and plan.location:
            out.append(
                Probe(
                    kind="location_fit",
                    angle=f"Location gap — candidate {candidate.get('location') or 'elsewhere'}, plan {plan.location}.",
                    reason="Confirm relocation appetite before spending an interview loop on this candidate.",
                    signal_dim="motivation",
                )
            )

    # Motivation probe fallback on phone screen.
    if stage == "phone_screen" and len(out) < 2:
        out.append(
            Probe(
                kind="motivation",
                angle="Motivation — why THIS team, why now?",
                reason='Listen for a specific thing they read about the team, not a generic "growth" answer.',
                signal_dim="motivation",
            )
        )

    # Ownership probe on behavioral.
    if stage == "behavioral":
        out.append(
            Probe(
                kind="ownership_probe",
                angle="Ownership — walk-through of a shipped failure they owned.",
                reason="Look for first-person accountability + a specific prevention step, not blame routing.",
                signal_dim="ownership",
            )
        )

    return out[:MAX_PROBES]


# ─────────── talking points ───────────


def build_talking_points(candidate: dict, plan: QueryPlan) -> list[TalkingPoint]:
    out: list[TalkingPoint] = []
    title = (candidate.get("role") or "").strip()
    loc = (candidate.get("location") or "").strip()

    if title:
        out.append(
            TalkingPoint(
                hook=f"Currently a {title}",
                reference='Anchor for the "why leave / why now" — reference the seniority and stack fit.',
            )
        )
    tags = (candidate.get("tags") or [])[:2]
    if tags:
        out.append(
            TalkingPoint(
                hook=f"Public focus: {' · '.join(tags)}",
                reference="Reference before the technical dive — signals you actually read their profile.",
            )
        )
    overlap = [t for t in (candidate.get("tags") or []) if t.lower() in plan.skills]
    if overlap:
        out.append(
            TalkingPoint(
                hook=f"Direct stack overlap: {', '.join(overlap[:2])}",
                reference="Skip the surface intro on these — go one layer deeper right away.",
            )
        )
    if len(out) < MAX_TALKING and loc:
        out.append(
            TalkingPoint(
                hook=f"Based in {loc}",
                reference="Confirm the office-day expectation without making it awkward.",
            )
        )
    return out[:MAX_TALKING]


# ─────────── question selection ───────────


def pick_questions(
    plan: QueryPlan,
    focus: list[FocusDim],
    stage: Stage,
) -> list[BriefQuestion]:
    bank = [q for q in build_questions(plan) if q.stage == stage]
    focus_keys = {f.key for f in focus}
    weight_by_dim = {f.key: f.priority for f in focus}

    target = 1 if stage == "phone_screen" else (2 if stage == "behavioral" else 3)
    scored: list[tuple[Any, float, bool]] = []
    for q in bank:
        w = weight_by_dim.get(q.signal, 0.0)
        stage_aff = STAGE_AFFINITY[stage].get(q.signal, 0.02)
        diff_fit = 1 - abs(q.difficulty - target) / 4
        priority = w * 0.55 + stage_aff * 0.25 + diff_fit * 0.20
        scored.append((q, priority, q.signal in focus_keys))
    scored.sort(key=lambda x: (0 if x[2] else 1, -x[1]))

    out: list[BriefQuestion] = []
    for q, priority, _ in scored[:MAX_QUESTIONS]:
        out.append(
            BriefQuestion(
                id=q.id,
                prompt=q.prompt,
                followup=q.followups[0] if q.followups else None,
                signal_dim=q.signal,
                difficulty=q.difficulty,
                source=q.source,
                priority=round(priority, 4),
            )
        )
    return out


# ─────────── flags & metrics ───────────


def build_flags(
    plan: QueryPlan,
    candidate: dict,
    match: MatchResult,
    statuses: list[DimStatus],
    interview: dict | None,
) -> list[BriefFlagEntry]:
    out: list[BriefFlagEntry] = []
    if match.score < 60:
        out.append(
            BriefFlagEntry(
                "low_match_score",
                FLAG_LABEL["low_match_score"],
                f"Composite {match.score}/100 — verify the shortlist decision before spending panel time.",
            )
        )
    if len(match.missing_skills) >= 2 and plan.skills:
        skills_str = ", ".join(match.missing_skills[:3])
        out.append(
            BriefFlagEntry(
                "missing_required_skill",
                FLAG_LABEL["missing_required_skill"],
                f"Missing {skills_str} — probe adjacency, not just presence.",
            )
        )
    if plan.seniority and match.seniority_candidate and not match.seniority_match:
        out.append(
            BriefFlagEntry(
                "seniority_mismatch",
                FLAG_LABEL["seniority_mismatch"],
                f"Candidate {match.seniority_candidate}, plan {plan.seniority} — surface scope explicitly.",
            )
        )
    if match.location_match == "partial":
        out.append(
            BriefFlagEntry(
                "location_partial",
                FLAG_LABEL["location_partial"],
                "Hybrid flag on location — confirm before offer stage.",
            )
        )
    open_high = [s for s in statuses if s.state == "open" and s.weight >= 0.15][:2]
    if open_high:
        labels = ", ".join(s.label for s in open_high)
        s_ = "s" if len(open_high) > 1 else ""
        out.append(
            BriefFlagEntry(
                "key_dim_open",
                FLAG_LABEL["key_dim_open"],
                f"High-weight dim{s_} still open: {labels}.",
            )
        )
    if not interview:
        out.append(
            BriefFlagEntry(
                "no_prior_stages",
                FLAG_LABEL["no_prior_stages"],
                "No prior stage on record — this is the first pass.",
            )
        )
    else:
        rated = sum(1 for s in statuses if s.state != "open")
        if rated <= 1 and len(statuses) >= 4:
            out.append(
                BriefFlagEntry(
                    "thin_signal",
                    FLAG_LABEL["thin_signal"],
                    f"Only {rated}/{len(statuses)} dims have signal — treat this like a fresh pass.",
                )
            )
    return out


def _metrics(
    statuses: list[DimStatus],
    focus: list[FocusDim],
    match: MatchResult,
) -> tuple[int, int]:
    total_weight = sum(s.weight for s in statuses) or 1.0
    covered_weight = sum(s.weight for s in statuses if s.state == "covered")
    partial_weight = sum(s.weight for s in statuses if s.state == "partial")
    decision_confidence = round(((covered_weight + partial_weight * 0.5) / total_weight) * 100)
    focus_weight = sum(f.weight for f in focus)
    if match.score < 60:
        score_lever = 0.35
    elif match.score < 75:
        score_lever = 0.20
    else:
        score_lever = 0.10
    criticality_raw = focus_weight * 0.7 + score_lever + (100 - decision_confidence) / 400
    criticality = round(_clamp(criticality_raw, 0.0, 1.0) * 100)
    return criticality, decision_confidence


# ─────────── public entrypoint ───────────


def compose_brief(
    role: dict,
    candidate: dict,
    stage: Stage,
    interview: dict | None = None,
    now: int | None = None,
) -> BriefBundle:
    plan = role["plan"]
    if not isinstance(plan, QueryPlan):
        plan = QueryPlan(
            text=plan.get("text", ""),
            skills=list(plan.get("skills") or []),
            location=plan.get("location"),
            seniority=plan.get("seniority"),
        )
    role_id = str(role.get("id") or "")
    role_name = str(role.get("name") or "Role")
    candidate_id = int(candidate.get("id") or 0)
    candidate_name = str(candidate.get("name") or "Candidate")

    rubric = (
        [RubricDim(**d) if isinstance(d, dict) else d for d in interview["rubric"]]
        if interview and interview.get("rubric")
        else build_rubric(plan)
    )
    match = match_candidate(plan, candidate)
    statuses = analyze_coverage(rubric, interview)
    focus = pick_focus_dims(statuses, stage)
    probes = build_probes(plan, candidate, match, stage)
    talking = build_talking_points(candidate, plan)
    questions = pick_questions(plan, focus, stage)
    do_not_re_cover = [s for s in statuses if s.state == "covered"]
    flags = build_flags(plan, candidate, match, statuses, interview)
    criticality, decision_confidence = _metrics(statuses, focus, match)
    budget = TIME_BUDGET_BY_STAGE[stage]
    focus_minutes = sum(f.minutes for f in focus)

    fn = _first_name(candidate_name)
    parts = [fn]
    if candidate.get("role"):
        parts.append(str(candidate["role"]))
    if candidate.get("location"):
        parts.append(str(candidate["location"]))
    intro = " · ".join(parts)

    rp = (
        f"{plan.seniority} {plan.skills[0] if plan.skills else role_name}"
        if plan.seniority
        else role_name
    )
    headline = f"{STAGE_LABEL[stage]} · {fn} → {rp}"

    saturated = sum(1 for s in statuses if s.state == "covered")
    with_signal = sum(1 for s in statuses if s.state != "open")
    tiles = [
        BriefTile(
            "match", "Composite match", f"{match.score}/100",
            f"{len(match.matched_skills)}/{len(plan.skills)} skills",
        ),
        BriefTile(
            "covered", "Dims with signal", f"{with_signal}/{len(statuses)}",
            f"{saturated} saturated",
        ),
        BriefTile(
            "focus", "Focus minutes", f"{focus_minutes}/{budget}m",
            f"{len(focus)} focus dim" + ("" if len(focus) == 1 else "s"),
        ),
        BriefTile(
            "critic", "Criticality", f"{criticality}/100",
            f"decision {decision_confidence}%",
        ),
    ]

    return BriefBundle(
        version="credicrew.brief.v1",
        role_id=role_id,
        role_name=role_name,
        candidate_id=candidate_id,
        candidate_name=candidate_name,
        stage=stage,
        stage_label=STAGE_LABEL[stage],
        intro=intro,
        headline=headline,
        match=match,
        time_budget_min=budget,
        dim_statuses=statuses,
        focus=focus,
        probes=probes,
        talking_points=talking,
        questions=questions,
        do_not_re_cover=do_not_re_cover,
        flags=flags,
        tiles=tiles,
        criticality=criticality,
        decision_confidence=decision_confidence,
        issued_at=now or 0,
        rubric=rubric,
    )


# ─────────── markdown / dict serialisers ───────────


def to_markdown(brief: BriefBundle) -> str:
    lines: list[str] = []
    lines.append(f"# {brief.headline}")
    lines.append("")
    m = brief.match
    lines.append(
        f"_{brief.intro} · match {m.score if m else '—'}/100 · "
        f"{brief.time_budget_min}m budget · decision {brief.decision_confidence}%_"
    )
    lines.append("")
    lines.append("## Focus this stage")
    if not brief.focus:
        lines.append("_All dims already covered. Use the stage to break ties._")
    else:
        for f in brief.focus:
            lines.append(
                f"- **{f.label}** ({round(f.weight * 100)}% weight · {f.minutes}m) — {f.why_line}"
            )
    lines.append("")
    lines.append("## Signals to probe")
    if not brief.probes:
        lines.append("_No candidate-specific probes surfaced._")
    else:
        for p in brief.probes:
            lines.append(f"- **{PROBE_LABEL[p.kind]}** — {p.angle}")
            lines.append(f"  · {p.reason}")
    lines.append("")
    lines.append("## Questions to ask")
    if not brief.questions:
        lines.append("_No stage-fit questions available for this plan._")
    else:
        for i, q in enumerate(brief.questions, start=1):
            lines.append(
                f"{i}. **{q.prompt}**  \n"
                f"   _Signal: {q.signal_dim} · difficulty {q.difficulty} · from {q.source}_"
            )
            if q.followup:
                lines.append(f"   ↳ {q.followup}")
    lines.append("")
    if brief.do_not_re_cover:
        lines.append("## Skip — already covered")
        for d in brief.do_not_re_cover:
            stages = ", ".join(STAGE_LABEL[s] for s in d.rated_in_stages) or "prior stages"
            lines.append(f"- ~~{d.label}~~ (rated {d.best_rating}/5 in {stages})")
        lines.append("")
    if brief.talking_points:
        lines.append("## Warm-up hooks")
        for t in brief.talking_points:
            lines.append(f"- **{t.hook}** — {t.reference}")
        lines.append("")
    if brief.flags:
        lines.append("## Red flags")
        for f in brief.flags:
            lines.append(f"- **{f.label}** — {f.detail}")
        lines.append("")
    lines.append("---")
    lines.append(
        f"Issued by Credicrew · brief.v1 · role `{brief.role_id}` · candidate `{brief.candidate_id}`"
    )
    return "\n".join(lines)


def _match_as_dict(m: MatchResult) -> dict:
    return {
        "score": m.score,
        "matchedSkills": m.matched_skills,
        "missingSkills": m.missing_skills,
        "seniority": {
            "wanted": m.seniority_wanted,
            "candidate": m.seniority_candidate,
            "match": m.seniority_match,
        },
        "location": {
            "wanted": m.location_wanted,
            "match": m.location_match,
        },
        "factors": [asdict(f) for f in m.factors],
    }


def brief_as_dict(brief: BriefBundle) -> dict:
    """Wire shape for the API — camelCase to match TS engine."""
    return {
        "version": brief.version,
        "roleId": brief.role_id,
        "roleName": brief.role_name,
        "candidateId": brief.candidate_id,
        "candidateName": brief.candidate_name,
        "stage": brief.stage,
        "stageLabel": brief.stage_label,
        "intro": brief.intro,
        "headline": brief.headline,
        "match": _match_as_dict(brief.match) if brief.match else None,
        "timeBudgetMin": brief.time_budget_min,
        "dimStatuses": [
            {
                "key": d.key,
                "label": d.label,
                "description": d.description,
                "weight": d.weight,
                "state": d.state,
                "bestRating": d.best_rating,
                "ratedInStages": d.rated_in_stages,
            }
            for d in brief.dim_statuses
        ],
        "focus": [
            {
                "key": f.key,
                "label": f.label,
                "weight": f.weight,
                "gap": f.gap,
                "affinity": f.affinity,
                "priority": f.priority,
                "minutes": f.minutes,
                "whyLine": f.why_line,
            }
            for f in brief.focus
        ],
        "probes": [
            {
                "kind": p.kind,
                "angle": p.angle,
                "reason": p.reason,
                "signalDim": p.signal_dim,
            }
            for p in brief.probes
        ],
        "talkingPoints": [asdict(t) for t in brief.talking_points],
        "questions": [
            {
                "id": q.id,
                "prompt": q.prompt,
                "followup": q.followup,
                "signalDim": q.signal_dim,
                "difficulty": q.difficulty,
                "source": q.source,
                "priority": q.priority,
            }
            for q in brief.questions
        ],
        "doNotReCover": [
            {
                "key": d.key,
                "label": d.label,
                "description": d.description,
                "weight": d.weight,
                "state": d.state,
                "bestRating": d.best_rating,
                "ratedInStages": d.rated_in_stages,
            }
            for d in brief.do_not_re_cover
        ],
        "flags": [asdict(f) for f in brief.flags],
        "tiles": [asdict(t) for t in brief.tiles],
        "criticality": brief.criticality,
        "decisionConfidence": brief.decision_confidence,
        "issuedAt": brief.issued_at,
        "rubric": [asdict(r) for r in brief.rubric],
    }


def defaults() -> dict:
    return {
        "timeBudgetByStage": dict(TIME_BUDGET_BY_STAGE),
        "coveredRatingFloor": COVERED_RATING_FLOOR,
        "partialMinRating": PARTIAL_MIN_RATING,
        "maxFocusDims": MAX_FOCUS_DIMS,
        "maxQuestions": MAX_QUESTIONS,
        "maxProbes": MAX_PROBES,
        "stageAffinity": {s: dict(v) for s, v in STAGE_AFFINITY.items()},
        "stages": list(STAGES),
        "coverageHex": dict(COVERAGE_HEX),
        "coverageLabel": dict(COVERAGE_LABEL),
        "probeHex": dict(PROBE_HEX),
        "probeLabel": dict(PROBE_LABEL),
        "flagLabel": dict(FLAG_LABEL),
        "flagTone": dict(FLAG_TONE),
    }
