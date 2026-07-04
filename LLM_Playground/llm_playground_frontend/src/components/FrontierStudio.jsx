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
  Compass,
  Sparkles,
  Play,
  Plus,
  Trash2,
  Search,
  Copy,
  DollarSign,
  Coins,
  ListChecks,
  Star,
  TrendingUp,
  Activity,
  Trophy,
  Crown,
  Target,
  Timer,
  Zap,
  Layers,
  Award,
  FileText,
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
  OpenAI:    ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"],
  Anthropic: ["claude-3-5-sonnet", "claude-3-5-haiku", "claude-3-haiku"],
  Google:    ["gemini-1.5-pro", "gemini-1.5-flash"],
};

// ─── Helpers ──────────────────────────────────────────────────────────────

const fmtNum = (n, d = 1) => (n == null ? "—" : Number(n).toFixed(d));
const fmtPct = (n) => (n == null ? "—" : `${Number(n).toFixed(0)}%`);

const fmtMoney = (n) => {
  if (n == null) return "—";
  const v = Number(n);
  if (Math.abs(v) >= 1000) return `$${(v / 1000).toFixed(1)}k`;
  if (Math.abs(v) >= 1) return `$${v.toFixed(2)}`;
  if (Math.abs(v) >= 0.001) return `$${v.toFixed(4)}`;
  if (v === 0) return "$0";
  return `$${v.toExponential(1)}`;
};

const fmtCostPerCall = (n) => {
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

// ─── Atoms ────────────────────────────────────────────────────────────────

const ScoreRing = ({ value, size = 88, label = "" }) => {
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
        <div className="text-2xl font-extrabold leading-none tracking-tight" style={{ color: hue }}>
          {v == null ? "—" : v}
        </div>
        {label && <div className="text-[9px] uppercase tracking-[0.18em] text-slate-400 mt-1">{label}</div>}
      </div>
    </div>
  );
};

const TierChip = ({ tier }) => {
  const meta = TIER_META[tier] || TIER_META.unknown;
  return (
    <span className={`inline-flex items-center gap-1 text-[10px] uppercase tracking-wide px-2 py-0.5 rounded-full font-semibold ${meta.chip}`}>
      <span className="w-1.5 h-1.5 rounded-full" style={{ background: meta.hue }} />
      {meta.label}
    </span>
  );
};

const StatTile = ({ icon: Icon, label, value, sub, tone = "slate" }) => (
  <div className={`flex items-center gap-3 px-3 py-2.5 rounded-xl bg-white/85 ring-1 ring-${tone}-200 shadow-sm`}>
    <div className={`p-2 rounded-lg bg-${tone}-50`}>
      <Icon className={`w-4 h-4 text-${tone}-600`} />
    </div>
    <div className="min-w-0">
      <div className="text-[10px] uppercase tracking-wide text-slate-500 font-semibold">{label}</div>
      <div className="text-base font-bold text-slate-800 tabular-nums truncate">{value}</div>
      {sub && <div className="text-[10px] text-slate-500 truncate">{sub}</div>}
    </div>
  </div>
);

// ─── Pareto plot (SVG) ────────────────────────────────────────────────────
// Log-cost x-axis, linear-quality y-axis. Frontier drawn as a stepped line
// connecting non-dominated points, elbow marked with a star, dominated
// points rendered dimmer.

const ParetoPlot = ({ points, elbowKey, quality_floor, budget_ceiling }) => {
  const valid = (points || []).filter(p => p.quality != null && p.cost_per_call != null);
  if (!valid.length) {
    return (
      <div className="h-72 flex items-center justify-center text-sm text-slate-400 italic">
        No points yet — run the frontier.
      </div>
    );
  }
  const W = 720, H = 340;
  const M = { l: 60, r: 24, t: 20, b: 40 };
  const inner_w = W - M.l - M.r;
  const inner_h = H - M.t - M.b;

  // Domain: log-cost x, linear-quality y (0..100 fixed).
  const logCosts = valid.map(p => Math.log10(Math.max(1e-8, p.cost_per_call)));
  const minLC = Math.floor(Math.min(...logCosts) - 0.15);
  const maxLC = Math.ceil(Math.max(...logCosts) + 0.15);
  const spanLC = Math.max(0.5, maxLC - minLC);
  const y_lo = 20, y_hi = 100;
  const y_span = y_hi - y_lo;

  const xForLC = (lc) => M.l + ((lc - minLC) / spanLC) * inner_w;
  const xForCost = (c) => xForLC(Math.log10(Math.max(1e-8, c)));
  const yForQ = (q) => M.t + inner_h - ((Math.max(y_lo, Math.min(y_hi, q)) - y_lo) / y_span) * inner_h;

  // x-axis ticks — powers of 10 within domain.
  const xTicks = [];
  for (let p = minLC; p <= maxLC; p += 1) {
    xTicks.push(p);
  }
  const yTicks = [20, 40, 60, 80, 100];

  // Frontier points sorted by cost ascending.
  const frontier = valid.filter(p => p.on_frontier).slice().sort((a, b) => a.cost_per_call - b.cost_per_call);

  // Stepped path: from cheapest to most expensive frontier point, each pair
  // rises vertically then extends horizontally. Reads more clearly than
  // straight segments — the "staircase" is exactly what a Pareto frontier is.
  let pathD = "";
  if (frontier.length) {
    pathD = `M ${xForCost(frontier[0].cost_per_call)} ${yForQ(frontier[0].quality)}`;
    for (let i = 1; i < frontier.length; i++) {
      const prev = frontier[i - 1];
      const cur = frontier[i];
      pathD += ` L ${xForCost(cur.cost_per_call)} ${yForQ(prev.quality)}`;
      pathD += ` L ${xForCost(cur.cost_per_call)} ${yForQ(cur.quality)}`;
    }
  }

  return (
    <div className="w-full overflow-x-auto">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full min-w-[560px]" role="img" aria-label="Cost vs Quality Pareto plot">
        {/* Background grid */}
        <rect x={M.l} y={M.t} width={inner_w} height={inner_h} fill="#f8fafc" />
        {yTicks.map(t => (
          <g key={`y${t}`}>
            <line x1={M.l} y1={yForQ(t)} x2={M.l + inner_w} y2={yForQ(t)} stroke="#e2e8f0" strokeDasharray="3 3" />
            <text x={M.l - 8} y={yForQ(t) + 3} textAnchor="end" fontSize="10" fill="#64748b">{t}</text>
          </g>
        ))}
        {xTicks.map(t => (
          <g key={`x${t}`}>
            <line x1={xForLC(t)} y1={M.t} x2={xForLC(t)} y2={M.t + inner_h} stroke="#e2e8f0" strokeDasharray="3 3" />
            <text x={xForLC(t)} y={M.t + inner_h + 14} textAnchor="middle" fontSize="10" fill="#64748b">
              {t <= -4 ? `$${(10 ** t).toExponential(0)}` : `$${(10 ** t).toFixed(t < 0 ? Math.min(6, -t) : 0)}`}
            </text>
          </g>
        ))}

        {/* Constraint shading */}
        {quality_floor != null && quality_floor > y_lo && (
          <rect x={M.l} y={M.t} width={inner_w} height={yForQ(quality_floor) - M.t} fill="#fee2e2" fillOpacity="0.35" />
        )}
        {budget_ceiling != null && (
          <rect x={xForCost(budget_ceiling)} y={M.t} width={M.l + inner_w - xForCost(budget_ceiling)} height={inner_h} fill="#fee2e2" fillOpacity="0.35" />
        )}
        {quality_floor != null && quality_floor > y_lo && (
          <g>
            <line x1={M.l} y1={yForQ(quality_floor)} x2={M.l + inner_w} y2={yForQ(quality_floor)} stroke="#f43f5e" strokeDasharray="4 3" strokeWidth="1.2" />
            <text x={M.l + 6} y={yForQ(quality_floor) - 4} fontSize="9" fill="#e11d48">quality floor {quality_floor}</text>
          </g>
        )}
        {budget_ceiling != null && (
          <g>
            <line x1={xForCost(budget_ceiling)} y1={M.t} x2={xForCost(budget_ceiling)} y2={M.t + inner_h} stroke="#f43f5e" strokeDasharray="4 3" strokeWidth="1.2" />
            <text x={xForCost(budget_ceiling) + 4} y={M.t + 12} fontSize="9" fill="#e11d48">budget ${budget_ceiling}</text>
          </g>
        )}

        {/* Frontier path */}
        {pathD && (
          <path d={pathD} stroke="#6366f1" strokeWidth="2.2" fill="none" strokeLinejoin="round" strokeLinecap="round" opacity="0.8" />
        )}

        {/* Points */}
        {valid.map((p, i) => {
          const cx = xForCost(p.cost_per_call);
          const cy = yForQ(p.quality);
          const meta = TIER_META[p.tier] || TIER_META.unknown;
          const key = `${p.provider}:${p.model}`;
          const isElbow = key === elbowKey;
          const r = isElbow ? 10 : p.on_frontier ? 8 : 5.5;
          return (
            <g key={i}>
              {isElbow && (
                <circle cx={cx} cy={cy} r={r + 6} fill="none" stroke="#f59e0b" strokeWidth="1.4" opacity="0.6" />
              )}
              <circle
                cx={cx} cy={cy} r={r}
                fill={meta.hue}
                fillOpacity={p.on_frontier ? 0.95 : 0.35}
                stroke={isElbow ? "#f59e0b" : "#ffffff"}
                strokeWidth={isElbow ? 2.5 : 1.6}
              />
              {(p.on_frontier || isElbow) && (
                <text
                  x={cx + r + 4}
                  y={cy + 3}
                  fontSize="10"
                  fontWeight={isElbow ? 700 : 500}
                  fill={isElbow ? "#b45309" : "#334155"}
                >
                  {p.model.length > 22 ? p.model.slice(0, 22) + "…" : p.model}
                </text>
              )}
            </g>
          );
        })}

        {/* Axis labels */}
        <text x={M.l + inner_w / 2} y={H - 4} textAnchor="middle" fontSize="10" fill="#475569" fontWeight="600">
          Cost / call — log scale
        </text>
        <text
          transform={`rotate(-90 14 ${M.t + inner_h / 2})`}
          x={14} y={M.t + inner_h / 2}
          textAnchor="middle" fontSize="10" fill="#475569" fontWeight="600"
        >
          Quality composite (0–100)
        </text>
      </svg>
      {/* Tier legend */}
      <div className="flex flex-wrap gap-1.5 justify-center mt-1">
        {Object.entries(TIER_META).filter(([k]) => k !== "unknown").map(([k, m]) => (
          <span key={k} className={`inline-flex items-center gap-1 text-[10px] font-semibold ${m.chip} px-2 py-0.5 rounded-full`}>
            <span className="w-1.5 h-1.5 rounded-full" style={{ background: m.hue }} />
            {m.label}
          </span>
        ))}
        <span className="inline-flex items-center gap-1 text-[10px] font-semibold text-slate-600 bg-slate-100 px-2 py-0.5 rounded-full">
          <span className="w-2 h-2 rounded-full border border-amber-400 ring-1 ring-amber-300" />
          Elbow
        </span>
      </div>
    </div>
  );
};

// ─── Recommendation card ──────────────────────────────────────────────────

const RecCard = ({ title, icon: Icon, rec, monthlyCalls, accent = "sky", missing = "no eligible model" }) => {
  if (!rec) {
    return (
      <div className={`rounded-2xl border-2 border-dashed border-${accent}-200 bg-white/60 p-4`}>
        <div className={`flex items-center gap-1.5 text-[10px] uppercase tracking-[0.18em] text-${accent}-700 font-bold`}>
          <Icon className="w-3 h-3" /> {title}
        </div>
        <div className="text-sm text-slate-500 italic mt-3">{missing}</div>
      </div>
    );
  }
  const meta = TIER_META[rec.tier] || TIER_META.unknown;
  return (
    <div className={`rounded-2xl border bg-gradient-to-br from-${accent}-50 to-white ring-1 ring-${accent}-200 shadow-sm p-4`}>
      <div className={`flex items-center gap-1.5 text-[10px] uppercase tracking-[0.18em] text-${accent}-700 font-bold`}>
        <Icon className="w-3 h-3" /> {title}
      </div>
      <div className="mt-2 flex items-baseline gap-2">
        <div className="text-lg font-extrabold text-slate-900 truncate">{rec.model}</div>
        <TierChip tier={rec.tier} />
      </div>
      <div className="text-[11px] text-slate-500 mt-0.5">{rec.provider}</div>
      <div className="grid grid-cols-2 gap-2 mt-3">
        <div className="rounded-lg bg-white ring-1 ring-slate-200 px-2 py-1.5">
          <div className="text-[9px] uppercase tracking-wide text-slate-500 font-semibold">Quality</div>
          <div className="text-sm font-bold tabular-nums" style={{ color: scoreHue(rec.quality) }}>
            {fmtNum(rec.quality, 1)} · {fmtPct(rec.quality_kept_pct)} of top
          </div>
        </div>
        <div className="rounded-lg bg-white ring-1 ring-slate-200 px-2 py-1.5">
          <div className="text-[9px] uppercase tracking-wide text-slate-500 font-semibold">Cost / call</div>
          <div className="text-sm font-bold tabular-nums text-slate-800">{fmtCostPerCall(rec.cost_per_call)}</div>
        </div>
        <div className="rounded-lg bg-white ring-1 ring-slate-200 px-2 py-1.5">
          <div className="text-[9px] uppercase tracking-wide text-slate-500 font-semibold">$ / month</div>
          <div className="text-sm font-bold tabular-nums text-slate-800">{fmtMoney(rec.monthly_cost)}</div>
        </div>
        <div className={`rounded-lg bg-emerald-50 ring-1 ring-emerald-200 px-2 py-1.5`}>
          <div className="text-[9px] uppercase tracking-wide text-emerald-700 font-semibold">Monthly savings</div>
          <div className="text-sm font-bold tabular-nums text-emerald-700">{fmtMoney(rec.monthly_savings)}</div>
        </div>
      </div>
    </div>
  );
};

// ─── Point row for the table ──────────────────────────────────────────────

const PointRow = ({ p, elbowKey }) => {
  const meta = TIER_META[p.tier] || TIER_META.unknown;
  const key = `${p.provider}:${p.model}`;
  const isElbow = key === elbowKey;
  const rowClass = isElbow
    ? "bg-amber-50 ring-2 ring-amber-300"
    : p.on_frontier
      ? `bg-white ring-1 ${meta.ring}`
      : "bg-slate-50 opacity-70 ring-1 ring-slate-200";
  return (
    <div className={`rounded-xl px-3 py-2.5 grid grid-cols-12 gap-2 items-center ${rowClass}`}>
      <div className="col-span-4 min-w-0">
        <div className="flex items-center gap-1.5">
          <span className={`w-1.5 h-1.5 rounded-full ${meta.dot}`} />
          <span className="text-[10px] uppercase tracking-wide text-slate-500 font-semibold">
            {p.provider}
          </span>
          <TierChip tier={p.tier} />
        </div>
        <div className="text-sm font-bold text-slate-900 truncate mt-0.5">
          {p.model}
          {isElbow && <Star className="w-3.5 h-3.5 inline-block ml-1 text-amber-500 fill-amber-400" />}
        </div>
      </div>
      <div className="col-span-2 text-right">
        <div className="text-[9px] uppercase tracking-wide text-slate-500">Quality</div>
        <div className="text-sm font-bold tabular-nums" style={{ color: scoreHue(p.quality) }}>
          {fmtNum(p.quality, 1)}
        </div>
        {p.quality_stdev > 0 && (
          <div className="text-[9px] text-slate-400 tabular-nums">±{fmtNum(p.quality_stdev, 1)}</div>
        )}
      </div>
      <div className="col-span-2 text-right">
        <div className="text-[9px] uppercase tracking-wide text-slate-500">$/call</div>
        <div className="text-sm font-mono text-slate-800">{fmtCostPerCall(p.cost_per_call)}</div>
      </div>
      <div className="col-span-2 text-right">
        <div className="text-[9px] uppercase tracking-wide text-slate-500">$/mo</div>
        <div className="text-sm font-mono text-slate-800">{fmtMoney(p.monthly_cost)}</div>
      </div>
      <div className="col-span-2 text-right">
        <div className="text-[9px] uppercase tracking-wide text-slate-500">Latency</div>
        <div className="text-sm font-mono text-slate-800">{p.latency_ms ? `${Math.round(p.latency_ms)}ms` : "—"}</div>
      </div>
      <div className="col-span-12 mt-0.5 flex items-center gap-2 flex-wrap">
        {p.on_frontier ? (
          <span className="text-[10px] uppercase tracking-wide font-semibold px-1.5 py-0.5 rounded bg-indigo-100 text-indigo-700">
            Frontier
          </span>
        ) : (
          <span className="text-[10px] uppercase tracking-wide font-semibold px-1.5 py-0.5 rounded bg-slate-100 text-slate-500">
            Dominated
          </span>
        )}
        {isElbow && (
          <span className="text-[10px] uppercase tracking-wide font-semibold px-1.5 py-0.5 rounded bg-amber-100 text-amber-800">
            Kneedle elbow
          </span>
        )}
        <span className="text-[11px] text-slate-500 italic truncate">{p.rationale}</span>
      </div>
    </div>
  );
};

// ─── Main component ───────────────────────────────────────────────────────

const FrontierStudio = () => {
  const [runs, setRuns] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [activeRun, setActiveRun] = useState(null);
  const [loadingList, setLoadingList] = useState(false);
  const [loadingRun, setLoadingRun] = useState(false);
  const [seeding, setSeeding] = useState(false);
  const [searchQ, setSearchQ] = useState("");
  const [stats, setStats] = useState({ total_runs: 0, completed_runs: 0 });
  const [defaults, setDefaults] = useState(null);
  const [running, setRunning] = useState(false);

  // Editor state
  const [editorOpen, setEditorOpen] = useState(false);
  const [draftName, setDraftName] = useState("");
  const [draftDesc, setDraftDesc] = useState("");
  const [draftSystem, setDraftSystem] = useState("");
  const [draftUser, setDraftUser] = useState("");
  const [draftTemp, setDraftTemp] = useState(0.4);
  const [draftReplays, setDraftReplays] = useState(3);
  const [draftMonthlyCalls, setDraftMonthlyCalls] = useState(50000);
  const [draftQualityFloor, setDraftQualityFloor] = useState(70);
  const [draftBudgetCeiling, setDraftBudgetCeiling] = useState(0.001);
  const [draftDry, setDraftDry] = useState(true);
  const [draftRoster, setDraftRoster] = useState([]);
  const [creating, setCreating] = useState(false);

  // Live constraint sliders (recompute picks against a persisted run).
  const [liveQuality, setLiveQuality] = useState(null);
  const [liveBudget, setLiveBudget] = useState(null);
  const [liveRecs, setLiveRecs] = useState(null);
  const debounceRef = useRef(null);

  useEffect(() => {
    refresh();
    refreshStats();
    ApiService.frontierDefaults().then(res => {
      if (res.success) {
        setDefaults(res.defaults);
        setDraftRoster((res.defaults?.roster || []).map(r => ({ ...r, enabled: true })));
      }
    }).catch(() => {});
  }, []);

  const refresh = useCallback(async () => {
    setLoadingList(true);
    try {
      const res = await ApiService.listFrontiers({ q: searchQ || undefined, limit: 100 });
      if (!res.success) throw new Error(res.error || "list failed");
      setRuns(res.frontiers || []);
      if (!selectedId && res.frontiers?.length) {
        setSelectedId(res.frontiers[0].id);
      }
    } catch (e) {
      toast.error(`List error: ${e.message}`);
    } finally {
      setLoadingList(false);
    }
  }, [searchQ, selectedId]);

  const refreshStats = useCallback(async () => {
    try {
      const res = await ApiService.frontierStats();
      if (res.success) setStats(res.stats || { total_runs: 0 });
    } catch (e) { /* non-fatal */ }
  }, []);

  useEffect(() => {
    if (!selectedId) { setActiveRun(null); return; }
    let cancelled = false;
    setLoadingRun(true);
    ApiService.getFrontier(selectedId)
      .then(res => {
        if (cancelled || !res.success) return;
        setActiveRun(res.frontier);
        setLiveRecs(null);
        setLiveQuality(res.frontier?.quality_floor ?? 70);
        setLiveBudget(res.frontier?.budget_ceiling ?? null);
      })
      .catch(e => toast.error(`Run load error: ${e.message}`))
      .finally(() => { if (!cancelled) setLoadingRun(false); });
    return () => { cancelled = true; };
  }, [selectedId]);

  useEffect(() => {
    const t = setTimeout(() => { refresh(); }, 250);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchQ]);

  // Recompute recommendations when constraint sliders move.
  useEffect(() => {
    if (!activeRun || activeRun.status !== "succeeded") return;
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(async () => {
      try {
        const res = await ApiService.recommendFrontier(activeRun.id, {
          quality_floor: liveQuality,
          budget_ceiling: liveBudget,
          monthly_calls: activeRun.monthly_calls,
        });
        if (res.success) setLiveRecs(res);
      } catch { /* non-fatal */ }
    }, 220);
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current); };
  }, [liveQuality, liveBudget, activeRun?.id]);

  // ── Actions ─────────────────────────────────────────────────────────────

  const seedDemo = async () => {
    setSeeding(true);
    try {
      const res = await ApiService.seedFrontier();
      if (!res.success) throw new Error(res.error || "seed failed");
      toast.success("Demo seeded — fintech support prompt across 9 models");
      await refresh();
      await refreshStats();
      setSelectedId(res.frontier?.id || null);
    } catch (e) {
      toast.error(`Seed error: ${e.message}`);
    } finally {
      setSeeding(false);
    }
  };

  const createRun = async () => {
    if (!draftName.trim()) return toast.error("Name required");
    if (!draftUser.trim()) return toast.error("User prompt required");
    const roster = draftRoster.filter(r => r.enabled).map(r => ({ provider: r.provider, model: r.model }));
    if (roster.length < 2) return toast.error("Enable at least 2 models in the roster");
    setCreating(true);
    try {
      const res = await ApiService.createFrontier({
        name: draftName.trim(),
        description: draftDesc.trim(),
        system_prompt: draftSystem,
        user_prompt: draftUser,
        temperature: draftTemp,
        n_replays: draftReplays,
        monthly_calls: draftMonthlyCalls,
        quality_floor: draftQualityFloor,
        budget_ceiling: draftBudgetCeiling,
        dryrun: draftDry,
        roster,
      });
      if (!res.success) throw new Error(res.error || "create failed");
      toast.success("Frontier run created — hit Run to sweep the roster");
      setEditorOpen(false);
      setDraftName(""); setDraftDesc(""); setDraftSystem(""); setDraftUser("");
      await refresh();
      setSelectedId(res.frontier?.id || null);
    } catch (e) {
      toast.error(`Create error: ${e.message}`);
    } finally {
      setCreating(false);
    }
  };

  const runActive = async () => {
    if (!activeRun) return;
    setRunning(true);
    try {
      const res = await ApiService.runFrontier(activeRun.id, { confirm_live: !activeRun.dryrun });
      if (!res.success) throw new Error(res.error || "run failed");
      toast.success(
        `Sweep done — elbow is ${res.frontier?.elbow_model || "—"} @ ${fmtMoney(res.frontier?.monthly_savings)}/mo savings`
      );
      setActiveRun(res.frontier);
      await refresh();
      await refreshStats();
    } catch (e) {
      toast.error(`Run error: ${e.message}`);
    } finally {
      setRunning(false);
    }
  };

  const deleteActive = async () => {
    if (!activeRun) return;
    if (!confirm(`Delete "${activeRun.name}"?`)) return;
    try {
      await ApiService.deleteFrontier(activeRun.id);
      toast.success("Deleted");
      setSelectedId(null);
      setActiveRun(null);
      await refresh();
      await refreshStats();
    } catch (e) {
      toast.error(`Delete error: ${e.message}`);
    }
  };

  const downloadJson = () => {
    if (!activeRun) return;
    const blob = new Blob([JSON.stringify(activeRun, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `frontier_${activeRun.id}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const copyRecommendation = () => {
    const key = activeRun?.summary?.elbow_key;
    if (!key) return toast.error("No recommendation yet");
    navigator.clipboard?.writeText(key);
    toast.success(`Copied "${key}"`);
  };

  const toggleRoster = (i) => {
    setDraftRoster(rs => rs.map((r, idx) => idx === i ? { ...r, enabled: !r.enabled } : r));
  };
  const addRoster = () => {
    setDraftRoster(rs => [...rs, { provider: "OpenAI", model: "gpt-4o-mini", enabled: true }]);
  };
  const removeRoster = (i) => {
    setDraftRoster(rs => rs.filter((_, idx) => idx !== i));
  };
  const editRoster = (i, patch) => {
    setDraftRoster(rs => rs.map((r, idx) => idx === i ? { ...r, ...patch } : r));
  };

  // ── Derived ────────────────────────────────────────────────────────────

  const points = activeRun?.points || [];
  const elbowKey = activeRun?.summary?.elbow_key || null;
  const topKey = activeRun?.summary?.default_recommendation?.key || activeRun?.top_quality_model || null;

  const defaultRec = activeRun?.summary?.default_recommendation || null;
  const qualityRec = liveRecs?.quality_pick ?? activeRun?.summary?.quality_recommendation ?? null;
  const budgetRec = liveRecs?.budget_pick ?? activeRun?.summary?.budget_recommendation ?? null;
  const topPoint = liveRecs?.top_quality ?? (activeRun?.top_quality_model ? {
    key: activeRun.top_quality_model,
    model: (activeRun.top_quality_model || "").split(":").slice(1).join(":"),
    provider: (activeRun.top_quality_model || "").split(":")[0],
    quality: activeRun.top_quality,
    cost_per_call: activeRun.top_quality_cost,
    monthly_cost: (activeRun.top_quality_cost || 0) * (activeRun.monthly_calls || 0),
    tier: points.find(p => `${p.provider}:${p.model}` === activeRun.top_quality_model)?.tier,
    monthly_savings: 0,
    quality_kept_pct: 100,
  } : null);

  return (
    <div className="space-y-6">
      {/* Header */}
      <Card className="border-0 shadow-md bg-gradient-to-br from-sky-50 via-indigo-50 to-emerald-50">
        <CardContent className="p-5">
          <div className="flex items-start justify-between gap-4 flex-wrap">
            <div className="flex items-start gap-3">
              <div className="p-2.5 rounded-xl bg-gradient-to-br from-sky-500 to-indigo-500 shadow-lg">
                <Compass className="w-6 h-6 text-white" />
              </div>
              <div>
                <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.18em] text-sky-700 font-bold">
                  Round 16 · Day 73
                  <span className="px-1.5 py-0.5 rounded text-white bg-gradient-to-r from-sky-500 to-indigo-500">NEW</span>
                </div>
                <h2 className="text-2xl font-extrabold tracking-tight text-slate-900">
                  Frontier
                </h2>
                <p className="text-sm text-slate-600 max-w-2xl">
                  Cost / quality Pareto explorer. For a prompt + candidate roster it computes each
                  model's quality vs cost, keeps the frontier, kneedles the elbow — and hands you the
                  cheapest model that keeps 95% of flagship quality.
                </p>
              </div>
            </div>
            <div className="flex flex-col gap-2 items-stretch">
              <div className="flex gap-2">
                <Button
                  size="sm"
                  onClick={() => setEditorOpen(true)}
                  className="bg-gradient-to-r from-sky-600 to-indigo-600 hover:from-sky-700 hover:to-indigo-700 text-white gap-1"
                >
                  <Plus className="w-3.5 h-3.5" /> New frontier
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={seedDemo}
                  disabled={seeding}
                  className="gap-1"
                >
                  <Sparkles className="w-3.5 h-3.5" /> {seeding ? "Seeding…" : "Seed demo"}
                </Button>
              </div>
              <div className="grid grid-cols-2 gap-2 text-[10px] tabular-nums text-slate-700">
                <div className="rounded-lg bg-white/80 ring-1 ring-sky-100 px-2 py-1">
                  <div className="uppercase tracking-wide text-[9px] text-slate-500">Runs</div>
                  <div className="font-bold">{stats.total_runs || 0}</div>
                </div>
                <div className="rounded-lg bg-white/80 ring-1 ring-emerald-100 px-2 py-1">
                  <div className="uppercase tracking-wide text-[9px] text-slate-500">$ saved / run</div>
                  <div className="font-bold">{fmtMoney(stats.avg_monthly_savings)}</div>
                </div>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      <div className="grid grid-cols-12 gap-4">
        {/* Left rail */}
        <div className="col-span-12 lg:col-span-3 space-y-3">
          <Card className="shadow-md border-0 bg-white/80 backdrop-blur-sm">
            <CardHeader className="pb-2">
              <CardTitle className="text-xs uppercase tracking-wider text-slate-500 flex items-center gap-2">
                <ListChecks className="w-3.5 h-3.5" /> Saved runs
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              <div className="relative">
                <Search className="w-3.5 h-3.5 absolute left-2.5 top-2.5 text-slate-400" />
                <Input
                  className="pl-7 h-8 text-xs"
                  placeholder="search…"
                  value={searchQ}
                  onChange={e => setSearchQ(e.target.value)}
                />
              </div>
              <ScrollArea className="h-[480px] pr-1">
                {loadingList && <div className="text-xs text-slate-500 py-2">Loading…</div>}
                {!loadingList && runs.length === 0 && (
                  <div className="text-xs text-slate-500 italic py-4 px-1 leading-relaxed">
                    No runs yet. Hit <b>Seed demo</b> to sweep a support prompt
                    across 9 models and see which one to actually ship.
                  </div>
                )}
                <div className="space-y-1.5">
                  {runs.map(r => {
                    const selected = r.id === selectedId;
                    return (
                      <button
                        key={r.id}
                        onClick={() => setSelectedId(r.id)}
                        className={`w-full text-left px-2 py-2 rounded-lg border transition-all ${
                          selected
                            ? "bg-sky-50 border-sky-300 ring-2 ring-sky-200"
                            : "bg-white border-slate-200 hover:border-sky-200 hover:bg-sky-50/50"
                        }`}
                      >
                        <div className="flex items-center justify-between gap-2">
                          <div className="text-xs font-semibold text-slate-800 truncate">{r.name}</div>
                          <span
                            className={`text-[9px] px-1.5 py-0.5 rounded uppercase tracking-wide ${
                              r.status === "succeeded"
                                ? "bg-emerald-100 text-emerald-700"
                                : r.status === "running"
                                ? "bg-amber-100 text-amber-700"
                                : r.status === "failed"
                                ? "bg-rose-100 text-rose-700"
                                : "bg-slate-100 text-slate-600"
                            }`}
                          >
                            {r.status}
                          </span>
                        </div>
                        <div className="flex items-center gap-2 text-[10px] text-slate-500 mt-1">
                          <span>{r.total_models || "–"} models</span>
                          {r.frontier_size ? <span className="text-indigo-700 font-semibold">·{r.frontier_size} frontier</span> : null}
                          {r.monthly_savings ? (
                            <span className="text-emerald-700 font-semibold">{fmtMoney(r.monthly_savings)}/mo</span>
                          ) : null}
                          <span className="ml-auto">{fmtRel(r.updated_at)}</span>
                        </div>
                      </button>
                    );
                  })}
                </div>
              </ScrollArea>
            </CardContent>
          </Card>
        </div>

        {/* Right rail */}
        <div className="col-span-12 lg:col-span-9 space-y-4">
          {!activeRun && !loadingRun && (
            <Card className="border-dashed border-2 border-slate-200 bg-white/60">
              <CardContent className="py-16 text-center space-y-3">
                <div className="inline-flex p-4 rounded-full bg-gradient-to-br from-sky-100 to-indigo-100">
                  <Compass className="w-8 h-8 text-sky-600" />
                </div>
                <h3 className="text-lg font-bold text-slate-800">Pick a run or seed a demo</h3>
                <p className="text-sm text-slate-500 max-w-md mx-auto">
                  Frontier sweeps your prompt across a roster of models, plots the cost/quality
                  frontier, and finds the elbow where marginal quality-per-dollar is highest.
                </p>
                <div className="flex justify-center gap-2 pt-2">
                  <Button onClick={() => setEditorOpen(true)} className="bg-gradient-to-r from-sky-600 to-indigo-600 text-white gap-1">
                    <Plus className="w-3.5 h-3.5" /> New frontier
                  </Button>
                  <Button variant="outline" onClick={seedDemo} disabled={seeding} className="gap-1">
                    <Sparkles className="w-3.5 h-3.5" /> Seed demo
                  </Button>
                </div>
              </CardContent>
            </Card>
          )}

          {loadingRun && <div className="text-sm text-slate-500">Loading run…</div>}

          {activeRun && (
            <>
              {/* Hero */}
              <Card className="border-0 shadow-md bg-white/95">
                <CardContent className="p-5">
                  <div className="flex items-start justify-between gap-4 flex-wrap">
                    <div className="min-w-0">
                      <div className="text-[10px] uppercase tracking-[0.18em] text-slate-500 font-bold">
                        {activeRun.total_models || 0} models · T={activeRun.temperature} · {activeRun.n_replays} replays · {activeRun.monthly_calls?.toLocaleString()} calls/mo
                        {activeRun.dryrun && (
                          <span className="ml-2 px-1.5 py-0.5 rounded bg-amber-100 text-amber-800 normal-case font-semibold tracking-normal">
                            dryrun
                          </span>
                        )}
                      </div>
                      <h3 className="text-xl font-bold text-slate-900 mt-0.5 truncate max-w-2xl">{activeRun.name}</h3>
                      {activeRun.description && (
                        <p className="text-sm text-slate-600 max-w-2xl mt-1">{activeRun.description}</p>
                      )}
                    </div>
                    <div className="flex gap-2 shrink-0">
                      <Button
                        size="sm"
                        onClick={runActive}
                        disabled={running}
                        className="bg-gradient-to-r from-sky-600 to-indigo-600 text-white gap-1"
                      >
                        <Play className="w-3.5 h-3.5" /> {running ? "Sweeping…" : (activeRun.status === "succeeded" ? "Re-run" : "Run")}
                      </Button>
                      <Button size="sm" variant="outline" onClick={downloadJson} className="gap-1">
                        <FileText className="w-3.5 h-3.5" /> JSON
                      </Button>
                      <Button size="sm" variant="ghost" onClick={deleteActive} className="text-rose-600 gap-1">
                        <Trash2 className="w-3.5 h-3.5" />
                      </Button>
                    </div>
                  </div>

                  {activeRun.status === "succeeded" && (
                    <div className="mt-5 grid grid-cols-1 md:grid-cols-[auto_auto_1fr] gap-5 items-center">
                      <div className="flex flex-col items-center">
                        <ScoreRing value={activeRun.top_quality} size={88} label="top model" />
                        <div className="text-[10px] text-slate-500 mt-1 font-mono truncate max-w-[160px] text-center">
                          {activeRun.top_quality_model?.split(":").slice(1).join(":") || "—"}
                        </div>
                      </div>
                      <div className="flex flex-col items-center gap-1 text-amber-600 font-bold">
                        <Star className="w-5 h-5 fill-amber-400 text-amber-500" />
                        <span className="text-[10px] uppercase tracking-wider">Elbow</span>
                        <span className="text-[9px] text-slate-500">{fmtPct(activeRun.quality_kept_pct)} kept</span>
                      </div>
                      <div className="flex items-center gap-5 flex-wrap">
                        <ScoreRing value={activeRun.elbow_quality} size={88} label="elbow" />
                        <div className="grid grid-cols-2 gap-2 flex-1 min-w-[260px]">
                          <StatTile
                            icon={DollarSign}
                            label="Monthly savings"
                            value={fmtMoney(activeRun.monthly_savings)}
                            sub="elbow vs top-quality"
                            tone="emerald"
                          />
                          <StatTile
                            icon={Coins}
                            label="Elbow $/call"
                            value={fmtCostPerCall(activeRun.elbow_cost)}
                            sub={activeRun.elbow_model || "—"}
                            tone="amber"
                          />
                          <StatTile
                            icon={Layers}
                            label="Frontier"
                            value={`${activeRun.frontier_size}/${activeRun.total_models}`}
                            sub={`${activeRun.total_models - activeRun.frontier_size} dominated`}
                            tone="sky"
                          />
                          <StatTile
                            icon={TrendingUp}
                            label="Quality kept"
                            value={fmtPct(activeRun.quality_kept_pct)}
                            sub={`of ${fmtNum(activeRun.top_quality, 0)}-pt top`}
                            tone="indigo"
                          />
                        </div>
                      </div>
                    </div>
                  )}

                  {/* Actions strip */}
                  {activeRun.status === "succeeded" && activeRun.summary?.actions?.length > 0 && (
                    <div className="mt-5 rounded-xl bg-gradient-to-br from-indigo-50 to-sky-50 ring-1 ring-indigo-200 p-3">
                      <div className="text-[10px] uppercase tracking-wider text-indigo-700 font-bold mb-1.5 flex items-center gap-1">
                        <Wand2 className="w-3 h-3" /> Actions
                      </div>
                      <ul className="space-y-1 text-[12px] text-slate-800">
                        {activeRun.summary.actions.map((a, i) => (
                          <li
                            key={i}
                            className="leading-snug"
                            dangerouslySetInnerHTML={{
                              __html: a
                                .replace(/\*\*(.*?)\*\*/g, '<b>$1</b>')
                                .replace(/\*(.*?)\*/g, '<i>$1</i>'),
                            }}
                          />
                        ))}
                      </ul>
                    </div>
                  )}
                </CardContent>
              </Card>

              {/* Pareto plot */}
              {activeRun.status === "succeeded" && (
                <Card className="border-0 shadow-md bg-white/95">
                  <CardHeader className="pb-2 flex flex-row items-center justify-between">
                    <CardTitle className="text-xs uppercase tracking-wider text-slate-500 flex items-center gap-2">
                      <Target className="w-3.5 h-3.5" /> Cost / quality frontier
                    </CardTitle>
                    <Button size="sm" variant="outline" onClick={copyRecommendation} className="gap-1 h-7">
                      <Copy className="w-3.5 h-3.5" /> Copy pick
                    </Button>
                  </CardHeader>
                  <CardContent className="p-3 pt-1">
                    <ParetoPlot
                      points={points}
                      elbowKey={elbowKey}
                      quality_floor={liveQuality}
                      budget_ceiling={liveBudget}
                    />
                  </CardContent>
                </Card>
              )}

              {/* Recommendations + constraint sliders */}
              {activeRun.status === "succeeded" && (
                <Card className="border-0 shadow-md bg-white/95">
                  <CardHeader className="pb-2">
                    <CardTitle className="text-xs uppercase tracking-wider text-slate-500 flex items-center gap-2">
                      <Award className="w-3.5 h-3.5" /> Picks — drag to tune
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="p-4 pt-1 space-y-4">
                    {/* Sliders */}
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div className="space-y-1.5">
                        <div className="flex items-center justify-between text-[11px]">
                          <Label className="text-slate-700 font-semibold">Min quality</Label>
                          <span className="font-mono text-slate-500">{fmtNum(liveQuality, 0)} pts</span>
                        </div>
                        <Slider
                          value={[liveQuality ?? 0]}
                          onValueChange={([v]) => setLiveQuality(v)}
                          min={0} max={100} step={1}
                          className="w-full"
                        />
                        <div className="flex justify-between text-[9px] text-slate-400 font-mono">
                          <span>0</span><span>25</span><span>50</span><span>75</span><span>100</span>
                        </div>
                      </div>
                      <div className="space-y-1.5">
                        <div className="flex items-center justify-between text-[11px]">
                          <Label className="text-slate-700 font-semibold">Max cost / call</Label>
                          <span className="font-mono text-slate-500">{fmtCostPerCall(liveBudget)}</span>
                        </div>
                        <Slider
                          value={[Math.log10(Math.max(1e-7, liveBudget ?? 0.005)) + 7]}
                          onValueChange={([v]) => setLiveBudget(Math.pow(10, v - 7))}
                          min={0} max={9} step={0.05}
                          className="w-full"
                        />
                        <div className="flex justify-between text-[9px] text-slate-400 font-mono">
                          <span>1e-7</span><span>1e-5</span><span>1e-3</span><span>0.1</span><span>10</span>
                        </div>
                      </div>
                    </div>

                    {/* Rec cards */}
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                      <RecCard title="Default (elbow)" icon={Star} rec={defaultRec} monthlyCalls={activeRun.monthly_calls} accent="amber" />
                      <RecCard title="Meets quality floor" icon={Crown} rec={qualityRec} monthlyCalls={activeRun.monthly_calls} accent="indigo" missing="no model clears the floor" />
                      <RecCard title="Within budget" icon={Coffee} rec={budgetRec} monthlyCalls={activeRun.monthly_calls} accent="emerald" missing="no model fits the budget" />
                    </div>
                  </CardContent>
                </Card>
              )}

              {/* Point table */}
              {activeRun.status === "succeeded" && (
                <Card className="border-0 shadow-md bg-white/95">
                  <CardHeader className="pb-2">
                    <CardTitle className="text-xs uppercase tracking-wider text-slate-500 flex items-center gap-2">
                      <Layers className="w-3.5 h-3.5" /> Models ({points.length})
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-1.5">
                    {points
                      .slice()
                      .sort((a, b) => (a.cost_per_call ?? 1e9) - (b.cost_per_call ?? 1e9))
                      .map((p, i) => (
                        <PointRow key={p.id || i} p={p} elbowKey={elbowKey} />
                      ))}
                  </CardContent>
                </Card>
              )}

              {/* Baseline medoid */}
              {activeRun.status === "succeeded" && activeRun.summary?.baseline_medoid && (
                <Card className="border-0 shadow-md bg-white/95">
                  <CardHeader className="pb-2">
                    <CardTitle className="text-xs uppercase tracking-wider text-slate-500 flex items-center gap-2">
                      <FileText className="w-3.5 h-3.5" /> Anchor response — {activeRun.summary?.anchor_key || "top tier"}
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <pre className="text-[11px] leading-relaxed bg-slate-50 border border-slate-200 rounded-lg p-3 whitespace-pre-wrap max-h-72 overflow-auto text-slate-700">
                      {activeRun.summary.baseline_medoid}
                    </pre>
                    <p className="text-[10px] text-slate-500 italic mt-1.5">
                      Fidelity of every candidate's response is scored as Jaccard-similarity to this anchor — so
                      "high quality" means "resembles what the flagship-tier model said".
                    </p>
                  </CardContent>
                </Card>
              )}

              {activeRun.status !== "succeeded" && activeRun.status !== "running" && (
                <Card className="border-dashed border-slate-200 bg-white/60">
                  <CardContent className="py-10 text-center space-y-2">
                    <Compass className="w-7 h-7 mx-auto text-slate-400" />
                    <div className="text-sm text-slate-700">Run not executed yet.</div>
                    <Button size="sm" onClick={runActive} disabled={running} className="bg-gradient-to-r from-sky-600 to-indigo-600 text-white gap-1">
                      <Play className="w-3.5 h-3.5" /> Sweep the roster
                    </Button>
                  </CardContent>
                </Card>
              )}
            </>
          )}
        </div>
      </div>

      {/* Editor modal */}
      {editorOpen && (
        <div
          className="fixed inset-0 z-50 bg-slate-900/50 backdrop-blur-sm flex items-start justify-center p-4 overflow-auto"
          onClick={() => setEditorOpen(false)}
        >
          <Card
            className="w-full max-w-3xl my-8 shadow-2xl border-0"
            onClick={e => e.stopPropagation()}
          >
            <CardHeader className="pb-3 border-b">
              <CardTitle className="flex items-center gap-2">
                <Plus className="w-4 h-4 text-sky-600" />
                New frontier
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4 py-4">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label className="text-xs">Name</Label>
                  <Input value={draftName} onChange={e => setDraftName(e.target.value)} placeholder="e.g. Support prompt — model selection" />
                </div>
                <div>
                  <Label className="text-xs">Description (optional)</Label>
                  <Input value={draftDesc} onChange={e => setDraftDesc(e.target.value)} placeholder="What is this prompt for?" />
                </div>
              </div>

              <div>
                <Label className="text-xs">System prompt</Label>
                <Textarea
                  value={draftSystem}
                  onChange={e => setDraftSystem(e.target.value)}
                  placeholder="Optional system prompt to test."
                  className="font-mono text-xs"
                  style={{ minHeight: 100 }}
                />
              </div>

              <div>
                <Label className="text-xs">User prompt (the test case)</Label>
                <Textarea
                  value={draftUser}
                  onChange={e => setDraftUser(e.target.value)}
                  placeholder="A representative user message — every model in the roster gets this input."
                  className="font-mono text-xs"
                  style={{ minHeight: 80 }}
                />
              </div>

              <div>
                <div className="flex items-center justify-between">
                  <Label className="text-xs">Roster</Label>
                  <Button variant="outline" size="sm" className="h-6 gap-1 text-[10px]" onClick={addRoster}>
                    <Plus className="w-3 h-3" /> Add
                  </Button>
                </div>
                <div className="text-[10px] text-slate-500 -mt-0.5">
                  Enable the models to include in the sweep. Every enabled entry gets {draftReplays} replays.
                </div>
                <div className="mt-1.5 space-y-1.5 max-h-56 overflow-auto pr-1">
                  {draftRoster.map((r, i) => (
                    <div key={i} className={`flex items-center gap-2 rounded-lg border px-2 py-1.5 ${r.enabled ? "bg-white ring-1 ring-slate-200" : "bg-slate-50 opacity-60"}`}>
                      <Switch checked={r.enabled} onCheckedChange={() => toggleRoster(i)} />
                      <Select value={r.provider} onValueChange={v => editRoster(i, { provider: v })}>
                        <SelectTrigger className="h-7 text-xs w-32"><SelectValue /></SelectTrigger>
                        <SelectContent>
                          {Object.keys(PROVIDER_MODELS).map(p => <SelectItem key={p} value={p}>{p}</SelectItem>)}
                        </SelectContent>
                      </Select>
                      <Input
                        value={r.model}
                        onChange={e => editRoster(i, { model: e.target.value })}
                        placeholder="model id"
                        className="h-7 text-xs flex-1 font-mono"
                      />
                      <Button size="sm" variant="ghost" className="h-6 w-6 p-0 text-rose-500" onClick={() => removeRoster(i)}>
                        <Trash2 className="w-3 h-3" />
                      </Button>
                    </div>
                  ))}
                </div>
              </div>

              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <div>
                  <Label className="text-xs">Temperature</Label>
                  <Input type="number" min="0" max="2" step="0.05" value={draftTemp} onChange={e => setDraftTemp(parseFloat(e.target.value) || 0)} className="h-9 text-xs" />
                </div>
                <div>
                  <Label className="text-xs">Replays / model</Label>
                  <Input type="number" min="1" max="6" value={draftReplays} onChange={e => setDraftReplays(parseInt(e.target.value) || 1)} className="h-9 text-xs" />
                </div>
                <div>
                  <Label className="text-xs">Monthly calls</Label>
                  <Input type="number" min="100" value={draftMonthlyCalls} onChange={e => setDraftMonthlyCalls(parseInt(e.target.value) || 0)} className="h-9 text-xs" />
                </div>
                <div className="flex items-center justify-between gap-2 px-3 py-2 rounded-lg bg-amber-50 ring-1 ring-amber-200">
                  <div>
                    <div className="text-xs font-semibold text-amber-800">Dryrun</div>
                    <div className="text-[10px] text-amber-700">no API keys</div>
                  </div>
                  <Switch checked={draftDry} onCheckedChange={setDraftDry} />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label className="text-xs">Quality floor (0-100)</Label>
                  <Input type="number" min="0" max="100" step="1" value={draftQualityFloor} onChange={e => setDraftQualityFloor(parseFloat(e.target.value) || 0)} className="h-9 text-xs" />
                </div>
                <div>
                  <Label className="text-xs">Budget ceiling ($/call)</Label>
                  <Input type="number" min="0" step="0.0001" value={draftBudgetCeiling} onChange={e => setDraftBudgetCeiling(parseFloat(e.target.value) || 0)} className="h-9 text-xs font-mono" />
                </div>
              </div>
            </CardContent>
            <div className="border-t px-5 py-3 flex justify-end gap-2 bg-slate-50/50">
              <Button variant="outline" onClick={() => setEditorOpen(false)}>Cancel</Button>
              <Button
                onClick={createRun}
                disabled={creating}
                className="bg-gradient-to-r from-sky-600 to-indigo-600 text-white gap-1"
              >
                <Plus className="w-3.5 h-3.5" /> {creating ? "Creating…" : "Create run"}
              </Button>
            </div>
          </Card>
        </div>
      )}
    </div>
  );
};

export default FrontierStudio;
