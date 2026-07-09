import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Radio,
  Sparkles,
  Play,
  Plus,
  Trash2,
  Search,
  DollarSign,
  ListChecks,
  Activity,
  Timer,
  Zap,
  Layers,
  ArrowRight,
  ArrowDownRight,
  ShieldCheck,
  TrendingDown,
  GitBranch,
  Gauge,
  Route,
  ChevronRight,
  Wand2,
  Coffee,
} from "lucide-react";
import { toast } from "sonner";
import ApiService from "../services/api";

// ─── Constants ────────────────────────────────────────────────────────────

const TIER_META = {
  flagship:  { label: "Flagship",  hue: "#8b5cf6", chip: "bg-violet-100 text-violet-700",  soft: "bg-violet-50",  ring: "ring-violet-200",  dot: "bg-violet-500"  },
  premium:   { label: "Premium",   hue: "#0284c7", chip: "bg-sky-100 text-sky-700",         soft: "bg-sky-50",      ring: "ring-sky-200",      dot: "bg-sky-500"      },
  mid:       { label: "Mid",       hue: "#0d9488", chip: "bg-teal-100 text-teal-700",       soft: "bg-teal-50",     ring: "ring-teal-200",     dot: "bg-teal-500"     },
  efficient: { label: "Efficient", hue: "#10b981", chip: "bg-emerald-100 text-emerald-700", soft: "bg-emerald-50",  ring: "ring-emerald-200",  dot: "bg-emerald-500"  },
  budget:    { label: "Budget",    hue: "#f59e0b", chip: "bg-amber-100 text-amber-700",     soft: "bg-amber-50",    ring: "ring-amber-200",    dot: "bg-amber-500"    },
  unknown:   { label: "?",         hue: "#94a3b8", chip: "bg-slate-100 text-slate-600",     soft: "bg-slate-50",    ring: "ring-slate-200",    dot: "bg-slate-400"    },
};

const PROVIDER_MODELS = {
  OpenAI:    ["gpt-4-turbo", "gpt-4o", "gpt-4o-mini", "gpt-3.5-turbo"],
  Anthropic: ["claude-3-5-sonnet", "claude-3-5-haiku", "claude-3-haiku"],
  Google:    ["gemini-1.5-pro", "gemini-1.5-flash"],
};

const GATE_TYPE_META = {
  composite:   { label: "Composite quality", hue: "#8b5cf6", help: "accept if replay quality ≥ threshold" },
  length:      { label: "Output length",     hue: "#0284c7", help: "accept if output_tokens ≥ threshold" },
  coverage:    { label: "Keyword coverage",  hue: "#0d9488", help: "accept if keyword hits ≥ threshold" },
  consistency: { label: "Set consistency",   hue: "#f59e0b", help: "accept if replay stdev ≤ threshold AND mean ≥ 60" },
};

// ─── Helpers ──────────────────────────────────────────────────────────────

const fmtNum = (n, d = 1) => (n == null ? "—" : Number(n).toFixed(d));
const fmtPct = (n) => (n == null ? "—" : `${Number(n).toFixed(0)}%`);
const fmtPct1 = (n) => (n == null ? "—" : `${Number(n).toFixed(1)}%`);

const fmtMoney = (n) => {
  if (n == null) return "—";
  const v = Number(n);
  if (Math.abs(v) >= 1000) return `$${(v / 1000).toFixed(1)}k`;
  if (Math.abs(v) >= 1) return `$${v.toFixed(2)}`;
  if (Math.abs(v) >= 0.001) return `$${v.toFixed(4)}`;
  if (v === 0) return "$0";
  return `$${v.toExponential(1)}`;
};

const fmtCost = (n) => {
  if (n == null) return "—";
  const v = Number(n);
  if (v === 0) return "$0";
  if (v >= 0.01) return `$${v.toFixed(4)}`;
  if (v >= 0.0001) return `$${v.toFixed(5)}`;
  return `$${v.toExponential(2)}`;
};

const scoreHue = (v) => {
  if (v == null) return "#94a3b8";
  const clipped = Math.max(0, Math.min(100, Number(v)));
  return `hsl(${Math.round(clipped * 1.25)} 75% 48%)`;
};

const fmtRel = (iso) => {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const diff = (Date.now() - d.getTime()) / 1000;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  if (diff < 86400 * 7) return `${Math.floor(diff / 86400)}d ago`;
  return d.toLocaleDateString();
};

const fmtLatency = (ms) => {
  if (ms == null) return "—";
  const v = Number(ms);
  if (v >= 1000) return `${(v / 1000).toFixed(2)}s`;
  return `${Math.round(v)}ms`;
};

// ─── Atoms ────────────────────────────────────────────────────────────────

const ScoreRing = ({ value, size = 100, label = "" }) => {
  const v = value == null ? null : Math.max(0, Math.min(100, Math.round(value)));
  const hue = v == null ? "#cbd5e1" : scoreHue(v);
  const deg = v == null ? 0 : v * 3.6;
  return (
    <div
      className="relative inline-flex items-center justify-center shrink-0"
      style={{
        width: size, height: size, borderRadius: "9999px",
        background: `conic-gradient(${hue} ${deg}deg, #e2e8f0 ${deg}deg)`,
      }}
    >
      <div
        className="bg-white rounded-full flex flex-col items-center justify-center shadow-inner"
        style={{ width: size - 14, height: size - 14 }}
      >
        <div className="text-xl font-black tabular-nums" style={{ color: hue }}>
          {v == null ? "—" : v}
        </div>
        {label && <div className="text-[9px] tracking-widest uppercase text-slate-500">{label}</div>}
      </div>
    </div>
  );
};

const StatTile = ({ label, value, sub, icon: Icon, tint = "slate" }) => (
  <div className={`bg-white rounded-lg border border-${tint}-200 shadow-sm px-3 py-2.5 min-w-0`}>
    <div className="flex items-center justify-between mb-1">
      <span className="text-[10px] uppercase tracking-widest text-slate-500">{label}</span>
      {Icon && <Icon className={`w-3.5 h-3.5 text-${tint}-500`} />}
    </div>
    <div className={`text-lg font-black tabular-nums text-${tint}-700 truncate`}>{value}</div>
    {sub && <div className="text-[10px] text-slate-500 mt-0.5 truncate">{sub}</div>}
  </div>
);

const TierChip = ({ tier }) => {
  const meta = TIER_META[tier] || TIER_META.unknown;
  return (
    <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-semibold ${meta.chip}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${meta.dot}`} />
      {meta.label}
    </span>
  );
};

const Bar = ({ value, max = 100, hue = "#8b5cf6", tone = "" }) => {
  const pct = max > 0 ? Math.max(0, Math.min(100, (Number(value) / max) * 100)) : 0;
  return (
    <div className={`h-1.5 rounded-full bg-slate-100 overflow-hidden ${tone}`}>
      <div style={{ width: `${pct}%`, background: hue }} className="h-full transition-all" />
    </div>
  );
};

// ─── Sankey-like cascade flow ────────────────────────────────────────────

const CascadeFlow = ({ picked, escalation }) => {
  if (!picked || picked.length === 0) {
    return (
      <div className="text-center text-slate-500 text-sm py-8">
        No levels picked — the cascade is empty. Click a level below to add it.
      </div>
    );
  }
  const rows = picked.map((lv) => ({
    key: lv.key,
    label: lv.model,
    tier: lv.tier,
    reach: lv.p_reach ?? 0,
    terminate: lv.p_terminate ?? 0,
    escalate: Math.max(0, (lv.p_reach ?? 0) - (lv.p_terminate ?? 0)),
    quality: lv.quality,
    cost: lv.cost_per_call,
    pass: lv.pass_rate ?? 0,
  }));
  return (
    <div className="space-y-1.5">
      {rows.map((r, i) => {
        const isLast = i === rows.length - 1;
        const meta = TIER_META[r.tier] || TIER_META.unknown;
        return (
          <div key={r.key}>
            <div
              className="relative rounded-lg border shadow-sm overflow-hidden"
              style={{ borderColor: meta.hue + "33" }}
            >
              {/* Reach fill */}
              <div
                className="absolute inset-y-0 left-0 opacity-15"
                style={{ width: `${(r.reach * 100).toFixed(1)}%`, background: meta.hue, transition: "width 260ms ease" }}
              />
              {/* Terminate fill */}
              <div
                className="absolute inset-y-0 left-0 opacity-45"
                style={{ width: `${(r.terminate * 100).toFixed(1)}%`, background: meta.hue, transition: "width 260ms ease" }}
              />
              <div className="relative px-3 py-2 flex items-center gap-3">
                <div
                  className="w-7 h-7 rounded-full flex items-center justify-center text-white text-[11px] font-black shrink-0"
                  style={{ background: meta.hue }}
                >
                  {i + 1}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <TierChip tier={r.tier} />
                    <span className="font-semibold text-slate-900 truncate">{r.label}</span>
                  </div>
                  <div className="text-[10px] text-slate-600 mt-0.5">
                    Q={fmtNum(r.quality)} · {fmtCost(r.cost)}/call · pass {fmtPct(r.pass * 100)}
                  </div>
                </div>
                <div className="flex flex-col items-end text-[10px] gap-0.5">
                  <div className="tabular-nums text-slate-700">
                    <span className="font-bold" style={{ color: meta.hue }}>{(r.reach * 100).toFixed(0)}%</span>
                    <span className="text-slate-500"> reach</span>
                  </div>
                  <div className="tabular-nums text-slate-700">
                    <span className="font-bold" style={{ color: "#10b981" }}>{(r.terminate * 100).toFixed(0)}%</span>
                    <span className="text-slate-500"> terminate</span>
                  </div>
                </div>
              </div>
            </div>
            {!isLast && (
              <div className="flex items-center gap-2 pl-4 py-1">
                <ArrowDownRight className="w-3.5 h-3.5 text-rose-400" />
                <span className="text-[10px] text-rose-600 font-semibold tabular-nums">
                  {fmtPct(r.escalate * 100)} escalate to next
                </span>
                <div className="flex-1 h-px bg-rose-200/60" />
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
};

// ─── Level card (roster row) ────────────────────────────────────────────

const LevelRow = ({ lv, onToggle, flagshipCost, monthlyCalls, isFlagship, isCheap }) => {
  const meta = TIER_META[lv.tier] || TIER_META.unknown;
  const qHue = scoreHue(lv.quality || 0);
  const passPct = Math.round((lv.pass_rate || 0) * 100);
  const savedVsFlagship =
    flagshipCost && lv.cost_per_call != null
      ? Math.max(0, (flagshipCost - lv.cost_per_call) * (monthlyCalls || 1))
      : 0;
  return (
    <div
      className={`group relative border rounded-xl bg-white shadow-sm transition-all hover:shadow-md ${
        lv.picked ? "ring-2 ring-offset-1" : ""
      }`}
      style={{ borderColor: meta.hue + "33", ringColor: meta.hue }}
    >
      {/* Left-edge picked accent */}
      {lv.picked && (
        <div className="absolute inset-y-1 left-0 w-1 rounded-full" style={{ background: meta.hue }} />
      )}
      <div className="p-3 flex items-center gap-3">
        {/* Ordinal + toggle */}
        <button
          onClick={() => onToggle && onToggle(lv)}
          className={`w-8 h-8 rounded-full font-black text-[11px] flex items-center justify-center transition-all ${
            lv.picked ? "text-white shadow" : "text-slate-500 bg-slate-100 hover:bg-slate-200"
          }`}
          style={lv.picked ? { background: meta.hue } : {}}
          title={lv.picked ? "Remove from cascade" : "Add to cascade"}
        >
          {lv.ord + 1}
        </button>

        {/* Model + tier */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <TierChip tier={lv.tier} />
            <span className="text-sm font-bold text-slate-900 truncate">{lv.model}</span>
            {isFlagship && (
              <span className="text-[9px] uppercase tracking-widest bg-violet-100 text-violet-700 px-1 py-0.5 rounded font-semibold">
                Flagship
              </span>
            )}
            {isCheap && (
              <span className="text-[9px] uppercase tracking-widest bg-amber-100 text-amber-700 px-1 py-0.5 rounded font-semibold">
                Cheapest
              </span>
            )}
            {lv.picked && (
              <span className="text-[9px] uppercase tracking-widest bg-emerald-100 text-emerald-700 px-1 py-0.5 rounded font-semibold">
                In cascade
              </span>
            )}
          </div>
          <div className="text-[10px] text-slate-500 mt-0.5">{lv.provider}</div>
        </div>

        {/* Quality bar */}
        <div className="w-24 shrink-0">
          <div className="flex items-center justify-between mb-1 text-[10px] text-slate-500">
            <span>Q</span>
            <span className="tabular-nums font-bold" style={{ color: qHue }}>
              {fmtNum(lv.quality)}
            </span>
          </div>
          <Bar value={lv.quality || 0} max={100} hue={qHue} />
        </div>

        {/* Cost */}
        <div className="w-20 text-right shrink-0">
          <div className="text-[10px] text-slate-500">Cost/call</div>
          <div className="text-sm font-bold tabular-nums text-slate-800">
            {fmtCost(lv.cost_per_call)}
          </div>
        </div>

        {/* Latency */}
        <div className="w-16 text-right shrink-0">
          <div className="text-[10px] text-slate-500">Latency</div>
          <div className="text-sm font-bold tabular-nums text-slate-800">
            {fmtLatency(lv.latency_ms)}
          </div>
        </div>

        {/* Pass */}
        <div className="w-24 shrink-0">
          <div className="flex items-center justify-between mb-1 text-[10px] text-slate-500">
            <span>Pass</span>
            <span className="tabular-nums font-bold text-emerald-700">{passPct}%</span>
          </div>
          <Bar value={passPct} max={100} hue="#10b981" />
        </div>

        {/* Savings */}
        <div className="w-20 text-right shrink-0">
          <div className="text-[10px] text-slate-500">Save/mo</div>
          <div className="text-sm font-bold tabular-nums text-emerald-700">
            {fmtMoney(savedVsFlagship)}
          </div>
        </div>
      </div>
      {lv.rationale && (
        <div className="border-t bg-slate-50/60 px-3 py-1.5 text-[11px] text-slate-600 rounded-b-xl">
          {lv.rationale}
        </div>
      )}
    </div>
  );
};

// ─── Recommendation card ──────────────────────────────────────────────────

const RecCard = ({ title, subtitle, shape, kind, active, onApply }) => {
  const meta =
    kind === "balanced"
      ? { hue: "#8b5cf6", grad: "from-violet-50 to-fuchsia-50", ring: "ring-violet-300", icon: ShieldCheck }
      : kind === "cost_min"
      ? { hue: "#10b981", grad: "from-emerald-50 to-lime-50", ring: "ring-emerald-300", icon: TrendingDown }
      : { hue: "#0284c7", grad: "from-sky-50 to-cyan-50", ring: "ring-sky-300", icon: Timer };
  const Icon = meta.icon;
  if (!shape) {
    return (
      <div className={`rounded-xl border border-dashed border-slate-300 bg-gradient-to-br ${meta.grad} p-3 opacity-60`}>
        <div className="flex items-center gap-2 mb-1">
          <Icon className="w-4 h-4" style={{ color: meta.hue }} />
          <div className="text-xs font-bold uppercase tracking-widest text-slate-700">{title}</div>
        </div>
        <div className="text-[11px] text-slate-500">{subtitle}</div>
        <div className="text-xs text-slate-400 mt-2 italic">No shape fits the current constraints.</div>
      </div>
    );
  }
  return (
    <button
      onClick={() => onApply && onApply(shape)}
      className={`text-left rounded-xl border bg-gradient-to-br ${meta.grad} p-3 shadow-sm hover:shadow-md transition-all ${
        active ? `ring-2 ${meta.ring}` : ""
      }`}
      style={{ borderColor: meta.hue + "55" }}
    >
      <div className="flex items-center justify-between mb-1">
        <div className="flex items-center gap-2">
          <Icon className="w-4 h-4" style={{ color: meta.hue }} />
          <div className="text-xs font-bold uppercase tracking-widest text-slate-700">{title}</div>
        </div>
        <span
          className="text-[9px] uppercase tracking-widest text-white px-1.5 py-0.5 rounded font-semibold"
          style={{ background: meta.hue }}
        >
          {shape.size} lvl
        </span>
      </div>
      <div className="text-[11px] text-slate-600 mb-2">{subtitle}</div>
      <div className="grid grid-cols-3 gap-1.5 mb-2">
        <div className="bg-white/70 rounded px-1.5 py-1">
          <div className="text-[9px] uppercase text-slate-500">Kept</div>
          <div className="text-sm font-black tabular-nums" style={{ color: meta.hue }}>
            {fmtPct1(shape.quality_kept_pct)}
          </div>
        </div>
        <div className="bg-white/70 rounded px-1.5 py-1">
          <div className="text-[9px] uppercase text-slate-500">Save/mo</div>
          <div className="text-sm font-black tabular-nums text-emerald-700">
            {fmtMoney(shape.monthly_savings)}
          </div>
        </div>
        <div className="bg-white/70 rounded px-1.5 py-1">
          <div className="text-[9px] uppercase text-slate-500">Esc</div>
          <div className="text-sm font-black tabular-nums text-rose-600">
            {fmtPct(shape.escalation_rate * 100)}
          </div>
        </div>
      </div>
      <div className="text-[10px] text-slate-600 font-mono truncate">
        {(shape.keys || []).map((k) => k.split(":").pop()).join(" → ")}
      </div>
    </button>
  );
};

// ─── Cost/Quality mini scatter ────────────────────────────────────────────

const ScanScatter = ({ scan = [], flagshipCost, flagshipQuality, activeShape }) => {
  if (!scan || scan.length === 0) return null;
  const width = 620, height = 200, pad = { l: 42, r: 12, t: 10, b: 26 };

  const costs = scan.map((s) => Math.max(1e-8, s.expected_cost));
  const quals = scan.map((s) => s.expected_quality);
  const logCosts = costs.map((c) => Math.log10(c));
  const xMin = Math.min(...logCosts) - 0.1;
  const xMax = Math.max(...logCosts) + 0.1;
  const yMin = Math.max(0, Math.min(...quals) - 3);
  const yMax = Math.min(100, Math.max(...quals) + 3);

  const sx = (lc) => pad.l + ((lc - xMin) / (xMax - xMin || 1)) * (width - pad.l - pad.r);
  const sy = (q) => pad.t + (1 - (q - yMin) / (yMax - yMin || 1)) * (height - pad.t - pad.b);

  const activeKey = activeShape ? (activeShape.keys || []).join("|") : null;

  return (
    <div className="border rounded-xl bg-white overflow-hidden shadow-sm">
      <div className="px-3 py-2 bg-slate-50 border-b flex items-center justify-between">
        <div className="flex items-center gap-2 text-xs text-slate-600 font-semibold uppercase tracking-widest">
          <Layers className="w-3.5 h-3.5" />
          Subset scan · {scan.length} cascade shapes
        </div>
        <div className="text-[10px] text-slate-500">log-cost · linear quality</div>
      </div>
      <svg viewBox={`0 0 ${width} ${height}`} className="w-full">
        {/* Grid */}
        {[0, 0.25, 0.5, 0.75, 1].map((f, i) => {
          const y = pad.t + f * (height - pad.t - pad.b);
          const yVal = yMax - f * (yMax - yMin);
          return (
            <g key={`g${i}`}>
              <line x1={pad.l} x2={width - pad.r} y1={y} y2={y} stroke="#e2e8f0" strokeDasharray="2,3" />
              <text x={pad.l - 4} y={y + 3} textAnchor="end" fontSize="9" fill="#94a3b8">
                {yVal.toFixed(0)}
              </text>
            </g>
          );
        })}
        {/* Flagship reference line (vertical at flagship cost) */}
        {flagshipCost && (
          <>
            <line
              x1={sx(Math.log10(Math.max(1e-8, flagshipCost)))}
              x2={sx(Math.log10(Math.max(1e-8, flagshipCost)))}
              y1={pad.t}
              y2={height - pad.b}
              stroke="#c026d3"
              strokeDasharray="3,3"
              opacity="0.6"
            />
            <line
              x1={pad.l}
              x2={width - pad.r}
              y1={sy(flagshipQuality)}
              y2={sy(flagshipQuality)}
              stroke="#c026d3"
              strokeDasharray="3,3"
              opacity="0.6"
            />
          </>
        )}
        {/* Dots */}
        {scan.map((s, i) => {
          const isActive = activeKey && (s.keys || []).join("|") === activeKey;
          const rr = isActive ? 6 : Math.max(2.5, 2.5 + s.size * 0.3);
          const hue =
            s.size === 1 ? "#94a3b8"
              : s.size === 2 ? "#0d9488"
              : s.size === 3 ? "#0284c7"
              : "#8b5cf6";
          return (
            <g key={i}>
              <circle
                cx={sx(logCosts[i])}
                cy={sy(quals[i])}
                r={rr}
                fill={hue}
                fillOpacity={isActive ? 1 : 0.55}
                stroke={isActive ? "#facc15" : "none"}
                strokeWidth={isActive ? 2 : 0}
              />
            </g>
          );
        })}
        {/* Axis labels */}
        <text x={width / 2} y={height - 5} textAnchor="middle" fontSize="9" fill="#64748b">
          expected cost / call →
        </text>
        <text x={12} y={pad.t + 10} fontSize="9" fill="#64748b">
          quality ↑
        </text>
      </svg>
      <div className="px-3 py-1.5 border-t bg-slate-50 flex items-center gap-3 text-[10px] text-slate-500">
        <span className="inline-flex items-center gap-1">
          <span className="w-2 h-2 rounded-full bg-slate-400" />1-level
        </span>
        <span className="inline-flex items-center gap-1">
          <span className="w-2 h-2 rounded-full bg-teal-500" />2-level
        </span>
        <span className="inline-flex items-center gap-1">
          <span className="w-2 h-2 rounded-full bg-sky-500" />3-level
        </span>
        <span className="inline-flex items-center gap-1">
          <span className="w-2 h-2 rounded-full bg-violet-500" />4+
        </span>
        <span className="ml-auto">
          <span className="inline-flex items-center gap-1">
            <span className="w-2 h-2 border border-fuchsia-500 border-dashed rounded-full" />
            flagship reference
          </span>
        </span>
      </div>
    </div>
  );
};

// ─── Editor modal ─────────────────────────────────────────────────────────

const EMPTY_FORM = {
  name: "",
  description: "",
  system_prompt: "",
  user_prompt: "",
  temperature: 0.4,
  top_p: 1.0,
  n_replays: 4,
  monthly_calls: 50000,
  gate_type: "composite",
  gate_threshold: 55.0,
  quality_floor: 60.0,
  latency_ceiling_ms: 3500,
  dryrun: true,
  roster: [
    { provider: "Anthropic", model: "claude-3-haiku" },
    { provider: "OpenAI",    model: "gpt-4o-mini" },
    { provider: "Anthropic", model: "claude-3-5-haiku" },
    { provider: "OpenAI",    model: "gpt-3.5-turbo" },
    { provider: "Google",    model: "gemini-1.5-pro" },
    { provider: "OpenAI",    model: "gpt-4o" },
    { provider: "OpenAI",    model: "gpt-4-turbo" },
  ],
};

const RelayEditor = ({ open, onClose, onCreated, defaults }) => {
  const [form, setForm] = useState(EMPTY_FORM);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (open) {
      setForm(EMPTY_FORM);
    }
  }, [open]);

  if (!open) return null;

  const addToRoster = (provider, model) => {
    setForm((f) => {
      if (f.roster.some((r) => r.provider === provider && r.model === model)) return f;
      return { ...f, roster: [...f.roster, { provider, model }] };
    });
  };
  const removeFromRoster = (i) => {
    setForm((f) => ({ ...f, roster: f.roster.filter((_, idx) => idx !== i) }));
  };

  const submit = async () => {
    if (!form.name.trim()) return toast.error("Name is required");
    if (!form.user_prompt.trim()) return toast.error("User prompt is required");
    if (form.roster.length < 2) return toast.error("Roster needs at least 2 models");
    setSaving(true);
    try {
      const res = await ApiService.createRelay(form);
      if (res?.success) {
        toast.success("Relay run queued");
        onCreated && onCreated(res.relay);
        onClose && onClose();
      } else {
        toast.error(res?.error || "Failed to create relay run");
      }
    } catch (e) {
      toast.error(String(e));
    } finally {
      setSaving(false);
    }
  };

  const gateMeta = GATE_TYPE_META[form.gate_type] || GATE_TYPE_META.composite;

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-2xl max-w-4xl w-full max-h-[90vh] overflow-hidden flex flex-col">
        <div className="px-5 py-4 bg-gradient-to-r from-emerald-500 via-teal-500 to-sky-500 text-white flex items-center justify-between">
          <div>
            <div className="text-xs uppercase tracking-widest opacity-90">Relay · New cascade design</div>
            <div className="text-lg font-black">Design a router for this prompt</div>
          </div>
          <Button variant="ghost" onClick={onClose} className="text-white hover:bg-white/20">
            Close
          </Button>
        </div>
        <div className="flex-1 overflow-auto p-5 space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label className="text-xs">Name</Label>
              <Input
                value={form.name}
                onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                placeholder="e.g. Fintech triage cascade"
              />
            </div>
            <div>
              <Label className="text-xs">Description</Label>
              <Input
                value={form.description}
                onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
                placeholder="One line, shown in the runs list"
              />
            </div>
          </div>
          <div>
            <Label className="text-xs">System prompt</Label>
            <Textarea
              rows={4}
              value={form.system_prompt}
              onChange={(e) => setForm((f) => ({ ...f, system_prompt: e.target.value }))}
              placeholder="Full role, constraints, output shape…"
            />
          </div>
          <div>
            <Label className="text-xs">User prompt</Label>
            <Textarea
              rows={3}
              value={form.user_prompt}
              onChange={(e) => setForm((f) => ({ ...f, user_prompt: e.target.value }))}
              placeholder="A representative live message…"
            />
          </div>

          <Separator />

          <div>
            <Label className="text-xs mb-1 block">Model roster (cost-ordered automatically)</Label>
            <div className="border rounded-lg bg-slate-50 p-2 space-y-2">
              <div className="flex flex-wrap gap-1.5">
                {form.roster.map((r, i) => (
                  <span
                    key={`${r.provider}:${r.model}:${i}`}
                    className="inline-flex items-center gap-1 bg-white border rounded px-2 py-0.5 text-xs shadow-sm"
                  >
                    <span className="text-slate-500 font-mono text-[10px]">{r.provider}</span>
                    <span className="font-semibold">{r.model}</span>
                    <button
                      onClick={() => removeFromRoster(i)}
                      className="text-slate-400 hover:text-rose-600 text-sm leading-none"
                    >
                      ×
                    </button>
                  </span>
                ))}
              </div>
              <div className="flex flex-wrap gap-1">
                {Object.entries(PROVIDER_MODELS).flatMap(([prov, models]) =>
                  models.map((m) => {
                    const already = form.roster.some((r) => r.provider === prov && r.model === m);
                    return (
                      <button
                        key={`${prov}:${m}`}
                        onClick={() => addToRoster(prov, m)}
                        disabled={already}
                        className={`text-[10px] px-1.5 py-0.5 rounded border ${
                          already
                            ? "bg-slate-100 text-slate-400 border-slate-200"
                            : "bg-white hover:bg-emerald-50 text-slate-700 border-slate-300"
                        }`}
                      >
                        + {m}
                      </button>
                    );
                  })
                )}
              </div>
            </div>
          </div>

          <Separator />

          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label className="text-xs">Gate</Label>
              <Select
                value={form.gate_type}
                onValueChange={(v) => {
                  const dflts = defaults?.gate_thresholds || {};
                  setForm((f) => ({ ...f, gate_type: v, gate_threshold: dflts[v] ?? f.gate_threshold }));
                }}
              >
                <SelectTrigger className="bg-white">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {Object.entries(GATE_TYPE_META).map(([k, v]) => (
                    <SelectItem key={k} value={k}>
                      {v.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <div className="text-[10px] text-slate-500 mt-1">{gateMeta.help}</div>
            </div>
            <div>
              <div className="flex items-center justify-between">
                <Label className="text-xs">Gate threshold</Label>
                <span className="text-xs font-mono bg-slate-100 px-2 py-0.5 rounded tabular-nums">
                  {form.gate_threshold}
                </span>
              </div>
              <Slider
                value={[form.gate_threshold]}
                onValueChange={([v]) => setForm((f) => ({ ...f, gate_threshold: v }))}
                min={form.gate_type === "coverage" ? 1 : form.gate_type === "length" ? 20 : 0}
                max={form.gate_type === "composite" ? 100 : form.gate_type === "consistency" ? 40 : form.gate_type === "coverage" ? 14 : 600}
                step={form.gate_type === "coverage" ? 1 : 1}
                className="mt-2"
              />
            </div>
            <div>
              <div className="flex items-center justify-between">
                <Label className="text-xs">n replays / model</Label>
                <span className="text-xs font-mono bg-slate-100 px-2 py-0.5 rounded tabular-nums">
                  {form.n_replays}
                </span>
              </div>
              <Slider
                value={[form.n_replays]}
                onValueChange={([v]) => setForm((f) => ({ ...f, n_replays: v }))}
                min={2}
                max={8}
                step={1}
                className="mt-2"
              />
            </div>
            <div>
              <Label className="text-xs">Monthly calls</Label>
              <Input
                type="number"
                min={100}
                value={form.monthly_calls}
                onChange={(e) => setForm((f) => ({ ...f, monthly_calls: Number(e.target.value) || 0 }))}
              />
            </div>
            <div>
              <Label className="text-xs">Quality floor (0-100)</Label>
              <Input
                type="number"
                min={0}
                max={100}
                value={form.quality_floor ?? ""}
                onChange={(e) => setForm((f) => ({ ...f, quality_floor: e.target.value === "" ? null : Number(e.target.value) }))}
              />
            </div>
            <div>
              <Label className="text-xs">Latency ceiling (ms)</Label>
              <Input
                type="number"
                min={0}
                value={form.latency_ceiling_ms ?? ""}
                onChange={(e) => setForm((f) => ({ ...f, latency_ceiling_ms: e.target.value === "" ? null : Number(e.target.value) }))}
              />
            </div>
          </div>
          <div className="flex items-center gap-3 pt-2">
            <Switch checked={form.dryrun} onCheckedChange={(v) => setForm((f) => ({ ...f, dryrun: v }))} />
            <div>
              <div className="text-xs font-semibold text-slate-800">
                Dryrun mode {form.dryrun ? "on" : "off"}
              </div>
              <div className="text-[10px] text-slate-500">
                {form.dryrun
                  ? "Uses deterministic synthetic replays. No API credits spent."
                  : "Fires real API calls. You'll be asked to confirm before it runs."}
              </div>
            </div>
          </div>
        </div>
        <div className="border-t bg-slate-50 px-5 py-3 flex items-center justify-end gap-2">
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button
            onClick={submit}
            disabled={saving}
            className="bg-gradient-to-r from-emerald-500 to-sky-500 hover:from-emerald-600 hover:to-sky-600 text-white"
          >
            {saving ? "Queuing…" : "Queue run"}
          </Button>
        </div>
      </div>
    </div>
  );
};

// ─── Main studio ──────────────────────────────────────────────────────────

const RelayStudio = () => {
  const [defaults, setDefaults] = useState(null);
  const [runs, setRuns] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [current, setCurrent] = useState(null);
  const [loading, setLoading] = useState(false);
  const [q, setQ] = useState("");
  const [editorOpen, setEditorOpen] = useState(false);
  const [preview, setPreview] = useState(null);
  const [gateType, setGateType] = useState("composite");
  const [gateThreshold, setGateThreshold] = useState(55);
  const [monthlyCalls, setMonthlyCalls] = useState(50000);
  const [pickOverride, setPickOverride] = useState(null);
  const previewDebounceRef = useRef(null);

  const loadDefaults = useCallback(async () => {
    try {
      const r = await ApiService.relayDefaults();
      if (r?.success) setDefaults(r.defaults);
    } catch (_) {
      /* ignore */
    }
  }, []);

  const loadRuns = useCallback(async () => {
    try {
      const r = await ApiService.listRelays({ q });
      if (r?.success) {
        setRuns(r.relays || []);
      }
    } catch (_) {
      /* ignore */
    }
  }, [q]);

  const loadRun = useCallback(async (id) => {
    if (!id) {
      setCurrent(null);
      return;
    }
    setLoading(true);
    try {
      const r = await ApiService.getRelay(id);
      if (r?.success && r.relay) {
        setCurrent(r.relay);
        setGateType(r.relay.gate_type);
        setGateThreshold(r.relay.gate_threshold);
        setMonthlyCalls(r.relay.monthly_calls);
        setPreview(null);
        setPickOverride(null);
      }
    } catch (e) {
      toast.error(String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadDefaults();
  }, [loadDefaults]);

  useEffect(() => {
    loadRuns();
  }, [loadRuns]);

  useEffect(() => {
    if (selectedId) loadRun(selectedId);
  }, [selectedId, loadRun]);

  const seedIfEmpty = useCallback(async () => {
    if (runs.length > 0) return;
    try {
      const r = await ApiService.seedRelay();
      if (r?.success && r.relay) {
        toast.success("Seed cascade loaded");
        setSelectedId(r.relay.id);
        await loadRuns();
      }
    } catch (_) {
      /* ignore */
    }
  }, [runs, loadRuns]);

  useEffect(() => {
    if (defaults && runs && runs.length === 0) {
      seedIfEmpty();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [defaults, runs.length]);

  const runRelay = async () => {
    if (!current) return;
    try {
      const r = await ApiService.runRelay(current.id, { confirm_live: !current.dryrun });
      if (r?.success) {
        toast.success("Relay run finished");
        loadRun(current.id);
        loadRuns();
      } else {
        toast.error(r?.error || "run failed");
      }
    } catch (e) {
      toast.error(String(e));
    }
  };

  const deleteRun = async (id) => {
    if (!window.confirm("Delete this relay run?")) return;
    try {
      await ApiService.deleteRelay(id);
      toast.success("Deleted");
      if (selectedId === id) {
        setSelectedId(null);
        setCurrent(null);
      }
      loadRuns();
    } catch (e) {
      toast.error(String(e));
    }
  };

  // Live preview — re-simulate when gate / picks / calls change.
  const requestPreview = useCallback(
    (payload) => {
      if (!current) return;
      clearTimeout(previewDebounceRef.current);
      previewDebounceRef.current = setTimeout(async () => {
        try {
          const r = await ApiService.previewRelay(current.id, payload);
          if (r?.success) setPreview(r.preview);
        } catch (_) {
          /* ignore */
        }
      }, 220);
    },
    [current]
  );

  useEffect(() => {
    if (!current) return;
    requestPreview({
      gate_type: gateType,
      gate_threshold: gateThreshold,
      monthly_calls: monthlyCalls,
      picked_indexes: pickOverride,
    });
  }, [current, gateType, gateThreshold, monthlyCalls, pickOverride, requestPreview]);

  const filteredRuns = useMemo(() => {
    if (!q.trim()) return runs;
    const needle = q.toLowerCase();
    return runs.filter(
      (r) =>
        (r.name || "").toLowerCase().includes(needle) ||
        (r.description || "").toLowerCase().includes(needle)
    );
  }, [runs, q]);

  // Derive effective cascade (preview overrides persisted).
  const effectiveCascade = preview?.cascade || current?.summary?.cascade;
  const effectiveShapes = preview?.shapes || current?.summary?.shapes;
  const effectiveKept = preview?.quality_kept_pct ?? current?.quality_kept_pct;
  const effectiveSavings = preview?.monthly_savings ?? current?.monthly_savings;

  const levels = current?.levels || [];
  const orderedLevels = useMemo(
    () => [...levels].sort((a, b) => a.ord - b.ord),
    [levels]
  );

  // Overlay preview pass_rate/pick state onto ordered levels for display.
  const displayLevels = useMemo(() => {
    if (!preview) return orderedLevels;
    const pickSet = new Set(effectiveCascade?.picked_keys || []);
    const reachMap = new Map();
    const termMap = new Map();
    (effectiveCascade?.picked_keys || []).forEach((k, i) => {
      reachMap.set(k, effectiveCascade.p_reach[i]);
      termMap.set(k, effectiveCascade.p_terminate[i]);
    });
    return orderedLevels.map((lv) => {
      const key = `${lv.provider}:${lv.model}`;
      // Preview pass_rate is stored under `preview.cascade` but was
      // computed on the full level list. We piggy-back off the level rows
      // — they aren't sent back, so use stored ones for a plausible view.
      return {
        ...lv,
        picked: pickSet.has(key),
        p_reach: reachMap.get(key) ?? 0,
        p_terminate: termMap.get(key) ?? 0,
      };
    });
  }, [orderedLevels, preview, effectiveCascade]);

  const pickedLevels = useMemo(
    () => (displayLevels || []).filter((lv) => lv.picked),
    [displayLevels]
  );

  const flagshipKey = current?.summary?.flagship_key;
  const cheapKey = current?.summary?.cheap_key;
  const flagshipCost = current?.flagship_cost;
  const flagshipQuality = current?.flagship_quality;

  const toggleLevel = (lv) => {
    if (!current) return;
    const cur = new Set(pickedLevels.map((l) => l.ord));
    if (cur.has(lv.ord)) cur.delete(lv.ord);
    else cur.add(lv.ord);
    setPickOverride(Array.from(cur));
  };

  const applyShape = (shape) => {
    if (!shape) return;
    setPickOverride(shape.indexes || []);
  };

  const gateMeta = GATE_TYPE_META[gateType] || GATE_TYPE_META.composite;

  return (
    <div className="space-y-4">
      {/* Hero */}
      <div className="rounded-2xl overflow-hidden shadow-lg border border-emerald-100">
        <div className="bg-gradient-to-r from-emerald-500 via-teal-500 to-sky-600 px-5 py-4 text-white">
          <div className="flex items-center justify-between">
            <div>
              <div className="flex items-center gap-2 text-xs uppercase tracking-widest opacity-90">
                <Radio className="w-3.5 h-3.5" />
                Relay · Cascade Router Designer
                <span className="text-[9px] bg-white/25 rounded px-1 py-0.5 font-semibold">NEW</span>
              </div>
              <div className="text-lg font-black mt-0.5">
                Route cheap first, escalate on demand. Save real money.
              </div>
              <div className="text-[11px] opacity-90 mt-0.5 max-w-3xl">
                Frontier picks the best single model. Relay picks the best <em>chain</em>:
                a cheap model handles the easy cases, and only the hard ones fall through to your
                flagship. Deterministic dryrun, subset scan, gate slider, live preview.
              </div>
            </div>
            <div className="flex gap-2">
              <Button onClick={() => setEditorOpen(true)} className="bg-white text-emerald-700 hover:bg-emerald-50 font-bold">
                <Plus className="w-4 h-4 mr-1" /> New run
              </Button>
              <Button
                onClick={async () => {
                  const r = await ApiService.seedRelay();
                  if (r?.success) {
                    toast.success("Seed loaded");
                    setSelectedId(r.relay.id);
                    loadRuns();
                  }
                }}
                variant="outline"
                className="border-white/40 bg-white/10 text-white hover:bg-white/25"
              >
                <Coffee className="w-4 h-4 mr-1" /> Seed demo
              </Button>
            </div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-12 gap-4">
        {/* Left rail — saved runs */}
        <div className="col-span-3">
          <Card className="h-full">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm flex items-center gap-2">
                <Route className="w-4 h-4 text-emerald-600" /> Saved cascades
              </CardTitle>
            </CardHeader>
            <CardContent className="p-2 space-y-2">
              <div className="relative">
                <Search className="w-3.5 h-3.5 absolute left-2 top-1/2 -translate-y-1/2 text-slate-400" />
                <Input
                  value={q}
                  onChange={(e) => setQ(e.target.value)}
                  placeholder="Search…"
                  className="pl-7 h-8 text-xs"
                />
              </div>
              <ScrollArea className="h-[64vh] pr-1">
                <div className="space-y-1.5">
                  {filteredRuns.length === 0 && (
                    <div className="text-[11px] text-slate-500 italic p-2">
                      No runs yet. Click "Seed demo" or "New run".
                    </div>
                  )}
                  {filteredRuns.map((r) => {
                    const active = r.id === selectedId;
                    return (
                      <button
                        key={r.id}
                        onClick={() => setSelectedId(r.id)}
                        className={`w-full text-left p-2 rounded-lg border shadow-sm transition-all ${
                          active
                            ? "bg-emerald-50 border-emerald-300 ring-2 ring-emerald-200"
                            : "bg-white border-slate-200 hover:border-emerald-200"
                        }`}
                      >
                        <div className="flex items-center justify-between gap-1 mb-1">
                          <div className="text-xs font-bold truncate flex-1">{r.name}</div>
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              deleteRun(r.id);
                            }}
                            className="text-slate-400 hover:text-rose-600 shrink-0"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </div>
                        <div className="flex items-center gap-1 text-[10px] text-slate-500">
                          <span className="tabular-nums">{r.picked_levels || 0} lvl</span>
                          <span>·</span>
                          <span className="tabular-nums text-emerald-700 font-semibold">
                            {fmtMoney(r.monthly_savings)}
                          </span>
                          <span>·</span>
                          <span className="tabular-nums">{fmtPct(r.quality_kept_pct)} kept</span>
                        </div>
                        <div className="text-[10px] text-slate-400 mt-1">
                          {fmtRel(r.updated_at)} · {r.status}
                        </div>
                      </button>
                    );
                  })}
                </div>
              </ScrollArea>
            </CardContent>
          </Card>
        </div>

        {/* Main */}
        <div className="col-span-9 space-y-4">
          {!current && (
            <Card>
              <CardContent className="p-10 text-center text-slate-500">
                <div className="text-4xl mb-2">🚦</div>
                <div className="font-semibold mb-1">Pick a cascade to inspect</div>
                <div className="text-xs">Or click "Seed demo" for a deterministic sample run.</div>
              </CardContent>
            </Card>
          )}

          {current && (
            <>
              {/* Hero card — dual rings + metrics */}
              <Card>
                <CardContent className="p-4">
                  <div className="flex gap-5 items-start">
                    <div className="flex items-center gap-3">
                      <div className="flex flex-col items-center">
                        <ScoreRing value={effectiveCascade?.expected_quality} label="cascade" size={120} />
                        <div className="text-[10px] text-slate-500 mt-1 tabular-nums">
                          Q · {fmtNum(effectiveCascade?.expected_quality)}
                        </div>
                      </div>
                      <div className="flex flex-col items-center text-slate-400 pt-6">
                        <ChevronRight className="w-4 h-4" />
                        <div className="text-[9px] uppercase mt-1">vs</div>
                      </div>
                      <div className="flex flex-col items-center">
                        <ScoreRing value={flagshipQuality} label="flagship" size={90} />
                        <div className="text-[10px] text-slate-500 mt-1 tabular-nums">
                          Q · {fmtNum(flagshipQuality)}
                        </div>
                      </div>
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="text-lg font-black text-slate-900 truncate">{current.name}</div>
                      {current.description && (
                        <div className="text-xs text-slate-500 mt-0.5">{current.description}</div>
                      )}
                      <div className="grid grid-cols-4 gap-2 mt-3">
                        <StatTile
                          label="Cost / call"
                          value={fmtCost(effectiveCascade?.expected_cost)}
                          sub={`vs ${fmtCost(flagshipCost)} flagship`}
                          icon={DollarSign}
                          tint="emerald"
                        />
                        <StatTile
                          label="Save / mo"
                          value={fmtMoney(effectiveSavings)}
                          sub={`${(current.monthly_calls || 0).toLocaleString()} calls`}
                          icon={TrendingDown}
                          tint="teal"
                        />
                        <StatTile
                          label="Quality kept"
                          value={fmtPct1(effectiveKept)}
                          sub={`of ${current.summary?.flagship_key?.split(":").pop() || "flagship"}`}
                          icon={ShieldCheck}
                          tint="violet"
                        />
                        <StatTile
                          label="Escalation rate"
                          value={fmtPct((effectiveCascade?.escalation_rate || 0) * 100)}
                          sub={`p50 latency ${fmtLatency(effectiveCascade?.expected_latency)}`}
                          icon={Zap}
                          tint="rose"
                        />
                      </div>

                      {/* Actions strip */}
                      <div className="mt-3 flex flex-wrap gap-2">
                        <Button
                          size="sm"
                          onClick={runRelay}
                          className="bg-gradient-to-r from-emerald-500 to-teal-500 text-white hover:opacity-90"
                        >
                          <Play className="w-3.5 h-3.5 mr-1" /> Re-run
                        </Button>
                        <Button size="sm" variant="outline" onClick={() => setPickOverride(null)}>
                          <Wand2 className="w-3.5 h-3.5 mr-1" /> Reset picks
                        </Button>
                        {pickOverride && (
                          <span className="text-[10px] uppercase tracking-widest text-amber-700 bg-amber-100 px-2 py-1 rounded font-semibold self-center">
                            Preview mode · click reset to snap back
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                </CardContent>
              </Card>

              {/* Recommendations */}
              <div className="grid grid-cols-3 gap-3">
                <RecCard
                  title="Balanced"
                  subtitle="Keeps ≥95% quality"
                  kind="balanced"
                  shape={effectiveShapes?.balanced}
                  active={
                    effectiveCascade?.picked_keys?.join("|") ===
                    (effectiveShapes?.balanced?.keys || []).join("|")
                  }
                  onApply={applyShape}
                />
                <RecCard
                  title="Cost min"
                  subtitle={`Above quality floor ${current.quality_floor ?? "—"}`}
                  kind="cost_min"
                  shape={effectiveShapes?.cost_min}
                  active={
                    effectiveCascade?.picked_keys?.join("|") ===
                    (effectiveShapes?.cost_min?.keys || []).join("|")
                  }
                  onApply={applyShape}
                />
                <RecCard
                  title="Latency capped"
                  subtitle={`Under ${fmtLatency(current.latency_ceiling_ms)}`}
                  kind="latency_capped"
                  shape={effectiveShapes?.latency_capped}
                  active={
                    effectiveCascade?.picked_keys?.join("|") ===
                    (effectiveShapes?.latency_capped?.keys || []).join("|")
                  }
                  onApply={applyShape}
                />
              </div>

              {/* Gate controls */}
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm flex items-center gap-2">
                    <Gauge className="w-4 h-4 text-teal-600" />
                    Gate · {gateMeta.label}
                    <span className="ml-auto text-[10px] text-slate-500 font-normal">
                      {gateMeta.help}
                    </span>
                  </CardTitle>
                </CardHeader>
                <CardContent className="pt-1 space-y-3">
                  <div className="grid grid-cols-3 gap-3 items-center">
                    <div>
                      <Label className="text-[10px] uppercase tracking-widest text-slate-500">
                        Gate type
                      </Label>
                      <Select value={gateType} onValueChange={setGateType}>
                        <SelectTrigger className="bg-white">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {Object.entries(GATE_TYPE_META).map(([k, v]) => (
                            <SelectItem key={k} value={k}>
                              {v.label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    <div>
                      <div className="flex items-center justify-between">
                        <Label className="text-[10px] uppercase tracking-widest text-slate-500">
                          Threshold
                        </Label>
                        <span className="text-xs font-mono bg-slate-100 px-2 py-0.5 rounded tabular-nums">
                          {gateThreshold}
                        </span>
                      </div>
                      <Slider
                        value={[gateThreshold]}
                        onValueChange={([v]) => setGateThreshold(v)}
                        min={gateType === "coverage" ? 1 : gateType === "length" ? 20 : 0}
                        max={
                          gateType === "composite"
                            ? 100
                            : gateType === "consistency"
                            ? 40
                            : gateType === "coverage"
                            ? 14
                            : 600
                        }
                        step={1}
                        className="mt-2"
                      />
                    </div>
                    <div>
                      <Label className="text-[10px] uppercase tracking-widest text-slate-500">
                        Monthly calls
                      </Label>
                      <Input
                        type="number"
                        min={100}
                        value={monthlyCalls}
                        onChange={(e) => setMonthlyCalls(Number(e.target.value) || 0)}
                        className="h-8"
                      />
                    </div>
                  </div>
                </CardContent>
              </Card>

              {/* Cascade flow + scan */}
              <div className="grid grid-cols-2 gap-4">
                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm flex items-center gap-2">
                      <GitBranch className="w-4 h-4 text-violet-600" />
                      Live cascade shape
                      <span className="ml-auto text-[10px] text-slate-500 font-normal">
                        {pickedLevels.length} level{pickedLevels.length === 1 ? "" : "s"}
                      </span>
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <CascadeFlow picked={pickedLevels} escalation={effectiveCascade?.escalation_rate} />
                  </CardContent>
                </Card>
                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm flex items-center gap-2">
                      <Activity className="w-4 h-4 text-sky-600" />
                      Cost / quality scan
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <ScanScatter
                      scan={effectiveShapes?.scan || []}
                      flagshipCost={flagshipCost}
                      flagshipQuality={flagshipQuality}
                      activeShape={
                        effectiveCascade
                          ? { keys: effectiveCascade.picked_keys }
                          : null
                      }
                    />
                  </CardContent>
                </Card>
              </div>

              {/* Level table */}
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm flex items-center gap-2">
                    <ListChecks className="w-4 h-4 text-emerald-600" />
                    Roster · click a level to toggle in/out
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-2">
                  {displayLevels.map((lv) => (
                    <LevelRow
                      key={lv.id}
                      lv={lv}
                      onToggle={toggleLevel}
                      flagshipCost={flagshipCost}
                      monthlyCalls={monthlyCalls}
                      isFlagship={`${lv.provider}:${lv.model}` === flagshipKey}
                      isCheap={`${lv.provider}:${lv.model}` === cheapKey}
                    />
                  ))}
                </CardContent>
              </Card>

              {/* Actions strip (recommendations from engine) */}
              {current.summary?.actions?.length > 0 && (
                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm flex items-center gap-2">
                      <Sparkles className="w-4 h-4 text-amber-500" />
                      What to do next
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-1.5">
                    {current.summary.actions.map((a, i) => (
                      <div
                        key={i}
                        className="text-[12px] text-slate-700 bg-amber-50/50 border-l-4 border-amber-400 pl-3 py-1.5 rounded"
                        dangerouslySetInnerHTML={{
                          __html: a
                            .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
                            .replace(/\*([^*]+)\*/g, "<em>$1</em>")
                            .replace(/`([^`]+)`/g, "<code class='bg-slate-100 px-1 rounded'>$1</code>"),
                        }}
                      />
                    ))}
                  </CardContent>
                </Card>
              )}

              {/* Baseline sample */}
              {current.summary?.baseline_medoid && (
                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm flex items-center gap-2">
                      <ArrowRight className="w-4 h-4 text-slate-500" />
                      Anchor response ({current.summary.anchor_key?.split(":").pop()})
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="text-[11px] text-slate-700 bg-slate-50 border rounded p-3 font-mono whitespace-pre-wrap">
                      {current.summary.baseline_medoid}
                    </div>
                  </CardContent>
                </Card>
              )}
            </>
          )}
        </div>
      </div>

      <RelayEditor
        open={editorOpen}
        onClose={() => setEditorOpen(false)}
        onCreated={(r) => {
          setSelectedId(r.id);
          loadRuns();
        }}
        defaults={defaults}
      />
    </div>
  );
};

export default RelayStudio;
