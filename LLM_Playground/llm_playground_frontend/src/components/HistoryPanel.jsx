import React, { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  History as HistoryIcon,
  Search,
  Star,
  StarOff,
  Trash2,
  RefreshCcw,
  Tag as TagIcon,
  GitCompareArrows,
  ListOrdered,
  Award,
  Timer,
  DollarSign,
  Hash,
  Bot,
  CornerUpLeft,
  TrendingUp,
  TrendingDown,
  Minus,
  X,
  Sparkles,
  ChevronRight,
} from "lucide-react";
import { toast } from "sonner";
import ApiService from "../services/api";

const PROVIDER_DOT = {
  OpenAI:    "bg-emerald-500",
  Anthropic: "bg-amber-500",
  Google:    "bg-sky-500",
  August:    "bg-fuchsia-500",
};

const PROVIDER_TEXT = {
  OpenAI:    "text-emerald-700",
  Anthropic: "text-amber-700",
  Google:    "text-sky-700",
  August:    "text-fuchsia-700",
};

const fmtCost = (c) =>
  c == null ? "—" : c < 0.0001 ? `$${(c * 1000).toFixed(3)}m` : `$${Number(c).toFixed(4)}`;

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

const fmtAbs = (epoch) => (epoch ? new Date(Number(epoch) * 1000).toLocaleString() : "—");

// Same conic-gradient ring as Arena, sized for compact rows.
const MiniRing = ({ value = 0, size = 38 }) => {
  const v = Math.max(0, Math.min(100, Math.round(value || 0)));
  const hue = Math.round(v * 1.2);
  const ringColor = `hsl(${hue} 80% 50%)`;
  return (
    <div
      className="relative inline-flex items-center justify-center shrink-0"
      style={{
        width: size, height: size, borderRadius: "9999px",
        background: `conic-gradient(${ringColor} ${v * 3.6}deg, #e5e7eb ${v * 3.6}deg)`,
      }}
    >
      <div
        className="bg-white flex items-center justify-center"
        style={{ width: size - 8, height: size - 8, borderRadius: "9999px" }}
      >
        <span className="text-[10px] font-bold tabular-nums" style={{ color: ringColor }}>
          {v}
        </span>
      </div>
    </div>
  );
};

const Delta = ({ value, unit = "", invert = false }) => {
  // `invert=true` means lower-is-better (e.g. latency, cost) — we flip the
  // sign of the colouring so a green up-arrow always means "B improved over A".
  if (value == null) return <span className="text-[11px] text-gray-400">—</span>;
  const pos = invert ? value < 0 : value > 0;
  const Icon = value === 0 ? Minus : pos ? TrendingUp : TrendingDown;
  const cls =
    value === 0
      ? "text-gray-500"
      : pos
        ? "text-emerald-600"
        : "text-rose-600";
  const formatted =
    Math.abs(value) >= 100
      ? value.toFixed(0)
      : Math.abs(value) >= 1
        ? value.toFixed(2)
        : value.toFixed(4);
  return (
    <span className={`inline-flex items-center gap-0.5 text-[11px] font-mono ${cls}`}>
      <Icon className="w-3 h-3" />
      {formatted}
      {unit}
    </span>
  );
};

const StatTile = ({ label, value, accent = "from-blue-50 to-indigo-50 border-blue-100 text-blue-900", hint }) => (
  <div className={`p-3 rounded-lg bg-gradient-to-br ${accent} border`}>
    <div className="text-[11px] uppercase tracking-wide font-semibold opacity-75">{label}</div>
    <div className="text-xl font-bold">{value}</div>
    {hint && <div className="text-[10px] opacity-70 mt-0.5">{hint}</div>}
  </div>
);

// Re-rendering the Arena cards inside the detail pane keeps the visual
// language consistent: same provider chips, same ring, same metrics.
const ResultMiniCard = ({ r, verdict, isJudgeWinner, fastest, cheapest, verbose }) => {
  const dot = PROVIDER_DOT[r.provider] || "bg-gray-400";
  const text = PROVIDER_TEXT[r.provider] || "text-gray-700";
  const isError = r.status !== "success";
  return (
    <div
      className={`rounded-lg border bg-white shadow-sm overflow-hidden flex flex-col
        ${isError ? "border-red-200" : isJudgeWinner ? "ring-2 ring-amber-400 shadow-amber-200/40" : "ring-1 ring-gray-200"}`}
    >
      <div className={`flex items-center justify-between px-2 py-1.5 border-b ${isError ? "bg-red-50" : "bg-gray-50/70"}`}>
        <div className="flex items-center gap-2 min-w-0">
          <span className={`w-2 h-2 rounded-full ${isError ? "bg-red-500" : dot}`} />
          <span className={`text-[11px] font-semibold ${isError ? "text-red-700" : text}`}>{r.provider}</span>
          <span className="text-[11px] font-mono text-gray-700 truncate" title={r.model}>{r.model}</span>
        </div>
        <div className="flex items-center gap-1 flex-wrap">
          {isJudgeWinner && (
            <Badge className="bg-gradient-to-r from-amber-500 to-orange-500 text-white text-[9px] gap-0.5 px-1.5 py-0">
              <Award className="w-2.5 h-2.5" /> judge
            </Badge>
          )}
          {fastest && !isError && <Badge className="bg-orange-500 text-white text-[9px] px-1.5 py-0">fast</Badge>}
          {cheapest && !isError && <Badge className="bg-emerald-500 text-white text-[9px] px-1.5 py-0">cheap</Badge>}
          {verbose && !isError && <Badge className="bg-purple-500 text-white text-[9px] px-1.5 py-0">verbose</Badge>}
        </div>
      </div>
      {verdict && (
        <div className="px-2 py-1.5 border-b bg-gradient-to-r from-amber-50/60 via-white to-orange-50/40 flex items-center gap-2">
          <MiniRing value={verdict.composite} size={36} />
          <div className="flex-1 min-w-0">
            {verdict.rationale && (
              <div className="text-[10px] italic text-gray-600 line-clamp-2" title={verdict.rationale}>
                "{verdict.rationale}"
              </div>
            )}
          </div>
        </div>
      )}
      <div className="p-2 text-xs text-gray-800 flex-1">
        {isError ? (
          <div className="text-[11px] text-red-600 break-words">{r.error || "Request failed"}</div>
        ) : (
          <div className="whitespace-pre-wrap max-h-32 overflow-auto pr-1 text-[12px]">
            {r.response || <span className="text-gray-400 italic">empty</span>}
          </div>
        )}
      </div>
      <div className="px-2 py-1 border-t bg-gray-50/60 grid grid-cols-3 gap-1 text-[10px] text-gray-600">
        <span className="flex items-center gap-1"><Timer className="w-3 h-3" />{r.latency ?? "—"}s</span>
        <span className="flex items-center gap-1"><Hash className="w-3 h-3" />{r.total_tokens ?? 0}</span>
        <span className="flex items-center gap-1"><DollarSign className="w-3 h-3" />{fmtCost(r.cost_usd)}</span>
      </div>
    </div>
  );
};

const HistoryPanel = ({ onRerun }) => {
  const [filters, setFilters] = useState({
    q: "",
    provider: "",
    judged: false,
    starred: false,
  });
  const [runs, setRuns] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [stats, setStats] = useState(null);

  // Selected run drives the right pane; selectedB lets the user pin a second
  // run for diffing without losing the primary detail view.
  const [selectedId, setSelectedId] = useState(null);
  const [selectedRun, setSelectedRun] = useState(null);
  const [compareWithId, setCompareWithId] = useState(null);
  const [diff, setDiff] = useState(null);
  const [tagDraft, setTagDraft] = useState("");
  const [noteDraft, setNoteDraft] = useState("");

  // ─── Fetchers ──────────────────────────────────────────────────────────
  const refresh = async () => {
    setLoading(true);
    try {
      const [list, s] = await Promise.all([
        ApiService.listHistory({
          q: filters.q,
          provider: filters.provider,
          judged: filters.judged,
          starred: filters.starred,
          limit: 200,
        }),
        ApiService.historyStats(),
      ]);
      setRuns(list.runs || []);
      setTotal(list.total || 0);
      setStats(s.stats || null);
    } catch (e) {
      toast.error(`History: ${e.message}`);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Debounced refetch on filter change so typing doesn't hammer the backend.
  useEffect(() => {
    const t = setTimeout(refresh, 250);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filters.q, filters.provider, filters.judged, filters.starred]);

  // Re-fetch a fresh detail whenever selection changes.
  useEffect(() => {
    let cancelled = false;
    if (!selectedId) {
      setSelectedRun(null);
      return undefined;
    }
    (async () => {
      try {
        const res = await ApiService.getRun(selectedId);
        if (cancelled) return;
        setSelectedRun(res.run || null);
        setTagDraft(res.run?.tag || "");
        setNoteDraft(res.run?.note || "");
      } catch (e) {
        if (!cancelled) toast.error(`Run: ${e.message}`);
      }
    })();
    return () => { cancelled = true; };
  }, [selectedId]);

  useEffect(() => {
    if (!selectedId || !compareWithId || selectedId === compareWithId) {
      setDiff(null);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const res = await ApiService.diffRuns(selectedId, compareWithId);
        if (!cancelled) setDiff(res.diff || null);
      } catch (e) {
        if (!cancelled) toast.error(`Diff: ${e.message}`);
      }
    })();
    return () => { cancelled = true; };
  }, [selectedId, compareWithId]);

  // ─── Mutations ─────────────────────────────────────────────────────────
  const toggleStar = async (run) => {
    try {
      await ApiService.setRunMeta(run.id, { starred: !run.starred });
      setRuns(prev => prev.map(r => r.id === run.id ? { ...r, starred: !r.starred } : r));
      if (selectedRun?.id === run.id) setSelectedRun(s => s ? { ...s, starred: !s.starred } : s);
    } catch (e) {
      toast.error(`Star: ${e.message}`);
    }
  };

  const deleteRun = async (run) => {
    if (!window.confirm(`Delete this run? "${(run.prompt_preview || "").slice(0, 80)}"`)) return;
    try {
      await ApiService.deleteRun(run.id);
      setRuns(prev => prev.filter(r => r.id !== run.id));
      if (selectedId === run.id) setSelectedId(null);
      if (compareWithId === run.id) setCompareWithId(null);
      toast.success("Run deleted");
    } catch (e) {
      toast.error(`Delete: ${e.message}`);
    }
  };

  const saveMeta = async () => {
    if (!selectedRun) return;
    try {
      const res = await ApiService.setRunMeta(selectedRun.id, { tag: tagDraft, note: noteDraft });
      setSelectedRun(res.run);
      setRuns(prev => prev.map(r => r.id === res.run.id ? { ...r, tag: res.run.tag, note: res.run.note } : r));
      toast.success("Saved");
    } catch (e) {
      toast.error(`Save: ${e.message}`);
    }
  };

  // Stuff a saved run back into the Arena composer + kick a fresh run.
  const handleRerun = (run) => {
    if (!onRerun) return;
    const candidates = (run.payload?.results || run.results || []).map(r => ({
      provider: r.provider, model: r.model,
    }));
    onRerun({
      prompt: run.payload?.prompt || run.prompt || "",
      system_prompt: run.payload?.system_prompt || run.system_prompt || "",
      candidates,
    });
  };

  // ─── Filter pill helpers ───────────────────────────────────────────────
  const toggleProvider = (p) => {
    setFilters(f => ({ ...f, provider: f.provider === p ? "" : p }));
  };

  const filtersActive =
    !!filters.q || !!filters.provider || filters.judged || filters.starred;

  const resetFilters = () =>
    setFilters({ q: "", provider: "", judged: false, starred: false });

  // ─── Render ────────────────────────────────────────────────────────────
  return (
    <Card className="shadow-lg border-0 bg-white/60 backdrop-blur-sm">
      <CardHeader className="pb-4">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <CardTitle className="flex items-center gap-2 text-lg">
            <HistoryIcon className="w-5 h-5 text-indigo-600" />
            Run History
            <span className="text-xs font-normal text-gray-500">
              — every Arena & Judge run, queryable & comparable
            </span>
          </CardTitle>
          <div className="flex items-center gap-2">
            {compareWithId && (
              <Badge className="bg-violet-100 text-violet-700 border border-violet-200 gap-1">
                <GitCompareArrows className="w-3 h-3" /> compare on
                <button
                  onClick={() => setCompareWithId(null)}
                  className="ml-1 hover:text-violet-900"
                  title="Clear compare selection"
                >
                  <X className="w-3 h-3" />
                </button>
              </Badge>
            )}
            <Button
              onClick={refresh}
              size="sm"
              variant="outline"
              className="gap-1"
              disabled={loading}
              title="Refresh from server"
            >
              <RefreshCcw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
              Refresh
            </Button>
          </div>
        </div>
      </CardHeader>

      <CardContent className="space-y-4">
        {/* Stats banner */}
        {stats && stats.total_runs > 0 && (
          <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
            <StatTile
              label="Runs"
              value={stats.total_runs}
              accent="from-indigo-50 to-blue-50 border-indigo-100 text-indigo-900"
              hint={stats.first_at ? `since ${fmtRel(stats.first_at)}` : undefined}
            />
            <StatTile
              label="Successes"
              value={`${stats.total_success}/${stats.total_candidates}`}
              accent="from-emerald-50 to-green-50 border-emerald-100 text-emerald-900"
              hint="model calls"
            />
            <StatTile
              label="Total spend"
              value={fmtCost(stats.total_cost)}
              accent="from-purple-50 to-fuchsia-50 border-purple-100 text-purple-900"
            />
            <StatTile
              label="Judged"
              value={stats.judged_runs}
              accent="from-amber-50 to-orange-50 border-amber-100 text-amber-900"
              hint={stats.judged_runs ? `avg top ${stats.avg_top_score.toFixed(1)}` : "none yet"}
            />
            <StatTile
              label="Avg wall"
              value={`${stats.avg_wall.toFixed(2)}s`}
              accent="from-rose-50 to-pink-50 border-rose-100 text-rose-900"
              hint="per run"
            />
          </div>
        )}

        {/* Top contestants ribbon (only when we have judged runs) */}
        {stats?.winners?.length > 0 && (
          <div className="rounded-lg border border-amber-200/70 bg-gradient-to-r from-amber-50/80 to-orange-50/60 p-3">
            <div className="flex items-center gap-2 mb-2 text-amber-900 text-xs font-semibold">
              <ListOrdered className="w-3.5 h-3.5" /> Top judge winners
            </div>
            <div className="flex flex-wrap gap-1.5">
              {stats.winners.map((w, i) => {
                const [provider, ...rest] = (w.model || "").split(":");
                const model = rest.join(":");
                const dot = PROVIDER_DOT[provider] || "bg-gray-400";
                return (
                  <span
                    key={w.model}
                    className="inline-flex items-center gap-1.5 px-2 py-1 rounded-full bg-white border border-amber-200 text-[11px]"
                  >
                    {i === 0 && <Award className="w-3 h-3 text-amber-500" />}
                    <span className={`w-1.5 h-1.5 rounded-full ${dot}`} />
                    <span className="font-mono">{model}</span>
                    <span className="text-amber-700 font-semibold">×{w.wins}</span>
                  </span>
                );
              })}
            </div>
          </div>
        )}

        {/* Filters */}
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center">
          <div className="flex-1 relative">
            <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
            <Input
              value={filters.q}
              onChange={e => setFilters(f => ({ ...f, q: e.target.value }))}
              placeholder="Search prompt, system, model fingerprint…"
              className="pl-9 bg-white"
            />
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            {["OpenAI", "Anthropic", "Google"].map(p => (
              <button
                key={p}
                onClick={() => toggleProvider(p)}
                className={`px-2.5 py-1 rounded-full text-[11px] border transition ${
                  filters.provider === p
                    ? "bg-indigo-50 border-indigo-300 text-indigo-800 ring-2 ring-indigo-200"
                    : "bg-white border-gray-200 text-gray-600 hover:bg-gray-50"
                }`}
              >
                <span className={`inline-block w-1.5 h-1.5 rounded-full mr-1 ${PROVIDER_DOT[p]}`} />
                {p}
              </button>
            ))}
            <label className="flex items-center gap-1.5 text-[11px] text-gray-700">
              <Switch
                checked={filters.judged}
                onCheckedChange={(v) => setFilters(f => ({ ...f, judged: v }))}
              />
              judged only
            </label>
            <label className="flex items-center gap-1.5 text-[11px] text-gray-700">
              <Switch
                checked={filters.starred}
                onCheckedChange={(v) => setFilters(f => ({ ...f, starred: v }))}
              />
              starred
            </label>
            {filtersActive && (
              <Button onClick={resetFilters} size="sm" variant="ghost" className="h-7 px-2 text-[11px] text-gray-500">
                <X className="w-3 h-3 mr-1" /> reset
              </Button>
            )}
          </div>
        </div>

        {/* Two-pane: list ⟷ detail */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
          {/* Run list */}
          <div className="lg:col-span-5">
            <div className="text-[11px] uppercase tracking-wide text-gray-500 font-semibold mb-1.5 flex items-center justify-between">
              <span>{total} run{total === 1 ? "" : "s"}</span>
              <span className="text-gray-400 normal-case tracking-normal">click to inspect · ⌘ + click to compare</span>
            </div>
            <ScrollArea className="h-[640px] border rounded-lg bg-white">
              {runs.length === 0 ? (
                <div className="text-center text-gray-400 py-16 px-4">
                  <Sparkles className="w-8 h-8 mx-auto mb-2 text-gray-300" />
                  {filtersActive ? (
                    <>No runs match those filters.</>
                  ) : (
                    <>
                      No runs yet — fan a prompt out in <span className="font-semibold">Arena</span> and it'll land here.
                    </>
                  )}
                </div>
              ) : (
                <div className="divide-y">
                  {runs.map(r => {
                    const isSelected = r.id === selectedId;
                    const isCompare  = r.id === compareWithId;
                    const judgeWinnerProvider = (r.judge_winner || "").split(":")[0];
                    const dot = PROVIDER_DOT[judgeWinnerProvider];
                    return (
                      <div
                        key={r.id}
                        onClick={(e) => {
                          if (e.metaKey || e.ctrlKey) {
                            // Pin this run as the diff partner.
                            setCompareWithId(prev => (prev === r.id ? null : r.id));
                          } else {
                            setSelectedId(r.id);
                          }
                        }}
                        className={`group cursor-pointer px-3 py-2.5 transition ${
                          isSelected ? "bg-indigo-50/80" :
                          isCompare  ? "bg-violet-50/60"  :
                          "hover:bg-gray-50"
                        }`}
                      >
                        <div className="flex items-center gap-2.5">
                          {r.judged ? (
                            <MiniRing value={r.judge_top_score || 0} size={36} />
                          ) : (
                            <div className="w-9 h-9 rounded-full bg-gray-100 border border-gray-200 flex items-center justify-center shrink-0">
                              <Bot className="w-4 h-4 text-gray-400" />
                            </div>
                          )}
                          <div className="flex-1 min-w-0">
                            <div className="flex items-start justify-between gap-2">
                              <div className="text-[13px] text-gray-800 line-clamp-2 leading-snug">
                                {r.prompt_preview || <span className="italic text-gray-400">(empty prompt)</span>}
                              </div>
                              <div className="flex items-center gap-1 shrink-0">
                                <button
                                  onClick={(e) => { e.stopPropagation(); toggleStar(r); }}
                                  className="text-gray-300 hover:text-amber-500 transition"
                                  title={r.starred ? "Unstar" : "Star"}
                                >
                                  {r.starred ? <Star className="w-4 h-4 fill-amber-400 text-amber-500" /> : <StarOff className="w-4 h-4" />}
                                </button>
                              </div>
                            </div>
                            <div className="mt-1 flex items-center gap-2 flex-wrap text-[10px]">
                              <span className="text-gray-500">{fmtRel(r.created_at)}</span>
                              <span className="text-gray-300">·</span>
                              <span className="text-gray-600">{r.n_candidates} model{r.n_candidates === 1 ? "" : "s"}</span>
                              <span className={`text-gray-300`}>·</span>
                              <span className={`${r.n_success === r.n_candidates ? "text-emerald-700" : "text-amber-700"}`}>
                                {r.n_success}/{r.n_candidates} ok
                              </span>
                              <span className="text-gray-300">·</span>
                              <span className="text-purple-700 font-mono">{fmtCost(r.total_cost_usd)}</span>
                              {r.judged && r.judge_winner && (
                                <>
                                  <span className="text-gray-300">·</span>
                                  <span className={`inline-flex items-center gap-1 ${PROVIDER_TEXT[judgeWinnerProvider] || "text-gray-700"}`}>
                                    <span className={`w-1.5 h-1.5 rounded-full ${dot || "bg-gray-400"}`} />
                                    <Award className="w-3 h-3" />
                                    {(r.judge_winner.split(":")[1] || "").slice(0, 24)}
                                  </span>
                                </>
                              )}
                              {r.tag && (
                                <Badge variant="outline" className="text-[9px] border-indigo-200 text-indigo-700 bg-indigo-50 gap-0.5 py-0">
                                  <TagIcon className="w-2.5 h-2.5" />
                                  {r.tag}
                                </Badge>
                              )}
                            </div>
                            {/* Provider dot strip */}
                            <div className="flex items-center gap-1 mt-1.5">
                              {(r.models || []).slice(0, 8).map((m, i) => {
                                const [p] = m.split(":");
                                return (
                                  <span
                                    key={i}
                                    title={m}
                                    className={`w-1.5 h-1.5 rounded-full ${PROVIDER_DOT[p] || "bg-gray-300"}`}
                                  />
                                );
                              })}
                            </div>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </ScrollArea>
          </div>

          {/* Detail */}
          <div className="lg:col-span-7">
            {!selectedRun ? (
              <div className="h-[640px] flex flex-col items-center justify-center text-center text-gray-400 border border-dashed rounded-lg bg-white">
                <HistoryIcon className="w-10 h-10 mb-3 text-gray-300" />
                <p className="font-medium text-gray-500">Pick a run to inspect.</p>
                <p className="text-xs mt-1 max-w-xs">
                  Hold <kbd className="px-1 py-0.5 rounded bg-gray-100 border text-[10px]">⌘/Ctrl</kbd> +
                  click a second row to compare two runs side-by-side.
                </p>
              </div>
            ) : (
              <RunDetail
                run={selectedRun}
                diff={diff}
                compareWithId={compareWithId}
                onPickCompareTarget={() => {
                  // Convenience: if the user pressed "compare", auto-pin the
                  // currently-selected run as A and clear B so they can pick.
                  setCompareWithId(null);
                  toast.info("Pick a second run with ⌘ / Ctrl + click");
                }}
                onClearCompare={() => setCompareWithId(null)}
                tagDraft={tagDraft}
                noteDraft={noteDraft}
                setTagDraft={setTagDraft}
                setNoteDraft={setNoteDraft}
                onSaveMeta={saveMeta}
                onDelete={() => deleteRun(selectedRun)}
                onRerun={() => handleRerun(selectedRun)}
              />
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
};

// ─── Detail pane ─────────────────────────────────────────────────────────────
const RunDetail = ({
  run, diff, compareWithId, onPickCompareTarget, onClearCompare,
  tagDraft, noteDraft, setTagDraft, setNoteDraft, onSaveMeta, onDelete, onRerun,
}) => {
  const payload = run.payload || {};
  const results = payload.results || [];
  const winners = payload.winners || {};
  const judge   = payload.judge || null;

  const verdictByCandidate = useMemo(() => {
    const m = {};
    (judge?.verdicts || []).forEach(v => { m[v.candidate] = v; });
    return m;
  }, [judge]);

  return (
    <div className="border rounded-lg bg-white shadow-sm flex flex-col" style={{ minHeight: 640 }}>
      {/* Title bar */}
      <div className="px-4 py-3 border-b bg-gradient-to-r from-indigo-50/50 via-white to-purple-50/40 flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-3 min-w-0">
          {run.judged ? (
            <MiniRing value={run.judge_top_score || 0} size={48} />
          ) : (
            <div className="w-12 h-12 rounded-full bg-gray-100 border border-gray-200 flex items-center justify-center shrink-0">
              <Bot className="w-5 h-5 text-gray-400" />
            </div>
          )}
          <div className="min-w-0">
            <div className="text-sm font-semibold text-gray-800 line-clamp-1">
              {run.prompt || <span className="italic text-gray-400">(empty prompt)</span>}
            </div>
            <div className="text-[11px] text-gray-500 mt-0.5">
              {fmtAbs(run.created_at)} · {run.n_candidates} model{run.n_candidates === 1 ? "" : "s"} · {run.wall_latency}s
              · {fmtCost(run.total_cost_usd)}
              {run.judged && run.judge_winner && (
                <> · <span className="text-amber-700 font-mono">{run.judge_winner}</span> won @ {Math.round(run.judge_top_score || 0)}</>
              )}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-1.5 flex-wrap">
          <Button onClick={onRerun} size="sm" variant="outline" className="gap-1 text-indigo-700 hover:bg-indigo-50 border-indigo-200">
            <CornerUpLeft className="w-3.5 h-3.5" /> Re-run
          </Button>
          {compareWithId ? (
            <Button onClick={onClearCompare} size="sm" variant="outline" className="gap-1 text-violet-700 hover:bg-violet-50 border-violet-200">
              <X className="w-3.5 h-3.5" /> Clear compare
            </Button>
          ) : (
            <Button onClick={onPickCompareTarget} size="sm" variant="outline" className="gap-1 text-violet-700 hover:bg-violet-50 border-violet-200">
              <GitCompareArrows className="w-3.5 h-3.5" /> Compare with…
            </Button>
          )}
          <Button onClick={onDelete} size="sm" variant="outline" className="gap-1 text-rose-700 hover:bg-rose-50 border-rose-200">
            <Trash2 className="w-3.5 h-3.5" /> Delete
          </Button>
        </div>
      </div>

      {/* Tag + note row */}
      <div className="px-4 py-2.5 border-b bg-white grid grid-cols-1 sm:grid-cols-3 gap-2 items-end">
        <div>
          <Label className="text-[10px] uppercase tracking-wide text-gray-500">Tag</Label>
          <Input
            value={tagDraft}
            onChange={e => setTagDraft(e.target.value)}
            placeholder="e.g. baseline, finance-eval"
            className="h-8 text-xs mt-1 bg-white"
          />
        </div>
        <div className="sm:col-span-2">
          <Label className="text-[10px] uppercase tracking-wide text-gray-500">Note</Label>
          <Input
            value={noteDraft}
            onChange={e => setNoteDraft(e.target.value)}
            placeholder="Why this run mattered…"
            className="h-8 text-xs mt-1 bg-white"
          />
        </div>
        <div className="sm:col-span-3 flex justify-end">
          <Button onClick={onSaveMeta} size="sm" variant="ghost" className="h-7 text-[11px] text-indigo-700 hover:bg-indigo-50 gap-1">
            <TagIcon className="w-3 h-3" /> Save tag & note
          </Button>
        </div>
      </div>

      {/* When a diff is loaded, the comparison rules the view; otherwise the detail does. */}
      {diff ? (
        <DiffView diff={diff} />
      ) : (
        <div className="p-4 space-y-3 overflow-auto" style={{ maxHeight: 640 }}>
          {payload.system_prompt && (
            <div className="rounded-md bg-gray-50 border border-gray-200 p-2">
              <Label className="text-[10px] uppercase tracking-wide text-gray-500">System prompt</Label>
              <div className="text-xs text-gray-700 mt-0.5 whitespace-pre-wrap line-clamp-4">
                {payload.system_prompt}
              </div>
            </div>
          )}

          {/* Judge leaderboard */}
          {judge?.leaderboard?.length > 0 && (
            <div className="rounded-lg border border-amber-200 bg-gradient-to-br from-amber-50/80 to-orange-50/60 p-3 space-y-2">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-1.5 text-[12px] font-semibold text-amber-900">
                  <ListOrdered className="w-3.5 h-3.5 text-amber-700" />
                  Leaderboard
                </div>
                <div className="text-[10px] text-amber-700/80">
                  {judge.judge?.provider} · {judge.judge?.model} · {judge.judge?.latency}s
                </div>
              </div>
              {judge.leaderboard.map((row, rank) => (
                <div key={row.candidate} className="grid grid-cols-12 items-center gap-2 bg-white/80 rounded-md px-2 py-1.5 ring-1 ring-amber-100">
                  <div className="col-span-1 text-[10px] font-bold text-amber-800">
                    {rank === 0 ? <Award className="w-3.5 h-3.5 text-amber-500" /> : `#${rank+1}`}
                  </div>
                  <div className="col-span-4 flex items-center gap-1.5 min-w-0">
                    <span className={`w-1.5 h-1.5 rounded-full ${PROVIDER_DOT[row.provider] || "bg-gray-400"}`} />
                    <span className="text-[10px] font-mono text-gray-700 truncate" title={row.model}>{row.model}</span>
                  </div>
                  <div className="col-span-5 h-1.5 bg-gray-200 rounded-full overflow-hidden">
                    <div
                      className="h-full rounded-full"
                      style={{
                        width: `${row.composite}%`,
                        background: `hsl(${Math.round(row.composite * 1.2)} 80% 50%)`,
                      }}
                    />
                  </div>
                  <div className="col-span-2 text-right text-[11px] font-mono">{row.composite}</div>
                </div>
              ))}
            </div>
          )}

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {results.map((r, i) => (
              <ResultMiniCard
                key={i}
                r={r}
                verdict={verdictByCandidate[i]}
                isJudgeWinner={judge?.winner === i}
                fastest={winners.fastest === r.model}
                cheapest={winners.cheapest === r.model}
                verbose={winners.most_verbose === r.model}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

// ─── Diff view ───────────────────────────────────────────────────────────────
const DiffView = ({ diff }) => {
  const a = diff.a, b = diff.b, d = diff.deltas;
  return (
    <div className="p-4 space-y-3 overflow-auto" style={{ maxHeight: 640 }}>
      {/* Headline diff banner */}
      <div className="rounded-lg border border-violet-200 bg-gradient-to-r from-violet-50 via-white to-indigo-50 p-3">
        <div className="flex items-center gap-2 text-violet-900 text-xs font-semibold mb-2">
          <GitCompareArrows className="w-4 h-4" /> Comparing two runs
        </div>
        <div className="grid grid-cols-2 gap-3 text-[11px] text-gray-700">
          <div>
            <div className="font-mono text-[10px] text-violet-700">A · {fmtRel(a.created_at)}</div>
            <div className="line-clamp-2 mt-0.5">{a.prompt_preview || a.prompt}</div>
          </div>
          <div>
            <div className="font-mono text-[10px] text-violet-700">B · {fmtRel(b.created_at)}</div>
            <div className="line-clamp-2 mt-0.5">{b.prompt_preview || b.prompt}</div>
          </div>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mt-3">
          <DiffStat label="Wall time" a={a.wall_latency} b={b.wall_latency} delta={d.wall_latency} unit="s" invert />
          <DiffStat label="Total $" a={a.total_cost_usd} b={b.total_cost_usd} delta={d.total_cost} costy invert />
          <DiffStat label="Successes" a={a.n_success} b={b.n_success} delta={d.n_success} integer />
          <DiffStat label="Top score" a={a.judge_top_score} b={b.judge_top_score} delta={d.judge_top_score} integer />
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-3 text-[11px] text-violet-800">
          <span className="font-mono">{diff.shared_models.length} shared</span>
          {diff.a_only.length > 0 && (
            <span className="font-mono text-violet-600">A-only: {diff.a_only.join(", ")}</span>
          )}
          {diff.b_only.length > 0 && (
            <span className="font-mono text-violet-600">B-only: {diff.b_only.join(", ")}</span>
          )}
        </div>
      </div>

      {/* Per-shared-model diff rows */}
      <div className="space-y-1.5">
        <div className="text-[10px] uppercase tracking-wide text-gray-500 font-semibold mb-1">Shared models</div>
        {diff.per_model.length === 0 ? (
          <div className="text-[12px] text-gray-500 italic">No models in common between these runs.</div>
        ) : diff.per_model.map(row => {
          const [provider] = row.model.split(":");
          return (
            <div key={row.model} className="rounded-lg border border-gray-200 bg-white px-3 py-2">
              <div className="flex items-center gap-2 mb-1.5">
                <span className={`w-1.5 h-1.5 rounded-full ${PROVIDER_DOT[provider] || "bg-gray-400"}`} />
                <span className="text-[12px] font-mono text-gray-800">{row.model}</span>
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-1.5 text-[11px]">
                <DiffMetric label="latency" a={row.a.latency} b={row.b.latency} delta={row.deltas.latency} unit="s" invert />
                <DiffMetric label="cost"    a={row.a.cost_usd} b={row.b.cost_usd} delta={row.deltas.cost_usd} costy invert />
                <DiffMetric label="chars"   a={row.a.response_chars} b={row.b.response_chars} delta={row.deltas.response_chars} integer />
                <DiffMetric label="score"   a={row.a.composite} b={row.b.composite} delta={row.deltas.composite} integer />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

const DiffStat = ({ label, a, b, delta, unit = "", invert = false, integer = false, costy = false }) => {
  const fmt = (v) => v == null ? "—" : costy ? fmtCost(v) : integer ? Math.round(v) : Number(v).toFixed(2);
  return (
    <div className="bg-white border border-violet-100 rounded-md p-2">
      <div className="text-[10px] uppercase tracking-wide text-violet-700 font-semibold">{label}</div>
      <div className="flex items-center justify-between mt-0.5">
        <div className="text-[11px] text-gray-600 font-mono">
          <span className="text-violet-700">A</span> {fmt(a)}{unit && !costy ? unit : ""}
          <ChevronRight className="w-3 h-3 inline mx-1 text-gray-300" />
          <span className="text-violet-700">B</span> {fmt(b)}{unit && !costy ? unit : ""}
        </div>
        <Delta value={delta} unit={costy ? "" : unit} invert={invert} />
      </div>
    </div>
  );
};

const DiffMetric = ({ label, a, b, delta, unit = "", invert = false, integer = false, costy = false }) => {
  const fmt = (v) => v == null ? "—" : costy ? fmtCost(v) : integer ? Math.round(v) : Number(v).toFixed(2);
  return (
    <div className="flex items-center justify-between gap-1 bg-gray-50/60 border border-gray-100 rounded px-1.5 py-1">
      <span className="text-[10px] uppercase tracking-wide text-gray-500">{label}</span>
      <div className="flex items-center gap-1">
        <span className="text-gray-600 font-mono text-[11px]">{fmt(a)}{!costy && unit ? unit : ""}</span>
        <ChevronRight className="w-3 h-3 text-gray-300" />
        <span className="text-gray-800 font-mono text-[11px]">{fmt(b)}{!costy && unit ? unit : ""}</span>
        <Delta value={delta} unit={costy ? "" : unit} invert={invert} />
      </div>
    </div>
  );
};

export default HistoryPanel;
