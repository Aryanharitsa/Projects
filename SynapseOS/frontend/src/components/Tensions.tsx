"use client";

import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import type {
  GraphNode,
  NoteDraft,
  Tension,
  TensionKind,
  TensionReport,
  TensionSignalKind,
} from "@/lib/types";

type NoteStub = Pick<GraphNode, "id" | "title" | "body" | "tags" | "degree" | "weight">;

type Props = {
  open: boolean;
  onClose: () => void;
  onSelectNote: (node: NoteStub) => void;
  /**
   * The Reconcile button on a tension fires this with a NoteDraft —
   * the parent forwards it to the NoteComposer, which pre-fills its
   * fields and lets the user finish the bridge note in one click.
   */
  onReconcile: (draft: NoteDraft) => void;
};

const KIND_LABEL: Record<TensionSignalKind, string> = {
  polarity: "stance",
  antonym: "antonyms",
  contrast: "but-cues",
  title: "title clash",
};

const KIND_GLYPH: Record<TensionSignalKind, string> = {
  polarity: "↕",
  antonym: "⇄",
  contrast: "≠",
  title: "‼",
};

type Filter = "all" | TensionKind;

/**
 * Tensions — surface the contradictions your second brain has been
 * hiding from itself.
 *
 * Synthesis tells you what a cluster *says*; Tensions tells you where
 * your graph disagrees with itself. Each tension is a semantically-close
 * pair whose stances, antonyms, or title-form oppositions don't line up.
 * One quote per side proves it, and a one-click Reconcile pre-fills the
 * NoteComposer with a bridge prompt naming both sides so the
 * disagreement turns into the next atomic note.
 */
export function Tensions({ open, onClose, onSelectNote, onReconcile }: Props) {
  const [report, setReport] = useState<TensionReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<Filter>("all");

  useEffect(() => {
    if (!open) return;
    setLoading(true);
    setError(null);
    setReport(null);
    api
      .tensions()
      .then(setReport)
      .catch((e) => setError(e instanceof Error ? e.message : "failed to load tensions"))
      .finally(() => setLoading(false));
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  const filtered = useMemo(() => {
    if (!report) return [];
    if (filter === "all") return report.tensions;
    return report.tensions.filter((t) => t.kind === filter);
  }, [report, filter]);

  const counts = useMemo(() => {
    const c: { all: number; internal: number; cross: number } = {
      all: report?.tensions.length ?? 0,
      internal: 0,
      cross: 0,
    };
    for (const t of report?.tensions ?? []) c[t.kind]++;
    return c;
  }, [report]);

  if (!open) return null;

  const openNote = (id: number, title: string) => {
    onSelectNote({ id, title, body: "", tags: [], degree: 0, weight: 0 });
    onClose();
  };

  const reconcile = (t: Tension) => {
    onReconcile({
      title: t.bridge_title,
      body: t.bridge_prompt,
      tags: t.bridge_tags,
    });
    onClose();
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center px-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="tensions-title"
    >
      <div
        className="absolute inset-0 bg-ink-900/80 backdrop-blur-md"
        onClick={onClose}
      />
      <div className="absolute inset-0 pointer-events-none bg-grid-fade opacity-60" />

      <div className="relative w-full max-w-4xl max-h-[88vh] flex flex-col rounded-2xl bg-ink-800/90 ring-1 ring-white/10 shadow-card overflow-hidden animate-fade-in">
        {/* Header strip — rose/red gradient to read as "contradiction". */}
        <div
          className="flex items-center justify-between gap-4 px-6 py-4 border-b border-white/5"
          style={{
            background:
              "linear-gradient(90deg, rgba(244,63,94,0.16), rgba(168,85,247,0.08) 40%, transparent 80%)",
          }}
        >
          <div className="flex items-center gap-3 min-w-0">
            <TensionGlyph />
            <div className="min-w-0">
              <div
                id="tensions-title"
                className="text-base font-semibold tracking-tight text-ink-100 truncate"
              >
                Tensions in your second brain
              </div>
              <div className="text-[11px] font-mono text-ink-300 uppercase tracking-[0.16em] mt-0.5">
                where the graph disagrees with itself
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            {report && report.tension_count > 0 && (
              <a
                href={api.tensionsExportUrl()}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1.5 rounded-full bg-white/[0.03] ring-1 ring-white/10 hover:ring-rose-400/50 px-3 py-1 font-mono text-[11px] text-ink-200 hover:text-ink-100 transition"
                title="Download as portable Markdown"
              >
                ⤓ md
              </a>
            )}
            <button
              onClick={onClose}
              className="inline-flex items-center justify-center rounded-full w-8 h-8 ring-1 ring-white/10 text-ink-300 hover:text-ink-100 hover:ring-white/30 transition"
              aria-label="close"
            >
              ✕
            </button>
          </div>
        </div>

        {/* Filter tabs + summary */}
        <div className="flex items-center justify-between gap-4 px-6 py-3 border-b border-white/5 bg-ink-800/60">
          <div className="flex items-center gap-1.5 text-[11px] font-mono">
            <FilterChip
              active={filter === "all"}
              onClick={() => setFilter("all")}
              label="all"
              count={counts.all}
            />
            <FilterChip
              active={filter === "internal"}
              onClick={() => setFilter("internal")}
              label="inside a cluster"
              count={counts.internal}
              tone="rose"
            />
            <FilterChip
              active={filter === "cross"}
              onClick={() => setFilter("cross")}
              label="across clusters"
              count={counts.cross}
              tone="violet"
            />
          </div>
          {report && (
            <div className="text-[11px] font-mono text-ink-400">
              <span className="text-ink-200">{report.candidate_count}</span>{" "}
              close pairs ·{" "}
              <span className="text-ink-200">
                {report.total_pairs_scanned}
              </span>{" "}
              total · floor {(report.floor * 100).toFixed(0)}%
            </div>
          )}
        </div>

        {/* Body */}
        <div className="overflow-y-auto px-6 py-5 space-y-4">
          {loading && <LoadingState />}
          {!loading && error && (
            <div className="rounded-xl bg-rose-500/10 ring-1 ring-rose-500/30 p-4 text-sm text-rose-200">
              {error}
            </div>
          )}
          {!loading && !error && report && report.tension_count === 0 && (
            <EmptyState />
          )}
          {!loading &&
            !error &&
            report &&
            filtered.length === 0 &&
            report.tension_count > 0 && (
              <div className="text-xs text-ink-400 font-mono">
                no tensions match this filter
              </div>
            )}
          {!loading &&
            !error &&
            filtered.map((t) => (
              <TensionCard
                key={`${t.a_id}-${t.b_id}`}
                tension={t}
                onOpenNote={openNote}
                onReconcile={() => reconcile(t)}
              />
            ))}
        </div>

        <div className="px-6 py-3 border-t border-white/5 bg-ink-800/60 text-[11px] font-mono text-ink-400 flex items-center justify-between">
          <span>
            magnitude = cosine × (1 + Σ signal weights), capped at 1 ·{" "}
            <span className="text-ink-300">esc</span> to close
          </span>
          <span>
            built on{" "}
            <span className="text-rose-300">
              polarity · antonyms · contrast · title-clash
            </span>
          </span>
        </div>
      </div>
    </div>
  );
}

function FilterChip({
  active,
  onClick,
  label,
  count,
  tone = "rose",
}: {
  active: boolean;
  onClick: () => void;
  label: string;
  count: number;
  tone?: "rose" | "violet";
}) {
  const accent =
    tone === "rose"
      ? "ring-rose-400/50 text-rose-200 bg-rose-500/15"
      : "ring-synapse-violet/40 text-synapse-violet bg-synapse-violet/15";
  return (
    <button
      onClick={onClick}
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 ring-1 transition ${
        active
          ? accent
          : "ring-white/10 text-ink-300 bg-white/[0.02] hover:text-ink-100 hover:ring-white/20"
      }`}
    >
      <span>{label}</span>
      <span className={active ? "text-ink-100" : "text-ink-400"}>{count}</span>
    </button>
  );
}

function TensionCard({
  tension: t,
  onOpenNote,
  onReconcile,
}: {
  tension: Tension;
  onOpenNote: (id: number, title: string) => void;
  onReconcile: () => void;
}) {
  const magPct = Math.round(t.magnitude * 100);
  const cosPct = Math.round(t.cosine * 100);
  const accent = t.kind === "internal" ? "#f43f5e" : "#a855f7";

  return (
    <article
      className="rounded-2xl bg-white/[0.025] ring-1 ring-white/10 shadow-card overflow-hidden hover:ring-white/20 transition"
      style={{
        background: `linear-gradient(180deg, ${accent}0a, transparent 35%), rgba(255,255,255,0.025)`,
      }}
    >
      {/* Magnitude meter */}
      <div className="relative h-1.5 bg-white/[0.04]">
        <div
          className="absolute inset-y-0 left-0"
          style={{
            width: `${magPct}%`,
            background: `linear-gradient(90deg, ${accent}, #fb7185)`,
            boxShadow: `0 0 12px ${accent}55`,
          }}
        />
      </div>

      <div className="p-4">
        {/* Headline row: title A ⟷ title B with magnitude badge */}
        <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-3 mb-3">
          <button
            onClick={() => onOpenNote(t.a_id, t.a_title)}
            className="text-left group min-w-0"
            title={t.a_title}
          >
            <div className="text-sm font-semibold text-ink-100 group-hover:text-rose-200 truncate transition">
              {t.a_title}
            </div>
            {t.cluster_a_name && (
              <div
                className="text-[10px] font-mono uppercase tracking-[0.14em] mt-0.5 inline-flex items-center gap-1"
                style={{ color: t.cluster_a_color ?? "#94a3b8" }}
              >
                <span
                  className="w-1.5 h-1.5 rounded-full inline-block"
                  style={{ background: t.cluster_a_color ?? "#94a3b8" }}
                />
                {t.cluster_a_name}
              </div>
            )}
          </button>

          <div className="flex flex-col items-center gap-0.5 px-3">
            <div
              className="text-[10px] font-mono uppercase tracking-[0.18em]"
              style={{ color: accent }}
            >
              {t.kind === "internal" ? "inside" : "across"}
            </div>
            <div className="text-lg leading-none" style={{ color: accent }}>
              ⟷
            </div>
            <div className="text-[11px] font-mono text-ink-100">
              <span className="text-ink-100">{magPct}%</span>
              <span className="text-ink-400"> · cos {cosPct}%</span>
            </div>
          </div>

          <button
            onClick={() => onOpenNote(t.b_id, t.b_title)}
            className="text-right group min-w-0"
            title={t.b_title}
          >
            <div className="text-sm font-semibold text-ink-100 group-hover:text-rose-200 truncate transition">
              {t.b_title}
            </div>
            {t.cluster_b_name && (
              <div
                className="text-[10px] font-mono uppercase tracking-[0.14em] mt-0.5 inline-flex items-center gap-1 justify-end"
                style={{ color: t.cluster_b_color ?? "#94a3b8" }}
              >
                {t.cluster_b_name}
                <span
                  className="w-1.5 h-1.5 rounded-full inline-block"
                  style={{ background: t.cluster_b_color ?? "#94a3b8" }}
                />
              </div>
            )}
          </button>
        </div>

        {/* Signal pills */}
        {t.signals.length > 0 && (
          <div className="flex flex-wrap gap-1.5 mb-3">
            {t.signals.map((s, i) => (
              <span
                key={`${s.kind}-${i}`}
                className="inline-flex items-center gap-1 rounded-full bg-white/[0.04] ring-1 ring-white/10 px-2 py-0.5 font-mono text-[10px] text-ink-200"
                title={`weight ${s.weight}`}
              >
                <span style={{ color: accent }} className="text-[11px] leading-none">
                  {KIND_GLYPH[s.kind]}
                </span>
                <span className="text-ink-300">{KIND_LABEL[s.kind]}</span>
                <span className="text-ink-100">{s.detail}</span>
              </span>
            ))}
          </div>
        )}

        {/* Evidence: one quote per side, with polarity arrow */}
        <div className="grid sm:grid-cols-2 gap-3 mb-3">
          {t.evidence.map((ev, i) => (
            <EvidenceBlock
              key={`${ev.note_id}-${i}`}
              evidence={ev}
              accent={accent}
              align={i === 0 ? "left" : "right"}
              onClick={() => onOpenNote(ev.note_id, ev.title)}
            />
          ))}
        </div>

        {/* Bridge prompt + Reconcile button */}
        <div className="rounded-xl bg-ink-900/50 ring-1 ring-white/[0.06] p-3 flex items-start gap-3">
          <div className="flex-1 min-w-0">
            <div className="text-[10px] font-mono uppercase tracking-[0.16em] text-synapse-cyan mb-1">
              suggested bridge
            </div>
            <div className="text-sm text-ink-100 mb-1 truncate">
              {t.bridge_title}
            </div>
            <p className="text-xs text-ink-300 line-clamp-2">
              {t.bridge_prompt}
            </p>
          </div>
          <button
            onClick={onReconcile}
            className="shrink-0 inline-flex items-center gap-1.5 rounded-lg px-3 py-2 text-xs font-medium text-ink-900 bg-gradient-to-r from-synapse-cyan to-synapse-violet hover:brightness-110 shadow-glow transition"
            title="Open the composer with this draft pre-filled"
          >
            ⤴ Reconcile
          </button>
        </div>
      </div>
    </article>
  );
}

function EvidenceBlock({
  evidence,
  accent,
  align,
  onClick,
}: {
  evidence: { note_id: number; title: string; sentence: string; polarity: number };
  accent: string;
  align: "left" | "right";
  onClick: () => void;
}) {
  const arrow =
    evidence.polarity > 0 ? "↑" : evidence.polarity < 0 ? "↓" : "·";
  const arrowColor =
    evidence.polarity > 0
      ? "#a3e635"
      : evidence.polarity < 0
        ? "#fb7185"
        : "#8a95bf";
  return (
    <button
      onClick={onClick}
      className={`group text-${align} rounded-xl bg-white/[0.025] ring-1 ring-white/[0.06] hover:ring-white/20 p-3 transition`}
    >
      <div className="flex items-start gap-2 mb-1">
        <span
          className="text-base leading-none mt-0.5"
          style={{ color: arrowColor }}
          aria-hidden
        >
          {arrow}
        </span>
        <div className="flex-1 min-w-0">
          <div className="text-[10px] font-mono uppercase tracking-[0.14em] text-ink-300 group-hover:text-ink-200 truncate">
            {evidence.title}
          </div>
        </div>
      </div>
      <p
        className="text-xs leading-relaxed text-ink-100 italic"
        style={{ borderLeft: `2px solid ${accent}66`, paddingLeft: "0.5rem" }}
      >
        “{evidence.sentence}”
      </p>
    </button>
  );
}

function TensionGlyph() {
  return (
    <div className="relative w-9 h-9 shrink-0">
      <svg viewBox="0 0 40 40" className="w-full h-full">
        <defs>
          <linearGradient id="tg" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="#f43f5e" />
            <stop offset="100%" stopColor="#a855f7" />
          </linearGradient>
        </defs>
        <circle cx="10" cy="20" r="5" fill="#f43f5e" />
        <circle cx="30" cy="20" r="5" fill="#a855f7" />
        {/* Jagged disagreement line between them */}
        <path
          d="M15 20 L18 14 L22 26 L25 20"
          stroke="url(#tg)"
          strokeWidth="2"
          fill="none"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
      <div className="absolute inset-0 rounded-full shadow-glow pointer-events-none" />
    </div>
  );
}

function LoadingState() {
  return (
    <div className="space-y-3">
      {[0, 1, 2].map((i) => (
        <div
          key={i}
          className="rounded-2xl bg-white/[0.02] ring-1 ring-white/10 h-32 overflow-hidden relative"
        >
          <div
            className="absolute inset-y-0 w-1/3 bg-gradient-to-r from-transparent via-white/[0.06] to-transparent"
            style={{
              animation: "ws-shimmer 1.6s ease-in-out infinite",
              animationDelay: `${i * 0.15}s`,
            }}
          />
        </div>
      ))}
    </div>
  );
}

function EmptyState() {
  return (
    <div className="rounded-2xl bg-white/[0.025] ring-1 ring-white/10 p-8 text-center">
      <div className="inline-flex items-center justify-center w-12 h-12 rounded-full bg-gradient-to-br from-synapse-lime/20 to-synapse-cyan/20 ring-1 ring-synapse-lime/40 mb-3">
        <span className="text-2xl text-synapse-lime">✓</span>
      </div>
      <div className="text-base text-ink-100 font-semibold mb-1">
        Your second brain is in harmony
      </div>
      <p className="text-xs text-ink-300 leading-relaxed max-w-md mx-auto">
        No semantically-close pairs disagree with each other at the
        current floor. Either your beliefs are unusually coherent, or you
        haven&apos;t written enough opinionated atoms yet. Add more, then
        come back.
      </p>
    </div>
  );
}
