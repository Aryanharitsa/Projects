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
  Shield,
  ShieldAlert,
  ShieldCheck,
  Bug,
  AlertTriangle,
  Plus,
  Trash2,
  Play,
  Beaker,
  RotateCcw,
  Sparkles,
  ChevronRight,
  ChevronDown,
  Crosshair,
  ArrowRight,
  ArrowUp,
  ArrowDown,
  Skull,
  Target,
  Layers,
  Activity,
  Search,
  Copy,
  Download,
  Lock,
  Unlock,
  Zap,
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
const fmtSigned = (n, d = 1) => {
  if (n == null || Number.isNaN(Number(n))) return "—";
  const v = Number(n);
  return `${v >= 0 ? "+" : ""}${v.toFixed(d)}`;
};
const fmtCost = (c) => {
  if (c == null) return "—";
  if (c === 0) return "$0";
  if (c < 0.001) return `$${(c * 1000).toFixed(3)}m`;
  return `$${Number(c).toFixed(4)}`;
};

// Robustness colour ramp — 0 (red) → 100 (green).
const robHue = (v) => {
  if (v == null || Number.isNaN(Number(v))) return "#94a3b8";
  const clipped = Math.max(0, Math.min(100, Number(v)));
  const hue = Math.round(clipped * 1.25); // 0→0 red, 100→125 emerald
  return `hsl(${hue} 78% 48%)`;
};

const bandFor = (v) => {
  if (v == null) return { label: "—", hue: "#94a3b8" };
  if (v >= 80) return { label: "Hardened", hue: "#22c55e" };
  if (v >= 60) return { label: "Solid", hue: "#84cc16" };
  if (v >= 40) return { label: "Brittle", hue: "#f59e0b" };
  return { label: "Fragile", hue: "#ef4444" };
};

// Category palette — must mirror backend `CATEGORY_HUES`.
const CAT = {
  typographic: { hue: "#06b6d4", label: "Typographic", glyph: "Aa" },
  structural:  { hue: "#a855f7", label: "Structural",  glyph: "§" },
  distractor:  { hue: "#f59e0b", label: "Distractor",  glyph: "…" },
  injection:   { hue: "#ef4444", label: "Injection",   glyph: "⚠" },
  baseline:    { hue: "#94a3b8", label: "Baseline",    glyph: "○" },
};

// Delta colour for a given category — negative is bad except for the
// degradation category where any drop matters.
const deltaHue = (delta) => {
  if (delta == null) return "#94a3b8";
  const v = Number(delta);
  if (v >= 1) return "#22c55e";
  if (v >= -1) return "#cbd5e1";
  if (v >= -5) return "#f59e0b";
  if (v >= -15) return "#fb923c";
  return "#ef4444";
};

// ─── Visual primitives ─────────────────────────────────────────────────────

const RobustnessRing = ({ value, size = 168, band }) => {
  const has = value != null && !Number.isNaN(Number(value));
  const v = has ? Math.max(0, Math.min(100, Number(value))) : 0;
  const hue = has ? robHue(v) : "#475569";
  const inner = size - 14;
  return (
    <div
      className="relative grid place-items-center shrink-0"
      style={{
        width: size,
        height: size,
        borderRadius: "50%",
        background: `conic-gradient(${hue} ${v * 3.6}deg, rgba(148,163,184,0.16) ${v * 3.6}deg 360deg)`,
        boxShadow: has ? `0 0 ${size / 3}px ${hue}33` : "none",
      }}
    >
      <div
        className="grid place-items-center bg-slate-950 border border-slate-800/60"
        style={{
          width: inner,
          height: inner,
          borderRadius: "50%",
        }}
      >
        <div className="flex flex-col items-center leading-none">
          <span className="text-[12px] text-slate-500 uppercase tracking-[0.3em] mb-1">
            Robust
          </span>
          <span className="text-[44px] font-bold tracking-tight" style={{ color: has ? hue : "#94a3b8" }}>
            {has ? Math.round(v) : "—"}
          </span>
          {band ? (
            <span
              className="text-[11px] mt-1.5 px-2 py-0.5 rounded-full font-medium uppercase tracking-widest"
              style={{
                color: hue,
                background: `${hue}1a`,
                border: `1px solid ${hue}55`,
              }}
            >
              {band}
            </span>
          ) : null}
        </div>
      </div>
    </div>
  );
};

const MiniRing = ({ value, size = 48 }) => {
  const has = value != null;
  const v = has ? Math.max(0, Math.min(100, Number(value))) : 0;
  const hue = has ? robHue(v) : "#475569";
  const inner = size - 6;
  return (
    <div
      className="relative grid place-items-center shrink-0"
      style={{
        width: size,
        height: size,
        borderRadius: "50%",
        background: `conic-gradient(${hue} ${v * 3.6}deg, rgba(148,163,184,0.18) ${v * 3.6}deg 360deg)`,
      }}
    >
      <div
        className="grid place-items-center bg-slate-950"
        style={{
          width: inner,
          height: inner,
          borderRadius: "50%",
        }}
      >
        <span className="text-[12px] font-bold" style={{ color: has ? hue : "#94a3b8" }}>
          {has ? Math.round(v) : "—"}
        </span>
      </div>
    </div>
  );
};

const CategoryChip = ({ category, small = false }) => {
  const meta = CAT[category] || CAT.baseline;
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full font-medium border ${
        small ? "px-1.5 py-0.5 text-[10px]" : "px-2 py-0.5 text-[11px]"
      }`}
      style={{
        color: meta.hue,
        borderColor: `${meta.hue}55`,
        background: `${meta.hue}1a`,
      }}
    >
      <span
        className="inline-grid place-items-center font-bold"
        style={{
          width: small ? 11 : 14,
          height: small ? 11 : 14,
          borderRadius: "50%",
          background: meta.hue,
          color: "#0f172a",
          fontSize: small ? 8 : 9,
          lineHeight: 1,
        }}
      >
        {meta.glyph}
      </span>
      {meta.label}
    </span>
  );
};

// Centered bipolar delta bar — negative on left, positive on right.
const DeltaBar = ({ value, max = 60, height = 8, showLabel = true }) => {
  if (value == null) {
    return (
      <div className="flex items-center gap-2">
        <div className="flex-1 rounded-full bg-slate-800/80" style={{ height }} />
        <span className="text-[11px] text-slate-500 w-10 text-right">—</span>
      </div>
    );
  }
  const v = Math.max(-max, Math.min(max, Number(value)));
  const pct = Math.abs(v) / max;
  const hue = deltaHue(v);
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 relative rounded-full bg-slate-800/80 overflow-hidden" style={{ height }}>
        {/* Zero line */}
        <div
          className="absolute top-0 bottom-0 w-px bg-slate-600/70"
          style={{ left: "50%" }}
        />
        <div
          className="absolute top-0 bottom-0 rounded-full"
          style={{
            ...(v < 0
              ? { right: "50%", width: `${pct * 50}%` }
              : { left: "50%", width: `${pct * 50}%` }),
            background: hue,
            boxShadow: `0 0 6px ${hue}66`,
          }}
        />
      </div>
      {showLabel ? (
        <span className="text-[11px] font-mono w-12 text-right" style={{ color: hue }}>
          {fmtSigned(v)}
        </span>
      ) : null}
    </div>
  );
};

// ─── Empty / error states ──────────────────────────────────────────────────

const EmptyState = ({ icon, title, body, action }) => {
  const IconCmp = icon;
  return (
    <div className="rounded-2xl border border-slate-800/80 bg-gradient-to-br from-slate-950 via-slate-900/60 to-slate-950 py-16 px-8 text-center">
      <div className="inline-flex w-14 h-14 rounded-full items-center justify-center bg-slate-800/60 mb-4">
        <IconCmp className="w-7 h-7 text-slate-400" />
      </div>
      <h3 className="text-lg font-semibold text-slate-200">{title}</h3>
      <p className="mt-1 text-sm text-slate-400 max-w-md mx-auto">{body}</p>
      {action ? <div className="mt-5">{action}</div> : null}
    </div>
  );
};

// ─── Setup tab ─────────────────────────────────────────────────────────────

const SetupTab = ({
  perturbations,
  rubrics,
  onCreate,
  onSeed,
  creating,
  setCreating,
}) => {
  const [name, setName] = useState("My prompt — robustness audit");
  const [description, setDescription] = useState("");
  const [basePrompt, setBasePrompt] = useState(
    "You are a calm, concise customer support specialist for a small SaaS " +
    "company. Read the user's message, identify the issue, and reply with a " +
    "two-sentence answer followed by the next step they should take."
  );
  const [cases, setCases] = useState([
    { input: "I was double charged last month — can you refund?", expected: "Apology + refund offer + next step (confirmation reply)." },
    { input: "The app keeps crashing on iPhone every time I open the dashboard.", expected: "Apology + diagnostic ask (build / reinstall) as next step." },
    { input: "Is the EU enterprise plan GDPR compliant?", expected: "Yes-with-caveats answer + offer to send DPA link as next step." },
  ]);
  const [rubricId, setRubricId] = useState("");
  const [picked, setPicked] = useState(() => new Set(perturbations.map((p) => p.kind)));
  const [dryrun, setDryrun] = useState(true);
  const [previewKind, setPreviewKind] = useState(perturbations[0]?.kind || "");
  const [previewData, setPreviewData] = useState(null);

  // Reset picked set if catalog re-arrived.
  useEffect(() => {
    setPicked(new Set(perturbations.map((p) => p.kind)));
    if (perturbations.length && !previewKind) setPreviewKind(perturbations[0].kind);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [perturbations]);

  // Live preview of every perturbation as the user types.
  const debouncedRef = useRef(null);
  const firstCaseInput = cases[0]?.input || "";
  useEffect(() => {
    if (debouncedRef.current) clearTimeout(debouncedRef.current);
    if (!basePrompt.trim()) return;
    debouncedRef.current = setTimeout(async () => {
      try {
        const res = await ApiService.adversaryPreview({
          base_prompt: basePrompt,
          sample_input: firstCaseInput || "Help me, please.",
        });
        setPreviewData(res.previews || []);
      } catch {
        // Silent — preview is best-effort.
      }
    }, 320);
    return () => debouncedRef.current && clearTimeout(debouncedRef.current);
  }, [basePrompt, firstCaseInput]);

  const togglePerturb = (kind) => {
    setPicked((prev) => {
      const n = new Set(prev);
      if (n.has(kind)) n.delete(kind);
      else n.add(kind);
      return n;
    });
  };
  const toggleCategory = (cat) => {
    const kinds = perturbations.filter((p) => p.category === cat).map((p) => p.kind);
    const allOn = kinds.every((k) => picked.has(k));
    setPicked((prev) => {
      const n = new Set(prev);
      kinds.forEach((k) => (allOn ? n.delete(k) : n.add(k)));
      return n;
    });
  };

  const updateCase = (i, patch) => setCases((prev) => prev.map((c, idx) => (idx === i ? { ...c, ...patch } : c)));
  const removeCase = (i) => setCases((prev) => prev.filter((_, idx) => idx !== i));
  const addCase = () => setCases((prev) => [...prev, { input: "", expected: "" }]);

  const submit = async () => {
    const trimName = name.trim();
    const trimPrompt = basePrompt.trim();
    if (!trimName) return toast.error("Name is required");
    if (!trimPrompt) return toast.error("Base prompt is required");
    const tc = cases.filter((c) => (c.input || "").trim());
    if (!tc.length) return toast.error("At least one non-empty test case is required");
    if (!picked.size) return toast.error("Pick at least one perturbation");
    setCreating(true);
    try {
      const res = await ApiService.createAudit({
        name: trimName,
        description,
        base_prompt: trimPrompt,
        test_cases: tc,
        perturbations: Array.from(picked),
        rubric_id: rubricId || "",
        dryrun,
      });
      onCreate(res.audit);
    } catch (e) {
      toast.error(`Create failed: ${e.message}`);
    } finally {
      setCreating(false);
    }
  };

  // Group perturbations by category for the picker.
  const byCat = useMemo(() => {
    const m = {};
    perturbations.forEach((p) => {
      if (!m[p.category]) m[p.category] = [];
      m[p.category].push(p);
    });
    return m;
  }, [perturbations]);

  const currentPreview = (previewData || []).find((p) => p.kind === previewKind);

  return (
    <div className="space-y-6">
      <Card className="border-slate-800/80 bg-slate-950/60 overflow-hidden">
        <CardHeader className="pb-3 border-b border-slate-800/60 bg-gradient-to-r from-slate-950 via-slate-900/30 to-slate-950">
          <CardTitle className="text-base text-slate-200 flex items-center gap-2">
            <ShieldCheck className="w-4 h-4 text-emerald-400" />
            New robustness audit
          </CardTitle>
        </CardHeader>
        <CardContent className="pt-5 space-y-5">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <Label className="text-slate-400 text-xs uppercase tracking-widest">Audit name</Label>
              <Input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. v3 support prompt — robustness"
                className="bg-slate-900/60 border-slate-800 text-slate-100 mt-1"
              />
            </div>
            <div>
              <Label className="text-slate-400 text-xs uppercase tracking-widest">Description (optional)</Label>
              <Input
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="What are you trying to confirm?"
                className="bg-slate-900/60 border-slate-800 text-slate-100 mt-1"
              />
            </div>
          </div>

          <div>
            <Label className="text-slate-400 text-xs uppercase tracking-widest">Base prompt</Label>
            <Textarea
              value={basePrompt}
              onChange={(e) => setBasePrompt(e.target.value)}
              placeholder="The system / instruction you ship to production…"
              className="bg-slate-900/60 border-slate-800 text-slate-100 min-h-[120px] mt-1 font-mono text-[13px] leading-relaxed"
            />
          </div>

          <div>
            <div className="flex items-center justify-between mb-2">
              <Label className="text-slate-400 text-xs uppercase tracking-widest">
                Test cases <span className="text-slate-500 normal-case lowercase">— {cases.length}</span>
              </Label>
              <Button
                size="sm"
                variant="ghost"
                onClick={addCase}
                className="text-slate-300 hover:text-white hover:bg-slate-800 h-7"
              >
                <Plus className="w-3.5 h-3.5 mr-1" /> Add case
              </Button>
            </div>
            <div className="space-y-3">
              {cases.map((c, i) => (
                <div
                  key={i}
                  className="grid grid-cols-1 md:grid-cols-2 gap-2 p-3 rounded-lg border border-slate-800/60 bg-slate-900/40"
                >
                  <Textarea
                    value={c.input}
                    onChange={(e) => updateCase(i, { input: e.target.value })}
                    placeholder="Input the model will see"
                    className="bg-slate-950/60 border-slate-800 text-slate-100 min-h-[64px] text-[13px] leading-relaxed"
                  />
                  <div className="flex gap-2">
                    <Textarea
                      value={c.expected}
                      onChange={(e) => updateCase(i, { expected: e.target.value })}
                      placeholder="What a good answer looks like (optional)"
                      className="bg-slate-950/60 border-slate-800 text-slate-100 min-h-[64px] text-[13px] leading-relaxed flex-1"
                    />
                    <button
                      onClick={() => removeCase(i)}
                      className="self-start text-slate-500 hover:text-rose-400 p-1.5 rounded hover:bg-slate-800/60"
                      title="Remove case"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <Label className="text-slate-400 text-xs uppercase tracking-widest">
                Rubric <span className="text-slate-500 normal-case lowercase">— optional, dry-run will use a default</span>
              </Label>
              <Select value={rubricId || "__none"} onValueChange={(v) => setRubricId(v === "__none" ? "" : v)}>
                <SelectTrigger className="bg-slate-900/60 border-slate-800 text-slate-100 mt-1">
                  <SelectValue placeholder="No rubric — heuristic scoring" />
                </SelectTrigger>
                <SelectContent className="bg-slate-900 border-slate-800 text-slate-100">
                  <SelectItem value="__none">No rubric — heuristic scoring</SelectItem>
                  {rubrics.map((r) => (
                    <SelectItem key={r.id} value={r.id}>
                      {r.name}
                      {r.n_dimensions ? ` · ${r.n_dimensions} dims` : ""}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="flex items-end gap-3">
              <div className="flex-1">
                <Label className="text-slate-400 text-xs uppercase tracking-widest">Mode</Label>
                <div
                  onClick={() => setDryrun((v) => !v)}
                  className="mt-1 flex items-center gap-2 px-3 py-2 rounded-md border border-slate-800 bg-slate-900/60 cursor-pointer hover:border-slate-700 transition-colors"
                >
                  <Switch checked={dryrun} onCheckedChange={setDryrun} />
                  <div className="text-sm text-slate-200">
                    {dryrun ? "Dry-run — instant, no API keys" : "Live — real model + real judge"}
                  </div>
                </div>
              </div>
            </div>
            <div className="flex items-end justify-end gap-2">
              <Button
                variant="ghost"
                onClick={onSeed}
                className="border border-slate-800 text-slate-300 hover:bg-slate-800/60"
                title="Seed a 'Customer support' demo audit so you can see the UI populated"
              >
                <Sparkles className="w-4 h-4 mr-1.5" /> Seed demo
              </Button>
              <Button
                onClick={submit}
                disabled={creating}
                className="bg-gradient-to-r from-emerald-500 to-cyan-500 text-slate-950 hover:opacity-90 font-medium"
              >
                <Play className="w-4 h-4 mr-1.5" /> Create audit
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card className="border-slate-800/80 bg-slate-950/60 overflow-hidden">
        <CardHeader className="pb-3 border-b border-slate-800/60">
          <div className="flex items-center justify-between flex-wrap gap-2">
            <CardTitle className="text-base text-slate-200 flex items-center gap-2">
              <Crosshair className="w-4 h-4 text-fuchsia-400" />
              Perturbation catalogue
            </CardTitle>
            <div className="flex items-center gap-2 text-xs">
              <span className="text-slate-500">
                {picked.size} / {perturbations.length} selected
              </span>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => setPicked(new Set(perturbations.map((p) => p.kind)))}
                className="h-7 text-slate-300 hover:text-white hover:bg-slate-800"
              >
                Select all
              </Button>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => setPicked(new Set())}
                className="h-7 text-slate-300 hover:text-white hover:bg-slate-800"
              >
                Clear
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent className="pt-5 space-y-5">
          {Object.entries(byCat).map(([cat, list]) => {
            const meta = CAT[cat] || CAT.baseline;
            const allOn = list.every((p) => picked.has(p.kind));
            return (
              <div key={cat}>
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <span
                      className="inline-grid place-items-center font-bold rounded-md"
                      style={{
                        width: 22,
                        height: 22,
                        background: meta.hue,
                        color: "#0f172a",
                        fontSize: 11,
                      }}
                    >
                      {meta.glyph}
                    </span>
                    <h4 className="text-sm font-semibold text-slate-200">
                      {meta.label}
                    </h4>
                    <span className="text-xs text-slate-500">
                      {list.filter((p) => picked.has(p.kind)).length} / {list.length} on
                    </span>
                  </div>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => toggleCategory(cat)}
                    className="h-7 text-slate-300 hover:text-white hover:bg-slate-800"
                  >
                    {allOn ? "Disable all" : "Enable all"}
                  </Button>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                  {list.map((p) => {
                    const on = picked.has(p.kind);
                    return (
                      <div
                        key={p.kind}
                        onClick={() => {
                          togglePerturb(p.kind);
                          setPreviewKind(p.kind);
                        }}
                        className={`group cursor-pointer p-3 rounded-lg border transition-all ${
                          on
                            ? "border-slate-700 bg-slate-900/60"
                            : "border-slate-800/40 bg-slate-950/40 opacity-60 hover:opacity-100"
                        }`}
                        style={on ? { borderColor: `${meta.hue}55`, boxShadow: `0 0 0 1px ${meta.hue}22` } : undefined}
                      >
                        <div className="flex items-start justify-between gap-2">
                          <div className="flex items-center gap-2">
                            <div
                              className="w-2 h-2 rounded-full"
                              style={{ background: on ? meta.hue : "#475569" }}
                            />
                            <span className="text-[13px] font-medium text-slate-100">
                              {p.label}
                            </span>
                          </div>
                          <span
                            className="text-[10px] uppercase tracking-widest font-mono"
                            style={{ color: on ? meta.hue : "#64748b" }}
                          >
                            sev {Math.round((p.severity || 0) * 100)}
                          </span>
                        </div>
                        <p className="mt-1 text-[12px] text-slate-400 leading-relaxed">
                          {p.blurb}
                        </p>
                      </div>
                    );
                  })}
                </div>
              </div>
            );
          })}

          {currentPreview && (
            <div className="rounded-xl border border-slate-800/60 bg-slate-900/40 p-4">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2 text-xs uppercase tracking-widest text-slate-400">
                  <Search className="w-3.5 h-3.5" /> Live preview
                </div>
                <Select value={previewKind} onValueChange={setPreviewKind}>
                  <SelectTrigger className="w-64 bg-slate-950/60 border-slate-800 text-slate-100 h-8 text-[13px]">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent className="bg-slate-900 border-slate-800 text-slate-100">
                    {perturbations.map((p) => (
                      <SelectItem key={p.kind} value={p.kind}>
                        {CAT[p.category]?.label || p.category} · {p.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-[12.5px] leading-relaxed">
                <div>
                  <div className="text-[10px] uppercase tracking-widest text-slate-500 mb-1">
                    Perturbed prompt
                    <span className="ml-2 text-slate-600 normal-case">
                      Δ {currentPreview.delta_chars_prompt >= 0 ? "+" : ""}
                      {currentPreview.delta_chars_prompt} chars
                    </span>
                  </div>
                  <pre className="font-mono text-[12px] text-slate-300 whitespace-pre-wrap bg-slate-950/60 border border-slate-800 rounded p-2 max-h-44 overflow-auto">
                    {currentPreview.prompt}
                  </pre>
                </div>
                <div>
                  <div className="text-[10px] uppercase tracking-widest text-slate-500 mb-1">
                    Perturbed input
                    {currentPreview.injection_marker ? (
                      <span className="ml-2 text-rose-400 normal-case">
                        marker: <span className="font-mono">{currentPreview.injection_marker}</span>
                      </span>
                    ) : (
                      <span className="ml-2 text-slate-600 normal-case">
                        Δ {currentPreview.delta_chars_input >= 0 ? "+" : ""}
                        {currentPreview.delta_chars_input} chars
                      </span>
                    )}
                  </div>
                  <pre className="font-mono text-[12px] text-slate-300 whitespace-pre-wrap bg-slate-950/60 border border-slate-800 rounded p-2 max-h-44 overflow-auto">
                    {currentPreview.input || "—"}
                  </pre>
                </div>
              </div>
              <div className="mt-2 text-[11px] text-slate-500 italic">
                {currentPreview.note}
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

// ─── Results — overview ─────────────────────────────────────────────────────

const ResultsOverview = ({ audit, onRerun, onDelete, running, deleting }) => {
  const summary = useMemo(() => audit.summary || {}, [audit]);
  const band = bandFor(audit.robustness_score);
  const cleanComp = audit.clean_composite;
  const vulns = useMemo(() => summary.vulnerabilities || [], [summary]);
  const cats = useMemo(() => summary.by_category || [], [summary]);
  const dimImpact = summary.dim_impact || [];

  const nonInjRuns = (audit.runs || []).filter((r) => !r.is_baseline && r.category !== "injection");
  const injRuns = (audit.runs || []).filter((r) => r.category === "injection");
  const ranOK = (audit.runs || []).filter((r) => r.status === "complete").length;

  // Sort non-injection runs by delta ascending (worst first).
  const sortedNonInj = useMemo(
    () => [...nonInjRuns].sort((a, b) => (a.delta ?? 0) - (b.delta ?? 0)),
    [nonInjRuns]
  );

  const exportMarkdown = useCallback(() => {
    const lines = [
      `# ${audit.name} — Adversary Lab digest`,
      "",
      `> ${summary.headline || ""}`,
      "",
      `- Clean composite: **${fmtNum(cleanComp, 1)}**`,
      `- Robustness: **${fmtNum(audit.robustness_score, 1)}** · ${audit.band || band.label}`,
      `- Safety: ${fmtNum(summary.safety_score, 1)} · Degradation: ${fmtNum(summary.degradation_score, 1)}`,
      `- Injections succeeded: ${summary.injection_success_count}/${summary.injection_count}`,
      `- Vulnerabilities: ${vulns.length}`,
      "",
      "## By category",
      "| Category | n | Mean Δ | Worst Δ |",
      "|---|---:|---:|---:|",
      ...cats.map(
        (c) =>
          `| ${c.label} | ${c.n} | ${fmtSigned(c.mean_delta)} | ${fmtSigned(c.worst_delta)} |`
      ),
      "",
      "## Vulnerabilities",
      ...vulns.map((v) => `- **${v.kind}** (${v.category}): ${v.reason}`),
    ];
    const blob = new Blob([lines.join("\n")], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `adversary-${audit.id.slice(0, 8)}.md`;
    a.click();
    URL.revokeObjectURL(url);
  }, [audit, summary, cleanComp, band, vulns, cats]);

  return (
    <div className="space-y-5">
      {/* Hero */}
      <div
        className="rounded-2xl border border-slate-800/80 p-6 relative overflow-hidden"
        style={{
          background:
            "radial-gradient(ellipse at top right, rgba(34,197,94,0.10), transparent 55%), " +
            "linear-gradient(180deg, #0c1424, #050816)",
        }}
      >
        <div className="flex flex-wrap gap-6 items-center">
          <RobustnessRing value={audit.robustness_score} band={audit.band || band.label} />
          <div className="flex-1 min-w-[260px]">
            <div className="text-xs uppercase tracking-[0.3em] text-slate-500 mb-1">
              {audit.dryrun ? "Dry-run audit" : "Live audit"}
            </div>
            <h2 className="text-xl md:text-2xl font-semibold text-slate-100">
              {audit.name}
            </h2>
            <p className="mt-2 text-sm text-slate-300 leading-relaxed">
              {summary.headline || "—"}
            </p>
            <div className="mt-4 grid grid-cols-2 md:grid-cols-4 gap-3">
              <Tile
                label="Clean composite"
                value={fmtNum(cleanComp, 1)}
                hue="#64748b"
              />
              <Tile
                label="Degradation"
                value={fmtNum(summary.degradation_score, 0)}
                hue={robHue(summary.degradation_score)}
                suffix=" / 100"
              />
              <Tile
                label="Safety"
                value={fmtNum(summary.safety_score, 0)}
                hue={robHue(summary.safety_score)}
                suffix=" / 100"
              />
              <Tile
                label="Vulnerabilities"
                value={vulns.length}
                hue={vulns.length === 0 ? "#22c55e" : vulns.length <= 2 ? "#f59e0b" : "#ef4444"}
              />
            </div>
          </div>
          <div className="flex flex-col gap-2 ml-auto">
            <Button
              size="sm"
              onClick={onRerun}
              disabled={running}
              className="bg-gradient-to-r from-emerald-500 to-cyan-500 text-slate-950 hover:opacity-90"
            >
              <RotateCcw className="w-3.5 h-3.5 mr-1.5" />
              {running ? "Running…" : "Re-run audit"}
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={exportMarkdown}
              className="border border-slate-800 text-slate-300 hover:bg-slate-800/60"
            >
              <Download className="w-3.5 h-3.5 mr-1.5" /> Markdown digest
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={onDelete}
              disabled={deleting}
              className="border border-rose-900/40 text-rose-300 hover:bg-rose-950/40 hover:text-rose-200"
            >
              <Trash2 className="w-3.5 h-3.5 mr-1.5" /> Delete
            </Button>
          </div>
        </div>
        <div className="mt-5 flex items-center gap-2 text-[11px] text-slate-500">
          <Activity className="w-3 h-3" />
          <span>
            {ranOK}/{(audit.runs || []).length} runs completed · duration{" "}
            {fmtNum(summary.duration, 2)}s · cost {fmtCost(summary.total_cost)} ·
            updated {fmtRel(audit.updated_at)}
          </span>
        </div>
      </div>

      {/* Category strip */}
      <Card className="border-slate-800/80 bg-slate-950/60">
        <CardHeader className="pb-3">
          <CardTitle className="text-sm text-slate-200 flex items-center gap-2">
            <Layers className="w-4 h-4 text-cyan-400" />
            By perturbation family
          </CardTitle>
        </CardHeader>
        <CardContent className="pt-0">
          <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
            {cats.map((c) => {
              const hue = c.hue;
              return (
                <div
                  key={c.category}
                  className="relative rounded-xl border border-slate-800/60 bg-slate-900/40 p-4 overflow-hidden"
                  style={{ boxShadow: `inset 0 0 0 1px ${hue}22` }}
                >
                  <div
                    className="absolute top-0 left-0 right-0 h-0.5"
                    style={{ background: hue }}
                  />
                  <div className="flex items-center justify-between">
                    <CategoryChip category={c.category} small />
                    <span className="text-[10px] text-slate-500 uppercase tracking-widest">
                      n={c.n}
                    </span>
                  </div>
                  <div className="mt-3 flex items-baseline gap-1.5">
                    <span
                      className="text-2xl font-semibold tabular-nums"
                      style={{ color: deltaHue(c.mean_delta) }}
                    >
                      {fmtSigned(c.mean_delta)}
                    </span>
                    <span className="text-[11px] text-slate-500">mean Δ</span>
                  </div>
                  <div className="mt-1 text-[11px] text-slate-400">
                    worst Δ{" "}
                    <span style={{ color: deltaHue(c.worst_delta) }} className="tabular-nums">
                      {fmtSigned(c.worst_delta)}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>

      {/* Vulnerabilities */}
      <Card className="border-slate-800/80 bg-slate-950/60">
        <CardHeader className="pb-3 border-b border-slate-800/60">
          <CardTitle className="text-sm text-slate-200 flex items-center gap-2">
            <Bug className="w-4 h-4 text-rose-400" />
            Vulnerabilities to address
            <span className="text-slate-500 font-normal text-xs">
              — perturbations that dropped composite ≥ 15 pts or injected the marker
            </span>
          </CardTitle>
        </CardHeader>
        <CardContent className="pt-4">
          {vulns.length === 0 ? (
            <div className="text-center py-6 text-sm text-slate-400">
              <ShieldCheck className="w-8 h-8 mx-auto mb-2 text-emerald-400 opacity-70" />
              No vulnerabilities detected. The prompt held up across every
              probe — good calibration.
            </div>
          ) : (
            <ul className="space-y-2">
              {vulns.map((v) => {
                const meta = CAT[v.category] || CAT.baseline;
                return (
                  <li
                    key={v.kind}
                    className="flex items-start gap-3 p-3 rounded-lg border border-slate-800/60 bg-slate-900/40"
                    style={{ boxShadow: `inset 3px 0 0 ${meta.hue}` }}
                  >
                    {v.n_injected ? (
                      <Skull className="w-4 h-4 text-rose-400 mt-0.5 shrink-0" />
                    ) : (
                      <AlertTriangle className="w-4 h-4 text-amber-400 mt-0.5 shrink-0" />
                    )}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-[13px] font-semibold text-slate-100">
                          {v.kind.replace(/_/g, " ")}
                        </span>
                        <CategoryChip category={v.category} small />
                      </div>
                      <p className="mt-1 text-[12px] text-slate-300">
                        {v.reason}
                      </p>
                    </div>
                    {v.delta != null && (
                      <span
                        className="text-[13px] font-mono tabular-nums shrink-0"
                        style={{ color: deltaHue(v.delta) }}
                      >
                        {fmtSigned(v.delta)} pts
                      </span>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </CardContent>
      </Card>

      {/* Per-perturbation bars */}
      <Card className="border-slate-800/80 bg-slate-950/60">
        <CardHeader className="pb-3 border-b border-slate-800/60">
          <CardTitle className="text-sm text-slate-200 flex items-center gap-2">
            <Target className="w-4 h-4 text-fuchsia-400" />
            Per-perturbation impact
            <span className="text-slate-500 font-normal text-xs">— Δ composite vs clean baseline, worst first</span>
          </CardTitle>
        </CardHeader>
        <CardContent className="pt-4 space-y-1.5">
          {sortedNonInj.map((r) => (
            <PerturbationRow key={r.id} row={r} />
          ))}
          {injRuns.length > 0 && (
            <div className="pt-3 mt-3 border-t border-slate-800/60">
              <div className="text-[10px] uppercase tracking-widest text-slate-500 mb-2">
                Injection vectors
              </div>
              {injRuns.map((r) => (
                <PerturbationRow key={r.id} row={r} />
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Per-dimension impact */}
      <Card className="border-slate-800/80 bg-slate-950/60">
        <CardHeader className="pb-3 border-b border-slate-800/60">
          <CardTitle className="text-sm text-slate-200 flex items-center gap-2">
            <Activity className="w-4 h-4 text-violet-400" />
            Per-dimension impact
            <span className="text-slate-500 font-normal text-xs">— averaged 0..10 score delta across all probes</span>
          </CardTitle>
        </CardHeader>
        <CardContent className="pt-4">
          {dimImpact.length === 0 ? (
            <div className="text-sm text-slate-400 text-center py-6">
              No dimension breakdown — attach a rubric to surface this view.
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {dimImpact.map((d) => (
                <div
                  key={d.name}
                  className="rounded-lg border border-slate-800/60 bg-slate-900/40 p-3"
                >
                  <div className="flex items-center justify-between text-[12px] text-slate-300">
                    <span>{d.name}</span>
                    <span className="text-[10px] text-slate-500 uppercase tracking-widest">
                      weight {d.weight}%
                    </span>
                  </div>
                  <div className="mt-2">
                    <DeltaBar value={d.mean_delta} max={5} />
                  </div>
                  <div className="mt-1 text-[11px] text-slate-500">
                    worst{" "}
                    <span style={{ color: deltaHue(d.worst_delta) }}>
                      {fmtSigned(d.worst_delta)}
                    </span>{" "}
                    · n={d.n}
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

const Tile = ({ label, value, hue = "#cbd5e1", suffix = "" }) => (
  <div
    className="rounded-lg border border-slate-800/60 bg-slate-900/40 px-3 py-2"
    style={{ boxShadow: `inset 0 -2px 0 ${hue}40` }}
  >
    <div className="text-[10px] uppercase tracking-widest text-slate-500">{label}</div>
    <div className="mt-0.5 flex items-baseline gap-0.5">
      <span className="text-lg font-semibold tabular-nums" style={{ color: hue }}>
        {value}
      </span>
      {suffix ? (
        <span className="text-[11px] text-slate-500">{suffix}</span>
      ) : null}
    </div>
  </div>
);

const PerturbationRow = ({ row }) => {
  const [open, setOpen] = useState(false);
  const meta = CAT[row.category] || CAT.baseline;
  const failed = row.status === "failed";
  return (
    <div
      className="rounded-lg border border-slate-800/60 bg-slate-900/30"
      style={open ? { boxShadow: `0 0 0 1px ${meta.hue}55` } : undefined}
    >
      <div
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-3 px-3 py-2 cursor-pointer hover:bg-slate-900/60 rounded-lg"
      >
        {open ? (
          <ChevronDown className="w-3.5 h-3.5 text-slate-500" />
        ) : (
          <ChevronRight className="w-3.5 h-3.5 text-slate-500" />
        )}
        <CategoryChip category={row.category} small />
        <span className="text-[13px] text-slate-100 font-medium min-w-[160px]">
          {row.perturbation_kind.replace(/_/g, " ")}
        </span>
        <div className="flex-1">
          {failed ? (
            <div className="flex items-center gap-2 text-[11px] text-rose-400">
              <AlertTriangle className="w-3 h-3" />
              {row.error || "failed"}
            </div>
          ) : (
            <DeltaBar value={row.delta} max={60} />
          )}
        </div>
        {!failed && (
          <div className="text-[11px] text-slate-400 tabular-nums font-mono min-w-[58px] text-right">
            {fmtNum(row.composite, 1)}
          </div>
        )}
        {row.injection_marker ? (
          row.injection_success ? (
            <span className="inline-flex items-center gap-1 text-[10px] text-rose-300 bg-rose-950/40 border border-rose-900/40 px-1.5 py-0.5 rounded-full">
              <Skull className="w-3 h-3" /> leaked
            </span>
          ) : (
            <span className="inline-flex items-center gap-1 text-[10px] text-emerald-300 bg-emerald-950/30 border border-emerald-900/40 px-1.5 py-0.5 rounded-full">
              <ShieldCheck className="w-3 h-3" /> resisted
            </span>
          )
        ) : null}
      </div>
      {open && !failed && (
        <div className="border-t border-slate-800/60 px-3 py-3 space-y-3">
          <div className="text-[11px] text-slate-400 italic">{row.note}</div>
          {row.injection_marker ? (
            <div className="text-[11px] flex items-center gap-2">
              <Lock className="w-3 h-3 text-slate-500" />
              <span className="text-slate-500">Expected leak marker:</span>
              <code className="font-mono text-slate-300 bg-slate-950/80 px-1.5 py-0.5 rounded border border-slate-800">
                {row.injection_marker}
              </code>
              <span
                className={row.injection_success ? "text-rose-300" : "text-emerald-300"}
              >
                — {row.injection_success ? "present in response" : "not present"}
              </span>
            </div>
          ) : null}
          {Object.keys(row.dim_deltas || {}).length > 0 && (
            <div>
              <div className="text-[10px] uppercase tracking-widest text-slate-500 mb-1">
                Per-dimension Δ vs clean
              </div>
              <div className="grid grid-cols-2 gap-1.5">
                {Object.entries(row.dim_deltas).map(([k, v]) => (
                  <div key={k} className="flex items-center gap-2">
                    <span className="text-[11px] text-slate-300 w-28 truncate">{k}</span>
                    <div className="flex-1">
                      <DeltaBar value={v} max={5} height={6} />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
          <div>
            <div className="text-[10px] uppercase tracking-widest text-slate-500 mb-1">
              Perturbed prompt
            </div>
            <pre className="font-mono text-[11.5px] text-slate-300 whitespace-pre-wrap bg-slate-950/80 border border-slate-800 rounded p-2 max-h-40 overflow-auto">
              {row.prompt}
            </pre>
          </div>
          {(row.runs || []).length > 0 && (
            <div>
              <div className="text-[10px] uppercase tracking-widest text-slate-500 mb-1">
                Per-case
              </div>
              <div className="space-y-2">
                {row.runs.map((rr) => (
                  <div
                    key={rr.case_index}
                    className="rounded border border-slate-800/60 bg-slate-950/60 p-2"
                  >
                    <div className="flex items-center justify-between text-[11px]">
                      <span className="text-slate-400">Case #{rr.case_index + 1}</span>
                      <div className="flex items-center gap-2">
                        {rr.injected ? (
                          <span className="text-rose-300 text-[10px]">marker leaked</span>
                        ) : null}
                        <span
                          className="font-mono tabular-nums"
                          style={{ color: robHue(rr.composite) }}
                        >
                          {fmtNum(rr.composite, 1)}
                        </span>
                      </div>
                    </div>
                    <div className="mt-1 grid grid-cols-1 md:grid-cols-2 gap-2 text-[11px]">
                      <div>
                        <span className="text-slate-500">Input: </span>
                        <span className="text-slate-300 break-words">
                          {rr.input || "—"}
                        </span>
                      </div>
                      <div>
                        <span className="text-slate-500">Response: </span>
                        <span className="text-slate-300 break-words">
                          {rr.response || "—"}
                        </span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

// ─── Audits left rail ──────────────────────────────────────────────────────

const AuditRail = ({ audits, selectedId, onSelect, onNew, query, onQuery }) => (
  <div className="space-y-3">
    <div className="flex items-center gap-2">
      <div className="relative flex-1">
        <Search className="w-3.5 h-3.5 text-slate-500 absolute left-2.5 top-2.5" />
        <Input
          value={query}
          onChange={(e) => onQuery(e.target.value)}
          placeholder="Search audits"
          className="bg-slate-900/60 border-slate-800 text-slate-100 pl-8 h-8 text-[13px]"
        />
      </div>
      <Button
        size="sm"
        onClick={onNew}
        className="h-8 bg-slate-100 text-slate-900 hover:bg-white"
        title="New audit"
      >
        <Plus className="w-3.5 h-3.5" />
      </Button>
    </div>
    <ScrollArea className="h-[calc(100vh-280px)] min-h-[420px] pr-2">
      <ul className="space-y-2">
        {audits.map((a) => {
          const sel = a.id === selectedId;
          const band = bandFor(a.robustness_score);
          return (
            <li key={a.id}>
              <button
                onClick={() => onSelect(a.id)}
                className={`w-full text-left p-3 rounded-lg border transition-all ${
                  sel
                    ? "border-emerald-600/40 bg-emerald-950/20"
                    : "border-slate-800/60 bg-slate-900/40 hover:border-slate-700"
                }`}
                style={sel ? { boxShadow: `inset 3px 0 0 ${band.hue}` } : undefined}
              >
                <div className="flex items-start gap-3">
                  <MiniRing value={a.robustness_score} />
                  <div className="flex-1 min-w-0">
                    <div className="text-[13px] font-medium text-slate-100 truncate">
                      {a.name}
                    </div>
                    <div className="mt-0.5 flex items-center gap-1.5 text-[10px] uppercase tracking-widest">
                      <span style={{ color: band.hue }}>{a.band || band.label}</span>
                      <span className="text-slate-600">·</span>
                      <span className="text-slate-500">
                        {a.n_vulnerabilities} vuln
                      </span>
                      <span className="text-slate-600">·</span>
                      <span className="text-slate-500">{fmtRel(a.updated_at)}</span>
                    </div>
                    <div className="mt-1 flex items-center gap-1 flex-wrap">
                      {a.dryrun ? (
                        <Badge variant="outline" className="text-[9px] px-1 py-0 border-slate-700 text-slate-400">
                          dry-run
                        </Badge>
                      ) : (
                        <Badge variant="outline" className="text-[9px] px-1 py-0 border-emerald-700 text-emerald-300">
                          live
                        </Badge>
                      )}
                      {a.n_injections_ok > 0 && (
                        <Badge className="text-[9px] px-1 py-0 bg-rose-950/40 border border-rose-900/40 text-rose-300">
                          {a.n_injections_ok}/{a.n_injections} leaked
                        </Badge>
                      )}
                    </div>
                  </div>
                </div>
              </button>
            </li>
          );
        })}
        {audits.length === 0 && (
          <li className="text-center py-8 text-sm text-slate-500">
            No audits yet — hit Seed demo to start.
          </li>
        )}
      </ul>
    </ScrollArea>
  </div>
);

// ─── Top stats strip ───────────────────────────────────────────────────────

const StatsStrip = ({ stats }) => (
  <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
    <Tile label="Audits" value={stats?.n_audits ?? 0} hue="#22d3ee" />
    <Tile
      label="Avg robustness"
      value={stats?.avg_robustness != null ? fmtNum(stats.avg_robustness, 0) : "—"}
      hue={robHue(stats?.avg_robustness)}
    />
    <Tile
      label="Best robustness"
      value={stats?.best_robustness != null ? fmtNum(stats.best_robustness, 0) : "—"}
      hue={robHue(stats?.best_robustness)}
    />
    <Tile
      label="Vulns flagged"
      value={stats?.n_vulnerabilities ?? 0}
      hue={(stats?.n_vulnerabilities || 0) === 0 ? "#22c55e" : "#f59e0b"}
    />
    <Tile
      label="Injections leaked"
      value={stats?.n_injections_succeeded ?? 0}
      hue={(stats?.n_injections_succeeded || 0) === 0 ? "#22c55e" : "#ef4444"}
    />
  </div>
);

// ─── Main component ───────────────────────────────────────────────────────

const AdversaryLab = () => {
  const [audits, setAudits] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [perturbations, setPerturbations] = useState([]);
  const [rubrics, setRubrics] = useState([]);
  const [stats, setStats] = useState(null);
  const [audit, setAudit] = useState(null);
  const [, setLoading] = useState(false);
  const [running, setRunning] = useState(false);
  const [creating, setCreating] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [tab, setTab] = useState("setup"); // "setup" | "results"
  const [query, setQuery] = useState("");

  // Initial: load catalog + rubrics + audits + stats.
  const refresh = useCallback(async (preferAuditId = null) => {
    setLoading(true);
    try {
      const [catRes, rbRes, listRes, statsRes] = await Promise.all([
        ApiService.adversaryPerturbations(),
        ApiService.listRubrics({ limit: 50 }).catch(() => ({ rubrics: [] })),
        ApiService.listAudits({ q: query || undefined, limit: 50 }),
        ApiService.adversaryStats(),
      ]);
      setPerturbations(catRes.perturbations || []);
      setRubrics(rbRes.rubrics || []);
      setAudits(listRes.audits || []);
      setStats(statsRes.stats || null);
      const list = listRes.audits || [];
      const targetId =
        preferAuditId ||
        (selectedId && list.find((a) => a.id === selectedId)?.id) ||
        list[0]?.id ||
        null;
      if (targetId) {
        setSelectedId(targetId);
        const detail = await ApiService.getAudit(targetId);
        setAudit(detail.audit);
        setTab(detail.audit?.status === "complete" ? "results" : "setup");
      } else {
        setAudit(null);
        setTab("setup");
      }
    } catch (e) {
      toast.error(`Load failed: ${e.message}`);
    } finally {
      setLoading(false);
    }
  }, [query, selectedId]);

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!selectedId) {
      setAudit(null);
      return;
    }
    let cancelled = false;
    ApiService.getAudit(selectedId)
      .then((res) => {
        if (cancelled) return;
        setAudit(res.audit);
        setTab(res.audit?.status === "complete" ? "results" : "setup");
      })
      .catch((e) => toast.error(`Audit load failed: ${e.message}`));
    return () => {
      cancelled = true;
    };
  }, [selectedId]);

  // Refresh just the list on query change (debounced).
  const qRef = useRef(null);
  useEffect(() => {
    if (qRef.current) clearTimeout(qRef.current);
    qRef.current = setTimeout(async () => {
      try {
        const res = await ApiService.listAudits({ q: query || undefined, limit: 50 });
        setAudits(res.audits || []);
      } catch {
        // soft fail
      }
    }, 200);
    return () => qRef.current && clearTimeout(qRef.current);
  }, [query]);

  const onSeed = async () => {
    try {
      const res = await ApiService.seedAudit();
      const aid = res.audit?.id;
      toast.success("Seeded — running audit…");
      setSelectedId(aid);
      await ApiService.runAudit(aid, {});
      await refresh(aid);
      setTab("results");
    } catch (e) {
      toast.error(`Seed failed: ${e.message}`);
    }
  };

  const onCreate = async (newAudit) => {
    try {
      setSelectedId(newAudit.id);
      toast.success(`Created "${newAudit.name}" — running audit…`);
      setRunning(true);
      await ApiService.runAudit(newAudit.id, {
        confirm_live: !newAudit.dryrun,
      });
      await refresh(newAudit.id);
      setTab("results");
      toast.success("Audit complete");
    } catch (e) {
      toast.error(`Run failed: ${e.message}`);
    } finally {
      setRunning(false);
    }
  };

  const onRerun = async () => {
    if (!audit) return;
    setRunning(true);
    try {
      await ApiService.runAudit(audit.id, {
        confirm_live: !audit.dryrun,
      });
      const res = await ApiService.getAudit(audit.id);
      setAudit(res.audit);
      const list = await ApiService.listAudits({ q: query || undefined, limit: 50 });
      setAudits(list.audits || []);
      const st = await ApiService.adversaryStats();
      setStats(st.stats || null);
      toast.success("Re-run complete");
    } catch (e) {
      toast.error(`Re-run failed: ${e.message}`);
    } finally {
      setRunning(false);
    }
  };

  const onDelete = async () => {
    if (!audit) return;
    if (!window.confirm(`Delete audit "${audit.name}"? This cannot be undone.`)) return;
    setDeleting(true);
    try {
      await ApiService.deleteAudit(audit.id);
      toast.success("Deleted");
      setSelectedId(null);
      await refresh();
    } catch (e) {
      toast.error(`Delete failed: ${e.message}`);
    } finally {
      setDeleting(false);
    }
  };

  return (
    <div className="space-y-4 text-slate-100">
      {/* Header */}
      <div className="rounded-2xl border border-slate-800/80 px-5 py-4 relative overflow-hidden"
        style={{
          background:
            "radial-gradient(ellipse at top left, rgba(34,197,94,0.10), transparent 55%), " +
            "radial-gradient(ellipse at bottom right, rgba(239,68,68,0.10), transparent 55%), " +
            "linear-gradient(180deg, #0c1424, #060914)",
        }}
      >
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-emerald-500/30 to-rose-500/30 grid place-items-center border border-slate-800/60">
              <Shield className="w-5 h-5 text-slate-100" />
            </div>
            <div>
              <h1 className="text-xl font-semibold tracking-tight">
                Adversary Lab
                <span className="ml-2 text-[10px] uppercase tracking-[0.3em] bg-gradient-to-r from-emerald-500 via-cyan-500 to-rose-500 text-slate-950 px-1.5 py-0.5 rounded font-bold align-middle">
                  new
                </span>
              </h1>
              <p className="text-xs text-slate-400 max-w-2xl mt-0.5">
                Probe your prompt with 15 deterministic perturbations across
                typos, structure, distractors, and prompt-injection vectors.
                Surface the brittle ones before users do.
              </p>
            </div>
          </div>
          <StatsStrip stats={stats} />
        </div>
      </div>

      {/* Tabs + body */}
      <div className="grid grid-cols-1 lg:grid-cols-[320px_1fr] gap-4">
        <Card className="border-slate-800/80 bg-slate-950/60 p-3">
          <AuditRail
            audits={audits}
            selectedId={selectedId}
            onSelect={(id) => {
              setSelectedId(id);
              setTab("results");
            }}
            onNew={() => {
              setSelectedId(null);
              setAudit(null);
              setTab("setup");
            }}
            query={query}
            onQuery={setQuery}
          />
        </Card>

        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <button
              onClick={() => setTab("setup")}
              className={`px-3 py-1.5 rounded-lg text-[13px] font-medium border ${
                tab === "setup"
                  ? "bg-slate-100 text-slate-900 border-slate-100"
                  : "bg-slate-900/60 text-slate-300 border-slate-800 hover:border-slate-700"
              }`}
            >
              <Beaker className="w-3.5 h-3.5 inline mr-1.5" />
              Setup
            </button>
            <button
              onClick={() => setTab("results")}
              disabled={!audit || audit.status !== "complete"}
              className={`px-3 py-1.5 rounded-lg text-[13px] font-medium border ${
                tab === "results"
                  ? "bg-slate-100 text-slate-900 border-slate-100"
                  : "bg-slate-900/60 text-slate-300 border-slate-800 hover:border-slate-700 disabled:opacity-40 disabled:cursor-not-allowed"
              }`}
            >
              <Activity className="w-3.5 h-3.5 inline mr-1.5" />
              Results
              {audit?.robustness_score != null ? (
                <span
                  className="ml-1.5 text-[10px] px-1.5 py-0.5 rounded-full font-mono"
                  style={{
                    color: robHue(audit.robustness_score),
                    background: `${robHue(audit.robustness_score)}1a`,
                  }}
                >
                  {Math.round(audit.robustness_score)}
                </span>
              ) : null}
            </button>
            {running && (
              <div className="ml-auto flex items-center gap-2 text-[11px] text-emerald-300">
                <Zap className="w-3 h-3 animate-pulse" />
                running probes…
              </div>
            )}
          </div>

          {tab === "setup" ? (
            <SetupTab
              perturbations={perturbations}
              rubrics={rubrics}
              onCreate={onCreate}
              onSeed={onSeed}
              creating={creating}
              setCreating={setCreating}
            />
          ) : audit && audit.status === "complete" ? (
            <ResultsOverview
              audit={audit}
              onRerun={onRerun}
              onDelete={onDelete}
              running={running}
              deleting={deleting}
            />
          ) : audit && audit.status === "running" ? (
            <EmptyState
              icon={Zap}
              title="Running probes…"
              body="The audit is currently running. Results will appear here when it finishes."
            />
          ) : audit ? (
            <EmptyState
              icon={Play}
              title="Audit not yet run"
              body="Press Run to score the clean baseline + every selected perturbation."
              action={
                <Button
                  size="sm"
                  onClick={onRerun}
                  className="bg-gradient-to-r from-emerald-500 to-cyan-500 text-slate-950"
                >
                  <Play className="w-3.5 h-3.5 mr-1.5" /> Run audit
                </Button>
              }
            />
          ) : (
            <EmptyState
              icon={ShieldAlert}
              title="No audit selected"
              body="Pick one from the rail, or hit Seed demo on the Setup tab to see Adversary Lab populated with a sample customer-support audit."
            />
          )}
        </div>
      </div>
    </div>
  );
};

export default AdversaryLab;
