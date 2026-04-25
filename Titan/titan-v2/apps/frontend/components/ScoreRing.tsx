type Band = "low" | "medium" | "high" | "critical";

const COLOR: Record<Band, string> = {
  low: "#22d3a8",
  medium: "#fbbf24",
  high: "#fb923c",
  critical: "#ef4444",
};

export default function ScoreRing({
  score,
  band,
  size = 84,
}: {
  score: number;
  band: Band;
  size?: number;
}) {
  const pct = Math.max(0, Math.min(100, score));
  const color = COLOR[band];
  const ring = `conic-gradient(${color} ${pct * 3.6}deg, rgba(255,255,255,0.06) 0)`;
  return (
    <div
      className="relative grid place-items-center rounded-full"
      style={{ width: size, height: size, background: ring }}
    >
      <div
        className="absolute inset-[6px] rounded-full"
        style={{ background: "rgba(7,11,20,0.85)" }}
      />
      <div className="relative text-center leading-none">
        <div className="text-[20px] font-semibold tracking-tight" style={{ color }}>
          {score.toFixed(0)}
        </div>
        <div className="mt-0.5 text-[9px] uppercase tracking-[0.18em] text-white/55">
          {band}
        </div>
      </div>
    </div>
  );
}
