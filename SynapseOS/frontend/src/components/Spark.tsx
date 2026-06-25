"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import type {
  GraphNode,
  NoteDraft,
  Spark,
  SparkKind,
  SparkReport,
} from "@/lib/types";

type Props = {
  open: boolean;
  onClose: () => void;
  /**
   * Pre-fill the NoteComposer with a spark's draft. Same channel
   * Tensions's Reconcile uses — the composer hydrates from the draft,
   * scrolls into view, and focuses the body.
   */
  onUseDraft: (draft: NoteDraft) => void;
  /** Jump the canvas onto a cited note (closes the modal). */
  onSelectNote: (stub: GraphNode) => void;
  /** Optional bonus — close the modal too when a draft is sent. */
  onAfterUse?: () => void;
};

type Filter = SparkKind | "all";

const FILTER_TABS: { value: Filter; label: string }[] = [
  { value: "all", label: "All" },
  { value: "bridge", label: "Bridge" },
  { value: "distill", label: "Distill" },
  { value: "counter", label: "Counter" },
  { value: "frontier", label: "Frontier" },
  { value: "revive", label: "Revive" },
];

const KIND_META: Record<
  SparkKind,
  {
    label: string;
    tagline: string;
    glyph: string;
    /** Tailwind gradient stops used to tint cards / chips per kind. */
    cardGrad: string;
    ring: string;
    text: string;
    chip: string;
    glow: string;
  }
> = {
  bridge: {
    label: "Bridge",
    tagline: "connector between two semantically close clusters",
    glyph: "⇄",
    cardGrad: "from-synapse-violet/14 via-synapse-cyan/10 to-transparent",
    ring: "ring-synapse-violet/45",
    text: "text-synapse-violet",
    chip: "bg-synapse-violet/15 text-synapse-violet ring-1 ring-synapse-violet/40",
    glow: "shadow-[0_0_36px_-12px_rgba(168,85,247,0.55)]",
  },
  distill: {
    label: "Distill",
    tagline: "anchor an un-anchored cohesive cluster with a synthesis note",
    glyph: "❍",
    cardGrad: "from-synapse-cyan/14 via-sky-400/8 to-transparent",
    ring: "ring-synapse-cyan/45",
    text: "text-synapse-cyan",
    chip: "bg-synapse-cyan/15 text-synapse-cyan ring-1 ring-synapse-cyan/40",
    glow: "shadow-[0_0_36px_-12px_rgba(34,211,238,0.55)]",
  },
  counter: {
    label: "Counter",
    tagline: "write the opposing voice the cluster is missing",
    glyph: "⊘",
    cardGrad: "from-rose-500/15 via-synapse-violet/8 to-transparent",
    ring: "ring-rose-400/45",
    text: "text-rose-300",
    chip: "bg-rose-500/15 text-rose-200 ring-1 ring-rose-400/40",
    glow: "shadow-[0_0_36px_-12px_rgba(244,63,94,0.55)]",
  },
  frontier: {
    label: "Frontier",
    tagline: "define a single-mention concept before it slips away",
    glyph: "✺",
    cardGrad: "from-synapse-lime/14 via-emerald-400/8 to-transparent",
    ring: "ring-synapse-lime/45",
    text: "text-synapse-lime",
    chip: "bg-synapse-lime/15 text-synapse-lime ring-1 ring-synapse-lime/40",
    glow: "shadow-[0_0_36px_-12px_rgba(163,230,53,0.55)]",
  },
  revive: {
    label: "Revive",
    tagline: "re-enter a cohesive but dormant cluster",
    glyph: "☼",
    cardGrad: "from-synapse-amber/14 via-orange-400/8 to-transparent",
    ring: "ring-synapse-amber/45",
    text: "text-synapse-amber",
    chip: "bg-synapse-amber/15 text-synapse-amber ring-1 ring-synapse-amber/40",
    glow: "shadow-[0_0_36px_-12px_rgba(251,191,36,0.55)]",
  },
};

/**
 * Spark — the first *generative* surface in SynapseOS.
 *
 * Every other surface describes what's in your graph. Spark proposes
 * what should be *next*: a queue of concrete next-note drafts targeting
 * specific structural gaps (bridges, un-anchored clusters, missing
 * opposing voices, single-mention frontier terms, dormant vaults).
 *
 * Each card shows a draft title + opener + tags + predicted cluster +
 * the synapses it would form, plus the cited evidence the spark draws
 * from. "Use this draft" hands the NoteComposer a pre-filled draft —
 * the user skims, edits, and saves.
 */
export function Spark({ open, onClose, onUseDraft, onSelectNote, onAfterUse }: Props) {
  const [report, setReport] = useState<SparkReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<Filter>("all");
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [usedIds, setUsedIds] = useState<Set<string>>(new Set());

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await api.spark({ limit: 16, perKind: 4 });
      setReport(r);
    } catch (e) {
      setError(e instanceof Error ? e.message : "failed to load sparks");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (open) load();
  }, [open, load]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  // Reset session-only state when the modal closes so a fresh open is
  // a fresh queue.
  useEffect(() => {
    if (!open) {
      setExpandedId(null);
      setUsedIds(new Set());
    }
  }, [open]);

  const filtered = useMemo(() => {
    if (!report) return [] as Spark[];
    if (filter === "all") return report.sparks;
    return report.sparks.filter((s) => s.kind === filter);
  }, [report, filter]);

  const counts = useMemo(() => {
    const c: Record<Filter, number> = {
      all: 0,
      bridge: 0,
      distill: 0,
      counter: 0,
      frontier: 0,
      revive: 0,
    };
    if (!report) return c;
    c.all = report.sparks.length;
    for (const s of report.sparks) c[s.kind] = (c[s.kind] ?? 0) + 1;
    return c;
  }, [report]);

  const handleUse = useCallback(
    (sp: Spark) => {
      const draft: NoteDraft = {
        title: sp.title,
        body: sp.body,
        tags: sp.tags,
      };
      onUseDraft(draft);
      setUsedIds((prev) => {
        const next = new Set(prev);
        next.add(sp.id);
        return next;
      });
      onAfterUse?.();
    },
    [onUseDraft, onAfterUse],
  );

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center px-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="spark-title"
    >
      <div
        className="absolute inset-0 bg-ink-900/80 backdrop-blur-md"
        onClick={onClose}
      />
      <div className="absolute inset-0 pointer-events-none bg-grid-fade opacity-60" />

      <div className="relative w-full max-w-6xl max-h-[92vh] flex flex-col rounded-2xl bg-ink-800/92 ring-1 ring-white/10 shadow-card overflow-hidden animate-fade-in">
        {/* Header band */}
        <div
          className="flex items-center justify-between gap-4 px-6 py-4 border-b border-white/5"
          style={{
            background:
              "linear-gradient(90deg, rgba(168,85,247,0.18), rgba(34,211,238,0.10) 40%, rgba(163,230,53,0.10) 70%, rgba(251,191,36,0.10))",
          }}
        >
          <div className="flex items-center gap-3 min-w-0">
            <SparkGlyph />
            <div className="min-w-0">
              <div
                id="spark-title"
                className="text-base font-semibold tracking-tight text-ink-100 flex items-center gap-2"
              >
                Spark — what to write next
                <span className="px-1.5 py-0.5 rounded-md bg-gradient-to-r from-synapse-violet/30 to-synapse-cyan/30 ring-1 ring-white/10 text-[9px] uppercase tracking-widest text-ink-100">
                  new
                </span>
              </div>
              <div className="text-[11px] font-mono text-ink-300 uppercase tracking-[0.16em] mt-0.5">
                graph gaps → concrete next-note drafts · predicted synapses live
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            {report && (
              <a
                href={api.sparkExportUrl({ limit: 16 })}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1 rounded-full bg-white/[0.03] ring-1 ring-white/10 hover:ring-white/30 px-3 py-1 font-mono text-[11px] text-ink-300 hover:text-ink-100 transition"
                title="Export the full spark queue as portable Markdown"
              >
                ⤓ md
              </a>
            )}
            <button
              onClick={load}
              className="inline-flex items-center gap-1 rounded-full bg-white/[0.03] ring-1 ring-white/10 hover:ring-white/30 px-3 py-1 font-mono text-[11px] text-ink-300 hover:text-ink-100 transition"
              disabled={loading}
              title="Recompute the spark queue against current graph state"
            >
              ↻ {loading ? "spinning" : "re-spark"}
            </button>
            <button
              onClick={onClose}
              className="text-ink-300 hover:text-ink-100 transition px-2"
              aria-label="close"
            >
              ✕
            </button>
          </div>
        </div>

        {/* Filter + stats row */}
        <div className="flex flex-wrap items-center gap-2 px-6 py-3 border-b border-white/5 bg-ink-900/40">
          {FILTER_TABS.map((tab) => {
            const active = filter === tab.value;
            const meta = tab.value !== "all" ? KIND_META[tab.value] : null;
            return (
              <button
                key={tab.value}
                onClick={() => setFilter(tab.value)}
                className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 font-mono text-[11px] transition ${
                  active
                    ? meta
                      ? `${meta.chip} ${meta.glow}`
                      : "bg-gradient-to-r from-synapse-violet/25 to-synapse-cyan/25 ring-1 ring-white/30 text-ink-100"
                    : "bg-white/[0.02] ring-1 ring-white/5 text-ink-300 hover:text-ink-100 hover:ring-white/15"
                }`}
              >
                {meta && <span aria-hidden>{meta.glyph}</span>}
                {tab.label}
                <span className="ml-1 inline-flex items-center justify-center min-w-[1.1rem] h-[1.1rem] rounded-full bg-white/[0.06] ring-1 ring-white/10 text-[10px] text-ink-200 px-1">
                  {counts[tab.value]}
                </span>
              </button>
            );
          })}
          {report && (
            <div className="ml-auto flex items-center gap-2 font-mono text-[11px] text-ink-300">
              <span className="inline-flex items-center gap-1 rounded-full bg-white/[0.02] ring-1 ring-white/5 px-2.5 py-1">
                <span className="opacity-70">avg synapses</span>
                <span className="text-ink-100">
                  {(report.summary.mean_predicted_synapses ?? 0).toFixed(1)}
                </span>
              </span>
              <span className="inline-flex items-center gap-1 rounded-full bg-white/[0.02] ring-1 ring-white/5 px-2.5 py-1">
                <span className="opacity-70">notes</span>
                <span className="text-ink-100">{report.total_notes}</span>
              </span>
              <span className="inline-flex items-center gap-1 rounded-full bg-white/[0.02] ring-1 ring-white/5 px-2.5 py-1">
                <span className="opacity-70">clusters</span>
                <span className="text-ink-100">{report.total_clusters}</span>
              </span>
            </div>
          )}
        </div>

        {/* Cards body */}
        <div className="flex-1 overflow-y-auto p-6">
          {loading && !report && (
            <div className="grid place-items-center text-ink-300 font-mono text-xs h-64">
              <div className="flex items-center gap-3">
                <SparkSpinner />
                sparking the queue …
              </div>
            </div>
          )}
          {error && !loading && (
            <div className="rounded-xl bg-rose-500/8 ring-1 ring-rose-400/40 p-4 text-xs font-mono text-rose-200">
              {error}
            </div>
          )}
          {!loading && report && filtered.length === 0 && (
            <EmptyState filter={filter} />
          )}
          {!loading && report && filtered.length > 0 && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
              {filtered.map((sp) => (
                <SparkCard
                  key={sp.id}
                  spark={sp}
                  expanded={expandedId === sp.id}
                  used={usedIds.has(sp.id)}
                  onToggle={() =>
                    setExpandedId((prev) => (prev === sp.id ? null : sp.id))
                  }
                  onUse={() => handleUse(sp)}
                  onSelectNote={(noteId, title) => {
                    onSelectNote({
                      id: noteId,
                      title,
                      body: "",
                      tags: [],
                      degree: 0,
                      weight: 0,
                    } as GraphNode);
                  }}
                />
              ))}
            </div>
          )}
        </div>

        {/* Footer hint */}
        <div className="border-t border-white/5 px-6 py-2 text-[10px] font-mono text-ink-400 flex items-center justify-between">
          <span>
            spark queue is deterministic — same graph state ⇒ same sparks ·
            press <span className="text-ink-200">esc</span> to close
          </span>
          <span>
            ✦ Use this draft → opens NoteComposer with title/body/tags
            pre-filled
          </span>
        </div>
      </div>
    </div>
  );
}

// ----------------------------------------------------------------- card

function SparkCard({
  spark,
  expanded,
  used,
  onToggle,
  onUse,
  onSelectNote,
}: {
  spark: Spark;
  expanded: boolean;
  used: boolean;
  onToggle: () => void;
  onUse: () => void;
  onSelectNote: (noteId: number, title: string) => void;
}) {
  const meta = KIND_META[spark.kind];
  const pri = Math.max(0, Math.min(1, spark.priority));
  return (
    <article
      className={`relative rounded-2xl bg-gradient-to-br ${meta.cardGrad} ring-1 ${meta.ring} p-5 transition ${
        used ? "opacity-65" : "hover:ring-white/20"
      }`}
    >
      {/* top row — kind tag + priority */}
      <div className="flex items-start justify-between gap-3 mb-3">
        <div className="flex items-center gap-2 min-w-0">
          <span
            className={`inline-flex items-center gap-1 rounded-md px-2 py-0.5 font-mono text-[10px] uppercase tracking-widest ${meta.chip}`}
          >
            <span aria-hidden className="text-base leading-none">
              {meta.glyph}
            </span>
            {meta.label}
          </span>
          {spark.kind === "bridge" &&
            spark.bridge_cluster_a_name &&
            spark.bridge_cluster_b_name && (
              <span className="text-[10px] font-mono text-ink-300">
                <ClusterDot color={spark.bridge_cluster_a_color} />
                {spark.bridge_cluster_a_name}
                <span className="mx-1 opacity-50">↔</span>
                <ClusterDot color={spark.bridge_cluster_b_color} />
                {spark.bridge_cluster_b_name}
                {spark.bridge_centroid_cosine > 0 && (
                  <span className="ml-1 opacity-60">
                    cos {spark.bridge_centroid_cosine.toFixed(2)}
                  </span>
                )}
              </span>
            )}
        </div>
        <PriorityRing value={pri} color={meta.text} />
      </div>

      {/* title */}
      <h3 className="text-base font-semibold tracking-tight text-ink-100 leading-snug mb-1">
        {spark.title}
      </h3>

      {/* rationale */}
      <p className="text-[11px] italic text-ink-300 leading-snug mb-3">
        {spark.rationale}
      </p>

      {/* body preview */}
      <div className="rounded-lg bg-ink-900/40 ring-1 ring-white/5 p-3 mb-3 text-[12.5px] text-ink-200 leading-relaxed font-[450] whitespace-pre-line">
        {expanded || spark.body.length <= 360
          ? spark.body
          : `${spark.body.slice(0, 360).trimEnd()}…`}
        {spark.body.length > 360 && (
          <button
            onClick={onToggle}
            className="ml-2 font-mono text-[10px] text-ink-300 hover:text-ink-100 underline-offset-2 hover:underline"
          >
            {expanded ? "show less" : "show full"}
          </button>
        )}
      </div>

      {/* tags */}
      {spark.tags.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mb-3">
          {spark.tags.map((t) => (
            <span
              key={t}
              className="inline-flex items-center rounded-md px-1.5 py-0.5 font-mono text-[10px] bg-white/[0.04] ring-1 ring-white/10 text-ink-200"
            >
              #{t}
            </span>
          ))}
        </div>
      )}

      {/* predicted landing */}
      {(spark.predicted_cluster_name || spark.expected_synapse_count > 0) && (
        <div className="rounded-lg bg-white/[0.02] ring-1 ring-white/5 p-3 mb-3 text-[11px] text-ink-300 leading-relaxed">
          <div className="flex items-center justify-between gap-2 mb-1.5">
            <span className="uppercase tracking-[0.15em] text-[10px] text-ink-400">
              if you commit this
            </span>
            <span className="font-mono text-ink-200">
              {spark.expected_synapse_count} synapse
              {spark.expected_synapse_count === 1 ? "" : "s"}
            </span>
          </div>
          {spark.predicted_cluster_name && (
            <div className="flex items-center gap-2 mb-2">
              <span className="text-ink-400">lands in</span>
              <ClusterDot color={spark.predicted_cluster_color} />
              <span className="text-ink-100 font-medium">
                {spark.predicted_cluster_name}
              </span>
              <span className="font-mono text-ink-400 text-[10px]">
                strength {spark.predicted_cluster_strength.toFixed(2)}
              </span>
            </div>
          )}
          {spark.predicted_synapses.length > 0 && (
            <ul className="space-y-1">
              {spark.predicted_synapses.slice(0, 4).map((p) => (
                <li key={p.note_id} className="flex items-center gap-2 min-w-0">
                  <SynapseBar value={p.strength} />
                  <button
                    onClick={() => onSelectNote(p.note_id, p.title)}
                    className="truncate text-left text-ink-200 hover:text-ink-100 underline-offset-2 hover:underline"
                    title={p.title}
                  >
                    {p.title}
                  </button>
                  <span className="ml-auto font-mono text-[10px] text-ink-400 shrink-0">
                    {p.strength.toFixed(2)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {/* cited evidence */}
      {spark.cited_evidence.length > 0 && (
        <div className="rounded-lg bg-white/[0.015] ring-1 ring-white/5 p-3 mb-3">
          <div className="flex items-center justify-between gap-2 mb-1.5">
            <span className="uppercase tracking-[0.15em] text-[10px] text-ink-400">
              cites
            </span>
            <span className="text-[10px] text-ink-500">
              what this spark draws from
            </span>
          </div>
          <ul className="space-y-2">
            {spark.cited_evidence.map((ev) => (
              <li
                key={ev.note_id}
                className="text-[11.5px] text-ink-300 leading-snug"
              >
                <button
                  onClick={() => onSelectNote(ev.note_id, ev.title)}
                  className="text-ink-100 font-medium hover:underline mr-1"
                  title="Open this note on the canvas"
                >
                  {ev.title}
                </button>
                {ev.cluster_name && (
                  <span className="text-[10px] font-mono text-ink-400">
                    <ClusterDot color={ev.cluster_color} />
                    {ev.cluster_name}
                  </span>
                )}
                <div className="text-ink-300 italic mt-0.5">
                  “{ev.snippet}”
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* action row */}
      <div className="flex items-center gap-2 pt-1">
        <button
          onClick={onUse}
          disabled={used}
          className={`inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 font-mono text-[11px] transition ${
            used
              ? "bg-white/[0.04] text-ink-400 ring-1 ring-white/10 cursor-default"
              : `bg-gradient-to-r ${meta.cardGrad.replace("/14", "/30").replace("/10", "/25").replace("/8", "/20")} ring-1 ${meta.ring} ${meta.text} hover:brightness-110`
          }`}
          title="Open the NoteComposer with this draft pre-filled"
        >
          {used ? "✓ sent to composer" : "✦ use this draft"}
        </button>
        <button
          onClick={onToggle}
          className="inline-flex items-center gap-1 rounded-md bg-white/[0.03] ring-1 ring-white/10 px-2.5 py-1.5 font-mono text-[11px] text-ink-300 hover:text-ink-100 hover:ring-white/25"
        >
          {expanded ? "− less" : "+ details"}
        </button>
        <span className="ml-auto font-mono text-[10px] text-ink-500">
          spark id <span className="text-ink-300">{spark.id}</span>
        </span>
      </div>
    </article>
  );
}

// ------------------------------------------------------------- support

function PriorityRing({ value, color }: { value: number; color: string }) {
  const pct = Math.round(value * 100);
  const stroke = 4;
  const r = 14;
  const c = 2 * Math.PI * r;
  return (
    <div className="relative w-9 h-9 shrink-0" title={`priority ${pct}/100`}>
      <svg viewBox="0 0 36 36" className="w-full h-full -rotate-90">
        <circle
          cx="18"
          cy="18"
          r={r}
          stroke="currentColor"
          strokeWidth={stroke}
          fill="none"
          className="text-white/[0.06]"
        />
        <circle
          cx="18"
          cy="18"
          r={r}
          stroke="currentColor"
          strokeWidth={stroke}
          strokeLinecap="round"
          fill="none"
          strokeDasharray={`${(value * c).toFixed(2)} ${c.toFixed(2)}`}
          className={color}
        />
      </svg>
      <span
        className={`absolute inset-0 grid place-items-center font-mono text-[10px] ${color}`}
      >
        {pct}
      </span>
    </div>
  );
}

function SynapseBar({ value }: { value: number }) {
  const pct = Math.max(0, Math.min(1, value));
  const hue = Math.round(180 + pct * 80); // cyan → violet ramp
  return (
    <div
      className="w-10 h-1.5 rounded-full bg-white/[0.05] overflow-hidden shrink-0"
      title={`cosine ${value.toFixed(3)}`}
    >
      <div
        className="h-full rounded-full"
        style={{
          width: `${pct * 100}%`,
          background: `linear-gradient(90deg, hsl(${hue} 80% 60%), hsl(${hue + 40} 90% 65%))`,
        }}
      />
    </div>
  );
}

function ClusterDot({ color }: { color: string | null }) {
  return (
    <span
      className="inline-block w-2 h-2 rounded-full mr-1 align-middle ring-1 ring-white/20"
      style={{ background: color ?? "#64748b" }}
    />
  );
}

function SparkGlyph() {
  return (
    <div className="relative w-10 h-10 rounded-xl bg-gradient-to-br from-synapse-violet/30 via-synapse-cyan/20 to-synapse-amber/20 ring-1 ring-white/15 grid place-items-center shadow-[0_0_24px_-6px_rgba(168,85,247,0.55)]">
      <svg
        viewBox="0 0 24 24"
        className="w-5 h-5 text-ink-100 animate-pulse-slow"
        fill="currentColor"
        aria-hidden
      >
        <path d="M13 2 3 14h7l-1 8 10-12h-7l1-8z" />
      </svg>
    </div>
  );
}

function SparkSpinner() {
  return (
    <span className="relative inline-flex w-4 h-4">
      <span className="absolute inset-0 rounded-full ring-2 ring-synapse-violet/30 border-t-2 border-t-synapse-violet animate-spin" />
    </span>
  );
}

function EmptyState({ filter }: { filter: Filter }) {
  return (
    <div className="grid place-items-center min-h-[40vh]">
      <div className="max-w-md text-center space-y-3">
        <div className="text-4xl">✨</div>
        <div className="text-sm text-ink-100 font-medium">
          No sparks{filter === "all" ? "" : ` of kind ${filter}`} right now.
        </div>
        <p className="text-xs text-ink-400 leading-relaxed">
          {filter === "all"
            ? "Your graph has no obvious gaps at the current threshold. Write a few more notes and recompute, or nudge τ in the Atlas to surface more candidates."
            : "Try a different kind, or write a note that creates the pathology this spark watches for."}
        </p>
      </div>
    </div>
  );
}
