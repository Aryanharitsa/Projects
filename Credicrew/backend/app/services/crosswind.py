"""Crosswind — Cross-Role Candidate Router (Python mirror).

Same physics, same thresholds, same outputs as
``frontend/src/lib/crosswind.ts`` so a backend client (or an agent calling
``POST /crosswind/summary``) gets byte-identical routing recommendations
for the same fixture.

Inputs
------
* ``roles`` — list of role dicts with ``id``, ``name``, ``plan`` (text)
  and a ``shortlist`` of ``{candidate_id, status, added_at?,
  stage_changed_at?}`` entries.
* ``candidates`` — list of candidate dicts ``{id, name, tags, keywords,
  role, location, headline}`` — same shape the frontend's
  ``candidates.ts`` exports.

Outputs
-------
A summary dataclass-as-dict mirroring the TS ``CrosswindSummary``:
``cells``, ``moves``, ``magnets``, ``lonely``, ``per_role``,
``score_histogram``, plus the portfolio rollup totals.
"""
from __future__ import annotations

import statistics
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable

from app.services.match import MatchResult, match_candidate, plan_query

STRONG_FLOOR = 80
SOLID_FLOOR = 60
MISPLACE_THRESHOLD = 10
MAGNET_ROLES = 3
TRANSPLANT_FLOOR = 70

FROZEN_STATUSES = frozenset({"passed", "offer"})


@dataclass
class CrosswindCell:
    candidate_id: int
    candidate_name: str
    role_id: str
    role_name: str
    is_home: bool
    is_on_shortlist: bool
    status: str | None
    score: int
    matched: list[str]
    missing: list[str]
    location_state: str
    seniority_match: bool


@dataclass
class RoutingMove:
    candidate_id: int
    candidate_name: str
    from_role_id: str
    from_role_name: str
    from_score: int
    to_role_id: str
    to_role_name: str
    to_score: int
    delta: int
    why: list[str] = field(default_factory=list)
    status: str | None = None


@dataclass
class MagnetHit:
    role_id: str
    role_name: str
    score: int
    is_home: bool


@dataclass
class TalentMagnet:
    candidate_id: int
    candidate_name: str
    home_role_id: str | None
    home_role_name: str | None
    hits: list[MagnetHit] = field(default_factory=list)
    top_score: int = 0


@dataclass
class LonelyTransplant:
    candidate_id: int
    candidate_name: str
    from_role_id: str
    from_role_name: str
    score: int
    delta: int
    status: str | None = None


@dataclass
class LonelyRole:
    role_id: str
    role_name: str
    own_best: int
    own_median: int
    candidate_count: int
    transplants: list[LonelyTransplant] = field(default_factory=list)


@dataclass
class PerRoleRollup:
    role_id: str
    role_name: str
    candidate_count: int
    best: int
    median: int
    is_target: bool
    is_source: bool
    crowded_rank: int | None = None


@dataclass
class CrosswindSummary:
    generated_at: int
    role_count: int
    candidate_count: int
    cell_count: int
    cells: list[CrosswindCell]
    current_total: int
    optimal_total: int
    lift_total: int
    lift_avg_per_move: int
    moves: list[RoutingMove]
    magnets: list[TalentMagnet]
    lonely: list[LonelyRole]
    per_role: list[PerRoleRollup]
    score_histogram: list[int]


def _median(xs: list[int]) -> int:
    if not xs:
        return 0
    return round(statistics.median(xs))


def _diff_why(home: MatchResult, target: MatchResult, from_role_name: str, to_role_name: str) -> list[str]:
    lines: list[str] = []

    skills_gained = [s for s in target.matched_skills if s not in home.matched_skills]
    skills_lost = [s for s in home.matched_skills if s not in target.matched_skills]
    if skills_gained or skills_lost:
        parts: list[str] = []
        if skills_gained:
            shown = ", ".join(skills_gained[:3])
            parts.append(f"+{len(skills_gained)} matched skill{'' if len(skills_gained) == 1 else 's'} ({shown})")
        if skills_lost:
            shown = ", ".join(skills_lost[:2])
            parts.append(f"−{len(skills_lost)} ({shown})")
        lines.append(", ".join(parts))

    if home.location_match != target.location_match:
        lines.append(f"Location {home.location_match} → {target.location_match}")

    if home.seniority_match != target.seniority_match:
        arrow = "mismatch → match" if target.seniority_match else "match → mismatch"
        lines.append(f"Seniority {arrow}")

    if not lines:
        lines.append(f"Higher composite fit for {to_role_name} than {from_role_name}.")
    return lines


def _resolve_plan(role: dict[str, Any]):
    """Accept either a ready ``plan`` dict/QueryPlan or a free-text ``jd`` /
    ``plan_text`` field. Same as the TS surface which expects ``role.plan``
    already to be a ``QueryPlan`` (so this matches when both sides
    pre-plan)."""
    plan = role.get("plan")
    if isinstance(plan, dict):
        return plan_query(plan.get("text") or "") if "text" in plan and not plan.get("skills") else _from_dict_plan(plan)
    if isinstance(plan, str):
        return plan_query(plan)
    jd = role.get("jd") or role.get("plan_text") or role.get("text") or ""
    return plan_query(jd)


def _from_dict_plan(d: dict[str, Any]):
    from app.services.match import QueryPlan
    return QueryPlan(
        text=d.get("text") or "",
        skills=list(d.get("skills") or []),
        location=d.get("location"),
        seniority=d.get("seniority"),
    )


def analyze_crosswind(
    roles: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    *,
    now_ms: int | None = None,
) -> CrosswindSummary:
    candidate_by_id: dict[int, dict[str, Any]] = {int(c["id"]): c for c in candidates if "id" in c}

    # active_placements
    placements: dict[int, dict[str, Any]] = {}
    for role in roles:
        rid = str(role.get("id") or "")
        for e in (role.get("shortlist") or []):
            status = str(e.get("status") or "")
            if status in FROZEN_STATUSES:
                continue
            cid = int(e.get("candidate_id") or e.get("candidateId") or 0)
            if cid <= 0 or cid not in candidate_by_id:
                continue
            ts = float(
                e.get("stage_changed_at")
                or e.get("stageChangedAt")
                or e.get("added_at")
                or e.get("addedAt")
                or 0
            )
            prev = placements.get(cid)
            if prev is None or ts > prev["ts"]:
                placements[cid] = {
                    "candidate_id": cid,
                    "candidate_name": candidate_by_id[cid].get("name") or f"Candidate {cid}",
                    "candidate": candidate_by_id[cid],
                    "home_role_id": rid,
                    "status": status,
                    "ts": ts,
                }

    # Pre-compute shortlist membership.
    shortlist_of: dict[str, dict[int, dict[str, Any]]] = {}
    for role in roles:
        rid = str(role.get("id") or "")
        m: dict[int, dict[str, Any]] = {}
        for e in (role.get("shortlist") or []):
            cid = int(e.get("candidate_id") or e.get("candidateId") or 0)
            if cid > 0:
                m[cid] = {"status": e.get("status"), **e}
        shortlist_of[rid] = m

    # Pre-resolve plans once.
    role_plans = {str(role.get("id") or ""): _resolve_plan(role) for role in roles}

    cells: list[CrosswindCell] = []
    matches_by_candidate: dict[int, dict[str, MatchResult]] = {}

    for cid, p in placements.items():
        row: dict[str, MatchResult] = {}
        for role in roles:
            rid = str(role.get("id") or "")
            m = match_candidate(role_plans[rid], p["candidate"])
            row[rid] = m
            entry = shortlist_of.get(rid, {}).get(cid)
            cells.append(CrosswindCell(
                candidate_id=cid,
                candidate_name=p["candidate_name"],
                role_id=rid,
                role_name=role.get("name") or "Role",
                is_home=(rid == p["home_role_id"]),
                is_on_shortlist=entry is not None,
                status=(entry.get("status") if entry else None),
                score=m.score,
                matched=list(m.matched_skills),
                missing=list(m.missing_skills),
                location_state=m.location_match,
                seniority_match=m.seniority_match,
            ))
        matches_by_candidate[cid] = row

    role_by_id = {str(r.get("id") or ""): r for r in roles}

    moves: list[RoutingMove] = []
    current_total = 0
    optimal_total = 0
    for cid, p in placements.items():
        row = matches_by_candidate.get(cid)
        if not row:
            continue
        home_m = row.get(p["home_role_id"])
        if home_m is None:
            continue
        current_total += home_m.score

        best_rid = p["home_role_id"]
        best_m = home_m
        for role in roles:
            rid = str(role.get("id") or "")
            if rid == p["home_role_id"]:
                continue
            if shortlist_of.get(rid, {}).get(cid) is not None:
                continue
            cand_m = row.get(rid)
            if cand_m is None:
                continue
            if cand_m.score > best_m.score:
                best_m = cand_m
                best_rid = rid
        optimal_total += best_m.score

        delta = best_m.score - home_m.score
        if delta >= MISPLACE_THRESHOLD and best_rid != p["home_role_id"]:
            from_role = role_by_id.get(p["home_role_id"], {})
            to_role = role_by_id.get(best_rid, {})
            moves.append(RoutingMove(
                candidate_id=cid,
                candidate_name=p["candidate_name"],
                from_role_id=p["home_role_id"],
                from_role_name=from_role.get("name") or "Role",
                from_score=home_m.score,
                to_role_id=best_rid,
                to_role_name=to_role.get("name") or "Role",
                to_score=best_m.score,
                delta=delta,
                why=_diff_why(home_m, best_m, from_role.get("name") or "", to_role.get("name") or ""),
                status=p["status"],
            ))
    moves.sort(key=lambda m: -m.delta)

    # Magnets
    magnets: list[TalentMagnet] = []
    for cid, p in placements.items():
        row = matches_by_candidate.get(cid)
        if not row:
            continue
        hits: list[MagnetHit] = []
        for role in roles:
            rid = str(role.get("id") or "")
            m = row.get(rid)
            if m is None or m.score < STRONG_FLOOR:
                continue
            hits.append(MagnetHit(
                role_id=rid,
                role_name=role.get("name") or "Role",
                score=m.score,
                is_home=(rid == p["home_role_id"]),
            ))
        hits.sort(key=lambda h: -h.score)
        if len(hits) >= MAGNET_ROLES:
            home_role = role_by_id.get(p["home_role_id"], {})
            magnets.append(TalentMagnet(
                candidate_id=cid,
                candidate_name=p["candidate_name"],
                home_role_id=p["home_role_id"] or None,
                home_role_name=home_role.get("name"),
                hits=hits,
                top_score=hits[0].score if hits else 0,
            ))
    magnets.sort(key=lambda t: (-len(t.hits), -t.top_score))

    # Lonely roles
    lonely: list[LonelyRole] = []
    for role in roles:
        rid = str(role.get("id") or "")
        own_scores: list[int] = []
        for e in (role.get("shortlist") or []):
            status = str(e.get("status") or "")
            if status in FROZEN_STATUSES:
                continue
            cid = int(e.get("candidate_id") or e.get("candidateId") or 0)
            if cid <= 0 or cid not in candidate_by_id:
                continue
            own_scores.append(match_candidate(role_plans[rid], candidate_by_id[cid]).score)
        own_best = max(own_scores) if own_scores else 0
        own_median = _median(own_scores)
        if own_best >= STRONG_FLOOR:
            continue

        transplants: list[LonelyTransplant] = []
        for cid, p in placements.items():
            if p["home_role_id"] == rid:
                continue
            if shortlist_of.get(rid, {}).get(cid) is not None:
                continue
            row = matches_by_candidate.get(cid)
            if not row:
                continue
            score = row.get(rid, MatchResult(score=0)).score
            if score < TRANSPLANT_FLOOR:
                continue
            home_m = row.get(p["home_role_id"])
            home_score = home_m.score if home_m else 0
            delta = score - home_score
            if delta < -5:
                continue
            from_role = role_by_id.get(p["home_role_id"], {})
            transplants.append(LonelyTransplant(
                candidate_id=cid,
                candidate_name=p["candidate_name"],
                from_role_id=p["home_role_id"],
                from_role_name=from_role.get("name") or "Role",
                score=score,
                delta=delta,
                status=p["status"],
            ))
        if not transplants:
            continue
        transplants.sort(key=lambda t: -t.score)
        lonely.append(LonelyRole(
            role_id=rid,
            role_name=role.get("name") or "Role",
            own_best=own_best,
            own_median=own_median,
            candidate_count=len(own_scores),
            transplants=transplants[:5],
        ))
    lonely.sort(key=lambda l: l.own_best)

    # Per-role rollup.
    target_set = {m.to_role_id for m in moves}
    source_set = {m.from_role_id for m in moves}
    per_role: list[PerRoleRollup] = []
    for role in roles:
        rid = str(role.get("id") or "")
        scores: list[int] = []
        for e in (role.get("shortlist") or []):
            status = str(e.get("status") or "")
            if status in FROZEN_STATUSES:
                continue
            cid = int(e.get("candidate_id") or e.get("candidateId") or 0)
            if cid <= 0 or cid not in candidate_by_id:
                continue
            scores.append(match_candidate(role_plans[rid], candidate_by_id[cid]).score)
        per_role.append(PerRoleRollup(
            role_id=rid,
            role_name=role.get("name") or "Role",
            candidate_count=len(scores),
            best=max(scores) if scores else 0,
            median=_median(scores),
            is_target=rid in target_set,
            is_source=rid in source_set,
        ))
    ranked = sorted(per_role, key=lambda r: -r.best)
    for i, r in enumerate(ranked):
        for p in per_role:
            if p.role_id == r.role_id:
                p.crowded_rank = i + 1
                break

    histogram = [0] * 10
    for c in cells:
        bucket = min(9, c.score // 10)
        histogram[bucket] += 1

    move_count = len(moves)
    lift_total = optimal_total - current_total
    return CrosswindSummary(
        generated_at=now_ms if now_ms is not None else int(time.time() * 1000),
        role_count=len(roles),
        candidate_count=len(placements),
        cell_count=len(cells),
        cells=cells,
        current_total=current_total,
        optimal_total=optimal_total,
        lift_total=lift_total,
        lift_avg_per_move=(lift_total // move_count) if move_count else 0,
        moves=moves,
        magnets=magnets,
        lonely=lonely,
        per_role=per_role,
        score_histogram=histogram,
    )


def summary_to_dict(s: CrosswindSummary) -> dict[str, Any]:
    return asdict(s)


def lift_band(lift_total: int, move_count: int) -> str:
    if move_count == 0:
        return "idle"
    if lift_total >= 60 or move_count >= 5:
        return "urgent"
    if lift_total >= 25 or move_count >= 3:
        return "meaningful"
    return "modest"


def build_brief(s: CrosswindSummary) -> str:
    """Markdown brief — mirrors the frontend's ``buildBrief()`` output."""
    lines: list[str] = []
    lines.append(f"# Crosswind — {time.strftime('%Y-%m-%d', time.gmtime(s.generated_at / 1000))}")
    lines.append("")
    lines.append(
        f"**Portfolio lift:** +{s.lift_total} pts across {len(s.moves)} routing move"
        f"{'' if len(s.moves) == 1 else 's'}."
    )
    lines.append(f"**Active candidates:** {s.candidate_count} across {s.role_count} roles.")
    lines.append("")
    lines.append("## Routing moves")
    if not s.moves:
        lines.append("_None._")
    else:
        for m in s.moves:
            lines.append(
                f"- {m.candidate_name}: {m.from_role_name} ({m.from_score}) → "
                f"{m.to_role_name} ({m.to_score}) **+{m.delta}** — {'; '.join(m.why)}"
            )
    lines.append("")
    lines.append(f"## Talent magnets (≥ {MAGNET_ROLES} roles at ≥{STRONG_FLOOR})")
    if not s.magnets:
        lines.append("_None._")
    else:
        for t in s.magnets:
            hit_strs = ", ".join(f"{h.role_name}({h.score})" for h in t.hits)
            lines.append(f"- **{t.candidate_name}** — {len(t.hits)} roles: {hit_strs}")
    lines.append("")
    lines.append("## Lonely roles")
    if not s.lonely:
        lines.append("_None._")
    else:
        for l in s.lonely:
            top = l.transplants[0]
            lines.append(
                f"- **{l.role_name}** (best own {l.own_best}) — top transplant: "
                f"{top.candidate_name} from {top.from_role_name} at {top.score}"
            )
    return "\n".join(lines)
