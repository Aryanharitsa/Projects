"use client";

import dynamic from "next/dynamic";
import { useEffect, useMemo, useRef } from "react";
import type { Graph as GraphT, GraphNode } from "@/lib/types";

// react-force-graph-2d uses a canvas + DOM refs that can't SSR.
const ForceGraph2D = dynamic(() => import("react-force-graph-2d"), { ssr: false });

type Props = {
  data: GraphT | null;
  selectedId: number | null;
  highlightPath: Set<string> | null; // edge keys "u-v" with u<v
  // When non-null, nodes outside this community are dimmed and edges
  // crossing the boundary are faded. The graph still renders everything,
  // it just lets the user mentally "lift" one cluster out of the rest.
  isolatedCommunity: number | null;
  onSelect: (node: GraphNode) => void;
};

type FGNode = GraphNode & { x?: number; y?: number };
type FGLink = { source: number | FGNode; target: number | FGNode; strength: number };

const edgeKey = (a: number, b: number) => (a < b ? `${a}-${b}` : `${b}-${a}`);

// The default node fill when the backend hasn't provided a community
// color (e.g. an empty graph).
const DEFAULT_FILL = "#7c6cf0";

export function Graph({
  data,
  selectedId,
  highlightPath,
  isolatedCommunity,
  onSelect,
}: Props) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const graphRef = useRef<any>(null);

  const fgData = useMemo(() => {
    if (!data) return { nodes: [] as FGNode[], links: [] as FGLink[] };
    return {
      nodes: data.nodes.map((n) => ({ ...n })) as FGNode[],
      links: data.edges.map((e) => ({
        source: e.source,
        target: e.target,
        strength: e.strength,
      })) as FGLink[],
    };
  }, [data]);

  // Quick lookup so the link-painter can ask "are both endpoints in the
  // isolated community?" without scanning the node list every frame.
  const communityById = useMemo(() => {
    const m = new Map<number, number | null | undefined>();
    for (const n of fgData.nodes) m.set(n.id, n.community ?? null);
    return m;
  }, [fgData.nodes]);

  // Cold-start zoom to fit once nodes are laid out
  useEffect(() => {
    if (!graphRef.current || fgData.nodes.length === 0) return;
    const t = setTimeout(() => {
      try {
        graphRef.current.zoomToFit(600, 80);
      } catch {
        /* no-op */
      }
    }, 400);
    return () => clearTimeout(t);
  }, [fgData.nodes.length]);

  return (
    <div
      ref={wrapRef}
      className="relative w-full h-full rounded-xl bg-ink-900/60 ring-1 ring-white/5 shadow-card overflow-hidden"
    >
      <div className="absolute top-3 left-4 z-10 text-[11px] font-mono text-ink-300 tracking-widest uppercase pointer-events-none">
        knowledge graph
      </div>
      <div className="absolute top-3 right-4 z-10 text-[10px] font-mono text-ink-400 tracking-widest uppercase pointer-events-none">
        drag · zoom · click a node
      </div>
      {data && data.nodes.length === 0 ? (
        <div className="absolute inset-0 flex items-center justify-center text-sm text-ink-300">
          no notes yet — commit your first thought on the left.
        </div>
      ) : (
        <ForceGraph2D
          ref={graphRef}
          graphData={fgData as any}
          backgroundColor="rgba(0,0,0,0)"
          cooldownTicks={120}
          d3AlphaDecay={0.03}
          d3VelocityDecay={0.3}
          linkWidth={(l: any) => {
            const k = edgeKey(linkId(l.source), linkId(l.target));
            const highlighted = highlightPath?.has(k);
            return highlighted ? 2.2 : 0.8 + l.strength * 1.8;
          }}
          linkColor={(l: any) => {
            const k = edgeKey(linkId(l.source), linkId(l.target));
            if (highlightPath?.has(k)) return "rgba(251,191,36,0.95)";
            const su = linkId(l.source);
            const tu = linkId(l.target);
            const ca = communityById.get(su);
            const cb = communityById.get(tu);
            const isolatedHit =
              isolatedCommunity == null ||
              (ca === isolatedCommunity && cb === isolatedCommunity);
            const baseAlpha = 0.25 + l.strength * 0.55;
            const alpha = isolatedHit ? baseAlpha : baseAlpha * 0.18;
            // Edges within a community pick up that community's color;
            // cross-community edges stay neutral violet so they don't
            // shout over the cluster colors.
            const sameComm = ca != null && ca === cb;
            const colorHex = sameComm
              ? (fgData.nodes.find((n) => n.id === su)?.community_color ?? "#a855f7")
              : "#a855f7";
            return hexToRgba(colorHex, alpha);
          }}
          linkDirectionalParticles={(l: any) => {
            const k = edgeKey(linkId(l.source), linkId(l.target));
            return highlightPath?.has(k) ? 4 : 0;
          }}
          linkDirectionalParticleSpeed={0.006}
          linkDirectionalParticleColor={() => "rgba(251,191,36,0.95)"}
          linkDirectionalParticleWidth={2}
          nodeCanvasObject={(node: any, ctx: CanvasRenderingContext2D, scale: number) => {
            const n = node as FGNode;
            const radius = 5 + Math.min(8, n.degree * 0.8) + n.weight * 4;
            const isSelected = n.id === selectedId;
            const fill = n.community_color ?? DEFAULT_FILL;
            const isolated =
              isolatedCommunity != null && (n.community ?? -2) !== isolatedCommunity;
            const alpha = isolated ? 0.18 : 1.0;

            // Glow halo
            const grad = ctx.createRadialGradient(
              n.x!,
              n.y!,
              0,
              n.x!,
              n.y!,
              radius * 2.6,
            );
            grad.addColorStop(0, hexToRgba(fill, 0.55 * alpha));
            grad.addColorStop(1, hexToRgba(fill, 0));
            ctx.beginPath();
            ctx.fillStyle = grad;
            ctx.arc(n.x!, n.y!, radius * 2.6, 0, 2 * Math.PI, false);
            ctx.fill();

            // Core
            ctx.beginPath();
            ctx.fillStyle = hexToRgba(fill, alpha);
            ctx.arc(n.x!, n.y!, radius, 0, 2 * Math.PI, false);
            ctx.fill();

            // Centrality ring — high-weight nodes get a thin inner stroke
            // matching their community color so "this is a hub" reads
            // visually even before you mouse over.
            if (n.weight > 0.55) {
              ctx.beginPath();
              ctx.strokeStyle = hexToRgba("#ffffff", 0.65 * alpha);
              ctx.lineWidth = 1 / scale;
              ctx.arc(n.x!, n.y!, radius - 1.5 / scale, 0, 2 * Math.PI, false);
              ctx.stroke();
            }

            // Ring for selection
            if (isSelected) {
              ctx.beginPath();
              ctx.strokeStyle = "rgba(251,191,36,1)";
              ctx.lineWidth = 2 / scale;
              ctx.arc(n.x!, n.y!, radius + 3 / scale, 0, 2 * Math.PI, false);
              ctx.stroke();
            }

            // Label (only above a certain zoom, and always for the selected one)
            const labelOn = scale > 1.3 || isSelected || n.weight > 0.75;
            if (labelOn && !isolated) {
              const label = n.title.length > 32 ? n.title.slice(0, 29) + "…" : n.title;
              const fontSize = 12 / scale;
              ctx.font = `${fontSize}px ui-sans-serif, system-ui`;
              const textWidth = ctx.measureText(label).width;
              const pad = 4 / scale;
              ctx.fillStyle = "rgba(5,7,13,0.8)";
              ctx.fillRect(
                n.x! + radius + 6 / scale,
                n.y! - fontSize / 2 - pad,
                textWidth + 2 * pad,
                fontSize + 2 * pad,
              );
              ctx.fillStyle = "rgba(195,201,232,0.96)";
              ctx.fillText(label, n.x! + radius + 6 / scale + pad, n.y! + fontSize / 3);
            }
          }}
          nodePointerAreaPaint={(node: any, color, ctx) => {
            const n = node as FGNode;
            const radius = 5 + Math.min(8, n.degree * 0.8) + n.weight * 4;
            ctx.fillStyle = color;
            ctx.beginPath();
            ctx.arc(n.x!, n.y!, radius + 2, 0, 2 * Math.PI, false);
            ctx.fill();
          }}
          onNodeClick={(n: any) => onSelect(n as GraphNode)}
        />
      )}
    </div>
  );
}

function linkId(side: number | FGNode): number {
  return typeof side === "number" ? side : side.id;
}

function hexToRgba(hex: string, alpha: number): string {
  // Accept #RGB, #RRGGBB, or rgba(...) passthrough.
  if (hex.startsWith("rgba") || hex.startsWith("rgb")) return hex;
  let h = hex.replace("#", "");
  if (h.length === 3) {
    h = h
      .split("")
      .map((c) => c + c)
      .join("");
  }
  const r = parseInt(h.slice(0, 2), 16);
  const g = parseInt(h.slice(2, 4), 16);
  const b = parseInt(h.slice(4, 6), 16);
  return `rgba(${r},${g},${b},${alpha.toFixed(3)})`;
}
