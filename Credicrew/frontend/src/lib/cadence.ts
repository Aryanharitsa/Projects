// Cadence Studio — per-candidate pipeline velocity & stage SLA engine.
//
// Forecast Studio (Day 47) answers the aggregate question: *will I have a
// hire by start_date?* It treats the funnel as a population and projects
// expected hires across thousands of MC trials. What it does NOT answer
// is the question every recruiter asks on a Monday morning:
//
//     "Which candidates in my pipeline are about to fall off this week,
//      and what should I do about each one — today?"
//
// Cadence is the per-candidate aging companion. For every shortlist entry
// it computes:
//
//   • `stageAgeDays` — time since the candidate entered their current
//     stage (read from a `stageChangedAt` timestamp when present;
//     deterministically synthesised from the entry+stage hash otherwise so
//     the surface lights up immediately on first open with a realistic
//     mix);
//   • `band` ∈ {on_track, slowing, at_risk, stalled} — driven by the
//     stage's SLA priors (mirrored from `forecast.ts` velocity medians +
//     a per-stage SLA multiplier);
//   • `surviveProb7d` — exponential-hazard probability the candidate is
//     still sitting in this stage in 7 days (memoryless, so
//     `exp(-7 · ln2 / median)`);
//   • `riskScore` ∈ 0..100 — 0.6 · overdue + 0.4 · staleness;
//   • a band-keyed `recommendation` string — what to do today.
//
// Roll-ups: per-stage (median/p75 age, band counts, expected exits in 7d,
// bottleneck flag, 0..100 health), per-role (band breakdown + health),
// and a global summary (active count, at-risk + stalled counts, expected
// exits/7d, worst stage, worst role, top recommendations, markdown
// brief).
//
// Pure functions. Deterministic for a given input. Mirrored byte-for-byte
// in `backend/app/services/cadence.py`.

import type { PipelineStatus } from '@/lib/roles';

// ---------- types ----------

export type CadenceBand = 'on_track' | 'slowing' | 'at_risk' | 'stalled';

export const CADENCE_BANDS: CadenceBand[] = [
  'on_track',
  'slowing',
  'at_risk',
  'stalled',
];

export const BAND_LABEL: Record<CadenceBand, string> = {
  on_track: 'On track',
  slowing: 'Slowing',
  at_risk: 'At risk',
  stalled: 'Stalled',
};

export const BAND_HUE: Record<CadenceBand, string> = {
  on_track: '#34d399', // emerald
  slowing: '#facc15',  // amber
  at_risk: '#fb923c',  // orange
  stalled: '#fb7185',  // rose
};

/**
 * Per-stage SLA in days. The SLA is the *expected* time a healthy
 * candidate spends in this stage before advancing; aging beyond it lands
 * the candidate in `slowing` then `at_risk` then `stalled`.
 */
export const STAGE_SLA_DAYS: Record<PipelineStatus, number> = {
  new: 1,
  outreach: 3,
  screening: 5,
  interview: 7,
  offer: 5,
  passed: 30,
};

/**
 * Median time-in-stage priors (mirrored from forecast.ts). Used by the
 * exponential-hazard survival model so cadence + forecast are calibrated
 * on the same physics.
 */
export const STAGE_MEDIAN_DAYS: Record<PipelineStatus, number> = {
  new: 2,
  outreach: 4,
  screening: 5,
  interview: 7,
  offer: 4,
  passed: 30,
};

/** Active stages — `passed` and offer-accepted are terminal. */
export const ACTIVE_STAGES: PipelineStatus[] = [
  'new',
  'outreach',
  'screening',
  'interview',
  'offer',
];

export type CadenceCandidate = {
  candidateId: number;
  candidateName: string;
  roleId: string;
  roleName: string;
  stage: PipelineStatus;
  /** Time since the candidate entered the current stage (days). */
  stageAgeDays: number;
  /** Total time in pipeline (days). */
  pipelineAgeDays: number;
  /** Match score (0..100) — used to prioritise hot-list ties. */
  matchScore: number;
  /** Location string — used for context in the hot list. */
  location?: string;
};

export type CadenceItem = {
  candidateId: number;
  candidateName: string;
  roleId: string;
  roleName: string;
  stage: PipelineStatus;
  stageAgeDays: number;
  pipelineAgeDays: number;
  matchScore: number;
  location?: string;
  band: CadenceBand;
  riskScore: number;
  surviveProb7d: number;
  daysOverSla: number;
  slaDays: number;
  recommendation: string;
};

export type StageRollup = {
  stage: PipelineStatus;
  count: number;
  ageMedian: number;
  ageP75: number;
  bands: Record<CadenceBand, number>;
  expectedExits7d: number;
  bottleneck: boolean;
  health: number;
  slaDays: number;
  medianDays: number;
};

export type RoleRollup = {
  roleId: string;
  roleName: string;
  count: number;
  bands: Record<CadenceBand, number>;
  health: number;
  topStalled: CadenceItem[];
};

export type CadenceSummary = {
  totalActive: number;
  atRiskCount: number;
  stalledCount: number;
  onTrackCount: number;
  healthScore: number;
  expectedExits7d: number;
  worstStage: PipelineStatus | null;
  worstRoleId: string | null;
  byStage: StageRollup[];
  byRole: RoleRollup[];
  hotList: CadenceItem[];
  items: CadenceItem[];
  recommendations: string[];
  generatedAt: number;
};

// ---------- helpers ----------

function clamp(n: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, n));
}

function quantile(sorted: number[], q: number): number {
  if (sorted.length === 0) return 0;
  if (sorted.length === 1) return sorted[0];
  const pos = (sorted.length - 1) * q;
  const lo = Math.floor(pos);
  const hi = Math.ceil(pos);
  if (lo === hi) return sorted[lo];
  const w = pos - lo;
  return sorted[lo] * (1 - w) + sorted[hi] * w;
}

function emptyBands(): Record<CadenceBand, number> {
  return { on_track: 0, slowing: 0, at_risk: 0, stalled: 0 };
}

/** FNV-1a 32-bit hash → number in [0, 1). Used for deterministic seeding. */
export function fnv1aUnit(s: string): number {
  let h = 0x811c9dc5;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  return (h >>> 0) / 0xffffffff;
}

// ---------- band + risk ----------

export function bandForAge(ageDays: number, slaDays: number): CadenceBand {
  const sla = Math.max(0.5, slaDays);
  if (ageDays <= sla * 0.7) return 'on_track';
  if (ageDays <= sla) return 'slowing';
  if (ageDays <= sla * 1.6) return 'at_risk';
  return 'stalled';
}

/**
 * Memoryless exponential survival: P(still in this stage in 7 days |
 * currently in this stage). Lambda = ln(2) / median.
 *
 *     P(survive 7d) = exp(-7 · ln(2) / median)
 *
 * A median of 4d → 30% chance of still being here next week.
 * A median of 7d → 50%.
 */
export function survival7d(medianDays: number): number {
  const m = Math.max(0.5, medianDays);
  return Math.exp((-7 * Math.LN2) / m);
}

/**
 * 0..100 risk that this candidate stalls / drops. Combines `overdue`
 * (how far past SLA) with `staleness` (how long they've been sitting
 * relative to the typical median).
 */
export function riskScore(ageDays: number, slaDays: number, medianDays: number): number {
  const sla = Math.max(0.5, slaDays);
  const m = Math.max(0.5, medianDays);
  const overdue = clamp((ageDays - sla) / m, 0, 1);
  const staleness = clamp(ageDays / (m * 4), 0, 1);
  return Math.round(100 * (0.6 * overdue + 0.4 * staleness));
}

function recommendForBand(band: CadenceBand, stage: PipelineStatus, ageDays: number, slaDays: number): string {
  const overdueDays = Math.max(0, ageDays - slaDays);
  if (band === 'on_track') {
    if (stage === 'offer') return 'On track — keep weekly touch warm until decision.';
    return `On track — keep moving (${ageDays.toFixed(1)}d in ${stage}).`;
  }
  if (band === 'slowing') {
    if (stage === 'outreach') return `Approaching SLA (${ageDays.toFixed(1)}/${slaDays}d) — bump the thread today.`;
    if (stage === 'screening') return `Screening dragging — schedule the call within 48h.`;
    if (stage === 'interview') return `Interview slot still open — confirm or reschedule today.`;
    if (stage === 'offer') return `Offer drifting — re-engage and surface the deciding blocker.`;
    return `Approaching SLA — nudge the next step.`;
  }
  if (band === 'at_risk') {
    if (stage === 'outreach') return `${overdueDays.toFixed(1)}d past outreach SLA — try the alt channel or close the thread.`;
    if (stage === 'screening') return `${overdueDays.toFixed(1)}d past screening SLA — escalate or move to a recruiter sync.`;
    if (stage === 'interview') return `${overdueDays.toFixed(1)}d past interview SLA — panel waiting on whom?`;
    if (stage === 'offer') return `${overdueDays.toFixed(1)}d past offer SLA — counter-offer risk rising; call them.`;
    return `${overdueDays.toFixed(1)}d past SLA — escalate today.`;
  }
  if (stage === 'offer') return `Stalled offer — assume lost unless contacted today; consider next finalist.`;
  if (stage === 'interview') return `Stalled in interview — close the loop or pass; the slot is dead weight.`;
  if (stage === 'screening') return `Stalled screen — drop or hand off; this seat is blocking your funnel.`;
  if (stage === 'outreach') return `Stalled outreach — try one final channel, then close as no-response.`;
  return `Stalled — close the loop today.`;
}

// ---------- seed / synthesise ----------

/**
 * Deterministically synthesise a `stageAgeDays` from an entry's identity
 * + current stage, so the surface lights up with a realistic distribution
 * on first open even when `stageChangedAt` isn't recorded yet. The mix
 * targets ~50% on_track, 25% slowing, 17% at_risk, 8% stalled.
 */
export function synthStageAge(
  roleId: string,
  candidateId: number,
  stage: PipelineStatus,
): number {
  const u = fnv1aUnit(`${roleId}|${candidateId}|${stage}`);
  const sla = STAGE_SLA_DAYS[stage] ?? 5;
  if (u < 0.5) {
    // on_track: 0 .. 0.7 SLA
    return Math.round(u * 2 * 0.7 * sla * 10) / 10;
  }
  if (u < 0.75) {
    // slowing: 0.7 .. 1.0 SLA
    return Math.round((sla * (0.7 + (u - 0.5) * 4 * 0.3)) * 10) / 10;
  }
  if (u < 0.92) {
    // at_risk: 1.0 .. 1.6 SLA
    return Math.round((sla * (1.0 + (u - 0.75) * (0.6 / 0.17))) * 10) / 10;
  }
  // stalled: 1.6 .. 3.0 SLA
  return Math.round((sla * (1.6 + (u - 0.92) * (1.4 / 0.08))) * 10) / 10;
}

// ---------- core analyzer ----------

export type CadenceInput = {
  candidates: CadenceCandidate[];
  /** Default 7 days for the survival projection. */
  horizonDays?: number;
};

export function analyzeCadence(input: CadenceInput): CadenceSummary {
  const items: CadenceItem[] = [];
  for (const c of input.candidates) {
    if (!ACTIVE_STAGES.includes(c.stage)) continue;
    const sla = STAGE_SLA_DAYS[c.stage] ?? 5;
    const median = STAGE_MEDIAN_DAYS[c.stage] ?? 5;
    const band = bandForAge(c.stageAgeDays, sla);
    const risk = riskScore(c.stageAgeDays, sla, median);
    const survive = survival7d(median);
    items.push({
      candidateId: c.candidateId,
      candidateName: c.candidateName,
      roleId: c.roleId,
      roleName: c.roleName,
      stage: c.stage,
      stageAgeDays: c.stageAgeDays,
      pipelineAgeDays: c.pipelineAgeDays,
      matchScore: c.matchScore,
      location: c.location,
      band,
      riskScore: risk,
      surviveProb7d: survive,
      daysOverSla: Math.max(0, c.stageAgeDays - sla),
      slaDays: sla,
      recommendation: recommendForBand(band, c.stage, c.stageAgeDays, sla),
    });
  }

  // ---- per-stage ----
  const byStage: StageRollup[] = [];
  for (const stage of ACTIVE_STAGES) {
    const inStage = items.filter(i => i.stage === stage);
    const ages = inStage.map(i => i.stageAgeDays).sort((a, b) => a - b);
    const bands = emptyBands();
    for (const i of inStage) bands[i.band] += 1;
    const expectedExits7d = inStage.reduce(
      (acc, i) => acc + (1 - i.surviveProb7d),
      0,
    );
    const atRisk = bands.at_risk + bands.stalled;
    const denom = Math.max(1, inStage.length);
    const health = Math.round(
      100 * (1 - (0.6 * (bands.stalled / denom) + 0.3 * (bands.at_risk / denom) + 0.1 * (bands.slowing / denom))),
    );
    byStage.push({
      stage,
      count: inStage.length,
      ageMedian: ages.length ? +quantile(ages, 0.5).toFixed(1) : 0,
      ageP75: ages.length ? +quantile(ages, 0.75).toFixed(1) : 0,
      bands,
      expectedExits7d: +expectedExits7d.toFixed(2),
      bottleneck: false,
      health,
      slaDays: STAGE_SLA_DAYS[stage],
      medianDays: STAGE_MEDIAN_DAYS[stage],
    });
    // mark unused field
    void atRisk;
  }

  // Bottleneck = stage with the largest (at_risk + stalled) — only flag
  // when there's a real problem (≥ 2 candidates AND ≥ 25% of the stage).
  let worstScore = 0;
  let bottleneckIdx = -1;
  for (let i = 0; i < byStage.length; i++) {
    const s = byStage[i];
    const stuck = s.bands.at_risk + s.bands.stalled;
    if (s.count < 2) continue;
    if (stuck / s.count < 0.25) continue;
    if (stuck > worstScore) {
      worstScore = stuck;
      bottleneckIdx = i;
    }
  }
  if (bottleneckIdx >= 0) byStage[bottleneckIdx].bottleneck = true;

  // ---- per-role ----
  const roleMap = new Map<string, RoleRollup>();
  for (const i of items) {
    if (!roleMap.has(i.roleId)) {
      roleMap.set(i.roleId, {
        roleId: i.roleId,
        roleName: i.roleName,
        count: 0,
        bands: emptyBands(),
        health: 100,
        topStalled: [],
      });
    }
    const r = roleMap.get(i.roleId)!;
    r.count += 1;
    r.bands[i.band] += 1;
  }
  for (const r of roleMap.values()) {
    const denom = Math.max(1, r.count);
    r.health = Math.round(
      100 * (1 - (0.6 * (r.bands.stalled / denom) + 0.3 * (r.bands.at_risk / denom) + 0.1 * (r.bands.slowing / denom))),
    );
    r.topStalled = items
      .filter(i => i.roleId === r.roleId && (i.band === 'at_risk' || i.band === 'stalled'))
      .sort((a, b) => b.riskScore - a.riskScore)
      .slice(0, 3);
  }
  const byRole = Array.from(roleMap.values()).sort((a, b) => a.health - b.health);

  // ---- top-level rollups ----
  const totalActive = items.length;
  const onTrackCount = items.filter(i => i.band === 'on_track').length;
  const atRiskCount = items.filter(i => i.band === 'at_risk').length;
  const stalledCount = items.filter(i => i.band === 'stalled').length;
  const slowingCount = items.filter(i => i.band === 'slowing').length;
  const denom = Math.max(1, totalActive);
  const healthScore = Math.round(
    100 * (1 - (0.6 * (stalledCount / denom) + 0.3 * (atRiskCount / denom) + 0.1 * (slowingCount / denom))),
  );
  const expectedExits7d = +items.reduce(
    (acc, i) => acc + (1 - i.surviveProb7d),
    0,
  ).toFixed(2);

  // ---- worst stage / role ----
  let worstStage: PipelineStatus | null = null;
  let worstStageHealth = 101;
  for (const s of byStage) {
    if (s.count === 0) continue;
    if (s.health < worstStageHealth) {
      worstStageHealth = s.health;
      worstStage = s.stage;
    }
  }
  let worstRoleId: string | null = null;
  if (byRole.length > 0 && byRole[0].health < 75) worstRoleId = byRole[0].roleId;

  // ---- hot list: top 8 by risk score (descending), ties → higher match ----
  const hotList = items
    .filter(i => i.band === 'at_risk' || i.band === 'stalled')
    .sort((a, b) => (b.riskScore - a.riskScore) || (b.matchScore - a.matchScore))
    .slice(0, 8);

  // ---- recommendations ----
  const recommendations: string[] = [];
  if (totalActive === 0) {
    recommendations.push('No active candidates — load roles and add a shortlist to see cadence.');
  } else if (stalledCount === 0 && atRiskCount === 0) {
    recommendations.push(`**Healthy** — all ${totalActive} active candidates inside SLA. Keep cadence.`);
  } else {
    if (stalledCount > 0) {
      recommendations.push(
        `**${stalledCount} stalled** — close the loop or drop. Each stalled card is a slot blocking real progress.`,
      );
    }
    if (atRiskCount > 0) {
      recommendations.push(
        `**${atRiskCount} at risk** — these need a nudge today or they roll into stalled by Friday.`,
      );
    }
    if (bottleneckIdx >= 0) {
      const bn = byStage[bottleneckIdx];
      recommendations.push(
        `**Bottleneck: ${stageLabel(bn.stage)}** — ${bn.bands.at_risk + bn.bands.stalled} of ${bn.count} candidates past SLA (median age ${bn.ageMedian}d vs SLA ${bn.slaDays}d).`,
      );
    }
    if (worstRoleId) {
      const r = byRole[0];
      recommendations.push(
        `**Worst role: ${r.roleName}** — health ${r.health}/100 across ${r.count} candidates. Recover or descope.`,
      );
    }
    if (hotList.length > 0) {
      const top = hotList[0];
      recommendations.push(
        `**Today's top action:** ${top.candidateName} (${top.roleName}, ${stageLabel(top.stage)}, ${top.stageAgeDays}d) — ${top.recommendation}`,
      );
    }
  }

  return {
    totalActive,
    atRiskCount,
    stalledCount,
    onTrackCount,
    healthScore,
    expectedExits7d,
    worstStage,
    worstRoleId,
    byStage,
    byRole,
    hotList,
    items,
    recommendations,
    generatedAt: Date.now(),
  };
}

export function stageLabel(stage: PipelineStatus): string {
  switch (stage) {
    case 'new': return 'New';
    case 'outreach': return 'Outreach';
    case 'screening': return 'Screening';
    case 'interview': return 'Interview';
    case 'offer': return 'Offer';
    case 'passed': return 'Passed';
  }
}

// ---------- markdown brief ----------

export function buildCadenceBrief(s: CadenceSummary): string {
  const lines: string[] = [];
  const dt = new Date(s.generatedAt).toISOString().slice(0, 10);
  lines.push(`# Pipeline Cadence — ${dt}`);
  lines.push('');
  lines.push(`**Health:** ${s.healthScore}/100 · **Active:** ${s.totalActive} · **At risk:** ${s.atRiskCount} · **Stalled:** ${s.stalledCount}`);
  lines.push(`**Projected exits next 7 days:** ${s.expectedExits7d.toFixed(1)}`);
  lines.push('');
  if (s.recommendations.length > 0) {
    lines.push('## Recommendations');
    for (const r of s.recommendations) lines.push(`- ${r}`);
    lines.push('');
  }
  if (s.hotList.length > 0) {
    lines.push('## Today\'s hot list');
    lines.push('| Candidate | Role | Stage | Age | Band | Action |');
    lines.push('|---|---|---|---:|---|---|');
    for (const h of s.hotList) {
      lines.push(`| ${h.candidateName} | ${h.roleName} | ${stageLabel(h.stage)} | ${h.stageAgeDays}d | ${BAND_LABEL[h.band]} | ${h.recommendation} |`);
    }
    lines.push('');
  }
  if (s.byStage.some(b => b.count > 0)) {
    lines.push('## Stage health');
    lines.push('| Stage | Count | Median age | SLA | At risk | Stalled | Health |');
    lines.push('|---|---:|---:|---:|---:|---:|---:|');
    for (const st of s.byStage) {
      if (st.count === 0) continue;
      lines.push(`| ${stageLabel(st.stage)}${st.bottleneck ? ' ⚠️' : ''} | ${st.count} | ${st.ageMedian}d | ${st.slaDays}d | ${st.bands.at_risk} | ${st.bands.stalled} | ${st.health} |`);
    }
    lines.push('');
  }
  if (s.byRole.length > 0) {
    lines.push('## Role health');
    lines.push('| Role | Active | On track | At risk | Stalled | Health |');
    lines.push('|---|---:|---:|---:|---:|---:|');
    for (const r of s.byRole) {
      lines.push(`| ${r.roleName} | ${r.count} | ${r.bands.on_track} | ${r.bands.at_risk} | ${r.bands.stalled} | ${r.health} |`);
    }
    lines.push('');
  }
  return lines.join('\n');
}
