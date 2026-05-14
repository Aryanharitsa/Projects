"""Offer Studio HTTP surface.

Four endpoints:

* `POST /offer/benchmark` — comp band + equity band + sign-on + bonus
  from a (seniority, location, matched-skill) tuple. Optionally also
  returns a suggested initial draft.
* `POST /offer/simulate` — runs the deterministic win-probability model
  for a given draft + benchmark + signals. Returns per-factor
  contributions so the caller can render the explanation.
* `POST /offer/compose` — builds the Markdown offer letter for a
  finalised draft.
* `POST /offer/full` — convenience: benchmark + simulate + compose in one
  call, useful for agentic clients that want one round-trip.
"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from app.services.match import plan_query
from app.services.offer import (
    OfferDraft,
    band_position,
    benchmark_comp,
    build_offer_letter,
    suggest_draft,
    win_probability,
)


router = APIRouter(prefix="/offer", tags=["offer"])


class _PlanIn(BaseModel):
    seniority: str | None = None
    location: str | None = None


class _DraftIn(BaseModel):
    # Accept both snake_case and camelCase — the TS engine emits camelCase
    # via offer.ts `as_dict()`, while curl-style clients tend to use
    # snake_case. populate_by_name=True wires both up to the same fields.
    model_config = ConfigDict(populate_by_name=True)

    base: float
    equity_pct: float = Field(default=0.0, alias="equityPct")
    target_bonus_pct: float = Field(default=0.0, alias="targetBonusPct")
    sign_on: float = Field(default=0.0, alias="signOn")
    vesting_years: int = Field(default=4, alias="vestingYears")
    cliff_months: int = Field(default=12, alias="cliffMonths")
    start_date: str | None = Field(default=None, alias="startDate")
    expires_on: str | None = Field(default=None, alias="expiresOn")
    notes: str | None = None


def _draft_from_in(d: _DraftIn) -> OfferDraft:
    return OfferDraft(
        base=d.base,
        equity_pct=d.equity_pct,
        target_bonus_pct=d.target_bonus_pct,
        sign_on=d.sign_on,
        vesting_years=d.vesting_years,
        cliff_months=d.cliff_months,
        start_date=d.start_date,
        expires_on=d.expires_on,
        notes=d.notes,
    )


class BenchmarkRequest(BaseModel):
    jd: str | None = None
    plan: _PlanIn | None = None
    matched_skills: list[str] = Field(default_factory=list)
    currency: Literal["INR", "USD"] = "INR"
    include_suggested: bool = True


@router.post("/benchmark")
def benchmark(body: BenchmarkRequest) -> dict:
    seniority: str | None
    location: str | None
    if body.jd:
        qp = plan_query(body.jd)
        seniority = qp.seniority
        location = qp.location
    elif body.plan:
        seniority = body.plan.seniority
        location = body.plan.location
    else:
        seniority, location = None, None
    b = benchmark_comp(seniority, location, list(body.matched_skills), body.currency)
    out: dict = {"benchmark": b.as_dict()}
    if body.include_suggested:
        out["suggested"] = suggest_draft(b).as_dict()
    return out


class SimulateRequest(BaseModel):
    jd: str | None = None
    plan: _PlanIn | None = None
    matched_skills: list[str] = Field(default_factory=list)
    draft: _DraftIn
    composite: int | None = None
    match_score: int = 60
    days_since_outreach: int | None = None
    thin_data: bool = False
    low_confidence: bool = False
    currency: Literal["INR", "USD"] = "INR"


@router.post("/simulate")
def simulate(body: SimulateRequest) -> dict:
    seniority: str | None
    location: str | None
    if body.jd:
        qp = plan_query(body.jd)
        seniority = qp.seniority
        location = qp.location
    elif body.plan:
        seniority = body.plan.seniority
        location = body.plan.location
    else:
        seniority, location = None, None
    bench = benchmark_comp(seniority, location, list(body.matched_skills), body.currency)
    draft = _draft_from_in(body.draft)
    win = win_probability(
        draft, bench,
        composite=body.composite,
        match_score=body.match_score,
        matched_skills=list(body.matched_skills),
        days_since_outreach=body.days_since_outreach,
        thin_data=body.thin_data,
        low_confidence=body.low_confidence,
    )
    return {
        "benchmark": bench.as_dict(),
        "win": win.as_dict(),
        "bandPosition": round(band_position(draft, bench), 3),
    }


class ComposeRequest(BaseModel):
    company_name: str = "Your Company"
    hiring_manager: str | None = None
    candidate_name: str
    role_name: str
    location: str
    jd: str | None = None
    plan: _PlanIn | None = None
    matched_skills: list[str] = Field(default_factory=list)
    draft: _DraftIn
    currency: Literal["INR", "USD"] = "INR"


@router.post("/compose")
def compose(body: ComposeRequest) -> dict:
    seniority: str | None
    location: str | None
    if body.jd:
        qp = plan_query(body.jd)
        seniority = qp.seniority
        location = qp.location
    elif body.plan:
        seniority = body.plan.seniority
        location = body.plan.location
    else:
        seniority, location = None, None
    bench = benchmark_comp(seniority, location, list(body.matched_skills), body.currency)
    draft = _draft_from_in(body.draft)
    md = build_offer_letter(
        company_name=body.company_name,
        hiring_manager=body.hiring_manager,
        candidate_name=body.candidate_name,
        role_name=body.role_name,
        location=body.location,
        offer=draft,
        benchmark=bench,
    )
    return {"markdown": md, "benchmark": bench.as_dict()}


class FullRequest(SimulateRequest):
    company_name: str = "Your Company"
    hiring_manager: str | None = None
    candidate_name: str = "Candidate"
    role_name: str = "Role"
    location: str = "Bengaluru"


@router.post("/full")
def full(body: FullRequest) -> dict:
    sim = simulate(body)  # type: ignore[arg-type]
    bench_data = sim["benchmark"]
    draft = _draft_from_in(body.draft)
    # Rebuild benchmark for letter (cheap; deterministic).
    seniority: str | None
    location: str | None
    if body.jd:
        qp = plan_query(body.jd)
        seniority = qp.seniority
        location = qp.location
    elif body.plan:
        seniority = body.plan.seniority
        location = body.plan.location
    else:
        seniority, location = None, None
    bench = benchmark_comp(seniority, location, list(body.matched_skills), body.currency)
    md = build_offer_letter(
        company_name=body.company_name,
        hiring_manager=body.hiring_manager,
        candidate_name=body.candidate_name,
        role_name=body.role_name,
        location=body.location,
        offer=draft,
        benchmark=bench,
    )
    return {
        "benchmark": bench_data,
        "win": sim["win"],
        "bandPosition": sim["bandPosition"],
        "letter": md,
    }
