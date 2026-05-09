// Decision Studio engine.
//
// The hiring loop now runs JD → match → outreach → interview → scorecard.
// What's missing is the *decision* — comparing candidates side-by-side
// across the rubric, surfacing calibration risks, and turning a stack of
// scorecards into a single hire/no-hire recommendation per candidate plus
// an overall ranking for the role.
//
// Pure functions. Mirrored on the backend in `app/services/decision.py`
// so a programmatic / agentic client gets byte-identical verdicts.

import type {
  InterviewRecord,
  RubricDimension,
  Recommendation,
  ScorecardSummary,
} from '@/lib/interview';
import { summarise } from '@/lib/interview';
import type { CandidateLike, MatchResult } from '@/lib/match';

// ---------- types ----------

export type CandidateInput = {
  candidateId: number;
  candidate: CandidateLike & { id: number };
  match: MatchResult;
  interview: InterviewRecord | null;
  status?: string;
};

export type DecisionFlag =
  | 'low_confidence'        // < 60% of dims rated
  | 'thin_data'             // < 35% of dims rated
  | 'rubric_drift'          // dim rated in some stages but not consistently
  | 'missing_key_dim'       // a top-3 weighted dim has no rating
  | 'high_variance'         // stdev across rated dims ≥ 1.5
  | 'no_interview'          // no interview record at all
  | 'unrated';              // interview exists but zero ratings

export const FLAG_LABEL: Record<DecisionFlag, string> = {
  low_confidence: 'Low confidence',
  thin_data: 'Thin data',
  rubric_drift: 'Rubric drift',
  missing_key_dim: 'Key dim unrated',
  high_variance: 'High variance',
  no_interview: 'No interview',
  unrated: 'Not yet rated',
};

export const FLAG_TONE: Record<DecisionFlag, string> = {
  low_confidence: 'amber',
  thin_data: 'rose',
  rubric_drift: 'amber',
  missing_key_dim: 'rose',
  high_variance: 'amber',
  no_interview: 'slate',
  unrated: 'slate',
};

export type CandidateVerdict = {
  candidateId: number;
  name: string;
  role?: string;
  location?: string;
  matchScore: number;
  composite: number | null;        // null if no interview / no ratings
  recommendation: Recommendation | null;
  confidence: number;              // [0,1] = ratedCount / totalCount
  hireSignal: number;              // calibrated: composite * sqrt(confidence)
  ratedCount: number;
  totalCount: number;
  variance: number;                // stdev across rated dim ratings (0 if <2)
  ratingsByDim: Record<string, number | null>;
  flags: DecisionFlag[];
  rank: number;                    // 1-indexed, by hireSignal desc
  topStrengths: string[];          // dim labels rated 4–5
  topConcerns: string[];           // dim labels rated 1–2
};

export type DimStat = {
  key: string;
  label: string;
  weight: number;                  // averaged across candidates' rubrics
  ratedFraction: number;           // [0,1] candidates with this dim rated
  mean: number | null;             // mean of rated values
  best: { candidateId: number; rating: number } | null;
  spread: number;                  // max - min across rated values (0 if <2)
};

export type RecommendationCounts = Record<Recommendation, number>;

export type DecisionSummary = {
  roleId: string;
  verdicts: CandidateVerdict[];    // sorted by rank asc
  rubric: RubricDimension[];       // canonical rubric (union; first occurrence wins)
  dimStats: DimStat[];
  counts: RecommendationCounts;    // tally over verdicts with composite ≠ null
  unratedCount: number;
  topHire: CandidateVerdict | null;
  nextRound: CandidateVerdict[];   // unrated / thin-data + decent match — worth interviewing
  generatedAt: number;
};

// ---------- math helpers ----------

function stdev(values: number[]): number {
  if (values.length < 2) return 0;
  const m = values.reduce((a, b) => a + b, 0) / values.length;
  const v = values.reduce((a, b) => a + (b - m) ** 2, 0) / values.length;
  return Math.sqrt(v);
}

// ---------- per-candidate verdict ----------

function computeVerdict(input: CandidateInput): Omit<CandidateVerdict, 'rank'> {
  const { candidate, match, interview } = input;

  // No interview yet → only match score is known.
  if (!interview) {
    return {
      candidateId: input.candidateId,
      name: candidate.name ?? `Candidate #${input.candidateId}`,
      role: candidate.role,
      location: candidate.location,
      matchScore: match.score,
      composite: null,
      recommendation: null,
      confidence: 0,
      hireSignal: 0,
      ratedCount: 0,
      totalCount: interview ? (interview as InterviewRecord).rubric.length : 0,
      variance: 0,
      ratingsByDim: {},
      flags: ['no_interview'],
      topStrengths: [],
      topConcerns: [],
    };
  }

  const summary: ScorecardSummary = summarise(interview);
  const ratingsByDim: Record<string, number | null> = {};

  // Latest rating per dim wins (mirrors interview.summarise math).
  for (const dim of interview.rubric) ratingsByDim[dim.key] = null;
  for (const stage of interview.stages) {
    for (const sc of stage.scores) {
      if (sc.rating !== null) ratingsByDim[sc.key] = sc.rating;
    }
  }

  const totalCount = interview.rubric.length;
  const ratedCount = summary.ratedCount;
  const confidence = totalCount > 0 ? ratedCount / totalCount : 0;
  const composite = ratedCount > 0 ? summary.composite : null;
  const recommendation = ratedCount > 0 ? summary.recommendation : null;

  // Hire signal calibrates composite by data completeness.
  // sqrt(confidence) is gentler than raw multiplication — a 60%-rated
  // 80-composite candidate keeps a ~62 signal, not 48.
  const hireSignal = composite !== null
    ? Math.round(composite * Math.sqrt(confidence))
    : 0;

  const ratedValues = Object.values(ratingsByDim).filter(
    (v): v is number => v !== null,
  );
  const variance = stdev(ratedValues);

  // ---- flags ----
  const flags: DecisionFlag[] = [];

  if (ratedCount === 0) {
    flags.push('unrated');
  } else {
    if (confidence < 0.35) flags.push('thin_data');
    else if (confidence < 0.6) flags.push('low_confidence');

    // Top-3 weighted dim with no rating → missing_key_dim.
    const topDims = [...interview.rubric]
      .sort((a, b) => b.weight - a.weight)
      .slice(0, 3);
    if (topDims.some(d => ratingsByDim[d.key] === null)) {
      flags.push('missing_key_dim');
    }

    if (variance >= 1.5) flags.push('high_variance');

    // Rubric drift: a dim rated in one stage but missing in another *done*
    // stage. Indicates the same dim was probed inconsistently.
    const stageRated: Record<string, Set<string>> = {};
    for (const st of interview.stages) {
      if (st.status !== 'done') continue;
      const set = new Set<string>();
      for (const sc of st.scores) if (sc.rating !== null) set.add(sc.key);
      stageRated[st.stage] = set;
    }
    const doneStages = Object.keys(stageRated);
    if (doneStages.length >= 2) {
      const everRated = new Set<string>();
      for (const set of Object.values(stageRated)) {
        for (const k of set) everRated.add(k);
      }
      // a dim is "drifted" if it's rated in some done stages but not all.
      const drifted = [...everRated].some(k =>
        doneStages.some(s => !stageRated[s].has(k))
        && doneStages.some(s => stageRated[s].has(k)),
      );
      if (drifted) flags.push('rubric_drift');
    }
  }

  // ---- strengths / concerns from rubric ratings ----
  const labelByKey: Record<string, string> = {};
  for (const d of interview.rubric) labelByKey[d.key] = d.label;
  const topStrengths: string[] = [];
  const topConcerns: string[] = [];
  for (const [k, r] of Object.entries(ratingsByDim)) {
    if (r === null) continue;
    if (r >= 4) topStrengths.push(labelByKey[k] ?? k);
    if (r <= 2) topConcerns.push(labelByKey[k] ?? k);
  }

  return {
    candidateId: input.candidateId,
    name: candidate.name ?? `Candidate #${input.candidateId}`,
    role: candidate.role,
    location: candidate.location,
    matchScore: match.score,
    composite,
    recommendation,
    confidence,
    hireSignal,
    ratedCount,
    totalCount,
    variance: Math.round(variance * 100) / 100,
    ratingsByDim,
    flags,
    topStrengths: topStrengths.slice(0, 3),
    topConcerns: topConcerns.slice(0, 3),
  };
}

// ---------- rubric union ----------

/** First-seen rubric across candidates. Different roles use the same
 *  rubric in practice; this just guards against the rare "rubric was
 *  rebuilt mid-process" case. */
function unionRubric(records: InterviewRecord[]): RubricDimension[] {
  const seen = new Map<string, RubricDimension>();
  for (const r of records) {
    for (const d of r.rubric) if (!seen.has(d.key)) seen.set(d.key, d);
  }
  return [...seen.values()];
}

// ---------- per-dim stats ----------

function computeDimStats(
  rubric: RubricDimension[],
  verdicts: Omit<CandidateVerdict, 'rank'>[],
): DimStat[] {
  return rubric.map(dim => {
    let sum = 0;
    let n = 0;
    let min = Infinity;
    let max = -Infinity;
    let best: { candidateId: number; rating: number } | null = null;

    let candidatesWithDim = 0;
    let candidatesRated = 0;
    for (const v of verdicts) {
      if (!(dim.key in v.ratingsByDim)) continue;
      candidatesWithDim += 1;
      const r = v.ratingsByDim[dim.key];
      if (r === null) continue;
      candidatesRated += 1;
      sum += r;
      n += 1;
      if (r < min) min = r;
      if (r > max) max = r;
      if (!best || r > best.rating) best = { candidateId: v.candidateId, rating: r };
    }

    return {
      key: dim.key,
      label: dim.label,
      weight: dim.weight,
      ratedFraction: candidatesWithDim > 0 ? candidatesRated / candidatesWithDim : 0,
      mean: n > 0 ? Math.round((sum / n) * 100) / 100 : null,
      best,
      spread: n >= 2 && max > min ? max - min : 0,
    };
  });
}

// ---------- main ----------

export function buildDecisionSummary(
  roleId: string,
  inputs: CandidateInput[],
): DecisionSummary {
  // 1. compute pre-rank verdicts
  const verdicts = inputs.map(computeVerdict);

  // 2. rank by hireSignal desc, then composite, then matchScore.
  // Unrated/no-interview candidates fall to the bottom but are still ranked.
  verdicts.sort((a, b) => {
    if (b.hireSignal !== a.hireSignal) return b.hireSignal - a.hireSignal;
    if ((b.composite ?? -1) !== (a.composite ?? -1))
      return (b.composite ?? -1) - (a.composite ?? -1);
    return b.matchScore - a.matchScore;
  });
  const ranked: CandidateVerdict[] = verdicts.map((v, i) => ({ ...v, rank: i + 1 }));

  // 3. canonical rubric (union; preserves first-seen weight)
  const records = inputs
    .map(i => i.interview)
    .filter((r): r is InterviewRecord => r !== null);
  const rubric = unionRubric(records);

  // 4. per-dim stats
  const dimStats = computeDimStats(rubric, verdicts);

  // 5. counts by recommendation tier (rated only)
  const counts: RecommendationCounts = {
    no_hire: 0, lean_no: 0, mixed: 0, lean_yes: 0, strong_hire: 0,
  };
  let unratedCount = 0;
  for (const v of ranked) {
    if (v.recommendation === null) unratedCount += 1;
    else counts[v.recommendation] += 1;
  }

  // 6. top hire = best rated candidate above mixed; null if no rated candidate
  const topHire = ranked.find(
    v => v.recommendation === 'strong_hire' || v.recommendation === 'lean_yes',
  ) ?? null;

  // 7. next-round candidates: thin or unrated, but match ≥ 60.
  const nextRound = ranked.filter(v =>
    (v.flags.includes('no_interview') ||
      v.flags.includes('unrated') ||
      v.flags.includes('thin_data'))
    && v.matchScore >= 60,
  ).slice(0, 5);

  return {
    roleId,
    verdicts: ranked,
    rubric,
    dimStats,
    counts,
    unratedCount,
    topHire,
    nextRound,
    generatedAt: Date.now(),
  };
}

// ---------- markdown debrief ----------

const REC_LABEL: Record<Recommendation, string> = {
  strong_hire: 'Strong hire',
  lean_yes: 'Lean yes',
  mixed: 'Mixed signal',
  lean_no: 'Lean no',
  no_hire: 'No hire',
};

export function buildDebrief(roleName: string, summary: DecisionSummary): string {
  const lines: string[] = [];
  lines.push(`# Hiring committee debrief — ${roleName}`);
  lines.push('');
  const date = new Date(summary.generatedAt).toISOString().slice(0, 10);
  lines.push(`Generated ${date} · ${summary.verdicts.length} candidate${summary.verdicts.length === 1 ? '' : 's'} reviewed.`);
  lines.push('');

  // Headline.
  if (summary.topHire) {
    lines.push(`**Recommended hire:** ${summary.topHire.name} — ${REC_LABEL[summary.topHire.recommendation!]} · composite ${summary.topHire.composite} · signal ${summary.topHire.hireSignal}.`);
  } else if (summary.verdicts.some(v => v.composite !== null)) {
    lines.push(`**No clear hire yet.** Best candidate is ${summary.verdicts[0].name} (signal ${summary.verdicts[0].hireSignal}); recommend more interview coverage before deciding.`);
  } else {
    lines.push(`**Pre-interview stage.** No scorecards have been submitted yet — schedule first-round panels for the next-round list below.`);
  }
  lines.push('');

  // Tally.
  const tallyParts: string[] = [];
  for (const tier of ['strong_hire', 'lean_yes', 'mixed', 'lean_no', 'no_hire'] as Recommendation[]) {
    if (summary.counts[tier] > 0) tallyParts.push(`${summary.counts[tier]} ${REC_LABEL[tier]}`);
  }
  if (summary.unratedCount > 0) tallyParts.push(`${summary.unratedCount} not yet rated`);
  if (tallyParts.length > 0) {
    lines.push(`**Tally:** ${tallyParts.join(' · ')}.`);
    lines.push('');
  }

  // Per-candidate.
  lines.push('## Candidates');
  lines.push('');
  for (const v of summary.verdicts) {
    lines.push(`### ${v.rank}. ${v.name}${v.role ? ` — ${v.role}` : ''}`);
    if (v.recommendation) {
      lines.push(`- **Verdict:** ${REC_LABEL[v.recommendation]} · composite ${v.composite} · signal ${v.hireSignal} · confidence ${(v.confidence * 100).toFixed(0)}% (${v.ratedCount}/${v.totalCount} dims rated)`);
    } else {
      lines.push(`- **Verdict:** Not rated yet · match ${v.matchScore}`);
    }
    if (v.topStrengths.length) lines.push(`- **Strengths:** ${v.topStrengths.join(', ')}.`);
    if (v.topConcerns.length) lines.push(`- **Concerns:** ${v.topConcerns.join(', ')}.`);
    if (v.flags.length) lines.push(`- **Flags:** ${v.flags.map(f => FLAG_LABEL[f]).join(' · ')}.`);
    lines.push('');
  }

  // Next round.
  if (summary.nextRound.length > 0) {
    lines.push('## Next-round candidates (worth interviewing)');
    lines.push('');
    for (const v of summary.nextRound) {
      lines.push(`- ${v.name}${v.role ? ` — ${v.role}` : ''} (match ${v.matchScore})`);
    }
    lines.push('');
  }

  // Per-dim signal.
  const ratedDims = summary.dimStats.filter(d => d.mean !== null);
  if (ratedDims.length > 0) {
    lines.push('## Rubric signal across pool');
    lines.push('');
    for (const d of ratedDims) {
      const meanStr = d.mean!.toFixed(1);
      lines.push(`- **${d.label}:** mean ${meanStr}/5 · ${(d.ratedFraction * 100).toFixed(0)}% coverage${d.spread > 0 ? ` · spread ${d.spread}` : ''}`);
    }
    lines.push('');
  }

  return lines.join('\n');
}

// ---------- recommendation styling helpers (used by UI) ----------

export const TIER_HUE: Record<Recommendation, string> = {
  strong_hire: '#34d399',  // emerald
  lean_yes: '#818cf8',     // indigo
  mixed: '#facc15',        // amber/yellow
  lean_no: '#fb7185',      // rose-400
  no_hire: '#f43f5e',      // rose-500
};

/** A 1–5 rating → color stop on the rubric heatmap. */
export function ratingHue(rating: number | null): string {
  if (rating === null) return 'rgba(255,255,255,0.04)';
  const stops: [number, string][] = [
    [1, 'rgba(244,63,94,0.55)'],   // rose
    [2, 'rgba(251,113,133,0.45)'], // pink
    [3, 'rgba(250,204,21,0.40)'],  // amber
    [4, 'rgba(129,140,248,0.45)'], // indigo
    [5, 'rgba(52,211,153,0.55)'],  // emerald
  ];
  const idx = Math.max(0, Math.min(4, Math.round(rating) - 1));
  return stops[idx][1];
}
