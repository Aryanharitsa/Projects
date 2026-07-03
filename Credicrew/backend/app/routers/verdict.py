"""API surface for Verdict — the rejection ontology + JD-refinement advisor.

`POST /verdict/summary`  — analyse one role's passed pool
`POST /verdict/portfolio` — analyse multiple roles and roll up
`GET  /verdict/defaults`  — expose physics constants for the UI to display

Physics is imported from `app.services.verdict` which mirrors
`frontend/src/lib/verdict.ts`, so a role posted to either endpoint gets
the same mix, top reason, health verdict, and suggestions as the browser.
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.services.match import QueryPlan
from app.services.verdict import (
    CATEGORIES,
    CATEGORY_HEX,
    CATEGORY_LABEL,
    CULTURE_SCORE_FLOOR,
    CULTURE_SKILL_FLOOR,
    H_HEALTHY_CULTURE,
    H_OVERFISHED,
    H_SPEC_LEAK,
    MIN_PLAN_SKILLS_FOR_SKILLS_SHORT,
    R_CULTURE_MIN_SHARE,
    R_LOCATION_MIN_SHARE,
    R_MISSING_SKILL_MIN_N,
    R_SENIORITY_OVER_MIN_N,
    R_SENIORITY_OVER_MIN_SHARE,
    R_SENIORITY_UNDER_MIN_N,
    R_SENIORITY_UNDER_MIN_SHARE,
    R_SKILLS_SHORT_MIN_SHARE,
    SENIORITY_LADDER,
    SKILLS_SHORT_FLOOR,
    analyze_portfolio,
    analyze_role,
    portfolio_to_dict,
    role_to_dict,
)

router = APIRouter(prefix="/verdict", tags=["verdict"])


class PlanIn(BaseModel):
    text: str = ""
    skills: list[str] = Field(default_factory=list)
    location: str | None = None
    seniority: str | None = None


class CandidateIn(BaseModel):
    id: int
    name: str
    role: str | None = None
    location: str | None = None
    headline: str | None = None
    tags: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)


class RoleIn(BaseModel):
    role_id: str
    role_name: str
    plan: PlanIn
    passed_candidates: list[CandidateIn] = Field(default_factory=list)
    total_shortlist_size: int = 0


class RoleRequest(BaseModel):
    role: RoleIn


class PortfolioRequest(BaseModel):
    roles: list[RoleIn]


def _plan(p: PlanIn) -> QueryPlan:
    return QueryPlan(
        text=p.text, skills=list(p.skills), location=p.location, seniority=p.seniority,
    )


@router.post("/summary")
def verdict_summary(body: RoleRequest) -> dict:
    r = analyze_role(
        role_id=body.role.role_id,
        role_name=body.role.role_name,
        plan=_plan(body.role.plan),
        passed_candidates=[c.model_dump() for c in body.role.passed_candidates],
        total_shortlist_size=body.role.total_shortlist_size,
    )
    return role_to_dict(r)


@router.post("/portfolio")
def verdict_portfolio(body: PortfolioRequest) -> dict:
    rvs = [
        analyze_role(
            role_id=r.role_id,
            role_name=r.role_name,
            plan=_plan(r.plan),
            passed_candidates=[c.model_dump() for c in r.passed_candidates],
            total_shortlist_size=r.total_shortlist_size,
        )
        for r in body.roles
    ]
    return portfolio_to_dict(analyze_portfolio(rvs))


@router.get("/defaults")
def verdict_defaults() -> dict:
    return {
        "categories": list(CATEGORIES),
        "category_label": CATEGORY_LABEL,
        "category_hex": CATEGORY_HEX,
        "seniority_ladder": list(SENIORITY_LADDER),
        "physics": {
            "culture_score_floor": CULTURE_SCORE_FLOOR,
            "culture_skill_floor": CULTURE_SKILL_FLOOR,
            "skills_short_floor": SKILLS_SHORT_FLOOR,
            "min_plan_skills_for_skills_short": MIN_PLAN_SKILLS_FOR_SKILLS_SHORT,
        },
        "refinement_thresholds": {
            "r_seniority_over_min_n": R_SENIORITY_OVER_MIN_N,
            "r_seniority_over_min_share": R_SENIORITY_OVER_MIN_SHARE,
            "r_seniority_under_min_n": R_SENIORITY_UNDER_MIN_N,
            "r_seniority_under_min_share": R_SENIORITY_UNDER_MIN_SHARE,
            "r_location_min_share": R_LOCATION_MIN_SHARE,
            "r_skills_short_min_share": R_SKILLS_SHORT_MIN_SHARE,
            "r_missing_skill_min_n": R_MISSING_SKILL_MIN_N,
            "r_culture_min_share": R_CULTURE_MIN_SHARE,
        },
        "health_thresholds": {
            "h_healthy_culture": H_HEALTHY_CULTURE,
            "h_spec_leak": H_SPEC_LEAK,
            "h_overfished": H_OVERFISHED,
        },
    }
