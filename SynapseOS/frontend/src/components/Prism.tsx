"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import type {
  Community,
  GraphNode,
  PrismLensId,
  PrismLensResult,
  PrismLensSpec,
  PrismReport,
  PrismStance,
  PrismTargetKind,
} from "@/lib/types";

type Props = {
  open: boolean;
  onClose: () => void;
  /** Default target when the modal opens — the note the user is
   *  currently inspecting, if any. */
  seedNote?: GraphNode | null;
  /** Cluster list, for the cluster-target picker. */
  communities: Community[];
  /** Called when the user clicks a lens pick to jump to that note in
   *  the inspector. */
  onSelectNote?: (stub: GraphNode) => void;
  /** Called when the user clicks the composite Spark suggestion. Fires
   *  a Spark-like NoteDraft into the composer via the page-level
   *  composerDraft hook. */
  onDraftFromSpark?: (draft: { title: string; body: string; tags: string[] }) => void;
};

type TargetChoice =
  | { kind: "note"; id: number; label: string }
  | { kind: "cluster"; id: number; label: string; color: string }
  | { kind: "query"; text: string };

// --------------------------------------------------------------- palette
//
// Each lens carries a `color` string that maps to Tailwind's native
// palette. The frontend can't compose class names dynamically (Tailwind
// JIT strips unused strings), so we index a static class table. Every
// slot renders both a background wash and a stroke color for the lens
// header and pick rows.

const LENS_STYLE: Record<
  string,
  {
    tile: string;
    dot: string;
    ring: string;
    text: string;
    softText: string;
    gradient: string;
    strokeHex: string;
  }
> = {
  rose: {
    tile: "bg-rose-500/12 ring-rose-400/40",
    dot: "bg-rose-400",
    ring: "ring-rose-400/50",
    text: "text-rose-200",
    softText: "text-rose-300/80",
    gradient: "from-rose-500/30 via-rose-500/15 to-rose-500/5",
    strokeHex: "#fb7185",
  },
  sky: {
    tile: "bg-sky-500/12 ring-sky-400/40",
    dot: "bg-sky-400",
    ring: "ring-sky-400/50",
    text: "text-sky-200",
    softText: "text-sky-300/80",
    gradient: "from-sky-500/30 via-sky-500/15 to-sky-500/5",
    strokeHex: "#38bdf8",
  },
  amber: {
    tile: "bg-amber-500/12 ring-amber-400/40",
    dot: "bg-amber-400",
    ring: "ring-amber-400/50",
    text: "text-amber-200",
    softText: "text-amber-300/80",
    gradient: "from-amber-500/30 via-amber-500/15 to-amber-500/5",
    strokeHex: "#fbbf24",
  },
  violet: {
    tile: "bg-violet-500/12 ring-violet-400/40",
    dot: "bg-violet-400",
    ring: "ring-violet-400/50",
    text: "text-violet-200",
    softText: "text-violet-300/80",
    gradient: "from-violet-500/30 via-violet-500/15 to-violet-500/5",
    strokeHex: "#a78bfa",
  },
  emerald: {
    tile: "bg-emerald-500/12 ring-emerald-400/40",
    dot: "bg-emerald-400",
    ring: "ring-emerald-400/50",
    text: "text-emerald-200",
    softText: "text-emerald-300/80",
    gradient: "from-emerald-500/30 via-emerald-500/15 to-emerald-500/5",
    strokeHex: "#34d399",
  },
  fuchsia: {
    tile: "bg-fuchsia-500/12 ring-fuchsia-400/40",
    dot: "bg-fuchsia-400",
    ring: "ring-fuchsia-400/50",
    text: "text-fuchsia-200",
    softText: "text-fuchsia-300/80",
    gradient: "from-fuchsia-500/30 via-fuchsia-500/15 to-fuchsia-500/5",
    strokeHex: "#e879f9",
  },
  cyan: {
    tile: "bg-cyan-500/12 ring-cyan-400/40",
    dot: "bg-cyan-400",
    ring: "ring-cyan-400/50",
    text: "text-cyan-200",
    softText: "text-cyan-300/80",
    gradient: "from-cyan-500/30 via-cyan-500/15 to-cyan-500/5",
    strokeHex: "#22d3ee",
  },
  lime: {
    tile: "bg-lime-500/12 ring-lime-400/40",
    dot: "bg-lime-400",
    ring: "ring-lime-400/50",
    text: "text-lime-200",
    softText: "text-lime-300/80",
    gradient: "from-lime-500/30 via-lime-500/15 to-lime-500/5",
    strokeHex: "#a3e635",
  },
};

const STANCE_STYLE: Record<PrismStance, { label: string; chip: string }> = {
  reinforce: {
    label: "reinforces",
    chip: "bg-emerald-500/15 ring-emerald-400/40 text-emerald-200",
  },
  challenge: {
    label: "challenges",
    chip: "bg-rose-500/15 ring-rose-400/40 text-rose-200",
  },
  neutral: {
    label: "grazes",
    chip: "bg-sky-500/12 ring-sky-400/35 text-sky-200",
  },
  thin: {
    label: "thin",
    chip: "bg-white/[0.03] ring-white/10 text-ink-300",
  },
};

const FAMILY_LABEL: Record<string, string> = {
  critical: "critical",
  empirical: "empirical",
  narrative: "narrative",
  generative: "generative",
};

/**
 * Prism — perspective explorer.
 *
 * You pin a target (the currently-selected note, a cluster centroid, or
 * an ad-hoc query) and Prism re-projects the entire vault through eight
 * canonical perspectives: skeptic, empiricist, historian, futurist,
 * practitioner, contrarian, systems, first-principles. Each lens returns
 * its top-K supporting notes ranked by
 *     score = cosine(target) × (1 + λ · lens-lexicon-density) × recency
 * with a diversification pass so the same note doesn't top-out every
 * lens. A per-lens coverage number (0..1) tells you where your vault
 * has depth on this target and where it has a hole; the weakest lens
 * turns into a Spark-shaped writing prompt you can fire straight into
 * the composer.
 *
 * The panel is *diagnostic*, not editorial — it doesn't produce prose
 * for you; it shows you the shape of your own thinking, one perspective
 * at a time.
 */
export function Prism({
  open,
  onClose,
  seedNote,
  communities,
  onSelectNote,
  onDraftFromSpark,
}: Props) {
  const [lensSpecs, setLensSpecs] = useState<PrismLensSpec[] | null>(null);
  const [report, setReport] = useState<PrismReport | null>(null);
  const [target, setTarget] = useState<TargetChoice | null>(null);
  const [queryDraft, setQueryDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [topK, setTopK] = useState(3);
  const [floor, setFloor] = useState(0.16);
  const [copyFlash, setCopyFlash] = useState<string | null>(null);
  const [mdBusy, setMdBusy] = useState(false);

  // First-time modal-open bootstraps the lens catalog + picks the seed
  // note as the default target when there is one.
  useEffect(() => {
    if (!open) return;
    if (lensSpecs === null) {
      api.prismLenses().then(setLensSpecs).catch(() => setLensSpecs([]));
    }
    setTarget((prev) => {
      if (prev) return prev;
      if (seedNote) {
        return { kind: "note", id: seedNote.id, label: seedNote.title };
      }
      if (communities.length > 0) {
        return {
          kind: "cluster",
          id: communities[0].id,
          label: communities[0].name,
          color: communities[0].color,
        };
      }
      return null;
    });
  }, [open, lensSpecs, seedNote, communities]);

  // Whenever the target OR knobs change, refetch the report. Kept as one
  // effect so a rapid re-target doesn't leave a stale report in view.
  useEffect(() => {
    if (!open) return;
    if (!target) return;
    let cancelled = false;
    setBusy(true);
    setError(null);
    const payload =
      target.kind === "query"
        ? { target_kind: "query" as const, query: target.text, top_k_per_lens: topK, floor_sim: floor }
        : {
            target_kind: target.kind,
            target_id: target.id,
            top_k_per_lens: topK,
            floor_sim: floor,
          };
    api
      .prismCompute(payload)
      .then((r) => {
        if (!cancelled) setReport(r);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : "compute failed");
      })
      .finally(() => {
        if (!cancelled) setBusy(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, target, topK, floor]);

  // Reset transient state on close so a re-open lands on the current
  // selection, not a stale one.
  useEffect(() => {
    if (open) return;
    setCopyFlash(null);
    setError(null);
  }, [open]);

  // Esc closes.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  const submitQuery = useCallback(() => {
    const q = queryDraft.trim();
    if (!q) return;
    setTarget({ kind: "query", text: q });
  }, [queryDraft]);

  const handlePickClick = useCallback(
    (nid: number, title: string) => {
      if (!onSelectNote) return;
      onSelectNote({
        id: nid,
        title,
        body: "",
        tags: [],
        degree: 0,
        weight: 0,
      });
    },
    [onSelectNote],
  );

  const copyMarkdown = useCallback(async () => {
    if (!target) return;
    setMdBusy(true);
    try {
      const payload =
        target.kind === "query"
          ? { target_kind: "query" as const, query: target.text, top_k_per_lens: topK, floor_sim: floor }
          : {
              target_kind: target.kind,
              target_id: target.id,
              top_k_per_lens: topK,
              floor_sim: floor,
            };
      const md = await api.prismExportMd(payload);
      await navigator.clipboard.writeText(md);
      setCopyFlash("copied markdown to clipboard");
      window.setTimeout(() => setCopyFlash(null), 2200);
    } catch (e) {
      setCopyFlash(e instanceof Error ? e.message : "copy failed");
      window.setTimeout(() => setCopyFlash(null), 3000);
    } finally {
      setMdBusy(false);
    }
  }, [target, topK, floor]);

  const composite = useMemo(() => {
    if (!report) return null;
    const strong = report.lenses.find((l) => l.id === report.strongest_lens);
    const weak = report.lenses.find((l) => l.id === report.weakest_lens);
    return { strong, weak };
  }, [report]);

  const useSparkAsDraft = useCallback(() => {
    if (!report?.spark_suggestion || !report?.weakest_lens) return;
    const lens = report.lenses.find((l) => l.id === report.weakest_lens);
    if (!lens) return;
    const title = `${report.target.label} — through the ${lens.label} lens`;
    const body = `${report.spark_suggestion}\n\n(Prism weakest lens: ${lens.label} — coverage ${lens.coverage.toFixed(2)}. This draft fills the gap.)`;
    const tags = ["prism", lens.id.replace("_", "-")];
    onDraftFromSpark?.({ title, body, tags });
    setCopyFlash("draft sent to composer");
    window.setTimeout(() => setCopyFlash(null), 2200);
  }, [report, onDraftFromSpark]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/70 backdrop-blur-sm p-6">
      <div className="relative w-full max-w-6xl my-4 rounded-2xl bg-gradient-to-br from-ink-800/95 via-ink-800/90 to-ink-900/95 ring-1 ring-white/10 shadow-2xl overflow-hidden">
        <div
          className="absolute inset-0 pointer-events-none opacity-40"
          style={{
            background:
              "radial-gradient(600px 260px at 12% 0%, rgba(244,114,182,0.10), transparent 60%), radial-gradient(700px 300px at 90% 20%, rgba(34,211,238,0.10), transparent 65%), radial-gradient(600px 260px at 55% 100%, rgba(163,230,53,0.08), transparent 60%)",
          }}
        />

        {/* -------- header -------- */}
        <div className="relative flex items-center justify-between px-6 pt-6 pb-4 border-b border-white/5">
          <div className="flex items-center gap-3">
            <div
              className="w-9 h-9 rounded-lg bg-gradient-to-br from-rose-500/25 via-violet-500/25 to-cyan-500/25 ring-1 ring-white/10 flex items-center justify-center text-lg"
              aria-hidden
            >
              🔷
            </div>
            <div>
              <div className="text-base font-semibold text-ink-100">Prism</div>
              <div className="text-[11px] text-ink-300 uppercase tracking-[0.18em]">
                8 perspectives · one idea
              </div>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <button
              onClick={copyMarkdown}
              disabled={!target || mdBusy}
              className="text-[11px] font-mono uppercase tracking-[0.14em] px-3 py-1.5 rounded-full bg-white/[0.03] ring-1 ring-white/10 text-ink-200 hover:text-ink-100 hover:ring-white/25 disabled:opacity-40"
              title="Copy a Markdown reading brief of this Prism to the clipboard"
            >
              {mdBusy ? "…" : "copy .md"}
            </button>
            <button
              onClick={onClose}
              className="text-ink-300 hover:text-ink-100 text-xl leading-none px-2"
              aria-label="close prism"
            >
              ✕
            </button>
          </div>
        </div>

        {/* -------- target picker -------- */}
        <div className="relative px-6 pt-4 pb-3 border-b border-white/5">
          <TargetPicker
            target={target}
            seedNote={seedNote}
            communities={communities}
            onPickNote={() => {
              if (seedNote) {
                setTarget({ kind: "note", id: seedNote.id, label: seedNote.title });
              }
            }}
            onPickCluster={(c) =>
              setTarget({ kind: "cluster", id: c.id, label: c.name, color: c.color })
            }
            queryDraft={queryDraft}
            onQueryDraft={setQueryDraft}
            onSubmitQuery={submitQuery}
            topK={topK}
            onTopK={setTopK}
            floor={floor}
            onFloor={setFloor}
          />
        </div>

        {/* -------- body -------- */}
        <div className="relative px-6 py-6 min-h-[560px]">
          {!target && (
            <div className="text-xs text-ink-300 text-center py-24">
              Pick a target above — a note in the Inspector, a cluster, or ask an
              ad-hoc question — and Prism will interrogate the vault through eight
              lenses.
            </div>
          )}
          {error && (
            <div className="mb-4 text-xs font-mono text-rose-300 bg-rose-500/10 ring-1 ring-rose-400/40 rounded px-3 py-2">
              {error}
            </div>
          )}
          {report && target && (
            <PrismBody
              report={report}
              busy={busy}
              composite={composite}
              onPickClick={handlePickClick}
              onUseSpark={useSparkAsDraft}
              copyFlash={copyFlash}
            />
          )}
          {busy && !report && (
            <div className="text-xs font-mono text-ink-300">interrogating vault…</div>
          )}
        </div>
      </div>
    </div>
  );
}

// --------------------------------------------------------------- picker

function TargetPicker({
  target,
  seedNote,
  communities,
  onPickNote,
  onPickCluster,
  queryDraft,
  onQueryDraft,
  onSubmitQuery,
  topK,
  onTopK,
  floor,
  onFloor,
}: {
  target: TargetChoice | null;
  seedNote?: GraphNode | null;
  communities: Community[];
  onPickNote: () => void;
  onPickCluster: (c: Community) => void;
  queryDraft: string;
  onQueryDraft: (q: string) => void;
  onSubmitQuery: () => void;
  topK: number;
  onTopK: (n: number) => void;
  floor: number;
  onFloor: (n: number) => void;
}) {
  return (
    <div className="grid grid-cols-12 gap-4 items-start">
      <div className="col-span-12 md:col-span-3">
        <div className="text-[10px] uppercase tracking-[0.16em] text-ink-300 mb-1.5">
          note target
        </div>
        <button
          onClick={onPickNote}
          disabled={!seedNote}
          className={`w-full text-left rounded-lg px-3 py-2 ring-1 transition text-xs font-mono ${
            target?.kind === "note" && seedNote && target.id === seedNote.id
              ? "bg-white/[0.06] ring-white/25 text-ink-100"
              : "bg-white/[0.02] ring-white/10 text-ink-300 hover:text-ink-100 hover:ring-white/20"
          } disabled:opacity-40`}
          title={seedNote ? "Interrogate the note currently selected in the Inspector" : "Select a note in the Inspector first"}
        >
          <div className="text-[10px] uppercase tracking-[0.14em] text-ink-400 mb-0.5">
            selected
          </div>
          <div className="truncate text-ink-100">
            {seedNote ? seedNote.title : "— none selected —"}
          </div>
        </button>
      </div>
      <div className="col-span-12 md:col-span-4">
        <div className="text-[10px] uppercase tracking-[0.16em] text-ink-300 mb-1.5">
          cluster target
        </div>
        <div className="flex flex-wrap gap-1.5 max-h-[86px] overflow-y-auto pr-1">
          {communities.length === 0 && (
            <span className="text-[11px] font-mono text-ink-400 italic">no clusters yet</span>
          )}
          {communities.map((c) => {
            const active = target?.kind === "cluster" && target.id === c.id;
            return (
              <button
                key={c.id}
                onClick={() => onPickCluster(c)}
                className={`text-[11px] font-mono rounded-full px-2.5 py-1 ring-1 transition ${
                  active
                    ? "bg-white/[0.08] ring-white/25 text-ink-100"
                    : "bg-white/[0.02] ring-white/10 text-ink-200 hover:text-ink-100 hover:ring-white/20"
                }`}
                title={`${c.size} notes · ${c.terms.slice(0, 3).join(" · ")}`}
              >
                <span
                  className="inline-block w-2 h-2 rounded-full mr-1.5 align-middle"
                  style={{ backgroundColor: c.color }}
                />
                {c.name}
                <span className="ml-1 text-ink-400">{c.size}</span>
              </button>
            );
          })}
        </div>
      </div>
      <div className="col-span-12 md:col-span-5">
        <div className="text-[10px] uppercase tracking-[0.16em] text-ink-300 mb-1.5">
          ad-hoc query
        </div>
        <div className="flex items-center gap-2">
          <input
            type="text"
            value={queryDraft}
            onChange={(e) => onQueryDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") onSubmitQuery();
            }}
            placeholder='e.g. "is boring technology overrated?"'
            className="flex-1 bg-white/[0.02] ring-1 ring-white/10 focus:ring-white/30 rounded-lg px-3 py-2 text-xs font-mono text-ink-100 placeholder:text-ink-400 outline-none"
          />
          <button
            onClick={onSubmitQuery}
            disabled={!queryDraft.trim()}
            className="text-[11px] font-mono uppercase tracking-[0.14em] px-3 py-2 rounded-lg bg-white/[0.04] ring-1 ring-white/15 text-ink-100 hover:ring-white/30 disabled:opacity-40"
          >
            probe
          </button>
        </div>
        <div className="mt-2.5 flex items-center gap-4 text-[10px] font-mono text-ink-300">
          <label className="flex items-center gap-2">
            top-K
            <input
              type="range"
              min={1}
              max={6}
              value={topK}
              onChange={(e) => onTopK(Number(e.target.value))}
              className="w-24 accent-rose-400"
            />
            <span className="text-ink-100 tabular-nums">{topK}</span>
          </label>
          <label className="flex items-center gap-2">
            floor
            <input
              type="range"
              min={0}
              max={70}
              value={Math.round(floor * 100)}
              onChange={(e) => onFloor(Number(e.target.value) / 100)}
              className="w-24 accent-cyan-400"
            />
            <span className="text-ink-100 tabular-nums">{floor.toFixed(2)}</span>
          </label>
        </div>
      </div>
    </div>
  );
}

// --------------------------------------------------------------- body

function PrismBody({
  report,
  busy,
  composite,
  onPickClick,
  onUseSpark,
  copyFlash,
}: {
  report: PrismReport;
  busy: boolean;
  composite: { strong?: PrismLensResult; weak?: PrismLensResult } | null;
  onPickClick: (nid: number, title: string) => void;
  onUseSpark: () => void;
  copyFlash: string | null;
}) {
  const dist = report.stance_distribution;

  return (
    <div className={`space-y-5 ${busy ? "opacity-70 transition-opacity" : ""}`}>
      {/* -------- target card + composite strip -------- */}
      <div className="grid grid-cols-12 gap-4">
        <div className="col-span-12 md:col-span-7 rounded-xl bg-white/[0.02] ring-1 ring-white/8 p-4">
          <div className="flex items-baseline justify-between gap-3">
            <div className="text-[10px] uppercase tracking-[0.16em] text-ink-300">
              target · {report.target.kind}
              {report.target.cluster_color && (
                <span
                  className="inline-block ml-2 w-2 h-2 rounded-full align-middle"
                  style={{ backgroundColor: report.target.cluster_color }}
                />
              )}
            </div>
            <span className="text-[10px] font-mono text-ink-400">
              prism_id <span className="text-ink-200">{report.prism_id}</span>
            </span>
          </div>
          <div className="mt-1 text-sm font-semibold text-ink-100">
            {report.target.label}
          </div>
          {report.target.excerpt && (
            <div className="mt-2 text-[12px] leading-relaxed text-ink-300 border-l-2 border-white/10 pl-3 italic">
              {report.target.excerpt}
            </div>
          )}
        </div>
        <div className="col-span-12 md:col-span-5 rounded-xl bg-white/[0.02] ring-1 ring-white/8 p-4">
          <div className="text-[10px] uppercase tracking-[0.16em] text-ink-300 mb-2">
            composite stance
          </div>
          <StanceBar dist={dist} />
          <div className="mt-3 grid grid-cols-2 gap-2 text-[11px] font-mono">
            <div className="rounded-lg bg-white/[0.02] ring-1 ring-white/8 px-2.5 py-1.5">
              <div className="text-[9px] uppercase tracking-[0.14em] text-ink-400">
                strongest
              </div>
              {composite?.strong ? (
                <StrongWeakChip lens={composite.strong} />
              ) : (
                <div className="text-ink-400">—</div>
              )}
            </div>
            <div className="rounded-lg bg-white/[0.02] ring-1 ring-white/8 px-2.5 py-1.5">
              <div className="text-[9px] uppercase tracking-[0.14em] text-ink-400">
                weakest · a hole
              </div>
              {composite?.weak ? (
                <StrongWeakChip lens={composite.weak} />
              ) : (
                <div className="text-ink-400">—</div>
              )}
            </div>
          </div>
          {report.dominant_family && (
            <div className="mt-2 text-[10px] font-mono text-ink-300">
              dominant family:{" "}
              <span className="text-ink-100">{FAMILY_LABEL[report.dominant_family] ?? report.dominant_family}</span>
              <span className="ml-3 text-ink-400">
                {report.stats.candidates_considered} of {report.stats.total_notes} notes above floor
              </span>
            </div>
          )}
        </div>
      </div>

      {/* -------- spark suggestion -------- */}
      {report.spark_suggestion && (
        <div className="rounded-xl bg-gradient-to-r from-violet-500/12 via-cyan-500/10 to-rose-500/12 ring-1 ring-white/12 p-3.5 flex items-center gap-3">
          <div
            aria-hidden
            className="w-7 h-7 rounded-full bg-gradient-to-br from-amber-400/40 to-violet-500/40 ring-1 ring-white/15 flex items-center justify-center text-sm"
          >
            ⚡
          </div>
          <div className="flex-1 text-[12px] leading-relaxed text-ink-100">
            <div className="text-[9px] uppercase tracking-[0.14em] text-ink-300 mb-0.5">
              spark · fill the weakest lens
            </div>
            {report.spark_suggestion}
          </div>
          <button
            onClick={onUseSpark}
            className="text-[11px] font-mono uppercase tracking-[0.14em] px-3 py-1.5 rounded-full bg-white/[0.06] ring-1 ring-white/15 text-ink-100 hover:ring-white/30"
          >
            use as draft
          </button>
        </div>
      )}

      {/* -------- lens grid -------- */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {report.lenses.map((l) => (
          <LensCard key={l.id} lens={l} onPickClick={onPickClick} />
        ))}
      </div>

      {copyFlash && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-[60] px-4 py-2 rounded-full bg-white/[0.04] ring-1 ring-white/20 text-[11px] font-mono text-ink-100 backdrop-blur">
          {copyFlash}
        </div>
      )}
    </div>
  );
}

// --------------------------------------------------------------- lens card

function LensCard({
  lens,
  onPickClick,
}: {
  lens: PrismLensResult;
  onPickClick: (nid: number, title: string) => void;
}) {
  const style = LENS_STYLE[lens.color] ?? LENS_STYLE.sky;
  const stance = STANCE_STYLE[lens.stance];
  const coveragePct = Math.round(lens.coverage * 100);

  return (
    <div className={`rounded-xl bg-gradient-to-br ${style.gradient} ring-1 ${style.ring} p-3.5 flex flex-col gap-2.5 min-h-[220px]`}>
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <div
            className={`w-7 h-7 rounded-lg ${style.tile} ring-1 flex items-center justify-center text-sm ${style.text}`}
            aria-hidden
          >
            {lens.icon}
          </div>
          <div className="min-w-0">
            <div className={`text-[13px] font-semibold ${style.text} truncate`}>
              {lens.label}
            </div>
            <div className="text-[10px] text-ink-300 truncate">{lens.tagline}</div>
          </div>
        </div>
        <span
          className={`text-[10px] font-mono uppercase tracking-[0.12em] px-1.5 py-0.5 rounded ring-1 ${stance.chip} shrink-0`}
        >
          {stance.label}
        </span>
      </div>

      <div>
        <div className="flex items-baseline justify-between text-[10px] font-mono text-ink-300">
          <span>coverage</span>
          <span className={style.text}>{coveragePct}%</span>
        </div>
        <div className="mt-1 h-1.5 rounded-full bg-white/[0.05] overflow-hidden">
          <div
            className={`h-full ${style.dot}`}
            style={{ width: `${Math.max(3, coveragePct)}%`, opacity: coveragePct < 5 ? 0.35 : 1 }}
          />
        </div>
        {lens.weakness && (
          <div className="mt-1.5 text-[10px] italic text-ink-400">{lens.weakness}</div>
        )}
      </div>

      <div className="space-y-1.5 pt-1">
        {lens.picks.length === 0 && (
          <div className="text-[11px] font-mono italic text-ink-400 px-1">
            (no supporting notes)
          </div>
        )}
        {lens.picks.map((p) => (
          <button
            key={`${lens.id}-${p.note_id}`}
            onClick={() => onPickClick(p.note_id, p.title)}
            className="block w-full text-left rounded-lg bg-white/[0.02] ring-1 ring-white/8 hover:ring-white/20 hover:bg-white/[0.04] px-2.5 py-1.5 transition"
          >
            <div className="flex items-center gap-2">
              {p.is_top && (
                <span
                  className={`text-[10px] font-bold ${style.text}`}
                  aria-label="top pick"
                >
                  ★
                </span>
              )}
              {p.cluster_color && (
                <span
                  className="w-1.5 h-1.5 rounded-full shrink-0"
                  style={{ backgroundColor: p.cluster_color }}
                />
              )}
              <span className="text-[11.5px] text-ink-100 truncate flex-1">
                {p.title}
              </span>
              <span className="text-[9px] font-mono text-ink-400 tabular-nums shrink-0">
                {(p.similarity * 100).toFixed(0)}·{(p.lexicon_score * 100).toFixed(0)}
              </span>
            </div>
            <div className={`mt-0.5 text-[10.5px] leading-snug ${style.softText} pl-3 border-l ${style.ring.replace("ring-", "border-").replace("/50", "/25")} line-clamp-2`}>
              {p.quote}
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}

// --------------------------------------------------------------- helpers

function StrongWeakChip({ lens }: { lens: PrismLensResult }) {
  const style = LENS_STYLE[lens.color] ?? LENS_STYLE.sky;
  return (
    <div className="flex items-center gap-1.5">
      <span className={`w-2 h-2 rounded-full ${style.dot}`} />
      <span className={`text-[11px] ${style.text}`}>{lens.label}</span>
      <span className="ml-auto text-[10px] text-ink-400">{(lens.coverage * 100).toFixed(0)}%</span>
    </div>
  );
}

function StanceBar({ dist }: { dist: Record<PrismStance, number> }) {
  const stances: PrismStance[] = ["reinforce", "challenge", "neutral", "thin"];
  const barColor: Record<PrismStance, string> = {
    reinforce: "bg-emerald-500",
    challenge: "bg-rose-500",
    neutral: "bg-sky-500",
    thin: "bg-ink-500",
  };
  return (
    <div>
      <div className="flex w-full h-2.5 rounded-full overflow-hidden ring-1 ring-white/8">
        {stances.map((s) => {
          const w = Math.round((dist[s] ?? 0) * 100);
          if (w === 0) return null;
          return (
            <div
              key={s}
              className={barColor[s]}
              style={{ width: `${w}%` }}
              title={`${s} ${w}%`}
            />
          );
        })}
      </div>
      <div className="mt-1.5 flex justify-between text-[10px] font-mono text-ink-300">
        {stances.map((s) => (
          <span key={s} className="flex items-center gap-1">
            <span className={`w-1.5 h-1.5 rounded-full ${barColor[s]}`} />
            {s} {Math.round((dist[s] ?? 0) * 100)}%
          </span>
        ))}
      </div>
    </div>
  );
}

// Re-export lens id type for consumers.
export type { PrismLensId };
