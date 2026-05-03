'use client';
import { useState } from 'react';
import type { Question } from '@/lib/interview';

const DIFF_LABEL: Record<number, string> = {
  1: 'warm-up',
  2: 'mid',
  3: 'deep',
  4: 'stretch',
};

const DIFF_TONE: Record<number, string> = {
  1: 'border-sky-400/30 bg-sky-400/10 text-sky-200',
  2: 'border-emerald-400/30 bg-emerald-400/10 text-emerald-200',
  3: 'border-amber-400/30 bg-amber-400/10 text-amber-200',
  4: 'border-rose-400/30 bg-rose-400/10 text-rose-200',
};

export default function QuestionCard({ q }: { q: Question }) {
  const [open, setOpen] = useState(false);
  const sourceLabel = q.source === 'universal' ? 'Universal' : q.source;
  return (
    <div className="rounded-xl border border-white/10 bg-white/[0.025] p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <p className="text-sm leading-relaxed text-white/90">{q.prompt}</p>
          <div className="mt-2 flex flex-wrap items-center gap-1.5 text-[10px]">
            <span className={`rounded-full border px-1.5 py-0.5 uppercase tracking-wider ${DIFF_TONE[q.difficulty]}`}>
              {DIFF_LABEL[q.difficulty]}
            </span>
            <span className="rounded-full border border-white/10 bg-white/5 px-1.5 py-0.5 text-white/60">
              probes · {q.signal.replace(/_/g, ' ')}
            </span>
            <span className="rounded-full border border-white/10 bg-white/5 px-1.5 py-0.5 text-white/45">
              {sourceLabel}
            </span>
          </div>
        </div>
        {q.followups.length > 0 && (
          <button
            onClick={() => setOpen(v => !v)}
            className="shrink-0 rounded-md border border-white/10 bg-white/5 px-2 py-1 text-[11px] text-white/70 hover:bg-white/10"
            aria-expanded={open}
          >
            {open ? 'hide' : `+${q.followups.length} follow-up${q.followups.length === 1 ? '' : 's'}`}
          </button>
        )}
      </div>
      {open && q.followups.length > 0 && (
        <ul className="mt-3 space-y-1.5 border-l-2 border-indigo-400/30 pl-3">
          {q.followups.map((f, i) => (
            <li key={i} className="text-xs text-white/65">
              ↳ {f}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
