// Hindsight — Post-Hire Outcome Calibration & Rubric Tuner.
//
// Every other Credicrew surface is forward-looking. Discover ranks who to
// talk to. Decision Studio ranks who interviewed best. Forecast Studio
// predicts whether a hire will close. Hindsight is the only surface that
// looks *backwards*: it takes the offers that turned into accepted hires,
// pairs each one with the post-hire performance outcome, and asks
// the question every other surface assumes is already answered — *did our
// rubric actually predict who succeeded?*
//
// The math is intentionally simple and inspectable:
//
//   For every rubric dimension d the engine computes
//     r_perf(d)  = Pearson(interview rating on d,  performance score)
//     r_tenure(d) = Pearson(interview rating on d,  tenureDays)
//   over the rated hires. The "predictive power" of a dim is
//     pp(d) = round( max(|r_perf|, 0.6·|r_tenure|) · 100 )
//   bucketed into strong (≥55) · moderate (≥35) · weak (≥10) · unknown.
//
//   The suggested rubric weight is a 50/50 blend of *what we said matters*
//   (current weight) and *what actually mattered* (|r| normalised across
//   rated dims) — never a hard reset, so a single-quarter calibration
//   never tears down the whole rubric.
//
//   Pool-level calibration is reported as:
//     hitRate     = share of hires with performance ≥ 4
//     pearson     = Pearson(composite, performance)
//     spearman    = Pearson on rank-transformed composite / performance
//     brierScore  = mean( (composite/100  −  1[perf ≥ 4])² )    (0 = perfect)
//
// Synthetic outcomes — until the recruiter logs real performance, Hindsight
// fabricates an outcome per hire that *does* correlate with the rubric
// signal but with bounded noise, so the engine has data to learn from on
// first open. Deterministic FNV-1a hash of `${candidateId}::${roleId}` so
// the same hire shows the same outcome on every reload. Once a real outcome
// is logged it overrides the synthetic.
//
// All pure data, browser-first. Mirrored in `backend/app/services/hindsight.py`.

import type { CandidateLike } from '@/lib/match';
import { matchCandidate } from '@/lib/match';
import type { Role } from '@/lib/roles';
import {
  ensureInterview as ensureInterviewRecord,
  getInterview,
  summarise,
  type InterviewRecord,
  type RubricDimension,
  type ScorecardSummary,
} from '@/lib/interview';

// ---------- tunables ----------

/** Dimensions with |r| ≥ this against performance are "strong" predictors. */
export const PP_STRONG = 0.55;
export const PP_MODERATE = 0.35;
export const PP_WEAK = 0.10;
/** A surprise false positive needs composite ≥ this and performance ≤ FP_PERF_FLOOR. */
export const FP_COMPOSITE_FLOOR = 80;
export const FP_PERF_FLOOR = 2;
/** A surprise false negative needs composite ≤ this and performance ≥ FN_PERF_FLOOR. */
export const FN_COMPOSITE_CEIL = 55;
export const FN_PERF_FLOOR = 4;
/** Minimum hires per dim before |r| means anything. */
export const MIN_SAMPLES = 4;
/** How aggressively to retune weights from observed signal. 0 = never change,
 *  1 = full hand-over to |r|. We blend half-and-half so the rubric reflects
 *  both the intent (current) and the evidence (observed). */
export const RETUNE_BLEND = 0.5;
/** A "good hire" outcome threshold for hit-rate + Brier. */
export const GOOD_HIRE_FLOOR = 4;
/** Tenure half-life days the seed uses to project a deterministic tenure. */
const TENURE_BASE_DAYS = 60;
const TENURE_PER_RATING_DAYS = 95;
const DAY_MS = 86_400_000;
const HIRE_STATUS = 'offer' as const;

// ---------- types ----------

export type HireOutcome = {
  candidateId: number;
  roleId: string;
  hiredAtMs: number;
  /** 1..5 performance rating; the team's lived experience after hire. */
  performance: 1 | 2 | 3 | 4 | 5;
  /** Calendar days from hire until now (or until attrition if !stillActive). */
  tenureDays: number;
  stillActive: boolean;
  /** Optional manager note. */
  note?: string;
  /** Source: 'real' = recruiter-logged, 'synthetic' = engine seed. */
  source: 'real' | 'synthetic';
};

export type HireRecord = {
  candidateId: number;
  candidateName: string;
  roleId: string;
  roleName: string;
  hiredAtMs: number;
  /** Interview composite at time of decision; undefined if no scorecard exists. */
  composite?: number;
  /** Recommendation tier (from summarise()). */
  recommendation?: ScorecardSummary['recommendation'];
  /** Rated dim → rating snapshot at hire time. */
  ratings: Record<string, number>;
  /** Snapshot of the rubric the candidate was rated on. */
  rubric: RubricDimension[];
  outcome: HireOutcome;
};

export type DimensionCalibration = {
  key: string;
  label: string;
  /** Average current rubric weight across hires that rated this dim. */
  currentWeight: number;
  /** Pearson r between dim rating and performance score. */
  rPerformance: number;
  /** Pearson r between dim rating and tenure days. */
  rTenure: number;
  samples: number;
  /** 0..100 — round(max(|rPerf|, 0.6·|rTen|) · 100). */
  predictivePower: number;
  /** Re-weighted suggestion (renormalised against the other dims). */
  suggestedWeight: number;
  /** suggestedWeight − currentWeight. */
  weightDelta: number;
  band: 'strong' | 'moderate' | 'weak' | 'unknown';
};

export type CompositeBin = {
  /** Bin label like "70–79". */
  label: string;
  /** Bin floor (0, 10, …, 90). */
  floor: number;
  count: number;
  meanPerformance: number;
  meanTenureDays: number;
  /** Share of bin with performance ≥ GOOD_HIRE_FLOOR. */
  goodRate: number;
};

export type SurpriseCase = {
  candidateId: number;
  candidateName: string;
  roleId: string;
  roleName: string;
  composite: number;
  performance: number;
  tenureDays: number;
  stillActive: boolean;
  kind: 'false_positive' | 'false_negative';
  /** Best/worst dim that drove the surprise; undefined if no rating signal. */
  driverKey?: string;
  driverLabel?: string;
  driverRating?: number;
  /** Human-readable explainer. */
  why: string;
};

export type RubricRecommendation = {
  keep: { key: string; label: string; currentWeight: number; suggestedWeight: number; delta: number }[];
  promote: { key: string; label: string; currentWeight: number; suggestedWeight: number; delta: number }[];
  reduce: { key: string; label: string; currentWeight: number; suggestedWeight: number; delta: number }[];
  drop: { key: string; label: string; rPerformance: number; samples: number }[];
};

export type TenureBand = {
  band: 'strong_hire' | 'lean_yes' | 'mixed' | 'lean_no' | 'no_hire';
  meanTenureDays: number;
  meanPerformance: number;
  count: number;
};

export type HindsightSummary = {
  generatedAt: number;
  hires: HireRecord[];
  hireCount: number;
  realCount: number;
  syntheticCount: number;
  hitRate: number;
  meanComposite: number;
  meanPerformance: number;
  meanTenureDays: number;
  attritionRate: number;
  pearson: number;
  spearman: number;
  brierScore: number;
  perDimension: DimensionCalibration[];
  compositeBins: CompositeBin[];
  surpriseCases: SurpriseCase[];
  rubricRecommendation: RubricRecommendation;
  tenureByBand: TenureBand[];
  calibrationBand: 'excellent' | 'good' | 'mixed' | 'concerning' | 'unknown';
  /** Plain-English action list rendered above the dim grid. */
  actions: string[];
};

// ---------- pure math ----------

/** FNV-1a 32-bit. Returns an unsigned integer. */
export function fnv1a(s: string): number {
  let h = 0x811c9dc5;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = (h + ((h << 1) + (h << 4) + (h << 7) + (h << 8) + (h << 24))) >>> 0;
  }
  return h >>> 0;
}

export function pearson(xs: number[], ys: number[]): number {
  const n = xs.length;
  if (n < 2 || n !== ys.length) return 0;
  let sx = 0, sy = 0;
  for (let i = 0; i < n; i++) { sx += xs[i]; sy += ys[i]; }
  const mx = sx / n;
  const my = sy / n;
  let num = 0, dx2 = 0, dy2 = 0;
  for (let i = 0; i < n; i++) {
    const dx = xs[i] - mx;
    const dy = ys[i] - my;
    num += dx * dy;
    dx2 += dx * dx;
    dy2 += dy * dy;
  }
  const denom = Math.sqrt(dx2 * dy2);
  if (denom === 0) return 0;
  return num / denom;
}

/** Average rank with ties resolved by mean rank. */
function ranks(xs: number[]): number[] {
  const idx = xs.map((v, i) => ({ v, i })).sort((a, b) => a.v - b.v);
  const r = new Array<number>(xs.length).fill(0);
  let i = 0;
  while (i < idx.length) {
    let j = i;
    while (j + 1 < idx.length && idx[j + 1].v === idx[i].v) j++;
    const mean = (i + j) / 2 + 1;
    for (let k = i; k <= j; k++) r[idx[k].i] = mean;
    i = j + 1;
  }
  return r;
}

export function spearman(xs: number[], ys: number[]): number {
  if (xs.length !== ys.length || xs.length < 2) return 0;
  return pearson(ranks(xs), ranks(ys));
}

export function clamp(v: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, v));
}

// ---------- synthetic outcome seed ----------

/** Build a deterministic outcome for an offer-status shortlist entry that
 *  correlates with the interview composite (so calibration math has signal
 *  on first open). Mixed in: a per-candidate noise term so the engine sees
 *  both calibrated and surprise hires from the seed alone. */
export function syntheticOutcome(
  candidateId: number,
  roleId: string,
  hiredAtMs: number,
  composite: number,
  nowMs: number,
): HireOutcome {
  const h = fnv1a(`${candidateId}::${roleId}::outcome`);
  // 0..1 noise centred at 0.5
  const noise01 = (h % 10_000) / 10_000;
  // Centred noise in [-0.5..0.5].
  const noiseCentred = noise01 - 0.5;
  // Outcome anchored to composite/25 (so 80 → ~3.2, 100 → 4.0) plus 1.6 * noise
  // (yielding occasional +/- 1 rating jumps).
  const base = composite / 25 + noiseCentred * 1.7 + 0.7;
  const perf = clamp(Math.round(base), 1, 5) as 1 | 2 | 3 | 4 | 5;

  // Tenure: starts at TENURE_BASE_DAYS + ~95 days per rating step, with a
  // small per-candidate jitter so ties break visually.
  const jitter = (h >>> 8) % 60;
  const tenure = Math.round(TENURE_BASE_DAYS + perf * TENURE_PER_RATING_DAYS + jitter);
  // Cap to days since hire so we don't claim more tenure than has elapsed.
  const daysSinceHire = Math.max(0, Math.floor((nowMs - hiredAtMs) / DAY_MS));
  const tenureDays = Math.min(tenure, Math.max(7, daysSinceHire));
  // Attrition: low performers and middling hires after a year are at risk.
  const attritionRoll = ((h >>> 16) % 100) / 100;
  const attritionProb = perf <= 2 ? 0.65 : perf === 3 ? 0.25 : 0.08;
  const stillActive = attritionRoll > attritionProb;

  return {
    candidateId,
    roleId,
    hiredAtMs,
    performance: perf,
    tenureDays,
    stillActive,
    source: 'synthetic',
  };
}

// ---------- hire extraction ----------

/** Pull every offer-status shortlist entry across roles into a HireRecord.
 *  Pairs each with its interview scorecard (if any) and a synthetic-or-real
 *  outcome from `outcomeOverrides`. */
export function extractHires(
  roles: Role[],
  candidates: (CandidateLike & { id: number; name?: string })[],
  outcomeOverrides: Map<string, HireOutcome>,
  opts: { nowMs?: number; interviewsByKey?: Map<string, InterviewRecord> } = {},
): HireRecord[] {
  const now = opts.nowMs ?? Date.now();
  const byId = new Map<number, CandidateLike & { id: number; name?: string }>();
  for (const c of candidates) byId.set(c.id, c);
  const interviewsByKey = opts.interviewsByKey ?? new Map<string, InterviewRecord>();

  const out: HireRecord[] = [];
  for (const role of roles) {
    for (const e of role.shortlist) {
      if (e.status !== HIRE_STATUS) continue;
      const cand = byId.get(e.candidateId);
      if (!cand) continue;
      const hiredAt = e.stageChangedAt ?? e.addedAt ?? now - 90 * DAY_MS;

      // Pull interview record if present.
      const key = `${role.id}::${e.candidateId}`;
      const ivr = interviewsByKey.get(key);
      let composite: number | undefined;
      let rec: ScorecardSummary['recommendation'] | undefined;
      const ratings: Record<string, number> = {};
      let rubric: RubricDimension[] = [];
      if (ivr) {
        const s = summarise(ivr);
        composite = s.composite;
        rec = s.recommendation;
        rubric = ivr.rubric;
        // Latest rating per dim (mirrors summarise()'s policy).
        const latest: Record<string, number | null> = {};
        for (const d of ivr.rubric) latest[d.key] = null;
        for (const stage of ivr.stages) {
          for (const score of stage.scores) {
            if (score.rating !== null) latest[score.key] = score.rating;
          }
        }
        for (const [k, v] of Object.entries(latest)) {
          if (v !== null) ratings[k] = v;
        }
      }

      // Fallback composite: rebuild from the candidate's home-role match
      // score so even un-interviewed hires light up the calibration math.
      if (composite === undefined) {
        const m = matchCandidate(role.plan, cand);
        composite = Math.round(0.55 * m.score + 0.45 * 70);
      }

      const overrideKey = `${e.candidateId}::${role.id}`;
      const outcome = outcomeOverrides.get(overrideKey)
        ?? syntheticOutcome(e.candidateId, role.id, hiredAt, composite, now);

      out.push({
        candidateId: e.candidateId,
        candidateName: cand.name ?? `Candidate ${e.candidateId}`,
        roleId: role.id,
        roleName: role.name,
        hiredAtMs: hiredAt,
        composite,
        recommendation: rec,
        ratings,
        rubric,
        outcome,
      });
    }
  }
  // Newest hire first.
  out.sort((a, b) => b.hiredAtMs - a.hiredAtMs);
  return out;
}

// ---------- engine ----------

/** Average current rubric weight per dim across the hire pool. Dim weights
 *  drift role-to-role (skill-bank dims change with the JD), so we report
 *  the *experienced* weight — what hires were actually scored on. */
function averageRubricWeights(hires: HireRecord[]): Map<string, { weight: number; label: string }> {
  const sums = new Map<string, { sum: number; count: number; label: string }>();
  for (const h of hires) {
    for (const dim of h.rubric) {
      const cur = sums.get(dim.key) ?? { sum: 0, count: 0, label: dim.label };
      cur.sum += dim.weight;
      cur.count += 1;
      cur.label = dim.label;
      sums.set(dim.key, cur);
    }
  }
  const out = new Map<string, { weight: number; label: string }>();
  for (const [k, v] of sums) {
    out.set(k, { weight: v.count > 0 ? v.sum / v.count : 0, label: v.label });
  }
  return out;
}

function band(power: number, samples: number): DimensionCalibration['band'] {
  if (samples < MIN_SAMPLES) return 'unknown';
  if (power >= PP_STRONG * 100) return 'strong';
  if (power >= PP_MODERATE * 100) return 'moderate';
  if (power >= PP_WEAK * 100) return 'weak';
  return 'unknown';
}

function buildPerDimension(hires: HireRecord[]): DimensionCalibration[] {
  const avgW = averageRubricWeights(hires);
  // Collect per-dim (rating, performance, tenure) triplets.
  const buckets = new Map<string, { ratings: number[]; perf: number[]; tenure: number[] }>();
  for (const h of hires) {
    for (const [k, r] of Object.entries(h.ratings)) {
      const b = buckets.get(k) ?? { ratings: [], perf: [], tenure: [] };
      b.ratings.push(r);
      b.perf.push(h.outcome.performance);
      b.tenure.push(h.outcome.tenureDays);
      buckets.set(k, b);
    }
  }

  const raw: DimensionCalibration[] = [];
  for (const [k, b] of buckets) {
    const meta = avgW.get(k);
    if (!meta) continue;
    const rPerf = pearson(b.ratings, b.perf);
    const rTen = pearson(b.ratings, b.tenure);
    const pp = Math.round(Math.max(Math.abs(rPerf), 0.6 * Math.abs(rTen)) * 100);
    raw.push({
      key: k,
      label: meta.label,
      currentWeight: meta.weight,
      rPerformance: round3(rPerf),
      rTenure: round3(rTen),
      samples: b.ratings.length,
      predictivePower: pp,
      // Will be filled by the reweight pass.
      suggestedWeight: meta.weight,
      weightDelta: 0,
      band: band(pp, b.ratings.length),
    });
  }

  // Reweighting: blend current weight with normalised |r_perf|. Dims with
  // n < MIN_SAMPLES stay at their current weight (no evidence to reweight on).
  const weights = raw.map(d =>
    d.samples >= MIN_SAMPLES ? Math.max(0, Math.abs(d.rPerformance)) : 0,
  );
  const sumW = weights.reduce((a, b) => a + b, 0);
  if (sumW > 0) {
    for (let i = 0; i < raw.length; i++) {
      const observed = weights[i] / sumW;
      const blended = RETUNE_BLEND * observed + (1 - RETUNE_BLEND) * raw[i].currentWeight;
      raw[i].suggestedWeight = blended;
    }
  }
  // Renormalise suggested across dims to sum to 1 so callers can plug it in.
  const sumS = raw.reduce((a, d) => a + d.suggestedWeight, 0);
  if (sumS > 0) {
    for (const d of raw) {
      d.suggestedWeight = round3(d.suggestedWeight / sumS);
      d.weightDelta = round3(d.suggestedWeight - d.currentWeight);
    }
  }
  // Sort by predictive power desc.
  raw.sort((a, b) => b.predictivePower - a.predictivePower);
  return raw;
}

function buildCompositeBins(hires: HireRecord[]): CompositeBin[] {
  const bins: CompositeBin[] = [];
  for (let floor = 0; floor <= 90; floor += 10) {
    const ceil = floor + 9;
    const inBin = hires.filter(h => (h.composite ?? -1) >= floor && (h.composite ?? -1) <= ceil);
    if (inBin.length === 0) {
      bins.push({
        label: `${floor}–${ceil}`,
        floor,
        count: 0,
        meanPerformance: 0,
        meanTenureDays: 0,
        goodRate: 0,
      });
      continue;
    }
    const perf = inBin.reduce((a, h) => a + h.outcome.performance, 0) / inBin.length;
    const tenure = inBin.reduce((a, h) => a + h.outcome.tenureDays, 0) / inBin.length;
    const good = inBin.filter(h => h.outcome.performance >= GOOD_HIRE_FLOOR).length / inBin.length;
    bins.push({
      label: `${floor}–${ceil}`,
      floor,
      count: inBin.length,
      meanPerformance: round2(perf),
      meanTenureDays: Math.round(tenure),
      goodRate: round2(good),
    });
  }
  return bins;
}

function buildSurpriseCases(hires: HireRecord[]): SurpriseCase[] {
  const out: SurpriseCase[] = [];
  for (const h of hires) {
    const c = h.composite ?? 0;
    const p = h.outcome.performance;
    let kind: SurpriseCase['kind'] | null = null;
    if (c >= FP_COMPOSITE_FLOOR && p <= FP_PERF_FLOOR) kind = 'false_positive';
    else if (c <= FN_COMPOSITE_CEIL && p >= FN_PERF_FLOOR) kind = 'false_negative';
    if (!kind) continue;

    // Driver: the rated dim whose rating is most extreme relative to outcome.
    let driverKey: string | undefined;
    let driverLabel: string | undefined;
    let driverRating: number | undefined;
    let bestDelta = -Infinity;
    for (const dim of h.rubric) {
      const r = h.ratings[dim.key];
      if (r === undefined) continue;
      // For a FP we want the highest rating (rubric over-scored).
      // For a FN we want the lowest rating (rubric under-scored).
      const delta = kind === 'false_positive' ? r : -r;
      if (delta > bestDelta) {
        bestDelta = delta;
        driverKey = dim.key;
        driverLabel = dim.label;
        driverRating = r;
      }
    }

    const why = explainSurprise(kind, c, p, h.outcome.tenureDays, h.outcome.stillActive, driverLabel, driverRating);
    out.push({
      candidateId: h.candidateId,
      candidateName: h.candidateName,
      roleId: h.roleId,
      roleName: h.roleName,
      composite: c,
      performance: p,
      tenureDays: h.outcome.tenureDays,
      stillActive: h.outcome.stillActive,
      kind,
      driverKey,
      driverLabel,
      driverRating,
      why,
    });
  }
  // FPs first, then by magnitude of the surprise (|composite - perf*20|).
  out.sort((a, b) => {
    if (a.kind !== b.kind) return a.kind === 'false_positive' ? -1 : 1;
    const ma = Math.abs(a.composite - a.performance * 20);
    const mb = Math.abs(b.composite - b.performance * 20);
    return mb - ma;
  });
  return out;
}

function explainSurprise(
  kind: SurpriseCase['kind'],
  composite: number,
  perf: number,
  tenureDays: number,
  active: boolean,
  driverLabel?: string,
  driverRating?: number,
): string {
  if (kind === 'false_positive') {
    const tail = active
      ? `still on the team but underperforming after ${tenureDays}d.`
      : `left after ${tenureDays}d.`;
    if (driverLabel && driverRating !== undefined) {
      return `Rated ${driverRating}/5 on ${driverLabel} at interview · landed at perf ${perf}/5 — ${tail}`;
    }
    return `Composite ${composite} predicted strong-hire · landed at perf ${perf}/5 — ${tail}`;
  }
  // false negative
  const tail = active
    ? `now performing at ${perf}/5 after ${tenureDays}d.`
    : `delivered ${perf}/5 then moved on after ${tenureDays}d.`;
  if (driverLabel && driverRating !== undefined) {
    return `Rated only ${driverRating}/5 on ${driverLabel} at interview but ${tail}`;
  }
  return `Composite ${composite} predicted mixed · ${tail}`;
}

function buildRecommendation(perDim: DimensionCalibration[]): RubricRecommendation {
  const keep: RubricRecommendation['keep'] = [];
  const promote: RubricRecommendation['promote'] = [];
  const reduce: RubricRecommendation['reduce'] = [];
  const drop: RubricRecommendation['drop'] = [];

  for (const d of perDim) {
    const delta = d.suggestedWeight - d.currentWeight;
    if (d.samples < MIN_SAMPLES) {
      continue; // not enough evidence — leave alone
    }
    if (d.band === 'strong' && delta >= 0.03) {
      promote.push({
        key: d.key,
        label: d.label,
        currentWeight: round3(d.currentWeight),
        suggestedWeight: round3(d.suggestedWeight),
        delta: round3(delta),
      });
    } else if (Math.abs(delta) < 0.03 && d.band !== 'unknown') {
      keep.push({
        key: d.key,
        label: d.label,
        currentWeight: round3(d.currentWeight),
        suggestedWeight: round3(d.suggestedWeight),
        delta: round3(delta),
      });
    } else if (delta <= -0.03 && d.band !== 'unknown') {
      reduce.push({
        key: d.key,
        label: d.label,
        currentWeight: round3(d.currentWeight),
        suggestedWeight: round3(d.suggestedWeight),
        delta: round3(delta),
      });
    }
    if (Math.abs(d.rPerformance) < PP_WEAK && d.samples >= MIN_SAMPLES) {
      drop.push({
        key: d.key,
        label: d.label,
        rPerformance: round3(d.rPerformance),
        samples: d.samples,
      });
    }
  }

  promote.sort((a, b) => b.delta - a.delta);
  reduce.sort((a, b) => a.delta - b.delta);
  keep.sort((a, b) => b.suggestedWeight - a.suggestedWeight);
  return { keep, promote, reduce, drop };
}

function buildTenureByBand(hires: HireRecord[]): TenureBand[] {
  const bands: TenureBand['band'][] = ['strong_hire', 'lean_yes', 'mixed', 'lean_no', 'no_hire'];
  const buckets = new Map<TenureBand['band'], { tenure: number[]; perf: number[] }>();
  for (const b of bands) buckets.set(b, { tenure: [], perf: [] });
  for (const h of hires) {
    const rec = h.recommendation ?? recommendationFromComposite(h.composite ?? 0);
    const buck = buckets.get(rec);
    if (!buck) continue;
    buck.tenure.push(h.outcome.tenureDays);
    buck.perf.push(h.outcome.performance);
  }
  return bands.map(b => {
    const buck = buckets.get(b)!;
    const count = buck.tenure.length;
    if (count === 0) {
      return { band: b, meanTenureDays: 0, meanPerformance: 0, count: 0 };
    }
    const mt = buck.tenure.reduce((a, c) => a + c, 0) / count;
    const mp = buck.perf.reduce((a, c) => a + c, 0) / count;
    return { band: b, meanTenureDays: Math.round(mt), meanPerformance: round2(mp), count };
  });
}

function recommendationFromComposite(c: number): TenureBand['band'] {
  if (c >= 80) return 'strong_hire';
  if (c >= 65) return 'lean_yes';
  if (c >= 50) return 'mixed';
  if (c >= 35) return 'lean_no';
  return 'no_hire';
}

function brier(hires: HireRecord[]): number {
  if (hires.length === 0) return 0;
  let s = 0;
  for (const h of hires) {
    const p = clamp((h.composite ?? 0) / 100, 0, 1);
    const y = h.outcome.performance >= GOOD_HIRE_FLOOR ? 1 : 0;
    s += (p - y) ** 2;
  }
  return round3(s / hires.length);
}

function calibrationBand(
  pearson: number,
  hires: HireRecord[],
): HindsightSummary['calibrationBand'] {
  if (hires.length < MIN_SAMPLES) return 'unknown';
  if (pearson >= 0.55) return 'excellent';
  if (pearson >= 0.35) return 'good';
  if (pearson >= 0.15) return 'mixed';
  return 'concerning';
}

function actionList(s: Omit<HindsightSummary, 'actions'>): string[] {
  const a: string[] = [];
  if (s.hireCount === 0) {
    a.push('No accepted offers yet — Hindsight lights up the moment your first hire lands.');
    return a;
  }
  const verdict =
    s.calibrationBand === 'excellent' ? 'rubric is calibrated — keep going.'
    : s.calibrationBand === 'good' ? 'rubric is mostly working — tighten weights below to lift further.'
    : s.calibrationBand === 'mixed' ? 'rubric is partially predictive — promote the strong dims, prune the noise.'
    : s.calibrationBand === 'concerning' ? 'rubric is not telling you who succeeds — re-weight aggressively or replace dims.'
    : 'not enough hires to know — log post-hire outcomes monthly to grow the signal.';
  a.push(`Pearson(composite, performance) = ${s.pearson.toFixed(2)} · Brier = ${s.brierScore.toFixed(2)} — ${verdict}`);

  const strongest = s.perDimension.find(d => d.band === 'strong');
  if (strongest) {
    a.push(`Strongest signal: **${strongest.label}** (r=${strongest.rPerformance.toFixed(2)}, n=${strongest.samples}) — protect the questions that exercise it.`);
  }
  const weakest = s.perDimension.find(d => d.band === 'weak' || (d.band === 'unknown' && d.samples >= MIN_SAMPLES));
  if (weakest && weakest.key !== strongest?.key) {
    a.push(`Weakest signal: **${weakest.label}** (r=${weakest.rPerformance.toFixed(2)}) — either replace the prompts or reduce its weight.`);
  }
  if (s.rubricRecommendation.drop.length > 0) {
    const names = s.rubricRecommendation.drop.slice(0, 2).map(d => d.label).join(', ');
    a.push(`Drop candidate dim${s.rubricRecommendation.drop.length === 1 ? '' : 's'}: ${names} — |r| stays below ${PP_WEAK} across hires.`);
  }
  const fps = s.surpriseCases.filter(c => c.kind === 'false_positive').length;
  const fns = s.surpriseCases.filter(c => c.kind === 'false_negative').length;
  if (fps > 0 && fns > 0) {
    a.push(`Surprise pool: ${fps} false positive${fps === 1 ? '' : 's'}, ${fns} false negative${fns === 1 ? '' : 's'} — your calibration teachers.`);
  } else if (fps > 0) {
    a.push(`${fps} hire${fps === 1 ? '' : 's'} predicted strong but underperformed — review the panel that scored them.`);
  } else if (fns > 0) {
    a.push(`${fns} mid-composite hire${fns === 1 ? '' : 's'} delivered strongly — your bar may be too high.`);
  }
  if (s.attritionRate >= 0.20) {
    a.push(`Attrition is ${(s.attritionRate * 100).toFixed(0)}% — investigate post-hire onboarding before tuning the rubric further.`);
  }
  return a;
}

/** Two-digit round. */
function round2(v: number): number { return Math.round(v * 100) / 100; }
/** Three-digit round. */
function round3(v: number): number { return Math.round(v * 1000) / 1000; }

/** Entry point: take roles + candidate pool + outcome overrides and produce
 *  the full calibration summary. */
export function analyzeHindsight(
  roles: Role[],
  candidates: (CandidateLike & { id: number; name?: string })[],
  outcomeOverrides: Map<string, HireOutcome>,
  opts: { nowMs?: number; interviewsByKey?: Map<string, InterviewRecord> } = {},
): HindsightSummary {
  const now = opts.nowMs ?? Date.now();
  const hires = extractHires(roles, candidates, outcomeOverrides, { nowMs: now, interviewsByKey: opts.interviewsByKey });

  const hireCount = hires.length;
  const realCount = hires.filter(h => h.outcome.source === 'real').length;
  const syntheticCount = hireCount - realCount;
  const compArr = hires.map(h => h.composite ?? 0);
  const perfArr = hires.map(h => h.outcome.performance);
  const tenureArr = hires.map(h => h.outcome.tenureDays);

  const hitRate = hireCount === 0 ? 0
    : round2(hires.filter(h => h.outcome.performance >= GOOD_HIRE_FLOOR).length / hireCount);
  const meanComposite = hireCount === 0 ? 0 : Math.round(compArr.reduce((a, b) => a + b, 0) / hireCount);
  const meanPerformance = hireCount === 0 ? 0 : round2(perfArr.reduce((a, b) => a + b, 0) / hireCount);
  const meanTenureDays = hireCount === 0 ? 0 : Math.round(tenureArr.reduce((a, b) => a + b, 0) / hireCount);
  const attritionRate = hireCount === 0 ? 0
    : round2(hires.filter(h => !h.outcome.stillActive).length / hireCount);
  const p = round3(pearson(compArr, perfArr));
  const sp = round3(spearman(compArr, perfArr));
  const br = brier(hires);

  const perDimension = buildPerDimension(hires);
  const compositeBins = buildCompositeBins(hires);
  const surpriseCases = buildSurpriseCases(hires);
  const rubricRecommendation = buildRecommendation(perDimension);
  const tenureByBand = buildTenureByBand(hires);
  const calBand = calibrationBand(p, hires);

  const partial: Omit<HindsightSummary, 'actions'> = {
    generatedAt: now,
    hires,
    hireCount,
    realCount,
    syntheticCount,
    hitRate,
    meanComposite,
    meanPerformance,
    meanTenureDays,
    attritionRate,
    pearson: p,
    spearman: sp,
    brierScore: br,
    perDimension,
    compositeBins,
    surpriseCases,
    rubricRecommendation,
    tenureByBand,
    calibrationBand: calBand,
  };

  return { ...partial, actions: actionList(partial) };
}

// ---------- markdown brief ----------

function asPct(v: number): string { return `${Math.round(v * 100)}%`; }

export function buildBrief(s: HindsightSummary): string {
  const lines: string[] = [];
  lines.push(`# Hindsight — Post-Hire Calibration Brief`);
  lines.push('');
  lines.push(`*${new Date(s.generatedAt).toISOString().slice(0, 10)} · ${s.hireCount} hire${s.hireCount === 1 ? '' : 's'} reviewed (${s.realCount} real outcomes, ${s.syntheticCount} synthesised)*`);
  lines.push('');
  lines.push(`## Headline`);
  lines.push(`- **Calibration band:** ${s.calibrationBand}`);
  lines.push(`- **Hit rate (perf ≥ 4):** ${asPct(s.hitRate)}`);
  lines.push(`- **Mean composite → mean performance:** ${s.meanComposite} → ${s.meanPerformance.toFixed(2)}/5`);
  lines.push(`- **Pearson r:** ${s.pearson.toFixed(2)} · **Spearman:** ${s.spearman.toFixed(2)} · **Brier:** ${s.brierScore.toFixed(2)}`);
  lines.push(`- **Attrition rate:** ${asPct(s.attritionRate)} · **Mean tenure:** ${s.meanTenureDays}d`);
  lines.push('');
  if (s.actions.length > 0) {
    lines.push(`## Actions`);
    for (const a of s.actions) lines.push(`- ${a}`);
    lines.push('');
  }
  if (s.perDimension.length > 0) {
    lines.push(`## Rubric dimensions ranked by predictive power`);
    lines.push('');
    lines.push(`| Dimension | n | r(perf) | r(tenure) | Power | Current → Suggested | Δ |`);
    lines.push(`|---|---:|---:|---:|---:|---:|---:|`);
    for (const d of s.perDimension) {
      const delta = d.weightDelta;
      const sign = delta > 0 ? `+${delta.toFixed(3)}` : delta.toFixed(3);
      lines.push(`| ${d.label} | ${d.samples} | ${d.rPerformance.toFixed(2)} | ${d.rTenure.toFixed(2)} | ${d.predictivePower} | ${d.currentWeight.toFixed(3)} → ${d.suggestedWeight.toFixed(3)} | ${sign} |`);
    }
    lines.push('');
  }
  if (s.rubricRecommendation.promote.length > 0) {
    lines.push(`## Promote`);
    for (const r of s.rubricRecommendation.promote) {
      lines.push(`- **${r.label}** → +${r.delta.toFixed(3)} (suggested ${r.suggestedWeight.toFixed(3)})`);
    }
    lines.push('');
  }
  if (s.rubricRecommendation.reduce.length > 0) {
    lines.push(`## Reduce`);
    for (const r of s.rubricRecommendation.reduce) {
      lines.push(`- **${r.label}** → ${r.delta.toFixed(3)} (suggested ${r.suggestedWeight.toFixed(3)})`);
    }
    lines.push('');
  }
  if (s.rubricRecommendation.drop.length > 0) {
    lines.push(`## Drop candidates`);
    for (const r of s.rubricRecommendation.drop) {
      lines.push(`- **${r.label}** — r=${r.rPerformance.toFixed(2)} over n=${r.samples}`);
    }
    lines.push('');
  }
  if (s.surpriseCases.length > 0) {
    lines.push(`## Surprise hires`);
    for (const c of s.surpriseCases.slice(0, 6)) {
      const tag = c.kind === 'false_positive' ? 'FP' : 'FN';
      lines.push(`- **[${tag}] ${c.candidateName}** (${c.roleName}) · composite ${c.composite} · perf ${c.performance}/5 — ${c.why}`);
    }
    lines.push('');
  }
  if (s.compositeBins.some(b => b.count > 0)) {
    lines.push(`## Calibration curve`);
    lines.push('');
    lines.push(`| Composite | n | mean perf | good rate | mean tenure (d) |`);
    lines.push(`|---|---:|---:|---:|---:|`);
    for (const b of s.compositeBins) {
      if (b.count === 0) continue;
      lines.push(`| ${b.label} | ${b.count} | ${b.meanPerformance.toFixed(2)} | ${asPct(b.goodRate)} | ${b.meanTenureDays} |`);
    }
  }
  return lines.join('\n');
}

// ---------- localStorage persistence ----------

const HIRE_KEY = 'credicrew:hires:v1';

type StoredOutcome = HireOutcome;

function readAllStored(): StoredOutcome[] {
  if (typeof window === 'undefined') return [];
  try {
    const raw = localStorage.getItem(HIRE_KEY);
    if (!raw) return [];
    const list = JSON.parse(raw);
    return Array.isArray(list) ? list : [];
  } catch {
    return [];
  }
}

function writeAllStored(list: StoredOutcome[]): void {
  if (typeof window === 'undefined') return;
  localStorage.setItem(HIRE_KEY, JSON.stringify(list));
}

export function listOutcomes(): HireOutcome[] {
  return readAllStored();
}

export function outcomeMap(): Map<string, HireOutcome> {
  const m = new Map<string, HireOutcome>();
  for (const o of readAllStored()) {
    m.set(`${o.candidateId}::${o.roleId}`, o);
  }
  return m;
}

export function setOutcome(o: HireOutcome): HireOutcome[] {
  const list = readAllStored();
  const i = list.findIndex(x => x.candidateId === o.candidateId && x.roleId === o.roleId);
  const next = { ...o, source: 'real' as const };
  if (i < 0) list.unshift(next);
  else list[i] = next;
  writeAllStored(list);
  return list;
}

export function clearOutcome(candidateId: number, roleId: string): HireOutcome[] {
  const list = readAllStored().filter(o => !(o.candidateId === candidateId && o.roleId === roleId));
  writeAllStored(list);
  return list;
}

export function clearAllOutcomes(): void {
  writeAllStored([]);
}

// ---------- interview lookup helper ----------

/** Build an `interviewsByKey` map from the hire shortlist by walking the
 *  per-role interview list once. Mirrors how the page wires the engine. */
export function interviewsByKey(roles: Role[]): Map<string, InterviewRecord> {
  const m = new Map<string, InterviewRecord>();
  if (typeof window === 'undefined') return m;
  for (const role of roles) {
    for (const e of role.shortlist) {
      if (e.status !== HIRE_STATUS) continue;
      const r = getInterview(role.id, e.candidateId);
      if (r) m.set(`${role.id}::${e.candidateId}`, r);
    }
  }
  return m;
}

/** Demo seeder: ensures every offer-status entry has a baseline interview
 *  record so the dim-rated math has something to chew on. We don't auto-fill
 *  ratings (that would invalidate the calibration on real data); we only
 *  ensure the rubric exists in case the recruiter is auditing pre-rubric
 *  hires. Returns the count created. */
export function ensureInterviewsForHires(
  roles: Role[],
  candidates: (CandidateLike & { id: number; name?: string })[],
): number {
  const byId = new Map<number, CandidateLike & { id: number; name?: string }>();
  for (const c of candidates) byId.set(c.id, c);
  let created = 0;
  for (const role of roles) {
    for (const e of role.shortlist) {
      if (e.status !== HIRE_STATUS) continue;
      const existing = getInterview(role.id, e.candidateId);
      if (existing) continue;
      const cand = byId.get(e.candidateId);
      if (!cand) continue;
      ensureInterviewRecord({
        roleId: role.id,
        candidateId: e.candidateId,
        plan: role.plan,
      });
      created += 1;
    }
  }
  return created;
}

