"""Persistent, queryable history of Arena + Judge runs.

A run is the canonical record of *one prompt fanned out across N models*: the
prompt, system prompt, every candidate's response with its metrics, the
arena-derived winners (fastest / cheapest / verbose), and — if the user later
clicked **Judge** — the LLM-as-judge verdicts, leaderboard, and winner.

The store is a single SQLite table (`runs`) where:

* Heavyweight payload (`results`, `verdicts`, `leaderboard`, …) lives in a
  JSON `payload` column. We never query *into* it, so JSON is fine.
* Everything we filter, sort, or aggregate on is **also** mirrored as a
  scalar column with an index — `created_at`, `prompt_hash`, `n_candidates`,
  `n_success`, `total_cost_usd`, `wall_latency`, `judged`, `judge_winner`,
  `judge_top_score`, `tag`, `starred`. That keeps `GET /history` snappy under
  thousands of rows without paying SQLite-JSON1 indexing tax.

The API is intentionally tiny (`save_run`, `update_judge`, `list_runs`,
`get_run`, `set_meta`, `delete_run`, `stats`, `diff`) so swapping the backing
store later (e.g. Postgres) is a one-day job.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from typing import Any, Dict, Iterable, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

_DB_PATH = os.environ.get(
    "LLM_HISTORY_DB",
    os.path.join(os.path.dirname(__file__), "database", "history.db"),
)
_DB_LOCK = threading.Lock()


def _ensure_dir() -> None:
    os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)


@contextmanager
def _conn():
    """Per-call SQLite connection — the store is low-traffic, this is fine."""
    _ensure_dir()
    con = sqlite3.connect(_DB_PATH, timeout=10.0, isolation_level=None)
    con.row_factory = sqlite3.Row
    try:
        yield con
    finally:
        con.close()


_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id              TEXT PRIMARY KEY,
    created_at      REAL NOT NULL,
    prompt          TEXT NOT NULL,
    prompt_hash     TEXT NOT NULL,
    system_prompt   TEXT,
    models          TEXT NOT NULL,        -- comma-joined "Provider:model" fingerprint
    n_candidates    INTEGER NOT NULL,
    n_success       INTEGER NOT NULL,
    total_cost_usd  REAL NOT NULL,
    wall_latency    REAL NOT NULL,
    fastest_model   TEXT,
    cheapest_model  TEXT,
    judged          INTEGER NOT NULL DEFAULT 0,
    judge_provider  TEXT,
    judge_model     TEXT,
    judge_winner    TEXT,                 -- provider:model of judge's #1
    judge_top_score REAL,
    tag             TEXT,
    note            TEXT,
    starred         INTEGER NOT NULL DEFAULT 0,
    payload         TEXT NOT NULL          -- full JSON blob
);

CREATE INDEX IF NOT EXISTS idx_runs_created      ON runs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_runs_prompt_hash  ON runs(prompt_hash);
CREATE INDEX IF NOT EXISTS idx_runs_judged       ON runs(judged);
CREATE INDEX IF NOT EXISTS idx_runs_starred      ON runs(starred);
CREATE INDEX IF NOT EXISTS idx_runs_tag          ON runs(tag);
"""


def init_db() -> None:
    with _DB_LOCK, _conn() as con:
        con.executescript(_SCHEMA)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _hash_prompt(prompt: str) -> str:
    return hashlib.sha256((prompt or "").strip().encode("utf-8")).hexdigest()[:16]


def _fingerprint(results: List[Dict[str, Any]]) -> str:
    return ",".join(f"{r.get('provider','?')}:{r.get('model','?')}" for r in results)


def _row_to_summary(row: sqlite3.Row) -> Dict[str, Any]:
    return {
        "id":              row["id"],
        "created_at":      row["created_at"],
        "prompt":          row["prompt"],
        "prompt_preview":  (row["prompt"] or "")[:160],
        "system_prompt":   row["system_prompt"] or "",
        "models":          [m for m in (row["models"] or "").split(",") if m],
        "n_candidates":    row["n_candidates"],
        "n_success":       row["n_success"],
        "total_cost_usd":  row["total_cost_usd"],
        "wall_latency":    row["wall_latency"],
        "fastest_model":   row["fastest_model"],
        "cheapest_model":  row["cheapest_model"],
        "judged":          bool(row["judged"]),
        "judge_provider":  row["judge_provider"],
        "judge_model":     row["judge_model"],
        "judge_winner":    row["judge_winner"],
        "judge_top_score": row["judge_top_score"],
        "tag":             row["tag"],
        "note":            row["note"],
        "starred":         bool(row["starred"]),
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def save_run(arena: Dict[str, Any], prompt: str, system_prompt: str = "") -> str:
    """Persist a fresh Arena run, return its `run_id`.

    `arena` is whatever ``/api/compare`` returns — we keep it intact in
    `payload` and pull summary columns out of it.
    """
    run_id = arena.get("request_id") or str(uuid.uuid4())
    results: List[Dict[str, Any]] = arena.get("results") or []
    winners: Dict[str, Any] = arena.get("winners") or {}

    n_success = sum(1 for r in results if r.get("status") == "success")
    total_cost = round(sum(float(r.get("cost_usd") or 0.0) for r in results), 6)

    payload = {
        "id":            run_id,
        "prompt":        prompt,
        "system_prompt": system_prompt,
        "results":       results,
        "winners":       winners,
        "wall_latency":  arena.get("wall_latency"),
        "judge":         None,
    }

    with _DB_LOCK, _conn() as con:
        con.execute(
            """INSERT OR REPLACE INTO runs
               (id, created_at, prompt, prompt_hash, system_prompt,
                models, n_candidates, n_success, total_cost_usd,
                wall_latency, fastest_model, cheapest_model,
                judged, judge_provider, judge_model, judge_winner,
                judge_top_score, tag, note, starred, payload)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, NULL, NULL, NULL, NULL,
                       NULL, NULL, 0, ?)""",
            (
                run_id,
                time.time(),
                prompt or "",
                _hash_prompt(prompt or ""),
                system_prompt or "",
                _fingerprint(results),
                len(results),
                n_success,
                total_cost,
                float(arena.get("wall_latency") or 0.0),
                winners.get("fastest"),
                winners.get("cheapest"),
                json.dumps(payload, ensure_ascii=False),
            ),
        )
    return run_id


def update_judge(run_id: str, judge_payload: Dict[str, Any]) -> bool:
    """Attach a judge result to an existing run. Returns False if the run
    has been deleted in the meantime — the judge call still succeeded, we
    just don't have a row to attach to."""
    if not run_id:
        return False
    leaderboard: List[Dict[str, Any]] = judge_payload.get("leaderboard") or []
    judge_meta: Dict[str, Any] = judge_payload.get("judge") or {}

    top = leaderboard[0] if leaderboard else None
    judge_winner = f"{top.get('provider','?')}:{top.get('model','?')}" if top else None
    judge_top_score = float(top.get("composite") or 0.0) if top else None

    with _DB_LOCK, _conn() as con:
        row = con.execute("SELECT payload FROM runs WHERE id = ?", (run_id,)).fetchone()
        if not row:
            return False
        try:
            payload = json.loads(row["payload"])
        except (TypeError, ValueError):
            payload = {}
        payload["judge"] = {
            "rubric":       judge_payload.get("rubric"),
            "verdicts":     judge_payload.get("verdicts"),
            "leaderboard":  leaderboard,
            "winner":       judge_payload.get("winner"),
            "judge":        judge_meta,
        }
        con.execute(
            """UPDATE runs
               SET judged = 1,
                   judge_provider = ?,
                   judge_model = ?,
                   judge_winner = ?,
                   judge_top_score = ?,
                   payload = ?
               WHERE id = ?""",
            (
                judge_meta.get("provider"),
                judge_meta.get("model"),
                judge_winner,
                judge_top_score,
                json.dumps(payload, ensure_ascii=False),
                run_id,
            ),
        )
    return True


def list_runs(
    *,
    q: Optional[str] = None,
    model: Optional[str] = None,
    provider: Optional[str] = None,
    judged_only: bool = False,
    starred_only: bool = False,
    tag: Optional[str] = None,
    since: Optional[float] = None,
    before: Optional[float] = None,
    limit: int = 50,
    offset: int = 0,
) -> Tuple[List[Dict[str, Any]], int]:
    """Return `(rows, total)`. Filters compose with AND semantics."""
    where: List[str] = []
    args: List[Any] = []
    if q:
        where.append("(prompt LIKE ? OR system_prompt LIKE ? OR models LIKE ?)")
        like = f"%{q}%"
        args += [like, like, like]
    if model:
        where.append("models LIKE ?")
        args.append(f"%{model}%")
    if provider:
        where.append("models LIKE ?")
        args.append(f"%{provider}:%")
    if judged_only:
        where.append("judged = 1")
    if starred_only:
        where.append("starred = 1")
    if tag:
        where.append("tag = ?")
        args.append(tag)
    if since is not None:
        where.append("created_at >= ?")
        args.append(float(since))
    if before is not None:
        where.append("created_at <= ?")
        args.append(float(before))

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    limit = max(1, min(int(limit), 500))
    offset = max(0, int(offset))

    with _DB_LOCK, _conn() as con:
        total = con.execute(
            f"SELECT COUNT(*) AS c FROM runs {where_sql}", args
        ).fetchone()["c"]
        rows = con.execute(
            f"""SELECT * FROM runs {where_sql}
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?""",
            args + [limit, offset],
        ).fetchall()

    return [_row_to_summary(r) for r in rows], int(total)


def get_run(run_id: str) -> Optional[Dict[str, Any]]:
    """Full payload + summary fields. Returns None if not found."""
    with _DB_LOCK, _conn() as con:
        row = con.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    if not row:
        return None
    summary = _row_to_summary(row)
    try:
        summary["payload"] = json.loads(row["payload"])
    except (TypeError, ValueError):
        summary["payload"] = None
    return summary


def set_meta(
    run_id: str,
    *,
    tag: Optional[str] = None,
    note: Optional[str] = None,
    starred: Optional[bool] = None,
) -> bool:
    sets: List[str] = []
    args: List[Any] = []
    if tag is not None:
        sets.append("tag = ?")
        args.append(tag.strip() or None)
    if note is not None:
        sets.append("note = ?")
        args.append(note)
    if starred is not None:
        sets.append("starred = ?")
        args.append(1 if starred else 0)
    if not sets:
        return False
    args.append(run_id)
    with _DB_LOCK, _conn() as con:
        cur = con.execute(
            f"UPDATE runs SET {', '.join(sets)} WHERE id = ?", args
        )
        return cur.rowcount > 0


def delete_run(run_id: str) -> bool:
    with _DB_LOCK, _conn() as con:
        cur = con.execute("DELETE FROM runs WHERE id = ?", (run_id,))
        return cur.rowcount > 0


def stats() -> Dict[str, Any]:
    """Top-level dashboard metrics across the whole history."""
    with _DB_LOCK, _conn() as con:
        agg = con.execute(
            """SELECT COUNT(*)              AS total_runs,
                      COALESCE(SUM(n_candidates), 0)   AS total_candidates,
                      COALESCE(SUM(n_success), 0)      AS total_success,
                      COALESCE(SUM(total_cost_usd), 0) AS total_cost,
                      COALESCE(AVG(wall_latency), 0)   AS avg_wall,
                      COALESCE(SUM(judged), 0)         AS judged_runs,
                      COALESCE(AVG(judge_top_score), 0) AS avg_top_score,
                      MIN(created_at) AS first_at,
                      MAX(created_at) AS last_at
               FROM runs"""
        ).fetchone()
        # Per-model win rate across judged runs (the model that came #1).
        wins = con.execute(
            """SELECT judge_winner AS m, COUNT(*) AS wins
               FROM runs
               WHERE judged = 1 AND judge_winner IS NOT NULL
               GROUP BY judge_winner
               ORDER BY wins DESC
               LIMIT 8"""
        ).fetchall()
        # Per-model appearance count (how often a model entered the arena).
        # We approximate this by counting CSV occurrences in the models column;
        # exact enough for the "top contestants" ribbon.
        appearances_rows = con.execute(
            "SELECT models FROM runs"
        ).fetchall()

    appearances: Dict[str, int] = {}
    for r in appearances_rows:
        for m in (r["models"] or "").split(","):
            if not m:
                continue
            appearances[m] = appearances.get(m, 0) + 1
    top_appearances = sorted(appearances.items(), key=lambda kv: kv[1], reverse=True)[:8]

    return {
        "total_runs":       int(agg["total_runs"]),
        "total_candidates": int(agg["total_candidates"]),
        "total_success":    int(agg["total_success"]),
        "total_cost":       float(round(agg["total_cost"] or 0.0, 6)),
        "avg_wall":         float(round(agg["avg_wall"] or 0.0, 3)),
        "judged_runs":      int(agg["judged_runs"]),
        "avg_top_score":    float(round(agg["avg_top_score"] or 0.0, 2)),
        "first_at":         agg["first_at"],
        "last_at":          agg["last_at"],
        "winners":          [{"model": w["m"], "wins": int(w["wins"])} for w in wins],
        "appearances":      [{"model": m, "count": c} for m, c in top_appearances],
    }


def diff(run_id_a: str, run_id_b: str) -> Optional[Dict[str, Any]]:
    """Side-by-side diff of two runs. Returns None if either is missing.

    The shape is:
        {
          a: <summary>, b: <summary>,
          shared_models: [...], a_only: [...], b_only: [...],
          per_model: [{model, a:{score,latency,cost,response_chars},
                              b:{...}, deltas:{...}}, ...],
          deltas: { wall_latency, total_cost, n_success,
                    judge_top_score?:..., judge_winner?:[a,b] }
        }
    """
    a = get_run(run_id_a)
    b = get_run(run_id_b)
    if not a or not b:
        return None

    def _idx(payload: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        out: Dict[str, Dict[str, Any]] = {}
        for r in (payload or {}).get("results", []) or []:
            key = f"{r.get('provider','?')}:{r.get('model','?')}"
            out[key] = r
        return out

    def _judge_idx(payload: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        j = (payload or {}).get("judge") or {}
        verdicts = j.get("verdicts") or []
        results = (payload or {}).get("results", []) or []
        out: Dict[str, Dict[str, Any]] = {}
        for v in verdicts:
            cand_i = v.get("candidate")
            if cand_i is None or cand_i >= len(results):
                continue
            r = results[cand_i]
            key = f"{r.get('provider','?')}:{r.get('model','?')}"
            out[key] = v
        return out

    a_results = _idx(a["payload"])
    b_results = _idx(b["payload"])
    a_verdicts = _judge_idx(a["payload"])
    b_verdicts = _judge_idx(b["payload"])

    a_keys = set(a_results)
    b_keys = set(b_results)
    shared = sorted(a_keys & b_keys)
    a_only = sorted(a_keys - b_keys)
    b_only = sorted(b_keys - a_keys)

    def _bundle(model_key: str, side: Dict[str, Dict[str, Any]],
                vside: Dict[str, Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        r = side.get(model_key)
        if not r:
            return None
        v = vside.get(model_key) or {}
        return {
            "provider":      r.get("provider"),
            "model":         r.get("model"),
            "status":        r.get("status"),
            "latency":       r.get("latency"),
            "cost_usd":      r.get("cost_usd"),
            "total_tokens":  r.get("total_tokens"),
            "response_chars": len(r.get("response") or ""),
            "composite":     v.get("composite"),
            "rationale":     v.get("rationale"),
        }

    per_model: List[Dict[str, Any]] = []
    for k in shared:
        ab = _bundle(k, a_results, a_verdicts)
        bb = _bundle(k, b_results, b_verdicts)
        if not ab or not bb:
            continue
        deltas = {
            "latency":       _safe_delta(ab.get("latency"), bb.get("latency")),
            "cost_usd":      _safe_delta(ab.get("cost_usd"), bb.get("cost_usd")),
            "response_chars": _safe_delta(ab.get("response_chars"), bb.get("response_chars")),
            "composite":     _safe_delta(ab.get("composite"), bb.get("composite")),
        }
        per_model.append({"model": k, "a": ab, "b": bb, "deltas": deltas})

    deltas_top = {
        "wall_latency":   _safe_delta(a.get("wall_latency"),   b.get("wall_latency")),
        "total_cost":     _safe_delta(a.get("total_cost_usd"), b.get("total_cost_usd")),
        "n_success":      _safe_delta(a.get("n_success"),      b.get("n_success")),
        "judge_top_score": _safe_delta(a.get("judge_top_score"), b.get("judge_top_score")),
        "judge_winner":   [a.get("judge_winner"), b.get("judge_winner")],
    }

    return {
        "a": {k: a[k] for k in a if k != "payload"},
        "b": {k: b[k] for k in b if k != "payload"},
        "shared_models": shared,
        "a_only": a_only,
        "b_only": b_only,
        "per_model": per_model,
        "deltas": deltas_top,
    }


def _safe_delta(a: Any, b: Any) -> Optional[float]:
    """`b - a` if both are numeric; None otherwise."""
    try:
        if a is None or b is None:
            return None
        return float(b) - float(a)
    except (TypeError, ValueError):
        return None


# Initialise on import — main.py imports this module at boot.
init_db()
