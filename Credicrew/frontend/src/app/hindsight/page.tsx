'use client';

import { useEffect, useMemo, useState, type CSSProperties } from 'react';
import Link from 'next/link';

import { candidates as CANDIDATES } from '@/data/candidates';
import {
  analyzeHindsight,
  buildBrief,
  clearAllOutcomes,
  clearOutcome,
  ensureInterviewsForHires,
  interviewsByKey,
  listOutcomes,
  outcomeMap,
  setOutcome,
  type DimensionCalibration,
  type HindsightSummary,
  type HireOutcome,
  type HireRecord,
  type SurpriseCase,
} from '@/lib/hindsight';
import {
  addToShortlist,
  listRoles,
  setStatus,
  type Role,
} from '@/lib/roles';

// ---------- helpers ----------

function copyToClipboard(s: string): Promise<void> {
  if (typeof navigator !== 'undefined' && navigator.clipboard) {
    return navigator.clipboard.writeText(s);
  }
  return new Promise(res => {
    const ta = document.createElement('textarea');
    ta.value = s;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    ta.remove();
    res();
  });
}

function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map(w => w[0]?.toUpperCase() ?? '')
    .join('');
}

function fmtPct(v: number): string {
  return `${Math.round(v * 100)}%`;
}

function fmtDays(d: number): string {
  if (d >= 365) return `${(d / 365).toFixed(1)}y`;
  if (d >= 30) return `${(d / 30).toFixed(1)}mo`;
  return `${d}d`;
}

const BAND_HUE: Record<HindsightSummary['calibrationBand'], string> = {
  excellent: '#34d399',
  good: '#22d3ee',
  mixed: '#f59e0b',
  concerning: '#f43f5e',
  unknown: '#94a3b8',
};

const BAND_LABEL: Record<HindsightSummary['calibrationBand'], string> = {
  excellent: 'rubric is calibrated',
  good: 'mostly predictive',
  mixed: 'partial signal',
  concerning: 'rubric not predictive',
  unknown: 'too early to tell',
};

const DIM_BAND_HUE: Record<DimensionCalibration['band'], string> = {
  strong: '#34d399',
  moderate: '#22d3ee',
  weak: '#f59e0b',
  unknown: '#64748b',
};

const DIM_BAND_LABEL: Record<DimensionCalibration['band'], string> = {
  strong: 'strong',
  moderate: 'moderate',
  weak: 'weak',
  unknown: 'unknown',
};

const PERF_HUE: Record<number, string> = {
  1: '#f43f5e',
  2: '#fb923c',
  3: '#f59e0b',
  4: '#22d3ee',
  5: '#34d399',
};

// ---------- atoms ----------

function CalibrationRing({
  pearson,
  band,
  size = 184,
}: {
  pearson: number;
  band: HindsightSummary['calibrationBand'];
  size?: number;
}) {
  const pct = Math.max(0, Math.min(100, Math.round(Math.abs(pearson) * 100)));
  const hue = BAND_HUE[band];
  return (
    <div
      className="cc-hd-ring relative grid place-items-center rounded-full"
      style={{
        width: size,
        height: size,
        background: `conic-gradient(${hue} ${pct}%, rgba(255,255,255,0.06) 0)`,
      }}
    >
      <div className="absolute rounded-full bg-[#0b0b12]" style={{ inset: 6 }} />
      <div className="relative flex flex-col items-center leading-none">
        <span className="text-[11px] uppercase tracking-wider text-white/55">Pearson r</span>
        <span
          className="mt-1 text-4xl font-semibold tabular-nums"
          style={{ color: hue }}
        >
          {pearson.toFixed(2)}
        </span>
        <span className="mt-1 text-[10px] uppercase tracking-wider text-white/45">
          {BAND_LABEL[band]}
        </span>
      </div>
    </div>
  );
}

function StatTile({
  label,
  value,
  sub,
  hue,
}: {
  label: string;
  value: string;
  sub?: string;
  hue?: string;
}) {
  return (
    <div
      className="cc-hd-tile relative overflow-hidden rounded-xl border border-white/10 bg-white/5 p-4"
      style={
        hue
          ? ({
              ['--hd-accent' as keyof CSSProperties]: hue,
            } as CSSProperties)
          : undefined
      }
    >
      <div
        aria-hidden
        className="pointer-events-none absolute inset-x-0 top-0 h-px opacity-70"
        style={hue ? { background: hue } : undefined}
      />
      <div className="text-[11px] uppercase tracking-wider text-white/55">{label}</div>
      <div
        className="mt-1 text-2xl font-semibold tabular-nums"
        style={hue ? { color: hue } : undefined}
      >
        {value}
      </div>
      {sub && <div className="mt-1 text-[11px] text-white/50">{sub}</div>}
    </div>
  );
}

function PerformanceDot({ rating }: { rating: number }) {
  const r = Math.max(1, Math.min(5, Math.round(rating)));
  const hue = PERF_HUE[r];
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[11px] tabular-nums"
      style={{ borderColor: `${hue}55`, background: `${hue}15`, color: hue }}
    >
      <span className="h-1.5 w-1.5 rounded-full" style={{ background: hue }} />
      {rating.toFixed(1)}/5
    </span>
  );
}

function BandPill({ band }: { band: DimensionCalibration['band'] }) {
  const hue = DIM_BAND_HUE[band];
  return (
    <span
      className="rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-wider"
      style={{
        borderColor: `${hue}50`,
        background: `${hue}15`,
        color: hue,
      }}
    >
      {DIM_BAND_LABEL[band]}
    </span>
  );
}

// ---------- empty state ----------

function EmptyState({ onSeed }: { onSeed: () => void }) {
  return (
    <div className="mx-auto mt-16 max-w-2xl rounded-2xl border border-white/10 bg-white/5 p-8 text-center">
      <div className="mx-auto grid h-12 w-12 place-items-center rounded-full bg-gradient-to-br from-emerald-400/60 to-sky-500/60 text-xl">
        🪞
      </div>
      <h2 className="mt-4 text-xl font-semibold">No hires to review yet</h2>
      <p className="mt-2 text-sm text-white/60">
        Hindsight reads every shortlist entry currently in{' '}
        <span className="rounded bg-emerald-400/15 px-1.5 text-emerald-200">Offer</span> status,
        pairs it with the post-hire performance outcome you log, and calibrates the rubric from
        the result. Until then, seed a demo pool to see the engine work on real fixtures.
      </p>
      <div className="mt-4 flex items-center justify-center gap-2 text-xs">
        <button
          onClick={onSeed}
          className="rounded-md border border-emerald-400/40 bg-emerald-500/15 px-3 py-1.5 text-emerald-200 hover:bg-emerald-500/25"
        >
          Seed demo hires
        </button>
        <Link
          href="/roles"
          className="rounded-md border border-white/10 bg-white/5 px-3 py-1.5 text-white/80 hover:bg-white/10"
        >
          Open Roles
        </Link>
      </div>
    </div>
  );
}

// ---------- calibration curve ----------

function CalibrationCurve({ bins }: { bins: HindsightSummary['compositeBins'] }) {
  const width = 520;
  const height = 220;
  const pad = { l: 36, r: 12, t: 16, b: 28 };
  const innerW = width - pad.l - pad.r;
  const innerH = height - pad.t - pad.b;
  // Y axis: performance 1..5
  const yMin = 1, yMax = 5;
  const xs = bins.map(b => b.floor);
  // Bin centres
  const cx = (floor: number) => pad.l + ((floor + 5) / 100) * innerW;
  const cy = (perf: number) => pad.t + innerH - ((perf - yMin) / (yMax - yMin)) * innerH;

  // Build path through non-empty bins
  const pts = bins.filter(b => b.count > 0).map(b => ({
    x: cx(b.floor),
    y: cy(b.meanPerformance),
    bin: b,
  }));
  const path = pts.length > 1
    ? `M ${pts[0].x.toFixed(1)} ${pts[0].y.toFixed(1)} ` +
      pts.slice(1).map(p => `L ${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(' ')
    : '';

  // Reference diagonal: ideal calibration is monotone — we draw composite/20+1.
  const ideal = `M ${pad.l} ${cy(1)} L ${pad.l + innerW} ${cy(5)}`;

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="w-full" role="img" aria-label="Calibration curve">
      <defs>
        <linearGradient id="hd-curve-grad" x1="0" x2="1">
          <stop offset="0%" stopColor="#f43f5e" />
          <stop offset="50%" stopColor="#22d3ee" />
          <stop offset="100%" stopColor="#34d399" />
        </linearGradient>
      </defs>
      {/* axes */}
      <line x1={pad.l} y1={pad.t + innerH} x2={pad.l + innerW} y2={pad.t + innerH} stroke="rgba(255,255,255,0.15)" />
      <line x1={pad.l} y1={pad.t} x2={pad.l} y2={pad.t + innerH} stroke="rgba(255,255,255,0.15)" />
      {/* y ticks */}
      {[1, 2, 3, 4, 5].map(r => (
        <g key={r}>
          <text x={pad.l - 6} y={cy(r) + 3} fontSize="9" textAnchor="end" fill="rgba(255,255,255,0.45)">{r}</text>
          <line x1={pad.l} y1={cy(r)} x2={pad.l + innerW} y2={cy(r)} stroke="rgba(255,255,255,0.05)" />
        </g>
      ))}
      {/* x ticks */}
      {xs.filter((_, i) => i % 2 === 0).map(f => (
        <text key={f} x={cx(f)} y={pad.t + innerH + 14} fontSize="9" textAnchor="middle" fill="rgba(255,255,255,0.45)">
          {f}
        </text>
      ))}
      {/* ideal */}
      <path d={ideal} stroke="rgba(255,255,255,0.18)" strokeDasharray="4 4" fill="none" />
      {/* connecting line */}
      {path && (
        <path d={path} stroke="url(#hd-curve-grad)" strokeWidth="2.2" fill="none" />
      )}
      {/* dots */}
      {pts.map((p, i) => (
        <g key={i}>
          <circle
            cx={p.x}
            cy={p.y}
            r={4 + Math.min(8, Math.sqrt(p.bin.count) * 2)}
            fill={PERF_HUE[Math.round(p.bin.meanPerformance)] ?? '#a78bfa'}
            opacity="0.85"
          />
          <title>
            {`Composite ${p.bin.label} · n=${p.bin.count} · mean perf ${p.bin.meanPerformance.toFixed(2)} · good ${fmtPct(p.bin.goodRate)}`}
          </title>
        </g>
      ))}
      <text x={pad.l + innerW / 2} y={height - 4} fontSize="9" textAnchor="middle" fill="rgba(255,255,255,0.4)">
        Interview composite
      </text>
      <text
        x={pad.l - 22}
        y={pad.t + innerH / 2}
        fontSize="9"
        textAnchor="middle"
        fill="rgba(255,255,255,0.4)"
        transform={`rotate(-90 ${pad.l - 22} ${pad.t + innerH / 2})`}
      >
        Mean performance
      </text>
    </svg>
  );
}

// ---------- per-dim bar ----------

function PredictivePowerBar({ d }: { d: DimensionCalibration }) {
  const pct = Math.min(100, d.predictivePower);
  const hue = DIM_BAND_HUE[d.band];
  return (
    <div className="flex w-full flex-col gap-1">
      <div className="flex items-center justify-between text-[10px] uppercase tracking-wider text-white/45">
        <span>Predictive power · r={d.rPerformance.toFixed(2)}</span>
        <span className="tabular-nums text-white/65">{d.predictivePower}</span>
      </div>
      <div className="h-2 w-full overflow-hidden rounded-full bg-white/5">
        <div
          className="h-full rounded-full transition-all"
          style={{ width: `${pct}%`, background: hue }}
        />
      </div>
    </div>
  );
}

function WeightDeltaBar({ d }: { d: DimensionCalibration }) {
  // Centre = current weight. Bar to the right (emerald) for promote, left (rose) for reduce.
  const maxAxis = 0.5; // weights cap visualisation at 0.5
  const cur = Math.min(maxAxis, d.currentWeight);
  const sug = Math.min(maxAxis, d.suggestedWeight);
  const left = (Math.min(cur, sug) / maxAxis) * 100;
  const right = (Math.max(cur, sug) / maxAxis) * 100;
  const fillStart = Math.min(cur, sug) / maxAxis * 100;
  const fillEnd = Math.max(cur, sug) / maxAxis * 100;
  const delta = d.suggestedWeight - d.currentWeight;
  const hue = delta >= 0 ? '#34d399' : '#f43f5e';
  return (
    <div className="flex w-full flex-col gap-1">
      <div className="flex items-center justify-between text-[10px] uppercase tracking-wider text-white/45">
        <span>
          {d.currentWeight.toFixed(3)} → {d.suggestedWeight.toFixed(3)}
        </span>
        <span className="tabular-nums" style={{ color: hue }}>
          {delta >= 0 ? '+' : ''}{delta.toFixed(3)}
        </span>
      </div>
      <div className="relative h-2 w-full overflow-hidden rounded-full bg-white/5">
        <div
          className="absolute top-0 h-full"
          style={{
            left: `${fillStart}%`,
            width: `${Math.max(2, fillEnd - fillStart)}%`,
            background: `linear-gradient(90deg, ${hue}55, ${hue})`,
          }}
        />
        {/* current marker */}
        <div
          className="absolute top-0 h-full w-px bg-white/55"
          style={{ left: `${(cur / maxAxis) * 100}%` }}
        />
        {/* suggested marker */}
        <div
          className="absolute top-0 h-full w-[2px]"
          style={{ left: `${(sug / maxAxis) * 100}%`, background: hue }}
        />
      </div>
      <div className="flex items-center justify-between text-[9px] text-white/35">
        <span>0</span>
        <span>0.25</span>
        <span>0.5</span>
      </div>
    </div>
  );
}

// ---------- hire row (outcome editor) ----------

function HireRow({
  hire,
  onSetOutcome,
  onClearOutcome,
}: {
  hire: HireRecord;
  onSetOutcome: (perf: 1 | 2 | 3 | 4 | 5, stillActive: boolean, note?: string) => void;
  onClearOutcome: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [perf, setPerf] = useState<number>(hire.outcome.performance);
  const [active, setActive] = useState<boolean>(hire.outcome.stillActive);
  const [note, setNoteState] = useState<string>(hire.outcome.note ?? '');

  return (
    <div className="cc-hd-row rounded-xl border border-white/10 bg-white/[0.03] p-4">
      <div className="flex items-start gap-3">
        <div
          className="grid h-10 w-10 shrink-0 place-items-center rounded-full text-[11px] font-semibold"
          style={{
            background: 'rgba(167,139,250,0.15)',
            color: '#c4b5fd',
            border: '1px solid rgba(167,139,250,0.35)',
          }}
        >
          {initials(hire.candidateName)}
        </div>
        <div className="flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <div className="text-sm font-semibold text-white">{hire.candidateName}</div>
            <Link
              href={`/roles/${hire.roleId}`}
              className="rounded-md border border-white/10 bg-white/5 px-2 py-0.5 text-[11px] text-white/70 hover:bg-white/10"
            >
              {hire.roleName}
            </Link>
            <span className="rounded-full border border-indigo-400/30 bg-indigo-400/10 px-2 py-0.5 text-[10px] uppercase tracking-wider text-indigo-200">
              composite {hire.composite ?? '—'}
            </span>
            <PerformanceDot rating={hire.outcome.performance} />
            <span
              className="rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-wider"
              style={
                hire.outcome.stillActive
                  ? { borderColor: '#34d39955', background: '#34d39915', color: '#34d399' }
                  : { borderColor: '#f4344555', background: '#f4344515', color: '#f87171' }
              }
            >
              {hire.outcome.stillActive ? `active · ${fmtDays(hire.outcome.tenureDays)}` : `attrited · ${fmtDays(hire.outcome.tenureDays)}`}
            </span>
            {hire.outcome.source === 'synthetic' && (
              <span className="rounded-full border border-white/10 bg-white/5 px-2 py-0.5 text-[10px] uppercase tracking-wider text-white/55">
                synthetic
              </span>
            )}
          </div>
          {hire.outcome.note && !editing && (
            <div className="mt-2 text-[12px] text-white/65">"{hire.outcome.note}"</div>
          )}
        </div>
        <div className="shrink-0">
          {editing ? (
            <button
              onClick={() => {
                onSetOutcome(perf as 1 | 2 | 3 | 4 | 5, active, note || undefined);
                setEditing(false);
              }}
              className="rounded-md border border-emerald-400/40 bg-emerald-500/15 px-3 py-1.5 text-xs font-medium text-emerald-100 hover:bg-emerald-500/25"
            >
              Save outcome
            </button>
          ) : (
            <button
              onClick={() => setEditing(true)}
              className="rounded-md border border-white/10 bg-white/5 px-3 py-1.5 text-xs text-white/70 hover:bg-white/10"
            >
              {hire.outcome.source === 'real' ? 'Edit outcome' : 'Log real outcome'}
            </button>
          )}
        </div>
      </div>

      {editing && (
        <div className="mt-3 grid gap-3 rounded-lg border border-white/10 bg-white/[0.02] p-3 md:grid-cols-2">
          <div>
            <div className="text-[10px] uppercase tracking-wider text-white/45">Performance (1–5)</div>
            <div className="mt-2 flex items-center gap-2">
              {[1, 2, 3, 4, 5].map(n => (
                <button
                  key={n}
                  onClick={() => setPerf(n)}
                  className={`h-8 w-8 rounded-md border text-sm tabular-nums ${
                    perf === n
                      ? 'border-white/45 bg-white/10 text-white'
                      : 'border-white/10 bg-white/[0.03] text-white/55 hover:bg-white/10'
                  }`}
                >
                  {n}
                </button>
              ))}
            </div>
          </div>
          <div>
            <div className="text-[10px] uppercase tracking-wider text-white/45">Still active?</div>
            <div className="mt-2 flex items-center gap-2">
              <button
                onClick={() => setActive(true)}
                className={`rounded-md border px-3 py-1.5 text-xs ${
                  active
                    ? 'border-emerald-400/40 bg-emerald-500/15 text-emerald-100'
                    : 'border-white/10 bg-white/[0.03] text-white/55 hover:bg-white/10'
                }`}
              >
                Active
              </button>
              <button
                onClick={() => setActive(false)}
                className={`rounded-md border px-3 py-1.5 text-xs ${
                  !active
                    ? 'border-rose-400/40 bg-rose-500/15 text-rose-100'
                    : 'border-white/10 bg-white/[0.03] text-white/55 hover:bg-white/10'
                }`}
              >
                Attrited
              </button>
            </div>
          </div>
          <div className="md:col-span-2">
            <div className="text-[10px] uppercase tracking-wider text-white/45">Manager note (optional)</div>
            <input
              type="text"
              value={note}
              onChange={e => setNoteState(e.target.value)}
              placeholder="e.g. owned migration to event-driven backend ahead of schedule."
              className="mt-1 w-full rounded-md border border-white/10 bg-white/[0.03] px-3 py-1.5 text-sm text-white placeholder:text-white/30 focus:border-indigo-400/50 focus:outline-none"
            />
          </div>
          <div className="md:col-span-2 flex justify-end gap-2">
            {hire.outcome.source === 'real' && (
              <button
                onClick={() => {
                  onClearOutcome();
                  setEditing(false);
                }}
                className="rounded-md border border-rose-400/30 bg-rose-500/10 px-3 py-1.5 text-xs text-rose-200 hover:bg-rose-500/20"
              >
                Reset to synthetic
              </button>
            )}
            <button
              onClick={() => setEditing(false)}
              className="rounded-md border border-white/10 bg-white/[0.03] px-3 py-1.5 text-xs text-white/65 hover:bg-white/10"
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

// ---------- surprise card ----------

function SurpriseCard({ c }: { c: SurpriseCase }) {
  const isFp = c.kind === 'false_positive';
  const hue = isFp ? '#f43f5e' : '#22d3ee';
  return (
    <div
      className="cc-hd-surprise relative overflow-hidden rounded-xl border border-white/10 bg-white/[0.04] p-4"
      style={{ ['--hd-accent' as keyof CSSProperties]: hue } as CSSProperties}
    >
      <div
        aria-hidden
        className="pointer-events-none absolute inset-x-0 top-0 h-px opacity-80"
        style={{ background: `linear-gradient(to right, transparent, ${hue}, transparent)` }}
      />
      <div className="flex items-center gap-2">
        <span
          className="rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-wider"
          style={{ borderColor: `${hue}55`, background: `${hue}15`, color: hue }}
        >
          {isFp ? 'false positive' : 'false negative'}
        </span>
        <Link
          href={`/roles/${c.roleId}`}
          className="rounded-md border border-white/10 bg-white/5 px-2 py-0.5 text-[11px] text-white/70 hover:bg-white/10"
        >
          {c.roleName}
        </Link>
      </div>
      <div className="mt-2 flex items-center gap-2">
        <div
          className="grid h-9 w-9 shrink-0 place-items-center rounded-full text-[11px] font-semibold"
          style={{ background: `${hue}22`, color: hue, border: `1px solid ${hue}55` }}
        >
          {initials(c.candidateName)}
        </div>
        <div className="text-sm font-semibold text-white">{c.candidateName}</div>
        <span className="rounded-full border border-indigo-400/30 bg-indigo-400/10 px-2 py-0.5 text-[10px] uppercase tracking-wider text-indigo-200">
          composite {c.composite}
        </span>
        <PerformanceDot rating={c.performance} />
        <span className="rounded-full border border-white/10 bg-white/5 px-2 py-0.5 text-[10px] uppercase tracking-wider text-white/55">
          tenure {fmtDays(c.tenureDays)}
        </span>
      </div>
      <p className="mt-2 text-[12px] leading-relaxed text-white/75">{c.why}</p>
    </div>
  );
}

// ---------- main page ----------

export default function HindsightPage() {
  const [hydrated, setHydrated] = useState(false);
  const [roles, setRoles] = useState<Role[]>([]);
  const [outcomes, setOutcomes] = useState<HireOutcome[]>([]);
  const [filter, setFilter] = useState<'all' | 'real' | 'synthetic'>('all');
  const [showHowItWorks, setShowHowItWorks] = useState(false);
  const [briefMsg, setBriefMsg] = useState<string>('');

  useEffect(() => {
    setHydrated(true);
    setRoles(listRoles());
    setOutcomes(listOutcomes());
  }, []);

  const refresh = () => {
    setRoles(listRoles());
    setOutcomes(listOutcomes());
  };

  const overrides = useMemo(() => {
    const m = new Map<string, HireOutcome>();
    for (const o of outcomes) m.set(`${o.candidateId}::${o.roleId}`, o);
    return m;
  }, [outcomes]);

  const ivKeys = useMemo(() => {
    if (!hydrated) return interviewsByKey([]);
    return interviewsByKey(roles);
  }, [roles, hydrated]);

  const summary = useMemo(() => {
    if (!hydrated) return null;
    return analyzeHindsight(roles, CANDIDATES, overrides, { interviewsByKey: ivKeys });
  }, [roles, overrides, ivKeys, hydrated]);

  const visibleHires = useMemo(() => {
    if (!summary) return [];
    if (filter === 'all') return summary.hires;
    if (filter === 'real') return summary.hires.filter(h => h.outcome.source === 'real');
    return summary.hires.filter(h => h.outcome.source === 'synthetic');
  }, [summary, filter]);

  function seedDemoHires() {
    // Drop 6 candidates into the first three roles' shortlists as offer-status.
    const rolesList = listRoles();
    if (rolesList.length < 2) return;
    const usedIds = new Set<number>();
    for (const r of rolesList) for (const e of r.shortlist) usedIds.add(e.candidateId);
    const pool = CANDIDATES.filter(c => !usedIds.has(c.id));
    const picks = pool.slice(0, 6);
    const distribution = [
      { idx: 0, roleI: 0 },
      { idx: 1, roleI: 0 },
      { idx: 2, roleI: 1 },
      { idx: 3, roleI: 1 },
      { idx: 4, roleI: Math.min(2, rolesList.length - 1) },
      { idx: 5, roleI: Math.min(2, rolesList.length - 1) },
    ];
    for (const d of distribution) {
      const cand = picks[d.idx];
      const role = rolesList[d.roleI];
      if (!cand || !role) continue;
      addToShortlist(role.id, cand.id, 'offer');
      setStatus(role.id, cand.id, 'offer');
    }
    ensureInterviewsForHires(listRoles(), CANDIDATES);
    refresh();
  }

  function onSetHireOutcome(hire: HireRecord, perf: 1 | 2 | 3 | 4 | 5, stillActive: boolean, note?: string) {
    const tenure = Math.max(7, Math.floor((Date.now() - hire.hiredAtMs) / 86_400_000));
    setOutcome({
      candidateId: hire.candidateId,
      roleId: hire.roleId,
      hiredAtMs: hire.hiredAtMs,
      performance: perf,
      stillActive,
      tenureDays: tenure,
      note,
      source: 'real',
    });
    refresh();
  }

  function onClearHireOutcome(hire: HireRecord) {
    clearOutcome(hire.candidateId, hire.roleId);
    refresh();
  }

  async function onCopyBrief() {
    if (!summary) return;
    const md = buildBrief(summary);
    await copyToClipboard(md);
    setBriefMsg('Copied.');
    setTimeout(() => setBriefMsg(''), 2000);
  }

  function onDownloadBrief() {
    if (!summary) return;
    const md = buildBrief(summary);
    const blob = new Blob([md], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `hindsight-${new Date().toISOString().slice(0, 10)}.md`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  function onResetAll() {
    if (typeof window !== 'undefined') {
      const ok = window.confirm('Clear all logged outcomes? Synthetic outcomes will be re-derived on next render.');
      if (!ok) return;
    }
    clearAllOutcomes();
    refresh();
  }

  if (!hydrated) {
    return (
      <main className="mx-auto max-w-6xl px-4 py-10 text-white">
        <div className="rounded-2xl border border-white/10 bg-white/5 p-8 text-center text-white/55">
          Loading…
        </div>
      </main>
    );
  }

  if (!summary || summary.hireCount === 0) {
    return (
      <main className="mx-auto max-w-6xl px-4 py-10 text-white">
        <PageHero summary={null} onSeed={seedDemoHires} />
        <EmptyState onSeed={seedDemoHires} />
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-6xl px-4 py-8 text-white">
      <PageHero summary={summary} onSeed={seedDemoHires} />

      {/* Hero band */}
      <section
        className="cc-hd-hero relative mt-6 grid gap-6 overflow-hidden rounded-3xl border border-white/10 bg-white/5 p-6 md:grid-cols-[auto,1fr]"
        style={{ ['--hd-accent' as keyof CSSProperties]: BAND_HUE[summary.calibrationBand] } as CSSProperties}
      >
        <div className="flex items-center gap-6">
          <CalibrationRing pearson={summary.pearson} band={summary.calibrationBand} />
          <div className="flex flex-col gap-2">
            <div className="text-[11px] uppercase tracking-wider text-white/55">Hindsight</div>
            <div className="text-2xl font-semibold leading-tight">
              {summary.hireCount} hire{summary.hireCount === 1 ? '' : 's'} reviewed
            </div>
            <div className="text-[13px] text-white/65">
              {summary.realCount} real outcome{summary.realCount === 1 ? '' : 's'} · {summary.syntheticCount} synthesised
            </div>
            <div className="flex flex-wrap items-center gap-2 pt-2">
              <span
                className="rounded-full border px-2.5 py-1 text-[11px] uppercase tracking-wider"
                style={{
                  borderColor: `${BAND_HUE[summary.calibrationBand]}55`,
                  background: `${BAND_HUE[summary.calibrationBand]}15`,
                  color: BAND_HUE[summary.calibrationBand],
                }}
              >
                {BAND_LABEL[summary.calibrationBand]}
              </span>
              <span className="rounded-full border border-white/10 bg-white/5 px-2 py-0.5 text-[11px] text-white/65">
                Spearman {summary.spearman.toFixed(2)}
              </span>
              <span className="rounded-full border border-white/10 bg-white/5 px-2 py-0.5 text-[11px] text-white/65">
                Brier {summary.brierScore.toFixed(2)}
              </span>
            </div>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <StatTile label="Hit rate (perf ≥ 4)" value={fmtPct(summary.hitRate)} sub="of hires reach the team's bar" hue="#34d399" />
          <StatTile label="Mean composite" value={`${summary.meanComposite}`} sub={`mean perf ${summary.meanPerformance.toFixed(2)}/5`} hue="#a78bfa" />
          <StatTile label="Mean tenure" value={fmtDays(summary.meanTenureDays)} sub="from hire to today" hue="#22d3ee" />
          <StatTile
            label="Attrition"
            value={fmtPct(summary.attritionRate)}
            sub={summary.attritionRate >= 0.2 ? 'investigate onboarding' : 'healthy'}
            hue={summary.attritionRate >= 0.2 ? '#f43f5e' : '#34d399'}
          />
        </div>
      </section>

      {/* Action strip */}
      {summary.actions.length > 0 && (
        <section className="mt-6 rounded-2xl border border-violet-400/20 bg-violet-500/[0.07] p-5">
          <div className="mb-2 text-[11px] uppercase tracking-wider text-violet-200/80">Actions</div>
          <ul className="space-y-1.5 text-[13px] leading-relaxed text-white/80">
            {summary.actions.map((a, i) => (
              <li key={i} className="flex items-start gap-2">
                <span className="mt-1.5 inline-block h-1.5 w-1.5 shrink-0 rounded-full bg-violet-300" />
                <span dangerouslySetInnerHTML={{ __html: renderInlineMarkdown(a) }} />
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Per-dim grid + calibration curve */}
      <section className="mt-8 grid gap-6 lg:grid-cols-[1.4fr,1fr]">
        <div className="rounded-2xl border border-white/10 bg-white/5 p-5">
          <div className="flex items-center justify-between">
            <div>
              <div className="text-[11px] uppercase tracking-wider text-white/55">Rubric dimensions</div>
              <div className="mt-1 text-lg font-semibold">Predictive power · weight reweight</div>
            </div>
            <span className="text-[11px] text-white/50">
              Min {`n=${4}`} for signal · |r| · suggested = 0.5·observed + 0.5·current
            </span>
          </div>
          {summary.perDimension.length === 0 ? (
            <div className="mt-4 rounded-lg border border-white/10 bg-white/[0.03] p-4 text-[13px] text-white/55">
              No rated dimensions across hires yet. Run an interview on each shortlisted candidate
              to unlock per-dim calibration.
            </div>
          ) : (
            <div className="mt-4 space-y-3">
              {summary.perDimension.map(d => (
                <div
                  key={d.key}
                  className="cc-hd-dim relative grid gap-3 rounded-xl border border-white/10 bg-white/[0.03] p-4 md:grid-cols-[1fr,1fr]"
                >
                  <div>
                    <div className="flex items-center gap-2">
                      <BandPill band={d.band} />
                      <div className="text-sm font-semibold">{d.label}</div>
                      <span className="text-[10px] uppercase tracking-wider text-white/45">n={d.samples}</span>
                    </div>
                    <div className="mt-2">
                      <PredictivePowerBar d={d} />
                    </div>
                    <div className="mt-2 text-[11px] text-white/55">
                      tenure r {d.rTenure.toFixed(2)} · perf r {d.rPerformance.toFixed(2)}
                    </div>
                  </div>
                  <div>
                    <div className="text-[10px] uppercase tracking-wider text-white/45">Weight</div>
                    <div className="mt-2">
                      <WeightDeltaBar d={d} />
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="rounded-2xl border border-white/10 bg-white/5 p-5">
          <div className="text-[11px] uppercase tracking-wider text-white/55">Calibration curve</div>
          <div className="mt-1 text-lg font-semibold">Composite → mean performance</div>
          <div className="mt-3">
            <CalibrationCurve bins={summary.compositeBins} />
          </div>
          <div className="mt-3 grid grid-cols-2 gap-2 text-[11px] text-white/65">
            <div>
              <span className="mr-1 inline-block h-1 w-3 align-middle" style={{ background: 'rgba(255,255,255,0.3)' }} />
              ideal monotone
            </div>
            <div>
              <span className="mr-1 inline-block h-1 w-3 align-middle" style={{ background: '#22d3ee' }} />
              observed mean perf
            </div>
          </div>
          {summary.compositeBins.some(b => b.count > 0) && (
            <div className="mt-4 max-h-44 overflow-y-auto rounded-lg border border-white/10 bg-white/[0.02]">
              <table className="w-full text-[11px] text-white/70">
                <thead className="sticky top-0 bg-white/[0.04] text-[10px] uppercase tracking-wider text-white/45">
                  <tr>
                    <th className="px-2 py-1 text-left">bin</th>
                    <th className="px-2 py-1 text-right">n</th>
                    <th className="px-2 py-1 text-right">mean perf</th>
                    <th className="px-2 py-1 text-right">good rate</th>
                  </tr>
                </thead>
                <tbody>
                  {summary.compositeBins.filter(b => b.count > 0).map(b => (
                    <tr key={b.label} className="border-t border-white/[0.04]">
                      <td className="px-2 py-1 tabular-nums">{b.label}</td>
                      <td className="px-2 py-1 text-right tabular-nums">{b.count}</td>
                      <td className="px-2 py-1 text-right tabular-nums">{b.meanPerformance.toFixed(2)}</td>
                      <td className="px-2 py-1 text-right tabular-nums">{fmtPct(b.goodRate)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </section>

      {/* Rubric recommendation */}
      <section className="mt-8 grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <RecommendationCard
          title="Promote"
          tone="#34d399"
          items={summary.rubricRecommendation.promote.map(r => ({
            label: r.label,
            detail: `+${r.delta.toFixed(3)} → ${r.suggestedWeight.toFixed(3)}`,
          }))}
          emptyText="No dims earn a weight bump yet — log more outcomes."
        />
        <RecommendationCard
          title="Keep"
          tone="#22d3ee"
          items={summary.rubricRecommendation.keep.map(r => ({
            label: r.label,
            detail: `at ${r.currentWeight.toFixed(3)}`,
          }))}
          emptyText="No dims are at their right weight yet — math still shifting."
        />
        <RecommendationCard
          title="Reduce"
          tone="#f59e0b"
          items={summary.rubricRecommendation.reduce.map(r => ({
            label: r.label,
            detail: `${r.delta.toFixed(3)} → ${r.suggestedWeight.toFixed(3)}`,
          }))}
          emptyText="Nothing over-weighted."
        />
        <RecommendationCard
          title="Drop candidates"
          tone="#f43f5e"
          items={summary.rubricRecommendation.drop.map(r => ({
            label: r.label,
            detail: `r=${r.rPerformance.toFixed(2)} · n=${r.samples}`,
          }))}
          emptyText="Every rated dim has at least weak signal."
        />
      </section>

      {/* Tenure by band */}
      <section className="mt-8 rounded-2xl border border-white/10 bg-white/5 p-5">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-[11px] uppercase tracking-wider text-white/55">Tenure × recommendation band</div>
            <div className="mt-1 text-lg font-semibold">Do "strong hires" actually stick longer?</div>
          </div>
          <span className="text-[11px] text-white/50">days tenure · mean perf per band</span>
        </div>
        <div className="mt-4 grid gap-3 md:grid-cols-5">
          {summary.tenureByBand.map(b => {
            const hue = b.band === 'strong_hire' ? '#34d399'
              : b.band === 'lean_yes' ? '#22d3ee'
              : b.band === 'mixed' ? '#a78bfa'
              : b.band === 'lean_no' ? '#f59e0b'
              : '#f43f5e';
            const label = b.band.replace('_', ' ');
            return (
              <div
                key={b.band}
                className="cc-hd-tile relative overflow-hidden rounded-xl border border-white/10 bg-white/[0.03] p-3"
              >
                <div
                  aria-hidden
                  className="pointer-events-none absolute inset-x-0 top-0 h-px"
                  style={{ background: hue }}
                />
                <div className="text-[10px] uppercase tracking-wider text-white/55">{label}</div>
                <div className="mt-1 text-xl font-semibold tabular-nums" style={{ color: hue }}>
                  {b.count === 0 ? '—' : fmtDays(b.meanTenureDays)}
                </div>
                <div className="text-[11px] text-white/55">
                  {b.count === 0 ? 'no hires' : `n=${b.count} · ${b.meanPerformance.toFixed(2)}/5`}
                </div>
              </div>
            );
          })}
        </div>
      </section>

      {/* Surprise cases */}
      {summary.surpriseCases.length > 0 && (
        <section className="mt-8 rounded-2xl border border-white/10 bg-white/5 p-5">
          <div className="flex items-center justify-between">
            <div>
              <div className="text-[11px] uppercase tracking-wider text-white/55">Surprise hires</div>
              <div className="mt-1 text-lg font-semibold">Calibration teachers</div>
            </div>
            <span className="text-[11px] text-white/50">
              FP composite ≥ {80} · perf ≤ {2} · FN composite ≤ {55} · perf ≥ {4}
            </span>
          </div>
          <div className="mt-4 grid gap-3 md:grid-cols-2">
            {summary.surpriseCases.slice(0, 6).map(c => (
              <SurpriseCard key={`${c.candidateId}::${c.roleId}::${c.kind}`} c={c} />
            ))}
          </div>
        </section>
      )}

      {/* Hires list with outcome editor */}
      <section className="mt-8 rounded-2xl border border-white/10 bg-white/5 p-5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <div className="text-[11px] uppercase tracking-wider text-white/55">Hires</div>
            <div className="mt-1 text-lg font-semibold">Log post-hire outcomes</div>
          </div>
          <div className="flex items-center gap-2">
            {(['all', 'real', 'synthetic'] as const).map(f => (
              <button
                key={f}
                onClick={() => setFilter(f)}
                className={`rounded-md border px-3 py-1.5 text-[11px] uppercase tracking-wider transition ${
                  filter === f
                    ? 'border-white/40 bg-white/10 text-white'
                    : 'border-white/10 bg-white/[0.03] text-white/55 hover:bg-white/10'
                }`}
              >
                {f}
              </button>
            ))}
            <button
              onClick={onResetAll}
              className="rounded-md border border-rose-400/30 bg-rose-500/10 px-3 py-1.5 text-[11px] uppercase tracking-wider text-rose-200 hover:bg-rose-500/20"
            >
              Reset all
            </button>
          </div>
        </div>
        <div className="mt-4 space-y-3">
          {visibleHires.length === 0 && (
            <div className="rounded-lg border border-white/10 bg-white/[0.03] p-4 text-[13px] text-white/55">
              No hires match this filter.
            </div>
          )}
          {visibleHires.map(h => (
            <HireRow
              key={`${h.roleId}::${h.candidateId}`}
              hire={h}
              onSetOutcome={(perf, active, note) => onSetHireOutcome(h, perf, active, note)}
              onClearOutcome={() => onClearHireOutcome(h)}
            />
          ))}
        </div>
      </section>

      {/* Brief actions */}
      <section className="mt-8 flex flex-wrap items-center justify-between gap-2 rounded-2xl border border-white/10 bg-white/5 p-5">
        <div>
          <div className="text-[11px] uppercase tracking-wider text-white/55">Calibration brief</div>
          <div className="mt-1 text-sm text-white/70">
            Headline · per-dim r · suggested reweights · surprise hires · calibration curve.
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={onCopyBrief}
            className="rounded-md border border-emerald-400/40 bg-emerald-500/15 px-3 py-1.5 text-xs font-medium text-emerald-100 hover:bg-emerald-500/25"
          >
            {briefMsg ? briefMsg : 'Copy Markdown'}
          </button>
          <button
            onClick={onDownloadBrief}
            className="rounded-md border border-white/10 bg-white/5 px-3 py-1.5 text-xs text-white/80 hover:bg-white/10"
          >
            Download .md
          </button>
          <button
            onClick={() => setShowHowItWorks(s => !s)}
            className="rounded-md border border-white/10 bg-white/5 px-3 py-1.5 text-xs text-white/80 hover:bg-white/10"
          >
            {showHowItWorks ? 'Hide' : 'How it works'}
          </button>
        </div>
      </section>

      {showHowItWorks && (
        <section className="mt-4 rounded-2xl border border-white/10 bg-white/[0.03] p-5 text-[12.5px] leading-relaxed text-white/75">
          <h3 className="text-sm font-semibold text-white">Hindsight math</h3>
          <ul className="mt-2 list-disc space-y-1 pl-5">
            <li><b>Pearson(composite, performance)</b> tells you whether the rubric ranks hires the way they actually perform. ≥0.55 is excellent.</li>
            <li><b>Brier score</b> = <code>mean((composite/100 − good)²)</code>; 0 is perfect, ≈0.25 is uninformative.</li>
            <li><b>Per-dim r(perf)</b> measures how strongly a rubric dim&apos;s rating predicts performance. Dims with |r| ≥ 0.55 are strong predictors.</li>
            <li><b>Suggested weight</b> = 0.5·(|r| / Σ|r|) + 0.5·(current weight), renormalised to sum to 1. Half evidence, half intent — never a wholesale rewrite.</li>
            <li><b>Surprise hires</b> are the calibration teachers: composite ≥ 80 + perf ≤ 2 (panel over-scored) or composite ≤ 55 + perf ≥ 4 (panel under-scored).</li>
            <li><b>Synthetic outcomes</b> seed the calibration on first open. They correlate with composite but carry deterministic noise so dims show non-trivial r. Logged real outcomes always override.</li>
          </ul>
        </section>
      )}
    </main>
  );
}

function PageHero({
  summary,
  onSeed,
}: {
  summary: HindsightSummary | null;
  onSeed: () => void;
}) {
  return (
    <header className="flex items-center justify-between py-2">
      <Link href="/" className="flex items-center gap-2 font-semibold text-white">
        <span className="grid h-7 w-7 place-items-center rounded-full bg-gradient-to-br from-indigo-400 to-violet-600 text-xs font-bold">
          C
        </span>
        <span className="text-lg">Credicrew</span>
      </Link>
      <nav className="hidden items-center gap-1 md:flex">
        <Link href="/" className="rounded-lg px-3 py-1.5 text-sm text-white/70 hover:bg-white/5 hover:text-white">Discover</Link>
        <Link href="/roles" className="rounded-lg px-3 py-1.5 text-sm text-white/70 hover:bg-white/5 hover:text-white">Roles</Link>
        <Link href="/hq" className="rounded-lg px-3 py-1.5 text-sm text-white/70 hover:bg-white/5 hover:text-white">Command Center</Link>
        <Link href="/cadence" className="rounded-lg px-3 py-1.5 text-sm text-white/70 hover:bg-white/5 hover:text-white">Cadence</Link>
        <Link href="/crosswind" className="rounded-lg px-3 py-1.5 text-sm text-white/70 hover:bg-white/5 hover:text-white">Crosswind</Link>
        <Link href="/revive" className="rounded-lg px-3 py-1.5 text-sm text-white/70 hover:bg-white/5 hover:text-white">Revive</Link>
        <Link
          href="/hindsight"
          className="rounded-lg bg-white/10 px-3 py-1.5 text-sm text-white"
        >
          Hindsight
        </Link>
        {summary && summary.hireCount === 0 && (
          <button
            onClick={onSeed}
            className="ml-2 rounded-lg border border-emerald-400/30 bg-emerald-500/15 px-3 py-1.5 text-xs font-medium text-emerald-100 hover:bg-emerald-500/25"
          >
            Seed demo hires
          </button>
        )}
      </nav>
    </header>
  );
}

function RecommendationCard({
  title,
  tone,
  items,
  emptyText,
}: {
  title: string;
  tone: string;
  items: { label: string; detail: string }[];
  emptyText: string;
}) {
  return (
    <div
      className="cc-hd-rec relative overflow-hidden rounded-2xl border border-white/10 bg-white/5 p-4"
      style={{ ['--hd-accent' as keyof CSSProperties]: tone } as CSSProperties}
    >
      <div
        aria-hidden
        className="pointer-events-none absolute inset-x-0 top-0 h-px opacity-80"
        style={{ background: tone }}
      />
      <div className="text-[11px] uppercase tracking-wider" style={{ color: tone }}>{title}</div>
      <div className="mt-1 text-sm font-semibold text-white">
        {items.length} dim{items.length === 1 ? '' : 's'}
      </div>
      <div className="mt-2 space-y-1.5 text-[12px] leading-relaxed">
        {items.length === 0 ? (
          <div className="text-white/55">{emptyText}</div>
        ) : (
          items.slice(0, 4).map(it => (
            <div key={it.label} className="flex items-start justify-between gap-2">
              <span className="text-white/80">{it.label}</span>
              <span className="shrink-0 text-white/55 tabular-nums">{it.detail}</span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

// Render very-light Markdown — `**bold**` only.
function renderInlineMarkdown(text: string): string {
  // Escape HTML first.
  const escaped = text.replace(/[&<>"']/g, ch => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  } as Record<string, string>)[ch] ?? ch);
  return escaped.replace(/\*\*(.+?)\*\*/g, '<strong class="text-white">$1</strong>');
}
