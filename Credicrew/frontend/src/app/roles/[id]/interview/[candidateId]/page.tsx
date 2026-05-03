'use client';
import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { useParams } from 'next/navigation';

import { candidates } from '@/data/candidates';
import { matchCandidate } from '@/lib/match';
import { getRole } from '@/lib/roles';
import {
  STAGES,
  STAGE_LABEL,
  STAGE_TONE,
  addSignal,
  buildIntroLine,
  ensureInterview,
  removeSignal,
  setRating,
  setStageNotes,
  setStageStatus,
  summarise,
  type DimensionScore,
  type InterviewRecord,
  type InterviewStage,
} from '@/lib/interview';
import { downloadFile } from '@/lib/csv';
import InterviewStepper from '@/components/InterviewStepper';
import QuestionCard from '@/components/QuestionCard';
import RubricSlider from '@/components/RubricSlider';
import RecommendationRing from '@/components/RecommendationRing';

const TONE_BG: Record<string, string> = {
  sky: 'bg-sky-400',
  indigo: 'bg-indigo-400',
  violet: 'bg-violet-400',
  amber: 'bg-amber-400',
  emerald: 'bg-emerald-400',
};

export default function InterviewWorkspace() {
  const params = useParams<{ id: string; candidateId: string }>();
  const roleId = params?.id;
  const cidNum = Number(params?.candidateId);

  const [record, setRecord] = useState<InterviewRecord | null>(null);
  const [ready, setReady] = useState(false);
  const [active, setActive] = useState<InterviewStage>('phone_screen');
  const [signalDraft, setSignalDraft] = useState({ kind: 'strength' as 'strength' | 'concern', text: '' });
  const [notFound, setNotFound] = useState(false);

  const role = useMemo(() => (roleId ? getRole(roleId) : null), [roleId]);
  const candidate = useMemo(() => candidates.find(c => c.id === cidNum) ?? null, [cidNum]);

  useEffect(() => {
    if (!roleId || !candidate || !role) {
      if (ready) return;
      setNotFound(!role || !candidate);
      setReady(true);
      return;
    }
    const r = ensureInterview({ roleId, candidateId: cidNum, plan: role.plan });
    setRecord(r);
    setReady(true);
  }, [roleId, cidNum, role, candidate, ready]);

  const summary = useMemo(() => (record ? summarise(record) : null), [record]);
  const match = useMemo(
    () => (role && candidate ? matchCandidate(role.plan, candidate) : null),
    [role, candidate],
  );

  if (!ready) {
    return (
      <main className="min-h-screen bg-gradient-to-b from-[#0b0b12] to-black text-white">
        <div className="mx-auto max-w-6xl px-4 py-12 text-white/50">Loading…</div>
      </main>
    );
  }
  if (notFound || !role || !candidate || !record || !summary) {
    return (
      <main className="min-h-screen bg-gradient-to-b from-[#0b0b12] to-black text-white">
        <div className="mx-auto max-w-6xl px-4 py-12 text-center">
          <h1 className="text-2xl font-semibold">Interview not found</h1>
          <p className="mt-2 text-white/60">
            The role or candidate may have been removed on this device.
          </p>
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

  const stageRec = record.stages.find(s => s.stage === active)!;
  const stageQuestions = record.questions.filter(q => q.stage === active);
  const tone = STAGE_TONE[active];

  const onRate = (dimKey: string, rating: DimensionScore['rating']) => {
    setRecord(setRating(record, active, dimKey, rating));
  };
  const onStageNotes = (text: string) => {
    setRecord(setStageNotes(record, active, text));
  };
  const onStatus = (status: 'planned' | 'in_progress' | 'done') => {
    setRecord(setStageStatus(record, active, status));
  };
  const onAddSignal = () => {
    if (!signalDraft.text.trim()) return;
    setRecord(addSignal(record, active, signalDraft.kind, signalDraft.text));
    setSignalDraft({ ...signalDraft, text: '' });
  };
  const onRemoveSignal = (ts: number) => {
    setRecord(removeSignal(record, active, ts));
  };

  const onExportReport = () => {
    const lines: string[] = [];
    lines.push(`# Interview report — ${candidate.name}`);
    lines.push('');
    lines.push(`Role: ${role.name}`);
    lines.push(`${buildIntroLine(role.plan, candidate)}`);
    if (match) lines.push(`Pre-interview match: ${match.score}/100`);
    lines.push('');
    lines.push(`## Recommendation: ${summary.recommendation.replace(/_/g, ' ')} (composite ${summary.composite})`);
    lines.push(`Rated ${summary.ratedCount}/${summary.totalCount} dimensions.`);
    lines.push('');
    lines.push(`## Rubric`);
    for (const d of summary.perDimension) {
      lines.push(
        `- ${d.label} · weight ${(d.weight * 100).toFixed(0)}% · rating ${d.rating ?? '—'} · impact ${d.impact}`,
      );
    }
    lines.push('');
    if (summary.strengths.length) {
      lines.push(`## Strengths`);
      for (const s of summary.strengths) lines.push(`- ${s.text}`);
      lines.push('');
    }
    if (summary.concerns.length) {
      lines.push(`## Concerns`);
      for (const s of summary.concerns) lines.push(`- ${s.text}`);
      lines.push('');
    }
    lines.push(`## Stages`);
    for (const stage of record.stages) {
      lines.push(`### ${STAGE_LABEL[stage.stage]} — ${stage.status.replace('_', ' ')}`);
      const rated = stage.scores.filter(sc => sc.rating !== null);
      for (const sc of rated) {
        const dim = record.rubric.find(d => d.key === sc.key);
        lines.push(`- ${dim?.label ?? sc.key}: ${sc.rating}`);
      }
      if (stage.notes) {
        lines.push('');
        lines.push(stage.notes);
      }
      lines.push('');
    }
    const filename = `interview_${role.name.replace(/[^a-z0-9]+/gi, '_')}_${candidate.name.replace(/[^a-z0-9]+/gi, '_')}.md`;
    downloadFile(filename, lines.join('\n'), 'text/markdown;charset=utf-8');
  };

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

        {/* Title row */}
        <section className="flex flex-wrap items-end justify-between gap-4">
          <div className="min-w-0 flex-1">
            <div className="text-[11px] uppercase tracking-wider text-white/45">
              Interview kit
            </div>
            <h1 className="mt-1 text-3xl font-semibold md:text-4xl">
              {candidate.name}
            </h1>
            <div className="mt-2 text-sm text-white/60">
              {buildIntroLine(role.plan, candidate)}
              {match && (
                <span className="ml-2 rounded-full border border-emerald-400/30 bg-emerald-400/10 px-2 py-0.5 text-[11px] text-emerald-200">
                  match · {match.score}
                </span>
              )}
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={onExportReport}
              className="rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-xs text-white hover:bg-white/10"
              title="Download a Markdown debrief"
            >
              Export report (.md)
            </button>
          </div>
        </section>

        {/* Top: stepper + recommendation */}
        <section className="mt-8 grid gap-4 lg:grid-cols-[1fr_auto]">
          <InterviewStepper record={record} active={active} onPick={setActive} />
          <div className="rounded-2xl border border-white/10 bg-white/[0.04] p-5">
            <RecommendationRing
              composite={summary.composite}
              recommendation={summary.recommendation}
              ratedCount={summary.ratedCount}
              totalCount={summary.totalCount}
            />
          </div>
        </section>

        {/* Stage active panel */}
        <section className="mt-8">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-3">
              <span
                className={`grid h-7 w-7 place-items-center rounded-full text-xs font-semibold text-black ${TONE_BG[tone]}`}
              >
                {STAGES.indexOf(active) + 1}
              </span>
              <h2 className="text-xl font-semibold">{STAGE_LABEL[active]}</h2>
              <span className="rounded-full border border-white/10 bg-white/5 px-2 py-0.5 text-[11px] text-white/55">
                {stageQuestions.length} prompt{stageQuestions.length === 1 ? '' : 's'}
              </span>
            </div>
            <div className="flex items-center gap-1.5">
              {(['planned', 'in_progress', 'done'] as const).map(s => (
                <button
                  key={s}
                  onClick={() => onStatus(s)}
                  className={`rounded-md border px-2 py-1 text-[11px] capitalize transition ${
                    stageRec.status === s
                      ? 'border-white/20 bg-white/[0.08] text-white'
                      : 'border-white/10 bg-white/[0.02] text-white/60 hover:bg-white/[0.06]'
                  }`}
                >
                  {s.replace('_', ' ')}
                </button>
              ))}
            </div>
          </div>

          <div className="grid gap-6 lg:grid-cols-[1.4fr_1fr]">
            {/* Left: questions + notes */}
            <div className="space-y-3">
              {stageQuestions.length === 0 ? (
                <div className="rounded-xl border border-dashed border-white/10 bg-white/[0.02] p-6 text-center text-sm text-white/55">
                  No prompts for this stage. Use the rubric and notes to capture signal.
                </div>
              ) : (
                stageQuestions.map(q => <QuestionCard key={q.id} q={q} />)
              )}
              <div className="mt-4 rounded-xl border border-white/10 bg-white/[0.025] p-4">
                <div className="mb-2 text-[11px] uppercase tracking-wider text-white/50">
                  Stage notes
                </div>
                <textarea
                  defaultValue={stageRec.notes ?? ''}
                  onBlur={e => onStageNotes(e.target.value)}
                  rows={5}
                  placeholder="Capture quotes, code-walk-throughs, follow-ups…"
                  className="w-full rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-sm text-white/85 placeholder-white/30 focus:border-indigo-400/60 focus:outline-none"
                />
              </div>
            </div>

            {/* Right: rubric + signals */}
            <div className="space-y-3">
              <div className="rounded-xl border border-white/10 bg-white/[0.04] p-4">
                <div className="mb-3 text-[11px] uppercase tracking-wider text-white/50">
                  Rubric · this stage
                </div>
                <div className="space-y-2.5">
                  {record.rubric.map(dim => {
                    const score = stageRec.scores.find(s => s.key === dim.key)!;
                    return (
                      <RubricSlider
                        key={dim.key}
                        dim={dim}
                        score={score}
                        onRate={r => onRate(dim.key, r)}
                      />
                    );
                  })}
                </div>
              </div>

              <div className="rounded-xl border border-white/10 bg-white/[0.04] p-4">
                <div className="mb-3 flex items-center justify-between">
                  <div className="text-[11px] uppercase tracking-wider text-white/50">
                    Signals · this stage
                  </div>
                  <div className="text-[11px] text-white/40">
                    {stageRec.signals.length}
                  </div>
                </div>
                <div className="flex gap-1.5">
                  <button
                    onClick={() => setSignalDraft({ ...signalDraft, kind: 'strength' })}
                    className={`rounded-md border px-2 py-1 text-[11px] ${
                      signalDraft.kind === 'strength'
                        ? 'border-emerald-400/40 bg-emerald-400/10 text-emerald-200'
                        : 'border-white/10 bg-white/[0.02] text-white/60'
                    }`}
                  >
                    + strength
                  </button>
                  <button
                    onClick={() => setSignalDraft({ ...signalDraft, kind: 'concern' })}
                    className={`rounded-md border px-2 py-1 text-[11px] ${
                      signalDraft.kind === 'concern'
                        ? 'border-rose-400/40 bg-rose-400/10 text-rose-200'
                        : 'border-white/10 bg-white/[0.02] text-white/60'
                    }`}
                  >
                    + concern
                  </button>
                </div>
                <div className="mt-2 flex gap-2">
                  <input
                    value={signalDraft.text}
                    onChange={e => setSignalDraft({ ...signalDraft, text: e.target.value })}
                    onKeyDown={e => e.key === 'Enter' && onAddSignal()}
                    placeholder={
                      signalDraft.kind === 'strength'
                        ? 'e.g. drove the indexing redesign solo'
                        : 'e.g. waved away async correctness'
                    }
                    className="flex-1 rounded-md border border-white/10 bg-black/30 px-2 py-1 text-xs text-white/85 placeholder-white/30 focus:border-indigo-400/60 focus:outline-none"
                  />
                  <button
                    onClick={onAddSignal}
                    className="rounded-md bg-indigo-500 px-2.5 py-1 text-[11px] font-medium text-black hover:bg-indigo-400"
                  >
                    add
                  </button>
                </div>
                {stageRec.signals.length > 0 && (
                  <ul className="mt-3 space-y-1.5">
                    {stageRec.signals.map(s => (
                      <li
                        key={s.ts}
                        className={`flex items-start justify-between gap-2 rounded-md border px-2 py-1.5 text-xs ${
                          s.kind === 'strength'
                            ? 'border-emerald-400/30 bg-emerald-400/10 text-emerald-100'
                            : 'border-rose-400/30 bg-rose-400/10 text-rose-100'
                        }`}
                      >
                        <span>
                          <span className="opacity-60">{s.kind === 'strength' ? '+' : '−'} </span>
                          {s.text}
                        </span>
                        <button
                          onClick={() => onRemoveSignal(s.ts)}
                          className="text-white/40 hover:text-white/80"
                          title="Remove"
                        >
                          ×
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
          </div>
        </section>

        {/* Composite breakdown */}
        <section className="mt-10 rounded-2xl border border-white/10 bg-white/[0.04] p-5">
          <div className="mb-3 flex items-center justify-between">
            <div>
              <div className="text-[11px] uppercase tracking-wider text-white/50">
                Composite breakdown
              </div>
              <div className="text-sm text-white/70">
                Weighted Σ over rated dimensions across all stages.
              </div>
            </div>
            <div className="text-[11px] text-white/40">
              {summary.ratedCount}/{summary.totalCount} rated
            </div>
          </div>
          <div className="space-y-2">
            {summary.perDimension.map(d => {
              const rated = d.rating !== null;
              const fill = rated ? d.impact : 0;
              return (
                <div key={d.key} className="grid grid-cols-[1fr_auto] items-center gap-3">
                  <div>
                    <div className="flex items-center justify-between text-xs">
                      <span className="text-white/85">{d.label}</span>
                      <span className="text-white/50">
                        {rated ? `${d.rating} · ${d.impact} pt` : 'unrated'}
                      </span>
                    </div>
                    <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-white/[0.06]">
                      <div
                        className="h-full rounded-full transition-all"
                        style={{
                          width: `${Math.min(100, fill * 1.2)}%`,
                          background: rated
                            ? 'linear-gradient(90deg, #818cf8, #34d399)'
                            : 'transparent',
                        }}
                      />
                    </div>
                  </div>
                  <div className="text-[10px] text-white/40">
                    w · {(d.weight * 100).toFixed(0)}%
                  </div>
                </div>
              );
            })}
          </div>
        </section>
      </div>
    </main>
  );
}
