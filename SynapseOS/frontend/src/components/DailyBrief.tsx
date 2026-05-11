"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Brief, BriefPick, BriefReasonKind, GraphNode } from "@/lib/types";

type Props = {
  open: boolean;
  onClose: () => void;
  /** Called when the user clicks "Open in graph" or a connection chip. */
  onSelectNote: (node: Pick<GraphNode, "id" | "title" | "body" | "tags" | "degree" | "weight">) => void;
  /** Called whenever a pick is "marked seen" — the page can refresh its
   *  picks or invalidate the badge. */
  onTouchedAny?: () => void;
};

/**
 * Daily Brief — your second brain, on a rotation.
 *
 * The brief surfaces notes the revisit engine thinks you should
 * re-engage with: stale-but-central thoughts, isolated orphans, and
 * notes whose cluster you haven't visited in a while. Each pick comes
 * with a one-line journal prompt and a couple of *cross-cluster*
 * connection suggestions — bridges the graph hasn't drawn yet.
 *
 * Visual layout: a centered modal with a carousel of cards. One card
 * at a time keeps the page focused — the brief is meant to *replace*
 * scrolling, not add another scroll surface.
 */
export function DailyBrief({ open, onClose, onSelectNote, onTouchedAny }: Props) {
  const [brief, setBrief] = useState<Brief | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [idx, setIdx] = useState(0);
  const [touched, setTouched] = useState<Set<number>>(new Set());
  const [animKey, setAnimKey] = useState(0);

  // Load the brief whenever the modal opens.
  useEffect(() => {
    if (!open) return;
    setLoading(true);
    setError(null);
    setIdx(0);
    setTouched(new Set());
    api
      .brief({ k: 5 })
      .then((b) => {
        setBrief(b);
        setAnimKey((k) => k + 1);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "failed to load brief"))
      .finally(() => setLoading(false));
  }, [open]);

  // Keyboard nav while the modal is open.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if (e.key === "ArrowRight") setIdx((i) => Math.min(i + 1, (brief?.picks.length ?? 1) - 1));
      if (e.key === "ArrowLeft") setIdx((i) => Math.max(i - 1, 0));
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, brief, onClose]);

  const picks = brief?.picks ?? [];
  const current = picks[idx];

  const handleTouch = useCallback(
    async (noteId: number) => {
      try {
        await api.touchNote(noteId);
      } catch {
        // best-effort — touch is a UX nicety, not a correctness gate.
      }
      setTouched((prev) => {
        const next = new Set(prev);
        next.add(noteId);
        return next;
      });
      // Remember the brief was attended to today so the header pill can
      // drop its "new" indicator.
      try {
        localStorage.setItem(
          "synapseos:lastBriefSeen",
          brief?.date ?? new Date().toISOString().slice(0, 10),
        );
      } catch {}
      onTouchedAny?.();
    },
    [brief?.date, onTouchedAny],
  );

  const goPrev = () => setIdx((i) => Math.max(0, i - 1));
  const goNext = () => setIdx((i) => Math.min(picks.length - 1, i + 1));

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center px-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="brief-title"
    >
      {/* Backdrop with same radial palette as the page. */}
      <div
        className="absolute inset-0 bg-ink-900/80 backdrop-blur-md"
        onClick={onClose}
      />
      <div className="absolute inset-0 pointer-events-none bg-grid-fade opacity-60" />

      <div
        key={animKey}
        className="relative w-full max-w-3xl rounded-2xl bg-ink-800/90 ring-1 ring-white/10 shadow-card overflow-hidden animate-fade-in"
      >
        {/* Header strip with date + close. */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-white/5 bg-gradient-to-r from-synapse-violet/[0.06] via-transparent to-synapse-cyan/[0.06]">
          <div className="flex items-center gap-3">
            <BriefLogo />
            <div>
              <div
                id="brief-title"
                className="text-base font-semibold tracking-tight text-ink-100"
              >
                Daily Brief
              </div>
              <div className="text-[11px] font-mono text-ink-300">
                {brief ? prettyDate(brief.date) : "loading…"}
                {brief && brief.picks.length > 0 && (
                  <>
                    {" · "}
                    <span className="text-synapse-cyan">
                      {idx + 1}/{brief.picks.length}
                    </span>
                  </>
                )}
                {brief?.stats?.clusters_touched != null && (
                  <>
                    {" · "}across {brief.stats.clusters_touched} clusters
                  </>
                )}
              </div>
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-ink-300 hover:text-ink-100 text-xs font-mono px-2 py-1 rounded ring-1 ring-white/10 hover:ring-synapse-pink/40 transition"
            aria-label="close"
          >
            esc
          </button>
        </div>

        <div className="px-6 py-6 min-h-[460px]">
          {loading && <BriefSkeleton />}
          {error && !loading && (
            <div className="text-sm font-mono text-synapse-pink">
              {error} — start the backend with{" "}
              <span className="text-ink-100">uvicorn app.main:app --reload</span>
            </div>
          )}
          {!loading && !error && picks.length === 0 && <EmptyState />}
          {!loading && !error && current && (
            <PickCard
              pick={current}
              touched={touched.has(current.note_id)}
              onTouch={() => handleTouch(current.note_id)}
              onOpen={(id) => {
                const c = picks.find((p) => p.note_id === id);
                if (c) {
                  onSelectNote({
                    id: c.note_id,
                    title: c.title,
                    body: c.snippet,
                    tags: c.tags,
                    degree: 0,
                    weight: 0,
                  });
                }
                handleTouch(id);
                onClose();
              }}
              onConnection={(id, title) => {
                onSelectNote({
                  id,
                  title,
                  body: "",
                  tags: [],
                  degree: 0,
                  weight: 0,
                });
                onClose();
              }}
            />
          )}
        </div>

        {/* Footer: prev / pager dots / next + "mark all seen". */}
        {!loading && !error && picks.length > 0 && (
          <div className="flex items-center justify-between px-6 py-4 border-t border-white/5">
            <button
              onClick={goPrev}
              disabled={idx === 0}
              className="px-3 py-1.5 rounded-md text-xs font-mono ring-1 ring-white/10 text-ink-200 hover:text-ink-100 hover:ring-synapse-violet/40 disabled:opacity-30 disabled:cursor-not-allowed transition"
            >
              ← prev
            </button>
            <div className="flex items-center gap-1.5">
              {picks.map((p, i) => (
                <button
                  key={p.note_id}
                  onClick={() => setIdx(i)}
                  aria-label={`pick ${i + 1}`}
                  className={`w-2 h-2 rounded-full transition ${
                    i === idx
                      ? "bg-synapse-cyan shadow-[0_0_8px_rgba(34,211,238,0.7)]"
                      : touched.has(p.note_id)
                        ? "bg-synapse-lime/70"
                        : "bg-white/15 hover:bg-white/35"
                  }`}
                />
              ))}
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={async () => {
                  // Mark every remaining pick as seen in parallel.
                  await Promise.all(
                    picks
                      .filter((p) => !touched.has(p.note_id))
                      .map((p) => handleTouch(p.note_id)),
                  );
                }}
                className="px-3 py-1.5 rounded-md text-xs font-mono ring-1 ring-synapse-lime/40 text-synapse-lime hover:bg-synapse-lime/10 transition"
              >
                mark all seen
              </button>
              <button
                onClick={goNext}
                disabled={idx === picks.length - 1}
                className="px-3 py-1.5 rounded-md text-xs font-mono ring-1 ring-white/10 text-ink-200 hover:text-ink-100 hover:ring-synapse-violet/40 disabled:opacity-30 disabled:cursor-not-allowed transition"
              >
                next →
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// --------------------------------------------------------------- card

function PickCard({
  pick,
  touched,
  onTouch,
  onOpen,
  onConnection,
}: {
  pick: BriefPick;
  touched: boolean;
  onTouch: () => void;
  onOpen: (id: number) => void;
  onConnection: (id: number, title: string) => void;
}) {
  return (
    <div className="animate-fade-in space-y-5">
      {/* Cluster + score ring header */}
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-center gap-2 flex-wrap min-w-0">
          {pick.cluster_name && (
            <span
              className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 font-mono text-[11px] ring-1"
              style={{
                color: pick.cluster_color ?? "#a855f7",
                borderColor: `${pick.cluster_color ?? "#a855f7"}55`,
                background: `${pick.cluster_color ?? "#a855f7"}10`,
              }}
            >
              <span
                className="w-1.5 h-1.5 rounded-full"
                style={{ background: pick.cluster_color ?? "#a855f7" }}
              />
              {pick.cluster_name}
            </span>
          )}
          {pick.is_orphan && (
            <span className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 font-mono text-[11px] ring-1 ring-synapse-amber/40 text-synapse-amber bg-synapse-amber/10">
              <span className="w-1.5 h-1.5 rounded-full bg-synapse-amber animate-pulse-slow" />
              orphan
            </span>
          )}
          {touched && (
            <span className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 font-mono text-[11px] ring-1 ring-synapse-lime/40 text-synapse-lime bg-synapse-lime/10">
              ✓ seen
            </span>
          )}
        </div>
        <ScoreRing value={pick.score} color={pick.cluster_color ?? "#a855f7"} />
      </div>

      {/* Title + body excerpt */}
      <div>
        <h3 className="text-xl font-semibold tracking-tight text-ink-100 leading-tight">
          {pick.title}
        </h3>
        <p className="mt-2 text-sm leading-relaxed text-ink-200">{pick.snippet}</p>
        {pick.tags.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-1.5">
            {pick.tags.map((t) => (
              <span
                key={t}
                className="font-mono text-[10px] text-ink-300 ring-1 ring-white/5 rounded px-1.5 py-0.5"
              >
                #{t}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* Reasons strip */}
      <div className="flex flex-wrap gap-1.5">
        {pick.reasons.map((r, i) => (
          <ReasonPill key={`${r.kind}-${i}`} kind={r.kind} text={r.text} />
        ))}
      </div>

      {/* Journal prompt */}
      <div className="rounded-xl bg-white/[0.02] ring-1 ring-synapse-violet/25 p-4 relative overflow-hidden">
        <div className="absolute -top-8 -right-8 w-32 h-32 rounded-full bg-synapse-violet/10 blur-2xl pointer-events-none" />
        <div className="relative">
          <div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-synapse-violet mb-1.5">
            ponder this
          </div>
          <p className="text-sm leading-relaxed text-ink-100 italic">
            “{pick.prompt}”
          </p>
        </div>
      </div>

      {/* Connection suggestions */}
      {pick.connections.length > 0 && (
        <div>
          <div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-ink-300 mb-2">
            bridges to consider
          </div>
          <ul className="space-y-1.5">
            {pick.connections.map((c) => (
              <li
                key={c.note_id}
                className="flex items-center gap-2 rounded-lg ring-1 ring-white/5 bg-white/[0.015] px-3 py-2"
              >
                <span className="text-ink-400 text-sm shrink-0">↝</span>
                <button
                  onClick={() => onConnection(c.note_id, c.title)}
                  className="flex-1 text-left text-sm text-ink-100 truncate hover:text-synapse-cyan transition"
                  title={c.title}
                >
                  {c.title}
                </button>
                {c.cluster_name && (
                  <span className="text-[10px] font-mono text-ink-400 shrink-0">
                    via {c.cluster_name}
                  </span>
                )}
                <span className="text-[11px] font-mono text-synapse-cyan/90 shrink-0">
                  {(c.strength * 100).toFixed(0)}%
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* CTAs */}
      <div className="flex items-center gap-2 pt-2">
        <button
          onClick={() => onOpen(pick.note_id)}
          className="px-3 py-2 rounded-md text-xs font-mono bg-synapse-cyan/15 text-synapse-cyan ring-1 ring-synapse-cyan/40 hover:bg-synapse-cyan/25 transition"
        >
          open in graph →
        </button>
        <button
          onClick={onTouch}
          disabled={touched}
          className={`px-3 py-2 rounded-md text-xs font-mono ring-1 transition ${
            touched
              ? "ring-synapse-lime/30 text-synapse-lime/70 cursor-default"
              : "ring-white/10 text-ink-200 hover:text-synapse-lime hover:ring-synapse-lime/40"
          }`}
        >
          {touched ? "marked seen" : "mark seen"}
        </button>
        <span className="ml-auto font-mono text-[10px] text-ink-400">
          {pick.days_since_seen == null
            ? "never re-read"
            : pick.days_since_seen === 0
              ? "touched today"
              : `${pick.days_since_seen}d since touched`}
        </span>
      </div>
    </div>
  );
}

// --------------------------------------------------------------- bits

function ReasonPill({ kind, text }: { kind: BriefReasonKind; text: string }) {
  const style = {
    stale: "ring-synapse-amber/40 text-synapse-amber bg-synapse-amber/10",
    central: "ring-synapse-violet/40 text-synapse-violet bg-synapse-violet/10",
    orphan: "ring-synapse-pink/40 text-synapse-pink bg-synapse-pink/10",
    diverse: "ring-synapse-cyan/40 text-synapse-cyan bg-synapse-cyan/10",
  }[kind];
  const glyph = {
    stale: "◷",
    central: "✦",
    orphan: "○",
    diverse: "⤬",
  }[kind];
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 font-mono text-[11px] ring-1 ${style}`}
    >
      <span aria-hidden>{glyph}</span>
      {text}
    </span>
  );
}

function ScoreRing({ value, color }: { value: number; color: string }) {
  // value is the composite revisit score, typically in [0, 1.0]+ but
  // we'll clamp to a visual range of [0, 0.85] before painting so a
  // mid-pack pick still reads as "non-trivial."
  const pct = Math.max(0.05, Math.min(0.95, (value + 0.05) / 0.9));
  const deg = Math.round(pct * 360);
  return (
    <div
      className="relative w-14 h-14 rounded-full shrink-0"
      style={{
        background: `conic-gradient(${color} ${deg}deg, rgba(255,255,255,0.06) ${deg}deg)`,
      }}
      aria-label={`revisit score ${value.toFixed(2)}`}
    >
      <div className="absolute inset-[3px] rounded-full bg-ink-800 flex items-center justify-center">
        <span className="font-mono text-[11px] text-ink-100">
          {Math.round(value * 100)}
        </span>
      </div>
    </div>
  );
}

function BriefSkeleton() {
  return (
    <div className="space-y-4 animate-fade-in">
      <div className="h-7 w-1/2 rounded bg-white/[0.04]" />
      <div className="h-4 w-3/4 rounded bg-white/[0.03]" />
      <div className="h-4 w-2/3 rounded bg-white/[0.03]" />
      <div className="h-20 w-full rounded-xl bg-white/[0.025] ring-1 ring-white/5" />
      <div className="h-10 w-full rounded-lg bg-white/[0.02]" />
      <div className="h-10 w-full rounded-lg bg-white/[0.02]" />
    </div>
  );
}

function EmptyState() {
  return (
    <div className="text-center py-12 space-y-2">
      <div className="text-3xl">∅</div>
      <p className="text-sm text-ink-200">No notes to surface yet.</p>
      <p className="text-[11px] text-ink-400">
        Add a handful of thoughts; the brief turns on automatically.
      </p>
    </div>
  );
}

function BriefLogo() {
  return (
    <div className="relative w-9 h-9">
      <svg viewBox="0 0 36 36" className="w-full h-full">
        <defs>
          <linearGradient id="bl" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="#fbbf24" />
            <stop offset="100%" stopColor="#a855f7" />
          </linearGradient>
        </defs>
        <circle cx="18" cy="18" r="14" fill="none" stroke="url(#bl)" strokeWidth="1.2" />
        <circle cx="18" cy="18" r="2.5" fill="url(#bl)" />
        <g stroke="url(#bl)" strokeWidth="0.6" opacity="0.85">
          <line x1="18" y1="18" x2="6" y2="10" />
          <line x1="18" y1="18" x2="30" y2="10" />
          <line x1="18" y1="18" x2="18" y2="32" />
        </g>
        <circle cx="6" cy="10" r="1.5" fill="#fbbf24" />
        <circle cx="30" cy="10" r="1.5" fill="#a855f7" />
        <circle cx="18" cy="32" r="1.5" fill="#22d3ee" />
      </svg>
    </div>
  );
}

// --------------------------------------------------------------- util

function prettyDate(d: string): string {
  // YYYY-MM-DD → "May 11, 2026"
  try {
    const dt = new Date(`${d}T00:00:00Z`);
    return dt.toLocaleDateString(undefined, {
      year: "numeric",
      month: "long",
      day: "numeric",
      timeZone: "UTC",
    });
  } catch {
    return d;
  }
}

