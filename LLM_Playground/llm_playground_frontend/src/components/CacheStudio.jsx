import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { Input } from "@/components/ui/input";
import {
  Database,
  Sparkles,
  Play,
  Timer,
  DollarSign,
  Activity,
  Copy,
  Download,
  ClipboardCheck,
  Layers,
  Zap,
  Gauge,
  Cog,
  Rows3,
  Cpu,
  Fingerprint,
  Percent,
  TrendingDown,
  TrendingUp,
  Repeat,
  Package,
  ScanSearch,
} from "lucide-react";
import ApiService from "../services/api";

// ── Palette ───────────────────────────────────────────────────────────────
const POLICY_HUE = {
  lru:  { hue: "#38bdf8", ring: "sky-500",     text: "text-sky-200",     bg: "bg-sky-500/15",     border: "border-sky-500/40",     gradient: "from-sky-500/25 via-blue-500/15 to-transparent" },
  lfu:  { hue: "#34d399", ring: "emerald-500", text: "text-emerald-200", bg: "bg-emerald-500/15", border: "border-emerald-500/40", gradient: "from-emerald-500/25 via-teal-500/15 to-transparent" },
  fifo: { hue: "#f59e0b", ring: "amber-500",   text: "text-amber-200",   bg: "bg-amber-500/15",   border: "border-amber-500/40",   gradient: "from-amber-500/25 via-orange-500/15 to-transparent" },
  sdiv: { hue: "#e879f9", ring: "fuchsia-500", text: "text-fuchsia-200", bg: "bg-fuchsia-500/15", border: "border-fuchsia-500/40", gradient: "from-fuchsia-500/25 via-purple-500/15 to-transparent" },
};

const PICK_HUE = {
  conservative: { hue: "#10b981", text: "text-emerald-200", border: "border-emerald-500/50", bg: "bg-emerald-500/10", chip: "bg-emerald-500/15 text-emerald-200 border-emerald-500/40", icon: TrendingDown, label: "Conservative" },
  balanced:     { hue: "#38bdf8", text: "text-sky-200",     border: "border-sky-500/50",     bg: "bg-sky-500/10",     chip: "bg-sky-500/15 text-sky-200 border-sky-500/40",         icon: Gauge,        label: "Balanced" },
  aggressive:   { hue: "#e879f9", text: "text-fuchsia-200", border: "border-fuchsia-500/50", bg: "bg-fuchsia-500/10", chip: "bg-fuchsia-500/15 text-fuchsia-200 border-fuchsia-500/40", icon: TrendingUp,   label: "Aggressive" },
};

const hueFor = (p) => POLICY_HUE[p] || POLICY_HUE.lru;
const pickHueFor = (k) => PICK_HUE[k] || PICK_HUE.balanced;

const fmtPct = (n, d = 1) => `${(Math.max(0, Math.min(1, n || 0)) * 100).toFixed(d)}%`;
const fmtUSD = (n, d = 2) => `$${(n || 0).toFixed(d)}`;
const fmtMS  = (n) => `${Math.round(n || 0)} ms`;
const fmtInt = (n) => `${(n || 0).toLocaleString()}`;

// ── Reusable atoms ────────────────────────────────────────────────────────
function ScoreRing({ pct = 0, size = 172, stroke = 14, hue = "#38bdf8", subLabel = "hit rate", label }) {
  const dashLen = 2 * Math.PI * ((size - stroke) / 2);
  const clamped = Math.max(0, Math.min(100, pct));
  const filled = (clamped / 100) * dashLen;
  return (
    <div className="relative" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size/2} cy={size/2} r={(size-stroke)/2} fill="none"
          stroke="rgba(255,255,255,0.06)" strokeWidth={stroke} />
        <circle cx={size/2} cy={size/2} r={(size-stroke)/2} fill="none"
          stroke={hue} strokeWidth={stroke}
          strokeDasharray={`${filled} ${dashLen}`} strokeLinecap="round"
          style={{ transition: "stroke-dasharray 400ms cubic-bezier(0.22,0.61,0.36,1)" }} />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <div className="text-4xl font-bold text-white tabular-nums">{label ?? `${clamped.toFixed(0)}%`}</div>
        <div className="text-[10px] uppercase tracking-widest text-white/50 mt-1">{subLabel}</div>
      </div>
    </div>
  );
}

function StatTile({ icon: Icon, label, value, hint, hue = "text-white/85" }) {
  return (
    <Card className="bg-white/[0.03] border-white/10">
      <CardContent className="p-3">
        <div className="flex items-center gap-2 text-[10px] uppercase tracking-widest text-white/50">
          {Icon && <Icon className="w-3.5 h-3.5" />}
          {label}
        </div>
        <div className={`text-xl font-bold tabular-nums mt-1 ${hue}`}>{value}</div>
        {hint && <div className="text-[11px] text-white/50 mt-0.5">{hint}</div>}
      </CardContent>
    </Card>
  );
}

function PolicyChip({ policy, active, onClick }) {
  const h = hueFor(policy);
  return (
    <button onClick={onClick}
      className={`px-2 py-1 rounded border text-[11px] uppercase tracking-widest font-semibold
        ${active ? `${h.bg} ${h.text} ${h.border}` : "bg-white/[0.03] text-white/50 border-white/10 hover:text-white/80"}`}>
      {policy}
    </button>
  );
}

// ── Threshold sweep curve (SVG) ───────────────────────────────────────────
function SweepCurve({ points, activeThreshold, onPickThreshold }) {
  const width = 640, height = 220, padL = 44, padR = 20, padT = 16, padB = 32;
  if (!points || points.length === 0) return <div className="text-white/40 text-sm">No sweep data yet.</div>;
  const xs = points.map(p => p.threshold);
  const xMin = Math.min(...xs), xMax = Math.max(...xs);
  const xr = xMax - xMin || 1;
  const sx = (x) => padL + ((x - xMin) / xr) * (width - padL - padR);
  const sy = (v) => padT + (1 - Math.max(0, Math.min(1, v))) * (height - padT - padB);

  const line = (accessor, hue) => {
    const d = points.map((p, i) => `${i === 0 ? "M" : "L"} ${sx(p.threshold).toFixed(1)} ${sy(accessor(p)).toFixed(1)}`).join(" ");
    return <path d={d} fill="none" stroke={hue} strokeWidth={2.2} strokeLinecap="round" />;
  };

  return (
    <div className="w-full overflow-x-auto">
      <svg width={width} height={height} className="text-white/60">
        {/* grid */}
        {[0, 0.25, 0.5, 0.75, 1].map(g => (
          <line key={g} x1={padL} x2={width - padR} y1={sy(g)} y2={sy(g)} stroke="rgba(255,255,255,0.08)" strokeDasharray="2 2" />
        ))}
        {[0, 0.25, 0.5, 0.75, 1].map(g => (
          <text key={g} x={padL - 6} y={sy(g) + 3} textAnchor="end" fontSize="9" fill="rgba(255,255,255,0.5)" fontFamily="monospace">
            {(g * 100).toFixed(0)}
          </text>
        ))}
        {/* x-axis ticks */}
        {points.map((p, i) => (
          <g key={i}>
            <line x1={sx(p.threshold)} y1={height - padB} x2={sx(p.threshold)} y2={height - padB + 3} stroke="rgba(255,255,255,0.4)" />
            <text x={sx(p.threshold)} y={height - padB + 14} textAnchor="middle" fontSize="9" fill="rgba(255,255,255,0.5)" fontFamily="monospace">
              {p.threshold.toFixed(2)}
            </text>
          </g>
        ))}

        {/* Lines */}
        {line(p => p.hit_rate, "#38bdf8")}
        {line(p => p.savings_pct, "#34d399")}
        {line(p => p.quality_risk_pct, "#fb7185")}

        {/* Points + active marker */}
        {points.map((p, i) => (
          <g key={i}>
            <circle cx={sx(p.threshold)} cy={sy(p.hit_rate)} r={3} fill="#38bdf8" />
            <circle cx={sx(p.threshold)} cy={sy(p.savings_pct)} r={3} fill="#34d399" />
            <circle cx={sx(p.threshold)} cy={sy(p.quality_risk_pct)} r={3} fill="#fb7185" />
            <rect
              x={sx(p.threshold) - 14} y={padT}
              width={28} height={height - padT - padB}
              fill={activeThreshold === p.threshold ? "rgba(255,255,255,0.06)" : "transparent"}
              onClick={() => onPickThreshold && onPickThreshold(p.threshold)}
              style={{ cursor: "pointer" }}
            />
          </g>
        ))}

        {/* Legend */}
        <g transform={`translate(${padL + 8}, ${padT + 4})`}>
          <circle cx={0} cy={0} r={3} fill="#38bdf8" />
          <text x={8} y={3} fontSize="10" fill="rgba(255,255,255,0.75)">hit rate</text>
          <circle cx={70} cy={0} r={3} fill="#34d399" />
          <text x={78} y={3} fontSize="10" fill="rgba(255,255,255,0.75)">savings</text>
          <circle cx={140} cy={0} r={3} fill="#fb7185" />
          <text x={148} y={3} fontSize="10" fill="rgba(255,255,255,0.75)">quality risk</text>
        </g>
      </svg>
    </div>
  );
}

// ── 4×N policy grid heatmap ───────────────────────────────────────────────
function PolicyGrid({ grid, thresholds, activePolicy, activeThreshold, onPick }) {
  if (!grid) return null;
  const policies = ["lru", "lfu", "fifo", "sdiv"];

  const cellFor = (v) => {
    const c = Math.max(0, Math.min(1, v));
    if (c < 0.25) return `rgba(244, 63, 94, ${0.20 + c * 1.2})`;
    if (c < 0.55) return `rgba(245, 158, 11, ${0.30 + (c - 0.25) * 1.3})`;
    if (c < 0.75) return `rgba(56, 189, 248, ${0.30 + (c - 0.55) * 1.5})`;
    return `rgba(16, 185, 129, ${0.35 + (c - 0.75) * 2.0})`;
  };

  return (
    <div className="w-full overflow-x-auto">
      <div className="min-w-[540px]">
        {/* Header */}
        <div className="grid" style={{ gridTemplateColumns: `120px repeat(${thresholds.length}, minmax(52px, 1fr))` }}>
          <div className="text-[10px] uppercase tracking-widest text-white/50 py-2">Policy \ threshold</div>
          {thresholds.map((t, i) => (
            <div key={i} className="text-[10px] uppercase tracking-widest text-white/50 py-2 text-center font-mono">
              {t.toFixed(2)}
            </div>
          ))}
        </div>
        {policies.map(p => {
          const h = hueFor(p);
          const row = grid[p] || [];
          return (
            <div key={p} className="grid items-center gap-1"
              style={{ gridTemplateColumns: `120px repeat(${thresholds.length}, minmax(52px, 1fr))` }}>
              <div className="flex items-center gap-2 py-1">
                <span className={`inline-block w-2 h-2 rounded-full`} style={{ background: h.hue }} />
                <span className={`text-[11px] font-semibold uppercase tracking-widest ${h.text}`}>{p}</span>
              </div>
              {row.map((cell, i) => {
                const isActive = activePolicy === p && Math.abs(activeThreshold - cell.threshold) < 1e-4;
                return (
                  <button key={i}
                    className={`h-11 relative text-[10px] font-semibold tabular-nums text-white/90 rounded
                      ${isActive ? "ring-2 ring-white/70" : "ring-1 ring-white/5 hover:ring-white/30"}`}
                    style={{ background: cellFor(cell.savings_pct) }}
                    title={`savings=${(cell.savings_pct*100).toFixed(1)}% · hit=${(cell.hit_rate*100).toFixed(1)}% · risk=${(cell.quality_risk_pct*100).toFixed(1)}%`}
                    onClick={() => onPick && onPick(p, cell.threshold)}>
                    <div>{(cell.savings_pct*100).toFixed(0)}</div>
                    <div className="text-[8px] text-white/60">{(cell.hit_rate*100).toFixed(0)}/{(cell.quality_risk_pct*100).toFixed(0)}</div>
                  </button>
                );
              })}
            </div>
          );
        })}
      </div>
      <div className="text-[10px] text-white/40 mt-2">
        Cell shade = savings %. Row 1 = savings %, row 2 = hit % / quality-risk %. Click a cell to snap the studio to that (policy, threshold).
      </div>
    </div>
  );
}

// ── Recommendation card ───────────────────────────────────────────────────
function RecCard({ kind, pick, active, onClick, monthlyRequests }) {
  const h = pickHueFor(kind);
  const Icon = h.icon;
  if (!pick) {
    return (
      <Card className={`bg-white/[0.02] border-white/10`}>
        <CardContent className="p-4 text-white/50 text-sm">
          {h.label}: no recipe met the constraints.
        </CardContent>
      </Card>
    );
  }
  const ph = hueFor(pick.policy);
  return (
    <button onClick={onClick}
      className={`text-left rounded-lg border p-4 w-full transition
        ${active ? `${h.border} ${h.bg}` : "border-white/10 bg-white/[0.02] hover:bg-white/[0.05]"}`}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Icon className={`w-4 h-4 ${h.text}`} />
          <div className={`text-[11px] uppercase tracking-widest font-semibold ${h.text}`}>
            {h.label}
          </div>
        </div>
        {active && <ClipboardCheck className={`w-4 h-4 ${h.text}`} />}
      </div>
      <div className="mt-1 text-white/85 text-sm">{pick.blurb}</div>
      <div className="mt-3 grid grid-cols-3 gap-2">
        <div>
          <div className="text-[9px] uppercase tracking-widest text-white/40">Policy · thr</div>
          <div className={`text-xs font-semibold ${ph.text}`}>{pick.policy.toUpperCase()} · {pick.threshold.toFixed(2)}</div>
        </div>
        <div>
          <div className="text-[9px] uppercase tracking-widest text-white/40">Hit rate</div>
          <div className="text-xs font-semibold text-white/85 tabular-nums">{fmtPct(pick.hit_rate)}</div>
        </div>
        <div>
          <div className="text-[9px] uppercase tracking-widest text-white/40">Quality risk</div>
          <div className="text-xs font-semibold text-white/85 tabular-nums">{fmtPct(pick.quality_risk_pct)}</div>
        </div>
        <div>
          <div className="text-[9px] uppercase tracking-widest text-white/40">Save/mo</div>
          <div className={`text-xs font-semibold ${h.text} tabular-nums`}>{fmtUSD(pick.monthly_savings_usd)}</div>
        </div>
        <div>
          <div className="text-[9px] uppercase tracking-widest text-white/40">Cost/mo</div>
          <div className="text-xs font-semibold text-white/85 tabular-nums">{fmtUSD(pick.monthly_cost_usd)}</div>
        </div>
        <div>
          <div className="text-[9px] uppercase tracking-widest text-white/40">Latency</div>
          <div className="text-xs font-semibold text-white/85 tabular-nums">{fmtMS(pick.avg_latency_ms)}</div>
        </div>
      </div>
    </button>
  );
}

// ── Cluster bar chart ─────────────────────────────────────────────────────
function ClusterBars({ clusters }) {
  if (!clusters || clusters.length === 0) return <div className="text-white/40 text-sm">No clusters at this threshold.</div>;
  const top = clusters.slice(0, 12);
  const max = Math.max(...top.map(c => c.size));
  const palette = ["#38bdf8", "#34d399", "#e879f9", "#f59e0b", "#a78bfa", "#fb7185", "#2dd4bf", "#f472b6", "#60a5fa", "#facc15", "#4ade80", "#f97316"];
  return (
    <div className="space-y-1.5">
      {top.map((c, i) => (
        <div key={c.cluster_id} className="flex items-center gap-3">
          <div className="w-16 text-[10px] font-mono text-white/50 shrink-0">{c.cluster_id}</div>
          <div className="flex-1 min-w-0">
            <div className="text-[11px] text-white/85 truncate">{c.representative}</div>
            <div className="flex items-center gap-1 mt-1">
              <div className="h-1.5 rounded-full flex-1 bg-white/5 overflow-hidden">
                <div className="h-full rounded-full" style={{ width: `${(c.size / max) * 100}%`, background: palette[i % palette.length] }} />
              </div>
              <span className="text-[10px] font-mono text-white/60 shrink-0 tabular-nums">{c.size} · {fmtPct(c.share_pct)}</span>
            </div>
            {c.intents.length > 0 && (
              <div className="text-[9px] text-white/40 mt-0.5 truncate">
                {c.intents.map(t => `#${t}`).join("  ")}
              </div>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

// ── Trace tail ────────────────────────────────────────────────────────────
function TraceTail({ trace }) {
  if (!trace || trace.length === 0) return <div className="text-white/40 text-sm">No requests yet.</div>;
  return (
    <div className="text-[11px] font-mono">
      <div className="grid grid-cols-[38px_60px_60px_60px_1fr] gap-2 text-[9px] uppercase tracking-widest text-white/40 pb-2 border-b border-white/10">
        <div>#</div><div>Result</div><div>Sim</div><div>Lat</div><div>Match / intent</div>
      </div>
      {trace.map((t, i) => (
        <div key={i} className="grid grid-cols-[38px_60px_60px_60px_1fr] gap-2 py-1 border-b border-white/5">
          <div className="text-white/40">{t.step}</div>
          <div className={t.outcome === "hit" ? "text-emerald-300" : "text-white/60"}>
            {t.outcome}
          </div>
          <div className="text-white/70 tabular-nums">{t.similarity.toFixed(2)}</div>
          <div className="text-white/60 tabular-nums">{Math.round(t.latency_ms)}ms</div>
          <div className="text-white/85 truncate">
            {t.matched_prompt ? <span className="text-white/60">↳ {t.matched_prompt}</span> : <span className="italic text-white/40">miss — inserted</span>}
            {t.intent && t.intent !== "(untagged)" && <span className="text-[10px] text-white/40 ml-2">#{t.intent}</span>}
          </div>
        </div>
      ))}
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────
export default function CacheStudio() {
  const [defaultsCfg, setDefaultsCfg] = useState(null);
  const [workloads, setWorkloads] = useState([]);
  const [policies, setPolicies] = useState([]);

  const [workloadId, setWorkloadId] = useState("customer_support");
  const [threshold, setThreshold] = useState(0.85);
  const [capacity, setCapacity] = useState(256);
  const [ttlDays, setTtlDays] = useState(7);
  const [policy, setPolicy] = useState("lru");
  const [monthlyReq, setMonthlyReq] = useState(100000);
  const [qualityCeiling, setQualityCeiling] = useState(8); // percent

  const [sim, setSim] = useState(null);
  const [sweep, setSweep] = useState(null);
  const [picks, setPicks] = useState(null);
  const [clusters, setClusters] = useState(null);
  const [compiled, setCompiled] = useState(null);
  const [markdown, setMarkdown] = useState("");
  const [activePick, setActivePick] = useState(null);
  const [busy, setBusy] = useState(false);
  const [copyState, setCopyState] = useState(null);

  const debounceRef = useRef(null);

  // Bootstrap ─ load seed, defaults, and workload catalog
  useEffect(() => {
    (async () => {
      try {
        setBusy(true);
        const [d, p, w, s] = await Promise.all([
          ApiService.cacheDefaults(),
          ApiService.cachePolicies(),
          ApiService.cacheWorkloads(),
          ApiService.cacheSeed(),
        ]);
        setDefaultsCfg(d.defaults);
        setPolicies(p.policies);
        setWorkloads(w.workloads);
        const seed = s.seed;
        setWorkloadId(seed.workload_id);
        setThreshold(seed.simulation.threshold);
        setCapacity(seed.simulation.capacity);
        setPolicy(seed.simulation.policy);
        setTtlDays(Math.max(1, Math.round(seed.simulation.ttl_seconds / 86400)));
        setSim(seed.simulation);
        setSweep({ curve: seed.threshold_curve, grid: seed.policy_grid });
        setPicks(seed.recommendations);
        setClusters(seed.clusters);
        setCompiled(seed.compiled);
        setMarkdown(seed.markdown);
      } catch (e) {
        console.error("cache bootstrap failed", e);
      } finally {
        setBusy(false);
      }
    })();
  }, []);

  const runSim = useCallback(async () => {
    try {
      setBusy(true);
      const cfg = {
        workload_id: workloadId,
        threshold,
        capacity,
        ttl_seconds: ttlDays * 86400,
        policy,
      };
      const [s, sw, r, cl, cp] = await Promise.all([
        ApiService.cacheSimulate(cfg),
        ApiService.cacheSweep({ workload_id: workloadId, policy, capacity, ttl_seconds: ttlDays * 86400 }),
        ApiService.cacheRecommend({
          workload_id: workloadId,
          capacity,
          ttl_seconds: ttlDays * 86400,
          monthly_requests: monthlyReq,
          quality_risk_ceiling: qualityCeiling / 100,
        }),
        ApiService.cacheCluster({ workload_id: workloadId, threshold }),
        ApiService.cacheCompile({
          workload_id: workloadId,
          policy,
          threshold,
          capacity,
          ttl_seconds: ttlDays * 86400,
          monthly_requests: monthlyReq,
          quality_risk_ceiling: qualityCeiling / 100,
        }),
      ]);
      setSim(s.simulation);
      setSweep({ curve: sw.curve, grid: sw.grid });
      setPicks(r.recommendations);
      setClusters(cl.clusters);
      setCompiled(cp.config);
      setMarkdown(cp.markdown);
    } catch (e) {
      console.error("cache runSim failed", e);
    } finally {
      setBusy(false);
    }
  }, [workloadId, threshold, capacity, ttlDays, policy, monthlyReq, qualityCeiling]);

  // Debounced auto-run when any control changes
  useEffect(() => {
    if (!defaultsCfg) return;
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => { runSim(); }, 220);
    return () => debounceRef.current && clearTimeout(debounceRef.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workloadId, threshold, capacity, ttlDays, policy, monthlyReq, qualityCeiling]);

  const currentWorkload = useMemo(
    () => workloads.find(w => w.id === workloadId),
    [workloads, workloadId]
  );

  const applyPick = useCallback((kind) => {
    const pick = picks?.picks?.[kind];
    if (!pick) return;
    setPolicy(pick.policy);
    setThreshold(pick.threshold);
    setActivePick(kind);
  }, [picks]);

  const snapTo = useCallback((p, t) => {
    setPolicy(p);
    setThreshold(t);
    setActivePick(null);
  }, []);

  const copy = useCallback(async (text, key) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopyState(key);
      setTimeout(() => setCopyState(null), 1400);
    } catch (e) {
      console.warn("clipboard failed", e);
    }
  }, []);

  const download = useCallback((filename, text, mime = "text/markdown") => {
    const blob = new Blob([text], { type: mime });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = filename; a.click();
    URL.revokeObjectURL(url);
  }, []);

  const hitPct  = (sim?.rates?.hit_rate  ?? 0) * 100;
  const savePct = (sim?.cost?.savings_pct ?? 0) * 100;
  const riskPct = (sim?.rates?.quality_risk_pct ?? 0) * 100;
  const activePolicyHue = hueFor(policy);

  return (
    <div className="w-full space-y-4">
      {/* Hero ─────────────────────────────────────────────────────────── */}
      <Card className="border-white/10 overflow-hidden">
        <div className={`bg-gradient-to-br ${activePolicyHue.gradient} p-5`}>
          <div className="flex items-center justify-between mb-4">
            <div>
              <div className="flex items-center gap-2">
                <Database className="w-4 h-4 text-white/70" />
                <span className="text-[10px] uppercase tracking-widest text-white/60">Studio</span>
                <span className="text-[10px] uppercase tracking-widest text-white/40">·</span>
                <span className="text-[10px] uppercase tracking-widest text-white/60">Semantic response cache</span>
              </div>
              <h2 className="text-white text-2xl font-bold tracking-tight mt-1">Cache <span className="text-white/50 text-lg font-medium">— tune the knife-edge</span></h2>
              <p className="text-white/60 text-sm mt-1 max-w-3xl">
                Simulate a semantic cache against any workload. Sweep the similarity threshold,
                compare four eviction policies side by side, and ship a JSON config that a middleware
                layer can enforce byte-for-byte.
              </p>
            </div>
            <div className="flex items-center gap-3">
              <ScoreRing pct={hitPct} hue={activePolicyHue.hue} subLabel="hit rate" size={132} stroke={10}
                label={`${hitPct.toFixed(0)}%`} />
              <ScoreRing pct={savePct} hue="#34d399" subLabel="cost saved" size={132} stroke={10}
                label={`${savePct.toFixed(0)}%`} />
            </div>
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <StatTile icon={Percent} label="Hit rate"
              value={fmtPct(sim?.rates?.hit_rate, 1)}
              hint={`${fmtInt(sim?.totals?.hits ?? 0)} / ${fmtInt(sim?.totals?.requests ?? 0)} requests`}
              hue="text-sky-200" />
            <StatTile icon={DollarSign} label="Monthly savings"
              value={picks?.picks?.balanced ? fmtUSD(picks.picks.balanced.monthly_savings_usd, 2) : "—"}
              hint={`vs ${fmtUSD(picks?.picks?.balanced?.monthly_baseline_usd ?? 0)} baseline`}
              hue="text-emerald-200" />
            <StatTile icon={Timer} label="Avg latency"
              value={fmtMS(sim?.latency_ms?.avg)}
              hint={`p50 ${fmtMS(sim?.latency_ms?.p50)} · p95 ${fmtMS(sim?.latency_ms?.p95)}`}
              hue="text-white/85" />
            <StatTile icon={Activity} label="Quality risk"
              value={fmtPct(sim?.rates?.quality_risk_pct, 1)}
              hint={`hits below ${defaultsCfg?.safe_similarity_bar?.toFixed(2) ?? "0.85"} similarity bar`}
              hue={riskPct > (qualityCeiling) ? "text-rose-200" : "text-emerald-200"} />
          </div>
        </div>
      </Card>

      {/* Recommendations ──────────────────────────────────────────────── */}
      <Card className="bg-white/[0.02] border-white/10">
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <CardTitle className="text-white text-base flex items-center gap-2">
              <Sparkles className="w-4 h-4 text-fuchsia-300" />
              Three shippable picks
              <span className="text-[10px] uppercase tracking-widest text-white/40 ml-1">
                @ {fmtInt(monthlyReq)} req/mo · quality-risk ceiling {qualityCeiling}%
              </span>
            </CardTitle>
            <div className="flex items-center gap-3">
              <div className="flex items-center gap-1">
                <Label className="text-[10px] uppercase tracking-widest text-white/50">req/mo</Label>
                <Input value={monthlyReq}
                  onChange={(e) => setMonthlyReq(Math.max(1, parseInt(e.target.value.replace(/[^0-9]/g, "") || "0", 10)))}
                  className="w-28 h-7 bg-white/[0.03] border-white/10 text-white text-xs" />
              </div>
              <div className="flex items-center gap-1 w-56">
                <Label className="text-[10px] uppercase tracking-widest text-white/50 shrink-0">risk ≤</Label>
                <Slider value={[qualityCeiling]} onValueChange={([v]) => setQualityCeiling(v)}
                  min={0} max={30} step={1} className="flex-1" />
                <span className="text-[10px] text-white/60 tabular-nums w-8 shrink-0 text-right">{qualityCeiling}%</span>
              </div>
            </div>
          </div>
        </CardHeader>
        <CardContent className="grid grid-cols-1 md:grid-cols-3 gap-3">
          {["conservative", "balanced", "aggressive"].map((kind) => (
            <RecCard key={kind} kind={kind}
              pick={picks?.picks?.[kind]}
              active={activePick === kind}
              monthlyRequests={monthlyReq}
              onClick={() => applyPick(kind)} />
          ))}
        </CardContent>
      </Card>

      {/* Controls + Sweep ─────────────────────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Card className="bg-white/[0.02] border-white/10 lg:col-span-1">
          <CardHeader className="pb-2">
            <CardTitle className="text-white text-base flex items-center gap-2">
              <Cog className="w-4 h-4 text-sky-300" /> Cache config
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {/* Workload */}
            <div>
              <Label className="text-[10px] uppercase tracking-widest text-white/50 mb-2 block">Workload</Label>
              <div className="grid grid-cols-1 gap-2">
                {workloads.map(w => {
                  const active = w.id === workloadId;
                  return (
                    <button key={w.id}
                      onClick={() => setWorkloadId(w.id)}
                      className={`text-left rounded border p-2 transition ${active ? "border-sky-500/50 bg-sky-500/10" : "border-white/10 bg-white/[0.02] hover:bg-white/[0.05]"}`}>
                      <div className="flex items-center justify-between">
                        <div className="text-[12px] font-semibold text-white/90">{w.name}</div>
                        <div className="text-[10px] text-white/50 font-mono">{w.size} req · {w.distinct_intents} intents</div>
                      </div>
                      <div className="text-[10px] text-white/50 mt-1">{w.description}</div>
                    </button>
                  );
                })}
              </div>
            </div>
            <Separator className="bg-white/10" />
            {/* Policy pills */}
            <div>
              <Label className="text-[10px] uppercase tracking-widest text-white/50 mb-2 block">Eviction policy</Label>
              <div className="flex flex-wrap gap-1.5">
                {["lru", "lfu", "fifo", "sdiv"].map(p => (
                  <PolicyChip key={p} policy={p} active={policy === p} onClick={() => setPolicy(p)} />
                ))}
              </div>
              {policies.find(p => p.id === policy) && (
                <p className="text-[11px] text-white/50 mt-2">{policies.find(p => p.id === policy).description}</p>
              )}
            </div>
            {/* Threshold slider */}
            <div>
              <div className="flex items-center justify-between mb-1">
                <Label className="text-[10px] uppercase tracking-widest text-white/50">Similarity threshold</Label>
                <span className="text-xs text-white/80 tabular-nums">{threshold.toFixed(3)}</span>
              </div>
              <Slider value={[threshold * 100]} onValueChange={([v]) => setThreshold(v / 100)}
                min={50} max={99} step={1} />
              <div className="flex justify-between text-[9px] text-white/40 mt-1"><span>0.50 (loose)</span><span>0.99 (strict)</span></div>
            </div>
            {/* Capacity + TTL */}
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label className="text-[10px] uppercase tracking-widest text-white/50 mb-1 block">Capacity</Label>
                <Input value={capacity}
                  onChange={(e) => setCapacity(Math.max(1, parseInt(e.target.value.replace(/[^0-9]/g, "") || "1", 10)))}
                  className="bg-white/[0.03] border-white/10 text-white text-xs h-8" />
              </div>
              <div>
                <Label className="text-[10px] uppercase tracking-widest text-white/50 mb-1 block">TTL (days)</Label>
                <Input value={ttlDays}
                  onChange={(e) => setTtlDays(Math.max(1, parseInt(e.target.value.replace(/[^0-9]/g, "") || "1", 10)))}
                  className="bg-white/[0.03] border-white/10 text-white text-xs h-8" />
              </div>
            </div>
            <Separator className="bg-white/10" />
            <div className="flex items-center gap-2">
              <Button onClick={runSim} disabled={busy}
                className="bg-sky-600 hover:bg-sky-500 text-white text-xs h-8 flex-1">
                <Play className="w-3.5 h-3.5 mr-1" /> Rerun simulation
              </Button>
              {busy && <span className="text-[10px] text-white/50 animate-pulse">running…</span>}
            </div>
          </CardContent>
        </Card>

        {/* Sweep curve */}
        <Card className="bg-white/[0.02] border-white/10 lg:col-span-2">
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between">
              <CardTitle className="text-white text-base flex items-center gap-2">
                <Gauge className="w-4 h-4 text-emerald-300" />
                Threshold sensitivity · <span className="text-white/50 uppercase text-[10px] tracking-widest">{policy}</span>
              </CardTitle>
              <span className="text-[10px] text-white/40">click a band to snap · {currentWorkload?.size ?? 0} requests</span>
            </div>
          </CardHeader>
          <CardContent>
            <SweepCurve
              points={sweep?.curve?.points ?? []}
              activeThreshold={sweep?.curve?.points?.reduce((closest, p) =>
                Math.abs(p.threshold - threshold) < Math.abs(closest - threshold) ? p.threshold : closest,
                sweep?.curve?.points?.[0]?.threshold ?? 0)}
              onPickThreshold={(t) => setThreshold(t)}
            />
            <div className="text-[11px] text-white/50 mt-1">
              As the threshold tightens: hit rate falls, savings fall, quality-risk collapses.
              The right pick is where the emerald savings line has fallen just enough to bring rose quality-risk under your ceiling.
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Policy grid + Clusters ──────────────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Card className="bg-white/[0.02] border-white/10 lg:col-span-2">
          <CardHeader className="pb-2">
            <CardTitle className="text-white text-base flex items-center gap-2">
              <Layers className="w-4 h-4 text-fuchsia-300" />
              Policy × Threshold grid · savings
              <span className="text-[10px] uppercase tracking-widest text-white/40 ml-1">
                cell = savings %, subline = hit % / risk %
              </span>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <PolicyGrid
              grid={sweep?.grid?.grid}
              thresholds={sweep?.grid?.thresholds ?? []}
              activePolicy={policy}
              activeThreshold={threshold}
              onPick={snapTo}
            />
          </CardContent>
        </Card>

        <Card className="bg-white/[0.02] border-white/10">
          <CardHeader className="pb-2">
            <CardTitle className="text-white text-base flex items-center gap-2">
              <ScanSearch className="w-4 h-4 text-sky-300" />
              Intent clusters
              <span className="text-[10px] uppercase tracking-widest text-white/40 ml-1">@ threshold {threshold.toFixed(2)}</span>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-[11px] text-white/60 mb-3 flex items-center justify-between">
              <div>
                <span className="text-white/90 font-semibold">{clusters?.cluster_count ?? 0}</span> clusters ·
                <span className="text-white/70"> {clusters?.singleton_count ?? 0} singletons</span>
              </div>
              <div>head 20% share <span className="text-white/90 font-semibold tabular-nums">{fmtPct(clusters?.head_share_pct)}</span></div>
            </div>
            <ScrollArea className="h-80 pr-2">
              <ClusterBars clusters={clusters?.clusters ?? []} />
            </ScrollArea>
          </CardContent>
        </Card>
      </div>

      {/* Top intents + Trace ────────────────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Card className="bg-white/[0.02] border-white/10">
          <CardHeader className="pb-2">
            <CardTitle className="text-white text-base flex items-center gap-2">
              <Rows3 className="w-4 h-4 text-emerald-300" /> Top intents
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-1.5">
              {(sim?.top_intents ?? []).slice(0, 8).map((r) => {
                const barColor = r.hit_rate > 0.7 ? "#34d399" : r.hit_rate > 0.4 ? "#38bdf8" : "#f59e0b";
                return (
                  <div key={r.intent} className="flex items-center gap-2">
                    <div className="w-32 text-[11px] text-white/85 truncate">{r.intent}</div>
                    <div className="flex-1 min-w-0">
                      <div className="h-1.5 rounded-full bg-white/5 overflow-hidden">
                        <div className="h-full rounded-full" style={{ width: `${r.hit_rate * 100}%`, background: barColor }} />
                      </div>
                    </div>
                    <div className="w-20 text-right text-[10px] font-mono text-white/60 tabular-nums shrink-0">
                      {r.hits}/{r.total} · {fmtPct(r.hit_rate, 0)}
                    </div>
                  </div>
                );
              })}
            </div>
          </CardContent>
        </Card>

        <Card className="bg-white/[0.02] border-white/10 lg:col-span-2">
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between">
              <CardTitle className="text-white text-base flex items-center gap-2">
                <Repeat className="w-4 h-4 text-sky-300" /> Trace tail
                <span className="text-[10px] uppercase tracking-widest text-white/40 ml-1">last {sim?.trace_tail?.length ?? 0} events</span>
              </CardTitle>
              <div className="text-[10px] text-white/50 tabular-nums">
                cache size <span className="text-white/85 font-semibold">{sim?.final_cache_size ?? 0}</span> ·
                evictions <span className="text-white/85 font-semibold">{sim?.totals?.evictions ?? 0}</span> ·
                TTL evicts <span className="text-white/85 font-semibold">{sim?.totals?.ttl_evictions ?? 0}</span>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            <ScrollArea className="h-72 pr-2">
              <TraceTail trace={sim?.trace_tail ?? []} />
            </ScrollArea>
          </CardContent>
        </Card>
      </div>

      {/* Compiled JSON ───────────────────────────────────────────────── */}
      <Card className="bg-white/[0.02] border-white/10">
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <CardTitle className="text-white text-base flex items-center gap-2">
              <Fingerprint className="w-4 h-4 text-fuchsia-300" /> Compiled cache
              {compiled && (
                <span className="text-[10px] uppercase tracking-widest text-white/40 ml-1 font-mono">
                  id {compiled.cache_id}
                </span>
              )}
            </CardTitle>
            <div className="flex items-center gap-2">
              <Button size="sm" variant="ghost"
                className="h-7 text-[11px] text-white/70 hover:text-white"
                onClick={() => copy(JSON.stringify(compiled, null, 2), "json")}>
                {copyState === "json" ? <ClipboardCheck className="w-3.5 h-3.5 mr-1 text-emerald-300" /> : <Copy className="w-3.5 h-3.5 mr-1" />}
                Copy JSON
              </Button>
              <Button size="sm" variant="ghost"
                className="h-7 text-[11px] text-white/70 hover:text-white"
                onClick={() => copy(markdown, "md")}>
                {copyState === "md" ? <ClipboardCheck className="w-3.5 h-3.5 mr-1 text-emerald-300" /> : <Copy className="w-3.5 h-3.5 mr-1" />}
                Copy Markdown
              </Button>
              <Button size="sm" variant="ghost"
                className="h-7 text-[11px] text-white/70 hover:text-white"
                onClick={() => download(`cache-${compiled?.cache_id || "config"}.md`, markdown)}>
                <Download className="w-3.5 h-3.5 mr-1" /> Download
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          {/* Pipeline preview */}
          <div>
            <div className="text-[10px] uppercase tracking-widest text-white/50 mb-2">Pipeline</div>
            <div className="space-y-1.5">
              {(compiled?.pipeline ?? []).map((s) => (
                <div key={s.step} className={`flex items-center gap-2 p-2 rounded border ${activePolicyHue.bg} ${activePolicyHue.border}`}>
                  <div className="w-5 h-5 rounded-full bg-white/10 text-white/80 text-[10px] font-bold flex items-center justify-center">{s.step}</div>
                  <div className="flex-1">
                    <div className="text-[11px] font-semibold text-white/90">{s.action}</div>
                    <div className="text-[10px] text-white/50">{s.notes}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
          {/* Expected block */}
          <div>
            <div className="text-[10px] uppercase tracking-widest text-white/50 mb-2">Expected on this workload</div>
            {compiled?.expected ? (
              <div className="grid grid-cols-2 gap-2">
                <StatTile icon={Percent} label="Hit rate" value={fmtPct(compiled.expected.hit_rate, 1)} hue="text-sky-200" />
                <StatTile icon={Activity} label="Quality risk" value={fmtPct(compiled.expected.quality_risk_pct, 1)} hue="text-emerald-200" />
                <StatTile icon={Timer} label="Avg latency" value={fmtMS(compiled.expected.avg_latency_ms)} hue="text-white/85" />
                <StatTile icon={DollarSign} label="Monthly cost" value={fmtUSD(compiled.expected.monthly_cost_usd, 2)} hue="text-white/85" />
                <StatTile icon={TrendingDown} label="Monthly savings" value={fmtUSD(compiled.expected.monthly_savings_usd, 2)} hue="text-emerald-200" />
                <StatTile icon={DollarSign} label="Monthly baseline" value={fmtUSD(compiled.expected.monthly_baseline_usd, 2)} hue="text-white/70" />
              </div>
            ) : (
              <div className="text-white/40 text-sm">Compile again with a workload to see expected metrics.</div>
            )}
            <div className="mt-3 text-[10px] text-white/40 leading-relaxed">
              Embedding: <span className="text-white/70 font-mono">{compiled?.embedding?.kind}</span> ·
              dim <span className="text-white/70 font-mono">{compiled?.embedding?.dim}</span>.
              Swap for a production embedder — the simulator's cost / hit ratios carry over.
            </div>
          </div>
          {/* JSON */}
          <div>
            <div className="text-[10px] uppercase tracking-widest text-white/50 mb-2">JSON</div>
            <ScrollArea className="h-80 rounded border border-white/10 bg-black/30">
              <pre className="text-[10px] leading-relaxed text-white/80 p-3 font-mono whitespace-pre">
                {compiled ? JSON.stringify(compiled, null, 2) : ""}
              </pre>
            </ScrollArea>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
