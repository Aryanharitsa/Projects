'use client';
import Link from 'next/link';
import { useEffect, useState } from 'react';
import { isSaved, toggleSave } from '@/lib/pipeline';
import type { Candidate } from '@/data/candidates';
import type { MatchResult } from '@/lib/match';
import { scoreBand } from '@/lib/match';
import MatchExplain from '@/components/MatchExplain';

type Props = { c: Candidate; match?: MatchResult };

export default function CandidateCard({ c, match }: Props) {
  const [saved, setSaved] = useState(false);
  useEffect(() => setSaved(isSaved(c.id)), [c.id]);

  const displayScore = match ? match.score : c.score;
  const band = scoreBand(displayScore);
  const ringColor =
    band === 'strong' ? '#34d399' :
    band === 'solid'  ? '#facc15' : '#f87171';

  return (
    <div className="group rounded-2xl border border-white/10 bg-white/[0.04] p-5 shadow-sm transition hover:border-white/20 hover:bg-white/[0.06] hover:shadow-lg">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="truncate font-semibold text-white">{c.name}</div>
          <div className="mt-0.5 truncate text-xs text-white/60">
            {c.role} • {c.location}
          </div>
        </div>

        <div
          className="relative grid h-14 w-14 shrink-0 place-items-center rounded-full"
          style={{
            background: `conic-gradient(${ringColor} ${displayScore}%, rgba(255,255,255,0.08) 0)`,
          }}
        >
          <div className="absolute inset-[3px] rounded-full bg-[#0b0b12]" />
          <div className="relative text-center leading-none">
            <div
              className="text-sm font-bold"
              style={{ color: ringColor }}
            >
              {displayScore}
            </div>
            <div className="text-[9px] uppercase tracking-wider text-white/50">
              {match ? 'match' : 'rank'}
            </div>
          </div>
        </div>
      </div>

      {match && match.matchedSkills.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1">
          {match.matchedSkills.map(s => (
            <span
              key={`m-${s}`}
              className="rounded-md bg-emerald-500/15 px-2 py-0.5 text-[11px] text-emerald-200"
            >
              ✓ {s}
            </span>
          ))}
          {match.missingSkills.slice(0, 3).map(s => (
            <span
              key={`x-${s}`}
              className="rounded-md bg-rose-500/10 px-2 py-0.5 text-[11px] text-rose-300/80 line-through"
            >
              {s}
            </span>
          ))}
        </div>
      )}

      {!match && (
        <div className="mt-3 flex flex-wrap gap-1">
          {c.tags.map(t => (
            <span
              key={t}
              className="rounded-md bg-white/10 px-2 py-0.5 text-[11px] text-white/80"
            >
              {t}
            </span>
          ))}
        </div>
      )}

      <div className="mt-4 flex items-center justify-between">
        <div className="flex gap-2">
          <Link
            href={`/cv/${c.id}`}
            className="rounded-md bg-white/10 px-3 py-1.5 text-xs text-white hover:bg-white/20"
          >
            View CV
          </Link>
          <button
            onClick={() => setSaved(toggleSave(c.id).includes(c.id))}
            className={`rounded-md px-3 py-1.5 text-xs ${
              saved
                ? 'bg-emerald-500 text-black'
                : 'bg-white/10 text-white hover:bg-white/20'
            }`}
          >
            {saved ? 'Saved' : 'Save'}
          </button>
          <button className="rounded-md bg-indigo-500 px-3 py-1.5 text-xs font-medium text-black hover:bg-indigo-400">
            Outreach
          </button>
        </div>
        {match && <MatchExplain result={match} />}
      </div>
    </div>
  );
}
