"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { TrailSummary } from "@/lib/types";

type Props = {
  /** Bumps when the page knows the trail list might have changed
   *  (e.g. the player just patched a trail). Cheap parent-triggered
   *  refresh signal. */
  refreshKey: number;
  /** Currently-active trail id, if any (so we can highlight it). */
  activeTrailId: number | null;
  /** Open the player in play mode for an existing trail. */
  onOpenPlay: (trailId: number) => void;
  /** Open the player in build mode for a new trail. */
  onOpenNew: () => void;
  /** Open the builder for an existing trail. */
  onOpenEdit: (trailId: number) => void;
};

/**
 * Trails — curated, replayable walks through your second brain.
 *
 * Each trail is an ordered list of notes with optional captions. The
 * panel shows: title, step count, a "health" badge (fraction of
 * consecutive steps that ride a real synapse at the current τ), and
 * shortcuts to play / edit / delete.
 *
 * Empty state is opinionated: it tells the user *what* a trail is,
 * not just "no trails yet". The whole feature is invisible without
 * the framing.
 */
export function TrailsPanel({
  refreshKey,
  activeTrailId,
  onOpenPlay,
  onOpenNew,
  onOpenEdit,
}: Props) {
  const [trails, setTrails] = useState<TrailSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    api
      .listTrails()
      .then((ts) => {
        if (!cancelled) setTrails(ts);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : "failed to load trails");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [refreshKey]);

  const handleDelete = async (id: number) => {
    if (!confirm("Delete this trail? The notes themselves stay.")) return;
    setBusyId(id);
    try {
      await api.deleteTrail(id);
      setTrails((prev) => prev.filter((t) => t.id !== id));
    } catch (e) {
      setError(e instanceof Error ? e.message : "delete failed");
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="rounded-xl bg-ink-800/60 ring-1 ring-white/5 shadow-card p-4 animate-fade-in">
      <div className="flex items-center justify-between mb-2">
        <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-ink-200 flex items-center gap-2">
          trails
          {trails.length > 0 && (
            <span className="font-mono text-[10px] text-ink-400">
              {trails.length}
            </span>
          )}
        </div>
        <button
          onClick={onOpenNew}
          className="text-[10px] font-mono uppercase tracking-[0.14em] rounded-full px-2.5 py-1 ring-1 ring-synapse-amber/40 text-synapse-amber hover:ring-synapse-amber/80 hover:text-ink-100 transition"
        >
          + new
        </button>
      </div>
      <p className="text-[11px] text-ink-400 leading-snug mb-3">
        Replayable walks through your graph. Save an investigation, share a
        syllabus, export as Markdown.
      </p>

      {error && (
        <div className="text-[11px] text-synapse-pink mb-2 font-mono">{error}</div>
      )}

      {loading && trails.length === 0 ? (
        <div className="text-[11px] text-ink-400 font-mono">loading…</div>
      ) : trails.length === 0 ? (
        <button
          onClick={onOpenNew}
          className="w-full text-left rounded-lg ring-1 ring-dashed ring-white/10 bg-white/[0.012] p-3 hover:bg-white/[0.03] transition group"
        >
          <div className="text-sm text-ink-200 group-hover:text-ink-100">
            Start your first trail
          </div>
          <div className="text-[11px] text-ink-400 mt-1 leading-snug">
            Pick a starting note → SynapseOS suggests next stops along its
            synapses. Add captions as you go.
          </div>
        </button>
      ) : (
        <ul className="space-y-2">
          {trails.map((t) => {
            const active = activeTrailId === t.id;
            return (
              <li
                key={t.id}
                className={`rounded-lg p-2.5 transition ring-1 ${
                  active
                    ? "ring-synapse-amber/50 bg-synapse-amber/[0.04]"
                    : "ring-white/5 bg-white/[0.015] hover:bg-white/[0.03]"
                }`}
              >
                <div className="flex items-center justify-between gap-2">
                  <button
                    onClick={() => onOpenPlay(t.id)}
                    className="flex-1 text-left min-w-0"
                    title={t.title}
                  >
                    <div className="flex items-center gap-2">
                      {active && (
                        <span className="w-1.5 h-1.5 rounded-full bg-synapse-amber animate-pulse-slow shrink-0" />
                      )}
                      <span className="text-sm text-ink-100 truncate">
                        {t.title}
                      </span>
                    </div>
                    <div className="mt-1 flex items-center gap-2 text-[10px] font-mono text-ink-400">
                      <span>{t.step_count} stop{t.step_count === 1 ? "" : "s"}</span>
                      <span>·</span>
                      <HealthBadge health={t.health} hops={t.step_count - 1} />
                      {t.missing_count > 0 && (
                        <>
                          <span>·</span>
                          <span className="text-synapse-pink/90">
                            {t.missing_count} missing
                          </span>
                        </>
                      )}
                    </div>
                  </button>
                  <div className="flex items-center gap-1 shrink-0">
                    <IconButton
                      label="edit"
                      onClick={() => onOpenEdit(t.id)}
                      disabled={busyId === t.id}
                    >
                      <svg viewBox="0 0 16 16" className="w-3 h-3 fill-none stroke-current" strokeWidth="1.4">
                        <path d="M11 2.5l2.5 2.5L5 13.5H2.5V11L11 2.5z" />
                      </svg>
                    </IconButton>
                    <IconButton
                      label="delete"
                      tone="pink"
                      onClick={() => handleDelete(t.id)}
                      disabled={busyId === t.id}
                    >
                      <svg viewBox="0 0 16 16" className="w-3 h-3 fill-none stroke-current" strokeWidth="1.4">
                        <path d="M3 4h10M6 4V2.5h4V4M5 4l.5 9h5L11 4M7 6.5v5M9 6.5v5" />
                      </svg>
                    </IconButton>
                  </div>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

function HealthBadge({ health, hops }: { health: number; hops: number }) {
  if (hops <= 0) return <span className="text-ink-400">single stop</span>;
  const pct = Math.round(health * 100);
  const tone =
    health >= 0.66
      ? "text-synapse-lime"
      : health >= 0.33
        ? "text-synapse-amber"
        : "text-synapse-pink";
  const label = health >= 0.66 ? "synapse-walk" : health >= 0.33 ? "mixed" : "leaping";
  return (
    <span className={tone} title={`${pct}% of transitions ride a real synapse`}>
      {label} · {pct}%
    </span>
  );
}

function IconButton({
  children,
  label,
  onClick,
  tone = "neutral",
  disabled,
}: {
  children: React.ReactNode;
  label: string;
  onClick: () => void;
  tone?: "neutral" | "pink";
  disabled?: boolean;
}) {
  const toneRing =
    tone === "pink"
      ? "ring-white/5 text-ink-300 hover:text-synapse-pink hover:ring-synapse-pink/40"
      : "ring-white/5 text-ink-300 hover:text-synapse-cyan hover:ring-synapse-cyan/40";
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      aria-label={label}
      title={label}
      className={`p-1.5 rounded-md ring-1 ${toneRing} transition disabled:opacity-40`}
    >
      {children}
    </button>
  );
}
