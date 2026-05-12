"use client";

import { useMemo, useState } from "react";
import type { NetEdge, NetEntity } from "../lib/api";

const BAND_FILL: Record<NetEntity["band"], string> = {
  low: "#22d3a8",
  medium: "#fbbf24",
  high: "#fb923c",
  critical: "#ef4444",
};

/** Risk-coloured force-directed graph.
 *
 * Layout is pre-computed server-side (deterministic FR variant) — we just
 * project the virtual canvas coordinates onto whatever SVG box the parent
 * gives us. Nodes are sized by network_risk, hue-coded by band; aggregate
 * (multi-member) clusters get a thicker ring; sanctioned ones get a halo;
 * the selected node gets a teal aura. Edges are width-coded by aggregate
 * amount and use an arrow-headed curved path so two-way flows don't
 * overlap.
 */
export default function RiskGraph({
  entities,
  edges,
  selectedId,
  ablatedIds,
  onSelect,
  width = 760,
  height = 540,
  virtualSize = 1000,
}: {
  entities: NetEntity[];
  edges: NetEdge[];
  selectedId?: string | null;
  ablatedIds?: Set<string>;
  onSelect?: (id: string | null) => void;
  width?: number;
  height?: number;
  virtualSize?: number;
}) {
  const byId = useMemo(() => {
    const out: Record<string, NetEntity> = {};
    for (const e of entities) out[e.id] = e;
    return out;
  }, [entities]);

  const maxAmt = useMemo(
    () => Math.max(1, ...edges.map((e) => e.amount)),
    [edges],
  );

  const [hoverId, setHoverId] = useState<string | null>(null);

  const proj = (x: number, y: number) => ({
    x: (x / virtualSize) * width,
    y: (y / virtualSize) * height,
  });

  // Highlight set = direct neighbours of selected or hovered node.
  const focusId = hoverId || selectedId || null;
  const focusNeighbours = useMemo(() => {
    if (!focusId) return new Set<string>();
    const n = new Set<string>([focusId]);
    for (const e of edges) {
      if (e.src === focusId) n.add(e.dst);
      if (e.dst === focusId) n.add(e.src);
    }
    return n;
  }, [edges, focusId]);

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      className="w-full select-none rounded-2xl border border-white/10 bg-[radial-gradient(ellipse_at_top,_rgba(110,91,255,0.12),_transparent_55%),radial-gradient(ellipse_at_bottom,_rgba(45,225,194,0.08),_transparent_60%),rgba(7,11,20,0.6)]"
      role="img"
      aria-label="Entity risk network"
      onClick={() => onSelect?.(null)}
    >
      <defs>
        <linearGradient id="rg-edge" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#2DE1C2" stopOpacity="0.85" />
          <stop offset="1" stopColor="#6E5BFF" stopOpacity="0.85" />
        </linearGradient>
        <linearGradient id="rg-edge-faded" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#ffffff" stopOpacity="0.16" />
          <stop offset="1" stopColor="#ffffff" stopOpacity="0.06" />
        </linearGradient>
        <marker
          id="rg-arrow"
          viewBox="0 0 10 10"
          refX="9"
          refY="5"
          markerWidth="5"
          markerHeight="5"
          orient="auto-start-reverse"
        >
          <path d="M0,0 L10,5 L0,10 z" fill="#8B7CFF" />
        </marker>
        <marker
          id="rg-arrow-faded"
          viewBox="0 0 10 10"
          refX="9"
          refY="5"
          markerWidth="5"
          markerHeight="5"
          orient="auto-start-reverse"
        >
          <path d="M0,0 L10,5 L0,10 z" fill="rgba(255,255,255,0.22)" />
        </marker>
        <radialGradient id="rg-sanction-halo">
          <stop offset="0" stopColor="rgba(239,68,68,0.0)" />
          <stop offset="0.6" stopColor="rgba(239,68,68,0.35)" />
          <stop offset="1" stopColor="rgba(239,68,68,0)" />
        </radialGradient>
      </defs>

      {/* Edges first so they sit behind nodes */}
      {edges.map((e, i) => {
        const s = byId[e.src];
        const d = byId[e.dst];
        if (!s || !d) return null;
        const a = proj(s.x, s.y);
        const b = proj(d.x, d.y);
        const w = 0.7 + (e.amount / maxAmt) * 3.6;
        const onFocus = focusId
          ? e.src === focusId || e.dst === focusId
          : false;
        const ablated =
          ablatedIds?.has(e.src) || ablatedIds?.has(e.dst) || false;
        const dx = b.x - a.x;
        const dy = b.y - a.y;
        const norm = Math.sqrt(dx * dx + dy * dy) || 1;
        const offset = 14 + (i % 3) * 4;
        const mx = (a.x + b.x) / 2 + (-dy / norm) * offset;
        const my = (a.y + b.y) / 2 + (dx / norm) * offset;
        const path = `M ${a.x} ${a.y} Q ${mx} ${my} ${b.x} ${b.y}`;
        return (
          <g key={i} opacity={ablated ? 0.18 : onFocus ? 1 : focusId ? 0.22 : 0.7}>
            <path
              d={path}
              stroke={onFocus ? "url(#rg-edge)" : "url(#rg-edge-faded)"}
              strokeWidth={onFocus ? w + 0.6 : w}
              strokeDasharray={ablated ? "4 4" : undefined}
              fill="none"
              markerEnd={onFocus ? "url(#rg-arrow)" : "url(#rg-arrow-faded)"}
            />
            {onFocus && (
              <text
                x={mx}
                y={my - 4}
                textAnchor="middle"
                style={{ fontSize: 10, fontFamily: "JetBrains Mono, monospace" }}
                className="fill-white/60"
              >
                ₹{Math.round(e.amount).toLocaleString("en-IN")}
              </text>
            )}
          </g>
        );
      })}

      {/* Nodes */}
      {entities.map((n) => {
        const p = proj(n.x, n.y);
        const r = 8 + (n.network_risk / 100) * 18;
        const fill = BAND_FILL[n.band];
        const ablated = ablatedIds?.has(n.id) || false;
        const isFocus = n.id === focusId;
        const isNeighbour = focusId ? focusNeighbours.has(n.id) : true;
        const dim = focusId && !isNeighbour;
        return (
          <g
            key={n.id}
            transform={`translate(${p.x} ${p.y})`}
            opacity={ablated ? 0.32 : dim ? 0.28 : 1}
            style={{ cursor: "pointer", transition: "opacity 0.15s" }}
            onClick={(ev) => {
              ev.stopPropagation();
              onSelect?.(n.id === selectedId ? null : n.id);
            }}
            onMouseEnter={() => setHoverId(n.id)}
            onMouseLeave={() => setHoverId((cur) => (cur === n.id ? null : cur))}
          >
            {n.sanctioned && (
              <circle r={r + 8} fill="url(#rg-sanction-halo)" />
            )}
            {isFocus && (
              <circle
                r={r + 6}
                fill="none"
                stroke="rgba(45,225,194,0.55)"
                strokeWidth={1.5}
              />
            )}
            <circle
              r={r}
              fill={`${fill}33`}
              stroke={fill}
              strokeWidth={n.is_aggregate ? 2.2 : 1.4}
              strokeDasharray={ablated ? "3 3" : undefined}
            />
            <text
              y={4}
              textAnchor="middle"
              style={{ fontSize: 10, fontFamily: "Inter, sans-serif", fontWeight: 600 }}
              className="fill-white/95"
            >
              {Math.round(n.network_risk)}
            </text>
            <text
              y={r + 14}
              textAnchor="middle"
              style={{ fontSize: 11, fontFamily: "Inter, sans-serif" }}
              className="fill-white/80"
            >
              {n.display_name.length > 18
                ? `${n.display_name.slice(0, 16)}…`
                : n.display_name}
            </text>
            {n.is_aggregate && (
              <text
                y={r + 25}
                textAnchor="middle"
                style={{ fontSize: 9, fontFamily: "JetBrains Mono, monospace" }}
                className="fill-violet-300/90"
              >
                ×{n.member_count}
              </text>
            )}
          </g>
        );
      })}

      {/* Legend */}
      <g transform={`translate(${width - 188} ${height - 70})`}>
        <rect
          width={172}
          height={56}
          rx={10}
          fill="rgba(7,11,20,0.6)"
          stroke="rgba(255,255,255,0.08)"
        />
        {(["low", "medium", "high", "critical"] as const).map((b, i) => (
          <g key={b} transform={`translate(${10 + (i % 2) * 80} ${14 + Math.floor(i / 2) * 22})`}>
            <circle cx={4} cy={0} r={4.5} fill={BAND_FILL[b]} />
            <text
              x={12}
              y={3}
              style={{ fontSize: 10, fontFamily: "Inter, sans-serif" }}
              className="fill-white/65"
            >
              {b}
            </text>
          </g>
        ))}
      </g>
    </svg>
  );
}
