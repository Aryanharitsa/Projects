import type { PeerBucket } from "../lib/api";

const COLOR: Record<PeerBucket, string> = {
  aligned: "#22d3a8",
  drifting: "#fbbf24",
  outlier: "#fb923c",
  severe: "#ef4444",
};

export function peerBucketColor(bucket: PeerBucket): string {
  return COLOR[bucket] || "#94a3b8";
}

export default function PeerRing({
  score,
  bucket,
  size = 120,
  label,
}: {
  score: number;
  bucket: PeerBucket;
  size?: number;
  label?: string;
}) {
  const pct = Math.max(0, Math.min(100, score));
  const color = COLOR[bucket];
  const ring = `conic-gradient(${color} ${pct * 3.6}deg, rgba(255,255,255,0.06) 0)`;
  const inset = Math.round(size * 0.075);
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
          style={{ color, fontSize: Math.round(size * 0.3) }}
        >
          {score.toFixed(0)}
        </div>
        <div className="mt-1 text-[10px] uppercase tracking-[0.22em] text-white/55">
          {label ?? bucket}
        </div>
      </div>
    </div>
  );
}
