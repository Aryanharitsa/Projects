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
  onSelect: (node: GraphNode) => void;
};

type FGNode = GraphNode & { x?: number; y?: number };
type FGLink = { source: number | FGNode; target: number | FGNode; strength: number };

const edgeKey = (a: number, b: number) => (a < b ? `${a}-${b}` : `${b}-${a}`);

export function Graph({ data, selectedId, highlightPath, onSelect }: Props) {
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
            const alpha = 0.25 + l.strength * 0.55;
            return `rgba(168,85,247,${alpha})`;
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

            // Glow halo
            const grad = ctx.createRadialGradient(
              n.x!,
              n.y!,
              0,
              n.x!,
              n.y!,
              radius * 2.6,
            );
            const hue = hueForWeight(n.weight);
            grad.addColorStop(0, `${hue}AA`);
            grad.addColorStop(1, `${hue}00`);
            ctx.beginPath();
            ctx.fillStyle = grad;
            ctx.arc(n.x!, n.y!, radius * 2.6, 0, 2 * Math.PI, false);
            ctx.fill();

            // Core
            ctx.beginPath();
            ctx.fillStyle = hue;
            ctx.arc(n.x!, n.y!, radius, 0, 2 * Math.PI, false);
            ctx.fill();

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
            if (labelOn) {
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

function hueForWeight(w: number): string {
  // low weight = cool cyan, high weight = hot violet/pink
  if (w > 0.75) return "#ec4899";
  if (w > 0.5) return "#a855f7";
  if (w > 0.25) return "#7c6cf0";
  return "#22d3ee";
}
