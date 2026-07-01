"use client";

/*
 * Precedent — TITAN's case-similarity retrieval + Bayesian disposition
 * prior (round-15, day-70).
 *
 * Every other TITAN surface *judges* one case in isolation.  Precedent
 * asks the analyst's very first question — "have we seen this before,
 * and how did it end?" — by walking the case store and pulling the
 * ``k`` nearest historical cases.
 *
 * Render stack (hand-rolled SVG / CSS, zero charting libs):
 *
 *   1. Case picker — searchable, priority-tinted list of open cases.
 *      Click one → becomes the query.
 *   2. Hero panel — recommendation banner (accent-colored by verdict),
 *      query summary, aggregate tiles (posterior bar, median TTR,
 *      corpus coverage), rationale.
 *   3. Precedent cards — one card per match with a conic similarity
 *      ring, disposition pill, typology chip, top firing factors,
 *      block-attribution bars (which axes drove similarity), and the
 *      "vs precedent" delta view for the closest match.
 *   4. Posterior bar — Bayesian smoothed SAR / cleared split with
 *      base-rate reference line so the analyst can eyeball how much
 *      the precedents shifted the prior.
 *   5. Footer — engine + rules dump.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  getPrecedentForCase,
  getPrecedentRules,
  listPrecedentCandidates,
  seedPrecedentSamples,
  precedentExportUrl,
  PrecedentCandidate,
  PrecedentMatch,
  PrecedentRecommendationCode,
  PrecedentReport,
  PrecedentRules,
} from "../../lib/api";

const ACCENT: Record<PrecedentRecommendationCode, string> = {
  file_sar_probable: "#f43f5e",
  expedite_clearance: "#22d3a8",
  weigh_evidence: "#fbbf24",
  novel_investigate: "#a855f7",
  insufficient_precedent: "#94a3b8",
};

const HERO_BG: Record<PrecedentRecommendationCode, string> = {
  file_sar_probable:
    "radial-gradient(120% 100% at 50% 0%, rgba(244,63,94,0.22) 0%, rgba(7,11,20,0) 65%)",
  expedite_clearance:
    "radial-gradient(120% 100% at 50% 0%, rgba(34,211,168,0.18) 0%, rgba(7,11,20,0) 65%)",
  weigh_evidence:
    "radial-gradient(120% 100% at 50% 0%, rgba(251,191,36,0.20) 0%, rgba(7,11,20,0) 65%)",
  novel_investigate:
    "radial-gradient(120% 100% at 50% 0%, rgba(168,85,247,0.20) 0%, rgba(7,11,20,0) 65%)",
  insufficient_precedent:
    "radial-gradient(120% 100% at 50% 0%, rgba(148,163,184,0.14) 0%, rgba(7,11,20,0) 65%)",
};

const PRIORITY_HUE: Record<string, string> = {
  critical: "#ef4444",
  high: "#fb923c",
  medium: "#fbbf24",
  low: "#94a3b8",
};

const BAND_HUE: Record<string, string> = {
  low: "#22d3a8",
  medium: "#fbbf24",
  high: "#fb923c",
  critical: "#ef4444",
};

const DISPO_LABEL: Record<string, string> = {
  sar_filed: "SAR filed",
  cleared: "Cleared",
  in_flight: "In flight",
};

const DISPO_HUE: Record<string, string> = {
  sar_filed: "#f43f5e",
  cleared: "#22d3a8",
  in_flight: "#a855f7",
};

const BLOCK_LABEL: Record<string, string> = {
  factor: "Factor firings",
  typology: "Typology",
  amount: "Flow magnitude",
  posture: "Band + sanctions",
};

function fmtHours(h: number | null | undefined): string {
  if (h === null || h === undefined) return "—";
  if (h < 1) return `${(h * 60).toFixed(0)}m`;
  if (h < 48) return `${h.toFixed(1)}h`;
  return `${(h / 24).toFixed(1)}d`;
}

function fmtRelative(iso: string | null | undefined): string {
  if (!iso) return "—";
  const then = new Date(iso).getTime();
  const now = Date.now();
  const diff = Math.max(0, now - then) / 1000;
  if (diff < 3600) return `${Math.round(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.round(diff / 3600)}h ago`;
  return `${Math.round(diff / 86400)}d ago`;
}

function SimilarityRing({
  similarity,
  accent,
  size = 68,
}: {
  similarity: number;
  accent: string;
  size?: number;
}) {
  const pct = Math.max(0, Math.min(1, similarity));
  const ring = `conic-gradient(${accent} ${pct * 360}deg, rgba(255,255,255,0.06) 0)`;
  return (
    <div
      className="relative grid place-items-center rounded-full"
      style={{ width: size, height: size, background: ring }}
    >
      <div
        className="absolute inset-[5px] rounded-full"
        style={{ background: "rgba(7,11,20,0.85)" }}
      />
      <div className="relative text-center leading-none">
        <div className="text-[15px] font-semibold tracking-tight" style={{ color: accent }}>
          {(similarity * 100).toFixed(0)}
        </div>
        <div className="mt-0.5 text-[8px] uppercase tracking-[0.18em] text-white/50">
          match
        </div>
      </div>
    </div>
  );
}

function CandidateRow({
  candidate,
  active,
  onClick,
}: {
  candidate: PrecedentCandidate;
  active: boolean;
  onClick: () => void;
}) {
  const hue = PRIORITY_HUE[candidate.priority] ?? "#94a3b8";
  return (
    <button
      onClick={onClick}
      className={
        "group flex w-full items-start gap-2 rounded-lg border px-2.5 py-2 text-left transition " +
        (active
          ? "border-white/25 bg-white/[0.08]"
          : "border-white/5 bg-white/[0.02] hover:border-white/15 hover:bg-white/[0.05]")
      }
    >
      <div
        className="mt-1 h-2 w-2 shrink-0 rounded-full"
        style={{ background: hue, boxShadow: `0 0 8px ${hue}` }}
      />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5">
          <span className="truncate text-[13px] text-white/90">
            {candidate.display_name || candidate.account_id}
          </span>
        </div>
        <div className="mt-0.5 truncate text-[10.5px] uppercase tracking-[0.12em] text-white/40">
          {candidate.case_id} · {candidate.status} · {candidate.band}
          {candidate.typology_code ? ` · ${candidate.typology_code}` : ""}
        </div>
        {candidate.summary && (
          <div className="mt-0.5 line-clamp-1 text-[11px] text-white/50">
            {candidate.summary}
          </div>
        )}
      </div>
    </button>
  );
}

function DriverBars({ drivers, accent }: { drivers: PrecedentMatch["drivers"]; accent: string }) {
  const max = drivers.reduce((m, d) => Math.max(m, d.contribution), 0) || 1;
  return (
    <div className="space-y-1">
      {drivers.map((d) => (
        <div key={d.block} className="flex items-center gap-2 text-[10.5px] text-white/70">
          <div className="w-24 truncate uppercase tracking-[0.14em] text-white/45">
            {BLOCK_LABEL[d.block] ?? d.block}
          </div>
          <div className="relative h-1.5 flex-1 overflow-hidden rounded-full bg-white/[0.06]">
            <div
              className="absolute inset-y-0 left-0 rounded-full"
              style={{
                width: `${(d.contribution / max) * 100}%`,
                background: accent,
                opacity: 0.85,
              }}
            />
          </div>
          <div className="w-9 shrink-0 text-right font-mono text-white/60">
            {(d.contribution * 100).toFixed(1)}
          </div>
        </div>
      ))}
    </div>
  );
}

function DeltaChips({ deltas }: { deltas: PrecedentMatch["deltas"] }) {
  if (!deltas.length) return null;
  return (
    <div className="flex flex-wrap gap-1.5">
      {deltas.map((d) => {
        const positive = d.delta >= 0;
        const hue = positive ? "#fb923c" : "#22d3a8";
        return (
          <span
            key={d.axis}
            className="inline-flex items-center gap-1 rounded-full border border-white/10 bg-white/[0.03] px-2 py-0.5 text-[10px] uppercase tracking-[0.12em]"
            style={{ color: hue }}
          >
            {positive ? "▲" : "▼"} {d.axis}
            <span className="font-mono text-white/50">
              {(Math.abs(d.delta) * 100).toFixed(0)}
            </span>
          </span>
        );
      })}
    </div>
  );
}

function PrecedentCard({ match, accent }: { match: PrecedentMatch; accent: string }) {
  const dispoHue = DISPO_HUE[match.disposition] ?? "#94a3b8";
  const bandHue = BAND_HUE[match.band] ?? "#94a3b8";
  return (
    <div className="glass flex flex-col gap-3 rounded-2xl border border-white/5 bg-white/[0.02] p-4">
      <div className="flex items-start gap-3">
        <SimilarityRing similarity={match.similarity} accent={accent} />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5 text-[13px] text-white/85">
            <span className="truncate">{match.case_id}</span>
          </div>
          <div className="mt-0.5 truncate text-[11px] text-white/50">
            {match.summary || "—"}
          </div>
          <div className="mt-2 flex flex-wrap items-center gap-1.5">
            <span
              className="inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-[0.14em]"
              style={{
                borderColor: `${dispoHue}55`,
                background: `${dispoHue}18`,
                color: dispoHue,
              }}
            >
              {DISPO_LABEL[match.disposition] ?? match.status}
            </span>
            <span
              className="inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-[0.14em]"
              style={{
                borderColor: `${bandHue}55`,
                background: `${bandHue}12`,
                color: bandHue,
              }}
            >
              {match.band}
            </span>
            {match.typology_code && (
              <span
                className="inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-[0.14em] text-white/80"
                style={{
                  borderColor: "rgba(255,255,255,0.14)",
                  background: "rgba(255,255,255,0.03)",
                }}
              >
                {match.typology_code}
                {match.typology_name ? ` · ${match.typology_name}` : ""}
              </span>
            )}
          </div>
        </div>
      </div>
      {match.top_factors.length > 0 && (
        <div className="text-[11px] text-white/60">
          <span className="uppercase tracking-[0.14em] text-white/40">Factors</span>{" "}
          <span className="ml-1">{match.top_factors.join(" · ")}</span>
        </div>
      )}
      <div>
        <div className="mb-1 text-[10.5px] uppercase tracking-[0.14em] text-white/40">
          Similarity drivers
        </div>
        <DriverBars drivers={match.drivers} accent={accent} />
      </div>
      {match.deltas.length > 0 && (
        <div>
          <div className="mb-1.5 text-[10.5px] uppercase tracking-[0.14em] text-white/40">
            Vs query · top deltas
          </div>
          <DeltaChips deltas={match.deltas} />
        </div>
      )}
      <div className="flex items-center justify-between gap-3 text-[10.5px] text-white/45">
        <span>Opened {fmtRelative(match.opened_at_iso)}</span>
        <span>
          {match.disposition === "in_flight"
            ? "still open"
            : `resolved in ${fmtHours(match.resolution_hours)}`}
        </span>
      </div>
    </div>
  );
}

function PosteriorBar({
  posterior,
  counts,
}: {
  posterior: Record<"sar_filed" | "cleared", number>;
  counts: Record<string, number>;
}) {
  const sar = posterior.sar_filed ?? 0.5;
  const cleared = posterior.cleared ?? 0.5;
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between text-[10.5px] uppercase tracking-[0.14em] text-white/50">
        <span style={{ color: DISPO_HUE.cleared }}>Cleared · {(cleared * 100).toFixed(0)}%</span>
        <span style={{ color: DISPO_HUE.sar_filed }}>SAR · {(sar * 100).toFixed(0)}%</span>
      </div>
      <div className="relative h-3.5 overflow-hidden rounded-full bg-white/[0.05]">
        <div
          className="absolute inset-y-0 left-0"
          style={{
            width: `${cleared * 100}%`,
            background: `linear-gradient(90deg, ${DISPO_HUE.cleared}CC, ${DISPO_HUE.cleared}44)`,
          }}
        />
        <div
          className="absolute inset-y-0 right-0"
          style={{
            width: `${sar * 100}%`,
            background: `linear-gradient(90deg, ${DISPO_HUE.sar_filed}44, ${DISPO_HUE.sar_filed}CC)`,
          }}
        />
        <div
          className="absolute inset-y-0 w-px bg-white/40"
          style={{ left: "50%" }}
          title="50/50 base rate"
        />
      </div>
      <div className="flex items-center justify-between text-[10.5px] text-white/50">
        <span>n(cleared) = {counts.cleared ?? 0}</span>
        <span>n(in-flight) = {counts.in_flight ?? 0}</span>
        <span>n(SAR) = {counts.sar_filed ?? 0}</span>
      </div>
    </div>
  );
}

function AggregateTile({
  label,
  value,
  hint,
  accent,
}: {
  label: string;
  value: string;
  hint?: string;
  accent?: string;
}) {
  return (
    <div
      className="glass rounded-xl border border-white/5 bg-white/[0.02] px-3 py-2.5"
      style={accent ? { boxShadow: `inset 0 0 0 1px ${accent}22` } : undefined}
    >
      <div className="text-[10px] uppercase tracking-[0.16em] text-white/45">{label}</div>
      <div className="mt-1 text-[18px] font-semibold tracking-tight" style={{ color: accent ?? "white" }}>
        {value}
      </div>
      {hint && <div className="mt-0.5 text-[10.5px] text-white/45">{hint}</div>}
    </div>
  );
}

function EmptyPanel({
  onSeed,
  seeding,
  seedResult,
}: {
  onSeed: () => void;
  seeding: boolean;
  seedResult: string | null;
}) {
  return (
    <div className="glass flex flex-col items-center gap-3 rounded-2xl border border-white/5 bg-white/[0.02] p-8 text-center">
      <div className="text-[13px] uppercase tracking-[0.2em] text-white/40">
        Precedent
      </div>
      <div className="max-w-md text-[13px] text-white/70">
        The case store doesn&apos;t have enough terminal cases yet to compute a
        precedent panel. Seed the bundled six-family demo portfolio (30 cases
        with realistic dispositions) to explore the surface.
      </div>
      <button
        onClick={onSeed}
        disabled={seeding}
        className="mt-1 rounded-lg border border-white/15 bg-white/[0.06] px-4 py-1.5 text-[12px] uppercase tracking-[0.16em] text-white/85 transition hover:border-white/25 hover:bg-white/[0.1] disabled:opacity-50"
      >
        {seeding ? "Seeding…" : "Seed demo portfolio"}
      </button>
      {seedResult && (
        <div className="text-[11px] text-white/50">{seedResult}</div>
      )}
    </div>
  );
}

export default function PrecedentPage() {
  const [rules, setRules] = useState<PrecedentRules | null>(null);
  const [candidates, setCandidates] = useState<PrecedentCandidate[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [report, setReport] = useState<PrecedentReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [includeClosed, setIncludeClosed] = useState(false);
  const [seeding, setSeeding] = useState(false);
  const [seedResult, setSeedResult] = useState<string | null>(null);
  const [k, setK] = useState<number>(8);

  const filtered = useMemo(() => {
    if (!query.trim()) return candidates;
    const q = query.toLowerCase();
    return candidates.filter(
      (c) =>
        c.case_id.toLowerCase().includes(q) ||
        c.display_name.toLowerCase().includes(q) ||
        (c.account_id || "").toLowerCase().includes(q) ||
        (c.typology_code || "").toLowerCase().includes(q),
    );
  }, [candidates, query]);

  const refreshCandidates = useCallback(async () => {
    try {
      const res = await listPrecedentCandidates({ limit: 200, include_closed: includeClosed });
      setCandidates(res.candidates);
      if (!selected && res.candidates.length > 0) {
        setSelected(res.candidates[0].case_id);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [includeClosed, selected]);

  useEffect(() => {
    getPrecedentRules().then(setRules).catch(() => undefined);
    refreshCandidates();
  }, [refreshCandidates]);

  useEffect(() => {
    if (!selected) return;
    setLoading(true);
    setError(null);
    getPrecedentForCase(selected, { k, min_sim: 0.5 })
      .then(setReport)
      .catch((err) => setError(err instanceof Error ? err.message : String(err)))
      .finally(() => setLoading(false));
  }, [selected, k]);

  const seed = useCallback(async () => {
    setSeeding(true);
    setSeedResult(null);
    try {
      const res = await seedPrecedentSamples(false);
      if (res.seeded > 0) {
        setSeedResult(`Seeded ${res.seeded} case(s) across ${res.families?.length ?? 0} families.`);
      } else {
        setSeedResult(res.reason ?? "Store already populated.");
      }
      await refreshCandidates();
    } catch (err) {
      setSeedResult(err instanceof Error ? err.message : String(err));
    } finally {
      setSeeding(false);
    }
  }, [refreshCandidates]);

  const recCode: PrecedentRecommendationCode =
    report?.recommendation.code ?? "insufficient_precedent";
  const accent = ACCENT[recCode];
  const heroBg = HERO_BG[recCode];

  return (
    <div className="flex flex-col gap-6">
      {/* Hero */}
      <section
        className="glass-strong relative overflow-hidden rounded-2xl border border-white/5 p-6"
        style={{ background: heroBg }}
      >
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="max-w-2xl">
            <div className="text-[11px] uppercase tracking-[0.24em] text-white/45">
              Precedent · case-similarity retrieval
            </div>
            <div className="mt-1 text-[26px] font-semibold tracking-tight text-white">
              {report?.query.display_name || report?.query.account_id || "Pick a case to begin"}
            </div>
            <div className="mt-1 text-[12px] text-white/55">
              {report?.query.summary || (
                <>k nearest historical cases · Bayesian disposition prior · median time-to-resolve.</>
              )}
            </div>
            {report && (
              <div
                className="mt-4 inline-flex flex-wrap items-center gap-2 rounded-xl border px-3 py-2 text-[13px] font-medium"
                style={{
                  borderColor: `${accent}66`,
                  background: `${accent}18`,
                  color: accent,
                }}
              >
                <span
                  className="inline-block h-2 w-2 rounded-full"
                  style={{ background: accent, boxShadow: `0 0 10px ${accent}` }}
                />
                {report.recommendation.label}
              </div>
            )}
            {report?.recommendation.rationale && (
              <div className="mt-2 max-w-xl text-[12.5px] text-white/70">
                {report.recommendation.rationale}
              </div>
            )}
          </div>
          <div className="flex flex-col items-stretch gap-2 lg:items-end">
            <div className="flex flex-wrap items-center gap-1.5">
              {[6, 8, 12, 16].map((n) => (
                <button
                  key={n}
                  onClick={() => setK(n)}
                  className={
                    "rounded-md border px-2 py-1 text-[11px] uppercase tracking-[0.14em] transition " +
                    (n === k
                      ? "border-white/25 bg-white/[0.08] text-white"
                      : "border-white/10 bg-white/[0.02] text-white/60 hover:bg-white/[0.05]")
                  }
                >
                  k={n}
                </button>
              ))}
            </div>
            {selected && (
              <a
                href={precedentExportUrl({ case_id: selected, k, min_sim: 0.5 })}
                target="_blank"
                rel="noreferrer"
                className="rounded-md border border-white/15 bg-white/[0.04] px-3 py-1 text-[11px] uppercase tracking-[0.14em] text-white/75 transition hover:border-white/25 hover:bg-white/[0.08]"
              >
                Export memo (.md)
              </a>
            )}
          </div>
        </div>

        {report && (
          <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
            <AggregateTile
              label="Precedents"
              value={String(report.matches.length)}
              hint={`from ${report.corpus_size} case${report.corpus_size === 1 ? "" : "s"}`}
              accent={accent}
            />
            <AggregateTile
              label="P(SAR)"
              value={`${((report.posterior.sar_filed ?? 0) * 100).toFixed(0)}%`}
              hint="Laplace-smoothed"
              accent={
                (report.posterior.sar_filed ?? 0) >= 0.65
                  ? DISPO_HUE.sar_filed
                  : (report.posterior.sar_filed ?? 0) <= 0.25
                    ? DISPO_HUE.cleared
                    : "#fbbf24"
              }
            />
            <AggregateTile
              label="Median TTR"
              value={fmtHours(report.median_resolution_hours ?? undefined)}
              hint={
                report.p95_resolution_hours != null
                  ? `p95 · ${fmtHours(report.p95_resolution_hours)}`
                  : "no terminal precedents"
              }
            />
            <AggregateTile
              label="Considered"
              value={String(report.considered)}
              hint={`sim ≥ ${(0.5 * 100).toFixed(0)}%`}
            />
          </div>
        )}
      </section>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[280px_minmax(0,1fr)]">
        {/* Candidate picker */}
        <aside className="glass flex flex-col gap-3 rounded-2xl border border-white/5 bg-white/[0.02] p-4">
          <div className="flex items-center justify-between text-[10.5px] uppercase tracking-[0.16em] text-white/45">
            <span>Query candidates</span>
            <span className="font-mono text-white/60">{filtered.length}</span>
          </div>
          <input
            type="text"
            placeholder="Search cases…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="rounded-lg border border-white/10 bg-white/[0.03] px-3 py-1.5 text-[12px] text-white/80 outline-none placeholder:text-white/30 focus:border-white/25"
          />
          <label className="flex items-center gap-2 text-[10.5px] uppercase tracking-[0.14em] text-white/50">
            <input
              type="checkbox"
              checked={includeClosed}
              onChange={(e) => setIncludeClosed(e.target.checked)}
              className="h-3 w-3 accent-white/80"
            />
            include closed
          </label>
          <div className="-mr-1 flex max-h-[520px] flex-col gap-1 overflow-auto pr-1">
            {filtered.length === 0 && (
              <div className="rounded-lg border border-dashed border-white/10 bg-white/[0.02] p-3 text-[11px] text-white/45">
                No candidates. Try seeding the demo portfolio.
              </div>
            )}
            {filtered.map((c) => (
              <CandidateRow
                key={c.case_id}
                candidate={c}
                active={selected === c.case_id}
                onClick={() => setSelected(c.case_id)}
              />
            ))}
          </div>
        </aside>

        {/* Main content */}
        <section className="flex flex-col gap-4">
          {loading && (
            <div className="glass rounded-2xl border border-white/5 bg-white/[0.02] p-6 text-[13px] text-white/55">
              Retrieving precedents…
            </div>
          )}

          {error && (
            <div className="glass rounded-2xl border border-rose-500/30 bg-rose-500/10 p-4 text-[13px] text-rose-200">
              {error}
            </div>
          )}

          {!loading && !error && report && report.matches.length === 0 && (
            <EmptyPanel onSeed={seed} seeding={seeding} seedResult={seedResult} />
          )}

          {!loading && !error && report && report.matches.length > 0 && (
            <>
              {/* Posterior + histogram */}
              <div className="glass rounded-2xl border border-white/5 bg-white/[0.02] p-4">
                <div className="mb-2 flex items-center justify-between">
                  <div className="text-[11px] uppercase tracking-[0.14em] text-white/45">
                    Disposition prior (Bayesian, α = 0.5)
                  </div>
                  <div className="text-[10.5px] text-white/45">
                    base rate · 50/50
                  </div>
                </div>
                <PosteriorBar posterior={report.posterior} counts={report.disposition_counts} />
              </div>

              {/* Precedent cards */}
              <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
                {report.matches.map((m) => (
                  <PrecedentCard key={m.case_id} match={m} accent={accent} />
                ))}
              </div>
            </>
          )}

          {!loading && !error && !report && (
            <EmptyPanel onSeed={seed} seeding={seeding} seedResult={seedResult} />
          )}
        </section>
      </div>

      {rules && (
        <footer className="glass rounded-2xl border border-white/5 bg-white/[0.02] p-4 text-[11px] text-white/55">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <span>
              engine <span className="font-mono text-white/70">{rules.engine}</span>
            </span>
            <span>
              blocks:{" "}
              {rules.blocks.map((b) => (
                <span key={b.block} className="mr-2 font-mono text-white/70">
                  {b.block}:{b.weight.toFixed(2)}
                </span>
              ))}
            </span>
            <span className="font-mono text-white/45">
              floor {(rules.defaults.min_similarity * 100).toFixed(0)}% · k
              default {rules.defaults.k}
            </span>
          </div>
        </footer>
      )}
    </div>
  );
}
