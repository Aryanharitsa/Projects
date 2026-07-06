"use client";

/*
 * Triage — TITAN's cleared-case suppression + false-positive mining
 * surface (round-16, day-75).
 *
 * Every prior TITAN surface *judges* one alert.  Triage answers the
 * opposite question — *"is this alert noise?"* — by mining the case
 * store's disposition history and returning a Bayesian log-lift
 * suppression score with named precedent chains.
 *
 * Render stack (hand-rolled SVG / CSS, zero charting libs):
 *
 *   1. Hero — verdict-tone-tinted radial gradient banner, suppression
 *      conic ring (big), query signature chips, verdict reason.
 *   2. Aggregate tiles — corpus size, prior clearance rate, S score,
 *      suppression %.
 *   3. Case picker — searchable priority-tinted list, filter for
 *      sanctions-touching signatures.
 *   4. Combo table — sorted by strength → lift magnitude, per-row
 *      log2-lift bar, cleared vs SAR chip, support pill.
 *   5. Suppression matrix — 9x9 factor-pair heatmap, cell shaded by
 *      lift (rose→amber→teal), support-count overlay.
 *   6. Evidence panels — 3 cleared + 3 SAR precedents side-by-side
 *      with shared-factor chips.
 *   7. Portfolio strip — base rate, top noise + top signal combos
 *      (shown whether or not a case is selected).
 *   8. Rules footer — engine version + verdict ladder chips.
 */

import { useCallback, useEffect, useMemo, useState } from "react";

import {
  getTriageForCase,
  getTriageProfile,
  getTriageRules,
  listTriageCandidates,
  seedTriageSamples,
  triageExportUrl,
  TriageCandidate,
  TriageComboRow,
  TriageMatrixCell,
  TriageProfile,
  TriageReport,
  TriageRules,
  TriageVerdictCode,
} from "../../lib/api";

// ---------------------------------------------------------------------------
// Palette
// ---------------------------------------------------------------------------

const VERDICT_ACCENT: Record<TriageVerdictCode, string> = {
  suppress_high_confidence: "#22d3a8",
  suppress_review_lightly: "#67e8f9",
  no_prior_signal: "#94a3b8",
  elevate_review: "#fbbf24",
  escalate_critical: "#f43f5e",
  insufficient_history: "#a855f7",
};

const HERO_BG: Record<TriageVerdictCode, string> = {
  suppress_high_confidence:
    "radial-gradient(120% 100% at 50% 0%, rgba(34,211,168,0.22) 0%, rgba(7,11,20,0) 65%)",
  suppress_review_lightly:
    "radial-gradient(120% 100% at 50% 0%, rgba(103,232,249,0.18) 0%, rgba(7,11,20,0) 65%)",
  no_prior_signal:
    "radial-gradient(120% 100% at 50% 0%, rgba(148,163,184,0.14) 0%, rgba(7,11,20,0) 65%)",
  elevate_review:
    "radial-gradient(120% 100% at 50% 0%, rgba(251,191,36,0.20) 0%, rgba(7,11,20,0) 65%)",
  escalate_critical:
    "radial-gradient(120% 100% at 50% 0%, rgba(244,63,94,0.22) 0%, rgba(7,11,20,0) 65%)",
  insufficient_history:
    "radial-gradient(120% 100% at 50% 0%, rgba(168,85,247,0.20) 0%, rgba(7,11,20,0) 65%)",
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

const DISPO_HUE: Record<string, string> = {
  cleared: "#22d3a8",
  sar_filed: "#f43f5e",
};

const DISPO_LABEL: Record<string, string> = {
  cleared: "Cleared",
  sar_filed: "SAR filed",
};

// Lift → hue ramp for the suppression matrix and combo bars.  Symmetric
// around 0 by design: strong noise = teal, strong signal = rose,
// neutral = slate.  Clamp lift to ±3.5 (≈ 12× odds) which is enough to
// paint the extremes without collapsing the mid-range into muddy grey.
function liftHue(lift: number, supported: boolean): string {
  if (!supported) return "rgba(148,163,184,0.20)";
  const clamped = Math.max(-3.5, Math.min(3.5, lift));
  if (clamped >= 0) {
    const t = Math.min(1, clamped / 2.5);
    // slate → cyan → teal
    if (t < 0.5) {
      const a = t * 2;
      return `rgba(${103 * a + 148 * (1 - a)},${232 * a + 163 * (1 - a)},${249 * a + 184 * (1 - a)},${0.30 + 0.55 * t})`;
    }
    return `rgba(34,211,168,${0.35 + 0.55 * t})`;
  }
  const t = Math.min(1, -clamped / 2.5);
  // slate → amber → rose
  if (t < 0.5) {
    const a = t * 2;
    return `rgba(${251 * a + 148 * (1 - a)},${191 * a + 163 * (1 - a)},${36 * a + 184 * (1 - a)},${0.30 + 0.55 * t})`;
  }
  return `rgba(244,63,94,${0.35 + 0.55 * t})`;
}

function fmtLift(lift: number): string {
  const s = lift >= 0 ? "+" : "";
  return `${s}${lift.toFixed(2)}`;
}

function fmtPct(x: number, digits = 1): string {
  return `${(x * 100).toFixed(digits)}%`;
}

function fmtRelative(iso?: string | null): string {
  if (!iso) return "—";
  const then = new Date(iso).getTime();
  const now = Date.now();
  const diff = Math.max(0, now - then) / 1000;
  if (diff < 3600) return `${Math.round(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.round(diff / 3600)}h ago`;
  return `${Math.round(diff / 86400)}d ago`;
}

// ---------------------------------------------------------------------------
// Components
// ---------------------------------------------------------------------------

function SuppressionRing({
  suppression,
  s,
  accent,
  size = 132,
}: {
  suppression: number;
  s: number;
  accent: string;
  size?: number;
}) {
  const pct = Math.max(0, Math.min(1, suppression));
  const ring = `conic-gradient(${accent} ${pct * 360}deg, rgba(255,255,255,0.06) 0)`;
  return (
    <div
      className="relative grid place-items-center rounded-full"
      style={{
        width: size,
        height: size,
        background: ring,
        boxShadow: `0 0 42px -6px ${accent}55`,
      }}
    >
      <div
        className="absolute inset-[8px] rounded-full"
        style={{ background: "rgba(7,11,20,0.9)" }}
      />
      <div className="relative text-center leading-none">
        <div
          className="text-[26px] font-semibold tracking-tight"
          style={{ color: accent }}
        >
          {(pct * 100).toFixed(0)}
        </div>
        <div className="mt-1 text-[9px] uppercase tracking-[0.20em] text-white/50">
          suppression
        </div>
        <div className="mt-2 font-mono text-[10px] text-white/50">
          S = {fmtLift(s)}
        </div>
      </div>
    </div>
  );
}

function AggregateTile({
  label,
  value,
  caption,
  accent = "#94a3b8",
}: {
  label: string;
  value: string;
  caption?: string;
  accent?: string;
}) {
  return (
    <div className="glass flex flex-col gap-1 rounded-2xl border border-white/5 bg-white/[0.02] px-4 py-3">
      <div className="text-[10px] uppercase tracking-[0.16em] text-white/40">
        {label}
      </div>
      <div
        className="text-[20px] font-semibold tracking-tight"
        style={{ color: accent }}
      >
        {value}
      </div>
      {caption && (
        <div className="text-[10.5px] text-white/50">{caption}</div>
      )}
    </div>
  );
}

function CandidateRow({
  candidate,
  active,
  onClick,
}: {
  candidate: TriageCandidate;
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
          {candidate.has_sanctions && (
            <span className="rounded-sm bg-rose-500/20 px-1 py-0 font-mono text-[9px] uppercase tracking-[0.14em] text-rose-300">
              sanc
            </span>
          )}
        </div>
        <div className="mt-0.5 truncate text-[10.5px] uppercase tracking-[0.12em] text-white/40">
          {candidate.id} · {candidate.status} · {candidate.band}
          {candidate.typology_code ? ` · ${candidate.typology_code}` : ""}
        </div>
        {candidate.signature_labels.length > 0 && (
          <div className="mt-1 line-clamp-1 text-[10.5px] text-white/55">
            {candidate.signature_labels.join(" + ")}
          </div>
        )}
      </div>
    </button>
  );
}

function ComboRow({
  row,
  detectorLabels,
}: {
  row: TriageComboRow;
  detectorLabels?: Record<string, string>;
}) {
  const labels =
    row.labels ??
    row.combo.map((f) => detectorLabels?.[f] ?? f);
  const support = row.n_seen;
  const hue = liftHue(row.lift, support >= 3);
  const magnitude = Math.min(1, Math.abs(row.lift) / 3.5);
  const barSide = row.lift >= 0 ? "left" : "right";
  return (
    <div className="flex items-center gap-3 rounded-lg border border-white/5 bg-white/[0.02] px-3 py-2">
      <div className="w-40 shrink-0 truncate text-[11.5px] text-white/85">
        {labels.join(" + ")}
      </div>
      <div className="relative h-5 flex-1 overflow-hidden rounded-sm bg-white/[0.03]">
        {/* Centreline */}
        <div className="absolute inset-y-0 left-1/2 w-px bg-white/10" />
        <div
          className="absolute inset-y-0 rounded-sm transition-all"
          style={{
            width: `${magnitude * 50}%`,
            [barSide]: "50%",
            background: hue,
          }}
        />
        <div
          className="absolute inset-0 flex items-center justify-center font-mono text-[10px] tracking-tight text-white/85"
          style={{ textShadow: "0 0 6px rgba(0,0,0,0.6)" }}
        >
          {fmtLift(row.lift)}
        </div>
      </div>
      <div className="w-16 shrink-0 text-right font-mono text-[10.5px]">
        <span className="text-emerald-300">{row.n_cleared}</span>
        <span className="mx-1 text-white/30">/</span>
        <span className="text-rose-300">{row.n_sar}</span>
      </div>
      <div
        className={
          "w-14 shrink-0 rounded-full border px-2 py-0.5 text-center text-[9.5px] uppercase tracking-[0.14em] " +
          (row.strongly_supported
            ? "border-emerald-400/40 bg-emerald-400/10 text-emerald-200"
            : support >= 3
            ? "border-white/15 bg-white/[0.04] text-white/70"
            : "border-white/10 bg-white/[0.02] text-white/45")
        }
      >
        {support >= 3 ? `${support}` : "few"}
      </div>
    </div>
  );
}

function SuppressionMatrix({
  detectors,
  labels,
  matrix,
  prior,
}: {
  detectors: string[];
  labels: Record<string, string>;
  matrix: TriageMatrixCell[][];
  prior: number;
}) {
  const [hover, setHover] = useState<TriageMatrixCell | null>(null);
  return (
    <div className="glass rounded-2xl border border-white/5 bg-white/[0.02] p-4">
      <div className="mb-3 flex items-baseline justify-between">
        <div className="text-[13px] font-semibold tracking-tight text-white/85">
          Factor-pair suppression matrix
        </div>
        <div className="text-[10.5px] text-white/50">
          shaded by log₂-lift · prior {fmtPct(prior)}
        </div>
      </div>
      <div className="flex gap-3">
        <div className="grid gap-1 pt-6" style={{ gridTemplateRows: `repeat(${detectors.length}, minmax(0, 32px))` }}>
          {detectors.map((d) => (
            <div
              key={`ylabel-${d}`}
              className="flex items-center text-right text-[9.5px] uppercase tracking-[0.12em] text-white/50"
            >
              {labels[d]}
            </div>
          ))}
        </div>
        <div className="flex-1 overflow-x-auto">
          <div className="min-w-fit">
            <div
              className="mb-1 grid gap-1"
              style={{
                gridTemplateColumns: `repeat(${detectors.length}, minmax(56px, 1fr))`,
              }}
            >
              {detectors.map((d) => (
                <div
                  key={`xlabel-${d}`}
                  className="truncate text-center text-[9.5px] uppercase tracking-[0.12em] text-white/50"
                >
                  {labels[d]}
                </div>
              ))}
            </div>
            <div
              className="grid gap-1"
              style={{
                gridTemplateColumns: `repeat(${detectors.length}, minmax(56px, 1fr))`,
              }}
            >
              {matrix.map((row, ri) =>
                row.map((cell, ci) => {
                  const hue = liftHue(cell.lift, cell.supported);
                  const isDiag = ri === ci;
                  return (
                    <div
                      key={`cell-${ri}-${ci}`}
                      className={
                        "relative flex h-8 items-center justify-center rounded-md border font-mono text-[10px] transition " +
                        (isDiag
                          ? "border-white/25"
                          : "border-white/5 hover:border-white/25")
                      }
                      style={{ background: hue }}
                      onMouseEnter={() => setHover(cell)}
                      onMouseLeave={() =>
                        setHover((h) => (h === cell ? null : h))
                      }
                    >
                      {cell.supported ? (
                        <span className="text-white/90">
                          {fmtPct(cell.p_clear, 0)}
                        </span>
                      ) : (
                        <span className="text-white/40">·</span>
                      )}
                    </div>
                  );
                }),
              )}
            </div>
          </div>
        </div>
      </div>
      <div className="mt-3 flex items-center justify-between text-[10.5px] text-white/60">
        <div className="flex items-center gap-2">
          <span className="inline-block h-3 w-8 rounded-sm" style={{ background: liftHue(-2.5, true) }} />
          <span>signal (rare clearance)</span>
          <span className="inline-block h-3 w-8 rounded-sm" style={{ background: liftHue(0, false) }} />
          <span>thin support</span>
          <span className="inline-block h-3 w-8 rounded-sm" style={{ background: liftHue(2.5, true) }} />
          <span>noise (routinely cleared)</span>
        </div>
        <div className="min-h-[16px] font-mono">
          {hover
            ? `${labels[hover.a]} × ${labels[hover.b]} — ${hover.n_cleared} cleared / ${hover.n_sar} SAR (${fmtLift(hover.lift)})`
            : "hover a cell for details"}
        </div>
      </div>
    </div>
  );
}

function PrecedentCard({
  row,
  detectorLabels,
}: {
  row: TriageReport["evidence"]["cleared"][number];
  detectorLabels: Record<string, string>;
}) {
  const dispoHue = DISPO_HUE[row.disposition] ?? "#94a3b8";
  const bandHue = BAND_HUE[row.band] ?? "#94a3b8";
  return (
    <div className="glass flex flex-col gap-2 rounded-2xl border border-white/5 bg-white/[0.02] p-3">
      <div className="flex items-center gap-2">
        <span
          className="inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-[0.14em]"
          style={{
            borderColor: `${dispoHue}55`,
            background: `${dispoHue}18`,
            color: dispoHue,
          }}
        >
          {DISPO_LABEL[row.disposition] ?? row.disposition}
        </span>
        <span
          className="inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-[0.14em]"
          style={{
            borderColor: `${bandHue}55`,
            background: `${bandHue}12`,
            color: bandHue,
          }}
        >
          {row.band}
        </span>
        {row.typology_code && (
          <span className="rounded-full border border-white/10 bg-white/[0.03] px-2 py-0.5 text-[10px] uppercase tracking-[0.14em] text-white/70">
            {row.typology_code}
          </span>
        )}
      </div>
      <div>
        <div className="truncate text-[12.5px] text-white/85">
          {row.display_name || row.account_id}
        </div>
        <div className="mt-0.5 truncate font-mono text-[10.5px] text-white/45">
          {row.id}
        </div>
      </div>
      {row.summary && (
        <div className="line-clamp-2 text-[11px] text-white/55">
          {row.summary}
        </div>
      )}
      <div className="flex flex-wrap gap-1.5">
        <span className="rounded-full border border-white/10 bg-white/[0.03] px-1.5 py-0.5 text-[9.5px] uppercase tracking-[0.12em] text-white/50">
          shared
        </span>
        {row.shared_factors.map((f) => (
          <span
            key={f}
            className="rounded-full border border-white/15 bg-white/[0.05] px-2 py-0.5 text-[10px] text-white/80"
          >
            {detectorLabels[f] ?? f}
          </span>
        ))}
      </div>
      <div className="mt-1 flex items-center justify-between text-[10px] text-white/50">
        <span>score {row.risk_score.toFixed(1)}</span>
        <span>{fmtRelative(row.closed_at_iso ?? row.opened_at_iso)}</span>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function TriagePage() {
  const [rules, setRules] = useState<TriageRules | null>(null);
  const [profile, setProfile] = useState<TriageProfile | null>(null);
  const [candidates, setCandidates] = useState<TriageCandidate[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [report, setReport] = useState<TriageReport | null>(null);
  const [reportLoading, setReportLoading] = useState<boolean>(false);
  const [seeding, setSeeding] = useState<boolean>(false);
  const [filter, setFilter] = useState<string>("");
  const [sancOnly, setSancOnly] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const refreshCore = useCallback(async () => {
    try {
      const [r, p, c] = await Promise.all([
        getTriageRules(),
        getTriageProfile(),
        listTriageCandidates({ limit: 200 }),
      ]);
      setRules(r);
      setProfile(p);
      setCandidates(c.candidates);
      if (!selectedId && c.candidates.length > 0) {
        setSelectedId(c.candidates[0].id);
      }
      setError(null);
    } catch (e: any) {
      setError(String(e?.message ?? e));
    }
  }, [selectedId]);

  useEffect(() => {
    void refreshCore();
  }, [refreshCore]);

  useEffect(() => {
    if (!selectedId) {
      setReport(null);
      return;
    }
    let cancelled = false;
    setReportLoading(true);
    getTriageForCase(selectedId)
      .then((r) => {
        if (!cancelled) {
          setReport(r);
          setError(null);
        }
      })
      .catch((e) => {
        if (!cancelled) {
          setReport(null);
          setError(String(e?.message ?? e));
        }
      })
      .finally(() => {
        if (!cancelled) setReportLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedId]);

  const seed = useCallback(async () => {
    setSeeding(true);
    try {
      await seedTriageSamples(false);
      await refreshCore();
    } catch (e: any) {
      setError(String(e?.message ?? e));
    } finally {
      setSeeding(false);
    }
  }, [refreshCore]);

  const filteredCandidates = useMemo(() => {
    const q = filter.trim().toLowerCase();
    return candidates.filter((c) => {
      if (sancOnly && !c.has_sanctions) return false;
      if (!q) return true;
      return (
        c.id.toLowerCase().includes(q) ||
        c.account_id.toLowerCase().includes(q) ||
        (c.display_name || "").toLowerCase().includes(q) ||
        c.signature_labels.some((l) => l.toLowerCase().includes(q))
      );
    });
  }, [candidates, filter, sancOnly]);

  const detectorLabels = useMemo(() => {
    if (profile) return profile.detector_labels;
    if (rules) {
      const out: Record<string, string> = {};
      for (const d of rules.detectors) out[d.name] = d.label;
      return out;
    }
    return {} as Record<string, string>;
  }, [profile, rules]);

  const verdictCode: TriageVerdictCode | null =
    report?.verdict.code ?? null;
  const accent = verdictCode ? VERDICT_ACCENT[verdictCode] : "#94a3b8";
  const heroBg = verdictCode ? HERO_BG[verdictCode] : HERO_BG.no_prior_signal;

  const showSeedNudge =
    profile !== null && profile.corpus.closed_total < 20 && !seeding;

  return (
    <div className="space-y-6">
      {/* ---------- HERO ---------- */}
      <section
        className="glass relative overflow-hidden rounded-3xl border border-white/5 p-5 md:p-7"
        style={{ background: heroBg }}
      >
        <div className="flex flex-col gap-6 md:flex-row md:items-center md:justify-between">
          <div className="min-w-0 flex-1">
            <div className="text-[11px] uppercase tracking-[0.24em] text-white/45">
              titan · triage · round-16 · day-75
            </div>
            <div className="mt-2 flex flex-wrap items-baseline gap-3">
              <h1 className="text-[28px] font-semibold tracking-tight text-white">
                Cleared-case suppression
              </h1>
              <span
                className="rounded-full border px-2 py-0.5 font-mono text-[10.5px] uppercase tracking-[0.18em]"
                style={{
                  borderColor: `${accent}55`,
                  background: `${accent}12`,
                  color: accent,
                }}
              >
                {report ? report.verdict.label : "select a candidate"}
              </span>
            </div>
            <p className="mt-2 max-w-3xl text-[13px] leading-6 text-white/70">
              {report
                ? report.verdict.reason
                : "Mines the case store's ‘cleared vs SAR-filed’ history and returns a Bayesian log-lift suppression score with named precedent chains, so an analyst knows which of today's alerts look like signatures we've routinely cleared before — and which look like the ones we filed."}
            </p>
            {report && (
              <div className="mt-4 flex flex-wrap gap-1.5">
                {report.query.signature_labels.map((l, i) => {
                  const name = report.query.signature[i];
                  const isSanc = name === "sanctions_hit";
                  return (
                    <span
                      key={l}
                      className="rounded-full border px-2 py-0.5 text-[10.5px] uppercase tracking-[0.14em]"
                      style={{
                        borderColor: isSanc ? "#f43f5e55" : `${accent}55`,
                        background: isSanc ? "#f43f5e18" : `${accent}18`,
                        color: isSanc ? "#f9a8b7" : accent,
                      }}
                    >
                      {l}
                      {isSanc && " ⛔"}
                    </span>
                  );
                })}
                {report.score.sanctions_veto_applied && (
                  <span className="rounded-full border border-rose-400/50 bg-rose-500/12 px-2 py-0.5 text-[10.5px] uppercase tracking-[0.14em] text-rose-300">
                    sanctions veto applied
                  </span>
                )}
              </div>
            )}
          </div>
          <div className="flex shrink-0 items-center gap-6">
            <SuppressionRing
              suppression={report?.score.suppression ?? 0.5}
              s={report?.score.s ?? 0}
              accent={accent}
            />
          </div>
        </div>
        {report && (
          <a
            href={triageExportUrl(report.query.case_id)}
            className="absolute right-5 top-5 rounded-md border border-white/15 bg-white/[0.05] px-2 py-1 font-mono text-[10.5px] uppercase tracking-[0.14em] text-white/70 hover:bg-white/[0.10]"
          >
            export .md
          </a>
        )}
      </section>

      {/* ---------- AGGREGATE STRIP ---------- */}
      <section className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <AggregateTile
          label="Closed corpus"
          value={
            report ? String(report.corpus.closed_total) : profile ? String(profile.corpus.closed_total) : "—"
          }
          caption={
            report
              ? `${report.corpus.cleared_total} cleared · ${report.corpus.sar_total} SAR`
              : profile
              ? `${profile.corpus.cleared_total} cleared · ${profile.corpus.sar_total} SAR`
              : "waiting for mining"
          }
        />
        <AggregateTile
          label="Portfolio prior"
          value={
            report ? fmtPct(report.corpus.p_clear_prior) : profile ? fmtPct(profile.corpus.p_clear_prior) : "—"
          }
          caption="baseline clearance rate"
          accent="#67e8f9"
        />
        <AggregateTile
          label="Aggregate S"
          value={report ? fmtLift(report.score.s) : "—"}
          caption={
            report
              ? `scored ${report.score.scored_combos} combo${report.score.scored_combos === 1 ? "" : "s"}`
              : "pick a case"
          }
          accent={accent}
        />
        <AggregateTile
          label="Suppression"
          value={report ? fmtPct(report.score.suppression) : "—"}
          caption={
            report
              ? report.score.strongly_supported_combos > 0
                ? `${report.score.strongly_supported_combos} strongly supported`
                : "thin evidence"
              : "0..100 — noise-likelihood"
          }
          accent={accent}
        />
      </section>

      {/* ---------- CANDIDATE + COMBO + EVIDENCE ---------- */}
      <section className="grid grid-cols-12 gap-4">
        {/* Left rail: case picker */}
        <div className="glass col-span-12 flex flex-col gap-3 rounded-2xl border border-white/5 bg-white/[0.02] p-4 md:col-span-4 lg:col-span-3">
          <div className="flex items-center justify-between">
            <div className="text-[12.5px] font-semibold tracking-tight text-white/85">
              Query candidates
            </div>
            <span className="rounded-full border border-white/10 bg-white/[0.02] px-2 py-0.5 font-mono text-[10px] text-white/60">
              {candidates.length}
            </span>
          </div>
          <input
            className="w-full rounded-md border border-white/10 bg-white/[0.03] px-2 py-1.5 text-[12px] placeholder-white/30 focus:border-white/30 focus:outline-none"
            placeholder="filter · id / signature"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          />
          <label className="flex items-center gap-2 text-[11px] text-white/70">
            <input
              type="checkbox"
              className="accent-rose-400"
              checked={sancOnly}
              onChange={(e) => setSancOnly(e.target.checked)}
            />
            sanctions-touching only
          </label>
          <div className="max-h-[520px] space-y-1.5 overflow-y-auto pr-1">
            {filteredCandidates.map((c) => (
              <CandidateRow
                key={c.id}
                candidate={c}
                active={c.id === selectedId}
                onClick={() => setSelectedId(c.id)}
              />
            ))}
            {filteredCandidates.length === 0 && (
              <div className="rounded-lg border border-dashed border-white/10 bg-white/[0.01] p-3 text-[11.5px] leading-5 text-white/60">
                No open or review cases match — {" "}
                <button
                  className="underline decoration-dotted underline-offset-2 hover:text-white"
                  onClick={seed}
                  disabled={seeding}
                >
                  seed the FP-rich demo corpus
                </button>
                {" "}or open a case from the AML console.
              </div>
            )}
          </div>
          {showSeedNudge && (
            <button
              onClick={seed}
              disabled={seeding}
              className="mt-1 rounded-md border border-cyan-400/40 bg-cyan-400/[0.08] px-2 py-1.5 text-[11px] uppercase tracking-[0.14em] text-cyan-200 hover:bg-cyan-400/[0.14] disabled:opacity-60"
            >
              {seeding ? "seeding…" : "seed FP-rich demo corpus"}
            </button>
          )}
        </div>

        {/* Middle: query + combo table */}
        <div className="col-span-12 space-y-4 md:col-span-8 lg:col-span-6">
          <div className="glass rounded-2xl border border-white/5 bg-white/[0.02] p-4">
            <div className="flex items-baseline justify-between">
              <div className="text-[13px] font-semibold tracking-tight text-white/85">
                {report
                  ? `Query — ${report.query.display_name || report.query.account_id}`
                  : "Query"}
              </div>
              {report && (
                <div className="font-mono text-[10.5px] text-white/50">
                  {report.query.case_id}
                </div>
              )}
            </div>
            {report && (
              <>
                <div className="mt-2 grid grid-cols-2 gap-3 text-[11px] text-white/60 md:grid-cols-4">
                  <div>
                    <div className="text-[9.5px] uppercase tracking-[0.14em] text-white/40">
                      Band
                    </div>
                    <div style={{ color: BAND_HUE[report.query.band] ?? "#e6edf6" }}>
                      {report.query.band}
                    </div>
                  </div>
                  <div>
                    <div className="text-[9.5px] uppercase tracking-[0.14em] text-white/40">
                      Priority
                    </div>
                    <div style={{ color: PRIORITY_HUE[report.query.priority] ?? "#e6edf6" }}>
                      {report.query.priority}
                    </div>
                  </div>
                  <div>
                    <div className="text-[9.5px] uppercase tracking-[0.14em] text-white/40">
                      Risk score
                    </div>
                    <div className="font-mono text-white/80">
                      {report.query.risk_score.toFixed(1)}
                    </div>
                  </div>
                  <div>
                    <div className="text-[9.5px] uppercase tracking-[0.14em] text-white/40">
                      Opened
                    </div>
                    <div className="text-white/80">
                      {fmtRelative(report.query.opened_at_iso)}
                    </div>
                  </div>
                </div>
                {report.query.top_factors.length > 0 && (
                  <div className="mt-3 flex flex-wrap gap-1.5">
                    {report.query.top_factors.map((f) => (
                      <span
                        key={f.name}
                        className="rounded-full border border-white/10 bg-white/[0.04] px-2 py-0.5 text-[10.5px]"
                      >
                        <span className="text-white/70">{f.label}</span>
                        <span className="ml-1.5 font-mono text-white/50">
                          {f.points.toFixed(1)}
                        </span>
                      </span>
                    ))}
                  </div>
                )}
              </>
            )}
            {!report && !reportLoading && (
              <div className="mt-2 text-[12px] text-white/60">
                Pick an open case on the left. Triage will re-mine the
                case store, score every combo in the case&#39;s
                signature, and either{" "}
                <span className="text-emerald-300">recommend suppression</span> —
                citing the exact cleared precedents — or{" "}
                <span className="text-rose-300">escalate</span> with the
                counter-evidence.
              </div>
            )}
            {reportLoading && (
              <div className="mt-2 text-[11.5px] text-white/50">
                mining precedents…
              </div>
            )}
          </div>

          <div className="glass rounded-2xl border border-white/5 bg-white/[0.02] p-4">
            <div className="mb-2 flex items-baseline justify-between">
              <div className="text-[13px] font-semibold tracking-tight text-white/85">
                Scored combos
              </div>
              {report && (
                <div className="text-[10.5px] text-white/50">
                  sorted by support → |lift| · shows singletons + pairs
                </div>
              )}
            </div>
            {report ? (
              <div className="space-y-1.5">
                {report.combos.map((c) => (
                  <ComboRow
                    key={c.key}
                    row={c}
                    detectorLabels={detectorLabels}
                  />
                ))}
                {report.combos.length === 0 && (
                  <div className="rounded-lg border border-dashed border-white/10 p-3 text-[11.5px] text-white/60">
                    No combos to score — the query has an empty
                    signature.
                  </div>
                )}
              </div>
            ) : (
              <div className="text-[11.5px] text-white/50">
                Select a case to see its scored combos.
              </div>
            )}
          </div>
        </div>

        {/* Right: evidence panels */}
        <div className="col-span-12 space-y-4 md:col-span-12 lg:col-span-3">
          <div className="glass rounded-2xl border border-white/5 bg-white/[0.02] p-4">
            <div className="mb-2 flex items-baseline justify-between">
              <div className="text-[13px] font-semibold tracking-tight text-emerald-300">
                Cleared precedents
              </div>
              <span className="rounded-full border border-emerald-400/25 bg-emerald-400/[0.08] px-2 py-0.5 font-mono text-[10px] text-emerald-200">
                {report ? report.evidence.cleared.length : 0}
              </span>
            </div>
            {report && report.evidence.cleared.length > 0 ? (
              <div className="space-y-2">
                {report.evidence.cleared.map((r) => (
                  <PrecedentCard
                    key={r.id}
                    row={r}
                    detectorLabels={detectorLabels}
                  />
                ))}
              </div>
            ) : (
              <div className="text-[11px] text-white/50">
                No cleared precedent shares ≥2 signature factors —
                signature has no strong noise precedent.
              </div>
            )}
          </div>
          <div className="glass rounded-2xl border border-white/5 bg-white/[0.02] p-4">
            <div className="mb-2 flex items-baseline justify-between">
              <div className="text-[13px] font-semibold tracking-tight text-rose-300">
                SAR precedents
              </div>
              <span className="rounded-full border border-rose-400/25 bg-rose-400/[0.08] px-2 py-0.5 font-mono text-[10px] text-rose-200">
                {report ? report.evidence.sar_filed.length : 0}
              </span>
            </div>
            {report && report.evidence.sar_filed.length > 0 ? (
              <div className="space-y-2">
                {report.evidence.sar_filed.map((r) => (
                  <PrecedentCard
                    key={r.id}
                    row={r}
                    detectorLabels={detectorLabels}
                  />
                ))}
              </div>
            ) : (
              <div className="text-[11px] text-white/50">
                No SAR precedent shares ≥2 signature factors — no
                counter-evidence surfaced.
              </div>
            )}
          </div>
        </div>
      </section>

      {/* ---------- SUPPRESSION MATRIX ---------- */}
      {profile && (
        <SuppressionMatrix
          detectors={profile.detectors}
          labels={profile.detector_labels}
          matrix={profile.matrix}
          prior={profile.corpus.p_clear_prior}
        />
      )}

      {/* ---------- PORTFOLIO SIGNAL/NOISE STRIP ---------- */}
      {profile && (
        <section className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <div className="glass rounded-2xl border border-white/5 bg-white/[0.02] p-4">
            <div className="mb-2 flex items-baseline justify-between">
              <div className="text-[13px] font-semibold tracking-tight text-emerald-300">
                Portfolio noise leaders
              </div>
              <div className="text-[10.5px] text-white/50">
                highest log₂-lift · min support {profile.corpus.closed_total ? "≥3" : "—"}
              </div>
            </div>
            <div className="space-y-1.5">
              {profile.top_noise_combos.length === 0 && (
                <div className="text-[11px] text-white/50">
                  No well-supported noise combos yet.
                </div>
              )}
              {profile.top_noise_combos.map((c) => (
                <ComboRow key={c.key} row={c} detectorLabels={profile.detector_labels} />
              ))}
            </div>
          </div>
          <div className="glass rounded-2xl border border-white/5 bg-white/[0.02] p-4">
            <div className="mb-2 flex items-baseline justify-between">
              <div className="text-[13px] font-semibold tracking-tight text-rose-300">
                Portfolio signal leaders
              </div>
              <div className="text-[10.5px] text-white/50">
                lowest log₂-lift · min support ≥3
              </div>
            </div>
            <div className="space-y-1.5">
              {profile.top_signal_combos.length === 0 && (
                <div className="text-[11px] text-white/50">
                  No well-supported signal combos yet.
                </div>
              )}
              {profile.top_signal_combos.map((c) => (
                <ComboRow key={c.key} row={c} detectorLabels={profile.detector_labels} />
              ))}
            </div>
          </div>
        </section>
      )}

      {/* ---------- FOOTER: RULES + VERDICT LADDER ---------- */}
      {rules && (
        <section className="glass rounded-2xl border border-white/5 bg-white/[0.02] p-4">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <div className="text-[12.5px] font-semibold tracking-tight text-white/85">
              Verdict ladder
            </div>
            <div className="font-mono text-[10.5px] text-white/50">
              engine {rules.engine} · Laplace α = {rules.constants.laplace_alpha} ·
              signature top-{rules.constants.signature_top_k} · min-support {rules.constants.min_support_any} / strong ≥{rules.constants.min_support_strong}
            </div>
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            {rules.verdict_ladder.map((v) => {
              const isCurrent = v.code === verdictCode;
              return (
                <span
                  key={v.code}
                  className={
                    "rounded-full border px-2.5 py-1 text-[11px] uppercase tracking-[0.14em] " +
                    (isCurrent ? "shadow-[0_0_18px_0_currentColor]" : "")
                  }
                  style={{
                    borderColor: `${v.accent}55`,
                    background: isCurrent ? `${v.accent}22` : `${v.accent}0d`,
                    color: v.accent,
                  }}
                >
                  {v.label}
                </span>
              );
            })}
          </div>
        </section>
      )}

      {error && (
        <div className="rounded-2xl border border-rose-400/40 bg-rose-500/[0.06] p-4 text-[12px] text-rose-200">
          {error}
        </div>
      )}
    </div>
  );
}
