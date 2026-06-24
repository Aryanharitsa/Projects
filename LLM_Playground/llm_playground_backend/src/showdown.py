"""Showdown Arena — paired A/B testing for prompts with real statistics.

Every other surface in the playground already exists for a different question:

* **Arena** — fan one prompt out to many models.
* **Vote** — rank one prompt's outputs via ELO.
* **Suites** — batch one prompt across cases.
* **Rubrics** — judge one response against a versioned rubric.
* **Optimizer** — *evolve* a prompt to chase a higher rubric score.
* **Adversary** — measure how a prompt holds up under perturbation.

What none of them answer is the single question every prompt engineer hits the
moment they have a candidate revision: **"is this challenger actually better
than the champion currently in production, or am I about to ship noise?"**.
Showdown Arena is that surface. Given two prompts (Champion and Challenger),
a shared set of test cases, and a rubric, it runs the *same* cases through
both prompts, judges each response, and surfaces a **paired** statistical
comparison:

* **Mean Δ** — average per-case ``(challenger.composite − champion.composite)``.
* **Paired bootstrap 95 % CI** — resample the per-case delta vector ``B`` times
  (``B=5000`` by default), recompute the mean each draw, take the 2.5 % and
  97.5 % percentiles. Same input → same CI: the bootstrap is seeded off the
  showdown id so re-runs are reproducible.
* **Sign-test p-value** — two-sided exact binomial on the win/loss vector
  (ties stripped). Tells you "are the wins distinguishable from a coin?".
* **Win rate** — fraction of cases where challenger > champion.
* **Cohen's d** — paired effect size ``mean(Δ) / std(Δ)`` (sample std).
* **Per-dimension Δ** — when a rubric is attached, every rubric dimension also
  carries its own mean Δ + sign.

Decision rule (the headline the UI lives on):

* ``ship_challenger`` — ``mean_Δ ≥ +3.0`` AND ``ci_low > 0`` AND ``win_rate ≥ 0.55``.
* ``keep_champion``  — ``mean_Δ ≤ −3.0`` AND ``ci_high < 0`` AND ``win_rate ≤ 0.45``.
* ``tied``           — ``|mean_Δ| < 1.0`` AND CI straddles zero AND win rate in [.40, .60].
* ``no_decision``    — anything else (effect there but not significant, or significant
  but tiny — add more cases to disambiguate).

Like Optimizer and Adversary, ``dryrun=True`` runs the entire loop without any
API keys: a deterministic synthetic response generator + heuristic rubric
scoring give a realistic-feeling demo (and the bootstrap CI / sign-test /
effect size all behave as you'd expect on the seed data).

Public surface (kept narrow):
``create_showdown``, ``list_showdowns``, ``get_showdown``, ``delete_showdown``,
``run_showdown``, ``stats``, ``seed_demo``.
"""
from __future__ import annotations

import hashlib
import json
import math
import random
import re
import sqlite3
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from typing import Any, Dict, List, Optional, Tuple

from src import history, rubrics
from src.pricing import estimate_cost

_DB_LOCK = history._DB_LOCK  # noqa: SLF001 — share the cross-table lock


@contextmanager
def _conn():
    with history._conn() as con:  # noqa: SLF001
        yield con


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS showdowns (
    id                    TEXT PRIMARY KEY,
    name                  TEXT NOT NULL,
    description           TEXT,
    champion_prompt       TEXT NOT NULL,
    challenger_prompt     TEXT NOT NULL,
    champion_label        TEXT NOT NULL DEFAULT 'Champion',
    challenger_label      TEXT NOT NULL DEFAULT 'Challenger',
    rubric_id             TEXT,
    rubric_revision       INTEGER,
    judge_provider        TEXT,
    judge_model           TEXT,
    candidate_provider    TEXT,
    candidate_model       TEXT,
    test_cases_json       TEXT NOT NULL,
    status                TEXT NOT NULL,
    dryrun                INTEGER NOT NULL DEFAULT 0,
    n_bootstrap           INTEGER NOT NULL DEFAULT 5000,
    champion_composite    REAL,
    challenger_composite  REAL,
    mean_delta            REAL,
    std_delta             REAL,
    ci_low                REAL,
    ci_high               REAL,
    p_value_sign          REAL,
    win_rate              REAL,
    n_wins                INTEGER NOT NULL DEFAULT 0,
    n_losses              INTEGER NOT NULL DEFAULT 0,
    n_ties                INTEGER NOT NULL DEFAULT 0,
    effect_size           REAL,
    decision              TEXT,
    total_cost            REAL NOT NULL DEFAULT 0,
    duration              REAL NOT NULL DEFAULT 0,
    summary_json          TEXT,
    created_at            REAL NOT NULL,
    updated_at            REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS showdown_runs (
    id                    TEXT PRIMARY KEY,
    showdown_id           TEXT NOT NULL,
    case_idx              INTEGER NOT NULL,
    case_input            TEXT NOT NULL,
    case_expected         TEXT,
    champion_response     TEXT,
    challenger_response   TEXT,
    champion_composite    REAL,
    challenger_composite  REAL,
    delta                 REAL,
    outcome               TEXT,             -- challenger_win | champion_win | tie
    champion_dim_json     TEXT,
    challenger_dim_json   TEXT,
    cost_usd              REAL NOT NULL DEFAULT 0,
    latency               REAL NOT NULL DEFAULT 0,
    error                 TEXT,
    created_at            REAL NOT NULL,
    FOREIGN KEY (showdown_id) REFERENCES showdowns(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_sd_updated   ON showdowns(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_sd_status    ON showdowns(status);
CREATE INDEX IF NOT EXISTS idx_sd_decision  ON showdowns(decision);
CREATE INDEX IF NOT EXISTS idx_sdrun_sd     ON showdown_runs(showdown_id, case_idx);
"""


def init_db() -> None:
    with _DB_LOCK, _conn() as con:
        con.executescript(_SCHEMA)


def _now() -> float:
    return time.time()


# ---------------------------------------------------------------------------
# Defaults & limits
# ---------------------------------------------------------------------------

# Heuristic rubric used in dry-run mode when no rubric is attached. Same shape
# as Adversary's so the scoring math composes cleanly.
_DEFAULT_DRYRUN_DIMENSIONS: List[Dict[str, Any]] = [
    {"name": "Correctness",  "weight": 40, "max_score": 10},
    {"name": "Completeness", "weight": 25, "max_score": 10},
    {"name": "Clarity",      "weight": 20, "max_score": 10},
    {"name": "Format",       "weight": 15, "max_score": 10},
]

MAX_TEST_CASES = 25
MIN_BOOTSTRAP  = 200
MAX_BOOTSTRAP  = 20000
DEFAULT_BOOTSTRAP = 5000

# Decision thresholds (centralised so the UI + Markdown digest can mirror them).
DECISION_THRESHOLDS = {
    "ship_min_delta":   3.0,
    "ship_min_winrate": 0.55,
    "keep_max_delta":  -3.0,
    "keep_max_winrate": 0.45,
    "tie_max_abs_delta": 1.0,
    "tie_winrate_low":   0.40,
    "tie_winrate_high":  0.60,
}


# ---------------------------------------------------------------------------
# Dry-run scoring — deterministic synthetic response + heuristic rubric
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(r"[A-Za-z0-9']+")


def _tokens(s: str) -> List[str]:
    return [t.lower() for t in _TOKEN_RE.findall(s or "")]


def _overlap(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    ta, tb = set(_tokens(a)), set(_tokens(b))
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / max(1, len(ta | tb))


_FORMAT_CUES = ("- ", "* ", "1.", "2.", ":", "\n\n", "**", "```", "step ")


def _dryrun_compose(
    *,
    prompt: str,
    case_input: str,
    case_expected: str,
    response: str,
    dimensions: List[Dict[str, Any]],
    side_seed: str,
) -> Dict[str, Any]:
    """Heuristic 0-100 composite + per-dim verdicts. Mirrors adversary's shape.

    ``side_seed`` is a short discriminator (``"champ"`` / ``"chall"``) so the
    same prompt+input pair can score slightly differently per side (otherwise
    a tie at the heuristic-rubric level would always result, which is boring).
    """
    overlap_exp = _overlap(response, case_expected) if case_expected else 0.0
    overlap_in = _overlap(response, case_input) * 0.5
    length = len(response or "")
    length_score = 1.0 if 80 <= length <= 800 else (
        0.5 if 30 <= length <= 1400 else 0.2 if response else 0.0
    )
    resp_l = (response or "").lower()
    fmt_hits = sum(1 for cue in _FORMAT_CUES if cue in resp_l)
    format_score = min(1.0, 0.25 + 0.18 * fmt_hits)
    base = 0.55 * (overlap_exp or overlap_in) + 0.25 * length_score + 0.20 * format_score
    h = hashlib.md5(
        (side_seed + "|" + prompt + "|" + (case_input or "") + "|" + (response or "")).encode()
    ).digest()
    dim_verdicts: List[Dict[str, Any]] = []
    composite = 0.0
    weight_sum = sum(int(d.get("weight") or 0) for d in dimensions) or 100
    for i, d in enumerate(dimensions):
        jitter = (h[i % len(h)] / 255.0 - 0.5) * 0.18
        per_dim = max(0.0, min(1.0, base + jitter))
        score = int(round(per_dim * 10))
        weight = int(d.get("weight") or 0)
        composite += (score / 10.0) * (weight / weight_sum)
        dim_verdicts.append({
            "name": d["name"],
            "weight": weight,
            "score": score,
            "max_score": 10,
            "rationale": "Heuristic dry-run score (no judge LLM was called).",
            "contribution": round((score / 10.0) * weight, 2),
        })
    return {
        "composite": round(composite * 100.0, 2),
        "dim_verdicts": dim_verdicts,
        "summary": "Dry-run heuristic score — install API keys to compare with a real judge.",
        "parsed_ok": True,
    }


# Hand-crafted heuristics that the synthetic response generator uses to make
# the challenger feel like it was "tuned" — better structure, more constraints
# acknowledged, optional step-by-step framing.
def _prompt_signals(prompt: str) -> Dict[str, float]:
    low = (prompt or "").lower()
    return {
        "examples":     1.0 if "input:" in low or "example" in low else 0.0,
        "format":       1.0 if "json" in low or "format" in low or "two-sentence" in low else 0.0,
        "structure":    1.0 if "step by step" in low or "first," in low or "structured" in low else 0.0,
        "tone":         1.0 if "calm" in low or "concise" in low or "friendly" in low else 0.0,
        "constraints":  1.0 if "must" in low or "always" in low or "do not" in low else 0.0,
        "length":       min(1.0, len(prompt) / 800.0),
    }


def _dryrun_response(
    *,
    prompt: str,
    case_input: str,
    case_expected: str,
    side_seed: str,
) -> str:
    """Synthesize a plausible response. Better-engineered prompts produce
    more cues that boost the heuristic score, so the challenger consistently
    wins/loses based on prompt quality rather than randomness."""
    signals = _prompt_signals(prompt)
    parts: List[str] = []
    # Open with an acknowledgement that latches onto a few user-input tokens
    # — this primes the expected-overlap dimension.
    if case_input:
        snippet = case_input.strip().split("\n", 1)[0]
        if len(snippet) > 80:
            snippet = snippet[:80] + "…"
        parts.append(f"Re: \"{snippet}\" —")

    if signals["structure"]:
        parts.append("Step 1: identify the goal. Step 2: address the request directly. Step 3: provide the next step.")
    elif signals["format"]:
        parts.append("Concise answer first, then the next step.")
    else:
        parts.append("Here is the answer to your question.")

    # If the rubric expects something specific, weave a hint of it.
    if case_expected:
        expected_tokens = _tokens(case_expected)
        # Pick 3 distinctive expected tokens (no common stopwords) to echo.
        keep = [t for t in expected_tokens if t not in {
            "the", "and", "a", "an", "to", "of", "in", "is", "are", "for",
            "with", "on", "or", "by", "be", "as", "it", "this", "that",
            "two-sentence", "next", "step", "concise",
        }]
        for token in keep[:3]:
            parts.append(token.capitalize() + ".")

    if signals["constraints"]:
        parts.append("All constraints from the system prompt were applied.")
    if signals["tone"]:
        parts.append("Thanks for reaching out — happy to help further.")

    # Side-discriminator: the challenger phrasing is slightly tighter, which
    # the format-cues heuristic rewards.
    if side_seed == "chall":
        parts.append("- Action item: see above.")
    else:
        parts.append("Action item: see above.")

    return " ".join(parts)


# ---------------------------------------------------------------------------
# Statistical helpers — pure, no external deps
# ---------------------------------------------------------------------------

def _mean(xs: List[float]) -> Optional[float]:
    return (sum(xs) / len(xs)) if xs else None


def _std(xs: List[float]) -> Optional[float]:
    if not xs or len(xs) < 2:
        return 0.0 if xs else None
    m = sum(xs) / len(xs)
    var = sum((x - m) ** 2 for x in xs) / (len(xs) - 1)
    return math.sqrt(var)


def _paired_bootstrap_ci(
    deltas: List[float],
    *,
    n_bootstrap: int,
    seed: str,
    confidence: float = 0.95,
) -> Tuple[Optional[float], Optional[float]]:
    """Resample deltas with replacement ``n_bootstrap`` times and return
    the (lower, upper) percentile bounds of the bootstrap means."""
    if not deltas:
        return None, None
    rng = random.Random(int(hashlib.md5(seed.encode()).hexdigest()[:8], 16))
    n = len(deltas)
    means: List[float] = []
    # If we have only one case the CI is degenerate — return ±0 around the value.
    if n == 1:
        return deltas[0], deltas[0]
    for _ in range(n_bootstrap):
        s = 0.0
        for _ in range(n):
            s += deltas[rng.randrange(n)]
        means.append(s / n)
    means.sort()
    alpha = (1.0 - confidence) / 2.0
    lo_idx = max(0, min(n_bootstrap - 1, int(math.floor(alpha * n_bootstrap))))
    hi_idx = max(0, min(n_bootstrap - 1, int(math.ceil((1 - alpha) * n_bootstrap)) - 1))
    return round(means[lo_idx], 3), round(means[hi_idx], 3)


def _binom_cdf(k: int, n: int, p: float) -> float:
    """Plain-Python cumulative binomial — fine for ``n ≤ MAX_TEST_CASES``."""
    if n <= 0:
        return 1.0
    if k < 0:
        return 0.0
    if k >= n:
        return 1.0
    out = 0.0
    # log-space for numerical safety.
    log_p = math.log(p) if p > 0 else float("-inf")
    log_q = math.log(1.0 - p) if p < 1 else float("-inf")
    for i in range(0, k + 1):
        log_coef = (
            math.lgamma(n + 1) - math.lgamma(i + 1) - math.lgamma(n - i + 1)
        )
        log_prob = log_coef + i * log_p + (n - i) * log_q
        out += math.exp(log_prob)
    return min(1.0, out)


def _sign_test_pvalue(n_wins: int, n_losses: int) -> Optional[float]:
    """Two-sided exact binomial sign test. Ties stripped before calling."""
    n = n_wins + n_losses
    if n == 0:
        return None
    k = min(n_wins, n_losses)
    p = 2.0 * _binom_cdf(k, n, 0.5)
    return round(min(1.0, p), 4)


def _decide(
    *,
    mean_delta: Optional[float],
    ci_low: Optional[float],
    ci_high: Optional[float],
    win_rate: Optional[float],
) -> str:
    if mean_delta is None or ci_low is None or ci_high is None or win_rate is None:
        return "no_decision"
    t = DECISION_THRESHOLDS
    if (
        mean_delta >= t["ship_min_delta"]
        and ci_low > 0
        and win_rate >= t["ship_min_winrate"]
    ):
        return "ship_challenger"
    if (
        mean_delta <= t["keep_max_delta"]
        and ci_high < 0
        and win_rate <= t["keep_max_winrate"]
    ):
        return "keep_champion"
    if (
        abs(mean_delta) < t["tie_max_abs_delta"]
        and ci_low <= 0 <= ci_high
        and t["tie_winrate_low"] <= win_rate <= t["tie_winrate_high"]
    ):
        return "tied"
    return "no_decision"


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------

def _normalise_cases(cases: Any) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not isinstance(cases, list):
        return out
    for c in cases:
        if not isinstance(c, dict):
            continue
        inp = (c.get("input") or "").strip()
        if not inp:
            continue
        out.append({
            "input": inp[:2000],
            "expected": (c.get("expected") or "").strip()[:2000],
        })
    return out[:MAX_TEST_CASES]


def _clip_bootstrap(n: Any) -> int:
    try:
        v = int(n)
    except (TypeError, ValueError):
        v = DEFAULT_BOOTSTRAP
    return max(MIN_BOOTSTRAP, min(MAX_BOOTSTRAP, v))


# ---------------------------------------------------------------------------
# Row decoders
# ---------------------------------------------------------------------------

def _row_to_showdown(row: sqlite3.Row) -> Dict[str, Any]:
    try:
        cases = json.loads(row["test_cases_json"])
    except (TypeError, ValueError, json.JSONDecodeError):
        cases = []
    summary = None
    if row["summary_json"]:
        try:
            summary = json.loads(row["summary_json"])
        except (TypeError, ValueError, json.JSONDecodeError):
            summary = None
    return {
        "id": row["id"],
        "name": row["name"],
        "description": row["description"] or "",
        "champion_prompt": row["champion_prompt"],
        "challenger_prompt": row["challenger_prompt"],
        "champion_label": row["champion_label"],
        "challenger_label": row["challenger_label"],
        "rubric_id": row["rubric_id"] or "",
        "rubric_revision": row["rubric_revision"],
        "judge_provider": row["judge_provider"] or "",
        "judge_model": row["judge_model"] or "",
        "candidate_provider": row["candidate_provider"] or "",
        "candidate_model": row["candidate_model"] or "",
        "test_cases": cases,
        "status": row["status"],
        "dryrun": bool(row["dryrun"]),
        "n_bootstrap": int(row["n_bootstrap"] or DEFAULT_BOOTSTRAP),
        "champion_composite": row["champion_composite"],
        "challenger_composite": row["challenger_composite"],
        "mean_delta": row["mean_delta"],
        "std_delta": row["std_delta"],
        "ci_low": row["ci_low"],
        "ci_high": row["ci_high"],
        "p_value_sign": row["p_value_sign"],
        "win_rate": row["win_rate"],
        "n_wins": int(row["n_wins"] or 0),
        "n_losses": int(row["n_losses"] or 0),
        "n_ties": int(row["n_ties"] or 0),
        "effect_size": row["effect_size"],
        "decision": row["decision"] or "",
        "total_cost": float(row["total_cost"] or 0),
        "duration": float(row["duration"] or 0),
        "summary": summary,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _row_to_run(row: sqlite3.Row) -> Dict[str, Any]:
    try:
        champ_dim = json.loads(row["champion_dim_json"]) if row["champion_dim_json"] else []
    except (TypeError, ValueError, json.JSONDecodeError):
        champ_dim = []
    try:
        chall_dim = json.loads(row["challenger_dim_json"]) if row["challenger_dim_json"] else []
    except (TypeError, ValueError, json.JSONDecodeError):
        chall_dim = []
    return {
        "id": row["id"],
        "showdown_id": row["showdown_id"],
        "case_idx": int(row["case_idx"] or 0),
        "case_input": row["case_input"] or "",
        "case_expected": row["case_expected"] or "",
        "champion_response": row["champion_response"] or "",
        "challenger_response": row["challenger_response"] or "",
        "champion_composite": row["champion_composite"],
        "challenger_composite": row["challenger_composite"],
        "delta": row["delta"],
        "outcome": row["outcome"] or "",
        "champion_dim": champ_dim,
        "challenger_dim": chall_dim,
        "cost_usd": float(row["cost_usd"] or 0),
        "latency": float(row["latency"] or 0),
        "error": row["error"] or "",
        "created_at": row["created_at"],
    }


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

def create_showdown(
    *,
    name: str,
    champion_prompt: str,
    challenger_prompt: str,
    test_cases: List[Dict[str, Any]],
    description: str = "",
    champion_label: str = "Champion",
    challenger_label: str = "Challenger",
    rubric_id: str = "",
    rubric_revision: Optional[int] = None,
    judge_provider: str = "",
    judge_model: str = "",
    candidate_provider: str = "",
    candidate_model: str = "",
    dryrun: bool = False,
    n_bootstrap: int = DEFAULT_BOOTSTRAP,
) -> Dict[str, Any]:
    init_db()
    name = (name or "").strip()
    if not name:
        raise ValueError("name is required")
    champ = (champion_prompt or "").strip()
    chall = (challenger_prompt or "").strip()
    if not champ:
        raise ValueError("champion_prompt is required")
    if not chall:
        raise ValueError("challenger_prompt is required")
    if champ == chall:
        raise ValueError("champion and challenger prompts are identical — nothing to compare")
    cases = _normalise_cases(test_cases)
    if not cases:
        raise ValueError("at least one non-empty test case is required")
    boot = _clip_bootstrap(n_bootstrap)
    sid = uuid.uuid4().hex
    now = _now()
    with _DB_LOCK, _conn() as con:
        con.execute(
            """INSERT INTO showdowns
                 (id, name, description,
                  champion_prompt, challenger_prompt,
                  champion_label, challenger_label,
                  rubric_id, rubric_revision,
                  judge_provider, judge_model,
                  candidate_provider, candidate_model,
                  test_cases_json, status, dryrun, n_bootstrap,
                  champion_composite, challenger_composite,
                  mean_delta, std_delta, ci_low, ci_high,
                  p_value_sign, win_rate, effect_size, decision,
                  total_cost, duration, summary_json,
                  created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                       'draft', ?, ?,
                       NULL, NULL, NULL, NULL, NULL, NULL,
                       NULL, NULL, NULL, NULL,
                       0, 0, NULL, ?, ?)""",
            (
                sid, name, (description or "").strip(),
                champ, chall,
                (champion_label or "Champion").strip()[:40] or "Champion",
                (challenger_label or "Challenger").strip()[:40] or "Challenger",
                rubric_id or None, rubric_revision,
                judge_provider or None, judge_model or None,
                candidate_provider or None, candidate_model or None,
                json.dumps(cases),
                1 if dryrun else 0, boot,
                now, now,
            ),
        )
    return get_showdown(sid) or {}


def list_showdowns(
    *,
    q: Optional[str] = None,
    status: Optional[str] = None,
    decision: Optional[str] = None,
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
    if decision:
        clauses.append("decision = ?")
        params.append(decision)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    with _DB_LOCK, _conn() as con:
        total_row = con.execute(
            f"SELECT COUNT(*) AS c FROM showdowns {where}", params,
        ).fetchone()
        total = int(total_row["c"]) if total_row else 0
        rows = con.execute(
            f"""SELECT * FROM showdowns {where}
                ORDER BY updated_at DESC
                LIMIT ? OFFSET ?""",
            params + [int(limit), int(offset)],
        ).fetchall()
    return [_row_to_showdown(r) for r in rows], total


def get_showdown(showdown_id: str) -> Optional[Dict[str, Any]]:
    init_db()
    with _DB_LOCK, _conn() as con:
        row = con.execute(
            "SELECT * FROM showdowns WHERE id = ?", (showdown_id,),
        ).fetchone()
        if not row:
            return None
        sd = _row_to_showdown(row)
        runs = con.execute(
            "SELECT * FROM showdown_runs WHERE showdown_id = ? ORDER BY case_idx ASC",
            (showdown_id,),
        ).fetchall()
    sd["runs"] = [_row_to_run(r) for r in runs]
    return sd


def delete_showdown(showdown_id: str) -> bool:
    init_db()
    with _DB_LOCK, _conn() as con:
        cur = con.execute("DELETE FROM showdowns WHERE id = ?", (showdown_id,))
        con.execute("DELETE FROM showdown_runs WHERE showdown_id = ?", (showdown_id,))
        return cur.rowcount > 0


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------

def _live_call_one(
    *,
    side: str,
    prompt: str,
    case: Dict[str, Any],
    candidate_provider: str,
    candidate_model: str,
    judge_provider: str,
    judge_model: str,
    rubric_id: str,
    revision_num: Optional[int],
    provider_factory,
) -> Dict[str, Any]:
    """One live (prompt × case) — candidate call + judge call. Reused for
    both sides."""
    case_input = (case.get("input") or "").strip()
    case_expected = (case.get("expected") or "").strip()
    cand = provider_factory.create_provider(candidate_provider)
    if not cand:
        return {
            "side": side,
            "response": "",
            "composite": None,
            "dim_verdicts": [],
            "cost_usd": 0.0,
            "latency": 0.0,
            "error": f"candidate provider '{candidate_provider}' not available",
        }
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": case_input or "(no input)"},
    ]
    t0 = time.time()
    try:
        resp = cand.make_request(candidate_model, messages)
    except Exception as exc:  # noqa: BLE001
        return {
            "side": side,
            "response": "",
            "composite": None,
            "dim_verdicts": [],
            "cost_usd": 0.0,
            "latency": round(time.time() - t0, 3),
            "error": f"candidate call failed: {exc}",
        }
    err = resp.get("error")
    if resp.get("status") != "success" or (isinstance(err, dict) and err):
        msg = err.get("message") if isinstance(err, dict) else (err or "candidate upstream error")
        return {
            "side": side,
            "response": "",
            "composite": None,
            "dim_verdicts": [],
            "cost_usd": 0.0,
            "latency": round(time.time() - t0, 3),
            "error": msg,
        }
    content = (resp.get("content") or "").strip()
    in_tok = int(resp.get("input_tokens") or 0)
    out_tok = int(resp.get("output_tokens") or 0)
    cand_cost = float(estimate_cost(candidate_model, in_tok, out_tok) or 0.0)
    cand_latency = round(time.time() - t0, 3)
    try:
        jpayload, _ = rubrics.judge_with_rubric(
            rubric_id,
            user_prompt=case_input or "(no input)",
            response=content,
            judge_provider=judge_provider,
            judge_model=judge_model,
            system_prompt=prompt,
            candidate_provider=candidate_provider,
            candidate_model=candidate_model,
            note=f"showdown ({side})",
            provider_factory=provider_factory,
            persist=False,
            revision_num=revision_num,
        )
    except Exception as exc:  # noqa: BLE001
        return {
            "side": side,
            "response": content,
            "composite": None,
            "dim_verdicts": [],
            "cost_usd": cand_cost,
            "latency": cand_latency,
            "error": f"judge failed: {exc}",
        }
    if not jpayload.get("success"):
        return {
            "side": side,
            "response": content,
            "composite": None,
            "dim_verdicts": [],
            "cost_usd": cand_cost,
            "latency": cand_latency,
            "error": jpayload.get("error") or "judge returned no verdict",
        }
    judge_cost = float((jpayload.get("judge") or {}).get("cost_usd") or 0.0)
    judge_lat = float((jpayload.get("judge") or {}).get("latency") or 0.0)
    return {
        "side": side,
        "response": content,
        "composite": jpayload.get("composite"),
        "dim_verdicts": jpayload.get("dim_verdicts", []),
        "cost_usd": round(cand_cost + judge_cost, 6),
        "latency": round(cand_latency + judge_lat, 3),
        "case_expected": case_expected,
    }


def _score_case_dryrun(
    *,
    side: str,
    prompt: str,
    case: Dict[str, Any],
    dimensions: List[Dict[str, Any]],
) -> Dict[str, Any]:
    case_input = (case.get("input") or "").strip()
    case_expected = (case.get("expected") or "").strip()
    side_seed = "chall" if side == "challenger" else "champ"
    response = _dryrun_response(
        prompt=prompt,
        case_input=case_input,
        case_expected=case_expected,
        side_seed=side_seed,
    )
    scored = _dryrun_compose(
        prompt=prompt,
        case_input=case_input,
        case_expected=case_expected,
        response=response,
        dimensions=dimensions,
        side_seed=side_seed,
    )
    return {
        "side": side,
        "response": response,
        "composite": scored["composite"],
        "dim_verdicts": scored["dim_verdicts"],
        "cost_usd": 0.0,
        "latency": 0.0,
        "case_expected": case_expected,
    }


def run_showdown(
    showdown_id: str,
    *,
    provider_factory,
    confirm_live: bool = False,
    parallel: int = 4,
) -> Tuple[Dict[str, Any], int]:
    """Score every case under both prompts, compute the paired stats, and
    persist the summary. Re-runnable in place — wipes any previous
    ``showdown_runs`` before scoring fresh."""
    init_db()
    sd = get_showdown(showdown_id)
    if not sd:
        return {"success": False, "error": "showdown not found"}, 404
    if sd["status"] == "running":
        return {"success": False, "error": "showdown already running"}, 400
    if not sd["dryrun"] and not confirm_live:
        return {
            "success": False,
            "error": "live showdown: pass confirm_live=true (this will spend API credits)",
        }, 400

    rubric_dims: List[Dict[str, Any]] = []
    if sd["rubric_id"]:
        rb = rubrics.get_rubric(sd["rubric_id"], include_revisions=False, recent_judgements=0)
        if rb:
            rubric_dims = rb.get("dimensions") or []
    if sd["dryrun"] and not rubric_dims:
        rubric_dims = list(_DEFAULT_DRYRUN_DIMENSIONS)

    cases = sd["test_cases"]
    n_cases = len(cases)

    # Wipe previous runs.
    with _DB_LOCK, _conn() as con:
        con.execute("DELETE FROM showdown_runs WHERE showdown_id = ?", (showdown_id,))
        con.execute(
            "UPDATE showdowns SET status='running', updated_at=? WHERE id=?",
            (_now(), showdown_id),
        )

    started = time.time()
    total_cost = 0.0
    per_case_runs: List[Dict[str, Any]] = []
    errors: List[str] = []

    def _do_side(side: str, prompt: str, case: Dict[str, Any]) -> Dict[str, Any]:
        if sd["dryrun"]:
            return _score_case_dryrun(
                side=side, prompt=prompt, case=case, dimensions=rubric_dims,
            )
        return _live_call_one(
            side=side, prompt=prompt, case=case,
            candidate_provider=sd["candidate_provider"],
            candidate_model=sd["candidate_model"],
            judge_provider=sd["judge_provider"],
            judge_model=sd["judge_model"],
            rubric_id=sd["rubric_id"],
            revision_num=sd["rubric_revision"],
            provider_factory=provider_factory,
        )

    # 2N tasks — both sides × every case, fully parallel where possible.
    tasks: List[Tuple[int, str]] = []
    for idx in range(n_cases):
        tasks.append((idx, "champion"))
        tasks.append((idx, "challenger"))

    results_buf: Dict[Tuple[int, str], Dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=max(1, min(parallel * 2, 8))) as pool:
        futures = {
            pool.submit(
                _do_side,
                side,
                sd["champion_prompt"] if side == "champion" else sd["challenger_prompt"],
                cases[idx],
            ): (idx, side)
            for idx, side in tasks
        }
        for fut in as_completed(futures):
            idx, side = futures[fut]
            try:
                results_buf[(idx, side)] = fut.result()
            except Exception as exc:  # noqa: BLE001
                results_buf[(idx, side)] = {
                    "side": side, "response": "", "composite": None,
                    "dim_verdicts": [], "cost_usd": 0.0, "latency": 0.0,
                    "error": str(exc),
                }

    # Stitch per-case rows + persist.
    deltas: List[float] = []
    champ_composites: List[float] = []
    chall_composites: List[float] = []
    n_wins = n_losses = n_ties = 0
    dim_deltas_per_case: List[Dict[str, float]] = []

    for idx in range(n_cases):
        case = cases[idx]
        champ = results_buf.get((idx, "champion")) or {}
        chall = results_buf.get((idx, "challenger")) or {}
        if champ.get("error"):
            errors.append(f"case {idx} champion: {champ['error']}")
        if chall.get("error"):
            errors.append(f"case {idx} challenger: {chall['error']}")
        c_cost = float(champ.get("cost_usd") or 0) + float(chall.get("cost_usd") or 0)
        c_lat = float(champ.get("latency") or 0) + float(chall.get("latency") or 0)
        total_cost += c_cost

        c_comp = champ.get("composite")
        h_comp = chall.get("composite")
        delta_val: Optional[float] = None
        outcome = ""
        if c_comp is not None and h_comp is not None:
            delta_val = round(float(h_comp) - float(c_comp), 3)
            deltas.append(delta_val)
            champ_composites.append(float(c_comp))
            chall_composites.append(float(h_comp))
            if delta_val > 0.5:
                outcome = "challenger_win"; n_wins += 1
            elif delta_val < -0.5:
                outcome = "champion_win"; n_losses += 1
            else:
                outcome = "tie"; n_ties += 1
            # Per-dim deltas: align by dim name.
            cd = {d.get("name"): float(d.get("score") or 0) for d in (champ.get("dim_verdicts") or [])}
            hd = {d.get("name"): float(d.get("score") or 0) for d in (chall.get("dim_verdicts") or [])}
            dim_deltas_per_case.append({
                k: round(hd[k] - cd[k], 3) for k in hd if k in cd
            })
        else:
            outcome = "skipped"

        _persist_run(
            showdown_id=showdown_id,
            case_idx=idx,
            case_input=(case.get("input") or ""),
            case_expected=(case.get("expected") or ""),
            champion_response=(champ.get("response") or ""),
            challenger_response=(chall.get("response") or ""),
            champion_composite=c_comp,
            challenger_composite=h_comp,
            delta=delta_val,
            outcome=outcome,
            champion_dim=champ.get("dim_verdicts") or [],
            challenger_dim=chall.get("dim_verdicts") or [],
            cost_usd=c_cost,
            latency=c_lat,
            error=" · ".join(filter(None, [champ.get("error"), chall.get("error")])) or None,
        )
        per_case_runs.append({
            "case_idx": idx,
            "delta": delta_val,
            "champion_composite": c_comp,
            "challenger_composite": h_comp,
            "outcome": outcome,
        })

    # Statistical roll-up.
    mean_delta = _mean(deltas)
    std_delta = _std(deltas)
    ci_low, ci_high = _paired_bootstrap_ci(
        deltas, n_bootstrap=sd["n_bootstrap"], seed=showdown_id,
    )
    win_rate = (n_wins / max(1, len(deltas))) if deltas else None
    p_sign = _sign_test_pvalue(n_wins, n_losses)
    effect_size: Optional[float] = None
    if std_delta and std_delta > 1e-6 and mean_delta is not None:
        effect_size = round(mean_delta / std_delta, 3)
    elif mean_delta == 0:
        effect_size = 0.0

    champ_avg = _mean(champ_composites)
    chall_avg = _mean(chall_composites)

    decision = _decide(
        mean_delta=mean_delta, ci_low=ci_low, ci_high=ci_high, win_rate=win_rate,
    )

    # Per-dimension roll-up (rubric attached only).
    dim_summary: List[Dict[str, Any]] = []
    for d in rubric_dims:
        name = d["name"]
        vals = [c[name] for c in dim_deltas_per_case if name in c]
        if not vals:
            dim_summary.append({
                "name": name, "weight": int(d.get("weight") or 0),
                "mean_delta": None, "worst_delta": None, "best_delta": None, "n": 0,
            })
            continue
        dim_summary.append({
            "name": name,
            "weight": int(d.get("weight") or 0),
            "mean_delta": round(_mean(vals) or 0.0, 3),
            "worst_delta": round(min(vals), 3),
            "best_delta":  round(max(vals), 3),
            "n": len(vals),
        })

    duration = round(time.time() - started, 3)
    headline = _build_headline(
        decision=decision,
        mean_delta=mean_delta,
        win_rate=win_rate,
        n=len(deltas),
        champion_label=sd["champion_label"],
        challenger_label=sd["challenger_label"],
        p_value=p_sign,
    )

    summary = {
        "n_cases":              n_cases,
        "n_compared":           len(deltas),
        "n_wins":               n_wins,
        "n_losses":             n_losses,
        "n_ties":               n_ties,
        "champion_composite":   round(champ_avg, 2) if champ_avg is not None else None,
        "challenger_composite": round(chall_avg, 2) if chall_avg is not None else None,
        "mean_delta":           round(mean_delta, 3) if mean_delta is not None else None,
        "std_delta":            round(std_delta, 3) if std_delta is not None else None,
        "ci_low":               ci_low,
        "ci_high":              ci_high,
        "p_value_sign":         p_sign,
        "win_rate":             round(win_rate, 3) if win_rate is not None else None,
        "effect_size":          effect_size,
        "decision":             decision,
        "headline":             headline,
        "dim_summary":          dim_summary,
        "per_case":             per_case_runs,
        "duration":             duration,
        "total_cost":           round(total_cost, 6),
        "errors":               errors[:25],
        "thresholds":           DECISION_THRESHOLDS,
        "n_bootstrap":          sd["n_bootstrap"],
    }

    with _DB_LOCK, _conn() as con:
        con.execute(
            """UPDATE showdowns
               SET status='complete',
                   champion_composite=?, challenger_composite=?,
                   mean_delta=?, std_delta=?,
                   ci_low=?, ci_high=?,
                   p_value_sign=?, win_rate=?,
                   n_wins=?, n_losses=?, n_ties=?,
                   effect_size=?, decision=?,
                   total_cost=?, duration=?, summary_json=?,
                   updated_at=?
               WHERE id=?""",
            (
                round(champ_avg, 2) if champ_avg is not None else None,
                round(chall_avg, 2) if chall_avg is not None else None,
                round(mean_delta, 3) if mean_delta is not None else None,
                round(std_delta, 3) if std_delta is not None else None,
                ci_low, ci_high, p_sign,
                round(win_rate, 3) if win_rate is not None else None,
                n_wins, n_losses, n_ties,
                effect_size, decision,
                round(total_cost, 6), duration,
                json.dumps(summary), _now(),
                showdown_id,
            ),
        )

    return {"success": True, "showdown": get_showdown(showdown_id), "summary": summary}, 200


def _persist_run(
    *,
    showdown_id: str,
    case_idx: int,
    case_input: str,
    case_expected: str,
    champion_response: str,
    challenger_response: str,
    champion_composite: Optional[float],
    challenger_composite: Optional[float],
    delta: Optional[float],
    outcome: str,
    champion_dim: List[Dict[str, Any]],
    challenger_dim: List[Dict[str, Any]],
    cost_usd: float,
    latency: float,
    error: Optional[str],
) -> str:
    rid = uuid.uuid4().hex
    now = _now()
    with _DB_LOCK, _conn() as con:
        con.execute(
            """INSERT INTO showdown_runs
                 (id, showdown_id, case_idx, case_input, case_expected,
                  champion_response, challenger_response,
                  champion_composite, challenger_composite, delta, outcome,
                  champion_dim_json, challenger_dim_json,
                  cost_usd, latency, error, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                rid, showdown_id, case_idx, case_input, case_expected,
                champion_response, challenger_response,
                champion_composite, challenger_composite, delta, outcome,
                json.dumps(champion_dim), json.dumps(challenger_dim),
                round(float(cost_usd or 0), 6),
                round(float(latency or 0), 3),
                error, now,
            ),
        )
    return rid


# ---------------------------------------------------------------------------
# Headline / decisions
# ---------------------------------------------------------------------------

def _build_headline(
    *,
    decision: str,
    mean_delta: Optional[float],
    win_rate: Optional[float],
    n: int,
    champion_label: str,
    challenger_label: str,
    p_value: Optional[float],
) -> str:
    if not n:
        return "No comparable cases — both candidates failed to produce a scored response."
    md = (f"{mean_delta:+.2f}" if mean_delta is not None else "?")
    wr = (f"{round((win_rate or 0) * 100)}%" if win_rate is not None else "?")
    p = f"p≈{p_value:.3f}" if p_value is not None else "p=—"
    if decision == "ship_challenger":
        head = f"Ship **{challenger_label}**. Mean Δ {md} across {n} cases ({wr} wins) is significant ({p})."
    elif decision == "keep_champion":
        head = f"Keep **{champion_label}**. Mean Δ {md} across {n} cases — challenger regressed ({wr} wins, {p})."
    elif decision == "tied":
        head = f"Tie — no meaningful difference. Mean Δ {md}, {wr} wins, {p}."
    else:
        head = f"No decision — effect ({md}) not separable from noise across {n} cases ({wr} wins, {p}). Add more cases or sharpen the rubric."
    return head


# ---------------------------------------------------------------------------
# Stats + seed
# ---------------------------------------------------------------------------

def stats() -> Dict[str, Any]:
    init_db()
    with _DB_LOCK, _conn() as con:
        n_showdowns = int(con.execute("SELECT COUNT(*) AS c FROM showdowns").fetchone()["c"])
        n_runs = int(con.execute("SELECT COUNT(*) AS c FROM showdown_runs").fetchone()["c"])
        n_ship = int(con.execute(
            "SELECT COUNT(*) AS c FROM showdowns WHERE decision = 'ship_challenger'"
        ).fetchone()["c"])
        n_keep = int(con.execute(
            "SELECT COUNT(*) AS c FROM showdowns WHERE decision = 'keep_champion'"
        ).fetchone()["c"])
        n_tied = int(con.execute(
            "SELECT COUNT(*) AS c FROM showdowns WHERE decision = 'tied'"
        ).fetchone()["c"])
        avg_row = con.execute(
            "SELECT AVG(mean_delta) AS a FROM showdowns WHERE mean_delta IS NOT NULL"
        ).fetchone()
        best_row = con.execute(
            "SELECT MAX(mean_delta) AS m FROM showdowns WHERE mean_delta IS NOT NULL"
        ).fetchone()
        rows = con.execute(
            """SELECT id, name, decision, mean_delta, win_rate, p_value_sign,
                      updated_at
               FROM showdowns
               WHERE status = 'complete'
               ORDER BY updated_at DESC
               LIMIT 5"""
        ).fetchall()
    recent = [{
        "id": r["id"], "name": r["name"], "decision": r["decision"] or "",
        "mean_delta": r["mean_delta"], "win_rate": r["win_rate"],
        "p_value_sign": r["p_value_sign"], "updated_at": r["updated_at"],
    } for r in rows]
    return {
        "n_showdowns": n_showdowns,
        "n_runs": n_runs,
        "n_ship_challenger": n_ship,
        "n_keep_champion": n_keep,
        "n_tied": n_tied,
        "avg_mean_delta": round(float(avg_row["a"]), 3) if avg_row and avg_row["a"] is not None else None,
        "best_mean_delta": round(float(best_row["m"]), 3) if best_row and best_row["m"] is not None else None,
        "recent": recent,
        "thresholds": DECISION_THRESHOLDS,
    }


_SEED_NAME = "Customer support — v1 vs v2 (concise + structured)"


def seed_demo() -> Dict[str, Any]:
    """Idempotent — looks for an existing showdown with the seed name first."""
    init_db()
    existing_id: Optional[str] = None
    with _DB_LOCK, _conn() as con:
        row = con.execute(
            "SELECT id FROM showdowns WHERE name = ? LIMIT 1", (_SEED_NAME,),
        ).fetchone()
        if row:
            existing_id = row["id"]
    if existing_id:
        return get_showdown(existing_id) or {}

    champion_prompt = (
        "You are a customer support specialist for a small SaaS company. "
        "Reply to the user's message and tell them what to do."
    )
    challenger_prompt = (
        "You are a calm, concise customer support specialist for a small SaaS "
        "company. Read the user's message, identify the underlying issue, and "
        "reply step by step. First, acknowledge the problem in one sentence. "
        "Second, answer the question directly. Third, propose the next concrete "
        "step the user should take. Always be friendly and constraints-aware: "
        "do not promise refunds you cannot guarantee, and always offer to "
        "escalate when the issue is not resolvable in one reply.\n\n"
        "Examples:\n"
        "Input: My card was charged twice.\n"
        "Output: I'm sorry about the duplicate charge — I can see two transactions on June 3rd. "
        "Step 1: I'll refund the extra one today. Step 2: it'll land in 3–5 business days. "
        "Step 3: reply here if you don't see it by Tuesday.\n\n"
        "Now respond in the same format to the new input."
    )
    test_cases = [
        {
            "input": "The mobile app keeps crashing every time I open the dashboard on my iPhone 14.",
            "expected": "Step-by-step apology + ask for build version + step to reinstall and reply with logs.",
        },
        {
            "input": "Can I get a refund for last month? I forgot to cancel before the renewal date.",
            "expected": "Polite acknowledgement, friendly refund-policy answer, next step to confirm reply.",
        },
        {
            "input": "Is your EU enterprise plan compliant with GDPR Article 28 sub-processors?",
            "expected": "Concise yes-with-caveats answer + step to send the DPA + sub-processor list link.",
        },
        {
            "input": "The dashboard shows totally wrong revenue numbers for July. They're off by $4k.",
            "expected": "Acknowledge urgency, ask for the timezone + screenshot, step to escalate to billing-eng.",
        },
        {
            "input": "Hey, what's the cheapest plan that supports SSO with Okta?",
            "expected": "Direct plan name + price + caveat about Okta SCIM, step to share the comparison link.",
        },
        {
            "input": "I'm getting a 502 every time I hit /api/v2/sync. This started about 30 minutes ago.",
            "expected": "Acknowledge outage urgency, step to share request ID + region, escalate to on-call.",
        },
        {
            "input": "The CSV export is missing the 'team' column we just added in custom fields.",
            "expected": "Direct acknowledgement + step to enable export-custom-fields toggle in Settings.",
        },
        {
            "input": "Can you delete all of my account data? I'm leaving the platform.",
            "expected": "Friendly confirmation, GDPR-erasure acknowledgement, step to confirm email + deletion ETA.",
        },
        {
            "input": "Is there a way to invite teammates without giving them admin access?",
            "expected": "Direct yes, step to use Member role + link to the role-comparison doc.",
        },
        {
            "input": "Our credit card just expired and renewal failed. How do we keep the team active?",
            "expected": "Reassurance + step to update card in Billing within 7-day grace window.",
        },
    ]
    sid = create_showdown(
        name=_SEED_NAME,
        description="Day-58 demo: terse v1 prompt vs structured + few-shot v2 prompt across 10 support tickets.",
        champion_prompt=champion_prompt,
        challenger_prompt=challenger_prompt,
        champion_label="v1 (terse)",
        challenger_label="v2 (structured)",
        test_cases=test_cases,
        dryrun=True,
    )["id"]
    return get_showdown(sid) or {}
