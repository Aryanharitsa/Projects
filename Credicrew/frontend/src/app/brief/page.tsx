'use client';

import Link from 'next/link';
import { useEffect, useMemo, useState, type CSSProperties } from 'react';

import { candidates as CANDIDATES } from '@/data/candidates';
import type { Role } from '@/lib/roles';
import { listRoles } from '@/lib/roles';
import type { InterviewRecord, InterviewStage } from '@/lib/interview';
import {
  STAGES,
  STAGE_LABEL,
  listInterviewsForRole,
} from '@/lib/interview';
import {
  composeBrief,
  toMarkdown,
  COVERAGE_HEX,
  COVERAGE_LABEL,
  FLAG_LABEL,
  FLAG_TONE,
  PROBE_HEX,
  PROBE_LABEL,
  type BriefBundle,
} from '@/lib/brief';

// ─────────── helpers ───────────

function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map(w => w[0]?.toUpperCase() ?? '')
    .join('');
}

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

const TONE_HEX: Record<string, string> = {
  sky: '#0ea5e9',
  indigo: '#6366f1',
  violet: '#a855f7',
  amber: '#f59e0b',
  emerald: '#10b981',
  rose: '#f43f5e',
  slate: '#94a3b8',
};

const STAGE_HEX: Record<InterviewStage, string> = {
  phone_screen: TONE_HEX.sky,
  technical: TONE_HEX.indigo,
  system_design: TONE_HEX.violet,
  behavioral: TONE_HEX.emerald,
};

// ─────────── atoms ───────────

function ScoreRing({
  value,
  accent,
  size = 176,
  label = 'match',
}: {
  value: number;
  accent: string;
  size?: number;
  label?: string;
}) {
  const clamped = Math.max(0, Math.min(100, value));
  const style: CSSProperties = {
    width: size,
    height: size,
    background: `conic-gradient(${accent} ${clamped * 3.6}deg, rgba(255,255,255,0.06) 0)`,
  };
  return (
    <div
      className="cc-br-ring relative grid place-items-center rounded-full"
      style={style}
    >
      <div
        className="grid place-items-center rounded-full bg-neutral-950/95 ring-1 ring-white/10"
        style={{ width: size - 20, height: size - 20 }}
      >
        <div className="text-center">
          <div className="text-4xl font-semibold text-white">{Math.round(clamped)}</div>
          <div className="text-[10px] uppercase tracking-widest text-white/60">{label}</div>
        </div>
      </div>
    </div>
  );
}

function TinyBar({
  pct,
  hex,
}: {
  pct: number;
  hex: string;
}) {
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

function Chip({
  hex,
  children,
}: {
  hex: string;
  children: React.ReactNode;
}) {
  return (
    <span
      className="inline-flex items-center gap-1 rounded-full border px-2 py-[2px] text-[11px] font-medium"
      style={{
        borderColor: `${hex}55`,
        background: `${hex}18`,
        color: hex,
      }}
    >
      {children}
    </span>
  );
}

function Tile({
  label,
  value,
  sub,
}: {
  label: string;
  value: string;
  sub?: string;
}) {
  return (
    <div className="cc-br-tile rounded-2xl border border-white/10 bg-white/[0.03] p-4">
      <div className="text-[10px] uppercase tracking-widest text-white/50">{label}</div>
      <div className="mt-1 text-xl font-semibold text-white">{value}</div>
      {sub ? <div className="mt-0.5 text-[11px] text-white/50">{sub}</div> : null}
    </div>
  );
}

// ─────────── selectors ───────────

function RolePicker({
  roles,
  value,
  onChange,
}: {
  roles: Role[];
  value: string | null;
  onChange: (id: string) => void;
}) {
  return (
    <select
      value={value ?? ''}
      onChange={e => onChange(e.target.value)}
      className="w-full rounded-xl border border-white/10 bg-neutral-900 px-3 py-2 text-sm text-white outline-none focus:border-white/25"
    >
      {roles.length === 0 && <option value="">No saved roles</option>}
      {roles.map(r => (
        <option key={r.id} value={r.id}>
          {r.name || 'Untitled role'} · {r.shortlist.length} on shortlist
        </option>
      ))}
    </select>
  );
}

function CandidatePicker({
  role,
  value,
  onChange,
}: {
  role: Role;
  value: number | null;
  onChange: (id: number) => void;
}) {
  const options = useMemo(() => {
    // Prefer shortlist, but fall back to all candidates if empty.
    if (role.shortlist.length === 0) return CANDIDATES.slice(0, 12);
    const shortlistIds = new Set(role.shortlist.map(e => e.candidateId));
    return CANDIDATES.filter(c => shortlistIds.has(c.id));
  }, [role]);
  useEffect(() => {
    if (value === null && options[0]) onChange(options[0].id);
  }, [value, options, onChange]);
  return (
    <select
      value={value ?? ''}
      onChange={e => onChange(Number(e.target.value))}
      className="w-full rounded-xl border border-white/10 bg-neutral-900 px-3 py-2 text-sm text-white outline-none focus:border-white/25"
    >
      {options.map(c => (
        <option key={c.id} value={c.id}>
          {c.name} · {c.role}
        </option>
      ))}
    </select>
  );
}

function StagePicker({
  value,
  onChange,
}: {
  value: InterviewStage;
  onChange: (s: InterviewStage) => void;
}) {
  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
      {STAGES.map(s => {
        const active = s === value;
        const hex = STAGE_HEX[s];
        return (
          <button
            key={s}
            onClick={() => onChange(s)}
            className="cc-br-stage rounded-xl border px-3 py-2 text-left text-sm transition"
            style={{
              borderColor: active ? `${hex}88` : 'rgba(255,255,255,0.10)',
              background: active ? `${hex}20` : 'rgba(255,255,255,0.03)',
              color: active ? hex : 'rgba(255,255,255,0.75)',
            }}
          >
            <div className="text-[10px] uppercase tracking-widest opacity-70">Stage</div>
            <div className="font-medium">{STAGE_LABEL[s]}</div>
          </button>
        );
      })}
    </div>
  );
}

// ─────────── brief cards ───────────

function CoverageStrip({ brief }: { brief: BriefBundle }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.02] p-4">
      <div className="mb-3 flex items-baseline justify-between">
        <div>
          <div className="text-[10px] uppercase tracking-widest text-white/50">Rubric coverage</div>
          <div className="text-sm text-white/80">
            {brief.dimStatuses.filter(s => s.state !== 'open').length}/{brief.dimStatuses.length} dims have prior signal
          </div>
        </div>
        <div className="flex items-center gap-2 text-[11px]">
          <Chip hex={COVERAGE_HEX.covered}>Covered</Chip>
          <Chip hex={COVERAGE_HEX.partial}>Partial</Chip>
          <Chip hex={COVERAGE_HEX.open}>Open</Chip>
        </div>
      </div>
      <div className="flex h-2.5 w-full overflow-hidden rounded-full bg-white/5">
        {brief.dimStatuses.map(d => (
          <div
            key={d.key}
            title={`${d.label} · ${COVERAGE_LABEL[d.state]}`}
            style={{
              flex: d.weight,
              background: COVERAGE_HEX[d.state],
              opacity: 0.9,
            }}
          />
        ))}
      </div>
      <div className="mt-2 grid grid-cols-2 gap-1.5 text-[11px] text-white/60 sm:grid-cols-3 md:grid-cols-4">
        {brief.dimStatuses.map(d => (
          <div key={d.key} className="flex items-center gap-1.5">
            <span
              className="h-1.5 w-1.5 rounded-full"
              style={{ background: COVERAGE_HEX[d.state] }}
            />
            <span className="truncate">{d.label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function FocusCard({ brief }: { brief: BriefBundle }) {
  const hex = STAGE_HEX[brief.stage];
  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.02] p-5">
      <div className="mb-3 flex items-baseline justify-between">
        <div>
          <div className="text-[10px] uppercase tracking-widest text-white/50">Focus this stage</div>
          <div className="text-sm text-white/80">Ordered by priority · minutes suggested</div>
        </div>
        <Chip hex={hex}>{STAGE_LABEL[brief.stage]} · {brief.timeBudgetMin}m</Chip>
      </div>
      {brief.focus.length === 0 ? (
        <div className="rounded-xl border border-emerald-400/20 bg-emerald-400/5 p-4 text-sm text-emerald-200">
          Every rubric dim already has signal — use this stage to break ties, not build coverage.
        </div>
      ) : (
        <div className="space-y-2">
          {brief.focus.map((f, i) => (
            <div
              key={f.key}
              className="cc-br-row grid grid-cols-[28px_1fr_auto] items-center gap-3 rounded-xl border border-white/10 bg-white/[0.02] p-3"
            >
              <div
                className="grid h-7 w-7 place-items-center rounded-full text-[11px] font-bold"
                style={{ background: `${hex}25`, color: hex }}
              >
                {i + 1}
              </div>
              <div className="min-w-0">
                <div className="flex items-baseline gap-2">
                  <div className="font-medium text-white">{f.label}</div>
                  <div className="text-[10px] uppercase tracking-widest text-white/40">
                    weight {Math.round(f.weight * 100)}%
                  </div>
                </div>
                <div className="mt-0.5 text-[11px] text-white/60">{f.whyLine}</div>
                <div className="mt-1.5">
                  <TinyBar pct={f.priority * 100 * 6} hex={hex} />
                </div>
              </div>
              <div className="text-right text-sm font-medium text-white/80">{f.minutes}m</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function ProbesCard({ brief }: { brief: BriefBundle }) {
  if (brief.probes.length === 0) return null;
  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.02] p-5">
      <div className="mb-3 flex items-baseline justify-between">
        <div>
          <div className="text-[10px] uppercase tracking-widest text-white/50">Signals to probe</div>
          <div className="text-sm text-white/80">Candidate-specific angles for this stage</div>
        </div>
        <span className="text-[10px] text-white/40">{brief.probes.length} probes</span>
      </div>
      <div className="space-y-2">
        {brief.probes.map((p, i) => {
          const hex = PROBE_HEX[p.kind];
          return (
            <div
              key={i}
              className="cc-br-row rounded-xl border border-white/10 bg-white/[0.02] p-3"
              style={{ borderLeft: `3px solid ${hex}` }}
            >
              <div className="flex items-baseline gap-2">
                <Chip hex={hex}>{PROBE_LABEL[p.kind]}</Chip>
                <div className="text-sm font-medium text-white">{p.angle}</div>
              </div>
              <div className="mt-1 text-[12px] text-white/65">{p.reason}</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function QuestionsCard({ brief }: { brief: BriefBundle }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.02] p-5">
      <div className="mb-3 flex items-baseline justify-between">
        <div>
          <div className="text-[10px] uppercase tracking-widest text-white/50">Questions to ask</div>
          <div className="text-sm text-white/80">
            Ranked by focus-dim weight, stage-affinity, and difficulty fit
          </div>
        </div>
        <span className="text-[10px] text-white/40">
          {brief.questions.length} of {brief.timeBudgetMin} min
        </span>
      </div>
      {brief.questions.length === 0 ? (
        <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4 text-sm text-white/60">
          No stage-fit questions yet — extend the interview kit or widen the plan skills.
        </div>
      ) : (
        <ol className="space-y-2.5">
          {brief.questions.map((q, i) => (
            <li
              key={q.id}
              className="cc-br-row rounded-xl border border-white/10 bg-white/[0.02] p-3"
            >
              <div className="flex items-baseline gap-2 text-[11px] text-white/50">
                <span className="grid h-5 w-5 place-items-center rounded-full bg-white/10 text-[10px] font-bold text-white">
                  {i + 1}
                </span>
                <span>{q.signalDim}</span>
                <span>·</span>
                <span>diff {q.difficulty}</span>
                <span>·</span>
                <span className="lowercase">from {q.source}</span>
              </div>
              <div className="mt-1 text-sm text-white/90">{q.prompt}</div>
              {q.followup && (
                <div className="mt-1 text-[12px] text-white/55">↳ {q.followup}</div>
              )}
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

function SkipCard({ brief }: { brief: BriefBundle }) {
  if (brief.doNotReCover.length === 0) return null;
  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.02] p-5">
      <div className="mb-2">
        <div className="text-[10px] uppercase tracking-widest text-white/50">Skip — already saturated</div>
        <div className="text-sm text-white/70">Prior stages closed these out; don&apos;t burn budget here.</div>
      </div>
      <div className="flex flex-wrap gap-2">
        {brief.doNotReCover.map(d => (
          <div
            key={d.key}
            className="flex items-center gap-2 rounded-full border border-emerald-400/25 bg-emerald-400/10 px-3 py-1 text-[12px]"
          >
            <span className="line-through text-white/75">{d.label}</span>
            <span className="text-[10px] text-emerald-200">
              rated {d.bestRating}/5
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function TalkingCard({ brief }: { brief: BriefBundle }) {
  if (brief.talkingPoints.length === 0) return null;
  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.02] p-5">
      <div className="mb-3">
        <div className="text-[10px] uppercase tracking-widest text-white/50">Warm-up hooks</div>
        <div className="text-sm text-white/70">Show them you actually read the profile.</div>
      </div>
      <div className="space-y-2">
        {brief.talkingPoints.map((t, i) => (
          <div key={i} className="rounded-xl border border-white/10 bg-white/[0.02] p-3">
            <div className="text-sm font-medium text-white/90">{t.hook}</div>
            <div className="mt-0.5 text-[12px] text-white/55">{t.reference}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

function FlagsCard({ brief }: { brief: BriefBundle }) {
  if (brief.flags.length === 0) return null;
  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.02] p-5">
      <div className="mb-3">
        <div className="text-[10px] uppercase tracking-widest text-white/50">Red flags</div>
        <div className="text-sm text-white/70">Watch these; hedge the offer if they don&apos;t clear.</div>
      </div>
      <div className="space-y-2">
        {brief.flags.map((f, i) => {
          const hex = TONE_HEX[FLAG_TONE[f.kind]] ?? TONE_HEX.slate;
          return (
            <div
              key={i}
              className="cc-br-row rounded-xl border border-white/10 bg-white/[0.02] p-3"
              style={{ borderLeft: `3px solid ${hex}` }}
            >
              <div className="flex items-baseline gap-2">
                <Chip hex={hex}>{FLAG_LABEL[f.kind]}</Chip>
              </div>
              <div className="mt-1 text-[12px] text-white/70">{f.detail}</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function MatchExplainMini({ brief }: { brief: BriefBundle }) {
  const factors = brief.match.factors;
  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.02] p-4">
      <div className="mb-2">
        <div className="text-[10px] uppercase tracking-widest text-white/50">Match breakdown</div>
      </div>
      <div className="space-y-1.5">
        {factors.map(f => (
          <div key={f.key} className="grid grid-cols-[1fr_auto] items-center gap-2 text-[12px]">
            <div className="truncate text-white/70">{f.label}</div>
            <div className="tabular-nums text-white/80">+{f.impact}</div>
          </div>
        ))}
      </div>
      <div className="mt-3 space-y-1.5">
        {brief.match.matchedSkills.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {brief.match.matchedSkills.map(s => (
              <span key={s} className="rounded-full border border-emerald-400/30 bg-emerald-400/10 px-2 py-[1px] text-[10px] text-emerald-200">
                ✓ {s}
              </span>
            ))}
          </div>
        )}
        {brief.match.missingSkills.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {brief.match.missingSkills.map(s => (
              <span key={s} className="rounded-full border border-rose-400/30 bg-rose-400/10 px-2 py-[1px] text-[10px] text-rose-200">
                × {s}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ─────────── empty state ───────────

function EmptyState() {
  return (
    <div className="mt-10 rounded-3xl border border-white/10 bg-white/[0.02] p-10 text-center">
      <div className="mx-auto mb-4 grid h-14 w-14 place-items-center rounded-full bg-gradient-to-br from-sky-400/30 via-indigo-500/25 to-violet-500/30 text-2xl">
        📋
      </div>
      <h2 className="text-xl font-semibold text-white">Brief has nothing to compose yet</h2>
      <p className="mx-auto mt-2 max-w-lg text-sm text-white/60">
        Save a role from the JD paste flow and shortlist a candidate — Brief will
        turn the plan + candidate + rubric coverage into a 60-second interviewer
        packet for whichever stage you&apos;re prepping for.
      </p>
      <div className="mt-5 flex justify-center gap-2">
        <Link
          href="/roles/new"
          className="rounded-full border border-white/15 bg-white/10 px-4 py-2 text-sm font-medium text-white hover:bg-white/15"
        >
          Create a role
        </Link>
        <Link
          href="/"
          className="rounded-full border border-white/15 px-4 py-2 text-sm text-white/70 hover:text-white"
        >
          Discover candidates
        </Link>
      </div>
    </div>
  );
}

// ─────────── page ───────────

export default function BriefPage() {
  const [roles, setRoles] = useState<Role[]>([]);
  const [roleId, setRoleId] = useState<string | null>(null);
  const [candidateId, setCandidateId] = useState<number | null>(null);
  const [stage, setStage] = useState<InterviewStage>('technical');
  const [interview, setInterview] = useState<InterviewRecord | null>(null);
  const [copied, setCopied] = useState<'md' | 'json' | null>(null);

  useEffect(() => {
    setRoles(listRoles());
  }, []);
  useEffect(() => {
    if (!roleId && roles[0]) setRoleId(roles[0].id);
  }, [roles, roleId]);

  const role = useMemo(
    () => roles.find(r => r.id === roleId) ?? null,
    [roles, roleId],
  );

  useEffect(() => {
    if (!role) {
      setInterview(null);
      return;
    }
    const ivs = listInterviewsForRole(role.id);
    const iv = ivs.find(x => x.candidateId === candidateId) ?? null;
    setInterview(iv);
  }, [role, candidateId]);

  const candidate = useMemo(
    () => CANDIDATES.find(c => c.id === candidateId) ?? null,
    [candidateId],
  );

  const brief = useMemo(() => {
    if (!role || !candidate) return null;
    return composeBrief({
      role: { id: role.id, name: role.name, plan: role.plan },
      candidate,
      stage,
      interview,
    });
  }, [role, candidate, stage, interview]);

  const stageHex = STAGE_HEX[stage];
  const heroStyle: CSSProperties = {
    background: `linear-gradient(135deg, ${stageHex}22, ${stageHex}0d 40%, transparent 70%)`,
    borderColor: `${stageHex}44`,
  };

  if (roles.length === 0) {
    return (
      <main className="mx-auto max-w-6xl px-4 py-10">
        <h1 className="text-2xl font-semibold text-white">Brief · Interviewer Handoff</h1>
        <p className="mt-1 text-sm text-white/60">
          A 60-second packet the interviewer opens right before the call —
          composed deterministically from the role plan, the candidate profile,
          and prior-stage rubric coverage.
        </p>
        <EmptyState />
      </main>
    );
  }

  const handleCopyMd = async () => {
    if (!brief) return;
    await copyToClipboard(toMarkdown(brief));
    setCopied('md');
    setTimeout(() => setCopied(null), 1400);
  };
  const handleCopyJson = async () => {
    if (!brief) return;
    await copyToClipboard(JSON.stringify(brief, null, 2));
    setCopied('json');
    setTimeout(() => setCopied(null), 1400);
  };
  const handleDownload = () => {
    if (!brief) return;
    const blob = new Blob([toMarkdown(brief)], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `brief-${brief.roleId}-${brief.candidateId}-${brief.stage}.md`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <main className="mx-auto max-w-6xl px-4 py-8">
      <div className="mb-5 flex items-center gap-2">
        <Link href="/roles" className="text-xs text-white/50 hover:text-white/80">
          ← Roles
        </Link>
        <span className="text-xs text-white/25">·</span>
        <span className="text-[10px] uppercase tracking-widest text-white/50">Brief</span>
        <span className="ml-2 rounded-full border border-sky-400/30 bg-gradient-to-r from-sky-400/15 to-indigo-500/15 px-2 py-[1px] text-[10px] font-medium text-sky-200">
          NEW · Day 77
        </span>
      </div>

      {/* Selectors */}
      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        <div>
          <div className="mb-1 text-[10px] uppercase tracking-widest text-white/50">Role</div>
          <RolePicker roles={roles} value={roleId} onChange={setRoleId} />
        </div>
        <div>
          <div className="mb-1 text-[10px] uppercase tracking-widest text-white/50">Candidate</div>
          {role ? (
            <CandidatePicker
              role={role}
              value={candidateId}
              onChange={setCandidateId}
            />
          ) : (
            <div className="rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-white/50">
              Pick a role first
            </div>
          )}
        </div>
        <div>
          <div className="mb-1 text-[10px] uppercase tracking-widest text-white/50">Time budget</div>
          <div className="rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-white/70">
            {brief?.timeBudgetMin ?? '—'}m · budget for {STAGE_LABEL[stage]}
          </div>
        </div>
      </div>

      <div className="mt-3">
        <div className="mb-1 text-[10px] uppercase tracking-widest text-white/50">Stage</div>
        <StagePicker value={stage} onChange={setStage} />
      </div>

      {!brief ? (
        <EmptyState />
      ) : (
        <>
          {/* Hero */}
          <section
            className="cc-br-hero mt-6 rounded-3xl border p-6"
            style={heroStyle}
          >
            <div className="grid grid-cols-1 items-center gap-6 md:grid-cols-[176px_1fr_auto]">
              <ScoreRing value={brief.match.score} accent={stageHex} />
              <div>
                <div className="flex flex-wrap items-center gap-2 text-[10px] uppercase tracking-widest text-white/50">
                  <span>Interviewer brief</span>
                  <span>·</span>
                  <span>role {brief.roleId.slice(0, 10)}…</span>
                  <span>·</span>
                  <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-[1px]`} style={{
                    borderColor: `${stageHex}55`,
                    background: `${stageHex}20`,
                    color: stageHex,
                  }}>
                    {STAGE_LABEL[brief.stage]}
                  </span>
                </div>
                <h1 className="mt-2 text-2xl font-semibold text-white sm:text-3xl">
                  {brief.headline}
                </h1>
                <div className="mt-1 text-sm text-white/70">
                  {brief.intro} · {brief.timeBudgetMin}m budget · {brief.focus.length} focus dim{brief.focus.length === 1 ? '' : 's'} · decision {brief.decisionConfidence}%
                </div>
                <div className="mt-3 flex flex-wrap gap-2">
                  <Chip hex={STAGE_HEX[brief.stage]}>criticality {brief.criticality}/100</Chip>
                  <Chip hex={COVERAGE_HEX.covered}>
                    {brief.doNotReCover.length} covered
                  </Chip>
                  <Chip hex={COVERAGE_HEX.partial}>
                    {brief.dimStatuses.filter(d => d.state === 'partial').length} partial
                  </Chip>
                  <Chip hex={COVERAGE_HEX.open}>
                    {brief.dimStatuses.filter(d => d.state === 'open').length} open
                  </Chip>
                </div>
              </div>
              <div className="flex gap-2 md:flex-col">
                <button
                  onClick={handleCopyMd}
                  className="cc-br-btn rounded-full border border-white/15 bg-white/10 px-3 py-1.5 text-xs font-medium text-white hover:bg-white/15"
                >
                  {copied === 'md' ? 'Copied' : 'Copy Markdown'}
                </button>
                <button
                  onClick={handleCopyJson}
                  className="cc-br-btn rounded-full border border-white/15 px-3 py-1.5 text-xs text-white/80 hover:text-white"
                >
                  {copied === 'json' ? 'Copied' : 'Copy JSON'}
                </button>
                <button
                  onClick={handleDownload}
                  className="cc-br-btn rounded-full border border-white/15 px-3 py-1.5 text-xs text-white/80 hover:text-white"
                >
                  Download .md
                </button>
              </div>
            </div>

            {/* Avatar tag + tiles */}
            <div className="mt-6 grid grid-cols-1 gap-3 sm:grid-cols-4">
              {brief.tiles.map(t => (
                <Tile key={t.key} label={t.label} value={t.value} sub={t.sub} />
              ))}
            </div>
          </section>

          {/* Coverage strip */}
          <section className="mt-4">
            <CoverageStrip brief={brief} />
          </section>

          {/* Grid */}
          <section className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-3">
            <div className="lg:col-span-2 space-y-4">
              <FocusCard brief={brief} />
              <ProbesCard brief={brief} />
              <QuestionsCard brief={brief} />
              <SkipCard brief={brief} />
            </div>
            <div className="space-y-4">
              <div className="rounded-2xl border border-white/10 bg-white/[0.02] p-4">
                <div className="flex items-center gap-3">
                  <div
                    className="grid h-11 w-11 place-items-center rounded-full font-bold text-white"
                    style={{ background: `${stageHex}30`, color: stageHex }}
                  >
                    {initials(brief.candidateName)}
                  </div>
                  <div>
                    <div className="text-sm font-semibold text-white">{brief.candidateName}</div>
                    <div className="text-[11px] text-white/60">
                      {candidate?.role} · {candidate?.location}
                    </div>
                  </div>
                </div>
                {candidate?.headline && (
                  <div className="mt-3 text-[12px] italic text-white/60">
                    &ldquo;{candidate.headline}&rdquo;
                  </div>
                )}
                {candidate?.tags?.length ? (
                  <div className="mt-3 flex flex-wrap gap-1">
                    {candidate.tags.slice(0, 6).map(t => (
                      <span key={t} className="rounded-full border border-white/10 bg-white/5 px-2 py-[1px] text-[10px] text-white/70">
                        {t}
                      </span>
                    ))}
                  </div>
                ) : null}
              </div>
              <MatchExplainMini brief={brief} />
              <TalkingCard brief={brief} />
              <FlagsCard brief={brief} />
            </div>
          </section>

          {/* Footer legend */}
          <section className="mt-6 rounded-2xl border border-white/10 bg-white/[0.02] p-5">
            <div className="text-[10px] uppercase tracking-widest text-white/50">
              How Brief composes
            </div>
            <div className="mt-2 grid grid-cols-1 gap-2 text-[12px] text-white/65 sm:grid-cols-2">
              <div>
                <strong className="text-white/85">Focus</strong> — priority =
                <span className="tabular-nums"> weight × gap × (0.5 + stage-affinity)</span>. Gap is 0 when a dim is
                covered, 0.4 when partial, 1 when open.
              </div>
              <div>
                <strong className="text-white/85">Probes</strong> — enumerate missing-skill,
                deepen-matched, seniority-scope, location-fit, motivation, ownership. Kind picked from
                the (plan, candidate, stage) triple.
              </div>
              <div>
                <strong className="text-white/85">Questions</strong> — from the interview kit, filtered to
                stage, ranked <span className="tabular-nums">0.55 · focus-weight + 0.25 · stage-affinity + 0.20 · difficulty-fit</span>.
              </div>
              <div>
                <strong className="text-white/85">Decision confidence</strong> —
                <span className="tabular-nums"> (covered-weight + 0.5 · partial-weight) / total-weight</span>. Same input
                bytes → same brief bytes; nothing behind an API key.
              </div>
            </div>
          </section>
        </>
      )}
    </main>
  );
}
