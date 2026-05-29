"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import ConfusionMatrix from "../../components/ConfusionMatrix";
import MetricSweep from "../../components/MetricSweep";
import RocCurve from "../../components/RocCurve";
import {
  BacktestResult,
  Tx,
  WeightOverrides,
  getBacktestSample,
  runBacktest,
} from "../../lib/api";

type WeightKey = keyof WeightOverrides;

const DETECTOR_LABELS: Record<WeightKey, string> = {
  structuring: "Structuring",
  velocity_spike: "Velocity Spike",
  round_trip: "Round-Trip Cycle",
  sanctions_hit: "Sanctions Hit",
  fan_in: "Fan-in",
  fan_out: "Fan-out",
  high_risk_geo: "High-Risk Geo",
  round_amount: "Round Amounts",
};

const DETECTOR_ORDER: WeightKey[] = [
  "structuring",
  "velocity_spike",
  "round_trip",
  "sanctions_hit",
  "fan_in",
  "fan_out",
  "high_risk_geo",
  "round_amount",
];

const MAX_WEIGHT = 60;
const BETAS = [0.5, 1, 2, 3];

const STRENGTH_TONE: Record<string, { bar: string; chip: string }> = {
  strong: { bar: "linear-gradient(90deg,#2DE1C2,#38BDF8)", chip: "ws-cnp-chip-teal" },
  moderate: { bar: "linear-gradient(90deg,#38BDF8,#6E5BFF)", chip: "ws-cnp-chip-violet" },
  weak: { bar: "linear-gradient(90deg,#FBBF24,#FB923C)", chip: "ws-cnp-chip-amber" },
  noise: { bar: "linear-gradient(90deg,#F43F5E,#9F1239)", chip: "ws-cnp-chip-rose" },
};

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
  const cols = ["account_id", "counterparty", "amount", "timestamp", "channel", "geo", "subject_name", "counterparty_name"];
  const head = cols.join(",");
  const rows = txs.map((t) => cols.map((c) => (t as any)[c] ?? "").join(","));
  return [head, ...rows].join("\n");
}

function parseLabels(s: string): string[] {
  return Array.from(new Set(s.split(/[\s,]+/).map((x) => x.trim()).filter(Boolean)));
}

export default function ValidationPage() {
  const [csv, setCsv] = useState("");
  const [labelStr, setLabelStr] = useState("");
  const [result, setResult] = useState<BacktestResult | null>(null);
  const [baseline, setBaseline] = useState<{
    auc: number;
    ap: number;
    fbeta: number;
    recall: number;
    alert_rate: number;
  } | null>(null);
  const [active, setActive] = useState(30);
  const [beta, setBeta] = useState(2);
  const [weights, setWeights] = useState<WeightOverrides>({});
  const [showWhatIf, setShowWhatIf] = useState(false);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const debounce = useRef<ReturnType<typeof setTimeout> | null>(null);

  const txs = useMemo(() => parseCsv(csv), [csv]);
  const labels = useMemo(() => parseLabels(labelStr), [labelStr]);
  const hasOverride = Object.keys(weights).length > 0;

  const run = useCallback(
    async (override?: WeightOverrides, b?: number) => {
      if (!txs.length || !labels.length) {
        setErr("Need transactions and at least one confirmed-suspicious account id.");
        return;
      }
      setErr(null);
      setLoading(true);
      try {
        const w = override ?? weights;
        const res = await runBacktest(txs, labels, {
          weights: Object.keys(w).length ? w : undefined,
          beta: b ?? beta,
        });
        setResult(res);
        setActive(res.metrics_at.recommended.threshold);
        if (!Object.keys(w).length) {
          setBaseline({
            auc: res.roc.auc,
            ap: res.pr.average_precision,
            fbeta: res.metrics_at.recommended.fbeta,
            recall: res.metrics_at.recommended.recall,
            alert_rate: res.metrics_at.recommended.alert_rate,
          });
        }
      } catch (e: any) {
        setErr(e.message || "Backtest failed");
      } finally {
        setLoading(false);
      }
    },
    [txs, labels, weights, beta],
  );

  const loadSample = useCallback(async () => {
    setErr(null);
    setLoading(true);
    try {
      const s = await getBacktestSample();
      setCsv(toCsv(s.transactions));
      setLabelStr(s.labels.join(", "));
    } catch (e: any) {
      setErr(e.message || "Could not load sample");
    } finally {
      setLoading(false);
    }
  }, []);

  // Load + run the bundled sample on first paint.
  useEffect(() => {
    (async () => {
      try {
        const s = await getBacktestSample();
        const sampleCsv = toCsv(s.transactions);
        setCsv(sampleCsv);
        setLabelStr(s.labels.join(", "));
        const res = await runBacktest(parseCsv(sampleCsv), s.labels, { beta: 2 });
        setResult(res);
        setActive(res.metrics_at.recommended.threshold);
        setBaseline({
          auc: res.roc.auc,
          ap: res.pr.average_precision,
          fbeta: res.metrics_at.recommended.fbeta,
          recall: res.metrics_at.recommended.recall,
          alert_rate: res.metrics_at.recommended.alert_rate,
        });
      } catch (e: any) {
        setErr(e.message || "Could not load sample");
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Live re-run when weights change (debounced) — validates a tuning hypothesis.
  useEffect(() => {
    if (!result) return;
    if (debounce.current) clearTimeout(debounce.current);
    debounce.current = setTimeout(() => run(weights), 300);
    return () => {
      if (debounce.current) clearTimeout(debounce.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [weights]);

  const at = result?.sweep[Math.max(0, Math.min(100, Math.round(active)))] ?? null;
  const rec = result?.metrics_at.recommended ?? null;
  const cur = result?.metrics_at.current ?? null;
  const effWeights = result?.effective_weights ?? {};

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <span className="pill pill-ok">Engine · {result?.engine ?? "titan-backtest"}</span>
          <h1 className="mt-2 text-2xl font-semibold tracking-tight md:text-3xl">
            Model Validation
          </h1>
          <p className="mt-1 max-w-2xl text-[13.5px] text-white/60">
            Replay the risk engine against a labelled set of confirmed
            outcomes and read the trade-off. Sweep the alert threshold,
            benchmark the production cut against an Fβ-optimal one, and see
            which detectors actually separate good from bad — the evidence a
            model-risk review (SR&nbsp;11-7&nbsp;/&nbsp;FFIEC) demands.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex items-center gap-1 rounded-xl border border-white/10 bg-black/25 p-1">
            <span className="px-2 text-[11px] uppercase tracking-wider text-white/45">Fβ</span>
            {BETAS.map((b) => (
              <button
                key={b}
                onClick={() => {
                  setBeta(b);
                  if (result) run(weights, b);
                }}
                className={`rounded-lg px-2.5 py-1 text-[12px] tabular-nums transition ${
                  beta === b ? "bg-white/15 text-white" : "text-white/55 hover:text-white/85"
                }`}
                title={b < 1 ? "precision-weighted" : b > 1 ? "recall-weighted" : "balanced"}
              >
                {b}
              </button>
            ))}
          </div>
          <button
            className={`btn ${showWhatIf ? "ring-1 ring-teal-400/40" : ""}`}
            onClick={() => setShowWhatIf((v) => !v)}
          >
            {showWhatIf ? "Hide tuning" : "Tune weights"}
          </button>
          <button className="btn" onClick={loadSample} disabled={loading}>
            Load sample
          </button>
          <button className="btn-primary" onClick={() => run()} disabled={loading}>
            {loading ? "Validating…" : `Validate ${txs.length} txs`}
          </button>
        </div>
      </header>

      {err && (
        <div className="glass border-rose-400/30 bg-rose-500/[0.06] px-4 py-2.5 text-[12.5px] text-rose-300">
          {err}
        </div>
      )}

      {/* Weight tuning */}
      {showWhatIf && (
        <section className="glass-strong p-5">
          <div className="flex flex-wrap items-baseline justify-between gap-3">
            <div>
              <h2 className="text-lg font-semibold">Validate a tuning hypothesis</h2>
              <p className="mt-1 text-[12.5px] text-white/55">
                Override detector weights and re-validate live. The headline
                tiles show the delta against the canonical rule set — proof a
                tweak actually improves detection, not just the leaderboard.
              </p>
            </div>
            <button className="btn-ghost" onClick={() => setWeights({})} disabled={!hasOverride}>
              Reset weights
            </button>
          </div>
          <div className="mt-4 grid gap-x-6 gap-y-4 md:grid-cols-2">
            {DETECTOR_ORDER.map((k) => {
              const base = effWeights[k] ?? 0;
              const cv = typeof weights[k] === "number" ? weights[k]! : base;
              const overridden = typeof weights[k] === "number" && weights[k] !== base;
              return (
                <div key={k}>
                  <div className="mb-1 flex items-baseline justify-between">
                    <span className={`text-[12.5px] font-medium ${overridden ? "text-teal-300" : "text-white/85"}`}>
                      {DETECTOR_LABELS[k]}
                    </span>
                    <span className="font-mono text-[11px] tabular-nums text-white/65">{cv.toFixed(0)}</span>
                  </div>
                  <input
                    type="range"
                    min={0}
                    max={MAX_WEIGHT}
                    step={1}
                    value={cv}
                    onChange={(e) => setWeights((w) => ({ ...w, [k]: Number(e.target.value) }))}
                    className="w-full accent-teal-400"
                  />
                </div>
              );
            })}
          </div>
        </section>
      )}

      {result && at && rec && cur && (
        <>
          {/* Verdict */}
          <section
            className={`relative overflow-hidden rounded-2xl border p-5 ${
              result.verdict.grade === "strong"
                ? "border-teal-400/30 bg-teal-500/[0.05]"
                : result.verdict.grade === "fair"
                  ? "border-sky-400/30 bg-sky-500/[0.05]"
                  : result.verdict.grade === "marginal"
                    ? "border-amber-400/30 bg-amber-500/[0.05]"
                    : "border-rose-400/30 bg-rose-500/[0.05]"
            }`}
          >
            <div className="flex flex-wrap items-center gap-3">
              <span
                className={`pill ${
                  result.verdict.grade === "strong"
                    ? "pill-ok"
                    : result.verdict.grade === "poor"
                      ? "pill-bad"
                      : "pill-warn"
                }`}
              >
                {result.verdict.grade}
              </span>
              <span className="text-[15px] font-semibold text-white/90">{result.verdict.headline}</span>
            </div>
            {result.verdict.notes.length > 0 && (
              <ul className="mt-3 space-y-1.5 text-[12.5px] text-white/70">
                {result.verdict.notes.map((n, i) => (
                  <li key={i} className="flex gap-2">
                    <span className="text-white/35">→</span>
                    <span>{n}</span>
                  </li>
                ))}
              </ul>
            )}
          </section>

          {/* Headline tiles */}
          <section className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
            <Tile
              label="ROC AUC"
              value={result.roc.auc.toFixed(3)}
              delta={baseline && hasOverride ? result.roc.auc - baseline.auc : null}
              accent="teal"
            />
            <Tile
              label="Avg precision"
              value={result.pr.average_precision.toFixed(3)}
              delta={baseline && hasOverride ? result.pr.average_precision - baseline.ap : null}
              accent="violet"
            />
            <Tile label="Recommended cut" value={rec.threshold.toFixed(0)} accent="amber" mono />
            <Tile
              label={`Recall @ rec`}
              value={`${(rec.recall * 100).toFixed(0)}%`}
              delta={baseline && hasOverride ? rec.recall - baseline.recall : null}
              accent="teal"
            />
            <Tile
              label="Alert rate @ rec"
              value={`${(rec.alert_rate * 100).toFixed(0)}%`}
              delta={baseline && hasOverride ? rec.alert_rate - baseline.alert_rate : null}
              accent="violet"
              deltaGoodWhenDown
            />
            <Tile
              label="Base rate"
              value={`${(result.labels.base_rate * 100).toFixed(0)}%`}
              cap={`${result.labels.n_pos}/${result.labels.n_total} labelled bad`}
              accent="neutral"
              mono
            />
          </section>

          {/* Confusion + metrics + ROC */}
          <section className="grid gap-4 lg:grid-cols-[1.3fr_0.9fr_0.9fr]">
            <div className="glass p-5">
              <div className="flex items-baseline justify-between">
                <div className="label !mb-0">Confusion @ cut {Math.round(active)}</div>
                <div className="flex gap-1.5">
                  <button
                    className="rounded-md border border-white/12 px-2 py-0.5 text-[10.5px] uppercase tracking-wider text-white/60 hover:text-white"
                    onClick={() => setActive(cur.threshold)}
                  >
                    now ({cur.threshold.toFixed(0)})
                  </button>
                  <button
                    className="rounded-md border border-teal-400/40 bg-teal-500/10 px-2 py-0.5 text-[10.5px] uppercase tracking-wider text-teal-300 hover:bg-teal-500/15"
                    onClick={() => setActive(rec.threshold)}
                  >
                    rec ({rec.threshold.toFixed(0)})
                  </button>
                </div>
              </div>
              <div className="mt-4">
                <ConfusionMatrix point={at} />
              </div>
            </div>

            <div className="glass p-5">
              <div className="label">Operating metrics</div>
              <div className="space-y-2.5">
                <MetricRow label="Precision" value={at.precision} />
                <MetricRow label="Recall (sensitivity)" value={at.recall} />
                <MetricRow label="Specificity" value={at.specificity} />
                <MetricRow label="F1" value={at.f1} />
                <MetricRow label={`Fβ (β=${result.beta})`} value={at.fbeta} highlight />
                <MetricRow label="Balanced acc." value={at.balanced_accuracy} />
                <div className="border-t border-white/8 pt-2.5">
                  <MetricRow label="Alert rate" value={at.alert_rate} muted />
                </div>
              </div>
            </div>

            <div className="glass p-5">
              <div className="flex items-baseline justify-between">
                <div className="label !mb-0">ROC</div>
                <span className="font-mono text-[12px] text-teal-300">AUC {result.roc.auc.toFixed(3)}</span>
              </div>
              <div className="mt-3">
                <RocCurve
                  roc={result.roc}
                  current={{ fpr: cur.fpr, tpr: cur.tpr }}
                  recommended={{ fpr: rec.fpr, tpr: rec.tpr }}
                />
              </div>
            </div>
          </section>

          {/* Threshold sweep */}
          <section className="glass-strong p-5">
            <div className="flex flex-wrap items-baseline justify-between gap-3">
              <div>
                <h2 className="text-lg font-semibold">Threshold sweep</h2>
                <p className="mt-0.5 text-[12.5px] text-white/55">
                  Drag the cursor (or the slider) to scrub the alert cut. The
                  amber guide is the Fβ-optimal point; the grey guide is the
                  current case-open cut.
                </p>
              </div>
              <span className="font-mono text-[12px] tabular-nums text-white/70">cut = {Math.round(active)}</span>
            </div>
            <div className="mt-4">
              <MetricSweep
                sweep={result.sweep}
                active={active}
                current={cur.threshold}
                recommended={rec.threshold}
                onScrub={setActive}
              />
            </div>
            <input
              type="range"
              min={0}
              max={100}
              step={1}
              value={active}
              onChange={(e) => setActive(Number(e.target.value))}
              className="mt-3 w-full accent-teal-400"
            />
          </section>

          {/* Detector discrimination */}
          <section className="glass-strong p-5">
            <div className="flex flex-wrap items-baseline justify-between gap-3">
              <div>
                <h2 className="text-lg font-semibold">Detector discrimination</h2>
                <p className="mt-0.5 text-[12.5px] text-white/55">
                  Each detector's own AUC over the labelled set — how well it
                  alone separates confirmed-bad from benign. 0.50 is a coin
                  flip; the bar measures the margin above chance.
                </p>
              </div>
            </div>
            <div className="mt-4 space-y-2.5">
              {result.detectors.map((d) => {
                const tone = STRENGTH_TONE[d.strength];
                const barPct = Math.max(0, Math.min(1, (d.auc - 0.5) / 0.5)) * 100;
                return (
                  <div
                    key={d.key}
                    className="grid grid-cols-[140px_1fr_auto] items-center gap-3 rounded-xl border border-white/8 bg-black/20 px-3 py-2.5 md:grid-cols-[160px_1fr_auto]"
                  >
                    <div className="min-w-0">
                      <div className="truncate text-[13px] font-medium text-white/85">{d.label}</div>
                      <div className="font-mono text-[10px] text-white/40">
                        w={d.weight.toFixed(0)} · fired {d.fired_pos}/{d.n_pos} bad · {d.fired_neg}/{d.n_neg} good
                      </div>
                    </div>
                    <div>
                      <div className="relative h-2.5 overflow-hidden rounded-full bg-white/[0.06]">
                        <span
                          className="absolute inset-y-0 left-0 rounded-full"
                          style={{ width: `${barPct}%`, background: tone.bar }}
                        />
                      </div>
                      <div className="mt-1 text-[11px] text-white/50">{d.note}</div>
                    </div>
                    <div className="flex flex-col items-end gap-1">
                      <span className="font-mono text-[14px] tabular-nums text-white/90">{d.auc.toFixed(2)}</span>
                      <span className={`ws-cnp-chip ${tone.chip}`}>{d.strength}</span>
                    </div>
                  </div>
                );
              })}
            </div>
          </section>

          {/* Accounts table */}
          <section className="glass p-5">
            <div className="flex items-baseline justify-between">
              <div className="label !mb-0">Scored accounts · outcome @ recommended cut ({rec.threshold.toFixed(0)})</div>
              <span className="text-[11px] text-white/45">{result.accounts.length} parties</span>
            </div>
            <div className="scroll-thin mt-3 max-h-96 overflow-y-auto pr-1">
              <table className="w-full text-left text-[12.5px]">
                <thead className="sticky top-0 bg-[#070b14] text-[10.5px] uppercase tracking-wider text-white/40">
                  <tr>
                    <th className="py-1.5 pr-2 font-normal">Account</th>
                    <th className="py-1.5 pr-2 font-normal">Score</th>
                    <th className="py-1.5 pr-2 font-normal">Label</th>
                    <th className="py-1.5 font-normal">Outcome</th>
                  </tr>
                </thead>
                <tbody>
                  {result.accounts.map((a) => (
                    <tr key={a.account_id} className="border-t border-white/5">
                      <td className="py-1.5 pr-2">
                        <span className="font-mono text-white/85">{a.account_id}</span>
                        {a.display_name && (
                          <span className="ml-2 text-[11px] text-white/45">{a.display_name}</span>
                        )}
                      </td>
                      <td className="py-1.5 pr-2 font-mono tabular-nums text-white/75">{a.score.toFixed(1)}</td>
                      <td className="py-1.5 pr-2">
                        <span className={a.label ? "text-rose-300" : "text-white/45"}>
                          {a.label ? "suspicious" : "benign"}
                        </span>
                      </td>
                      <td className="py-1.5">
                        <OutcomeChip outcome={a.outcome} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          {/* Input (collapsed at bottom) */}
          <section className="grid gap-4 lg:grid-cols-[1.4fr_1fr]">
            <div className="glass p-4">
              <div className="label">Transactions · CSV</div>
              <div className="dropzone rounded-xl">
                <textarea
                  value={csv}
                  onChange={(e) => setCsv(e.target.value)}
                  spellCheck={false}
                  className="scroll-thin h-56 w-full resize-none bg-transparent p-3 font-mono text-[11.5px] text-white/85 outline-none"
                />
              </div>
            </div>
            <div className="glass p-4">
              <div className="label">Confirmed-suspicious account ids</div>
              <textarea
                value={labelStr}
                onChange={(e) => setLabelStr(e.target.value)}
                spellCheck={false}
                placeholder="A1, A2, MULE …"
                className="input scroll-thin h-24 resize-none font-mono text-[12px]"
              />
              <p className="mt-2 text-[11px] text-white/45">
                Comma- or space-separated. These are your ground truth (e.g.
                accounts that ended in a filed SAR); every other scored party
                is treated as benign.
              </p>
              <p className="mt-2 text-[11px] text-white/40">
                {result.labels.n_pos} positive · {result.labels.n_neg} negative ·{" "}
                {result.labels.n_total} evaluated
              </p>
            </div>
          </section>
        </>
      )}
    </div>
  );
}

function Tile({
  label,
  value,
  cap,
  delta,
  accent,
  mono,
  deltaGoodWhenDown,
}: {
  label: string;
  value: string;
  cap?: string;
  delta?: number | null;
  accent: "teal" | "violet" | "amber" | "rose" | "neutral";
  mono?: boolean;
  deltaGoodWhenDown?: boolean;
}) {
  const show = typeof delta === "number" && Math.abs(delta) >= 0.005;
  const good = show ? (deltaGoodWhenDown ? delta! < 0 : delta! > 0) : false;
  return (
    <div className={`ws-cnp-tile ws-cnp-tile-${accent}`}>
      <div className="ws-cnp-tile-label">{label}</div>
      <div className={`ws-cnp-tile-value ${mono ? "font-mono" : ""}`}>{value}</div>
      {show ? (
        <div className={`mt-0.5 text-[10.5px] font-medium ${good ? "text-teal-300" : "text-rose-300"}`}>
          {delta! > 0 ? "+" : ""}
          {Math.abs(delta!) < 1 ? delta!.toFixed(3) : delta!.toFixed(1)} vs canonical
        </div>
      ) : (
        cap && <div className="ws-cnp-tile-cap">{cap}</div>
      )}
    </div>
  );
}

function MetricRow({
  label,
  value,
  highlight,
  muted,
}: {
  label: string;
  value: number;
  highlight?: boolean;
  muted?: boolean;
}) {
  return (
    <div className="flex items-center gap-3">
      <span className={`w-36 text-[12px] ${muted ? "text-white/45" : "text-white/65"}`}>{label}</span>
      <div className="relative h-2 flex-1 overflow-hidden rounded-full bg-white/[0.06]">
        <span
          className="absolute inset-y-0 left-0 rounded-full"
          style={{
            width: `${Math.max(0, Math.min(1, value)) * 100}%`,
            background: highlight
              ? "linear-gradient(90deg,#FBBF24,#FB923C)"
              : muted
                ? "linear-gradient(90deg,#475569,#64748B)"
                : "linear-gradient(90deg,#2DE1C2,#6E5BFF)",
          }}
        />
      </div>
      <span className={`w-10 text-right font-mono text-[12px] tabular-nums ${highlight ? "text-amber-300" : "text-white/85"}`}>
        {value.toFixed(2)}
      </span>
    </div>
  );
}

function OutcomeChip({ outcome }: { outcome: "tp" | "fp" | "fn" | "tn" }) {
  const map: Record<string, { cls: string; label: string }> = {
    tp: { cls: "ws-cnp-chip-teal", label: "caught" },
    fp: { cls: "ws-cnp-chip-amber", label: "false alarm" },
    fn: { cls: "ws-cnp-chip-rose", label: "missed" },
    tn: { cls: "ws-cnp-chip-neutral", label: "cleared" },
  };
  const m = map[outcome];
  return <span className={`ws-cnp-chip ${m.cls}`}>{m.label}</span>;
}
