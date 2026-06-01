"use client";

import type { DriftDimension } from "../lib/api";

/** 10-axis polar fingerprint. Baseline ring is the reference (always at the
 *  outer rim — "this is what the account looks like to itself"). Current
 *  ring is plotted *inwards* by `1 - score`, so a perfectly matching axis
 *  lands on the outer rim and a fully drifted axis collapses to the center.
 *  That gives the visual an immediate "where does the silhouette deviate?"
 *  read without a legend.
 */
export default function DriftRadar({
  dimensions,
  size = 280,
  accent = "#fb7185",
}: {
  dimensions: DriftDimension[];
  size?: number;
  accent?: string;
}) {
  const cx = size / 2;
  const cy = size / 2;
  const r = size * 0.36;

  const labels: Record<string, string> = {
    amount: "Amount",
    hour: "Hour",
    dow: "Day",
    direction: "Flow",
    velocity: "Velocity",
    cparty_diversity: "Concentration",
    cparty_novelty: "New cparts",
    geo: "Geo",
    round_rate: "Round",
    median_shift: "Median",
  };

  const n = dimensions.length;
  if (n === 0) return null;

  // Pre-compute polar points
  const angle = (i: number) => (Math.PI * 2 * i) / n - Math.PI / 2;
  const pt = (i: number, mag: number) => {
    const a = angle(i);
    return [cx + Math.cos(a) * r * mag, cy + Math.sin(a) * r * mag] as const;
  };

  // Baseline silhouette: always sits at the outer ring (mag = 1).
  const baselinePath = dimensions
    .map((_d, i) => {
      const [x, y] = pt(i, 1);
      return `${i === 0 ? "M" : "L"}${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ") + " Z";

  // Current silhouette: at (1 - score), so high drift collapses to the center.
  const currentPath = dimensions
    .map((d, i) => {
      const mag = Math.max(0.05, 1 - Math.min(1, d.score));
      const [x, y] = pt(i, mag);
      return `${i === 0 ? "M" : "L"}${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ") + " Z";

  // Concentric grid rings (0.25/0.5/0.75/1.0)
  const grid = [0.25, 0.5, 0.75, 1.0];

  return (
    <svg viewBox={`0 0 ${size} ${size}`} className="w-full h-auto">
      <defs>
        <radialGradient id="drift-bg" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="rgba(255,255,255,0.04)" />
          <stop offset="100%" stopColor="rgba(255,255,255,0.0)" />
        </radialGradient>
        <linearGradient id="drift-current" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor={accent} stopOpacity="0.85" />
          <stop offset="100%" stopColor="#6E5BFF" stopOpacity="0.55" />
        </linearGradient>
      </defs>

      {/* dish background */}
      <circle cx={cx} cy={cy} r={r * 1.1} fill="url(#drift-bg)" />

      {/* grid rings */}
      {grid.map((g, i) => (
        <circle
          key={i}
          cx={cx}
          cy={cy}
          r={r * g}
          fill="none"
          stroke="rgba(255,255,255,0.08)"
          strokeDasharray={g === 1 ? "0" : "2 4"}
        />
      ))}

      {/* spokes */}
      {dimensions.map((_d, i) => {
        const [x, y] = pt(i, 1);
        return (
          <line
            key={i}
            x1={cx}
            y1={cy}
            x2={x}
            y2={y}
            stroke="rgba(255,255,255,0.07)"
          />
        );
      })}

      {/* baseline silhouette (outer reference) */}
      <path
        d={baselinePath}
        fill="rgba(45,225,194,0.06)"
        stroke="rgba(45,225,194,0.45)"
        strokeWidth={1}
        strokeDasharray="3 3"
      />

      {/* current silhouette (the drift) */}
      <path
        d={currentPath}
        fill="url(#drift-current)"
        stroke={accent}
        strokeWidth={1.5}
        opacity={0.95}
      />

      {/* axis dots */}
      {dimensions.map((d, i) => {
        const mag = Math.max(0.05, 1 - Math.min(1, d.score));
        const [x, y] = pt(i, mag);
        return (
          <circle
            key={i}
            cx={x}
            cy={y}
            r={3}
            fill={accent}
            stroke="rgba(7,11,20,0.9)"
            strokeWidth={1.2}
          />
        );
      })}

      {/* labels */}
      {dimensions.map((d, i) => {
        const a = angle(i);
        const lx = cx + Math.cos(a) * (r * 1.22);
        const ly = cy + Math.sin(a) * (r * 1.22);
        const anchor =
          Math.abs(Math.cos(a)) < 0.2 ? "middle" : Math.cos(a) > 0 ? "start" : "end";
        const isHot = d.score >= 0.4;
        return (
          <text
            key={i}
            x={lx}
            y={ly}
            textAnchor={anchor as any}
            dominantBaseline="middle"
            style={{
              fontSize: 10.5,
              fontFamily: "Inter, sans-serif",
              fontWeight: isHot ? 600 : 500,
            }}
            fill={isHot ? "#fda4af" : "rgba(230,237,246,0.75)"}
          >
            {labels[d.key] ?? d.label}
          </text>
        );
      })}
    </svg>
  );
}
