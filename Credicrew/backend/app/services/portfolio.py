"""Hiring Command Center engine — Python mirror of frontend/src/lib/portfolio.ts.

Aggregates a flattened snapshot of every role + its shortlist (each
candidate carrying its match score, interview composite, offer draft, and
accept-probability) into one portfolio summary: hero KPIs, an aggregate
stage funnel with conversion, a committed-vs-expected comp forecast,
per-role health scores, a cross-role talent leaderboard, and a prioritised
attention feed.

Pure functions; no I/O. Output is camelCase-friendly so the TS engine and
this engine emit byte-identical payloads for the same input.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Optional


PROGRESSION = ["new", "outreach", "screening", "interview", "offer"]
NON_TERMINAL = {"new", "outreach", "screening", "interview"}

STAGE_LABEL = {
    "new": "New",
    "outreach": "Outreach",
    "screening": "Screening",
    "interview": "Interview",
    "offer": "Offer",
}

DAY_MS = 86_400_000
STALE_DAYS = 14
FAST_TRACK_SIGNAL = 75
OFFER_RISK_PROB = 0.45

SEVERITY_RANK = {"high": 0, "medium": 1, "low": 2}


# ---------- input dataclasses ----------


@dataclass
class PortfolioOffer:
    base: float
    equity_pct: float
    target_bonus_pct: float
    sign_on: float


@dataclass
class PortfolioCandidate:
    candidate_id: int
    name: str
    status: str
    added_at: int
    match_score: int
    composite: Optional[int] = None
    confidence: float = 0.0
    recommendation: Optional[str] = None
    role: Optional[str] = None
    offer: Optional[PortfolioOffer] = None
    win_probability: Optional[float] = None


@dataclass
class PortfolioRole:
    id: str
    name: str
    created_at: int
    updated_at: int
    candidates: list[PortfolioCandidate] = field(default_factory=list)
    seniority: Optional[str] = None
    location: Optional[str] = None


# ---------- math helpers ----------


def _round(n: float, dp: int = 2) -> float:
    return round(float(n), dp)


def hire_signal(composite: Optional[int], confidence: float) -> int:
    if composite is None:
        return 0
    conf = max(0.0, min(1.0, confidence))
    return round(composite * math.sqrt(conf))


def total_cash(o: PortfolioOffer) -> float:
    return o.base + o.sign_on + o.base * (o.target_bonus_pct / 100.0)


# ---------- derived per-candidate view ----------


@dataclass
class _Derived:
    cand: PortfolioCandidate
    role_id: str
    role_name: str
    signal: int
    age_days: int
    is_active: bool
    is_stale: bool


def _derive(roles: list[PortfolioRole], now: int) -> list[_Derived]:
    out: list[_Derived] = []
    for role in roles:
        for c in role.candidates:
            age_days = max(0, (now - c.added_at) // DAY_MS)
            is_active = c.status != "passed"
            non_terminal = c.status in NON_TERMINAL
            out.append(
                _Derived(
                    cand=c,
                    role_id=role.id,
                    role_name=role.name,
                    signal=hire_signal(c.composite, c.confidence),
                    age_days=age_days,
                    is_active=is_active,
                    is_stale=is_active and non_terminal and age_days >= STALE_DAYS,
                )
            )
    return out


# ---------- funnel ----------


def _build_funnel(rows: list[_Derived]) -> list[dict]:
    here = {k: 0 for k in PROGRESSION}
    for r in rows:
        if r.cand.status == "passed":
            continue
        if r.cand.status in here:
            here[r.cand.status] += 1
    reached = {k: 0 for k in PROGRESSION}
    acc = 0
    for k in reversed(PROGRESSION):
        acc += here[k]
        reached[k] = acc
    out = []
    for i, key in enumerate(PROGRESSION):
        prev = reached[PROGRESSION[i - 1]] if i > 0 else None
        conv = _round(reached[key] / prev, 4) if (prev is not None and prev > 0) else None
        out.append(
            {
                "key": key,
                "here": here[key],
                "reached": reached[key],
                "conversionFromPrev": conv,
            }
        )
    return out


# ---------- comp forecast ----------


def _build_comp(rows: list[_Derived]) -> dict:
    with_offer = [r for r in rows if r.cand.offer]
    committed = 0.0
    expected = 0.0
    base_sum = 0.0
    prob_sum = 0.0
    role_spend: dict[str, float] = {}
    for r in with_offer:
        tc = total_cash(r.cand.offer)  # type: ignore[arg-type]
        p = r.cand.win_probability if r.cand.win_probability is not None else 0.5
        committed += tc
        expected += tc * p
        base_sum += r.cand.offer.base  # type: ignore[union-attr]
        prob_sum += p
        role_spend[r.role_id] = role_spend.get(r.role_id, 0.0) + tc
    n = len(with_offer)
    top_role = None
    top_spend = -1.0
    for rid, spend in role_spend.items():
        if spend > top_spend:
            top_spend = spend
            top_role = rid
    return {
        "offers": n,
        "committedAnnual": _round(committed),
        "expectedAnnual": _round(expected),
        "avgBase": _round(base_sum / n) if n > 0 else 0,
        "avgWinProbability": _round(prob_sum / n, 4) if n > 0 else 0,
        "topSpendRoleId": top_role,
    }


# ---------- per-role health ----------


def _role_health_score(cands: list[_Derived]) -> Optional[int]:
    if not cands:
        return None
    parts: list[tuple[float, float]] = []  # (weight, value)

    active = [c for c in cands if c.is_active]
    if active:
        stale = sum(1 for c in active if c.is_stale)
        parts.append((0.30, 1 - stale / len(active)))

    reached_interview = [c for c in cands if c.cand.status in ("interview", "offer")]
    if reached_interview:
        done = sum(1 for c in reached_interview if c.cand.composite is not None)
        parts.append((0.25, done / len(reached_interview)))

    interviewed = [c for c in cands if c.cand.composite is not None]
    if interviewed:
        mean_sig = sum(c.signal for c in interviewed) / len(interviewed)
        parts.append((0.25, mean_sig / 100))

    offers = [c for c in cands if c.cand.offer]
    if offers:
        mean_p = sum(
            (c.cand.win_probability if c.cand.win_probability is not None else 0.5)
            for c in offers
        ) / len(offers)
        parts.append((0.20, mean_p))

    if not parts:
        return None
    wsum = sum(w for w, _ in parts)
    score = sum(w * v for w, v in parts) / wsum
    return round(max(0.0, min(1.0, score)) * 100)


def _build_role_health(roles: list[PortfolioRole], rows: list[_Derived], now: int) -> list[dict]:
    by_role: dict[str, list[_Derived]] = {}
    for r in rows:
        by_role.setdefault(r.role_id, []).append(r)

    out = []
    for role in roles:
        cands = by_role.get(role.id, [])
        active = [c for c in cands if c.is_active]
        interviewed = [c for c in cands if c.cand.composite is not None]
        offers = [c for c in cands if c.cand.status == "offer"]
        stale = [c for c in cands if c.is_stale]

        top = None
        ranked = sorted(interviewed, key=lambda c: c.signal, reverse=True)
        if ranked:
            top = {
                "candidateId": ranked[0].cand.candidate_id,
                "name": ranked[0].cand.name,
                "hireSignal": ranked[0].signal,
            }
        elif cands:
            by_match = sorted(cands, key=lambda c: c.cand.match_score, reverse=True)[0]
            top = {
                "candidateId": by_match.cand.candidate_id,
                "name": by_match.cand.name,
                "hireSignal": 0,
            }

        best_composite = (
            max(c.cand.composite for c in interviewed) if interviewed else None  # type: ignore[type-var]
        )

        stage_count: dict[str, int] = {}
        for c in active:
            if c.cand.status == "offer":
                continue
            stage_count[c.cand.status] = stage_count.get(c.cand.status, 0) + 1
        bottleneck = None
        bn = 1
        for s in PROGRESSION:
            if s == "offer":
                continue
            cnt = stage_count.get(s, 0)
            if cnt > bn:
                bn = cnt
                bottleneck = s

        out.append(
            {
                "roleId": role.id,
                "roleName": role.name,
                "seniority": role.seniority,
                "location": role.location,
                "candidates": len(cands),
                "active": len(active),
                "interviewed": len(interviewed),
                "offers": len(offers),
                "stale": len(stale),
                "daysOpen": max(0, (now - role.created_at) // DAY_MS),
                "topCandidate": top,
                "bestComposite": best_composite,
                "bottleneck": bottleneck,
                "health": _role_health_score(cands),
            }
        )
    return out


# ---------- talent ----------


def _build_talent(rows: list[_Derived]) -> list[dict]:
    interviewed = [r for r in rows if r.cand.composite is not None]
    interviewed.sort(
        key=lambda r: (r.signal, r.cand.composite, r.cand.match_score),
        reverse=True,
    )
    out = []
    for r in interviewed[:8]:
        out.append(
            {
                "roleId": r.role_id,
                "roleName": r.role_name,
                "candidateId": r.cand.candidate_id,
                "name": r.cand.name,
                "role": r.cand.role,
                "status": r.cand.status,
                "matchScore": r.cand.match_score,
                "composite": r.cand.composite,
                "hireSignal": r.signal,
                "recommendation": r.cand.recommendation,
            }
        )
    return out


# ---------- attention feed ----------


def _build_attention(roles: list[PortfolioRole], rows: list[_Derived]) -> list[dict]:
    items: list[dict] = []
    by_role: dict[str, list[_Derived]] = {}
    for r in rows:
        by_role.setdefault(r.role_id, []).append(r)

    stale = sorted((r for r in rows if r.is_stale), key=lambda r: r.age_days, reverse=True)
    for r in stale:
        label = STAGE_LABEL.get(r.cand.status, r.cand.status)
        items.append(
            {
                "kind": "stale_candidate",
                "severity": "high" if r.age_days >= 21 else "medium",
                "roleId": r.role_id,
                "roleName": r.role_name,
                "candidateId": r.cand.candidate_id,
                "candidateName": r.cand.name,
                "message": f"{r.cand.name} has sat in {label} for {r.age_days} days — nudge or advance.",
            }
        )

    for r in rows:
        if r.cand.status != "offer" or not r.cand.offer or r.cand.win_probability is None:
            continue
        if r.cand.win_probability < OFFER_RISK_PROB:
            items.append(
                {
                    "kind": "offer_at_risk",
                    "severity": "high" if r.cand.win_probability < 0.3 else "medium",
                    "roleId": r.role_id,
                    "roleName": r.role_name,
                    "candidateId": r.cand.candidate_id,
                    "candidateName": r.cand.name,
                    "message": (
                        f"{r.cand.name}'s offer is tracking {round(r.cand.win_probability * 100)}% "
                        "to accept — sweeten the package or line up a backup."
                    ),
                }
            )

    for r in rows:
        if r.signal >= FAST_TRACK_SIGNAL and r.cand.status in ("new", "outreach"):
            label = STAGE_LABEL.get(r.cand.status, r.cand.status)
            items.append(
                {
                    "kind": "fast_track",
                    "severity": "medium",
                    "roleId": r.role_id,
                    "roleName": r.role_name,
                    "candidateId": r.cand.candidate_id,
                    "candidateName": r.cand.name,
                    "message": (
                        f"{r.cand.name} is a signal-{r.signal} candidate still in {label} — "
                        "fast-track before they're gone."
                    ),
                }
            )

    for role in roles:
        cands = by_role.get(role.id, [])
        if not cands:
            items.append(
                {
                    "kind": "empty_role",
                    "severity": "low",
                    "roleId": role.id,
                    "roleName": role.name,
                    "message": (
                        f"{role.name} has no candidates yet — source a shortlist to get the loop moving."
                    ),
                }
            )
            continue
        interviewed = sum(1 for c in cands if c.cand.composite is not None)
        active = sum(1 for c in cands if c.is_active)
        if interviewed == 0 and active > 0:
            items.append(
                {
                    "kind": "no_interviews",
                    "severity": "medium",
                    "roleId": role.id,
                    "roleName": role.name,
                    "message": (
                        f"{role.name} has {active} active candidate{'' if active == 1 else 's'} "
                        "but no interviews scored — schedule first-round panels."
                    ),
                }
            )

    items.sort(key=lambda it: SEVERITY_RANK[it["severity"]])
    return items[:10]


# ---------- portfolio health ----------


def _portfolio_health(role_health: list[dict]) -> Optional[int]:
    scored = [r for r in role_health if r["health"] is not None and r["candidates"] > 0]
    if not scored:
        return None
    wsum = 0.0
    acc = 0.0
    for r in scored:
        w = max(1, r["active"])
        wsum += w
        acc += w * r["health"]
    return round(acc / wsum)


# ---------- main ----------


def build_portfolio(roles: list[PortfolioRole], now: Optional[int] = None) -> dict:
    if now is None:
        now = int(time.time() * 1000)
    rows = _derive(roles, now)

    totals = {
        "roles": len(roles),
        "candidates": len(rows),
        "active": sum(1 for r in rows if r.is_active),
        "interviewed": sum(1 for r in rows if r.cand.composite is not None),
        "offers": sum(1 for r in rows if r.cand.status == "offer"),
        "passed": sum(1 for r in rows if r.cand.status == "passed"),
        "staleCandidates": sum(1 for r in rows if r.is_stale),
    }

    recommendation_mix = {
        "no_hire": 0, "lean_no": 0, "mixed": 0, "lean_yes": 0, "strong_hire": 0,
    }
    for r in rows:
        if r.cand.recommendation in recommendation_mix:
            recommendation_mix[r.cand.recommendation] += 1

    funnel = _build_funnel(rows)
    comp = _build_comp(rows)
    role_health = _build_role_health(roles, rows, now)
    talent = _build_talent(rows)
    attention = _build_attention(roles, rows)

    stage_count: dict[str, int] = {}
    for r in rows:
        if not r.is_active or r.cand.status == "offer":
            continue
        stage_count[r.cand.status] = stage_count.get(r.cand.status, 0) + 1
    bottleneck = None
    bn = 1
    for s in PROGRESSION:
        if s == "offer":
            continue
        cnt = stage_count.get(s, 0)
        if cnt > bn:
            bn = cnt
            bottleneck = s

    return {
        "totals": totals,
        "funnel": funnel,
        "compForecast": comp,
        "roleHealth": role_health,
        "talent": talent,
        "attention": attention,
        "recommendationMix": recommendation_mix,
        "portfolioHealth": _portfolio_health(role_health),
        "bottleneck": bottleneck,
        "generatedAt": now,
    }
