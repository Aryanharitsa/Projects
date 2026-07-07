'use client';

import { useEffect, useMemo, useState, type CSSProperties } from 'react';
import Link from 'next/link';

import { candidates as CANDIDATES } from '@/data/candidates';
import {
  analyzePortfolio,
  analyzeRole,
  CATEGORIES,
  CATEGORY_BLURB,
  CATEGORY_HEX,
  CATEGORY_LABEL,
  formatShare,
  HEALTH_HEX,
  HEALTH_LABEL,
  type Category,
  type MixCell,
  type RejectedEntry,
  type RoleVerdict,
  type SignalHealth,
  type Suggestion,
  type VerdictCandidate,
} from '@/lib/verdict';
import {
  applyPlanDelta,
  listRoles,
  type Role,
  type VerdictPlanDelta,
} from '@/lib/roles';

// ---------- helpers ----------

function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map(w => w[0]?.toUpperCase() ?? '')
    .join('');
}

// ---------- atoms ----------

function HealthRing({
  health,
  size = 176,
  centerLabel = 'Signal',
}: {
  health: SignalHealth;
  size?: number;
  centerLabel?: string;
}) {
  const hue = HEALTH_HEX[health];
  const pct =
    health === 'healthy'
      ? 92
      : health === 'spec_leak'
      ? 55
      : health === 'overfished'
      ? 48
      : health === 'mixed'
      ? 62
      : 20;
  return (
    <div
      className="relative grid place-items-center rounded-full"
      style={{
        width: size,
        height: size,
        background: `conic-gradient(${hue} ${pct}%, rgba(255,255,255,0.06) 0)`,
      }}
    >
      <div className="absolute rounded-full bg-[#0b0b12]" style={{ inset: 6 }} />
      <div className="relative flex flex-col items-center leading-none">
        <span className="text-[11px] uppercase tracking-wider text-white/55">
          {centerLabel}
        </span>
        <span
          className="mt-1 text-3xl font-semibold tabular-nums"
          style={{ color: hue }}
        >
          {HEALTH_LABEL[health]}
        </span>
      </div>
    </div>
  );
}

function StatTile({
  label,
  value,
  sub,
  hue,
}: {
  label: string;
  value: string;
  sub?: string;
  hue?: string;
}) {
  return (
    <div
      className="rounded-2xl border p-4"
      style={{
        borderColor: 'rgba(255,255,255,0.08)',
        background:
          hue
            ? `linear-gradient(180deg, ${hue}18, transparent)`
            : 'rgba(255,255,255,0.02)',
      }}
    >
      <div className="text-[10px] uppercase tracking-wider text-white/55">
        {label}
      </div>
      <div
        className="mt-2 text-2xl font-semibold tabular-nums"
        style={{ color: hue ?? 'white' }}
      >
        {value}
      </div>
      {sub && (
        <div className="mt-1 text-[11px] text-white/50">{sub}</div>
      )}
    </div>
  );
}

function CategoryChip({
  category,
  count,
  compact = false,
}: {
  category: Category;
  count?: number;
  compact?: boolean;
}) {
  const hue = CATEGORY_HEX[category];
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border ${
        compact ? 'px-2 py-0.5 text-[10px]' : 'px-2.5 py-0.5 text-[11px]'
      } tabular-nums`}
      style={{
        borderColor: `${hue}50`,
        background: `${hue}15`,
        color: hue,
      }}
    >
      <span className="h-1.5 w-1.5 rounded-full" style={{ background: hue }} />
      {CATEGORY_LABEL[category]}
      {typeof count === 'number' && (
        <span className="text-white/80">· {count}</span>
      )}
    </span>
  );
}

function HealthPill({ health }: { health: SignalHealth }) {
  const hue = HEALTH_HEX[health];
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[11px]"
      style={{
        borderColor: `${hue}55`,
        background: `${hue}15`,
        color: hue,
      }}
    >
      <span className="h-1.5 w-1.5 rounded-full" style={{ background: hue }} />
      {HEALTH_LABEL[health]}
    </span>
  );
}

// ---------- Mix bar ----------

function MixBar({ cells, total }: { cells: MixCell[]; total: number }) {
  if (total === 0) {
    return (
      <div className="rounded-xl border border-white/5 bg-white/2 px-3 py-6 text-center text-[12px] text-white/45">
        No passed candidates in this pool yet — bench is empty.
      </div>
    );
  }
  const ordered = CATEGORIES.map(c => cells.find(x => x.category === c)).filter(
    (c): c is MixCell => Boolean(c),
  );
  return (
    <div>
      <div className="flex h-6 w-full overflow-hidden rounded-lg border border-white/5 bg-white/3">
        {ordered.map(c => {
          const hue = CATEGORY_HEX[c.category];
          const pct = c.share * 100;
          if (pct < 0.5) return null;
          return (
            <div
              key={c.category}
              title={`${CATEGORY_LABEL[c.category]} · ${c.count} · ${formatShare(
                c.share,
              )}`}
              className="grid place-items-center text-[10px] font-semibold text-white/90"
              style={{
                width: `${pct}%`,
                background: `linear-gradient(180deg, ${hue}, ${hue}dd)`,
              }}
            >
              {pct >= 8 ? `${Math.round(pct)}%` : ''}
            </div>
          );
        })}
      </div>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {ordered.map(c => (
          <CategoryChip
            key={c.category}
            category={c.category}
            count={c.count}
            compact
          />
        ))}
      </div>
    </div>
  );
}

// ---------- Reason card ----------

function ReasonCard({
  cell,
}: {
  cell: MixCell;
}) {
  const hue = CATEGORY_HEX[cell.category];
  return (
    <div
      className="rounded-2xl border p-4"
      style={{
        borderColor: `${hue}44`,
        background: `linear-gradient(180deg, ${hue}12, rgba(255,255,255,0.02))`,
      }}
    >
      <div className="flex items-baseline justify-between">
        <div className="flex items-center gap-2">
          <span
            className="h-2.5 w-2.5 rounded-full"
            style={{ background: hue }}
          />
          <div className="text-sm font-semibold text-white">
            {CATEGORY_LABEL[cell.category]}
          </div>
        </div>
        <div className="text-[11px] text-white/55 tabular-nums">
          {cell.count} · {formatShare(cell.share)}
        </div>
      </div>
      <div className="mt-1 text-[11px] text-white/55">
        {CATEGORY_BLURB[cell.category]}
      </div>
      <div className="mt-3 space-y-1.5">
        {cell.entries.slice(0, 5).map(e => (
          <RejectedRow key={e.candidateId} entry={e} />
        ))}
        {cell.entries.length === 0 && (
          <div className="text-[11px] text-white/40">
            No candidates surfaced yet.
          </div>
        )}
      </div>
    </div>
  );
}

function RejectedRow({ entry }: { entry: RejectedEntry }) {
  const hue = CATEGORY_HEX[entry.category];
  return (
    <div className="flex items-center gap-2 rounded-lg border border-white/5 bg-white/3 px-2.5 py-1.5">
      <span
        className="grid h-6 w-6 place-items-center rounded-full text-[10px] font-semibold text-white/90"
        style={{ background: `${hue}30` }}
      >
        {initials(entry.name)}
      </span>
      <div className="min-w-0 flex-1">
        <div className="truncate text-[12px] font-medium text-white">
          {entry.name}
        </div>
        <div className="truncate text-[10px] text-white/50">
          {entry.primaryDriver}
        </div>
      </div>
      <span
        className="rounded-full border px-1.5 py-0.5 text-[10px] tabular-nums"
        style={{
          borderColor: 'rgba(255,255,255,0.1)',
          color: 'white',
        }}
      >
        {entry.match.score}
      </span>
    </div>
  );
}

// ---------- Suggestion card ----------

function SuggestionCard({
  suggestion,
  roleId,
  onApplied,
}: {
  suggestion: Suggestion;
  roleId?: string;
  onApplied?: () => void;
}) {
  const [applied, setApplied] = useState(false);
  const hue =
    suggestion.category === 'portfolio'
      ? '#94a3b8'
      : CATEGORY_HEX[suggestion.category as Category];
  const label =
    suggestion.category === 'portfolio'
      ? 'Portfolio'
      : CATEGORY_LABEL[suggestion.category as Category];
  const canApply = roleId && !!suggestion.planDelta && !applied;
  const isAdvisory = suggestion.impact === 0;

  return (
    <div
      className="flex flex-col rounded-2xl border p-4"
      style={{
        borderColor: `${hue}55`,
        background: `linear-gradient(180deg, ${hue}18, rgba(255,255,255,0.02))`,
      }}
    >
      <div className="flex items-center gap-2">
        <span
          className="rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-wider"
          style={{
            borderColor: `${hue}55`,
            background: `${hue}15`,
            color: hue,
          }}
        >
          {label}
        </span>
        {!isAdvisory && (
          <span className="rounded-full border border-white/10 bg-white/5 px-2 py-0.5 text-[10px] uppercase tracking-wider text-white/70 tabular-nums">
            +{suggestion.impact} recoverable
          </span>
        )}
        <span className="ml-auto text-[10px] uppercase tracking-wider text-white/45 tabular-nums">
          {suggestion.confidence}% conf
        </span>
      </div>
      <div className="mt-3 text-sm font-semibold leading-snug text-white">
        {suggestion.action}
      </div>
      <div className="mt-2 text-[12px] leading-snug text-white/60">
        {suggestion.basis}
      </div>
      <div className="mt-3 h-1.5 w-full overflow-hidden rounded-full bg-white/5">
        <div
          className="h-full rounded-full"
          style={{
            width: `${suggestion.confidence}%`,
            background: `linear-gradient(90deg, ${hue}, ${hue}88)`,
          }}
        />
      </div>
      {canApply && suggestion.planDelta && roleId ? (
        <button
          onClick={() => {
            applyPlanDelta(roleId, suggestion.planDelta as VerdictPlanDelta);
            setApplied(true);
            onApplied?.();
          }}
          className="mt-3 rounded-lg border border-white/10 bg-white text-black hover:bg-white/90 py-1.5 text-[12px] font-semibold"
        >
          Apply to JD plan
        </button>
      ) : applied ? (
        <div
          className="mt-3 rounded-lg border py-1.5 text-center text-[11px] font-semibold"
          style={{
            borderColor: `${hue}66`,
            background: `${hue}20`,
            color: hue,
          }}
        >
          Applied ✓
        </div>
      ) : isAdvisory ? (
        <div className="mt-3 rounded-lg border border-white/10 py-1.5 text-center text-[11px] text-white/55">
          Advisory — no plan mutation
        </div>
      ) : (
        <div className="mt-3 rounded-lg border border-white/10 py-1.5 text-center text-[11px] text-white/55">
          Open the role to apply
        </div>
      )}
    </div>
  );
}

// ---------- band strip ----------

function BandStrip({
  band,
  total,
}: {
  band: { strong: number; solid: number; weak: number };
  total: number;
}) {
  const items: Array<{ key: 'strong' | 'solid' | 'weak'; hue: string; label: string; count: number }> =
    [
      { key: 'strong', hue: '#34d399', label: 'Strong (≥80)', count: band.strong },
      { key: 'solid', hue: '#22d3ee', label: 'Solid (60-79)', count: band.solid },
      { key: 'weak', hue: '#94a3b8', label: 'Weak (<60)', count: band.weak },
    ];
  return (
    <div className="grid grid-cols-3 gap-2">
      {items.map(it => (
        <div
          key={it.key}
          className="rounded-xl border border-white/5 bg-white/3 px-3 py-2"
        >
          <div className="text-[10px] uppercase tracking-wider text-white/55">
            {it.label}
          </div>
          <div className="mt-1 flex items-baseline gap-2">
            <span
              className="text-lg font-semibold tabular-nums"
              style={{ color: it.hue }}
            >
              {it.count}
            </span>
            <span className="text-[10px] text-white/45 tabular-nums">
              {total ? Math.round((it.count / total) * 100) : 0}%
            </span>
          </div>
        </div>
      ))}
    </div>
  );
}

// ---------- Role summary card in the portfolio strip ----------

function RolePortfolioCard({
  rv,
  active,
  onClick,
}: {
  rv: RoleVerdict;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={`min-w-[240px] shrink-0 rounded-2xl border p-3 text-left transition ${
        active
          ? 'ring-1 ring-white/40 border-white/25'
          : 'border-white/8 hover:border-white/15'
      }`}
      style={{ background: 'rgba(255,255,255,0.02)' }}
    >
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0">
          <div className="truncate text-[12px] font-semibold text-white">
            {rv.roleName}
          </div>
          <div className="mt-0.5 text-[10px] text-white/50">
            {rv.totalPassed} passed · {formatShare(rv.passShare)} of shortlist
          </div>
        </div>
        <HealthPill health={rv.signalHealth} />
      </div>
      <div className="mt-2 flex h-1.5 overflow-hidden rounded-full bg-white/5">
        {rv.cells.slice(0, 6).map(c => {
          const hue = CATEGORY_HEX[c.category];
          const pct = c.share * 100;
          if (pct < 0.5) return null;
          return (
            <div
              key={c.category}
              style={{ width: `${pct}%`, background: hue }}
            />
          );
        })}
      </div>
      {rv.topReason && (
        <div className="mt-2 flex items-center gap-1.5">
          <span
            className="h-1.5 w-1.5 rounded-full"
            style={{ background: CATEGORY_HEX[rv.topReason] }}
          />
          <span className="text-[10px] text-white/60">
            Top: {CATEGORY_LABEL[rv.topReason]}
          </span>
        </div>
      )}
    </button>
  );
}

// ---------- Empty state ----------

function EmptyState() {
  return (
    <div className="mx-auto mt-16 max-w-xl rounded-2xl border border-white/8 bg-white/2 p-8 text-center">
      <div className="mx-auto grid h-14 w-14 place-items-center rounded-full bg-gradient-to-br from-indigo-500/40 to-violet-600/40 text-2xl">
        ⚖︎
      </div>
      <h2 className="mt-4 text-lg font-semibold text-white">
        Verdict has nothing to review yet.
      </h2>
      <p className="mt-2 text-[13px] text-white/60">
        Verdict opens the graveyard: every candidate with status <code>passed</code>{' '}
        in any role&apos;s shortlist gets re-scored, categorized, and rolled up into
        a health verdict on your JD spec. Create a role, add candidates, and
        mark some of them <code>passed</code> — Verdict will fill in.
      </p>
      <div className="mt-5 flex justify-center gap-2">
        <Link
          href="/roles/new"
          className="rounded-lg bg-white px-3 py-1.5 text-[12px] font-semibold text-black hover:bg-white/90"
        >
          Create a role
        </Link>
        <Link
          href="/"
          className="rounded-lg border border-white/10 bg-white/5 px-3 py-1.5 text-[12px] text-white/80 hover:bg-white/10"
        >
          Discover candidates
        </Link>
      </div>
    </div>
  );
}

// ---------- Page ----------

export default function VerdictPage() {
  const [roles, setRoles] = useState<Role[]>([]);
  const [selectedId, setSelectedId] = useState<string | 'portfolio'>('portfolio');
  const [tick, setTick] = useState(0);
  const refresh = () => setTick(t => t + 1);

  useEffect(() => {
    setRoles(listRoles());
  }, [tick]);

  const roleVerdicts: RoleVerdict[] = useMemo(() => {
    const candMap = new Map<number, VerdictCandidate>();
    for (const c of CANDIDATES) candMap.set(c.id, c);

    return roles.map(role => {
      const passedEntries = role.shortlist.filter(e => e.status === 'passed');
      const passedCandidates: VerdictCandidate[] = passedEntries
        .map(e => candMap.get(e.candidateId))
        .filter((c): c is VerdictCandidate => Boolean(c));
      return analyzeRole({
        roleId: role.id,
        roleName: role.name,
        plan: role.plan,
        passedCandidates,
        totalShortlistSize: role.shortlist.length,
      });
    });
  }, [roles]);

  const portfolio = useMemo(
    () => analyzePortfolio(roleVerdicts),
    [roleVerdicts],
  );

  const active =
    selectedId === 'portfolio'
      ? null
      : roleVerdicts.find(r => r.roleId === selectedId) ?? null;

  const showEmpty = roles.length === 0;

  const headerHue =
    active
      ? HEALTH_HEX[active.signalHealth]
      : HEALTH_HEX[portfolio.signalHealth];

  const gradientStyle: CSSProperties = {
    background: `radial-gradient(1200px 400px at 50% -10%, ${headerHue}22, transparent)`,
  };

  return (
    <main className="min-h-screen bg-[#0b0b12] text-white">
      <div
        className="border-b border-white/5 px-4 py-8 sm:py-10"
        style={gradientStyle}
      >
        <div className="mx-auto max-w-6xl">
          <div className="flex items-center gap-2 text-[11px] uppercase tracking-wider text-white/50">
            <span
              className="inline-flex h-2 w-2 rounded-full"
              style={{ background: headerHue }}
            />
            Rejection ontology
          </div>
          <h1 className="mt-2 text-3xl font-semibold tracking-tight sm:text-4xl">
            Verdict —{' '}
            <span style={{ color: headerHue }}>
              why you&apos;re passing everyone
            </span>
          </h1>
          <p className="mt-2 max-w-3xl text-[13px] text-white/60">
            Every prior surface answers <em>who to pick</em>. Verdict opens the
            graveyard and asks the two questions every quarter-two recruiter
            actually opens with: <em>why am I passing everyone?</em> and{' '}
            <em>is the JD the reason, or is the pool the reason?</em> Every
            passed candidate lands in a seven-cell ontology in strict priority
            order, the mix rolls up into a health verdict, and the Refinement
            Advisor turns the mix into deterministic JD tweaks with quantified
            recovery.
          </p>
        </div>
      </div>

      {showEmpty ? (
        <EmptyState />
      ) : (
        <div className="mx-auto max-w-6xl px-4 py-8">
          {/* Portfolio hero */}
          <section className="grid gap-4 rounded-3xl border border-white/8 bg-gradient-to-br from-white/3 to-white/2 p-5 sm:grid-cols-[auto_1fr]">
            <div className="grid place-items-center">
              <HealthRing
                health={
                  active ? active.signalHealth : portfolio.signalHealth
                }
              />
            </div>
            <div className="grid gap-3 sm:grid-cols-3">
              <StatTile
                label="Passed"
                value={String(
                  active ? active.totalPassed : portfolio.totalPassed,
                )}
                sub={
                  (active ? active.totalConsidered : portfolio.totalConsidered) > 0
                    ? `of ${
                        active
                          ? active.totalConsidered
                          : portfolio.totalConsidered
                      } shortlisted`
                    : 'no shortlist data'
                }
              />
              <StatTile
                label="Funnel waste"
                value={`${
                  active ? active.funnelWaste : portfolio.funnelWaste
                }/100`}
                sub="mean composite of passed pool"
                hue={headerHue}
              />
              <StatTile
                label="Top reason"
                value={
                  (active ? active.topReason : portfolio.topReason)
                    ? CATEGORY_LABEL[
                        (active
                          ? active.topReason
                          : portfolio.topReason) as Category
                      ]
                    : '—'
                }
                sub={
                  (active ? active.topReason : portfolio.topReason)
                    ? CATEGORY_BLURB[
                        (active
                          ? active.topReason
                          : portfolio.topReason) as Category
                      ]
                    : 'no signal yet'
                }
                hue={
                  (active ? active.topReason : portfolio.topReason)
                    ? CATEGORY_HEX[
                        (active
                          ? active.topReason
                          : portfolio.topReason) as Category
                      ]
                    : undefined
                }
              />
            </div>
          </section>

          {/* Selector strip */}
          <section className="mt-6">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold uppercase tracking-wider text-white/70">
                Portfolio strip
              </h2>
              <span className="text-[11px] text-white/45">
                {roles.length} role{roles.length === 1 ? '' : 's'} tracked
              </span>
            </div>
            <div className="mt-3 flex snap-x gap-3 overflow-x-auto pb-2">
              <button
                onClick={() => setSelectedId('portfolio')}
                className={`min-w-[220px] shrink-0 rounded-2xl border p-3 text-left transition ${
                  selectedId === 'portfolio'
                    ? 'ring-1 ring-white/40 border-white/25'
                    : 'border-white/8 hover:border-white/15'
                }`}
                style={{
                  background:
                    'linear-gradient(180deg, rgba(255,255,255,0.05), rgba(255,255,255,0.02))',
                }}
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="text-[12px] font-semibold text-white">
                    Whole portfolio
                  </div>
                  <HealthPill health={portfolio.signalHealth} />
                </div>
                <div className="mt-1 text-[10px] text-white/50">
                  {portfolio.totalPassed} passed · {roles.length} roles
                </div>
                <div className="mt-2">
                  <MixBar cells={portfolio.aggregatedCells} total={portfolio.totalPassed} />
                </div>
              </button>
              {roleVerdicts.map(rv => (
                <RolePortfolioCard
                  key={rv.roleId}
                  rv={rv}
                  active={selectedId === rv.roleId}
                  onClick={() => setSelectedId(rv.roleId)}
                />
              ))}
            </div>
          </section>

          {/* Detail body */}
          <section className="mt-8 grid gap-6 lg:grid-cols-[1.4fr_1fr]">
            <div className="space-y-6">
              <div className="rounded-2xl border border-white/8 bg-white/2 p-5">
                <div className="flex items-baseline justify-between">
                  <h3 className="text-sm font-semibold uppercase tracking-wider text-white/70">
                    {active ? `${active.roleName} · rejection mix` : 'Rejection mix'}
                  </h3>
                  <span className="text-[11px] text-white/45 tabular-nums">
                    {active ? active.totalPassed : portfolio.totalPassed} passed
                  </span>
                </div>
                <div className="mt-4">
                  <MixBar
                    cells={active ? active.cells : portfolio.aggregatedCells}
                    total={active ? active.totalPassed : portfolio.totalPassed}
                  />
                </div>
              </div>

              {active && active.cells.length > 0 && (
                <div>
                  <h3 className="text-sm font-semibold uppercase tracking-wider text-white/70">
                    Reason cards
                  </h3>
                  <div className="mt-3 grid gap-3 sm:grid-cols-2">
                    {active.cells.map(cell => (
                      <ReasonCard key={cell.category} cell={cell} />
                    ))}
                  </div>
                </div>
              )}

              {active && (
                <div className="rounded-2xl border border-white/8 bg-white/2 p-5">
                  <div className="flex items-baseline justify-between">
                    <h3 className="text-sm font-semibold uppercase tracking-wider text-white/70">
                      Score band of the reject pile
                    </h3>
                    <span className="text-[11px] text-white/45">higher is more waste</span>
                  </div>
                  <div className="mt-3">
                    <BandStrip band={active.bandDistribution} total={active.totalPassed} />
                  </div>
                </div>
              )}

              {active && active.commonMissingSkills.length > 0 && (
                <div className="rounded-2xl border border-white/8 bg-white/2 p-5">
                  <div className="flex items-baseline justify-between">
                    <h3 className="text-sm font-semibold uppercase tracking-wider text-white/70">
                      Skills most-often-missing on rejects
                    </h3>
                    <span className="text-[11px] text-white/45">
                      the disqualifiers
                    </span>
                  </div>
                  <div className="mt-3 space-y-2">
                    {active.commonMissingSkills.map(m => {
                      const max = active.commonMissingSkills[0].count;
                      const pct = (m.count / max) * 100;
                      return (
                        <div key={m.skill}>
                          <div className="flex items-baseline justify-between">
                            <div className="text-[12px] text-white">
                              {m.skill}
                            </div>
                            <div className="text-[11px] tabular-nums text-white/50">
                              {m.count} reject{m.count === 1 ? '' : 's'}
                            </div>
                          </div>
                          <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-white/5">
                            <div
                              className="h-full rounded-full"
                              style={{
                                width: `${pct}%`,
                                background:
                                  'linear-gradient(90deg, #f43f5e, #fb923c)',
                              }}
                            />
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>

            <div className="space-y-4">
              <div className="rounded-2xl border border-white/8 bg-gradient-to-br from-white/5 to-white/2 p-5">
                <h3 className="text-sm font-semibold uppercase tracking-wider text-white/70">
                  Refinement advisor
                </h3>
                <p className="mt-1 text-[11px] text-white/50">
                  Deterministic JD tweaks — apply mutates the role&apos;s plan directly
                  without touching the JD text.
                </p>
                <div className="mt-4 space-y-3">
                  {(active ? active.suggestions : portfolio.topSuggestions).map(
                    s => (
                      <SuggestionCard
                        key={s.id}
                        suggestion={s}
                        roleId={active?.roleId}
                        onApplied={refresh}
                      />
                    ),
                  )}
                  {(active ? active.suggestions.length : portfolio.topSuggestions.length) === 0 && (
                    <div className="rounded-xl border border-white/8 bg-white/2 p-4 text-center text-[12px] text-white/50">
                      Not enough passes yet to refine the spec. Come back once
                      the reject pile carries at least 3 candidates.
                    </div>
                  )}
                </div>
              </div>

              {active && (
                <div className="rounded-2xl border border-white/8 bg-white/2 p-5">
                  <h3 className="text-sm font-semibold uppercase tracking-wider text-white/70">
                    Current plan
                  </h3>
                  <dl className="mt-3 space-y-2 text-[12px]">
                    <div className="flex items-baseline justify-between gap-3">
                      <dt className="text-white/50">Seniority</dt>
                      <dd className="text-white/90">
                        {active.planSummary.seniority ?? '—'}
                      </dd>
                    </div>
                    <div className="flex items-baseline justify-between gap-3">
                      <dt className="text-white/50">Location</dt>
                      <dd className="text-white/90">
                        {active.planSummary.location ?? '—'}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-white/50">Skills</dt>
                      <dd className="mt-1 flex flex-wrap gap-1.5">
                        {active.planSummary.skills.length === 0 && (
                          <span className="text-white/45">—</span>
                        )}
                        {active.planSummary.skills.map(s => (
                          <span
                            key={s}
                            className="rounded-full border border-white/10 bg-white/5 px-2 py-0.5 text-[10px] text-white/80"
                          >
                            {s}
                          </span>
                        ))}
                      </dd>
                    </div>
                  </dl>
                  <Link
                    href={`/roles/${active.roleId}`}
                    className="mt-4 inline-flex items-center gap-1 text-[11px] text-white/60 hover:text-white"
                  >
                    Open role →
                  </Link>
                </div>
              )}

              <div className="rounded-2xl border border-white/8 bg-white/2 p-5">
                <h3 className="text-sm font-semibold uppercase tracking-wider text-white/70">
                  How the physics reads
                </h3>
                <ul className="mt-3 space-y-2 text-[11px] text-white/65">
                  <li>
                    <span
                      className="mr-2 inline-block h-2 w-2 rounded-full align-middle"
                      style={{ background: '#10b981' }}
                    />
                    <b>culture_signal</b> — score ≥ 65, skills ≥ 60%, seniority
                    match, location full/partial. Panel doing the signal work.
                  </li>
                  <li>
                    <span
                      className="mr-2 inline-block h-2 w-2 rounded-full align-middle"
                      style={{ background: '#0ea5e9' }}
                    />
                    <b>location_gap</b> — spec location set & candidate is neither
                    there nor remote/hybrid.
                  </li>
                  <li>
                    <span
                      className="mr-2 inline-block h-2 w-2 rounded-full align-middle"
                      style={{ background: '#a855f7' }}
                    />
                    <b>seniority_over</b> — candidate tier &gt; wanted tier + 1.
                  </li>
                  <li>
                    <span
                      className="mr-2 inline-block h-2 w-2 rounded-full align-middle"
                      style={{ background: '#f59e0b' }}
                    />
                    <b>seniority_under</b> — candidate tier &lt; wanted tier.
                  </li>
                  <li>
                    <span
                      className="mr-2 inline-block h-2 w-2 rounded-full align-middle"
                      style={{ background: '#f43f5e' }}
                    />
                    <b>skills_short</b> — matched &lt; 40% of a spec that asks
                    for at least 3 skills.
                  </li>
                  <li>
                    <span
                      className="mr-2 inline-block h-2 w-2 rounded-full align-middle"
                      style={{ background: '#94a3b8' }}
                    />
                    <b>mixed_signal</b> — moderate on every axis, no dominant miss.
                  </li>
                </ul>
              </div>
            </div>
          </section>
        </div>
      )}
    </main>
  );
}
