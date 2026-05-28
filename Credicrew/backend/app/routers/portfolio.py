"""Hiring Command Center HTTP surface.

`POST /portfolio/summary` — takes a flattened snapshot of every role and
its shortlist (each candidate carrying match score, interview composite,
offer draft, accept-probability) and returns the portfolio rollup: hero
KPIs, the aggregate funnel, the comp forecast, per-role health, the
cross-role talent leaderboard, and the attention feed.

Accepts both ``camelCase`` (TS-engine `as_dict` style) and ``snake_case``
(curl-style) payloads via Pydantic field aliases.
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from app.services.portfolio import (
    PortfolioCandidate,
    PortfolioOffer,
    PortfolioRole,
    build_portfolio,
)

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


class _OfferIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    base: float
    equity_pct: float = Field(0.0, alias="equityPct")
    target_bonus_pct: float = Field(0.0, alias="targetBonusPct")
    sign_on: float = Field(0.0, alias="signOn")


class _CandidateIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    candidate_id: int = Field(alias="candidateId")
    name: str
    status: str = "new"
    added_at: int = Field(0, alias="addedAt")
    match_score: int = Field(0, alias="matchScore")
    composite: int | None = None
    confidence: float = 0.0
    recommendation: str | None = None
    role: str | None = None
    offer: _OfferIn | None = None
    win_probability: float | None = Field(None, alias="winProbability")


class _RoleIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    name: str
    created_at: int = Field(0, alias="createdAt")
    updated_at: int = Field(0, alias="updatedAt")
    seniority: str | None = None
    location: str | None = None
    candidates: list[_CandidateIn] = Field(default_factory=list)


class PortfolioRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    roles: list[_RoleIn] = Field(default_factory=list)
    now: int | None = None


def _to_role(r: _RoleIn) -> PortfolioRole:
    return PortfolioRole(
        id=r.id,
        name=r.name,
        created_at=r.created_at,
        updated_at=r.updated_at,
        seniority=r.seniority,
        location=r.location,
        candidates=[
            PortfolioCandidate(
                candidate_id=c.candidate_id,
                name=c.name,
                status=c.status,
                added_at=c.added_at,
                match_score=c.match_score,
                composite=c.composite,
                confidence=c.confidence,
                recommendation=c.recommendation,
                role=c.role,
                offer=(
                    PortfolioOffer(
                        base=c.offer.base,
                        equity_pct=c.offer.equity_pct,
                        target_bonus_pct=c.offer.target_bonus_pct,
                        sign_on=c.offer.sign_on,
                    )
                    if c.offer is not None
                    else None
                ),
                win_probability=c.win_probability,
            )
            for c in r.candidates
        ],
    )


@router.post("/summary")
def summary(body: PortfolioRequest) -> dict:
    roles = [_to_role(r) for r in body.roles]
    return build_portfolio(roles, body.now)
