"""Sourcing Intelligence HTTP surface (Channel Studio).

`POST /sources/summary` — takes a flat list of shortlisted candidates
(each carrying its match score, interview composite, accept-probability,
and source attribution) and returns the per-channel ROI rollup that the
TS engine in `frontend/src/lib/sources.ts` produces — byte-identical for
the same input.

Accepts both ``camelCase`` (TS-style) and ``snake_case`` (curl-style)
payloads via Pydantic field aliases.
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from app.services.sources import (
    SourceAttribution,
    SourceCandidate,
    SourceInput,
    analyze_sources,
    build_source_brief,
)


router = APIRouter(prefix="/sources", tags=["sources"])


class _AttributionIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    channel: str
    detail: str | None = None
    cost_override: float | None = Field(None, alias="costOverride")


class _CandidateIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    candidate_id: int = Field(alias="candidateId")
    name: str
    role_id: str = Field(alias="roleId")
    role_name: str = Field(alias="roleName")
    status: str = "new"
    added_at: int = Field(0, alias="addedAt")
    match_score: float = Field(0.0, alias="matchScore")
    composite: float | None = None
    confidence: float = 0.0
    source: _AttributionIn
    win_probability: float | None = Field(None, alias="winProbability")
    has_offer: bool = Field(False, alias="hasOffer")
    location: str | None = None


class SourcesRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    candidates: list[_CandidateIn] = Field(default_factory=list)
    cost_overrides: dict[str, float] = Field(default_factory=dict, alias="costOverrides")
    now: int | None = None
    include_brief: bool = Field(False, alias="includeBrief")


def _to_candidate(c: _CandidateIn) -> SourceCandidate:
    return SourceCandidate(
        candidate_id=c.candidate_id,
        name=c.name,
        role_id=c.role_id,
        role_name=c.role_name,
        status=c.status,
        added_at=c.added_at,
        match_score=c.match_score,
        composite=c.composite,
        confidence=c.confidence,
        source=SourceAttribution(
            channel=c.source.channel,
            detail=c.source.detail,
            cost_override=c.source.cost_override,
        ),
        win_probability=c.win_probability,
        has_offer=c.has_offer,
        location=c.location,
    )


@router.post("/summary")
async def sources_summary(payload: SourcesRequest) -> dict:
    input_ = SourceInput(
        candidates=[_to_candidate(c) for c in payload.candidates],
        cost_overrides={k: float(v) for k, v in (payload.cost_overrides or {}).items()},
        now=payload.now,
    )
    summary = analyze_sources(input_)
    if payload.include_brief:
        summary["brief"] = build_source_brief(summary)
    return summary


class _BriefRequest(BaseModel):
    """Stand-alone Markdown brief — useful when the caller already has the summary."""
    model_config = ConfigDict(populate_by_name=True)

    summary: dict
    title: str | None = None


@router.post("/brief")
async def sources_brief(payload: _BriefRequest) -> dict:
    return {"markdown": build_source_brief(payload.summary, payload.title)}
