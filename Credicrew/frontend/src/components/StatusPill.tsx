'use client';
import type { PipelineStatus } from '@/lib/roles';
import { STATUSES, STATUS_LABEL, STATUS_TONE } from '@/lib/roles';

const TONE: Record<string, string> = {
  sky: 'border-sky-400/30 bg-sky-400/10 text-sky-200',
  indigo: 'border-indigo-400/30 bg-indigo-400/10 text-indigo-200',
  violet: 'border-violet-400/30 bg-violet-400/10 text-violet-200',
  amber: 'border-amber-400/30 bg-amber-400/10 text-amber-200',
  emerald: 'border-emerald-400/30 bg-emerald-400/10 text-emerald-200',
  rose: 'border-rose-400/30 bg-rose-400/10 text-rose-200',
};

export function StatusPill({ status }: { status: PipelineStatus }) {
  const tone = TONE[STATUS_TONE[status]];
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider ${tone}`}>
      <span className="h-1.5 w-1.5 rounded-full bg-current" />
      {STATUS_LABEL[status]}
    </span>
  );
}

export function StatusSelect({
  status,
  onChange,
  className = '',
}: {
  status: PipelineStatus;
  onChange: (next: PipelineStatus) => void;
  className?: string;
}) {
  const tone = TONE[STATUS_TONE[status]];
  return (
    <select
      value={status}
      onChange={e => onChange(e.target.value as PipelineStatus)}
      className={`rounded-md border bg-transparent px-2 py-1 text-[11px] font-medium uppercase tracking-wider focus:outline-none ${tone} ${className}`}
    >
      {STATUSES.map(s => (
        <option key={s} value={s} className="bg-neutral-900 text-white">
          {STATUS_LABEL[s]}
        </option>
      ))}
    </select>
  );
}
