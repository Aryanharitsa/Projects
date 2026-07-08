// Interviewer Handoff Composer (Day 77 · Brief).
//
// Every prior Credicrew surface answers *who to interview* — Discover
// ranks who to talk to, Roles maps them through the pipeline, Interview
// Kit builds the rubric and question bank, Decision Studio aggregates
// what came out. What nobody has ever built is the 60-second brief the
// interviewer actually opens the moment before the call: what to probe,
// what to skip, which of THIS candidate's angles pays into THIS stage's
// rubric gaps, and what red flags to watch for.
//
// This module composes that brief deterministically from data Credicrew
// already owns: the role's QueryPlan, the candidate, the InterviewRecord
// (if one exists), and the target stage. Same input bytes → same brief
// bytes. Mirrored in `backend/app/services/brief.py` so a programmatic
// client gets identical output.
//
// No LLM, no network. All pure functions.
//
// ─────────────────────────────────────────────────────────────────────────

import type { CandidateLike, MatchResult, QueryPlan } from '@/lib/match';
import { matchCandidate } from '@/lib/match';
import type {
  InterviewRecord,
  InterviewStage,
  RubricDimension,
} from '@/lib/interview';
import {
  STAGES,
  STAGE_LABEL,
  buildQuestions,
  buildRubric,
} from '@/lib/interview';

// ───── physics constants (mirrored 1:1 with brief.py) ─────

export const TIME_BUDGET_BY_STAGE: Record<InterviewStage, number> = {
  phone_screen: 30,
  technical: 60,
  system_design: 60,
  behavioral: 45,
};

/** Stage-to-dim affinity — how much a dim belongs in a given stage.
 *  Rows sum to ~1; every stage picks its own weighting of the 12 dims. */
const STAGE_AFFINITY: Record<InterviewStage, Record<string, number>> = {
  phone_screen: {
    communication: 0.35,
    motivation: 0.30,
    collaboration: 0.10,
    ownership: 0.10,
    frontend_depth: 0.03,
    backend_depth: 0.03,
    data_systems: 0.03,
    cloud_infra: 0.02,
    ml_systems: 0.02,
    language_craft: 0.02,
  },
  technical: {
    frontend_depth: 0.20,
    backend_depth: 0.20,
    data_systems: 0.15,
    language_craft: 0.15,
    ml_systems: 0.10,
    cloud_infra: 0.08,
    communication: 0.06,
    ownership: 0.06,
  },
  system_design: {
    system_design_skill: 0.35,
    backend_depth: 0.15,
    data_systems: 0.15,
    cloud_infra: 0.15,
    frontend_depth: 0.06,
    ml_systems: 0.06,
    scope_influence: 0.05,
    communication: 0.03,
  },
  behavioral: {
    collaboration: 0.30,
    ownership: 0.25,
    communication: 0.20,
    motivation: 0.15,
    scope_influence: 0.10,
  },
};

export const COVERED_RATING_FLOOR = 4;
export const PARTIAL_MIN_RATING = 3;
export const DIM_FOCUS_WEIGHT_FLOOR = 0.05;
export const MAX_FOCUS_DIMS = 4;
export const MAX_QUESTIONS = 5;
export const MAX_PROBES = 6;
export const MAX_TALKING = 3;

// ───── types ─────

export type CoverageState = 'covered' | 'partial' | 'open';

export const COVERAGE_HEX: Record<CoverageState, string> = {
  covered: '#22c55e',
  partial: '#f59e0b',
  open: '#f43f5e',
};

export const COVERAGE_LABEL: Record<CoverageState, string> = {
  covered: 'Covered',
  partial: 'Partial signal',
  open: 'Open',
};

export type DimStatus = {
  key: string;
  label: string;
  description: string;
  weight: number;
  state: CoverageState;
  bestRating: number | null;
  ratedInStages: InterviewStage[];
};

export type FocusDim = {
  key: string;
  label: string;
  weight: number;
  gap: number;
  affinity: number;
  priority: number;
  minutes: number;
  whyLine: string;
};

export type ProbeKind =
  | 'missing_skill'
  | 'matched_deepen'
  | 'seniority_scope'
  | 'location_fit'
  | 'motivation'
  | 'ownership_probe';

export const PROBE_HEX: Record<ProbeKind, string> = {
  missing_skill: '#f43f5e',
  matched_deepen: '#22c55e',
  seniority_scope: '#a855f7',
  location_fit: '#0ea5e9',
  motivation: '#f59e0b',
  ownership_probe: '#6366f1',
};

export const PROBE_LABEL: Record<ProbeKind, string> = {
  missing_skill: 'Missing skill',
  matched_deepen: 'Deepen',
  seniority_scope: 'Scope',
  location_fit: 'Location',
  motivation: 'Motivation',
  ownership_probe: 'Ownership',
};

export type Probe = {
  kind: ProbeKind;
  angle: string;
  reason: string;
  signalDim?: string;
};

export type TalkingPoint = {
  hook: string;
  reference: string;
};

export type BriefFlag =
  | 'low_match_score'
  | 'missing_required_skill'
  | 'seniority_mismatch'
  | 'location_partial'
  | 'thin_signal'
  | 'no_prior_stages'
  | 'key_dim_open';

export const FLAG_LABEL: Record<BriefFlag, string> = {
  low_match_score: 'Low match score',
  missing_required_skill: 'Missing required skill',
  seniority_mismatch: 'Seniority mismatch',
  location_partial: 'Location partial',
  thin_signal: 'Thin prior signal',
  no_prior_stages: 'No prior stages',
  key_dim_open: 'Key dim still open',
};

export const FLAG_TONE: Record<BriefFlag, string> = {
  low_match_score: 'rose',
  missing_required_skill: 'rose',
  seniority_mismatch: 'amber',
  location_partial: 'sky',
  thin_signal: 'amber',
  no_prior_stages: 'slate',
  key_dim_open: 'rose',
};

export type BriefFlagEntry = {
  kind: BriefFlag;
  label: string;
  detail: string;
};

export type BriefQuestion = {
  id: string;
  prompt: string;
  followup?: string;
  signalDim: string;
  difficulty: 1 | 2 | 3 | 4;
  source: string;
  priority: number;
};

export type BriefBundle = {
  version: 'credicrew.brief.v1';
  roleId: string;
  roleName: string;
  candidateId: number;
  candidateName: string;
  stage: InterviewStage;
  stageLabel: string;
  intro: string;
  headline: string;
  match: MatchResult;
  timeBudgetMin: number;
  dimStatuses: DimStatus[];
  focus: FocusDim[];
  probes: Probe[];
  talkingPoints: TalkingPoint[];
  questions: BriefQuestion[];
  doNotReCover: DimStatus[];
  flags: BriefFlagEntry[];
  tiles: { key: string; label: string; value: string; sub?: string }[];
  criticality: number;
  decisionConfidence: number;
  issuedAt: number;
  rubric: RubricDimension[];
};

// ───── helpers ─────

function clamp(x: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, x));
}

function round(x: number, n = 0): number {
  const p = Math.pow(10, n);
  return Math.round(x * p) / p;
}

function firstName(name?: string): string {
  return (name ?? 'the candidate').split(/\s+/)[0] ?? 'candidate';
}

const SENIORITY_TIER: Record<string, number> = {
  intern: 0,
  junior: 1,
  mid: 2,
  senior: 3,
  lead: 3,
  staff: 4,
  principal: 5,
};

function tier(rank?: string | null): number | null {
  if (!rank) return null;
  const t = SENIORITY_TIER[rank.toLowerCase()];
  return t === undefined ? null : t;
}

// ───── dim coverage ─────

export function analyzeCoverage(
  rubric: RubricDimension[],
  interview: InterviewRecord | null,
): DimStatus[] {
  const out: DimStatus[] = [];
  for (const dim of rubric) {
    let best: number | null = null;
    const staged: InterviewStage[] = [];
    if (interview) {
      for (const stage of interview.stages) {
        for (const sc of stage.scores) {
          if (sc.key === dim.key && sc.rating !== null) {
            if (best === null || sc.rating > best) best = sc.rating;
            if (!staged.includes(stage.stage)) staged.push(stage.stage);
          }
        }
      }
    }
    let state: CoverageState;
    if (best !== null && best >= COVERED_RATING_FLOOR) state = 'covered';
    else if (best !== null && best >= PARTIAL_MIN_RATING) state = 'partial';
    else state = 'open';
    out.push({
      key: dim.key,
      label: dim.label,
      description: dim.description,
      weight: dim.weight,
      state,
      bestRating: best,
      ratedInStages: staged,
    });
  }
  return out;
}

// ───── focus (which dims THIS stage should probe) ─────

function stateGap(state: CoverageState): number {
  if (state === 'covered') return 0;
  if (state === 'partial') return 0.4;
  return 1;
}

export function pickFocusDims(
  statuses: DimStatus[],
  stage: InterviewStage,
): FocusDim[] {
  const affinity = STAGE_AFFINITY[stage] ?? {};
  const scored = statuses
    .map(s => {
      const aff = affinity[s.key] ?? 0.02;
      const gap = stateGap(s.state);
      const priority = s.weight * gap * (0.5 + aff);
      return { dim: s, aff, gap, priority };
    })
    .filter(x => x.priority > 0)
    .sort((a, b) => b.priority - a.priority);

  const top = scored.slice(0, MAX_FOCUS_DIMS);
  const totalPriority = top.reduce((s, x) => s + x.priority, 0) || 1;
  const budget = TIME_BUDGET_BY_STAGE[stage];

  return top.map(x => {
    const share = x.priority / totalPriority;
    const minutes = Math.max(5, Math.round(share * budget * 0.85));
    return {
      key: x.dim.key,
      label: x.dim.label,
      weight: round(x.dim.weight, 3),
      gap: round(x.gap, 3),
      affinity: round(x.aff, 3),
      priority: round(x.priority, 4),
      minutes,
      whyLine: whyLineForFocus(x.dim, stage, x.aff),
    };
  });
}

function whyLineForFocus(
  dim: DimStatus,
  stage: InterviewStage,
  aff: number,
): string {
  const stageWord = STAGE_LABEL[stage].toLowerCase();
  const stateWord =
    dim.state === 'open'
      ? 'no prior signal'
      : dim.state === 'partial'
      ? `only ${dim.bestRating}/5 so far`
      : 'already saturated';
  const affWord =
    aff >= 0.2 ? 'core to this stage' : aff >= 0.1 ? 'fits this stage' : 'adjacent to this stage';
  return `${dim.label.toLowerCase()} — ${stateWord}; ${affWord} (${stageWord}).`;
}

// ───── probes (specific angles) ─────

export function buildProbes(
  plan: QueryPlan,
  candidate: CandidateLike,
  match: MatchResult,
  stage: InterviewStage,
): Probe[] {
  const out: Probe[] = [];
  const bag = new Set(
    [...(candidate.tags ?? []), ...(candidate.keywords ?? [])]
      .map(t => t.toLowerCase()),
  );

  // Missing-skill probes — where the candidate looks short.
  for (const skill of match.missingSkills.slice(0, 3)) {
    if (stage === 'behavioral') break;
    out.push({
      kind: 'missing_skill',
      angle: `Probe ${skill} familiarity — not on resume, but plan-required.`,
      reason: `Candidate did not list ${skill}; ask for the closest thing they have shipped and how long the ramp would be.`,
      signalDim: dimForSkill(skill),
    });
  }

  // Matched-skill deep-dive — where they signal fit; go deeper.
  for (const skill of match.matchedSkills.slice(0, 3)) {
    if (stage === 'behavioral') break;
    out.push({
      kind: 'matched_deepen',
      angle: `Deepen ${skill} — candidate signals it; test depth vs. name-drop.`,
      reason: `${skill} appears on candidate profile (${bag.has(skill) ? 'tag' : 'headline'}); probe the hardest bug they shipped in it.`,
      signalDim: dimForSkill(skill),
    });
  }

  // Seniority scope probe.
  const wantTier = tier(plan.seniority ?? undefined);
  const haveTier = tier(match.seniority.candidate ?? undefined);
  if (
    stage === 'behavioral' || stage === 'system_design' || stage === 'phone_screen'
  ) {
    if (wantTier !== null) {
      if (haveTier === null) {
        out.push({
          kind: 'seniority_scope',
          angle: `Establish scope — plan wants ${plan.seniority}; candidate seniority unread.`,
          reason: `Ask about the largest project they owned end-to-end and how many people they influenced.`,
          signalDim: 'scope_influence',
        });
      } else if (haveTier < wantTier) {
        out.push({
          kind: 'seniority_scope',
          angle: `Stretch check — candidate presents ${match.seniority.candidate}, plan wants ${plan.seniority}.`,
          reason: `Ask how they would ramp into a role one tier above their current — do they name specific gaps or wave vaguely?`,
          signalDim: 'scope_influence',
        });
      } else if (haveTier > wantTier) {
        out.push({
          kind: 'seniority_scope',
          angle: `Over-tier — candidate ${match.seniority.candidate}, plan ${plan.seniority}; probe motivation.`,
          reason: `Ask why the level down — comp, learning, life? A crisp answer is a good sign.`,
          signalDim: 'motivation',
        });
      }
    }
  }

  // Location probe (only phone screen or behavioral).
  if ((stage === 'phone_screen' || stage === 'behavioral')) {
    if (match.location.match === 'partial') {
      out.push({
        kind: 'location_fit',
        angle: `Location — hybrid signal; confirm expectation.`,
        reason: `Ask how many onsite days they can hit and their commute reality.`,
        signalDim: 'motivation',
      });
    } else if (match.location.match === 'none' && plan.location) {
      out.push({
        kind: 'location_fit',
        angle: `Location gap — candidate ${candidate.location ?? 'elsewhere'}, plan ${plan.location}.`,
        reason: `Confirm relocation appetite before spending an interview loop on this candidate.`,
        signalDim: 'motivation',
      });
    }
  }

  // Motivation probe on phone screen if none of the above fired.
  if (stage === 'phone_screen' && out.length < 2) {
    out.push({
      kind: 'motivation',
      angle: `Motivation — why THIS team, why now?`,
      reason: `Listen for a specific thing they read about the team, not a generic "growth" answer.`,
      signalDim: 'motivation',
    });
  }

  // Ownership probe on behavioral.
  if (stage === 'behavioral') {
    out.push({
      kind: 'ownership_probe',
      angle: `Ownership — walk-through of a shipped failure they owned.`,
      reason: `Look for first-person accountability + a specific prevention step, not blame routing.`,
      signalDim: 'ownership',
    });
  }

  return out.slice(0, MAX_PROBES);
}

function dimForSkill(skill: string): string {
  const map: Record<string, string> = {
    react: 'frontend_depth',
    'next.js': 'frontend_depth',
    vue: 'frontend_depth',
    svelte: 'frontend_depth',
    angular: 'frontend_depth',
    tailwind: 'frontend_depth',
    typescript: 'language_craft',
    javascript: 'language_craft',
    python: 'language_craft',
    go: 'language_craft',
    rust: 'language_craft',
    java: 'language_craft',
    fastapi: 'backend_depth',
    flask: 'backend_depth',
    django: 'backend_depth',
    express: 'backend_depth',
    'nest.js': 'backend_depth',
    postgres: 'data_systems',
    mysql: 'data_systems',
    mongodb: 'data_systems',
    redis: 'data_systems',
    kafka: 'data_systems',
    rabbitmq: 'data_systems',
    aws: 'cloud_infra',
    gcp: 'cloud_infra',
    azure: 'cloud_infra',
    docker: 'cloud_infra',
    kubernetes: 'cloud_infra',
    terraform: 'cloud_infra',
    pytorch: 'ml_systems',
    tensorflow: 'ml_systems',
    llm: 'ml_systems',
    nlp: 'ml_systems',
    ml: 'ml_systems',
  };
  return map[skill] ?? 'language_craft';
}

// ───── talking points (personalization for warm-up) ─────

export function buildTalkingPoints(
  candidate: CandidateLike,
  plan: QueryPlan,
): TalkingPoint[] {
  const out: TalkingPoint[] = [];
  const title = (candidate.role ?? '').trim();
  const loc = (candidate.location ?? '').trim();

  if (title) {
    out.push({
      hook: `Currently a ${title}`,
      reference: `Anchor for the "why leave / why now" — reference the seniority and stack fit.`,
    });
  }
  const tags = (candidate.tags ?? []).slice(0, 2);
  if (tags.length) {
    out.push({
      hook: `Public focus: ${tags.join(' · ')}`,
      reference: `Reference before the technical dive — signals you actually read their profile.`,
    });
  }
  const overlap = (candidate.tags ?? []).filter(t =>
    plan.skills.includes(t.toLowerCase()),
  );
  if (overlap.length) {
    out.push({
      hook: `Direct stack overlap: ${overlap.slice(0, 2).join(', ')}`,
      reference: `Skip the surface intro on these — go one layer deeper right away.`,
    });
  }
  if (out.length < MAX_TALKING && loc) {
    out.push({
      hook: `Based in ${loc}`,
      reference: `Confirm the office-day expectation without making it awkward.`,
    });
  }
  return out.slice(0, MAX_TALKING);
}

// ───── question selection ─────

export function pickQuestions(
  plan: QueryPlan,
  focus: FocusDim[],
  stage: InterviewStage,
): BriefQuestion[] {
  const bank = buildQuestions(plan).filter(q => q.stage === stage);
  const focusKeys = new Set(focus.map(f => f.key));
  const weightByDim: Record<string, number> = {};
  for (const f of focus) weightByDim[f.key] = f.priority;

  const scored = bank.map(q => {
    const w = weightByDim[q.signal] ?? 0;
    const stageAff = STAGE_AFFINITY[stage][q.signal] ?? 0.02;
    // Difficulty sweet-spot per stage: phone_screen=1, technical=3, sd=3, behavioral=2.
    const target = stage === 'phone_screen' ? 1 : stage === 'behavioral' ? 2 : 3;
    const diffFit = 1 - Math.abs(q.difficulty - target) / 4;
    const priority = w * 0.55 + stageAff * 0.25 + diffFit * 0.20;
    return { q, priority, inFocus: focusKeys.has(q.signal) };
  });

  scored.sort((a, b) => {
    if (a.inFocus !== b.inFocus) return a.inFocus ? -1 : 1;
    return b.priority - a.priority;
  });

  return scored.slice(0, MAX_QUESTIONS).map(({ q, priority }) => ({
    id: q.id,
    prompt: q.prompt,
    followup: q.followups[0],
    signalDim: q.signal,
    difficulty: q.difficulty,
    source: q.source,
    priority: round(priority, 4),
  }));
}

// ───── flags & metrics ─────

function buildFlags(
  plan: QueryPlan,
  candidate: CandidateLike,
  match: MatchResult,
  statuses: DimStatus[],
  interview: InterviewRecord | null,
): BriefFlagEntry[] {
  const out: BriefFlagEntry[] = [];
  if (match.score < 60) {
    out.push({
      kind: 'low_match_score',
      label: FLAG_LABEL.low_match_score,
      detail: `Composite ${match.score}/100 — verify the shortlist decision before spending panel time.`,
    });
  }
  if (match.missingSkills.length >= 2 && plan.skills.length) {
    out.push({
      kind: 'missing_required_skill',
      label: FLAG_LABEL.missing_required_skill,
      detail: `Missing ${match.missingSkills.slice(0, 3).join(', ')} — probe adjacency, not just presence.`,
    });
  }
  if (
    plan.seniority &&
    match.seniority.candidate &&
    !match.seniority.match
  ) {
    out.push({
      kind: 'seniority_mismatch',
      label: FLAG_LABEL.seniority_mismatch,
      detail: `Candidate ${match.seniority.candidate}, plan ${plan.seniority} — surface scope explicitly.`,
    });
  }
  if (match.location.match === 'partial') {
    out.push({
      kind: 'location_partial',
      label: FLAG_LABEL.location_partial,
      detail: `Hybrid flag on location — confirm before offer stage.`,
    });
  }
  const openHighWeight = statuses
    .filter(s => s.state === 'open' && s.weight >= 0.15)
    .slice(0, 2);
  if (openHighWeight.length) {
    out.push({
      kind: 'key_dim_open',
      label: FLAG_LABEL.key_dim_open,
      detail: `High-weight dim${openHighWeight.length > 1 ? 's' : ''} still open: ${openHighWeight.map(s => s.label).join(', ')}.`,
    });
  }
  if (!interview) {
    out.push({
      kind: 'no_prior_stages',
      label: FLAG_LABEL.no_prior_stages,
      detail: `No prior stage on record — this is the first pass.`,
    });
  } else {
    const rated = statuses.filter(s => s.state !== 'open').length;
    if (rated <= 1 && statuses.length >= 4) {
      out.push({
        kind: 'thin_signal',
        label: FLAG_LABEL.thin_signal,
        detail: `Only ${rated}/${statuses.length} dims have signal — treat this like a fresh pass.`,
      });
    }
  }
  return out;
}

function metrics(
  statuses: DimStatus[],
  focus: FocusDim[],
  match: MatchResult,
): { criticality: number; decisionConfidence: number } {
  const totalWeight = statuses.reduce((s, x) => s + x.weight, 0) || 1;
  const coveredWeight = statuses
    .filter(s => s.state === 'covered')
    .reduce((s, x) => s + x.weight, 0);
  const partialWeight = statuses
    .filter(s => s.state === 'partial')
    .reduce((s, x) => s + x.weight, 0);
  const decisionConfidence = Math.round(
    ((coveredWeight + partialWeight * 0.5) / totalWeight) * 100,
  );
  const focusWeight = focus.reduce((s, x) => s + x.weight, 0);
  const scoreLever = match.score < 60 ? 0.35 : match.score < 75 ? 0.20 : 0.10;
  const criticality = Math.round(
    clamp(focusWeight * 0.7 + scoreLever + (100 - decisionConfidence) / 400, 0, 1) *
      100,
  );
  return { criticality, decisionConfidence };
}

// ───── public entrypoint ─────

export type ComposeInput = {
  role: { id: string; name: string; plan: QueryPlan };
  candidate: CandidateLike & { id: number };
  stage: InterviewStage;
  interview?: InterviewRecord | null;
  now?: number;
};

export function composeBrief(input: ComposeInput): BriefBundle {
  const { role, candidate, stage } = input;
  const interview = input.interview ?? null;
  const rubric = interview?.rubric ?? buildRubric(role.plan);
  const match = matchCandidate(role.plan, candidate);
  const statuses = analyzeCoverage(rubric, interview);
  const focus = pickFocusDims(statuses, stage);
  const probes = buildProbes(role.plan, candidate, match, stage);
  const talking = buildTalkingPoints(candidate, role.plan);
  const questions = pickQuestions(role.plan, focus, stage);
  const doNotReCover = statuses.filter(s => s.state === 'covered');
  const flags = buildFlags(role.plan, candidate, match, statuses, interview);
  const m = metrics(statuses, focus, match);
  const budget = TIME_BUDGET_BY_STAGE[stage];
  const focusMinutes = focus.reduce((s, x) => s + x.minutes, 0);

  const intro = (() => {
    const parts = [firstName(candidate.name), candidate.role ?? 'engineer'];
    if (candidate.location) parts.push(candidate.location);
    return parts.filter(Boolean).join(' · ');
  })();

  const headline = (() => {
    const fn = firstName(candidate.name);
    const rp = role.plan.seniority
      ? `${role.plan.seniority} ${role.plan.skills[0] ?? role.name}`
      : role.name;
    return `${STAGE_LABEL[stage]} · ${fn} → ${rp}`;
  })();

  const tiles: BriefBundle['tiles'] = [
    {
      key: 'match',
      label: 'Composite match',
      value: `${match.score}/100`,
      sub: `${match.matchedSkills.length}/${role.plan.skills.length || 0} skills`,
    },
    {
      key: 'covered',
      label: 'Dims with signal',
      value: `${statuses.filter(s => s.state !== 'open').length}/${statuses.length}`,
      sub: `${statuses.filter(s => s.state === 'covered').length} saturated`,
    },
    {
      key: 'focus',
      label: 'Focus minutes',
      value: `${focusMinutes}/${budget}m`,
      sub: `${focus.length} focus dim${focus.length === 1 ? '' : 's'}`,
    },
    {
      key: 'critic',
      label: 'Criticality',
      value: `${m.criticality}/100`,
      sub: `decision ${m.decisionConfidence}%`,
    },
  ];

  return {
    version: 'credicrew.brief.v1',
    roleId: role.id,
    roleName: role.name,
    candidateId: candidate.id,
    candidateName: candidate.name ?? 'Candidate',
    stage,
    stageLabel: STAGE_LABEL[stage],
    intro,
    headline,
    match,
    timeBudgetMin: budget,
    dimStatuses: statuses,
    focus,
    probes,
    talkingPoints: talking,
    questions,
    doNotReCover,
    flags,
    tiles,
    criticality: m.criticality,
    decisionConfidence: m.decisionConfidence,
    issuedAt: input.now ?? Date.now(),
    rubric,
  };
}

// ───── markdown / json exports ─────

export function toMarkdown(brief: BriefBundle): string {
  const lines: string[] = [];
  lines.push(`# ${brief.headline}`);
  lines.push('');
  lines.push(
    `_${brief.intro} · match ${brief.match.score}/100 · ${brief.timeBudgetMin}m budget · decision ${brief.decisionConfidence}%_`,
  );
  lines.push('');
  lines.push('## Focus this stage');
  if (brief.focus.length === 0) {
    lines.push('_All dims already covered. Use the stage to break ties._');
  } else {
    for (const f of brief.focus) {
      lines.push(`- **${f.label}** (${Math.round(f.weight * 100)}% weight · ${f.minutes}m) — ${f.whyLine}`);
    }
  }
  lines.push('');
  lines.push('## Signals to probe');
  if (brief.probes.length === 0) {
    lines.push('_No candidate-specific probes surfaced._');
  } else {
    for (const p of brief.probes) {
      lines.push(`- **${PROBE_LABEL[p.kind]}** — ${p.angle}`);
      lines.push(`  · ${p.reason}`);
    }
  }
  lines.push('');
  lines.push('## Questions to ask');
  if (brief.questions.length === 0) {
    lines.push('_No stage-fit questions available for this plan._');
  } else {
    for (let i = 0; i < brief.questions.length; i++) {
      const q = brief.questions[i];
      lines.push(`${i + 1}. **${q.prompt}**  \n   _Signal: ${q.signalDim} · difficulty ${q.difficulty} · from ${q.source}_`);
      if (q.followup) lines.push(`   ↳ ${q.followup}`);
    }
  }
  lines.push('');
  if (brief.doNotReCover.length) {
    lines.push('## Skip — already covered');
    for (const d of brief.doNotReCover) {
      lines.push(`- ~~${d.label}~~ (rated ${d.bestRating}/5 in ${d.ratedInStages.map(s => STAGE_LABEL[s]).join(', ') || 'prior stages'})`);
    }
    lines.push('');
  }
  if (brief.talkingPoints.length) {
    lines.push('## Warm-up hooks');
    for (const t of brief.talkingPoints) {
      lines.push(`- **${t.hook}** — ${t.reference}`);
    }
    lines.push('');
  }
  if (brief.flags.length) {
    lines.push('## Red flags');
    for (const f of brief.flags) {
      lines.push(`- **${f.label}** — ${f.detail}`);
    }
    lines.push('');
  }
  lines.push('---');
  lines.push(
    `Issued by Credicrew · brief.v1 · role \`${brief.roleId}\` · candidate \`${brief.candidateId}\``,
  );
  return lines.join('\n');
}

export function defaults(): {
  timeBudgetByStage: Record<InterviewStage, number>;
  coveredRatingFloor: number;
  partialMinRating: number;
  maxFocusDims: number;
  maxQuestions: number;
  maxProbes: number;
  stageAffinity: Record<InterviewStage, Record<string, number>>;
  stages: InterviewStage[];
} {
  return {
    timeBudgetByStage: { ...TIME_BUDGET_BY_STAGE },
    coveredRatingFloor: COVERED_RATING_FLOOR,
    partialMinRating: PARTIAL_MIN_RATING,
    maxFocusDims: MAX_FOCUS_DIMS,
    maxQuestions: MAX_QUESTIONS,
    maxProbes: MAX_PROBES,
    stageAffinity: STAGE_AFFINITY,
    stages: STAGES,
  };
}
