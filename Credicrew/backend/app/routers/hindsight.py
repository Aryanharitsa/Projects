"""Hindsight HTTP surface.

``POST /hindsight/summary`` — takes a portfolio (list of roles + a candidate
pool + optional interview records + optional logged outcomes) and returns
the post-hire calibration summary used by the ``/hindsight`` frontend
surface: per-dim predictive power, suggested rubric reweights, surprise
hires, calibration curve bins, tenure-by-band and the headline counts.

``POST /hindsight/brief`` — re-renders the markdown calibration brief from
a payload (mirrors the surface's "copy brief" button).

``GET /hindsight/defaults`` — exposes the thresholds and formulas the
engine uses so clients can stay in sync without hard-coding them.

Accepts both ``camelCase`` (TS-engine style) and ``snake_case`` payloads
via Pydantic aliases.
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from app.services.hindsight import (
    FN_COMPOSITE_CEIL,
    FN_PERF_FLOOR,
    FP_COMPOSITE_FLOOR,
    FP_PERF_FLOOR,
    GOOD_HIRE_FLOOR,
    MIN_SAMPLES,
    PP_MODERATE,
    PP_STRONG,
    PP_WEAK,
    RETUNE_BLEND,
    analyze_hindsight,
    build_brief,
    summary_to_dict,
)

router = APIRouter(prefix="/hindsight", tags=["hindsight"])


class _ShortlistEntry(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="allow")

    candidate_id: int = Field(..., alias="candidateId")
    status: str = "new"
    added_at: Optional[float] = Field(None, alias="addedAt")
    stage_changed_at: Optional[float] = Field(None, alias="stageChangedAt")
    note: Optional[str] = None


class _PlanIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="allow")

    text: Optional[str] = ""
    skills: list[str] = Field(default_factory=list)
    location: Optional[str] = None
    seniority: Optional[str] = None


class _RoleIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="allow")

    id: str
    name: str
    jd: Optional[str] = None
    plan: Optional[_PlanIn] = None
    shortlist: list[_ShortlistEntry] = Field(default_factory=list)


class _CandidateIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="allow")

    id: int
    name: Optional[str] = None
    role: Optional[str] = None
    location: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    headline: Optional[str] = None


class _OutcomeIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="allow")

    candidate_id: int = Field(..., alias="candidateId")
    role_id: str = Field(..., alias="roleId")
    hired_at_ms: Optional[float] = Field(None, alias="hiredAtMs")
    performance: int = 3
    tenure_days: int = Field(0, alias="tenureDays")
    still_active: bool = Field(True, alias="stillActive")
    note: Optional[str] = None
    source: str = "real"


class _SummaryRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="allow")

    roles: list[_RoleIn]
    candidates: list[_CandidateIn]
    # Interview records carry their own rubric + stages; we keep them
    # loosely typed because they're large and the engine only reads
    # `rubric` and `stages[*].scores[*]`.
    interviews: list[dict[str, Any]] = Field(default_factory=list)
    outcomes: list[_OutcomeIn] = Field(default_factory=list)
    include_brief: bool = Field(False, alias="includeBrief")
    now_ms: Optional[int] = Field(None, alias="nowMs")


class _BriefRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="allow")

    summary: dict[str, Any]


def _role_to_dict(r: _RoleIn) -> dict[str, Any]:
    return {
        "id": r.id,
        "name": r.name,
        "jd": r.jd,
        "plan": (r.plan.model_dump(by_alias=False) if r.plan else None),
        "shortlist": [
            {
                "candidate_id": e.candidate_id,
                "status": e.status,
                "added_at": e.added_at or 0,
                "stage_changed_at": e.stage_changed_at,
                "note": e.note,
            }
            for e in r.shortlist
        ],
    }


def _candidate_to_dict(c: _CandidateIn) -> dict[str, Any]:
    return {
        "id": c.id,
        "name": c.name,
        "role": c.role,
        "location": c.location,
        "tags": c.tags,
        "keywords": c.keywords,
        "headline": c.headline,
    }


def _outcome_to_dict(o: _OutcomeIn) -> dict[str, Any]:
    return {
        "candidate_id": o.candidate_id,
        "role_id": o.role_id,
        "hired_at_ms": o.hired_at_ms,
        "performance": o.performance,
        "tenure_days": o.tenure_days,
        "still_active": o.still_active,
        "note": o.note,
        "source": o.source,
    }


@router.post("/summary")
def hindsight_summary(req: _SummaryRequest) -> dict[str, Any]:
    summary = analyze_hindsight(
        [_role_to_dict(r) for r in req.roles],
        [_candidate_to_dict(c) for c in req.candidates],
        interviews=req.interviews,
        outcomes=[_outcome_to_dict(o) for o in req.outcomes],
        now_ms=req.now_ms,
    )
    out = summary_to_dict(summary)
    if req.include_brief:
        out["brief"] = build_brief(summary)
    return out


@router.post("/brief")
def hindsight_brief(req: _BriefRequest) -> dict[str, Any]:
    # Reconstruct the minimum HindsightSummary needed for build_brief. We
    # only need the headline + per-dim + recommendation + surprise + bins +
    # actions. We round-trip through dataclasses for type sanity.
    from app.services.hindsight import (
        CompositeBin,
        DimensionCalibration,
        HindsightSummary,
        RubricRecommendation,
        SurpriseCase,
        TenureBand,
    )

    s = req.summary

    def _ix(d: dict[str, Any], *keys: str, default: Any = None) -> Any:
        for k in keys:
            if k in d and d[k] is not None:
                return d[k]
        return default

    per_dim = [
        DimensionCalibration(
            key=str(_ix(d, "key", default="")),
            label=str(_ix(d, "label", default="")),
            current_weight=float(_ix(d, "current_weight", "currentWeight", default=0.0)),
            r_performance=float(_ix(d, "r_performance", "rPerformance", default=0.0)),
            r_tenure=float(_ix(d, "r_tenure", "rTenure", default=0.0)),
            samples=int(_ix(d, "samples", default=0)),
            predictive_power=int(_ix(d, "predictive_power", "predictivePower", default=0)),
            suggested_weight=float(_ix(d, "suggested_weight", "suggestedWeight", default=0.0)),
            weight_delta=float(_ix(d, "weight_delta", "weightDelta", default=0.0)),
            band=str(_ix(d, "band", default="unknown")),
        )
        for d in (s.get("per_dimension") or s.get("perDimension") or [])
    ]
    bins = [
        CompositeBin(
            label=str(_ix(b, "label", default="")),
            floor=int(_ix(b, "floor", default=0)),
            count=int(_ix(b, "count", default=0)),
            mean_performance=float(_ix(b, "mean_performance", "meanPerformance", default=0.0)),
            mean_tenure_days=int(_ix(b, "mean_tenure_days", "meanTenureDays", default=0)),
            good_rate=float(_ix(b, "good_rate", "goodRate", default=0.0)),
        )
        for b in (s.get("composite_bins") or s.get("compositeBins") or [])
    ]
    surprises = [
        SurpriseCase(
            candidate_id=int(_ix(c, "candidate_id", "candidateId", default=0)),
            candidate_name=str(_ix(c, "candidate_name", "candidateName", default="")),
            role_id=str(_ix(c, "role_id", "roleId", default="")),
            role_name=str(_ix(c, "role_name", "roleName", default="")),
            composite=int(_ix(c, "composite", default=0)),
            performance=int(_ix(c, "performance", default=0)),
            tenure_days=int(_ix(c, "tenure_days", "tenureDays", default=0)),
            still_active=bool(_ix(c, "still_active", "stillActive", default=True)),
            kind=str(_ix(c, "kind", default="false_positive")),
            driver_key=_ix(c, "driver_key", "driverKey"),
            driver_label=_ix(c, "driver_label", "driverLabel"),
            driver_rating=_ix(c, "driver_rating", "driverRating"),
            why=str(_ix(c, "why", default="")),
        )
        for c in (s.get("surprise_cases") or s.get("surpriseCases") or [])
    ]
    tbb = [
        TenureBand(
            band=str(_ix(b, "band", default="")),
            mean_tenure_days=int(_ix(b, "mean_tenure_days", "meanTenureDays", default=0)),
            mean_performance=float(_ix(b, "mean_performance", "meanPerformance", default=0.0)),
            count=int(_ix(b, "count", default=0)),
        )
        for b in (s.get("tenure_by_band") or s.get("tenureByBand") or [])
    ]
    rec_in = s.get("rubric_recommendation") or s.get("rubricRecommendation") or {}
    rec = RubricRecommendation(
        keep=list(rec_in.get("keep") or []),
        promote=list(rec_in.get("promote") or []),
        reduce=list(rec_in.get("reduce") or []),
        drop=list(rec_in.get("drop") or []),
    )

    summary = HindsightSummary(
        generated_at=int(_ix(s, "generated_at", "generatedAt", default=0)),
        hires=[],
        hire_count=int(_ix(s, "hire_count", "hireCount", default=0)),
        real_count=int(_ix(s, "real_count", "realCount", default=0)),
        synthetic_count=int(_ix(s, "synthetic_count", "syntheticCount", default=0)),
        hit_rate=float(_ix(s, "hit_rate", "hitRate", default=0.0)),
        mean_composite=int(_ix(s, "mean_composite", "meanComposite", default=0)),
        mean_performance=float(_ix(s, "mean_performance", "meanPerformance", default=0.0)),
        mean_tenure_days=int(_ix(s, "mean_tenure_days", "meanTenureDays", default=0)),
        attrition_rate=float(_ix(s, "attrition_rate", "attritionRate", default=0.0)),
        pearson=float(_ix(s, "pearson", default=0.0)),
        spearman=float(_ix(s, "spearman", default=0.0)),
        brier_score=float(_ix(s, "brier_score", "brierScore", default=0.0)),
        per_dimension=per_dim,
        composite_bins=bins,
        surprise_cases=surprises,
        rubric_recommendation=rec,
        tenure_by_band=tbb,
        calibration_band=str(_ix(s, "calibration_band", "calibrationBand", default="unknown")),
        actions=list(_ix(s, "actions", default=[])),
    )
    return {"markdown": build_brief(summary)}


@router.get("/defaults")
def hindsight_defaults() -> dict[str, Any]:
    return {
        "thresholds": {
            "pp_strong": PP_STRONG,
            "pp_moderate": PP_MODERATE,
            "pp_weak": PP_WEAK,
            "fp_composite_floor": FP_COMPOSITE_FLOOR,
            "fp_perf_floor": FP_PERF_FLOOR,
            "fn_composite_ceil": FN_COMPOSITE_CEIL,
            "fn_perf_floor": FN_PERF_FLOOR,
            "min_samples": MIN_SAMPLES,
            "retune_blend": RETUNE_BLEND,
            "good_hire_floor": GOOD_HIRE_FLOOR,
        },
        "formulas": {
            "predictive_power": "round(max(|r_perf|, 0.6·|r_tenure|) · 100)",
            "suggested_weight": "0.5 · (|r_perf| / Σ|r_perf|) + 0.5 · current_weight, then renormalised",
            "calibration_band": "excellent ≥ 0.55 · good ≥ 0.35 · mixed ≥ 0.15 · concerning < 0.15",
            "brier_score": "mean( (composite/100 − good)^2 )",
            "tenure_synthesis": "60 + perf · 95 + (h>>8 % 60), capped to days since hire",
        },
    }
