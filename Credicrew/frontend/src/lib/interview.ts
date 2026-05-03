// Interview Kit engine.
//
// Day 7 wired the workspace through *outreach*. The hiring loop then went
// silent the moment a candidate flipped to `interview` status — no prep,
// no rubric, no record. This module fills that gap: given a Role's
// QueryPlan + a candidate, it produces a deterministic, JD-tailored
// interview plan (4 stages × question bank + weighted rubric), persists
// per-stage scorecards in localStorage, and aggregates a composite +
// recommendation tier.
//
// All pure functions. Same logic is mirrored on the backend in
// `app/services/interview.py` so a programmatic / agentic client gets
// byte-identical output.

import type { QueryPlan } from '@/lib/match';
import type { CandidateLike } from '@/lib/match';

// ---------- types ----------

export type InterviewStage =
  | 'phone_screen'
  | 'technical'
  | 'system_design'
  | 'behavioral';

export const STAGES: InterviewStage[] = [
  'phone_screen',
  'technical',
  'system_design',
  'behavioral',
];

export const STAGE_LABEL: Record<InterviewStage, string> = {
  phone_screen: 'Phone screen',
  technical: 'Technical',
  system_design: 'System design',
  behavioral: 'Behavioral',
};

export const STAGE_TONE: Record<InterviewStage, string> = {
  phone_screen: 'sky',
  technical: 'indigo',
  system_design: 'violet',
  behavioral: 'emerald',
};

export type Question = {
  id: string;
  stage: InterviewStage;
  prompt: string;
  followups: string[];
  signal: string;       // dimension key it probes
  difficulty: 1 | 2 | 3 | 4;
  source: string;       // skill key it came from, or 'universal'
};

export type DimensionSource =
  | 'skill'
  | 'seniority'
  | 'communication'
  | 'collaboration'
  | 'ownership';

export type RubricDimension = {
  key: string;
  label: string;
  description: string;
  weight: number;       // weights renormalised to sum to 1
  source: DimensionSource;
};

export type DimensionScore = {
  key: string;
  rating: 1 | 2 | 3 | 4 | 5 | null;   // null = not rated yet
  notes?: string;
};

export type Signal = {
  kind: 'strength' | 'concern';
  text: string;
  ts: number;
};

export type StageRecord = {
  stage: InterviewStage;
  status: 'planned' | 'in_progress' | 'done';
  scores: DimensionScore[];
  signals: Signal[];
  notes?: string;
  startedAt?: number;
  completedAt?: number;
};

export type InterviewRecord = {
  id: string;
  roleId: string;
  candidateId: number;
  rubric: RubricDimension[];
  questions: Question[];
  stages: StageRecord[];
  createdAt: number;
  updatedAt: number;
};

export type Recommendation =
  | 'no_hire'
  | 'lean_no'
  | 'mixed'
  | 'lean_yes'
  | 'strong_hire';

export const RECOMMENDATION_LABEL: Record<Recommendation, string> = {
  no_hire: 'No hire',
  lean_no: 'Lean no',
  mixed: 'Mixed signal',
  lean_yes: 'Lean yes',
  strong_hire: 'Strong hire',
};

export const RECOMMENDATION_TONE: Record<Recommendation, string> = {
  no_hire: 'rose',
  lean_no: 'amber',
  mixed: 'sky',
  lean_yes: 'indigo',
  strong_hire: 'emerald',
};

export type ScorecardSummary = {
  composite: number;        // 0..100 (rated dims only)
  recommendation: Recommendation;
  perDimension: {
    key: string;
    label: string;
    weight: number;          // renormalised across rated dims
    rating: number | null;
    impact: number;          // points contributed of 100
  }[];
  ratedCount: number;
  totalCount: number;
  strengths: Signal[];
  concerns: Signal[];
};

// ---------- skill question bank ----------
//
// Tightly curated. Each entry maps a SKILL_VOCAB key (or universal stage)
// to a small set of probing questions tagged with a signal-dimension. A
// rubric dimension keys to one or more of these signals so a question
// always pays into a rubric row.

type SkillBank = {
  signal: string;
  category: 'frontend' | 'backend' | 'data' | 'infra' | 'ml' | 'language';
  questions: Omit<Question, 'source' | 'stage'>[];
};

const SKILL_BANK: Record<string, SkillBank> = {
  react: {
    signal: 'frontend_depth',
    category: 'frontend',
    questions: [
      { id: 'react.001', prompt: 'A modal flickers between renders. Walk me through how you would diagnose it.', followups: ['When would you reach for `useLayoutEffect` vs `useEffect`?'], signal: 'frontend_depth', difficulty: 2 },
      { id: 'react.002', prompt: 'Design a state model for a deeply nested form. When does context start hurting more than it helps?', followups: ['How would you avoid a re-render storm on every keystroke?'], signal: 'frontend_depth', difficulty: 3 },
      { id: 'react.003', prompt: 'A list of 5,000 items is janking. What are the next three things you try, in order?', followups: ['Tradeoffs of `react-window` vs CSS `content-visibility`?'], signal: 'frontend_depth', difficulty: 3 },
      { id: 'react.004', prompt: 'Walk through what `Suspense` boundaries actually buy you, and a case where they make UX worse.', followups: ['Streaming SSR — when is it net negative?'], signal: 'frontend_depth', difficulty: 4 },
    ],
  },
  'next.js': {
    signal: 'frontend_depth',
    category: 'frontend',
    questions: [
      { id: 'next.001', prompt: 'When would you reach for a server component vs a client component?', followups: ['What breaks if you `use client` everywhere?'], signal: 'frontend_depth', difficulty: 2 },
      { id: 'next.002', prompt: 'Design caching for a product page that needs personalised pricing.', followups: ['Where does `revalidateTag` fit in?'], signal: 'frontend_depth', difficulty: 3 },
    ],
  },
  typescript: {
    signal: 'language_craft',
    category: 'language',
    questions: [
      { id: 'ts.001', prompt: 'Talk me through one place generics actually helped you, and one place they made code worse.', followups: ['When would you reach for a discriminated union over generics?'], signal: 'language_craft', difficulty: 2 },
      { id: 'ts.002', prompt: 'Design a `DeepReadonly<T>` and explain where the type system bites you.', followups: ['What about cyclic types?'], signal: 'language_craft', difficulty: 3 },
    ],
  },
  fastapi: {
    signal: 'backend_depth',
    category: 'backend',
    questions: [
      { id: 'fastapi.001', prompt: 'How does FastAPI dependency injection actually work? Show me how you would compose request-scoped DB sessions with a per-tenant cache.', followups: ['How would you unit test that?'], signal: 'backend_depth', difficulty: 3 },
      { id: 'fastapi.002', prompt: 'A handler is mixing async and sync DB calls under load and stalling. Walk through your fix.', followups: ['When is `run_in_threadpool` the wrong tool?'], signal: 'backend_depth', difficulty: 3 },
      { id: 'fastapi.003', prompt: 'Sketch an auth middleware that handles both session cookies and bearer tokens with one decorator.', followups: ['Where do you put rate limiting?'], signal: 'backend_depth', difficulty: 3 },
      { id: 'fastapi.004', prompt: 'How do you surface validation errors that are useful to the *frontend* without leaking internals?', followups: ['Where should error shape live?'], signal: 'backend_depth', difficulty: 2 },
    ],
  },
  python: {
    signal: 'language_craft',
    category: 'language',
    questions: [
      { id: 'py.001', prompt: 'Explain why a CPU-bound loop in `asyncio` blocks the event loop, and how you would actually fix that in production.', followups: ['Tradeoffs of `ProcessPoolExecutor` vs subinterpreters?'], signal: 'language_craft', difficulty: 3 },
      { id: 'py.002', prompt: 'Walk me through a memory leak you have actually shipped and how you found it.', followups: ['How would `tracemalloc` help here?'], signal: 'language_craft', difficulty: 3 },
    ],
  },
  postgres: {
    signal: 'data_systems',
    category: 'data',
    questions: [
      { id: 'pg.001', prompt: 'Design indexes for a query that filters on `(tenant_id, created_at)` and selects ~5% of rows.', followups: ['When would you reach for BRIN over B-tree?'], signal: 'data_systems', difficulty: 3 },
      { id: 'pg.002', prompt: 'A nightly job sometimes deadlocks against the API. Walk me through diagnosis.', followups: ['What does `pg_stat_activity` get you here?'], signal: 'data_systems', difficulty: 3 },
      { id: 'pg.003', prompt: 'You have a `JSONB` column that is now 70% of a hot table. What are your options?', followups: ['How would you migrate without downtime?'], signal: 'data_systems', difficulty: 4 },
      { id: 'pg.004', prompt: 'Explain MVCC like I am a junior dev — then tell me when it bites you.', followups: ['Long-running transactions: real-world impact?'], signal: 'data_systems', difficulty: 3 },
    ],
  },
  mongodb: {
    signal: 'data_systems',
    category: 'data',
    questions: [
      { id: 'mongo.001', prompt: 'When does Mongo earn its keep over Postgres, in your real experience?', followups: ['What would push you back to Postgres?'], signal: 'data_systems', difficulty: 2 },
      { id: 'mongo.002', prompt: 'Sketch a sharding strategy for a chat app with 10× burst traffic in one region.', followups: ['Hot-shard mitigation?'], signal: 'data_systems', difficulty: 4 },
    ],
  },
  redis: {
    signal: 'data_systems',
    category: 'data',
    questions: [
      { id: 'redis.001', prompt: 'Design a rate limiter for 50k req/s across 6 nodes with at-most-once semantics.', followups: ['Token bucket vs sliding window — which fits a public API?'], signal: 'data_systems', difficulty: 3 },
    ],
  },
  aws: {
    signal: 'cloud_infra',
    category: 'infra',
    questions: [
      { id: 'aws.001', prompt: 'A Lambda has p99 latency 8× p50. Walk me through your debug path.', followups: ['When is provisioned concurrency the wrong answer?'], signal: 'cloud_infra', difficulty: 3 },
      { id: 'aws.002', prompt: 'Design IAM for a SaaS where each tenant uploads to their own S3 prefix.', followups: ['When would you reach for STS vs presigned URLs?'], signal: 'cloud_infra', difficulty: 3 },
    ],
  },
  docker: {
    signal: 'cloud_infra',
    category: 'infra',
    questions: [
      { id: 'docker.001', prompt: 'Your image is 1.4 GB. Walk me through trimming it without losing reproducibility.', followups: ['Where does multi-stage hurt CI cache?'], signal: 'cloud_infra', difficulty: 2 },
    ],
  },
  kubernetes: {
    signal: 'cloud_infra',
    category: 'infra',
    questions: [
      { id: 'k8s.001', prompt: 'A pod is OOMKilled only on Mondays. How do you investigate?', followups: ['HPA vs VPA — when do you mix them?'], signal: 'cloud_infra', difficulty: 3 },
    ],
  },
  pytorch: {
    signal: 'ml_systems',
    category: 'ml',
    questions: [
      { id: 'pt.001', prompt: 'Training loss spikes around epoch 12 then plateaus. What are your next three diagnostics?', followups: ['Tradeoffs of grad-clip vs LR-warmup here?'], signal: 'ml_systems', difficulty: 3 },
    ],
  },
  llm: {
    signal: 'ml_systems',
    category: 'ml',
    questions: [
      { id: 'llm.001', prompt: 'Design a RAG pipeline where 30% of queries are about *recent* events.', followups: ['Where would you put a cache, and how do you invalidate?'], signal: 'ml_systems', difficulty: 3 },
      { id: 'llm.002', prompt: 'How do you measure that a model upgrade actually improved your product?', followups: ['What does "good" eval look like?'], signal: 'ml_systems', difficulty: 4 },
    ],
  },
};

// ---------- universal question banks ----------

const UNIVERSAL: Record<InterviewStage, Omit<Question, 'source' | 'stage'>[]> = {
  phone_screen: [
    { id: 'ps.001', prompt: 'Walk me through a project from the last six months you are proudest of, and your contribution.', followups: ['What broke that you did not expect?'], signal: 'communication', difficulty: 1 },
    { id: 'ps.002', prompt: 'Why this team, and why now?', followups: ['What would make you turn down an offer?'], signal: 'motivation', difficulty: 1 },
    { id: 'ps.003', prompt: 'What is non-negotiable for you in your next role?', followups: ['What is your bar for IC vs management track?'], signal: 'motivation', difficulty: 1 },
  ],
  technical: [
    { id: 'tech.001', prompt: 'Take 90 seconds and tell me the architecture of the system you are most proud of shipping.', followups: ['What was the part that was harder than it looked?'], signal: 'communication', difficulty: 2 },
    { id: 'tech.002', prompt: 'Pick a bug from this past quarter. Walk me from "user complaint" to "merged fix."', followups: ['How did you prevent recurrence?'], signal: 'ownership', difficulty: 2 },
  ],
  system_design: [
    { id: 'sd.001', prompt: 'Design a URL shortener that handles 10k req/s reads, 200 req/s writes, with click analytics.', followups: ['How do you keep the analytics pipeline from blocking the hot path?'], signal: 'system_design_skill', difficulty: 3 },
    { id: 'sd.002', prompt: 'Design a notification system that supports email, push, and in-app, with per-user quiet hours.', followups: ['How do you guarantee no duplicates after a retry storm?'], signal: 'system_design_skill', difficulty: 3 },
    { id: 'sd.003', prompt: 'Design a feature-flag service serving 5 ms p99 across 4 regions.', followups: ['Local cache invalidation — pull or push?'], signal: 'system_design_skill', difficulty: 4 },
  ],
  behavioral: [
    { id: 'b.001', prompt: 'Tell me about a disagreement with a peer or manager and how it landed.', followups: ['Would you handle it differently today?'], signal: 'collaboration', difficulty: 2 },
    { id: 'b.002', prompt: 'A project shipped late. Walk me through what you owned and what you would change.', followups: ['Who else was upstream, and how did you escalate?'], signal: 'ownership', difficulty: 2 },
    { id: 'b.003', prompt: 'Tell me about a time you changed your mind on a technical decision after pushback.', followups: ['What evidence moved you?'], signal: 'collaboration', difficulty: 2 },
    { id: 'b.004', prompt: 'When did you last say "I do not know"? What did you do next?', followups: ['Did you bring back what you learned?'], signal: 'communication', difficulty: 1 },
  ],
};

// stages where each skill question can fire
const SKILL_TO_STAGES: Record<string, InterviewStage[]> = {
  frontend: ['technical', 'system_design'],
  backend: ['technical', 'system_design'],
  data: ['technical', 'system_design'],
  infra: ['system_design'],
  ml: ['technical', 'system_design'],
  language: ['technical'],
};

// ---------- rubric construction ----------

// What a `signal` ID resolves to as a rubric dimension. Multiple skills can
// share a dimension (e.g. react + next.js → frontend_depth) which is the
// point — questions stack signal under one rubric row.
const DIMENSION_DEFS: Record<string, Omit<RubricDimension, 'weight'>> = {
  frontend_depth: {
    key: 'frontend_depth',
    label: 'Frontend depth',
    description: 'Component design, perf, browser primitives.',
    source: 'skill',
  },
  backend_depth: {
    key: 'backend_depth',
    label: 'Backend depth',
    description: 'API design, concurrency, error semantics.',
    source: 'skill',
  },
  data_systems: {
    key: 'data_systems',
    label: 'Data systems',
    description: 'Indexing, transactions, sharding, query design.',
    source: 'skill',
  },
  cloud_infra: {
    key: 'cloud_infra',
    label: 'Cloud / infra',
    description: 'Deploy story, IAM, observability, cost awareness.',
    source: 'skill',
  },
  ml_systems: {
    key: 'ml_systems',
    label: 'ML systems',
    description: 'Training pipelines, inference, eval, drift.',
    source: 'skill',
  },
  language_craft: {
    key: 'language_craft',
    label: 'Language craft',
    description: 'Idiomatic code, type discipline, runtime gotchas.',
    source: 'skill',
  },
  system_design_skill: {
    key: 'system_design_skill',
    label: 'System design',
    description: 'Frames problem, names tradeoffs, lands on a coherent answer.',
    source: 'skill',
  },
  communication: {
    key: 'communication',
    label: 'Communication',
    description: 'Clear, structured, listens, restates.',
    source: 'communication',
  },
  ownership: {
    key: 'ownership',
    label: 'Ownership',
    description: 'Drives outcomes end-to-end, owns the failure mode.',
    source: 'ownership',
  },
  collaboration: {
    key: 'collaboration',
    label: 'Collaboration',
    description: 'Productive disagreement, takes input, shares credit.',
    source: 'collaboration',
  },
  scope_influence: {
    key: 'scope_influence',
    label: 'Scope & influence',
    description: 'Sets direction, mentors, makes peers better.',
    source: 'seniority',
  },
  motivation: {
    key: 'motivation',
    label: 'Motivation & fit',
    description: 'Knows what they want, why this team.',
    source: 'communication',
  },
};

const SENIOR_RANKS = new Set(['senior', 'staff', 'principal', 'lead']);

/** Map a skill to its rubric dimension key (or null if unknown). */
export function skillDimension(skill: string): string | null {
  const bank = SKILL_BANK[skill];
  return bank ? bank.signal : null;
}

/** Build a 4–6-dimension weighted rubric from a query plan. */
export function buildRubric(plan: QueryPlan): RubricDimension[] {
  // Skill-driven dimensions, deduped, weighted by hit-count.
  const skillDimCount: Record<string, number> = {};
  for (const s of plan.skills) {
    const d = skillDimension(s);
    if (!d) continue;
    skillDimCount[d] = (skillDimCount[d] ?? 0) + 1;
  }
  const dims: { key: string; rawWeight: number }[] = [];
  for (const [key, count] of Object.entries(skillDimCount)) {
    // Each skill-dim starts at 1.0 + 0.25 per extra skill that maps to it.
    dims.push({ key, rawWeight: 1.0 + 0.25 * (count - 1) });
  }
  // System design always present.
  dims.push({ key: 'system_design_skill', rawWeight: 1.0 });
  // Universal behaviorals — light-but-real weights.
  dims.push({ key: 'communication', rawWeight: 0.7 });
  dims.push({ key: 'ownership', rawWeight: 0.7 });
  dims.push({ key: 'collaboration', rawWeight: 0.6 });
  // Seniority bonus dim.
  if (plan.seniority && SENIOR_RANKS.has(plan.seniority)) {
    dims.push({ key: 'scope_influence', rawWeight: 1.0 });
  }

  // Cap to 7 dimensions to keep the scorecard scannable.
  const trimmed = dims.slice(0, 7);
  const total = trimmed.reduce((s, d) => s + d.rawWeight, 0) || 1;
  return trimmed
    .map(d => {
      const def = DIMENSION_DEFS[d.key];
      if (!def) return null;
      return { ...def, weight: d.rawWeight / total } as RubricDimension;
    })
    .filter((x): x is RubricDimension => x !== null);
}

// ---------- question selection ----------

/** Distribute questions across stages from skill bank + universals. */
export function buildQuestions(plan: QueryPlan): Question[] {
  const out: Question[] = [];

  // Skill questions, distributed to their natural stages.
  // Cap each skill to 3 questions to avoid one-skill bloat.
  for (const skill of plan.skills) {
    const bank = SKILL_BANK[skill];
    if (!bank) continue;
    const stages = SKILL_TO_STAGES[bank.category] ?? ['technical'];
    const picks = bank.questions.slice(0, 3);
    for (let i = 0; i < picks.length; i++) {
      const stage = stages[i % stages.length];
      out.push({
        ...picks[i],
        stage,
        source: skill,
      });
    }
  }

  // Universal questions per stage. Always include phone_screen + behavioral.
  for (const stage of STAGES) {
    for (const q of UNIVERSAL[stage]) {
      out.push({ ...q, stage, source: 'universal' });
    }
  }

  // Stable sort: stage order, then difficulty asc, then id.
  const stageRank: Record<InterviewStage, number> = {
    phone_screen: 0,
    technical: 1,
    system_design: 2,
    behavioral: 3,
  };
  out.sort((a, b) =>
    stageRank[a.stage] - stageRank[b.stage] ||
    a.difficulty - b.difficulty ||
    a.id.localeCompare(b.id),
  );
  return out;
}

// ---------- record construction ----------

export type PlanInput = {
  roleId: string;
  candidateId: number;
  plan: QueryPlan;
};

export function buildInterviewPlan(input: PlanInput): InterviewRecord {
  const rubric = buildRubric(input.plan);
  const questions = buildQuestions(input.plan);
  const now = Date.now();
  const stages: StageRecord[] = STAGES.map(stage => ({
    stage,
    status: 'planned' as const,
    scores: rubric.map(d => ({ key: d.key, rating: null })),
    signals: [],
  }));
  return {
    id: `ir_${input.roleId}_${input.candidateId}`,
    roleId: input.roleId,
    candidateId: input.candidateId,
    rubric,
    questions,
    stages,
    createdAt: now,
    updatedAt: now,
  };
}

// ---------- scorecard math ----------

/** Aggregate per-stage scores into one composite + recommendation.
 *  Only rated dims contribute; weights renormalise across them so a
 *  half-finished interview still produces a meaningful number. */
export function summarise(record: InterviewRecord): ScorecardSummary {
  // Latest rating per dim wins (stages later in the record overwrite).
  const latest: Record<string, number | null> = {};
  for (const dim of record.rubric) latest[dim.key] = null;
  for (const stage of record.stages) {
    for (const score of stage.scores) {
      if (score.rating !== null) latest[score.key] = score.rating;
    }
  }

  let totalRatedWeight = 0;
  for (const dim of record.rubric) {
    if (latest[dim.key] !== null) totalRatedWeight += dim.weight;
  }

  // Composite: Σ ((rating - 1) / 4) * (weight / totalRatedWeight) * 100
  let composite = 0;
  const perDimension = record.rubric.map(dim => {
    const r = latest[dim.key];
    const renormWeight = totalRatedWeight > 0
      ? dim.weight / totalRatedWeight
      : dim.weight;
    if (r === null) {
      return {
        key: dim.key,
        label: dim.label,
        weight: renormWeight,
        rating: null,
        impact: 0,
      };
    }
    const norm = (r - 1) / 4;
    const points = norm * renormWeight * 100;
    composite += points;
    return {
      key: dim.key,
      label: dim.label,
      weight: renormWeight,
      rating: r,
      impact: Math.round(points),
    };
  });

  composite = Math.round(composite);

  // Recommendation tier.
  let recommendation: Recommendation;
  if (composite >= 80) recommendation = 'strong_hire';
  else if (composite >= 65) recommendation = 'lean_yes';
  else if (composite >= 50) recommendation = 'mixed';
  else if (composite >= 35) recommendation = 'lean_no';
  else recommendation = 'no_hire';

  const ratedCount = Object.values(latest).filter(v => v !== null).length;
  const totalCount = record.rubric.length;

  // Aggregate signals.
  const strengths: Signal[] = [];
  const concerns: Signal[] = [];
  for (const stage of record.stages) {
    for (const sig of stage.signals) {
      (sig.kind === 'strength' ? strengths : concerns).push(sig);
    }
  }
  // newest first
  strengths.sort((a, b) => b.ts - a.ts);
  concerns.sort((a, b) => b.ts - a.ts);

  return {
    composite,
    recommendation,
    perDimension,
    ratedCount,
    totalCount,
    strengths,
    concerns,
  };
}

// ---------- localStorage persistence ----------

const KEY = 'credicrew:interviews:v1';

function readAll(): InterviewRecord[] {
  if (typeof window === 'undefined') return [];
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return [];
    const list = JSON.parse(raw);
    return Array.isArray(list) ? list : [];
  } catch {
    return [];
  }
}

function writeAll(records: InterviewRecord[]): void {
  if (typeof window === 'undefined') return;
  localStorage.setItem(KEY, JSON.stringify(records));
}

export function getInterview(roleId: string, candidateId: number): InterviewRecord | null {
  return readAll().find(r => r.roleId === roleId && r.candidateId === candidateId) ?? null;
}

export function listInterviewsForRole(roleId: string): InterviewRecord[] {
  return readAll().filter(r => r.roleId === roleId);
}

export function ensureInterview(input: PlanInput): InterviewRecord {
  const existing = getInterview(input.roleId, input.candidateId);
  if (existing) return existing;
  const plan = buildInterviewPlan(input);
  const next = [plan, ...readAll()];
  writeAll(next);
  return plan;
}

export function saveInterview(record: InterviewRecord): InterviewRecord {
  const updated: InterviewRecord = { ...record, updatedAt: Date.now() };
  const list = readAll();
  const i = list.findIndex(r => r.id === record.id);
  if (i < 0) list.unshift(updated);
  else list[i] = updated;
  writeAll(list);
  return updated;
}

export function setStageStatus(
  record: InterviewRecord,
  stage: InterviewStage,
  status: StageRecord['status'],
): InterviewRecord {
  const stages = record.stages.map(s => {
    if (s.stage !== stage) return s;
    const next: StageRecord = { ...s, status };
    if (status === 'in_progress' && !s.startedAt) next.startedAt = Date.now();
    if (status === 'done') next.completedAt = Date.now();
    return next;
  });
  return saveInterview({ ...record, stages });
}

export function setRating(
  record: InterviewRecord,
  stage: InterviewStage,
  dimKey: string,
  rating: DimensionScore['rating'],
): InterviewRecord {
  const stages = record.stages.map(s => {
    if (s.stage !== stage) return s;
    const scores = s.scores.map(sc => sc.key === dimKey ? { ...sc, rating } : sc);
    const status: StageRecord['status'] =
      s.status === 'planned' && rating !== null ? 'in_progress' : s.status;
    return { ...s, scores, status, startedAt: s.startedAt ?? (rating !== null ? Date.now() : undefined) };
  });
  return saveInterview({ ...record, stages });
}

export function setStageNotes(
  record: InterviewRecord,
  stage: InterviewStage,
  notes: string,
): InterviewRecord {
  const stages = record.stages.map(s =>
    s.stage === stage ? { ...s, notes } : s,
  );
  return saveInterview({ ...record, stages });
}

export function addSignal(
  record: InterviewRecord,
  stage: InterviewStage,
  kind: Signal['kind'],
  text: string,
): InterviewRecord {
  const trimmed = text.trim();
  if (!trimmed) return record;
  const sig: Signal = { kind, text: trimmed, ts: Date.now() };
  const stages = record.stages.map(s =>
    s.stage === stage ? { ...s, signals: [sig, ...s.signals] } : s,
  );
  return saveInterview({ ...record, stages });
}

export function removeSignal(
  record: InterviewRecord,
  stage: InterviewStage,
  ts: number,
): InterviewRecord {
  const stages = record.stages.map(s =>
    s.stage === stage ? { ...s, signals: s.signals.filter(x => x.ts !== ts) } : s,
  );
  return saveInterview({ ...record, stages });
}

export function deleteInterview(roleId: string, candidateId: number): void {
  writeAll(readAll().filter(r => !(r.roleId === roleId && r.candidateId === candidateId)));
}

// ---------- candidate-aware label sugar ----------

/** Optional helper: a one-line greeting line a UI can drop above the
 *  first stage. Pure function, no I/O. Mirrored on backend. */
export function buildIntroLine(plan: QueryPlan, c: CandidateLike): string {
  const name = (c.name ?? 'the candidate').split(' ')[0];
  const role = plan.seniority ? `${plan.seniority} ${plan.skills[0] ?? ''}`.trim() : (plan.skills[0] ?? 'engineer');
  return `${name} · ${role}${plan.location ? ` · ${plan.location}` : ''}`;
}
