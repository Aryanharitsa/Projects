"use client";

import { useMemo } from "react";
import clsx from "clsx";
import {
  Plus,
  Search,
  Hash,
  Trash2,
  FileText,
  Network,
  Command,
} from "lucide-react";
import { useStore } from "@/lib/store";
import { backlinksOf, buildLinks } from "@/lib/wikilinks";

export default function Sidebar() {
  const notes = useStore((s) => s.notes);
  const activeId = useStore((s) => s.activeId);
  const query = useStore((s) => s.query);
  const setQuery = useStore((s) => s.setQuery);
  const setActive = useStore((s) => s.setActive);
  const createNote = useStore((s) => s.createNote);
  const deleteNote = useStore((s) => s.deleteNote);
  const openCommand = useStore((s) => s.openCommand);
  const toggleGraph = useStore((s) => s.toggleGraph);
  const graphOpen = useStore((s) => s.graphOpen);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    const sorted = [...notes].sort((a, b) => b.updatedAt - a.updatedAt);
    if (!q) return sorted;
    return sorted.filter(
      (n) =>
        n.title.toLowerCase().includes(q) ||
        n.body.toLowerCase().includes(q) ||
        n.tags.some((t) => t.includes(q.replace(/^#/, ""))),
    );
  }, [notes, query]);

  const stats = useMemo(() => {
    const links = buildLinks(notes);
    const resolved = links.filter((l) => l.resolved).length;
    return { notes: notes.length, links: resolved, ghosts: links.length - resolved };
  }, [notes]);

  return (
    <aside className="w-72 shrink-0 border-r border-white/5 bg-void-800/60 flex flex-col h-full">
      {/* Brand */}
      <div className="px-4 pt-5 pb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <SynapseMark />
          <div>
            <div className="font-semibold tracking-tight">SynapseOS</div>
            <div className="text-[10px] uppercase tracking-[0.18em] text-ink-400">
              Your thoughts, connected
            </div>
          </div>
        </div>
      </div>

      {/* Search */}
      <div className="px-3">
        <label className="relative block">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-ink-400" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search notes..."
            className="w-full pl-9 pr-12 py-2 rounded-lg bg-void-700/80 border border-white/5 text-sm placeholder:text-ink-400"
          />
          <button
            onClick={() => openCommand(true)}
            title="Command palette (⌘K)"
            className="absolute right-1.5 top-1/2 -translate-y-1/2 flex items-center gap-1 text-[10px] text-ink-400 px-1.5 py-0.5 rounded border border-white/5 bg-void-600/70 hover:text-ink-100"
          >
            <Command className="w-3 h-3" /> K
          </button>
        </label>
      </div>

      {/* Actions */}
      <div className="px-3 pt-3 flex items-center gap-2">
        <button
          onClick={() => createNote()}
          className="flex-1 flex items-center justify-center gap-1.5 py-2 rounded-lg text-sm bg-gradient-to-br from-synapse-cyan/20 to-synapse-violet/20 hover:from-synapse-cyan/30 hover:to-synapse-violet/30 border border-synapse-cyan/25 text-ink-100 transition-all"
        >
          <Plus className="w-4 h-4" /> New note
        </button>
        <button
          onClick={toggleGraph}
          title="Toggle graph"
          className={clsx(
            "px-2.5 py-2 rounded-lg border text-sm transition-all",
            graphOpen
              ? "bg-synapse-violet/20 border-synapse-violet/40 text-ink-100"
              : "bg-void-700/60 border-white/5 text-ink-300 hover:text-ink-100",
          )}
        >
          <Network className="w-4 h-4" />
        </button>
      </div>

      {/* Note list */}
      <div className="mt-3 px-1.5 flex-1 overflow-y-auto">
        <div className="px-2 pb-1.5 text-[10px] uppercase tracking-[0.18em] text-ink-400">
          Notes · {filtered.length}
        </div>
        <ul className="space-y-0.5">
          {filtered.map((n) => {
            const isActive = n.id === activeId;
            const backCount = backlinksOf(n.id, notes).length;
            return (
              <li key={n.id}>
                <div
                  className={clsx(
                    "group w-full text-left px-2.5 py-2 rounded-md text-sm border transition-all flex items-start gap-2",
                    isActive
                      ? "bg-synapse-cyan/10 border-synapse-cyan/30"
                      : "border-transparent hover:bg-white/5 hover:border-white/5",
                  )}
                >
                  <button
                    onClick={() => setActive(n.id)}
                    className="flex items-start gap-2 flex-1 min-w-0 text-left"
                  >
                    <FileText
                      className={clsx(
                        "w-4 h-4 mt-0.5 shrink-0",
                        isActive ? "text-synapse-cyan" : "text-ink-400",
                      )}
                    />
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-ink-100">{n.title}</div>
                      <div className="text-[11px] text-ink-400 flex items-center gap-1.5 mt-0.5">
                        <span>{timeAgo(n.updatedAt)}</span>
                        {backCount > 0 && (
                          <span className="px-1 py-px rounded bg-synapse-violet/15 text-synapse-violet border border-synapse-violet/25">
                            ← {backCount}
                          </span>
                        )}
                        {n.tags.slice(0, 2).map((t) => (
                          <span key={t} className="flex items-center gap-0.5 text-synapse-amber/80">
                            <Hash className="w-2.5 h-2.5" />
                            {t}
                          </span>
                        ))}
                      </div>
                    </div>
                  </button>
                  <button
                    onClick={() => {
                      if (confirm(`Delete "${n.title}"?`)) deleteNote(n.id);
                    }}
                    className="opacity-0 group-hover:opacity-100 text-ink-400 hover:text-synapse-magenta transition"
                    title="Delete"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              </li>
            );
          })}
        </ul>
      </div>

      {/* Stats footer */}
      <div className="px-4 py-3 border-t border-white/5 text-[11px] text-ink-400 flex items-center gap-3">
        <Stat label="notes" value={stats.notes} />
        <Stat label="links" value={stats.links} color="text-synapse-cyan" />
        <Stat label="ghosts" value={stats.ghosts} color="text-synapse-magenta" />
      </div>
    </aside>
  );
}

function Stat({
  label,
  value,
  color = "text-ink-100",
}: {
  label: string;
  value: number;
  color?: string;
}) {
  return (
    <div>
      <div className={clsx("font-semibold tabular-nums", color)}>{value}</div>
      <div className="uppercase tracking-wider text-[9px]">{label}</div>
    </div>
  );
}

function SynapseMark() {
  return (
    <div className="relative w-8 h-8">
      <div className="absolute inset-0 rounded-lg bg-gradient-to-br from-synapse-cyan via-synapse-violet to-synapse-magenta opacity-90" />
      <div className="absolute inset-[2px] rounded-[7px] bg-void-900 flex items-center justify-center">
        <svg viewBox="0 0 24 24" className="w-4 h-4" fill="none">
          <circle cx="6" cy="6" r="2" fill="#22e4ff" />
          <circle cx="18" cy="6" r="2" fill="#9a5bff" />
          <circle cx="12" cy="18" r="2" fill="#ff4fd8" />
          <path
            d="M6 6 L12 18 M18 6 L12 18 M6 6 L18 6"
            stroke="url(#g)"
            strokeWidth="1.3"
            strokeLinecap="round"
          />
          <defs>
            <linearGradient id="g" x1="0" y1="0" x2="24" y2="24">
              <stop offset="0" stopColor="#22e4ff" />
              <stop offset="1" stopColor="#ff4fd8" />
            </linearGradient>
          </defs>
        </svg>
      </div>
    </div>
  );
}

function timeAgo(ts: number) {
  const s = (Date.now() - ts) / 1000;
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m`;
  if (s < 86400) return `${Math.floor(s / 3600)}h`;
  if (s < 86400 * 7) return `${Math.floor(s / 86400)}d`;
  return new Date(ts).toLocaleDateString();
}
