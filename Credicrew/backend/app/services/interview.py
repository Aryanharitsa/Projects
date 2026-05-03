"""Interview Kit engine — Python mirror of frontend/src/lib/interview.ts.

Given a Role's QueryPlan + a candidate, produce a deterministic interview
plan (4 stages × question bank + weighted rubric). Given a filled-in
scorecard, aggregate to a composite + recommendation tier.

Pure functions — no I/O. Output shapes mirror the TS engine so a client
can flow client-side <-> server-side without losing context.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Iterable, Literal

from app.services.match import QueryPlan

Stage = Literal["phone_screen", "technical", "system_design", "behavioral"]
STAGES: tuple[Stage, ...] = (
    "phone_screen", "technical", "system_design", "behavioral",
)
STAGE_LABEL: dict[Stage, str] = {
    "phone_screen": "Phone screen",
    "technical": "Technical",
    "system_design": "System design",
    "behavioral": "Behavioral",
}

# ---------- skill question bank (kept in lockstep with the TS module) ----------

@dataclass
class _BankQ:
    id: str
    prompt: str
    followups: list[str]
    signal: str
    difficulty: int


@dataclass
class _Bank:
    signal: str
    category: str
    questions: list[_BankQ]


SKILL_BANK: dict[str, _Bank] = {
    "react": _Bank(
        signal="frontend_depth", category="frontend",
        questions=[
            _BankQ("react.001", "A modal flickers between renders. Walk me through how you would diagnose it.",
                   ["When would you reach for `useLayoutEffect` vs `useEffect`?"], "frontend_depth", 2),
            _BankQ("react.002", "Design a state model for a deeply nested form. When does context start hurting more than it helps?",
                   ["How would you avoid a re-render storm on every keystroke?"], "frontend_depth", 3),
            _BankQ("react.003", "A list of 5,000 items is janking. What are the next three things you try, in order?",
                   ["Tradeoffs of `react-window` vs CSS `content-visibility`?"], "frontend_depth", 3),
            _BankQ("react.004", "Walk through what `Suspense` boundaries actually buy you, and a case where they make UX worse.",
                   ["Streaming SSR — when is it net negative?"], "frontend_depth", 4),
        ],
    ),
    "next.js": _Bank(
        signal="frontend_depth", category="frontend",
        questions=[
            _BankQ("next.001", "When would you reach for a server component vs a client component?",
                   ["What breaks if you `use client` everywhere?"], "frontend_depth", 2),
            _BankQ("next.002", "Design caching for a product page that needs personalised pricing.",
                   ["Where does `revalidateTag` fit in?"], "frontend_depth", 3),
        ],
    ),
    "typescript": _Bank(
        signal="language_craft", category="language",
        questions=[
            _BankQ("ts.001", "Talk me through one place generics actually helped you, and one place they made code worse.",
                   ["When would you reach for a discriminated union over generics?"], "language_craft", 2),
            _BankQ("ts.002", "Design a `DeepReadonly<T>` and explain where the type system bites you.",
                   ["What about cyclic types?"], "language_craft", 3),
        ],
    ),
    "fastapi": _Bank(
        signal="backend_depth", category="backend",
        questions=[
            _BankQ("fastapi.001", "How does FastAPI dependency injection actually work? Show me how you would compose request-scoped DB sessions with a per-tenant cache.",
                   ["How would you unit test that?"], "backend_depth", 3),
            _BankQ("fastapi.002", "A handler is mixing async and sync DB calls under load and stalling. Walk through your fix.",
                   ["When is `run_in_threadpool` the wrong tool?"], "backend_depth", 3),
            _BankQ("fastapi.003", "Sketch an auth middleware that handles both session cookies and bearer tokens with one decorator.",
                   ["Where do you put rate limiting?"], "backend_depth", 3),
            _BankQ("fastapi.004", "How do you surface validation errors that are useful to the *frontend* without leaking internals?",
                   ["Where should error shape live?"], "backend_depth", 2),
        ],
    ),
    "python": _Bank(
        signal="language_craft", category="language",
        questions=[
            _BankQ("py.001", "Explain why a CPU-bound loop in `asyncio` blocks the event loop, and how you would actually fix that in production.",
                   ["Tradeoffs of `ProcessPoolExecutor` vs subinterpreters?"], "language_craft", 3),
            _BankQ("py.002", "Walk me through a memory leak you have actually shipped and how you found it.",
                   ["How would `tracemalloc` help here?"], "language_craft", 3),
        ],
    ),
    "postgres": _Bank(
        signal="data_systems", category="data",
        questions=[
            _BankQ("pg.001", "Design indexes for a query that filters on `(tenant_id, created_at)` and selects ~5% of rows.",
                   ["When would you reach for BRIN over B-tree?"], "data_systems", 3),
            _BankQ("pg.002", "A nightly job sometimes deadlocks against the API. Walk me through diagnosis.",
                   ["What does `pg_stat_activity` get you here?"], "data_systems", 3),
            _BankQ("pg.003", "You have a `JSONB` column that is now 70% of a hot table. What are your options?",
                   ["How would you migrate without downtime?"], "data_systems", 4),
            _BankQ("pg.004", "Explain MVCC like I am a junior dev — then tell me when it bites you.",
                   ["Long-running transactions: real-world impact?"], "data_systems", 3),
        ],
    ),
    "mongodb": _Bank(
        signal="data_systems", category="data",
        questions=[
            _BankQ("mongo.001", "When does Mongo earn its keep over Postgres, in your real experience?",
                   ["What would push you back to Postgres?"], "data_systems", 2),
            _BankQ("mongo.002", "Sketch a sharding strategy for a chat app with 10× burst traffic in one region.",
                   ["Hot-shard mitigation?"], "data_systems", 4),
        ],
    ),
    "redis": _Bank(
        signal="data_systems", category="data",
        questions=[
            _BankQ("redis.001", "Design a rate limiter for 50k req/s across 6 nodes with at-most-once semantics.",
                   ["Token bucket vs sliding window — which fits a public API?"], "data_systems", 3),
        ],
    ),
    "aws": _Bank(
        signal="cloud_infra", category="infra",
        questions=[
            _BankQ("aws.001", "A Lambda has p99 latency 8× p50. Walk me through your debug path.",
                   ["When is provisioned concurrency the wrong answer?"], "cloud_infra", 3),
            _BankQ("aws.002", "Design IAM for a SaaS where each tenant uploads to their own S3 prefix.",
                   ["When would you reach for STS vs presigned URLs?"], "cloud_infra", 3),
        ],
    ),
    "docker": _Bank(
        signal="cloud_infra", category="infra",
        questions=[
            _BankQ("docker.001", "Your image is 1.4 GB. Walk me through trimming it without losing reproducibility.",
                   ["Where does multi-stage hurt CI cache?"], "cloud_infra", 2),
        ],
    ),
    "kubernetes": _Bank(
        signal="cloud_infra", category="infra",
        questions=[
            _BankQ("k8s.001", "A pod is OOMKilled only on Mondays. How do you investigate?",
                   ["HPA vs VPA — when do you mix them?"], "cloud_infra", 3),
        ],
    ),
    "pytorch": _Bank(
        signal="ml_systems", category="ml",
        questions=[
            _BankQ("pt.001", "Training loss spikes around epoch 12 then plateaus. What are your next three diagnostics?",
                   ["Tradeoffs of grad-clip vs LR-warmup here?"], "ml_systems", 3),
        ],
    ),
    "llm": _Bank(
        signal="ml_systems", category="ml",
        questions=[
            _BankQ("llm.001", "Design a RAG pipeline where 30% of queries are about *recent* events.",
                   ["Where would you put a cache, and how do you invalidate?"], "ml_systems", 3),
            _BankQ("llm.002", "How do you measure that a model upgrade actually improved your product?",
                   ["What does \"good\" eval look like?"], "ml_systems", 4),
        ],
    ),
}

UNIVERSAL: dict[Stage, list[_BankQ]] = {
    "phone_screen": [
        _BankQ("ps.001", "Walk me through a project from the last six months you are proudest of, and your contribution.",
               ["What broke that you did not expect?"], "communication", 1),
        _BankQ("ps.002", "Why this team, and why now?",
               ["What would make you turn down an offer?"], "motivation", 1),
        _BankQ("ps.003", "What is non-negotiable for you in your next role?",
               ["What is your bar for IC vs management track?"], "motivation", 1),
    ],
    "technical": [
        _BankQ("tech.001", "Take 90 seconds and tell me the architecture of the system you are most proud of shipping.",
               ["What was the part that was harder than it looked?"], "communication", 2),
        _BankQ("tech.002", "Pick a bug from this past quarter. Walk me from \"user complaint\" to \"merged fix.\"",
               ["How did you prevent recurrence?"], "ownership", 2),
    ],
    "system_design": [
        _BankQ("sd.001", "Design a URL shortener that handles 10k req/s reads, 200 req/s writes, with click analytics.",
               ["How do you keep the analytics pipeline from blocking the hot path?"], "system_design_skill", 3),
        _BankQ("sd.002", "Design a notification system that supports email, push, and in-app, with per-user quiet hours.",
               ["How do you guarantee no duplicates after a retry storm?"], "system_design_skill", 3),
        _BankQ("sd.003", "Design a feature-flag service serving 5 ms p99 across 4 regions.",
               ["Local cache invalidation — pull or push?"], "system_design_skill", 4),
    ],
    "behavioral": [
        _BankQ("b.001", "Tell me about a disagreement with a peer or manager and how it landed.",
               ["Would you handle it differently today?"], "collaboration", 2),
        _BankQ("b.002", "A project shipped late. Walk me through what you owned and what you would change.",
               ["Who else was upstream, and how did you escalate?"], "ownership", 2),
        _BankQ("b.003", "Tell me about a time you changed your mind on a technical decision after pushback.",
               ["What evidence moved you?"], "collaboration", 2),
        _BankQ("b.004", "When did you last say \"I do not know\"? What did you do next?",
               ["Did you bring back what you learned?"], "communication", 1),
    ],
}

SKILL_TO_STAGES: dict[str, list[Stage]] = {
    "frontend": ["technical", "system_design"],
    "backend": ["technical", "system_design"],
    "data": ["technical", "system_design"],
    "infra": ["system_design"],
    "ml": ["technical", "system_design"],
    "language": ["technical"],
}

# ---------- rubric ----------

@dataclass
class RubricDim:
    key: str
    label: str
    description: str
    weight: float
    source: str

DIMENSION_DEFS: dict[str, dict[str, str]] = {
    "frontend_depth": {"label": "Frontend depth", "description": "Component design, perf, browser primitives.", "source": "skill"},
    "backend_depth": {"label": "Backend depth", "description": "API design, concurrency, error semantics.", "source": "skill"},
    "data_systems": {"label": "Data systems", "description": "Indexing, transactions, sharding, query design.", "source": "skill"},
    "cloud_infra": {"label": "Cloud / infra", "description": "Deploy story, IAM, observability, cost awareness.", "source": "skill"},
    "ml_systems": {"label": "ML systems", "description": "Training pipelines, inference, eval, drift.", "source": "skill"},
    "language_craft": {"label": "Language craft", "description": "Idiomatic code, type discipline, runtime gotchas.", "source": "skill"},
    "system_design_skill": {"label": "System design", "description": "Frames problem, names tradeoffs, lands on a coherent answer.", "source": "skill"},
    "communication": {"label": "Communication", "description": "Clear, structured, listens, restates.", "source": "communication"},
    "ownership": {"label": "Ownership", "description": "Drives outcomes end-to-end, owns the failure mode.", "source": "ownership"},
    "collaboration": {"label": "Collaboration", "description": "Productive disagreement, takes input, shares credit.", "source": "collaboration"},
    "scope_influence": {"label": "Scope & influence", "description": "Sets direction, mentors, makes peers better.", "source": "seniority"},
    "motivation": {"label": "Motivation & fit", "description": "Knows what they want, why this team.", "source": "communication"},
}

SENIOR_RANKS = frozenset({"senior", "staff", "principal", "lead"})


def skill_dimension(skill: str) -> str | None:
    bank = SKILL_BANK.get(skill)
    return bank.signal if bank else None


def build_rubric(plan: QueryPlan) -> list[RubricDim]:
    skill_dim_count: dict[str, int] = {}
    for s in plan.skills:
        d = skill_dimension(s)
        if not d:
            continue
        skill_dim_count[d] = skill_dim_count.get(d, 0) + 1

    raw: list[tuple[str, float]] = []
    for key, count in skill_dim_count.items():
        raw.append((key, 1.0 + 0.25 * (count - 1)))
    raw.append(("system_design_skill", 1.0))
    raw.append(("communication", 0.7))
    raw.append(("ownership", 0.7))
    raw.append(("collaboration", 0.6))
    if plan.seniority and plan.seniority in SENIOR_RANKS:
        raw.append(("scope_influence", 1.0))

    trimmed = raw[:7]
    total = sum(w for _, w in trimmed) or 1.0
    out: list[RubricDim] = []
    for key, w in trimmed:
        d = DIMENSION_DEFS.get(key)
        if not d:
            continue
        out.append(RubricDim(
            key=key, label=d["label"], description=d["description"],
            source=d["source"], weight=w / total,
        ))
    return out


# ---------- questions ----------

@dataclass
class Question:
    id: str
    stage: Stage
    prompt: str
    followups: list[str]
    signal: str
    difficulty: int
    source: str


def build_questions(plan: QueryPlan) -> list[Question]:
    out: list[Question] = []
    for skill in plan.skills:
        bank = SKILL_BANK.get(skill)
        if not bank:
            continue
        stages = SKILL_TO_STAGES.get(bank.category, ["technical"])
        picks = bank.questions[:3]
        for i, q in enumerate(picks):
            stage: Stage = stages[i % len(stages)]
            out.append(Question(
                id=q.id, stage=stage, prompt=q.prompt, followups=list(q.followups),
                signal=q.signal, difficulty=q.difficulty, source=skill,
            ))
    for stage in STAGES:
        for q in UNIVERSAL[stage]:
            out.append(Question(
                id=q.id, stage=stage, prompt=q.prompt, followups=list(q.followups),
                signal=q.signal, difficulty=q.difficulty, source="universal",
            ))
    rank: dict[Stage, int] = {s: i for i, s in enumerate(STAGES)}
    out.sort(key=lambda q: (rank[q.stage], q.difficulty, q.id))
    return out


@dataclass
class StageRecord:
    stage: Stage
    status: str = "planned"  # planned | in_progress | done
    scores: list[dict] = field(default_factory=list)
    signals: list[dict] = field(default_factory=list)
    notes: str | None = None


@dataclass
class InterviewPlan:
    rubric: list[RubricDim]
    questions: list[Question]
    stages: list[StageRecord]


def build_plan(plan: QueryPlan) -> InterviewPlan:
    rubric = build_rubric(plan)
    questions = build_questions(plan)
    stages = [
        StageRecord(
            stage=s,
            scores=[{"key": d.key, "rating": None} for d in rubric],
        )
        for s in STAGES
    ]
    return InterviewPlan(rubric=rubric, questions=questions, stages=stages)


# ---------- scoring ----------

@dataclass
class DimResult:
    key: str
    label: str
    weight: float
    rating: int | None
    impact: int


@dataclass
class Summary:
    composite: int
    recommendation: str
    per_dimension: list[DimResult]
    rated_count: int
    total_count: int


def summarise(rubric: list[RubricDim], stages: list[StageRecord]) -> Summary:
    """Aggregate the latest rating per dim across all stages, then weighted-Σ."""
    latest: dict[str, int | None] = {d.key: None for d in rubric}
    for st in stages:
        for sc in st.scores:
            r = sc.get("rating")
            if r is not None:
                latest[sc["key"]] = int(r)

    rated_weight = sum(d.weight for d in rubric if latest.get(d.key) is not None)
    composite = 0.0
    per_dim: list[DimResult] = []
    for d in rubric:
        r = latest.get(d.key)
        renorm = (d.weight / rated_weight) if rated_weight > 0 else d.weight
        if r is None:
            per_dim.append(DimResult(d.key, d.label, renorm, None, 0))
            continue
        norm = (r - 1) / 4.0
        pts = norm * renorm * 100
        composite += pts
        per_dim.append(DimResult(d.key, d.label, renorm, r, round(pts)))

    composite_i = round(composite)
    if composite_i >= 80:
        rec = "strong_hire"
    elif composite_i >= 65:
        rec = "lean_yes"
    elif composite_i >= 50:
        rec = "mixed"
    elif composite_i >= 35:
        rec = "lean_no"
    else:
        rec = "no_hire"

    rated_count = sum(1 for v in latest.values() if v is not None)
    return Summary(
        composite=composite_i,
        recommendation=rec,
        per_dimension=per_dim,
        rated_count=rated_count,
        total_count=len(rubric),
    )


# ---------- helpers ----------

def plan_as_dict(p: InterviewPlan) -> dict:
    return {
        "rubric": [asdict(d) for d in p.rubric],
        "questions": [asdict(q) for q in p.questions],
        "stages": [
            {
                "stage": st.stage,
                "status": st.status,
                "scores": list(st.scores),
                "signals": list(st.signals),
                "notes": st.notes,
            }
            for st in p.stages
        ],
    }


def summary_as_dict(s: Summary) -> dict:
    return {
        "composite": s.composite,
        "recommendation": s.recommendation,
        "rated_count": s.rated_count,
        "total_count": s.total_count,
        "per_dimension": [asdict(d) for d in s.per_dimension],
    }


def stages_from_payload(rubric: list[RubricDim], payload: Iterable[dict]) -> list[StageRecord]:
    """Build StageRecord list from a client-shaped payload (validates dims)."""
    valid = {d.key for d in rubric}
    out: list[StageRecord] = []
    for item in payload:
        st = StageRecord(
            stage=item.get("stage"),  # type: ignore[arg-type]
            status=item.get("status", "planned"),
            scores=[
                {"key": s["key"], "rating": s.get("rating")}
                for s in item.get("scores", [])
                if s.get("key") in valid
            ],
            signals=list(item.get("signals", [])),
            notes=item.get("notes"),
        )
        out.append(st)
    return out
