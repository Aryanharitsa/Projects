"use client";

import {
  DragEvent,
  Suspense,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useSearchParams } from "next/navigation";
import DeltaBar from "../../components/DeltaBar";
import EntityCard from "../../components/EntityCard";
import RiskGraph from "../../components/RiskGraph";
import ScoreRing from "../../components/ScoreRing";
import {
  NetworkAnalyze,
  NetworkAttribution,
  NetworkCounterfactual,
  Tx,
  analyzeNetwork,
  attributionNetwork,
  counterfactualNetwork,
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
A6,B,180000,2026-04-24T09:00:00Z,RTGS,IN,,Mehta Trading LLP,Aurelia Shell Limited
A6,M2,42000,2026-04-24T11:00:00Z,UPI,IN,,Mehta Trading LLP,Trident Exports
A7,M1,41000,2026-04-25T09:00:00Z,UPI,IN,,Bhargav Holdings,Trident Exports
A7,M3,44000,2026-04-25T13:00:00Z,UPI,IN,,Bhargav Holdings,Trident Exports
`;

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

type SortKey = "network" | "risk" | "lift" | "flow";

export default function NetworkPage() {
  return (
    <Suspense fallback={null}>
      <NetworkPageInner />
    </Suspense>
  );
}

function NetworkPageInner() {
  const params = useSearchParams();
  const focusFromQuery = params.get("focus");

  const [csv, setCsv] = useState(SAMPLE);
  const [resp, setResp] = useState<NetworkAnalyze | null>(null);
  const [cf, setCf] = useState<NetworkCounterfactual | null>(null);
  const [attrib, setAttrib] = useState<NetworkAttribution | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [ablated, setAblated] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(false);
  const [cfLoading, setCfLoading] = useState(false);
  const [attribLoading, setAttribLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [drag, setDrag] = useState(false);
  const [sortKey, setSortKey] = useState<SortKey>("network");
  const [showCsv, setShowCsv] = useState(false);

  const fileRef = useRef<HTMLInputElement>(null);

  const txs = useMemo(() => parseCsv(csv), [csv]);

  const runAnalyse = useCallback(async () => {
    setLoading(true);
    setErr(null);
    setCf(null);
    setAttrib(null);
    try {
      const out = await analyzeNetwork(parseCsv(csv));
      setResp(out);
      // Preserve current selection if it still exists.
      setSelected((cur) => {
        if (!cur) return null;
        return out.entities.some((e) => e.id === cur) ? cur : null;
      });
    } catch (e: any) {
      setErr(e?.message || String(e));
    } finally {
      setLoading(false);
    }
  }, [csv]);

  // Initial run on mount.
  useEffect(() => {
    runAnalyse();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Honour ?focus= query string.
  useEffect(() => {
    if (focusFromQuery && resp) {
      // Resolve party id → cluster id.
      for (const ent of resp.entities) {
        if (ent.members.includes(focusFromQuery) || ent.id === focusFromQuery) {
          setSelected(ent.id);
          break;
        }
      }
    }
  }, [focusFromQuery, resp]);

  // Run attribution when a single-member entity is selected.
  useEffect(() => {
    if (!resp || !selected) {
      setAttrib(null);
      return;
    }
    const ent = resp.entities.find((e) => e.id === selected);
    if (!ent || ent.is_aggregate) {
      // For aggregate clusters attribution is per-account and would need
      // a member chooser. Keep it simple — only run for primary accounts.
      setAttrib(null);
      return;
    }
    const accountId = ent.id;
    setAttribLoading(true);
    let cancelled = false;
    attributionNetwork(txs, accountId)
      .then((res) => {
        if (!cancelled) setAttrib(res);
      })
      .catch(() => {
        if (!cancelled) setAttrib(null);
      })
      .finally(() => {
        if (!cancelled) setAttribLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [resp, selected, txs]);

  const runCounterfactual = useCallback(async () => {
    if (ablated.size === 0) return;
    setCfLoading(true);
    try {
      const out = await counterfactualNetwork(txs, Array.from(ablated));
      setCf(out);
    } catch (e: any) {
      setErr(e?.message || String(e));
    } finally {
      setCfLoading(false);
    }
  }, [ablated, txs]);

  const clearAblation = () => {
    setAblated(new Set());
    setCf(null);
  };

  const onFile = (file: File) => {
    const reader = new FileReader();
    reader.onload = () => setCsv(String(reader.result || ""));
    reader.readAsText(file);
  };
  const onDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDrag(false);
    const f = e.dataTransfer.files[0];
    if (f) onFile(f);
  };

  const sortedEntities = useMemo(() => {
    if (!resp) return [];
    const xs = [...resp.entities];
    if (sortKey === "network") xs.sort((a, b) => b.network_risk - a.network_risk);
    if (sortKey === "risk") xs.sort((a, b) => b.risk_score - a.risk_score);
    if (sortKey === "lift") xs.sort((a, b) => b.network_delta - a.network_delta);
    if (sortKey === "flow")
      xs.sort(
        (a, b) =>
          b.inbound_total + b.outbound_total - (a.inbound_total + a.outbound_total),
      );
    return xs;
  }, [resp, sortKey]);

  const selectedEntity = resp?.entities.find((e) => e.id === selected) || null;
  const deltasBySelected = useMemo(() => {
    if (!cf || !selected) return null;
    return cf.deltas.find((d) => d.entity_id === selected) || null;
  }, [cf, selected]);

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <span className="pill pill-ok">round 4 · day 20</span>
          <h1 className="mt-3 text-2xl font-semibold tracking-tight md:text-3xl">
            <span className="grad-text">Network intelligence.</span>
          </h1>
          <p className="mt-1.5 max-w-2xl text-[14px] text-white/65">
            Per-account scoring catches one account at a time. Real laundering
            is networked — we cluster likely-same entities, propagate risk
            along the money flow, then let you{" "}
            <span className="text-white/85">ablate any node</span> to see what
            the picture looks like without them.
          </p>
        </div>
        <div className="flex gap-2">
          <button onClick={runAnalyse} disabled={loading} className="btn-primary">
            {loading ? "Analysing…" : "Re-run analysis"}
          </button>
          <button onClick={() => setShowCsv((v) => !v)} className="btn">
            {showCsv ? "Hide" : "Edit"} input
          </button>
        </div>
      </div>

      {err && (
        <div className="rounded-xl border border-rose-400/30 bg-rose-500/10 px-4 py-2.5 text-[13px] text-rose-200">
          {err}
        </div>
      )}

      {/* Input zone */}
      {showCsv && (
        <div className="glass p-5">
          <div className="mb-3 flex items-center justify-between">
            <span className="label !mb-0">Input · CSV</span>
            <div className="flex gap-2">
              <button onClick={() => fileRef.current?.click()} className="btn">
                Upload CSV
              </button>
              <button onClick={() => setCsv(SAMPLE)} className="btn-ghost">
                Reset sample
              </button>
              <input
                ref={fileRef}
                type="file"
                accept=".csv,text/csv"
                hidden
                onChange={(e) => e.target.files?.[0] && onFile(e.target.files[0])}
              />
            </div>
          </div>
          <div
            onDragOver={(e) => {
              e.preventDefault();
              setDrag(true);
            }}
            onDragLeave={() => setDrag(false)}
            onDrop={onDrop}
            className={`dropzone rounded-xl p-1 ${drag ? "dropzone-active" : ""}`}
          >
            <textarea
              value={csv}
              onChange={(e) => setCsv(e.target.value)}
              spellCheck={false}
              className="scroll-thin h-44 w-full resize-y rounded-xl bg-transparent p-3 font-mono text-[11.5px] leading-relaxed text-white/85 outline-none"
            />
          </div>
        </div>
      )}

      {/* Stats banner */}
      {resp && (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
          <div className="ws-net-stat">
            <div className="text-[11px] uppercase tracking-wider text-white/45">
              Resolved entities
            </div>
            <div className="mt-1 flex items-baseline gap-2">
              <span className="text-3xl font-semibold tracking-tight text-white">
                {resp.summary.total_clusters}
              </span>
              <span className="text-[12px] text-white/45">
                from {resp.summary.total_parties} parties
              </span>
            </div>
          </div>
          <div className="ws-net-stat ws-net-stat-violet">
            <div className="text-[11px] uppercase tracking-wider text-white/45">
              Aggregate clusters
            </div>
            <div className="mt-1 text-3xl font-semibold tracking-tight text-violet-200">
              {resp.summary.multi_member_clusters}
            </div>
            <div className="mt-0.5 text-[11.5px] text-white/45">
              merged by name + fingerprint
            </div>
          </div>
          <div className="ws-net-stat ws-net-stat-amber">
            <div className="text-[11px] uppercase tracking-wider text-white/45">
              Avg network lift
            </div>
            <div className="mt-1 text-3xl font-semibold tracking-tight text-amber-200">
              {resp.summary.avg_network_lift > 0 ? "+" : ""}
              {resp.summary.avg_network_lift.toFixed(1)}
            </div>
            <div className="mt-0.5 text-[11.5px] text-white/45">
              network_risk − risk_score
            </div>
          </div>
          <div className="ws-net-stat">
            <div className="text-[11px] uppercase tracking-wider text-white/45">
              Components
            </div>
            <div className="mt-1 text-3xl font-semibold tracking-tight text-white">
              {resp.summary.components}
            </div>
            <div className="mt-0.5 text-[11.5px] text-white/45">
              density {resp.summary.density.toFixed(3)}
            </div>
          </div>
          <div className="ws-net-stat ws-net-stat-rose">
            <div className="text-[11px] uppercase tracking-wider text-white/45">
              Top lift
            </div>
            <div className="mt-1 truncate text-lg font-semibold tracking-tight text-white">
              {resp.entities.find((e) => e.id === resp.summary.top_lift_entity_id)
                ?.display_name || "—"}
            </div>
            <div className="mt-0.5 text-[11.5px] text-white/45">
              biggest jump from neighbourhood
            </div>
          </div>
        </div>
      )}

      {/* Main: graph + sidebar */}
      {resp && (
        <div className="grid gap-5 lg:grid-cols-[1.55fr_1fr]">
          {/* Graph */}
          <div className="glass p-4">
            <div className="mb-2 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="pill pill-ok">graph</span>
                <span className="text-[12px] text-white/55">
                  {resp.entities.length} nodes · {resp.edges.length} edges
                </span>
              </div>
              <span className="text-[11px] text-white/45">
                click a node to inspect · click again to clear
              </span>
            </div>
            <RiskGraph
              entities={resp.entities}
              edges={resp.edges}
              selectedId={selected}
              ablatedIds={ablated}
              onSelect={setSelected}
            />
          </div>

          {/* Sidebar */}
          <div className="glass p-4">
            <div className="mb-3 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="pill">entities</span>
                <span className="text-[11.5px] text-white/45">
                  {sortedEntities.length} resolved
                </span>
              </div>
              <select
                value={sortKey}
                onChange={(e) => setSortKey(e.target.value as SortKey)}
                className="rounded-lg border border-white/10 bg-black/40 px-2 py-1 text-[12px] text-white/75"
              >
                <option value="network">by network risk</option>
                <option value="risk">by per-account risk</option>
                <option value="lift">by network lift</option>
                <option value="flow">by total flow</option>
              </select>
            </div>
            <div className="scroll-thin grid max-h-[540px] gap-1.5 overflow-y-auto pr-1">
              {sortedEntities.map((e) => (
                <EntityCard
                  key={e.id}
                  entity={e}
                  selected={selected === e.id}
                  ablated={ablated.has(e.id)}
                  onClick={() => setSelected(e.id === selected ? null : e.id)}
                  onAblateToggle={() =>
                    setAblated((cur) => {
                      const next = new Set(cur);
                      if (next.has(e.id)) next.delete(e.id);
                      else next.add(e.id);
                      return next;
                    })
                  }
                />
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Counterfactual */}
      {resp && (
        <div className="glass p-5 md:p-6">
          <div className="mb-3 flex flex-wrap items-end justify-between gap-3">
            <div>
              <div className="text-[11px] uppercase tracking-wider text-white/45">
                Counterfactual
              </div>
              <div className="mt-1 text-lg font-semibold">
                What if these entities never existed?
              </div>
              <div className="mt-1 max-w-2xl text-[13px] text-white/55">
                Toggle the − button on any sidebar row to ablate it. We re-run
                the full pipeline with those parties removed and surface the
                per-entity score deltas.
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              {ablated.size > 0 && (
                <span className="pill pill-warn">
                  {ablated.size} ablated
                </span>
              )}
              <button onClick={clearAblation} className="btn-ghost" disabled={ablated.size === 0}>
                Clear
              </button>
              <button
                onClick={runCounterfactual}
                disabled={ablated.size === 0 || cfLoading}
                className="btn-primary"
              >
                {cfLoading ? "Re-scoring…" : `Re-score without ${ablated.size || ""}`}
              </button>
            </div>
          </div>

          {ablated.size === 0 && !cf && (
            <div className="rounded-xl border border-dashed border-white/10 bg-white/[0.02] p-5 text-center text-[13px] text-white/45">
              No entities ablated. Pick one or more from the sidebar to begin.
            </div>
          )}

          {cf && (
            <>
              <div className="ws-net-cf-banner mb-4">
                <div className="text-[11px] uppercase tracking-wider text-white/55">
                  Network impact
                </div>
                <div className="mt-1 flex flex-wrap items-baseline gap-x-6 gap-y-2">
                  <div>
                    <span className="text-3xl font-semibold tracking-tight text-white">
                      {cf.summary.network_avg_after.toFixed(1)}
                    </span>
                    <span className="ml-2 text-[12px] text-white/55">
                      avg network risk (was {cf.summary.network_avg_before.toFixed(1)})
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span
                      className={
                        cf.summary.network_avg_change < 0
                          ? "text-teal-300"
                          : cf.summary.network_avg_change > 0
                          ? "text-amber-300"
                          : "text-white/55"
                      }
                    >
                      {cf.summary.network_avg_change > 0 ? "+" : ""}
                      {cf.summary.network_avg_change.toFixed(2)}
                    </span>
                    <span className="text-[12px] text-white/55">change</span>
                  </div>
                  <div className="text-[12px] text-white/55">
                    alerts: {cf.summary.alerted_before} → {cf.summary.alerted_after}
                  </div>
                  <div className="text-[12px] text-white/55">
                    {cf.txs_removed} transactions removed
                  </div>
                </div>
              </div>

              <div className="grid gap-1.5">
                <div className="grid grid-cols-[1.4fr_1fr_1fr_1fr] gap-3 px-2 pb-2 text-[10.5px] uppercase tracking-wider text-white/40">
                  <span>Entity</span>
                  <span>Risk before → after</span>
                  <span>Network before → after</span>
                  <span>Δ network</span>
                </div>
                {cf.deltas.slice(0, 12).map((d) => (
                  <div
                    key={d.entity_id}
                    className="grid grid-cols-[1.4fr_1fr_1fr_1fr] items-center gap-3 rounded-lg px-2 py-1.5 hover:bg-white/[0.03]"
                  >
                    <div className="flex items-center gap-2 truncate">
                      <span className="truncate text-[13px] text-white/85">
                        {d.display_name}
                      </span>
                      {ablated.has(d.entity_id) && (
                        <span className="pill pill-bad !py-0 !text-[9.5px]">ablated</span>
                      )}
                    </div>
                    <div className="font-mono text-[12px] text-white/65">
                      {d.risk_before.toFixed(1)} → {d.risk_after.toFixed(1)}
                    </div>
                    <div className="font-mono text-[12px] text-white/65">
                      {d.network_before.toFixed(1)} → {d.network_after.toFixed(1)}
                    </div>
                    <div className="flex items-center gap-3">
                      <DeltaBar value={d.network_delta} />
                      <span
                        className={`w-12 text-right font-mono text-[12px] ${
                          d.network_delta < -0.5
                            ? "text-teal-300"
                            : d.network_delta > 0.5
                            ? "text-amber-300"
                            : "text-white/55"
                        }`}
                      >
                        {d.network_delta > 0 ? "+" : ""}
                        {d.network_delta.toFixed(1)}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      )}

      {/* Selected entity — attribution + details */}
      {selectedEntity && (
        <div className="grid gap-5 lg:grid-cols-[1fr_1.4fr]">
          {/* Detail */}
          <div className="glass p-5">
            <div className="flex items-center gap-4">
              <ScoreRing
                score={selectedEntity.network_risk}
                band={selectedEntity.band}
                size={84}
              />
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-1.5">
                  <h2 className="truncate text-xl font-semibold tracking-tight">
                    {selectedEntity.display_name}
                  </h2>
                  {selectedEntity.sanctioned && (
                    <span className="pill pill-bad">sanctions</span>
                  )}
                </div>
                <div className="mt-1 flex flex-wrap gap-2 text-[11.5px] text-white/55">
                  <span className="font-mono">{selectedEntity.id}</span>
                  {selectedEntity.is_aggregate && (
                    <>
                      <span className="text-white/25">·</span>
                      <span>
                        merged {selectedEntity.member_count} accounts:{" "}
                        <span className="font-mono text-white/80">
                          {selectedEntity.members.join(", ")}
                        </span>
                      </span>
                    </>
                  )}
                </div>
              </div>
            </div>
            <div className="mt-4 grid grid-cols-3 gap-3">
              <Stat label="Per-account risk" value={selectedEntity.risk_score.toFixed(1)} />
              <Stat
                label="Network lift"
                value={`${selectedEntity.network_delta > 0 ? "+" : ""}${selectedEntity.network_delta.toFixed(1)}`}
                tone={selectedEntity.network_delta > 1 ? "amber" : "neutral"}
              />
              <Stat
                label="Net flow"
                value={shortIN(
                  selectedEntity.inbound_total - selectedEntity.outbound_total,
                )}
              />
            </div>
            {selectedEntity.flags.length > 0 && (
              <div className="mt-3 flex flex-wrap gap-1.5">
                {selectedEntity.flags.map((f) => (
                  <span key={f} className="ws-net-flag">
                    {f}
                  </span>
                ))}
              </div>
            )}
            <div className="mt-4 text-[12px] text-white/45">
              In:{" "}
              <span className="font-mono text-white/75">
                ₹{Math.round(selectedEntity.inbound_total).toLocaleString("en-IN")}
              </span>
              {" · "}Out:{" "}
              <span className="font-mono text-white/75">
                ₹{Math.round(selectedEntity.outbound_total).toLocaleString("en-IN")}
              </span>
            </div>
            {deltasBySelected && (
              <div className="mt-4 rounded-xl border border-violet-400/20 bg-violet-500/[0.06] p-3">
                <div className="text-[11px] uppercase tracking-wider text-violet-300/85">
                  In current counterfactual
                </div>
                <div className="mt-1 flex flex-wrap items-baseline gap-x-4 text-[12.5px] text-white/75">
                  <span>
                    risk{" "}
                    <span className="font-mono">
                      {deltasBySelected.risk_before.toFixed(1)} →{" "}
                      {deltasBySelected.risk_after.toFixed(1)}
                    </span>
                  </span>
                  <span>
                    network{" "}
                    <span className="font-mono">
                      {deltasBySelected.network_before.toFixed(1)} →{" "}
                      {deltasBySelected.network_after.toFixed(1)}
                    </span>
                  </span>
                </div>
              </div>
            )}
          </div>

          {/* Attribution */}
          <div className="glass p-5">
            <div className="mb-3 flex items-center justify-between">
              <div>
                <div className="text-[11px] uppercase tracking-wider text-white/45">
                  Attribution
                </div>
                <div className="text-[15px] font-semibold">
                  Which counterparties contribute most to{" "}
                  <span className="text-white/85">
                    {selectedEntity.display_name}
                  </span>
                  ?
                </div>
              </div>
              {attribLoading && (
                <span className="pill pill-warn">computing…</span>
              )}
            </div>
            {!attrib && !attribLoading && (
              <div className="rounded-xl border border-dashed border-white/10 bg-white/[0.02] p-5 text-[12.5px] text-white/45">
                Attribution runs leave-one-counterparty-out on a single primary
                account. Aggregate clusters need a member-chooser, not added
                here yet — pick a non-aggregate entity to see lifts.
              </div>
            )}
            {attrib && attrib.counterparties.length === 0 && (
              <div className="rounded-xl border border-dashed border-white/10 bg-white/[0.02] p-5 text-[12.5px] text-white/45">
                No counterparty contributes lift — the account's risk does not
                depend on any single partner.
              </div>
            )}
            {attrib && attrib.counterparties.length > 0 && (
              <>
                <div className="mb-2 text-[12.5px] text-white/55">
                  Baseline score{" "}
                  <span className="font-mono text-white/85">
                    {attrib.baseline_score.toFixed(1)}
                  </span>
                  . Each row is the drop if all transactions to/from that
                  counterparty are removed.
                </div>
                <div className="space-y-0.5">
                  {attrib.counterparties.map((c) => {
                    const liftPct = Math.max(0, Math.min(1, c.lift / Math.max(1, attrib.baseline_score)));
                    return (
                      <div key={c.counterparty} className="ws-net-attrib-row">
                        <div className="truncate">
                          <span className="font-mono text-[12.5px] text-white/85">
                            {c.counterparty}
                          </span>
                          <div className="text-[10.5px] text-white/40">
                            {c.tx_count} tx · ₹
                            {Math.round(c.amount_total).toLocaleString("en-IN")}
                          </div>
                        </div>
                        <div className="ws-net-attrib-bar">
                          <span style={{ width: `${liftPct * 100}%` }} />
                        </div>
                        <div className="text-right font-mono text-[12.5px] text-amber-200">
                          −{c.lift.toFixed(1)}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </>
            )}
          </div>
        </div>
      )}

      {/* Formula footer */}
      {resp && (
        <div className="glass p-5">
          <div className="text-[11px] uppercase tracking-wider text-white/45">
            How it works
          </div>
          <div className="mt-2 grid gap-4 md:grid-cols-3">
            <FormulaCard
              title="Entity resolution"
              body={
                <>
                  Cluster ids that look like the same hand: fuzzy name match
                  (Σ {resp.params.name_tau.toFixed(2)} threshold, reuses
                  watchlist primitives) OR shared-counterparty Jaccard ≥{" "}
                  {resp.params.counterparty_tau.toFixed(2)}. Union-Find
                  closes transitively.
                </>
              }
            />
            <FormulaCard
              title="Risk propagation"
              body={
                <>
                  Biased PageRank{" "}
                  <span className="font-mono text-teal-300/85">
                    r ← (1−α) s + α Wᵀ r
                  </span>{" "}
                  with α = {resp.params.pr_alpha.toFixed(2)}, seed = per-account
                  risk, W = row-stochastic money flow. Final score blends 55%
                  per-account + 45% network so peer-tainted nodes lift visibly.
                </>
              }
            />
            <FormulaCard
              title="Counterfactual"
              body={
                <>
                  Ablate a set, drop every transaction touching any of those
                  parties, rerun the full pipeline, return per-entity deltas.
                  Auditable, deterministic — the same ablation always produces
                  the same answer.
                </>
              }
            />
          </div>
        </div>
      )}
    </div>
  );
}

function Stat({
  label,
  value,
  tone = "neutral",
}: {
  label: string;
  value: string;
  tone?: "neutral" | "amber";
}) {
  const color = tone === "amber" ? "text-amber-200" : "text-white/90";
  return (
    <div className="rounded-xl border border-white/10 bg-white/[0.02] p-3">
      <div className="text-[10.5px] uppercase tracking-wider text-white/40">
        {label}
      </div>
      <div className={`mt-1 text-lg font-semibold tracking-tight ${color}`}>
        {value}
      </div>
    </div>
  );
}

function FormulaCard({ title, body }: { title: string; body: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-white/10 bg-black/20 p-4">
      <div className="text-[12px] font-semibold text-white/85">{title}</div>
      <div className="mt-1.5 text-[12.5px] leading-relaxed text-white/55">
        {body}
      </div>
    </div>
  );
}

function shortIN(value: number): string {
  const abs = Math.abs(value);
  const sign = value < 0 ? "−" : "";
  if (abs >= 10_00_000) return `${sign}₹${(abs / 10_00_000).toFixed(2)} Cr`;
  if (abs >= 1_000) return `${sign}₹${(abs / 1_000).toFixed(1)}k`;
  return `${sign}₹${Math.round(abs).toLocaleString("en-IN")}`;
}
