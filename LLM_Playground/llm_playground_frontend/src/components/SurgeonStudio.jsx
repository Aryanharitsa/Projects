import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Scissors,
  Sparkles,
  Play,
  Plus,
  Trash2,
  RotateCcw,
  Search,
  Copy,
  AlertTriangle,
  Activity,
  TrendingUp,
  TrendingDown,
  Beaker,
  DollarSign,
  Coins,
  ListChecks,
  Layers,
  CheckCircle2,
  XCircle,
  ChevronRight,
  ChevronDown,
  Crosshair,
  FileText,
  Wand2,
} from "lucide-react";
import { toast } from "sonner";
import ApiService from "../services/api";

// ─── Constants — mirror backend ────────────────────────────────────────────

const BAND_META = {
  critical:     { label: "Critical",    hue: "#e11d48", soft: "#ffe4e6", text: "text-rose-700",   ring: "ring-rose-200",   chip: "bg-rose-100 text-rose-700"   },
  supporting:   { label: "Supporting",  hue: "#f59e0b", soft: "#fef3c7", text: "text-amber-700",  ring: "ring-amber-200",  chip: "bg-amber-100 text-amber-700" },
  "dead-weight":{ label: "Dead weight", hue: "#64748b", soft: "#f1f5f9", text: "text-slate-600",  ring: "ring-slate-200",  chip: "bg-slate-100 text-slate-700" },
  harmful:      { label: "Harmful",     hue: "#8b5cf6", soft: "#ede9fe", text: "text-violet-700", ring: "ring-violet-200", chip: "bg-violet-100 text-violet-700" },
  unknown:      { label: "Unknown",     hue: "#94a3b8", soft: "#f8fafc", text: "text-slate-500",  ring: "ring-slate-200",  chip: "bg-slate-100 text-slate-600" },
};

const PROVIDER_MODELS = {
  OpenAI:    ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"],
  Anthropic: ["claude-opus-4-8", "claude-sonnet-4-6", "claude-haiku-4-5-20251001"],
  Google:    ["gemini-2.5-pro", "gemini-2.5-flash"],
};

const KIND_GLYPH = {
  heading:         "§",
  "heading-block": "§",
  paragraph:       "¶",
  "list-item":     "•",
  "sentence-group":"…",
};

// ─── Helpers ───────────────────────────────────────────────────────────────

const fmtNum = (n, d = 1) => (n == null ? "—" : Number(n).toFixed(d));
const fmtPct = (n) => (n == null ? "—" : `${Number(n).toFixed(0)}%`);
const fmtMoney = (n) => {
  if (n == null) return "—";
  const v = Number(n);
  if (Math.abs(v) >= 1000) return `$${(v / 1000).toFixed(1)}k`;
  if (Math.abs(v) >= 1) return `$${v.toFixed(2)}`;
  return `$${v.toFixed(3)}`;
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

// ─── Tiny UI atoms ─────────────────────────────────────────────────────────

const ScoreRing = ({ value, size = 92, label = "" }) => {
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

const BandPill = ({ band }) => {
  const meta = BAND_META[band] || BAND_META.unknown;
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

// ─── Section card — the workhorse of the studio ───────────────────────────

const SectionCard = ({ sec, maxTok }) => {
  const [open, setOpen] = useState(false);
  const meta = BAND_META[sec.band] || BAND_META.unknown;
  const widthPct = maxTok ? Math.max(8, Math.min(100, (sec.tokens / maxTok) * 100)) : 0;
  const load = sec.load_score == null ? null : sec.load_score;
  const loadAbs = load == null ? 0 : Math.min(40, Math.abs(load));
  const loadPct = (loadAbs / 40) * 100;
  return (
    <div
      className={`rounded-xl border bg-white/95 ring-1 ${meta.ring} shadow-sm hover:shadow-md transition-shadow`}
      style={{ borderLeft: `4px solid ${meta.hue}` }}
    >
      <div
        className="px-3 py-2.5 cursor-pointer select-none flex items-start gap-3"
        onClick={() => setOpen(o => !o)}
      >
        <div className="text-base text-slate-400 mt-0.5 w-4 text-center font-mono">
          {KIND_GLYPH[sec.kind] || "·"}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between gap-2">
            <div className="text-[11px] uppercase tracking-wide text-slate-500 truncate">
              #{sec.section_index + 1} · {sec.kind.replace("-", " ")}
            </div>
            <div className="flex items-center gap-1.5 shrink-0">
              <BandPill band={sec.band} />
              {open ? <ChevronDown className="w-3.5 h-3.5 text-slate-400" /> : <ChevronRight className="w-3.5 h-3.5 text-slate-400" />}
            </div>
          </div>
          <div className="font-semibold text-slate-800 truncate mt-0.5">{sec.title || "(untitled)"}</div>
          {/* Load + tokens bars */}
          <div className="mt-2 grid grid-cols-[60px_1fr_44px] gap-2 items-center">
            <div className="text-[9px] uppercase tracking-wider text-slate-500">Tokens</div>
            <div className="h-1.5 rounded-full bg-slate-100 overflow-hidden">
              <div className="h-full rounded-full bg-slate-400/70" style={{ width: `${widthPct}%` }} />
            </div>
            <div className="text-[10px] text-right font-mono text-slate-600">{sec.tokens}</div>

            <div className="text-[9px] uppercase tracking-wider text-slate-500">Load</div>
            <div className="h-2 rounded-full bg-slate-100 overflow-hidden relative">
              {load != null && (
                <div
                  className="h-full rounded-full"
                  style={{
                    width: `${loadPct}%`,
                    background: meta.hue,
                    marginLeft: load < 0 ? `${50 - loadPct / 2}%` : "0%",
                  }}
                />
              )}
            </div>
            <div className={`text-[10px] text-right font-mono font-semibold ${meta.text}`}>
              {load == null ? "—" : `${load >= 0 ? "+" : ""}${load.toFixed(1)}`}
            </div>
          </div>
        </div>
      </div>
      {open && (
        <div className="border-t border-slate-100 px-3 py-2.5 text-[12px] space-y-2 bg-slate-50/60 rounded-b-xl">
          <div className="text-slate-700 italic">{sec.rationale}</div>
          <div>
            <div className="text-[10px] uppercase tracking-wide text-slate-500 mb-1 font-semibold">Section content</div>
            <pre className="whitespace-pre-wrap text-[11px] bg-white border border-slate-200 rounded p-2 text-slate-700 max-h-32 overflow-auto">
              {sec.content || "(empty)"}
            </pre>
          </div>
          {sec.medoid_sample && (
            <div>
              <div className="text-[10px] uppercase tracking-wide text-slate-500 mb-1 font-semibold">
                Medoid response when this section is removed
              </div>
              <pre className="whitespace-pre-wrap text-[11px] bg-white border border-slate-200 rounded p-2 text-slate-700 max-h-32 overflow-auto">
                {sec.medoid_sample}
              </pre>
            </div>
          )}
          <div className="flex items-center gap-3 text-[10px] text-slate-500">
            <span>Baseline {fmtNum(sec.baseline_score, 1)}</span>
            <span>→</span>
            <span>Ablated {fmtNum(sec.ablated_score, 1)}</span>
          </div>
        </div>
      )}
    </div>
  );
};

// ─── Main component ───────────────────────────────────────────────────────

const SurgeonStudio = () => {
  // ----- Run-list state -----
  const [runs, setRuns] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [activeRun, setActiveRun] = useState(null);
  const [loadingList, setLoadingList] = useState(false);
  const [loadingRun, setLoadingRun] = useState(false);
  const [seeding, setSeeding] = useState(false);
  const [searchQ, setSearchQ] = useState("");
  const [statsData, setStatsData] = useState(null);
  const [stats, setStats] = useState({ total_runs: 0, completed_runs: 0 });

  // ----- Editor state for create-new -----
  const [editorOpen, setEditorOpen] = useState(false);
  const [draftName, setDraftName] = useState("");
  const [draftDesc, setDraftDesc] = useState("");
  const [draftSystem, setDraftSystem] = useState("");
  const [draftUser, setDraftUser] = useState("");
  const [draftProvider, setDraftProvider] = useState("OpenAI");
  const [draftModel, setDraftModel] = useState("gpt-4o-mini");
  const [draftTemp, setDraftTemp] = useState(0.4);
  const [draftReplays, setDraftReplays] = useState(3);
  const [draftMonthlyCalls, setDraftMonthlyCalls] = useState(50000);
  const [draftDry, setDraftDry] = useState(true);
  const [parsePreview, setParsePreview] = useState(null);
  const [creating, setCreating] = useState(false);

  // ----- Run-execute state -----
  const [running, setRunning] = useState(false);

  // Initial bootstrap.
  useEffect(() => {
    refresh();
    refreshStats();
  }, []);

  const refresh = useCallback(async () => {
    setLoadingList(true);
    try {
      const res = await ApiService.listSurgeons({ q: searchQ || undefined, limit: 100 });
      if (!res.success) throw new Error(res.error || "list failed");
      setRuns(res.surgeons || []);
      if (!selectedId && res.surgeons?.length) {
        setSelectedId(res.surgeons[0].id);
      }
    } catch (e) {
      toast.error(`List error: ${e.message}`);
    } finally {
      setLoadingList(false);
    }
  }, [searchQ, selectedId]);

  const refreshStats = useCallback(async () => {
    try {
      const res = await ApiService.surgeonStats();
      if (res.success) {
        setStats(res.stats || { total_runs: 0, completed_runs: 0 });
        setStatsData(res.stats);
      }
    } catch (e) { /* non-fatal */ }
  }, []);

  // Load full run when selection changes.
  useEffect(() => {
    if (!selectedId) {
      setActiveRun(null);
      return;
    }
    let cancelled = false;
    setLoadingRun(true);
    ApiService.getSurgeon(selectedId)
      .then(res => { if (!cancelled && res.success) setActiveRun(res.surgeon); })
      .catch(e => toast.error(`Run load error: ${e.message}`))
      .finally(() => { if (!cancelled) setLoadingRun(false); });
    return () => { cancelled = true; };
  }, [selectedId]);

  // Re-search whenever the search query changes (debounced lightly).
  useEffect(() => {
    const t = setTimeout(() => { refresh(); }, 250);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchQ]);

  // ── Editor preview: re-parse on prompt change (debounced) ──
  useEffect(() => {
    if (!editorOpen) return;
    if (!draftSystem.trim()) { setParsePreview(null); return; }
    const t = setTimeout(() => {
      ApiService.surgeonParse(draftSystem)
        .then(res => { if (res.success) setParsePreview(res); })
        .catch(() => setParsePreview(null));
    }, 350);
    return () => clearTimeout(t);
  }, [draftSystem, editorOpen]);

  // ── Actions ─────────────────────────────────────────────────────────────

  const seedDemo = async () => {
    setSeeding(true);
    try {
      const res = await ApiService.seedSurgeon();
      if (!res.success) throw new Error(res.error || "seed failed");
      toast.success("Demo seeded — bloated support prompt is loaded");
      await refresh();
      await refreshStats();
      setSelectedId(res.surgeon?.id || null);
    } catch (e) {
      toast.error(`Seed error: ${e.message}`);
    } finally {
      setSeeding(false);
    }
  };

  const createRun = async () => {
    if (!draftName.trim()) return toast.error("Name required");
    if (!draftSystem.trim()) return toast.error("System prompt required");
    if (!draftUser.trim()) return toast.error("User prompt required");
    setCreating(true);
    try {
      const res = await ApiService.createSurgeon({
        name: draftName.trim(),
        description: draftDesc.trim(),
        system_prompt: draftSystem,
        user_prompt: draftUser,
        candidate_provider: draftProvider,
        candidate_model: draftModel,
        temperature: draftTemp,
        n_replays: draftReplays,
        monthly_calls: draftMonthlyCalls,
        dryrun: draftDry,
      });
      if (!res.success) throw new Error(res.error || "create failed");
      toast.success("Surgeon run created — hit Run to execute");
      setEditorOpen(false);
      setDraftName(""); setDraftDesc(""); setDraftSystem(""); setDraftUser("");
      await refresh();
      setSelectedId(res.surgeon?.id || null);
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
      const res = await ApiService.runSurgeon(activeRun.id, { confirm_live: !activeRun.dryrun });
      if (!res.success) throw new Error(res.error || "run failed");
      toast.success(`Ablation done — saved ${res.surgeon?.tokens_saved} tokens`);
      setActiveRun(res.surgeon);
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
      await ApiService.deleteSurgeon(activeRun.id);
      toast.success("Deleted");
      setSelectedId(null);
      setActiveRun(null);
      await refresh();
      await refreshStats();
    } catch (e) {
      toast.error(`Delete error: ${e.message}`);
    }
  };

  const copyLeanPrompt = () => {
    const text = activeRun?.summary?.lean_prompt || "";
    if (!text) return toast.error("No lean prompt yet — run the ablation first");
    navigator.clipboard?.writeText(text);
    toast.success("Lean prompt copied");
  };

  const downloadJson = () => {
    if (!activeRun) return;
    const blob = new Blob([JSON.stringify(activeRun, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `surgeon_${activeRun.id}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  // ── Derived ────────────────────────────────────────────────────────────

  const maxTok = useMemo(() => {
    const arr = activeRun?.sections || parsePreview?.sections || [];
    return arr.reduce((m, s) => Math.max(m, s.tokens || 0), 0) || 1;
  }, [activeRun, parsePreview]);

  const bandCounts = useMemo(() => ({
    critical:     activeRun?.critical_count || 0,
    supporting:   activeRun?.supporting_count || 0,
    "dead-weight":activeRun?.dead_weight_count || 0,
    harmful:      activeRun?.harmful_count || 0,
  }), [activeRun]);

  // Token stack-bar (proportional widths by band).
  const tokenStack = useMemo(() => {
    if (!activeRun?.sections?.length) return [];
    const totalTok = activeRun.sections.reduce((s, x) => s + (x.tokens || 0), 0) || 1;
    const buckets = {};
    activeRun.sections.forEach(s => {
      const b = s.band || "unknown";
      buckets[b] = (buckets[b] || 0) + (s.tokens || 0);
    });
    return Object.entries(buckets)
      .filter(([, v]) => v > 0)
      .map(([band, tokens]) => ({
        band, tokens, pct: (tokens / totalTok) * 100,
      }))
      .sort((a, b) => {
        const order = { critical: 0, supporting: 1, "dead-weight": 2, harmful: 3, unknown: 4 };
        return (order[a.band] ?? 9) - (order[b.band] ?? 9);
      });
  }, [activeRun]);

  // ── Render ─────────────────────────────────────────────────────────────

  return (
    <div className="space-y-6">
      {/* Header */}
      <Card className="border-0 shadow-md bg-gradient-to-br from-rose-50 via-amber-50 to-violet-50">
        <CardContent className="p-5">
          <div className="flex items-start justify-between gap-4 flex-wrap">
            <div className="flex items-start gap-3">
              <div className="p-2.5 rounded-xl bg-gradient-to-br from-rose-500 to-violet-500 shadow-lg">
                <Scissors className="w-6 h-6 text-white" />
              </div>
              <div>
                <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.18em] text-rose-700 font-bold">
                  Round 15 · Day 68
                  <span className="px-1.5 py-0.5 rounded text-white bg-gradient-to-r from-rose-500 to-violet-500">NEW</span>
                </div>
                <h2 className="text-2xl font-extrabold tracking-tight text-slate-900">
                  Prompt Surgeon
                </h2>
                <p className="text-sm text-slate-600 max-w-2xl">
                  Section-level ablation & attribution. Every paragraph gets a load score —
                  drop the dead weight, keep the load-bearers, ship a shorter prompt for the same
                  (or better) answer.
                </p>
              </div>
            </div>
            <div className="flex flex-col gap-2 items-stretch">
              <div className="flex gap-2">
                <Button
                  size="sm"
                  onClick={() => setEditorOpen(true)}
                  className="bg-gradient-to-r from-rose-600 to-violet-600 hover:from-rose-700 hover:to-violet-700 text-white gap-1"
                >
                  <Plus className="w-3.5 h-3.5" /> New ablation
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
                <div className="rounded-lg bg-white/80 ring-1 ring-rose-100 px-2 py-1">
                  <div className="uppercase tracking-wide text-[9px] text-slate-500">Runs</div>
                  <div className="font-bold">{stats.total_runs || 0}</div>
                </div>
                <div className="rounded-lg bg-white/80 ring-1 ring-violet-100 px-2 py-1">
                  <div className="uppercase tracking-wide text-[9px] text-slate-500">Tokens saved</div>
                  <div className="font-bold">{stats.total_tokens_saved || 0}</div>
                </div>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      <div className="grid grid-cols-12 gap-4">
        {/* Left rail: run list */}
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
                    No runs yet. Hit <b>Seed demo</b> to load a bloated 600-token support
                    prompt and watch Surgeon find the 35% you can cut.
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
                            ? "bg-rose-50 border-rose-300 ring-2 ring-rose-200"
                            : "bg-white border-slate-200 hover:border-rose-200 hover:bg-rose-50/50"
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
                          <span>{r.total_sections || "–"} sec</span>
                          {r.tokens_saved ? (
                            <span className="text-emerald-700 font-semibold">−{r.tokens_saved} tok</span>
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

        {/* Right: detail view */}
        <div className="col-span-12 lg:col-span-9 space-y-4">
          {!activeRun && !loadingRun && (
            <Card className="border-dashed border-2 border-slate-200 bg-white/60">
              <CardContent className="py-16 text-center space-y-3">
                <div className="inline-flex p-4 rounded-full bg-gradient-to-br from-rose-100 to-violet-100">
                  <Scissors className="w-8 h-8 text-rose-600" />
                </div>
                <h3 className="text-lg font-bold text-slate-800">Pick a run or seed a demo</h3>
                <p className="text-sm text-slate-500 max-w-md mx-auto">
                  Surgeon parses your system prompt into sections, ablates each one, and tells you
                  which ones are doing real work. Then it ships you a leaner prompt and a monthly
                  $ savings projection.
                </p>
                <div className="flex justify-center gap-2 pt-2">
                  <Button onClick={() => setEditorOpen(true)} className="bg-gradient-to-r from-rose-600 to-violet-600 text-white gap-1">
                    <Plus className="w-3.5 h-3.5" /> New ablation
                  </Button>
                  <Button variant="outline" onClick={seedDemo} disabled={seeding} className="gap-1">
                    <Sparkles className="w-3.5 h-3.5" /> Seed demo
                  </Button>
                </div>
              </CardContent>
            </Card>
          )}

          {loadingRun && (
            <div className="text-sm text-slate-500">Loading run…</div>
          )}

          {activeRun && (
            <>
              {/* Active hero */}
              <Card className="border-0 shadow-md bg-white/95">
                <CardContent className="p-5">
                  <div className="flex items-start justify-between gap-4 flex-wrap">
                    <div className="min-w-0">
                      <div className="text-[10px] uppercase tracking-[0.18em] text-slate-500 font-bold">
                        {activeRun.candidate_provider || "—"} · {activeRun.candidate_model || "—"} · T={activeRun.temperature} · {activeRun.n_replays} replays
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
                        className="bg-gradient-to-r from-rose-600 to-violet-600 text-white gap-1"
                      >
                        <Play className="w-3.5 h-3.5" /> {running ? "Running…" : (activeRun.status === "succeeded" ? "Re-run" : "Run")}
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
                        <ScoreRing value={activeRun.baseline_score} size={88} label="baseline" />
                      </div>
                      <div className="flex flex-col items-center gap-1 text-rose-600 font-bold">
                        <Crosshair className="w-5 h-5" />
                        <span className="text-[10px] uppercase tracking-wider">Surgeon</span>
                      </div>
                      <div className="flex items-center gap-5 flex-wrap">
                        <ScoreRing value={activeRun.lean_score} size={88} label="lean" />
                        <div className="grid grid-cols-2 gap-2 flex-1 min-w-[260px]">
                          <StatTile
                            icon={Coins}
                            label="Tokens saved"
                            value={`${activeRun.tokens_saved || 0}`}
                            sub={`${activeRun.original_tokens} → ${activeRun.lean_tokens}`}
                            tone="emerald"
                          />
                          <StatTile
                            icon={DollarSign}
                            label="Monthly savings"
                            value={fmtMoney(activeRun.monthly_savings)}
                            sub={`@${(activeRun.monthly_calls || 0).toLocaleString()} calls/mo`}
                            tone="amber"
                          />
                          <StatTile
                            icon={Layers}
                            label="Sections"
                            value={`${activeRun.total_sections || 0}`}
                            sub={`${activeRun.summary?.pct_kept != null ? `${activeRun.summary.pct_kept}% kept` : "—"}`}
                            tone="slate"
                          />
                          <StatTile
                            icon={activeRun.lean_score > activeRun.baseline_score ? TrendingUp : Activity}
                            label="Quality delta"
                            value={`${activeRun.lean_score >= activeRun.baseline_score ? "+" : ""}${fmtNum(activeRun.lean_score - activeRun.baseline_score, 1)}`}
                            sub="vs baseline"
                            tone={activeRun.lean_score >= activeRun.baseline_score ? "emerald" : "rose"}
                          />
                        </div>
                      </div>
                    </div>
                  )}

                  {/* Band breakdown */}
                  {activeRun.status === "succeeded" && (
                    <>
                      <div className="mt-5">
                        <div className="text-[10px] uppercase tracking-wide text-slate-500 font-bold mb-1.5">
                          Band breakdown
                        </div>
                        <div className="h-3 w-full rounded-full overflow-hidden flex bg-slate-100">
                          {tokenStack.map(({ band, pct }) => (
                            <div
                              key={band}
                              className="h-full"
                              title={`${BAND_META[band]?.label || band}: ${pct.toFixed(1)}% of tokens`}
                              style={{ width: `${pct}%`, background: BAND_META[band]?.hue || "#cbd5e1" }}
                            />
                          ))}
                        </div>
                        <div className="mt-2 flex flex-wrap gap-1.5">
                          {Object.entries(bandCounts).map(([band, count]) => (
                            <div
                              key={band}
                              className="text-[10px] px-2 py-1 rounded-full bg-slate-50 ring-1 ring-slate-200 flex items-center gap-1.5"
                            >
                              <span className="w-1.5 h-1.5 rounded-full" style={{ background: BAND_META[band]?.hue }} />
                              <span className="font-semibold text-slate-700">{BAND_META[band]?.label}</span>
                              <span className="font-mono text-slate-500">{count}</span>
                            </div>
                          ))}
                        </div>
                      </div>

                      {/* Action strip */}
                      {activeRun.summary?.actions?.length > 0 && (
                        <div className="mt-5 rounded-xl bg-gradient-to-br from-violet-50 to-rose-50 ring-1 ring-violet-200 p-3">
                          <div className="text-[10px] uppercase tracking-wider text-violet-700 font-bold mb-1.5 flex items-center gap-1">
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
                    </>
                  )}
                </CardContent>
              </Card>

              {/* Sections grid */}
              {activeRun.status === "succeeded" && (
                <Card className="border-0 shadow-md bg-white/95">
                  <CardHeader className="pb-2">
                    <CardTitle className="text-xs uppercase tracking-wider text-slate-500 flex items-center gap-2">
                      <Layers className="w-3.5 h-3.5" /> Sections — load attribution
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5">
                      {(activeRun.sections || []).map(s => (
                        <SectionCard key={s.id || s.section_index} sec={s} maxTok={maxTok} />
                      ))}
                    </div>
                  </CardContent>
                </Card>
              )}

              {/* Lean prompt diff */}
              {activeRun.status === "succeeded" && activeRun.summary?.lean_prompt && (
                <Card className="border-0 shadow-md bg-white/95">
                  <CardHeader className="pb-2 flex flex-row items-center justify-between">
                    <CardTitle className="text-xs uppercase tracking-wider text-slate-500 flex items-center gap-2">
                      <Scissors className="w-3.5 h-3.5" /> Lean prompt — paste-ready
                    </CardTitle>
                    <Button size="sm" variant="outline" onClick={copyLeanPrompt} className="gap-1 h-7">
                      <Copy className="w-3.5 h-3.5" /> Copy
                    </Button>
                  </CardHeader>
                  <CardContent>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                      <div>
                        <div className="text-[10px] uppercase tracking-wider text-slate-500 mb-1 font-bold flex items-center gap-1">
                          <FileText className="w-3 h-3" /> Original
                          <span className="font-normal text-slate-400 normal-case">
                            · {activeRun.original_tokens} tokens
                          </span>
                        </div>
                        <pre className="text-[11px] leading-relaxed bg-slate-50 border border-slate-200 rounded-lg p-3 whitespace-pre-wrap max-h-96 overflow-auto text-slate-700">
                          {activeRun.system_prompt}
                        </pre>
                      </div>
                      <div>
                        <div className="text-[10px] uppercase tracking-wider text-emerald-700 mb-1 font-bold flex items-center gap-1">
                          <CheckCircle2 className="w-3 h-3" /> Lean
                          <span className="font-normal text-slate-400 normal-case">
                            · {activeRun.lean_tokens} tokens · −{activeRun.tokens_saved}
                          </span>
                        </div>
                        <pre className="text-[11px] leading-relaxed bg-emerald-50 border border-emerald-200 rounded-lg p-3 whitespace-pre-wrap max-h-96 overflow-auto text-slate-800">
                          {activeRun.summary.lean_prompt}
                        </pre>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              )}

              {activeRun.status !== "succeeded" && activeRun.status !== "running" && (
                <Card className="border-dashed border-slate-200 bg-white/60">
                  <CardContent className="py-10 text-center space-y-2">
                    <Beaker className="w-7 h-7 mx-auto text-slate-400" />
                    <div className="text-sm text-slate-700">Run not executed yet.</div>
                    <Button size="sm" onClick={runActive} disabled={running} className="bg-gradient-to-r from-rose-600 to-violet-600 text-white gap-1">
                      <Play className="w-3.5 h-3.5" /> Run ablation
                    </Button>
                  </CardContent>
                </Card>
              )}
            </>
          )}
        </div>
      </div>

      {/* ── Editor modal ───────────────────────────────────────────────── */}
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
                <Plus className="w-4 h-4 text-rose-600" />
                New ablation
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4 py-4">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label className="text-xs">Name</Label>
                  <Input value={draftName} onChange={e => setDraftName(e.target.value)} placeholder="e.g. Support prompt bloat audit" />
                </div>
                <div>
                  <Label className="text-xs">Description (optional)</Label>
                  <Input value={draftDesc} onChange={e => setDraftDesc(e.target.value)} placeholder="What is this prompt for?" />
                </div>
              </div>

              <div>
                <Label className="text-xs">System prompt to ablate</Label>
                <Textarea
                  value={draftSystem}
                  onChange={e => setDraftSystem(e.target.value)}
                  placeholder="Paste the system prompt you want to slim down…"
                  className="font-mono text-xs"
                  style={{ minHeight: 160 }}
                />
                {parsePreview && (
                  <div className="mt-2 flex items-center gap-2 text-[11px] text-slate-600">
                    <Layers className="w-3 h-3" />
                    <span>
                      <b>{parsePreview.sections?.length || 0}</b> sections parsed
                      <span className="text-slate-400"> · </span>
                      <b>{parsePreview.total_tokens || 0}</b> tokens total
                    </span>
                  </div>
                )}
              </div>

              <div>
                <Label className="text-xs">User prompt (the test case)</Label>
                <Textarea
                  value={draftUser}
                  onChange={e => setDraftUser(e.target.value)}
                  placeholder="A representative user message — Surgeon scores responses against this query."
                  className="font-mono text-xs"
                  style={{ minHeight: 90 }}
                />
              </div>

              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <div>
                  <Label className="text-xs">Provider</Label>
                  <Select value={draftProvider} onValueChange={v => { setDraftProvider(v); setDraftModel((PROVIDER_MODELS[v]||[])[0] || ""); }}>
                    <SelectTrigger className="h-9 text-xs"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {Object.keys(PROVIDER_MODELS).map(p => (
                        <SelectItem key={p} value={p}>{p}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label className="text-xs">Model</Label>
                  <Select value={draftModel} onValueChange={setDraftModel}>
                    <SelectTrigger className="h-9 text-xs"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {(PROVIDER_MODELS[draftProvider] || []).map(m => (
                        <SelectItem key={m} value={m}>{m}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label className="text-xs">Temperature</Label>
                  <Input type="number" min="0" max="2" step="0.05" value={draftTemp} onChange={e => setDraftTemp(parseFloat(e.target.value) || 0)} className="h-9 text-xs" />
                </div>
                <div>
                  <Label className="text-xs">Replays / section</Label>
                  <Input type="number" min="1" max="8" value={draftReplays} onChange={e => setDraftReplays(parseInt(e.target.value) || 1)} className="h-9 text-xs" />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3 items-end">
                <div>
                  <Label className="text-xs">Monthly calls (for $ projection)</Label>
                  <Input type="number" min="100" value={draftMonthlyCalls} onChange={e => setDraftMonthlyCalls(parseInt(e.target.value) || 0)} className="h-9 text-xs" />
                </div>
                <div className="flex items-center justify-between gap-2 px-3 py-2 rounded-lg bg-amber-50 ring-1 ring-amber-200">
                  <div>
                    <div className="text-xs font-semibold text-amber-800">Dryrun</div>
                    <div className="text-[10px] text-amber-700">no API keys needed — synthetic responses</div>
                  </div>
                  <Switch checked={draftDry} onCheckedChange={setDraftDry} />
                </div>
              </div>
            </CardContent>
            <div className="border-t px-5 py-3 flex justify-end gap-2 bg-slate-50/50">
              <Button variant="outline" onClick={() => setEditorOpen(false)}>Cancel</Button>
              <Button
                onClick={createRun}
                disabled={creating}
                className="bg-gradient-to-r from-rose-600 to-violet-600 text-white gap-1"
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

export default SurgeonStudio;
