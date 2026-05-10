"""Personal Chatbot Arena — blind A/B voting + ELO leaderboard.

Day 17 shipped a queryable run history. Round-2 (Day 8) shipped LLM-as-judge.
This module closes the loop: humans get to be the judge too. Every Arena run
on file becomes a source of pairs to vote on, votes feed an ELO model, and the
leaderboard is computed deterministically from the full vote log so it survives
schema changes and lets us replay with a different K-factor.

Storage piggy-backs on the existing ``history.db`` SQLite file (the user already
gitignores it; the votes table just slides in alongside ``runs``):

    votes(id, created_at, run_id, prompt_hash, model_a, model_b,
          winner, voter, judge_winner, latency_a, latency_b,
          cost_a, cost_b)

* ``winner`` is one of ``a`` / ``b`` / ``tie`` / ``both_bad``. ``both_bad`` is
  recorded but contributes 0 / 0 to ELO (no signal either way) so the
  rating doesn't drift on a no-information vote.
* ``judge_winner`` is the model the LLM-judge picked when the run was scored
  (or NULL). We use it later to compute judge↔human agreement *without* having
  to re-open the run payload.

Public API:

* ``record_vote(run_id, model_a, model_b, winner, voter=None,
   judge_winner=None, …)`` → vote_id
* ``leaderboard(k=24, prior=1500, since=None, min_games=0)``
* ``pair_matrix(top_n=8)``
* ``recent_votes(limit=20)``
* ``agreement(min_votes=1)`` — judge-vs-human agreement %, plus per-model rows
* ``stats()`` — top-level counts for the dashboard banner
* ``delete_vote(vote_id)`` — undo a misclick
* ``pick_pair_from_run(run_id, exclude_models=None)`` — anonymise a fresh pair
* ``pick_pair(run_id=None, voter=None, prefer_undervoted=True)`` —
  full sampler: walks recent runs, biases towards under-played pairs.

The ELO replay is the single source of truth. Every leaderboard call walks
``votes ORDER BY created_at`` and applies one update per vote. With sub-1000
votes that's microseconds; if it ever hurts we can checkpoint, but until then
the simplicity is worth more than the speed-up.
"""
from __future__ import annotations

import json
import os
import random
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from typing import Any, Dict, Iterable, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Storage — share the history.db file so a single backup captures everything.
# ---------------------------------------------------------------------------

_DB_PATH = os.environ.get(
    "LLM_HISTORY_DB",
    os.path.join(os.path.dirname(__file__), "database", "history.db"),
)
_DB_LOCK = threading.Lock()

# ELO knobs — exposed via env so a power-user can tune the K-factor without
# editing the file. K=24 matches FIDE blitz; over-aggressive for very small
# vote pools but the rating CI banner makes that obvious.
DEFAULT_K = float(os.environ.get("LLM_ELO_K", "24"))
DEFAULT_PRIOR = float(os.environ.get("LLM_ELO_PRIOR", "1500"))


def _ensure_dir() -> None:
    os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)


@contextmanager
def _conn():
    _ensure_dir()
    con = sqlite3.connect(_DB_PATH, timeout=10.0, isolation_level=None)
    con.row_factory = sqlite3.Row
    try:
        yield con
    finally:
        con.close()


_SCHEMA = """
CREATE TABLE IF NOT EXISTS votes (
    id            TEXT PRIMARY KEY,
    created_at    REAL NOT NULL,
    run_id        TEXT NOT NULL,
    prompt_hash   TEXT,
    prompt_preview TEXT,
    model_a       TEXT NOT NULL,    -- "Provider:model"
    model_b       TEXT NOT NULL,
    winner        TEXT NOT NULL,    -- 'a' | 'b' | 'tie' | 'both_bad'
    voter         TEXT,
    judge_winner  TEXT,
    latency_a     REAL,
    latency_b     REAL,
    cost_a        REAL,
    cost_b        REAL
);

CREATE INDEX IF NOT EXISTS idx_votes_created ON votes(created_at);
CREATE INDEX IF NOT EXISTS idx_votes_run     ON votes(run_id);
CREATE INDEX IF NOT EXISTS idx_votes_a       ON votes(model_a);
CREATE INDEX IF NOT EXISTS idx_votes_b       ON votes(model_b);
"""


def init_db() -> None:
    with _DB_LOCK, _conn() as con:
        con.executescript(_SCHEMA)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_WINNERS = {"a", "b", "tie", "both_bad"}


def _model_key(provider: str, model: str) -> str:
    return f"{provider or '?'}:{model or '?'}"


def _split_key(key: str) -> Tuple[str, str]:
    if not key:
        return "?", "?"
    if ":" in key:
        p, m = key.split(":", 1)
        return p, m
    return "?", key


def _normalise_winner(w: Any) -> Optional[str]:
    if not isinstance(w, str):
        return None
    w = w.strip().lower()
    if w in VALID_WINNERS:
        return w
    # Tolerate friendlier strings the UI might send.
    aliases = {"left": "a", "right": "b", "draw": "tie", "neither": "both_bad"}
    return aliases.get(w)


# ---------------------------------------------------------------------------
# Pair sampling — random by default, slightly biased towards pairs that
# haven't been voted on much (so a power-user voter doesn't get the same
# match-up over and over).
# ---------------------------------------------------------------------------


def _list_runs_with_candidates(min_success: int = 2, limit: int = 200) -> List[sqlite3.Row]:
    """Return run rows with at least 2 successful candidates, newest first.

    Reads from the same ``runs`` table ``history.py`` writes to. We only need
    enough metadata to identify the run; the caller pulls full payloads via
    history.get_run().
    """
    with _DB_LOCK, _conn() as con:
        rows = con.execute(
            """SELECT id, prompt, prompt_hash, models, n_success, payload
               FROM runs
               WHERE n_success >= ?
               ORDER BY created_at DESC
               LIMIT ?""",
            (min_success, limit),
        ).fetchall()
    return rows


def _candidates_from_payload(payload_json: str) -> List[Dict[str, Any]]:
    try:
        payload = json.loads(payload_json or "{}")
    except (TypeError, ValueError):
        return []
    out = []
    for i, r in enumerate(payload.get("results") or []):
        if r.get("status") != "success":
            continue
        body = r.get("response") or ""
        if not body:
            continue
        out.append({
            "candidate":  i,
            "provider":   r.get("provider", "?"),
            "model":      r.get("model", "?"),
            "response":   body,
            "latency":    r.get("latency"),
            "cost_usd":   r.get("cost_usd"),
            "total_tokens": r.get("total_tokens"),
        })
    return out


def _judge_winner_for_payload(payload_json: str) -> Optional[str]:
    try:
        payload = json.loads(payload_json or "{}")
    except (TypeError, ValueError):
        return None
    j = (payload or {}).get("judge") or {}
    lb = j.get("leaderboard") or []
    if not lb:
        return None
    top = lb[0] or {}
    return _model_key(top.get("provider", "?"), top.get("model", "?"))


def _pair_play_count(model_a: str, model_b: str) -> int:
    a, b = sorted([model_a, model_b])
    with _DB_LOCK, _conn() as con:
        n = con.execute(
            """SELECT COUNT(*) AS c FROM votes
               WHERE (model_a = ? AND model_b = ?) OR (model_a = ? AND model_b = ?)""",
            (a, b, b, a),
        ).fetchone()["c"]
    return int(n)


def pick_pair_from_run(
    run_id: str,
    *,
    exclude_models: Optional[Iterable[str]] = None,
) -> Optional[Dict[str, Any]]:
    """Return ``{run_id, prompt, system_prompt, prompt_hash, a, b,
    judge_winner}`` where ``a`` and ``b`` are the *anonymised* sides — the
    response body is exposed but ``provider``/``model`` are returned as
    ``"hidden"`` and only revealed once the vote is cast.
    """
    excl = set(exclude_models or [])
    with _DB_LOCK, _conn() as con:
        row = con.execute(
            "SELECT id, prompt, prompt_hash, payload FROM runs WHERE id = ?", (run_id,),
        ).fetchone()
    if not row:
        return None
    cands = [c for c in _candidates_from_payload(row["payload"]) if _model_key(c["provider"], c["model"]) not in excl]
    if len(cands) < 2:
        return None
    a, b = random.sample(cands, 2)
    # Randomise which one shows on the left so a voter can't infer "left = first
    # candidate index" from runs they ran themselves.
    if random.random() < 0.5:
        a, b = b, a
    payload = {}
    try:
        payload = json.loads(row["payload"] or "{}")
    except (TypeError, ValueError):
        pass
    return {
        "run_id":        row["id"],
        "prompt":        row["prompt"],
        "prompt_hash":   row["prompt_hash"],
        "system_prompt": payload.get("system_prompt") or "",
        "a": _anonymise_side(a),
        "b": _anonymise_side(b),
        # Server-side truth — never leaked to the client until vote is cast.
        "_truth": {
            "a": _model_key(a["provider"], a["model"]),
            "b": _model_key(b["provider"], b["model"]),
        },
        "judge_winner":  _judge_winner_for_payload(row["payload"]),
    }


def _anonymise_side(c: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "candidate":   c.get("candidate"),
        "provider":    "hidden",
        "model":       "hidden",
        "response":    c.get("response") or "",
        "response_chars": len(c.get("response") or ""),
        "latency":     c.get("latency"),
        "cost_usd":    c.get("cost_usd"),
        "total_tokens": c.get("total_tokens"),
    }


def pick_pair(
    *,
    run_id: Optional[str] = None,
    voter: Optional[str] = None,
    prefer_undervoted: bool = True,
    exclude_pairs: Optional[Iterable[Tuple[str, str]]] = None,
    max_runs_scanned: int = 60,
) -> Optional[Dict[str, Any]]:
    """Sample a pair to vote on.

    * If ``run_id`` is given, samples within that run (fast path used by the
      "Vote on this run" deeplink in the History panel).
    * Otherwise, walks the most recent ``max_runs_scanned`` runs (newest first)
      and yields the first run whose candidates contain a pair we can serve.
    * When ``prefer_undervoted`` is set and we have a choice of pairs, we bias
      towards pairs with the fewest existing votes — keeps the rating signal
      diversified instead of piling 30 votes on one match-up.
    """
    if run_id:
        return pick_pair_from_run(run_id)

    excluded: set = set()
    for p in exclude_pairs or []:
        if not p:
            continue
        a, b = sorted([p[0], p[1]])
        excluded.add((a, b))

    runs = _list_runs_with_candidates(min_success=2, limit=max_runs_scanned)
    random.shuffle(runs)
    best: Optional[Tuple[int, Dict[str, Any]]] = None

    for row in runs:
        cands = _candidates_from_payload(row["payload"])
        if len(cands) < 2:
            continue
        # Build all possible pairs, score by play count (lower is better).
        keys = [_model_key(c["provider"], c["model"]) for c in cands]
        pair_scores: List[Tuple[int, Tuple[int, int]]] = []
        for i in range(len(cands)):
            for j in range(i + 1, len(cands)):
                a_k, b_k = sorted([keys[i], keys[j]])
                if (a_k, b_k) in excluded:
                    continue
                if a_k == b_k:
                    continue
                count = _pair_play_count(a_k, b_k) if prefer_undervoted else 0
                pair_scores.append((count, (i, j)))
        if not pair_scores:
            continue
        pair_scores.sort(key=lambda kv: kv[0])
        # Among the lowest play-count tier, randomise so we don't hand back the
        # same first pair every time after a refresh.
        floor = pair_scores[0][0]
        floor_pairs = [p for n, p in pair_scores if n == floor]
        i, j = random.choice(floor_pairs)
        a, b = cands[i], cands[j]
        if random.random() < 0.5:
            a, b = b, a
        candidate_pair = pick_pair_from_run(row["id"])
        if candidate_pair:
            # Re-pull the canonical structure (prompt + system_prompt + truth)
            # but overwrite a/b/_truth with our deterministic pick.
            candidate_pair["a"] = _anonymise_side(a)
            candidate_pair["b"] = _anonymise_side(b)
            candidate_pair["_truth"] = {
                "a": _model_key(a["provider"], a["model"]),
                "b": _model_key(b["provider"], b["model"]),
            }
            score = floor
            if best is None or score < best[0]:
                best = (score, candidate_pair)
            if score == 0:
                # Found an unplayed pair — shortcut.
                return candidate_pair

    return best[1] if best else None


# ---------------------------------------------------------------------------
# Vote recording / deletion
# ---------------------------------------------------------------------------


def record_vote(
    *,
    run_id: str,
    model_a: str,
    model_b: str,
    winner: str,
    voter: Optional[str] = None,
    judge_winner: Optional[str] = None,
    prompt_hash: Optional[str] = None,
    prompt_preview: Optional[str] = None,
    latency_a: Optional[float] = None,
    latency_b: Optional[float] = None,
    cost_a: Optional[float] = None,
    cost_b: Optional[float] = None,
) -> Optional[str]:
    """Persist a vote, return its id. Returns None if the winner field is
    invalid or the two models are equal (which would be meaningless)."""
    w = _normalise_winner(winner)
    if not w:
        return None
    if not model_a or not model_b or model_a == model_b:
        return None
    vote_id = str(uuid.uuid4())
    with _DB_LOCK, _conn() as con:
        con.execute(
            """INSERT INTO votes (id, created_at, run_id, prompt_hash, prompt_preview,
                                  model_a, model_b, winner, voter, judge_winner,
                                  latency_a, latency_b, cost_a, cost_b)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                vote_id,
                time.time(),
                run_id or "",
                prompt_hash or None,
                (prompt_preview or "")[:200] or None,
                model_a,
                model_b,
                w,
                (voter or "").strip() or None,
                judge_winner or None,
                _f(latency_a), _f(latency_b), _f(cost_a), _f(cost_b),
            ),
        )
    return vote_id


def _f(v: Any) -> Optional[float]:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def delete_vote(vote_id: str) -> bool:
    if not vote_id:
        return False
    with _DB_LOCK, _conn() as con:
        cur = con.execute("DELETE FROM votes WHERE id = ?", (vote_id,))
        return cur.rowcount > 0


# ---------------------------------------------------------------------------
# ELO replay — single source of truth.
# ---------------------------------------------------------------------------


def _expected(rating_a: float, rating_b: float) -> float:
    """Standard ELO expected score for A given the two ratings."""
    return 1.0 / (1.0 + 10.0 ** ((rating_b - rating_a) / 400.0))


def _all_votes(since: Optional[float] = None) -> List[sqlite3.Row]:
    sql = "SELECT * FROM votes"
    args: List[Any] = []
    if since is not None:
        sql += " WHERE created_at >= ?"
        args.append(float(since))
    sql += " ORDER BY created_at ASC"
    with _DB_LOCK, _conn() as con:
        return con.execute(sql, args).fetchall()


def leaderboard(
    *,
    k: float = DEFAULT_K,
    prior: float = DEFAULT_PRIOR,
    since: Optional[float] = None,
    min_games: int = 0,
) -> Dict[str, Any]:
    """Replay the entire vote log to derive ELO ratings.

    Returns a dict with ``ratings`` (the leaderboard) and ``meta`` (k, prior,
    n_votes, n_models, last_vote_at).

    Each row carries:
      provider, model, key, rating, games, wins, losses, ties, both_bad,
      win_rate, avg_opp_rating, last_played, recent_form (last 8 results,
      newest first, encoded as 'W'/'L'/'T'/'B').
    """
    votes = _all_votes(since=since)
    rating: Dict[str, float] = {}
    games: Dict[str, int] = {}
    wins: Dict[str, int] = {}
    losses: Dict[str, int] = {}
    ties: Dict[str, int] = {}
    both_bad: Dict[str, int] = {}
    last_played: Dict[str, float] = {}
    opp_rating_sum: Dict[str, float] = {}
    form: Dict[str, List[str]] = {}

    def _bump(model: str) -> None:
        if model not in rating:
            rating[model] = float(prior)
            games[model] = 0
            wins[model] = 0
            losses[model] = 0
            ties[model] = 0
            both_bad[model] = 0
            opp_rating_sum[model] = 0.0
            form[model] = []

    for v in votes:
        a = v["model_a"]
        b = v["model_b"]
        w = v["winner"]
        ts = float(v["created_at"] or 0.0)
        _bump(a); _bump(b)

        if w == "both_bad":
            both_bad[a] += 1
            both_bad[b] += 1
            last_played[a] = ts; last_played[b] = ts
            form[a].insert(0, "B"); form[b].insert(0, "B")
            form[a] = form[a][:8]; form[b] = form[b][:8]
            # No rating change — no information.
            continue

        ra, rb = rating[a], rating[b]
        ea = _expected(ra, rb)
        eb = 1.0 - ea
        if w == "a":
            sa, sb = 1.0, 0.0
            wins[a] += 1; losses[b] += 1
            form[a].insert(0, "W"); form[b].insert(0, "L")
        elif w == "b":
            sa, sb = 0.0, 1.0
            wins[b] += 1; losses[a] += 1
            form[a].insert(0, "L"); form[b].insert(0, "W")
        else:  # tie
            sa, sb = 0.5, 0.5
            ties[a] += 1; ties[b] += 1
            form[a].insert(0, "T"); form[b].insert(0, "T")

        rating[a] = ra + k * (sa - ea)
        rating[b] = rb + k * (sb - eb)
        games[a] += 1; games[b] += 1
        opp_rating_sum[a] += rb
        opp_rating_sum[b] += ra
        last_played[a] = ts; last_played[b] = ts
        form[a] = form[a][:8]; form[b] = form[b][:8]

    rows = []
    for key, r in rating.items():
        n = games[key]
        if n < int(min_games):
            continue
        provider, model = _split_key(key)
        scoring = wins[key] + 0.5 * ties[key]
        rows.append({
            "key":          key,
            "provider":     provider,
            "model":        model,
            "rating":       round(r, 1),
            "games":        n,
            "wins":         wins[key],
            "losses":       losses[key],
            "ties":         ties[key],
            "both_bad":     both_bad[key],
            "win_rate":     round((scoring / n) * 100.0, 1) if n else 0.0,
            "avg_opp_rating": round(opp_rating_sum[key] / n, 1) if n else None,
            "last_played":  last_played.get(key),
            "recent_form":  form[key],
        })
    rows.sort(key=lambda row: (-row["rating"], -row["games"]))
    for i, row in enumerate(rows):
        row["rank"] = i + 1

    meta = {
        "k":            k,
        "prior":        prior,
        "n_votes":      len(votes),
        "n_models":     len(rating),
        "last_vote_at": max((float(v["created_at"]) for v in votes), default=None),
    }
    return {"ratings": rows, "meta": meta}


# ---------------------------------------------------------------------------
# Head-to-head matrix
# ---------------------------------------------------------------------------


def pair_matrix(top_n: int = 8) -> Dict[str, Any]:
    """Return a head-to-head wins matrix for the top-N most-rated models.

    Output shape:
        {
          models: [key, key, ...],         # row/column order, top-N by ELO
          providers: { key: provider },    # for cell colouring
          cells: [
            { a: key_row, b: key_col, wins_a: n, wins_b: n, ties: n,
              both_bad: n, total: n, win_rate_a: pct }
          ]
        }

    Cells are returned for ordered pairs (i, j) where i < j; the frontend
    mirrors them across the diagonal. Diagonal cells are omitted.
    """
    lb = leaderboard()
    keys = [r["key"] for r in lb["ratings"][:max(1, int(top_n))]]
    if len(keys) < 2:
        return {"models": keys, "providers": {}, "cells": []}
    placeholders = ",".join("?" * len(keys))
    with _DB_LOCK, _conn() as con:
        rows = con.execute(
            f"""SELECT model_a, model_b, winner, COUNT(*) AS n
                FROM votes
                WHERE model_a IN ({placeholders}) AND model_b IN ({placeholders})
                GROUP BY model_a, model_b, winner""",
            (*keys, *keys),
        ).fetchall()

    pair: Dict[Tuple[str, str], Dict[str, int]] = {}
    for r in rows:
        a, b = r["model_a"], r["model_b"]
        canon = tuple(sorted([a, b]))
        cell = pair.setdefault(canon, {"wins_a": 0, "wins_b": 0, "ties": 0, "both_bad": 0})
        flip = (canon[0] != a)  # vote stored with A/B swapped vs canonical order
        w = r["winner"]
        n = int(r["n"])
        if w == "tie":
            cell["ties"] += n
        elif w == "both_bad":
            cell["both_bad"] += n
        elif w == "a":
            if flip:
                cell["wins_b"] += n
            else:
                cell["wins_a"] += n
        elif w == "b":
            if flip:
                cell["wins_a"] += n
            else:
                cell["wins_b"] += n

    cells: List[Dict[str, Any]] = []
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            a, b = keys[i], keys[j]
            canon = tuple(sorted([a, b]))
            cell = pair.get(canon, {"wins_a": 0, "wins_b": 0, "ties": 0, "both_bad": 0})
            # Map canonical wins back to the row-vs-column convention.
            if canon[0] == a:
                wins_a, wins_b = cell["wins_a"], cell["wins_b"]
            else:
                wins_a, wins_b = cell["wins_b"], cell["wins_a"]
            total_scored = wins_a + wins_b + cell["ties"]
            win_rate_a = (
                round(((wins_a + 0.5 * cell["ties"]) / total_scored) * 100.0, 1)
                if total_scored else None
            )
            cells.append({
                "a":         a,
                "b":         b,
                "wins_a":    wins_a,
                "wins_b":    wins_b,
                "ties":      cell["ties"],
                "both_bad":  cell["both_bad"],
                "total":     total_scored + cell["both_bad"],
                "win_rate_a": win_rate_a,
            })

    providers = {k: _split_key(k)[0] for k in keys}
    return {"models": keys, "providers": providers, "cells": cells}


# ---------------------------------------------------------------------------
# Recent votes feed + per-vote enrichment
# ---------------------------------------------------------------------------


def recent_votes(limit: int = 20) -> List[Dict[str, Any]]:
    limit = max(1, min(int(limit), 200))
    with _DB_LOCK, _conn() as con:
        rows = con.execute(
            """SELECT * FROM votes ORDER BY created_at DESC LIMIT ?""", (limit,),
        ).fetchall()
    out = []
    for r in rows:
        out.append({
            "id":             r["id"],
            "created_at":     r["created_at"],
            "run_id":         r["run_id"],
            "prompt_hash":    r["prompt_hash"],
            "prompt_preview": r["prompt_preview"],
            "model_a":        r["model_a"],
            "model_b":        r["model_b"],
            "winner":         r["winner"],
            "voter":          r["voter"],
            "judge_winner":   r["judge_winner"],
            "latency_a":      r["latency_a"],
            "latency_b":      r["latency_b"],
            "cost_a":         r["cost_a"],
            "cost_b":         r["cost_b"],
        })
    return out


# ---------------------------------------------------------------------------
# Judge-vs-human agreement
# ---------------------------------------------------------------------------


def agreement(*, min_votes: int = 1) -> Dict[str, Any]:
    """How often did the human's pick match the LLM judge's #1?

    For every vote whose source run has a judge result, we compare the human
    pick (model_a / model_b / tie) to the judge's #1 model. We only count
    decisive cases on both sides; ties on either side don't contribute.

    Returns:
        {
          n: total votes considered,
          n_decisive: votes where both sides were decisive,
          agree: count where human pick == judge winner,
          agree_pct,
          per_model: [
            { model, n, agree, agree_pct }
          ]
        }
    """
    with _DB_LOCK, _conn() as con:
        rows = con.execute(
            """SELECT model_a, model_b, winner, judge_winner FROM votes
               WHERE judge_winner IS NOT NULL"""
        ).fetchall()

    n_total = len(rows)
    n_decisive = 0
    agree = 0
    per_model_n: Dict[str, int] = {}
    per_model_agree: Dict[str, int] = {}

    for r in rows:
        w = r["winner"]
        jw = r["judge_winner"]
        if w not in ("a", "b") or not jw:
            continue
        n_decisive += 1
        human_pick = r["model_a"] if w == "a" else r["model_b"]
        per_model_n[jw] = per_model_n.get(jw, 0) + 1
        if human_pick == jw:
            agree += 1
            per_model_agree[jw] = per_model_agree.get(jw, 0) + 1

    per_model_rows = []
    for key, n in per_model_n.items():
        if n < int(min_votes):
            continue
        a = per_model_agree.get(key, 0)
        provider, model = _split_key(key)
        per_model_rows.append({
            "key":        key,
            "provider":   provider,
            "model":      model,
            "n":          n,
            "agree":      a,
            "agree_pct":  round((a / n) * 100.0, 1) if n else 0.0,
        })
    per_model_rows.sort(key=lambda x: (-x["n"], -x["agree_pct"]))

    return {
        "n":           n_total,
        "n_decisive":  n_decisive,
        "agree":       agree,
        "agree_pct":   round((agree / n_decisive) * 100.0, 1) if n_decisive else None,
        "per_model":   per_model_rows,
    }


# ---------------------------------------------------------------------------
# Top-of-page stats (cheap aggregates).
# ---------------------------------------------------------------------------


def stats() -> Dict[str, Any]:
    with _DB_LOCK, _conn() as con:
        agg = con.execute(
            """SELECT COUNT(*) AS n,
                      COUNT(DISTINCT model_a || '||' || model_b) AS n_pairs,
                      COUNT(DISTINCT voter)                       AS n_voters,
                      MIN(created_at) AS first_at,
                      MAX(created_at) AS last_at,
                      SUM(CASE WHEN winner = 'tie'      THEN 1 ELSE 0 END) AS n_ties,
                      SUM(CASE WHEN winner = 'both_bad' THEN 1 ELSE 0 END) AS n_both_bad
               FROM votes"""
        ).fetchone()

    return {
        "n_votes":     int(agg["n"] or 0),
        "n_pairs":     int(agg["n_pairs"] or 0),
        "n_voters":    int(agg["n_voters"] or 0),
        "n_ties":      int(agg["n_ties"] or 0),
        "n_both_bad":  int(agg["n_both_bad"] or 0),
        "first_at":    agg["first_at"],
        "last_at":     agg["last_at"],
    }


# Initialise on import.
init_db()
