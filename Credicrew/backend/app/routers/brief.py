"""API surface for Brief — the Interviewer Handoff Composer.

`POST /brief/compose`   — {role, candidate, stage, interview?} → BriefBundle
`POST /brief/markdown`  — same input → {markdown: "..."}
`GET  /brief/defaults`  — physics constants + palettes for the UI to display

Byte-for-byte parity with `frontend/src/lib/brief.ts`.
"""
from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from app.services.brief import (
    brief_as_dict,
    compose_brief,
    defaults as brief_defaults,
    to_markdown,
)
from app.services.match import QueryPlan

router = APIRouter(prefix="/brief", tags=["brief"])

Stage = Literal["phone_screen", "technical", "system_design", "behavioral"]


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


class BriefRequest(BaseModel):
    role: RoleIn
    candidate: CandidateIn
    stage: Stage = "technical"
    interview: dict[str, Any] | None = None
    now: int | None = None


def _to_dicts(req: BriefRequest) -> tuple[dict, dict]:
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
    candidate_dict = req.candidate.model_dump()
    return role_dict, candidate_dict


@router.post("/compose")
def compose(req: BriefRequest) -> dict:
    role_dict, candidate_dict = _to_dicts(req)
    brief = compose_brief(
        role=role_dict,
        candidate=candidate_dict,
        stage=req.stage,
        interview=req.interview,
        now=req.now,
    )
    return brief_as_dict(brief)


@router.post("/markdown")
def markdown(req: BriefRequest) -> dict:
    role_dict, candidate_dict = _to_dicts(req)
    brief = compose_brief(
        role=role_dict,
        candidate=candidate_dict,
        stage=req.stage,
        interview=req.interview,
        now=req.now,
    )
    return {
        "roleId": brief.role_id,
        "candidateId": brief.candidate_id,
        "stage": brief.stage,
        "markdown": to_markdown(brief),
    }


@router.get("/defaults")
def get_defaults() -> dict:
    return brief_defaults()
