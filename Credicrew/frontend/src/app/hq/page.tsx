'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';

import { candidates } from '@/data/candidates';
import { matchCandidate } from '@/lib/match';
import {
  listRoles,
  STATUS_LABEL,
  STATUS_TONE,
  type PipelineStatus,
  type Role,
} from '@/lib/roles';
import {
  getInterview,
  summarise,
  RECOMMENDATION_LABEL,
  type Recommendation,
} from '@/lib/interview';
import {
  benchmarkComp,
  getOffer,
  winProbability,
} from '@/lib/offer';
import { TIER_HUE } from '@/lib/decision';
import {
  buildPortfolio,
  formatLPA,
  HEALTH_HUE,
  PROGRESSION,
  SEVERITY_TONE,
  STAGE_DISPLAY,
  type PortfolioCandidate,
  type PortfolioInput,
  type PortfolioRole,
  type PortfolioSummary,
} from '@/lib/portfolio';

const TONE_RING: Record<string, string> = {
  rose: 'border-rose-400/30 bg-rose-400/10 text-rose-200',
  amber: 'border-amber-400/30 bg-amber-400/10 text-amber-200',
  sky: 'border-sky-400/30 bg-sky-400/10 text-sky-200',
  indigo: 'border-indigo-400/30 bg-indigo-400/10 text-indigo-200',
  emerald: 'border-emerald-400/30 bg-emerald-400/10 text-emerald-200',
  violet: 'border-violet-400/30 bg-violet-400/10 text-violet-200',
  slate: 'border-white/15 bg-white/5 text-white/65',
};

const STATUS_HEX: Record<string, string> = {
  sky: '#38bdf8',
  indigo: '#818cf8',
  violet: '#a78bfa',
  amber: '#facc15',
  emerald: '#34d399',
  rose: '#fb7185',
};

function copyToClipboard(s: string): Promise<void> {
  if (typeof navigator !== 'undefined' && navigator.clipboard) {
    return navigator.clipboard.writeText(s);
  }
  return new Promise(res => {
    const ta = document.createElement('textarea');
    ta.value = s;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    ta.remove();
    res();
  });
}

function downloadText(filename: string, body: string, type = 'text/markdown') {
  const blob = new Blob([body], { type });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  setTimeout(() => {
    URL.revokeObjectURL(url);
    a.remove();
  }, 0);
}

/** Resolve every role's shortlist into the portfolio engine's input shape,
 *  reusing the same match / interview / offer engines the per-role pages use. */
function gatherInput(roles: Role[]): PortfolioInput {
  const pRoles: PortfolioRole[] = roles.map(role => {
    const cands: PortfolioCandidate[] = role.shortlist.map(entry => {
      const c = candidates.find(x => x.id === entry.candidateId);
      const fallback = { id: entry.candidateId, name: `Candidate #${entry.candidateId}` };
      const cand = c ?? fallback;
      const match = matchCandidate(role.plan, cand);

      // Interview composite / confidence.
      const ir = getInterview(role.id, entry.candidateId);
      let composite: number | null = null;
      let confidence = 0;
      let recommendation: Recommendation | null = null;
      if (ir) {
        const s = summarise(ir);
        confidence = s.totalCount > 0 ? s.ratedCount / s.totalCount : 0;
        composite = s.ratedCount > 0 ? s.composite : null;
        recommendation = s.ratedCount > 0 ? s.recommendation : null;
      }

      // Offer draft + accept-probability.
      const draft = getOffer(role.id, entry.candidateId);
      let offer: PortfolioCandidate['offer'] | undefined;
      let winProb: number | undefined;
      if (draft) {
        offer = {
          base: draft.base,
          equityPct: draft.equityPct,
          targetBonusPct: draft.targetBonusPct,
          signOn: draft.signOn,
        };
        const benchmark = benchmarkComp(role.plan, match.matchedSkills);
        const win = winProbability(draft, benchmark, {
          composite,
          matchScore: match.score,
          matchedSkills: match.matchedSkills,
          thinData: confidence > 0 && confidence < 0.35,
          lowConfidence: confidence >= 0.35 && confidence < 0.6,
        });
        winProb = win.probability;
      }

      return {
        candidateId: entry.candidateId,
        name: cand.name ?? `Candidate #${entry.candidateId}`,
        role: c?.role,
        status: entry.status,
        addedAt: entry.addedAt,
        matchScore: match.score,
        composite,
        confidence,
        recommendation,
        offer,
        winProbability: winProb,
      };
    });
    return {
      id: role.id,
      name: role.name,
      seniority: role.plan.seniority,
      location: role.plan.location,
      createdAt: role.createdAt,
      updatedAt: role.updatedAt,
      candidates: cands,
    };
  });
  return { roles: pRoles };
}

function buildBrief(summary: PortfolioSummary): string {
  const L: string[] = [];
  const date = new Date(summary.generatedAt).toISOString().slice(0, 10);
  L.push(`# Hiring Command Center — portfolio brief`);
  L.push('');
  L.push(`Generated ${date} · ${summary.totals.roles} role${summary.totals.roles === 1 ? '' : 's'} · ${summary.totals.candidates} candidate${summary.totals.candidates === 1 ? '' : 's'}.`);
  L.push('');
  L.push(`**Portfolio health:** ${summary.portfolioHealth ?? '—'}/100 · ${summary.totals.active} active · ${summary.totals.interviewed} interviewed · ${summary.totals.offers} offer${summary.totals.offers === 1 ? '' : 's'} out.`);
  if (summary.totals.staleCandidates > 0) {
    L.push(`**Stale:** ${summary.totals.staleCandidates} candidate${summary.totals.staleCandidates === 1 ? '' : 's'} idle ≥14 days.`);
  }
  L.push('');
  L.push(`## Comp forecast`);
  L.push(`- Committed (all ${summary.compForecast.offers} drafted offers sign): **${formatLPA(summary.compForecast.committedAnnual)}**/yr`);
  L.push(`- Risk-weighted expected: **${formatLPA(summary.compForecast.expectedAnnual)}**/yr (avg ${Math.round(summary.compForecast.avgWinProbability * 100)}% accept)`);
  L.push('');
  L.push(`## Funnel`);
  for (const s of summary.funnel) {
    const conv = s.conversionFromPrev !== null ? ` (${Math.round(s.conversionFromPrev * 100)}% from prev)` : '';
    L.push(`- ${STAGE_DISPLAY[s.key]}: ${s.here} here · ${s.reached} reached${conv}`);
  }
  L.push('');
  if (summary.talent.length > 0) {
    L.push(`## Top talent across roles`);
    for (const t of summary.talent.slice(0, 5)) {
      L.push(`- ${t.name} — signal ${t.hireSignal} · composite ${t.composite} · ${t.roleName}`);
    }
    L.push('');
  }
  if (summary.attention.length > 0) {
    L.push(`## Needs attention`);
    for (const a of summary.attention) {
      L.push(`- [${a.severity}] ${a.message}`);
    }
    L.push('');
  }
  return L.join('\n');
}

// ---------- small UI pieces ----------

function Ring({ value, hue, size = 120, caption }: {
  value: number | null; hue: string; size?: number; caption?: string;
}) {
  const pct = value === null ? 0 : Math.max(0, Math.min(100, value));
  return (
    <div
      className="cc-hq-ring relative grid place-items-center rounded-full"
      style={{
        width: size, height: size,
        background: `conic-gradient(${hue} ${pct}%, rgba(255,255,255,0.06) 0)`,
      }}
    >
      <div className="absolute rounded-full bg-[#0b0b12]" style={{ inset: 4 }} />
      <div className="relative flex flex-col items-center leading-none">
        <span className="text-3xl font-semibold tabular-nums" style={{ color: hue }}>
          {value ?? '—'}
        </span>
        {caption && (
          <span className="mt-1 text-[9px] uppercase tracking-wider text-white/45">
            {caption}
          </span>
        )}
      </div>
    </div>
  );
}

function Tile({ label, value, detail, tone = 'slate' }: {
  label: string; value: string; detail?: string; tone?: string;
}) {
  return (
    <div className={`cc-tile rounded-xl border p-3 ${TONE_RING[tone]}`}>
      <div className="text-[10px] uppercase tracking-wider opacity-70">{label}</div>
      <div className="mt-1 truncate text-xl font-semibold tabular-nums">{value}</div>
      {detail && <div className="mt-0.5 truncate text-[11px] opacity-65">{detail}</div>}
    </div>
  );
}

function StageBar({ counts }: { counts: Record<string, number> }) {
  const total = PROGRESSION.reduce((s, k) => s + (counts[k] ?? 0), 0)
    + (counts.passed ?? 0);
  if (total === 0) {
    return <div className="h-2 rounded-full bg-white/5" />;
  }
  const segs: { key: string; n: number; hue: string }[] = [];
  for (const k of PROGRESSION) {
    if ((counts[k] ?? 0) > 0) segs.push({ key: k, n: counts[k], hue: STATUS_HEX[STATUS_TONE[k as PipelineStatus]] });
  }
  if ((counts.passed ?? 0) > 0) segs.push({ key: 'passed', n: counts.passed, hue: 'rgba(255,255,255,0.18)' });
  return (
    <div className="flex h-2 overflow-hidden rounded-full bg-white/5">
      {segs.map(s => (
        <div
          key={s.key}
          style={{ width: `${(s.n / total) * 100}%`, background: s.hue }}
          title={`${STATUS_LABEL[s.key as PipelineStatus] ?? s.key}: ${s.n}`}
        />
      ))}
    </div>
  );
}

export default function CommandCenter() {
  const [roles, setRoles] = useState<Role[]>([]);
  const [ready, setReady] = useState(false);
  const [copied, setCopied] = useState(false);
  const [sortKey, setSortKey] = useState<'health' | 'active' | 'days'>('health');

  useEffect(() => {
    setRoles(listRoles());
    setReady(true);
    const onFocus = () => setRoles(listRoles());
    window.addEventListener('focus', onFocus);
    return () => window.removeEventListener('focus', onFocus);
  }, []);

  const input = useMemo(() => gatherInput(roles), [roles]);
  const summary = useMemo(() => buildPortfolio(input), [input]);

  // Per-role status counts (for the stage mini-bars) keyed by role id.
  const statusCounts = useMemo(() => {
    const m: Record<string, Record<string, number>> = {};
    for (const r of input.roles) {
      const acc: Record<string, number> = {};
      for (const c of r.candidates) acc[c.status] = (acc[c.status] ?? 0) + 1;
      m[r.id] = acc;
    }
    return m;
  }, [input]);

  const sortedRoleHealth = useMemo(() => {
    const arr = [...summary.roleHealth];
    arr.sort((a, b) => {
      if (sortKey === 'active') return b.active - a.active;
      if (sortKey === 'days') return b.daysOpen - a.daysOpen;
      return (b.health ?? -1) - (a.health ?? -1);
    });
    return arr;
  }, [summary.roleHealth, sortKey]);

  const onCopy = async () => {
    await copyToClipboard(buildBrief(summary));
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  const onDownload = () => {
    const date = new Date(summary.generatedAt).toISOString().slice(0, 10).replace(/-/g, '');
    downloadText(`credicrew_portfolio_${date}.md`, buildBrief(summary));
  };

  const totalActive = summary.funnel[0]?.reached ?? 0;
  const maxComp = Math.max(summary.compForecast.committedAnnual, 1);
  const hasData = summary.totals.roles > 0;

  return (
    <main className="min-h-screen bg-gradient-to-b from-[#0b0b12] to-black text-white">
      <div className="mx-auto max-w-6xl px-4 pb-24">
        <header className="flex items-center justify-between py-6">
          <Link href="/" className="flex items-center gap-2">
            <div className="grid h-8 w-8 place-items-center rounded-full bg-gradient-to-br from-indigo-400 to-violet-600 font-bold text-white">
              C
            </div>
            <div className="text-lg font-semibold">Credicrew</div>
          </Link>
          <nav className="flex items-center gap-6 text-sm text-white/80">
            <Link href="/" className="hover:text-white">Discover</Link>
            <Link href="/roles" className="hover:text-white">Roles</Link>
            <Link href="/hq" className="text-white">Command Center</Link>
            <Link href="/pipeline" className="hover:text-white">Pipeline</Link>
          </nav>
        </header>

        {/* Title + actions */}
        <section className="mt-2 flex flex-wrap items-end justify-between gap-4">
          <div className="min-w-0 flex-1">
            <div className="text-[11px] uppercase tracking-wider text-violet-300/80">
              Command Center
            </div>
            <h1 className="mt-1 text-3xl font-semibold md:text-4xl">Hiring HQ</h1>
            <p className="mt-2 max-w-2xl text-sm text-white/60">
              Every role, one screen. Aggregate funnel, comp-spend forecast,
              per-role health, your strongest people across the whole pipeline,
              and what needs attention today.
            </p>
          </div>
          {hasData && (
            <div className="flex flex-wrap items-center gap-2">
              <button
                onClick={onCopy}
                className="rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-xs text-white hover:bg-white/10"
              >
                {copied ? 'Copied ✓' : 'Copy brief'}
              </button>
              <button
                onClick={onDownload}
                className="rounded-lg bg-gradient-to-r from-indigo-400 to-violet-400 px-3 py-2 text-xs font-semibold text-black hover:opacity-95"
              >
                Export brief.md
              </button>
            </div>
          )}
        </section>

        {!ready ? (
          <div className="mt-10 text-white/50">Loading…</div>
        ) : !hasData ? (
          <div className="mt-10 rounded-2xl border border-dashed border-white/10 bg-white/[0.02] p-10 text-center">
            <div className="text-lg font-medium text-white">No roles yet</div>
            <p className="mx-auto mt-2 max-w-md text-sm text-white/55">
              The Command Center rolls up every saved role. Create a role from a
              job description, build a shortlist, and the portfolio view lights
              up here.
            </p>
            <Link
              href="/roles/new"
              className="mt-6 inline-block rounded-lg bg-gradient-to-r from-indigo-400 to-violet-400 px-4 py-2 text-sm font-semibold text-black hover:opacity-95"
            >
              Create your first role
            </Link>
          </div>
        ) : (
          <>
            {/* Hero: health ring + KPI grid */}
            <section className="mt-6 grid gap-4 lg:grid-cols-3">
              <div className="cc-hq-hero flex items-center gap-5 rounded-2xl border border-white/10 bg-white/[0.03] p-5">
                <Ring
                  value={summary.portfolioHealth}
                  hue={HEALTH_HUE(summary.portfolioHealth)}
                  caption="health"
                />
                <div className="min-w-0">
                  <div className="text-[10px] uppercase tracking-wider text-white/45">
                    Portfolio health
                  </div>
                  <div className="mt-1 text-sm text-white/75">
                    {summary.portfolioHealth === null
                      ? 'Add candidates to start scoring.'
                      : summary.portfolioHealth >= 75
                      ? 'Pipelines are flowing and well-covered.'
                      : summary.portfolioHealth >= 55
                      ? 'Healthy, with a few rough edges.'
                      : summary.portfolioHealth >= 40
                      ? 'Momentum is slipping in places.'
                      : 'Stalling — see what needs attention.'}
                  </div>
                  <div className="mt-2 text-[11px] text-white/45">
                    Across {summary.totals.active} active candidate
                    {summary.totals.active === 1 ? '' : 's'} in {summary.totals.roles} role
                    {summary.totals.roles === 1 ? '' : 's'}
                    {summary.bottleneck ? ` · bottleneck at ${STAGE_DISPLAY[summary.bottleneck]}` : ''}.
                  </div>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3 lg:col-span-2 lg:grid-cols-3">
                <Tile label="Open roles" value={String(summary.totals.roles)} detail={`${summary.totals.candidates} shortlisted`} tone="indigo" />
                <Tile label="In flight" value={String(summary.totals.active)} detail={`${summary.totals.passed} passed`} tone="sky" />
                <Tile label="Interviews run" value={String(summary.totals.interviewed)} detail={`${summary.totals.offers} at offer`} tone="violet" />
                <Tile label="Offers out" value={String(summary.totals.offers)} detail={`${summary.compForecast.offers} drafted`} tone="emerald" />
                <Tile label="Committed comp" value={formatLPA(summary.compForecast.committedAnnual)} detail="if all offers sign" tone="emerald" />
                <Tile label="Stale" value={String(summary.totals.staleCandidates)} detail="idle ≥14 days" tone={summary.totals.staleCandidates > 0 ? 'amber' : 'slate'} />
              </div>
            </section>

            {/* Funnel */}
            <section className="mt-6 rounded-2xl border border-white/10 bg-white/[0.03] p-5">
              <div className="mb-4 flex items-center justify-between">
                <div>
                  <div className="text-[10px] uppercase tracking-wider text-white/45">
                    Portfolio funnel
                  </div>
                  <div className="text-base font-semibold">All roles · stage flow</div>
                </div>
                <div className="text-[11px] text-white/40">
                  {totalActive} active across the pipeline
                </div>
              </div>
              <div className="space-y-2.5">
                {summary.funnel.map(stage => {
                  const w = totalActive > 0 ? (stage.reached / totalActive) * 100 : 0;
                  const hue = STATUS_HEX[STATUS_TONE[stage.key as PipelineStatus]];
                  return (
                    <div key={stage.key} className="cc-funnel-row flex items-center gap-3">
                      <div className="w-20 shrink-0 text-right text-[11px] text-white/60">
                        {STAGE_DISPLAY[stage.key]}
                      </div>
                      <div className="relative h-7 flex-1 overflow-hidden rounded-lg bg-white/[0.04]">
                        <div
                          className="h-full rounded-lg transition-all"
                          style={{ width: `${Math.max(w, stage.reached > 0 ? 4 : 0)}%`, background: `linear-gradient(90deg, ${hue}cc, ${hue}55)` }}
                        />
                        <div className="absolute inset-0 flex items-center px-2.5 text-[11px] font-medium text-white">
                          {stage.reached}
                          <span className="ml-1 text-white/45">reached</span>
                          {stage.here > 0 && (
                            <span className="ml-2 text-white/45">· {stage.here} here</span>
                          )}
                        </div>
                      </div>
                      <div className="w-14 shrink-0 text-right text-[11px]">
                        {stage.conversionFromPrev !== null ? (
                          <span
                            className={
                              stage.conversionFromPrev >= 0.5
                                ? 'text-emerald-300'
                                : stage.conversionFromPrev >= 0.25
                                ? 'text-amber-300'
                                : 'text-rose-300'
                            }
                          >
                            {Math.round(stage.conversionFromPrev * 100)}%
                          </span>
                        ) : (
                          <span className="text-white/25">—</span>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </section>

            {/* Role leaderboard + comp forecast */}
            <section className="mt-6 grid gap-6 lg:grid-cols-3">
              <div className="lg:col-span-2">
                <div className="mb-3 flex items-center justify-between">
                  <div className="text-[11px] uppercase tracking-wider text-white/45">
                    Role leaderboard
                  </div>
                  <div className="flex items-center gap-1">
                    {(['health', 'active', 'days'] as const).map(k => (
                      <button
                        key={k}
                        onClick={() => setSortKey(k)}
                        className={`rounded-md px-2 py-1 text-[10px] ${
                          sortKey === k
                            ? 'bg-white/10 text-white'
                            : 'text-white/45 hover:bg-white/5 hover:text-white/70'
                        }`}
                      >
                        {k === 'health' ? 'Health' : k === 'active' ? 'In flight' : 'Days open'}
                      </button>
                    ))}
                  </div>
                </div>
                <div className="space-y-2">
                  {sortedRoleHealth.map(rh => (
                    <Link
                      key={rh.roleId}
                      href={`/roles/${rh.roleId}`}
                      className="cc-rank-row block rounded-xl border border-white/10 bg-white/[0.03] p-3 hover:bg-white/[0.06]"
                    >
                      <div className="flex items-center gap-3">
                        <Ring value={rh.health} hue={HEALTH_HUE(rh.health)} size={48} />
                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="truncate font-medium text-white">{rh.roleName}</span>
                            {rh.seniority && (
                              <span className="rounded-full border border-white/10 bg-white/5 px-2 py-0.5 text-[9px] uppercase tracking-wide text-white/55">
                                {rh.seniority}
                              </span>
                            )}
                            {rh.stale > 0 && (
                              <span className="rounded-full border border-amber-400/30 bg-amber-400/10 px-2 py-0.5 text-[9px] text-amber-200">
                                {rh.stale} stale
                              </span>
                            )}
                            {rh.bottleneck && (
                              <span className="rounded-full border border-white/10 bg-white/5 px-2 py-0.5 text-[9px] text-white/50">
                                stuck · {STAGE_DISPLAY[rh.bottleneck]}
                              </span>
                            )}
                          </div>
                          <div className="mt-1.5">
                            <StageBar counts={statusCounts[rh.roleId] ?? {}} />
                          </div>
                          <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[11px] text-white/50">
                            <span>{rh.candidates} candidate{rh.candidates === 1 ? '' : 's'}</span>
                            <span>{rh.interviewed} interviewed</span>
                            <span>{rh.offers} offer{rh.offers === 1 ? '' : 's'}</span>
                            <span>{rh.daysOpen}d open</span>
                            {rh.topCandidate && rh.topCandidate.hireSignal > 0 && (
                              <span className="text-white/70">
                                top · {rh.topCandidate.name} ({rh.topCandidate.hireSignal})
                              </span>
                            )}
                          </div>
                        </div>
                      </div>
                    </Link>
                  ))}
                </div>
              </div>

              <aside className="space-y-4">
                {/* Comp forecast */}
                <div className="cc-hq-comp rounded-2xl border border-white/10 bg-white/[0.03] p-4">
                  <div className="text-[10px] uppercase tracking-wider text-white/45">
                    Comp forecast · annual
                  </div>
                  {summary.compForecast.offers === 0 ? (
                    <div className="mt-3 text-[12px] text-white/45">
                      Draft an offer in Offer Studio to project spend.
                    </div>
                  ) : (
                    <>
                      <div className="mt-3 space-y-3">
                        <div>
                          <div className="flex items-center justify-between text-[11px]">
                            <span className="text-white/60">Committed</span>
                            <span className="font-mono text-emerald-200">{formatLPA(summary.compForecast.committedAnnual)}</span>
                          </div>
                          <div className="mt-1 h-2 overflow-hidden rounded-full bg-white/5">
                            <div className="h-full rounded-full bg-gradient-to-r from-emerald-400 to-emerald-300" style={{ width: '100%' }} />
                          </div>
                        </div>
                        <div>
                          <div className="flex items-center justify-between text-[11px]">
                            <span className="text-white/60">Expected (risk-weighted)</span>
                            <span className="font-mono text-indigo-200">{formatLPA(summary.compForecast.expectedAnnual)}</span>
                          </div>
                          <div className="mt-1 h-2 overflow-hidden rounded-full bg-white/5">
                            <div
                              className="h-full rounded-full bg-gradient-to-r from-indigo-400 to-violet-300"
                              style={{ width: `${(summary.compForecast.expectedAnnual / maxComp) * 100}%` }}
                            />
                          </div>
                        </div>
                      </div>
                      <div className="mt-3 grid grid-cols-2 gap-2 text-[11px]">
                        <div className="rounded-lg border border-white/5 bg-white/[0.02] px-2 py-1.5">
                          <div className="text-white/45">Avg base</div>
                          <div className="font-mono text-white/85">{formatLPA(summary.compForecast.avgBase)}</div>
                        </div>
                        <div className="rounded-lg border border-white/5 bg-white/[0.02] px-2 py-1.5">
                          <div className="text-white/45">Avg accept</div>
                          <div className="font-mono text-white/85">{Math.round(summary.compForecast.avgWinProbability * 100)}%</div>
                        </div>
                      </div>
                    </>
                  )}
                </div>

                {/* Recommendation mix */}
                {summary.totals.interviewed > 0 && (
                  <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-4">
                    <div className="text-[10px] uppercase tracking-wider text-white/45">
                      Recommendation mix
                    </div>
                    <div className="mt-2 flex h-2 overflow-hidden rounded-full bg-white/5">
                      {(['strong_hire', 'lean_yes', 'mixed', 'lean_no', 'no_hire'] as Recommendation[]).map(tier => {
                        const n = summary.recommendationMix[tier];
                        const pct = summary.totals.interviewed > 0 ? (n / summary.totals.interviewed) * 100 : 0;
                        if (pct === 0) return null;
                        return <div key={tier} style={{ width: `${pct}%`, background: TIER_HUE[tier] }} title={`${RECOMMENDATION_LABEL[tier]}: ${n}`} />;
                      })}
                    </div>
                    <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[10px] text-white/60">
                      {(['strong_hire', 'lean_yes', 'mixed', 'lean_no', 'no_hire'] as Recommendation[]).map(tier => (
                        summary.recommendationMix[tier] > 0 ? (
                          <span key={tier} className="inline-flex items-center gap-1">
                            <span className="h-1.5 w-1.5 rounded-full" style={{ background: TIER_HUE[tier] }} />
                            {RECOMMENDATION_LABEL[tier]}
                            <span className="font-mono text-white">{summary.recommendationMix[tier]}</span>
                          </span>
                        ) : null
                      ))}
                    </div>
                  </div>
                )}
              </aside>
            </section>

            {/* Talent + attention */}
            <section className="mt-8 grid gap-6 lg:grid-cols-2">
              {/* Talent leaderboard */}
              <div>
                <div className="mb-3 text-[11px] uppercase tracking-wider text-white/45">
                  Top talent · across all roles
                </div>
                {summary.talent.length === 0 ? (
                  <div className="rounded-2xl border border-dashed border-white/10 bg-white/[0.02] p-6 text-center text-sm text-white/55">
                    Score an interview to surface your strongest people here.
                  </div>
                ) : (
                  <div className="space-y-2">
                    {summary.talent.map((t, i) => {
                      const hue = t.recommendation ? TIER_HUE[t.recommendation] : '#818cf8';
                      return (
                        <Link
                          key={`${t.roleId}-${t.candidateId}`}
                          href={`/roles/${t.roleId}/interview/${t.candidateId}`}
                          className="cc-rank-row flex items-center gap-3 rounded-xl border border-white/10 bg-white/[0.03] p-3 hover:bg-white/[0.06]"
                        >
                          <div className="w-5 text-right font-mono text-[11px] text-white/40">#{i + 1}</div>
                          <div
                            className="relative grid h-11 w-11 shrink-0 place-items-center rounded-full"
                            style={{ background: `conic-gradient(${hue} ${t.hireSignal}%, rgba(255,255,255,0.06) 0)` }}
                          >
                            <div className="absolute rounded-full bg-[#0b0b12]" style={{ inset: 3 }} />
                            <span className="relative text-[13px] font-semibold tabular-nums" style={{ color: hue }}>{t.composite}</span>
                          </div>
                          <div className="min-w-0 flex-1">
                            <div className="truncate font-medium text-white">{t.name}</div>
                            <div className="truncate text-[11px] text-white/50">
                              {t.roleName} · {STATUS_LABEL[t.status]}
                            </div>
                          </div>
                          <div className="shrink-0 text-right">
                            <div className="font-mono text-xs text-white/70">sig {t.hireSignal}</div>
                            <div className="text-[10px] text-white/40">match {t.matchScore}</div>
                          </div>
                        </Link>
                      );
                    })}
                  </div>
                )}
              </div>

              {/* Attention feed */}
              <div>
                <div className="mb-3 text-[11px] uppercase tracking-wider text-white/45">
                  Needs attention
                </div>
                {summary.attention.length === 0 ? (
                  <div className="rounded-2xl border border-emerald-400/20 bg-emerald-400/[0.04] p-6 text-center text-sm text-emerald-200/80">
                    Nothing on fire — every role is moving. ✓
                  </div>
                ) : (
                  <div className="space-y-2">
                    {summary.attention.map((a, i) => {
                      const tone = SEVERITY_TONE[a.severity];
                      const href = a.candidateId !== undefined
                        ? a.kind === 'offer_at_risk'
                          ? `/roles/${a.roleId}/offer/${a.candidateId}`
                          : `/roles/${a.roleId}/interview/${a.candidateId}`
                        : `/roles/${a.roleId}`;
                      return (
                        <Link
                          key={`${a.kind}-${a.roleId}-${a.candidateId ?? i}`}
                          href={href}
                          className={`cc-hq-attn flex items-start gap-2.5 rounded-xl border p-3 text-[12px] ${TONE_RING[tone]}`}
                        >
                          <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-current" />
                          <div className="min-w-0">
                            <div className="leading-snug">{a.message}</div>
                            <div className="mt-0.5 text-[10px] uppercase tracking-wide opacity-55">
                              {a.severity} · {a.roleName}
                            </div>
                          </div>
                        </Link>
                      );
                    })}
                  </div>
                )}
              </div>
            </section>
          </>
        )}
      </div>
    </main>
  );
}
