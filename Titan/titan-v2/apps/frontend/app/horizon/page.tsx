"use client";

/*
 * Horizon — TITAN's regulatory-change impact simulator (round-18, day-85).
 *
 * Every prior TITAN surface answers "given today's rules, what is this
 * case?".  Horizon answers the question every MLRO loses sleep over the
 * night before a policy revision ships:
 *
 *     "Which of the six-hundred cases in the queue would flip band?
 *      Which cleared cases would re-fire?  Which detectors do the damage?"
 *
 * Layout (all hand-rolled SVG + CSS, zero charting libs):
 *
 *   1. Hero — action-tinted radial banner, proposal name, three stat pills,
 *      author + generated-at strip.
 *   2. Preset picker — horizontal chip row for the six curated proposals.
 *   3. Proposal summary — the resolved config, one chip per material edit.
 *   4. Backlog waterfall — hand-rolled horizontal bar stack showing
 *      cleared→alert, alert→cleared, still_alert, still_cleared shares.
 *   5. Band-transition matrix — 4×4 grid of old_band × new_band counts.
 *   6. Detector contribution — horizontal bars (|Δ| points, backlog total).
 *   7. Case impact table — sortable by |Δ|, one row per case, click to
 *      drill down.  Verdict chip on the left, band delta on the right.
 *   8. Case drill-down — score arc (old → new), per-detector Δ bars with
 *      the engine's own reason strings, fired/dropped sanctions block.
 *   9. Action recommendation — coloured card summarising verdict.
 *  10. Rules footer — engine version + verdict ladder chips + markdown
 *      export link.
 */

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import {
  explainHorizonCase,
  getHorizonRules,
  getHorizonSample,
  horizonExportUrl,
  simulateHorizon,
  HorizonActionCode,
  HorizonAlertFlip,
  HorizonBand,
  HorizonCaseDetail,
  HorizonDetectorDelta,
  HorizonImpact,
  HorizonProposal,
  HorizonReport,
  HorizonRules,
  HorizonSummary,
  HorizonVerdictCode,
} from "../../lib/api";

// ---------------------------------------------------------------------------
// Palette — action-code drives the hero tint, verdict drives per-case chips.
// ---------------------------------------------------------------------------

const ACTION_ACCENT: Record<HorizonActionCode, string> = {
  investigate: "#f43f5e",
  pilot: "#fbbf24",
  roll_out: "#22d3a8",
  defer: "#94a3b8",
};

const ACTION_BG: Record<HorizonActionCode, string> = {
  investigate:
    "radial-gradient(130% 100% at 50% -10%, rgba(244,63,94,0.28) 0%, rgba(7,11,20,0) 65%)",
  pilot:
    "radial-gradient(130% 100% at 50% -10%, rgba(251,191,36,0.22) 0%, rgba(7,11,20,0) 65%)",
  roll_out:
    "radial-gradient(130% 100% at 50% -10%, rgba(34,211,168,0.20) 0%, rgba(7,11,20,0) 65%)",
  defer:
    "radial-gradient(130% 100% at 50% -10%, rgba(148,163,184,0.20) 0%, rgba(7,11,20,0) 65%)",
};

const VERDICT_ACCENT: Record<HorizonVerdictCode, string> = {
  material_flip: "#f43f5e",
  band_shift: "#fbbf24",
  touched: "#a855f7",
  stable: "#22d3a8",
};

const BAND_ACCENT: Record<HorizonBand, string> = {
  low: "#22d3a8",
  medium: "#a5b4fc",
  high: "#fbbf24",
  critical: "#f43f5e",
};

const BAND_ORDER: HorizonBand[] = ["low", "medium", "high", "critical"];

const ALERT_LABEL: Record<HorizonAlertFlip, string> = {
  cleared_to_alert: "Cleared → Alert",
  alert_to_cleared: "Alert → Cleared",
  still_alert: "Still Alert",
  still_cleared: "Still Cleared",
};

const ALERT_ACCENT: Record<HorizonAlertFlip, string> = {
  cleared_to_alert: "#f43f5e",
  alert_to_cleared: "#22d3a8",
  still_alert: "#fbbf24",
  still_cleared: "#94a3b8",
};

const DETECTOR_LABEL: Record<string, string> = {
  structuring: "Structuring",
  velocity_spike: "Velocity spike",
  round_trip: "Round-trip cycle",
  sanctions_hit: "Sanctions hit",
  adverse_media: "Adverse media",
  fan_in: "Fan-in",
  fan_out: "Fan-out",
  high_risk_geo: "High-risk geo",
  round_amount: "Round amount",
};

// Utility formatters — kept as top-level constants so React doesn't churn
// them on every render.
const fmt1 = (n: number) => n.toFixed(1);
const fmtSigned = (n: number) => `${n >= 0 ? "+" : ""}${n.toFixed(1)}`;
const fmtPct = (n: number, digits = 0) => `${(n * 100).toFixed(digits)}%`;

// ---------------------------------------------------------------------------
// Root page
// ---------------------------------------------------------------------------

export default function HorizonPage() {
  const [rules, setRules] = useState<HorizonRules | null>(null);
  const [report, setReport] = useState<HorizonReport | null>(null);
  const [presetName, setPresetName] = useState<string>("");
  const [selectedCase, setSelectedCase] = useState<string | null>(null);
  const [caseDetail, setCaseDetail] = useState<HorizonCaseDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Weight editor overrides — starts empty, layered on top of the preset.
  const [weightOverrides, setWeightOverrides] = useState<Record<string, number>>({});
  const [disabledOverrides, setDisabledOverrides] = useState<Set<string>>(new Set());

  // Bootstrap: rules + first sample.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [r, s] = await Promise.all([getHorizonRules(), getHorizonSample()]);
        if (cancelled) return;
        setRules(r);
        setReport(s);
        setPresetName(s.proposal.name);
        if (s.cases.length) setSelectedCase(s.cases[0].case_id);
      } catch (err: any) {
        if (!cancelled) setError(err?.message ?? "failed to load");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // Whenever the preset switches, reset overrides + refetch the sample.
  const applyPreset = async (name: string) => {
    setLoading(true);
    setWeightOverrides({});
    setDisabledOverrides(new Set());
    setPresetName(name);
    setError(null);
    try {
      const s = await getHorizonSample(name);
      setReport(s);
      if (s.cases.length) setSelectedCase(s.cases[0].case_id);
    } catch (err: any) {
      setError(err?.message ?? "failed to load preset");
    } finally {
      setLoading(false);
    }
  };

  // Live re-simulate whenever the caller edits a weight slider or toggles
  // a detector.  Everything else stays inherited from the preset.
  const currentPreset = useMemo(
    () => rules?.presets.find((p) => p.name === presetName) ?? null,
    [rules, presetName],
  );

  const rerunCustom = async () => {
    if (!currentPreset) return;
    setLoading(true);
    setError(null);
    const mergedWeights = { ...currentPreset.weights, ...weightOverrides };
    const disabled = new Set(currentPreset.disabled_detectors);
    disabledOverrides.forEach((d) => disabled.add(d));
    try {
      const s = await simulateHorizon({
        name: currentPreset.name + " (edited)",
        summary: currentPreset.summary,
        author: currentPreset.author,
        weights: mergedWeights,
        disabled_detectors: Array.from(disabled),
        sanctions_threshold: currentPreset.sanctions_threshold,
        additional_sanctions: currentPreset.additional_sanctions,
        jurisdiction_uplift: currentPreset.jurisdiction_uplift,
        jurisdiction_relief: currentPreset.jurisdiction_relief,
        band_cutoffs: currentPreset.band_cutoffs,
        alert_threshold: currentPreset.alert_threshold,
      });
      setReport(s);
    } catch (err: any) {
      setError(err?.message ?? "simulation failed");
    } finally {
      setLoading(false);
    }
  };

  // Case drill-down.
  useEffect(() => {
    if (!selectedCase || !report) return;
    let cancelled = false;
    (async () => {
      try {
        // We use the *current* proposal (not the preset) so edits are
        // reflected in the drill-down.  If nothing was edited, this is
        // identical to the preset.
        const detail = await explainHorizonCase(selectedCase, {
          name: report.proposal.name,
          summary: report.proposal.summary,
          author: report.proposal.author,
          weights: report.proposal.weights,
          disabled_detectors: report.proposal.disabled_detectors,
          sanctions_threshold: report.proposal.sanctions_threshold,
          additional_sanctions: report.proposal.additional_sanctions,
          jurisdiction_uplift: report.proposal.jurisdiction_uplift,
          jurisdiction_relief: report.proposal.jurisdiction_relief,
          band_cutoffs: report.proposal.band_cutoffs,
          alert_threshold: report.proposal.alert_threshold,
        });
        if (!cancelled) setCaseDetail(detail);
      } catch (err: any) {
        if (!cancelled) setCaseDetail(null);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [selectedCase, report]);

  if (loading && !report) return <BootShell />;
  if (error && !report) return <ErrorShell message={error} />;
  if (!report || !rules) return <BootShell />;

  const summary = report.summary;
  const action = summary.action_code;
  const p = report.proposal;

  return (
    <main className="min-h-screen text-slate-100">
      <TopNav />

      {/* -------- Hero -------- */}
      <section
        className="border-b border-white/5"
        style={{ background: ACTION_BG[action] }}
      >
        <div className="mx-auto max-w-7xl px-6 py-14">
          <div className="flex items-start justify-between gap-6 flex-wrap">
            <div className="flex-1 min-w-[280px]">
              <div className="text-xs uppercase tracking-[0.28em] text-white/50">
                Horizon · Regulatory-change impact
              </div>
              <h1 className="mt-2 text-4xl font-semibold tracking-tight text-white">
                {p.name}
              </h1>
              {p.summary && (
                <p className="mt-3 max-w-2xl text-sm leading-relaxed text-white/70">
                  {p.summary}
                </p>
              )}
              <div className="mt-4 flex flex-wrap gap-x-4 gap-y-2 text-xs text-white/50">
                <span>author · {p.author}</span>
                <span>engine · {report.engine_version}</span>
                <span>generated · {report.generated_at.slice(0, 19)}Z</span>
                <span>source · {report.source ?? report.cases_source ?? "fixture"}</span>
              </div>
            </div>
            <ActionPill action={action} label={summary.action_label} />
          </div>

          <div className="mt-8 grid grid-cols-2 gap-4 sm:grid-cols-4">
            <StatTile
              label="Cases replayed"
              value={summary.total_cases.toString()}
              hint={`avg |Δ| ${summary.avg_abs_score_delta.toFixed(1)} pts`}
            />
            <StatTile
              label="Cleared → Alert"
              value={summary.alert_flip.cleared_to_alert.toString()}
              accent={ALERT_ACCENT.cleared_to_alert}
              hint={
                summary.alert_flip.cleared_to_alert > 0
                  ? "requires re-review"
                  : "no re-fires"
              }
            />
            <StatTile
              label="Alert → Cleared"
              value={summary.alert_flip.alert_to_cleared.toString()}
              accent={ALERT_ACCENT.alert_to_cleared}
              hint={
                summary.alert_flip.alert_to_cleared > 0
                  ? "backlog relief"
                  : "no relief"
              }
            />
            <StatTile
              label="Material flips"
              value={summary.by_verdict.material_flip.toString()}
              accent={VERDICT_ACCENT.material_flip}
              hint={`${summary.by_verdict.band_shift} band shifts`}
            />
          </div>
        </div>
      </section>

      {/* -------- Preset picker -------- */}
      <section className="mx-auto max-w-7xl px-6 pt-8">
        <div className="text-xs uppercase tracking-[0.28em] text-white/40">
          Preset proposals
        </div>
        <div className="mt-3 flex gap-3 overflow-x-auto pb-2">
          {rules.presets.map((preset) => {
            const active = preset.name === presetName;
            return (
              <button
                key={preset.name}
                onClick={() => applyPreset(preset.name)}
                className={
                  "shrink-0 rounded-2xl border px-4 py-3 text-left transition " +
                  (active
                    ? "border-white/30 bg-white/10"
                    : "border-white/10 bg-white/[0.03] hover:border-white/20 hover:bg-white/[0.06]")
                }
                style={{ minWidth: 240, maxWidth: 320 }}
              >
                <div className="text-sm font-medium text-white">
                  {preset.name}
                </div>
                <div
                  className="mt-1 text-xs text-white/50"
                  style={{
                    display: "-webkit-box",
                    WebkitLineClamp: 2,
                    WebkitBoxOrient: "vertical",
                    overflow: "hidden",
                  }}
                >
                  {preset.summary}
                </div>
              </button>
            );
          })}
        </div>
      </section>

      {/* -------- Proposal summary (config diff chips) -------- */}
      <section className="mx-auto max-w-7xl px-6 pt-6">
        <ProposalChips proposal={p} rules={rules} />
      </section>

      {/* -------- Waterfall + band matrix -------- */}
      <section className="mx-auto grid max-w-7xl grid-cols-1 gap-6 px-6 pt-8 lg:grid-cols-2">
        <WaterfallCard summary={summary} />
        <BandMatrixCard summary={summary} />
      </section>

      {/* -------- Detector contribution -------- */}
      <section className="mx-auto max-w-7xl px-6 pt-6">
        <DetectorContributionCard summary={summary} />
      </section>

      {/* -------- Weight sliders (edit the preset) -------- */}
      <section className="mx-auto max-w-7xl px-6 pt-6">
        <WeightEditor
          rules={rules}
          preset={currentPreset}
          overrides={weightOverrides}
          setOverrides={setWeightOverrides}
          disabled={disabledOverrides}
          setDisabled={setDisabledOverrides}
          onApply={rerunCustom}
          loading={loading}
        />
      </section>

      {/* -------- Case impact table + drill-down -------- */}
      <section className="mx-auto grid max-w-7xl grid-cols-1 gap-6 px-6 pt-8 lg:grid-cols-5">
        <div className="lg:col-span-2">
          <CaseTable
            cases={report.cases}
            selected={selectedCase}
            onSelect={setSelectedCase}
          />
        </div>
        <div className="lg:col-span-3">
          <CaseDrillDown detail={caseDetail} />
        </div>
      </section>

      {/* -------- Rules footer -------- */}
      <section className="mx-auto max-w-7xl px-6 py-12">
        <RulesFooter rules={rules} presetName={presetName} />
      </section>
    </main>
  );
}

// ---------------------------------------------------------------------------
// Boot + error shells (small, consistent with the rest of TITAN)
// ---------------------------------------------------------------------------

function BootShell() {
  return (
    <main className="min-h-screen text-slate-100">
      <TopNav />
      <div className="mx-auto max-w-7xl px-6 py-20 text-sm text-white/50">
        Loading Horizon — replaying the backlog…
      </div>
    </main>
  );
}

function ErrorShell({ message }: { message: string }) {
  return (
    <main className="min-h-screen text-slate-100">
      <TopNav />
      <div className="mx-auto max-w-7xl px-6 py-20 text-sm text-rose-300">
        {message}
      </div>
    </main>
  );
}

function TopNav() {
  return (
    <div className="border-b border-white/5">
      <div className="mx-auto flex max-w-7xl items-center gap-4 px-6 py-3 text-xs uppercase tracking-[0.28em] text-white/40">
        <Link href="/" className="hover:text-white/80">
          TITAN
        </Link>
        <span className="text-white/20">/</span>
        <span className="text-white/70">Horizon</span>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Hero components
// ---------------------------------------------------------------------------

function ActionPill({
  action,
  label,
}: {
  action: HorizonActionCode;
  label: string;
}) {
  const accent = ACTION_ACCENT[action];
  return (
    <div
      className="rounded-2xl border px-5 py-4 min-w-[260px]"
      style={{
        borderColor: accent + "66",
        background: accent + "1A",
      }}
    >
      <div className="text-[10px] uppercase tracking-[0.32em] text-white/50">
        Suggested action
      </div>
      <div className="mt-1 text-lg font-semibold" style={{ color: accent }}>
        {action.replace("_", " ").toUpperCase()}
      </div>
      <div className="mt-1 text-xs text-white/60">{label}</div>
    </div>
  );
}

function StatTile({
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
    <div className="rounded-2xl border border-white/10 bg-white/[0.03] px-5 py-4">
      <div className="text-[10px] uppercase tracking-[0.32em] text-white/40">
        {label}
      </div>
      <div
        className="mt-1 text-3xl font-semibold tracking-tight"
        style={{ color: accent ?? "#f8fafc" }}
      >
        {value}
      </div>
      {hint && <div className="mt-1 text-xs text-white/50">{hint}</div>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Proposal chips — a one-line answer to "what changed?"
// ---------------------------------------------------------------------------

function ProposalChips({
  proposal,
  rules,
}: {
  proposal: HorizonProposal;
  rules: HorizonRules;
}) {
  const chips: React.ReactNode[] = [];
  // Weight deltas (against baseline)
  Object.entries(proposal.effective_weights).forEach(([name, w]) => {
    const base = rules.baseline_weights[name] ?? 0;
    if (Math.abs(w - base) < 0.01) return;
    const disabled = proposal.disabled_detectors.includes(name);
    chips.push(
      <Chip
        key={"w-" + name}
        tone={disabled ? "rose" : w > base ? "amber" : "teal"}
      >
        {DETECTOR_LABEL[name] || name}: {base.toFixed(1)} →{" "}
        <span className="font-semibold">{w.toFixed(1)}</span>
        {disabled && " (off)"}
      </Chip>,
    );
  });
  // Sanctions threshold
  if (proposal.sanctions_threshold != null) {
    chips.push(
      <Chip key="stgate" tone="violet">
        Sanctions gate ≥ {(proposal.sanctions_threshold * 100).toFixed(0)}%
      </Chip>,
    );
  }
  // Additional sanctions
  if (proposal.additional_sanctions.length) {
    chips.push(
      <Chip key="sdn" tone="rose">
        +{proposal.additional_sanctions.length} SDN entries
      </Chip>,
    );
  }
  // Jurisdiction uplift / relief
  if (proposal.jurisdiction_uplift.length) {
    chips.push(
      <Chip key="uplift" tone="rose">
        Uplift: {proposal.jurisdiction_uplift.join(" · ")}
      </Chip>,
    );
  }
  if (proposal.jurisdiction_relief.length) {
    chips.push(
      <Chip key="relief" tone="teal">
        Relief: {proposal.jurisdiction_relief.join(" · ")}
      </Chip>,
    );
  }
  // Band cutoffs
  if (proposal.band_cutoffs) {
    const [lo, mid, hi] = proposal.band_cutoffs;
    chips.push(
      <Chip key="bands" tone="amber">
        Bands: {lo.toFixed(0)} / {mid.toFixed(0)} / {hi.toFixed(0)}
      </Chip>,
    );
  }
  if (!chips.length) chips.push(<Chip key="noop">No config edits</Chip>);
  return (
    <div className="flex flex-wrap gap-2 rounded-2xl border border-white/10 bg-white/[0.02] p-4">
      {chips}
    </div>
  );
}

function Chip({
  children,
  tone = "slate",
}: {
  children: React.ReactNode;
  tone?: "slate" | "rose" | "amber" | "teal" | "violet";
}) {
  const map: Record<string, string> = {
    slate: "bg-white/[0.06] border-white/10 text-white/70",
    rose: "bg-rose-500/10 border-rose-400/30 text-rose-100",
    amber: "bg-amber-500/10 border-amber-400/30 text-amber-100",
    teal: "bg-teal-500/10 border-teal-400/30 text-teal-100",
    violet: "bg-violet-500/10 border-violet-400/30 text-violet-100",
  };
  return (
    <span
      className={
        "inline-flex items-center rounded-full border px-3 py-1 text-xs " +
        map[tone]
      }
    >
      {children}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Waterfall — a hand-rolled stacked bar showing alert-flip shares.
// ---------------------------------------------------------------------------

function WaterfallCard({ summary }: { summary: HorizonSummary }) {
  const total = summary.total_cases || 1;
  const order: HorizonAlertFlip[] = [
    "cleared_to_alert",
    "still_alert",
    "alert_to_cleared",
    "still_cleared",
  ];
  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-6">
      <div className="flex items-center justify-between">
        <div>
          <div className="text-[10px] uppercase tracking-[0.32em] text-white/40">
            Backlog waterfall
          </div>
          <div className="mt-1 text-lg font-medium text-white">
            Alert-fire distribution
          </div>
        </div>
        <div className="text-xs text-white/50">
          verdict change · {summary.by_verdict.material_flip} material,{" "}
          {summary.by_verdict.band_shift} shifts
        </div>
      </div>
      <div className="mt-6 flex h-8 overflow-hidden rounded-lg border border-white/10">
        {order.map((code) => {
          const share = summary.alert_flip[code] / total;
          if (share <= 0) return null;
          return (
            <div
              key={code}
              className="flex items-center justify-center text-[10px] font-medium text-black/70"
              style={{
                width: `${share * 100}%`,
                background: ALERT_ACCENT[code],
                minWidth: 24,
              }}
              title={`${ALERT_LABEL[code]}: ${summary.alert_flip[code]}`}
            >
              {share > 0.08 ? summary.alert_flip[code] : ""}
            </div>
          );
        })}
      </div>
      <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
        {order.map((code) => (
          <div key={code} className="flex items-center gap-2 text-xs">
            <span
              className="inline-block h-2 w-4 rounded-full"
              style={{ background: ALERT_ACCENT[code] }}
            />
            <span className="text-white/70">{ALERT_LABEL[code]}</span>
            <span className="ml-auto text-white/50">
              {summary.alert_flip[code]}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// 4x4 band matrix — old_band × new_band counts
// ---------------------------------------------------------------------------

function BandMatrixCard({ summary }: { summary: HorizonSummary }) {
  const total = summary.total_cases || 1;
  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-6">
      <div className="text-[10px] uppercase tracking-[0.32em] text-white/40">
        Band transition matrix
      </div>
      <div className="mt-1 text-lg font-medium text-white">
        Old band × new band (counts)
      </div>
      <div className="mt-6 overflow-x-auto">
        <table className="w-full border-separate border-spacing-1 text-xs">
          <thead>
            <tr>
              <th className="p-2 text-left text-white/40 font-normal">from ↓ / to →</th>
              {BAND_ORDER.map((b) => (
                <th key={b} className="p-2 text-center text-white/60">
                  <span
                    className="inline-block h-2 w-full max-w-[64px] rounded-full"
                    style={{ background: BAND_ACCENT[b] }}
                  />
                  <div className="mt-1 uppercase tracking-widest text-[10px]">
                    {b}
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {BAND_ORDER.map((oldB) => (
              <tr key={oldB}>
                <th className="p-2 text-left text-white/60">
                  <div className="flex items-center gap-2">
                    <span
                      className="inline-block h-2 w-4 rounded-full"
                      style={{ background: BAND_ACCENT[oldB] }}
                    />
                    <span className="uppercase tracking-widest text-[10px]">
                      {oldB}
                    </span>
                  </div>
                </th>
                {BAND_ORDER.map((newB) => {
                  const v = summary.band_matrix[oldB]?.[newB] ?? 0;
                  const share = v / total;
                  const diagonal = oldB === newB;
                  const bg = diagonal
                    ? `rgba(255,255,255,${0.04 + share * 0.14})`
                    : `${BAND_ACCENT[newB]}${Math.round(28 + share * 100)
                        .toString(16)
                        .padStart(2, "0")}`;
                  return (
                    <td
                      key={newB}
                      className="rounded-lg p-3 text-center"
                      style={{
                        background: bg,
                        color: v > 0 ? "#f8fafc" : "#94a3b8",
                        fontWeight: v > 0 ? 600 : 400,
                      }}
                    >
                      {v}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="mt-3 text-[11px] text-white/40">
        Off-diagonal is a flip. Colours track destination band.
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Detector contribution — horizontal bars sorted by |Δ|
// ---------------------------------------------------------------------------

function DetectorContributionCard({ summary }: { summary: HorizonSummary }) {
  const max = Math.max(
    ...summary.detector_contribution.map((r) => r.abs_delta),
    0.001,
  );
  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-6">
      <div className="flex items-center justify-between">
        <div>
          <div className="text-[10px] uppercase tracking-[0.32em] text-white/40">
            Detector contribution
          </div>
          <div className="mt-1 text-lg font-medium text-white">
            |Δ| points, backlog total
          </div>
        </div>
        <div className="text-xs text-white/50">
          top mover ·{" "}
          <span className="text-white/80">
            {DETECTOR_LABEL[summary.detector_contribution[0]?.name ?? ""] ||
              "—"}
          </span>
        </div>
      </div>
      <div className="mt-6 space-y-3">
        {summary.detector_contribution.map((row) => (
          <div key={row.name} className="flex items-center gap-4">
            <div className="w-40 shrink-0 text-xs text-white/60">
              {DETECTOR_LABEL[row.name] || row.name}
            </div>
            <div className="relative flex-1 h-3 rounded-full bg-white/[0.06] overflow-hidden">
              <div
                className="absolute left-0 top-0 h-full rounded-full"
                style={{
                  width: `${(row.abs_delta / max) * 100}%`,
                  background:
                    row.abs_delta > 0
                      ? "linear-gradient(90deg,#a855f7,#f43f5e)"
                      : "#334155",
                }}
              />
            </div>
            <div className="w-16 text-right text-xs tabular-nums text-white/70">
              {row.abs_delta.toFixed(1)}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Weight editor — the interactive part.  Sliders scale each detector
// weight in [0, MAX_WEIGHT], toggle disables it.
// ---------------------------------------------------------------------------

function WeightEditor({
  rules,
  preset,
  overrides,
  setOverrides,
  disabled,
  setDisabled,
  onApply,
  loading,
}: {
  rules: HorizonRules;
  preset: HorizonProposal | null;
  overrides: Record<string, number>;
  setOverrides: (o: Record<string, number>) => void;
  disabled: Set<string>;
  setDisabled: (d: Set<string>) => void;
  onApply: () => void;
  loading: boolean;
}) {
  const setWeight = (name: string, value: number) => {
    setOverrides({ ...overrides, [name]: value });
  };
  const toggleDisabled = (name: string) => {
    const next = new Set(disabled);
    if (next.has(name)) next.delete(name);
    else next.add(name);
    setDisabled(next);
  };
  const reset = () => {
    setOverrides({});
    setDisabled(new Set());
  };
  const dirty =
    Object.keys(overrides).length > 0 || disabled.size > 0;

  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-6">
      <div className="flex items-center justify-between">
        <div>
          <div className="text-[10px] uppercase tracking-[0.32em] text-white/40">
            Layer edits on the preset
          </div>
          <div className="mt-1 text-lg font-medium text-white">
            Detector weight sliders
          </div>
        </div>
        <div className="flex gap-2">
          <button
            onClick={reset}
            disabled={!dirty || loading}
            className="rounded-lg border border-white/10 px-3 py-1.5 text-xs text-white/70 hover:bg-white/[0.06] disabled:opacity-40"
          >
            Reset
          </button>
          <button
            onClick={onApply}
            disabled={!dirty || loading}
            className="rounded-lg border border-violet-400/40 bg-violet-500/20 px-3 py-1.5 text-xs text-violet-100 hover:bg-violet-500/30 disabled:opacity-40"
          >
            {loading ? "Simulating…" : "Re-simulate"}
          </button>
        </div>
      </div>
      <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {rules.detector_order.map((name) => {
          const baseWeight = preset?.effective_weights[name] ?? rules.baseline_weights[name] ?? 0;
          const current = overrides[name] ?? baseWeight;
          const isDisabled =
            disabled.has(name) ||
            (preset?.disabled_detectors.includes(name) && !disabled.has(name)
              ? false
              : disabled.has(name));
          return (
            <div
              key={name}
              className={
                "rounded-xl border p-4 " +
                (isDisabled
                  ? "border-rose-400/30 bg-rose-500/10"
                  : "border-white/10 bg-white/[0.02]")
              }
            >
              <div className="flex items-center justify-between">
                <div className="text-xs font-medium text-white/80">
                  {DETECTOR_LABEL[name] || name}
                </div>
                <button
                  onClick={() => toggleDisabled(name)}
                  className={
                    "rounded border px-2 py-0.5 text-[10px] uppercase tracking-widest transition " +
                    (isDisabled
                      ? "border-rose-400/40 bg-rose-500/20 text-rose-100"
                      : "border-white/10 bg-white/[0.04] text-white/50 hover:bg-white/[0.08]")
                  }
                >
                  {isDisabled ? "off" : "on"}
                </button>
              </div>
              <input
                type="range"
                min={0}
                max={rules.max_weight}
                step={0.5}
                value={current}
                onChange={(e) => setWeight(name, parseFloat(e.target.value))}
                disabled={isDisabled}
                className="mt-3 w-full accent-violet-400"
              />
              <div className="mt-1 flex items-center justify-between text-[11px] tabular-nums text-white/50">
                <span>0</span>
                <span
                  className="text-white/80"
                  style={{ color: current > baseWeight ? "#fbbf24" : current < baseWeight ? "#22d3a8" : "#e2e8f0" }}
                >
                  {current.toFixed(1)}
                </span>
                <span>{rules.max_weight}</span>
              </div>
              <div className="mt-1 text-[10px] text-white/40">
                baseline {rules.baseline_weights[name]?.toFixed(1) ?? "0.0"} → preset {baseWeight.toFixed(1)}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Case impact table — click-through drives the drill-down
// ---------------------------------------------------------------------------

function CaseTable({
  cases,
  selected,
  onSelect,
}: {
  cases: HorizonImpact[];
  selected: string | null;
  onSelect: (id: string) => void;
}) {
  const [verdictFilter, setVerdictFilter] = useState<
    HorizonVerdictCode | "all"
  >("all");
  const filtered = useMemo(
    () =>
      verdictFilter === "all"
        ? cases
        : cases.filter((c) => c.verdict === verdictFilter),
    [cases, verdictFilter],
  );

  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.03]">
      <div className="flex items-center justify-between border-b border-white/10 px-5 py-4">
        <div>
          <div className="text-[10px] uppercase tracking-[0.32em] text-white/40">
            Case impact
          </div>
          <div className="mt-1 text-lg font-medium text-white">
            {filtered.length} cases · sorted by |Δ|
          </div>
        </div>
        <select
          value={verdictFilter}
          onChange={(e) =>
            setVerdictFilter(e.target.value as HorizonVerdictCode | "all")
          }
          className="rounded-lg border border-white/10 bg-white/[0.05] px-2 py-1 text-xs text-white/70"
        >
          <option value="all">All verdicts</option>
          <option value="material_flip">Material flip</option>
          <option value="band_shift">Band shift</option>
          <option value="touched">Touched</option>
          <option value="stable">Stable</option>
        </select>
      </div>
      <div className="max-h-[520px] overflow-y-auto">
        {filtered.map((c) => {
          const active = c.case_id === selected;
          return (
            <button
              key={c.case_id}
              onClick={() => onSelect(c.case_id)}
              className={
                "flex w-full items-start gap-3 border-b border-white/5 px-5 py-4 text-left transition " +
                (active ? "bg-violet-500/10" : "hover:bg-white/[0.03]")
              }
            >
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span
                    className="inline-block h-1.5 w-1.5 rounded-full"
                    style={{ background: VERDICT_ACCENT[c.verdict] }}
                  />
                  <span className="truncate text-sm font-medium text-white">
                    {c.display_name || c.account_id}
                  </span>
                </div>
                <div className="mt-1 truncate text-[11px] text-white/50">
                  {c.case_id} · {c.driver_note}
                </div>
              </div>
              <div className="text-right">
                <div className="text-xs text-white/60">
                  <BandChip band={c.old_band} /> →{" "}
                  <BandChip band={c.new_band} />
                </div>
                <div
                  className="mt-1 text-sm tabular-nums font-semibold"
                  style={{
                    color:
                      c.score_delta > 0
                        ? "#fbbf24"
                        : c.score_delta < 0
                        ? "#22d3a8"
                        : "#94a3b8",
                  }}
                >
                  {fmtSigned(c.score_delta)}
                </div>
              </div>
            </button>
          );
        })}
        {filtered.length === 0 && (
          <div className="px-5 py-16 text-center text-xs text-white/40">
            No cases match this verdict.
          </div>
        )}
      </div>
    </div>
  );
}

function BandChip({ band }: { band: HorizonBand }) {
  return (
    <span
      className="inline-block rounded-full px-2 py-0.5 text-[10px] font-medium uppercase tracking-widest"
      style={{
        background: `${BAND_ACCENT[band]}22`,
        color: BAND_ACCENT[band],
      }}
    >
      {band}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Case drill-down — score arc + per-detector Δ bars + sanctions block
// ---------------------------------------------------------------------------

function CaseDrillDown({ detail }: { detail: HorizonCaseDetail | null }) {
  if (!detail) {
    return (
      <div className="flex h-full min-h-[240px] items-center justify-center rounded-2xl border border-white/10 bg-white/[0.02] text-sm text-white/40">
        Pick a case to see the per-detector explainer.
      </div>
    );
  }
  const c = detail.impact;
  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-6">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div className="min-w-0">
          <div className="text-[10px] uppercase tracking-[0.32em] text-white/40">
            Case drill-down
          </div>
          <div className="mt-1 truncate text-lg font-medium text-white">
            {c.display_name || c.account_id}
          </div>
          <div className="mt-0.5 text-xs text-white/50">
            {c.case_id} · {c.status} · {c.priority}
            {c.assignee ? ` · ${c.assignee}` : ""}
          </div>
          <div className="mt-4">
            <VerdictBadge verdict={c.verdict} />
          </div>
        </div>
        <ScoreArc old_score={c.old_score} new_score={c.new_score} />
      </div>

      <div className="mt-6">
        <div className="text-[10px] uppercase tracking-[0.32em] text-white/40">
          Detector delta
        </div>
        <div className="mt-3 space-y-2">
          {c.detectors.map((d) => (
            <DetectorRow key={d.name} d={d} />
          ))}
        </div>
      </div>

      {(c.fired_sanctions.length > 0 || c.dropped_sanctions.length > 0) && (
        <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2">
          <SanctionsBlock
            title="Fired hits"
            hits={c.fired_sanctions}
            tone="rose"
            emptyText="No sanctions hits."
          />
          <SanctionsBlock
            title="Dropped hits"
            hits={c.dropped_sanctions}
            tone="teal"
            emptyText="No hits dropped."
          />
        </div>
      )}
      <div className="mt-6 text-[11px] text-white/40">
        Driver · {c.driver_note}
      </div>
    </div>
  );
}

function VerdictBadge({ verdict }: { verdict: HorizonVerdictCode }) {
  const accent = VERDICT_ACCENT[verdict];
  const label: Record<HorizonVerdictCode, string> = {
    material_flip: "Material flip",
    band_shift: "Band shift",
    touched: "Score touched",
    stable: "Stable",
  };
  return (
    <span
      className="inline-flex items-center rounded-full border px-3 py-1 text-xs"
      style={{
        borderColor: accent + "66",
        color: accent,
        background: accent + "22",
      }}
    >
      {label[verdict]}
    </span>
  );
}

function ScoreArc({
  old_score,
  new_score,
}: {
  old_score: number;
  new_score: number;
}) {
  const size = 148;
  const stroke = 10;
  const r = (size - stroke) / 2;
  const cx = size / 2;
  const cy = size / 2;
  const circ = 2 * Math.PI * r;
  const oldOffset = circ - (old_score / 100) * circ;
  const newOffset = circ - (new_score / 100) * circ;
  const delta = new_score - old_score;
  const deltaColor =
    delta > 0 ? "#fbbf24" : delta < 0 ? "#22d3a8" : "#94a3b8";
  return (
    <div className="relative">
      <svg width={size} height={size} className="block">
        <circle
          cx={cx}
          cy={cy}
          r={r}
          fill="none"
          stroke="rgba(255,255,255,0.06)"
          strokeWidth={stroke}
        />
        <circle
          cx={cx}
          cy={cy}
          r={r}
          fill="none"
          stroke="#334155"
          strokeWidth={stroke}
          strokeDasharray={circ}
          strokeDashoffset={oldOffset}
          transform={`rotate(-90 ${cx} ${cy})`}
        />
        <circle
          cx={cx}
          cy={cy}
          r={r - stroke - 2}
          fill="none"
          stroke={deltaColor}
          strokeWidth={stroke}
          strokeDasharray={circ}
          strokeDashoffset={newOffset}
          transform={`rotate(-90 ${cx} ${cy})`}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <div
          className="text-2xl font-semibold tabular-nums"
          style={{ color: deltaColor }}
        >
          {fmt1(new_score)}
        </div>
        <div className="text-[10px] uppercase tracking-widest text-white/40">
          {fmt1(old_score)} → {fmt1(new_score)}
        </div>
        <div className="text-[10px] tabular-nums" style={{ color: deltaColor }}>
          {fmtSigned(delta)} pts
        </div>
      </div>
    </div>
  );
}

function DetectorRow({ d }: { d: HorizonDetectorDelta }) {
  const width = Math.max(Math.abs(d.old_points), Math.abs(d.new_points), 1);
  const scale = 60; // MAX_FACTOR_POINTS
  const oldPct = (d.old_points / scale) * 100;
  const newPct = (d.new_points / scale) * 100;
  const delta = d.delta;
  const tone = delta > 0.05 ? "#fbbf24" : delta < -0.05 ? "#22d3a8" : "#94a3b8";
  return (
    <div className="rounded-lg border border-white/10 bg-white/[0.02] p-3">
      <div className="flex items-center justify-between text-xs">
        <div className="text-white/80">{DETECTOR_LABEL[d.name] || d.name}</div>
        <div className="tabular-nums text-white/60">
          {d.old_points.toFixed(1)} →{" "}
          <span style={{ color: tone }}>
            {d.new_points.toFixed(1)} ({fmtSigned(delta)})
          </span>
        </div>
      </div>
      <div className="mt-2 relative h-2 rounded-full bg-white/[0.05]">
        <div
          className="absolute top-0 h-full rounded-full"
          style={{
            width: `${oldPct}%`,
            background: "#475569",
          }}
        />
        <div
          className="absolute top-0 h-full rounded-full"
          style={{
            width: `${newPct}%`,
            background: tone,
            opacity: 0.7,
          }}
        />
      </div>
      <div className="mt-2 flex items-center justify-between text-[10px] text-white/40">
        <span>
          intensity {(d.intensity * 100).toFixed(0)}% · weight {d.old_weight.toFixed(1)} → {d.new_weight.toFixed(1)}
        </span>
        <span className="max-w-[60%] truncate text-right">{d.reason}</span>
      </div>
    </div>
  );
}

function SanctionsBlock({
  title,
  hits,
  tone,
  emptyText,
}: {
  title: string;
  hits: any[];
  tone: "rose" | "teal";
  emptyText: string;
}) {
  const accent = tone === "rose" ? "#f43f5e" : "#22d3a8";
  return (
    <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4">
      <div className="flex items-center justify-between">
        <div className="text-[10px] uppercase tracking-[0.32em] text-white/40">
          {title}
        </div>
        <div
          className="text-[10px] font-semibold"
          style={{ color: accent }}
        >
          {hits.length}
        </div>
      </div>
      {hits.length === 0 ? (
        <div className="mt-2 text-xs text-white/40">{emptyText}</div>
      ) : (
        <ul className="mt-2 space-y-2 text-xs">
          {hits.map((h, i) => (
            <li key={i} className="rounded-lg border border-white/5 bg-white/[0.03] p-2">
              <div className="text-white/80">
                {h.name || h.subject_name || "—"}
              </div>
              <div className="mt-0.5 text-[11px] text-white/50">
                {[h.list, h.jurisdiction, h.matched_alias]
                  .filter(Boolean)
                  .join(" · ")}
              </div>
              {typeof h.similarity === "number" && (
                <div className="mt-1 text-[10px] tabular-nums text-white/40">
                  similarity {(h.similarity * 100).toFixed(1)}%
                </div>
              )}
              {h.source === "proposal" && (
                <span
                  className="mt-1 inline-block rounded-full border border-rose-400/30 bg-rose-500/10 px-2 py-0.5 text-[10px] text-rose-200"
                >
                  new SDN
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Rules footer
// ---------------------------------------------------------------------------

function RulesFooter({
  rules,
  presetName,
}: {
  rules: HorizonRules;
  presetName: string;
}) {
  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.02] p-6">
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <div className="text-[10px] uppercase tracking-[0.32em] text-white/40">
            Engine
          </div>
          <div className="mt-1 text-sm text-white/80">
            {rules.engine_version}
          </div>
          <div className="mt-1 text-[11px] text-white/40">
            Replay is deterministic — same proposal + same case snapshot →
            same report, forever.
          </div>
        </div>
        <a
          href={horizonExportUrl(presetName)}
          target="_blank"
          rel="noreferrer"
          className="rounded-lg border border-white/10 bg-white/[0.04] px-4 py-2 text-xs text-white/80 hover:bg-white/[0.08]"
        >
          Download impact memo (.md)
        </a>
      </div>
      <div className="mt-5 flex flex-wrap gap-2">
        {rules.verdict_ladder.map((v) => (
          <Chip
            key={v.code}
            tone={
              v.accent === "rose"
                ? "rose"
                : v.accent === "amber"
                ? "amber"
                : v.accent === "violet"
                ? "violet"
                : "teal"
            }
          >
            {v.label}
          </Chip>
        ))}
      </div>
      <div className="mt-4 grid grid-cols-2 gap-2 text-[11px] text-white/50 sm:grid-cols-4">
        <div>
          <span className="text-white/40">Band cutoffs · </span>
          {rules.default_band_cutoffs.join(" / ")}
        </div>
        <div>
          <span className="text-white/40">Alert threshold · </span>
          {rules.default_alert_threshold}
        </div>
        <div>
          <span className="text-white/40">Sanctions gate · </span>
          {rules.default_sanctions_threshold.toFixed(2)}
        </div>
        <div>
          <span className="text-white/40">Detectors · </span>
          {rules.detector_order.length}
        </div>
      </div>
    </div>
  );
}
