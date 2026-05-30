import React, { useEffect, useMemo, useState, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
  FlaskConical,
  Plus,
  Search,
  Star,
  StarOff,
  Trash2,
  Edit3,
  Save,
  X,
  Play,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Sparkles,
  ListChecks,
  TrendingUp,
  TrendingDown,
  Minus,
  Clock,
  DollarSign,
  Gauge,
  Trophy,
  ChevronRight,
  ChevronDown,
  Zap,
  GitCompareArrows,
  RotateCcw,
  Tag as TagIcon,
  FileCode2,
  Hash,
  Crown,
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
const fmtPct = (n) => (n == null ? "—" : `${Number(n).toFixed(1)}%`);

const PROVIDER_HUE = {
  OpenAI: "#10a37f",
  Anthropic: "#d97757",
  Google: "#4285f4",
  August: "#8b5cf6",
};
const hueFor = (provider) => PROVIDER_HUE[provider] || "#6366f1";

// ─── Visual primitives ──────────────────────────────────────────────────────

const ScoreRing = ({ value, size = 44 }) => {
  const has = value != null && !Number.isNaN(Number(value));
  const v = has ? Math.max(0, Math.min(100, Math.round(Number(value)))) : 0;
  const hue = Math.round(v * 1.2);
  const ringColor = has ? `hsl(${hue} 80% 48%)` : "#cbd5e1";
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
      title={has ? `${v} / 100` : "no judge score"}
    >
      <div
        className="rounded-full bg-white flex items-center justify-center font-semibold text-gray-800"
        style={{ width: size - 7, height: size - 7, fontSize: size > 40 ? 13 : 11 }}
      >
        {has ? v : "—"}
      </div>
    </div>
  );
};

const PassChip = ({ passed, status }) => {
  if (status === "error") {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-xs font-medium bg-amber-100 text-amber-800 border border-amber-300">
        <AlertTriangle className="w-3 h-3" /> Error
      </span>
    );
  }
  if (passed) {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-xs font-medium bg-emerald-100 text-emerald-800 border border-emerald-300">
        <CheckCircle2 className="w-3 h-3" /> Pass
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-xs font-medium bg-rose-100 text-rose-800 border border-rose-300">
      <XCircle className="w-3 h-3" /> Fail
    </span>
  );
};

const PassRateBar = ({ value, height = 6 }) => {
  const has = value != null;
  const v = has ? Math.max(0, Math.min(100, value)) : 0;
  const hue = Math.round(v * 1.2);
  return (
    <div className="w-full bg-gray-200 rounded-full overflow-hidden" style={{ height }}>
      <div
        className="h-full transition-all"
        style={{
          width: `${has ? v : 0}%`,
          background: has ? `hsl(${hue} 80% 48%)` : "#cbd5e1",
        }}
      />
    </div>
  );
};

const DeltaPill = ({ value, unit = "", invert = false, fmt }) => {
  if (value == null || Number.isNaN(Number(value))) {
    return (
      <span className="inline-flex items-center gap-1 text-xs text-gray-400">
        <Minus className="w-3 h-3" /> —
      </span>
    );
  }
  const v = Number(value);
  const good = invert ? v < 0 : v > 0;
  const same = v === 0;
  const Icon = same ? Minus : good ? TrendingUp : TrendingDown;
  const color = same ? "text-gray-500" : good ? "text-emerald-600" : "text-rose-600";
  const sign = v > 0 ? "+" : "";
  const display = fmt ? fmt(v) : `${sign}${v.toFixed(2)}${unit}`;
  return (
    <span className={`inline-flex items-center gap-1 text-xs font-medium ${color}`}>
      <Icon className="w-3 h-3" /> {display}
    </span>
  );
};

const Sparkbars = ({ rates }) => {
  if (!rates || rates.length === 0) {
    return <div className="h-5 w-20 text-[10px] text-gray-400">no runs</div>;
  }
  const w = 80;
  const h = 18;
  const n = rates.length;
  const bw = Math.max(2, w / n - 1);
  return (
    <svg width={w} height={h} className="overflow-visible">
      {rates.map((r, i) => {
        const val = r == null ? 0 : Math.max(0, Math.min(100, r));
        const bh = Math.max(1, (val / 100) * h);
        const hue = Math.round(val * 1.2);
        const fill = r == null ? "#e5e7eb" : `hsl(${hue} 80% 50%)`;
        return (
          <rect
            key={i}
            x={i * (bw + 1)}
            y={h - bh}
            width={bw}
            height={bh}
            fill={fill}
            rx={1}
          />
        );
      })}
    </svg>
  );
};

// ─── Suite list (left column) ───────────────────────────────────────────────

const SuiteListItem = ({ suite, isSelected, onSelect, onToggleStar, onDelete }) => {
  const latest = suite.latest_run;
  const latestRate = latest?.pass_rate;
  return (
    <div
      onClick={() => onSelect(suite.id)}
      className={`relative cursor-pointer rounded-lg border transition-all p-3 ${
        isSelected
          ? "border-indigo-400 bg-gradient-to-r from-indigo-50 to-violet-50 shadow-sm"
          : "border-gray-200 bg-white hover:border-indigo-300 hover:bg-indigo-50/40"
      }`}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 mb-1">
            <FlaskConical className="w-4 h-4 text-indigo-600 shrink-0" />
            <span className="font-semibold text-sm text-gray-900 truncate">{suite.name}</span>
            {suite.tag && (
              <Badge variant="outline" className="text-[10px] py-0 px-1.5 h-4 border-indigo-300 text-indigo-700">
                {suite.tag}
              </Badge>
            )}
          </div>
          <div className="text-xs text-gray-500 line-clamp-2 mb-2">
            {suite.description || "No description"}
          </div>
          <div className="flex items-center gap-3 text-[11px] text-gray-600">
            <span className="inline-flex items-center gap-1">
              <ListChecks className="w-3 h-3" />
              {suite.n_cases} case{suite.n_cases === 1 ? "" : "s"}
            </span>
            <span className="inline-flex items-center gap-1">
              <Play className="w-3 h-3" />
              {suite.n_runs} run{suite.n_runs === 1 ? "" : "s"}
            </span>
            {suite.last_run_at && (
              <span className="inline-flex items-center gap-1 text-gray-500">
                <Clock className="w-3 h-3" />
                {fmtRel(suite.last_run_at)}
              </span>
            )}
          </div>
          {latest && (
            <div className="mt-2 flex items-center gap-2">
              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between text-[10px] text-gray-500 mb-0.5">
                  <span className="truncate" style={{ color: hueFor(latest.provider) }}>
                    {latest.provider}:{latest.model}
                  </span>
                  <span>{fmtPct(latestRate)}</span>
                </div>
                <PassRateBar value={latestRate} />
              </div>
            </div>
          )}
        </div>
        <div className="flex flex-col items-end gap-1">
          <button
            onClick={(e) => {
              e.stopPropagation();
              onToggleStar(suite);
            }}
            className="text-gray-400 hover:text-amber-500 transition-colors"
            title={suite.starred ? "Unstar" : "Star"}
          >
            {suite.starred ? (
              <Star className="w-3.5 h-3.5 fill-amber-400 text-amber-400" />
            ) : (
              <StarOff className="w-3.5 h-3.5" />
            )}
          </button>
          <button
            onClick={(e) => {
              e.stopPropagation();
              if (confirm(`Delete suite "${suite.name}" and all its runs?`)) {
                onDelete(suite);
              }
            }}
            className="text-gray-400 hover:text-rose-500 transition-colors"
            title="Delete suite"
          >
            <Trash2 className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
    </div>
  );
};

// ─── Case editor ────────────────────────────────────────────────────────────

const CaseEditor = ({ caseData, onSave, onCancel }) => {
  const [c, setC] = useState({
    title: caseData?.title || "",
    user_prompt: caseData?.user_prompt || "",
    expected_contains: caseData?.expected_contains || "",
    expected_not_contains: caseData?.expected_not_contains || "",
    expected_regex: caseData?.expected_regex || "",
    expect_json: !!caseData?.expect_json,
    judge_min: caseData?.judge_min ?? "",
    note: caseData?.note || "",
  });

  const setField = (k, v) => setC((p) => ({ ...p, [k]: v }));

  return (
    <div className="border border-indigo-300 rounded-lg bg-gradient-to-br from-indigo-50/40 to-violet-50/40 p-4 space-y-3">
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <div className="sm:col-span-2">
          <Label className="text-xs text-gray-600 mb-1 block">Title</Label>
          <Input
            value={c.title}
            onChange={(e) => setField("title", e.target.value)}
            placeholder="Short label for the case"
            className="text-sm"
          />
        </div>
        <div>
          <Label className="text-xs text-gray-600 mb-1 block">Judge min (0–100)</Label>
          <Input
            type="number"
            min="0"
            max="100"
            step="1"
            value={c.judge_min}
            onChange={(e) => setField("judge_min", e.target.value)}
            placeholder="optional"
            className="text-sm"
          />
        </div>
      </div>
      <div>
        <Label className="text-xs text-gray-600 mb-1 block">User prompt</Label>
        <Textarea
          value={c.user_prompt}
          onChange={(e) => setField("user_prompt", e.target.value)}
          placeholder="The prompt that's sent to the model for this case…"
          rows={4}
          className="text-sm font-mono"
        />
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div>
          <Label className="text-xs text-gray-600 mb-1 block">Must contain</Label>
          <Input
            value={c.expected_contains}
            onChange={(e) => setField("expected_contains", e.target.value)}
            placeholder="substring (case-insensitive)"
            className="text-sm"
          />
        </div>
        <div>
          <Label className="text-xs text-gray-600 mb-1 block">Must NOT contain</Label>
          <Input
            value={c.expected_not_contains}
            onChange={(e) => setField("expected_not_contains", e.target.value)}
            placeholder="forbidden substring"
            className="text-sm"
          />
        </div>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 items-end">
        <div className="sm:col-span-2">
          <Label className="text-xs text-gray-600 mb-1 block">Regex match</Label>
          <Input
            value={c.expected_regex}
            onChange={(e) => setField("expected_regex", e.target.value)}
            placeholder="e.g. \\b408\\b"
            className="text-sm font-mono"
          />
        </div>
        <div className="flex items-center gap-2 pb-2">
          <Switch checked={c.expect_json} onCheckedChange={(v) => setField("expect_json", !!v)} id="expect-json" />
          <Label htmlFor="expect-json" className="text-xs cursor-pointer text-gray-700">
            Response must parse as JSON
          </Label>
        </div>
      </div>
      <div>
        <Label className="text-xs text-gray-600 mb-1 block">Note (optional)</Label>
        <Input
          value={c.note}
          onChange={(e) => setField("note", e.target.value)}
          placeholder="Why this case exists, expected behaviour, etc."
          className="text-sm"
        />
      </div>
      <div className="flex justify-end gap-2 pt-1">
        <Button size="sm" variant="outline" onClick={onCancel}>
          <X className="w-3.5 h-3.5 mr-1" /> Cancel
        </Button>
        <Button
          size="sm"
          onClick={() => {
            if (!c.user_prompt.trim()) {
              toast.error("User prompt is required");
              return;
            }
            onSave({
              ...c,
              judge_min: c.judge_min === "" ? null : Number(c.judge_min),
            });
          }}
          className="bg-gradient-to-r from-indigo-600 to-violet-600 text-white"
        >
          <Save className="w-3.5 h-3.5 mr-1" /> Save case
        </Button>
      </div>
    </div>
  );
};

const CaseRow = ({ caseData, onEdit, onDelete, index }) => {
  const criteria = [];
  if (caseData.expected_contains) criteria.push({ icon: "+", text: caseData.expected_contains, kind: "contains" });
  if (caseData.expected_not_contains) criteria.push({ icon: "−", text: caseData.expected_not_contains, kind: "not_contains" });
  if (caseData.expected_regex) criteria.push({ icon: "/", text: caseData.expected_regex, kind: "regex" });
  if (caseData.expect_json) criteria.push({ icon: "{}", text: "valid JSON", kind: "json" });
  if (caseData.judge_min != null) criteria.push({ icon: "≥", text: `judge ≥ ${caseData.judge_min}`, kind: "judge_min" });
  if (criteria.length === 0) criteria.push({ icon: "✓", text: "non-empty response", kind: "smoke" });

  return (
    <div className="rounded-lg border border-gray-200 bg-white hover:border-indigo-300 transition-colors p-3 group">
      <div className="flex items-start gap-3">
        <div className="flex-shrink-0 w-7 h-7 rounded-md bg-gradient-to-br from-indigo-100 to-violet-100 border border-indigo-200 flex items-center justify-center text-xs font-bold text-indigo-700">
          {index + 1}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className="font-medium text-sm text-gray-900">{caseData.title}</span>
            {caseData.note && (
              <span className="text-[11px] text-gray-500 italic truncate">— {caseData.note}</span>
            )}
          </div>
          <div className="text-xs text-gray-600 font-mono bg-gray-50 rounded px-2 py-1 mb-2 line-clamp-2">
            {caseData.user_prompt}
          </div>
          <div className="flex flex-wrap gap-1.5">
            {criteria.map((c, i) => (
              <span
                key={i}
                className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium bg-indigo-50 border border-indigo-200 text-indigo-800"
                title={c.kind}
              >
                <span className="font-mono">{c.icon}</span>
                <span className="truncate max-w-[200px]">{c.text}</span>
              </span>
            ))}
          </div>
        </div>
        <div className="flex flex-col gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
          <button onClick={() => onEdit(caseData)} className="text-gray-400 hover:text-indigo-600" title="Edit">
            <Edit3 className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={() => {
              if (confirm(`Delete case "${caseData.title}"?`)) onDelete(caseData);
            }}
            className="text-gray-400 hover:text-rose-500"
            title="Delete"
          >
            <Trash2 className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
    </div>
  );
};

// ─── Run-config panel ───────────────────────────────────────────────────────

const RunConfigPanel = ({ suite, onRun, isRunning }) => {
  const [provider, setProvider] = useState("OpenAI");
  const [model, setModel] = useState("");
  const [systemPrompt, setSystemPrompt] = useState("");
  const [judgeOn, setJudgeOn] = useState(false);
  const [judgeProvider, setJudgeProvider] = useState("Anthropic");
  const [judgeModel, setJudgeModel] = useState("");
  const [models, setModels] = useState([]);
  const [judgeModels, setJudgeModels] = useState([]);
  const [note, setNote] = useState("");

  useEffect(() => {
    let cancelled = false;
    ApiService.getModels(provider)
      .then((m) => {
        if (cancelled) return;
        setModels(m);
        if (m.length && !model) setModel(m[0]);
      })
      .catch(() => {});
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [provider]);

  useEffect(() => {
    let cancelled = false;
    if (!judgeOn) return;
    ApiService.getModels(judgeProvider)
      .then((m) => {
        if (cancelled) return;
        setJudgeModels(m);
        if (m.length && !judgeModel) setJudgeModel(m[0]);
      })
      .catch(() => {});
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [judgeProvider, judgeOn]);

  return (
    <Card className="border-indigo-200 shadow-sm bg-gradient-to-br from-white via-indigo-50/30 to-violet-50/30">
      <CardHeader className="pb-3">
        <CardTitle className="text-base flex items-center gap-2">
          <Play className="w-4 h-4 text-indigo-600" />
          Run "{suite.name}" against a model
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <Label className="text-xs text-gray-600 mb-1 block">Provider</Label>
            <Select value={provider} onValueChange={setProvider}>
              <SelectTrigger className="bg-white text-sm">
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
            <Label className="text-xs text-gray-600 mb-1 block">Model</Label>
            <Select value={model} onValueChange={setModel}>
              <SelectTrigger className="bg-white text-sm">
                <SelectValue placeholder="Pick a model…" />
              </SelectTrigger>
              <SelectContent className="max-h-60">
                {models.map((m) => (
                  <SelectItem key={m} value={m}>{m}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
        <div>
          <Label className="text-xs text-gray-600 mb-1 block">
            System prompt <span className="text-gray-400">(applied to every case)</span>
          </Label>
          <Textarea
            value={systemPrompt}
            onChange={(e) => setSystemPrompt(e.target.value)}
            placeholder="optional"
            rows={2}
            className="text-sm"
          />
        </div>

        <div className="rounded-lg border border-violet-200 bg-violet-50/30 p-3">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <Sparkles className="w-4 h-4 text-violet-600" />
              <Label className="text-sm font-medium text-gray-800">
                LLM-as-judge scoring
              </Label>
            </div>
            <Switch checked={judgeOn} onCheckedChange={setJudgeOn} />
          </div>
          <div className="text-[11px] text-gray-500 mb-2">
            Required if any case uses a <code>judge_min</code> threshold. Scores every response 0–100 against the default rubric.
          </div>
          {judgeOn && (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              <Select value={judgeProvider} onValueChange={setJudgeProvider}>
                <SelectTrigger className="bg-white text-sm">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="OpenAI">OpenAI</SelectItem>
                  <SelectItem value="Anthropic">Anthropic</SelectItem>
                  <SelectItem value="Google">Google</SelectItem>
                </SelectContent>
              </Select>
              <Select value={judgeModel} onValueChange={setJudgeModel}>
                <SelectTrigger className="bg-white text-sm">
                  <SelectValue placeholder="Judge model…" />
                </SelectTrigger>
                <SelectContent className="max-h-60">
                  {judgeModels.map((m) => (
                    <SelectItem key={m} value={m}>{m}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}
        </div>

        <div>
          <Label className="text-xs text-gray-600 mb-1 block">Note (optional)</Label>
          <Input
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="e.g. 'after refactoring the system prompt'"
            className="text-sm"
          />
        </div>

        <div className="flex justify-end gap-2 pt-1">
          <Button
            size="sm"
            disabled={!provider || !model || isRunning || suite.cases?.length === 0}
            onClick={() =>
              onRun({
                provider,
                model,
                system_prompt: systemPrompt,
                judge_provider: judgeOn ? judgeProvider : "",
                judge_model: judgeOn ? judgeModel : "",
                note,
              })
            }
            className="bg-gradient-to-r from-indigo-600 to-violet-600 text-white shadow-sm"
          >
            {isRunning ? (
              <>
                <Zap className="w-3.5 h-3.5 mr-1 animate-pulse" />
                Running…
              </>
            ) : (
              <>
                <Play className="w-3.5 h-3.5 mr-1" />
                Run {suite.cases?.length || 0} case{(suite.cases?.length || 0) === 1 ? "" : "s"}
              </>
            )}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
};

// ─── Run history row + selected-run detail ──────────────────────────────────

const RunHistoryRow = ({ run, isSelected, onSelect, isCompareA, isCompareB, onToggleCompare }) => {
  return (
    <div
      onClick={() => onSelect(run.id)}
      className={`cursor-pointer rounded-lg border p-3 transition-all ${
        isSelected
          ? "border-indigo-400 bg-indigo-50/40 shadow-sm"
          : "border-gray-200 bg-white hover:border-indigo-300"
      }`}
    >
      <div className="flex items-center gap-3">
        <div
          className="w-2.5 h-2.5 rounded-full shrink-0"
          style={{ background: hueFor(run.provider) }}
          title={run.provider}
        />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="font-medium text-sm text-gray-900 truncate">
              {run.provider}:{run.model}
            </span>
            {run.judge_model && (
              <span className="text-[10px] text-violet-700 bg-violet-100 border border-violet-200 px-1 py-0 rounded">
                judged
              </span>
            )}
            <span className="text-xs text-gray-500 ml-auto">{fmtRel(run.started_at)}</span>
          </div>
          <div className="flex items-center gap-3 mt-1 text-[11px] text-gray-600">
            <span className="inline-flex items-center gap-1 text-emerald-700">
              <CheckCircle2 className="w-3 h-3" /> {run.n_passed}
            </span>
            <span className="inline-flex items-center gap-1 text-rose-700">
              <XCircle className="w-3 h-3" /> {run.n_failed}
            </span>
            {run.n_errored > 0 && (
              <span className="inline-flex items-center gap-1 text-amber-700">
                <AlertTriangle className="w-3 h-3" /> {run.n_errored}
              </span>
            )}
            <span className="font-semibold text-gray-800">{fmtPct(run.pass_rate)}</span>
            {run.avg_composite != null && (
              <span className="inline-flex items-center gap-1 text-violet-700">
                <Gauge className="w-3 h-3" /> {fmtNum(run.avg_composite, 1)}
              </span>
            )}
            <span className="inline-flex items-center gap-1 text-gray-600 ml-auto">
              {fmtCost(run.total_cost)}
            </span>
          </div>
          <div className="mt-1.5">
            <PassRateBar value={run.pass_rate} height={4} />
          </div>
        </div>
        <div className="flex flex-col gap-1">
          <button
            onClick={(e) => {
              e.stopPropagation();
              onToggleCompare(run.id);
            }}
            className={`text-[10px] px-1.5 py-0.5 rounded border transition-colors ${
              isCompareA
                ? "bg-indigo-600 text-white border-indigo-600"
                : isCompareB
                ? "bg-violet-600 text-white border-violet-600"
                : "bg-white text-gray-600 border-gray-300 hover:border-indigo-400"
            }`}
            title="Pick for compare (max 2)"
          >
            {isCompareA ? "A" : isCompareB ? "B" : "vs"}
          </button>
        </div>
      </div>
    </div>
  );
};

const ReasonBadge = ({ reason }) => {
  const symbols = {
    contains: "+",
    not_contains: "−",
    regex: "/",
    json: "{}",
    judge_min: "≥",
    non_empty: "·",
    no_error: "!",
  };
  const sym = symbols[reason.kind] || "?";
  return (
    <span
      title={reason.detail || reason.kind}
      className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium border ${
        reason.ok
          ? "bg-emerald-50 border-emerald-200 text-emerald-800"
          : "bg-rose-50 border-rose-200 text-rose-800"
      }`}
    >
      <span className="font-mono">{sym}</span>
      <span className="truncate max-w-[180px]">
        {reason.kind === "judge_min"
          ? `≥${reason.expected}${reason.detail ? ` · ${reason.detail}` : ""}`
          : reason.kind === "non_empty"
          ? reason.detail || (reason.ok ? "non-empty" : "empty")
          : reason.kind === "no_error"
          ? reason.detail || "no error"
          : (reason.expected || "")}
      </span>
    </span>
  );
};

const CaseResultRow = ({ result, idx }) => {
  const [open, setOpen] = useState(false);
  return (
    <div className={`rounded-lg border ${
      result.status === "error"
        ? "border-amber-200 bg-amber-50/40"
        : result.passed
        ? "border-emerald-200 bg-emerald-50/30"
        : "border-rose-200 bg-rose-50/30"
    }`}>
      <div
        className="p-3 cursor-pointer"
        onClick={() => setOpen((p) => !p)}
      >
        <div className="flex items-center gap-3">
          <div className="flex-shrink-0 w-7 h-7 rounded-md bg-white border border-gray-200 flex items-center justify-center text-xs font-bold text-gray-700">
            {idx + 1}
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="font-medium text-sm text-gray-900">{result.case_title}</span>
              <PassChip passed={result.passed} status={result.status} />
              {result.composite != null && (
                <span className="text-xs text-violet-700 font-medium inline-flex items-center gap-1">
                  <Gauge className="w-3 h-3" />
                  {fmtNum(result.composite, 1)}
                </span>
              )}
              <span className="text-[11px] text-gray-500 inline-flex items-center gap-1 ml-auto">
                <Clock className="w-3 h-3" /> {fmtNum(result.latency, 2)}s
                <DollarSign className="w-3 h-3 ml-2" /> {fmtCost(result.cost_usd)}
                {open ? <ChevronDown className="w-3 h-3 ml-1" /> : <ChevronRight className="w-3 h-3 ml-1" />}
              </span>
            </div>
            <div className="text-[11px] text-gray-600 font-mono line-clamp-1 mt-1">
              {result.case_prompt}
            </div>
            <div className="flex flex-wrap gap-1 mt-1.5">
              {(result.reasons || []).map((r, i) => (
                <ReasonBadge key={i} reason={r} />
              ))}
            </div>
          </div>
        </div>
      </div>
      {open && (
        <div className="px-3 pb-3 border-t border-gray-200/60">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-3 mt-2">
            <div>
              <Label className="text-[11px] text-gray-500 uppercase tracking-wide">Prompt</Label>
              <pre className="text-xs bg-white border border-gray-200 rounded p-2 max-h-48 overflow-auto whitespace-pre-wrap">
                {result.case_prompt}
              </pre>
            </div>
            <div>
              <Label className="text-[11px] text-gray-500 uppercase tracking-wide">
                Response {result.status === "error" && "(failed)"}
              </Label>
              <pre className="text-xs bg-white border border-gray-200 rounded p-2 max-h-48 overflow-auto whitespace-pre-wrap">
                {result.status === "error"
                  ? `⚠ ${result.error || "Provider call failed"}`
                  : (result.response || "(empty)")}
              </pre>
            </div>
          </div>
          {result.judge_verdict && (
            <div className="mt-2">
              <Label className="text-[11px] text-gray-500 uppercase tracking-wide">
                Judge rationale
              </Label>
              <div className="text-xs bg-violet-50 border border-violet-200 rounded p-2 italic text-violet-900">
                {result.judge_verdict.rationale || "(no rationale)"}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

const RunDetail = ({ run }) => {
  if (!run) return null;
  const summary = useMemo(() => {
    const passByKind = {};
    let n_with_judge = 0;
    let composite_sum = 0;
    (run.results || []).forEach((r) => {
      if (r.composite != null) {
        n_with_judge++;
        composite_sum += r.composite;
      }
      (r.reasons || []).forEach((reason) => {
        if (!passByKind[reason.kind]) {
          passByKind[reason.kind] = { pass: 0, fail: 0 };
        }
        passByKind[reason.kind][reason.ok ? "pass" : "fail"]++;
      });
    });
    return {
      passByKind,
      avg_composite: n_with_judge ? composite_sum / n_with_judge : null,
    };
  }, [run]);

  return (
    <Card className="border-gray-200 shadow-sm">
      <CardHeader className="pb-3">
        <CardTitle className="text-base flex items-center gap-2">
          <Trophy className="w-4 h-4 text-amber-500" />
          Run report — {run.provider}:{run.model}
          <span className="text-xs font-normal text-gray-500 ml-auto">
            {fmtRel(run.started_at)}
          </span>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Headline metrics */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          <div className="rounded-lg bg-gradient-to-br from-emerald-50 to-emerald-100 border border-emerald-200 p-3">
            <div className="text-[10px] uppercase tracking-wide text-emerald-700 font-semibold">Pass rate</div>
            <div className="text-2xl font-bold text-emerald-900 mt-1">{fmtPct(run.pass_rate)}</div>
            <div className="mt-1">
              <PassRateBar value={run.pass_rate} />
            </div>
            <div className="text-[10px] text-emerald-700 mt-1">
              {run.n_passed} pass · {run.n_failed} fail · {run.n_errored} err
            </div>
          </div>
          <div className="rounded-lg bg-gradient-to-br from-violet-50 to-violet-100 border border-violet-200 p-3">
            <div className="text-[10px] uppercase tracking-wide text-violet-700 font-semibold">Avg composite</div>
            <div className="text-2xl font-bold text-violet-900 mt-1">{fmtNum(run.avg_composite, 1)}</div>
            <div className="text-[10px] text-violet-700 mt-1">
              {run.n_judged}/{run.n_cases} judged
            </div>
          </div>
          <div className="rounded-lg bg-gradient-to-br from-amber-50 to-amber-100 border border-amber-200 p-3">
            <div className="text-[10px] uppercase tracking-wide text-amber-700 font-semibold">Total cost</div>
            <div className="text-2xl font-bold text-amber-900 mt-1">{fmtCost(run.total_cost)}</div>
            <div className="text-[10px] text-amber-700 mt-1">
              {(run.n_cases > 0
                ? fmtCost(run.total_cost / run.n_cases)
                : "—")}/case
            </div>
          </div>
          <div className="rounded-lg bg-gradient-to-br from-sky-50 to-sky-100 border border-sky-200 p-3">
            <div className="text-[10px] uppercase tracking-wide text-sky-700 font-semibold">Wall time</div>
            <div className="text-2xl font-bold text-sky-900 mt-1">{fmtNum(run.wall_latency, 1)}s</div>
            <div className="text-[10px] text-sky-700 mt-1">
              {fmtNum(run.total_latency, 1)}s serial
            </div>
          </div>
        </div>

        {/* Per-criterion pass/fail */}
        {Object.keys(summary.passByKind).length > 0 && (
          <div className="rounded-lg border border-gray-200 bg-white p-3">
            <div className="text-xs font-semibold text-gray-700 mb-2 flex items-center gap-2">
              <ListChecks className="w-3.5 h-3.5 text-indigo-600" />
              Criteria breakdown
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2">
              {Object.entries(summary.passByKind).map(([kind, ct]) => {
                const total = ct.pass + ct.fail;
                const rate = total ? (ct.pass / total) * 100 : 0;
                return (
                  <div key={kind} className="text-[11px] bg-gray-50 border border-gray-200 rounded p-2">
                    <div className="font-medium text-gray-700 capitalize">{kind.replace("_", " ")}</div>
                    <div className="flex items-center gap-1 mt-0.5">
                      <span className="text-emerald-600">{ct.pass}</span>
                      <span className="text-gray-400">/</span>
                      <span className="text-rose-600">{ct.fail}</span>
                      <span className="ml-auto text-gray-700 font-medium">{rate.toFixed(0)}%</span>
                    </div>
                    <PassRateBar value={rate} height={3} />
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Per-case results */}
        <div className="space-y-2">
          {(run.results || []).map((r, i) => (
            <CaseResultRow key={r.id} result={r} idx={i} />
          ))}
        </div>
      </CardContent>
    </Card>
  );
};

const CompareDrawer = ({ compare, onClose }) => {
  if (!compare) return null;
  const { summary, rows } = compare;
  return (
    <Card className="border-violet-300 shadow-md bg-gradient-to-br from-white via-violet-50/30 to-fuchsia-50/30">
      <CardHeader className="pb-3">
        <CardTitle className="text-base flex items-center gap-2">
          <GitCompareArrows className="w-4 h-4 text-violet-600" />
          Compare runs
          <button onClick={onClose} className="ml-auto text-gray-400 hover:text-gray-700">
            <X className="w-4 h-4" />
          </button>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-sm">
          <div className="rounded-lg border border-indigo-200 bg-indigo-50/40 p-3">
            <div className="text-[10px] uppercase tracking-wide text-indigo-700 font-semibold">A</div>
            <div className="font-medium">{summary.a.model_key}</div>
            <div className="text-[11px] text-gray-600">{fmtRel(summary.a.started_at)}</div>
            <div className="mt-1 text-xs">
              {fmtPct(summary.a.pass_rate)} · q{fmtNum(summary.a.avg_composite, 1)}
            </div>
          </div>
          <div className="rounded-lg border border-violet-200 bg-violet-50/40 p-3">
            <div className="text-[10px] uppercase tracking-wide text-violet-700 font-semibold">B</div>
            <div className="font-medium">{summary.b.model_key}</div>
            <div className="text-[11px] text-gray-600">{fmtRel(summary.b.started_at)}</div>
            <div className="mt-1 text-xs">
              {fmtPct(summary.b.pass_rate)} · q{fmtNum(summary.b.avg_composite, 1)}
            </div>
          </div>
          <div className="rounded-lg border border-gray-200 bg-white p-3">
            <div className="text-[10px] uppercase tracking-wide text-gray-600 font-semibold">B − A</div>
            <div className="space-y-1 mt-1">
              <div className="flex items-center justify-between text-xs">
                <span className="text-gray-500">Pass rate</span>
                <DeltaPill
                  value={summary.delta.pass_rate}
                  unit="%"
                  fmt={(v) => `${v > 0 ? "+" : ""}${v.toFixed(1)}%`}
                />
              </div>
              <div className="flex items-center justify-between text-xs">
                <span className="text-gray-500">Composite</span>
                <DeltaPill
                  value={summary.delta.avg_composite}
                  fmt={(v) => `${v > 0 ? "+" : ""}${v.toFixed(1)}`}
                />
              </div>
              <div className="flex items-center justify-between text-xs">
                <span className="text-gray-500">Cost</span>
                <DeltaPill
                  value={summary.delta.total_cost}
                  invert={true}
                  fmt={(v) => `${v > 0 ? "+" : ""}$${v.toFixed(4)}`}
                />
              </div>
              <div className="flex items-center justify-between text-xs">
                <span className="text-gray-500">Wall time</span>
                <DeltaPill
                  value={summary.delta.wall_latency}
                  invert={true}
                  fmt={(v) => `${v > 0 ? "+" : ""}${v.toFixed(1)}s`}
                />
              </div>
            </div>
          </div>
        </div>

        <div className="rounded-lg border border-gray-200 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-3 py-2 text-left text-[11px] font-semibold text-gray-600 uppercase tracking-wide">Case</th>
                <th className="px-2 py-2 text-center text-[11px] font-semibold text-gray-600 uppercase tracking-wide">A</th>
                <th className="px-2 py-2 text-center text-[11px] font-semibold text-gray-600 uppercase tracking-wide">B</th>
                <th className="px-2 py-2 text-center text-[11px] font-semibold text-gray-600 uppercase tracking-wide">Δ composite</th>
                <th className="px-2 py-2 text-center text-[11px] font-semibold text-gray-600 uppercase tracking-wide">Pass shift</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => {
                const passShift = row.delta.passed;
                return (
                  <tr key={row.case_id || row.case_idx} className="border-t border-gray-200">
                    <td className="px-3 py-2">
                      <div className="font-medium text-gray-900">{row.title}</div>
                    </td>
                    <td className="px-2 py-2 text-center">
                      {row.a ? <PassChip passed={row.a.passed} status={row.a.status} /> : <span className="text-xs text-gray-400">—</span>}
                      {row.a?.composite != null && (
                        <div className="text-[10px] text-violet-700 mt-0.5">{fmtNum(row.a.composite, 1)}</div>
                      )}
                    </td>
                    <td className="px-2 py-2 text-center">
                      {row.b ? <PassChip passed={row.b.passed} status={row.b.status} /> : <span className="text-xs text-gray-400">—</span>}
                      {row.b?.composite != null && (
                        <div className="text-[10px] text-violet-700 mt-0.5">{fmtNum(row.b.composite, 1)}</div>
                      )}
                    </td>
                    <td className="px-2 py-2 text-center">
                      <DeltaPill value={row.delta.composite} fmt={(v) => `${v > 0 ? "+" : ""}${v.toFixed(1)}`} />
                    </td>
                    <td className="px-2 py-2 text-center">
                      {passShift == null ? (
                        <span className="text-xs text-gray-400">—</span>
                      ) : passShift > 0 ? (
                        <span className="text-emerald-700 text-xs font-medium inline-flex items-center gap-1">
                          <TrendingUp className="w-3 h-3" /> fixed
                        </span>
                      ) : passShift < 0 ? (
                        <span className="text-rose-700 text-xs font-medium inline-flex items-center gap-1">
                          <TrendingDown className="w-3 h-3" /> regressed
                        </span>
                      ) : (
                        <span className="text-gray-500 text-xs inline-flex items-center gap-1">
                          <Minus className="w-3 h-3" /> same
                        </span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
};

// ─── Top-of-page stats banner ───────────────────────────────────────────────

const StatsBanner = ({ stats }) => {
  if (!stats) return null;
  return (
    <div className="grid grid-cols-2 lg:grid-cols-5 gap-2.5 mb-3">
      <div className="rounded-lg bg-gradient-to-br from-indigo-50 to-violet-50 border border-indigo-200 p-2.5">
        <div className="text-[10px] uppercase tracking-wide text-indigo-700 font-semibold">Suites</div>
        <div className="text-xl font-bold text-indigo-900 mt-0.5">{stats.n_suites}</div>
      </div>
      <div className="rounded-lg bg-gradient-to-br from-violet-50 to-fuchsia-50 border border-violet-200 p-2.5">
        <div className="text-[10px] uppercase tracking-wide text-violet-700 font-semibold">Cases</div>
        <div className="text-xl font-bold text-violet-900 mt-0.5">{stats.n_cases}</div>
      </div>
      <div className="rounded-lg bg-gradient-to-br from-emerald-50 to-teal-50 border border-emerald-200 p-2.5">
        <div className="text-[10px] uppercase tracking-wide text-emerald-700 font-semibold">Runs</div>
        <div className="text-xl font-bold text-emerald-900 mt-0.5">{stats.n_runs}</div>
        <div className="text-[10px] text-emerald-700 mt-0.5">
          avg {fmtPct(stats.avg_pass_rate)}
        </div>
      </div>
      <div className="rounded-lg bg-gradient-to-br from-amber-50 to-orange-50 border border-amber-200 p-2.5">
        <div className="text-[10px] uppercase tracking-wide text-amber-700 font-semibold">Spend</div>
        <div className="text-xl font-bold text-amber-900 mt-0.5">{fmtCost(stats.total_cost)}</div>
      </div>
      <div className="rounded-lg bg-gradient-to-br from-rose-50 to-pink-50 border border-rose-200 p-2.5 col-span-2 lg:col-span-1">
        <div className="text-[10px] uppercase tracking-wide text-rose-700 font-semibold inline-flex items-center gap-1">
          <Crown className="w-3 h-3" /> Best model
        </div>
        {stats.best_model ? (
          <>
            <div className="text-xs font-bold text-rose-900 mt-0.5 truncate">{stats.best_model.key}</div>
            <div className="text-[10px] text-rose-700">
              {fmtPct(stats.best_model.avg_pass)} over {stats.best_model.n_runs} run{stats.best_model.n_runs === 1 ? "" : "s"}
            </div>
          </>
        ) : (
          <div className="text-xs text-rose-700 mt-0.5">no runs yet</div>
        )}
      </div>
    </div>
  );
};

// ─── New-suite inline form ──────────────────────────────────────────────────

const NewSuiteForm = ({ onCreate, onCancel }) => {
  const [name, setName] = useState("");
  const [desc, setDesc] = useState("");
  const [tag, setTag] = useState("");
  return (
    <div className="border border-indigo-300 bg-indigo-50/40 rounded-lg p-3 space-y-2">
      <Input
        placeholder="Suite name (e.g. 'JSON Strictness')"
        value={name}
        onChange={(e) => setName(e.target.value)}
        autoFocus
        className="text-sm"
      />
      <Textarea
        placeholder="What does this suite test?"
        value={desc}
        onChange={(e) => setDesc(e.target.value)}
        rows={2}
        className="text-sm"
      />
      <div className="flex items-center gap-2">
        <TagIcon className="w-3.5 h-3.5 text-gray-400" />
        <Input
          placeholder="tag (optional)"
          value={tag}
          onChange={(e) => setTag(e.target.value)}
          className="text-xs h-7"
        />
      </div>
      <div className="flex justify-end gap-2">
        <Button size="sm" variant="outline" onClick={onCancel}>
          <X className="w-3.5 h-3.5 mr-1" /> Cancel
        </Button>
        <Button
          size="sm"
          onClick={() => {
            if (!name.trim()) {
              toast.error("Name is required");
              return;
            }
            onCreate({ name, description: desc, tag: tag.trim() || null });
          }}
          className="bg-gradient-to-r from-indigo-600 to-violet-600 text-white"
        >
          <Plus className="w-3.5 h-3.5 mr-1" /> Create
        </Button>
      </div>
    </div>
  );
};

// ─── Main panel ─────────────────────────────────────────────────────────────

const EvalSuites = () => {
  const [stats, setStats] = useState(null);
  const [suites, setSuites] = useState([]);
  const [search, setSearch] = useState("");
  const [starredOnly, setStarredOnly] = useState(false);
  const [selectedSuiteId, setSelectedSuiteId] = useState(null);
  const [selectedSuite, setSelectedSuite] = useState(null);

  const [editingCase, setEditingCase] = useState(null); // case obj or "new"
  const [showNewSuite, setShowNewSuite] = useState(false);

  const [runs, setRuns] = useState([]);
  const [selectedRunId, setSelectedRunId] = useState(null);
  const [selectedRun, setSelectedRun] = useState(null);
  const [isRunning, setIsRunning] = useState(false);

  const [compareA, setCompareA] = useState(null);
  const [compareB, setCompareB] = useState(null);
  const [compareResult, setCompareResult] = useState(null);

  const refreshStats = useCallback(async () => {
    try {
      const r = await ApiService.suitesStats();
      setStats(r.stats);
    } catch (e) { console.warn(e); }
  }, []);

  const refreshSuites = useCallback(async () => {
    try {
      const r = await ApiService.listSuites({
        q: search || undefined,
        starred: starredOnly || undefined,
      });
      setSuites(r.suites || []);
    } catch (e) { console.warn(e); }
  }, [search, starredOnly]);

  const refreshSelectedSuite = useCallback(async () => {
    if (!selectedSuiteId) {
      setSelectedSuite(null);
      setRuns([]);
      return;
    }
    try {
      const r = await ApiService.getSuite(selectedSuiteId);
      setSelectedSuite(r.suite);
      setRuns(r.suite.recent_runs || []);
    } catch (e) {
      console.warn(e);
      toast.error("Failed to load suite");
    }
  }, [selectedSuiteId]);

  const refreshSelectedRun = useCallback(async () => {
    if (!selectedRunId) {
      setSelectedRun(null);
      return;
    }
    try {
      const r = await ApiService.getSuiteRun(selectedRunId);
      setSelectedRun(r.run);
    } catch (e) {
      console.warn(e);
    }
  }, [selectedRunId]);

  useEffect(() => { refreshStats(); }, [refreshStats]);
  useEffect(() => { refreshSuites(); }, [refreshSuites]);
  useEffect(() => { refreshSelectedSuite(); }, [refreshSelectedSuite]);
  useEffect(() => { refreshSelectedRun(); }, [refreshSelectedRun]);

  // ─── Suite mutations ──────────────────────────────────────────────────────

  const handleCreateSuite = async (payload) => {
    try {
      const r = await ApiService.createSuite(payload);
      toast.success(`Created "${r.suite.name}"`);
      setShowNewSuite(false);
      setSelectedSuiteId(r.suite.id);
      await Promise.all([refreshStats(), refreshSuites()]);
    } catch (e) {
      toast.error(e.message || "Failed to create suite");
    }
  };

  const handleSeedSmoke = async () => {
    try {
      const r = await ApiService.seedSmokeSuite();
      toast.success(`Seeded "Smoke Test" with 6 cases — hit Run to fire it.`);
      setSelectedSuiteId(r.suite.id);
      await Promise.all([refreshStats(), refreshSuites()]);
    } catch (e) {
      toast.error(e.message || "Failed to seed suite");
    }
  };

  const handleToggleStar = async (suite) => {
    try {
      await ApiService.setSuiteMeta(suite.id, { starred: !suite.starred });
      await refreshSuites();
    } catch (e) { toast.error(e.message); }
  };

  const handleDeleteSuite = async (suite) => {
    try {
      await ApiService.deleteSuite(suite.id);
      toast.success(`Deleted "${suite.name}"`);
      if (selectedSuiteId === suite.id) setSelectedSuiteId(null);
      await Promise.all([refreshStats(), refreshSuites()]);
    } catch (e) { toast.error(e.message); }
  };

  // ─── Case mutations ──────────────────────────────────────────────────────

  const handleSaveCase = async (payload) => {
    if (!selectedSuiteId) return;
    try {
      if (editingCase && editingCase !== "new") {
        await ApiService.updateSuiteCase(selectedSuiteId, editingCase.id, payload);
        toast.success("Case updated");
      } else {
        await ApiService.addSuiteCase(selectedSuiteId, payload);
        toast.success("Case added");
      }
      setEditingCase(null);
      await Promise.all([refreshStats(), refreshSelectedSuite()]);
    } catch (e) { toast.error(e.message); }
  };

  const handleDeleteCase = async (c) => {
    try {
      await ApiService.deleteSuiteCase(selectedSuiteId, c.id);
      await Promise.all([refreshStats(), refreshSelectedSuite()]);
    } catch (e) { toast.error(e.message); }
  };

  // ─── Run mutations ──────────────────────────────────────────────────────

  const handleRunSuite = async (cfg) => {
    if (!selectedSuiteId) return;
    setIsRunning(true);
    try {
      const r = await ApiService.runSuite(selectedSuiteId, cfg);
      toast.success(
        `Run finished — ${r.run.n_passed}/${r.run.n_cases} passed (${fmtPct(r.run.pass_rate)}).`
      );
      setSelectedRunId(r.run.id);
      await Promise.all([refreshStats(), refreshSelectedSuite()]);
    } catch (e) {
      toast.error(e.message || "Run failed");
    } finally {
      setIsRunning(false);
    }
  };

  // ─── Compare ─────────────────────────────────────────────────────────────

  const handleToggleCompare = (runId) => {
    if (compareA === runId) {
      setCompareA(null);
      setCompareResult(null);
    } else if (compareB === runId) {
      setCompareB(null);
      setCompareResult(null);
    } else if (!compareA) {
      setCompareA(runId);
    } else if (!compareB) {
      setCompareB(runId);
    } else {
      // both filled — replace B
      setCompareB(runId);
      setCompareResult(null);
    }
  };

  useEffect(() => {
    if (compareA && compareB) {
      ApiService.compareSuiteRuns(compareA, compareB)
        .then((r) => setCompareResult(r.compare))
        .catch((e) => toast.error(e.message || "Compare failed"));
    } else {
      setCompareResult(null);
    }
  }, [compareA, compareB]);

  // ─── Render ──────────────────────────────────────────────────────────────

  return (
    <div className="space-y-4">
      {/* Header */}
      <Card className="border-0 shadow-lg bg-gradient-to-br from-indigo-600 via-violet-600 to-fuchsia-600 text-white">
        <CardContent className="py-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-white/20 backdrop-blur flex items-center justify-center">
              <FlaskConical className="w-6 h-6" />
            </div>
            <div className="flex-1">
              <div className="flex items-center gap-2">
                <h2 className="text-lg font-bold">Eval Suites</h2>
                <span className="text-[10px] uppercase tracking-wider bg-white/25 text-white px-1.5 py-0.5 rounded">new</span>
              </div>
              <p className="text-xs text-white/85 mt-0.5">
                Reproducible test batteries — define a fixed list of cases, run them against any model, and watch pass-rate + judge composite move as you change the prompt or swap the model. Catch regressions before users do.
              </p>
            </div>
          </div>
        </CardContent>
      </Card>

      <StatsBanner stats={stats} />

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
        {/* Suite list */}
        <div className="lg:col-span-4">
          <Card className="border-gray-200 shadow-sm">
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between gap-2">
                <CardTitle className="text-sm flex items-center gap-2">
                  <ListChecks className="w-4 h-4 text-indigo-600" />
                  Suites
                  <span className="text-xs font-normal text-gray-500">({suites.length})</span>
                </CardTitle>
                <Button
                  size="sm"
                  onClick={() => setShowNewSuite((p) => !p)}
                  className="h-7 bg-gradient-to-r from-indigo-600 to-violet-600 text-white"
                >
                  <Plus className="w-3.5 h-3.5 mr-1" /> New
                </Button>
              </div>
              <div className="flex items-center gap-2 mt-2">
                <div className="relative flex-1">
                  <Search className="w-3.5 h-3.5 absolute left-2 top-1/2 -translate-y-1/2 text-gray-400" />
                  <Input
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    placeholder="Search suites…"
                    className="text-xs h-8 pl-7"
                  />
                </div>
                <button
                  onClick={() => setStarredOnly((p) => !p)}
                  className={`p-1.5 rounded transition-colors ${
                    starredOnly ? "bg-amber-100 text-amber-600" : "text-gray-400 hover:text-amber-500"
                  }`}
                  title="Starred only"
                >
                  <Star className={`w-3.5 h-3.5 ${starredOnly ? "fill-amber-400" : ""}`} />
                </button>
              </div>
            </CardHeader>
            <CardContent className="space-y-2">
              {showNewSuite && (
                <NewSuiteForm
                  onCreate={handleCreateSuite}
                  onCancel={() => setShowNewSuite(false)}
                />
              )}
              {suites.length === 0 && !showNewSuite ? (
                <div className="text-center py-8 px-4">
                  <FlaskConical className="w-12 h-12 mx-auto mb-3 text-indigo-400" />
                  <h3 className="text-sm font-semibold text-gray-900 mb-1">
                    No suites yet
                  </h3>
                  <p className="text-xs text-gray-500 mb-4">
                    A suite is a fixed list of test cases you run against any model — define it once, watch for regressions every time you change the prompt or swap models.
                  </p>
                  <div className="flex flex-col gap-2">
                    <Button
                      size="sm"
                      onClick={handleSeedSmoke}
                      className="bg-gradient-to-r from-indigo-600 to-violet-600 text-white"
                    >
                      <Sparkles className="w-3.5 h-3.5 mr-1" /> Seed a starter "Smoke Test" suite
                    </Button>
                    <Button size="sm" variant="outline" onClick={() => setShowNewSuite(true)}>
                      <Plus className="w-3.5 h-3.5 mr-1" /> Create blank suite
                    </Button>
                  </div>
                </div>
              ) : (
                <ScrollArea className="h-[60vh]">
                  <div className="space-y-2 pr-2">
                    {suites.map((s) => (
                      <SuiteListItem
                        key={s.id}
                        suite={s}
                        isSelected={s.id === selectedSuiteId}
                        onSelect={(id) => {
                          setSelectedSuiteId(id);
                          setSelectedRunId(null);
                          setCompareA(null);
                          setCompareB(null);
                        }}
                        onToggleStar={handleToggleStar}
                        onDelete={handleDeleteSuite}
                      />
                    ))}
                  </div>
                </ScrollArea>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Detail column */}
        <div className="lg:col-span-8 space-y-4">
          {!selectedSuite ? (
            <Card className="border-dashed border-2 border-gray-300 bg-white/60 backdrop-blur-sm">
              <CardContent className="py-16 text-center">
                <FlaskConical className="w-14 h-14 mx-auto mb-4 text-indigo-300" />
                <h3 className="text-base font-semibold text-gray-700 mb-2">
                  Pick a suite to inspect or run
                </h3>
                <p className="text-sm text-gray-500 max-w-md mx-auto">
                  Or seed the starter "Smoke Test" to see a full end-to-end run in 30 seconds.
                </p>
              </CardContent>
            </Card>
          ) : (
            <>
              {/* Suite header */}
              <Card className="border-gray-200 shadow-sm">
                <CardContent className="py-4">
                  <div className="flex items-start gap-3">
                    <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-indigo-100 to-violet-100 border border-indigo-200 flex items-center justify-center">
                      <FlaskConical className="w-5 h-5 text-indigo-600" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <h3 className="text-lg font-bold text-gray-900">{selectedSuite.name}</h3>
                        {selectedSuite.tag && (
                          <Badge variant="outline" className="text-[10px] border-indigo-300 text-indigo-700">
                            {selectedSuite.tag}
                          </Badge>
                        )}
                        <button
                          onClick={() => handleToggleStar(selectedSuite)}
                          className="text-gray-400 hover:text-amber-500 ml-auto"
                        >
                          {selectedSuite.starred ? (
                            <Star className="w-4 h-4 fill-amber-400 text-amber-400" />
                          ) : (
                            <StarOff className="w-4 h-4" />
                          )}
                        </button>
                      </div>
                      <p className="text-xs text-gray-600">{selectedSuite.description || "No description"}</p>
                      <div className="flex items-center gap-3 mt-2 text-[11px] text-gray-500">
                        <span className="inline-flex items-center gap-1">
                          <ListChecks className="w-3 h-3" /> {selectedSuite.cases?.length || 0} cases
                        </span>
                        <span className="inline-flex items-center gap-1">
                          <Hash className="w-3 h-3" /> {selectedSuite.id.slice(0, 8)}
                        </span>
                        <span>updated {fmtRel(selectedSuite.updated_at)}</span>
                      </div>
                    </div>
                  </div>
                </CardContent>
              </Card>

              {/* Run config */}
              <RunConfigPanel suite={selectedSuite} onRun={handleRunSuite} isRunning={isRunning} />

              {/* Cases */}
              <Card className="border-gray-200 shadow-sm">
                <CardHeader className="pb-3">
                  <div className="flex items-center justify-between">
                    <CardTitle className="text-sm flex items-center gap-2">
                      <ListChecks className="w-4 h-4 text-indigo-600" />
                      Cases
                      <span className="text-xs font-normal text-gray-500">
                        ({selectedSuite.cases?.length || 0})
                      </span>
                    </CardTitle>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => setEditingCase("new")}
                      disabled={editingCase === "new"}
                    >
                      <Plus className="w-3.5 h-3.5 mr-1" /> Add case
                    </Button>
                  </div>
                </CardHeader>
                <CardContent className="space-y-2">
                  {editingCase === "new" && (
                    <CaseEditor onSave={handleSaveCase} onCancel={() => setEditingCase(null)} />
                  )}
                  {(selectedSuite.cases || []).map((c, i) => {
                    const isEditing = editingCase && editingCase !== "new" && editingCase.id === c.id;
                    if (isEditing) {
                      return (
                        <CaseEditor
                          key={c.id}
                          caseData={c}
                          onSave={handleSaveCase}
                          onCancel={() => setEditingCase(null)}
                        />
                      );
                    }
                    return (
                      <CaseRow
                        key={c.id}
                        caseData={c}
                        index={i}
                        onEdit={setEditingCase}
                        onDelete={handleDeleteCase}
                      />
                    );
                  })}
                  {(selectedSuite.cases || []).length === 0 && !editingCase && (
                    <div className="text-center py-8 text-sm text-gray-500">
                      <FileCode2 className="w-8 h-8 mx-auto mb-2 text-gray-300" />
                      No cases yet — click "Add case" to define your first test.
                    </div>
                  )}
                </CardContent>
              </Card>

              {/* Run history */}
              {(runs.length > 0 || selectedRun) && (
                <Card className="border-gray-200 shadow-sm">
                  <CardHeader className="pb-3">
                    <div className="flex items-center justify-between">
                      <CardTitle className="text-sm flex items-center gap-2">
                        <Clock className="w-4 h-4 text-indigo-600" />
                        Recent runs
                        <span className="text-xs font-normal text-gray-500">({runs.length})</span>
                      </CardTitle>
                      {(compareA || compareB) && (
                        <button
                          onClick={() => { setCompareA(null); setCompareB(null); setCompareResult(null); }}
                          className="text-xs text-gray-500 hover:text-gray-800 inline-flex items-center gap-1"
                        >
                          <RotateCcw className="w-3 h-3" /> Clear compare
                        </button>
                      )}
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-2">
                    {runs.map((r) => (
                      <RunHistoryRow
                        key={r.id}
                        run={r}
                        isSelected={r.id === selectedRunId}
                        isCompareA={r.id === compareA}
                        isCompareB={r.id === compareB}
                        onSelect={(id) => setSelectedRunId(id === selectedRunId ? null : id)}
                        onToggleCompare={handleToggleCompare}
                      />
                    ))}
                  </CardContent>
                </Card>
              )}

              {compareResult && (
                <CompareDrawer
                  compare={compareResult}
                  onClose={() => { setCompareA(null); setCompareB(null); setCompareResult(null); }}
                />
              )}

              {selectedRun && <RunDetail run={selectedRun} />}
            </>
          )}
        </div>
      </div>
    </div>
  );
};

export default EvalSuites;
