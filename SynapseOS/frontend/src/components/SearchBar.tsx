"use client";

import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import type { GraphNode, SearchHit } from "@/lib/types";

type Props = {
  onSelect: (node: GraphNode) => void;
};

export function SearchBar({ onSelect }: Props) {
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<SearchHit[]>([]);
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!q.trim()) {
      setHits([]);
      return;
    }
    const t = setTimeout(() => {
      api
        .search(q.trim(), 8)
        .then(setHits)
        .catch(() => setHits([]));
    }, 160);
    return () => clearTimeout(t);
  }, [q]);

  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (!wrapRef.current?.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  return (
    <div ref={wrapRef} className="relative">
      <div className="flex items-center gap-2 rounded-xl bg-ink-800/60 ring-1 ring-white/5 shadow-card px-3 py-2">
        <svg
          className="w-4 h-4 text-ink-300"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
        >
          <circle cx="11" cy="11" r="7" />
          <path d="M21 21l-4.3-4.3" />
        </svg>
        <input
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          placeholder="semantic search — ask your brain"
          className="flex-1 bg-transparent text-sm text-ink-100 placeholder:text-ink-400 focus:outline-none"
        />
        {q && (
          <button
            onClick={() => {
              setQ("");
              setHits([]);
            }}
            className="text-[10px] text-ink-300 hover:text-ink-100 font-mono"
          >
            clear
          </button>
        )}
      </div>
      {open && hits.length > 0 && (
        <div className="absolute z-20 left-0 right-0 mt-2 rounded-xl bg-ink-800/95 backdrop-blur ring-1 ring-white/10 shadow-xl overflow-hidden animate-fade-in">
          {hits.map((h) => (
            <button
              key={h.node.id}
              onClick={() => {
                onSelect(h.node);
                setOpen(false);
              }}
              className="w-full text-left px-3 py-2 flex items-center gap-3 hover:bg-white/5 transition border-b border-white/5 last:border-0"
            >
              <span
                className="w-1 rounded-full bg-gradient-to-t from-synapse-cyan to-synapse-violet"
                style={{ height: `${Math.max(10, h.score * 28)}px` }}
              />
              <span className="flex-1 text-sm text-ink-100 truncate">
                {h.node.title}
              </span>
              <span className="text-[10px] font-mono text-ink-300">
                {(h.score * 100).toFixed(0)}%
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
