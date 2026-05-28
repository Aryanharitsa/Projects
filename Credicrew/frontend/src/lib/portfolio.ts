// Hiring Command Center engine.
//
// Every other surface in Credicrew is single-role / single-candidate: you
// open a role, you work one shortlist, you score one interview, you draft
// one offer. A recruiter running ten reqs at once has had no bird's-eye
// view — no portfolio funnel, no comp-spend forecast, no "which role is
// stalling and who's my strongest person across everything" answer.
//
// This module is the missing aggregation layer. It takes a flattened
// snapshot of every role + its shortlist (with each candidate's match
// score, interview composite, offer draft, and accept-probability already
// resolved by the caller) and rolls it up into one portfolio summary:
// hero KPIs, an aggregate stage funnel with conversion, a committed-vs-
// expected comp forecast, per-role health scores, a cross-role talent
// leaderboard, and a prioritised attention feed.
//
// Pure functions only — no localStorage, no network. The page resolves the
// per-candidate fields from the existing engines and hands clean data in,
// which keeps this byte-for-byte mirrorable in
// `backend/app/services/portfolio.py`.

import type { PipelineStatus } from '@/lib/roles';
import type { Recommendation } from '@/lib/interview';

// ---------- input shape ----------

export type PortfolioOffer = {
  base: number;            // LPA INR (or annual unit — caller-consistent)
  equityPct: number;       // % of company
  targetBonusPct: number;  // %
  signOn: number;          // same unit as base
};

export type PortfolioCandidate = {
  candidateId: number;
  name: string;
  role?: string;
  status: PipelineStatus;
  addedAt: number;                       // epoch ms — proxy for time-in-pipeline
  matchScore: number;                    // 0..100
  composite: number | null;              // interview composite, null if none
  confidence: number;                    // 0..1 (ratedCount / totalCount)
  recommendation: Recommendation | null;
  offer?: PortfolioOffer;                // present iff a draft exists
  winProbability?: number;               // 0..1 — accept odds for the offer
};

export type PortfolioRole = {
  id: string;
  name: string;
  seniority?: string;
  location?: string;
  createdAt: number;
  updatedAt: number;
  candidates: PortfolioCandidate[];
};

export type PortfolioInput = {
  roles: PortfolioRole[];
  now?: number;
};

// ---------- output shape ----------

export type StageKey = 'new' | 'outreach' | 'screening' | 'interview' | 'offer';

export const PROGRESSION: StageKey[] = [
  'new',
  'outreach',
  'screening',
  'interview',
  'offer',
];

export type FunnelStage = {
  key: StageKey;
  here: number;            // candidates currently at this stage
  reached: number;         // reached at least this stage (cumulative from the top)
  conversionFromPrev: number | null; // reached(this) / reached(prev), null at the top
};

export type CompForecast = {
  offers: number;          // candidates with a drafted offer
  committedAnnual: number; // Σ year-1 total cash if every drafted offer is signed
  expectedAnnual: number;  // Σ total cash · accept-probability (risk-weighted)
  avgBase: number;         // mean base across drafted offers
  avgWinProbability: number; // mean accept-probability across drafted offers
  topSpendRoleId: string | null;
};

export type RoleHealth = {
  roleId: string;
  roleName: string;
  seniority?: string;
  location?: string;
  candidates: number;
  active: number;          // not passed
  interviewed: number;     // composite != null
  offers: number;          // status === 'offer'
  stale: number;           // active, non-terminal, ≥ STALE_DAYS old
  daysOpen: number;        // since createdAt
  topCandidate: { candidateId: number; name: string; hireSignal: number } | null;
  bestComposite: number | null;
  bottleneck: StageKey | null; // progression stage (excl. offer) holding the most active
  health: number | null;   // 0..100, null when there's nothing to score
};

export type TalentEntry = {
  roleId: string;
  roleName: string;
  candidateId: number;
  name: string;
  role?: string;
  status: PipelineStatus;
  matchScore: number;
  composite: number;
  hireSignal: number;
  recommendation: Recommendation | null;
};

export type AttentionKind =
  | 'stale_candidate'
  | 'offer_at_risk'
  | 'no_interviews'
  | 'fast_track'
  | 'empty_role';

export type AttentionSeverity = 'high' | 'medium' | 'low';

export type AttentionItem = {
  kind: AttentionKind;
  severity: AttentionSeverity;
  roleId: string;
  roleName: string;
  candidateId?: number;
  candidateName?: string;
  message: string;
};

export type PortfolioSummary = {
  totals: {
    roles: number;
    candidates: number;
    active: number;
    interviewed: number;
    offers: number;
    passed: number;
    staleCandidates: number;
  };
  funnel: FunnelStage[];
  compForecast: CompForecast;
  roleHealth: RoleHealth[];
  talent: TalentEntry[];
  attention: AttentionItem[];
  recommendationMix: Record<Recommendation, number>;
  portfolioHealth: number | null; // 0..100
  bottleneck: StageKey | null;     // portfolio-wide stage holding the most active
  generatedAt: number;
};

// ---------- tuning constants ----------

const STALE_DAYS = 14;
const DAY_MS = 86_400_000;
const FAST_TRACK_SIGNAL = 75;
const OFFER_RISK_PROB = 0.45;

const STAGE_LABEL: Record<StageKey, string> = {
  new: 'New',
  outreach: 'Outreach',
  screening: 'Screening',
  interview: 'Interview',
  offer: 'Offer',
};

export const STAGE_DISPLAY = STAGE_LABEL;

// ---------- math helpers ----------

function round(n: number, dp = 2): number {
  const f = 10 ** dp;
  return Math.round(n * f) / f;
}

/** Calibrated hire signal — mirrors decision.ts so the two never disagree. */
export function hireSignal(composite: number | null, confidence: number): number {
  if (composite === null) return 0;
  return Math.round(composite * Math.sqrt(Math.max(0, Math.min(1, confidence))));
}

/** Year-1 total cash for an offer draft. Mirrors peer_parity's total_cash. */
export function totalCash(o: PortfolioOffer): number {
  return o.base + o.signOn + o.base * (o.targetBonusPct / 100);
}

function severityRank(s: AttentionSeverity): number {
  return s === 'high' ? 0 : s === 'medium' ? 1 : 2;
}

// ---------- per-candidate derived view ----------

type Derived = PortfolioCandidate & {
  roleId: string;
  roleName: string;
  signal: number;
  ageDays: number;
  isActive: boolean;
  isStale: boolean;
};

function deriveCandidates(input: PortfolioInput): Derived[] {
  const now = input.now ?? Date.now();
  const out: Derived[] = [];
  for (const role of input.roles) {
    for (const c of role.candidates) {
      const ageDays = Math.max(0, Math.floor((now - c.addedAt) / DAY_MS));
      const isActive = c.status !== 'passed';
      const nonTerminal =
        c.status === 'new' ||
        c.status === 'outreach' ||
        c.status === 'screening' ||
        c.status === 'interview';
      out.push({
        ...c,
        roleId: role.id,
        roleName: role.name,
        signal: hireSignal(c.composite, c.confidence),
        ageDays,
        isActive,
        isStale: isActive && nonTerminal && ageDays >= STALE_DAYS,
      });
    }
  }
  return out;
}

// ---------- funnel ----------

function buildFunnel(rows: Derived[]): FunnelStage[] {
  const here: Record<StageKey, number> = {
    new: 0, outreach: 0, screening: 0, interview: 0, offer: 0,
  };
  for (const r of rows) {
    if (r.status === 'passed') continue;
    here[r.status as StageKey] += 1;
  }
  // reached-at-least: cumulative from the deepest stage backwards.
  const reached: Record<StageKey, number> = {
    new: 0, outreach: 0, screening: 0, interview: 0, offer: 0,
  };
  let acc = 0;
  for (let i = PROGRESSION.length - 1; i >= 0; i--) {
    acc += here[PROGRESSION[i]];
    reached[PROGRESSION[i]] = acc;
  }
  return PROGRESSION.map((key, i) => {
    const prev = i > 0 ? reached[PROGRESSION[i - 1]] : null;
    const conv = prev !== null && prev > 0 ? round(reached[key] / prev, 4) : null;
    return { key, here: here[key], reached: reached[key], conversionFromPrev: conv };
  });
}

// ---------- comp forecast ----------

function buildCompForecast(rows: Derived[]): CompForecast {
  const withOffer = rows.filter(r => r.offer);
  let committed = 0;
  let expected = 0;
  let baseSum = 0;
  let probSum = 0;
  const roleSpend: Record<string, number> = {};
  for (const r of withOffer) {
    const tc = totalCash(r.offer!);
    const p = r.winProbability ?? 0.5;
    committed += tc;
    expected += tc * p;
    baseSum += r.offer!.base;
    probSum += p;
    roleSpend[r.roleId] = (roleSpend[r.roleId] ?? 0) + tc;
  }
  const n = withOffer.length;
  let topSpendRoleId: string | null = null;
  let topSpend = -1;
  for (const [rid, spend] of Object.entries(roleSpend)) {
    if (spend > topSpend) { topSpend = spend; topSpendRoleId = rid; }
  }
  return {
    offers: n,
    committedAnnual: round(committed),
    expectedAnnual: round(expected),
    avgBase: n > 0 ? round(baseSum / n) : 0,
    avgWinProbability: n > 0 ? round(probSum / n, 4) : 0,
    topSpendRoleId,
  };
}

// ---------- per-role health ----------

function buildRoleHealth(input: PortfolioInput, rows: Derived[]): RoleHealth[] {
  const now = input.now ?? Date.now();
  const byRole = new Map<string, Derived[]>();
  for (const r of rows) {
    const list = byRole.get(r.roleId) ?? [];
    list.push(r);
    byRole.set(r.roleId, list);
  }

  return input.roles.map(role => {
    const cands = byRole.get(role.id) ?? [];
    const active = cands.filter(c => c.isActive);
    const interviewed = cands.filter(c => c.composite !== null);
    const offers = cands.filter(c => c.status === 'offer');
    const stale = cands.filter(c => c.isStale);

    // Top candidate by hire signal (interviewed only); fall back to best match.
    let top: RoleHealth['topCandidate'] = null;
    const ranked = [...interviewed].sort((a, b) => b.signal - a.signal);
    if (ranked.length > 0) {
      top = { candidateId: ranked[0].candidateId, name: ranked[0].name, hireSignal: ranked[0].signal };
    } else if (cands.length > 0) {
      const byMatch = [...cands].sort((a, b) => b.matchScore - a.matchScore)[0];
      top = { candidateId: byMatch.candidateId, name: byMatch.name, hireSignal: 0 };
    }

    const bestComposite = interviewed.length > 0
      ? Math.max(...interviewed.map(c => c.composite!))
      : null;

    // Bottleneck: the progression stage (excluding offer) with the most active.
    const stageCount: Record<string, number> = {};
    for (const c of active) {
      if (c.status === 'offer') continue;
      stageCount[c.status] = (stageCount[c.status] ?? 0) + 1;
    }
    let bottleneck: StageKey | null = null;
    let bn = 1; // require ≥ 2 to call it a bottleneck
    for (const s of PROGRESSION) {
      if (s === 'offer') continue;
      const c = stageCount[s] ?? 0;
      if (c > bn) { bn = c; bottleneck = s; }
    }

    return {
      roleId: role.id,
      roleName: role.name,
      seniority: role.seniority,
      location: role.location,
      candidates: cands.length,
      active: active.length,
      interviewed: interviewed.length,
      offers: offers.length,
      stale: stale.length,
      daysOpen: Math.max(0, Math.floor((now - role.createdAt) / DAY_MS)),
      topCandidate: top,
      bestComposite,
      bottleneck,
      health: roleHealthScore(cands),
    };
  });
}

/** Renormalised, weighted health score over whichever signals are present.
 *  Components (weights): momentum 0.30 · coverage 0.25 · quality 0.25 ·
 *  offer confidence 0.20. Absent components drop out and the remaining
 *  weights renormalise — same philosophy as the interview rubric. */
function roleHealthScore(cands: Derived[]): number | null {
  if (cands.length === 0) return null;
  const parts: { weight: number; value: number }[] = [];

  const active = cands.filter(c => c.isActive);
  if (active.length > 0) {
    const stale = active.filter(c => c.isStale).length;
    parts.push({ weight: 0.30, value: 1 - stale / active.length }); // momentum
  }

  // Coverage: of those who reached interview-or-beyond, how many are interviewed.
  const reachedInterview = cands.filter(
    c => c.status === 'interview' || c.status === 'offer',
  );
  if (reachedInterview.length > 0) {
    const done = reachedInterview.filter(c => c.composite !== null).length;
    parts.push({ weight: 0.25, value: done / reachedInterview.length });
  }

  // Quality: mean hire signal across interviewed candidates.
  const interviewed = cands.filter(c => c.composite !== null);
  if (interviewed.length > 0) {
    const meanSig = interviewed.reduce((s, c) => s + c.signal, 0) / interviewed.length;
    parts.push({ weight: 0.25, value: meanSig / 100 });
  }

  // Offer confidence: mean accept-probability across drafted offers.
  const offers = cands.filter(c => c.offer);
  if (offers.length > 0) {
    const meanP = offers.reduce((s, c) => s + (c.winProbability ?? 0.5), 0) / offers.length;
    parts.push({ weight: 0.20, value: meanP });
  }

  if (parts.length === 0) return null;
  const wsum = parts.reduce((s, p) => s + p.weight, 0);
  const score = parts.reduce((s, p) => s + p.weight * p.value, 0) / wsum;
  return Math.round(Math.max(0, Math.min(1, score)) * 100);
}

// ---------- talent leaderboard ----------

function buildTalent(rows: Derived[]): TalentEntry[] {
  return rows
    .filter(r => r.composite !== null)
    .sort((a, b) =>
      b.signal - a.signal ||
      (b.composite! - a.composite!) ||
      b.matchScore - a.matchScore,
    )
    .slice(0, 8)
    .map(r => ({
      roleId: r.roleId,
      roleName: r.roleName,
      candidateId: r.candidateId,
      name: r.name,
      role: r.role,
      status: r.status,
      matchScore: r.matchScore,
      composite: r.composite!,
      hireSignal: r.signal,
      recommendation: r.recommendation,
    }));
}

// ---------- attention feed ----------

function buildAttention(input: PortfolioInput, rows: Derived[]): AttentionItem[] {
  const items: AttentionItem[] = [];
  const byRole = new Map<string, Derived[]>();
  for (const r of rows) {
    const list = byRole.get(r.roleId) ?? [];
    list.push(r);
    byRole.set(r.roleId, list);
  }

  // Stale candidates — worst first, one item each (capped later).
  const stale = rows.filter(r => r.isStale).sort((a, b) => b.ageDays - a.ageDays);
  for (const r of stale) {
    items.push({
      kind: 'stale_candidate',
      severity: r.ageDays >= 21 ? 'high' : 'medium',
      roleId: r.roleId,
      roleName: r.roleName,
      candidateId: r.candidateId,
      candidateName: r.name,
      message: `${r.name} has sat in ${STAGE_LABEL[r.status as StageKey] ?? r.status} for ${r.ageDays} days — nudge or advance.`,
    });
  }

  // Offers at risk — drafted offer at the offer stage with low accept odds.
  for (const r of rows) {
    if (r.status !== 'offer' || !r.offer || r.winProbability === undefined) continue;
    if (r.winProbability < OFFER_RISK_PROB) {
      items.push({
        kind: 'offer_at_risk',
        severity: r.winProbability < 0.3 ? 'high' : 'medium',
        roleId: r.roleId,
        roleName: r.roleName,
        candidateId: r.candidateId,
        candidateName: r.name,
        message: `${r.name}'s offer is tracking ${Math.round(r.winProbability * 100)}% to accept — sweeten the package or line up a backup.`,
      });
    }
  }

  // Fast-track — a strong interviewed candidate still parked early.
  for (const r of rows) {
    if (r.signal >= FAST_TRACK_SIGNAL && (r.status === 'new' || r.status === 'outreach')) {
      items.push({
        kind: 'fast_track',
        severity: 'medium',
        roleId: r.roleId,
        roleName: r.roleName,
        candidateId: r.candidateId,
        candidateName: r.name,
        message: `${r.name} is a signal-${r.signal} candidate still in ${STAGE_LABEL[r.status as StageKey]} — fast-track before they're gone.`,
      });
    }
  }

  // Roles with a shortlist but no interviews.
  for (const role of input.roles) {
    const cands = byRole.get(role.id) ?? [];
    if (cands.length === 0) {
      items.push({
        kind: 'empty_role',
        severity: 'low',
        roleId: role.id,
        roleName: role.name,
        message: `${role.name} has no candidates yet — source a shortlist to get the loop moving.`,
      });
      continue;
    }
    const interviewed = cands.filter(c => c.composite !== null).length;
    const active = cands.filter(c => c.isActive).length;
    if (interviewed === 0 && active > 0) {
      items.push({
        kind: 'no_interviews',
        severity: 'medium',
        roleId: role.id,
        roleName: role.name,
        message: `${role.name} has ${active} active candidate${active === 1 ? '' : 's'} but no interviews scored — schedule first-round panels.`,
      });
    }
  }

  items.sort((a, b) => severityRank(a.severity) - severityRank(b.severity));
  return items.slice(0, 10);
}

// ---------- portfolio health ----------

function portfolioHealthScore(roleHealth: RoleHealth[]): number | null {
  const scored = roleHealth.filter(r => r.health !== null && r.candidates > 0);
  if (scored.length === 0) return null;
  // Weight each role by its active candidate count (roles with more in flight
  // matter more) with a floor of 1 so an all-passed role still counts a little.
  let wsum = 0;
  let acc = 0;
  for (const r of scored) {
    const w = Math.max(1, r.active);
    wsum += w;
    acc += w * (r.health as number);
  }
  return Math.round(acc / wsum);
}

// ---------- main ----------

export function buildPortfolio(input: PortfolioInput): PortfolioSummary {
  const rows = deriveCandidates(input);

  const totals = {
    roles: input.roles.length,
    candidates: rows.length,
    active: rows.filter(r => r.isActive).length,
    interviewed: rows.filter(r => r.composite !== null).length,
    offers: rows.filter(r => r.status === 'offer').length,
    passed: rows.filter(r => r.status === 'passed').length,
    staleCandidates: rows.filter(r => r.isStale).length,
  };

  const recommendationMix: Record<Recommendation, number> = {
    no_hire: 0, lean_no: 0, mixed: 0, lean_yes: 0, strong_hire: 0,
  };
  for (const r of rows) {
    if (r.recommendation) recommendationMix[r.recommendation] += 1;
  }

  const funnel = buildFunnel(rows);
  const compForecast = buildCompForecast(rows);
  const roleHealth = buildRoleHealth(input, rows);
  const talent = buildTalent(rows);
  const attention = buildAttention(input, rows);

  // Portfolio bottleneck — progression stage (excl. offer) holding the most active.
  const stageCount: Record<string, number> = {};
  for (const r of rows) {
    if (!r.isActive || r.status === 'offer') continue;
    stageCount[r.status] = (stageCount[r.status] ?? 0) + 1;
  }
  let bottleneck: StageKey | null = null;
  let bn = 1;
  for (const s of PROGRESSION) {
    if (s === 'offer') continue;
    const c = stageCount[s] ?? 0;
    if (c > bn) { bn = c; bottleneck = s; }
  }

  return {
    totals,
    funnel,
    compForecast,
    roleHealth,
    talent,
    attention,
    recommendationMix,
    portfolioHealth: portfolioHealthScore(roleHealth),
    bottleneck,
    generatedAt: input.now ?? Date.now(),
  };
}

// ---------- formatting sugar (UI) ----------

export function formatLPA(n: number): string {
  // Indian-numbering, LPA. Keeps one decimal only when meaningful.
  const rounded = Math.round(n * 10) / 10;
  const isInt = Math.abs(rounded - Math.round(rounded)) < 1e-9;
  const v = isInt ? Math.round(rounded) : rounded;
  return `₹${v.toLocaleString('en-IN')} LPA`;
}

export const HEALTH_HUE = (h: number | null): string => {
  if (h === null) return 'rgba(255,255,255,0.25)';
  if (h >= 75) return '#34d399';  // emerald
  if (h >= 55) return '#818cf8';  // indigo
  if (h >= 40) return '#facc15';  // amber
  return '#fb7185';               // rose
};

export const SEVERITY_TONE: Record<AttentionSeverity, string> = {
  high: 'rose',
  medium: 'amber',
  low: 'slate',
};
