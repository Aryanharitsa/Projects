"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import MetricRangeBar from "../../components/MetricRangeBar";
import PeerRing, { peerBucketColor } from "../../components/PeerRing";
import {
  PeerAnalyzeResponse,
  PeerBucket,
  PeerCohort,
  PeerCustomerReport,
  PeerRules,
  analyzePeers,
  getPeerRules,
  getPeerSample,
} from "../../lib/api";

const BUCKETS: PeerBucket[] = ["severe", "outlier", "drifting", "aligned"];
const BUCKET_LABELS: Record<PeerBucket, string> = {
  severe: "Severe",
  outlier: "Outlier",
  drifting: "Drifting",
  aligned: "Aligned",
};

const LEVEL_LABELS: Record<string, string> = {
  full: "industry × domicile × size",
  medium: "industry × domicile",
  loose: "industry only",
  global: "global fallback",
};

function bucketTone(b: PeerBucket) {
  return {
    severe: "border-rose-400/40 bg-rose-500/10 text-rose-300",
    outlier: "border-orange-400/40 bg-orange-500/10 text-orange-300",
    drifting: "border-amber-400/40 bg-amber-500/10 text-amber-200",
    aligned: "border-teal-400/40 bg-teal-500/10 text-teal-300",
  }[b];
}

function bandFill(b: PeerBucket) {
  return {
    severe: "linear-gradient(135deg, rgba(239,68,68,0.18), rgba(239,68,68,0.04))",
    outlier: "linear-gradient(135deg, rgba(251,146,60,0.18), rgba(251,146,60,0.04))",
    drifting: "linear-gradient(135deg, rgba(251,191,36,0.16), rgba(251,191,36,0.04))",
    aligned: "linear-gradient(135deg, rgba(34,211,168,0.14), rgba(34,211,168,0.04))",
  }[b];
}

function cohortLabel(c: PeerCohort): string {
  const parts: string[] = [];
  if (c.industry) parts.push(c.industry);
  if (c.domicile) parts.push(c.domicile);
  if (c.size_band) parts.push(c.size_band);
  if (parts.length === 0) parts.push("global");
  return parts.join(" · ");
}

function compactNum(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

export default function PeerLensPage() {
  const [rules, setRules] = useState<PeerRules | null>(null);
  const [data, setData] = useState<PeerAnalyzeResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const [active, setActive] = useState<string | null>(null);
  const [bucketFilter, setBucketFilter] = useState<PeerBucket | null>(null);
  const [cohortFilter, setCohortFilter] = useState<string | null>(null);
  const [search, setSearch] = useState("");

  const run = useCallback(async () => {
    setBusy(true);
    setErr(null);
    try {
      const sample = await getPeerSample();
      const result = await analyzePeers(sample.customers, sample.transactions);
      setData(result);
      // Land on the top outlier.
      setActive(result.customers[0]?.customer_id ?? null);
    } catch (e: any) {
      setErr(e?.message || "failed to run peer analysis");
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    let cancel = false;
    (async () => {
      setLoading(true);
      try {
        const r = await getPeerRules();
        if (cancel) return;
        setRules(r);
        await run();
      } catch (e: any) {
        if (!cancel) setErr(e?.message || "failed to initialise peer lens");
      } finally {
        if (!cancel) setLoading(false);
      }
    })();
    return () => {
      cancel = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const filtered = useMemo(() => {
    if (!data) return [];
    let rows = data.customers;
    if (bucketFilter) rows = rows.filter((r) => r.bucket === bucketFilter);
    if (cohortFilter) rows = rows.filter((r) => r.cohort_id === cohortFilter);
    if (search.trim()) {
      const q = search.trim().toLowerCase();
      rows = rows.filter(
        (r) =>
          r.display_name.toLowerCase().includes(q) ||
          r.customer_id.toLowerCase().includes(q) ||
          r.industry.toLowerCase().includes(q) ||
          r.domicile.toLowerCase().includes(q),
      );
    }
    return rows;
  }, [data, bucketFilter, cohortFilter, search]);

  const activeReport = useMemo(
    () => data?.customers.find((r) => r.customer_id === active) || null,
    [data, active],
  );
  const activeCohort = useMemo(
    () => data?.cohorts.find((c) => c.cohort_id === activeReport?.cohort_id) || null,
    [data, activeReport],
  );

  return (
    <div className="space-y-6">
      <Hero
        data={data}
        loading={loading || busy}
        onRerun={run}
        rules={rules}
      />

      {err && (
        <div className="glass border border-rose-400/30 bg-rose-500/10 px-4 py-2.5 text-[13px] text-rose-200">
          {err}
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1.05fr)_minmax(0,1.35fr)]">
        <PortfolioPanel
          data={data}
          loading={loading}
          rows={filtered}
          active={active}
          setActive={setActive}
          bucketFilter={bucketFilter}
          setBucketFilter={setBucketFilter}
          cohortFilter={cohortFilter}
          setCohortFilter={setCohortFilter}
          search={search}
          setSearch={setSearch}
        />
        <CustomerPanel
          report={activeReport}
          cohort={activeCohort}
          loading={loading}
        />
      </div>

      {rules && <RulesFootnote rules={rules} />}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Hero
// ---------------------------------------------------------------------------

function Hero({
  data,
  loading,
  onRerun,
  rules,
}: {
  data: PeerAnalyzeResponse | null;
  loading: boolean;
  onRerun: () => void;
  rules: PeerRules | null;
}) {
  const p = data?.portfolio;
  return (
    <section className="glass-strong relative overflow-hidden px-6 py-6 md:px-8 md:py-7">
      <div
        aria-hidden
        className="pointer-events-none absolute -right-24 -top-20 h-72 w-72 rounded-full opacity-50 blur-3xl"
        style={{ background: "radial-gradient(closest-side, rgba(251,146,60,0.25), transparent)" }}
      />
      <div className="relative grid gap-6 md:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
        <div className="space-y-3">
          <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.22em] text-white/45">
            <span>Peer Lens</span>
            <span className="text-white/20">·</span>
            <span>round-12 · day-55</span>
          </div>
          <h1 className="text-3xl font-semibold tracking-tight md:text-[34px]">
            <span className="grad-text">Cohort outlier detection</span>{" "}
            across your customer book.
          </h1>
          <p className="max-w-2xl text-[14px] leading-relaxed text-white/70">
            Every other engine in TITAN scores one customer in isolation. Peer Lens
            scores them <em className="text-white">against their peers</em> — same
            industry, jurisdiction, and size band — using robust MAD-based z-scores
            across nine behavioral axes. Catches customers who look fine on their own
            but are structurally out-of-line with their cohort.
          </p>
          <div className="flex flex-wrap items-center gap-2 pt-1">
            <button
              type="button"
              className="btn-primary disabled:opacity-60"
              onClick={onRerun}
              disabled={loading}
            >
              {loading ? "Analysing…" : "Re-run analysis"}
            </button>
            {rules && (
              <span className="pill">
                lookback {rules.lookback_days}d
              </span>
            )}
            {rules && (
              <span className="pill">
                min cohort {rules.min_cohort_size}
              </span>
            )}
            {data && (
              <span className="pill pill-ok">
                {data.cohorts.length} cohorts
              </span>
            )}
          </div>
        </div>

        <div className="grid grid-cols-4 gap-2 md:gap-3">
          <Tile label="Customers" value={p ? String(p.customers) : "—"} />
          <Tile label="Outliers" value={p ? String(p.outliers) : "—"} tone="orange" />
          <Tile label="Severe" value={p ? String(p.severe) : "—"} tone="rose" />
          <Tile
            label="Avg score"
            value={p ? p.average_score.toFixed(1) : "—"}
          />
        </div>
      </div>
    </section>
  );
}

function Tile({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: "rose" | "orange" | "teal";
}) {
  const accent =
    tone === "rose"
      ? "#ef4444"
      : tone === "orange"
      ? "#fb923c"
      : tone === "teal"
      ? "#22d3a8"
      : "#e6edf6";
  return (
    <div className="rounded-xl border border-white/10 bg-white/[0.03] px-3 py-3">
      <div className="text-[10px] uppercase tracking-[0.2em] text-white/45">{label}</div>
      <div
        className="mt-1 font-semibold tracking-tight"
        style={{ color: accent, fontSize: 24 }}
      >
        {value}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Portfolio panel — left
// ---------------------------------------------------------------------------

function PortfolioPanel({
  data,
  loading,
  rows,
  active,
  setActive,
  bucketFilter,
  setBucketFilter,
  cohortFilter,
  setCohortFilter,
  search,
  setSearch,
}: {
  data: PeerAnalyzeResponse | null;
  loading: boolean;
  rows: PeerCustomerReport[];
  active: string | null;
  setActive: (id: string) => void;
  bucketFilter: PeerBucket | null;
  setBucketFilter: (b: PeerBucket | null) => void;
  cohortFilter: string | null;
  setCohortFilter: (c: string | null) => void;
  search: string;
  setSearch: (s: string) => void;
}) {
  return (
    <div className="glass space-y-4 px-5 py-5">
      <div className="flex items-center justify-between">
        <div>
          <div className="text-[11px] uppercase tracking-[0.22em] text-white/45">
            Portfolio
          </div>
          <div className="text-[15px] font-semibold text-white/90">
            {rows.length} of {data?.customers.length ?? 0} customers
          </div>
        </div>
        <input
          className="input max-w-[220px]"
          placeholder="search name, id, country…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      <div className="flex flex-wrap items-center gap-1.5">
        <ChipBucket
          label="All"
          count={data?.customers.length ?? 0}
          active={bucketFilter === null}
          onClick={() => setBucketFilter(null)}
        />
        {BUCKETS.map((b) => (
          <ChipBucket
            key={b}
            label={BUCKET_LABELS[b]}
            count={data?.by_bucket?.[b] ?? 0}
            accent={peerBucketColor(b)}
            active={bucketFilter === b}
            onClick={() => setBucketFilter(bucketFilter === b ? null : b)}
          />
        ))}
      </div>

      {data && data.cohorts.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-[10px] uppercase tracking-[0.22em] text-white/40">
            cohort:
          </span>
          <ChipBucket
            label="all"
            count={data.customers.length}
            active={cohortFilter === null}
            onClick={() => setCohortFilter(null)}
          />
          {data.cohorts.map((c) => (
            <ChipBucket
              key={c.cohort_id}
              label={cohortLabel(c)}
              count={c.size}
              active={cohortFilter === c.cohort_id}
              onClick={() =>
                setCohortFilter(cohortFilter === c.cohort_id ? null : c.cohort_id)
              }
            />
          ))}
        </div>
      )}

      <div className="scroll-thin max-h-[640px] overflow-auto pr-1">
        {loading && !rows.length ? (
          <div className="py-10 text-center text-[13px] text-white/50">
            Loading peer cohorts…
          </div>
        ) : rows.length === 0 ? (
          <div className="py-10 text-center text-[13px] text-white/50">
            No customers match these filters.
          </div>
        ) : (
          <ul className="space-y-2">
            {rows.map((r) => (
              <CustomerRow
                key={r.customer_id}
                report={r}
                active={r.customer_id === active}
                onClick={() => setActive(r.customer_id)}
              />
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function ChipBucket({
  label,
  count,
  accent,
  active,
  onClick,
}: {
  label: string;
  count: number;
  accent?: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] transition ${
        active
          ? "border-white/40 bg-white/10 text-white"
          : "border-white/10 bg-white/[0.03] text-white/65 hover:border-white/25 hover:text-white"
      }`}
    >
      {accent && (
        <span
          className="inline-block h-1.5 w-1.5 rounded-full"
          style={{ background: accent }}
        />
      )}
      <span>{label}</span>
      <span className="text-white/40">{count}</span>
    </button>
  );
}

function CustomerRow({
  report,
  active,
  onClick,
}: {
  report: PeerCustomerReport;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <li>
      <button
        type="button"
        onClick={onClick}
        className={`group flex w-full items-center gap-3 rounded-xl border px-3 py-2.5 text-left transition ${
          active
            ? "border-white/30 bg-white/[0.06]"
            : "border-white/10 hover:border-white/25 hover:bg-white/[0.03]"
        }`}
        style={active ? { boxShadow: `inset 4px 0 0 0 ${report.bucket_accent}` } : undefined}
      >
        <div
          className="flex h-12 w-12 shrink-0 items-center justify-center rounded-lg border"
          style={{
            background: bandFill(report.bucket),
            borderColor: `${report.bucket_accent}55`,
            color: report.bucket_accent,
          }}
        >
          <span className="text-base font-semibold tracking-tight">
            {report.outlier_score.toFixed(0)}
          </span>
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between gap-2">
            <div className="truncate text-[13.5px] font-medium text-white/95">
              {report.display_name}
            </div>
            <span
              className={`shrink-0 rounded-full border px-2 py-[1px] text-[9.5px] uppercase tracking-wider ${bucketTone(report.bucket)}`}
            >
              {BUCKET_LABELS[report.bucket]}
            </span>
          </div>
          <div className="mt-0.5 flex items-center gap-2 text-[11px] text-white/55">
            <span>{report.industry}</span>
            <span className="text-white/25">·</span>
            <span>{report.domicile}</span>
            <span className="text-white/25">·</span>
            <span>{report.size_band}</span>
            <span className="text-white/25">·</span>
            <span className="text-white/45">cohort n={report.cohort_size}</span>
          </div>
          <div className="mt-1 truncate text-[11.5px] text-white/55">
            {report.headline}
          </div>
        </div>
      </button>
    </li>
  );
}

// ---------------------------------------------------------------------------
// Customer detail panel — right
// ---------------------------------------------------------------------------

function CustomerPanel({
  report,
  cohort,
  loading,
}: {
  report: PeerCustomerReport | null;
  cohort: PeerCohort | null;
  loading: boolean;
}) {
  if (loading && !report) {
    return (
      <div className="glass grid place-items-center px-5 py-16 text-[13px] text-white/55">
        Loading customer detail…
      </div>
    );
  }
  if (!report) {
    return (
      <div className="glass grid place-items-center px-5 py-16 text-[13px] text-white/55">
        Pick a customer on the left to inspect peer positioning.
      </div>
    );
  }

  const sorted = [...report.metrics].sort((a, b) => b.gated_z - a.gated_z);

  return (
    <div className="glass space-y-5 px-5 py-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="space-y-1.5">
          <div className="text-[11px] uppercase tracking-[0.22em] text-white/45">
            {report.cohort_level} cohort · {LEVEL_LABELS[report.cohort_level]}
          </div>
          <div className="text-[19px] font-semibold tracking-tight text-white">
            {report.display_name}
          </div>
          <div className="flex flex-wrap items-center gap-2 text-[11.5px] text-white/55">
            <span>{report.industry}</span>
            <span className="text-white/25">·</span>
            <span>{report.domicile}</span>
            <span className="text-white/25">·</span>
            <span>size: {report.size_band}</span>
            <span className="text-white/25">·</span>
            <span>peer count: {report.cohort_size}</span>
          </div>
          <div className="mt-1 max-w-xl text-[13px] leading-relaxed text-white/75">
            {report.headline}
          </div>
        </div>
        <PeerRing
          score={report.outlier_score}
          bucket={report.bucket}
          size={120}
        />
      </div>

      <div
        className="rounded-xl border px-4 py-3"
        style={{
          background: bandFill(report.bucket),
          borderColor: `${report.bucket_accent}55`,
        }}
      >
        <div className="text-[10px] uppercase tracking-[0.22em] text-white/55">
          Recommended action
        </div>
        <div className="mt-0.5 text-[13px] text-white/90">
          {report.recommended_action}
        </div>
      </div>

      <DriverGrid report={report} />

      <section className="space-y-2">
        <div className="flex items-center justify-between">
          <div className="text-[12px] uppercase tracking-[0.22em] text-white/55">
            Per-metric peer positioning
          </div>
          <div className="text-[11px] text-white/40">
            {report.extreme_count} of {report.metrics.length} axes ≥ 3σ
          </div>
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          {sorted.map((m) => (
            <div
              key={m.key}
              className="rounded-xl border border-white/10 bg-white/[0.02] px-3 py-3"
            >
              <MetricRangeBar metric={m} />
              <div className="mt-1.5 flex items-center justify-between text-[10px] text-white/35">
                <span>basis: {m.basis}</span>
                <span>
                  IQR {fmtBasic(m.unit, m.cohort_p25)} – {fmtBasic(m.unit, m.cohort_p75)}
                </span>
              </div>
            </div>
          ))}
        </div>
      </section>

      {cohort && (
        <section className="grid gap-3 sm:grid-cols-2">
          <div className="rounded-xl border border-white/10 bg-white/[0.02] px-4 py-3">
            <div className="text-[10px] uppercase tracking-[0.22em] text-white/45">
              Cohort signature
            </div>
            <div className="mt-1 font-mono text-[11px] text-white/70 break-all">
              {cohort.cohort_id}
            </div>
            <div className="mt-2 text-[12px] text-white/65">
              {cohort.size} members · scored at <strong>{cohort.level}</strong> level
            </div>
          </div>
          <div className="rounded-xl border border-white/10 bg-white/[0.02] px-4 py-3">
            <div className="text-[10px] uppercase tracking-[0.22em] text-white/45">
              Max gated z
            </div>
            <div className="mt-1 text-[22px] font-semibold tracking-tight text-white">
              {report.max_gated_z.toFixed(2)}
            </div>
            <div className="mt-1 text-[11.5px] text-white/55">
              {report.extreme_count} of {report.metrics.length} axes beyond 3σ
            </div>
          </div>
        </section>
      )}
    </div>
  );
}

function DriverGrid({ report }: { report: PeerCustomerReport }) {
  const drivers = report.top_drivers.length > 0 ? report.top_drivers : report.metrics.slice(0, 3);
  return (
    <section className="grid gap-2 sm:grid-cols-3">
      {drivers.slice(0, 3).map((d, i) => (
        <div
          key={d.key}
          className="rounded-xl border border-white/10 bg-white/[0.025] px-3 py-2.5"
        >
          <div className="flex items-center justify-between text-[10px] uppercase tracking-[0.22em] text-white/45">
            <span>driver #{i + 1}</span>
            <span style={{ color: d.accent }}>
              {d.direction === "high" ? "high-only" : "both"}
            </span>
          </div>
          <div className="mt-1 text-[12.5px] font-medium text-white/90">{d.label}</div>
          <div className="mt-0.5 flex items-baseline justify-between">
            <span className="font-mono text-[15px] text-white">
              {fmtBasic(d.unit, d.value)}
            </span>
            <span className="text-[11px] text-white/50">
              med {fmtBasic(d.unit, d.cohort_median)}
            </span>
          </div>
          <div
            className="mt-1 inline-flex items-center rounded-full border px-2 py-0.5 text-[10px]"
            style={{
              borderColor: d.gated_z > 3 ? "rgba(239,68,68,0.5)" : "rgba(255,255,255,0.18)",
              color: d.gated_z > 3 ? "#fecaca" : "#cbd5e1",
              background: d.gated_z > 3 ? "rgba(239,68,68,0.10)" : "rgba(255,255,255,0.03)",
            }}
          >
            z = {(d.z >= 0 ? "+" : "−")}
            {Math.abs(d.z).toFixed(2)}
          </div>
        </div>
      ))}
    </section>
  );
}

function fmtBasic(unit: "USD" | "%" | "txs" | "cps", value: number): string {
  if (unit === "USD") {
    if (value >= 1_000_000) return `$${(value / 1_000_000).toFixed(2)}M`;
    if (value >= 1_000) return `$${(value / 1_000).toFixed(1)}K`;
    return `$${value.toFixed(0)}`;
  }
  if (unit === "%") return `${(value * 100).toFixed(0)}%`;
  if (value >= 1000) return value.toLocaleString();
  if (Number.isInteger(value)) return `${value}`;
  return value.toFixed(2);
}

// ---------------------------------------------------------------------------
// Rules footnote
// ---------------------------------------------------------------------------

function RulesFootnote({ rules }: { rules: PeerRules }) {
  return (
    <details className="glass overflow-hidden px-5 py-4">
      <summary className="cursor-pointer text-[12px] uppercase tracking-[0.22em] text-white/55">
        Engine rules · {rules.engine} · v{rules.version}
      </summary>
      <div className="mt-3 grid gap-3 text-[12px] text-white/70 md:grid-cols-2">
        <div>
          <div className="text-[10px] uppercase tracking-[0.22em] text-white/45">
            Cohort fallback
          </div>
          <ol className="mt-1 list-decimal space-y-0.5 pl-5 text-white/65">
            {rules.fallback_chain.map((s) => (
              <li key={s}>{s}</li>
            ))}
          </ol>
          <div className="mt-2 text-[11px] text-white/50">
            most-specific cohort with ≥ {rules.min_cohort_size} members wins.
          </div>
        </div>
        <div>
          <div className="text-[10px] uppercase tracking-[0.22em] text-white/45">
            Score composition
          </div>
          <pre className="mt-1 whitespace-pre-wrap font-mono text-[11px] text-white/65">
{`outlier_score = min(100,
  ${rules.scoring.per_max_z} * max(|gated z|) +
  ${rules.scoring.per_extreme} * count(|z| > ${rules.scoring.extreme_z_floor}))

robust: ${rules.scoring.robust_first}`}
          </pre>
        </div>
        <div className="md:col-span-2">
          <div className="text-[10px] uppercase tracking-[0.22em] text-white/45">
            Metrics ({rules.metrics.length})
          </div>
          <div className="mt-2 grid grid-cols-2 gap-1.5 md:grid-cols-3">
            {rules.metrics.map((m) => (
              <div
                key={m.key}
                className="rounded-md border border-white/10 bg-white/[0.02] px-2 py-1.5 text-[11.5px]"
              >
                <span
                  className="mr-1.5 inline-block h-1.5 w-1.5 rounded-full align-middle"
                  style={{ background: m.accent }}
                />
                <span className="text-white/85">{m.label}</span>
                <span className="ml-1 text-white/35">({m.direction})</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </details>
  );
}
