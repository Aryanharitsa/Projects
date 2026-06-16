'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { useParams } from 'next/navigation';

import { getRole, type Role } from '@/lib/roles';
import {
  DEFAULT_ASSUMPTIONS,
  FORECAST_PROGRESSION,
  FORECAST_STAGE_LABEL,
  defaultTargetDate,
  forecastFunnel,
  funnelFromRole,
  quickProbabilityEstimate,
  type ConversionMap,
  type ForecastResult,
  type ForecastStage,
  type VelocityMap,
} from '@/lib/forecast';

// ---------- visual constants ----------

const STAGE_HUE: Record<ForecastStage, string> = {
  new: 'from-sky-400 to-blue-500',
  outreach: 'from-indigo-400 to-violet-500',
  screening: 'from-violet-400 to-fuchsia-500',
  interview: 'from-amber-400 to-orange-500',
  offer: 'from-emerald-400 to-teal-500',
};

const STAGE_TEXT: Record<ForecastStage, string> = {
  new: 'text-sky-200',
  outreach: 'text-indigo-200',
  screening: 'text-violet-200',
  interview: 'text-amber-200',
  offer: 'text-emerald-200',
};

const STAGE_BORDER: Record<ForecastStage, string> = {
  new: 'border-sky-400/30 bg-sky-400/10',
  outreach: 'border-indigo-400/30 bg-indigo-400/10',
  screening: 'border-violet-400/30 bg-violet-400/10',
  interview: 'border-amber-400/30 bg-amber-400/10',
  offer: 'border-emerald-400/30 bg-emerald-400/10',
};

function bandFromProbability(p: number): { label: string; hue: string; text: string } {
  if (p >= 0.75) return { label: 'On track', hue: 'from-emerald-400 to-teal-400', text: 'text-emerald-100' };
  if (p >= 0.40) return { label: 'Tight',    hue: 'from-amber-400 to-orange-400', text: 'text-amber-100' };
  if (p >= 0.15) return { label: 'At risk',  hue: 'from-orange-400 to-rose-500',  text: 'text-orange-100' };
  return            { label: 'Unlikely', hue: 'from-rose-500 to-rose-700',    text: 'text-rose-100' };
}

function formatDate(iso: string | null): string {
  if (!iso) return '—';
  const [y, m, d] = iso.split('-').map(Number);
  const dt = new Date(Date.UTC(y, (m ?? 1) - 1, d ?? 1));
  return dt.toLocaleDateString(undefined, { day: '2-digit', month: 'short', year: 'numeric' });
}

function pct(n: number): string {
  return `${Math.round(n * 100)}%`;
}

// ---------- subcomponents ----------

function ScoreRing({ value, hue, label, sub }: { value: number; hue: string; label: string; sub?: string }) {
  const deg = Math.round(value * 360);
  return (
    <div className="relative flex items-center justify-center">
      <div
        className="relative grid h-44 w-44 place-items-center rounded-full"
        style={{
          background: `conic-gradient(currentColor 0deg, currentColor ${deg}deg, rgba(255,255,255,0.06) ${deg}deg)`,
        }}
      >
        <div className={`absolute inset-2 rounded-full bg-gradient-to-br ${hue} opacity-20`} />
        <div className="absolute inset-3 rounded-full bg-[#070a14] ring-1 ring-white/10" />
        <div className="relative text-center">
          <div className="text-4xl font-semibold tracking-tight text-white">{pct(value)}</div>
          <div className="mt-1 text-[10px] uppercase tracking-[0.18em] text-white/55">{label}</div>
          {sub && <div className="mt-1 text-[11px] text-white/70">{sub}</div>}
        </div>
      </div>
    </div>
  );
}

function FanChart({ result, targetDate }: { result: ForecastResult; targetDate: string }) {
  const { p10, p50, p90 } = result.hireDate;
  if (!p10 || !p50 || !p90) {
    return (
      <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4 text-sm text-white/60">
        Not enough trials produced a hire to plot a range. Add more candidates or relax the constraints.
      </div>
    );
  }
  const now = result.now;
  const dayMs = 86_400_000;
  const p10Ms = Date.parse(`${p10}T00:00:00Z`);
  const p50Ms = Date.parse(`${p50}T00:00:00Z`);
  const p90Ms = Date.parse(`${p90}T00:00:00Z`);
  const targetMs = Date.parse(`${targetDate}T00:00:00Z`);
  const minMs = Math.min(now, p10Ms);
  const maxMs = Math.max(targetMs, p90Ms) + 7 * dayMs;
  const span = Math.max(1, maxMs - minMs);
  const fracOf = (ms: number) => ((ms - minMs) / span) * 100;
  const fP10 = fracOf(p10Ms);
  const fP50 = fracOf(p50Ms);
  const fP90 = fracOf(p90Ms);
  const fTarget = fracOf(targetMs);
  const fNow = fracOf(now);
  const beforeTarget = p50Ms <= targetMs;
  return (
    <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
      <div className="flex items-baseline justify-between">
        <div className="text-sm font-medium text-white">Earliest-hire date fan</div>
        <div className="text-xs text-white/55">range across {result.trials} trials</div>
      </div>
      <div className="relative mt-5 h-16">
        <div className="absolute left-0 right-0 top-1/2 h-px -translate-y-1/2 bg-white/15" />
        {/* P10 → P90 band */}
        <div
          className="absolute top-1/2 h-3 -translate-y-1/2 rounded-full bg-gradient-to-r from-sky-400/70 via-violet-400/80 to-fuchsia-400/70"
          style={{ left: `${fP10}%`, width: `${Math.max(0.5, fP90 - fP10)}%` }}
        />
        {/* P50 */}
        <div
          className="absolute top-1/2 grid -translate-y-1/2 place-items-center"
          style={{ left: `${fP50}%` }}
        >
          <div className="h-5 w-5 -translate-x-1/2 rounded-full bg-white shadow-[0_0_0_3px_rgba(0,0,0,.6)]" />
        </div>
        {/* Target */}
        <div
          className="absolute -top-1 bottom-0 w-px bg-emerald-300"
          style={{ left: `${fTarget}%` }}
        />
        <div
          className="absolute -top-5 text-[10px] uppercase tracking-[0.12em] text-emerald-200"
          style={{ left: `calc(${fTarget}% + 4px)` }}
        >
          target
        </div>
        {/* Now */}
        <div className="absolute -top-1 bottom-0 w-px bg-white/40" style={{ left: `${fNow}%` }} />
        <div
          className="absolute -top-5 text-[10px] uppercase tracking-[0.12em] text-white/55"
          style={{ left: `calc(${fNow}% + 4px)` }}
        >
          today
        </div>
      </div>
      <div className="mt-3 grid grid-cols-3 gap-3 text-xs">
        <div className="rounded-lg border border-white/10 bg-black/30 px-3 py-2">
          <div className="text-[10px] uppercase tracking-[0.14em] text-white/45">P10 (best case)</div>
          <div className="mt-0.5 text-white">{formatDate(p10)}</div>
        </div>
        <div className="rounded-lg border border-white/10 bg-black/30 px-3 py-2">
          <div className="text-[10px] uppercase tracking-[0.14em] text-white/45">P50 (median)</div>
          <div className={`mt-0.5 ${beforeTarget ? 'text-emerald-200' : 'text-amber-200'}`}>
            {formatDate(p50)}
          </div>
        </div>
        <div className="rounded-lg border border-white/10 bg-black/30 px-3 py-2">
          <div className="text-[10px] uppercase tracking-[0.14em] text-white/45">P90 (worst case)</div>
          <div className="mt-0.5 text-white">{formatDate(p90)}</div>
        </div>
      </div>
    </div>
  );
}

function FunnelCard({ result, bottleneck }: { result: ForecastResult; bottleneck: ForecastStage | null }) {
  const total = result.funnel.reduce((a, b) => a + b.here, 0);
  const expectedAtOffer = result.funnel.find(f => f.key === 'offer')?.expectedHires ?? 0;
  return (
    <section className="rounded-2xl border border-white/10 bg-white/[0.04] p-5">
      <header className="flex items-baseline justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-[0.16em] text-white/70">Pipeline funnel</h2>
        <div className="text-xs text-white/55">
          {total} candidate{total === 1 ? '' : 's'} • expected hires {result.expectedHires.toFixed(2)}
        </div>
      </header>
      <div className="mt-4 grid grid-cols-1 gap-2 md:grid-cols-5">
        {result.funnel.map(stage => {
          const isBottleneck = stage.key === bottleneck;
          const stageTotal = total > 0 ? Math.max(0.04, stage.expectedAdvancers / total) : 0;
          return (
            <div
              key={stage.key}
              className={`relative rounded-xl border p-3 ${STAGE_BORDER[stage.key]} ${
                isBottleneck ? 'ring-2 ring-rose-400/50' : ''
              }`}
            >
              <div className={`text-[10px] font-semibold uppercase tracking-[0.16em] ${STAGE_TEXT[stage.key]}`}>
                {FORECAST_STAGE_LABEL[stage.key]}
                {isBottleneck && (
                  <span className="ml-1 rounded bg-rose-500/30 px-1.5 py-0.5 text-[9px] text-rose-100">
                    cliff
                  </span>
                )}
              </div>
              <div className="mt-2 flex items-baseline gap-2">
                <div className="text-2xl font-semibold text-white">{stage.here}</div>
                <div className="text-[10px] text-white/55">here</div>
              </div>
              <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-black/40">
                <div
                  className={`h-full rounded-full bg-gradient-to-r ${STAGE_HUE[stage.key]}`}
                  style={{ width: `${Math.min(100, stageTotal * 100).toFixed(1)}%` }}
                />
              </div>
              <div className="mt-2 grid grid-cols-2 gap-1 text-[10px] text-white/55">
                <div>
                  <div className="text-white/75">{stage.expectedAdvancers.toFixed(1)}</div>
                  expected
                </div>
                <div>
                  <div className="text-white/75">{stage.expectedHires.toFixed(2)}</div>
                  → hires
                </div>
              </div>
            </div>
          );
        })}
      </div>
      <div className="mt-4 text-xs text-white/60">
        Of {total} candidate{total === 1 ? '' : 's'} in the pipeline today,{' '}
        <span className="text-emerald-200">{expectedAtOffer.toFixed(2)}</span> are expected to
        accept an offer and start.
      </div>
    </section>
  );
}

function TornadoRow({
  label,
  baseline,
  plus,
  minus,
  scale,
}: {
  label: string;
  baseline: number;
  plus: number;
  minus: number;
  scale: number;
}) {
  const half = scale; // half-axis width in pct points
  const plusDelta = plus - baseline;
  const minusDelta = minus - baseline;
  const plusW = Math.min(50, (Math.abs(plusDelta) / half) * 50);
  const minusW = Math.min(50, (Math.abs(minusDelta) / half) * 50);
  const plusRight = plusDelta > 0 ? plusW : -plusW;
  const minusLeft = minusDelta < 0 ? minusW : -minusW;
  return (
    <div>
      <div className="flex items-center justify-between text-[11px]">
        <span className="text-white/80">{label}</span>
        <span className="font-mono text-white/55">
          {plusDelta >= 0 ? '+' : ''}
          {Math.round(plusDelta * 100)} / {minusDelta >= 0 ? '+' : ''}
          {Math.round(minusDelta * 100)} pp
        </span>
      </div>
      <div className="relative mt-1 h-3.5 rounded-md bg-black/30">
        <div className="absolute left-1/2 top-0 h-full w-px bg-white/15" />
        <div
          className="absolute top-0 h-full rounded-l-md bg-gradient-to-l from-rose-400/80 to-rose-500/40"
          style={{
            right: `${50 - Math.max(0, -minusLeft)}%`,
            width: `${Math.max(0, minusLeft >= 0 ? 0 : -minusLeft)}%`,
          }}
        />
        <div
          className="absolute top-0 h-full rounded-r-md bg-gradient-to-r from-emerald-400/80 to-emerald-500/40"
          style={{
            left: '50%',
            width: `${Math.max(0, plusRight)}%`,
          }}
        />
      </div>
    </div>
  );
}

// ---------- page ----------

export default function ForecastStudio() {
  const params = useParams<{ id: string }>();
  const id = params?.id;

  const [role, setRole] = useState<Role | null>(null);
  const [ready, setReady] = useState(false);
  const [now] = useState<number>(() => Date.now());
  const [targetDate, setTargetDate] = useState<string>(() => defaultTargetDate());
  const [conversion, setConversion] = useState<ConversionMap>({ ...DEFAULT_ASSUMPTIONS.conversion });
  const [velocity, setVelocity] = useState<VelocityMap>({ ...DEFAULT_ASSUMPTIONS.velocity });
  const [notice, setNotice] = useState<number>(DEFAULT_ASSUMPTIONS.noticePeriodDays);
  const [funnelBoost, setFunnelBoost] = useState<Record<ForecastStage, number>>({
    new: 0, outreach: 0, screening: 0, interview: 0, offer: 0,
  });

  useEffect(() => {
    if (!id) return;
    setRole(getRole(id));
    setReady(true);
  }, [id]);

  const baseFunnel = useMemo(() => {
    if (!role) return null;
    return funnelFromRole(role);
  }, [role]);

  const effectiveFunnel = useMemo(() => {
    if (!baseFunnel) return null;
    const out = { ...baseFunnel };
    for (const k of FORECAST_PROGRESSION) {
      out[k] = Math.max(0, (out[k] | 0) + (funnelBoost[k] | 0));
    }
    return out;
  }, [baseFunnel, funnelBoost]);

  const result: ForecastResult | null = useMemo(() => {
    if (!effectiveFunnel) return null;
    return forecastFunnel({
      funnel: effectiveFunnel,
      targetDate,
      now,
      assumptions: {
        conversion,
        velocity,
        noticePeriodDays: notice,
        durationSigma: DEFAULT_ASSUMPTIONS.durationSigma,
      },
      trials: 3000,
    });
  }, [effectiveFunnel, targetDate, now, conversion, velocity, notice]);

  // Quick fast-estimate that reacts to slider drag for the live overlay.
  const quickP = useMemo(() => {
    if (!effectiveFunnel) return 0;
    return quickProbabilityEstimate(effectiveFunnel, targetDate, now, {
      conversion, velocity, noticePeriodDays: notice,
    });
  }, [effectiveFunnel, targetDate, now, conversion, velocity, notice]);

  // ---------- render guards ----------

  if (!ready) {
    return <div className="min-h-screen bg-[#070a14] p-10 text-white/60">Loading…</div>;
  }
  if (!role) {
    return (
      <div className="min-h-screen bg-[#070a14] p-10 text-center text-white/70">
        Role not found.{' '}
        <Link href="/roles" className="text-violet-300 underline">
          Back to roles
        </Link>
      </div>
    );
  }
  if (!result || !effectiveFunnel) return null;

  const band = bandFromProbability(result.probabilityByTarget);
  const totalCand = FORECAST_PROGRESSION.reduce((s, k) => s + effectiveFunnel[k], 0);
  const sensitivityScale = Math.max(
    0.1,
    ...result.sensitivity.map(r =>
      Math.max(Math.abs(r.upliftPlus - r.baseline), Math.abs(r.baseline - r.upliftMinus)),
    ),
  );

  return (
    <div className="min-h-screen bg-[#070a14] text-white">
      <div className="mx-auto max-w-7xl px-6 py-10">
        {/* nav */}
        <nav className="flex flex-wrap items-center gap-2 text-xs text-white/55">
          <Link href="/roles" className="hover:text-white">Roles</Link>
          <span>/</span>
          <Link href={`/roles/${role.id}`} className="hover:text-white">{role.name}</Link>
          <span>/</span>
          <span className="text-white/80">Forecast</span>
        </nav>

        {/* header */}
        <header className="mt-4 flex flex-wrap items-end justify-between gap-4">
          <div>
            <h1 className="text-3xl font-semibold tracking-tight md:text-4xl">Forecast Studio</h1>
            <p className="mt-2 max-w-2xl text-sm text-white/70">
              Monte-Carlo simulator over your funnel. Will you hit the start date? Where&apos;s the
              dropout cliff? Which lever moves the dial the most? Pull a slider — the curves
              re-draw live.
            </p>
          </div>
          <div className="flex items-center gap-3">
            <label className="rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-xs">
              <div className="text-[10px] uppercase tracking-[0.16em] text-white/55">Target start</div>
              <input
                type="date"
                value={targetDate}
                onChange={e => setTargetDate(e.target.value)}
                className="mt-0.5 bg-transparent text-sm text-white outline-none"
              />
            </label>
            <Link
              href={`/roles/${role.id}`}
              className="rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-xs text-white hover:bg-white/10"
            >
              ← Back to role
            </Link>
          </div>
        </header>

        {/* hero */}
        <section className="mt-8 grid grid-cols-1 gap-4 lg:grid-cols-3">
          <div className={`relative overflow-hidden rounded-2xl border border-white/10 p-6 lg:col-span-1`}>
            <div className={`absolute inset-0 bg-gradient-to-br ${band.hue} opacity-10`} />
            <div className="relative">
              <div className="text-[10px] uppercase tracking-[0.18em] text-white/55">
                P(hire by {formatDate(targetDate)})
              </div>
              <div className="mt-5 flex items-center gap-5">
                <div className={band.text}>
                  <ScoreRing
                    value={result.probabilityByTarget}
                    hue={band.hue}
                    label={band.label}
                  />
                </div>
                <div className="space-y-2 text-sm">
                  <div>
                    <div className="text-[10px] uppercase tracking-[0.14em] text-white/45">Any hire ever</div>
                    <div className="text-base text-white">{pct(result.hireDate.anyHireProbability)}</div>
                  </div>
                  <div>
                    <div className="text-[10px] uppercase tracking-[0.14em] text-white/45">Median hire date</div>
                    <div className="text-base text-white">{formatDate(result.hireDate.p50)}</div>
                  </div>
                  <div>
                    <div className="text-[10px] uppercase tracking-[0.14em] text-white/45">Expected hires / trial</div>
                    <div className="text-base text-white">{result.expectedHires.toFixed(2)}</div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div className="lg:col-span-2">
            <FanChart result={result} targetDate={targetDate} />
            <div className="mt-3 flex items-center justify-between text-xs text-white/55">
              <span>
                Quick estimate (closed-form):{' '}
                <span className="font-mono text-white/80">{pct(quickP)}</span> — used while you
                drag, replaced by the Monte-Carlo result above.
              </span>
              <span>{totalCand} candidate{totalCand === 1 ? '' : 's'} in pipeline</span>
            </div>
          </div>
        </section>

        {/* funnel */}
        <div className="mt-6">
          <FunnelCard result={result} bottleneck={result.bottleneck} />
        </div>

        {/* what-if + sensitivity */}
        <div className="mt-6 grid grid-cols-1 gap-4 lg:grid-cols-2">
          {/* What-if levers */}
          <section className="rounded-2xl border border-white/10 bg-white/[0.04] p-5">
            <header className="flex items-baseline justify-between">
              <h2 className="text-sm font-semibold uppercase tracking-[0.16em] text-white/70">What-if levers</h2>
              <button
                onClick={() => {
                  setConversion({ ...DEFAULT_ASSUMPTIONS.conversion });
                  setVelocity({ ...DEFAULT_ASSUMPTIONS.velocity });
                  setNotice(DEFAULT_ASSUMPTIONS.noticePeriodDays);
                  setFunnelBoost({ new: 0, outreach: 0, screening: 0, interview: 0, offer: 0 });
                }}
                className="rounded-md border border-white/10 bg-white/5 px-2 py-1 text-[11px] text-white/70 hover:bg-white/10"
              >
                Reset
              </button>
            </header>

            <div className="mt-4 space-y-4">
              {FORECAST_PROGRESSION.map(stage => (
                <div key={stage} className="rounded-xl border border-white/10 bg-black/20 p-3">
                  <div className="flex items-baseline justify-between">
                    <div className={`text-[11px] font-semibold uppercase tracking-[0.14em] ${STAGE_TEXT[stage]}`}>
                      {FORECAST_STAGE_LABEL[stage]}
                    </div>
                    <div className="font-mono text-[10px] text-white/55">
                      {pct(conversion[stage])} • {velocity[stage].toFixed(1)} d
                      {(funnelBoost[stage] | 0) !== 0 && (
                        <span className="ml-1 text-violet-200">
                          {funnelBoost[stage] > 0 ? '+' : ''}{funnelBoost[stage]} cand
                        </span>
                      )}
                    </div>
                  </div>
                  <div className="mt-2 grid grid-cols-2 gap-3 text-[10px]">
                    <label className="block">
                      <div className="text-white/55">Conversion</div>
                      <input
                        type="range"
                        min={0} max={1} step={0.01}
                        value={conversion[stage]}
                        onChange={e => setConversion({ ...conversion, [stage]: parseFloat(e.target.value) })}
                        className="w-full accent-violet-400"
                      />
                    </label>
                    <label className="block">
                      <div className="text-white/55">Days (median)</div>
                      <input
                        type="range"
                        min={1} max={30} step={0.5}
                        value={velocity[stage]}
                        onChange={e => setVelocity({ ...velocity, [stage]: parseFloat(e.target.value) })}
                        className="w-full accent-sky-400"
                      />
                    </label>
                  </div>
                  {(stage === 'new' || stage === 'outreach') && (
                    <div className="mt-2 flex items-center gap-2 text-[10px]">
                      <span className="text-white/55">Inject candidates</span>
                      <button
                        onClick={() => setFunnelBoost({ ...funnelBoost, [stage]: (funnelBoost[stage] | 0) - 1 })}
                        className="rounded border border-white/10 bg-white/5 px-2 py-0.5 text-white/80 hover:bg-white/10"
                      >−</button>
                      <span className="w-8 text-center font-mono text-white">
                        {funnelBoost[stage] > 0 ? '+' : ''}{funnelBoost[stage]}
                      </span>
                      <button
                        onClick={() => setFunnelBoost({ ...funnelBoost, [stage]: (funnelBoost[stage] | 0) + 1 })}
                        className="rounded border border-white/10 bg-white/5 px-2 py-0.5 text-white/80 hover:bg-white/10"
                      >+</button>
                    </div>
                  )}
                </div>
              ))}

              <div className="rounded-xl border border-white/10 bg-black/20 p-3">
                <div className="flex items-baseline justify-between">
                  <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-white/75">
                    Notice period
                  </div>
                  <div className="font-mono text-[10px] text-white/55">{notice.toFixed(0)} d</div>
                </div>
                <input
                  type="range"
                  min={0} max={90} step={1}
                  value={notice}
                  onChange={e => setNotice(parseInt(e.target.value))}
                  className="mt-2 w-full accent-fuchsia-400"
                />
              </div>
            </div>
          </section>

          {/* Tornado */}
          <section className="rounded-2xl border border-white/10 bg-white/[0.04] p-5">
            <header className="flex items-baseline justify-between">
              <h2 className="text-sm font-semibold uppercase tracking-[0.16em] text-white/70">Sensitivity tornado</h2>
              <div className="text-[10px] uppercase tracking-[0.14em] text-white/45">
                P(hire-by-target) swing
              </div>
            </header>
            <div className="mt-4 space-y-3">
              {result.sensitivity.slice(0, 9).map((row, i) => (
                <TornadoRow
                  key={i}
                  label={row.label}
                  baseline={row.baseline}
                  plus={row.upliftPlus}
                  minus={row.upliftMinus}
                  scale={sensitivityScale}
                />
              ))}
            </div>
            <div className="mt-4 flex items-center gap-4 text-[10px] text-white/55">
              <span className="flex items-center gap-1">
                <span className="inline-block h-2 w-2 rounded bg-emerald-400" /> favourable nudge
              </span>
              <span className="flex items-center gap-1">
                <span className="inline-block h-2 w-2 rounded bg-rose-400" /> adverse nudge
              </span>
            </div>
          </section>
        </div>

        {/* Recommendations */}
        <section className="mt-6 rounded-2xl border border-violet-400/30 bg-gradient-to-br from-violet-500/15 to-fuchsia-500/10 p-5">
          <h2 className="text-sm font-semibold uppercase tracking-[0.16em] text-violet-100">
            Action recommendations
          </h2>
          <ul className="mt-3 space-y-2 text-sm text-white/85">
            {result.recommendations.map((r, i) => (
              <li key={i} className="flex gap-2">
                <span className="mt-1 inline-block h-1.5 w-1.5 flex-shrink-0 rounded-full bg-violet-300" />
                <span>{r}</span>
              </li>
            ))}
          </ul>
        </section>

        {/* Assumptions footer */}
        <details className="mt-6 rounded-2xl border border-white/10 bg-white/[0.03] p-4 text-xs text-white/65">
          <summary className="cursor-pointer text-white/85">How the forecast is computed</summary>
          <p className="mt-3">
            For every candidate at every stage of the funnel, the engine simulates a forward
            walk through Outreach → Screening → Interview → Offer → Accept. Each transition has
            a Bernoulli outcome (the conversion slider) and a LogNormal-distributed duration
            (the days slider, with σ = {DEFAULT_ASSUMPTIONS.durationSigma}). A trial that
            produces at least one accepted offer yields an earliest-hire date equal to the
            offer-accept timestamp plus the notice period. {result.trials.toLocaleString()} trials
            are drawn from a deterministic seed of your funnel shape so the numbers don&apos;t
            jitter on re-render.
          </p>
          <p className="mt-2">
            The bottleneck is the stage whose <em>expected reach × (1 − conversion)</em> is the
            highest — i.e. the stage where the largest absolute number of candidates die. The
            sensitivity tornado rerolls the MC at conversion ± 15pp and velocity ± 30% per stage,
            plus an &ldquo;add 5 candidates&rdquo; lever at the top of the funnel, and ranks levers by total
            swing in P(hire-by-target).
          </p>
        </details>
      </div>
    </div>
  );
}
