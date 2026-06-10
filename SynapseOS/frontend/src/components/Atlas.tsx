"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import type {
  AtlasCluster,
  AtlasQuadrant,
  AtlasRecommendation,
  AtlasRecommendationKind,
  AtlasReport,
} from "@/lib/types";

type Props = {
  open: boolean;
  onClose: () => void;
  /** Jump the canvas into "isolate this cluster" mode and close the modal. */
  onIsolateCluster: (clusterId: number) => void;
  /** Open the per-cluster digest (Synthesis) for the given cluster. */
  onSynthesizeCluster: (clusterId: number) => void;
};

const WINDOW_PRESETS = [
  { value: 7, label: "7d" },
  { value: 30, label: "30d" },
  { value: 90, label: "90d" },
  { value: 180, label: "180d" },
];

const QUADRANT_META: Record<
  AtlasQuadrant,
  { label: string; tag: string; tint: string; ring: string; text: string }
> = {
  stronghold: {
    label: "Strongholds",
    tag: "high cohesion · high activity",
    tint: "from-synapse-lime/15 to-emerald-400/5",
    ring: "ring-synapse-lime/40",
    text: "text-synapse-lime",
  },
  frontier: {
    label: "Frontiers",
    tag: "still forming · actively growing",
    tint: "from-synapse-cyan/15 to-sky-400/5",
    ring: "ring-synapse-cyan/40",
    text: "text-synapse-cyan",
  },
  vault: {
    label: "Vaults",
    tag: "tight but cooling",
    tint: "from-synapse-violet/15 to-fuchsia-400/5",
    ring: "ring-synapse-violet/40",
    text: "text-synapse-violet",
  },
  drift: {
    label: "Drift",
    tag: "stale & unfocused",
    tint: "from-ink-500/20 to-transparent",
    ring: "ring-ink-400/40",
    text: "text-ink-200",
  },
};

const REC_META: Record<
  AtlasRecommendationKind,
  { glyph: string; label: string; cls: string }
> = {
  synthesize: {
    glyph: "✦",
    label: "synthesize",
    cls: "ring-synapse-cyan/40 text-synapse-cyan bg-synapse-cyan/10",
  },
  split: {
    glyph: "⇆",
    label: "split",
    cls: "ring-rose-400/40 text-rose-300 bg-rose-500/10",
  },
  revisit: {
    glyph: "☼",
    label: "revisit",
    cls: "ring-synapse-amber/40 text-synapse-amber bg-synapse-amber/10",
  },
  dissolve: {
    glyph: "∽",
    label: "dissolve",
    cls: "ring-ink-400/40 text-ink-200 bg-white/[0.04]",
  },
  bridge: {
    glyph: "⇄",
    label: "bridge",
    cls: "ring-synapse-violet/40 text-synapse-violet bg-synapse-violet/10",
  },
};

const FILTER_TABS: { value: AtlasQuadrant | "all"; label: string }[] = [
  { value: "all", label: "All" },
  { value: "stronghold", label: "Strongholds" },
  { value: "frontier", label: "Frontiers" },
  { value: "vault", label: "Vaults" },
  { value: "drift", label: "Drift" },
];

/**
 * Atlas — a cartographer's view of your second brain.
 *
 * Every other surface zooms in on one cluster, one pair, one note. Atlas
 * zooms out. It scatters every cluster on cohesion × activity, classifies
 * each into Strongholds / Frontiers / Vaults / Drift, and surfaces a
 * prioritized to-do list ("synthesize this while it's hot", "this may be
 * two topics", "this cluster is cooling") that the user can act on with
 * one click.
 */
export function Atlas({ open, onClose, onIsolateCluster, onSynthesizeCluster }: Props) {
  const [report, setReport] = useState<AtlasReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [windowDays, setWindowDays] = useState(30);
  const [filter, setFilter] = useState<AtlasQuadrant | "all">("all");
  const [hoverId, setHoverId] = useState<number | null>(null);
  const [pinnedId, setPinnedId] = useState<number | null>(null);

  const load = useCallback(async (w: number) => {
    setLoading(true);
    setError(null);
    try {
      const r = await api.atlas({ windowDays: w });
      setReport(r);
    } catch (e) {
      setError(e instanceof Error ? e.message : "failed to load atlas");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (open) load(windowDays);
  }, [open, windowDays, load]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  const filtered = useMemo(() => {
    if (!report) return [] as AtlasCluster[];
    if (filter === "all") return report.clusters;
    return report.clusters.filter((c) => c.quadrant === filter);
  }, [report, filter]);

  const focused: AtlasCluster | null = useMemo(() => {
    if (!report) return null;
    const id = pinnedId ?? hoverId;
    if (id === null) return null;
    return report.clusters.find((c) => c.id === id) ?? null;
  }, [report, pinnedId, hoverId]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center px-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="atlas-title"
    >
      <div
        className="absolute inset-0 bg-ink-900/80 backdrop-blur-md"
        onClick={onClose}
      />
      <div className="absolute inset-0 pointer-events-none bg-grid-fade opacity-60" />

      <div className="relative w-full max-w-6xl max-h-[92vh] flex flex-col rounded-2xl bg-ink-800/90 ring-1 ring-white/10 shadow-card overflow-hidden animate-fade-in">
        {/* Header */}
        <div
          className="flex items-center justify-between gap-4 px-6 py-4 border-b border-white/5"
          style={{
            background:
              "linear-gradient(90deg, rgba(168,85,247,0.16), rgba(34,211,238,0.10) 45%, rgba(163,230,53,0.08) 85%)",
          }}
        >
          <div className="flex items-center gap-3 min-w-0">
            <AtlasGlyph />
            <div className="min-w-0">
              <div
                id="atlas-title"
                className="text-base font-semibold tracking-tight text-ink-100"
              >
                Atlas — a cartographer&apos;s view of your second brain
              </div>
              <div className="text-[11px] font-mono text-ink-300 uppercase tracking-[0.16em] mt-0.5">
                cohesion × activity · quadrant signal · prioritized moves
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            {report && report.total_clusters > 0 && (
              <a
                href={api.atlasExportUrl({ windowDays })}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1.5 rounded-full bg-white/[0.03] ring-1 ring-white/10 hover:ring-synapse-cyan/50 px-3 py-1 font-mono text-[11px] text-ink-200 hover:text-ink-100 transition"
                title="Download as portable Markdown"
              >
                ⤓ md
              </a>
            )}
            <button
              onClick={onClose}
              className="inline-flex items-center justify-center rounded-full w-8 h-8 ring-1 ring-white/10 text-ink-300 hover:text-ink-100 hover:ring-white/30 transition"
              aria-label="close"
            >
              ✕
            </button>
          </div>
        </div>

        {/* Toolbar */}
        <div className="flex items-center justify-between gap-4 px-6 py-3 border-b border-white/5 bg-ink-800/60 flex-wrap">
          <div className="flex items-center gap-2 text-[11px] font-mono">
            <span className="text-ink-300 uppercase tracking-[0.16em]">window</span>
            {WINDOW_PRESETS.map((p) => (
              <button
                key={p.value}
                onClick={() => setWindowDays(p.value)}
                className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 ring-1 transition ${
                  windowDays === p.value
                    ? "ring-synapse-cyan/60 text-synapse-cyan bg-synapse-cyan/15"
                    : "ring-white/10 text-ink-300 hover:text-ink-100 hover:ring-white/20"
                }`}
              >
                {p.label}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-1 text-[11px] font-mono">
            {FILTER_TABS.map((t) => (
              <button
                key={t.value}
                onClick={() => setFilter(t.value)}
                className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 ring-1 transition ${
                  filter === t.value
                    ? "ring-synapse-violet/60 text-synapse-violet bg-synapse-violet/15"
                    : "ring-white/10 text-ink-300 hover:text-ink-100 hover:ring-white/20"
                }`}
              >
                {t.label}
              </button>
            ))}
          </div>
        </div>

        {/* Body */}
        <div className="grid grid-cols-12 gap-0 overflow-hidden flex-1 min-h-0">
          {/* Map */}
          <section className="col-span-12 lg:col-span-8 border-r border-white/5 bg-ink-900/30 overflow-y-auto min-h-0">
            <div className="p-6 space-y-4">
              {loading && <AtlasSkeleton />}
              {!loading && error && (
                <div className="rounded-xl bg-rose-500/10 ring-1 ring-rose-500/30 p-3 text-xs text-rose-200">
                  {error} — start the backend with{" "}
                  <span className="font-mono text-ink-100">
                    uvicorn app.main:app --reload
                  </span>
                </div>
              )}
              {!loading && !error && report && report.total_clusters === 0 && (
                <AtlasEmpty totalNotes={report.total_notes} />
              )}
              {!loading && !error && report && report.total_clusters > 0 && (
                <>
                  <SummaryStrip report={report} />
                  <QuadrantChart
                    clusters={filtered}
                    hoverId={hoverId}
                    pinnedId={pinnedId}
                    onHover={setHoverId}
                    onClick={(id) =>
                      setPinnedId((prev) => (prev === id ? null : id))
                    }
                  />
                  <QuadrantLegend />
                </>
              )}
            </div>
          </section>

          {/* Sidebar */}
          <aside className="col-span-12 lg:col-span-4 overflow-y-auto min-h-0">
            <div className="p-5 space-y-4">
              {focused && report && (
                <ClusterDetail
                  cluster={focused}
                  onIsolate={() => {
                    onIsolateCluster(focused.id);
                    onClose();
                  }}
                  onSynthesize={() => {
                    onSynthesizeCluster(focused.id);
                  }}
                />
              )}
              {!focused && report && report.total_clusters > 0 && (
                <RecommendationsList
                  recommendations={report.recommendations}
                  onPin={(id) => setPinnedId(id)}
                  onSynthesize={(id) => onSynthesizeCluster(id)}
                  onIsolate={(id) => {
                    onIsolateCluster(id);
                    onClose();
                  }}
                />
              )}
            </div>
          </aside>
        </div>
      </div>
    </div>
  );
}

// ----------------------------------------------------------------- summary

function SummaryStrip({ report }: { report: AtlasReport }) {
  const s = report.summary;
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
      <SummaryCard
        label="Strongholds"
        value={s.stronghold_count ?? 0}
        text="text-synapse-lime"
        ring="ring-synapse-lime/30"
      />
      <SummaryCard
        label="Frontiers"
        value={s.frontier_count ?? 0}
        text="text-synapse-cyan"
        ring="ring-synapse-cyan/30"
      />
      <SummaryCard
        label="Vaults"
        value={s.vault_count ?? 0}
        text="text-synapse-violet"
        ring="ring-synapse-violet/30"
      />
      <SummaryCard
        label="Drift"
        value={s.drift_count ?? 0}
        text="text-ink-200"
        ring="ring-ink-400/30"
      />
    </div>
  );
}

function SummaryCard({
  label,
  value,
  text,
  ring,
}: {
  label: string;
  value: number;
  text: string;
  ring: string;
}) {
  return (
    <div
      className={`rounded-xl bg-white/[0.02] ring-1 ${ring} px-3 py-2 flex items-baseline justify-between`}
    >
      <span
        className={`text-[10px] uppercase tracking-[0.18em] font-mono ${text} opacity-80`}
      >
        {label}
      </span>
      <span className={`text-lg font-semibold ${text}`}>{value}</span>
    </div>
  );
}

// ----------------------------------------------------------------- chart

function QuadrantChart({
  clusters,
  hoverId,
  pinnedId,
  onHover,
  onClick,
}: {
  clusters: AtlasCluster[];
  hoverId: number | null;
  pinnedId: number | null;
  onHover: (id: number | null) => void;
  onClick: (id: number) => void;
}) {
  const W = 800;
  const H = 420;
  const PAD_L = 56;
  const PAD_R = 28;
  const PAD_T = 22;
  const PAD_B = 44;
  const innerW = W - PAD_L - PAD_R;
  const innerH = H - PAD_T - PAD_B;

  // Cohesion is already 0..1; activity is already 0..1. Both axes use
  // those raw values so the visual reads honestly.
  const x = (cohesion: number) => PAD_L + cohesion * innerW;
  const y = (activity: number) => PAD_T + (1 - activity) * innerH;

  const maxSize = Math.max(1, ...clusters.map((c) => c.size));
  const radius = (size: number) => {
    // Sqrt scaling so a 4× note count → 2× radius; visually honest area encoding.
    const t = Math.sqrt(size / maxSize);
    return 9 + t * 22;
  };

  // Midline positions for the quadrant fold.
  const midX = PAD_L + 0.5 * innerW;
  const midY = PAD_T + (1 - 0.4) * innerH; // ACTIVITY_MID

  // Sort smallest-first so big bubbles sit on top during render.
  const sorted = [...clusters].sort((a, b) => a.size - b.size);

  return (
    <div className="rounded-xl bg-ink-900/40 ring-1 ring-white/5 p-4">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="w-full h-auto"
        role="img"
        aria-label="cluster quadrant chart"
      >
        <defs>
          <linearGradient id="atlas-grid" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor="#1a1f35" stopOpacity="0.6" />
            <stop offset="100%" stopColor="#0a0d18" stopOpacity="0.2" />
          </linearGradient>
          <radialGradient id="bubble-glow" cx="0.5" cy="0.5" r="0.55">
            <stop offset="0%" stopColor="white" stopOpacity="0.18" />
            <stop offset="60%" stopColor="white" stopOpacity="0.02" />
            <stop offset="100%" stopColor="white" stopOpacity="0" />
          </radialGradient>
        </defs>

        {/* plot bg */}
        <rect
          x={PAD_L}
          y={PAD_T}
          width={innerW}
          height={innerH}
          fill="url(#atlas-grid)"
          rx="10"
        />

        {/* quadrant tints */}
        <g pointerEvents="none">
          {/* stronghold: top-right */}
          <rect
            x={midX}
            y={PAD_T}
            width={PAD_L + innerW - midX}
            height={midY - PAD_T}
            fill="#a3e635"
            opacity="0.045"
            rx="0"
          />
          {/* frontier: top-left */}
          <rect
            x={PAD_L}
            y={PAD_T}
            width={midX - PAD_L}
            height={midY - PAD_T}
            fill="#22d3ee"
            opacity="0.045"
          />
          {/* vault: bottom-right */}
          <rect
            x={midX}
            y={midY}
            width={PAD_L + innerW - midX}
            height={PAD_T + innerH - midY}
            fill="#a855f7"
            opacity="0.045"
          />
          {/* drift: bottom-left */}
          <rect
            x={PAD_L}
            y={midY}
            width={midX - PAD_L}
            height={PAD_T + innerH - midY}
            fill="#5b6590"
            opacity="0.05"
          />
        </g>

        {/* quadrant labels */}
        <g
          fontFamily="ui-monospace, SFMono-Regular, Menlo, monospace"
          fontSize="11"
          textAnchor="middle"
          opacity="0.65"
          pointerEvents="none"
        >
          <text x={(midX + PAD_L + innerW) / 2} y={PAD_T + 18} fill="#a3e635">
            STRONGHOLD
          </text>
          <text x={(midX + PAD_L) / 2} y={PAD_T + 18} fill="#22d3ee">
            FRONTIER
          </text>
          <text
            x={(midX + PAD_L + innerW) / 2}
            y={PAD_T + innerH - 6}
            fill="#a855f7"
          >
            VAULT
          </text>
          <text x={(midX + PAD_L) / 2} y={PAD_T + innerH - 6} fill="#8a95bf">
            DRIFT
          </text>
        </g>

        {/* mid lines */}
        <g stroke="#38405f" strokeDasharray="3 5" strokeWidth="1" opacity="0.6">
          <line x1={midX} y1={PAD_T} x2={midX} y2={PAD_T + innerH} />
          <line x1={PAD_L} y1={midY} x2={PAD_L + innerW} y2={midY} />
        </g>

        {/* axes */}
        <g
          stroke="#5b6590"
          strokeWidth="1"
          opacity="0.55"
          pointerEvents="none"
        >
          <line x1={PAD_L} y1={PAD_T + innerH} x2={PAD_L + innerW} y2={PAD_T + innerH} />
          <line x1={PAD_L} y1={PAD_T} x2={PAD_L} y2={PAD_T + innerH} />
        </g>

        {/* axis labels */}
        <g
          fontFamily="ui-monospace, SFMono-Regular, Menlo, monospace"
          fontSize="10"
          fill="#8a95bf"
          pointerEvents="none"
        >
          <text x={PAD_L + innerW / 2} y={H - 14} textAnchor="middle">
            cohesion →
          </text>
          <text
            x={16}
            y={PAD_T + innerH / 2}
            textAnchor="middle"
            transform={`rotate(-90 16 ${PAD_T + innerH / 2})`}
          >
            ← activity (touched in window)
          </text>
          {/* tick labels */}
          <text x={PAD_L} y={PAD_T + innerH + 14} textAnchor="middle">
            0
          </text>
          <text x={PAD_L + innerW} y={PAD_T + innerH + 14} textAnchor="middle">
            1
          </text>
          <text x={PAD_L - 8} y={PAD_T + innerH + 4} textAnchor="end">
            0
          </text>
          <text x={PAD_L - 8} y={PAD_T + 4} textAnchor="end">
            1
          </text>
        </g>

        {/* bubbles */}
        <g>
          {sorted.map((c) => {
            const cx = x(c.cohesion);
            const cy = y(c.activity);
            const r = radius(c.size);
            const isActive = hoverId === c.id || pinnedId === c.id;
            return (
              <g
                key={c.id}
                onMouseEnter={() => onHover(c.id)}
                onMouseLeave={() => onHover(null)}
                onClick={() => onClick(c.id)}
                style={{ cursor: "pointer" }}
              >
                {/* glow halo for active */}
                {isActive && (
                  <circle
                    cx={cx}
                    cy={cy}
                    r={r + 8}
                    fill={c.color}
                    opacity="0.18"
                  />
                )}
                <circle
                  cx={cx}
                  cy={cy}
                  r={r}
                  fill={c.color}
                  opacity={isActive ? 0.95 : 0.78}
                  stroke={isActive ? "#ffffff" : c.color}
                  strokeOpacity={isActive ? 0.9 : 0.35}
                  strokeWidth={isActive ? 1.5 : 1}
                />
                {/* inner glossy highlight */}
                <circle
                  cx={cx}
                  cy={cy}
                  r={r}
                  fill="url(#bubble-glow)"
                  pointerEvents="none"
                />
                {/* label */}
                {(isActive || r > 14) && (
                  <text
                    x={cx}
                    y={cy + r + 12}
                    fontFamily="ui-sans-serif, system-ui, sans-serif"
                    fontSize="11"
                    fontWeight="600"
                    fill="#c3c9e8"
                    textAnchor="middle"
                    pointerEvents="none"
                  >
                    {c.name}
                  </text>
                )}
              </g>
            );
          })}
        </g>
      </svg>
    </div>
  );
}

function QuadrantLegend() {
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-[11px]">
      {(Object.keys(QUADRANT_META) as AtlasQuadrant[]).map((q) => {
        const m = QUADRANT_META[q];
        return (
          <div
            key={q}
            className={`rounded-lg ring-1 ${m.ring} bg-gradient-to-br ${m.tint} px-3 py-2`}
          >
            <div
              className={`font-mono uppercase tracking-[0.16em] ${m.text} text-[10px]`}
            >
              {m.label}
            </div>
            <div className="text-ink-300 mt-0.5">{m.tag}</div>
          </div>
        );
      })}
    </div>
  );
}

// ----------------------------------------------------------------- focused panel

function ClusterDetail({
  cluster,
  onIsolate,
  onSynthesize,
}: {
  cluster: AtlasCluster;
  onIsolate: () => void;
  onSynthesize: () => void;
}) {
  const m = QUADRANT_META[cluster.quadrant];
  return (
    <div className="rounded-xl bg-white/[0.02] ring-1 ring-white/10 overflow-hidden">
      <div
        className={`px-4 py-3 bg-gradient-to-br ${m.tint} border-b border-white/5`}
      >
        <div className="flex items-center gap-2">
          <span
            className="inline-block w-2.5 h-2.5 rounded-full ring-1 ring-white/20"
            style={{ background: cluster.color }}
          />
          <span className="text-sm font-semibold text-ink-100 truncate">
            {cluster.name}
          </span>
          <span
            className={`ml-auto font-mono text-[10px] uppercase tracking-[0.16em] ${m.text}`}
          >
            {m.label.slice(0, -1)}
          </span>
        </div>
        {cluster.terms.length > 0 && (
          <div className="mt-1.5 flex flex-wrap gap-1">
            {cluster.terms.slice(0, 4).map((t) => (
              <span
                key={t}
                className="inline-flex rounded-full bg-white/[0.04] ring-1 ring-white/10 px-2 py-0.5 text-[10px] font-mono text-ink-300"
              >
                {t}
              </span>
            ))}
          </div>
        )}
      </div>
      <div className="p-4 space-y-2 text-[11px] font-mono">
        <DetailRow
          label="size"
          value={`${cluster.size} note${cluster.size === 1 ? "" : "s"}`}
        />
        <DetailRow
          label="cohesion"
          value={cluster.cohesion.toFixed(2)}
          bar={cluster.cohesion}
          barColor="bg-synapse-lime/70"
        />
        <DetailRow
          label="activity"
          value={cluster.activity.toFixed(2)}
          bar={cluster.activity}
          barColor="bg-synapse-cyan/70"
        />
        <DetailRow
          label="density"
          value={cluster.internal_density.toFixed(2)}
          bar={cluster.internal_density}
          barColor="bg-synapse-violet/60"
        />
        <DetailRow label="growth" value={`+${cluster.growth_velocity}`} />
        <DetailRow label="newest" value={`${cluster.newest_age_days}d ago`} />
        <DetailRow
          label="last touch"
          value={
            cluster.last_touched_days === null
              ? "—"
              : `${cluster.last_touched_days}d ago`
          }
        />
        <DetailRow
          label="bridges"
          value={
            cluster.bridge_count > 0
              ? `${cluster.bridge_count} waiting`
              : "0"
          }
        />
      </div>
      <div className="px-4 pb-4 flex items-center gap-2">
        <button
          onClick={onSynthesize}
          className="flex-1 inline-flex items-center justify-center gap-1.5 rounded-full bg-synapse-cyan/15 ring-1 ring-synapse-cyan/50 hover:ring-synapse-cyan px-3 py-1.5 font-mono text-[11px] text-synapse-cyan transition"
          title="Open the cluster brief in Synthesis"
        >
          ✦ synthesize
        </button>
        <button
          onClick={onIsolate}
          className="flex-1 inline-flex items-center justify-center gap-1.5 rounded-full bg-white/[0.03] ring-1 ring-white/10 hover:ring-white/30 px-3 py-1.5 font-mono text-[11px] text-ink-200 hover:text-ink-100 transition"
          title="Isolate this cluster on the canvas"
        >
          ⊙ isolate
        </button>
      </div>
    </div>
  );
}

function DetailRow({
  label,
  value,
  bar,
  barColor,
}: {
  label: string;
  value: string;
  bar?: number;
  barColor?: string;
}) {
  return (
    <div className="flex items-center gap-3">
      <span className="w-20 shrink-0 text-ink-300 uppercase tracking-[0.16em] text-[10px]">
        {label}
      </span>
      {bar !== undefined && (
        <span className="flex-1 h-1.5 rounded-full bg-white/[0.04] overflow-hidden">
          <span
            className={`block h-full ${barColor ?? "bg-white/30"}`}
            style={{ width: `${Math.min(100, Math.round(bar * 100))}%` }}
          />
        </span>
      )}
      <span className="text-ink-100 ml-auto">{value}</span>
    </div>
  );
}

// ----------------------------------------------------------------- recommendations

function RecommendationsList({
  recommendations,
  onPin,
  onSynthesize,
  onIsolate,
}: {
  recommendations: AtlasRecommendation[];
  onPin: (id: number) => void;
  onSynthesize: (id: number) => void;
  onIsolate: (id: number) => void;
}) {
  if (recommendations.length === 0) {
    return (
      <div className="rounded-xl bg-white/[0.02] ring-1 ring-white/10 p-5 text-xs text-ink-300 leading-relaxed">
        <div className="font-semibold text-ink-100 mb-1">Nothing urgent.</div>
        <p>
          Your atlas is balanced — no clusters are leaking, splitting, or
          rotting on the bench. Hover a bubble for details, or come back after
          a writing session.
        </p>
      </div>
    );
  }
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between px-1">
        <div className="text-[10px] font-mono uppercase tracking-[0.18em] text-ink-300">
          recommendations
        </div>
        <div className="text-[10px] font-mono text-ink-400">
          {recommendations.length} item{recommendations.length === 1 ? "" : "s"}
        </div>
      </div>
      <ul className="space-y-2">
        {recommendations.slice(0, 10).map((rec) => (
          <li key={`${rec.cluster_id}-${rec.kind}`}>
            <RecommendationCard
              rec={rec}
              onPin={() => onPin(rec.cluster_id)}
              onSynthesize={() => onSynthesize(rec.cluster_id)}
              onIsolate={() => onIsolate(rec.cluster_id)}
            />
          </li>
        ))}
      </ul>
    </div>
  );
}

function RecommendationCard({
  rec,
  onPin,
  onSynthesize,
  onIsolate,
}: {
  rec: AtlasRecommendation;
  onPin: () => void;
  onSynthesize: () => void;
  onIsolate: () => void;
}) {
  const meta = REC_META[rec.kind];
  const action =
    rec.kind === "synthesize" || rec.kind === "split"
      ? { label: "open brief", run: onSynthesize }
      : { label: "isolate", run: onIsolate };
  return (
    <div className="rounded-xl bg-white/[0.02] ring-1 ring-white/10 hover:ring-white/20 p-3 transition">
      <div className="flex items-center gap-2">
        <span
          className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 font-mono text-[10px] ring-1 ${meta.cls}`}
        >
          {meta.glyph} {meta.label}
        </span>
        <span
          className="inline-block w-2 h-2 rounded-full ring-1 ring-white/15"
          style={{ background: rec.cluster_color }}
          title={rec.cluster_name}
        />
        <span className="text-[11px] text-ink-300 truncate">
          {rec.cluster_name}
        </span>
        <span className="ml-auto text-[10px] font-mono text-ink-400">
          p{(rec.priority).toFixed(2)}
        </span>
      </div>
      <div className="mt-1.5 text-[12px] text-ink-100 font-medium">
        {rec.headline}
      </div>
      <div className="mt-1 text-[11px] text-ink-300 leading-relaxed">
        {rec.detail}
      </div>
      <div className="mt-2 flex items-center gap-1">
        <button
          onClick={action.run}
          className="inline-flex items-center gap-1 rounded-full bg-white/[0.04] ring-1 ring-white/10 hover:ring-synapse-cyan/40 hover:text-synapse-cyan px-2 py-0.5 font-mono text-[10px] text-ink-200 transition"
        >
          → {action.label}
        </button>
        <button
          onClick={onPin}
          className="inline-flex items-center gap-1 rounded-full bg-white/[0.04] ring-1 ring-white/10 hover:ring-white/30 px-2 py-0.5 font-mono text-[10px] text-ink-300 hover:text-ink-100 transition"
        >
          show on map
        </button>
      </div>
    </div>
  );
}

// ----------------------------------------------------------------- empty / skeleton / glyph

function AtlasEmpty({ totalNotes }: { totalNotes: number }) {
  return (
    <div className="h-full min-h-[300px] flex items-center justify-center p-8">
      <div className="text-center max-w-sm">
        <div className="text-3xl opacity-30 mb-3">⌖</div>
        <p className="text-xs text-ink-300 font-mono leading-relaxed">
          {totalNotes === 0
            ? "No notes yet. Add a few atomic thoughts and the Atlas will start mapping them as clusters form."
            : "Not enough connections yet — every note is its own island. Lower τ in the canvas or write a few more notes to start forming clusters."}
        </p>
      </div>
    </div>
  );
}

function AtlasSkeleton() {
  return (
    <div className="space-y-4 animate-pulse-slow">
      <div className="grid grid-cols-4 gap-2">
        {Array.from({ length: 4 }).map((_, i) => (
          <div
            key={i}
            className="h-12 rounded-xl bg-white/[0.02] ring-1 ring-white/5"
          />
        ))}
      </div>
      <div className="h-[420px] rounded-xl bg-white/[0.02] ring-1 ring-white/5" />
    </div>
  );
}

function AtlasGlyph() {
  return (
    <div className="relative w-9 h-9 shrink-0">
      <svg viewBox="0 0 36 36" className="w-full h-full">
        <defs>
          <radialGradient id="atlas-glyph-rg" cx="0.5" cy="0.5" r="0.6">
            <stop offset="0%" stopColor="#22d3ee" stopOpacity="0.85" />
            <stop offset="100%" stopColor="#a855f7" stopOpacity="0.2" />
          </radialGradient>
        </defs>
        <rect
          x="3"
          y="3"
          width="30"
          height="30"
          rx="7"
          fill="url(#atlas-glyph-rg)"
          opacity="0.55"
        />
        <line x1="18" y1="5" x2="18" y2="31" stroke="#c3c9e8" strokeOpacity="0.5" strokeWidth="0.7" strokeDasharray="2 2" />
        <line x1="5" y1="18" x2="31" y2="18" stroke="#c3c9e8" strokeOpacity="0.5" strokeWidth="0.7" strokeDasharray="2 2" />
        <circle cx="24" cy="11" r="3.5" fill="#a3e635" />
        <circle cx="11" cy="11" r="2.5" fill="#22d3ee" />
        <circle cx="25" cy="25" r="2.5" fill="#a855f7" />
        <circle cx="11" cy="24" r="1.8" fill="#8a95bf" />
      </svg>
    </div>
  );
}
