"use client";

/*
 * Nexus — TITAN's beneficial-ownership + sanctions/PEP-reach surface
 * (round-17, day-80).
 *
 * Every prior TITAN surface reasons about a *transaction* or *alert*.
 * Nexus reasons about the *legal structure* — who really owns and
 * controls this entity once you unwind the holding companies, the
 * nominees, and the offshore chain.  It answers four regulator
 * questions in one deterministic pass:
 *
 *   1. FinCEN CTA — who is the beneficial owner (≥ 25% aggregate)?
 *   2. OFAC 50% rule — does aggregate sanctioned control block the
 *      target, whether or not it appears on the SDN list?
 *   3. FATF Rec. 24 — how layered is the corporate structure?
 *   4. EU 6AMLD — do nominee / trustee edges obscure the UBO?
 *
 * Render stack (hand-rolled SVG + CSS, zero charting libs):
 *
 *   1. Hero — verdict-tinted radial banner, opacity conic ring, target
 *      chips (kind / jurisdiction / verdict reason).
 *   2. Portfolio tiles — entities, edges, sanctioned hits, PEP hits,
 *      average opacity, verdict distribution ribbon.
 *   3. Target picker — verdict-tinted searchable list of every entity
 *      the sample analyses.
 *   4. Ownership Chain — hand-rolled radial SVG.  Target at centre,
 *      controllers rendered above by depth.  Edge stroke width scales
 *      with pct; sanctioned paths glow rose, PEP paths glow amber.
 *   5. UBO table — the natural-persons the FinCEN 25% rule flags.
 *   6. Sanctions + PEP reach panels — side-by-side with reach codes.
 *   7. Opacity components — seven horizontal bars, one per component,
 *      weighted proportionally.
 *   8. Ownership paths — top-6 rows with chain, depth, cumulative pct.
 *   9. Reach picker → radial burst — pick any sanctioned/PEP
 *      controller and see every downstream target with aggregate reach.
 *  10. Rules footer — engine version + verdict ladder chips.
 */

import { useEffect, useMemo, useState } from "react";

import {
  getNexusEntity,
  getNexusReach,
  getNexusRules,
  getNexusSample,
  listNexusCandidates,
  nexusExportUrl,
  NexusCandidate,
  NexusController,
  NexusPath,
  NexusReachReport,
  NexusReachRow,
  NexusRules,
  NexusSampleReport,
  NexusTargetReport,
  NexusVerdictCode,
} from "../../lib/api";

// ---------------------------------------------------------------------------
// Palette + label maps — kept as top-level constants for stable rendering.
// ---------------------------------------------------------------------------

const VERDICT_ACCENT: Record<NexusVerdictCode, string> = {
  blocked_by_sanctions: "#f43f5e",
  sanctions_exposed: "#fb7185",
  pep_edd_required: "#fbbf24",
  opaque_structure: "#a855f7",
  transparent_structure: "#22d3a8",
};

const VERDICT_BG: Record<NexusVerdictCode, string> = {
  blocked_by_sanctions:
    "radial-gradient(130% 100% at 50% -10%, rgba(244,63,94,0.28) 0%, rgba(7,11,20,0) 65%)",
  sanctions_exposed:
    "radial-gradient(130% 100% at 50% -10%, rgba(251,113,133,0.22) 0%, rgba(7,11,20,0) 65%)",
  pep_edd_required:
    "radial-gradient(130% 100% at 50% -10%, rgba(251,191,36,0.20) 0%, rgba(7,11,20,0) 65%)",
  opaque_structure:
    "radial-gradient(130% 100% at 50% -10%, rgba(168,85,247,0.22) 0%, rgba(7,11,20,0) 65%)",
  transparent_structure:
    "radial-gradient(130% 100% at 50% -10%, rgba(34,211,168,0.22) 0%, rgba(7,11,20,0) 65%)",
};

const KIND_LABEL: Record<string, string> = {
  individual: "Individual",
  corporation: "Corporation",
  trust: "Trust",
  foundation: "Foundation",
  spv: "SPV",
  partnership: "Partnership",
};

const KIND_SHAPE: Record<string, string> = {
  individual: "●",
  corporation: "■",
  trust: "◆",
  foundation: "▲",
  spv: "◑",
  partnership: "◇",
};

const SHELL_LABEL: Record<string, string> = {
  holding_only: "Holding-only",
  no_employees: "No employees",
  thin_capital: "Thin capital",
  recent_incorporation: "Recently incorporated",
  nominee_directors: "Nominee directors",
  mail_drop_address: "Mail-drop address",
};

const EDGE_TYPE_LABEL: Record<string, string> = {
  voting: "Voting",
  economic: "Economic",
  nominee: "Nominee",
  trustee: "Trustee",
  founder: "Founder",
  control: "Substantial control",
};

const OPACITY_COMPONENT_LABEL: Record<string, string> = {
  depth: "Chain depth",
  shell: "Shell node share",
  offshore: "Offshore share",
  nominee: "Nominee / trustee share",
  dispersal: "Controller dispersal",
  cycle: "Cycle penalty",
  thinness: "Thin-capital share",
};

const REACH_TONE: Record<string, string> = {
  BLOCKED_REACH: "#f43f5e",
  REPORTABLE_REACH: "#fb923c",
  EXPOSED_LINK: "#a855f7",
  EDD_REQUIRED: "#fbbf24",
  PEP_LINKED: "#f472b6",
  PEP_NEXUS: "#c4b5fd",
};

const UBO_LABEL: Record<string, string> = {
  beneficial_owner: "Beneficial owner",
  screening_required: "Screening required",
  corporate_owner: "Corporate controller",
  de_minimis: "De minimis",
};

const OPACITY_BAND_TONE: Record<string, string> = {
  opaque: "#a855f7",
  layered: "#f472b6",
  moderate: "#fbbf24",
  clean: "#22d3a8",
};

const fmtPct = (v: number, digits = 1) =>
  `${(Math.max(0, Math.min(1, v)) * 100).toFixed(digits)}%`;

// ---------------------------------------------------------------------------
// Root page
// ---------------------------------------------------------------------------

export default function NexusPage() {
  const [sample, setSample] = useState<NexusSampleReport | null>(null);
  const [rules, setRules] = useState<NexusRules | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [entity, setEntity] = useState<NexusTargetReport | null>(null);
  const [loadingEntity, setLoadingEntity] = useState(false);
  const [candidates, setCandidates] = useState<NexusCandidate[]>([]);
  const [reachRoot, setReachRoot] = useState<string | null>(null);
  const [reach, setReach] = useState<NexusReachReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [verdictFilter, setVerdictFilter] = useState<
    NexusVerdictCode | "all"
  >("all");

  // Bootstrap: pull rules, sample, and controller candidates in parallel.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [s, r, c] = await Promise.all([
          getNexusSample(),
          getNexusRules(),
          listNexusCandidates(),
        ]);
        if (cancelled) return;
        setSample(s);
        setRules(r);
        setCandidates(c.candidates);
        const initial = s.highlight_target_id ?? s.reports[0]?.target.id ?? null;
        setSelected(initial);
        const sanctionedRoot =
          c.candidates.find((cc) => cc.sanctioned) ??
          c.candidates.find((cc) => cc.pep) ??
          c.candidates[0];
        if (sanctionedRoot) setReachRoot(sanctionedRoot.id);
      } catch (err: any) {
        if (!cancelled) setError(err?.message ?? "failed to load");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // Full entity report — the one the surface draws its charts from.
  useEffect(() => {
    if (!selected) return;
    let cancelled = false;
    setLoadingEntity(true);
    (async () => {
      try {
        const r = await getNexusEntity(selected);
        if (!cancelled) setEntity(r.report);
      } catch (err: any) {
        if (!cancelled) setError(err?.message ?? "failed to load entity");
      } finally {
        if (!cancelled) setLoadingEntity(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [selected]);

  // Reach report (downstream from a sanctioned/PEP root).
  useEffect(() => {
    if (!reachRoot) return;
    let cancelled = false;
    (async () => {
      try {
        const r = await getNexusReach(reachRoot);
        if (!cancelled) setReach(r);
      } catch (err: any) {
        if (!cancelled) setError(err?.message ?? "failed to load reach");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [reachRoot]);

  const targetsFiltered = useMemo(() => {
    if (!sample) return [] as NexusTargetReport[];
    const q = query.trim().toLowerCase();
    return sample.reports.filter((r) => {
      if (verdictFilter !== "all" && r.verdict.code !== verdictFilter)
        return false;
      if (!q) return true;
      return (
        r.target.id.toLowerCase().includes(q) ||
        r.target.name.toLowerCase().includes(q) ||
        r.target.jurisdiction.toLowerCase().includes(q)
      );
    });
  }, [sample, query, verdictFilter]);

  if (error && !sample) return <ErrorBanner message={error} />;
  if (!sample || !rules) return <Loading />;

  const view = entity ?? sample.reports.find((r) => r.target.id === selected)!;

  return (
    <main className="mt-6 flex flex-col gap-8">
      <Hero report={view} portfolio={sample.portfolio} rules={rules} />

      <PortfolioStrip sample={sample} />

      <TargetPicker
        reports={sample.reports}
        filtered={targetsFiltered}
        selected={selected}
        onSelect={setSelected}
        query={query}
        onQuery={setQuery}
        verdictFilter={verdictFilter}
        onVerdictFilter={setVerdictFilter}
      />

      <OwnershipChain
        report={view}
        loading={loadingEntity}
        onSelectController={(id) => {
          const cand = candidates.find((c) => c.id === id);
          if (cand) setReachRoot(id);
        }}
      />

      <div className="grid gap-6 lg:grid-cols-2">
        <UboPanel report={view} rules={rules} />
        <SanctionsPepPanel report={view} rules={rules} />
      </div>

      <OpacityBreakdown report={view} rules={rules} />

      <OwnershipPathsTable report={view} />

      <ReachSection
        candidates={candidates}
        selected={reachRoot}
        onSelect={setReachRoot}
        report={reach}
        rules={rules}
      />

      <RulesFooter rules={rules} corpusHash={sample.corpus_hash} />

      {error ? (
        <p className="text-xs text-rose-300/80">error: {error}</p>
      ) : null}
    </main>
  );
}

// ---------------------------------------------------------------------------
// Hero
// ---------------------------------------------------------------------------

function Hero({
  report,
  portfolio,
  rules,
}: {
  report: NexusTargetReport;
  portfolio: NexusSampleReport["portfolio"];
  rules: NexusRules;
}) {
  const accent = VERDICT_ACCENT[report.verdict.code];
  const bg = VERDICT_BG[report.verdict.code];
  const opacity = report.opacity.score;
  const opacityBandTone = OPACITY_BAND_TONE[report.opacity.band] ?? "#94a3b8";
  return (
    <section
      className="relative overflow-hidden rounded-3xl border border-white/10 bg-slate-950/70 p-8"
      style={{ backgroundImage: bg }}
    >
      <div className="flex flex-col gap-8 md:flex-row md:items-center">
        <ConicRing value={opacity / 100} accent={accent} label={String(opacity)} sub="opacity" />
        <div className="flex flex-1 flex-col gap-3">
          <div className="flex flex-wrap items-baseline gap-3">
            <span
              className="rounded-full px-2.5 py-0.5 text-[10px] font-semibold uppercase tracking-[0.14em]"
              style={{
                background: `${accent}22`,
                color: accent,
                boxShadow: `inset 0 0 0 1px ${accent}44`,
              }}
            >
              {report.verdict.label}
            </span>
            <span className="text-[11px] uppercase tracking-widest text-slate-400">
              {KIND_LABEL[report.target.kind] ?? report.target.kind}
              {" · "}
              {report.target.jurisdiction || "—"}
              {" · risk "}
              {report.target.jurisdiction_risk.toFixed(2)}
            </span>
          </div>
          <h1 className="text-3xl font-semibold text-white md:text-4xl">
            {report.target.name}
          </h1>
          <p className="max-w-2xl text-sm leading-relaxed text-slate-300/90">
            {report.verdict.reason}
          </p>
          <div className="mt-1 flex flex-wrap gap-2">
            {report.target.shell_indicators.length ? (
              report.target.shell_indicators.map((s) => (
                <span
                  key={s}
                  className="rounded-full border border-rose-400/40 bg-rose-400/10 px-2 py-0.5 text-[10px] uppercase tracking-wider text-rose-200"
                >
                  {SHELL_LABEL[s] ?? s}
                </span>
              ))
            ) : (
              <span className="rounded-full border border-emerald-400/40 bg-emerald-400/10 px-2 py-0.5 text-[10px] uppercase tracking-wider text-emerald-200">
                No shell indicators
              </span>
            )}
            <span
              className="rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-wider"
              style={{
                borderColor: `${opacityBandTone}55`,
                background: `${opacityBandTone}18`,
                color: opacityBandTone,
              }}
            >
              {report.opacity.band} — depth {report.opacity.max_depth ?? 0}
            </span>
          </div>
        </div>
        <div className="flex min-w-[200px] flex-col gap-2 rounded-2xl border border-white/10 bg-black/30 p-4 text-xs text-slate-300">
          <SmallStat
            label="Beneficial owners"
            value={report.ubos.length}
            tone={report.ubos.length ? "#22d3a8" : "#a855f7"}
          />
          <SmallStat
            label="Ownership paths"
            value={report.path_count}
            tone="#67e8f9"
          />
          <SmallStat
            label="Sanctioned aggregate"
            value={fmtPct(report.sanctions.aggregate, 1)}
            tone={
              report.sanctions.verdict === "CLEAN"
                ? "#22d3a8"
                : report.sanctions.verdict === "BLOCKED"
                ? "#f43f5e"
                : "#fb7185"
            }
          />
          <SmallStat
            label="PEP nexus"
            value={report.pep.count}
            tone={report.pep.count ? "#fbbf24" : "#22d3a8"}
          />
          <div className="pt-2 text-[10px] uppercase tracking-widest text-slate-500">
            Engine {rules.engine} · {portfolio.entities} entities · {portfolio.edges} edges
          </div>
        </div>
      </div>
    </section>
  );
}

function ConicRing({
  value,
  accent,
  label,
  sub,
}: {
  value: number;
  accent: string;
  label: string;
  sub: string;
}) {
  const pct = Math.max(0, Math.min(1, value));
  const deg = pct * 360;
  return (
    <div
      className="relative flex h-[148px] w-[148px] items-center justify-center rounded-full"
      style={{
        background: `conic-gradient(${accent} 0deg ${deg}deg, rgba(148,163,184,0.14) ${deg}deg 360deg)`,
        boxShadow: `0 0 42px ${accent}22`,
      }}
    >
      <div className="flex h-[124px] w-[124px] flex-col items-center justify-center rounded-full bg-slate-950/95">
        <span className="text-[36px] font-semibold leading-none text-white">
          {label}
        </span>
        <span className="mt-1 text-[10px] uppercase tracking-widest text-slate-400">
          {sub}
        </span>
      </div>
    </div>
  );
}

function SmallStat({
  label,
  value,
  tone,
}: {
  label: string;
  value: number | string;
  tone: string;
}) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-b border-white/5 py-1.5 last:border-b-0">
      <span className="text-[10px] uppercase tracking-wider text-slate-500">
        {label}
      </span>
      <span
        className="text-sm font-semibold tabular-nums"
        style={{ color: tone }}
      >
        {value}
      </span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Portfolio strip
// ---------------------------------------------------------------------------

function PortfolioStrip({ sample }: { sample: NexusSampleReport }) {
  const p = sample.portfolio;
  const tiles = [
    { label: "Entities", value: p.entities, tone: "#67e8f9" },
    { label: "Ownership edges", value: p.edges, tone: "#a855f7" },
    { label: "Offshore nodes", value: p.offshore, tone: "#fb923c" },
    { label: "Shell-flagged", value: p.shell_flagged, tone: "#f472b6" },
    { label: "Sanctioned hits", value: p.sanctioned_hits, tone: "#f43f5e" },
    { label: "PEP hits", value: p.pep_hits, tone: "#fbbf24" },
    { label: "Avg opacity", value: p.opacity_avg, tone: "#22d3a8" },
  ];
  const totalTargets = Math.max(1, p.targets);
  const ladder: NexusVerdictCode[] = [
    "blocked_by_sanctions",
    "sanctions_exposed",
    "pep_edd_required",
    "opaque_structure",
    "transparent_structure",
  ];
  return (
    <section className="grid gap-4 rounded-2xl border border-white/10 bg-slate-950/60 p-5">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-7">
        {tiles.map((t) => (
          <div
            key={t.label}
            className="rounded-xl border border-white/10 bg-black/30 px-4 py-3"
          >
            <div className="text-[10px] uppercase tracking-widest text-slate-500">
              {t.label}
            </div>
            <div
              className="mt-1 text-2xl font-semibold tabular-nums"
              style={{ color: t.tone }}
            >
              {typeof t.value === "number" ? t.value : t.value}
            </div>
          </div>
        ))}
      </div>
      <div className="flex flex-col gap-1.5">
        <div className="text-[10px] uppercase tracking-widest text-slate-500">
          Verdict distribution ({p.targets} targets)
        </div>
        <div className="flex h-3 overflow-hidden rounded-full bg-white/5">
          {ladder.map((v) => {
            const n = p.verdict_hist[v] ?? 0;
            if (n === 0) return null;
            return (
              <div
                key={v}
                title={`${v}: ${n}`}
                style={{
                  width: `${(n / totalTargets) * 100}%`,
                  background: VERDICT_ACCENT[v],
                }}
              />
            );
          })}
        </div>
        <div className="mt-1 flex flex-wrap gap-2 text-[10px] text-slate-400">
          {ladder.map((v) => (
            <span key={v} className="inline-flex items-center gap-1.5">
              <span
                className="inline-block h-2 w-2 rounded-full"
                style={{ background: VERDICT_ACCENT[v] }}
              />
              {v.replace(/_/g, " ")} · {p.verdict_hist[v] ?? 0}
            </span>
          ))}
        </div>
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Target picker
// ---------------------------------------------------------------------------

function TargetPicker({
  reports,
  filtered,
  selected,
  onSelect,
  query,
  onQuery,
  verdictFilter,
  onVerdictFilter,
}: {
  reports: NexusTargetReport[];
  filtered: NexusTargetReport[];
  selected: string | null;
  onSelect: (id: string) => void;
  query: string;
  onQuery: (v: string) => void;
  verdictFilter: NexusVerdictCode | "all";
  onVerdictFilter: (v: NexusVerdictCode | "all") => void;
}) {
  const counts: Record<string, number> = {};
  for (const r of reports) counts[r.verdict.code] = (counts[r.verdict.code] ?? 0) + 1;
  const filters: (NexusVerdictCode | "all")[] = [
    "all",
    "blocked_by_sanctions",
    "sanctions_exposed",
    "pep_edd_required",
    "opaque_structure",
    "transparent_structure",
  ];
  return (
    <section className="grid gap-3 rounded-2xl border border-white/10 bg-slate-950/60 p-5">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-sm font-semibold uppercase tracking-widest text-slate-300">
          Targets ({filtered.length})
        </h2>
        <input
          value={query}
          onChange={(e) => onQuery(e.target.value)}
          placeholder="Search name / jurisdiction / id"
          className="flex-1 min-w-[220px] rounded-lg border border-white/10 bg-black/30 px-3 py-1.5 text-xs text-slate-100 placeholder:text-slate-500 focus:border-cyan-300/60 focus:outline-none"
        />
      </div>
      <div className="flex flex-wrap gap-1.5 text-[10px]">
        {filters.map((f) => {
          const active = verdictFilter === f;
          const label = f === "all" ? "All" : f.replace(/_/g, " ");
          const count = f === "all" ? reports.length : counts[f] ?? 0;
          const tone = f === "all" ? "#67e8f9" : VERDICT_ACCENT[f];
          return (
            <button
              key={f}
              onClick={() => onVerdictFilter(f)}
              className="rounded-full border px-2.5 py-1 uppercase tracking-wider transition"
              style={{
                borderColor: active ? tone : `${tone}55`,
                background: active ? `${tone}22` : "transparent",
                color: active ? tone : `${tone}dd`,
              }}
            >
              {label} · {count}
            </button>
          );
        })}
      </div>
      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {filtered.map((r) => {
          const tone = VERDICT_ACCENT[r.verdict.code];
          const isActive = selected === r.target.id;
          return (
            <button
              key={r.target.id}
              onClick={() => onSelect(r.target.id)}
              className="group flex flex-col gap-1 rounded-xl border p-3 text-left transition"
              style={{
                borderColor: isActive ? tone : "rgba(148,163,184,0.15)",
                background: isActive ? `${tone}12` : "rgba(0,0,0,0.28)",
                boxShadow: isActive ? `inset 0 0 0 1px ${tone}55` : "none",
              }}
            >
              <div className="flex items-center justify-between text-[10px] uppercase tracking-wider">
                <span className="text-slate-400">{r.target.id}</span>
                <span style={{ color: tone }}>
                  opacity {r.opacity.score}
                </span>
              </div>
              <div className="text-sm font-semibold text-white">
                {r.target.name}
              </div>
              <div className="flex flex-wrap items-center gap-1.5 text-[10px] text-slate-400">
                <span>{KIND_LABEL[r.target.kind] ?? r.target.kind}</span>
                <span>·</span>
                <span>{r.target.jurisdiction || "—"}</span>
                <span>·</span>
                <span>{r.ubos.length} UBO(s)</span>
                {r.sanctions.aggregate > 0 ? (
                  <span
                    className="ml-1 rounded-full px-1.5 py-0.5 text-[9px]"
                    style={{
                      background: `${VERDICT_ACCENT.sanctions_exposed}22`,
                      color: VERDICT_ACCENT.sanctions_exposed,
                    }}
                  >
                    SDN {fmtPct(r.sanctions.aggregate, 0)}
                  </span>
                ) : null}
                {r.pep.count ? (
                  <span
                    className="ml-1 rounded-full px-1.5 py-0.5 text-[9px]"
                    style={{
                      background: `${VERDICT_ACCENT.pep_edd_required}22`,
                      color: VERDICT_ACCENT.pep_edd_required,
                    }}
                  >
                    PEP
                  </span>
                ) : null}
              </div>
            </button>
          );
        })}
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Ownership chain — the flagship SVG.  Radial layout: target at the
// bottom-centre; each controller at an angle, all paths overlaid; nodes
// on intermediate holdings appear on the path lines.
// ---------------------------------------------------------------------------

type ChainNode = {
  id: string;
  label: string;
  depth: number;
  x: number;
  y: number;
  isRoot: boolean;
  isTarget: boolean;
  sanctioned: boolean;
  pep: boolean;
  kind?: string;
  jurisdiction?: string;
};

function buildChainLayout(
  report: NexusTargetReport,
): { nodes: Map<string, ChainNode>; paths: NexusPath[] } {
  const nodes = new Map<string, ChainNode>();
  const W = 920;
  const H = 420;
  const cx = W / 2;
  const cy = H - 60;
  nodes.set(report.target.id, {
    id: report.target.id,
    label: report.target.name,
    depth: 0,
    x: cx,
    y: cy,
    isRoot: false,
    isTarget: true,
    sanctioned: false,
    pep: false,
    kind: report.target.kind,
    jurisdiction: report.target.jurisdiction,
  });
  const paths: NexusPath[] = [];
  const seenPath = new Set<string>();
  for (const c of report.controllers) {
    for (const p of c.paths) {
      const key = p.chain.join("→");
      if (seenPath.has(key)) continue;
      seenPath.add(key);
      paths.push(p);
    }
  }
  paths.sort((a, b) => b.weight - a.weight);
  const trimmed = paths.slice(0, 24);
  const maxDepth = trimmed.reduce((m, p) => Math.max(m, p.depth), 1);
  const perLevel = Math.max(120, (H - 120) / Math.max(1, maxDepth));

  // For each controller (root), assign an X coord — spread across the
  // top by weight.  Then interpolate intermediate nodes.
  const rootOrder: string[] = [];
  const rootMeta = new Map<string, NexusController>();
  for (const c of report.controllers) {
    rootOrder.push(c.root);
    rootMeta.set(c.root, c);
  }
  const totalRoots = Math.max(1, rootOrder.length);
  rootOrder.forEach((rid, i) => {
    // spread across the top width with a small margin
    const t = totalRoots === 1 ? 0.5 : i / (totalRoots - 1);
    const marginX = 90;
    const rx = marginX + t * (W - 2 * marginX);
    const ry = 40;
    const meta = rootMeta.get(rid)!;
    nodes.set(rid, {
      id: rid,
      label: meta.name ?? rid,
      depth: 999,
      x: rx,
      y: ry,
      isRoot: true,
      isTarget: false,
      sanctioned: !!meta.sanctioned,
      pep: !!meta.pep,
      kind: meta.kind,
      jurisdiction: meta.jurisdiction,
    });
  });

  // Intermediate nodes: for every non-endpoint node in a top path,
  // place it at a level = depth-from-target * perLevel; x interpolated
  // between root and target.
  for (const p of trimmed) {
    const chain = p.chain;
    if (chain.length <= 2) continue;
    const root = nodes.get(chain[0]);
    const target = nodes.get(report.target.id);
    if (!root || !target) continue;
    for (let i = 1; i < chain.length - 1; i++) {
      const id = chain[i];
      if (nodes.has(id)) continue;
      const t = i / (chain.length - 1);
      const x = root.x + (target.x - root.x) * t;
      const y = root.y + (target.y - root.y) * t;
      nodes.set(id, {
        id,
        label: id,
        depth: chain.length - 1 - i,
        x,
        y,
        isRoot: false,
        isTarget: false,
        sanctioned: false,
        pep: false,
      });
    }
  }

  return { nodes, paths: trimmed };
}

function OwnershipChain({
  report,
  loading,
  onSelectController,
}: {
  report: NexusTargetReport;
  loading: boolean;
  onSelectController: (id: string) => void;
}) {
  const { nodes, paths } = useMemo(() => buildChainLayout(report), [report]);
  const W = 920;
  const H = 420;

  const maxWeight = paths.reduce((m, p) => Math.max(m, p.weight), 0.001);

  return (
    <section className="grid gap-4 rounded-3xl border border-white/10 bg-slate-950/60 p-6">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <div className="flex items-baseline gap-3">
          <h2 className="text-sm font-semibold uppercase tracking-widest text-slate-300">
            Ownership chain
          </h2>
          <span className="text-[10px] uppercase tracking-widest text-slate-500">
            {report.path_count} paths · click a controller to see its
            downstream reach
          </span>
        </div>
        <div className="flex items-center gap-3 text-[10px] text-slate-400">
          <LegendDot color="#f43f5e" label="Sanctioned path" />
          <LegendDot color="#fbbf24" label="PEP path" />
          <LegendDot color="#67e8f9" label="Clean path" />
        </div>
      </div>
      <div className="relative overflow-hidden rounded-2xl border border-white/5 bg-slate-950/80">
        {loading ? (
          <div className="absolute inset-0 flex items-center justify-center text-xs text-slate-500">
            loading entity…
          </div>
        ) : null}
        <svg
          viewBox={`0 0 ${W} ${H}`}
          className="block h-auto w-full"
          preserveAspectRatio="xMidYMid meet"
        >
          <defs>
            <linearGradient id="nex-clean" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#67e8f9" stopOpacity="0.85" />
              <stop offset="100%" stopColor="#22d3a8" stopOpacity="0.55" />
            </linearGradient>
            <linearGradient id="nex-sdn" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#f43f5e" stopOpacity="0.9" />
              <stop offset="100%" stopColor="#fb7185" stopOpacity="0.6" />
            </linearGradient>
            <linearGradient id="nex-pep" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#fbbf24" stopOpacity="0.85" />
              <stop offset="100%" stopColor="#f472b6" stopOpacity="0.6" />
            </linearGradient>
            <radialGradient id="nex-node-target" cx="50%" cy="50%" r="50%">
              <stop offset="0%" stopColor="#0ea5e9" stopOpacity="0.9" />
              <stop offset="100%" stopColor="#155e75" stopOpacity="0.75" />
            </radialGradient>
          </defs>

          {/* Paths (drawn first so nodes sit on top). */}
          {paths.map((p, i) => {
            const controller = report.controllers.find(
              (c) => c.root === p.root,
            );
            const isSanctioned = !!controller?.sanctioned;
            const isPep = !!controller?.pep;
            const grad = isSanctioned
              ? "url(#nex-sdn)"
              : isPep
              ? "url(#nex-pep)"
              : "url(#nex-clean)";
            const pts = p.chain
              .map((id) => nodes.get(id))
              .filter((n): n is ChainNode => !!n);
            if (pts.length < 2) return null;
            const d = pts
              .map((n, j) => {
                if (j === 0) return `M ${n.x.toFixed(1)} ${n.y.toFixed(1)}`;
                const prev = pts[j - 1];
                const midX = (prev.x + n.x) / 2;
                const midY = (prev.y + n.y) / 2 + 12;
                return `Q ${midX.toFixed(1)} ${midY.toFixed(1)} ${n.x.toFixed(1)} ${n.y.toFixed(1)}`;
              })
              .join(" ");
            const width = 1.5 + (p.weight / maxWeight) * 6.5;
            return (
              <g key={i}>
                <path
                  d={d}
                  fill="none"
                  stroke={grad}
                  strokeWidth={width}
                  strokeLinecap="round"
                  opacity={0.85}
                />
                {/* Weight badge near midpoint */}
                {p.chain.length >= 2 ? (
                  <text
                    x={(pts[0].x + pts[pts.length - 1].x) / 2}
                    y={(pts[0].y + pts[pts.length - 1].y) / 2}
                    textAnchor="middle"
                    fontSize={10}
                    fill="rgba(148,163,184,0.7)"
                    style={{ pointerEvents: "none" }}
                  >
                    {fmtPct(p.weight, 1)}
                  </text>
                ) : null}
              </g>
            );
          })}

          {/* Nodes */}
          {Array.from(nodes.values()).map((n) => {
            const r = n.isTarget ? 26 : n.isRoot ? 20 : 8;
            const fill = n.isTarget
              ? "url(#nex-node-target)"
              : n.sanctioned
              ? "#f43f5e"
              : n.pep
              ? "#fbbf24"
              : n.isRoot
              ? "#22d3a8"
              : "#334155";
            const stroke = n.isTarget
              ? "#0ea5e9"
              : n.sanctioned
              ? "#fecdd3"
              : n.pep
              ? "#fde68a"
              : "#94a3b8";
            const clickable = n.isRoot && (n.sanctioned || n.pep);
            return (
              <g
                key={n.id}
                style={{ cursor: clickable ? "pointer" : "default" }}
                onClick={() =>
                  clickable ? onSelectController(n.id) : undefined
                }
              >
                <circle
                  cx={n.x}
                  cy={n.y}
                  r={r}
                  fill={fill}
                  stroke={stroke}
                  strokeWidth={1.5}
                  opacity={n.isRoot || n.isTarget ? 0.95 : 0.65}
                />
                {n.isRoot || n.isTarget ? (
                  <>
                    <text
                      x={n.x}
                      y={n.isTarget ? n.y + 4 : n.y + 3}
                      textAnchor="middle"
                      fontSize={n.isTarget ? 12 : 10}
                      fill="#f1f5f9"
                      fontWeight={n.isTarget ? 600 : 500}
                    >
                      {KIND_SHAPE[n.kind ?? "corporation"] ?? "●"}
                    </text>
                    <text
                      x={n.x}
                      y={n.isTarget ? n.y + r + 16 : n.y - r - 6}
                      textAnchor="middle"
                      fontSize={11}
                      fill="#e2e8f0"
                    >
                      {n.label.length > 34
                        ? n.label.slice(0, 31) + "…"
                        : n.label}
                    </text>
                    {n.jurisdiction ? (
                      <text
                        x={n.x}
                        y={
                          n.isTarget
                            ? n.y + r + 28
                            : n.y - r - 18
                        }
                        textAnchor="middle"
                        fontSize={9}
                        fill="#94a3b8"
                      >
                        {n.jurisdiction}
                      </text>
                    ) : null}
                  </>
                ) : (
                  <text
                    x={n.x + 10}
                    y={n.y + 3}
                    fontSize={9}
                    fill="#94a3b8"
                  >
                    {n.id}
                  </text>
                )}
              </g>
            );
          })}
        </svg>
      </div>
    </section>
  );
}

function LegendDot({ color, label }: { color: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span
        className="inline-block h-2 w-2 rounded-full"
        style={{ background: color }}
      />
      {label}
    </span>
  );
}

// ---------------------------------------------------------------------------
// UBO panel
// ---------------------------------------------------------------------------

function UboPanel({
  report,
  rules,
}: {
  report: NexusTargetReport;
  rules: NexusRules;
}) {
  const controllers = report.controllers;
  return (
    <section className="grid gap-3 rounded-2xl border border-white/10 bg-slate-950/60 p-5">
      <div className="flex items-baseline justify-between gap-3">
        <h2 className="text-sm font-semibold uppercase tracking-widest text-slate-300">
          Controllers ({controllers.length})
        </h2>
        <a
          href={nexusExportUrl(report.target.id)}
          className="text-[10px] uppercase tracking-widest text-cyan-300/80 hover:text-cyan-300"
          target="_blank"
          rel="noreferrer"
        >
          Download memo ↗
        </a>
      </div>
      <p className="text-[11px] text-slate-500">
        FinCEN CTA threshold {fmtPct(rules.thresholds.ubo, 0)} · Screening
        floor {fmtPct(rules.thresholds.ubo_screen, 0)} · Substantial-control
        override always upgrades to UBO.
      </p>
      <div className="grid gap-2">
        {controllers.length === 0 ? (
          <div className="rounded-lg border border-purple-400/30 bg-purple-400/5 p-4 text-xs text-purple-200">
            No controller edges found for this entity.
          </div>
        ) : (
          controllers.map((c) => {
            const uboCode = c.ubo?.code ?? "de_minimis";
            const uboTone =
              uboCode === "beneficial_owner"
                ? "#22d3a8"
                : uboCode === "screening_required"
                ? "#fbbf24"
                : uboCode === "corporate_owner"
                ? "#67e8f9"
                : "#64748b";
            const barPct = Math.max(1, Math.min(100, c.aggregate * 100));
            const ubothresh = rules.thresholds.ubo * 100;
            return (
              <div
                key={c.root}
                className="rounded-xl border border-white/10 bg-black/25 p-3"
              >
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <div className="flex items-baseline gap-2">
                    <span className="text-sm font-semibold text-white">
                      {c.name ?? c.root}
                    </span>
                    <span className="text-[10px] uppercase tracking-wider text-slate-500">
                      {c.root} · {KIND_LABEL[c.kind ?? ""] ?? c.kind} ·{" "}
                      {c.jurisdiction || "—"}
                    </span>
                  </div>
                  <span
                    className="rounded-full px-2 py-0.5 text-[10px] uppercase tracking-wider"
                    style={{
                      background: `${uboTone}22`,
                      color: uboTone,
                      boxShadow: `inset 0 0 0 1px ${uboTone}44`,
                    }}
                  >
                    {UBO_LABEL[uboCode]}
                  </span>
                </div>
                <div className="mt-2 flex items-center gap-3">
                  <div className="relative h-2 flex-1 overflow-hidden rounded-full bg-white/5">
                    <div
                      className="absolute inset-y-0 left-0"
                      style={{ width: `${barPct}%`, background: uboTone }}
                    />
                    <div
                      className="absolute inset-y-0 w-px bg-white/50"
                      style={{ left: `${ubothresh}%` }}
                    />
                  </div>
                  <span
                    className="min-w-[64px] text-right text-sm font-semibold tabular-nums"
                    style={{ color: uboTone }}
                  >
                    {fmtPct(c.aggregate, 1)}
                  </span>
                </div>
                <div className="mt-1.5 flex flex-wrap items-center gap-2 text-[10px] text-slate-400">
                  <span>{c.path_count} path(s)</span>
                  <span>·</span>
                  <span>shortest depth {c.shortest_depth}</span>
                  {c.sanctioned ? (
                    <span
                      className="rounded-full px-1.5 py-0.5"
                      style={{
                        background: `${VERDICT_ACCENT.sanctions_exposed}22`,
                        color: VERDICT_ACCENT.sanctions_exposed,
                      }}
                    >
                      SDN{c.sanctions_list ? ` · ${c.sanctions_list}` : ""}
                    </span>
                  ) : null}
                  {c.pep ? (
                    <span
                      className="rounded-full px-1.5 py-0.5"
                      style={{
                        background: `${VERDICT_ACCENT.pep_edd_required}22`,
                        color: VERDICT_ACCENT.pep_edd_required,
                      }}
                    >
                      PEP{c.pep_position ? ` · ${c.pep_position}` : ""}
                    </span>
                  ) : null}
                  {c.substantial_control ? (
                    <span
                      className="rounded-full px-1.5 py-0.5"
                      style={{
                        background: "rgba(103,232,249,0.15)",
                        color: "#67e8f9",
                      }}
                    >
                      Substantial control
                    </span>
                  ) : null}
                  {c.role ? (
                    <span className="text-slate-500">· {c.role}</span>
                  ) : null}
                </div>
                {c.ubo?.reason ? (
                  <div className="mt-1 text-[11px] text-slate-500">
                    {c.ubo.reason}
                  </div>
                ) : null}
              </div>
            );
          })
        )}
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Sanctions + PEP reach panel
// ---------------------------------------------------------------------------

function SanctionsPepPanel({
  report,
  rules,
}: {
  report: NexusTargetReport;
  rules: NexusRules;
}) {
  const s = report.sanctions;
  const p = report.pep;
  const sBar = Math.max(0, Math.min(1, s.aggregate));
  const pBar = Math.max(0, Math.min(1, p.max_aggregate));
  return (
    <section className="grid gap-3 rounded-2xl border border-white/10 bg-slate-950/60 p-5">
      <h2 className="text-sm font-semibold uppercase tracking-widest text-slate-300">
        Sanctioned / PEP nexus
      </h2>
      <div className="grid gap-4">
        <NexusMeter
          label="Sanctioned aggregate control"
          value={sBar}
          bandThresholds={[rules.thresholds.ofac_report, rules.thresholds.ofac_block]}
          bandColors={["#67e8f9", "#fb923c", "#f43f5e"]}
          bandLabels={["clean", "reportable", "blocked"]}
          verdict={s.verdict}
          verdictTone={
            s.verdict === "CLEAN"
              ? "#22d3a8"
              : s.verdict === "BLOCKED"
              ? "#f43f5e"
              : s.verdict === "REPORTABLE"
              ? "#fb923c"
              : "#a855f7"
          }
        />
        <div className="grid gap-2">
          {s.hits.length === 0 ? (
            <div className="rounded-lg border border-emerald-400/30 bg-emerald-400/5 p-3 text-xs text-emerald-200">
              No sanctioned controllers detected in any ownership path.
            </div>
          ) : (
            s.hits.map((h) => (
              <ReachRow
                key={h.root}
                title={h.name ?? h.root}
                sub={
                  `${h.root} · ${h.jurisdiction ?? "—"}` +
                  (h.sanctions_list ? ` · ${h.sanctions_list}` : "")
                }
                pct={h.aggregate}
                tone={REACH_TONE[h.reach_code]}
                code={h.reach_code}
                paths={h.path_count}
              />
            ))
          )}
        </div>
        <NexusMeter
          label="Max PEP aggregate control"
          value={pBar}
          bandThresholds={[rules.thresholds.pep_link, rules.thresholds.pep_edd]}
          bandColors={["#67e8f9", "#f472b6", "#fbbf24"]}
          bandLabels={["nexus", "linked", "EDD required"]}
          verdict={p.count ? `${p.count} controller${p.count === 1 ? "" : "s"}` : "CLEAN"}
          verdictTone={
            p.count === 0
              ? "#22d3a8"
              : p.max_aggregate >= rules.thresholds.pep_edd
              ? "#fbbf24"
              : "#f472b6"
          }
        />
        <div className="grid gap-2">
          {p.hits.length === 0 ? (
            <div className="rounded-lg border border-emerald-400/30 bg-emerald-400/5 p-3 text-xs text-emerald-200">
              No PEP nexus detected.
            </div>
          ) : (
            p.hits.map((h) => (
              <ReachRow
                key={h.root}
                title={h.name ?? h.root}
                sub={
                  `${h.root} · ${h.jurisdiction ?? "—"}` +
                  (h.pep_position ? ` · ${h.pep_position}` : "")
                }
                pct={h.aggregate}
                tone={REACH_TONE[h.reach_code]}
                code={h.reach_code}
                paths={h.path_count}
              />
            ))
          )}
        </div>
      </div>
    </section>
  );
}

function NexusMeter({
  label,
  value,
  bandThresholds,
  bandColors,
  bandLabels,
  verdict,
  verdictTone,
}: {
  label: string;
  value: number;
  bandThresholds: number[];
  bandColors: string[];
  bandLabels: string[];
  verdict: string;
  verdictTone: string;
}) {
  const stops = bandThresholds
    .map((t, i) => `${bandColors[i]} ${(bandThresholds[i - 1] ?? 0) * 100}% ${t * 100}%`)
    .concat(`${bandColors[bandColors.length - 1]} ${bandThresholds[bandThresholds.length - 1] * 100}% 100%`);
  const barBg = `linear-gradient(90deg, ${stops.join(", ")})`;
  return (
    <div>
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-[10px] uppercase tracking-widest text-slate-400">
          {label}
        </span>
        <span
          className="text-[10px] uppercase tracking-widest"
          style={{ color: verdictTone }}
        >
          {verdict}
        </span>
      </div>
      <div className="relative mt-1.5 h-3 overflow-hidden rounded-full bg-white/5">
        <div className="absolute inset-0 opacity-70" style={{ background: barBg }} />
        <div
          className="absolute inset-y-0 left-0 border-r-2 border-white/70 bg-white/10"
          style={{ width: `${Math.max(0.5, value * 100)}%` }}
        />
      </div>
      <div className="mt-1 flex justify-between text-[9px] text-slate-500">
        {bandThresholds.map((t, i) => (
          <span key={i}>
            {bandLabels[i]} ≥ {fmtPct(t, 0)}
          </span>
        ))}
        <span>{bandLabels[bandLabels.length - 1]}</span>
      </div>
    </div>
  );
}

function ReachRow({
  title,
  sub,
  pct,
  tone,
  code,
  paths,
}: {
  title: string;
  sub: string;
  pct: number;
  tone: string;
  code: string;
  paths: number;
}) {
  return (
    <div
      className="flex items-center gap-3 rounded-lg border px-3 py-2"
      style={{
        borderColor: `${tone}44`,
        background: `${tone}0f`,
      }}
    >
      <div className="flex-1">
        <div className="text-sm font-semibold text-white">{title}</div>
        <div className="text-[10px] text-slate-400">{sub}</div>
      </div>
      <div className="text-right">
        <div
          className="text-sm font-semibold tabular-nums"
          style={{ color: tone }}
        >
          {fmtPct(pct, 1)}
        </div>
        <div className="text-[9px] uppercase tracking-wider text-slate-500">
          {code} · {paths} path{paths === 1 ? "" : "s"}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Opacity breakdown
// ---------------------------------------------------------------------------

function OpacityBreakdown({
  report,
  rules,
}: {
  report: NexusTargetReport;
  rules: NexusRules;
}) {
  const comp = report.opacity.components;
  const rows = Object.entries(rules.opacity_weights).map(([k, w]) => ({
    key: k,
    weight: w,
    value: comp[k as keyof typeof comp] ?? 0,
    contribution: (comp[k as keyof typeof comp] ?? 0) * w * 100,
  }));
  const total = rows.reduce((s, r) => s + r.contribution, 0);
  return (
    <section className="grid gap-3 rounded-2xl border border-white/10 bg-slate-950/60 p-5">
      <div className="flex items-baseline justify-between gap-3">
        <h2 className="text-sm font-semibold uppercase tracking-widest text-slate-300">
          Opacity breakdown ({report.opacity.score})
        </h2>
        <span
          className="rounded-full px-2 py-0.5 text-[10px] uppercase tracking-widest"
          style={{
            background: `${OPACITY_BAND_TONE[report.opacity.band]}22`,
            color: OPACITY_BAND_TONE[report.opacity.band],
          }}
        >
          {report.opacity.band}
        </span>
      </div>
      <div className="grid gap-1.5">
        {rows.map((r) => {
          const pct = Math.max(1, Math.min(100, r.contribution / Math.max(1, total) * 100));
          const rawPct = Math.max(1, Math.min(100, r.value * 100));
          return (
            <div key={r.key} className="grid gap-1">
              <div className="flex items-center justify-between text-[10px] text-slate-400">
                <span>{OPACITY_COMPONENT_LABEL[r.key] ?? r.key}</span>
                <span className="tabular-nums text-slate-500">
                  raw {r.value.toFixed(2)} · weight {r.weight.toFixed(2)} · contribution {r.contribution.toFixed(1)}
                </span>
              </div>
              <div className="relative h-2 overflow-hidden rounded-full bg-white/5">
                <div
                  className="absolute inset-y-0 left-0 bg-white/10"
                  style={{ width: `${rawPct}%` }}
                />
                <div
                  className="absolute inset-y-0 left-0"
                  style={{ width: `${pct}%`, background: OPACITY_BAND_TONE[report.opacity.band] }}
                />
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Ownership paths table
// ---------------------------------------------------------------------------

function OwnershipPathsTable({ report }: { report: NexusTargetReport }) {
  const rows: (NexusPath & { controllerName?: string; sanctioned?: boolean; pep?: boolean })[] = [];
  for (const c of report.controllers) {
    for (const p of c.paths) {
      rows.push({
        ...p,
        controllerName: c.name,
        sanctioned: c.sanctioned,
        pep: c.pep,
      });
    }
  }
  rows.sort((a, b) => b.weight - a.weight);
  const trimmed = rows.slice(0, 10);
  return (
    <section className="grid gap-3 rounded-2xl border border-white/10 bg-slate-950/60 p-5">
      <h2 className="text-sm font-semibold uppercase tracking-widest text-slate-300">
        Ownership paths (top 10)
      </h2>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[720px] text-left text-xs">
          <thead className="text-[10px] uppercase tracking-wider text-slate-500">
            <tr>
              <th className="py-2 pr-2">#</th>
              <th className="py-2 pr-2">Controller</th>
              <th className="py-2 pr-2">Chain</th>
              <th className="py-2 pr-2 text-right">Depth</th>
              <th className="py-2 pr-2 text-right">Cumulative</th>
            </tr>
          </thead>
          <tbody>
            {trimmed.map((r, i) => {
              const tone = r.sanctioned
                ? VERDICT_ACCENT.sanctions_exposed
                : r.pep
                ? VERDICT_ACCENT.pep_edd_required
                : "#67e8f9";
              return (
                <tr
                  key={`${r.root}-${i}`}
                  className="border-t border-white/5"
                  style={{
                    background: (r.sanctioned || r.pep) ? `${tone}08` : "transparent",
                  }}
                >
                  <td className="py-2 pr-2 text-slate-500">{i + 1}</td>
                  <td className="py-2 pr-2 text-white">{r.controllerName ?? r.root}</td>
                  <td className="py-2 pr-2 text-slate-300">
                    {r.chain.map((c, j) => (
                      <span key={c}>
                        <span className="rounded bg-white/5 px-1.5 py-0.5">{c}</span>
                        {j < r.chain.length - 1 ? (
                          <span className="mx-1 text-slate-500">→</span>
                        ) : null}
                      </span>
                    ))}
                    <span className="ml-2 text-[9px] text-slate-500">
                      {r.edges.map((e) => fmtPct(e.pct, 0)).join(" × ")}
                    </span>
                  </td>
                  <td className="py-2 pr-2 text-right text-slate-400 tabular-nums">
                    {r.depth}
                  </td>
                  <td
                    className="py-2 pr-2 text-right tabular-nums font-semibold"
                    style={{ color: tone }}
                  >
                    {fmtPct(r.weight, 2)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Reach section — pick a sanctioned/PEP root, see downstream reach.
// ---------------------------------------------------------------------------

function ReachSection({
  candidates,
  selected,
  onSelect,
  report,
  rules,
}: {
  candidates: NexusCandidate[];
  selected: string | null;
  onSelect: (id: string) => void;
  report: NexusReachReport | null;
  rules: NexusRules;
}) {
  return (
    <section className="grid gap-4 rounded-3xl border border-white/10 bg-slate-950/60 p-6">
      <div className="flex items-baseline justify-between gap-3">
        <h2 className="text-sm font-semibold uppercase tracking-widest text-slate-300">
          Downstream reach
        </h2>
        <span className="text-[10px] uppercase tracking-widest text-slate-500">
          Pick a controller — every target the aggregate rule blocks / reports
        </span>
      </div>
      <div className="flex flex-wrap gap-2">
        {candidates.map((c) => {
          const isActive = selected === c.id;
          const tone = c.sanctioned
            ? "#f43f5e"
            : c.pep
            ? "#fbbf24"
            : "#67e8f9";
          return (
            <button
              key={c.id}
              onClick={() => onSelect(c.id)}
              className="rounded-xl border px-3 py-1.5 text-left text-[11px] transition"
              style={{
                borderColor: isActive ? tone : `${tone}55`,
                background: isActive ? `${tone}18` : "transparent",
                color: isActive ? "white" : "#cbd5e1",
              }}
            >
              <span className="block font-semibold">{c.name}</span>
              <span className="mt-0.5 flex flex-wrap items-center gap-1 text-[9px] uppercase tracking-widest text-slate-500">
                {c.id}
                {c.sanctioned ? (
                  <span
                    className="rounded-full px-1.5 py-0.5"
                    style={{ background: "rgba(244,63,94,0.18)", color: "#fecdd3" }}
                  >
                    SDN
                  </span>
                ) : null}
                {c.pep ? (
                  <span
                    className="rounded-full px-1.5 py-0.5"
                    style={{ background: "rgba(251,191,36,0.18)", color: "#fde68a" }}
                  >
                    PEP
                  </span>
                ) : null}
                <span>· {c.child_count} child(ren)</span>
              </span>
            </button>
          );
        })}
      </div>
      {report ? <ReachViz report={report} rules={rules} /> : (
        <div className="rounded-xl border border-white/10 bg-black/25 p-6 text-center text-xs text-slate-500">
          Pick a controller above to see downstream reach.
        </div>
      )}
    </section>
  );
}

function ReachViz({ report, rules }: { report: NexusReachReport; rules: NexusRules }) {
  const W = 900;
  const H = 420;
  const cx = W / 2;
  const cy = H / 2;
  const rBase = 130;
  const rStep = 70;

  // Position each reach target on a ring by depth.
  const rows = report.reach.slice(0, 16);
  const perDepth: Record<number, number[]> = {};
  rows.forEach((r) => {
    (perDepth[r.shortest_depth] ??= []).push(0);
  });
  const depths = Object.keys(perDepth)
    .map((d) => parseInt(d, 10))
    .sort((a, b) => a - b);

  const positions = new Map<string, { x: number; y: number; r: number; ring: number }>();
  depths.forEach((d, ringIdx) => {
    const group = rows.filter((r) => r.shortest_depth === d);
    group.forEach((row, i) => {
      const angle = (Math.PI * 2 * (i + 0.5)) / group.length - Math.PI / 2;
      const ringR = rBase + ringIdx * rStep;
      positions.set(row.target, {
        x: cx + Math.cos(angle) * ringR,
        y: cy + Math.sin(angle) * ringR,
        r: 14 + Math.min(24, row.aggregate * 28),
        ring: ringIdx,
      });
    });
  });

  const rootTone = report.root.sanctioned
    ? "#f43f5e"
    : report.root.pep
    ? "#fbbf24"
    : "#67e8f9";

  return (
    <div className="grid gap-4 md:grid-cols-[minmax(0,3fr)_minmax(240px,2fr)]">
      <div className="relative overflow-hidden rounded-2xl border border-white/5 bg-slate-950/80">
        <svg
          viewBox={`0 0 ${W} ${H}`}
          className="block h-auto w-full"
          preserveAspectRatio="xMidYMid meet"
        >
          <defs>
            <radialGradient id="reach-root" cx="50%" cy="50%" r="50%">
              <stop offset="0%" stopColor={rootTone} stopOpacity="0.95" />
              <stop offset="100%" stopColor={rootTone} stopOpacity="0.55" />
            </radialGradient>
          </defs>

          {/* Ring guides */}
          {depths.map((_, i) => (
            <circle
              key={i}
              cx={cx}
              cy={cy}
              r={rBase + i * rStep}
              fill="none"
              stroke="rgba(148,163,184,0.12)"
              strokeDasharray="3 4"
            />
          ))}

          {/* Threshold rings — labelled bands */}
          {rules.thresholds.ofac_block ? (
            <>
              <circle
                cx={cx}
                cy={cy}
                r={rBase - 30}
                fill="none"
                stroke="rgba(244,63,94,0.30)"
                strokeDasharray="4 3"
              />
              <text
                x={cx}
                y={cy - (rBase - 30) - 6}
                textAnchor="middle"
                fill="#fda4af"
                fontSize={9}
              >
                50% OFAC block
              </text>
            </>
          ) : null}

          {/* Spokes from root to each target */}
          {rows.map((r) => {
            const p = positions.get(r.target);
            if (!p) return null;
            const tone =
              r.aggregate >= 0.5
                ? "#f43f5e"
                : r.aggregate >= 0.25
                ? "#fb923c"
                : "#a855f7";
            const width = 1.5 + Math.min(6, r.aggregate * 8);
            return (
              <line
                key={r.target}
                x1={cx}
                y1={cy}
                x2={p.x}
                y2={p.y}
                stroke={tone}
                strokeWidth={width}
                opacity={0.55}
              />
            );
          })}

          {/* Target nodes */}
          {rows.map((r) => {
            const p = positions.get(r.target);
            if (!p) return null;
            const tone =
              r.aggregate >= 0.5
                ? "#f43f5e"
                : r.aggregate >= 0.25
                ? "#fb923c"
                : "#a855f7";
            return (
              <g key={r.target}>
                <circle
                  cx={p.x}
                  cy={p.y}
                  r={p.r}
                  fill={`${tone}55`}
                  stroke={tone}
                  strokeWidth={1.6}
                />
                <text
                  x={p.x}
                  y={p.y + 3}
                  textAnchor="middle"
                  fontSize={11}
                  fill="#f1f5f9"
                  fontWeight={600}
                >
                  {fmtPct(r.aggregate, 0)}
                </text>
                <text
                  x={p.x}
                  y={p.y + p.r + 14}
                  textAnchor="middle"
                  fontSize={10}
                  fill="#cbd5e1"
                >
                  {(r.name ?? r.target).slice(0, 22)}
                </text>
              </g>
            );
          })}

          {/* Root */}
          <circle
            cx={cx}
            cy={cy}
            r={40}
            fill="url(#reach-root)"
            stroke={rootTone}
            strokeWidth={2}
          />
          <text
            x={cx}
            y={cy - 2}
            textAnchor="middle"
            fill="#f8fafc"
            fontSize={11}
            fontWeight={700}
          >
            {report.root.name.slice(0, 22)}
          </text>
          <text
            x={cx}
            y={cy + 14}
            textAnchor="middle"
            fill="#cbd5e1"
            fontSize={9}
          >
            {report.root.sanctioned
              ? report.root.sanctions_list ?? "Sanctioned"
              : report.root.pep
              ? report.root.pep_position ?? "PEP"
              : "Controller"}
          </text>
        </svg>
      </div>
      <div className="grid gap-2 text-xs">
        <div className="rounded-xl border border-white/10 bg-black/30 p-3">
          <div className="text-[10px] uppercase tracking-widest text-slate-500">
            {report.root_kind === "sanctioned"
              ? "OFAC reach"
              : report.root_kind === "pep"
              ? "PEP reach"
              : "Controller reach"}
          </div>
          <div className="mt-1 grid grid-cols-3 gap-2 text-center text-[11px]">
            <div>
              <div className="text-lg font-semibold text-rose-300 tabular-nums">
                {report.counts.blocked}
              </div>
              <div className="text-[10px] uppercase tracking-widest text-slate-500">
                blocked
              </div>
            </div>
            <div>
              <div className="text-lg font-semibold text-orange-300 tabular-nums">
                {report.counts.reportable}
              </div>
              <div className="text-[10px] uppercase tracking-widest text-slate-500">
                reportable
              </div>
            </div>
            <div>
              <div className="text-lg font-semibold text-purple-300 tabular-nums">
                {report.counts.exposed}
              </div>
              <div className="text-[10px] uppercase tracking-widest text-slate-500">
                exposed
              </div>
            </div>
          </div>
        </div>
        <div className="rounded-xl border border-white/10 bg-black/30 p-3">
          <div className="text-[10px] uppercase tracking-widest text-slate-500">
            Downstream targets ({report.reach.length})
          </div>
          <div className="mt-2 grid gap-1.5 text-[11px] text-slate-300">
            {report.reach.slice(0, 8).map((r) => {
              const tone =
                r.aggregate >= 0.5
                  ? "#f43f5e"
                  : r.aggregate >= 0.25
                  ? "#fb923c"
                  : "#a855f7";
              return (
                <div
                  key={r.target}
                  className="flex items-baseline justify-between gap-2 border-b border-white/5 pb-1 last:border-b-0"
                >
                  <span className="truncate">{r.name ?? r.target}</span>
                  <span
                    className="tabular-nums text-xs font-semibold"
                    style={{ color: tone }}
                  >
                    {fmtPct(r.aggregate, 1)}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Rules footer
// ---------------------------------------------------------------------------

function RulesFooter({
  rules,
  corpusHash,
}: {
  rules: NexusRules;
  corpusHash: string;
}) {
  return (
    <footer className="grid gap-3 rounded-2xl border border-white/10 bg-slate-950/60 p-5 text-[10px] uppercase tracking-widest text-slate-400">
      <div className="flex flex-wrap gap-2">
        {rules.verdict_ladder.map((v) => (
          <span
            key={v.code}
            className="rounded-full px-2.5 py-1"
            style={{
              background: `${VERDICT_ACCENT[v.code]}20`,
              color: VERDICT_ACCENT[v.code],
              boxShadow: `inset 0 0 0 1px ${VERDICT_ACCENT[v.code]}55`,
            }}
          >
            {v.label}
          </span>
        ))}
      </div>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span>{rules.engine}</span>
        <span>corpus hash · {corpusHash}</span>
        <span>
          UBO {fmtPct(rules.thresholds.ubo, 0)} · OFAC{" "}
          {fmtPct(rules.thresholds.ofac_block, 0)} · PEP{" "}
          {fmtPct(rules.thresholds.pep_edd, 0)}
        </span>
      </div>
    </footer>
  );
}

// ---------------------------------------------------------------------------
// Loading + error placeholders
// ---------------------------------------------------------------------------

function Loading() {
  return (
    <div className="mt-6 flex min-h-[400px] items-center justify-center rounded-3xl border border-white/10 bg-slate-950/60 text-xs uppercase tracking-widest text-slate-500">
      loading nexus…
    </div>
  );
}

function ErrorBanner({ message }: { message: string }) {
  return (
    <div className="mt-6 rounded-3xl border border-rose-400/40 bg-rose-500/10 p-6 text-sm text-rose-100">
      Failed to load: {message}
    </div>
  );
}
