'use client';
import { useMemo, useState } from 'react';
import CandidateCard from '@/components/CandidateCard';
import { candidates } from '@/data/candidates';
import { matchCandidate, planQuery } from '@/lib/match';

export default function Discover() {
  const [q, setQ] = useState('');
  const [minScore, setMinScore] = useState(0);

  const { plan, ranked, bandCounts } = useMemo(() => {
    const plan = planQuery(q);
    const isActive =
      q.trim().length > 0 &&
      (plan.skills.length > 0 || plan.location || plan.seniority);

    const rows = candidates.map(c => {
      if (isActive) {
        const m = matchCandidate(plan, c);
        return { c, match: m, display: m.score };
      }
      const hay = [
        c.name, c.role, c.location, c.headline,
        ...(c.tags || []), ...(c.keywords || []),
      ].join(' ').toLowerCase();
      const ok = !q.trim() || hay.includes(q.trim().toLowerCase());
      return ok ? { c, match: undefined, display: c.score } : null;
    }).filter(Boolean) as { c: any; match?: any; display: number }[];

    const filtered = rows.filter(r => r.display >= minScore);
    filtered.sort((a, b) => b.display - a.display);

    const counts = { strong: 0, solid: 0, weak: 0 };
    for (const r of filtered) {
      if (r.display >= 80) counts.strong++;
      else if (r.display >= 60) counts.solid++;
      else counts.weak++;
    }
    return { plan, ranked: filtered, bandCounts: counts };
  }, [q, minScore]);

  const isActive = plan.skills.length > 0 || plan.location || plan.seniority;

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
            <a href="/" className="hover:text-white">Discover</a>
            <a href="/pipeline" className="hover:text-white">Pipeline</a>
            <a href="/submit" className="hover:text-white">Submit</a>
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
              </div>
            )}
          </div>
        </section>

        <div className="mt-8 flex items-center justify-between text-sm">
          <div className="text-white/60">
            Showing {ranked.length} of {candidates.length}
          </div>
          {isActive && (
            <div className="flex items-center gap-3 text-xs">
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
            </div>
          )}
        </div>

        <div className="mt-4 grid gap-5 md:grid-cols-2 lg:grid-cols-3">
          {ranked.map(r => (
            <CandidateCard key={r.c.id} c={r.c} match={r.match} />
          ))}
        </div>

        {ranked.length === 0 && (
          <div className="mt-16 text-center text-white/50">
            No candidates above the minimum score. Try lowering the threshold or broadening the query.
          </div>
        )}
      </div>
    </main>
  );
}
