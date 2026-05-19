'use client';

import { useMemo } from 'react';
import {
  STATUS_HUE,
  VERDICT_HUE,
  VERDICT_KICKER,
  VERDICT_LABEL,
  type ParityDimension,
  type PeerParityResult,
  type ScatterPoint,
} from '@/lib/peer_parity';

type Props = {
  result: PeerParityResult;
  onOpenPool?: () => void;
  onPublish?: () => void;
  onClearInversion?: () => void;
  publishLabel?: string;
};

const SCATTER_W = 520;
const SCATTER_H = 260;
const PAD_L = 44;
const PAD_R = 16;
const PAD_T = 18;
const PAD_B = 28;

export default function PeerParityPanel({
  result, onOpenPool, onPublish, onClearInversion, publishLabel = 'Publish to peer pool',
}: Props) {
  const hue = VERDICT_HUE[result.verdict];

  // ---------- scatter coordinates ----------
  const scatter = useMemo(() => buildScatter(result), [result]);

  return (
    <section
      className="cc-parity-shell rounded-2xl border border-white/10 bg-white/[0.03] p-5"
      style={{
        ['--parity-hue' as string]: hue,
      }}
    >
      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 text-[10px] uppercase tracking-wider text-white/45">
            Peer parity
            <span className="cc-parity-dot" />
            <span className="text-white/35">
              {result.peerCount} peer{result.peerCount === 1 ? '' : 's'} · regression R²{' '}
              {result.regression.r2 < 0 ? '—' : result.regression.r2.toFixed(2)}
            </span>
          </div>
          <h2 className="mt-1 text-xl font-semibold">
            <span style={{ color: hue }}>{VERDICT_KICKER[result.verdict]}</span>
          </h2>
          <p className="mt-1 max-w-2xl text-sm text-white/55">{VERDICT_LABEL[result.verdict]}</p>
        </div>

        <div className="flex flex-wrap items-center gap-2 print:hidden">
          {onPublish && (
            <button
              onClick={onPublish}
              className="rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-xs text-white hover:bg-white/10"
              title="Snapshot this offer into the team peer pool"
            >
              {publishLabel}
            </button>
          )}
          {onOpenPool && (
            <button
              onClick={onOpenPool}
              className="rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-xs text-white hover:bg-white/10"
            >
              Manage peers
            </button>
          )}
        </div>
      </div>

      {/* Hero stats */}
      <div className="cc-parity-stats mt-5 grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Verdict" value={titleCase(result.verdict)} hue={hue} />
        <Stat
          label="Drift score"
          value={`${result.driftScore.toFixed(2)}σ`}
          detail="max |z| across dims"
          hue={hueForDrift(result.driftScore)}
        />
        <Stat
          label="Out of band"
          value={`${result.outOfBandCount} / ${result.dims.length}`}
          detail="|z| ≥ 1.5σ"
          hue={result.outOfBandCount === 0 ? '#34d399' : result.outOfBandCount >= 3 ? '#fb923c' : '#fbbf24'}
        />
        <Stat
          label="Inversions"
          value={String(result.inversions.length)}
          detail="peers leapfrogged"
          hue={result.inversions.length === 0 ? '#34d399' : '#f43f5e'}
        />
      </div>

      {/* Scatter + suggestions */}
      <div className="mt-6 grid gap-5 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div className="cc-parity-scatter rounded-xl border border-white/10 bg-black/30 p-4">
          <div className="flex items-baseline justify-between">
            <div className="text-[10px] uppercase tracking-wider text-white/45">
              Composite vs base · with regression line
            </div>
            <div className="text-[10px] text-white/40">
              y = {result.regression.a.toFixed(2)}·x + {result.regression.b.toFixed(1)} · σ {result.regression.sigma.toFixed(1)}
            </div>
          </div>
          <ScatterChart points={scatter.points} regression={scatter.regression} band={scatter.band} hue={hue} />
          <div className="mt-2 flex flex-wrap items-center gap-3 text-[10px] text-white/45">
            <Legend dotHue="#94a3b8" label="Peer offer" />
            <Legend dotHue={hue} label="Proposed offer" isStar />
            <Legend dotHue="#a78bfa" label="Expected ±1σ band" isBand />
          </div>
        </div>

        <div className="space-y-3">
          {result.inversions.length > 0 && (
            <div className="cc-parity-card cc-parity-inv rounded-xl border border-rose-400/30 bg-rose-400/[0.06] p-3">
              <div className="flex items-center justify-between gap-2">
                <div className="text-[10px] uppercase tracking-wider text-rose-200/80">
                  Inversion alert
                </div>
                {onClearInversion && (
                  <button
                    onClick={onClearInversion}
                    className="rounded-md border border-rose-400/30 bg-rose-400/10 px-2 py-0.5 text-[10px] text-rose-100 hover:bg-rose-400/20"
                  >
                    Snap to peer band
                  </button>
                )}
              </div>
              <ul className="mt-1.5 space-y-1.5 text-[11px] text-rose-100/85">
                {result.inversions.slice(0, 3).map(inv => (
                  <li key={inv.peer.id}>
                    <span className="font-semibold">{inv.peer.candidateName}</span>{' '}
                    scored composite <span className="font-mono">{inv.peer.composite}</span>{' '}
                    (+{inv.compositeGap}) yet total {Math.round(inv.totalGapPct * 100)}% lower than the proposal.
                  </li>
                ))}
              </ul>
            </div>
          )}

          <div className="cc-parity-card rounded-xl border border-white/10 bg-white/[0.03] p-3">
            <div className="text-[10px] uppercase tracking-wider text-white/45">Suggestions</div>
            <ul className="mt-1.5 space-y-1.5 text-[11px] text-white/75">
              {result.suggestions.length === 0 && (
                <li className="text-white/40">No corrective moves needed.</li>
              )}
              {result.suggestions.map((s, i) => (
                <li key={i} className="flex gap-1.5">
                  <span style={{ color: hue }}>→</span>
                  <span>{s}</span>
                </li>
              ))}
            </ul>
          </div>

          {result.notes.length > 0 && (
            <div className="rounded-xl border border-dashed border-amber-400/30 bg-amber-400/5 p-3 text-[11px] text-amber-200/85">
              {result.notes.join(' ')}
            </div>
          )}
        </div>
      </div>

      {/* Per-dim parity bars */}
      <div className="mt-6">
        <div className="text-[10px] uppercase tracking-wider text-white/45">
          Per-dimension parity vs team band at composite {result.proposed.composite}
        </div>
        <div className="cc-parity-dims mt-3 grid gap-2.5">
          {result.dims.map(d => (
            <DimBar key={d.key} dim={d} hue={STATUS_HUE[d.status]} />
          ))}
        </div>
      </div>

      {/* Nearest peers */}
      {result.nearestPeers.length > 0 && (
        <div className="mt-6">
          <div className="text-[10px] uppercase tracking-wider text-white/45">
            Nearest peers by composite
          </div>
          <div className="mt-2 overflow-x-auto rounded-xl border border-white/10 bg-black/20">
            <table className="w-full text-[11px]">
              <thead className="text-left text-white/45">
                <tr>
                  <th className="px-3 py-2 font-medium">Peer</th>
                  <th className="px-3 py-2 font-medium">Composite</th>
                  <th className="px-3 py-2 font-medium">Base</th>
                  <th className="px-3 py-2 font-medium">Δ vs proposed</th>
                  <th className="px-3 py-2 font-medium">Total (yr 1)</th>
                  <th className="px-3 py-2 font-medium">Equity</th>
                </tr>
              </thead>
              <tbody>
                {result.nearestPeers.map(np => {
                  const dc = np.deltaComposite;
                  const db = np.deltaBase;
                  return (
                    <tr key={np.peer.id} className="border-t border-white/[0.06]">
                      <td className="px-3 py-2">
                        <div className="font-medium text-white">{np.peer.candidateName}</div>
                        <div className="text-[10px] text-white/40">{np.peer.seniority} · {np.peer.location}</div>
                      </td>
                      <td className="px-3 py-2 font-mono">{np.peer.composite ?? '—'}</td>
                      <td className="px-3 py-2 font-mono">₹{np.peer.base} LPA</td>
                      <td className="px-3 py-2 font-mono">
                        <span className={dc > 0 ? 'text-emerald-300' : dc < 0 ? 'text-rose-300' : 'text-white/55'}>
                          {dc > 0 ? '+' : ''}{dc} composite
                        </span>
                        <span className="ml-2 text-white/40">·</span>
                        <span className={`ml-2 ${db > 0 ? 'text-emerald-300' : db < 0 ? 'text-rose-300' : 'text-white/55'}`}>
                          {db > 0 ? '+' : ''}₹{db} LPA
                        </span>
                      </td>
                      <td className="px-3 py-2 font-mono">₹{np.totalCash} LPA</td>
                      <td className="px-3 py-2 font-mono">{np.peer.equityPct.toFixed(3)}%</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </section>
  );
}

function titleCase(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

function hueForDrift(d: number): string {
  if (d < 1.5) return '#34d399';
  if (d < 3) return '#fbbf24';
  return '#fb923c';
}

function Stat({ label, value, detail, hue }: { label: string; value: string; detail?: string; hue: string }) {
  return (
    <div
      className="cc-parity-stat rounded-xl border p-3"
      style={{ borderColor: `${hue}33`, background: `${hue}0d` }}
    >
      <div className="text-[10px] uppercase tracking-wider text-white/55">{label}</div>
      <div className="mt-1 truncate text-lg font-semibold" style={{ color: hue }}>{value}</div>
      {detail && <div className="mt-0.5 truncate text-[10px] text-white/45">{detail}</div>}
    </div>
  );
}

function DimBar({ dim, hue }: { dim: ParityDimension; hue: string }) {
  // Render the proposed offer marker against the [expectedLow, expectedHigh]
  // band on a domain that always contains both peer expected center AND the
  // proposed value, padded for headroom.
  const span = [
    dim.expectedLow,
    dim.expectedHigh,
    dim.expected,
    dim.proposed,
  ];
  let lo = Math.min(...span);
  let hi = Math.max(...span);
  if (hi - lo < 1e-6) { lo -= 1; hi += 1; }
  const pad = (hi - lo) * 0.12;
  lo -= pad;
  hi += pad;
  if (lo < 0 && dim.key !== 'base') lo = 0;
  const at = (v: number) => `${Math.max(0, Math.min(100, ((v - lo) / (hi - lo)) * 100))}%`;

  const fmt = (v: number) => {
    if (dim.key === 'equity') return `${v.toFixed(3)}%`;
    if (dim.key === 'target_bonus') return `${v.toFixed(0)}%`;
    return `₹${Math.round(v)}`;
  };
  const zLabel = `z = ${dim.z >= 0 ? '+' : ''}${dim.z.toFixed(2)}`;

  return (
    <div className="cc-parity-dim rounded-lg border border-white/10 bg-white/[0.025] p-3">
      <div className="flex items-baseline justify-between text-[11px]">
        <div className="text-white/85">{dim.label}</div>
        <div className="flex items-center gap-2">
          <span className="font-mono text-white/65">
            {fmt(dim.proposed)} <span className="text-white/35">vs</span> {fmt(dim.expected)}
          </span>
          <span
            className="rounded px-1.5 py-0.5 text-[10px] font-medium"
            style={{ background: `${hue}1a`, color: hue, border: `1px solid ${hue}40` }}
          >
            {zLabel}
          </span>
        </div>
      </div>
      <div className="cc-parity-track relative mt-2 h-2.5 rounded-full bg-white/[0.06]">
        {/* expected band */}
        <div
          className="absolute top-0 h-full rounded-full"
          style={{
            left: at(dim.expectedLow),
            width: `calc(${at(dim.expectedHigh)} - ${at(dim.expectedLow)})`,
            background: 'linear-gradient(90deg, rgba(167,139,250,0.22), rgba(96,165,250,0.22))',
          }}
        />
        {/* expected center tick */}
        <div
          className="absolute top-1/2 h-3 w-px -translate-y-1/2"
          style={{ left: at(dim.expected), background: 'rgba(255,255,255,0.45)' }}
        />
        {/* proposed marker */}
        <div
          className="cc-parity-marker absolute top-1/2 h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full"
          style={{
            left: at(dim.proposed),
            background: hue,
            boxShadow: `0 0 0 2px rgba(10,10,16,0.95), 0 0 8px ${hue}88`,
          }}
        />
      </div>
      <div className="mt-1 flex justify-between text-[9px] text-white/35">
        <span>P25-ish</span>
        <span>expected at composite {dim.proposed === dim.expected ? '—' : ''}</span>
        <span>P75-ish</span>
      </div>
    </div>
  );
}

function Legend({ dotHue, label, isStar, isBand }: { dotHue: string; label: string; isStar?: boolean; isBand?: boolean }) {
  if (isBand) {
    return (
      <span className="inline-flex items-center gap-1.5">
        <span
          className="inline-block h-2 w-6 rounded"
          style={{ background: 'linear-gradient(90deg, rgba(167,139,250,0.30), rgba(96,165,250,0.30))' }}
        />
        {label}
      </span>
    );
  }
  if (isStar) {
    return (
      <span className="inline-flex items-center gap-1.5">
        <svg width="14" height="14" viewBox="-7 -7 14 14">
          <Star r={6} fill={dotHue} />
        </svg>
        {label}
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className="inline-block h-2 w-2 rounded-full" style={{ background: dotHue }} />
      {label}
    </span>
  );
}

function Star({ r, fill }: { r: number; fill: string }) {
  // 5-point star
  const pts: string[] = [];
  for (let i = 0; i < 10; i++) {
    const angle = (Math.PI / 5) * i - Math.PI / 2;
    const rr = i % 2 === 0 ? r : r * 0.45;
    pts.push(`${(Math.cos(angle) * rr).toFixed(2)},${(Math.sin(angle) * rr).toFixed(2)}`);
  }
  return <polygon points={pts.join(' ')} fill={fill} stroke="#0a0a10" strokeWidth={0.8} />;
}

// ---------- scatter helpers ----------

type ScatterRender = {
  points: Array<{ x: number; y: number; pt: ScatterPoint }>;
  regression: { x1: number; y1: number; x2: number; y2: number } | null;
  band: { x1: number; y1Lo: number; y1Hi: number; x2: number; y2Lo: number; y2Hi: number } | null;
};

function buildScatter(result: PeerParityResult): ScatterRender {
  const { range, scatter, regression } = result;
  const cMin = Math.max(0, range.compositeMin - 5);
  const cMax = Math.min(100, range.compositeMax + 5);
  const bMin = Math.max(0, range.baseMin * 0.85);
  const bMax = range.baseMax * 1.15;
  const innerW = SCATTER_W - PAD_L - PAD_R;
  const innerH = SCATTER_H - PAD_T - PAD_B;
  const xAt = (c: number) => PAD_L + ((c - cMin) / (cMax - cMin)) * innerW;
  const yAt = (b: number) => PAD_T + (1 - (b - bMin) / (bMax - bMin)) * innerH;

  const points = scatter.map(s => ({ x: xAt(s.composite), y: yAt(s.base), pt: s }));

  if (regression.n < 2 || result.regression.r2 < 0) {
    return { points, regression: null, band: null };
  }
  const a = regression.a;
  const b0 = regression.b;
  const sigma = regression.sigma;
  const x1 = cMin, x2 = cMax;
  const y1 = a * x1 + b0;
  const y2 = a * x2 + b0;
  return {
    points,
    regression: { x1: xAt(x1), y1: yAt(y1), x2: xAt(x2), y2: yAt(y2) },
    band: {
      x1: xAt(x1), y1Lo: yAt(y1 - sigma), y1Hi: yAt(y1 + sigma),
      x2: xAt(x2), y2Lo: yAt(y2 - sigma), y2Hi: yAt(y2 + sigma),
    },
  };
}

function ScatterChart({
  points, regression, band, hue,
}: ScatterRender & { hue: string }) {
  return (
    <svg
      viewBox={`0 0 ${SCATTER_W} ${SCATTER_H}`}
      preserveAspectRatio="xMidYMid meet"
      className="mt-3 w-full"
      role="img"
      aria-label="Peer scatter — composite vs base salary"
    >
      <defs>
        <linearGradient id="parity-band" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor="rgba(167,139,250,0.18)" />
          <stop offset="100%" stopColor="rgba(96,165,250,0.10)" />
        </linearGradient>
        <filter id="parity-glow" x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur stdDeviation="2.6" result="b" />
          <feMerge>
            <feMergeNode in="b" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>

      {/* axes */}
      <line x1={PAD_L} y1={SCATTER_H - PAD_B} x2={SCATTER_W - PAD_R} y2={SCATTER_H - PAD_B} stroke="rgba(255,255,255,0.10)" />
      <line x1={PAD_L} y1={PAD_T} x2={PAD_L} y2={SCATTER_H - PAD_B} stroke="rgba(255,255,255,0.10)" />

      {/* axis labels */}
      <text x={(PAD_L + SCATTER_W - PAD_R) / 2} y={SCATTER_H - 6} textAnchor="middle" fill="rgba(255,255,255,0.4)" fontSize="10">
        Interview composite →
      </text>
      <text x={10} y={PAD_T + 6} textAnchor="start" fill="rgba(255,255,255,0.4)" fontSize="10">
        Base (LPA) ↑
      </text>

      {/* ±1σ band */}
      {band && (
        <polygon
          points={`${band.x1},${band.y1Lo} ${band.x2},${band.y2Lo} ${band.x2},${band.y2Hi} ${band.x1},${band.y1Hi}`}
          fill="url(#parity-band)"
        />
      )}

      {/* regression line */}
      {regression && (
        <line
          x1={regression.x1} y1={regression.y1}
          x2={regression.x2} y2={regression.y2}
          stroke="rgba(167,139,250,0.8)"
          strokeWidth={1.4}
          strokeDasharray="4 4"
        />
      )}

      {/* peer dots */}
      {points.filter(p => !p.pt.isProposed).map(p => (
        <g key={p.pt.id}>
          <circle cx={p.x} cy={p.y} r={4.5} fill="rgba(148,163,184,0.85)" stroke="rgba(10,10,16,0.95)" strokeWidth={1} />
          <title>{`${p.pt.name} · composite ${p.pt.composite} · ₹${p.pt.base} LPA · total ₹${p.pt.total} LPA`}</title>
        </g>
      ))}

      {/* proposed marker — glowing star */}
      {points.filter(p => p.pt.isProposed).map(p => (
        <g key={p.pt.id} transform={`translate(${p.x},${p.y})`} filter="url(#parity-glow)">
          <Star r={7.5} fill={hue} />
          <title>{`Proposed · composite ${p.pt.composite} · ₹${p.pt.base} LPA · total ₹${p.pt.total} LPA`}</title>
        </g>
      ))}
    </svg>
  );
}
