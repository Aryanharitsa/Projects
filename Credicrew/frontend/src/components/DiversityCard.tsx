'use client';
import type { Candidate } from '@/data/candidates';
import { extractSeniority } from '@/lib/match';

type Props = {
  candidates: Candidate[];
};

const TOP_N = 5;

const PALETTE = [
  '#818cf8', // indigo
  '#a78bfa', // violet
  '#34d399', // emerald
  '#facc15', // amber
  '#f472b6', // pink
  '#60a5fa', // blue
];

function tally<T extends string>(items: T[]): { key: T; n: number }[] {
  const m = new Map<T, number>();
  for (const k of items) m.set(k, (m.get(k) ?? 0) + 1);
  return Array.from(m, ([key, n]) => ({ key, n })).sort((a, b) => b.n - a.n);
}

function donutGradient(slices: { n: number; color: string }[], total: number): string {
  if (total === 0) return 'rgba(255,255,255,0.06)';
  let acc = 0;
  const stops: string[] = [];
  for (const s of slices) {
    const start = (acc / total) * 360;
    acc += s.n;
    const end = (acc / total) * 360;
    stops.push(`${s.color} ${start}deg ${end}deg`);
  }
  return `conic-gradient(${stops.join(', ')})`;
}

function normLocation(loc: string): string {
  return loc.split(/[(]/)[0].trim();
}

export default function DiversityCard({ candidates }: Props) {
  const total = candidates.length;
  if (total === 0) return null;

  const locs = tally(candidates.map(c => normLocation(c.location)));
  const seniorities = tally(
    candidates.map(c =>
      extractSeniority(`${c.role} ${c.headline}`) ?? 'unspecified',
    ),
  );
  const skills = tally(candidates.flatMap(c => c.tags ?? []));

  const topLocs = locs.slice(0, TOP_N);
  const otherLoc = locs.slice(TOP_N).reduce((s, x) => s + x.n, 0);
  const locSlices = [
    ...topLocs.map((x, i) => ({ ...x, color: PALETTE[i % PALETTE.length] })),
    ...(otherLoc > 0 ? [{ key: 'Other', n: otherLoc, color: 'rgba(255,255,255,0.18)' }] : []),
  ];

  return (
    <section className="mt-8 rounded-2xl border border-white/10 bg-white/[0.04] p-5 shadow-sm">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <div className="text-[11px] uppercase tracking-wider text-white/50">
            Pool composition
          </div>
          <div className="text-sm text-white/80">
            {total} candidate{total === 1 ? '' : 's'} in current view
          </div>
        </div>
      </div>

      <div className="grid gap-6 md:grid-cols-3">
        {/* Locations donut */}
        <div className="flex items-center gap-4">
          <div
            className="relative h-24 w-24 shrink-0 rounded-full"
            style={{ background: donutGradient(locSlices, total) }}
            aria-label="Location distribution donut"
          >
            <div className="absolute inset-[10px] rounded-full bg-[#0b0b12]" />
            <div className="absolute inset-0 grid place-items-center">
              <div className="text-center">
                <div className="text-base font-semibold text-white">
                  {locs.length}
                </div>
                <div className="text-[10px] uppercase tracking-wider text-white/50">
                  cities
                </div>
              </div>
            </div>
          </div>
          <div className="min-w-0 flex-1">
            <div className="mb-1 text-[11px] uppercase tracking-wider text-white/50">
              Locations
            </div>
            <ul className="space-y-1 text-xs text-white/80">
              {locSlices.slice(0, 5).map(s => (
                <li
                  key={s.key as string}
                  className="flex items-center justify-between gap-2"
                >
                  <span className="flex min-w-0 items-center gap-1.5">
                    <span
                      className="h-2 w-2 shrink-0 rounded-full"
                      style={{ background: s.color }}
                    />
                    <span className="truncate">{s.key}</span>
                  </span>
                  <span className="text-white/50">{s.n}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>

        {/* Seniority bars */}
        <div>
          <div className="mb-2 text-[11px] uppercase tracking-wider text-white/50">
            Seniority
          </div>
          <ul className="space-y-2">
            {seniorities.slice(0, 6).map(s => {
              const pct = Math.round((s.n / total) * 100);
              return (
                <li key={s.key}>
                  <div className="flex items-center justify-between text-xs">
                    <span className="capitalize text-white/80">{s.key}</span>
                    <span className="text-white/50">
                      {s.n} · {pct}%
                    </span>
                  </div>
                  <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-white/5">
                    <div
                      className="h-full rounded-full bg-gradient-to-r from-indigo-400 to-violet-500"
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                </li>
              );
            })}
          </ul>
        </div>

        {/* Top skills */}
        <div>
          <div className="mb-2 text-[11px] uppercase tracking-wider text-white/50">
            Top skills
          </div>
          <ul className="space-y-2">
            {skills.slice(0, 6).map(s => {
              const pct = Math.round((s.n / total) * 100);
              return (
                <li key={s.key}>
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-white/80">{s.key}</span>
                    <span className="text-white/50">{s.n}</span>
                  </div>
                  <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-white/5">
                    <div
                      className="h-full rounded-full bg-gradient-to-r from-emerald-400 to-cyan-400"
                      style={{ width: `${Math.max(8, pct)}%` }}
                    />
                  </div>
                </li>
              );
            })}
          </ul>
        </div>
      </div>
    </section>
  );
}
