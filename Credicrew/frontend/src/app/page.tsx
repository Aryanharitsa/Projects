'use client';
import { useMemo, useState } from 'react';
import CandidateCard from '@/components/CandidateCard';
import { candidates } from '@/data/candidates';

export default function Discover() {
  const [q, setQ] = useState('');
  const [minScore, setMinScore] = useState(75);

  const filtered = useMemo(() => {
    const query = q.trim().toLowerCase();
    return candidates.filter(c => {
      if (c.score < minScore) return false;
      if (!query) return true;
      const hay = [
        c.name, c.role, c.location,
        c.headline, ...(c.tags||[]), ...(c.keywords||[])
      ].join(' ').toLowerCase();
      return hay.includes(query);
    });
  }, [q, minScore]);

  return (
    <main className="min-h-screen bg-gradient-to-b from-[#0b0b12] to-black text-white">
      <div className="max-w-6xl mx-auto px-4 pb-24">
        <header className="flex items-center justify-between py-6">
          <div className="flex items-center gap-2">
            <div className="h-8 w-8 rounded-full bg-indigo-500 text-black grid place-items-center font-bold">F</div>
            <div className="font-semibold text-lg">Credicrew</div>
          </div>
          <nav className="flex items-center gap-6 text-sm text-white/80">
            <a href="/" className="hover:text-white">Discover</a>
            <a href="/pipeline" className="hover:text-white">Pipeline</a>
            <a href="/submit" className="hover:text-white">Submit</a>
          </nav>
        </header>

        <section className="text-center mt-6">
          <h1 className="text-3xl md:text-5xl font-semibold">
            Find great talent—<span className="text-indigo-400">fast</span>
          </h1>
          <p className="text-white/60 mt-3">Describe who you’re looking for and tune results with simple controls.</p>
        </section>

        {/* Search + filter */}
        <section className="mt-8 flex flex-col items-center gap-4">
          <div className="w-full max-w-xl bg-white/5 border border-white/10 rounded-lg p-4">
            <div className="flex gap-2">
              <input
                value={q}
                onChange={(e) => setQ(e.target.value)}
                type="text"
                placeholder="e.g. Senior backend (FastAPI + Postgres) in Bengaluru"
                className="flex-1 bg-transparent border border-white/10 rounded-md px-3 py-2 text-sm text-white placeholder-white/40 focus:outline-none"
              />
              <button
                onClick={() => setQ(q)}  // no-op; keeps button for UX
                className="px-4 py-2 rounded-md bg-indigo-500 hover:bg-indigo-400 text-black text-sm font-medium"
              >
                Search
              </button>
            </div>
            <div className="flex items-center justify-between mt-3">
              <span className="text-xs text-white/60">Min score</span>
              <input
                type="range"
                min={0}
                max={100}
                value={minScore}
                onChange={(e) => setMinScore(parseInt(e.target.value, 10))}
                className="w-3/4"
              />
              <span className="text-xs text-white/60 w-8 text-right">{minScore}</span>
            </div>
          </div>
        </section>

        <p className="text-white/60 text-sm mt-10">Showing {filtered.length} of {candidates.length}</p>

        <div className="grid gap-5 mt-4 md:grid-cols-2 lg:grid-cols-3">
          {filtered.map((c) => <CandidateCard key={c.id} c={c} />)}
        </div>
      </div>
    </main>
  );
}
