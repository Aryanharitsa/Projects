from fastapi import FastAPI, Body
from pydantic import BaseModel
from typing import List, Optional
import importlib.util, json, os
from pathlib import Path

app = FastAPI(title="Fintrace AML (TITAN)")

# --- Dynamic import of Fintrace scorer if present ---
ROOT = Path(__file__).resolve().parent
FINTRACE_DIR = ROOT / "fintrace"
score_case = None
try:
    score_path = FINTRACE_DIR / "ml" / "score_case.py"
    if score_path.exists():
        spec = importlib.util.spec_from_file_location("score_case", score_path)
        score_case = importlib.util.module_from_spec(spec); spec.loader.exec_module(score_case)
except Exception as e:
    score_case = None

class Tx(BaseModel):
    account_id: str
    counterparty: str
    amount: float
    timestamp: str
    channel: str
    geo: Optional[str] = None
    meta: Optional[dict] = None
    subject: Optional[str] = None

class ScoreReq(BaseModel):
    transactions: List[Tx]
    pattern_type: Optional[str] = "cycle"

@app.get("/healthz")
def health():
    return {"ok": True, "engine": "fintrace", "scorer_loaded": bool(score_case)}

@app.post("/aml/score")
def aml_score(req: ScoreReq = Body(...)):
    # If fintrace scorer exists and exposes score_case(case), try to call it.
    if score_case and hasattr(score_case, "score_case"):
        # Minimal graph case: nodes = unique accounts; edges = transfers
        acct = sorted({t.account_id for t in req.transactions} | {t.counterparty for t in req.transactions})
        idx = {a:i for i,a in enumerate(acct)}
        case = {
            "pattern_type": req.pattern_type,
            "nodes": [{"id": str(i)} for i,_ in enumerate(acct)],
            "edges": [{"source": str(idx[t.account_id]), "target": str(idx[t.counterparty])} for t in req.transactions]
        }
        try:
            result = score_case.score_case(case)
            return {"ok": True, "engine": "fintrace", "mode": "scorer", "node_map": acct, "result": result}
        except Exception as e:
            return {"ok": False, "engine": "fintrace", "mode": "scorer", "error": str(e)}

    # Fallback stub so the endpoint works today without the ML deps
    acct = sorted({t.account_id for t in req.transactions} | {t.counterparty for t in req.transactions})
    edges = [{"source": t.account_id, "target": t.counterparty, "amount": t.amount} for t in req.transactions]
    nodes = [{"id": a, "risk": (1.0 if any(x["amount"]>=100000 for x in edges if x["source"]==a) else 0.1)} for a in acct]
    return {"ok": True, "engine": "fintrace", "mode": "stub", "nodes": nodes, "edges": edges}
