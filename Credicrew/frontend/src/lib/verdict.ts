// Verdict — Rejection Ontology & JD-Refinement Advisor.
//
// Every prior Credicrew surface answers *who to pick*. Discover ranks the
// pool. Decision Studio ranks who interviewed best. Forecast Studio
// predicts whether the hire will close. Crosswind reroutes whom you have.
// Revive reactivates whom you passed on. Hindsight looks at hires 90 days
// on. Nobody, until now, opens the graveyard and asks the two questions
// every quarter-two recruiter opens with: *why am I passing everyone?* and
// *is my JD the reason, or is my pool the reason?*.
//
// Verdict is the diagnostic. For every candidate sitting in a role's
// shortlist with status = `passed`, it re-computes `matchCandidate(plan,
// candidate)` and drops the pass into one of a seven-cell ontology in
// strict priority order:
//
//   1. culture_signal   score ≥ 65 and skills ≥ 60% and seniority match
//                        and location full/partial — the panel said no
//                        despite a spec fit. This is the healthy category:
//                        it means the human signal is doing the filtering
//                        the spec cannot.
//   2. location_gap      plan.location set (non-remote) and match = none
//   3. seniority_over    candidate tier > wanted + 1
//   4. seniority_under   candidate tier < wanted
//   5. skills_short      matched < 40% of plan.skills (min 3 skills)
//   6. mixed_signal      score 40-64 with no dominant reason
//   7. other             default fallback
//
// The `signalHealth` verdict on the mix reads:
//
//   healthy      culture_signal ≥ 40%           panel doing signal work
//   spec_leak    seniority_* + location_gap ≥ 50%   JD spec is filtering
//                                              people the sourcer should
//                                              have. This is the JD leak.
//   overfished   skills_short ≥ 50%             source pool is off-spec
//   mixed        otherwise
//
// The **Refinement Advisor** turns the mix into deterministic,
// impact-quantified JD suggestions:
//
//   • seniority_over  ≥ 3, share ≥ 20%   → split into Senior + Staff
//   • seniority_under ≥ 3, share ≥ 30%   → tighten the min-seniority bar
//   • location_gap ≥ 25%                 → open remote / hybrid
//   • skills_short ≥ 40% with a common missing skill S ≥ 3 rejects
//                                        → move S to nice-to-have
//   • culture_signal ≥ 40%               → advisory only: spec is well-tuned
//
// Every suggestion carries `action` (imperative one-liner), `impact`
// (candidates recoverable), `confidence` (0-100 driven by evidence count),
// and `basis` (why the engine surfaced it). The advisor never *applies* to
// the plan itself — that's a per-row user click in the UI.
//
// Mirrored on the backend at `app/services/verdict.py` — every physics
// constant here is duplicated there so the API and the browser produce
// byte-identical mixes and suggestions.

import { matchCandidate, type CandidateLike, type MatchResult, type QueryPlan } from '@/lib/match';

// Priority-ordered category list. Order matters: the first bucket a
// passed candidate qualifies for wins.
export const CATEGORIES = [
  'culture_signal',
  'location_gap',
  'seniority_over',
  'seniority_under',
  'skills_short',
  'mixed_signal',
  'other',
] as const;

export type Category = (typeof CATEGORIES)[number];

export const CATEGORY_LABEL: Record<Category, string> = {
  culture_signal: 'Culture signal',
  location_gap: 'Location gap',
  seniority_over: 'Over-qualified',
  seniority_under: 'Under-qualified',
  skills_short: 'Skills short',
  mixed_signal: 'Mixed signal',
  other: 'Other',
};

export const CATEGORY_HEX: Record<Category, string> = {
  culture_signal: '#10b981', // emerald 500
  location_gap: '#0ea5e9',   // sky 500
  seniority_over: '#a855f7', // violet 500
  seniority_under: '#f59e0b', // amber 500
  skills_short: '#f43f5e',   // rose 500
  mixed_signal: '#94a3b8',   // slate 400
  other: '#64748b',          // slate 500
};

export const CATEGORY_BLURB: Record<Category, string> = {
  culture_signal: 'Spec fit but the panel said no — a healthy filter',
  location_gap: 'Passed on location alone — spec is filtering the pool',
  seniority_over: 'Over the seniority bar — spec is too narrow at the top',
  seniority_under: 'Under the seniority bar — spec is leaking into sourcing',
  skills_short: 'Missing core skills — source pool is off-spec',
  mixed_signal: 'Moderate on every axis, no dominant reason',
  other: 'No dominant category — not enough signal',
};

// Seniority ladder (matches `match.ts` SENIORITY constant order).
// Index 0 = intern, index 5 = principal. `lead` maps to senior/staff span.
export const SENIORITY_LADDER = [
  'intern',
  'junior',
  'mid',
  'senior',
  'staff',
  'principal',
] as const;

const SENIORITY_TIER: Record<string, number> = {
  intern: 0,
  junior: 1,
  mid: 2,
  senior: 3,
  lead: 3, // team lead ~ senior in the pay-band lattice
  staff: 4,
  principal: 5,
};

// Physics thresholds — mirrored in Python.
export const CULTURE_SCORE_FLOOR = 65;
export const CULTURE_SKILL_FLOOR = 0.6;
export const SKILLS_SHORT_FLOOR = 0.4;
export const MIN_PLAN_SKILLS_FOR_SKILLS_SHORT = 3;
export const SENIORITY_OVER_GAP = 1; // must exceed wanted+1 to over-qualify

// Refinement thresholds.
export const R_SENIORITY_OVER_MIN_N = 3;
export const R_SENIORITY_OVER_MIN_SHARE = 0.2;
export const R_SENIORITY_UNDER_MIN_N = 3;
export const R_SENIORITY_UNDER_MIN_SHARE = 0.3;
export const R_LOCATION_MIN_SHARE = 0.25;
export const R_SKILLS_SHORT_MIN_SHARE = 0.4;
export const R_MISSING_SKILL_MIN_N = 3;
export const R_CULTURE_MIN_SHARE = 0.4;

// Health thresholds.
export const H_HEALTHY_CULTURE = 0.4;
export const H_SPEC_LEAK = 0.5;
export const H_OVERFISHED = 0.5;

// Health band hex — read the verdict by colour.
export const HEALTH_HEX: Record<SignalHealth, string> = {
  healthy: '#10b981',
  spec_leak: '#f59e0b',
  overfished: '#f43f5e',
  mixed: '#94a3b8',
  unknown: '#475569',
};

export const HEALTH_LABEL: Record<SignalHealth, string> = {
  healthy: 'Healthy',
  spec_leak: 'Spec leak',
  overfished: 'Overfished',
  mixed: 'Mixed',
  unknown: 'Insufficient data',
};

export type SignalHealth =
  | 'healthy'
  | 'spec_leak'
  | 'overfished'
  | 'mixed'
  | 'unknown';

// ---------- Types ----------

export type VerdictCandidate = CandidateLike & {
  id: number;
  name: string;
  location?: string;
};

export type RejectedEntry = {
  candidateId: number;
  name: string;
  category: Category;
  match: MatchResult;
  wantedTier: number | null;
  candidateTier: number | null;
  primaryDriver: string;
};

export type MixCell = {
  category: Category;
  count: number;
  share: number;
  entries: RejectedEntry[];
};

export type Suggestion = {
  id: string;
  category: Category | 'portfolio';
  action: string;
  basis: string;
  impact: number;      // # candidates the change would recover
  confidence: number;  // 0..100
  planDelta?: PlanDelta;
};

export type PlanDelta = {
  kind: 'add_location' | 'demote_skill' | 'widen_seniority' | 'narrow_seniority';
  value: string;
};

export type RoleVerdict = {
  roleId: string;
  roleName: string;
  planSummary: {
    skills: string[];
    location?: string;
    seniority?: string;
  };
  totalPassed: number;
  totalConsidered: number;
  passShare: number;       // passed / considered
  cells: MixCell[];        // sorted desc by count
  topReason: Category | null;
  signalHealth: SignalHealth;
  funnelWaste: number;     // 0..100 mean composite of passed pool
  bandDistribution: {
    strong: number;
    solid: number;
    weak: number;
  };
  commonMissingSkills: Array<{ skill: string; count: number }>;
  suggestions: Suggestion[];
};

export type VerdictPortfolio = {
  roles: RoleVerdict[];
  totalPassed: number;
  totalConsidered: number;
  passShare: number;
  aggregatedCells: MixCell[];  // roll-up across all roles
  signalHealth: SignalHealth;
  funnelWaste: number;
  topReason: Category | null;
  topSuggestions: Suggestion[]; // top 3 across portfolio by impact*confidence
};

// ---------- Physics ----------

export function tierOf(sen: string | undefined | null): number | null {
  if (!sen) return null;
  const t = SENIORITY_TIER[sen];
  return typeof t === 'number' ? t : null;
}

function pickCategory(
  plan: QueryPlan,
  m: MatchResult,
  wantedTier: number | null,
  candTier: number | null,
): Category {
  const skillCov = plan.skills.length === 0 ? 1 : m.matchedSkills.length / plan.skills.length;

  // (1) culture_signal — spec fit but human said no.
  if (
    m.score >= CULTURE_SCORE_FLOOR &&
    skillCov >= CULTURE_SKILL_FLOOR &&
    m.seniority.match &&
    (m.location.match === 'full' || m.location.match === 'partial')
  ) {
    return 'culture_signal';
  }

  // (2) location_gap — spec has a location constraint that failed hard.
  if (plan.location && plan.location !== 'remote' && m.location.match === 'none') {
    return 'location_gap';
  }

  // (3) seniority_over — candidate too senior for the ask.
  if (
    wantedTier !== null &&
    candTier !== null &&
    candTier > wantedTier + SENIORITY_OVER_GAP
  ) {
    return 'seniority_over';
  }

  // (4) seniority_under — candidate below the ask.
  if (
    wantedTier !== null &&
    candTier !== null &&
    candTier < wantedTier
  ) {
    return 'seniority_under';
  }

  // (5) skills_short — spec-substantial and candidate missed most.
  if (
    plan.skills.length >= MIN_PLAN_SKILLS_FOR_SKILLS_SHORT &&
    skillCov < SKILLS_SHORT_FLOOR
  ) {
    return 'skills_short';
  }

  // (6) mixed_signal — moderate, no single dominant miss.
  if (m.score >= 40 && m.score < CULTURE_SCORE_FLOOR) {
    return 'mixed_signal';
  }

  return 'other';
}

function driverFor(cat: Category, m: MatchResult, wantedSen: string | undefined): string {
  switch (cat) {
    case 'culture_signal':
      return `Composite ${m.score} · panel signal`;
    case 'location_gap':
      return `Location · ${m.location.wanted ?? 'unknown'}`;
    case 'seniority_over':
      return `${m.seniority.candidate ?? 'senior'} → wanted ${wantedSen ?? 'lower'}`;
    case 'seniority_under':
      return `${m.seniority.candidate ?? 'junior'} → wanted ${wantedSen ?? 'higher'}`;
    case 'skills_short': {
      const miss = m.missingSkills.slice(0, 2).join(', ');
      return miss ? `Missing ${miss}` : 'Skills coverage low';
    }
    case 'mixed_signal':
      return `Composite ${m.score} · nothing dominant`;
    default:
      return 'Unclassified';
  }
}

// Compute health from an aggregated mix (share by category).
function computeHealth(
  cells: MixCell[],
  totalPassed: number,
): SignalHealth {
  if (totalPassed < 3) return 'unknown';
  const byCat: Record<Category, number> = {
    culture_signal: 0,
    location_gap: 0,
    seniority_over: 0,
    seniority_under: 0,
    skills_short: 0,
    mixed_signal: 0,
    other: 0,
  };
  for (const c of cells) byCat[c.category] = c.share;
  const spec = byCat.location_gap + byCat.seniority_over + byCat.seniority_under;
  if (byCat.culture_signal >= H_HEALTHY_CULTURE) return 'healthy';
  if (spec >= H_SPEC_LEAK) return 'spec_leak';
  if (byCat.skills_short >= H_OVERFISHED) return 'overfished';
  return 'mixed';
}

function topReasonOf(cells: MixCell[]): Category | null {
  if (!cells.length) return null;
  // cells are already sorted desc by count in analyzeRole
  return cells[0].category;
}

function bandOf(score: number): 'strong' | 'solid' | 'weak' {
  if (score >= 80) return 'strong';
  if (score >= 60) return 'solid';
  return 'weak';
}

function suggestionsFor(role: {
  roleId: string;
  cells: Record<Category, MixCell>;
  totalPassed: number;
  planSkills: string[];
  planLocation?: string;
  planSeniority?: string;
  missingSkillCounts: Array<{ skill: string; count: number }>;
}): Suggestion[] {
  const out: Suggestion[] = [];
  const { cells, totalPassed, planSkills, planLocation, planSeniority, missingSkillCounts } = role;

  const oCell = cells.seniority_over;
  if (
    oCell &&
    oCell.count >= R_SENIORITY_OVER_MIN_N &&
    oCell.share >= R_SENIORITY_OVER_MIN_SHARE &&
    planSeniority
  ) {
    const nextTier = SENIORITY_LADDER[
      Math.min(
        SENIORITY_LADDER.length - 1,
        (tierOf(planSeniority) ?? 3) + 1,
      )
    ];
    out.push({
      id: `${role.roleId}:sen_over`,
      category: 'seniority_over',
      action: `Split into ${planSeniority} + ${nextTier} variants`,
      basis: `${oCell.count} candidates (${Math.round(oCell.share * 100)}%) passed for over-qualification alone — the ${nextTier} band is landing in your funnel unclaimed.`,
      impact: oCell.count,
      confidence: Math.min(95, 40 + oCell.count * 8),
      planDelta: { kind: 'widen_seniority', value: nextTier },
    });
  }

  const uCell = cells.seniority_under;
  if (
    uCell &&
    uCell.count >= R_SENIORITY_UNDER_MIN_N &&
    uCell.share >= R_SENIORITY_UNDER_MIN_SHARE
  ) {
    out.push({
      id: `${role.roleId}:sen_under`,
      category: 'seniority_under',
      action: `Tighten the minimum-seniority bar in the JD copy`,
      basis: `${uCell.count} under-tier candidates (${Math.round(uCell.share * 100)}%) entered your pipeline — the spec isn't loud enough about the floor.`,
      impact: uCell.count,
      confidence: Math.min(95, 40 + uCell.count * 8),
      planDelta: planSeniority
        ? { kind: 'narrow_seniority', value: planSeniority }
        : undefined,
    });
  }

  const lCell = cells.location_gap;
  if (
    lCell &&
    lCell.count >= 2 &&
    lCell.share >= R_LOCATION_MIN_SHARE &&
    planLocation
  ) {
    out.push({
      id: `${role.roleId}:loc`,
      category: 'location_gap',
      action: `Open the role to remote or hybrid`,
      basis: `${lCell.count} candidates (${Math.round(lCell.share * 100)}%) were passed on location alone — the ${planLocation} constraint is the single reason they didn't make it.`,
      impact: lCell.count,
      confidence: Math.min(90, 35 + lCell.count * 10),
      planDelta: { kind: 'add_location', value: 'remote' },
    });
  }

  const sCell = cells.skills_short;
  if (
    sCell &&
    sCell.share >= R_SKILLS_SHORT_MIN_SHARE &&
    planSkills.length >= MIN_PLAN_SKILLS_FOR_SKILLS_SHORT
  ) {
    const top = missingSkillCounts[0];
    if (top && top.count >= R_MISSING_SKILL_MIN_N && planSkills.includes(top.skill)) {
      out.push({
        id: `${role.roleId}:skill:${top.skill}`,
        category: 'skills_short',
        action: `Move "${top.skill}" from must-have to nice-to-have`,
        basis: `${top.count} of the passed pool would have cleared the bar without "${top.skill}" — it's the single largest disqualifier in your reject pile.`,
        impact: top.count,
        confidence: Math.min(90, 30 + top.count * 8),
        planDelta: { kind: 'demote_skill', value: top.skill },
      });
    }
  }

  const cCell = cells.culture_signal;
  if (
    cCell &&
    cCell.share >= R_CULTURE_MIN_SHARE &&
    totalPassed >= 4
  ) {
    out.push({
      id: `${role.roleId}:culture`,
      category: 'culture_signal',
      action: 'Advisory — spec is well-tuned; panel is doing the signal work',
      basis: `${cCell.count} of ${totalPassed} passed candidates cleared the spec but the panel said no anyway — that's the healthy pattern. Leave the JD alone; focus tuning on the interview loop instead.`,
      impact: 0,
      confidence: Math.min(90, 40 + cCell.count * 5),
    });
  }

  return out.sort(
    (a, b) => (b.impact * b.confidence) - (a.impact * a.confidence),
  );
}

// ---------- Role-level analysis ----------

export function analyzeRole(input: {
  roleId: string;
  roleName: string;
  plan: QueryPlan;
  passedCandidates: VerdictCandidate[];
  totalShortlistSize: number;
}): RoleVerdict {
  const { roleId, roleName, plan, passedCandidates, totalShortlistSize } = input;
  const wantedTier = tierOf(plan.seniority);

  const entries: RejectedEntry[] = passedCandidates.map(c => {
    const m = matchCandidate(plan, c);
    const candTier = tierOf(m.seniority.candidate ?? undefined);
    const category = pickCategory(plan, m, wantedTier, candTier);
    return {
      candidateId: c.id,
      name: c.name,
      category,
      match: m,
      wantedTier,
      candidateTier: candTier,
      primaryDriver: driverFor(category, m, plan.seniority),
    };
  });

  const totalPassed = entries.length;
  const buckets: Record<Category, RejectedEntry[]> = {
    culture_signal: [],
    location_gap: [],
    seniority_over: [],
    seniority_under: [],
    skills_short: [],
    mixed_signal: [],
    other: [],
  };
  for (const e of entries) buckets[e.category].push(e);

  const cellsAll: Record<Category, MixCell> = {} as Record<Category, MixCell>;
  const cells: MixCell[] = [];
  for (const cat of CATEGORIES) {
    const arr = buckets[cat];
    const cell: MixCell = {
      category: cat,
      count: arr.length,
      share: totalPassed > 0 ? arr.length / totalPassed : 0,
      entries: arr
        .slice()
        .sort((a, b) => b.match.score - a.match.score)
        .slice(0, 8),
    };
    cellsAll[cat] = cell;
    if (arr.length > 0) cells.push(cell);
  }
  cells.sort((a, b) => b.count - a.count || CATEGORIES.indexOf(a.category) - CATEGORIES.indexOf(b.category));

  // Missing-skill leaderboard across passed entries.
  const missCounter: Map<string, number> = new Map();
  for (const e of entries) {
    for (const s of e.match.missingSkills) {
      missCounter.set(s, (missCounter.get(s) ?? 0) + 1);
    }
  }
  const commonMissingSkills = Array.from(missCounter.entries())
    .map(([skill, count]) => ({ skill, count }))
    .sort((a, b) => b.count - a.count || a.skill.localeCompare(b.skill))
    .slice(0, 5);

  const bandDistribution = { strong: 0, solid: 0, weak: 0 };
  let waste = 0;
  for (const e of entries) {
    bandDistribution[bandOf(e.match.score)] += 1;
    waste += e.match.score;
  }
  const funnelWaste = totalPassed > 0 ? Math.round(waste / totalPassed) : 0;

  const suggestions = suggestionsFor({
    roleId,
    cells: cellsAll,
    totalPassed,
    planSkills: plan.skills,
    planLocation: plan.location,
    planSeniority: plan.seniority,
    missingSkillCounts: commonMissingSkills,
  });

  return {
    roleId,
    roleName,
    planSummary: {
      skills: plan.skills,
      location: plan.location,
      seniority: plan.seniority,
    },
    totalPassed,
    totalConsidered: totalShortlistSize,
    passShare: totalShortlistSize > 0 ? totalPassed / totalShortlistSize : 0,
    cells,
    topReason: topReasonOf(cells),
    signalHealth: computeHealth(cells, totalPassed),
    funnelWaste,
    bandDistribution,
    commonMissingSkills,
    suggestions,
  };
}

// ---------- Portfolio roll-up ----------

export function analyzePortfolio(roles: RoleVerdict[]): VerdictPortfolio {
  const totalPassed = roles.reduce((a, r) => a + r.totalPassed, 0);
  const totalConsidered = roles.reduce((a, r) => a + r.totalConsidered, 0);

  const counts: Record<Category, number> = {
    culture_signal: 0,
    location_gap: 0,
    seniority_over: 0,
    seniority_under: 0,
    skills_short: 0,
    mixed_signal: 0,
    other: 0,
  };
  let waste = 0;
  for (const r of roles) {
    for (const c of r.cells) counts[c.category] += c.count;
    waste += r.funnelWaste * r.totalPassed;
  }

  const aggregatedCells: MixCell[] = [];
  for (const cat of CATEGORIES) {
    if (counts[cat] > 0) {
      aggregatedCells.push({
        category: cat,
        count: counts[cat],
        share: totalPassed > 0 ? counts[cat] / totalPassed : 0,
        entries: [],
      });
    }
  }
  aggregatedCells.sort(
    (a, b) => b.count - a.count || CATEGORIES.indexOf(a.category) - CATEGORIES.indexOf(b.category),
  );

  const health = computeHealth(aggregatedCells, totalPassed);
  const topReason = aggregatedCells.length ? aggregatedCells[0].category : null;
  const funnelWaste = totalPassed > 0 ? Math.round(waste / totalPassed) : 0;

  // Rank suggestions across the portfolio by expected recovery
  // (impact × confidence). Advisory (impact=0) suggestions drop to bottom.
  const bag: Suggestion[] = roles.flatMap(r => r.suggestions);
  const topSuggestions = bag
    .slice()
    .sort((a, b) => (b.impact * b.confidence) - (a.impact * a.confidence))
    .slice(0, 3);

  return {
    roles,
    totalPassed,
    totalConsidered,
    passShare: totalConsidered > 0 ? totalPassed / totalConsidered : 0,
    aggregatedCells,
    signalHealth: health,
    funnelWaste,
    topReason,
    topSuggestions,
  };
}

// ---------- Formatting helpers used by the UI ----------

export function formatShare(x: number): string {
  return `${Math.round(x * 100)}%`;
}
