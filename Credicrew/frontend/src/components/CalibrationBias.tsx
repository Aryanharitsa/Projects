'use client';

import {
  RATER_FLAG_LABEL,
  RATER_FLAG_TONE,
  type RaterStat,
} from '@/lib/calibration';

const TONE_PILL: Record<string, string> = {
  rose: 'border-rose-400/30 bg-rose-400/10 text-rose-200',
  amber: 'border-amber-400/30 bg-amber-400/10 text-amber-200',
  sky: 'border-sky-400/30 bg-sky-400/10 text-sky-200',
  violet: 'border-violet-400/30 bg-violet-400/10 text-violet-200',
  slate: 'border-white/15 bg-white/5 text-white/60',
};

// Leniency axis runs ±1.5 rating points; clamp the bar to that.
const AXIS = 1.5;

export default function CalibrationBias({ raters }: { raters: RaterStat[] }) {
  if (raters.length === 0) {
    return (
      <div className="rounded-2xl border border-dashed border-white/10 bg-white/[0.02] p-6 text-center text-sm text-white/55">
        No interviewers yet — add a panel to measure rater bias.
      </div>
    );
  }
  return (
    <div className="cc-cal-bias rounded-2xl border border-white/10 bg-white/[0.03] p-4">
      <div className="mb-3 flex items-center justify-between text-[11px] uppercase tracking-wider">
        <span className="text-rose-300/80">← Severe</span>
        <span className="text-white/45">Leniency vs. consensus</span>
        <span className="text-amber-300/80">Lenient →</span>
      </div>
      <div className="space-y-2.5">
        {raters.map(r => {
          const frac = Math.max(-1, Math.min(1, r.leniency / AXIS));
          const widthPct = Math.abs(frac) * 50;
          const positive = r.leniency >= 0;
          const barColor = positive
            ? 'linear-gradient(90deg, rgba(251,191,36,0.25), rgba(251,191,36,0.85))'
            : 'linear-gradient(270deg, rgba(244,63,94,0.25), rgba(244,63,94,0.85))';
          return (
            <div key={r.interviewerId} className="cc-cal-row rounded-xl border border-white/5 bg-white/[0.02] p-2.5">
              <div className="flex items-center justify-between gap-2">
                <div className="min-w-0">
                  <span className="text-sm font-medium text-white">{r.name}</span>
                  {r.title && (
                    <span className="ml-2 text-[11px] text-white/45">{r.title}</span>
                  )}
                </div>
                <div className="flex shrink-0 items-center gap-1.5">
                  {r.flags.length === 0 ? (
                    <span className="rounded-full border border-emerald-400/30 bg-emerald-400/10 px-2 py-0.5 text-[10px] text-emerald-200">
                      Calibrated
                    </span>
                  ) : (
                    r.flags.map(f => (
                      <span
                        key={f}
                        className={`rounded-full border px-2 py-0.5 text-[10px] font-medium ${TONE_PILL[RATER_FLAG_TONE[f]]}`}
                      >
                        {RATER_FLAG_LABEL[f]}
                      </span>
                    ))
                  )}
                </div>
              </div>

              {/* diverging bar */}
              <div className="relative mt-2 h-3 w-full">
                <div className="absolute inset-0 rounded-full bg-white/[0.04]" />
                {/* center tick */}
                <div className="absolute left-1/2 top-[-2px] h-[16px] w-px -translate-x-1/2 bg-white/25" />
                <div
                  className="absolute top-0 h-3 rounded-full"
                  style={{
                    width: `${widthPct}%`,
                    left: positive ? '50%' : `${50 - widthPct}%`,
                    background: barColor,
                  }}
                />
              </div>

              <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[10px] text-white/55">
                <span>
                  leniency{' '}
                  <span className={`font-mono ${positive ? 'text-amber-200' : 'text-rose-200'}`}>
                    {positive ? '+' : ''}{r.leniency.toFixed(2)}
                  </span>
                </span>
                <span>spread <span className="font-mono text-white/75">{r.spread.toFixed(2)}</span></span>
                <span>
                  consensus r{' '}
                  <span className="font-mono text-white/75">
                    {r.consensusCorr === null ? '—' : r.consensusCorr.toFixed(2)}
                  </span>
                </span>
                <span className="text-white/35">{r.count} ratings</span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
