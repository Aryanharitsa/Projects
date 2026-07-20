"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { GraphNode, Neighbor } from "@/lib/types";

type Props = {
  selected: GraphNode | null;
  onSelect: (node: GraphNode) => void;
  onDelete: (id: number) => Promise<void>;
  /** Trail UX hooks — only shown when the player is open. When no
   *  trail is yet saved (`canAppend === false` but `canStart === true`),
   *  we expose "start trail here" instead so the user can seed a
   *  fresh draft from the inspected note. */
  trailCanAppend?: boolean;
  trailCanStart?: boolean;
  onAddToTrail?: (id: number) => void;
  onStartTrailHere?: (id: number) => void;
  /** Opens the Prism modal pre-targeted at this note. */
  onInterrogateInPrism?: (id: number) => void;
};

export function Inspector({
  selected,
  onSelect,
  onDelete,
  trailCanAppend,
  trailCanStart,
  onAddToTrail,
  onStartTrailHere,
  onInterrogateInPrism,
}: Props) {
  const [neighbors, setNeighbors] = useState<Neighbor[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!selected) return;
    let cancelled = false;
    setLoading(true);
    api
      .neighbors(selected.id)
      .then((n) => {
        if (!cancelled) setNeighbors(n);
      })
      .catch(() => {
        if (!cancelled) setNeighbors([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selected?.id]);

  if (!selected) {
    return (
      <div className="rounded-xl bg-ink-800/60 ring-1 ring-white/5 shadow-card p-5 text-sm text-ink-300">
        <div className="text-xs font-semibold uppercase tracking-[0.16em] text-ink-200 mb-2">
          inspector
        </div>
        <p className="leading-relaxed text-ink-300">
          Click any node in the graph, or a result in search. You&apos;ll see
          the full note and its strongest synapses here.
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-xl bg-ink-800/60 ring-1 ring-white/5 shadow-card p-5 animate-fade-in">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-ink-100 leading-tight">
            {selected.title}
          </h2>
          <div className="mt-1 flex flex-wrap gap-1.5">
            {selected.tags.map((t) => (
              <span
                key={t}
                className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-synapse-violet/10 text-synapse-violet ring-1 ring-synapse-violet/20"
              >
                #{t}
              </span>
            ))}
          </div>
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          {onInterrogateInPrism && (
            <button
              onClick={() => onInterrogateInPrism(selected.id)}
              title="interrogate this note through 8 perspective lenses"
              className="text-[10px] font-mono uppercase tracking-[0.12em] rounded-full px-2.5 py-1 ring-1 ring-rose-400/45 text-rose-200 hover:text-ink-100 hover:ring-rose-400/80 bg-gradient-to-r from-rose-500/10 via-violet-500/10 to-cyan-500/10 transition"
            >
              🔷 prism
            </button>
          )}
          {trailCanAppend && onAddToTrail && (
            <button
              onClick={() => onAddToTrail(selected.id)}
              title="append this note to the active trail"
              className="text-[10px] font-mono uppercase tracking-[0.12em] rounded-full px-2.5 py-1 ring-1 ring-synapse-amber/40 text-synapse-amber hover:ring-synapse-amber hover:text-ink-100 transition"
            >
              + trail
            </button>
          )}
          {!trailCanAppend && trailCanStart && onStartTrailHere && (
            <button
              onClick={() => onStartTrailHere(selected.id)}
              title="start a new trail from this note"
              className="text-[10px] font-mono uppercase tracking-[0.12em] rounded-full px-2.5 py-1 ring-1 ring-synapse-amber/30 text-synapse-amber/90 hover:ring-synapse-amber hover:text-ink-100 transition"
            >
              ◇ trail
            </button>
          )}
          <button
            onClick={() => onDelete(selected.id)}
            title="delete note"
            className="text-xs text-ink-400 hover:text-synapse-pink transition px-2 py-1 rounded ring-1 ring-white/5"
          >
            delete
          </button>
        </div>
      </div>

      <p className="mt-4 text-sm text-ink-100/90 leading-relaxed whitespace-pre-wrap">
        {selected.body}
      </p>

      <div className="mt-4 flex gap-3 text-[11px] text-ink-300 font-mono">
        <span>deg {selected.degree}</span>
        <span>·</span>
        <span>weight {(selected.weight * 100).toFixed(0)}%</span>
      </div>

      <div className="hairline my-5" />

      <div className="text-xs font-semibold uppercase tracking-[0.16em] text-ink-200 mb-2 flex items-center justify-between">
        <span>strongest synapses</span>
        {loading && <span className="text-ink-400 font-normal normal-case">loading…</span>}
      </div>

      {neighbors.length === 0 && !loading ? (
        <p className="text-xs text-ink-400">
          No connections yet. Add more notes on related topics — synapses form
          automatically.
        </p>
      ) : (
        <ul className="space-y-1.5">
          {neighbors.map((n) => (
            <li key={n.node.id}>
              <button
                onClick={() => onSelect(n.node)}
                className="w-full text-left flex items-center gap-2 rounded-lg px-2 py-1.5 hover:bg-white/[0.03] transition"
              >
                <StrengthBar strength={n.strength} />
                <span className="flex-1 text-sm text-ink-100 truncate">
                  {n.node.title}
                </span>
                <span className="text-[10px] font-mono text-ink-300">
                  {(n.strength * 100).toFixed(0)}%
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function StrengthBar({ strength }: { strength: number }) {
  const pct = Math.max(0.08, Math.min(1, strength));
  return (
    <span
      className="w-1.5 rounded-full bg-gradient-to-t from-synapse-cyan to-synapse-violet"
      style={{ height: `${pct * 18 + 6}px` }}
    />
  );
}
