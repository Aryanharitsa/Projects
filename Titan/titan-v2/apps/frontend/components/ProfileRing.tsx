import type { ProfileBucket } from "../lib/api";

const COLOR: Record<ProfileBucket, string> = {
  low: "#22d3a8",
  medium: "#fbbf24",
  high: "#fb923c",
  critical: "#ef4444",
};

export function bucketColor(bucket: ProfileBucket): string {
  return COLOR[bucket] || "#94a3b8";
}

export default function ProfileRing({
  composite,
  bucket,
  size = 132,
  engine_composite,
  label,
}: {
  composite: number;
  bucket: ProfileBucket;
  size?: number;
  engine_composite?: number;
  label?: string;
}) {
  const pct = Math.max(0, Math.min(100, composite));
  const color = COLOR[bucket];
  const ring = `conic-gradient(${color} ${pct * 3.6}deg, rgba(255,255,255,0.06) 0)`;
  const inset = Math.round(size * 0.07);
  const showOverride =
    typeof engine_composite === "number" &&
    Math.abs(engine_composite - composite) >= 0.5;
  return (
    <div
      className="relative grid place-items-center rounded-full"
      style={{ width: size, height: size, background: ring }}
    >
      <div
        className="absolute rounded-full"
        style={{
          background:
            "radial-gradient(70% 70% at 50% 30%, rgba(255,255,255,0.04) 0%, rgba(7,11,20,0.94) 100%)",
          top: inset,
          left: inset,
          right: inset,
          bottom: inset,
          boxShadow: `inset 0 0 0 1px ${color}33`,
        }}
      />
      <div className="relative text-center leading-none">
        <div
          className="font-semibold tracking-tight"
          style={{ color, fontSize: Math.round(size * 0.30) }}
        >
          {composite.toFixed(0)}
        </div>
        <div className="mt-1 text-[10px] uppercase tracking-[0.22em] text-white/55">
          {label ?? bucket}
        </div>
        {showOverride && (
          <div className="mt-1 text-[9.5px] text-white/40">
            engine {engine_composite!.toFixed(0)}
          </div>
        )}
      </div>
    </div>
  );
}
