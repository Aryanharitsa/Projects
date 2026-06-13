"use client";

import type { GraphStats } from "@/lib/types";

type Props = {
  stats: GraphStats | null;
  apiOk: boolean | null;
  chatActive?: boolean;
  trailActive?: boolean;
  onOpenBrief?: () => void;
  briefBadge?: boolean;
  onOpenDistill?: () => void;
  onOpenTensions?: () => void;
  tensionsBadge?: number;
  onOpenEcho?: () => void;
  echoBadge?: number;
  onOpenAtlas?: () => void;
};

export function Header({
  stats,
  apiOk,
  chatActive,
  trailActive,
  onOpenBrief,
  briefBadge,
  onOpenDistill,
  onOpenTensions,
  tensionsBadge,
  onOpenEcho,
  echoBadge,
  onOpenAtlas,
}: Props) {
  return (
    <header className="relative border-b border-white/5">
      <div className="absolute inset-0 bg-grid-fade pointer-events-none" />
      <div className="relative mx-auto max-w-[1600px] px-6 py-5 flex items-center gap-6">
        <div className="flex items-center gap-3">
          <Logo />
          <div>
            <div className="text-lg font-semibold tracking-tight text-ink-100">
              SynapseOS
            </div>
            <div className="text-[11px] text-ink-300 uppercase tracking-[0.18em]">
              second brain · as an OS
            </div>
          </div>
        </div>

        <div className="ml-auto flex items-center gap-2 text-xs">
          {stats && (
            <>
              <Pill label="nodes" value={stats.nodes} color="violet" />
              <Pill label="synapses" value={stats.edges} color="cyan" />
              {stats.communities !== undefined && (
                <Pill label="clusters" value={stats.communities} color="pink" />
              )}
              <Pill
                label="avg deg"
                value={stats.avg_degree.toFixed(1)}
                color="lime"
              />
              <Pill
                label={`τ ${stats.threshold.toFixed(2)}`}
                value={`k=${stats.top_k}`}
                color="amber"
              />
            </>
          )}
          {chatActive && (
            <span className="inline-flex items-center gap-1.5 rounded-full bg-synapse-cyan/10 ring-1 ring-synapse-cyan/40 px-2.5 py-1 font-mono text-[11px] text-synapse-cyan">
              <span className="w-1.5 h-1.5 rounded-full bg-synapse-cyan animate-pulse-slow" />
              traversal active
            </span>
          )}
          {trailActive && (
            <span className="inline-flex items-center gap-1.5 rounded-full bg-synapse-amber/10 ring-1 ring-synapse-amber/40 px-2.5 py-1 font-mono text-[11px] text-synapse-amber">
              <span className="w-1.5 h-1.5 rounded-full bg-synapse-amber animate-pulse-slow" />
              trail open
            </span>
          )}
          {onOpenDistill && (
            <button
              onClick={onOpenDistill}
              className="relative inline-flex items-center gap-1.5 rounded-full bg-gradient-to-r from-synapse-violet/20 to-synapse-cyan/20 ring-1 ring-synapse-violet/40 hover:ring-synapse-violet/70 px-3 py-1 font-mono text-[11px] text-synapse-violet hover:text-ink-100 transition"
              aria-label="open distill"
            >
              <span aria-hidden>✨</span>
              distill
            </button>
          )}
          {onOpenTensions && (
            <button
              onClick={onOpenTensions}
              className="relative inline-flex items-center gap-1.5 rounded-full bg-gradient-to-r from-rose-500/20 to-synapse-violet/15 ring-1 ring-rose-400/40 hover:ring-rose-400/70 px-3 py-1 font-mono text-[11px] text-rose-200 hover:text-ink-100 transition"
              aria-label="open tensions"
              title="Surface contradictions in your second brain"
            >
              <span aria-hidden>⟷</span>
              tensions
              {tensionsBadge !== undefined && tensionsBadge > 0 && (
                <span className="ml-0.5 inline-flex items-center justify-center min-w-[1.1rem] h-[1.1rem] rounded-full bg-rose-500/30 ring-1 ring-rose-300/60 text-[10px] text-rose-100 px-1">
                  {tensionsBadge > 99 ? "99+" : tensionsBadge}
                </span>
              )}
            </button>
          )}
          {onOpenEcho && (
            <button
              onClick={onOpenEcho}
              className="relative inline-flex items-center gap-1.5 rounded-full bg-gradient-to-r from-synapse-cyan/20 to-synapse-amber/15 ring-1 ring-synapse-cyan/40 hover:ring-synapse-cyan/70 px-3 py-1 font-mono text-[11px] text-synapse-cyan hover:text-ink-100 transition"
              aria-label="open echo"
              title="Find and merge near-duplicate notes"
            >
              <span aria-hidden>⌬</span>
              echoes
              {echoBadge !== undefined && echoBadge > 0 && (
                <span className="ml-0.5 inline-flex items-center justify-center min-w-[1.1rem] h-[1.1rem] rounded-full bg-synapse-cyan/30 ring-1 ring-synapse-cyan/60 text-[10px] text-ink-100 px-1">
                  {echoBadge > 99 ? "99+" : echoBadge}
                </span>
              )}
            </button>
          )}
          {onOpenAtlas && (
            <button
              onClick={onOpenAtlas}
              className="relative inline-flex items-center gap-1.5 rounded-full bg-gradient-to-r from-synapse-lime/15 to-synapse-violet/15 ring-1 ring-synapse-lime/40 hover:ring-synapse-lime/70 px-3 py-1 font-mono text-[11px] text-synapse-lime hover:text-ink-100 transition"
              aria-label="open atlas"
              title="Executive map of every cluster — cohesion × activity quadrant + recommendations"
            >
              <span aria-hidden>⌖</span>
              atlas
            </button>
          )}
          {onOpenBrief && (
            <button
              onClick={onOpenBrief}
              className="relative inline-flex items-center gap-1.5 rounded-full bg-gradient-to-r from-synapse-amber/20 to-synapse-violet/20 ring-1 ring-synapse-amber/40 hover:ring-synapse-amber/70 px-3 py-1 font-mono text-[11px] text-synapse-amber hover:text-ink-100 transition"
              aria-label="open daily brief"
            >
              <span aria-hidden>☼</span>
              daily brief
              {briefBadge && (
                <span className="ml-0.5 w-1.5 h-1.5 rounded-full bg-synapse-cyan animate-pulse-slow" />
              )}
            </button>
          )}
          <HealthDot ok={apiOk} />
        </div>
      </div>
      <div className="hairline" />
    </header>
  );
}

function Logo() {
  return (
    <div className="relative w-10 h-10">
      <svg viewBox="0 0 40 40" className="w-full h-full">
        <defs>
          <linearGradient id="lg" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="#a855f7" />
            <stop offset="100%" stopColor="#22d3ee" />
          </linearGradient>
        </defs>
        <circle cx="20" cy="20" r="2.5" fill="url(#lg)" />
        <circle cx="8" cy="10" r="2" fill="#a855f7" />
        <circle cx="32" cy="12" r="2" fill="#22d3ee" />
        <circle cx="10" cy="30" r="2" fill="#22d3ee" />
        <circle cx="32" cy="30" r="2" fill="#ec4899" />
        <g stroke="url(#lg)" strokeWidth="0.75" opacity="0.8">
          <line x1="20" y1="20" x2="8" y2="10" />
          <line x1="20" y1="20" x2="32" y2="12" />
          <line x1="20" y1="20" x2="10" y2="30" />
          <line x1="20" y1="20" x2="32" y2="30" />
          <line x1="8" y1="10" x2="32" y2="12" />
          <line x1="10" y1="30" x2="32" y2="30" />
        </g>
      </svg>
      <div className="absolute inset-0 rounded-full shadow-glow pointer-events-none" />
    </div>
  );
}

function Pill({
  label,
  value,
  color,
}: {
  label: string;
  value: string | number;
  color: "violet" | "cyan" | "lime" | "amber" | "pink";
}) {
  const ring = {
    violet: "ring-synapse-violet/40 text-synapse-violet",
    cyan: "ring-synapse-cyan/40 text-synapse-cyan",
    lime: "ring-synapse-lime/40 text-synapse-lime",
    amber: "ring-synapse-amber/40 text-synapse-amber",
    pink: "ring-synapse-pink/40 text-synapse-pink",
  }[color];
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full bg-white/[0.02] ring-1 ${ring} px-2.5 py-1 font-mono text-[11px]`}
    >
      <span className="opacity-70">{label}</span>
      <span className="text-ink-100">{value}</span>
    </span>
  );
}

function HealthDot({ ok }: { ok: boolean | null }) {
  const color =
    ok === null ? "bg-ink-400" : ok ? "bg-synapse-lime" : "bg-synapse-pink";
  const label =
    ok === null ? "checking" : ok ? "backend online" : "backend offline";
  return (
    <span className="inline-flex items-center gap-2 text-[11px] text-ink-300">
      <span className={`w-2 h-2 rounded-full ${color} ${ok ? "animate-pulse-slow" : ""}`} />
      {label}
    </span>
  );
}
