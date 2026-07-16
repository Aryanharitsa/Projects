'use client';

import Link from 'next/link';
import { useEffect, useMemo, useState, type CSSProperties } from 'react';

import { candidates as CANDIDATES } from '@/data/candidates';
import type { Role } from '@/lib/roles';
import { listRoles } from '@/lib/roles';
import type { InterviewRecord } from '@/lib/interview';
import { listInterviewsForRole } from '@/lib/interview';
import {
  composeBundle,
  scoreResponses,
  toMarkdown,
  ANSWER_VERDICT_LABEL,
  ANSWER_VERDICT_TONE,
  KIND_HEX,
  KIND_LABEL,
  QUESTION_KIND_LABEL,
  VERDICT_LABEL,
  VERDICT_TONE,
  type AnswerVerdict,
  type ReferenceBundle,
  type ReferenceReport,
  type ResponseAnswer,
} from '@/lib/reference';

// ─────────── helpers ───────────

const TONE_HEX: Record<string, string> = {
  sky: '#0ea5e9',
  indigo: '#6366f1',
  violet: '#a855f7',
  amber: '#f59e0b',
  emerald: '#10b981',
  rose: '#f43f5e',
  slate: '#94a3b8',
  cyan: '#06b6d4',
  pink: '#ec4899',
};

const SEVERITY_HEX: Record<string, string> = {
  block: TONE_HEX.rose,
  concern: TONE_HEX.amber,
  gap: TONE_HEX.sky,
  watch: TONE_HEX.slate,
};

const CLAIM_STATUS_HEX: Record<string, string> = {
  confirmed: TONE_HEX.emerald,
  contradicted: TONE_HEX.rose,
  concern: TONE_HEX.amber,
  unknown: TONE_HEX.slate,
  resolved: TONE_HEX.emerald,
};

const ANSWER_VERDICT_ORDER: AnswerVerdict[] = [
  'pending',
  'corroborated',
  'concerned',
  'contradicted',
  'no_signal',
];

const RESPONSE_KEY = 'credicrew:reference:responses:v1';

function loadResponses(): Record<string, Record<string, ResponseAnswer>> {
  if (typeof window === 'undefined') return {};
  try {
    const raw = localStorage.getItem(RESPONSE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === 'object' ? parsed : {};
  } catch {
    return {};
  }
}

function saveResponses(state: Record<string, Record<string, ResponseAnswer>>): void {
  if (typeof window === 'undefined') return;
  try {
    localStorage.setItem(RESPONSE_KEY, JSON.stringify(state));
  } catch {
    // storage full or blocked — deliberately silent so the UI keeps working
  }
}

function scopeKey(roleId: string, candidateId: number): string {
  return `${roleId}::${candidateId}`;
}

function copyToClipboard(s: string): Promise<void> {
  if (typeof navigator !== 'undefined' && navigator.clipboard) {
    return navigator.clipboard.writeText(s);
  }
  return new Promise((res) => {
    const ta = document.createElement('textarea');
    ta.value = s;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    ta.remove();
    res();
  });
}

// ─────────── atoms ───────────

function ScoreRing({
  value,
  accent,
  size = 176,
  label = 'projected',
  suffix = '',
}: {
  value: number;
  accent: string;
  size?: number;
  label?: string;
  suffix?: string;
}) {
  const clamped = Math.max(0, Math.min(100, value));
  const style: CSSProperties = {
    width: size,
    height: size,
    background: `conic-gradient(${accent} ${clamped * 3.6}deg, rgba(255,255,255,0.06) 0)`,
    boxShadow: `0 0 32px -8px ${accent}70, inset 0 0 24px -4px ${accent}30`,
  };
  return (
    <div className="relative grid place-items-center rounded-full" style={style}>
      <div
        className="grid place-items-center rounded-full bg-neutral-950/95 ring-1 ring-white/10"
        style={{ width: size - 20, height: size - 20 }}
      >
        <div className="text-center">
          <div className="text-4xl font-semibold text-white">
            {Math.round(clamped)}
            {suffix}
          </div>
          <div className="text-[10px] uppercase tracking-widest text-white/60">{label}</div>
        </div>
      </div>
    </div>
  );
}

function Chip({
  hex,
  children,
  tight = false,
}: {
  hex: string;
  children: React.ReactNode;
  tight?: boolean;
}) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full border font-medium ${
        tight ? 'px-1.5 py-[1px] text-[10px]' : 'px-2 py-[2px] text-[11px]'
      }`}
      style={{ borderColor: `${hex}55`, background: `${hex}18`, color: hex }}
    >
      {children}
    </span>
  );
}

function Tile({
  label,
  value,
  sub,
  accent,
}: {
  label: string;
  value: string;
  sub?: string;
  accent?: string;
}) {
  return (
    <div
      className="rounded-2xl border border-white/10 bg-white/[0.03] p-4"
      style={accent ? { boxShadow: `inset 0 0 24px -12px ${accent}55` } : undefined}
    >
      <div className="text-[10px] uppercase tracking-widest text-white/50">{label}</div>
      <div className="mt-1 text-xl font-semibold text-white">{value}</div>
      {sub && <div className="mt-1 text-[11px] text-white/50">{sub}</div>}
    </div>
  );
}

function TinyBar({ pct, hex }: { pct: number; hex: string }) {
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-white/5">
      <div
        className="h-full rounded-full"
        style={{
          width: `${Math.max(2, Math.min(100, pct))}%`,
          background: `linear-gradient(90deg, ${hex}, color-mix(in srgb, ${hex} 60%, white))`,
        }}
      />
    </div>
  );
}

function SectionTitle({ title, sub }: { title: string; sub?: string }) {
  return (
    <div className="mb-3">
      <h3 className="text-sm font-semibold tracking-widest text-white/80 uppercase">{title}</h3>
      {sub && <p className="mt-1 text-[12px] text-white/50">{sub}</p>}
    </div>
  );
}

// ─────────── page ───────────

type MutableResponses = Record<string, ResponseAnswer>;

export default function ReferencePage() {
  const [roles, setRoles] = useState<Role[]>([]);
  const [roleId, setRoleId] = useState<string>('');
  const [candidateId, setCandidateId] = useState<number>(0);
  const [interviewsForRole, setInterviewsForRole] = useState<InterviewRecord[]>([]);
  const [responsesByScope, setResponsesByScope] = useState<Record<string, MutableResponses>>({});
  const [copied, setCopied] = useState<null | 'md' | 'json'>(null);
  const [now, setNow] = useState<number>(0);

  // hydrate roles + candidates once
  useEffect(() => {
    const rs = listRoles();
    setRoles(rs);
    setResponsesByScope(loadResponses());
    setNow(Date.now());
  }, []);

  // when role changes, load its interviews and pick the first candidate that has one
  useEffect(() => {
    if (!roleId) {
      setInterviewsForRole([]);
      return;
    }
    const list = listInterviewsForRole(roleId);
    setInterviewsForRole(list);
    if (list.length && !list.find((r) => r.candidateId === candidateId)) {
      setCandidateId(list[0].candidateId);
    }
  }, [roleId, candidateId]);

  // Autoselect the first role if none picked yet.
  useEffect(() => {
    if (!roleId && roles.length) setRoleId(roles[0].id);
  }, [roles, roleId]);

  const activeRole: Role | null = useMemo(
    () => roles.find((r) => r.id === roleId) ?? null,
    [roles, roleId],
  );

  const candidateOptions = useMemo(() => {
    // Candidates that already have an interview record for this role first,
    // then the general pool sorted by score.
    const withInterview = new Set(interviewsForRole.map((r) => r.candidateId));
    const inCandidates = CANDIDATES.filter((c) => withInterview.has(c.id));
    const rest = CANDIDATES.filter((c) => !withInterview.has(c.id))
      .slice()
      .sort((a, b) => b.score - a.score);
    return [...inCandidates, ...rest];
  }, [interviewsForRole]);

  const activeCandidate = useMemo(
    () => candidateOptions.find((c) => c.id === candidateId) ?? candidateOptions[0] ?? null,
    [candidateOptions, candidateId],
  );

  useEffect(() => {
    if (!candidateId && activeCandidate) setCandidateId(activeCandidate.id);
  }, [activeCandidate, candidateId]);

  const activeInterview: InterviewRecord | null = useMemo(() => {
    if (!activeCandidate) return null;
    return interviewsForRole.find((r) => r.candidateId === activeCandidate.id) ?? null;
  }, [interviewsForRole, activeCandidate]);

  const bundle: ReferenceBundle | null = useMemo(() => {
    if (!activeRole || !activeCandidate) return null;
    return composeBundle({
      role: { id: activeRole.id, name: activeRole.name, plan: activeRole.plan },
      candidate: {
        id: activeCandidate.id,
        name: activeCandidate.name,
        role: activeCandidate.role,
        location: activeCandidate.location,
        headline: activeCandidate.headline,
        tags: activeCandidate.tags,
        keywords: activeCandidate.keywords,
      },
      interview: activeInterview,
    });
  }, [activeRole, activeCandidate, activeInterview]);

  const scopeId = bundle ? scopeKey(bundle.roleId, bundle.candidateId) : '';
  const responses: MutableResponses = useMemo(
    () => (scopeId ? responsesByScope[scopeId] ?? {} : {}),
    [scopeId, responsesByScope],
  );

  const report: ReferenceReport | null = useMemo(() => {
    if (!bundle) return null;
    return scoreResponses(bundle, Object.values(responses));
  }, [bundle, responses]);

  function setResponse(scope: string, question: ResponseAnswer): void {
    setResponsesByScope((prev) => {
      const scopeMap = { ...(prev[scope] ?? {}) };
      scopeMap[question.questionId] = question;
      const next = { ...prev, [scope]: scopeMap };
      saveResponses(next);
      return next;
    });
  }

  function resetResponses(scope: string): void {
    setResponsesByScope((prev) => {
      const next = { ...prev };
      delete next[scope];
      saveResponses(next);
      return next;
    });
  }

  const verdictHex = report ? TONE_HEX[VERDICT_TONE[report.verdict]] : TONE_HEX.sky;

  return (
    <main className="mx-auto max-w-6xl px-4 py-8 text-white">
      <PageHeader now={now} />

      <Config
        roles={roles}
        roleId={roleId}
        setRoleId={setRoleId}
        candidateOptions={candidateOptions}
        candidateId={candidateId}
        setCandidateId={setCandidateId}
        interviewsForRole={interviewsForRole}
      />

      {!bundle ? (
        <EmptyState hasRoles={roles.length > 0} />
      ) : (
        <>
          <Hero
            bundle={bundle}
            report={report}
            verdictHex={verdictHex}
            hasInterview={Boolean(activeInterview)}
          />

          <div className="mt-6 grid grid-cols-2 gap-3 md:grid-cols-5">
            <Tile
              label="Interview composite"
              value={bundle.interviewComposite != null ? `${bundle.interviewComposite}/100` : '—'}
              sub={activeInterview ? 'from interview record' : 'no record yet'}
              accent={activeInterview ? TONE_HEX.indigo : undefined}
            />
            <Tile
              label="Score shift"
              value={report ? `${report.scoreShift >= 0 ? '+' : ''}${report.scoreShift.toFixed(1)} pts` : '0.0 pts'}
              sub={report ? `${report.coveragePct.toFixed(0)}% coverage` : 'awaiting answers'}
              accent={report && report.scoreShift < 0 ? TONE_HEX.rose : TONE_HEX.emerald}
            />
            <Tile
              label="Projected composite"
              value={report?.projectedComposite != null ? `${report.projectedComposite}/100` : '—'}
              sub={
                report && bundle.interviewComposite != null && report.projectedComposite != null
                  ? `${report.projectedComposite - bundle.interviewComposite >= 0 ? '+' : ''}${
                      report.projectedComposite - bundle.interviewComposite
                    } vs baseline`
                  : 'needs interview record'
              }
              accent={verdictHex}
            />
            <Tile
              label="Slots"
              value={`${bundle.slots.length} × refs`}
              sub={`tier: ${bundle.seniorityTier}`}
              accent={TONE_HEX.violet}
            />
            <Tile
              label="Time budget"
              value={`${bundle.totalMinutes}m`}
              sub={`${bundle.totalQuestions} questions`}
              accent={TONE_HEX.cyan}
            />
          </div>

          <div className="mt-8 grid gap-6 lg:grid-cols-3">
            <div className="space-y-6 lg:col-span-2">
              {bundle.slots.map((slot) => (
                <SlotCard
                  key={slot.slotId}
                  slot={slot}
                  responses={responses}
                  onAnswer={(question, verdict, note) =>
                    setResponse(scopeId, {
                      slotId: slot.slotId,
                      questionId: question.id,
                      verdict,
                      note,
                    })
                  }
                />
              ))}
            </div>

            <aside className="space-y-6">
              <ClaimPanel bundle={bundle} report={report} />
              <FlagPanel bundle={bundle} report={report} />
              <ActionsPanel
                bundle={bundle}
                report={report}
                copied={copied}
                onCopyMd={async () => {
                  await copyToClipboard(toMarkdown(bundle));
                  setCopied('md');
                  setTimeout(() => setCopied(null), 1600);
                }}
                onCopyJson={async () => {
                  await copyToClipboard(JSON.stringify({ bundle, report }, null, 2));
                  setCopied('json');
                  setTimeout(() => setCopied(null), 1600);
                }}
                onReset={() => resetResponses(scopeId)}
              />
            </aside>
          </div>
        </>
      )}

      <Footer />
    </main>
  );
}

// ─────────── header + config + empty ───────────

function PageHeader({ now }: { now: number }) {
  return (
    <header className="mb-6 flex items-start justify-between gap-4">
      <div>
        <div className="mb-1 flex items-center gap-2 text-[10px] uppercase tracking-[0.2em] text-white/60">
          <span
            className="inline-flex h-1.5 w-1.5 rounded-full"
            style={{ background: TONE_HEX.emerald, boxShadow: `0 0 12px ${TONE_HEX.emerald}` }}
          />
          Day 82 · Reference
        </div>
        <h1 className="bg-gradient-to-br from-emerald-200 via-cyan-200 to-indigo-200 bg-clip-text text-3xl font-semibold text-transparent">
          Reference — Structured Reference-Check Composer
        </h1>
        <p className="mt-1 max-w-2xl text-sm text-white/60">
          The last 25 minutes between “we like this candidate” and “we send the offer.” Every claim
          worth corroborating, every rubric flag worth probing, one deterministic question sheet per
          referee — folded back into a score-shifted verdict as the answers come in.
        </p>
      </div>
      <div className="hidden shrink-0 rounded-2xl border border-white/10 bg-white/[0.03] px-3 py-2 text-right text-[11px] text-white/55 md:block">
        <div>engine credicrew-reference/1.0.0</div>
        <div>envelope credicrew.reference.v1</div>
        {now > 0 && <div>opened {new Date(now).toLocaleString()}</div>}
      </div>
    </header>
  );
}

function Config({
  roles,
  roleId,
  setRoleId,
  candidateOptions,
  candidateId,
  setCandidateId,
  interviewsForRole,
}: {
  roles: Role[];
  roleId: string;
  setRoleId: (v: string) => void;
  candidateOptions: (typeof CANDIDATES)[number][];
  candidateId: number;
  setCandidateId: (v: number) => void;
  interviewsForRole: InterviewRecord[];
}) {
  const withInterview = new Set(interviewsForRole.map((r) => r.candidateId));
  return (
    <div className="mb-6 flex flex-wrap items-center gap-3 rounded-2xl border border-white/10 bg-white/[0.03] p-4">
      <label className="flex flex-col text-[11px] uppercase tracking-widest text-white/50">
        Role
        <select
          value={roleId}
          onChange={(e) => setRoleId(e.target.value)}
          className="mt-1 min-w-[240px] rounded-lg border border-white/10 bg-neutral-900/70 px-3 py-2 text-sm text-white focus:border-white/30 focus:outline-none"
        >
          {roles.length === 0 && <option value="">— no roles yet —</option>}
          {roles.map((r) => (
            <option key={r.id} value={r.id}>
              {r.name}
            </option>
          ))}
        </select>
      </label>
      <label className="flex flex-col text-[11px] uppercase tracking-widest text-white/50">
        Candidate
        <select
          value={candidateId || ''}
          onChange={(e) => setCandidateId(Number(e.target.value))}
          className="mt-1 min-w-[280px] rounded-lg border border-white/10 bg-neutral-900/70 px-3 py-2 text-sm text-white focus:border-white/30 focus:outline-none"
        >
          <option value="">— pick a candidate —</option>
          {candidateOptions.map((c) => (
            <option key={c.id} value={c.id}>
              {withInterview.has(c.id) ? '◉ ' : '◯ '}
              {c.name} · {c.role}
            </option>
          ))}
        </select>
      </label>
      <div className="ml-auto flex flex-col items-end text-[11px] text-white/50">
        <span>{interviewsForRole.length} interview{interviewsForRole.length !== 1 ? 's' : ''} on this role</span>
        <span className="text-white/40">◉ = has interview record · ◯ = pool</span>
      </div>
    </div>
  );
}

function EmptyState({ hasRoles }: { hasRoles: boolean }) {
  return (
    <div className="rounded-2xl border border-dashed border-white/10 bg-white/[0.02] p-10 text-center text-white/60">
      <div className="mx-auto mb-4 grid h-16 w-16 place-items-center rounded-full bg-gradient-to-br from-emerald-400/40 to-cyan-400/40 text-2xl">
        ◈
      </div>
      <p className="text-sm">
        {hasRoles
          ? 'Pick a role and a candidate above to compose a reference sheet.'
          : 'No roles yet — head to Roles, create a role and shortlist a candidate to unlock the reference sheet.'}
      </p>
      {!hasRoles && (
        <Link
          href="/roles"
          className="mt-4 inline-flex items-center gap-2 rounded-lg border border-white/10 bg-white/5 px-4 py-2 text-sm text-white hover:bg-white/10"
        >
          Go to Roles →
        </Link>
      )}
    </div>
  );
}

// ─────────── hero ───────────

function Hero({
  bundle,
  report,
  verdictHex,
  hasInterview,
}: {
  bundle: ReferenceBundle;
  report: ReferenceReport | null;
  verdictHex: string;
  hasInterview: boolean;
}) {
  const projected = report?.projectedComposite ?? bundle.interviewComposite ?? 0;
  const suffix = bundle.interviewComposite != null ? '' : '';
  return (
    <div
      className="relative overflow-hidden rounded-3xl border border-white/10 bg-neutral-950/60 p-6 md:p-8"
      style={{
        boxShadow: `inset 0 0 100px -30px ${verdictHex}55`,
      }}
    >
      <div
        className="pointer-events-none absolute -right-10 -top-16 h-64 w-64 rounded-full opacity-30 blur-3xl"
        style={{ background: verdictHex }}
      />
      <div
        className="pointer-events-none absolute -bottom-24 -left-16 h-64 w-64 rounded-full opacity-20 blur-3xl"
        style={{ background: TONE_HEX.violet }}
      />
      <div className="relative flex flex-col items-start gap-6 md:flex-row md:items-center">
        <ScoreRing value={projected} accent={verdictHex} label="projected" suffix={suffix} />
        <div className="flex-1 space-y-3">
          <div className="flex items-center gap-2">
            <Chip hex={verdictHex}>
              <span
                className="inline-block h-2 w-2 rounded-full"
                style={{ background: verdictHex }}
              />
              {report ? VERDICT_LABEL[report.verdict] : VERDICT_LABEL.pending}
            </Chip>
            <Chip hex={TONE_HEX.indigo}>{bundle.candidateName}</Chip>
            <Chip hex={TONE_HEX.slate}>{bundle.seniorityTier} tier</Chip>
            {hasInterview ? (
              <Chip hex={TONE_HEX.emerald}>◉ interview record on file</Chip>
            ) : (
              <Chip hex={TONE_HEX.amber}>◯ no interview record — guessing from profile</Chip>
            )}
          </div>
          <h2 className="text-xl font-semibold text-white md:text-2xl">
            {report?.headline ?? bundle.headline}
          </h2>
          <div className="flex flex-wrap gap-2">
            {bundle.slots.map((s) => (
              <Chip key={s.slotId} hex={KIND_HEX[s.kind]}>
                {KIND_LABEL[s.kind]} · {s.minutes}m · {s.questions.length}q
              </Chip>
            ))}
          </div>
          <div className="text-[11px] text-white/50">
            corpus hash <span className="font-mono">{bundle.corpusHash}</span> · same input bytes →
            same bundle bytes.
          </div>
        </div>
      </div>
    </div>
  );
}

// ─────────── slot card ───────────

function SlotCard({
  slot,
  responses,
  onAnswer,
}: {
  slot: ReferenceBundle['slots'][number];
  responses: MutableResponses;
  onAnswer: (
    question: ReferenceBundle['slots'][number]['questions'][number],
    verdict: AnswerVerdict,
    note?: string,
  ) => void;
}) {
  const kindHex = KIND_HEX[slot.kind];
  const answered = slot.questions.filter((q) => {
    const r = responses[q.id];
    return r && r.verdict !== 'pending';
  }).length;
  const total = slot.questions.length;
  const pct = total > 0 ? Math.round((100 * answered) / total) : 0;

  return (
    <div
      className="overflow-hidden rounded-2xl border border-white/10 bg-white/[0.02]"
      style={{ boxShadow: `inset 0 0 60px -30px ${kindHex}55` }}
    >
      <div
        className="flex flex-wrap items-center gap-3 border-b border-white/5 px-5 py-4"
        style={{ background: `${kindHex}0a` }}
      >
        <div
          className="grid h-8 w-8 place-items-center rounded-full text-xs font-bold"
          style={{
            background: `${kindHex}22`,
            color: kindHex,
            border: `1px solid ${kindHex}55`,
          }}
        >
          {slot.kind === 'manager' && '★'}
          {slot.kind === 'peer' && '●'}
          {slot.kind === 'report' && '↳'}
          {slot.kind === 'skip_level' && '↑'}
        </div>
        <div className="mr-auto">
          <div className="text-xs uppercase tracking-widest text-white/50">Reference slot</div>
          <div className="text-lg font-semibold text-white">{slot.label}</div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Chip hex={kindHex}>{slot.minutes} min budget</Chip>
          <Chip hex={TONE_HEX.slate}>
            {answered}/{total} answered
          </Chip>
        </div>
      </div>
      <div className="space-y-4 px-5 py-4">
        <p className="text-[13px] text-white/70">{slot.intro}</p>
        {slot.focus.length > 0 && (
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[10px] uppercase tracking-widest text-white/40">Focus dims</span>
            {slot.focus.map((f) => (
              <Chip key={f} hex={TONE_HEX.amber}>
                {f}
              </Chip>
            ))}
          </div>
        )}
        <div className="mb-2">
          <TinyBar pct={pct} hex={kindHex} />
        </div>
        <ol className="space-y-4">
          {slot.questions.map((q, idx) => {
            const resp = responses[q.id];
            const verdict = resp?.verdict ?? 'pending';
            return (
              <li
                key={q.id}
                className="rounded-xl border border-white/5 bg-white/[0.02] p-4"
                style={{
                  borderColor:
                    verdict === 'pending'
                      ? 'rgba(255,255,255,0.08)'
                      : `${TONE_HEX[ANSWER_VERDICT_TONE[verdict]]}55`,
                }}
              >
                <div className="mb-2 flex items-start gap-2">
                  <span className="min-w-[24px] rounded bg-white/5 px-1 text-center text-[11px] font-mono text-white/60">
                    {idx + 1}
                  </span>
                  <div className="flex-1">
                    <div className="flex flex-wrap items-center gap-2 text-[11px]">
                      <Chip hex={kindHex} tight>
                        {QUESTION_KIND_LABEL[q.kind]}
                      </Chip>
                      {q.linkedClaimId && (
                        <Chip hex={TONE_HEX.cyan} tight>
                          claim
                        </Chip>
                      )}
                      {q.linkedFlagDim && (
                        <Chip hex={TONE_HEX.amber} tight>
                          flag · {q.linkedFlagDim}
                        </Chip>
                      )}
                      <span className="text-[10px] text-white/40">priority {q.priority.toFixed(2)}</span>
                    </div>
                    <p className="mt-1 text-[13px] font-medium leading-snug text-white">
                      {q.text}
                    </p>
                    {q.hint && (
                      <p className="mt-1 text-[11px] italic text-white/45">{q.hint}</p>
                    )}
                  </div>
                </div>
                <div className="mt-3 flex flex-wrap items-center gap-1">
                  {ANSWER_VERDICT_ORDER.map((v) => {
                    const hex = TONE_HEX[ANSWER_VERDICT_TONE[v]];
                    const active = verdict === v;
                    return (
                      <button
                        key={v}
                        type="button"
                        onClick={() => onAnswer(q, v, resp?.note)}
                        className="rounded-full px-2.5 py-1 text-[11px] font-medium transition-colors"
                        style={{
                          background: active ? `${hex}30` : 'rgba(255,255,255,0.04)',
                          color: active ? hex : 'rgba(255,255,255,0.65)',
                          border: `1px solid ${active ? hex + 'aa' : 'rgba(255,255,255,0.08)'}`,
                        }}
                      >
                        {ANSWER_VERDICT_LABEL[v]}
                      </button>
                    );
                  })}
                </div>
                {verdict !== 'pending' && (
                  <textarea
                    value={resp?.note ?? ''}
                    onChange={(e) => onAnswer(q, verdict, e.target.value)}
                    placeholder="What did they actually say? (optional — pasted into markdown export)"
                    className="mt-2 h-16 w-full rounded-lg border border-white/10 bg-neutral-900/70 px-2 py-1.5 text-[12px] text-white/85 focus:border-white/30 focus:outline-none"
                  />
                )}
              </li>
            );
          })}
        </ol>
      </div>
    </div>
  );
}

// ─────────── side panels ───────────

function ClaimPanel({ bundle, report }: { bundle: ReferenceBundle; report: ReferenceReport | null }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.02] p-4">
      <SectionTitle
        title="Claims to corroborate"
        sub={`${bundle.claims.length} extracted from profile & panel signals`}
      />
      {bundle.claims.length === 0 && (
        <p className="text-[12px] text-white/40">No corroborable claims in this candidate profile.</p>
      )}
      <ul className="space-y-2">
        {bundle.claims.slice(0, 10).map((c) => {
          const status = report?.claimStatus.find((cs) => cs.claimId === c.id);
          const statusKey = status?.status ?? 'unknown';
          const statusHex = CLAIM_STATUS_HEX[statusKey] ?? TONE_HEX.slate;
          return (
            <li
              key={c.id}
              className="rounded-xl border border-white/5 bg-white/[0.02] p-3"
              style={{ borderColor: `${statusHex}33` }}
            >
              <div className="flex flex-wrap items-center gap-1">
                <Chip hex={TONE_HEX.indigo} tight>
                  {c.kind}
                </Chip>
                <Chip hex={statusHex} tight>
                  {statusKey}
                </Chip>
                <span className="ml-auto text-[10px] font-mono text-white/40">
                  w {c.weight.toFixed(2)}
                </span>
              </div>
              <p className="mt-1 text-[12px] leading-snug text-white/80">{c.text}</p>
              {status && status.matches > 0 && (
                <div className="mt-2 flex items-center gap-2 text-[10px] text-white/50">
                  <span>✔ {status.corroborated}</span>
                  <span>⚠ {status.concerned}</span>
                  <span>✖ {status.contradicted}</span>
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function FlagPanel({ bundle, report }: { bundle: ReferenceBundle; report: ReferenceReport | null }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.02] p-4">
      <SectionTitle
        title="Rubric flags to probe"
        sub={`${bundle.redFlags.length} flag${bundle.redFlags.length !== 1 ? 's' : ''} from the interview record`}
      />
      {bundle.redFlags.length === 0 && (
        <p className="text-[12px] text-white/40">
          No red flags — panel scored every high-weight dim at 4+.
        </p>
      )}
      <ul className="space-y-2">
        {bundle.redFlags.map((f) => {
          const sevHex = SEVERITY_HEX[f.severity] ?? TONE_HEX.slate;
          const status = report?.flagStatus.find((fs) => fs.dim === f.dim);
          const statusKey = status?.status ?? 'unknown';
          const statusHex = CLAIM_STATUS_HEX[statusKey] ?? TONE_HEX.slate;
          return (
            <li
              key={f.dim}
              className="rounded-xl border border-white/5 bg-white/[0.02] p-3"
              style={{ borderColor: `${sevHex}33` }}
            >
              <div className="flex flex-wrap items-center gap-1">
                <Chip hex={sevHex} tight>
                  {f.severity}
                </Chip>
                <Chip hex={statusHex} tight>
                  {statusKey}
                </Chip>
                <span className="ml-auto text-[10px] font-mono text-white/40">
                  w {f.weight.toFixed(2)}
                </span>
              </div>
              <p className="mt-1 text-[12px] font-medium text-white">{f.dimLabel}</p>
              <p className="text-[11px] text-white/50">
                panel rating: {f.latestRating != null ? `${f.latestRating}/5` : 'no rating'}
                {f.stage ? ` · ${f.stage}` : ''}
              </p>
              {status && status.matches > 0 && (
                <div className="mt-2 flex items-center gap-2 text-[10px] text-white/50">
                  <span>✔ {status.corroborated}</span>
                  <span>⚠ {status.concerned}</span>
                  <span>✖ {status.contradicted}</span>
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function ActionsPanel({
  bundle,
  report,
  copied,
  onCopyMd,
  onCopyJson,
  onReset,
}: {
  bundle: ReferenceBundle;
  report: ReferenceReport | null;
  copied: null | 'md' | 'json';
  onCopyMd: () => void;
  onCopyJson: () => void;
  onReset: () => void;
}) {
  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.02] p-4">
      <SectionTitle title="Actions" sub="Export the sheet · reset responses" />
      <div className="flex flex-col gap-2">
        <button
          type="button"
          onClick={onCopyMd}
          className="rounded-lg border border-emerald-400/40 bg-emerald-400/10 px-3 py-2 text-sm text-emerald-200 transition-colors hover:bg-emerald-400/20"
        >
          {copied === 'md' ? '✓ Markdown copied' : '📋 Copy markdown reference sheet'}
        </button>
        <button
          type="button"
          onClick={onCopyJson}
          className="rounded-lg border border-cyan-400/40 bg-cyan-400/10 px-3 py-2 text-sm text-cyan-200 transition-colors hover:bg-cyan-400/20"
        >
          {copied === 'json' ? '✓ JSON copied' : '↧ Copy JSON envelope (bundle + report)'}
        </button>
        <button
          type="button"
          onClick={onReset}
          className="rounded-lg border border-rose-400/30 bg-rose-500/5 px-3 py-2 text-sm text-rose-200/80 transition-colors hover:bg-rose-500/15"
        >
          ✕ Reset responses for this candidate
        </button>
      </div>
      <div className="mt-3 space-y-1 text-[11px] text-white/45">
        <div>
          {report ? report.totalAnswered : 0}/{bundle.totalQuestions} questions answered
        </div>
        <div>{bundle.totalMinutes} minutes total across {bundle.slots.length} references</div>
        <div className="pt-2 border-t border-white/5">
          <span className="font-mono">{bundle.bundleVersion}</span>
        </div>
      </div>
    </div>
  );
}

// ─────────── footer ───────────

function Footer() {
  return (
    <footer className="mt-10 flex flex-wrap items-center justify-between gap-4 border-t border-white/5 pt-6 text-[11px] text-white/50">
      <div className="flex items-center gap-2">
        <span
          className="inline-block h-1.5 w-1.5 rounded-full"
          style={{ background: TONE_HEX.emerald, boxShadow: `0 0 8px ${TONE_HEX.emerald}` }}
        />
        Reference — Day 82. Deterministic composer. Same input bytes → same bundle bytes.
      </div>
      <div className="flex items-center gap-3">
        <Link href="/brief" className="hover:text-white/80">
          ← Brief
        </Link>
        <span className="text-white/20">|</span>
        <Link href="/verdict" className="hover:text-white/80">
          Verdict
        </Link>
        <span className="text-white/20">|</span>
        <Link href="/hindsight" className="hover:text-white/80">
          Hindsight →
        </Link>
      </div>
    </footer>
  );
}
