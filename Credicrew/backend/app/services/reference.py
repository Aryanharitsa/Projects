"""Structured Reference-Check Composer (Day 82 · Reference).

Python mirror of `frontend/src/lib/reference.ts`. Every physics constant
here is duplicated in the TS module so the API and the browser produce
byte-identical reference bundles.

Every prior Credicrew surface answers a hiring question. Discover ranks
who to talk to. Roles moves them through pipeline. Interview Kit runs
the loop. Decision Studio aggregates the panel. Offer Studio benchmarks
comp. Peer Parity audits fairness. Brief hands the interviewer their
prep. What nothing has ever built is the *reference call* — the last
25-minute conversation between "we like this candidate" and "we send the
offer letter." It is almost universally improvised: whoever draws the
short straw phones two names on Monday, freestyles fifteen questions,
and writes back a two-line note.

Reference closes that gap. Given a role's `QueryPlan`, a candidate, and
(optionally) an `InterviewRecord`, this module produces a deterministic
`ReferenceBundle`:

  · claim harvest — every corroboration-worthy assertion the candidate
    has planted, weighted by impact × verifiability
  · red-flag harvest — every rubric dim the panel scored ≤ 3 and every
    high-weight dim they never rated
  · reference slots — recommended ref mix (manager · peer · report ·
    skip_level) based on seniority tier
  · per-slot question sheet — 5–7 questions, prioritised by weight ×
    kind-fit, mixed with 1–2 open questions and a growth question
  · minutes budget — proportional to question count, cap 30 min
  · markdown export — paste-into-doc reference sheet

Once responses come back, `score_responses` folds each verdict into a
score-shift (–25..+15 pts) and issues one of five terminal verdicts
(`proceed`, `proceed_with_caveat`, `reopen`, `block`, `pending`).

No LLM, no I/O. Same input bytes → same output bytes.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Literal

from app.services.interview import DIMENSION_DEFS, RubricDim, build_rubric
from app.services.match import QueryPlan


# ─────────────────────── physics constants ────────────────────────

ReferenceKind = Literal["manager", "peer", "report", "skip_level"]
KINDS: tuple[ReferenceKind, ...] = ("manager", "peer", "report", "skip_level")

KIND_LABEL: dict[ReferenceKind, str] = {
    "manager": "Direct manager",
    "peer": "Peer",
    "report": "Direct report",
    "skip_level": "Skip-level",
}

KIND_HEX: dict[ReferenceKind, str] = {
    "manager": "#818cf8",     # indigo-400
    "peer": "#22d3ee",        # cyan-400
    "report": "#a78bfa",      # violet-400
    "skip_level": "#f472b6",  # pink-400
}

KIND_TONE: dict[ReferenceKind, str] = {
    "manager": "indigo",
    "peer": "cyan",
    "report": "violet",
    "skip_level": "pink",
}

# Reference mix by seniority tier — three slots for senior+, two for the rest.
SENIOR_RANKS = frozenset({"senior", "staff", "principal", "lead"})
STAFF_RANKS = frozenset({"staff", "principal", "lead"})

SLOT_MIX_BY_TIER: dict[str, tuple[ReferenceKind, ...]] = {
    "junior": ("manager", "peer"),
    "mid": ("manager", "peer", "peer"),
    "senior": ("manager", "peer", "report"),
    "staff": ("manager", "peer", "report", "skip_level"),
}

# Time budget per slot: 30-minute cap, roughly proportional to question count.
MAX_QUESTIONS_PER_REF = 7
MIN_QUESTIONS_PER_REF = 4
MINUTES_PER_QUESTION = 3.5
MINUTES_CAP = 30

# Score-shift math. corroborated claims add trust, contradicted claims blow it up.
SHIFT_CORROBORATED = 1.0
SHIFT_CONCERNED = -1.5
SHIFT_CONTRADICTED = -3.0
SHIFT_NO_SIGNAL = 0.0
SHIFT_CLAMP_MIN = -25.0
SHIFT_CLAMP_MAX = 15.0

# Rating thresholds — anything at or below is worth a probe.
REDFLAG_BLOCK_RATING = 2
REDFLAG_WATCH_RATING = 3
REDFLAG_HIGH_WEIGHT = 0.10  # dims above this weight are always worth a ref probe

# Recommended verdict thresholds against the composite score shift.
VERDICT_PROCEED_MIN = 3.0
VERDICT_CAVEAT_MIN = -3.0
VERDICT_REOPEN_MIN = -12.0

# Claim harvesting.
IMPACT_HINTS = (
    ("led", "leadership"), ("managed", "leadership"), ("mentored", "leadership"),
    ("architected", "delivery"), ("designed", "delivery"),
    ("shipped", "delivery"), ("delivered", "delivery"), ("launched", "delivery"),
    ("migrated", "impact"), ("scaled", "impact"), ("optimised", "impact"),
    ("optimized", "impact"), ("reduced", "impact"), ("saved", "impact"),
    ("owned", "ownership"), ("drove", "ownership"),
    ("founder", "leadership"), ("staff", "seniority"), ("principal", "seniority"),
)

NUMBER_RE = re.compile(r"(\d{1,3}(?:[,.]\d{3})*|\d+(?:\.\d+)?)(x|%|k|m|b|/s)?", re.IGNORECASE)

Verdict = Literal["proceed", "proceed_with_caveat", "reopen", "block", "pending"]

VERDICT_LABEL: dict[Verdict, str] = {
    "proceed": "Proceed",
    "proceed_with_caveat": "Proceed with caveat",
    "reopen": "Reopen loop",
    "block": "Block offer",
    "pending": "Awaiting references",
}

VERDICT_TONE: dict[Verdict, str] = {
    "proceed": "emerald",
    "proceed_with_caveat": "sky",
    "reopen": "amber",
    "block": "rose",
    "pending": "slate",
}


AnswerVerdict = Literal["corroborated", "concerned", "contradicted", "no_signal", "pending"]

ANSWER_VERDICT_LABEL: dict[AnswerVerdict, str] = {
    "corroborated": "Corroborated",
    "concerned": "Concerned",
    "contradicted": "Contradicted",
    "no_signal": "No signal",
    "pending": "Pending",
}

ANSWER_VERDICT_TONE: dict[AnswerVerdict, str] = {
    "corroborated": "emerald",
    "concerned": "amber",
    "contradicted": "rose",
    "no_signal": "slate",
    "pending": "sky",
}

# ─────────────────────── dataclasses ────────────────────────

QuestionKind = Literal["claim", "redflag", "delivery", "growth", "open"]

QUESTION_KIND_LABEL: dict[QuestionKind, str] = {
    "claim": "Claim check",
    "redflag": "Flag probe",
    "delivery": "Delivery",
    "growth": "Growth",
    "open": "Open",
}

ClaimKind = Literal["skill", "impact", "seniority", "leadership", "delivery", "ownership"]


@dataclass
class Claim:
    id: str
    kind: ClaimKind
    text: str
    weight: float
    source: str  # tag/keyword/headline/dim


@dataclass
class RedFlag:
    dim: str
    dim_label: str
    latest_rating: int | None
    stage: str | None
    severity: Literal["block", "concern", "watch", "gap"]
    weight: float


@dataclass
class RefQuestion:
    id: str
    text: str
    kind: QuestionKind
    priority: float
    minutes: float
    linked_claim_id: str | None = None
    linked_flag_dim: str | None = None
    hint: str | None = None


@dataclass
class ReferenceSlot:
    slot_id: str
    kind: ReferenceKind
    label: str
    minutes: int
    questions: list[RefQuestion]
    intro: str
    focus: list[str] = field(default_factory=list)


@dataclass
class ReferenceBundle:
    bundle_version: str
    role_id: str
    role_name: str
    candidate_id: int
    candidate_name: str
    seniority_tier: str
    slots: list[ReferenceSlot]
    claims: list[Claim]
    red_flags: list[RedFlag]
    interview_composite: int | None
    total_minutes: int
    total_questions: int
    corpus_hash: str
    headline: str


@dataclass
class ResponseAnswer:
    slot_id: str
    question_id: str
    verdict: AnswerVerdict
    note: str | None = None


@dataclass
class ClaimStatus:
    claim_id: str
    kind: ClaimKind
    text: str
    weight: float
    matches: int
    corroborated: int
    contradicted: int
    concerned: int
    status: Literal["confirmed", "contradicted", "concern", "unknown"]


@dataclass
class FlagStatus:
    dim: str
    dim_label: str
    severity: str
    weight: float
    matches: int
    corroborated: int
    contradicted: int
    concerned: int
    status: Literal["resolved", "confirmed", "concern", "unknown"]


@dataclass
class SlotSummary:
    slot_id: str
    kind: ReferenceKind
    label: str
    answered: int
    total: int
    corroborated: int
    concerned: int
    contradicted: int
    no_signal: int
    coverage_pct: float


@dataclass
class ReferenceReport:
    bundle_version: str
    role_id: str
    candidate_id: int
    verdict: Verdict
    headline: str
    score_shift: float
    projected_composite: int | None
    slots: list[SlotSummary]
    claim_status: list[ClaimStatus]
    flag_status: list[FlagStatus]
    total_answered: int
    total_questions: int
    coverage_pct: float


# ─────────────────────── helpers ────────────────────────

def _seniority_tier(seniority: str | None) -> str:
    if not seniority:
        return "mid"
    s = seniority.lower()
    if s in STAFF_RANKS:
        return "staff"
    if s in SENIOR_RANKS:
        return "senior"
    if s == "junior" or s == "intern":
        return "junior"
    return "mid"


def _tokenise(*parts: str | None) -> list[str]:
    joined = " ".join([p for p in parts if p])
    return [t for t in re.split(r"[^A-Za-z0-9+.#]+", joined.lower()) if t]


def _stable_id(prefix: str, *parts: Any) -> str:
    key = "|".join(str(p) for p in parts)
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:8]
    return f"{prefix}.{digest}"


def _corpus_hash(*parts: Any) -> str:
    key = "\0".join(str(p) for p in parts)
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def _latest_rating_per_dim(record: dict[str, Any] | None) -> dict[str, tuple[int, str | None]]:
    """Return {dim_key: (rating, stage)} using the newest non-null rating."""
    out: dict[str, tuple[int, str | None]] = {}
    if not record:
        return out
    for st in record.get("stages", []) or []:
        stage = st.get("stage")
        for sc in st.get("scores", []) or []:
            r = sc.get("rating")
            if r is None:
                continue
            key = sc.get("key")
            if not key:
                continue
            out[key] = (int(r), stage)
    return out


def _interview_composite(record: dict[str, Any] | None) -> int | None:
    if not record:
        return None
    rubric_raw = record.get("rubric") or []
    if not rubric_raw:
        return None
    ratings = _latest_rating_per_dim(record)
    rated_weight = 0.0
    for d in rubric_raw:
        if ratings.get(d.get("key")) is not None:
            rated_weight += float(d.get("weight", 0.0))
    if rated_weight <= 0:
        return None
    composite = 0.0
    for d in rubric_raw:
        r_entry = ratings.get(d.get("key"))
        if r_entry is None:
            continue
        r = r_entry[0]
        w = float(d.get("weight", 0.0))
        renorm = w / rated_weight
        norm = (r - 1) / 4.0
        composite += norm * renorm * 100
    return round(composite)


# ─────────────────────── harvesters ────────────────────────

def harvest_claims(
    candidate: dict[str, Any],
    plan: QueryPlan,
    interview: dict[str, Any] | None = None,
) -> list[Claim]:
    """Extract corroboration-worthy assertions from the candidate + record."""
    out: list[Claim] = []
    seen: set[str] = set()

    # Skill claims — anything in plan.skills present in candidate tags/keywords.
    plan_skills = [s.lower() for s in (plan.skills or [])]
    cand_tags = [t.lower() for t in (candidate.get("tags") or [])]
    cand_keywords = [k.lower() for k in (candidate.get("keywords") or [])]
    corpus = set(cand_tags + cand_keywords)
    for s in plan_skills:
        if s in corpus and s not in seen:
            text = f"Ships {s} in production"
            c = Claim(
                id=_stable_id("cl.sk", s, candidate.get("id", 0)),
                kind="skill", text=text, weight=0.7, source=s,
            )
            out.append(c)
            seen.add(s)

    headline = (candidate.get("headline") or "").strip()
    role = (candidate.get("role") or "").strip()
    text_blob = f"{headline} {role}".lower()

    # Impact-verb claims — scan headline for classic assertions.
    for verb, kind in IMPACT_HINTS:
        if verb in text_blob and verb not in seen:
            key = f"{verb}:{kind}"
            if key in seen:
                continue
            snippet = _extract_snippet(headline, verb) or _extract_snippet(role, verb)
            if not snippet:
                snippet = f"Candidate claims to have {verb} scope"
            weight = 0.85 if kind in ("leadership", "impact", "delivery") else 0.55
            c = Claim(
                id=_stable_id("cl.imp", verb, candidate.get("id", 0)),
                kind=kind,  # type: ignore[arg-type]
                text=snippet, weight=weight, source=verb,
            )
            out.append(c)
            seen.add(key)

    # Seniority claim — if title or headline says senior/staff/principal/lead.
    for tier in ("staff", "principal", "senior", "lead"):
        if tier in text_blob and f"tier:{tier}" not in seen:
            c = Claim(
                id=_stable_id("cl.ten", tier, candidate.get("id", 0)),
                kind="seniority",
                text=f"Presented as {tier}-tier engineer",
                weight=0.8, source=tier,
            )
            out.append(c)
            seen.add(f"tier:{tier}")
            break  # only take the highest observed tier

    # Numerical impact claims — 40%, 3x, 10M/s, etc.
    for m in NUMBER_RE.finditer(text_blob):
        val = m.group(0)
        # Skip trivial small numbers (years, single digits).
        if len(val) <= 2 and val.isdigit() and int(val) < 5:
            continue
        key = f"num:{val}"
        if key in seen:
            continue
        seen.add(key)
        c = Claim(
            id=_stable_id("cl.num", val, candidate.get("id", 0)),
            kind="impact",
            text=f"Metric claim: '{val}' in profile",
            weight=0.7, source=val,
        )
        out.append(c)

    # Strength signals from interview record — panelists said this out loud.
    if interview:
        for st in interview.get("stages") or []:
            for sig in st.get("signals") or []:
                if sig.get("kind") != "strength":
                    continue
                text = (sig.get("text") or "").strip()
                if not text or text[:60] in seen:
                    continue
                seen.add(text[:60])
                out.append(Claim(
                    id=_stable_id("cl.sig", text[:24], st.get("stage", ""), candidate.get("id", 0)),
                    kind="delivery",
                    text=f"Panel strength note: “{text[:110]}”",
                    weight=0.6, source=f"stage:{st.get('stage','?')}",
                ))

    # Order: highest weight first (deterministic tiebreak on id).
    out.sort(key=lambda c: (-c.weight, c.id))
    return out


def _extract_snippet(blob: str, verb: str) -> str | None:
    if not blob:
        return None
    low = blob.lower()
    idx = low.find(verb.lower())
    if idx < 0:
        return None
    # Grab 60 chars around the verb.
    start = max(0, idx - 8)
    end = min(len(blob), idx + 60)
    snippet = blob[start:end].strip(" ,.;:")
    return f"“{snippet}”" if snippet else None


def harvest_red_flags(
    plan: QueryPlan,
    interview: dict[str, Any] | None = None,
) -> list[RedFlag]:
    """Extract dim-level probes — weak ratings + gaps in high-weight dims."""
    out: list[RedFlag] = []
    if not interview:
        return out
    rubric_raw = interview.get("rubric") or []
    rubric_by_key = {d.get("key"): d for d in rubric_raw}
    ratings = _latest_rating_per_dim(interview)

    for d in rubric_raw:
        key = d.get("key")
        if not key:
            continue
        w = float(d.get("weight", 0.0))
        r_entry = ratings.get(key)
        label = d.get("label") or DIMENSION_DEFS.get(key, {}).get("label", key)
        if r_entry is None:
            if w >= REDFLAG_HIGH_WEIGHT:
                out.append(RedFlag(
                    dim=key, dim_label=label, latest_rating=None, stage=None,
                    severity="gap", weight=w,
                ))
            continue
        rating, stage = r_entry
        severity: Literal["block", "concern", "watch", "gap"]
        if rating <= REDFLAG_BLOCK_RATING:
            severity = "block"
        elif rating <= REDFLAG_WATCH_RATING:
            # Distinguish concern (weight matters) from watch (light nudge).
            severity = "concern" if w >= REDFLAG_HIGH_WEIGHT else "watch"
        else:
            continue
        out.append(RedFlag(
            dim=key, dim_label=label, latest_rating=rating, stage=stage,
            severity=severity, weight=w,
        ))

    # Sort: block > concern > gap > watch, then by weight desc, then dim key.
    sev_rank = {"block": 0, "concern": 1, "gap": 2, "watch": 3}
    out.sort(key=lambda f: (sev_rank[f.severity], -f.weight, f.dim))
    return out


# ─────────────────────── question sheets ────────────────────────

def _claim_probe(claim: Claim, kind: ReferenceKind) -> RefQuestion:
    """Turn a claim into a reference-appropriate probe."""
    text_map: dict[tuple[ClaimKind, ReferenceKind], str] = {
        ("skill", "manager"):
            f"How would you rate their {claim.source} depth on a real production project you saw them ship?",
        ("skill", "peer"):
            f"Have you paired with them on {claim.source}? What's the bug they solved that you couldn't have?",
        ("skill", "report"):
            f"When you got stuck on {claim.source}, what was the specific way they unstuck you?",
        ("skill", "skip_level"):
            f"What visible impact did their {claim.source} work have on your team's velocity?",
        ("impact", "manager"):
            f"Can you walk me through what they actually owned in the work described as: {claim.text}",
        ("impact", "peer"):
            f"They mentioned {claim.text}. What was your read on how much of that outcome was theirs vs the team's?",
        ("impact", "report"):
            f"On the project they described as {claim.text}, what did you see them do that others couldn't?",
        ("impact", "skip_level"):
            f"How did the outcome behind {claim.text} land in the wider org?",
        ("leadership", "manager"):
            "Can you describe a moment they had to make an uncomfortable call and how it landed?",
        ("leadership", "peer"):
            "Have you ever pushed back on a decision they made? Walk me through how they took it.",
        ("leadership", "report"):
            "What's a piece of hard feedback they gave you and how did it change your work?",
        ("leadership", "skip_level"):
            "What have you observed about how they set direction for their team from the outside?",
        ("delivery", "manager"):
            "Tell me about a delivery slip on their watch — what happened, and what did they do differently the next time?",
        ("delivery", "peer"):
            "Have they ever cut a corner that came back to bite the team? How did they handle it?",
        ("delivery", "report"):
            "What's a shipped thing you built with them that would not have happened without them?",
        ("delivery", "skip_level"):
            "Which of their team's ships would you point at as their signature work?",
        ("seniority", "manager"):
            f"What would need to be true for them to be a *notch above* {claim.source}? Are they there today?",
        ("seniority", "peer"):
            f"When you compare them to other {claim.source}-tier folks on the team, where do they actually sit?",
        ("seniority", "report"):
            "Did they behave like a senior IC or like a manager in disguise? Give me a concrete example.",
        ("seniority", "skip_level"):
            "Do you see them being able to hold a room of principals? Where would they get stuck?",
        ("ownership", "manager"):
            "Give me the closest thing to a fire drill they've ever run. What happened after the incident?",
        ("ownership", "peer"):
            "Have they ever owned a failure end-to-end without deflecting to the team?",
        ("ownership", "report"):
            "What's a project you were on where they owned the outcome even though the delivery was ambiguous?",
        ("ownership", "skip_level"):
            "How willingly do they take on unowned problems in your org?",
    }
    text = text_map.get((claim.kind, kind))
    if not text:
        text = f"Can you speak to the claim: {claim.text}"
    return RefQuestion(
        id=_stable_id("q.cl", claim.id, kind),
        text=text,
        kind="claim",
        priority=claim.weight * (1.1 if kind == "manager" else 0.95),
        minutes=MINUTES_PER_QUESTION,
        linked_claim_id=claim.id,
        hint=f"Claim source: {claim.source}",
    )


def _flag_probe(flag: RedFlag, kind: ReferenceKind) -> RefQuestion:
    """Turn a rubric-dim red-flag into a reference probe."""
    dim = flag.dim
    label = flag.dim_label
    text: str
    if dim == "collaboration":
        text = {
            "manager": "How did they handle disagreement with a stubborn stakeholder?",
            "peer": "Tell me about a project where the two of you disagreed. How did that end?",
            "report": "When you disagreed with them technically, how did that go?",
            "skip_level": "What's their reputation across teams — collaborator or lone wolf?",
        }[kind]
    elif dim == "ownership":
        text = {
            "manager": "Walk me through the last time they dropped a ball. How did they recover?",
            "peer": "Have they ever left you holding the bag? Tell me what happened.",
            "report": "What's a project they owned end-to-end even when it got messy?",
            "skip_level": "When something breaks, do they lead or wait for someone else to?",
        }[kind]
    elif dim == "communication":
        text = {
            "manager": "How well do they land hard news with execs?",
            "peer": "Do their design docs land the first time? What do they typically need to rewrite?",
            "report": "When they gave you feedback, was it specific enough that you could act on it?",
            "skip_level": "Do their updates to leadership tell you what you need without follow-ups?",
        }[kind]
    elif dim == "system_design_skill":
        text = {
            "manager": "Walk me through a system they designed that scaled well past its original assumptions.",
            "peer": "In design reviews, do they carry the room or ride the loudest voice?",
            "report": "Have they mentored you on system design? What's an example?",
            "skip_level": "Do you trust their designs at scale? Why?",
        }[kind]
    elif dim == "scope_influence":
        text = {
            "manager": "Where have they meaningfully expanded scope without being asked?",
            "peer": "What are the projects they *changed the direction of* rather than just executed?",
            "report": "How much of your quarter's roadmap did they set vs execute?",
            "skip_level": "Are they a scope-setter or a scope-taker? Give me an example.",
        }[kind]
    elif dim.endswith("_depth") or dim in ("data_systems", "cloud_infra", "language_craft"):
        text = f"How would you rate their {label.lower()} on a project you actually saw them ship?"
    elif dim == "motivation":
        text = "What have you seen about why they want to do this specific kind of work?"
    else:
        text = f"On {label.lower()}, what's the closest concrete story you can share?"
    prio = 0.7 + flag.weight * 2.0
    if flag.severity == "block":
        prio += 0.6
    elif flag.severity == "concern":
        prio += 0.3
    return RefQuestion(
        id=_stable_id("q.fl", dim, kind),
        text=text,
        kind="redflag",
        priority=prio,
        minutes=MINUTES_PER_QUESTION,
        linked_flag_dim=dim,
        hint=f"Panel rated {label} at "
             + (f"{flag.latest_rating}/5" if flag.latest_rating is not None else "no signal"),
    )


def _open_question(kind: ReferenceKind) -> RefQuestion:
    text = {
        "manager": "What haven't I asked that I should have?",
        "peer": "Is there anything about working with them that would surprise us on day 30?",
        "report": "If you were rehiring them, what would you want to know that you didn't when you first joined their team?",
        "skip_level": "What would you tell my CEO about this person, off the record?",
    }[kind]
    return RefQuestion(
        id=_stable_id("q.open", kind),
        text=text, kind="open", priority=0.55, minutes=MINUTES_PER_QUESTION,
        hint="Open question — save for the last 5 minutes.",
    )


def _growth_question(kind: ReferenceKind) -> RefQuestion:
    text = {
        "manager": "Where would you position them on their growth curve — plateauing, steady, or accelerating?",
        "peer": "In a year, do you think they'll be doing bigger things than they're doing today?",
        "report": "How did they help you grow? What's next for them?",
        "skip_level": "How's their trajectory look from where you sit?",
    }[kind]
    return RefQuestion(
        id=_stable_id("q.grow", kind),
        text=text, kind="growth", priority=0.5, minutes=MINUTES_PER_QUESTION,
        hint="Growth signal — asked once, near the end.",
    )


def _delivery_baseline(kind: ReferenceKind) -> RefQuestion:
    text = {
        "manager": "Describe one shipped project from the last 12 months that they clearly owned end-to-end.",
        "peer": "Walk me through a project you built alongside them. What was theirs, what was yours?",
        "report": "What's a shipped project of theirs you saw close up? How did it land?",
        "skip_level": "Which of their team's outputs would you personally point to as their work?",
    }[kind]
    return RefQuestion(
        id=_stable_id("q.deliv", kind),
        text=text, kind="delivery", priority=0.9, minutes=MINUTES_PER_QUESTION,
        hint="Anchors the call on real work — always first.",
    )


def _compose_slot(
    kind: ReferenceKind,
    slot_ix: int,
    claims: list[Claim],
    flags: list[RedFlag],
    plan: QueryPlan,
) -> ReferenceSlot:
    q: list[RefQuestion] = [_delivery_baseline(kind)]

    # Choose flag probes first — kind-affinity by dim.
    flag_priorities: dict[ReferenceKind, tuple[str, ...]] = {
        "manager": ("ownership", "delivery", "communication", "scope_influence", "system_design_skill"),
        "peer": ("collaboration", "communication", "system_design_skill", "language_craft", "backend_depth"),
        "report": ("collaboration", "ownership", "communication", "scope_influence"),
        "skip_level": ("scope_influence", "delivery", "communication", "system_design_skill"),
    }
    kind_pref = flag_priorities[kind]

    def flag_kind_boost(f: RedFlag) -> float:
        return 0.4 if f.dim in kind_pref else 0.0

    for f in flags:
        if f.severity in ("block", "concern", "gap"):
            fq = _flag_probe(f, kind)
            fq.priority += flag_kind_boost(f)
            q.append(fq)

    # Claim probes — pick top claims by weight, up to 2 per slot.
    claim_kind_prio: dict[ReferenceKind, tuple[ClaimKind, ...]] = {
        "manager": ("impact", "leadership", "delivery", "ownership", "seniority", "skill"),
        "peer": ("skill", "delivery", "impact", "ownership", "seniority", "leadership"),
        "report": ("leadership", "delivery", "ownership", "impact", "skill", "seniority"),
        "skip_level": ("impact", "leadership", "seniority", "delivery", "ownership", "skill"),
    }
    prio = claim_kind_prio[kind]

    def claim_score(c: Claim) -> float:
        try:
            aff = 1.0 + (0.15 * (len(prio) - prio.index(c.kind)))
        except ValueError:
            aff = 0.9
        return c.weight * aff

    ranked_claims = sorted(claims, key=lambda c: (-claim_score(c), c.id))
    picks: list[Claim] = []
    used_kinds: set[str] = set()
    for c in ranked_claims:
        if len(picks) >= 3:
            break
        # avoid three copies of the same claim kind
        if c.kind in used_kinds and len(picks) >= 2:
            continue
        picks.append(c)
        used_kinds.add(c.kind)
    for c in picks:
        q.append(_claim_probe(c, kind))

    # Growth for every slot.
    q.append(_growth_question(kind))

    # Open for every slot.
    q.append(_open_question(kind))

    # Cap.
    q.sort(key=lambda x: -x.priority)
    hard_cap = min(MAX_QUESTIONS_PER_REF, max(MIN_QUESTIONS_PER_REF, len(q)))
    trimmed = q[:hard_cap]
    # Enforce anchor: keep delivery baseline first if present.
    delivery_q = next((x for x in trimmed if x.kind == "delivery"), None)
    others = [x for x in trimmed if x.kind != "delivery"]
    ordered: list[RefQuestion] = []
    if delivery_q is not None:
        ordered.append(delivery_q)
    ordered.extend(others)

    minutes = round(min(MINUTES_CAP, len(ordered) * MINUTES_PER_QUESTION))
    intro_map: dict[ReferenceKind, str] = {
        "manager": "Anchor the call on delivery, then probe ownership and hard-news moments.",
        "peer": "Anchor on paired work, then push on collaboration and technical depth.",
        "report": "Anchor on shipped work, then probe leadership and feedback.",
        "skip_level": "Anchor on the visible output, then probe scope and trajectory.",
    }
    focus_dims = [f.dim_label for f in flags[:3]]
    slot_id = _stable_id("slot", kind, slot_ix)
    return ReferenceSlot(
        slot_id=slot_id,
        kind=kind,
        label=KIND_LABEL[kind],
        minutes=minutes,
        questions=ordered,
        intro=intro_map[kind],
        focus=focus_dims,
    )


# ─────────────────────── main composer ────────────────────────

def compose_bundle(
    role: dict[str, Any],
    candidate: dict[str, Any],
    interview: dict[str, Any] | None = None,
) -> ReferenceBundle:
    plan: QueryPlan = role.get("plan")  # type: ignore[assignment]
    if not isinstance(plan, QueryPlan):
        plan = QueryPlan(
            text=(plan or {}).get("text", "") if isinstance(plan, dict) else "",
            skills=(plan or {}).get("skills", []) if isinstance(plan, dict) else [],
            location=(plan or {}).get("location") if isinstance(plan, dict) else None,
            seniority=(plan or {}).get("seniority") if isinstance(plan, dict) else None,
        )

    tier = _seniority_tier(plan.seniority)
    mix = SLOT_MIX_BY_TIER.get(tier, SLOT_MIX_BY_TIER["mid"])

    claims = harvest_claims(candidate, plan, interview)
    flags = harvest_red_flags(plan, interview)

    slots: list[ReferenceSlot] = []
    for ix, kind in enumerate(mix):
        slots.append(_compose_slot(kind, ix, claims, flags, plan))

    total_q = sum(len(s.questions) for s in slots)
    total_min = sum(s.minutes for s in slots)

    interview_comp = _interview_composite(interview)

    headline = _headline(candidate, tier, len(claims), len(flags), interview_comp)
    corpus_hash = _corpus_hash(
        role.get("id"),
        candidate.get("id"),
        tier,
        tuple(s.kind for s in slots),
        tuple(c.id for c in claims),
        tuple(f.dim for f in flags),
    )
    return ReferenceBundle(
        bundle_version="credicrew.reference.v1",
        role_id=str(role.get("id") or ""),
        role_name=str(role.get("name") or "Role"),
        candidate_id=int(candidate.get("id", 0)),
        candidate_name=str(candidate.get("name") or "Candidate"),
        seniority_tier=tier,
        slots=slots,
        claims=claims,
        red_flags=flags,
        interview_composite=interview_comp,
        total_minutes=total_min,
        total_questions=total_q,
        corpus_hash=corpus_hash,
        headline=headline,
    )


def _headline(
    candidate: dict[str, Any],
    tier: str,
    n_claims: int,
    n_flags: int,
    composite: int | None,
) -> str:
    name = candidate.get("name") or "Candidate"
    parts: list[str] = []
    if composite is not None:
        parts.append(f"interview composite {composite}/100")
    if n_flags:
        parts.append(f"{n_flags} rubric flag{'s' if n_flags != 1 else ''} to probe")
    if n_claims:
        parts.append(f"{n_claims} claim{'s' if n_claims != 1 else ''} to corroborate")
    if not parts:
        return f"Reference sheet for {name} — {tier} tier · no interview signal yet."
    return f"Reference sheet for {name} — {tier} tier · " + ", ".join(parts) + "."


# ─────────────────────── response scoring ────────────────────────

def score_responses(
    bundle: ReferenceBundle,
    responses: Iterable[ResponseAnswer],
) -> ReferenceReport:
    """Fold reference answers back into a projected composite + verdict."""
    answers = list(responses)
    q_by_id: dict[str, RefQuestion] = {q.id: q for slot in bundle.slots for q in slot.questions}
    q_slot: dict[str, ReferenceSlot] = {q.id: slot for slot in bundle.slots for q in slot.questions}
    claim_by_id: dict[str, Claim] = {c.id: c for c in bundle.claims}
    flag_by_dim: dict[str, RedFlag] = {f.dim: f for f in bundle.red_flags}

    # slot roll-up
    slot_answered: dict[str, int] = {s.slot_id: 0 for s in bundle.slots}
    slot_corroborated: dict[str, int] = {s.slot_id: 0 for s in bundle.slots}
    slot_concerned: dict[str, int] = {s.slot_id: 0 for s in bundle.slots}
    slot_contradicted: dict[str, int] = {s.slot_id: 0 for s in bundle.slots}
    slot_no_signal: dict[str, int] = {s.slot_id: 0 for s in bundle.slots}

    # claim/flag roll-ups
    claim_agg: dict[str, dict[str, int]] = {
        c.id: {"matches": 0, "corr": 0, "contra": 0, "concern": 0}
        for c in bundle.claims
    }
    flag_agg: dict[str, dict[str, int]] = {
        f.dim: {"matches": 0, "corr": 0, "contra": 0, "concern": 0}
        for f in bundle.red_flags
    }

    total_shift = 0.0
    total_answered = 0

    for a in answers:
        q = q_by_id.get(a.question_id)
        if not q:
            continue
        slot = q_slot.get(q.id)
        if not slot:
            continue
        if a.verdict == "pending":
            continue
        slot_answered[slot.slot_id] += 1
        total_answered += 1

        if a.verdict == "corroborated":
            slot_corroborated[slot.slot_id] += 1
            total_shift += SHIFT_CORROBORATED * q.priority
        elif a.verdict == "concerned":
            slot_concerned[slot.slot_id] += 1
            total_shift += SHIFT_CONCERNED * q.priority
        elif a.verdict == "contradicted":
            slot_contradicted[slot.slot_id] += 1
            total_shift += SHIFT_CONTRADICTED * q.priority
        elif a.verdict == "no_signal":
            slot_no_signal[slot.slot_id] += 1
            total_shift += SHIFT_NO_SIGNAL * q.priority

        # claim aggregation
        if q.linked_claim_id and q.linked_claim_id in claim_agg:
            agg = claim_agg[q.linked_claim_id]
            agg["matches"] += 1
            if a.verdict == "corroborated":
                agg["corr"] += 1
            elif a.verdict == "contradicted":
                agg["contra"] += 1
            elif a.verdict == "concerned":
                agg["concern"] += 1

        # flag aggregation
        if q.linked_flag_dim and q.linked_flag_dim in flag_agg:
            agg = flag_agg[q.linked_flag_dim]
            agg["matches"] += 1
            if a.verdict == "corroborated":
                agg["corr"] += 1
            elif a.verdict == "contradicted":
                agg["contra"] += 1
            elif a.verdict == "concerned":
                agg["concern"] += 1

    total_shift = max(SHIFT_CLAMP_MIN, min(SHIFT_CLAMP_MAX, total_shift))

    # claim statuses
    claim_status: list[ClaimStatus] = []
    for cid, agg in claim_agg.items():
        c = claim_by_id[cid]
        status: Literal["confirmed", "contradicted", "concern", "unknown"]
        if agg["contra"] >= 1:
            status = "contradicted"
        elif agg["corr"] >= 2 or (agg["corr"] >= 1 and agg["matches"] == 1):
            status = "confirmed"
        elif agg["concern"] >= 1:
            status = "concern"
        else:
            status = "unknown"
        claim_status.append(ClaimStatus(
            claim_id=cid, kind=c.kind, text=c.text, weight=c.weight,
            matches=agg["matches"], corroborated=agg["corr"],
            contradicted=agg["contra"], concerned=agg["concern"],
            status=status,
        ))
    claim_status.sort(key=lambda cs: (-cs.weight, cs.claim_id))

    # flag statuses
    flag_status: list[FlagStatus] = []
    for dim, agg in flag_agg.items():
        f = flag_by_dim[dim]
        status: Literal["resolved", "confirmed", "concern", "unknown"]
        if agg["contra"] >= 1:
            status = "confirmed"  # ref confirmed the flag = worse for candidate
        elif agg["corr"] >= 1:
            status = "resolved"
        elif agg["concern"] >= 1:
            status = "concern"
        else:
            status = "unknown"
        flag_status.append(FlagStatus(
            dim=dim, dim_label=f.dim_label, severity=f.severity, weight=f.weight,
            matches=agg["matches"], corroborated=agg["corr"],
            contradicted=agg["contra"], concerned=agg["concern"],
            status=status,
        ))
    sev_rank = {"block": 0, "concern": 1, "gap": 2, "watch": 3}
    flag_status.sort(key=lambda fs: (sev_rank.get(fs.severity, 4), -fs.weight, fs.dim))

    # slot summaries
    slot_summaries: list[SlotSummary] = []
    for s in bundle.slots:
        total = len(s.questions)
        ans = slot_answered[s.slot_id]
        cov = round(100 * ans / total, 1) if total > 0 else 0.0
        slot_summaries.append(SlotSummary(
            slot_id=s.slot_id, kind=s.kind, label=s.label,
            answered=ans, total=total,
            corroborated=slot_corroborated[s.slot_id],
            concerned=slot_concerned[s.slot_id],
            contradicted=slot_contradicted[s.slot_id],
            no_signal=slot_no_signal[s.slot_id],
            coverage_pct=cov,
        ))

    total_q = sum(len(s.questions) for s in bundle.slots)
    coverage_pct = round(100 * total_answered / total_q, 1) if total_q > 0 else 0.0

    # verdict
    verdict = _verdict(total_shift, claim_status, flag_status, coverage_pct)

    proj = None
    if bundle.interview_composite is not None:
        proj = max(0, min(100, round(bundle.interview_composite + total_shift)))

    headline = _report_headline(verdict, total_shift, claim_status, flag_status, coverage_pct)

    return ReferenceReport(
        bundle_version=bundle.bundle_version,
        role_id=bundle.role_id,
        candidate_id=bundle.candidate_id,
        verdict=verdict,
        headline=headline,
        score_shift=round(total_shift, 2),
        projected_composite=proj,
        slots=slot_summaries,
        claim_status=claim_status,
        flag_status=flag_status,
        total_answered=total_answered,
        total_questions=total_q,
        coverage_pct=coverage_pct,
    )


def _verdict(
    shift: float,
    claim_status: list[ClaimStatus],
    flag_status: list[FlagStatus],
    coverage: float,
) -> Verdict:
    contra_claims = sum(1 for cs in claim_status if cs.status == "contradicted")
    hard_flag_confirmed = sum(
        1 for fs in flag_status if fs.status == "confirmed" and fs.severity in ("block", "concern")
    )
    if coverage < 15.0:
        return "pending"
    if contra_claims >= 2 or hard_flag_confirmed >= 2:
        return "block"
    if contra_claims == 1 or hard_flag_confirmed == 1:
        # A single confirmed hard flag or contradicted claim always reopens
        # the loop — the panel needs to re-check that specific angle before
        # we send an offer, regardless of how the other refs shake out.
        return "reopen"
    if shift >= VERDICT_PROCEED_MIN:
        return "proceed"
    if shift >= VERDICT_CAVEAT_MIN:
        return "proceed_with_caveat"
    if shift >= VERDICT_REOPEN_MIN:
        return "reopen"
    return "block"


def _report_headline(
    verdict: Verdict, shift: float,
    claim_status: list[ClaimStatus],
    flag_status: list[FlagStatus],
    coverage: float,
) -> str:
    sign = "+" if shift >= 0 else ""
    corr = sum(1 for c in claim_status if c.status == "confirmed")
    contra = sum(1 for c in claim_status if c.status == "contradicted")
    resolved = sum(1 for f in flag_status if f.status == "resolved")
    confirmed_flags = sum(1 for f in flag_status if f.status == "confirmed")
    parts: list[str] = [f"shift {sign}{shift:.1f} pts"]
    if corr:
        parts.append(f"{corr} claim{'s' if corr != 1 else ''} confirmed")
    if contra:
        parts.append(f"{contra} contradicted")
    if resolved:
        parts.append(f"{resolved} flag{'s' if resolved != 1 else ''} resolved")
    if confirmed_flags:
        parts.append(f"{confirmed_flags} flag{'s' if confirmed_flags != 1 else ''} confirmed")
    parts.append(f"{coverage:.0f}% coverage")
    verdict_prefix = {
        "proceed": "Proceed to offer — ",
        "proceed_with_caveat": "Proceed with caveat — ",
        "reopen": "Reopen the loop — ",
        "block": "Do not send offer — ",
        "pending": "Awaiting refs — ",
    }[verdict]
    return verdict_prefix + " · ".join(parts) + "."


# ─────────────────────── markdown export ────────────────────────

def to_markdown(bundle: ReferenceBundle) -> str:
    lines: list[str] = []
    lines.append(f"# Reference sheet — {bundle.candidate_name}")
    lines.append("")
    lines.append(f"> {bundle.headline}")
    lines.append("")
    lines.append(f"- **Role:** {bundle.role_name} (`{bundle.role_id}`)")
    lines.append(f"- **Seniority tier:** {bundle.seniority_tier}")
    if bundle.interview_composite is not None:
        lines.append(f"- **Interview composite:** {bundle.interview_composite}/100")
    lines.append(f"- **Total minutes budgeted:** {bundle.total_minutes}m across {len(bundle.slots)} references ({bundle.total_questions} questions)")
    lines.append(f"- **Corpus hash:** `{bundle.corpus_hash}`")
    lines.append("")
    if bundle.claims:
        lines.append("## Claims to corroborate")
        for c in bundle.claims[:8]:
            lines.append(f"- **[{c.kind}]** {c.text} · weight {c.weight:.2f} · source `{c.source}`")
        lines.append("")
    if bundle.red_flags:
        lines.append("## Rubric flags to probe")
        for f in bundle.red_flags[:8]:
            r = f"{f.latest_rating}/5" if f.latest_rating is not None else "no rating"
            lines.append(f"- **[{f.severity}]** {f.dim_label} — panel: {r} · weight {f.weight:.2f}")
        lines.append("")
    for slot in bundle.slots:
        lines.append(f"## {slot.label} ({slot.minutes}m)")
        lines.append(f"_{slot.intro}_")
        if slot.focus:
            lines.append(f"- **Focus dims:** {', '.join(slot.focus)}")
        lines.append("")
        for i, q in enumerate(slot.questions, start=1):
            lines.append(f"{i}. **[{QUESTION_KIND_LABEL[q.kind]}]** {q.text}")
            if q.hint:
                lines.append(f"   - _{q.hint}_")
        lines.append("")
    lines.append("---")
    lines.append("_generated by credicrew.reference.v1 — deterministic, same input → same output_")
    return "\n".join(lines)


# ─────────────────────── serialisation ────────────────────────

def bundle_as_dict(b: ReferenceBundle) -> dict:
    return {
        "bundleVersion": b.bundle_version,
        "roleId": b.role_id,
        "roleName": b.role_name,
        "candidateId": b.candidate_id,
        "candidateName": b.candidate_name,
        "seniorityTier": b.seniority_tier,
        "interviewComposite": b.interview_composite,
        "totalMinutes": b.total_minutes,
        "totalQuestions": b.total_questions,
        "corpusHash": b.corpus_hash,
        "headline": b.headline,
        "claims": [
            {"id": c.id, "kind": c.kind, "text": c.text, "weight": c.weight, "source": c.source}
            for c in b.claims
        ],
        "redFlags": [
            {
                "dim": f.dim, "dimLabel": f.dim_label, "latestRating": f.latest_rating,
                "stage": f.stage, "severity": f.severity, "weight": f.weight,
            } for f in b.red_flags
        ],
        "slots": [
            {
                "slotId": s.slot_id, "kind": s.kind, "label": s.label,
                "minutes": s.minutes, "intro": s.intro, "focus": list(s.focus),
                "questions": [
                    {
                        "id": q.id, "text": q.text, "kind": q.kind,
                        "priority": q.priority, "minutes": q.minutes,
                        "linkedClaimId": q.linked_claim_id,
                        "linkedFlagDim": q.linked_flag_dim,
                        "hint": q.hint,
                    } for q in s.questions
                ],
            } for s in b.slots
        ],
    }


def report_as_dict(r: ReferenceReport) -> dict:
    return {
        "bundleVersion": r.bundle_version,
        "roleId": r.role_id,
        "candidateId": r.candidate_id,
        "verdict": r.verdict,
        "verdictLabel": VERDICT_LABEL[r.verdict],
        "verdictTone": VERDICT_TONE[r.verdict],
        "headline": r.headline,
        "scoreShift": r.score_shift,
        "projectedComposite": r.projected_composite,
        "totalAnswered": r.total_answered,
        "totalQuestions": r.total_questions,
        "coveragePct": r.coverage_pct,
        "slots": [asdict(s) for s in r.slots],
        "claimStatus": [asdict(cs) for cs in r.claim_status],
        "flagStatus": [asdict(fs) for fs in r.flag_status],
    }


def defaults() -> dict:
    return {
        "kinds": list(KINDS),
        "kindLabel": KIND_LABEL,
        "kindHex": KIND_HEX,
        "kindTone": KIND_TONE,
        "slotMixByTier": {k: list(v) for k, v in SLOT_MIX_BY_TIER.items()},
        "shiftClamp": [SHIFT_CLAMP_MIN, SHIFT_CLAMP_MAX],
        "shiftWeights": {
            "corroborated": SHIFT_CORROBORATED,
            "concerned": SHIFT_CONCERNED,
            "contradicted": SHIFT_CONTRADICTED,
            "no_signal": SHIFT_NO_SIGNAL,
        },
        "answerVerdicts": {
            k: {"label": ANSWER_VERDICT_LABEL[k], "tone": ANSWER_VERDICT_TONE[k]}
            for k in ANSWER_VERDICT_LABEL
        },
        "verdicts": {
            k: {"label": VERDICT_LABEL[k], "tone": VERDICT_TONE[k]}
            for k in VERDICT_LABEL
        },
        "questionKindLabel": QUESTION_KIND_LABEL,
        "engine": "credicrew-reference/1.0.0",
    }


__all__ = [
    "AnswerVerdict",
    "Claim",
    "ClaimStatus",
    "FlagStatus",
    "RedFlag",
    "ReferenceBundle",
    "ReferenceKind",
    "ReferenceReport",
    "ReferenceSlot",
    "ResponseAnswer",
    "RefQuestion",
    "SlotSummary",
    "Verdict",
    "bundle_as_dict",
    "compose_bundle",
    "defaults",
    "harvest_claims",
    "harvest_red_flags",
    "report_as_dict",
    "score_responses",
    "to_markdown",
]
