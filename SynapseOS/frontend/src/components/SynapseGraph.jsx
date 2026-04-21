import { useEffect, useMemo, useRef, useState } from "react";
import {
  forceCenter,
  forceCollide,
  forceLink,
  forceManyBody,
  forceSimulation,
  forceX,
  forceY,
} from "d3-force";

/**
 * A canvas-based force-directed graph tuned for SynapseOS.
 * - Node radius scales with degree (size field from backend).
 * - Edge opacity/thickness scales with strength.
 * - Nodes glow (radial gradient) over a dark background.
 * - Hover highlights neighbourhood; click selects.
 */
export default function SynapseGraph({
  graph,
  selectedId,
  onSelect,
  onHover,
  className = "",
}) {
  const canvasRef = useRef(null);
  const wrapRef   = useRef(null);
  const [dims, setDims] = useState({ w: 800, h: 600 });
  const simRef   = useRef(null);
  const hoverRef = useRef(null);

  // Observe container size — the graph fills its parent.
  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      const r = entries[0].contentRect;
      setDims({ w: Math.max(320, r.width), h: Math.max(320, r.height) });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // Build sim nodes/links. Memoize by id set so we don't restart unnecessarily.
  const simData = useMemo(() => {
    if (!graph) return { nodes: [], links: [] };
    const nodes = graph.nodes.map((n) => ({
      ...n,
      r: 6 + Math.min(20, Math.sqrt((n.size ?? 0) * 16)),
    }));
    const idToNode = new Map(nodes.map((n) => [n.id, n]));
    const links = graph.edges
      .filter((e) => idToNode.has(e.source) && idToNode.has(e.target))
      .map((e) => ({
        source: idToNode.get(e.source),
        target: idToNode.get(e.target),
        strength: e.strength,
      }));
    return { nodes, links };
  }, [graph]);

  // (Re)start simulation when data changes or container resizes.
  useEffect(() => {
    if (simRef.current) simRef.current.stop();
    if (!simData.nodes.length) return;

    const sim = forceSimulation(simData.nodes)
      .force("charge", forceManyBody().strength(-220))
      .force("link",
        forceLink(simData.links)
          .id((d) => d.id)
          .distance((l) => 70 + (1 - l.strength) * 140)
          .strength((l) => 0.2 + l.strength * 0.6))
      .force("x", forceX(dims.w / 2).strength(0.04))
      .force("y", forceY(dims.h / 2).strength(0.04))
      .force("center", forceCenter(dims.w / 2, dims.h / 2))
      .force("collide", forceCollide().radius((d) => d.r + 4))
      .alpha(0.9)
      .alphaDecay(0.03);

    sim.on("tick", draw);
    simRef.current = sim;
    return () => sim.stop();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [simData, dims.w, dims.h]);

  // Redraw when selection changes even if sim has cooled.
  useEffect(() => {
    draw();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId]);

  function draw() {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const dpr = window.devicePixelRatio || 1;
    canvas.width  = dims.w * dpr;
    canvas.height = dims.h * dpr;
    canvas.style.width  = `${dims.w}px`;
    canvas.style.height = `${dims.h}px`;
    const ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, dims.w, dims.h);

    const hoveredId = hoverRef.current;
    const neighbors = new Set();
    if (hoveredId || selectedId) {
      const focus = hoveredId ?? selectedId;
      for (const l of simData.links) {
        if (l.source.id === focus) neighbors.add(l.target.id);
        if (l.target.id === focus) neighbors.add(l.source.id);
      }
    }

    // edges
    for (const l of simData.links) {
      const strong = (hoveredId || selectedId)
        && (l.source.id === hoveredId || l.target.id === hoveredId
         || l.source.id === selectedId || l.target.id === selectedId);

      const alpha = strong
        ? 0.55 + l.strength * 0.45
        : 0.08 + l.strength * 0.25;

      ctx.beginPath();
      const grad = ctx.createLinearGradient(l.source.x, l.source.y,
                                             l.target.x, l.target.y);
      grad.addColorStop(0, `rgba(167,139,250,${alpha})`);
      grad.addColorStop(1, `rgba(244,114,182,${alpha})`);
      ctx.strokeStyle = grad;
      ctx.lineWidth = 0.6 + l.strength * 2.4;
      ctx.moveTo(l.source.x, l.source.y);
      ctx.lineTo(l.target.x, l.target.y);
      ctx.stroke();
    }

    // nodes
    for (const n of simData.nodes) {
      const isSelected = n.id === selectedId;
      const isHover    = n.id === hoveredId;
      const isNeighbor = neighbors.has(n.id);
      const dim = (hoveredId || selectedId) && !isSelected && !isHover && !isNeighbor;

      // glow halo
      const haloR = n.r * (isSelected || isHover ? 4.2 : 2.8);
      const halo = ctx.createRadialGradient(n.x, n.y, 0, n.x, n.y, haloR);
      halo.addColorStop(0, isSelected
        ? "rgba(244,114,182,0.55)"
        : isHover ? "rgba(167,139,250,0.55)"
                  : `rgba(129,140,248,${dim ? 0.08 : 0.22})`);
      halo.addColorStop(1, "rgba(129,140,248,0)");
      ctx.fillStyle = halo;
      ctx.beginPath();
      ctx.arc(n.x, n.y, haloR, 0, Math.PI * 2);
      ctx.fill();

      // solid core
      ctx.beginPath();
      ctx.arc(n.x, n.y, n.r, 0, Math.PI * 2);
      const core = ctx.createRadialGradient(n.x, n.y, 0, n.x, n.y, n.r);
      if (isSelected) {
        core.addColorStop(0, "#fbcfe8");
        core.addColorStop(1, "#db2777");
      } else if (isHover) {
        core.addColorStop(0, "#ddd6fe");
        core.addColorStop(1, "#7c3aed");
      } else {
        core.addColorStop(0, dim ? "#3b3f55" : "#c7d2fe");
        core.addColorStop(1, dim ? "#1e2033" : "#6366f1");
      }
      ctx.fillStyle = core;
      ctx.fill();
      ctx.strokeStyle = "rgba(255,255,255,0.2)";
      ctx.lineWidth = 0.75;
      ctx.stroke();

      // label for high-degree / selected / hovered nodes
      if (isSelected || isHover || n.r > 10) {
        ctx.font = "11px ui-sans-serif, system-ui, sans-serif";
        ctx.fillStyle = dim
          ? "rgba(255,255,255,0.25)"
          : "rgba(255,255,255,0.92)";
        ctx.textAlign = "center";
        ctx.textBaseline = "top";
        const label = n.title.length > 34
          ? n.title.slice(0, 33) + "…"
          : n.title;
        ctx.fillText(label, n.x, n.y + n.r + 4);
      }
    }
  }

  // interaction — pointer hover + click
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    function pickNode(ev) {
      const rect = canvas.getBoundingClientRect();
      const x = ev.clientX - rect.left;
      const y = ev.clientY - rect.top;
      let best = null, bestD = Infinity;
      for (const n of simData.nodes) {
        const dx = n.x - x, dy = n.y - y;
        const d = dx * dx + dy * dy;
        const r = n.r + 6;
        if (d < r * r && d < bestD) {
          best = n; bestD = d;
        }
      }
      return best;
    }

    function onMove(ev) {
      const n = pickNode(ev);
      const id = n ? n.id : null;
      if (id !== hoverRef.current) {
        hoverRef.current = id;
        canvas.style.cursor = id ? "pointer" : "default";
        onHover?.(n);
        draw();
      }
    }
    function onClick(ev) {
      const n = pickNode(ev);
      onSelect?.(n ? n.id : null);
    }
    function onLeave() {
      hoverRef.current = null;
      onHover?.(null);
      draw();
    }
    canvas.addEventListener("mousemove", onMove);
    canvas.addEventListener("click", onClick);
    canvas.addEventListener("mouseleave", onLeave);
    return () => {
      canvas.removeEventListener("mousemove", onMove);
      canvas.removeEventListener("click", onClick);
      canvas.removeEventListener("mouseleave", onLeave);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [simData, onSelect, onHover]);

  return (
    <div
      ref={wrapRef}
      className={`relative w-full h-full overflow-hidden rounded-2xl border border-white/10 bg-gradient-to-b from-[#0a0b1c] to-[#05060f] ${className}`}
    >
      <canvas ref={canvasRef} />
      {!simData.nodes.length && (
        <div className="absolute inset-0 grid place-items-center text-white/40 text-sm">
          No thoughts yet. Drop one in and watch the synapses form.
        </div>
      )}
    </div>
  );
}
