"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import type {
  AtomPreview,
  AtomizeMode,
  AtomizeResponse,
  GraphNode,
} from "@/lib/types";

type Props = {
  open: boolean;
  onClose: () => void;
  /** Called after commit so the page can refresh /graph + /communities + /orphans. */
  onCommitted?: (createdIds: number[], synapsesFormed: number) => void;
  /** Click a predicted neighbor chip → focus that note in the inspector. */
  onPreviewNeighbor?: (n: Pick<GraphNode, "id" | "title" | "body" | "tags" | "degree" | "weight">) => void;
  /** Used to enrich predicted neighbors with current weight/degree. */
  nodes: GraphNode[];
};

const SAMPLE = `# Why graphs over hierarchies
Hierarchies lie. A note rarely belongs under exactly one folder. Tags miss the long tail.
A graph is what your thinking actually looks like — overlapping, partial, alive.

## Cold start is the real problem
Most PKM tools fail at the empty-canvas step. People install, stare at an empty graph,
and never come back. Distill solves this by atomizing anything you already wrote into
a swarm of small notes that immediately synapse to your existing thoughts.

## What an atom looks like
One claim, one paragraph, one title that could be a tweet. If you'd cite it on its own,
it's an atom. If it needs three siblings to stand up, it's not — split it.`;

export function Distill({
  open,
  onClose,
  onCommitted,
  onPreviewNeighbor,
  nodes,
}: Props) {
  const [text, setText] = useState("");
  const [mode, setMode] = useState<AtomizeMode>("auto");
  const [stage, setStage] = useState<"input" | "preview" | "committing" | "done">(
    "input",
  );
  const [previewing, setPreviewing] = useState(false);
  const [response, setResponse] = useState<AtomizeResponse | null>(null);
  const [atoms, setAtoms] = useState<AtomPreview[]>([]);
  const [dropped, setDropped] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const [committed, setCommitted] = useState<{
    count: number;
    synapses: number;
  } | null>(null);

  // Reset everything when the modal opens fresh.
  useEffect(() => {
    if (!open) return;
    setText("");
    setMode("auto");
    setStage("input");
    setResponse(null);
    setAtoms([]);
    setDropped(new Set());
    setError(null);
    setCommitted(null);
  }, [open]);

  // Esc closes the modal at any stage.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  const handlePreview = useCallback(async () => {
    if (!text.trim()) return;
    setPreviewing(true);
    setError(null);
    try {
      const r = await api.atomize({ text, mode });
      setResponse(r);
      setAtoms(r.atoms);
      setDropped(new Set());
      setStage("preview");
    } catch (e) {
      setError(e instanceof Error ? e.message : "failed to distill");
    } finally {
      setPreviewing(false);
    }
  }, [text, mode]);

  const surviving = useMemo(
    () => atoms.filter((a) => !dropped.has(a.temp_id)),
    [atoms, dropped],
  );

  const totalSynapses = useMemo(
    () => surviving.reduce((acc, a) => acc + a.expected_synapses, 0),
    [surviving],
  );

  const updateAtom = useCallback(
    (id: string, patch: Partial<AtomPreview>) => {
      setAtoms((prev) =>
        prev.map((a) => (a.temp_id === id ? { ...a, ...patch } : a)),
      );
    },
    [],
  );

  const handleCommit = useCallback(async () => {
    if (surviving.length === 0) return;
    setStage("committing");
    setError(null);
    try {
      const res = await api.atomizeCommit(
        surviving.map((a) => ({
          title: a.title.trim() || "Untitled atom",
          body: a.body.trim(),
          tags: a.tags,
        })),
      );
      setCommitted({
        count: res.created.length,
        synapses: res.synapses_formed,
      });
      setStage("done");
      onCommitted?.(
        res.created.map((c) => c.note_id),
        res.synapses_formed,
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "commit failed");
      setStage("preview");
    }
  }, [surviving, onCommitted]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center px-4 py-6"
      role="dialog"
      aria-label="Distill — atomize long-form text"
    >
      <div
        className="absolute inset-0 bg-ink-950/85 backdrop-blur-md"
        onClick={onClose}
      />

      <div className="absolute inset-0 pointer-events-none bg-grid-fade opacity-50" />

      <div className="relative w-full max-w-5xl max-h-[92vh] flex flex-col rounded-2xl ring-1 ring-white/10 shadow-glow bg-gradient-to-b from-ink-900/95 to-ink-950/95">
        <DistillHeader
          stage={stage}
          mode={mode}
          onMode={setMode}
          llmAvailable={response?.llm_available ?? false}
          llmProvider={response?.llm_provider ?? null}
          atomsCount={surviving.length}
          totalSynapses={totalSynapses}
          totalChars={response?.total_chars ?? text.length}
          onClose={onClose}
        />

        <div className="flex-1 overflow-y-auto px-7 py-5">
          {stage === "input" && (
            <InputStage
              text={text}
              onText={setText}
              onPreview={handlePreview}
              previewing={previewing}
              error={error}
            />
          )}

          {stage === "preview" && (
            <PreviewStage
              atoms={atoms}
              dropped={dropped}
              onDropToggle={(id) =>
                setDropped((prev) => {
                  const next = new Set(prev);
                  if (next.has(id)) next.delete(id);
                  else next.add(id);
                  return next;
                })
              }
              onUpdate={updateAtom}
              onCommit={handleCommit}
              onBack={() => setStage("input")}
              nodes={nodes}
              onPreviewNeighbor={onPreviewNeighbor}
              notice={response?.notice ?? null}
              modeUsed={response?.mode_used ?? "heuristic"}
              error={error}
            />
          )}

          {stage === "committing" && (
            <div className="py-24 flex flex-col items-center gap-4 text-ink-300">
              <div className="w-12 h-12 rounded-full ring-2 ring-synapse-violet/50 animate-pulse-slow" />
              <div className="font-mono text-xs">
                committing {surviving.length} atoms…
              </div>
            </div>
          )}

          {stage === "done" && committed && (
            <DoneStage
              count={committed.count}
              synapses={committed.synapses}
              onClose={onClose}
              onDistillMore={() => {
                setText("");
                setStage("input");
                setResponse(null);
                setAtoms([]);
                setDropped(new Set());
                setCommitted(null);
              }}
            />
          )}
        </div>
      </div>
    </div>
  );
}

// -------------------------------------------------------------------- header

function DistillHeader({
  stage,
  mode,
  onMode,
  llmAvailable,
  llmProvider,
  atomsCount,
  totalSynapses,
  totalChars,
  onClose,
}: {
  stage: "input" | "preview" | "committing" | "done";
  mode: AtomizeMode;
  onMode: (m: AtomizeMode) => void;
  llmAvailable: boolean;
  llmProvider: string | null;
  atomsCount: number;
  totalSynapses: number;
  totalChars: number;
  onClose: () => void;
}) {
  return (
    <div className="border-b border-white/5 px-7 py-4 flex items-center gap-4">
      <div className="flex items-center gap-3">
        <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-synapse-violet/40 to-synapse-cyan/30 ring-1 ring-white/10 grid place-items-center text-synapse-violet text-base">
          ✨
        </div>
        <div>
          <div className="text-sm font-semibold text-ink-100">Distill</div>
          <div className="text-[11px] text-ink-300 uppercase tracking-[0.16em]">
            paste anything · ship atoms
          </div>
        </div>
      </div>

      <div className="ml-auto flex items-center gap-2 text-[11px]">
        {stage === "preview" && (
          <>
            <Stat label="atoms" value={atomsCount} color="violet" />
            <Stat label="synapses" value={totalSynapses} color="cyan" />
          </>
        )}
        {stage === "input" && (
          <Stat label="chars" value={totalChars} color="amber" />
        )}

        {(stage === "input" || stage === "preview") && (
          <ModeToggle
            mode={mode}
            onMode={onMode}
            llmAvailable={llmAvailable}
            llmProvider={llmProvider}
          />
        )}

        <button
          onClick={onClose}
          className="ml-1 px-2.5 py-1 rounded-md ring-1 ring-white/10 hover:ring-white/30 text-ink-300 hover:text-ink-100 transition font-mono"
          aria-label="close distill"
        >
          esc ✕
        </button>
      </div>
    </div>
  );
}

function ModeToggle({
  mode,
  onMode,
  llmAvailable,
  llmProvider,
}: {
  mode: AtomizeMode;
  onMode: (m: AtomizeMode) => void;
  llmAvailable: boolean;
  llmProvider: string | null;
}) {
  const opt = (
    key: AtomizeMode,
    label: string,
    color: "auto" | "heuristic" | "llm",
    disabled?: boolean,
    title?: string,
  ) => {
    const active = mode === key;
    const cls = active
      ? color === "llm"
        ? "ring-synapse-amber/60 text-synapse-amber bg-synapse-amber/10"
        : color === "heuristic"
          ? "ring-synapse-cyan/60 text-synapse-cyan bg-synapse-cyan/10"
          : "ring-synapse-violet/60 text-synapse-violet bg-synapse-violet/10"
      : "ring-white/10 text-ink-300 hover:text-ink-100";
    return (
      <button
        key={key}
        onClick={() => !disabled && onMode(key)}
        disabled={disabled}
        title={title}
        className={`px-2 py-1 rounded-md ring-1 ${cls} font-mono disabled:opacity-40 disabled:cursor-not-allowed transition`}
      >
        {label}
      </button>
    );
  };
  return (
    <div className="inline-flex items-center gap-1 rounded-lg bg-white/[0.02] p-0.5 ring-1 ring-white/5">
      {opt("auto", "auto", "auto")}
      {opt("heuristic", "fast", "heuristic")}
      {opt(
        "llm",
        llmAvailable ? `llm ${llmProvider ? "✓" : ""}` : "llm —",
        "llm",
        !llmAvailable,
        llmAvailable
          ? `LLM refine (${llmProvider})`
          : "set SYNAPSE_LLM_KEY to enable",
      )}
    </div>
  );
}

function Stat({
  label,
  value,
  color,
}: {
  label: string;
  value: number;
  color: "violet" | "cyan" | "amber";
}) {
  const ring = {
    violet: "ring-synapse-violet/40 text-synapse-violet",
    cyan: "ring-synapse-cyan/40 text-synapse-cyan",
    amber: "ring-synapse-amber/40 text-synapse-amber",
  }[color];
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full bg-white/[0.02] ring-1 ${ring} px-2.5 py-1 font-mono`}
    >
      <span className="opacity-70">{label}</span>
      <span className="text-ink-100">{value}</span>
    </span>
  );
}

// -------------------------------------------------------------------- input

function InputStage({
  text,
  onText,
  onPreview,
  previewing,
  error,
}: {
  text: string;
  onText: (s: string) => void;
  onPreview: () => void;
  previewing: boolean;
  error: string | null;
}) {
  return (
    <div className="flex flex-col gap-5">
      <div className="text-[13px] text-ink-300 leading-relaxed max-w-2xl">
        Paste an article, transcript, meeting notes, or a long braindump.
        Distill segments it into <span className="text-synapse-violet">atomic notes</span>,
        proposes titles + tags, and previews which existing notes each atom
        will <span className="text-synapse-cyan">synapse</span> to before
        anything saves.
      </div>

      <div className="relative">
        <textarea
          value={text}
          onChange={(e) => onText(e.target.value)}
          placeholder="paste here…"
          className="w-full h-[42vh] min-h-[280px] bg-white/[0.02] ring-1 ring-white/10 focus:ring-synapse-violet/60 rounded-xl p-4 font-mono text-[13px] text-ink-100 leading-relaxed placeholder:text-ink-400 resize-none transition outline-none"
          spellCheck={false}
          autoFocus
        />
        <div className="absolute right-3 bottom-3 flex items-center gap-2 text-[11px] font-mono text-ink-400">
          <span>{text.length.toLocaleString()} chars</span>
        </div>
      </div>

      <div className="flex items-center gap-3">
        <button
          onClick={onPreview}
          disabled={!text.trim() || previewing}
          className="px-4 py-2 rounded-lg bg-gradient-to-r from-synapse-violet/30 to-synapse-cyan/30 ring-1 ring-synapse-violet/60 hover:ring-synapse-violet text-ink-100 font-mono text-xs disabled:opacity-50 disabled:cursor-not-allowed transition"
        >
          {previewing ? "distilling…" : "preview atoms →"}
        </button>
        <button
          onClick={() => onText(SAMPLE)}
          className="px-3 py-2 rounded-lg ring-1 ring-white/10 hover:ring-white/30 text-ink-300 hover:text-ink-100 font-mono text-xs transition"
        >
          try a sample
        </button>
        {text && (
          <button
            onClick={() => onText("")}
            className="px-3 py-2 rounded-lg ring-1 ring-white/5 hover:ring-synapse-pink/40 text-ink-400 hover:text-synapse-pink font-mono text-xs transition"
          >
            clear
          </button>
        )}
      </div>

      {error && (
        <div className="text-xs font-mono text-synapse-pink">
          {error}
        </div>
      )}

      <div className="text-[11px] font-mono text-ink-400 flex flex-wrap gap-x-5 gap-y-1">
        <span>· headings start new atoms</span>
        <span>· short paragraphs glue forward</span>
        <span>· monster paragraphs sentence-split</span>
        <span>· nothing saves until you confirm</span>
      </div>
    </div>
  );
}

// -------------------------------------------------------------------- preview

function PreviewStage({
  atoms,
  dropped,
  onDropToggle,
  onUpdate,
  onCommit,
  onBack,
  nodes,
  onPreviewNeighbor,
  notice,
  modeUsed,
  error,
}: {
  atoms: AtomPreview[];
  dropped: Set<string>;
  onDropToggle: (id: string) => void;
  onUpdate: (id: string, patch: Partial<AtomPreview>) => void;
  onCommit: () => void;
  onBack: () => void;
  nodes: GraphNode[];
  onPreviewNeighbor?: (n: Pick<GraphNode, "id" | "title" | "body" | "tags" | "degree" | "weight">) => void;
  notice: string | null;
  modeUsed: "heuristic" | "llm";
  error: string | null;
}) {
  const surviving = atoms.filter((a) => !dropped.has(a.temp_id)).length;

  if (atoms.length === 0) {
    return (
      <div className="py-24 flex flex-col items-center gap-4 text-ink-300">
        <div className="text-sm">No atoms could be extracted from that input.</div>
        <button
          onClick={onBack}
          className="px-3 py-2 rounded-lg ring-1 ring-white/10 hover:ring-white/30 text-ink-300 hover:text-ink-100 font-mono text-xs transition"
        >
          ← back
        </button>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      {notice && (
        <div className="text-[11px] font-mono px-3 py-2 rounded-md ring-1 ring-synapse-amber/30 bg-synapse-amber/5 text-synapse-amber">
          {notice}
        </div>
      )}

      <div className="space-y-3">
        {atoms.map((a, i) => (
          <AtomCard
            key={a.temp_id}
            atom={a}
            index={i + 1}
            dropped={dropped.has(a.temp_id)}
            onToggleDrop={() => onDropToggle(a.temp_id)}
            onUpdate={(patch) => onUpdate(a.temp_id, patch)}
            nodes={nodes}
            onPreviewNeighbor={onPreviewNeighbor}
            modeUsed={modeUsed}
          />
        ))}
      </div>

      {error && (
        <div className="text-xs font-mono text-synapse-pink">
          {error}
        </div>
      )}

      <div className="sticky bottom-0 -mx-7 -mb-5 px-7 py-4 bg-gradient-to-t from-ink-950/95 via-ink-950/90 to-transparent flex items-center gap-3">
        <button
          onClick={onBack}
          className="px-3 py-2 rounded-lg ring-1 ring-white/10 hover:ring-white/30 text-ink-300 hover:text-ink-100 font-mono text-xs transition"
        >
          ← back
        </button>
        <div className="text-[11px] font-mono text-ink-400">
          {surviving} of {atoms.length} kept · click a synapse chip to peek
        </div>
        <button
          onClick={onCommit}
          disabled={surviving === 0}
          className="ml-auto px-4 py-2 rounded-lg bg-gradient-to-r from-synapse-lime/20 to-synapse-cyan/20 ring-1 ring-synapse-lime/60 hover:ring-synapse-lime text-synapse-lime hover:text-ink-100 font-mono text-xs disabled:opacity-40 disabled:cursor-not-allowed transition"
        >
          commit {surviving} atom{surviving === 1 ? "" : "s"} →
        </button>
      </div>
    </div>
  );
}

// -------------------------------------------------------------------- atom card

function AtomCard({
  atom,
  index,
  dropped,
  onToggleDrop,
  onUpdate,
  nodes,
  onPreviewNeighbor,
  modeUsed,
}: {
  atom: AtomPreview;
  index: number;
  dropped: boolean;
  onToggleDrop: () => void;
  onUpdate: (patch: Partial<AtomPreview>) => void;
  nodes: GraphNode[];
  onPreviewNeighbor?: (n: Pick<GraphNode, "id" | "title" | "body" | "tags" | "degree" | "weight">) => void;
  modeUsed: "heuristic" | "llm";
}) {
  const [tagDraft, setTagDraft] = useState("");
  const [bodyExpanded, setBodyExpanded] = useState(false);

  const addTag = useCallback(() => {
    const slug = tagDraft
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "");
    if (!slug) return;
    if (atom.tags.includes(slug)) {
      setTagDraft("");
      return;
    }
    onUpdate({ tags: [...atom.tags, slug].slice(0, 5) });
    setTagDraft("");
  }, [atom.tags, onUpdate, tagDraft]);

  const removeTag = useCallback(
    (slug: string) =>
      onUpdate({ tags: atom.tags.filter((t) => t !== slug) }),
    [atom.tags, onUpdate],
  );

  const accentBg = atom.cluster_color ?? "#94a3b8";
  const showBody = bodyExpanded || atom.body.length <= 240;
  const previewBody = showBody ? atom.body : `${atom.body.slice(0, 240)}…`;

  return (
    <div
      className={`relative rounded-xl ring-1 transition overflow-hidden ${
        dropped
          ? "ring-white/5 bg-white/[0.005] opacity-50"
          : "ring-white/10 bg-white/[0.015] hover:ring-white/20"
      }`}
    >
      {/* Cluster accent stripe */}
      <div
        className="absolute left-0 top-0 bottom-0 w-1"
        style={{
          background: dropped
            ? "transparent"
            : `linear-gradient(180deg, ${accentBg}, ${accentBg}55)`,
        }}
      />

      <div className="pl-5 pr-4 py-4 space-y-3">
        <div className="flex items-start gap-3">
          <span className="text-[10px] font-mono text-ink-400 mt-1.5 w-6 shrink-0">
            #{index}
          </span>
          <div className="flex-1 min-w-0">
            <input
              value={atom.title}
              onChange={(e) => onUpdate({ title: e.target.value })}
              className="w-full bg-transparent text-[15px] font-semibold text-ink-100 leading-tight outline-none focus:bg-white/[0.03] rounded px-1 -mx-1 transition"
              maxLength={140}
            />
            <div className="flex items-center gap-2 mt-1 text-[10px] font-mono text-ink-400">
              {atom.llm_refined && modeUsed === "llm" && (
                <span className="text-synapse-amber">✨ llm-refined</span>
              )}
              <span>{atom.char_count.toLocaleString()} chars</span>
              <span>·</span>
              <span>
                {atom.expected_synapses === 0 ? (
                  <span className="text-synapse-pink">
                    will be an orphan
                  </span>
                ) : (
                  <span className="text-synapse-cyan">
                    {atom.expected_synapses} synapse
                    {atom.expected_synapses === 1 ? "" : "s"} predicted
                  </span>
                )}
              </span>
              {atom.cluster_id !== null && (
                <>
                  <span>·</span>
                  <span style={{ color: atom.cluster_color ?? "#a3a3a3" }}>
                    will join {atom.cluster_name} (
                    {(atom.cluster_strength * 100).toFixed(0)}% match)
                  </span>
                </>
              )}
            </div>
          </div>
          <button
            onClick={onToggleDrop}
            className={`shrink-0 px-2 py-1 rounded-md ring-1 font-mono text-[10px] transition ${
              dropped
                ? "ring-synapse-lime/40 text-synapse-lime hover:ring-synapse-lime/70"
                : "ring-white/10 text-ink-400 hover:ring-synapse-pink/40 hover:text-synapse-pink"
            }`}
            title={dropped ? "restore" : "drop this atom"}
          >
            {dropped ? "↺ restore" : "✕ drop"}
          </button>
        </div>

        {!dropped && (
          <>
            <textarea
              value={atom.body}
              onChange={(e) => onUpdate({ body: e.target.value })}
              rows={Math.min(8, Math.max(2, Math.ceil(previewBody.length / 90)))}
              className="w-full bg-white/[0.02] ring-1 ring-white/5 focus:ring-synapse-violet/40 rounded-md p-2.5 font-mono text-[12px] text-ink-200 leading-relaxed resize-y outline-none transition"
              onFocus={() => setBodyExpanded(true)}
              spellCheck={false}
            />

            <div className="flex flex-wrap items-center gap-1.5">
              {atom.tags.map((tag) => (
                <button
                  key={tag}
                  onClick={() => removeTag(tag)}
                  className="group inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-white/[0.04] ring-1 ring-white/10 hover:ring-synapse-pink/40 hover:text-synapse-pink text-[10px] font-mono text-ink-200 transition"
                  title="click to remove"
                >
                  #{tag}
                  <span className="opacity-0 group-hover:opacity-100 transition">
                    ✕
                  </span>
                </button>
              ))}
              {atom.tags.length < 5 && (
                <input
                  value={tagDraft}
                  onChange={(e) => setTagDraft(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === ",") {
                      e.preventDefault();
                      addTag();
                    }
                  }}
                  onBlur={() => tagDraft && addTag()}
                  placeholder="+ tag"
                  className="bg-transparent w-20 outline-none placeholder:text-ink-400 text-[10px] font-mono text-ink-100 px-1.5 py-0.5 rounded-full ring-1 ring-dashed ring-white/10 focus:ring-synapse-violet/60 transition"
                />
              )}
            </div>

            {atom.neighbors.length > 0 ? (
              <div className="flex flex-wrap items-center gap-1.5 text-[11px] font-mono">
                <span className="text-ink-400">will synapse to:</span>
                {atom.neighbors.map((n) => {
                  const real = nodes.find((x) => x.id === n.note_id);
                  return (
                    <button
                      key={n.note_id}
                      onClick={() => {
                        if (real) onPreviewNeighbor?.(real);
                      }}
                      className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md bg-white/[0.025] ring-1 ring-white/5 hover:ring-synapse-cyan/40 text-ink-200 hover:text-ink-100 transition max-w-[26ch]"
                      title={`cosine ${(n.strength * 100).toFixed(0)}% · #${n.note_id}`}
                    >
                      <span
                        className="w-1.5 h-1.5 rounded-full shrink-0"
                        style={{ background: n.cluster_color ?? "#22d3ee" }}
                      />
                      <span className="truncate">{n.title}</span>
                      <span className="text-synapse-cyan">
                        {(n.strength * 100).toFixed(0)}%
                      </span>
                    </button>
                  );
                })}
              </div>
            ) : (
              <div className="text-[11px] font-mono text-ink-400">
                no neighbors above τ — will surface in orphan rescue panel
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

// -------------------------------------------------------------------- done

function DoneStage({
  count,
  synapses,
  onClose,
  onDistillMore,
}: {
  count: number;
  synapses: number;
  onClose: () => void;
  onDistillMore: () => void;
}) {
  return (
    <div className="py-16 flex flex-col items-center text-center gap-5">
      <div className="relative w-20 h-20 grid place-items-center">
        <div className="absolute inset-0 rounded-full bg-gradient-to-br from-synapse-lime/30 to-synapse-cyan/30 blur-xl" />
        <div className="relative w-16 h-16 rounded-full ring-2 ring-synapse-lime/60 grid place-items-center text-synapse-lime text-2xl">
          ✓
        </div>
      </div>
      <div>
        <div className="text-lg font-semibold text-ink-100">
          {count} atom{count === 1 ? "" : "s"} landed in your graph
        </div>
        <div className="text-sm text-ink-300 mt-1">
          {synapses === 0 ? (
            <>No synapses formed yet — try lowering τ in the graph view.</>
          ) : (
            <>
              <span className="text-synapse-cyan">{synapses}</span> synapse
              {synapses === 1 ? "" : "s"} formed against existing notes.
            </>
          )}
        </div>
      </div>
      <div className="flex items-center gap-3 pt-2">
        <button
          onClick={onDistillMore}
          className="px-3 py-2 rounded-lg ring-1 ring-white/10 hover:ring-white/30 text-ink-300 hover:text-ink-100 font-mono text-xs transition"
        >
          distill more
        </button>
        <button
          onClick={onClose}
          className="px-4 py-2 rounded-lg bg-gradient-to-r from-synapse-violet/30 to-synapse-cyan/30 ring-1 ring-synapse-violet/60 hover:ring-synapse-violet text-ink-100 font-mono text-xs transition"
        >
          back to graph →
        </button>
      </div>
    </div>
  );
}
