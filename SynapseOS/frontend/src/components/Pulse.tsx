"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import type {
  PulseBridge,
  PulseCluster,
  PulseClusterStatus,
  PulseHub,
  PulseRecommendation,
  PulseRecommendationKind,
  PulseReport,
} from "@/lib/types";

type Props = {
  open: boolean;
  onClose: () => void;
  /** Open the per-cluster Synthesis modal for the given cluster. */
  onSynthesizeCluster?: (clusterId: number) => void;
  /** Isolate the given cluster on the canvas + close the modal. */
  onIsolateCluster?: (clusterId: number) => void;
  /** Select a single note in the inspector + close the modal. */
  onSelectNote?: (note: { id: number; title: string }) => void;
};

const WINDOW_PRESETS = [
  { value: 1, label: "1d" },
  { value: 7, label: "7d" },
  { value: 30, label: "30d" },
  { value: 90, label: "90d" },
];

const STATUS_META: Record<
  PulseClusterStatus,
  { label: string; ring: string; text: string; bg: string; dot: string }
> = {
  hot: {
    label: "hot",
    ring: "ring-synapse-lime/50",
    text: "text-synapse-lime",
    bg: "bg-synapse-lime/10",
    dot: "bg-synapse-lime",
  },
  born: {
    label: "born",
    ring: "ring-synapse-pink/50",
    text: "text-synapse-pink",
    bg: "bg-synapse-pink/10",
    dot: "bg-synapse-pink",
  },
  emerging: {
    label: "emerging",
    ring: "ring-synapse-cyan/50",
    text: "text-synapse-cyan",
    bg: "bg-synapse-cyan/10",
    dot: "bg-synapse-cyan",
  },
  warm: {
    label: "warm",
    ring: "ring-synapse-amber/50",
    text: "text-synapse-amber",
    bg: "bg-synapse-amber/10",
    dot: "bg-synapse-amber",
  },
  dormant: {
    label: "dormant",
    ring: "ring-ink-400/40",
    text: "text-ink-300",
    bg: "bg-white/[0.02]",
    dot: "bg-ink-400",
  },
};

const REC_META: Record<
  PulseRecommendationKind,
  { glyph: string; cls: string }
> = {
  synthesize: {
    glyph: "✦",
    cls: "ring-synapse-lime/40 text-synapse-lime bg-synapse-lime/10",
  },
  name: {
    glyph: "⌁",
    cls: "ring-synapse-cyan/40 text-synapse-cyan bg-synapse-cyan/10",
  },
  hub: {
    glyph: "✺",
    cls: "ring-synapse-violet/40 text-synapse-violet bg-synapse-violet/10",
  },
  bridge: {
    glyph: "⇄",
    cls: "ring-synapse-pink/40 text-synapse-pink bg-synapse-pink/10",
  },
  revisit: {
    glyph: "☼",
    cls: "ring-synapse-amber/40 text-synapse-amber bg-synapse-amber/10",
  },
};

/**
 * Pulse — what changed in your second brain over a window.
 *
 * Atlas is the *snapshot*. Chronicle is the *biography* per cluster.
 * Daily Brief is *today's picks*. Pulse is the **cross-cluster diff
 * over the last N days**: new notes, words written, streak, bridges
 * born, hubs born, vocabulary that emerged or faded, per-cluster
 * status, and a prioritized recommendations list. Open on a Friday
 * afternoon and you can see your whole week's worth of thinking on
 * one screen.
 */
export function Pulse({
  open,
  onClose,
  onSynthesizeCluster,
  onIsolateCluster,
  onSelectNote,
}: Props) {
  const [report, setReport] = useState<PulseReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [windowDays, setWindowDays] = useState(7);

  const load = useCallback(async (w: number) => {
    setLoading(true);
    setError(null);
    try {
      const r = await api.pulse({ windowDays: w });
      setReport(r);
    } catch (e) {
      setError(e instanceof Error ? e.message : "failed to load pulse");
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

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center px-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="pulse-title"
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
              "linear-gradient(90deg, rgba(236,72,153,0.18), rgba(163,230,53,0.10) 45%, rgba(34,211,238,0.10) 85%)",
          }}
        >
          <div className="flex items-center gap-3 min-w-0">
            <PulseGlyph />
            <div className="min-w-0">
              <div
                id="pulse-title"
                className="text-base font-semibold tracking-tight text-ink-100"
              >
                Pulse — what changed in your second brain
              </div>
              <div className="text-[11px] font-mono text-ink-300 uppercase tracking-[0.16em] mt-0.5">
                cross-cluster · time-windowed · prioritized
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            {report && report.total_notes > 0 && (
              <a
                href={api.pulseExportUrl({ windowDays })}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1.5 rounded-full bg-white/[0.03] ring-1 ring-white/10 hover:ring-synapse-pink/50 px-3 py-1 font-mono text-[11px] text-ink-200 hover:text-ink-100 transition"
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
                    ? "ring-synapse-pink/60 text-synapse-pink bg-synapse-pink/15"
                    : "ring-white/10 text-ink-300 hover:text-ink-100 hover:ring-white/20"
                }`}
              >
                {p.label}
              </button>
            ))}
          </div>
          {report && (
            <div className="text-[11px] font-mono text-ink-300 truncate">
              {report.headline}
            </div>
          )}
        </div>

        {/* Body */}
        <div className="overflow-y-auto flex-1 min-h-0">
          <div className="p-6 space-y-6">
            {loading && <PulseSkeleton />}
            {!loading && error && (
              <div className="rounded-xl bg-rose-500/10 ring-1 ring-rose-500/30 p-3 text-xs text-rose-200">
                {error} — start the backend with{" "}
                <span className="font-mono text-ink-100">
                  uvicorn app.main:app --reload
                </span>
              </div>
            )}
            {!loading && !error && report && report.total_notes === 0 && (
              <PulseEmpty />
            )}
            {!loading && !error && report && report.total_notes > 0 && (
              <>
                <MetricsStrip report={report} />
                <ActivitySparkline report={report} />
                <VocabularyDelta report={report} />

                <div className="grid grid-cols-12 gap-5">
                  <section className="col-span-12 lg:col-span-7 space-y-3">
                    <SectionHeader
                      title="Active clusters"
                      hint="status · share new · momentum · centroid drift"
                      count={report.clusters.filter((c) => c.status !== "dormant").length}
                    />
                    <ClusterList
                      clusters={report.clusters}
                      onIsolate={(id) => {
                        if (onIsolateCluster) onIsolateCluster(id);
                        onClose();
                      }}
                      onSynthesize={(id) => {
                        if (onSynthesizeCluster) onSynthesizeCluster(id);
                      }}
                    />
                  </section>

                  <aside className="col-span-12 lg:col-span-5 space-y-3">
                    <SectionHeader
                      title="Recommendations"
                      hint="priority-ranked moves"
                      count={report.recommendations.length}
                    />
                    <RecommendationsList
                      recommendations={report.recommendations}
                      onSynthesize={(id) => {
                        if (onSynthesizeCluster) onSynthesizeCluster(id);
                      }}
                      onIsolate={(id) => {
                        if (onIsolateCluster) onIsolateCluster(id);
                        onClose();
                      }}
                      onSelectNote={(note) => {
                        if (onSelectNote) onSelectNote(note);
                        onClose();
                      }}
                    />
                  </aside>
                </div>

                {report.hubs.length > 0 && (
                  <section className="space-y-3">
                    <SectionHeader
                      title="Hubs born"
                      hint="new notes already pulling synapses"
                      count={report.hubs_born}
                    />
                    <HubsList
                      hubs={report.hubs}
                      onSelectNote={(note) => {
                        if (onSelectNote) onSelectNote(note);
                        onClose();
                      }}
                    />
                  </section>
                )}

                {report.bridges.length > 0 && (
                  <section className="space-y-3">
                    <SectionHeader
                      title="Bridges born"
                      hint="fresh cross-cluster synapses"
                      count={report.bridges_born}
                    />
                    <BridgesList
                      bridges={report.bridges}
                      onSelectNote={(note) => {
                        if (onSelectNote) onSelectNote(note);
                        onClose();
                      }}
                    />
                  </section>
                )}
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// ------------------------------------------------------------ metrics


function MetricsStrip({ report }: { report: PulseReport }) {
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2">
      <MetricCard
        label="new notes"
        value={report.new_notes}
        ring="ring-synapse-lime/30"
        text="text-synapse-lime"
        hint={`≈ ${report.words_written.toLocaleString()} words`}
      />
      <MetricCard
        label="revisits"
        value={report.revisited_notes}
        ring="ring-synapse-amber/30"
        text="text-synapse-amber"
      />
      <MetricCard
        label="bridges"
        value={report.bridges_born}
        ring="ring-synapse-pink/30"
        text="text-synapse-pink"
        hint="cross-cluster"
      />
      <MetricCard
        label="hubs"
        value={report.hubs_born}
        ring="ring-synapse-violet/30"
        text="text-synapse-violet"
        hint="new + degree ≥ 3"
      />
      <MetricCard
        label="streak"
        value={`${report.streak_days}d`}
        ring="ring-synapse-cyan/30"
        text="text-synapse-cyan"
        hint="consecutive"
      />
      <MetricCard
        label="hot · forming"
        value={`${report.clusters_hot} · ${report.clusters_emerging}`}
        ring="ring-white/10"
        text="text-ink-100"
        hint={`${report.clusters_dormant} dormant`}
      />
    </div>
  );
}

function MetricCard({
  label,
  value,
  ring,
  text,
  hint,
}: {
  label: string;
  value: string | number;
  ring: string;
  text: string;
  hint?: string;
}) {
  return (
    <div
      className={`rounded-xl bg-white/[0.02] ring-1 ${ring} px-3 py-2.5 flex flex-col gap-0.5`}
    >
      <span
        className={`text-[10px] uppercase tracking-[0.18em] font-mono ${text} opacity-80`}
      >
        {label}
      </span>
      <span className={`text-xl font-semibold ${text}`}>{value}</span>
      {hint && (
        <span className="text-[10px] font-mono text-ink-300 opacity-70">
          {hint}
        </span>
      )}
    </div>
  );
}

// ------------------------------------------------------------ sparkline

function ActivitySparkline({ report }: { report: PulseReport }) {
  const W = 720;
  const H = 88;
  const PAD_L = 32;
  const PAD_R = 14;
  const PAD_T = 8;
  const PAD_B = 22;
  const innerW = W - PAD_L - PAD_R;
  const innerH = H - PAD_T - PAD_B;

  const days = report.activity;
  const maxVal = Math.max(
    1,
    ...days.map((d) => d.created + d.revisited),
  );
  const step = days.length > 1 ? innerW / (days.length - 1) : innerW;

  const xOf = (i: number) => PAD_L + i * step;
  const yOf = (v: number) => PAD_T + (1 - v / maxVal) * innerH;

  // Two stacked series: created (lime) + revisited (amber, on top).
  const linePts = (vals: number[]) =>
    vals.map((v, i) => `${xOf(i).toFixed(1)},${yOf(v).toFixed(1)}`).join(" ");

  const created = days.map((d) => d.created);
  const total = days.map((d) => d.created + d.revisited);

  // Pick a few tick labels — first, middle, last.
  const tickIndices = [0, Math.floor(days.length / 2), days.length - 1].filter(
    (v, i, arr) => arr.indexOf(v) === i,
  );

  return (
    <div className="rounded-xl bg-ink-900/40 ring-1 ring-white/5 px-4 py-3">
      <div className="flex items-center justify-between mb-1">
        <div className="text-[11px] font-mono text-ink-300 uppercase tracking-[0.16em]">
          daily activity · last {report.window_days}d
        </div>
        <div className="flex items-center gap-3 text-[10px] font-mono">
          <span className="inline-flex items-center gap-1.5 text-synapse-lime">
            <span className="w-2 h-2 rounded-full bg-synapse-lime" />
            created
          </span>
          <span className="inline-flex items-center gap-1.5 text-synapse-amber">
            <span className="w-2 h-2 rounded-full bg-synapse-amber" />
            revisited
          </span>
        </div>
      </div>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="w-full h-auto"
        role="img"
        aria-label={`daily activity sparkline over ${report.window_days}d`}
      >
        <defs>
          <linearGradient id="pulse-fill" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor="#a3e635" stopOpacity="0.45" />
            <stop offset="100%" stopColor="#a3e635" stopOpacity="0" />
          </linearGradient>
          <linearGradient id="pulse-fill-rev" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor="#fbbf24" stopOpacity="0.32" />
            <stop offset="100%" stopColor="#fbbf24" stopOpacity="0" />
          </linearGradient>
        </defs>

        {/* baseline */}
        <line
          x1={PAD_L}
          y1={PAD_T + innerH}
          x2={PAD_L + innerW}
          y2={PAD_T + innerH}
          stroke="#38405f"
          strokeWidth="1"
          opacity="0.4"
        />
        {/* midline */}
        <line
          x1={PAD_L}
          y1={PAD_T + innerH / 2}
          x2={PAD_L + innerW}
          y2={PAD_T + innerH / 2}
          stroke="#38405f"
          strokeDasharray="2 4"
          strokeWidth="1"
          opacity="0.35"
        />

        {/* total area (created + revisited) */}
        {days.length > 0 && (
          <polygon
            points={`${PAD_L},${PAD_T + innerH} ${linePts(total)} ${PAD_L + innerW},${PAD_T + innerH}`}
            fill="url(#pulse-fill-rev)"
          />
        )}
        {/* created area */}
        {days.length > 0 && (
          <polygon
            points={`${PAD_L},${PAD_T + innerH} ${linePts(created)} ${PAD_L + innerW},${PAD_T + innerH}`}
            fill="url(#pulse-fill)"
          />
        )}
        {/* line on top */}
        <polyline
          points={linePts(created)}
          fill="none"
          stroke="#a3e635"
          strokeWidth="1.6"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <polyline
          points={linePts(total)}
          fill="none"
          stroke="#fbbf24"
          strokeWidth="1.2"
          strokeOpacity="0.85"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeDasharray="2 4"
        />

        {/* dots */}
        {days.map((d, i) => {
          const isPeak = d.created + d.revisited > 0;
          if (!isPeak) return null;
          return (
            <g key={d.date}>
              <circle
                cx={xOf(i)}
                cy={yOf(d.created)}
                r={2.4}
                fill="#a3e635"
              />
              {d.revisited > 0 && (
                <circle
                  cx={xOf(i)}
                  cy={yOf(d.created + d.revisited)}
                  r={2}
                  fill="#fbbf24"
                />
              )}
            </g>
          );
        })}

        {/* y-axis label (max) */}
        <text
          x={PAD_L - 4}
          y={PAD_T + 6}
          textAnchor="end"
          fontSize="9"
          fontFamily="ui-monospace, SFMono-Regular, Menlo, monospace"
          fill="#8a95bf"
        >
          {maxVal}
        </text>

        {/* x-axis labels */}
        {tickIndices.map((i) => (
          <text
            key={i}
            x={xOf(i)}
            y={PAD_T + innerH + 14}
            textAnchor="middle"
            fontSize="9"
            fontFamily="ui-monospace, SFMono-Regular, Menlo, monospace"
            fill="#8a95bf"
          >
            {dayLabel(days[i].date)}
          </text>
        ))}
      </svg>
    </div>
  );
}

function dayLabel(iso: string): string {
  // "2026-06-20" -> "Jun 20" (deterministic across locales).
  const parts = iso.split("-");
  if (parts.length !== 3) return iso;
  const months = [
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
  ];
  const m = Number(parts[1]);
  const d = Number(parts[2]);
  if (!m || !d || m < 1 || m > 12) return iso;
  return `${months[m - 1]} ${d}`;
}

// --------------------------------------------------------- vocab delta

function VocabularyDelta({ report }: { report: PulseReport }) {
  if (report.emerged_terms.length === 0 && report.faded_terms.length === 0) {
    return null;
  }
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
      <VocabPanel
        label="Emerged"
        terms={report.emerged_terms}
        hint="frequent now · rare before"
        ring="ring-synapse-lime/40"
        text="text-synapse-lime"
        bg="bg-synapse-lime/[0.04]"
        chip="ring-synapse-lime/30 text-synapse-lime bg-synapse-lime/10"
      />
      <VocabPanel
        label="Faded"
        terms={report.faded_terms}
        hint="frequent before · rare now"
        ring="ring-ink-400/40"
        text="text-ink-200"
        bg="bg-white/[0.02]"
        chip="ring-ink-400/30 text-ink-200 bg-white/[0.03]"
      />
    </div>
  );
}

function VocabPanel({
  label,
  terms,
  hint,
  ring,
  text,
  bg,
  chip,
}: {
  label: string;
  terms: string[];
  hint: string;
  ring: string;
  text: string;
  bg: string;
  chip: string;
}) {
  return (
    <div className={`rounded-xl ${bg} ring-1 ${ring} px-4 py-3`}>
      <div className="flex items-center justify-between mb-2">
        <div className={`text-[11px] font-mono uppercase tracking-[0.16em] ${text}`}>
          {label}
        </div>
        <div className="text-[10px] font-mono text-ink-300 opacity-70">{hint}</div>
      </div>
      {terms.length === 0 ? (
        <div className="text-xs text-ink-300 italic">— no change</div>
      ) : (
        <div className="flex flex-wrap gap-1.5">
          {terms.map((t) => (
            <span
              key={t}
              className={`inline-flex items-center rounded-full px-2.5 py-0.5 ring-1 text-[11px] font-mono ${chip}`}
            >
              {t}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

// ------------------------------------------------------------- clusters

function ClusterList({
  clusters,
  onIsolate,
  onSynthesize,
}: {
  clusters: PulseCluster[];
  onIsolate: (id: number) => void;
  onSynthesize: (id: number) => void;
}) {
  if (clusters.length === 0) {
    return (
      <div className="rounded-xl bg-white/[0.02] ring-1 ring-white/5 p-4 text-xs text-ink-300">
        No clusters yet — write enough notes for the graph to find them.
      </div>
    );
  }
  return (
    <div className="space-y-2">
      {clusters.map((c) => (
        <ClusterRow
          key={c.cluster_id}
          cluster={c}
          onIsolate={() => onIsolate(c.cluster_id)}
          onSynthesize={() => onSynthesize(c.cluster_id)}
        />
      ))}
    </div>
  );
}

function ClusterRow({
  cluster,
  onIsolate,
  onSynthesize,
}: {
  cluster: PulseCluster;
  onIsolate: () => void;
  onSynthesize: () => void;
}) {
  const meta = STATUS_META[cluster.status];
  const pct = Math.round(cluster.momentum * 100);
  const sharePct = Math.round(cluster.share_new * 100);
  return (
    <div
      className={`rounded-xl ${meta.bg} ring-1 ${meta.ring} px-4 py-3 transition`}
    >
      <div className="flex items-center justify-between gap-3 mb-1.5">
        <div className="flex items-center gap-2 min-w-0">
          <span
            className="w-2.5 h-2.5 rounded-full shrink-0"
            style={{ background: cluster.color }}
            aria-hidden
          />
          <span className="text-sm font-semibold text-ink-100 truncate">
            {cluster.name}
          </span>
          <span
            className={`inline-flex items-center gap-1 rounded-full px-1.5 py-0 ring-1 text-[10px] font-mono uppercase tracking-[0.12em] ${meta.ring} ${meta.text}`}
          >
            <span className={`w-1.5 h-1.5 rounded-full ${meta.dot}`} />
            {meta.label}
          </span>
        </div>
        <div className="flex items-center gap-1 shrink-0">
          <button
            onClick={onSynthesize}
            className="inline-flex items-center gap-1 rounded-full bg-white/[0.03] ring-1 ring-white/10 hover:ring-synapse-cyan/50 px-2 py-0.5 font-mono text-[10px] text-ink-200 hover:text-ink-100 transition"
            title="Open synthesis brief"
          >
            ✦ synth
          </button>
          <button
            onClick={onIsolate}
            className="inline-flex items-center gap-1 rounded-full bg-white/[0.03] ring-1 ring-white/10 hover:ring-synapse-violet/50 px-2 py-0.5 font-mono text-[10px] text-ink-200 hover:text-ink-100 transition"
            title="Isolate on canvas"
          >
            ⊙ isolate
          </button>
        </div>
      </div>

      <div className="flex items-center gap-2 mb-2">
        <span className="text-[10px] font-mono text-ink-300 opacity-70 w-16 shrink-0">
          momentum
        </span>
        <div className="flex-1 h-1.5 rounded-full bg-white/[0.04] overflow-hidden">
          <div
            className="h-full rounded-full"
            style={{
              width: `${pct}%`,
              background: cluster.color,
              opacity: 0.85,
            }}
          />
        </div>
        <span className="text-[10px] font-mono text-ink-200 w-10 text-right">
          {pct}
        </span>
      </div>

      <div className="flex flex-wrap items-center gap-2 text-[10.5px] font-mono text-ink-300">
        <Pill>{cluster.size} notes</Pill>
        <Pill className="text-synapse-lime">
          +{cluster.new_count} new
        </Pill>
        {cluster.revisits_count > 0 && (
          <Pill className="text-synapse-amber">
            ↻ {cluster.revisits_count}
          </Pill>
        )}
        <Pill>{sharePct}% new</Pill>
        {cluster.centroid_drift !== null && cluster.centroid_drift > 0 && (
          <Pill className="text-synapse-pink">
            drift {cluster.centroid_drift.toFixed(2)}
          </Pill>
        )}
        {cluster.last_touched_days !== null && cluster.new_count === 0 && (
          <Pill className="text-ink-300 opacity-80">
            quiet {cluster.last_touched_days}d
          </Pill>
        )}
      </div>

      {(cluster.new_terms.length > 0 || cluster.hot_titles.length > 0) && (
        <div className="mt-2.5 pt-2.5 border-t border-white/[0.04] space-y-1.5">
          {cluster.new_terms.length > 0 && (
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="text-[10px] font-mono text-ink-300 opacity-70">
                new vocab:
              </span>
              {cluster.new_terms.map((t) => (
                <span
                  key={t}
                  className="inline-flex items-center rounded-full bg-white/[0.025] ring-1 ring-white/10 px-2 py-0 font-mono text-[10px] text-ink-200"
                >
                  {t}
                </span>
              ))}
            </div>
          )}
          {cluster.hot_titles.length > 0 && (
            <ul className="space-y-0.5">
              {cluster.hot_titles.slice(0, 3).map((t) => (
                <li
                  key={t}
                  className="text-[11.5px] text-ink-200 truncate flex items-center gap-1.5"
                >
                  <span
                    className="w-1 h-1 rounded-full shrink-0"
                    style={{ background: cluster.color, opacity: 0.7 }}
                  />
                  {t}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

function Pill({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <span
      className={`inline-flex items-center rounded-full bg-white/[0.025] ring-1 ring-white/10 px-2 py-0 ${className}`}
    >
      {children}
    </span>
  );
}

// -------------------------------------------------------- recommendations

function RecommendationsList({
  recommendations,
  onSynthesize,
  onIsolate,
  onSelectNote,
}: {
  recommendations: PulseRecommendation[];
  onSynthesize: (id: number) => void;
  onIsolate: (id: number) => void;
  onSelectNote: (note: { id: number; title: string }) => void;
}) {
  if (recommendations.length === 0) {
    return (
      <div className="rounded-xl bg-white/[0.02] ring-1 ring-white/5 p-4 text-xs text-ink-300">
        No outstanding moves — the window looks healthy.
      </div>
    );
  }
  return (
    <ul className="space-y-2">
      {recommendations.map((r, i) => (
        <RecommendationCard
          key={`${r.kind}-${i}-${r.headline}`}
          rec={r}
          onAct={() => {
            if (r.kind === "synthesize" || r.kind === "name") {
              if (r.cluster_id !== null) onSynthesize(r.cluster_id);
            } else if (r.kind === "revisit" || r.kind === "bridge") {
              if (r.cluster_id !== null) onIsolate(r.cluster_id);
            } else if (r.kind === "hub" && r.note_id !== null) {
              onSelectNote({ id: r.note_id, title: r.headline });
            }
          }}
        />
      ))}
    </ul>
  );
}

function RecommendationCard({
  rec,
  onAct,
}: {
  rec: PulseRecommendation;
  onAct: () => void;
}) {
  const meta = REC_META[rec.kind];
  return (
    <li
      className={`rounded-xl ring-1 ${meta.cls} px-3 py-2.5 cursor-pointer hover:bg-white/[0.04] transition`}
      onClick={onAct}
    >
      <div className="flex items-start gap-2.5">
        <span className="text-base leading-none mt-0.5">{meta.glyph}</span>
        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between gap-2">
            <div className="text-xs font-semibold text-ink-100 truncate">
              {rec.headline}
            </div>
            <span className="text-[9.5px] font-mono opacity-60 shrink-0">
              p {rec.priority.toFixed(2)}
            </span>
          </div>
          <p className="text-[11.5px] text-ink-300 leading-relaxed mt-0.5">
            {rec.detail}
          </p>
        </div>
      </div>
    </li>
  );
}

// ---------------------------------------------------------------- hubs

function HubsList({
  hubs,
  onSelectNote,
}: {
  hubs: PulseHub[];
  onSelectNote: (note: { id: number; title: string }) => void;
}) {
  return (
    <ul className="grid grid-cols-1 md:grid-cols-2 gap-2">
      {hubs.map((h) => (
        <li
          key={h.note_id}
          className="rounded-xl bg-white/[0.02] ring-1 ring-synapse-violet/30 hover:ring-synapse-violet/60 px-3 py-2.5 cursor-pointer transition"
          onClick={() =>
            onSelectNote({ id: h.note_id, title: h.title })
          }
        >
          <div className="flex items-center gap-2 mb-1">
            <span className="text-synapse-violet text-base leading-none">✺</span>
            <div className="text-xs font-semibold text-ink-100 truncate flex-1">
              {h.title}
            </div>
            <span className="inline-flex items-center gap-1 rounded-full bg-synapse-violet/10 ring-1 ring-synapse-violet/40 px-1.5 py-0 font-mono text-[10px] text-synapse-violet">
              {h.degree}×
            </span>
          </div>
          {h.snippet && (
            <p className="text-[11px] text-ink-300 leading-snug line-clamp-2 mb-1">
              {h.snippet}
            </p>
          )}
          <div className="flex items-center gap-2 text-[10px] font-mono text-ink-300">
            {h.cluster_name && (
              <span className="inline-flex items-center gap-1">
                <span
                  className="w-1.5 h-1.5 rounded-full"
                  style={{ background: h.cluster_color ?? "#5b6590" }}
                />
                {h.cluster_name}
              </span>
            )}
            <span className="opacity-70">·</span>
            <span>{h.days_old}d old</span>
          </div>
        </li>
      ))}
    </ul>
  );
}

// ---------------------------------------------------------------- bridges

function BridgesList({
  bridges,
  onSelectNote,
}: {
  bridges: PulseBridge[];
  onSelectNote: (note: { id: number; title: string }) => void;
}) {
  return (
    <ul className="space-y-2">
      {bridges.map((b, i) => (
        <li
          key={`${b.source_id}-${b.target_id}-${i}`}
          className="rounded-xl bg-white/[0.02] ring-1 ring-white/10 hover:ring-synapse-pink/50 px-3 py-2.5 transition"
        >
          <div className="flex items-center gap-2 mb-1 flex-wrap text-[11px] font-mono">
            <span
              className="inline-flex items-center gap-1 rounded-full bg-white/[0.025] ring-1 px-2 py-0"
              style={{
                borderColor: b.source_cluster_color,
                color: b.source_cluster_color,
              }}
            >
              <span
                className="w-1.5 h-1.5 rounded-full"
                style={{ background: b.source_cluster_color }}
              />
              {b.source_cluster_name}
            </span>
            <span className="text-synapse-pink">⇄</span>
            <span
              className="inline-flex items-center gap-1 rounded-full bg-white/[0.025] ring-1 px-2 py-0"
              style={{
                borderColor: b.target_cluster_color,
                color: b.target_cluster_color,
              }}
            >
              <span
                className="w-1.5 h-1.5 rounded-full"
                style={{ background: b.target_cluster_color }}
              />
              {b.target_cluster_name}
            </span>
            <span className="ml-auto opacity-60">
              cosine {b.strength.toFixed(2)}
            </span>
          </div>
          <div className="flex items-center gap-2 text-[12px] text-ink-200 flex-wrap">
            <button
              className="text-left underline-offset-2 hover:underline truncate max-w-[40%]"
              onClick={() =>
                onSelectNote({ id: b.source_id, title: b.source_title })
              }
              title="open in inspector"
            >
              {b.source_is_new && (
                <span className="text-synapse-lime text-[9.5px] mr-1 font-mono">
                  NEW
                </span>
              )}
              {b.source_title}
            </button>
            <span className="text-ink-400 text-xs">↔</span>
            <button
              className="text-left underline-offset-2 hover:underline truncate max-w-[40%]"
              onClick={() =>
                onSelectNote({ id: b.target_id, title: b.target_title })
              }
              title="open in inspector"
            >
              {b.target_is_new && (
                <span className="text-synapse-lime text-[9.5px] mr-1 font-mono">
                  NEW
                </span>
              )}
              {b.target_title}
            </button>
          </div>
        </li>
      ))}
    </ul>
  );
}

// ----------------------------------------------------------- shared chrome

function SectionHeader({
  title,
  hint,
  count,
}: {
  title: string;
  hint: string;
  count: number;
}) {
  return (
    <div className="flex items-center justify-between gap-3">
      <div className="flex items-center gap-2">
        <h3 className="text-sm font-semibold tracking-tight text-ink-100">
          {title}
        </h3>
        <span className="inline-flex items-center justify-center min-w-[1.4rem] h-[1.4rem] rounded-full bg-white/[0.04] ring-1 ring-white/10 text-[10px] font-mono text-ink-200">
          {count}
        </span>
      </div>
      <div className="text-[10.5px] font-mono text-ink-300 uppercase tracking-[0.14em]">
        {hint}
      </div>
    </div>
  );
}

function PulseEmpty() {
  return (
    <div className="rounded-xl bg-white/[0.02] ring-1 ring-white/5 p-6 text-center">
      <div className="text-2xl text-ink-300 mb-2">♡</div>
      <div className="text-sm text-ink-200 mb-1">
        Pulse is quiet — there are no notes yet.
      </div>
      <div className="text-[11px] text-ink-300">
        Write or distill a few atomic notes, then come back to see your
        weekly rhythm.
      </div>
    </div>
  );
}

function PulseSkeleton() {
  return (
    <div className="space-y-4 animate-pulse-slow">
      <div className="grid grid-cols-6 gap-2">
        {[...Array(6)].map((_, i) => (
          <div
            key={i}
            className="h-16 rounded-xl bg-white/[0.02] ring-1 ring-white/5"
          />
        ))}
      </div>
      <div className="h-24 rounded-xl bg-white/[0.02] ring-1 ring-white/5" />
      <div className="h-20 rounded-xl bg-white/[0.02] ring-1 ring-white/5" />
      <div className="grid grid-cols-12 gap-5">
        <div className="col-span-7 space-y-2">
          {[...Array(3)].map((_, i) => (
            <div
              key={i}
              className="h-24 rounded-xl bg-white/[0.02] ring-1 ring-white/5"
            />
          ))}
        </div>
        <div className="col-span-5 space-y-2">
          {[...Array(3)].map((_, i) => (
            <div
              key={i}
              className="h-16 rounded-xl bg-white/[0.02] ring-1 ring-white/5"
            />
          ))}
        </div>
      </div>
    </div>
  );
}

function PulseGlyph() {
  return (
    <div className="relative w-9 h-9 rounded-lg bg-gradient-to-br from-synapse-pink/30 to-synapse-lime/20 ring-1 ring-synapse-pink/40 flex items-center justify-center">
      <svg viewBox="0 0 32 16" className="w-7 h-3.5" aria-hidden="true">
        <polyline
          points="0,8 6,8 9,3 12,13 15,5 18,11 21,8 32,8"
          fill="none"
          stroke="#ec4899"
          strokeWidth="1.6"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    </div>
  );
}
