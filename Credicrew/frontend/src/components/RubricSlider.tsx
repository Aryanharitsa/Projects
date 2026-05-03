'use client';
import type { DimensionScore, RubricDimension } from '@/lib/interview';

const RATING_LABEL: Record<number, string> = {
  1: 'Strong concern',
  2: 'Below bar',
  3: 'On bar',
  4: 'Above bar',
  5: 'Exceptional',
};

const RATING_HEX: Record<number, string> = {
  1: '#fb7185',
  2: '#fbbf24',
  3: '#7dd3fc',
  4: '#818cf8',
  5: '#34d399',
};

export default function RubricSlider({
  dim,
  score,
  onRate,
}: {
  dim: RubricDimension;
  score: DimensionScore;
  onRate: (rating: DimensionScore['rating']) => void;
}) {
  const r = score.rating;
  const color = r ? RATING_HEX[r] : 'rgba(255,255,255,0.18)';
  return (
    <div className="rounded-xl border border-white/10 bg-white/[0.025] p-3">
      <div className="flex items-baseline justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-white">{dim.label}</span>
            <span className="rounded-full border border-white/10 bg-white/5 px-1.5 py-0.5 text-[10px] text-white/50">
              w · {(dim.weight * 100).toFixed(0)}%
            </span>
          </div>
          <p className="mt-0.5 text-[11px] text-white/50">{dim.description}</p>
        </div>
        <div
          className="shrink-0 rounded-full px-2 py-0.5 text-[10px] font-medium"
          style={{
            color: r ? color : 'rgba(255,255,255,0.4)',
            background: r ? `${color}1c` : 'rgba(255,255,255,0.04)',
            border: `1px solid ${r ? `${color}50` : 'rgba(255,255,255,0.1)'}`,
          }}
        >
          {r ? `${r} · ${RATING_LABEL[r]}` : 'unrated'}
        </div>
      </div>
      <div className="mt-3 grid grid-cols-5 gap-1.5">
        {[1, 2, 3, 4, 5].map(n => {
          const sel = r === n;
          const hex = RATING_HEX[n];
          return (
            <button
              key={n}
              onClick={() => onRate(sel ? null : (n as 1 | 2 | 3 | 4 | 5))}
              title={`${n} · ${RATING_LABEL[n]}`}
              className={`group relative h-9 rounded-lg border text-xs font-semibold transition ${
                sel
                  ? 'text-white'
                  : 'border-white/10 bg-white/[0.02] text-white/55 hover:bg-white/[0.05] hover:text-white'
              }`}
              style={
                sel
                  ? {
                    background: `${hex}1c`,
                    borderColor: `${hex}80`,
                    color: hex,
                    boxShadow: `0 0 12px ${hex}30`,
                  }
                  : undefined
              }
            >
              {n}
            </button>
          );
        })}
      </div>
    </div>
  );
}
