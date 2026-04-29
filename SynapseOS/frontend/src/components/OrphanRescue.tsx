"use client";

import type { GraphNode, OrphanSuggestion } from "@/lib/types";

type Props = {
  orphans: OrphanSuggestion[];
  nodes: GraphNode[];
  // When the user clicks "show in graph" we surface both the orphan
  // and its suggested neighbor in the inspector chain.
  onSelect: (node: GraphNode) => void;
};

/**
 * Notes that fell below the current synapse threshold and have no
 * incoming or outgoing edges. For each, we show the strongest peer
 * they almost-but-not-quite linked to, along with the τ value that
 * would make the link fire.
 *
 * Hidden when the graph is fully connected — the empty state would
 * just be visual noise.
 */
export function OrphanRescue({ orphans, nodes, onSelect }: Props) {
  if (orphans.length === 0) return null;
  const byId = new Map(nodes.map((n) => [n.id, n]));
  return (
    <div className="rounded-xl bg-ink-800/60 ring-1 ring-white/5 shadow-card p-4 animate-fade-in">
      <div className="flex items-center justify-between mb-2">
        <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-ink-200">
          orphan rescue
        </div>
        <span className="text-[10px] font-mono text-ink-400">
          {orphans.length} {orphans.length === 1 ? "note" : "notes"}
        </span>
      </div>
      <p className="text-[11px] text-ink-400 leading-snug mb-3">
        These notes have no synapses at the current threshold. Drop ``τ`` to
        the suggested value — or refine the note text — to attach them.
      </p>
      <ul className="space-y-2">
        {orphans.slice(0, 6).map((o) => {
          const orphanNode = byId.get(o.note_id);
          const candidate = o.suggested_id != null ? byId.get(o.suggested_id) : null;
          return (
            <li
              key={o.note_id}
              className="rounded-lg ring-1 ring-white/5 bg-white/[0.015] p-2.5"
            >
              <div className="flex items-center justify-between gap-2">
                <button
                  onClick={() => orphanNode && onSelect(orphanNode)}
                  className="flex-1 text-left text-sm text-ink-100 truncate hover:text-synapse-amber transition"
                  title={o.title}
                >
                  {o.title}
                </button>
                <span className="text-[10px] font-mono text-ink-400 shrink-0">
                  τ→{o.suggested_threshold.toFixed(2)}
                </span>
              </div>
              {o.suggested_title ? (
                <div className="mt-1 flex items-center gap-2 text-[11px]">
                  <span className="text-ink-400">would attach to</span>
                  <button
                    onClick={() => candidate && onSelect(candidate)}
                    className="font-medium text-ink-200 truncate hover:text-synapse-cyan transition"
                    title={o.suggested_title}
                  >
                    {o.suggested_title}
                  </button>
                  <span className="ml-auto font-mono text-synapse-cyan/90 shrink-0">
                    {(o.suggested_strength * 100).toFixed(0)}%
                  </span>
                </div>
              ) : (
                <div className="mt-1 text-[11px] text-ink-400">
                  no candidates yet — add a related note.
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
