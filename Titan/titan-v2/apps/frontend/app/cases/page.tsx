"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import CaseCard from "../../components/CaseCard";
import {
  CasePriority,
  CaseSla,
  CaseStats,
  CaseStatus,
  CaseSummary,
  casesAssignees,
  casesStats,
  listCases,
} from "../../lib/api";

const PRIORITY_LANES: CasePriority[] = ["critical", "high", "medium"];

const PRIORITY_LANE_TITLE: Record<CasePriority, string> = {
  critical: "Critical",
  high: "High",
  medium: "Medium",
  low: "Low",
};

const STATUS_OPTIONS: { value: CaseStatus | ""; label: string }[] = [
  { value: "", label: "All statuses" },
  { value: "open", label: "Open" },
  { value: "review", label: "In review" },
  { value: "escalated", label: "Escalated" },
  { value: "cleared", label: "Cleared" },
  { value: "sar_filed", label: "SAR filed" },
];

const SLA_OPTIONS: { value: CaseSla | ""; label: string }[] = [
  { value: "", label: "Any SLA" },
  { value: "ok", label: "On-track" },
  { value: "warn", label: "Warning" },
  { value: "breach", label: "Breached" },
];

export default function CasesPage() {
  const [stats, setStats] = useState<CaseStats | null>(null);
  const [cases, setCases] = useState<CaseSummary[]>([]);
  const [assignees, setAssignees] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  const [status, setStatus] = useState<CaseStatus | "">("");
  const [assignee, setAssignee] = useState<string>("");
  const [sla, setSla] = useState<CaseSla | "">("");
  const [q, setQ] = useState<string>("");
  const [includeClosed, setIncludeClosed] = useState<boolean>(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const [s, l, a] = await Promise.all([
        casesStats(),
        listCases({
          status: (status || undefined) as CaseStatus | undefined,
          assignee: assignee || undefined,
          sla: (sla || undefined) as CaseSla | undefined,
          q: q || undefined,
          include_closed: includeClosed,
          limit: 200,
        }),
        casesAssignees(),
      ]);
      setStats(s);
      setCases(l.cases);
      setAssignees(a.assignees);
    } catch (e: any) {
      setErr(e.message || "Failed to load cases");
    } finally {
      setLoading(false);
    }
  }, [status, assignee, sla, q, includeClosed]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // Re-fetch search on debounce
  useEffect(() => {
    const t = setTimeout(refresh, 250);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q]);

  const lanes = useMemo(() => {
    const grouped: Record<CasePriority, CaseSummary[]> = {
      critical: [],
      high: [],
      medium: [],
      low: [],
    };
    for (const c of cases) grouped[c.priority].push(c);
    return grouped;
  }, [cases]);

  const lowCount = lanes.low.length;

  const resetFilters = useCallback(() => {
    setStatus("");
    setAssignee("");
    setSla("");
    setQ("");
    setIncludeClosed(false);
  }, []);

  const anyFilter =
    !!status || !!assignee || !!sla || !!q || includeClosed;

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <span className="pill pill-ok">Workflow · cases</span>
          <h1 className="mt-2 text-2xl font-semibold tracking-tight md:text-3xl">
            Case queue
          </h1>
          <p className="mt-1 max-w-2xl text-[13.5px] text-white/60">
            Every alert from the AML console can be promoted to a case.
            Cases carry priority, SLA, an audit trail of every transition,
            and the snapshot of evidence that triage saw — so the workflow
            stays inspectable end-to-end.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            className={`btn ${includeClosed ? "ring-1 ring-teal-400/30" : ""}`}
            onClick={() => setIncludeClosed((v) => !v)}
          >
            {includeClosed ? "Hide closed" : "Show closed"}
          </button>
          <button className="btn" onClick={refresh} disabled={loading}>
            {loading ? "Refreshing…" : "Refresh"}
          </button>
        </div>
      </header>

      {/* Stats banner */}
      <section className="grid grid-cols-2 gap-3 md:grid-cols-6">
        <Tile
          label="Open"
          value={stats?.open_total ?? 0}
          eyebrow="not closed"
          tone="violet"
        />
        <Tile
          label="In review"
          value={stats?.by_status.review ?? 0}
          eyebrow="under triage"
          tone="teal"
        />
        <Tile
          label="Escalated"
          value={stats?.by_status.escalated ?? 0}
          eyebrow="bumped to L2"
          tone="amber"
        />
        <Tile
          label="SAR filed"
          value={stats?.by_status.sar_filed ?? 0}
          eyebrow="terminal"
          tone="emerald"
        />
        <Tile
          label="SLA breach"
          value={stats?.by_sla.breach ?? 0}
          eyebrow={`> ${stats?.sla_thresholds.breach_hours ?? 72}h`}
          tone={(stats?.by_sla.breach ?? 0) > 0 ? "rose" : "neutral"}
        />
        <Tile
          label="Avg age"
          value={`${(stats?.avg_open_age_hours ?? 0).toFixed(1)}h`}
          eyebrow="open cases"
          tone="neutral"
        />
      </section>

      {/* Filter bar */}
      <section className="glass-strong flex flex-wrap items-end gap-3 px-4 py-3">
        <div className="min-w-[220px] flex-1">
          <div className="label">Search</div>
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="account, name, or summary…"
            className="input"
          />
        </div>
        <div>
          <div className="label">Status</div>
          <select
            value={status}
            onChange={(e) => setStatus(e.target.value as CaseStatus | "")}
            className="input"
          >
            {STATUS_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </div>
        <div>
          <div className="label">Assignee</div>
          <select
            value={assignee}
            onChange={(e) => setAssignee(e.target.value)}
            className="input"
          >
            <option value="">All assignees</option>
            <option value="__unassigned__">Unassigned</option>
            {assignees.map((a) => (
              <option key={a} value={a}>
                {a}
              </option>
            ))}
          </select>
        </div>
        <div>
          <div className="label">SLA</div>
          <select
            value={sla}
            onChange={(e) => setSla(e.target.value as CaseSla | "")}
            className="input"
          >
            {SLA_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </div>
        {anyFilter && (
          <button className="btn-ghost" onClick={resetFilters}>
            Reset
          </button>
        )}
        <span className="ml-auto text-[11.5px] text-white/45">
          {cases.length} {cases.length === 1 ? "case" : "cases"}
        </span>
      </section>

      {err && (
        <div className="glass border-rose-400/30 bg-rose-500/[0.06] p-3 text-[12.5px] text-rose-300">
          {err}
        </div>
      )}

      {/* Empty state */}
      {!loading && cases.length === 0 && (
        <section className="glass grid place-items-center px-6 py-16 text-center">
          <div>
            <div className="text-3xl">∅</div>
            <h2 className="mt-3 text-xl font-semibold tracking-tight">
              No cases match.
            </h2>
            <p className="mt-1.5 max-w-md text-[13px] text-white/55">
              Run a batch through the AML console and use{" "}
              <span className="text-white/85">Open as cases</span> to promote
              alerts. Every promoted alert keeps a frozen evidence snapshot.
            </p>
            <div className="mt-4 flex justify-center gap-2">
              <a href="/aml" className="btn-primary">
                Open AML console
              </a>
              {anyFilter && (
                <button className="btn" onClick={resetFilters}>
                  Clear filters
                </button>
              )}
            </div>
          </div>
        </section>
      )}

      {/* Kanban swim lanes */}
      {cases.length > 0 && (
        <section className="grid gap-4 md:grid-cols-3">
          {PRIORITY_LANES.map((p) => (
            <div key={p} className={`ws-lane ws-lane-stripe-${p}`}>
              <div className="ws-lane-header">
                <span
                  className="inline-block h-2 w-2 rounded-full"
                  style={{
                    background:
                      p === "critical"
                        ? "#ef4444"
                        : p === "high"
                        ? "#fb923c"
                        : "#fbbf24",
                  }}
                />
                <span className="text-[12px] font-semibold uppercase tracking-wider text-white/85">
                  {PRIORITY_LANE_TITLE[p]}
                </span>
                <span className="ml-auto rounded-full border border-white/10 bg-white/[0.04] px-2 py-0.5 font-mono text-[10.5px] text-white/55">
                  {lanes[p].length}
                </span>
              </div>
              <div className="flex flex-col gap-2.5">
                {lanes[p].length === 0 ? (
                  <div className="ws-lane-empty">
                    Nothing in this lane.
                  </div>
                ) : (
                  lanes[p].map((c) => <CaseCard key={c.id} c={c} />)
                )}
              </div>
            </div>
          ))}
        </section>
      )}

      {/* Low priority collapsed list */}
      {lowCount > 0 && (
        <section className="glass p-4">
          <div className="flex items-center gap-2">
            <span
              className="inline-block h-2 w-2 rounded-full"
              style={{ background: "#22d3a8" }}
            />
            <span className="text-[12px] font-semibold uppercase tracking-wider text-white/75">
              Low priority
            </span>
            <span className="ml-auto rounded-full border border-white/10 bg-white/[0.04] px-2 py-0.5 font-mono text-[10.5px] text-white/55">
              {lowCount}
            </span>
          </div>
          <div className="mt-3 grid gap-2.5 sm:grid-cols-2 lg:grid-cols-3">
            {lanes.low.map((c) => (
              <CaseCard key={c.id} c={c} />
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

function Tile({
  label,
  value,
  eyebrow,
  tone,
}: {
  label: string;
  value: number | string;
  eyebrow?: string;
  tone: "violet" | "teal" | "amber" | "rose" | "emerald" | "neutral";
}) {
  const COLOR: Record<string, string> = {
    violet: "rgba(139,124,255,0.45)",
    teal: "rgba(45,225,194,0.45)",
    amber: "rgba(251,191,36,0.5)",
    rose: "rgba(239,68,68,0.55)",
    emerald: "rgba(16,185,129,0.5)",
    neutral: "rgba(255,255,255,0.18)",
  };
  return (
    <div className="glass relative overflow-hidden p-3">
      <div
        aria-hidden
        className="pointer-events-none absolute -top-12 -right-12 h-32 w-32 rounded-full blur-2xl"
        style={{ background: COLOR[tone] }}
      />
      <div className="relative">
        <div className="text-[10.5px] uppercase tracking-wider text-white/45">
          {label}
        </div>
        <div className="mt-1 text-2xl font-semibold tracking-tight">
          {value}
        </div>
        {eyebrow && (
          <div className="mt-0.5 text-[11px] text-white/45">{eyebrow}</div>
        )}
      </div>
    </div>
  );
}
