'use client';

import { useEffect, useMemo, useState, type CSSProperties } from 'react';
import Link from 'next/link';

import { candidates as CANDIDATES } from '@/data/candidates';
import {
  REVIVE_COMPOSITE_FLOOR,
  REVIVE_MATCH_FLOOR,
  RECENCY_HALF_LIFE_DAYS,
  SOURCING_COST_PER_HIRE_USD,
  STALE_DAYS,
  TIER_HEX,
  TIER_LABEL,
  analyzeRevive,
  buildBrief,
  formatDays,
  formatUsd,
  liftBand,
  tierFor,
  type ReviveOpportunity,
  type ReviveSummary,
} from '@/lib/revive';
import {
  addToShortlist,
  listRoles,
  removeFromShortlist,
  setNote,
  type Role,
} from '@/lib/roles';

// ---------- small UI helpers ----------

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

function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map(w => w[0]?.toUpperCase() ?? '')
    .join('');
}

// ---------- atoms ----------

function ReactivationRing({
  score,
  size = 168,
}: {
  score: number;
  size?: number;
}) {
  const tier = tierFor(score);
  const hue = TIER_HEX[tier];
  const pct = Math.max(0, Math.min(100, score));
  return (
    <div
      className="cc-rv-ring relative grid place-items-center rounded-full"
      style={{
        width: size,
        height: size,
        background: `conic-gradient(${hue} ${pct}%, rgba(255,255,255,0.06) 0)`,
      }}
    >
      <div className="absolute rounded-full bg-[#0b0b12]" style={{ inset: 6 }} />
      <div className="relative flex flex-col items-center leading-none">
        <span className="text-[11px] uppercase tracking-wider text-white/55">
          Reactivation
        </span>
        <span
          className="mt-1 text-4xl font-semibold tabular-nums"
          style={{ color: hue }}
        >
          {score}
        </span>
        <span className="mt-1 text-[10px] uppercase tracking-wider text-white/45">
          {TIER_LABEL[tier]} pick
        </span>
      </div>
    </div>
  );
}

function ScoreDot({ score, label }: { score: number; label?: string }) {
  const tier = tierFor(score);
  const hue = TIER_HEX[tier];
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[11px] tabular-nums"
      style={{
        borderColor: `${hue}50`,
        background: `${hue}15`,
        color: hue,
      }}
    >
      <span className="h-1.5 w-1.5 rounded-full" style={{ background: hue }} />
      {label ?? `${score}`}
    </span>
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
      className="relative overflow-hidden rounded-xl border border-white/10 bg-white/5 p-4"
      style={
        hue
          ? ({
              ['--rv-accent' as keyof CSSProperties]: hue,
            } as CSSProperties)
          : undefined
      }
    >
      <div
        aria-hidden
        className="pointer-events-none absolute inset-x-0 top-0 h-px opacity-70"
        style={hue ? { background: hue } : undefined}
      />
      <div className="text-[11px] uppercase tracking-wider text-white/55">{label}</div>
      <div
        className="mt-1 text-2xl font-semibold tabular-nums"
        style={hue ? { color: hue } : undefined}
      >
        {value}
      </div>
      {sub && <div className="mt-1 text-[11px] text-white/50">{sub}</div>}
    </div>
  );
}

function RecencyBar({ recency, days }: { recency: number; days: number }) {
  const pct = Math.max(4, Math.round(recency * 100));
  const stale = days >= STALE_DAYS;
  const hue = stale ? '#f43f5e' : recency >= 0.7 ? '#10b981' : '#f59e0b';
  return (
    <div className="flex w-full flex-col gap-1">
      <div className="flex items-center justify-between text-[10px] uppercase tracking-wider text-white/45">
        <span>Recency</span>
        <span className="tabular-nums text-white/65">
          {formatDays(days)} ago · {Math.round(recency * 100)}%
        </span>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-white/5">
        <div
          className="h-full rounded-full transition-all"
          style={{ width: `${pct}%`, background: hue }}
        />
      </div>
    </div>
  );
}

function StaleBadge() {
  return (
    <span className="rounded-full border border-rose-400/30 bg-rose-400/10 px-2 py-0.5 text-[10px] uppercase tracking-wider text-rose-200">
      stale · confirm interest
    </span>
  );
}

// ---------- header ----------

function HeaderNav() {
  return (
    <header className="flex items-center justify-between py-6">
      <Link href="/" className="flex items-center gap-2 font-semibold text-white">
        <span className="grid h-7 w-7 place-items-center rounded-full bg-gradient-to-br from-indigo-400 to-violet-600 text-xs font-bold">
          C
        </span>
        <span className="text-lg">Credicrew</span>
      </Link>
      <nav className="hidden items-center gap-1 md:flex">
        <Link href="/" className="rounded-lg px-3 py-1.5 text-sm text-white/70 hover:bg-white/5 hover:text-white">Discover</Link>
        <Link href="/roles" className="rounded-lg px-3 py-1.5 text-sm text-white/70 hover:bg-white/5 hover:text-white">Roles</Link>
        <Link href="/hq" className="rounded-lg px-3 py-1.5 text-sm text-white/70 hover:bg-white/5 hover:text-white">Command Center</Link>
        <Link href="/crosswind" className="rounded-lg px-3 py-1.5 text-sm text-white/70 hover:bg-white/5 hover:text-white">Crosswind</Link>
        <Link
          href="/revive"
          className="rounded-lg bg-white/10 px-3 py-1.5 text-sm text-white"
        >
          Revive
        </Link>
        <Link href="/cadence" className="rounded-lg px-3 py-1.5 text-sm text-white/70 hover:bg-white/5 hover:text-white">Cadence</Link>
        <Link href="/sources" className="rounded-lg px-3 py-1.5 text-sm text-white/70 hover:bg-white/5 hover:text-white">Channels</Link>
        <Link href="/pipeline" className="rounded-lg px-3 py-1.5 text-sm text-white/70 hover:bg-white/5 hover:text-white">Pipeline</Link>
      </nav>
    </header>
  );
}

// ---------- empty state ----------

function EmptyState() {
  return (
    <div className="mx-auto mt-16 max-w-2xl rounded-2xl border border-white/10 bg-white/5 p-8 text-center">
      <div className="mx-auto grid h-12 w-12 place-items-center rounded-full bg-gradient-to-br from-rose-400/60 to-fuchsia-500/60 text-xl">
        🥈
      </div>
      <h2 className="mt-4 text-xl font-semibold">No silver medalists yet</h2>
      <p className="mt-2 text-sm text-white/60">
        When you mark a candidate as <span className="rounded bg-rose-400/15 px-1.5 text-rose-200">Passed</span> in any
        role, they enter your silver pool. Revive surfaces them when a different open role would be a better fit, so
        sourcing cost you&apos;ve already paid doesn&apos;t evaporate.
      </p>
      <div className="mt-4 flex items-center justify-center gap-2 text-xs">
        <Link
          href="/roles"
          className="rounded-md border border-white/10 bg-white/5 px-3 py-1.5 text-white/80 hover:bg-white/10"
        >
          Open Roles
        </Link>
        <Link
          href="/"
          className="rounded-md border border-indigo-400/40 bg-indigo-500/15 px-3 py-1.5 text-indigo-200 hover:bg-indigo-500/25"
        >
          Discover
        </Link>
      </div>
    </div>
  );
}

// ---------- opportunity card ----------

function OpportunityCard({
  opp,
  onReactivate,
  alternativesCount,
  onToggleAlternatives,
  alternativesOpen,
  alternatives,
}: {
  opp: ReviveOpportunity;
  onReactivate: (
    candidateId: number,
    fromRoleId: string,
    toRoleId: string,
    toRoleName: string,
  ) => void;
  alternativesCount: number;
  onToggleAlternatives: () => void;
  alternativesOpen: boolean;
  alternatives: ReviveOpportunity[];
}) {
  const stale = opp.daysDormant >= STALE_DAYS;
  const tier = tierFor(opp.reactivationScore);
  const tierHue = TIER_HEX[tier];
  const deltaText = opp.delta > 0 ? `+${opp.delta}` : `${opp.delta}`;

  return (
    <div
      className="cc-rv-card group relative overflow-hidden rounded-2xl border border-white/10 bg-gradient-to-br from-white/[0.07] to-white/[0.02] p-5"
      style={
        {
          ['--rv-accent' as keyof CSSProperties]: tierHue,
        } as CSSProperties
      }
    >
      <div
        aria-hidden
        className="pointer-events-none absolute inset-x-0 top-0 h-px"
        style={{ background: `linear-gradient(to right, transparent, ${tierHue}, transparent)` }}
      />

      <div className="flex items-start gap-4">
        <div
          className="grid h-12 w-12 shrink-0 place-items-center rounded-full font-semibold"
          style={{
            background: `${tierHue}22`,
            color: tierHue,
            border: `1px solid ${tierHue}55`,
          }}
        >
          {initials(opp.candidateName)}
        </div>

        <div className="flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <div className="text-base font-semibold text-white">{opp.candidateName}</div>
            <ScoreDot score={opp.reactivationScore} label={`Reactivation ${opp.reactivationScore}`} />
            {stale && <StaleBadge />}
          </div>

          <div className="mt-1 flex flex-wrap items-center gap-2 text-[12px] text-white/70">
            <span className="inline-flex items-center gap-1 rounded-md border border-rose-400/30 bg-rose-400/10 px-2 py-0.5 text-rose-200">
              <span className="text-[10px] uppercase tracking-wider opacity-80">From</span>
              <span className="font-medium">{opp.fromRoleName}</span>
              <span className="tabular-nums opacity-75">({opp.fromScore})</span>
            </span>
            <span className="text-white/30">→</span>
            <span className="inline-flex items-center gap-1 rounded-md border border-emerald-400/30 bg-emerald-400/10 px-2 py-0.5 text-emerald-200">
              <span className="text-[10px] uppercase tracking-wider opacity-80">To</span>
              <span className="font-medium">{opp.toRoleName}</span>
              <span className="tabular-nums opacity-75">({opp.toScore})</span>
            </span>
            <span
              className="ml-1 inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] tabular-nums"
              style={{
                borderColor: opp.delta >= 0 ? '#34d39950' : '#f4344550',
                background: opp.delta >= 0 ? '#34d39915' : '#f4344515',
                color: opp.delta >= 0 ? '#34d399' : '#f87171',
              }}
            >
              Δ {deltaText}
            </span>
          </div>
        </div>

        <div className="ml-auto shrink-0">
          <ReactivationRing score={opp.reactivationScore} size={108} />
        </div>
      </div>

      {/* Skill diff for the new role */}
      <div className="mt-4 grid gap-3 md:grid-cols-2">
        <div className="rounded-xl border border-white/5 bg-white/[0.03] p-3">
          <div className="text-[10px] uppercase tracking-wider text-white/45">
            Matched · {opp.toRoleName}
          </div>
          <div className="mt-1 flex flex-wrap gap-1.5">
            {opp.match.matchedSkills.length === 0 ? (
              <span className="text-[12px] text-white/45">
                {opp.match.missingSkills.length === 0
                  ? 'JD specifies no required skills.'
                  : '— none yet —'}
              </span>
            ) : (
              opp.match.matchedSkills.map(s => (
                <span
                  key={s}
                  className="rounded-full border border-emerald-400/30 bg-emerald-400/10 px-2 py-0.5 text-[11px] text-emerald-200"
                >
                  {s}
                </span>
              ))
            )}
          </div>
        </div>
        <div className="rounded-xl border border-white/5 bg-white/[0.03] p-3">
          <div className="text-[10px] uppercase tracking-wider text-white/45">Missing</div>
          <div className="mt-1 flex flex-wrap gap-1.5">
            {opp.match.missingSkills.length === 0 ? (
              <span className="text-[12px] text-emerald-300/70">— none —</span>
            ) : (
              opp.match.missingSkills.map(s => (
                <span
                  key={s}
                  className="rounded-full border border-white/10 bg-white/5 px-2 py-0.5 text-[11px] text-white/60"
                >
                  {s}
                </span>
              ))
            )}
          </div>
        </div>
      </div>

      {/* Recency bar */}
      <div className="mt-4">
        <RecencyBar recency={opp.recency} days={opp.daysDormant} />
      </div>

      {/* Why */}
      <ul className="mt-3 space-y-1 text-[12px] leading-snug text-white/70">
        {opp.why.map((w, i) => (
          <li key={i} className="flex gap-2">
            <span className="mt-0.5 inline-block h-1 w-1 shrink-0 rounded-full bg-white/40" />
            <span>{w}</span>
          </li>
        ))}
      </ul>

      {/* Actions */}
      <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-white/5 pt-3">
        <button
          onClick={() =>
            onReactivate(opp.candidateId, opp.fromRoleId, opp.toRoleId, opp.toRoleName)
          }
          className="rounded-md bg-emerald-500 px-3 py-1.5 text-[12px] font-medium text-black hover:bg-emerald-400"
          title={`Move ${opp.candidateName} from ${opp.fromRoleName} (passed) to ${opp.toRoleName} as new`}
        >
          Reactivate to {opp.toRoleName}
        </button>
        {alternativesCount > 0 && (
          <button
            onClick={onToggleAlternatives}
            className="rounded-md border border-white/10 bg-white/5 px-3 py-1.5 text-[12px] text-white/75 hover:bg-white/10"
          >
            {alternativesOpen ? 'Hide' : `Show ${alternativesCount} other fit${alternativesCount === 1 ? '' : 's'}`}
          </button>
        )}
        <Link
          href={`/roles/${opp.fromRoleId}`}
          className="ml-auto text-[12px] text-white/45 hover:text-white/75"
        >
          View original role →
        </Link>
      </div>

      {alternativesOpen && alternatives.length > 0 && (
        <div className="mt-3 rounded-xl border border-white/5 bg-black/30 p-3">
          <div className="text-[10px] uppercase tracking-wider text-white/45">
            Other open roles that fit
          </div>
          <ul className="mt-2 space-y-1">
            {alternatives.map(a => (
              <li
                key={`${a.candidateId}-${a.toRoleId}`}
                className="flex items-center justify-between gap-3 rounded-md border border-white/5 bg-white/[0.03] px-2.5 py-1.5"
              >
                <div className="min-w-0 flex-1 truncate text-[12px] text-white/80">
                  → {a.toRoleName}
                  <span className="ml-2 text-[10px] text-white/40">
                    match {a.toScore} · {formatDays(a.daysDormant)} dormant
                  </span>
                </div>
                <ScoreDot score={a.reactivationScore} />
                <button
                  onClick={() =>
                    onReactivate(a.candidateId, a.fromRoleId, a.toRoleId, a.toRoleName)
                  }
                  className="rounded-md border border-emerald-400/40 bg-emerald-500/15 px-2 py-1 text-[11px] text-emerald-200 hover:bg-emerald-500/25"
                >
                  Reactivate
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

// ---------- per-role card ----------

function PerRoleCard({
  row,
  onReactivate,
}: {
  row: ReviveSummary['perRole'][number];
  onReactivate: (
    candidateId: number,
    fromRoleId: string,
    toRoleId: string,
    toRoleName: string,
  ) => void;
}) {
  const tier = tierFor(row.bestScore);
  const hue = TIER_HEX[tier];
  return (
    <div
      className="relative overflow-hidden rounded-xl border border-white/10 bg-white/[0.03] p-4"
      style={
        {
          ['--rv-accent' as keyof CSSProperties]: hue,
        } as CSSProperties
      }
    >
      <div
        aria-hidden
        className="pointer-events-none absolute inset-y-0 left-0 w-[3px]"
        style={{ background: hue }}
      />
      <div className="flex items-baseline justify-between">
        <Link
          href={`/roles/${row.roleId}`}
          className="truncate text-sm font-semibold text-white hover:underline"
        >
          {row.roleName}
        </Link>
        <ScoreDot score={row.bestScore} label={`Best ${row.bestScore}`} />
      </div>
      <ul className="mt-3 space-y-1.5">
        {row.picks.slice(0, 5).map(p => (
          <li
            key={`${p.candidateId}-${p.fromRoleId}`}
            className="flex items-center justify-between gap-2 rounded-md border border-white/5 bg-black/20 px-2 py-1.5"
          >
            <div className="min-w-0 flex-1 truncate text-[12px] text-white/80">
              {p.candidateName}
              <span className="ml-2 text-[10px] text-white/45">
                from {p.fromRoleName} · {formatDays(p.daysDormant)}
              </span>
            </div>
            <ScoreDot score={p.reactivationScore} />
            <button
              onClick={() =>
                onReactivate(p.candidateId, p.fromRoleId, p.toRoleId, p.toRoleName)
              }
              className="rounded-md border border-emerald-400/40 bg-emerald-500/15 px-2 py-0.5 text-[10px] text-emerald-200 hover:bg-emerald-500/25"
              title={`Reactivate ${p.candidateName} from ${p.fromRoleName} into ${p.toRoleName}`}
            >
              Reactivate
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

// ---------- seed helpers ----------

/**
 * One-click "seed silver pool" for demos. Picks a small set of candidates
 * not currently sitting in any role's shortlist, drops them into the
 * highest-fit open role as a `passed` entry with synthetic dormancy.
 * Pure UX sugar — does nothing destructive.
 */
function seedSilverPool(roles: Role[], candidates: typeof CANDIDATES): number {
  if (roles.length === 0) return 0;
  const occupied = new Set<number>();
  for (const r of roles) for (const e of r.shortlist) occupied.add(e.candidateId);

  const fresh = candidates.filter(c => !occupied.has(c.id)).slice(0, 8);
  if (fresh.length === 0) return 0;

  let inserted = 0;
  for (let i = 0; i < fresh.length; i++) {
    const c = fresh[i];
    const role = roles[i % roles.length];
    addToShortlist(role.id, c.id, 'passed');
    // Touch the entry's stageChangedAt to give it a synthetic dormancy spread.
    const synthDays = 5 + i * 22; // 5, 27, 49, 71, ...
    const ts = Date.now() - synthDays * 86_400_000;
    // Write back via raw localStorage to set stageChangedAt — the public
    // API doesn't expose it directly.
    try {
      const raw = localStorage.getItem('credicrew:roles:v1');
      if (raw) {
        const list = JSON.parse(raw) as Role[];
        const idx = list.findIndex(r => r.id === role.id);
        if (idx >= 0) {
          const sIdx = list[idx].shortlist.findIndex(e => e.candidateId === c.id);
          if (sIdx >= 0) {
            list[idx].shortlist[sIdx].stageChangedAt = ts;
            list[idx].shortlist[sIdx].addedAt = ts;
            list[idx].shortlist[sIdx].note = 'seeded — dormant silver';
            localStorage.setItem('credicrew:roles:v1', JSON.stringify(list));
          }
        }
      }
    } catch {
      /* swallow */
    }
    inserted += 1;
  }
  return inserted;
}

// ---------- page ----------

export default function Revive() {
  const [roles, setRoles] = useState<Role[]>([]);
  const [tick, setTick] = useState(0);
  const refresh = () => setTick(t => t + 1);

  const [minScore, setMinScore] = useState(REVIVE_COMPOSITE_FLOOR);
  const [hideStale, setHideStale] = useState(false);
  const [groupBy, setGroupBy] = useState<'candidate' | 'role'>('candidate');
  const [openAltsFor, setOpenAltsFor] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  useEffect(() => {
    setRoles(listRoles());
  }, [tick]);

  const summary = useMemo(() => analyzeRevive(roles, CANDIDATES), [roles]);

  // Filtered queue.
  const filteredOpps = useMemo(() => {
    return summary.opportunities.filter(o => {
      if (o.reactivationScore < minScore) return false;
      if (hideStale && o.stale) return false;
      return true;
    });
  }, [summary, minScore, hideStale]);

  // For the candidate-grouped view, collapse to one row per candidate (best fit),
  // showing the rest as "alternatives".
  const candidateGroups = useMemo(() => {
    const byCandidate = new Map<number, ReviveOpportunity[]>();
    for (const o of filteredOpps) {
      const list = byCandidate.get(o.candidateId) ?? [];
      list.push(o);
      byCandidate.set(o.candidateId, list);
    }
    const out: { primary: ReviveOpportunity; alternatives: ReviveOpportunity[] }[] = [];
    for (const list of byCandidate.values()) {
      list.sort((a, b) => b.reactivationScore - a.reactivationScore);
      out.push({ primary: list[0], alternatives: list.slice(1) });
    }
    out.sort((a, b) => b.primary.reactivationScore - a.primary.reactivationScore);
    return out;
  }, [filteredOpps]);

  // For the role-grouped view, re-run the per-role roll-up against the *filtered* opps.
  const filteredPerRole = useMemo(() => {
    const m = new Map<string, { name: string; picks: ReviveOpportunity[] }>();
    for (const r of summary.perRole) {
      m.set(r.roleId, { name: r.roleName, picks: [] });
    }
    for (const o of filteredOpps) {
      const row = m.get(o.toRoleId);
      if (row) row.picks.push(o);
    }
    const out: ReviveSummary['perRole'] = [];
    for (const [roleId, row] of m.entries()) {
      if (row.picks.length === 0) continue;
      out.push({
        roleId,
        roleName: row.name,
        picks: row.picks,
        bestScore: row.picks[0]?.reactivationScore ?? 0,
      });
    }
    out.sort((a, b) => b.bestScore - a.bestScore);
    return out;
  }, [summary, filteredOpps]);

  const band = liftBand(summary.revivableCount, summary.silver.length);

  function reactivate(
    candidateId: number,
    fromRoleId: string,
    toRoleId: string,
    toRoleName: string,
  ) {
    const fromRole = roles.find(r => r.id === fromRoleId);
    const candName =
      CANDIDATES.find(c => c.id === candidateId)?.name ?? `Candidate ${candidateId}`;

    addToShortlist(toRoleId, candidateId, 'new');
    setNote(
      toRoleId,
      candidateId,
      `Reactivated from ${fromRole?.name ?? 'previous role'} (silver medalist).`,
    );
    // Remove the passed entry from the original role so we don't keep
    // re-surfacing the same person.
    removeFromShortlist(fromRoleId, candidateId);
    setToast(`Reactivated ${candName} → ${toRoleName}`);
    setOpenAltsFor(null);
    refresh();
    setTimeout(() => setToast(null), 2400);
  }

  function handleSeed() {
    const n = seedSilverPool(roles, CANDIDATES);
    if (n > 0) {
      setToast(`Seeded ${n} silver medalists across your roles.`);
      refresh();
      setTimeout(() => setToast(null), 2400);
    } else {
      setToast('Could not seed — all candidates are already on a shortlist.');
      setTimeout(() => setToast(null), 2400);
    }
  }

  function copyBrief() {
    copyToClipboard(buildBrief(summary)).then(() => {
      setToast('Briefing copied to clipboard.');
      setTimeout(() => setToast(null), 1800);
    });
  }

  const hasRoles = roles.length > 0;
  const hasSilver = summary.silver.length > 0;

  return (
    <main className="min-h-screen bg-gradient-to-b from-[#0b0b12] to-black text-white">
      <style>{`
        .cc-rv-card { transition: transform 160ms ease, box-shadow 160ms ease; }
        .cc-rv-card:hover {
          transform: translateY(-1px);
          box-shadow: 0 12px 40px -16px var(--rv-accent, rgba(255,255,255,0.25));
          border-color: color-mix(in srgb, var(--rv-accent) 45%, rgba(255,255,255,0.1));
        }
      `}</style>

      <div className="mx-auto max-w-6xl px-4 pb-24">
        <HeaderNav />

        {/* Hero */}
        <section className="mt-2">
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div>
              <div className="text-[11px] uppercase tracking-wider text-rose-300/80">
                Silver Medalist Reactivation Engine
              </div>
              <h1 className="mt-1 text-3xl font-semibold md:text-4xl">
                Revive — work the pool you already paid for.
              </h1>
              <p className="mt-2 max-w-2xl text-sm text-white/60">
                Crosswind routes who&apos;s in your pipelines today. Revive looks at the {' '}
                <span className="text-rose-200">passed</span> pool and asks the question every recruiter dodges: would
                this candidate, who didn&apos;t fit one role, fit a different one? Half-life decay of {' '}
                <span className="tabular-nums text-white/80">{RECENCY_HALF_LIFE_DAYS}d</span> keeps the queue fresh;
                match floor {REVIVE_MATCH_FLOOR} keeps it honest.
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <button
                onClick={copyBrief}
                disabled={!hasSilver}
                className="rounded-md border border-white/10 bg-white/5 px-3 py-1.5 text-xs text-white/80 hover:bg-white/10 disabled:opacity-40"
              >
                📋 Copy briefing
              </button>
              {!hasSilver && hasRoles && (
                <button
                  onClick={handleSeed}
                  className="rounded-md border border-indigo-400/40 bg-indigo-500/15 px-3 py-1.5 text-xs text-indigo-200 hover:bg-indigo-500/25"
                  title="Drop a synthetic silver-medalist set into your roles so you can see Revive in action."
                >
                  ✨ Seed demo pool
                </button>
              )}
            </div>
          </div>

          {/* Stat strip */}
          <div className="mt-6 grid grid-cols-2 gap-3 md:grid-cols-4">
            <StatTile
              label="Silver pool"
              value={String(summary.silver.length)}
              sub={`across ${roles.length} role${roles.length === 1 ? '' : 's'}`}
              hue="#a78bfa"
            />
            <StatTile
              label="Revivable"
              value={String(summary.revivableCount)}
              sub={`composite ≥ ${REVIVE_COMPOSITE_FLOOR}`}
              hue={band.hex}
            />
            <StatTile
              label="Est. cost saved"
              value={formatUsd(summary.estimatedCostSavedUsd)}
              sub={`@ ${formatUsd(SOURCING_COST_PER_HIRE_USD)} / sourced hire`}
              hue="#34d399"
            />
            <StatTile
              label="Top pick"
              value={summary.topPick ? `${summary.topPick.reactivationScore}` : '—'}
              sub={summary.topPick ? summary.topPick.candidateName : 'queue is empty'}
              hue={summary.topPick ? TIER_HEX[tierFor(summary.topPick.reactivationScore)] : '#475569'}
            />
          </div>

          {hasSilver && (
            <div
              className="mt-3 rounded-lg border px-3 py-2 text-[12px]"
              style={{
                borderColor: `${band.hex}40`,
                background: `${band.hex}10`,
                color: band.hex,
              }}
            >
              <span className="font-medium">{band.label}.</span>{' '}
              <span className="text-white/70">{band.blurb}</span>
            </div>
          )}
        </section>

        {/* Filters */}
        {hasSilver && (
          <section className="mt-6 rounded-2xl border border-white/10 bg-white/5 p-3">
            <div className="flex flex-wrap items-center gap-3 text-sm">
              <div className="flex items-center gap-2">
                <span className="text-xs text-white/55">Min reactivation</span>
                <input
                  type="range"
                  min={0}
                  max={100}
                  value={minScore}
                  onChange={e => setMinScore(parseInt(e.target.value, 10))}
                  className="w-44 accent-rose-400"
                />
                <span className="w-8 text-right text-xs tabular-nums text-white/65">{minScore}</span>
              </div>
              <label className="flex items-center gap-2 text-xs text-white/65">
                <input
                  type="checkbox"
                  checked={hideStale}
                  onChange={e => setHideStale(e.target.checked)}
                  className="accent-rose-400"
                />
                Hide stale (&gt; {STALE_DAYS}d)
              </label>
              <div className="ml-auto inline-flex overflow-hidden rounded-md border border-white/10 bg-black/30 text-[11px]">
                <button
                  onClick={() => setGroupBy('candidate')}
                  className={`px-3 py-1.5 transition ${
                    groupBy === 'candidate'
                      ? 'bg-white/10 text-white'
                      : 'text-white/60 hover:bg-white/5'
                  }`}
                >
                  By candidate
                </button>
                <button
                  onClick={() => setGroupBy('role')}
                  className={`px-3 py-1.5 transition ${
                    groupBy === 'role'
                      ? 'bg-white/10 text-white'
                      : 'text-white/60 hover:bg-white/5'
                  }`}
                >
                  By open role
                </button>
              </div>
            </div>
          </section>
        )}

        {/* Main content */}
        {!hasRoles ? (
          <div className="mx-auto mt-16 max-w-2xl rounded-2xl border border-white/10 bg-white/5 p-8 text-center">
            <h2 className="text-xl font-semibold">Create a role first</h2>
            <p className="mt-2 text-sm text-white/60">
              Revive operates on the candidates sitting in your roles. Save a role from Discover and pass on a couple of
              candidates — they become your silver pool.
            </p>
            <div className="mt-4 flex items-center justify-center gap-2 text-xs">
              <Link
                href="/"
                className="rounded-md border border-indigo-400/40 bg-indigo-500/15 px-3 py-1.5 text-indigo-200 hover:bg-indigo-500/25"
              >
                Go to Discover
              </Link>
            </div>
          </div>
        ) : !hasSilver ? (
          <EmptyState />
        ) : (
          <section className="mt-6">
            {groupBy === 'candidate' ? (
              candidateGroups.length === 0 ? (
                <div className="rounded-2xl border border-white/10 bg-white/5 p-6 text-center text-sm text-white/55">
                  No opportunities at this threshold. Lower the slider or unhide stale entries.
                </div>
              ) : (
                <div className="grid gap-4">
                  {candidateGroups.map(group => {
                    const key = `${group.primary.candidateId}-${group.primary.fromRoleId}-${group.primary.toRoleId}`;
                    const altsOpen = openAltsFor === key;
                    return (
                      <OpportunityCard
                        key={key}
                        opp={group.primary}
                        onReactivate={reactivate}
                        alternativesCount={group.alternatives.length}
                        alternativesOpen={altsOpen}
                        onToggleAlternatives={() =>
                          setOpenAltsFor(altsOpen ? null : key)
                        }
                        alternatives={group.alternatives}
                      />
                    );
                  })}
                </div>
              )
            ) : filteredPerRole.length === 0 ? (
              <div className="rounded-2xl border border-white/10 bg-white/5 p-6 text-center text-sm text-white/55">
                No roles have a revivable silver match at this threshold.
              </div>
            ) : (
              <div className="grid gap-4 md:grid-cols-2">
                {filteredPerRole.map(row => (
                  <PerRoleCard key={row.roleId} row={row} onReactivate={reactivate} />
                ))}
              </div>
            )}
          </section>
        )}

        {/* Footnote */}
        {hasSilver && (
          <section className="mt-10 grid gap-3 rounded-2xl border border-white/5 bg-white/[0.03] p-4 text-[12px] text-white/55 md:grid-cols-2">
            <div>
              <div className="text-[10px] uppercase tracking-wider text-white/45">How reactivation is scored</div>
              <p className="mt-1">
                <span className="tabular-nums text-white/80">reactivation = match × (0.5 + 0.5 × recency)</span>
                {' '}where recency = 2<sup>−daysDormant / {RECENCY_HALF_LIFE_DAYS}</sup>. Match quality dominates;
                recency tilts the queue. Match floor: {REVIVE_MATCH_FLOOR}. Composite floor for &ldquo;revivable&rdquo;:{' '}
                {REVIVE_COMPOSITE_FLOOR}.
              </p>
            </div>
            <div>
              <div className="text-[10px] uppercase tracking-wider text-white/45">What clicking Reactivate does</div>
              <p className="mt-1">
                Adds the candidate to the new role&apos;s shortlist as <span className="text-sky-200">new</span> with a
                provenance note (&ldquo;Reactivated from <em>original role</em>&rdquo;) and removes them from the original
                role&apos;s passed bucket so the queue doesn&apos;t re-surface the same person.
              </p>
            </div>
          </section>
        )}

        {toast && (
          <div className="pointer-events-none fixed inset-x-0 bottom-6 z-40 flex justify-center">
            <div className="pointer-events-auto rounded-full border border-emerald-400/40 bg-emerald-500/15 px-4 py-2 text-sm text-emerald-100 shadow-xl backdrop-blur">
              {toast}
            </div>
          </div>
        )}
      </div>
    </main>
  );
}
