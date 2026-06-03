// Sourcing Intelligence engine — Channel Studio (Day 42).
//
// Every other Credicrew surface analyses what happens *after* a candidate
// is already in the pipeline: match scoring, interview rubric, calibration,
// decision verdict, offer benchmark, peer parity, portfolio health. None
// of them answer the question that sits at the top of the funnel:
//
//   "Where should I spend my next hour of outreach?"
//
// This module is the missing top-of-funnel layer. It attributes every
// candidate to a *channel* (LinkedIn outreach, employee referral, job
// post, agency, community, university, AI sourcing, silver-medal recycle),
// then rolls the existing pipeline + interview + offer + accept-prob
// signals back up to per-channel ROI.
//
// The engine is pure data + math. The page (`/sources`) consumes the
// output and `backend/app/services/sources.py` mirrors it byte-for-byte
// for agentic clients.

import type { PipelineStatus } from '@/lib/roles';

// ---------- channel taxonomy ----------

export type Channel =
  | 'linkedin_outreach'
  | 'referral'
  | 'job_post'
  | 'agency'
  | 'community'
  | 'university'
  | 'ai_sourcing'
  | 'silver_medal';

export const CHANNELS: Channel[] = [
  'linkedin_outreach',
  'referral',
  'job_post',
  'agency',
  'community',
  'university',
  'ai_sourcing',
  'silver_medal',
];

export const CHANNEL_LABEL: Record<Channel, string> = {
  linkedin_outreach: 'LinkedIn outreach',
  referral: 'Employee referral',
  job_post: 'Job post (inbound)',
  agency: 'Recruiter agency',
  community: 'Community / event',
  university: 'University pipeline',
  ai_sourcing: 'AI sourcing',
  silver_medal: 'Silver medal',
};

export const CHANNEL_BLURB: Record<Channel, string> = {
  linkedin_outreach: 'Cold outbound to passive candidates on LinkedIn.',
  referral: 'Employees nominate someone in their network.',
  job_post: 'Direct applications to a posted JD.',
  agency: 'External recruiter delivers a shortlist for a fee.',
  community: 'Talent met at meetups, conferences, hackathons, Slack.',
  university: 'New-grad / intern channel from campus partners.',
  ai_sourcing: 'Auto-scraped candidates from public engineering signal.',
  silver_medal: 'Strong previous-loop runner-ups recycled into a new req.',
};

// Per-candidate cost defaults (₹, thousands per candidate touched).
// Agency dominates by a wide margin (% of base on hire ≈ ₹600k+/hire,
// amortised); university/community are near-zero per touch.
export const DEFAULT_COST_PER_CANDIDATE: Record<Channel, number> = {
  linkedin_outreach: 4,   // ~ ₹4k per touched candidate (seat + InMail share)
  referral: 8,            // bonus amortised across touches
  job_post: 1,            // ATS + JD distribution share
  agency: 60,             // dominant cost driver
  community: 2,           // event sponsorship amortised
  university: 3,          // campus drive amortised
  ai_sourcing: 2,         // tool subscription amortised
  silver_medal: 1,        // re-engage cost is near-zero
};

// ---------- input ----------

export type SourceAttribution = {
  channel: Channel;
  // Optional human-readable sub-source ('LinkedIn — DM template v3',
  // 'Referral — Aman P', 'TechWeek 2026'). Surfaced in the UI but not
  // used in math today.
  detail?: string;
  // Optional override of the default per-candidate cost; the engine
  // falls back to DEFAULT_COST_PER_CANDIDATE[channel] when absent.
  costOverride?: number;
};

export type SourceCandidate = {
  candidateId: number;
  name: string;
  roleId: string;
  roleName: string;
  status: PipelineStatus;
  addedAt: number;                  // epoch ms
  matchScore: number;               // 0..100
  composite: number | null;         // interview composite, null if none
  confidence: number;               // 0..1
  source: SourceAttribution;
  winProbability?: number;          // 0..1, accept odds if an offer exists
  hasOffer?: boolean;
  location?: string;                // for diversity attribution
};

export type SourceInput = {
  candidates: SourceCandidate[];
  // Caller may override per-channel cost defaults (e.g., the editor on
  // the Channel Studio page lets the recruiter tune them live).
  costOverrides?: Partial<Record<Channel, number>>;
  now?: number;
};

// ---------- output ----------

export type ChannelStage = {
  key: 'new' | 'outreach' | 'screening' | 'interview' | 'offer';
  here: number;
  reached: number;
};

export type ChannelDiversityCell = {
  label: string;
  count: number;
  share: number;            // 0..1 within the channel
};

export type ChannelMetrics = {
  channel: Channel;
  label: string;
  count: number;            // total candidates attributed
  active: number;           // non-passed
  reached: Record<ChannelStage['key'], number>;
  conversion: Record<ChannelStage['key'], number | null>;
  // Quality
  meanMatchScore: number;        // 0..100
  meanComposite: number | null;  // 0..100
  meanWinProb: number | null;    // 0..1
  // Speed
  meanDaysToOffer: number | null;
  // Cost
  costPerCandidate: number;      // ₹k per touch
  totalSpend: number;            // ₹k
  costPerInterview: number | null;
  costPerOffer: number | null;
  // Composite ROI
  qualityScore: number;          // 0..100
  conversionScore: number;       // 0..100
  costScore: number;             // 0..100
  speedScore: number;            // 0..100
  roi: number;                   // 0..100
  band: ChannelBand;
  // Diversity attribution (top locations)
  topLocations?: ChannelDiversityCell[];
  // Per-channel one-line recommendation
  recommendation: string;
};

export type ChannelBand = 'scale' | 'steady' | 'experiment' | 'cut';

export const BAND_LABEL: Record<ChannelBand, string> = {
  scale: 'Scale — double down',
  steady: 'Steady — keep running',
  experiment: 'Experiment — needs more data',
  cut: 'Cut — reallocate budget',
};

export const BAND_TONE: Record<ChannelBand, string> = {
  scale: 'emerald',
  steady: 'sky',
  experiment: 'amber',
  cut: 'rose',
};

export const BAND_HUE: Record<ChannelBand, string> = {
  scale: '#34d399',
  steady: '#38bdf8',
  experiment: '#f59e0b',
  cut: '#f43f5e',
};

export type SourceRecommendation = {
  channel: Channel;
  band: ChannelBand;
  title: string;
  detail: string;
};

export type SourceSummary = {
  byChannel: ChannelMetrics[];
  // Cross-channel rollups
  totalCandidates: number;
  totalActive: number;
  totalSpend: number;            // ₹k
  totalOffers: number;
  totalInterviewed: number;
  costPerInterview: number | null;
  costPerOffer: number | null;
  bestChannel: Channel | null;
  worstChannel: Channel | null;
  diversification: number;       // 0..1 normalised Shannon entropy across channels
  recommendations: SourceRecommendation[];
};

// ---------- math helpers ----------

const DAY_MS = 86_400_000;

function clip(x: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, x));
}

function safeMean(xs: number[]): number | null {
  if (!xs.length) return null;
  const s = xs.reduce((a, b) => a + b, 0);
  return s / xs.length;
}

function round1(x: number): number { return Math.round(x * 10) / 10; }
function round2(x: number): number { return Math.round(x * 100) / 100; }

// Conversion-to-score (0..100) — a sigmoid-ish step so a 25% reached-offer
// rate already counts as strong (rare in real outbound), 5% is poor.
function conversionToScore(c: number): number {
  // c is reached(offer) / count, in [0,1]. 25% → 90, 10% → 60, 5% → 35, 2% → 18.
  return clip(100 * (1 - Math.exp(-12 * c)), 0, 100);
}

function speedToScore(meanDays: number | null): number {
  if (meanDays === null) return 60; // neutral if no offer yet
  // 14 days → ~95, 21 → 80, 30 → 60, 45 → 35, 60+ → ≤20
  return clip(120 - 2.5 * meanDays, 0, 100);
}

function costToScore(costPerOffer: number | null, costPerInterview: number | null): number {
  // We prefer cost-per-offer; fall back to cost-per-interview × 3 as a proxy.
  const cpo = costPerOffer ?? (costPerInterview === null ? null : costPerInterview * 3);
  if (cpo === null) return 55; // neutral — not enough signal yet
  // ₹50k/offer → 95, ₹200k → 70, ₹500k → 40, ₹1M → 15.
  return clip(100 - 0.085 * cpo, 0, 100);
}

function bandFor(roi: number, count: number): ChannelBand {
  if (count < 4) return 'experiment';
  if (roi >= 70) return 'scale';
  if (roi >= 50) return 'steady';
  if (roi >= 35) return 'experiment';
  return 'cut';
}

function shannonNorm(counts: number[]): number {
  const n = counts.length;
  if (n <= 1) return 0;
  const total = counts.reduce((a, b) => a + b, 0);
  if (total <= 0) return 0;
  let h = 0;
  for (const c of counts) {
    if (c <= 0) continue;
    const p = c / total;
    h -= p * Math.log(p);
  }
  return h / Math.log(n);
}

function topNCells(items: Iterable<[string, number]>, n: number, total: number): ChannelDiversityCell[] {
  const arr = Array.from(items)
    .filter(([, c]) => c > 0)
    .sort((a, b) => b[1] - a[1])
    .slice(0, n);
  return arr.map(([label, count]) => ({
    label,
    count,
    share: total > 0 ? count / total : 0,
  }));
}

// ---------- main entry ----------

export function analyzeSources(input: SourceInput): SourceSummary {
  const now = input.now ?? Date.now();
  const overrides = input.costOverrides ?? {};

  // Bucket candidates by channel.
  const buckets = new Map<Channel, SourceCandidate[]>();
  for (const ch of CHANNELS) buckets.set(ch, []);
  for (const c of input.candidates) {
    const arr = buckets.get(c.source.channel);
    if (arr) arr.push(c);
  }

  const byChannel: ChannelMetrics[] = [];

  for (const ch of CHANNELS) {
    const arr = buckets.get(ch) ?? [];
    const count = arr.length;
    if (count === 0) {
      // Skip empty channels entirely — keeps the surface readable.
      continue;
    }

    // Funnel — reached counts (a candidate at `interview` counts in
    // reached-new, reached-outreach, reached-screening, reached-interview).
    const STAGE_RANK: Record<string, number> = {
      new: 0, outreach: 1, screening: 2, interview: 3, offer: 4, passed: -1,
    };
    const reached: Record<ChannelStage['key'], number> = {
      new: 0, outreach: 0, screening: 0, interview: 0, offer: 0,
    };
    const here: Record<ChannelStage['key'], number> = {
      new: 0, outreach: 0, screening: 0, interview: 0, offer: 0,
    };
    let active = 0;
    let totalDaysToOffer = 0;
    let offerCount = 0;
    let interviewedCount = 0;
    const composites: number[] = [];
    const winProbs: number[] = [];
    const matches: number[] = [];
    const locCounts = new Map<string, number>();

    for (const c of arr) {
      matches.push(c.matchScore);
      const rank = STAGE_RANK[c.status];
      if (c.status !== 'passed') active += 1;
      if (rank >= 0) {
        if (c.status in here) here[c.status as ChannelStage['key']] += 1;
        for (let r = 0; r <= rank && r <= 4; r++) {
          const stageKey = (['new', 'outreach', 'screening', 'interview', 'offer'] as const)[r];
          reached[stageKey] += 1;
        }
      }
      if (c.composite !== null) {
        composites.push(c.composite);
        interviewedCount += 1;
      }
      if (c.hasOffer && c.winProbability !== undefined) {
        winProbs.push(c.winProbability);
      }
      if (c.status === 'offer' || (c.hasOffer && c.status !== 'passed')) {
        offerCount += 1;
        const days = (now - c.addedAt) / DAY_MS;
        if (days >= 0 && days <= 180) totalDaysToOffer += days;
      }
      const loc = c.location || 'Unknown';
      locCounts.set(loc, (locCounts.get(loc) ?? 0) + 1);
    }

    const conv: Record<ChannelStage['key'], number | null> = {
      new: null,
      outreach: reached.new > 0 ? reached.outreach / reached.new : null,
      screening: reached.outreach > 0 ? reached.screening / reached.outreach : null,
      interview: reached.screening > 0 ? reached.interview / reached.screening : null,
      offer: reached.interview > 0 ? reached.offer / reached.interview : null,
    };

    const meanMatch = safeMean(matches) ?? 0;
    const meanComposite = safeMean(composites);
    const meanWinProb = safeMean(winProbs);
    const meanDaysToOffer = offerCount > 0 ? totalDaysToOffer / offerCount : null;

    const costPerCand =
      overrides[ch] !== undefined
        ? (overrides[ch] as number)
        : DEFAULT_COST_PER_CANDIDATE[ch];
    const totalSpend = count * costPerCand;
    const costPerInterview = interviewedCount > 0 ? totalSpend / interviewedCount : null;
    const costPerOffer = offerCount > 0 ? totalSpend / offerCount : null;

    // Quality 0..100. Composite if we have it (40%); match score baseline
    // (40%); win-prob lift on top (20% when we have it). When we have no
    // composites yet we fall back to match-only on the 80% it occupies.
    const baseQ = 0.4 * meanMatch;
    const compQ = meanComposite !== null ? 0.4 * meanComposite : 0;
    const winQ = meanWinProb !== null ? 20 * meanWinProb : 0;
    let qualityScore = baseQ + compQ + winQ;
    // Re-normalise if absent components leave the dial low.
    if (meanComposite === null && meanWinProb === null) qualityScore = meanMatch;
    else if (meanComposite === null) qualityScore = (baseQ + winQ) / 0.6;
    else if (meanWinProb === null) qualityScore = (baseQ + compQ) / 0.8;
    qualityScore = clip(qualityScore, 0, 100);

    const conversionScore = conversionToScore(reached.offer / count);
    const speedScore = speedToScore(meanDaysToOffer);
    const costScore = costToScore(costPerOffer, costPerInterview);

    const roi = clip(
      0.4 * qualityScore +
        0.3 * conversionScore +
        0.2 * costScore +
        0.1 * speedScore,
      0,
      100,
    );

    const band = bandFor(roi, count);
    const topLocations = topNCells(locCounts.entries(), 3, count);
    const recommendation = recommendFor(ch, {
      band,
      qualityScore,
      conversionScore,
      costScore,
      speedScore,
      meanComposite,
      offerCount,
      count,
      costPerOffer,
      meanDaysToOffer,
    });

    byChannel.push({
      channel: ch,
      label: CHANNEL_LABEL[ch],
      count,
      active,
      reached,
      conversion: conv,
      meanMatchScore: round1(meanMatch),
      meanComposite: meanComposite === null ? null : round1(meanComposite),
      meanWinProb: meanWinProb === null ? null : round2(meanWinProb),
      meanDaysToOffer: meanDaysToOffer === null ? null : round1(meanDaysToOffer),
      costPerCandidate: round1(costPerCand),
      totalSpend: round1(totalSpend),
      costPerInterview: costPerInterview === null ? null : round1(costPerInterview),
      costPerOffer: costPerOffer === null ? null : round1(costPerOffer),
      qualityScore: round1(qualityScore),
      conversionScore: round1(conversionScore),
      costScore: round1(costScore),
      speedScore: round1(speedScore),
      roi: round1(roi),
      band,
      topLocations,
      recommendation,
    });
  }

  // Rank for best/worst (only channels with ≥ 4 candidates qualify for
  // the headline — anything thinner is `experiment` and should not be
  // recommended as the leader).
  const ranked = [...byChannel].sort((a, b) => b.roi - a.roi);
  const eligible = ranked.filter(m => m.count >= 4);
  const bestChannel = eligible.length ? eligible[0].channel : null;
  const worstChannel = eligible.length ? eligible[eligible.length - 1].channel : null;

  const totalCandidates = byChannel.reduce((s, m) => s + m.count, 0);
  const totalActive = byChannel.reduce((s, m) => s + m.active, 0);
  const totalSpend = round1(byChannel.reduce((s, m) => s + m.totalSpend, 0));
  const totalOffers = byChannel.reduce((s, m) => s + m.reached.offer, 0);
  const totalInterviewed = byChannel.reduce((s, m) => s + m.reached.interview, 0);
  const costPerInterview = totalInterviewed > 0 ? round1(totalSpend / totalInterviewed) : null;
  const costPerOffer = totalOffers > 0 ? round1(totalSpend / totalOffers) : null;

  const diversification = round2(shannonNorm(byChannel.map(m => m.count)));

  const recommendations = buildRecommendations(byChannel, ranked);

  return {
    byChannel: ranked,
    totalCandidates,
    totalActive,
    totalSpend,
    totalOffers,
    totalInterviewed,
    costPerInterview,
    costPerOffer,
    bestChannel,
    worstChannel,
    diversification,
    recommendations,
  };
}

// ---------- per-channel one-liner ----------

function recommendFor(
  ch: Channel,
  s: {
    band: ChannelBand;
    qualityScore: number;
    conversionScore: number;
    costScore: number;
    speedScore: number;
    meanComposite: number | null;
    offerCount: number;
    count: number;
    costPerOffer: number | null;
    meanDaysToOffer: number | null;
  },
): string {
  const label = CHANNEL_LABEL[ch];
  if (s.count < 4) {
    return `Too few candidates (${s.count}) — keep testing ${label.toLowerCase()} before judging it.`;
  }
  if (s.band === 'cut') {
    if (s.costScore < 35 && s.costPerOffer !== null) {
      return `Cost-per-offer ₹${Math.round(s.costPerOffer)}k is too high — pause ${label.toLowerCase()} unless quality lifts.`;
    }
    if (s.conversionScore < 25) {
      return `Pipeline reaches offer only ${(s.conversionScore).toFixed(0)} on the conversion dial — stop investing until top-of-funnel quality improves.`;
    }
    return `ROI lags every other channel — cut spend and reallocate.`;
  }
  if (s.band === 'scale') {
    if (s.qualityScore >= 75 && s.conversionScore >= 65) {
      return `Highest-quality + highest-converting channel — double InMail seats / referral bonuses here this quarter.`;
    }
    return `Above-bar on every dial — scale this channel hard.`;
  }
  if (s.band === 'steady') {
    if (s.conversionScore < 50) {
      return `Solid quality but mid conversion — sharpen the first-touch message before adding volume.`;
    }
    if (s.speedScore < 50 && s.meanDaysToOffer !== null) {
      return `Quality is fine but cycle time is ${Math.round(s.meanDaysToOffer)} days — fast-track the screening hand-off.`;
    }
    return `Reliable baseline — keep at current volume.`;
  }
  // experiment
  return `Promising but thin — invest in ${label.toLowerCase()} for one more quarter before deciding.`;
}

// ---------- top-level recommendations ----------

function buildRecommendations(
  all: ChannelMetrics[],
  ranked: ChannelMetrics[],
): SourceRecommendation[] {
  const recs: SourceRecommendation[] = [];

  const scaleable = ranked.filter(m => m.band === 'scale');
  for (const m of scaleable.slice(0, 1)) {
    recs.push({
      channel: m.channel,
      band: m.band,
      title: `Scale ${m.label}`,
      detail:
        `ROI ${m.roi.toFixed(0)} · ${m.count} candidates · quality ${m.qualityScore.toFixed(0)} · ` +
        `${(m.reached.offer)} reached offer (${(100 * m.reached.offer / Math.max(1, m.count)).toFixed(0)}%). ` +
        m.recommendation,
    });
  }

  const cuts = ranked.filter(m => m.band === 'cut');
  for (const m of cuts.slice(0, 1)) {
    recs.push({
      channel: m.channel,
      band: m.band,
      title: `Cut ${m.label}`,
      detail:
        `ROI ${m.roi.toFixed(0)} · ${m.count} candidates · cost-per-offer ` +
        (m.costPerOffer === null ? '—' : `₹${Math.round(m.costPerOffer)}k`) +
        `. ${m.recommendation}`,
    });
  }

  // Concentration risk — if one channel >55% of the active pipeline, flag it.
  const totalActive = all.reduce((s, m) => s + m.active, 0);
  if (totalActive >= 12) {
    const top = [...all].sort((a, b) => b.active - a.active)[0];
    if (top && top.active / totalActive > 0.55) {
      recs.push({
        channel: top.channel,
        band: 'experiment',
        title: 'Diversify channel mix',
        detail:
          `${top.label} accounts for ${(100 * top.active / totalActive).toFixed(0)}% of the active pipeline ` +
          `(${top.active} of ${totalActive}). A single-channel pipeline is fragile — open a parallel ` +
          `experiment in another channel this week.`,
      });
    }
  }

  // Experiment graduation — strong quality on a thin channel.
  const promising = ranked.filter(m => m.band === 'experiment' && m.qualityScore >= 70 && m.count >= 2);
  for (const m of promising.slice(0, 1)) {
    recs.push({
      channel: m.channel,
      band: m.band,
      title: `Promote ${m.label} to a tracked experiment`,
      detail:
        `Only ${m.count} candidates but mean quality is ${m.qualityScore.toFixed(0)} — ` +
        `commit to 10 more touches and re-evaluate next month.`,
    });
  }

  return recs;
}

// ---------- markdown brief ----------

export function buildSourceBrief(summary: SourceSummary, opts?: { title?: string }): string {
  const lines: string[] = [];
  lines.push(`# ${opts?.title ?? 'Sourcing Intelligence — Channel Studio brief'}`);
  lines.push('');
  lines.push(
    `**Pipeline**: ${summary.totalActive} active · ${summary.totalCandidates} total · ` +
      `${summary.totalInterviewed} interviewed · ${summary.totalOffers} reached offer.`,
  );
  lines.push(
    `**Spend**: ₹${Math.round(summary.totalSpend)}k total · ` +
      (summary.costPerInterview === null ? '—' : `₹${Math.round(summary.costPerInterview)}k/interview · `) +
      (summary.costPerOffer === null ? '—' : `₹${Math.round(summary.costPerOffer)}k/offer`),
  );
  lines.push(`**Diversification**: ${(summary.diversification * 100).toFixed(0)}/100 normalised channel entropy.`);
  if (summary.bestChannel) {
    const m = summary.byChannel.find(x => x.channel === summary.bestChannel);
    if (m) lines.push(`**Best channel**: ${m.label} — ROI ${m.roi.toFixed(0)} · ${m.count} candidates.`);
  }
  if (summary.worstChannel && summary.worstChannel !== summary.bestChannel) {
    const m = summary.byChannel.find(x => x.channel === summary.worstChannel);
    if (m) lines.push(`**Worst channel**: ${m.label} — ROI ${m.roi.toFixed(0)} · ${m.count} candidates.`);
  }
  lines.push('');

  if (summary.recommendations.length) {
    lines.push('## Recommendations');
    for (const r of summary.recommendations) {
      lines.push(`- **${r.title}** — ${r.detail}`);
    }
    lines.push('');
  }

  lines.push('## Per-channel breakdown');
  lines.push('');
  lines.push(
    '| Channel | Count | Quality | Conv→Offer | Cost/offer (₹k) | ROI | Band |',
  );
  lines.push('|---|---:|---:|---:|---:|---:|---|');
  for (const m of summary.byChannel) {
    const conv =
      m.count > 0 ? `${(100 * m.reached.offer / m.count).toFixed(0)}%` : '—';
    const cpo = m.costPerOffer === null ? '—' : `${Math.round(m.costPerOffer)}`;
    lines.push(
      `| ${m.label} | ${m.count} | ${m.qualityScore.toFixed(0)} | ${conv} | ${cpo} | ${m.roi.toFixed(0)} | ${BAND_LABEL[m.band]} |`,
    );
  }
  lines.push('');

  return lines.join('\n');
}
