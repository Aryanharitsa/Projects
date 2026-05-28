"""Studio Insights — cross-cutting analytics over the whole evaluation history.

The playground already *measures* everything (Arena latency/cost, LLM-judge
composites, multi-judge consensus, blind-vote ELO) and *persists* it into
``history.db``. What it never did was step back and answer the one question
every LLM evaluation exists to answer:

    "Which model gives me the best quality per dollar?"

This module mines the existing ``runs`` table (plus the ELO replay in
``vote_arena``) and rolls it up into:

* **Model scorecards** — per ``Provider:model``: appearances, success rate,
  average latency, average cost per response, average judge composite, judge
  wins, ELO rating + win-rate, and a derived **quality-per-dollar** efficiency.
* **The efficiency frontier** — the Pareto frontier of *quality (judge
  composite, 0-100) vs cost ($/response)*. A model is *dominated* when another
  model is at least as good on quality **and** at least as cheap; the
  non-dominated set is the frontier — the only models you should ever pick from.
* **Spend timeline** — daily spend, run count, and average top score.
* **Provider roll-up** — spend share + mean quality per provider.
* **Headline summary** — total spend, best-value pick, top-quality pick, etc.

Everything is **derived** — no new tables, no writes. The whole surface is a
single read of data the rest of the app already produced, so it can never
disagree with History, Judge, or Vote: it *is* the same numbers, aggregated.

Pure stdlib (``sqlite3`` + a little arithmetic). Deterministic given the DB —
the same rows always produce the same scorecards, which is what makes it
testable without a single API key.
"""
from __future__ import annotations

import json
import math
import os
import sqlite3
import threading
import time
from contextlib import contextmanager
from typing import Any, Dict, List, Optional, Tuple

from src import vote_arena

# ---------------------------------------------------------------------------
# Storage — read-only view over the same history.db the rest of the app writes.
# ---------------------------------------------------------------------------

_DB_PATH = os.environ.get(
    "LLM_HISTORY_DB",
    os.path.join(os.path.dirname(__file__), "database", "history.db"),
)
_DB_LOCK = threading.Lock()

_DAY = 86400.0


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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _model_key(provider: Any, model: Any) -> str:
    return f"{provider or '?'}:{model or '?'}"


def _split_key(key: str) -> Tuple[str, str]:
    if key and ":" in key:
        p, m = key.split(":", 1)
        return p, m
    return "?", (key or "?")


def _num(v: Any) -> Optional[float]:
    try:
        if v is None:
            return None
        f = float(v)
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    except (TypeError, ValueError):
        return None


def _mean(values: List[float]) -> Optional[float]:
    vals = [v for v in values if v is not None]
    return (sum(vals) / len(vals)) if vals else None


def _day_floor(ts: float) -> float:
    """Floor a unix timestamp to the start of its UTC day."""
    return math.floor(ts / _DAY) * _DAY


# ---------------------------------------------------------------------------
# Per-model accumulation
# ---------------------------------------------------------------------------

class _Acc:
    """Mutable per-model accumulator. Plain object, not a dataclass, so this
    file has zero non-stdlib import surface."""

    __slots__ = (
        "appearances", "n_runs", "successes", "errors",
        "latencies", "costs", "tokens", "chars", "composites",
        "judge_wins", "first_at", "last_at",
    )

    def __init__(self) -> None:
        self.appearances = 0
        self.n_runs = 0
        self.successes = 0
        self.errors = 0
        self.latencies: List[float] = []
        self.costs: List[float] = []
        self.tokens: List[float] = []
        self.chars: List[float] = []
        self.composites: List[float] = []
        self.judge_wins = 0
        self.first_at: Optional[float] = None
        self.last_at: Optional[float] = None


def _load_runs() -> List[sqlite3.Row]:
    with _DB_LOCK, _conn() as con:
        try:
            return con.execute(
                """SELECT id, created_at, total_cost_usd, judged,
                          judge_winner, judge_top_score, payload
                   FROM runs
                   ORDER BY created_at ASC"""
            ).fetchall()
        except sqlite3.OperationalError:
            # `runs` table not created yet (fresh DB) — nothing to analyse.
            return []


def _composite_index(payload: Dict[str, Any]) -> Dict[str, float]:
    """Map ``Provider:model`` → judge composite for a run's verdicts.

    Works for single-judge runs and for consensus runs (history.update_consensus
    writes a back-compat ``payload.judge`` with per-candidate composites from the
    panel means), so both render through one path."""
    judge = (payload or {}).get("judge") or {}
    verdicts = judge.get("verdicts") or []
    out: Dict[str, float] = {}
    for v in verdicts:
        c = _num(v.get("composite"))
        if c is None:
            continue
        out[_model_key(v.get("provider"), v.get("model"))] = c
    return out


def _aggregate(rows: List[sqlite3.Row]) -> Tuple[Dict[str, _Acc], Dict[str, Any]]:
    """Walk every run once, building per-model accumulators + global totals."""
    acc: Dict[str, _Acc] = {}
    total_spend = 0.0
    n_judged = 0
    judge_top_scores: List[float] = []

    for row in rows:
        created = _num(row["created_at"]) or 0.0
        total_spend += _num(row["total_cost_usd"]) or 0.0
        judged = bool(row["judged"])
        if judged:
            n_judged += 1
            jts = _num(row["judge_top_score"])
            if jts is not None:
                judge_top_scores.append(jts)

        try:
            payload = json.loads(row["payload"] or "{}")
        except (TypeError, ValueError):
            payload = {}

        comp_by_key = _composite_index(payload)
        judge_winner_key = (row["judge_winner"] or None) if judged else None

        for r in payload.get("results") or []:
            key = _model_key(r.get("provider"), r.get("model"))
            a = acc.get(key)
            if a is None:
                a = acc[key] = _Acc()
            a.appearances += 1
            a.n_runs += 1
            if a.first_at is None or created < a.first_at:
                a.first_at = created
            if a.last_at is None or created > a.last_at:
                a.last_at = created

            status = r.get("status")
            if status == "success":
                a.successes += 1
            else:
                a.errors += 1

            lat = _num(r.get("latency"))
            if lat is not None and status == "success":
                a.latencies.append(lat)
            cost = _num(r.get("cost_usd"))
            if cost is not None:
                a.costs.append(cost)
            tok = _num(r.get("total_tokens"))
            if tok is not None:
                a.tokens.append(tok)
            body = r.get("response")
            if isinstance(body, str) and body:
                a.chars.append(float(len(body)))

            if key in comp_by_key:
                a.composites.append(comp_by_key[key])
            if judge_winner_key and key == judge_winner_key:
                a.judge_wins += 1

    totals = {
        "total_spend": round(total_spend, 6),
        "n_runs": len(rows),
        "n_judged_runs": n_judged,
        "avg_top_score": _mean(judge_top_scores),
        "first_at": (_num(rows[0]["created_at"]) if rows else None),
        "last_at": (_num(rows[-1]["created_at"]) if rows else None),
    }
    return acc, totals


# ---------------------------------------------------------------------------
# Scorecards
# ---------------------------------------------------------------------------

def model_scorecards(
    *,
    min_appearances: int = 1,
    elo: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """One row per ``Provider:model``, sorted by quality-per-dollar (then
    quality, then cost). ``elo`` is an optional pre-computed
    ``vote_arena.leaderboard()`` payload (passed in so the bundle endpoint only
    replays votes once)."""
    rows = _load_runs()
    acc, _ = _aggregate(rows)

    elo = elo if elo is not None else vote_arena.leaderboard()
    elo_by_key = {r["key"]: r for r in (elo.get("ratings") or [])}

    cards: List[Dict[str, Any]] = []
    for key, a in acc.items():
        if a.appearances < int(min_appearances):
            continue
        provider, model = _split_key(key)
        avg_cost = _mean(a.costs)
        avg_comp = _mean(a.composites)
        qpd = (
            (avg_comp / avg_cost)
            if (avg_comp is not None and avg_cost is not None and avg_cost > 0)
            else None
        )
        er = elo_by_key.get(key) or {}
        cards.append({
            "key":            key,
            "provider":       provider,
            "model":          model,
            "appearances":    a.appearances,
            "successes":      a.successes,
            "errors":         a.errors,
            "success_rate":   round((a.successes / a.appearances) * 100.0, 1) if a.appearances else 0.0,
            "avg_latency":    round(_mean(a.latencies), 3) if a.latencies else None,
            "avg_cost":       round(avg_cost, 6) if avg_cost is not None else None,
            "avg_tokens":     round(_mean(a.tokens), 0) if a.tokens else None,
            "avg_chars":      round(_mean(a.chars), 0) if a.chars else None,
            "avg_composite":  round(avg_comp, 2) if avg_comp is not None else None,
            "n_judged":       len(a.composites),
            "judge_wins":     a.judge_wins,
            "quality_per_dollar": round(qpd, 1) if qpd is not None else None,
            "is_free":        (avg_cost is not None and avg_cost <= 0),
            "elo":            er.get("rating"),
            "elo_games":      er.get("games", 0),
            "elo_win_rate":   er.get("win_rate"),
            "first_at":       a.first_at,
            "last_at":        a.last_at,
        })

    # Efficiency index — min/max normalise quality-per-dollar to 0-100 so the UI
    # can draw a comparable bar. Models without a $-quality signal get None.
    qpds = [c["quality_per_dollar"] for c in cards if c["quality_per_dollar"] is not None]
    if qpds:
        lo, hi = min(qpds), max(qpds)
        span = (hi - lo) or 1.0
        for c in cards:
            q = c["quality_per_dollar"]
            c["efficiency_index"] = round(((q - lo) / span) * 100.0, 1) if q is not None else None
    else:
        for c in cards:
            c["efficiency_index"] = None

    cards.sort(key=lambda c: (
        -(c["quality_per_dollar"] if c["quality_per_dollar"] is not None else -1),
        -(c["avg_composite"] if c["avg_composite"] is not None else -1),
        (c["avg_cost"] if c["avg_cost"] is not None else float("inf")),
    ))
    return cards


# ---------------------------------------------------------------------------
# Efficiency (Pareto) frontier
# ---------------------------------------------------------------------------

def efficiency_frontier(cards: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Pareto frontier of *maximise quality (composite) · minimise cost*.

    A model is **dominated** when some other eligible model has
    ``composite >= mine`` AND ``avg_cost <= mine`` with at least one strict —
    i.e. you'd never rationally pick the dominated one. The non-dominated set is
    the frontier. We only consider models with a judge composite and a positive
    cost (the two axes); everything else is reported under ``unplaced`` with a
    reason so the UI can nudge the user to judge them.
    """
    eligible: List[Dict[str, Any]] = []
    unplaced: List[Dict[str, Any]] = []
    for c in cards:
        if c["avg_composite"] is None:
            unplaced.append({"key": c["key"], "reason": "no_judge_score"})
        elif c["avg_cost"] is None or c["avg_cost"] <= 0:
            unplaced.append({"key": c["key"], "reason": "no_cost"})
        else:
            eligible.append(c)

    points: List[Dict[str, Any]] = []
    for c in eligible:
        q, cost = c["avg_composite"], c["avg_cost"]
        dominators: List[str] = []
        for o in eligible:
            if o["key"] == c["key"]:
                continue
            oq, ocost = o["avg_composite"], o["avg_cost"]
            at_least_as_good = (oq >= q) and (ocost <= cost)
            strictly_better = (oq > q) or (ocost < cost)
            if at_least_as_good and strictly_better:
                dominators.append(o["key"])
        points.append({
            "key":           c["key"],
            "provider":      c["provider"],
            "model":         c["model"],
            "quality":       q,
            "cost":          cost,
            "quality_per_dollar": c["quality_per_dollar"],
            "appearances":   c["appearances"],
            "elo":           c["elo"],
            "on_frontier":   len(dominators) == 0,
            "dominated_by":  dominators,
        })

    frontier_keys = sorted(
        [p["key"] for p in points if p["on_frontier"]],
        key=lambda k: next(pt["cost"] for pt in points if pt["key"] == k),
    )
    return {
        "points":        points,
        "frontier":      frontier_keys,
        "n_eligible":    len(eligible),
        "n_on_frontier": len(frontier_keys),
        "unplaced":      unplaced,
    }


# ---------------------------------------------------------------------------
# Spend / quality timeline
# ---------------------------------------------------------------------------

def cost_timeline() -> List[Dict[str, Any]]:
    """Per-UTC-day spend, run count, judged count, and average top score."""
    rows = _load_runs()
    buckets: Dict[float, Dict[str, Any]] = {}
    for row in rows:
        created = _num(row["created_at"])
        if created is None:
            continue
        day = _day_floor(created)
        b = buckets.get(day)
        if b is None:
            b = buckets[day] = {"day": day, "spend": 0.0, "runs": 0,
                                "judged": 0, "_scores": []}
        b["spend"] += _num(row["total_cost_usd"]) or 0.0
        b["runs"] += 1
        if bool(row["judged"]):
            b["judged"] += 1
            jts = _num(row["judge_top_score"])
            if jts is not None:
                b["_scores"].append(jts)

    out: List[Dict[str, Any]] = []
    for day in sorted(buckets):
        b = buckets[day]
        out.append({
            "day":           day,
            "spend":         round(b["spend"], 6),
            "runs":          b["runs"],
            "judged":        b["judged"],
            "avg_top_score": round(_mean(b["_scores"]), 2) if b["_scores"] else None,
        })
    return out


# ---------------------------------------------------------------------------
# Provider roll-up
# ---------------------------------------------------------------------------

def provider_rollup(cards: List[Dict[str, Any]], total_spend: float) -> List[Dict[str, Any]]:
    """Aggregate scorecards up to the provider level (OpenAI / Anthropic / …)."""
    by_prov: Dict[str, Dict[str, Any]] = {}
    for c in cards:
        p = c["provider"]
        b = by_prov.get(p)
        if b is None:
            b = by_prov[p] = {"provider": p, "models": 0, "appearances": 0,
                              "spend": 0.0, "_quality": [], "judge_wins": 0}
        b["models"] += 1
        b["appearances"] += c["appearances"]
        # spend ≈ avg_cost × appearances (cost is per-response).
        if c["avg_cost"] is not None:
            b["spend"] += c["avg_cost"] * c["appearances"]
        if c["avg_composite"] is not None:
            b["_quality"].append(c["avg_composite"])
        b["judge_wins"] += c["judge_wins"]

    rows: List[Dict[str, Any]] = []
    for p, b in by_prov.items():
        rows.append({
            "provider":     p,
            "models":       b["models"],
            "appearances":  b["appearances"],
            "spend":        round(b["spend"], 6),
            "spend_share":  round((b["spend"] / total_spend) * 100.0, 1) if total_spend > 0 else 0.0,
            "avg_quality":  round(_mean(b["_quality"]), 2) if b["_quality"] else None,
            "judge_wins":   b["judge_wins"],
        })
    rows.sort(key=lambda r: -r["spend"])
    return rows


# ---------------------------------------------------------------------------
# Headline summary
# ---------------------------------------------------------------------------

def _pick(cards: List[Dict[str, Any]], key: str, *, want_max: bool,
          require: Optional[str] = None) -> Optional[Dict[str, Any]]:
    pool = [c for c in cards if c.get(key) is not None]
    if require:
        pool = [c for c in pool if c.get(require) is not None]
    if not pool:
        return None
    return (max if want_max else min)(pool, key=lambda c: c[key])


def build_insights(*, min_appearances: int = 1) -> Dict[str, Any]:
    """The whole analytics bundle in one read — powers ``GET /api/insights``."""
    rows = _load_runs()
    _, totals = _aggregate(rows)
    elo = vote_arena.leaderboard()
    cards = model_scorecards(min_appearances=min_appearances, elo=elo)
    frontier = efficiency_frontier(cards)
    timeline = cost_timeline()
    providers = provider_rollup(cards, totals["total_spend"])

    # Recent-window spend trend, anchored on the latest run so it's deterministic.
    now_ref = totals["last_at"] or time.time()
    last_7d = sum(d["spend"] for d in timeline if d["day"] >= now_ref - 7 * _DAY)
    prev_7d = sum(d["spend"] for d in timeline
                  if now_ref - 14 * _DAY <= d["day"] < now_ref - 7 * _DAY)
    spend_trend_pct = (
        round(((last_7d - prev_7d) / prev_7d) * 100.0, 1) if prev_7d > 0 else None
    )

    frontier_keys = set(frontier["frontier"])
    best_value = _pick(
        [c for c in cards if c["key"] in frontier_keys],
        "quality_per_dollar", want_max=True,
    ) or _pick(cards, "quality_per_dollar", want_max=True)
    top_quality = _pick(cards, "avg_composite", want_max=True)
    cheapest = _pick([c for c in cards if (c["avg_cost"] or 0) > 0], "avg_cost", want_max=False)
    fastest = _pick(cards, "avg_latency", want_max=False)
    top_elo = _pick([c for c in cards if (c["elo_games"] or 0) > 0], "elo", want_max=True)

    def _ref(card: Optional[Dict[str, Any]], *fields: str) -> Optional[Dict[str, Any]]:
        if not card:
            return None
        out = {"key": card["key"], "provider": card["provider"], "model": card["model"]}
        for f in fields:
            out[f] = card.get(f)
        return out

    summary = {
        "total_spend":      totals["total_spend"],
        "n_runs":           totals["n_runs"],
        "n_judged_runs":    totals["n_judged_runs"],
        "n_models":         len(cards),
        "avg_top_score":    round(totals["avg_top_score"], 2) if totals["avg_top_score"] is not None else None,
        "spend_last_7d":    round(last_7d, 6),
        "spend_prev_7d":    round(prev_7d, 6),
        "spend_trend_pct":  spend_trend_pct,
        "best_value":       _ref(best_value, "quality_per_dollar", "avg_composite", "avg_cost"),
        "top_quality":      _ref(top_quality, "avg_composite", "avg_cost"),
        "cheapest":         _ref(cheapest, "avg_cost", "avg_composite"),
        "fastest":          _ref(fastest, "avg_latency"),
        "top_elo":          _ref(top_elo, "elo", "elo_games"),
        "first_at":         totals["first_at"],
        "last_at":          totals["last_at"],
    }

    return {
        "summary":    summary,
        "scorecards": cards,
        "frontier":   frontier,
        "timeline":   timeline,
        "providers":  providers,
        "elo_meta":   elo.get("meta", {}),
    }
