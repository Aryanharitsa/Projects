"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import DistributionOverlay from "../../components/DistributionOverlay";
import DriftRadar from "../../components/DriftRadar";
import DriftTimeline from "../../components/DriftTimeline";
import {
  DriftReport,
  DriftResponse,
  DriftSample,
  DriftVerdict,
  Tx,
  getDriftSample,
  runDrift,
} from "../../lib/api";

const VERDICT_RANK: Record<DriftVerdict, number> = {
  stable: 0,
  mild: 1,
  drifting: 2,
  erratic: 3,
  transformed: 4,
};

const HOUR_LABELS = Array.from({ length: 24 }, (_, i) => `${i}`);
const DOW_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

function parseCsv(text: string): Tx[] {
  const lines = text.trim().split(/\r?\n/);
  if (lines.length < 2) return [];
  const cols = lines[0].split(",").map((c) => c.trim());
  return lines
    .slice(1)
    .filter(Boolean)
    .map((line) => {
      const vals = line.split(",");
      const o: any = {};
      cols.forEach((c, i) => (o[c] = (vals[i] ?? "").trim()));
      o.amount = Number(o.amount);
      return o as Tx;
    });
}

function toCsv(txs: Tx[]): string {
  const cols = [
    "account_id",
    "counterparty",
    "amount",
    "timestamp",
    "channel",
    "geo",
    "subject_name",
    "counterparty_name",
  ];
  const head = cols.join(",");
  const rows = txs.map((t) =>
    cols.map((c) => (t as any)[c] ?? "").join(",")
  );
  return [head, ...rows].join("\n");
}

function fmtPct(x: number): string {
  return `${(x * 100).toFixed(1)}%`;
}

function isoToShort(iso: string | null): string {
  if (!iso) return "—";
  return iso.slice(0, 10);
}

export default function DriftPage() {
  const [csv, setCsv] = useState("");
  const [response, setResponse] = useState<DriftResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [scope, setScope] = useState<"portfolio" | "single">("portfolio");
  const [accountId, setAccountId] = useState<string>("");
  const [baselineFraction, setBaselineFraction] = useState<number>(0.7);
  const [splitAt, setSplitAt] = useState<string>("");
  const [useFraction, setUseFraction] = useState<boolean>(true);
  const [activeIdx, setActiveIdx] = useState<number>(0);
  const [sampleNote, setSampleNote] = useState<string>("");

  const loadSample = useCallback(async () => {
    try {
      const s: DriftSample = await getDriftSample();
      setCsv(toCsv(s.transactions));
      setAccountId(s.highlight_account);
      setSplitAt(s.recommended_split_at);
      setUseFraction(false);
      setScope("portfolio");
      setSampleNote(s.note);
      setErr(null);
    } catch (e: any) {
      setErr(e?.message || "failed to load sample");
    }
  }, []);

  // Auto-load sample on first visit so the page is never empty
  useEffect(() => {
    if (!csv) void loadSample();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const run = useCallback(async () => {
    setBusy(true);
    setErr(null);
    setResponse(null);
    setActiveIdx(0);
    try {
      const txs = parseCsv(csv);
      if (!txs.length) throw new Error("empty transactions CSV");
      const opts: any = {};
      if (scope === "single" && accountId) opts.account_id = accountId.trim();
      if (useFraction) opts.baseline_fraction = baselineFraction;
      else if (splitAt) opts.split_at = splitAt;
      const out = await runDrift(txs, opts);
      setResponse(out);
    } catch (e: any) {
      setErr(e?.message || "drift analysis failed");
    } finally {
      setBusy(false);
    }
  }, [csv, scope, accountId, useFraction, baselineFraction, splitAt]);

  const reports: DriftReport[] = useMemo(() => {
    if (!response) return [];
    if (response.scope === "single") return response.report ? [response.report] : [];
    return response.reports;
  }, [response]);

  const active = reports[activeIdx] ?? null;

  // -----------------------------------------------------------------------
  // Hero stats
  // -----------------------------------------------------------------------
  const summaryCounts = useMemo(() => {
    if (!response || response.scope !== "portfolio") return null;
    return response.summary;
  }, [response]);

  return (
    <div className="space-y-6">
      {/* ----- Header ----- */}
      <section className="glass-strong overflow-hidden p-6 md:p-8">
        <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
          <div>
            <span className="pill pill-bad">round-8 · day-40</span>
            <h1 className="mt-3 text-2xl font-semibold leading-tight md:text-3xl">
              <span className="grad-text">Behavioral Drift</span> — does the account still look like itself?
            </h1>
            <p className="mt-2 max-w-2xl text-[13.5px] leading-relaxed text-white/65">
              The eight risk detectors catch <em>threshold breaches</em>. This surface
              catches the other half: accounts whose recent behavior no longer matches
              their own historical baseline. Sleeper takeovers, mule recruitments,
              slow operator shifts — patterns no per-transaction rule will fire on,
              because nothing crossed a line; the line itself moved.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <button onClick={loadSample} className="btn">
              Load demo
            </button>
            <button onClick={run} disabled={busy || !csv} className="btn-primary">
              {busy ? "Analysing…" : "Run drift analysis"} <span aria-hidden>→</span>
            </button>
          </div>
        </div>

        {sampleNote && (
          <div className="mt-4 rounded-xl border border-white/5 bg-white/[0.02] p-3 text-[12px] text-white/55">
            <strong className="text-white/80">Demo loaded.</strong> {sampleNote}
          </div>
        )}
      </section>

      {/* ----- Controls ----- */}
      <section className="glass grid grid-cols-1 gap-4 p-5 md:grid-cols-[1.6fr_1fr] md:p-6">
        <div>
          <div className="mb-2 text-[11px] uppercase tracking-wider text-white/45">
            Transactions (CSV)
          </div>
          <textarea
            value={csv}
            onChange={(e) => setCsv(e.target.value)}
            spellCheck={false}
            rows={8}
            className="w-full resize-y rounded-xl border border-white/10 bg-black/30 p-3 font-mono text-[11.5px] text-white/80 focus:border-white/20 focus:outline-none"
          />
          <div className="mt-2 text-[11px] text-white/45">
            {csv ? `${(csv.match(/\n/g)?.length ?? 0)} rows` : "—"}
          </div>
        </div>
        <div className="space-y-3">
          <div>
            <div className="mb-1 text-[11px] uppercase tracking-wider text-white/45">
              Scope
            </div>
            <div className="flex gap-2">
              <button
                onClick={() => setScope("portfolio")}
                className={`flex-1 rounded-lg border px-3 py-1.5 text-[12.5px] transition ${
                  scope === "portfolio"
                    ? "border-teal-400/40 bg-teal-500/10 text-teal-300"
                    : "border-white/10 bg-white/[0.02] text-white/55 hover:bg-white/[0.05]"
                }`}
              >
                Portfolio (rank all)
              </button>
              <button
                onClick={() => setScope("single")}
                className={`flex-1 rounded-lg border px-3 py-1.5 text-[12.5px] transition ${
                  scope === "single"
                    ? "border-teal-400/40 bg-teal-500/10 text-teal-300"
                    : "border-white/10 bg-white/[0.02] text-white/55 hover:bg-white/[0.05]"
                }`}
              >
                Single account
              </button>
            </div>
          </div>
          {scope === "single" && (
            <div>
              <div className="mb-1 text-[11px] uppercase tracking-wider text-white/45">
                Account id
              </div>
              <input
                value={accountId}
                onChange={(e) => setAccountId(e.target.value)}
                placeholder="ACC-DRIFT"
                className="w-full rounded-lg border border-white/10 bg-black/30 px-3 py-1.5 text-[12.5px] text-white/85 focus:border-white/20 focus:outline-none"
              />
            </div>
          )}
          <div>
            <div className="mb-1 flex items-center justify-between text-[11px] uppercase tracking-wider text-white/45">
              <span>Window split</span>
              <button
                onClick={() => setUseFraction((v) => !v)}
                className="rounded-md border border-white/10 bg-white/[0.04] px-2 py-0.5 text-[10px] normal-case tracking-normal text-white/65 hover:bg-white/[0.07]"
              >
                {useFraction ? "switch to ISO timestamp" : "switch to fraction slider"}
              </button>
            </div>
            {useFraction ? (
              <div>
                <input
                  type="range"
                  min={0.2}
                  max={0.9}
                  step={0.05}
                  value={baselineFraction}
                  onChange={(e) => setBaselineFraction(Number(e.target.value))}
                  className="w-full accent-teal-400"
                />
                <div className="mt-1 flex justify-between text-[11px] text-white/55">
                  <span>baseline = first {(baselineFraction * 100).toFixed(0)}%</span>
                  <span>current = last {((1 - baselineFraction) * 100).toFixed(0)}%</span>
                </div>
              </div>
            ) : (
              <input
                value={splitAt}
                onChange={(e) => setSplitAt(e.target.value)}
                placeholder="2026-05-17T00:00:00Z"
                className="w-full rounded-lg border border-white/10 bg-black/30 px-3 py-1.5 font-mono text-[11.5px] text-white/85 focus:border-white/20 focus:outline-none"
              />
            )}
          </div>
        </div>
      </section>

      {err && (
        <div className="rounded-xl border border-rose-400/30 bg-rose-500/10 p-3 text-[12px] text-rose-200">
          {err}
        </div>
      )}

      {/* ----- Portfolio summary ----- */}
      {summaryCounts && reports.length > 0 && (
        <section className="grid grid-cols-2 gap-3 md:grid-cols-6">
          <SummaryTile label="Accounts" value={String(summaryCounts.total_accounts)} />
          <SummaryTile
            label="Drifters"
            value={String(summaryCounts.drifters)}
            accent={summaryCounts.drifters > 0 ? "text-rose-300" : undefined}
          />
          <VerdictTile label="Stable" count={summaryCounts.by_verdict.stable} verdict="stable" />
          <VerdictTile label="Mild" count={summaryCounts.by_verdict.mild} verdict="mild" />
          <VerdictTile label="Drifting" count={summaryCounts.by_verdict.drifting} verdict="drifting" />
          <VerdictTile
            label="Erratic / break"
            count={
              summaryCounts.by_verdict.erratic + summaryCounts.by_verdict.transformed
            }
            verdict="erratic"
          />
        </section>
      )}

      {/* ----- Body: ranking rail + active report ----- */}
      {reports.length > 0 && (
        <section className="grid grid-cols-1 gap-5 lg:grid-cols-[280px_1fr]">
          {/* Left rail */}
          <aside className="glass overflow-hidden p-3">
            <div className="px-2 pb-2 text-[11px] uppercase tracking-wider text-white/45">
              {response?.scope === "single" ? "Single account" : `Ranked (${reports.length})`}
            </div>
            <ul className="space-y-1">
              {reports.map((r, i) => (
                <li key={r.account_id}>
                  <button
                    onClick={() => setActiveIdx(i)}
                    className={`group block w-full rounded-xl border px-3 py-2 text-left transition ${
                      i === activeIdx
                        ? "border-white/20 bg-white/[0.06]"
                        : "border-transparent hover:border-white/10 hover:bg-white/[0.03]"
                    }`}
                  >
                    <div className="flex items-baseline justify-between gap-2">
                      <span className="truncate text-[13px] font-medium">
                        {r.display_name || r.account_id}
                      </span>
                      <VerdictPill verdict={r.verdict} compact />
                    </div>
                    <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-white/[0.05]">
                      <div
                        className="h-full rounded-full"
                        style={{
                          width: `${Math.max(2, r.overall * 100)}%`,
                          background: VERDICT_BAR[r.verdict],
                        }}
                      />
                    </div>
                    <div className="mt-1 flex items-center justify-between text-[10.5px] text-white/45">
                      <span>{r.account_id}</span>
                      <span>{fmtPct(r.overall)}</span>
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          </aside>

          {/* Active report */}
          <div className="space-y-5">
            {active ? <ActiveReport report={active} /> : null}
          </div>
        </section>
      )}

      {response?.scope === "single" && response.report === null && (
        <div className="glass p-5 text-[13px] text-white/60">
          Not enough transactions on either side of the split to analyse{" "}
          <code className="font-mono text-white/80">{response.account_id}</code> —{" "}
          {response.reason}.
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

const VERDICT_BAR: Record<DriftVerdict, string> = {
  stable: "linear-gradient(90deg,#2DE1C2,#38BDF8)",
  mild: "linear-gradient(90deg,#38BDF8,#6E5BFF)",
  drifting: "linear-gradient(90deg,#FBBF24,#FB923C)",
  erratic: "linear-gradient(90deg,#FB923C,#F43F5E)",
  transformed: "linear-gradient(90deg,#F43F5E,#7F1D1D)",
};

const VERDICT_HEX: Record<DriftVerdict, string> = {
  stable: "#2DE1C2",
  mild: "#38BDF8",
  drifting: "#FBBF24",
  erratic: "#FB923C",
  transformed: "#F43F5E",
};

function SummaryTile({
  label,
  value,
  accent,
}: {
  label: string;
  value: string;
  accent?: string;
}) {
  return (
    <div className="glass px-4 py-3">
      <div className="text-[11px] uppercase tracking-wider text-white/40">{label}</div>
      <div
        className={`mt-1 text-2xl font-semibold tracking-tight ${accent ?? "grad-text"}`}
      >
        {value}
      </div>
    </div>
  );
}

function VerdictTile({
  label,
  count,
  verdict,
}: {
  label: string;
  count: number;
  verdict: DriftVerdict;
}) {
  return (
    <div className="glass px-4 py-3">
      <div className="text-[11px] uppercase tracking-wider text-white/40">{label}</div>
      <div
        className="mt-1 text-2xl font-semibold tracking-tight"
        style={{ color: VERDICT_HEX[verdict] }}
      >
        {count}
      </div>
    </div>
  );
}

function VerdictPill({
  verdict,
  compact = false,
}: {
  verdict: DriftVerdict;
  compact?: boolean;
}) {
  const cls = `pill ws-drift-pill-${verdict}`;
  return (
    <span className={cls} style={compact ? { padding: "0 0.5rem", fontSize: 9 } : undefined}>
      {verdict}
    </span>
  );
}

function DriftRingHero({ overall, verdict }: { overall: number; verdict: DriftVerdict }) {
  const pct = Math.max(0, Math.min(1, overall)) * 100;
  const color = VERDICT_HEX[verdict];
  const ring = `conic-gradient(${color} ${pct * 3.6}deg, rgba(255,255,255,0.06) 0)`;
  const glow = verdict === "drifting" || verdict === "erratic" || verdict === "transformed";
  return (
    <div
      className={`relative grid place-items-center rounded-full ws-drift-ring ${
        glow ? "ws-drift-ring-glow" : ""
      }`}
      style={{ width: 132, height: 132, background: ring }}
    >
      <div className="absolute inset-[8px] rounded-full" style={{ background: "rgba(7,11,20,0.92)" }} />
      <div className="relative text-center leading-none">
        <div
          className="text-[34px] font-semibold tracking-tight"
          style={{ color }}
        >
          {pct.toFixed(0)}
        </div>
        <div className="mt-1 text-[9.5px] uppercase tracking-[0.18em] text-white/55">
          drift / 100
        </div>
      </div>
    </div>
  );
}

function ActiveReport({ report }: { report: DriftReport }) {
  const verdictClass = `ws-drift-verdict-${report.verdict}`;
  const cp = report.change_point;

  const hourBaseline = report.dimensions.find((d) => d.key === "hour")?.baseline?.histogram ?? [];
  const hourCurrent = report.dimensions.find((d) => d.key === "hour")?.current?.histogram ?? [];
  const dowBaseline = report.dimensions.find((d) => d.key === "dow")?.baseline?.histogram ?? [];
  const dowCurrent = report.dimensions.find((d) => d.key === "dow")?.current?.histogram ?? [];

  return (
    <>
      {/* Hero */}
      <section className={`glass-strong ws-drift-hero ${verdictClass} p-6 md:p-7`}>
        <div className="flex flex-col items-start gap-5 md:flex-row md:items-center">
          <DriftRingHero overall={report.overall} verdict={report.verdict} />
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <VerdictPill verdict={report.verdict} />
              <code className="rounded-md border border-white/10 bg-white/[0.05] px-2 py-0.5 font-mono text-[11px] text-white/65">
                {report.account_id}
              </code>
              {report.display_name && report.display_name !== report.account_id && (
                <span className="text-[12.5px] text-white/55">{report.display_name}</span>
              )}
            </div>
            <h2 className="mt-2 text-xl font-semibold leading-tight md:text-2xl">
              {report.headline}
            </h2>
            <p className="mt-2 text-[13px] leading-relaxed text-white/70">
              {report.narrative}
            </p>
            <div className="mt-3 rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2 text-[12.5px] text-white/75">
              <span className="text-[10px] uppercase tracking-widest text-white/40">
                Recommended action
              </span>
              <div className="mt-0.5">{report.suggested_action}</div>
            </div>
          </div>
        </div>
      </section>

      {/* Radar + windows */}
      <section className="grid grid-cols-1 gap-5 md:grid-cols-[1.1fr_1fr]">
        <div className="glass p-5">
          <div className="flex items-baseline justify-between">
            <h3 className="text-[14px] font-semibold">Behavioral fingerprint</h3>
            <span className="text-[11px] text-white/45">
              outer = baseline · inward dent = drift on that axis
            </span>
          </div>
          <div className="mt-3">
            <DriftRadar
              dimensions={report.dimensions}
              accent={VERDICT_HEX[report.verdict]}
              size={300}
            />
          </div>
        </div>

        <div className="glass p-5">
          <h3 className="text-[14px] font-semibold">Windows</h3>
          <div className="mt-3 grid grid-cols-2 gap-4">
            <WindowCard
              title="Baseline"
              tone="border-teal-400/30"
              data={report.baseline_window}
            />
            <WindowCard
              title="Current"
              tone="border-rose-400/30"
              data={report.current_window}
            />
          </div>
          {report.drivers.length > 0 && (
            <div className="mt-4 border-t border-white/5 pt-4">
              <div className="text-[11px] uppercase tracking-wider text-white/40">
                Top drivers
              </div>
              <div className="mt-2 flex flex-wrap gap-2">
                {report.drivers.map((d) => (
                  <span
                    key={d}
                    className="rounded-full border border-rose-400/30 bg-rose-500/10 px-2.5 py-1 text-[11px] text-rose-200"
                  >
                    {d}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      </section>

      {/* Per-dimension breakdown */}
      <section className="glass p-5">
        <div className="flex items-baseline justify-between">
          <h3 className="text-[14px] font-semibold">Per-dimension drift</h3>
          <span className="text-[11px] text-white/45">
            score · weight · contribution to composite
          </span>
        </div>
        <div className="mt-3 space-y-2">
          {report.dimensions
            .slice()
            .sort((a, b) => b.contribution - a.contribution)
            .map((d) => (
              <div
                key={d.key}
                className="ws-drift-dim-row grid grid-cols-[1fr_2fr_auto] items-center gap-3 rounded-xl border border-white/5 bg-white/[0.015] px-3 py-2"
              >
                <div className="min-w-0">
                  <div className="text-[13px] font-medium">{d.label}</div>
                  <div className="text-[11px] text-white/45">{d.detail}</div>
                </div>
                <div className="relative">
                  <div className="h-2 overflow-hidden rounded-full bg-white/[0.04]">
                    <div
                      className="h-full rounded-full"
                      style={{
                        width: `${Math.max(2, d.score * 100)}%`,
                        background:
                          d.score >= 0.5
                            ? "linear-gradient(90deg,#FB923C,#F43F5E)"
                            : d.score >= 0.25
                            ? "linear-gradient(90deg,#FBBF24,#FB923C)"
                            : "linear-gradient(90deg,#2DE1C2,#38BDF8)",
                      }}
                    />
                  </div>
                  <div className="mt-1 grid grid-cols-3 text-[10px] text-white/40">
                    <span>score {(d.score * 100).toFixed(0)}%</span>
                    <span className="text-center">weight {(d.weight * 100).toFixed(0)}%</span>
                    <span className="text-right">
                      contrib {(d.contribution * 100).toFixed(1)}%
                    </span>
                  </div>
                </div>
                <div
                  className="rounded-md border border-white/10 bg-white/[0.04] px-2 py-1 font-mono text-[11px] text-white/75"
                  title="Score on this axis"
                >
                  {(d.score * 100).toFixed(0)}
                </div>
              </div>
            ))}
        </div>
      </section>

      {/* Distribution overlays — only show if hour/dow dimensions present */}
      {(hourBaseline.length === 24 || dowBaseline.length === 7) && (
        <section className="grid grid-cols-1 gap-5 md:grid-cols-2">
          {hourBaseline.length === 24 && (
            <div className="glass p-5">
              <div className="flex items-baseline justify-between">
                <h3 className="text-[14px] font-semibold">Hour of day</h3>
                <span className="text-[11px] text-white/45">
                  JS divergence ·{" "}
                  {(
                    (report.dimensions.find((d) => d.key === "hour")?.score ?? 0) * 100
                  ).toFixed(0)}
                  %
                </span>
              </div>
              <div className="mt-3">
                <DistributionOverlay
                  baseline={hourBaseline}
                  current={hourCurrent}
                  labels={HOUR_LABELS}
                  height={120}
                />
              </div>
            </div>
          )}
          {dowBaseline.length === 7 && (
            <div className="glass p-5">
              <div className="flex items-baseline justify-between">
                <h3 className="text-[14px] font-semibold">Day of week</h3>
                <span className="text-[11px] text-white/45">
                  JS divergence ·{" "}
                  {(
                    (report.dimensions.find((d) => d.key === "dow")?.score ?? 0) * 100
                  ).toFixed(0)}
                  %
                </span>
              </div>
              <div className="mt-3">
                <DistributionOverlay
                  baseline={dowBaseline}
                  current={dowCurrent}
                  labels={DOW_LABELS}
                  height={120}
                />
              </div>
            </div>
          )}
        </section>
      )}

      {/* Change-point */}
      <section className="glass p-5">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h3 className="text-[14px] font-semibold">Change-point estimate</h3>
          {cp.detected ? (
            <span className="rounded-full border border-amber-400/30 bg-amber-500/10 px-3 py-0.5 text-[11px] text-amber-200">
              onset ≈ {isoToShort(cp.onset_iso)} · {cp.days_ago} day{cp.days_ago === 1 ? "" : "s"} ago
            </span>
          ) : (
            <span className="rounded-full border border-teal-400/30 bg-teal-500/10 px-3 py-0.5 text-[11px] text-teal-300">
              No onset detected within current window
            </span>
          )}
        </div>
        <p className="mt-2 text-[12.5px] leading-relaxed text-white/55">
          Walks the current window day by day; each day takes the trailing 7-day slice and
          measures KS against the long baseline. The first day above floor is the drift onset.
        </p>
        <div className="mt-3">
          <DriftTimeline
            rolling={cp.rolling_ks}
            threshold={0.3}
            onsetDay={cp.onset_iso ? isoToShort(cp.onset_iso) : null}
            height={150}
          />
        </div>
      </section>

      {/* Counterparties */}
      <section className="glass p-5">
        <div className="flex items-baseline justify-between">
          <h3 className="text-[14px] font-semibold">Counterparty contribution</h3>
          <span className="text-[11px] text-white/45">
            who's new · who's suddenly more active
          </span>
        </div>
        <div className="mt-3 overflow-hidden rounded-xl border border-white/5">
          <table className="w-full text-[12.5px]">
            <thead className="bg-white/[0.03] text-[11px] uppercase tracking-wider text-white/45">
              <tr>
                <th className="px-3 py-2 text-left font-medium">Counterparty</th>
                <th className="px-3 py-2 text-right font-medium">Baseline</th>
                <th className="px-3 py-2 text-right font-medium">Current</th>
                <th className="px-3 py-2 text-right font-medium">Activity Δ</th>
                <th className="px-3 py-2 text-right font-medium">Volume Δ</th>
              </tr>
            </thead>
            <tbody>
              {report.counterparties.map((cp) => (
                <tr
                  key={cp.counterparty}
                  className="ws-drift-cparty-row border-t border-white/5"
                >
                  <td className="px-3 py-2">
                    <div className="flex items-center gap-2">
                      <code className="font-mono text-[12px] text-white/80">
                        {cp.counterparty}
                      </code>
                      {cp.is_new && (
                        <span className="rounded-full border border-rose-400/30 bg-rose-500/10 px-1.5 py-0.5 text-[9.5px] uppercase tracking-wider text-rose-200">
                          new
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="px-3 py-2 text-right text-white/65">
                    {cp.baseline_count} <span className="text-white/35">tx</span>
                  </td>
                  <td className="px-3 py-2 text-right text-white/85">
                    {cp.current_count} <span className="text-white/35">tx</span>
                  </td>
                  <td className="px-3 py-2 text-right font-mono text-[11.5px]">
                    {cp.is_new
                      ? "—"
                      : cp.activity_lift !== null
                      ? `${cp.activity_lift > 0 ? "+" : ""}${(cp.activity_lift * 100).toFixed(0)}%`
                      : "—"}
                  </td>
                  <td className="px-3 py-2 text-right font-mono text-[11.5px]">
                    {cp.is_new
                      ? "+∞"
                      : cp.volume_lift !== null
                      ? `${cp.volume_lift > 0 ? "+" : ""}${(cp.volume_lift * 100).toFixed(0)}%`
                      : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}

function WindowCard({
  title,
  tone,
  data,
}: {
  title: string;
  tone: string;
  data: any;
}) {
  return (
    <div className={`rounded-xl border ${tone} bg-black/20 p-3`}>
      <div className="text-[10.5px] uppercase tracking-widest text-white/45">
        {title}
      </div>
      <div className="mt-1 text-[12.5px] text-white/85">
        {data.tx_count} txs over {data.span_days}d
      </div>
      <div className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-[11.5px] text-white/55">
        <div>median</div>
        <div className="text-right font-mono text-white/75">
          {data.median_amount?.toLocaleString() ?? "—"}
        </div>
        <div>inflow share</div>
        <div className="text-right font-mono text-white/75">
          {((data.inflow_share ?? 0) * 100).toFixed(0)}%
        </div>
        <div>unique cparts</div>
        <div className="text-right font-mono text-white/75">
          {data.unique_counterparties ?? 0}
        </div>
        <div>active days</div>
        <div className="text-right font-mono text-white/75">{data.active_days ?? 0}</div>
      </div>
      <div className="mt-2 text-[10px] text-white/35">
        {isoToShort(data.start_iso)} → {isoToShort(data.end_iso)}
      </div>
    </div>
  );
}
