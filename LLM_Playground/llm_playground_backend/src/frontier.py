"""Frontier — Cost / Quality Pareto Explorer.

Every studio in this playground answers *a* question about a prompt:

* **Arena / Vote** — which model gave the best answer *this time*?
* **Rubrics / Judge** — score responses against a bespoke rubric.
* **Suites** — batch a prompt across many cases and aggregate.
* **Drift** — how deterministic is model X for prompt P?
* **Adversary** — what breaks the prompt when the input is messy?
* **Showdown** — is *this* prompt rewrite an actual upgrade?
* **Optimizer** — evolve the prompt toward a target.
* **Surgeon** — which paragraphs of the prompt earn their cost?

None of them answers the single question every team hits the day they
have to *ship* a prompt: **which model should I run this on?**

The answer is never "the biggest one". A flagship model at $30/M-tokens
gets you a 92-quality answer; a mid-tier one at $0.15/M gets you an
87-quality answer — same prompt, same day, same customer. On 50k calls a
month the delta is a $2,000 AWS invoice you did not need to pay. But no
tool in the playground *shows* that trade-off. Arena renders raw
responses side-by-side and leaves the pricing math to you. Judges score
quality but ignore cost. Insights aggregates history but has no notion
of dominance.

Frontier is that surface. Given a prompt (system + user), a list of
candidate models, and an optional monthly call rate, it:

* Runs each model ``n_replays`` times.
* Computes a **quality composite** (0-100) — coverage of expected
  keywords, fidelity vs a shared baseline, and structural format score —
  matching the metric Surgeon uses so scores are directly comparable
  across studios.
* Computes **cost per call** — actual token counts from the replays run
  through the project's pricing table.
* Computes **latency mean** per model.
* Applies **Pareto dominance**: model A dominates B iff A has ≥ B's
  quality AND ≤ B's cost with at least one strict. Points that no other
  point dominates form the **frontier**.
* Runs the **Kneedle elbow** on the frontier (log-cost x-axis) — the
  single point where marginal quality per dollar is highest. That is
  the pick a team should default to.
* Serves three recommendations off one call: **elbow** (default),
  **best within budget**, and **cheapest meeting quality**.
* Computes monthly $ savings from picking the elbow vs the top-quality
  model at the user-set call rate — the number that actually justifies
  running Frontier in the first place.

Dryrun is deterministic — quality and response length for each model
are seeded from ``SHA1(prompt || model || replay_index)`` and biased by
the model's pricing tier — so the demo lights up with a plausible
frontier the moment the page loads, without any API keys.

Public surface:
``create_frontier``, ``list_frontiers``, ``get_frontier``,
``delete_frontier``, ``run_frontier``, ``seed_demo``, ``stats``,
``defaults``, ``compute_pareto``, ``kneedle_elbow``.
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
from src.pricing import _lookup as _price_lookup, estimate_cost

_DB_LOCK = history._DB_LOCK  # noqa: SLF001 — share the cross-table sqlite lock


@contextmanager
def _conn():
    with history._conn() as con:  # noqa: SLF001
        yield con


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS frontier_runs (
    id                  TEXT PRIMARY KEY,
    name                TEXT NOT NULL,
    description         TEXT,
    system_prompt       TEXT NOT NULL,
    user_prompt         TEXT NOT NULL,
    temperature         REAL NOT NULL DEFAULT 0.4,
    top_p               REAL NOT NULL DEFAULT 1.0,
    n_replays           INTEGER NOT NULL DEFAULT 3,
    monthly_calls       INTEGER NOT NULL DEFAULT 50000,
    quality_floor       REAL,
    budget_ceiling      REAL,
    status              TEXT NOT NULL,
    total_models        INTEGER DEFAULT 0,
    frontier_size       INTEGER DEFAULT 0,
    top_quality         REAL,
    top_quality_model   TEXT,
    top_quality_cost    REAL,
    cheapest_cost       REAL,
    cheapest_model      TEXT,
    elbow_model         TEXT,
    elbow_quality       REAL,
    elbow_cost          REAL,
    monthly_savings     REAL,
    quality_kept_pct    REAL,
    total_cost          REAL DEFAULT 0,
    duration            REAL DEFAULT 0,
    dryrun              INTEGER NOT NULL DEFAULT 1,
    summary_json        TEXT,
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS frontier_points (
    id                TEXT PRIMARY KEY,
    frontier_id       TEXT NOT NULL,
    provider          TEXT NOT NULL,
    model             TEXT NOT NULL,
    tier              TEXT,
    quality           REAL,
    quality_stdev     REAL,
    cost_per_call     REAL,
    latency_ms        REAL,
    input_tokens      INTEGER,
    output_tokens     INTEGER,
    replays_ok        INTEGER,
    replays_total     INTEGER,
    on_frontier       INTEGER,
    is_elbow          INTEGER,
    dominates_json    TEXT,
    dominated_by_json TEXT,
    medoid_sample     TEXT,
    monthly_cost      REAL,
    monthly_savings   REAL,
    rationale         TEXT,
    created_at        TEXT NOT NULL,
    FOREIGN KEY (frontier_id) REFERENCES frontier_runs(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_frontier_points_run
    ON frontier_points(frontier_id, cost_per_call);
"""


def init_db() -> None:
    with _DB_LOCK, _conn() as con:
        con.executescript(_SCHEMA)


# ---------------------------------------------------------------------------
# Defaults / model roster
# ---------------------------------------------------------------------------

DEFAULT_N_REPLAYS = 3
MIN_N_REPLAYS = 1
MAX_N_REPLAYS = 6
DEFAULT_TEMPERATURE = 0.4
DEFAULT_TOP_P = 1.0
DEFAULT_MONTHLY_CALLS = 50_000

# Model roster used when the caller doesn't hand one in. Deliberately
# spans every pricing tier so the frontier plot has range on the x-axis
# even for a first-time visitor with no customization.
DEFAULT_ROSTER: List[Dict[str, str]] = [
    {"provider": "OpenAI",    "model": "gpt-4o"},
    {"provider": "OpenAI",    "model": "gpt-4o-mini"},
    {"provider": "OpenAI",    "model": "gpt-3.5-turbo"},
    {"provider": "OpenAI",    "model": "gpt-4-turbo"},
    {"provider": "Anthropic", "model": "claude-3-5-sonnet"},
    {"provider": "Anthropic", "model": "claude-3-5-haiku"},
    {"provider": "Anthropic", "model": "claude-3-haiku"},
    {"provider": "Google",    "model": "gemini-1.5-pro"},
    {"provider": "Google",    "model": "gemini-1.5-flash"},
]


def _tier_for(model: str) -> str:
    """Map a model to a rough capability tier via its output price. The
    tier is used both as a display label ("Premium") and as the quality
    bias for dryrun response generation."""
    _in, out = _price_lookup(model or "")
    if out >= 40:
        return "flagship"
    if out >= 10:
        return "premium"
    if out >= 3:
        return "mid"
    if out >= 1:
        return "efficient"
    return "budget"


_TIER_QUALITY_BIAS = {
    "flagship":  22.0,
    "premium":   15.0,
    "mid":       8.0,
    "efficient": 2.0,
    "budget":    -6.0,
}

_TIER_LATENCY_MS = {
    "flagship":  (1200, 4000),
    "premium":   (800,  2500),
    "mid":       (500,  1800),
    "efficient": (400,  1200),
    "budget":    (300,  900),
}

_TIER_OUT_TOKENS = {
    "flagship":  (280, 520),
    "premium":   (220, 440),
    "mid":       (170, 340),
    "efficient": (140, 280),
    "budget":    (90,  200),
}


def defaults() -> Dict[str, Any]:
    return {
        "n_replays": {"default": DEFAULT_N_REPLAYS, "min": MIN_N_REPLAYS, "max": MAX_N_REPLAYS},
        "temperature": {"default": DEFAULT_TEMPERATURE, "min": 0.0, "max": 2.0, "step": 0.05},
        "top_p": {"default": DEFAULT_TOP_P, "min": 0.0, "max": 1.0, "step": 0.05},
        "monthly_calls": {"default": DEFAULT_MONTHLY_CALLS, "min": 100, "max": 10_000_000},
        "roster": DEFAULT_ROSTER,
        "tiers": {
            "flagship":  {"label": "Flagship",  "color": "violet",   "bias": _TIER_QUALITY_BIAS["flagship"]},
            "premium":   {"label": "Premium",   "color": "sky",      "bias": _TIER_QUALITY_BIAS["premium"]},
            "mid":       {"label": "Mid",       "color": "teal",     "bias": _TIER_QUALITY_BIAS["mid"]},
            "efficient": {"label": "Efficient", "color": "emerald",  "bias": _TIER_QUALITY_BIAS["efficient"]},
            "budget":    {"label": "Budget",    "color": "amber",    "bias": _TIER_QUALITY_BIAS["budget"]},
        },
        "scoring": {
            "axes": ["coverage", "fidelity", "format"],
            "weights": {"coverage": 0.50, "fidelity": 0.30, "format": 0.20},
            "scale": "0-100",
        },
        "elbow_method": "kneedle on log-cost / linear-quality axes",
    }


# ---------------------------------------------------------------------------
# Helpers — hashing, token estimate, tokens, clipping.
# ---------------------------------------------------------------------------

_WORD_RE = re.compile(r"[a-z0-9]+")

_STOP = {
    "the", "and", "for", "with", "that", "this", "from", "your", "you",
    "are", "was", "were", "have", "has", "had", "but", "not", "any",
    "all", "can", "will", "may", "into", "out", "over", "under",
    "should", "would", "could", "must", "also", "more", "than", "then",
    "they", "them", "their", "our", "its", "his", "her",
}


def _tokens(text: str) -> List[str]:
    return _WORD_RE.findall((text or "").lower())


def _token_estimate(text: str) -> int:
    s = text or ""
    return max(1, math.ceil(len(s) / 4))


def _seed_hash(*parts: str) -> bytes:
    return hashlib.sha1("||".join(parts).encode()).digest()


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


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


def _keywords_from(prompt: str, k: int = 14) -> List[str]:
    freq: Dict[str, int] = {}
    for w in _tokens(prompt):
        if len(w) < 4 or w in _STOP:
            continue
        freq[w] = freq.get(w, 0) + 1
    return [w for w, _ in sorted(freq.items(), key=lambda kv: -kv[1])[:k]]


def _mean(values: List[float]) -> float:
    vs = [float(v) for v in values if v is not None]
    if not vs:
        return 0.0
    return sum(vs) / len(vs)


def _stdev(values: List[float]) -> float:
    vs = [float(v) for v in values if v is not None]
    if len(vs) < 2:
        return 0.0
    m = _mean(vs)
    return math.sqrt(sum((v - m) ** 2 for v in vs) / len(vs))


# ---------------------------------------------------------------------------
# Scoring — coverage + fidelity + format → 0-100 composite (matches Surgeon)
# ---------------------------------------------------------------------------

def _coverage_score(response: str, expected_keywords: List[str]) -> float:
    if not expected_keywords:
        return 60.0
    words = set(_tokens(response))
    hits = sum(1 for kw in expected_keywords if kw.lower() in words)
    pct = hits / len(expected_keywords)
    return round(20.0 + pct * 80.0, 2)


def _fidelity_score(response: str, baseline: str) -> float:
    if not baseline:
        return 50.0 if (response or "").strip() else 0.0
    a = set(_tokens(response))
    b = set(_tokens(baseline))
    if not a and not b:
        return 100.0
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return round(100.0 * inter / union, 2)


def _format_score(response: str) -> float:
    text = (response or "").strip()
    if not text:
        return 0.0
    tok = _token_estimate(text)
    if tok < 20:
        return 30.0
    if tok < 60:
        return 60.0
    if tok <= 400:
        return 95.0
    if tok <= 800:
        return 75.0
    return 50.0


def composite_score(response: str, *, expected_keywords: List[str], baseline: str) -> float:
    cov = _coverage_score(response, expected_keywords)
    fid = _fidelity_score(response, baseline)
    fmt = _format_score(response)
    return round(0.50 * cov + 0.30 * fid + 0.20 * fmt, 2)


# ---------------------------------------------------------------------------
# Dryrun call synthesis — tier-aware synthetic responses.
# ---------------------------------------------------------------------------

_DRY_CORPUS = [
    "Here is a structured response to your request.",
    "First, we consider the key constraints in the prompt.",
    "Second, we outline a concrete approach with checkpoints.",
    "Third, we list the assumptions made along the way.",
    "Fourth, we describe the expected output and how to validate it.",
    "Finally, we surface the open questions a reviewer should answer.",
    "The trade-offs depend on latency, cost, and accuracy targets.",
    "We avoid speculative claims and ground each step in the prompt.",
    "The recommended pattern balances developer velocity with observability.",
    "Where the prompt is ambiguous we default to the safer interpretation.",
    "Timelines assume the standard deployment path with review gates.",
    "Fallback behavior is documented so downstream consumers do not break.",
    "Sources: the prompt, prior conversation, and standard practice.",
    "The above is intended as a starting point for iteration, not a final spec.",
]


def _dry_call(
    *,
    system_prompt: str,
    user_prompt: str,
    provider: str,
    model: str,
    replay_index: int,
    expected_keywords: List[str],
) -> Dict[str, Any]:
    """Deterministic synthetic call — response body, tokens, latency,
    quality all seeded from ``SHA1(prompt || model || replay_index)`` and
    biased by the model's price tier."""
    tier = _tier_for(model)
    seed = _seed_hash("frontier-dry", system_prompt[:128], user_prompt[:128], model, str(replay_index))

    # Response length driven by tier + tiny per-replay jitter.
    lo, hi = _TIER_OUT_TOKENS[tier]
    tgt_out_tokens = lo + int((seed[0] / 255.0) * (hi - lo))
    n_sentences = max(3, min(len(_DRY_CORPUS), 3 + int((seed[1] / 255.0) * 8)))
    body_parts = [_DRY_CORPUS[(replay_index + i + seed[2]) % len(_DRY_CORPUS)] for i in range(n_sentences)]
    # Sprinkle some of the expected keywords so richer models score higher
    # on coverage (they get more expected keywords woven in). The counts
    # aim for a ~40→85 quality spread once composite_score is applied.
    kw_budget = {
        "flagship":  12,
        "premium":   10,
        "mid":       7,
        "efficient": 4,
        "budget":    2,
    }[tier]
    kw_take = min(len(expected_keywords), kw_budget)
    if kw_take and expected_keywords:
        offset = seed[3] % max(1, len(expected_keywords))
        picked = [expected_keywords[(offset + i) % len(expected_keywords)] for i in range(kw_take)]
        body_parts.append(f"Key considerations: {', '.join(picked)}.")

    body = " ".join(body_parts)
    # Trim toward the tier target so higher-tier models produce longer answers.
    desired_chars = max(80, tgt_out_tokens * 4)
    if len(body) > desired_chars:
        body = body[: desired_chars - 1].rstrip() + "…"

    in_tok = _token_estimate(system_prompt + "\n" + user_prompt)
    out_tok = _token_estimate(body)
    lat_lo, lat_hi = _TIER_LATENCY_MS[tier]
    latency_ms = lat_lo + int((seed[4] / 255.0) * (lat_hi - lat_lo))

    return {
        "replay_index": replay_index,
        "status": "success",
        "response": body,
        "latency_ms": latency_ms,
        "input_tokens": in_tok,
        "output_tokens": out_tok,
        "tier": tier,
        "cost_usd": float(estimate_cost(model, in_tok, out_tok)),
        "error": None,
    }


def _live_call(
    *,
    provider_factory,
    system_prompt: str,
    user_prompt: str,
    provider: str,
    model: str,
    temperature: float,
    top_p: float,
    replay_index: int,
) -> Dict[str, Any]:
    inst = provider_factory.create_provider(provider)
    if not inst:
        return {
            "replay_index": replay_index, "status": "error",
            "error": f"provider {provider} not available",
            "response": "", "latency_ms": 0, "input_tokens": 0,
            "output_tokens": 0, "tier": _tier_for(model), "cost_usd": 0.0,
        }
    started = time.time()
    try:
        params = {"temperature": temperature, "top_p": top_p, "max_tokens": 600}
        resp = inst.chat(
            model=model,
            messages=[{"role": "user", "content": user_prompt}],
            system_prompt=system_prompt or "",
            params=params,
        )
        if isinstance(resp, dict):
            text = resp.get("response") or resp.get("content") or ""
            in_tok = int(resp.get("input_tokens", 0) or 0)
            out_tok = int(resp.get("output_tokens", 0) or 0)
        else:
            text = str(resp or "")
            in_tok = _token_estimate(system_prompt + "\n" + user_prompt)
            out_tok = _token_estimate(text)
        latency_ms = int(round((time.time() - started) * 1000))
        in_tok = in_tok or _token_estimate(system_prompt + "\n" + user_prompt)
        out_tok = out_tok or _token_estimate(text)
        return {
            "replay_index": replay_index,
            "status": "success" if text.strip() else "error",
            "error": None if text.strip() else "empty response",
            "response": text,
            "latency_ms": latency_ms,
            "input_tokens": in_tok,
            "output_tokens": out_tok,
            "tier": _tier_for(model),
            "cost_usd": float(estimate_cost(model, in_tok, out_tok)),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "replay_index": replay_index, "status": "error", "error": str(exc),
            "response": "", "latency_ms": int(round((time.time() - started) * 1000)),
            "input_tokens": 0, "output_tokens": 0,
            "tier": _tier_for(model), "cost_usd": 0.0,
        }


def _medoid(samples: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    succ = [s for s in samples if s.get("status") == "success" and (s.get("response") or "").strip()]
    if not succ:
        return None
    if len(succ) == 1:
        return succ[0]
    sets = [set(_tokens(s["response"])) for s in succ]
    best_i = 0
    best_score = -1.0
    for i in range(len(succ)):
        total = 0.0
        for j in range(len(succ)):
            if i == j:
                continue
            a, b = sets[i], sets[j]
            if not a and not b:
                total += 1.0
            elif not a or not b:
                total += 0.0
            else:
                total += len(a & b) / len(a | b)
        avg = total / max(1, len(succ) - 1)
        if avg > best_score:
            best_score = avg
            best_i = i
    return succ[best_i]


# ---------------------------------------------------------------------------
# Pareto dominance + Kneedle elbow.
# ---------------------------------------------------------------------------

def _dominates(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
    """Point ``a`` dominates ``b`` iff ``a`` has ≥ quality AND ≤ cost with
    at least one strict. We're only interested in *successful* points —
    error rows (quality=None) are never on the frontier."""
    if a["quality"] is None or b["quality"] is None:
        return False
    if a["cost_per_call"] is None or b["cost_per_call"] is None:
        return False
    ge_q = a["quality"] >= b["quality"]
    le_c = a["cost_per_call"] <= b["cost_per_call"]
    strict = (a["quality"] > b["quality"]) or (a["cost_per_call"] < b["cost_per_call"])
    return ge_q and le_c and strict


def compute_pareto(points: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Annotate each point with ``on_frontier``, ``dominated_by``,
    ``dominates`` and return the frontier ordered by cost ascending."""
    for p in points:
        p["on_frontier"] = True
        p["dominated_by"] = []
        p["dominates"] = []
    for i, p in enumerate(points):
        for j, q in enumerate(points):
            if i == j:
                continue
            if _dominates(q, p):
                p["on_frontier"] = False
                p["dominated_by"].append(_key(q))
        # A degenerate row with no successful replays never joins.
        if p.get("quality") is None or p.get("cost_per_call") is None:
            p["on_frontier"] = False
    for i, p in enumerate(points):
        for j, q in enumerate(points):
            if i == j:
                continue
            if _dominates(p, q):
                p["dominates"].append(_key(q))
    frontier = [p for p in points if p["on_frontier"]]
    frontier.sort(key=lambda x: (x["cost_per_call"], -x["quality"]))
    return frontier


def _key(point: Dict[str, Any]) -> str:
    return f"{point.get('provider','?')}:{point.get('model','?')}"


def kneedle_elbow(frontier: List[Dict[str, Any]]) -> Optional[int]:
    """Kneedle-lite: return the index into ``frontier`` (sorted by cost
    ascending) of the point whose normalized (log-cost, quality) sits
    highest above the line connecting the frontier endpoints. If there
    are fewer than 3 frontier points the elbow is the cheapest — the
    curve is degenerate and the recommendation still needs an anchor."""
    if not frontier:
        return None
    if len(frontier) == 1:
        return 0
    if len(frontier) == 2:
        # With 2 points there's no interior elbow — recommend the cheaper.
        return 0

    log_costs = [math.log10(max(1e-8, p["cost_per_call"])) for p in frontier]
    qualities = [float(p["quality"]) for p in frontier]

    x_min, x_max = log_costs[0], log_costs[-1]
    y_min, y_max = qualities[0], qualities[-1]
    x_range = max(1e-9, x_max - x_min)
    y_range = max(1e-9, y_max - y_min)

    best_i = 1
    best_d = -1.0
    for i in range(1, len(frontier) - 1):
        xn = (log_costs[i] - x_min) / x_range
        yn = (qualities[i] - y_min) / y_range
        # Distance above y=x diagonal in normalized space — the classic
        # Kneedle "difference curve" over a monotone-non-decreasing frontier.
        d = yn - xn
        if d > best_d:
            best_d = d
            best_i = i
    return best_i


# ---------------------------------------------------------------------------
# Persistence — CRUD on frontier_runs + frontier_points
# ---------------------------------------------------------------------------

def _row_to_run(row: sqlite3.Row) -> Dict[str, Any]:
    summary: Dict[str, Any] = {}
    if row["summary_json"]:
        try:
            summary = json.loads(row["summary_json"])
        except (TypeError, ValueError, json.JSONDecodeError):
            summary = {}
    return {
        "id": row["id"],
        "name": row["name"],
        "description": row["description"] or "",
        "system_prompt": row["system_prompt"],
        "user_prompt": row["user_prompt"],
        "temperature": float(row["temperature"]),
        "top_p": float(row["top_p"]),
        "n_replays": int(row["n_replays"]),
        "monthly_calls": int(row["monthly_calls"]),
        "quality_floor": float(row["quality_floor"]) if row["quality_floor"] is not None else None,
        "budget_ceiling": float(row["budget_ceiling"]) if row["budget_ceiling"] is not None else None,
        "status": row["status"],
        "total_models": int(row["total_models"] or 0),
        "frontier_size": int(row["frontier_size"] or 0),
        "top_quality": float(row["top_quality"]) if row["top_quality"] is not None else None,
        "top_quality_model": row["top_quality_model"] or "",
        "top_quality_cost": float(row["top_quality_cost"]) if row["top_quality_cost"] is not None else None,
        "cheapest_cost": float(row["cheapest_cost"]) if row["cheapest_cost"] is not None else None,
        "cheapest_model": row["cheapest_model"] or "",
        "elbow_model": row["elbow_model"] or "",
        "elbow_quality": float(row["elbow_quality"]) if row["elbow_quality"] is not None else None,
        "elbow_cost": float(row["elbow_cost"]) if row["elbow_cost"] is not None else None,
        "monthly_savings": float(row["monthly_savings"] or 0),
        "quality_kept_pct": float(row["quality_kept_pct"] or 0),
        "total_cost": float(row["total_cost"] or 0),
        "duration": float(row["duration"] or 0),
        "dryrun": bool(row["dryrun"]),
        "summary": summary,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _row_to_point(row: sqlite3.Row) -> Dict[str, Any]:
    def _jl(col: str) -> List[str]:
        raw = row[col]
        if not raw:
            return []
        try:
            v = json.loads(raw)
            return v if isinstance(v, list) else []
        except (TypeError, ValueError, json.JSONDecodeError):
            return []
    return {
        "id": row["id"],
        "provider": row["provider"],
        "model": row["model"],
        "key": f"{row['provider']}:{row['model']}",
        "tier": row["tier"] or "unknown",
        "quality": float(row["quality"]) if row["quality"] is not None else None,
        "quality_stdev": float(row["quality_stdev"] or 0),
        "cost_per_call": float(row["cost_per_call"]) if row["cost_per_call"] is not None else None,
        "latency_ms": float(row["latency_ms"] or 0),
        "input_tokens": int(row["input_tokens"] or 0),
        "output_tokens": int(row["output_tokens"] or 0),
        "replays_ok": int(row["replays_ok"] or 0),
        "replays_total": int(row["replays_total"] or 0),
        "on_frontier": bool(row["on_frontier"]),
        "is_elbow": bool(row["is_elbow"]),
        "dominates": _jl("dominates_json"),
        "dominated_by": _jl("dominated_by_json"),
        "medoid_sample": row["medoid_sample"] or "",
        "monthly_cost": float(row["monthly_cost"] or 0),
        "monthly_savings": float(row["monthly_savings"] or 0),
        "rationale": row["rationale"] or "",
        "created_at": row["created_at"],
    }


def create_frontier(
    *,
    name: str,
    description: str = "",
    system_prompt: str,
    user_prompt: str,
    temperature: Any = DEFAULT_TEMPERATURE,
    top_p: Any = DEFAULT_TOP_P,
    n_replays: Any = DEFAULT_N_REPLAYS,
    monthly_calls: Any = DEFAULT_MONTHLY_CALLS,
    quality_floor: Any = None,
    budget_ceiling: Any = None,
    dryrun: bool = False,
    roster: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    init_db()
    if not name.strip():
        raise ValueError("name required")
    if not (user_prompt or "").strip():
        raise ValueError("user_prompt required")
    roster = list(roster or DEFAULT_ROSTER)
    # Dedupe + validate roster entries.
    seen = set()
    clean: List[Dict[str, str]] = []
    for r in roster:
        p = str(r.get("provider") or "").strip()
        m = str(r.get("model") or "").strip()
        if not p or not m:
            continue
        key = f"{p}:{m}"
        if key in seen:
            continue
        seen.add(key)
        clean.append({"provider": p, "model": m})
    if len(clean) < 2:
        raise ValueError("frontier needs at least 2 candidate models")
    temperature = _clip_float(temperature, 0.0, 2.0, DEFAULT_TEMPERATURE)
    top_p = _clip_float(top_p, 0.0, 1.0, DEFAULT_TOP_P)
    n_replays = _clip_int(n_replays, MIN_N_REPLAYS, MAX_N_REPLAYS, DEFAULT_N_REPLAYS)
    monthly_calls = _clip_int(monthly_calls, 100, 10_000_000, DEFAULT_MONTHLY_CALLS)
    qf = None
    if quality_floor is not None:
        qf = _clip_float(quality_floor, 0.0, 100.0, 0.0)
    bc = None
    if budget_ceiling is not None:
        bc = _clip_float(budget_ceiling, 0.0, 1000.0, 0.0)

    run_id = uuid.uuid4().hex[:12]
    now = _now()
    summary = {"roster": clean}
    with _DB_LOCK, _conn() as con:
        con.execute(
            """
            INSERT INTO frontier_runs (
                id, name, description, system_prompt, user_prompt,
                temperature, top_p, n_replays, monthly_calls,
                quality_floor, budget_ceiling, status, dryrun,
                summary_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'queued', ?, ?, ?, ?)
            """,
            (
                run_id, name.strip(), description.strip(),
                system_prompt or "", user_prompt.strip(),
                temperature, top_p, n_replays, monthly_calls,
                qf, bc, 1 if dryrun else 0,
                json.dumps(summary), now, now,
            ),
        )
    return get_frontier(run_id) or {}


def list_frontiers(
    *,
    q: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> Tuple[List[Dict[str, Any]], int]:
    init_db()
    where: List[str] = []
    args: List[Any] = []
    if q:
        where.append("(name LIKE ? OR description LIKE ?)")
        like = f"%{q}%"
        args.extend([like, like])
    if status:
        where.append("status = ?")
        args.append(status)
    sql_where = ("WHERE " + " AND ".join(where)) if where else ""
    with _DB_LOCK, _conn() as con:
        total = con.execute(f"SELECT COUNT(*) FROM frontier_runs {sql_where}", args).fetchone()[0]
        rows = con.execute(
            f"SELECT * FROM frontier_runs {sql_where} ORDER BY updated_at DESC LIMIT ? OFFSET ?",
            args + [int(limit), int(offset)],
        ).fetchall()
    return [_row_to_run(r) for r in rows], int(total)


def get_frontier(run_id: str, *, with_points: bool = True) -> Optional[Dict[str, Any]]:
    init_db()
    with _DB_LOCK, _conn() as con:
        row = con.execute("SELECT * FROM frontier_runs WHERE id = ?", (run_id,)).fetchone()
        if not row:
            return None
        run = _row_to_run(row)
        if with_points:
            prows = con.execute(
                "SELECT * FROM frontier_points WHERE frontier_id = ? ORDER BY cost_per_call ASC",
                (run_id,),
            ).fetchall()
            run["points"] = [_row_to_point(r) for r in prows]
    return run


def delete_frontier(run_id: str) -> bool:
    init_db()
    with _DB_LOCK, _conn() as con:
        cur = con.execute("DELETE FROM frontier_runs WHERE id = ?", (run_id,))
        con.execute("DELETE FROM frontier_points WHERE frontier_id = ?", (run_id,))
        return cur.rowcount > 0


def stats() -> Dict[str, Any]:
    init_db()
    with _DB_LOCK, _conn() as con:
        total = con.execute("SELECT COUNT(*) FROM frontier_runs").fetchone()[0]
        completed = con.execute(
            "SELECT COUNT(*) FROM frontier_runs WHERE status='succeeded'"
        ).fetchone()[0]
        agg = con.execute(
            """SELECT AVG(top_quality), AVG(elbow_quality), AVG(monthly_savings),
                      AVG(quality_kept_pct), SUM(monthly_savings)
                 FROM frontier_runs WHERE status='succeeded'"""
        ).fetchone()
        last_row = con.execute(
            "SELECT id, name, updated_at, elbow_model, monthly_savings "
            "FROM frontier_runs ORDER BY updated_at DESC LIMIT 1"
        ).fetchone()
    return {
        "total_runs": int(total or 0),
        "completed_runs": int(completed or 0),
        "avg_top_quality": round(float(agg[0]), 2) if agg and agg[0] is not None else None,
        "avg_elbow_quality": round(float(agg[1]), 2) if agg and agg[1] is not None else None,
        "avg_monthly_savings": round(float(agg[2]), 2) if agg and agg[2] is not None else None,
        "avg_quality_kept_pct": round(float(agg[3]), 1) if agg and agg[3] is not None else None,
        "total_monthly_savings": round(float(agg[4] or 0), 2) if agg else 0.0,
        "last_run": dict(last_row) if last_row else None,
    }


# ---------------------------------------------------------------------------
# Engine — per-model replay batch → aggregate → Pareto → elbow → recommend.
# ---------------------------------------------------------------------------

def _run_one_model(
    *,
    provider: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float,
    top_p: float,
    n_replays: int,
    expected_keywords: List[str],
    baseline_text: str,
    dryrun: bool,
    provider_factory,
) -> Dict[str, Any]:
    """Fire ``n_replays`` calls for one candidate, score them, aggregate."""
    if dryrun:
        replays = [
            _dry_call(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                provider=provider,
                model=model,
                replay_index=i,
                expected_keywords=expected_keywords,
            )
            for i in range(n_replays)
        ]
    else:
        replays = []
        with ThreadPoolExecutor(max_workers=min(n_replays, 4)) as pool:
            futures = {
                pool.submit(
                    _live_call,
                    provider_factory=provider_factory,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    provider=provider,
                    model=model,
                    temperature=temperature,
                    top_p=top_p,
                    replay_index=i,
                ): i
                for i in range(n_replays)
            }
            for fut in as_completed(futures):
                i = futures[fut]
                try:
                    r = fut.result()
                except Exception as exc:  # noqa: BLE001
                    r = {
                        "replay_index": i, "status": "error", "error": str(exc),
                        "response": "", "latency_ms": 0, "input_tokens": 0,
                        "output_tokens": 0, "tier": _tier_for(model), "cost_usd": 0.0,
                    }
                replays.append(r)
        replays.sort(key=lambda r: r["replay_index"])

    ok = [r for r in replays if r["status"] == "success"]
    total_cost = sum(float(r.get("cost_usd") or 0) for r in replays)
    if not ok:
        return {
            "provider": provider, "model": model, "tier": _tier_for(model),
            "quality": None, "quality_stdev": 0.0,
            "cost_per_call": None, "latency_ms": 0.0,
            "input_tokens": 0, "output_tokens": 0,
            "replays_ok": 0, "replays_total": len(replays),
            "medoid_sample": "", "total_cost": total_cost,
        }

    qualities = [
        composite_score(r["response"], expected_keywords=expected_keywords, baseline=baseline_text)
        for r in ok
    ]
    q_mean = round(_mean(qualities), 2)
    q_sd = round(_stdev(qualities), 2)
    latency_mean = _mean([float(r.get("latency_ms") or 0) for r in ok])
    in_tok_mean = int(round(_mean([r.get("input_tokens") or 0 for r in ok])))
    out_tok_mean = int(round(_mean([r.get("output_tokens") or 0 for r in ok])))
    # Cost per call: use the mean tokens through the pricing table so the
    # dashboard shows what a *typical* call costs, not the sum of replays.
    cost_per_call = float(estimate_cost(model, in_tok_mean, out_tok_mean))
    med = _medoid(ok) or ok[0]
    med_body = (med.get("response") or "")
    if len(med_body) > 600:
        med_body = med_body[:597].rstrip() + "…"

    return {
        "provider": provider,
        "model": model,
        "tier": _tier_for(model),
        "quality": q_mean,
        "quality_stdev": q_sd,
        "cost_per_call": round(cost_per_call, 6),
        "latency_ms": round(latency_mean, 1),
        "input_tokens": in_tok_mean,
        "output_tokens": out_tok_mean,
        "replays_ok": len(ok),
        "replays_total": len(replays),
        "medoid_sample": med_body,
        "total_cost": round(total_cost, 6),
    }


def run_frontier(
    frontier_id: str,
    *,
    provider_factory,
    confirm_live: bool = False,
) -> Tuple[Dict[str, Any], int]:
    """Execute a frontier run: for each roster model, replay N times,
    aggregate, compute Pareto, kneedle, recommendations. Persist."""
    init_db()
    run = get_frontier(frontier_id, with_points=False)
    if not run:
        return {"success": False, "error": "frontier run not found"}, 404
    if run["status"] == "running":
        return {"success": False, "error": "frontier run already running"}, 400
    if not run["dryrun"] and not confirm_live:
        return {
            "success": False,
            "error": "live frontier run: pass confirm_live=true (this will spend API credits)",
        }, 400

    roster: List[Dict[str, str]] = list(run["summary"].get("roster") or DEFAULT_ROSTER)
    if len(roster) < 2:
        return {"success": False, "error": "roster must include at least 2 models"}, 400

    # Reset any prior points — a run is re-runnable in place.
    with _DB_LOCK, _conn() as con:
        con.execute("DELETE FROM frontier_points WHERE frontier_id = ?", (frontier_id,))
        con.execute(
            "UPDATE frontier_runs SET status='running', updated_at=? WHERE id=?",
            (_now(), frontier_id),
        )

    started = time.time()
    system_prompt = run["system_prompt"]
    user_prompt = run["user_prompt"]
    expected_keywords = _keywords_from(system_prompt + "\n" + user_prompt, k=14)

    # Pick a baseline for fidelity scoring — the medoid of the highest-tier
    # roster member's replays. That anchors "faithful" to what the premium
    # model says, which is the intuition Frontier is built on.
    priority = ["flagship", "premium", "mid", "efficient", "budget"]
    def _pri(m: Dict[str, str]) -> int:
        return priority.index(_tier_for(m["model"])) if _tier_for(m["model"]) in priority else 99
    anchor = sorted(roster, key=_pri)[0]
    anchor_result = _run_one_model(
        provider=anchor["provider"], model=anchor["model"],
        system_prompt=system_prompt, user_prompt=user_prompt,
        temperature=run["temperature"], top_p=run["top_p"],
        n_replays=run["n_replays"], expected_keywords=expected_keywords,
        baseline_text="", dryrun=run["dryrun"],
        provider_factory=provider_factory,
    )
    baseline_text = anchor_result.get("medoid_sample") or ""

    # Score every roster member (including the anchor, so it appears on the
    # chart alongside cheaper alternatives).
    points: List[Dict[str, Any]] = []
    total_cost = 0.0
    for m in roster:
        if m["provider"] == anchor["provider"] and m["model"] == anchor["model"]:
            pt = dict(anchor_result)
        else:
            pt = _run_one_model(
                provider=m["provider"], model=m["model"],
                system_prompt=system_prompt, user_prompt=user_prompt,
                temperature=run["temperature"], top_p=run["top_p"],
                n_replays=run["n_replays"], expected_keywords=expected_keywords,
                baseline_text=baseline_text, dryrun=run["dryrun"],
                provider_factory=provider_factory,
            )
        total_cost += float(pt.get("total_cost") or 0)
        points.append(pt)

    # Recompute anchor's quality against itself as baseline — trivially high
    # fidelity — is a distortion, so re-score with an empty baseline for the
    # anchor row (falls back to a plain non-emptiness proxy). We do this by
    # re-scoring against the *other* points' median-length response instead.
    non_anchor_responses = [
        p.get("medoid_sample", "")
        for p in points
        if not (p["provider"] == anchor["provider"] and p["model"] == anchor["model"])
    ]
    if non_anchor_responses:
        alt_baseline = max(non_anchor_responses, key=len)
        anchor_row = next(
            (p for p in points if p["provider"] == anchor["provider"] and p["model"] == anchor["model"]),
            None,
        )
        if anchor_row and anchor_row.get("medoid_sample"):
            anchor_row["quality"] = round(
                composite_score(
                    anchor_row["medoid_sample"],
                    expected_keywords=expected_keywords,
                    baseline=alt_baseline,
                ),
                2,
            )

    # Compute Pareto + elbow.
    frontier = compute_pareto(points)
    elbow_idx = kneedle_elbow(frontier)
    elbow_point = frontier[elbow_idx] if elbow_idx is not None and frontier else None
    # Flag elbow on the stored points so the UI can render a star without
    # re-deriving the elbow client-side.
    for p in points:
        p["is_elbow"] = bool(
            elbow_point and _key(p) == _key(elbow_point)
        )

    # Winners / summary.
    valid = [p for p in points if p["quality"] is not None and p["cost_per_call"] is not None]
    top_q_point = max(valid, key=lambda x: (x["quality"], -x["cost_per_call"])) if valid else None
    cheap_point = min(valid, key=lambda x: (x["cost_per_call"], -x["quality"])) if valid else None

    monthly_calls = int(run["monthly_calls"])

    # Per-point monthly cost + savings vs top-quality.
    top_cost = top_q_point["cost_per_call"] if top_q_point else 0
    for p in points:
        c = p.get("cost_per_call") or 0
        p["monthly_cost"] = round(c * monthly_calls, 2)
        p["monthly_savings"] = round(max(0.0, top_cost - c) * monthly_calls, 2)

    # Recommendations.
    quality_floor = run["quality_floor"]
    budget_ceiling = run["budget_ceiling"]

    def _cheapest_meeting(q: float) -> Optional[Dict[str, Any]]:
        eligible = [p for p in valid if p["quality"] >= q]
        if not eligible:
            return None
        return min(eligible, key=lambda x: (x["cost_per_call"], -x["quality"]))

    def _best_within(b: float) -> Optional[Dict[str, Any]]:
        eligible = [p for p in valid if p["cost_per_call"] <= b]
        if not eligible:
            return None
        return max(eligible, key=lambda x: (x["quality"], -x["cost_per_call"]))

    default_rec = elbow_point or (cheap_point or (top_q_point if top_q_point else None))
    quality_recommend = _cheapest_meeting(quality_floor) if quality_floor is not None else None
    budget_recommend = _best_within(budget_ceiling) if budget_ceiling is not None else None

    # Headline "savings vs top" for whichever pick the elbow lands on.
    elbow_savings = 0.0
    quality_kept_pct = 0.0
    if elbow_point and top_q_point:
        elbow_savings = max(0.0, (top_q_point["cost_per_call"] - elbow_point["cost_per_call"])) * monthly_calls
        if top_q_point["quality"] > 0:
            quality_kept_pct = round(100.0 * elbow_point["quality"] / top_q_point["quality"], 1)

    actions = _actions_from(
        points=points, frontier=frontier, top_q=top_q_point, elbow=elbow_point,
        cheap=cheap_point, monthly_calls=monthly_calls,
    )

    summary_ext = {
        "roster": [{"provider": p["provider"], "model": p["model"]} for p in points],
        "frontier_keys": [_key(p) for p in frontier],
        "elbow_key": _key(elbow_point) if elbow_point else None,
        "expected_keywords": expected_keywords,
        "anchor_key": _key(anchor_result),
        "baseline_medoid": baseline_text[:600] + ("…" if len(baseline_text) > 600 else ""),
        "default_recommendation": _rec_shape(default_rec, monthly_calls, top_q_point),
        "quality_recommendation": _rec_shape(quality_recommend, monthly_calls, top_q_point),
        "budget_recommendation": _rec_shape(budget_recommend, monthly_calls, top_q_point),
        "actions": actions,
    }

    # Persist points.
    now = _now()
    with _DB_LOCK, _conn() as con:
        for p in points:
            con.execute(
                """
                INSERT INTO frontier_points (
                    id, frontier_id, provider, model, tier,
                    quality, quality_stdev, cost_per_call, latency_ms,
                    input_tokens, output_tokens, replays_ok, replays_total,
                    on_frontier, is_elbow, dominates_json, dominated_by_json,
                    medoid_sample, monthly_cost, monthly_savings, rationale,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    uuid.uuid4().hex[:12], frontier_id, p["provider"], p["model"], p["tier"],
                    p.get("quality"), p.get("quality_stdev") or 0,
                    p.get("cost_per_call"), p.get("latency_ms") or 0,
                    p.get("input_tokens") or 0, p.get("output_tokens") or 0,
                    p.get("replays_ok") or 0, p.get("replays_total") or 0,
                    1 if p.get("on_frontier") else 0, 1 if p.get("is_elbow") else 0,
                    json.dumps(p.get("dominates") or []),
                    json.dumps(p.get("dominated_by") or []),
                    p.get("medoid_sample") or "",
                    p.get("monthly_cost") or 0,
                    p.get("monthly_savings") or 0,
                    _point_rationale(p, top_q_point, elbow_point),
                    now,
                ),
            )

    duration = round(time.time() - started, 3)
    with _DB_LOCK, _conn() as con:
        con.execute(
            """
            UPDATE frontier_runs SET
                status='succeeded',
                total_models=?, frontier_size=?,
                top_quality=?, top_quality_model=?, top_quality_cost=?,
                cheapest_cost=?, cheapest_model=?,
                elbow_model=?, elbow_quality=?, elbow_cost=?,
                monthly_savings=?, quality_kept_pct=?,
                total_cost=?, duration=?, summary_json=?, updated_at=?
            WHERE id=?
            """,
            (
                len(points), len(frontier),
                top_q_point["quality"] if top_q_point else None,
                _key(top_q_point) if top_q_point else "",
                top_q_point["cost_per_call"] if top_q_point else None,
                cheap_point["cost_per_call"] if cheap_point else None,
                _key(cheap_point) if cheap_point else "",
                _key(elbow_point) if elbow_point else "",
                elbow_point["quality"] if elbow_point else None,
                elbow_point["cost_per_call"] if elbow_point else None,
                round(elbow_savings, 2), round(quality_kept_pct, 1),
                round(total_cost, 6), duration,
                json.dumps({**run["summary"], **summary_ext}), now, frontier_id,
            ),
        )

    return {"success": True, "frontier": get_frontier(frontier_id)}, 200


# ---------------------------------------------------------------------------
# Rationales / actions.
# ---------------------------------------------------------------------------

def _rec_shape(point: Optional[Dict[str, Any]], monthly_calls: int, top: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not point:
        return None
    savings = 0.0
    kept = 100.0
    if top and top.get("cost_per_call") is not None and point.get("cost_per_call") is not None:
        savings = round(max(0.0, top["cost_per_call"] - point["cost_per_call"]) * monthly_calls, 2)
    if top and top.get("quality"):
        kept = round(100.0 * (point.get("quality") or 0) / top["quality"], 1)
    return {
        "provider": point["provider"],
        "model": point["model"],
        "key": _key(point),
        "tier": point.get("tier"),
        "quality": point.get("quality"),
        "cost_per_call": point.get("cost_per_call"),
        "monthly_cost": round((point.get("cost_per_call") or 0) * monthly_calls, 2),
        "monthly_savings": savings,
        "quality_kept_pct": kept,
    }


def _point_rationale(p: Dict[str, Any], top: Optional[Dict[str, Any]], elbow: Optional[Dict[str, Any]]) -> str:
    if p.get("quality") is None:
        return "All replays failed — no valid quality/cost point for this model."
    if elbow and _key(p) == _key(elbow):
        return (
            f"Kneedle elbow — best marginal quality-per-dollar on the Pareto "
            f"frontier ({p['quality']:.0f} pts at ${p['cost_per_call']:.5f}/call)."
        )
    if p.get("on_frontier"):
        return (
            f"On the frontier — no other model dominates this cost/quality point. "
            f"Q={p['quality']:.0f}, ${p['cost_per_call']:.5f}/call."
        )
    dominated_by = p.get("dominated_by") or []
    if dominated_by:
        return (
            f"Dominated by {len(dominated_by)} model{'s' if len(dominated_by) > 1 else ''}: "
            f"{', '.join(dominated_by[:3])}"
            + ("…" if len(dominated_by) > 3 else "")
            + " — both cheaper *and* higher quality."
        )
    return "Off the frontier."


def _actions_from(
    *,
    points: List[Dict[str, Any]],
    frontier: List[Dict[str, Any]],
    top_q: Optional[Dict[str, Any]],
    elbow: Optional[Dict[str, Any]],
    cheap: Optional[Dict[str, Any]],
    monthly_calls: int,
) -> List[str]:
    actions: List[str] = []
    if elbow and top_q and _key(elbow) != _key(top_q):
        savings = max(0.0, top_q["cost_per_call"] - elbow["cost_per_call"]) * monthly_calls
        kept = round(100.0 * elbow["quality"] / top_q["quality"], 0) if top_q["quality"] else 0
        actions.append(
            f"**Ship** *{elbow['model']}* — the elbow keeps ~{kept:.0f}% of *{top_q['model']}*'s "
            f"quality at **${savings:,.0f}/mo** savings on {monthly_calls:,} calls."
        )
    if elbow and top_q and _key(elbow) == _key(top_q):
        actions.append(
            f"The frontier's elbow *is* the top-quality model (*{top_q['model']}*) — "
            "there's no cheaper Pareto pick for this prompt."
        )
    dominated = [p for p in points if p.get("dominated_by")]
    if dominated:
        worst = max(dominated, key=lambda p: len(p.get("dominated_by") or []))
        actions.append(
            f"**Drop** *{worst['model']}* — dominated by "
            f"{len(worst.get('dominated_by') or [])} other model"
            f"{'s' if len(worst.get('dominated_by') or []) > 1 else ''} on both axes."
        )
    if cheap and elbow and _key(cheap) != _key(elbow):
        gap = round(elbow["quality"] - cheap["quality"], 1)
        if gap >= 8:
            actions.append(
                f"For batch / non-critical calls, *{cheap['model']}* trades ~{gap:.0f} pts of "
                f"quality for ${(elbow['cost_per_call'] - cheap['cost_per_call']) * monthly_calls:,.0f}/mo "
                "more savings."
            )
    if len(frontier) >= 2:
        actions.append(
            f"Frontier has **{len(frontier)} candidates** — {', '.join(p['model'] for p in frontier[:5])}"
            + ("…" if len(frontier) > 5 else "")
            + " — every other roster model is dominated."
        )
    if not actions:
        actions.append("Every roster model landed at similar cost/quality — the frontier is flat.")
    return actions


# ---------------------------------------------------------------------------
# Seed demo — lights up the page on first load.
# ---------------------------------------------------------------------------

_DEMO_SYSTEM_PROMPT = (
    "You are a senior support engineer at a fintech company. When a customer "
    "reports a payment issue, you must: (1) identify the transaction by "
    "reference ID, (2) check the reconciliation status against our ledger, "
    "(3) classify the failure (network timeout, insufficient funds, fraud "
    "block, ledger mismatch), (4) recommend the next step, and (5) close "
    "with a concise summary a manager could paste into a ticket. Be precise, "
    "cite the exact reference the customer gave, and never promise refunds."
)

_DEMO_USER_PROMPT = (
    "Hi — I'm Priya from Northwind Analytics. Our merchant account "
    "transaction TX-2026-07-04-891 for $2,480.00 was declined this morning. "
    "The dashboard says 'network error retry' but the funds are on hold. "
    "Can you check what's going on and tell me if I should retry?"
)


def seed_demo() -> Dict[str, Any]:
    init_db()
    run = create_frontier(
        name="Fintech support — model-selection frontier",
        description=(
            "Sample Frontier run: fan a support-engineer prompt across nine "
            "models spanning flagship / premium / mid / efficient / budget "
            "tiers, then pick the elbow."
        ),
        system_prompt=_DEMO_SYSTEM_PROMPT,
        user_prompt=_DEMO_USER_PROMPT,
        temperature=0.4,
        n_replays=3,
        monthly_calls=50_000,
        quality_floor=70.0,
        budget_ceiling=0.005,
        dryrun=True,
    )
    from src.providers.provider_factory import ProviderFactory  # local import to avoid cycle
    payload, _ = run_frontier(run["id"], provider_factory=ProviderFactory(), confirm_live=False)
    return payload.get("frontier") or run
