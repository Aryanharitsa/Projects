// Compass — Loop Health Radar.
//
// Every prior surface in Credicrew answers a *local* question: this role's
// funnel, this candidate's shortlist score, this offer's peer parity, this
// panel's calibration. Compass sits above all of them and answers the one
// question a Head of Talent opens their week with — *is the whole loop
// healthy, or is it quietly leaking somewhere?*
//
// Six axes, each already earned by an upstream surface, each 0..100, each
// with a plain-English driver list and a deep-link:
//
//   1. Funnel        — portfolioHealth · reached-→-offer conversion (Portfolio)
//   2. Calibration   — icc after de-biasing · panel consensus (Calibration)
//   3. Predictiveness— rubric ↔ post-hire perf pearson (Hindsight)
//   4. Parity        — offer drift z-score, band adherence (Peer Parity)
//   5. Signal        — rejection ontology health, funnel waste (Verdict)
//   6. Channel       — ROI-weighted mean, diversification (Sources)
//
// Composite is the equal-weight mean over axes with data (so newly-opened
// workspaces don't crash to 20/100 because Hindsight has zero hires). The
// weakest axis becomes the top-of-page advice; the strongest becomes the
// bragging-rights chip.
//
// Every math constant is documented inline. The engine is pure — the page
// resolves upstream inputs and hands them in, keeping this byte-for-byte
// mirrorable in `backend/app/services/compass.py`.

import type { PortfolioSummary } from '@/lib/portfolio';
import type { CalibrationResult } from '@/lib/calibration';
import type { HindsightSummary } from '@/lib/hindsight';
import type { PeerParityResult } from '@/lib/peer_parity';
import type { VerdictPortfolio } from '@/lib/verdict';
import { HEALTH_LABEL as VERDICT_HEALTH_LABEL } from '@/lib/verdict';
import type { SourceSummary } from '@/lib/sources';

// ---------- taxonomy ----------

export const AXES = [
  'funnel',
  'calibration',
  'predictiveness',
  'parity',
  'signal',
  'channel',
] as const;

export type CompassAxis = (typeof AXES)[number];

export const AXIS_LABEL: Record<CompassAxis, string> = {
  funnel:         'Funnel',
  calibration:    'Calibration',
  predictiveness: 'Predictiveness',
  parity:         'Pay parity',
  signal:         'Signal',
  channel:        'Channel',
};

/** One-line "what does this axis mean" tooltip. */
export const AXIS_BLURB: Record<CompassAxis, string> = {
  funnel:         'How many roles are moving vs. stalling, and are candidates converting stage-to-stage.',
  calibration:    'How reliable your panels are and whether removing rater bias changes who you’d hire.',
  predictiveness: 'Whether the interview rubric actually correlated with post-hire performance.',
  parity:         'Whether new offers hold the pay band your accepted-peer offers established.',
  signal:         'Whether the rejection pile reads as JD tuning or as pool-quality — the shape of the graveyard.',
  channel:        'Whether the channels you’re sourcing from are producing hires per rupee spent.',
};

export const AXIS_ROUTE: Record<CompassAxis, string> = {
  funnel:         '/hq',
  calibration:    '/hq',      // no dedicated calibration page in the app router yet
  predictiveness: '/hindsight',
  parity:         '/hq',      // parity opens from a role's Offer Studio
  signal:         '/verdict',
  channel:        '/sources',
};

export const AXIS_HEX: Record<CompassAxis, string> = {
  funnel:         '#38bdf8',
  calibration:    '#a78bfa',
  predictiveness: '#34d399',
  parity:         '#f59e0b',
  signal:         '#fb7185',
  channel:        '#22d3ee',
};

export type CompassBand = 'critical' | 'warning' | 'stable' | 'strong' | 'unknown';

export const BAND_LABEL: Record<CompassBand, string> = {
  critical: 'Critical',
  warning:  'Warning',
  stable:   'Stable',
  strong:   'Strong',
  unknown:  'Insufficient data',
};

export const BAND_HEX: Record<CompassBand, string> = {
  critical: '#f43f5e',
  warning:  '#f59e0b',
  stable:   '#38bdf8',
  strong:   '#10b981',
  unknown:  '#475569',
};

// ---------- tuning constants ----------

/** Band cut-offs for a 0..100 axis score. */
const BAND_STRONG = 75;
const BAND_STABLE = 55;
const BAND_WARN = 35;

/** Ideal pass-share window; hurts symmetrically outside it. */
const PASS_SHARE_LOW = 0.35;
const PASS_SHARE_HIGH = 0.65;

/** A raw parity drift-score of 3.0 (severe) maps to 0/100. */
const PARITY_Z_CAP = 3.0;

/** Weight the composite carries if no axes have data. */
const MIN_AXES_FOR_COMPOSITE = 2;

// ---------- I/O shape ----------

export type CompassInput = {
  portfolio: PortfolioSummary;
  /** One CalibrationResult per role that has panel data (any depth). */
  calibration: CalibrationResult[];
  hindsight: HindsightSummary | null;
  /** One PeerParityResult per role that has a drafted offer + peer pool. */
  parity: PeerParityResult[];
  verdict: VerdictPortfolio;
  sources: SourceSummary;
  now?: number;
};

export type CompassAxisScore = {
  axis: CompassAxis;
  label: string;
  score: number | null;       // 0..100, null = insufficient data
  band: CompassBand;
  headline: string;           // one-sentence takeaway shown on the tile
  drivers: string[];          // 2-4 evidence bullets shown on hover / explain
  cta: { label: string; href: string };
  weight: number;             // relative weight inside the composite (0..1)
  sampleSize: number;         // the n that produced this score (0 → null score)
};

export type CompassAdvice = {
  axis: CompassAxis;
  severity: 'high' | 'medium' | 'low';
  headline: string;
  detail: string;
  cta: { label: string; href: string };
};

export type CompassSummary = {
  generatedAt: number;
  composite: number | null;
  band: CompassBand;
  coverage: number;           // 0..1 — share of axes with data
  weakest: CompassAxis | null;
  strongest: CompassAxis | null;
  axes: Record<CompassAxis, CompassAxisScore>;
  advice: CompassAdvice[];
  notes: string[];            // free-form contextual notes (e.g. "no hires logged yet")
};

// ---------- pure math ----------

function clamp(v: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, v));
}

function round(v: number): number { return Math.round(v); }

function bandFor(score: number | null): CompassBand {
  if (score === null) return 'unknown';
  if (score >= BAND_STRONG) return 'strong';
  if (score >= BAND_STABLE) return 'stable';
  if (score >= BAND_WARN) return 'warning';
  return 'critical';
}

function weightedMean(entries: Array<{ v: number; w: number }>): number | null {
  let s = 0;
  let w = 0;
  for (const e of entries) {
    if (Number.isFinite(e.v) && e.w > 0) {
      s += e.v * e.w;
      w += e.w;
    }
  }
  return w > 0 ? s / w : null;
}

// ---------- per-axis scorers ----------

/**
 * Funnel — how much of the shortlist is moving vs. how much is stuck. Uses
 * portfolioHealth (already 0..100 from the Portfolio engine) as the base,
 * then applies a stale-share penalty so ten dormant reqs can't hide behind
 * one healthy one.
 */
function scoreFunnel(portfolio: PortfolioSummary): CompassAxisScore {
  const { totals, portfolioHealth, funnel, bottleneck } = portfolio;

  if (totals.candidates === 0) {
    return {
      axis: 'funnel',
      label: AXIS_LABEL.funnel,
      score: null,
      band: 'unknown',
      headline: 'No candidates in the pipeline yet.',
      drivers: ['Add candidates to any role to light up the funnel.'],
      cta: { label: 'Open Command Center', href: AXIS_ROUTE.funnel },
      weight: 0.20,
      sampleSize: 0,
    };
  }

  const base = portfolioHealth ?? 50;
  const staleShare = totals.active > 0 ? totals.staleCandidates / totals.active : 0;
  const stalePenalty = clamp(staleShare * 40, 0, 25);
  const score = round(clamp(base - stalePenalty, 0, 100));

  const reachedOffer = funnel.find(f => f.key === 'offer')?.reached ?? 0;
  const topReached = funnel[0]?.reached ?? totals.candidates;
  const funnelPass = topReached > 0 ? reachedOffer / topReached : 0;

  const drivers = [
    `${totals.active} active · ${totals.offers} offer${totals.offers === 1 ? '' : 's'} out · ${totals.staleCandidates} stale (≥14d).`,
    `${round(funnelPass * 100)}% of the top of funnel has reached an offer.`,
    bottleneck
      ? `Bottleneck stage: ${bottleneck}.`
      : 'No single stage is holding the portfolio.',
  ];

  const headline =
    score >= BAND_STRONG
      ? 'The portfolio is moving.'
      : score >= BAND_STABLE
        ? 'Steady, with some drag.'
        : score >= BAND_WARN
          ? 'Meaningful drag in the pipeline.'
          : 'The funnel is stuck.';

  return {
    axis: 'funnel',
    label: AXIS_LABEL.funnel,
    score,
    band: bandFor(score),
    headline,
    drivers,
    cta: { label: 'Open Command Center', href: AXIS_ROUTE.funnel },
    weight: 0.20,
    sampleSize: totals.candidates,
  };
}

/**
 * Calibration — panel reliability. Uses iccCalibrated (post de-biasing)
 * because that's what "would the ranking change if bias were removed?"
 * actually measures. Blended with consensus (agreement across the pool).
 */
function scoreCalibration(results: CalibrationResult[]): CompassAxisScore {
  const usable = results.filter(r =>
    (r.iccCalibrated !== null || r.icc !== null || r.consensusIndex !== null) &&
    r.candidates.length > 0,
  );
  if (usable.length === 0) {
    return {
      axis: 'calibration',
      label: AXIS_LABEL.calibration,
      score: null,
      band: 'unknown',
      headline: 'No panel scorecards logged yet.',
      drivers: ['Rate at least two candidates on any panel to unlock calibration.'],
      cta: { label: 'Open panel', href: AXIS_ROUTE.calibration },
      weight: 0.15,
      sampleSize: 0,
    };
  }

  // Per-role axis: 0.55·icc + 0.45·consensus, both 0..100. Weight by
  // candidate-cell count so a role with a handful of ratings doesn't drown
  // out a real interview funnel.
  const perRole = usable.map(r => {
    const icc = r.iccCalibrated ?? r.icc ?? 0;
    const consensus = r.consensusIndex ?? 0;
    const v = clamp((icc * 0.55 + consensus * 0.45) * 100, 0, 100);
    const w = Math.max(1, r.candidates.length);
    return { v, w };
  });
  const raw = weightedMean(perRole) ?? 0;

  // Bias penalty — every additional biased rater above one costs 4 pts.
  const biased = usable.reduce((n, r) => n + (r.biasedRaters ?? 0), 0);
  const biasPenalty = clamp(Math.max(0, biased - 1) * 4, 0, 20);
  const score = round(clamp(raw - biasPenalty, 0, 100));

  const totalRaters = usable.reduce(
    (n, r) => n + r.raters.length, 0,
  );
  const avgConsensus = usable.reduce(
    (s, r) => s + (r.consensusIndex ?? 0), 0,
  ) / usable.length;
  const rankShifts = usable.reduce((n, r) => n + r.rankShiftCount, 0);

  const drivers = [
    `${usable.length} panel${usable.length === 1 ? '' : 's'} scored · ${totalRaters} interviewer${totalRaters === 1 ? '' : 's'} rated.`,
    `Mean consensus ${Math.round(avgConsensus * 100)}/100 across scored panels.`,
    biased > 0
      ? `${biased} rater${biased === 1 ? '' : 's'} flagged as lenient/severe/flat.`
      : 'No rater bias flags fired.',
    rankShifts > 0
      ? `${rankShifts} rank shift${rankShifts === 1 ? '' : 's'} after de-biasing — the ranking changed.`
      : 'De-biasing did not change the ranking.',
  ];

  const headline =
    score >= BAND_STRONG
      ? 'Panels agree; the ranking is trustworthy.'
      : score >= BAND_STABLE
        ? 'Panels roughly agree.'
        : score >= BAND_WARN
          ? 'Panel signal is noisy.'
          : 'Panels are unreliable — one rater is deciding it.';

  return {
    axis: 'calibration',
    label: AXIS_LABEL.calibration,
    score,
    band: bandFor(score),
    headline,
    drivers,
    cta: { label: 'Open Command Center', href: AXIS_ROUTE.calibration },
    weight: 0.15,
    sampleSize: totalRaters,
  };
}

/**
 * Predictiveness — did the rubric predict who succeeded? Blend of Pearson
 * (composite vs performance), hit-rate, and 1-Brier.
 */
function scorePredictiveness(h: HindsightSummary | null): CompassAxisScore {
  if (!h || h.hireCount === 0) {
    return {
      axis: 'predictiveness',
      label: AXIS_LABEL.predictiveness,
      score: null,
      band: 'unknown',
      headline: 'No hires logged yet.',
      drivers: ['Draft and accept an offer to feed Hindsight.'],
      cta: { label: 'Open Hindsight', href: AXIS_ROUTE.predictiveness },
      weight: 0.15,
      sampleSize: 0,
    };
  }

  // Pearson can be negative — treat that as *worse than random* so the
  // score floors at 0 rather than wrapping around.
  const pearsonPart = clamp(((h.pearson + 1) / 2) * 100, 0, 100);
  const hitPart = clamp(h.hitRate * 100, 0, 100);
  const brierPart = clamp((1 - h.brierScore) * 100, 0, 100);

  // 0.5 Pearson · 0.3 hit-rate · 0.2 (1-Brier). Anchored on Pearson because
  // it's the closest thing to "the rubric explained performance."
  const raw = 0.5 * pearsonPart + 0.3 * hitPart + 0.2 * brierPart;

  // Small-sample penalty — Pearson is unstable below 6 hires.
  const sampleFactor = clamp(h.hireCount / 8, 0.5, 1);
  const score = round(clamp(raw * sampleFactor, 0, 100));

  const drivers = [
    `${h.hireCount} hire${h.hireCount === 1 ? '' : 's'} scored (${h.realCount} real · ${h.syntheticCount} synthetic).`,
    `Composite ↔ performance Pearson = ${h.pearson.toFixed(2)}.`,
    `Hit rate ${Math.round(h.hitRate * 100)}% · Brier ${h.brierScore.toFixed(2)}.`,
    h.calibrationBand !== 'unknown'
      ? `Calibration band: ${h.calibrationBand}.`
      : 'Calibration band: not yet reliable.',
  ];

  const headline =
    score >= BAND_STRONG
      ? 'The rubric predicts who succeeds.'
      : score >= BAND_STABLE
        ? 'The rubric mostly predicts performance.'
        : score >= BAND_WARN
          ? 'The rubric is only weakly predictive.'
          : 'The rubric is not predicting performance.';

  return {
    axis: 'predictiveness',
    label: AXIS_LABEL.predictiveness,
    score,
    band: bandFor(score),
    headline,
    drivers,
    cta: { label: 'Open Hindsight', href: AXIS_ROUTE.predictiveness },
    weight: 0.15,
    sampleSize: h.hireCount,
  };
}

/**
 * Parity — are new offers holding the pay band established by accepted
 * peer offers? Score = 100 - z-based drift penalty - inversion penalty.
 */
function scoreParity(results: PeerParityResult[]): CompassAxisScore {
  const usable = results.filter(r => r.peerCount >= 3);
  if (usable.length === 0) {
    return {
      axis: 'parity',
      label: AXIS_LABEL.parity,
      score: null,
      band: 'unknown',
      headline: 'No offers to audit yet.',
      drivers: ['Draft an offer with at least three peer records to unlock parity.'],
      cta: { label: 'Open Command Center', href: AXIS_ROUTE.parity },
      weight: 0.15,
      sampleSize: 0,
    };
  }

  const perRole = usable.map(r => {
    // driftScore is max |z| across dims. Map z=0 → 100, z=3 → 0.
    const zScore = clamp(100 - (r.driftScore / PARITY_Z_CAP) * 100, 0, 100);
    // Inversion penalty — one severe (composite < peer, comp > peer) knocks
    // 15 pts off. Two knocks 25.
    const invPenalty = clamp(r.inversions.length * 12, 0, 30);
    // Out-of-band dims — proportional penalty.
    const oobShare = r.dims.length > 0 ? r.outOfBandCount / r.dims.length : 0;
    const oobPenalty = oobShare * 15;
    const v = clamp(zScore - invPenalty - oobPenalty, 0, 100);
    return { v, w: 1 };
  });
  const score = round(weightedMean(perRole) ?? 0);

  const totalInversions = usable.reduce((n, r) => n + r.inversions.length, 0);
  const avgDrift = usable.reduce((s, r) => s + r.driftScore, 0) / usable.length;
  const verdictCounts: Record<string, number> = {};
  for (const r of usable) {
    verdictCounts[r.verdict] = (verdictCounts[r.verdict] ?? 0) + 1;
  }

  const drivers = [
    `${usable.length} offer${usable.length === 1 ? '' : 's'} audited against peer pools.`,
    `Mean drift z = ${avgDrift.toFixed(2)} (band cap 3.0).`,
    totalInversions > 0
      ? `${totalInversions} composite↔comp inversion${totalInversions === 1 ? '' : 's'} vs. accepted peers.`
      : 'No composite↔comp inversions detected.',
    `Verdict mix: ${Object.entries(verdictCounts).map(([k, v]) => `${v} ${k}`).join(' · ') || 'n/a'}.`,
  ];

  const headline =
    score >= BAND_STRONG
      ? 'Offers are inside the band.'
      : score >= BAND_STABLE
        ? 'Offers drift a little but the band holds.'
        : score >= BAND_WARN
          ? 'The pay band is drifting.'
          : 'Pay-band discipline is broken.';

  return {
    axis: 'parity',
    label: AXIS_LABEL.parity,
    score,
    band: bandFor(score),
    headline,
    drivers,
    cta: { label: 'Open Command Center', href: AXIS_ROUTE.parity },
    weight: 0.10,
    sampleSize: usable.length,
  };
}

/**
 * Signal — does the graveyard read as JD tuning or as pool quality? Uses
 * signalHealth (bucketed), pass-share window, and funnel waste.
 */
function scoreSignal(v: VerdictPortfolio): CompassAxisScore {
  if (v.totalConsidered === 0) {
    return {
      axis: 'signal',
      label: AXIS_LABEL.signal,
      score: null,
      band: 'unknown',
      headline: 'Nothing shortlisted yet.',
      drivers: ['Shortlist candidates on a role to compute rejection signal.'],
      cta: { label: 'Open Verdict', href: AXIS_ROUTE.signal },
      weight: 0.15,
      sampleSize: 0,
    };
  }

  // Base score from signalHealth bucket.
  const bucket: Record<string, number> = {
    healthy:    90,
    mixed:      65,
    spec_leak:  45,
    overfished: 30,
    unknown:    50,
  };
  const raw = bucket[v.signalHealth] ?? 50;

  // Pass-share window penalty — extremes on either side hurt symmetrically.
  const ps = v.passShare;
  let windowPenalty = 0;
  if (ps < PASS_SHARE_LOW) {
    windowPenalty = (PASS_SHARE_LOW - ps) * 60; // very few rejects = suspicious
  } else if (ps > PASS_SHARE_HIGH) {
    windowPenalty = (ps - PASS_SHARE_HIGH) * 60; // rejecting almost everyone
  }
  // Funnel waste — high mean composite of rejected pool means we passed on
  // strong candidates. Small penalty (max 15 pts).
  const wastePenalty = clamp((v.funnelWaste - 60) / 40, 0, 1) * 15;

  const score = round(clamp(raw - windowPenalty - wastePenalty, 0, 100));

  const drivers = [
    `${v.totalPassed} of ${v.totalConsidered} shortlisted passed (${Math.round(ps * 100)}%).`,
    `Signal reads as: ${VERDICT_HEALTH_LABEL[v.signalHealth] ?? v.signalHealth}.`,
    v.topReason ? `Top rejection reason: ${v.topReason.replace(/_/g, ' ')}.` : 'No dominant rejection reason.',
    `Funnel waste (mean composite of passed pool): ${v.funnelWaste}/100.`,
  ];

  const headline =
    v.signalHealth === 'healthy'
      ? 'The graveyard reads as tuned JD tuning.'
      : v.signalHealth === 'spec_leak'
        ? 'JD spec leak — rewrite the ask.'
        : v.signalHealth === 'overfished'
          ? 'Pool is fished out — open new channels.'
          : v.signalHealth === 'mixed'
            ? 'Mixed rejection signals.'
            : 'Not enough passed candidates to read.';

  return {
    axis: 'signal',
    label: AXIS_LABEL.signal,
    score,
    band: bandFor(score),
    headline,
    drivers,
    cta: { label: 'Open Verdict', href: AXIS_ROUTE.signal },
    weight: 0.15,
    sampleSize: v.totalPassed,
  };
}

/**
 * Channel — is the sourcing mix producing hires per rupee? Blend of top-ROI
 * mean and diversification (so a "one-hot" pipeline that relies entirely on
 * referrals still shows the concentration risk).
 */
function scoreChannel(s: SourceSummary): CompassAxisScore {
  const active = s.byChannel.filter(c => c.count > 0);
  if (active.length === 0) {
    return {
      axis: 'channel',
      label: AXIS_LABEL.channel,
      score: null,
      band: 'unknown',
      headline: 'No channel activity yet.',
      drivers: ['Attribute at least one candidate to a channel.'],
      cta: { label: 'Open Sources', href: AXIS_ROUTE.channel },
      weight: 0.10,
      sampleSize: 0,
    };
  }

  // Volume-weighted ROI across channels (0..100).
  const roiEntries = active.map(c => ({ v: c.roi, w: Math.max(1, c.count) }));
  const roi = weightedMean(roiEntries) ?? 0;
  // Diversification is 0..1; blend at 0.25 weight.
  const raw = roi * 0.75 + s.diversification * 100 * 0.25;
  // Cost efficiency — if we have a costPerOffer, penalize > ₹500k / hire (a
  // rough India-market severity floor).
  let costPenalty = 0;
  if (s.costPerOffer !== null && s.costPerOffer > 0) {
    costPenalty = clamp((s.costPerOffer - 500) / 500, 0, 1) * 10;
  }
  const score = round(clamp(raw - costPenalty, 0, 100));

  const drivers = [
    `${active.length} channel${active.length === 1 ? '' : 's'} active · ${s.totalCandidates} total attributed.`,
    `Volume-weighted mean ROI: ${Math.round(roi)}/100.`,
    `Channel diversification: ${Math.round(s.diversification * 100)}/100 (Shannon entropy).`,
    s.bestChannel
      ? `Best channel: ${s.bestChannel.replace(/_/g, ' ')}${s.worstChannel && s.worstChannel !== s.bestChannel ? ` · cut: ${s.worstChannel.replace(/_/g, ' ')}` : ''}.`
      : 'No standout channel yet.',
  ];

  const headline =
    score >= BAND_STRONG
      ? 'Channels are efficient and diversified.'
      : score >= BAND_STABLE
        ? 'Channels work; the mix could tighten.'
        : score >= BAND_WARN
          ? 'Channel ROI is weak or concentrated.'
          : 'Sourcing spend isn’t returning hires.';

  return {
    axis: 'channel',
    label: AXIS_LABEL.channel,
    score,
    band: bandFor(score),
    headline,
    drivers,
    cta: { label: 'Open Sources', href: AXIS_ROUTE.channel },
    weight: 0.10,
    sampleSize: s.totalCandidates,
  };
}

// ---------- advice ----------

function severityFromBand(b: CompassBand): 'high' | 'medium' | 'low' {
  if (b === 'critical') return 'high';
  if (b === 'warning') return 'medium';
  return 'low';
}

const AXIS_ADVICE: Record<CompassAxis, string> = {
  funnel:
    'Open Command Center, filter by "stale + non-terminal," and either send a nudge, book a slot, or pass. Stalled candidates are your cheapest recovery — you’ve already paid to source them.',
  calibration:
    'Open the panel for the noisiest role (highest rank-shift count), drop or retrain the flagged rater, and re-score the remaining panel on the top three shortlist candidates before the next loop.',
  predictiveness:
    'Open Hindsight, apply the recommended 50/50 rubric reweighting, and roll the drop-list dimensions out of the interview kit for next quarter. Weak-signal dims are wasting panel minutes.',
  parity:
    'Open the offer with the highest drift z. Either bring it inside the band with a base + sign-on rebalance, or log the exception (with a written reason) so the peer pool learns the outlier.',
  signal:
    'Open Verdict, apply the top-impact refinement — most often "open the role to remote" or "move a nice-to-have skill out of the required list." Confirm the recovered candidates are actually shortlist-worthy before shipping the plan delta.',
  channel:
    'Open Sources. Cut spend on the "cut"-banded channel first (highest cost-per-offer with zero conversion), reinvest into the top-ROI channel, and start one experiment channel to break concentration risk.',
};

function buildAdvice(axes: CompassAxisScore[]): CompassAdvice[] {
  const usable = axes.filter(a => a.score !== null);
  if (usable.length === 0) return [];
  const sorted = usable.slice().sort((a, b) => (a.score! - b.score!));
  return sorted
    .filter(a => a.band !== 'strong')
    .slice(0, 3)
    .map(a => ({
      axis: a.axis,
      severity: severityFromBand(a.band),
      headline: `${a.label} — ${a.score}/100 (${BAND_LABEL[a.band].toLowerCase()})`,
      detail: AXIS_ADVICE[a.axis],
      cta: a.cta,
    }));
}

// ---------- public entrypoint ----------

export function analyzeCompass(input: CompassInput): CompassSummary {
  const now = input.now ?? Date.now();

  const axes: Record<CompassAxis, CompassAxisScore> = {
    funnel:         scoreFunnel(input.portfolio),
    calibration:    scoreCalibration(input.calibration),
    predictiveness: scorePredictiveness(input.hindsight),
    parity:         scoreParity(input.parity),
    signal:         scoreSignal(input.verdict),
    channel:        scoreChannel(input.sources),
  };

  const list = AXES.map(a => axes[a]);
  const withScore = list.filter(a => a.score !== null);
  const coverage = list.length > 0 ? withScore.length / list.length : 0;

  let composite: number | null = null;
  if (withScore.length >= MIN_AXES_FOR_COMPOSITE) {
    const entries = withScore.map(a => ({ v: a.score as number, w: a.weight }));
    composite = round(weightedMean(entries) ?? 0);
  }
  const band = bandFor(composite);

  let weakest: CompassAxis | null = null;
  let strongest: CompassAxis | null = null;
  if (withScore.length > 0) {
    let low = 101, high = -1;
    for (const a of withScore) {
      if ((a.score as number) < low) { low = a.score as number; weakest = a.axis; }
      if ((a.score as number) > high) { high = a.score as number; strongest = a.axis; }
    }
  }

  const notes: string[] = [];
  if (withScore.length < AXES.length) {
    const missing = list.filter(a => a.score === null).map(a => a.label.toLowerCase());
    notes.push(`Composite excludes ${missing.length} axis${missing.length === 1 ? '' : 'es'}: ${missing.join(', ')}.`);
  }
  if (withScore.length < MIN_AXES_FOR_COMPOSITE) {
    notes.push(`Need at least ${MIN_AXES_FOR_COMPOSITE} axes with data to compute a composite.`);
  }
  if (input.hindsight && input.hindsight.hireCount > 0 && input.hindsight.realCount === 0) {
    notes.push('All Hindsight outcomes are synthetic; log real performance to sharpen predictiveness.');
  }

  return {
    generatedAt: now,
    composite,
    band,
    coverage,
    weakest,
    strongest,
    axes,
    advice: buildAdvice(list),
    notes,
  };
}

// ---------- rendering helpers ----------

/** SVG polygon points for a hexagonal radar with N-axis scoring. */
export function radarPolygonPoints(
  scores: Array<number | null>,
  cx: number,
  cy: number,
  r: number,
): string {
  const n = scores.length;
  const pts: string[] = [];
  for (let i = 0; i < n; i++) {
    const s = scores[i];
    const t = s === null ? 0.05 : Math.max(0.02, s / 100); // never render at origin
    const theta = -Math.PI / 2 + (i * 2 * Math.PI) / n;
    const x = cx + Math.cos(theta) * r * t;
    const y = cy + Math.sin(theta) * r * t;
    pts.push(`${x.toFixed(1)},${y.toFixed(1)}`);
  }
  return pts.join(' ');
}

/** Positions of the axis labels on the radar (outside the outermost ring). */
export function radarAxisAnchors(
  n: number,
  cx: number,
  cy: number,
  r: number,
): Array<{ x: number; y: number; anchor: 'start' | 'middle' | 'end' }> {
  const out: Array<{ x: number; y: number; anchor: 'start' | 'middle' | 'end' }> = [];
  for (let i = 0; i < n; i++) {
    const theta = -Math.PI / 2 + (i * 2 * Math.PI) / n;
    const x = cx + Math.cos(theta) * (r + 18);
    const y = cy + Math.sin(theta) * (r + 18);
    let anchor: 'start' | 'middle' | 'end' = 'middle';
    if (Math.cos(theta) > 0.3) anchor = 'start';
    else if (Math.cos(theta) < -0.3) anchor = 'end';
    out.push({ x, y, anchor });
  }
  return out;
}

// ---------- exportable brief ----------

export function buildCompassBrief(s: CompassSummary): string {
  const L: string[] = [];
  L.push('# Loop Health — Compass');
  L.push('');
  L.push(
    `**Composite**: ${s.composite ?? '—'}/100 · ${BAND_LABEL[s.band]} · coverage ${Math.round(s.coverage * 100)}%`,
  );
  L.push('');
  L.push('## Axes');
  for (const a of AXES) {
    const axis = s.axes[a];
    L.push(
      `- **${axis.label}** — ${axis.score === null ? 'n/a' : `${axis.score}/100`} · ${BAND_LABEL[axis.band]}`,
    );
    L.push(`  - ${axis.headline}`);
    for (const d of axis.drivers) L.push(`  - ${d}`);
  }
  if (s.advice.length > 0) {
    L.push('');
    L.push('## Recommended moves');
    for (const a of s.advice) {
      L.push(`1. **${a.headline}**`);
      L.push(`   ${a.detail}`);
    }
  }
  if (s.notes.length > 0) {
    L.push('');
    L.push('## Notes');
    for (const n of s.notes) L.push(`- ${n}`);
  }
  return L.join('\n');
}
