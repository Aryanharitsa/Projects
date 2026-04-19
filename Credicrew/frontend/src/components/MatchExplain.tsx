'use client';
import { useState } from 'react';
import type { MatchResult } from '@/lib/match';

export default function MatchExplain({ result }: { result: MatchResult }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="relative">
      <button
        onClick={() => setOpen(v => !v)}
        className="text-[11px] uppercase tracking-wider text-indigo-300 hover:text-indigo-200"
        aria-expanded={open}
      >
        {open ? 'hide why' : 'why this match?'}
      </button>
      {open && (
        <div className="absolute right-0 z-20 mt-2 w-72 rounded-xl border border-white/10 bg-neutral-900/95 p-3 shadow-xl backdrop-blur">
          <div className="mb-2 text-[11px] uppercase tracking-wider text-white/50">
            Score breakdown
          </div>
          <ul className="space-y-1.5">
            {result.factors.map(f => (
              <li
                key={f.key + f.label}
                className="flex items-center justify-between gap-2 border-b border-white/5 pb-1.5 last:border-b-0 last:pb-0"
              >
                <span className="text-xs text-white/80">{f.label}</span>
                <span
                  className={`text-xs font-semibold ${
                    f.impact > 0 ? 'text-emerald-300' : 'text-white/40'
                  }`}
                >
                  +{f.impact}
                </span>
              </li>
            ))}
          </ul>
          {result.missingSkills.length > 0 && (
            <div className="mt-3">
              <div className="mb-1 text-[11px] uppercase tracking-wider text-rose-300/80">
                Missing
              </div>
              <div className="flex flex-wrap gap-1">
                {result.missingSkills.map(s => (
                  <span
                    key={s}
                    className="rounded-md bg-rose-500/15 px-1.5 py-0.5 text-[11px] text-rose-200"
                  >
                    {s}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
