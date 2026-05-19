"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AttributionContribution,
  CaseNetworkPanel as CaseNetworkPayload,
  EntityAttributionMember,
  NetworkDelta,
  Tx,
  getCaseNetwork,
  runCaseNetworkClearing,
} from "../lib/api";
import RiskGraph from "./RiskGraph";

/** The case-detail surface for network intelligence.
 *
 * Auto-fetches `/aml/cases/{id}/network`, which runs entity resolution
 * + biased PageRank + leave-one-counterparty-out + a "clear this case"
 * counterfactual against the persisted neighbourhood snapshot. Renders:
 *
 *  - 4-tile headline (solo risk / network risk / lift / "if cleared" deltas)
 *  - 1-hop subgraph (centred on the case's resolved entity)
 *  - per-member breakdown when the subject is an aggregate cluster
 *  - top-N counterparty attribution bars (member-aware for aggregates)
 *  - peer-lift list — entities whose network risk drops the most if
 *    this case is ablated (the "who else depends on this account?" view)
 *
 * Empty state (legacy case opened without a transactions snapshot)
 * exposes a single re-run path: if the caller (the AML console) passes
 * `fallbackTransactions`, a button POSTs to `/network/clearing` to
 * compute the panel on demand without persisting.
 */
export default function CaseNetworkPanel({
  caseId,
  accountId,
  fallbackTransactions,
  onSelectEntity,
}: {
  caseId: string;
  accountId: string;
  fallbackTransactions?: Tx[];
  onSelectEntity?: (entityId: string | null) => void;
}) {
  const [panel, setPanel] = useState<CaseNetworkPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [hops, setHops] = useState<0 | 1 | 2>(1);
  const [focus, setFocus] = useState<string | null>(null);
  const [runningFallback, setRunningFallback] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const out = await getCaseNetwork(caseId, { hops });
      setPanel(out);
    } catch (e: any) {
      setErr(e.message || "Failed to load network panel");
    } finally {
      setLoading(false);
    }
  }, [caseId, hops]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const onRunWithFallback = useCallback(async () => {
    if (!fallbackTransactions?.length) return;
    setRunningFallback(true);
    setErr(null);
    try {
      const out = await runCaseNetworkClearing(caseId, fallbackTransactions, { hops });
      setPanel(out);
    } catch (e: any) {
      setErr(e.message || "Re-run failed");
    } finally {
      setRunningFallback(false);
    }
  }, [caseId, fallbackTransactions, hops]);

  const headerControls = (
    <div className="flex items-center gap-2">
      <div className="ws-cnp-hops">
        {[0, 1, 2].map((h) => (
          <button
            key={h}
            className={hops === h ? "ws-cnp-hops-on" : ""}
            onClick={() => setHops(h as 0 | 1 | 2)}
            disabled={loading}
          >
            {h} hop{h === 1 ? "" : "s"}
          </button>
        ))}
      </div>
      <button
        className="btn-ghost px-2 py-1 text-[11px]"
        onClick={refresh}
        disabled={loading}
        title="Re-run analysis"
      >
        {loading ? "…" : "↻"}
      </button>
    </div>
  );

  if (loading && !panel) {
    return (
      <div className="ws-cnp-card">
        <div className="ws-cnp-head">
          <div>
            <div className="ws-cnp-eyebrow">Network intelligence</div>
            <div className="ws-cnp-title">Position in resolved entity graph</div>
          </div>
          {headerControls}
        </div>
        <div className="grid place-items-center py-10 text-white/45 text-[12.5px]">
          Resolving entities · propagating risk…
        </div>
      </div>
    );
  }

  if (!panel || !panel.available) {
    return (
      <div className="ws-cnp-card">
        <div className="ws-cnp-head">
          <div>
            <div className="ws-cnp-eyebrow">Network intelligence</div>
            <div className="ws-cnp-title">Position in resolved entity graph</div>
          </div>
          {headerControls}
        </div>
        <div className="ws-cnp-empty">
          <div className="ws-cnp-empty-icon">◌</div>
          <div className="text-[13px] text-white/75">
            {panel?.available === false
              ? panel.reason
              : err || "No data."}
          </div>
          {fallbackTransactions && fallbackTransactions.length > 0 && (
            <button
              className="btn-primary mt-3"
              onClick={onRunWithFallback}
              disabled={runningFallback}
            >
              {runningFallback
                ? "Running…"
                : `Run analysis with ${fallbackTransactions.length} input transactions`}
            </button>
          )}
          <div className="mt-3 text-[10.5px] text-white/35">
            account · <span className="font-mono">{accountId}</span>
          </div>
        </div>
        {err && (
          <div className="mt-3 text-[12px] text-rose-300">{err}</div>
        )}
      </div>
    );
  }

  // Type-narrowed: available === true
  const { subject, subgraph, attribution, clearing, snapshot_meta, full_summary, source } = panel;
  const subjectIsAgg = !!subject.is_aggregate;
  const subjectLift = subject.network_risk - subject.risk_score;
  const clearingChange = clearing.summary?.network_avg_change ?? 0;
  const clearedAlertedDelta =
    (clearing.summary?.alerted_after ?? 0) - (clearing.summary?.alerted_before ?? 0);

  return (
    <div className="ws-cnp-card">
      <div className="ws-cnp-head">
        <div>
          <div className="ws-cnp-eyebrow">Network intelligence</div>
          <div className="ws-cnp-title">Position in resolved entity graph</div>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-[10.5px] text-white/45">
            <span className="font-mono">{subject.id}</span>
            <span>·</span>
            <span>{subgraph.node_count} entities</span>
            <span>/</span>
            <span>{subgraph.edge_count} edges</span>
            <span>·</span>
            <span>graph total: {full_summary?.total_clusters ?? "—"}</span>
            {snapshot_meta && (
              <>
                <span>·</span>
                <span title={`snapshot saved at ${snapshot_meta.created_at_iso}`}>
                  snapshot · {snapshot_meta.tx_count} txs
                </span>
              </>
            )}
            {source === "client-supplied" && (
              <span className="ws-cnp-chip ws-cnp-chip-violet">live</span>
            )}
          </div>
        </div>
        {headerControls}
      </div>

      {err && <div className="mt-2 text-[12px] text-rose-300">{err}</div>}

      {/* 4 headline tiles */}
      <div className="ws-cnp-stats">
        <Tile
          label="solo risk"
          value={subject.risk_score.toFixed(0)}
          tone={bandTone(subject.band)}
          caption="per-account engine"
        />
        <Tile
          label="network risk"
          value={subject.network_risk.toFixed(0)}
          tone={bandTone(subject.band)}
          caption={subjectLift >= 0.5
            ? `peer-tainted +${subjectLift.toFixed(1)}`
            : subjectLift <= -0.5
              ? `peer-cleared ${subjectLift.toFixed(1)}`
              : "no peer effect"}
        />
        <Tile
          label="if cleared"
          value={`${clearingChange > 0 ? "+" : ""}${clearingChange.toFixed(1)}`}
          tone={clearingChange < 0 ? "teal" : clearingChange > 0 ? "amber" : "neutral"}
          caption="Δ network avg (post-ablation)"
        />
        <Tile
          label="alerted before/after"
          value={`${clearing.summary?.alerted_before ?? 0} → ${clearing.summary?.alerted_after ?? 0}`}
          tone={clearedAlertedDelta < 0 ? "teal" : clearedAlertedDelta > 0 ? "amber" : "neutral"}
          caption={`${clearing.txs_removed} txs removed`}
        />
      </div>

      {/* Graph + side panel */}
      <div className="ws-cnp-main">
        <div className="ws-cnp-graph">
          <RiskGraph
            entities={subgraph.entities}
            edges={subgraph.edges}
            selectedId={focus || subject.id}
            onSelect={(id) => {
              setFocus(id);
              onSelectEntity?.(id);
            }}
            width={620}
            height={400}
          />
          <div className="mt-2 flex items-center justify-between text-[10.5px] text-white/40">
            <span>
              centre = <span className="font-mono">{subject.display_name}</span>
              {subjectIsAgg && (
                <span className="ws-cnp-chip ws-cnp-chip-violet ml-2">
                  ×{subject.member_count}
                </span>
              )}
            </span>
            <Link href={`/network?focus=${encodeURIComponent(subject.id)}`} className="ws-cnp-link">
              Open in full network →
            </Link>
          </div>
        </div>

        <div className="ws-cnp-side">
          {/* Per-member breakdown for aggregates */}
          {subjectIsAgg && attribution.per_member && attribution.per_member.length > 0 && (
            <Section title="Aggregate cluster · per-member">
              <div className="ws-cnp-members">
                {attribution.per_member.map((m: EntityAttributionMember) => (
                  <div key={m.member_id} className="ws-cnp-member">
                    <span className="font-mono text-[11.5px] text-white/85">
                      {m.member_id}
                    </span>
                    <span
                      className={`ws-cnp-chip ws-cnp-chip-${bandTone(m.band)}`}
                    >
                      {m.band}
                    </span>
                    <span className="ml-auto tabular-nums text-[12px] text-white/90">
                      {m.baseline_score.toFixed(0)}
                    </span>
                  </div>
                ))}
                <div className="mt-1.5 text-[10.5px] text-white/40">
                  cluster baseline = max(members)
                </div>
              </div>
            </Section>
          )}

          {/* Attribution — counterparties driving the score */}
          <Section
            title="Counterparties driving the score"
            caption="leave-one-out lift"
          >
            {attribution.counterparties.length === 0 ? (
              <div className="text-[12px] text-white/50">No external counterparties.</div>
            ) : (
              <AttribBars
                rows={attribution.counterparties}
                baseline={attribution.baseline_score}
              />
            )}
          </Section>

          {/* Peer lifts — who depends on this case */}
          <Section
            title="Peers that drop most if cleared"
            caption="biggest network drop · 8 max"
          >
            {clearing.peer_lifts.length === 0 ? (
              <div className="text-[12px] text-white/50">
                No peers depend on this subject.
              </div>
            ) : (
              <PeerList lifts={clearing.peer_lifts} />
            )}
          </Section>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------

function Tile({
  label,
  value,
  tone,
  caption,
}: {
  label: string;
  value: string;
  tone: "teal" | "amber" | "rose" | "violet" | "neutral";
  caption?: string;
}) {
  return (
    <div className={`ws-cnp-tile ws-cnp-tile-${tone}`}>
      <div className="ws-cnp-tile-label">{label}</div>
      <div className="ws-cnp-tile-value">{value}</div>
      {caption && <div className="ws-cnp-tile-cap">{caption}</div>}
    </div>
  );
}

function Section({
  title,
  caption,
  children,
}: {
  title: string;
  caption?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="ws-cnp-section">
      <div className="flex items-baseline justify-between">
        <div className="ws-cnp-sec-title">{title}</div>
        {caption && (
          <div className="font-mono text-[10px] text-white/35">{caption}</div>
        )}
      </div>
      <div className="mt-2">{children}</div>
    </div>
  );
}

function AttribBars({
  rows,
  baseline,
}: {
  rows: AttributionContribution[];
  baseline: number;
}) {
  const max = Math.max(0.0001, ...rows.map((r) => Math.abs(r.lift)));
  return (
    <div className="space-y-1.5">
      {rows.map((r) => {
        const pct = Math.min(100, (Math.abs(r.lift) / max) * 100);
        const positive = r.lift >= 0;
        return (
          <div key={r.counterparty} className="ws-cnp-arow">
            <span className="font-mono truncate text-[11.5px] text-white/85" title={r.counterparty}>
              {r.counterparty}
            </span>
            <div className="ws-cnp-abar">
              <span
                style={{ width: `${pct}%` }}
                className={positive ? "ws-cnp-abar-pos" : "ws-cnp-abar-neg"}
              />
            </div>
            <span className="tabular-nums text-right text-[11.5px] text-white/80">
              {positive ? "+" : ""}
              {r.lift.toFixed(1)}
            </span>
            <span className="font-mono text-[10px] text-white/40">
              {r.tx_count}tx · {shortMoney(r.amount_total)}
            </span>
          </div>
        );
      })}
      <div className="mt-1.5 text-[10.5px] text-white/40">
        baseline · {baseline.toFixed(0)} — bar length is |Δ| normalised across this list
      </div>
    </div>
  );
}

function PeerList({ lifts }: { lifts: NetworkDelta[] }) {
  const max = Math.max(0.0001, ...lifts.map((l) => Math.abs(l.network_delta)));
  return (
    <div className="space-y-1.5">
      {lifts.map((d) => {
        const pct = Math.min(100, (Math.abs(d.network_delta) / max) * 100);
        const drops = d.network_delta < 0; // ablating the subject hurt this peer
        return (
          <div key={d.entity_id} className="ws-cnp-arow">
            <span className="font-mono truncate text-[11.5px] text-white/85" title={d.display_name}>
              {d.display_name || d.entity_id}
            </span>
            <div className="ws-cnp-abar">
              <span
                style={{ width: `${pct}%` }}
                className={drops ? "ws-cnp-abar-neg" : "ws-cnp-abar-pos"}
              />
            </div>
            <span
              className={
                "tabular-nums text-right text-[11.5px] " +
                (drops ? "text-teal-300" : "text-amber-300")
              }
            >
              {d.network_delta > 0 ? "+" : ""}
              {d.network_delta.toFixed(1)}
            </span>
            <span className="font-mono text-[10px] text-white/40">
              {d.network_before.toFixed(0)} → {d.network_after.toFixed(0)}
            </span>
          </div>
        );
      })}
    </div>
  );
}

function bandTone(
  band: "low" | "medium" | "high" | "critical",
): "teal" | "amber" | "rose" | "violet" | "neutral" {
  if (band === "critical") return "rose";
  if (band === "high") return "amber";
  if (band === "medium") return "violet";
  return "teal";
}

function shortMoney(v: number | undefined): string {
  if (v == null || Number.isNaN(v as number)) return "—";
  const n = v as number;
  if (Math.abs(n) >= 1e7) return `₹${(n / 1e7).toFixed(1)}cr`;
  if (Math.abs(n) >= 1e5) return `₹${(n / 1e5).toFixed(1)}L`;
  if (Math.abs(n) >= 1e3) return `₹${(n / 1e3).toFixed(1)}k`;
  return `₹${n.toFixed(0)}`;
}
