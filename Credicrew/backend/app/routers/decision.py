"""Decision Studio HTTP surface.

Two endpoints:

* `POST /decision/summary` — calibrated ranking + per-candidate verdicts
  + per-dim stats + recommendation tally for a role's interviewed pool.
  Optionally returns a markdown debrief.

* `POST /decision/debrief` — same input shape but returns *only* the
  markdown body. Mostly a convenience for clients that already cached
  the summary.
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.services.decision import (
    CandidateInput,
    _InterviewLite,
    build_debrief,
    build_summary,
    rubric_from_payload,
    stages_from_payload,
    summary_as_dict,
)
from app.services.match import (
    MatchResult,
    QueryPlan,
    match_candidate,
    plan_query,
)

router = APIRouter(prefix="/decision", tags=["decision"])


class _MatchIn(BaseModel):
    score: int
    matched_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)


class _RubricItem(BaseModel):
    key: str
    label: str = ""
    description: str = ""
    weight: float = 0.0
    source: str = "skill"


class _StageItem(BaseModel):
    stage: str
    status: str = "planned"
    scores: list[dict] = Field(default_factory=list)
    signals: list[dict] = Field(default_factory=list)
    notes: str | None = None


class _InterviewIn(BaseModel):
    rubric: list[_RubricItem]
    stages: list[_StageItem]


class _CandidateIn(BaseModel):
    candidate_id: int
    name: str
    role: str | None = None
    location: str | None = None
    tags: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    headline: str | None = None
    interview: _InterviewIn | None = None
    # Override to skip live re-matching
    match: _MatchIn | None = None


class _PlanIn(BaseModel):
    text: str = ""
    skills: list[str] = Field(default_factory=list)
    location: str | None = None
    seniority: str | None = None


class DecisionRequest(BaseModel):
    role_id: str
    role_name: str | None = None
    jd: str | None = None
    plan: _PlanIn | None = None
    candidates: list[_CandidateIn]
    include_debrief: bool = False


def _as_query_plan(req: DecisionRequest) -> QueryPlan:
    if req.jd:
        return plan_query(req.jd)
    if req.plan:
        return QueryPlan(
            text=req.plan.text,
            skills=list(req.plan.skills),
            location=req.plan.location,
            seniority=req.plan.seniority,
        )
    return QueryPlan(text="", skills=[], location=None, seniority=None)


def _as_inputs(req: DecisionRequest, plan: QueryPlan) -> list[CandidateInput]:
    out: list[CandidateInput] = []
    for c in req.candidates:
        if c.match is not None:
            mr = MatchResult(
                score=c.match.score,
                matched_skills=list(c.match.matched_skills),
                missing_skills=list(c.match.missing_skills),
            )
        else:
            mr = match_candidate(plan, {
                "name": c.name,
                "role": c.role or "",
                "location": c.location or "",
                "tags": c.tags,
                "keywords": c.keywords,
                "headline": c.headline or "",
            })
        interview_lite = None
        if c.interview is not None:
            rubric = rubric_from_payload([d.model_dump() for d in c.interview.rubric])
            stages = stages_from_payload(rubric, [s.model_dump() for s in c.interview.stages])
            interview_lite = _InterviewLite(rubric=rubric, stages=stages)
        out.append(CandidateInput(
            candidate_id=c.candidate_id,
            name=c.name,
            role=c.role,
            location=c.location,
            match=mr,
            interview=interview_lite,
        ))
    return out


@router.post("/summary")
def summary(body: DecisionRequest) -> dict:
    plan = _as_query_plan(body)
    inputs = _as_inputs(body, plan)
    s = build_summary(body.role_id, inputs)
    out = summary_as_dict(s)
    if body.include_debrief:
        out["debrief"] = build_debrief(body.role_name or body.role_id, s)
    return out


@router.post("/debrief")
def debrief(body: DecisionRequest) -> dict:
    plan = _as_query_plan(body)
    inputs = _as_inputs(body, plan)
    s = build_summary(body.role_id, inputs)
    return {"markdown": build_debrief(body.role_name or body.role_id, s)}
