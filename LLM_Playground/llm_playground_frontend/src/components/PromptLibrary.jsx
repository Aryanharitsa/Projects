import React, { useEffect, useState, useCallback } from "react";
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
  BookOpenText,
  Plus,
  Search,
  Star,
  StarOff,
  Trash2,
  Edit3,
  Save,
  X,
  GitBranch,
  GitCompareArrows,
  Sparkles,
  ChevronRight,
  Tag as TagIcon,
  Play,
  History as HistoryIcon,
  Clock,
  TrendingUp,
  TrendingDown,
  Minus,
  Layers,
  Flame,
  Check,
} from "lucide-react";
import { toast } from "sonner";
import ApiService from "../services/api";

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

const fmtCost = (c) =>
  c == null ? "—" : c < 0.0001 ? `$${(c * 1000).toFixed(3)}m` : `$${Number(c).toFixed(4)}`;

// ─── Sub-components ────────────────────────────────────────────────────────

// Conic-gradient score ring — same visual language as Arena/History.
const ScoreRing = ({ value, size = 44, label }) => {
  const has = value != null && !Number.isNaN(Number(value));
  const v = has ? Math.max(0, Math.min(100, Math.round(Number(value)))) : 0;
  const hue = Math.round(v * 1.2);
  const ringColor = has ? `hsl(${hue} 80% 50%)` : "#cbd5e1";
  return (
    <div
      className="relative inline-flex items-center justify-center shrink-0"
      style={{
        width: size,
        height: size,
        borderRadius: "9999px",
        background: has
          ? `conic-gradient(${ringColor} ${v * 3.6}deg, #e5e7eb ${v * 3.6}deg)`
          : "conic-gradient(#cbd5e1 0deg, #e5e7eb 0deg)",
      }}
      title={has ? `${v} / 100${label ? ` · ${label}` : ""}` : "no judged runs yet"}
    >
      <div
        className="rounded-full bg-white flex items-center justify-center font-semibold"
        style={{ width: size - 8, height: size - 8, fontSize: size > 40 ? 13 : 11 }}
      >
        {has ? v : "—"}
      </div>
    </div>
  );
};

// Sparkline of judge_top_score over versions. Gaps = un-judged versions.
// SVG path that *only* connects consecutive scored points (segments with a
// hole stop and restart so a missing v3 doesn't get linearly interpolated).
const ScoreSparkline = ({ data, height = 28, width = 110 }) => {
  if (!data || data.length === 0) {
    return <div className="text-[10px] text-gray-400 italic">no runs yet</div>;
  }
  if (data.length === 1) {
    const s = data[0].s;
    return (
      <div className="flex items-center gap-1 text-[11px] text-gray-600">
        <Sparkles className="w-3 h-3 text-violet-500" />
        {s == null ? "un-judged" : `${s}`}
      </div>
    );
  }
  const n = data.length;
  const min = 0;
  const max = 100;
  const xs = (i) => (n === 1 ? width / 2 : (i / (n - 1)) * (width - 4) + 2);
  const ys = (s) => height - 2 - ((s - min) / (max - min)) * (height - 4);

  const segments = [];
  let cur = [];
  data.forEach((d, i) => {
    if (d.s != null) {
      cur.push({ x: xs(i), y: ys(d.s) });
    } else if (cur.length) {
      segments.push(cur);
      cur = [];
    }
  });
  if (cur.length) segments.push(cur);

  return (
    <svg width={width} height={height} className="block">
      <line x1={0} y1={height - 1} x2={width} y2={height - 1} stroke="#e5e7eb" strokeWidth={1} />
      {segments.map((seg, i) => (
        <polyline
          key={i}
          fill="none"
          stroke="url(#sparkGrad)"
          strokeWidth={1.6}
          strokeLinecap="round"
          strokeLinejoin="round"
          points={seg.map((p) => `${p.x},${p.y}`).join(" ")}
        />
      ))}
      {data.map((d, i) =>
        d.s == null ? null : (
          <circle
            key={i}
            cx={xs(i)}
            cy={ys(d.s)}
            r={2}
            fill={i === n - 1 ? "#7c3aed" : "#a78bfa"}
          />
        )
      )}
      <defs>
        <linearGradient id="sparkGrad" x1="0" x2="1">
          <stop offset="0" stopColor="#a78bfa" />
          <stop offset="1" stopColor="#ec4899" />
        </linearGradient>
      </defs>
    </svg>
  );
};

// Per-version score-delta chip — direction-aware colours.
const Delta = ({ value, suffix = "" }) => {
  if (value == null || Number.isNaN(Number(value))) {
    return (
      <span className="inline-flex items-center gap-0.5 text-[10px] text-gray-400">
        <Minus className="w-3 h-3" /> n/a
      </span>
    );
  }
  const v = Number(value);
  if (Math.abs(v) < 0.01) {
    return (
      <span className="inline-flex items-center gap-0.5 text-[10px] text-gray-500">
        <Minus className="w-3 h-3" /> 0{suffix}
      </span>
    );
  }
  const up = v > 0;
  return (
    <span
      className={
        "inline-flex items-center gap-0.5 text-[10px] font-medium " +
        (up ? "text-emerald-600" : "text-rose-600")
      }
    >
      {up ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
      {up ? "+" : ""}
      {v.toFixed(2)}
      {suffix}
    </span>
  );
};

// ─── Main component ───────────────────────────────────────────────────────

export default function PromptLibrary({
  onRunInArena,
  selectedPromptId,
  onSelectedPromptIdChange,
  pendingDraft,
  onConsumeDraft,
}) {
  const [prompts, setPrompts] = useState([]);
  const [stats, setStats] = useState(null);
  const [search, setSearch] = useState("");
  const [starredOnly, setStarredOnly] = useState(false);
  const [loading, setLoading] = useState(false);

  const [activeId, setActiveId] = useState(selectedPromptId || null);
  const [activePrompt, setActivePrompt] = useState(null);

  // New prompt form
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const [newSys, setNewSys] = useState("");
  const [newTpl, setNewTpl] = useState("");
  const [newTag, setNewTag] = useState("");

  // Inline editor for "save as new version"
  const [editorOpen, setEditorOpen] = useState(false);
  const [editSys, setEditSys] = useState("");
  const [editTpl, setEditTpl] = useState("");
  const [editNote, setEditNote] = useState("");

  // Diff selection state
  const [diffA, setDiffA] = useState(null);
  const [diffB, setDiffB] = useState(null);
  const [diffResult, setDiffResult] = useState(null);
  const [, setDiffing] = useState(false);

  // Name editor
  const [nameEditing, setNameEditing] = useState(false);
  const [nameDraft, setNameDraft] = useState("");

  // ─── Data fetches ───────────────────────────────────────────────────────

  const refreshList = useCallback(async () => {
    setLoading(true);
    try {
      const filters = {};
      if (search) filters.q = search;
      if (starredOnly) filters.starred = true;
      const [list, s] = await Promise.all([
        ApiService.listPrompts(filters),
        ApiService.promptStats(),
      ]);
      setPrompts(list.prompts || []);
      setStats(s.stats || null);
    } catch (err) {
      console.error(err);
      toast.error("Failed to load prompts");
    } finally {
      setLoading(false);
    }
  }, [search, starredOnly]);

  const refreshActive = useCallback(async () => {
    if (!activeId) {
      setActivePrompt(null);
      return;
    }
    try {
      const res = await ApiService.getPrompt(activeId);
      setActivePrompt(res.prompt || null);
      if (res.prompt) {
        setNameDraft(res.prompt.name || "");
        const head = (res.prompt.versions || []).find(
          (v) => v.id === res.prompt.current_version_id
        );
        if (head && !editorOpen) {
          setEditSys(head.system_prompt || "");
          setEditTpl(head.user_template || "");
        }
      }
    } catch (err) {
      console.error(err);
      toast.error("Failed to load prompt detail");
    }
  }, [activeId, editorOpen]);

  useEffect(() => {
    // Debounced refresh on filter changes (search/starredOnly).
    const t = setTimeout(refreshList, 250);
    return () => clearTimeout(t);
  }, [refreshList]);

  useEffect(() => {
    refreshActive();
  }, [refreshActive]);

  // External "create from draft" flow — Arena hands us {name, system, template}.
  useEffect(() => {
    if (!pendingDraft) return;
    setCreating(true);
    setNewName(pendingDraft.name || "");
    setNewSys(pendingDraft.system_prompt || "");
    setNewTpl(pendingDraft.user_template || "");
    setNewTag(pendingDraft.tag || "");
    onConsumeDraft?.();
  }, [pendingDraft, onConsumeDraft]);

  // ─── Actions ───────────────────────────────────────────────────────────

  const handleCreate = async () => {
    if (!newName.trim()) {
      toast.error("Name your prompt first");
      return;
    }
    try {
      const res = await ApiService.createPrompt({
        name: newName.trim(),
        system_prompt: newSys,
        user_template: newTpl,
        tag: newTag.trim() || undefined,
      });
      toast.success(`Created “${res.prompt.name}”`);
      setActiveId(res.prompt.id);
      onSelectedPromptIdChange?.(res.prompt.id);
      setCreating(false);
      setNewName("");
      setNewSys("");
      setNewTpl("");
      setNewTag("");
      refreshList();
    } catch (err) {
      toast.error(`Create failed: ${err.message}`);
    }
  };

  const handleAddVersion = async () => {
    if (!activeId) return;
    try {
      const res = await ApiService.addPromptVersion(activeId, {
        system_prompt: editSys,
        user_template: editTpl,
        note: editNote,
      });
      const v = res.version;
      const headV = (activePrompt?.versions || []).find(
        (x) => x.id === activePrompt?.current_version_id
      );
      if (headV && v.id === headV.id) {
        toast.info("No changes detected — kept existing head");
      } else {
        toast.success(`Saved v${v.version_num}`);
      }
      setEditorOpen(false);
      setEditNote("");
      refreshList();
      refreshActive();
    } catch (err) {
      toast.error(`Save failed: ${err.message}`);
    }
  };

  const handleDelete = async () => {
    if (!activeId) return;
    if (!confirm(`Delete prompt "${activePrompt?.name}"? Linked runs stay archived.`))
      return;
    try {
      await ApiService.deletePrompt(activeId);
      toast.success("Deleted");
      setActiveId(null);
      onSelectedPromptIdChange?.(null);
      refreshList();
    } catch (err) {
      toast.error(`Delete failed: ${err.message}`);
    }
  };

  const handleStar = async (next) => {
    if (!activeId) return;
    try {
      await ApiService.setPromptMeta(activeId, { starred: next });
      refreshList();
      refreshActive();
    } catch (err) {
      toast.error(`Update failed: ${err.message}`);
    }
  };

  const handleRename = async () => {
    if (!activeId) return;
    if (!nameDraft.trim()) return setNameEditing(false);
    try {
      await ApiService.setPromptMeta(activeId, { name: nameDraft.trim() });
      setNameEditing(false);
      refreshList();
      refreshActive();
    } catch (err) {
      toast.error(`Rename failed: ${err.message}`);
    }
  };

  // Click-to-diff: first click → A, second click → B, third resets to A.
  const handleVersionClick = (vid) => {
    if (!diffA) {
      setDiffA(vid);
    } else if (diffA && !diffB && vid !== diffA) {
      setDiffB(vid);
    } else {
      setDiffA(vid);
      setDiffB(null);
      setDiffResult(null);
    }
  };

  useEffect(() => {
    if (!diffA || !diffB) {
      setDiffResult(null);
      return;
    }
    setDiffing(true);
    ApiService.diffPromptVersions(diffA, diffB)
      .then((res) => setDiffResult(res.diff || null))
      .catch((err) => {
        toast.error(`Diff failed: ${err.message}`);
        setDiffResult(null);
      })
      .finally(() => setDiffing(false));
  }, [diffA, diffB]);

  const clearDiff = () => {
    setDiffA(null);
    setDiffB(null);
    setDiffResult(null);
  };

  const handleRunVersion = (v) => {
    if (!activePrompt) return;
    onRunInArena?.({
      prompt_id: activePrompt.id,
      prompt_name: activePrompt.name,
      version_id: v.id,
      version_num: v.version_num,
      system_prompt: v.system_prompt || "",
      user_template: v.user_template || "",
    });
    toast.success(`Loaded v${v.version_num} of “${activePrompt.name}” into Arena`);
  };

  // ─── Render ────────────────────────────────────────────────────────────

  const versions = activePrompt?.versions || [];
  const headId = activePrompt?.current_version_id;

  return (
    <div className="space-y-4">
      {/* Stats banner */}
      <Card className="shadow-lg border-0 bg-gradient-to-br from-violet-50 via-fuchsia-50 to-pink-50 backdrop-blur-sm">
        <CardContent className="p-4">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <div className="p-1.5 rounded-lg bg-gradient-to-br from-violet-500 to-fuchsia-500">
                <BookOpenText className="w-4 h-4 text-white" />
              </div>
              <div>
                <div className="text-base font-semibold leading-tight">Prompt Library</div>
                <div className="text-[11px] text-gray-500">
                  Versioned prompts, linked to every Arena run they produced.
                </div>
              </div>
            </div>
            <Button
              onClick={() => setCreating(true)}
              size="sm"
              className="bg-gradient-to-r from-violet-500 to-fuchsia-500 text-white hover:opacity-90 gap-1"
            >
              <Plus className="w-4 h-4" /> New prompt
            </Button>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
            <StatTile icon={<BookOpenText className="w-3.5 h-3.5" />} label="Prompts" value={stats?.n_prompts ?? "—"} tint="violet" />
            <StatTile icon={<Layers className="w-3.5 h-3.5" />} label="Versions" value={stats?.n_versions ?? "—"} tint="fuchsia" />
            <StatTile icon={<HistoryIcon className="w-3.5 h-3.5" />} label="Linked runs" value={stats?.n_linked_runs ?? "—"} tint="pink" />
            <StatTile icon={<Sparkles className="w-3.5 h-3.5" />} label="Avg score" value={stats?.avg_composite ? Number(stats.avg_composite).toFixed(1) : "—"} tint="amber" />
          </div>
          {stats?.top_iterated?.length > 0 && (
            <div className="flex items-center gap-2 mt-3 text-[11px] text-gray-600 flex-wrap">
              <Flame className="w-3 h-3 text-orange-500" />
              <span className="font-medium">Most iterated:</span>
              {stats.top_iterated.slice(0, 5).map((p) => (
                <button
                  key={p.id}
                  onClick={() => { setActiveId(p.id); onSelectedPromptIdChange?.(p.id); }}
                  className="px-1.5 py-0.5 rounded bg-white/70 hover:bg-white border border-violet-200 transition-colors"
                >
                  {p.name} · v{p.n_versions}
                </button>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Filter row */}
      <Card className="shadow-sm border-0 bg-white/60 backdrop-blur-sm">
        <CardContent className="p-3">
          <div className="flex items-center gap-3 flex-wrap">
            <div className="relative flex-1 min-w-[200px]">
              <Search className="w-3.5 h-3.5 absolute left-2.5 top-2.5 text-gray-400" />
              <Input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search prompts by name or tag…"
                className="pl-8 h-9"
              />
            </div>
            <div className="flex items-center gap-2">
              <Switch checked={starredOnly} onCheckedChange={setStarredOnly} />
              <Label className="text-xs">Starred only</Label>
            </div>
            {(search || starredOnly) && (
              <Button
                onClick={() => { setSearch(""); setStarredOnly(false); }}
                size="sm"
                variant="ghost"
                className="h-7 text-xs gap-1"
              >
                <X className="w-3 h-3" /> Reset
              </Button>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Create-prompt form */}
      {creating && (
        <Card className="shadow-md border-0 bg-white/80 backdrop-blur-sm border-l-4 border-l-violet-500">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-2">
              <Plus className="w-4 h-4 text-violet-600" /> Create prompt
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div>
              <Label className="text-xs">Name *</Label>
              <Input value={newName} onChange={(e) => setNewName(e.target.value)} className="h-9 mt-1" />
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div>
                <Label className="text-xs">System prompt</Label>
                <Textarea value={newSys} onChange={(e) => setNewSys(e.target.value)} rows={4} className="mt-1 font-mono text-xs" />
              </div>
              <div>
                <Label className="text-xs">User template</Label>
                <Textarea value={newTpl} onChange={(e) => setNewTpl(e.target.value)} rows={4} className="mt-1 font-mono text-xs" />
              </div>
            </div>
            <div className="flex items-center gap-2">
              <div className="flex-1">
                <Label className="text-xs">Tag (optional)</Label>
                <Input value={newTag} onChange={(e) => setNewTag(e.target.value)} placeholder="e.g. production" className="h-9 mt-1" />
              </div>
              <div className="flex items-end gap-2 pt-4">
                <Button onClick={handleCreate} size="sm" className="bg-violet-600 hover:bg-violet-700 text-white gap-1">
                  <Save className="w-4 h-4" /> Save
                </Button>
                <Button onClick={() => setCreating(false)} size="sm" variant="ghost">Cancel</Button>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Two-column grid */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
        {/* Prompt list */}
        <Card className="shadow-md border-0 bg-white/60 backdrop-blur-sm lg:col-span-5">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-2">
              <BookOpenText className="w-4 h-4 text-violet-600" />
              Prompts
              <Badge variant="outline" className="text-[10px]">{prompts.length}</Badge>
            </CardTitle>
          </CardHeader>
          <CardContent className="px-2">
            <ScrollArea className="h-[600px] pr-2">
              {loading && prompts.length === 0 ? (
                <div className="text-center text-xs text-gray-400 py-12">Loading…</div>
              ) : prompts.length === 0 ? (
                <div className="text-center py-12 text-xs text-gray-500">
                  No prompts yet.<br />
                  <Button onClick={() => setCreating(true)} size="sm" variant="link" className="text-violet-600 mt-2">
                    Create your first prompt →
                  </Button>
                </div>
              ) : (
                <div className="space-y-2">
                  {prompts.map((p) => (
                    <button
                      key={p.id}
                      onClick={() => { setActiveId(p.id); onSelectedPromptIdChange?.(p.id); clearDiff(); }}
                      className={
                        "w-full text-left px-3 py-2.5 rounded-lg border transition-all " +
                        (activeId === p.id
                          ? "border-violet-400 bg-gradient-to-br from-violet-50 to-fuchsia-50 shadow-sm"
                          : "border-gray-200 hover:border-violet-200 hover:bg-violet-50/40 bg-white")
                      }
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-1.5">
                            {p.starred && <Star className="w-3 h-3 fill-amber-400 text-amber-400" />}
                            <span className="font-medium text-sm truncate">{p.name}</span>
                            <Badge variant="secondary" className="text-[9px] px-1 py-0 ml-1">
                              v{p.current_version_num}
                            </Badge>
                          </div>
                          {p.preview && (
                            <div className="text-[11px] text-gray-500 mt-0.5 line-clamp-2 font-mono">
                              {p.preview}
                            </div>
                          )}
                        </div>
                        <ScoreRing value={p.n_judged ? p.avg_composite : null} size={36} />
                      </div>
                      <div className="flex items-center justify-between mt-2 gap-2">
                        <div className="flex items-center gap-2 text-[10px] text-gray-500 flex-wrap">
                          <span className="inline-flex items-center gap-0.5"><Layers className="w-2.5 h-2.5" /> {p.n_versions}v</span>
                          <span className="inline-flex items-center gap-0.5"><HistoryIcon className="w-2.5 h-2.5" /> {p.n_runs} runs</span>
                          {p.tag && (
                            <span className="inline-flex items-center gap-0.5 text-violet-600">
                              <TagIcon className="w-2.5 h-2.5" /> {p.tag}
                            </span>
                          )}
                          <span className="inline-flex items-center gap-0.5">
                            <Clock className="w-2.5 h-2.5" /> {fmtRel(p.updated_at)}
                          </span>
                        </div>
                        <ScoreSparkline data={p.score_spark} />
                      </div>
                    </button>
                  ))}
                </div>
              )}
            </ScrollArea>
          </CardContent>
        </Card>

        {/* Detail */}
        <div className="lg:col-span-7">
          {!activePrompt ? (
            <Card className="shadow-md border-0 bg-white/60 backdrop-blur-sm h-full">
              <CardContent className="flex items-center justify-center h-[600px] text-sm text-gray-400">
                Select a prompt to inspect versions →
              </CardContent>
            </Card>
          ) : (
            <Card className="shadow-md border-0 bg-white/60 backdrop-blur-sm">
              <CardHeader className="pb-3">
                <div className="flex items-start justify-between gap-2 flex-wrap">
                  <div className="flex items-start gap-3 flex-1 min-w-0">
                    <ScoreRing
                      value={
                        activePrompt.versions.find((v) => v.id === headId)?.stats?.n_judged
                          ? activePrompt.versions.find((v) => v.id === headId)?.stats?.avg_composite
                          : null
                      }
                      size={48}
                      label="head version"
                    />
                    <div className="flex-1 min-w-0">
                      {nameEditing ? (
                        <div className="flex items-center gap-1">
                          <Input
                            value={nameDraft}
                            onChange={(e) => setNameDraft(e.target.value)}
                            onKeyDown={(e) => e.key === "Enter" && handleRename()}
                            className="h-8 text-base font-semibold"
                            autoFocus
                          />
                          <Button onClick={handleRename} size="sm" variant="ghost" className="h-8 px-2">
                            <Check className="w-4 h-4 text-emerald-600" />
                          </Button>
                          <Button onClick={() => setNameEditing(false)} size="sm" variant="ghost" className="h-8 px-2">
                            <X className="w-4 h-4" />
                          </Button>
                        </div>
                      ) : (
                        <div className="flex items-center gap-1.5">
                          <CardTitle className="text-base truncate">{activePrompt.name}</CardTitle>
                          <Button onClick={() => setNameEditing(true)} size="sm" variant="ghost" className="h-6 px-1">
                            <Edit3 className="w-3 h-3" />
                          </Button>
                          {activePrompt.tag && (
                            <Badge variant="outline" className="text-[10px] gap-0.5">
                              <TagIcon className="w-2.5 h-2.5" /> {activePrompt.tag}
                            </Badge>
                          )}
                        </div>
                      )}
                      <div className="text-[11px] text-gray-500 mt-1">
                        {versions.length} version{versions.length === 1 ? "" : "s"} · created {fmtRel(activePrompt.created_at)} · updated {fmtRel(activePrompt.updated_at)}
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-1">
                    <Button
                      onClick={() => handleStar(!activePrompt.starred)}
                      size="sm"
                      variant="outline"
                      className="h-8 gap-1"
                    >
                      {activePrompt.starred ? (
                        <><Star className="w-3.5 h-3.5 fill-amber-400 text-amber-400" /> Starred</>
                      ) : (
                        <><StarOff className="w-3.5 h-3.5" /> Star</>
                      )}
                    </Button>
                    <Button onClick={() => setEditorOpen(true)} size="sm" className="h-8 gap-1 bg-violet-600 hover:bg-violet-700 text-white">
                      <GitBranch className="w-3.5 h-3.5" /> New version
                    </Button>
                    <Button onClick={handleDelete} size="sm" variant="outline" className="h-8 px-2 text-rose-600 hover:bg-rose-50">
                      <Trash2 className="w-3.5 h-3.5" />
                    </Button>
                  </div>
                </div>
              </CardHeader>
              <CardContent className="space-y-3">
                {/* Version editor */}
                {editorOpen && (
                  <Card className="bg-gradient-to-br from-violet-50/60 to-fuchsia-50/60 border-violet-200">
                    <CardContent className="p-3 space-y-2">
                      <div className="flex items-center justify-between">
                        <Label className="text-xs font-semibold text-violet-700">New version</Label>
                        <span className="text-[10px] text-gray-500">v{(versions.at(-1)?.version_num || 0) + 1} will be created if content differs from head</span>
                      </div>
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                        <div>
                          <Label className="text-[10px] uppercase tracking-wider text-gray-500">System</Label>
                          <Textarea value={editSys} onChange={(e) => setEditSys(e.target.value)} rows={5} className="font-mono text-xs mt-1" />
                        </div>
                        <div>
                          <Label className="text-[10px] uppercase tracking-wider text-gray-500">User template</Label>
                          <Textarea value={editTpl} onChange={(e) => setEditTpl(e.target.value)} rows={5} className="font-mono text-xs mt-1" />
                        </div>
                      </div>
                      <Input value={editNote} onChange={(e) => setEditNote(e.target.value)} placeholder="Change note (optional, e.g. 'tightened tone')" className="h-8 text-xs" />
                      <div className="flex items-center gap-2 justify-end">
                        <Button onClick={() => setEditorOpen(false)} size="sm" variant="ghost" className="h-7">Cancel</Button>
                        <Button onClick={handleAddVersion} size="sm" className="h-7 gap-1 bg-violet-600 hover:bg-violet-700 text-white">
                          <Save className="w-3.5 h-3.5" /> Save version
                        </Button>
                      </div>
                    </CardContent>
                  </Card>
                )}

                {/* Diff banner */}
                {(diffA || diffB) && (
                  <Card className="bg-gradient-to-r from-indigo-50 to-violet-50 border-indigo-200">
                    <CardContent className="p-2 flex items-center justify-between gap-2 flex-wrap">
                      <div className="flex items-center gap-2 text-xs">
                        <GitCompareArrows className="w-4 h-4 text-indigo-600" />
                        <span className="font-medium">
                          {diffA && !diffB && "Pick a second version to diff against"}
                          {diffA && diffB && (() => {
                            const a = versions.find((v) => v.id === diffA);
                            const b = versions.find((v) => v.id === diffB);
                            return `Diffing v${a?.version_num} → v${b?.version_num}`;
                          })()}
                        </span>
                      </div>
                      <Button onClick={clearDiff} size="sm" variant="ghost" className="h-6 text-xs gap-1">
                        <X className="w-3 h-3" /> Clear
                      </Button>
                    </CardContent>
                  </Card>
                )}

                {/* Diff result */}
                {diffResult && (
                  <DiffPanel diff={diffResult} />
                )}

                {/* Version timeline */}
                <div>
                  <Label className="text-[10px] uppercase tracking-wider text-gray-500 mb-1.5 block">
                    Version timeline · click two to diff
                  </Label>
                  <div className="space-y-2">
                    {[...versions].reverse().map((v) => {
                      const isHead = v.id === headId;
                      const isA = v.id === diffA;
                      const isB = v.id === diffB;
                      const ringValue = v.stats?.n_judged ? v.stats.avg_composite : null;
                      return (
                        <div
                          key={v.id}
                          className={
                            "px-3 py-2.5 rounded-lg border transition-all relative " +
                            (isA ? "border-indigo-400 bg-indigo-50 ring-1 ring-indigo-400"
                              : isB ? "border-fuchsia-400 bg-fuchsia-50 ring-1 ring-fuchsia-400"
                              : isHead ? "border-violet-300 bg-violet-50/50"
                              : "border-gray-200 bg-white hover:border-violet-200")
                          }
                        >
                          <div className="flex items-start gap-3">
                            <button
                              onClick={() => handleVersionClick(v.id)}
                              className="shrink-0"
                              title="Click to set diff endpoint"
                            >
                              <ScoreRing value={ringValue} size={42} />
                            </button>
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-2 flex-wrap">
                                <span className="font-semibold text-sm">v{v.version_num}</span>
                                {isHead && (
                                  <Badge className="text-[9px] bg-violet-600 text-white px-1 py-0">HEAD</Badge>
                                )}
                                {isA && <Badge className="text-[9px] bg-indigo-600 text-white px-1 py-0">A</Badge>}
                                {isB && <Badge className="text-[9px] bg-fuchsia-600 text-white px-1 py-0">B</Badge>}
                                <span className="text-[10px] text-gray-500">{fmtRel(v.created_at)}</span>
                                {v.note && (
                                  <span className="text-[11px] italic text-violet-700 truncate">“{v.note}”</span>
                                )}
                              </div>
                              <div className="flex items-center gap-3 mt-1.5 text-[10px] text-gray-600 flex-wrap">
                                <span className="inline-flex items-center gap-0.5">
                                  <HistoryIcon className="w-2.5 h-2.5" /> {v.stats?.n_runs || 0} runs
                                </span>
                                {v.stats?.n_judged > 0 && (
                                  <span className="inline-flex items-center gap-0.5">
                                    <Sparkles className="w-2.5 h-2.5 text-violet-500" />
                                    {v.stats.avg_composite}/100
                                  </span>
                                )}
                                {v.stats?.best_model && (
                                  <span className="inline-flex items-center gap-0.5 text-amber-600">
                                    🏆 {v.stats.best_model.split(":")[1] || v.stats.best_model}
                                  </span>
                                )}
                                {v.stats?.total_cost > 0 && (
                                  <span className="font-mono">{fmtCost(v.stats.total_cost)}</span>
                                )}
                              </div>
                              {/* Tiny preview */}
                              <div className="mt-1.5 font-mono text-[10px] text-gray-500 line-clamp-2">
                                {(v.user_template || v.system_prompt || "").slice(0, 220)}
                              </div>
                            </div>
                            <div className="flex flex-col gap-1 shrink-0">
                              <Button
                                onClick={() => handleRunVersion(v)}
                                size="sm"
                                variant="outline"
                                className="h-7 text-xs gap-1 border-violet-300 hover:bg-violet-50"
                              >
                                <Play className="w-3 h-3 text-violet-600" /> Run
                              </Button>
                              <Button
                                onClick={() => handleVersionClick(v.id)}
                                size="sm"
                                variant="ghost"
                                className="h-7 text-xs gap-1"
                              >
                                <GitCompareArrows className="w-3 h-3" />
                                {isA || isB ? "Picked" : "Diff"}
                              </Button>
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}

// ─── Diff sub-panel ───────────────────────────────────────────────────────

function DiffPanel({ diff }) {
  const a = diff.a;
  const b = diff.b;
  const stats = diff.stats || {};
  const overall = stats.overall || { added: 0, removed: 0, similarity: 1 };
  const sd = diff.score_delta;

  return (
    <Card className="bg-gradient-to-br from-slate-50 to-violet-50 border-violet-200">
      <CardContent className="p-3 space-y-3">
        {/* Diff header */}
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <div className="text-xs font-semibold text-violet-700 flex items-center gap-1.5">
            <GitCompareArrows className="w-4 h-4" />
            v{a.version_num} → v{b.version_num}
          </div>
          <div className="flex items-center gap-2 text-[10px] flex-wrap">
            <span className="px-1.5 py-0.5 rounded bg-emerald-100 text-emerald-700 font-mono">
              +{overall.added}
            </span>
            <span className="px-1.5 py-0.5 rounded bg-rose-100 text-rose-700 font-mono">
              −{overall.removed}
            </span>
            <span className="px-1.5 py-0.5 rounded bg-slate-100 text-slate-600 font-mono">
              {Math.round(overall.similarity * 100)}% similar
            </span>
            <span className="px-1.5 py-0.5 rounded bg-violet-100 text-violet-700 inline-flex items-center gap-1">
              Score Δ: <Delta value={sd} />
            </span>
          </div>
        </div>

        {/* Per-version stats side-by-side */}
        <div className="grid grid-cols-2 gap-2">
          <VersionStatTile v={a} side="A" />
          <VersionStatTile v={b} side="B" />
        </div>

        {/* Unified diff hunks */}
        <div className="rounded-lg bg-slate-900 text-slate-200 font-mono text-[11px] overflow-hidden">
          {diff.hunks.length === 0 ? (
            <div className="px-3 py-4 text-center text-slate-500 italic">
              Identical content (timestamps differ but text matches)
            </div>
          ) : (
            <ScrollArea className="max-h-[280px]">
              {diff.hunks.map((h, i) => (
                <div key={i}>
                  <div className="bg-slate-800 px-3 py-1 text-slate-400 text-[10px]">
                    {h.header}
                  </div>
                  {h.lines.map((line, j) => {
                    const bg =
                      line.type === "add" ? "bg-emerald-500/15 text-emerald-300"
                        : line.type === "del" ? "bg-rose-500/15 text-rose-300"
                        : "text-slate-300";
                    const prefix =
                      line.type === "add" ? "+ "
                        : line.type === "del" ? "− "
                        : "  ";
                    return (
                      <div
                        key={j}
                        className={`px-3 py-0.5 ${bg} whitespace-pre-wrap break-words`}
                      >
                        <span className="opacity-60 select-none">{prefix}</span>
                        {line.text || " "}
                      </div>
                    );
                  })}
                </div>
              ))}
            </ScrollArea>
          )}
        </div>

        <div className="text-[10px] text-gray-500">
          System: +{stats.system?.added || 0} / −{stats.system?.removed || 0} ·
          Template: +{stats.template?.added || 0} / −{stats.template?.removed || 0}
        </div>
      </CardContent>
    </Card>
  );
}

function VersionStatTile({ v, side }) {
  const judged = v.stats?.n_judged || 0;
  const score = judged ? v.stats?.avg_composite : null;
  const sideTint = side === "A" ? "border-indigo-300 bg-indigo-50/60" : "border-fuchsia-300 bg-fuchsia-50/60";
  const sideLabel = side === "A" ? "text-indigo-700" : "text-fuchsia-700";
  return (
    <div className={`rounded-lg border ${sideTint} p-2`}>
      <div className="flex items-center gap-2 mb-1">
        <Badge className={`text-[9px] px-1 py-0 ${side === "A" ? "bg-indigo-600" : "bg-fuchsia-600"} text-white`}>
          {side}
        </Badge>
        <span className={`text-xs font-semibold ${sideLabel}`}>v{v.version_num}</span>
        <span className="text-[10px] text-gray-500">{fmtRel(v.created_at)}</span>
      </div>
      <div className="flex items-center gap-2 text-[10px] text-gray-600 flex-wrap">
        <span>{v.stats?.n_runs || 0} runs</span>
        {judged > 0 ? (
          <span className="font-mono text-violet-700">{score}/100</span>
        ) : (
          <span className="italic text-gray-400">un-judged</span>
        )}
        {v.stats?.best_model && (
          <span className="text-amber-700">🏆 {v.stats.best_model.split(":")[1] || v.stats.best_model}</span>
        )}
      </div>
      {v.note && (
        <div className="text-[10px] italic text-violet-700 mt-1 line-clamp-1">“{v.note}”</div>
      )}
    </div>
  );
}

function StatTile({ icon, label, value, tint = "violet" }) {
  const ring = {
    violet:  "from-violet-500 to-violet-600",
    fuchsia: "from-fuchsia-500 to-fuchsia-600",
    pink:    "from-pink-500 to-pink-600",
    amber:   "from-amber-500 to-orange-500",
  }[tint];
  return (
    <div className="rounded-lg bg-white/70 border border-white/40 px-2.5 py-2 backdrop-blur">
      <div className="flex items-center gap-1 text-[10px] uppercase tracking-wider text-gray-500">
        <div className={`p-0.5 rounded bg-gradient-to-br ${ring} text-white`}>{icon}</div>
        {label}
      </div>
      <div className="text-base font-bold text-gray-900 mt-0.5">{value}</div>
    </div>
  );
}
