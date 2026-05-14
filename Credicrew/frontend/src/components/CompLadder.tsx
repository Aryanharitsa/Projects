// Vertical compensation ladder. Shows P25 → P90 as a coloured stack with
// the current offer's base salary as a marker that snaps to its band position.
//
// Designed to read at a glance: tick labels on the right, band tint behind,
// "you are here" badge floating against the marker.

'use client';

import { bandPosition, type CompBenchmark, type OfferDraft } from '@/lib/offer';

function fmtINR(n: number): string {
  // Indian numbering ("1,23,456")
  const s = String(Math.round(n));
  if (s.length <= 3) return s;
  const head = s.slice(0, -3);
  const tail = s.slice(-3);
  const pairs: string[] = [];
  let h = head;
  while (h.length > 2) {
    pairs.unshift(h.slice(-2));
    h = h.slice(0, -2);
  }
  if (h) pairs.unshift(h);
  return `${pairs.join(',')},${tail}`;
}

export function fmtMoney(n: number, unit: 'LPA' | 'annual', currency: 'INR' | 'USD'): string {
  if (currency === 'USD') {
    return `$${Math.round(n).toLocaleString('en-US')}${unit === 'annual' ? ' /yr' : ' LPA'}`;
  }
  return unit === 'LPA' ? `₹${fmtINR(n)} LPA` : `₹${fmtINR(n)} /yr`;
}

const TICKS: ReadonlyArray<{ key: 'p25' | 'p50' | 'p75' | 'p90'; label: string; tone: string }> = [
  { key: 'p90', label: 'P90 · top tail', tone: '#34d399' },
  { key: 'p75', label: 'P75 · top quartile', tone: '#a78bfa' },
  { key: 'p50', label: 'P50 · market', tone: '#818cf8' },
  { key: 'p25', label: 'P25 · entry', tone: '#fb7185' },
];

export default function CompLadder({
  benchmark, offer,
}: { benchmark: CompBenchmark; offer: OfferDraft }) {
  const pos = bandPosition(offer, benchmark);
  // map [0,1] of (P25..P90) → bottom-up vertical %. Clip 0..100 for the marker.
  const yPct = Math.max(0, Math.min(100, pos * 100));

  return (
    <div className="cc-ladder rounded-2xl border border-white/10 bg-white/[0.03] p-4">
      <div className="flex items-baseline justify-between">
        <div>
          <div className="text-[10px] uppercase tracking-wider text-white/45">
            Compensation band
          </div>
          <div className="text-base font-semibold text-white">
            {benchmark.seniority} · {benchmark.location}
          </div>
        </div>
        <div className="text-right">
          <div className="text-[10px] uppercase tracking-wider text-white/45">
            Your offer
          </div>
          <div
            className="text-base font-semibold"
            style={{ color: pos < 0.25 ? '#fb7185' : pos > 0.85 ? '#34d399' : '#a78bfa' }}
          >
            {fmtMoney(offer.base, benchmark.base.unit, benchmark.base.currency)}
          </div>
        </div>
      </div>

      <div className="mt-4 flex">
        {/* Bar */}
        <div className="relative h-64 w-12 shrink-0">
          {/* gradient track */}
          <div
            className="absolute inset-0 rounded-full"
            style={{
              background:
                'linear-gradient(to top, rgba(244,63,94,0.25), rgba(129,140,248,0.30) 40%, rgba(167,139,250,0.30) 70%, rgba(52,211,153,0.40))',
            }}
          />
          {/* tick lines */}
          {TICKS.map(t => {
            const v = benchmark.base[t.key];
            const span = benchmark.base.p90 - benchmark.base.p25;
            const y = span > 0 ? ((v - benchmark.base.p25) / span) * 100 : 50;
            return (
              <div
                key={t.key}
                className="absolute left-0 right-0 border-t border-white/10"
                style={{ bottom: `${y}%` }}
              />
            );
          })}
          {/* offer marker */}
          <div
            className="absolute -left-1.5 -right-1.5 flex items-center"
            style={{ bottom: `calc(${yPct}% - 8px)` }}
          >
            <div
              className="h-4 w-full rounded-full shadow-[0_0_18px_rgba(167,139,250,0.55)]"
              style={{
                background:
                  pos < 0 ? '#f43f5e' : pos > 1 ? '#34d399' : '#a78bfa',
                outline: '2px solid rgba(11,11,18,0.85)',
              }}
            />
          </div>
        </div>

        {/* Tick labels + values */}
        <div className="relative ml-3 grow">
          <div className="absolute inset-y-0 left-0 right-0">
            {TICKS.map(t => {
              const v = benchmark.base[t.key];
              const span = benchmark.base.p90 - benchmark.base.p25;
              const y = span > 0 ? ((v - benchmark.base.p25) / span) * 100 : 50;
              return (
                <div
                  key={t.key}
                  className="absolute flex w-full items-center justify-between"
                  style={{ bottom: `calc(${y}% - 9px)` }}
                >
                  <div className="flex items-center gap-2">
                    <span className="h-1.5 w-1.5 rounded-full" style={{ background: t.tone }} />
                    <span className="text-[11px] text-white/70">{t.label}</span>
                  </div>
                  <span className="font-mono text-[11px] text-white">
                    {fmtMoney(v, benchmark.base.unit, benchmark.base.currency)}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      <div className="mt-4 grid grid-cols-3 gap-2 text-[11px]">
        <Pill label="Equity P50" value={`${benchmark.equity.pct_p50.toFixed(2)}%`} tone="violet" />
        <Pill label="Target bonus" value={`${benchmark.targetBonusPct.toFixed(0)}%`} tone="indigo" />
        <Pill
          label="Sign-on hint"
          value={fmtMoney(benchmark.signOnSuggested, benchmark.base.unit, benchmark.base.currency)}
          tone="teal"
        />
      </div>

      <ul className="mt-3 space-y-1 text-[11px] text-white/55">
        {benchmark.rationale.map((r, i) => (
          <li key={i}>• {r}</li>
        ))}
      </ul>
    </div>
  );
}

function Pill({ label, value, tone }: { label: string; value: string; tone: string }) {
  const cls: Record<string, string> = {
    violet: 'border-violet-400/30 bg-violet-400/10 text-violet-200',
    indigo: 'border-indigo-400/30 bg-indigo-400/10 text-indigo-200',
    teal: 'border-teal-400/30 bg-teal-400/10 text-teal-200',
  };
  return (
    <div className={`rounded-lg border ${cls[tone] ?? cls.violet} px-2 py-1.5`}>
      <div className="text-[9px] uppercase tracking-wider opacity-70">{label}</div>
      <div className="mt-0.5 font-mono text-[12px]">{value}</div>
    </div>
  );
}
