'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { useParams } from 'next/navigation';

import { candidates } from '@/data/candidates';
import { matchCandidate } from '@/lib/match';
import { getRole, type Role } from '@/lib/roles';
import {
  listInterviewsForRole,
  RECOMMENDATION_LABEL,
  RECOMMENDATION_TONE,
  type InterviewRecord,
} from '@/lib/interview';
import {
  buildDebrief,
  buildDecisionSummary,
  FLAG_LABEL,
  FLAG_TONE,
  TIER_HUE,
  type CandidateInput,
  type CandidateVerdict,
  type DecisionSummary,
} from '@/lib/decision';
import DecisionMatrix from '@/components/DecisionMatrix';
import SlotProposer from '@/components/SlotProposer';
import PipelineAnalytics from '@/components/PipelineAnalytics';

const TONE_RING: Record<string, string> = {
  rose: 'border-rose-400/30 bg-rose-400/10 text-rose-200',
  amber: 'border-amber-400/30 bg-amber-400/10 text-amber-200',
  sky: 'border-sky-400/30 bg-sky-400/10 text-sky-200',
  indigo: 'border-indigo-400/30 bg-indigo-400/10 text-indigo-200',
  emerald: 'border-emerald-400/30 bg-emerald-400/10 text-emerald-200',
  violet: 'border-violet-400/30 bg-violet-400/10 text-violet-200',
  slate: 'border-white/15 bg-white/5 text-white/65',
};

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

function downloadText(filename: string, body: string, type = 'text/plain') {
  const blob = new Blob([body], { type });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  setTimeout(() => {
    URL.revokeObjectURL(url);
    a.remove();
  }, 0);
}

function VerdictRing({ verdict, size = 64 }: { verdict: CandidateVerdict; size?: number }) {
  const hue = verdict.recommendation
    ? TIER_HUE[verdict.recommendation]
    : 'rgba(255,255,255,0.35)';
  const pct = Math.max(0, Math.min(100, verdict.hireSignal));
  return (
    <div
      className="cc-vring relative grid place-items-center rounded-full"
      style={{
        width: size, height: size,
        background: `conic-gradient(${hue} ${pct}%, rgba(255,255,255,0.06) 0)`,
      }}
    >
      <div
        className="absolute rounded-full bg-[#0b0b12]"
        style={{ inset: 3 }}
      />
      <div className="relative flex flex-col items-center leading-none">
        <span className="text-[15px] font-semibold" style={{ color: hue }}>
          {verdict.composite ?? '—'}
        </span>
        <span className="mt-0.5 text-[8px] uppercase tracking-wider text-white/45">
          sig {verdict.hireSignal}
        </span>
      </div>
    </div>
  );
}

function FlagPill({ flag }: { flag: CandidateVerdict['flags'][number] }) {
  const tone = FLAG_TONE[flag];
  return (
    <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-medium ${TONE_RING[tone]}`}>
      <span className="h-1.5 w-1.5 rounded-full bg-current" />
      {FLAG_LABEL[flag]}
    </span>
  );
}

export default function DecisionStudio() {
  const params = useParams<{ id: string }>();
  const id = params?.id;

  const [role, setRole] = useState<Role | null>(null);
  const [interviews, setInterviews] = useState<InterviewRecord[]>([]);
  const [ready, setReady] = useState(false);
  const [selected, setSelected] = useState<number | null>(null);
  const [pinned, setPinned] = useState<Set<number>>(new Set());
  const [sortDim, setSortDim] = useState<string | null>(null);
  const [debriefCopied, setDebriefCopied] = useState(false);
  const [showOnlyPinned, setShowOnlyPinned] = useState(false);

  useEffect(() => {
    if (!id) return;
    const r = getRole(id);
    setRole(r);
    if (r) setInterviews(listInterviewsForRole(r.id));
    setReady(true);
    const onFocus = () => {
      if (r) setInterviews(listInterviewsForRole(r.id));
    };
    window.addEventListener('focus', onFocus);
    return () => window.removeEventListener('focus', onFocus);
  }, [id]);

  const inputs: CandidateInput[] = useMemo(() => {
    if (!role) return [];
    const ivByCid: Record<number, InterviewRecord> = {};
    for (const ir of interviews) ivByCid[ir.candidateId] = ir;
    return role.shortlist.map(entry => {
      const c = candidates.find(x => x.id === entry.candidateId);
      const fallback = { id: entry.candidateId, name: `Candidate #${entry.candidateId}` };
      const cand = c ?? fallback;
      const match = c ? matchCandidate(role.plan, c) : matchCandidate(role.plan, fallback);
      return {
        candidateId: entry.candidateId,
        candidate: cand,
        match,
        interview: ivByCid[entry.candidateId] ?? null,
        status: entry.status,
      };
    });
  }, [role, interviews]);

  const summary: DecisionSummary | null = useMemo(() => {
    if (!role) return null;
    return buildDecisionSummary(role.id, inputs);
  }, [role, inputs]);

  const visibleVerdicts: CandidateVerdict[] = useMemo(() => {
    if (!summary) return [];
    if (showOnlyPinned && pinned.size > 0) {
      return summary.verdicts.filter(v => pinned.has(v.candidateId));
    }
    return summary.verdicts;
  }, [summary, showOnlyPinned, pinned]);

  // Auto-select the top hire on first ready load.
  useEffect(() => {
    if (!summary || selected !== null) return;
    if (summary.topHire) setSelected(summary.topHire.candidateId);
    else if (summary.verdicts.length > 0) setSelected(summary.verdicts[0].candidateId);
  }, [summary, selected]);

  const onTogglePin = (cid: number) => {
    setPinned(prev => {
      const next = new Set(prev);
      if (next.has(cid)) next.delete(cid);
      else next.add(cid);
      return next;
    });
  };

  const onCopyDebrief = async () => {
    if (!role || !summary) return;
    await copyToClipboard(buildDebrief(role.name, summary));
    setDebriefCopied(true);
    setTimeout(() => setDebriefCopied(false), 1500);
  };

  const onDownloadDebrief = () => {
    if (!role || !summary) return;
    const md = buildDebrief(role.name, summary);
    const safe = role.name.replace(/[^a-z0-9]+/gi, '_');
    downloadText(`debrief_${safe}.md`, md, 'text/markdown');
  };

  if (!ready) {
    return (
      <main className="min-h-screen bg-gradient-to-b from-[#0b0b12] to-black text-white">
        <div className="mx-auto max-w-6xl px-4 py-12 text-white/50">Loading…</div>
      </main>
    );
  }

  if (!role) {
    return (
      <main className="min-h-screen bg-gradient-to-b from-[#0b0b12] to-black text-white">
        <div className="mx-auto max-w-6xl px-4 py-12 text-center">
          <h1 className="text-2xl font-semibold">Role not found</h1>
          <Link
            href="/roles"
            className="mt-6 inline-block rounded-lg bg-indigo-500 px-4 py-2 text-sm font-medium text-black hover:bg-indigo-400"
          >
            Back to roles
          </Link>
        </div>
      </main>
    );
  }

  const focused = selected !== null && summary
    ? summary.verdicts.find(v => v.candidateId === selected) ?? null
    : null;
  const focusedCand = focused
    ? candidates.find(c => c.id === focused.candidateId) ?? null
    : null;

  return (
    <main className="min-h-screen bg-gradient-to-b from-[#0b0b12] to-black text-white">
      <div className="mx-auto max-w-6xl px-4 pb-24">
        <header className="flex items-center justify-between py-6">
          <Link
            href={`/roles/${role.id}`}
            className="text-sm text-white/60 hover:text-white"
          >
            ← {role.name}
          </Link>
          <nav className="flex items-center gap-6 text-sm text-white/80">
            <Link href="/" className="hover:text-white">Discover</Link>
            <Link href="/roles" className="hover:text-white">Roles</Link>
            <Link href="/pipeline" className="hover:text-white">Pipeline</Link>
          </nav>
        </header>

        {/* Title + actions */}
        <section className="mt-2 flex flex-wrap items-end justify-between gap-4">
          <div className="min-w-0 flex-1">
            <div className="text-[11px] uppercase tracking-wider text-violet-300/80">
              Decision Studio
            </div>
            <h1 className="mt-1 text-3xl font-semibold md:text-4xl">
              {role.name}
            </h1>
            <p className="mt-2 max-w-2xl text-sm text-white/60">
              Side-by-side rubric heatmap, calibrated hire signal, committee
              debrief, and one-click iCal scheduling for the next round.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <button
              onClick={onCopyDebrief}
              disabled={!summary || summary.verdicts.length === 0}
              className="rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-xs text-white hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {debriefCopied ? 'Copied ✓' : 'Copy debrief'}
            </button>
            <button
              onClick={onDownloadDebrief}
              disabled={!summary || summary.verdicts.length === 0}
              className="rounded-lg bg-gradient-to-r from-teal-400 to-violet-400 px-3 py-2 text-xs font-semibold text-black hover:opacity-95 disabled:cursor-not-allowed disabled:from-white/10 disabled:to-white/10 disabled:text-white/40"
            >
              Export debrief.md
            </button>
          </div>
        </section>

        {/* Headline tiles */}
        {summary && summary.verdicts.length > 0 && (
          <section className="mt-6 grid gap-3 md:grid-cols-4">
            <Tile
              label="Top hire"
              value={summary.topHire?.name ?? '—'}
              detail={summary.topHire
                ? `${RECOMMENDATION_LABEL[summary.topHire.recommendation!]} · sig ${summary.topHire.hireSignal}`
                : 'No clear winner yet'}
              tone={summary.topHire ? 'emerald' : 'slate'}
            />
            <Tile
              label="Reviewed"
              value={`${summary.verdicts.length - summary.unratedCount}/${summary.verdicts.length}`}
              detail={summary.unratedCount > 0
                ? `${summary.unratedCount} not yet rated`
                : 'all candidates rated'}
              tone="indigo"
            />
            <Tile
              label="Hires available"
              value={String(summary.counts.strong_hire + summary.counts.lean_yes)}
              detail={`${summary.counts.strong_hire} strong · ${summary.counts.lean_yes} lean`}
              tone="violet"
            />
            <Tile
              label="Risk flags"
              value={String(summary.verdicts.reduce((a, v) => a + v.flags.length, 0))}
              detail="across candidates"
              tone="amber"
            />
          </section>
        )}

        {/* Tier histogram */}
        {summary && summary.verdicts.some(v => v.recommendation !== null) && (
          <section className="mt-4 rounded-2xl border border-white/10 bg-white/[0.03] p-4">
            <div className="mb-2 flex items-center justify-between">
              <div className="text-[10px] uppercase tracking-wider text-white/45">
                Recommendation tiers
              </div>
              <div className="text-[10px] text-white/40">
                {summary.verdicts.length - summary.unratedCount} rated · {summary.unratedCount} pending
              </div>
            </div>
            <div className="flex h-2 overflow-hidden rounded-full bg-white/5">
              {(['no_hire', 'lean_no', 'mixed', 'lean_yes', 'strong_hire'] as const).map(tier => {
                const n = summary.counts[tier];
                const pct = summary.verdicts.length > 0
                  ? (n / summary.verdicts.length) * 100
                  : 0;
                if (pct === 0) return null;
                return (
                  <div
                    key={tier}
                    style={{ width: `${pct}%`, background: TIER_HUE[tier] }}
                    title={`${RECOMMENDATION_LABEL[tier]}: ${n}`}
                  />
                );
              })}
              {summary.unratedCount > 0 && (
                <div
                  style={{
                    width: `${(summary.unratedCount / summary.verdicts.length) * 100}%`,
                    background: 'rgba(255,255,255,0.18)',
                  }}
                  title={`Unrated: ${summary.unratedCount}`}
                />
              )}
            </div>
            <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-white/65">
              {(['strong_hire', 'lean_yes', 'mixed', 'lean_no', 'no_hire'] as const).map(tier => (
                <span key={tier} className="inline-flex items-center gap-1">
                  <span className="h-1.5 w-1.5 rounded-full" style={{ background: TIER_HUE[tier] }} />
                  <span className="text-white/55">{RECOMMENDATION_LABEL[tier]}</span>
                  <span className="font-mono text-white">{summary.counts[tier]}</span>
                </span>
              ))}
              {summary.unratedCount > 0 && (
                <span className="inline-flex items-center gap-1">
                  <span className="h-1.5 w-1.5 rounded-full bg-white/35" />
                  <span className="text-white/55">Unrated</span>
                  <span className="font-mono text-white">{summary.unratedCount}</span>
                </span>
              )}
            </div>
          </section>
        )}

        {/* Pipeline analytics */}
        <section className="mt-6">
          <PipelineAnalytics role={role} />
        </section>

        {/* Matrix */}
        <section className="mt-8">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <div>
              <div className="text-[11px] uppercase tracking-wider text-white/45">
                Calibrated comparison
              </div>
              <div className="text-base font-semibold text-white">
                Rubric × candidates
              </div>
            </div>
            <div className="flex items-center gap-2">
              {sortDim && (
                <button
                  type="button"
                  onClick={() => setSortDim(null)}
                  className="rounded-md border border-white/10 bg-white/5 px-2 py-1 text-[11px] text-white/70 hover:bg-white/10"
                >
                  Reset sort
                </button>
              )}
              {pinned.size > 0 && (
                <button
                  type="button"
                  onClick={() => setShowOnlyPinned(v => !v)}
                  className={`rounded-md border px-2 py-1 text-[11px] ${
                    showOnlyPinned
                      ? 'border-violet-400/60 bg-violet-400/15 text-violet-100'
                      : 'border-white/10 bg-white/5 text-white/70 hover:bg-white/10'
                  }`}
                >
                  {showOnlyPinned ? `Showing ${pinned.size} pinned` : `Show only pinned (${pinned.size})`}
                </button>
              )}
            </div>
          </div>
          {summary ? (
            <DecisionMatrix
              summary={{ ...summary, verdicts: visibleVerdicts }}
              selected={selected}
              pinned={pinned}
              onSelect={cid => setSelected(cid)}
              onTogglePin={onTogglePin}
              sortDim={sortDim}
              onSortDim={setSortDim}
            />
          ) : null}
        </section>

        {/* Ranked list + focus pane */}
        <section className="mt-8 grid gap-6 lg:grid-cols-3">
          {/* Ranked list */}
          <div className="lg:col-span-2">
            <div className="mb-3 text-[11px] uppercase tracking-wider text-white/45">
              Ranked verdicts
            </div>
            <div className="space-y-2">
              {summary?.verdicts.map(v => {
                const isFocused = v.candidateId === selected;
                const tone = v.recommendation
                  ? RECOMMENDATION_TONE[v.recommendation]
                  : 'slate';
                return (
                  <button
                    type="button"
                    key={v.candidateId}
                    onClick={() => setSelected(v.candidateId)}
                    className={`cc-rank-row block w-full rounded-xl border p-3 text-left transition ${
                      isFocused
                        ? 'border-violet-400/60 bg-violet-400/5'
                        : 'border-white/10 bg-white/[0.03] hover:bg-white/[0.06]'
                    }`}
                  >
                    <div className="flex items-center gap-3">
                      <div className="text-[11px] font-mono text-white/50 w-6 text-right">
                        #{v.rank}
                      </div>
                      <VerdictRing verdict={v} size={52} />
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="font-medium text-white">{v.name}</span>
                          {v.recommendation && (
                            <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-medium ${TONE_RING[tone]}`}>
                              {RECOMMENDATION_LABEL[v.recommendation]}
                            </span>
                          )}
                          {!v.recommendation && (
                            <span className="text-[10px] text-white/40">
                              not yet rated
                            </span>
                          )}
                        </div>
                        <div className="mt-0.5 truncate text-[11px] text-white/55">
                          {v.role ?? '—'}{v.location ? ` · ${v.location}` : ''}
                        </div>
                        <div className="mt-1 flex flex-wrap gap-1">
                          {v.flags.map(f => <FlagPill key={f} flag={f} />)}
                        </div>
                      </div>
                      <div className="shrink-0 text-right">
                        <div className="font-mono text-xs text-white/55">
                          match {v.matchScore}
                        </div>
                        <div className="text-[10px] text-white/35">
                          rated {v.ratedCount}/{v.totalCount}
                        </div>
                      </div>
                    </div>
                  </button>
                );
              })}
              {summary && summary.verdicts.length === 0 && (
                <div className="rounded-2xl border border-dashed border-white/10 bg-white/[0.02] p-8 text-center text-sm text-white/55">
                  Add candidates to the role&apos;s shortlist to see verdicts here.
                </div>
              )}
            </div>
          </div>

          {/* Focus pane */}
          <aside className="space-y-4">
            {focused && summary ? (
              <>
                <div className="cc-focus rounded-2xl border border-white/10 bg-white/[0.03] p-4">
                  <div className="flex items-start gap-3">
                    <VerdictRing verdict={focused} size={72} />
                    <div className="min-w-0 flex-1">
                      <div className="text-base font-semibold text-white">
                        {focused.name}
                      </div>
                      <div className="text-[11px] text-white/55">
                        {focused.role ?? '—'}
                        {focused.location ? ` · ${focused.location}` : ''}
                      </div>
                      <div className="mt-1.5 text-[11px] text-white/65">
                        Match {focused.matchScore} · rated {focused.ratedCount}/{focused.totalCount}
                        {focused.totalCount > 0 ? ` · conf ${(focused.confidence * 100).toFixed(0)}%` : ''}
                      </div>
                    </div>
                  </div>

                  {focused.flags.length > 0 && (
                    <div className="mt-3 flex flex-wrap gap-1.5">
                      {focused.flags.map(f => <FlagPill key={f} flag={f} />)}
                    </div>
                  )}

                  {focused.topStrengths.length > 0 && (
                    <div className="mt-3">
                      <div className="text-[10px] uppercase tracking-wider text-emerald-300/80">
                        Strengths
                      </div>
                      <div className="mt-1 flex flex-wrap gap-1">
                        {focused.topStrengths.map(s => (
                          <span
                            key={s}
                            className="rounded-full border border-emerald-400/30 bg-emerald-400/10 px-2 py-0.5 text-[10px] text-emerald-200"
                          >
                            {s}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                  {focused.topConcerns.length > 0 && (
                    <div className="mt-3">
                      <div className="text-[10px] uppercase tracking-wider text-rose-300/80">
                        Concerns
                      </div>
                      <div className="mt-1 flex flex-wrap gap-1">
                        {focused.topConcerns.map(s => (
                          <span
                            key={s}
                            className="rounded-full border border-rose-400/30 bg-rose-400/10 px-2 py-0.5 text-[10px] text-rose-200"
                          >
                            {s}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  <div className="mt-4 flex flex-wrap gap-2">
                    <Link
                      href={`/roles/${role.id}/interview/${focused.candidateId}`}
                      className="rounded-md border border-violet-400/40 bg-violet-400/10 px-2.5 py-1 text-[11px] font-medium text-violet-200 hover:bg-violet-400/20"
                    >
                      Open scorecard
                    </Link>
                  </div>
                </div>

                <SlotProposer
                  candidateName={focused.name}
                  candidateEmail={focusedCand?.headline?.match(/[\w.+-]+@[\w-]+\.[\w.-]+/)?.[0]}
                  roleName={role.name}
                />
              </>
            ) : (
              <div className="rounded-2xl border border-dashed border-white/10 bg-white/[0.02] p-6 text-center text-sm text-white/55">
                Select a candidate to inspect their verdict and propose interview slots.
              </div>
            )}

            {/* Next-round candidates */}
            {summary && summary.nextRound.length > 0 && (
              <div className="cc-nextround rounded-2xl border border-white/10 bg-white/[0.03] p-4">
                <div className="text-[10px] uppercase tracking-wider text-white/45">
                  Next round candidates
                </div>
                <div className="mt-1 text-[11px] text-white/55">
                  Strong match · interview thin or missing
                </div>
                <ul className="mt-2 space-y-1.5">
                  {summary.nextRound.map(v => (
                    <li
                      key={v.candidateId}
                      className="flex items-center justify-between rounded-md border border-white/5 bg-white/[0.02] px-2 py-1.5 text-[11px]"
                    >
                      <button
                        type="button"
                        onClick={() => setSelected(v.candidateId)}
                        className="truncate text-left text-white/80 hover:text-white"
                      >
                        {v.name}
                      </button>
                      <span className="shrink-0 font-mono text-[10px] text-white/45">
                        match {v.matchScore}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </aside>
        </section>
      </div>
    </main>
  );
}

function Tile({
  label, value, detail, tone,
}: { label: string; value: string; detail: string; tone: string }) {
  return (
    <div className={`cc-tile rounded-xl border p-3 ${TONE_RING[tone]}`}>
      <div className="text-[10px] uppercase tracking-wider opacity-70">
        {label}
      </div>
      <div className="mt-1 truncate text-lg font-semibold">{value}</div>
      <div className="mt-0.5 truncate text-[11px] opacity-65">{detail}</div>
    </div>
  );
}
