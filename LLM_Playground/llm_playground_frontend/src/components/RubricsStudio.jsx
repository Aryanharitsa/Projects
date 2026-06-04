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
import { Slider } from "@/components/ui/slider";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Ruler,
  Plus,
  Search,
  Star,
  StarOff,
  Trash2,
  Save,
  X,
  Sparkles,
  Scale,
  ChevronRight,
  ChevronDown,
  ArrowUp,
  ArrowDown,
  Crown,
  Gauge,
  Clock,
  DollarSign,
  Zap,
  History as HistoryIcon,
  Play,
  RotateCcw,
  CheckCircle2,
  AlertTriangle,
  Tag as TagIcon,
  Hash,
  Award,
  Trophy,
  ListChecks,
} from "lucide-react";
import { toast } from "sonner";
import ApiService from "../services/api";

// ─── Formatting helpers ─────────────────────────────────────────────────────

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

const fmtCost = (c) => {
  if (c == null) return "—";
  if (c === 0) return "$0";
  if (c < 0.001) return `$${(c * 1000).toFixed(3)}m`;
  return `$${Number(c).toFixed(4)}`;
};

const fmtNum = (n, d = 0) => (n == null ? "—" : Number(n).toFixed(d));

const PROVIDER_HUE = {
  OpenAI: "#10a37f",
  Anthropic: "#d97757",
  Google: "#4285f4",
  August: "#8b5cf6",
};
const hueFor = (provider) => PROVIDER_HUE[provider] || "#6366f1";

// ─── Visual primitives ──────────────────────────────────────────────────────

const ScoreRing = ({ value, size = 56, label = "" }) => {
  const has = value != null && !Number.isNaN(Number(value));
  const v = has ? Math.max(0, Math.min(100, Math.round(Number(value)))) : 0;
  const hue = Math.round(v * 1.2);
  const ringColor = has ? `hsl(${hue} 80% 48%)` : "#cbd5e1";
  const innerSize = size - 8;
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
      title={label || (has ? `${v} / 100` : "no judge score")}
    >
      <div
        className="rounded-full bg-white flex items-center justify-center font-semibold text-gray-800"
        style={{ width: innerSize, height: innerSize, fontSize: size / 4 }}
      >
        {has ? v : "—"}
      </div>
    </div>
  );
};

const Kpi = ({ icon: Icon, label, value, sub, accent = "indigo" }) => {
  const accents = {
    indigo: "from-indigo-500 to-violet-500",
    emerald: "from-emerald-500 to-teal-500",
    amber: "from-amber-500 to-orange-500",
    rose: "from-rose-500 to-pink-500",
    sky: "from-sky-500 to-cyan-500",
  };
  return (
    <div className="relative overflow-hidden rounded-xl border bg-white/70 backdrop-blur-sm p-4 shadow-sm">
      <div
        className={`absolute -top-8 -right-8 h-24 w-24 rounded-full bg-gradient-to-br ${accents[accent]} opacity-10`}
      />
      <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-gray-500">
        {Icon ? <Icon className="w-3.5 h-3.5" /> : null}
        {label}
      </div>
      <div className="mt-1 text-2xl font-semibold text-gray-900">{value}</div>
      {sub ? <div className="mt-1 text-xs text-gray-500">{sub}</div> : null}
    </div>
  );
};

const WeightBar = ({ dimensions }) => {
  // A stacked horizontal bar visualising each dimension's slice. Pure CSS.
  if (!dimensions?.length) return null;
  const total = dimensions.reduce((s, d) => s + (Number(d.weight) || 0), 0) || 100;
  return (
    <div className="flex h-2.5 w-full overflow-hidden rounded-full border bg-gray-100">
      {dimensions.map((d, i) => {
        const pct = ((Number(d.weight) || 0) / total) * 100;
        const hue = Math.round(((i / dimensions.length) * 220 + 200) % 360);
        return (
          <div
            key={d.name + i}
            className="h-full transition-all"
            style={{
              width: `${pct}%`,
              background: `hsl(${hue} 75% 55%)`,
            }}
            title={`${d.name}: ${pct.toFixed(1)}%`}
          />
        );
      })}
    </div>
  );
};

const ProgressFill = ({ value, max = 10 }) => {
  const v = Math.max(0, Math.min(max, Number(value) || 0));
  const pct = (v / max) * 100;
  const hue = Math.round(pct * 1.2);
  return (
    <div className="h-2 w-full overflow-hidden rounded-full bg-gray-100">
      <div
        className="h-full rounded-full transition-all"
        style={{ width: `${pct}%`, background: `hsl(${hue} 80% 50%)` }}
      />
    </div>
  );
};

// ─── Empty / loading states ─────────────────────────────────────────────────

const EmptyState = ({ onSeed, onCreate, seeding }) => (
  <Card className="border-2 border-dashed bg-gradient-to-br from-indigo-50/60 via-white to-violet-50/60">
    <CardContent className="py-12 text-center space-y-4">
      <div className="mx-auto h-14 w-14 rounded-2xl bg-gradient-to-br from-indigo-500 to-violet-500 flex items-center justify-center shadow-lg">
        <Scale className="w-7 h-7 text-white" />
      </div>
      <div>
        <div className="text-lg font-semibold text-gray-900">No rubrics yet</div>
        <div className="text-sm text-gray-600 mt-1">
          Rubrics are reusable, anchor-driven scoring sheets the judge uses to evaluate responses.
          <br />
          Seed four starter rubrics (Code, RAG, Support, Creative) to see what a good one looks like.
        </div>
      </div>
      <div className="flex items-center justify-center gap-2">
        <Button
          onClick={onSeed}
          disabled={seeding}
          className="bg-gradient-to-r from-indigo-500 to-violet-500 hover:opacity-90 text-white"
        >
          <Sparkles className="w-4 h-4 mr-2" />
          {seeding ? "Seeding…" : "Seed 4 starter rubrics"}
        </Button>
        <Button variant="outline" onClick={onCreate}>
          <Plus className="w-4 h-4 mr-2" />
          Start from scratch
        </Button>
      </div>
    </CardContent>
  </Card>
);

// ─── Dimension editor row ───────────────────────────────────────────────────

const DimensionRow = ({
  dim,
  index,
  total,
  onChange,
  onRemove,
  onMove,
}) => {
  const [expanded, setExpanded] = useState(false);
  const weight = Number(dim.weight) || 0;
  return (
    <div className="rounded-lg border bg-white shadow-sm">
      <div className="flex items-start gap-2 p-3">
        <div className="flex flex-col gap-0.5 pt-1 text-gray-300">
          <button
            type="button"
            onClick={() => onMove(index, -1)}
            disabled={index === 0}
            className="hover:text-indigo-500 disabled:opacity-30 disabled:cursor-not-allowed"
            title="Move up"
          >
            <ArrowUp className="w-3.5 h-3.5" />
          </button>
          <button
            type="button"
            onClick={() => onMove(index, +1)}
            disabled={index === total - 1}
            className="hover:text-indigo-500 disabled:opacity-30 disabled:cursor-not-allowed"
            title="Move down"
          >
            <ArrowDown className="w-3.5 h-3.5" />
          </button>
        </div>
        <div className="flex-1 space-y-2">
          <div className="flex items-center gap-2">
            <Input
              value={dim.name}
              onChange={(e) => onChange({ ...dim, name: e.target.value })}
              placeholder="Dimension name (e.g. Groundedness)"
              className="flex-1 font-medium"
            />
            <div className="flex items-center gap-2 min-w-[160px]">
              <div className="w-28">
                <Slider
                  value={[weight]}
                  min={0}
                  max={100}
                  step={1}
                  onValueChange={([v]) => onChange({ ...dim, weight: v })}
                />
              </div>
              <div className="w-12 text-right text-sm font-mono tabular-nums text-gray-700">
                {weight}%
              </div>
            </div>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setExpanded((v) => !v)}
              title={expanded ? "Collapse" : "Expand"}
            >
              {expanded ? (
                <ChevronDown className="w-4 h-4" />
              ) : (
                <ChevronRight className="w-4 h-4" />
              )}
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={onRemove}
              title="Remove"
              className="text-rose-500 hover:text-rose-600 hover:bg-rose-50"
            >
              <Trash2 className="w-4 h-4" />
            </Button>
          </div>
          <Input
            value={dim.description}
            onChange={(e) => onChange({ ...dim, description: e.target.value })}
            placeholder="One-line description (what does this dimension measure?)"
            className="text-sm"
          />
          {expanded && (
            <div className="mt-2 space-y-2 rounded-md border bg-gradient-to-br from-indigo-50/40 to-white p-3">
              <div className="text-xs font-medium uppercase tracking-wider text-indigo-700">
                Anchors — what does each score level look like?
              </div>
              {["0", "5", "10"].map((lvl) => (
                <div key={lvl} className="space-y-1">
                  <div className="flex items-center gap-2 text-xs text-gray-600">
                    <Badge
                      variant="outline"
                      className="font-mono"
                      style={{
                        background:
                          lvl === "0"
                            ? "linear-gradient(90deg, #fee2e2, #fecaca)"
                            : lvl === "5"
                            ? "linear-gradient(90deg, #fef3c7, #fde68a)"
                            : "linear-gradient(90deg, #dcfce7, #bbf7d0)",
                      }}
                    >
                      {lvl}
                    </Badge>
                    <span className="text-gray-500">
                      {lvl === "0"
                        ? "fails this dimension"
                        : lvl === "5"
                        ? "middling"
                        : "exemplary"}
                    </span>
                  </div>
                  <Textarea
                    value={dim.anchors?.[lvl] || ""}
                    onChange={(e) =>
                      onChange({
                        ...dim,
                        anchors: { ...(dim.anchors || {}), [lvl]: e.target.value },
                      })
                    }
                    placeholder={`What a ${lvl}/10 response on "${
                      dim.name || "this dimension"
                    }" looks like…`}
                    className="text-sm min-h-[58px]"
                  />
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

// ─── Main component ─────────────────────────────────────────────────────────

const blankDimension = () => ({
  name: "",
  description: "",
  weight: 25,
  anchors: { 0: "", 5: "", 10: "" },
});

const blankRubric = () => ({
  name: "",
  description: "",
  tag: "",
  judge_addendum: "",
  dimensions: [blankDimension(), blankDimension(), blankDimension(), blankDimension()],
});

export default function RubricsStudio() {
  const [stats, setStats] = useState(null);
  const [rubrics, setRubrics] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [seeding, setSeeding] = useState(false);
  const [query, setQuery] = useState("");
  const [tagFilter, setTagFilter] = useState("");
  const [starredOnly, setStarredOnly] = useState(false);
  const [selectedId, setSelectedId] = useState(null);
  const [selected, setSelected] = useState(null);
  const [draftMode, setDraftMode] = useState(false); // true = creating a new rubric

  // Editor state
  const [editName, setEditName] = useState("");
  const [editDesc, setEditDesc] = useState("");
  const [editTag, setEditTag] = useState("");
  const [editAddendum, setEditAddendum] = useState("");
  const [editDims, setEditDims] = useState([]);
  const [editNote, setEditNote] = useState("");
  const [saving, setSaving] = useState(false);

  // Test panel state
  const [testProvider, setTestProvider] = useState("OpenAI");
  const [testModel, setTestModel] = useState("");
  const [testModelsList, setTestModelsList] = useState([]);
  const [testCandidateProvider, setTestCandidateProvider] = useState("");
  const [testCandidateModel, setTestCandidateModel] = useState("");
  const [testPrompt, setTestPrompt] = useState("");
  const [testResponse, setTestResponse] = useState("");
  const [testSystem, setTestSystem] = useState("");
  const [testRunning, setTestRunning] = useState(false);
  const [testResult, setTestResult] = useState(null);

  // Revision drawer
  const [showRevisions, setShowRevisions] = useState(false);
  const [showJudgements, setShowJudgements] = useState(false);
  const [judgements, setJudgements] = useState([]);
  const [judgementsLoading, setJudgementsLoading] = useState(false);

  // Right pane tab
  const [rightTab, setRightTab] = useState("builder"); // 'builder' | 'test' | 'history'

  // ───── data loaders ──────────────────────────────────────────────────────

  const loadStats = useCallback(async () => {
    try {
      const data = await ApiService.rubricsStats();
      setStats(data.stats);
    } catch (e) {
      console.error("rubricsStats failed", e);
    }
  }, []);

  const loadRubrics = useCallback(async () => {
    setLoading(true);
    try {
      const data = await ApiService.listRubrics({
        q: query,
        tag: tagFilter,
        starred: starredOnly,
        limit: 200,
      });
      setRubrics(data.rubrics || []);
      setTotal(data.total || 0);
    } catch (e) {
      toast.error("Failed to load rubrics");
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, [query, tagFilter, starredOnly]);

  const loadSelected = useCallback(async (id) => {
    if (!id) {
      setSelected(null);
      return;
    }
    try {
      const data = await ApiService.getRubric(id);
      setSelected(data.rubric);
      // Hydrate editor from the loaded rubric.
      setEditName(data.rubric.name || "");
      setEditDesc(data.rubric.description || "");
      setEditTag(data.rubric.tag || "");
      setEditAddendum(data.rubric.judge_addendum || "");
      setEditDims(
        (data.rubric.dimensions || []).map((d) => ({
          name: d.name || "",
          description: d.description || "",
          weight: d.weight || 0,
          anchors: { 0: "", 5: "", 10: "", ...(d.anchors || {}) },
        })),
      );
      setEditNote("");
      setDraftMode(false);
      setTestResult(null);
    } catch (e) {
      toast.error("Failed to load rubric");
      console.error(e);
    }
  }, []);

  const loadJudgements = useCallback(
    async (id) => {
      if (!id) return;
      setJudgementsLoading(true);
      try {
        const data = await ApiService.listRubricJudgements(id, { limit: 50 });
        setJudgements(data.judgements || []);
      } catch (e) {
        console.error(e);
      } finally {
        setJudgementsLoading(false);
      }
    },
    [],
  );

  // Provider models for the Test panel.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const models = await ApiService.getModels(testProvider);
        if (!cancelled) {
          setTestModelsList(models || []);
          if ((models || []).length > 0 && !testModel) {
            setTestModel(models[0]);
          }
        }
      } catch (e) {
        if (!cancelled) setTestModelsList([]);
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [testProvider]);

  // First load: stats + list.
  useEffect(() => {
    loadStats();
    loadRubrics();
  }, [loadStats, loadRubrics]);

  // Reload list when filters change.
  useEffect(() => {
    loadRubrics();
  }, [query, tagFilter, starredOnly, loadRubrics]);

  // Load detail when selectedId changes.
  useEffect(() => {
    if (selectedId) {
      loadSelected(selectedId);
    }
  }, [selectedId, loadSelected]);

  // ───── derived ───────────────────────────────────────────────────────────

  const weightSum = useMemo(
    () => editDims.reduce((s, d) => s + (Number(d.weight) || 0), 0),
    [editDims],
  );

  const allTags = useMemo(() => {
    const t = new Set();
    rubrics.forEach((r) => {
      if (r.tag) t.add(r.tag);
    });
    return Array.from(t).sort();
  }, [rubrics]);

  const tagHue = (tag) => {
    if (!tag) return "#a3a3a3";
    let h = 0;
    for (let i = 0; i < tag.length; i++) h = (h * 31 + tag.charCodeAt(i)) % 360;
    return `hsl(${h} 65% 50%)`;
  };

  const dimsChanged = useMemo(() => {
    if (!selected || draftMode) return true;
    const cur = selected.dimensions || [];
    if (cur.length !== editDims.length) return true;
    const norm = (d) =>
      JSON.stringify({
        n: d.name,
        d: d.description,
        w: Number(d.weight) || 0,
        a: ["0", "5", "10"].map((l) => (d.anchors?.[l] || "").trim()),
      });
    for (let i = 0; i < cur.length; i++) {
      if (norm(cur[i]) !== norm(editDims[i])) return true;
    }
    return (selected.judge_addendum || "") !== (editAddendum || "");
  }, [selected, editDims, editAddendum, draftMode]);

  const metaChanged = useMemo(() => {
    if (!selected || draftMode) return true;
    return (
      (selected.name || "") !== editName ||
      (selected.description || "") !== editDesc ||
      (selected.tag || "") !== editTag
    );
  }, [selected, editName, editDesc, editTag, draftMode]);

  // ───── actions ───────────────────────────────────────────────────────────

  const startDraft = () => {
    setSelectedId(null);
    setSelected(null);
    const d = blankRubric();
    setEditName(d.name);
    setEditDesc(d.description);
    setEditTag(d.tag);
    setEditAddendum(d.judge_addendum);
    setEditDims(d.dimensions);
    setEditNote("");
    setDraftMode(true);
    setRightTab("builder");
    setTestResult(null);
  };

  const seed = async () => {
    setSeeding(true);
    try {
      const data = await ApiService.seedRubrics();
      toast.success("Starter rubrics seeded");
      await Promise.all([loadRubrics(), loadStats()]);
      const seeded = (data.rubrics || []).find((r) => r.name === "Code Review");
      if (seeded) setSelectedId(seeded.id);
    } catch (e) {
      toast.error("Seed failed");
      console.error(e);
    } finally {
      setSeeding(false);
    }
  };

  const validateForSave = () => {
    if (!editName.trim()) {
      toast.error("Name is required");
      return false;
    }
    const named = editDims.filter((d) => d.name.trim());
    if (named.length === 0) {
      toast.error("Add at least one named dimension");
      return false;
    }
    if (weightSum === 0) {
      toast.error("Total weight must be > 0");
      return false;
    }
    return true;
  };

  const saveDraft = async () => {
    if (!validateForSave()) return;
    setSaving(true);
    try {
      const data = await ApiService.createRubric({
        name: editName.trim(),
        description: editDesc.trim(),
        tag: editTag.trim(),
        dimensions: editDims.filter((d) => d.name.trim()),
        judge_addendum: editAddendum.trim(),
        note: editNote.trim() || "Initial revision",
      });
      toast.success("Rubric created");
      await Promise.all([loadRubrics(), loadStats()]);
      setSelectedId(data.rubric.id);
      setDraftMode(false);
    } catch (e) {
      toast.error(`Save failed: ${e.message}`);
    } finally {
      setSaving(false);
    }
  };

  const saveRevision = async () => {
    if (!selectedId) return;
    if (!validateForSave()) return;
    setSaving(true);
    try {
      // 1) Meta first (name/desc/tag may have changed).
      if (metaChanged) {
        await ApiService.setRubricMeta(selectedId, {
          name: editName.trim(),
          description: editDesc.trim(),
          tag: editTag.trim(),
        });
      }
      // 2) Dimensions / addendum → revision.
      if (dimsChanged || editNote.trim()) {
        const data = await ApiService.saveRubricRevision(selectedId, {
          dimensions: editDims.filter((d) => d.name.trim()),
          judge_addendum: editAddendum.trim(),
          note: editNote.trim(),
        });
        setSelected(data.rubric);
        toast.success(
          `Saved revision ${data.rubric?.current_revision_num}`,
        );
      } else {
        toast.success("Meta saved");
      }
      await Promise.all([loadRubrics(), loadStats(), loadSelected(selectedId)]);
      setEditNote("");
    } catch (e) {
      toast.error(`Save failed: ${e.message}`);
    } finally {
      setSaving(false);
    }
  };

  const toggleStar = async (rubric) => {
    try {
      await ApiService.setRubricMeta(rubric.id, { starred: !rubric.starred });
      await loadRubrics();
      if (selectedId === rubric.id) {
        await loadSelected(rubric.id);
      }
    } catch (e) {
      toast.error("Failed to update star");
    }
  };

  const deleteSelected = async () => {
    if (!selectedId) return;
    if (
      !window.confirm(
        `Delete rubric "${selected?.name || ""}" and all its revisions + judgements? This cannot be undone.`,
      )
    ) {
      return;
    }
    try {
      await ApiService.deleteRubric(selectedId);
      toast.success("Rubric deleted");
      setSelectedId(null);
      setSelected(null);
      await Promise.all([loadRubrics(), loadStats()]);
    } catch (e) {
      toast.error("Delete failed");
    }
  };

  const restoreRevision = async (revisionNum) => {
    if (!selectedId) return;
    try {
      const data = await ApiService.restoreRubricRevision(selectedId, revisionNum, {
        note: `Restored from r${revisionNum}`,
      });
      setSelected(data.rubric);
      await loadSelected(selectedId);
      await loadRubrics();
      toast.success(`Restored r${revisionNum} (now r${data.rubric?.current_revision_num})`);
    } catch (e) {
      toast.error("Restore failed");
    }
  };

  const runTest = async () => {
    if (!selectedId) return;
    if (!testPrompt.trim() || !testResponse.trim()) {
      toast.error("Prompt and response are required");
      return;
    }
    if (!testProvider || !testModel) {
      toast.error("Pick a judge provider + model");
      return;
    }
    setTestRunning(true);
    setTestResult(null);
    try {
      const payload = await ApiService.testRubric(selectedId, {
        user_prompt: testPrompt.trim(),
        response: testResponse.trim(),
        system_prompt: testSystem.trim(),
        judge_provider: testProvider,
        judge_model: testModel,
        candidate_provider: testCandidateProvider.trim(),
        candidate_model: testCandidateModel.trim(),
      });
      if (!payload?.success) {
        throw new Error(payload?.error || "judge call failed");
      }
      setTestResult(payload);
      await Promise.all([loadStats(), loadSelected(selectedId)]);
      toast.success(`Composite ${Number(payload.composite).toFixed(1)} / 100`);
    } catch (e) {
      toast.error(`Test failed: ${e.message}`);
    } finally {
      setTestRunning(false);
    }
  };

  const deleteJudgement = async (jid) => {
    try {
      await ApiService.deleteRubricJudgement(jid);
      await loadJudgements(selectedId);
      await loadStats();
      await loadSelected(selectedId);
      toast.success("Judgement removed");
    } catch (e) {
      toast.error("Delete failed");
    }
  };

  // ───── render ────────────────────────────────────────────────────────────

  const showEmpty = !loading && rubrics.length === 0 && !draftMode && !query && !tagFilter && !starredOnly;

  return (
    <div className="space-y-6">
      {/* HERO BANNER */}
      <Card className="border-0 shadow-lg bg-gradient-to-br from-indigo-600 via-violet-600 to-fuchsia-600 text-white overflow-hidden relative">
        <div className="absolute inset-0 opacity-10" style={{
          background:
            "radial-gradient(circle at 80% 20%, white 0, transparent 40%), radial-gradient(circle at 20% 80%, white 0, transparent 40%)",
        }} />
        <CardContent className="relative py-6 px-6">
          <div className="flex items-start justify-between flex-wrap gap-4">
            <div>
              <div className="flex items-center gap-2 text-sm uppercase tracking-wider text-white/80">
                <Scale className="w-4 h-4" /> Rubrics Studio
                <Badge className="bg-white/20 hover:bg-white/20 text-white border-0 text-[10px] uppercase tracking-wider">
                  Round 9 · new
                </Badge>
              </div>
              <div className="mt-1 text-2xl font-semibold">
                Build the yardstick the judge uses
              </div>
              <div className="mt-1 text-sm text-white/80 max-w-2xl">
                Reusable, anchor-driven scoring sheets. Each dimension carries a 0/5/10
                anchor description, the judge is shown all of it, and the composite is
                computed server-side from per-dim scores. Versioned like prompts.
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Button
                onClick={startDraft}
                className="bg-white text-indigo-700 hover:bg-white/90"
              >
                <Plus className="w-4 h-4 mr-2" />
                New rubric
              </Button>
              {stats && stats.n_rubrics === 0 ? (
                <Button
                  onClick={seed}
                  disabled={seeding}
                  className="bg-white/20 hover:bg-white/30 text-white border border-white/40"
                >
                  <Sparkles className="w-4 h-4 mr-2" />
                  {seeding ? "Seeding…" : "Seed 4 starters"}
                </Button>
              ) : null}
            </div>
          </div>

          {stats ? (
            <div className="mt-5 grid grid-cols-2 md:grid-cols-4 lg:grid-cols-5 gap-3">
              <div className="rounded-lg bg-white/10 backdrop-blur px-3 py-2 border border-white/20">
                <div className="text-[10px] uppercase tracking-wider text-white/70">
                  Rubrics
                </div>
                <div className="text-xl font-semibold">{stats.n_rubrics}</div>
                <div className="text-[11px] text-white/70">
                  {stats.n_starred} starred
                </div>
              </div>
              <div className="rounded-lg bg-white/10 backdrop-blur px-3 py-2 border border-white/20">
                <div className="text-[10px] uppercase tracking-wider text-white/70">
                  Judgements
                </div>
                <div className="text-xl font-semibold">{stats.n_judgements}</div>
                <div className="text-[11px] text-white/70">across all rubrics</div>
              </div>
              <div className="rounded-lg bg-white/10 backdrop-blur px-3 py-2 border border-white/20">
                <div className="text-[10px] uppercase tracking-wider text-white/70">
                  Avg composite
                </div>
                <div className="text-xl font-semibold">
                  {stats.avg_composite != null
                    ? `${Number(stats.avg_composite).toFixed(1)}`
                    : "—"}
                </div>
                <div className="text-[11px] text-white/70">/ 100</div>
              </div>
              <div className="rounded-lg bg-white/10 backdrop-blur px-3 py-2 border border-white/20">
                <div className="text-[10px] uppercase tracking-wider text-white/70">
                  Total spend
                </div>
                <div className="text-xl font-semibold">{fmtCost(stats.total_cost)}</div>
                <div className="text-[11px] text-white/70">judge calls</div>
              </div>
              {stats.best_model ? (
                <div className="rounded-lg bg-gradient-to-br from-amber-300/30 to-amber-500/30 backdrop-blur px-3 py-2 border border-amber-200/50 col-span-2 md:col-span-1">
                  <div className="text-[10px] uppercase tracking-wider text-white/80 flex items-center gap-1">
                    <Crown className="w-3 h-3" /> Best model
                  </div>
                  <div
                    className="text-sm font-semibold truncate"
                    title={`${stats.best_model.provider}:${stats.best_model.model}`}
                  >
                    {stats.best_model.model}
                  </div>
                  <div className="text-[11px] text-white/80">
                    {Number(stats.best_model.avg_composite).toFixed(1)} avg ·{" "}
                    {stats.best_model.n_judgements} runs
                  </div>
                </div>
              ) : null}
            </div>
          ) : null}
        </CardContent>
      </Card>

      {showEmpty ? <EmptyState onSeed={seed} onCreate={startDraft} seeding={seeding} /> : null}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* LEFT — LIST */}
        <div className="lg:col-span-1 space-y-3">
          <Card className="border bg-white/70 backdrop-blur-sm shadow-sm">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm flex items-center gap-2 text-gray-700">
                <Ruler className="w-4 h-4" /> Your rubrics
                <Badge variant="outline" className="ml-auto font-mono">{total}</Badge>
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="relative">
                <Search className="w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400" />
                <Input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Search rubrics…"
                  className="pl-8 h-8 text-sm"
                />
              </div>
              <div className="flex items-center justify-between gap-2 flex-wrap">
                <Select
                  value={tagFilter || "_all"}
                  onValueChange={(v) => setTagFilter(v === "_all" ? "" : v)}
                >
                  <SelectTrigger className="h-8 text-xs flex-1 min-w-[120px]">
                    <SelectValue placeholder="All tags" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="_all">All tags</SelectItem>
                    {allTags.map((t) => (
                      <SelectItem key={t} value={t}>
                        {t}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <div className="flex items-center gap-1.5">
                  <Switch
                    id="starred-only"
                    checked={starredOnly}
                    onCheckedChange={setStarredOnly}
                  />
                  <Label
                    htmlFor="starred-only"
                    className="text-xs cursor-pointer flex items-center gap-1"
                  >
                    <Star className="w-3 h-3 text-amber-500" />
                    Starred
                  </Label>
                </div>
              </div>
              <ScrollArea className="h-[480px] pr-2">
                <div className="space-y-2">
                  {loading ? (
                    <div className="text-xs text-gray-500 text-center py-4">Loading…</div>
                  ) : null}
                  {!loading && rubrics.length === 0 && (query || tagFilter || starredOnly) ? (
                    <div className="text-xs text-gray-500 text-center py-4">
                      No rubrics match. Clear filters?
                    </div>
                  ) : null}
                  {rubrics.map((r) => {
                    const active = r.id === selectedId;
                    return (
                      <button
                        key={r.id}
                        onClick={() => {
                          setSelectedId(r.id);
                          setRightTab("builder");
                        }}
                        className={`w-full text-left rounded-lg p-3 border transition-all ${
                          active
                            ? "border-indigo-300 bg-gradient-to-br from-indigo-50 to-violet-50 shadow-sm ring-1 ring-indigo-200"
                            : "border-gray-200 bg-white hover:border-gray-300 hover:shadow-sm"
                        }`}
                      >
                        <div className="flex items-start gap-2">
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-1.5">
                              <div className="text-sm font-medium text-gray-900 truncate">
                                {r.name || "(untitled)"}
                              </div>
                              {r.starred ? (
                                <Star className="w-3 h-3 text-amber-500 fill-amber-500" />
                              ) : null}
                            </div>
                            {r.description ? (
                              <div className="text-xs text-gray-600 truncate mt-0.5">
                                {r.description}
                              </div>
                            ) : null}
                            <div className="flex items-center gap-1.5 mt-1.5 flex-wrap">
                              {r.tag ? (
                                <Badge
                                  variant="outline"
                                  className="text-[10px] py-0 px-1.5 font-mono"
                                  style={{
                                    background: `${tagHue(r.tag)}22`,
                                    color: tagHue(r.tag),
                                    borderColor: `${tagHue(r.tag)}55`,
                                  }}
                                >
                                  <TagIcon className="w-2.5 h-2.5 mr-0.5" />
                                  {r.tag}
                                </Badge>
                              ) : null}
                              <Badge
                                variant="outline"
                                className="text-[10px] py-0 px-1.5 font-mono"
                              >
                                {r.n_dimensions || 0} dims
                              </Badge>
                              {r.n_judgements > 0 ? (
                                <Badge
                                  variant="outline"
                                  className="text-[10px] py-0 px-1.5 font-mono bg-indigo-50 text-indigo-700 border-indigo-200"
                                >
                                  {r.n_judgements} judged
                                </Badge>
                              ) : null}
                              <span className="text-[10px] text-gray-500 ml-auto">
                                {fmtRel(r.updated_at)}
                              </span>
                            </div>
                          </div>
                          {r.avg_composite != null ? (
                            <ScoreRing value={r.avg_composite} size={40} />
                          ) : null}
                        </div>
                      </button>
                    );
                  })}
                </div>
              </ScrollArea>
            </CardContent>
          </Card>

          {/* TOP JUDGES sidebar widget */}
          {stats?.top_judges?.length ? (
            <Card className="border bg-white/70 backdrop-blur-sm shadow-sm">
              <CardHeader className="pb-2">
                <CardTitle className="text-xs uppercase tracking-wider text-gray-600 flex items-center gap-2">
                  <Award className="w-3.5 h-3.5" /> Top judges
                </CardTitle>
              </CardHeader>
              <CardContent className="pt-0 space-y-2">
                {stats.top_judges.slice(0, 5).map((j, i) => (
                  <div
                    key={`${j.provider}:${j.model}`}
                    className="flex items-center gap-2 text-xs"
                  >
                    <div
                      className="h-2.5 w-2.5 rounded-full"
                      style={{ background: hueFor(j.provider) }}
                    />
                    <div className="flex-1 min-w-0">
                      <div className="truncate font-medium text-gray-800">
                        {j.model}
                      </div>
                      <div className="text-[10px] text-gray-500">
                        {j.n_uses} uses · {fmtNum(j.avg_latency, 2)}s · {fmtCost(j.total_cost)}
                      </div>
                    </div>
                    <Badge
                      variant="outline"
                      className="font-mono text-[10px]"
                    >
                      avg {fmtNum(j.avg_composite, 1)}
                    </Badge>
                  </div>
                ))}
              </CardContent>
            </Card>
          ) : null}
        </div>

        {/* RIGHT — DETAIL */}
        <div className="lg:col-span-2 space-y-3">
          {!selected && !draftMode ? (
            <Card className="border-2 border-dashed bg-white/40">
              <CardContent className="py-16 text-center">
                <Scale className="w-10 h-10 mx-auto text-gray-300" />
                <div className="mt-3 text-sm text-gray-600">
                  Pick a rubric on the left, or{" "}
                  <button
                    onClick={startDraft}
                    className="text-indigo-600 underline hover:text-indigo-700"
                  >
                    start a new one
                  </button>
                  .
                </div>
              </CardContent>
            </Card>
          ) : (
            <Card className="border bg-white/70 backdrop-blur-sm shadow-sm">
              <CardHeader className="pb-3">
                <div className="flex items-start justify-between gap-3 flex-wrap">
                  <div className="flex-1 min-w-[300px]">
                    <div className="flex items-center gap-2">
                      <Input
                        value={editName}
                        onChange={(e) => setEditName(e.target.value)}
                        placeholder="Rubric name (e.g. RAG Faithfulness)"
                        className="text-lg font-semibold flex-1"
                      />
                      {!draftMode && selected ? (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => toggleStar(selected)}
                          className="text-amber-500 hover:bg-amber-50"
                        >
                          {selected.starred ? (
                            <Star className="w-4 h-4 fill-amber-500" />
                          ) : (
                            <StarOff className="w-4 h-4" />
                          )}
                        </Button>
                      ) : null}
                    </div>
                    <Textarea
                      value={editDesc}
                      onChange={(e) => setEditDesc(e.target.value)}
                      placeholder="One-line description of what this rubric measures"
                      className="text-sm mt-2 min-h-[44px]"
                    />
                    <div className="flex items-center gap-2 mt-2 flex-wrap">
                      <Input
                        value={editTag}
                        onChange={(e) => setEditTag(e.target.value)}
                        placeholder="Tag (e.g. code, rag, support)"
                        className="text-xs h-7 w-44"
                      />
                      {!draftMode && selected ? (
                        <>
                          <Badge
                            variant="outline"
                            className="font-mono text-[10px]"
                            title="Current revision number"
                          >
                            r{selected.current_revision_num}
                          </Badge>
                          <Badge variant="outline" className="font-mono text-[10px]">
                            {selected.n_judgements || 0} judgements
                          </Badge>
                          {selected.avg_composite != null ? (
                            <Badge
                              variant="outline"
                              className="font-mono text-[10px] bg-emerald-50 text-emerald-700 border-emerald-200"
                            >
                              avg {Number(selected.avg_composite).toFixed(1)}
                            </Badge>
                          ) : null}
                          <span className="text-[10px] text-gray-500 ml-auto">
                            updated {fmtRel(selected.updated_at)}
                          </span>
                        </>
                      ) : (
                        <Badge variant="outline" className="font-mono text-[10px]">
                          NEW
                        </Badge>
                      )}
                    </div>
                  </div>
                </div>
                <Separator className="mt-3" />
                <div className="flex items-center gap-1 mt-2">
                  {[
                    { id: "builder", label: "Builder", icon: Ruler },
                    { id: "test", label: "Test", icon: Play, disabled: draftMode },
                    {
                      id: "history",
                      label: "History",
                      icon: HistoryIcon,
                      disabled: draftMode,
                    },
                  ].map((t) => (
                    <Button
                      key={t.id}
                      variant={rightTab === t.id ? "default" : "ghost"}
                      size="sm"
                      disabled={t.disabled}
                      onClick={() => {
                        setRightTab(t.id);
                        if (t.id === "history" && selectedId) {
                          loadJudgements(selectedId);
                        }
                      }}
                      className={
                        rightTab === t.id
                          ? "bg-gradient-to-r from-indigo-500 to-violet-500 hover:opacity-90 text-white"
                          : ""
                      }
                    >
                      <t.icon className="w-3.5 h-3.5 mr-1.5" />
                      {t.label}
                    </Button>
                  ))}
                </div>
              </CardHeader>

              <CardContent>
                {rightTab === "builder" ? (
                  <div className="space-y-4">
                    {/* Weight summary */}
                    <div className="rounded-lg border bg-white p-3 space-y-2">
                      <div className="flex items-center justify-between">
                        <div className="text-xs uppercase tracking-wider text-gray-500 flex items-center gap-1">
                          <Gauge className="w-3.5 h-3.5" /> Weight distribution
                        </div>
                        <div className="text-xs font-mono">
                          {weightSum === 100 ? (
                            <span className="text-emerald-600 flex items-center gap-1">
                              <CheckCircle2 className="w-3 h-3" />
                              {weightSum}%
                            </span>
                          ) : (
                            <span className="text-amber-600 flex items-center gap-1">
                              <AlertTriangle className="w-3 h-3" />
                              {weightSum}% (normalised to 100% on save)
                            </span>
                          )}
                        </div>
                      </div>
                      <WeightBar dimensions={editDims.filter((d) => d.name.trim())} />
                      <div className="flex flex-wrap gap-1.5 pt-1">
                        {editDims.map((d, i) =>
                          d.name.trim() ? (
                            <Badge
                              key={`${d.name}-${i}`}
                              variant="outline"
                              className="text-[10px] font-mono"
                            >
                              {d.name} · {Number(d.weight) || 0}%
                            </Badge>
                          ) : null,
                        )}
                      </div>
                    </div>

                    {/* Dimensions */}
                    <div className="space-y-2">
                      <div className="flex items-center justify-between">
                        <Label className="text-sm">Dimensions</Label>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => setEditDims([...editDims, blankDimension()])}
                        >
                          <Plus className="w-3.5 h-3.5 mr-1" />
                          Add dimension
                        </Button>
                      </div>
                      {editDims.map((d, i) => (
                        <DimensionRow
                          key={i}
                          dim={d}
                          index={i}
                          total={editDims.length}
                          onChange={(next) =>
                            setEditDims((arr) => arr.map((x, j) => (j === i ? next : x)))
                          }
                          onRemove={() =>
                            setEditDims((arr) => arr.filter((_, j) => j !== i))
                          }
                          onMove={(idx, dir) =>
                            setEditDims((arr) => {
                              const next = [...arr];
                              const tgt = idx + dir;
                              if (tgt < 0 || tgt >= next.length) return next;
                              const tmp = next[idx];
                              next[idx] = next[tgt];
                              next[tgt] = tmp;
                              return next;
                            })
                          }
                        />
                      ))}
                    </div>

                    {/* Judge addendum */}
                    <div className="space-y-1">
                      <Label className="text-sm flex items-center gap-1">
                        <Sparkles className="w-3.5 h-3.5 text-indigo-500" />
                        Judge guidance (shown to the judge model)
                      </Label>
                      <Textarea
                        value={editAddendum}
                        onChange={(e) => setEditAddendum(e.target.value)}
                        placeholder="Optional. Domain-specific guidance the judge should follow when scoring — e.g. 'treat unsupported claims as the most severe failure mode'."
                        className="text-sm min-h-[64px]"
                      />
                    </div>

                    {/* Save bar */}
                    <div className="flex items-center justify-between gap-2 pt-2 border-t">
                      <div className="flex-1">
                        <Input
                          value={editNote}
                          onChange={(e) => setEditNote(e.target.value)}
                          placeholder="Change note (optional — appears in the revision log)"
                          className="text-xs h-8"
                        />
                      </div>
                      <div className="flex items-center gap-2">
                        {!draftMode && selected ? (
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => loadSelected(selectedId)}
                            title="Discard local edits"
                          >
                            <RotateCcw className="w-3.5 h-3.5 mr-1" />
                            Revert
                          </Button>
                        ) : null}
                        {!draftMode && selected ? (
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={deleteSelected}
                            className="text-rose-600 hover:bg-rose-50 hover:text-rose-700"
                          >
                            <Trash2 className="w-3.5 h-3.5 mr-1" />
                            Delete
                          </Button>
                        ) : null}
                        <Button
                          size="sm"
                          disabled={saving || (!draftMode && !dimsChanged && !metaChanged && !editNote.trim())}
                          onClick={draftMode ? saveDraft : saveRevision}
                          className="bg-gradient-to-r from-indigo-500 to-violet-500 hover:opacity-90 text-white"
                        >
                          <Save className="w-3.5 h-3.5 mr-1.5" />
                          {saving
                            ? "Saving…"
                            : draftMode
                            ? "Create rubric"
                            : dimsChanged
                            ? "Save revision"
                            : "Save meta"}
                        </Button>
                      </div>
                    </div>

                    {/* Revisions */}
                    {!draftMode && selected?.revisions?.length ? (
                      <div className="rounded-lg border bg-gray-50/40">
                        <button
                          type="button"
                          onClick={() => setShowRevisions((v) => !v)}
                          className="w-full flex items-center justify-between px-3 py-2 text-sm text-gray-700 hover:bg-gray-100/60 rounded-lg"
                        >
                          <span className="flex items-center gap-2">
                            <HistoryIcon className="w-3.5 h-3.5" />
                            Revision history
                            <Badge variant="outline" className="font-mono">
                              {selected.revisions.length}
                            </Badge>
                          </span>
                          {showRevisions ? (
                            <ChevronDown className="w-4 h-4" />
                          ) : (
                            <ChevronRight className="w-4 h-4" />
                          )}
                        </button>
                        {showRevisions ? (
                          <div className="border-t divide-y">
                            {selected.revisions.map((rev) => {
                              const isCurrent =
                                rev.revision_num === selected.current_revision_num;
                              return (
                                <div
                                  key={rev.id}
                                  className="px-3 py-2 flex items-start gap-3"
                                >
                                  <Badge
                                    className={`font-mono ${
                                      isCurrent
                                        ? "bg-emerald-500 hover:bg-emerald-500 text-white"
                                        : "bg-gray-100 hover:bg-gray-100 text-gray-700"
                                    }`}
                                  >
                                    r{rev.revision_num}
                                  </Badge>
                                  <div className="flex-1 min-w-0">
                                    <div className="text-sm text-gray-800 truncate">
                                      {rev.note || "(no note)"}
                                    </div>
                                    <div className="text-[11px] text-gray-500 flex items-center gap-1.5">
                                      <Clock className="w-3 h-3" />
                                      {fmtRel(rev.created_at)}
                                      <span className="text-gray-300">·</span>
                                      <Hash className="w-3 h-3" />
                                      {(rev.dimensions || []).length} dims
                                      {rev.parent_revision ? (
                                        <>
                                          <span className="text-gray-300">·</span>
                                          parent r{rev.parent_revision}
                                        </>
                                      ) : null}
                                    </div>
                                  </div>
                                  {!isCurrent ? (
                                    <Button
                                      variant="outline"
                                      size="sm"
                                      onClick={() => restoreRevision(rev.revision_num)}
                                    >
                                      <RotateCcw className="w-3 h-3 mr-1" />
                                      Restore
                                    </Button>
                                  ) : null}
                                </div>
                              );
                            })}
                          </div>
                        ) : null}
                      </div>
                    ) : null}
                  </div>
                ) : null}

                {rightTab === "test" ? (
                  <div className="space-y-4">
                    <div className="rounded-lg border bg-gradient-to-br from-indigo-50/40 to-violet-50/40 p-3 space-y-3">
                      <div className="text-xs uppercase tracking-wider text-indigo-700 font-medium flex items-center gap-1">
                        <Play className="w-3.5 h-3.5" /> Test this rubric
                      </div>
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                        <div>
                          <Label className="text-xs">Judge provider</Label>
                          <Select
                            value={testProvider}
                            onValueChange={(v) => {
                              setTestProvider(v);
                              setTestModel("");
                            }}
                          >
                            <SelectTrigger className="h-8 text-sm">
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                              <SelectItem value="OpenAI">OpenAI</SelectItem>
                              <SelectItem value="Anthropic">Anthropic</SelectItem>
                              <SelectItem value="Google">Google</SelectItem>
                            </SelectContent>
                          </Select>
                        </div>
                        <div>
                          <Label className="text-xs">Judge model</Label>
                          <Select value={testModel} onValueChange={setTestModel}>
                            <SelectTrigger className="h-8 text-sm">
                              <SelectValue placeholder="Pick a model" />
                            </SelectTrigger>
                            <SelectContent className="max-h-[300px]">
                              {testModelsList.map((m) => (
                                <SelectItem key={m} value={m}>
                                  {m}
                                </SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                        </div>
                      </div>
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                        <div>
                          <Label className="text-xs">Candidate provider (optional)</Label>
                          <Input
                            value={testCandidateProvider}
                            onChange={(e) => setTestCandidateProvider(e.target.value)}
                            placeholder="e.g. OpenAI"
                            className="h-8 text-sm"
                          />
                        </div>
                        <div>
                          <Label className="text-xs">Candidate model (optional)</Label>
                          <Input
                            value={testCandidateModel}
                            onChange={(e) => setTestCandidateModel(e.target.value)}
                            placeholder="e.g. gpt-4o-mini — used for leaderboard stats"
                            className="h-8 text-sm"
                          />
                        </div>
                      </div>
                      <div>
                        <Label className="text-xs">System prompt (optional)</Label>
                        <Textarea
                          value={testSystem}
                          onChange={(e) => setTestSystem(e.target.value)}
                          placeholder="Optional — shown to the judge as context"
                          className="text-sm min-h-[48px]"
                        />
                      </div>
                      <div>
                        <Label className="text-xs">User prompt</Label>
                        <Textarea
                          value={testPrompt}
                          onChange={(e) => setTestPrompt(e.target.value)}
                          placeholder="The question / instruction the model was asked"
                          className="text-sm min-h-[72px]"
                        />
                      </div>
                      <div>
                        <Label className="text-xs">Response to score</Label>
                        <Textarea
                          value={testResponse}
                          onChange={(e) => setTestResponse(e.target.value)}
                          placeholder="Paste the model's response here"
                          className="text-sm min-h-[140px] font-mono"
                        />
                      </div>
                      <div className="flex items-center justify-between">
                        <div className="text-xs text-gray-500">
                          The judgement is logged so it counts towards stats and
                          leaderboards.
                        </div>
                        <Button
                          size="sm"
                          disabled={testRunning}
                          onClick={runTest}
                          className="bg-gradient-to-r from-emerald-500 to-teal-500 hover:opacity-90 text-white"
                        >
                          <Play className="w-3.5 h-3.5 mr-1.5" />
                          {testRunning ? "Judging…" : "Run rubric judge"}
                        </Button>
                      </div>
                    </div>

                    {/* Test result */}
                    {testResult ? (
                      <Card className="border bg-white shadow-sm">
                        <CardHeader className="pb-2">
                          <div className="flex items-center justify-between flex-wrap gap-3">
                            <CardTitle className="text-base flex items-center gap-2">
                              <Trophy className="w-4 h-4 text-amber-500" />
                              Verdict
                              {testResult.candidate?.model ? (
                                <Badge variant="outline" className="font-mono text-[10px]">
                                  {testResult.candidate.provider}:
                                  {testResult.candidate.model}
                                </Badge>
                              ) : null}
                            </CardTitle>
                            <div className="flex items-center gap-3">
                              <ScoreRing value={testResult.composite} size={72} />
                              <div className="text-right">
                                <div className="text-xs text-gray-500 uppercase tracking-wider">
                                  Composite
                                </div>
                                <div className="text-2xl font-semibold">
                                  {Number(testResult.composite).toFixed(1)}
                                  <span className="text-sm text-gray-400">/100</span>
                                </div>
                                {!testResult.parsed_ok ? (
                                  <Badge
                                    variant="outline"
                                    className="text-[10px] bg-amber-50 text-amber-700 border-amber-300"
                                  >
                                    judge JSON malformed — scored as 0s
                                  </Badge>
                                ) : null}
                              </div>
                            </div>
                          </div>
                          {testResult.summary ? (
                            <div className="mt-2 text-sm italic text-gray-700">
                              "{testResult.summary}"
                            </div>
                          ) : null}
                        </CardHeader>
                        <CardContent className="space-y-3">
                          <div className="space-y-2">
                            {testResult.dim_verdicts.map((dv) => (
                              <div
                                key={dv.name}
                                className="rounded-lg border bg-gradient-to-br from-white to-indigo-50/30 p-3"
                              >
                                <div className="flex items-center justify-between gap-3">
                                  <div className="flex-1 min-w-0">
                                    <div className="flex items-center gap-2">
                                      <div className="text-sm font-medium text-gray-900 truncate">
                                        {dv.name}
                                      </div>
                                      <Badge
                                        variant="outline"
                                        className="font-mono text-[10px]"
                                      >
                                        {dv.weight}%
                                      </Badge>
                                    </div>
                                  </div>
                                  <div className="font-mono text-sm">
                                    <span
                                      className={
                                        dv.score >= 7
                                          ? "text-emerald-600 font-semibold"
                                          : dv.score >= 4
                                          ? "text-amber-600"
                                          : "text-rose-600"
                                      }
                                    >
                                      {dv.score}
                                    </span>
                                    <span className="text-gray-400">/{dv.max_score}</span>
                                  </div>
                                </div>
                                <div className="mt-2">
                                  <ProgressFill value={dv.score} max={dv.max_score} />
                                </div>
                                {dv.rationale ? (
                                  <div className="mt-1.5 text-xs text-gray-600 italic">
                                    {dv.rationale}
                                  </div>
                                ) : null}
                                <div className="mt-1 text-[10px] text-gray-400 font-mono">
                                  contributes {dv.contribution.toFixed(1)} pts to composite
                                </div>
                              </div>
                            ))}
                          </div>
                          <div className="flex items-center gap-3 text-xs text-gray-500 pt-2 border-t">
                            <div className="flex items-center gap-1">
                              <Clock className="w-3 h-3" />
                              {fmtNum(testResult.judge?.latency, 2)}s
                            </div>
                            <div className="flex items-center gap-1">
                              <DollarSign className="w-3 h-3" />
                              {fmtCost(testResult.judge?.cost_usd)}
                            </div>
                            <div className="flex items-center gap-1">
                              <Zap className="w-3 h-3" />
                              {testResult.judge?.total_tokens} tok
                            </div>
                            <div className="ml-auto">
                              judged by {testResult.judge?.model}
                            </div>
                          </div>
                        </CardContent>
                      </Card>
                    ) : null}
                  </div>
                ) : null}

                {rightTab === "history" ? (
                  <div className="space-y-3">
                    <div className="flex items-center justify-between">
                      <div className="text-sm text-gray-600 flex items-center gap-2">
                        <ListChecks className="w-4 h-4" />
                        {judgements.length} recent judgement{judgements.length === 1 ? "" : "s"}
                      </div>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => loadJudgements(selectedId)}
                        disabled={judgementsLoading}
                      >
                        <RotateCcw className="w-3.5 h-3.5 mr-1" />
                        Refresh
                      </Button>
                    </div>
                    {judgementsLoading ? (
                      <div className="text-xs text-gray-500 text-center py-6">
                        Loading…
                      </div>
                    ) : judgements.length === 0 ? (
                      <div className="rounded-lg border bg-gray-50/40 py-8 text-center text-sm text-gray-500">
                        No judgements yet. Switch to <b>Test</b> and run one.
                      </div>
                    ) : (
                      <ScrollArea className="h-[520px] pr-2">
                        <div className="space-y-2">
                          {judgements.map((j) => {
                            const dims = Array.isArray(j.dim_scores)
                              ? j.dim_scores
                              : [];
                            return (
                              <div
                                key={j.id}
                                className="rounded-lg border bg-white p-3 space-y-2"
                              >
                                <div className="flex items-center justify-between gap-2 flex-wrap">
                                  <div className="flex items-center gap-2">
                                    <ScoreRing value={j.composite} size={36} />
                                    <div>
                                      <div className="text-sm font-medium text-gray-900">
                                        {j.candidate_model
                                          ? `${j.candidate_provider}:${j.candidate_model}`
                                          : "anonymous response"}
                                      </div>
                                      <div className="text-[11px] text-gray-500">
                                        judged by {j.judge_provider}:{j.judge_model} ·{" "}
                                        {fmtRel(j.created_at)} · r{j.revision_num}
                                      </div>
                                    </div>
                                  </div>
                                  <div className="flex items-center gap-2">
                                    <Badge
                                      variant="outline"
                                      className="font-mono text-[10px]"
                                    >
                                      {fmtNum(j.latency, 2)}s
                                    </Badge>
                                    <Badge
                                      variant="outline"
                                      className="font-mono text-[10px]"
                                    >
                                      {fmtCost(j.cost_usd)}
                                    </Badge>
                                    <Button
                                      variant="ghost"
                                      size="sm"
                                      onClick={() => deleteJudgement(j.id)}
                                      className="text-gray-400 hover:text-rose-600 hover:bg-rose-50"
                                    >
                                      <Trash2 className="w-3.5 h-3.5" />
                                    </Button>
                                  </div>
                                </div>
                                {j.summary ? (
                                  <div className="text-xs italic text-gray-700">
                                    "{j.summary}"
                                  </div>
                                ) : null}
                                {dims.length > 0 ? (
                                  <div className="flex flex-wrap gap-1.5">
                                    {dims.map((d) => (
                                      <Badge
                                        key={d.name}
                                        variant="outline"
                                        className={`text-[10px] font-mono ${
                                          d.score >= 7
                                            ? "bg-emerald-50 text-emerald-700 border-emerald-200"
                                            : d.score >= 4
                                            ? "bg-amber-50 text-amber-700 border-amber-200"
                                            : "bg-rose-50 text-rose-700 border-rose-200"
                                        }`}
                                        title={d.rationale || ""}
                                      >
                                        {d.name} {d.score}/{d.max_score}
                                      </Badge>
                                    ))}
                                  </div>
                                ) : null}
                                <details className="text-xs text-gray-600">
                                  <summary className="cursor-pointer text-gray-500 hover:text-gray-700">
                                    Show prompt + response
                                  </summary>
                                  <div className="mt-2 space-y-2">
                                    <div>
                                      <div className="text-[10px] uppercase tracking-wider text-gray-400">
                                        Prompt
                                      </div>
                                      <pre className="whitespace-pre-wrap font-mono text-[11px] bg-gray-50 rounded p-2 max-h-[120px] overflow-auto">
                                        {j.user_prompt}
                                      </pre>
                                    </div>
                                    <div>
                                      <div className="text-[10px] uppercase tracking-wider text-gray-400">
                                        Response
                                      </div>
                                      <pre className="whitespace-pre-wrap font-mono text-[11px] bg-gray-50 rounded p-2 max-h-[200px] overflow-auto">
                                        {j.response}
                                      </pre>
                                    </div>
                                  </div>
                                </details>
                              </div>
                            );
                          })}
                        </div>
                      </ScrollArea>
                    )}
                  </div>
                ) : null}
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
