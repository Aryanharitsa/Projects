import type { ProfileHistoryEntry, ProfileBucket } from "../lib/api";

const COLOR: Record<ProfileBucket, string> = {
  low: "#22d3a8",
  medium: "#fbbf24",
  high: "#fb923c",
  critical: "#ef4444",
};

const KIND_TONE: Record<string, string> = {
  refresh: "#94a3b8",
  override: "#a78bfa",
  clear_override: "#5eead4",
  seed: "#64748b",
};

/** Compact sparkline of the customer's composite over the last N refreshes.
 *
 * Domain shows up to 24 points (reverse-chronological in the API; we plot
 * chronologically). Bucket-band horizontal guides are rendered as faint
 * dashed lines at 30 / 60 / 80 so the eye reads "this customer just
 * crossed into high" without us having to label it. Each point is
 * recoloured by the bucket at that refresh. Hovering a point shows the
 * underlying tooltip — kept native so we add zero deps.
 */
export default function HistoryStrip({
  history,
  height = 88,
}: {
  history: ProfileHistoryEntry[];
  height?: number;
}) {
  if (!history.length) {
    return (
      <div
        className="rounded-xl border border-dashed border-white/10 bg-white/[0.02] text-center text-[12px] text-white/45"
        style={{ height, display: "grid", placeItems: "center" }}
      >
        No history yet. The first refresh seeds the trail.
      </div>
    );
  }
  // History from API is reverse-chron; flip to chronological for the chart.
  const pts = [...history].reverse();
  const n = pts.length;
  const width = Math.max(260, n * 28);
  const pad = 12;
  const yFor = (v: number) => {
    const y = (1 - Math.max(0, Math.min(100, v)) / 100) * (height - pad * 2) + pad;
    return y;
  };
  const xFor = (i: number) => {
    if (n === 1) return width / 2;
    return pad + (i * (width - pad * 2)) / (n - 1);
  };

  // Path
  const path = pts
    .map((p, i) => `${i === 0 ? "M" : "L"}${xFor(i).toFixed(1)},${yFor(p.composite).toFixed(1)}`)
    .join(" ");

  // Engine-composite line (when overrides shift the surfaced number).
  const enginePath = pts
    .map((p, i) => `${i === 0 ? "M" : "L"}${xFor(i).toFixed(1)},${yFor(p.engine_composite).toFixed(1)}`)
    .join(" ");

  const guideY = (cut: number) => yFor(cut);

  return (
    <div className="overflow-x-auto scroll-thin">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        style={{ width: Math.max(width, 380), height }}
      >
        <defs>
          <linearGradient id="hs-area" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor="rgba(110,91,255,0.32)" />
            <stop offset="100%" stopColor="rgba(110,91,255,0.00)" />
          </linearGradient>
        </defs>
        {/* Bucket guides at 30 / 60 / 80 */}
        {[30, 60, 80].map((cut) => (
          <line
            key={cut}
            x1={pad}
            x2={width - pad}
            y1={guideY(cut)}
            y2={guideY(cut)}
            stroke={cut === 80 ? "#ef4444" : cut === 60 ? "#fb923c" : "#fbbf24"}
            strokeOpacity={0.20}
            strokeDasharray="3 3"
            strokeWidth={1}
          />
        ))}
        {/* Area fill under composite */}
        <path
          d={`${path} L${xFor(n - 1).toFixed(1)},${(height - pad).toFixed(1)} L${xFor(0).toFixed(1)},${(height - pad).toFixed(1)} Z`}
          fill="url(#hs-area)"
        />
        {/* Engine vs surfaced — when they diverge, surfaced is solid, engine dashed */}
        {pts.some((p) => Math.abs(p.composite - p.engine_composite) > 0.5) && (
          <path
            d={enginePath}
            fill="none"
            stroke="rgba(255,255,255,0.35)"
            strokeWidth={1}
            strokeDasharray="2 3"
          />
        )}
        <path
          d={path}
          fill="none"
          stroke="rgba(110,91,255,0.95)"
          strokeWidth={1.6}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        {/* Refresh-kind dots */}
        {pts.map((p, i) => {
          const cx = xFor(i);
          const cy = yFor(p.composite);
          const tone = KIND_TONE[p.refresh_kind] || "#94a3b8";
          const bucketTone = COLOR[p.bucket] || tone;
          const label = `${p.refreshed_at.slice(0, 10)} · ${p.bucket} · ${p.composite.toFixed(0)}${
            p.refresh_kind === "override" ? " (override)" :
            p.refresh_kind === "clear_override" ? " (override cleared)" : ""
          }`;
          return (
            <g key={p.id || i}>
              <title>{label}</title>
              <circle
                cx={cx}
                cy={cy}
                r={p.refresh_kind === "override" ? 4 : 3}
                fill={bucketTone}
                stroke="rgba(7,11,20,0.95)"
                strokeWidth={1.5}
              />
              {p.refresh_kind === "override" && (
                <circle
                  cx={cx}
                  cy={cy}
                  r={6}
                  fill="none"
                  stroke="#a78bfa"
                  strokeOpacity={0.55}
                  strokeWidth={1}
                />
              )}
            </g>
          );
        })}
      </svg>
    </div>
  );
}
