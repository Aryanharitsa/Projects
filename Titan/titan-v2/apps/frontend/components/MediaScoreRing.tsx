import type { MediaGrade } from "../lib/api";

const COLOR: Record<MediaGrade, string> = {
  clear: "#22d3a8",
  elevated: "#fbbf24",
  material: "#fb923c",
  severe: "#ef4444",
};

export function gradeColor(grade: MediaGrade): string {
  return COLOR[grade] || "#94a3b8";
}

export default function MediaScoreRing({
  composite,
  grade,
  size = 84,
  thin = false,
}: {
  composite: number;
  grade: MediaGrade;
  size?: number;
  thin?: boolean;
}) {
  const pct = Math.max(0, Math.min(100, composite));
  const color = COLOR[grade];
  const ring = `conic-gradient(${color} ${pct * 3.6}deg, rgba(255,255,255,0.06) 0)`;
  const insetPx = thin ? 5 : 6;
  return (
    <div
      className="relative grid place-items-center rounded-full"
      style={{ width: size, height: size, background: ring }}
    >
      <div
        className="absolute rounded-full"
        style={{
          background: "rgba(7,11,20,0.88)",
          top: insetPx,
          left: insetPx,
          right: insetPx,
          bottom: insetPx,
        }}
      />
      <div className="relative text-center leading-none">
        <div
          className="font-semibold tracking-tight"
          style={{ color, fontSize: Math.round(size * 0.24) }}
        >
          {composite.toFixed(0)}
        </div>
        <div className="mt-0.5 text-[9px] uppercase tracking-[0.18em] text-white/55">
          {grade}
        </div>
      </div>
    </div>
  );
}
