'use client';

import { useMemo } from 'react';
import type { Role, ShortlistEntry, PipelineStatus } from '@/lib/roles';
import { STATUSES, STATUS_LABEL, STATUS_TONE, countByStatus } from '@/lib/roles';

const TONE_BG: Record<string, string> = {
  sky: 'bg-sky-400',
  indigo: 'bg-indigo-400',
  violet: 'bg-violet-400',
  amber: 'bg-amber-400',
  emerald: 'bg-emerald-400',
  rose: 'bg-rose-400',
};

const TONE_TEXT: Record<string, string> = {
  sky: 'text-sky-200',
  indigo: 'text-indigo-200',
  violet: 'text-violet-200',
  amber: 'text-amber-200',
  emerald: 'text-emerald-200',
  rose: 'text-rose-200',
};

type Props = {
  role: Role;
};

const STAGE_FORWARD: PipelineStatus[] = [
  'new', 'outreach', 'screening', 'interview', 'offer',
];

function ago(ms: number): string {
  const dt = Date.now() - ms;
  const days = Math.floor(dt / 86_400_000);
  if (days <= 0) return 'today';
  if (days === 1) return '1 day';
  if (days < 30) return `${days} days`;
  const months = Math.floor(days / 30);
  return months === 1 ? '1 month' : `${months} months`;
}

export default function PipelineAnalytics({ role }: Props) {
  const counts = countByStatus(role);
  const total = role.shortlist.length;

  // Funnel widths: monotonically nonincreasing — at any stage we show the
  // count of candidates that reached *at least* that stage. That's a more
  // honest funnel than per-stage counts (which double-count nothing).
  const funnel = useMemo(() => {
    const reached: Record<PipelineStatus, number> = {
      new: 0, outreach: 0, screening: 0, interview: 0, offer: 0, passed: 0,
    };
    for (const e of role.shortlist) {
      const idx = STAGE_FORWARD.indexOf(e.status);
      if (idx < 0) continue; // 'passed' is a terminal off-track state
      for (let i = 0; i <= idx; i += 1) reached[STAGE_FORWARD[i]] += 1;
    }
    return STAGE_FORWARD.map(s => ({
      status: s,
      reached: reached[s],
      pct: total > 0 ? reached[s] / total : 0,
    }));
  }, [role.shortlist, total]);

  // Conversion rates between adjacent stages.
  const conversions = useMemo(() => {
    const out: { from: PipelineStatus; to: PipelineStatus; rate: number; note: string }[] = [];
    for (let i = 0; i < STAGE_FORWARD.length - 1; i += 1) {
      const from = STAGE_FORWARD[i];
      const to = STAGE_FORWARD[i + 1];
      const numFrom = funnel[i].reached;
      const numTo = funnel[i + 1].reached;
      const rate = numFrom > 0 ? numTo / numFrom : 0;
      out.push({
        from,
        to,
        rate,
        note: numFrom === 0
          ? '—'
          : `${numTo}/${numFrom}`,
      });
    }
    return out;
  }, [funnel]);

  // Stale candidates: in_progress stages with addedAt > 14 days ago.
  const stale = useMemo(() => {
    const cutoff = 14 * 86_400_000;
    return role.shortlist
      .filter((e: ShortlistEntry) =>
        e.status !== 'offer' && e.status !== 'passed' && Date.now() - e.addedAt > cutoff,
      )
      .sort((a, b) => a.addedAt - b.addedAt)
      .slice(0, 5);
  }, [role.shortlist]);

  if (total === 0) {
    return (
      <div className="cc-empty rounded-2xl border border-dashed border-white/10 bg-white/[0.02] p-6 text-center text-sm text-white/55">
        No shortlist activity yet. Add candidates from the role&apos;s Matches tab to populate the funnel.
      </div>
    );
  }

  return (
    <div className="cc-funnel space-y-4 rounded-2xl border border-white/10 bg-white/[0.04] p-5">
      <div className="flex items-baseline justify-between">
        <div>
          <div className="text-[10px] uppercase tracking-wider text-white/45">
            Pipeline funnel
          </div>
          <div className="text-base font-semibold text-white">
            {total} shortlisted · {counts.passed} passed · {counts.offer} offer
          </div>
        </div>
        <div className="text-[11px] text-white/45">
          Reached-at-least funnel · conversion rates between adjacent stages
        </div>
      </div>

      <div className="space-y-1.5">
        {funnel.map((row, i) => {
          const tone = STATUS_TONE[row.status];
          return (
            <div
              key={row.status}
              className="cc-funnel-row flex items-center gap-3"
              title={`${row.reached} of ${total} reached at least ${STATUS_LABEL[row.status]}`}
            >
              <div className="w-24 shrink-0 text-[11px] text-white/65">
                {STATUS_LABEL[row.status]}
              </div>
              <div className="relative h-7 flex-1 overflow-hidden rounded-md bg-white/5">
                <div
                  className={`absolute inset-y-0 left-0 ${TONE_BG[tone]} opacity-70 transition-all`}
                  style={{ width: `${row.pct * 100}%` }}
                />
                <div
                  className={`relative flex h-full items-center px-2 text-[11px] font-medium ${TONE_TEXT[tone]}`}
                >
                  {row.reached}
                  <span className="ml-1 text-white/45">
                    · {(row.pct * 100).toFixed(0)}%
                  </span>
                </div>
              </div>
              {i < conversions.length && (
                <div className="w-20 shrink-0 text-right text-[10px] text-white/55">
                  →{' '}
                  <span className={
                    conversions[i].rate >= 0.5
                      ? 'text-emerald-300'
                      : conversions[i].rate >= 0.25
                      ? 'text-amber-300'
                      : 'text-rose-300'
                  }>
                    {(conversions[i].rate * 100).toFixed(0)}%
                  </span>
                  <span className="ml-1 text-white/30">{conversions[i].note}</span>
                </div>
              )}
            </div>
          );
        })}
      </div>

      <div className="grid gap-3 md:grid-cols-2">
        <div className="cc-funnel-tile rounded-lg border border-white/10 bg-white/[0.02] p-3">
          <div className="text-[10px] uppercase tracking-wider text-white/45">
            Status mix
          </div>
          <div className="mt-2 flex h-2 overflow-hidden rounded-full bg-white/5">
            {STATUSES.map(s => {
              const n = counts[s];
              const pct = total ? (n / total) * 100 : 0;
              if (pct === 0) return null;
              return (
                <div
                  key={s}
                  className={TONE_BG[STATUS_TONE[s]]}
                  style={{ width: `${pct}%` }}
                  title={`${STATUS_LABEL[s]}: ${n}`}
                />
              );
            })}
          </div>
          <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-white/65">
            {STATUSES.map(s => (
              <span key={s} className="inline-flex items-center gap-1">
                <span className={`h-1.5 w-1.5 rounded-full ${TONE_BG[STATUS_TONE[s]]}`} />
                <span className="text-white/55">{STATUS_LABEL[s]}</span>
                <span className="font-mono text-white">{counts[s]}</span>
              </span>
            ))}
          </div>
        </div>

        <div className="cc-funnel-tile rounded-lg border border-white/10 bg-white/[0.02] p-3">
          <div className="flex items-center justify-between">
            <div className="text-[10px] uppercase tracking-wider text-white/45">
              Stale (≥ 14 days)
            </div>
            <div className="text-[10px] text-white/40">
              top {stale.length || 0}
            </div>
          </div>
          {stale.length === 0 ? (
            <div className="mt-2 text-[12px] text-emerald-300/80">
              No stalled candidates ✓
            </div>
          ) : (
            <ul className="mt-2 space-y-1.5">
              {stale.map(e => (
                <li
                  key={e.candidateId}
                  className="flex items-center justify-between text-[11px]"
                >
                  <span className="text-white/75">
                    Candidate #{e.candidateId}
                  </span>
                  <span className="text-white/45">
                    {STATUS_LABEL[e.status]} · {ago(e.addedAt)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
