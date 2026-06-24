"""Cadence Studio — per-candidate pipeline velocity & stage SLA engine.

Byte-for-byte mirror of `frontend/src/lib/cadence.ts`. For every shortlist
entry the engine computes:

  * ``stage_age_days`` — synthesised from the entry+stage hash if no
    explicit ``stage_changed_at`` is supplied (so the surface lights up
    immediately on first open with a realistic spread);
  * a band ``on_track`` / ``slowing`` / ``at_risk`` / ``stalled`` driven by
    the per-stage SLA;
  * ``survive_prob_7d`` via the exponential-hazard model
    ``exp(-7 * ln 2 / median)``;
  * a 0..100 ``risk_score`` (``0.6 * overdue + 0.4 * staleness``);
  * a band-keyed plain-English recommendation.

Roll-ups: per-stage (median/p75 age, band counts, expected exits/7d,
bottleneck flag, 0..100 health), per-role (band breakdown + health), and
a global summary with markdown brief.

Pure stdlib. ``analyze_cadence`` is the single public entrypoint.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

# ---------- constants ----------

BAND_LABEL = {
    "on_track": "On track",
    "slowing": "Slowing",
    "at_risk": "At risk",
    "stalled": "Stalled",
}

CADENCE_BANDS = ["on_track", "slowing", "at_risk", "stalled"]

STAGE_SLA_DAYS = {
    "new": 1,
    "outreach": 3,
    "screening": 5,
    "interview": 7,
    "offer": 5,
    "passed": 30,
}

STAGE_MEDIAN_DAYS = {
    "new": 2,
    "outreach": 4,
    "screening": 5,
    "interview": 7,
    "offer": 4,
    "passed": 30,
}

ACTIVE_STAGES = ["new", "outreach", "screening", "interview", "offer"]

STAGE_LABEL = {
    "new": "New",
    "outreach": "Outreach",
    "screening": "Screening",
    "interview": "Interview",
    "offer": "Offer",
    "passed": "Passed",
}


# ---------- helpers ----------


def _clamp(n: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, n))


def _quantile(sorted_vals: list[float], q: float) -> float:
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return float(sorted_vals[0])
    pos = (len(sorted_vals) - 1) * q
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return float(sorted_vals[lo])
    w = pos - lo
    return float(sorted_vals[lo] * (1 - w) + sorted_vals[hi] * w)


def _empty_bands() -> dict[str, int]:
    return {"on_track": 0, "slowing": 0, "at_risk": 0, "stalled": 0}


def fnv1a_unit(s: str) -> float:
    """FNV-1a 32-bit hash → [0, 1). Matches the TS engine bit-for-bit."""
    h = 0x811C9DC5
    for ch in s:
        h ^= ord(ch)
        h = (h * 0x01000193) & 0xFFFFFFFF
    return h / 0xFFFFFFFF


def synth_stage_age(role_id: str, candidate_id: int, stage: str) -> float:
    """Deterministic synthesised stage age — mirrors the TS shape exactly."""
    u = fnv1a_unit(f"{role_id}|{candidate_id}|{stage}")
    sla = STAGE_SLA_DAYS.get(stage, 5)
    if u < 0.5:
        return round(u * 2 * 0.7 * sla * 10) / 10
    if u < 0.75:
        return round((sla * (0.7 + (u - 0.5) * 4 * 0.3)) * 10) / 10
    if u < 0.92:
        return round((sla * (1.0 + (u - 0.75) * (0.6 / 0.17))) * 10) / 10
    return round((sla * (1.6 + (u - 0.92) * (1.4 / 0.08))) * 10) / 10


# ---------- band + risk ----------


def band_for_age(age_days: float, sla_days: float) -> str:
    sla = max(0.5, sla_days)
    if age_days <= sla * 0.7:
        return "on_track"
    if age_days <= sla:
        return "slowing"
    if age_days <= sla * 1.6:
        return "at_risk"
    return "stalled"


def survival_7d(median_days: float) -> float:
    m = max(0.5, median_days)
    return math.exp((-7 * math.log(2)) / m)


def risk_score(age_days: float, sla_days: float, median_days: float) -> int:
    sla = max(0.5, sla_days)
    m = max(0.5, median_days)
    overdue = _clamp((age_days - sla) / m, 0.0, 1.0)
    staleness = _clamp(age_days / (m * 4), 0.0, 1.0)
    return round(100 * (0.6 * overdue + 0.4 * staleness))


def _recommend(band: str, stage: str, age_days: float, sla_days: float) -> str:
    overdue_days = max(0.0, age_days - sla_days)
    if band == "on_track":
        if stage == "offer":
            return "On track — keep weekly touch warm until decision."
        return f"On track — keep moving ({age_days:.1f}d in {stage})."
    if band == "slowing":
        if stage == "outreach":
            return f"Approaching SLA ({age_days:.1f}/{sla_days}d) — bump the thread today."
        if stage == "screening":
            return "Screening dragging — schedule the call within 48h."
        if stage == "interview":
            return "Interview slot still open — confirm or reschedule today."
        if stage == "offer":
            return "Offer drifting — re-engage and surface the deciding blocker."
        return "Approaching SLA — nudge the next step."
    if band == "at_risk":
        if stage == "outreach":
            return f"{overdue_days:.1f}d past outreach SLA — try the alt channel or close the thread."
        if stage == "screening":
            return f"{overdue_days:.1f}d past screening SLA — escalate or move to a recruiter sync."
        if stage == "interview":
            return f"{overdue_days:.1f}d past interview SLA — panel waiting on whom?"
        if stage == "offer":
            return f"{overdue_days:.1f}d past offer SLA — counter-offer risk rising; call them."
        return f"{overdue_days:.1f}d past SLA — escalate today."
    # stalled
    if stage == "offer":
        return "Stalled offer — assume lost unless contacted today; consider next finalist."
    if stage == "interview":
        return "Stalled in interview — close the loop or pass; the slot is dead weight."
    if stage == "screening":
        return "Stalled screen — drop or hand off; this seat is blocking your funnel."
    if stage == "outreach":
        return "Stalled outreach — try one final channel, then close as no-response."
    return "Stalled — close the loop today."


# ---------- I/O types ----------


@dataclass
class CadenceCandidate:
    candidate_id: int
    candidate_name: str
    role_id: str
    role_name: str
    stage: str
    stage_age_days: float
    pipeline_age_days: float
    match_score: float = 0.0
    location: Optional[str] = None


@dataclass
class CadenceItem:
    candidate_id: int
    candidate_name: str
    role_id: str
    role_name: str
    stage: str
    stage_age_days: float
    pipeline_age_days: float
    match_score: float
    location: Optional[str]
    band: str
    risk_score: int
    survive_prob_7d: float
    days_over_sla: float
    sla_days: int
    recommendation: str

    def as_dict(self) -> dict:
        return {
            "candidateId": self.candidate_id,
            "candidateName": self.candidate_name,
            "roleId": self.role_id,
            "roleName": self.role_name,
            "stage": self.stage,
            "stageAgeDays": self.stage_age_days,
            "pipelineAgeDays": self.pipeline_age_days,
            "matchScore": self.match_score,
            "location": self.location,
            "band": self.band,
            "riskScore": self.risk_score,
            "surviveProb7d": self.survive_prob_7d,
            "daysOverSla": self.days_over_sla,
            "slaDays": self.sla_days,
            "recommendation": self.recommendation,
        }


@dataclass
class StageRollup:
    stage: str
    count: int = 0
    age_median: float = 0.0
    age_p75: float = 0.0
    bands: dict[str, int] = field(default_factory=_empty_bands)
    expected_exits_7d: float = 0.0
    bottleneck: bool = False
    health: int = 100
    sla_days: int = 0
    median_days: int = 0

    def as_dict(self) -> dict:
        return {
            "stage": self.stage,
            "count": self.count,
            "ageMedian": self.age_median,
            "ageP75": self.age_p75,
            "bands": dict(self.bands),
            "expectedExits7d": self.expected_exits_7d,
            "bottleneck": self.bottleneck,
            "health": self.health,
            "slaDays": self.sla_days,
            "medianDays": self.median_days,
        }


@dataclass
class RoleRollup:
    role_id: str
    role_name: str
    count: int = 0
    bands: dict[str, int] = field(default_factory=_empty_bands)
    health: int = 100
    top_stalled: list[CadenceItem] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "roleId": self.role_id,
            "roleName": self.role_name,
            "count": self.count,
            "bands": dict(self.bands),
            "health": self.health,
            "topStalled": [c.as_dict() for c in self.top_stalled],
        }


# ---------- core analyzer ----------


def analyze_cadence(
    candidates: list[CadenceCandidate],
    *,
    horizon_days: int = 7,
    now_ms: Optional[int] = None,
) -> dict:
    """Single entrypoint. Returns a JSON-ready dict matching the TS shape."""
    items: list[CadenceItem] = []
    for c in candidates:
        if c.stage not in ACTIVE_STAGES:
            continue
        sla = STAGE_SLA_DAYS.get(c.stage, 5)
        median = STAGE_MEDIAN_DAYS.get(c.stage, 5)
        band = band_for_age(c.stage_age_days, sla)
        risk = risk_score(c.stage_age_days, sla, median)
        survive = survival_7d(median)
        items.append(
            CadenceItem(
                candidate_id=c.candidate_id,
                candidate_name=c.candidate_name,
                role_id=c.role_id,
                role_name=c.role_name,
                stage=c.stage,
                stage_age_days=c.stage_age_days,
                pipeline_age_days=c.pipeline_age_days,
                match_score=c.match_score,
                location=c.location,
                band=band,
                risk_score=risk,
                survive_prob_7d=survive,
                days_over_sla=max(0.0, c.stage_age_days - sla),
                sla_days=sla,
                recommendation=_recommend(band, c.stage, c.stage_age_days, sla),
            )
        )

    # ---- per-stage ----
    by_stage: list[StageRollup] = []
    for stage in ACTIVE_STAGES:
        in_stage = [i for i in items if i.stage == stage]
        ages = sorted(i.stage_age_days for i in in_stage)
        bands = _empty_bands()
        for i in in_stage:
            bands[i.band] += 1
        expected_exits = sum(1 - i.survive_prob_7d for i in in_stage)
        denom = max(1, len(in_stage))
        health = round(
            100
            * (
                1
                - (
                    0.6 * (bands["stalled"] / denom)
                    + 0.3 * (bands["at_risk"] / denom)
                    + 0.1 * (bands["slowing"] / denom)
                )
            )
        )
        by_stage.append(
            StageRollup(
                stage=stage,
                count=len(in_stage),
                age_median=round(_quantile(ages, 0.5), 1) if ages else 0.0,
                age_p75=round(_quantile(ages, 0.75), 1) if ages else 0.0,
                bands=bands,
                expected_exits_7d=round(expected_exits, 2),
                bottleneck=False,
                health=health,
                sla_days=STAGE_SLA_DAYS[stage],
                median_days=STAGE_MEDIAN_DAYS[stage],
            )
        )

    worst_score = 0
    bottleneck_idx = -1
    for idx, s in enumerate(by_stage):
        stuck = s.bands["at_risk"] + s.bands["stalled"]
        if s.count < 2:
            continue
        if stuck / s.count < 0.25:
            continue
        if stuck > worst_score:
            worst_score = stuck
            bottleneck_idx = idx
    if bottleneck_idx >= 0:
        by_stage[bottleneck_idx].bottleneck = True

    # ---- per-role ----
    role_map: dict[str, RoleRollup] = {}
    for i in items:
        r = role_map.get(i.role_id)
        if r is None:
            r = RoleRollup(role_id=i.role_id, role_name=i.role_name)
            role_map[i.role_id] = r
        r.count += 1
        r.bands[i.band] += 1
    for r in role_map.values():
        denom = max(1, r.count)
        r.health = round(
            100
            * (
                1
                - (
                    0.6 * (r.bands["stalled"] / denom)
                    + 0.3 * (r.bands["at_risk"] / denom)
                    + 0.1 * (r.bands["slowing"] / denom)
                )
            )
        )
        stalled = [
            i
            for i in items
            if i.role_id == r.role_id and i.band in ("at_risk", "stalled")
        ]
        stalled.sort(key=lambda x: x.risk_score, reverse=True)
        r.top_stalled = stalled[:3]
    by_role = sorted(role_map.values(), key=lambda r: r.health)

    # ---- top-level rollups ----
    total_active = len(items)
    on_track_count = sum(1 for i in items if i.band == "on_track")
    at_risk_count = sum(1 for i in items if i.band == "at_risk")
    stalled_count = sum(1 for i in items if i.band == "stalled")
    slowing_count = sum(1 for i in items if i.band == "slowing")
    denom = max(1, total_active)
    health_score = round(
        100
        * (
            1
            - (
                0.6 * (stalled_count / denom)
                + 0.3 * (at_risk_count / denom)
                + 0.1 * (slowing_count / denom)
            )
        )
    )
    expected_exits_7d = round(sum(1 - i.survive_prob_7d for i in items), 2)

    worst_stage: Optional[str] = None
    worst_stage_health = 101
    for s in by_stage:
        if s.count == 0:
            continue
        if s.health < worst_stage_health:
            worst_stage_health = s.health
            worst_stage = s.stage

    worst_role_id: Optional[str] = None
    if by_role and by_role[0].health < 75:
        worst_role_id = by_role[0].role_id

    hot_list = sorted(
        (i for i in items if i.band in ("at_risk", "stalled")),
        key=lambda x: (x.risk_score, x.match_score),
        reverse=True,
    )[:8]

    # ---- recommendations ----
    recs: list[str] = []
    if total_active == 0:
        recs.append("No active candidates — load roles and add a shortlist to see cadence.")
    elif stalled_count == 0 and at_risk_count == 0:
        recs.append(
            f"**Healthy** — all {total_active} active candidates inside SLA. Keep cadence."
        )
    else:
        if stalled_count > 0:
            recs.append(
                f"**{stalled_count} stalled** — close the loop or drop. Each stalled card is a slot blocking real progress."
            )
        if at_risk_count > 0:
            recs.append(
                f"**{at_risk_count} at risk** — these need a nudge today or they roll into stalled by Friday."
            )
        if bottleneck_idx >= 0:
            bn = by_stage[bottleneck_idx]
            recs.append(
                f"**Bottleneck: {STAGE_LABEL[bn.stage]}** — {bn.bands['at_risk'] + bn.bands['stalled']} of {bn.count} candidates past SLA (median age {bn.age_median}d vs SLA {bn.sla_days}d)."
            )
        if worst_role_id:
            r = by_role[0]
            recs.append(
                f"**Worst role: {r.role_name}** — health {r.health}/100 across {r.count} candidates. Recover or descope."
            )
        if hot_list:
            top = hot_list[0]
            recs.append(
                f"**Today's top action:** {top.candidate_name} ({top.role_name}, {STAGE_LABEL[top.stage]}, {top.stage_age_days}d) — {top.recommendation}"
            )

    return {
        "totalActive": total_active,
        "atRiskCount": at_risk_count,
        "stalledCount": stalled_count,
        "onTrackCount": on_track_count,
        "healthScore": health_score,
        "expectedExits7d": expected_exits_7d,
        "worstStage": worst_stage,
        "worstRoleId": worst_role_id,
        "byStage": [s.as_dict() for s in by_stage],
        "byRole": [r.as_dict() for r in by_role],
        "hotList": [h.as_dict() for h in hot_list],
        "items": [i.as_dict() for i in items],
        "recommendations": recs,
        "generatedAt": now_ms if now_ms is not None else 0,
        "horizonDays": horizon_days,
    }


# ---------- markdown brief ----------


def build_cadence_brief(summary: dict, *, iso_date: Optional[str] = None) -> str:
    lines: list[str] = []
    dt = iso_date or "—"
    lines.append(f"# Pipeline Cadence — {dt}")
    lines.append("")
    lines.append(
        f"**Health:** {summary['healthScore']}/100 · "
        f"**Active:** {summary['totalActive']} · "
        f"**At risk:** {summary['atRiskCount']} · "
        f"**Stalled:** {summary['stalledCount']}"
    )
    lines.append(
        f"**Projected exits next 7 days:** {summary['expectedExits7d']:.1f}"
    )
    lines.append("")
    if summary.get("recommendations"):
        lines.append("## Recommendations")
        for r in summary["recommendations"]:
            lines.append(f"- {r}")
        lines.append("")
    hot = summary.get("hotList") or []
    if hot:
        lines.append("## Today's hot list")
        lines.append("| Candidate | Role | Stage | Age | Band | Action |")
        lines.append("|---|---|---|---:|---|---|")
        for h in hot:
            lines.append(
                f"| {h['candidateName']} | {h['roleName']} | "
                f"{STAGE_LABEL[h['stage']]} | {h['stageAgeDays']}d | "
                f"{BAND_LABEL[h['band']]} | {h['recommendation']} |"
            )
        lines.append("")
    by_stage = summary.get("byStage") or []
    if any(s["count"] > 0 for s in by_stage):
        lines.append("## Stage health")
        lines.append("| Stage | Count | Median age | SLA | At risk | Stalled | Health |")
        lines.append("|---|---:|---:|---:|---:|---:|---:|")
        for st in by_stage:
            if st["count"] == 0:
                continue
            flag = " ⚠️" if st["bottleneck"] else ""
            lines.append(
                f"| {STAGE_LABEL[st['stage']]}{flag} | {st['count']} | "
                f"{st['ageMedian']}d | {st['slaDays']}d | "
                f"{st['bands']['at_risk']} | {st['bands']['stalled']} | "
                f"{st['health']} |"
            )
        lines.append("")
    by_role = summary.get("byRole") or []
    if by_role:
        lines.append("## Role health")
        lines.append("| Role | Active | On track | At risk | Stalled | Health |")
        lines.append("|---|---:|---:|---:|---:|---:|")
        for r in by_role:
            lines.append(
                f"| {r['roleName']} | {r['count']} | "
                f"{r['bands']['on_track']} | {r['bands']['at_risk']} | "
                f"{r['bands']['stalled']} | {r['health']} |"
            )
        lines.append("")
    return "\n".join(lines)
