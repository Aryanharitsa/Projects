"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "@/lib/api";
import type {
  GraphNode,
  SearchHit,
  Trail,
  TrailDraftStep,
  TrailStep,
  TrailSuggestion,
} from "@/lib/types";

type Mode = "play" | "build";

type Props = {
  open: boolean;
  /** When non-null, the player loads an existing trail; when null it's
   *  a fresh draft and Save is gated on a title + ≥1 step. */
  trailId: number | null;
  /** Forced initial mode. The user can toggle once inside. */
  initialMode: Mode;
  /** Optional starter steps (e.g. user clicked "Save path as trail"). */
  startSteps?: TrailDraftStep[] | null;
  /** Optional callable for the canvas: highlights the current step. */
  onFocusNote: (node: GraphNode | null) => void;
  /** Push the trail's step ids upward so the parent can dim the canvas. */
  onTrailChange: (trail: Trail | null) => void;
  /** Bump after any save/delete so the sidebar list refreshes. */
  onMutated: () => void;
  onClose: () => void;
};

const AUTO_ADVANCE_MS = 4200;

export function TrailPlayer({
  open,
  trailId,
  initialMode,
  startSteps,
  onFocusNote,
  onTrailChange,
  onMutated,
  onClose,
}: Props) {
  const [trail, setTrail] = useState<Trail | null>(null);
  const [mode, setMode] = useState<Mode>(initialMode);
  const [idx, setIdx] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [draftTitle, setDraftTitle] = useState("");
  const [draftDescription, setDraftDescription] = useState("");
  const [suggestions, setSuggestions] = useState<TrailSuggestion[]>([]);
  const [searchQ, setSearchQ] = useState("");
  const [searchHits, setSearchHits] = useState<SearchHit[]>([]);
  const [draftSteps, setDraftSteps] = useState<TrailDraftStep[]>([]);
  const autoTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // ------------------------------------------------------------ load
  useEffect(() => {
    if (!open) return;
    setMode(initialMode);
    setIdx(0);
    setPlaying(false);
    setError(null);
    setSearchQ("");
    setSearchHits([]);
    if (trailId == null) {
      // Fresh draft.
      setTrail(null);
      setDraftTitle("");
      setDraftDescription("");
      setDraftSteps(startSteps?.map((s) => ({ ...s })) ?? []);
      onTrailChange(null);
      return;
    }
    setLoading(true);
    api
      .getTrail(trailId)
      .then((t) => {
        setTrail(t);
        setDraftTitle(t.title);
        setDraftDescription(t.description);
        setDraftSteps(t.steps.map((s) => ({ note_id: s.note_id, caption: s.caption })));
        onTrailChange(t);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "failed to load trail"))
      .finally(() => setLoading(false));
  }, [open, trailId, initialMode, startSteps, onTrailChange]);

  // ------------------------------------------------------------ suggestions
  useEffect(() => {
    if (!open || mode !== "build") return;
    if (trail == null) {
      // Empty draft → no trail yet → use first /search call or none.
      setSuggestions([]);
      return;
    }
    let cancelled = false;
    api
      .trailSuggestions(trail.id, 6)
      .then((res) => {
        if (!cancelled) setSuggestions(res.suggestions);
      })
      .catch(() => {
        /* non-fatal */
      });
    return () => {
      cancelled = true;
    };
  }, [open, mode, trail?.id, trail?.updated_at]);

  // Focused note for the canvas — only in play mode (or while idle in build).
  useEffect(() => {
    if (!open || !trail) {
      onFocusNote(null);
      return;
    }
    const step = trail.steps[idx];
    if (!step || !step.exists) {
      onFocusNote(null);
      return;
    }
    onFocusNote({
      id: step.note_id,
      title: step.title,
      body: step.snippet,
      tags: step.tags,
      degree: 0,
      weight: 0,
      community: step.cluster_id ?? null,
      community_color: step.cluster_color ?? null,
    });
  }, [open, trail, idx, onFocusNote]);

  // Auto-advance in play mode.
  useEffect(() => {
    if (autoTimer.current) {
      clearTimeout(autoTimer.current);
      autoTimer.current = null;
    }
    if (!open || !playing || !trail || trail.steps.length === 0) return;
    if (idx >= trail.steps.length - 1) {
      setPlaying(false);
      return;
    }
    autoTimer.current = setTimeout(() => {
      setIdx((i) => Math.min(i + 1, trail.steps.length - 1));
    }, AUTO_ADVANCE_MS);
    return () => {
      if (autoTimer.current) clearTimeout(autoTimer.current);
    };
  }, [open, playing, idx, trail]);

  // Keyboard nav.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if (mode !== "play" || !trail) return;
      if (e.key === "ArrowRight")
        setIdx((i) => Math.min(i + 1, trail.steps.length - 1));
      if (e.key === "ArrowLeft") setIdx((i) => Math.max(i - 1, 0));
      if (e.key === " ") {
        e.preventDefault();
        setPlaying((p) => !p);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, mode, trail, onClose]);

  // ------------------------------------------------------------ save / mutate
  const saveDraft = useCallback(async () => {
    if (!draftTitle.trim()) {
      setError("Give your trail a title first.");
      return;
    }
    if (draftSteps.length === 0) {
      setError("A trail needs at least one stop.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      if (trail == null) {
        const created = await api.createTrail({
          title: draftTitle,
          description: draftDescription,
          steps: draftSteps,
        });
        setTrail(created);
        onTrailChange(created);
      } else {
        const updated = await api.updateTrail(trail.id, {
          title: draftTitle,
          description: draftDescription,
          steps: draftSteps,
        });
        setTrail(updated);
        onTrailChange(updated);
      }
      onMutated();
    } catch (e) {
      setError(e instanceof Error ? e.message : "save failed");
    } finally {
      setSaving(false);
    }
  }, [draftTitle, draftDescription, draftSteps, trail, onTrailChange, onMutated]);

  const handleAppend = useCallback(
    async (noteId: number, caption = "") => {
      // Dedupe: don't append if the tail is already this note.
      if (draftSteps.length > 0 && draftSteps[draftSteps.length - 1].note_id === noteId) {
        return;
      }
      const nextDraft = [...draftSteps, { note_id: noteId, caption }];
      setDraftSteps(nextDraft);
      if (trail) {
        try {
          const updated = await api.appendTrailStep(trail.id, { note_id: noteId, caption });
          setTrail(updated);
          onTrailChange(updated);
          onMutated();
        } catch (e) {
          setError(e instanceof Error ? e.message : "append failed");
        }
      }
    },
    [draftSteps, trail, onTrailChange, onMutated],
  );

  const handleRemove = useCallback((i: number) => {
    setDraftSteps((prev) => prev.filter((_, j) => j !== i));
  }, []);

  const handleMove = useCallback((i: number, dir: -1 | 1) => {
    setDraftSteps((prev) => {
      const j = i + dir;
      if (j < 0 || j >= prev.length) return prev;
      const out = [...prev];
      [out[i], out[j]] = [out[j], out[i]];
      return out;
    });
  }, []);

  const handleEditCaption = useCallback((i: number, caption: string) => {
    setDraftSteps((prev) => prev.map((s, j) => (j === i ? { ...s, caption } : s)));
  }, []);

  const handleDelete = useCallback(async () => {
    if (!trail) return;
    if (!confirm("Delete this trail? The notes themselves stay.")) return;
    try {
      await api.deleteTrail(trail.id);
      onTrailChange(null);
      onMutated();
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "delete failed");
    }
  }, [trail, onClose, onMutated, onTrailChange]);

  // ------------------------------------------------------------ search
  useEffect(() => {
    if (!searchQ.trim()) {
      setSearchHits([]);
      return;
    }
    const handle = setTimeout(() => {
      api
        .search(searchQ, 5)
        .then(setSearchHits)
        .catch(() => setSearchHits([]));
    }, 200);
    return () => clearTimeout(handle);
  }, [searchQ]);

  // ------------------------------------------------------------ derived
  const isDirty = useMemo(() => {
    if (!trail) return draftSteps.length > 0 || draftTitle.trim().length > 0;
    if (draftTitle.trim() !== trail.title) return true;
    if (draftDescription !== trail.description) return true;
    if (draftSteps.length !== trail.steps.length) return true;
    for (let i = 0; i < draftSteps.length; i++) {
      if (
        draftSteps[i].note_id !== trail.steps[i].note_id ||
        draftSteps[i].caption !== trail.steps[i].caption
      )
        return true;
    }
    return false;
  }, [trail, draftSteps, draftTitle, draftDescription]);

  if (!open) return null;

  const stepCount = trail?.steps.length ?? draftSteps.length;
  const current = trail?.steps[idx] ?? null;

  return (
    <div
      className="fixed inset-0 z-40 flex items-center justify-center px-4 py-8 bg-ink-900/85 backdrop-blur-md animate-fade-in"
      role="dialog"
      aria-modal="true"
    >
      <div className="w-full max-w-5xl max-h-full overflow-hidden rounded-2xl bg-ink-800/85 ring-1 ring-white/10 shadow-glow flex flex-col">
        {/* Header */}
        <div className="flex items-center gap-3 px-6 py-4 border-b border-white/5">
          <div className="flex items-center gap-2 text-[10px] font-mono uppercase tracking-[0.18em] text-synapse-amber">
            <span className="w-1.5 h-1.5 rounded-full bg-synapse-amber animate-pulse-slow" />
            trail · {trail ? "saved" : "draft"}
          </div>
          <div className="ml-2 inline-flex items-center rounded-full bg-white/[0.04] ring-1 ring-white/10 p-0.5">
            <ModeTab
              active={mode === "play"}
              disabled={stepCount === 0}
              onClick={() => setMode("play")}
            >
              ▶ play
            </ModeTab>
            <ModeTab active={mode === "build"} onClick={() => setMode("build")}>
              ✎ build
            </ModeTab>
          </div>

          <div className="ml-auto flex items-center gap-2">
            {trail && (
              <a
                href={api.trailExportUrl(trail.id)}
                download
                className="text-[11px] font-mono rounded-full px-3 py-1 ring-1 ring-synapse-cyan/40 text-synapse-cyan hover:text-ink-100 hover:ring-synapse-cyan transition"
                title="download as Markdown"
              >
                ⤓ markdown
              </a>
            )}
            {trail && (
              <button
                onClick={handleDelete}
                className="text-[11px] font-mono rounded-full px-3 py-1 ring-1 ring-synapse-pink/30 text-synapse-pink/90 hover:ring-synapse-pink hover:text-ink-100 transition"
              >
                delete
              </button>
            )}
            <button
              onClick={onClose}
              className="text-[11px] font-mono rounded-full px-3 py-1 ring-1 ring-white/10 text-ink-300 hover:text-ink-100 hover:ring-white/30 transition"
            >
              close ✕
            </button>
          </div>
        </div>

        {loading && (
          <div className="px-6 py-16 text-center text-sm font-mono text-ink-300">
            loading trail…
          </div>
        )}

        {/* Title block — always editable in build mode, read-only in play */}
        {!loading && (
          <div className="px-6 pt-5 pb-3 border-b border-white/5">
            {mode === "build" ? (
              <>
                <input
                  value={draftTitle}
                  onChange={(e) => setDraftTitle(e.target.value)}
                  placeholder="Trail title — e.g. ‘How embeddings made folders obsolete’"
                  className="w-full bg-transparent text-xl font-semibold text-ink-100 focus-ring rounded outline-none placeholder:text-ink-400"
                />
                <textarea
                  value={draftDescription}
                  onChange={(e) => setDraftDescription(e.target.value)}
                  placeholder="One-line description (optional)"
                  rows={2}
                  className="w-full mt-2 bg-white/[0.02] ring-1 ring-white/5 rounded-lg p-2.5 text-sm text-ink-100 focus-ring outline-none resize-none placeholder:text-ink-400"
                />
              </>
            ) : (
              <>
                <h1 className="text-xl font-semibold text-ink-100 leading-tight">
                  {trail?.title ?? "Untitled trail"}
                </h1>
                {trail?.description && (
                  <p className="mt-1 text-sm text-ink-300">{trail.description}</p>
                )}
              </>
            )}
            {trail && (
              <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] font-mono text-ink-400">
                <span>{trail.steps.length} stops</span>
                <span>·</span>
                <span title="fraction of transitions that ride a real synapse">
                  {Math.round(trail.health * 100)}% synapse-aligned
                </span>
                <span>·</span>
                <span>τ {trail.threshold.toFixed(2)}</span>
                <span>·</span>
                <span>Σ strength {trail.total_strength.toFixed(2)}</span>
                {trail.missing_count > 0 && (
                  <>
                    <span>·</span>
                    <span className="text-synapse-pink/90">
                      {trail.missing_count} deleted note
                      {trail.missing_count === 1 ? "" : "s"}
                    </span>
                  </>
                )}
              </div>
            )}
          </div>
        )}

        {/* Body */}
        {!loading && (
          <div className="flex-1 overflow-y-auto">
            {mode === "play" ? (
              <PlayBody
                trail={trail}
                idx={idx}
                setIdx={setIdx}
                playing={playing}
                setPlaying={setPlaying}
              />
            ) : (
              <BuildBody
                steps={draftSteps}
                currentTrail={trail}
                suggestions={suggestions}
                onAppend={handleAppend}
                onRemove={handleRemove}
                onMove={handleMove}
                onEditCaption={handleEditCaption}
                searchQ={searchQ}
                setSearchQ={setSearchQ}
                searchHits={searchHits}
              />
            )}
          </div>
        )}

        {/* Footer */}
        {!loading && mode === "build" && (
          <div className="border-t border-white/5 px-6 py-3 flex items-center gap-3">
            {error && (
              <span className="text-[11px] font-mono text-synapse-pink">{error}</span>
            )}
            <div className="ml-auto flex items-center gap-2">
              {isDirty && (
                <span className="text-[11px] font-mono text-ink-400">unsaved</span>
              )}
              <button
                disabled={!isDirty || saving}
                onClick={saveDraft}
                className="text-[12px] font-mono uppercase tracking-[0.14em] rounded-full px-4 py-1.5 ring-1 ring-synapse-amber/40 text-synapse-amber hover:ring-synapse-amber hover:text-ink-100 transition disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {saving ? "saving…" : trail ? "save changes" : "save trail"}
              </button>
              {trail && (
                <button
                  onClick={() => setMode("play")}
                  disabled={trail.steps.length === 0}
                  className="text-[12px] font-mono uppercase tracking-[0.14em] rounded-full px-4 py-1.5 ring-1 ring-synapse-cyan/40 text-synapse-cyan hover:ring-synapse-cyan hover:text-ink-100 transition disabled:opacity-40"
                >
                  open in player →
                </button>
              )}
            </div>
          </div>
        )}

        {!loading && mode === "play" && current && (
          <div className="border-t border-white/5 px-6 py-3 flex items-center gap-3">
            <button
              onClick={() => setIdx((i) => Math.max(0, i - 1))}
              disabled={idx === 0}
              className="text-[11px] font-mono rounded-full px-3 py-1 ring-1 ring-white/10 text-ink-200 hover:text-ink-100 hover:ring-white/30 transition disabled:opacity-30"
            >
              ← prev
            </button>
            <button
              onClick={() => setPlaying((p) => !p)}
              disabled={idx >= (trail?.steps.length ?? 1) - 1 && !playing}
              className="text-[12px] font-mono uppercase tracking-[0.14em] rounded-full px-4 py-1.5 ring-1 ring-synapse-amber/40 text-synapse-amber hover:ring-synapse-amber hover:text-ink-100 transition"
            >
              {playing ? "■ pause" : "▶ play"}
            </button>
            <button
              onClick={() =>
                setIdx((i) => Math.min((trail?.steps.length ?? 1) - 1, i + 1))
              }
              disabled={idx >= (trail?.steps.length ?? 1) - 1}
              className="text-[11px] font-mono rounded-full px-3 py-1 ring-1 ring-white/10 text-ink-200 hover:text-ink-100 hover:ring-white/30 transition disabled:opacity-30"
            >
              next →
            </button>
            <div className="ml-auto text-[11px] font-mono text-ink-400">
              {idx + 1} / {trail?.steps.length ?? 0}
              {playing && (
                <span className="ml-2 text-synapse-amber">
                  auto-advancing
                </span>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- play body

function PlayBody({
  trail,
  idx,
  setIdx,
  playing,
  setPlaying,
}: {
  trail: Trail | null;
  idx: number;
  setIdx: (n: number | ((prev: number) => number)) => void;
  playing: boolean;
  setPlaying: (p: boolean) => void;
}) {
  if (!trail || trail.steps.length === 0) {
    return (
      <div className="px-6 py-16 text-center text-sm text-ink-300">
        This trail has no stops yet. Switch to <strong>build</strong> to add some.
      </div>
    );
  }
  const step = trail.steps[idx];
  const strength = step?.strength_to_next;
  const synapse = step?.is_synapse_to_next ?? false;

  return (
    <div className="px-6 py-5">
      <ProgressDots
        steps={trail.steps}
        idx={idx}
        onJump={(i) => {
          setIdx(i);
          setPlaying(false);
        }}
      />

      <div
        key={`${idx}-${step?.note_id}`}
        className="mt-5 rounded-2xl bg-gradient-to-br from-white/[0.04] to-white/[0.01] ring-1 ring-white/8 p-6 animate-fade-in"
        style={
          step?.cluster_color
            ? {
                boxShadow: `0 0 0 1px ${rgba(step.cluster_color, 0.35)}, 0 0 30px -4px ${rgba(step.cluster_color, 0.25)}`,
              }
            : undefined
        }
      >
        <div className="flex items-center gap-2 text-[11px] font-mono">
          <span className="text-ink-400">
            stop {idx + 1} of {trail.steps.length}
          </span>
          {step?.cluster_name && (
            <span
              className="rounded-full px-2 py-0.5 ring-1"
              style={{
                color: step.cluster_color ?? undefined,
                borderColor: rgba(step.cluster_color ?? "#a855f7", 0.4),
                background: rgba(step.cluster_color ?? "#a855f7", 0.08),
              }}
            >
              {step.cluster_name}
            </span>
          )}
        </div>
        <h2 className="mt-2 text-2xl font-semibold text-ink-100 leading-tight">
          {step?.title ?? "(missing note)"}
        </h2>
        {step?.caption && (
          <p className="mt-3 text-sm text-synapse-amber/90 italic leading-relaxed border-l-2 border-synapse-amber/50 pl-3">
            “{step.caption}”
          </p>
        )}
        <p className="mt-4 text-[15px] text-ink-100/90 leading-relaxed">
          {step?.snippet || (
            <span className="text-ink-400">No body — this note may have been deleted.</span>
          )}
        </p>
        {step?.tags && step.tags.length > 0 && (
          <div className="mt-4 flex flex-wrap gap-1.5">
            {step.tags.map((t) => (
              <span
                key={t}
                className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-synapse-violet/10 text-synapse-violet ring-1 ring-synapse-violet/20"
              >
                #{t}
              </span>
            ))}
          </div>
        )}

        {strength != null && (
          <div className="mt-5 flex items-center gap-3 text-[11px] font-mono">
            <span className={synapse ? "text-synapse-cyan" : "text-ink-400"}>
              {synapse ? "→ synapse" : "⤳ leap"}
            </span>
            <div className="flex-1 h-1 rounded-full bg-white/5 overflow-hidden">
              <div
                className={`h-full ${
                  synapse
                    ? "bg-gradient-to-r from-synapse-cyan to-synapse-violet"
                    : "bg-gradient-to-r from-synapse-pink/70 to-synapse-amber/70"
                }`}
                style={{ width: `${Math.max(8, Math.min(100, strength * 100 * 3))}%` }}
              />
            </div>
            <span className="text-ink-300">cos {strength.toFixed(2)}</span>
          </div>
        )}
      </div>
    </div>
  );
}

function ProgressDots({
  steps,
  idx,
  onJump,
}: {
  steps: TrailStep[];
  idx: number;
  onJump: (i: number) => void;
}) {
  return (
    <div className="flex items-center gap-1">
      {steps.map((s, i) => {
        const isCurrent = i === idx;
        const isPast = i < idx;
        // The connector before this step shows the previous edge's quality.
        const prev = i > 0 ? steps[i - 1] : null;
        const synapse = prev?.is_synapse_to_next ?? false;
        return (
          <div key={i} className="flex items-center gap-1">
            {i > 0 && (
              <div
                className={`h-px w-6 ${
                  synapse
                    ? "bg-gradient-to-r from-synapse-cyan/60 to-synapse-violet/60"
                    : "bg-gradient-to-r from-ink-400/40 to-ink-400/40 [border-style:dashed]"
                }`}
                title={
                  prev?.strength_to_next != null
                    ? `${synapse ? "synapse" : "leap"} · cos ${prev.strength_to_next.toFixed(2)}`
                    : undefined
                }
              />
            )}
            <button
              onClick={() => onJump(i)}
              title={s.title}
              className={`group rounded-full transition ${
                isCurrent
                  ? "w-3.5 h-3.5"
                  : "w-2.5 h-2.5 hover:scale-110"
              }`}
              style={{
                background: isCurrent
                  ? s.cluster_color ?? "#fbbf24"
                  : isPast
                    ? rgba(s.cluster_color ?? "#a855f7", 0.6)
                    : "rgba(91,101,144,0.35)",
                boxShadow: isCurrent
                  ? `0 0 0 2px ${rgba(s.cluster_color ?? "#fbbf24", 0.25)}, 0 0 14px ${rgba(s.cluster_color ?? "#fbbf24", 0.55)}`
                  : undefined,
              }}
              aria-label={`go to stop ${i + 1}`}
            />
          </div>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------- build body

function BuildBody({
  steps,
  currentTrail,
  suggestions,
  onAppend,
  onRemove,
  onMove,
  onEditCaption,
  searchQ,
  setSearchQ,
  searchHits,
}: {
  steps: TrailDraftStep[];
  currentTrail: Trail | null;
  suggestions: TrailSuggestion[];
  onAppend: (noteId: number, caption?: string) => void;
  onRemove: (i: number) => void;
  onMove: (i: number, dir: -1 | 1) => void;
  onEditCaption: (i: number, caption: string) => void;
  searchQ: string;
  setSearchQ: (q: string) => void;
  searchHits: SearchHit[];
}) {
  // Resolve the live note for each draft step so we can render the
  // title even before the trail has been saved (when `currentTrail`
  // hasn't been hydrated yet).
  const liveById = useMemo(() => {
    const m = new Map<number, { title: string; tags: string[]; cluster_color: string | null; cluster_name: string | null }>();
    if (currentTrail) {
      for (const s of currentTrail.steps) {
        m.set(s.note_id, {
          title: s.title,
          tags: s.tags,
          cluster_color: s.cluster_color,
          cluster_name: s.cluster_name,
        });
      }
    }
    for (const h of searchHits) {
      m.set(h.node.id, {
        title: h.node.title,
        tags: h.node.tags,
        cluster_color: h.node.community_color ?? null,
        cluster_name: null,
      });
    }
    for (const s of suggestions) {
      if (!m.has(s.note_id)) {
        m.set(s.note_id, {
          title: s.title,
          tags: s.tags,
          cluster_color: s.cluster_color,
          cluster_name: s.cluster_name,
        });
      }
    }
    return m;
  }, [currentTrail, searchHits, suggestions]);

  return (
    <div className="px-6 py-5 grid grid-cols-12 gap-5">
      <div className="col-span-12 lg:col-span-7">
        <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-ink-200 mb-2">
          stops ({steps.length})
        </div>
        {steps.length === 0 ? (
          <div className="rounded-xl ring-1 ring-dashed ring-white/10 p-5 text-sm text-ink-300 bg-white/[0.012]">
            No stops yet. Pick a starting note from the right panel — the
            suggestions show your most central thoughts. After the first stop,
            SynapseOS proposes synapse neighbors as next steps.
          </div>
        ) : (
          <ol className="space-y-2">
            {steps.map((s, i) => {
              const live = liveById.get(s.note_id);
              return (
                <li
                  key={`${i}-${s.note_id}`}
                  className="group rounded-lg ring-1 ring-white/5 bg-white/[0.015] p-3"
                >
                  <div className="flex items-start gap-2">
                    <span
                      className="mt-0.5 inline-flex items-center justify-center w-6 h-6 rounded-full text-[10px] font-mono shrink-0"
                      style={{
                        background: live?.cluster_color
                          ? rgba(live.cluster_color, 0.18)
                          : "rgba(168,85,247,0.18)",
                        color: live?.cluster_color ?? "#a855f7",
                        boxShadow: `inset 0 0 0 1px ${rgba(live?.cluster_color ?? "#a855f7", 0.45)}`,
                      }}
                    >
                      {i + 1}
                    </span>
                    <div className="flex-1 min-w-0">
                      <div className="text-sm text-ink-100 truncate">
                        {live?.title ?? `note #${s.note_id}`}
                      </div>
                      <input
                        value={s.caption}
                        onChange={(e) => onEditCaption(i, e.target.value)}
                        placeholder="caption (optional) — what does this stop mean here?"
                        className="mt-1 w-full bg-transparent text-[12px] text-ink-200 outline-none placeholder:text-ink-400 focus:text-synapse-amber transition"
                        maxLength={400}
                      />
                    </div>
                    <div className="flex items-center gap-1 shrink-0 opacity-60 group-hover:opacity-100 transition">
                      <button
                        onClick={() => onMove(i, -1)}
                        disabled={i === 0}
                        aria-label="move up"
                        className="p-1 rounded text-ink-300 hover:text-synapse-cyan disabled:opacity-30"
                      >
                        ▲
                      </button>
                      <button
                        onClick={() => onMove(i, 1)}
                        disabled={i === steps.length - 1}
                        aria-label="move down"
                        className="p-1 rounded text-ink-300 hover:text-synapse-cyan disabled:opacity-30"
                      >
                        ▼
                      </button>
                      <button
                        onClick={() => onRemove(i)}
                        aria-label="remove"
                        className="p-1 rounded text-ink-300 hover:text-synapse-pink"
                      >
                        ✕
                      </button>
                    </div>
                  </div>
                </li>
              );
            })}
          </ol>
        )}
      </div>

      <div className="col-span-12 lg:col-span-5 space-y-4">
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-ink-200 mb-2">
            {steps.length === 0 ? "starting points" : "likely next"}
          </div>
          {suggestions.length === 0 ? (
            <p className="text-[11px] text-ink-400">
              {steps.length === 0
                ? "Add a note first to see suggestions."
                : "No close neighbors left. Try search ↓."}
            </p>
          ) : (
            <ul className="space-y-1.5">
              {suggestions.map((s) => (
                <li key={s.note_id}>
                  <button
                    onClick={() => onAppend(s.note_id)}
                    className="w-full text-left rounded-lg p-2 ring-1 ring-white/5 bg-white/[0.012] hover:bg-white/[0.04] transition group"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-sm text-ink-100 truncate group-hover:text-ink-100">
                        {s.title}
                      </span>
                      <span
                        className="text-[10px] font-mono shrink-0"
                        style={{ color: s.cluster_color ?? "#22d3ee" }}
                      >
                        {s.strength > 0
                          ? `cos ${s.strength.toFixed(2)}`
                          : `· hub`}
                      </span>
                    </div>
                    {s.cluster_name && (
                      <div
                        className="mt-0.5 text-[10px] font-mono"
                        style={{ color: rgba(s.cluster_color ?? "#a855f7", 0.85) }}
                      >
                        {s.cluster_name}
                      </div>
                    )}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div>
          <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-ink-200 mb-2">
            add by search
          </div>
          <input
            value={searchQ}
            onChange={(e) => setSearchQ(e.target.value)}
            placeholder="search your brain…"
            className="w-full bg-white/[0.02] ring-1 ring-white/5 rounded-lg px-3 py-2 text-sm text-ink-100 outline-none focus-ring placeholder:text-ink-400"
          />
          {searchHits.length > 0 && (
            <ul className="mt-2 space-y-1.5">
              {searchHits.map((h) => (
                <li key={h.node.id}>
                  <button
                    onClick={() => onAppend(h.node.id)}
                    className="w-full text-left rounded-lg p-2 ring-1 ring-white/5 bg-white/[0.012] hover:bg-white/[0.04] transition"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-sm text-ink-100 truncate">
                        {h.node.title}
                      </span>
                      <span className="text-[10px] font-mono text-synapse-cyan/90 shrink-0">
                        {(h.score * 100).toFixed(0)}%
                      </span>
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}

function ModeTab({
  active,
  onClick,
  children,
  disabled,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
  disabled?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`text-[11px] font-mono uppercase tracking-[0.14em] rounded-full px-3 py-1 transition ${
        active
          ? "bg-synapse-amber/15 text-synapse-amber ring-1 ring-synapse-amber/40"
          : "text-ink-300 hover:text-ink-100 disabled:opacity-30 disabled:cursor-not-allowed"
      }`}
    >
      {children}
    </button>
  );
}

function rgba(hex: string, alpha: number): string {
  if (hex.startsWith("rgba") || hex.startsWith("rgb")) return hex;
  let h = hex.replace("#", "");
  if (h.length === 3) h = h.split("").map((c) => c + c).join("");
  const r = parseInt(h.slice(0, 2), 16);
  const g = parseInt(h.slice(2, 4), 16);
  const b = parseInt(h.slice(4, 6), 16);
  return `rgba(${r},${g},${b},${alpha.toFixed(3)})`;
}
