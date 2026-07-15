"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { api } from "@/lib/api";
import type {
  GraphNode,
  SignalCitationDelta,
  SignalDelta,
  SignalLensNoteSummary,
  SignalReport,
  SignalStatus,
  SignalSubqDelta,
} from "@/lib/types";

type Props = {
  open: boolean;
  onClose: () => void;
  /** Jump the canvas onto a note (closes the modal). */
  onSelectNote: (stub: GraphNode) => void;
  /** Open the Compass modal at a specific question id. */
  onOpenInCompass: (questionId: number) => void;
  /** Called after any watch mutation so the parent can refresh badges. */
  onMutated?: () => void;
};

/**
 * Signal — persistent watches over Compass research questions.
 *
 * Compass is your *in-flight* research surface — you pin a question,
 * mark reads, watch a citation-stitched working answer grow beneath you.
 * That's a one-sitting flow. Real research is a thread you drop and pick
 * up over days or weeks.
 *
 * Signal turns any Compass question into a *watched* thread. Pinning
 * snapshots the current lens; the next time you open Signal, the lens is
 * recomputed and diffed against that snapshot. You see, per question:
 *
 * - Coverage delta (mass-weighted).
 * - Notes that joined or left the lens since pin.
 * - Notes you newly read for this question.
 * - Citations added / removed from the working answer.
 * - Per-subquestion coverage_pct delta — which sub-aspect moved.
 *
 * "Refresh" re-baselines a watch — the "mark as read" of the rail; the
 * next visit shows only what's changed *since your last review*.
 */
export function Signal({
  open,
  onClose,
  onSelectNote,
  onOpenInCompass,
  onMutated,
}: Props) {
  const [report, setReport] = useState<SignalReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await api.signalList();
      setReport(r);
    } catch (e) {
      setError(e instanceof Error ? e.message : "failed to load signal report");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!open) return;
    refresh();
  }, [open, refresh]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  const handleRebaseline = useCallback(
    async (qid: number) => {
      setBusyId(qid);
      try {
        await api.signalRefresh(qid);
        await refresh();
        onMutated?.();
      } catch (e) {
        setError(e instanceof Error ? e.message : "refresh failed");
      } finally {
        setBusyId(null);
      }
    },
    [refresh, onMutated],
  );

  const handleUnwatch = useCallback(
    async (qid: number) => {
      if (!confirm("Stop watching this question? Its snapshot is discarded."))
        return;
      setBusyId(qid);
      try {
        await api.signalUnwatch(qid);
        await refresh();
        onMutated?.();
      } catch (e) {
        setError(e instanceof Error ? e.message : "unwatch failed");
      } finally {
        setBusyId(null);
      }
    },
    [refresh, onMutated],
  );

  const summary = useMemo(() => {
    if (!report) return null;
    return {
      total: report.watch_count,
      grown: report.grown_count,
      shrunk: report.shrunk_count,
      stable: report.stable_count,
      neu: report.new_count,
    };
  }, [report]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center px-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="signal-title"
    >
      <div
        className="absolute inset-0 bg-ink-900/82 backdrop-blur-md"
        onClick={onClose}
      />
      <div className="absolute inset-0 pointer-events-none bg-grid-fade opacity-60" />

      <div className="relative w-full max-w-[1180px] max-h-[94vh] flex flex-col rounded-2xl bg-ink-800/92 ring-1 ring-white/10 shadow-card overflow-hidden animate-fade-in">
        <SignalHeader
          summary={summary}
          loading={loading}
          onClose={onClose}
          onRefresh={refresh}
        />

        <div className="flex-1 overflow-y-auto">
          {error && (
            <div className="mx-6 mt-4 rounded-xl bg-rose-500/10 ring-1 ring-rose-400/40 p-3 text-xs font-mono text-rose-200">
              {error}
            </div>
          )}

          {!loading && report && report.watches.length === 0 && (
            <EmptyState />
          )}

          {loading && (
            <div className="grid place-items-center text-ink-300 font-mono text-xs h-64">
              <div className="flex items-center gap-3">
                <SignalPulse />
                triangulating deltas …
              </div>
            </div>
          )}

          {!loading && report && report.watches.length > 0 && (
            <div className="p-6 space-y-4">
              {report.watches.map((w) => (
                <WatchCard
                  key={w.question_id}
                  delta={w}
                  expanded={expandedId === w.question_id}
                  busy={busyId === w.question_id}
                  onToggle={() =>
                    setExpandedId((prev) =>
                      prev === w.question_id ? null : w.question_id,
                    )
                  }
                  onRebaseline={() => handleRebaseline(w.question_id)}
                  onUnwatch={() => handleUnwatch(w.question_id)}
                  onOpenInCompass={() => onOpenInCompass(w.question_id)}
                  onSelectNote={(n) =>
                    onSelectNote({
                      id: n.note_id,
                      title: n.title,
                      body: "",
                      tags: [],
                      degree: 0,
                      weight: 0,
                    } as GraphNode)
                  }
                />
              ))}
            </div>
          )}
        </div>

        <div className="border-t border-white/5 px-6 py-2 text-[10px] font-mono text-ink-400 flex items-center justify-between bg-ink-900/40">
          <span>
            signal · persistent watches over Compass · re-baseline is your{" "}
            <span className="text-ink-200">mark-as-read</span> · press{" "}
            <span className="text-ink-200">esc</span> to close
          </span>
          {report && report.watch_count > 0 && (
            <a
              href={api.signalExportUrl()}
              target="_blank"
              rel="noreferrer"
              className="text-ink-300 hover:text-ink-100 transition"
            >
              ⤓ export.md
            </a>
          )}
        </div>
      </div>
    </div>
  );
}

// ----------------------------------------------------------------- header

function SignalHeader({
  summary,
  loading,
  onClose,
  onRefresh,
}: {
  summary: { total: number; grown: number; shrunk: number; stable: number; neu: number } | null;
  loading: boolean;
  onClose: () => void;
  onRefresh: () => void;
}) {
  return (
    <div
      className="flex items-center justify-between gap-4 px-6 py-4 border-b border-white/5"
      style={{
        background:
          "linear-gradient(90deg, rgba(163,230,53,0.14), rgba(34,211,238,0.15) 50%, rgba(168,85,247,0.12))",
      }}
    >
      <div className="flex items-center gap-3 min-w-0">
        <SignalGlyph />
        <div className="min-w-0">
          <div
            id="signal-title"
            className="text-base font-semibold tracking-tight text-ink-100 flex items-center gap-2"
          >
            Signal — watched research threads
            <span className="px-1.5 py-0.5 rounded-md bg-gradient-to-r from-synapse-lime/30 to-synapse-cyan/30 ring-1 ring-white/10 text-[9px] uppercase tracking-widest text-ink-100">
              new
            </span>
          </div>
          <div className="text-[11px] font-mono text-ink-300 uppercase tracking-[0.16em] mt-0.5">
            what your vault has learned since you pinned each question
          </div>
        </div>
      </div>
      <div className="flex items-center gap-2 shrink-0">
        {summary && summary.total > 0 && (
          <div className="hidden sm:flex items-center gap-1.5 text-[11px] font-mono">
            {summary.grown > 0 && (
              <span className="rounded-full bg-synapse-lime/15 ring-1 ring-synapse-lime/40 text-synapse-lime px-2 py-0.5">
                ↑ {summary.grown} grown
              </span>
            )}
            {summary.shrunk > 0 && (
              <span className="rounded-full bg-synapse-pink/15 ring-1 ring-synapse-pink/40 text-synapse-pink px-2 py-0.5">
                ↓ {summary.shrunk} shrunk
              </span>
            )}
            {summary.stable > 0 && (
              <span className="rounded-full bg-white/[0.04] ring-1 ring-white/10 text-ink-300 px-2 py-0.5">
                • {summary.stable} stable
              </span>
            )}
            {summary.neu > 0 && (
              <span className="rounded-full bg-synapse-cyan/15 ring-1 ring-synapse-cyan/40 text-synapse-cyan px-2 py-0.5">
                ✦ {summary.neu} new
              </span>
            )}
          </div>
        )}
        <button
          onClick={onRefresh}
          disabled={loading}
          className="text-[11px] font-mono text-ink-300 hover:text-ink-100 rounded-full ring-1 ring-white/10 hover:ring-white/25 px-3 py-1 transition disabled:opacity-50"
          aria-label="recompute deltas"
          title="Recompute every watch's delta against its snapshot"
        >
          ↻ recompute
        </button>
        <button
          onClick={onClose}
          className="text-xs font-mono text-ink-300 hover:text-ink-100 rounded-full ring-1 ring-white/10 hover:ring-white/25 px-3 py-1 transition"
        >
          close ⨯
        </button>
      </div>
    </div>
  );
}

function SignalGlyph() {
  return (
    <div className="relative w-9 h-9">
      <svg viewBox="0 0 40 40" className="w-full h-full">
        <defs>
          <linearGradient id="sg" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="#a3e635" />
            <stop offset="50%" stopColor="#22d3ee" />
            <stop offset="100%" stopColor="#a855f7" />
          </linearGradient>
        </defs>
        <circle cx="20" cy="20" r="2.5" fill="url(#sg)" />
        <circle
          cx="20"
          cy="20"
          r="8"
          fill="none"
          stroke="url(#sg)"
          strokeWidth="0.75"
          opacity="0.7"
        >
          <animate
            attributeName="r"
            values="8;13;8"
            dur="3s"
            repeatCount="indefinite"
          />
          <animate
            attributeName="opacity"
            values="0.7;0.1;0.7"
            dur="3s"
            repeatCount="indefinite"
          />
        </circle>
        <circle
          cx="20"
          cy="20"
          r="14"
          fill="none"
          stroke="url(#sg)"
          strokeWidth="0.5"
          opacity="0.4"
        >
          <animate
            attributeName="r"
            values="14;19;14"
            dur="3s"
            begin="0.6s"
            repeatCount="indefinite"
          />
          <animate
            attributeName="opacity"
            values="0.4;0;0.4"
            dur="3s"
            begin="0.6s"
            repeatCount="indefinite"
          />
        </circle>
      </svg>
    </div>
  );
}

function SignalPulse() {
  return (
    <span className="inline-block w-2.5 h-2.5 rounded-full bg-synapse-cyan animate-pulse-slow" />
  );
}

// ----------------------------------------------------------------- empty

function EmptyState() {
  return (
    <div className="mx-6 my-10 rounded-2xl bg-white/[0.02] ring-1 ring-white/5 p-10 text-center">
      <div className="mx-auto mb-4 w-14 h-14 rounded-full bg-gradient-to-br from-synapse-lime/25 to-synapse-cyan/25 ring-1 ring-white/10 grid place-items-center text-2xl">
        ⌒
      </div>
      <div className="text-ink-100 font-semibold text-sm mb-1">
        No signals yet
      </div>
      <p className="text-xs text-ink-300 max-w-md mx-auto leading-relaxed">
        Open Compass, pick a research question, and click{" "}
        <span className="text-synapse-lime">◎ watch</span> to pin it.
        Signal will snapshot the current lens; the next time you check
        back, it'll tell you exactly what your vault has learned since.
      </p>
    </div>
  );
}

// ----------------------------------------------------------------- watch card

function WatchCard({
  delta,
  expanded,
  busy,
  onToggle,
  onRebaseline,
  onUnwatch,
  onOpenInCompass,
  onSelectNote,
}: {
  delta: SignalDelta;
  expanded: boolean;
  busy: boolean;
  onToggle: () => void;
  onRebaseline: () => void;
  onUnwatch: () => void;
  onOpenInCompass: () => void;
  onSelectNote: (n: SignalLensNoteSummary | SignalCitationDelta) => void;
}) {
  const tint = statusTint(delta.status);

  return (
    <article
      className={`relative rounded-2xl bg-white/[0.02] ring-1 ${tint.ring} p-5 space-y-4 transition ${busy ? "opacity-60" : ""}`}
      style={{
        boxShadow: `0 0 26px -18px ${tint.glow}`,
      }}
    >
      <header className="flex items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap mb-1.5">
            <StatusBadge status={delta.status} />
            <span className="text-[10px] font-mono text-ink-400 uppercase tracking-[0.14em]">
              pinned {relativeAgo(delta.pinned_at)}
              {delta.last_refreshed_at && (
                <>
                  {" · refreshed "}
                  {relativeAgo(delta.last_refreshed_at)}
                </>
              )}
            </span>
          </div>
          <button
            onClick={onOpenInCompass}
            className="text-left group"
            title="Open this question in Compass"
          >
            <h3 className="text-[15px] font-semibold text-ink-100 group-hover:text-synapse-cyan transition leading-snug">
              {delta.question_text}
            </h3>
          </button>
          <p className={`mt-1.5 text-xs font-mono leading-relaxed ${tint.headline}`}>
            {delta.headline}
          </p>
        </div>
        <CoverageRing
          now={delta.coverage_now}
          pinned={delta.coverage_pinned}
          delta={delta.coverage_delta}
        />
      </header>

      <ChipRow delta={delta} />

      <footer className="flex items-center justify-between gap-3 pt-1">
        <button
          onClick={onToggle}
          className="text-[11px] font-mono text-ink-300 hover:text-ink-100 transition"
        >
          {expanded ? "▲ hide detail" : "▼ show detail"}
        </button>
        <div className="flex items-center gap-2">
          <button
            onClick={onOpenInCompass}
            className="text-[11px] font-mono rounded-full bg-synapse-cyan/15 ring-1 ring-synapse-cyan/40 hover:ring-synapse-cyan/70 text-synapse-cyan px-3 py-1 transition"
          >
            🧭 open in compass
          </button>
          <button
            onClick={onRebaseline}
            disabled={busy}
            className="text-[11px] font-mono rounded-full bg-synapse-lime/15 ring-1 ring-synapse-lime/40 hover:ring-synapse-lime/70 text-synapse-lime px-3 py-1 transition disabled:opacity-50"
            title="Re-snapshot the current lens as the new baseline"
          >
            ↻ mark reviewed
          </button>
          <button
            onClick={onUnwatch}
            disabled={busy}
            className="text-[11px] font-mono rounded-full bg-white/[0.03] ring-1 ring-white/10 hover:ring-rose-400/50 text-ink-300 hover:text-rose-200 px-3 py-1 transition disabled:opacity-50"
            title="Stop watching this question"
          >
            ⨯ unwatch
          </button>
        </div>
      </footer>

      {expanded && (
        <div className="pt-4 border-t border-white/5 space-y-4">
          {delta.citations_added.length > 0 && (
            <DetailBlock
              label="New citations"
              accent="text-synapse-lime"
            >
              {delta.citations_added.map((c) => (
                <CitationRow
                  key={c.note_id}
                  citation={c}
                  polarity="add"
                  onClick={() => onSelectNote(c)}
                />
              ))}
            </DetailBlock>
          )}
          {delta.citations_removed.length > 0 && (
            <DetailBlock label="Dropped citations" accent="text-synapse-pink">
              {delta.citations_removed.map((c) => (
                <CitationRow
                  key={c.note_id}
                  citation={c}
                  polarity="drop"
                  onClick={() => onSelectNote(c)}
                />
              ))}
            </DetailBlock>
          )}
          {delta.joined_since.length > 0 && (
            <DetailBlock
              label={`Joined the lens (${delta.joined_since_count})`}
              accent="text-synapse-cyan"
            >
              {delta.joined_since.map((n) => (
                <NoteRow key={n.note_id} note={n} onClick={() => onSelectNote(n)} />
              ))}
            </DetailBlock>
          )}
          {delta.left_since.length > 0 && (
            <DetailBlock
              label={`Left the lens (${delta.left_since_count})`}
              accent="text-ink-300"
            >
              {delta.left_since.map((n) => (
                <NoteRow key={n.note_id} note={n} dim onClick={() => onSelectNote(n)} />
              ))}
            </DetailBlock>
          )}
          {delta.reads_new.length > 0 && (
            <DetailBlock
              label={`You newly read (${delta.reads_new_count})`}
              accent="text-synapse-amber"
            >
              {delta.reads_new.map((n) => (
                <NoteRow key={n.note_id} note={n} onClick={() => onSelectNote(n)} />
              ))}
            </DetailBlock>
          )}
          {delta.subquestion_progress.length > 0 && (
            <DetailBlock label="Sub-questions that moved" accent="text-synapse-violet">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                {delta.subquestion_progress.slice(0, 8).map((s) => (
                  <SubqRow key={s.term} subq={s} />
                ))}
              </div>
            </DetailBlock>
          )}
          {delta.working_answer && (
            <DetailBlock label="Working answer (now)" accent="text-ink-200">
              <p className="text-[12.5px] text-ink-200 leading-relaxed font-serif whitespace-pre-wrap">
                {delta.working_answer}
              </p>
            </DetailBlock>
          )}
          {noDetailFor(delta) && (
            <p className="text-[12px] text-ink-400 italic">
              No enumerated deltas — nothing joined, left, was read, or
              changed citations since {relativeAgo(delta.last_refreshed_at || delta.pinned_at)}.
              A rebaseline resets your review pointer.
            </p>
          )}
        </div>
      )}
    </article>
  );
}

function noDetailFor(d: SignalDelta): boolean {
  return (
    d.citations_added.length === 0 &&
    d.citations_removed.length === 0 &&
    d.joined_since.length === 0 &&
    d.left_since.length === 0 &&
    d.reads_new.length === 0 &&
    d.subquestion_progress.length === 0 &&
    !d.working_answer
  );
}

// ----------------------------------------------------------------- pieces

function StatusBadge({ status }: { status: SignalStatus }) {
  const s = statusTint(status);
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[10px] font-mono uppercase tracking-[0.14em] ring-1 ${s.badgeRing} ${s.badgeBg} ${s.badgeText}`}
    >
      <span className="w-1.5 h-1.5 rounded-full" style={{ background: s.dot }} />
      {status}
    </span>
  );
}

function ChipRow({ delta }: { delta: SignalDelta }) {
  const chips: { key: string; label: ReactNode; tint: string }[] = [];
  if (delta.joined_since_count > 0)
    chips.push({
      key: "joined",
      label: (
        <>
          <span className="text-synapse-cyan">+{delta.joined_since_count}</span>{" "}
          in lens
        </>
      ),
      tint: "ring-synapse-cyan/40 text-ink-100 bg-synapse-cyan/8",
    });
  if (delta.left_since_count > 0)
    chips.push({
      key: "left",
      label: (
        <>
          <span className="text-synapse-pink">-{delta.left_since_count}</span>{" "}
          left lens
        </>
      ),
      tint: "ring-synapse-pink/40 text-ink-100 bg-synapse-pink/8",
    });
  if (delta.citations_added.length > 0)
    chips.push({
      key: "citeadd",
      label: (
        <>
          <span className="text-synapse-lime">+{delta.citations_added.length}</span>{" "}
          citation
          {delta.citations_added.length !== 1 && "s"}
        </>
      ),
      tint: "ring-synapse-lime/40 text-ink-100 bg-synapse-lime/8",
    });
  if (delta.citations_removed.length > 0)
    chips.push({
      key: "citedrop",
      label: (
        <>
          <span className="text-synapse-pink">-{delta.citations_removed.length}</span>{" "}
          dropped
        </>
      ),
      tint: "ring-synapse-pink/40 text-ink-100 bg-synapse-pink/8",
    });
  if (delta.reads_new_count > 0)
    chips.push({
      key: "reads",
      label: (
        <>
          <span className="text-synapse-amber">{delta.reads_new_count}</span>{" "}
          new read
          {delta.reads_new_count !== 1 && "s"}
        </>
      ),
      tint: "ring-synapse-amber/40 text-ink-100 bg-synapse-amber/8",
    });
  if (delta.subquestion_progress.length > 0)
    chips.push({
      key: "subq",
      label: (
        <>
          <span className="text-synapse-violet">{delta.subquestion_progress.length}</span>{" "}
          sub-question{delta.subquestion_progress.length !== 1 && "s"} moved
        </>
      ),
      tint: "ring-synapse-violet/40 text-ink-100 bg-synapse-violet/8",
    });
  if (chips.length === 0)
    chips.push({
      key: "quiet",
      label: <span className="text-ink-400">no movement</span>,
      tint: "ring-white/10 text-ink-300 bg-white/[0.02]",
    });
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {chips.map((c) => (
        <span
          key={c.key}
          className={`inline-flex items-center rounded-full ring-1 px-2 py-0.5 text-[10.5px] font-mono ${c.tint}`}
        >
          {c.label}
        </span>
      ))}
    </div>
  );
}

function CoverageRing({
  now,
  pinned,
  delta,
}: {
  now: number;
  pinned: number;
  delta: number;
}) {
  const size = 76;
  const stroke = 6;
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const nowFrac = Math.max(0, Math.min(100, now)) / 100;
  const pinnedFrac = Math.max(0, Math.min(100, pinned)) / 100;
  const deltaFmt = delta >= 0 ? `+${delta.toFixed(1)}` : delta.toFixed(1);
  const deltaClass =
    delta > 0.5
      ? "text-synapse-lime"
      : delta < -0.5
        ? "text-synapse-pink"
        : "text-ink-300";
  return (
    <div className="shrink-0 relative" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          stroke="rgba(255,255,255,0.08)"
          strokeWidth={stroke}
          fill="none"
        />
        {/* Pinned baseline (dimmer) */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          stroke="rgba(148,163,184,0.4)"
          strokeWidth={stroke}
          strokeDasharray={`${c * pinnedFrac} ${c}`}
          strokeLinecap="round"
          fill="none"
          opacity={0.6}
        />
        {/* Current coverage on top */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          stroke="url(#cov-grad)"
          strokeWidth={stroke}
          strokeDasharray={`${c * nowFrac} ${c}`}
          strokeLinecap="round"
          fill="none"
        />
        <defs>
          <linearGradient id="cov-grad" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="#22d3ee" />
            <stop offset="100%" stopColor="#a855f7" />
          </linearGradient>
        </defs>
      </svg>
      <div className="absolute inset-0 grid place-items-center">
        <div className="text-center">
          <div className="text-[15px] font-semibold text-ink-100 leading-none">
            {Math.round(now)}%
          </div>
          <div className={`text-[9px] font-mono mt-0.5 ${deltaClass}`}>
            {deltaFmt}
          </div>
        </div>
      </div>
    </div>
  );
}

function DetailBlock({
  label,
  accent,
  children,
}: {
  label: string;
  accent: string;
  children: ReactNode;
}) {
  return (
    <div className="space-y-2">
      <div
        className={`text-[10px] font-mono uppercase tracking-[0.16em] ${accent}`}
      >
        {label}
      </div>
      <div className="space-y-1.5">{children}</div>
    </div>
  );
}

function CitationRow({
  citation,
  polarity,
  onClick,
}: {
  citation: SignalCitationDelta;
  polarity: "add" | "drop";
  onClick: () => void;
}) {
  const rail =
    polarity === "add"
      ? "before:bg-synapse-lime/70"
      : "before:bg-synapse-pink/70";
  const strike = polarity === "drop" ? "line-through opacity-70" : "";
  return (
    <button
      onClick={onClick}
      className={`relative w-full text-left rounded-lg bg-white/[0.02] hover:bg-white/[0.05] ring-1 ring-white/5 hover:ring-white/15 pl-3 pr-3 py-2 transition before:content-[''] before:absolute before:top-2 before:bottom-2 before:left-0 before:w-[3px] before:rounded-r ${rail}`}
    >
      <div className={`text-[12.5px] text-ink-100 font-medium ${strike}`}>
        {citation.title}
      </div>
      <div className="text-[11.5px] text-ink-300 font-serif leading-snug mt-0.5 line-clamp-2">
        {citation.excerpt}
      </div>
      <div className="text-[9.5px] font-mono text-ink-400 mt-1">
        #{citation.note_id} · relevance {citation.relevance.toFixed(2)}
      </div>
    </button>
  );
}

function NoteRow({
  note,
  dim,
  onClick,
}: {
  note: SignalLensNoteSummary;
  dim?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={`w-full text-left rounded-lg bg-white/[0.02] hover:bg-white/[0.05] ring-1 ring-white/5 hover:ring-white/15 px-3 py-2 transition ${dim ? "opacity-60" : ""}`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            {note.cluster_color && (
              <span
                className="inline-block w-1.5 h-1.5 rounded-full shrink-0"
                style={{ background: note.cluster_color }}
              />
            )}
            <span className="text-[12.5px] text-ink-100 font-medium truncate">
              {note.title}
            </span>
          </div>
          {note.snippet && (
            <div className="text-[11.5px] text-ink-300 mt-0.5 line-clamp-2 leading-snug">
              {note.snippet}
            </div>
          )}
        </div>
        {note.relevance > 0 && (
          <div className="shrink-0 text-[10px] font-mono text-ink-400">
            {note.relevance.toFixed(2)}
          </div>
        )}
      </div>
    </button>
  );
}

function SubqRow({ subq }: { subq: SignalSubqDelta }) {
  const delta = subq.coverage_pct_delta;
  const arrow =
    delta > 0.5 ? "↑" : delta < -0.5 ? "↓" : subq.note_count_pinned === 0 ? "✦" : "•";
  const arrowColor =
    delta > 0.5
      ? "text-synapse-lime"
      : delta < -0.5
        ? "text-synapse-pink"
        : subq.note_count_pinned === 0
          ? "text-synapse-cyan"
          : "text-ink-400";
  const now = Math.round(subq.coverage_pct_now);
  const pin = Math.round(subq.coverage_pct_pinned);
  const barPct = Math.max(2, Math.min(100, now));
  return (
    <div className="rounded-lg bg-white/[0.02] ring-1 ring-white/5 px-3 py-2">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <span className={`text-[13px] leading-none ${arrowColor}`}>{arrow}</span>
          <span className="text-[12px] text-ink-100 font-medium truncate">
            {subq.term}
          </span>
        </div>
        <div className="text-[10px] font-mono text-ink-300 shrink-0">
          {now}% <span className="text-ink-500">(was {pin}%)</span>
        </div>
      </div>
      <div className="mt-1.5 h-1 rounded-full bg-white/[0.06] overflow-hidden relative">
        <div
          className="h-full rounded-full bg-gradient-to-r from-synapse-cyan to-synapse-violet"
          style={{ width: `${barPct}%` }}
        />
        {subq.coverage_pct_pinned > 0 && (
          <div
            className="absolute top-0 h-full w-[2px] bg-ink-300/70"
            style={{ left: `${Math.min(100, subq.coverage_pct_pinned)}%` }}
            title={`pinned baseline: ${pin}%`}
          />
        )}
      </div>
      <div className="text-[9.5px] font-mono text-ink-400 mt-1">
        {subq.covered_now}/{subq.note_count_now} covered
        {subq.note_count_pinned !== subq.note_count_now && (
          <span className="text-ink-500">
            {" "}
            · was {subq.covered_pinned}/{subq.note_count_pinned}
          </span>
        )}
      </div>
    </div>
  );
}

// ----------------------------------------------------------------- utils

function statusTint(status: SignalStatus): {
  ring: string;
  glow: string;
  headline: string;
  badgeRing: string;
  badgeBg: string;
  badgeText: string;
  dot: string;
} {
  switch (status) {
    case "grown":
      return {
        ring: "ring-synapse-lime/30",
        glow: "rgba(163,230,53,0.55)",
        headline: "text-synapse-lime",
        badgeRing: "ring-synapse-lime/50",
        badgeBg: "bg-synapse-lime/12",
        badgeText: "text-synapse-lime",
        dot: "#a3e635",
      };
    case "shrunk":
      return {
        ring: "ring-synapse-pink/30",
        glow: "rgba(236,72,153,0.55)",
        headline: "text-synapse-pink",
        badgeRing: "ring-synapse-pink/50",
        badgeBg: "bg-synapse-pink/12",
        badgeText: "text-synapse-pink",
        dot: "#ec4899",
      };
    case "new":
      return {
        ring: "ring-synapse-cyan/30",
        glow: "rgba(34,211,238,0.55)",
        headline: "text-synapse-cyan",
        badgeRing: "ring-synapse-cyan/50",
        badgeBg: "bg-synapse-cyan/12",
        badgeText: "text-synapse-cyan",
        dot: "#22d3ee",
      };
    case "fresh":
      return {
        ring: "ring-synapse-violet/30",
        glow: "rgba(168,85,247,0.55)",
        headline: "text-synapse-violet",
        badgeRing: "ring-synapse-violet/50",
        badgeBg: "bg-synapse-violet/12",
        badgeText: "text-synapse-violet",
        dot: "#a855f7",
      };
    default:
      return {
        ring: "ring-white/10",
        glow: "rgba(148,163,184,0.35)",
        headline: "text-ink-300",
        badgeRing: "ring-white/15",
        badgeBg: "bg-white/[0.03]",
        badgeText: "text-ink-300",
        dot: "#94a3b8",
      };
  }
}

function relativeAgo(iso: string | null): string {
  if (!iso) return "—";
  const then = Date.parse(iso);
  if (!Number.isFinite(then)) return iso;
  const diffSec = Math.max(0, (Date.now() - then) / 1000);
  if (diffSec < 60) return "just now";
  if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m ago`;
  if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}h ago`;
  const days = Math.floor(diffSec / 86400);
  if (days < 30) return `${days}d ago`;
  const months = Math.floor(days / 30);
  if (months < 12) return `${months}mo ago`;
  return `${Math.floor(months / 12)}y ago`;
}
