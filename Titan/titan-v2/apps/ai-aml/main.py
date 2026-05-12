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

Case-management surface (round-3, day-15)
-----------------------------------------
GET    /aml/cases               queue with priority/status/assignee filters
POST   /aml/cases/open          promote one account_report to a case
POST   /aml/cases/bulk_open     promote a /aml/score response in one shot
GET    /aml/cases/stats         dashboard tiles + SLA breakdown
GET    /aml/cases/assignees     distinct assignees seen in the store
GET    /aml/cases/{id}          one case + full event timeline + snapshot
POST   /aml/cases/{id}/transition   open → review → cleared/escalated/sar_filed
POST   /aml/cases/{id}/assign       set or clear assignee
POST   /aml/cases/{id}/note         append a free-text note to the timeline
POST   /aml/cases/{id}/sar          generate + attach SAR, transition to sar_filed
DELETE /aml/cases/{id}              hard delete (admin demo only)

Network intelligence (round-4, day-20)
--------------------------------------
GET    /aml/network/rules           thresholds + propagation params for auditors
POST   /aml/network/analyze         entity resolution + risk propagation + layout
POST   /aml/network/counterfactual  ablate entities, rescore, return deltas
POST   /aml/network/attribution     leave-one-counterparty-out per account
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import Body, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

import cases as case_store
import network as network_engine
import risk as risk_engine
import sanctions as sanctions_engine
import sar as sar_engine

ENGINE_VERSION = "titan-aml/1.3.0"

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


# ---------------------------------------------------------------------------
# Case management
# ---------------------------------------------------------------------------


class OpenCaseReq(BaseModel):
    account_report: Dict[str, Any]
    opened_by: Optional[str] = "TITAN-AUTOMATED"
    note: Optional[str] = None


class BulkOpenReq(BaseModel):
    score_response: Dict[str, Any]
    min_priority: Optional[str] = Field(
        default="medium",
        description="Skip accounts whose derived priority is below this band.",
    )
    opened_by: Optional[str] = "TITAN-AUTOMATED"


class TransitionReq(BaseModel):
    to_status: str = Field(
        ...,
        description="One of review | cleared | escalated | sar_filed | reopen",
    )
    actor: str = Field(default="TITAN-ANALYST", min_length=1)
    note: Optional[str] = None


class AssignReq(BaseModel):
    assignee: str = ""
    actor: str = Field(default="TITAN-ANALYST", min_length=1)


class NoteReq(BaseModel):
    body: str = Field(..., min_length=1)
    actor: str = Field(default="TITAN-ANALYST", min_length=1)


class FileSarReq(BaseModel):
    actor: str = Field(default="TITAN-ANALYST", min_length=1)
    analyst: Optional[str] = None  # SAR header name; falls back to actor
    note: Optional[str] = None


@app.get("/aml/cases")
def cases_list(
    status: Optional[str] = None,
    priority: Optional[str] = None,
    assignee: Optional[str] = None,
    account_id: Optional[str] = None,
    q: Optional[str] = None,
    sla: Optional[str] = None,
    include_closed: bool = True,
    limit: int = 200,
    offset: int = 0,
) -> Dict[str, Any]:
    return case_store.list_cases(
        status=status,
        priority=priority,
        assignee=assignee,
        account_id=account_id,
        q=q,
        sla=sla,
        include_closed=include_closed,
        limit=limit,
        offset=offset,
    )


@app.post("/aml/cases/open")
def cases_open(req: OpenCaseReq = Body(...)) -> Dict[str, Any]:
    try:
        case = case_store.open_case(
            req.account_report, opened_by=req.opened_by or "TITAN-AUTOMATED",
            note=req.note,
        )
        return {"ok": True, "case": case}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/aml/cases/bulk_open")
def cases_bulk_open(req: BulkOpenReq = Body(...)) -> Dict[str, Any]:
    try:
        out = case_store.bulk_open_from_score(
            req.score_response,
            min_priority=req.min_priority or "medium",
            opened_by=req.opened_by or "TITAN-AUTOMATED",
        )
        return {"ok": True, **out}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/aml/cases/stats")
def cases_stats() -> Dict[str, Any]:
    return {"ok": True, "engine": ENGINE_VERSION, **case_store.stats()}


@app.get("/aml/cases/assignees")
def cases_assignees() -> Dict[str, Any]:
    return {"ok": True, "assignees": case_store.assignees()}


@app.get("/aml/cases/{case_id}")
def cases_get(case_id: str) -> Dict[str, Any]:
    case = case_store.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="case not found")
    return {"ok": True, "case": case}


@app.post("/aml/cases/{case_id}/transition")
def cases_transition(case_id: str, req: TransitionReq = Body(...)) -> Dict[str, Any]:
    try:
        case = case_store.transition(
            case_id, to_status=req.to_status, actor=req.actor, note=req.note,
        )
        return {"ok": True, "case": case}
    except KeyError:
        raise HTTPException(status_code=404, detail="case not found")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/aml/cases/{case_id}/assign")
def cases_assign(case_id: str, req: AssignReq = Body(...)) -> Dict[str, Any]:
    try:
        case = case_store.assign(case_id, assignee=req.assignee, actor=req.actor)
        return {"ok": True, "case": case}
    except KeyError:
        raise HTTPException(status_code=404, detail="case not found")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/aml/cases/{case_id}/note")
def cases_note(case_id: str, req: NoteReq = Body(...)) -> Dict[str, Any]:
    try:
        event = case_store.add_note(case_id, actor=req.actor, body=req.body)
        return {"ok": True, "event": event}
    except KeyError:
        raise HTTPException(status_code=404, detail="case not found")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/aml/cases/{case_id}/sar")
def cases_file_sar(case_id: str, req: FileSarReq = Body(...)) -> Dict[str, Any]:
    case = case_store.get_case(case_id, with_events=False)
    if not case:
        raise HTTPException(status_code=404, detail="case not found")
    snapshot = (case.get("snapshot") or {})
    snapshot["account_id"] = case["account_id"]  # required by sar_engine
    sar_doc = sar_engine.render_sar(snapshot, analyst=req.analyst or req.actor)
    try:
        updated = case_store.attach_sar(case_id, sar=sar_doc, actor=req.actor)
        return {"ok": True, "case": updated, "sar": sar_doc}
    except KeyError:
        raise HTTPException(status_code=404, detail="case not found")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/aml/cases/{case_id}")
def cases_delete(case_id: str) -> Dict[str, Any]:
    if not case_store.delete_case(case_id):
        raise HTTPException(status_code=404, detail="case not found")
    return {"ok": True, "deleted": case_id}


# ---------------------------------------------------------------------------
# Network intelligence
# ---------------------------------------------------------------------------


class NetAnalyzeReq(BaseModel):
    transactions: List[Tx]
    weights: Optional[Dict[str, float]] = None
    sanctions_threshold: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    name_tau: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    counterparty_tau: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    score_response: Optional[Dict[str, Any]] = Field(
        default=None,
        description=(
            "Optional pre-computed /aml/score response. When present we skip"
            " re-scoring and consume it directly, so the network call is cheap."
        ),
    )


class NetCounterfactualReq(BaseModel):
    transactions: List[Tx]
    ablate: List[str] = Field(..., min_length=1, description="Entity ids to remove.")
    weights: Optional[Dict[str, float]] = None
    sanctions_threshold: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class NetAttributionReq(BaseModel):
    transactions: List[Tx]
    account_id: str = Field(..., min_length=1)
    weights: Optional[Dict[str, float]] = None
    sanctions_threshold: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    max_report: int = Field(default=8, ge=1, le=20)


@app.get("/aml/network/rules")
def network_rules() -> Dict[str, Any]:
    return network_engine.get_rules()


@app.post("/aml/network/analyze")
def network_analyze(req: NetAnalyzeReq = Body(...)) -> Dict[str, Any]:
    if not req.transactions:
        raise HTTPException(status_code=400, detail="transactions[] is empty")
    rows = [t.model_dump() for t in req.transactions]
    return {
        "ok": True,
        **network_engine.analyze(
            rows,
            score_response=req.score_response,
            weights=req.weights,
            sanctions_threshold=req.sanctions_threshold,
            name_tau=(req.name_tau if req.name_tau is not None else network_engine.NAME_TAU),
            counterparty_tau=(
                req.counterparty_tau
                if req.counterparty_tau is not None
                else network_engine.COUNTERPARTY_TAU
            ),
        ),
    }


@app.post("/aml/network/counterfactual")
def network_counterfactual(req: NetCounterfactualReq = Body(...)) -> Dict[str, Any]:
    if not req.transactions:
        raise HTTPException(status_code=400, detail="transactions[] is empty")
    rows = [t.model_dump() for t in req.transactions]
    return {
        "ok": True,
        **network_engine.counterfactual(
            rows,
            ablate_entity_ids=req.ablate,
            weights=req.weights,
            sanctions_threshold=req.sanctions_threshold,
        ),
    }


@app.post("/aml/network/attribution")
def network_attribution(req: NetAttributionReq = Body(...)) -> Dict[str, Any]:
    if not req.transactions:
        raise HTTPException(status_code=400, detail="transactions[] is empty")
    rows = [t.model_dump() for t in req.transactions]
    return {
        "ok": True,
        **network_engine.attribution(
            rows,
            account_id=req.account_id,
            weights=req.weights,
            sanctions_threshold=req.sanctions_threshold,
            max_report=req.max_report,
        ),
    }
