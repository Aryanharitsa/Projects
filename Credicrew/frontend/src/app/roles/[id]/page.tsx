'use client';
import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';

import { candidates } from '@/data/candidates';
import { matchCandidate, type MatchResult } from '@/lib/match';
import {
  type Role,
  type PipelineStatus,
  STATUSES,
  STATUS_LABEL,
  STATUS_TONE,
  addToShortlist,
  buildShareUrl,
  countByStatus,
  deleteRole,
  getRole,
  removeFromShortlist,
  setNote,
  setStatus,
  updateRole,
} from '@/lib/roles';
import { StatusPill, StatusSelect } from '@/components/StatusPill';
import OutreachModal from '@/components/OutreachModal';
import DiversityCard from '@/components/DiversityCard';

const TONE_BG: Record<string, string> = {
  sky: 'bg-sky-400',
  indigo: 'bg-indigo-400',
  violet: 'bg-violet-400',
  amber: 'bg-amber-400',
  emerald: 'bg-emerald-400',
  rose: 'bg-rose-400',
};

export default function RoleDetail() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const id = params?.id;

  const [role, setRole] = useState<Role | null>(null);
  const [ready, setReady] = useState(false);
  const [tab, setTab] = useState<'matches' | 'shortlist'>('matches');
  const [outreach, setOutreach] = useState<{ candidateId: number } | null>(null);
  const [shareCopied, setShareCopied] = useState(false);
  const [editingName, setEditingName] = useState(false);
  const [nameDraft, setNameDraft] = useState('');
  const [jdDraft, setJdDraft] = useState('');
  const [editingJd, setEditingJd] = useState(false);

  useEffect(() => {
    if (!id) return;
    const r = getRole(id);
    setRole(r);
    setReady(true);
    if (r) {
      setNameDraft(r.name);
      setJdDraft(r.jd);
    }
  }, [id]);

  const ranked = useMemo(() => {
    if (!role) return [];
    const plan = role.plan;
    return candidates
      .map(c => ({ c, match: matchCandidate(plan, c) }))
      .filter(x =>
        // surface anyone with at least one skill or default; show top 24
        plan.skills.length === 0 ? true : x.match.matchedSkills.length > 0 || x.match.score >= 60,
      )
      .sort((a, b) => b.match.score - a.match.score)
      .slice(0, 24);
  }, [role]);

  const shortlistDetails = useMemo(() => {
    if (!role) return [];
    return role.shortlist
      .map(e => {
        const c = candidates.find(x => x.id === e.candidateId);
        if (!c) return null;
        const match = matchCandidate(role.plan, c);
        return { entry: e, c, match };
      })
      .filter(Boolean) as {
        entry: Role['shortlist'][number];
        c: (typeof candidates)[number];
        match: MatchResult;
      }[];
  }, [role]);

  const counts = role ? countByStatus(role) : null;
  const total = role?.shortlist.length ?? 0;

  const refresh = () => id && setRole(getRole(id));

  const onAdd = (cid: number) => {
    if (!role) return;
    const r = addToShortlist(role.id, cid, 'new');
    if (r) setRole(r);
  };
  const onRemove = (cid: number) => {
    if (!role) return;
    removeFromShortlist(role.id, cid);
    refresh();
  };
  const onStatus = (cid: number, s: PipelineStatus) => {
    if (!role) return;
    setStatus(role.id, cid, s);
    refresh();
  };
  const onNote = (cid: number, note: string) => {
    if (!role) return;
    setNote(role.id, cid, note);
    refresh();
  };

  const saveName = () => {
    if (!role) return;
    const next = nameDraft.trim() || role.name;
    if (next !== role.name) updateRole(role.id, { name: next });
    setEditingName(false);
    refresh();
  };

  const saveJd = () => {
    if (!role) return;
    if (jdDraft !== role.jd) updateRole(role.id, { jd: jdDraft });
    setEditingJd(false);
    refresh();
  };

  const onShare = async () => {
    if (!role) return;
    const url = buildShareUrl(role);
    try {
      await navigator.clipboard.writeText(url);
      setShareCopied(true);
      setTimeout(() => setShareCopied(false), 1500);
    } catch {
      window.prompt('Copy this share link:', url);
    }
  };

  const onDelete = () => {
    if (!role) return;
    if (!confirm(`Delete role "${role.name}"? This can't be undone.`)) return;
    deleteRole(role.id);
    router.push('/roles');
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
          <p className="mt-2 text-white/60">It may have been deleted on this device.</p>
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

  const outreachCandidate = outreach
    ? candidates.find(c => c.id === outreach.candidateId) ?? null
    : null;
  const outreachMatch = outreachCandidate ? matchCandidate(role.plan, outreachCandidate) : undefined;

  const planChips = (
    <div className="flex flex-wrap gap-1.5">
      {role.plan.seniority && (
        <span className="rounded-full border border-indigo-400/30 bg-indigo-400/10 px-2 py-0.5 text-[11px] text-indigo-200">
          {role.plan.seniority}
        </span>
      )}
      {role.plan.skills.map(s => (
        <span
          key={s}
          className="rounded-full border border-emerald-400/30 bg-emerald-400/10 px-2 py-0.5 text-[11px] text-emerald-200"
        >
          {s}
        </span>
      ))}
      {role.plan.location && (
        <span className="rounded-full border border-amber-400/30 bg-amber-400/10 px-2 py-0.5 text-[11px] text-amber-200">
          📍 {role.plan.location}
        </span>
      )}
      {role.plan.skills.length === 0 && !role.plan.location && !role.plan.seniority && (
        <span className="text-xs text-white/40">
          No structured signals detected — try tweaking the JD.
        </span>
      )}
    </div>
  );

  return (
    <main className="min-h-screen bg-gradient-to-b from-[#0b0b12] to-black text-white">
      <div className="mx-auto max-w-6xl px-4 pb-24">
        <header className="flex items-center justify-between py-6">
          <Link href="/roles" className="text-sm text-white/60 hover:text-white">
            ← Roles
          </Link>
          <nav className="flex items-center gap-6 text-sm text-white/80">
            <Link href="/" className="hover:text-white">Discover</Link>
            <Link href="/roles" className="text-white">Roles</Link>
            <Link href="/pipeline" className="hover:text-white">Pipeline</Link>
          </nav>
        </header>

        {/* Title + actions */}
        <section className="mt-2 flex flex-wrap items-end justify-between gap-4">
          <div className="min-w-0 flex-1">
            {editingName ? (
              <input
                autoFocus
                value={nameDraft}
                onChange={e => setNameDraft(e.target.value)}
                onBlur={saveName}
                onKeyDown={e => e.key === 'Enter' && saveName()}
                className="w-full max-w-xl rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-3xl font-semibold text-white focus:border-indigo-400/60 focus:outline-none md:text-4xl"
              />
            ) : (
              <h1
                className="cursor-text text-3xl font-semibold md:text-4xl"
                onClick={() => setEditingName(true)}
                title="Click to rename"
              >
                {role.name}
              </h1>
            )}
            <div className="mt-3">{planChips}</div>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={onShare}
              className="rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-xs text-white hover:bg-white/10"
            >
              {shareCopied ? 'Link copied ✓' : 'Share link'}
            </button>
            <button
              onClick={onDelete}
              className="rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-xs text-rose-300 hover:bg-rose-500/10"
            >
              Delete
            </button>
          </div>
        </section>

        {/* Pipeline summary */}
        {total > 0 && counts && (
          <section className="mt-8 rounded-2xl border border-white/10 bg-white/[0.04] p-5">
            <div className="mb-3 flex items-center justify-between">
              <div>
                <div className="text-[11px] uppercase tracking-wider text-white/50">
                  Pipeline
                </div>
                <div className="text-sm text-white/80">
                  {total} candidate{total === 1 ? '' : 's'} shortlisted
                </div>
              </div>
              <div className="text-[11px] text-white/40">
                {role.pitch ? `Pitch: ${role.pitch.slice(0, 90)}${role.pitch.length > 90 ? '…' : ''}` : ''}
              </div>
            </div>
            <div className="flex h-2 w-full overflow-hidden rounded-full bg-white/5">
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
            <div className="mt-3 grid grid-cols-3 gap-3 md:grid-cols-6">
              {STATUSES.map(s => (
                <div
                  key={s}
                  className="rounded-lg border border-white/5 bg-white/[0.02] px-3 py-2"
                >
                  <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-white/50">
                    <span className={`h-1.5 w-1.5 rounded-full ${TONE_BG[STATUS_TONE[s]]}`} />
                    {STATUS_LABEL[s]}
                  </div>
                  <div className="mt-1 text-lg font-semibold text-white">{counts[s]}</div>
                </div>
              ))}
            </div>
          </section>
        )}

        {/* JD viewer / editor */}
        <section className="mt-6 rounded-2xl border border-white/10 bg-white/[0.04] p-5">
          <div className="mb-2 flex items-center justify-between">
            <div className="text-[11px] uppercase tracking-wider text-white/50">
              Job description
            </div>
            <button
              onClick={() => setEditingJd(v => !v)}
              className="text-[11px] text-indigo-300 hover:text-indigo-200"
            >
              {editingJd ? 'Save' : 'Edit'}
            </button>
          </div>
          {editingJd ? (
            <textarea
              value={jdDraft}
              onChange={e => setJdDraft(e.target.value)}
              onBlur={saveJd}
              rows={8}
              className="w-full rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-sm text-white focus:border-indigo-400/60 focus:outline-none"
            />
          ) : (
            <pre className="whitespace-pre-wrap font-sans text-sm leading-relaxed text-white/80">
              {role.jd || <span className="text-white/40">No JD yet — click Edit.</span>}
            </pre>
          )}
        </section>

        {/* Tabs */}
        <div className="mt-8 flex items-center gap-2 border-b border-white/10">
          <button
            onClick={() => setTab('matches')}
            className={`-mb-px border-b-2 px-3 py-2 text-sm transition ${
              tab === 'matches'
                ? 'border-indigo-400 text-white'
                : 'border-transparent text-white/60 hover:text-white'
            }`}
          >
            Matches ({ranked.length})
          </button>
          <button
            onClick={() => setTab('shortlist')}
            className={`-mb-px border-b-2 px-3 py-2 text-sm transition ${
              tab === 'shortlist'
                ? 'border-indigo-400 text-white'
                : 'border-transparent text-white/60 hover:text-white'
            }`}
          >
            Shortlist ({total})
          </button>
        </div>

        {tab === 'matches' && (
          <>
            <DiversityCard candidates={ranked.map(r => r.c)} />
            <div className="mt-6 grid gap-4 md:grid-cols-2">
              {ranked.map(({ c, match }) => {
                const isOn = role.shortlist.some(e => e.candidateId === c.id);
                const ringColor =
                  match.score >= 80 ? '#34d399' : match.score >= 60 ? '#facc15' : '#f87171';
                return (
                  <div
                    key={c.id}
                    className="flex items-start gap-4 rounded-xl border border-white/10 bg-white/[0.03] p-4"
                  >
                    <div
                      className="relative grid h-12 w-12 shrink-0 place-items-center rounded-full"
                      style={{
                        background: `conic-gradient(${ringColor} ${match.score}%, rgba(255,255,255,0.08) 0)`,
                      }}
                    >
                      <div className="absolute inset-[3px] rounded-full bg-[#0b0b12]" />
                      <div className="relative text-sm font-semibold" style={{ color: ringColor }}>
                        {match.score}
                      </div>
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="truncate font-medium">{c.name}</div>
                      <div className="text-xs text-white/60">
                        {c.role} · {c.location}
                      </div>
                      {match.matchedSkills.length > 0 && (
                        <div className="mt-1 flex flex-wrap gap-1">
                          {match.matchedSkills.map(s => (
                            <span
                              key={s}
                              className="rounded bg-emerald-500/15 px-1.5 py-0.5 text-[10px] text-emerald-200"
                            >
                              ✓ {s}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                    <div className="flex shrink-0 flex-col items-end gap-2">
                      {isOn ? (
                        <span className="rounded-md bg-emerald-500/15 px-2 py-1 text-[11px] text-emerald-200">
                          On shortlist
                        </span>
                      ) : (
                        <button
                          onClick={() => onAdd(c.id)}
                          className="rounded-md bg-indigo-500 px-2.5 py-1 text-[11px] font-medium text-black hover:bg-indigo-400"
                        >
                          + Shortlist
                        </button>
                      )}
                      <button
                        onClick={() => setOutreach({ candidateId: c.id })}
                        className="rounded-md border border-white/10 bg-white/5 px-2.5 py-1 text-[11px] text-white hover:bg-white/10"
                      >
                        Outreach
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
            {ranked.length === 0 && (
              <div className="mt-10 text-center text-white/50">
                No matches surfaced. Try refining the JD with more concrete skills.
              </div>
            )}
          </>
        )}

        {tab === 'shortlist' && (
          <>
            {shortlistDetails.length === 0 ? (
              <div className="mt-10 rounded-2xl border border-dashed border-white/10 bg-white/[0.02] p-10 text-center">
                <h2 className="text-lg font-semibold">Shortlist is empty</h2>
                <p className="mt-1 text-sm text-white/60">
                  Add candidates from the Matches tab to start the pipeline.
                </p>
                <button
                  onClick={() => setTab('matches')}
                  className="mt-5 rounded-lg bg-indigo-500 px-4 py-2 text-sm font-medium text-black hover:bg-indigo-400"
                >
                  Browse matches
                </button>
              </div>
            ) : (
              <div className="mt-6 space-y-3">
                {shortlistDetails.map(({ entry, c, match }) => (
                  <div
                    key={c.id}
                    className="rounded-xl border border-white/10 bg-white/[0.04] p-4"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="font-medium">{c.name}</span>
                          <StatusPill status={entry.status} />
                          <span className="text-xs text-white/40">· {match.score} match</span>
                        </div>
                        <div className="text-xs text-white/60">
                          {c.role} · {c.location}
                        </div>
                        {match.matchedSkills.length > 0 && (
                          <div className="mt-1 flex flex-wrap gap-1">
                            {match.matchedSkills.slice(0, 5).map(s => (
                              <span
                                key={s}
                                className="rounded bg-emerald-500/15 px-1.5 py-0.5 text-[10px] text-emerald-200"
                              >
                                ✓ {s}
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
                      <div className="flex shrink-0 flex-col items-end gap-2">
                        <StatusSelect
                          status={entry.status}
                          onChange={s => onStatus(c.id, s)}
                        />
                        <div className="flex gap-1.5">
                          <button
                            onClick={() => setOutreach({ candidateId: c.id })}
                            className="rounded-md bg-indigo-500 px-2.5 py-1 text-[11px] font-medium text-black hover:bg-indigo-400"
                          >
                            Outreach
                          </button>
                          <button
                            onClick={() => onRemove(c.id)}
                            className="rounded-md border border-white/10 bg-white/5 px-2.5 py-1 text-[11px] text-white hover:bg-rose-500/10 hover:text-rose-300"
                          >
                            Remove
                          </button>
                        </div>
                      </div>
                    </div>
                    <div className="mt-3">
                      <input
                        defaultValue={entry.note ?? ''}
                        placeholder="Add a private note (e.g. 'Follow up Tue, available 30 days')"
                        onBlur={e => onNote(c.id, e.target.value)}
                        className="w-full rounded-md border border-white/10 bg-black/30 px-3 py-1.5 text-xs text-white/80 placeholder-white/30 focus:border-indigo-400/60 focus:outline-none"
                      />
                    </div>
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </div>

      {outreachCandidate && (
        <OutreachModal
          open={!!outreach}
          onClose={() => setOutreach(null)}
          candidate={outreachCandidate}
          match={outreachMatch}
          role={{ name: role.name, plan: role.plan, pitch: role.pitch }}
        />
      )}
    </main>
  );
}
