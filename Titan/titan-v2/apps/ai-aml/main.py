"""TITAN AML service.

Replaces the prior fintrace-shim with a self-contained, deterministic,
explainable risk engine. Runs offline, has no external ML dependencies,
and exposes a small, well-shaped HTTP surface.

Endpoints
---------
GET  /healthz                   liveness + engine version
GET  /aml/rules                 current rule weights / thresholds (auditor-facing)
POST /aml/score                 score a batch of transactions → per-account reports
POST /aml/sar                   generate a SAR draft from one account report
POST /aml/sanctions/screen      fuzzy-match one or more names against the watchlist
GET  /aml/sanctions/list        full bundled watchlist (paged)
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import Body, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

import risk as risk_engine
import sanctions as sanctions_engine
import sar as sar_engine

ENGINE_VERSION = "titan-aml/1.1.0"

app = FastAPI(
    title="TITAN AML",
    description=(
        "Deterministic, explainable AML scoring + sanctions screening. "
        "Every rule, threshold, and watchlist entry is exposed for audit."
    ),
    version=ENGINE_VERSION,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class Tx(BaseModel):
    account_id: str
    counterparty: str
    amount: float = Field(gt=0)
    timestamp: str
    channel: Optional[str] = ""
    geo: Optional[str] = ""
    subject: Optional[str] = ""
    subject_name: Optional[str] = ""
    counterparty_name: Optional[str] = ""
    meta: Optional[Dict[str, Any]] = None


class ScoreReq(BaseModel):
    transactions: List[Tx]
    weights: Optional[Dict[str, float]] = Field(
        default=None,
        description="Optional per-detector weight overrides for what-if analysis.",
    )
    sanctions_threshold: Optional[float] = Field(
        default=None, ge=0.0, le=1.0,
        description="Override the sanctions-hit similarity gate (default 0.65).",
    )


class SARReq(BaseModel):
    account_report: Dict[str, Any]
    analyst: Optional[str] = "TITAN-AUTOMATED"


class ScreenReq(BaseModel):
    names: List[str] = Field(..., min_length=1)
    jurisdiction: Optional[str] = None
    threshold: float = Field(default=0.45, ge=0.0, le=1.0)
    top_k: int = Field(default=5, ge=1, le=20)


@app.get("/healthz")
def healthz() -> Dict[str, Any]:
    meta = sanctions_engine.get_metadata()
    return {
        "ok": True,
        "engine": ENGINE_VERSION,
        "watchlist": {"version": meta.get("version"), "size": meta.get("size")},
    }


@app.get("/aml/rules")
def rules() -> Dict[str, Any]:
    return risk_engine.get_rules()


@app.post("/aml/score")
def score(req: ScoreReq = Body(...)) -> Dict[str, Any]:
    if not req.transactions:
        raise HTTPException(status_code=400, detail="transactions[] is empty")
    rows = [t.model_dump() for t in req.transactions]
    threshold = (
        req.sanctions_threshold
        if req.sanctions_threshold is not None
        else risk_engine.SANCTIONS_HIT_THRESHOLD
    )
    return {
        "ok": True,
        "engine": ENGINE_VERSION,
        **risk_engine.score_accounts(
            rows,
            weights_override=req.weights,
            sanctions_threshold=threshold,
        ),
    }


@app.post("/aml/sar")
def sar(req: SARReq = Body(...)) -> Dict[str, Any]:
    if "account_id" not in req.account_report:
        raise HTTPException(status_code=400, detail="account_report.account_id required")
    return sar_engine.render_sar(req.account_report, analyst=req.analyst or "TITAN-AUTOMATED")


@app.post("/aml/sanctions/screen")
def sanctions_screen(req: ScreenReq = Body(...)) -> Dict[str, Any]:
    results = sanctions_engine.screen_many(
        req.names,
        jurisdiction=req.jurisdiction,
        threshold=req.threshold,
        top_k=req.top_k,
    )
    matched = sum(1 for r in results if r.get("best"))
    grade_counts: Dict[str, int] = {}
    for r in results:
        if r.get("best"):
            grade_counts[r["best"]["grade"]] = grade_counts.get(r["best"]["grade"], 0) + 1
    return {
        "ok": True,
        "engine": ENGINE_VERSION,
        "watchlist": sanctions_engine.get_metadata(),
        "queried": len(req.names),
        "matched": matched,
        "by_grade": grade_counts,
        "results": results,
    }


@app.get("/aml/sanctions/list")
def sanctions_list(limit: int = 50) -> Dict[str, Any]:
    return {
        "ok": True,
        "watchlist": sanctions_engine.get_metadata(),
        "entries": sanctions_engine.list_entries(limit=limit),
    }
