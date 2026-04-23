"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import clsx from "clsx";
import { Eye, Pencil, Link2 } from "lucide-react";
import { useStore } from "@/lib/store";
import { renderMarkdown } from "@/lib/markdown";
import { extractWikilinks } from "@/lib/wikilinks";

export default function NoteEditor() {
  const notes = useStore((s) => s.notes);
  const activeId = useStore((s) => s.activeId);
  const updateNote = useStore((s) => s.updateNote);
  const openOrCreate = useStore((s) => s.openOrCreate);
  const [mode, setMode] = useState<"edit" | "preview" | "split">("split");
  const previewRef = useRef<HTMLDivElement>(null);

  const note = useMemo(
    () => notes.find((n) => n.id === activeId) ?? null,
    [notes, activeId],
  );

  // Wire clicks on rendered wikilinks back into the store.
  useEffect(() => {
    const el = previewRef.current;
    if (!el) return;
    const onClick = (e: MouseEvent) => {
      const target = e.target as HTMLElement;
      const a = target.closest<HTMLElement>("[data-wikilink]");
      if (a) {
        e.preventDefault();
        const title = a.dataset.title;
        if (title) openOrCreate(title);
      }
    };
    el.addEventListener("click", onClick);
    return () => el.removeEventListener("click", onClick);
  }, [openOrCreate, note?.id]);

  if (!note) {
    return (
      <div className="flex-1 flex items-center justify-center text-ink-400">
        Select or create a note from the sidebar.
      </div>
    );
  }

  const linkCount = extractWikilinks(note.body).length;
  const words = note.body.trim() ? note.body.trim().split(/\s+/).length : 0;
  const html = renderMarkdown(note.body, notes);

  return (
    <section className="flex-1 flex flex-col min-w-0 h-full">
      {/* Toolbar */}
      <header className="flex items-center justify-between px-6 py-3 border-b border-white/5 bg-void-800/40">
        <div className="flex-1 min-w-0">
          <input
            value={note.title}
            onChange={(e) => updateNote(note.id, { title: e.target.value })}
            className="w-full bg-transparent text-lg font-semibold tracking-tight focus:outline-none"
            placeholder="Untitled"
          />
          <div className="text-[11px] text-ink-400 flex items-center gap-3 mt-0.5">
            <span>{words} words</span>
            <span className="flex items-center gap-1">
              <Link2 className="w-3 h-3" /> {linkCount} links
            </span>
            <span>{note.tags.length > 0 && `#${note.tags.join(" #")}`}</span>
          </div>
        </div>
        <div className="flex items-center gap-1 rounded-lg bg-void-700/60 border border-white/5 p-1 text-xs">
          <ToolbarButton active={mode === "edit"} onClick={() => setMode("edit")} icon={<Pencil className="w-3.5 h-3.5" />} label="Edit" />
          <ToolbarButton active={mode === "split"} onClick={() => setMode("split")} icon={<SplitIcon />} label="Split" />
          <ToolbarButton active={mode === "preview"} onClick={() => setMode("preview")} icon={<Eye className="w-3.5 h-3.5" />} label="Read" />
        </div>
      </header>

      {/* Editor + Preview */}
      <div className="flex-1 overflow-hidden flex">
        {(mode === "edit" || mode === "split") && (
          <div
            className={clsx(
              "h-full overflow-y-auto",
              mode === "split"
                ? "w-1/2 border-r border-white/5"
                : "flex-1",
            )}
          >
            <textarea
              value={note.body}
              onChange={(e) => updateNote(note.id, { body: e.target.value })}
              spellCheck={false}
              className="w-full h-full bg-transparent px-8 py-6 resize-none font-mono text-[13.5px] leading-[1.7] text-ink-200 placeholder:text-ink-400 focus:outline-none"
              placeholder={"Start writing... use [[Title]] to link and #tag for tags."}
            />
          </div>
        )}
        {(mode === "preview" || mode === "split") && (
          <div
            ref={previewRef}
            className={clsx(
              "h-full overflow-y-auto px-8 py-6",
              mode === "split" ? "w-1/2" : "flex-1",
            )}
          >
            <article
              className="prose-synapse max-w-2xl mx-auto"
              dangerouslySetInnerHTML={{ __html: html }}
            />
          </div>
        )}
      </div>
    </section>
  );
}

function ToolbarButton({
  active,
  onClick,
  icon,
  label,
}: {
  active: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  label: string;
}) {
  return (
    <button
      onClick={onClick}
      className={clsx(
        "flex items-center gap-1 px-2.5 py-1 rounded-md transition",
        active
          ? "bg-synapse-cyan/15 text-synapse-cyan"
          : "text-ink-300 hover:text-ink-100",
      )}
    >
      {icon}
      <span>{label}</span>
    </button>
  );
}

function SplitIcon() {
  return (
    <svg viewBox="0 0 24 24" className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth="2">
      <rect x="3" y="5" width="18" height="14" rx="2" />
      <line x1="12" y1="5" x2="12" y2="19" />
    </svg>
  );
}
