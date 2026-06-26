"""Drift Lab — Output Stability & Variance Tester.

Every other quality surface in the playground perturbs *something* about the
call and measures the impact:

* **Adversary** changes the *input* (typos, structural shuffles, injections)
  and asks "does my prompt hold up when reality is messy?"
* **Showdown** changes the *prompt* (champion vs challenger) and asks "is
  this rewrite actually better — at a statistically meaningful threshold?"
* **Suites / Rubrics / Judge** change the *test case* (case A vs B vs …) and
  ask "how well does this prompt cover the cases I care about?"

None of them touch the question every engineer who ships an LLM with
``temperature > 0`` runs into: *if I call this exact prompt eight times in a
row against this exact model, how non-deterministic is the answer?*

That question matters in production. When you ship a customer-support
prompt and one user gets a refund offer while another gets a polite shrug
from the same call, your reliability isn't a function of model quality — it
is a function of model *consistency at this temperature*. Drift Lab is the
surface that measures it.

Given a prompt + an input + a target ``(provider, model, temperature)``,
``run_drift`` issues ``n_replays`` parallel calls (defaults: 8) and turns
the bag of responses into structured signal:

* **Lexical stability** — mean pairwise Jaccard similarity over 3-gram
  word-shingles. 100 = every reply lexically identical, 0 = no overlap.
* **Length stability** — ``100 · (1 − clip(σ(token_count) / μ(token_count),
  0, 1))``. A response that's 80 tokens one call and 800 tokens the next
  reads as *unreliable* even if the words overlap.
* **Latency stability** — same CV-floor trick over response time. Models
  whose wall-clock time swings 5× call-to-call burn caller patience even
  when the text is fine.
* **Composite Stability Score** (0–100) =
  ``0.55·lexical + 0.30·length + 0.15·latency``.
  Bands: ``Steady ≥ 80 · Consistent ≥ 60 · Drifty ≥ 40 · Wild < 40``.

Beyond the headline score, the engine returns *texture*:

* **Pairwise similarity matrix** — full ``n×n`` Jaccard table so the UI can
  paint a heatmap and the user can see *which* two replays diverged.
* **Clusters** — single-link agglomerative grouping at a configurable
  threshold (default 0.55). ``n_clusters`` collapses the matrix into a
  one-number answer: 1 = monolithic ("the model always says the same
  thing"), N = chaos ("every reply lives in its own cluster").
* **Medoid** — the single response with the highest mean similarity to all
  other replies. This is the *canonical* answer — the one most likely to
  represent what a user will actually see.
* **Variance type** — categorical roll-up:
    - ``Cosmetic``  — lex ≥ 70 and length-CV < 0.20 → "same answer,
      slightly reworded".
    - ``Verbose``   — lex ≥ 50 and length-CV ≥ 0.20 → "same answer, length
      varies — verbosity drift".
    - ``Substantive`` — lex < 50 → "different answers altogether".
    - ``Steady``    — lex ≥ 90 and length-CV < 0.08 → "boringly stable".

Like Adversary and Showdown, the whole loop runs in ``dryrun`` mode without
any API keys — deterministic synthetic responses with controlled drift, so
the demo lights up the moment the page loads.

Public surface (kept narrow):
``create_drift``, ``list_drifts``, ``get_drift``, ``delete_drift``,
``run_drift``, ``seed_demo``, ``stats``, ``defaults``.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from typing import Any, Dict, List, Optional, Tuple

from src import history
from src.pricing import estimate_cost

_DB_LOCK = history._DB_LOCK  # noqa: SLF001 — share the cross-table sqlite lock


@contextmanager
def _conn():
    with history._conn() as con:  # noqa: SLF001
        yield con


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS drift_runs (
    id                 TEXT PRIMARY KEY,
    name               TEXT NOT NULL,
    description        TEXT,
    system_prompt      TEXT,
    user_prompt        TEXT NOT NULL,
    candidate_provider TEXT,
    candidate_model    TEXT,
    temperature        REAL NOT NULL DEFAULT 0.7,
    top_p              REAL NOT NULL DEFAULT 1.0,
    n_replays          INTEGER NOT NULL DEFAULT 8,
    cluster_threshold  REAL NOT NULL DEFAULT 0.55,
    status             TEXT NOT NULL,
    stability_score    REAL,
    band               TEXT,
    lexical_score      REAL,
    length_score       REAL,
    latency_score      REAL,
    mean_similarity    REAL,
    min_similarity     REAL,
    length_cv          REAL,
    latency_cv         REAL,
    n_clusters         INTEGER,
    variance_type      TEXT,
    medoid_index       INTEGER,
    total_cost         REAL NOT NULL DEFAULT 0,
    duration           REAL NOT NULL DEFAULT 0,
    dryrun             INTEGER NOT NULL DEFAULT 0,
    summary_json       TEXT,
    created_at         REAL NOT NULL,
    updated_at         REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS drift_samples (
    id            TEXT PRIMARY KEY,
    drift_id      TEXT NOT NULL,
    replay_index  INTEGER NOT NULL,
    response      TEXT NOT NULL,
    input_tokens  INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    cost_usd      REAL NOT NULL DEFAULT 0,
    latency       REAL NOT NULL DEFAULT 0,
    cluster_id    INTEGER,
    mean_sim      REAL,
    status        TEXT NOT NULL,
    error         TEXT,
    created_at    REAL NOT NULL,
    FOREIGN KEY (drift_id) REFERENCES drift_runs(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_drift_runs_updated ON drift_runs(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_drift_runs_status  ON drift_runs(status);
CREATE INDEX IF NOT EXISTS idx_drift_samples_run  ON drift_samples(drift_id);
"""


def init_db() -> None:
    with _DB_LOCK, _conn() as con:
        con.executescript(_SCHEMA)


def _now() -> float:
    return time.time()


# ---------------------------------------------------------------------------
# Constants & weights — exposed via /defaults so the UI stays in sync.
# ---------------------------------------------------------------------------

DEFAULT_N_REPLAYS = 8
MAX_N_REPLAYS = 16
MIN_N_REPLAYS = 3

DEFAULT_TEMPERATURE = 0.7
DEFAULT_TOP_P = 1.0
DEFAULT_CLUSTER_THRESHOLD = 0.55

# Composite-score blend.
W_LEXICAL = 0.55
W_LENGTH = 0.30
W_LATENCY = 0.15

# Variance-type cut-offs. (lex on 0..100, length_cv unitless.)
COSMETIC_LEX_FLOOR = 70.0
STEADY_LEX_FLOOR = 90.0
STEADY_CV_CEIL = 0.08
LOW_CV_CEIL = 0.20
SUBSTANTIVE_LEX_CEIL = 50.0

BAND_THRESHOLDS = (
    ("Steady", 80.0),
    ("Consistent", 60.0),
    ("Drifty", 40.0),
    ("Wild", 0.0),
)

BAND_HUES = {
    "Steady": "#22c55e",
    "Consistent": "#84cc16",
    "Drifty": "#f59e0b",
    "Wild": "#ef4444",
    "—": "#94a3b8",
}

VARIANCE_TYPE_HUES = {
    "Steady": "#22c55e",
    "Cosmetic": "#06b6d4",
    "Verbose": "#a855f7",
    "Substantive": "#ef4444",
    "—": "#94a3b8",
}

VARIANCE_TYPE_BLURB = {
    "Steady": "Boringly stable — replays read near-identical.",
    "Cosmetic": "Same answer, slightly reworded across calls.",
    "Verbose": "Same gist, but the model's verbosity drifts call-to-call.",
    "Substantive": "Replays disagree on the substance, not just the wording.",
    "—": "No replays produced a measurable response.",
}


def defaults() -> Dict[str, Any]:
    """Public defaults — drives the UI sliders / pickers and lets clients
    reconstruct the composite formula without hard-coding it."""
    return {
        "n_replays": {"default": DEFAULT_N_REPLAYS, "min": MIN_N_REPLAYS, "max": MAX_N_REPLAYS},
        "temperature": {"default": DEFAULT_TEMPERATURE, "min": 0.0, "max": 2.0, "step": 0.05},
        "top_p": {"default": DEFAULT_TOP_P, "min": 0.0, "max": 1.0, "step": 0.05},
        "cluster_threshold": {
            "default": DEFAULT_CLUSTER_THRESHOLD,
            "min": 0.2, "max": 0.95, "step": 0.05,
        },
        "weights": {
            "lexical": W_LEXICAL,
            "length": W_LENGTH,
            "latency": W_LATENCY,
        },
        "bands": [
            {"name": "Steady",     "floor": 80.0, "hue": BAND_HUES["Steady"]},
            {"name": "Consistent", "floor": 60.0, "hue": BAND_HUES["Consistent"]},
            {"name": "Drifty",     "floor": 40.0, "hue": BAND_HUES["Drifty"]},
            {"name": "Wild",       "floor":  0.0, "hue": BAND_HUES["Wild"]},
        ],
        "variance_types": [
            {"name": k, "hue": VARIANCE_TYPE_HUES[k], "blurb": VARIANCE_TYPE_BLURB[k]}
            for k in ("Steady", "Cosmetic", "Verbose", "Substantive")
        ],
    }


# ---------------------------------------------------------------------------
# Text utilities — shingling, jaccard, clustering
# ---------------------------------------------------------------------------

_WORD_RE = re.compile(r"[A-Za-z0-9]+")


def _tokens(text: str) -> List[str]:
    return [t.lower() for t in _WORD_RE.findall(text or "")]


def _shingles(text: str, n: int = 3) -> set:
    """N-gram word shingles. Fall back to unigrams if the doc is too short
    (otherwise short answers like "yes." have an empty shingle set and
    Jaccard would divide by zero)."""
    toks = _tokens(text)
    if len(toks) < n:
        return set(toks)
    return {" ".join(toks[i : i + n]) for i in range(len(toks) - n + 1)}


def _jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    if union == 0:
        return 1.0
    return inter / union


def _pairwise_similarity(samples: List[Dict[str, Any]]) -> List[List[float]]:
    """Full n×n Jaccard table (symmetric, diagonal = 1.0)."""
    shings = [_shingles(s.get("response") or "") for s in samples]
    n = len(samples)
    out: List[List[float]] = [[0.0] * n for _ in range(n)]
    for i in range(n):
        out[i][i] = 1.0
        for j in range(i + 1, n):
            sim = round(_jaccard(shings[i], shings[j]), 4)
            out[i][j] = sim
            out[j][i] = sim
    return out


def _single_link_cluster(matrix: List[List[float]], threshold: float) -> List[int]:
    """Connected components on the similarity graph thresholded at
    ``threshold``. Returns a per-sample cluster id (0..k-1), assigned in
    *first-touch* order so cluster 0 contains sample 0 and a stable label
    helps the UI."""
    n = len(matrix)
    if n == 0:
        return []
    cluster = [-1] * n
    next_id = 0
    for start in range(n):
        if cluster[start] != -1:
            continue
        cluster[start] = next_id
        stack = [start]
        while stack:
            cur = stack.pop()
            row = matrix[cur]
            for j in range(n):
                if cluster[j] != -1:
                    continue
                if row[j] >= threshold:
                    cluster[j] = next_id
                    stack.append(j)
        next_id += 1
    return cluster


def _mean(xs: List[float]) -> Optional[float]:
    vals = [float(v) for v in xs if v is not None]
    if not vals:
        return None
    return sum(vals) / len(vals)


def _std(xs: List[float]) -> Optional[float]:
    vals = [float(v) for v in xs if v is not None]
    if len(vals) < 2:
        return 0.0 if vals else None
    m = sum(vals) / len(vals)
    var = sum((v - m) ** 2 for v in vals) / (len(vals) - 1)
    return math.sqrt(var)


def _cv(xs: List[float]) -> Optional[float]:
    """Coefficient of variation σ/μ. Returns 0 if μ ≈ 0 (no signal to vary
    around). None if no samples."""
    m = _mean(xs)
    if m is None:
        return None
    if abs(m) < 1e-9:
        return 0.0
    s = _std(xs) or 0.0
    return s / abs(m)


# ---------------------------------------------------------------------------
# Composite scoring
# ---------------------------------------------------------------------------

def _band_for(score: Optional[float]) -> str:
    if score is None:
        return "—"
    for name, floor in BAND_THRESHOLDS:
        if score >= floor:
            return name
    return "Wild"


def _classify_variance(lexical: Optional[float], length_cv: Optional[float]) -> str:
    """First-match-wins ladder.

    The order matters: we test the ``Steady`` floor before ``Cosmetic`` so a
    truly identical batch (lex ≥ 90, CV ≤ 0.08) reads as ``Steady`` and a
    merely reworded batch (lex ≥ 70, CV < 0.20) reads as ``Cosmetic`` —
    distinct because the *user-visible behaviour* differs (rewording is
    cheap drift, verbosity drift might leak into UI sizing, substantive
    drift is a correctness problem).
    """
    if lexical is None or length_cv is None:
        return "—"
    if lexical >= STEADY_LEX_FLOOR and length_cv <= STEADY_CV_CEIL:
        return "Steady"
    if lexical < SUBSTANTIVE_LEX_CEIL:
        return "Substantive"
    if length_cv >= LOW_CV_CEIL:
        return "Verbose"
    if lexical >= COSMETIC_LEX_FLOOR:
        return "Cosmetic"
    # Mid-zone fall-through: neither cosmetic nor verbose — call it Cosmetic
    # but the lower band will already flag the score.
    return "Cosmetic"


def _composite(
    lex_score: Optional[float],
    len_score: Optional[float],
    lat_score: Optional[float],
) -> Optional[float]:
    parts = []
    weights_sum = 0.0
    if lex_score is not None:
        parts.append(W_LEXICAL * lex_score)
        weights_sum += W_LEXICAL
    if len_score is not None:
        parts.append(W_LENGTH * len_score)
        weights_sum += W_LENGTH
    if lat_score is not None:
        parts.append(W_LATENCY * lat_score)
        weights_sum += W_LATENCY
    if not parts or weights_sum <= 0:
        return None
    # Renormalise — if one axis is missing the others still produce a sane
    # number rather than collapsing to 0.
    return sum(parts) / weights_sum


# ---------------------------------------------------------------------------
# Live + dryrun replay engines
# ---------------------------------------------------------------------------

def _live_one_call(
    *,
    idx: int,
    cand,
    candidate_model: str,
    messages: List[Dict[str, str]],
    parameters: Dict[str, Any],
) -> Dict[str, Any]:
    t0 = time.time()
    try:
        resp = cand.make_request(candidate_model, messages, parameters=parameters)
    except Exception as exc:  # noqa: BLE001
        return {
            "replay_index": idx,
            "response": "",
            "input_tokens": 0,
            "output_tokens": 0,
            "cost_usd": 0.0,
            "latency": round(time.time() - t0, 3),
            "status": "failed",
            "error": f"candidate call failed: {exc}",
        }
    err = resp.get("error")
    if resp.get("status") != "success" or (isinstance(err, dict) and err):
        msg = err.get("message") if isinstance(err, dict) else (err or "upstream error")
        return {
            "replay_index": idx,
            "response": "",
            "input_tokens": 0,
            "output_tokens": 0,
            "cost_usd": 0.0,
            "latency": round(time.time() - t0, 3),
            "status": "failed",
            "error": str(msg),
        }
    content = (resp.get("content") or "").strip()
    in_tok = int(resp.get("input_tokens") or 0)
    out_tok = int(resp.get("output_tokens") or 0)
    return {
        "replay_index": idx,
        "response": content,
        "input_tokens": in_tok,
        "output_tokens": out_tok,
        "cost_usd": float(estimate_cost(candidate_model, in_tok, out_tok) or 0.0),
        "latency": round(time.time() - t0, 3),
        "status": "success",
        "error": None,
    }


def _live_replays(
    *,
    system_prompt: str,
    user_prompt: str,
    candidate_provider: str,
    candidate_model: str,
    temperature: float,
    top_p: float,
    n_replays: int,
    provider_factory,
    parallel: int = 4,
) -> List[Dict[str, Any]]:
    cand = provider_factory.create_provider(candidate_provider)
    if not cand:
        return [{
            "replay_index": 0,
            "response": "",
            "input_tokens": 0,
            "output_tokens": 0,
            "cost_usd": 0.0,
            "latency": 0.0,
            "status": "failed",
            "error": f"candidate provider '{candidate_provider}' not available",
        }]
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": user_prompt})
    parameters = {"temperature": float(temperature), "top_p": float(top_p)}
    out: List[Dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max(1, min(parallel, 8))) as pool:
        futures = [
            pool.submit(
                _live_one_call,
                idx=i,
                cand=cand,
                candidate_model=candidate_model,
                messages=messages,
                parameters=parameters,
            )
            for i in range(n_replays)
        ]
        for fut in as_completed(futures):
            out.append(fut.result())
    out.sort(key=lambda r: r["replay_index"])
    return out


# ----- Dryrun synthesis -----------------------------------------------------

_DRY_BASELINES = [
    "The answer depends on the user's intent, but the most likely path is to acknowledge the issue, "
    "explain the cause briefly, and offer a concrete next step the user can take in the product. "
    "Keep the tone calm and avoid jargon.",
    "Here is a two-sentence response: acknowledge the user's concern, then offer the next concrete "
    "action they can take. Keep the response short, friendly, and free of jargon so the customer "
    "feels heard.",
]

_DRY_SYNONYMS = {
    "answer": ["reply", "response", "message"],
    "issue": ["problem", "concern", "matter"],
    "concrete": ["specific", "actionable", "clear"],
    "calm": ["measured", "warm", "steady"],
    "user": ["customer", "person", "reader"],
    "jargon": ["technical terms", "buzzwords", "complex words"],
    "briefly": ["in a sentence", "quickly", "succinctly"],
}


def _dry_response_for(
    *,
    seed: str,
    idx: int,
    temperature: float,
) -> str:
    """Deterministic synthetic response with controllable drift.

    ``temperature`` drives how aggressively we (a) swap synonyms, (b) jiggle
    length by appending / pruning sentences, (c) reorder clauses. The
    ``idx``-th call is reproducible from the same ``seed`` so the demo
    renders the same headline every page-load.
    """
    base_idx = int(hashlib.sha1((seed + ":base").encode()).hexdigest()[:4], 16) % len(_DRY_BASELINES)
    body = _DRY_BASELINES[base_idx]
    # ---- (a) synonym swaps — frequency scales with temperature
    swap_budget = int(round(min(0.95, temperature) * 5))
    h = hashlib.sha1((seed + f":{idx}").encode()).digest()
    pos = 0
    if swap_budget > 0:
        tokens = body.split()
        for k in range(swap_budget):
            byte = h[(k + pos) % len(h)]
            for word, options in _DRY_SYNONYMS.items():
                # Probabilistic swap, biased by temperature
                if word in tokens:
                    if byte % 7 < int(round(temperature * 5)):
                        tokens[tokens.index(word)] = options[byte % len(options)]
                        break
            pos += 1
        body = " ".join(tokens)
    # ---- (b) length jiggle
    extra_pool = [
        " If this is a new symptom, also note when it first appeared so we can correlate with a recent release.",
        " Either reply confirms what you'd like and we'll execute, or skip this step entirely.",
        " A short follow-up confirming success closes the loop nicely.",
        " (Internal note: this case may benefit from a brief screen-share if it persists.)",
        " The customer should reach out again if the suggestion doesn't land within 24 hours.",
    ]
    add_n = max(0, min(len(extra_pool), int(round(temperature * 5))))
    coin = h[3] % (add_n + 1) if add_n else 0
    for k in range(coin):
        body = body + extra_pool[(h[4 + k] % len(extra_pool))]
    # ---- (c) clause reorder — only at high temperature
    if temperature >= 0.9 and idx % 2 == 1:
        parts = body.split(". ")
        if len(parts) >= 3:
            mid = parts.pop(1)
            parts.append(mid)
            body = ". ".join(parts)
    return body.strip()


def _dry_replays(
    *,
    system_prompt: str,
    user_prompt: str,
    candidate_model: str,
    temperature: float,
    n_replays: int,
) -> List[Dict[str, Any]]:
    seed = hashlib.sha1((system_prompt + "|" + user_prompt + "|" + candidate_model).encode()).hexdigest()[:12]
    out: List[Dict[str, Any]] = []
    for i in range(n_replays):
        body = _dry_response_for(seed=seed, idx=i, temperature=temperature)
        h = hashlib.sha1((seed + f":lat{i}").encode()).digest()
        latency = 0.45 + (h[0] / 255.0) * (0.4 + temperature * 0.9)
        in_tok = max(40, len(_tokens(system_prompt + user_prompt)))
        out_tok = max(20, len(_tokens(body)))
        out.append({
            "replay_index": i,
            "response": body,
            "input_tokens": in_tok,
            "output_tokens": out_tok,
            "cost_usd": round(float(estimate_cost(candidate_model, in_tok, out_tok) or 0.0), 6),
            "latency": round(latency, 3),
            "status": "success",
            "error": None,
        })
    return out


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def _row_to_drift(row: sqlite3.Row) -> Dict[str, Any]:
    summary = {}
    if row["summary_json"]:
        try:
            summary = json.loads(row["summary_json"])
        except (TypeError, ValueError, json.JSONDecodeError):
            summary = {}
    return {
        "id": row["id"],
        "name": row["name"],
        "description": row["description"] or "",
        "system_prompt": row["system_prompt"] or "",
        "user_prompt": row["user_prompt"],
        "candidate_provider": row["candidate_provider"] or "",
        "candidate_model": row["candidate_model"] or "",
        "temperature": float(row["temperature"]),
        "top_p": float(row["top_p"]),
        "n_replays": int(row["n_replays"]),
        "cluster_threshold": float(row["cluster_threshold"]),
        "status": row["status"],
        "stability_score": float(row["stability_score"]) if row["stability_score"] is not None else None,
        "band": row["band"],
        "lexical_score": float(row["lexical_score"]) if row["lexical_score"] is not None else None,
        "length_score": float(row["length_score"]) if row["length_score"] is not None else None,
        "latency_score": float(row["latency_score"]) if row["latency_score"] is not None else None,
        "mean_similarity": float(row["mean_similarity"]) if row["mean_similarity"] is not None else None,
        "min_similarity": float(row["min_similarity"]) if row["min_similarity"] is not None else None,
        "length_cv": float(row["length_cv"]) if row["length_cv"] is not None else None,
        "latency_cv": float(row["latency_cv"]) if row["latency_cv"] is not None else None,
        "n_clusters": int(row["n_clusters"]) if row["n_clusters"] is not None else None,
        "variance_type": row["variance_type"],
        "medoid_index": int(row["medoid_index"]) if row["medoid_index"] is not None else None,
        "total_cost": float(row["total_cost"] or 0),
        "duration": float(row["duration"] or 0),
        "dryrun": bool(row["dryrun"]),
        "summary": summary,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _row_to_sample(row: sqlite3.Row) -> Dict[str, Any]:
    return {
        "id": row["id"],
        "replay_index": int(row["replay_index"]),
        "response": row["response"],
        "input_tokens": int(row["input_tokens"] or 0),
        "output_tokens": int(row["output_tokens"] or 0),
        "cost_usd": float(row["cost_usd"] or 0),
        "latency": float(row["latency"] or 0),
        "cluster_id": int(row["cluster_id"]) if row["cluster_id"] is not None else None,
        "mean_sim": float(row["mean_sim"]) if row["mean_sim"] is not None else None,
        "status": row["status"],
        "error": row["error"] or "",
        "created_at": row["created_at"],
    }


# ---------------------------------------------------------------------------
# Public CRUD
# ---------------------------------------------------------------------------

def _clip_int(v: Any, lo: int, hi: int, default: int) -> int:
    try:
        n = int(v)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, n))


def _clip_float(v: Any, lo: float, hi: float, default: float) -> float:
    try:
        n = float(v)
    except (TypeError, ValueError):
        return default
    if math.isnan(n) or math.isinf(n):
        return default
    return max(lo, min(hi, n))


def create_drift(
    *,
    name: str,
    user_prompt: str,
    system_prompt: str = "",
    description: str = "",
    candidate_provider: str = "",
    candidate_model: str = "",
    temperature: Any = DEFAULT_TEMPERATURE,
    top_p: Any = DEFAULT_TOP_P,
    n_replays: Any = DEFAULT_N_REPLAYS,
    cluster_threshold: Any = DEFAULT_CLUSTER_THRESHOLD,
    dryrun: bool = False,
) -> Dict[str, Any]:
    init_db()
    name = (name or "").strip()
    if not name:
        raise ValueError("name is required")
    user_prompt = (user_prompt or "").strip()
    if not user_prompt:
        raise ValueError("user_prompt is required")
    if not dryrun:
        if not candidate_provider or not candidate_model:
            raise ValueError("candidate_provider and candidate_model are required in live mode")
    temperature = _clip_float(temperature, 0.0, 2.0, DEFAULT_TEMPERATURE)
    top_p = _clip_float(top_p, 0.0, 1.0, DEFAULT_TOP_P)
    n_replays = _clip_int(n_replays, MIN_N_REPLAYS, MAX_N_REPLAYS, DEFAULT_N_REPLAYS)
    cluster_threshold = _clip_float(cluster_threshold, 0.2, 0.95, DEFAULT_CLUSTER_THRESHOLD)
    did = uuid.uuid4().hex
    now = _now()
    with _DB_LOCK, _conn() as con:
        con.execute(
            """INSERT INTO drift_runs
                 (id, name, description, system_prompt, user_prompt,
                  candidate_provider, candidate_model,
                  temperature, top_p, n_replays, cluster_threshold,
                  status, total_cost, duration, dryrun,
                  created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                       'draft', 0, 0, ?, ?, ?)""",
            (
                did, name, (description or "").strip(),
                (system_prompt or "").strip(), user_prompt,
                candidate_provider or None, candidate_model or None,
                temperature, top_p, n_replays, cluster_threshold,
                1 if dryrun else 0, now, now,
            ),
        )
    return get_drift(did) or {}


def list_drifts(
    *,
    q: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> Tuple[List[Dict[str, Any]], int]:
    init_db()
    clauses: List[str] = []
    params: List[Any] = []
    if q:
        clauses.append("(LOWER(name) LIKE ? OR LOWER(description) LIKE ?)")
        like = f"%{q.lower().strip()}%"
        params.extend([like, like])
    if status:
        clauses.append("status = ?")
        params.append(status)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    with _DB_LOCK, _conn() as con:
        total = con.execute(
            f"SELECT COUNT(*) AS c FROM drift_runs {where}",
            params,
        ).fetchone()["c"]
        rows = con.execute(
            f"""SELECT * FROM drift_runs
                {where}
                ORDER BY updated_at DESC
                LIMIT ? OFFSET ?""",
            (*params, int(limit), int(offset)),
        ).fetchall()
    out = [_row_to_drift(r) for r in rows]
    return out, int(total)


def get_drift(drift_id: str) -> Optional[Dict[str, Any]]:
    init_db()
    with _DB_LOCK, _conn() as con:
        row = con.execute("SELECT * FROM drift_runs WHERE id = ?", (drift_id,)).fetchone()
        if not row:
            return None
        drift = _row_to_drift(row)
        srows = con.execute(
            """SELECT * FROM drift_samples
               WHERE drift_id = ?
               ORDER BY replay_index ASC""",
            (drift_id,),
        ).fetchall()
        drift["samples"] = [_row_to_sample(s) for s in srows]
        drift["n_samples"] = len(drift["samples"])
    return drift


def delete_drift(drift_id: str) -> bool:
    init_db()
    with _DB_LOCK, _conn() as con:
        con.execute("DELETE FROM drift_samples WHERE drift_id = ?", (drift_id,))
        cur = con.execute("DELETE FROM drift_runs WHERE id = ?", (drift_id,))
        return cur.rowcount > 0


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

def run_drift(
    drift_id: str,
    *,
    provider_factory,
    confirm_live: bool = False,
) -> Tuple[Dict[str, Any], int]:
    """Execute the replay batch and roll the bag into stability metrics.

    Dry-run mode runs in milliseconds (no upstream calls). Live mode issues
    ``n_replays`` parallel candidate calls and requires ``confirm_live=True``
    so the user explicitly opts in to spending credits.
    """
    init_db()
    drift = get_drift(drift_id)
    if not drift:
        return {"success": False, "error": "drift run not found"}, 404
    if drift["status"] == "running":
        return {"success": False, "error": "drift run already running"}, 400
    if not drift["dryrun"] and not confirm_live:
        return {
            "success": False,
            "error": "live drift run: pass confirm_live=true (this will spend API credits)",
        }, 400

    # Wipe previous samples — a run is re-runnable in place.
    with _DB_LOCK, _conn() as con:
        con.execute("DELETE FROM drift_samples WHERE drift_id = ?", (drift_id,))
        con.execute(
            "UPDATE drift_runs SET status='running', updated_at=? WHERE id=?",
            (_now(), drift_id),
        )

    started = time.time()

    # 1) Replay batch.
    if drift["dryrun"]:
        samples = _dry_replays(
            system_prompt=drift["system_prompt"],
            user_prompt=drift["user_prompt"],
            candidate_model=drift["candidate_model"] or "dryrun/echo",
            temperature=drift["temperature"],
            n_replays=drift["n_replays"],
        )
    else:
        samples = _live_replays(
            system_prompt=drift["system_prompt"],
            user_prompt=drift["user_prompt"],
            candidate_provider=drift["candidate_provider"],
            candidate_model=drift["candidate_model"],
            temperature=drift["temperature"],
            top_p=drift["top_p"],
            n_replays=drift["n_replays"],
            provider_factory=provider_factory,
        )

    success_samples = [s for s in samples if s["status"] == "success" and (s.get("response") or "").strip()]
    failed_samples = [s for s in samples if s not in success_samples]

    # 2) Pairwise similarity + clusters.
    if len(success_samples) >= 2:
        matrix = _pairwise_similarity(success_samples)
        clusters = _single_link_cluster(matrix, drift["cluster_threshold"])
        # Mean similarity per row (excluding diagonal).
        n = len(matrix)
        mean_sims: List[float] = []
        off_diag: List[float] = []
        for i in range(n):
            row = [matrix[i][j] for j in range(n) if j != i]
            mean_sims.append(sum(row) / len(row) if row else 0.0)
            off_diag.extend(row)
        # Halve off_diag since each pair appears twice.
        unique_pairs = []
        for i in range(n):
            for j in range(i + 1, n):
                unique_pairs.append(matrix[i][j])
        mean_similarity = _mean(unique_pairs) if unique_pairs else None
        min_similarity = min(unique_pairs) if unique_pairs else None
        medoid_local_idx = max(range(n), key=lambda i: mean_sims[i])
        medoid_replay = success_samples[medoid_local_idx]["replay_index"]
        # Cluster size summary.
        cluster_sizes: Dict[int, int] = {}
        for c in clusters:
            cluster_sizes[c] = cluster_sizes.get(c, 0) + 1
        n_clusters = len(cluster_sizes)
        cluster_summary = [
            {
                "id": cid,
                "size": cluster_sizes[cid],
                "replay_indexes": [
                    success_samples[i]["replay_index"]
                    for i, c in enumerate(clusters)
                    if c == cid
                ],
            }
            for cid in sorted(cluster_sizes.keys())
        ]
    elif len(success_samples) == 1:
        matrix = [[1.0]]
        clusters = [0]
        mean_sims = [1.0]
        mean_similarity = None
        min_similarity = None
        medoid_local_idx = 0
        medoid_replay = success_samples[0]["replay_index"]
        n_clusters = 1
        cluster_summary = [{"id": 0, "size": 1, "replay_indexes": [medoid_replay]}]
    else:
        matrix = []
        clusters = []
        mean_sims = []
        mean_similarity = None
        min_similarity = None
        medoid_local_idx = None
        medoid_replay = None
        n_clusters = 0
        cluster_summary = []

    # 3) Length + latency stability.
    out_tokens = [s["output_tokens"] for s in success_samples]
    latencies = [s["latency"] for s in success_samples]
    costs = [s["cost_usd"] for s in success_samples]
    length_cv = _cv(out_tokens) if out_tokens else None
    latency_cv = _cv(latencies) if latencies else None

    lex_score = (mean_similarity * 100.0) if mean_similarity is not None else (100.0 if success_samples else None)
    len_score = (
        100.0 * max(0.0, 1.0 - min(1.0, length_cv))
        if length_cv is not None else None
    )
    lat_score = (
        100.0 * max(0.0, 1.0 - min(1.0, latency_cv))
        if latency_cv is not None else None
    )

    composite = _composite(lex_score, len_score, lat_score)
    band = _band_for(composite)
    variance_type = _classify_variance(lex_score, length_cv)

    # 4) Annotate per-sample with cluster + mean_sim.
    sample_meta_by_idx: Dict[int, Tuple[Optional[int], Optional[float]]] = {}
    for i, s in enumerate(success_samples):
        sample_meta_by_idx[s["replay_index"]] = (
            clusters[i] if i < len(clusters) else None,
            round(mean_sims[i], 4) if i < len(mean_sims) else None,
        )

    # 5) Persist.
    total_cost = sum(s["cost_usd"] for s in samples)
    with _DB_LOCK, _conn() as con:
        for s in samples:
            cid, msim = sample_meta_by_idx.get(s["replay_index"], (None, None))
            con.execute(
                """INSERT INTO drift_samples
                     (id, drift_id, replay_index,
                      response, input_tokens, output_tokens,
                      cost_usd, latency,
                      cluster_id, mean_sim,
                      status, error, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    uuid.uuid4().hex, drift_id, s["replay_index"],
                    s["response"], s["input_tokens"], s["output_tokens"],
                    round(s["cost_usd"], 6), round(s["latency"], 3),
                    cid, msim,
                    s["status"], s.get("error"), _now(),
                ),
            )

    duration = round(time.time() - started, 3)
    headline = _build_headline(
        composite=composite,
        band=band,
        variance_type=variance_type,
        n_clusters=n_clusters,
        n_success=len(success_samples),
        n_total=len(samples),
        length_cv=length_cv,
    )
    summary = {
        "stability_score": round(composite, 2) if composite is not None else None,
        "band": band,
        "variance_type": variance_type,
        "variance_blurb": VARIANCE_TYPE_BLURB.get(variance_type, ""),
        "lexical_score": round(lex_score, 2) if lex_score is not None else None,
        "length_score": round(len_score, 2) if len_score is not None else None,
        "latency_score": round(lat_score, 2) if lat_score is not None else None,
        "mean_similarity": round(mean_similarity, 4) if mean_similarity is not None else None,
        "min_similarity": round(min_similarity, 4) if min_similarity is not None else None,
        "length_cv": round(length_cv, 4) if length_cv is not None else None,
        "latency_cv": round(latency_cv, 4) if latency_cv is not None else None,
        "cost_cv": round(_cv(costs), 4) if costs else None,
        "n_clusters": n_clusters,
        "medoid_replay_index": medoid_replay,
        "similarity_matrix": matrix,
        "clusters": cluster_summary,
        "n_samples": len(samples),
        "n_success": len(success_samples),
        "n_failed": len(failed_samples),
        "mean_tokens": round(_mean(out_tokens), 2) if out_tokens else None,
        "mean_latency": round(_mean(latencies), 3) if latencies else None,
        "total_cost": round(total_cost, 6),
        "duration": duration,
        "headline": headline,
        "advisory": _build_advisory(band, variance_type, length_cv, n_clusters, len(success_samples)),
    }

    with _DB_LOCK, _conn() as con:
        con.execute(
            """UPDATE drift_runs
               SET status='complete',
                   stability_score=?, band=?,
                   lexical_score=?, length_score=?, latency_score=?,
                   mean_similarity=?, min_similarity=?,
                   length_cv=?, latency_cv=?,
                   n_clusters=?, variance_type=?, medoid_index=?,
                   total_cost=?, duration=?, summary_json=?,
                   updated_at=?
               WHERE id=?""",
            (
                round(composite, 2) if composite is not None else None,
                band,
                round(lex_score, 2) if lex_score is not None else None,
                round(len_score, 2) if len_score is not None else None,
                round(lat_score, 2) if lat_score is not None else None,
                round(mean_similarity, 4) if mean_similarity is not None else None,
                round(min_similarity, 4) if min_similarity is not None else None,
                round(length_cv, 4) if length_cv is not None else None,
                round(latency_cv, 4) if latency_cv is not None else None,
                n_clusters, variance_type, medoid_replay,
                round(total_cost, 6), duration,
                json.dumps(summary), _now(),
                drift_id,
            ),
        )
    return {"success": True, "drift": get_drift(drift_id), "summary": summary}, 200


def _build_headline(
    *,
    composite: Optional[float],
    band: str,
    variance_type: str,
    n_clusters: int,
    n_success: int,
    n_total: int,
    length_cv: Optional[float],
) -> str:
    if composite is None:
        return "No usable replays — every call failed or returned empty."
    score = round(composite)
    head = f"{band} — {score}/100 stability across {n_success}/{n_total} replays."
    if n_clusters > 1:
        head += f" Replies fell into {n_clusters} distinct cluster(s)."
    if variance_type and variance_type != "—":
        if variance_type == "Substantive":
            head += " Substantive drift — replays disagree on the answer."
        elif variance_type == "Verbose":
            head += " Verbosity drift — length varies call-to-call."
        elif variance_type == "Cosmetic":
            head += " Cosmetic drift — same answer, slightly reworded."
        elif variance_type == "Steady":
            head += " Replays read near-identical."
    if length_cv is not None and length_cv >= 0.5:
        head += f" Length CV {length_cv:.2f} — token count swings widely."
    return head


def _build_advisory(
    band: str,
    variance_type: str,
    length_cv: Optional[float],
    n_clusters: int,
    n_success: int,
) -> str:
    if n_success == 0:
        return "Every replay failed — verify your provider key and the model id before re-running."
    if band == "Steady":
        return (
            "Ship as-is — this prompt is reliable at the current temperature. "
            "If you need to *introduce* variance (e.g. for creative-writing tasks), raise temperature."
        )
    if band == "Consistent":
        return (
            "Production-acceptable. Watch the divergent cluster(s) — if any reply contradicts the rest "
            "on a critical detail, tighten the system prompt or drop temperature one notch."
        )
    if band == "Drifty":
        if variance_type == "Substantive":
            return (
                "Not safe to ship — replies disagree on the substance. Add explicit constraints "
                "(scope, format, refusal rules) to your system prompt before re-testing."
            )
        if variance_type == "Verbose":
            return (
                "Replies overlap, but length swings widely. Add an explicit length constraint to the "
                "system prompt (e.g. \"reply in 2 sentences\") and re-run."
            )
        return (
            "Tighten the prompt or drop temperature. Today's output cluster count "
            f"({n_clusters}) suggests the model is exploring multiple valid framings."
        )
    if band == "Wild":
        return (
            "This prompt is unsafe to ship at the current temperature. Either pin temperature to 0 "
            "(if the task is deterministic) or rewrite the prompt with hard constraints — what to do, "
            "what *not* to do, and the exact output format."
        )
    return "Re-run with more replays to get a confident verdict."


# ---------------------------------------------------------------------------
# Stats + seed
# ---------------------------------------------------------------------------

def stats() -> Dict[str, Any]:
    init_db()
    with _DB_LOCK, _conn() as con:
        n_runs = int(con.execute("SELECT COUNT(*) AS c FROM drift_runs").fetchone()["c"])
        n_samples = int(con.execute("SELECT COUNT(*) AS c FROM drift_samples").fetchone()["c"])
        avg_row = con.execute(
            "SELECT AVG(stability_score) AS a FROM drift_runs WHERE stability_score IS NOT NULL"
        ).fetchone()
        best_row = con.execute(
            "SELECT MAX(stability_score) AS m FROM drift_runs"
        ).fetchone()
        worst_row = con.execute(
            "SELECT MIN(stability_score) AS m FROM drift_runs WHERE stability_score IS NOT NULL"
        ).fetchone()
        # Per-band counts.
        band_rows = con.execute(
            "SELECT band, COUNT(*) AS c FROM drift_runs WHERE band IS NOT NULL GROUP BY band"
        ).fetchall()
        by_band = {r["band"]: int(r["c"]) for r in band_rows}
        # Per-variance-type counts.
        var_rows = con.execute(
            """SELECT variance_type, COUNT(*) AS c
               FROM drift_runs
               WHERE variance_type IS NOT NULL AND variance_type != '—'
               GROUP BY variance_type"""
        ).fetchall()
        by_variance = {r["variance_type"]: int(r["c"]) for r in var_rows}
    return {
        "n_runs": n_runs,
        "n_samples": n_samples,
        "avg_stability": round(float(avg_row["a"]), 2) if avg_row and avg_row["a"] is not None else None,
        "best_stability": round(float(best_row["m"]), 2) if best_row and best_row["m"] is not None else None,
        "worst_stability": round(float(worst_row["m"]), 2) if worst_row and worst_row["m"] is not None else None,
        "by_band": by_band,
        "by_variance_type": by_variance,
    }


_SEED_NAME = "Customer support — Drift baseline"


def seed_demo() -> Dict[str, Any]:
    """Idempotent — looks for an existing seeded run with the canonical name."""
    init_db()
    existing_id: Optional[str] = None
    with _DB_LOCK, _conn() as con:
        row = con.execute(
            "SELECT id FROM drift_runs WHERE name = ? LIMIT 1",
            (_SEED_NAME,),
        ).fetchone()
        if row:
            existing_id = row["id"]
    if existing_id:
        return get_drift(existing_id) or {}
    system_prompt = (
        "You are a calm, concise customer support specialist for a small SaaS company. "
        "Read the user's message, identify the issue, and reply with a two-sentence answer "
        "followed by the next concrete step the user should take."
    )
    user_prompt = (
        "I was double charged last month — there are two transactions for the same plan on June 3rd. "
        "Can you sort it out?"
    )
    drift = create_drift(
        name=_SEED_NAME,
        description="Day-63 demo: replay the same support prompt 8× at T=0.7 and measure drift.",
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        temperature=0.7,
        top_p=1.0,
        n_replays=8,
        cluster_threshold=DEFAULT_CLUSTER_THRESHOLD,
        dryrun=True,
    )
    return drift
