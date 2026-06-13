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
  Sparkles,
  Plus,
  Trash2,
  Play,
  Pause,
  Crown,
  Zap,
  ChevronRight,
  ChevronDown,
  ArrowUp,
  TrendingUp,
  TrendingDown,
  GitBranch,
  Microscope,
  Wand2,
  Beaker,
  Trophy,
  Layers,
  RotateCcw,
  Check,
  X,
  Lightbulb,
  Cpu,
  Activity,
  Award,
  Copy,
  Download,
  Search,
  AlertTriangle,
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

const fmtNum = (n, d = 0) => (n == null ? "—" : Number(n).toFixed(d));
const fmtCost = (c) => {
  if (c == null) return "—";
  if (c === 0) return "$0";
  if (c < 0.001) return `$${(c * 1000).toFixed(3)}m`;
  return `$${Number(c).toFixed(4)}`;
};

// ─── Visual primitives ──────────────────────────────────────────────────────

const scoreHue = (v) => {
  if (v == null || Number.isNaN(Number(v))) return "#cbd5e1";
  const clipped = Math.max(0, Math.min(100, Number(v)));
  const hue = Math.round(clipped * 1.25); // 0→0 (red), 100→125 (green)
  return `hsl(${hue} 78% 48%)`;
};

const MUTATION_HUE = {
  add_role: "#8b5cf6",
  step_by_step: "#06b6d4",
  add_constraints: "#f59e0b",
  few_shot: "#10b981",
  simplify: "#64748b",
  structure_sections: "#6366f1",
  safety_check: "#ec4899",
  negative_constraints: "#ef4444",
  anchor_guidance: "#a855f7",
  grounding: "#0ea5e9",
  one_shot_inverse: "#f97316",
  base: "#94a3b8",
};
const hueForMutation = (kind) => MUTATION_HUE[kind] || "#6366f1";

const ScoreRing = ({ value, size = 56, label = "" }) => {
  const has = value != null && !Number.isNaN(Number(value));
  const v = has ? Math.max(0, Math.min(100, Number(value))) : 0;
  const ringColor = has ? scoreHue(v) : "#cbd5e1";
  const innerSize = size - 8;
  return (
    <div
      className="relative grid place-items-center shrink-0"
      style={{
        width: size,
        height: size,
        borderRadius: "50%",
        background: `conic-gradient(${ringColor} ${v * 3.6}deg, rgba(148,163,184,0.18) ${v * 3.6}deg 360deg)`,
        boxShadow: has ? `0 0 ${Math.max(8, size / 4)}px ${ringColor}33` : "none",
      }}
    >
      <div
        className="grid place-items-center bg-slate-950"
        style={{
          width: innerSize,
          height: innerSize,
          borderRadius: "50%",
        }}
      >
        <div className="flex flex-col items-center leading-none">
          <span className="text-[15px] font-bold" style={{ color: has ? ringColor : "#94a3b8" }}>
            {has ? Math.round(v) : "—"}
          </span>
          {label ? (
            <span className="text-[8.5px] text-slate-400 mt-0.5 uppercase tracking-widest">
              {label}
            </span>
          ) : null}
        </div>
      </div>
    </div>
  );
};

const LiftPill = ({ base, best }) => {
  if (base == null || best == null) return null;
  const lift = Number(best) - Number(base);
  const up = lift >= 0;
  const Icon = up ? TrendingUp : TrendingDown;
  return (
    <span
      className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold border"
      style={{
        color: up ? "#22d3a8" : "#fb7185",
        borderColor: up ? "rgba(34, 211, 168, 0.4)" : "rgba(251, 113, 133, 0.4)",
        background: up ? "rgba(34, 211, 168, 0.10)" : "rgba(251, 113, 133, 0.10)",
      }}
    >
      <Icon className="w-3 h-3" />
      {up ? "+" : ""}
      {lift.toFixed(1)} pts
    </span>
  );
};

const MutationChip = ({ kind, label, small = false }) => {
  const hue = hueForMutation(kind);
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full font-medium border ${small ? "px-1.5 py-0.5 text-[10px]" : "px-2 py-0.5 text-[11px]"}`}
      style={{
        color: hue,
        borderColor: `${hue}55`,
        background: `${hue}1a`,
      }}
    >
      <span
        className="w-1.5 h-1.5 rounded-full"
        style={{ background: hue }}
      />
      {label || kind.replace(/_/g, " ")}
    </span>
  );
};

// Horizontal bar inside a card
const Bar = ({ value, max = 100, color, height = 6, label }) => {
  const pct = max ? Math.max(0, Math.min(100, (Number(value) / max) * 100)) : 0;
  return (
    <div>
      {label ? (
        <div className="flex items-center justify-between text-[10px] text-slate-400 mb-0.5 uppercase tracking-wider">
          <span>{label}</span>
          <span className="font-mono text-slate-300">{Number(value || 0).toFixed(1)}</span>
        </div>
      ) : null}
      <div className="w-full rounded-full overflow-hidden bg-slate-800/80" style={{ height }}>
        <div
          className="h-full rounded-full"
          style={{
            width: `${pct}%`,
            background: color || `linear-gradient(90deg, ${scoreHue(value)} 0%, ${scoreHue(Math.min(100, (value || 0) + 12))} 100%)`,
            transition: "width 280ms ease",
          }}
        />
      </div>
    </div>
  );
};

// ─── Lineage / evolution tree ──────────────────────────────────────────────
// Renders generations as columns; each variant is a card whose colour is the
// score band. SVG connectors run from a parent in the previous column to each
// child, with the stroke hue picking up the *child's* score so the eye is
// guided towards the winning branches.

const NODE_W = 200;
const NODE_H = 86;
const NODE_GAP_Y = 18;
const COL_GAP_X = 96;

function layoutGenerations(opt) {
  if (!opt) return { columns: [], links: [], width: 0, height: 0 };
  const variants = opt.variants || [];
  // Group by generation (0 = base).
  const byGen = new Map();
  variants.forEach((v) => {
    const g = Number(v.generation || 0);
    if (!byGen.has(g)) byGen.set(g, []);
    byGen.get(g).push(v);
  });
  const generations = Array.from(byGen.keys()).sort((a, b) => a - b);
  // Sort each column by score desc so winners float to the top.
  generations.forEach((g) => {
    byGen.get(g).sort((a, b) => (b.avg_composite ?? -1) - (a.avg_composite ?? -1));
  });

  const columns = generations.map((g, ci) => {
    const items = byGen.get(g) || [];
    return {
      generation: g,
      items: items.map((v, ri) => ({
        ...v,
        x: ci * (NODE_W + COL_GAP_X),
        y: ri * (NODE_H + NODE_GAP_Y),
      })),
    };
  });

  // Index variant → node for link resolution.
  const idIndex = new Map();
  columns.forEach((c) =>
    c.items.forEach((it) => idIndex.set(it.id, it))
  );

  const links = [];
  columns.forEach((c) => {
    c.items.forEach((it) => {
      const parent = it.parent_id ? idIndex.get(it.parent_id) : null;
      if (!parent) return;
      links.push({
        from: { x: parent.x + NODE_W, y: parent.y + NODE_H / 2 },
        to: { x: it.x, y: it.y + NODE_H / 2 },
        scoreHue: scoreHue(it.avg_composite),
        kind: it.mutation_kind,
      });
    });
  });

  const width = Math.max(1, columns.length) * (NODE_W + COL_GAP_X);
  const height = Math.max(
    NODE_H,
    ...columns.map((c) => Math.max(NODE_H, c.items.length * (NODE_H + NODE_GAP_Y)))
  );
  return { columns, links, width, height };
}

const LineageTree = ({ opt, selectedId, onSelect }) => {
  const { columns, links, width, height } = useMemo(() => layoutGenerations(opt), [opt]);
  const totalH = height + 60;
  if (!columns.length) {
    return (
      <div className="text-center py-12 text-sm text-slate-500">
        <GitBranch className="w-7 h-7 mx-auto mb-2 opacity-60" />
        No variants yet. Hit <strong>Run next generation</strong> to evolve.
      </div>
    );
  }
  return (
    <div className="overflow-auto rounded-2xl border border-slate-800/80 bg-gradient-to-br from-slate-950 via-slate-900/60 to-slate-950 p-5">
      <div
        className="relative"
        style={{ width: Math.max(width, 320), height: totalH, minWidth: "100%" }}
      >
        <svg
          width={width}
          height={totalH}
          style={{ position: "absolute", left: 0, top: 32, pointerEvents: "none" }}
        >
          <defs>
            {links.map((l, i) => (
              <linearGradient key={i} id={`gr-${i}`} x1="0" x2="1" y1="0" y2="0">
                <stop offset="0%" stopColor={hueForMutation(l.kind)} stopOpacity="0.5" />
                <stop offset="100%" stopColor={l.scoreHue} stopOpacity="0.95" />
              </linearGradient>
            ))}
          </defs>
          {links.map((l, i) => {
            const dx = (l.to.x - l.from.x) / 2;
            const path = `M ${l.from.x} ${l.from.y} C ${l.from.x + dx} ${l.from.y}, ${l.to.x - dx} ${l.to.y}, ${l.to.x} ${l.to.y}`;
            return (
              <path
                key={i}
                d={path}
                fill="none"
                stroke={`url(#gr-${i})`}
                strokeWidth={2.2}
                opacity={0.85}
              />
            );
          })}
        </svg>

        {/* Column headers */}
        <div className="absolute top-0 left-0 right-0 flex" style={{ height: 28 }}>
          {columns.map((c, i) => (
            <div
              key={c.generation}
              className="shrink-0 text-[11px] uppercase tracking-widest text-slate-400"
              style={{
                width: NODE_W,
                marginRight: i === columns.length - 1 ? 0 : COL_GAP_X,
                textAlign: "center",
              }}
            >
              {c.generation === 0 ? "Base" : `Gen ${c.generation}`}
            </div>
          ))}
        </div>

        {/* Nodes */}
        <div className="absolute" style={{ top: 32, left: 0 }}>
          {columns.map((c) =>
            c.items.map((v) => {
              const hue = scoreHue(v.avg_composite);
              const mut = hueForMutation(v.mutation_kind);
              const active = selectedId === v.id;
              const champ = v.is_champion;
              return (
                <button
                  key={v.id}
                  onClick={() => onSelect?.(v)}
                  className={`absolute text-left transition-transform ${active ? "scale-[1.03]" : "hover:scale-[1.02]"}`}
                  style={{
                    left: v.x,
                    top: v.y,
                    width: NODE_W,
                    height: NODE_H,
                  }}
                >
                  <div
                    className="h-full rounded-xl border backdrop-blur-md p-2.5 flex flex-col justify-between"
                    style={{
                      borderColor: champ ? "#fbbf24" : active ? hue : "rgba(148,163,184,0.25)",
                      background: champ
                        ? `linear-gradient(135deg, rgba(251,191,36,0.18), rgba(15,23,42,0.6))`
                        : "rgba(15, 23, 42, 0.75)",
                      boxShadow: champ
                        ? "0 0 22px rgba(251,191,36,0.35)"
                        : active
                        ? `0 0 16px ${hue}55`
                        : "0 1px 0 rgba(255,255,255,0.02)",
                    }}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <MutationChip kind={v.mutation_kind} small />
                      <ScoreRing value={v.avg_composite} size={32} />
                    </div>
                    <div>
                      {champ ? (
                        <div className="flex items-center gap-1 text-[10px] text-amber-300 uppercase tracking-widest mb-0.5">
                          <Crown className="w-2.5 h-2.5" />
                          Champion
                        </div>
                      ) : null}
                      <Bar
                        value={v.avg_composite ?? 0}
                        color={`linear-gradient(90deg, ${mut}, ${hue})`}
                        height={4}
                      />
                      <div className="flex items-center justify-between text-[9px] text-slate-400 mt-1 uppercase tracking-widest font-mono">
                        <span>
                          {v.runs?.filter((r) => r.composite != null).length || 0}/
                          {v.runs?.length || 0} cases
                        </span>
                        <span>{fmtCost(v.cost_usd)}</span>
                      </div>
                    </div>
                  </div>
                </button>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
};

// ─── Variant detail ────────────────────────────────────────────────────────

const VariantDetail = ({ variant, baseVariant, onPromote, onCopy, onClose }) => {
  const [expanded, setExpanded] = useState(true);
  if (!variant) return null;
  const lift =
    baseVariant && variant.avg_composite != null && baseVariant.avg_composite != null
      ? Number(variant.avg_composite) - Number(baseVariant.avg_composite)
      : null;

  return (
    <Card className="bg-slate-900/80 border border-slate-800/80 backdrop-blur-md">
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-3">
            <ScoreRing value={variant.avg_composite} size={64} label="score" />
            <div>
              <CardTitle className="text-base text-slate-100 flex items-center gap-2">
                {variant.is_champion ? <Crown className="w-4 h-4 text-amber-400" /> : null}
                {variant.mutation_kind === "base"
                  ? "Base prompt"
                  : `Gen ${variant.generation} · ${variant.mutation_kind.replace(/_/g, " ")}`}
                {variant.is_elite ? (
                  <Badge variant="outline" className="text-[10px] border-violet-500/50 text-violet-300">
                    elite
                  </Badge>
                ) : null}
              </CardTitle>
              <div className="text-xs text-slate-400 mt-0.5 italic">
                {variant.mutation_note || "—"}
              </div>
              {lift != null ? (
                <div className="mt-1.5 flex items-center gap-2">
                  <LiftPill base={baseVariant.avg_composite} best={variant.avg_composite} />
                  <span className="text-[11px] text-slate-500">
                    vs base ({baseVariant.avg_composite?.toFixed(1)})
                  </span>
                </div>
              ) : null}
            </div>
          </div>
          <div className="flex items-center gap-1.5">
            <Button
              size="sm"
              variant="outline"
              className="h-7 text-[11px] border-slate-700 text-slate-300 hover:bg-slate-800"
              onClick={() => onCopy?.(variant.prompt)}
            >
              <Copy className="w-3 h-3 mr-1" />
              Copy
            </Button>
            {!variant.is_champion && variant.avg_composite != null ? (
              <Button
                size="sm"
                className="h-7 text-[11px] bg-gradient-to-r from-amber-500 to-amber-600 hover:from-amber-400 hover:to-amber-500 text-white border-0"
                onClick={() => onPromote?.(variant)}
              >
                <Crown className="w-3 h-3 mr-1" />
                Promote
              </Button>
            ) : null}
            {onClose ? (
              <Button
                size="sm"
                variant="ghost"
                className="h-7 w-7 p-0 text-slate-400 hover:text-slate-200"
                onClick={onClose}
              >
                <X className="w-4 h-4" />
              </Button>
            ) : null}
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="grid grid-cols-3 gap-2 text-center text-[11px]">
          <div className="rounded-lg bg-slate-950/60 border border-slate-800/80 p-2">
            <div className="text-slate-500 uppercase tracking-widest">Min</div>
            <div className="text-slate-200 font-mono">{fmtNum(variant.min_composite, 1)}</div>
          </div>
          <div className="rounded-lg bg-slate-950/60 border border-slate-800/80 p-2">
            <div className="text-slate-500 uppercase tracking-widest">Avg</div>
            <div className="font-mono font-bold" style={{ color: scoreHue(variant.avg_composite) }}>
              {fmtNum(variant.avg_composite, 1)}
            </div>
          </div>
          <div className="rounded-lg bg-slate-950/60 border border-slate-800/80 p-2">
            <div className="text-slate-500 uppercase tracking-widest">Max</div>
            <div className="text-slate-200 font-mono">{fmtNum(variant.max_composite, 1)}</div>
          </div>
        </div>

        <div>
          <button
            className="w-full flex items-center justify-between text-[11px] uppercase tracking-widest text-slate-400 hover:text-slate-200"
            onClick={() => setExpanded((x) => !x)}
          >
            <span className="flex items-center gap-2">
              {expanded ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
              Prompt
              <span className="text-slate-600 font-mono normal-case tracking-normal">
                · {variant.prompt?.length || 0} chars
              </span>
            </span>
            <span className="font-mono text-slate-500 normal-case">#{variant.prompt_hash}</span>
          </button>
          {expanded ? (
            <pre className="mt-1.5 max-h-72 overflow-auto rounded-lg bg-slate-950/80 border border-slate-800/80 p-3 text-[12px] leading-relaxed text-slate-200 whitespace-pre-wrap font-mono">
              {variant.prompt}
            </pre>
          ) : null}
        </div>

        {variant.runs?.length ? (
          <div>
            <div className="text-[11px] uppercase tracking-widest text-slate-400 mb-1.5">
              Per-case results
            </div>
            <div className="space-y-2">
              {variant.runs.map((r, i) => {
                const compHue = scoreHue(r.composite);
                return (
                  <div
                    key={i}
                    className="rounded-lg border border-slate-800/80 bg-slate-950/60 p-2.5"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <div className="text-[11px] text-slate-300 truncate">
                        <span className="text-slate-500 font-mono mr-1.5">#{i + 1}</span>
                        {r.input?.slice(0, 110) || "—"}
                        {r.input?.length > 110 ? "…" : ""}
                      </div>
                      <ScoreRing value={r.composite} size={36} />
                    </div>
                    {r.error ? (
                      <div className="mt-1.5 flex items-center gap-1.5 text-[11px] text-rose-300">
                        <AlertTriangle className="w-3 h-3" /> {r.error}
                      </div>
                    ) : (
                      <div className="mt-1.5 grid grid-cols-1 gap-1.5">
                        <Bar value={r.composite ?? 0} color={`linear-gradient(90deg, ${compHue}, ${compHue})`} height={4} />
                        {r.summary ? (
                          <div className="text-[11px] text-slate-400 italic">
                            “{r.summary.slice(0, 220)}{r.summary.length > 220 ? "…" : ""}”
                          </div>
                        ) : null}
                        {r.response ? (
                          <details className="text-[11px] text-slate-400 mt-0.5">
                            <summary className="cursor-pointer hover:text-slate-200">show response</summary>
                            <pre className="mt-1 rounded bg-slate-900/80 p-2 whitespace-pre-wrap font-mono text-[11px] text-slate-300">
                              {r.response}
                            </pre>
                          </details>
                        ) : null}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
};

// ─── Optimization rail row ──────────────────────────────────────────────────

const OptRow = ({ opt, active, onClick }) => {
  const status = opt.status || "draft";
  const statusHue =
    status === "complete"
      ? "#22d3a8"
      : status === "running"
      ? "#fb923c"
      : status === "failed"
      ? "#fb7185"
      : "#94a3b8";
  return (
    <button
      onClick={onClick}
      className={`w-full text-left rounded-xl border p-3 transition-all ${active ? "border-violet-500/70 bg-violet-500/10" : "border-slate-800/70 hover:border-slate-700 bg-slate-900/40 hover:bg-slate-900/70"}`}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5 text-sm text-slate-100 font-medium truncate">
            <Sparkles className="w-3.5 h-3.5 text-violet-400" />
            {opt.name}
          </div>
          <div className="flex items-center gap-1.5 mt-1 text-[10px] uppercase tracking-widest">
            <span
              className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full border"
              style={{
                color: statusHue,
                borderColor: `${statusHue}55`,
                background: `${statusHue}1a`,
              }}
            >
              <span className="w-1 h-1 rounded-full" style={{ background: statusHue }} />
              {status}
            </span>
            <span className="text-slate-500 normal-case tracking-normal">
              gen {opt.generations_done}/{opt.target_generations}
            </span>
            <span className="text-slate-500 normal-case tracking-normal">
              · {opt.n_variants ?? "—"} variants
            </span>
          </div>
        </div>
        <ScoreRing value={opt.best_composite} size={36} />
      </div>
      {opt.base_composite != null && opt.best_composite != null ? (
        <div className="mt-2 flex items-center justify-between text-[11px]">
          <span className="text-slate-500 font-mono">
            {opt.base_composite.toFixed(1)} → {opt.best_composite.toFixed(1)}
          </span>
          <LiftPill base={opt.base_composite} best={opt.best_composite} />
        </div>
      ) : (
        <div className="mt-2 text-[11px] text-slate-500 italic">No baseline scored yet.</div>
      )}
    </button>
  );
};

// ─── New-optimization wizard ────────────────────────────────────────────────

const DEFAULT_BASE = "Reply to this customer support email. Be helpful and friendly.";

const NewOptForm = ({ rubrics, mutations, onCreate, busy }) => {
  const [name, setName] = useState("Untitled optimization");
  const [basePrompt, setBasePrompt] = useState(DEFAULT_BASE);
  const [cases, setCases] = useState([
    { input: "I've been charged twice this month — please refund the duplicate.", expected: "Acknowledge the duplicate, confirm refund timing, ask for order ID." },
    { input: "The app crashes when I open the camera. iPhone 12, iOS 17.", expected: "Confirm the bug, suggest a workaround, escalate." },
  ]);
  const [targetGens, setTargetGens] = useState(3);
  const [population, setPopulation] = useState(5);
  const [elite, setElite] = useState(2);
  const [enabledMut, setEnabledMut] = useState({
    add_role: true,
    step_by_step: true,
    add_constraints: true,
    structure_sections: true,
    few_shot: true,
    negative_constraints: false,
    anchor_guidance: false,
    safety_check: false,
    grounding: false,
    simplify: false,
    one_shot_inverse: false,
  });
  const [dryrun, setDryrun] = useState(true);
  const [rubricId, setRubricId] = useState("");
  const [judgeProvider, setJudgeProvider] = useState("");
  const [judgeModel, setJudgeModel] = useState("");
  const [candProvider, setCandProvider] = useState("");
  const [candModel, setCandModel] = useState("");
  const [previewBusy, setPreviewBusy] = useState(false);
  const [previews, setPreviews] = useState([]);

  const addCase = () => setCases((cs) => [...cs, { input: "", expected: "" }]);
  const removeCase = (i) =>
    setCases((cs) => cs.filter((_, idx) => idx !== i));
  const updateCase = (i, key, value) =>
    setCases((cs) => cs.map((c, idx) => (idx === i ? { ...c, [key]: value } : c)));

  const enabledMutKinds = useMemo(
    () => Object.entries(enabledMut).filter(([, v]) => v).map(([k]) => k),
    [enabledMut]
  );

  const handlePreview = useCallback(async () => {
    if (!basePrompt.trim()) return;
    setPreviewBusy(true);
    try {
      const res = await ApiService.optimizerPreview({
        base_prompt: basePrompt,
        test_cases: cases,
        rubric_id: rubricId || undefined,
      });
      setPreviews(res.previews || []);
    } catch (e) {
      toast.error(`Preview failed: ${e.message}`);
    } finally {
      setPreviewBusy(false);
    }
  }, [basePrompt, cases, rubricId]);

  const submit = useCallback(() => {
    const payload = {
      name: name.trim() || "Untitled optimization",
      base_prompt: basePrompt.trim(),
      test_cases: cases.filter((c) => c.input.trim()),
      target_generations: targetGens,
      strategy: {
        population,
        elite,
        mutations: enabledMutKinds,
      },
      dryrun,
      rubric_id: rubricId || undefined,
      judge_provider: judgeProvider || undefined,
      judge_model: judgeModel || undefined,
      candidate_provider: candProvider || undefined,
      candidate_model: candModel || undefined,
    };
    onCreate(payload);
  }, [name, basePrompt, cases, targetGens, population, elite, enabledMutKinds, dryrun, rubricId, judgeProvider, judgeModel, candProvider, candModel, onCreate]);

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="md:col-span-2 space-y-3">
          <Label className="text-xs uppercase tracking-widest text-slate-400">Name</Label>
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="bg-slate-900/60 border-slate-700 text-slate-100"
            placeholder="e.g. Customer-email triage"
          />
          <Label className="text-xs uppercase tracking-widest text-slate-400 mt-2 block">
            Base prompt — your starting point
          </Label>
          <Textarea
            value={basePrompt}
            onChange={(e) => setBasePrompt(e.target.value)}
            className="bg-slate-900/60 border-slate-700 text-slate-100 min-h-[110px] font-mono text-sm"
            placeholder="The prompt the optimizer will try to improve…"
          />
        </div>
        <div className="space-y-3">
          <div className="rounded-2xl border border-slate-800/80 bg-slate-900/60 p-3 space-y-3">
            <div className="flex items-center justify-between">
              <Label className="text-xs uppercase tracking-widest text-slate-400">
                Mode
              </Label>
              <div className="flex items-center gap-2">
                <span className={`text-[11px] ${dryrun ? "text-emerald-300" : "text-slate-500"}`}>
                  Dry-run
                </span>
                <Switch checked={!dryrun} onCheckedChange={(v) => setDryrun(!v)} />
                <span className={`text-[11px] ${!dryrun ? "text-amber-300" : "text-slate-500"}`}>
                  Live
                </span>
              </div>
            </div>
            <div className="text-[11px] text-slate-500 leading-snug">
              {dryrun
                ? "Heuristic scoring — no API calls, runs instantly. Great for exploring strategies."
                : "Real candidate model produces responses; real judge scores them against the rubric. Costs credits."}
            </div>
            <Separator className="bg-slate-800/80" />
            <div className="grid grid-cols-2 gap-2 text-[11px]">
              <div>
                <Label className="text-[10px] uppercase tracking-widest text-slate-500">Generations</Label>
                <Input
                  type="number"
                  min={1}
                  max={8}
                  value={targetGens}
                  onChange={(e) => setTargetGens(Number(e.target.value) || 1)}
                  className="bg-slate-950/60 border-slate-800 text-slate-200 h-8 mt-1"
                />
              </div>
              <div>
                <Label className="text-[10px] uppercase tracking-widest text-slate-500">Population</Label>
                <Input
                  type="number"
                  min={1}
                  max={12}
                  value={population}
                  onChange={(e) => setPopulation(Number(e.target.value) || 1)}
                  className="bg-slate-950/60 border-slate-800 text-slate-200 h-8 mt-1"
                />
              </div>
              <div>
                <Label className="text-[10px] uppercase tracking-widest text-slate-500">Elites carried</Label>
                <Input
                  type="number"
                  min={0}
                  max={population}
                  value={elite}
                  onChange={(e) => setElite(Math.min(Number(e.target.value) || 0, population))}
                  className="bg-slate-950/60 border-slate-800 text-slate-200 h-8 mt-1"
                />
              </div>
              <div>
                <Label className="text-[10px] uppercase tracking-widest text-slate-500">Active mutations</Label>
                <div className="text-slate-300 font-mono mt-2">{enabledMutKinds.length}</div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div>
        <Label className="text-xs uppercase tracking-widest text-slate-400">
          Mutation strategy mix
        </Label>
        <div className="mt-2 grid grid-cols-2 lg:grid-cols-3 gap-2">
          {mutations.map((m) => {
            const on = enabledMut[m.kind];
            const hue = hueForMutation(m.kind);
            return (
              <button
                key={m.kind}
                onClick={() =>
                  setEnabledMut((prev) => ({ ...prev, [m.kind]: !prev[m.kind] }))
                }
                className={`text-left rounded-xl border p-2.5 transition-all`}
                style={{
                  borderColor: on ? `${hue}80` : "rgba(148,163,184,0.25)",
                  background: on
                    ? `linear-gradient(135deg, ${hue}22, rgba(15,23,42,0.5))`
                    : "rgba(15,23,42,0.55)",
                }}
              >
                <div className="flex items-center justify-between gap-2">
                  <MutationChip kind={m.kind} label={m.label} small />
                  {on ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <span className="text-[10px] text-slate-500">off</span>}
                </div>
                <div className="text-[11px] text-slate-400 mt-1.5 leading-snug">{m.blurb}</div>
              </button>
            );
          })}
        </div>
      </div>

      {!dryrun ? (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 rounded-2xl border border-amber-500/30 bg-amber-500/5 p-3">
          <div className="md:col-span-2 flex items-center gap-2 text-[11px] text-amber-300">
            <Zap className="w-3.5 h-3.5" /> Live mode — pick a rubric to judge against and the candidate model to optimize for.
          </div>
          <div>
            <Label className="text-[10px] uppercase tracking-widest text-slate-400">Rubric</Label>
            <Select value={rubricId} onValueChange={setRubricId}>
              <SelectTrigger className="bg-slate-900/60 border-slate-700 text-slate-200 mt-1">
                <SelectValue placeholder="Pick a saved rubric" />
              </SelectTrigger>
              <SelectContent>
                {rubrics.map((r) => (
                  <SelectItem key={r.id} value={r.id}>
                    {r.name} · {r.n_dimensions || 0} dims
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <Label className="text-[10px] uppercase tracking-widest text-slate-400">Judge provider</Label>
              <Input value={judgeProvider} onChange={(e) => setJudgeProvider(e.target.value)} placeholder="OpenAI" className="bg-slate-900/60 border-slate-700 text-slate-200 mt-1 h-8" />
            </div>
            <div>
              <Label className="text-[10px] uppercase tracking-widest text-slate-400">Judge model</Label>
              <Input value={judgeModel} onChange={(e) => setJudgeModel(e.target.value)} placeholder="gpt-4o-mini" className="bg-slate-900/60 border-slate-700 text-slate-200 mt-1 h-8" />
            </div>
            <div>
              <Label className="text-[10px] uppercase tracking-widest text-slate-400">Candidate provider</Label>
              <Input value={candProvider} onChange={(e) => setCandProvider(e.target.value)} placeholder="OpenAI" className="bg-slate-900/60 border-slate-700 text-slate-200 mt-1 h-8" />
            </div>
            <div>
              <Label className="text-[10px] uppercase tracking-widest text-slate-400">Candidate model</Label>
              <Input value={candModel} onChange={(e) => setCandModel(e.target.value)} placeholder="gpt-4o-mini" className="bg-slate-900/60 border-slate-700 text-slate-200 mt-1 h-8" />
            </div>
          </div>
        </div>
      ) : null}

      <div>
        <div className="flex items-center justify-between">
          <Label className="text-xs uppercase tracking-widest text-slate-400">
            Test cases ({cases.length})
          </Label>
          <Button
            size="sm"
            variant="outline"
            className="h-7 text-[11px] border-slate-700 text-slate-300 hover:bg-slate-800"
            onClick={addCase}
          >
            <Plus className="w-3 h-3 mr-1" />
            Add case
          </Button>
        </div>
        <div className="mt-2 space-y-2">
          {cases.map((c, i) => (
            <div
              key={i}
              className="rounded-xl border border-slate-800/80 bg-slate-900/40 p-2.5 space-y-1.5"
            >
              <div className="flex items-center justify-between text-[10px] uppercase tracking-widest text-slate-500">
                <span>Case #{i + 1}</span>
                <Button
                  size="sm"
                  variant="ghost"
                  className="h-6 w-6 p-0 text-slate-500 hover:text-rose-400"
                  onClick={() => removeCase(i)}
                >
                  <Trash2 className="w-3 h-3" />
                </Button>
              </div>
              <Textarea
                value={c.input}
                onChange={(e) => updateCase(i, "input", e.target.value)}
                placeholder="Input the candidate model will see…"
                className="bg-slate-950/60 border-slate-800 text-slate-200 min-h-[60px] text-sm"
              />
              <Textarea
                value={c.expected}
                onChange={(e) => updateCase(i, "expected", e.target.value)}
                placeholder="(optional) Expected output / key facts the response should cover"
                className="bg-slate-950/60 border-slate-800 text-slate-400 min-h-[40px] text-xs"
              />
            </div>
          ))}
        </div>
      </div>

      <div className="flex items-center gap-2">
        <Button
          variant="outline"
          className="border-slate-700 text-slate-300 hover:bg-slate-800"
          onClick={handlePreview}
          disabled={previewBusy || !basePrompt.trim()}
        >
          <Microscope className="w-3.5 h-3.5 mr-1.5" />
          {previewBusy ? "Previewing…" : "Preview mutations"}
        </Button>
        <Button
          className="bg-gradient-to-r from-violet-500 via-fuchsia-500 to-amber-500 text-white border-0 shadow-[0_0_20px_rgba(168,85,247,0.35)] hover:shadow-[0_0_28px_rgba(168,85,247,0.55)]"
          onClick={submit}
          disabled={busy || !basePrompt.trim() || cases.filter((c) => c.input.trim()).length === 0}
        >
          <Play className="w-3.5 h-3.5 mr-1.5" />
          {busy ? "Creating…" : "Create optimization"}
        </Button>
      </div>

      {previews.length ? (
        <div>
          <Label className="text-xs uppercase tracking-widest text-slate-400">
            Mutation previews
          </Label>
          <div className="mt-2 grid grid-cols-1 lg:grid-cols-2 gap-2">
            {previews.map((p) => {
              const hue = hueForMutation(p.kind);
              return (
                <div
                  key={p.kind}
                  className="rounded-xl border bg-slate-950/60 p-2.5"
                  style={{ borderColor: p.changed ? `${hue}66` : "rgba(148,163,184,0.18)" }}
                >
                  <div className="flex items-center justify-between gap-2">
                    <MutationChip kind={p.kind} label={p.label} small />
                    <span className={`text-[10px] font-mono ${p.delta_chars > 0 ? "text-emerald-400" : p.delta_chars < 0 ? "text-amber-400" : "text-slate-500"}`}>
                      Δ {p.delta_chars >= 0 ? "+" : ""}{p.delta_chars} chars
                    </span>
                  </div>
                  <div className="text-[11px] text-slate-400 mt-1.5 italic">{p.note}</div>
                  <pre className="mt-1.5 max-h-32 overflow-auto rounded bg-slate-900/80 p-2 text-[11px] text-slate-200 whitespace-pre-wrap font-mono leading-snug">
                    {p.prompt.slice(0, 600)}{p.prompt.length > 600 ? "…" : ""}
                  </pre>
                </div>
              );
            })}
          </div>
        </div>
      ) : null}
    </div>
  );
};

// ─── Main panel ────────────────────────────────────────────────────────────

const OptimizerStudio = () => {
  const [optimizations, setOptimizations] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [selectedOpt, setSelectedOpt] = useState(null);
  const [stats, setStats] = useState(null);
  const [mutations, setMutations] = useState([]);
  const [rubrics, setRubrics] = useState([]);
  const [tab, setTab] = useState("setup"); // setup | tree | leaderboard
  const [activeVariantId, setActiveVariantId] = useState(null);
  const [creating, setCreating] = useState(false);
  const [advancing, setAdvancing] = useState(false);
  const [query, setQuery] = useState("");
  const [showWizard, setShowWizard] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const list = await ApiService.listOptimizations({ q: query || undefined });
      setOptimizations(list.optimizations || []);
      const st = await ApiService.optimizerStats();
      setStats(st.stats || null);
    } catch (e) {
      // silent — sidebar shouldn't disrupt main flow
      console.warn("optimizer refresh failed", e);
    }
  }, [query]);

  // Lazy-load mutations + rubrics on first mount.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const m = await ApiService.optimizerMutations();
        if (!cancelled) setMutations(m.mutations || []);
      } catch {
        // tolerate
      }
      try {
        const r = await ApiService.listRubrics({ limit: 50 });
        if (!cancelled) setRubrics(r.rubrics || []);
      } catch {
        // tolerate
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  useEffect(() => {
    if (!selectedId) {
      setSelectedOpt(null);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const r = await ApiService.getOptimization(selectedId);
        if (!cancelled) {
          setSelectedOpt(r.optimization);
          // default-select the champion or top variant
          const champ = (r.optimization?.variants || []).find((v) => v.is_champion);
          const top = (r.optimization?.variants || []).reduce(
            (best, v) =>
              v.avg_composite != null && (!best || v.avg_composite > (best.avg_composite ?? -1))
                ? v
                : best,
            null
          );
          setActiveVariantId(champ?.id || top?.id || null);
        }
      } catch (e) {
        toast.error(`Failed to load optimization: ${e.message}`);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [selectedId]);

  const baseVariant = useMemo(
    () => (selectedOpt?.variants || []).find((v) => v.mutation_kind === "base"),
    [selectedOpt]
  );
  const activeVariant = useMemo(
    () => (selectedOpt?.variants || []).find((v) => v.id === activeVariantId) || null,
    [selectedOpt, activeVariantId]
  );

  const sortedVariants = useMemo(() => {
    const list = (selectedOpt?.variants || []).filter((v) => v.avg_composite != null);
    return list.sort((a, b) => (b.avg_composite ?? 0) - (a.avg_composite ?? 0));
  }, [selectedOpt]);

  const handleCreate = useCallback(
    async (payload) => {
      setCreating(true);
      try {
        const res = await ApiService.createOptimization(payload);
        toast.success(`Optimization "${res.optimization.name}" created`);
        setShowWizard(false);
        setSelectedId(res.optimization.id);
        setTab("tree");
        await refresh();
      } catch (e) {
        toast.error(`Create failed: ${e.message}`);
      } finally {
        setCreating(false);
      }
    },
    [refresh]
  );

  const handleSeed = useCallback(async () => {
    try {
      const res = await ApiService.seedOptimization();
      toast.success("Demo optimization seeded — hit Run to evolve");
      setSelectedId(res.optimization.id);
      setTab("tree");
      await refresh();
    } catch (e) {
      toast.error(`Seed failed: ${e.message}`);
    }
  }, [refresh]);

  const reloadSelected = useCallback(async () => {
    if (!selectedId) return;
    try {
      const r = await ApiService.getOptimization(selectedId);
      setSelectedOpt(r.optimization);
    } catch (e) {
      // tolerate
    }
  }, [selectedId]);

  const handleAdvance = useCallback(async () => {
    if (!selectedId) return;
    setAdvancing(true);
    try {
      const res = await ApiService.advanceOptimization(selectedId);
      if (res.best_in_generation != null) {
        toast.success(
          `Gen ${res.generation}: best ${res.best_in_generation.toFixed(1)}/100` +
            (res.gen_cost ? ` · ${fmtCost(res.gen_cost)}` : "")
        );
      } else {
        toast.message(`Gen ${res.generation}: no successful variants`);
      }
      await reloadSelected();
      await refresh();
    } catch (e) {
      toast.error(`Advance failed: ${e.message}`);
    } finally {
      setAdvancing(false);
    }
  }, [selectedId, reloadSelected, refresh]);

  const handleRunAll = useCallback(async () => {
    if (!selectedId || !selectedOpt) return;
    setAdvancing(true);
    try {
      const res = await ApiService.runOptimization(selectedId, {
        confirm_live: !selectedOpt.dryrun,
      });
      const runs = res.generations_run || [];
      toast.success(
        `Ran ${runs.length} generation${runs.length === 1 ? "" : "s"} — best ${
          res.optimization.best_composite != null
            ? res.optimization.best_composite.toFixed(1)
            : "—"
        }/100`
      );
      await reloadSelected();
      await refresh();
    } catch (e) {
      toast.error(`Run failed: ${e.message}`);
    } finally {
      setAdvancing(false);
    }
  }, [selectedId, selectedOpt, reloadSelected, refresh]);

  const handleDelete = useCallback(
    async (oid) => {
      if (!window.confirm("Delete this optimization and all its variants?")) return;
      try {
        await ApiService.deleteOptimization(oid);
        toast.success("Optimization deleted");
        if (selectedId === oid) {
          setSelectedId(null);
          setSelectedOpt(null);
        }
        await refresh();
      } catch (e) {
        toast.error(`Delete failed: ${e.message}`);
      }
    },
    [selectedId, refresh]
  );

  const handlePromote = useCallback(
    async (variant) => {
      if (!selectedId) return;
      try {
        const res = await ApiService.promoteVariant(selectedId, variant.id);
        toast.success(`Promoted to champion — ${variant.avg_composite?.toFixed(1)}/100`);
        setSelectedOpt(res.optimization);
        await refresh();
      } catch (e) {
        toast.error(`Promote failed: ${e.message}`);
      }
    },
    [selectedId, refresh]
  );

  const handleCopy = useCallback(async (text) => {
    try {
      await navigator.clipboard.writeText(text);
      toast.success("Prompt copied");
    } catch {
      toast.error("Copy failed");
    }
  }, []);

  const handleExport = useCallback(() => {
    if (!selectedOpt) return;
    const blob = new Blob(
      [JSON.stringify(selectedOpt, null, 2)],
      { type: "application/json" }
    );
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `optimization-${selectedOpt.id.slice(0, 8)}.json`;
    a.click();
    URL.revokeObjectURL(url);
    toast.success("Exported");
  }, [selectedOpt]);

  const remaining =
    selectedOpt ? Math.max(0, selectedOpt.target_generations - selectedOpt.generations_done) : 0;

  return (
    <Card className="shadow-2xl border-0 bg-slate-950/60 text-slate-100 backdrop-blur-xl overflow-hidden">
      <CardHeader className="pb-3 border-b border-slate-800/80 bg-gradient-to-br from-violet-600/20 via-fuchsia-600/15 to-amber-500/20 relative">
        <div
          className="absolute inset-0 opacity-30 pointer-events-none"
          style={{
            background:
              "radial-gradient(800px 300px at 0% 0%, rgba(168,85,247,0.35), transparent 60%), radial-gradient(700px 320px at 100% 0%, rgba(251,191,36,0.25), transparent 65%)",
          }}
        />
        <div className="relative flex items-start justify-between gap-3 flex-wrap">
          <div>
            <CardTitle className="flex items-center gap-2 text-xl">
              <div className="grid place-items-center w-8 h-8 rounded-lg bg-gradient-to-br from-violet-500 to-fuchsia-500 shadow-[0_0_20px_rgba(168,85,247,0.4)]">
                <Wand2 className="w-4 h-4 text-white" />
              </div>
              Optimizer Studio
              <Badge className="text-[10px] uppercase tracking-wider bg-gradient-to-r from-violet-500 via-fuchsia-500 to-amber-500 text-white border-0">
                Round 10 · new
              </Badge>
            </CardTitle>
            <div className="text-sm text-slate-300 mt-1.5 max-w-2xl leading-snug">
              Type a base prompt, pick a rubric, and watch it evolve. Each generation mutates the elites,
              scores every variant on every test case, and promotes the winner.
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              className="border-slate-700 text-slate-200 hover:bg-slate-800/60"
              onClick={handleSeed}
            >
              <Beaker className="w-4 h-4 mr-1.5" />
              Seed demo
            </Button>
            <Button
              className="bg-gradient-to-r from-violet-500 to-fuchsia-500 text-white border-0 shadow-[0_0_20px_rgba(168,85,247,0.35)] hover:shadow-[0_0_28px_rgba(168,85,247,0.55)]"
              onClick={() => {
                setShowWizard(true);
                setSelectedId(null);
                setTab("setup");
              }}
            >
              <Plus className="w-4 h-4 mr-1.5" />
              New optimization
            </Button>
          </div>
        </div>

        {/* Stats strip */}
        <div className="relative mt-4 grid grid-cols-2 md:grid-cols-5 gap-2">
          <StatTile icon={<Layers className="w-3.5 h-3.5" />} label="Optimizations" value={stats?.n_optimizations ?? 0} />
          <StatTile icon={<Activity className="w-3.5 h-3.5" />} label="Running" value={stats?.n_running ?? 0} hue="#fb923c" />
          <StatTile icon={<Cpu className="w-3.5 h-3.5" />} label="Variants explored" value={stats?.n_variants ?? 0} />
          <StatTile
            icon={<TrendingUp className="w-3.5 h-3.5" />}
            label="Best lift"
            value={stats?.biggest_lift ? `+${stats.biggest_lift.lift.toFixed(1)} pts` : "—"}
            hue="#22d3a8"
          />
          <StatTile
            icon={<Award className="w-3.5 h-3.5" />}
            label="Top mutation"
            value={stats?.top_mutations?.[0]?.kind?.replace(/_/g, " ") || "—"}
            hue={hueForMutation(stats?.top_mutations?.[0]?.kind)}
          />
        </div>
      </CardHeader>

      <CardContent className="p-0">
        <div className="grid grid-cols-1 lg:grid-cols-[300px,1fr]">
          {/* Left rail */}
          <div className="border-r border-slate-800/80 bg-slate-950/40 p-3 min-h-[600px]">
            <div className="relative">
              <Search className="w-3.5 h-3.5 text-slate-500 absolute left-2.5 top-1/2 -translate-y-1/2" />
              <Input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search optimizations…"
                className="pl-7 bg-slate-900/60 border-slate-800 text-slate-200 h-8"
              />
            </div>
            <Separator className="my-3 bg-slate-800/80" />
            <ScrollArea className="h-[540px] pr-1.5">
              <div className="space-y-2">
                {optimizations.length === 0 ? (
                  <div className="text-center py-8 text-sm text-slate-500">
                    <Lightbulb className="w-6 h-6 mx-auto mb-2 opacity-60" />
                    No optimizations yet. <br />
                    Try the demo seed, or create your own.
                  </div>
                ) : (
                  optimizations.map((o) => (
                    <OptRow
                      key={o.id}
                      opt={o}
                      active={o.id === selectedId}
                      onClick={() => {
                        setSelectedId(o.id);
                        setShowWizard(false);
                        setTab("tree");
                      }}
                    />
                  ))
                )}
              </div>
            </ScrollArea>
          </div>

          {/* Main pane */}
          <div className="p-5 min-h-[600px]">
            {showWizard ? (
              <div>
                <div className="mb-3 flex items-center justify-between">
                  <h3 className="text-lg font-semibold text-slate-100 flex items-center gap-2">
                    <Sparkles className="w-4 h-4 text-violet-400" />
                    New optimization
                  </h3>
                  <Button
                    variant="ghost"
                    className="text-slate-400 hover:text-slate-200"
                    onClick={() => setShowWizard(false)}
                  >
                    <X className="w-4 h-4 mr-1" />
                    Cancel
                  </Button>
                </div>
                <NewOptForm
                  rubrics={rubrics}
                  mutations={mutations}
                  onCreate={handleCreate}
                  busy={creating}
                />
              </div>
            ) : !selectedOpt ? (
              <EmptyHero
                stats={stats}
                onSeed={handleSeed}
                onCreate={() => setShowWizard(true)}
              />
            ) : (
              <div className="space-y-4">
                {/* Hero strip */}
                <div className="rounded-2xl border border-slate-800/80 bg-gradient-to-br from-slate-900 via-slate-900/60 to-slate-950 p-4">
                  <div className="flex items-start justify-between gap-4 flex-wrap">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <h3 className="text-xl font-bold text-slate-100">
                          {selectedOpt.name}
                        </h3>
                        <Badge
                          variant="outline"
                          className={`text-[11px] uppercase tracking-widest border-slate-700 ${selectedOpt.dryrun ? "text-emerald-300" : "text-amber-300"}`}
                        >
                          {selectedOpt.dryrun ? "Dry-run" : "Live"}
                        </Badge>
                        <Badge
                          variant="outline"
                          className="text-[11px] uppercase tracking-widest border-slate-700 text-slate-300"
                        >
                          {selectedOpt.status}
                        </Badge>
                      </div>
                      {selectedOpt.description ? (
                        <div className="text-sm text-slate-400 mt-1">{selectedOpt.description}</div>
                      ) : null}
                      <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px] text-slate-400">
                        <span>
                          Gen{" "}
                          <span className="text-slate-200 font-mono">
                            {selectedOpt.generations_done}/{selectedOpt.target_generations}
                          </span>
                        </span>
                        <span>·</span>
                        <span>
                          {selectedOpt.n_variants} variants
                        </span>
                        <span>·</span>
                        <span>{selectedOpt.test_cases.length} test cases</span>
                        <span>·</span>
                        <span>Total spend {fmtCost(selectedOpt.total_cost)}</span>
                      </div>
                    </div>
                    <div className="flex items-center gap-3 flex-wrap">
                      <div className="text-right">
                        <div className="text-[10px] uppercase tracking-widest text-slate-500">
                          Base → Best
                        </div>
                        <div className="flex items-center gap-2 mt-0.5">
                          <ScoreRing value={selectedOpt.base_composite} size={48} />
                          <ArrowUp className="w-4 h-4 text-violet-400" />
                          <ScoreRing value={selectedOpt.best_composite} size={64} label="best" />
                        </div>
                        {selectedOpt.base_composite != null && selectedOpt.best_composite != null ? (
                          <div className="mt-1.5 flex justify-end">
                            <LiftPill
                              base={selectedOpt.base_composite}
                              best={selectedOpt.best_composite}
                            />
                          </div>
                        ) : null}
                      </div>
                    </div>
                  </div>

                  <div className="mt-3 flex flex-wrap items-center gap-2">
                    <Button
                      onClick={handleAdvance}
                      disabled={advancing || remaining <= 0}
                      className="bg-gradient-to-r from-violet-500 to-fuchsia-500 text-white border-0 shadow-[0_0_18px_rgba(168,85,247,0.35)]"
                    >
                      <Play className="w-4 h-4 mr-1.5" />
                      {advancing
                        ? "Running…"
                        : remaining > 0
                        ? `Run next generation (${remaining} left)`
                        : "Complete"}
                    </Button>
                    {selectedOpt.dryrun && remaining > 0 ? (
                      <Button
                        onClick={handleRunAll}
                        disabled={advancing}
                        variant="outline"
                        className="border-slate-700 text-slate-200 hover:bg-slate-800"
                      >
                        <Zap className="w-4 h-4 mr-1.5" />
                        Run all remaining
                      </Button>
                    ) : null}
                    <Button
                      variant="outline"
                      className="border-slate-700 text-slate-200 hover:bg-slate-800"
                      onClick={handleExport}
                    >
                      <Download className="w-4 h-4 mr-1.5" />
                      Export JSON
                    </Button>
                    <Button
                      variant="outline"
                      className="border-rose-800/60 text-rose-300 hover:bg-rose-900/30 ml-auto"
                      onClick={() => handleDelete(selectedOpt.id)}
                    >
                      <Trash2 className="w-4 h-4 mr-1.5" />
                      Delete
                    </Button>
                  </div>

                  {selectedOpt.generations?.length ? (
                    <div className="mt-3 grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-1.5">
                      {[
                        { generation: 0, best_composite: selectedOpt.base_composite, n_variants: 1, isBase: true },
                        ...selectedOpt.generations,
                      ].map((g, i) => (
                        <div
                          key={g.id || `gen-${i}`}
                          className="rounded-lg border border-slate-800/80 bg-slate-950/60 p-2 text-center"
                        >
                          <div className="text-[10px] uppercase tracking-widest text-slate-500">
                            {g.isBase ? "Base" : `Gen ${g.generation}`}
                          </div>
                          <div className="font-mono text-sm mt-0.5 font-bold" style={{ color: scoreHue(g.best_composite) }}>
                            {g.best_composite != null ? g.best_composite.toFixed(1) : "—"}
                          </div>
                          <div className="text-[10px] text-slate-500 font-mono">
                            {g.n_variants} var
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : null}
                </div>

                {/* Tabs */}
                <div className="flex items-center gap-1 rounded-lg bg-slate-900/60 p-1 w-fit border border-slate-800/80">
                  {[
                    { k: "tree", label: "Lineage", icon: <GitBranch className="w-3.5 h-3.5" /> },
                    { k: "leaderboard", label: "Leaderboard", icon: <Trophy className="w-3.5 h-3.5" /> },
                    { k: "setup", label: "Setup", icon: <Sparkles className="w-3.5 h-3.5" /> },
                  ].map((t) => (
                    <button
                      key={t.k}
                      onClick={() => setTab(t.k)}
                      className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-[12px] uppercase tracking-widest transition ${
                        tab === t.k
                          ? "bg-gradient-to-r from-violet-500 to-fuchsia-500 text-white shadow-[0_0_15px_rgba(168,85,247,0.45)]"
                          : "text-slate-400 hover:text-slate-200"
                      }`}
                    >
                      {t.icon}
                      {t.label}
                    </button>
                  ))}
                </div>

                {tab === "tree" ? (
                  <div className="grid grid-cols-1 xl:grid-cols-[1fr,440px] gap-4">
                    <LineageTree
                      opt={selectedOpt}
                      selectedId={activeVariantId}
                      onSelect={(v) => setActiveVariantId(v.id)}
                    />
                    <VariantDetail
                      variant={activeVariant}
                      baseVariant={baseVariant}
                      onPromote={handlePromote}
                      onCopy={handleCopy}
                    />
                  </div>
                ) : null}

                {tab === "leaderboard" ? (
                  <div className="space-y-2">
                    {sortedVariants.length === 0 ? (
                      <div className="text-center py-8 text-sm text-slate-500">
                        No scored variants yet. Run a generation.
                      </div>
                    ) : (
                      sortedVariants.map((v, i) => {
                        const hue = scoreHue(v.avg_composite);
                        return (
                          <button
                            key={v.id}
                            onClick={() => {
                              setActiveVariantId(v.id);
                              setTab("tree");
                            }}
                            className="w-full text-left rounded-xl border border-slate-800/80 bg-slate-900/60 hover:bg-slate-900/90 p-3 transition-all"
                            style={{
                              borderLeft: `3px solid ${hue}`,
                            }}
                          >
                            <div className="flex items-center gap-3">
                              <div className="w-7 h-7 grid place-items-center rounded-md bg-slate-950/60 text-slate-400 font-mono text-sm">
                                {i + 1}
                              </div>
                              <ScoreRing value={v.avg_composite} size={44} />
                              <div className="min-w-0 flex-1">
                                <div className="flex items-center gap-1.5 flex-wrap">
                                  {v.is_champion ? <Crown className="w-3.5 h-3.5 text-amber-400" /> : null}
                                  <span className="text-sm text-slate-200 font-medium">
                                    {v.mutation_kind === "base" ? "Base prompt" : `Gen ${v.generation}`}
                                  </span>
                                  <MutationChip kind={v.mutation_kind} small />
                                  {v.is_elite ? (
                                    <Badge variant="outline" className="text-[10px] border-violet-500/50 text-violet-300">
                                      elite
                                    </Badge>
                                  ) : null}
                                </div>
                                <div className="text-[11px] text-slate-500 mt-0.5 italic truncate">
                                  {v.mutation_note}
                                </div>
                              </div>
                              <div className="text-right shrink-0">
                                <div className="text-[10px] text-slate-500 uppercase tracking-widest">range</div>
                                <div className="text-[11px] text-slate-300 font-mono">
                                  {v.min_composite?.toFixed(1)} – {v.max_composite?.toFixed(1)}
                                </div>
                              </div>
                            </div>
                          </button>
                        );
                      })
                    )}
                  </div>
                ) : null}

                {tab === "setup" ? (
                  <Card className="bg-slate-900/60 border border-slate-800/80">
                    <CardHeader className="pb-3">
                      <CardTitle className="text-base text-slate-200">Configuration</CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-3 text-sm">
                      <div>
                        <div className="text-[11px] uppercase tracking-widest text-slate-500 mb-1">Base prompt</div>
                        <pre className="rounded bg-slate-950/80 border border-slate-800/80 p-3 text-sm text-slate-200 whitespace-pre-wrap font-mono">
                          {selectedOpt.base_prompt}
                        </pre>
                      </div>
                      <div className="grid grid-cols-2 lg:grid-cols-4 gap-2 text-center text-xs">
                        <KV label="Population" value={selectedOpt.strategy?.population} />
                        <KV label="Elites" value={selectedOpt.strategy?.elite} />
                        <KV label="Mutations" value={selectedOpt.strategy?.mutations?.length} />
                        <KV label="Target gens" value={selectedOpt.target_generations} />
                      </div>
                      <div>
                        <div className="text-[11px] uppercase tracking-widest text-slate-500 mb-1">Mutation pool</div>
                        <div className="flex flex-wrap gap-1.5">
                          {(selectedOpt.strategy?.mutations || []).map((k) => {
                            const meta = mutations.find((m) => m.kind === k);
                            return <MutationChip key={k} kind={k} label={meta?.label || k} />;
                          })}
                        </div>
                      </div>
                      <div>
                        <div className="text-[11px] uppercase tracking-widest text-slate-500 mb-1">Test cases ({selectedOpt.test_cases.length})</div>
                        <div className="space-y-1.5">
                          {selectedOpt.test_cases.map((c, i) => (
                            <div key={i} className="rounded-lg bg-slate-950/60 border border-slate-800/80 p-2 text-[12px]">
                              <div className="text-slate-300">
                                <span className="text-slate-500 font-mono mr-1.5">#{i + 1}</span>
                                {c.input}
                              </div>
                              {c.expected ? (
                                <div className="mt-1 text-slate-500 text-[11px] italic">
                                  expected: {c.expected}
                                </div>
                              ) : null}
                            </div>
                          ))}
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                ) : null}
              </div>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
};

const StatTile = ({ icon, label, value, hue }) => (
  <div
    className="rounded-xl border border-slate-800/80 bg-slate-950/40 backdrop-blur-md p-2.5"
    style={hue ? { borderColor: `${hue}33` } : undefined}
  >
    <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-widest text-slate-400">
      {icon}
      {label}
    </div>
    <div
      className="text-lg font-bold mt-0.5 font-mono"
      style={{ color: hue || "#e2e8f0" }}
    >
      {value}
    </div>
  </div>
);

const KV = ({ label, value }) => (
  <div className="rounded-lg bg-slate-950/60 border border-slate-800/80 p-2">
    <div className="text-[10px] uppercase tracking-widest text-slate-500">{label}</div>
    <div className="text-slate-200 font-mono">{value ?? "—"}</div>
  </div>
);

const EmptyHero = ({ stats, onSeed, onCreate }) => (
  <div className="text-center py-12 max-w-xl mx-auto">
    <div className="grid place-items-center w-16 h-16 mx-auto mb-4 rounded-2xl bg-gradient-to-br from-violet-500 via-fuchsia-500 to-amber-500 shadow-[0_0_40px_rgba(168,85,247,0.45)]">
      <Wand2 className="w-7 h-7 text-white" />
    </div>
    <h3 className="text-2xl font-bold text-slate-100">Optimize a prompt.</h3>
    <p className="mt-2 text-sm text-slate-400 leading-relaxed">
      Type a base prompt, supply a handful of test cases, pick a rubric, and Optimizer
      will mutate the prompt across generations — keeping the elites, exploring new
      strategies, and showing you the winning lineage and the deltas.
    </p>
    <div className="mt-5 flex justify-center gap-2">
      <Button
        variant="outline"
        className="border-slate-700 text-slate-200 hover:bg-slate-800/60"
        onClick={onSeed}
      >
        <Beaker className="w-4 h-4 mr-1.5" />
        Seed demo optimization
      </Button>
      <Button
        className="bg-gradient-to-r from-violet-500 to-fuchsia-500 text-white border-0 shadow-[0_0_18px_rgba(168,85,247,0.35)]"
        onClick={onCreate}
      >
        <Plus className="w-4 h-4 mr-1.5" />
        Start from scratch
      </Button>
    </div>
    {stats?.recent?.length ? (
      <div className="mt-8 text-left">
        <div className="text-[11px] uppercase tracking-widest text-slate-500 mb-2 text-center">
          Recent activity
        </div>
        <div className="space-y-1.5">
          {stats.recent.map((r) => (
            <div
              key={r.id}
              className="rounded-lg border border-slate-800/80 bg-slate-900/40 p-2 flex items-center justify-between"
            >
              <div className="text-sm text-slate-300 truncate flex items-center gap-2">
                <Sparkles className="w-3 h-3 text-violet-400" />
                {r.name}
              </div>
              {r.lift != null ? <LiftPill base={r.base} best={r.best} /> : null}
            </div>
          ))}
        </div>
      </div>
    ) : null}
  </div>
);

export default OptimizerStudio;
