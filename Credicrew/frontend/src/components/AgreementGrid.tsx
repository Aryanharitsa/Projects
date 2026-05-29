'use client';

import {
  agreementHue,
  ratingHue,
  type CellInfo,
  type Interviewer,
  type RubricLite,
} from '@/lib/calibration';

type Props = {
  cells: CellInfo[];
  candidates: { id: number; name: string }[];
  rubric: RubricLite[];
  interviewers: Interviewer[];
  selected: { candidateId: number; dimKey: string } | null;
  onSelectCell: (candidateId: number, dimKey: string) => void;
  onSetRating: (interviewerId: string, candidateId: number, dimKey: string, rating: number) => void;
};

export default function AgreementGrid({
  cells, candidates, rubric, interviewers, selected, onSelectCell, onSetRating,
}: Props) {
  const cellByKey = new Map(cells.map(c => [`${c.candidateId}|${c.dimKey}`, c]));

  const sel = selected ? cellByKey.get(`${selected.candidateId}|${selected.dimKey}`) ?? null : null;
  const selCand = selected ? candidates.find(c => c.id === selected.candidateId) : null;
  const selDim = selected ? rubric.find(d => d.key === selected.dimKey) : null;

  return (
    <div className="cc-cal-grid rounded-2xl border border-white/10 bg-white/[0.03] p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div>
          <div className="text-[11px] uppercase tracking-wider text-white/45">
            Agreement heatmap
          </div>
          <div className="text-base font-semibold text-white">
            Where the panel splits
          </div>
        </div>
        <div className="flex items-center gap-2 text-[10px] text-white/50">
          <span>disagree</span>
          <span className="h-3 w-24 rounded-full" style={{ background: 'linear-gradient(90deg, rgba(244,63,94,0.6), rgba(250,204,21,0.5), rgba(52,211,153,0.6))' }} />
          <span>agree</span>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full border-separate" style={{ borderSpacing: 4 }}>
          <thead>
            <tr>
              <th className="sticky left-0 z-10 bg-[#0b0b12] px-2 py-1 text-left text-[10px] font-medium uppercase tracking-wider text-white/40">
                Candidate
              </th>
              {rubric.map(d => (
                <th key={d.key} className="px-1 py-1 text-center text-[10px] font-medium text-white/55" style={{ minWidth: 64 }}>
                  {d.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {candidates.map(cand => (
              <tr key={cand.id}>
                <td className="sticky left-0 z-10 max-w-[140px] truncate bg-[#0b0b12] px-2 py-1 text-[12px] text-white/85">
                  {cand.name}
                </td>
                {rubric.map(d => {
                  const c = cellByKey.get(`${cand.id}|${d.key}`);
                  const isSel = selected?.candidateId === cand.id && selected?.dimKey === d.key;
                  const hot = !!c && c.n >= 2 && c.range >= 2;
                  const bg = c
                    ? (c.agreement !== null ? agreementHue(c.agreement) : 'rgba(255,255,255,0.06)')
                    : 'rgba(255,255,255,0.02)';
                  return (
                    <td key={d.key} className="p-0">
                      <button
                        type="button"
                        onClick={() => onSelectCell(cand.id, d.key)}
                        className={`cc-cal-cell relative grid h-11 w-full place-items-center rounded-md text-[12px] transition ${
                          isSel ? 'ring-2 ring-white/70' : hot ? 'ring-1 ring-rose-400/50' : ''
                        }`}
                        style={{ background: bg }}
                        title={c ? `mean ${c.mean} · ${c.n} rater${c.n === 1 ? '' : 's'}${c.agreement !== null ? ` · agreement ${(c.agreement * 100).toFixed(0)}%` : ''}` : 'No ratings yet'}
                      >
                        <span className="font-mono font-medium text-white">
                          {c ? c.mean.toFixed(1) : '·'}
                        </span>
                        {c && (
                          <span className="absolute right-1 top-0.5 text-[8px] text-white/55">{c.n}</span>
                        )}
                      </button>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Inspector */}
      {selected && selCand && selDim && (
        <div className="cc-cal-inspect mt-4 rounded-xl border border-white/10 bg-white/[0.04] p-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="text-sm font-medium text-white">
              {selCand.name} <span className="text-white/40">·</span>{' '}
              <span className="text-white/75">{selDim.label}</span>
            </div>
            <div className="flex items-center gap-3 text-[11px] text-white/60">
              <span>consensus <span className="font-mono text-white">{sel ? sel.mean.toFixed(2) : '—'}</span></span>
              {sel && sel.agreement !== null && (
                <span>agreement <span className="font-mono text-white">{(sel.agreement * 100).toFixed(0)}%</span></span>
              )}
              {sel && sel.range >= 2 && (
                <span className="rounded-full border border-rose-400/30 bg-rose-400/10 px-2 py-0.5 text-rose-200">split</span>
              )}
            </div>
          </div>

          <div className="mt-3 space-y-1.5">
            {interviewers.map(iv => {
              const existing = sel?.ratings.find(r => r.interviewerId === iv.id);
              const rating = existing?.rating ?? 0;
              return (
                <div key={iv.id} className="flex items-center justify-between gap-2">
                  <div className="min-w-0 flex-1 truncate text-[12px] text-white/80">
                    {iv.name}
                    {iv.title && <span className="ml-1.5 text-[10px] text-white/40">{iv.title}</span>}
                  </div>
                  <div className="flex shrink-0 items-center gap-1">
                    {[1, 2, 3, 4, 5].map(v => {
                      const active = rating === v;
                      return (
                        <button
                          key={v}
                          type="button"
                          onClick={() => onSetRating(iv.id, selCand.id, selDim.key, active ? 0 : v)}
                          className={`grid h-7 w-7 place-items-center rounded-md text-[12px] font-medium transition ${
                            active ? 'text-white ring-1 ring-white/60' : 'text-white/55 hover:text-white'
                          }`}
                          style={{ background: active ? ratingHue(v) : 'rgba(255,255,255,0.05)' }}
                          title={active ? 'Click to clear' : `Set ${v}`}
                        >
                          {v}
                        </button>
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>
          <div className="mt-2 text-[10px] text-white/40">
            Edit a rating to watch the bias, ranking and reliability recompute live.
          </div>
        </div>
      )}
    </div>
  );
}
