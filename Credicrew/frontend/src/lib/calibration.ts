// Calibration Studio engine.
//
// Every interview in Credicrew so far assumed a *single* rater: one
// scorecard, one composite. Real hiring runs panels — and the #1 hidden
// source of unfair decisions is that interviewers aren't calibrated. Some
// rate everyone high (leniency), some low (severity), some give everyone a
// 3 (central-tendency / "flat"), and some simply disagree with the room
// (contrarian). A candidate's fate then depends on *who happened to
// interview them*, not how they did.
//
// This module models a panel — interviewers × candidates × rubric
// dimensions — and answers three questions no other surface asks:
//
//   1. Is each interviewer calibrated, or biased? (leniency / spread /
//      agreement-with-consensus)
//   2. How reliable is the panel as a whole? (consensus index + ICC(1))
//   3. Does removing systematic rater bias change who we'd hire?
//      (raw vs. de-biased ranking + rank shifts)
//
// All pure functions. Mirrored byte-for-byte in
// `backend/app/services/calibration.py` so a programmatic / agentic client
// gets identical verdicts. Storage (localStorage `credicrew:panels:v1`,
// keyed per role) lives at the bottom.

import { ratingHue } from '@/lib/decision';

// ---------- types ----------

export type Interviewer = {
  id: string;
  name: string;
  title?: string;       // e.g. "Eng Manager", "Staff Engineer"
};

export type PanelRating = {
  interviewerId: string;
  candidateId: number;
  dimKey: string;
  rating: number;       // 1..5
};

export type Panel = {
  roleId: string;
  interviewers: Interviewer[];
  ratings: PanelRating[];
};

export type RubricLite = { key: string; label: string; weight: number };

export type CandidateLite = {
  id: number;
  name: string;
  role?: string;
  location?: string;
};

export type RaterFlag = 'lenient' | 'severe' | 'flat' | 'contrarian';

export const RATER_FLAG_LABEL: Record<RaterFlag, string> = {
  lenient: 'Lenient',
  severe: 'Severe',
  flat: 'Flat / central',
  contrarian: 'Off-consensus',
};

export const RATER_FLAG_TONE: Record<RaterFlag, string> = {
  lenient: 'amber',
  severe: 'rose',
  flat: 'sky',
  contrarian: 'violet',
};

export type RaterBand = 'calibrated' | 'lenient' | 'severe';

export type RaterStat = {
  interviewerId: string;
  name: string;
  title?: string;
  leniency: number;             // mean (rating − consensus) over their cells
  spread: number;               // population stdev of their ratings
  consensusCorr: number | null; // Pearson r vs. per-cell consensus (null if degenerate)
  count: number;                // # cells rated
  band: RaterBand;
  flags: RaterFlag[];
};

export type CandFlag = 'single_rater' | 'high_disagreement' | 'thin';

export const CAND_FLAG_LABEL: Record<CandFlag, string> = {
  single_rater: 'Single-rater dim',
  high_disagreement: 'Panel split',
  thin: 'Thin coverage',
};

export const CAND_FLAG_TONE: Record<CandFlag, string> = {
  single_rater: 'slate',
  high_disagreement: 'rose',
  thin: 'amber',
};

export type CandidateScore = {
  candidateId: number;
  name: string;
  role?: string;
  location?: string;
  rawComposite: number | null;        // consensus composite, 0..100
  calibratedComposite: number | null; // after removing rater leniency
  delta: number;                      // calibrated − raw
  rawRank: number;                    // 1-indexed by rawComposite desc
  calibratedRank: number;             // 1-indexed by calibratedComposite desc
  rankShift: number;                  // rawRank − calibratedRank (+ = climbed)
  confidence: number;                 // ratedDims / totalDims [0,1]
  ratedDims: number;
  totalDims: number;
  consensus: number | null;           // mean agreement over candidate's multi-rated cells
  flags: CandFlag[];
};

export type CellRating = { interviewerId: string; name: string; rating: number };

export type CellInfo = {
  candidateId: number;
  candidateName: string;
  dimKey: string;
  dimLabel: string;
  ratings: CellRating[];
  mean: number;
  spread: number;       // population stdev across raters
  range: number;        // max − min
  n: number;
  agreement: number | null; // 1 − var/4, null if n<2
};

export type ICCBand = 'excellent' | 'good' | 'fair' | 'poor' | 'unreliable';

export const ICC_BAND_LABEL: Record<ICCBand, string> = {
  excellent: 'Excellent',
  good: 'Good',
  fair: 'Fair',
  poor: 'Poor',
  unreliable: 'Unreliable',
};

export type CalibrationVerdict =
  | 'calibrated'
  | 'minor_drift'
  | 'needs_calibration'
  | 'unreliable';

export const VERDICT_LABEL: Record<CalibrationVerdict, string> = {
  calibrated: 'Calibrated · panel agrees',
  minor_drift: 'Minor drift · one rater off',
  needs_calibration: 'Needs calibration · biased raters',
  unreliable: 'Unreliable · not enough overlap',
};

export const VERDICT_KICKER: Record<CalibrationVerdict, string> = {
  calibrated: 'Trust the ranking',
  minor_drift: 'Sanity-check the edge cases',
  needs_calibration: 'Recalibrate before deciding',
  unreliable: 'Add overlapping ratings',
};

export const VERDICT_HUE: Record<CalibrationVerdict, string> = {
  calibrated: '#34d399',
  minor_drift: '#fbbf24',
  needs_calibration: '#fb923c',
  unreliable: '#f43f5e',
};

export type CalibrationResult = {
  roleId: string;
  raters: RaterStat[];
  candidates: CandidateScore[];
  cells: CellInfo[];
  hotCells: CellInfo[];
  consensusIndex: number | null;   // overall agreement 0..1
  icc: number | null;              // raw intraclass correlation, one-way
  iccBand: ICCBand | null;
  iccCalibrated: number | null;    // ICC after removing rater leniency
  iccCalibratedBand: ICCBand | null;
  rankShiftCount: number;
  singleRaterCells: number;
  multiRatedCells: number;
  biasedRaters: number;
  grandMean: number;
  verdict: CalibrationVerdict;
  rubric: RubricLite[];
  suggestions: string[];
  notes: string[];
  generatedAt: number;
};

// ---------- math helpers ----------

const LENIENCY_THRESHOLD = 0.4;   // |dev from consensus| to flag a rater
const FLAT_SPREAD = 0.5;          // stdev below which a rater is "flat"
const CONTRARIAN_CORR = 0.2;      // consensus correlation below which = off-consensus
const HOT_RANGE = 2;              // min(max−min) for a disagreement hot-cell
const MAX_CELL_VAR = 4;           // population variance of {1,5} → normaliser

function mean(xs: number[]): number {
  if (xs.length === 0) return 0;
  let s = 0;
  for (const x of xs) s += x;
  return s / xs.length;
}

function pvar(xs: number[]): number {
  if (xs.length === 0) return 0;
  const m = mean(xs);
  let s = 0;
  for (const x of xs) s += (x - m) ** 2;
  return s / xs.length;
}

function pstd(xs: number[]): number {
  return Math.sqrt(pvar(xs));
}

function pearson(xs: number[], ys: number[]): number | null {
  const n = xs.length;
  if (n < 2 || ys.length !== n) return null;
  let sx = 0, sy = 0, sxx = 0, syy = 0, sxy = 0;
  for (let i = 0; i < n; i++) {
    sx += xs[i]; sy += ys[i];
    sxx += xs[i] * xs[i]; syy += ys[i] * ys[i];
    sxy += xs[i] * ys[i];
  }
  const cov = n * sxy - sx * sy;
  const vx = n * sxx - sx * sx;
  const vy = n * syy - sy * sy;
  if (vx <= 1e-9 || vy <= 1e-9) return null;
  return cov / Math.sqrt(vx * vy);
}

/** ICC(1) — one-way random-effects intraclass correlation, unbalanced.
 *  Targets are candidate×dimension cells; measurements are the raters who
 *  scored that cell. This handles unbalanced panels (different candidates
 *  seen by different interviewers) where a balanced targets×raters matrix
 *  doesn't exist. Returns null if there's no replication to measure. */
function iccOneWay(groups: number[][]): number | null {
  const valid = groups.filter(g => g.length >= 1);
  const k = valid.length;
  if (k < 2) return null;
  let N = 0;
  for (const g of valid) N += g.length;
  if (N <= k) return null; // no within-target replication

  const all: number[] = [];
  for (const g of valid) for (const x of g) all.push(x);
  const grand = mean(all);

  let ssb = 0, ssw = 0, sumNi2 = 0;
  for (const g of valid) {
    const gm = mean(g);
    ssb += g.length * (gm - grand) ** 2;
    for (const x of g) ssw += (x - gm) ** 2;
    sumNi2 += g.length * g.length;
  }
  const msb = ssb / (k - 1);
  const msw = ssw / (N - k);
  // Average group-size correction for unequal n_i.
  const k0 = (N - sumNi2 / N) / (k - 1);
  const denom = msb + (k0 - 1) * msw;
  if (Math.abs(denom) < 1e-9) return null;
  return (msb - msw) / denom;
}

function iccBandOf(icc: number | null): ICCBand | null {
  if (icc === null) return null;
  if (icc >= 0.75) return 'excellent';
  if (icc >= 0.6) return 'good';
  if (icc >= 0.4) return 'fair';
  if (icc >= 0.2) return 'poor';
  return 'unreliable';
}

function round(x: number, digits: number): number {
  const f = Math.pow(10, digits);
  return Math.round(x * f) / f;
}

const clamp = (x: number, lo: number, hi: number) =>
  Math.max(lo, Math.min(hi, x));

function cellKey(candidateId: number, dimKey: string): string {
  return `${candidateId}|${dimKey}`;
}

// ---------- main ----------

export function computeCalibration(
  panel: Panel,
  candidates: CandidateLite[],
  rubric: RubricLite[],
): CalibrationResult {
  const interviewers = panel.interviewers;
  const interviewerById = new Map(interviewers.map(i => [i.id, i]));
  const candById = new Map(candidates.map(c => [c.id, c]));
  const dimByKey = new Map(rubric.map(d => [d.key, d]));

  // Keep only ratings that point at a known interviewer, candidate, dim.
  const ratings = panel.ratings.filter(r =>
    interviewerById.has(r.interviewerId) &&
    candById.has(r.candidateId) &&
    dimByKey.has(r.dimKey) &&
    Number.isFinite(r.rating),
  );

  // Index by cell and by rater.
  const byCell = new Map<string, { interviewerId: string; rating: number }[]>();
  const byRater = new Map<string, { cellKey: string; rating: number }[]>();
  for (const r of ratings) {
    const ck = cellKey(r.candidateId, r.dimKey);
    if (!byCell.has(ck)) byCell.set(ck, []);
    byCell.get(ck)!.push({ interviewerId: r.interviewerId, rating: r.rating });
    if (!byRater.has(r.interviewerId)) byRater.set(r.interviewerId, []);
    byRater.get(r.interviewerId)!.push({ cellKey: ck, rating: r.rating });
  }

  // Raw consensus (cell mean) per cell.
  const cellMean = new Map<string, number>();
  for (const [ck, rs] of byCell) cellMean.set(ck, mean(rs.map(r => r.rating)));

  const grandMean = ratings.length > 0 ? mean(ratings.map(r => r.rating)) : 0;

  // ---- per-rater stats ----
  const raters: RaterStat[] = interviewers.map(iv => {
    const own = byRater.get(iv.id) ?? [];
    const ownRatings = own.map(o => o.rating);
    const consensusForOwn = own.map(o => cellMean.get(o.cellKey) ?? o.rating);
    const leniency = own.length > 0
      ? mean(own.map(o => o.rating - (cellMean.get(o.cellKey) ?? o.rating)))
      : 0;
    const spread = pstd(ownRatings);
    const consensusCorr = pearson(ownRatings, consensusForOwn);

    const flags: RaterFlag[] = [];
    if (leniency >= LENIENCY_THRESHOLD) flags.push('lenient');
    if (leniency <= -LENIENCY_THRESHOLD) flags.push('severe');
    if (own.length >= 3 && spread < FLAT_SPREAD) flags.push('flat');
    if (consensusCorr !== null && consensusCorr < CONTRARIAN_CORR) flags.push('contrarian');

    const band: RaterBand =
      leniency >= LENIENCY_THRESHOLD ? 'lenient'
        : leniency <= -LENIENCY_THRESHOLD ? 'severe'
          : 'calibrated';

    return {
      interviewerId: iv.id,
      name: iv.name,
      title: iv.title,
      leniency: round(leniency, 3),
      spread: round(spread, 3),
      consensusCorr: consensusCorr === null ? null : round(consensusCorr, 3),
      count: own.length,
      band,
      flags,
    };
  });

  const leniencyById = new Map(raters.map(r => [r.interviewerId, r.leniency]));
  const nameById = new Map(interviewers.map(i => [i.id, i.name]));

  // ---- cells (heatmap + hot-cell detection) ----
  const cells: CellInfo[] = [];
  for (const cand of candidates) {
    for (const dim of rubric) {
      const ck = cellKey(cand.id, dim.key);
      const rs = byCell.get(ck);
      if (!rs || rs.length === 0) continue;
      const vals = rs.map(r => r.rating);
      const v = pvar(vals);
      const n = vals.length;
      cells.push({
        candidateId: cand.id,
        candidateName: cand.name,
        dimKey: dim.key,
        dimLabel: dim.label,
        ratings: rs
          .map(r => ({
            interviewerId: r.interviewerId,
            name: nameById.get(r.interviewerId) ?? r.interviewerId,
            rating: r.rating,
          }))
          .sort((a, b) => a.name.localeCompare(b.name)),
        mean: round(mean(vals), 3),
        spread: round(pstd(vals), 3),
        range: Math.max(...vals) - Math.min(...vals),
        n,
        agreement: n >= 2 ? round(clamp(1 - v / MAX_CELL_VAR, 0, 1), 3) : null,
      });
    }
  }

  const multiRated = cells.filter(c => c.n >= 2);
  const singleRaterCells = cells.filter(c => c.n === 1).length;
  const multiRatedCells = multiRated.length;
  const consensusIndex = multiRated.length > 0
    ? round(mean(multiRated.map(c => c.agreement as number)), 3)
    : null;

  // ---- per-candidate raw + calibrated composite ----
  function composite(meanByDim: Map<string, number>): { value: number | null; rated: number } {
    let totalW = 0;
    let rated = 0;
    for (const dim of rubric) {
      if (meanByDim.has(dim.key)) { totalW += dim.weight; rated += 1; }
    }
    if (rated === 0 || totalW <= 0) return { value: null, rated: 0 };
    let acc = 0;
    for (const dim of rubric) {
      const m = meanByDim.get(dim.key);
      if (m === undefined) continue;
      const norm = (clamp(m, 1, 5) - 1) / 4;
      acc += norm * (dim.weight / totalW) * 100;
    }
    return { value: Math.round(acc), rated };
  }

  type Pre = {
    candidateId: number; name: string; role?: string; location?: string;
    rawComposite: number | null; calibratedComposite: number | null;
    confidence: number; ratedDims: number; totalDims: number;
    consensus: number | null; flags: CandFlag[];
  };

  const pre: Pre[] = candidates.map(cand => {
    const rawByDim = new Map<string, number>();
    const calByDim = new Map<string, number>();
    let hasSingle = false;
    const candCellAgreements: number[] = [];
    for (const dim of rubric) {
      const ck = cellKey(cand.id, dim.key);
      const rs = byCell.get(ck);
      if (!rs || rs.length === 0) continue;
      rawByDim.set(dim.key, mean(rs.map(r => r.rating)));
      // de-biased: subtract each rater's leniency, then average.
      const adj = rs.map(r => r.rating - (leniencyById.get(r.interviewerId) ?? 0));
      calByDim.set(dim.key, mean(adj));
      if (rs.length === 1) hasSingle = true;
      const c = cells.find(x => x.candidateId === cand.id && x.dimKey === dim.key);
      if (c && c.agreement !== null) candCellAgreements.push(c.agreement);
    }
    const raw = composite(rawByDim);
    const cal = composite(calByDim);
    const totalDims = rubric.length;
    const confidence = totalDims > 0 ? raw.rated / totalDims : 0;
    const consensus = candCellAgreements.length > 0
      ? round(mean(candCellAgreements), 3)
      : null;

    const flags: CandFlag[] = [];
    if (hasSingle) flags.push('single_rater');
    if (consensus !== null && consensus < 0.5) flags.push('high_disagreement');
    if (confidence < 0.5) flags.push('thin');

    return {
      candidateId: cand.id,
      name: cand.name,
      role: cand.role,
      location: cand.location,
      rawComposite: raw.value,
      calibratedComposite: cal.value,
      confidence: round(confidence, 3),
      ratedDims: raw.rated,
      totalDims,
      consensus,
      flags,
    };
  });

  // ---- ranks (raw + calibrated) ----
  function rankBy(key: 'rawComposite' | 'calibratedComposite'): Map<number, number> {
    const sorted = [...pre].sort((a, b) => {
      const av = a[key]; const bv = b[key];
      if (av === null && bv === null) return a.candidateId - b.candidateId;
      if (av === null) return 1;
      if (bv === null) return -1;
      if (bv !== av) return bv - av;
      return a.candidateId - b.candidateId;
    });
    const m = new Map<number, number>();
    sorted.forEach((p, i) => m.set(p.candidateId, i + 1));
    return m;
  }
  const rawRanks = rankBy('rawComposite');
  const calRanks = rankBy('calibratedComposite');

  const candidateScores: CandidateScore[] = pre.map(p => {
    const rawRank = rawRanks.get(p.candidateId) ?? 0;
    const calibratedRank = calRanks.get(p.candidateId) ?? 0;
    const delta = (p.calibratedComposite ?? 0) - (p.rawComposite ?? 0);
    return {
      candidateId: p.candidateId,
      name: p.name,
      role: p.role,
      location: p.location,
      rawComposite: p.rawComposite,
      calibratedComposite: p.calibratedComposite,
      delta: p.rawComposite === null || p.calibratedComposite === null ? 0 : delta,
      rawRank,
      calibratedRank,
      rankShift: rawRank - calibratedRank,
      confidence: p.confidence,
      ratedDims: p.ratedDims,
      totalDims: p.totalDims,
      consensus: p.consensus,
      flags: p.flags,
    };
  });
  candidateScores.sort((a, b) => a.calibratedRank - b.calibratedRank);

  const rankShiftCount = candidateScores.filter(c => c.rankShift !== 0).length;

  // ---- ICC over multi-rated cells (unbalanced one-way) ----
  const iccGroups = multiRated.map(c => c.ratings.map(r => r.rating));
  const iccRaw = iccOneWay(iccGroups);
  const icc = iccRaw === null ? null : round(iccRaw, 3);
  const iccBand = iccBandOf(icc);
  // The same reliability *after* removing each rater's leniency. If bias was
  // dragging reliability down, this is visibly higher — calibration recovers
  // the panel's power to tell candidates apart.
  const calGroups = multiRated.map(c =>
    c.ratings.map(r => r.rating - (leniencyById.get(r.interviewerId) ?? 0)),
  );
  const iccCalRaw = iccOneWay(calGroups);
  const iccCalibrated = iccCalRaw === null ? null : round(iccCalRaw, 3);
  const iccCalibratedBand = iccBandOf(iccCalibrated);

  // ---- hot cells ----
  const hotCells = multiRated
    .filter(c => c.range >= HOT_RANGE)
    .sort((a, b) => b.range - a.range || b.spread - a.spread)
    .slice(0, 8);

  const biasedRaters = raters.filter(
    r => r.flags.includes('lenient') || r.flags.includes('severe'),
  ).length;

  // ---- verdict ----
  let verdict: CalibrationVerdict;
  if (multiRatedCells === 0) {
    verdict = 'unreliable';
  } else if (
    (consensusIndex ?? 0) >= 0.8 &&
    biasedRaters === 0 &&
    (icc === null || icc >= 0.6)
  ) {
    verdict = 'calibrated';
  } else if ((consensusIndex ?? 0) >= 0.62 && biasedRaters <= 1) {
    verdict = 'minor_drift';
  } else if ((consensusIndex ?? 0) >= 0.45) {
    verdict = 'needs_calibration';
  } else {
    verdict = 'unreliable';
  }

  // ---- notes ----
  const notes: string[] = [];
  if (interviewers.length < 2) {
    notes.push('Add at least two interviewers per candidate so agreement can be measured.');
  }
  if (multiRatedCells === 0 && interviewers.length >= 2) {
    notes.push('No candidate-dimension was scored by more than one interviewer yet — overlap the panel to measure agreement.');
  }
  if (icc === null && multiRatedCells > 0) {
    notes.push('Not enough overlapping ratings for a reliability (ICC) estimate — overlap more raters per cell.');
  }
  const ratedCands = new Set(ratings.map(r => r.candidateId)).size;
  if (ratedCands > 0 && ratedCands < 3) {
    notes.push(`Only ${ratedCands} candidate${ratedCands === 1 ? '' : 's'} scored — reliability and rank shifts are directional until more are added.`);
  }

  // ---- suggestions ----
  const suggestions: string[] = [];
  for (const r of raters) {
    if (r.flags.includes('lenient')) {
      suggestions.push(`${r.name} rates +${r.leniency.toFixed(2)} above consensus on average — recalibrate or weight their scores down.`);
    } else if (r.flags.includes('severe')) {
      suggestions.push(`${r.name} rates ${r.leniency.toFixed(2)} below consensus on average — recalibrate or weight their scores up.`);
    }
  }
  for (const r of raters) {
    if (r.flags.includes('flat')) {
      suggestions.push(`${r.name}'s ratings barely vary (spread ${r.spread.toFixed(2)}) — push the middle apart with anchored rubric examples.`);
    }
  }
  for (const r of raters) {
    if (r.flags.includes('contrarian') && !r.flags.includes('lenient') && !r.flags.includes('severe')) {
      suggestions.push(`${r.name} correlates only ${(r.consensusCorr ?? 0).toFixed(2)} with the panel — pair-review before trusting solo verdicts.`);
    }
  }
  // Top-pick flip after calibration.
  const rawTop = [...candidateScores].sort((a, b) => a.rawRank - b.rawRank)[0];
  const calTop = [...candidateScores].sort((a, b) => a.calibratedRank - b.calibratedRank)[0];
  if (rawTop && calTop && rawTop.candidateId !== calTop.candidateId) {
    suggestions.push(`De-biasing flips the top pick from ${rawTop.name} to ${calTop.name} — the lead was a rater-bias artefact.`);
  } else if (rankShiftCount > 0) {
    suggestions.push(`Removing rater bias reorders ${rankShiftCount} candidate${rankShiftCount === 1 ? '' : 's'} — review the moved rows before deciding.`);
  }
  if (hotCells.length > 0) {
    const h = hotCells[0];
    const spread = h.ratings.map(x => x.rating).join('/');
    suggestions.push(`Biggest split: ${h.candidateName} on ${h.dimLabel} (${spread}) — discuss this dimension before locking a decision.`);
  }
  if (icc !== null && iccBand) {
    if (iccCalibrated !== null && iccCalibratedBand && iccCalibrated - icc >= 0.1) {
      suggestions.push(`Reliability is ICC ${icc.toFixed(2)} (${ICC_BAND_LABEL[iccBand].toLowerCase()}) raw, but ${iccCalibrated.toFixed(2)} (${ICC_BAND_LABEL[iccCalibratedBand].toLowerCase()}) once rater bias is removed — calibration recovers the panel's signal.`);
    } else {
      suggestions.push(`Panel reliability ICC = ${icc.toFixed(2)} (${ICC_BAND_LABEL[iccBand].toLowerCase()}) — ${icc >= 0.6 ? 'the ranking is trustworthy.' : 'individual scorecards carry real noise; lean on the panel mean.'}`);
    }
  }
  if (suggestions.length === 0 && multiRatedCells > 0) {
    suggestions.push('Panel is well-calibrated — interviewers agree and no systematic rater bias detected.');
  }

  return {
    roleId: panel.roleId,
    raters,
    candidates: candidateScores,
    cells,
    hotCells,
    consensusIndex,
    icc,
    iccBand,
    iccCalibrated,
    iccCalibratedBand,
    rankShiftCount,
    singleRaterCells,
    multiRatedCells,
    biasedRaters,
    grandMean: round(grandMean, 3),
    verdict,
    rubric,
    suggestions,
    notes,
    generatedAt: Date.now(),
  };
}

// ---------- markdown report ----------

export function buildCalibrationReport(
  roleName: string,
  result: CalibrationResult,
): string {
  const lines: string[] = [];
  lines.push(`# Interview calibration report — ${roleName}`);
  lines.push('');
  const date = new Date(result.generatedAt).toISOString().slice(0, 10);
  lines.push(`Generated ${date} · ${result.raters.length} interviewer${result.raters.length === 1 ? '' : 's'} · ${result.candidates.length} candidate${result.candidates.length === 1 ? '' : 's'}.`);
  lines.push('');
  lines.push(`**Verdict:** ${VERDICT_LABEL[result.verdict]}.`);
  const reli: string[] = [];
  if (result.consensusIndex !== null) reli.push(`consensus index ${(result.consensusIndex * 100).toFixed(0)}%`);
  if (result.icc !== null) {
    let s = `ICC ${result.icc.toFixed(2)}${result.iccBand ? ` (${ICC_BAND_LABEL[result.iccBand].toLowerCase()})` : ''}`;
    if (result.iccCalibrated !== null && result.iccCalibratedBand) {
      s += ` → ${result.iccCalibrated.toFixed(2)} (${ICC_BAND_LABEL[result.iccCalibratedBand].toLowerCase()}) de-biased`;
    }
    reli.push(s);
  }
  if (reli.length) {
    lines.push('');
    lines.push(`**Reliability:** ${reli.join(' · ')}.`);
  }
  lines.push('');

  // Interviewer calibration.
  lines.push('## Interviewer calibration');
  lines.push('');
  for (const r of result.raters) {
    const tag = r.flags.length ? r.flags.map(f => RATER_FLAG_LABEL[f]).join(', ') : 'Calibrated';
    const sign = r.leniency >= 0 ? '+' : '';
    const corr = r.consensusCorr === null ? '—' : r.consensusCorr.toFixed(2);
    lines.push(`- **${r.name}**${r.title ? ` (${r.title})` : ''}: leniency ${sign}${r.leniency.toFixed(2)} · spread ${r.spread.toFixed(2)} · consensus r ${corr} · ${tag}`);
  }
  lines.push('');

  // Ranking — raw vs calibrated.
  lines.push('## Ranking — raw vs. de-biased');
  lines.push('');
  for (const c of result.candidates) {
    const shift = c.rankShift === 0 ? '–' : c.rankShift > 0 ? `▲${c.rankShift}` : `▼${-c.rankShift}`;
    lines.push(`${c.calibratedRank}. **${c.name}** — calibrated ${c.calibratedComposite ?? '—'} (raw ${c.rawComposite ?? '—'}, Δ${c.delta >= 0 ? '+' : ''}${c.delta}) · was #${c.rawRank} ${shift}${c.flags.length ? ` · ${c.flags.map(f => CAND_FLAG_LABEL[f]).join(', ')}` : ''}`);
  }
  lines.push('');

  // Disagreement hot-cells.
  if (result.hotCells.length > 0) {
    lines.push('## Disagreement hot-cells (discuss these)');
    lines.push('');
    for (const h of result.hotCells) {
      const spread = h.ratings.map(x => `${x.name.split(' ')[0]} ${x.rating}`).join(' · ');
      lines.push(`- **${h.candidateName} — ${h.dimLabel}** (range ${h.range}): ${spread}`);
    }
    lines.push('');
  }

  // Actions.
  if (result.suggestions.length > 0) {
    lines.push('## Recommended actions');
    lines.push('');
    for (const s of result.suggestions) lines.push(`- ${s}`);
    lines.push('');
  }

  return lines.join('\n');
}

// ---------- cosmetics ----------

/** Agreement (0..1) → heatmap colour for the candidate × dim grid. */
export function agreementHue(agreement: number | null): string {
  if (agreement === null) return 'rgba(255,255,255,0.05)';
  // 0 (disagreement, rose) → 1 (consensus, emerald)
  const stops: [number, string][] = [
    [0.0, 'rgba(244,63,94,0.55)'],
    [0.4, 'rgba(251,113,133,0.45)'],
    [0.6, 'rgba(250,204,21,0.40)'],
    [0.8, 'rgba(129,140,248,0.42)'],
    [1.0, 'rgba(52,211,153,0.55)'],
  ];
  let chosen = stops[0][1];
  for (const [t, c] of stops) {
    if (agreement >= t) chosen = c;
  }
  return chosen;
}

/** Re-export so the studio cell inspector can colour individual ratings. */
export { ratingHue };

// ---------- localStorage ----------

const PANEL_KEY = 'credicrew:panels:v1';

type PanelStore = Record<string, Panel>;   // keyed by roleId

function readStore(): PanelStore {
  if (typeof window === 'undefined') return {};
  try {
    const raw = window.localStorage.getItem(PANEL_KEY);
    if (!raw) return {};
    const obj = JSON.parse(raw);
    return obj && typeof obj === 'object' ? obj : {};
  } catch {
    return {};
  }
}

function writeStore(s: PanelStore): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(PANEL_KEY, JSON.stringify(s));
  } catch {
    /* quota — ignore */
  }
}

export function getPanel(roleId: string): Panel | null {
  return readStore()[roleId] ?? null;
}

export function savePanel(panel: Panel): void {
  const s = readStore();
  s[panel.roleId] = panel;
  writeStore(s);
}

export function ensurePanel(roleId: string, seed: () => Panel): Panel {
  const existing = getPanel(roleId);
  if (existing && existing.interviewers.length > 0) return existing;
  const seeded = seed();
  savePanel(seeded);
  return seeded;
}

export function setRating(
  roleId: string,
  interviewerId: string,
  candidateId: number,
  dimKey: string,
  rating: number,
): Panel {
  const panel = getPanel(roleId) ?? { roleId, interviewers: [], ratings: [] };
  const next = panel.ratings.filter(
    r => !(r.interviewerId === interviewerId && r.candidateId === candidateId && r.dimKey === dimKey),
  );
  if (rating >= 1 && rating <= 5) {
    next.push({ interviewerId, candidateId, dimKey, rating });
  }
  const updated: Panel = { ...panel, ratings: next };
  savePanel(updated);
  return updated;
}

export function addInterviewer(roleId: string, iv: Interviewer): Panel {
  const panel = getPanel(roleId) ?? { roleId, interviewers: [], ratings: [] };
  const interviewers = panel.interviewers.filter(x => x.id !== iv.id);
  interviewers.push(iv);
  const updated: Panel = { ...panel, interviewers };
  savePanel(updated);
  return updated;
}

export function removeInterviewer(roleId: string, interviewerId: string): Panel {
  const panel = getPanel(roleId) ?? { roleId, interviewers: [], ratings: [] };
  const updated: Panel = {
    ...panel,
    interviewers: panel.interviewers.filter(x => x.id !== interviewerId),
    ratings: panel.ratings.filter(r => r.interviewerId !== interviewerId),
  };
  savePanel(updated);
  return updated;
}

export function mergeRatings(roleId: string, ratings: PanelRating[]): Panel {
  const panel = getPanel(roleId) ?? { roleId, interviewers: [], ratings: [] };
  const key = (r: PanelRating) => `${r.interviewerId}|${r.candidateId}|${r.dimKey}`;
  const map = new Map(panel.ratings.map(r => [key(r), r]));
  for (const r of ratings) {
    if (r.rating >= 1 && r.rating <= 5) map.set(key(r), r);
  }
  const updated: Panel = { ...panel, ratings: [...map.values()] };
  savePanel(updated);
  return updated;
}

export function makeInterviewerId(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return crypto.randomUUID();
  }
  return `iv_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
}
