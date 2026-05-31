"use client";

import { useEffect, useRef, useState } from "react";
import type { NoteDraft } from "@/lib/types";

type Props = {
  onCreate: (payload: { title: string; body: string; tags: string[] }) => Promise<void>;
  /**
   * When non-null, pre-fill the composer with this draft and scroll
   * into view. Used by Tensions's Reconcile action to hand the user a
   * bridge note that's 80% written. The parent should clear the prop
   * when the draft has been consumed.
   */
  draft?: NoteDraft | null;
  onDraftConsumed?: () => void;
};

export function NoteComposer({ onCreate, draft, onDraftConsumed }: Props) {
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [tagsRaw, setTagsRaw] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [flashFrom, setFlashFrom] = useState<"reconcile" | null>(null);
  const wrapRef = useRef<HTMLFormElement>(null);
  const bodyRef = useRef<HTMLTextAreaElement>(null);

  // Hydrate from an external draft. We scroll the composer into view
  // and focus the body so the user can immediately type — the title is
  // already a sensible suggestion, the bridge prompt is in the body.
  useEffect(() => {
    if (!draft) return;
    setTitle(draft.title);
    setBody(draft.body);
    setTagsRaw(draft.tags.join(", "));
    setErr(null);
    setFlashFrom("reconcile");
    onDraftConsumed?.();
    // Scroll + focus on the next paint so React has committed the new
    // value before the textarea receives focus.
    requestAnimationFrame(() => {
      wrapRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
      bodyRef.current?.focus();
      bodyRef.current?.setSelectionRange(0, 0);
    });
    const t = window.setTimeout(() => setFlashFrom(null), 2200);
    return () => window.clearTimeout(t);
  }, [draft, onDraftConsumed]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!title.trim() || !body.trim()) return;
    setBusy(true);
    setErr(null);
    try {
      const tags = tagsRaw
        .split(",")
        .map((t) => t.trim().toLowerCase())
        .filter(Boolean);
      await onCreate({ title: title.trim(), body: body.trim(), tags });
      setTitle("");
      setBody("");
      setTagsRaw("");
    } catch (e) {
      setErr(e instanceof Error ? e.message : "failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form
      ref={wrapRef}
      onSubmit={submit}
      className={`relative rounded-xl bg-ink-800/60 ring-1 p-4 space-y-3 transition shadow-card ${
        flashFrom === "reconcile"
          ? "ring-rose-400/60 shadow-[0_0_24px_-4px_rgba(244,63,94,0.5)]"
          : "ring-white/5"
      }`}
    >
      {flashFrom === "reconcile" && (
        <div className="absolute -top-2 left-3 px-2 py-0.5 rounded-full bg-gradient-to-r from-rose-500 to-synapse-violet text-[10px] font-mono text-ink-900 uppercase tracking-widest shadow-glow">
          ⤴ reconciling
        </div>
      )}
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-semibold uppercase tracking-[0.16em] text-ink-200">
          new thought
        </h3>
        <span className="text-[10px] text-ink-400 font-mono">
          synapses form automatically
        </span>
      </div>
      <input
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        placeholder="title — one atomic idea"
        className="w-full rounded-lg bg-ink-900/60 ring-1 ring-white/5 px-3 py-2 text-sm text-ink-100 placeholder:text-ink-400 focus-ring"
      />
      <textarea
        ref={bodyRef}
        value={body}
        onChange={(e) => setBody(e.target.value)}
        placeholder="write the note. the graph will connect it for you."
        rows={4}
        className="w-full resize-none rounded-lg bg-ink-900/60 ring-1 ring-white/5 px-3 py-2 text-sm text-ink-100 placeholder:text-ink-400 focus-ring"
      />
      <div className="flex items-center gap-2">
        <input
          value={tagsRaw}
          onChange={(e) => setTagsRaw(e.target.value)}
          placeholder="tags, comma, separated"
          className="flex-1 rounded-lg bg-ink-900/60 ring-1 ring-white/5 px-3 py-2 text-xs text-ink-100 placeholder:text-ink-400 focus-ring font-mono"
        />
        <button
          disabled={busy || !title.trim() || !body.trim()}
          className="rounded-lg px-4 py-2 text-sm font-medium text-ink-900 bg-gradient-to-r from-synapse-cyan to-synapse-violet disabled:opacity-40 disabled:cursor-not-allowed hover:brightness-110 transition shadow-glow"
        >
          {busy ? "wiring…" : "commit"}
        </button>
      </div>
      {err && <p className="text-xs text-synapse-pink">{err}</p>}
    </form>
  );
}
