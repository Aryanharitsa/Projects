"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import type {
  ChronicleCategory,
  ChronicleChapter,
  ChronicleCluster,
  ChronicleReport,
} from "@/lib/types";

type Props = {
  open: boolean;
  onClose: () => void;
  onSelectNote: (stub: { id: number; title: string; body: string; tags: string[] }) => void;
  onSynthesizeCluster: (clusterId: number) => void;
  onIsolateCluster: (clusterId: number) => void;
};

const CHAPTER_PRESETS = [
  { value: 3, label: "3" },
  { value: 4, label: "4" },
  { value: 6, label: "6" },
];

const CATEGORY_META: Record<
  ChronicleCategory,
  {
    label: string;
    tag: string;
    text: string;
    ring: string;
    bg: string;
    glyph: string;
  }
> = {
  calm: {
    label: "Calm",
    tag: "steady restatement",
    text: "text-synapse-lime",
    ring: "ring-synapse-lime/40",
    bg: "bg-synapse-lime/10",
    glyph: "∽",
  },
  shifting: {
    label: "Shifting",
    tag: "gradual development",
    text: "text-synapse-cyan",
    ring: "ring-synapse-cyan/40",
    bg: "bg-synapse-cyan/10",
    glyph: "≈",
  },
  pivoting: {
    label: "Pivoting",
    tag: "framing visibly turned",
    text: "text-synapse-pink",
    ring: "ring-synapse-pink/40",
    bg: "bg-synapse-pink/10",
    glyph: "⇆",
  },
};

const FILTER_TABS: { value: ChronicleCategory | "all"; label: string }[] = [
  { value: "all", label: "All" },
  { value: "pivoting", label: "Pivoting" },
  { value: "shifting", label: "Shifting" },
  { value: "calm", label: "Calm" },
];

function formatDateShort(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso.slice(0, 10);
  return d.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function formatCadence(days: number): string {
  if (days <= 0) return "same-day";
  if (days < 1) return `${(days * 24).toFixed(0)}h`;
  if (days < 14) return `${days.toFixed(1)}d`;
  if (days < 60) return `${days.toFixed(0)}d`;
  return `${(days / 7).toFixed(0)}w`;
}

/**
 * Chronicle — temporal narrative of how each topic evolved.
 *
 * Every other surface in SynapseOS is a snapshot. Chronicle replays the
 * cluster: chapter-by-chapter, it shows when the vocabulary turned over,
 * which terms emerged, which faded, and where the pivot moment landed.
 * Calm / shifting / pivoting bands give you the shape at a glance.
 */
export function Chronicle({
  open,
  onClose,
  onSelectNote,
  onSynthesizeCluster,
  onIsolateCluster,
}: Props) {
  const [report, setReport] = useState<ChronicleReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [maxChapters, setMaxChapters] = useState(4);
  const [filter, setFilter] = useState<ChronicleCategory | "all">("all");
  const [focusedId, setFocusedId] = useState<number | null>(null);

  const load = useCallback(async (mc: number) => {
    setLoading(true);
    setError(null);
    try {
      const r = await api.chronicle({ maxChapters: mc });
      setReport(r);
      // Default focus = top-ranked cluster (highest drift × size).
      if (r.clusters.length > 0) {
        setFocusedId((prev) =>
          prev !== null && r.clusters.some((c) => c.cluster_id === prev)
            ? prev
            : r.clusters[0].cluster_id,
        );
      } else {
        setFocusedId(null);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "failed to load chronicle");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (open) load(maxChapters);
  }, [open, maxChapters, load]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  const filtered = useMemo(() => {
    if (!report) return [] as ChronicleCluster[];
    if (filter === "all") return report.clusters;
    return report.clusters.filter((c) => c.category === filter);
  }, [report, filter]);

  const focused: ChronicleCluster | null = useMemo(() => {
    if (!report) return null;
    if (focusedId === null) return null;
    return report.clusters.find((c) => c.cluster_id === focusedId) ?? null;
  }, [report, focusedId]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center px-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="chronicle-title"
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
              "linear-gradient(90deg, rgba(244,114,182,0.16), rgba(168,85,247,0.10) 50%, rgba(34,211,238,0.08) 95%)",
          }}
        >
          <div className="flex items-center gap-3 min-w-0">
            <ChronicleGlyph />
            <div className="min-w-0">
              <div
                id="chronicle-title"
                className="text-base font-semibold tracking-tight text-ink-100"
              >
                Chronicle — watch your topics evolve
              </div>
              <div className="text-[11px] font-mono text-ink-300 uppercase tracking-[0.16em] mt-0.5">
                chapters · drift velocity · pivot moments · emerged & faded vocabulary
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            {report && report.eligible_clusters > 0 && (
              <a
                href={api.chronicleExportUrl({ maxChapters })}
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
            <span className="text-ink-300 uppercase tracking-[0.16em]">
              max chapters
            </span>
            {CHAPTER_PRESETS.map((p) => (
              <button
                key={p.value}
                onClick={() => setMaxChapters(p.value)}
                className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 ring-1 transition ${
                  maxChapters === p.value
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
          {/* Cluster rail */}
          <aside className="col-span-12 lg:col-span-4 border-r border-white/5 overflow-y-auto min-h-0">
            <div className="p-4 space-y-3">
              {loading && <RailSkeleton />}
              {!loading && error && (
                <div className="rounded-xl bg-rose-500/10 ring-1 ring-rose-500/30 p-3 text-xs text-rose-200">
                  {error} — start the backend with{" "}
                  <span className="font-mono text-ink-100">
                    uvicorn app.main:app --reload
                  </span>
                </div>
              )}
              {!loading && !error && report && (
                <>
                  <SummaryStrip report={report} />
                  {filtered.length === 0 && <RailEmpty report={report} filter={filter} />}
                  {filtered.map((c) => (
                    <ClusterCard
                      key={c.cluster_id}
                      cluster={c}
                      active={focused?.cluster_id === c.cluster_id}
                      onClick={() => setFocusedId(c.cluster_id)}
                    />
                  ))}
                </>
              )}
            </div>
          </aside>

          {/* Main timeline */}
          <section className="col-span-12 lg:col-span-8 overflow-y-auto min-h-0 bg-ink-900/30">
            <div className="p-6">
              {loading && <TimelineSkeleton />}
              {!loading && report && report.eligible_clusters === 0 && (
                <EmptyState report={report} />
              )}
              {!loading && focused && (
                <ClusterTimeline
                  cluster={focused}
                  onSelectNote={onSelectNote}
                  onSynthesize={() => onSynthesizeCluster(focused.cluster_id)}
                  onIsolate={() => {
                    onIsolateCluster(focused.cluster_id);
                    onClose();
                  }}
                />
              )}
            </div>
          </section>
        </div>

        {/* Footnote */}
        <div className="px-6 py-3 border-t border-white/5 text-[11px] font-mono text-ink-400 flex items-center justify-between gap-4 flex-wrap">
          <span>
            chapter := equal-time bin of the cluster · drift := 1 −
            cosine(centroid<sub>i</sub>, centroid<sub>i+1</sub>) · pivot :=
            argmax drift_in
          </span>
          {report && (
            <span className="text-ink-300">
              {report.eligible_clusters} cluster
              {report.eligible_clusters === 1 ? "" : "s"} with a story · mean
              drift {(report.summary.mean_drift ?? 0).toFixed(2)}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

// ---------- Summary strip

function SummaryStrip({ report }: { report: ChronicleReport }) {
  const s = report.summary;
  return (
    <div className="rounded-xl bg-white/[0.02] ring-1 ring-white/5 p-3 mb-2">
      <div className="text-[10px] font-mono uppercase tracking-[0.18em] text-ink-300 mb-2">
        chronicle overview
      </div>
      <div className="grid grid-cols-3 gap-2 mb-2">
        <Tile label="Pivoting" value={s.pivoting_count ?? 0} tone="pink" />
        <Tile label="Shifting" value={s.shifting_count ?? 0} tone="cyan" />
        <Tile label="Calm" value={s.calm_count ?? 0} tone="lime" />
      </div>
      <div className="grid grid-cols-2 gap-2 text-[10px] font-mono text-ink-300">
        <div className="rounded-md bg-white/[0.02] ring-1 ring-white/5 px-2 py-1.5">
          <div className="opacity-60">mean drift</div>
          <div className="text-ink-100">
            {(s.mean_drift ?? 0).toFixed(2)}
          </div>
        </div>
        <div className="rounded-md bg-white/[0.02] ring-1 ring-white/5 px-2 py-1.5">
          <div className="opacity-60">chapters</div>
          <div className="text-ink-100">{s.total_chapters ?? 0}</div>
        </div>
      </div>
      {(s.most_pivoting || s.most_stable) && (
        <div className="mt-2 grid grid-cols-1 gap-1 text-[10px] font-mono">
          {s.most_pivoting && (
            <div className="text-ink-300">
              <span className="opacity-60">most pivoting · </span>
              <span className="text-synapse-pink">{s.most_pivoting}</span>
            </div>
          )}
          {s.most_stable && s.most_stable !== s.most_pivoting && (
            <div className="text-ink-300">
              <span className="opacity-60">most stable · </span>
              <span className="text-synapse-lime">{s.most_stable}</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function Tile({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone: "pink" | "cyan" | "lime";
}) {
  const cls =
    tone === "pink"
      ? "ring-synapse-pink/30 text-synapse-pink bg-synapse-pink/10"
      : tone === "cyan"
      ? "ring-synapse-cyan/30 text-synapse-cyan bg-synapse-cyan/10"
      : "ring-synapse-lime/30 text-synapse-lime bg-synapse-lime/10";
  return (
    <div
      className={`rounded-md ring-1 px-2 py-1.5 flex flex-col items-start ${cls}`}
    >
      <span className="text-[10px] font-mono opacity-80 uppercase tracking-[0.14em]">
        {label}
      </span>
      <span className="text-sm font-semibold tabular-nums">{value}</span>
    </div>
  );
}

// ---------- Cluster card (left rail)

function ClusterCard({
  cluster,
  active,
  onClick,
}: {
  cluster: ChronicleCluster;
  active: boolean;
  onClick: () => void;
}) {
  const meta = CATEGORY_META[cluster.category];
  return (
    <button
      onClick={onClick}
      className={`w-full text-left rounded-xl p-3 ring-1 transition group ${
        active
          ? "ring-white/30 bg-white/[0.04]"
          : "ring-white/5 bg-white/[0.01] hover:ring-white/15 hover:bg-white/[0.03]"
      }`}
    >
      <div className="flex items-start justify-between gap-2 mb-1.5">
        <div className="flex items-center gap-2 min-w-0">
          <span
            className="w-2.5 h-2.5 rounded-full shrink-0"
            style={{ backgroundColor: cluster.color }}
          />
          <span className="text-sm font-semibold text-ink-100 truncate">
            {cluster.name}
          </span>
        </div>
        <span
          className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 ring-1 text-[10px] font-mono shrink-0 ${meta.ring} ${meta.text} ${meta.bg}`}
          title={meta.tag}
        >
          <span aria-hidden>{meta.glyph}</span>
          {meta.label}
        </span>
      </div>
      <DriftBar
        cluster={cluster}
        emphasis={active ? "active" : "muted"}
      />
      <div className="mt-2 text-[10px] font-mono text-ink-400 flex items-center gap-2 flex-wrap">
        <span>{cluster.size} notes</span>
        <span>·</span>
        <span>{cluster.chapter_count} chapters</span>
        <span>·</span>
        <span>{cluster.span_days}d span</span>
        <span>·</span>
        <span>cadence {formatCadence(cluster.cadence_days)}</span>
      </div>
    </button>
  );
}

function DriftBar({
  cluster,
  emphasis,
}: {
  cluster: ChronicleCluster;
  emphasis: "active" | "muted";
}) {
  // Render chapters as proportional segments with drift-in indicators
  // between them. The track itself is the cluster's color at low opacity;
  // drift markers ride on top in the category color so the eye reads
  // "this is the shape of the story" at a glance.
  const total = cluster.chapters.reduce((acc, c) => acc + Math.max(1, c.count), 0);
  const meta = CATEGORY_META[cluster.category];
  return (
    <div className="space-y-1.5">
      <div
        className={`relative h-2.5 rounded-full overflow-hidden ${
          emphasis === "active" ? "ring-1 ring-white/15" : ""
        }`}
        style={{ backgroundColor: cluster.color + "22" }}
      >
        {cluster.chapters.map((ch, i) => {
          const widthPct = (Math.max(1, ch.count) / total) * 100;
          const offset = cluster.chapters
            .slice(0, i)
            .reduce((acc, c) => acc + (Math.max(1, c.count) / total) * 100, 0);
          const isPivot =
            cluster.pivot_index !== null && i === cluster.pivot_index + 1;
          return (
            <span
              key={ch.index}
              className="absolute top-0 h-full"
              style={{
                left: `${offset}%`,
                width: `${widthPct}%`,
                background: isPivot
                  ? `linear-gradient(90deg, ${cluster.color}66, ${cluster.color})`
                  : `linear-gradient(90deg, ${cluster.color}44, ${cluster.color}88)`,
              }}
              title={`Chapter ${ch.index + 1}: ${formatDateShort(ch.date_start)} → ${formatDateShort(ch.date_end)}`}
            />
          );
        })}
      </div>
      <div className="flex items-center justify-between text-[10px] font-mono">
        <span className="text-ink-400">
          drift{" "}
          <span className={meta.text}>{cluster.total_drift.toFixed(2)}</span>
        </span>
        <span className="text-ink-400">
          stability{" "}
          <span className="text-ink-200">{cluster.stability.toFixed(2)}</span>
        </span>
      </div>
    </div>
  );
}

// ---------- Main timeline

function ClusterTimeline({
  cluster,
  onSelectNote,
  onSynthesize,
  onIsolate,
}: {
  cluster: ChronicleCluster;
  onSelectNote: (stub: { id: number; title: string; body: string; tags: string[] }) => void;
  onSynthesize: () => void;
  onIsolate: () => void;
}) {
  const meta = CATEGORY_META[cluster.category];
  return (
    <div className="space-y-6">
      {/* Cluster header */}
      <div>
        <div className="flex items-center gap-3 flex-wrap mb-2">
          <span
            className="w-3 h-3 rounded-full"
            style={{ backgroundColor: cluster.color }}
          />
          <h2 className="text-xl font-semibold tracking-tight text-ink-100">
            {cluster.name}
          </h2>
          <span
            className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 ring-1 text-[11px] font-mono ${meta.ring} ${meta.text} ${meta.bg}`}
          >
            <span aria-hidden>{meta.glyph}</span>
            {meta.label} · {meta.tag}
          </span>
          <button
            onClick={onSynthesize}
            className="ml-auto inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 ring-1 ring-synapse-cyan/40 hover:ring-synapse-cyan/70 text-[11px] font-mono text-synapse-cyan hover:text-ink-100 bg-synapse-cyan/10 transition"
            title="Read this cluster as prose (Synthesis)"
          >
            ✦ synthesize
          </button>
          <button
            onClick={onIsolate}
            className="inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 ring-1 ring-synapse-violet/40 hover:ring-synapse-violet/70 text-[11px] font-mono text-synapse-violet hover:text-ink-100 bg-synapse-violet/10 transition"
            title="Highlight just this cluster on the graph"
          >
            ◎ isolate
          </button>
        </div>
        <p className="text-sm text-ink-200 leading-relaxed">
          {cluster.headline}
        </p>
        <div className="mt-2 flex items-center gap-3 flex-wrap text-[11px] font-mono text-ink-300">
          <Stat label="size" value={`${cluster.size} notes`} />
          <Stat label="span" value={`${cluster.span_days}d`} />
          <Stat label="cadence" value={`${formatCadence(cluster.cadence_days)}/note`} />
          <Stat label="drift" value={cluster.total_drift.toFixed(2)} highlight />
          <Stat label="peak" value={cluster.peak_drift.toFixed(2)} />
          <Stat label="stability" value={cluster.stability.toFixed(2)} />
        </div>
      </div>

      {/* Vocabulary deltas */}
      {(cluster.emerged_terms.length > 0 || cluster.faded_terms.length > 0) && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {cluster.emerged_terms.length > 0 && (
            <DeltaPanel
              title="Emerged"
              tone="cyan"
              hint="terms in later chapters that were rare or absent at the start"
              terms={cluster.emerged_terms}
            />
          )}
          {cluster.faded_terms.length > 0 && (
            <DeltaPanel
              title="Faded"
              tone="amber"
              hint="terms that anchored early chapters but dropped out by the end"
              terms={cluster.faded_terms}
            />
          )}
        </div>
      )}

      {/* Chapters */}
      <div>
        <div className="text-[11px] font-mono text-ink-300 uppercase tracking-[0.18em] mb-3">
          chapters
        </div>
        <div className="space-y-3">
          {cluster.chapters.map((ch, i) => (
            <div key={ch.index}>
              {i > 0 && (
                <DriftConnector
                  drift={ch.drift_in}
                  isPivot={cluster.pivot_index === i - 1}
                  color={cluster.color}
                />
              )}
              <ChapterCard
                cluster={cluster}
                chapter={ch}
                isPivot={cluster.pivot_index === i - 1}
                onSelectNote={onSelectNote}
              />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function Stat({
  label,
  value,
  highlight,
}: {
  label: string;
  value: string;
  highlight?: boolean;
}) {
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-white/[0.02] ring-1 ring-white/5 px-2 py-0.5">
      <span className="opacity-70">{label}</span>
      <span className={highlight ? "text-synapse-cyan" : "text-ink-100"}>
        {value}
      </span>
    </span>
  );
}

function DeltaPanel({
  title,
  tone,
  hint,
  terms,
}: {
  title: string;
  tone: "cyan" | "amber";
  hint: string;
  terms: string[];
}) {
  const ring =
    tone === "cyan"
      ? "ring-synapse-cyan/30"
      : "ring-synapse-amber/30";
  const text =
    tone === "cyan" ? "text-synapse-cyan" : "text-synapse-amber";
  return (
    <div
      className={`rounded-xl bg-white/[0.02] ring-1 ${ring} p-3`}
    >
      <div className={`text-[11px] font-mono uppercase tracking-[0.16em] ${text}`}>
        {title}
      </div>
      <div className="text-[10px] font-mono text-ink-400 mt-0.5 mb-2">{hint}</div>
      <div className="flex flex-wrap gap-1.5">
        {terms.map((t) => (
          <span
            key={t}
            className={`inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-mono bg-white/[0.04] ring-1 ${ring} ${text}`}
          >
            {t}
          </span>
        ))}
      </div>
    </div>
  );
}

function DriftConnector({
  drift,
  isPivot,
  color,
}: {
  drift: number;
  isPivot: boolean;
  color: string;
}) {
  // Drift bar — width 0-100% mapped from drift 0-0.5+; the pivot gets a
  // pink badge so the inflection moment reads at a glance.
  const widthPct = Math.min(100, Math.round((drift / 0.6) * 100));
  return (
    <div className="flex items-center gap-3 my-1.5 pl-4">
      <div className="flex-1 flex items-center gap-2">
        <div
          className="relative h-0.5 rounded-full overflow-hidden flex-1"
          style={{ backgroundColor: color + "22" }}
        >
          <span
            className="absolute inset-y-0 left-0 rounded-full"
            style={{
              width: `${widthPct}%`,
              background: isPivot
                ? "linear-gradient(90deg, #f472b6, #a855f7)"
                : `linear-gradient(90deg, ${color}88, ${color})`,
            }}
          />
        </div>
        <span className="text-[10px] font-mono text-ink-400">
          drift <span className="text-ink-200">{drift.toFixed(2)}</span>
        </span>
        {isPivot && (
          <span className="inline-flex items-center gap-1 rounded-full bg-synapse-pink/15 ring-1 ring-synapse-pink/50 px-2 py-0.5 text-[10px] font-mono text-synapse-pink">
            ⇆ pivot
          </span>
        )}
      </div>
    </div>
  );
}

function ChapterCard({
  cluster,
  chapter,
  isPivot,
  onSelectNote,
}: {
  cluster: ChronicleCluster;
  chapter: ChronicleChapter;
  isPivot: boolean;
  onSelectNote: (stub: { id: number; title: string; body: string; tags: string[] }) => void;
}) {
  return (
    <div
      className={`relative rounded-xl bg-white/[0.02] ring-1 p-4 ${
        isPivot ? "ring-synapse-pink/40" : "ring-white/5"
      }`}
      style={
        isPivot
          ? {
              background:
                "linear-gradient(135deg, rgba(244,114,182,0.06), rgba(168,85,247,0.04))",
            }
          : undefined
      }
    >
      <div className="flex items-start justify-between gap-3 mb-2 flex-wrap">
        <div className="flex items-center gap-2.5 min-w-0">
          <span
            className="inline-flex items-center justify-center w-6 h-6 rounded-full text-[11px] font-mono tabular-nums text-ink-900"
            style={{ backgroundColor: cluster.color }}
          >
            {chapter.index + 1}
          </span>
          <div className="min-w-0">
            <div className="text-[13px] font-semibold text-ink-100">
              Chapter {chapter.index + 1}
            </div>
            <div className="text-[10px] font-mono text-ink-400">
              {formatDateShort(chapter.date_start)} →{" "}
              {formatDateShort(chapter.date_end)} · {chapter.span_days}d
            </div>
          </div>
        </div>
        <div className="flex items-center gap-1.5 flex-wrap">
          <span className="inline-flex items-center gap-1 rounded-full bg-white/[0.03] ring-1 ring-white/10 px-2 py-0.5 text-[10px] font-mono text-ink-300">
            {chapter.count} note{chapter.count === 1 ? "" : "s"}
          </span>
          {chapter.drift_in > 0 && (
            <span className="inline-flex items-center gap-1 rounded-full bg-white/[0.03] ring-1 ring-white/10 px-2 py-0.5 text-[10px] font-mono text-ink-300">
              Δ {chapter.drift_in.toFixed(2)}
            </span>
          )}
        </div>
      </div>

      {chapter.terms.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mb-3">
          {chapter.terms.map((t) => (
            <span
              key={t}
              className="inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-mono"
              style={{
                backgroundColor: cluster.color + "1f",
                color: cluster.color,
              }}
            >
              {t}
            </span>
          ))}
        </div>
      )}

      <button
        onClick={() =>
          onSelectNote({
            id: chapter.anchor_id,
            title: chapter.anchor_title,
            body: chapter.anchor_sentence,
            tags: [],
          })
        }
        className="w-full text-left rounded-lg bg-white/[0.02] ring-1 ring-white/5 hover:ring-white/15 hover:bg-white/[0.04] p-3 transition group"
      >
        <div className="flex items-center justify-between gap-2 mb-1">
          <div className="text-[10px] font-mono uppercase tracking-[0.14em] text-ink-400">
            anchor — most representative of this chapter
          </div>
          <span className="text-[10px] font-mono text-ink-400 group-hover:text-ink-200 transition">
            open →
          </span>
        </div>
        <div className="text-sm font-semibold text-ink-100">
          {chapter.anchor_title}
        </div>
        {chapter.anchor_sentence && (
          <div className="text-[12px] text-ink-300 leading-relaxed mt-1">
            “{chapter.anchor_sentence}”
          </div>
        )}
      </button>
    </div>
  );
}

// ---------- States

function RailEmpty({
  report,
  filter,
}: {
  report: ChronicleReport;
  filter: ChronicleCategory | "all";
}) {
  if (report.eligible_clusters === 0) return null;
  return (
    <div className="rounded-xl bg-white/[0.02] ring-1 ring-white/5 p-3 text-xs text-ink-300">
      No {filter === "all" ? "" : filter + " "}clusters match this filter — try
      another band.
    </div>
  );
}

function EmptyState({ report }: { report: ChronicleReport }) {
  return (
    <div className="rounded-2xl bg-white/[0.02] ring-1 ring-white/10 p-6 text-sm text-ink-300 leading-relaxed">
      <div className="text-base font-semibold text-ink-100 mb-2">
        No chronicles to tell yet.
      </div>
      <p>
        Chronicle needs at least {report.min_cluster_notes} notes per cluster
        and a non-zero time span between them. Right now{" "}
        <span className="text-ink-100">
          {report.total_notes} note
          {report.total_notes === 1 ? "" : "s"}
        </span>{" "}
        across{" "}
        <span className="text-ink-100">
          {report.total_clusters} cluster
          {report.total_clusters === 1 ? "" : "s"}
        </span>{" "}
        don&apos;t cross that bar — keep writing, and clusters will start
        sprouting chapters as soon as they have a temporal arc to show.
      </p>
    </div>
  );
}

function RailSkeleton() {
  return (
    <div className="space-y-3 animate-pulse">
      {Array.from({ length: 4 }).map((_, i) => (
        <div key={i} className="rounded-xl bg-white/[0.02] ring-1 ring-white/5 p-3">
          <div className="h-3 w-2/3 bg-white/[0.06] rounded mb-2" />
          <div className="h-2 w-full bg-white/[0.04] rounded mb-1.5" />
          <div className="h-2 w-1/3 bg-white/[0.04] rounded" />
        </div>
      ))}
    </div>
  );
}

function TimelineSkeleton() {
  return (
    <div className="space-y-4 animate-pulse">
      <div className="h-6 w-2/3 bg-white/[0.06] rounded" />
      <div className="h-3 w-1/2 bg-white/[0.04] rounded" />
      <div className="grid grid-cols-2 gap-3">
        <div className="h-20 bg-white/[0.04] rounded-xl" />
        <div className="h-20 bg-white/[0.04] rounded-xl" />
      </div>
      <div className="h-32 bg-white/[0.04] rounded-xl" />
      <div className="h-32 bg-white/[0.04] rounded-xl" />
    </div>
  );
}

function ChronicleGlyph() {
  // Simple "scroll/timeline" glyph — three nodes connected by an arc,
  // with the middle one slightly higher to suggest the pivot peak.
  return (
    <span
      className="inline-flex items-center justify-center w-9 h-9 rounded-xl bg-gradient-to-br from-synapse-pink/20 to-synapse-violet/10 ring-1 ring-synapse-pink/40"
      aria-hidden
    >
      <svg viewBox="0 0 28 28" className="w-5 h-5">
        <defs>
          <linearGradient id="chr-g" x1="0" y1="1" x2="1" y2="0">
            <stop offset="0%" stopColor="#f472b6" />
            <stop offset="100%" stopColor="#a855f7" />
          </linearGradient>
        </defs>
        <path
          d="M3 21 C 9 6, 15 6, 25 18"
          fill="none"
          stroke="url(#chr-g)"
          strokeWidth="1.5"
          strokeLinecap="round"
        />
        <circle cx="3" cy="21" r="2" fill="#f472b6" />
        <circle cx="14" cy="9" r="2.5" fill="#a855f7" />
        <circle cx="25" cy="18" r="2" fill="#22d3ee" />
      </svg>
    </span>
  );
}
