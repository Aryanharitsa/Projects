"use client";

import type { Community } from "@/lib/types";

type Props = {
  communities: Community[];
  isolated: number | null;
  onIsolate: (id: number | null) => void;
};

/**
 * The "topic palette" — the list of auto-derived clusters with their
 * names, sizes, and the three terms that distinguish them. Clicking a
 * cluster *isolates* it in the canvas (everything outside fades out);
 * clicking the active one again clears the isolation.
 */
export function TopicPalette({ communities, isolated, onIsolate }: Props) {
  if (communities.length === 0) {
    return (
      <div className="rounded-xl bg-white/[0.015] ring-1 ring-white/5 p-4 text-xs text-ink-300">
        <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-ink-200 mb-2">
          topic palette
        </div>
        <p className="leading-relaxed text-ink-300">
          Add a few notes — clusters and their names will surface here as
          synapses form.
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-xl bg-ink-800/60 ring-1 ring-white/5 shadow-card p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-ink-200">
          topic palette
        </div>
        {isolated !== null && (
          <button
            onClick={() => onIsolate(null)}
            className="text-[10px] font-mono text-synapse-amber hover:text-synapse-amber/80 transition px-1.5 py-0.5 rounded ring-1 ring-synapse-amber/40"
          >
            show all
          </button>
        )}
      </div>
      <ul className="space-y-1.5">
        {communities.map((c) => {
          const active = isolated === c.id;
          return (
            <li key={c.id}>
              <button
                onClick={() => onIsolate(active ? null : c.id)}
                title={active ? "click to clear isolation" : "isolate this cluster"}
                className={`group w-full text-left flex items-start gap-2.5 rounded-lg px-2 py-1.5 transition ${
                  active
                    ? "bg-white/[0.05] ring-1 ring-white/15"
                    : "hover:bg-white/[0.03] ring-1 ring-transparent"
                }`}
              >
                <span
                  className="mt-1 w-2.5 h-2.5 rounded-full shrink-0"
                  style={{
                    background: c.color,
                    boxShadow: `0 0 10px ${c.color}, 0 0 0 1px rgba(255,255,255,0.06)`,
                  }}
                />
                <span className="flex-1 min-w-0">
                  <span className="flex items-baseline gap-2">
                    <span className="text-sm text-ink-100 truncate font-medium">
                      {c.name}
                    </span>
                    <span className="text-[10px] font-mono text-ink-400 shrink-0">
                      {c.size}
                    </span>
                  </span>
                  {c.terms.length > 0 && (
                    <span className="mt-0.5 flex flex-wrap gap-1">
                      {c.terms.slice(0, 3).map((t) => (
                        <span
                          key={t}
                          className="text-[10px] font-mono px-1.5 py-0 rounded bg-white/[0.03] text-ink-300 ring-1 ring-white/5"
                        >
                          {t}
                        </span>
                      ))}
                    </span>
                  )}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
