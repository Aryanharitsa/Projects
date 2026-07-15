"use client";

import { forwardRef, useCallback, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { api } from "@/lib/api";
import type {
  CompassCitation,
  CompassLens,
  CompassQuestionSummary,
  CompassSubquestion,
  GraphNode,
  LensNote,
} from "@/lib/types";

type Props = {
  open: boolean;
  onClose: () => void;
  /** Jump the canvas onto a note (closes the modal). */
  onSelectNote: (stub: GraphNode) => void;
};

/**
 * Compass — question-anchored lens & research session.
 *
 * Every other surface in SynapseOS is observational (Atlas, Pulse,
 * Chronicle, Tensions, Echo, Synthesis) or generative-writing (Spark,
 * Distill). Compass is **generative-reading**: pin a question, get a
 * relevance-ranked reading queue across the entire vault, mark notes
 * as read for *this* question, watch the citation-stitched working
 * answer grow beneath you, and track coverage as a mass-weighted ring.
 *
 * Left rail: every persisted question, each with its own coverage %.
 * Right panel: the active lens — coverage ring, sub-questions,
 * working answer with [n] citations, frontiers ("next 3 to read"),
 * and the full ranked queue with mark-as-read controls.
 *
 * All computation is deterministic and extractive — every cited line
 * is verbatim from one of the user's own notes, every coverage number
 * is reproducible from `(question, reads)`.
 */
type CompassPropsWithSignal = Props & {
  /** Compass-selected question id to focus on open (from Signal → open in Compass). */
  focusQuestionId?: number | null;
  /** Called after any signal watch mutation so the parent can refresh badges. */
  onSignalMutated?: () => void;
};

export function Compass({
  open,
  onClose,
  onSelectNote,
  focusQuestionId,
  onSignalMutated,
}: CompassPropsWithSignal) {
  const [questions, setQuestions] = useState<CompassQuestionSummary[]>([]);
  const [activeId, setActiveId] = useState<number | null>(null);
  const [lens, setLens] = useState<CompassLens | null>(null);
  const [loadingList, setLoadingList] = useState(false);
  const [loadingLens, setLoadingLens] = useState(false);
  const [draft, setDraft] = useState("");
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<"all" | "unread" | "read">("all");
  const [busyNoteId, setBusyNoteId] = useState<number | null>(null);
  const [pinnedIds, setPinnedIds] = useState<Set<number>>(new Set());
  const [watchBusy, setWatchBusy] = useState(false);

  const refreshList = useCallback(async (preferredId?: number | null) => {
    setLoadingList(true);
    setError(null);
    try {
      const qs = await api.compassQuestions();
      setQuestions(qs);
      // Pick an active question: prefer the explicit hint, else the
      // currently-active one if still present, else the newest.
      setActiveId((prev) => {
        if (preferredId !== undefined && preferredId !== null) return preferredId;
        if (prev !== null && qs.some((q) => q.id === prev)) return prev;
        return qs.length > 0 ? qs[0].id : null;
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : "failed to load questions");
    } finally {
      setLoadingList(false);
    }
  }, []);

  const loadLens = useCallback(async (id: number) => {
    setLoadingLens(true);
    setError(null);
    try {
      const l = await api.compassLens(id);
      setLens(l);
    } catch (e) {
      setError(e instanceof Error ? e.message : "failed to load lens");
      setLens(null);
    } finally {
      setLoadingLens(false);
    }
  }, []);

  const refreshPinnedIds = useCallback(async () => {
    try {
      const r = await api.signalPinnedIds();
      setPinnedIds(new Set(r.question_ids));
    } catch {
      /* pin toggle is a nice-to-have — don't error the modal on failure */
    }
  }, []);

  useEffect(() => {
    if (!open) return;
    refreshList();
    refreshPinnedIds();
  }, [open, refreshList, refreshPinnedIds]);

  // Signal → "open in Compass" hands over a question id to jump to.
  useEffect(() => {
    if (!open) return;
    if (focusQuestionId != null) setActiveId(focusQuestionId);
  }, [open, focusQuestionId]);

  useEffect(() => {
    if (!open || activeId === null) {
      setLens(null);
      return;
    }
    loadLens(activeId);
  }, [open, activeId, loadLens]);

  const handleWatchToggle = useCallback(async () => {
    if (activeId === null) return;
    setWatchBusy(true);
    try {
      if (pinnedIds.has(activeId)) {
        await api.signalUnwatch(activeId);
      } else {
        await api.signalWatch(activeId);
      }
      await refreshPinnedIds();
      onSignalMutated?.();
    } catch (e) {
      setError(e instanceof Error ? e.message : "watch toggle failed");
    } finally {
      setWatchBusy(false);
    }
  }, [activeId, pinnedIds, refreshPinnedIds, onSignalMutated]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  const handleCreate = useCallback(async () => {
    const text = draft.trim();
    if (text.length < 3) return;
    setCreating(true);
    setError(null);
    try {
      const newLens = await api.compassCreate(text);
      setDraft("");
      setLens(newLens);
      setActiveId(newLens.question_id);
      // Refresh the rail so the new question shows up with its summary.
      const qs = await api.compassQuestions();
      setQuestions(qs);
    } catch (e) {
      setError(e instanceof Error ? e.message : "failed to create question");
    } finally {
      setCreating(false);
    }
  }, [draft]);

  const handleMarkRead = useCallback(
    async (noteId: number) => {
      if (activeId === null) return;
      setBusyNoteId(noteId);
      try {
        const updated = await api.compassMarkRead(activeId, noteId);
        setLens(updated);
        // Patch the rail's coverage without a full refetch.
        setQuestions((prev) =>
          prev.map((q) =>
            q.id === activeId
              ? {
                  ...q,
                  reads_count: updated.stats.read_in_lens ?? q.reads_count + 1,
                  coverage_pct: updated.coverage_pct,
                  last_read_at: updated.generated_at,
                }
              : q,
          ),
        );
      } catch (e) {
        setError(e instanceof Error ? e.message : "mark-read failed");
      } finally {
        setBusyNoteId(null);
      }
    },
    [activeId],
  );

  const handleUnmarkRead = useCallback(
    async (noteId: number) => {
      if (activeId === null) return;
      setBusyNoteId(noteId);
      try {
        const updated = await api.compassUnmarkRead(activeId, noteId);
        setLens(updated);
        setQuestions((prev) =>
          prev.map((q) =>
            q.id === activeId
              ? {
                  ...q,
                  reads_count: Math.max(0, q.reads_count - 1),
                  coverage_pct: updated.coverage_pct,
                }
              : q,
          ),
        );
      } catch (e) {
        setError(e instanceof Error ? e.message : "unmark-read failed");
      } finally {
        setBusyNoteId(null);
      }
    },
    [activeId],
  );

  const handleArchive = useCallback(
    async (id: number) => {
      if (!confirm("Delete this question and all its read markers?")) return;
      try {
        await api.compassDelete(id);
        await refreshList(id === activeId ? null : activeId);
        if (id === activeId) setLens(null);
      } catch (e) {
        setError(e instanceof Error ? e.message : "delete failed");
      }
    },
    [activeId, refreshList],
  );

  const filteredNotes: LensNote[] = useMemo(() => {
    if (!lens) return [];
    if (filter === "unread") return lens.notes.filter((n) => !n.read);
    if (filter === "read") return lens.notes.filter((n) => n.read);
    return lens.notes;
  }, [lens, filter]);

  const handleCitationClick = useCallback(
    (c: CompassCitation) => {
      onSelectNote({
        id: c.note_id,
        title: c.title,
        body: "",
        tags: [],
        degree: 0,
        weight: 0,
      } as GraphNode);
    },
    [onSelectNote],
  );

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center px-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="compass-title"
    >
      <div
        className="absolute inset-0 bg-ink-900/82 backdrop-blur-md"
        onClick={onClose}
      />
      <div className="absolute inset-0 pointer-events-none bg-grid-fade opacity-60" />

      <div className="relative w-full max-w-[1280px] max-h-[94vh] flex flex-col rounded-2xl bg-ink-800/92 ring-1 ring-white/10 shadow-card overflow-hidden animate-fade-in">
        <CompassHeader
          lens={lens}
          loading={loadingLens}
          onClose={onClose}
          onRefresh={() => activeId !== null && loadLens(activeId)}
        />

        <div className="flex-1 overflow-hidden grid grid-cols-12 gap-0">
          {/* Left rail — saved questions + composer */}
          <aside className="col-span-12 md:col-span-4 lg:col-span-3 border-r border-white/5 bg-ink-900/40 overflow-y-auto p-4 space-y-4">
            <QuestionComposer
              value={draft}
              onChange={setDraft}
              onSubmit={handleCreate}
              busy={creating}
            />
            <QuestionList
              questions={questions}
              activeId={activeId}
              loading={loadingList}
              onSelect={setActiveId}
              onDelete={handleArchive}
            />
          </aside>

          {/* Right panel — active lens */}
          <section className="col-span-12 md:col-span-8 lg:col-span-9 overflow-y-auto">
            {error && (
              <div className="mx-6 mt-4 rounded-xl bg-rose-500/10 ring-1 ring-rose-400/40 p-3 text-xs font-mono text-rose-200">
                {error}
              </div>
            )}
            {activeId === null && !loadingLens && (
              <EmptyState />
            )}
            {activeId !== null && (loadingLens || !lens) && (
              <div className="grid place-items-center text-ink-300 font-mono text-xs h-64">
                <div className="flex items-center gap-3">
                  <CompassSpinner />
                  triangulating the lens …
                </div>
              </div>
            )}
            {activeId !== null && lens && !loadingLens && (
              <div className="p-6 space-y-6">
                <LensHeader
                  lens={lens}
                  watched={pinnedIds.has(lens.question_id)}
                  watchBusy={watchBusy}
                  onWatchToggle={handleWatchToggle}
                />
                <SubquestionsRow
                  subquestions={lens.subquestions}
                  onSelectNote={(noteId, title) =>
                    onSelectNote({
                      id: noteId,
                      title,
                      body: "",
                      tags: [],
                      degree: 0,
                      weight: 0,
                    } as GraphNode)
                  }
                />
                <WorkingAnswerCard
                  answer={lens.working_answer}
                  citations={lens.citations}
                  onCitationClick={handleCitationClick}
                />
                <FrontiersCard
                  frontiers={lens.frontiers}
                  onSelect={(n) =>
                    onSelectNote({
                      id: n.note_id,
                      title: n.title,
                      body: "",
                      tags: n.tags,
                      degree: 0,
                      weight: 0,
                    } as GraphNode)
                  }
                  onMarkRead={handleMarkRead}
                  busyNoteId={busyNoteId}
                />
                <QueueCard
                  notes={filteredNotes}
                  filter={filter}
                  total={lens.notes.length}
                  unreadCount={lens.notes.filter((n) => !n.read).length}
                  onFilter={setFilter}
                  onMarkRead={handleMarkRead}
                  onUnmarkRead={handleUnmarkRead}
                  busyNoteId={busyNoteId}
                  onSelect={(n) =>
                    onSelectNote({
                      id: n.note_id,
                      title: n.title,
                      body: "",
                      tags: n.tags,
                      degree: 0,
                      weight: 0,
                    } as GraphNode)
                  }
                />
              </div>
            )}
          </section>
        </div>

        <div className="border-t border-white/5 px-6 py-2 text-[10px] font-mono text-ink-400 flex items-center justify-between bg-ink-900/40">
          <span>
            compass · question-anchored lens · extractive working answer · press{" "}
            <span className="text-ink-200">esc</span> to close
          </span>
          {lens && (
            <a
              href={api.compassExportUrl(lens.question_id)}
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

function CompassHeader({
  lens,
  loading,
  onClose,
  onRefresh,
}: {
  lens: CompassLens | null;
  loading: boolean;
  onClose: () => void;
  onRefresh: () => void;
}) {
  return (
    <div
      className="flex items-center justify-between gap-4 px-6 py-4 border-b border-white/5"
      style={{
        background:
          "linear-gradient(90deg, rgba(34,211,238,0.18), rgba(168,85,247,0.12) 50%, rgba(251,191,36,0.10))",
      }}
    >
      <div className="flex items-center gap-3 min-w-0">
        <CompassGlyph />
        <div className="min-w-0">
          <div
            id="compass-title"
            className="text-base font-semibold tracking-tight text-ink-100 flex items-center gap-2"
          >
            Compass — question-anchored lens
            <span className="px-1.5 py-0.5 rounded-md bg-gradient-to-r from-synapse-cyan/30 to-synapse-violet/30 ring-1 ring-white/10 text-[9px] uppercase tracking-widest text-ink-100">
              new
            </span>
          </div>
          <div className="text-[11px] font-mono text-ink-300 uppercase tracking-[0.16em] mt-0.5">
            pin a question · vault re-ranks · read your way to an answer
          </div>
        </div>
      </div>
      <div className="flex items-center gap-2 shrink-0">
        {lens && (
          <a
            href={api.compassExportUrl(lens.question_id)}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1 rounded-full bg-white/[0.03] ring-1 ring-white/10 hover:ring-white/30 px-3 py-1 font-mono text-[11px] text-ink-300 hover:text-ink-100 transition"
            title="Export the current working answer + queue as Markdown"
          >
            ⤓ md
          </a>
        )}
        <button
          onClick={onRefresh}
          disabled={loading || !lens}
          className="inline-flex items-center gap-1 rounded-full bg-white/[0.03] ring-1 ring-white/10 hover:ring-white/30 px-3 py-1 font-mono text-[11px] text-ink-300 hover:text-ink-100 transition disabled:opacity-50"
          title="Recompute the lens against current graph state"
        >
          ↻ {loading ? "spinning" : "re-lens"}
        </button>
        <button
          onClick={onClose}
          className="text-ink-300 hover:text-ink-100 transition px-2"
          aria-label="close"
        >
          ✕
        </button>
      </div>
    </div>
  );
}

// ----------------------------------------------------------------- left rail

function QuestionComposer({
  value,
  onChange,
  onSubmit,
  busy,
}: {
  value: string;
  onChange: (v: string) => void;
  onSubmit: () => void;
  busy: boolean;
}) {
  return (
    <div className="rounded-xl bg-gradient-to-br from-synapse-cyan/12 to-synapse-violet/10 ring-1 ring-synapse-cyan/40 p-3">
      <label className="block text-[10px] uppercase tracking-[0.18em] text-ink-300 mb-1.5">
        pin a question
      </label>
      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
            e.preventDefault();
            onSubmit();
          }
        }}
        rows={3}
        placeholder="e.g. what makes a second brain compound over time?"
        className="w-full resize-none rounded-lg bg-ink-900/60 ring-1 ring-white/10 focus:ring-synapse-cyan/60 outline-none p-2 text-[12.5px] text-ink-100 placeholder:text-ink-400 leading-snug"
      />
      <div className="flex items-center justify-between mt-2">
        <span className="text-[10px] font-mono text-ink-400">⌘↵ to pin</span>
        <button
          onClick={onSubmit}
          disabled={busy || value.trim().length < 3}
          className={`inline-flex items-center gap-1 rounded-md px-3 py-1 font-mono text-[11px] transition ${
            busy || value.trim().length < 3
              ? "bg-white/[0.04] text-ink-400 ring-1 ring-white/10 cursor-not-allowed"
              : "bg-gradient-to-r from-synapse-cyan/35 to-synapse-violet/30 ring-1 ring-synapse-cyan/60 text-ink-100 hover:brightness-110"
          }`}
        >
          {busy ? "pinning…" : "✦ pin"}
        </button>
      </div>
    </div>
  );
}

function QuestionList({
  questions,
  activeId,
  loading,
  onSelect,
  onDelete,
}: {
  questions: CompassQuestionSummary[];
  activeId: number | null;
  loading: boolean;
  onSelect: (id: number) => void;
  onDelete: (id: number) => void;
}) {
  if (loading && questions.length === 0) {
    return (
      <div className="text-[11px] font-mono text-ink-400 px-1">loading…</div>
    );
  }
  if (questions.length === 0) {
    return (
      <div className="text-[11px] font-mono text-ink-400 px-1 leading-relaxed">
        No questions pinned yet. Compass is the persistent companion to Chat —
        pin one above and the entire vault re-ranks against it.
      </div>
    );
  }
  return (
    <div className="space-y-2">
      <div className="text-[10px] font-mono uppercase tracking-[0.16em] text-ink-400 px-1">
        active questions ({questions.length})
      </div>
      {questions.map((q) => {
        const active = q.id === activeId;
        return (
          <button
            key={q.id}
            onClick={() => onSelect(q.id)}
            className={`group w-full text-left rounded-xl p-3 transition ${
              active
                ? "bg-gradient-to-br from-synapse-cyan/12 to-synapse-violet/10 ring-1 ring-synapse-cyan/55 shadow-[0_0_28px_-12px_rgba(34,211,238,0.55)]"
                : "bg-white/[0.02] ring-1 ring-white/5 hover:ring-white/20"
            }`}
          >
            <div className="flex items-start justify-between gap-2">
              <div className="text-[12.5px] text-ink-100 leading-snug line-clamp-2">
                {q.text}
              </div>
              <span
                className="ml-1 opacity-0 group-hover:opacity-100 transition text-ink-400 hover:text-rose-300 text-xs shrink-0"
                onClick={(e) => {
                  e.stopPropagation();
                  onDelete(q.id);
                }}
                title="Delete question"
              >
                ✕
              </span>
            </div>
            <div className="flex items-center justify-between mt-2 text-[10px] font-mono text-ink-400">
              <CoverageBar pct={q.coverage_pct} active={active} />
              <span className="ml-2 shrink-0">
                {q.reads_count} read
              </span>
            </div>
          </button>
        );
      })}
    </div>
  );
}

function CoverageBar({ pct, active }: { pct: number; active: boolean }) {
  const safe = Math.max(0, Math.min(100, pct));
  return (
    <span className="flex-1 inline-flex items-center gap-1.5 min-w-0">
      <span className="flex-1 h-1 rounded-full bg-white/[0.06] overflow-hidden">
        <span
          className={`block h-full rounded-full transition-[width] duration-500 ${
            active
              ? "bg-gradient-to-r from-synapse-cyan to-synapse-violet"
              : "bg-gradient-to-r from-synapse-cyan/60 to-synapse-violet/60"
          }`}
          style={{ width: `${safe}%` }}
        />
      </span>
      <span className="text-ink-300 shrink-0 tabular-nums">
        {safe.toFixed(0)}%
      </span>
    </span>
  );
}

// ----------------------------------------------------------------- right header

function LensHeader({
  lens,
  watched,
  watchBusy,
  onWatchToggle,
}: {
  lens: CompassLens;
  watched: boolean;
  watchBusy: boolean;
  onWatchToggle: () => void;
}) {
  const inLens = lens.in_lens;
  const read = lens.stats.read_in_lens ?? 0;
  return (
    <div className="rounded-2xl bg-gradient-to-br from-synapse-cyan/10 via-synapse-violet/8 to-transparent ring-1 ring-white/8 p-5">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 mb-1.5">
            <span className="text-[10px] uppercase tracking-[0.18em] text-ink-400">
              researching
            </span>
            <button
              onClick={onWatchToggle}
              disabled={watchBusy}
              title={
                watched
                  ? "Unpin from Signal — stop tracking this question's delta"
                  : "Pin as Signal — track how your vault answers this question over time"
              }
              className={`inline-flex items-center gap-1 text-[10px] font-mono uppercase tracking-[0.14em] rounded-full ring-1 px-2 py-0.5 transition disabled:opacity-50 ${
                watched
                  ? "bg-synapse-lime/15 ring-synapse-lime/45 text-synapse-lime hover:ring-synapse-lime/80"
                  : "bg-white/[0.02] ring-white/10 text-ink-300 hover:ring-synapse-lime/40 hover:text-synapse-lime"
              }`}
              aria-pressed={watched}
            >
              <span aria-hidden>{watched ? "◉" : "◎"}</span>
              {watched ? "watching" : "watch"}
            </button>
          </div>
          <h2 className="text-xl lg:text-2xl font-semibold tracking-tight text-ink-100 leading-tight">
            {lens.question_text}
          </h2>
          <div className="mt-3 flex flex-wrap items-center gap-2 text-[11px] font-mono text-ink-300">
            <Pill label="in lens" value={`${inLens}/${lens.total_notes}`} />
            <Pill label="read" value={`${read}/${inLens}`} />
            <Pill
              label="frontiers"
              value={String(lens.frontiers.length)}
            />
            <Pill
              label="top relevance"
              value={(lens.stats.top_relevance ?? 0).toFixed(2)}
            />
            <Pill
              label="pinned"
              value={new Date(lens.created_at).toLocaleDateString(undefined, {
                month: "short",
                day: "numeric",
              })}
            />
          </div>
        </div>
        <CoverageRing pct={lens.coverage_pct} />
      </div>
    </div>
  );
}

function Pill({ label, value }: { label: string; value: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full bg-white/[0.03] ring-1 ring-white/8 px-2.5 py-1">
      <span className="opacity-70">{label}</span>
      <span className="text-ink-100">{value}</span>
    </span>
  );
}

function CoverageRing({ pct }: { pct: number }) {
  const safe = Math.max(0, Math.min(100, pct));
  const r = 32;
  const c = 2 * Math.PI * r;
  return (
    <div className="relative w-24 h-24 shrink-0" title={`coverage ${safe.toFixed(0)}%`}>
      <svg viewBox="0 0 80 80" className="w-full h-full -rotate-90">
        <defs>
          <linearGradient id="coverage-grad" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="#22d3ee" />
            <stop offset="100%" stopColor="#a855f7" />
          </linearGradient>
        </defs>
        <circle
          cx="40"
          cy="40"
          r={r}
          stroke="currentColor"
          strokeWidth={6}
          fill="none"
          className="text-white/[0.08]"
        />
        <circle
          cx="40"
          cy="40"
          r={r}
          stroke="url(#coverage-grad)"
          strokeWidth={6}
          strokeLinecap="round"
          fill="none"
          strokeDasharray={`${((safe / 100) * c).toFixed(2)} ${c.toFixed(2)}`}
          style={{ transition: "stroke-dasharray 600ms ease" }}
        />
      </svg>
      <div className="absolute inset-0 grid place-items-center">
        <div className="text-center">
          <div className="text-xl font-semibold text-ink-100 tabular-nums">
            {safe.toFixed(0)}
            <span className="text-xs text-ink-300">%</span>
          </div>
          <div className="text-[9px] font-mono uppercase tracking-widest text-ink-400">
            coverage
          </div>
        </div>
      </div>
    </div>
  );
}

// ----------------------------------------------------------------- subquestions

function SubquestionsRow({
  subquestions,
  onSelectNote,
}: {
  subquestions: CompassSubquestion[];
  onSelectNote: (noteId: number, title: string) => void;
}) {
  if (subquestions.length === 0) return null;
  return (
    <div className="rounded-xl bg-white/[0.02] ring-1 ring-white/5 p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="text-[10px] uppercase tracking-[0.18em] text-ink-300">
          sub-themes
        </div>
        <div className="text-[10px] font-mono text-ink-400">
          distinctive terms · per-term coverage
        </div>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        {subquestions.map((s) => (
          <button
            key={s.term}
            onClick={() => onSelectNote(s.sample_note_id, s.term)}
            className="text-left rounded-lg bg-gradient-to-br from-synapse-violet/12 to-synapse-cyan/8 ring-1 ring-synapse-violet/35 hover:ring-synapse-violet/65 p-3 transition group"
            title="Open the most-relevant note for this sub-theme"
          >
            <div className="flex items-center justify-between mb-1.5">
              <span className="text-[13px] text-ink-100 font-medium tracking-tight">
                {s.term}
              </span>
              <span
                className={`text-[10px] font-mono tabular-nums ${
                  s.coverage_pct >= 100
                    ? "text-synapse-lime"
                    : s.coverage_pct > 0
                      ? "text-synapse-cyan"
                      : "text-ink-400"
                }`}
              >
                {s.covered}/{s.note_count}
              </span>
            </div>
            <div className="h-1 rounded-full bg-white/[0.06] overflow-hidden">
              <div
                className="h-full rounded-full bg-gradient-to-r from-synapse-violet to-synapse-cyan transition-[width] duration-500"
                style={{ width: `${s.coverage_pct}%` }}
              />
            </div>
            <div className="mt-1.5 text-[10px] font-mono text-ink-400">
              {s.coverage_pct.toFixed(0)}% covered ·{" "}
              {s.coverage_pct >= 100
                ? "answered"
                : s.covered === 0
                  ? "untouched"
                  : "in progress"}
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}

// ----------------------------------------------------------------- working answer

type WorkingAnswerProps = {
  answer: string;
  citations: CompassCitation[];
  onCitationClick: (c: CompassCitation) => void;
};

const WorkingAnswerCard = forwardRef<HTMLDivElement, WorkingAnswerProps>(
  function WorkingAnswerCard(
    { answer, citations, onCitationClick }: WorkingAnswerProps,
    ref,
  ) {
    if (!answer) {
      return (
        <div
          ref={ref}
          className="rounded-2xl bg-white/[0.02] ring-1 ring-white/5 p-5"
        >
          <div className="text-[10px] uppercase tracking-[0.18em] text-ink-300 mb-2">
            working answer
          </div>
          <div className="text-[13px] text-ink-300 italic leading-relaxed">
            Mark a note as read from the frontiers below and an extractive
            answer will assemble here, one citation at a time, in relevance
            order. Every line is verbatim from your own notes — the compass
            quotes, it doesn&apos;t paraphrase.
          </div>
        </div>
      );
    }
    return (
      <div
        ref={ref}
        className="rounded-2xl bg-gradient-to-br from-synapse-cyan/10 via-synapse-violet/6 to-transparent ring-1 ring-synapse-cyan/30 p-5 shadow-[0_0_36px_-18px_rgba(34,211,238,0.6)]"
      >
        <div className="flex items-center justify-between mb-3">
          <div className="text-[10px] uppercase tracking-[0.18em] text-ink-300">
            working answer
          </div>
          <div className="text-[10px] font-mono text-ink-400">
            {citations.length} citation{citations.length === 1 ? "" : "s"} ·
            extractive · auditable
          </div>
        </div>
        <p className="text-[14px] text-ink-100 leading-relaxed">
          {renderAnswerWithCitations(answer, citations, onCitationClick)}
        </p>
        {citations.length > 0 && (
          <div className="mt-4 pt-3 border-t border-white/5 grid grid-cols-1 md:grid-cols-2 gap-2">
            {citations.map((c) => (
              <button
                key={c.ref}
                onClick={() => onCitationClick(c)}
                className="text-left rounded-lg bg-white/[0.02] ring-1 ring-white/5 hover:ring-white/20 p-2.5 transition"
              >
                <div className="flex items-baseline gap-2">
                  <span className="text-[10px] font-mono text-synapse-cyan tabular-nums">
                    [{c.ref}]
                  </span>
                  <span className="text-[12px] text-ink-100 font-medium tracking-tight truncate">
                    {c.title}
                  </span>
                  <span className="ml-auto text-[10px] font-mono text-ink-400 shrink-0">
                    {c.relevance.toFixed(2)}
                  </span>
                </div>
                <div className="text-[11px] text-ink-300 italic line-clamp-2 mt-0.5">
                  {c.excerpt}
                </div>
              </button>
            ))}
          </div>
        )}
      </div>
    );
  },
);

function renderAnswerWithCitations(
  answer: string,
  citations: CompassCitation[],
  onClick: (c: CompassCitation) => void,
): ReactNode[] {
  const byRef = new Map<number, CompassCitation>();
  for (const c of citations) byRef.set(c.ref, c);
  const re = /\[(\d+)\]/g;
  const out: ReactNode[] = [];
  let cursor = 0;
  let match: RegExpExecArray | null;
  let key = 0;
  while ((match = re.exec(answer)) !== null) {
    if (match.index > cursor) {
      out.push(answer.slice(cursor, match.index));
    }
    const ref = parseInt(match[1], 10);
    const c = byRef.get(ref);
    if (c) {
      out.push(
        <button
          key={`cit-${key++}`}
          onClick={() => onClick(c)}
          className="inline-flex items-center align-baseline mx-0.5 px-1.5 py-px rounded-md bg-synapse-cyan/20 ring-1 ring-synapse-cyan/40 hover:ring-synapse-cyan/80 text-[10px] font-mono text-synapse-cyan hover:text-ink-100 transition tabular-nums"
          title={c.title}
        >
          {ref}
        </button>,
      );
    } else {
      out.push(match[0]);
    }
    cursor = match.index + match[0].length;
  }
  if (cursor < answer.length) {
    out.push(answer.slice(cursor));
  }
  return out;
}

// ----------------------------------------------------------------- frontiers

function FrontiersCard({
  frontiers,
  onSelect,
  onMarkRead,
  busyNoteId,
}: {
  frontiers: LensNote[];
  onSelect: (n: LensNote) => void;
  onMarkRead: (noteId: number) => void;
  busyNoteId: number | null;
}) {
  if (frontiers.length === 0) {
    return (
      <div className="rounded-2xl bg-white/[0.02] ring-1 ring-white/5 p-5 text-center">
        <div className="text-[10px] uppercase tracking-[0.18em] text-ink-300 mb-2">
          frontiers
        </div>
        <div className="text-[12px] text-ink-300 italic">
          No un-read in-lens notes — you've covered every relevant slice.
        </div>
      </div>
    );
  }
  return (
    <div className="rounded-2xl bg-gradient-to-br from-synapse-amber/8 to-transparent ring-1 ring-synapse-amber/30 p-5">
      <div className="flex items-center justify-between mb-3">
        <div className="text-[10px] uppercase tracking-[0.18em] text-ink-300">
          frontiers · read next
        </div>
        <div className="text-[10px] font-mono text-ink-400">
          top {frontiers.length} un-read by info gain
        </div>
      </div>
      <ol className="space-y-2.5">
        {frontiers.map((n, i) => (
          <li
            key={n.note_id}
            className="rounded-xl bg-ink-900/40 ring-1 ring-white/5 hover:ring-white/15 p-3 transition"
          >
            <div className="flex items-start gap-3">
              <span className="text-synapse-amber font-mono text-sm tabular-nums mt-0.5">
                {i + 1}
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex items-baseline gap-2 flex-wrap">
                  <button
                    onClick={() => onSelect(n)}
                    className="text-[13px] text-ink-100 font-medium tracking-tight hover:underline"
                    title="Open this note on the canvas"
                  >
                    {n.title}
                  </button>
                  {n.title_hit && (
                    <span className="text-[9px] font-mono px-1.5 py-px rounded bg-synapse-amber/20 ring-1 ring-synapse-amber/40 text-synapse-amber uppercase tracking-widest">
                      title hit
                    </span>
                  )}
                  {n.cluster_name && (
                    <span className="text-[10px] font-mono text-ink-400">
                      <ClusterDot color={n.cluster_color} />
                      {n.cluster_name}
                    </span>
                  )}
                </div>
                <div className="text-[12px] text-ink-300 italic mt-1 leading-snug">
                  “{n.snippet}”
                </div>
                <div className="mt-2 flex items-center gap-3 text-[10px] font-mono text-ink-400 flex-wrap">
                  <RelevanceBar value={n.relevance} />
                  <span>rel {n.relevance.toFixed(2)}</span>
                  <span>cos {n.cosine.toFixed(2)}</span>
                  <span>lex {n.lexical.toFixed(2)}</span>
                  <button
                    onClick={() => onMarkRead(n.note_id)}
                    disabled={busyNoteId === n.note_id}
                    className="ml-auto inline-flex items-center gap-1 rounded-md bg-gradient-to-r from-synapse-cyan/30 to-synapse-violet/25 ring-1 ring-synapse-cyan/55 px-2.5 py-1 text-synapse-cyan hover:text-ink-100 hover:brightness-110 transition disabled:opacity-50"
                  >
                    {busyNoteId === n.note_id ? "…" : "✓ mark read"}
                  </button>
                </div>
              </div>
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}

// ----------------------------------------------------------------- full queue

function QueueCard({
  notes,
  filter,
  total,
  unreadCount,
  onFilter,
  onMarkRead,
  onUnmarkRead,
  busyNoteId,
  onSelect,
}: {
  notes: LensNote[];
  filter: "all" | "unread" | "read";
  total: number;
  unreadCount: number;
  onFilter: (f: "all" | "unread" | "read") => void;
  onMarkRead: (id: number) => void;
  onUnmarkRead: (id: number) => void;
  busyNoteId: number | null;
  onSelect: (n: LensNote) => void;
}) {
  return (
    <div className="rounded-2xl bg-white/[0.015] ring-1 ring-white/5 p-5">
      <div className="flex items-center justify-between mb-3 flex-wrap gap-3">
        <div className="text-[10px] uppercase tracking-[0.18em] text-ink-300">
          full queue · {total} note{total === 1 ? "" : "s"} in lens
        </div>
        <div className="inline-flex items-center gap-1">
          {(["all", "unread", "read"] as const).map((f) => {
            const active = filter === f;
            const count = f === "all" ? total : f === "unread" ? unreadCount : total - unreadCount;
            return (
              <button
                key={f}
                onClick={() => onFilter(f)}
                className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 font-mono text-[10px] transition ${
                  active
                    ? "bg-gradient-to-r from-synapse-cyan/25 to-synapse-violet/20 ring-1 ring-synapse-cyan/55 text-ink-100"
                    : "bg-white/[0.03] ring-1 ring-white/8 text-ink-300 hover:ring-white/20"
                }`}
              >
                {f}
                <span className="opacity-70">{count}</span>
              </button>
            );
          })}
        </div>
      </div>
      {notes.length === 0 ? (
        <div className="text-[12px] text-ink-400 italic py-6 text-center">
          {filter === "all"
            ? "No notes pass the relevance floor for this question yet. Try a more concrete wording, or write a note that engages this topic."
            : `No ${filter} notes in this view.`}
        </div>
      ) : (
        <div className="space-y-2">
          {notes.map((n) => (
            <QueueRow
              key={n.note_id}
              note={n}
              busy={busyNoteId === n.note_id}
              onSelect={() => onSelect(n)}
              onMarkRead={() => onMarkRead(n.note_id)}
              onUnmarkRead={() => onUnmarkRead(n.note_id)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function QueueRow({
  note,
  busy,
  onSelect,
  onMarkRead,
  onUnmarkRead,
}: {
  note: LensNote;
  busy: boolean;
  onSelect: () => void;
  onMarkRead: () => void;
  onUnmarkRead: () => void;
}) {
  return (
    <article
      className={`rounded-xl p-3 transition ring-1 ${
        note.read
          ? "bg-white/[0.015] ring-white/5 opacity-75"
          : "bg-white/[0.025] ring-white/10 hover:ring-white/20"
      }`}
    >
      <div className="flex items-start gap-3">
        <div className="shrink-0 mt-0.5">
          <RelevanceDial value={note.relevance} read={note.read} />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-baseline gap-2 flex-wrap">
            <button
              onClick={onSelect}
              className="text-[13px] font-medium tracking-tight text-ink-100 hover:underline truncate"
              title="Open this note on the canvas"
            >
              {note.title}
            </button>
            {note.cluster_name && (
              <span className="text-[10px] font-mono text-ink-400 shrink-0">
                <ClusterDot color={note.cluster_color} />
                {note.cluster_name}
              </span>
            )}
            {note.title_hit && (
              <span className="text-[9px] font-mono px-1.5 py-px rounded bg-synapse-amber/15 ring-1 ring-synapse-amber/40 text-synapse-amber uppercase tracking-widest">
                title
              </span>
            )}
            {note.read && (
              <span className="text-[9px] font-mono px-1.5 py-px rounded bg-synapse-lime/15 ring-1 ring-synapse-lime/40 text-synapse-lime uppercase tracking-widest">
                read
              </span>
            )}
          </div>
          <div className="text-[12px] text-ink-300 italic line-clamp-2 mt-0.5 leading-snug">
            “{note.snippet}”
          </div>
          <div className="mt-2 flex items-center gap-3 text-[10px] font-mono text-ink-400 flex-wrap">
            <span>rel {note.relevance.toFixed(2)}</span>
            <span>gain {note.info_gain.toFixed(2)}</span>
            <span>cos {note.cosine.toFixed(2)}</span>
            <span>lex {note.lexical.toFixed(2)}</span>
            {note.tags.length > 0 && (
              <span className="opacity-70">
                {note.tags.slice(0, 3).map((t) => (
                  <span key={t} className="mr-1">
                    #{t}
                  </span>
                ))}
              </span>
            )}
            <span className="ml-auto inline-flex items-center gap-1">
              {note.read ? (
                <button
                  onClick={onUnmarkRead}
                  disabled={busy}
                  className="inline-flex items-center gap-1 rounded-md bg-white/[0.04] ring-1 ring-white/10 hover:ring-white/25 px-2 py-1 text-ink-300 hover:text-ink-100 transition disabled:opacity-50"
                  title="Unmark this read for the active question"
                >
                  ↺ unread
                </button>
              ) : (
                <button
                  onClick={onMarkRead}
                  disabled={busy}
                  className="inline-flex items-center gap-1 rounded-md bg-gradient-to-r from-synapse-cyan/25 to-synapse-violet/20 ring-1 ring-synapse-cyan/50 px-2 py-1 text-synapse-cyan hover:text-ink-100 transition disabled:opacity-50"
                >
                  {busy ? "…" : "✓ mark read"}
                </button>
              )}
            </span>
          </div>
        </div>
      </div>
    </article>
  );
}

// ----------------------------------------------------------------- atoms

function RelevanceBar({ value }: { value: number }) {
  const safe = Math.max(0, Math.min(1, value));
  const hue = Math.round(180 + safe * 80);
  return (
    <span className="inline-block w-16 h-1.5 rounded-full bg-white/[0.06] overflow-hidden align-middle">
      <span
        className="block h-full rounded-full"
        style={{
          width: `${safe * 100}%`,
          background: `linear-gradient(90deg, hsl(${hue} 75% 55%), hsl(${hue + 40} 80% 65%))`,
        }}
      />
    </span>
  );
}

function RelevanceDial({ value, read }: { value: number; read: boolean }) {
  const safe = Math.max(0, Math.min(1, value));
  const r = 11;
  const c = 2 * Math.PI * r;
  return (
    <div className="relative w-7 h-7" title={`relevance ${safe.toFixed(2)}`}>
      <svg viewBox="0 0 30 30" className="w-full h-full -rotate-90">
        <circle
          cx="15"
          cy="15"
          r={r}
          stroke="currentColor"
          strokeWidth={3}
          fill="none"
          className="text-white/[0.06]"
        />
        <circle
          cx="15"
          cy="15"
          r={r}
          stroke={read ? "#a3e635" : "#22d3ee"}
          strokeWidth={3}
          strokeLinecap="round"
          fill="none"
          strokeDasharray={`${(safe * c).toFixed(2)} ${c.toFixed(2)}`}
        />
      </svg>
      <span
        className={`absolute inset-0 grid place-items-center font-mono text-[9px] ${
          read ? "text-synapse-lime" : "text-synapse-cyan"
        } tabular-nums`}
      >
        {Math.round(safe * 100)}
      </span>
    </div>
  );
}

function ClusterDot({ color }: { color: string | null }) {
  return (
    <span
      className="inline-block w-2 h-2 rounded-full mr-1 align-middle ring-1 ring-white/20"
      style={{ background: color ?? "#64748b" }}
    />
  );
}

function CompassGlyph() {
  return (
    <div className="relative w-10 h-10 rounded-xl bg-gradient-to-br from-synapse-cyan/30 via-synapse-violet/20 to-synapse-amber/20 ring-1 ring-white/15 grid place-items-center shadow-[0_0_24px_-6px_rgba(34,211,238,0.55)]">
      <svg viewBox="0 0 24 24" className="w-5 h-5 text-ink-100" aria-hidden>
        <circle
          cx="12"
          cy="12"
          r="9"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.6"
          opacity="0.5"
        />
        <circle cx="12" cy="12" r="1.5" fill="currentColor" />
        <path
          d="M12 4 L14 12 L12 20 L10 12 Z"
          fill="currentColor"
          opacity="0.85"
        />
      </svg>
    </div>
  );
}

function CompassSpinner() {
  return (
    <span className="relative inline-flex w-4 h-4">
      <span className="absolute inset-0 rounded-full ring-2 ring-synapse-cyan/30 border-t-2 border-t-synapse-cyan animate-spin" />
    </span>
  );
}

function EmptyState() {
  return (
    <div className="grid place-items-center min-h-[40vh]">
      <div className="max-w-md text-center space-y-3 px-6">
        <div className="text-4xl">🧭</div>
        <div className="text-sm text-ink-100 font-medium">
          Compass — pin your first question.
        </div>
        <p className="text-xs text-ink-400 leading-relaxed">
          Compass turns the vault into a research session. Pin a question on the
          left, watch every relevant note re-rank against it, and mark reads as
          you go — the working answer grows beneath you, one verbatim citation
          at a time.
        </p>
      </div>
    </div>
  );
}
