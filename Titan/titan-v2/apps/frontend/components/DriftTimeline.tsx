"use client";

/** Rolling-KS chart: per-day Kolmogorov-Smirnov of a trailing window
 *  against the long baseline. The shaded threshold line marks where
 *  the engine declared "drift onset" and the onset point is highlighted.
 */
export default function DriftTimeline({
  rolling,
  threshold,
  onsetDay,
  height = 130,
}: {
  rolling: { day: string; ks: number; n: number }[];
  threshold: number;
  onsetDay: string | null;
  height?: number;
}) {
  if (!rolling.length) {
    return (
      <div className="text-[12px] italic text-white/45">
        Rolling KS unavailable — current window is empty.
      </div>
    );
  }
  const n = rolling.length;
  const w = 100 / Math.max(1, n - 1);

  const points = rolling.map((p, i) => {
    const x = i * w;
    const y = 100 - Math.min(1, p.ks) * 92;
    return [x, y] as const;
  });

  const path = points
    .map(([x, y], i) => `${i === 0 ? "M" : "L"}${x.toFixed(2)},${y.toFixed(2)}`)
    .join(" ");

  // Shade-under-curve so the spikes read at a glance
  const filled =
    `M0,${(100 - 0)} ` +
    points.map(([x, y]) => `L${x.toFixed(2)},${y.toFixed(2)}`).join(" ") +
    ` L${(100).toFixed(2)},100 Z`;

  const thY = 100 - threshold * 92;
  const onsetIdx = onsetDay ? rolling.findIndex((p) => p.day === onsetDay) : -1;

  return (
    <div>
      <svg viewBox="0 0 100 100" preserveAspectRatio="none" style={{ width: "100%", height }}>
        <defs>
          <linearGradient id="drift-line" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#fb7185" stopOpacity="0.6" />
            <stop offset="100%" stopColor="#fb7185" stopOpacity="0.0" />
          </linearGradient>
        </defs>

        {/* gridlines */}
        {[0.25, 0.5, 0.75, 1.0].map((g) => (
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

        {/* threshold line */}
        <line
          x1="0"
          y1={thY}
          x2="100"
          y2={thY}
          stroke="#fbbf24"
          strokeOpacity="0.7"
          strokeWidth="0.5"
          strokeDasharray="3 3"
        />

        {/* filled area */}
        <path d={filled} fill="url(#drift-line)" />

        {/* curve */}
        <path d={path} fill="none" stroke="#fb7185" strokeWidth="0.9" />

        {/* dots */}
        {points.map(([x, y], i) => (
          <circle
            key={i}
            cx={x}
            cy={y}
            r={i === onsetIdx ? 1.6 : 1.0}
            fill={i === onsetIdx ? "#fbbf24" : "#fb7185"}
            stroke="rgba(7,11,20,0.8)"
            strokeWidth="0.3"
          />
        ))}
      </svg>
      <div className="mt-1 flex justify-between text-[10px] text-white/45">
        <span>{rolling[0]?.day}</span>
        <span>floor = {threshold.toFixed(2)}</span>
        <span>{rolling[rolling.length - 1]?.day}</span>
      </div>
    </div>
  );
}
