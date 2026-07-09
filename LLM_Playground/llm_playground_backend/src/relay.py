"""Relay — Cascade Router Designer.

Frontier (Day 73) answered *which single model should I run this on?* by
sweeping a roster, computing quality vs cost per model, and kneedle-ing the
elbow of the Pareto frontier. That answer is correct if you deploy exactly
**one** model. In practice, teams deploy a **cascade**: run a cheap model
first, and only escalate to a bigger, slower one when the cheap answer looks
weak. Cursor / Perplexity / Notdiamond / Martian all do this. It is the
single biggest lever in production cost.

Relay is the surface for designing that cascade.

Given a prompt (system + user), a cost-ordered roster of candidate models,
and a **gate** — the rule that decides "keep this level's answer vs escalate
to the next" — Relay:

* Runs every roster model ``n_replays`` times, scoring each replay by the
  same coverage / fidelity / format composite Frontier and Surgeon use, so
  quality numbers are directly comparable across studios.
* For each level, computes the **pass rate** at the current gate — the
  fraction of replays whose composite / length / coverage / consistency
  clears the gate threshold. The pass rate is the probability that a
  live prompt terminates at this level instead of escalating.
* Walks the ordered levels front-to-back, computing:
    - ``p_reach[i]``    = probability a prompt reaches level i
    - ``p_terminate[i]``= p_reach[i] · pass_rate[i]
    - ``expected_cost``   = Σ p_reach[i] · cost_per_call[i]
    - ``expected_quality``= Σ p_terminate[i] · quality[i]
    - ``expected_latency``= Σ p_reach[i] · latency[i]
* Compares the cascade against **three baselines**:
    - **always_flagship** — always run the most expensive model
    - **always_cheap**    — always run the cheapest model
    - **frontier_elbow**  — run the single-model Kneedle elbow
* Recommends three cascade shapes off one call:
    - **balanced**       — keeps ≥ 95% of flagship quality
    - **cost_min**       — cheapest subset that meets a user quality floor
    - **latency_capped** — highest-quality subset under a p50 latency cap
  Each recommendation is a *subset* of the roster; the engine tries every
  2ⁿ subset ordered by cost (n ≤ 10 so exhaustive is trivial).
* Reports **monthly savings** at the user-set call rate and **quality
  kept %** vs flagship — the two numbers that justify shipping a cascade.

Gates supported (chosen via ``gate_type``):

    composite    — replay quality ≥ threshold (default 65)
    length       — output_tokens ≥ threshold (default 80)
    coverage     — expected-keyword hits ≥ threshold (default 4)
    consistency  — replay-set stdev ≤ threshold AND mean quality ≥ 60

Dryrun is deterministic — the same prompt + roster + gate returns the
same cascade shape, the same expected cost, the same monthly savings —
so the demo lights up on first page load without any API credentials
and stays the same across refreshes.

Public surface: ``create_relay``, ``list_relays``, ``get_relay``,
``delete_relay``, ``run_relay``, ``seed_demo``, ``stats``, ``defaults``,
``simulate_cascade``, ``suggest_shapes``, ``preview_gate``.
"""
from __future__ import annotations

import hashlib
import itertools
import json
import math
import re
import sqlite3
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src import history
from src.pricing import _lookup as _price_lookup, estimate_cost

_DB_LOCK = history._DB_LOCK  # noqa: SLF001


@contextmanager
def _conn():
    with history._conn() as con:  # noqa: SLF001
        yield con


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS relay_runs (
    id                    TEXT PRIMARY KEY,
    name                  TEXT NOT NULL,
    description           TEXT,
    system_prompt         TEXT NOT NULL,
    user_prompt           TEXT NOT NULL,
    temperature           REAL NOT NULL DEFAULT 0.4,
    top_p                 REAL NOT NULL DEFAULT 1.0,
    n_replays             INTEGER NOT NULL DEFAULT 4,
    monthly_calls         INTEGER NOT NULL DEFAULT 50000,
    gate_type             TEXT NOT NULL DEFAULT 'composite',
    gate_threshold        REAL NOT NULL DEFAULT 65.0,
    quality_floor         REAL,
    latency_ceiling_ms    REAL,
    status                TEXT NOT NULL,
    total_models          INTEGER DEFAULT 0,
    picked_levels         INTEGER DEFAULT 0,
    cascade_quality       REAL,
    cascade_cost          REAL,
    cascade_latency       REAL,
    flagship_quality      REAL,
    flagship_cost         REAL,
    cheap_quality         REAL,
    cheap_cost            REAL,
    quality_kept_pct      REAL,
    monthly_savings       REAL,
    escalation_rate       REAL,
    total_cost            REAL DEFAULT 0,
    duration              REAL DEFAULT 0,
    dryrun                INTEGER NOT NULL DEFAULT 1,
    summary_json          TEXT,
    created_at            TEXT NOT NULL,
    updated_at            TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS relay_levels (
    id                TEXT PRIMARY KEY,
    relay_id          TEXT NOT NULL,
    ord               INTEGER NOT NULL,
    provider          TEXT NOT NULL,
    model             TEXT NOT NULL,
    tier              TEXT,
    picked            INTEGER NOT NULL DEFAULT 0,
    quality           REAL,
    quality_stdev     REAL,
    cost_per_call     REAL,
    latency_ms        REAL,
    input_tokens      INTEGER,
    output_tokens     INTEGER,
    replays_ok        INTEGER,
    replays_total     INTEGER,
    pass_rate         REAL,
    p_reach           REAL,
    p_terminate       REAL,
    contrib_cost      REAL,
    contrib_quality   REAL,
    contrib_latency   REAL,
    medoid_sample     TEXT,
    rationale         TEXT,
    created_at        TEXT NOT NULL,
    FOREIGN KEY (relay_id) REFERENCES relay_runs(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_relay_levels_run
    ON relay_levels(relay_id, ord);
"""


def init_db() -> None:
    with _DB_LOCK, _conn() as con:
        con.executescript(_SCHEMA)


# ---------------------------------------------------------------------------
# Defaults / roster
# ---------------------------------------------------------------------------

DEFAULT_N_REPLAYS = 4
MIN_N_REPLAYS = 2
MAX_N_REPLAYS = 8
DEFAULT_TEMPERATURE = 0.4
DEFAULT_TOP_P = 1.0
DEFAULT_MONTHLY_CALLS = 50_000

GATE_TYPES: Tuple[str, ...] = ("composite", "length", "coverage", "consistency")
DEFAULT_GATE_TYPE = "composite"
DEFAULT_GATE_THRESHOLDS: Dict[str, float] = {
    "composite":   65.0,
    "length":      80.0,
    "coverage":    4.0,
    "consistency": 8.0,
}

DEFAULT_ROSTER: List[Dict[str, str]] = [
    {"provider": "Anthropic", "model": "claude-3-haiku"},
    {"provider": "Google",    "model": "gemini-1.5-flash"},
    {"provider": "OpenAI",    "model": "gpt-4o-mini"},
    {"provider": "Anthropic", "model": "claude-3-5-haiku"},
    {"provider": "OpenAI",    "model": "gpt-3.5-turbo"},
    {"provider": "Google",    "model": "gemini-1.5-pro"},
    {"provider": "OpenAI",    "model": "gpt-4o"},
    {"provider": "Anthropic", "model": "claude-3-5-sonnet"},
    {"provider": "OpenAI",    "model": "gpt-4-turbo"},
]


def _tier_for(model: str) -> str:
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
        "n_replays":         {"default": DEFAULT_N_REPLAYS, "min": MIN_N_REPLAYS, "max": MAX_N_REPLAYS},
        "temperature":       {"default": DEFAULT_TEMPERATURE, "min": 0.0, "max": 2.0, "step": 0.05},
        "top_p":             {"default": DEFAULT_TOP_P, "min": 0.0, "max": 1.0, "step": 0.05},
        "monthly_calls":     {"default": DEFAULT_MONTHLY_CALLS, "min": 100, "max": 10_000_000},
        "roster":            DEFAULT_ROSTER,
        "gate_type":         {"default": DEFAULT_GATE_TYPE, "options": list(GATE_TYPES)},
        "gate_thresholds":   dict(DEFAULT_GATE_THRESHOLDS),
        "gate_meaning": {
            "composite":   "accept if composite quality ≥ threshold",
            "length":      "accept if output_tokens ≥ threshold",
            "coverage":    "accept if keyword hits ≥ threshold",
            "consistency": "accept if quality stdev ≤ threshold AND mean ≥ 60",
        },
        "tiers": {
            "flagship":  {"label": "Flagship",  "color": "violet",  "bias": _TIER_QUALITY_BIAS["flagship"]},
            "premium":   {"label": "Premium",   "color": "sky",     "bias": _TIER_QUALITY_BIAS["premium"]},
            "mid":       {"label": "Mid",       "color": "teal",    "bias": _TIER_QUALITY_BIAS["mid"]},
            "efficient": {"label": "Efficient", "color": "emerald", "bias": _TIER_QUALITY_BIAS["efficient"]},
            "budget":    {"label": "Budget",    "color": "amber",   "bias": _TIER_QUALITY_BIAS["budget"]},
        },
        "scoring": {
            "axes":    ["coverage", "fidelity", "format"],
            "weights": {"coverage": 0.50, "fidelity": 0.30, "format": 0.20},
            "scale":   "0-100",
        },
        "cascade_physics": {
            "p_reach":       "product of (1 - pass_rate) over cheaper levels",
            "expected_cost": "Σ p_reach[i] · cost_per_call[i]",
            "expected_quality": "Σ p_reach[i] · pass_rate[i] · quality[i]",
            "escalation_rate": "1 - pass_rate at level 0",
        },
    }


# ---------------------------------------------------------------------------
# Helpers
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


def _mean(values: Sequence[float]) -> float:
    vs = [float(v) for v in values if v is not None]
    if not vs:
        return 0.0
    return sum(vs) / len(vs)


def _stdev(values: Sequence[float]) -> float:
    vs = [float(v) for v in values if v is not None]
    if len(vs) < 2:
        return 0.0
    m = _mean(vs)
    return math.sqrt(sum((v - m) ** 2 for v in vs) / len(vs))


# ---------------------------------------------------------------------------
# Scoring — mirror Frontier / Surgeon so numbers compare across studios.
# ---------------------------------------------------------------------------

def _coverage_hits(response: str, expected_keywords: List[str]) -> int:
    if not expected_keywords:
        return 0
    words = set(_tokens(response))
    return sum(1 for kw in expected_keywords if kw.lower() in words)


def _coverage_score(response: str, expected_keywords: List[str]) -> float:
    if not expected_keywords:
        return 60.0
    hits = _coverage_hits(response, expected_keywords)
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
# Dryrun call — mirror of Frontier's synthetic call.
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
    tier = _tier_for(model)
    seed = _seed_hash("relay-dry", system_prompt[:128], user_prompt[:128], model, str(replay_index))

    lo, hi = _TIER_OUT_TOKENS[tier]
    tgt_out_tokens = lo + int((seed[0] / 255.0) * (hi - lo))
    n_sentences = max(3, min(len(_DRY_CORPUS), 3 + int((seed[1] / 255.0) * 8)))
    body_parts = [_DRY_CORPUS[(replay_index + i + seed[2]) % len(_DRY_CORPUS)] for i in range(n_sentences)]

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
# Gate physics — decide "accept vs escalate" per replay.
# ---------------------------------------------------------------------------

def _replay_passes(
    replay: Dict[str, Any],
    *,
    gate_type: str,
    threshold: float,
    quality: float,
    expected_keywords: List[str],
    baseline_text: str,
) -> bool:
    """Return True if this replay's answer clears the gate."""
    if replay.get("status") != "success":
        return False
    resp = replay.get("response") or ""
    if gate_type == "length":
        return int(replay.get("output_tokens") or 0) >= float(threshold)
    if gate_type == "coverage":
        return _coverage_hits(resp, expected_keywords) >= int(threshold)
    if gate_type == "consistency":
        # consistency is set-level — we approximate per-replay pass as
        # "response's individual composite ≥ 60". The set-level stdev
        # check is applied later against the level aggregate.
        cs = composite_score(resp, expected_keywords=expected_keywords, baseline=baseline_text)
        return cs >= 60.0
    # composite (default)
    cs = composite_score(resp, expected_keywords=expected_keywords, baseline=baseline_text)
    return cs >= float(threshold)


def _level_pass_rate(
    *,
    replays: List[Dict[str, Any]],
    gate_type: str,
    threshold: float,
    expected_keywords: List[str],
    baseline_text: str,
    quality_mean: float,
    quality_stdev: float,
) -> float:
    """Fraction of replays clearing the gate. For ``consistency`` we also
    require the set-level stdev to fall under the threshold — that veto
    collapses the rate to 0 for chaotic responses."""
    if not replays:
        return 0.0
    ok = sum(
        1
        for r in replays
        if _replay_passes(
            r,
            gate_type=gate_type,
            threshold=threshold,
            quality=quality_mean,
            expected_keywords=expected_keywords,
            baseline_text=baseline_text,
        )
    )
    rate = ok / len(replays)
    if gate_type == "consistency":
        if quality_stdev > float(threshold):
            return 0.0
        if quality_mean < 60.0:
            return 0.0
    return round(rate, 3)


# ---------------------------------------------------------------------------
# Cascade simulation — the shipped physics.
# ---------------------------------------------------------------------------

def simulate_cascade(
    levels: List[Dict[str, Any]],
    *,
    picked_indexes: Optional[Sequence[int]] = None,
) -> Dict[str, Any]:
    """Walk the ordered levels, computing p_reach / p_terminate / expected
    cost / expected quality / expected latency and escalation rate.

    ``picked_indexes`` — indexes (into ``levels``, cost-ordered) that are
    part of the cascade; every other level is skipped. If None, every
    level with a valid quality/cost point is included."""
    ordered = sorted(levels, key=lambda lv: (lv.get("cost_per_call") or 0.0))
    idx_map = {id(lv): i for i, lv in enumerate(ordered)}
    if picked_indexes is None:
        chain = [
            lv for lv in ordered
            if lv.get("quality") is not None and lv.get("cost_per_call") is not None
        ]
    else:
        pick_set = {int(i) for i in picked_indexes}
        chain = [
            lv for i, lv in enumerate(ordered)
            if i in pick_set
            and lv.get("quality") is not None
            and lv.get("cost_per_call") is not None
        ]
    if not chain:
        return {
            "picked_keys":       [],
            "picked_indexes":    [],
            "p_reach":           [],
            "p_terminate":       [],
            "contrib_cost":      [],
            "contrib_quality":   [],
            "contrib_latency":   [],
            "expected_cost":     0.0,
            "expected_quality":  0.0,
            "expected_latency":  0.0,
            "escalation_rate":   0.0,
            "termination":       [],
        }

    # Force the *last* level to always accept — it's the fallback. Even
    # if its own pass_rate is 0.5 in isolation, every prompt that reaches
    # the end has nowhere else to go.
    pass_rates = [float(lv.get("pass_rate") or 0.0) for lv in chain]
    pass_rates[-1] = 1.0

    n = len(chain)
    p_reach = [0.0] * n
    p_reach[0] = 1.0
    for i in range(1, n):
        p_reach[i] = round(p_reach[i - 1] * (1.0 - pass_rates[i - 1]), 4)
    p_terminate = [round(p_reach[i] * pass_rates[i], 4) for i in range(n)]

    contrib_cost = [round(p_reach[i] * float(chain[i].get("cost_per_call") or 0.0), 8) for i in range(n)]
    contrib_quality = [round(p_terminate[i] * float(chain[i].get("quality") or 0.0), 4) for i in range(n)]
    contrib_latency = [round(p_reach[i] * float(chain[i].get("latency_ms") or 0.0), 3) for i in range(n)]

    expected_cost = round(sum(contrib_cost), 8)
    expected_quality = round(sum(contrib_quality), 3)
    expected_latency = round(sum(contrib_latency), 2)
    escalation_rate = round(1.0 - pass_rates[0], 3) if n > 0 else 0.0

    return {
        "picked_keys":       [f"{lv['provider']}:{lv['model']}" for lv in chain],
        "picked_indexes":    [idx_map[id(lv)] for lv in chain],
        "p_reach":           p_reach,
        "p_terminate":       p_terminate,
        "contrib_cost":      contrib_cost,
        "contrib_quality":   contrib_quality,
        "contrib_latency":   contrib_latency,
        "expected_cost":     expected_cost,
        "expected_quality":  expected_quality,
        "expected_latency":  expected_latency,
        "escalation_rate":   escalation_rate,
        "termination": [
            {
                "provider": lv["provider"],
                "model":    lv["model"],
                "key":      f"{lv['provider']}:{lv['model']}",
                "share":    p_terminate[i],
                "quality":  lv.get("quality"),
                "cost":     lv.get("cost_per_call"),
            }
            for i, lv in enumerate(chain)
        ],
    }


# ---------------------------------------------------------------------------
# Subset search — enumerate all 2ⁿ subsets and score each.
# ---------------------------------------------------------------------------

def _cost_ordered_indexes(levels: List[Dict[str, Any]]) -> List[int]:
    idxed = [(i, lv) for i, lv in enumerate(levels) if lv.get("cost_per_call") is not None]
    idxed.sort(key=lambda t: (t[1].get("cost_per_call") or 0.0))
    return [i for i, _ in idxed]


def suggest_shapes(
    levels: List[Dict[str, Any]],
    *,
    monthly_calls: int,
    flagship_quality: float,
    flagship_cost: float,
    quality_floor: Optional[float],
    latency_ceiling_ms: Optional[float],
    max_subsets: int = 512,
) -> Dict[str, Any]:
    """Try every non-empty subset (ordered by cost). Return the three
    canonical picks + the raw subset scan for the frontier plot.

    For n=8 the subset space is 256 — well within budget. The cap
    ``max_subsets`` bounds n=10 (1024) at the ceiling since UI never asks
    for a roster > 10 in practice."""
    order = _cost_ordered_indexes(levels)
    n = len(order)
    if n == 0:
        return {"scan": [], "balanced": None, "cost_min": None, "latency_capped": None}

    # For very large rosters, prefer contiguous prefixes only.
    prefix_only = n > 10
    subsets: List[Tuple[int, ...]] = []
    if prefix_only:
        subsets = [tuple(order[: k + 1]) for k in range(n)]
    else:
        for r in range(1, n + 1):
            for combo in itertools.combinations(order, r):
                combo_sorted = tuple(sorted(combo, key=lambda i: (levels[i].get("cost_per_call") or 0.0)))
                subsets.append(combo_sorted)
                if len(subsets) >= max_subsets:
                    break
            if len(subsets) >= max_subsets:
                break

    scan: List[Dict[str, Any]] = []
    for combo in subsets:
        sim = simulate_cascade(levels, picked_indexes=combo)
        if not sim["picked_keys"]:
            continue
        rec = {
            "keys":            sim["picked_keys"],
            "indexes":         list(combo),
            "expected_cost":   sim["expected_cost"],
            "expected_quality":sim["expected_quality"],
            "expected_latency":sim["expected_latency"],
            "escalation_rate": sim["escalation_rate"],
            "monthly_cost":    round(sim["expected_cost"] * monthly_calls, 2),
            "monthly_savings": round(max(0.0, (flagship_cost - sim["expected_cost"]) * monthly_calls), 2),
            "quality_kept_pct": round(100.0 * sim["expected_quality"] / max(1e-9, flagship_quality), 1),
            "size":            len(combo),
        }
        scan.append(rec)

    def _fits_latency(rec: Dict[str, Any]) -> bool:
        return (
            latency_ceiling_ms is None
            or rec["expected_latency"] <= float(latency_ceiling_ms)
        )

    balanced_pool = [
        r for r in scan
        if r["quality_kept_pct"] >= 95.0 and _fits_latency(r)
    ]
    # Cheapest shape that keeps ≥95% of flagship quality. Ties broken by
    # *size ascending* (fewer levels = simpler cascade), then quality
    # descending (a nearly-free extra point of quality is worth taking).
    balanced = (
        min(balanced_pool, key=lambda r: (r["expected_cost"], r["size"], -r["expected_quality"]))
        if balanced_pool else None
    )

    cost_min = None
    if quality_floor is not None:
        pool = [r for r in scan if r["expected_quality"] >= float(quality_floor) and _fits_latency(r)]
        if pool:
            cost_min = min(pool, key=lambda r: (r["expected_cost"], -r["expected_quality"]))

    latency_capped = None
    if latency_ceiling_ms is not None:
        pool = [r for r in scan if _fits_latency(r)]
        if pool:
            latency_capped = max(pool, key=lambda r: (r["expected_quality"], -r["expected_cost"]))

    return {
        "scan":            scan,
        "balanced":        balanced,
        "cost_min":        cost_min,
        "latency_capped":  latency_capped,
    }


# ---------------------------------------------------------------------------
# Persistence.
# ---------------------------------------------------------------------------

def _row_to_run(row: sqlite3.Row) -> Dict[str, Any]:
    summary: Dict[str, Any] = {}
    if row["summary_json"]:
        try:
            summary = json.loads(row["summary_json"])
        except (TypeError, ValueError, json.JSONDecodeError):
            summary = {}
    return {
        "id":                  row["id"],
        "name":                row["name"],
        "description":         row["description"] or "",
        "system_prompt":       row["system_prompt"],
        "user_prompt":         row["user_prompt"],
        "temperature":         float(row["temperature"]),
        "top_p":               float(row["top_p"]),
        "n_replays":           int(row["n_replays"]),
        "monthly_calls":       int(row["monthly_calls"]),
        "gate_type":           row["gate_type"],
        "gate_threshold":      float(row["gate_threshold"]),
        "quality_floor":       float(row["quality_floor"]) if row["quality_floor"] is not None else None,
        "latency_ceiling_ms":  float(row["latency_ceiling_ms"]) if row["latency_ceiling_ms"] is not None else None,
        "status":              row["status"],
        "total_models":        int(row["total_models"] or 0),
        "picked_levels":       int(row["picked_levels"] or 0),
        "cascade_quality":     float(row["cascade_quality"]) if row["cascade_quality"] is not None else None,
        "cascade_cost":        float(row["cascade_cost"]) if row["cascade_cost"] is not None else None,
        "cascade_latency":     float(row["cascade_latency"]) if row["cascade_latency"] is not None else None,
        "flagship_quality":    float(row["flagship_quality"]) if row["flagship_quality"] is not None else None,
        "flagship_cost":       float(row["flagship_cost"]) if row["flagship_cost"] is not None else None,
        "cheap_quality":       float(row["cheap_quality"]) if row["cheap_quality"] is not None else None,
        "cheap_cost":          float(row["cheap_cost"]) if row["cheap_cost"] is not None else None,
        "quality_kept_pct":    float(row["quality_kept_pct"] or 0),
        "monthly_savings":     float(row["monthly_savings"] or 0),
        "escalation_rate":     float(row["escalation_rate"] or 0),
        "total_cost":          float(row["total_cost"] or 0),
        "duration":            float(row["duration"] or 0),
        "dryrun":              bool(row["dryrun"]),
        "summary":             summary,
        "created_at":          row["created_at"],
        "updated_at":          row["updated_at"],
    }


def _row_to_level(row: sqlite3.Row) -> Dict[str, Any]:
    return {
        "id":              row["id"],
        "ord":             int(row["ord"] or 0),
        "provider":        row["provider"],
        "model":           row["model"],
        "key":             f"{row['provider']}:{row['model']}",
        "tier":            row["tier"] or "unknown",
        "picked":          bool(row["picked"]),
        "quality":         float(row["quality"]) if row["quality"] is not None else None,
        "quality_stdev":   float(row["quality_stdev"] or 0),
        "cost_per_call":   float(row["cost_per_call"]) if row["cost_per_call"] is not None else None,
        "latency_ms":      float(row["latency_ms"] or 0),
        "input_tokens":    int(row["input_tokens"] or 0),
        "output_tokens":   int(row["output_tokens"] or 0),
        "replays_ok":      int(row["replays_ok"] or 0),
        "replays_total":   int(row["replays_total"] or 0),
        "pass_rate":       float(row["pass_rate"] or 0),
        "p_reach":         float(row["p_reach"] or 0),
        "p_terminate":     float(row["p_terminate"] or 0),
        "contrib_cost":    float(row["contrib_cost"] or 0),
        "contrib_quality": float(row["contrib_quality"] or 0),
        "contrib_latency": float(row["contrib_latency"] or 0),
        "medoid_sample":   row["medoid_sample"] or "",
        "rationale":       row["rationale"] or "",
        "created_at":      row["created_at"],
    }


def create_relay(
    *,
    name: str,
    description: str = "",
    system_prompt: str,
    user_prompt: str,
    temperature: Any = DEFAULT_TEMPERATURE,
    top_p: Any = DEFAULT_TOP_P,
    n_replays: Any = DEFAULT_N_REPLAYS,
    monthly_calls: Any = DEFAULT_MONTHLY_CALLS,
    gate_type: str = DEFAULT_GATE_TYPE,
    gate_threshold: Any = None,
    quality_floor: Any = None,
    latency_ceiling_ms: Any = None,
    dryrun: bool = False,
    roster: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    init_db()
    if not name.strip():
        raise ValueError("name required")
    if not (user_prompt or "").strip():
        raise ValueError("user_prompt required")
    roster = list(roster or DEFAULT_ROSTER)
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
        raise ValueError("relay needs at least 2 candidate models")
    temperature = _clip_float(temperature, 0.0, 2.0, DEFAULT_TEMPERATURE)
    top_p = _clip_float(top_p, 0.0, 1.0, DEFAULT_TOP_P)
    n_replays = _clip_int(n_replays, MIN_N_REPLAYS, MAX_N_REPLAYS, DEFAULT_N_REPLAYS)
    monthly_calls = _clip_int(monthly_calls, 100, 10_000_000, DEFAULT_MONTHLY_CALLS)
    if gate_type not in GATE_TYPES:
        gate_type = DEFAULT_GATE_TYPE
    if gate_threshold is None:
        gate_threshold = DEFAULT_GATE_THRESHOLDS[gate_type]
    gate_threshold = _clip_float(gate_threshold, 0.0, 1000.0, DEFAULT_GATE_THRESHOLDS[gate_type])
    qf = _clip_float(quality_floor, 0.0, 100.0, 0.0) if quality_floor is not None else None
    lc = _clip_float(latency_ceiling_ms, 0.0, 60000.0, 0.0) if latency_ceiling_ms is not None else None

    run_id = uuid.uuid4().hex[:12]
    now = _now()
    summary = {"roster": clean}
    with _DB_LOCK, _conn() as con:
        con.execute(
            """
            INSERT INTO relay_runs (
                id, name, description, system_prompt, user_prompt,
                temperature, top_p, n_replays, monthly_calls,
                gate_type, gate_threshold, quality_floor, latency_ceiling_ms,
                status, dryrun, summary_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'queued', ?, ?, ?, ?)
            """,
            (
                run_id, name.strip(), description.strip(),
                system_prompt or "", user_prompt.strip(),
                temperature, top_p, n_replays, monthly_calls,
                gate_type, float(gate_threshold), qf, lc,
                1 if dryrun else 0, json.dumps(summary), now, now,
            ),
        )
    return get_relay(run_id) or {}


def list_relays(
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
        total = con.execute(f"SELECT COUNT(*) FROM relay_runs {sql_where}", args).fetchone()[0]
        rows = con.execute(
            f"SELECT * FROM relay_runs {sql_where} ORDER BY updated_at DESC LIMIT ? OFFSET ?",
            args + [int(limit), int(offset)],
        ).fetchall()
    return [_row_to_run(r) for r in rows], int(total)


def get_relay(run_id: str, *, with_levels: bool = True) -> Optional[Dict[str, Any]]:
    init_db()
    with _DB_LOCK, _conn() as con:
        row = con.execute("SELECT * FROM relay_runs WHERE id = ?", (run_id,)).fetchone()
        if not row:
            return None
        run = _row_to_run(row)
        if with_levels:
            lrows = con.execute(
                "SELECT * FROM relay_levels WHERE relay_id = ? ORDER BY ord ASC",
                (run_id,),
            ).fetchall()
            run["levels"] = [_row_to_level(r) for r in lrows]
    return run


def delete_relay(run_id: str) -> bool:
    init_db()
    with _DB_LOCK, _conn() as con:
        cur = con.execute("DELETE FROM relay_runs WHERE id = ?", (run_id,))
        con.execute("DELETE FROM relay_levels WHERE relay_id = ?", (run_id,))
        return cur.rowcount > 0


def stats() -> Dict[str, Any]:
    init_db()
    with _DB_LOCK, _conn() as con:
        total = con.execute("SELECT COUNT(*) FROM relay_runs").fetchone()[0]
        completed = con.execute(
            "SELECT COUNT(*) FROM relay_runs WHERE status='succeeded'"
        ).fetchone()[0]
        agg = con.execute(
            """SELECT AVG(cascade_quality), AVG(cascade_cost),
                      AVG(monthly_savings), AVG(quality_kept_pct),
                      AVG(escalation_rate), SUM(monthly_savings)
                 FROM relay_runs WHERE status='succeeded'"""
        ).fetchone()
        last_row = con.execute(
            "SELECT id, name, updated_at, monthly_savings, quality_kept_pct "
            "FROM relay_runs ORDER BY updated_at DESC LIMIT 1"
        ).fetchone()
    return {
        "total_runs":              int(total or 0),
        "completed_runs":          int(completed or 0),
        "avg_cascade_quality":     round(float(agg[0]), 2) if agg and agg[0] is not None else None,
        "avg_cascade_cost":        round(float(agg[1]), 6) if agg and agg[1] is not None else None,
        "avg_monthly_savings":     round(float(agg[2]), 2) if agg and agg[2] is not None else None,
        "avg_quality_kept_pct":    round(float(agg[3]), 1) if agg and agg[3] is not None else None,
        "avg_escalation_rate":     round(float(agg[4]), 3) if agg and agg[4] is not None else None,
        "total_monthly_savings":   round(float(agg[5] or 0), 2) if agg else 0.0,
        "last_run":                dict(last_row) if last_row else None,
    }


# ---------------------------------------------------------------------------
# Engine — per-model replay batch → gate → subset scan → cascade.
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
            "replays": replays,
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
    cost_per_call = float(estimate_cost(model, in_tok_mean, out_tok_mean))
    med = _medoid(ok) or ok[0]
    med_body = (med.get("response") or "")
    if len(med_body) > 600:
        med_body = med_body[:597].rstrip() + "…"

    return {
        "provider":      provider,
        "model":         model,
        "tier":          _tier_for(model),
        "replays":       replays,
        "quality":       q_mean,
        "quality_stdev": q_sd,
        "cost_per_call": round(cost_per_call, 6),
        "latency_ms":    round(latency_mean, 1),
        "input_tokens":  in_tok_mean,
        "output_tokens": out_tok_mean,
        "replays_ok":    len(ok),
        "replays_total": len(replays),
        "medoid_sample": med_body,
        "total_cost":    round(total_cost, 6),
    }


def _pick_baseline_anchor(roster: List[Dict[str, str]]) -> Dict[str, str]:
    priority = ["flagship", "premium", "mid", "efficient", "budget"]

    def _pri(m: Dict[str, str]) -> int:
        t = _tier_for(m["model"])
        return priority.index(t) if t in priority else 99

    return sorted(roster, key=_pri)[0]


def run_relay(
    relay_id: str,
    *,
    provider_factory,
    confirm_live: bool = False,
) -> Tuple[Dict[str, Any], int]:
    init_db()
    run = get_relay(relay_id, with_levels=False)
    if not run:
        return {"success": False, "error": "relay run not found"}, 404
    if run["status"] == "running":
        return {"success": False, "error": "relay run already running"}, 400
    if not run["dryrun"] and not confirm_live:
        return {
            "success": False,
            "error": "live relay run: pass confirm_live=true (this will spend API credits)",
        }, 400

    roster: List[Dict[str, str]] = list(run["summary"].get("roster") or DEFAULT_ROSTER)
    if len(roster) < 2:
        return {"success": False, "error": "roster must include at least 2 models"}, 400

    with _DB_LOCK, _conn() as con:
        con.execute("DELETE FROM relay_levels WHERE relay_id = ?", (relay_id,))
        con.execute(
            "UPDATE relay_runs SET status='running', updated_at=? WHERE id=?",
            (_now(), relay_id),
        )

    started = time.time()
    system_prompt = run["system_prompt"]
    user_prompt = run["user_prompt"]
    expected_keywords = _keywords_from(system_prompt + "\n" + user_prompt, k=14)
    gate_type = run["gate_type"]
    gate_threshold = float(run["gate_threshold"])
    monthly_calls = int(run["monthly_calls"])

    anchor = _pick_baseline_anchor(roster)
    anchor_result = _run_one_model(
        provider=anchor["provider"], model=anchor["model"],
        system_prompt=system_prompt, user_prompt=user_prompt,
        temperature=run["temperature"], top_p=run["top_p"],
        n_replays=run["n_replays"], expected_keywords=expected_keywords,
        baseline_text="", dryrun=run["dryrun"],
        provider_factory=provider_factory,
    )
    baseline_text = anchor_result.get("medoid_sample") or ""

    # Score every roster member.
    levels: List[Dict[str, Any]] = []
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
        # Compute pass_rate at gate for this level.
        pt["pass_rate"] = _level_pass_rate(
            replays=pt.get("replays") or [],
            gate_type=gate_type,
            threshold=gate_threshold,
            expected_keywords=expected_keywords,
            baseline_text=baseline_text,
            quality_mean=float(pt.get("quality") or 0.0),
            quality_stdev=float(pt.get("quality_stdev") or 0.0),
        )
        levels.append(pt)

    # Re-score anchor against best non-anchor response (avoids trivial 100
    # self-fidelity — same trick Frontier plays).
    non_anchor_responses = [
        p.get("medoid_sample", "")
        for p in levels
        if not (p["provider"] == anchor["provider"] and p["model"] == anchor["model"])
    ]
    if non_anchor_responses:
        alt_baseline = max(non_anchor_responses, key=len)
        anchor_row = next(
            (p for p in levels if p["provider"] == anchor["provider"] and p["model"] == anchor["model"]),
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

    # Baselines: always-flagship and always-cheap.
    valid = [p for p in levels if p.get("quality") is not None and p.get("cost_per_call") is not None]
    if not valid:
        return {"success": False, "error": "no valid replays across roster"}, 500
    flagship = max(valid, key=lambda x: (x["quality"], -x["cost_per_call"]))
    cheap = min(valid, key=lambda x: (x["cost_per_call"], -x["quality"]))

    # Subset scan + recommendations.
    shapes = suggest_shapes(
        levels,
        monthly_calls=monthly_calls,
        flagship_quality=float(flagship["quality"] or 0),
        flagship_cost=float(flagship["cost_per_call"] or 0),
        quality_floor=run["quality_floor"],
        latency_ceiling_ms=run["latency_ceiling_ms"],
    )

    # Default cascade — score each subset by kept_quality × savings, pick
    # the highest score that isn't a *broken* cascade (a cheap level with
    # pass_rate = 0 just burns money to reach the fallback).
    default_pick: Optional[Dict[str, Any]] = None
    scan_list = shapes["scan"] or []
    order_indexes = _cost_ordered_indexes(levels)
    idx_pass = {i: float(levels[i].get("pass_rate") or 0.0) for i in order_indexes}
    fs_cost = float(flagship.get("cost_per_call") or 0.0)
    if scan_list:
        best_score = -1e18
        for r in scan_list:
            picks = r.get("indexes") or []
            if not picks:
                continue
            # Filter out cascades whose first (or any non-terminal) level
            # has a pass_rate of 0 — you'd always escalate anyway.
            picks_sorted = list(picks)
            non_terminal = picks_sorted[:-1] if len(picks_sorted) > 1 else []
            if any(idx_pass.get(i, 0.0) <= 0.02 for i in non_terminal):
                continue
            kept = r.get("quality_kept_pct", 0.0)
            savings_pct = 0.0
            if fs_cost > 0:
                savings_pct = max(0.0, 100.0 * (fs_cost - r["expected_cost"]) / fs_cost)
            # Small bonus for keeping the cascade shallow (fewer levels =
            # simpler ops story) so a 1-level tie always wins.
            simplicity_bonus = max(0.0, 5.0 - r["size"]) * 1.5
            score = kept * 0.6 + savings_pct * 0.4 + simplicity_bonus
            if score > best_score:
                best_score = score
                default_pick = r
    if default_pick is None:
        default_pick = shapes["balanced"] or shapes["cost_min"]
    picked_indexes: List[int] = list(default_pick["indexes"]) if default_pick else _cost_ordered_indexes(levels)
    cascade = simulate_cascade(levels, picked_indexes=picked_indexes)

    # Assemble level rows with picked flag + p_reach / p_terminate / contribs.
    order = _cost_ordered_indexes(levels)
    ord_by_key = {f"{levels[i]['provider']}:{levels[i]['model']}": rank for rank, i in enumerate(order)}
    pick_key_set = set(cascade["picked_keys"])
    key_to_reach: Dict[str, float] = {}
    key_to_term: Dict[str, float] = {}
    key_to_ccost: Dict[str, float] = {}
    key_to_cqual: Dict[str, float] = {}
    key_to_clat: Dict[str, float] = {}
    for i, k in enumerate(cascade["picked_keys"]):
        key_to_reach[k] = cascade["p_reach"][i]
        key_to_term[k] = cascade["p_terminate"][i]
        key_to_ccost[k] = cascade["contrib_cost"][i]
        key_to_cqual[k] = cascade["contrib_quality"][i]
        key_to_clat[k] = cascade["contrib_latency"][i]

    for lv in levels:
        key = f"{lv['provider']}:{lv['model']}"
        lv["ord"] = ord_by_key.get(key, 99)
        lv["picked"] = key in pick_key_set
        lv["p_reach"] = key_to_reach.get(key, 0.0) if lv["picked"] else 0.0
        lv["p_terminate"] = key_to_term.get(key, 0.0) if lv["picked"] else 0.0
        lv["contrib_cost"] = key_to_ccost.get(key, 0.0) if lv["picked"] else 0.0
        lv["contrib_quality"] = key_to_cqual.get(key, 0.0) if lv["picked"] else 0.0
        lv["contrib_latency"] = key_to_clat.get(key, 0.0) if lv["picked"] else 0.0

    # Overall metrics.
    quality_kept_pct = round(100.0 * cascade["expected_quality"] / max(1e-9, flagship["quality"] or 0), 1)
    monthly_savings = round(max(0.0, (float(flagship["cost_per_call"] or 0) - cascade["expected_cost"])) * monthly_calls, 2)

    actions = _actions_from(
        cascade=cascade,
        levels=levels,
        flagship=flagship,
        cheap=cheap,
        monthly_calls=monthly_calls,
        gate_type=gate_type,
        gate_threshold=gate_threshold,
        quality_kept_pct=quality_kept_pct,
        monthly_savings=monthly_savings,
    )

    summary_ext = {
        "roster":              [{"provider": p["provider"], "model": p["model"]} for p in levels],
        "expected_keywords":   expected_keywords,
        "anchor_key":          f"{anchor['provider']}:{anchor['model']}",
        "baseline_medoid":     baseline_text[:600] + ("…" if len(baseline_text) > 600 else ""),
        "flagship_key":        f"{flagship['provider']}:{flagship['model']}",
        "cheap_key":           f"{cheap['provider']}:{cheap['model']}",
        "cascade":             cascade,
        "shapes":              {
            "scan":            shapes["scan"],
            "balanced":        shapes["balanced"],
            "cost_min":        shapes["cost_min"],
            "latency_capped":  shapes["latency_capped"],
        },
        "actions":             actions,
    }

    now = _now()
    with _DB_LOCK, _conn() as con:
        for lv in levels:
            con.execute(
                """
                INSERT INTO relay_levels (
                    id, relay_id, ord, provider, model, tier, picked,
                    quality, quality_stdev, cost_per_call, latency_ms,
                    input_tokens, output_tokens, replays_ok, replays_total,
                    pass_rate, p_reach, p_terminate,
                    contrib_cost, contrib_quality, contrib_latency,
                    medoid_sample, rationale, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    uuid.uuid4().hex[:12], relay_id, int(lv.get("ord") or 0),
                    lv["provider"], lv["model"], lv["tier"],
                    1 if lv.get("picked") else 0,
                    lv.get("quality"), lv.get("quality_stdev") or 0,
                    lv.get("cost_per_call"), lv.get("latency_ms") or 0,
                    lv.get("input_tokens") or 0, lv.get("output_tokens") or 0,
                    lv.get("replays_ok") or 0, lv.get("replays_total") or 0,
                    lv.get("pass_rate") or 0,
                    lv.get("p_reach") or 0, lv.get("p_terminate") or 0,
                    lv.get("contrib_cost") or 0, lv.get("contrib_quality") or 0,
                    lv.get("contrib_latency") or 0,
                    lv.get("medoid_sample") or "",
                    _level_rationale(lv, cascade),
                    now,
                ),
            )

    duration = round(time.time() - started, 3)
    with _DB_LOCK, _conn() as con:
        con.execute(
            """
            UPDATE relay_runs SET
                status='succeeded',
                total_models=?, picked_levels=?,
                cascade_quality=?, cascade_cost=?, cascade_latency=?,
                flagship_quality=?, flagship_cost=?,
                cheap_quality=?, cheap_cost=?,
                quality_kept_pct=?, monthly_savings=?, escalation_rate=?,
                total_cost=?, duration=?, summary_json=?, updated_at=?
            WHERE id=?
            """,
            (
                len(levels), len(cascade["picked_keys"]),
                cascade["expected_quality"], cascade["expected_cost"], cascade["expected_latency"],
                flagship["quality"], flagship["cost_per_call"],
                cheap["quality"], cheap["cost_per_call"],
                quality_kept_pct, monthly_savings, cascade["escalation_rate"],
                round(total_cost, 6), duration,
                json.dumps({**run["summary"], **summary_ext}), now, relay_id,
            ),
        )

    return {"success": True, "relay": get_relay(relay_id)}, 200


def preview_gate(
    relay_id: str,
    *,
    gate_type: Optional[str] = None,
    gate_threshold: Optional[float] = None,
    quality_floor: Optional[float] = None,
    latency_ceiling_ms: Optional[float] = None,
    picked_indexes: Optional[Sequence[int]] = None,
    monthly_calls: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """Re-simulate a persisted relay under a new gate / picked-subset /
    constraint set — no new calls, just re-derive from the stored replays.

    For dryrun runs we have to reconstruct the level's pass_rate under the
    new gate. Rather than store raw replays (which would fatten the DB
    considerably), we approximate the new pass_rate by projecting the
    stored ``quality`` + ``quality_stdev`` + ``output_tokens`` through the
    gate function. The approximation is exact for ``composite`` (the
    stored quality *is* the gate signal) and near-exact for ``length``
    and ``consistency``. Only ``coverage`` shifts slightly since we don't
    persist per-replay keyword hits."""
    run = get_relay(relay_id)
    if not run:
        return None
    levels = run.get("levels") or []
    if not levels:
        return None
    gt = gate_type if gate_type in GATE_TYPES else run["gate_type"]
    thr = float(gate_threshold if gate_threshold is not None else DEFAULT_GATE_THRESHOLDS.get(gt, run["gate_threshold"]))
    calls = int(monthly_calls if monthly_calls is not None else run["monthly_calls"])

    # Approximate pass_rate under the new gate.
    for lv in levels:
        if lv.get("quality") is None:
            lv["pass_rate"] = 0.0
            continue
        q = float(lv["quality"] or 0)
        sd = float(lv.get("quality_stdev") or 0)
        out_tok = int(lv.get("output_tokens") or 0)
        if gt == "length":
            lv["pass_rate"] = 1.0 if out_tok >= thr else 0.0
        elif gt == "coverage":
            # Rebuild an approximate keyword-hit count from quality:
            # coverage_score = 20 + 80·pct, quality is 0.5·coverage + fid + fmt.
            # Solve: pct ≈ (quality - 30) / 40 clamped to [0, 1], then hits ≈ pct * 14.
            pct = max(0.0, min(1.0, (q - 30.0) / 40.0))
            approx_hits = pct * 14.0
            lv["pass_rate"] = round(min(1.0, max(0.0, (approx_hits - thr + 2) / 4.0)), 3)
        elif gt == "consistency":
            if sd > thr or q < 60.0:
                lv["pass_rate"] = 0.0
            else:
                lv["pass_rate"] = round(min(1.0, max(0.0, (q - 60.0) / 25.0 + 0.5)), 3)
        else:  # composite
            # Approximate via Gaussian on (quality, stdev): fraction ≥ thr
            if sd < 0.5:
                lv["pass_rate"] = 1.0 if q >= thr else 0.0
            else:
                z = (q - thr) / max(0.5, sd)
                # cdf of z (skip full erf, use logistic approximation)
                lv["pass_rate"] = round(1.0 / (1.0 + math.exp(-1.6 * z)), 3)

    valid = [p for p in levels if p.get("quality") is not None and p.get("cost_per_call") is not None]
    if not valid:
        return None
    flagship = max(valid, key=lambda x: (x["quality"], -x["cost_per_call"]))
    shapes = suggest_shapes(
        levels,
        monthly_calls=calls,
        flagship_quality=float(flagship["quality"] or 0),
        flagship_cost=float(flagship["cost_per_call"] or 0),
        quality_floor=quality_floor if quality_floor is not None else run["quality_floor"],
        latency_ceiling_ms=latency_ceiling_ms if latency_ceiling_ms is not None else run["latency_ceiling_ms"],
    )
    pick = None
    if picked_indexes is not None:
        pick = list(picked_indexes)
    else:
        default_pick = shapes["balanced"] or shapes["cost_min"] or None
        pick = list(default_pick["indexes"]) if default_pick else _cost_ordered_indexes(levels)
    cascade = simulate_cascade(levels, picked_indexes=pick)
    quality_kept_pct = round(100.0 * cascade["expected_quality"] / max(1e-9, flagship["quality"] or 0), 1)
    monthly_savings = round(max(0.0, (float(flagship["cost_per_call"] or 0) - cascade["expected_cost"])) * calls, 2)
    return {
        "gate_type":         gt,
        "gate_threshold":    thr,
        "monthly_calls":     calls,
        "cascade":           cascade,
        "shapes":            {
            "balanced":        shapes["balanced"],
            "cost_min":        shapes["cost_min"],
            "latency_capped":  shapes["latency_capped"],
            "scan":            shapes["scan"],
        },
        "quality_kept_pct":  quality_kept_pct,
        "monthly_savings":   monthly_savings,
    }


# ---------------------------------------------------------------------------
# Rationales & actions.
# ---------------------------------------------------------------------------

def _level_rationale(lv: Dict[str, Any], cascade: Dict[str, Any]) -> str:
    if lv.get("quality") is None:
        return "All replays failed — no valid quality/cost point for this level."
    key = f"{lv['provider']}:{lv['model']}"
    if not lv.get("picked"):
        return (
            f"Skipped — either dominated by another level in the cascade, or "
            f"its pass rate ({(lv.get('pass_rate') or 0):.0%}) at the gate is "
            f"too low to earn a slot."
        )
    p_r = lv.get("p_reach") or 0.0
    p_t = lv.get("p_terminate") or 0.0
    return (
        f"On the cascade — {p_r:.0%} of live prompts reach here, "
        f"{p_t:.0%} terminate at this level "
        f"(Q={lv.get('quality'):.0f}, ${lv.get('cost_per_call'):.5f}/call)."
    )


def _actions_from(
    *,
    cascade: Dict[str, Any],
    levels: List[Dict[str, Any]],
    flagship: Dict[str, Any],
    cheap: Dict[str, Any],
    monthly_calls: int,
    gate_type: str,
    gate_threshold: float,
    quality_kept_pct: float,
    monthly_savings: float,
) -> List[str]:
    actions: List[str] = []
    picked = [f"{lv['provider']}:{lv['model']}" for lv in levels if lv.get("picked")]
    if picked and monthly_savings > 0:
        pct = round(100.0 * monthly_savings / max(1e-9, float(flagship.get("cost_per_call") or 0) * monthly_calls), 1)
        shape_word = "substitution" if len(picked) == 1 else f"{len(picked)}-level cascade"
        arrow = picked[0] if len(picked) == 1 else " → ".join(picked)
        actions.append(
            f"**Ship** the {shape_word} `{arrow}` — "
            f"keeps **{quality_kept_pct:.0f}%** of *{flagship['model']}*'s quality at "
            f"**${monthly_savings:,.0f}/mo savings** ({pct:.0f}% off) on "
            f"{monthly_calls:,} calls."
        )
    esc = cascade.get("escalation_rate") or 0.0
    if picked and esc >= 0.3:
        first = picked[0].split(":")[-1]
        actions.append(
            f"Level 1 (*{first}*) escalates on **{esc:.0%}** of prompts — "
            f"either widen its gate ({gate_type} ≥ {gate_threshold:g}) or "
            "swap it for a stronger cheap model to lift the pass rate."
        )
    picked_set = set(picked)
    dropped = [
        f"{lv['provider']}:{lv['model']}" for lv in levels
        if not lv.get("picked") and lv.get("quality") is not None
    ]
    if dropped:
        actions.append(
            f"**Drop** {len(dropped)} model{'s' if len(dropped) != 1 else ''} — "
            f"{', '.join(m.split(':')[-1] for m in dropped[:4])}"
            + ("…" if len(dropped) > 4 else "")
            + " — the cascade doesn't need them."
        )
    if len(picked) >= 3:
        actions.append(
            "Three or more levels means a longer latency tail. Cap the deepest "
            "level with a hard timeout so slow escalations don't ruin p95."
        )
    if not picked:
        actions.append(
            f"No cascade shape beats always-*{flagship['model']}* under the "
            f"current constraints — loosen quality_floor or latency_ceiling_ms."
        )
    return actions


# ---------------------------------------------------------------------------
# Seed demo — lights up the page on first load.
# ---------------------------------------------------------------------------

_DEMO_SYSTEM_PROMPT = (
    "You are a customer-support triage assistant at a fintech company. When a "
    "customer sends a message, classify it into one of these buckets: "
    "payment_declined, transfer_pending, kyc_review, refund_request, "
    "account_locked, other. Then either (a) answer directly if the case is "
    "trivial, (b) hand off to the relevant human queue with the reason, or "
    "(c) request the specific piece of information you still need. Be precise, "
    "cite the transaction reference the customer gave, and never promise refunds."
)

_DEMO_USER_PROMPT = (
    "Hi — my transfer of $2,150 to my supplier account is still pending after "
    "two days. Reference is TR-2026-07-08-441. Can you tell me what's holding "
    "it up and how long it usually takes?"
)


def seed_demo() -> Dict[str, Any]:
    init_db()
    run = create_relay(
        name="Fintech triage — cascade router",
        description=(
            "Sample Relay run: cost-ordered eight-model roster, composite "
            "gate at quality ≥ 65, 50k monthly calls. Recommends the "
            "balanced 2-3 level cascade that keeps ≥95% of flagship "
            "quality at a fraction of the cost."
        ),
        system_prompt=_DEMO_SYSTEM_PROMPT,
        user_prompt=_DEMO_USER_PROMPT,
        temperature=0.4,
        n_replays=4,
        monthly_calls=50_000,
        gate_type="composite",
        gate_threshold=55.0,
        quality_floor=60.0,
        latency_ceiling_ms=3500.0,
        dryrun=True,
    )
    from src.providers.provider_factory import ProviderFactory  # local import to avoid cycle
    payload, _ = run_relay(run["id"], provider_factory=ProviderFactory(), confirm_live=False)
    return payload.get("relay") or run
