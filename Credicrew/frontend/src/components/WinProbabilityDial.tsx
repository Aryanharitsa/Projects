// SVG arc dial showing win probability, plus the factor stack underneath
// (positive contributions in green-violet, negatives in rose).
//
// The dial is a 220° arc that fills proportionally with the candidate's
// acceptance odds. Color steps through the same five bands the WinProbability
// type advertises so the visual matches the verbal verdict.

'use client';

import {
  BAND_HUE, BAND_LABEL, type WinProbability,
} from '@/lib/offer';

export default function WinProbabilityDial({
  win, size = 220,
}: { win: WinProbability; size?: number }) {
  const pct = Math.round(win.probability * 100);
  const r = size / 2 - 14;
  const cx = size / 2;
  const cy = size / 2;
  // 220° sweep, starting at -200° (lower-left), ending at +20° (lower-right)
  const startAngle = -200;
  const endAngle = 20;
  const totalArc = endAngle - startAngle;
  const valueAngle = startAngle + totalArc * win.probability;
  const hue = BAND_HUE[win.band];

  const polar = (a: number, rad = r) => {
    const rad2 = (a * Math.PI) / 180;
    return { x: cx + rad * Math.cos(rad2), y: cy + rad * Math.sin(rad2) };
  };

  const arcPath = (a0: number, a1: number, rad: number) => {
    const p0 = polar(a0, rad);
    const p1 = polar(a1, rad);
    const large = Math.abs(a1 - a0) > 180 ? 1 : 0;
    const sweep = a1 > a0 ? 1 : 0;
    return `M ${p0.x.toFixed(2)} ${p0.y.toFixed(2)} A ${rad} ${rad} 0 ${large} ${sweep} ${p1.x.toFixed(2)} ${p1.y.toFixed(2)}`;
  };

  // background and value arc
  const trackD = arcPath(startAngle, endAngle, r);
  const valueD = arcPath(startAngle, valueAngle, r);

  return (
    <div className="cc-dial flex flex-col items-center">
      <svg width={size} height={size * 0.78} viewBox={`0 0 ${size} ${size * 0.78}`}>
        <defs>
          <linearGradient id="dialGrad" gradientUnits="userSpaceOnUse"
            x1={polar(startAngle).x} y1={polar(startAngle).y}
            x2={polar(endAngle).x} y2={polar(endAngle).y}
          >
            <stop offset="0%" stopColor="#f43f5e" />
            <stop offset="30%" stopColor="#fb7185" />
            <stop offset="55%" stopColor="#facc15" />
            <stop offset="80%" stopColor="#818cf8" />
            <stop offset="100%" stopColor="#34d399" />
          </linearGradient>
        </defs>

        <path
          d={trackD}
          stroke="rgba(255,255,255,0.06)"
          strokeWidth={20}
          fill="none"
          strokeLinecap="round"
        />
        <path
          d={valueD}
          stroke="url(#dialGrad)"
          strokeWidth={20}
          fill="none"
          strokeLinecap="round"
          style={{ filter: 'drop-shadow(0 0 12px rgba(167,139,250,0.45))' }}
        />

        {/* Band markers at 25/45/65/85 */}
        {[0.25, 0.45, 0.65, 0.85].map(p => {
          const a = startAngle + totalArc * p;
          const inner = polar(a, r - 14);
          const outer = polar(a, r + 14);
          return (
            <line
              key={p}
              x1={inner.x} y1={inner.y}
              x2={outer.x} y2={outer.y}
              stroke="rgba(255,255,255,0.18)"
              strokeWidth={1.2}
            />
          );
        })}

        {/* Center value */}
        <text
          x={cx}
          y={cy - 4}
          textAnchor="middle"
          fontSize={42}
          fontWeight={700}
          fill={hue}
        >
          {pct}%
        </text>
        <text
          x={cx}
          y={cy + 22}
          textAnchor="middle"
          fontSize={11}
          letterSpacing={2}
          fill="rgba(255,255,255,0.55)"
        >
          ACCEPT PROBABILITY
        </text>
      </svg>

      <div
        className="mt-1 inline-flex items-center gap-2 rounded-full border px-3 py-1 text-[11px] font-medium"
        style={{
          background: `${hue}1a`,
          borderColor: `${hue}55`,
          color: hue,
        }}
      >
        <span className="h-1.5 w-1.5 rounded-full" style={{ background: hue }} />
        {BAND_LABEL[win.band]}
        <span className="text-white/45">· logit {win.logit.toFixed(2)}</span>
      </div>
    </div>
  );
}

export function FactorBars({ win }: { win: WinProbability }) {
  // Symmetric bar chart centered on 0 — positives grow right, negatives left.
  const max = Math.max(0.01, ...win.factors.map(f => Math.abs(f.delta)));
  return (
    <ul className="mt-2 space-y-1.5">
      {win.factors.map(f => {
        const w = (Math.abs(f.delta) / max) * 50; // up to 50% of the row
        const positive = f.delta >= 0;
        const hue = positive ? 'rgba(52,211,153,0.50)' : 'rgba(244,63,94,0.45)';
        return (
          <li key={f.key} className="cc-factor flex items-center gap-2 text-[11px]">
            <span className="w-1/2 truncate text-white/70" title={f.label}>
              {f.label}
            </span>
            <div className="relative h-2 grow rounded-full bg-white/5">
              <div className="absolute left-1/2 top-0 h-full w-px bg-white/15" />
              <div
                className="absolute top-0 h-full rounded-full"
                style={{
                  width: `${w}%`,
                  background: hue,
                  left: positive ? '50%' : `${50 - w}%`,
                }}
              />
            </div>
            <span
              className="w-12 text-right font-mono"
              style={{ color: positive ? '#34d399' : '#fb7185' }}
            >
              {f.delta >= 0 ? '+' : ''}
              {f.delta.toFixed(2)}
            </span>
          </li>
        );
      })}
    </ul>
  );
}
