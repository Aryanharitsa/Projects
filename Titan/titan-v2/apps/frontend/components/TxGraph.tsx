"use client";
import { useMemo } from "react";

type Edge = { from: string; to: string; amount: number };

/** Compact transaction graph rendered with a deterministic circular layout
 *  so the same data always lays out the same way. No heavy d3-force dep —
 *  this is intentionally tiny and predictable.
 */
export default function TxGraph({
  edges,
  highlight,
  width = 560,
  height = 320,
}: {
  edges: Edge[];
  highlight?: string;
  width?: number;
  height?: number;
}) {
  const { nodes, layout } = useMemo(() => {
    const ids = Array.from(
      new Set(edges.flatMap((e) => [e.from, e.to])),
    ).sort();
    const cx = width / 2;
    const cy = height / 2;
    const r = Math.min(width, height) / 2 - 36;
    const pos: Record<string, { x: number; y: number }> = {};
    ids.forEach((id, i) => {
      const t = (i / Math.max(ids.length, 1)) * Math.PI * 2 - Math.PI / 2;
      pos[id] = { x: cx + Math.cos(t) * r, y: cy + Math.sin(t) * r };
    });
    return { nodes: ids, layout: pos };
  }, [edges, width, height]);

  const maxAmt = Math.max(1, ...edges.map((e) => e.amount));

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      className="w-full rounded-xl border border-white/10 bg-black/30"
      role="img"
      aria-label="Transaction graph"
    >
      <defs>
        <linearGradient id="edgeG" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#2DE1C2" stopOpacity="0.85" />
          <stop offset="1" stopColor="#6E5BFF" stopOpacity="0.85" />
        </linearGradient>
        <marker
          id="arrow"
          viewBox="0 0 10 10"
          refX="9"
          refY="5"
          markerWidth="5"
          markerHeight="5"
          orient="auto-start-reverse"
        >
          <path d="M0,0 L10,5 L0,10 z" fill="#8B7CFF" />
        </marker>
      </defs>

      {edges.map((e, i) => {
        const a = layout[e.from];
        const b = layout[e.to];
        if (!a || !b) return null;
        const w = 0.6 + (e.amount / maxAmt) * 3.2;
        const focus = highlight && (e.from === highlight || e.to === highlight);
        // Curve so two-way edges don't overlap: offset by a perpendicular delta
        const dx = b.x - a.x;
        const dy = b.y - a.y;
        const mx = (a.x + b.x) / 2;
        const my = (a.y + b.y) / 2;
        const norm = Math.sqrt(dx * dx + dy * dy) || 1;
        const offset = 18 + (i % 3) * 4;
        const px = (-dy / norm) * offset;
        const py = (dx / norm) * offset;
        const cx = mx + px;
        const cy = my + py;
        const path = `M ${a.x} ${a.y} Q ${cx} ${cy} ${b.x} ${b.y}`;
        return (
          <g key={i} opacity={focus ? 1 : 0.7}>
            <path
              d={path}
              stroke={focus ? "url(#edgeG)" : "rgba(255,255,255,0.18)"}
              strokeWidth={w}
              fill="none"
              markerEnd="url(#arrow)"
            />
          </g>
        );
      })}

      {nodes.map((id) => {
        const p = layout[id];
        const focus = id === highlight;
        return (
          <g key={id} transform={`translate(${p.x} ${p.y})`}>
            <circle
              r={focus ? 18 : 13}
              fill={focus ? "rgba(45,225,194,0.9)" : "rgba(255,255,255,0.06)"}
              stroke={focus ? "rgba(45,225,194,0.4)" : "rgba(255,255,255,0.22)"}
              strokeWidth={focus ? 3 : 1.5}
            />
            <text
              y={focus ? -26 : -20}
              textAnchor="middle"
              className="fill-white/85"
              style={{ fontSize: 11, fontFamily: "JetBrains Mono, monospace" }}
            >
              {id}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
