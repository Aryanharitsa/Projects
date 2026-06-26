"use client";

/*
 * Lineage — TITAN's temporal fund-flow tracer (round-14, day-65).
 *
 * Render stack (every visualisation is hand-rolled SVG / CSS — zero
 * charting libraries imported, so the route stays small):
 *
 *   1. Hero  — mood-tinted gradient panel with a 168 px conic score
 *              ring, headline, advisory, seed picker, direction + depth
 *              + window controls, markdown-export button.
 *   2. Vital-signs strip (6 tiles, hue-rim-lit).
 *   3. Temporal DAG canvas — the centrepiece.  X axis is time
 *      (window_start → window_end), Y axis is hop depth.  Nodes are
 *      sized by in_amount, ringed in the bucket palette by suspicion,
 *      labelled with their display name + role chip.  Edges are
 *      animated dashed curves with thickness ∝ amount, colour by
 *      pattern-tag (rose for round_trip, orange for smurf, gold for
 *      integration, etc.).  Click any node → opens the provenance
 *      drawer.
 *   4. Pattern panel — one card per detected pattern, with ranked
 *      evidence chips + recommended action + contributing-node pills.
 *   5. Provenance drawer — sticky right column.  When a node is
 *      selected, shows its share-by-source breakdown as horizontal bars
 *      and the role tags as chips.
 *   6. Trail-score breakdown — five bars (one per factor) with their
 *      contribution + weight + raw value.
 *   7. Plan-of-action — numbered list, deep-links into /cases,
 *      /profile, /network.
 *   8. Footer — engine version + tunables dump.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import {
  getLineageSample,
  getLineageSeeds,
  lineageExportUrl,
  LineageDirection,
  LineageEdge,
  LineageMood,
  LineageNode,
  LineagePattern,
  LineageReport,
  LineageSeed,
} from "../../lib/api";

const MOOD_BG: Record<LineageMood, string> = {
  calm:     "radial-gradient(120% 100% at 50% 0%, rgba(34,211,168,0.18) 0%, rgba(7,11,20,0) 65%)",
  watch:    "radial-gradient(120% 100% at 50% 0%, rgba(251,191,36,0.20) 0%, rgba(7,11,20,0) 65%)",
  active:   "radial-gradient(120% 100% at 50% 0%, rgba(251,146,60,0.22) 0%, rgba(7,11,20,0) 65%)",
  critical: "radial-gradient(120% 100% at 50% 0%, rgba(239,68,68,0.26) 0%, rgba(7,11,20,0) 65%)",
};

const MOOD_ACCENT: Record<LineageMood, string> = {
  calm: "#22d3a8",
  watch: "#fbbf24",
  active: "#fb923c",
  critical: "#ef4444",
};

const MOOD_LABEL: Record<LineageMood, string> = {
  calm: "Calm trail",
  watch: "Watch trail",
  active: "Active trail",
  critical: "Critical trail",
};

const ROLE_HUE: Record<string, string> = {
  funnel: "#fb923c",
  mule: "#fbbf24",
  layer: "#ef4444",
  integration: "#a78bfa",
  smurf: "#fb923c",
};

const PRIORITY_HUE: Record<string, string> = {
  critical: "#ef4444",
  high: "#fb923c",
  medium: "#fbbf24",
  low: "#94a3b8",
};

const DIRECTION_CHOICES: { value: LineageDirection; label: string; hint: string }[] = [
  { value: "both",     label: "Both",       hint: "upstream + downstream" },
  { value: "forward",  label: "Downstream", hint: "where did funds go" },
  { value: "backward", label: "Upstream",   hint: "where did funds come from" },
];

const WINDOW_CHOICES: number[] = [7, 14, 30, 60];

function clamp(x: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, x));
}

function formatAmount(value: number): string {
  if (value >= 10_000_000) return `₹${(value / 10_000_000).toFixed(2)}Cr`;
  if (value >= 100_000)    return `₹${(value / 100_000).toFixed(2)}L`;
  if (value >= 1_000)      return `₹${(value / 1_000).toFixed(1)}k`;
  return `₹${Math.round(value).toLocaleString()}`;
}

function fmtTimestamp(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleString(undefined, {
      month: "short", day: "numeric",
      hour: "2-digit", minute: "2-digit",
    });
  } catch { return iso; }
}

function escapeHtml(s: string): string {
  return s.replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" })[c] || c);
}

function renderInlineMarkdown(text: string): string {
  return escapeHtml(text).replace(
    /\*\*(.+?)\*\*/g,
    '<strong class="text-white">$1</strong>',
  );
}

// =============================================================
// Temporal DAG layout (deterministic, time × depth)
// =============================================================

type LayoutNode = {
  id: string;
  x: number;       // [0,1]
  y: number;       // [0,1]
  node: LineageNode;
  size: number;    // node radius in px
};

type LayoutEdge = {
  edge: LineageEdge;
  sx: number; sy: number;
  tx: number; ty: number;
};

function layoutTrace(report: LineageReport, w: number, h: number, padX = 70, padY = 40) {
  const innerW = Math.max(1, w - padX * 2);
  const innerH = Math.max(1, h - padY * 2);
  const t0 = new Date(report.window_start).getTime();
  const t1 = new Date(report.window_end).getTime();
  const tSpan = Math.max(1, t1 - t0);

  // depth range
  const minDepth = Math.min(0, ...report.nodes.map((n) => n.depth));
  const maxDepth = Math.max(0, ...report.nodes.map((n) => n.depth));
  const depthSpan = Math.max(1, maxDepth - minDepth);

  // amount range for size mapping
  const amountMax = Math.max(
    1,
    ...report.nodes.map((n) => Math.max(n.in_amount, n.out_amount)),
  );

  // For each node, x = time of first_seen (clamped to window),
  // y = depth-fraction.  If first_seen missing, fall back to centre.
  const layoutNodes: LayoutNode[] = report.nodes.map((n) => {
    const ts = n.first_seen ? new Date(n.first_seen).getTime() : (t0 + t1) / 2;
    const xFrac = clamp((ts - t0) / tSpan, 0, 1);
    const yFrac = (n.depth - minDepth) / depthSpan;
    const size = 7 + 16 * Math.sqrt(Math.max(n.in_amount, n.out_amount) / amountMax);
    return {
      id: n.account_id,
      x: padX + xFrac * innerW,
      y: padY + yFrac * innerH,
      node: n,
      size,
    };
  });

  // Spread overlapping nodes along x by depth (deterministic jitter)
  const byPos = new Map<string, LayoutNode[]>();
  layoutNodes.forEach((ln) => {
    const k = `${Math.round(ln.x / 22)}:${Math.round(ln.y / 18)}`;
    if (!byPos.has(k)) byPos.set(k, []);
    byPos.get(k)!.push(ln);
  });
  byPos.forEach((arr) => {
    if (arr.length === 1) return;
    arr.sort((a, b) => a.node.account_id.localeCompare(b.node.account_id));
    arr.forEach((ln, i) => {
      const shift = (i - (arr.length - 1) / 2) * 26;
      ln.y = clamp(ln.y + shift, padY, h - padY);
    });
  });

  const nodeIndex = new Map(layoutNodes.map((ln) => [ln.id, ln]));
  const layoutEdges: LayoutEdge[] = report.edges
    .filter((e) => nodeIndex.has(e.src) && nodeIndex.has(e.dst))
    .map((e) => {
      const s = nodeIndex.get(e.src)!;
      const t = nodeIndex.get(e.dst)!;
      return { edge: e, sx: s.x, sy: s.y, tx: t.x, ty: t.y };
    });

  return { layoutNodes, layoutEdges, padX, padY, w, h };
}

function bezierPath(sx: number, sy: number, tx: number, ty: number): string {
  const mx = (sx + tx) / 2;
  return `M${sx},${sy} C${mx},${sy} ${mx},${ty} ${tx},${ty}`;
}

function edgeColor(e: LineageEdge): string {
  if (e.pattern_tags.includes("round_trip")) return "#ef4444";
  if (e.pattern_tags.includes("smurf_chain")) return "#fb923c";
  if (e.pattern_tags.includes("integration")) return "#a78bfa";
  if (e.pattern_tags.includes("pass_through")) return "#fbbf24";
  if (e.pattern_tags.includes("geo_hopping")) return "#60a5fa";
  return "#3b4658";
}

function edgeWidth(e: LineageEdge, max: number): number {
  return 1.0 + 3.6 * Math.sqrt(Math.min(1, e.amount / Math.max(1, max)));
}

// =============================================================
// Subcomponents
// =============================================================

function ScoreRing({
  score, mood, size = 168,
}: { score: number; mood: LineageMood; size?: number }) {
  const pct = clamp(score, 0, 100);
  const accent = MOOD_ACCENT[mood];
  const bg = `conic-gradient(${accent} 0% ${pct}%, rgba(255,255,255,0.06) ${pct}% 100%)`;
  return (
    <div
      className="relative flex items-center justify-center rounded-full"
      style={{
        width: size, height: size, background: bg,
        animation: "pulse-breathe 4.6s ease-in-out infinite",
      }}
    >
      <div
        className="flex flex-col items-center justify-center rounded-full bg-[#070b14]"
        style={{ width: size - 24, height: size - 24 }}
      >
        <div className="text-[44px] font-semibold leading-none text-white" style={{ color: accent }}>
          {score}
        </div>
        <div className="mt-1 text-[10px] uppercase tracking-[0.18em] text-white/55">
          trail · {mood}
        </div>
      </div>
    </div>
  );
}

function ChipPill({
  children, hue, dim = false,
}: { children: any; hue: string; dim?: boolean }) {
  return (
    <span
      className="inline-flex items-center rounded-full border px-2 py-0.5 text-[10.5px] uppercase tracking-wider"
      style={{
        background: `${hue}${dim ? "0f" : "1a"}`,
        borderColor: `${hue}55`,
        color: hue,
      }}
    >
      {children}
    </span>
  );
}

function PatternCard({ p, onPick }: { p: LineagePattern; onPick: (id: string) => void }) {
  return (
    <div
      className="rounded-xl border border-white/10 bg-white/[0.02] p-4"
      style={{ borderLeft: `3px solid ${p.accent}` }}
    >
      <div className="flex items-center justify-between gap-3">
        <div>
          <div className="text-[15px] font-semibold text-white">{p.label}</div>
          <div className="text-[11px] uppercase tracking-wider text-white/45">
            {p.code} · {p.severity}
          </div>
        </div>
        <div
          className="rounded-md px-2.5 py-1 text-[12.5px] font-semibold"
          style={{ background: `${p.accent}1f`, color: p.accent }}
        >
          {Math.round(p.confidence * 100)}%
        </div>
      </div>
      <ul className="mt-3 space-y-1.5">
        {p.evidence.map((ev, i) => (
          <li
            key={i}
            className="text-[12.5px] leading-snug text-white/75"
            dangerouslySetInnerHTML={{ __html: "• " + renderInlineMarkdown(ev) }}
          />
        ))}
      </ul>
      {p.contributing_nodes.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {p.contributing_nodes.slice(0, 6).map((nid) => (
            <button
              key={nid}
              type="button"
              onClick={() => onPick(nid)}
              className="rounded-md border border-white/10 bg-white/[0.04] px-2 py-0.5 text-[11px] text-white/80 hover:bg-white/[0.08]"
              title="Open provenance"
            >
              {nid}
            </button>
          ))}
        </div>
      )}
      <div className="mt-3 rounded-md border border-white/10 bg-black/30 px-3 py-2 text-[12px] text-white/70">
        <span className="font-semibold text-white">Action · </span>
        {p.action}
      </div>
    </div>
  );
}

// =============================================================
// Main page
// =============================================================

export default function LineagePage() {
  const [report, setReport] = useState<LineageReport | null>(null);
  const [seeds, setSeeds] = useState<LineageSeed[]>([]);
  const [seed, setSeed] = useState<string>("");
  const [direction, setDirection] = useState<LineageDirection>("both");
  const [maxDepth, setMaxDepth] = useState<number>(4);
  const [windowDays, setWindowDays] = useState<number>(30);
  const [loading, setLoading] = useState<boolean>(true);
  const [refreshing, setRefreshing] = useState<boolean>(false);
  const [err, setErr] = useState<string | null>(null);
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  const canvasRef = useRef<HTMLDivElement>(null);
  const [canvasW, setCanvasW] = useState<number>(960);
  const canvasH = 460;

  const load = useCallback(async () => {
    setErr(null);
    setRefreshing(true);
    try {
      const r = await getLineageSample({
        seed: seed || undefined,
        direction,
        max_depth: maxDepth,
        window_days: windowDays,
      });
      setReport(r);
      if (!seed && r.seed) setSeed(r.seed);
      setSelectedNode((cur) => {
        if (cur && r.nodes.some((n) => n.account_id === cur)) return cur;
        return r.seed;
      });
    } catch (e: any) {
      setErr(e?.message || "Failed to load lineage trace.");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [seed, direction, maxDepth, windowDays]);

  // bootstrap
  useEffect(() => {
    getLineageSeeds()
      .then((r) => setSeeds(r.seeds))
      .catch(() => setSeeds([]));
  }, []);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    function measure() {
      if (!canvasRef.current) return;
      const rect = canvasRef.current.getBoundingClientRect();
      setCanvasW(Math.max(640, Math.floor(rect.width)));
    }
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, [report]);

  const layout = useMemo(() => {
    if (!report) return null;
    return layoutTrace(report, canvasW, canvasH);
  }, [report, canvasW]);

  const maxEdgeAmount = useMemo(() => {
    if (!report) return 1;
    return Math.max(1, ...report.edges.map((e) => e.amount));
  }, [report]);

  const selected = useMemo(
    () => report?.nodes.find((n) => n.account_id === selectedNode) || null,
    [report, selectedNode],
  );

  if (loading) {
    return (
      <div className="rounded-xl border border-white/10 bg-white/[0.02] p-8 text-center text-white/70">
        Loading lineage trace…
      </div>
    );
  }

  if (err || !report) {
    return (
      <div className="rounded-xl border border-rose-400/30 bg-rose-400/[0.06] p-6 text-rose-200">
        <div className="text-[13px] font-semibold uppercase tracking-wider">Lineage failed</div>
        <div className="mt-1 text-[14px] text-white/80">{err || "Empty response."}</div>
        <button
          type="button"
          onClick={load}
          className="mt-3 rounded-md border border-white/15 bg-white/[0.04] px-3 py-1.5 text-[12.5px] text-white hover:bg-white/[0.08]"
        >
          Retry
        </button>
      </div>
    );
  }

  const mood = report.mood;
  const accent = MOOD_ACCENT[mood];

  return (
    <div className="space-y-6">
      {/* ===== Hero ===== */}
      <section
        className="lineage-hero glass-strong rounded-2xl border border-white/10 p-6 md:p-7"
        style={{ background: MOOD_BG[mood] }}
      >
        <div className="grid grid-cols-1 gap-6 md:grid-cols-[auto_1fr]">
          <div className="flex items-center justify-center">
            <ScoreRing score={report.trail_score} mood={mood} />
          </div>
          <div className="space-y-3">
            <div className="flex flex-wrap items-center gap-2">
              <ChipPill hue={accent}>{MOOD_LABEL[mood]}</ChipPill>
              <ChipPill hue="#94a3b8">{report.direction}</ChipPill>
              <ChipPill hue="#94a3b8">{report.window_days}d window</ChipPill>
              <ChipPill hue="#94a3b8">depth ≤ {report.max_depth}</ChipPill>
              {report.source === "sample" && (
                <ChipPill hue="#fbbf24" dim>demo · sample fixture</ChipPill>
              )}
            </div>
            <h1
              className="text-[26px] font-semibold leading-tight text-white md:text-[28px]"
              dangerouslySetInnerHTML={{ __html: renderInlineMarkdown(report.headline) }}
            />
            <p className="text-[14px] leading-snug text-white/75">{report.advisory}</p>
            <div className="text-[11.5px] uppercase tracking-wider text-white/45">
              composed {fmtTimestamp(report.composed_at)} · engine {report.engine}
            </div>
          </div>
        </div>

        {/* Controls */}
        <div className="mt-5 grid grid-cols-1 gap-3 md:grid-cols-3">
          <div className="rounded-xl border border-white/10 bg-black/30 p-3">
            <div className="text-[11px] uppercase tracking-wider text-white/45">Seed account</div>
            <select
              value={seed}
              onChange={(e) => setSeed(e.target.value)}
              className="mt-2 w-full rounded-md border border-white/10 bg-black/40 px-2.5 py-1.5 text-[13px] text-white outline-none focus:border-white/30"
            >
              {seeds.length === 0 && <option value="">{report.seed_label}</option>}
              {seeds.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.label} — {s.context}
                </option>
              ))}
            </select>
          </div>
          <div className="rounded-xl border border-white/10 bg-black/30 p-3">
            <div className="text-[11px] uppercase tracking-wider text-white/45">Direction</div>
            <div className="mt-2 grid grid-cols-3 gap-1">
              {DIRECTION_CHOICES.map((d) => (
                <button
                  key={d.value}
                  type="button"
                  onClick={() => setDirection(d.value)}
                  className="rounded-md px-2 py-1 text-[12px] transition"
                  style={{
                    background: direction === d.value ? "rgba(255,255,255,0.1)" : "transparent",
                    color: direction === d.value ? "#fff" : "rgba(255,255,255,0.65)",
                    border: "1px solid rgba(255,255,255,0.10)",
                  }}
                  title={d.hint}
                >
                  {d.label}
                </button>
              ))}
            </div>
          </div>
          <div className="rounded-xl border border-white/10 bg-black/30 p-3">
            <div className="flex items-center justify-between">
              <div className="text-[11px] uppercase tracking-wider text-white/45">
                Depth · {maxDepth}
              </div>
              <div className="text-[11px] uppercase tracking-wider text-white/45">
                Window
              </div>
            </div>
            <div className="mt-2 flex items-center gap-2">
              <input
                type="range" min={1} max={6} step={1}
                value={maxDepth}
                onChange={(e) => setMaxDepth(parseInt(e.target.value, 10))}
                className="flex-1 accent-white"
              />
              <div className="flex gap-1">
                {WINDOW_CHOICES.map((d) => (
                  <button
                    key={d}
                    type="button"
                    onClick={() => setWindowDays(d)}
                    className="rounded px-2 py-1 text-[11.5px]"
                    style={{
                      background: windowDays === d ? "rgba(255,255,255,0.10)" : "transparent",
                      color: windowDays === d ? "#fff" : "rgba(255,255,255,0.6)",
                      border: "1px solid rgba(255,255,255,0.10)",
                    }}
                  >
                    {d}d
                  </button>
                ))}
              </div>
            </div>
          </div>
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={load}
            disabled={refreshing}
            className="rounded-md border border-white/15 bg-white/[0.05] px-3 py-1.5 text-[12.5px] text-white hover:bg-white/[0.10]"
          >
            {refreshing ? "Recomputing…" : "Recompute"}
          </button>
          <a
            href={lineageExportUrl({ seed, direction, max_depth: maxDepth, window_days: windowDays })}
            target="_blank" rel="noreferrer"
            className="rounded-md border border-white/10 px-3 py-1.5 text-[12.5px] text-white/80 hover:bg-white/[0.05]"
          >
            Download §3 exhibit (.md)
          </a>
          <Link
            href={`/cases?account_id=${seed}`}
            className="rounded-md border border-white/10 px-3 py-1.5 text-[12.5px] text-white/70 hover:bg-white/[0.05]"
          >
            Open seed in Cases →
          </Link>
          <Link
            href={`/network?seed=${seed}`}
            className="rounded-md border border-white/10 px-3 py-1.5 text-[12.5px] text-white/70 hover:bg-white/[0.05]"
          >
            Open seed in Network →
          </Link>
        </div>
      </section>

      {/* ===== Vital-signs strip ===== */}
      <section className="grid grid-cols-2 gap-3 md:grid-cols-6">
        {[
          {
            label: "Nodes traced", value: String(report.nodes.length),
            sub: `${report.nodes.filter((n) => n.suspicion_score >= 0.4).length} suspicious`,
            hue: "#60a5fa",
          },
          {
            label: "Edges traced", value: String(report.edges.length),
            sub: `${report.edges.filter((e) => e.pattern_tags.length > 0).length} flagged`,
            hue: "#a78bfa",
          },
          {
            label: "Depth (longest)", value: String(Math.max(0, report.longest_path.length - 1)),
            sub: `path of ${report.longest_path.length} accounts`,
            hue: "#22d3a8",
          },
          {
            label: "Amount traced", value: formatAmount(report.total_amount_traced),
            sub: `max edge ${formatAmount(maxEdgeAmount)}`,
            hue: "#fbbf24",
          },
          {
            label: "Jurisdictions", value: String(report.distinct_geos.length),
            sub: report.distinct_geos.join(" · ") || "—",
            hue: "#fb923c",
          },
          {
            label: "Patterns", value: String(report.patterns.length),
            sub: report.patterns.map((p) => p.code.split("_")[0]).slice(0, 3).join(" · ") || "none",
            hue: "#ef4444",
          },
        ].map((t) => (
          <div
            key={t.label}
            className="glass-strong rounded-xl border border-white/10 p-3"
            style={{ boxShadow: `inset 4px 0 0 0 ${t.hue}` }}
          >
            <div className="text-[10.5px] uppercase tracking-wider text-white/45">{t.label}</div>
            <div className="mt-1 text-[19px] font-semibold text-white">{t.value}</div>
            <div className="mt-0.5 text-[11.5px] text-white/55">{t.sub}</div>
          </div>
        ))}
      </section>

      {/* ===== Temporal DAG canvas ===== */}
      <section className="glass-strong rounded-2xl border border-white/10 p-4 md:p-5">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-[15px] font-semibold text-white">Temporal fund-flow trail</h2>
            <p className="text-[12px] text-white/55">
              X = time (window start → end) · Y = hop depth from seed · circle = account (size ∝ amount, ring = suspicion) · edge = transaction (thickness ∝ amount, colour = pattern).
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {[
              { c: "#fb923c", l: "smurf" },
              { c: "#ef4444", l: "round-trip" },
              { c: "#fbbf24", l: "pass-through" },
              { c: "#a78bfa", l: "integration" },
              { c: "#60a5fa", l: "geo-hop" },
              { c: "#3b4658", l: "ordinary" },
            ].map((s) => (
              <div key={s.l} className="flex items-center gap-1.5 text-[11px] text-white/60">
                <span style={{ width: 12, height: 3, background: s.c, display: "inline-block" }} />
                {s.l}
              </div>
            ))}
          </div>
        </div>

        <div ref={canvasRef} className="mt-3 overflow-hidden rounded-xl border border-white/10 bg-black/30">
          {layout && (
            <svg width={canvasW} height={canvasH} role="img" aria-label="Lineage trail">
              {/* time-axis grid */}
              {[0.25, 0.5, 0.75].map((f, i) => {
                const x = layout.padX + f * (canvasW - layout.padX * 2);
                return (
                  <line
                    key={i}
                    x1={x} y1={layout.padY - 6}
                    x2={x} y2={canvasH - layout.padY + 6}
                    stroke="rgba(255,255,255,0.06)"
                    strokeDasharray="2 4"
                  />
                );
              })}
              {/* axis labels */}
              <text x={layout.padX} y={canvasH - 12} fill="rgba(255,255,255,0.45)" fontSize={10.5}>
                {fmtTimestamp(report.window_start)}
              </text>
              <text x={canvasW - layout.padX} y={canvasH - 12} fill="rgba(255,255,255,0.45)" fontSize={10.5} textAnchor="end">
                {fmtTimestamp(report.window_end)}
              </text>
              <text x={10} y={layout.padY + 4} fill="rgba(255,255,255,0.45)" fontSize={10.5}>
                hop +{Math.max(0, ...report.nodes.map((n) => n.depth))}
              </text>
              <text x={10} y={canvasH - layout.padY} fill="rgba(255,255,255,0.45)" fontSize={10.5}>
                hop {Math.min(0, ...report.nodes.map((n) => n.depth))}
              </text>

              {/* edges */}
              {layout.layoutEdges.map((le, i) => {
                const stroke = edgeColor(le.edge);
                const flagged = le.edge.pattern_tags.length > 0;
                return (
                  <g key={i}>
                    <path
                      d={bezierPath(le.sx, le.sy, le.tx, le.ty)}
                      fill="none"
                      stroke={stroke}
                      strokeOpacity={flagged ? 0.95 : 0.5}
                      strokeWidth={edgeWidth(le.edge, maxEdgeAmount)}
                      className={flagged ? "lineage-flow-line" : ""}
                    />
                  </g>
                );
              })}

              {/* nodes */}
              {layout.layoutNodes.map((ln) => {
                const isSel = selectedNode === ln.id;
                const isSeed = ln.id === report.seed;
                const ringColor = ln.node.suspicion_score >= 0.6
                  ? "#ef4444"
                  : ln.node.suspicion_score >= 0.3
                  ? "#fb923c"
                  : isSeed
                  ? "#fff"
                  : "#94a3b8";
                return (
                  <g
                    key={ln.id}
                    transform={`translate(${ln.x}, ${ln.y})`}
                    onClick={() => setSelectedNode(ln.id)}
                    style={{ cursor: "pointer" }}
                    className={isSeed ? "lineage-node-pulse" : ""}
                  >
                    <circle
                      r={ln.size + (isSel ? 6 : 0)}
                      fill={isSeed ? "rgba(34,211,168,0.18)" : "rgba(15,23,42,0.55)"}
                      stroke={ringColor}
                      strokeWidth={isSel ? 3 : isSeed ? 2.5 : 1.5}
                    />
                    {ln.node.role_tags.length > 0 && (
                      <circle
                        r={ln.size + 3}
                        fill="none"
                        stroke={ROLE_HUE[ln.node.role_tags[0]] || "#a78bfa"}
                        strokeOpacity={0.7}
                        strokeWidth={1.5}
                        strokeDasharray="2 3"
                      />
                    )}
                    <text
                      x={0}
                      y={ln.size + 14}
                      textAnchor="middle"
                      fill="rgba(255,255,255,0.85)"
                      fontSize={11}
                      style={{ pointerEvents: "none" }}
                    >
                      {ln.node.display_name.length > 22
                        ? ln.node.display_name.slice(0, 20) + "…"
                        : ln.node.display_name}
                    </text>
                    {(ln.node.role_tags.length > 0 || isSeed) && (
                      <text
                        x={0} y={ln.size + 26}
                        textAnchor="middle"
                        fill={isSeed ? "#22d3a8" : ROLE_HUE[ln.node.role_tags[0]] || "#a78bfa"}
                        fontSize={9.5}
                        style={{ pointerEvents: "none" }}
                      >
                        {isSeed ? "SEED" : ln.node.role_tags[0]?.toUpperCase()}
                      </text>
                    )}
                  </g>
                );
              })}
            </svg>
          )}
        </div>
      </section>

      {/* ===== Patterns + Provenance side-by-side ===== */}
      <section className="grid grid-cols-1 gap-4 lg:grid-cols-[1.4fr_1fr]">
        <div className="space-y-3">
          <div>
            <h2 className="text-[15px] font-semibold text-white">
              Detected patterns ({report.patterns.length})
            </h2>
            <p className="text-[12px] text-white/55">
              Six flow-shape detectors run over the DAG. Ranked by confidence.
            </p>
          </div>
          {report.patterns.length === 0 ? (
            <div className="rounded-xl border border-white/10 bg-white/[0.02] p-5 text-center text-[13px] text-white/65">
              No patterns matched — trail looks like an ordinary flow of funds.
            </div>
          ) : (
            <div className="space-y-3">
              {report.patterns.map((p) => (
                <PatternCard key={p.code} p={p} onPick={setSelectedNode} />
              ))}
            </div>
          )}
        </div>

        {/* Provenance drawer */}
        <div className="space-y-3">
          <div>
            <h2 className="text-[15px] font-semibold text-white">Node provenance</h2>
            <p className="text-[12px] text-white/55">
              FIFO lot-tracer — what fraction of this account's recent inflow can be attributed to each upstream source.
            </p>
          </div>
          {selected ? (
            <div className="glass-strong rounded-xl border border-white/10 p-4">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <div className="text-[14.5px] font-semibold text-white">
                    {selected.display_name}
                  </div>
                  <div className="text-[11px] uppercase tracking-wider text-white/45">
                    {selected.account_id} · depth {selected.depth} · geo {selected.geo || "—"}
                  </div>
                </div>
                <div
                  className="rounded-md px-2 py-1 text-[12px] font-semibold"
                  style={{
                    background: "rgba(239,68,68,0.10)",
                    color: selected.suspicion_score >= 0.6 ? "#ef4444" : "#94a3b8",
                  }}
                >
                  suspicion {Math.round(selected.suspicion_score * 100)}
                </div>
              </div>
              {selected.role_tags.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {selected.role_tags.map((t) => (
                    <ChipPill key={t} hue={ROLE_HUE[t] || "#a78bfa"}>{t}</ChipPill>
                  ))}
                </div>
              )}
              <dl className="mt-3 grid grid-cols-2 gap-2 text-[12px]">
                <div className="rounded-md border border-white/10 bg-black/30 px-3 py-2">
                  <dt className="uppercase text-[10px] tracking-wider text-white/45">Inflow</dt>
                  <dd className="text-white">{formatAmount(selected.in_amount)} · {selected.in_count} tx · {selected.distinct_inflows} payer(s)</dd>
                </div>
                <div className="rounded-md border border-white/10 bg-black/30 px-3 py-2">
                  <dt className="uppercase text-[10px] tracking-wider text-white/45">Outflow</dt>
                  <dd className="text-white">{formatAmount(selected.out_amount)} · {selected.out_count} tx · {selected.distinct_outflows} payee(s)</dd>
                </div>
                <div className="rounded-md border border-white/10 bg-black/30 px-3 py-2">
                  <dt className="uppercase text-[10px] tracking-wider text-white/45">Retention</dt>
                  <dd className="text-white">{(selected.retention * 100).toFixed(1)}%</dd>
                </div>
                <div className="rounded-md border border-white/10 bg-black/30 px-3 py-2">
                  <dt className="uppercase text-[10px] tracking-wider text-white/45">Active range</dt>
                  <dd className="text-[11.5px] text-white">
                    {selected.first_seen ? fmtTimestamp(selected.first_seen) : "—"}
                    <br/>
                    → {selected.last_seen ? fmtTimestamp(selected.last_seen) : "—"}
                  </dd>
                </div>
              </dl>
              <div className="mt-4">
                <div className="text-[11.5px] uppercase tracking-wider text-white/50">
                  Inflow provenance · {selected.provenance.length} source(s)
                </div>
                <div className="mt-2 space-y-1.5">
                  {selected.provenance.length === 0 && (
                    <div className="text-[12px] text-white/55">
                      No upstream provenance — this account is the origin point in the window.
                    </div>
                  )}
                  {selected.provenance.slice(0, 8).map((p) => {
                    const w = clamp(p.share * 100, 2, 100);
                    return (
                      <button
                        type="button"
                        key={p.source_id}
                        onClick={() => p.source_id !== "__other__" && setSelectedNode(p.source_id)}
                        className="block w-full rounded-md border border-white/10 bg-white/[0.02] px-3 py-1.5 text-left hover:bg-white/[0.04]"
                      >
                        <div className="flex items-center justify-between text-[12px]">
                          <span className="text-white/80">{p.source_label}</span>
                          <span className="font-mono text-white/65">
                            {(p.share * 100).toFixed(1)}% · {p.via_hops}h
                          </span>
                        </div>
                        <div className="mt-1 h-1.5 w-full rounded bg-white/[0.04]">
                          <div
                            className="h-1.5 rounded"
                            style={{
                              width: `${w}%`,
                              background: "linear-gradient(90deg, rgba(34,211,168,0.85), rgba(96,165,250,0.85))",
                            }}
                          />
                        </div>
                      </button>
                    );
                  })}
                </div>
              </div>
              <Link
                href={`/profile?customer_id=${selected.account_id}`}
                className="mt-4 inline-block rounded-md border border-white/10 px-3 py-1.5 text-[12px] text-white/80 hover:bg-white/[0.05]"
              >
                Open {selected.display_name} in Profile →
              </Link>
            </div>
          ) : (
            <div className="rounded-xl border border-white/10 bg-white/[0.02] p-5 text-center text-[13px] text-white/55">
              Click any node in the trail to inspect its provenance.
            </div>
          )}
        </div>
      </section>

      {/* ===== Trail-score breakdown ===== */}
      <section className="glass-strong rounded-2xl border border-white/10 p-4 md:p-5">
        <h2 className="text-[15px] font-semibold text-white">Trail score breakdown</h2>
        <p className="text-[12px] text-white/55">
          Composite of five normalised factors. Each bar shows the factor's contribution to the 0–100 trail score.
        </p>
        <div className="mt-4 space-y-2">
          {report.factors.map((f) => {
            const w = clamp(f.contribution, 0, 100);
            return (
              <div key={f.key} className="grid grid-cols-[110px_1fr_70px] items-center gap-3">
                <div className="text-[12px] text-white/70">{f.key.replace("_", " ")}</div>
                <div className="h-2 w-full rounded bg-white/[0.04]">
                  <div
                    className="h-2 rounded"
                    style={{
                      width: `${w}%`,
                      background: `linear-gradient(90deg, ${accent}, ${accent}aa)`,
                    }}
                  />
                </div>
                <div className="text-right font-mono text-[12px] text-white/75">
                  {f.contribution.toFixed(1)}pt
                  <span className="ml-1 text-white/40">· w{(f.weight * 100).toFixed(0)}</span>
                </div>
              </div>
            );
          })}
        </div>
      </section>

      {/* ===== Plan of action ===== */}
      <section className="glass-strong rounded-2xl border border-white/10 p-4 md:p-5">
        <h2 className="text-[15px] font-semibold text-white">
          Plan of action ({report.plan_of_action.length})
        </h2>
        <p className="text-[12px] text-white/55">
          Prioritised checklist. Each item deep-links into the TITAN tab it lives in.
        </p>
        <ol className="mt-4 space-y-2">
          {report.plan_of_action.map((a, i) => {
            const hue = PRIORITY_HUE[a.priority] || "#94a3b8";
            const inner = (
              <div
                className="flex items-start gap-3 rounded-xl border border-white/10 bg-white/[0.02] px-4 py-3"
                style={{ boxShadow: `inset 3px 0 0 0 ${hue}` }}
              >
                <div
                  className="grid h-7 w-7 shrink-0 place-items-center rounded-full text-[12px] font-semibold"
                  style={{ background: `${hue}1f`, color: hue }}
                >
                  {i + 1}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="text-[10.5px] uppercase tracking-wider text-white/45">
                    {a.kind} · {a.priority}
                  </div>
                  <div
                    className="mt-0.5 text-[13px] leading-snug text-white/80"
                    dangerouslySetInnerHTML={{ __html: renderInlineMarkdown(a.body) }}
                  />
                </div>
              </div>
            );
            return (
              <li key={i}>
                {a.href ? <Link href={a.href} className="block hover:opacity-90">{inner}</Link> : inner}
              </li>
            );
          })}
        </ol>
      </section>

      {/* ===== Footer ===== */}
      <footer className="rounded-xl border border-white/5 bg-white/[0.02] px-4 py-3 text-[11.5px] text-white/50">
        <div className="font-mono">
          {report.engine} · score = 0.40·depth + 0.25·amount + 0.15·pattern + 0.10·geo + 0.10·suspicious_node ·
          patterns: smurf_chain · round_trip · pass_through · integration · velocity_ramp · geo_hopping
        </div>
      </footer>
    </div>
  );
}
