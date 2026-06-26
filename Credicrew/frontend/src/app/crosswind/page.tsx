'use client';

import { useEffect, useMemo, useState, type CSSProperties } from 'react';
import Link from 'next/link';

import { candidates as CANDIDATES } from '@/data/candidates';
import {
  analyzeCrosswind,
  BAND_HUE,
  BAND_LABEL,
  CELL_HEX,
  cellTier,
  liftBand,
  recommendationLines,
  STRONG_FLOOR,
  MAGNET_ROLES,
  MISPLACE_THRESHOLD,
  TRANSPLANT_FLOOR,
  type CrosswindSummary,
  type RoutingMove,
} from '@/lib/crosswind';
import {
  addToShortlist,
  listRoles,
  STATUS_LABEL,
  STATUS_TONE,
  type PipelineStatus,
  type Role,
} from '@/lib/roles';

// ---------- small UI helpers ----------

const TONE_RING: Record<string, string> = {
  rose: 'border-rose-400/30 bg-rose-400/10 text-rose-200',
  amber: 'border-amber-400/30 bg-amber-400/10 text-amber-200',
  sky: 'border-sky-400/30 bg-sky-400/10 text-sky-200',
  indigo: 'border-indigo-400/30 bg-indigo-400/10 text-indigo-200',
  emerald: 'border-emerald-400/30 bg-emerald-400/10 text-emerald-200',
  violet: 'border-violet-400/30 bg-violet-400/10 text-violet-200',
  orange: 'border-orange-400/30 bg-orange-400/10 text-orange-200',
  slate: 'border-white/15 bg-white/5 text-white/65',
};

const STAGE_HEX: Record<PipelineStatus, string> = {
  new: '#38bdf8',
  outreach: '#818cf8',
  screening: '#a78bfa',
  interview: '#facc15',
  offer: '#34d399',
  passed: '#fb7185',
};

function liftHue(band: ReturnType<typeof liftBand>): string {
  return BAND_HUE[band];
}

function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map(w => w[0]?.toUpperCase() ?? '')
    .join('');
}

function shortName(name: string, max = 14): string {
  if (name.length <= max) return name;
  // Try first + last initial.
  const parts = name.split(/\s+/);
  if (parts.length >= 2) {
    const candidate = `${parts[0]} ${parts[parts.length - 1][0]}.`;
    if (candidate.length <= max) return candidate;
    return `${parts[0].slice(0, max - 2)}…`;
  }
  return `${name.slice(0, max - 1)}…`;
}

function roleLabel(name: string, max = 18): string {
  if (name.length <= max) return name;
  return `${name.slice(0, max - 1)}…`;
}

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

// ---------- atoms ----------

function LiftRing({ summary, size = 168 }: { summary: CrosswindSummary; size?: number }) {
  // Percent rendered: lift as a fraction of the theoretical max (100 pts/move).
  const theoreticalMax = Math.max(1, summary.candidateCount * 25);
  const pct = Math.min(100, Math.round((summary.liftTotal / theoreticalMax) * 100));
  const band = liftBand(summary.liftTotal, summary.moves.length);
  const hue = liftHue(band);
  return (
    <div
      className="cc-xw-ring relative grid place-items-center rounded-full"
      style={{
        width: size,
        height: size,
        background: `conic-gradient(${hue} ${pct}%, rgba(255,255,255,0.06) 0)`,
        ['--xw-accent' as keyof CSSProperties]: hue,
      } as CSSProperties}
    >
      <div className="absolute rounded-full bg-[#0b0b12]" style={{ inset: 6 }} />
      <div className="relative flex flex-col items-center leading-none">
        <span className="text-[11px] uppercase tracking-wider text-white/55">Portfolio lift</span>
        <span className="mt-1 text-4xl font-semibold tabular-nums" style={{ color: hue }}>
          {summary.liftTotal > 0 ? `+${summary.liftTotal}` : '0'}
        </span>
        <span className="mt-1 text-[10px] uppercase tracking-wider text-white/40">
          {BAND_LABEL[band]} · {summary.moves.length} move{summary.moves.length === 1 ? '' : 's'}
        </span>
      </div>
    </div>
  );
}

function MetricTile({
  label,
  value,
  sub,
  tone = 'slate',
}: {
  label: string;
  value: string | number;
  sub?: string;
  tone?: keyof typeof TONE_RING;
}) {
  return (
    <div className={`cc-xw-tile rounded-xl border px-4 py-3 ${TONE_RING[tone]}`}>
      <div className="text-[10px] uppercase tracking-wider opacity-75">{label}</div>
      <div className="mt-1 text-2xl font-semibold tabular-nums">{value}</div>
      {sub && <div className="mt-1 text-xs opacity-70">{sub}</div>}
    </div>
  );
}

function Avatar({ name, score, status }: { name: string; score?: number; status?: PipelineStatus }) {
  const hue = score !== undefined ? CELL_HEX[cellTier(score)] : '#a78bfa';
  return (
    <div className="relative inline-flex shrink-0">
      <span
        className="grid h-9 w-9 place-items-center rounded-full border text-xs font-bold text-white"
        style={{
          background: `linear-gradient(135deg, ${hue}, ${hue}88)`,
          borderColor: `${hue}aa`,
        }}
      >
        {initials(name)}
      </span>
      {status && (
        <span
          className="absolute -bottom-0.5 -right-0.5 grid h-3.5 w-3.5 place-items-center rounded-full border-2 border-[#0b0b12]"
          style={{ background: STAGE_HEX[status] }}
          title={STATUS_LABEL[status]}
        />
      )}
    </div>
  );
}

function StagePill({ status }: { status: PipelineStatus }) {
  const tone = STATUS_TONE[status];
  return (
    <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-wider ${TONE_RING[tone]}`}>
      <span
        className="inline-block h-1.5 w-1.5 rounded-full"
        style={{ background: STAGE_HEX[status] }}
      />
      {STATUS_LABEL[status]}
    </span>
  );
}

// ---------- match matrix ----------

function MatchMatrix({
  summary,
  onPick,
}: {
  summary: CrosswindSummary;
  onPick: (candidateId: number, roleId: string) => void;
}) {
  // Rows = unique candidates (sorted by best-fit role score descending).
  // Cols = roles in perRole order (kept stable across renders so the same
  // role always appears in the same column).
  const cellsByCandidate = useMemo(() => {
    const m = new Map<number, typeof summary.cells>();
    for (const c of summary.cells) {
      const arr = m.get(c.candidateId) ?? [];
      arr.push(c);
      m.set(c.candidateId, arr);
    }
    return m;
  }, [summary.cells]);

  const rows = useMemo(() => {
    const ids = Array.from(cellsByCandidate.keys());
    const name = (id: number) => cellsByCandidate.get(id)?.[0]?.candidateName ?? '?';
    const best = (id: number) =>
      Math.max(...(cellsByCandidate.get(id) ?? []).map(c => c.score));
    return ids.sort((a, b) => best(b) - best(a) || name(a).localeCompare(name(b)));
  }, [cellsByCandidate]);

  const cols = summary.perRole;

  if (rows.length === 0 || cols.length === 0) {
    return (
      <div className="rounded-xl border border-white/10 bg-white/[0.02] p-6 text-center text-sm text-white/60">
        No active candidates × roles to plot. Add candidates to at least two roles&apos; shortlists, then come back.
      </div>
    );
  }

  return (
    <div className="cc-xw-matrix overflow-x-auto rounded-2xl border border-white/10 bg-white/[0.02]">
      <table className="min-w-full table-fixed border-separate border-spacing-0">
        <thead>
          <tr>
            <th className="sticky left-0 z-10 w-44 border-b border-white/5 bg-[#0b0b12]/95 px-3 py-2 text-left text-[10px] font-medium uppercase tracking-wider text-white/55 backdrop-blur">
              Candidate
            </th>
            {cols.map(c => (
              <th
                key={c.roleId}
                className={`border-b border-white/5 px-2 py-2 text-center text-[10px] font-medium uppercase tracking-wider ${
                  c.isTarget ? 'text-emerald-300' : c.isSource ? 'text-rose-300' : 'text-white/55'
                }`}
                style={{ minWidth: 88 }}
                title={c.roleName}
              >
                <div className="flex flex-col items-center gap-0.5">
                  <span>{roleLabel(c.roleName)}</span>
                  <span className="font-mono text-[9px] opacity-50">best {c.best}</span>
                </div>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map(candidateId => {
            const cells = cellsByCandidate.get(candidateId) ?? [];
            const byRoleId = new Map(cells.map(c => [c.roleId, c]));
            const firstHome = cells.find(c => c.isHome);
            const name = firstHome?.candidateName ?? '?';
            const status = firstHome?.status;
            return (
              <tr key={candidateId} className="cc-xw-row">
                <td className="sticky left-0 z-10 border-b border-white/5 bg-[#0b0b12]/95 px-3 py-2 backdrop-blur">
                  <div className="flex items-center gap-2">
                    <Avatar name={name} score={firstHome?.score} status={status} />
                    <div className="min-w-0">
                      <div className="truncate text-xs font-medium text-white/85" title={name}>
                        {shortName(name, 18)}
                      </div>
                      {firstHome && (
                        <div className="truncate text-[10px] text-white/45" title={firstHome.roleName}>
                          {roleLabel(firstHome.roleName, 18)}
                        </div>
                      )}
                    </div>
                  </div>
                </td>
                {cols.map(col => {
                  const cell = byRoleId.get(col.roleId);
                  if (!cell) return <td key={col.roleId} />;
                  const tier = cellTier(cell.score);
                  const hex = CELL_HEX[tier];
                  const alpha = 0.08 + (cell.score / 100) * 0.6;
                  const isStrong = cell.score >= STRONG_FLOOR;
                  // Compute lift relative to home for highlighting alternative columns.
                  const home = cells.find(c => c.isHome);
                  const lift = home && !cell.isHome ? cell.score - home.score : 0;
                  return (
                    <td key={col.roleId} className="border-b border-white/5 p-1">
                      <button
                        type="button"
                        onClick={() => onPick(cell.candidateId, cell.roleId)}
                        className={`cc-xw-cell relative grid w-full place-items-center rounded-md border text-xs font-medium ${
                          cell.isHome ? 'ring-2 ring-white/40' : 'ring-0'
                        }`}
                        style={{
                          background: `${hex}${Math.round(alpha * 255).toString(16).padStart(2, '0')}`,
                          borderColor: `${hex}55`,
                          color: isStrong ? '#0b0b12' : 'white',
                          minHeight: 36,
                        }}
                        title={`${cell.candidateName} → ${cell.roleName}: ${cell.score}${cell.isHome ? ' (home)' : ''}${
                          lift > 0 ? ` · +${lift} vs home` : lift < 0 ? ` · ${lift} vs home` : ''
                        }`}
                      >
                        <span className="tabular-nums">{cell.score}</span>
                        {!cell.isHome && lift >= MISPLACE_THRESHOLD && (
                          <span
                            className="absolute -right-0.5 -top-0.5 grid h-3.5 w-3.5 place-items-center rounded-full bg-emerald-400 text-[8px] font-bold text-[#0b0b12]"
                            title={`Better fit: +${lift}`}
                          >
                            ↑
                          </span>
                        )}
                      </button>
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ---------- routing-flow sankey ----------

function RoutingFlow({ summary }: { summary: CrosswindSummary }) {
  if (summary.moves.length === 0) {
    return (
      <div className="rounded-xl border border-white/10 bg-white/[0.02] p-5 text-center text-sm text-white/60">
        No routing moves currently recommended.
      </div>
    );
  }
  const sources = new Map<string, number>();
  const sinks = new Map<string, number>();
  for (const m of summary.moves) {
    sources.set(m.fromRoleName, (sources.get(m.fromRoleName) ?? 0) + 1);
    sinks.set(m.toRoleName, (sinks.get(m.toRoleName) ?? 0) + 1);
  }
  const left = Array.from(sources.entries()).sort((a, b) => b[1] - a[1]);
  const right = Array.from(sinks.entries()).sort((a, b) => b[1] - a[1]);

  // Build a stable y-position per node so we can draw paths.
  const W = 720;
  const H = Math.max(220, 60 + Math.max(left.length, right.length) * 44);
  const leftX = 16;
  const rightX = W - 16 - 200;
  const nodeW = 200;
  const nodeH = 32;
  const gap = 12;
  const startY = 36;
  const leftPos = new Map<string, { y: number; cy: number }>();
  left.forEach(([name], i) => {
    const y = startY + i * (nodeH + gap);
    leftPos.set(name, { y, cy: y + nodeH / 2 });
  });
  const rightPos = new Map<string, { y: number; cy: number }>();
  right.forEach(([name], i) => {
    const y = startY + i * (nodeH + gap);
    rightPos.set(name, { y, cy: y + nodeH / 2 });
  });

  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.02] p-4">
      <div className="mb-3 flex items-center justify-between">
        <div>
          <div className="text-sm font-semibold text-white/85">Routing flow</div>
          <div className="text-[11px] text-white/45">Where misplaced candidates would go if we routed optimally.</div>
        </div>
        <div className="flex items-center gap-3 text-[10px] uppercase tracking-wider text-white/55">
          <span className="flex items-center gap-1"><span className="inline-block h-2 w-2 rounded-full bg-rose-300" /> source</span>
          <span className="flex items-center gap-1"><span className="inline-block h-2 w-2 rounded-full bg-emerald-300" /> target</span>
        </div>
      </div>
      <svg width="100%" viewBox={`0 0 ${W} ${H}`} className="overflow-visible">
        <defs>
          <linearGradient id="xw-flow" x1="0%" x2="100%">
            <stop offset="0%" stopColor="#fb7185" stopOpacity="0.55" />
            <stop offset="100%" stopColor="#34d399" stopOpacity="0.55" />
          </linearGradient>
        </defs>
        {summary.moves.map(m => {
          const a = leftPos.get(m.fromRoleName);
          const b = rightPos.get(m.toRoleName);
          if (!a || !b) return null;
          const x1 = leftX + nodeW;
          const x2 = rightX;
          const mx1 = x1 + (x2 - x1) * 0.4;
          const mx2 = x1 + (x2 - x1) * 0.6;
          return (
            <path
              key={`${m.candidateId}-${m.toRoleId}`}
              d={`M ${x1} ${a.cy} C ${mx1} ${a.cy}, ${mx2} ${b.cy}, ${x2} ${b.cy}`}
              stroke="url(#xw-flow)"
              strokeWidth={Math.max(1.5, m.delta / 6)}
              fill="none"
              opacity={0.85}
            />
          );
        })}
        {left.map(([name, count]) => {
          const p = leftPos.get(name)!;
          return (
            <g key={`l-${name}`}>
              <rect
                x={leftX}
                y={p.y}
                width={nodeW}
                height={nodeH}
                rx={6}
                fill="#fb71851a"
                stroke="#fb718566"
              />
              <text x={leftX + 10} y={p.cy + 4} fontSize="12" fill="#fda4af" className="font-medium">
                {roleLabel(name, 18)}
              </text>
              <text x={leftX + nodeW - 10} y={p.cy + 4} fontSize="11" fill="#fb7185" textAnchor="end" className="tabular-nums">
                −{count}
              </text>
            </g>
          );
        })}
        {right.map(([name, count]) => {
          const p = rightPos.get(name)!;
          return (
            <g key={`r-${name}`}>
              <rect
                x={rightX}
                y={p.y}
                width={nodeW}
                height={nodeH}
                rx={6}
                fill="#34d3991a"
                stroke="#34d39966"
              />
              <text x={rightX + 10} y={p.cy + 4} fontSize="12" fill="#a7f3d0" className="font-medium">
                {roleLabel(name, 18)}
              </text>
              <text x={rightX + nodeW - 10} y={p.cy + 4} fontSize="11" fill="#34d399" textAnchor="end" className="tabular-nums">
                +{count}
              </text>
            </g>
          );
        })}
      </svg>
      <div className="mt-2 text-[10px] uppercase tracking-wider text-white/40">
        Edge thickness ∝ score gain. {summary.moves.length} moves · −{left.length} source role{left.length === 1 ? '' : 's'} · +{right.length} target role{right.length === 1 ? '' : 's'}.
      </div>
    </div>
  );
}

// ---------- score histogram ----------

function ScoreHistogram({ buckets }: { buckets: number[] }) {
  const max = Math.max(...buckets, 1);
  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.02] p-4">
      <div className="mb-3">
        <div className="text-sm font-semibold text-white/85">Match-score distribution</div>
        <div className="text-[11px] text-white/45">Across every (candidate × role) cell — where your portfolio fits and where it doesn&apos;t.</div>
      </div>
      <div className="flex h-32 items-end gap-2">
        {buckets.map((count, i) => {
          const lo = i * 10;
          const hi = lo + 9;
          const tier = cellTier(lo + 5);
          const hex = CELL_HEX[tier];
          const h = max ? (count / max) * 100 : 0;
          return (
            <div key={i} className="flex flex-1 flex-col items-center gap-1">
              <div className="text-[10px] tabular-nums text-white/55">{count || ''}</div>
              <div
                className="w-full rounded-t-md transition-all duration-300"
                style={{
                  height: `${h}%`,
                  minHeight: count > 0 ? 4 : 0,
                  background: `linear-gradient(180deg, ${hex}, ${hex}55)`,
                  border: `1px solid ${hex}66`,
                }}
                title={`${lo}–${hi}: ${count} cells`}
              />
              <div className="text-[9px] tabular-nums text-white/40">{lo}</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ---------- main page ----------

export default function CrosswindPage() {
  const [roles, setRoles] = useState<Role[]>([]);
  const [, setReloadKey] = useState(0);
  const [applied, setApplied] = useState<Set<string>>(new Set());
  const [showAllMoves, setShowAllMoves] = useState(false);
  const [showExplain, setShowExplain] = useState(false);

  useEffect(() => {
    setRoles(listRoles());
  }, []);

  const summary = useMemo(() => analyzeCrosswind(roles, CANDIDATES), [roles]);

  const recs = useMemo(() => recommendationLines(summary), [summary]);
  const band = liftBand(summary.liftTotal, summary.moves.length);

  function applyMove(m: RoutingMove) {
    const key = `${m.candidateId}->${m.toRoleId}`;
    addToShortlist(m.toRoleId, m.candidateId, 'new');
    setApplied(prev => new Set(prev).add(key));
    setRoles(listRoles());
    setReloadKey(k => k + 1);
  }

  function buildBrief(): string {
    const lines: string[] = [];
    lines.push(`# Crosswind — ${new Date(summary.generatedAt).toLocaleDateString()}`);
    lines.push('');
    lines.push(`**Portfolio lift:** +${summary.liftTotal} pts across ${summary.moves.length} routing move${summary.moves.length === 1 ? '' : 's'}.`);
    lines.push(`**Active candidates:** ${summary.candidateCount} across ${summary.roleCount} roles.`);
    lines.push('');
    lines.push('## Routing moves');
    if (summary.moves.length === 0) lines.push('_None._');
    else {
      for (const m of summary.moves) {
        lines.push(`- ${m.candidateName}: ${m.fromRoleName} (${m.fromScore}) → ${m.toRoleName} (${m.toScore}) **+${m.delta}** — ${m.why.join('; ')}`);
      }
    }
    lines.push('');
    lines.push(`## Talent magnets (≥ ${MAGNET_ROLES} roles at ≥${STRONG_FLOOR})`);
    if (summary.magnets.length === 0) lines.push('_None._');
    else {
      for (const t of summary.magnets) {
        lines.push(`- **${t.candidateName}** — ${t.hits.length} roles: ${t.hits.map(h => `${h.roleName}(${h.score})`).join(', ')}`);
      }
    }
    lines.push('');
    lines.push('## Lonely roles');
    if (summary.lonely.length === 0) lines.push('_None._');
    else {
      for (const l of summary.lonely) {
        lines.push(`- **${l.roleName}** (best own ${l.ownBest}) — top transplant: ${l.transplants[0].candidateName} from ${l.transplants[0].fromRoleName} at ${l.transplants[0].score}`);
      }
    }
    return lines.join('\n');
  }

  const accent = liftHue(band);

  return (
    <div className="relative isolate min-h-screen text-white">
      <div
        className="pointer-events-none absolute inset-x-0 top-0 -z-10 h-72 opacity-60"
        style={{
          background: `radial-gradient(620px 220px at 80% 0%, ${accent}22, transparent 60%), radial-gradient(420px 180px at -10% 130%, rgba(56,189,248,0.06), transparent 60%)`,
        }}
      />

      <div className="mx-auto max-w-6xl px-4 py-8">
        {/* Header */}
        <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
          <div>
            <div className="flex items-center gap-2 text-[11px] uppercase tracking-wider text-white/55">
              <span
                className="inline-block h-2 w-2 rounded-full"
                style={{ background: accent, boxShadow: `0 0 8px ${accent}` }}
              />
              Cross-role candidate router
            </div>
            <h1 className="mt-1 text-3xl font-semibold">Crosswind</h1>
            <p className="mt-1 max-w-2xl text-sm text-white/60">
              Most of Credicrew is role-scoped. Crosswind asks the portfolio-level
              question: is every candidate already in the role that fits them best?
              The same match engine that drives Discover scores every active
              candidate against every open role, then surfaces the moves that lift
              the total fit-quality of your pipeline.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={() => copyToClipboard(buildBrief())}
              className="rounded-lg border border-white/15 bg-white/5 px-3 py-1.5 text-xs text-white/80 hover:bg-white/10"
            >
              Copy brief
            </button>
            <button
              type="button"
              onClick={() => downloadText('crosswind-brief.md', buildBrief())}
              className="rounded-lg border border-white/15 bg-white/5 px-3 py-1.5 text-xs text-white/80 hover:bg-white/10"
            >
              Download .md
            </button>
            <Link
              href="/hq"
              className="rounded-lg border border-white/15 bg-white/5 px-3 py-1.5 text-xs text-white/80 hover:bg-white/10"
            >
              ← Command Center
            </Link>
          </div>
        </div>

        {/* Hero */}
        <section
          className="cc-xw-hero mb-6 grid grid-cols-1 gap-4 rounded-2xl border border-white/10 bg-white/[0.03] p-5 md:grid-cols-[auto_minmax(0,1fr)_minmax(0,1fr)]"
          style={{ ['--xw-accent' as keyof CSSProperties]: accent } as CSSProperties}
        >
          <div className="grid place-items-center">
            <LiftRing summary={summary} />
          </div>
          <div className="grid grid-cols-2 content-center gap-2 sm:grid-cols-2">
            <MetricTile
              label="Active candidates"
              value={summary.candidateCount}
              sub={`${summary.cellCount} (candidate × role) cells`}
              tone="sky"
            />
            <MetricTile
              label="Open roles"
              value={summary.roleCount}
              sub={`${summary.perRole.filter(r => r.isTarget).length} would gain · ${summary.perRole.filter(r => r.isSource).length} would lose`}
              tone="indigo"
            />
            <MetricTile
              label="Routing moves"
              value={summary.moves.length}
              sub={summary.moves[0] ? `top +${summary.moves[0].delta} pts` : '—'}
              tone={summary.moves.length ? 'violet' : 'slate'}
            />
            <MetricTile
              label="Avg lift / move"
              value={summary.liftAvgPerMove ? `+${summary.liftAvgPerMove}` : '—'}
              sub={`Threshold ≥ ${MISPLACE_THRESHOLD} pts`}
              tone={band === 'urgent' ? 'rose' : band === 'meaningful' ? 'violet' : 'slate'}
            />
          </div>
          <div className="grid content-center gap-2">
            <MetricTile
              label="Talent magnets"
              value={summary.magnets.length}
              sub={summary.magnets[0] ? `${summary.magnets[0].candidateName} · ${summary.magnets[0].hits.length} roles` : 'None yet'}
              tone={summary.magnets.length ? 'emerald' : 'slate'}
            />
            <MetricTile
              label="Lonely roles"
              value={summary.lonely.length}
              sub={summary.lonely[0] ? `${summary.lonely[0].roleName} (best ${summary.lonely[0].ownBest})` : 'None — every role has a strong match'}
              tone={summary.lonely.length ? 'amber' : 'slate'}
            />
          </div>
        </section>

        {/* Recommendations strip */}
        {recs.length > 0 && (
          <section className="mb-6 rounded-2xl border border-violet-400/25 bg-violet-400/[0.06] p-5">
            <div className="mb-1 text-[10px] uppercase tracking-wider text-violet-200/75">Today&apos;s routing brief</div>
            <ul className="space-y-1.5 text-sm text-white/85">
              {recs.map((line, i) => (
                <li key={i} className="leading-relaxed">
                  <RichText text={line} />
                </li>
              ))}
            </ul>
          </section>
        )}

        {/* Match Matrix — centerpiece */}
        <section className="mb-6">
          <div className="mb-3 flex items-end justify-between">
            <div>
              <h2 className="text-lg font-semibold text-white/90">Match matrix</h2>
              <p className="text-xs text-white/50">
                Every active candidate × every open role. White ring = candidate&apos;s
                current home. <span className="inline-grid h-3.5 w-3.5 -mb-0.5 place-items-center rounded-full bg-emerald-400 text-[7px] font-bold text-[#0b0b12]">↑</span> = +{MISPLACE_THRESHOLD}+ pts better than home. Click any cell to add the candidate to that role.
              </p>
            </div>
            <div className="flex items-center gap-3 text-[10px] uppercase tracking-wider text-white/55">
              <span className="flex items-center gap-1.5">
                <span className="h-3 w-6 rounded-sm" style={{ background: CELL_HEX.emerald }} /> ≥{STRONG_FLOOR}
              </span>
              <span className="flex items-center gap-1.5">
                <span className="h-3 w-6 rounded-sm" style={{ background: CELL_HEX.sky }} /> 70–79
              </span>
              <span className="flex items-center gap-1.5">
                <span className="h-3 w-6 rounded-sm" style={{ background: CELL_HEX.amber }} /> 55–69
              </span>
              <span className="flex items-center gap-1.5">
                <span className="h-3 w-6 rounded-sm" style={{ background: CELL_HEX.rose }} /> 35–54
              </span>
              <span className="flex items-center gap-1.5">
                <span className="h-3 w-6 rounded-sm" style={{ background: CELL_HEX.slate }} /> &lt;35
              </span>
            </div>
          </div>
          <MatchMatrix
            summary={summary}
            onPick={(candidateId, roleId) => {
              const cell = summary.cells.find(c => c.candidateId === candidateId && c.roleId === roleId);
              if (!cell || cell.isHome || cell.isOnShortlist) return;
              const move: RoutingMove = {
                candidateId: cell.candidateId,
                candidateName: cell.candidateName,
                fromRoleId: '',
                fromRoleName: '',
                fromScore: 0,
                toRoleId: cell.roleId,
                toRoleName: cell.roleName,
                toScore: cell.score,
                delta: 0,
                why: [],
              };
              applyMove(move);
            }}
          />
        </section>

        {/* Routing moves + Sankey */}
        <section className="mb-6 grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
          <div className="rounded-2xl border border-white/10 bg-white/[0.02] p-4">
            <div className="mb-3 flex items-end justify-between">
              <div>
                <h2 className="text-base font-semibold text-white/90">Recommended moves</h2>
                <p className="text-xs text-white/50">
                  Sorted by score lift. Apply to add the candidate to the target
                  role&apos;s shortlist (status: new).
                </p>
              </div>
              {summary.moves.length > 4 && (
                <button
                  type="button"
                  onClick={() => setShowAllMoves(v => !v)}
                  className="text-[11px] uppercase tracking-wider text-violet-300 hover:text-violet-200"
                >
                  {showAllMoves ? 'Show top 4' : `Show all ${summary.moves.length}`}
                </button>
              )}
            </div>
            {summary.moves.length === 0 ? (
              <div className="rounded-xl border border-white/10 bg-white/[0.02] p-6 text-center text-sm text-white/55">
                Every active candidate is already in their best-fit role. Nothing to reroute.
              </div>
            ) : (
              <ul className="space-y-2">
                {(showAllMoves ? summary.moves : summary.moves.slice(0, 4)).map(m => {
                  const key = `${m.candidateId}->${m.toRoleId}`;
                  const isApplied = applied.has(key);
                  return (
                    <li
                      key={key}
                      className="cc-xw-move flex items-start gap-3 rounded-xl border border-white/10 bg-white/[0.03] p-3"
                    >
                      <Avatar name={m.candidateName} score={m.toScore} status={m.status} />
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-baseline gap-x-2 text-sm">
                          <span className="font-medium text-white/90">{m.candidateName}</span>
                          {m.status && <StagePill status={m.status} />}
                        </div>
                        <div className="mt-1 flex items-center gap-2 text-xs text-white/55">
                          <span className="rounded border border-rose-300/30 bg-rose-400/10 px-1.5 py-0.5 text-rose-200">
                            {m.fromRoleName} · {m.fromScore}
                          </span>
                          <span className="text-white/30">→</span>
                          <span className="rounded border border-emerald-300/30 bg-emerald-400/10 px-1.5 py-0.5 text-emerald-200">
                            {m.toRoleName} · {m.toScore}
                          </span>
                          <span
                            className="rounded-full px-2 py-0.5 text-[10px] font-bold tabular-nums"
                            style={{ background: `${accent}22`, color: accent }}
                          >
                            +{m.delta}
                          </span>
                        </div>
                        <ul className="mt-1.5 space-y-0.5 text-[11px] text-white/55">
                          {m.why.map((line, i) => (
                            <li key={i}>· {line}</li>
                          ))}
                        </ul>
                      </div>
                      <button
                        type="button"
                        onClick={() => applyMove(m)}
                        disabled={isApplied}
                        className={`shrink-0 rounded-lg border px-3 py-1.5 text-xs font-medium ${
                          isApplied
                            ? 'cursor-default border-emerald-300/30 bg-emerald-400/10 text-emerald-200'
                            : 'border-violet-300/30 bg-violet-400/10 text-violet-100 hover:bg-violet-400/20'
                        }`}
                      >
                        {isApplied ? '✓ Routed' : 'Route →'}
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
          <RoutingFlow summary={summary} />
        </section>

        {/* Talent magnets + Lonely roles */}
        <section className="mb-6 grid grid-cols-1 gap-4 lg:grid-cols-2">
          <div className="rounded-2xl border border-white/10 bg-white/[0.02] p-4">
            <div className="mb-3">
              <h2 className="text-base font-semibold text-white/90">Talent magnets</h2>
              <p className="text-xs text-white/50">
                Candidates with strong fit (≥{STRONG_FLOOR}) across ≥{MAGNET_ROLES} roles. Make sure
                these don&apos;t fall off — they&apos;re portfolio-level scarce.
              </p>
            </div>
            {summary.magnets.length === 0 ? (
              <div className="rounded-xl border border-white/10 bg-white/[0.02] p-5 text-center text-xs text-white/55">
                No magnets yet. Add more candidates whose skills span ≥{MAGNET_ROLES} of your open roles.
              </div>
            ) : (
              <ul className="space-y-2">
                {summary.magnets.slice(0, 5).map(m => (
                  <li key={m.candidateId} className="rounded-xl border border-emerald-300/20 bg-emerald-400/[0.04] p-3">
                    <div className="flex items-center gap-2">
                      <Avatar name={m.candidateName} score={m.topScore} />
                      <div className="min-w-0 flex-1">
                        <div className="flex items-baseline gap-2 text-sm">
                          <span className="font-medium text-white/90">{m.candidateName}</span>
                          <span className="text-[11px] text-white/55">
                            home: {m.homeRoleName ?? '—'}
                          </span>
                        </div>
                        <div className="mt-0.5 text-[11px] text-emerald-200/75">
                          Strong in {m.hits.length} roles · top {m.topScore}
                        </div>
                      </div>
                    </div>
                    <div className="mt-2 flex flex-wrap gap-1">
                      {m.hits.map(h => (
                        <span
                          key={h.roleId}
                          className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] ${
                            h.isHome ? TONE_RING.violet : TONE_RING.emerald
                          }`}
                        >
                          {h.isHome ? '★ ' : ''}{roleLabel(h.roleName, 16)} · {h.score}
                        </span>
                      ))}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <div className="rounded-2xl border border-white/10 bg-white/[0.02] p-4">
            <div className="mb-3">
              <h2 className="text-base font-semibold text-white/90">Lonely roles</h2>
              <p className="text-xs text-white/50">
                Roles whose own shortlist has no strong match. Transplant candidates
                from another role who&apos;d score ≥ {TRANSPLANT_FLOOR} here.
              </p>
            </div>
            {summary.lonely.length === 0 ? (
              <div className="rounded-xl border border-white/10 bg-white/[0.02] p-5 text-center text-xs text-white/55">
                Every role has at least one strong own match. Nothing to transplant.
              </div>
            ) : (
              <ul className="space-y-2">
                {summary.lonely.slice(0, 5).map(l => (
                  <li key={l.roleId} className="rounded-xl border border-amber-300/20 bg-amber-400/[0.04] p-3">
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <div className="text-sm font-medium text-white/90">{l.roleName}</div>
                        <div className="text-[11px] text-amber-200/70">
                          Own best {l.ownBest} · median {l.ownMedian} · {l.candidateCount} candidates
                        </div>
                      </div>
                      <Link
                        href={`/roles/${l.roleId}`}
                        className="text-[11px] uppercase tracking-wider text-amber-200/80 hover:text-amber-100"
                      >
                        Open →
                      </Link>
                    </div>
                    <div className="mt-2 space-y-1">
                      {l.transplants.slice(0, 3).map(t => (
                        <div
                          key={`${l.roleId}-${t.candidateId}`}
                          className="flex items-center justify-between gap-2 rounded-md border border-white/10 bg-white/[0.03] px-2 py-1.5"
                        >
                          <div className="flex items-center gap-2">
                            <Avatar name={t.candidateName} score={t.score} status={t.status} />
                            <div className="text-xs">
                              <div className="text-white/85">{t.candidateName}</div>
                              <div className="text-[10px] text-white/50">from {t.fromRoleName}</div>
                            </div>
                          </div>
                          <div className="text-right">
                            <div className="text-sm font-semibold tabular-nums text-emerald-300">
                              {t.score}
                            </div>
                            <div className="text-[10px] tabular-nums text-white/50">
                              {t.delta >= 0 ? '+' : ''}{t.delta} vs home
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </section>

        {/* Histogram */}
        <section className="mb-6">
          <ScoreHistogram buckets={summary.scoreHistogram} />
        </section>

        {/* Explainer */}
        <section className="rounded-2xl border border-white/10 bg-white/[0.02]">
          <button
            type="button"
            onClick={() => setShowExplain(v => !v)}
            className="flex w-full items-center justify-between px-4 py-3 text-left text-sm font-medium text-white/85"
          >
            How Crosswind reasons
            <span className="text-white/45">{showExplain ? '−' : '+'}</span>
          </button>
          {showExplain && (
            <div className="space-y-3 border-t border-white/10 px-4 py-4 text-xs leading-relaxed text-white/65">
              <p>
                For every <em>active</em> candidate (status ≠ passed/offer) and every
                open role, we run <code className="rounded bg-white/10 px-1">matchCandidate(role.plan, candidate)</code>
                — the same engine the Discover page uses, weighted skills 0.55 · location
                0.15 · seniority 0.20 · base 0.10.
              </p>
              <ul className="list-disc space-y-1.5 pl-5">
                <li>
                  <strong className="text-white/85">Routing move</strong> — candidate&apos;s current home
                  role is <em>not</em> their best-scoring role, and the delta ≥ {MISPLACE_THRESHOLD} pts.
                  Sorted by delta (largest first). Applying a move adds the candidate to the
                  target role&apos;s shortlist as <code className="rounded bg-white/10 px-1">new</code>.
                </li>
                <li>
                  <strong className="text-white/85">Talent magnet</strong> — score ≥ {STRONG_FLOOR}
                  in ≥ {MAGNET_ROLES} distinct roles. These candidates have unusual cross-role
                  reach, and losing them costs you N reqs, not 1.
                </li>
                <li>
                  <strong className="text-white/85">Lonely role</strong> — own shortlist has no
                  match ≥ {STRONG_FLOOR}, but a candidate from another pool scores ≥ {TRANSPLANT_FLOOR} here
                  <em> and</em> the move doesn&apos;t hurt their own home fit by more than 5 pts.
                </li>
                <li>
                  <strong className="text-white/85">Portfolio lift</strong> — Σ
                  (best_alternative_score − current_score) over all active candidates, expressed
                  as a +N total and split as moves × avg/move. The conic ring is normalised to
                  a notional max of 25 pts per candidate.
                </li>
                <li>
                  <strong className="text-white/85">Frozen statuses</strong> — passed and offer
                  are excluded from routing. You don&apos;t reroute a reject, and you don&apos;t poach a
                  candidate who&apos;s already on an offer letter.
                </li>
              </ul>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

// ---------- text formatting ----------

function RichText({ text }: { text: string }) {
  // Tiny **bold** parser so the recs strip can highlight numerics.
  const parts: { bold: boolean; v: string }[] = [];
  let i = 0;
  while (i < text.length) {
    const open = text.indexOf('**', i);
    if (open < 0) {
      parts.push({ bold: false, v: text.slice(i) });
      break;
    }
    if (open > i) parts.push({ bold: false, v: text.slice(i, open) });
    const close = text.indexOf('**', open + 2);
    if (close < 0) {
      parts.push({ bold: false, v: text.slice(open) });
      break;
    }
    parts.push({ bold: true, v: text.slice(open + 2, close) });
    i = close + 2;
  }
  return (
    <>
      {parts.map((p, idx) =>
        p.bold ? (
          <strong key={idx} className="text-white">{p.v}</strong>
        ) : (
          <span key={idx}>{p.v}</span>
        ),
      )}
    </>
  );
}
