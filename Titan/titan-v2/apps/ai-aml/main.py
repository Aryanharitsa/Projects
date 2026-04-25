"""TITAN AML service.

Replaces the prior fintrace-shim with a self-contained, deterministic,
explainable risk engine. Runs offline, has no external ML dependencies,
and exposes a small, well-shaped HTTP surface.

Endpoints
---------
GET  /healthz           liveness + engine version
GET  /aml/rules         current rule weights / thresholds (auditor-facing)
POST /aml/score         score a batch of transactions → per-account reports
POST /aml/sar           generate a SAR draft from one account report
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import Body, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

import risk as risk_engine
import sar as sar_engine

ENGINE_VERSION = "titan-aml/1.0.0"

app = FastAPI(
    title="TITAN AML",
    description=(
        "Deterministic, explainable AML scoring for KYC-verified subjects. "
        "Every rule and threshold is exposed at /aml/rules so reports can be "
        "audited end-to-end."
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
    meta: Optional[Dict[str, Any]] = None


class ScoreReq(BaseModel):
    transactions: List[Tx]


class SARReq(BaseModel):
    account_report: Dict[str, Any]
    analyst: Optional[str] = "TITAN-AUTOMATED"


@app.get("/healthz")
def healthz() -> Dict[str, Any]:
    return {"ok": True, "engine": ENGINE_VERSION}


@app.get("/aml/rules")
def rules() -> Dict[str, Any]:
    return risk_engine.get_rules()


@app.post("/aml/score")
def score(req: ScoreReq = Body(...)) -> Dict[str, Any]:
    if not req.transactions:
        raise HTTPException(status_code=400, detail="transactions[] is empty")
    rows = [t.model_dump() for t in req.transactions]
    return {"ok": True, "engine": ENGINE_VERSION, **risk_engine.score_accounts(rows)}


@app.post("/aml/sar")
def sar(req: SARReq = Body(...)) -> Dict[str, Any]:
    if "account_id" not in req.account_report:
        raise HTTPException(status_code=400, detail="account_report.account_id required")
    return sar_engine.render_sar(req.account_report, analyst=req.analyst or "TITAN-AUTOMATED")
