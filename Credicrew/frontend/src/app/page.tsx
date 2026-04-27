'use client';
import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';

import CandidateCard from '@/components/CandidateCard';
import DiversityCard from '@/components/DiversityCard';
import OutreachModal from '@/components/OutreachModal';
import { candidates, type Candidate } from '@/data/candidates';
import { matchCandidate, planQuery, type MatchResult } from '@/lib/match';
import { addToShortlist, createRole, listRoles, type Role } from '@/lib/roles';

export default function Discover() {
  const router = useRouter();
  const [q, setQ] = useState('');
  const [minScore, setMinScore] = useState(0);
  const [showDiversity, setShowDiversity] = useState(true);

  const [outreach, setOutreach] = useState<{
    candidate: Candidate;
    match?: MatchResult;
  } | null>(null);

  // Roles in scope on this device — used by the per-card "Add to role" picker.
  const [roles, setRoles] = useState<Role[]>([]);
  useEffect(() => setRoles(listRoles()), []);
  const refreshRoles = () => setRoles(listRoles());

  const { plan, ranked, bandCounts, isActive } = useMemo(() => {
    const plan = planQuery(q);
    const isActive =
      q.trim().length > 0 &&
      (plan.skills.length > 0 || !!plan.location || !!plan.seniority);

    const rows = candidates
      .map(c => {
        if (isActive) {
          const m = matchCandidate(plan, c);
          return { c, match: m, display: m.score };
        }
        const hay = [
          c.name, c.role, c.location, c.headline,
          ...(c.tags || []), ...(c.keywords || []),
        ]
          .join(' ')
          .toLowerCase();
        const ok = !q.trim() || hay.includes(q.trim().toLowerCase());
        return ok ? { c, match: undefined, display: c.score } : null;
      })
      .filter(Boolean) as { c: Candidate; match?: MatchResult; display: number }[];

    const filtered = rows.filter(r => r.display >= minScore);
    filtered.sort((a, b) => b.display - a.display);

    const counts = { strong: 0, solid: 0, weak: 0 };
    for (const r of filtered) {
      if (r.display >= 80) counts.strong++;
      else if (r.display >= 60) counts.solid++;
      else counts.weak++;
    }
    return { plan, ranked: filtered, bandCounts: counts, isActive };
  }, [q, minScore]);

  const saveAsRole = () => {
    if (!isActive) return;
    const name =
      (plan.seniority ? plan.seniority[0].toUpperCase() + plan.seniority.slice(1) + ' ' : '') +
      (plan.skills[0]
        ? plan.skills[0][0].toUpperCase() + plan.skills[0].slice(1) + ' role'
        : 'Engineering role');
    const role = createRole({ name, jd: q.trim() });
    router.push(`/roles/${role.id}`);
  };

  return (
    <main className="min-h-screen bg-gradient-to-b from-[#0b0b12] to-black text-white">
      <div className="mx-auto max-w-6xl px-4 pb-24">
        <header className="flex items-center justify-between py-6">
          <div className="flex items-center gap-2">
            <div className="grid h-8 w-8 place-items-center rounded-full bg-gradient-to-br from-indigo-400 to-violet-600 font-bold text-white">
              C
            </div>
            <div className="text-lg font-semibold">Credicrew</div>
          </div>
          <nav className="flex items-center gap-6 text-sm text-white/80">
            <Link href="/" className="text-white">Discover</Link>
            <Link href="/roles" className="hover:text-white">Roles</Link>
            <Link href="/pipeline" className="hover:text-white">Pipeline</Link>
            <Link href="/submit" className="hover:text-white">Submit</Link>
          </nav>
        </header>

        <section className="mt-6 text-center">
          <h1 className="text-3xl font-semibold md:text-5xl">
            Find great talent—
            <span className="bg-gradient-to-r from-indigo-300 to-violet-400 bg-clip-text text-transparent">
              explainably
            </span>
          </h1>
          <p className="mt-3 text-white/60">
            Describe the role. We rank by skill coverage, location, and seniority—and tell you why.
          </p>
        </section>

        <section className="mt-8 flex flex-col items-center gap-4">
          <div className="w-full max-w-2xl rounded-2xl border border-white/10 bg-white/5 p-4 shadow-lg backdrop-blur">
            <input
              value={q}
              onChange={e => setQ(e.target.value)}
              type="text"
              placeholder='e.g. "Senior backend (FastAPI + Postgres) in Bengaluru"'
              className="w-full rounded-lg border border-white/10 bg-black/20 px-4 py-3 text-sm text-white placeholder-white/40 focus:border-indigo-400/60 focus:outline-none"
            />
            <div className="mt-3 flex items-center justify-between gap-4">
              <span className="text-xs text-white/60">Min score</span>
              <input
                type="range"
                min={0}
                max={100}
                value={minScore}
                onChange={e => setMinScore(parseInt(e.target.value, 10))}
                className="w-3/4 accent-indigo-400"
              />
              <span className="w-8 text-right text-xs text-white/60">{minScore}</span>
            </div>
            {isActive && (
              <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-white/10 pt-3">
                <span className="text-[11px] uppercase tracking-wider text-white/50">
                  Detected
                </span>
                {plan.seniority && (
                  <span className="rounded-full border border-indigo-400/30 bg-indigo-400/10 px-2 py-0.5 text-[11px] text-indigo-200">
                    {plan.seniority}
                  </span>
                )}
                {plan.skills.map(s => (
                  <span
                    key={s}
                    className="rounded-full border border-emerald-400/30 bg-emerald-400/10 px-2 py-0.5 text-[11px] text-emerald-200"
                  >
                    {s}
                  </span>
                ))}
                {plan.location && (
                  <span className="rounded-full border border-amber-400/30 bg-amber-400/10 px-2 py-0.5 text-[11px] text-amber-200">
                    📍 {plan.location}
                  </span>
                )}
                <button
                  onClick={saveAsRole}
                  className="ml-auto rounded-md bg-indigo-500 px-3 py-1 text-[11px] font-medium text-black hover:bg-indigo-400"
                  title="Save the current query as a Role with its own pipeline"
                >
                  💾 Save as role
                </button>
              </div>
            )}
          </div>
        </section>

        <div className="mt-8 flex items-center justify-between text-sm">
          <div className="text-white/60">
            Showing {ranked.length} of {candidates.length}
          </div>
          <div className="flex items-center gap-3 text-xs">
            {isActive && (
              <>
                <span className="inline-flex items-center gap-1 text-emerald-300">
                  <span className="h-2 w-2 rounded-full bg-emerald-400" />
                  {bandCounts.strong} strong
                </span>
                <span className="inline-flex items-center gap-1 text-amber-300">
                  <span className="h-2 w-2 rounded-full bg-amber-400" />
                  {bandCounts.solid} solid
                </span>
                <span className="inline-flex items-center gap-1 text-rose-300">
                  <span className="h-2 w-2 rounded-full bg-rose-400" />
                  {bandCounts.weak} weak
                </span>
              </>
            )}
            <button
              onClick={() => setShowDiversity(v => !v)}
              className="rounded-md border border-white/10 bg-white/5 px-2 py-1 text-white/70 hover:bg-white/10"
            >
              {showDiversity ? 'Hide' : 'Show'} composition
            </button>
          </div>
        </div>

        {showDiversity && <DiversityCard candidates={ranked.map(r => r.c)} />}

        <div className="mt-6 grid gap-5 md:grid-cols-2 lg:grid-cols-3">
          {ranked.map(r => (
            <CandidateCard
              key={r.c.id}
              c={r.c}
              match={r.match}
              roles={roles}
              onShortlist={(roleId, candidateId) => {
                addToShortlist(roleId, candidateId);
                refreshRoles();
              }}
              onOutreach={(c, m) => setOutreach({ candidate: c, match: m })}
            />
          ))}
        </div>

        {ranked.length === 0 && (
          <div className="mt-16 text-center text-white/50">
            No candidates above the minimum score. Try lowering the threshold or broadening the query.
          </div>
        )}
      </div>

      {outreach && (
        <OutreachModal
          open={true}
          onClose={() => setOutreach(null)}
          candidate={outreach.candidate}
          match={outreach.match}
          role={null}
        />
      )}
    </main>
  );
}
