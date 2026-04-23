"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import clsx from "clsx";
import { FileText, Plus, ArrowRight, Search } from "lucide-react";
import { useStore } from "@/lib/store";

export default function CommandPalette() {
  const open = useStore((s) => s.commandOpen);
  const openCommand = useStore((s) => s.openCommand);
  const notes = useStore((s) => s.notes);
  const setActive = useStore((s) => s.setActive);
  const createFromTitle = useStore((s) => s.createFromTitle);

  const [q, setQ] = useState("");
  const [cursor, setCursor] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  // Global ⌘K / Ctrl+K to open.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const mod = e.metaKey || e.ctrlKey;
      if (mod && e.key.toLowerCase() === "k") {
        e.preventDefault();
        openCommand(true);
      }
      if (e.key === "Escape") openCommand(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [openCommand]);

  useEffect(() => {
    if (open) {
      setQ("");
      setCursor(0);
      setTimeout(() => inputRef.current?.focus(), 30);
    }
  }, [open]);

  const results = useMemo(() => {
    const ql = q.trim().toLowerCase();
    if (!ql) return notes.slice(0, 10);
    return notes
      .map((n) => ({
        n,
        score: score(n.title.toLowerCase(), ql) * 3 + score(n.body.toLowerCase(), ql),
      }))
      .filter((r) => r.score > 0)
      .sort((a, b) => b.score - a.score)
      .slice(0, 8)
      .map((r) => r.n);
  }, [q, notes]);

  const canCreate = q.trim().length > 0 && !results.some((n) => n.title.toLowerCase() === q.trim().toLowerCase());
  const totalItems = results.length + (canCreate ? 1 : 0);

  if (!open) return null;

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setCursor((c) => Math.min(totalItems - 1, c + 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setCursor((c) => Math.max(0, c - 1));
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (cursor < results.length) {
        setActive(results[cursor].id);
      } else if (canCreate) {
        createFromTitle(q.trim());
      }
      openCommand(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center pt-28 px-4"
      onClick={() => openCommand(false)}
    >
      <div className="absolute inset-0 bg-void-900/70 backdrop-blur-sm" />
      <div
        className="relative w-full max-w-xl rounded-2xl surface shadow-glowViolet overflow-hidden animate-fade-up"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-3 px-4 py-3 border-b border-white/5">
          <Search className="w-4 h-4 text-synapse-cyan" />
          <input
            ref={inputRef}
            value={q}
            onChange={(e) => {
              setQ(e.target.value);
              setCursor(0);
            }}
            onKeyDown={onKeyDown}
            placeholder="Jump to, or create a note..."
            className="flex-1 bg-transparent text-sm focus:outline-none placeholder:text-ink-400"
          />
          <kbd className="text-[10px] px-1.5 py-0.5 rounded border border-white/10 text-ink-400">
            esc
          </kbd>
        </div>
        <ul className="max-h-80 overflow-y-auto py-1">
          {results.map((n, i) => (
            <li key={n.id}>
              <button
                onClick={() => {
                  setActive(n.id);
                  openCommand(false);
                }}
                onMouseEnter={() => setCursor(i)}
                className={clsx(
                  "w-full flex items-center gap-3 px-4 py-2 text-left text-sm transition",
                  i === cursor ? "bg-synapse-cyan/10" : "hover:bg-white/5",
                )}
              >
                <FileText className="w-4 h-4 text-ink-400" />
                <div className="flex-1 min-w-0">
                  <div className="truncate text-ink-100">{n.title}</div>
                  <div className="truncate text-[11px] text-ink-400">
                    {n.body.replace(/[#*`>\[\]]/g, "").slice(0, 80)}
                  </div>
                </div>
                <ArrowRight className="w-3.5 h-3.5 text-ink-400" />
              </button>
            </li>
          ))}
          {canCreate && (
            <li>
              <button
                onClick={() => {
                  createFromTitle(q.trim());
                  openCommand(false);
                }}
                onMouseEnter={() => setCursor(results.length)}
                className={clsx(
                  "w-full flex items-center gap-3 px-4 py-2 text-left text-sm transition",
                  cursor === results.length
                    ? "bg-synapse-violet/15"
                    : "hover:bg-white/5",
                )}
              >
                <Plus className="w-4 h-4 text-synapse-violet" />
                <div className="flex-1">
                  <div className="text-ink-100">
                    Create <span className="text-synapse-violet">&ldquo;{q}&rdquo;</span>
                  </div>
                  <div className="text-[11px] text-ink-400">New note</div>
                </div>
              </button>
            </li>
          )}
          {results.length === 0 && !canCreate && (
            <li className="px-4 py-6 text-center text-ink-400 text-sm">
              No matches. Keep typing to create.
            </li>
          )}
        </ul>
        <div className="px-4 py-2 border-t border-white/5 text-[10px] text-ink-400 flex items-center gap-3">
          <span>↑↓ navigate</span>
          <span>↵ open</span>
          <span>type to create</span>
        </div>
      </div>
    </div>
  );
}

/** Tiny fuzzy-ish scorer: prefix > substring > subseq. */
function score(hay: string, needle: string): number {
  if (!needle) return 0;
  if (hay.startsWith(needle)) return 100;
  const idx = hay.indexOf(needle);
  if (idx >= 0) return 60 - Math.min(50, idx);
  let hi = 0;
  let ni = 0;
  let run = 0;
  let best = 0;
  while (hi < hay.length && ni < needle.length) {
    if (hay[hi] === needle[ni]) {
      run++;
      ni++;
      best = Math.max(best, run);
    } else {
      run = 0;
    }
    hi++;
  }
  if (ni === needle.length) return 10 + best;
  return 0;
}
