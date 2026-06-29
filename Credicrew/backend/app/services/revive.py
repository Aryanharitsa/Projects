"""Revive — Silver Medalist Reactivation Engine (Python mirror).

Same physics, same thresholds, same outputs as
``frontend/src/lib/revive.ts`` so a backend client (or an agent calling
``POST /revive/summary``) gets byte-identical reactivation opportunities
for the same fixture.

Inputs
------
* ``roles`` — list of role dicts with ``id``, ``name``, ``plan`` (text)
  and a ``shortlist`` of ``{candidate_id, status, added_at?,
  stage_changed_at?, note?}`` entries.
* ``candidates`` — list of candidate dicts ``{id, name, tags, keywords,
  role, location, headline}`` — same shape the frontend's
  ``candidates.ts`` exports.

Outputs
-------
A summary dataclass-as-dict mirroring the TS ``ReviveSummary``:
``silver``, ``opportunities``, ``per_candidate``, ``per_role``,
``revivable_count``, ``estimated_cost_saved_usd``, ``top_pick``,
``reactivation_histogram``.
"""
from __future__ import annotations

import math
import time
from dataclasses import asdict, dataclass, field
from typing import Any

from app.services.match import MatchResult, QueryPlan, match_candidate, plan_query

RECENCY_HALF_LIFE_DAYS = 90
RECENCY_FLOOR = 0.5
REVIVE_MATCH_FLOOR = 65
REVIVE_COMPOSITE_FLOOR = 55
STALE_DAYS = 180
SOURCING_COST_PER_HIRE_USD = 1500
PER_ROLE_LIMIT = 8

DAY_MS = 86_400_000


# ---------- pure math ----------

def days_between(ms: float, now_ms: float) -> int:
    if not ms or ms <= 0:
        return 0
    return max(0, int((now_ms - ms) // DAY_MS))


def recency_factor(days_dormant: int) -> float:
    if days_dormant <= 0:
        return 1.0
    return math.pow(2, -days_dormant / RECENCY_HALF_LIFE_DAYS)


def reactivation_score(match_score: int, recency: float) -> int:
    r = max(0.0, min(1.0, recency))
    tilt = RECENCY_FLOOR + (1 - RECENCY_FLOOR) * r
    return int(round(max(0.0, min(100.0, match_score * tilt))))


# ---------- types ----------

@dataclass
class SilverEntry:
    candidate_id: int
    candidate_name: str
    from_role_id: str
    from_role_name: str
    passed_at_ms: float
    days_dormant: int
    from_score: int
    note: str | None = None


@dataclass
class ReviveOpportunity:
    candidate_id: int
    candidate_name: str
    from_role_id: str
    from_role_name: str
    from_score: int
    to_role_id: str
    to_role_name: str
    to_score: int
    delta: int
    days_dormant: int
    recency: float
    reactivation_score: int
    matched_skills: list[str]
    missing_skills: list[str]
    location_match: str
    seniority_match: bool
    why: list[str] = field(default_factory=list)
    stale: bool = False


@dataclass
class CandidateBest:
    silver: SilverEntry
    best: ReviveOpportunity | None
    alternatives: list[ReviveOpportunity] = field(default_factory=list)


@dataclass
class RoleTopPicks:
    role_id: str
    role_name: str
    picks: list[ReviveOpportunity]
    best_score: int


@dataclass
class ReviveSummary:
    generated_at: int
    silver: list[SilverEntry]
    opportunities: list[ReviveOpportunity]
    per_candidate: list[CandidateBest]
    per_role: list[RoleTopPicks]
    revivable_count: int
    estimated_cost_saved_usd: int
    top_pick: ReviveOpportunity | None
    reactivation_histogram: list[int]


# ---------- engine ----------

def _why_lines(
    silver: SilverEntry,
    match: MatchResult,
    to_role_name: str,
    delta: int,
    recency: float,
    days_dormant: int,
) -> list[str]:
    lines: list[str] = []
    if delta >= 15:
        lines.append(f"+{delta} pts vs original role — strictly better fit.")
    elif delta >= 5:
        lines.append(f"+{delta} pts vs {silver.from_role_name} — modest upside.")
    elif delta >= -5:
        lines.append("Comparable fit to original role; routes a sunk-cost candidate.")
    else:
        lines.append(f"Lower than original ({delta} pts) but still ≥ revive floor.")

    matched = list(match.matched_skills)
    missing = list(match.missing_skills)
    if len(matched) >= 3:
        sample = ", ".join(matched[:4])
        suffix = "…" if len(matched) > 4 else ""
        lines.append(f"Matches {len(matched)} skills for {to_role_name}: {sample}{suffix}.")
    elif len(matched) == 0 and len(missing) == 0:
        lines.append("Role JD specifies no required skills — soft match only.")

    if match.location_match == "full":
        lines.append("Location aligns.")
    elif match.location_match == "partial":
        lines.append("Location is a partial (flex) match.")

    if recency >= 0.85:
        lines.append(
            f"Passed only {days_dormant} day{'' if days_dormant == 1 else 's'} ago — easy to re-open the thread."
        )
    elif days_dormant >= STALE_DAYS:
        lines.append(f"Dormant {days_dormant} days — confirm interest before re-engaging.")

    return lines


def _resolved_plan(role: dict[str, Any]) -> QueryPlan:
    plan = role.get("plan")
    if isinstance(plan, dict) and plan.get("skills") is not None:
        return QueryPlan(
            text=plan.get("text") or role.get("jd") or "",
            skills=list(plan.get("skills") or []),
            location=plan.get("location"),
            seniority=plan.get("seniority"),
        )
    text = role.get("jd") or (plan.get("text") if isinstance(plan, dict) else "") or ""
    return plan_query(text)


def analyze_revive(
    roles: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    now_ms: int | None = None,
) -> ReviveSummary:
    now = now_ms if now_ms is not None else int(time.time() * 1000)

    by_id: dict[int, dict[str, Any]] = {int(c["id"]): c for c in candidates if "id" in c}

    # Pre-compute every role's shortlist membership.
    on_shortlist_of: dict[int, set[str]] = {}
    for role in roles:
        for e in role.get("shortlist") or []:
            cid = int(e.get("candidate_id") or e.get("candidateId") or 0)
            if cid == 0:
                continue
            on_shortlist_of.setdefault(cid, set()).add(role["id"])

    # Resolve plans once per role.
    plans: dict[str, QueryPlan] = {r["id"]: _resolved_plan(r) for r in roles}

    # Lift out passed entries.
    silver_by_key: dict[str, SilverEntry] = {}
    for role in roles:
        for e in role.get("shortlist") or []:
            status = e.get("status")
            if status != "passed":
                continue
            cid = int(e.get("candidate_id") or e.get("candidateId") or 0)
            cand = by_id.get(cid)
            if not cand:
                continue
            passed_at = float(
                e.get("stage_changed_at")
                or e.get("stageChangedAt")
                or e.get("added_at")
                or e.get("addedAt")
                or 0
            )
            days = days_between(passed_at, now)
            home_match = match_candidate(plans[role["id"]], cand)
            key = f"{cid}::{role['id']}"
            silver_by_key[key] = SilverEntry(
                candidate_id=cid,
                candidate_name=cand.get("name") or f"Candidate {cid}",
                from_role_id=role["id"],
                from_role_name=role.get("name") or "",
                passed_at_ms=passed_at,
                days_dormant=days,
                from_score=home_match.score,
                note=e.get("note"),
            )
    silver = list(silver_by_key.values())

    opportunities: list[ReviveOpportunity] = []
    histogram = [0] * 11

    for s in silver:
        occupied = on_shortlist_of.get(s.candidate_id, set())
        recency = recency_factor(s.days_dormant)
        stale = s.days_dormant >= STALE_DAYS

        cand = by_id.get(s.candidate_id)
        if not cand:
            continue

        for role in roles:
            if role["id"] == s.from_role_id:
                continue
            if role["id"] in occupied:
                continue
            m = match_candidate(plans[role["id"]], cand)
            if m.score < REVIVE_MATCH_FLOOR:
                continue

            composite = reactivation_score(m.score, recency)
            delta = m.score - s.from_score
            why = _why_lines(s, m, role.get("name") or "", delta, recency, s.days_dormant)

            opportunities.append(
                ReviveOpportunity(
                    candidate_id=s.candidate_id,
                    candidate_name=s.candidate_name,
                    from_role_id=s.from_role_id,
                    from_role_name=s.from_role_name,
                    from_score=s.from_score,
                    to_role_id=role["id"],
                    to_role_name=role.get("name") or "",
                    to_score=m.score,
                    delta=delta,
                    days_dormant=s.days_dormant,
                    recency=round(recency, 4),
                    reactivation_score=composite,
                    matched_skills=list(m.matched_skills),
                    missing_skills=list(m.missing_skills),
                    location_match=m.location_match,
                    seniority_match=bool(m.seniority_match),
                    why=why,
                    stale=stale,
                )
            )
            bucket = min(10, composite // 10)
            histogram[bucket] += 1

    opportunities.sort(key=lambda o: -o.reactivation_score)

    # Per-candidate roll-up.
    per_candidate_map: dict[int, CandidateBest] = {}
    for s in silver:
        prev = per_candidate_map.get(s.candidate_id)
        if not prev:
            per_candidate_map[s.candidate_id] = CandidateBest(silver=s, best=None)
        else:
            if s.passed_at_ms > prev.silver.passed_at_ms:
                prev.silver = s
    for opp in opportunities:
        row = per_candidate_map.get(opp.candidate_id)
        if not row:
            continue
        row.alternatives.append(opp)
        if row.best is None or opp.reactivation_score > row.best.reactivation_score:
            row.best = opp
    per_candidate = sorted(
        per_candidate_map.values(),
        key=lambda r: -(r.best.reactivation_score if r.best else -1),
    )

    # Per-role roll-up.
    per_role_map: dict[str, RoleTopPicks] = {
        r["id"]: RoleTopPicks(role_id=r["id"], role_name=r.get("name") or "", picks=[], best_score=0)
        for r in roles
    }
    for opp in opportunities:
        row = per_role_map.get(opp.to_role_id)
        if not row:
            continue
        row.picks.append(opp)
        if opp.reactivation_score > row.best_score:
            row.best_score = opp.reactivation_score
    per_role = [
        RoleTopPicks(
            role_id=r.role_id,
            role_name=r.role_name,
            picks=r.picks[:PER_ROLE_LIMIT],
            best_score=r.best_score,
        )
        for r in per_role_map.values()
        if r.picks
    ]
    per_role.sort(key=lambda r: -r.best_score)

    revivable = [o for o in opportunities if o.reactivation_score >= REVIVE_COMPOSITE_FLOOR]
    revivable_count = len(revivable)
    distinct_revivable = {o.candidate_id for o in revivable}
    cost_saved = len(distinct_revivable) * SOURCING_COST_PER_HIRE_USD

    return ReviveSummary(
        generated_at=now,
        silver=silver,
        opportunities=opportunities,
        per_candidate=per_candidate,
        per_role=per_role,
        revivable_count=revivable_count,
        estimated_cost_saved_usd=cost_saved,
        top_pick=opportunities[0] if opportunities else None,
        reactivation_histogram=histogram,
    )


# ---------- band + brief (mirrors TS) ----------

def lift_band(revivable: int, silver_count: int) -> dict[str, str]:
    if silver_count == 0:
        return {
            "label": "Empty pool",
            "hex": "#64748b",
            "blurb": "Mark candidates as Passed in any role to start your silver pool.",
        }
    pct = (revivable / max(1, silver_count)) * 100
    if pct >= 50:
        return {
            "label": "High-yield pool",
            "hex": "#10b981",
            "blurb": "More than half of your silver medalists are revivable — work the queue.",
        }
    if pct >= 25:
        return {
            "label": "Healthy pool",
            "hex": "#0ea5e9",
            "blurb": "Solid reactivation opportunities — pick the hot ones first.",
        }
    if pct >= 10:
        return {
            "label": "Niche pool",
            "hex": "#f59e0b",
            "blurb": "A few good fits — most of the pool is dormant for a reason.",
        }
    return {
        "label": "Low-yield pool",
        "hex": "#f43f5e",
        "blurb": "Most silver medalists don't fit the open roles — broaden roles or sourcing.",
    }


def _format_days(days: int) -> str:
    if days <= 0:
        return "today"
    if days == 1:
        return "1 day"
    if days < 60:
        return f"{days} days"
    months = round(days / 30)
    return f"{months} month{'' if months == 1 else 's'}"


def _format_usd(n: int) -> str:
    if n >= 1_000_000:
        return f"${n / 1_000_000:.1f}M"
    if n >= 10_000:
        return f"${round(n / 1000)}k"
    if n >= 1000:
        return f"${n / 1000:.1f}k"
    return f"${n}"


def build_brief(s: ReviveSummary) -> str:
    band = lift_band(s.revivable_count, len(s.silver))
    lines: list[str] = ["# Revive — Silver Medalist Briefing", ""]
    lines.append(f"**Pool:** {len(s.silver)} silver medalists across your roles.")
    plural = "y" if s.revivable_count == 1 else "ies"
    lines.append(
        f"**Revivable:** {s.revivable_count} opportunit{plural} clear the {REVIVE_COMPOSITE_FLOOR} reactivation floor."
    )
    lines.append(f"**Estimated sourcing cost saved:** {_format_usd(s.estimated_cost_saved_usd)}.")
    lines.append(f"**Pool quality:** {band['label']} — {band['blurb']}")
    lines.append("")
    if s.top_pick:
        t = s.top_pick
        lines.append("## Top pick")
        lines.append(
            f"- **{t.candidate_name}** — {t.from_role_name} ({t.from_score}) → "
            f"{t.to_role_name} ({t.to_score}). Reactivation {t.reactivation_score}. "
            f"Passed {_format_days(t.days_dormant)} ago."
        )
        if t.why:
            lines.append(f"  - {t.why[0]}")
        lines.append("")
    if s.per_role:
        lines.append("## By open role")
        for r in s.per_role[:5]:
            top = r.picks[0]
            lines.append(
                f"- **{r.role_name}** — best revive {top.candidate_name} @ "
                f"{top.reactivation_score} (from {top.from_role_name}, "
                f"{_format_days(top.days_dormant)} dormant)."
            )
    return "\n".join(lines)


def summary_to_dict(s: ReviveSummary) -> dict[str, Any]:
    return {
        "generated_at": s.generated_at,
        "silver": [asdict(x) for x in s.silver],
        "opportunities": [asdict(x) for x in s.opportunities],
        "per_candidate": [
            {
                "silver": asdict(c.silver),
                "best": (asdict(c.best) if c.best else None),
                "alternatives": [asdict(a) for a in c.alternatives],
            }
            for c in s.per_candidate
        ],
        "per_role": [
            {
                "role_id": r.role_id,
                "role_name": r.role_name,
                "best_score": r.best_score,
                "picks": [asdict(p) for p in r.picks],
            }
            for r in s.per_role
        ],
        "revivable_count": s.revivable_count,
        "estimated_cost_saved_usd": s.estimated_cost_saved_usd,
        "top_pick": asdict(s.top_pick) if s.top_pick else None,
        "reactivation_histogram": s.reactivation_histogram,
    }
