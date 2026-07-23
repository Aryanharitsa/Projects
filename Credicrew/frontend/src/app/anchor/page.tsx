'use client';

import Link from 'next/link';
import { useEffect, useMemo, useState, type CSSProperties } from 'react';

import { candidates as CANDIDATES } from '@/data/candidates';
import { listRoles, type Role } from '@/lib/roles';
import { matchCandidate } from '@/lib/match';
import { getInterview, summarise } from '@/lib/interview';
import { getOffer } from '@/lib/offer';
import { totalCash } from '@/lib/portfolio';
import {
  analyzeAnchor,
  buildAnchorBrief,
  ringDashPair,
  TIER_HEX,
  TIER_LABEL,
  TIER_BLURB,
  TIER_ORDER,
  DRIVER_HEX,
  AXIS_LABEL,
  AXES,
  RECENCY_ZERO_DAYS,
  CADENCE_ZERO_HOURS,
  type AnchorCandidateInput,
  type AnchorCandidateScore,
  type AnchorSummary,
  type AnchorTier,
} from '@/lib/anchor';
import { seedSignals, daysInStageFrom } from '@/lib/anchor_seed';

// ─────────── palette ───────────

const STAGE_HEX: Record<string, string> = {
  new:       '#38bdf8',
  outreach:  '#818cf8',
  screening: '#a78bfa',
  interview: '#f59e0b',
  offer:     '#10b981',
  passed:    '#f43f5e',
};

const STAGE_LABEL: Record<string, string> = {
  new:       'New',
  outreach:  'Outreach',
  screening: 'Screening',
  interview: 'Interview',
  offer:     'Offer',
  passed:    'Passed',
};

const NUM_LOCALE = 'en-IN';

function formatINR(v: number): string {
  if (v <= 0) return '—';
  if (v >= 100_00_000) {
    return `₹${(v / 100_00_000).toFixed(2)}Cr`;
  }
  if (v >= 1_00_000) {
    return `₹${(v / 1_00_000).toFixed(2)}L`;
  }
  return `₹${Math.round(v).toLocaleString(NUM_LOCALE)}`;
}

function copyToClipboard(s: string): Promise<void> {
  if (typeof navigator !== 'undefined' && navigator.clipboard) {
    return navigator.clipboard.writeText(s);
  }
  return new Promise((res) => {
    const ta = document.createElement('textarea');
    ta.value = s;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    ta.remove();
    res();
  });
}

// ─────────── momentum ring atom ───────────

function MomentumRing({
  momentum,
  size = 112,
  stroke = 8,
}: {
  momentum: number;
  size?: number;
  stroke?: number;
}) {
  const r = (size - stroke) / 2;
  const cx = size / 2;
  const cy = size / 2;
  const { dashArray, dashOffset } = ringDashPair(momentum, r);
  const accent =
    momentum >= 75 ? '#10b981' :
    momentum >= 55 ? '#38bdf8' :
    momentum >= 35 ? '#f59e0b' :
    '#f43f5e';
  return (
    <div className="relative grid place-items-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={cx} cy={cy} r={r} fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth={stroke} />
        <circle
          cx={cx}
          cy={cy}
          r={r}
          fill="none"
          stroke={accent}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={dashArray}
          strokeDashoffset={dashOffset}
          style={{
            filter: `drop-shadow(0 0 8px ${accent}60)`,
            transition: 'stroke-dashoffset .6s ease, stroke .6s ease',
          }}
        />
      </svg>
      <div className="absolute inset-0 grid place-items-center">
        <div className="text-center">
          <div className="text-2xl font-semibold text-white leading-none">{Math.round(momentum)}</div>
          <div className="text-[9px] uppercase tracking-widest text-white/60 mt-1">momentum</div>
        </div>
      </div>
    </div>
  );
}

function TierBadge({ tier }: { tier: AnchorTier }) {
  const hex = TIER_HEX[tier];
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[10px] font-semibold uppercase tracking-widest"
      style={{
        color: hex,
        background: `${hex}18`,
        border: `1px solid ${hex}55`,
      }}
    >
      <span className="h-1.5 w-1.5 rounded-full" style={{ background: hex, boxShadow: `0 0 8px ${hex}` }} />
      {TIER_LABEL[tier]}
    </span>
  );
}

function DriverChip({ label, hex, detail }: { label: string; hex: string; detail?: string }) {
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-lg px-2 py-1 text-[11px] leading-none"
      style={{
        color: hex,
        background: `${hex}12`,
        border: `1px solid ${hex}35`,
      }}
      title={detail}
    >
      <span className="h-1.5 w-1.5 rounded-full" style={{ background: hex }} />
      {label}
    </span>
  );
}

function StagePill({ status }: { status: string }) {
  const hex = STAGE_HEX[status] ?? '#94a3b8';
  return (
    <span
      className="rounded-md px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider"
      style={{
        color: hex,
        background: `${hex}18`,
        border: `1px solid ${hex}44`,
      }}
    >
      {STAGE_LABEL[status] ?? status}
    </span>
  );
}

function KpiTile({
  label,
  value,
  sub,
  accent = '#a78bfa',
}: {
  label: string;
  value: string;
  sub?: string;
  accent?: string;
}) {
  const style: CSSProperties = {
    background: `linear-gradient(140deg, ${accent}18 0%, transparent 60%), rgba(255,255,255,0.02)`,
    borderColor: `${accent}45`,
  };
  return (
    <div className="rounded-2xl border p-4" style={style}>
      <div className="text-[10px] uppercase tracking-widest text-white/60">{label}</div>
      <div className="mt-1 text-2xl font-semibold text-white leading-tight">{value}</div>
      {sub && <div className="mt-1 text-xs text-white/60">{sub}</div>}
    </div>
  );
}

// ─────────── stage heatmap ───────────

function StageHeatmap({ summary }: { summary: AnchorSummary }) {
  if (summary.byStage.length === 0) return null;
  const maxCount = Math.max(...summary.byStage.map(s => s.count));
  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.02] p-5">
      <div className="mb-3 flex items-baseline justify-between">
        <div>
          <div className="text-sm font-semibold text-white">Stage risk heatmap</div>
          <div className="text-[11px] text-white/50">Active candidates by stage, with mean risk overlaid.</div>
        </div>
      </div>
      <div className="space-y-2.5">
        {summary.byStage.map(b => {
          const hex = STAGE_HEX[b.status] ?? '#94a3b8';
          const meanRiskHex =
            b.meanRisk >= 65 ? '#f43f5e' :
            b.meanRisk >= 45 ? '#f59e0b' :
            b.meanRisk >= 25 ? '#38bdf8' :
            '#10b981';
          const wPct = Math.max(6, (b.count / maxCount) * 100);
          const rPct = Math.max(0, Math.min(100, b.meanRisk));
          return (
            <div key={b.status} className="grid grid-cols-[110px_1fr_auto] items-center gap-3">
              <div className="flex items-center gap-2">
                <span className="h-2.5 w-2.5 rounded-full" style={{ background: hex }} />
                <div className="text-xs text-white/80">{STAGE_LABEL[b.status]}</div>
              </div>
              <div className="relative h-6 overflow-hidden rounded-md bg-white/5">
                <div
                  className="absolute inset-y-0 left-0 rounded-md"
                  style={{
                    width: `${wPct}%`,
                    background: `linear-gradient(90deg, ${hex}44, ${hex}22)`,
                    borderRight: `2px solid ${hex}80`,
                  }}
                />
                <div
                  className="absolute inset-y-0 left-0 h-full"
                  style={{
                    width: `${rPct}%`,
                    background: `repeating-linear-gradient(45deg, ${meanRiskHex}30 0 6px, transparent 6px 12px)`,
                    borderRight: `1px dashed ${meanRiskHex}80`,
                  }}
                  title={`Mean risk ${b.meanRisk}/100`}
                />
                <div className="relative z-10 flex h-full items-center px-2 text-[10px] text-white/80">
                  {b.count} active · {b.atRisk} at risk · {b.critical} critical
                </div>
              </div>
              <div className="min-w-[36px] text-right text-xs font-semibold" style={{ color: meanRiskHex }}>
                {b.meanRisk}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ─────────── driver histogram ───────────

function DriverHistogram({ summary }: { summary: AnchorSummary }) {
  if (summary.driverHistogram.length === 0) return null;
  const max = Math.max(...summary.driverHistogram.map(d => d.count));
  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.02] p-5">
      <div className="mb-3">
        <div className="text-sm font-semibold text-white">Dominant drivers</div>
        <div className="text-[11px] text-white/50">Which signals show up most across the at-risk pool.</div>
      </div>
      <div className="space-y-2">
        {summary.driverHistogram.slice(0, 8).map(d => {
          const w = Math.max(4, (d.count / max) * 100);
          return (
            <div key={d.driver} className="grid grid-cols-[140px_1fr_auto] items-center gap-2 text-xs">
              <div className="flex items-center gap-2 text-white/80">
                <span className="h-2 w-2 rounded-full" style={{ background: d.hex }} />
                {d.label}
              </div>
              <div className="h-2 rounded-full bg-white/5">
                <div
                  className="h-2 rounded-full"
                  style={{
                    width: `${w}%`,
                    background: `linear-gradient(90deg, ${d.hex}, ${d.hex}88)`,
                    boxShadow: `0 0 8px ${d.hex}66`,
                  }}
                />
              </div>
              <div className="w-8 text-right text-white/70">{d.count}</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ─────────── candidate card ───────────

function CandidateCard({
  score,
  onCopy,
}: {
  score: AnchorCandidateScore;
  onCopy: (text: string, name: string) => void;
}) {
  const [showScript, setShowScript] = useState(false);
  const tierHex = TIER_HEX[score.tier];

  return (
    <div className="relative overflow-hidden rounded-2xl border border-white/10 bg-white/[0.02] p-4">
      <div
        className="absolute inset-x-0 top-0 h-[3px]"
        style={{ background: `linear-gradient(90deg, ${tierHex}, transparent)` }}
      />
      <div className="grid gap-4 md:grid-cols-[112px_1fr_auto] md:items-start">
        <MomentumRing momentum={score.momentum} />
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <div className="truncate text-base font-semibold text-white">{score.candidateName}</div>
            <StagePill status={score.status} />
            <TierBadge tier={score.tier} />
          </div>
          <div className="mt-0.5 truncate text-[11px] text-white/50">
            {score.candidateTitle && <>{score.candidateTitle} · </>}
            for <span className="text-white/70">{score.roleName}</span>
          </div>

          <div className="mt-2 flex flex-wrap gap-1.5">
            {score.drivers.slice(0, 4).map(d => (
              <DriverChip
                key={d.driver}
                label={d.label}
                hex={DRIVER_HEX[d.driver]}
                detail={d.detail}
              />
            ))}
            {score.drivers.length === 0 && (
              <span className="text-[11px] text-white/40 italic">No pressing risk drivers.</span>
            )}
          </div>

          {score.noteKeyphrase && (
            <div className="mt-3 rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-[11px] text-white/70">
              <span className="text-white/40 mr-1">last note:</span>&ldquo;{score.noteKeyphrase}&rdquo;
            </div>
          )}
        </div>

        <div className="flex flex-col items-end gap-1 text-right text-[11px]">
          <div>
            <span className="text-white/40">Risk</span>{' '}
            <span className="font-semibold text-white">{score.risk}</span>
            <span className="text-white/40">/100</span>
          </div>
          <div>
            <span className="text-white/40">Ghost</span>{' '}
            <span className="font-semibold text-white">{Math.round(score.ghostProbability * 100)}%</span>
          </div>
          <div>
            <span className="text-white/40">Half-life</span>{' '}
            <span className="font-semibold text-white">{score.halfLifeDays}d</span>
          </div>
          {score.exposureAnnual > 0 && (
            <div>
              <span className="text-white/40">Exposure</span>{' '}
              <span className="font-semibold text-white">{formatINR(score.exposureAnnual)}</span>
            </div>
          )}
          {score.salvageValue > 0 && (
            <div>
              <span className="text-white/40">Salvage</span>{' '}
              <span className="font-semibold" style={{ color: tierHex }}>{score.salvageValue}</span>
            </div>
          )}
        </div>
      </div>

      {/* axis mini-bars */}
      <div className="mt-4 grid grid-cols-3 gap-2 sm:grid-cols-6">
        {AXES.map(axis => {
          const v = score.axes[axis];
          const color =
            v >= 75 ? '#10b981' :
            v >= 55 ? '#38bdf8' :
            v >= 35 ? '#f59e0b' :
            '#f43f5e';
          return (
            <div key={axis}>
              <div className="text-[10px] uppercase tracking-wider text-white/50">{AXIS_LABEL[axis]}</div>
              <div className="mt-1 h-1.5 rounded-full bg-white/5">
                <div
                  className="h-1.5 rounded-full"
                  style={{
                    width: `${v}%`,
                    background: color,
                    boxShadow: `0 0 6px ${color}80`,
                  }}
                />
              </div>
              <div className="mt-0.5 text-[10px] text-white/60">{v}/100</div>
            </div>
          );
        })}
      </div>

      {/* recovery script */}
      {score.tier !== 'hold' && (
        <div className="mt-4 rounded-xl border border-white/10 bg-black/40 p-3">
          <button
            onClick={() => setShowScript(v => !v)}
            className="flex w-full items-center justify-between text-left"
          >
            <div>
              <div className="text-[10px] uppercase tracking-widest" style={{ color: tierHex }}>
                Recommended nudge · {score.script.channel} · ~{score.script.minutes}min
              </div>
              <div className="text-sm text-white mt-0.5">{score.script.headline}</div>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onCopy(score.script.body, score.candidateName);
                }}
                className="rounded-md border border-white/15 bg-white/5 px-2 py-1 text-[10px] text-white/70 hover:bg-white/10 hover:text-white"
              >
                Copy
              </button>
              <span className="text-white/50 text-lg leading-none">{showScript ? '−' : '+'}</span>
            </div>
          </button>
          {showScript && (
            <pre className="mt-3 whitespace-pre-wrap break-words rounded-lg bg-neutral-950/80 p-3 text-[12px] leading-relaxed text-white/85">
              {score.script.body}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}

// ─────────── page ───────────

type TierFilter = AnchorTier | 'all';

export default function AnchorPage() {
  const [roles, setRoles] = useState<Role[]>([]);
  const [now, setNow] = useState<number>(() => Date.now());
  const [tierFilter, setTierFilter] = useState<TierFilter>('all');
  const [copied, setCopied] = useState<string | null>(null);

  useEffect(() => {
    setRoles(listRoles());
    setNow(Date.now());
  }, []);

  const summary = useMemo<AnchorSummary>(() => {
    const inputs: AnchorCandidateInput[] = [];
    for (const role of roles) {
      const rolePlan = role.plan;
      for (const entry of role.shortlist) {
        if (entry.status === 'passed') continue;
        const c = CANDIDATES.find(x => x.id === entry.candidateId);
        if (!c) continue;

        const daysInStage = daysInStageFrom(entry.stageChangedAt, entry.addedAt, now);
        const signals = seedSignals(entry.candidateId, role.id, entry.status, daysInStage);

        // Resolve match score (from Match engine so we mirror Discover).
        const matchScore = rolePlan
          ? matchCandidate(rolePlan, {
              name: c.name,
              role: c.role,
              location: c.location,
              tags: c.tags,
              keywords: c.keywords,
              headline: c.headline,
            }).score
          : c.score;

        const record = getInterview(role.id, entry.candidateId);
        let composite: number | null = null;
        if (record) {
          const sum = summarise(record);
          composite = sum.composite;
        }

        const draft = getOffer(role.id, entry.candidateId);
        const offerValueAnnual = draft
          ? Math.round(totalCash({
              base: draft.base,
              equityPct: draft.equityPct,
              targetBonusPct: draft.targetBonusPct,
              signOn: draft.signOn,
            }) * 1_00_000) // convert LPA (lakh) → rupees for exposure math
          : undefined;

        inputs.push({
          candidateId: entry.candidateId,
          candidateName: c.name,
          candidateTitle: c.role,
          candidateLocation: c.location,
          roleId: role.id,
          roleName: role.name,
          roleSeniority: role.plan?.seniority ?? undefined,
          status: entry.status,
          addedAt: entry.addedAt,
          stageChangedAt: entry.stageChangedAt,
          matchScore,
          compositeScore: composite,
          offerValueAnnual,
          signals,
        });
      }
    }
    return analyzeAnchor({ candidates: inputs, now });
  }, [roles, now]);

  const filteredScores = useMemo(() => {
    if (tierFilter === 'all') return summary.scores;
    return summary.scores.filter(s => s.tier === tierFilter);
  }, [summary.scores, tierFilter]);

  const handleCopy = (text: string, name: string) => {
    copyToClipboard(text).then(() => {
      setCopied(name);
      setTimeout(() => setCopied(null), 1500);
    });
  };

  const handleExportBrief = () => {
    const md = buildAnchorBrief(summary);
    const blob = new Blob([md], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `anchor-brief-${new Date(now).toISOString().slice(0, 10)}.md`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const primaryAccent = '#f472b6';

  return (
    <main className="mx-auto max-w-6xl px-4 py-8 text-white">
      {/* hero */}
      <div
        className="relative mb-6 overflow-hidden rounded-3xl border border-white/10 p-6 sm:p-8"
        style={{
          background:
            'radial-gradient(600px 240px at 100% 0%, rgba(244,114,182,0.18), transparent 60%), radial-gradient(500px 200px at 0% 100%, rgba(56,189,248,0.14), transparent 60%), linear-gradient(140deg, rgba(255,255,255,0.03), rgba(255,255,255,0))',
        }}
      >
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.2em] text-white/60">
              <span
                className="rounded-full px-2 py-0.5 text-[9px] font-bold tracking-widest"
                style={{ background: `${primaryAccent}22`, color: primaryAccent, border: `1px solid ${primaryAccent}55` }}
              >
                Day 92
              </span>
              Anchor · Momentum & Drop-Off Risk Radar
            </div>
            <h1 className="mt-2 text-3xl sm:text-4xl font-semibold tracking-tight">
              Which candidates are about to ghost me — and what do I say now?
            </h1>
            <p className="mt-2 max-w-2xl text-sm text-white/70">
              Every active candidate in the pipeline is scored on six momentum axes and
              mapped to a recovery ladder. Copy-paste nudges are pre-written for the top
              risk driver. Anchor is the tab you open on Tuesday morning.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handleExportBrief}
              className="rounded-lg border border-white/15 bg-white/5 px-3 py-2 text-xs text-white/80 hover:bg-white/10 hover:text-white"
            >
              Export brief (.md)
            </button>
            <Link
              href="/hq"
              className="rounded-lg border border-white/15 bg-white/5 px-3 py-2 text-xs text-white/80 hover:bg-white/10 hover:text-white"
            >
              Open Command Center
            </Link>
          </div>
        </div>
      </div>

      {/* KPIs */}
      <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <KpiTile
          label="Active"
          value={summary.totals.active.toString()}
          sub={
            summary.meanMomentum !== null
              ? `Mean momentum ${summary.meanMomentum}/100`
              : 'No pipeline yet'
          }
          accent="#38bdf8"
        />
        <KpiTile
          label="At risk"
          value={summary.totals.atRisk.toString()}
          sub={`${summary.totals.critical} critical · ${summary.totals.released} for release`}
          accent="#f59e0b"
        />
        <KpiTile
          label="Salvageable"
          value={summary.totals.salvageableCount.toString()}
          sub={summary.totals.salvageValueTotal > 0
            ? `${summary.totals.salvageValueTotal} pts of salvage on the board`
            : 'Queue empty'}
          accent="#a78bfa"
        />
        <KpiTile
          label="Exposure at risk"
          value={
            summary.totals.exposureAnnual > 0
              ? formatINR(summary.totals.exposureAnnual)
              : '—'
          }
          sub={summary.totals.exposurePreOffer > 0
            ? `Pre-offer sunk: ${formatINR(summary.totals.exposurePreOffer)}`
            : 'No drafted offers at risk'}
          accent="#f472b6"
        />
      </div>

      {/* two-panel */}
      <div className="mb-6 grid gap-4 lg:grid-cols-2">
        <StageHeatmap summary={summary} />
        <DriverHistogram summary={summary} />
      </div>

      {/* tier filter chips */}
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className="text-[10px] uppercase tracking-widest text-white/50">Tier</span>
          <div className="flex flex-wrap gap-1.5">
            <button
              onClick={() => setTierFilter('all')}
              className={`rounded-full border px-3 py-1 text-[11px] transition ${
                tierFilter === 'all'
                  ? 'border-white/30 bg-white/10 text-white'
                  : 'border-white/10 bg-white/5 text-white/60 hover:bg-white/10'
              }`}
            >
              All ({summary.scores.length})
            </button>
            {TIER_ORDER.map(t => {
              const hex = TIER_HEX[t];
              const count = summary.tierMix[t] ?? 0;
              const active = tierFilter === t;
              return (
                <button
                  key={t}
                  onClick={() => setTierFilter(t)}
                  className="rounded-full border px-3 py-1 text-[11px] transition"
                  style={
                    active
                      ? {
                          color: hex,
                          background: `${hex}22`,
                          borderColor: `${hex}88`,
                        }
                      : {
                          color: 'rgba(255,255,255,0.6)',
                          background: 'rgba(255,255,255,0.03)',
                          borderColor: 'rgba(255,255,255,0.1)',
                        }
                  }
                  title={TIER_BLURB[t]}
                >
                  {TIER_LABEL[t]} ({count})
                </button>
              );
            })}
          </div>
        </div>
        {copied && (
          <div className="text-[11px] text-emerald-300">Copied nudge for {copied}.</div>
        )}
      </div>

      {/* list */}
      {summary.scores.length === 0 ? (
        <div className="rounded-2xl border border-white/10 bg-white/[0.02] p-8 text-center">
          <div className="text-lg font-semibold text-white">Nothing in the pipeline yet</div>
          <p className="mt-2 text-sm text-white/70">
            Add a role, shortlist a few candidates, and Anchor will start scoring their
            momentum. Try <Link href="/roles" className="text-fuchsia-300 hover:underline">Roles</Link> or{' '}
            <Link href="/" className="text-fuchsia-300 hover:underline">Discover</Link>.
          </p>
        </div>
      ) : (
        <div className="grid gap-3">
          {filteredScores.map(s => (
            <CandidateCard
              key={`${s.roleId}::${s.candidateId}`}
              score={s}
              onCopy={handleCopy}
            />
          ))}
          {filteredScores.length === 0 && (
            <div className="rounded-2xl border border-white/10 bg-white/[0.02] p-6 text-center text-sm text-white/60">
              No candidates in this tier.
            </div>
          )}
        </div>
      )}

      {/* footnote */}
      <div className="mt-8 rounded-2xl border border-white/10 bg-white/[0.02] p-4 text-[11px] leading-relaxed text-white/60">
        <div className="mb-1 text-white/80 font-semibold text-xs">How Anchor scores</div>
        Momentum = 0.25 recency · 0.20 cadence · 0.15 reliability · 0.20 pace · 0.10
        sentiment · 0.10 competing. Risk = 100 − momentum, +{15} pts if an external
        offer is confirmed. Ghost probability = σ(logit(stage prior) + (risk − 50)/20),
        with priors {`{new:0.35, outreach:0.30, screening:0.22, interview:0.15, offer:0.10}`}.
        Half-life = days until momentum decays past {30}. Recency dies at{' '}
        {RECENCY_ZERO_DAYS}d of silence; cadence dies at {CADENCE_ZERO_HOURS}h of median
        reply latency. Signals for the demo are seeded deterministically from
        (candidateId, roleId, status) so the same pipeline always produces the same board.
      </div>
    </main>
  );
}
