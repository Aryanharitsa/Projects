// Peer Parity — fairness audit for a proposed offer against the team's
// existing accepted offers ("peers"). Bridges Decision Studio (interview
// composite) and Offer Studio (base / equity / sign-on / bonus) by asking
// the question Decision and Offer alone never asked together:
//
//   *Is this offer consistent with how we paid peers at a similar bar?*
//
// The engine fits a 1-D linear regression `dim = a·composite + b` per
// compensation dimension, then z-scores the proposed offer against the
// residual stddev. Out-of-band z-scores and rank inversions against
// higher-composite peers become the verdict.
//
// Mirrored byte-for-byte in `backend/app/services/peer_parity.py` so the
// FastAPI surface and the browser engine produce identical verdicts.
//
// Pure functions; storage lives at the bottom (localStorage namespaced
// `credicrew:peers:v1`).

export type PeerOffer = {
  id: string;
  candidateName: string;
  roleName: string;
  seniority: string;
  location: string;
  /** Interview composite at hire — 0..100. null is allowed; treated as 50 (mid). */
  composite: number | null;
  base: number;            // LPA INR
  equityPct: number;
  signOn: number;
  targetBonusPct: number;
  acceptedAt: string;      // ISO yyyy-mm-dd
  source?: 'seed' | 'observed' | 'manual';
};

export type ParityDimKey = 'base' | 'equity' | 'sign_on' | 'target_bonus' | 'total_cash';

export type ParityDimension = {
  key: ParityDimKey;
  label: string;
  proposed: number;
  expected: number;
  /** expected - 1σ residual (clamped ≥ 0 for non-negative dims). */
  expectedLow: number;
  /** expected + 1σ residual. */
  expectedHigh: number;
  /** σ residual; 0 if regression is degenerate (n<3 or zero variance). */
  sigma: number;
  z: number;
  /** (proposed - expected) / max(1, |expected|) */
  pctDelta: number;
  status: 'in_band' | 'stretch' | 'severe';
};

export type ProposedSnapshot = {
  composite: number;
  base: number;
  equity: number;
  sign_on: number;
  target_bonus: number;
  total_cash: number;
};

export type ParityPeer = {
  peer: PeerOffer;
  /** Δ composite = peer.composite - proposed.composite (sign preserved). */
  deltaComposite: number;
  /** Δ base in LPA. */
  deltaBase: number;
  totalCash: number;
};

export type Inversion = {
  peer: PeerOffer;
  /** how much higher the peer scored at interview. */
  compositeGap: number;
  /** total comp gap as a fraction of the peer's total. */
  totalGapPct: number;
};

export type ScatterPoint = {
  id: string;
  name: string;
  composite: number;
  base: number;
  total: number;
  equity: number;
  /** true for the proposed offer marker — UI styles it differently. */
  isProposed: boolean;
};

export type Regression = {
  a: number;
  b: number;
  /** coefficient of determination. -1 = degenerate. */
  r2: number;
  /** σ residual on `base` (LPA). */
  sigma: number;
  n: number;
};

export type PeerParityVerdict = 'fair' | 'stretch' | 'drift' | 'inversion';

export type PeerParityResult = {
  verdict: PeerParityVerdict;
  /** max(|z|) across dims, rounded to 0.01. */
  driftScore: number;
  /** # of dims whose status ≠ in_band. */
  outOfBandCount: number;
  proposed: ProposedSnapshot;
  dims: ParityDimension[];
  inversions: Inversion[];
  nearestPeers: ParityPeer[];
  scatter: ScatterPoint[];
  regression: Regression;
  peerCount: number;
  suggestions: string[];
  notes: string[];
  /** Min and max composite seen across peers (for scatter axis). */
  range: { compositeMin: number; compositeMax: number; baseMin: number; baseMax: number };
};

// ---------- math ----------

const Z_STRETCH = 1.5;
const Z_SEVERE = 3.0;
/** If σ_residual would otherwise be tiny (very homogeneous team), floor it
 *  to 5% of the mean so we don't declare every offer "severe drift." */
const SIGMA_FLOOR_FRAC = 0.05;

function mean(xs: number[]): number {
  if (xs.length === 0) return 0;
  let s = 0;
  for (const x of xs) s += x;
  return s / xs.length;
}

function regress(xs: number[], ys: number[]): { a: number; b: number; r2: number; sigma: number } {
  const n = xs.length;
  if (n < 2) {
    const my = mean(ys);
    return { a: 0, b: my, r2: -1, sigma: 0 };
  }
  let sx = 0, sy = 0, sxx = 0, sxy = 0;
  for (let i = 0; i < n; i++) {
    sx += xs[i]; sy += ys[i];
    sxx += xs[i] * xs[i];
    sxy += xs[i] * ys[i];
  }
  const denom = n * sxx - sx * sx;
  // No composite variance — fall back to a flat predictor at the mean.
  if (Math.abs(denom) < 1e-9) {
    const my = sy / n;
    let resSq = 0;
    for (const y of ys) resSq += (y - my) ** 2;
    const sigma = n > 1 ? Math.sqrt(resSq / (n - 1)) : 0;
    return { a: 0, b: my, r2: 0, sigma };
  }
  const a = (n * sxy - sx * sy) / denom;
  const b = (sy - a * sx) / n;
  let resSq = 0;
  for (let i = 0; i < n; i++) {
    const e = ys[i] - (a * xs[i] + b);
    resSq += e * e;
  }
  const my = sy / n;
  let totSq = 0;
  for (const y of ys) totSq += (y - my) ** 2;
  const r2 = totSq > 1e-9 ? 1 - resSq / totSq : 0;
  const sigma = n > 1 ? Math.sqrt(resSq / (n - 1)) : 0;
  return { a, b, r2, sigma };
}

function applyFloor(sigma: number, ysMean: number): number {
  const floor = Math.abs(ysMean) * SIGMA_FLOOR_FRAC;
  return Math.max(sigma, floor);
}

function compositeOf(p: PeerOffer): number {
  return p.composite == null ? 50 : p.composite;
}

function totalCash(base: number, signOn: number, targetBonusPct: number): number {
  return base + signOn + base * (targetBonusPct / 100);
}

function zStatus(z: number): 'in_band' | 'stretch' | 'severe' {
  const az = Math.abs(z);
  if (az < Z_STRETCH) return 'in_band';
  if (az < Z_SEVERE) return 'stretch';
  return 'severe';
}

// ---------- public API ----------

export type CheckArgs = {
  composite: number | null;
  base: number;
  equityPct: number;
  signOn: number;
  targetBonusPct: number;
  candidateName?: string;
};

const DIM_LABELS: Record<ParityDimKey, string> = {
  base: 'Base salary',
  equity: 'Equity %',
  sign_on: 'Sign-on bonus',
  target_bonus: 'Target bonus %',
  total_cash: 'Total cash (yr 1)',
};

function buildDim(
  key: ParityDimKey,
  proposedComposite: number,
  proposedValue: number,
  composites: number[],
  values: number[],
): ParityDimension {
  const reg = regress(composites, values);
  const meanY = mean(values);
  const sigma = applyFloor(reg.sigma, meanY);
  const expected = reg.a * proposedComposite + reg.b;
  const z = sigma > 1e-9 ? (proposedValue - expected) / sigma : 0;
  const expectedLow = Math.max(0, expected - sigma);
  const expectedHigh = expected + sigma;
  const denom = Math.max(1, Math.abs(expected));
  return {
    key,
    label: DIM_LABELS[key],
    proposed: round(proposedValue, 4),
    expected: round(expected, 4),
    expectedLow: round(expectedLow, 4),
    expectedHigh: round(expectedHigh, 4),
    sigma: round(sigma, 4),
    z: round(z, 3),
    pctDelta: round((proposedValue - expected) / denom, 4),
    status: zStatus(z),
  };
}

function round(x: number, digits: number): number {
  const f = Math.pow(10, digits);
  return Math.round(x * f) / f;
}

export function computePeerParity(
  args: CheckArgs,
  peers: PeerOffer[],
): PeerParityResult {
  const proposedComposite = args.composite == null ? 50 : args.composite;
  const proposedTotal = totalCash(args.base, args.signOn, args.targetBonusPct);
  const proposed: ProposedSnapshot = {
    composite: proposedComposite,
    base: round(args.base, 2),
    equity: round(args.equityPct, 4),
    sign_on: round(args.signOn, 2),
    target_bonus: round(args.targetBonusPct, 2),
    total_cash: round(proposedTotal, 2),
  };

  const notes: string[] = [];
  if (peers.length === 0) {
    notes.push('No peer offers in the pool yet — publish accepted offers to start the audit.');
  } else if (peers.length < 3) {
    notes.push(`Only ${peers.length} peer${peers.length === 1 ? '' : 's'} in the pool — verdict is directional. Add more for a tighter audit.`);
  }

  const composites = peers.map(compositeOf);
  const baseRegression = regress(composites, peers.map(p => p.base));

  // 5 parity dimensions.
  const dimDefs: { key: ParityDimKey; proposed: number; values: number[] }[] = [
    { key: 'base', proposed: args.base, values: peers.map(p => p.base) },
    { key: 'equity', proposed: args.equityPct, values: peers.map(p => p.equityPct) },
    { key: 'sign_on', proposed: args.signOn, values: peers.map(p => p.signOn) },
    { key: 'target_bonus', proposed: args.targetBonusPct, values: peers.map(p => p.targetBonusPct) },
    { key: 'total_cash', proposed: proposedTotal, values: peers.map(p => totalCash(p.base, p.signOn, p.targetBonusPct)) },
  ];

  const dims: ParityDimension[] = peers.length >= 2
    ? dimDefs.map(d => buildDim(d.key, proposedComposite, d.proposed, composites, d.values))
    : dimDefs.map(d => ({
      key: d.key,
      label: DIM_LABELS[d.key],
      proposed: round(d.proposed, 4),
      expected: round(mean(d.values || [d.proposed]), 4),
      expectedLow: round(Math.max(0, mean(d.values || [d.proposed]) * 0.85), 4),
      expectedHigh: round(mean(d.values || [d.proposed]) * 1.15, 4),
      sigma: 0,
      z: 0,
      pctDelta: 0,
      status: 'in_band' as const,
    }));

  // Inversions: peers who scored *higher* on composite yet have *lower* total cash.
  const inversions: Inversion[] = [];
  for (const p of peers) {
    const pc = compositeOf(p);
    if (pc <= proposedComposite + 1) continue; // require ≥ 2 points higher to count
    const peerTotal = totalCash(p.base, p.signOn, p.targetBonusPct);
    if (proposedTotal > peerTotal * 1.02) {  // tolerate 2% noise
      inversions.push({
        peer: p,
        compositeGap: round(pc - proposedComposite, 1),
        totalGapPct: round((proposedTotal - peerTotal) / Math.max(1, peerTotal), 3),
      });
    }
  }
  inversions.sort((a, b) => b.totalGapPct - a.totalGapPct);

  // Nearest peers by composite gap.
  const nearest: ParityPeer[] = peers
    .map(p => ({
      peer: p,
      deltaComposite: round(compositeOf(p) - proposedComposite, 1),
      deltaBase: round(p.base - args.base, 2),
      totalCash: round(totalCash(p.base, p.signOn, p.targetBonusPct), 2),
    }))
    .sort((a, b) => Math.abs(a.deltaComposite) - Math.abs(b.deltaComposite))
    .slice(0, 5);

  // Scatter — peers + proposed marker.
  const scatter: ScatterPoint[] = [
    ...peers.map(p => ({
      id: p.id,
      name: p.candidateName,
      composite: compositeOf(p),
      base: p.base,
      total: round(totalCash(p.base, p.signOn, p.targetBonusPct), 2),
      equity: p.equityPct,
      isProposed: false,
    })),
    {
      id: '__proposed__',
      name: args.candidateName ?? 'Proposed',
      composite: proposedComposite,
      base: args.base,
      total: round(proposedTotal, 2),
      equity: args.equityPct,
      isProposed: true,
    },
  ];

  // Axis range over both peers and the proposed marker.
  const allComp = scatter.map(s => s.composite);
  const allBase = scatter.map(s => s.base);
  const range = peers.length === 0
    ? { compositeMin: Math.max(0, proposedComposite - 20), compositeMax: Math.min(100, proposedComposite + 20),
        baseMin: Math.max(0, args.base * 0.6), baseMax: args.base * 1.4 }
    : {
      compositeMin: Math.min(...allComp),
      compositeMax: Math.max(...allComp),
      baseMin: Math.min(...allBase),
      baseMax: Math.max(...allBase),
    };

  // Verdict.
  const outOfBandCount = dims.filter(d => d.status !== 'in_band').length;
  const driftScore = round(dims.reduce((m, d) => Math.max(m, Math.abs(d.z)), 0), 2);
  let verdict: PeerParityVerdict = 'fair';
  if (inversions.length >= 1) verdict = 'inversion';
  else if (dims.some(d => d.status === 'severe') || outOfBandCount >= 3) verdict = 'drift';
  else if (outOfBandCount >= 1) verdict = 'stretch';
  if (peers.length < 2) {
    verdict = 'fair';   // not enough data to assert anything
  }

  // Suggestions: smallest single-dim move to bring the worst dim back to z ≤ Z_STRETCH.
  const suggestions: string[] = [];
  if (peers.length >= 2) {
    const worst = [...dims].sort((a, b) => Math.abs(b.z) - Math.abs(a.z))[0];
    if (worst && Math.abs(worst.z) > Z_STRETCH) {
      const dir = worst.z > 0 ? 'down' : 'up';
      const target = worst.expected + Math.sign(worst.z) * Z_STRETCH * worst.sigma;
      const delta = target - worst.proposed;
      suggestions.push(
        `Bring ${worst.label.toLowerCase()} ${dir} to ${formatNum(target, worst.key)} ` +
        `(Δ ${formatDelta(delta, worst.key)}) to land inside the ±1.5σ band.`
      );
    }
    for (const inv of inversions.slice(0, 2)) {
      const peerTotal = totalCash(inv.peer.base, inv.peer.signOn, inv.peer.targetBonusPct);
      const targetTotal = peerTotal * 0.98;
      const drop = proposedTotal - targetTotal;
      suggestions.push(
        `Cut total cash by ~₹${round(drop, 1)} LPA to clear the inversion against ` +
        `${inv.peer.candidateName} (composite ${compositeOf(inv.peer)} vs ${proposedComposite}).`
      );
    }
    if (suggestions.length === 0) {
      suggestions.push('All dimensions are inside the ±1.5σ band — offer reads fair against your team.');
    }
  }

  return {
    verdict,
    driftScore,
    outOfBandCount,
    proposed,
    dims,
    inversions,
    nearestPeers: nearest,
    scatter,
    regression: {
      a: round(baseRegression.a, 4),
      b: round(baseRegression.b, 4),
      r2: round(baseRegression.r2, 3),
      sigma: round(applyFloor(baseRegression.sigma, mean(peers.map(p => p.base))), 3),
      n: peers.length,
    },
    peerCount: peers.length,
    suggestions,
    notes,
    range,
  };
}

function formatNum(v: number, key: ParityDimKey): string {
  if (key === 'equity') return `${v.toFixed(3)}%`;
  if (key === 'target_bonus') return `${Math.round(v)}%`;
  return `₹${Math.round(v)} LPA`;
}

function formatDelta(d: number, key: ParityDimKey): string {
  const s = d >= 0 ? '+' : '-';
  const a = Math.abs(d);
  if (key === 'equity') return `${s}${a.toFixed(3)} pp`;
  if (key === 'target_bonus') return `${s}${Math.round(a)} pp`;
  return `${s}₹${Math.round(a)} LPA`;
}

// ---------- verdict cosmetics ----------

export const VERDICT_HUE: Record<PeerParityVerdict, string> = {
  fair: '#34d399',
  stretch: '#fbbf24',
  drift: '#fb923c',
  inversion: '#f43f5e',
};

export const VERDICT_LABEL: Record<PeerParityVerdict, string> = {
  fair: 'Fair · within team band',
  stretch: 'Stretch · drifts on one dim',
  drift: 'Drift · multiple dims out-of-band',
  inversion: 'Inversion · leapfrogs higher-composite peer',
};

export const VERDICT_KICKER: Record<PeerParityVerdict, string> = {
  fair: 'In line with team',
  stretch: 'Acceptable stretch',
  drift: 'Reconsider before sending',
  inversion: 'Equity risk — fix before sending',
};

export const STATUS_HUE: Record<ParityDimension['status'], string> = {
  in_band: '#34d399',
  stretch: '#fbbf24',
  severe: '#f43f5e',
};

// ---------- localStorage ----------

const PEER_KEY = 'credicrew:peers:v1';

type PeerStore = Record<string, PeerOffer[]>;   // keyed by roleId

function readStore(): PeerStore {
  if (typeof window === 'undefined') return {};
  try {
    const raw = window.localStorage.getItem(PEER_KEY);
    if (!raw) return {};
    const obj = JSON.parse(raw);
    return obj && typeof obj === 'object' ? obj : {};
  } catch {
    return {};
  }
}

function writeStore(s: PeerStore): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(PEER_KEY, JSON.stringify(s));
  } catch {
    /* quota — ignore */
  }
}

export function listPeers(roleId: string): PeerOffer[] {
  return readStore()[roleId] ?? [];
}

export function savePeers(roleId: string, peers: PeerOffer[]): void {
  const s = readStore();
  s[roleId] = peers;
  writeStore(s);
}

export function addPeer(roleId: string, peer: PeerOffer): PeerOffer[] {
  const peers = listPeers(roleId);
  // de-dupe by id
  const filtered = peers.filter(p => p.id !== peer.id);
  filtered.push(peer);
  filtered.sort((a, b) => (b.acceptedAt || '').localeCompare(a.acceptedAt || ''));
  savePeers(roleId, filtered);
  return filtered;
}

export function removePeer(roleId: string, peerId: string): PeerOffer[] {
  const peers = listPeers(roleId).filter(p => p.id !== peerId);
  savePeers(roleId, peers);
  return peers;
}

export function ensureSeeded(roleId: string, seed: () => PeerOffer[]): PeerOffer[] {
  const existing = listPeers(roleId);
  if (existing.length > 0) return existing;
  const seeded = seed();
  savePeers(roleId, seeded);
  return seeded;
}

export function makePeerId(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return crypto.randomUUID();
  }
  return `peer_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
}
