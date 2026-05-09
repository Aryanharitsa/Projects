'use client';

import type { DecisionSummary, DimStat } from '@/lib/decision';
import { ratingHue } from '@/lib/decision';

type Props = {
  summary: DecisionSummary;
  selected: number | null;
  pinned: Set<number>;
  onSelect: (cid: number) => void;
  onTogglePin: (cid: number) => void;
  sortDim: string | null;
  onSortDim: (key: string | null) => void;
};

const RATING_LABEL: Record<number, string> = {
  1: 'No signal',
  2: 'Below bar',
  3: 'On bar',
  4: 'Above bar',
  5: 'Stretch',
};

export default function DecisionMatrix({
  summary,
  selected,
  pinned,
  onSelect,
  onTogglePin,
  sortDim,
  onSortDim,
}: Props) {
  const { rubric, dimStats, verdicts } = summary;
  const dimByKey: Record<string, DimStat> = {};
  for (const d of dimStats) dimByKey[d.key] = d;

  // Re-sort verdicts when a dim is selected for sort.
  const ordered = sortDim
    ? [...verdicts].sort((a, b) => {
        const ar = a.ratingsByDim[sortDim] ?? -1;
        const br = b.ratingsByDim[sortDim] ?? -1;
        if (br !== ar) return br - ar;
        return b.hireSignal - a.hireSignal;
      })
    : verdicts;

  if (rubric.length === 0) {
    return (
      <div className="cc-empty rounded-2xl border border-dashed border-white/10 bg-white/[0.02] p-10 text-center">
        <p className="text-sm text-white/60">
          No interview rubrics yet. Start an interview from the role&apos;s shortlist
          to populate the matrix.
        </p>
      </div>
    );
  }

  return (
    <div className="cc-matrix overflow-hidden rounded-2xl border border-white/10 bg-white/[0.03]">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[640px] table-fixed border-collapse text-left text-sm">
          <thead>
            <tr>
              <th className="sticky left-0 z-10 w-44 bg-[#0c0c14] px-3 py-2.5 text-[10px] uppercase tracking-wider text-white/45">
                Rubric dim
              </th>
              {ordered.map(v => (
                <th
                  key={v.candidateId}
                  scope="col"
                  className={`min-w-[112px] px-2 py-2.5 align-bottom ${
                    selected === v.candidateId
                      ? 'bg-white/[0.07]'
                      : pinned.has(v.candidateId) ? 'bg-violet-500/10' : ''
                  }`}
                >
                  <button
                    type="button"
                    onClick={() => onSelect(v.candidateId)}
                    className="flex w-full flex-col items-start gap-0.5 text-left text-[11px] leading-tight text-white/80 hover:text-white"
                    title={`Open ${v.name}`}
                  >
                    <span className="text-[9px] uppercase tracking-wider text-white/40">
                      #{v.rank}
                    </span>
                    <span className="line-clamp-2 font-medium text-white">{v.name}</span>
                    <span className="font-mono text-[10px] text-white/55">
                      sig {v.hireSignal}
                      {v.composite !== null ? ` · c${v.composite}` : ''}
                    </span>
                  </button>
                  <button
                    type="button"
                    onClick={() => onTogglePin(v.candidateId)}
                    className={`mt-1 inline-flex items-center justify-center rounded-full border px-1.5 py-0.5 text-[9px] uppercase tracking-wider transition ${
                      pinned.has(v.candidateId)
                        ? 'border-violet-400/60 bg-violet-400/15 text-violet-100'
                        : 'border-white/15 bg-white/5 text-white/55 hover:bg-white/10'
                    }`}
                    title="Pin to compare side-by-side"
                  >
                    {pinned.has(v.candidateId) ? '★ pinned' : '☆ pin'}
                  </button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rubric.map(dim => {
              const stat = dimByKey[dim.key];
              const isSorted = sortDim === dim.key;
              return (
                <tr key={dim.key} className="border-t border-white/5">
                  <th
                    scope="row"
                    className="sticky left-0 z-10 w-44 bg-[#0c0c14] px-3 py-2 text-left align-top"
                  >
                    <button
                      type="button"
                      onClick={() => onSortDim(isSorted ? null : dim.key)}
                      className={`block w-full text-left text-[12px] leading-tight transition ${
                        isSorted ? 'text-indigo-200' : 'text-white/85 hover:text-white'
                      }`}
                      title={`Sort by ${dim.label}`}
                    >
                      <span className="block font-medium">
                        {dim.label}
                        {isSorted && <span className="ml-1 text-indigo-300">↓</span>}
                      </span>
                      <span className="mt-0.5 block text-[10px] text-white/45">
                        weight {Math.round(dim.weight * 100)}%
                        {stat?.mean !== null && stat?.mean !== undefined
                          ? ` · μ ${stat.mean.toFixed(1)}`
                          : ''}
                      </span>
                    </button>
                  </th>
                  {ordered.map(v => {
                    const r = v.ratingsByDim[dim.key];
                    const bg = ratingHue(r ?? null);
                    const isBest = stat?.best?.candidateId === v.candidateId;
                    return (
                      <td
                        key={v.candidateId}
                        className={`px-1 py-1 text-center align-middle ${
                          selected === v.candidateId
                            ? 'bg-white/[0.05]'
                            : pinned.has(v.candidateId) ? 'bg-violet-500/[0.06]' : ''
                        }`}
                      >
                        <button
                          type="button"
                          onClick={() => onSelect(v.candidateId)}
                          className="cc-cell relative grid h-9 w-full place-items-center rounded-lg border border-white/10 transition hover:border-white/30"
                          style={{ background: bg }}
                          title={
                            r === undefined || r === null
                              ? `${v.name} · ${dim.label}: not rated`
                              : `${v.name} · ${dim.label}: ${r} · ${RATING_LABEL[r]}`
                          }
                        >
                          {r === undefined || r === null ? (
                            <span className="text-[11px] text-white/30">—</span>
                          ) : (
                            <span className="text-[12px] font-semibold text-white drop-shadow">
                              {r}
                            </span>
                          )}
                          {isBest && r !== null && r !== undefined && (
                            <span className="absolute right-0.5 top-0.5 text-[8px] text-amber-200">
                              ★
                            </span>
                          )}
                        </button>
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="flex flex-wrap items-center gap-3 border-t border-white/10 bg-white/[0.02] px-4 py-2.5 text-[11px] text-white/60">
        <span className="text-white/45">Heatmap:</span>
        {[1, 2, 3, 4, 5].map(r => (
          <span key={r} className="inline-flex items-center gap-1.5">
            <span
              className="inline-block h-3 w-5 rounded"
              style={{ background: ratingHue(r) }}
            />
            <span className="font-mono">{r}</span>
            <span className="text-white/40">{RATING_LABEL[r]}</span>
          </span>
        ))}
        <span className="ml-auto text-white/35">
          ★ = top scorer for that dim · click a dim label to sort · click a column header to inspect
        </span>
      </div>
    </div>
  );
}
