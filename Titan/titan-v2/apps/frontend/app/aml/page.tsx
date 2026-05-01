"use client";

import { DragEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import FactorBars from "../../components/FactorBars";
import ScoreRing from "../../components/ScoreRing";
import SimilarityRing, { GRADE_TINT } from "../../components/SimilarityRing";
import TxGraph from "../../components/TxGraph";
import {
  AccountReport,
  ScoreResponse,
  Tx,
  WeightOverrides,
  generateSar,
  score,
} from "../../lib/api";

const SAMPLE = `account_id,counterparty,amount,timestamp,channel,geo,subject,subject_name,counterparty_name
A1,M1,45000,2026-04-20T09:00:00Z,UPI,IN,0xabc,Lakshmi Holdings Pvt Ltd,Trident Exports
A1,M2,47500,2026-04-20T11:00:00Z,UPI,IN,0xabc,Lakshmi Holdings Pvt Ltd,Trident Exports
A1,M3,49000,2026-04-20T15:00:00Z,UPI,IN,0xabc,Lakshmi Holdings Pvt Ltd,Trident Exports
A1,M4,48500,2026-04-20T20:00:00Z,UPI,IN,0xabc,Lakshmi Holdings Pvt Ltd,Sundar Logistics
A2,B,500000,2026-04-21T10:00:00Z,RTGS,IN,0xdef,Rohit Mehta Trading,Aurelia Shell Limited
B,C,480000,2026-04-21T11:00:00Z,RTGS,IN,,Aurelia Shell Limited,Crescent Maritime
C,A2,460000,2026-04-21T12:00:00Z,RTGS,IN,,Crescent Maritime,Rohit Mehta Trading
A3,X,100000,2026-04-22T10:00:00Z,SWIFT,KP,0x999,Devraj Industries,Pyongyang Horizon
A4,P,10000,2026-03-25T10:00:00Z,UPI,IN,,Vikram Enterprises,Local Vendor
A4,P,900000,2026-04-22T10:00:00Z,RTGS,IN,,Vikram Enterprises,Local Vendor
A5,Q,250000,2026-04-23T08:00:00Z,SWIFT,RU,0x42,Northern Steel Co,Argentum Horizon GmbH
A5,R,180000,2026-04-23T08:30:00Z,SWIFT,AE,0x42,Northern Steel Co,Golden Oryx Trading
`;

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

function parseCsv(text: string): Tx[] {
  const lines = text.trim().split(/\r?\n/);
  if (lines.length < 2) return [];
  const cols = lines[0].split(",").map((c) => c.trim());
  return lines.slice(1).filter(Boolean).map((line) => {
    const vals = line.split(",");
    const o: any = {};
    cols.forEach((c, i) => (o[c] = (vals[i] ?? "").trim()));
    o.amount = Number(o.amount);
    return o as Tx;
  });
}

export default function AMLPage() {
  const [csv, setCsv] = useState(SAMPLE);
  const [resp, setResp] = useState<ScoreResponse | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [drag, setDrag] = useState(false);
  const [sar, setSar] = useState<{ md: string; id: string } | null>(null);
  const [showWhatIf, setShowWhatIf] = useState(false);
  const [weights, setWeights] = useState<WeightOverrides>({});
  const fileRef = useRef<HTMLInputElement>(null);
  const debounceTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const txs = useMemo(() => parseCsv(csv), [csv]);
  const selectedReport = useMemo(
    () => resp?.accounts.find((a) => a.account_id === selected) ?? resp?.accounts[0] ?? null,
    [resp, selected],
  );

  const runScore = useCallback(
    async (override?: WeightOverrides) => {
      setErr(null);
      setSar(null);
      setLoading(true);
      try {
        const data = await score(parseCsv(csv), { weights: override ?? weights });
        setResp(data);
        if (!selected && data.accounts[0]) {
          setSelected(data.accounts[0].account_id);
        }
      } catch (e: any) {
        setErr(e.message || "Scoring failed");
      } finally {
        setLoading(false);
      }
    },
    [csv, weights, selected],
  );

  const onScore = useCallback(() => runScore(), [runScore]);

  // Auto-rescore on weight change (debounced) so the simulator feels live.
  useEffect(() => {
    if (!resp) return;
    if (debounceTimer.current) clearTimeout(debounceTimer.current);
    debounceTimer.current = setTimeout(() => runScore(weights), 250);
    return () => {
      if (debounceTimer.current) clearTimeout(debounceTimer.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [weights]);

  const onDrop = useCallback(async (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDrag(false);
    const f = e.dataTransfer.files?.[0];
    if (!f) return;
    setCsv(await f.text());
  }, []);

  const onFile = useCallback(async (f: File | null) => {
    if (!f) return;
    setCsv(await f.text());
  }, []);

  const onSar = useCallback(async () => {
    if (!selectedReport) return;
    try {
      setSar(null);
      const out = await generateSar(selectedReport);
      setSar({ md: out.narrative_md, id: out.sar_id });
    } catch (e: any) {
      setErr(e.message || "SAR generation failed");
    }
  }, [selectedReport]);

  const resetWeights = useCallback(() => setWeights({}), []);

  const effectiveWeights = resp?.effective_weights ?? {};
  const isOverridden = (k: WeightKey) =>
    typeof weights[k] === "number" && weights[k] !== effectiveWeights[k];

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <span className="pill pill-ok">
            Engine · {resp?.engine ?? "titan-aml/1.1.0"}
          </span>
          <h1 className="mt-2 text-2xl font-semibold tracking-tight md:text-3xl">
            AML Console
          </h1>
          <p className="mt-1 max-w-2xl text-[13.5px] text-white/60">
            Drop a CSV of transactions or paste rows below. Every score is the
            sum of weighted, named detectors — including a fuzzy-matched
            sanctions screen against the bundled watchlist. Open the what-if
            panel to retune weights and watch the leaderboard shift live.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            className={`btn ${showWhatIf ? "ring-1 ring-teal-400/40" : ""}`}
            onClick={() => setShowWhatIf((v) => !v)}
          >
            {showWhatIf ? "Hide what-if" : "What-if simulator"}
          </button>
          <button className="btn" onClick={() => setCsv(SAMPLE)}>
            Reset sample
          </button>
          <button className="btn-primary" onClick={onScore} disabled={loading}>
            {loading ? "Scoring…" : `Score ${txs.length} txs`}
          </button>
        </div>
      </header>

      {/* What-if simulator */}
      {showWhatIf && (
        <section className="glass-strong p-5">
          <div className="flex flex-wrap items-baseline justify-between gap-3">
            <div>
              <h2 className="text-lg font-semibold">What-if · weight simulator</h2>
              <p className="mt-1 text-[12.5px] text-white/55">
                Tweak any detector's weight; the leaderboard re-scores in
                ~250ms. Each weight is clamped to{" "}
                <span className="font-mono">[0, {MAX_WEIGHT}]</span>. Reset
                returns to the canonical rule set.
              </p>
            </div>
            <button
              className="btn-ghost"
              onClick={resetWeights}
              disabled={!Object.keys(weights).length}
            >
              Reset weights
            </button>
          </div>
          <div className="mt-4 grid gap-x-6 gap-y-4 md:grid-cols-2">
            {DETECTOR_ORDER.map((k) => {
              const baseline = effectiveWeights[k] ?? 0;
              const current = typeof weights[k] === "number" ? weights[k]! : baseline;
              return (
                <div key={k}>
                  <div className="mb-1 flex items-baseline justify-between">
                    <span
                      className={`text-[12.5px] font-medium ${
                        isOverridden(k) ? "text-teal-300" : "text-white/85"
                      }`}
                    >
                      {DETECTOR_LABELS[k]}
                      {isOverridden(k) && (
                        <span className="ml-2 font-mono text-[10.5px] text-white/45">
                          (override)
                        </span>
                      )}
                    </span>
                    <span className="font-mono text-[11px] tabular-nums text-white/65">
                      {current.toFixed(0)}
                    </span>
                  </div>
                  <input
                    type="range"
                    min={0}
                    max={MAX_WEIGHT}
                    step={1}
                    value={current}
                    onChange={(e) =>
                      setWeights((w) => ({ ...w, [k]: Number(e.target.value) }))
                    }
                    className="w-full accent-teal-400"
                  />
                </div>
              );
            })}
          </div>
        </section>
      )}

      {/* Input + Summary */}
      <section className="grid gap-5 lg:grid-cols-[1.1fr_1fr]">
        <div
          className={`glass p-4 ${drag ? "dropzone-active" : ""}`}
          onDragOver={(e) => {
            e.preventDefault();
            setDrag(true);
          }}
          onDragLeave={() => setDrag(false)}
          onDrop={onDrop}
        >
          <div className="mb-2 flex items-center justify-between">
            <span className="label !mb-0">Input · CSV</span>
            <button
              type="button"
              className="text-[12px] text-teal-400 hover:underline"
              onClick={() => fileRef.current?.click()}
            >
              Upload file
            </button>
            <input
              ref={fileRef}
              type="file"
              accept=".csv,text/csv"
              hidden
              onChange={(e) => onFile(e.target.files?.[0] ?? null)}
            />
          </div>
          <div className="dropzone rounded-xl">
            <textarea
              value={csv}
              onChange={(e) => setCsv(e.target.value)}
              spellCheck={false}
              className="scroll-thin h-72 w-full resize-none bg-transparent p-3 font-mono text-[12px] text-white/85 outline-none"
            />
          </div>
          <p className="mt-2 text-[11px] text-white/45">
            Optional <span className="font-mono">subject_name</span> /{" "}
            <span className="font-mono">counterparty_name</span> columns enable
            sanctions screening on the parties.
          </p>
          {err && <p className="mt-3 text-[12px] text-rose-300">{err}</p>}
        </div>

        <div className="glass p-5">
          <div className="label">Run summary</div>
          {!resp && (
            <div className="grid h-72 place-items-center text-center text-white/45">
              <div>
                <div className="text-3xl">∅</div>
                <div className="mt-2 text-[13px]">Score a batch to populate.</div>
              </div>
            </div>
          )}
          {resp && (
            <div>
              <div className="grid grid-cols-3 gap-3">
                <Tile label="Accounts" value={resp.summary.total_accounts} />
                <Tile label="Transactions" value={resp.summary.total_transactions} />
                <Tile
                  label="Alerted (≥60)"
                  value={resp.summary.alerted}
                  warn={resp.summary.alerted > 0}
                />
                <Tile label="Highest" value={resp.summary.highest_score} />
                <Tile label="Average" value={resp.summary.average_score} />
                <Tile
                  label="Sanctions"
                  value={resp.summary.sanctions_alerted ?? 0}
                  warn={(resp.summary.sanctions_alerted ?? 0) > 0}
                />
              </div>

              <div className="mt-5">
                <div className="label">Accounts (sorted by risk)</div>
                <div className="scroll-thin max-h-56 space-y-2 overflow-y-auto pr-1">
                  {resp.accounts.map((a) => (
                    <button
                      key={a.account_id}
                      onClick={() => setSelected(a.account_id)}
                      className={`band-${a.band} flex w-full items-center justify-between gap-3 rounded-xl border px-3 py-2 text-left transition hover:translate-y-[-1px] ${
                        selected === a.account_id
                          ? "ring-1 ring-white/30"
                          : ""
                      }`}
                    >
                      <span className="flex min-w-0 flex-col">
                        <span className="font-mono text-[12.5px] text-white/85">
                          {a.account_id}
                        </span>
                        {a.display_name && (
                          <span className="truncate text-[10.5px] text-white/55">
                            {a.display_name}
                          </span>
                        )}
                      </span>
                      <span className="flex items-center gap-2 text-[11px] uppercase tracking-wider text-white/55">
                        {a.sanctions_hits.length > 0 && (
                          <span className="rounded-md border border-rose-400/40 bg-rose-500/10 px-1.5 py-0.5 text-[9.5px] text-rose-300">
                            sanctions
                          </span>
                        )}
                        <span>{a.band}</span>
                      </span>
                      <span className="text-[14px] font-semibold tabular-nums">
                        {a.risk_score.toFixed(0)}
                      </span>
                    </button>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>
      </section>

      {/* Detail panel */}
      {selectedReport && (
        <section className="glass-strong p-5 md:p-6">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="flex items-center gap-4">
              <ScoreRing
                score={selectedReport.risk_score}
                band={selectedReport.band}
              />
              <div>
                <div className="label">Account</div>
                <div className="font-mono text-lg">
                  {selectedReport.account_id}
                </div>
                {selectedReport.display_name && (
                  <div className="mt-0.5 text-[12.5px] text-white/75">
                    {selectedReport.display_name}
                  </div>
                )}
                <div className="mt-1 text-[12px] text-white/55">
                  {selectedReport.counterparty_count} counterparties · in{" "}
                  ₹{selectedReport.inbound_total.toLocaleString()} · out ₹
                  {selectedReport.outbound_total.toLocaleString()}
                </div>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <button
                className="btn"
                onClick={() =>
                  navigator.clipboard.writeText(JSON.stringify(selectedReport, null, 2))
                }
              >
                Copy JSON
              </button>
              <button className="btn-primary" onClick={onSar}>
                Generate SAR
              </button>
            </div>
          </div>

          <div className="mt-5 grid gap-5 md:grid-cols-[1.1fr_1fr]">
            <div className="rounded-xl border border-white/10 bg-black/20 p-4">
              <div className="label">Factor breakdown</div>
              <FactorBars factors={selectedReport.factors} />
            </div>
            <div className="rounded-xl border border-white/10 bg-black/20 p-4">
              <div className="label">Transaction graph</div>
              <TxGraph
                edges={selectedReport.edges.map((e) => ({
                  from: e.from,
                  to: e.to,
                  amount: e.amount,
                }))}
                highlight={selectedReport.account_id}
              />
              <div className="mt-2 text-[11px] text-white/45">
                Edge thickness scales with transfer amount; the highlighted node
                is the subject account.
              </div>
            </div>
          </div>

          {/* Sanctions hits */}
          {selectedReport.sanctions_hits.length > 0 && (
            <div className="mt-5 rounded-xl border border-rose-400/25 bg-rose-500/[0.04] p-4">
              <div className="flex items-baseline justify-between">
                <div className="label !mb-0 text-rose-300">
                  Sanctions hits · {selectedReport.sanctions_hits.length}
                </div>
                <span className="font-mono text-[11px] text-white/45">
                  threshold ≥ {((resp?.sanctions_threshold ?? 0.65) * 100).toFixed(0)}%
                </span>
              </div>
              <div className="mt-3 grid gap-3 md:grid-cols-2">
                {selectedReport.sanctions_hits.map((h) => (
                  <div
                    key={h.entity_id + h.queried_party}
                    className="flex items-start gap-3 rounded-xl border border-white/10 bg-black/30 p-3"
                  >
                    <SimilarityRing similarity={h.similarity} grade={h.grade} size={64} />
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span
                          className={`inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-[10px] uppercase tracking-wider ${GRADE_TINT[h.grade]}`}
                        >
                          {h.grade}
                        </span>
                        <span className="font-mono text-[10.5px] text-white/55">
                          {h.list} · {h.jurisdiction}
                        </span>
                        <span className="rounded-md border border-white/10 bg-white/[0.04] px-1.5 py-0.5 font-mono text-[10px] text-white/55">
                          {h.queried_role}
                        </span>
                      </div>
                      <div className="mt-1.5 truncate text-[13px] font-semibold tracking-tight">
                        {h.name}
                      </div>
                      <div className="mt-0.5 truncate text-[11.5px] text-white/55">
                        “{h.queried_name}” → matched on “{h.matched_alias}”
                      </div>
                      <div className="mt-1 line-clamp-2 text-[11.5px] text-white/55">
                        {h.reason}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {sar && (
            <div className="mt-5 rounded-xl border border-teal-400/25 bg-teal-500/[0.04] p-4">
              <div className="flex items-center justify-between">
                <div className="label !mb-0 text-teal-400">
                  SAR draft · {sar.id}
                </div>
                <div className="flex items-center gap-2">
                  <button
                    className="btn-ghost"
                    onClick={() => navigator.clipboard.writeText(sar.md)}
                  >
                    Copy markdown
                  </button>
                </div>
              </div>
              <pre className="scroll-thin mt-3 max-h-80 overflow-auto whitespace-pre-wrap rounded-lg bg-black/30 p-3 font-mono text-[12px] text-white/80">
                {sar.md}
              </pre>
            </div>
          )}
        </section>
      )}
    </div>
  );
}

function Tile({
  label,
  value,
  warn = false,
  mono = false,
}: {
  label: string;
  value: number | string;
  warn?: boolean;
  mono?: boolean;
}) {
  return (
    <div className="rounded-xl border border-white/10 bg-black/25 p-3">
      <div className="text-[10.5px] uppercase tracking-wider text-white/45">
        {label}
      </div>
      <div
        className={`mt-1 ${mono ? "font-mono text-[12px]" : "text-xl font-semibold"} ${
          warn ? "text-amber-300" : "text-white"
        }`}
      >
        {value}
      </div>
    </div>
  );
}
