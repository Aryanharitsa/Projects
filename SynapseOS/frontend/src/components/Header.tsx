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
  onOpenChronicle?: () => void;
  chronicleBadge?: number;
  onOpenPulse?: () => void;
  pulseBadge?: number;
  onOpenSpark?: () => void;
  sparkBadge?: number;
  onOpenCompass?: () => void;
  compassBadge?: number;
  onOpenRecall?: () => void;
  recallBadge?: number;
  onOpenSignal?: () => void;
  /** Total pinned watches — the base count for the badge. */
  signalBadge?: number;
  /** Watches whose delta is currently ``grown`` or ``shrunk`` — the
   *  actionable subset. When > 0 the badge tints amber to nudge review. */
  signalMoversBadge?: number;
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
  onOpenChronicle,
  chronicleBadge,
  onOpenPulse,
  pulseBadge,
  onOpenSpark,
  sparkBadge,
  onOpenCompass,
  compassBadge,
  onOpenRecall,
  recallBadge,
  onOpenSignal,
  signalBadge,
  signalMoversBadge,
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
          {onOpenChronicle && (
            <button
              onClick={onOpenChronicle}
              className="relative inline-flex items-center gap-1.5 rounded-full bg-gradient-to-r from-synapse-pink/20 to-synapse-violet/15 ring-1 ring-synapse-pink/40 hover:ring-synapse-pink/70 px-3 py-1 font-mono text-[11px] text-synapse-pink hover:text-ink-100 transition"
              aria-label="open chronicle"
              title="Watch each topic evolve over time — chapters, drift, pivots, emerged & faded terms"
            >
              <span aria-hidden>⟿</span>
              chronicle
              {chronicleBadge !== undefined && chronicleBadge > 0 && (
                <span className="ml-0.5 inline-flex items-center justify-center min-w-[1.1rem] h-[1.1rem] rounded-full bg-synapse-pink/30 ring-1 ring-synapse-pink/60 text-[10px] text-ink-100 px-1">
                  {chronicleBadge > 99 ? "99+" : chronicleBadge}
                </span>
              )}
            </button>
          )}
          {onOpenPulse && (
            <button
              onClick={onOpenPulse}
              className="relative inline-flex items-center gap-1.5 rounded-full bg-gradient-to-r from-synapse-pink/20 via-synapse-lime/15 to-synapse-cyan/15 ring-1 ring-synapse-pink/40 hover:ring-synapse-pink/70 px-3 py-1 font-mono text-[11px] text-synapse-pink hover:text-ink-100 transition"
              aria-label="open pulse"
              title="What changed in your second brain this week — new notes, bridges, hubs, vocabulary delta"
            >
              <span aria-hidden>⩘</span>
              pulse
              {pulseBadge !== undefined && pulseBadge > 0 && (
                <span className="ml-0.5 inline-flex items-center justify-center min-w-[1.1rem] h-[1.1rem] rounded-full bg-synapse-lime/30 ring-1 ring-synapse-lime/60 text-[10px] text-ink-100 px-1">
                  {pulseBadge > 99 ? "99+" : pulseBadge}
                </span>
              )}
            </button>
          )}
          {onOpenCompass && (
            <button
              onClick={onOpenCompass}
              className="relative inline-flex items-center gap-1.5 rounded-full bg-gradient-to-r from-synapse-cyan/25 via-synapse-violet/20 to-synapse-amber/15 ring-1 ring-synapse-cyan/45 hover:ring-synapse-cyan/80 px-3 py-1 font-mono text-[11px] text-ink-100 transition shadow-[0_0_20px_-8px_rgba(34,211,238,0.65)] hover:shadow-[0_0_28px_-6px_rgba(34,211,238,0.85)]"
              aria-label="open compass"
              title="Question-anchored lens — pin a research question, mark reads, grow a citation-stitched working answer"
            >
              <span aria-hidden className="text-synapse-cyan">🧭</span>
              compass
              <span className="-ml-0.5 px-1 py-px rounded bg-gradient-to-r from-synapse-cyan/35 to-synapse-violet/30 ring-1 ring-white/10 text-[9px] uppercase tracking-widest text-ink-100">
                new
              </span>
              {compassBadge !== undefined && compassBadge > 0 && (
                <span className="ml-0.5 inline-flex items-center justify-center min-w-[1.1rem] h-[1.1rem] rounded-full bg-synapse-cyan/35 ring-1 ring-synapse-cyan/70 text-[10px] text-ink-100 px-1">
                  {compassBadge > 99 ? "99+" : compassBadge}
                </span>
              )}
            </button>
          )}
          {onOpenSpark && (
            <button
              onClick={onOpenSpark}
              className="relative inline-flex items-center gap-1.5 rounded-full bg-gradient-to-r from-synapse-violet/25 via-synapse-cyan/15 to-synapse-amber/15 ring-1 ring-synapse-violet/45 hover:ring-synapse-violet/80 px-3 py-1 font-mono text-[11px] text-ink-100 transition shadow-[0_0_20px_-8px_rgba(168,85,247,0.65)] hover:shadow-[0_0_28px_-6px_rgba(168,85,247,0.85)]"
              aria-label="open spark"
              title="What to write next — concrete draft proposals targeting the gaps in your graph"
            >
              <span
                aria-hidden
                className="text-synapse-amber animate-pulse-slow"
              >
                ⚡
              </span>
              spark
              <span className="-ml-0.5 px-1 py-px rounded bg-gradient-to-r from-synapse-violet/35 to-synapse-cyan/30 ring-1 ring-white/10 text-[9px] uppercase tracking-widest text-ink-100">
                new
              </span>
              {sparkBadge !== undefined && sparkBadge > 0 && (
                <span className="ml-0.5 inline-flex items-center justify-center min-w-[1.1rem] h-[1.1rem] rounded-full bg-synapse-violet/35 ring-1 ring-synapse-violet/70 text-[10px] text-ink-100 px-1">
                  {sparkBadge > 99 ? "99+" : sparkBadge}
                </span>
              )}
            </button>
          )}
          {onOpenSignal && (
            <button
              onClick={onOpenSignal}
              className="relative inline-flex items-center gap-1.5 rounded-full bg-gradient-to-r from-synapse-lime/25 via-synapse-cyan/20 to-synapse-violet/20 ring-1 ring-synapse-lime/45 hover:ring-synapse-lime/80 px-3 py-1 font-mono text-[11px] text-ink-100 transition shadow-[0_0_20px_-8px_rgba(163,230,53,0.65)] hover:shadow-[0_0_28px_-6px_rgba(34,211,238,0.75)]"
              aria-label="open signal"
              title="Persistent watches over Compass questions — see what your vault has learned since you pinned each one"
            >
              <span aria-hidden className="text-synapse-lime">◉</span>
              signal
              <span className="-ml-0.5 px-1 py-px rounded bg-gradient-to-r from-synapse-lime/35 to-synapse-cyan/30 ring-1 ring-white/10 text-[9px] uppercase tracking-widest text-ink-100">
                new
              </span>
              {signalBadge !== undefined && signalBadge > 0 && (
                <span
                  className={`ml-0.5 inline-flex items-center justify-center min-w-[1.1rem] h-[1.1rem] rounded-full text-[10px] px-1 ring-1 ${
                    signalMoversBadge && signalMoversBadge > 0
                      ? "bg-synapse-amber/30 ring-synapse-amber/70 text-synapse-amber"
                      : "bg-synapse-lime/25 ring-synapse-lime/55 text-ink-100"
                  }`}
                >
                  {signalMoversBadge && signalMoversBadge > 0
                    ? `${signalMoversBadge}↕`
                    : signalBadge > 99
                      ? "99+"
                      : signalBadge}
                </span>
              )}
            </button>
          )}
          {onOpenRecall && (
            <button
              onClick={onOpenRecall}
              className="relative inline-flex items-center gap-1.5 rounded-full bg-gradient-to-r from-synapse-cyan/25 via-synapse-violet/20 to-synapse-lime/20 ring-1 ring-synapse-cyan/45 hover:ring-synapse-cyan/80 px-3 py-1 font-mono text-[11px] text-ink-100 transition shadow-[0_0_20px_-8px_rgba(34,211,238,0.65)] hover:shadow-[0_0_28px_-6px_rgba(163,230,53,0.7)]"
              aria-label="open recall"
              title="Active-recall quiz — cloze, prompt and neighbor-choice cards over your graph, SM-2 spaced repetition"
            >
              <span aria-hidden className="text-synapse-cyan">↻</span>
              recall
              <span className="-ml-0.5 px-1 py-px rounded bg-gradient-to-r from-synapse-cyan/35 to-synapse-lime/30 ring-1 ring-white/10 text-[9px] uppercase tracking-widest text-ink-100">
                new
              </span>
              {recallBadge !== undefined && recallBadge > 0 && (
                <span className="ml-0.5 inline-flex items-center justify-center min-w-[1.1rem] h-[1.1rem] rounded-full bg-synapse-amber/30 ring-1 ring-synapse-amber/60 text-[10px] text-synapse-amber px-1">
                  {recallBadge > 99 ? "99+" : recallBadge}
                </span>
              )}
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
