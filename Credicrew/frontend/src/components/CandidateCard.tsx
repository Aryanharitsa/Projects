'use client';
import Link from 'next/link';
import { useEffect, useState } from 'react';
import { isSaved, toggleSave } from '@/lib/pipeline';
import type { Candidate } from '@/data/candidates';

export default function CandidateCard({ c }: { c: Candidate }) {
  const [saved, setSaved] = useState(false);
  useEffect(() => setSaved(isSaved(c.id)), [c.id]);

  const scoreColor =
    c.score >= 85 ? 'bg-green-500 text-black' :
    c.score >= 70 ? 'bg-yellow-500 text-black' :
    'bg-red-500 text-white';

  return (
    <div className="rounded-xl border border-white/10 bg-white/5 p-4 shadow-sm hover:shadow-md transition">
      <div className="flex items-start justify-between">
        <div>
          <div className="font-semibold text-white">{c.name}</div>
          <div className="text-xs text-white/60 mt-1">{c.role} • {c.location}</div>
        </div>
        <div className={`text-xs px-2 py-1 rounded-full ${scoreColor}`}>{c.score}</div>
      </div>

      <div className="flex gap-2 mt-3 flex-wrap">
        {c.tags.map(t => (
          <span key={t} className="text-[11px] px-2 py-1 rounded-md bg-white/10 text-white/80">{t}</span>
        ))}
      </div>

      <div className="flex gap-2 mt-4">
        <Link href={`/cv/${c.id}`} className="px-3 py-2 rounded-md bg-white/10 text-white hover:bg-white/20 text-sm">View CV</Link>
        <button
          onClick={() => setSaved(toggleSave(c.id).includes(c.id))}
          className={`px-3 py-2 rounded-md text-sm ${saved ? 'bg-green-500 text-black' : 'bg-white/10 text-white hover:bg-white/20'}`}
        >
          {saved ? 'Saved' : 'Save'}
        </button>
        <button className="px-3 py-2 rounded-md bg-indigo-500 hover:bg-indigo-400 text-black text-sm">Outreach</button>
      </div>
    </div>
  );
}
