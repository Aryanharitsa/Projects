"""Revive HTTP surface.

``POST /revive/summary`` — takes a portfolio (list of roles + a candidate
pool) and returns the silver-medalist reactivation summary used by the
``/revive`` frontend surface: silver entries, ranked opportunities, the
per-candidate and per-role roll-ups, the headline counts and the
markdown brief.

``POST /revive/brief`` — re-renders a markdown brief from a payload.

``GET /revive/defaults`` — exposes the thresholds and formulas the engine
uses so clients can stay in sync.

Accepts both ``camelCase`` (TS-engine style) and ``snake_case`` payloads
via Pydantic aliases.
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from app.services.revive import (
    RECENCY_FLOOR,
    RECENCY_HALF_LIFE_DAYS,
    REVIVE_COMPOSITE_FLOOR,
    REVIVE_MATCH_FLOOR,
    SOURCING_COST_PER_HIRE_USD,
    STALE_DAYS,
    analyze_revive,
    build_brief,
    lift_band,
    summary_to_dict,
)

router = APIRouter(prefix="/revive", tags=["revive"])


class _ShortlistEntry(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="allow")

    candidate_id: int = Field(..., alias="candidateId")
    status: str = "new"
    added_at: Optional[float] = Field(None, alias="addedAt")
    stage_changed_at: Optional[float] = Field(None, alias="stageChangedAt")
    note: Optional[str] = None


class _PlanIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="allow")

    text: Optional[str] = ""
    skills: list[str] = Field(default_factory=list)
    location: Optional[str] = None
    seniority: Optional[str] = None


class _RoleIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="allow")

    id: str
    name: str
    jd: Optional[str] = None
    plan: Optional[_PlanIn] = None
    shortlist: list[_ShortlistEntry] = Field(default_factory=list)


class _CandidateIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="allow")

    id: int
    name: Optional[str] = None
    role: Optional[str] = None
    location: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    headline: Optional[str] = None


class _SummaryRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    roles: list[_RoleIn]
    candidates: list[_CandidateIn]
    include_brief: bool = Field(False, alias="includeBrief")
    now_ms: Optional[int] = Field(None, alias="nowMs")


class _BriefRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    summary: dict[str, Any]


def _role_to_dict(r: _RoleIn) -> dict[str, Any]:
    return {
        "id": r.id,
        "name": r.name,
        "jd": r.jd,
        "plan": (r.plan.model_dump(by_alias=False) if r.plan else None),
        "shortlist": [
            {
                "candidate_id": e.candidate_id,
                "status": e.status,
                "added_at": e.added_at or 0,
                "stage_changed_at": e.stage_changed_at,
                "note": e.note,
            }
            for e in r.shortlist
        ],
    }


def _candidate_to_dict(c: _CandidateIn) -> dict[str, Any]:
    return {
        "id": c.id,
        "name": c.name,
        "role": c.role,
        "location": c.location,
        "tags": c.tags,
        "keywords": c.keywords,
        "headline": c.headline,
    }


@router.post("/summary")
def revive_summary(req: _SummaryRequest) -> dict[str, Any]:
    summary = analyze_revive(
        [_role_to_dict(r) for r in req.roles],
        [_candidate_to_dict(c) for c in req.candidates],
        now_ms=req.now_ms,
    )
    out = summary_to_dict(summary)
    out["band"] = lift_band(summary.revivable_count, len(summary.silver))
    if req.include_brief:
        out["brief"] = build_brief(summary)
    return out


@router.post("/brief")
def revive_brief(req: _BriefRequest) -> dict[str, Any]:
    # We don't need to round-trip a full summary dataclass to render the brief
    # — build_brief reads only the headline fields. Reconstruct the minimum we
    # need from the input dict.
    from app.services.revive import ReviveOpportunity, ReviveSummary, RoleTopPicks, SilverEntry

    s = req.summary

    def _ix(d: dict[str, Any], *keys: str, default: Any = None) -> Any:
        for k in keys:
            if k in d and d[k] is not None:
                return d[k]
        return default

    silver_in = s.get("silver") or []
    silver = [
        SilverEntry(
            candidate_id=int(_ix(x, "candidate_id", "candidateId", default=0)),
            candidate_name=str(_ix(x, "candidate_name", "candidateName", default="")),
            from_role_id=str(_ix(x, "from_role_id", "fromRoleId", default="")),
            from_role_name=str(_ix(x, "from_role_name", "fromRoleName", default="")),
            passed_at_ms=float(_ix(x, "passed_at_ms", "passedAtMs", default=0)),
            days_dormant=int(_ix(x, "days_dormant", "daysDormant", default=0)),
            from_score=int(_ix(x, "from_score", "fromScore", default=0)),
            note=_ix(x, "note"),
        )
        for x in silver_in
    ]

    def _opp(x: dict[str, Any]) -> ReviveOpportunity:
        return ReviveOpportunity(
            candidate_id=int(_ix(x, "candidate_id", "candidateId", default=0)),
            candidate_name=str(_ix(x, "candidate_name", "candidateName", default="")),
            from_role_id=str(_ix(x, "from_role_id", "fromRoleId", default="")),
            from_role_name=str(_ix(x, "from_role_name", "fromRoleName", default="")),
            from_score=int(_ix(x, "from_score", "fromScore", default=0)),
            to_role_id=str(_ix(x, "to_role_id", "toRoleId", default="")),
            to_role_name=str(_ix(x, "to_role_name", "toRoleName", default="")),
            to_score=int(_ix(x, "to_score", "toScore", default=0)),
            delta=int(_ix(x, "delta", default=0)),
            days_dormant=int(_ix(x, "days_dormant", "daysDormant", default=0)),
            recency=float(_ix(x, "recency", default=0.0)),
            reactivation_score=int(_ix(x, "reactivation_score", "reactivationScore", default=0)),
            matched_skills=list(_ix(x, "matched_skills", "matchedSkills", default=[])),
            missing_skills=list(_ix(x, "missing_skills", "missingSkills", default=[])),
            location_match=str(_ix(x, "location_match", "locationMatch", default="none")),
            seniority_match=bool(_ix(x, "seniority_match", "seniorityMatch", default=False)),
            why=list(_ix(x, "why", default=[])),
            stale=bool(_ix(x, "stale", default=False)),
        )

    opportunities = [_opp(x) for x in (s.get("opportunities") or [])]

    per_role_in = s.get("per_role") or []
    per_role = [
        RoleTopPicks(
            role_id=str(_ix(r, "role_id", "roleId", default="")),
            role_name=str(_ix(r, "role_name", "roleName", default="")),
            picks=[_opp(p) for p in (r.get("picks") or [])],
            best_score=int(_ix(r, "best_score", "bestScore", default=0)),
        )
        for r in per_role_in
    ]

    top_pick = None
    tp = s.get("top_pick") or s.get("topPick")
    if tp:
        top_pick = _opp(tp)

    summary = ReviveSummary(
        generated_at=int(_ix(s, "generated_at", "generatedAt", default=0)),
        silver=silver,
        opportunities=opportunities,
        per_candidate=[],
        per_role=per_role,
        revivable_count=int(_ix(s, "revivable_count", "revivableCount", default=0)),
        estimated_cost_saved_usd=int(_ix(s, "estimated_cost_saved_usd", "estimatedCostSavedUsd", default=0)),
        top_pick=top_pick,
        reactivation_histogram=list(_ix(s, "reactivation_histogram", "reactivationHistogram", default=[])),
    )
    return {"brief": build_brief(summary)}


@router.get("/defaults")
def revive_defaults() -> dict[str, Any]:
    return {
        "thresholds": {
            "recency_half_life_days": RECENCY_HALF_LIFE_DAYS,
            "recency_floor": RECENCY_FLOOR,
            "revive_match_floor": REVIVE_MATCH_FLOOR,
            "revive_composite_floor": REVIVE_COMPOSITE_FLOOR,
            "stale_days": STALE_DAYS,
            "sourcing_cost_per_hire_usd": SOURCING_COST_PER_HIRE_USD,
        },
        "scope": {
            "silver_status": "passed",
            "excludes": "candidate is already on the target role's shortlist (any status)",
        },
        "formulas": {
            "recency": "2 ^ (−daysDormant / RECENCY_HALF_LIFE_DAYS)",
            "reactivation_score": "matchScore × (RECENCY_FLOOR + (1 − RECENCY_FLOOR) × recency)",
            "estimated_cost_saved_usd": "|distinct_revivable_candidates| × SOURCING_COST_PER_HIRE_USD",
        },
    }
