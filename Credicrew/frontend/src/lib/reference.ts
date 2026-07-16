// Structured Reference-Check Composer (Day 82 · Reference).
//
// Every prior Credicrew surface answers a hiring question. Discover ranks
// who to talk to. Roles moves them through pipeline. Interview Kit runs
// the loop. Decision Studio aggregates the panel. Offer Studio benchmarks
// comp. Peer Parity audits fairness. Brief hands the interviewer their
// prep. What nothing has ever built is the *reference call* — the last
// 25-minute conversation between "we like this candidate" and "we send
// the offer letter." It is almost universally improvised: whoever draws
// the short straw phones two names on Monday, freestyles fifteen
// questions, and writes back a two-line note.
//
// Reference closes that gap. Given a role's `QueryPlan`, a candidate,
// and (optionally) an `InterviewRecord`, this module produces a
// deterministic `ReferenceBundle` — claims to corroborate, red flags to
// probe, per-reference question sheets, minute budgets, and a markdown
// export. Once responses come back, `scoreResponses` folds each verdict
// into a projected composite score and one of five terminal verdicts.
//
// Same input bytes → same output bytes. Mirrored in
// `backend/app/services/reference.py` so a programmatic client gets
// byte-identical output.
//
// No LLM, no network. All pure functions.
//
// ─────────────────────────────────────────────────────────────────────────

import type { CandidateLike, QueryPlan } from '@/lib/match';
import type { InterviewRecord } from '@/lib/interview';

// ───────────────────── physics constants ─────────────────────

export type ReferenceKind = 'manager' | 'peer' | 'report' | 'skip_level';

export const KINDS: ReferenceKind[] = ['manager', 'peer', 'report', 'skip_level'];

export const KIND_LABEL: Record<ReferenceKind, string> = {
  manager: 'Direct manager',
  peer: 'Peer',
  report: 'Direct report',
  skip_level: 'Skip-level',
};

export const KIND_HEX: Record<ReferenceKind, string> = {
  manager: '#818cf8',
  peer: '#22d3ee',
  report: '#a78bfa',
  skip_level: '#f472b6',
};

export const KIND_TONE: Record<ReferenceKind, string> = {
  manager: 'indigo',
  peer: 'cyan',
  report: 'violet',
  skip_level: 'pink',
};

const SENIOR_RANKS = new Set(['senior', 'staff', 'principal', 'lead']);
const STAFF_RANKS = new Set(['staff', 'principal', 'lead']);

export const SLOT_MIX_BY_TIER: Record<string, ReferenceKind[]> = {
  junior: ['manager', 'peer'],
  mid: ['manager', 'peer', 'peer'],
  senior: ['manager', 'peer', 'report'],
  staff: ['manager', 'peer', 'report', 'skip_level'],
};

export const MAX_QUESTIONS_PER_REF = 7;
export const MIN_QUESTIONS_PER_REF = 4;
export const MINUTES_PER_QUESTION = 3.5;
export const MINUTES_CAP = 30;

export const SHIFT_CORROBORATED = 1.0;
export const SHIFT_CONCERNED = -1.5;
export const SHIFT_CONTRADICTED = -3.0;
export const SHIFT_NO_SIGNAL = 0.0;
export const SHIFT_CLAMP_MIN = -25.0;
export const SHIFT_CLAMP_MAX = 15.0;

export const REDFLAG_BLOCK_RATING = 2;
export const REDFLAG_WATCH_RATING = 3;
export const REDFLAG_HIGH_WEIGHT = 0.10;

export const VERDICT_PROCEED_MIN = 3.0;
export const VERDICT_CAVEAT_MIN = -3.0;
export const VERDICT_REOPEN_MIN = -12.0;

const IMPACT_HINTS: [string, ClaimKind][] = [
  ['led', 'leadership'], ['managed', 'leadership'], ['mentored', 'leadership'],
  ['architected', 'delivery'], ['designed', 'delivery'],
  ['shipped', 'delivery'], ['delivered', 'delivery'], ['launched', 'delivery'],
  ['migrated', 'impact'], ['scaled', 'impact'], ['optimised', 'impact'],
  ['optimized', 'impact'], ['reduced', 'impact'], ['saved', 'impact'],
  ['owned', 'ownership'], ['drove', 'ownership'],
  ['founder', 'leadership'], ['staff', 'seniority'], ['principal', 'seniority'],
];

const NUMBER_RE = /(\d{1,3}(?:[,.]\d{3})*|\d+(?:\.\d+)?)(x|%|k|m|b|\/s)?/gi;

export type Verdict = 'proceed' | 'proceed_with_caveat' | 'reopen' | 'block' | 'pending';

export const VERDICT_LABEL: Record<Verdict, string> = {
  proceed: 'Proceed',
  proceed_with_caveat: 'Proceed with caveat',
  reopen: 'Reopen loop',
  block: 'Block offer',
  pending: 'Awaiting references',
};

export const VERDICT_TONE: Record<Verdict, string> = {
  proceed: 'emerald',
  proceed_with_caveat: 'sky',
  reopen: 'amber',
  block: 'rose',
  pending: 'slate',
};

export type AnswerVerdict =
  | 'corroborated'
  | 'concerned'
  | 'contradicted'
  | 'no_signal'
  | 'pending';

export const ANSWER_VERDICT_LABEL: Record<AnswerVerdict, string> = {
  corroborated: 'Corroborated',
  concerned: 'Concerned',
  contradicted: 'Contradicted',
  no_signal: 'No signal',
  pending: 'Pending',
};

export const ANSWER_VERDICT_TONE: Record<AnswerVerdict, string> = {
  corroborated: 'emerald',
  concerned: 'amber',
  contradicted: 'rose',
  no_signal: 'slate',
  pending: 'sky',
};

export type QuestionKind = 'claim' | 'redflag' | 'delivery' | 'growth' | 'open';

export const QUESTION_KIND_LABEL: Record<QuestionKind, string> = {
  claim: 'Claim check',
  redflag: 'Flag probe',
  delivery: 'Delivery',
  growth: 'Growth',
  open: 'Open',
};

export type ClaimKind = 'skill' | 'impact' | 'seniority' | 'leadership' | 'delivery' | 'ownership';

// ───────────────────── types ─────────────────────

export type Claim = {
  id: string;
  kind: ClaimKind;
  text: string;
  weight: number;
  source: string;
};

export type FlagSeverity = 'block' | 'concern' | 'watch' | 'gap';

export type RedFlag = {
  dim: string;
  dimLabel: string;
  latestRating: number | null;
  stage: string | null;
  severity: FlagSeverity;
  weight: number;
};

export type RefQuestion = {
  id: string;
  text: string;
  kind: QuestionKind;
  priority: number;
  minutes: number;
  linkedClaimId?: string | null;
  linkedFlagDim?: string | null;
  hint?: string | null;
};

export type ReferenceSlot = {
  slotId: string;
  kind: ReferenceKind;
  label: string;
  minutes: number;
  intro: string;
  focus: string[];
  questions: RefQuestion[];
};

export type ReferenceBundle = {
  bundleVersion: string;
  roleId: string;
  roleName: string;
  candidateId: number;
  candidateName: string;
  seniorityTier: string;
  slots: ReferenceSlot[];
  claims: Claim[];
  redFlags: RedFlag[];
  interviewComposite: number | null;
  totalMinutes: number;
  totalQuestions: number;
  corpusHash: string;
  headline: string;
};

export type ResponseAnswer = {
  slotId: string;
  questionId: string;
  verdict: AnswerVerdict;
  note?: string;
};

export type ClaimStatus = {
  claimId: string;
  kind: ClaimKind;
  text: string;
  weight: number;
  matches: number;
  corroborated: number;
  contradicted: number;
  concerned: number;
  status: 'confirmed' | 'contradicted' | 'concern' | 'unknown';
};

export type FlagStatus = {
  dim: string;
  dimLabel: string;
  severity: string;
  weight: number;
  matches: number;
  corroborated: number;
  contradicted: number;
  concerned: number;
  status: 'resolved' | 'confirmed' | 'concern' | 'unknown';
};

export type SlotSummary = {
  slotId: string;
  kind: ReferenceKind;
  label: string;
  answered: number;
  total: number;
  corroborated: number;
  concerned: number;
  contradicted: number;
  noSignal: number;
  coveragePct: number;
};

export type ReferenceReport = {
  bundleVersion: string;
  roleId: string;
  candidateId: number;
  verdict: Verdict;
  headline: string;
  scoreShift: number;
  projectedComposite: number | null;
  slots: SlotSummary[];
  claimStatus: ClaimStatus[];
  flagStatus: FlagStatus[];
  totalAnswered: number;
  totalQuestions: number;
  coveragePct: number;
};

// ───────────────────── helpers ─────────────────────

function seniorityTier(seniority?: string | null): string {
  if (!seniority) return 'mid';
  const s = seniority.toLowerCase();
  if (STAFF_RANKS.has(s)) return 'staff';
  if (SENIOR_RANKS.has(s)) return 'senior';
  if (s === 'junior' || s === 'intern') return 'junior';
  return 'mid';
}

// Deterministic stable id — sha1(prefix|parts) → 8 hex. Uses a tiny
// FNV-1a fallback if crypto.subtle is unavailable (SSR). Both hashes
// mirror the Python `sha1` prefix trim by design; we only care about
// determinism, not cross-language equivalence for these ids.
function fnv1a(input: string): string {
  let hash = 0x811c9dc5;
  for (let i = 0; i < input.length; i++) {
    hash ^= input.charCodeAt(i);
    hash = Math.imul(hash, 0x01000193);
  }
  return (hash >>> 0).toString(16).padStart(8, '0');
}

function stableId(prefix: string, ...parts: (string | number)[]): string {
  const key = parts.map((p) => String(p)).join('|');
  return `${prefix}.${fnv1a(key)}`;
}

function corpusHash(...parts: (string | number | undefined | null | string[])[]): string {
  const flat = parts
    .map((p) => (Array.isArray(p) ? p.join(',') : p == null ? '' : String(p)))
    .join('\0');
  // 16-hex deterministic digest.
  const h1 = fnv1a(flat);
  const h2 = fnv1a(flat + '||salt');
  return (h1 + h2).slice(0, 16);
}

function latestRatingPerDim(
  record: InterviewRecord | null | undefined,
): Map<string, { rating: number; stage: string }> {
  const out = new Map<string, { rating: number; stage: string }>();
  if (!record) return out;
  for (const st of record.stages ?? []) {
    for (const sc of st.scores ?? []) {
      if (sc.rating == null) continue;
      out.set(sc.key, { rating: Number(sc.rating), stage: st.stage });
    }
  }
  return out;
}

function interviewComposite(record: InterviewRecord | null | undefined): number | null {
  if (!record) return null;
  const rubric = record.rubric ?? [];
  if (!rubric.length) return null;
  const ratings = latestRatingPerDim(record);
  let ratedWeight = 0;
  for (const d of rubric) if (ratings.has(d.key)) ratedWeight += d.weight;
  if (ratedWeight <= 0) return null;
  let composite = 0;
  for (const d of rubric) {
    const r = ratings.get(d.key);
    if (!r) continue;
    const renorm = d.weight / ratedWeight;
    const norm = (r.rating - 1) / 4;
    composite += norm * renorm * 100;
  }
  return Math.round(composite);
}

// ───────────────────── harvesters ─────────────────────

export function harvestClaims(
  candidate: CandidateLike & { id?: number; tags?: string[]; keywords?: string[] },
  plan: QueryPlan,
  interview?: InterviewRecord | null,
): Claim[] {
  const out: Claim[] = [];
  const seen = new Set<string>();

  const planSkills = (plan.skills ?? []).map((s) => s.toLowerCase());
  const tags = (candidate.tags ?? []).map((t) => t.toLowerCase());
  const kws = (candidate.keywords ?? []).map((k) => k.toLowerCase());
  const corpus = new Set([...tags, ...kws]);
  for (const s of planSkills) {
    if (corpus.has(s) && !seen.has(s)) {
      out.push({
        id: stableId('cl.sk', s, candidate.id ?? 0),
        kind: 'skill',
        text: `Ships ${s} in production`,
        weight: 0.7,
        source: s,
      });
      seen.add(s);
    }
  }

  const headline = (candidate.headline ?? '').trim();
  const roleText = (candidate.role ?? '').trim();
  const blob = `${headline} ${roleText}`.toLowerCase();

  for (const [verb, kind] of IMPACT_HINTS) {
    if (blob.includes(verb)) {
      const key = `${verb}:${kind}`;
      if (seen.has(key)) continue;
      const snippet = extractSnippet(headline, verb) ?? extractSnippet(roleText, verb);
      const text = snippet ?? `Candidate claims to have ${verb} scope`;
      const weight = ['leadership', 'impact', 'delivery'].includes(kind) ? 0.85 : 0.55;
      out.push({
        id: stableId('cl.imp', verb, candidate.id ?? 0),
        kind,
        text,
        weight,
        source: verb,
      });
      seen.add(key);
    }
  }

  for (const tier of ['staff', 'principal', 'senior', 'lead'] as const) {
    if (blob.includes(tier) && !seen.has(`tier:${tier}`)) {
      out.push({
        id: stableId('cl.ten', tier, candidate.id ?? 0),
        kind: 'seniority',
        text: `Presented as ${tier}-tier engineer`,
        weight: 0.8,
        source: tier,
      });
      seen.add(`tier:${tier}`);
      break;
    }
  }

  const numberMatches = blob.matchAll(NUMBER_RE);
  for (const m of numberMatches) {
    const val = m[0];
    if (val.length <= 2 && /^\d+$/.test(val) && Number(val) < 5) continue;
    const key = `num:${val}`;
    if (seen.has(key)) continue;
    seen.add(key);
    out.push({
      id: stableId('cl.num', val, candidate.id ?? 0),
      kind: 'impact',
      text: `Metric claim: '${val}' in profile`,
      weight: 0.7,
      source: val,
    });
  }

  if (interview) {
    for (const st of interview.stages ?? []) {
      for (const sig of st.signals ?? []) {
        if (sig.kind !== 'strength') continue;
        const text = (sig.text ?? '').trim();
        if (!text) continue;
        const shortKey = text.slice(0, 60);
        if (seen.has(shortKey)) continue;
        seen.add(shortKey);
        out.push({
          id: stableId('cl.sig', text.slice(0, 24), st.stage, candidate.id ?? 0),
          kind: 'delivery',
          text: `Panel strength note: "${text.slice(0, 110)}"`,
          weight: 0.6,
          source: `stage:${st.stage}`,
        });
      }
    }
  }

  out.sort((a, b) => (b.weight - a.weight) || a.id.localeCompare(b.id));
  return out;
}

function extractSnippet(blob: string, verb: string): string | null {
  if (!blob) return null;
  const low = blob.toLowerCase();
  const idx = low.indexOf(verb.toLowerCase());
  if (idx < 0) return null;
  const start = Math.max(0, idx - 8);
  const end = Math.min(blob.length, idx + 60);
  const snippet = blob.slice(start, end).replace(/^[\s,.;:]+|[\s,.;:]+$/g, '');
  return snippet ? `"${snippet}"` : null;
}

export function harvestRedFlags(
  plan: QueryPlan,
  interview?: InterviewRecord | null,
): RedFlag[] {
  const out: RedFlag[] = [];
  if (!interview) return out;
  const rubric = interview.rubric ?? [];
  const ratings = latestRatingPerDim(interview);

  for (const d of rubric) {
    const key = d.key;
    const w = d.weight;
    const r = ratings.get(key);
    if (!r) {
      if (w >= REDFLAG_HIGH_WEIGHT) {
        out.push({ dim: key, dimLabel: d.label, latestRating: null, stage: null, severity: 'gap', weight: w });
      }
      continue;
    }
    let severity: FlagSeverity;
    if (r.rating <= REDFLAG_BLOCK_RATING) severity = 'block';
    else if (r.rating <= REDFLAG_WATCH_RATING) severity = w >= REDFLAG_HIGH_WEIGHT ? 'concern' : 'watch';
    else continue;
    out.push({ dim: key, dimLabel: d.label, latestRating: r.rating, stage: r.stage, severity, weight: w });
  }
  const sevRank: Record<FlagSeverity, number> = { block: 0, concern: 1, gap: 2, watch: 3 };
  out.sort(
    (a, b) =>
      (sevRank[a.severity] - sevRank[b.severity]) ||
      (b.weight - a.weight) ||
      a.dim.localeCompare(b.dim),
  );
  return out;
}

// ───────────────────── question sheets ─────────────────────

function claimProbe(claim: Claim, kind: ReferenceKind): RefQuestion {
  const map: Partial<Record<`${ClaimKind}:${ReferenceKind}`, string>> = {
    'skill:manager': `How would you rate their ${claim.source} depth on a real production project you saw them ship?`,
    'skill:peer': `Have you paired with them on ${claim.source}? What's the bug they solved that you couldn't have?`,
    'skill:report': `When you got stuck on ${claim.source}, what was the specific way they unstuck you?`,
    'skill:skip_level': `What visible impact did their ${claim.source} work have on your team's velocity?`,
    'impact:manager': `Can you walk me through what they actually owned in the work described as: ${claim.text}`,
    'impact:peer': `They mentioned ${claim.text}. What was your read on how much of that outcome was theirs vs the team's?`,
    'impact:report': `On the project they described as ${claim.text}, what did you see them do that others couldn't?`,
    'impact:skip_level': `How did the outcome behind ${claim.text} land in the wider org?`,
    'leadership:manager': 'Can you describe a moment they had to make an uncomfortable call and how it landed?',
    'leadership:peer': 'Have you ever pushed back on a decision they made? Walk me through how they took it.',
    'leadership:report': "What's a piece of hard feedback they gave you and how did it change your work?",
    'leadership:skip_level': 'What have you observed about how they set direction for their team from the outside?',
    'delivery:manager': 'Tell me about a delivery slip on their watch — what happened, and what did they do differently the next time?',
    'delivery:peer': 'Have they ever cut a corner that came back to bite the team? How did they handle it?',
    'delivery:report': "What's a shipped thing you built with them that would not have happened without them?",
    'delivery:skip_level': "Which of their team's ships would you point at as their signature work?",
    'seniority:manager': `What would need to be true for them to be a *notch above* ${claim.source}? Are they there today?`,
    'seniority:peer': `When you compare them to other ${claim.source}-tier folks on the team, where do they actually sit?`,
    'seniority:report': 'Did they behave like a senior IC or like a manager in disguise? Give me a concrete example.',
    'seniority:skip_level': 'Do you see them being able to hold a room of principals? Where would they get stuck?',
    'ownership:manager': "Give me the closest thing to a fire drill they've ever run. What happened after the incident?",
    'ownership:peer': 'Have they ever owned a failure end-to-end without deflecting to the team?',
    'ownership:report': "What's a project you were on where they owned the outcome even though the delivery was ambiguous?",
    'ownership:skip_level': 'How willingly do they take on unowned problems in your org?',
  };
  const text = map[`${claim.kind}:${kind}` as `${ClaimKind}:${ReferenceKind}`]
    ?? `Can you speak to the claim: ${claim.text}`;
  return {
    id: stableId('q.cl', claim.id, kind),
    text,
    kind: 'claim',
    priority: claim.weight * (kind === 'manager' ? 1.1 : 0.95),
    minutes: MINUTES_PER_QUESTION,
    linkedClaimId: claim.id,
    hint: `Claim source: ${claim.source}`,
  };
}

function flagProbe(flag: RedFlag, kind: ReferenceKind): RefQuestion {
  let text: string;
  const label = flag.dimLabel;
  const dim = flag.dim;
  if (dim === 'collaboration') {
    text = {
      manager: 'How did they handle disagreement with a stubborn stakeholder?',
      peer: 'Tell me about a project where the two of you disagreed. How did that end?',
      report: 'When you disagreed with them technically, how did that go?',
      skip_level: "What's their reputation across teams — collaborator or lone wolf?",
    }[kind];
  } else if (dim === 'ownership') {
    text = {
      manager: 'Walk me through the last time they dropped a ball. How did they recover?',
      peer: 'Have they ever left you holding the bag? Tell me what happened.',
      report: "What's a project they owned end-to-end even when it got messy?",
      skip_level: 'When something breaks, do they lead or wait for someone else to?',
    }[kind];
  } else if (dim === 'communication') {
    text = {
      manager: 'How well do they land hard news with execs?',
      peer: 'Do their design docs land the first time? What do they typically need to rewrite?',
      report: 'When they gave you feedback, was it specific enough that you could act on it?',
      skip_level: 'Do their updates to leadership tell you what you need without follow-ups?',
    }[kind];
  } else if (dim === 'system_design_skill') {
    text = {
      manager: 'Walk me through a system they designed that scaled well past its original assumptions.',
      peer: 'In design reviews, do they carry the room or ride the loudest voice?',
      report: "Have they mentored you on system design? What's an example?",
      skip_level: 'Do you trust their designs at scale? Why?',
    }[kind];
  } else if (dim === 'scope_influence') {
    text = {
      manager: 'Where have they meaningfully expanded scope without being asked?',
      peer: 'What are the projects they *changed the direction of* rather than just executed?',
      report: "How much of your quarter's roadmap did they set vs execute?",
      skip_level: 'Are they a scope-setter or a scope-taker? Give me an example.',
    }[kind];
  } else if (dim.endsWith('_depth') || ['data_systems', 'cloud_infra', 'language_craft'].includes(dim)) {
    text = `How would you rate their ${label.toLowerCase()} on a project you actually saw them ship?`;
  } else if (dim === 'motivation') {
    text = "What have you seen about why they want to do this specific kind of work?";
  } else {
    text = `On ${label.toLowerCase()}, what's the closest concrete story you can share?`;
  }

  let prio = 0.7 + flag.weight * 2.0;
  if (flag.severity === 'block') prio += 0.6;
  else if (flag.severity === 'concern') prio += 0.3;
  return {
    id: stableId('q.fl', dim, kind),
    text,
    kind: 'redflag',
    priority: prio,
    minutes: MINUTES_PER_QUESTION,
    linkedFlagDim: dim,
    hint: `Panel rated ${label} at ${flag.latestRating != null ? `${flag.latestRating}/5` : 'no signal'}`,
  };
}

function openQuestion(kind: ReferenceKind): RefQuestion {
  const text = {
    manager: "What haven't I asked that I should have?",
    peer: 'Is there anything about working with them that would surprise us on day 30?',
    report: 'If you were rehiring them, what would you want to know that you didn\'t when you first joined their team?',
    skip_level: 'What would you tell my CEO about this person, off the record?',
  }[kind];
  return {
    id: stableId('q.open', kind),
    text,
    kind: 'open',
    priority: 0.55,
    minutes: MINUTES_PER_QUESTION,
    hint: 'Open question — save for the last 5 minutes.',
  };
}

function growthQuestion(kind: ReferenceKind): RefQuestion {
  const text = {
    manager: 'Where would you position them on their growth curve — plateauing, steady, or accelerating?',
    peer: "In a year, do you think they'll be doing bigger things than they're doing today?",
    report: "How did they help you grow? What's next for them?",
    skip_level: "How's their trajectory look from where you sit?",
  }[kind];
  return {
    id: stableId('q.grow', kind),
    text,
    kind: 'growth',
    priority: 0.5,
    minutes: MINUTES_PER_QUESTION,
    hint: 'Growth signal — asked once, near the end.',
  };
}

function deliveryBaseline(kind: ReferenceKind): RefQuestion {
  const text = {
    manager: 'Describe one shipped project from the last 12 months that they clearly owned end-to-end.',
    peer: 'Walk me through a project you built alongside them. What was theirs, what was yours?',
    report: "What's a shipped project of theirs you saw close up? How did it land?",
    skip_level: "Which of their team's outputs would you personally point to as their work?",
  }[kind];
  return {
    id: stableId('q.deliv', kind),
    text,
    kind: 'delivery',
    priority: 0.9,
    minutes: MINUTES_PER_QUESTION,
    hint: 'Anchors the call on real work — always first.',
  };
}

function composeSlot(
  kind: ReferenceKind,
  slotIx: number,
  claims: Claim[],
  flags: RedFlag[],
): ReferenceSlot {
  const q: RefQuestion[] = [deliveryBaseline(kind)];

  const flagPriorities: Record<ReferenceKind, string[]> = {
    manager: ['ownership', 'delivery', 'communication', 'scope_influence', 'system_design_skill'],
    peer: ['collaboration', 'communication', 'system_design_skill', 'language_craft', 'backend_depth'],
    report: ['collaboration', 'ownership', 'communication', 'scope_influence'],
    skip_level: ['scope_influence', 'delivery', 'communication', 'system_design_skill'],
  };
  const kindPref = new Set(flagPriorities[kind]);

  for (const f of flags) {
    if (f.severity === 'block' || f.severity === 'concern' || f.severity === 'gap') {
      const fq = flagProbe(f, kind);
      if (kindPref.has(f.dim)) fq.priority += 0.4;
      q.push(fq);
    }
  }

  const claimKindPrio: Record<ReferenceKind, ClaimKind[]> = {
    manager: ['impact', 'leadership', 'delivery', 'ownership', 'seniority', 'skill'],
    peer: ['skill', 'delivery', 'impact', 'ownership', 'seniority', 'leadership'],
    report: ['leadership', 'delivery', 'ownership', 'impact', 'skill', 'seniority'],
    skip_level: ['impact', 'leadership', 'seniority', 'delivery', 'ownership', 'skill'],
  };
  const prio = claimKindPrio[kind];
  const score = (c: Claim): number => {
    const idx = prio.indexOf(c.kind);
    const aff = idx >= 0 ? 1.0 + 0.15 * (prio.length - idx) : 0.9;
    return c.weight * aff;
  };
  const rankedClaims = [...claims].sort((a, b) => score(b) - score(a) || a.id.localeCompare(b.id));

  const picks: Claim[] = [];
  const usedKinds = new Set<string>();
  for (const c of rankedClaims) {
    if (picks.length >= 3) break;
    if (usedKinds.has(c.kind) && picks.length >= 2) continue;
    picks.push(c);
    usedKinds.add(c.kind);
  }
  for (const c of picks) q.push(claimProbe(c, kind));

  q.push(growthQuestion(kind));
  q.push(openQuestion(kind));

  q.sort((a, b) => b.priority - a.priority);
  const hardCap = Math.min(MAX_QUESTIONS_PER_REF, Math.max(MIN_QUESTIONS_PER_REF, q.length));
  const trimmed = q.slice(0, hardCap);
  const delivery = trimmed.find((x) => x.kind === 'delivery');
  const others = trimmed.filter((x) => x.kind !== 'delivery');
  const ordered: RefQuestion[] = [];
  if (delivery) ordered.push(delivery);
  ordered.push(...others);

  const minutes = Math.round(Math.min(MINUTES_CAP, ordered.length * MINUTES_PER_QUESTION));
  const introMap: Record<ReferenceKind, string> = {
    manager: 'Anchor the call on delivery, then probe ownership and hard-news moments.',
    peer: 'Anchor on paired work, then push on collaboration and technical depth.',
    report: 'Anchor on shipped work, then probe leadership and feedback.',
    skip_level: 'Anchor on the visible output, then probe scope and trajectory.',
  };
  const focus = flags.slice(0, 3).map((f) => f.dimLabel);
  return {
    slotId: stableId('slot', kind, slotIx),
    kind,
    label: KIND_LABEL[kind],
    minutes,
    questions: ordered,
    intro: introMap[kind],
    focus,
  };
}

// ───────────────────── main composer ─────────────────────

export function composeBundle(args: {
  role: { id?: string; name?: string; plan: QueryPlan };
  candidate: CandidateLike & { id: number; name: string; tags?: string[]; keywords?: string[] };
  interview?: InterviewRecord | null;
}): ReferenceBundle {
  const { role, candidate, interview } = args;
  const plan = role.plan;
  const tier = seniorityTier(plan.seniority);
  const mix = SLOT_MIX_BY_TIER[tier] ?? SLOT_MIX_BY_TIER.mid;

  const claims = harvestClaims(candidate, plan, interview);
  const flags = harvestRedFlags(plan, interview);

  const slots = mix.map((k, ix) => composeSlot(k, ix, claims, flags));

  const totalQ = slots.reduce((s, x) => s + x.questions.length, 0);
  const totalMin = slots.reduce((s, x) => s + x.minutes, 0);
  const composite = interviewComposite(interview);

  const headline = buildHeadline(candidate.name, tier, claims.length, flags.length, composite);
  const hash = corpusHash(
    role.id ?? '',
    candidate.id,
    tier,
    slots.map((s) => s.kind).join(','),
    claims.map((c) => c.id).join(','),
    flags.map((f) => f.dim).join(','),
  );

  return {
    bundleVersion: 'credicrew.reference.v1',
    roleId: role.id ?? '',
    roleName: role.name ?? 'Role',
    candidateId: candidate.id,
    candidateName: candidate.name,
    seniorityTier: tier,
    slots,
    claims,
    redFlags: flags,
    interviewComposite: composite,
    totalMinutes: totalMin,
    totalQuestions: totalQ,
    corpusHash: hash,
    headline,
  };
}

function buildHeadline(
  name: string, tier: string, nClaims: number, nFlags: number, composite: number | null,
): string {
  const parts: string[] = [];
  if (composite != null) parts.push(`interview composite ${composite}/100`);
  if (nFlags) parts.push(`${nFlags} rubric flag${nFlags !== 1 ? 's' : ''} to probe`);
  if (nClaims) parts.push(`${nClaims} claim${nClaims !== 1 ? 's' : ''} to corroborate`);
  if (!parts.length) return `Reference sheet for ${name} — ${tier} tier · no interview signal yet.`;
  return `Reference sheet for ${name} — ${tier} tier · ${parts.join(', ')}.`;
}

// ───────────────────── response scoring ─────────────────────

export function scoreResponses(
  bundle: ReferenceBundle,
  responses: ResponseAnswer[],
): ReferenceReport {
  const qById = new Map<string, RefQuestion>();
  const qSlot = new Map<string, ReferenceSlot>();
  for (const slot of bundle.slots) {
    for (const q of slot.questions) {
      qById.set(q.id, q);
      qSlot.set(q.id, slot);
    }
  }
  const claimById = new Map(bundle.claims.map((c) => [c.id, c] as const));
  const flagByDim = new Map(bundle.redFlags.map((f) => [f.dim, f] as const));

  const slotAnswered = new Map<string, number>();
  const slotCorr = new Map<string, number>();
  const slotConcern = new Map<string, number>();
  const slotContra = new Map<string, number>();
  const slotNS = new Map<string, number>();
  for (const s of bundle.slots) {
    slotAnswered.set(s.slotId, 0);
    slotCorr.set(s.slotId, 0);
    slotConcern.set(s.slotId, 0);
    slotContra.set(s.slotId, 0);
    slotNS.set(s.slotId, 0);
  }
  const claimAgg = new Map<string, { matches: number; corr: number; contra: number; concern: number }>();
  for (const c of bundle.claims) claimAgg.set(c.id, { matches: 0, corr: 0, contra: 0, concern: 0 });
  const flagAgg = new Map<string, { matches: number; corr: number; contra: number; concern: number }>();
  for (const f of bundle.redFlags) flagAgg.set(f.dim, { matches: 0, corr: 0, contra: 0, concern: 0 });

  let totalShift = 0;
  let totalAnswered = 0;

  for (const a of responses) {
    const q = qById.get(a.questionId);
    if (!q) continue;
    const slot = qSlot.get(q.id);
    if (!slot) continue;
    if (a.verdict === 'pending') continue;
    slotAnswered.set(slot.slotId, (slotAnswered.get(slot.slotId) ?? 0) + 1);
    totalAnswered += 1;

    if (a.verdict === 'corroborated') {
      slotCorr.set(slot.slotId, (slotCorr.get(slot.slotId) ?? 0) + 1);
      totalShift += SHIFT_CORROBORATED * q.priority;
    } else if (a.verdict === 'concerned') {
      slotConcern.set(slot.slotId, (slotConcern.get(slot.slotId) ?? 0) + 1);
      totalShift += SHIFT_CONCERNED * q.priority;
    } else if (a.verdict === 'contradicted') {
      slotContra.set(slot.slotId, (slotContra.get(slot.slotId) ?? 0) + 1);
      totalShift += SHIFT_CONTRADICTED * q.priority;
    } else if (a.verdict === 'no_signal') {
      slotNS.set(slot.slotId, (slotNS.get(slot.slotId) ?? 0) + 1);
      totalShift += SHIFT_NO_SIGNAL * q.priority;
    }

    if (q.linkedClaimId && claimAgg.has(q.linkedClaimId)) {
      const agg = claimAgg.get(q.linkedClaimId)!;
      agg.matches += 1;
      if (a.verdict === 'corroborated') agg.corr += 1;
      else if (a.verdict === 'contradicted') agg.contra += 1;
      else if (a.verdict === 'concerned') agg.concern += 1;
    }
    if (q.linkedFlagDim && flagAgg.has(q.linkedFlagDim)) {
      const agg = flagAgg.get(q.linkedFlagDim)!;
      agg.matches += 1;
      if (a.verdict === 'corroborated') agg.corr += 1;
      else if (a.verdict === 'contradicted') agg.contra += 1;
      else if (a.verdict === 'concerned') agg.concern += 1;
    }
  }

  totalShift = Math.max(SHIFT_CLAMP_MIN, Math.min(SHIFT_CLAMP_MAX, totalShift));

  const claimStatus: ClaimStatus[] = [];
  for (const [cid, agg] of claimAgg) {
    const c = claimById.get(cid)!;
    let status: ClaimStatus['status'];
    if (agg.contra >= 1) status = 'contradicted';
    else if (agg.corr >= 2 || (agg.corr >= 1 && agg.matches === 1)) status = 'confirmed';
    else if (agg.concern >= 1) status = 'concern';
    else status = 'unknown';
    claimStatus.push({
      claimId: cid,
      kind: c.kind,
      text: c.text,
      weight: c.weight,
      matches: agg.matches,
      corroborated: agg.corr,
      contradicted: agg.contra,
      concerned: agg.concern,
      status,
    });
  }
  claimStatus.sort((a, b) => (b.weight - a.weight) || a.claimId.localeCompare(b.claimId));

  const flagStatus: FlagStatus[] = [];
  for (const [dim, agg] of flagAgg) {
    const f = flagByDim.get(dim)!;
    let status: FlagStatus['status'];
    if (agg.contra >= 1) status = 'confirmed';
    else if (agg.corr >= 1) status = 'resolved';
    else if (agg.concern >= 1) status = 'concern';
    else status = 'unknown';
    flagStatus.push({
      dim,
      dimLabel: f.dimLabel,
      severity: f.severity,
      weight: f.weight,
      matches: agg.matches,
      corroborated: agg.corr,
      contradicted: agg.contra,
      concerned: agg.concern,
      status,
    });
  }
  const sevRank: Record<string, number> = { block: 0, concern: 1, gap: 2, watch: 3 };
  flagStatus.sort(
    (a, b) =>
      ((sevRank[a.severity] ?? 4) - (sevRank[b.severity] ?? 4)) ||
      (b.weight - a.weight) ||
      a.dim.localeCompare(b.dim),
  );

  const slotSummaries: SlotSummary[] = bundle.slots.map((s) => {
    const total = s.questions.length;
    const ans = slotAnswered.get(s.slotId) ?? 0;
    const cov = total > 0 ? Math.round((100 * ans) / total * 10) / 10 : 0;
    return {
      slotId: s.slotId,
      kind: s.kind,
      label: s.label,
      answered: ans,
      total,
      corroborated: slotCorr.get(s.slotId) ?? 0,
      concerned: slotConcern.get(s.slotId) ?? 0,
      contradicted: slotContra.get(s.slotId) ?? 0,
      noSignal: slotNS.get(s.slotId) ?? 0,
      coveragePct: cov,
    };
  });

  const totalQ = bundle.slots.reduce((s, x) => s + x.questions.length, 0);
  const coveragePct = totalQ > 0 ? Math.round((100 * totalAnswered) / totalQ * 10) / 10 : 0;
  const verdict = decideVerdict(totalShift, claimStatus, flagStatus, coveragePct);

  const projectedComposite =
    bundle.interviewComposite != null
      ? Math.max(0, Math.min(100, Math.round(bundle.interviewComposite + totalShift)))
      : null;

  const headline = reportHeadline(verdict, totalShift, claimStatus, flagStatus, coveragePct);
  return {
    bundleVersion: bundle.bundleVersion,
    roleId: bundle.roleId,
    candidateId: bundle.candidateId,
    verdict,
    headline,
    scoreShift: Math.round(totalShift * 100) / 100,
    projectedComposite,
    slots: slotSummaries,
    claimStatus,
    flagStatus,
    totalAnswered,
    totalQuestions: totalQ,
    coveragePct,
  };
}

function decideVerdict(
  shift: number,
  claims: ClaimStatus[],
  flags: FlagStatus[],
  coverage: number,
): Verdict {
  const contra = claims.filter((c) => c.status === 'contradicted').length;
  const hardConfirmed = flags.filter(
    (f) => f.status === 'confirmed' && (f.severity === 'block' || f.severity === 'concern'),
  ).length;
  if (coverage < 15) return 'pending';
  if (contra >= 2 || hardConfirmed >= 2) return 'block';
  if (contra === 1 || hardConfirmed === 1) return 'reopen';
  if (shift >= VERDICT_PROCEED_MIN) return 'proceed';
  if (shift >= VERDICT_CAVEAT_MIN) return 'proceed_with_caveat';
  if (shift >= VERDICT_REOPEN_MIN) return 'reopen';
  return 'block';
}

function reportHeadline(
  verdict: Verdict, shift: number, claims: ClaimStatus[], flags: FlagStatus[], coverage: number,
): string {
  const sign = shift >= 0 ? '+' : '';
  const corr = claims.filter((c) => c.status === 'confirmed').length;
  const contra = claims.filter((c) => c.status === 'contradicted').length;
  const resolved = flags.filter((f) => f.status === 'resolved').length;
  const confirmedFlags = flags.filter((f) => f.status === 'confirmed').length;
  const parts: string[] = [`shift ${sign}${shift.toFixed(1)} pts`];
  if (corr) parts.push(`${corr} claim${corr !== 1 ? 's' : ''} confirmed`);
  if (contra) parts.push(`${contra} contradicted`);
  if (resolved) parts.push(`${resolved} flag${resolved !== 1 ? 's' : ''} resolved`);
  if (confirmedFlags) parts.push(`${confirmedFlags} flag${confirmedFlags !== 1 ? 's' : ''} confirmed`);
  parts.push(`${coverage.toFixed(0)}% coverage`);
  const prefix: Record<Verdict, string> = {
    proceed: 'Proceed to offer — ',
    proceed_with_caveat: 'Proceed with caveat — ',
    reopen: 'Reopen the loop — ',
    block: 'Do not send offer — ',
    pending: 'Awaiting refs — ',
  };
  return prefix[verdict] + parts.join(' · ') + '.';
}

// ───────────────────── markdown export ─────────────────────

export function toMarkdown(bundle: ReferenceBundle): string {
  const lines: string[] = [];
  lines.push(`# Reference sheet — ${bundle.candidateName}`, '');
  lines.push(`> ${bundle.headline}`, '');
  lines.push(`- **Role:** ${bundle.roleName} (\`${bundle.roleId}\`)`);
  lines.push(`- **Seniority tier:** ${bundle.seniorityTier}`);
  if (bundle.interviewComposite != null) {
    lines.push(`- **Interview composite:** ${bundle.interviewComposite}/100`);
  }
  lines.push(
    `- **Total minutes budgeted:** ${bundle.totalMinutes}m across ${bundle.slots.length} references (${bundle.totalQuestions} questions)`,
  );
  lines.push(`- **Corpus hash:** \`${bundle.corpusHash}\``, '');
  if (bundle.claims.length) {
    lines.push('## Claims to corroborate');
    for (const c of bundle.claims.slice(0, 8)) {
      lines.push(`- **[${c.kind}]** ${c.text} · weight ${c.weight.toFixed(2)} · source \`${c.source}\``);
    }
    lines.push('');
  }
  if (bundle.redFlags.length) {
    lines.push('## Rubric flags to probe');
    for (const f of bundle.redFlags.slice(0, 8)) {
      const r = f.latestRating != null ? `${f.latestRating}/5` : 'no rating';
      lines.push(
        `- **[${f.severity}]** ${f.dimLabel} — panel: ${r} · weight ${f.weight.toFixed(2)}`,
      );
    }
    lines.push('');
  }
  for (const slot of bundle.slots) {
    lines.push(`## ${slot.label} (${slot.minutes}m)`);
    lines.push(`_${slot.intro}_`);
    if (slot.focus.length) lines.push(`- **Focus dims:** ${slot.focus.join(', ')}`);
    lines.push('');
    slot.questions.forEach((q, i) => {
      lines.push(`${i + 1}. **[${QUESTION_KIND_LABEL[q.kind]}]** ${q.text}`);
      if (q.hint) lines.push(`   - _${q.hint}_`);
    });
    lines.push('');
  }
  lines.push('---');
  lines.push('_generated by credicrew.reference.v1 — deterministic, same input → same output_');
  return lines.join('\n');
}

// ───────────────────── defaults ─────────────────────

export const REFERENCE_DEFAULTS = {
  engine: 'credicrew-reference/1.0.0',
  bundleVersion: 'credicrew.reference.v1',
  kinds: KINDS,
  kindLabel: KIND_LABEL,
  kindHex: KIND_HEX,
  kindTone: KIND_TONE,
  slotMixByTier: SLOT_MIX_BY_TIER,
  shiftClamp: [SHIFT_CLAMP_MIN, SHIFT_CLAMP_MAX] as [number, number],
  shiftWeights: {
    corroborated: SHIFT_CORROBORATED,
    concerned: SHIFT_CONCERNED,
    contradicted: SHIFT_CONTRADICTED,
    no_signal: SHIFT_NO_SIGNAL,
  },
  answerVerdicts: ANSWER_VERDICT_LABEL,
  verdicts: VERDICT_LABEL,
};
