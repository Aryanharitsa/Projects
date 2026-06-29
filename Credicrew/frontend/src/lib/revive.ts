// Revive — Silver Medalist Reactivation Engine.
//
// Every active Credicrew surface looks at *who's in pipeline now*. Crosswind
// (Day 57) explicitly filters out `passed` and `offer` statuses — see
// `FROZEN_STATUSES` in `crosswind.ts` — because routing *active* candidates is
// a different problem from reviving rejected ones. As a result, the dormant
// pool of "we already paid sourcing cost on this person, we just passed for
// this one role" is **invisible to every cross-role surface**. That pool is
// the highest-ROI sourcing channel a recruiter has and Credicrew had no
// surface for it.
//
// Revive walks every role's shortlist, lifts out the `passed` entries, and
// re-scores each one against every *other currently open role's* plan with
// the same `matchCandidate` engine that powers Discover and Crosswind. From
// the resulting candidate × role grid it derives a single
// **reactivation score** per opportunity:
//
//     reactivation = matchScore × (RECENCY_FLOOR + (1 − RECENCY_FLOOR) × recency)
//
// where `recency = 2^(−daysDormant / RECENCY_HALF_LIFE_DAYS)` is an
// exponential decay (default 90-day half-life) and `RECENCY_FLOOR = 0.5` so
// even a year-old silver medalist never falls below half their fit weight —
// match quality dominates, recency tilts the queue.
//
// Other portfolio-level signals derived from the same grid:
//
//   * **Best per candidate** — every silver medalist's single best
//     alternative role (rolls up the noisy candidate × role grid into a
//     1-row-per-candidate queue).
//   * **Top picks per role** — for each currently open role, the silver
//     medalists who'd score highest if reactivated here.
//   * **Stale band** — entries older than STALE_DAYS get visually
//     deprioritized but still appear so a recruiter can clean up the queue.
//   * **Cost saved estimate** — each successful reactivation skips the
//     cost of re-sourcing a comparable candidate; we expose a config
//     constant the UI multiplies by the revivable count for the headline.
//
// All pure data, deterministic, browser-first. A backend mirror lives at
// `app/services/revive.py` so an agentic client (or `POST /revive/summary`)
// gets byte-identical opportunities for the same fixture.

import type { CandidateLike, MatchResult } from '@/lib/match';
import { matchCandidate } from '@/lib/match';
import type { Role } from '@/lib/roles';

// ---------- tunables ----------

export const RECENCY_HALF_LIFE_DAYS = 90;
export const RECENCY_FLOOR = 0.5;
/** A revival opportunity must score at least this on the alternative role. */
export const REVIVE_MATCH_FLOOR = 65;
/** And its reactivation composite must clear this to enter the "revivable" headline. */
export const REVIVE_COMPOSITE_FLOOR = 55;
/** Days at which a silver medalist is visually marked stale (still shown). */
export const STALE_DAYS = 180;
/** Estimated $ saved per reactivation vs sourcing a comparable candidate cold. */
export const SOURCING_COST_PER_HIRE_USD = 1500;
/** Open roles for the purposes of Revive — `offer` roles are still open
 *  (the candidate hasn't accepted yet), but a deleted role obviously isn't.
 *  We don't have a closed-role concept yet, so any role in the list is
 *  treated as open. */
const DAY_MS = 86_400_000;

// ---------- types ----------

export type SilverEntry = {
  candidateId: number;
  candidateName: string;
  candidate: CandidateLike;
  fromRoleId: string;
  fromRoleName: string;
  passedAtMs: number;
  daysDormant: number;
  /** Original match score of the candidate against the role they were passed from. */
  fromScore: number;
  note?: string;
};

export type ReviveOpportunity = {
  candidateId: number;
  candidateName: string;
  fromRoleId: string;
  fromRoleName: string;
  fromScore: number;
  toRoleId: string;
  toRoleName: string;
  toScore: number;
  /** toScore − fromScore. Positive ⇒ better fit elsewhere. */
  delta: number;
  daysDormant: number;
  recency: number;
  /** matchScore × (FLOOR + (1−FLOOR) × recency) → 0..100 */
  reactivationScore: number;
  match: MatchResult;
  /** Human-readable reasons rendered in the card. */
  why: string[];
  /** ≥ STALE_DAYS dormant. */
  stale: boolean;
};

export type CandidateBest = {
  silver: SilverEntry;
  /** Single best alternative role for this candidate; undefined if no role
   *  cleared REVIVE_MATCH_FLOOR. */
  best?: ReviveOpportunity;
  /** All alternative roles that cleared REVIVE_MATCH_FLOOR, sorted by
   *  reactivationScore desc. Excludes the from-role and any role the
   *  candidate is already on. */
  alternatives: ReviveOpportunity[];
};

export type RoleTopPicks = {
  roleId: string;
  roleName: string;
  /** Top reactivation candidates for this role, sorted by reactivationScore
   *  desc. Capped at PER_ROLE_LIMIT. */
  picks: ReviveOpportunity[];
  /** Best reactivation score available for this role. */
  bestScore: number;
};

export type ReviveSummary = {
  generatedAt: number;
  /** All silver medalists, de-duped by (candidateId, fromRoleId). */
  silver: SilverEntry[];
  /** All passing opportunities (≥ REVIVE_MATCH_FLOOR). */
  opportunities: ReviveOpportunity[];
  /** One row per silver candidate with their single best alternative. */
  perCandidate: CandidateBest[];
  /** One row per open role with its top revive picks. */
  perRole: RoleTopPicks[];
  /** Headline: how many opportunities cleared REVIVE_COMPOSITE_FLOOR. */
  revivableCount: number;
  /** Headline: estimated $ saved if every revivable opportunity converts to a hire. */
  estimatedCostSavedUsd: number;
  /** Headline: top single opportunity, if any. */
  topPick?: ReviveOpportunity;
  /** Histogram of reactivation scores across all opportunities, 10-pt buckets 0..100. */
  reactivationHistogram: number[];
};

// ---------- pure math ----------

export function daysBetween(ms: number, now: number): number {
  if (!ms || ms <= 0) return 0;
  return Math.max(0, Math.floor((now - ms) / DAY_MS));
}

export function recencyFactor(daysDormant: number): number {
  if (daysDormant <= 0) return 1;
  return Math.pow(2, -daysDormant / RECENCY_HALF_LIFE_DAYS);
}

export function reactivationScore(matchScore: number, recency: number): number {
  const r = Math.max(0, Math.min(1, recency));
  const tilt = RECENCY_FLOOR + (1 - RECENCY_FLOOR) * r;
  return Math.round(Math.max(0, Math.min(100, matchScore * tilt)));
}

// ---------- engine ----------

const PER_ROLE_LIMIT = 8;

function whyLines(
  silver: SilverEntry,
  match: MatchResult,
  toRoleName: string,
  delta: number,
  recency: number,
  daysDormant: number,
): string[] {
  const lines: string[] = [];

  if (delta >= 15) {
    lines.push(`+${delta} pts vs original role — strictly better fit.`);
  } else if (delta >= 5) {
    lines.push(`+${delta} pts vs ${silver.fromRoleName} — modest upside.`);
  } else if (delta >= -5) {
    lines.push(`Comparable fit to original role; routes a sunk-cost candidate.`);
  } else {
    lines.push(`Lower than original (${delta} pts) but still ≥ revive floor.`);
  }

  if (match.matchedSkills.length >= 3) {
    lines.push(
      `Matches ${match.matchedSkills.length} skills for ${toRoleName}: ${match.matchedSkills
        .slice(0, 4)
        .join(', ')}${match.matchedSkills.length > 4 ? '…' : ''}.`,
    );
  } else if (match.matchedSkills.length === 0 && match.missingSkills.length === 0) {
    lines.push(`Role JD specifies no required skills — soft match only.`);
  }

  if (match.location.match === 'full') {
    lines.push('Location aligns.');
  } else if (match.location.match === 'partial') {
    lines.push('Location is a partial (flex) match.');
  }

  if (recency >= 0.85) {
    lines.push(`Passed only ${daysDormant} day${daysDormant === 1 ? '' : 's'} ago — easy to re-open the thread.`);
  } else if (daysDormant >= STALE_DAYS) {
    lines.push(`Dormant ${daysDormant} days — confirm interest before re-engaging.`);
  }

  return lines;
}

export function analyzeRevive(
  roles: Role[],
  candidates: (CandidateLike & { id: number; name?: string })[],
  opts: { nowMs?: number } = {},
): ReviveSummary {
  const now = opts.nowMs ?? Date.now();

  const byId = new Map<number, CandidateLike & { id: number; name?: string }>();
  for (const c of candidates) byId.set(c.id, c);

  // Pre-compute every role's shortlist so we know which roles a candidate is
  // currently sitting in (any status). We use this to avoid suggesting roles
  // a candidate is already on.
  const onShortlistOf = new Map<number, Set<string>>();
  for (const role of roles) {
    for (const e of role.shortlist) {
      let set = onShortlistOf.get(e.candidateId);
      if (!set) {
        set = new Set();
        onShortlistOf.set(e.candidateId, set);
      }
      set.add(role.id);
    }
  }

  // Lift out every (candidate, role) pair where status === 'passed'.
  // De-dupe by (candidateId, fromRoleId) — duplicates shouldn't exist but
  // defend against malformed seeds.
  const silverByKey = new Map<string, SilverEntry>();
  for (const role of roles) {
    for (const e of role.shortlist) {
      if (e.status !== 'passed') continue;
      const cand = byId.get(e.candidateId);
      if (!cand) continue;
      const passedAt = e.stageChangedAt ?? e.addedAt ?? 0;
      const days = daysBetween(passedAt, now);

      // Re-run match against the from-role for the "fromScore" baseline.
      const homePlan = role.plan;
      const homeMatch = matchCandidate(homePlan, cand);

      const key = `${e.candidateId}::${role.id}`;
      silverByKey.set(key, {
        candidateId: e.candidateId,
        candidateName: cand.name ?? `Candidate ${e.candidateId}`,
        candidate: cand,
        fromRoleId: role.id,
        fromRoleName: role.name,
        passedAtMs: passedAt,
        daysDormant: days,
        fromScore: homeMatch.score,
        note: e.note,
      });
    }
  }
  const silver = Array.from(silverByKey.values());

  const opportunities: ReviveOpportunity[] = [];
  const reactivationHistogram = new Array(11).fill(0);

  for (const s of silver) {
    const occupied = onShortlistOf.get(s.candidateId) ?? new Set<string>();
    const recency = recencyFactor(s.daysDormant);
    const stale = s.daysDormant >= STALE_DAYS;

    for (const role of roles) {
      // Don't suggest the role they were passed from, or any role they're
      // already actively on (in any status). Either is noise.
      if (role.id === s.fromRoleId) continue;
      if (occupied.has(role.id)) continue;

      const m = matchCandidate(role.plan, s.candidate);
      if (m.score < REVIVE_MATCH_FLOOR) continue;

      const composite = reactivationScore(m.score, recency);
      const delta = m.score - s.fromScore;
      const why = whyLines(s, m, role.name, delta, recency, s.daysDormant);

      opportunities.push({
        candidateId: s.candidateId,
        candidateName: s.candidateName,
        fromRoleId: s.fromRoleId,
        fromRoleName: s.fromRoleName,
        fromScore: s.fromScore,
        toRoleId: role.id,
        toRoleName: role.name,
        toScore: m.score,
        delta,
        daysDormant: s.daysDormant,
        recency,
        reactivationScore: composite,
        match: m,
        why,
        stale,
      });

      const bucket = Math.min(10, Math.floor(composite / 10));
      reactivationHistogram[bucket] += 1;
    }
  }

  opportunities.sort((a, b) => b.reactivationScore - a.reactivationScore);

  // Per-candidate roll-up.
  const perCandidateMap = new Map<number, CandidateBest>();
  for (const s of silver) {
    if (!perCandidateMap.has(s.candidateId)) {
      perCandidateMap.set(s.candidateId, { silver: s, alternatives: [] });
    } else {
      // If the same candidate has multiple `passed` entries across roles,
      // prefer the most recently passed one as the canonical silver record.
      const prev = perCandidateMap.get(s.candidateId)!;
      if (s.passedAtMs > prev.silver.passedAtMs) {
        prev.silver = s;
      }
    }
  }
  for (const opp of opportunities) {
    const row = perCandidateMap.get(opp.candidateId);
    if (!row) continue;
    row.alternatives.push(opp);
    if (!row.best || opp.reactivationScore > row.best.reactivationScore) {
      row.best = opp;
    }
  }
  const perCandidate = Array.from(perCandidateMap.values()).sort((a, b) => {
    const av = a.best?.reactivationScore ?? -1;
    const bv = b.best?.reactivationScore ?? -1;
    return bv - av;
  });

  // Per-role roll-up.
  const perRoleMap = new Map<string, RoleTopPicks>();
  for (const role of roles) {
    perRoleMap.set(role.id, {
      roleId: role.id,
      roleName: role.name,
      picks: [],
      bestScore: 0,
    });
  }
  for (const opp of opportunities) {
    const row = perRoleMap.get(opp.toRoleId);
    if (!row) continue;
    row.picks.push(opp);
    if (opp.reactivationScore > row.bestScore) row.bestScore = opp.reactivationScore;
  }
  const perRole = Array.from(perRoleMap.values())
    .map(r => ({ ...r, picks: r.picks.slice(0, PER_ROLE_LIMIT) }))
    .filter(r => r.picks.length > 0)
    .sort((a, b) => b.bestScore - a.bestScore);

  const revivableCount = opportunities.filter(
    o => o.reactivationScore >= REVIVE_COMPOSITE_FLOOR,
  ).length;
  // Distinct silver candidates who have at least one revivable opportunity
  // — the cost-saved estimate is per-candidate, not per-opportunity.
  const distinctRevivableCandidates = new Set<number>();
  for (const o of opportunities) {
    if (o.reactivationScore >= REVIVE_COMPOSITE_FLOOR) {
      distinctRevivableCandidates.add(o.candidateId);
    }
  }
  const estimatedCostSavedUsd =
    distinctRevivableCandidates.size * SOURCING_COST_PER_HIRE_USD;

  return {
    generatedAt: now,
    silver,
    opportunities,
    perCandidate,
    perRole,
    revivableCount,
    estimatedCostSavedUsd,
    topPick: opportunities[0],
    reactivationHistogram,
  };
}

// ---------- visual helpers ----------

export type ReviveTier = 'hot' | 'warm' | 'tepid' | 'cold';

export function tierFor(score: number): ReviveTier {
  if (score >= 78) return 'hot';
  if (score >= 65) return 'warm';
  if (score >= REVIVE_COMPOSITE_FLOOR) return 'tepid';
  return 'cold';
}

export const TIER_LABEL: Record<ReviveTier, string> = {
  hot: 'Hot',
  warm: 'Warm',
  tepid: 'Tepid',
  cold: 'Cold',
};

export const TIER_HEX: Record<ReviveTier, string> = {
  hot: '#10b981', // emerald-500
  warm: '#0ea5e9', // sky-500
  tepid: '#f59e0b', // amber-500
  cold: '#475569', // slate-600
};

export function formatUsd(n: number): string {
  if (n >= 1_000_000) return `$${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 10_000) return `$${Math.round(n / 1000)}k`;
  if (n >= 1000) return `$${(n / 1000).toFixed(1)}k`;
  return `$${n}`;
}

export function formatDays(days: number): string {
  if (days <= 0) return 'today';
  if (days === 1) return '1 day';
  if (days < 60) return `${days} days`;
  const months = Math.round(days / 30);
  return `${months} month${months === 1 ? '' : 's'}`;
}

/** Headline band used for the hero stat. */
export function liftBand(revivable: number, silverCount: number): {
  label: string;
  hex: string;
  blurb: string;
} {
  if (silverCount === 0) {
    return {
      label: 'Empty pool',
      hex: '#64748b',
      blurb: 'Mark candidates as Passed in any role to start your silver pool.',
    };
  }
  const pct = (revivable / Math.max(1, silverCount)) * 100;
  if (pct >= 50)
    return {
      label: 'High-yield pool',
      hex: '#10b981',
      blurb: 'More than half of your silver medalists are revivable — work the queue.',
    };
  if (pct >= 25)
    return {
      label: 'Healthy pool',
      hex: '#0ea5e9',
      blurb: 'Solid reactivation opportunities — pick the hot ones first.',
    };
  if (pct >= 10)
    return {
      label: 'Niche pool',
      hex: '#f59e0b',
      blurb: 'A few good fits — most of the pool is dormant for a reason.',
    };
  return {
    label: 'Low-yield pool',
    hex: '#f43f5e',
    blurb: 'Most silver medalists don\'t fit the open roles — broaden roles or sourcing.',
  };
}

/** Markdown brief — used by the backend mirror and the "copy briefing" button. */
export function buildBrief(s: ReviveSummary): string {
  const lines: string[] = [];
  lines.push('# Revive — Silver Medalist Briefing');
  lines.push('');
  const band = liftBand(s.revivableCount, s.silver.length);
  lines.push(`**Pool:** ${s.silver.length} silver medalists across your roles.`);
  lines.push(
    `**Revivable:** ${s.revivableCount} opportunit${s.revivableCount === 1 ? 'y' : 'ies'} clear the ${REVIVE_COMPOSITE_FLOOR} reactivation floor.`,
  );
  lines.push(`**Estimated sourcing cost saved:** ${formatUsd(s.estimatedCostSavedUsd)}.`);
  lines.push(`**Pool quality:** ${band.label} — ${band.blurb}`);
  lines.push('');

  if (s.topPick) {
    const t = s.topPick;
    lines.push('## Top pick');
    lines.push(
      `- **${t.candidateName}** — ${t.fromRoleName} (${t.fromScore}) → ${t.toRoleName} (${t.toScore}). Reactivation ${t.reactivationScore}. Passed ${formatDays(t.daysDormant)} ago.`,
    );
    if (t.why.length) lines.push(`  - ${t.why[0]}`);
    lines.push('');
  }

  if (s.perRole.length) {
    lines.push('## By open role');
    for (const r of s.perRole.slice(0, 5)) {
      const top = r.picks[0];
      lines.push(
        `- **${r.roleName}** — best revive ${top.candidateName} @ ${top.reactivationScore} (from ${top.fromRoleName}, ${formatDays(top.daysDormant)} dormant).`,
      );
    }
  }
  return lines.join('\n');
}
