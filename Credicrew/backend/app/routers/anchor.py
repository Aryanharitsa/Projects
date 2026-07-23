"""API surface for Anchor — the Momentum & Drop-Off Risk Radar.

`POST /anchor/summary`  — {candidates} → AnchorSummary
`POST /anchor/markdown` — same input → {markdown: "..."}
`GET  /anchor/defaults` — physics constants + palettes for the UI

Byte-for-byte parity with `frontend/src/lib/anchor.ts`.
"""
from __future__ import annotations

from typing import Any, Literal, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.services.anchor import (
    CandidateInput,
    Signals,
    analyze,
    defaults as anchor_defaults,
    summary_as_dict,
    to_markdown,
)


router = APIRouter(prefix="/anchor", tags=["anchor"])


SentimentToneIn = Literal["warm", "neutral", "cool"]
TouchDirectionIn = Literal["in", "out"]
StatusIn = Literal["new", "outreach", "screening", "interview", "offer", "passed"]


class SignalsIn(BaseModel):
    daysSinceLastTouch: float = 0.0
    lastTouchDirection: TouchDirectionIn = "out"
    responseLatencyHours: float = 6.0
    rescheduleCount: int = 0
    noShow: bool = False
    daysInStage: float = 0.0
    competingPipelines: int = 0
    sentimentTone: SentimentToneIn = "neutral"
    externalOffer: bool = False
    noteKeyphrase: Optional[str] = None


class CandidateIn(BaseModel):
    candidateId: int
    candidateName: str
    roleId: str
    roleName: str
    status: StatusIn
    addedAt: int
    matchScore: float = 0.0
    compositeScore: Optional[float] = None
    candidateTitle: Optional[str] = None
    candidateLocation: Optional[str] = None
    roleSeniority: Optional[str] = None
    stageChangedAt: Optional[int] = None
    offerValueAnnual: Optional[float] = None
    signals: Optional[SignalsIn] = None


class SummaryRequest(BaseModel):
    candidates: list[CandidateIn] = Field(default_factory=list)
    now: Optional[int] = None


def _to_candidate(c: CandidateIn) -> CandidateInput:
    sigs = None
    if c.signals is not None:
        sigs = Signals(
            days_since_last_touch=c.signals.daysSinceLastTouch,
            last_touch_direction=c.signals.lastTouchDirection,
            response_latency_hours=c.signals.responseLatencyHours,
            reschedule_count=c.signals.rescheduleCount,
            no_show=c.signals.noShow,
            days_in_stage=c.signals.daysInStage,
            competing_pipelines=c.signals.competingPipelines,
            sentiment_tone=c.signals.sentimentTone,
            external_offer=c.signals.externalOffer,
            note_keyphrase=c.signals.noteKeyphrase,
        )
    return CandidateInput(
        candidate_id=c.candidateId,
        candidate_name=c.candidateName,
        candidate_title=c.candidateTitle,
        candidate_location=c.candidateLocation,
        role_id=c.roleId,
        role_name=c.roleName,
        role_seniority=c.roleSeniority,
        status=c.status,
        added_at=c.addedAt,
        stage_changed_at=c.stageChangedAt,
        match_score=c.matchScore,
        composite_score=c.compositeScore,
        offer_value_annual=c.offerValueAnnual,
        signals=sigs,
    )


@router.post("/summary")
def summary(req: SummaryRequest) -> dict[str, Any]:
    inputs = [_to_candidate(c) for c in req.candidates]
    result = analyze(inputs, now=req.now)
    return summary_as_dict(result)


@router.post("/markdown")
def markdown(req: SummaryRequest) -> dict[str, Any]:
    inputs = [_to_candidate(c) for c in req.candidates]
    result = analyze(inputs, now=req.now)
    return {"markdown": to_markdown(result)}


@router.get("/defaults")
def get_defaults() -> dict[str, Any]:
    return anchor_defaults()
