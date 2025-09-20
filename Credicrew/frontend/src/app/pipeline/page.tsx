'use client';
import { useEffect, useState } from 'react';
import Link from 'next/link';
import { candidates } from '@/data/candidates';
import CandidateCard from '@/components/CandidateCard';
import { getSavedIds } from '@/lib/pipeline';

export default function Pipeline() {
  const [ids, setIds] = useState<number[]>([]);
  useEffect(() => setIds(getSavedIds()), []);
  const saved = candidates.filter(c => ids.includes(c.id));

  return (
    <main className="min-h-screen bg-gradient-to-b from-[#0b0b12] to-black text-white">
      <div className="max-w-6xl mx-auto px-4 pb-24">
        <header className="flex items-center justify-between py-6">
          <div className="flex items-center gap-2">
            <div className="h-8 w-8 rounded-full bg-indigo-500 text-black grid place-items-center font-bold">F</div>
            <div className="font-semibold text-lg">Credicrew</div>
          </div>
          <nav className="flex items-center gap-6 text-sm text-white/80">
            <Link href="/" className="hover:text-white">Back to Discover</Link>
          </nav>
        </header>

        <h1 className="text-2xl md:text-3xl font-semibold">Pipeline</h1>
        <p className="text-white/60 mt-2">Candidates you’ve saved from Discover.</p>

        {saved.length === 0 ? (
          <div className="mt-10 text-white/60">
            Nothing here yet. Go to <Link href="/" className="text-indigo-400 hover:underline">Discover</Link> and click <span className="text-white">Save</span>.
          </div>
        ) : (
          <div className="grid gap-5 mt-8 md:grid-cols-2 lg:grid-cols-3">
            {saved.map(c => <CandidateCard key={c.id} c={c} />)}
          </div>
        )}
      </div>
    </main>
  );
}
