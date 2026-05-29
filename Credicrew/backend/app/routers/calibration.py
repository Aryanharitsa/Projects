"""Calibration Studio HTTP surface.

* ``POST /calibration/summary`` — given a panel (interviewers + ratings),
  the candidates, and the rubric, return per-interviewer bias, panel
  reliability (consensus index + ICC), the raw-vs-de-biased ranking, and
  disagreement hot-cells.

The engine is pure (``app/services/calibration.py``) and mirrors the
browser engine byte-for-byte, so a programmatic / agentic caller gets the
same verdict the UI shows.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from app.services.calibration import (
    CandidateLite,
    Interviewer,
    PanelRating,
    RubricLite,
    compute_calibration,
)

router = APIRouter(prefix="/calibration", tags=["calibration"])


class InterviewerIn(BaseModel):
    id: str
    name: str
    title: Optional[str] = None


class RatingIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    interviewer_id: str = Field(alias="interviewerId")
    candidate_id: int = Field(alias="candidateId")
    dim_key: str = Field(alias="dimKey")
    rating: float


class CandidateIn(BaseModel):
    id: int
    name: str
    role: Optional[str] = None
    location: Optional[str] = None


class RubricIn(BaseModel):
    key: str
    label: str
    weight: float


class SummaryRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    role_id: str = Field(default="role", alias="roleId")
    interviewers: list[InterviewerIn] = Field(default_factory=list)
    ratings: list[RatingIn] = Field(default_factory=list)
    candidates: list[CandidateIn] = Field(default_factory=list)
    rubric: list[RubricIn] = Field(default_factory=list)
    generated_at: int = Field(default=0, alias="generatedAt")


@router.post("/summary")
def summary(body: SummaryRequest) -> dict:
    result = compute_calibration(
        role_id=body.role_id,
        interviewers=[
            Interviewer(id=i.id, name=i.name, title=i.title) for i in body.interviewers
        ],
        ratings=[
            PanelRating(
                interviewer_id=r.interviewer_id,
                candidate_id=r.candidate_id,
                dim_key=r.dim_key,
                rating=r.rating,
            )
            for r in body.ratings
        ],
        candidates=[
            CandidateLite(id=c.id, name=c.name, role=c.role, location=c.location)
            for c in body.candidates
        ],
        rubric=[RubricLite(key=d.key, label=d.label, weight=d.weight) for d in body.rubric],
        generated_at=body.generated_at,
    )
    return result.as_dict()
