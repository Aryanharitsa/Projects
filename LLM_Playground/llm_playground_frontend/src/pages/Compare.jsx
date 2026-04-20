import React, { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import {
  Plus, Play, Download, Upload, Trash2, Gauge, DollarSign, Clock, Sparkles,
} from "lucide-react";
import ApiService from "@/services/api";
import RunCard from "@/components/compare/RunCard";
import { estimateCost, formatUsd } from "@/lib/pricing";

const DEFAULT_PROVIDERS = ["OpenAI", "Anthropic", "Google", "August"];

const SEED_RUNS = [
  { provider: "OpenAI",    model: "gpt-4o-mini",
    params: { temperature: 0.7, max_tokens: 600 } },
  { provider: "Anthropic", model: "claude-3-5-haiku-20241022",
    params: { temperature: 0.7, max_tokens: 600 } },
  { provider: "Google",    model: "gemini-1.5-flash",
    params: { temperature: 0.7, max_tokens: 600 } },
];

const EXAMPLE_PROMPTS = [
  "Explain how transformer self-attention works to a 2nd-year CS student in under 120 words.",
  "Rewrite this as a crisp product-launch tweet:\n\n'We added side-by-side LLM comparison with cost tracking.'",
  "Write 3 different JSON-only function signatures for a tool that books flights.",
];

export default function Compare() {
  const [systemPrompt, setSystemPrompt] = useState(
    "You are a concise, accurate assistant. Be direct."
  );
  const [userPrompt, setUserPrompt]   = useState(EXAMPLE_PROMPTS[0]);
  const [runs, setRuns]               = useState(SEED_RUNS);
  const [results, setResults]         = useState([]);
  const [summary, setSummary]         = useState(null);
  const [loading, setLoading]         = useState(false);
  const [modelsByProvider, setModelsByProvider] = useState(
    () => Object.fromEntries(DEFAULT_PROVIDERS.map((p) => [p, []]))
  );

  // Prefetch models for all providers once so the dropdowns are populated.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const next = { ...modelsByProvider };
      await Promise.all(
        DEFAULT_PROVIDERS.map(async (p) => {
          try {
            next[p] = await ApiService.getModels(p);
          } catch {
            next[p] = [];
          }
        })
      );
      if (!cancelled) setModelsByProvider(next);
    })();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const updateRun = (i, next) =>
    setRuns((prev) => prev.map((r, idx) => (idx === i ? next : r)));

  const addRun = () => {
    if (runs.length >= 6) {
      toast.error("Max 6 panels per comparison");
      return;
    }
    setRuns((prev) => [
      ...prev,
      { provider: "OpenAI", model: "gpt-4o-mini",
        params: { temperature: 0.7, max_tokens: 600 } },
    ]);
  };

  const removeRun = (i) =>
    setRuns((prev) => prev.filter((_, idx) => idx !== i));

  const runAll = async () => {
    if (!userPrompt.trim()) {
      toast.error("Enter a prompt first");
      return;
    }
    if (runs.some((r) => !r.model)) {
      toast.error("Pick a model for every panel");
      return;
    }
    setLoading(true);
    setResults([]);
    setSummary(null);
    try {
      const payload = {
        system_prompt: systemPrompt,
        messages: [{ role: "user", content: userPrompt, enabled: true }],
        runs,
      };
      const out = await ApiService.compareRun(payload);
      if (!out.success) throw new Error(out.error || "Compare failed");
      setResults(out.results || []);
      setSummary(out.summary || null);
      toast.success(
        `Ran ${out.results.length} models · ${out.summary?.wall_clock_sec?.toFixed(2)}s wall clock`
      );
    } catch (err) {
      toast.error(`Error: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const exportJson = () => {
    if (!results.length) {
      toast.error("Nothing to export yet");
      return;
    }
    const blob = new Blob(
      [JSON.stringify({
        system_prompt: systemPrompt,
        user_prompt: userPrompt,
        runs, results, summary,
        exported_at: new Date().toISOString(),
      }, null, 2)],
      { type: "application/json" }
    );
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `llm-compare-${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const clearAll = () => {
    setResults([]);
    setSummary(null);
  };

  const maxCost = useMemo(
    () => Math.max(0.00001,
      ...results.map((r) => r.cost?.total_cost_usd || 0)),
    [results]
  );
  const maxLatency = useMemo(
    () => Math.max(0.01,
      ...results.map((r) => r.latency_sec || 0)),
    [results]
  );

  // Estimate total cost live before running (based on default ~300 output tok).
  const estTotalUsd = useMemo(() => {
    return runs.reduce((s, r) => {
      const { total_cost_usd } =
        estimateCost(r.provider, r.model, 60, r.params.max_tokens || 600);
      return s + total_cost_usd;
    }, 0);
  }, [runs]);

  return (
    <div className="mx-auto max-w-[1600px] px-6 py-8 space-y-6">
      {/* hero */}
      <section className="rounded-3xl border border-white/10 bg-gradient-to-br from-indigo-500/10 via-fuchsia-500/5 to-transparent p-8 backdrop-blur-sm relative overflow-hidden">
        <div
          aria-hidden
          className="absolute -top-20 -right-20 h-60 w-60 rounded-full bg-fuchsia-500/20 blur-3xl"
        />
        <div className="flex items-center gap-2 text-xs uppercase tracking-[0.2em] text-white/50">
          <Sparkles className="h-3.5 w-3.5" />
          Compare Mode
        </div>
        <h1 className="mt-2 text-3xl sm:text-4xl font-semibold tracking-tight">
          One prompt. Every model.
          <span className="bg-gradient-to-r from-indigo-300 via-fuchsia-300 to-rose-300 bg-clip-text text-transparent">
            &nbsp;Side by side.
          </span>
        </h1>
        <p className="mt-2 text-white/60 max-w-2xl text-sm">
          Fan out the same prompt to OpenAI, Anthropic, Google and your
          custom August stack in parallel. See the winner on quality,
          the winner on latency, and the winner on cost — all at once.
        </p>

        {/* prompt row */}
        <div className="mt-6 grid grid-cols-1 lg:grid-cols-[1fr,1.6fr] gap-4">
          <div className="rounded-xl border border-white/10 bg-black/20 p-3">
            <div className="text-[10px] uppercase tracking-wider text-white/40 mb-1">
              System prompt
            </div>
            <textarea
              value={systemPrompt}
              onChange={(e) => setSystemPrompt(e.target.value)}
              rows={4}
              placeholder="You are a helpful assistant…"
              className="w-full resize-none bg-transparent text-sm text-white/90 outline-none placeholder:text-white/30"
            />
          </div>
          <div className="rounded-xl border border-white/10 bg-black/20 p-3">
            <div className="flex items-center justify-between mb-1">
              <div className="text-[10px] uppercase tracking-wider text-white/40">
                User prompt
              </div>
              <div className="flex gap-1">
                {EXAMPLE_PROMPTS.map((p, i) => (
                  <button
                    key={i}
                    onClick={() => setUserPrompt(p)}
                    className="text-[10px] rounded-full border border-white/10 px-2 py-0.5 text-white/60 hover:text-white hover:border-white/30 transition-colors"
                    title={p}
                  >
                    example {i + 1}
                  </button>
                ))}
              </div>
            </div>
            <textarea
              value={userPrompt}
              onChange={(e) => setUserPrompt(e.target.value)}
              rows={4}
              placeholder="Ask anything…"
              className="w-full resize-none bg-transparent text-sm text-white/90 outline-none placeholder:text-white/30"
            />
          </div>
        </div>

        {/* action bar */}
        <div className="mt-5 flex flex-wrap items-center gap-2">
          <button
            onClick={runAll}
            disabled={loading}
            className="inline-flex items-center gap-2 rounded-full bg-gradient-to-r from-indigo-500 to-fuchsia-500 px-5 py-2 text-sm font-semibold text-white shadow-lg shadow-fuchsia-500/30 hover:shadow-fuchsia-500/50 disabled:opacity-60 disabled:cursor-not-allowed transition-shadow"
          >
            <Play className="h-4 w-4" />
            {loading ? "Running…" : `Run All (${runs.length})`}
          </button>
          <button
            onClick={addRun}
            className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/5 px-4 py-2 text-sm text-white/80 hover:bg-white/10 transition-colors"
          >
            <Plus className="h-4 w-4" />
            Add model
          </button>
          <button
            onClick={exportJson}
            className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/5 px-4 py-2 text-sm text-white/80 hover:bg-white/10 transition-colors"
          >
            <Download className="h-4 w-4" />
            Export JSON
          </button>
          <button
            onClick={clearAll}
            className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/5 px-4 py-2 text-sm text-white/80 hover:bg-white/10 transition-colors"
          >
            <Trash2 className="h-4 w-4" />
            Clear results
          </button>
          <div className="ml-auto text-[11px] text-white/50 tabular-nums">
            est. run cost ≈ <span className="text-white/80">{formatUsd(estTotalUsd)}</span>
          </div>
        </div>
      </section>

      {/* summary stats */}
      {summary && (
        <section className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <StatCard
            icon={Gauge} label="Runs"
            value={`${summary.success_count}/${summary.run_count}`}
            sub="successful"
          />
          <StatCard
            icon={Clock} label="Wall clock"
            value={`${summary.wall_clock_sec?.toFixed(2)}s`}
            sub="parallel"
          />
          <StatCard
            icon={DollarSign} label="Total cost"
            value={formatUsd(summary.total_cost_usd)}
            sub="this comparison"
          />
          <StatCard
            icon={Sparkles} label="Winner (cost)"
            value={
              summary.cheapest_index != null
                ? results[summary.cheapest_index]?.model ?? "—"
                : "—"
            }
            sub={
              summary.fastest_index != null
                ? `fastest: ${results[summary.fastest_index]?.model}`
                : ""
            }
          />
        </section>
      )}

      {/* grid of panels */}
      <section
        className={`grid gap-4 ${
          runs.length === 1 ? "grid-cols-1"
            : runs.length === 2 ? "grid-cols-1 md:grid-cols-2"
            : runs.length === 3 ? "grid-cols-1 md:grid-cols-2 xl:grid-cols-3"
            : "grid-cols-1 md:grid-cols-2 xl:grid-cols-3"
        }`}
      >
        {runs.map((spec, i) => (
          <RunCard
            key={i}
            index={i}
            spec={spec}
            modelsByProvider={modelsByProvider}
            result={results[i]}
            isLoading={loading}
            isCheapest={summary?.cheapest_index === i}
            isFastest={summary?.fastest_index === i}
            maxCost={maxCost}
            maxLatency={maxLatency}
            onChange={(next) => updateRun(i, next)}
            onRemove={() => removeRun(i)}
            canRemove={runs.length > 1}
          />
        ))}
      </section>
    </div>
  );
}

function StatCard({ icon: Icon, label, value, sub }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-4 backdrop-blur-sm">
      <div className="flex items-center gap-2 text-[10px] uppercase tracking-wider text-white/40">
        <Icon className="h-3.5 w-3.5" />
        {label}
      </div>
      <div className="mt-1 text-xl font-semibold tabular-nums text-white">
        {value}
      </div>
      {sub && <div className="text-[11px] text-white/50 mt-0.5">{sub}</div>}
    </div>
  );
}
