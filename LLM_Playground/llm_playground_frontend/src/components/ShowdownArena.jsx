import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Label } from "@/components/ui/label";
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
  Swords,
  Trophy,
  Crown,
  Target,
  Plus,
  Trash2,
  Play,
  Beaker,
  RotateCcw,
  Sparkles,
  ChevronRight,
  ChevronDown,
  Search,
  Copy,
  Download,
  ArrowRight,
  ArrowUp,
  ArrowDown,
  Equal,
  Scale,
  ShieldCheck,
  HelpCircle,
  Sigma,
  Activity,
  TrendingUp,
  TrendingDown,
  Award,
  AlertCircle,
} from "lucide-react";
import { toast } from "sonner";
import ApiService from "../services/api";

// ─── Helpers ───────────────────────────────────────────────────────────────

const fmtRel = (epoch) => {
  if (!epoch) return "—";
  const d = new Date(Number(epoch) * 1000);
  const diff = (Date.now() - d.getTime()) / 1000;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  if (diff < 86400 * 7) return `${Math.floor(diff / 86400)}d ago`;
  return d.toLocaleDateString();
};

const fmtNum = (n, d = 1) => (n == null ? "—" : Number(n).toFixed(d));
const fmtSigned = (n, d = 2) => {
  if (n == null || Number.isNaN(Number(n))) return "—";
  const v = Number(n);
  return `${v >= 0 ? "+" : ""}${v.toFixed(d)}`;
};
const fmtPct = (n, d = 0) => (n == null ? "—" : `${(Number(n) * 100).toFixed(d)}%`);
const fmtCost = (c) => {
  if (c == null) return "—";
  if (c === 0) return "$0";
  if (c < 0.001) return `$${(c * 1000).toFixed(3)}m`;
  return `$${Number(c).toFixed(4)}`;
};

// Delta colour ramp — positive (challenger wins) goes to emerald; negative
// (challenger regresses) goes to rose. Used everywhere a delta is shown.
const deltaHue = (v) => {
  if (v == null || Number.isNaN(Number(v))) return "#94a3b8";
  const n = Number(v);
  if (n >= 8)   return "#16a34a"; // emerald-600
  if (n >= 3)   return "#22c55e"; // emerald-500
  if (n >= 1)   return "#84cc16"; // lime-500
  if (n > -1)   return "#64748b"; // slate-500 (~tie)
  if (n > -3)   return "#f59e0b"; // amber-500
  if (n > -8)   return "#f97316"; // orange-500
  return "#ef4444";               // rose-500
};

// ─── Decision palette ──────────────────────────────────────────────────────

const DECISIONS = {
  ship_challenger: {
    label: "Ship Challenger",
    short: "Ship",
    glyph: TrendingUp,
    grad: "from-emerald-500 via-teal-500 to-cyan-500",
    hue: "#10b981",
    soft: "rgba(16,185,129,0.12)",
    blurb: "Statistically meaningful improvement — challenger should replace champion in production.",
  },
  keep_champion: {
    label: "Keep Champion",
    short: "Keep",
    glyph: Crown,
    grad: "from-amber-500 via-orange-500 to-rose-500",
    hue: "#f59e0b",
    soft: "rgba(245,158,11,0.12)",
    blurb: "Challenger regressed — leave the champion in place and try a new candidate.",
  },
  tied: {
    label: "Tied",
    short: "Tie",
    glyph: Scale,
    grad: "from-slate-400 via-slate-500 to-slate-600",
    hue: "#64748b",
    soft: "rgba(100,116,139,0.12)",
    blurb: "No meaningful difference — pick whichever is cheaper or simpler to maintain.",
  },
  no_decision: {
    label: "No Decision",
    short: "Wait",
    glyph: HelpCircle,
    grad: "from-fuchsia-500 via-violet-500 to-indigo-500",
    hue: "#a855f7",
    soft: "rgba(168,85,247,0.12)",
    blurb: "Effect not separable from noise — add more cases or sharpen the rubric before deciding.",
  },
};

const decisionMeta = (decision) => DECISIONS[decision] || DECISIONS.no_decision;

// ─── Primitives ────────────────────────────────────────────────────────────

// 168px decision ring — outer arc fills with decision colour proportional to
// confidence (win-rate when applicable, otherwise 0.5), inner badge holds the
// short label.
const DecisionRing = ({ decision, winRate, meanDelta }) => {
  const meta = decisionMeta(decision);
  const G = meta.glyph;
  const fill = winRate != null ? Math.max(0, Math.min(1, Number(winRate))) : 0.5;
  const deg = Math.round(fill * 360);
  const ring = {
    background: `conic-gradient(${meta.hue} ${deg}deg, rgba(148,163,184,0.18) ${deg}deg 360deg)`,
  };
  return (
    <div className="relative w-[168px] h-[168px] mx-auto">
      <div className="absolute inset-0 rounded-full" style={ring} />
      <div className="absolute inset-3 rounded-full bg-slate-950/85 ring-1 ring-white/10 flex flex-col items-center justify-center text-center">
        <G className="w-8 h-8 mb-1" style={{ color: meta.hue }} />
        <div className="text-[10px] uppercase tracking-[0.18em] text-slate-400">decision</div>
        <div className="text-[15px] font-semibold text-white mt-0.5 px-2 leading-tight">
          {meta.short}
        </div>
        {meanDelta != null && (
          <div className="text-[11px] mt-0.5 font-mono" style={{ color: deltaHue(meanDelta) }}>
            Δ {fmtSigned(meanDelta)}
          </div>
        )}
      </div>
    </div>
  );
};

// 56px mini ring used in the audit list — uses decision colour as the fill.
const MiniRing = ({ decision, winRate }) => {
  const meta = decisionMeta(decision);
  const G = meta.glyph;
  const fill = winRate != null ? Math.max(0, Math.min(1, Number(winRate))) : 0.5;
  const deg = Math.round(fill * 360);
  const ring = {
    background: `conic-gradient(${meta.hue} ${deg}deg, rgba(148,163,184,0.18) ${deg}deg 360deg)`,
  };
  return (
    <div className="relative w-[52px] h-[52px] flex-shrink-0">
      <div className="absolute inset-0 rounded-full" style={ring} />
      <div className="absolute inset-1.5 rounded-full bg-slate-950/85 ring-1 ring-white/10 flex items-center justify-center">
        <G className="w-4 h-4" style={{ color: meta.hue }} />
      </div>
    </div>
  );
};

// Tile metric card with bottom-edge hue rim.
const Tile = ({ icon: Icon, label, value, sub, hue = "#94a3b8" }) => (
  <div className="relative rounded-xl bg-slate-900/60 ring-1 ring-white/8 px-3 py-2.5 overflow-hidden">
    <div className="absolute inset-x-0 bottom-0 h-[3px]" style={{ background: hue }} />
    <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-slate-400">
      {Icon && <Icon className="w-3 h-3" />}
      {label}
    </div>
    <div className="text-lg font-semibold mt-0.5" style={{ color: hue }}>{value}</div>
    {sub && <div className="text-[10px] text-slate-500 mt-0.5">{sub}</div>}
  </div>
);

// Bipolar centred delta bar. Width relative to absMax. Optional CI band.
const DeltaBar = ({ value, ciLow, ciHigh, absMax = 12, label, height = 10 }) => {
  if (value == null) {
    return (
      <div className="w-full text-[10px] text-slate-500 italic">—</div>
    );
  }
  const v = Math.max(-absMax, Math.min(absMax, Number(value)));
  const pos = v >= 0;
  const widthPct = (Math.abs(v) / absMax) * 50;
  const hue = deltaHue(value);
  const trackHue = "rgba(148,163,184,0.12)";

  let ciSpan = null;
  if (ciLow != null && ciHigh != null) {
    const lo = Math.max(-absMax, Math.min(absMax, Number(ciLow)));
    const hi = Math.max(-absMax, Math.min(absMax, Number(ciHigh)));
    const left = ((lo + absMax) / (absMax * 2)) * 100;
    const right = ((hi + absMax) / (absMax * 2)) * 100;
    ciSpan = (
      <div
        className="absolute top-0 bottom-0 rounded-full"
        style={{
          left: `${left}%`,
          width: `${Math.max(0.3, right - left)}%`,
          background: hue,
          opacity: 0.22,
        }}
      />
    );
  }

  return (
    <div className="w-full">
      <div className="relative rounded-full overflow-hidden" style={{ height, background: trackHue }}>
        {ciSpan}
        {/* Zero line. */}
        <div className="absolute top-0 bottom-0 left-1/2 w-px bg-white/20" />
        {/* Filled value bar. */}
        <div
          className="absolute top-0 bottom-0"
          style={{
            left: pos ? "50%" : `${50 - widthPct}%`,
            width: `${widthPct}%`,
            background: hue,
            boxShadow: `0 0 8px ${hue}55`,
          }}
        />
      </div>
      {label !== undefined && (
        <div className="flex justify-between mt-1 text-[10px] text-slate-500 font-mono">
          <span>−{absMax}</span>
          <span style={{ color: hue }}>{label}</span>
          <span>+{absMax}</span>
        </div>
      )}
    </div>
  );
};

// Win/loss/tie pill row.
const WLTPills = ({ nWins, nLosses, nTies, champLabel = "champ", chalLabel = "chall" }) => (
  <div className="flex items-center gap-1.5 text-[11px]">
    <span className="px-2 py-0.5 rounded-full bg-emerald-500/15 text-emerald-300 ring-1 ring-emerald-500/30 font-mono">
      {nWins} <span className="opacity-70">{chalLabel}</span>
    </span>
    <span className="px-2 py-0.5 rounded-full bg-slate-500/15 text-slate-300 ring-1 ring-slate-500/30 font-mono">
      {nTies} ties
    </span>
    <span className="px-2 py-0.5 rounded-full bg-amber-500/15 text-amber-300 ring-1 ring-amber-500/30 font-mono">
      {nLosses} <span className="opacity-70">{champLabel}</span>
    </span>
  </div>
);

const EmptyState = ({ icon: Icon, title, body, action }) => (
  <div className="flex flex-col items-center justify-center py-12 text-center">
    {Icon && (
      <div className="w-12 h-12 rounded-2xl bg-slate-800/60 ring-1 ring-white/8 flex items-center justify-center mb-3">
        <Icon className="w-6 h-6 text-slate-400" />
      </div>
    )}
    <div className="text-sm font-medium text-slate-200">{title}</div>
    {body && <div className="text-xs text-slate-400 mt-1 max-w-xs">{body}</div>}
    {action && <div className="mt-3">{action}</div>}
  </div>
);

// ─── Defaults ──────────────────────────────────────────────────────────────

const newCase = () => ({ input: "", expected: "" });

const EMPTY_DRAFT = {
  name: "",
  description: "",
  champion_prompt: "",
  challenger_prompt: "",
  champion_label: "Champion",
  challenger_label: "Challenger",
  rubric_id: "",
  rubric_revision: null,
  dryrun: true,
  n_bootstrap: 5000,
  test_cases: [newCase(), newCase()],
};

// ─── Main component ───────────────────────────────────────────────────────

export default function ShowdownArena() {
  const [list, setList] = useState([]);
  const [statsBlob, setStatsBlob] = useState(null);
  const [selectedId, setSelectedId] = useState(null);
  const [selected, setSelected] = useState(null);
  const [tab, setTab] = useState("setup"); // setup | results
  const [draft, setDraft] = useState({ ...EMPTY_DRAFT });
  const [rubrics, setRubrics] = useState([]);
  const [loadingList, setLoadingList] = useState(false);
  const [creating, setCreating] = useState(false);
  const [running, setRunning] = useState(false);
  const [expanded, setExpanded] = useState({}); // per-case expand toggles
  const [search, setSearch] = useState("");
  const draftMode = !selectedId;

  const refreshList = useCallback(async () => {
    setLoadingList(true);
    try {
      const r = await ApiService.listShowdowns();
      setList(r.showdowns || []);
    } catch (e) {
      console.error(e);
      toast.error(e.message || "Failed to load showdowns");
    } finally {
      setLoadingList(false);
    }
  }, []);

  const refreshStats = useCallback(async () => {
    try {
      const r = await ApiService.showdownStats();
      setStatsBlob(r.stats || null);
    } catch (e) {
      console.error(e);
    }
  }, []);

  const refreshRubrics = useCallback(async () => {
    try {
      const r = await ApiService.listRubrics();
      setRubrics(r.rubrics || []);
    } catch (e) {
      console.error(e);
    }
  }, []);

  useEffect(() => {
    refreshList();
    refreshStats();
    refreshRubrics();
  }, [refreshList, refreshStats, refreshRubrics]);

  const loadShowdown = useCallback(async (id) => {
    setSelectedId(id);
    setExpanded({});
    setTab("setup");
    try {
      const r = await ApiService.getShowdown(id);
      setSelected(r.showdown);
      if (r.showdown && r.showdown.status === "complete") {
        setTab("results");
      }
    } catch (e) {
      console.error(e);
      toast.error(e.message || "Failed to load showdown");
    }
  }, []);

  const clearSelection = () => {
    setSelectedId(null);
    setSelected(null);
    setDraft({ ...EMPTY_DRAFT });
    setTab("setup");
    setExpanded({});
  };

  // ─── Actions ────────────────────────────────────────────────────────────
  const handleCreate = async () => {
    if (!draft.name.trim()) {
      toast.error("Name is required");
      return;
    }
    if (!draft.champion_prompt.trim() || !draft.challenger_prompt.trim()) {
      toast.error("Both Champion and Challenger prompts are required");
      return;
    }
    if (draft.champion_prompt.trim() === draft.challenger_prompt.trim()) {
      toast.error("Champion and Challenger prompts are identical");
      return;
    }
    const cases = (draft.test_cases || []).filter((c) => (c.input || "").trim());
    if (cases.length === 0) {
      toast.error("Add at least one test case with a non-empty input");
      return;
    }
    setCreating(true);
    try {
      const payload = {
        ...draft,
        test_cases: cases,
        n_bootstrap: Number(draft.n_bootstrap) || 5000,
      };
      const r = await ApiService.createShowdown(payload);
      toast.success("Showdown created");
      await refreshList();
      await refreshStats();
      await loadShowdown(r.showdown.id);
    } catch (e) {
      toast.error(e.message || "Failed to create showdown");
    } finally {
      setCreating(false);
    }
  };

  const handleSeed = async () => {
    setCreating(true);
    try {
      const r = await ApiService.seedShowdown();
      toast.success("Demo showdown seeded");
      await refreshList();
      await refreshStats();
      await loadShowdown(r.showdown.id);
    } catch (e) {
      toast.error(e.message || "Failed to seed");
    } finally {
      setCreating(false);
    }
  };

  const handleRun = async (sid = selectedId) => {
    if (!sid) return;
    setRunning(true);
    try {
      const sd = selected || (await ApiService.getShowdown(sid)).showdown;
      const live = sd && !sd.dryrun;
      const r = await ApiService.runShowdown(sid, { confirm_live: !!live });
      toast.success(`Showdown complete — ${r.summary.decision || "no_decision"}`);
      setSelected(r.showdown);
      setTab("results");
      await refreshList();
      await refreshStats();
    } catch (e) {
      toast.error(e.message || "Failed to run showdown");
    } finally {
      setRunning(false);
    }
  };

  const handleDelete = async (sid = selectedId) => {
    if (!sid) return;
    if (!window.confirm("Delete this showdown and all its case results?")) return;
    try {
      await ApiService.deleteShowdown(sid);
      toast.success("Showdown deleted");
      clearSelection();
      await refreshList();
      await refreshStats();
    } catch (e) {
      toast.error(e.message || "Failed to delete");
    }
  };

  // ─── Markdown export ────────────────────────────────────────────────────
  const exportMarkdown = () => {
    if (!selected || !selected.summary) return;
    const s = selected.summary;
    const meta = decisionMeta(s.decision);
    const dimRows = (s.dim_summary || [])
      .map((d) => `| ${d.name} | ${d.weight ?? 0} | ${fmtSigned(d.mean_delta)} | ${fmtSigned(d.worst_delta)} | ${fmtSigned(d.best_delta)} | ${d.n ?? 0} |`)
      .join("\n");
    const lines = [
      `# Showdown — ${selected.name}`,
      ``,
      `> **Decision: ${meta.label}** — ${s.headline}`,
      ``,
      `## Result snapshot`,
      ``,
      `| Metric | Value |`,
      `| --- | --- |`,
      `| Champion · ${selected.champion_label} | ${fmtNum(s.champion_composite, 2)} |`,
      `| Challenger · ${selected.challenger_label} | ${fmtNum(s.challenger_composite, 2)} |`,
      `| Mean Δ | ${fmtSigned(s.mean_delta)} |`,
      `| 95% bootstrap CI | [${fmtSigned(s.ci_low)}, ${fmtSigned(s.ci_high)}] |`,
      `| Win rate (challenger) | ${fmtPct(s.win_rate)} |`,
      `| Sign-test p-value | ${fmtNum(s.p_value_sign, 4)} |`,
      `| Cohen's d (paired) | ${fmtNum(s.effect_size, 3)} |`,
      `| Wins / Losses / Ties | ${s.n_wins} / ${s.n_losses} / ${s.n_ties} |`,
      `| Cases compared | ${s.n_compared}/${s.n_cases} |`,
      `| Bootstrap iterations | ${s.n_bootstrap} |`,
      `| Total cost | ${fmtCost(s.total_cost)} |`,
      ``,
      `## Decision rule`,
      ``,
      `- **Ship Challenger** when mean Δ ≥ +${s.thresholds.ship_min_delta}, CI excludes 0, win-rate ≥ ${Math.round(s.thresholds.ship_min_winrate * 100)}%.`,
      `- **Keep Champion** when mean Δ ≤ ${s.thresholds.keep_max_delta}, CI excludes 0, win-rate ≤ ${Math.round(s.thresholds.keep_max_winrate * 100)}%.`,
      `- **Tied** when |mean Δ| < ${s.thresholds.tie_max_abs_delta}, CI spans 0, win-rate in [${Math.round(s.thresholds.tie_winrate_low * 100)}%, ${Math.round(s.thresholds.tie_winrate_high * 100)}%].`,
      `- Otherwise **No Decision** — add more cases or sharpen the rubric.`,
      ``,
    ];
    if (dimRows) {
      lines.push(
        `## Per-dimension impact`,
        ``,
        `| Dimension | Weight | Mean Δ | Worst Δ | Best Δ | n |`,
        `| --- | --- | --- | --- | --- | --- |`,
        dimRows,
        ``,
      );
    }
    const perCase = (s.per_case || []).map((r) => {
      const out = r.outcome === "challenger_win" ? "challenger" : r.outcome === "champion_win" ? "champion" : "tie";
      return `| ${r.case_idx + 1} | ${fmtNum(r.champion_composite, 1)} | ${fmtNum(r.challenger_composite, 1)} | ${fmtSigned(r.delta)} | ${out} |`;
    }).join("\n");
    if (perCase) {
      lines.push(
        `## Per-case results`,
        ``,
        `| # | Champion | Challenger | Δ | Outcome |`,
        `| --- | --- | --- | --- | --- |`,
        perCase,
        ``,
      );
    }
    const blob = new Blob([lines.join("\n")], { type: "text/markdown" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `showdown-${selected.id.slice(0, 8)}.md`;
    a.click();
    URL.revokeObjectURL(a.href);
    toast.success("Markdown digest downloaded");
  };

  // ─── Filtered list ──────────────────────────────────────────────────────
  const filteredList = useMemo(() => {
    if (!search.trim()) return list;
    const q = search.trim().toLowerCase();
    return list.filter(
      (sd) =>
        (sd.name || "").toLowerCase().includes(q) ||
        (sd.description || "").toLowerCase().includes(q),
    );
  }, [list, search]);

  // ─── Hero stats strip ──────────────────────────────────────────────────
  const stats = statsBlob || {};
  const heroTiles = [
    {
      icon: Swords,
      label: "Showdowns",
      value: stats.n_showdowns ?? 0,
      hue: "#06b6d4",
    },
    {
      icon: TrendingUp,
      label: "Ship recs",
      value: stats.n_ship_challenger ?? 0,
      sub: "challengers won",
      hue: "#10b981",
    },
    {
      icon: Crown,
      label: "Keep recs",
      value: stats.n_keep_champion ?? 0,
      sub: "champions held",
      hue: "#f59e0b",
    },
    {
      icon: Scale,
      label: "Tied",
      value: stats.n_tied ?? 0,
      hue: "#64748b",
    },
    {
      icon: Sigma,
      label: "Avg Δ",
      value: fmtSigned(stats.avg_mean_delta),
      hue: deltaHue(stats.avg_mean_delta),
    },
  ];

  // ─── Setup tab ─────────────────────────────────────────────────────────
  const setupSource = selected || draft;
  const editable = !selected; // Once persisted, setup view becomes read-only.

  const setDraftField = (k, v) => setDraft((d) => ({ ...d, [k]: v }));
  const updateDraftCase = (i, k, v) =>
    setDraft((d) => ({
      ...d,
      test_cases: d.test_cases.map((c, idx) => (idx === i ? { ...c, [k]: v } : c)),
    }));
  const addCase = () =>
    setDraft((d) => ({ ...d, test_cases: [...d.test_cases, newCase()] }));
  const removeCase = (i) =>
    setDraft((d) => ({
      ...d,
      test_cases: d.test_cases.length > 1 ? d.test_cases.filter((_, idx) => idx !== i) : d.test_cases,
    }));

  // ─── Results helpers ────────────────────────────────────────────────────
  const runs = (selected && selected.runs) || [];
  const summary = selected && selected.summary;
  const meta = decisionMeta(summary?.decision);

  const sortedCaseRuns = useMemo(() => {
    // Sort by delta ascending so the worst (regressions) bubble to the top of
    // any "needs investigation" view. The per-case strip below the forest
    // plot keeps case order.
    return runs.slice().sort((a, b) => (a.delta ?? 0) - (b.delta ?? 0));
  }, [runs]);

  const caseAbsMax = useMemo(() => {
    let m = 5;
    runs.forEach((r) => {
      if (r.delta != null) m = Math.max(m, Math.abs(Number(r.delta)));
    });
    return Math.ceil(m + 1);
  }, [runs]);

  // ─── Render ─────────────────────────────────────────────────────────────
  return (
    <div className="space-y-3 text-slate-100">
      {/* HERO --------------------------------------------------------- */}
      <div className="rounded-2xl bg-gradient-to-br from-cyan-500/8 via-fuchsia-500/6 to-emerald-500/8 ring-1 ring-white/10 p-4 backdrop-blur">
        <div className="flex flex-col lg:flex-row gap-4 items-start lg:items-center">
          <div className="flex items-center gap-3">
            <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-cyan-500 via-fuchsia-500 to-emerald-500 flex items-center justify-center shadow-lg shadow-cyan-500/20">
              <Swords className="w-6 h-6 text-white" />
            </div>
            <div>
              <div className="text-[10px] uppercase tracking-[0.18em] text-slate-400 flex items-center gap-1.5">
                Showdown Arena
                <span className="text-[9px] font-semibold uppercase tracking-wider bg-gradient-to-r from-cyan-500 via-fuchsia-500 to-emerald-500 text-white px-1.5 py-0.5 rounded">
                  new
                </span>
              </div>
              <div className="text-lg lg:text-xl font-semibold mt-0.5 text-white">
                Champion <span className="text-slate-500">vs</span> Challenger — should you ship?
              </div>
              <div className="text-[11px] text-slate-400 mt-1 max-w-2xl">
                Paired A/B test: same cases through both prompts, judged by the same rubric, then real
                statistics (95% bootstrap CI · sign-test p · Cohen's d) decide the verdict.
              </div>
            </div>
          </div>
          <div className="flex-1" />
          <div className="grid grid-cols-2 lg:grid-cols-5 gap-2 w-full lg:w-auto">
            {heroTiles.map((t) => (
              <Tile key={t.label} icon={t.icon} label={t.label} value={t.value} sub={t.sub} hue={t.hue} />
            ))}
          </div>
        </div>
      </div>

      {/* TWO-PANE ----------------------------------------------------- */}
      <div className="grid grid-cols-1 lg:grid-cols-[320px_minmax(0,1fr)] gap-3">
        {/* LEFT RAIL ------------------------------------------------- */}
        <Card className="bg-slate-900/40 ring-1 ring-white/8 border-0">
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between gap-2">
              <CardTitle className="text-sm text-slate-200 flex items-center gap-2">
                <Trophy className="w-4 h-4 text-cyan-400" />
                Showdowns
              </CardTitle>
              <Button
                size="icon"
                variant="ghost"
                className="h-7 w-7 hover:bg-cyan-500/10"
                onClick={clearSelection}
                title="New showdown"
              >
                <Plus className="w-4 h-4 text-cyan-400" />
              </Button>
            </div>
            <div className="relative mt-1">
              <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3 h-3 text-slate-500" />
              <Input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search…"
                className="h-7 pl-7 text-[12px] bg-slate-950/50 border-white/8"
              />
            </div>
          </CardHeader>
          <Separator className="bg-white/8" />
          <CardContent className="p-0">
            <ScrollArea className="h-[560px]">
              <div className="p-2 space-y-1">
                {loadingList && (
                  <div className="text-xs text-slate-500 px-2 py-3">Loading…</div>
                )}
                {!loadingList && filteredList.length === 0 && (
                  <EmptyState
                    icon={Swords}
                    title="No showdowns yet"
                    body="Seed a demo or create one in the right pane."
                    action={
                      <Button
                        size="sm"
                        className="bg-gradient-to-r from-cyan-500 to-fuchsia-500 hover:opacity-90"
                        onClick={handleSeed}
                        disabled={creating}
                      >
                        <Beaker className="w-3.5 h-3.5 mr-1.5" /> Seed demo
                      </Button>
                    }
                  />
                )}
                {filteredList.map((sd) => {
                  const m = decisionMeta(sd.decision);
                  const sel = selectedId === sd.id;
                  return (
                    <button
                      key={sd.id}
                      onClick={() => loadShowdown(sd.id)}
                      className={`w-full text-left rounded-lg p-2 flex gap-2 items-start transition-all ${
                        sel
                          ? "bg-slate-800/70 ring-1 ring-cyan-500/50"
                          : "hover:bg-slate-800/40 ring-1 ring-transparent"
                      }`}
                    >
                      <MiniRing decision={sd.decision} winRate={sd.win_rate} />
                      <div className="flex-1 min-w-0">
                        <div className="text-[12px] font-medium text-slate-200 truncate">
                          {sd.name}
                        </div>
                        <div className="flex items-center gap-1.5 mt-0.5 flex-wrap">
                          <span
                            className="text-[10px] font-mono px-1.5 py-0.5 rounded"
                            style={{ background: m.soft, color: m.hue }}
                          >
                            {m.short}
                          </span>
                          {sd.mean_delta != null && (
                            <span
                              className="text-[10px] font-mono"
                              style={{ color: deltaHue(sd.mean_delta) }}
                            >
                              Δ {fmtSigned(sd.mean_delta)}
                            </span>
                          )}
                          {sd.win_rate != null && (
                            <span className="text-[10px] text-slate-500 font-mono">
                              {fmtPct(sd.win_rate)} wins
                            </span>
                          )}
                          <span className="text-[10px] text-slate-500 ml-auto">
                            {fmtRel(sd.updated_at)}
                          </span>
                        </div>
                        <div className="flex items-center gap-1.5 mt-1">
                          {sd.dryrun ? (
                            <span className="text-[9px] uppercase tracking-wider bg-violet-500/15 text-violet-300 px-1.5 py-0.5 rounded ring-1 ring-violet-500/20">
                              dry
                            </span>
                          ) : (
                            <span className="text-[9px] uppercase tracking-wider bg-rose-500/15 text-rose-300 px-1.5 py-0.5 rounded ring-1 ring-rose-500/20">
                              live
                            </span>
                          )}
                          <span className="text-[9px] uppercase tracking-wider text-slate-500">
                            status · {sd.status}
                          </span>
                        </div>
                      </div>
                    </button>
                  );
                })}
              </div>
            </ScrollArea>
          </CardContent>
        </Card>

        {/* RIGHT PANE ------------------------------------------------ */}
        <div className="space-y-3 min-w-0">
          {/* Tab switcher -------------------------------------------- */}
          <div className="flex items-center gap-2">
            <div className="inline-flex bg-slate-900/40 ring-1 ring-white/8 rounded-lg p-0.5">
              <button
                onClick={() => setTab("setup")}
                className={`px-3 py-1.5 rounded-md text-[12px] font-medium transition-all ${
                  tab === "setup"
                    ? "bg-gradient-to-r from-cyan-500/30 to-fuchsia-500/30 text-white ring-1 ring-cyan-500/30"
                    : "text-slate-400 hover:text-slate-200"
                }`}
              >
                Setup
              </button>
              <button
                onClick={() => selected?.status === "complete" && setTab("results")}
                disabled={!selected || selected.status !== "complete"}
                className={`px-3 py-1.5 rounded-md text-[12px] font-medium transition-all flex items-center gap-1.5 ${
                  tab === "results"
                    ? "bg-gradient-to-r from-emerald-500/30 to-cyan-500/30 text-white ring-1 ring-emerald-500/30"
                    : selected?.status === "complete"
                    ? "text-slate-400 hover:text-slate-200"
                    : "text-slate-600 cursor-not-allowed"
                }`}
              >
                Results
                {summary?.decision && tab !== "results" && (
                  <span
                    className="text-[9px] font-mono px-1.5 py-0.5 rounded"
                    style={{ background: meta.soft, color: meta.hue }}
                  >
                    {meta.short}
                  </span>
                )}
              </button>
            </div>
            <div className="flex-1" />
            {selected && (
              <div className="text-[11px] text-slate-500 flex items-center gap-2">
                <span className="font-mono">{selected.id.slice(0, 8)}</span>
                <span>·</span>
                <span>{fmtRel(selected.updated_at)}</span>
              </div>
            )}
          </div>

          {/* ─── SETUP ─────────────────────────────────────────────── */}
          {tab === "setup" && (
            <SetupPane
              source={setupSource}
              editable={editable}
              draftMode={draftMode}
              draft={draft}
              setDraftField={setDraftField}
              updateDraftCase={updateDraftCase}
              addCase={addCase}
              removeCase={removeCase}
              rubrics={rubrics}
              creating={creating}
              running={running}
              onCreate={handleCreate}
              onSeed={handleSeed}
              onRun={() => handleRun()}
              onDelete={() => handleDelete()}
              onClear={clearSelection}
            />
          )}

          {/* ─── RESULTS ───────────────────────────────────────────── */}
          {tab === "results" && selected && selected.status === "complete" && summary && (
            <ResultsPane
              selected={selected}
              summary={summary}
              runs={runs}
              caseAbsMax={caseAbsMax}
              sortedCaseRuns={sortedCaseRuns}
              expanded={expanded}
              setExpanded={setExpanded}
              running={running}
              onRerun={() => handleRun()}
              onDelete={() => handleDelete()}
              onExport={exportMarkdown}
            />
          )}
        </div>
      </div>
    </div>
  );
}

// ─── Setup Pane ────────────────────────────────────────────────────────────

function SetupPane({
  source,
  editable,
  draftMode,
  draft,
  setDraftField,
  updateDraftCase,
  addCase,
  removeCase,
  rubrics,
  creating,
  running,
  onCreate,
  onSeed,
  onRun,
  onDelete,
  onClear,
}) {
  const cases = (editable ? draft.test_cases : source.test_cases) || [];
  const championPrompt = editable ? draft.champion_prompt : source.champion_prompt;
  const challengerPrompt = editable ? draft.challenger_prompt : source.challenger_prompt;
  const championLabel = editable ? draft.champion_label : source.champion_label;
  const challengerLabel = editable ? draft.challenger_label : source.challenger_label;

  return (
    <div className="space-y-3">
      {/* Header card */}
      <Card className="bg-slate-900/40 ring-1 ring-white/8 border-0">
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between gap-2">
            <CardTitle className="text-sm text-slate-200 flex items-center gap-2">
              <Target className="w-4 h-4 text-cyan-400" />
              {editable ? "New showdown" : "Setup"}
            </CardTitle>
            {!editable && (
              <Button
                size="sm"
                variant="ghost"
                onClick={onClear}
                className="text-[11px] hover:bg-cyan-500/10"
              >
                <Plus className="w-3.5 h-3.5 mr-1" /> New
              </Button>
            )}
          </div>
        </CardHeader>
        <Separator className="bg-white/8" />
        <CardContent className="space-y-3 pt-3">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
            <div>
              <Label className="text-[11px] uppercase tracking-wider text-slate-400">Name</Label>
              <Input
                value={editable ? draft.name : source.name}
                onChange={(e) => editable && setDraftField("name", e.target.value)}
                placeholder="Customer support — v1 vs v2"
                disabled={!editable}
                className="mt-1 bg-slate-950/50 border-white/8"
              />
            </div>
            <div>
              <Label className="text-[11px] uppercase tracking-wider text-slate-400">
                Description
              </Label>
              <Input
                value={editable ? draft.description : source.description || ""}
                onChange={(e) => editable && setDraftField("description", e.target.value)}
                placeholder="What's changing between Champion and Challenger?"
                disabled={!editable}
                className="mt-1 bg-slate-950/50 border-white/8"
              />
            </div>
          </div>

          {/* Champion vs Challenger — side by side */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
            <div className="rounded-lg bg-amber-500/[0.05] ring-1 ring-amber-500/20 p-3">
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-1.5">
                  <Crown className="w-3.5 h-3.5 text-amber-400" />
                  <span className="text-[10px] uppercase tracking-wider text-amber-300">Champion</span>
                </div>
                <Input
                  value={championLabel}
                  onChange={(e) => editable && setDraftField("champion_label", e.target.value)}
                  disabled={!editable}
                  className="h-6 w-32 text-[11px] bg-slate-950/60 border-amber-500/20"
                />
              </div>
              <Textarea
                value={championPrompt}
                onChange={(e) => editable && setDraftField("champion_prompt", e.target.value)}
                placeholder="The prompt currently in production…"
                disabled={!editable}
                className="font-mono text-[12px] bg-slate-950/60 border-white/8 min-h-[180px]"
              />
            </div>
            <div className="rounded-lg bg-cyan-500/[0.05] ring-1 ring-cyan-500/20 p-3">
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-1.5">
                  <Sparkles className="w-3.5 h-3.5 text-cyan-400" />
                  <span className="text-[10px] uppercase tracking-wider text-cyan-300">Challenger</span>
                </div>
                <Input
                  value={challengerLabel}
                  onChange={(e) => editable && setDraftField("challenger_label", e.target.value)}
                  disabled={!editable}
                  className="h-6 w-32 text-[11px] bg-slate-950/60 border-cyan-500/20"
                />
              </div>
              <Textarea
                value={challengerPrompt}
                onChange={(e) => editable && setDraftField("challenger_prompt", e.target.value)}
                placeholder="The candidate revision you want to ship…"
                disabled={!editable}
                className="font-mono text-[12px] bg-slate-950/60 border-white/8 min-h-[180px]"
              />
            </div>
          </div>

          {/* Bottom controls row */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
            <div>
              <Label className="text-[11px] uppercase tracking-wider text-slate-400">Rubric</Label>
              <Select
                value={editable ? draft.rubric_id || "__none" : source.rubric_id || "__none"}
                onValueChange={(v) => editable && setDraftField("rubric_id", v === "__none" ? "" : v)}
                disabled={!editable}
              >
                <SelectTrigger className="mt-1 bg-slate-950/50 border-white/8">
                  <SelectValue placeholder="No rubric (heuristic)" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none">No rubric — heuristic scoring</SelectItem>
                  {(rubrics || []).map((r) => (
                    <SelectItem key={r.id} value={r.id}>
                      {r.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label className="text-[11px] uppercase tracking-wider text-slate-400">
                Bootstrap iterations
              </Label>
              <Input
                type="number"
                min={200}
                max={20000}
                step={500}
                value={editable ? draft.n_bootstrap : source.n_bootstrap}
                onChange={(e) => editable && setDraftField("n_bootstrap", Number(e.target.value))}
                disabled={!editable}
                className="mt-1 bg-slate-950/50 border-white/8 font-mono"
              />
              <div className="text-[10px] text-slate-500 mt-1">
                Higher = tighter CI. 200–20000.
              </div>
            </div>
            <div className="flex flex-col">
              <Label className="text-[11px] uppercase tracking-wider text-slate-400">Mode</Label>
              <div className="flex items-center gap-2 mt-1 bg-slate-950/50 ring-1 ring-white/8 rounded-md px-3 py-2 flex-1">
                <Switch
                  checked={editable ? draft.dryrun : source.dryrun}
                  onCheckedChange={(v) => editable && setDraftField("dryrun", v)}
                  disabled={!editable}
                />
                <div>
                  <div className="text-[12px] font-medium text-slate-200">
                    {(editable ? draft.dryrun : source.dryrun) ? "Dry-run" : "Live (judge LLM)"}
                  </div>
                  <div className="text-[10px] text-slate-500">
                    {(editable ? draft.dryrun : source.dryrun)
                      ? "No API spend. Deterministic synthetic responses."
                      : "Will spend real API credits on candidate + judge calls."}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Cases card */}
      <Card className="bg-slate-900/40 ring-1 ring-white/8 border-0">
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <CardTitle className="text-sm text-slate-200 flex items-center gap-2">
              <Activity className="w-4 h-4 text-fuchsia-400" />
              Test cases <span className="text-[10px] text-slate-500">({cases.length})</span>
            </CardTitle>
            {editable && (
              <Button
                size="sm"
                variant="ghost"
                onClick={addCase}
                className="text-[11px] hover:bg-fuchsia-500/10"
              >
                <Plus className="w-3.5 h-3.5 mr-1" /> Add case
              </Button>
            )}
          </div>
        </CardHeader>
        <Separator className="bg-white/8" />
        <CardContent className="pt-3 space-y-2">
          {cases.length === 0 && (
            <EmptyState icon={Activity} title="No cases yet" body="Add a case below to compare prompts." />
          )}
          {cases.map((c, i) => (
            <div
              key={i}
              className="rounded-lg bg-slate-950/40 ring-1 ring-white/8 p-2.5 grid grid-cols-1 md:grid-cols-2 gap-2 relative"
            >
              <div>
                <div className="flex items-center justify-between mb-1">
                  <div className="text-[10px] uppercase tracking-wider text-slate-400">
                    Case {i + 1} · Input
                  </div>
                  {editable && (
                    <button
                      onClick={() => removeCase(i)}
                      className="text-rose-400 hover:text-rose-300"
                      title="Remove case"
                    >
                      <Trash2 className="w-3 h-3" />
                    </button>
                  )}
                </div>
                <Textarea
                  value={c.input || ""}
                  onChange={(e) => editable && updateDraftCase(i, "input", e.target.value)}
                  placeholder="The user message…"
                  disabled={!editable}
                  className="min-h-[88px] bg-slate-950/60 border-white/8 text-[12px]"
                />
              </div>
              <div>
                <div className="text-[10px] uppercase tracking-wider text-slate-400 mb-1">
                  Expected (optional)
                </div>
                <Textarea
                  value={c.expected || ""}
                  onChange={(e) => editable && updateDraftCase(i, "expected", e.target.value)}
                  placeholder="What a good response should contain — primes the rubric."
                  disabled={!editable}
                  className="min-h-[88px] bg-slate-950/60 border-white/8 text-[12px]"
                />
              </div>
            </div>
          ))}
        </CardContent>
      </Card>

      {/* Actions */}
      <div className="flex flex-wrap gap-2 pt-1">
        {editable ? (
          <>
            <Button
              onClick={onCreate}
              disabled={creating}
              className="bg-gradient-to-r from-cyan-500 to-fuchsia-500 hover:opacity-90"
            >
              <Swords className="w-3.5 h-3.5 mr-1.5" /> Create showdown
            </Button>
            <Button onClick={onSeed} variant="outline" disabled={creating} className="border-fuchsia-500/30">
              <Beaker className="w-3.5 h-3.5 mr-1.5" /> Seed demo
            </Button>
          </>
        ) : (
          <>
            <Button
              onClick={onRun}
              disabled={running}
              className="bg-gradient-to-r from-emerald-500 to-cyan-500 hover:opacity-90"
            >
              <Play className="w-3.5 h-3.5 mr-1.5" /> {running ? "Running…" : "Run showdown"}
            </Button>
            <Button
              onClick={onDelete}
              variant="outline"
              className="border-rose-500/30 text-rose-300 hover:bg-rose-500/10"
            >
              <Trash2 className="w-3.5 h-3.5 mr-1.5" /> Delete
            </Button>
          </>
        )}
      </div>
    </div>
  );
}

// ─── Results Pane ──────────────────────────────────────────────────────────

function ResultsPane({
  selected,
  summary,
  runs,
  caseAbsMax,
  sortedCaseRuns,
  expanded,
  setExpanded,
  running,
  onRerun,
  onDelete,
  onExport,
}) {
  const meta = decisionMeta(summary.decision);

  return (
    <div className="space-y-3">
      {/* DECISION HERO ---------------------------------------------- */}
      <Card
        className="border-0 relative overflow-hidden"
        style={{
          background: `linear-gradient(135deg, ${meta.soft}, rgba(15,23,42,0.4))`,
          boxShadow: `inset 0 0 0 1px rgba(255,255,255,0.06), 0 0 24px ${meta.hue}22`,
        }}
      >
        <CardContent className="p-4">
          <div className="grid grid-cols-1 lg:grid-cols-[200px_minmax(0,1fr)_220px] gap-4">
            <div>
              <DecisionRing
                decision={summary.decision}
                winRate={summary.win_rate}
                meanDelta={summary.mean_delta}
              />
            </div>
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <div
                  className="text-[10px] uppercase tracking-wider px-2 py-0.5 rounded font-semibold"
                  style={{ background: meta.hue, color: "#020617" }}
                >
                  {meta.label}
                </div>
                {selected.dryrun && (
                  <span className="text-[9px] uppercase tracking-wider bg-violet-500/15 text-violet-300 px-1.5 py-0.5 rounded ring-1 ring-violet-500/20">
                    dry-run
                  </span>
                )}
                <span className="text-[10px] text-slate-500">
                  {fmtRel(selected.updated_at)} · {fmtNum(summary.duration, 2)}s · {fmtCost(summary.total_cost)}
                </span>
              </div>
              <div className="text-base font-semibold text-white">{selected.name}</div>
              <div
                className="text-sm text-slate-300"
                dangerouslySetInnerHTML={{
                  __html: (summary.headline || "")
                    .replace(/\*\*(.+?)\*\*/g, '<strong class="text-white">$1</strong>')
                    .replace(/`([^`]+)`/g, '<code class="text-cyan-300">$1</code>'),
                }}
              />
              <div className="text-[11px] text-slate-400 max-w-prose">{meta.blurb}</div>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-2 pt-1">
                <Tile
                  icon={Crown}
                  label={selected.champion_label}
                  value={fmtNum(summary.champion_composite, 1)}
                  sub="composite /100"
                  hue="#f59e0b"
                />
                <Tile
                  icon={Sparkles}
                  label={selected.challenger_label}
                  value={fmtNum(summary.challenger_composite, 1)}
                  sub="composite /100"
                  hue="#06b6d4"
                />
                <Tile
                  icon={TrendingUp}
                  label="Win rate"
                  value={fmtPct(summary.win_rate, 0)}
                  sub={`${summary.n_wins}/${summary.n_compared} cases`}
                  hue={deltaHue(((summary.win_rate ?? 0.5) - 0.5) * 12)}
                />
                <Tile
                  icon={Sigma}
                  label="Cohen's d"
                  value={fmtNum(summary.effect_size, 2)}
                  sub="paired effect"
                  hue={deltaHue((summary.effect_size ?? 0) * 4)}
                />
              </div>
            </div>
            <div className="flex flex-col gap-2">
              <Button
                onClick={onRerun}
                disabled={running}
                className="bg-gradient-to-r from-emerald-500 to-cyan-500 hover:opacity-90"
              >
                <RotateCcw className="w-3.5 h-3.5 mr-1.5" /> Re-run
              </Button>
              <Button
                onClick={onExport}
                variant="outline"
                className="border-white/10 hover:bg-white/5"
              >
                <Download className="w-3.5 h-3.5 mr-1.5" /> Markdown digest
              </Button>
              <Button
                onClick={onDelete}
                variant="outline"
                className="border-rose-500/30 text-rose-300 hover:bg-rose-500/10"
              >
                <Trash2 className="w-3.5 h-3.5 mr-1.5" /> Delete
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* FOREST PLOT --------------------------------------------- */}
      <Card className="bg-slate-900/40 ring-1 ring-white/8 border-0">
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <CardTitle className="text-sm text-slate-200 flex items-center gap-2">
              <Sigma className="w-4 h-4 text-emerald-400" />
              Effect-size forest plot
            </CardTitle>
            <div className="flex items-center gap-1.5 text-[10px] text-slate-500 font-mono">
              <span>bootstrap n=</span>
              <span className="text-emerald-300">{summary.n_bootstrap}</span>
              <span>·</span>
              <span>p<sub>sign</sub>=</span>
              <span className="text-emerald-300">{fmtNum(summary.p_value_sign, 4)}</span>
            </div>
          </div>
        </CardHeader>
        <Separator className="bg-white/8" />
        <CardContent className="pt-3 space-y-3">
          <div className="rounded-lg bg-slate-950/40 ring-1 ring-white/8 px-4 py-4">
            <div className="text-[10px] uppercase tracking-wider text-slate-400 flex justify-between mb-2">
              <span>Mean Δ + 95% bootstrap CI</span>
              <span className="font-mono" style={{ color: deltaHue(summary.mean_delta) }}>
                {fmtSigned(summary.mean_delta)} <span className="text-slate-500">[{fmtSigned(summary.ci_low)} … {fmtSigned(summary.ci_high)}]</span>
              </span>
            </div>
            <DeltaBar
              value={summary.mean_delta}
              ciLow={summary.ci_low}
              ciHigh={summary.ci_high}
              absMax={Math.max(8, caseAbsMax)}
              height={16}
              label={`Δ ${fmtSigned(summary.mean_delta)}`}
            />
            <div className="grid grid-cols-3 gap-2 mt-3">
              <div className="rounded-md bg-slate-900/60 ring-1 ring-white/8 px-2 py-1.5">
                <div className="text-[9px] uppercase tracking-wider text-slate-400">CI excludes 0?</div>
                <div className="text-[12px] font-medium mt-0.5">
                  {summary.ci_low != null && summary.ci_high != null
                    ? (summary.ci_low > 0 || summary.ci_high < 0
                      ? <span className="text-emerald-400">yes</span>
                      : <span className="text-amber-400">no (straddles)</span>)
                    : "—"}
                </div>
              </div>
              <div className="rounded-md bg-slate-900/60 ring-1 ring-white/8 px-2 py-1.5">
                <div className="text-[9px] uppercase tracking-wider text-slate-400">Sign test</div>
                <div className="text-[12px] font-medium mt-0.5">
                  {summary.p_value_sign != null
                    ? (summary.p_value_sign < 0.05
                      ? <span className="text-emerald-400">{fmtNum(summary.p_value_sign, 4)} ✓</span>
                      : <span className="text-amber-400">{fmtNum(summary.p_value_sign, 4)} ✗</span>)
                    : "—"}
                </div>
              </div>
              <div className="rounded-md bg-slate-900/60 ring-1 ring-white/8 px-2 py-1.5">
                <div className="text-[9px] uppercase tracking-wider text-slate-400">Cases compared</div>
                <div className="text-[12px] font-medium mt-0.5 font-mono">
                  {summary.n_compared}/{summary.n_cases}
                </div>
              </div>
            </div>
          </div>

          <WLTPills
            nWins={summary.n_wins}
            nLosses={summary.n_losses}
            nTies={summary.n_ties}
            champLabel={selected.champion_label}
            chalLabel={selected.challenger_label}
          />
        </CardContent>
      </Card>

      {/* PER-DIMENSION (rubric only) ------------------------------ */}
      {summary.dim_summary && summary.dim_summary.length > 0 && summary.dim_summary.some((d) => d.n > 0) && (
        <Card className="bg-slate-900/40 ring-1 ring-white/8 border-0">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-slate-200 flex items-center gap-2">
              <Award className="w-4 h-4 text-fuchsia-400" />
              Per-dimension impact (challenger − champion)
            </CardTitle>
          </CardHeader>
          <Separator className="bg-white/8" />
          <CardContent className="pt-3 grid grid-cols-1 md:grid-cols-2 gap-2">
            {summary.dim_summary
              .filter((d) => d.n > 0)
              .map((d) => (
                <div
                  key={d.name}
                  className="rounded-lg bg-slate-950/40 ring-1 ring-white/8 px-3 py-2"
                >
                  <div className="flex items-center justify-between mb-1.5">
                    <div className="flex items-center gap-2">
                      <span className="text-[12px] font-medium text-slate-200">{d.name}</span>
                      <span className="text-[10px] text-slate-500 font-mono">
                        w={d.weight}
                      </span>
                    </div>
                    <span
                      className="text-[11px] font-mono font-semibold"
                      style={{ color: deltaHue(d.mean_delta * 5) }}
                    >
                      Δ {fmtSigned(d.mean_delta, 2)}
                    </span>
                  </div>
                  <DeltaBar value={d.mean_delta} absMax={3} height={8} />
                  <div className="flex justify-between text-[10px] text-slate-500 font-mono mt-1.5">
                    <span>worst {fmtSigned(d.worst_delta, 2)}</span>
                    <span>best {fmtSigned(d.best_delta, 2)}</span>
                    <span>n={d.n}</span>
                  </div>
                </div>
              ))}
          </CardContent>
        </Card>
      )}

      {/* PER-CASE STRIP ------------------------------------------ */}
      <Card className="bg-slate-900/40 ring-1 ring-white/8 border-0">
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <CardTitle className="text-sm text-slate-200 flex items-center gap-2">
              <Activity className="w-4 h-4 text-cyan-400" />
              Per-case results
              <span className="text-[10px] text-slate-500 font-mono">
                sorted worst → best for challenger
              </span>
            </CardTitle>
            <div className="text-[10px] text-slate-500 font-mono">|Δ|≤{caseAbsMax}</div>
          </div>
        </CardHeader>
        <Separator className="bg-white/8" />
        <CardContent className="pt-3 space-y-2">
          {sortedCaseRuns.map((r) => {
            const open = !!expanded[r.id];
            const outIcon =
              r.outcome === "challenger_win" ? ArrowUp :
              r.outcome === "champion_win"  ? ArrowDown :
              r.outcome === "tie"            ? Equal     : AlertCircle;
            const outHue = deltaHue(r.delta ?? 0);
            const OutIcon = outIcon;
            return (
              <div
                key={r.id}
                className="rounded-lg bg-slate-950/40 ring-1 ring-white/8 overflow-hidden"
              >
                <button
                  onClick={() =>
                    setExpanded((e) => ({ ...e, [r.id]: !e[r.id] }))
                  }
                  className="w-full px-3 py-2 flex items-center gap-3 hover:bg-slate-800/40"
                >
                  <div className="text-[10px] font-mono text-slate-500 w-8 text-right">
                    #{r.case_idx + 1}
                  </div>
                  <OutIcon className="w-4 h-4 flex-shrink-0" style={{ color: outHue }} />
                  <div className="text-[12px] text-slate-200 truncate flex-1 text-left">
                    {(r.case_input || "(no input)").slice(0, 96)}
                    {r.case_input && r.case_input.length > 96 ? "…" : ""}
                  </div>
                  <div className="flex items-center gap-1.5 text-[10px] font-mono">
                    <span className="text-amber-300">{fmtNum(r.champion_composite, 1)}</span>
                    <ArrowRight className="w-3 h-3 text-slate-500" />
                    <span className="text-cyan-300">{fmtNum(r.challenger_composite, 1)}</span>
                  </div>
                  <div
                    className="w-28 text-right text-[11px] font-mono font-semibold"
                    style={{ color: outHue }}
                  >
                    Δ {fmtSigned(r.delta)}
                  </div>
                  {open ? (
                    <ChevronDown className="w-3.5 h-3.5 text-slate-500" />
                  ) : (
                    <ChevronRight className="w-3.5 h-3.5 text-slate-500" />
                  )}
                </button>
                <div className="px-3 pb-2">
                  <DeltaBar value={r.delta} absMax={caseAbsMax} height={6} />
                </div>
                {open && <CaseExpanded run={r} selected={selected} />}
              </div>
            );
          })}
          {!runs.length && (
            <EmptyState icon={Activity} title="No case results" body="Run the showdown to see per-case deltas." />
          )}
        </CardContent>
      </Card>
    </div>
  );
}

// ─── Per-case expand ───────────────────────────────────────────────────────

function CaseExpanded({ run, selected }) {
  return (
    <div className="bg-slate-950/60 px-3 py-3 grid grid-cols-1 lg:grid-cols-2 gap-3 border-t border-white/8">
      <div className="rounded-md bg-amber-500/[0.04] ring-1 ring-amber-500/20 p-2.5">
        <div className="flex items-center justify-between mb-1.5">
          <div className="flex items-center gap-1.5">
            <Crown className="w-3 h-3 text-amber-400" />
            <span className="text-[10px] uppercase tracking-wider text-amber-300">
              {selected.champion_label} response
            </span>
          </div>
          <span className="text-[11px] font-mono text-amber-300">
            {fmtNum(run.champion_composite, 1)}
          </span>
        </div>
        <div className="font-mono text-[11px] text-slate-300 whitespace-pre-wrap max-h-[260px] overflow-y-auto">
          {run.champion_response || "(no response)"}
        </div>
        {run.champion_dim && run.champion_dim.length > 0 && (
          <div className="grid grid-cols-2 gap-1 mt-2">
            {run.champion_dim.map((d) => (
              <div key={d.name} className="flex items-center justify-between text-[10px] font-mono">
                <span className="text-slate-400">{d.name}</span>
                <span className="text-amber-300">{d.score}/10</span>
              </div>
            ))}
          </div>
        )}
      </div>
      <div className="rounded-md bg-cyan-500/[0.04] ring-1 ring-cyan-500/20 p-2.5">
        <div className="flex items-center justify-between mb-1.5">
          <div className="flex items-center gap-1.5">
            <Sparkles className="w-3 h-3 text-cyan-400" />
            <span className="text-[10px] uppercase tracking-wider text-cyan-300">
              {selected.challenger_label} response
            </span>
          </div>
          <span className="text-[11px] font-mono text-cyan-300">
            {fmtNum(run.challenger_composite, 1)}
          </span>
        </div>
        <div className="font-mono text-[11px] text-slate-300 whitespace-pre-wrap max-h-[260px] overflow-y-auto">
          {run.challenger_response || "(no response)"}
        </div>
        {run.challenger_dim && run.challenger_dim.length > 0 && (
          <div className="grid grid-cols-2 gap-1 mt-2">
            {run.challenger_dim.map((d) => {
              const champD = (run.champion_dim || []).find((x) => x.name === d.name);
              const delta = champD ? d.score - champD.score : null;
              return (
                <div key={d.name} className="flex items-center justify-between text-[10px] font-mono">
                  <span className="text-slate-400">{d.name}</span>
                  <span className="text-cyan-300">
                    {d.score}/10
                    {delta != null && (
                      <span className="ml-1" style={{ color: deltaHue(delta * 4) }}>
                        ({fmtSigned(delta, 0)})
                      </span>
                    )}
                  </span>
                </div>
              );
            })}
          </div>
        )}
      </div>
      {run.case_expected && (
        <div className="lg:col-span-2 rounded-md bg-slate-900/40 ring-1 ring-white/8 p-2.5">
          <div className="text-[10px] uppercase tracking-wider text-slate-400 mb-1">
            Expected
          </div>
          <div className="text-[11px] text-slate-300 italic">{run.case_expected}</div>
        </div>
      )}
      {run.error && (
        <div className="lg:col-span-2 rounded-md bg-rose-500/10 ring-1 ring-rose-500/30 p-2.5 text-[11px] text-rose-300">
          {run.error}
        </div>
      )}
    </div>
  );
}
