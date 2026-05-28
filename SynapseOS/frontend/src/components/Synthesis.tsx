"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { ClusterDigest, GraphNode } from "@/lib/types";

type NoteStub = Pick<GraphNode, "id" | "title" | "body" | "tags" | "degree" | "weight">;

type Props = {
  open: boolean;
  clusterId: number | null;
  /** Loaded so the header can show the name/color before the fetch lands. */
  fallbackName?: string | null;
  fallbackColor?: string | null;
  onClose: () => void;
  onSelectNote: (node: NoteStub) => void;
};

/**
 * Synthesis — auto-written topic briefings.
 *
 * The topic palette shows you *that* a cluster exists and what it's
 * called. Synthesis tells you what it *says*: a cited synthesis paragraph,
 * the key claims, the open threads you haven't resolved, and the bridges
 * to other topics the graph hasn't drawn yet. Every claim links back to
 * the source note, and the whole thing exports to portable Markdown.
 */
export function Synthesis({
  open,
  clusterId,
  fallbackName,
  fallbackColor,
  onClose,
  onSelectNote,
}: Props) {
  const [digest, setDigest] = useState<ClusterDigest | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open || clusterId === null) return;
    setLoading(true);
    setError(null);
    setDigest(null);
    api
      .digest(clusterId)
      .then(setDigest)
      .catch((e) => setError(e instanceof Error ? e.message : "failed to synthesize"))
      .finally(() => setLoading(false));
  }, [open, clusterId]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  const color = digest?.color ?? fallbackColor ?? "#a855f7";
  const name = digest?.name ?? fallbackName ?? "Topic";

  const openNote = (id: number, title: string) => {
    onSelectNote({ id, title, body: "", tags: [], degree: 0, weight: 0 });
    onClose();
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center px-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="synth-title"
    >
      <div className="absolute inset-0 bg-ink-900/80 backdrop-blur-md" onClick={onClose} />
      <div className="absolute inset-0 pointer-events-none bg-grid-fade opacity-60" />

      <div className="relative w-full max-w-3xl max-h-[88vh] flex flex-col rounded-2xl bg-ink-800/90 ring-1 ring-white/10 shadow-card overflow-hidden animate-fade-in">
        {/* Header strip, tinted with the cluster's own color. */}
        <div
          className="flex items-center justify-between gap-4 px-6 py-4 border-b border-white/5"
          style={{
            background: `linear-gradient(90deg, ${color}14, transparent 60%)`,
          }}
        >
          <div className="flex items-center gap-3 min-w-0">
            <CohesionRing value={digest?.cohesion ?? 0} color={color} />
            <div className="min-w-0">
              <div
                id="synth-title"
                className="text-base font-semibold tracking-tight text-ink-100 truncate flex items-center gap-2"
              >
                <span
                  className="w-2.5 h-2.5 rounded-full shrink-0"
                  style={{ background: color, boxShadow: `0 0 10px ${color}` }}
                />
                {name}
                <span className="text-[11px] font-normal text-ink-300">synthesis</span>
              </div>
              <div className="text-[11px] font-mono text-ink-300 mt-0.5">
                {digest
                  ? `${digest.size} note${digest.size === 1 ? "" : "s"} · cohesion ${pct(digest.cohesion)}`
                  : "synthesizing…"}
                {digest && digest.terms.length > 0 && (
                  <> · {digest.terms.slice(0, 3).join(" · ")}</>
                )}
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            {digest && (
              <span
                className={`hidden sm:inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 font-mono text-[10px] ring-1 ${
                  digest.mode_used === "llm"
                    ? "ring-synapse-violet/40 text-synapse-violet bg-synapse-violet/10"
                    : "ring-white/10 text-ink-300"
                }`}
                title={
                  digest.mode_used === "llm"
                    ? `synthesized by ${digest.llm_provider ?? "LLM"}`
                    : "deterministic extractive synthesis (no LLM key set)"
                }
              >
                {digest.mode_used === "llm" ? "✨ llm" : "extractive"}
              </span>
            )}
            {clusterId !== null && (
              <a
                href={api.digestExportUrl(clusterId)}
                className="inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 font-mono text-[11px] ring-1 ring-synapse-cyan/40 text-synapse-cyan hover:bg-synapse-cyan/10 transition"
                title="download as portable Markdown"
              >
                ⤓ md
              </a>
            )}
            <button
              onClick={onClose}
              className="text-ink-300 hover:text-ink-100 text-xs font-mono px-2 py-1 rounded ring-1 ring-white/10 hover:ring-synapse-pink/40 transition"
              aria-label="close"
            >
              esc
            </button>
          </div>
        </div>

        <div className="px-6 py-6 overflow-y-auto">
          {loading && <SynthSkeleton />}
          {error && !loading && (
            <div className="text-sm font-mono text-synapse-pink">
              {error} — start the backend with{" "}
              <span className="text-ink-100">uvicorn app.main:app --reload</span>
            </div>
          )}
          {!loading && !error && digest && (
            <DigestBody digest={digest} onOpen={openNote} color={color} />
          )}
        </div>
      </div>
    </div>
  );
}

// --------------------------------------------------------------- body

function DigestBody({
  digest,
  onOpen,
  color,
}: {
  digest: ClusterDigest;
  onOpen: (id: number, title: string) => void;
  color: string;
}) {
  const refTitle = (ref: number) =>
    digest.sources.find((s) => s.ref === ref)?.title ?? `note ${ref}`;
  const refNote = (ref: number) => digest.sources.find((s) => s.ref === ref)?.note_id;

  return (
    <div className="space-y-6 animate-fade-in">
      {digest.notice && (
        <div className="text-[11px] font-mono text-synapse-amber/90 rounded-md ring-1 ring-synapse-amber/30 bg-synapse-amber/[0.06] px-3 py-2">
          {digest.notice}
        </div>
      )}

      {/* Synthesis prose */}
      {digest.overview && (
        <section>
          <SectionLabel color={color}>synthesis</SectionLabel>
          <p className="text-[15px] leading-relaxed text-ink-100">
            <CitedText
              text={digest.overview}
              onCite={(ref) => {
                const id = refNote(ref);
                if (id) onOpen(id, refTitle(ref));
              }}
              titleOf={refTitle}
            />
          </p>
        </section>
      )}

      {/* Key claims */}
      {digest.claims.length > 0 && (
        <section>
          <SectionLabel color={color}>key claims</SectionLabel>
          <ul className="space-y-2">
            {digest.claims.map((c, i) => (
              <li
                key={`${c.note_id}-${i}`}
                className="flex gap-2.5 text-sm leading-relaxed text-ink-200"
              >
                <span className="mt-1.5 w-1.5 h-1.5 rounded-full shrink-0" style={{ background: color }} />
                <span className="flex-1">
                  {c.text}{" "}
                  <Citation n={c.ref} title={refTitle(c.ref)} onClick={() => onOpen(c.note_id, refTitle(c.ref))} />
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Open threads */}
      {digest.open_threads.length > 0 && (
        <section>
          <SectionLabel color="#fbbf24">open threads</SectionLabel>
          <ul className="space-y-1.5">
            {digest.open_threads.map((t) => (
              <li key={`${t.kind}-${t.note_id}`}>
                <button
                  onClick={() => onOpen(t.note_id, t.title)}
                  className="group w-full text-left flex items-start gap-2.5 rounded-lg ring-1 ring-white/5 bg-white/[0.015] hover:bg-white/[0.04] px-3 py-2 transition"
                >
                  <span
                    className={`mt-0.5 text-sm shrink-0 ${
                      t.kind === "question" ? "text-synapse-amber" : "text-synapse-pink"
                    }`}
                    aria-hidden
                  >
                    {t.kind === "question" ? "?" : "○"}
                  </span>
                  <span className="flex-1 min-w-0">
                    <span className="block text-sm text-ink-100 group-hover:text-synapse-cyan transition leading-snug">
                      {t.text}
                    </span>
                    <span className="block text-[10px] font-mono text-ink-400 mt-0.5 truncate">
                      {t.kind === "question" ? "unanswered in" : "stub —"} {t.title}
                    </span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Bridges */}
      {digest.bridges.length > 0 && (
        <section>
          <SectionLabel color={color}>bridges to other topics</SectionLabel>
          <p className="text-[11px] text-ink-400 mb-2 leading-relaxed">
            Notes elsewhere in your graph that are close to this topic but
            aren&apos;t linked yet — a τ nudge away from a synapse.
          </p>
          <ul className="space-y-1.5">
            {digest.bridges.map((b) => (
              <li
                key={b.note_id}
                className="flex items-center gap-2 rounded-lg ring-1 ring-white/5 bg-white/[0.015] px-3 py-2"
              >
                <span className="text-ink-400 text-sm shrink-0">↝</span>
                <button
                  onClick={() => onOpen(b.note_id, b.title)}
                  className="flex-1 text-left text-sm text-ink-100 truncate hover:text-synapse-cyan transition"
                  title={b.title}
                >
                  {b.title}
                </button>
                <span
                  className="text-[10px] font-mono shrink-0 inline-flex items-center gap-1"
                  style={{ color: b.cluster_color }}
                  title={`currently in ${b.cluster_name}`}
                >
                  <span className="w-1.5 h-1.5 rounded-full" style={{ background: b.cluster_color }} />
                  {b.cluster_name}
                </span>
                <span className="text-[11px] font-mono text-synapse-cyan/90 shrink-0">
                  {pct(b.strength)}
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Sources */}
      {digest.sources.length > 0 && (
        <section>
          <SectionLabel color={color}>sources</SectionLabel>
          <ol className="space-y-1">
            {digest.sources.map((s) => (
              <li key={s.note_id} className="flex items-center gap-2 text-sm">
                <span className="font-mono text-[11px] text-ink-400 w-5 shrink-0">{s.ref}.</span>
                <button
                  onClick={() => onOpen(s.note_id, s.title)}
                  className="flex-1 text-left text-ink-200 truncate hover:text-synapse-cyan transition"
                  title={s.title}
                >
                  {s.title}
                </button>
                <span
                  className="text-[10px] font-mono shrink-0"
                  title="how central this note is to the topic"
                  style={{ color }}
                >
                  {pct(s.centrality)}
                </span>
              </li>
            ))}
          </ol>
        </section>
      )}

      {digest.overview === "" && digest.claims.length === 0 && (
        <div className="text-center py-8 space-y-2">
          <div className="text-2xl">◌</div>
          <p className="text-sm text-ink-200">This cluster is too thin to synthesize yet.</p>
          <p className="text-[11px] text-ink-400">Add more to these notes and try again.</p>
        </div>
      )}
    </div>
  );
}

// --------------------------------------------------------------- bits

function SectionLabel({ children, color }: { children: React.ReactNode; color: string }) {
  return (
    <div
      className="text-[10px] font-semibold uppercase tracking-[0.16em] mb-2"
      style={{ color }}
    >
      {children}
    </div>
  );
}

/** Inline superscript citation chip, e.g. the [3] after a sentence. */
function Citation({
  n,
  title,
  onClick,
}: {
  n: number;
  title: string;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      title={title}
      className="align-super text-[10px] font-mono px-1 rounded text-synapse-cyan/80 hover:text-synapse-cyan hover:bg-synapse-cyan/10 ring-1 ring-synapse-cyan/30 transition"
    >
      {n}
    </button>
  );
}

/** Renders text with inline `[#N]` markers turned into clickable chips. */
function CitedText({
  text,
  onCite,
  titleOf,
}: {
  text: string;
  onCite: (ref: number) => void;
  titleOf: (ref: number) => string;
}) {
  const parts = text.split(/(\[#\d+\])/g);
  return (
    <>
      {parts.map((p, i) => {
        const m = p.match(/^\[#(\d+)\]$/);
        if (m) {
          const ref = parseInt(m[1], 10);
          return <Citation key={i} n={ref} title={titleOf(ref)} onClick={() => onCite(ref)} />;
        }
        return <span key={i}>{p}</span>;
      })}
    </>
  );
}

function CohesionRing({ value, color }: { value: number; color: string }) {
  const v = Math.max(0, Math.min(1, value));
  const deg = Math.round(v * 360);
  return (
    <div
      className="relative w-12 h-12 rounded-full shrink-0"
      style={{ background: `conic-gradient(${color} ${deg}deg, rgba(255,255,255,0.06) ${deg}deg)` }}
      aria-label={`cohesion ${pct(value)}`}
      title={`cohesion ${pct(value)} — how tightly this topic holds together`}
    >
      <div className="absolute inset-[3px] rounded-full bg-ink-800 flex items-center justify-center">
        <span className="font-mono text-[10px] text-ink-100">{Math.round(v * 100)}</span>
      </div>
    </div>
  );
}

function SynthSkeleton() {
  return (
    <div className="space-y-5 animate-fade-in">
      <div className="h-4 w-1/3 rounded bg-white/[0.05]" />
      <div className="space-y-2">
        <div className="h-4 w-full rounded bg-white/[0.03]" />
        <div className="h-4 w-11/12 rounded bg-white/[0.03]" />
        <div className="h-4 w-2/3 rounded bg-white/[0.03]" />
      </div>
      <div className="h-4 w-1/4 rounded bg-white/[0.05]" />
      <div className="h-10 w-full rounded-lg bg-white/[0.02]" />
      <div className="h-10 w-full rounded-lg bg-white/[0.02]" />
    </div>
  );
}

function pct(x: number): string {
  return `${Math.round(x * 100)}%`;
}
