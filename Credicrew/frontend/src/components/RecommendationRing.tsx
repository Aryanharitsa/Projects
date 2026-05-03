'use client';
import {
  RECOMMENDATION_LABEL,
  RECOMMENDATION_TONE,
  type Recommendation,
} from '@/lib/interview';

const TONE_HEX: Record<string, string> = {
  rose: '#fb7185',
  amber: '#fbbf24',
  sky: '#7dd3fc',
  indigo: '#818cf8',
  emerald: '#34d399',
};

export default function RecommendationRing({
  composite,
  recommendation,
  ratedCount,
  totalCount,
  size = 124,
  thickness = 9,
}: {
  composite: number;
  recommendation: Recommendation;
  ratedCount: number;
  totalCount: number;
  size?: number;
  thickness?: number;
}) {
  const tone = RECOMMENDATION_TONE[recommendation];
  const color = TONE_HEX[tone] ?? '#a78bfa';
  const dashStyle = ratedCount === 0 ? 'striped' : 'solid';
  const innerSize = size - thickness * 2;

  return (
    <div className="flex items-center gap-4">
      <div
        className="relative grid place-items-center"
        style={{
          width: size,
          height: size,
          borderRadius: '9999px',
          background:
            dashStyle === 'striped'
              ? `conic-gradient(rgba(255,255,255,0.12) 0 100%)`
              : `conic-gradient(${color} ${composite}%, rgba(255,255,255,0.08) 0)`,
          boxShadow: dashStyle === 'striped' ? 'none' : `0 0 24px ${color}30`,
        }}
      >
        <div
          className="absolute grid place-items-center rounded-full bg-[#0b0b12] text-center"
          style={{ width: innerSize, height: innerSize }}
        >
          <div>
            <div className="text-[10px] uppercase tracking-wider text-white/40">
              composite
            </div>
            <div className="text-3xl font-semibold" style={{ color }}>
              {ratedCount === 0 ? '—' : composite}
            </div>
            <div className="text-[10px] text-white/45">
              {ratedCount}/{totalCount} rated
            </div>
          </div>
        </div>
      </div>
      <div className="min-w-0">
        <div className="text-[10px] uppercase tracking-wider text-white/40">
          recommendation
        </div>
        <div className="mt-1 inline-flex items-center gap-2 rounded-full px-2.5 py-1 text-xs font-medium"
          style={{
            color,
            background: `${color}1c`,
            border: `1px solid ${color}50`,
          }}
        >
          <span className="h-1.5 w-1.5 rounded-full" style={{ background: color }} />
          {RECOMMENDATION_LABEL[recommendation]}
        </div>
        <div className="mt-2 text-xs text-white/50">
          {ratedCount === 0
            ? 'Rate at least one dimension to lock in a signal.'
            : ratedCount < totalCount
              ? `${totalCount - ratedCount} dimension${totalCount - ratedCount === 1 ? '' : 's'} unrated — composite reflects what is filled in.`
              : 'All dimensions rated. Final composite locked.'}
        </div>
      </div>
    </div>
  );
}
