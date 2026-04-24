"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { GraphNode, Neighbor } from "@/lib/types";

type Props = {
  selected: GraphNode | null;
  onSelect: (node: GraphNode) => void;
  onDelete: (id: number) => Promise<void>;
};

export function Inspector({ selected, onSelect, onDelete }: Props) {
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
        <button
          onClick={() => onDelete(selected.id)}
          title="delete note"
          className="text-xs text-ink-400 hover:text-synapse-pink transition px-2 py-1 rounded ring-1 ring-white/5"
        >
          delete
        </button>
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
