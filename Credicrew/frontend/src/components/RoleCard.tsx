'use client';
import Link from 'next/link';
import type { Role } from '@/lib/roles';
import { STATUS_TONE, STATUSES, countByStatus } from '@/lib/roles';

const TONE_BG: Record<string, string> = {
  sky: 'bg-sky-400',
  indigo: 'bg-indigo-400',
  violet: 'bg-violet-400',
  amber: 'bg-amber-400',
  emerald: 'bg-emerald-400',
  rose: 'bg-rose-400',
};

function timeAgo(ts: number): string {
  const s = Math.max(1, Math.floor((Date.now() - ts) / 1000));
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.floor(h / 24);
  return `${d}d ago`;
}

export default function RoleCard({ role }: { role: Role }) {
  const total = role.shortlist.length;
  const counts = countByStatus(role);

  return (
    <Link
      href={`/roles/${role.id}`}
      className="group block rounded-2xl border border-white/10 bg-white/[0.04] p-5 shadow-sm transition hover:border-white/20 hover:bg-white/[0.06]"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="truncate text-base font-semibold text-white">
            {role.name}
          </div>
          <div className="mt-0.5 text-xs text-white/50">
            Updated {timeAgo(role.updatedAt)} · {total} shortlisted
          </div>
        </div>
        <div className="text-[10px] uppercase tracking-wider text-white/40 transition group-hover:text-indigo-300">
          Open →
        </div>
      </div>

      {(role.plan.skills.length > 0 || role.plan.location || role.plan.seniority) && (
        <div className="mt-3 flex flex-wrap gap-1">
          {role.plan.seniority && (
            <span className="rounded-full border border-indigo-400/30 bg-indigo-400/10 px-2 py-0.5 text-[10px] text-indigo-200">
              {role.plan.seniority}
            </span>
          )}
          {role.plan.skills.slice(0, 5).map(s => (
            <span
              key={s}
              className="rounded-full border border-emerald-400/30 bg-emerald-400/10 px-2 py-0.5 text-[10px] text-emerald-200"
            >
              {s}
            </span>
          ))}
          {role.plan.skills.length > 5 && (
            <span className="rounded-full border border-white/10 bg-white/5 px-2 py-0.5 text-[10px] text-white/60">
              +{role.plan.skills.length - 5}
            </span>
          )}
          {role.plan.location && (
            <span className="rounded-full border border-amber-400/30 bg-amber-400/10 px-2 py-0.5 text-[10px] text-amber-200">
              📍 {role.plan.location}
            </span>
          )}
        </div>
      )}

      {/* Pipeline strip */}
      <div className="mt-4">
        <div className="flex h-1.5 w-full overflow-hidden rounded-full bg-white/5">
          {STATUSES.map(s => {
            const n = counts[s];
            const pct = total ? (n / total) * 100 : 0;
            if (pct === 0) return null;
            return (
              <div
                key={s}
                className={TONE_BG[STATUS_TONE[s]]}
                style={{ width: `${pct}%` }}
                title={`${s}: ${n}`}
              />
            );
          })}
        </div>
        <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[10px] text-white/50">
          {STATUSES.map(s =>
            counts[s] ? (
              <span key={s} className="inline-flex items-center gap-1">
                <span className={`h-1.5 w-1.5 rounded-full ${TONE_BG[STATUS_TONE[s]]}`} />
                {counts[s]} {s}
              </span>
            ) : null,
          )}
          {total === 0 && (
            <span className="text-white/40">No candidates shortlisted yet.</span>
          )}
        </div>
      </div>
    </Link>
  );
}
