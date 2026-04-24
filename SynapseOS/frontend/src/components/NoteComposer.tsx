"use client";

import { useState } from "react";

type Props = {
  onCreate: (payload: { title: string; body: string; tags: string[] }) => Promise<void>;
};

export function NoteComposer({ onCreate }: Props) {
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [tagsRaw, setTagsRaw] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

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
      onSubmit={submit}
      className="rounded-xl bg-ink-800/60 ring-1 ring-white/5 shadow-card p-4 space-y-3"
    >
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
