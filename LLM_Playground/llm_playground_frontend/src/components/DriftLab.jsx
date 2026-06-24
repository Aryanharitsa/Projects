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
  Waves,
  Activity,
  Beaker,
  Play,
  Plus,
  Trash2,
  Sparkles,
  RotateCcw,
  Search,
  Copy,
  Crown,
  Layers,
  Trophy,
  AlertTriangle,
  TrendingUp,
  Wand2,
  ChevronRight,
  ChevronDown,
  Zap,
  Repeat,
  Thermometer,
  Target,
  CheckCircle2,
} from "lucide-react";
import { toast } from "sonner";
import ApiService from "../services/api";

// ─── Constants — mirror backend ────────────────────────────────────────────

const BAND_HUE = {
  Steady: "#22c55e",
  Consistent: "#84cc16",
  Drifty: "#f59e0b",
  Wild: "#ef4444",
  "—": "#94a3b8",
};

const VAR_HUE = {
  Steady: "#22c55e",
  Cosmetic: "#06b6d4",
  Verbose: "#a855f7",
  Substantive: "#ef4444",
  "—": "#94a3b8",
};

const VAR_GLYPH = {
  Steady: "≡",
  Cosmetic: "≈",
  Verbose: "↕",
  Substantive: "≠",
  "—": "·",
};

const PROVIDER_MODELS = {
  OpenAI: ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"],
  Anthropic: [
    "claude-opus-4-8",
    "claude-sonnet-4-6",
    "claude-haiku-4-5-20251001",
    "claude-3-5-sonnet-20241022",
  ],
  Google: ["gemini-2.5-pro", "gemini-2.5-flash", "gemini-1.5-pro"],
};

// ─── Tiny utils ────────────────────────────────────────────────────────────

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
const fmtCost = (c) => {
  if (c == null) return "—";
  if (c === 0) return "$0";
  if (c < 0.001) return `$${(c * 1000).toFixed(3)}m`;
  return `$${Number(c).toFixed(4)}`;
};

const stabilityHue = (v) => {
  if (v == null || Number.isNaN(Number(v))) return "#94a3b8";
  const clipped = Math.max(0, Math.min(100, Number(v)));
  // Same red→emerald ramp as adversary — keeps the eye trained.
  const hue = Math.round(clipped * 1.25);
  return `hsl(${hue} 78% 48%)`;
};

const simHue = (v) => {
  // 0.0 (diverged) → red, 1.0 (identical) → emerald.
  if (v == null || Number.isNaN(Number(v))) return "#1f2937";
  const clipped = Math.max(0, Math.min(1, Number(v)));
  const hue = Math.round(clipped * 125);
  const sat = 70 + clipped * 10;
  const light = 36 + clipped * 14;
  return `hsl(${hue} ${sat}% ${light}%)`;
};

const bandFor = (v) => {
  if (v == null) return { label: "—", hue: BAND_HUE["—"] };
  if (v >= 80) return { label: "Steady", hue: BAND_HUE.Steady };
  if (v >= 60) return { label: "Consistent", hue: BAND_HUE.Consistent };
  if (v >= 40) return { label: "Drifty", hue: BAND_HUE.Drifty };
  return { label: "Wild", hue: BAND_HUE.Wild };
};

const distinctClusterPalette = [
  "#22c55e",
  "#06b6d4",
  "#a855f7",
  "#f59e0b",
  "#ef4444",
  "#ec4899",
  "#84cc16",
  "#0ea5e9",
];
const clusterHue = (i) => distinctClusterPalette[(i || 0) % distinctClusterPalette.length];

// ─── Visual primitives ─────────────────────────────────────────────────────

const StabilityRing = ({ value, size = 168, band, variance }) => {
  const has = value != null && !Number.isNaN(Number(value));
  const v = has ? Math.max(0, Math.min(100, Number(value))) : 0;
  const hue = has ? stabilityHue(v) : "#475569";
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
        style={{ width: inner, height: inner, borderRadius: "50%" }}
      >
        <div className="flex flex-col items-center leading-none">
          <span className="text-[11px] text-slate-500 uppercase tracking-[0.3em] mb-1">
            Stability
          </span>
          <span
            className="text-[42px] font-bold tracking-tight"
            style={{ color: has ? hue : "#94a3b8" }}
          >
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
          {variance && variance !== "—" ? (
            <span
              className="text-[10px] mt-1 uppercase tracking-widest"
              style={{ color: VAR_HUE[variance] || "#94a3b8" }}
            >
              {VAR_GLYPH[variance] || "·"} {variance} drift
            </span>
          ) : null}
        </div>
      </div>
    </div>
  );
};

const MiniRing = ({ value, size = 46 }) => {
  const has = value != null;
  const v = has ? Math.max(0, Math.min(100, Number(value))) : 0;
  const hue = has ? stabilityHue(v) : "#475569";
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
        style={{ width: inner, height: inner, borderRadius: "50%" }}
      >
        <span className="text-[11px] font-bold tabular-nums" style={{ color: has ? hue : "#94a3b8" }}>
          {has ? Math.round(v) : "—"}
        </span>
      </div>
    </div>
  );
};

const SimRing = ({ value, size = 42 }) => {
  // 0..1 similarity — its own scale, gold→emerald ramp.
  const has = value != null;
  const v = has ? Math.max(0, Math.min(1, Number(value))) : 0;
  const hue = has ? simHue(v) : "#475569";
  const inner = size - 6;
  return (
    <div
      className="relative grid place-items-center shrink-0"
      style={{
        width: size,
        height: size,
        borderRadius: "50%",
        background: `conic-gradient(${hue} ${v * 360}deg, rgba(148,163,184,0.18) ${v * 360}deg 360deg)`,
      }}
    >
      <div
        className="grid place-items-center bg-slate-950"
        style={{ width: inner, height: inner, borderRadius: "50%" }}
      >
        <span className="text-[10px] font-mono tabular-nums" style={{ color: has ? hue : "#94a3b8" }}>
          {has ? v.toFixed(2) : "—"}
        </span>
      </div>
    </div>
  );
};

const BandChip = ({ band, small = false }) => {
  const hue = BAND_HUE[band] || BAND_HUE["—"];
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full font-medium border uppercase tracking-widest ${
        small ? "px-1.5 py-0.5 text-[9px]" : "px-2 py-0.5 text-[10px]"
      }`}
      style={{
        color: hue,
        borderColor: `${hue}55`,
        background: `${hue}1a`,
      }}
    >
      <span
        className="inline-block rounded-full"
        style={{ width: 6, height: 6, background: hue }}
      />
      {band || "—"}
    </span>
  );
};

const VarianceChip = ({ variance, small = false }) => {
  const hue = VAR_HUE[variance] || VAR_HUE["—"];
  const glyph = VAR_GLYPH[variance] || "·";
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full font-medium border ${
        small ? "px-1.5 py-0.5 text-[9px]" : "px-2 py-0.5 text-[10px]"
      }`}
      style={{
        color: hue,
        borderColor: `${hue}55`,
        background: `${hue}1a`,
      }}
    >
      <span className="font-bold">{glyph}</span>
      {variance} drift
    </span>
  );
};

const ClusterChip = ({ id, small = false }) => {
  const hue = clusterHue(id);
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full font-mono ${
        small ? "px-1.5 py-0.5 text-[9px]" : "px-2 py-0.5 text-[10px]"
      }`}
      style={{
        color: hue,
        borderColor: `${hue}55`,
        background: `${hue}1a`,
        border: `1px solid ${hue}55`,
      }}
    >
      <Layers className={small ? "w-2.5 h-2.5" : "w-3 h-3"} />
      cluster {id != null ? id : "—"}
    </span>
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
      {suffix ? <span className="text-[11px] text-slate-500">{suffix}</span> : null}
    </div>
  </div>
);

// Linear progress bar with hue tinted by the value itself.
const ScoreBar = ({ value, height = 8, label }) => {
  const v = value == null ? 0 : Math.max(0, Math.min(100, Number(value)));
  const hue = value == null ? "#475569" : stabilityHue(v);
  return (
    <div className="flex items-center gap-2">
      <div
        className="flex-1 rounded-full bg-slate-800/80 overflow-hidden"
        style={{ height }}
      >
        <div
          className="h-full rounded-full"
          style={{
            width: `${v}%`,
            background: hue,
            boxShadow: `0 0 6px ${hue}66`,
          }}
        />
      </div>
      <span
        className="text-[11px] font-mono tabular-nums w-12 text-right"
        style={{ color: hue }}
      >
        {value == null ? "—" : Math.round(v)}
      </span>
      {label ? (
        <span className="text-[10px] uppercase tracking-widest text-slate-500 w-16">
          {label}
        </span>
      ) : null}
    </div>
  );
};

// ─── Similarity heatmap ────────────────────────────────────────────────────

const Heatmap = ({ matrix, medoidIdx, replayIndexes }) => {
  const n = (matrix || []).length;
  if (!n) {
    return (
      <div className="text-center text-sm text-slate-500 py-6">
        Need at least two successful replays for a similarity matrix.
      </div>
    );
  }
  // Pick a cell size that fits comfortably in a card; clamp [22, 48].
  const cell = Math.max(22, Math.min(48, Math.round(420 / Math.max(n, 1))));
  const labels = replayIndexes || matrix.map((_, i) => i);
  return (
    <div className="flex items-start gap-3">
      <div>
        <div
          className="grid gap-[2px]"
          style={{
            gridTemplateColumns: `28px repeat(${n}, ${cell}px)`,
            gridTemplateRows: `28px repeat(${n}, ${cell}px)`,
          }}
        >
          {/* corner */}
          <div />
          {labels.map((idx, j) => (
            <div
              key={`top-${j}`}
              className="grid place-items-center text-[10px] font-mono text-slate-500"
            >
              #{idx}
            </div>
          ))}
          {matrix.map((row, i) => (
            <React.Fragment key={`row-${i}`}>
              <div className="grid place-items-center text-[10px] font-mono text-slate-500">
                #{labels[i]}
              </div>
              {row.map((sim, j) => {
                const isDiag = i === j;
                const isMedoidRow = labels[i] === medoidIdx;
                const isMedoidCol = labels[j] === medoidIdx;
                return (
                  <div
                    key={`c-${i}-${j}`}
                    title={`#${labels[i]} ↔ #${labels[j]} — Jaccard ${sim.toFixed(2)}`}
                    className="rounded-[3px] grid place-items-center relative"
                    style={{
                      width: cell,
                      height: cell,
                      background: simHue(sim),
                      boxShadow:
                        isMedoidRow || isMedoidCol
                          ? "inset 0 0 0 1px rgba(250, 204, 21, 0.65)"
                          : isDiag
                          ? "inset 0 0 0 1px rgba(148,163,184,0.35)"
                          : undefined,
                    }}
                  >
                    {cell >= 28 ? (
                      <span
                        className="text-[10px] font-mono tabular-nums"
                        style={{ color: sim > 0.55 ? "#022c1c" : "#e2e8f0" }}
                      >
                        {sim.toFixed(2)}
                      </span>
                    ) : null}
                    {isDiag && cell < 28 ? (
                      <span className="text-[10px] text-slate-400">·</span>
                    ) : null}
                  </div>
                );
              })}
            </React.Fragment>
          ))}
        </div>
      </div>

      {/* Legend */}
      <div className="flex flex-col gap-1 ml-1 pt-7">
        <div className="text-[10px] uppercase tracking-widest text-slate-500 mb-1">Jaccard</div>
        <div
          className="w-3 h-32 rounded-sm"
          style={{
            background:
              "linear-gradient(180deg, hsl(125 80% 50%), hsl(60 78% 46%), hsl(0 78% 46%))",
          }}
        />
        <div className="flex flex-col justify-between text-[9px] font-mono text-slate-500 h-32 -mt-32">
          <span>1.0</span>
          <span>0.5</span>
          <span>0.0</span>
        </div>
        {medoidIdx != null ? (
          <div className="mt-3 flex items-center gap-1 text-[9px] text-amber-300">
            <Crown className="w-3 h-3" />
            medoid #{medoidIdx}
          </div>
        ) : null}
      </div>
    </div>
  );
};

// ─── Cluster columns ────────────────────────────────────────────────────────

const ClusterColumns = ({ clusters, samples, medoidIdx }) => {
  if (!clusters || clusters.length === 0) {
    return null;
  }
  const sampleByIdx = new Map(samples.map((s) => [s.replay_index, s]));
  return (
    <div
      className="grid gap-3"
      style={{
        gridTemplateColumns: `repeat(${Math.min(clusters.length, 4)}, minmax(180px, 1fr))`,
      }}
    >
      {clusters.map((c) => {
        const hue = clusterHue(c.id);
        return (
          <div
            key={c.id}
            className="rounded-lg border bg-slate-900/40 p-3"
            style={{
              borderColor: `${hue}55`,
              boxShadow: `inset 3px 0 0 ${hue}`,
            }}
          >
            <div className="flex items-center justify-between mb-2">
              <span
                className="text-[11px] uppercase tracking-widest font-bold"
                style={{ color: hue }}
              >
                Cluster {c.id}
              </span>
              <span className="text-[10px] text-slate-400 font-mono">
                {c.size} {c.size === 1 ? "reply" : "replies"}
              </span>
            </div>
            <ul className="space-y-1.5">
              {c.replay_indexes.map((idx) => {
                const s = sampleByIdx.get(idx);
                const isMedoid = idx === medoidIdx;
                return (
                  <li
                    key={idx}
                    className="flex items-center gap-2 px-2 py-1 rounded bg-slate-950/60 border border-slate-800/60"
                  >
                    <span
                      className="text-[10px] font-mono w-7 tabular-nums"
                      style={{ color: hue }}
                    >
                      #{idx}
                    </span>
                    <span className="text-[10px] text-slate-400 font-mono">
                      μ{s?.mean_sim != null ? s.mean_sim.toFixed(2) : "—"}
                    </span>
                    <span className="text-[10px] text-slate-500 font-mono">
                      · {s?.output_tokens ?? "—"}t
                    </span>
                    {isMedoid ? (
                      <Crown className="w-3 h-3 text-amber-300 ml-auto" />
                    ) : null}
                  </li>
                );
              })}
            </ul>
          </div>
        );
      })}
    </div>
  );
};

// ─── Per-replay card grid ──────────────────────────────────────────────────

const ReplayCard = ({ sample, medoidIdx, copyOne }) => {
  const [open, setOpen] = useState(false);
  const isMedoid = sample.replay_index === medoidIdx;
  const cHue = clusterHue(sample.cluster_id);
  const failed = sample.status !== "success" || !(sample.response || "").trim();
  const text = sample.response || "";
  const shown = open ? text : text.slice(0, 240);
  return (
    <div
      className="rounded-lg border bg-slate-900/40 p-3 transition-all"
      style={{
        borderColor: isMedoid ? "#fbbf2466" : `${cHue}44`,
        boxShadow: isMedoid
          ? `0 0 0 1px #fbbf2466, inset 3px 0 0 #fbbf24`
          : `inset 3px 0 0 ${cHue}aa`,
      }}
    >
      <div className="flex items-center gap-2 mb-2 flex-wrap">
        <span
          className="text-[11px] uppercase tracking-widest font-bold font-mono px-1.5 py-0.5 rounded"
          style={{ color: cHue, background: `${cHue}1a`, border: `1px solid ${cHue}55` }}
        >
          #{sample.replay_index}
        </span>
        <ClusterChip id={sample.cluster_id} small />
        <SimRing value={sample.mean_sim} size={36} />
        <span className="text-[10px] text-slate-400">μ-sim</span>
        {isMedoid ? (
          <span className="ml-auto inline-flex items-center gap-1 text-[10px] text-amber-300 bg-amber-950/40 border border-amber-900/50 px-1.5 py-0.5 rounded-full">
            <Crown className="w-3 h-3" /> medoid
          </span>
        ) : null}
      </div>
      <div className="grid grid-cols-3 gap-1.5 mb-2">
        <Tile label="Tokens" value={sample.output_tokens ?? "—"} hue="#94a3b8" />
        <Tile label="Latency" value={fmtNum(sample.latency, 2)} hue="#06b6d4" suffix="s" />
        <Tile label="Cost" value={fmtCost(sample.cost_usd)} hue="#a855f7" />
      </div>
      {failed ? (
        <div className="text-[11px] text-rose-300 flex items-center gap-1">
          <AlertTriangle className="w-3 h-3" />
          {sample.error || "no response"}
        </div>
      ) : (
        <>
          <div className="text-[12px] text-slate-300 whitespace-pre-wrap leading-snug">
            {shown}
            {text.length > 240 && !open ? "…" : null}
          </div>
          <div className="mt-2 flex items-center gap-2">
            {text.length > 240 ? (
              <button
                onClick={() => setOpen((v) => !v)}
                className="text-[10px] text-slate-400 hover:text-slate-200 inline-flex items-center gap-1"
              >
                {open ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
                {open ? "show less" : "show full"}
              </button>
            ) : null}
            <button
              onClick={() => copyOne(text, sample.replay_index)}
              className="text-[10px] text-slate-400 hover:text-slate-200 inline-flex items-center gap-1 ml-auto"
              title="Copy this response"
            >
              <Copy className="w-3 h-3" /> copy
            </button>
          </div>
        </>
      )}
    </div>
  );
};

// ─── Empty state ────────────────────────────────────────────────────────────

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

const SetupTab = ({ defaults, onCreate, onSeed, creating }) => {
  const [name, setName] = useState("Customer support — drift baseline");
  const [description, setDescription] = useState("");
  const [systemPrompt, setSystemPrompt] = useState(
    "You are a calm, concise customer support specialist for a small SaaS company. " +
      "Read the user's message, identify the issue, and reply with a two-sentence answer " +
      "followed by the next concrete step the user should take."
  );
  const [userPrompt, setUserPrompt] = useState(
    "I was double charged last month — there are two transactions for the same plan on June 3rd. " +
      "Can you sort it out?"
  );
  const [provider, setProvider] = useState("Anthropic");
  const [model, setModel] = useState("claude-haiku-4-5-20251001");
  const [temperature, setTemperature] = useState(
    defaults?.temperature?.default ?? 0.7
  );
  const [topP, setTopP] = useState(defaults?.top_p?.default ?? 1.0);
  const [nReplays, setNReplays] = useState(
    defaults?.n_replays?.default ?? 8
  );
  const [clusterThreshold, setClusterThreshold] = useState(
    defaults?.cluster_threshold?.default ?? 0.55
  );
  const [dryrun, setDryrun] = useState(true);

  // Keep model in sync with provider.
  useEffect(() => {
    const list = PROVIDER_MODELS[provider] || [];
    if (list.length && !list.includes(model)) setModel(list[0]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [provider]);

  const submit = async () => {
    const trimName = name.trim();
    if (!trimName) return toast.error("Name is required");
    if (!userPrompt.trim()) return toast.error("User prompt is required");
    if (!dryrun && (!provider || !model)) {
      return toast.error("Live mode needs a provider + model");
    }
    await onCreate({
      name: trimName,
      description,
      system_prompt: systemPrompt,
      user_prompt: userPrompt,
      candidate_provider: dryrun ? "" : provider,
      candidate_model: dryrun ? "" : model,
      temperature: Number(temperature),
      top_p: Number(topP),
      n_replays: Number(nReplays),
      cluster_threshold: Number(clusterThreshold),
      dryrun,
    });
  };

  return (
    <div className="space-y-4">
      <Card className="border-slate-800/80 bg-slate-950/60 overflow-hidden">
        <CardHeader className="pb-3 border-b border-slate-800/60 bg-gradient-to-r from-slate-950 via-slate-900/30 to-slate-950">
          <CardTitle className="text-base text-slate-200 flex items-center gap-2">
            <Beaker className="w-4 h-4 text-cyan-400" />
            New drift run
            <span className="text-slate-500 font-normal text-xs ml-2">
              — replay the same prompt N times, measure stability
            </span>
          </CardTitle>
        </CardHeader>
        <CardContent className="pt-5 space-y-5">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <Label className="text-slate-400 text-xs uppercase tracking-widest">
                Run name
              </Label>
              <Input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. v3 support prompt — drift baseline"
                className="bg-slate-900/60 border-slate-800 text-slate-100 mt-1"
              />
            </div>
            <div>
              <Label className="text-slate-400 text-xs uppercase tracking-widest">
                Description (optional)
              </Label>
              <Input
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="What are you checking?"
                className="bg-slate-900/60 border-slate-800 text-slate-100 mt-1"
              />
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <Label className="text-slate-400 text-xs uppercase tracking-widest">
                System prompt
              </Label>
              <Textarea
                rows={5}
                value={systemPrompt}
                onChange={(e) => setSystemPrompt(e.target.value)}
                className="bg-slate-900/60 border-slate-800 text-slate-100 mt-1 font-mono text-[12.5px]"
              />
            </div>
            <div>
              <Label className="text-slate-400 text-xs uppercase tracking-widest">
                User prompt (held identical across replays)
              </Label>
              <Textarea
                rows={5}
                value={userPrompt}
                onChange={(e) => setUserPrompt(e.target.value)}
                className="bg-slate-900/60 border-slate-800 text-slate-100 mt-1 font-mono text-[12.5px]"
              />
            </div>
          </div>

          {/* Provider / model + dryrun toggle */}
          <div className="rounded-lg border border-slate-800/60 bg-slate-900/30 p-3 space-y-3">
            <div className="flex items-center gap-2">
              <Switch
                checked={dryrun}
                onCheckedChange={setDryrun}
                id="dryrun"
                className="data-[state=checked]:bg-cyan-500"
              />
              <Label htmlFor="dryrun" className="text-slate-200 text-[13px] cursor-pointer">
                Dry-run mode
              </Label>
              <span className="text-[11px] text-slate-500">
                — no API keys, deterministic synthetic replies (great for the demo).
              </span>
            </div>
            {!dryrun && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div>
                  <Label className="text-slate-400 text-xs uppercase tracking-widest">
                    Provider
                  </Label>
                  <Select value={provider} onValueChange={setProvider}>
                    <SelectTrigger className="bg-slate-900/60 border-slate-800 text-slate-100 mt-1">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {Object.keys(PROVIDER_MODELS).map((p) => (
                        <SelectItem key={p} value={p}>{p}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label className="text-slate-400 text-xs uppercase tracking-widest">Model</Label>
                  <Select value={model} onValueChange={setModel}>
                    <SelectTrigger className="bg-slate-900/60 border-slate-800 text-slate-100 mt-1">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {(PROVIDER_MODELS[provider] || []).map((m) => (
                        <SelectItem key={m} value={m}>{m}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
            )}
          </div>

          {/* Sliders */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <SliderTile
              label="Replays"
              icon={Repeat}
              hue="#06b6d4"
              value={nReplays}
              onChange={(v) => setNReplays(v)}
              min={defaults?.n_replays?.min || 3}
              max={defaults?.n_replays?.max || 16}
              step={1}
              fmt={(v) => `${v}`}
            />
            <SliderTile
              label="Temperature"
              icon={Thermometer}
              hue="#f59e0b"
              value={temperature}
              onChange={setTemperature}
              min={defaults?.temperature?.min ?? 0}
              max={defaults?.temperature?.max ?? 2}
              step={defaults?.temperature?.step ?? 0.05}
              fmt={(v) => Number(v).toFixed(2)}
            />
            <SliderTile
              label="Top-p"
              icon={Target}
              hue="#a855f7"
              value={topP}
              onChange={setTopP}
              min={defaults?.top_p?.min ?? 0}
              max={defaults?.top_p?.max ?? 1}
              step={defaults?.top_p?.step ?? 0.05}
              fmt={(v) => Number(v).toFixed(2)}
            />
            <SliderTile
              label="Cluster τ"
              icon={Layers}
              hue="#22c55e"
              value={clusterThreshold}
              onChange={setClusterThreshold}
              min={defaults?.cluster_threshold?.min ?? 0.2}
              max={defaults?.cluster_threshold?.max ?? 0.95}
              step={defaults?.cluster_threshold?.step ?? 0.05}
              fmt={(v) => Number(v).toFixed(2)}
            />
          </div>

          <div className="flex items-center gap-2">
            <Button
              onClick={submit}
              disabled={creating}
              className="bg-gradient-to-r from-cyan-500 to-emerald-500 text-slate-950 font-semibold"
            >
              {creating ? (
                <><Zap className="w-3.5 h-3.5 mr-1.5 animate-pulse" /> running…</>
              ) : (
                <><Play className="w-3.5 h-3.5 mr-1.5" /> Run drift</>
              )}
            </Button>
            <Button
              variant="outline"
              onClick={onSeed}
              className="border-slate-700 text-slate-200 bg-slate-900/60 hover:bg-slate-800"
            >
              <Sparkles className="w-3.5 h-3.5 mr-1.5 text-cyan-400" /> Seed demo
            </Button>
            <span className="text-[11px] text-slate-500 ml-2">
              {dryrun
                ? "Dry-run will fabricate deterministic synthetic replies — fast and key-free."
                : `Live: ${nReplays} calls to ${provider}/${model}. This spends credits.`}
            </span>
          </div>
        </CardContent>
      </Card>

      <Card className="border-slate-800/80 bg-slate-950/60">
        <CardHeader className="pb-3 border-b border-slate-800/60">
          <CardTitle className="text-sm text-slate-200 flex items-center gap-2">
            <Wand2 className="w-4 h-4 text-fuchsia-400" />
            How Drift Lab scores stability
          </CardTitle>
        </CardHeader>
        <CardContent className="pt-4 text-[12.5px] text-slate-400 leading-relaxed">
          <p>
            Drift Lab fires the same prompt at the same model{" "}
            <span className="text-slate-200 font-mono">{nReplays}×</span> in
            parallel, then collapses the bag of responses into a composite{" "}
            <span className="text-slate-200">Stability Score (0–100)</span>{" "}
            blended from three independent axes:
          </p>
          <ul className="mt-2 space-y-1.5 pl-2">
            <li>
              <span className="text-cyan-300 font-mono">0.55 × Lexical</span> — mean
              pairwise Jaccard over 3-gram word-shingles. 100 = lexically
              identical, 0 = nothing in common.
            </li>
            <li>
              <span className="text-fuchsia-300 font-mono">0.30 × Length</span> —{" "}
              <span className="font-mono">100·(1 − clip(σ/μ, 0, 1))</span> over
              output token counts. Penalises models whose verbosity changes
              call-to-call.
            </li>
            <li>
              <span className="text-amber-300 font-mono">0.15 × Latency</span> —
              same CV-floor trick on wall-clock time. A model that spikes 5×
              sometimes burns user patience even when the words are fine.
            </li>
          </ul>
          <p className="mt-3">
            Replies are clustered single-link at{" "}
            <span className="text-slate-200 font-mono">τ = {clusterThreshold.toFixed(2)}</span>{" "}
            so the surface tells you how *many distinct answers* the model
            produces, not just how *similar on average* they are. The{" "}
            <span className="text-amber-300 inline-flex items-center gap-1"><Crown className="w-3 h-3" /> medoid</span> is the single
            reply with the highest mean similarity to all the others — your
            canonical "what a user actually sees" answer.
          </p>
          <p className="mt-3 flex items-center gap-2 flex-wrap">
            Bands:
            <BandChip band="Steady" />
            <BandChip band="Consistent" />
            <BandChip band="Drifty" />
            <BandChip band="Wild" />
          </p>
        </CardContent>
      </Card>
    </div>
  );
};

const SliderTile = ({ label, icon, hue, value, onChange, min, max, step, fmt }) => {
  const IconCmp = icon;
  return (
    <div
      className="rounded-lg border border-slate-800/60 bg-slate-900/40 p-3"
      style={{ boxShadow: `inset 0 -2px 0 ${hue}66` }}
    >
      <div className="flex items-center gap-1.5 mb-1.5">
        <IconCmp className="w-3.5 h-3.5" style={{ color: hue }} />
        <span className="text-[10px] uppercase tracking-widest text-slate-500">{label}</span>
        <span
          className="text-[13px] font-mono ml-auto tabular-nums"
          style={{ color: hue }}
        >
          {fmt(value)}
        </span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full"
        style={{ accentColor: hue }}
      />
    </div>
  );
};

// ─── Results tab ────────────────────────────────────────────────────────────

const ResultsTab = ({ drift, onRerun, onDelete, running, deleting }) => {
  const summary = drift.summary || {};
  const samples = useMemo(() => drift.samples || [], [drift.samples]);
  const matrix = summary.similarity_matrix || [];
  const clusters = summary.clusters || [];
  const medoidIdx = summary.medoid_replay_index ?? drift.medoid_index;

  const replayIndexes = useMemo(() => {
    return samples
      .filter((s) => s.status === "success" && (s.response || "").trim())
      .map((s) => s.replay_index);
  }, [samples]);

  const copyOne = useCallback((text, idx) => {
    navigator.clipboard?.writeText(text);
    toast.success(`Copied reply #${idx}`);
  }, []);

  const copyAll = () => {
    const blob = samples
      .map(
        (s) =>
          `--- replay #${s.replay_index} (cluster ${s.cluster_id}, μ-sim ${s.mean_sim ?? "—"}) ---\n${s.response || ""}`
      )
      .join("\n\n");
    navigator.clipboard?.writeText(blob);
    toast.success(`Copied ${samples.length} replies`);
  };

  const exportJson = () => {
    const blob = JSON.stringify({ drift, summary }, null, 2);
    const url = URL.createObjectURL(new Blob([blob], { type: "application/json" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = `drift_${(drift.name || "run").replace(/[^a-z0-9]+/gi, "_").toLowerCase()}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const headline = summary.headline || drift.summary?.headline || "";
  const advisory = summary.advisory || "";
  const band = drift.band || summary.band || "—";
  const variance = drift.variance_type || summary.variance_type || "—";
  const stability =
    summary.stability_score != null
      ? summary.stability_score
      : drift.stability_score;

  return (
    <div className="space-y-4">
      {/* Hero card */}
      <Card className="border-slate-800/80 bg-slate-950/70 overflow-hidden">
        <CardContent className="p-5">
          <div className="flex flex-wrap items-center gap-5">
            <StabilityRing
              value={stability}
              band={band}
              variance={variance}
            />
            <div className="flex-1 min-w-[280px]">
              <div className="flex items-center gap-2 flex-wrap">
                <h2 className="text-lg font-semibold text-slate-100">
                  {drift.name}
                </h2>
                <BandChip band={band} />
                <VarianceChip variance={variance} />
                {drift.dryrun ? (
                  <span className="text-[10px] uppercase tracking-widest bg-slate-800/70 text-slate-400 px-1.5 py-0.5 rounded">
                    dry-run
                  </span>
                ) : (
                  <span className="text-[10px] uppercase tracking-widest bg-cyan-900/50 text-cyan-300 px-1.5 py-0.5 rounded">
                    live
                  </span>
                )}
              </div>
              <p className="mt-2 text-[14px] text-slate-200 leading-snug">
                {headline}
              </p>
              {advisory ? (
                <p className="mt-2 text-[12.5px] text-slate-400 leading-snug italic flex items-start gap-1.5">
                  <TrendingUp
                    className="w-3.5 h-3.5 mt-0.5 shrink-0"
                    style={{ color: BAND_HUE[band] || "#94a3b8" }}
                  />
                  {advisory}
                </p>
              ) : null}
              {/* 3 sub-scores */}
              <div className="mt-3 space-y-1.5">
                <ScoreBar value={summary.lexical_score} label="Lexical" />
                <ScoreBar value={summary.length_score} label="Length" />
                <ScoreBar value={summary.latency_score} label="Latency" />
              </div>
            </div>
            <div className="flex flex-col gap-2">
              <Button
                size="sm"
                variant="outline"
                onClick={onRerun}
                disabled={running}
                className="border-slate-700 text-slate-200 bg-slate-900/60 hover:bg-slate-800"
              >
                <RotateCcw className="w-3.5 h-3.5 mr-1.5" />
                {running ? "running…" : "Re-run"}
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={copyAll}
                className="border-slate-700 text-slate-200 bg-slate-900/60 hover:bg-slate-800"
              >
                <Copy className="w-3.5 h-3.5 mr-1.5" /> Copy all
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={exportJson}
                className="border-slate-700 text-slate-200 bg-slate-900/60 hover:bg-slate-800"
              >
                <Wand2 className="w-3.5 h-3.5 mr-1.5" /> Export JSON
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={onDelete}
                disabled={deleting}
                className="border-rose-900/60 text-rose-300 hover:bg-rose-950/40"
              >
                <Trash2 className="w-3.5 h-3.5 mr-1.5" />
                Delete
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Vital signs strip */}
      <div className="grid grid-cols-2 md:grid-cols-6 gap-2">
        <Tile
          label="Replays"
          value={`${summary.n_success ?? 0}/${summary.n_samples ?? 0}`}
          hue="#06b6d4"
        />
        <Tile
          label="Clusters"
          value={summary.n_clusters ?? "—"}
          hue={
            summary.n_clusters === 1
              ? "#22c55e"
              : summary.n_clusters > 1
              ? "#f59e0b"
              : "#94a3b8"
          }
        />
        <Tile
          label="Mean sim"
          value={summary.mean_similarity != null ? summary.mean_similarity.toFixed(2) : "—"}
          hue={simHue(summary.mean_similarity ?? 0)}
        />
        <Tile
          label="Min sim"
          value={summary.min_similarity != null ? summary.min_similarity.toFixed(2) : "—"}
          hue={simHue(summary.min_similarity ?? 0)}
        />
        <Tile
          label="Length CV"
          value={summary.length_cv != null ? summary.length_cv.toFixed(2) : "—"}
          hue={
            summary.length_cv == null
              ? "#94a3b8"
              : summary.length_cv < 0.1
              ? "#22c55e"
              : summary.length_cv < 0.3
              ? "#84cc16"
              : summary.length_cv < 0.6
              ? "#f59e0b"
              : "#ef4444"
          }
        />
        <Tile label="Cost" value={fmtCost(drift.total_cost ?? summary.total_cost)} hue="#a855f7" />
      </div>

      {/* Heatmap + cluster columns side-by-side on wide */}
      <div className="grid grid-cols-1 xl:grid-cols-[1.05fr_1fr] gap-4">
        <Card className="border-slate-800/80 bg-slate-950/60">
          <CardHeader className="pb-3 border-b border-slate-800/60">
            <CardTitle className="text-sm text-slate-200 flex items-center gap-2">
              <Activity className="w-4 h-4 text-cyan-400" />
              Pairwise similarity
              <span className="text-slate-500 font-normal text-xs">
                — Jaccard over 3-gram word-shingles, every replay × every replay
              </span>
            </CardTitle>
          </CardHeader>
          <CardContent className="pt-4 overflow-auto">
            <Heatmap
              matrix={matrix}
              medoidIdx={medoidIdx}
              replayIndexes={replayIndexes}
            />
          </CardContent>
        </Card>

        <Card className="border-slate-800/80 bg-slate-950/60">
          <CardHeader className="pb-3 border-b border-slate-800/60">
            <CardTitle className="text-sm text-slate-200 flex items-center gap-2">
              <Layers className="w-4 h-4 text-emerald-400" />
              Clusters
              <span className="text-slate-500 font-normal text-xs">
                — single-link at τ = {drift.cluster_threshold?.toFixed(2) ?? "0.55"}
              </span>
            </CardTitle>
          </CardHeader>
          <CardContent className="pt-4">
            {clusters.length === 0 ? (
              <div className="text-sm text-slate-500 text-center py-6">
                No clusters — at least two successful replays required.
              </div>
            ) : (
              <ClusterColumns
                clusters={clusters}
                samples={samples}
                medoidIdx={medoidIdx}
              />
            )}
          </CardContent>
        </Card>
      </div>

      {/* Per-replay cards */}
      <Card className="border-slate-800/80 bg-slate-950/60">
        <CardHeader className="pb-3 border-b border-slate-800/60">
          <CardTitle className="text-sm text-slate-200 flex items-center gap-2">
            <Repeat className="w-4 h-4 text-fuchsia-400" />
            Per-replay responses
            <span className="text-slate-500 font-normal text-xs">
              — same prompt, {samples.length} times; medoid wears the crown
            </span>
          </CardTitle>
        </CardHeader>
        <CardContent className="pt-4">
          <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-3">
            {samples.map((s) => (
              <ReplayCard
                key={s.id}
                sample={s}
                medoidIdx={medoidIdx}
                copyOne={copyOne}
              />
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Run config foot */}
      <Card className="border-slate-800/80 bg-slate-950/60">
        <CardContent className="pt-4 grid grid-cols-2 md:grid-cols-5 gap-3 text-[12px] text-slate-400">
          <ConfigPill label="Model" value={drift.candidate_model || "(dry-run)"} />
          <ConfigPill label="Provider" value={drift.candidate_provider || "(dry-run)"} />
          <ConfigPill label="Temperature" value={fmtNum(drift.temperature, 2)} />
          <ConfigPill label="Top-p" value={fmtNum(drift.top_p, 2)} />
          <ConfigPill
            label="Duration"
            value={`${fmtNum(drift.duration ?? summary.duration, 2)}s`}
          />
        </CardContent>
      </Card>
    </div>
  );
};

const ConfigPill = ({ label, value }) => (
  <div className="rounded border border-slate-800/60 bg-slate-900/40 px-3 py-2">
    <div className="text-[10px] uppercase tracking-widest text-slate-500">{label}</div>
    <div className="text-[13px] text-slate-200 font-mono mt-0.5 truncate">{value}</div>
  </div>
);

// ─── Top stats strip ───────────────────────────────────────────────────────

const StatsStrip = ({ stats }) => (
  <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
    <Tile label="Runs" value={stats?.n_runs ?? 0} hue="#22d3ee" />
    <Tile
      label="Avg stability"
      value={stats?.avg_stability != null ? fmtNum(stats.avg_stability, 0) : "—"}
      hue={stabilityHue(stats?.avg_stability)}
    />
    <Tile
      label="Best stability"
      value={stats?.best_stability != null ? fmtNum(stats.best_stability, 0) : "—"}
      hue={stabilityHue(stats?.best_stability)}
    />
    <Tile
      label="Steady runs"
      value={(stats?.by_band || {})?.Steady ?? 0}
      hue={BAND_HUE.Steady}
    />
    <Tile
      label="Wild runs"
      value={(stats?.by_band || {})?.Wild ?? 0}
      hue={BAND_HUE.Wild}
    />
  </div>
);

// ─── Run rail ──────────────────────────────────────────────────────────────

const RunRail = ({ runs, selectedId, onSelect, onNew, query, onQuery }) => (
  <div className="space-y-3">
    <div className="flex items-center gap-2">
      <div className="relative flex-1">
        <Search className="w-3.5 h-3.5 text-slate-500 absolute left-2.5 top-2.5" />
        <Input
          value={query}
          onChange={(e) => onQuery(e.target.value)}
          placeholder="Search runs"
          className="bg-slate-900/60 border-slate-800 text-slate-100 pl-8 h-8 text-[13px]"
        />
      </div>
      <Button
        size="sm"
        onClick={onNew}
        className="h-8 bg-slate-100 text-slate-900 hover:bg-white"
        title="New drift run"
      >
        <Plus className="w-3.5 h-3.5" />
      </Button>
    </div>
    <ScrollArea className="h-[calc(100vh-280px)] min-h-[420px] pr-2">
      <ul className="space-y-2">
        {runs.length === 0 ? (
          <li className="text-center text-[12px] text-slate-500 py-8 px-2">
            No drift runs yet. Hit <span className="text-slate-300">+</span> or seed a demo.
          </li>
        ) : null}
        {runs.map((r) => {
          const sel = r.id === selectedId;
          const band = bandFor(r.stability_score);
          return (
            <li key={r.id}>
              <button
                onClick={() => onSelect(r.id)}
                className={`w-full text-left p-3 rounded-lg border transition-all ${
                  sel
                    ? "border-cyan-600/40 bg-cyan-950/20"
                    : "border-slate-800/60 bg-slate-900/40 hover:border-slate-700"
                }`}
                style={sel ? { boxShadow: `inset 3px 0 0 ${band.hue}` } : undefined}
              >
                <div className="flex items-start gap-3">
                  <MiniRing value={r.stability_score} />
                  <div className="flex-1 min-w-0">
                    <div className="text-[13px] font-medium text-slate-100 truncate">
                      {r.name}
                    </div>
                    <div className="mt-0.5 flex items-center gap-1.5 text-[10px] uppercase tracking-widest">
                      <span style={{ color: band.hue }}>{r.band || band.label}</span>
                      <span className="text-slate-600">·</span>
                      <span className="text-slate-500">{r.n_clusters ?? "—"} clusters</span>
                      <span className="text-slate-600">·</span>
                      <span className="text-slate-500">{fmtRel(r.updated_at)}</span>
                    </div>
                    <div className="mt-1 flex items-center gap-1 flex-wrap">
                      {r.variance_type ? (
                        <VarianceChip variance={r.variance_type} small />
                      ) : null}
                      <span className="text-[9px] uppercase tracking-widest text-slate-500">
                        T={fmtNum(r.temperature, 2)}
                      </span>
                      <span className="text-[9px] uppercase tracking-widest text-slate-500">
                        {r.n_replays}× replays
                      </span>
                      {r.dryrun ? (
                        <span className="text-[9px] uppercase tracking-widest bg-slate-800/70 text-slate-400 px-1 rounded">
                          dry
                        </span>
                      ) : (
                        <span className="text-[9px] uppercase tracking-widest bg-cyan-900/40 text-cyan-300 px-1 rounded">
                          live
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              </button>
            </li>
          );
        })}
      </ul>
    </ScrollArea>
  </div>
);

// ─── Main component ───────────────────────────────────────────────────────

const DriftLab = () => {
  const [runs, setRuns] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [stats, setStats] = useState(null);
  const [defaults, setDefaults] = useState(null);
  const [drift, setDrift] = useState(null);
  const [, setLoading] = useState(false);
  const [running, setRunning] = useState(false);
  const [creating, setCreating] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [tab, setTab] = useState("setup");
  const [query, setQuery] = useState("");

  const refresh = useCallback(
    async (preferDriftId = null) => {
      setLoading(true);
      try {
        const [defaultsRes, listRes, statsRes] = await Promise.all([
          ApiService.driftDefaults().catch(() => ({ defaults: null })),
          ApiService.listDrifts({ q: query || undefined, limit: 50 }),
          ApiService.driftStats(),
        ]);
        setDefaults(defaultsRes.defaults || null);
        setRuns(listRes.drifts || []);
        setStats(statsRes.stats || null);
        const list = listRes.drifts || [];
        const targetId =
          preferDriftId ||
          (selectedId && list.find((r) => r.id === selectedId)?.id) ||
          list[0]?.id ||
          null;
        if (targetId) {
          setSelectedId(targetId);
          const detail = await ApiService.getDrift(targetId);
          setDrift(detail.drift);
          setTab(detail.drift?.status === "complete" ? "results" : "setup");
        } else {
          setDrift(null);
          setTab("setup");
        }
      } catch (e) {
        toast.error(`Load failed: ${e.message}`);
      } finally {
        setLoading(false);
      }
    },
    [query, selectedId]
  );

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!selectedId) {
      setDrift(null);
      return;
    }
    let cancelled = false;
    ApiService.getDrift(selectedId)
      .then((res) => {
        if (cancelled) return;
        setDrift(res.drift);
        setTab(res.drift?.status === "complete" ? "results" : "setup");
      })
      .catch((e) => toast.error(`Drift load failed: ${e.message}`));
    return () => {
      cancelled = true;
    };
  }, [selectedId]);

  // Debounced query refresh.
  const qRef = useRef(null);
  useEffect(() => {
    if (qRef.current) clearTimeout(qRef.current);
    qRef.current = setTimeout(async () => {
      try {
        const res = await ApiService.listDrifts({ q: query || undefined, limit: 50 });
        setRuns(res.drifts || []);
      } catch {
        // soft fail
      }
    }, 200);
    return () => qRef.current && clearTimeout(qRef.current);
  }, [query]);

  const onSeed = async () => {
    try {
      const res = await ApiService.seedDrift();
      const did = res.drift?.id;
      toast.success("Seeded — running drift…");
      setSelectedId(did);
      await ApiService.runDrift(did, {});
      await refresh(did);
      setTab("results");
    } catch (e) {
      toast.error(`Seed failed: ${e.message}`);
    }
  };

  const onCreate = async (payload) => {
    setCreating(true);
    try {
      const res = await ApiService.createDrift(payload);
      const newDrift = res.drift;
      setSelectedId(newDrift.id);
      toast.success(`Created "${newDrift.name}" — running…`);
      setRunning(true);
      await ApiService.runDrift(newDrift.id, {
        confirm_live: !newDrift.dryrun,
      });
      await refresh(newDrift.id);
      setTab("results");
      toast.success("Drift run complete");
    } catch (e) {
      toast.error(`Run failed: ${e.message}`);
    } finally {
      setCreating(false);
      setRunning(false);
    }
  };

  const onRerun = async () => {
    if (!drift) return;
    setRunning(true);
    try {
      await ApiService.runDrift(drift.id, { confirm_live: !drift.dryrun });
      const res = await ApiService.getDrift(drift.id);
      setDrift(res.drift);
      const list = await ApiService.listDrifts({ q: query || undefined, limit: 50 });
      setRuns(list.drifts || []);
      const st = await ApiService.driftStats();
      setStats(st.stats || null);
      toast.success("Re-run complete");
    } catch (e) {
      toast.error(`Re-run failed: ${e.message}`);
    } finally {
      setRunning(false);
    }
  };

  const onDelete = async () => {
    if (!drift) return;
    if (!window.confirm(`Delete drift run "${drift.name}"? This cannot be undone.`)) return;
    setDeleting(true);
    try {
      await ApiService.deleteDrift(drift.id);
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
      <div
        className="rounded-2xl border border-slate-800/80 px-5 py-4 relative overflow-hidden"
        style={{
          background:
            "radial-gradient(ellipse at top left, rgba(6,182,212,0.12), transparent 55%), " +
            "radial-gradient(ellipse at bottom right, rgba(168,85,247,0.12), transparent 55%), " +
            "linear-gradient(180deg, #0c1424, #060914)",
        }}
      >
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-cyan-500/30 to-fuchsia-500/30 grid place-items-center border border-slate-800/60">
              <Waves className="w-5 h-5 text-slate-100" />
            </div>
            <div>
              <h1 className="text-xl font-semibold tracking-tight">
                Drift Lab
                <span className="ml-2 text-[10px] uppercase tracking-[0.3em] bg-gradient-to-r from-cyan-500 via-fuchsia-500 to-amber-500 text-slate-950 px-1.5 py-0.5 rounded font-bold align-middle">
                  new
                </span>
              </h1>
              <p className="text-xs text-slate-400 max-w-2xl mt-0.5">
                Fire the same prompt at the same model N times in parallel.
                Measure how non-deterministic the output really is — lexical,
                length, and latency drift, plus the cluster count and the
                canonical medoid answer.
              </p>
            </div>
          </div>
          <StatsStrip stats={stats} />
        </div>
      </div>

      {/* Tabs + body */}
      <div className="grid grid-cols-1 lg:grid-cols-[320px_1fr] gap-4">
        <Card className="border-slate-800/80 bg-slate-950/60 p-3">
          <RunRail
            runs={runs}
            selectedId={selectedId}
            onSelect={(id) => {
              setSelectedId(id);
              setTab("results");
            }}
            onNew={() => {
              setSelectedId(null);
              setDrift(null);
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
              disabled={!drift || drift.status !== "complete"}
              className={`px-3 py-1.5 rounded-lg text-[13px] font-medium border ${
                tab === "results"
                  ? "bg-slate-100 text-slate-900 border-slate-100"
                  : "bg-slate-900/60 text-slate-300 border-slate-800 hover:border-slate-700 disabled:opacity-40 disabled:cursor-not-allowed"
              }`}
            >
              <Activity className="w-3.5 h-3.5 inline mr-1.5" />
              Results
              {drift?.stability_score != null ? (
                <span
                  className="ml-1.5 text-[10px] px-1.5 py-0.5 rounded-full font-mono"
                  style={{
                    color: stabilityHue(drift.stability_score),
                    background: `${stabilityHue(drift.stability_score)}1a`,
                  }}
                >
                  {Math.round(drift.stability_score)}
                </span>
              ) : null}
            </button>
            {running && (
              <div className="ml-auto flex items-center gap-2 text-[11px] text-cyan-300">
                <Zap className="w-3 h-3 animate-pulse" />
                running replays…
              </div>
            )}
          </div>

          {tab === "setup" ? (
            <SetupTab
              defaults={defaults}
              onCreate={onCreate}
              onSeed={onSeed}
              creating={creating}
            />
          ) : drift && drift.status === "complete" ? (
            <ResultsTab
              drift={drift}
              onRerun={onRerun}
              onDelete={onDelete}
              running={running}
              deleting={deleting}
            />
          ) : drift && drift.status === "running" ? (
            <EmptyState
              icon={Zap}
              title="Running replays…"
              body="The drift batch is currently in flight. Results will appear here when it finishes."
            />
          ) : drift ? (
            <EmptyState
              icon={Play}
              title="Drift not yet run"
              body="Press Re-run to fire the replay batch and score stability."
              action={
                <Button
                  size="sm"
                  onClick={onRerun}
                  className="bg-gradient-to-r from-cyan-500 to-emerald-500 text-slate-950"
                >
                  <Play className="w-3.5 h-3.5 mr-1.5" /> Run drift
                </Button>
              }
            />
          ) : (
            <EmptyState
              icon={Waves}
              title="No drift run selected"
              body="Pick a run from the rail, or seed the demo to see Drift Lab populated with a sample customer-support batch."
              action={
                <Button
                  size="sm"
                  onClick={onSeed}
                  className="bg-gradient-to-r from-cyan-500 to-fuchsia-500 text-slate-950"
                >
                  <Sparkles className="w-3.5 h-3.5 mr-1.5" /> Seed demo
                </Button>
              }
            />
          )}
        </div>
      </div>
    </div>
  );
};

export default DriftLab;
