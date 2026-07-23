// Anchor — Candidate Momentum & Drop-Off Risk Radar (Day 92).
//
// Every other Credicrew surface answers "who should I hire?" — Match ranks
// fit, Decision aggregates the loop, Offer benchmarks comp, Peer Parity
// audits fairness, Compass rolls the whole shop up. Nothing answers the
// question every recruiter opens their inbox with on a Tuesday morning:
// *which of the people already in my pipeline are about to ghost me, and
// what should I do about it in the next hour?*
//
// That question is not paranoia — it is the single biggest waste in modern
// hiring. A candidate you sourced, screened, and loved on the phone
// disappears between the second and third interview because a competing
// offer landed on Friday, calendar-tag slipped twice, and by the time
// "just circling back!" hits their inbox they've already accepted. The
// signals were there for a week. Nobody was looking at them together.
//
// Anchor puts a radar on it. Given each active candidate + their pipeline
// state + a signal packet (recency, cadence, reschedules, sentiment,
// competing pipelines), it computes:
//
//   · a 0..100 **momentum** score (higher = engaged) and its inverse
//     **risk** (higher = about to ghost)
//   · a Bayesian **ghost probability** anchored on a stage-conditioned
//     prior (offer-stage ghosts differ from screening-stage ghosts)
//   · a **half-life in days** — how long until untouched momentum decays
//     past the recoverable threshold
//   · 3–5 **driver chips** — the ranked signals dragging risk up
//   · a **recovery tier** (hold · ping · reengage · exec · release) and a
//     copy-paste **nudge script** tailored to the top driver
//   · a **salvage value** — how much loss you avoid by intervening now
//     (weighted by role fit × interview composite × offer exposure)
//
// Rolled up: at-risk queue, critical queue, released queue, per-stage
// risk histogram, driver-frequency histogram, and total ₹ exposure across
// drafted offers where the candidate is drifting.
//
// Every constant is inline and documented; every math step is a pure
// function. No LLM, no network. Mirrored byte-for-byte in
// `backend/app/services/anchor.py` so the FastAPI surface can serve the
// same summary an agentic client would compute in the browser.

import type { PipelineStatus } from '@/lib/roles';

// ────────────────────── physics constants ──────────────────────

/** Days since last touch that maps to a 0 recency axis. Beyond 12 days,
 *  the recency signal is dead — even a warm relationship goes cold. */
export const RECENCY_ZERO_DAYS = 12;

/** Hours of median candidate reply latency that maps to a 0 cadence axis.
 *  50 hours ≈ two business days; slower than that reads as disengagement. */
export const CADENCE_ZERO_HOURS = 50;

/** Per-reschedule reliability penalty (points). Two reschedules ≈ –30. */
export const RESCHEDULE_PENALTY = 15;

/** One-time reliability hit for a no-show. Never fully recovers. */
export const NO_SHOW_PENALTY = 30;

/** Reliability floor — even the messiest calendar can't drop the axis
 *  below this, because responsiveness elsewhere might still be strong. */
export const RELIABILITY_FLOOR = 20;

/** Per-competing-pipeline penalty on the competing axis (points). */
export const COMPETING_PENALTY = 25;

/** Risk bump when an external offer signal is confirmed (post-weighted). */
export const EXTERNAL_OFFER_RISK_BUMP = 15;

/** Risk ceiling — nothing is ever 100% guaranteed to ghost. */
export const RISK_CEILING = 98;

/** Per-stage budget in days — beyond this, the pace axis starts to bleed. */
export const STAGE_BUDGET_DAYS: Record<PipelineStatus, number> = {
  new:        4,
  outreach:   6,
  screening:  8,
  interview: 10,
  offer:      7,
  passed:    99, // never drops
};

/** Pace-axis decay per day *over budget* (points). */
export const PACE_DECAY_PER_DAY = 6;

/** Weights of each momentum axis. Sum to 1.0.
 *  Recency dominates because "when did we last talk" is the loudest
 *  ghost predictor in the real world. */
export const AXIS_WEIGHTS = {
  recency:     0.25,
  cadence:     0.20,
  reliability: 0.15,
  pace:        0.20,
  sentiment:   0.10,
  competing:   0.10,
} as const;

/** Recovery-tier thresholds on risk (0..100).
 *  Symmetric-ish so a well-tuned pipeline puts most people in `hold`
 *  and a stressed one lights up `ping`/`reengage` before `release`. */
export const TIER_THRESHOLDS = {
  ping:     25,
  reengage: 45,
  exec:     65,
  release:  82,
} as const;

/** Momentum floor below which a candidate is considered "no longer
 *  recoverable by scripted nudges." Used by the half-life calc. */
export const RECOVER_FLOOR = 30;

/** Stage-conditioned Bayesian prior on ghost probability. Not tuned on
 *  real data — anchored on common recruiting-industry mid-market rates.
 *  A candidate at `offer` who ghosts is much rarer than one at `new` who
 *  drops off; the risk score has to bend the prior, not replace it. */
export const STAGE_GHOST_PRIOR: Record<PipelineStatus, number> = {
  new:       0.35,
  outreach:  0.30,
  screening: 0.22,
  interview: 0.15,
  offer:     0.10,
  passed:    0.00,
};

/** Sensitivity of ghost probability to risk deviation from 50. A risk of
 *  70 shifts logit(prior) by +1.0 → prior 0.15 becomes ~0.32. */
export const RISK_LOGIT_GAIN = 20;

/** ₹ (thousands / lakh — caller-consistent) assumed lost when a candidate
 *  ghosts pre-offer. Used for exposure summary when no drafted offer. */
export const PRE_OFFER_SUNK_COST = 250;

// ────────────────────── taxonomy ──────────────────────

export type AnchorTier = 'hold' | 'ping' | 'reengage' | 'exec' | 'release';

export const TIER_ORDER: AnchorTier[] = ['hold', 'ping', 'reengage', 'exec', 'release'];

export const TIER_LABEL: Record<AnchorTier, string> = {
  hold:     'Hold pattern',
  ping:     'Soft ping',
  reengage: 'Warm re-engage',
  exec:     'Executive touch',
  release:  'Concede & release',
};

export const TIER_BLURB: Record<AnchorTier, string> = {
  hold:     'No action — the candidate is engaged, save the interruption.',
  ping:     'Light nudge — reconfirm next step, ask for a slot, close the loop.',
  reengage: 'Recruiter call — reset expectations, hear the objection, commit to a date.',
  exec:     'Hiring manager or engineering leader personally reaches out — you\'re asking a question only they can answer.',
  release:  'Send a graceful close; drop into Revive for a future role.',
};

export const TIER_HEX: Record<AnchorTier, string> = {
  hold:     '#10b981', // emerald
  ping:     '#38bdf8', // sky
  reengage: '#f59e0b', // amber
  exec:     '#fb7185', // rose-400
  release:  '#94a3b8', // slate — a "we're done here" grey
};

export const TIER_TONE: Record<AnchorTier, string> = {
  hold:     'emerald',
  ping:     'sky',
  reengage: 'amber',
  exec:     'rose',
  release:  'slate',
};

// ────────────────────── driver taxonomy ──────────────────────

export type AnchorDriver =
  | 'recency'
  | 'cadence'
  | 'reliability'
  | 'pace'
  | 'sentiment'
  | 'competing'
  | 'external_offer'
  | 'no_show';

export const DRIVER_LABEL: Record<AnchorDriver, string> = {
  recency:         'Silence',
  cadence:         'Reply latency',
  reliability:     'Reschedules',
  pace:            'Stage age',
  sentiment:       'Cool tone',
  competing:       'Competing pipelines',
  external_offer:  'Confirmed outside offer',
  no_show:         'Recent no-show',
};

export const DRIVER_HEX: Record<AnchorDriver, string> = {
  recency:        '#f472b6',
  cadence:        '#f59e0b',
  reliability:    '#fb7185',
  pace:           '#a78bfa',
  sentiment:      '#facc15',
  competing:      '#22d3ee',
  external_offer: '#f43f5e',
  no_show:        '#ef4444',
};

// ────────────────────── I/O shapes ──────────────────────

export type SentimentTone = 'warm' | 'neutral' | 'cool';

/** Raw signal packet — either provided by caller (real data), or seeded
 *  from a deterministic hash for demo state. */
export type AnchorSignals = {
  daysSinceLastTouch: number;   // 0..30+
  lastTouchDirection: 'in' | 'out'; // 'in' = candidate replied; 'out' = we messaged
  responseLatencyHours: number; // rolling median of candidate reply time
  rescheduleCount: number;      // count of interviewer/candidate reschedules
  noShow: boolean;              // any recent interview no-show
  daysInStage: number;          // days since stageChangedAt
  competingPipelines: number;   // 0..3 signals of competing processes
  sentimentTone: SentimentTone;
  externalOffer: boolean;       // confirmed outside offer in hand
  noteKeyphrase: string | null; // last note excerpt, may hint at driver
};

export type AnchorCandidateInput = {
  candidateId: number;
  candidateName: string;
  candidateTitle?: string;
  candidateLocation?: string;
  roleId: string;
  roleName: string;
  roleSeniority?: string;
  status: PipelineStatus;
  addedAt: number;
  stageChangedAt?: number;
  matchScore: number;             // 0..100 — how much we care
  compositeScore: number | null;  // interview composite (0..100), null if none
  /** Optional total year-1 cash for a drafted offer, same units as
   *  PortfolioOffer.base. Drives ₹ exposure math. */
  offerValueAnnual?: number;
  /** Caller may pre-supply signals; otherwise derived from seed. */
  signals?: AnchorSignals;
};

export type AnchorInput = {
  candidates: AnchorCandidateInput[];
  now?: number;
};

export type AnchorAxis =
  | 'recency'
  | 'cadence'
  | 'reliability'
  | 'pace'
  | 'sentiment'
  | 'competing';

export const AXES: AnchorAxis[] = [
  'recency',
  'cadence',
  'reliability',
  'pace',
  'sentiment',
  'competing',
];

export const AXIS_LABEL: Record<AnchorAxis, string> = {
  recency:     'Recency',
  cadence:     'Reply cadence',
  reliability: 'Reliability',
  pace:        'Stage pace',
  sentiment:   'Sentiment',
  competing:   'Competing offers',
};

export type AnchorDriverEntry = {
  driver: AnchorDriver;
  label: string;
  detail: string;         // one-sentence evidence
  contribution: number;   // pts of risk this driver contributes
};

export type AnchorScript = {
  headline: string;       // subject / one-line greeting
  body: string;           // multi-line message body (recruiter voice)
  channel: 'email' | 'inmail' | 'sms' | 'call';
  minutes: number;        // approx effort budget
};

export type AnchorCandidateScore = {
  candidateId: number;
  candidateName: string;
  candidateTitle?: string;
  roleId: string;
  roleName: string;
  status: PipelineStatus;
  axes: Record<AnchorAxis, number>; // 0..100 each
  momentum: number;                  // 0..100 weighted mean
  risk: number;                      // 0..100 = 100 - momentum (+external)
  tier: AnchorTier;
  ghostProbability: number;          // 0..1
  halfLifeDays: number;              // ≥ 1
  care: number;                      // 0..1 how much we want to save them
  salvageValue: number;              // 0..100 monetary-ish priority score
  exposureAnnual: number;            // ₹ at risk (same units as input)
  drivers: AnchorDriverEntry[];
  script: AnchorScript;
  signals: AnchorSignals;            // echoed for the UI
  noteKeyphrase: string | null;
};

export type AnchorStageBreakdown = {
  status: PipelineStatus;
  count: number;
  atRisk: number;      // risk >= TIER_THRESHOLDS.reengage
  critical: number;    // risk >= TIER_THRESHOLDS.exec
  meanRisk: number;    // 0..100
};

export type AnchorSummary = {
  generatedAt: number;
  totals: {
    active: number;
    atRisk: number;
    critical: number;
    released: number;
    exposureAnnual: number;
    exposurePreOffer: number;
    salvageableCount: number;
    salvageValueTotal: number;
  };
  scores: AnchorCandidateScore[];         // full ordered by risk desc
  salvageQueue: AnchorCandidateScore[];   // top by salvageValue
  criticalQueue: AnchorCandidateScore[];  // tier ∈ {exec, release}
  byStage: AnchorStageBreakdown[];
  driverHistogram: Array<{ driver: AnchorDriver; label: string; count: number; hex: string }>;
  tierMix: Record<AnchorTier, number>;
  meanMomentum: number | null;
  meanRisk: number | null;
  notes: string[];
};

// ────────────────────── math helpers ──────────────────────

function clamp(v: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, v));
}

function round(v: number): number { return Math.round(v); }

function safeMean(xs: number[]): number | null {
  const filtered = xs.filter(x => Number.isFinite(x));
  if (filtered.length === 0) return null;
  return filtered.reduce((s, x) => s + x, 0) / filtered.length;
}

function sigmoid(z: number): number {
  if (z >= 0) {
    const e = Math.exp(-z);
    return 1 / (1 + e);
  }
  const e = Math.exp(z);
  return e / (1 + e);
}

function logit(p: number): number {
  const q = clamp(p, 1e-6, 1 - 1e-6);
  return Math.log(q / (1 - q));
}

// ────────────────────── per-axis scorers ──────────────────────

function recencyAxis(s: AnchorSignals): number {
  const raw = 100 - (s.daysSinceLastTouch / RECENCY_ZERO_DAYS) * 100;
  // A candidate-initiated touch is worth more than one we sent.
  const inboundBoost = s.lastTouchDirection === 'in' ? 8 : 0;
  return clamp(raw + inboundBoost, 0, 100);
}

function cadenceAxis(s: AnchorSignals): number {
  const raw = 100 - (s.responseLatencyHours / CADENCE_ZERO_HOURS) * 100;
  return clamp(raw, 0, 100);
}

function reliabilityAxis(s: AnchorSignals): number {
  const penalty = s.rescheduleCount * RESCHEDULE_PENALTY + (s.noShow ? NO_SHOW_PENALTY : 0);
  return clamp(100 - penalty, RELIABILITY_FLOOR, 100);
}

function paceAxis(s: AnchorSignals, status: PipelineStatus): number {
  const budget = STAGE_BUDGET_DAYS[status] ?? 8;
  const over = Math.max(0, s.daysInStage - budget);
  return clamp(100 - over * PACE_DECAY_PER_DAY, 0, 100);
}

function sentimentAxis(s: AnchorSignals): number {
  if (s.sentimentTone === 'warm') return 90;
  if (s.sentimentTone === 'cool') return 30;
  return 60;
}

function competingAxis(s: AnchorSignals): number {
  const n = clamp(s.competingPipelines, 0, 3);
  return clamp(100 - n * COMPETING_PENALTY, 0, 100);
}

// ────────────────────── momentum / risk / tier ──────────────────────

function momentumFromAxes(axes: Record<AnchorAxis, number>): number {
  const w = AXIS_WEIGHTS;
  return (
    axes.recency     * w.recency +
    axes.cadence     * w.cadence +
    axes.reliability * w.reliability +
    axes.pace        * w.pace +
    axes.sentiment   * w.sentiment +
    axes.competing   * w.competing
  );
}

function riskFromMomentum(momentum: number, s: AnchorSignals): number {
  let r = 100 - momentum;
  if (s.externalOffer) r += EXTERNAL_OFFER_RISK_BUMP;
  return clamp(r, 0, RISK_CEILING);
}

export function tierFromRisk(risk: number): AnchorTier {
  if (risk >= TIER_THRESHOLDS.release)  return 'release';
  if (risk >= TIER_THRESHOLDS.exec)     return 'exec';
  if (risk >= TIER_THRESHOLDS.reengage) return 'reengage';
  if (risk >= TIER_THRESHOLDS.ping)     return 'ping';
  return 'hold';
}

/** P(ghost) = σ(logit(prior_stage) + (risk - 50)/RISK_LOGIT_GAIN).
 *  A risk of 50 leaves the stage prior unchanged; every 20 risk points
 *  above/below shifts the logit by 1. */
function ghostProbability(risk: number, status: PipelineStatus): number {
  const prior = STAGE_GHOST_PRIOR[status] ?? 0.20;
  const shift = (risk - 50) / RISK_LOGIT_GAIN;
  return clamp(sigmoid(logit(prior) + shift), 0, 0.99);
}

/** Half-life days = how long until momentum decays through RECOVER_FLOOR
 *  if we do nothing. Cheaper priorities decay faster. */
function halfLifeDays(momentum: number, care: number): number {
  const above = Math.max(1, momentum - RECOVER_FLOOR);
  // Base 3 pts/day, plus up to +3 for low-care candidates (we watch them
  // less, they slip faster).
  const decayPerDay = 3 + (1 - clamp(care, 0, 1)) * 3;
  return Math.max(1, Math.round(above / decayPerDay));
}

// ────────────────────── driver harvest ──────────────────────

/** For each axis that dropped ≥ this many points, log a driver entry. */
const DRIVER_MIN_CONTRIBUTION = 6;

function harvestDrivers(
  axes: Record<AnchorAxis, number>,
  s: AnchorSignals,
  status: PipelineStatus,
): AnchorDriverEntry[] {
  const out: AnchorDriverEntry[] = [];
  const w = AXIS_WEIGHTS;

  const contrib = (axisScore: number, weight: number) => (100 - axisScore) * weight;

  const c = {
    recency:     contrib(axes.recency, w.recency),
    cadence:     contrib(axes.cadence, w.cadence),
    reliability: contrib(axes.reliability, w.reliability),
    pace:        contrib(axes.pace, w.pace),
    sentiment:   contrib(axes.sentiment, w.sentiment),
    competing:   contrib(axes.competing, w.competing),
  };

  if (c.recency >= DRIVER_MIN_CONTRIBUTION) {
    const d = Math.round(s.daysSinceLastTouch);
    out.push({
      driver: 'recency',
      label: DRIVER_LABEL.recency,
      detail: `${d} day${d === 1 ? '' : 's'} since last touch (${s.lastTouchDirection === 'in' ? 'they replied last' : 'we messaged last'}).`,
      contribution: round(c.recency),
    });
  }
  if (c.cadence >= DRIVER_MIN_CONTRIBUTION) {
    const h = Math.round(s.responseLatencyHours);
    out.push({
      driver: 'cadence',
      label: DRIVER_LABEL.cadence,
      detail: `Median reply latency ${h}h — slowing vs pipeline baseline.`,
      contribution: round(c.cadence),
    });
  }
  if (c.reliability >= DRIVER_MIN_CONTRIBUTION) {
    const parts: string[] = [];
    if (s.rescheduleCount > 0) parts.push(`${s.rescheduleCount} reschedule${s.rescheduleCount === 1 ? '' : 's'}`);
    if (s.noShow) parts.push('one no-show');
    out.push({
      driver: s.noShow ? 'no_show' : 'reliability',
      label: s.noShow ? DRIVER_LABEL.no_show : DRIVER_LABEL.reliability,
      detail: parts.length > 0 ? parts.join(' · ') + '.' : 'Calendar drift on last two rounds.',
      contribution: round(c.reliability),
    });
  }
  if (c.pace >= DRIVER_MIN_CONTRIBUTION) {
    const budget = STAGE_BUDGET_DAYS[status] ?? 8;
    const over = Math.max(0, Math.round(s.daysInStage - budget));
    out.push({
      driver: 'pace',
      label: DRIVER_LABEL.pace,
      detail: `${Math.round(s.daysInStage)}d in ${status} · ${over}d over the ${budget}d stage budget.`,
      contribution: round(c.pace),
    });
  }
  if (c.sentiment >= DRIVER_MIN_CONTRIBUTION && s.sentimentTone === 'cool') {
    out.push({
      driver: 'sentiment',
      label: DRIVER_LABEL.sentiment,
      detail: s.noteKeyphrase
        ? `Last note tone reads cool — "${s.noteKeyphrase}".`
        : 'Last note tone reads cool.',
      contribution: round(c.sentiment),
    });
  }
  if (c.competing >= DRIVER_MIN_CONTRIBUTION) {
    out.push({
      driver: 'competing',
      label: DRIVER_LABEL.competing,
      detail: `${s.competingPipelines} concurrent process${s.competingPipelines === 1 ? '' : 'es'} mentioned.`,
      contribution: round(c.competing),
    });
  }
  if (s.externalOffer) {
    out.push({
      driver: 'external_offer',
      label: DRIVER_LABEL.external_offer,
      detail: 'Outside offer confirmed — competing deadline is live.',
      contribution: EXTERNAL_OFFER_RISK_BUMP,
    });
  }
  return out.sort((a, b) => b.contribution - a.contribution).slice(0, 5);
}

// ────────────────────── script composer ──────────────────────

function seniorityGreeting(name: string, seniority?: string): string {
  const first = (name || 'there').split(' ')[0];
  if (!seniority) return `Hi ${first},`;
  if (['staff', 'principal', 'lead'].includes(seniority.toLowerCase())) return `Hi ${first},`;
  return `Hey ${first},`;
}

/**
 * Compose a copy-paste nudge message tailored to (tier × top driver).
 * The scripts are opinionated on tone: no fluff, no "I hope this email
 * finds you well," a specific ask, a concrete next-step commitment.
 */
export function composeScript(
  c: AnchorCandidateInput,
  tier: AnchorTier,
  topDriver: AnchorDriver | null,
): AnchorScript {
  const greeting = seniorityGreeting(c.candidateName, c.roleSeniority);
  const role = c.roleName || 'the role';
  const stage = c.status;

  if (tier === 'hold') {
    return {
      headline: 'Hold — no message needed',
      body: 'Momentum is healthy. Log the current touchpoint and revisit if signals shift.',
      channel: 'email',
      minutes: 0,
    };
  }

  if (tier === 'ping') {
    const body =
      topDriver === 'recency'
        ? `${greeting}\n\nQuick nudge on ${role} — wanted to close the loop on next steps. Are you free for a 20-min slot ${nextSlotBlurb()}? Happy to share the interviewer background beforehand.\n\n— Aryan`
        : topDriver === 'pace'
          ? `${greeting}\n\nWe've been holding your ${role} slot at ${stage}. Wanted to make sure the timing still works — do you have 15 minutes ${nextSlotBlurb()} to lock the next round?\n\n— Aryan`
          : `${greeting}\n\nCircling back on ${role}. Where are you on your side — worth a quick 15 minute sync ${nextSlotBlurb()} to answer any open questions?\n\n— Aryan`;
    return { headline: `Soft ping on ${role}`, body, channel: 'email', minutes: 5 };
  }

  if (tier === 'reengage') {
    const body =
      topDriver === 'competing'
        ? `${greeting}\n\nWant to be direct — we know you're weighing options and don't want to lose the conversation. Can I get 25 minutes with you ${nextSlotBlurb()}? Would love to hear where ${role} sits versus the other processes, and share what we can commit to on our end.\n\n— Aryan`
        : topDriver === 'sentiment'
          ? `${greeting}\n\nLast note read a bit cool and I want to make sure we haven't dropped something on our end. Have 20 minutes ${nextSlotBlurb()} to talk through what would make ${role} more compelling? No pitch — just listening.\n\n— Aryan`
          : `${greeting}\n\nWant to reset expectations on ${role}. Can I pull you in for a 25 min recruiter sync ${nextSlotBlurb()}? Want to hear your timeline and commit to a decision date so nothing drifts.\n\n— Aryan`;
    return { headline: `Warm re-engage — ${role}`, body, channel: 'call', minutes: 25 };
  }

  if (tier === 'exec') {
    const body =
      topDriver === 'external_offer'
        ? `${greeting}\n\nHeard you have an offer in hand. Before you sign, would you give our hiring manager 30 minutes ${nextSlotBlurb()}? They want to hear what would make the difference, and we're willing to move fast on comp and start date to keep you in the conversation.\n\n— Aryan`
        : topDriver === 'competing'
          ? `${greeting}\n\nWant to escalate — our hiring manager would like to spend 30 minutes with you ${nextSlotBlurb()} to walk you through what the first six months of ${role} would look like end-to-end. Small ask, big signal from our side.\n\n— Aryan`
          : `${greeting}\n\nOur hiring manager wants to speak with you personally about ${role}. 30 minutes ${nextSlotBlurb()}. Not another interview — a conversation about scope, growth path, and what would matter to you. Would you take it?\n\n— Aryan`;
    return { headline: `Exec touch — ${role}`, body, channel: 'call', minutes: 30 };
  }

  // release
  const body =
    `${greeting}\n\nWanted to be straight — it looks like the timing isn't lining up for ${role} on either side. We're going to close the loop for now, but would love to keep in touch and reach out first when the next role that fits comes up. Thanks for the time you've already given.\n\n— Aryan`;
  return { headline: `Graceful close — ${role}`, body, channel: 'email', minutes: 5 };
}

function nextSlotBlurb(): string {
  // Deliberately generic — we don't have live calendar context. The
  // recruiter fills in the specific slot when they send. Kept vague so
  // scripts read as templates, not fabricated commitments.
  return 'this week or early next';
}

// ────────────────────── per-candidate scorer ──────────────────────

/** Weight of match/composite/offer in the "care" score. Caps at 1.0. */
function computeCare(c: AnchorCandidateInput): number {
  const matchPart = clamp(c.matchScore / 100, 0, 1) * 0.45;
  const compositePart = c.compositeScore !== null
    ? clamp(c.compositeScore / 100, 0, 1) * 0.35
    : 0;
  const offerPart = c.offerValueAnnual && c.offerValueAnnual > 0 ? 0.20 : 0;
  return clamp(matchPart + compositePart + offerPart, 0, 1);
}

function scoreOne(c: AnchorCandidateInput): AnchorCandidateScore {
  const signals = c.signals ?? defaultSignals();

  const axes: Record<AnchorAxis, number> = {
    recency:     recencyAxis(signals),
    cadence:     cadenceAxis(signals),
    reliability: reliabilityAxis(signals),
    pace:        paceAxis(signals, c.status),
    sentiment:   sentimentAxis(signals),
    competing:   competingAxis(signals),
  };

  const momentum = momentumFromAxes(axes);
  const risk = riskFromMomentum(momentum, signals);
  const tier = tierFromRisk(risk);
  const ghost = ghostProbability(risk, c.status);
  const care = computeCare(c);
  const halfLife = halfLifeDays(momentum, care);
  const drivers = harvestDrivers(axes, signals, c.status);
  const script = composeScript(c, tier, drivers[0]?.driver ?? null);

  // Salvage = care × (1 − ghost) mapped to 0..100. Multiplied by 100
  // so it reads like a ranking score, not a probability.
  const salvage = round(care * (1 - ghost) * 100);

  // Exposure: drafted offer at risk (ghost × total cash) + sunk cost
  // for pre-offer candidates whose ghost prob is meaningful.
  const draftedExposure = (c.offerValueAnnual ?? 0) * ghost;
  const preOfferExposure = c.offerValueAnnual ? 0 : PRE_OFFER_SUNK_COST * ghost;
  const exposureAnnual = round(draftedExposure + preOfferExposure);

  return {
    candidateId: c.candidateId,
    candidateName: c.candidateName,
    candidateTitle: c.candidateTitle,
    roleId: c.roleId,
    roleName: c.roleName,
    status: c.status,
    axes: {
      recency:     round(axes.recency),
      cadence:     round(axes.cadence),
      reliability: round(axes.reliability),
      pace:        round(axes.pace),
      sentiment:   round(axes.sentiment),
      competing:   round(axes.competing),
    },
    momentum: round(momentum),
    risk: round(risk),
    tier,
    ghostProbability: Math.round(ghost * 1000) / 1000,
    halfLifeDays: halfLife,
    care: Math.round(care * 1000) / 1000,
    salvageValue: salvage,
    exposureAnnual,
    drivers,
    script,
    signals,
    noteKeyphrase: signals.noteKeyphrase,
  };
}

function defaultSignals(): AnchorSignals {
  return {
    daysSinceLastTouch: 0,
    lastTouchDirection: 'out',
    responseLatencyHours: 6,
    rescheduleCount: 0,
    noShow: false,
    daysInStage: 0,
    competingPipelines: 0,
    sentimentTone: 'neutral',
    externalOffer: false,
    noteKeyphrase: null,
  };
}

// ────────────────────── public entrypoint ──────────────────────

export function analyzeAnchor(input: AnchorInput): AnchorSummary {
  const now = input.now ?? Date.now();

  // Terminal statuses aren't ghost-scorable — filter to actively-worked.
  const active = input.candidates.filter(c => c.status !== 'passed');

  const scores = active.map(scoreOne).sort((a, b) => b.risk - a.risk);

  const atRiskCount = scores.filter(s => s.risk >= TIER_THRESHOLDS.reengage).length;
  const criticalCount = scores.filter(s => s.risk >= TIER_THRESHOLDS.exec).length;
  const released = scores.filter(s => s.tier === 'release');
  const releasedCount = released.length;

  // Exposure summary — split so the UI can show ₹ from drafted offers
  // separately from the sunk-cost "we've been paying for this candidate
  // for weeks" preload.
  let exposureAnnual = 0;
  let exposurePreOffer = 0;
  for (const s of scores) {
    if (s.risk < TIER_THRESHOLDS.reengage) continue;
    // The score's `exposureAnnual` already includes both parts; we
    // re-split here for the UI headline.
    const c = active.find(a => a.candidateId === s.candidateId && a.roleId === s.roleId);
    if (c?.offerValueAnnual) exposureAnnual += s.exposureAnnual;
    else exposurePreOffer += s.exposureAnnual;
  }

  const salvageQueue = scores
    .filter(s => s.salvageValue > 5 && s.risk >= TIER_THRESHOLDS.ping)
    .sort((a, b) => b.salvageValue - a.salvageValue)
    .slice(0, 10);

  const criticalQueue = scores.filter(s => s.tier === 'exec' || s.tier === 'release');

  const byStage = computeStageBreakdown(scores);
  const driverHistogram = computeDriverHistogram(scores);
  const tierMix = computeTierMix(scores);

  const meanMomentum = safeMean(scores.map(s => s.momentum));
  const meanRisk = safeMean(scores.map(s => s.risk));

  const notes: string[] = [];
  if (scores.length === 0) {
    notes.push('No active candidates in the pipeline — Anchor lights up when at least one role has an active shortlist.');
  }
  if (releasedCount > 0) {
    notes.push(`${releasedCount} candidate${releasedCount === 1 ? '' : 's'} recommended for graceful close — export to Revive for future roles.`);
  }
  if (exposureAnnual > 0) {
    notes.push(`Drafted-offer exposure at risk: ₹${Math.round(exposureAnnual).toLocaleString('en-IN')}.`);
  }
  const salvageValueTotal = Math.round(salvageQueue.reduce((s, x) => s + x.salvageValue, 0));

  return {
    generatedAt: now,
    totals: {
      active: scores.length,
      atRisk: atRiskCount,
      critical: criticalCount,
      released: releasedCount,
      exposureAnnual: Math.round(exposureAnnual),
      exposurePreOffer: Math.round(exposurePreOffer),
      salvageableCount: salvageQueue.length,
      salvageValueTotal,
    },
    scores,
    salvageQueue,
    criticalQueue,
    byStage,
    driverHistogram,
    tierMix,
    meanMomentum: meanMomentum === null ? null : Math.round(meanMomentum),
    meanRisk: meanRisk === null ? null : Math.round(meanRisk),
    notes,
  };
}

function computeStageBreakdown(scores: AnchorCandidateScore[]): AnchorStageBreakdown[] {
  const map = new Map<PipelineStatus, AnchorStageBreakdown>();
  for (const s of scores) {
    const cur = map.get(s.status) ?? {
      status: s.status,
      count: 0,
      atRisk: 0,
      critical: 0,
      meanRisk: 0,
    };
    cur.count += 1;
    if (s.risk >= TIER_THRESHOLDS.reengage) cur.atRisk += 1;
    if (s.risk >= TIER_THRESHOLDS.exec) cur.critical += 1;
    cur.meanRisk += s.risk;
    map.set(s.status, cur);
  }
  const order: PipelineStatus[] = ['new', 'outreach', 'screening', 'interview', 'offer'];
  const out: AnchorStageBreakdown[] = [];
  for (const st of order) {
    const b = map.get(st);
    if (!b || b.count === 0) continue;
    out.push({
      ...b,
      meanRisk: Math.round(b.meanRisk / b.count),
    });
  }
  return out;
}

function computeDriverHistogram(scores: AnchorCandidateScore[]) {
  const counts = new Map<AnchorDriver, number>();
  for (const s of scores) {
    for (const d of s.drivers) {
      counts.set(d.driver, (counts.get(d.driver) ?? 0) + 1);
    }
  }
  const out = Array.from(counts.entries())
    .map(([driver, count]) => ({
      driver,
      label: DRIVER_LABEL[driver],
      count,
      hex: DRIVER_HEX[driver],
    }))
    .sort((a, b) => b.count - a.count);
  return out;
}

function computeTierMix(scores: AnchorCandidateScore[]): Record<AnchorTier, number> {
  const mix: Record<AnchorTier, number> = {
    hold: 0, ping: 0, reengage: 0, exec: 0, release: 0,
  };
  for (const s of scores) mix[s.tier] += 1;
  return mix;
}

// ────────────────────── rendering helpers ──────────────────────

/** Momentum ring — returns SVG dasharray/dashoffset for a stroked circle
 *  of `radius`. `momentum` in 0..100 maps to arc length. */
export function ringDashPair(momentum: number, radius: number): { dashArray: number; dashOffset: number } {
  const circ = 2 * Math.PI * radius;
  const pct = clamp(momentum, 0, 100) / 100;
  return { dashArray: circ, dashOffset: circ * (1 - pct) };
}

/** Tone→hex helper used by the UI. Mirrors reference.ts's map for
 *  visual consistency across surfaces. */
export const TONE_HEX: Record<string, string> = {
  sky:     '#0ea5e9',
  indigo:  '#6366f1',
  violet:  '#a855f7',
  amber:   '#f59e0b',
  emerald: '#10b981',
  rose:    '#f43f5e',
  slate:   '#94a3b8',
  cyan:    '#06b6d4',
  pink:    '#ec4899',
};

// ────────────────────── markdown export ──────────────────────

export function buildAnchorBrief(s: AnchorSummary): string {
  const L: string[] = [];
  L.push('# Anchor — Momentum & Drop-Off Risk');
  L.push('');
  L.push(
    `**Active**: ${s.totals.active} · **At risk**: ${s.totals.atRisk} · **Critical**: ${s.totals.critical} · **Released**: ${s.totals.released}`,
  );
  if (s.meanMomentum !== null && s.meanRisk !== null) {
    L.push(`**Mean momentum**: ${s.meanMomentum}/100 · **Mean risk**: ${s.meanRisk}/100`);
  }
  if (s.totals.exposureAnnual > 0) {
    L.push(`**Drafted-offer exposure**: ₹${s.totals.exposureAnnual.toLocaleString('en-IN')}`);
  }
  L.push('');
  L.push('## Salvage queue');
  if (s.salvageQueue.length === 0) {
    L.push('_No candidates need salvaging right now._');
  } else {
    for (const c of s.salvageQueue) {
      L.push(
        `- **${c.candidateName}** · ${c.roleName} · ${c.status} · risk ${c.risk} · ghost ${(c.ghostProbability * 100).toFixed(0)}% · **${TIER_LABEL[c.tier]}**`,
      );
      for (const d of c.drivers.slice(0, 3)) {
        L.push(`  - ${d.label}: ${d.detail}`);
      }
      L.push('');
      L.push('  Recommended nudge:');
      L.push('  ```');
      for (const line of c.script.body.split('\n')) L.push(`  ${line}`);
      L.push('  ```');
      L.push('');
    }
  }
  if (s.byStage.length > 0) {
    L.push('## Stage risk');
    for (const b of s.byStage) {
      L.push(`- **${b.status}** — ${b.count} active · ${b.atRisk} at risk · mean risk ${b.meanRisk}/100`);
    }
  }
  if (s.driverHistogram.length > 0) {
    L.push('');
    L.push('## Dominant drivers');
    for (const d of s.driverHistogram.slice(0, 5)) {
      L.push(`- **${d.label}** — ${d.count} occurrence${d.count === 1 ? '' : 's'}`);
    }
  }
  if (s.notes.length > 0) {
    L.push('');
    L.push('## Notes');
    for (const n of s.notes) L.push(`- ${n}`);
  }
  return L.join('\n');
}

// ────────────────────── defaults (UI palette payload) ──────────────────────

export function anchorDefaults() {
  return {
    tiers: TIER_ORDER.map(t => ({
      tier: t,
      label: TIER_LABEL[t],
      blurb: TIER_BLURB[t],
      hex: TIER_HEX[t],
      tone: TIER_TONE[t],
    })),
    axes: AXES.map(a => ({
      axis: a,
      label: AXIS_LABEL[a],
      weight: (AXIS_WEIGHTS as Record<string, number>)[a],
    })),
    drivers: (Object.keys(DRIVER_LABEL) as AnchorDriver[]).map(d => ({
      driver: d,
      label: DRIVER_LABEL[d],
      hex: DRIVER_HEX[d],
    })),
    thresholds: TIER_THRESHOLDS,
    stageBudgetDays: STAGE_BUDGET_DAYS,
    stageGhostPrior: STAGE_GHOST_PRIOR,
    recencyZeroDays: RECENCY_ZERO_DAYS,
    cadenceZeroHours: CADENCE_ZERO_HOURS,
    reliabilityFloor: RELIABILITY_FLOOR,
    externalOfferRiskBump: EXTERNAL_OFFER_RISK_BUMP,
    riskCeiling: RISK_CEILING,
    recoverFloor: RECOVER_FLOOR,
    preOfferSunkCost: PRE_OFFER_SUNK_COST,
  };
}
