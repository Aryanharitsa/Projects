// Offer Studio engine.
//
// Closes the hiring loop: JD → match → outreach → interview → decision →
// **offer**. Three concerns live here:
//
//   1. Deterministic compensation benchmarking (P25/P50/P75/P90 base bands,
//      equity bands, sign-on, target bonus) derived from the parsed JD plan
//      and the candidate's matched-skill set.
//   2. An explainable win-probability model — a transparent logistic with
//      per-factor contributions so the recruiter can see exactly *why* the
//      number moves when they drag a slider.
//   3. A Markdown offer-letter composer + a small structured serialiser the
//      print-ready preview consumes.
//
// Pure functions. Mirrored in `backend/app/services/offer.py` so a
// programmatic / agentic client gets byte-identical comp bands, win
// probabilities, and letter bodies.

import type { QueryPlan } from '@/lib/match';

// ---------- types ----------

export type Currency = 'INR' | 'USD';

export type CompBand = {
  p25: number;
  p50: number;
  p75: number;
  p90: number;
  currency: Currency;
  unit: 'LPA' | 'annual';
};

export type EquityBand = {
  /** percent of company, e.g. 0.08 means 0.08% */
  pct_p25: number;
  pct_p50: number;
  pct_p75: number;
};

export type CompBenchmark = {
  base: CompBand;
  equity: EquityBand;
  targetBonusPct: number;          // recommended annual target bonus %
  signOnSuggested: number;         // suggested sign-on (same unit as base)
  seniority: string;
  location: string;
  citymult: number;
  skillPremium: number;            // 0..0.20 — sum of rare-skill bumps
  rationale: string[];             // short bullets used by the UI tooltip
};

export type OfferDraft = {
  base: number;                    // LPA INR or annual USD
  equityPct: number;               // %
  targetBonusPct: number;          // %
  signOn: number;                  // same unit as base
  vestingYears: number;
  cliffMonths: number;
  startDate?: string;              // YYYY-MM-DD
  expiresOn?: string;              // YYYY-MM-DD
  notes?: string;
};

export type WinFactor = {
  key: string;
  label: string;
  /** contribution to logit (positive = pulls toward acceptance) */
  delta: number;
};

export type WinProbability = {
  probability: number;             // 0..1
  logit: number;
  factors: WinFactor[];            // sorted by |delta| desc, sign preserved
  band: 'long_shot' | 'uphill' | 'coin_flip' | 'likely' | 'lock';
};

export type OfferLetterContext = {
  companyName: string;
  hiringManager?: string;
  candidateName: string;
  roleName: string;
  location: string;
  offer: OfferDraft;
  benchmark: CompBenchmark;
};

// ---------- comp bands ----------

// Seniority base bands (INR LPA, P50). Calibrated to plausible 2025 India
// market — tweak in one place if the market shifts.
const SENIORITY_BASE_INR_P50: Record<string, number> = {
  intern: 6,
  junior: 14,
  mid: 26,
  senior: 48,
  staff: 82,
  principal: 135,
  lead: 70,
};

const SENIORITY_BONUS_PCT: Record<string, number> = {
  intern: 0,
  junior: 5,
  mid: 8,
  senior: 12,
  staff: 15,
  principal: 18,
  lead: 12,
};

// Equity (% of company) by seniority. P25/P50/P75 of typical early-stage
// India offers. Intern gets 0.
const SENIORITY_EQUITY_PCT: Record<string, [number, number, number]> = {
  intern: [0, 0, 0],
  junior: [0.01, 0.02, 0.04],
  mid: [0.04, 0.07, 0.12],
  senior: [0.10, 0.18, 0.30],
  staff: [0.25, 0.40, 0.65],
  principal: [0.50, 0.90, 1.40],
  lead: [0.18, 0.30, 0.50],
};

// City multipliers vs Bengaluru = 1.0.
const CITY_MULT: Record<string, number> = {
  bengaluru: 1.00,
  mumbai: 1.05,
  delhi: 0.96,
  gurgaon: 0.96,
  noida: 0.94,
  hyderabad: 0.95,
  pune: 0.92,
  chennai: 0.90,
  kolkata: 0.82,
  ahmedabad: 0.80,
  kochi: 0.78,
  remote: 0.95,
  hybrid: 0.97,
  onsite: 1.00,
};

// Skill rarity multipliers. Each "rare" matched skill bumps the base band
// by `+0.04` (capped at 0.20 across all matched skills) — reflects pricier
// supply curves for these stacks.
const RARE_SKILLS: Set<string> = new Set([
  'rust', 'kubernetes', 'terraform', 'pytorch', 'kafka', 'llm',
  'grpc', 'pulsar', 'wasm',
]);

const MODERN_SKILLS: Set<string> = new Set([
  'typescript', 'fastapi', 'next.js', 'gcp', 'aws', 'mongodb', 'postgres',
  'react', 'svelte', 'go', 'graphql', 'redis',
]);

export function citymult(location: string | undefined): { mult: number; key: string } {
  if (!location) return { mult: 0.90, key: 'unknown' };
  const k = location.toLowerCase().trim();
  if (k in CITY_MULT) return { mult: CITY_MULT[k], key: k };
  return { mult: 0.90, key: k };
}

export function skillPremium(matchedSkills: string[]): { premium: number; rare: string[]; modern: string[] } {
  const rare: string[] = [];
  const modern: string[] = [];
  for (const s of matchedSkills) {
    if (RARE_SKILLS.has(s)) rare.push(s);
    else if (MODERN_SKILLS.has(s)) modern.push(s);
  }
  // Rare skills bump 4% each, modern skills bump 1.5% each (cap 20%).
  const raw = rare.length * 0.04 + modern.length * 0.015;
  return { premium: Math.min(0.20, Math.round(raw * 1000) / 1000), rare, modern };
}

function bandSpread(p50: number): { p25: number; p75: number; p90: number } {
  // ±18% to P25/P75, +36% to P90 — wider top tail captures heat the
  // numbers shouldn't average over.
  return {
    p25: Math.round(p50 * 0.82),
    p75: Math.round(p50 * 1.18),
    p90: Math.round(p50 * 1.36),
  };
}

/** Build the full compensation benchmark for a (plan, matchedSkills) pair. */
export function benchmarkComp(
  plan: QueryPlan | undefined,
  matchedSkills: string[],
  opts?: { currency?: Currency },
): CompBenchmark {
  const seniority = (plan?.seniority ?? 'mid') as keyof typeof SENIORITY_BASE_INR_P50;
  const senKey = seniority in SENIORITY_BASE_INR_P50 ? seniority : 'mid';
  const senBaseP50 = SENIORITY_BASE_INR_P50[senKey];
  const { mult: cmult, key: ckey } = citymult(plan?.location);
  const { premium, rare, modern } = skillPremium(matchedSkills);

  const p50 = Math.round(senBaseP50 * cmult * (1 + premium));
  const { p25, p75, p90 } = bandSpread(p50);

  const [eqP25, eqP50, eqP75] = SENIORITY_EQUITY_PCT[senKey];
  const targetBonus = SENIORITY_BONUS_PCT[senKey];

  // Suggested sign-on: half of (P75 − P50) clipped to [0, 12% of P50].
  const signOnSuggested = Math.max(0, Math.min(
    Math.round(p50 * 0.12),
    Math.round((p75 - p50) * 0.5),
  ));

  const rationale: string[] = [
    `Seniority anchor: ${senKey} → P50 ${senBaseP50} LPA (Bengaluru-normalised).`,
    `Location multiplier (${ckey}): ×${cmult.toFixed(2)}.`,
  ];
  if (rare.length) rationale.push(`Rare-skill premium: ${rare.join(', ')} → +${(rare.length * 4)}%.`);
  if (modern.length) rationale.push(`Modern-stack premium: ${modern.join(', ')} → +${(modern.length * 1.5).toFixed(1)}%.`);
  if (!rare.length && !modern.length) rationale.push(`No skill premium (${matchedSkills.length} matched).`);
  rationale.push(`Suggested sign-on covers ~50% of the P50→P75 gap.`);

  return {
    base: { p25, p50, p75, p90, currency: opts?.currency ?? 'INR', unit: 'LPA' },
    equity: { pct_p25: eqP25, pct_p50: eqP50, pct_p75: eqP75 },
    targetBonusPct: targetBonus,
    signOnSuggested,
    seniority: senKey,
    location: ckey,
    citymult: cmult,
    skillPremium: premium,
    rationale,
  };
}

/** A reasonable starting draft snapped to P50 base / P50 equity. */
export function suggestDraft(benchmark: CompBenchmark): OfferDraft {
  return {
    base: benchmark.base.p50,
    equityPct: benchmark.equity.pct_p50,
    targetBonusPct: benchmark.targetBonusPct,
    signOn: benchmark.signOnSuggested,
    vestingYears: 4,
    cliffMonths: 12,
  };
}

/** Where the offer sits in the comp band. Returns 0..1 normalized to
 *  [P25, P90]; <0 means below P25, >1 means above P90. */
export function bandPosition(offer: OfferDraft, benchmark: CompBenchmark): number {
  const span = benchmark.base.p90 - benchmark.base.p25;
  if (span <= 0) return 0.5;
  return (offer.base - benchmark.base.p25) / span;
}

// ---------- win probability model ----------

export type WinSignals = {
  /** Interview composite 0..100, or null. */
  composite: number | null;
  /** Match score 0..100. */
  matchScore: number;
  /** Days since the outreach went out. */
  daysSinceOutreach?: number;
  /** True if Decision flags include `thin_data`. */
  thinData?: boolean;
  /** True if Decision flags include `low_confidence`. */
  lowConfidence?: boolean;
  /** Matched skill list (for rarity in the demand signal). */
  matchedSkills: string[];
  /** Optional candidate location override (otherwise uses plan). */
  candidateLocation?: string;
};

function sigmoid(x: number): number {
  if (x > 16) return 1;
  if (x < -16) return 0;
  return 1 / (1 + Math.exp(-x));
}

function bandFor(p: number): WinProbability['band'] {
  if (p >= 0.85) return 'lock';
  if (p >= 0.65) return 'likely';
  if (p >= 0.45) return 'coin_flip';
  if (p >= 0.25) return 'uphill';
  return 'long_shot';
}

/** Logistic win-probability model. */
export function winProbability(
  offer: OfferDraft,
  benchmark: CompBenchmark,
  signals: WinSignals,
): WinProbability {
  const factors: WinFactor[] = [];

  // Intercept — conversion is non-trivial; assume some recruiter overhead.
  factors.push({ key: 'baseline', label: 'Baseline conversion', delta: -0.6 });

  // Base pull vs P50: each +10% above P50 contributes +0.35; each -10% below
  // P50 contributes -0.35.
  const baseRatio = offer.base / Math.max(1, benchmark.base.p50) - 1;
  factors.push({
    key: 'base_pull',
    label: `Base vs P50 (${(baseRatio * 100).toFixed(0)}%)`,
    delta: Math.round(3.5 * baseRatio * 100) / 100,
  });

  // Equity vs P50 equity. Each +50% above contributes ~+0.4.
  const eqP50 = Math.max(0.001, benchmark.equity.pct_p50);
  const eqRatio = offer.equityPct / eqP50 - 1;
  factors.push({
    key: 'equity_pull',
    label: `Equity vs P50 (${(eqRatio * 100).toFixed(0)}%)`,
    delta: Math.round(0.8 * eqRatio * 100) / 100,
  });

  // Sign-on as fraction of base. 10% sign-on contributes +0.18.
  const signOnRatio = offer.signOn / Math.max(1, offer.base);
  if (signOnRatio > 0) {
    factors.push({
      key: 'signon',
      label: `Sign-on (${(signOnRatio * 100).toFixed(0)}% of base)`,
      delta: Math.round(1.8 * signOnRatio * 100) / 100,
    });
  }

  // Target bonus % vs recommended. Small effect.
  const bonusDelta = (offer.targetBonusPct - benchmark.targetBonusPct) / 100;
  if (Math.abs(bonusDelta) > 0.005) {
    factors.push({
      key: 'bonus',
      label: `Target bonus (${(bonusDelta * 100).toFixed(0)}pp vs market)`,
      delta: Math.round(1.2 * bonusDelta * 100) / 100,
    });
  }

  // External demand: rare-skill density + a composite-strength bump (top
  // candidates field more competing offers).
  const { rare } = skillPremium(signals.matchedSkills);
  const compositeDemand = signals.composite !== null && signals.composite >= 80 ? 0.45 : 0;
  const demand = rare.length * 0.18 + compositeDemand;
  if (demand > 0) {
    factors.push({
      key: 'demand',
      label: rare.length > 0
        ? `External demand (${rare.length} rare skill${rare.length === 1 ? '' : 's'}${compositeDemand ? ' · top tier' : ''})`
        : `External demand (top tier candidate)`,
      delta: Math.round(-demand * 100) / 100,
    });
  }

  // Recruiter confidence: if we have a strong composite, we're confident
  // about the pitch and slightly more credible to the candidate. Small bump.
  if (signals.composite !== null) {
    const credibility = (signals.composite - 60) / 100; // -.6..+.4 over 0..100
    factors.push({
      key: 'credibility',
      label: `Pitch credibility (composite ${signals.composite})`,
      delta: Math.round(0.4 * credibility * 100) / 100,
    });
  }

  // Outreach decay: every 7 days past 7d shaves 0.2 off the logit. Stale
  // outreach loses momentum.
  if (signals.daysSinceOutreach !== undefined) {
    const decay = -Math.max(0, signals.daysSinceOutreach - 7) / 7 * 0.2;
    if (decay < 0) {
      factors.push({
        key: 'momentum',
        label: `Outreach momentum (${signals.daysSinceOutreach}d old)`,
        delta: Math.round(decay * 100) / 100,
      });
    }
  }

  // Decision risk flags lower acceptance odds (uncertain candidates over-shop).
  if (signals.thinData) {
    factors.push({ key: 'thin_data', label: 'Thin interview data', delta: -0.5 });
  } else if (signals.lowConfidence) {
    factors.push({ key: 'low_confidence', label: 'Low interview confidence', delta: -0.25 });
  }

  // Match-score nudge — strong fit slightly raises odds.
  const matchPull = (signals.matchScore - 60) / 200;
  if (Math.abs(matchPull) > 0.01) {
    factors.push({
      key: 'match',
      label: `Match score ${signals.matchScore}`,
      delta: Math.round(matchPull * 100) / 100,
    });
  }

  // Aggregate.
  const logit = factors.reduce((s, f) => s + f.delta, 0);
  const probability = sigmoid(logit);

  // Sort by |delta| desc for the UI, baseline last.
  const sorted = factors
    .filter(f => f.key !== 'baseline')
    .sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta));
  const baseline = factors.find(f => f.key === 'baseline')!;
  sorted.push(baseline);

  return {
    probability,
    logit: Math.round(logit * 1000) / 1000,
    factors: sorted,
    band: bandFor(probability),
  };
}

export const BAND_LABEL: Record<WinProbability['band'], string> = {
  long_shot: 'Long shot',
  uphill: 'Uphill',
  coin_flip: 'Coin flip',
  likely: 'Likely',
  lock: 'Likely lock',
};

export const BAND_HUE: Record<WinProbability['band'], string> = {
  long_shot: '#f43f5e',
  uphill: '#fb7185',
  coin_flip: '#facc15',
  likely: '#818cf8',
  lock: '#34d399',
};

// ---------- offer letter ----------

function inrFmt(n: number, unit: 'LPA' | 'annual', currency: Currency): string {
  if (currency === 'USD') return `$${n.toLocaleString('en-US')} ${unit}`;
  if (unit === 'LPA') return `₹${n.toLocaleString('en-IN')} LPA`;
  return `₹${n.toLocaleString('en-IN')} / yr`;
}

export function buildOfferLetter(ctx: OfferLetterContext): string {
  const o = ctx.offer;
  const b = ctx.benchmark;
  const lines: string[] = [];
  lines.push(`# Offer of Employment — ${ctx.roleName}`);
  lines.push('');
  lines.push(`**${ctx.companyName}**`);
  if (ctx.hiringManager) lines.push(`Hiring manager: ${ctx.hiringManager}`);
  lines.push('');
  lines.push(`Dear ${ctx.candidateName.split(/\s+/)[0]},`);
  lines.push('');
  lines.push(`We're delighted to extend an offer for the role of **${ctx.roleName}** at ${ctx.companyName}, based in ${ctx.location}. Below are the proposed terms — please review and respond by ${o.expiresOn ?? 'the agreed date'}.`);
  lines.push('');
  lines.push('## Compensation');
  lines.push('');
  lines.push(`| Item | Value |`);
  lines.push(`|---|---|`);
  lines.push(`| Base salary | ${inrFmt(o.base, b.base.unit, b.base.currency)} |`);
  lines.push(`| Target performance bonus | ${o.targetBonusPct.toFixed(0)}% of base |`);
  if (o.signOn > 0) {
    lines.push(`| Sign-on bonus | ${inrFmt(o.signOn, b.base.unit, b.base.currency)} (paid on join) |`);
  }
  lines.push(`| Equity grant | ${o.equityPct.toFixed(3)}% of fully-diluted capitalisation |`);
  lines.push(`| Vesting | ${o.vestingYears} years, ${o.cliffMonths}-month cliff, monthly thereafter |`);
  if (o.startDate) lines.push(`| Proposed start date | ${o.startDate} |`);
  lines.push('');
  lines.push('## Benchmarking note');
  lines.push('');
  lines.push(`This package sits at the **${describeBandPosition(bandPosition(o, b))}** of the ${b.seniority} band for ${b.location}.`);
  lines.push(`(Band: P25 ${inrFmt(b.base.p25, b.base.unit, b.base.currency)} · P50 ${inrFmt(b.base.p50, b.base.unit, b.base.currency)} · P75 ${inrFmt(b.base.p75, b.base.unit, b.base.currency)} · P90 ${inrFmt(b.base.p90, b.base.unit, b.base.currency)}.)`);
  lines.push('');
  if (o.notes && o.notes.trim().length > 0) {
    lines.push('## Notes');
    lines.push('');
    lines.push(o.notes.trim());
    lines.push('');
  }
  lines.push('## Next steps');
  lines.push('');
  lines.push('Reply to this email with any questions; once confirmed, we\'ll send the formal employment contract along with onboarding documentation. We\'re looking forward to working with you.');
  lines.push('');
  lines.push('Warm regards,');
  lines.push(ctx.hiringManager ?? `The ${ctx.companyName} team`);
  return lines.join('\n');
}

function describeBandPosition(pos: number): string {
  if (pos < 0) return 'below P25 — below market';
  if (pos < 0.25) return 'P25 — entry of band';
  if (pos < 0.55) return 'P50 — middle of band';
  if (pos < 0.85) return 'P75 — top quartile';
  if (pos <= 1) return 'P90 — top tail';
  return 'above P90 — premium';
}

// ---------- localStorage state ----------

const OFFER_KEY = 'credicrew:offers:v1';

type OfferStore = Record<string, OfferDraft>; // keyed `${roleId}:${candidateId}`

function readOffers(): OfferStore {
  if (typeof window === 'undefined') return {};
  try {
    const raw = localStorage.getItem(OFFER_KEY);
    if (!raw) return {};
    const obj = JSON.parse(raw);
    return obj && typeof obj === 'object' ? obj : {};
  } catch {
    return {};
  }
}

function writeOffers(store: OfferStore): void {
  if (typeof window === 'undefined') return;
  localStorage.setItem(OFFER_KEY, JSON.stringify(store));
}

function offerKey(roleId: string, candidateId: number): string {
  return `${roleId}:${candidateId}`;
}

export function getOffer(roleId: string, candidateId: number): OfferDraft | null {
  return readOffers()[offerKey(roleId, candidateId)] ?? null;
}

export function saveOffer(roleId: string, candidateId: number, draft: OfferDraft): OfferDraft {
  const store = readOffers();
  store[offerKey(roleId, candidateId)] = draft;
  writeOffers(store);
  return draft;
}

export function listOffersForRole(roleId: string): Record<number, OfferDraft> {
  const store = readOffers();
  const out: Record<number, OfferDraft> = {};
  const prefix = `${roleId}:`;
  for (const [k, v] of Object.entries(store)) {
    if (k.startsWith(prefix)) {
      const cid = Number(k.slice(prefix.length));
      if (!Number.isNaN(cid)) out[cid] = v;
    }
  }
  return out;
}

export function deleteOffer(roleId: string, candidateId: number): void {
  const store = readOffers();
  delete store[offerKey(roleId, candidateId)];
  writeOffers(store);
}
