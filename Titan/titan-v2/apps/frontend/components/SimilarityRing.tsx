type Grade = "exact" | "strong" | "medium" | "weak" | "none";

const GRADE_COLOR: Record<Grade, string> = {
  exact: "#ef4444",
  strong: "#fb923c",
  medium: "#fbbf24",
  weak: "#2dd4bf",
  none: "rgba(255,255,255,0.18)",
};

const GRADE_LABEL: Record<Grade, string> = {
  exact: "exact",
  strong: "strong",
  medium: "medium",
  weak: "weak",
  none: "—",
};

export default function SimilarityRing({
  similarity,
  grade,
  size = 74,
}: {
  similarity: number;
  grade: Grade;
  size?: number;
}) {
  const pct = Math.max(0, Math.min(1, similarity));
  const color = GRADE_COLOR[grade];
  const ring = `conic-gradient(${color} ${pct * 360}deg, rgba(255,255,255,0.06) 0)`;
  return (
    <div
      className="relative grid place-items-center rounded-full"
      style={{ width: size, height: size, background: ring }}
    >
      <div
        className="absolute inset-[5px] rounded-full"
        style={{ background: "rgba(7,11,20,0.85)" }}
      />
      <div className="relative text-center leading-none">
        <div
          className="font-semibold tabular-nums tracking-tight"
          style={{ color, fontSize: size * 0.24 }}
        >
          {(pct * 100).toFixed(0)}%
        </div>
        <div
          className="mt-0.5 uppercase tracking-[0.18em] text-white/55"
          style={{ fontSize: size * 0.11 }}
        >
          {GRADE_LABEL[grade]}
        </div>
      </div>
    </div>
  );
}

export const GRADE_TINT: Record<Grade, string> = {
  exact: "border-rose-400/45 bg-rose-500/10 text-rose-300",
  strong: "border-orange-400/45 bg-orange-500/10 text-orange-300",
  medium: "border-amber-400/45 bg-amber-500/10 text-amber-300",
  weak: "border-teal-400/35 bg-teal-500/[0.08] text-teal-300",
  none: "border-white/10 bg-white/[0.03] text-white/50",
};
