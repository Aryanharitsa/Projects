// Crosswind — Cross-Role Candidate Router.
//
// Every other Credicrew surface is *role-scoped*: Discover ranks the global
// pool against ONE role, Forecast/Cadence/Decision are per-role. A recruiter
// running 10 reqs at once has a portfolio-level question that none of them
// answer: *given the candidates we already paid sourcing cost on, are they
// in the right roles?*
//
// Crosswind takes every active candidate currently sitting in some role's
// shortlist and re-scores them against **every other role's** plan, using
// the same `matchCandidate` engine the rest of Credicrew speaks. From that
// candidate × role match grid it derives four portfolio-level signals:
//
//   1. **Misplaced**  — candidate's current home role has a strictly
//      lower match score than their best alternative role by ≥
//      MISPLACE_THRESHOLD (default 10pt). Recommend rerouting.
//   2. **Talent magnet** — candidate is a `strong` match (≥80) in ≥ 3
//      distinct roles. Surface as portfolio-level scarce talent the
//      recruiter should make sure doesn't fall off.
//   3. **Lonely role** — role whose own shortlist has *no* `strong` match,
//      but at least one candidate sitting in another role's pool *would*
//      score `strong` here. The transplant opportunity.
//   4. **Portfolio lift** — Σ (best_role_score − current_role_score) over
//      all active candidates. The "if we routed optimally" headline number.
//
// The engine is pure-data, deterministic, and re-runs in the browser on
// every render — same physics ships on the backend via
// `app/services/crosswind.py` so an agentic client and the recruiter see
// byte-identical routing recommendations for the same fixture.

import type { CandidateLike, MatchResult } from '@/lib/match';
import { matchCandidate } from '@/lib/match';
import type { PipelineStatus, Role, ShortlistEntry } from '@/lib/roles';

export const STRONG_FLOOR = 80;
export const SOLID_FLOOR = 60;
export const MISPLACE_THRESHOLD = 10; // pts of upside required to recommend a move
export const MAGNET_ROLES = 3; // # of strong-matched roles to count as a magnet
export const TRANSPLANT_FLOOR = 70; // a transplant must score ≥ this in the lonely role

// Candidates with these statuses are excluded from routing
// (passed = rejected; offer = already committed).
const FROZEN_STATUSES: ReadonlySet<PipelineStatus> = new Set(['passed', 'offer']);

export type CrosswindCell = {
  candidateId: number;
  candidateName: string;
  roleId: string;
  roleName: string;
  /** Is this the role the candidate is currently sitting in? */
  isHome: boolean;
  /** Is the candidate currently on this role's shortlist (regardless of
   *  whether it's their primary home)? */
  isOnShortlist: boolean;
  status?: PipelineStatus;
  score: number;
  matched: string[];
  missing: string[];
  locationState: 'full' | 'partial' | 'none';
  seniorityMatch: boolean;
};

export type RoutingMove = {
  candidateId: number;
  candidateName: string;
  fromRoleId: string;
  fromRoleName: string;
  fromScore: number;
  toRoleId: string;
  toRoleName: string;
  toScore: number;
  delta: number;
  /** Human-readable "why" — diff between current and best fit. */
  why: string[];
  status?: PipelineStatus;
};

export type TalentMagnet = {
  candidateId: number;
  candidateName: string;
  homeRoleId?: string;
  homeRoleName?: string;
  hits: { roleId: string; roleName: string; score: number; isHome: boolean }[];
  topScore: number;
};

export type LonelyRole = {
  roleId: string;
  roleName: string;
  ownBest: number;
  ownMedian: number;
  candidateCount: number;
  transplants: {
    candidateId: number;
    candidateName: string;
    fromRoleId: string;
    fromRoleName: string;
    score: number;
    delta: number;
    status?: PipelineStatus;
  }[];
};

export type CrosswindSummary = {
  generatedAt: number;
  roleCount: number;
  candidateCount: number;
  cellCount: number;
  cells: CrosswindCell[];
  /** Score of where each candidate currently sits — sum over all active candidates. */
  currentTotal: number;
  /** Score if each candidate moved to their best-fit role — sum over all active candidates. */
  optimalTotal: number;
  /** optimalTotal − currentTotal. */
  liftTotal: number;
  /** Average delta per misplaced candidate. */
  liftAvgPerMove: number;
  moves: RoutingMove[];
  magnets: TalentMagnet[];
  lonely: LonelyRole[];
  perRole: {
    roleId: string;
    roleName: string;
    candidateCount: number;
    best: number;
    median: number;
    /** How many roles in the system have a higher fit-quality (best) for this role's shortlist. */
    crowdedRank?: number;
    /** True if the role would *gain* candidates if we routed optimally (i.e. some
     *  misplaced candidate's best role is this one). */
    isTarget: boolean;
    /** True if the role would *lose* candidates if we routed optimally. */
    isSource: boolean;
  }[];
  /** Histogram of score distribution across the matrix, 10-pt buckets 0..100. */
  scoreHistogram: number[];
};

type ActivePlacement = {
  candidateId: number;
  candidateName: string;
  candidate: CandidateLike;
  homeRoleId: string;
  status: PipelineStatus;
  /** Most recent stageChangedAt or addedAt timestamp — used to break ties
   *  when a candidate appears in multiple shortlists. */
  ts: number;
};

function median(xs: number[]): number {
  if (xs.length === 0) return 0;
  const sorted = [...xs].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 0
    ? Math.round((sorted[mid - 1] + sorted[mid]) / 2)
    : sorted[mid];
}

/** Walk the portfolio and emit one ActivePlacement per (candidate, home-role)
 *  pair. A candidate present in multiple shortlists is assigned to whichever
 *  one has the most recent stage transition — recruiters move people, not
 *  history. Frozen statuses (passed/offer) are excluded.
 */
function activePlacements(
  roles: Role[],
  byId: Map<number, CandidateLike & { id: number; name?: string }>,
): ActivePlacement[] {
  const seen = new Map<number, ActivePlacement>();
  for (const role of roles) {
    for (const e of role.shortlist) {
      if (FROZEN_STATUSES.has(e.status)) continue;
      const cand = byId.get(e.candidateId);
      if (!cand) continue;
      const ts = e.stageChangedAt ?? e.addedAt ?? 0;
      const prev = seen.get(e.candidateId);
      if (!prev || ts > prev.ts) {
        seen.set(e.candidateId, {
          candidateId: e.candidateId,
          candidateName: cand.name ?? `Candidate ${e.candidateId}`,
          candidate: cand,
          homeRoleId: role.id,
          status: e.status,
          ts,
        });
      }
    }
  }
  return Array.from(seen.values());
}

function diffWhy(home: MatchResult, target: MatchResult, fromRoleName: string, toRoleName: string): string[] {
  const lines: string[] = [];

  const skillsGained = target.matchedSkills.filter(s => !home.matchedSkills.includes(s));
  const skillsLost = home.matchedSkills.filter(s => !target.matchedSkills.includes(s));
  if (skillsGained.length || skillsLost.length) {
    const parts: string[] = [];
    if (skillsGained.length) parts.push(`+${skillsGained.length} matched skill${skillsGained.length === 1 ? '' : 's'} (${skillsGained.slice(0, 3).join(', ')})`);
    if (skillsLost.length) parts.push(`−${skillsLost.length} (${skillsLost.slice(0, 2).join(', ')})`);
    lines.push(parts.join(', '));
  }

  if (home.location.match !== target.location.match) {
    const arrow = `${home.location.match} → ${target.location.match}`;
    lines.push(`Location ${arrow}`);
  }

  if (home.seniority.match !== target.seniority.match) {
    const arrow = target.seniority.match ? 'mismatch → match' : 'match → mismatch';
    lines.push(`Seniority ${arrow}`);
  }

  if (lines.length === 0) {
    lines.push(`Higher composite fit for ${toRoleName} than ${fromRoleName}.`);
  }
  return lines;
}

export function analyzeCrosswind(
  roles: Role[],
  candidates: (CandidateLike & { id: number; name?: string })[],
): CrosswindSummary {
  const byId = new Map<number, CandidateLike & { id: number; name?: string }>();
  for (const c of candidates) byId.set(c.id, c);

  const placements = activePlacements(roles, byId);
  const cells: CrosswindCell[] = [];

  // Pre-compute shortlist membership for the cell view.
  const shortlistOf = new Map<string, Map<number, ShortlistEntry>>();
  for (const role of roles) {
    const m = new Map<number, ShortlistEntry>();
    for (const e of role.shortlist) m.set(e.candidateId, e);
    shortlistOf.set(role.id, m);
  }

  // Per-candidate × per-role match.
  const matchesByCandidate = new Map<number, Map<string, MatchResult>>();
  for (const p of placements) {
    const row = new Map<string, MatchResult>();
    for (const role of roles) {
      const m = matchCandidate(role.plan, p.candidate);
      row.set(role.id, m);
      const entry = shortlistOf.get(role.id)?.get(p.candidateId);
      cells.push({
        candidateId: p.candidateId,
        candidateName: p.candidateName,
        roleId: role.id,
        roleName: role.name,
        isHome: role.id === p.homeRoleId,
        isOnShortlist: !!entry,
        status: entry?.status,
        score: m.score,
        matched: m.matchedSkills,
        missing: m.missingSkills,
        locationState: m.location.match,
        seniorityMatch: m.seniority.match,
      });
    }
    matchesByCandidate.set(p.candidateId, row);
  }

  // Routing moves.
  const moves: RoutingMove[] = [];
  let currentTotal = 0;
  let optimalTotal = 0;
  for (const p of placements) {
    const row = matchesByCandidate.get(p.candidateId);
    if (!row) continue;
    const homeM = row.get(p.homeRoleId);
    if (!homeM) continue;
    currentTotal += homeM.score;

    let bestRoleId = p.homeRoleId;
    let bestM = homeM;
    for (const role of roles) {
      if (role.id === p.homeRoleId) continue;
      // Skip a target role if the candidate is *already* on its shortlist —
      // we want routing moves, not re-bumping the same record.
      if (shortlistOf.get(role.id)?.has(p.candidateId)) continue;
      const cand = row.get(role.id);
      if (!cand) continue;
      if (cand.score > bestM.score) {
        bestM = cand;
        bestRoleId = role.id;
      }
    }
    optimalTotal += bestM.score;

    const delta = bestM.score - homeM.score;
    if (delta >= MISPLACE_THRESHOLD && bestRoleId !== p.homeRoleId) {
      const fromRole = roles.find(r => r.id === p.homeRoleId)!;
      const toRole = roles.find(r => r.id === bestRoleId)!;
      moves.push({
        candidateId: p.candidateId,
        candidateName: p.candidateName,
        fromRoleId: fromRole.id,
        fromRoleName: fromRole.name,
        fromScore: homeM.score,
        toRoleId: toRole.id,
        toRoleName: toRole.name,
        toScore: bestM.score,
        delta,
        why: diffWhy(homeM, bestM, fromRole.name, toRole.name),
        status: p.status,
      });
    }
  }
  moves.sort((a, b) => b.delta - a.delta);

  // Talent magnets.
  const magnets: TalentMagnet[] = [];
  for (const p of placements) {
    const row = matchesByCandidate.get(p.candidateId);
    if (!row) continue;
    const hits = roles
      .map(r => ({
        roleId: r.id,
        roleName: r.name,
        score: row.get(r.id)?.score ?? 0,
        isHome: r.id === p.homeRoleId,
      }))
      .filter(h => h.score >= STRONG_FLOOR)
      .sort((a, b) => b.score - a.score);
    if (hits.length >= MAGNET_ROLES) {
      const home = roles.find(r => r.id === p.homeRoleId);
      magnets.push({
        candidateId: p.candidateId,
        candidateName: p.candidateName,
        homeRoleId: home?.id,
        homeRoleName: home?.name,
        hits,
        topScore: hits[0]?.score ?? 0,
      });
    }
  }
  magnets.sort((a, b) => b.hits.length - a.hits.length || b.topScore - a.topScore);

  // Lonely roles + transplant suggestions.
  const lonely: LonelyRole[] = [];
  for (const role of roles) {
    const ownScores: number[] = [];
    for (const e of role.shortlist) {
      if (FROZEN_STATUSES.has(e.status)) continue;
      const c = byId.get(e.candidateId);
      if (!c) continue;
      const m = matchCandidate(role.plan, c);
      ownScores.push(m.score);
    }
    const ownBest = ownScores.length ? Math.max(...ownScores) : 0;
    const ownMedian = median(ownScores);
    if (ownBest >= STRONG_FLOOR) continue; // Has a strong own match — not lonely.

    const transplants: LonelyRole['transplants'] = [];
    for (const p of placements) {
      if (p.homeRoleId === role.id) continue;
      // Already on this role's shortlist? Then no transplant needed.
      if (shortlistOf.get(role.id)?.has(p.candidateId)) continue;
      const row = matchesByCandidate.get(p.candidateId);
      if (!row) continue;
      const score = row.get(role.id)?.score ?? 0;
      if (score < TRANSPLANT_FLOOR) continue;
      const homeM = row.get(p.homeRoleId);
      const homeScore = homeM?.score ?? 0;
      const delta = score - homeScore;
      // Don't suggest a transplant that *hurts* the candidate's own fit
      // (lowering them by more than 5 pts).
      if (delta < -5) continue;
      const fromRole = roles.find(r => r.id === p.homeRoleId)!;
      transplants.push({
        candidateId: p.candidateId,
        candidateName: p.candidateName,
        fromRoleId: fromRole.id,
        fromRoleName: fromRole.name,
        score,
        delta,
        status: p.status,
      });
    }
    if (transplants.length === 0) continue;
    transplants.sort((a, b) => b.score - a.score);
    lonely.push({
      roleId: role.id,
      roleName: role.name,
      ownBest,
      ownMedian,
      candidateCount: ownScores.length,
      transplants: transplants.slice(0, 5),
    });
  }
  lonely.sort((a, b) => a.ownBest - b.ownBest);

  // Per-role rollup.
  const isTargetSet = new Set(moves.map(m => m.toRoleId));
  const isSourceSet = new Set(moves.map(m => m.fromRoleId));
  const perRole = roles.map(role => {
    const scores: number[] = [];
    for (const e of role.shortlist) {
      if (FROZEN_STATUSES.has(e.status)) continue;
      const c = byId.get(e.candidateId);
      if (!c) continue;
      scores.push(matchCandidate(role.plan, c).score);
    }
    const row: CrosswindSummary['perRole'][number] = {
      roleId: role.id,
      roleName: role.name,
      candidateCount: scores.length,
      best: scores.length ? Math.max(...scores) : 0,
      median: median(scores),
      isTarget: isTargetSet.has(role.id),
      isSource: isSourceSet.has(role.id),
    };
    return row;
  });
  // Crowded rank: ascending by best score → role with the strongest "own"
  // candidates gets rank 1, lonely roles get the highest rank.
  const ranked = [...perRole].sort((a, b) => b.best - a.best);
  for (let i = 0; i < ranked.length; i += 1) {
    const r = perRole.find(p => p.roleId === ranked[i].roleId);
    if (r) r.crowdedRank = i + 1;
  }

  // Score histogram.
  const histogram = new Array(10).fill(0);
  for (const cell of cells) {
    const bucket = Math.min(9, Math.floor(cell.score / 10));
    histogram[bucket] += 1;
  }

  const moveCount = moves.length;
  return {
    generatedAt: Date.now(),
    roleCount: roles.length,
    candidateCount: placements.length,
    cellCount: cells.length,
    cells,
    currentTotal,
    optimalTotal,
    liftTotal: optimalTotal - currentTotal,
    liftAvgPerMove: moveCount ? Math.round((optimalTotal - currentTotal) / moveCount) : 0,
    moves,
    magnets,
    lonely,
    perRole,
    scoreHistogram: histogram,
  };
}

export type CrosswindBand = 'idle' | 'modest' | 'meaningful' | 'urgent';

export function liftBand(lift: number, moveCount: number): CrosswindBand {
  if (moveCount === 0) return 'idle';
  if (lift >= 60 || moveCount >= 5) return 'urgent';
  if (lift >= 25 || moveCount >= 3) return 'meaningful';
  return 'modest';
}

export const BAND_HUE: Record<CrosswindBand, string> = {
  idle: '#9ca3af',
  modest: '#38bdf8',
  meaningful: '#a78bfa',
  urgent: '#fb7185',
};

export const BAND_LABEL: Record<CrosswindBand, string> = {
  idle: 'Steady',
  modest: 'Light',
  meaningful: 'Meaningful',
  urgent: 'Urgent',
};

/** Bucket a cell score into the visual heat tier used by the matrix. */
export function cellTier(score: number): 'rose' | 'amber' | 'sky' | 'emerald' | 'slate' {
  if (score >= 80) return 'emerald';
  if (score >= 70) return 'sky';
  if (score >= 55) return 'amber';
  if (score >= 35) return 'rose';
  return 'slate';
}

export const CELL_HEX: Record<ReturnType<typeof cellTier>, string> = {
  emerald: '#34d399',
  sky: '#38bdf8',
  amber: '#facc15',
  rose: '#fb7185',
  slate: '#475569',
};

/** Short human-readable explainer for the recommendations strip. */
export function recommendationLines(s: CrosswindSummary): string[] {
  const lines: string[] = [];
  const band = liftBand(s.liftTotal, s.moves.length);
  if (band === 'idle') {
    lines.push(
      `All ${s.candidateCount} active candidate${s.candidateCount === 1 ? ' is' : 's are'} already in their best-fit role. No reroutes recommended.`,
    );
  } else if (band === 'urgent') {
    lines.push(
      `**${s.moves.length} candidates are misplaced — total +${s.liftTotal} pts of fit-score on the table.** Highest-impact move: route ${s.moves[0].candidateName} from ${s.moves[0].fromRoleName} → ${s.moves[0].toRoleName} (+${s.moves[0].delta} pts).`,
    );
  } else {
    lines.push(
      `${s.moves.length} routing move${s.moves.length === 1 ? '' : 's'} available, total upside +${s.liftTotal} pts. Top move: ${s.moves[0].candidateName} → ${s.moves[0].toRoleName} (+${s.moves[0].delta}).`,
    );
  }
  if (s.magnets.length) {
    const top = s.magnets[0];
    lines.push(
      `**${s.magnets.length} talent magnet${s.magnets.length === 1 ? '' : 's'}** — candidates strong across ≥${MAGNET_ROLES} roles. ${top.candidateName} matches ${top.hits.length} roles at ≥${STRONG_FLOOR} — don't let them stall.`,
    );
  }
  if (s.lonely.length) {
    const top = s.lonely[0];
    const t = top.transplants[0];
    lines.push(
      `**${s.lonely.length} lonely role${s.lonely.length === 1 ? '' : 's'}** — no strong own match. ${top.roleName} (best ${top.ownBest}) could transplant ${t.candidateName} from ${t.fromRoleName} at ${t.score}.`,
    );
  }
  return lines;
}
