// Forecast Studio engine.
//
// Every other Credicrew surface is descriptive: who's in the funnel, who
// scored what, who's offering what comp, which channel is paying off.
// None of them answer the question that every hiring manager opens with —
// **"Will I have a hire by start_date?"** Forecast Studio is the missing
// predictive layer.
//
// The engine takes the current pipeline shape (counts at each stage), the
// recruiter's conversion + velocity assumptions (default-seeded from
// industry medians, fully overridable), and runs a Monte-Carlo simulation
// of every candidate's forward walk through the funnel. Each trial yields
// an earliest hire-date (the date the strongest accepted offer hits the
// end of its notice period); aggregating thousands of trials gives:
//
//   • probability of a hire by the target date,
//   • a P10 / P50 / P90 fan chart of earliest-hire dates,
//   • the expected number of advancers reaching each downstream stage,
//   • the **bottleneck** stage (the one with the worst marginal
//     contribution to the dropout cliff),
//   • a **sensitivity tornado** ranking which lever (conversion or
//     velocity at each stage) moves P(hire-by-target) the most, and
//   • a concrete **recommendations** list ("add 4 candidates to Outreach
//     to hit Jun 20 at 75%").
//
// Pure functions. Deterministic for a given seed so the UI doesn't
// flicker on re-render. Mirrored in `backend/app/services/forecast.py`.

import type { Role } from '@/lib/roles';
import { countByStatus } from '@/lib/roles';

// ---------- types ----------

export type ForecastStage = 'new' | 'outreach' | 'screening' | 'interview' | 'offer';

export const FORECAST_PROGRESSION: ForecastStage[] = [
  'new',
  'outreach',
  'screening',
  'interview',
  'offer',
];

export const FORECAST_STAGE_LABEL: Record<ForecastStage, string> = {
  new: 'New',
  outreach: 'Outreach',
  screening: 'Screening',
  interview: 'Interview',
  offer: 'Offer',
};

/** Probability of advancing from this stage to the next. 0..1 */
export type ConversionMap = Record<ForecastStage, number>;

/** Median days spent at this stage before advancing or dropping. */
export type VelocityMap = Record<ForecastStage, number>;

export type ForecastAssumptions = {
  /** p(advance from stage → next). offer → "accept". */
  conversion: ConversionMap;
  /** median days at each stage (LogNormal median). offer → days to decision. */
  velocity: VelocityMap;
  /** post-accept notice period before the candidate can start. */
  noticePeriodDays: number;
  /** LogNormal sigma — higher = more variance per stage. */
  durationSigma: number;
};

export const DEFAULT_CONVERSION: ConversionMap = {
  new: 0.65,
  outreach: 0.40,
  screening: 0.60,
  interview: 0.35,
  offer: 0.70,
};

export const DEFAULT_VELOCITY: VelocityMap = {
  new: 2,
  outreach: 4,
  screening: 5,
  interview: 8,
  offer: 4,
};

export const DEFAULT_ASSUMPTIONS: ForecastAssumptions = {
  conversion: DEFAULT_CONVERSION,
  velocity: DEFAULT_VELOCITY,
  noticePeriodDays: 30,
  durationSigma: 0.45,
};

export type ForecastInput = {
  /** counts of candidates currently sitting at each stage. */
  funnel: Record<ForecastStage, number>;
  /** ISO date string (YYYY-MM-DD) the recruiter is targeting for start. */
  targetDate: string;
  /** ms since epoch — the "now" anchor for the simulation. */
  now?: number;
  assumptions?: Partial<ForecastAssumptions>;
  /** Monte-Carlo trial count. Defaults to 4000. */
  trials?: number;
  /** RNG seed. Defaults to a stable value of the funnel. */
  seed?: number;
};

export type ForecastFunnelStage = {
  key: ForecastStage;
  here: number;
  expectedAdvancers: number; // E[# who reach the next stage]
  expectedHires: number;     // E[# who eventually become hires]
};

export type ForecastSensitivityRow = {
  lever:
    | { kind: 'conversion'; stage: ForecastStage }
    | { kind: 'velocity'; stage: ForecastStage }
    | { kind: 'add_candidates'; stage: ForecastStage };
  label: string;
  baseline: number;          // P(hire-by-target) baseline
  upliftPlus: number;        // P after positive nudge
  upliftMinus: number;       // P after negative nudge
  delta: number;             // |+| + |-| — total swing
};

export type ForecastResult = {
  trials: number;
  targetDate: string;
  now: number;
  /** P(at least one hire on/before target date). 0..1 */
  probabilityByTarget: number;
  /** Distribution of earliest-hire date over trials with any hire. */
  hireDate: {
    p10: string | null;
    p50: string | null;
    p90: string | null;
    /** fraction of trials that produced ANY hire (any date). */
    anyHireProbability: number;
  };
  /** Mean # of hires per trial. */
  expectedHires: number;
  funnel: ForecastFunnelStage[];
  /** Stage whose marginal probability contributes most to the dropout cliff. */
  bottleneck: ForecastStage | null;
  /** Ranked levers by total swing in P(hire-by-target). */
  sensitivity: ForecastSensitivityRow[];
  /** Pithy action suggestions. */
  recommendations: string[];
  assumptions: ForecastAssumptions;
};

// ---------- utils ----------

const DAY_MS = 86_400_000;

/** Deterministic mulberry32 PRNG. */
function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return function () {
    a = (a + 0x6D2B79F5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** Box-Muller transform for a standard normal sample. */
function gauss(rng: () => number): number {
  let u = rng();
  const v = rng();
  if (u < 1e-9) u = 1e-9;
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
}

/** LogNormal sample with the given median and sigma. */
function logNormalDays(rng: () => number, median: number, sigma: number): number {
  if (median <= 0) return 0;
  return Math.exp(Math.log(median) + sigma * gauss(rng));
}

function clamp01(x: number): number {
  return x < 0 ? 0 : x > 1 ? 1 : x;
}

function isoDate(ms: number): string {
  return new Date(ms).toISOString().slice(0, 10);
}

function parseIsoDay(iso: string): number {
  // Pin to start of UTC day so target comparisons are inclusive.
  return Date.parse(`${iso}T00:00:00.000Z`);
}

function mergeAssumptions(over?: Partial<ForecastAssumptions>): ForecastAssumptions {
  if (!over) return DEFAULT_ASSUMPTIONS;
  return {
    conversion: { ...DEFAULT_CONVERSION, ...(over.conversion ?? {}) },
    velocity: { ...DEFAULT_VELOCITY, ...(over.velocity ?? {}) },
    noticePeriodDays: over.noticePeriodDays ?? DEFAULT_ASSUMPTIONS.noticePeriodDays,
    durationSigma: over.durationSigma ?? DEFAULT_ASSUMPTIONS.durationSigma,
  };
}

function seedFromFunnel(funnel: Record<ForecastStage, number>): number {
  // FNV-1a over the funnel counts so re-rendering with the same shape
  // returns identical numbers but reshuffles when candidates move.
  let h = 0x811c9dc5;
  for (const stage of FORECAST_PROGRESSION) {
    h ^= funnel[stage] & 0xff;
    h = (h * 0x01000193) >>> 0;
  }
  return (h || 1) >>> 0;
}

// ---------- engine ----------

/** Build an input funnel from a saved Role. */
export function funnelFromRole(role: Role): Record<ForecastStage, number> {
  const counts = countByStatus(role);
  return {
    new: counts.new ?? 0,
    outreach: counts.outreach ?? 0,
    screening: counts.screening ?? 0,
    interview: counts.interview ?? 0,
    offer: counts.offer ?? 0,
  };
}

/**
 * Core Monte-Carlo runner. Returns:
 *   anyHire: fraction of trials with at least one hire,
 *   hits: trials that produced a hire by `targetMs`,
 *   sortedHireDates: sorted earliest-hire-date per trial (ms),
 *   expectedHires: mean # of hires per trial,
 *   reaches: per-stage reach counts summed across trials.
 */
function runMc(
  funnel: Record<ForecastStage, number>,
  targetMs: number,
  now: number,
  a: ForecastAssumptions,
  trials: number,
  seed: number,
): {
  anyHire: number;
  byTargetProb: number;
  sortedHireDates: number[];
  expectedHires: number;
  reaches: Record<ForecastStage, number>;
  hires: Record<ForecastStage, number>; // # who started at stage S and hired
} {
  const rng = mulberry32(seed);
  const sortedHireDates: number[] = [];
  let byTarget = 0;
  let hireSum = 0;
  const reaches: Record<ForecastStage, number> = {
    new: 0, outreach: 0, screening: 0, interview: 0, offer: 0,
  };
  const hires: Record<ForecastStage, number> = {
    new: 0, outreach: 0, screening: 0, interview: 0, offer: 0,
  };

  for (let t = 0; t < trials; t++) {
    let earliest: number | null = null;
    let trialHires = 0;
    for (const stage of FORECAST_PROGRESSION) {
      const count = funnel[stage] | 0;
      for (let i = 0; i < count; i++) {
        // Simulate stage walk and count reach side-effect inline.
        let tcur = now;
        let dropped = false;
        const startIdx = FORECAST_PROGRESSION.indexOf(stage);
        for (let s = startIdx; s < FORECAST_PROGRESSION.length; s++) {
          const st = FORECAST_PROGRESSION[s];
          reaches[st] += 1;
          const days = logNormalDays(rng, a.velocity[st], a.durationSigma);
          tcur += days * DAY_MS;
          if (rng() >= clamp01(a.conversion[st])) {
            dropped = true;
            break;
          }
        }
        if (!dropped) {
          const hireMs = tcur + a.noticePeriodDays * DAY_MS;
          trialHires += 1;
          hires[stage] += 1;
          if (earliest === null || hireMs < earliest) earliest = hireMs;
        }
      }
    }
    if (earliest !== null) {
      sortedHireDates.push(earliest);
      if (earliest <= targetMs) byTarget += 1;
    }
    hireSum += trialHires;
  }
  sortedHireDates.sort((a, b) => a - b);
  return {
    anyHire: sortedHireDates.length / trials,
    byTargetProb: byTarget / trials,
    sortedHireDates,
    expectedHires: hireSum / trials,
    reaches,
    hires,
  };
}

function percentile(sorted: number[], p: number): number | null {
  if (sorted.length === 0) return null;
  const idx = Math.min(sorted.length - 1, Math.max(0, Math.floor(p * sorted.length)));
  return sorted[idx];
}

/** A quick deterministic baseline — no MC needed — for sensitivity speedups. */
function fastByTargetEstimate(
  funnel: Record<ForecastStage, number>,
  targetMs: number,
  now: number,
  a: ForecastAssumptions,
): number {
  // Expected # of hires assuming everyone takes ~median time. We use a
  // closed-form lower-bound: 1 - P(zero hires by target).
  let probZero = 1;
  for (const stage of FORECAST_PROGRESSION) {
    const count = funnel[stage] | 0;
    if (count === 0) continue;
    const startIdx = FORECAST_PROGRESSION.indexOf(stage);
    // p that this candidate succeeds AND finishes by target
    let pSuccess = 1;
    let cumDays = 0;
    for (let s = startIdx; s < FORECAST_PROGRESSION.length; s++) {
      const st = FORECAST_PROGRESSION[s];
      pSuccess *= clamp01(a.conversion[st]);
      cumDays += a.velocity[st];
    }
    cumDays += a.noticePeriodDays;
    const finishMs = now + cumDays * DAY_MS;
    if (finishMs > targetMs) {
      // Apply a log-normal CDF-ish heuristic — for the fast pass we just
      // pin to 0 if the median path overruns; the full MC catches the rest.
      pSuccess *= 0.25;
    }
    probZero *= Math.pow(1 - pSuccess, count);
  }
  return 1 - probZero;
}

// ---------- public API ----------

/** Run the forecast. */
export function forecastFunnel(input: ForecastInput): ForecastResult {
  const now = input.now ?? Date.now();
  const trials = Math.max(200, input.trials ?? 4000);
  const assumptions = mergeAssumptions(input.assumptions);
  const funnel = input.funnel;
  const targetMs = parseIsoDay(input.targetDate);
  const seed = input.seed ?? seedFromFunnel(funnel);

  const total = FORECAST_PROGRESSION.reduce((s, k) => s + (funnel[k] | 0), 0);

  // Empty pipeline → nothing to forecast.
  if (total === 0) {
    return {
      trials,
      targetDate: input.targetDate,
      now,
      probabilityByTarget: 0,
      hireDate: { p10: null, p50: null, p90: null, anyHireProbability: 0 },
      expectedHires: 0,
      funnel: FORECAST_PROGRESSION.map(k => ({
        key: k,
        here: 0,
        expectedAdvancers: 0,
        expectedHires: 0,
      })),
      bottleneck: null,
      sensitivity: [],
      recommendations: [
        'No candidates in the pipeline yet — add a shortlist before forecasting.',
      ],
      assumptions,
    };
  }

  const main = runMc(funnel, targetMs, now, assumptions, trials, seed);

  const funnelOut: ForecastFunnelStage[] = FORECAST_PROGRESSION.map(k => ({
    key: k,
    here: funnel[k] | 0,
    expectedAdvancers: +(main.reaches[k] / trials).toFixed(2),
    expectedHires: +(main.hires[k] / trials).toFixed(2),
  }));

  // Bottleneck: stage with the biggest marginal probability mass lost.
  // We compute, for each stage, the *upstream survivors expected at that
  // stage* times (1 - conversion). The stage with the largest such drop
  // is where the most candidates die.
  const expectedReachAt: Record<ForecastStage, number> = { ...main.reaches };
  let bottleneck: ForecastStage | null = null;
  let bestDrop = 0;
  for (const k of FORECAST_PROGRESSION) {
    const reachMean = expectedReachAt[k] / trials;
    const drop = reachMean * (1 - clamp01(assumptions.conversion[k]));
    if (drop > bestDrop) {
      bestDrop = drop;
      bottleneck = k;
    }
  }

  // Sensitivity — tornado over conversion + velocity at each stage.
  // We use a smaller MC budget for each perturbation to keep things snappy.
  const sensTrials = Math.max(400, Math.floor(trials / 4));
  const baseline = main.byTargetProb;

  const sensitivity: ForecastSensitivityRow[] = [];

  for (const stage of FORECAST_PROGRESSION) {
    // Conversion ±15 percentage points (clamped to [0,1]).
    const cv = assumptions.conversion[stage];
    const cvPlus = clamp01(cv + 0.15);
    const cvMinus = clamp01(cv - 0.15);
    const aPlus = {
      ...assumptions,
      conversion: { ...assumptions.conversion, [stage]: cvPlus },
    };
    const aMinus = {
      ...assumptions,
      conversion: { ...assumptions.conversion, [stage]: cvMinus },
    };
    const plusP = runMc(funnel, targetMs, now, aPlus, sensTrials, seed ^ 0x9e3779b1).byTargetProb;
    const minusP = runMc(funnel, targetMs, now, aMinus, sensTrials, seed ^ 0x85ebca77).byTargetProb;
    sensitivity.push({
      lever: { kind: 'conversion', stage },
      label: `${FORECAST_STAGE_LABEL[stage]} conversion`,
      baseline,
      upliftPlus: plusP,
      upliftMinus: minusP,
      delta: Math.abs(plusP - baseline) + Math.abs(baseline - minusP),
    });

    // Velocity ±30%.
    const v = assumptions.velocity[stage];
    const aFast = {
      ...assumptions,
      velocity: { ...assumptions.velocity, [stage]: Math.max(0.25, v * 0.7) },
    };
    const aSlow = {
      ...assumptions,
      velocity: { ...assumptions.velocity, [stage]: v * 1.3 },
    };
    const fastP = runMc(funnel, targetMs, now, aFast, sensTrials, seed ^ 0xc2b2ae35).byTargetProb;
    const slowP = runMc(funnel, targetMs, now, aSlow, sensTrials, seed ^ 0x27d4eb2f).byTargetProb;
    sensitivity.push({
      lever: { kind: 'velocity', stage },
      label: `${FORECAST_STAGE_LABEL[stage]} speed`,
      baseline,
      upliftPlus: fastP,
      upliftMinus: slowP,
      delta: Math.abs(fastP - baseline) + Math.abs(baseline - slowP),
    });
  }

  // Add-candidates lever — only useful for the upstream stages where the
  // recruiter can plausibly inject more pipeline mass.
  for (const stage of ['new', 'outreach'] as ForecastStage[]) {
    const bumpFunnel = { ...funnel, [stage]: (funnel[stage] | 0) + 5 };
    const cutFunnel = { ...funnel, [stage]: Math.max(0, (funnel[stage] | 0) - 2) };
    const plusP = runMc(bumpFunnel, targetMs, now, assumptions, sensTrials, seed ^ 0x165667b1).byTargetProb;
    const minusP = runMc(cutFunnel, targetMs, now, assumptions, sensTrials, seed ^ 0xd3a2646c).byTargetProb;
    sensitivity.push({
      lever: { kind: 'add_candidates', stage },
      label: `Add 5 to ${FORECAST_STAGE_LABEL[stage]}`,
      baseline,
      upliftPlus: plusP,
      upliftMinus: minusP,
      delta: Math.abs(plusP - baseline) + Math.abs(baseline - minusP),
    });
  }

  sensitivity.sort((a, b) => b.delta - a.delta);

  // Recommendations — pull from the top sensitivity rows + funnel facts.
  const recs: string[] = [];
  const p10ms = percentile(main.sortedHireDates, 0.10);
  const p50ms = percentile(main.sortedHireDates, 0.50);
  const p90ms = percentile(main.sortedHireDates, 0.90);

  if (baseline >= 0.75) {
    recs.push(
      `Strong shape — ${Math.round(baseline * 100)}% chance to close by ${input.targetDate}. Focus on keeping the top of the funnel warm.`,
    );
  } else if (baseline >= 0.4) {
    recs.push(
      `Tight but feasible — ${Math.round(baseline * 100)}% chance to close by ${input.targetDate}. Apply the top lever below to tip it past 75%.`,
    );
  } else if (baseline > 0) {
    recs.push(
      `At risk — only ${Math.round(baseline * 100)}% chance to close by ${input.targetDate}. Consider widening the funnel or moving the date.`,
    );
  } else {
    recs.push(
      `Almost certain to miss — pipeline can't realistically close by ${input.targetDate}. Push the target out or escalate sourcing.`,
    );
  }

  if (bottleneck) {
    recs.push(
      `The ${FORECAST_STAGE_LABEL[bottleneck]} stage is your dropout cliff — ` +
        `tighten the bar earlier or coach the panel to convert more of them.`,
    );
  }
  const top = sensitivity[0];
  if (top && top.delta > 0.05) {
    const arrow = top.upliftPlus > top.upliftMinus ? '+' : '-';
    recs.push(
      `Biggest lever: ${top.label} — pushing it favourably moves P(hire-by-target) by ${arrow}${Math.round(
        Math.max(Math.abs(top.upliftPlus - top.baseline), Math.abs(top.baseline - top.upliftMinus)) * 100,
      )} points.`,
    );
  }
  if (p50ms !== null) {
    recs.push(
      `Median earliest-hire date: ${isoDate(p50ms)} (P10 ${
        p10ms !== null ? isoDate(p10ms) : '—'
      } · P90 ${p90ms !== null ? isoDate(p90ms) : '—'}).`,
    );
  }

  return {
    trials,
    targetDate: input.targetDate,
    now,
    probabilityByTarget: baseline,
    hireDate: {
      p10: p10ms !== null ? isoDate(p10ms) : null,
      p50: p50ms !== null ? isoDate(p50ms) : null,
      p90: p90ms !== null ? isoDate(p90ms) : null,
      anyHireProbability: main.anyHire,
    },
    expectedHires: +main.expectedHires.toFixed(2),
    funnel: funnelOut,
    bottleneck,
    sensitivity,
    recommendations: recs,
    assumptions,
  };
}

/**
 * Closed-form fast estimate of P(hire-by-target). Used by the UI for
 * the "quick what-if" sliders that update on drag without re-running
 * Monte Carlo.
 */
export function quickProbabilityEstimate(
  funnel: Record<ForecastStage, number>,
  targetDate: string,
  now: number,
  overrides?: Partial<ForecastAssumptions>,
): number {
  return fastByTargetEstimate(
    funnel,
    parseIsoDay(targetDate),
    now,
    mergeAssumptions(overrides),
  );
}

/** Default target date: 60 days from now. */
export function defaultTargetDate(now: number = Date.now()): string {
  return isoDate(now + 60 * DAY_MS);
}
