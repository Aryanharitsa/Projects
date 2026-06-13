"""Cadence Studio HTTP surface.

``POST /cadence/summary`` — takes a list of shortlist entries (one
``CadenceCandidate`` per active candidate-in-pipeline), runs the velocity
+ SLA engine, and returns the full summary: per-stage rollups, per-role
rollups, hot list, recommendations and a 7-day exit forecast.

``POST /cadence/brief`` — re-renders a markdown brief from a summary
payload.

``GET /cadence/defaults`` — exposes the SLA + median priors so the
frontend (and curious clients) can keep the calibration in sync without
hard-coding numbers.

Accepts both ``camelCase`` (TS-engine style) and ``snake_case`` payloads
via Pydantic aliases.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from app.services.cadence import (
    ACTIVE_STAGES,
    BAND_LABEL,
    CADENCE_BANDS,
    STAGE_LABEL,
    STAGE_MEDIAN_DAYS,
    STAGE_SLA_DAYS,
    CadenceCandidate,
    analyze_cadence,
    build_cadence_brief,
    synth_stage_age,
)

router = APIRouter(prefix="/cadence", tags=["cadence"])


class _CandidateIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    candidate_id: int = Field(..., alias="candidateId")
    candidate_name: str = Field(..., alias="candidateName")
    role_id: str = Field(..., alias="roleId")
    role_name: str = Field(..., alias="roleName")
    stage: str
    stage_age_days: Optional[float] = Field(None, alias="stageAgeDays")
    pipeline_age_days: Optional[float] = Field(None, alias="pipelineAgeDays")
    match_score: float = Field(0.0, alias="matchScore")
    location: Optional[str] = None


class CadenceRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    candidates: list[_CandidateIn]
    horizon_days: int = Field(7, alias="horizonDays")
    now: Optional[int] = None
    include_brief: bool = Field(False, alias="includeBrief")


class BriefRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    summary: dict
    iso_date: Optional[str] = Field(None, alias="isoDate")


def _resolve_candidates(rows: list[_CandidateIn]) -> list[CadenceCandidate]:
    out: list[CadenceCandidate] = []
    for r in rows:
        stage_age = (
            r.stage_age_days
            if r.stage_age_days is not None
            else synth_stage_age(r.role_id, r.candidate_id, r.stage)
        )
        pipeline_age = (
            r.pipeline_age_days
            if r.pipeline_age_days is not None
            else stage_age
        )
        out.append(
            CadenceCandidate(
                candidate_id=r.candidate_id,
                candidate_name=r.candidate_name,
                role_id=r.role_id,
                role_name=r.role_name,
                stage=r.stage,
                stage_age_days=float(stage_age),
                pipeline_age_days=float(pipeline_age),
                match_score=float(r.match_score),
                location=r.location,
            )
        )
    return out


@router.post("/summary")
def summary(body: CadenceRequest) -> dict:
    cands = _resolve_candidates(body.candidates)
    now_ms = body.now if body.now is not None else int(
        datetime.now(timezone.utc).timestamp() * 1000
    )
    summary_payload = analyze_cadence(
        cands,
        horizon_days=body.horizon_days,
        now_ms=now_ms,
    )
    if body.include_brief:
        iso_date = datetime.fromtimestamp(now_ms / 1000, tz=timezone.utc).date().isoformat()
        summary_payload = {
            **summary_payload,
            "brief": build_cadence_brief(summary_payload, iso_date=iso_date),
        }
    return summary_payload


@router.post("/brief")
def brief(body: BriefRequest) -> dict:
    iso_date = body.iso_date or datetime.now(timezone.utc).date().isoformat()
    return {"markdown": build_cadence_brief(body.summary, iso_date=iso_date)}


@router.get("/defaults")
def defaults() -> dict:
    return {
        "stageSlaDays": {s: STAGE_SLA_DAYS[s] for s in ACTIVE_STAGES},
        "stageMedianDays": {s: STAGE_MEDIAN_DAYS[s] for s in ACTIVE_STAGES},
        "stageLabels": {s: STAGE_LABEL[s] for s in ACTIVE_STAGES},
        "bands": list(CADENCE_BANDS),
        "bandLabels": dict(BAND_LABEL),
        "horizonDays": 7,
        "model": {
            "bandRule": "on_track <= 0.7*SLA; slowing <= SLA; at_risk <= 1.6*SLA; stalled > 1.6*SLA",
            "survival7d": "exp(-7 * ln 2 / median)",
            "risk": "0.6 * clip((age - sla)/median, 0, 1) + 0.4 * clip(age/(4*median), 0, 1)",
        },
    }
