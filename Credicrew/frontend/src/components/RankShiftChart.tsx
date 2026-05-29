'use client';

import type { CandidateScore } from '@/lib/calibration';

const CLIMB = '#34d399';
const DROP = '#fb7185';
const SAME = 'rgba(255,255,255,0.28)';

function tone(shift: number): string {
  if (shift > 0) return CLIMB;
  if (shift < 0) return DROP;
  return SAME;
}

export default function RankShiftChart({ candidates }: { candidates: CandidateScore[] }) {
  const n = candidates.length;
  if (n === 0) return null;

  const topPad = 34;
  const rowH = 46;
  const H = topPad + n * rowH + 12;
  const W = 640;
  const leftX = 232;
  const rightX = 408;

  const byRaw = [...candidates].sort((a, b) => a.rawRank - b.rawRank);
  const byCal = [...candidates].sort((a, b) => a.calibratedRank - b.calibratedRank);

  const y = (rank: number) => topPad + (rank - 1) * rowH + rowH / 2;

  return (
    <div className="cc-cal-bump rounded-2xl border border-white/10 bg-white/[0.03] p-4">
      <div className="mb-1 flex flex-wrap items-center justify-between gap-2">
        <div>
          <div className="text-[11px] uppercase tracking-wider text-white/45">
            Ranking — raw vs. de-biased
          </div>
          <div className="text-base font-semibold text-white">
            Who moves when rater bias is removed
          </div>
        </div>
        <div className="flex items-center gap-3 text-[10px] text-white/55">
          <span className="inline-flex items-center gap-1"><span className="h-1.5 w-3 rounded-full" style={{ background: CLIMB }} /> climbs</span>
          <span className="inline-flex items-center gap-1"><span className="h-1.5 w-3 rounded-full" style={{ background: DROP }} /> drops</span>
          <span className="inline-flex items-center gap-1"><span className="h-1.5 w-3 rounded-full" style={{ background: SAME }} /> unchanged</span>
        </div>
      </div>

      <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ height: 'auto' }} role="img">
        <text x={leftX} y={18} textAnchor="middle" fill="rgba(255,255,255,0.5)" fontSize={12} fontWeight={600}>
          Raw composite
        </text>
        <text x={rightX} y={18} textAnchor="middle" fill="rgba(255,255,255,0.5)" fontSize={12} fontWeight={600}>
          Calibrated
        </text>

        {/* connecting curves */}
        {candidates.map(c => {
          const y1 = y(c.rawRank);
          const y2 = y(c.calibratedRank);
          const col = tone(c.rankShift);
          const midX = (leftX + rightX) / 2;
          return (
            <path
              key={`p${c.candidateId}`}
              d={`M ${leftX} ${y1} C ${midX} ${y1}, ${midX} ${y2}, ${rightX} ${y2}`}
              fill="none"
              stroke={col}
              strokeWidth={c.rankShift !== 0 ? 2.4 : 1.4}
              opacity={c.rankShift !== 0 ? 0.95 : 0.5}
            />
          );
        })}

        {/* left column (raw order) */}
        {byRaw.map(c => {
          const yy = y(c.rawRank);
          const col = tone(c.rankShift);
          return (
            <g key={`l${c.candidateId}`}>
              <text x={leftX - 14} y={yy - 4} textAnchor="end" fill="#fff" fontSize={13} fontWeight={500}>
                {c.name}
              </text>
              <text x={leftX - 14} y={yy + 11} textAnchor="end" fill="rgba(255,255,255,0.45)" fontSize={11}>
                #{c.rawRank} · {c.rawComposite ?? '—'}
              </text>
              <circle cx={leftX} cy={yy} r={5} fill={col} stroke="#0b0b12" strokeWidth={2} />
            </g>
          );
        })}

        {/* right column (calibrated order) */}
        {byCal.map(c => {
          const yy = y(c.calibratedRank);
          const col = tone(c.rankShift);
          const shiftLabel = c.rankShift === 0 ? '–' : c.rankShift > 0 ? `▲${c.rankShift}` : `▼${-c.rankShift}`;
          const deltaLabel = c.delta === 0 ? '' : ` (Δ${c.delta > 0 ? '+' : ''}${c.delta})`;
          return (
            <g key={`r${c.candidateId}`}>
              <circle cx={rightX} cy={yy} r={5} fill={col} stroke="#0b0b12" strokeWidth={2} />
              <text x={rightX + 14} y={yy - 4} textAnchor="start" fill="#fff" fontSize={13} fontWeight={500}>
                {c.name}
                <tspan fill={col} fontSize={11} fontWeight={600}>{'  '}{shiftLabel}</tspan>
              </text>
              <text x={rightX + 14} y={yy + 11} textAnchor="start" fill="rgba(255,255,255,0.45)" fontSize={11}>
                #{c.calibratedRank} · {c.calibratedComposite ?? '—'}
                <tspan fill={c.delta > 0 ? CLIMB : c.delta < 0 ? DROP : 'rgba(255,255,255,0.4)'}>{deltaLabel}</tspan>
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}
