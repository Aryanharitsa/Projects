// Anchor signal seed — deterministic per (candidateId, roleId, status).
//
// Pipeline shortlists in Credicrew live in localStorage; we don't yet have
// a message log, calendar log, or CRM. To make Anchor a full-fidelity demo
// out of the box, we synthesize the six signal streams from a stable hash
// of (candidateId, roleId, status). Same inputs → same signals, forever.
//
// The synthesis is intentionally *pipeline-realistic*, not uniformly
// random:
//   · Candidates in later stages have shorter daysSinceLastTouch on
//     average (recruiters keep offer-stage candidates warm).
//   · A subset of interview / offer stage candidates fire a competing-
//     pipeline signal — the closer to offer, the more competing offers.
//   · No-shows are rare (~5%), reschedules moderately common (~25%
//     with 1+).
//   · Sentiment tone leans warm at the top of funnel and cools as
//     stages age.
//   · A small fraction of offer-stage candidates get an external-offer
//     flag set — the classic "another company is closing them" signal.
//
// The bag of note keyphrases is short and hand-picked so drivers read
// like actual recruiter notes.

import type { PipelineStatus } from '@/lib/roles';
import type { AnchorSignals, SentimentTone } from '@/lib/anchor';

/**
 * Deterministic hash — mulberry32-style mix of the input bytes. Any two
 * of these seeds should decorrelate; this isn't a crypto primitive.
 */
function hashStr(s: string): number {
  let h = 2166136261 >>> 0;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619) >>> 0;
  }
  return h >>> 0;
}

/**
 * PRNG factory keyed on the composite seed. Returns a next(0..1) that is
 * stable across invocations for the same seed.
 */
function prng(seed: number): () => number {
  let s = seed >>> 0;
  return () => {
    // xorshift32
    s ^= s << 13; s >>>= 0;
    s ^= s >>> 17; s >>>= 0;
    s ^= s << 5;  s >>>= 0;
    return s / 4294967296;
  };
}

/** Bell-ish average of three uniforms — reduces the tail. */
function bell(next: () => number, lo: number, hi: number): number {
  return lo + ((next() + next() + next()) / 3) * (hi - lo);
}

function pick<T>(next: () => number, xs: T[]): T {
  return xs[Math.floor(next() * xs.length) % xs.length];
}

// Short bag of note keyphrases; picked so drivers read like real notes.
const NOTE_WARM = [
  'excited to keep talking',
  'loved the eng chat',
  'wants to move fast',
  'strong follow-up',
];

const NOTE_NEUTRAL = [
  'circle back next week',
  'waiting on team feedback',
  'reviewing the take-home',
  'considering options',
];

const NOTE_COOL = [
  'been busy this week',
  'may need more time',
  'weighing another offer',
  'not sure on timing',
  'family situation',
];

function keyphraseFor(next: () => number, tone: SentimentTone): string | null {
  const bag = tone === 'warm' ? NOTE_WARM : tone === 'cool' ? NOTE_COOL : NOTE_NEUTRAL;
  return pick(next, bag);
}

/**
 * Stage-conditioned signal seeder. The distributions are hand-tuned so a
 * blind demo lights up all five recovery tiers without a single-hot bias.
 */
export function seedSignals(
  candidateId: number,
  roleId: string,
  status: PipelineStatus,
  daysInStage: number,
): AnchorSignals {
  const seed = hashStr(`anchor:${candidateId}:${roleId}:${status}`);
  const next = prng(seed);

  // ── recency ────────────────────────────────────────────────
  // Later stages have shorter mean silence — recruiters guard them.
  const recencyMean =
    status === 'new'       ? 4 :
    status === 'outreach'  ? 5 :
    status === 'screening' ? 4 :
    status === 'interview' ? 3 :
    status === 'offer'     ? 2 :
    5;
  const daysSinceLastTouch = Math.max(0, Math.round(bell(next, 0, recencyMean * 2.4)));

  // Inbound share: candidates who reply frequently earn the "in"
  // direction. The higher the seed value, the more inbound-led.
  const lastTouchDirection: 'in' | 'out' = next() < 0.35 ? 'in' : 'out';

  // ── cadence ────────────────────────────────────────────────
  // Reply latency in hours. Warm candidates reply in 3–8h; cool ones
  // stretch to 30–50h. Correlated (weakly) with recency.
  const cadenceBase =
    status === 'offer' ? 4 :
    status === 'interview' ? 8 :
    status === 'screening' ? 14 :
    status === 'outreach' ? 20 :
    12;
  const responseLatencyHours = Math.max(
    1,
    Math.round(bell(next, cadenceBase * 0.4, cadenceBase * 3.2)),
  );

  // ── reliability ────────────────────────────────────────────
  // ~25% chance of at least one reschedule; heavier in later stages.
  const rescheduleRoll = next();
  const rescheduleCount =
    rescheduleRoll < 0.10 ? 2 :
    rescheduleRoll < 0.30 ? 1 :
    0;
  const noShow = next() < (status === 'interview' || status === 'offer' ? 0.06 : 0.03);

  // ── competing pipelines ───────────────────────────────────
  // Rises with stage — offer-stage candidates are almost always
  // shopping. Cap at 3.
  const competeRoll = next();
  const competeBase =
    status === 'offer' ? 1.5 :
    status === 'interview' ? 0.8 :
    status === 'screening' ? 0.4 :
    0.2;
  const competingPipelines = Math.min(
    3,
    Math.max(0, Math.round(competeBase + competeRoll * 1.5)),
  );

  // ── sentiment ─────────────────────────────────────────────
  // Tilt cool if reschedules or competing pipelines are high. Otherwise
  // roughly 30/50/20 warm/neutral/cool.
  let sentimentTone: SentimentTone = 'neutral';
  const sentimentRoll = next();
  if (rescheduleCount >= 2 || competingPipelines >= 2 || noShow) {
    sentimentTone = sentimentRoll < 0.6 ? 'cool' : 'neutral';
  } else if (daysSinceLastTouch <= 2 && rescheduleCount === 0) {
    sentimentTone = sentimentRoll < 0.55 ? 'warm' : 'neutral';
  } else {
    sentimentTone =
      sentimentRoll < 0.3 ? 'warm' :
      sentimentRoll < 0.8 ? 'neutral' :
      'cool';
  }

  // ── external offer ────────────────────────────────────────
  // Only meaningful at interview/offer stages, and only for a subset.
  const externalOffer =
    (status === 'offer' && next() < 0.30) ||
    (status === 'interview' && next() < 0.10);

  // ── note keyphrase ────────────────────────────────────────
  const noteKeyphrase = keyphraseFor(next, sentimentTone);

  return {
    daysSinceLastTouch,
    lastTouchDirection,
    responseLatencyHours,
    rescheduleCount,
    noShow,
    daysInStage: Math.max(0, Math.round(daysInStage)),
    competingPipelines,
    sentimentTone,
    externalOffer,
    noteKeyphrase,
  };
}

/**
 * Derive daysInStage from a shortlist entry's stageChangedAt (fallback
 * to addedAt). Returned as a rounded, non-negative day count.
 */
export function daysInStageFrom(
  stageChangedAt: number | undefined,
  addedAt: number,
  now: number,
): number {
  const t = stageChangedAt ?? addedAt;
  const days = (now - t) / 86_400_000;
  return Math.max(0, Math.round(days));
}
