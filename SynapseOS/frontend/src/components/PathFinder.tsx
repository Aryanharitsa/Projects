"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import type { GraphNode, PathResult } from "@/lib/types";

type Props = {
  nodes: GraphNode[];
  onHighlight: (edgeKeys: Set<string> | null, nodes: GraphNode[]) => void;
};

const keyOf = (a: number, b: number) => (a < b ? `${a}-${b}` : `${b}-${a}`);

export function PathFinder({ nodes, onHighlight }: Props) {
  const [src, setSrc] = useState<number | "">("");
  const [dst, setDst] = useState<number | "">("");
  const [result, setResult] = useState<PathResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function findPath() {
    if (typeof src !== "number" || typeof dst !== "number" || src === dst) return;
    setBusy(true);
    setErr(null);
    try {
      const res = await api.path(src, dst);
      setResult(res);
      if (res.found) {
        const keys = new Set<string>();
        const ids = res.path.map((s) => s.node.id);
        for (let i = 0; i < ids.length - 1; i++) keys.add(keyOf(ids[i], ids[i + 1]));
        onHighlight(keys, res.path.map((p) => p.node));
      } else {
        onHighlight(null, []);
      }
    } catch (e) {
      setErr(e instanceof Error ? e.message : "failed");
    } finally {
      setBusy(false);
    }
  }

  function clear() {
    setResult(null);
    onHighlight(null, []);
  }

  return (
    <div className="rounded-xl bg-ink-800/60 ring-1 ring-white/5 shadow-card p-4 space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-semibold uppercase tracking-[0.16em] text-ink-200">
          trace a thought path
        </h3>
        {result && (
          <button
            onClick={clear}
            className="text-[10px] text-ink-300 hover:text-ink-100 font-mono"
          >
            clear
          </button>
        )}
      </div>
      <div className="grid grid-cols-2 gap-2">
        <NodeSelect value={src} nodes={nodes} onChange={setSrc} placeholder="from…" />
        <NodeSelect value={dst} nodes={nodes} onChange={setDst} placeholder="to…" />
      </div>
      <button
        onClick={findPath}
        disabled={busy || src === "" || dst === "" || src === dst}
        className="w-full rounded-lg px-3 py-2 text-sm font-medium text-ink-900 bg-gradient-to-r from-synapse-amber to-synapse-pink disabled:opacity-40 hover:brightness-110 transition"
      >
        {busy ? "tracing…" : "trace path"}
      </button>
      {err && <p className="text-xs text-synapse-pink">{err}</p>}
      {result && !result.found && (
        <p className="text-xs text-ink-300">
          No path — these thoughts aren&apos;t connected (yet).
        </p>
      )}
      {result && result.found && (
        <div className="mt-2 space-y-1.5 animate-fade-in">
          <div className="text-[10px] font-mono text-ink-300">
            cost {result.cost.toFixed(3)} · {result.path.length - 1} hop
            {result.path.length - 1 === 1 ? "" : "s"}
          </div>
          <ol className="space-y-1">
            {result.path.map((step, i) => (
              <li
                key={`${step.node.id}-${i}`}
                className="flex items-center gap-2 text-sm"
              >
                <span className="w-5 h-5 flex items-center justify-center rounded-full bg-synapse-amber/15 text-synapse-amber text-[10px] font-mono">
                  {i + 1}
                </span>
                <span className="flex-1 text-ink-100 truncate">{step.node.title}</span>
                {i > 0 && (
                  <span className="text-[10px] font-mono text-ink-300">
                    {(step.strength * 100).toFixed(0)}%
                  </span>
                )}
              </li>
            ))}
          </ol>
        </div>
      )}
    </div>
  );
}

function NodeSelect({
  value,
  nodes,
  onChange,
  placeholder,
}: {
  value: number | "";
  nodes: GraphNode[];
  onChange: (v: number | "") => void;
  placeholder: string;
}) {
  return (
    <select
      value={value === "" ? "" : String(value)}
      onChange={(e) => onChange(e.target.value === "" ? "" : Number(e.target.value))}
      className="rounded-lg bg-ink-900/60 ring-1 ring-white/5 px-2 py-1.5 text-xs text-ink-100 focus-ring"
    >
      <option value="">{placeholder}</option>
      {nodes.map((n) => (
        <option key={n.id} value={n.id}>
          {n.title}
        </option>
      ))}
    </select>
  );
}
