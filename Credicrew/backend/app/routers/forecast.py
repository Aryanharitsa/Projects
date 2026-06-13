"""Forecast Studio HTTP surface.

``POST /forecast/run`` — takes the current funnel (counts at each stage),
a target start date, and optional conversion/velocity overrides, and
returns the Monte-Carlo forecast: probability of a hire by the target
date, P10/P50/P90 fan, bottleneck, sensitivity tornado, and concrete
recommendations.

Accepts both ``camelCase`` (TS-engine style) and ``snake_case`` payloads.
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from app.services.forecast import (
    DEFAULT_CONVERSION,
    DEFAULT_VELOCITY,
    DEFAULT_NOTICE_DAYS,
    DEFAULT_DURATION_SIGMA,
    ForecastAssumptions,
    ForecastInput,
    forecast_funnel,
)

router = APIRouter(prefix="/forecast", tags=["forecast"])


class _FunnelIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    new: int = 0
    outreach: int = 0
    screening: int = 0
    interview: int = 0
    offer: int = 0


class _AssumptionsIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    conversion: dict[str, float] | None = None
    velocity: dict[str, float] | None = None
    notice_period_days: int | None = Field(None, alias="noticePeriodDays")
    duration_sigma: float | None = Field(None, alias="durationSigma")


class ForecastRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    funnel: _FunnelIn
    target_date: str = Field(..., alias="targetDate")
    now: int | None = None
    trials: int = 4000
    seed: int | None = None
    assumptions: _AssumptionsIn | None = None


def _to_assumptions(over: _AssumptionsIn | None) -> ForecastAssumptions:
    if over is None:
        return ForecastAssumptions()
    return ForecastAssumptions(
        conversion={**DEFAULT_CONVERSION, **(over.conversion or {})},
        velocity={**DEFAULT_VELOCITY, **(over.velocity or {})},
        notice_period_days=(
            over.notice_period_days if over.notice_period_days is not None else DEFAULT_NOTICE_DAYS
        ),
        duration_sigma=(
            over.duration_sigma if over.duration_sigma is not None else DEFAULT_DURATION_SIGMA
        ),
    )


@router.post("/run")
def run(body: ForecastRequest) -> dict:
    inp = ForecastInput(
        funnel={
            "new": body.funnel.new,
            "outreach": body.funnel.outreach,
            "screening": body.funnel.screening,
            "interview": body.funnel.interview,
            "offer": body.funnel.offer,
        },
        target_date=body.target_date,
        now=body.now,
        assumptions=_to_assumptions(body.assumptions),
        trials=body.trials,
        seed=body.seed,
    )
    return forecast_funnel(inp)


@router.get("/defaults")
def defaults() -> dict:
    return {
        "conversion": dict(DEFAULT_CONVERSION),
        "velocity": dict(DEFAULT_VELOCITY),
        "noticePeriodDays": DEFAULT_NOTICE_DAYS,
        "durationSigma": DEFAULT_DURATION_SIGMA,
        "progression": ["new", "outreach", "screening", "interview", "offer"],
    }
