"use client";

/** Diverging-bar visualisation for a signed delta. Negative = teal (good
 * — score dropped after ablation), positive = amber (bad — score rose).
 * Centered on a 50/50 midline; bar fills outward from the midline by
 * `Math.abs(value) / max`.
 */
export default function DeltaBar({
  value,
  max = 30,
}: {
  value: number;
  max?: number;
}) {
  const m = Math.max(1, max);
  const pct = Math.max(-1, Math.min(1, value / m));
  const isNeg = pct < 0;
  const width = Math.min(48, Math.abs(pct) * 48);
  return (
    <div className="relative h-1.5 w-24 overflow-hidden rounded-full bg-white/[0.06]">
      <div className="absolute inset-y-0 left-1/2 w-px bg-white/15" />
      <div
        className="absolute inset-y-0"
        style={{
          [isNeg ? "right" : "left"]: "50%",
          width: `${width}%`,
          background: isNeg
            ? "linear-gradient(90deg, rgba(45,225,194,0.05), rgba(45,225,194,0.85))"
            : "linear-gradient(90deg, rgba(251,191,36,0.85), rgba(251,146,60,0.05))",
        }}
      />
    </div>
  );
}
