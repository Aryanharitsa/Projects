"""Rejection Ontology & JD-Refinement Advisor.

Mirror of `frontend/src/lib/verdict.ts` — every physics constant here is
duplicated in TypeScript so the API and the browser produce byte-identical
mixes and refinement suggestions.

Categorises every `passed` shortlist entry into a seven-cell ontology in
strict priority order, rolls the mix up into a `signalHealth` verdict,
and derives deterministic JD-refinement suggestions with quantified
`impact` and `confidence`.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any

from app.services.match import QueryPlan, match_candidate

# Priority-ordered category list. Order matters: the first bucket a
# passed candidate qualifies for wins.
CATEGORIES: tuple[str, ...] = (
    "culture_signal",
    "location_gap",
    "seniority_over",
    "seniority_under",
    "skills_short",
    "mixed_signal",
    "other",
)

CATEGORY_LABEL: dict[str, str] = {
    "culture_signal": "Culture signal",
    "location_gap": "Location gap",
    "seniority_over": "Over-qualified",
    "seniority_under": "Under-qualified",
    "skills_short": "Skills short",
    "mixed_signal": "Mixed signal",
    "other": "Other",
}

CATEGORY_HEX: dict[str, str] = {
    "culture_signal": "#10b981",
    "location_gap": "#0ea5e9",
    "seniority_over": "#a855f7",
    "seniority_under": "#f59e0b",
    "skills_short": "#f43f5e",
    "mixed_signal": "#94a3b8",
    "other": "#64748b",
}

SENIORITY_LADDER: tuple[str, ...] = (
    "intern", "junior", "mid", "senior", "staff", "principal",
)

SENIORITY_TIER: dict[str, int] = {
    "intern": 0, "junior": 1, "mid": 2,
    "senior": 3, "lead": 3,
    "staff": 4, "principal": 5,
}

# Physics — mirrored with verdict.ts.
CULTURE_SCORE_FLOOR = 65
CULTURE_SKILL_FLOOR = 0.6
SKILLS_SHORT_FLOOR = 0.4
MIN_PLAN_SKILLS_FOR_SKILLS_SHORT = 3
SENIORITY_OVER_GAP = 1

R_SENIORITY_OVER_MIN_N = 3
R_SENIORITY_OVER_MIN_SHARE = 0.2
R_SENIORITY_UNDER_MIN_N = 3
R_SENIORITY_UNDER_MIN_SHARE = 0.3
R_LOCATION_MIN_SHARE = 0.25
R_SKILLS_SHORT_MIN_SHARE = 0.4
R_MISSING_SKILL_MIN_N = 3
R_CULTURE_MIN_SHARE = 0.4

H_HEALTHY_CULTURE = 0.4
H_SPEC_LEAK = 0.5
H_OVERFISHED = 0.5


@dataclass
class MixCellEntry:
    candidate_id: int
    name: str
    category: str
    score: int
    matched_skills: list[str]
    missing_skills: list[str]
    seniority_wanted: str | None
    seniority_candidate: str | None
    seniority_match: bool
    location_match: str
    primary_driver: str


@dataclass
class MixCell:
    category: str
    count: int
    share: float
    entries: list[MixCellEntry] = field(default_factory=list)


@dataclass
class Suggestion:
    id: str
    category: str
    action: str
    basis: str
    impact: int
    confidence: int
    plan_delta_kind: str | None = None
    plan_delta_value: str | None = None


@dataclass
class RoleVerdict:
    role_id: str
    role_name: str
    plan_summary: dict[str, Any]
    total_passed: int
    total_considered: int
    pass_share: float
    cells: list[MixCell]
    top_reason: str | None
    signal_health: str
    funnel_waste: int
    band_distribution: dict[str, int]
    common_missing_skills: list[dict[str, Any]]
    suggestions: list[Suggestion]


@dataclass
class VerdictPortfolio:
    roles: list[RoleVerdict]
    total_passed: int
    total_considered: int
    pass_share: float
    aggregated_cells: list[MixCell]
    signal_health: str
    funnel_waste: int
    top_reason: str | None
    top_suggestions: list[Suggestion]


def tier_of(sen: str | None) -> int | None:
    if not sen:
        return None
    return SENIORITY_TIER.get(sen)


def _band_of(score: int) -> str:
    if score >= 80:
        return "strong"
    if score >= 60:
        return "solid"
    return "weak"


def _pick_category(
    plan: QueryPlan,
    m,
    wanted_tier: int | None,
    cand_tier: int | None,
) -> str:
    skill_cov = 1.0 if not plan.skills else len(m.matched_skills) / len(plan.skills)

    if (
        m.score >= CULTURE_SCORE_FLOOR
        and skill_cov >= CULTURE_SKILL_FLOOR
        and m.seniority_match
        and m.location_match in ("full", "partial")
    ):
        return "culture_signal"

    if plan.location and plan.location != "remote" and m.location_match == "none":
        return "location_gap"

    if (
        wanted_tier is not None
        and cand_tier is not None
        and cand_tier > wanted_tier + SENIORITY_OVER_GAP
    ):
        return "seniority_over"

    if (
        wanted_tier is not None
        and cand_tier is not None
        and cand_tier < wanted_tier
    ):
        return "seniority_under"

    if (
        len(plan.skills) >= MIN_PLAN_SKILLS_FOR_SKILLS_SHORT
        and skill_cov < SKILLS_SHORT_FLOOR
    ):
        return "skills_short"

    if 40 <= m.score < CULTURE_SCORE_FLOOR:
        return "mixed_signal"

    return "other"


def _driver_for(cat: str, m, wanted_sen: str | None) -> str:
    if cat == "culture_signal":
        return f"Composite {m.score} · panel signal"
    if cat == "location_gap":
        return f"Location · {m.location_wanted or 'unknown'}"
    if cat == "seniority_over":
        return f"{m.seniority_candidate or 'senior'} → wanted {wanted_sen or 'lower'}"
    if cat == "seniority_under":
        return f"{m.seniority_candidate or 'junior'} → wanted {wanted_sen or 'higher'}"
    if cat == "skills_short":
        miss = ", ".join(m.missing_skills[:2])
        return f"Missing {miss}" if miss else "Skills coverage low"
    if cat == "mixed_signal":
        return f"Composite {m.score} · nothing dominant"
    return "Unclassified"


def _compute_health(counts_by_cat: dict[str, float], total_passed: int) -> str:
    if total_passed < 3:
        return "unknown"
    spec = (
        counts_by_cat.get("location_gap", 0.0)
        + counts_by_cat.get("seniority_over", 0.0)
        + counts_by_cat.get("seniority_under", 0.0)
    )
    if counts_by_cat.get("culture_signal", 0.0) >= H_HEALTHY_CULTURE:
        return "healthy"
    if spec >= H_SPEC_LEAK:
        return "spec_leak"
    if counts_by_cat.get("skills_short", 0.0) >= H_OVERFISHED:
        return "overfished"
    return "mixed"


def _suggestions_for(
    role_id: str,
    cells_by_cat: dict[str, MixCell],
    total_passed: int,
    plan_skills: list[str],
    plan_location: str | None,
    plan_seniority: str | None,
    missing_skill_counts: list[dict[str, Any]],
) -> list[Suggestion]:
    out: list[Suggestion] = []

    o = cells_by_cat.get("seniority_over")
    if (
        o
        and o.count >= R_SENIORITY_OVER_MIN_N
        and o.share >= R_SENIORITY_OVER_MIN_SHARE
        and plan_seniority
    ):
        wanted_idx = tier_of(plan_seniority) or 3
        next_tier = SENIORITY_LADDER[min(len(SENIORITY_LADDER) - 1, wanted_idx + 1)]
        out.append(Suggestion(
            id=f"{role_id}:sen_over",
            category="seniority_over",
            action=f"Split into {plan_seniority} + {next_tier} variants",
            basis=(
                f"{o.count} candidates ({round(o.share * 100)}%) passed for "
                f"over-qualification alone — the {next_tier} band is landing "
                "in your funnel unclaimed."
            ),
            impact=o.count,
            confidence=min(95, 40 + o.count * 8),
            plan_delta_kind="widen_seniority",
            plan_delta_value=next_tier,
        ))

    u = cells_by_cat.get("seniority_under")
    if (
        u
        and u.count >= R_SENIORITY_UNDER_MIN_N
        and u.share >= R_SENIORITY_UNDER_MIN_SHARE
    ):
        out.append(Suggestion(
            id=f"{role_id}:sen_under",
            category="seniority_under",
            action="Tighten the minimum-seniority bar in the JD copy",
            basis=(
                f"{u.count} under-tier candidates ({round(u.share * 100)}%) "
                "entered your pipeline — the spec isn't loud enough about the floor."
            ),
            impact=u.count,
            confidence=min(95, 40 + u.count * 8),
            plan_delta_kind="narrow_seniority" if plan_seniority else None,
            plan_delta_value=plan_seniority,
        ))

    l = cells_by_cat.get("location_gap")
    if (
        l
        and l.count >= 2
        and l.share >= R_LOCATION_MIN_SHARE
        and plan_location
    ):
        out.append(Suggestion(
            id=f"{role_id}:loc",
            category="location_gap",
            action="Open the role to remote or hybrid",
            basis=(
                f"{l.count} candidates ({round(l.share * 100)}%) were passed "
                f"on location alone — the {plan_location} constraint is the "
                "single reason they didn't make it."
            ),
            impact=l.count,
            confidence=min(90, 35 + l.count * 10),
            plan_delta_kind="add_location",
            plan_delta_value="remote",
        ))

    s = cells_by_cat.get("skills_short")
    if (
        s
        and s.share >= R_SKILLS_SHORT_MIN_SHARE
        and len(plan_skills) >= MIN_PLAN_SKILLS_FOR_SKILLS_SHORT
        and missing_skill_counts
    ):
        top = missing_skill_counts[0]
        if top["count"] >= R_MISSING_SKILL_MIN_N and top["skill"] in plan_skills:
            out.append(Suggestion(
                id=f"{role_id}:skill:{top['skill']}",
                category="skills_short",
                action=f'Move "{top["skill"]}" from must-have to nice-to-have',
                basis=(
                    f"{top['count']} of the passed pool would have cleared "
                    f"the bar without \"{top['skill']}\" — it's the single "
                    "largest disqualifier in your reject pile."
                ),
                impact=top["count"],
                confidence=min(90, 30 + top["count"] * 8),
                plan_delta_kind="demote_skill",
                plan_delta_value=top["skill"],
            ))

    c = cells_by_cat.get("culture_signal")
    if c and c.share >= R_CULTURE_MIN_SHARE and total_passed >= 4:
        out.append(Suggestion(
            id=f"{role_id}:culture",
            category="culture_signal",
            action="Advisory — spec is well-tuned; panel is doing the signal work",
            basis=(
                f"{c.count} of {total_passed} passed candidates cleared the "
                "spec but the panel said no anyway — that's the healthy pattern. "
                "Leave the JD alone; focus tuning on the interview loop instead."
            ),
            impact=0,
            confidence=min(90, 40 + c.count * 5),
        ))

    out.sort(key=lambda x: -(x.impact * x.confidence))
    return out


def analyze_role(
    *,
    role_id: str,
    role_name: str,
    plan: QueryPlan,
    passed_candidates: list[dict[str, Any]],
    total_shortlist_size: int,
) -> RoleVerdict:
    wanted_tier = tier_of(plan.seniority)

    entries: list[MixCellEntry] = []
    buckets: dict[str, list[MixCellEntry]] = {c: [] for c in CATEGORIES}

    for c in passed_candidates:
        m = match_candidate(plan, c)
        cand_tier = tier_of(m.seniority_candidate)
        cat = _pick_category(plan, m, wanted_tier, cand_tier)
        entry = MixCellEntry(
            candidate_id=c.get("id"),
            name=c.get("name") or "",
            category=cat,
            score=m.score,
            matched_skills=m.matched_skills,
            missing_skills=m.missing_skills,
            seniority_wanted=m.seniority_wanted,
            seniority_candidate=m.seniority_candidate,
            seniority_match=m.seniority_match,
            location_match=m.location_match,
            primary_driver=_driver_for(cat, m, plan.seniority),
        )
        entries.append(entry)
        buckets[cat].append(entry)

    total_passed = len(entries)

    cells_by_cat: dict[str, MixCell] = {}
    cells: list[MixCell] = []
    for cat in CATEGORIES:
        arr = buckets[cat]
        cell = MixCell(
            category=cat,
            count=len(arr),
            share=(len(arr) / total_passed) if total_passed else 0.0,
            entries=sorted(arr, key=lambda x: -x.score)[:8],
        )
        cells_by_cat[cat] = cell
        if arr:
            cells.append(cell)

    cells.sort(key=lambda c: (-c.count, CATEGORIES.index(c.category)))

    # missing-skill leaderboard
    miss_counter: dict[str, int] = {}
    for e in entries:
        for s in e.missing_skills:
            miss_counter[s] = miss_counter.get(s, 0) + 1
    common_missing = [
        {"skill": s, "count": n}
        for s, n in sorted(miss_counter.items(), key=lambda kv: (-kv[1], kv[0]))
    ][:5]

    band = {"strong": 0, "solid": 0, "weak": 0}
    waste_sum = 0
    for e in entries:
        band[_band_of(e.score)] += 1
        waste_sum += e.score
    funnel_waste = round(waste_sum / total_passed) if total_passed else 0

    share_by_cat = {cat: cells_by_cat[cat].share for cat in CATEGORIES}
    health = _compute_health(share_by_cat, total_passed)

    top_reason = cells[0].category if cells else None

    suggestions = _suggestions_for(
        role_id=role_id,
        cells_by_cat=cells_by_cat,
        total_passed=total_passed,
        plan_skills=plan.skills,
        plan_location=plan.location,
        plan_seniority=plan.seniority,
        missing_skill_counts=common_missing,
    )

    return RoleVerdict(
        role_id=role_id,
        role_name=role_name,
        plan_summary={
            "skills": plan.skills,
            "location": plan.location,
            "seniority": plan.seniority,
        },
        total_passed=total_passed,
        total_considered=total_shortlist_size,
        pass_share=(total_passed / total_shortlist_size) if total_shortlist_size else 0.0,
        cells=cells,
        top_reason=top_reason,
        signal_health=health,
        funnel_waste=funnel_waste,
        band_distribution=band,
        common_missing_skills=common_missing,
        suggestions=suggestions,
    )


def analyze_portfolio(roles: list[RoleVerdict]) -> VerdictPortfolio:
    total_passed = sum(r.total_passed for r in roles)
    total_considered = sum(r.total_considered for r in roles)

    counts: dict[str, int] = {c: 0 for c in CATEGORIES}
    waste_num = 0
    for r in roles:
        for c in r.cells:
            counts[c.category] += c.count
        waste_num += r.funnel_waste * r.total_passed

    aggregated: list[MixCell] = []
    for cat in CATEGORIES:
        if counts[cat] > 0:
            aggregated.append(MixCell(
                category=cat,
                count=counts[cat],
                share=(counts[cat] / total_passed) if total_passed else 0.0,
                entries=[],
            ))
    aggregated.sort(key=lambda c: (-c.count, CATEGORIES.index(c.category)))

    share_by_cat = {
        cat: (counts[cat] / total_passed) if total_passed else 0.0
        for cat in CATEGORIES
    }
    health = _compute_health(share_by_cat, total_passed)
    top_reason = aggregated[0].category if aggregated else None
    funnel_waste = round(waste_num / total_passed) if total_passed else 0

    bag: list[Suggestion] = [s for r in roles for s in r.suggestions]
    bag.sort(key=lambda x: -(x.impact * x.confidence))
    top_suggestions = bag[:3]

    return VerdictPortfolio(
        roles=roles,
        total_passed=total_passed,
        total_considered=total_considered,
        pass_share=(total_passed / total_considered) if total_considered else 0.0,
        aggregated_cells=aggregated,
        signal_health=health,
        funnel_waste=funnel_waste,
        top_reason=top_reason,
        top_suggestions=top_suggestions,
    )


def cell_to_dict(c: MixCell) -> dict[str, Any]:
    return {
        "category": c.category,
        "count": c.count,
        "share": c.share,
        "entries": [asdict(e) for e in c.entries],
    }


def role_to_dict(r: RoleVerdict) -> dict[str, Any]:
    return {
        "role_id": r.role_id,
        "role_name": r.role_name,
        "plan_summary": r.plan_summary,
        "total_passed": r.total_passed,
        "total_considered": r.total_considered,
        "pass_share": r.pass_share,
        "cells": [cell_to_dict(c) for c in r.cells],
        "top_reason": r.top_reason,
        "signal_health": r.signal_health,
        "funnel_waste": r.funnel_waste,
        "band_distribution": r.band_distribution,
        "common_missing_skills": r.common_missing_skills,
        "suggestions": [asdict(s) for s in r.suggestions],
    }


def portfolio_to_dict(p: VerdictPortfolio) -> dict[str, Any]:
    return {
        "roles": [role_to_dict(r) for r in p.roles],
        "total_passed": p.total_passed,
        "total_considered": p.total_considered,
        "pass_share": p.pass_share,
        "aggregated_cells": [cell_to_dict(c) for c in p.aggregated_cells],
        "signal_health": p.signal_health,
        "funnel_waste": p.funnel_waste,
        "top_reason": p.top_reason,
        "top_suggestions": [asdict(s) for s in p.top_suggestions],
    }
