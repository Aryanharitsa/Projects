"""API surface for Reference — the Structured Reference-Check Composer.

`POST /reference/compose`   — {role, candidate, interview?} → ReferenceBundle
`POST /reference/score`     — {bundle, responses} → ReferenceReport
`POST /reference/markdown`  — same input as compose → {markdown: "..."}
`GET  /reference/defaults`  — physics constants + palettes for the UI

Byte-for-byte parity with `frontend/src/lib/reference.ts`.
"""
from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from app.services.match import QueryPlan
from app.services.reference import (
    ResponseAnswer,
    bundle_as_dict,
    compose_bundle,
    defaults as reference_defaults,
    report_as_dict,
    score_responses,
    to_markdown,
)

router = APIRouter(prefix="/reference", tags=["reference"])


class PlanIn(BaseModel):
    text: str = ""
    skills: list[str] = Field(default_factory=list)
    location: str | None = None
    seniority: str | None = None


class RoleIn(BaseModel):
    id: str = ""
    name: str = "Role"
    plan: PlanIn


class CandidateIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    id: int
    name: str
    role: str | None = None
    location: str | None = None
    headline: str | None = None
    tags: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)


class ComposeRequest(BaseModel):
    role: RoleIn
    candidate: CandidateIn
    interview: dict[str, Any] | None = None


AnswerVerdictIn = Literal["corroborated", "concerned", "contradicted", "no_signal", "pending"]


class ResponseIn(BaseModel):
    slotId: str
    questionId: str
    verdict: AnswerVerdictIn
    note: str | None = None


class ScoreRequest(BaseModel):
    bundle: dict[str, Any]
    responses: list[ResponseIn] = Field(default_factory=list)


def _to_role_candidate(req: ComposeRequest) -> tuple[dict, dict]:
    role_dict = {
        "id": req.role.id,
        "name": req.role.name,
        "plan": QueryPlan(
            text=req.role.plan.text,
            skills=list(req.role.plan.skills),
            location=req.role.plan.location,
            seniority=req.role.plan.seniority,
        ),
    }
    return role_dict, req.candidate.model_dump()


@router.post("/compose")
def compose(req: ComposeRequest) -> dict:
    role_dict, candidate_dict = _to_role_candidate(req)
    bundle = compose_bundle(role=role_dict, candidate=candidate_dict, interview=req.interview)
    return bundle_as_dict(bundle)


@router.post("/markdown")
def markdown(req: ComposeRequest) -> dict:
    role_dict, candidate_dict = _to_role_candidate(req)
    bundle = compose_bundle(role=role_dict, candidate=candidate_dict, interview=req.interview)
    return {
        "roleId": bundle.role_id,
        "candidateId": bundle.candidate_id,
        "markdown": to_markdown(bundle),
    }


@router.post("/score")
def score(req: ScoreRequest) -> dict:
    # Hydrate a bundle dataclass from the client-shipped dict.
    from app.services.reference import (
        Claim,
        ReferenceBundle,
        ReferenceSlot,
        RefQuestion,
        RedFlag,
    )

    b = req.bundle or {}
    slots = []
    for s in b.get("slots", []):
        questions = [
            RefQuestion(
                id=q.get("id"), text=q.get("text"), kind=q.get("kind"),
                priority=float(q.get("priority", 0.0)),
                minutes=float(q.get("minutes", 0.0)),
                linked_claim_id=q.get("linkedClaimId"),
                linked_flag_dim=q.get("linkedFlagDim"),
                hint=q.get("hint"),
            )
            for q in s.get("questions", [])
        ]
        slots.append(ReferenceSlot(
            slot_id=s.get("slotId"), kind=s.get("kind"), label=s.get("label"),
            minutes=int(s.get("minutes", 0)),
            questions=questions,
            intro=s.get("intro", ""),
            focus=list(s.get("focus", [])),
        ))
    claims = [
        Claim(id=c.get("id"), kind=c.get("kind"), text=c.get("text"),
              weight=float(c.get("weight", 0.0)), source=c.get("source", ""))
        for c in b.get("claims", [])
    ]
    flags = [
        RedFlag(
            dim=f.get("dim"), dim_label=f.get("dimLabel"),
            latest_rating=f.get("latestRating"),
            stage=f.get("stage"),
            severity=f.get("severity"),
            weight=float(f.get("weight", 0.0)),
        )
        for f in b.get("redFlags", [])
    ]
    bundle = ReferenceBundle(
        bundle_version=b.get("bundleVersion", "credicrew.reference.v1"),
        role_id=b.get("roleId", ""),
        role_name=b.get("roleName", "Role"),
        candidate_id=int(b.get("candidateId", 0)),
        candidate_name=b.get("candidateName", "Candidate"),
        seniority_tier=b.get("seniorityTier", "mid"),
        slots=slots,
        claims=claims,
        red_flags=flags,
        interview_composite=b.get("interviewComposite"),
        total_minutes=int(b.get("totalMinutes", 0)),
        total_questions=int(b.get("totalQuestions", 0)),
        corpus_hash=b.get("corpusHash", ""),
        headline=b.get("headline", ""),
    )

    answers = [
        ResponseAnswer(
            slot_id=r.slotId, question_id=r.questionId,
            verdict=r.verdict, note=r.note,
        )
        for r in req.responses
    ]
    report = score_responses(bundle, answers)
    return report_as_dict(report)


@router.get("/defaults")
def get_defaults() -> dict:
    return reference_defaults()
