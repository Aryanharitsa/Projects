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

Adverse-media OSINT (round-9, day-45)
-------------------------------------
GET  /aml/media/rules           corpus + engine knobs (auditor-facing)
POST /aml/media/screen          batch-screen names against the adverse-media corpus
GET  /aml/media/articles        browse the corpus (category/tier/q filters)
GET  /aml/media/articles/{id}   single article + severity/tier weights

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

Case-aware network surface (round-5, day-25)
--------------------------------------------
GET    /aml/cases/{id}/network              auto-runs analysis from the case's
                                            snapshotted neighbourhood (subgraph,
                                            attribution, "if cleared" deltas)
POST   /aml/cases/{id}/network/clearing     re-runs the clearing counterfactual
                                            with caller-supplied transactions
                                            (override path for the AML console)

Model validation / backtest (round-7, day-35)
---------------------------------------------
GET    /aml/backtest/sample        bundled labelled validation set (one-click demo)
POST   /aml/backtest               replay the engine against labelled outcomes →
                                   confusion matrix + threshold sweep + ROC AUC +
                                   per-detector discrimination + tuning verdict

Behavioral drift / anomaly (round-8, day-40)
--------------------------------------------
GET    /aml/drift/rules            weights + verdict bands + every tunable knob
GET    /aml/drift/sample           three-account demo (stable + mild + sleeper-burst)
POST   /aml/drift                  account-vs-self drift across 10 axes → verdict
                                   + driver ranking + change-point + per-cparty view

Peer Lens — peer-group anomaly (round-12, day-55)
-------------------------------------------------
GET    /aml/peer/rules             metric list, direction gates, cohort fallback chain
GET    /aml/peer/sample            bundled six-cohort demo portfolio
POST   /aml/peer/analyze           customer-vs-cohort outlier scoring across 9 axes →
                                   robust z-scores (MAD), top drivers, cohort context

Pulse — compliance officer's morning brief (round-13, day-60)
-------------------------------------------------------------
GET    /aml/pulse/rules            window bounds, signal weights, mood ladder
GET    /aml/pulse/sample           rich demo pulse from the bundled customer book
GET    /aml/pulse                  LIVE composer over persisted profiles + cases
GET    /aml/pulse/export.md        markdown brief (paste into Slack / email)

Lineage — temporal fund-flow tracer (round-14, day-65)
------------------------------------------------------
GET    /aml/lineage/rules          pattern thresholds + score weights + mood ladder
GET    /aml/lineage/sample         bundled 28-tx three-arm laundering demo
GET    /aml/lineage/seeds          curated seed-account picker for the sample
POST   /aml/lineage/trace          full trace with caller-supplied transactions
GET    /aml/lineage/export.md      markdown SAR §3 exhibit

Precedent — case-similarity kNN + Bayesian disposition prior (round-15, day-70)
-------------------------------------------------------------------------------
GET    /aml/precedent/rules              block weights + tunables + verdict ladder
GET    /aml/precedent/candidates         cases eligible as queries (open queue)
GET    /aml/precedent/case/{case_id}     top-k precedents + prior + recommendation
POST   /aml/precedent/seed               seed the case store with the demo portfolio
GET    /aml/precedent/export.md          markdown "precedent memo" for a case

Triage — cleared-case suppression + false-positive mining (round-16, day-75)
----------------------------------------------------------------------------
GET    /aml/triage/rules                 every constant + verdict ladder + detector list
GET    /aml/triage/profile               portfolio prior + per-factor stats + 9x9 matrix
GET    /aml/triage/candidates            open/review cases eligible as triage queries
GET    /aml/triage/case/{case_id}        per-case Bayesian suppression report + evidence
POST   /aml/triage/seed                  seed a FP-rich supplementary corpus for the demo
GET    /aml/triage/export.md             markdown triage memo (paste into a case note)
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

import backtest as backtest_engine
import cases as case_store
import drift as drift_engine
import lineage as lineage_engine
import media as media_engine
import network as network_engine
import peer as peer_engine
import precedent as precedent_engine
import profile as profile_engine
import pulse as pulse_engine
import risk as risk_engine
import sanctions as sanctions_engine
import sar as sar_engine
import triage as triage_engine
import typology as typology_engine

ENGINE_VERSION = "titan-aml/1.14.0"

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
# Adverse-media OSINT (round-9, day-45)
# ---------------------------------------------------------------------------


class MediaScreenReq(BaseModel):
    names: List[str] = Field(..., min_length=1)
    jurisdiction: Optional[str] = None
    similarity_floor: float = Field(
        default=media_engine.DEFAULT_SIMILARITY_FLOOR, ge=0.0, le=1.0,
        description="Fuzzy-match floor for entity-name matching against article mentions.",
    )
    half_life_days: float = Field(
        default=media_engine.DEFAULT_HALF_LIFE_DAYS, ge=30.0, le=3650.0,
        description="Recency half-life in days for exponential decay (default 365).",
    )
    top_k: int = Field(default=media_engine.DEFAULT_TOP_K, ge=1, le=40)


@app.get("/aml/media/rules")
def media_rules() -> Dict[str, Any]:
    return {
        "ok": True,
        "engine": ENGINE_VERSION,
        "corpus": media_engine.get_metadata(),
    }


@app.post("/aml/media/screen")
def media_screen(req: MediaScreenReq = Body(...)) -> Dict[str, Any]:
    results = media_engine.screen_batch(
        req.names,
        jurisdiction=req.jurisdiction,
        similarity_floor=req.similarity_floor,
        half_life_days=req.half_life_days,
        top_k=req.top_k,
    )
    grade_counts: Dict[str, int] = {}
    for r in results:
        grade_counts[r["grade"]] = grade_counts.get(r["grade"], 0) + 1
    return {
        "ok": True,
        "engine": ENGINE_VERSION,
        "corpus": media_engine.get_metadata(),
        "queried": len(req.names),
        "screened": len(results),
        "matched": sum(1 for r in results if r["hit_count"] > 0),
        "by_grade": grade_counts,
        "results": results,
    }


@app.get("/aml/media/articles")
def media_articles(
    category: Optional[str] = None,
    tier: Optional[int] = Query(default=None, ge=1, le=3),
    q: Optional[str] = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> Dict[str, Any]:
    rows = media_engine.list_articles(category=category, tier=tier, q=q, limit=limit)
    return {
        "ok": True,
        "engine": ENGINE_VERSION,
        "count": len(rows),
        "filters": {"category": category, "tier": tier, "q": q, "limit": limit},
        "articles": rows,
    }


@app.get("/aml/media/articles/{article_id}")
def media_article(article_id: str) -> Dict[str, Any]:
    article = media_engine.get_article(article_id)
    if not article:
        raise HTTPException(status_code=404, detail="article not found")
    return {"ok": True, "engine": ENGINE_VERSION, "article": article}


# ---------------------------------------------------------------------------
# Typology library (round-6, day-30)
# ---------------------------------------------------------------------------


class TypologyClassifyReq(BaseModel):
    account_report: Dict[str, Any]


@app.get("/aml/typologies")
def typology_library() -> Dict[str, Any]:
    """Auditor-facing dump of the typology library.

    Frontend reads this to render the rules page and to verify both
    sides are on the same engine version before showing the badge.
    """

    return {"ok": True, "engine": ENGINE_VERSION, **typology_engine.get_library()}


@app.post("/aml/typologies/classify")
def typology_classify(req: TypologyClassifyReq = Body(...)) -> Dict[str, Any]:
    """Classify one account report on its own — useful when re-running the
    classifier after a what-if weights override has reshuffled the
    factors. The shape mirrors ``account_report.typologies`` so callers
    can drop the result straight back into a report dict."""

    if not isinstance(req.account_report, dict) or "account_id" not in req.account_report:
        raise HTTPException(status_code=400, detail="account_report.account_id required")
    matches = typology_engine.classify(req.account_report)
    return {
        "ok": True,
        "engine": ENGINE_VERSION,
        "typology_engine": typology_engine.ENGINE_VERSION,
        "account_id": req.account_report.get("account_id"),
        "typologies": matches,
    }


# ---------------------------------------------------------------------------
# Model validation / backtest (round-7, day-35)
# ---------------------------------------------------------------------------


class BacktestReq(BaseModel):
    transactions: List[Tx]
    labels: Any = Field(
        ...,
        description=(
            "Ground-truth labels. Either a list of confirmed-suspicious "
            "account ids (every other scored account is treated as benign), "
            "or a map of account_id -> truthy that restricts the evaluation "
            "to adjudicated accounts only."
        ),
    )
    weights: Optional[Dict[str, float]] = Field(
        default=None,
        description="Candidate per-detector weight overrides to validate.",
    )
    beta: float = Field(
        default=backtest_engine.DEFAULT_BETA, gt=0.0, le=10.0,
        description="Fβ recall-weighting (compliance default 2.0).",
    )
    operating_threshold: float = Field(
        default=backtest_engine.DEFAULT_OPERATING_THRESHOLD, ge=0.0, le=100.0,
        description="The current production alert cut to benchmark against.",
    )
    sanctions_threshold: Optional[float] = Field(default=None, ge=0.0, le=1.0)


@app.get("/aml/backtest/sample")
def backtest_sample() -> Dict[str, Any]:
    """Bundled labelled validation set for the one-click backtest demo."""

    return {"ok": True, "engine": ENGINE_VERSION, **backtest_engine.get_sample()}


@app.post("/aml/backtest")
def run_backtest(req: BacktestReq = Body(...)) -> Dict[str, Any]:
    if not req.transactions:
        raise HTTPException(status_code=400, detail="transactions[] is empty")
    if not req.labels:
        raise HTTPException(status_code=400, detail="labels are required to backtest")
    rows = [t.model_dump() for t in req.transactions]
    threshold = (
        req.sanctions_threshold
        if req.sanctions_threshold is not None
        else risk_engine.SANCTIONS_HIT_THRESHOLD
    )
    return {
        "ok": True,
        "engine": ENGINE_VERSION,
        **backtest_engine.backtest(
            rows,
            req.labels,
            weights=req.weights,
            beta=req.beta,
            operating_threshold=req.operating_threshold,
            sanctions_threshold=threshold,
        ),
    }


# ---------------------------------------------------------------------------
# Behavioral drift / anomaly (round-8, day-40)
# ---------------------------------------------------------------------------


class DriftReq(BaseModel):
    transactions: List[Tx]
    account_id: Optional[str] = Field(
        default=None,
        description=(
            "If provided, drift is computed for this account only. "
            "Otherwise every account with enough txs is scored and "
            "ranked by drift."
        ),
    )
    baseline_fraction: float = Field(
        default=drift_engine.DEFAULT_BASELINE_FRACTION,
        gt=0.0,
        lt=1.0,
        description="Share of the timeline that constitutes the baseline window.",
    )
    split_at: Optional[str] = Field(
        default=None,
        description=(
            "Explicit ISO timestamp to split baseline vs current. "
            "Overrides `baseline_fraction` when set."
        ),
    )


@app.get("/aml/drift/rules")
def drift_rules() -> Dict[str, Any]:
    """Auditor view of the drift engine's tunables."""

    return {"ok": True, **drift_engine.get_rules()}


@app.get("/aml/drift/sample")
def drift_sample() -> Dict[str, Any]:
    """Bundled three-account demo dataset exercising every verdict band."""

    return drift_engine.sample_dataset()


@app.post("/aml/drift")
def run_drift(req: DriftReq = Body(...)) -> Dict[str, Any]:
    if not req.transactions:
        raise HTTPException(status_code=400, detail="transactions[] is empty")
    rows = [t.model_dump() for t in req.transactions]
    return drift_engine.analyze(
        rows,
        account_id=req.account_id,
        baseline_fraction=req.baseline_fraction,
        split_at=req.split_at,
    )


# ---------------------------------------------------------------------------
# Case management
# ---------------------------------------------------------------------------


class OpenCaseReq(BaseModel):
    account_report: Dict[str, Any]
    opened_by: Optional[str] = "TITAN-AUTOMATED"
    note: Optional[str] = None
    transactions: Optional[List[Tx]] = Field(
        default=None,
        description=(
            "Optional source transactions used to compute the account report."
            " When present, a 1-hop neighbourhood snapshot is persisted with"
            " the case so the case-detail network panel can re-run analysis"
            " without the caller having to re-supply the batch."
        ),
    )
    weights: Optional[Dict[str, float]] = None
    sanctions_threshold: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class BulkOpenReq(BaseModel):
    score_response: Dict[str, Any]
    min_priority: Optional[str] = Field(
        default="medium",
        description="Skip accounts whose derived priority is below this band.",
    )
    opened_by: Optional[str] = "TITAN-AUTOMATED"
    transactions: Optional[List[Tx]] = Field(
        default=None,
        description="Same as OpenCaseReq.transactions, applied per-case.",
    )
    weights: Optional[Dict[str, float]] = None
    sanctions_threshold: Optional[float] = Field(default=None, ge=0.0, le=1.0)


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
        txs_rows = [t.model_dump() for t in req.transactions] if req.transactions else None
        case = case_store.open_case(
            req.account_report,
            opened_by=req.opened_by or "TITAN-AUTOMATED",
            note=req.note,
            transactions=txs_rows,
            weights=req.weights,
            sanctions_threshold=req.sanctions_threshold,
        )
        return {"ok": True, "case": case}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/aml/cases/bulk_open")
def cases_bulk_open(req: BulkOpenReq = Body(...)) -> Dict[str, Any]:
    try:
        txs_rows = [t.model_dump() for t in req.transactions] if req.transactions else None
        out = case_store.bulk_open_from_score(
            req.score_response,
            min_priority=req.min_priority or "medium",
            opened_by=req.opened_by or "TITAN-AUTOMATED",
            transactions=txs_rows,
            weights=req.weights,
            sanctions_threshold=req.sanctions_threshold,
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


# ---------------------------------------------------------------------------
# Case-aware network panel (round-5, day-25)
# ---------------------------------------------------------------------------


class CaseNetClearReq(BaseModel):
    transactions: List[Tx]
    weights: Optional[Dict[str, float]] = None
    sanctions_threshold: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    hops: int = Field(default=1, ge=0, le=2)


@app.get("/aml/cases/{case_id}/network")
def cases_network(
    case_id: str,
    hops: int = Query(default=1, ge=0, le=2),
) -> Dict[str, Any]:
    """Auto-run network analysis from the case's persisted neighbourhood.

    Returns ``available=false`` with a reason field when the case was
    opened without a transactions snapshot (legacy cases or callers that
    didn't pass them). The frontend renders an empty-state with a hint
    in that scenario instead of a hard error.
    """
    case = case_store.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="case not found")
    snap = case_store.get_case_transactions(case_id)
    if not snap or not snap.get("transactions"):
        return {
            "ok": True,
            "available": False,
            "reason": (
                "this case was opened without a transactions snapshot — "
                "re-promote from the AML console with the source CSV "
                "attached, or POST /aml/cases/{id}/network/clearing with "
                "the batch in hand."
            ),
            "account_id": case["account_id"],
            "case_id": case_id,
        }
    panel = network_engine.case_panel(
        snap["transactions"],
        account_id=case["account_id"],
        weights=snap.get("weights"),
        sanctions_threshold=snap.get("sanctions_threshold"),
        hops=hops,
    )
    panel["case_id"] = case_id
    panel["snapshot_meta"] = {
        "tx_count": snap.get("tx_count", 0),
        "counterparty_count": snap.get("counterparty_count", 0),
        "created_at_iso": snap.get("created_at_iso"),
    }
    return panel


@app.post("/aml/cases/{case_id}/network/clearing")
def cases_network_clearing(
    case_id: str, req: CaseNetClearReq = Body(...),
) -> Dict[str, Any]:
    """Run the case's network panel using caller-supplied transactions.

    Use this from the AML console when the case has no persisted
    snapshot and the analyst still has the input batch in memory. The
    case_id is required for shape parity with the GET path.
    """
    case = case_store.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="case not found")
    if not req.transactions:
        raise HTTPException(status_code=400, detail="transactions[] is empty")
    rows = [t.model_dump() for t in req.transactions]
    panel = network_engine.case_panel(
        rows,
        account_id=case["account_id"],
        weights=req.weights,
        sanctions_threshold=req.sanctions_threshold,
        hops=req.hops,
    )
    panel["case_id"] = case_id
    panel["source"] = "client-supplied"
    return panel


# ---------------------------------------------------------------------------
# Customer Risk Profile (round-10, day-50)
# ---------------------------------------------------------------------------


class ProfileComputeReq(BaseModel):
    customer: Dict[str, Any]
    evidence: Optional[Dict[str, Any]] = None
    transactions: Optional[List[Tx]] = Field(
        default=None,
        description=(
            "Optional. When present, the engine runs the AML score + drift + "
            "network pipelines and builds the evidence blob automatically "
            "before composing the profile."
        ),
    )
    weights: Optional[Dict[str, float]] = None
    sanctions_threshold: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class ProfileRefreshReq(ProfileComputeReq):
    refreshed_by: Optional[str] = "TITAN-ANALYST"
    note: Optional[str] = None


class ProfileOverrideReq(BaseModel):
    locked_bucket: str = Field(..., description="One of low | medium | high | critical")
    justification: str = Field(..., min_length=4, max_length=600)
    actor: str = Field(default="TITAN-ANALYST", min_length=1)
    expires_iso: Optional[str] = None


class ProfileClearOverrideReq(BaseModel):
    actor: str = Field(default="TITAN-ANALYST", min_length=1)
    note: Optional[str] = None


@app.get("/aml/profile/rules")
def profile_rules() -> Dict[str, Any]:
    return {"ok": True, "engine": ENGINE_VERSION, **profile_engine.get_rules()}


@app.get("/aml/profile/sample")
def profile_sample() -> Dict[str, Any]:
    return {"ok": True, "engine": ENGINE_VERSION, **profile_engine.get_sample()}


@app.post("/aml/profile/seed")
def profile_seed(force: bool = False) -> Dict[str, Any]:
    return profile_engine.seed_sample(force=force)


@app.post("/aml/profile/compute")
def profile_compute(req: ProfileComputeReq = Body(...)) -> Dict[str, Any]:
    if not isinstance(req.customer, dict) or not req.customer.get("customer_id"):
        raise HTTPException(status_code=400, detail="customer.customer_id is required")
    evidence = req.evidence or {}
    if req.transactions:
        threshold = (
            req.sanctions_threshold
            if req.sanctions_threshold is not None
            else risk_engine.SANCTIONS_HIT_THRESHOLD
        )
        rows = [t.model_dump() for t in req.transactions]
        built = profile_engine.build_evidence(
            req.customer, rows, sanctions_threshold=threshold,
        )
        for k, v in built.items():
            evidence.setdefault(k, v)
    try:
        out = profile_engine.compute_profile(
            req.customer, evidence=evidence, weights_override=req.weights,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    out["ok"] = True
    return out


@app.post("/aml/profile/refresh")
def profile_refresh(req: ProfileRefreshReq = Body(...)) -> Dict[str, Any]:
    if not isinstance(req.customer, dict) or not req.customer.get("customer_id"):
        raise HTTPException(status_code=400, detail="customer.customer_id is required")
    evidence = req.evidence or {}
    if req.transactions:
        threshold = (
            req.sanctions_threshold
            if req.sanctions_threshold is not None
            else risk_engine.SANCTIONS_HIT_THRESHOLD
        )
        rows = [t.model_dump() for t in req.transactions]
        built = profile_engine.build_evidence(
            req.customer, rows, sanctions_threshold=threshold,
        )
        for k, v in built.items():
            evidence.setdefault(k, v)
    try:
        out = profile_engine.upsert_profile(
            req.customer,
            evidence=evidence,
            weights_override=req.weights,
            refreshed_by=req.refreshed_by or "TITAN-ANALYST",
            note=req.note,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True, "profile": out}


@app.get("/aml/profile/portfolio")
def profile_portfolio(
    bucket: Optional[str] = None,
    refresh_label: Optional[str] = None,
    domicile: Optional[str] = None,
    q: Optional[str] = None,
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> Dict[str, Any]:
    listed = profile_engine.list_profiles(
        bucket=bucket, refresh_label=refresh_label,
        domicile=domicile, q=q, limit=limit, offset=offset,
    )
    stats = profile_engine.portfolio_stats()
    return {"ok": True, "engine": ENGINE_VERSION, **listed, "stats": stats}


@app.get("/aml/profile/{customer_id}")
def profile_get(customer_id: str) -> Dict[str, Any]:
    out = profile_engine.get_profile(customer_id)
    if not out:
        raise HTTPException(status_code=404, detail="customer not found")
    return {"ok": True, "profile": out}


@app.post("/aml/profile/{customer_id}/override")
def profile_override(customer_id: str, req: ProfileOverrideReq = Body(...)) -> Dict[str, Any]:
    try:
        out = profile_engine.set_override(
            customer_id,
            locked_bucket=req.locked_bucket,
            justification=req.justification,
            actor=req.actor,
            expires_iso=req.expires_iso,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="customer not found")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True, "profile": out}


@app.post("/aml/profile/{customer_id}/clear_override")
def profile_clear_override(customer_id: str, req: ProfileClearOverrideReq = Body(...)) -> Dict[str, Any]:
    try:
        out = profile_engine.clear_override(customer_id, actor=req.actor, note=req.note)
    except KeyError:
        raise HTTPException(status_code=404, detail="customer not found")
    return {"ok": True, "profile": out}


@app.delete("/aml/profile/{customer_id}")
def profile_delete(customer_id: str) -> Dict[str, Any]:
    deleted = profile_engine.delete_profile(customer_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="customer not found")
    return {"ok": True, "deleted": True, "customer_id": customer_id}


# ---------------------------------------------------------------------------
# Peer Lens — peer-group anomaly studio (round-12, day-55)
# ---------------------------------------------------------------------------


class PeerCustomerIn(BaseModel):
    customer_id: str = Field(..., min_length=1)
    display_name: Optional[str] = None
    industry: Optional[str] = "unknown"
    domicile: Optional[str] = None
    accounts: Optional[List[str]] = None


class PeerAnalyzeReq(BaseModel):
    customers: List[PeerCustomerIn] = Field(..., min_length=1)
    transactions: List[Tx] = Field(default_factory=list)


@app.get("/aml/peer/rules")
def peer_rules() -> Dict[str, Any]:
    return {"ok": True, "engine": ENGINE_VERSION, **peer_engine.get_rules()}


@app.get("/aml/peer/sample")
def peer_sample() -> Dict[str, Any]:
    sample = peer_engine.get_sample()
    return {"ok": True, "engine": ENGINE_VERSION, **sample}


@app.post("/aml/peer/analyze")
def peer_analyze(req: PeerAnalyzeReq = Body(...)) -> Dict[str, Any]:
    customers = [c.model_dump() for c in req.customers]
    transactions = [t.model_dump() for t in req.transactions]
    out = peer_engine.analyze(customers, transactions)
    return out


# ---------------------------------------------------------------------------
# Pulse — compliance officer's morning brief (round-13, day-60)
# ---------------------------------------------------------------------------


@app.get("/aml/pulse/rules")
def pulse_rules() -> Dict[str, Any]:
    return {"ok": True, "engine": ENGINE_VERSION, **pulse_engine.get_rules()}


@app.get("/aml/pulse/sample")
def pulse_sample(
    window_days: int = Query(default=pulse_engine.DEFAULT_WINDOW_DAYS,
                             ge=pulse_engine.MIN_WINDOW_DAYS,
                             le=pulse_engine.MAX_WINDOW_DAYS),
) -> Dict[str, Any]:
    """Rich demo pulse from the bundled customer book + synthetic priors.

    Used by the frontend on first load so the surface lights up without
    the analyst having to seed the store first.
    """
    report = pulse_engine.get_sample_pulse(window_days=window_days)
    return {"ok": True, **report.to_dict()}


@app.get("/aml/pulse")
def pulse_live(
    window_days: int = Query(default=pulse_engine.DEFAULT_WINDOW_DAYS,
                             ge=pulse_engine.MIN_WINDOW_DAYS,
                             le=pulse_engine.MAX_WINDOW_DAYS),
) -> Dict[str, Any]:
    """LIVE pulse — composes over the persisted profile + cases stores.

    Falls back to the sample pulse when the profile store is empty so the
    surface never renders a depressing "no data" state. The response
    carries ``source: live|sample`` so the UI can hint at the difference.
    """
    report = pulse_engine.build_live(window_days=window_days)
    if report.portfolio_size == 0:
        report = pulse_engine.get_sample_pulse(window_days=window_days)
        return {"ok": True, "source": "sample", **report.to_dict()}
    return {"ok": True, "source": "live", **report.to_dict()}


@app.get("/aml/pulse/export.md", response_class=None)
def pulse_export_md(
    window_days: int = Query(default=pulse_engine.DEFAULT_WINDOW_DAYS,
                             ge=pulse_engine.MIN_WINDOW_DAYS,
                             le=pulse_engine.MAX_WINDOW_DAYS),
    source: str = Query(default="auto", pattern="^(auto|live|sample)$"),
):
    from fastapi.responses import PlainTextResponse
    if source == "sample":
        report = pulse_engine.get_sample_pulse(window_days=window_days)
    elif source == "live":
        report = pulse_engine.build_live(window_days=window_days)
    else:
        report = pulse_engine.build_live(window_days=window_days)
        if report.portfolio_size == 0:
            report = pulse_engine.get_sample_pulse(window_days=window_days)
    return PlainTextResponse(
        pulse_engine.to_markdown(report),
        media_type="text/markdown; charset=utf-8",
    )


# ---------------------------------------------------------------------------
# Lineage — temporal fund-flow tracer (round-14, day-65)
# ---------------------------------------------------------------------------


class LineageTraceReq(BaseModel):
    transactions: List[Dict[str, Any]] = Field(default_factory=list)
    seed: str = Field(..., min_length=1)
    direction: str = Field(default="both", pattern="^(forward|backward|both)$")
    max_depth: int = Field(
        default=lineage_engine.DEFAULT_MAX_DEPTH,
        ge=lineage_engine.MIN_MAX_DEPTH,
        le=lineage_engine.MAX_MAX_DEPTH,
    )
    window_days: int = Field(
        default=lineage_engine.DEFAULT_WINDOW_DAYS,
        ge=lineage_engine.MIN_WINDOW_DAYS,
        le=lineage_engine.MAX_WINDOW_DAYS,
    )


@app.get("/aml/lineage/rules")
def lineage_rules() -> Dict[str, Any]:
    return {"ok": True, "engine": ENGINE_VERSION, **lineage_engine.get_rules()}


@app.get("/aml/lineage/seeds")
def lineage_seeds() -> Dict[str, Any]:
    return {
        "ok": True,
        "engine": ENGINE_VERSION,
        "seeds": lineage_engine.sample_seed_choices(),
    }


@app.get("/aml/lineage/sample")
def lineage_sample(
    seed: Optional[str] = Query(default=None),
    direction: str = Query(default="both", pattern="^(forward|backward|both)$"),
    max_depth: int = Query(
        default=lineage_engine.DEFAULT_MAX_DEPTH,
        ge=lineage_engine.MIN_MAX_DEPTH,
        le=lineage_engine.MAX_MAX_DEPTH,
    ),
    window_days: int = Query(
        default=lineage_engine.DEFAULT_WINDOW_DAYS,
        ge=lineage_engine.MIN_WINDOW_DAYS,
        le=lineage_engine.MAX_WINDOW_DAYS,
    ),
) -> Dict[str, Any]:
    """Sample lineage from the bundled 28-tx three-arm laundering fixture."""
    report = lineage_engine.get_sample_trace(
        seed=seed, direction=direction, max_depth=max_depth, window_days=window_days,
    )
    return {"ok": True, **report.to_dict()}


@app.post("/aml/lineage/trace")
def lineage_trace(req: LineageTraceReq) -> Dict[str, Any]:
    """Trace fund-flow lineage from caller-supplied transactions."""
    try:
        report = lineage_engine.compute_lineage(
            transactions=req.transactions,
            seed=req.seed,
            direction=req.direction,
            max_depth=req.max_depth,
            window_days=req.window_days,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return {"ok": True, **report.to_dict()}


@app.get("/aml/lineage/export.md", response_class=None)
def lineage_export_md(
    seed: Optional[str] = Query(default=None),
    direction: str = Query(default="both", pattern="^(forward|backward|both)$"),
    max_depth: int = Query(
        default=lineage_engine.DEFAULT_MAX_DEPTH,
        ge=lineage_engine.MIN_MAX_DEPTH,
        le=lineage_engine.MAX_MAX_DEPTH,
    ),
    window_days: int = Query(
        default=lineage_engine.DEFAULT_WINDOW_DAYS,
        ge=lineage_engine.MIN_WINDOW_DAYS,
        le=lineage_engine.MAX_WINDOW_DAYS,
    ),
):
    """Paste-able SAR §3 exhibit (markdown) — defaults to the bundled sample."""
    from fastapi.responses import PlainTextResponse
    report = lineage_engine.get_sample_trace(
        seed=seed, direction=direction, max_depth=max_depth, window_days=window_days,
    )
    return PlainTextResponse(
        lineage_engine.to_markdown(report),
        media_type="text/markdown; charset=utf-8",
    )


# ---------------------------------------------------------------------------
# Precedent — case-similarity kNN + Bayesian disposition prior (round-15, day-70)
# ---------------------------------------------------------------------------


@app.get("/aml/precedent/rules")
def precedent_rules() -> Dict[str, Any]:
    return {"ok": True, "engine": ENGINE_VERSION, **precedent_engine.get_rules()}


@app.get("/aml/precedent/candidates")
def precedent_candidates(
    limit: int = Query(default=100, ge=1, le=500),
    include_closed: bool = Query(default=False),
) -> Dict[str, Any]:
    """List cases the analyst can pick as a Precedent *query*.

    By default only open/review/escalated cases show up — those are the
    ones the analyst is actually deciding on.  Auditors can flip
    ``include_closed`` to trace back what a closed case's precedents
    were at the time.
    """
    candidates = precedent_engine.list_query_candidates(
        limit=limit, include_closed=include_closed,
    )
    return {
        "ok": True,
        "engine": ENGINE_VERSION,
        "count": len(candidates),
        "include_closed": include_closed,
        "candidates": candidates,
    }


@app.get("/aml/precedent/case/{case_id}")
def precedent_case(
    case_id: str,
    k: int = Query(default=precedent_engine.DEFAULT_K,
                   ge=1, le=precedent_engine.MAX_K),
    min_sim: float = Query(default=precedent_engine.MIN_SIM_FLOOR,
                           ge=0.0, le=1.0),
) -> Dict[str, Any]:
    try:
        report = precedent_engine.compute_for_case(case_id, k=k, min_sim=min_sim)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"case not found: {case_id}")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return {"ok": True, "engine": ENGINE_VERSION, **report.to_dict()}


@app.post("/aml/precedent/seed")
def precedent_seed(force: bool = Query(default=False)) -> Dict[str, Any]:
    result = precedent_engine.seed_sample_cases(force=force)
    return {"ok": True, "engine": ENGINE_VERSION, **result}


@app.get("/aml/precedent/export.md", response_class=None)
def precedent_export(
    case_id: str = Query(..., min_length=1),
    k: int = Query(default=precedent_engine.DEFAULT_K,
                   ge=1, le=precedent_engine.MAX_K),
    min_sim: float = Query(default=precedent_engine.MIN_SIM_FLOOR,
                           ge=0.0, le=1.0),
):
    from fastapi.responses import PlainTextResponse
    try:
        report = precedent_engine.compute_for_case(case_id, k=k, min_sim=min_sim)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"case not found: {case_id}")
    return PlainTextResponse(
        precedent_engine.to_markdown(report),
        media_type="text/markdown; charset=utf-8",
    )


# ---------------------------------------------------------------------------
# Triage — cleared-case suppression engine (round-16, day-75)
# ---------------------------------------------------------------------------


@app.get("/aml/triage/rules")
def triage_rules() -> Dict[str, Any]:
    """Auditor-facing dump — every constant driving the engine plus the
    verdict ladder.  ``/aml/triage/*`` reads only from this table."""
    return {"ok": True, "engine": ENGINE_VERSION, **triage_engine.get_rules()}


@app.get("/aml/triage/profile")
def triage_profile() -> Dict[str, Any]:
    """Portfolio-wide suppression profile.

    Returns the base clearance rate, per-detector clearance stats, the
    9x9 factor-pair suppression matrix, and the top noise / signal
    combos.  The /triage surface uses this to paint the portfolio view
    before an analyst picks a query case.
    """
    return {"ok": True, "engine": ENGINE_VERSION,
            **triage_engine.corpus_summary()}


@app.get("/aml/triage/candidates")
def triage_candidates(
    limit: int = Query(default=100, ge=1, le=500),
    include_closed: bool = Query(default=False),
) -> Dict[str, Any]:
    """Cases eligible as triage queries.  By default only open /
    review / escalated — analysts triage what's on their desk, not
    what's already closed."""
    picks = triage_engine.candidates(
        limit=limit, include_closed=include_closed,
    )
    return {
        "ok": True,
        "engine": ENGINE_VERSION,
        "count": len(picks),
        "include_closed": include_closed,
        "candidates": picks,
    }


@app.get("/aml/triage/case/{case_id}")
def triage_case(case_id: str) -> Dict[str, Any]:
    try:
        report = triage_engine.triage_for_case(case_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"case not found: {case_id}")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return {"ok": True, **report}


@app.post("/aml/triage/seed")
def triage_seed(force: bool = Query(default=False)) -> Dict[str, Any]:
    """Seed the case store with the FP-rich supplementary corpus.

    Idempotent — skips when the store already carries ≥ 20 terminal
    cases unless ``force`` is set.  Complements the Precedent seed;
    running both gives the miner a richer signal-vs-noise spectrum.
    """
    result = triage_engine.seed_sample_cases(force=force)
    return {"ok": True, "engine": ENGINE_VERSION, **result}


@app.get("/aml/triage/export.md", response_class=None)
def triage_export(case_id: str = Query(..., min_length=1)):
    from fastapi.responses import PlainTextResponse
    try:
        report = triage_engine.triage_for_case(case_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"case not found: {case_id}")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return PlainTextResponse(
        triage_engine.to_markdown(report),
        media_type="text/markdown; charset=utf-8",
    )
