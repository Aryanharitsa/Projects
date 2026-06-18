"""Crosswind HTTP surface.

``POST /crosswind/summary`` — takes a portfolio (list of roles + a
candidate pool) and returns the cross-role routing summary used by the
``/crosswind`` frontend surface: cells, moves, magnets, lonely roles,
per-role rollup, score histogram, and totals.

``POST /crosswind/brief`` — re-renders a markdown brief from a payload.

``GET /crosswind/defaults`` — exposes the thresholds the engine uses so
clients can stay in sync.

Accepts both ``camelCase`` (TS-engine style) and ``snake_case`` payloads
via Pydantic aliases.
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from app.services.crosswind import (
    MAGNET_ROLES,
    MISPLACE_THRESHOLD,
    SOLID_FLOOR,
    STRONG_FLOOR,
    TRANSPLANT_FLOOR,
    analyze_crosswind,
    build_brief,
    lift_band,
    summary_to_dict,
)

router = APIRouter(prefix="/crosswind", tags=["crosswind"])


class _ShortlistEntry(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="allow")

    candidate_id: int = Field(..., alias="candidateId")
    status: str = "new"
    added_at: Optional[float] = Field(None, alias="addedAt")
    stage_changed_at: Optional[float] = Field(None, alias="stageChangedAt")


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
def crosswind_summary(req: _SummaryRequest) -> dict[str, Any]:
    summary = analyze_crosswind(
        [_role_to_dict(r) for r in req.roles],
        [_candidate_to_dict(c) for c in req.candidates],
        now_ms=req.now_ms,
    )
    out = summary_to_dict(summary)
    out["band"] = lift_band(summary.lift_total, len(summary.moves))
    if req.include_brief:
        out["brief"] = build_brief(summary)
    return out


@router.post("/brief")
def crosswind_brief(req: _BriefRequest) -> dict[str, Any]:
    # Rebuild a minimal CrosswindSummary from a dict so we can reuse build_brief.
    from app.services.crosswind import (
        CrosswindSummary,
        LonelyRole,
        LonelyTransplant,
        MagnetHit,
        PerRoleRollup,
        RoutingMove,
        TalentMagnet,
    )
    s = req.summary

    def _opt(d, *keys, default=None):
        for k in keys:
            if k in d and d[k] is not None:
                return d[k]
        return default

    moves = [
        RoutingMove(
            candidate_id=int(m.get("candidate_id") or m.get("candidateId") or 0),
            candidate_name=m.get("candidate_name") or m.get("candidateName") or "",
            from_role_id=m.get("from_role_id") or m.get("fromRoleId") or "",
            from_role_name=m.get("from_role_name") or m.get("fromRoleName") or "",
            from_score=int(m.get("from_score") or m.get("fromScore") or 0),
            to_role_id=m.get("to_role_id") or m.get("toRoleId") or "",
            to_role_name=m.get("to_role_name") or m.get("toRoleName") or "",
            to_score=int(m.get("to_score") or m.get("toScore") or 0),
            delta=int(m.get("delta") or 0),
            why=list(m.get("why") or []),
            status=m.get("status"),
        )
        for m in (s.get("moves") or [])
    ]
    magnets = [
        TalentMagnet(
            candidate_id=int(t.get("candidate_id") or t.get("candidateId") or 0),
            candidate_name=t.get("candidate_name") or t.get("candidateName") or "",
            home_role_id=t.get("home_role_id") or t.get("homeRoleId"),
            home_role_name=t.get("home_role_name") or t.get("homeRoleName"),
            hits=[
                MagnetHit(
                    role_id=h.get("role_id") or h.get("roleId") or "",
                    role_name=h.get("role_name") or h.get("roleName") or "",
                    score=int(h.get("score") or 0),
                    is_home=bool(h.get("is_home") or h.get("isHome") or False),
                )
                for h in (t.get("hits") or [])
            ],
            top_score=int(t.get("top_score") or t.get("topScore") or 0),
        )
        for t in (s.get("magnets") or [])
    ]
    lonely = [
        LonelyRole(
            role_id=l.get("role_id") or l.get("roleId") or "",
            role_name=l.get("role_name") or l.get("roleName") or "",
            own_best=int(l.get("own_best") or l.get("ownBest") or 0),
            own_median=int(l.get("own_median") or l.get("ownMedian") or 0),
            candidate_count=int(l.get("candidate_count") or l.get("candidateCount") or 0),
            transplants=[
                LonelyTransplant(
                    candidate_id=int(t.get("candidate_id") or t.get("candidateId") or 0),
                    candidate_name=t.get("candidate_name") or t.get("candidateName") or "",
                    from_role_id=t.get("from_role_id") or t.get("fromRoleId") or "",
                    from_role_name=t.get("from_role_name") or t.get("fromRoleName") or "",
                    score=int(t.get("score") or 0),
                    delta=int(t.get("delta") or 0),
                    status=t.get("status"),
                )
                for t in (l.get("transplants") or [])
            ],
        )
        for l in (s.get("lonely") or [])
    ]
    summary = CrosswindSummary(
        generated_at=int(s.get("generated_at") or s.get("generatedAt") or 0),
        role_count=int(s.get("role_count") or s.get("roleCount") or 0),
        candidate_count=int(s.get("candidate_count") or s.get("candidateCount") or 0),
        cell_count=int(s.get("cell_count") or s.get("cellCount") or 0),
        cells=[],
        current_total=int(s.get("current_total") or s.get("currentTotal") or 0),
        optimal_total=int(s.get("optimal_total") or s.get("optimalTotal") or 0),
        lift_total=int(s.get("lift_total") or s.get("liftTotal") or 0),
        lift_avg_per_move=int(s.get("lift_avg_per_move") or s.get("liftAvgPerMove") or 0),
        moves=moves,
        magnets=magnets,
        lonely=lonely,
        per_role=[],
        score_histogram=list(s.get("score_histogram") or s.get("scoreHistogram") or []),
    )
    return {"brief": build_brief(summary)}


@router.get("/defaults")
def crosswind_defaults() -> dict[str, Any]:
    return {
        "thresholds": {
            "strong_floor": STRONG_FLOOR,
            "solid_floor": SOLID_FLOOR,
            "misplace_threshold": MISPLACE_THRESHOLD,
            "magnet_roles": MAGNET_ROLES,
            "transplant_floor": TRANSPLANT_FLOOR,
        },
        "frozen_statuses": ["passed", "offer"],
        "formulas": {
            "lift_total": "Σ(best_alternative_score − current_score) across active candidates",
            "magnet": f"score ≥ {STRONG_FLOOR} in ≥ {MAGNET_ROLES} distinct roles",
            "lonely": f"role with no own match ≥ {STRONG_FLOOR}, but a transplant ≥ {TRANSPLANT_FLOOR}",
            "move": f"home_score < best_alternative_score by ≥ {MISPLACE_THRESHOLD} pts",
        },
        "weights": {"skill": 0.55, "loc": 0.15, "sen": 0.20, "base": 0.10},
    }
