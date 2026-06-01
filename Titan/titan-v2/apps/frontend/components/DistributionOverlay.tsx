"use client";

/** Renders two normalized histograms overlaid so the analyst sees
 *  baseline (teal, hollow) vs current (rose, filled) at a glance.
 *
 *  Optimised for the 24-hour and 7-day cases — both are bounded categorical
 *  axes, so we just plot bar pairs. The taller-of-the-two sets the y-scale.
 */
export default function DistributionOverlay({
  baseline,
  current,
  labels,
  height = 110,
  baselineColor = "#2DE1C2",
  currentColor = "#fb7185",
  caption,
}: {
  baseline: number[];
  current: number[];
  labels?: string[];
  height?: number;
  baselineColor?: string;
  currentColor?: string;
  caption?: string;
}) {
  const n = Math.max(baseline.length, current.length);
  if (!n) return null;
  const padded = (arr: number[]) => arr.concat(Array(Math.max(0, n - arr.length)).fill(0));
  const a = padded(baseline);
  const b = padded(current);
  const peak = Math.max(0.0001, ...a, ...b);
  const w = 100 / n;

  // Marker labels: show every kth label so 24-bar charts don't overflow.
  const showEveryK = n > 12 ? Math.ceil(n / 8) : 1;

  return (
    <div>
      <svg viewBox="0 0 100 100" preserveAspectRatio="none" style={{ width: "100%", height }}>
        {/* y-gridlines at 0.25 / 0.5 / 0.75 of peak */}
        {[0.25, 0.5, 0.75].map((g) => (
          <line
            key={g}
            x1="0"
            y1={100 - g * 92}
            x2="100"
            y2={100 - g * 92}
            stroke="rgba(255,255,255,0.06)"
            strokeWidth={0.4}
          />
        ))}

        {/* bars: baseline (hollow rectangle on top), current (filled below) */}
        {a.map((va, i) => {
          const vb = b[i];
          const x = i * w;
          // baseline bar (a) — outlined, behind
          const ha = (va / peak) * 92;
          const hb = (vb / peak) * 92;
          const ya = 100 - ha;
          const yb = 100 - hb;
          return (
            <g key={i}>
              <rect
                x={x + w * 0.08}
                y={ya}
                width={w * 0.84}
                height={ha}
                fill={baselineColor}
                fillOpacity="0.06"
                stroke={baselineColor}
                strokeOpacity="0.55"
                strokeWidth="0.4"
              />
              <rect
                x={x + w * 0.22}
                y={yb}
                width={w * 0.56}
                height={hb}
                fill={currentColor}
                fillOpacity="0.85"
              />
            </g>
          );
        })}
      </svg>
      {labels && (
        <div className="mt-1 grid text-[9px] text-white/45" style={{ gridTemplateColumns: `repeat(${n}, 1fr)` }}>
          {labels.map((l, i) => (
            <div key={i} className="text-center">
              {i % showEveryK === 0 ? l : ""}
            </div>
          ))}
        </div>
      )}
      <div className="mt-2 flex items-center gap-4 text-[11px] text-white/55">
        <span className="inline-flex items-center gap-1.5">
          <span
            className="inline-block h-2 w-3 rounded-sm border"
            style={{ borderColor: baselineColor, background: `${baselineColor}10` }}
          />
          baseline
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span
            className="inline-block h-2 w-3 rounded-sm"
            style={{ background: currentColor }}
          />
          current
        </span>
        {caption && <span className="ml-auto text-white/40">{caption}</span>}
      </div>
    </div>
  );
}
