"use client";

import { useEffect, useMemo, useRef } from "react";
import {
  forceCenter,
  forceCollide,
  forceLink,
  forceManyBody,
  forceSimulation,
  type Simulation,
  type SimulationLinkDatum,
  type SimulationNodeDatum,
} from "d3-force";
import { useStore } from "@/lib/store";
import { buildGraph } from "@/lib/wikilinks";

type SimNode = SimulationNodeDatum & {
  id: string;
  title: string;
  degree: number;
  dangling?: boolean;
};

type SimLink = SimulationLinkDatum<SimNode>;

export default function GraphView() {
  const notes = useStore((s) => s.notes);
  const activeId = useStore((s) => s.activeId);
  const setActive = useStore((s) => s.setActive);

  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const simRef = useRef<Simulation<SimNode, SimLink> | null>(null);
  const nodesRef = useRef<SimNode[]>([]);
  const linksRef = useRef<SimLink[]>([]);
  const hoverRef = useRef<SimNode | null>(null);
  const dragRef = useRef<SimNode | null>(null);
  const transformRef = useRef({ x: 0, y: 0, k: 1 });
  const rafRef = useRef<number | null>(null);

  const graph = useMemo(() => buildGraph(notes), [notes]);

  // (Re)build sim whenever graph structure changes — but preserve positions
  // for nodes that already existed so the graph doesn't jolt on every edit.
  useEffect(() => {
    const prev = new Map(
      (nodesRef.current || []).map((n) => [n.id, { x: n.x, y: n.y, vx: n.vx, vy: n.vy }]),
    );

    const nodes: SimNode[] = graph.nodes.map((n) => {
      const p = prev.get(n.id);
      return {
        id: n.id,
        title: n.title,
        degree: n.degree,
        dangling: n.dangling,
        x: p?.x,
        y: p?.y,
        vx: p?.vx,
        vy: p?.vy,
      };
    });

    const links: SimLink[] = graph.edges.map((e) => ({
      source: e.source,
      target: e.target,
    }));

    nodesRef.current = nodes;
    linksRef.current = links;

    if (simRef.current) simRef.current.stop();
    const canvas = canvasRef.current!;
    const width = canvas.clientWidth || 600;
    const height = canvas.clientHeight || 500;

    const sim = forceSimulation<SimNode, SimLink>(nodes)
      .force(
        "link",
        forceLink<SimNode, SimLink>(links)
          .id((d) => d.id)
          .distance((l) => {
            const src = l.source as SimNode;
            const tgt = l.target as SimNode;
            const base = 58;
            return base + Math.min(20, (src.degree + tgt.degree) * 1.5);
          })
          .strength(0.4),
      )
      .force("charge", forceManyBody().strength(-120))
      .force("center", forceCenter(width / 2, height / 2).strength(0.06))
      .force("collide", forceCollide<SimNode>().radius((d) => nodeRadius(d) + 4))
      .alpha(0.9)
      .alphaDecay(0.03);

    sim.on("tick", scheduleDraw);
    simRef.current = sim;

    return () => {
      sim.stop();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [graph]);

  // Resize the canvas to fit its container (handles DPI).
  useEffect(() => {
    const canvas = canvasRef.current;
    const container = containerRef.current;
    if (!canvas || !container) return;
    const resize = () => {
      const dpr = window.devicePixelRatio || 1;
      const w = container.clientWidth;
      const h = container.clientHeight;
      canvas.width = w * dpr;
      canvas.height = h * dpr;
      canvas.style.width = `${w}px`;
      canvas.style.height = `${h}px`;
      const ctx = canvas.getContext("2d");
      if (ctx) ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      if (simRef.current) {
        simRef.current.force("center", forceCenter(w / 2, h / 2).strength(0.06));
        simRef.current.alpha(0.5).restart();
      }
      scheduleDraw();
    };
    const ro = new ResizeObserver(resize);
    ro.observe(container);
    resize();
    return () => ro.disconnect();
  }, []);

  // Pointer interaction: hover, click-to-open, drag, wheel-to-zoom, pan.
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const pick = (mx: number, my: number) => {
      const t = transformRef.current;
      const wx = (mx - t.x) / t.k;
      const wy = (my - t.y) / t.k;
      for (let i = nodesRef.current.length - 1; i >= 0; i--) {
        const n = nodesRef.current[i];
        if (n.x == null || n.y == null) continue;
        const r = nodeRadius(n) + 3;
        const dx = wx - n.x;
        const dy = wy - n.y;
        if (dx * dx + dy * dy <= r * r) return n;
      }
      return null;
    };

    const xy = (e: MouseEvent) => {
      const rect = canvas.getBoundingClientRect();
      return { mx: e.clientX - rect.left, my: e.clientY - rect.top };
    };

    const onMove = (e: MouseEvent) => {
      const { mx, my } = xy(e);
      if (dragRef.current) {
        const t = transformRef.current;
        const n = dragRef.current;
        n.fx = (mx - t.x) / t.k;
        n.fy = (my - t.y) / t.k;
        simRef.current?.alphaTarget(0.3).restart();
        return;
      }
      hoverRef.current = pick(mx, my);
      canvas.style.cursor = hoverRef.current ? "pointer" : "grab";
      scheduleDraw();
    };

    let panning = false;
    let panStart = { x: 0, y: 0 };
    const onDown = (e: MouseEvent) => {
      const { mx, my } = xy(e);
      const hit = pick(mx, my);
      if (hit) {
        dragRef.current = hit;
        const t = transformRef.current;
        hit.fx = (mx - t.x) / t.k;
        hit.fy = (my - t.y) / t.k;
      } else {
        panning = true;
        panStart = { x: mx - transformRef.current.x, y: my - transformRef.current.y };
        canvas.style.cursor = "grabbing";
      }
    };
    const onPan = (e: MouseEvent) => {
      if (!panning) return;
      const { mx, my } = xy(e);
      transformRef.current.x = mx - panStart.x;
      transformRef.current.y = my - panStart.y;
      scheduleDraw();
    };
    const onUp = () => {
      if (dragRef.current) {
        dragRef.current.fx = null;
        dragRef.current.fy = null;
        simRef.current?.alphaTarget(0);
        dragRef.current = null;
      }
      panning = false;
      canvas.style.cursor = "grab";
    };
    const onClick = (e: MouseEvent) => {
      const { mx, my } = xy(e);
      const hit = pick(mx, my);
      if (hit && !hit.dangling) setActive(hit.id);
    };
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const { mx, my } = xy(e);
      const t = transformRef.current;
      const factor = Math.exp(-e.deltaY * 0.0015);
      const k = Math.min(3, Math.max(0.3, t.k * factor));
      // Zoom toward cursor.
      t.x = mx - ((mx - t.x) * k) / t.k;
      t.y = my - ((my - t.y) * k) / t.k;
      t.k = k;
      scheduleDraw();
    };

    canvas.addEventListener("mousemove", onMove);
    canvas.addEventListener("mousemove", onPan);
    canvas.addEventListener("mousedown", onDown);
    window.addEventListener("mouseup", onUp);
    canvas.addEventListener("click", onClick);
    canvas.addEventListener("wheel", onWheel, { passive: false });
    return () => {
      canvas.removeEventListener("mousemove", onMove);
      canvas.removeEventListener("mousemove", onPan);
      canvas.removeEventListener("mousedown", onDown);
      window.removeEventListener("mouseup", onUp);
      canvas.removeEventListener("click", onClick);
      canvas.removeEventListener("wheel", onWheel);
    };
  }, [setActive]);

  // Redraw when the selected note changes.
  useEffect(() => {
    scheduleDraw();
  }, [activeId]);

  function scheduleDraw() {
    if (rafRef.current != null) return;
    rafRef.current = requestAnimationFrame(() => {
      rafRef.current = null;
      draw();
    });
  }

  function draw() {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const w = canvas.clientWidth;
    const h = canvas.clientHeight;
    const t = transformRef.current;
    ctx.clearRect(0, 0, w, h);

    // Background grid — feels like graph paper in space.
    drawGrid(ctx, w, h, t);

    ctx.save();
    ctx.translate(t.x, t.y);
    ctx.scale(t.k, t.k);

    // Compute neighbors for highlight.
    const activeNeighbors = new Set<string>();
    if (activeId) {
      for (const l of linksRef.current) {
        const s = (l.source as SimNode).id ?? (l.source as unknown as string);
        const tg = (l.target as SimNode).id ?? (l.target as unknown as string);
        if (s === activeId) activeNeighbors.add(tg as string);
        if (tg === activeId) activeNeighbors.add(s as string);
      }
    }

    // Edges
    for (const link of linksRef.current) {
      const s = link.source as SimNode;
      const tg = link.target as SimNode;
      if (s.x == null || s.y == null || tg.x == null || tg.y == null) continue;
      const connectsActive =
        activeId && (s.id === activeId || tg.id === activeId);
      const isDangling = !!(s.dangling || tg.dangling);

      ctx.beginPath();
      ctx.moveTo(s.x, s.y);
      ctx.lineTo(tg.x, tg.y);
      ctx.lineWidth = connectsActive ? 1.6 : 0.9;
      if (isDangling) {
        ctx.setLineDash([3, 3]);
        ctx.strokeStyle = connectsActive
          ? "rgba(255, 79, 216, 0.7)"
          : "rgba(255, 79, 216, 0.25)";
      } else {
        ctx.setLineDash([]);
        ctx.strokeStyle = connectsActive
          ? "rgba(34, 228, 255, 0.75)"
          : "rgba(154, 91, 255, 0.28)";
      }
      ctx.stroke();
    }
    ctx.setLineDash([]);

    // Nodes
    for (const n of nodesRef.current) {
      if (n.x == null || n.y == null) continue;
      const isActive = n.id === activeId;
      const isNeighbor = activeNeighbors.has(n.id);
      const isHover = hoverRef.current?.id === n.id;
      const r = nodeRadius(n);

      // Glow halo
      if (isActive || isHover) {
        const grad = ctx.createRadialGradient(n.x, n.y, r, n.x, n.y, r * 4);
        grad.addColorStop(0, "rgba(34, 228, 255, 0.35)");
        grad.addColorStop(1, "rgba(34, 228, 255, 0)");
        ctx.fillStyle = grad;
        ctx.beginPath();
        ctx.arc(n.x, n.y, r * 4, 0, Math.PI * 2);
        ctx.fill();
      }

      ctx.beginPath();
      ctx.arc(n.x, n.y, r, 0, Math.PI * 2);
      ctx.fillStyle = n.dangling
        ? "rgba(255, 79, 216, 0.15)"
        : isActive
          ? "#22e4ff"
          : isNeighbor
            ? "rgba(34, 228, 255, 0.75)"
            : "rgba(154, 91, 255, 0.85)";
      ctx.fill();

      ctx.lineWidth = isActive ? 2 : 1;
      ctx.strokeStyle = n.dangling
        ? "rgba(255, 79, 216, 0.7)"
        : isActive
          ? "#ffffff"
          : "rgba(255, 255, 255, 0.45)";
      if (n.dangling) ctx.setLineDash([2, 2]);
      ctx.stroke();
      ctx.setLineDash([]);

      // Labels: always show for active/hover/high-degree; otherwise fade.
      const showLabel =
        isActive ||
        isHover ||
        isNeighbor ||
        n.degree >= 3 ||
        nodesRef.current.length <= 12;
      if (showLabel) {
        ctx.font = `${isActive ? 600 : 500} 11px Inter, system-ui, sans-serif`;
        ctx.textAlign = "center";
        ctx.textBaseline = "top";
        ctx.fillStyle = isActive
          ? "#f5f7ff"
          : n.dangling
            ? "rgba(255, 79, 216, 0.9)"
            : "rgba(214, 219, 240, 0.85)";
        const label = truncate(n.title, 28);
        // soft text shadow for legibility over edges
        ctx.shadowColor = "rgba(5, 6, 13, 0.9)";
        ctx.shadowBlur = 4;
        ctx.fillText(label, n.x, n.y + r + 4);
        ctx.shadowBlur = 0;
      }
    }

    ctx.restore();
  }

  return (
    <div ref={containerRef} className="relative w-full h-full bg-void-900">
      <canvas ref={canvasRef} className="absolute inset-0" />
      {/* HUD */}
      <div className="absolute top-3 left-3 text-[10px] uppercase tracking-[0.18em] text-ink-400 flex items-center gap-2">
        <span className="px-2 py-0.5 rounded bg-void-700/70 border border-white/5">
          Synapse Graph
        </span>
        <span className="text-ink-500">drag · scroll · click</span>
      </div>
      <div className="absolute bottom-3 right-3 text-[10px] text-ink-400 flex items-center gap-3">
        <Legend color="#22e4ff" label="active" />
        <Legend color="#9a5bff" label="note" />
        <Legend color="#ff4fd8" label="ghost" dashed />
      </div>
    </div>
  );
}

function Legend({ color, label, dashed }: { color: string; label: string; dashed?: boolean }) {
  return (
    <span className="flex items-center gap-1">
      <span
        className="inline-block w-2.5 h-2.5 rounded-full"
        style={{
          background: dashed ? "transparent" : color,
          border: `1.5px ${dashed ? "dashed" : "solid"} ${color}`,
        }}
      />
      {label}
    </span>
  );
}

function nodeRadius(n: { degree: number; dangling?: boolean }) {
  if (n.dangling) return 4;
  return Math.min(14, 5 + Math.sqrt(n.degree) * 2.2);
}

function truncate(s: string, n: number) {
  return s.length <= n ? s : s.slice(0, n - 1) + "…";
}

function drawGrid(
  ctx: CanvasRenderingContext2D,
  w: number,
  h: number,
  t: { x: number; y: number; k: number },
) {
  const step = 36 * t.k;
  if (step < 10) return;
  ctx.save();
  ctx.strokeStyle = "rgba(255, 255, 255, 0.035)";
  ctx.lineWidth = 1;
  const offX = ((t.x % step) + step) % step;
  const offY = ((t.y % step) + step) % step;
  ctx.beginPath();
  for (let x = offX; x < w; x += step) {
    ctx.moveTo(x, 0);
    ctx.lineTo(x, h);
  }
  for (let y = offY; y < h; y += step) {
    ctx.moveTo(0, y);
    ctx.lineTo(w, y);
  }
  ctx.stroke();
  ctx.restore();
}
