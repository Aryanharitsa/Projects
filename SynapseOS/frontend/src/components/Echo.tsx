"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import type {
  EchoCluster,
  EchoMember,
  EchoReport,
  EchoSentence,
  GraphNode,
} from "@/lib/types";

type NoteStub = Pick<GraphNode, "id" | "title" | "body" | "tags" | "degree" | "weight">;

type Props = {
  open: boolean;
  onClose: () => void;
  onSelectNote: (node: NoteStub) => void;
  /** Called after a merge or skip mutates the store so the parent can refresh. */
  onMutated: () => void;
};

const THRESHOLD_PRESETS = [
  { value: 0.6, label: "loose" },
  { value: 0.72, label: "default" },
  { value: 0.8, label: "tight" },
  { value: 0.88, label: "exact" },
];

/**
 * Echo — semantic de-duplication studio.
 *
 * Mature second-brains accumulate restatements: the same insight written
 * three times across three weeks. Echo finds those clusters, shows you
 * the sentence-level overlap, and lets you collapse them into one
 * canonical note (or mark a pair as intentionally distinct so it never
 * gets flagged again).
 */
export function Echo({ open, onClose, onSelectNote, onMutated }: Props) {
  const [report, setReport] = useState<EchoReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [threshold, setThreshold] = useState(0.72);
  const [activeClusterId, setActiveClusterId] = useState<string | null>(null);
  const [busy, setBusy] = useState<"none" | "merge" | "skip">("none");
  const [flash, setFlash] = useState<string | null>(null);

  // Per-active-cluster local state — canonical choice + dropped members
  // + body/title overrides. Resets whenever the active cluster changes.
  const [canonOverride, setCanonOverride] = useState<number | null>(null);
  const [droppedIds, setDroppedIds] = useState<Set<number>>(new Set());
  const [titleOverride, setTitleOverride] = useState<string | null>(null);
  const [bodyOverride, setBodyOverride] = useState<string | null>(null);

  const load = useCallback(
    async (t: number) => {
      setLoading(true);
      setError(null);
      try {
        const r = await api.echo({ threshold: t });
        setReport(r);
        if (r.clusters.length > 0) {
          // Preserve the active cluster if it still exists, else pick top.
          setActiveClusterId((prev) => {
            if (prev && r.clusters.some((c) => c.cluster_id === prev)) return prev;
            return r.clusters[0]?.cluster_id ?? null;
          });
        } else {
          setActiveClusterId(null);
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : "failed to load echoes");
      } finally {
        setLoading(false);
      }
    },
    [],
  );

  useEffect(() => {
    if (open) load(threshold);
  }, [open, threshold, load]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  // Reset local overrides whenever the user switches clusters.
  useEffect(() => {
    setCanonOverride(null);
    setDroppedIds(new Set());
    setTitleOverride(null);
    setBodyOverride(null);
  }, [activeClusterId]);

  const active = useMemo<EchoCluster | null>(() => {
    if (!report || !activeClusterId) return null;
    return report.clusters.find((c) => c.cluster_id === activeClusterId) ?? null;
  }, [report, activeClusterId]);

  // Effective member list after the user drops some out of the merge.
  const effectiveMemberIds = useMemo<number[]>(() => {
    if (!active) return [];
    return active.members
      .map((m) => m.note_id)
      .filter((id) => !droppedIds.has(id));
  }, [active, droppedIds]);

  const effectiveCanon = useMemo<number | null>(() => {
    if (!active) return null;
    if (canonOverride !== null && effectiveMemberIds.includes(canonOverride)) {
      return canonOverride;
    }
    if (effectiveMemberIds.includes(active.canonical_id)) {
      return active.canonical_id;
    }
    return effectiveMemberIds[0] ?? null;
  }, [active, canonOverride, effectiveMemberIds]);

  // Live merge preview — recomputed server-side every time the user
  // changes canonical or drops a member. Debounced via a small async
  // race-guard so rapid clicks don't blow up the in-flight queue.
  const [preview, setPreview] = useState<EchoCluster | null>(null);
  const [previewBusy, setPreviewBusy] = useState(false);

  useEffect(() => {
    if (!active || effectiveMemberIds.length < 2 || effectiveCanon === null) {
      setPreview(null);
      return;
    }
    let cancelled = false;
    setPreviewBusy(true);
    api
      .echoPreview({
        note_ids: effectiveMemberIds,
        canonical_id: effectiveCanon,
      })
      .then((p) => {
        if (!cancelled) setPreview(p);
      })
      .catch(() => {
        if (!cancelled) setPreview(null);
      })
      .finally(() => {
        if (!cancelled) setPreviewBusy(false);
      });
    return () => {
      cancelled = true;
    };
  }, [active, effectiveMemberIds, effectiveCanon]);

  const flashFor = useCallback((msg: string) => {
    setFlash(msg);
    window.setTimeout(() => setFlash(null), 5500);
  }, []);

  const doMerge = useCallback(async () => {
    if (!active || !preview || effectiveCanon === null) return;
    setBusy("merge");
    try {
      const res = await api.echoMerge({
        note_ids: effectiveMemberIds,
        canonical_id: effectiveCanon,
        title: titleOverride ?? preview.merged_title,
        body: bodyOverride ?? preview.merged_body,
        tags: preview.merged_tags,
      });
      flashFor(
        `merged → #${res.merged_note_id} · ${res.deleted_ids.length} dupe${res.deleted_ids.length === 1 ? "" : "s"} removed · ${res.wasted_chars_recovered} chars recovered`,
      );
      onMutated();
      await load(threshold);
    } catch (e) {
      setError(e instanceof Error ? e.message : "merge failed");
    } finally {
      setBusy("none");
    }
  }, [
    active,
    preview,
    effectiveCanon,
    effectiveMemberIds,
    titleOverride,
    bodyOverride,
    threshold,
    load,
    onMutated,
    flashFor,
  ]);

  const doSkipCluster = useCallback(async () => {
    if (!active) return;
    setBusy("skip");
    try {
      // Mark every pair in the cluster as distinct.
      const pairs: [number, number][] = active.pairs.map((p) => [p.a_id, p.b_id]);
      await api.echoSkip({ pairs, reason: "marked distinct from Echo" });
      flashFor(
        `marked ${pairs.length} pair${pairs.length === 1 ? "" : "s"} distinct — cluster dismissed`,
      );
      onMutated();
      await load(threshold);
    } catch (e) {
      setError(e instanceof Error ? e.message : "skip failed");
    } finally {
      setBusy("none");
    }
  }, [active, threshold, load, onMutated, flashFor]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center px-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="echo-title"
    >
      <div
        className="absolute inset-0 bg-ink-900/80 backdrop-blur-md"
        onClick={onClose}
      />
      <div className="absolute inset-0 pointer-events-none bg-grid-fade opacity-60" />

      <div className="relative w-full max-w-6xl max-h-[90vh] flex flex-col rounded-2xl bg-ink-800/90 ring-1 ring-white/10 shadow-card overflow-hidden animate-fade-in">
        {/* Header strip — teal/amber gradient for the "echo / waveform" feel */}
        <div
          className="flex items-center justify-between gap-4 px-6 py-4 border-b border-white/5"
          style={{
            background:
              "linear-gradient(90deg, rgba(34,211,238,0.14), rgba(251,191,36,0.10) 40%, transparent 80%)",
          }}
        >
          <div className="flex items-center gap-3 min-w-0">
            <EchoGlyph />
            <div className="min-w-0">
              <div
                id="echo-title"
                className="text-base font-semibold tracking-tight text-ink-100 truncate"
              >
                Echoes — collapse the duplicates in your second brain
              </div>
              <div className="text-[11px] font-mono text-ink-300 uppercase tracking-[0.16em] mt-0.5">
                semantic dedup · sentence overlap · safe-merge
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            {report && report.cluster_count > 0 && (
              <a
                href={api.echoExportUrl({ threshold })}
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

        {/* Threshold + summary strip */}
        <div className="flex items-center justify-between gap-4 px-6 py-3 border-b border-white/5 bg-ink-800/60 flex-wrap">
          <div className="flex items-center gap-2 text-[11px] font-mono">
            <span className="text-ink-300 uppercase tracking-[0.16em]">τ</span>
            <input
              type="range"
              min={0.5}
              max={0.95}
              step={0.01}
              value={threshold}
              onChange={(e) => setThreshold(Number(e.target.value))}
              className="w-40 accent-synapse-cyan"
              aria-label="threshold"
            />
            <span className="text-synapse-cyan w-10">{threshold.toFixed(2)}</span>
            <div className="flex items-center gap-1 ml-2">
              {THRESHOLD_PRESETS.map((p) => (
                <button
                  key={p.value}
                  onClick={() => setThreshold(p.value)}
                  className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 ring-1 transition ${
                    Math.abs(threshold - p.value) < 0.005
                      ? "ring-synapse-cyan/60 text-synapse-cyan bg-synapse-cyan/15"
                      : "ring-white/10 text-ink-300 hover:text-ink-100 hover:ring-white/20"
                  }`}
                >
                  <span className="text-ink-400">{p.value.toFixed(2)}</span>
                  <span>{p.label}</span>
                </button>
              ))}
            </div>
          </div>
          {report && (
            <div className="text-[11px] font-mono text-ink-400 flex items-center gap-4">
              <span>
                <span className="text-ink-100">{report.cluster_count}</span>{" "}
                cluster{report.cluster_count === 1 ? "" : "s"}
              </span>
              <span>
                <span className="text-ink-100">{report.candidate_pairs}</span>{" "}
                dupe pair{report.candidate_pairs === 1 ? "" : "s"}
              </span>
              <span>
                <span className="text-ink-100">
                  {report.stats?.wasted_chars_total ?? 0}
                </span>{" "}
                chars recoverable
              </span>
              {report.skipped_pair_count > 0 && (
                <span title="pairs you previously marked distinct">
                  <span className="text-ink-100">
                    {report.skipped_pair_count}
                  </span>{" "}
                  skipped
                </span>
              )}
            </div>
          )}
        </div>

        {/* Body */}
        <div className="grid grid-cols-12 gap-0 overflow-hidden flex-1 min-h-0">
          {/* Cluster rail */}
          <aside className="col-span-12 md:col-span-4 lg:col-span-3 border-r border-white/5 bg-ink-900/30 overflow-y-auto min-h-0">
            {loading && <ClusterRailSkeleton />}
            {!loading && error && (
              <div className="m-4 rounded-xl bg-rose-500/10 ring-1 ring-rose-500/30 p-3 text-xs text-rose-200">
                {error}
              </div>
            )}
            {!loading && !error && report && report.cluster_count === 0 && (
              <ClusterRailEmpty />
            )}
            {!loading && !error && report && report.clusters.length > 0 && (
              <ul className="p-2 space-y-1">
                {report.clusters.map((c) => (
                  <li key={c.cluster_id}>
                    <ClusterRow
                      cluster={c}
                      active={c.cluster_id === activeClusterId}
                      onSelect={() => setActiveClusterId(c.cluster_id)}
                    />
                  </li>
                ))}
              </ul>
            )}
          </aside>

          {/* Active cluster detail */}
          <section className="col-span-12 md:col-span-8 lg:col-span-9 overflow-y-auto min-h-0">
            {!active && !loading && (
              <div className="h-full flex items-center justify-center p-8">
                <p className="text-xs text-ink-400 font-mono text-center max-w-sm">
                  No active cluster. Drop the threshold to find weaker matches
                  or add a few more notes to your second brain.
                </p>
              </div>
            )}
            {active && (
              <div className="p-6 space-y-6">
                <ClusterHeader
                  cluster={active}
                  preview={preview}
                  effectiveCount={effectiveMemberIds.length}
                />

                <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
                  {active.members.map((m) => (
                    <MemberCard
                      key={m.note_id}
                      member={m}
                      isCanonical={effectiveCanon === m.note_id}
                      isDropped={droppedIds.has(m.note_id)}
                      sentences={active.sentences}
                      onMakeCanonical={() => setCanonOverride(m.note_id)}
                      onToggleDropped={() => {
                        setDroppedIds((prev) => {
                          const next = new Set(prev);
                          if (next.has(m.note_id)) next.delete(m.note_id);
                          else next.add(m.note_id);
                          return next;
                        });
                      }}
                      onOpen={() =>
                        onSelectNote({
                          id: m.note_id,
                          title: m.title,
                          body: m.body,
                          tags: m.tags,
                          degree: 0,
                          weight: 0,
                        })
                      }
                    />
                  ))}
                </div>

                <PairLadder cluster={active} />

                <MergePreview
                  cluster={active}
                  preview={preview}
                  busy={previewBusy}
                  titleOverride={titleOverride}
                  bodyOverride={bodyOverride}
                  onTitleChange={setTitleOverride}
                  onBodyChange={setBodyOverride}
                  effectiveCanon={effectiveCanon}
                  effectiveCount={effectiveMemberIds.length}
                />

                <div className="flex items-center justify-between gap-3 pt-2">
                  <button
                    onClick={doSkipCluster}
                    disabled={busy !== "none"}
                    className="inline-flex items-center gap-2 rounded-lg px-4 py-2 text-xs font-medium text-ink-200 ring-1 ring-white/10 bg-white/[0.03] hover:ring-white/20 hover:text-ink-100 transition disabled:opacity-50"
                    title="Hide this cluster forever — these are intentionally separate notes"
                  >
                    {busy === "skip" ? "…" : "✕"} Mark distinct
                  </button>
                  <button
                    onClick={doMerge}
                    disabled={
                      busy !== "none" ||
                      !preview ||
                      effectiveMemberIds.length < 2
                    }
                    className="inline-flex items-center gap-2 rounded-lg px-5 py-2 text-sm font-medium text-ink-900 bg-gradient-to-r from-synapse-cyan to-synapse-amber hover:brightness-110 shadow-glow transition disabled:opacity-50 disabled:saturate-50"
                    title="Replace canonical with merged body; delete the other duplicates"
                  >
                    {busy === "merge"
                      ? "merging…"
                      : `⤵ Merge ${effectiveMemberIds.length} into #${effectiveCanon ?? "?"}`}
                  </button>
                </div>
              </div>
            )}
          </section>
        </div>

        {flash && (
          <div className="absolute bottom-4 left-1/2 -translate-x-1/2 px-4 py-2 rounded-full bg-gradient-to-r from-synapse-cyan/20 to-synapse-amber/20 ring-1 ring-synapse-cyan/50 backdrop-blur text-xs font-mono text-synapse-cyan shadow-glow flex items-center gap-2 z-10">
            <span>✓</span>
            {flash}
          </div>
        )}

        <div className="px-6 py-3 border-t border-white/5 bg-ink-800/60 text-[11px] font-mono text-ink-400 flex items-center justify-between">
          <span>
            redundancy = mean pairwise cosine · merge keeps canonical id · all
            other duplicates deleted
          </span>
          <span>
            <span className="text-ink-300">esc</span> to close
          </span>
        </div>
      </div>
    </div>
  );
}

// --------------------------------------------------------------- subcomponents

function ClusterRow({
  cluster: c,
  active,
  onSelect,
}: {
  cluster: EchoCluster;
  active: boolean;
  onSelect: () => void;
}) {
  const pct = Math.round(c.redundancy * 100);
  const peakPct = Math.round(c.peak_cosine * 100);
  return (
    <button
      onClick={onSelect}
      className={`w-full text-left rounded-xl p-3 ring-1 transition ${
        active
          ? "ring-synapse-cyan/50 bg-synapse-cyan/10"
          : "ring-white/5 bg-white/[0.015] hover:ring-white/15 hover:bg-white/[0.03]"
      }`}
    >
      <div className="flex items-center justify-between gap-2 mb-1.5">
        <span
          className="inline-flex items-center gap-1 font-mono text-[10px] uppercase tracking-[0.14em] text-ink-300"
          title="number of notes in this cluster"
        >
          <span aria-hidden>⌬</span>
          {c.size} note{c.size === 1 ? "" : "s"}
        </span>
        <span
          className="font-mono text-[11px] text-synapse-amber"
          title="chars you'd save by merging"
        >
          −{c.wasted_chars}
        </span>
      </div>
      <div className="relative h-1.5 rounded-full bg-white/[0.04] overflow-hidden mb-1.5">
        <div
          className="absolute inset-y-0 left-0 rounded-full"
          style={{
            width: `${pct}%`,
            background:
              "linear-gradient(90deg, rgba(34,211,238,0.9), rgba(251,191,36,0.9))",
            boxShadow: "0 0 10px rgba(34,211,238,0.45)",
          }}
        />
      </div>
      <div className="flex items-center justify-between text-[10px] font-mono text-ink-400">
        <span>
          <span className="text-ink-100">{pct}%</span> redundant
        </span>
        <span title="strongest pair in the cluster">peak {peakPct}%</span>
      </div>
    </button>
  );
}

function ClusterHeader({
  cluster: c,
  preview,
  effectiveCount,
}: {
  cluster: EchoCluster;
  preview: EchoCluster | null;
  effectiveCount: number;
}) {
  const liveWasted = preview?.wasted_chars ?? c.wasted_chars;
  const liveOverlap = preview?.overlap_ratio ?? c.overlap_ratio;
  return (
    <div className="rounded-2xl bg-white/[0.025] ring-1 ring-white/10 p-4 flex items-center justify-between gap-4 flex-wrap">
      <div>
        <div className="text-[11px] font-mono uppercase tracking-[0.16em] text-synapse-cyan mb-1">
          active cluster
        </div>
        <div className="text-base text-ink-100 font-semibold flex items-center gap-2">
          {c.members.find((m) => m.is_canonical)?.title ??
            c.members[0]?.title ??
            "—"}
        </div>
        <div className="text-[11px] font-mono text-ink-400 mt-1">
          {effectiveCount} active · {c.size} total in cluster ·{" "}
          {Math.round(c.peak_cosine * 100)}% peak cosine
        </div>
      </div>
      <div className="flex items-center gap-3">
        <Stat
          label="recoverable"
          value={`${liveWasted} ch`}
          tone="amber"
          hint="characters saved by merging"
        />
        <Stat
          label="overlap"
          value={`${Math.round(liveOverlap * 100)}%`}
          tone="cyan"
          hint="share of sentences appearing in ≥ 2 notes"
        />
        <Stat
          label="cohesion"
          value={`${Math.round(c.redundancy * 100)}%`}
          tone="violet"
          hint="mean pairwise cosine"
        />
      </div>
    </div>
  );
}

function Stat({
  label,
  value,
  tone,
  hint,
}: {
  label: string;
  value: string;
  tone: "amber" | "cyan" | "violet";
  hint?: string;
}) {
  const cls =
    tone === "amber"
      ? "ring-synapse-amber/40 text-synapse-amber"
      : tone === "cyan"
        ? "ring-synapse-cyan/40 text-synapse-cyan"
        : "ring-synapse-violet/40 text-synapse-violet";
  return (
    <div
      className={`rounded-xl ring-1 ${cls} bg-white/[0.02] px-3 py-2 text-center`}
      title={hint}
    >
      <div className="text-[10px] font-mono uppercase tracking-[0.14em] opacity-80">
        {label}
      </div>
      <div className="text-sm font-mono mt-0.5 text-ink-100">{value}</div>
    </div>
  );
}

function MemberCard({
  member: m,
  isCanonical,
  isDropped,
  sentences,
  onMakeCanonical,
  onToggleDropped,
  onOpen,
}: {
  member: EchoMember;
  isCanonical: boolean;
  isDropped: boolean;
  sentences: EchoSentence[];
  onMakeCanonical: () => void;
  onToggleDropped: () => void;
  onOpen: () => void;
}) {
  // Sentence ledger filtered to this note: which sentences from the
  // merged ledger are sourced from this member?
  const memberSentences = useMemo(
    () => sentences.filter((s) => s.note_ids.includes(m.note_id)),
    [sentences, m.note_id],
  );
  return (
    <article
      className={`rounded-2xl ring-1 transition overflow-hidden ${
        isDropped
          ? "ring-white/5 bg-white/[0.01] opacity-50"
          : isCanonical
            ? "ring-synapse-cyan/50 bg-synapse-cyan/[0.06]"
            : "ring-white/10 bg-white/[0.02] hover:ring-white/20"
      }`}
    >
      <div className="flex items-center justify-between gap-2 px-4 py-2.5 border-b border-white/5">
        <button
          onClick={onOpen}
          className="text-left min-w-0 flex-1 group"
          title="open this note in the inspector"
        >
          <div className="flex items-center gap-2">
            <span
              className="text-[10px] font-mono uppercase tracking-[0.14em] text-ink-400"
              aria-hidden
            >
              #{m.note_id}
            </span>
            <div className="text-sm text-ink-100 font-semibold truncate group-hover:text-synapse-cyan transition">
              {m.title}
            </div>
            {isCanonical && (
              <span className="inline-flex items-center gap-1 rounded-full bg-synapse-cyan/15 ring-1 ring-synapse-cyan/40 px-2 py-0.5 font-mono text-[10px] text-synapse-cyan shrink-0">
                ★ canonical
              </span>
            )}
            {isDropped && (
              <span className="inline-flex items-center gap-1 rounded-full bg-rose-500/15 ring-1 ring-rose-400/40 px-2 py-0.5 font-mono text-[10px] text-rose-200 shrink-0">
                dropped
              </span>
            )}
          </div>
          <div className="text-[10px] font-mono text-ink-400 mt-0.5 flex items-center gap-3">
            <span>{m.body_len} ch</span>
            <span>centrality {m.centrality.toFixed(2)}</span>
            <span>{new Date(m.created_at).toISOString().slice(0, 10)}</span>
          </div>
        </button>
        <div className="flex items-center gap-1 shrink-0">
          {!isCanonical && !isDropped && (
            <button
              onClick={onMakeCanonical}
              className="inline-flex items-center gap-1 rounded-md px-2 py-1 font-mono text-[10px] text-synapse-cyan ring-1 ring-synapse-cyan/30 bg-synapse-cyan/5 hover:bg-synapse-cyan/15 transition"
              title="merge into this note instead of the auto-pick"
            >
              ★ canonical
            </button>
          )}
          <button
            onClick={onToggleDropped}
            className={`inline-flex items-center gap-1 rounded-md px-2 py-1 font-mono text-[10px] ring-1 transition ${
              isDropped
                ? "text-synapse-lime ring-synapse-lime/30 bg-synapse-lime/5 hover:bg-synapse-lime/15"
                : "text-ink-300 ring-white/10 hover:ring-rose-400/40 hover:text-rose-200"
            }`}
            title={isDropped ? "include in merge" : "exclude from merge"}
          >
            {isDropped ? "+ keep" : "− exclude"}
          </button>
        </div>
      </div>
      <div className="p-4 max-h-56 overflow-y-auto">
        <p className="text-xs leading-relaxed text-ink-200 whitespace-pre-wrap">
          {highlightDuplicates(m.body, memberSentences)}
        </p>
        {m.tags.length > 0 && (
          <div className="flex flex-wrap gap-1 mt-3">
            {m.tags.map((t) => (
              <span
                key={t}
                className="inline-flex rounded-full bg-white/[0.04] ring-1 ring-white/10 px-2 py-0.5 font-mono text-[10px] text-ink-300"
              >
                #{t}
              </span>
            ))}
          </div>
        )}
      </div>
    </article>
  );
}

/**
 * Paint duplicated sentences in cyan within a note's body. We do a
 * cheap substring search per duplicate sentence — accurate enough for
 * the inline highlight, and matches the user's visual mental model of
 * "this phrase already exists in another note".
 */
function highlightDuplicates(body: string, sentences: EchoSentence[]) {
  const dups = sentences
    .filter((s) => s.is_duplicate)
    .map((s) => s.text.trim())
    .filter((s) => s.length > 8)
    .sort((a, b) => b.length - a.length);
  if (dups.length === 0) return body;
  const nodes: React.ReactNode[] = [];
  let cursor = 0;
  // Find earliest occurrences of any duplicate string and chunk.
  while (cursor < body.length) {
    let nextStart = -1;
    let nextLen = 0;
    let nextText = "";
    for (const s of dups) {
      const i = body.toLowerCase().indexOf(s.toLowerCase(), cursor);
      if (i === -1) continue;
      if (nextStart === -1 || i < nextStart) {
        nextStart = i;
        nextLen = s.length;
        nextText = body.slice(i, i + s.length);
      }
    }
    if (nextStart === -1) {
      nodes.push(body.slice(cursor));
      break;
    }
    if (nextStart > cursor) nodes.push(body.slice(cursor, nextStart));
    nodes.push(
      <mark
        key={`m-${nextStart}`}
        className="bg-synapse-cyan/15 ring-1 ring-synapse-cyan/30 rounded px-0.5 text-synapse-cyan"
      >
        {nextText}
      </mark>,
    );
    cursor = nextStart + nextLen;
  }
  return nodes;
}

function PairLadder({ cluster: c }: { cluster: EchoCluster }) {
  if (c.pairs.length === 0) return null;
  return (
    <div className="rounded-xl bg-ink-900/40 ring-1 ring-white/5 p-3">
      <div className="text-[10px] font-mono uppercase tracking-[0.16em] text-ink-400 mb-2">
        pairwise cosine
      </div>
      <div className="grid gap-1.5">
        {c.pairs.map((p) => {
          const pct = Math.round(p.cosine * 100);
          return (
            <div
              key={`${p.a_id}-${p.b_id}`}
              className="grid grid-cols-[3rem_1fr_3rem] items-center gap-2 text-[11px] font-mono"
            >
              <span className="text-ink-300 text-right">#{p.a_id}</span>
              <div className="relative h-1.5 rounded-full bg-white/[0.04] overflow-hidden">
                <div
                  className="absolute inset-y-0 left-0 rounded-full"
                  style={{
                    width: `${pct}%`,
                    background:
                      "linear-gradient(90deg, rgba(34,211,238,0.85), rgba(251,191,36,0.85))",
                  }}
                />
              </div>
              <span className="text-ink-300">
                #{p.b_id} <span className="text-ink-100">{pct}%</span>
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function MergePreview({
  cluster: c,
  preview,
  busy,
  titleOverride,
  bodyOverride,
  onTitleChange,
  onBodyChange,
  effectiveCanon,
  effectiveCount,
}: {
  cluster: EchoCluster;
  preview: EchoCluster | null;
  busy: boolean;
  titleOverride: string | null;
  bodyOverride: string | null;
  onTitleChange: (v: string | null) => void;
  onBodyChange: (v: string | null) => void;
  effectiveCanon: number | null;
  effectiveCount: number;
}) {
  const live = preview ?? c;
  const titleValue = titleOverride ?? live.merged_title;
  const bodyValue = bodyOverride ?? live.merged_body;
  const tooFew = effectiveCount < 2;
  return (
    <div className="rounded-2xl ring-1 ring-synapse-cyan/30 bg-gradient-to-br from-synapse-cyan/[0.05] to-synapse-amber/[0.04] p-4">
      <div className="flex items-center justify-between mb-3">
        <div>
          <div className="text-[11px] font-mono uppercase tracking-[0.16em] text-synapse-cyan">
            merge preview {busy && <span className="text-ink-400">· recomputing…</span>}
          </div>
          <div className="text-[10px] font-mono text-ink-400 mt-0.5">
            replaces canonical #{effectiveCanon ?? "?"} in place ·{" "}
            {Math.max(effectiveCount - 1, 0)} note
            {effectiveCount - 1 === 1 ? "" : "s"} will be deleted
          </div>
        </div>
        <div className="text-[10px] font-mono text-ink-400 text-right">
          <div>
            <span className="text-synapse-amber">{live.chars_total}</span>
            <span className="text-ink-500"> → </span>
            <span className="text-synapse-cyan">{live.chars_unique}</span> ch
          </div>
          <div>{live.merged_tags.length} merged tag{live.merged_tags.length === 1 ? "" : "s"}</div>
        </div>
      </div>
      {tooFew ? (
        <div className="text-xs text-ink-400 italic">
          Drop fewer members or pick at least two to preview a merge.
        </div>
      ) : (
        <>
          <label className="block mb-3">
            <span className="text-[10px] font-mono uppercase tracking-[0.14em] text-ink-300 mb-1 block">
              merged title
            </span>
            <input
              value={titleValue}
              onChange={(e) =>
                onTitleChange(
                  e.target.value === live.merged_title ? null : e.target.value,
                )
              }
              className="w-full rounded-lg bg-ink-900/60 ring-1 ring-white/10 focus:ring-synapse-cyan/50 px-3 py-2 text-sm text-ink-100 focus:outline-none"
              maxLength={140}
            />
          </label>
          <label className="block mb-3">
            <span className="text-[10px] font-mono uppercase tracking-[0.14em] text-ink-300 mb-1 block">
              merged body — duplicates collapsed, unique sentences kept
            </span>
            <textarea
              value={bodyValue}
              onChange={(e) =>
                onBodyChange(
                  e.target.value === live.merged_body ? null : e.target.value,
                )
              }
              rows={8}
              className="w-full rounded-lg bg-ink-900/60 ring-1 ring-white/10 focus:ring-synapse-cyan/50 px-3 py-2 text-sm text-ink-100 focus:outline-none font-sans leading-relaxed resize-y"
              maxLength={12000}
            />
          </label>
          {live.merged_tags.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {live.merged_tags.map((t) => (
                <span
                  key={t}
                  className="inline-flex rounded-full bg-synapse-cyan/10 ring-1 ring-synapse-cyan/30 px-2 py-0.5 font-mono text-[10px] text-synapse-cyan"
                >
                  #{t}
                </span>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}

function ClusterRailSkeleton() {
  return (
    <div className="p-2 space-y-1">
      {[0, 1, 2, 3].map((i) => (
        <div
          key={i}
          className="rounded-xl bg-white/[0.02] ring-1 ring-white/5 h-20 relative overflow-hidden"
        >
          <div
            className="absolute inset-y-0 w-1/3 bg-gradient-to-r from-transparent via-white/[0.05] to-transparent"
            style={{
              animation: "ws-shimmer 1.6s ease-in-out infinite",
              animationDelay: `${i * 0.15}s`,
            }}
          />
        </div>
      ))}
    </div>
  );
}

function ClusterRailEmpty() {
  return (
    <div className="p-6 text-center">
      <div className="inline-flex items-center justify-center w-12 h-12 rounded-full bg-gradient-to-br from-synapse-cyan/20 to-synapse-amber/20 ring-1 ring-synapse-cyan/40 mb-3">
        <span className="text-2xl text-synapse-cyan">∅</span>
      </div>
      <div className="text-base text-ink-100 font-semibold mb-1">
        No echoes
      </div>
      <p className="text-xs text-ink-300 leading-relaxed">
        Your notes are well-differentiated at this threshold. Lower τ to
        find weaker matches, or add more notes and come back.
      </p>
    </div>
  );
}

function EchoGlyph() {
  return (
    <div className="relative w-9 h-9 shrink-0">
      <svg viewBox="0 0 40 40" className="w-full h-full">
        <defs>
          <linearGradient id="eg" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="#22d3ee" />
            <stop offset="100%" stopColor="#fbbf24" />
          </linearGradient>
        </defs>
        <circle cx="20" cy="20" r="4" fill="url(#eg)" />
        <circle
          cx="20"
          cy="20"
          r="9"
          fill="none"
          stroke="#22d3ee"
          strokeOpacity="0.7"
          strokeWidth="1.2"
        />
        <circle
          cx="20"
          cy="20"
          r="14"
          fill="none"
          stroke="#fbbf24"
          strokeOpacity="0.45"
          strokeWidth="0.9"
        />
        <circle
          cx="20"
          cy="20"
          r="18.5"
          fill="none"
          stroke="#fbbf24"
          strokeOpacity="0.22"
          strokeWidth="0.7"
        />
      </svg>
      <div className="absolute inset-0 rounded-full shadow-glow pointer-events-none" />
    </div>
  );
}
