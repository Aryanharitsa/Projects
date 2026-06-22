import type { ProfileFactor } from "../lib/api";

/** Six-axis polar (radar) fingerprint of the customer's surface intensities.
 *
 * Each axis's outer rim is the surface's *weight* (i.e. its max possible
 * contribution); the filled polygon is the *intensity* × weight. So a
 * customer where transaction-risk is at 70% of its weight while everything
 * else is quiet has a long spoke on `transaction` and a tiny one elsewhere
 * — the shape itself communicates the risk signature at a glance.
 */
export default function FactorWheel({
  factors,
  size = 280,
}: {
  factors: ProfileFactor[];
  size?: number;
}) {
  const cx = size / 2;
  const cy = size / 2;
  const radius = (size / 2) - 38;
  const n = factors.length || 6;
  // Scale factor so the largest weight reaches the outer rim. We use a
  // single global max so axis scales are comparable (compliance teams want
  // "how much of its budget is each surface contributing?"). Highest
  // weight in the default config is 28 (transaction).
  const maxWeight = Math.max(...factors.map((f) => f.weight), 1);

  // Pre-compute axis tip + intensity point per factor.
  const axes = factors.map((f, i) => {
    const angle = (-Math.PI / 2) + (i * (2 * Math.PI)) / n;
    const tipX = cx + Math.cos(angle) * radius * (f.weight / maxWeight);
    const tipY = cy + Math.sin(angle) * radius * (f.weight / maxWeight);
    const filledR = radius * (f.weight / maxWeight) * Math.max(0, Math.min(1, f.intensity));
    const fillX = cx + Math.cos(angle) * filledR;
    const fillY = cy + Math.sin(angle) * filledR;
    const labelR = radius * (f.weight / maxWeight) + 22;
    const labX = cx + Math.cos(angle) * labelR;
    const labY = cy + Math.sin(angle) * labelR;
    return { f, angle, tipX, tipY, fillX, fillY, labX, labY };
  });

  const polygon = axes.map((a) => `${a.fillX},${a.fillY}`).join(" ");
  // Concentric reference rings at 25/50/75/100% of weight.
  const rings = [0.25, 0.5, 0.75, 1.0];

  return (
    <svg viewBox={`0 0 ${size} ${size}`} className="h-full w-full">
      <defs>
        <radialGradient id="fw-poly" cx="50%" cy="50%" r="60%">
          <stop offset="0%" stopColor="rgba(110,91,255,0.50)" />
          <stop offset="100%" stopColor="rgba(45,225,194,0.20)" />
        </radialGradient>
      </defs>

      {rings.map((r, i) => (
        <circle
          key={i}
          cx={cx}
          cy={cy}
          r={radius * r}
          fill="none"
          stroke="rgba(255,255,255,0.06)"
          strokeWidth={1}
          strokeDasharray={i === rings.length - 1 ? undefined : "3 3"}
        />
      ))}

      {axes.map((a, i) => (
        <line
          key={`axis-${i}`}
          x1={cx}
          y1={cy}
          x2={a.tipX}
          y2={a.tipY}
          stroke="rgba(255,255,255,0.08)"
          strokeWidth={1}
        />
      ))}

      <polygon
        points={polygon}
        fill="url(#fw-poly)"
        stroke="rgba(110,91,255,0.85)"
        strokeWidth={1.5}
        strokeLinejoin="round"
      />

      {axes.map((a, i) => (
        <g key={`pt-${i}`}>
          <circle cx={a.fillX} cy={a.fillY} r={3.5}
            fill={a.f.accent}
            stroke="rgba(7,11,20,0.95)"
            strokeWidth={1.5}
          />
        </g>
      ))}

      {axes.map((a, i) => (
        <g key={`lbl-${i}`}>
          <text
            x={a.labX}
            y={a.labY}
            textAnchor={
              a.labX < cx - 4 ? "end" : a.labX > cx + 4 ? "start" : "middle"
            }
            dominantBaseline="middle"
            style={{ fontSize: 10.5, fontFamily: "Inter, sans-serif" }}
            className="fill-white/65"
          >
            {a.f.label}
          </text>
          <text
            x={a.labX}
            y={a.labY + 12}
            textAnchor={
              a.labX < cx - 4 ? "end" : a.labX > cx + 4 ? "start" : "middle"
            }
            dominantBaseline="middle"
            style={{ fontSize: 9.5, fontFamily: "Inter, sans-serif", fill: a.f.accent }}
          >
            {(a.f.intensity * 100).toFixed(0)}%
          </text>
        </g>
      ))}
    </svg>
  );
}
