import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  EyeClosed,
  ShieldCheck,
  Copy,
  Download,
  ClipboardCheck,
  Play,
  Sparkles,
  AlertTriangle,
  Fingerprint,
  Percent,
  DollarSign,
  ArrowRight,
  Beaker,
  Package,
  FileWarning,
  Scale,
  Braces,
  RefreshCw,
} from "lucide-react";
import ApiService from "../services/api";

// ═════════════════════════════════════════════════════════════════════════════
// Palette
// ═════════════════════════════════════════════════════════════════════════════
const PRESET_HUE = {
  strict:     { hue: "#10b981", text: "text-emerald-200", ring: "ring-emerald-500/40", border: "border-emerald-500/50", bg: "bg-emerald-500/10", chip: "bg-emerald-500/15 text-emerald-200 border-emerald-500/40", label: "Strict" },
  balanced:   { hue: "#38bdf8", text: "text-sky-200",     ring: "ring-sky-500/40",     border: "border-sky-500/50",     bg: "bg-sky-500/10",     chip: "bg-sky-500/15 text-sky-200 border-sky-500/40",         label: "Balanced" },
  permissive: { hue: "#f59e0b", text: "text-amber-200",   ring: "ring-amber-500/40",   border: "border-amber-500/50",   bg: "bg-amber-500/10",   chip: "bg-amber-500/15 text-amber-200 border-amber-500/40",   label: "Permissive" },
};

// Entity → tone
const ENTITY_HUE = {
  EMAIL:            "sky",
  PHONE:            "cyan",
  SSN:              "rose",
  CREDIT_CARD:      "amber",
  IBAN:             "orange",
  IPV4:             "emerald",
  UUID:             "teal",
  API_KEY_OPENAI:   "violet",
  API_KEY_ANTHROPIC:"fuchsia",
  API_KEY_AWS:      "yellow",
  API_KEY_GENERIC:  "purple",
  JWT:              "indigo",
  URL_WITH_TOKEN:   "lime",
  DOB:              "pink",
  MAC_ADDR:         "slate",
  GEO_COORD:        "blue",
  PERSON_NAME:      "stone",
};
const _TW = {
  sky:      "bg-sky-500/15 text-sky-200 border-sky-500/40",
  cyan:     "bg-cyan-500/15 text-cyan-200 border-cyan-500/40",
  rose:     "bg-rose-500/15 text-rose-200 border-rose-500/40",
  amber:    "bg-amber-500/15 text-amber-200 border-amber-500/40",
  orange:   "bg-orange-500/15 text-orange-200 border-orange-500/40",
  emerald:  "bg-emerald-500/15 text-emerald-200 border-emerald-500/40",
  teal:     "bg-teal-500/15 text-teal-200 border-teal-500/40",
  violet:   "bg-violet-500/15 text-violet-200 border-violet-500/40",
  fuchsia:  "bg-fuchsia-500/15 text-fuchsia-200 border-fuchsia-500/40",
  yellow:   "bg-yellow-500/15 text-yellow-200 border-yellow-500/40",
  purple:   "bg-purple-500/15 text-purple-200 border-purple-500/40",
  indigo:   "bg-indigo-500/15 text-indigo-200 border-indigo-500/40",
  lime:     "bg-lime-500/15 text-lime-200 border-lime-500/40",
  pink:     "bg-pink-500/15 text-pink-200 border-pink-500/40",
  slate:    "bg-slate-500/15 text-slate-200 border-slate-500/40",
  blue:     "bg-blue-500/15 text-blue-200 border-blue-500/40",
  stone:    "bg-stone-500/15 text-stone-200 border-stone-500/40",
};
const chipTone = (eid) => _TW[ENTITY_HUE[eid] || "sky"];

const STRATEGY_HUE = {
  mask:         "text-slate-200 bg-slate-500/15 border-slate-500/40",
  tag:          "text-sky-200 bg-sky-500/15 border-sky-500/40",
  hash:         "text-violet-200 bg-violet-500/15 border-violet-500/40",
  pseudonymize: "text-emerald-200 bg-emerald-500/15 border-emerald-500/40",
  drop:         "text-rose-200 bg-rose-500/15 border-rose-500/40",
};

const BAND_HUE = {
  clean:    { hue: "#22c55e", label: "Clean",    text: "text-emerald-200" },
  low:      { hue: "#84cc16", label: "Low",      text: "text-lime-200" },
  moderate: { hue: "#f59e0b", label: "Moderate", text: "text-amber-200" },
  high:     { hue: "#f97316", label: "High",     text: "text-orange-200" },
  critical: { hue: "#ef4444", label: "Critical", text: "text-rose-200" },
};

const VERDICT_HUE = {
  clean:          "text-emerald-200 bg-emerald-500/15 border-emerald-500/40",
  compliant:      "text-emerald-200 bg-emerald-500/15 border-emerald-500/40",
  borderline:     "text-amber-200 bg-amber-500/15 border-amber-500/40",
  non_compliant:  "text-rose-200 bg-rose-500/15 border-rose-500/40",
};

// ═════════════════════════════════════════════════════════════════════════════
// Fmt helpers
// ═════════════════════════════════════════════════════════════════════════════
const fmtInt = (n) => `${(n || 0).toLocaleString()}`;
const fmtPct = (n, d = 1) => `${(n ?? 0).toFixed(d)}%`;
const fmtUSD = (n) => `$${(n || 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
const clamp = (n, lo, hi) => Math.max(lo, Math.min(hi, n));
const short = (s, n = 24) => (s && s.length > n ? s.slice(0, n) + "…" : s || "");

// ═════════════════════════════════════════════════════════════════════════════
// Reusable atoms
// ═════════════════════════════════════════════════════════════════════════════
function ScoreRing({ pct = 0, size = 176, stroke = 14, hue = "#38bdf8", label, subLabel = "exposure" }) {
  const dashLen = 2 * Math.PI * ((size - stroke) / 2);
  const clamped = clamp(pct, 0, 100);
  const filled = (clamped / 100) * dashLen;
  return (
    <div className="relative" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size/2} cy={size/2} r={(size-stroke)/2} fill="none"
          stroke="rgba(255,255,255,0.06)" strokeWidth={stroke} />
        <circle cx={size/2} cy={size/2} r={(size-stroke)/2} fill="none"
          stroke={hue} strokeWidth={stroke}
          strokeDasharray={`${filled} ${dashLen}`} strokeLinecap="round"
          style={{ transition: "stroke-dasharray 400ms cubic-bezier(0.22,0.61,0.36,1)" }} />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <div className="text-4xl font-bold text-white tabular-nums">{label ?? clamped.toFixed(0)}</div>
        <div className="text-[10px] uppercase tracking-widest text-white/50 mt-1">{subLabel}</div>
      </div>
    </div>
  );
}

function StatTile({ icon: Icon, label, value, hint, hue = "text-white/85" }) {
  return (
    <Card className="bg-white/[0.03] border-white/10">
      <CardContent className="p-3">
        <div className="flex items-center gap-2 text-[10px] uppercase tracking-widest text-white/50">
          {Icon && <Icon className="w-3.5 h-3.5" />}
          {label}
        </div>
        <div className={`text-xl font-bold tabular-nums mt-1 ${hue}`}>{value}</div>
        {hint && <div className="text-[11px] text-white/50 mt-0.5">{hint}</div>}
      </CardContent>
    </Card>
  );
}

function EntityChip({ eid, count, dim = false }) {
  return (
    <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded border text-[10px] uppercase tracking-wider font-semibold ${chipTone(eid)} ${dim ? "opacity-70" : ""}`}>
      {eid.replace(/_/g, " ")}
      {typeof count === "number" && <span className="text-white/70 tabular-nums">×{count}</span>}
    </span>
  );
}

function StrategyChip({ strat }) {
  return (
    <span className={`px-1.5 py-0.5 rounded border text-[10px] uppercase tracking-wider font-semibold ${STRATEGY_HUE[strat] || "text-white/60 bg-white/[0.04] border-white/10"}`}>
      {strat}
    </span>
  );
}

// ═════════════════════════════════════════════════════════════════════════════
// Highlighted-scan renderer — <mark>s every entity span in the input text
// ═════════════════════════════════════════════════════════════════════════════
function HighlightedText({ text, spans }) {
  if (!text) return <div className="text-white/40 text-sm">Empty.</div>;
  const parts = [];
  let cursor = 0;
  const sorted = [...(spans || [])].sort((a, b) => a.start - b.start);
  for (const s of sorted) {
    if (s.start >= cursor) {
      parts.push(<span key={`t-${cursor}`}>{text.slice(cursor, s.start)}</span>);
      parts.push(
        <mark key={`m-${s.start}`} className={`px-1 py-0.5 rounded font-mono border ${chipTone(s.entity_id)}`}
              title={`${s.entity_id} (sev ${s.severity})`}>
          {text.slice(s.start, s.end)}
        </mark>
      );
      cursor = s.end;
    }
  }
  parts.push(<span key={`tail`}>{text.slice(cursor)}</span>);
  return <div className="whitespace-pre-wrap break-words text-sm text-white/90 leading-relaxed">{parts}</div>;
}

// ═════════════════════════════════════════════════════════════════════════════
// Preset recommendation card
// ═════════════════════════════════════════════════════════════════════════════
function RecCard({ rec, active, onApply }) {
  const tone = PRESET_HUE[rec.preset] || PRESET_HUE.balanced;
  const sim = rec.simulation || {};
  const stats = rec.stats || {};
  return (
    <button onClick={onApply}
      className={`text-left w-full rounded-xl border p-4 transition
        ${active ? `${tone.border} ${tone.bg} ring-1 ${tone.ring}` : "bg-white/[0.03] border-white/10 hover:border-white/20"}`}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className={`px-2 py-0.5 rounded border text-[10px] uppercase tracking-widest ${tone.chip}`}>{tone.label}</span>
          <span className="text-white/40 font-mono text-[10px]">{rec.policy_id?.slice(0, 8)}</span>
        </div>
        <div className={`text-xl font-bold tabular-nums ${tone.text}`}>{fmtPct(sim.reduction_pct, 1)}</div>
      </div>
      <div className="grid grid-cols-3 gap-2 mt-3">
        <div>
          <div className="text-[9px] uppercase tracking-widest text-white/40">Post-egress $</div>
          <div className="text-sm font-semibold text-white/90 tabular-nums">{fmtUSD(sim.breach_exposure_post_usd)}</div>
        </div>
        <div>
          <div className="text-[9px] uppercase tracking-widest text-white/40">Utility keep</div>
          <div className="text-sm font-semibold text-white/90 tabular-nums">{fmtPct((1 - (stats.utility_loss || 0)) * 100, 0)}</div>
        </div>
        <div>
          <div className="text-[9px] uppercase tracking-widest text-white/40">Reversible</div>
          <div className="text-sm font-semibold text-white/90 tabular-nums">{fmtPct(stats.reversibility_pct || 0, 0)}</div>
        </div>
      </div>
      <div className="flex flex-wrap gap-1 mt-3">
        {(Object.entries(sim.compliance_verdict || {})).map(([fam, verdict]) => (
          <span key={fam} className={`px-1.5 py-0.5 rounded border text-[9px] uppercase tracking-wider ${VERDICT_HUE[verdict] || "text-white/60 bg-white/[0.03] border-white/10"}`}>
            {fam} · {verdict?.replace("_", " ")}
          </span>
        ))}
      </div>
    </button>
  );
}

// ═════════════════════════════════════════════════════════════════════════════
// Main studio
// ═════════════════════════════════════════════════════════════════════════════
export default function CurtainStudio() {
  const [seed, setSeed] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Live scanner state
  const [inputText, setInputText] = useState("");
  const [scanResult, setScanResult] = useState(null);

  // Policy state
  const [selectedPreset, setSelectedPreset] = useState("balanced");
  const [policy, setPolicy] = useState(null);        // per-entity strategy map
  const [monthlyReq, setMonthlyReq] = useState(100_000);

  // Redaction / rehydration state
  const [redactResult, setRedactResult] = useState(null);
  const [mockOutput, setMockOutput] = useState("");
  const [outputScan, setOutputScan] = useState(null);

  // Compiled policy state
  const [compiled, setCompiled] = useState(null);
  const [compileMd, setCompileMd] = useState("");

  // ─── Bootstrap: pull seed on mount ─────────────────────────────────────────
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        setLoading(true);
        const s = await ApiService.curtainSeed();
        if (cancelled) return;
        setSeed(s.seed);
        setInputText(s.seed.workload[0]);
        setScanResult(s.seed.input_scans[0]);
        setPolicy(s.seed.policy_presets.balanced);
        setRedactResult(s.seed.sample_redaction);
        setMockOutput(
          "Thanks — the ticket is on its way. If you need help you can also " +
          "email newton@apple.com (this address wasn't in your message)."
        );
        setOutputScan(s.seed.sample_output_scan);
        setCompiled(s.seed.sample_compile);
      } catch (e) {
        console.error(e);
        setError(e.message || String(e));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  // ─── Live scanner (debounced) ──────────────────────────────────────────────
  const scanDebounce = useRef(null);
  useEffect(() => {
    if (!inputText) { setScanResult(null); return; }
    if (scanDebounce.current) clearTimeout(scanDebounce.current);
    scanDebounce.current = setTimeout(async () => {
      try {
        const r = await ApiService.curtainScan(inputText);
        setScanResult(r.scan);
      } catch (e) { console.error(e); }
    }, 220);
    return () => scanDebounce.current && clearTimeout(scanDebounce.current);
  }, [inputText]);

  // ─── Auto-redact on policy or input change ─────────────────────────────────
  useEffect(() => {
    if (!inputText || !policy) return;
    let cancelled = false;
    (async () => {
      try {
        const r = await ApiService.curtainRedact({ text: inputText, policy });
        if (cancelled) return;
        setRedactResult(r.result);
      } catch (e) { console.error(e); }
    })();
    return () => { cancelled = true; };
  }, [inputText, policy]);

  // ─── Output scan on output change ──────────────────────────────────────────
  useEffect(() => {
    if (!mockOutput) { setOutputScan(null); return; }
    let cancelled = false;
    (async () => {
      try {
        const r = await ApiService.curtainOutputScan({
          output: mockOutput,
          input_scan: scanResult,
        });
        if (cancelled) return;
        setOutputScan(r.result);
      } catch (e) { console.error(e); }
    })();
    return () => { cancelled = true; };
  }, [mockOutput, scanResult]);

  // ─── Apply preset ──────────────────────────────────────────────────────────
  const applyPreset = useCallback((name) => {
    if (!seed) return;
    const p = seed.policy_presets[name];
    if (!p) return;
    setSelectedPreset(name);
    setPolicy({ ...p });
  }, [seed]);

  const cycleStrategy = useCallback((eid) => {
    if (!policy) return;
    const strategies = ["tag", "mask", "hash", "pseudonymize", "drop"];
    const cur = policy[eid] || "tag";
    const idx = strategies.indexOf(cur);
    const next = strategies[(idx + 1) % strategies.length];
    setPolicy({ ...policy, [eid]: next });
    setSelectedPreset("custom");
  }, [policy]);

  // ─── Simulation (workload-scaled forecast) ─────────────────────────────────
  const [sim, setSim] = useState(null);
  useEffect(() => {
    if (!policy || !seed) return;
    let cancelled = false;
    (async () => {
      try {
        const r = await ApiService.curtainSimulate({
          workload_id: "default",
          policy,
          monthly_requests: monthlyReq,
        });
        if (cancelled) return;
        setSim(r.simulation);
      } catch (e) { console.error(e); }
    })();
    return () => { cancelled = true; };
  }, [policy, monthlyReq, seed]);

  // ─── Recommendations (workload-scaled) ─────────────────────────────────────
  const [recs, setRecs] = useState(null);
  useEffect(() => {
    if (!seed) return;
    let cancelled = false;
    (async () => {
      try {
        const r = await ApiService.curtainRecommend({
          workload_id: "default",
          monthly_requests: monthlyReq,
        });
        if (cancelled) return;
        setRecs(r.recommendations);
      } catch (e) { console.error(e); }
    })();
    return () => { cancelled = true; };
  }, [seed, monthlyReq]);

  // ─── Compile-on-demand ─────────────────────────────────────────────────────
  const runCompile = useCallback(async () => {
    if (!policy) return;
    try {
      const r = await ApiService.curtainCompile({ policy, sample_text: inputText });
      setCompiled(r.compiled);
      setCompileMd(r.markdown);
    } catch (e) { console.error(e); }
  }, [policy, inputText]);
  useEffect(() => { if (policy) runCompile(); }, [policy, runCompile]);

  // ─── Rehydrate mock button ─────────────────────────────────────────────────
  const rehydrateAndInject = useCallback(async () => {
    if (!redactResult) return;
    // Simulate a canned response referencing the tagged input, then rehydrate.
    const canned = `Order [UUID_1] is being processed. We will contact [EMAIL_1] at [PHONE_1] shortly.`;
    try {
      const r = await ApiService.curtainRehydrate({
        text: canned,
        mapping: redactResult.mapping || [],
      });
      setMockOutput(r.rehydrated);
    } catch (e) { console.error(e); }
  }, [redactResult]);

  const copyToClipboard = useCallback((text) => {
    navigator.clipboard.writeText(text);
  }, []);

  const downloadJson = useCallback(() => {
    if (!compiled) return;
    const blob = new Blob([JSON.stringify(compiled, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = `curtain-policy-${compiled.policy_id}.json`;
    document.body.appendChild(a); a.click(); a.remove();
    URL.revokeObjectURL(url);
  }, [compiled]);

  const downloadMd = useCallback(() => {
    if (!compileMd) return;
    const blob = new Blob([compileMd], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = `curtain-policy-${compiled?.policy_id || "custom"}.md`;
    document.body.appendChild(a); a.click(); a.remove();
    URL.revokeObjectURL(url);
  }, [compileMd, compiled]);

  // ─── Derived ───────────────────────────────────────────────────────────────
  const band = BAND_HUE[scanResult?.exposure_band || "clean"];
  const ringPct = scanResult?.exposure_score || 0;
  const activePreset = selectedPreset === "custom" ? null : PRESET_HUE[selectedPreset];

  if (loading) {
    return (
      <Card className="bg-slate-950 border-white/10">
        <CardContent className="p-12 text-center">
          <RefreshCw className="w-8 h-8 text-white/40 mx-auto animate-spin" />
          <div className="text-white/60 mt-3 text-sm">Booting Curtain…</div>
        </CardContent>
      </Card>
    );
  }
  if (error) {
    return (
      <Card className="bg-slate-950 border-rose-500/40">
        <CardContent className="p-6 text-rose-200">
          <div className="flex items-center gap-2 font-semibold mb-2"><AlertTriangle className="w-4 h-4" /> Curtain failed to boot</div>
          <div className="text-sm text-white/70 font-mono">{error}</div>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-5 pb-8">
      {/* ── Hero ─────────────────────────────────────────────────────────── */}
      <Card className="bg-gradient-to-br from-emerald-950/60 via-sky-950/40 to-fuchsia-950/60 border-white/10 overflow-hidden relative">
        <div className="absolute inset-0 pointer-events-none opacity-40"
          style={{ background: "radial-gradient(80% 60% at 25% 15%, rgba(16,185,129,0.30), transparent), radial-gradient(60% 40% at 90% 100%, rgba(217,70,239,0.25), transparent)" }} />
        <CardContent className="p-6 relative">
          <div className="grid grid-cols-1 lg:grid-cols-[auto_1fr] gap-6 items-center">
            <div className="flex justify-center">
              <ScoreRing pct={ringPct} hue={band.hue} label={ringPct.toFixed(0)} subLabel="exposure" />
            </div>
            <div>
              <div className="flex items-center gap-2 text-[11px] uppercase tracking-widest text-white/60">
                <EyeClosed className="w-4 h-4 text-emerald-300" />
                Curtain — PII / Secret Redaction & Egress Policy Studio
                <span className="text-white/30 font-mono">{seed?.engine_version}</span>
              </div>
              <div className="text-2xl font-bold text-white mt-1">
                Every character your model sees, priced and policied.
              </div>
              <div className="text-white/70 text-sm mt-2 max-w-3xl">
                Two-sided scanner over 14 entity families. Live redaction under a shippable per-entity policy, output-side leak detector,
                and a compiler that emits a byte-stable JSON blob with a deterministic policy id.
              </div>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-4">
                <StatTile icon={Fingerprint} label="Entities found" value={fmtInt(scanResult?.total_hits || 0)} hue={band.text} hint={`${scanResult?.unique_entities || 0} unique types`} />
                <StatTile icon={ShieldCheck} label="Compliance verdict"
                  value={<span className={band.text}>{band.label}</span>}
                  hint={sim ? `${fmtPct(sim.reduction_pct, 1)} egress reduction` : "—"} />
                <StatTile icon={DollarSign} label="Post-redaction $ / mo"
                  value={sim ? fmtUSD(sim.breach_exposure_post_usd) : "—"}
                  hint={sim ? `was ${fmtUSD(sim.breach_exposure_pre_usd)}` : ""} />
                <StatTile icon={FileWarning} label="Output leaks"
                  value={fmtInt(outputScan?.leak_count || 0)}
                  hue={outputScan?.leak_count > 0 ? "text-rose-200" : "text-emerald-200"}
                  hint={outputScan?.leak_band || "clean"} />
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* ── Rec cards ────────────────────────────────────────────────────── */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        {(recs || []).map((r) => (
          <RecCard key={r.preset} rec={r} active={selectedPreset === r.preset} onApply={() => applyPreset(r.preset)} />
        ))}
      </div>

      {/* ── Main dashboard: 2 col layout ────────────────────────────────── */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-5">
        {/* LEFT — live scanner + input redaction */}
        <Card className="bg-slate-950 border-white/10">
          <CardHeader className="pb-2">
            <CardTitle className="text-white/85 text-sm flex items-center gap-2">
              <Beaker className="w-4 h-4 text-sky-300" /> Live scanner · input side
              <span className="text-[10px] text-white/40 uppercase tracking-widest">
                {scanResult ? `${scanResult.total_hits} hit${scanResult.total_hits === 1 ? "" : "s"} · band ${band.label}` : "empty"}
              </span>
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div>
              <Label className="text-[11px] text-white/60 uppercase tracking-widest">Paste any prompt (seed pre-filled)</Label>
              <Textarea rows={5} value={inputText} onChange={(e) => setInputText(e.target.value)}
                className="mt-1 bg-white/[0.03] border-white/10 text-white/90 font-mono text-xs" />
              <div className="flex flex-wrap gap-1 mt-2">
                {(seed?.workload || []).map((w, i) => (
                  <button key={i}
                    onClick={() => setInputText(w)}
                    className="px-1.5 py-0.5 rounded border text-[10px] uppercase tracking-wider font-semibold bg-white/[0.03] text-white/50 border-white/10 hover:text-white/80 hover:border-white/20">
                    seed #{i+1}
                  </button>
                ))}
              </div>
            </div>
            <Separator className="bg-white/10" />
            <div>
              <div className="text-[11px] text-white/60 uppercase tracking-widest mb-1">Highlighted spans</div>
              <div className="p-3 rounded bg-white/[0.02] border border-white/10 max-h-40 overflow-auto">
                <HighlightedText text={inputText} spans={scanResult?.spans || []} />
              </div>
            </div>
            <div>
              <div className="text-[11px] text-white/60 uppercase tracking-widest mb-1">Entity histogram</div>
              <div className="flex flex-wrap gap-1">
                {Object.entries(scanResult?.histogram || {}).length === 0 ? (
                  <span className="text-white/40 text-xs">No entities in this prompt.</span>
                ) : (
                  Object.entries(scanResult?.histogram || {}).map(([eid, c]) => (
                    <EntityChip key={eid} eid={eid} count={c} />
                  ))
                )}
              </div>
            </div>
            <Separator className="bg-white/10" />
            <div>
              <div className="flex items-center justify-between mb-1">
                <div className="text-[11px] text-white/60 uppercase tracking-widest">Redacted (what your provider sees)</div>
                <Button size="sm" variant="ghost" className="h-6 px-2 text-white/60 hover:text-white/90"
                  onClick={() => copyToClipboard(redactResult?.redacted || "")}>
                  <Copy className="w-3 h-3 mr-1" /> copy
                </Button>
              </div>
              <div className="p-3 rounded bg-white/[0.02] border border-white/10 max-h-40 overflow-auto text-xs font-mono text-white/90 whitespace-pre-wrap break-words">
                {redactResult?.redacted || "—"}
              </div>
              <div className="text-[10px] text-white/40 mt-1 flex items-center gap-2">
                <ArrowRight className="w-3 h-3" />
                {(redactResult?.mapping?.length || 0)} reversible placeholder{redactResult?.mapping?.length === 1 ? "" : "s"} ·
                Δ {redactResult?.delta_chars || 0} chars
              </div>
            </div>
          </CardContent>
        </Card>

        {/* RIGHT — policy composer */}
        <Card className="bg-slate-950 border-white/10">
          <CardHeader className="pb-2">
            <CardTitle className="text-white/85 text-sm flex items-center gap-2">
              <Scale className="w-4 h-4 text-emerald-300" /> Policy composer
              {activePreset && <span className={`px-1.5 py-0.5 rounded border text-[10px] uppercase tracking-widest ${activePreset.chip}`}>{activePreset.label}</span>}
              {selectedPreset === "custom" && <span className="px-1.5 py-0.5 rounded border text-[10px] uppercase tracking-widest bg-white/[0.05] text-white/70 border-white/20">Custom</span>}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div>
              <div className="text-[11px] text-white/60 uppercase tracking-widest mb-2">Click a strategy chip to cycle</div>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-white/40 text-[10px] uppercase tracking-widest">
                      <th className="text-left py-1">Entity</th>
                      <th className="text-left py-1">Family</th>
                      <th className="text-right py-1">Sev</th>
                      <th className="text-right py-1">$/breach</th>
                      <th className="text-right py-1">Strategy</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(seed?.entities || []).map((e) => (
                      <tr key={e.id} className="border-t border-white/[0.05] hover:bg-white/[0.02]">
                        <td className="py-1 pr-2"><EntityChip eid={e.id} /></td>
                        <td className="py-1 text-white/60 text-[10px] uppercase tracking-widest">{e.family}</td>
                        <td className="py-1 text-right text-white/70 tabular-nums">{e.severity}</td>
                        <td className="py-1 text-right text-white/70 tabular-nums">${e.breach_cost_usd.toFixed(2)}</td>
                        <td className="py-1 text-right">
                          <button onClick={() => cycleStrategy(e.id)}>
                            <StrategyChip strat={policy?.[e.id] || "tag"} />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
            <Separator className="bg-white/10" />
            <div>
              <div className="text-[11px] text-white/60 uppercase tracking-widest mb-2">Monthly traffic assumption</div>
              <div className="flex items-center gap-3">
                <Slider min={1_000} max={10_000_000} step={1_000} value={[monthlyReq]}
                  onValueChange={(v) => setMonthlyReq(v[0])} className="flex-1" />
                <div className="text-xs text-white/80 tabular-nums w-28 text-right">{fmtInt(monthlyReq)} req/mo</div>
              </div>
            </div>
            {sim && (
              <div className="grid grid-cols-3 gap-2">
                <StatTile icon={DollarSign} label="Pre-redact $/mo"   value={fmtUSD(sim.breach_exposure_pre_usd)} />
                <StatTile icon={ShieldCheck} label="Post-redact $/mo" value={fmtUSD(sim.breach_exposure_post_usd)} hue="text-emerald-200" />
                <StatTile icon={Percent}    label="Reduction"          value={fmtPct(sim.reduction_pct, 1)} hue="text-sky-200" />
              </div>
            )}
            <div className="flex flex-wrap gap-1">
              {sim && Object.entries(sim.compliance_verdict || {}).map(([fam, verdict]) => (
                <span key={fam} className={`px-2 py-0.5 rounded border text-[10px] uppercase tracking-widest ${VERDICT_HUE[verdict] || "text-white/60 bg-white/[0.03] border-white/10"}`}>
                  {fam} · {verdict?.replace("_", " ")}
                </span>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* ── Output-side scanner + rehydration ─────────────────────────────── */}
      <Card className="bg-slate-950 border-white/10">
        <CardHeader className="pb-2">
          <CardTitle className="text-white/85 text-sm flex items-center gap-2">
            <FileWarning className={`w-4 h-4 ${outputScan?.leak_count > 0 ? "text-rose-300" : "text-emerald-300"}`} />
            Output-side leak detector · post-model
            {outputScan && (
              <span className={`px-1.5 py-0.5 rounded border text-[10px] uppercase tracking-widest ${VERDICT_HUE[outputScan.leak_count > 0 ? "non_compliant" : "compliant"]}`}>
                {outputScan.leak_count} leak{outputScan.leak_count === 1 ? "" : "s"}
              </span>
            )}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex items-center gap-2">
            <Button size="sm" variant="secondary"
              className="bg-white/[0.05] text-white/85 border border-white/10 hover:bg-white/10"
              onClick={rehydrateAndInject}>
              <Play className="w-3 h-3 mr-1" /> Simulate model response + rehydrate
            </Button>
            <div className="text-[10px] text-white/40 uppercase tracking-widest">
              paste any response text below to re-scan
            </div>
          </div>
          <Textarea rows={3} value={mockOutput} onChange={(e) => setMockOutput(e.target.value)}
            className="mt-1 bg-white/[0.03] border-white/10 text-white/90 font-mono text-xs" />
          {outputScan && (
            <div className="p-3 rounded bg-white/[0.02] border border-white/10 max-h-40 overflow-auto">
              <HighlightedText text={mockOutput} spans={outputScan.spans || []} />
            </div>
          )}
          {outputScan && outputScan.leaks && outputScan.leaks.length > 0 && (
            <div className="rounded border border-rose-500/30 bg-rose-500/[0.06] p-3">
              <div className="text-[11px] text-rose-200 uppercase tracking-widest font-semibold mb-1 flex items-center gap-1">
                <AlertTriangle className="w-3.5 h-3.5" /> Leak candidates — not present in input
              </div>
              <div className="flex flex-wrap gap-2">
                {outputScan.leaks.map((l, i) => (
                  <div key={i} className="flex items-center gap-1">
                    <EntityChip eid={l.entity_id} />
                    <span className="text-white/70 font-mono text-xs">{short(l.raw, 40)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* ── Compiled policy panel ─────────────────────────────────────────── */}
      <Card className="bg-slate-950 border-white/10">
        <CardHeader className="pb-2">
          <CardTitle className="text-white/85 text-sm flex items-center gap-2">
            <Braces className="w-4 h-4 text-fuchsia-300" /> Compiled policy
            {compiled && (
              <span className="px-1.5 py-0.5 rounded border text-[10px] uppercase tracking-widest bg-fuchsia-500/15 text-fuchsia-200 border-fuchsia-500/40 font-mono">
                policy_id · {compiled.policy_id}
              </span>
            )}
            <div className="ml-auto flex items-center gap-1">
              <Button size="sm" variant="ghost" className="h-7 px-2 text-white/60 hover:text-white/90"
                onClick={() => copyToClipboard(JSON.stringify(compiled, null, 2))}>
                <Copy className="w-3 h-3 mr-1" /> copy json
              </Button>
              <Button size="sm" variant="ghost" className="h-7 px-2 text-white/60 hover:text-white/90"
                onClick={() => copyToClipboard(compileMd)}>
                <ClipboardCheck className="w-3 h-3 mr-1" /> copy md
              </Button>
              <Button size="sm" variant="ghost" className="h-7 px-2 text-white/60 hover:text-white/90"
                onClick={downloadJson}>
                <Download className="w-3 h-3 mr-1" /> json
              </Button>
              <Button size="sm" variant="ghost" className="h-7 px-2 text-white/60 hover:text-white/90"
                onClick={downloadMd}>
                <Download className="w-3 h-3 mr-1" /> md
              </Button>
            </div>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
            <StatTile icon={Percent} label="Reversibility" value={fmtPct(compiled?.stats?.reversibility_pct || 0, 0)} hue="text-emerald-200" />
            <StatTile icon={Package} label="Utility loss (sev-weighted)" value={((compiled?.stats?.utility_loss || 0) * 100).toFixed(1) + "%"} hue="text-sky-200" />
            <StatTile icon={Sparkles} label="Entities configured" value={Object.keys(compiled?.policy || {}).length} />
          </div>
          <Separator className="my-3 bg-white/10" />
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
            <div>
              <div className="text-[11px] text-white/60 uppercase tracking-widest mb-1">Per-strategy count</div>
              <div className="flex flex-wrap gap-1">
                {Object.entries(compiled?.stats?.strategy_histogram || {}).map(([s, c]) => (
                  <span key={s} className={`px-1.5 py-0.5 rounded border text-[10px] uppercase tracking-widest ${STRATEGY_HUE[s]}`}>
                    {s} × {c}
                  </span>
                ))}
              </div>
            </div>
            <div>
              <div className="text-[11px] text-white/60 uppercase tracking-widest mb-1">Family coverage</div>
              <div className="flex flex-wrap gap-1">
                {Object.entries(compiled?.stats?.family_coverage || {}).map(([f, cov]) => (
                  <span key={f} className="px-1.5 py-0.5 rounded border text-[10px] uppercase tracking-widest bg-white/[0.03] text-white/70 border-white/10">
                    {f} · {cov.protected}/{cov.total}
                  </span>
                ))}
              </div>
            </div>
          </div>
          <Separator className="my-3 bg-white/10" />
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
            <div>
              <div className="text-[11px] text-white/60 uppercase tracking-widest mb-1">Compiled JSON</div>
              <ScrollArea className="h-56 rounded border border-white/10 bg-black/40">
                <pre className="p-3 text-[11px] text-white/80 font-mono whitespace-pre">
{JSON.stringify(compiled, null, 2)}
                </pre>
              </ScrollArea>
            </div>
            <div>
              <div className="text-[11px] text-white/60 uppercase tracking-widest mb-1">Markdown summary</div>
              <ScrollArea className="h-56 rounded border border-white/10 bg-black/40">
                <pre className="p-3 text-[11px] text-white/80 font-mono whitespace-pre-wrap">
{compileMd}
                </pre>
              </ScrollArea>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* ── Formula footnote ─────────────────────────────────────────────── */}
      <Card className="bg-white/[0.02] border-white/10">
        <CardContent className="p-4">
          <div className="text-[10px] uppercase tracking-widest text-white/40 mb-1">Formula footnote</div>
          <div className="text-xs text-white/70 leading-relaxed">
            <b>exposure_score</b> = min(100, 10 · Σ<sub>e</sub> sev(e) · (1 − 0.55<sup>n(e)</sup>)) —
            saturating per-entity, sev-weighted. &nbsp;
            <b>residual leak</b> per strategy: drop 0 · mask 0 · hash 0.05 · pseudonymize 0.05 · tag 0.25. &nbsp;
            <b>breach_exposure_post</b> = Σ<sub>e</sub> count(e) · $breach(e) · residual(strategy<sub>e</sub>). &nbsp;
            <b>policy_id</b> = SHA-256(sorted policy + engine + salt)<sub>[:16]</sub> — same policy → same id, forever.
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
