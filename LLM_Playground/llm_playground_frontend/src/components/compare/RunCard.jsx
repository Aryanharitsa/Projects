import React from "react";
import { X, Copy, Crown, Zap, AlertTriangle, Loader2 } from "lucide-react";
import { formatUsd } from "@/lib/pricing";
import { toast } from "sonner";

const PROVIDER_ACCENT = {
  OpenAI:    "from-emerald-400 to-teal-500",
  Anthropic: "from-orange-400 to-amber-500",
  Google:    "from-sky-400  to-indigo-500",
  August:    "from-fuchsia-400 to-pink-500",
};

export default function RunCard({
  index,
  spec,
  modelsByProvider,
  result,
  isLoading,
  isCheapest,
  isFastest,
  maxCost,
  maxLatency,
  onChange,
  onRemove,
  canRemove,
}) {
  const accent = PROVIDER_ACCENT[spec.provider] || "from-indigo-400 to-violet-500";
  const status = result?.status;

  const copy = () => {
    if (!result?.content) return;
    navigator.clipboard.writeText(result.content);
    toast.success("Copied response");
  };

  // Bar widths (0..1) for cost & latency, relative to the max across all runs.
  const costFrac = result && maxCost
    ? Math.min(1, (result.cost?.total_cost_usd || 0) / maxCost)
    : 0;
  const latFrac = result && maxLatency
    ? Math.min(1, (result.latency_sec || 0) / maxLatency)
    : 0;

  return (
    <div className="flex flex-col rounded-2xl border border-white/10 bg-white/[0.03] backdrop-blur-sm overflow-hidden shadow-[0_4px_24px_-8px_rgba(0,0,0,0.5)] transition-colors hover:border-white/20">
      {/* header */}
      <div className="flex items-center gap-2 px-4 py-3 border-b border-white/10">
        <span
          className={`h-2.5 w-2.5 rounded-full bg-gradient-to-br ${accent} shadow-[0_0_8px_currentColor]`}
        />
        <select
          value={spec.provider}
          onChange={(e) => onChange({ ...spec, provider: e.target.value, model: "" })}
          className="bg-transparent text-sm font-medium text-white/90 outline-none border-none cursor-pointer"
        >
          {Object.keys(modelsByProvider).map((p) => (
            <option key={p} value={p} className="bg-[#0b0c1a]">{p}</option>
          ))}
        </select>

        <select
          value={spec.model}
          onChange={(e) => onChange({ ...spec, model: e.target.value })}
          className="ml-1 flex-1 bg-transparent text-xs text-white/70 outline-none border-none cursor-pointer truncate"
        >
          <option value="" className="bg-[#0b0c1a]">Select model…</option>
          {(modelsByProvider[spec.provider] || []).map((m) => (
            <option key={m} value={m} className="bg-[#0b0c1a]">{m}</option>
          ))}
        </select>

        <div className="flex items-center gap-1">
          {isCheapest && (
            <span
              title="Cheapest successful run"
              className="inline-flex items-center gap-1 rounded-full bg-emerald-500/15 text-emerald-300 text-[10px] px-2 py-0.5 border border-emerald-400/30"
            >
              <Crown className="h-3 w-3" /> cheapest
            </span>
          )}
          {isFastest && (
            <span
              title="Fastest successful run"
              className="inline-flex items-center gap-1 rounded-full bg-sky-500/15 text-sky-300 text-[10px] px-2 py-0.5 border border-sky-400/30"
            >
              <Zap className="h-3 w-3" /> fastest
            </span>
          )}
          {canRemove && (
            <button
              onClick={onRemove}
              className="ml-1 rounded-md p-1 text-white/40 hover:text-white/90 hover:bg-white/10 transition-colors"
              title="Remove run"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          )}
        </div>
      </div>

      {/* params row */}
      <div className="flex items-center gap-3 px-4 py-2 border-b border-white/5 text-[11px] text-white/60">
        <label className="flex items-center gap-1">
          temp
          <input
            type="number" min={0} max={2} step={0.1}
            value={spec.params.temperature}
            onChange={(e) => onChange({
              ...spec,
              params: { ...spec.params, temperature: Number(e.target.value) },
            })}
            className="w-12 bg-white/5 border border-white/10 rounded px-1 py-0.5 text-white/80"
          />
        </label>
        <label className="flex items-center gap-1">
          max
          <input
            type="number" min={32} max={8192} step={32}
            value={spec.params.max_tokens}
            onChange={(e) => onChange({
              ...spec,
              params: { ...spec.params, max_tokens: Number(e.target.value) },
            })}
            className="w-16 bg-white/5 border border-white/10 rounded px-1 py-0.5 text-white/80"
          />
        </label>
      </div>

      {/* body */}
      <div className="relative flex-1 min-h-[220px] p-4 text-sm leading-relaxed text-white/85 whitespace-pre-wrap overflow-auto font-[450]">
        {isLoading && (
          <div className="absolute inset-0 grid place-items-center bg-[#0b0c1a]/40 backdrop-blur-[1px]">
            <div className="flex items-center gap-2 text-white/70 text-xs">
              <Loader2 className="h-4 w-4 animate-spin" />
              thinking…
            </div>
          </div>
        )}
        {!isLoading && status === "error" && (
          <div className="flex items-start gap-2 text-red-300">
            <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" />
            <div>
              <div className="text-xs uppercase tracking-wider text-red-300/80 font-semibold">
                Request failed
              </div>
              <div className="text-xs text-red-200/80 mt-1">
                {result?.error || "Unknown error"}
              </div>
            </div>
          </div>
        )}
        {!isLoading && status === "success" && (
          <div className="text-white/90">{result.content}</div>
        )}
        {!isLoading && !result && (
          <div className="text-white/30 text-xs italic">
            No run yet. Hit <span className="text-white/70">Run All</span>.
          </div>
        )}
      </div>

      {/* metrics */}
      <div className="grid grid-cols-3 gap-px bg-white/5 border-t border-white/10 text-[11px]">
        <Metric label="tokens" value={result ? result.total_tokens : "—"} sub={
          result ? `in ${result.input_tokens} · out ${result.output_tokens}` : ""
        } />
        <Metric
          label="latency"
          value={result ? `${result.latency_sec.toFixed(2)}s` : "—"}
          bar={latFrac} barColor="from-sky-400 to-cyan-400"
        />
        <Metric
          label="cost"
          value={result ? formatUsd(result.cost.total_cost_usd) : "—"}
          bar={costFrac} barColor="from-emerald-400 to-teal-400"
        />
      </div>

      <div className="flex items-center justify-between px-4 py-2 bg-white/[0.02] text-[10px] text-white/40">
        <span className="truncate">
          {result?.model_version || spec.model || "no model selected"}
        </span>
        {result?.content && (
          <button
            onClick={copy}
            className="inline-flex items-center gap-1 hover:text-white/80 transition-colors"
          >
            <Copy className="h-3 w-3" /> copy
          </button>
        )}
      </div>
    </div>
  );
}

function Metric({ label, value, sub, bar, barColor = "from-white/40 to-white/20" }) {
  return (
    <div className="relative bg-[#0b0c1a] px-3 py-2">
      <div className="text-[9px] uppercase tracking-wider text-white/40">
        {label}
      </div>
      <div className="text-white/90 text-sm font-semibold tabular-nums">
        {value}
      </div>
      {sub && <div className="text-[10px] text-white/40 mt-0.5">{sub}</div>}
      {bar != null && (
        <div className="absolute left-3 right-3 bottom-1 h-0.5 bg-white/5 rounded overflow-hidden">
          <div
            className={`h-full rounded bg-gradient-to-r ${barColor}`}
            style={{ width: `${Math.max(4, bar * 100)}%` }}
          />
        </div>
      )}
    </div>
  );
}
