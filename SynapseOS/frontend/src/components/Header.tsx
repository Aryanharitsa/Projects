"use client";

import type { GraphStats } from "@/lib/types";

type Props = {
  stats: GraphStats | null;
  apiOk: boolean | null;
};

export function Header({ stats, apiOk }: Props) {
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
