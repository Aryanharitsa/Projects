"""Anchor — Candidate Momentum & Drop-Off Risk Radar (Day 92).

Python mirror of `frontend/src/lib/anchor.ts`. Every physics constant here
is duplicated in the TS module so the API and the browser produce
byte-identical summaries.

Every other Credicrew surface answers "who should I hire?" — Match ranks
fit, Decision aggregates the loop, Offer benchmarks comp, Peer Parity
audits fairness, Compass rolls the whole shop up. Nothing answers the
question every recruiter opens their inbox with on a Tuesday morning:
*which of the people already in my pipeline are about to ghost me, and
what should I do about it in the next hour?*

Anchor puts a radar on it. Given each active candidate + their pipeline
state + a signal packet (recency, cadence, reschedules, sentiment,
competing pipelines), it computes:

  · a 0..100 momentum score and its inverse risk (higher = about to ghost)
  · a Bayesian ghost probability anchored on a stage-conditioned prior
  · a half-life in days — how long until untouched momentum decays past
    the recoverable threshold
  · 3–5 driver chips — the ranked signals dragging risk up
  · a recovery tier (hold · ping · reengage · exec · release) with a
    copy-paste nudge script keyed on (tier, top driver)
  · a salvage value — how much loss you avoid by intervening now
    (weighted by role fit × interview composite × offer exposure)

No LLM, no I/O. Same input bytes → same output bytes.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Literal, Optional


# ─────────────────────── physics constants ────────────────────────

RECENCY_ZERO_DAYS = 12
CADENCE_ZERO_HOURS = 50
RESCHEDULE_PENALTY = 15
NO_SHOW_PENALTY = 30
RELIABILITY_FLOOR = 20
COMPETING_PENALTY = 25
EXTERNAL_OFFER_RISK_BUMP = 15
RISK_CEILING = 98

STAGE_BUDGET_DAYS: dict[str, int] = {
    "new": 4,
    "outreach": 6,
    "screening": 8,
    "interview": 10,
    "offer": 7,
    "passed": 99,
}

PACE_DECAY_PER_DAY = 6

AXIS_WEIGHTS: dict[str, float] = {
    "recency": 0.25,
    "cadence": 0.20,
    "reliability": 0.15,
    "pace": 0.20,
    "sentiment": 0.10,
    "competing": 0.10,
}

TIER_THRESHOLDS: dict[str, int] = {
    "ping": 25,
    "reengage": 45,
    "exec": 65,
    "release": 82,
}

RECOVER_FLOOR = 30

STAGE_GHOST_PRIOR: dict[str, float] = {
    "new": 0.35,
    "outreach": 0.30,
    "screening": 0.22,
    "interview": 0.15,
    "offer": 0.10,
    "passed": 0.00,
}

RISK_LOGIT_GAIN = 20
PRE_OFFER_SUNK_COST = 250

# ─────────────────────── taxonomy ────────────────────────

Tier = Literal["hold", "ping", "reengage", "exec", "release"]
TIER_ORDER: tuple[Tier, ...] = ("hold", "ping", "reengage", "exec", "release")

TIER_LABEL: dict[Tier, str] = {
    "hold": "Hold pattern",
    "ping": "Soft ping",
    "reengage": "Warm re-engage",
    "exec": "Executive touch",
    "release": "Concede & release",
}

TIER_BLURB: dict[Tier, str] = {
    "hold": "No action — the candidate is engaged, save the interruption.",
    "ping": "Light nudge — reconfirm next step, ask for a slot, close the loop.",
    "reengage": "Recruiter call — reset expectations, hear the objection, commit to a date.",
    "exec": "Hiring manager or engineering leader personally reaches out — you're asking a question only they can answer.",
    "release": "Send a graceful close; drop into Revive for a future role.",
}

TIER_HEX: dict[Tier, str] = {
    "hold": "#10b981",
    "ping": "#38bdf8",
    "reengage": "#f59e0b",
    "exec": "#fb7185",
    "release": "#94a3b8",
}

TIER_TONE: dict[Tier, str] = {
    "hold": "emerald",
    "ping": "sky",
    "reengage": "amber",
    "exec": "rose",
    "release": "slate",
}

Driver = Literal[
    "recency", "cadence", "reliability", "pace",
    "sentiment", "competing", "external_offer", "no_show",
]

DRIVER_LABEL: dict[Driver, str] = {
    "recency": "Silence",
    "cadence": "Reply latency",
    "reliability": "Reschedules",
    "pace": "Stage age",
    "sentiment": "Cool tone",
    "competing": "Competing pipelines",
    "external_offer": "Confirmed outside offer",
    "no_show": "Recent no-show",
}

DRIVER_HEX: dict[Driver, str] = {
    "recency": "#f472b6",
    "cadence": "#f59e0b",
    "reliability": "#fb7185",
    "pace": "#a78bfa",
    "sentiment": "#facc15",
    "competing": "#22d3ee",
    "external_offer": "#f43f5e",
    "no_show": "#ef4444",
}

Axis = Literal["recency", "cadence", "reliability", "pace", "sentiment", "competing"]
AXES: tuple[Axis, ...] = ("recency", "cadence", "reliability", "pace", "sentiment", "competing")

AXIS_LABEL: dict[Axis, str] = {
    "recency": "Recency",
    "cadence": "Reply cadence",
    "reliability": "Reliability",
    "pace": "Stage pace",
    "sentiment": "Sentiment",
    "competing": "Competing offers",
}


# ─────────────────────── I/O dataclasses ────────────────────────

SentimentTone = Literal["warm", "neutral", "cool"]
TouchDirection = Literal["in", "out"]


@dataclass
class Signals:
    days_since_last_touch: float = 0.0
    last_touch_direction: TouchDirection = "out"
    response_latency_hours: float = 6.0
    reschedule_count: int = 0
    no_show: bool = False
    days_in_stage: float = 0.0
    competing_pipelines: int = 0
    sentiment_tone: SentimentTone = "neutral"
    external_offer: bool = False
    note_keyphrase: Optional[str] = None


@dataclass
class CandidateInput:
    candidate_id: int
    candidate_name: str
    role_id: str
    role_name: str
    status: str
    added_at: int
    match_score: float = 0.0
    composite_score: Optional[float] = None
    candidate_title: Optional[str] = None
    candidate_location: Optional[str] = None
    role_seniority: Optional[str] = None
    stage_changed_at: Optional[int] = None
    offer_value_annual: Optional[float] = None
    signals: Optional[Signals] = None


@dataclass
class DriverEntry:
    driver: Driver
    label: str
    detail: str
    contribution: float


@dataclass
class Script:
    headline: str
    body: str
    channel: Literal["email", "inmail", "sms", "call"]
    minutes: int


@dataclass
class CandidateScore:
    candidate_id: int
    candidate_name: str
    role_id: str
    role_name: str
    status: str
    axes: dict[str, float]
    momentum: float
    risk: float
    tier: Tier
    ghost_probability: float
    half_life_days: int
    care: float
    salvage_value: float
    exposure_annual: float
    drivers: list[DriverEntry]
    script: Script
    signals: Signals
    note_keyphrase: Optional[str] = None
    candidate_title: Optional[str] = None


@dataclass
class StageBreakdown:
    status: str
    count: int
    at_risk: int
    critical: int
    mean_risk: float


@dataclass
class AnchorSummary:
    generated_at: int
    totals: dict[str, Any]
    scores: list[CandidateScore]
    salvage_queue: list[CandidateScore]
    critical_queue: list[CandidateScore]
    by_stage: list[StageBreakdown]
    driver_histogram: list[dict[str, Any]]
    tier_mix: dict[str, int]
    mean_momentum: Optional[float]
    mean_risk: Optional[float]
    notes: list[str]


# ─────────────────────── math helpers ────────────────────────


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _round(v: float) -> int:
    return int(round(v))


def _safe_mean(xs: list[float]) -> Optional[float]:
    ys = [x for x in xs if math.isfinite(x)]
    if not ys:
        return None
    return sum(ys) / len(ys)


def _sigmoid(z: float) -> float:
    if z >= 0:
        e = math.exp(-z)
        return 1.0 / (1.0 + e)
    e = math.exp(z)
    return e / (1.0 + e)


def _logit(p: float) -> float:
    q = _clamp(p, 1e-6, 1 - 1e-6)
    return math.log(q / (1 - q))


# ─────────────────────── per-axis scorers ────────────────────────


def _recency_axis(s: Signals) -> float:
    raw = 100 - (s.days_since_last_touch / RECENCY_ZERO_DAYS) * 100
    inbound_boost = 8 if s.last_touch_direction == "in" else 0
    return _clamp(raw + inbound_boost, 0, 100)


def _cadence_axis(s: Signals) -> float:
    raw = 100 - (s.response_latency_hours / CADENCE_ZERO_HOURS) * 100
    return _clamp(raw, 0, 100)


def _reliability_axis(s: Signals) -> float:
    penalty = s.reschedule_count * RESCHEDULE_PENALTY + (NO_SHOW_PENALTY if s.no_show else 0)
    return _clamp(100 - penalty, RELIABILITY_FLOOR, 100)


def _pace_axis(s: Signals, status: str) -> float:
    budget = STAGE_BUDGET_DAYS.get(status, 8)
    over = max(0, s.days_in_stage - budget)
    return _clamp(100 - over * PACE_DECAY_PER_DAY, 0, 100)


def _sentiment_axis(s: Signals) -> float:
    if s.sentiment_tone == "warm":
        return 90.0
    if s.sentiment_tone == "cool":
        return 30.0
    return 60.0


def _competing_axis(s: Signals) -> float:
    n = _clamp(s.competing_pipelines, 0, 3)
    return _clamp(100 - n * COMPETING_PENALTY, 0, 100)


# ─────────────────────── momentum / risk / tier ────────────────────────


def _momentum_from_axes(axes: dict[str, float]) -> float:
    w = AXIS_WEIGHTS
    return (
        axes["recency"] * w["recency"]
        + axes["cadence"] * w["cadence"]
        + axes["reliability"] * w["reliability"]
        + axes["pace"] * w["pace"]
        + axes["sentiment"] * w["sentiment"]
        + axes["competing"] * w["competing"]
    )


def _risk_from_momentum(momentum: float, s: Signals) -> float:
    r = 100 - momentum
    if s.external_offer:
        r += EXTERNAL_OFFER_RISK_BUMP
    return _clamp(r, 0, RISK_CEILING)


def tier_from_risk(risk: float) -> Tier:
    if risk >= TIER_THRESHOLDS["release"]:
        return "release"
    if risk >= TIER_THRESHOLDS["exec"]:
        return "exec"
    if risk >= TIER_THRESHOLDS["reengage"]:
        return "reengage"
    if risk >= TIER_THRESHOLDS["ping"]:
        return "ping"
    return "hold"


def _ghost_probability(risk: float, status: str) -> float:
    prior = STAGE_GHOST_PRIOR.get(status, 0.20)
    shift = (risk - 50) / RISK_LOGIT_GAIN
    return _clamp(_sigmoid(_logit(prior) + shift), 0, 0.99)


def _half_life_days(momentum: float, care: float) -> int:
    above = max(1.0, momentum - RECOVER_FLOOR)
    decay_per_day = 3.0 + (1 - _clamp(care, 0, 1)) * 3.0
    return max(1, _round(above / decay_per_day))


# ─────────────────────── driver harvest ────────────────────────

_DRIVER_MIN_CONTRIBUTION = 6.0


def _harvest_drivers(axes: dict[str, float], s: Signals, status: str) -> list[DriverEntry]:
    w = AXIS_WEIGHTS
    out: list[DriverEntry] = []

    def contrib(axis_score: float, weight: float) -> float:
        return (100 - axis_score) * weight

    c = {
        "recency":     contrib(axes["recency"], w["recency"]),
        "cadence":     contrib(axes["cadence"], w["cadence"]),
        "reliability": contrib(axes["reliability"], w["reliability"]),
        "pace":        contrib(axes["pace"], w["pace"]),
        "sentiment":   contrib(axes["sentiment"], w["sentiment"]),
        "competing":   contrib(axes["competing"], w["competing"]),
    }

    if c["recency"] >= _DRIVER_MIN_CONTRIBUTION:
        d = _round(s.days_since_last_touch)
        who = "they replied last" if s.last_touch_direction == "in" else "we messaged last"
        plural = "" if d == 1 else "s"
        out.append(DriverEntry(
            driver="recency",
            label=DRIVER_LABEL["recency"],
            detail=f"{d} day{plural} since last touch ({who}).",
            contribution=round(c["recency"], 2),
        ))
    if c["cadence"] >= _DRIVER_MIN_CONTRIBUTION:
        h = _round(s.response_latency_hours)
        out.append(DriverEntry(
            driver="cadence",
            label=DRIVER_LABEL["cadence"],
            detail=f"Median reply latency {h}h — slowing vs pipeline baseline.",
            contribution=round(c["cadence"], 2),
        ))
    if c["reliability"] >= _DRIVER_MIN_CONTRIBUTION:
        parts: list[str] = []
        if s.reschedule_count > 0:
            plural = "" if s.reschedule_count == 1 else "s"
            parts.append(f"{s.reschedule_count} reschedule{plural}")
        if s.no_show:
            parts.append("one no-show")
        detail = ". ".join(parts) + "." if parts else "Calendar drift on last two rounds."
        driver: Driver = "no_show" if s.no_show else "reliability"
        out.append(DriverEntry(
            driver=driver,
            label=DRIVER_LABEL[driver],
            detail=" · ".join(parts) + "." if parts else "Calendar drift on last two rounds.",
            contribution=round(c["reliability"], 2),
        ))
    if c["pace"] >= _DRIVER_MIN_CONTRIBUTION:
        budget = STAGE_BUDGET_DAYS.get(status, 8)
        over = max(0, _round(s.days_in_stage - budget))
        out.append(DriverEntry(
            driver="pace",
            label=DRIVER_LABEL["pace"],
            detail=f"{_round(s.days_in_stage)}d in {status} · {over}d over the {budget}d stage budget.",
            contribution=round(c["pace"], 2),
        ))
    if c["sentiment"] >= _DRIVER_MIN_CONTRIBUTION and s.sentiment_tone == "cool":
        detail = (
            f'Last note tone reads cool — "{s.note_keyphrase}".'
            if s.note_keyphrase else "Last note tone reads cool."
        )
        out.append(DriverEntry(
            driver="sentiment",
            label=DRIVER_LABEL["sentiment"],
            detail=detail,
            contribution=round(c["sentiment"], 2),
        ))
    if c["competing"] >= _DRIVER_MIN_CONTRIBUTION:
        plural = "" if s.competing_pipelines == 1 else "es"
        out.append(DriverEntry(
            driver="competing",
            label=DRIVER_LABEL["competing"],
            detail=f"{s.competing_pipelines} concurrent process{plural} mentioned.",
            contribution=round(c["competing"], 2),
        ))
    if s.external_offer:
        out.append(DriverEntry(
            driver="external_offer",
            label=DRIVER_LABEL["external_offer"],
            detail="Outside offer confirmed — competing deadline is live.",
            contribution=float(EXTERNAL_OFFER_RISK_BUMP),
        ))

    out.sort(key=lambda d: d.contribution, reverse=True)
    return out[:5]


# ─────────────────────── script composer ────────────────────────


def _seniority_greeting(name: str, seniority: Optional[str]) -> str:
    first = (name or "there").split(" ")[0]
    if not seniority:
        return f"Hi {first},"
    if seniority.lower() in {"staff", "principal", "lead"}:
        return f"Hi {first},"
    return f"Hey {first},"


def compose_script(c: CandidateInput, tier: Tier, top_driver: Optional[Driver]) -> Script:
    greeting = _seniority_greeting(c.candidate_name, c.role_seniority)
    role = c.role_name or "the role"
    stage = c.status

    if tier == "hold":
        return Script(
            headline="Hold — no message needed",
            body="Momentum is healthy. Log the current touchpoint and revisit if signals shift.",
            channel="email",
            minutes=0,
        )

    slot = "this week or early next"

    if tier == "ping":
        if top_driver == "recency":
            body = (
                f"{greeting}\n\nQuick nudge on {role} — wanted to close the loop on next steps. "
                f"Are you free for a 20-min slot {slot}? Happy to share the interviewer background beforehand.\n\n— Aryan"
            )
        elif top_driver == "pace":
            body = (
                f"{greeting}\n\nWe've been holding your {role} slot at {stage}. "
                f"Wanted to make sure the timing still works — do you have 15 minutes {slot} to lock the next round?\n\n— Aryan"
            )
        else:
            body = (
                f"{greeting}\n\nCircling back on {role}. "
                f"Where are you on your side — worth a quick 15 minute sync {slot} to answer any open questions?\n\n— Aryan"
            )
        return Script(headline=f"Soft ping on {role}", body=body, channel="email", minutes=5)

    if tier == "reengage":
        if top_driver == "competing":
            body = (
                f"{greeting}\n\nWant to be direct — we know you're weighing options and don't want to lose the conversation. "
                f"Can I get 25 minutes with you {slot}? Would love to hear where {role} sits versus the other processes, "
                f"and share what we can commit to on our end.\n\n— Aryan"
            )
        elif top_driver == "sentiment":
            body = (
                f"{greeting}\n\nLast note read a bit cool and I want to make sure we haven't dropped something on our end. "
                f"Have 20 minutes {slot} to talk through what would make {role} more compelling? No pitch — just listening.\n\n— Aryan"
            )
        else:
            body = (
                f"{greeting}\n\nWant to reset expectations on {role}. "
                f"Can I pull you in for a 25 min recruiter sync {slot}? "
                f"Want to hear your timeline and commit to a decision date so nothing drifts.\n\n— Aryan"
            )
        return Script(headline=f"Warm re-engage — {role}", body=body, channel="call", minutes=25)

    if tier == "exec":
        if top_driver == "external_offer":
            body = (
                f"{greeting}\n\nHeard you have an offer in hand. "
                f"Before you sign, would you give our hiring manager 30 minutes {slot}? "
                f"They want to hear what would make the difference, and we're willing to move fast on comp and start date to keep you in the conversation.\n\n— Aryan"
            )
        elif top_driver == "competing":
            body = (
                f"{greeting}\n\nWant to escalate — our hiring manager would like to spend 30 minutes with you {slot} "
                f"to walk you through what the first six months of {role} would look like end-to-end. "
                f"Small ask, big signal from our side.\n\n— Aryan"
            )
        else:
            body = (
                f"{greeting}\n\nOur hiring manager wants to speak with you personally about {role}. "
                f"30 minutes {slot}. Not another interview — a conversation about scope, growth path, and what would matter to you. "
                f"Would you take it?\n\n— Aryan"
            )
        return Script(headline=f"Exec touch — {role}", body=body, channel="call", minutes=30)

    body = (
        f"{greeting}\n\nWanted to be straight — it looks like the timing isn't lining up for {role} on either side. "
        f"We're going to close the loop for now, but would love to keep in touch and reach out first when the next role that fits comes up. "
        f"Thanks for the time you've already given.\n\n— Aryan"
    )
    return Script(headline=f"Graceful close — {role}", body=body, channel="email", minutes=5)


# ─────────────────────── per-candidate scorer ────────────────────────


def _compute_care(c: CandidateInput) -> float:
    match_part = _clamp(c.match_score / 100, 0, 1) * 0.45
    composite_part = (
        _clamp(c.composite_score / 100, 0, 1) * 0.35
        if c.composite_score is not None else 0
    )
    offer_part = 0.20 if c.offer_value_annual and c.offer_value_annual > 0 else 0
    return _clamp(match_part + composite_part + offer_part, 0, 1)


def _default_signals() -> Signals:
    return Signals()


def _score_one(c: CandidateInput) -> CandidateScore:
    signals = c.signals if c.signals is not None else _default_signals()

    axes = {
        "recency": _recency_axis(signals),
        "cadence": _cadence_axis(signals),
        "reliability": _reliability_axis(signals),
        "pace": _pace_axis(signals, c.status),
        "sentiment": _sentiment_axis(signals),
        "competing": _competing_axis(signals),
    }

    momentum = _momentum_from_axes(axes)
    risk = _risk_from_momentum(momentum, signals)
    tier = tier_from_risk(risk)
    ghost = _ghost_probability(risk, c.status)
    care = _compute_care(c)
    half_life = _half_life_days(momentum, care)
    drivers = _harvest_drivers(axes, signals, c.status)
    top_driver = drivers[0].driver if drivers else None
    script = compose_script(c, tier, top_driver)

    salvage = _round(care * (1 - ghost) * 100)

    drafted_exposure = (c.offer_value_annual or 0) * ghost
    pre_offer_exposure = 0 if c.offer_value_annual else PRE_OFFER_SUNK_COST * ghost
    exposure = _round(drafted_exposure + pre_offer_exposure)

    return CandidateScore(
        candidate_id=c.candidate_id,
        candidate_name=c.candidate_name,
        candidate_title=c.candidate_title,
        role_id=c.role_id,
        role_name=c.role_name,
        status=c.status,
        axes={k: float(_round(v)) for k, v in axes.items()},
        momentum=float(_round(momentum)),
        risk=float(_round(risk)),
        tier=tier,
        ghost_probability=round(ghost, 3),
        half_life_days=half_life,
        care=round(care, 3),
        salvage_value=float(salvage),
        exposure_annual=float(exposure),
        drivers=drivers,
        script=script,
        signals=signals,
        note_keyphrase=signals.note_keyphrase,
    )


# ─────────────────────── public entrypoint ────────────────────────


def analyze(candidates: Iterable[CandidateInput], now: Optional[int] = None) -> AnchorSummary:
    now_ms = now if now is not None else 0
    active = [c for c in candidates if c.status != "passed"]
    scores = sorted([_score_one(c) for c in active], key=lambda s: s.risk, reverse=True)

    at_risk = sum(1 for s in scores if s.risk >= TIER_THRESHOLDS["reengage"])
    critical = sum(1 for s in scores if s.risk >= TIER_THRESHOLDS["exec"])
    released = [s for s in scores if s.tier == "release"]

    exposure_annual = 0.0
    exposure_pre_offer = 0.0
    by_id: dict[tuple[int, str], CandidateInput] = {(c.candidate_id, c.role_id): c for c in active}
    for s in scores:
        if s.risk < TIER_THRESHOLDS["reengage"]:
            continue
        c = by_id.get((s.candidate_id, s.role_id))
        if c and c.offer_value_annual:
            exposure_annual += s.exposure_annual
        else:
            exposure_pre_offer += s.exposure_annual

    salvage_queue = sorted(
        [s for s in scores if s.salvage_value > 5 and s.risk >= TIER_THRESHOLDS["ping"]],
        key=lambda s: s.salvage_value, reverse=True,
    )[:10]

    critical_queue = [s for s in scores if s.tier in ("exec", "release")]

    by_stage = _stage_breakdown(scores)
    driver_histogram = _driver_histogram(scores)
    tier_mix: dict[str, int] = {t: 0 for t in TIER_ORDER}
    for s in scores:
        tier_mix[s.tier] += 1

    mean_momentum = _safe_mean([s.momentum for s in scores])
    mean_risk = _safe_mean([s.risk for s in scores])

    notes: list[str] = []
    if not scores:
        notes.append("No active candidates in the pipeline — Anchor lights up when at least one role has an active shortlist.")
    if released:
        plural = "" if len(released) == 1 else "s"
        notes.append(f"{len(released)} candidate{plural} recommended for graceful close — export to Revive for future roles.")
    if exposure_annual > 0:
        notes.append(f"Drafted-offer exposure at risk: ₹{_round(exposure_annual):,}.")

    salvage_value_total = _round(sum(s.salvage_value for s in salvage_queue))

    totals = {
        "active": len(scores),
        "atRisk": at_risk,
        "critical": critical,
        "released": len(released),
        "exposureAnnual": _round(exposure_annual),
        "exposurePreOffer": _round(exposure_pre_offer),
        "salvageableCount": len(salvage_queue),
        "salvageValueTotal": salvage_value_total,
    }

    return AnchorSummary(
        generated_at=now_ms,
        totals=totals,
        scores=scores,
        salvage_queue=salvage_queue,
        critical_queue=critical_queue,
        by_stage=by_stage,
        driver_histogram=driver_histogram,
        tier_mix=tier_mix,
        mean_momentum=None if mean_momentum is None else float(_round(mean_momentum)),
        mean_risk=None if mean_risk is None else float(_round(mean_risk)),
        notes=notes,
    )


def _stage_breakdown(scores: list[CandidateScore]) -> list[StageBreakdown]:
    buckets: dict[str, StageBreakdown] = {}
    for s in scores:
        b = buckets.get(s.status)
        if b is None:
            b = StageBreakdown(status=s.status, count=0, at_risk=0, critical=0, mean_risk=0)
            buckets[s.status] = b
        b.count += 1
        if s.risk >= TIER_THRESHOLDS["reengage"]:
            b.at_risk += 1
        if s.risk >= TIER_THRESHOLDS["exec"]:
            b.critical += 1
        b.mean_risk += s.risk
    order = ["new", "outreach", "screening", "interview", "offer"]
    out: list[StageBreakdown] = []
    for st in order:
        b = buckets.get(st)
        if b is None or b.count == 0:
            continue
        b.mean_risk = float(_round(b.mean_risk / b.count))
        out.append(b)
    return out


def _driver_histogram(scores: list[CandidateScore]) -> list[dict[str, Any]]:
    counts: dict[Driver, int] = {}
    for s in scores:
        for d in s.drivers:
            counts[d.driver] = counts.get(d.driver, 0) + 1
    out = [
        {"driver": d, "label": DRIVER_LABEL[d], "count": n, "hex": DRIVER_HEX[d]}
        for d, n in counts.items()
    ]
    out.sort(key=lambda x: x["count"], reverse=True)
    return out


# ─────────────────────── markdown export ────────────────────────


def to_markdown(s: AnchorSummary) -> str:
    L: list[str] = []
    L.append("# Anchor — Momentum & Drop-Off Risk")
    L.append("")
    L.append(
        f"**Active**: {s.totals['active']} · **At risk**: {s.totals['atRisk']} · "
        f"**Critical**: {s.totals['critical']} · **Released**: {s.totals['released']}"
    )
    if s.mean_momentum is not None and s.mean_risk is not None:
        L.append(f"**Mean momentum**: {int(s.mean_momentum)}/100 · **Mean risk**: {int(s.mean_risk)}/100")
    if s.totals["exposureAnnual"] > 0:
        L.append(f"**Drafted-offer exposure**: ₹{s.totals['exposureAnnual']:,}")
    L.append("")
    L.append("## Salvage queue")
    if not s.salvage_queue:
        L.append("_No candidates need salvaging right now._")
    else:
        for c in s.salvage_queue:
            L.append(
                f"- **{c.candidate_name}** · {c.role_name} · {c.status} · risk {int(c.risk)} · "
                f"ghost {int(c.ghost_probability * 100)}% · **{TIER_LABEL[c.tier]}**"
            )
            for d in c.drivers[:3]:
                L.append(f"  - {d.label}: {d.detail}")
            L.append("")
            L.append("  Recommended nudge:")
            L.append("  ```")
            for line in c.script.body.split("\n"):
                L.append(f"  {line}")
            L.append("  ```")
            L.append("")
    if s.by_stage:
        L.append("## Stage risk")
        for b in s.by_stage:
            L.append(
                f"- **{b.status}** — {b.count} active · {b.at_risk} at risk · mean risk {int(b.mean_risk)}/100"
            )
    if s.driver_histogram:
        L.append("")
        L.append("## Dominant drivers")
        for d in s.driver_histogram[:5]:
            plural = "" if d["count"] == 1 else "s"
            L.append(f"- **{d['label']}** — {d['count']} occurrence{plural}")
    if s.notes:
        L.append("")
        L.append("## Notes")
        for n in s.notes:
            L.append(f"- {n}")
    return "\n".join(L)


# ─────────────────────── serialization ────────────────────────


def score_as_dict(s: CandidateScore) -> dict[str, Any]:
    return {
        "candidateId": s.candidate_id,
        "candidateName": s.candidate_name,
        "candidateTitle": s.candidate_title,
        "roleId": s.role_id,
        "roleName": s.role_name,
        "status": s.status,
        "axes": s.axes,
        "momentum": s.momentum,
        "risk": s.risk,
        "tier": s.tier,
        "ghostProbability": s.ghost_probability,
        "halfLifeDays": s.half_life_days,
        "care": s.care,
        "salvageValue": s.salvage_value,
        "exposureAnnual": s.exposure_annual,
        "drivers": [
            {"driver": d.driver, "label": d.label, "detail": d.detail, "contribution": d.contribution}
            for d in s.drivers
        ],
        "script": {
            "headline": s.script.headline,
            "body": s.script.body,
            "channel": s.script.channel,
            "minutes": s.script.minutes,
        },
        "signals": {
            "daysSinceLastTouch": s.signals.days_since_last_touch,
            "lastTouchDirection": s.signals.last_touch_direction,
            "responseLatencyHours": s.signals.response_latency_hours,
            "rescheduleCount": s.signals.reschedule_count,
            "noShow": s.signals.no_show,
            "daysInStage": s.signals.days_in_stage,
            "competingPipelines": s.signals.competing_pipelines,
            "sentimentTone": s.signals.sentiment_tone,
            "externalOffer": s.signals.external_offer,
            "noteKeyphrase": s.signals.note_keyphrase,
        },
        "noteKeyphrase": s.note_keyphrase,
    }


def summary_as_dict(s: AnchorSummary) -> dict[str, Any]:
    return {
        "generatedAt": s.generated_at,
        "totals": s.totals,
        "scores": [score_as_dict(x) for x in s.scores],
        "salvageQueue": [score_as_dict(x) for x in s.salvage_queue],
        "criticalQueue": [score_as_dict(x) for x in s.critical_queue],
        "byStage": [
            {
                "status": b.status,
                "count": b.count,
                "atRisk": b.at_risk,
                "critical": b.critical,
                "meanRisk": b.mean_risk,
            }
            for b in s.by_stage
        ],
        "driverHistogram": s.driver_histogram,
        "tierMix": s.tier_mix,
        "meanMomentum": s.mean_momentum,
        "meanRisk": s.mean_risk,
        "notes": s.notes,
    }


def defaults() -> dict[str, Any]:
    return {
        "tiers": [
            {
                "tier": t,
                "label": TIER_LABEL[t],
                "blurb": TIER_BLURB[t],
                "hex": TIER_HEX[t],
                "tone": TIER_TONE[t],
            } for t in TIER_ORDER
        ],
        "axes": [
            {"axis": a, "label": AXIS_LABEL[a], "weight": AXIS_WEIGHTS[a]}
            for a in AXES
        ],
        "drivers": [
            {"driver": d, "label": DRIVER_LABEL[d], "hex": DRIVER_HEX[d]}
            for d in DRIVER_LABEL.keys()
        ],
        "thresholds": TIER_THRESHOLDS,
        "stageBudgetDays": STAGE_BUDGET_DAYS,
        "stageGhostPrior": STAGE_GHOST_PRIOR,
        "recencyZeroDays": RECENCY_ZERO_DAYS,
        "cadenceZeroHours": CADENCE_ZERO_HOURS,
        "reliabilityFloor": RELIABILITY_FLOOR,
        "externalOfferRiskBump": EXTERNAL_OFFER_RISK_BUMP,
        "riskCeiling": RISK_CEILING,
        "recoverFloor": RECOVER_FLOOR,
        "preOfferSunkCost": PRE_OFFER_SUNK_COST,
    }
