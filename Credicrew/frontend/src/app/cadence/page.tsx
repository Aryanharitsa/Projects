'use client';

import { useEffect, useMemo, useState, type CSSProperties } from 'react';
import Link from 'next/link';

import {
  analyzeCadence,
  buildCadenceBrief,
  BAND_HUE,
  BAND_LABEL,
  CADENCE_BANDS,
  ACTIVE_STAGES,
  STAGE_SLA_DAYS,
  STAGE_MEDIAN_DAYS,
  stageLabel,
  type CadenceBand,
  type CadenceItem,
  type CadenceSummary,
  type StageRollup,
} from '@/lib/cadence';
import { listRoles, type Role, type PipelineStatus, STATUS_TONE } from '@/lib/roles';
import {
  gatherCadenceInput,
  nudgeStage,
  clearAllOverrides,
} from '@/data/cadence_seed';

// ---------- helpers ----------

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

function healthHue(score: number): string {
  if (score >= 80) return '#34d399'; // emerald
  if (score >= 60) return '#facc15'; // amber
  if (score >= 40) return '#fb923c'; // orange
  return '#fb7185';                  // rose
}

function healthBand(score: number): string {
  if (score >= 80) return 'Healthy';
  if (score >= 60) return 'Watch';
  if (score >= 40) return 'Strained';
  return 'Critical';
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

function HealthRing({ score, size = 156 }: { score: number; size?: number }) {
  const pct = Math.max(0, Math.min(100, score));
  const hue = healthHue(score);
  return (
    <div
      className="cc-cad-ring relative grid place-items-center rounded-full"
      style={{
        width: size,
        height: size,
        background: `conic-gradient(${hue} ${pct}%, rgba(255,255,255,0.06) 0)`,
        ['--cad-accent' as keyof CSSProperties]: hue,
      } as CSSProperties}
    >
      <div className="absolute rounded-full bg-[#0b0b12]" style={{ inset: 6 }} />
      <div className="relative flex flex-col items-center leading-none">
        <span className="text-4xl font-semibold tabular-nums" style={{ color: hue }}>
          {Math.round(score)}
        </span>
        <span className="mt-1 text-[10px] uppercase tracking-wider text-white/55">
          {healthBand(score)}
        </span>
      </div>
    </div>
  );
}

function Tile({ label, value, detail, tone = 'slate' }: {
  label: string; value: string; detail?: string; tone?: string;
}) {
  return (
    <div className={`cc-cad-tile rounded-xl border p-3 ${TONE_RING[tone] ?? TONE_RING.slate}`}>
      <div className="text-[10px] uppercase tracking-wider opacity-70">{label}</div>
      <div className="mt-1 truncate text-xl font-semibold tabular-nums">{value}</div>
      {detail && <div className="mt-0.5 truncate text-[11px] opacity-65">{detail}</div>}
    </div>
  );
}

function BandStack({ bands, total }: {
  bands: Record<CadenceBand, number>; total: number;
}) {
  if (total === 0) {
    return <div className="h-2 w-full rounded-full bg-white/5" />;
  }
  return (
    <div className="flex h-2 w-full overflow-hidden rounded-full bg-white/5">
      {CADENCE_BANDS.map(b => {
        const w = (bands[b] / total) * 100;
        if (w === 0) return null;
        return (
          <div
            key={b}
            className="cc-cad-bar h-full"
            style={{ width: `${w}%`, background: BAND_HUE[b] }}
            title={`${BAND_LABEL[b]}: ${bands[b]}`}
          />
        );
      })}
    </div>
  );
}

function AgeBar({ age, sla, median }: { age: number; sla: number; median: number }) {
  // Visual scale: 0 → 0%, 1.6 SLA → 100% (matches at_risk boundary).
  const max = Math.max(sla * 1.6, age + 1);
  const pct = Math.min(100, (age / max) * 100);
  const slaPct = (sla / max) * 100;
  const medianPct = (median / max) * 100;
  const hue = healthHue(
    age <= sla * 0.7 ? 90 : age <= sla ? 70 : age <= sla * 1.6 ? 50 : 25,
  );
  return (
    <div className="relative h-1.5 w-full overflow-visible rounded-full bg-white/5">
      <div
        className="cc-cad-bar h-full rounded-full"
        style={{ width: `${pct}%`, background: hue }}
      />
      <div
        className="absolute top-[-3px] h-3 w-px bg-white/55"
        style={{ left: `${slaPct}%` }}
        title={`SLA ${sla}d`}
      />
      <div
        className="absolute top-[-2px] h-2 w-px bg-white/25"
        style={{ left: `${medianPct}%` }}
        title={`Median ${median}d`}
      />
    </div>
  );
}

function StageCard({ rollup }: { rollup: StageRollup }) {
  const hue = STAGE_HEX[rollup.stage];
  const pastSla = rollup.bands.at_risk + rollup.bands.stalled;
  return (
    <div
      className={`cc-cad-stage relative rounded-xl border border-white/10 bg-white/[0.03] p-4 ${rollup.bottleneck ? 'bottleneck' : ''}`}
      style={{ ['--cad-accent' as keyof CSSProperties]: hue } as CSSProperties}
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span
            className="inline-block h-2.5 w-2.5 rounded-full"
            style={{ background: hue }}
          />
          <h3 className="text-sm font-semibold">{stageLabel(rollup.stage)}</h3>
          {rollup.bottleneck && (
            <span className="cc-cad-pulse rounded-full border border-rose-400/40 bg-rose-400/10 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wider text-rose-200">
              Bottleneck
            </span>
          )}
        </div>
        <div className="flex items-center gap-2 text-[11px] text-white/55">
          <span className="tabular-nums">{rollup.count}</span>
          <span className="text-white/30">•</span>
          <span className="tabular-nums" style={{ color: healthHue(rollup.health) }}>
            {rollup.health}/100
          </span>
        </div>
      </div>

      {rollup.count > 0 ? (
        <>
          <div className="mt-3 grid grid-cols-3 gap-2 text-[11px]">
            <div className="rounded-md border border-white/5 bg-white/[0.02] p-2">
              <div className="text-[9px] uppercase tracking-wider text-white/45">Median age</div>
              <div className="mt-0.5 tabular-nums">{rollup.ageMedian}d</div>
              <div className="text-[10px] text-white/45">SLA {rollup.slaDays}d</div>
            </div>
            <div className="rounded-md border border-white/5 bg-white/[0.02] p-2">
              <div className="text-[9px] uppercase tracking-wider text-white/45">P75 age</div>
              <div className="mt-0.5 tabular-nums">{rollup.ageP75}d</div>
              <div className="text-[10px] text-white/45">Median {rollup.medianDays}d</div>
            </div>
            <div className="rounded-md border border-white/5 bg-white/[0.02] p-2">
              <div className="text-[9px] uppercase tracking-wider text-white/45">Exits / 7d</div>
              <div className="mt-0.5 tabular-nums">{rollup.expectedExits7d.toFixed(1)}</div>
              <div className="text-[10px] text-white/45">{pastSla} past SLA</div>
            </div>
          </div>

          <div className="mt-3">
            <BandStack bands={rollup.bands} total={rollup.count} />
            <div className="mt-1.5 flex flex-wrap items-center gap-2 text-[10px] text-white/55">
              {CADENCE_BANDS.map(b => (
                <span key={b} className="inline-flex items-center gap-1">
                  <span className="h-2 w-2 rounded-full" style={{ background: BAND_HUE[b] }} />
                  {BAND_LABEL[b]}
                  <span className="tabular-nums text-white/40">·{rollup.bands[b]}</span>
                </span>
              ))}
            </div>
          </div>
        </>
      ) : (
        <div className="mt-3 grid place-items-center rounded-md border border-dashed border-white/10 py-5 text-[11px] text-white/40">
          No candidates in this stage
        </div>
      )}
    </div>
  );
}

function HotRow({ item, onNudge }: {
  item: CadenceItem;
  onNudge: (key: string) => void;
}) {
  const key = `${item.roleId}|${item.candidateId}`;
  const hue = BAND_HUE[item.band];
  const stageTone = STATUS_TONE[item.stage] ?? 'slate';
  return (
    <div
      className="cc-cad-row grid grid-cols-12 items-center gap-3 rounded-xl border border-white/10 bg-white/[0.03] p-3"
      style={{ borderLeft: `3px solid ${hue}` }}
    >
      <div className="col-span-3 min-w-0">
        <div className="flex items-center gap-2">
          <span
            className="grid h-7 w-7 place-items-center rounded-full text-[10px] font-bold text-white"
            style={{ background: `linear-gradient(135deg, ${hue}, color-mix(in srgb, ${hue} 50%, #fff 0%))` }}
          >
            {item.candidateName.slice(0, 1).toUpperCase()}
          </span>
          <div className="min-w-0">
            <div className="truncate text-sm font-medium">{item.candidateName}</div>
            <div className="truncate text-[10px] text-white/45">{item.location ?? '—'}</div>
          </div>
        </div>
      </div>
      <div className="col-span-2 min-w-0">
        <Link
          href={`/roles/${item.roleId}`}
          className="block truncate text-[12px] text-white/70 hover:text-white"
          title={item.roleName}
        >
          {item.roleName}
        </Link>
      </div>
      <div className="col-span-1">
        <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] ${TONE_RING[stageTone] ?? TONE_RING.slate}`}>
          {stageLabel(item.stage)}
        </span>
      </div>
      <div className="col-span-2">
        <div className="flex items-center justify-between text-[10px] text-white/55">
          <span className="tabular-nums">{item.stageAgeDays}d</span>
          <span>SLA {item.slaDays}d</span>
        </div>
        <AgeBar
          age={item.stageAgeDays}
          sla={item.slaDays}
          median={STAGE_MEDIAN_DAYS[item.stage] ?? 5}
        />
      </div>
      <div className="col-span-1">
        <span
          className="rounded-md border px-2 py-0.5 text-[10px] font-medium"
          style={{
            borderColor: `${hue}55`,
            background: `${hue}1a`,
            color: hue,
          }}
        >
          {item.riskScore}
        </span>
      </div>
      <div className="col-span-2 truncate text-[11px] text-white/65" title={item.recommendation}>
        {item.recommendation}
      </div>
      <div className="col-span-1 flex justify-end">
        <button
          onClick={() => onNudge(key)}
          className="rounded-md border border-emerald-400/30 bg-emerald-400/10 px-2 py-1 text-[10px] text-emerald-200 hover:bg-emerald-400/20"
          title="Reset stage timer to now"
        >
          ✓ Nudged
        </button>
      </div>
    </div>
  );
}

function RoleHealthCard({ role, summary }: {
  role: { roleId: string; roleName: string; count: number; health: number; bands: Record<CadenceBand, number>; topStalled: CadenceItem[] };
  summary: CadenceSummary;
}) {
  const hue = healthHue(role.health);
  void summary;
  return (
    <Link
      href={`/roles/${role.roleId}`}
      className="cc-cad-stage block rounded-xl border border-white/10 bg-white/[0.03] p-4"
      style={{ ['--cad-accent' as keyof CSSProperties]: hue } as CSSProperties}
    >
      <div className="flex items-start justify-between">
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold text-white">{role.roleName}</div>
          <div className="text-[10px] text-white/50">{role.count} active</div>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="text-base font-semibold tabular-nums" style={{ color: hue }}>
            {role.health}
          </span>
          <span className="text-[10px] text-white/40">/100</span>
        </div>
      </div>
      <div className="mt-3">
        <BandStack bands={role.bands} total={role.count} />
      </div>
      <div className="mt-3 grid grid-cols-4 gap-1.5 text-[10px]">
        {CADENCE_BANDS.map(b => (
          <div key={b} className="rounded-md border border-white/5 bg-white/[0.02] p-1.5">
            <div className="flex items-center gap-1">
              <span className="h-1.5 w-1.5 rounded-full" style={{ background: BAND_HUE[b] }} />
              <span className="text-white/50">{BAND_LABEL[b]}</span>
            </div>
            <div className="mt-0.5 text-right tabular-nums">{role.bands[b]}</div>
          </div>
        ))}
      </div>
      {role.topStalled.length > 0 && (
        <div className="mt-3 border-t border-white/5 pt-2">
          <div className="text-[9px] uppercase tracking-wider text-white/45">Top stalled</div>
          <ul className="mt-1 space-y-0.5">
            {role.topStalled.map(c => (
              <li key={`${c.roleId}|${c.candidateId}`} className="flex items-center justify-between gap-2 text-[11px] text-white/70">
                <span className="truncate">{c.candidateName}</span>
                <span className="tabular-nums text-white/40">{c.stageAgeDays}d</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </Link>
  );
}

// Stage × age heatmap — rows: stage, cols: SLA bucket (≤0.7, 0.7-1, 1-1.6, >1.6)
function StageHeatmap({ items }: { items: CadenceItem[] }) {
  const buckets: { label: string; band: CadenceBand }[] = [
    { label: '≤ 0.7×SLA', band: 'on_track' },
    { label: '0.7–1×',   band: 'slowing' },
    { label: '1–1.6×',   band: 'at_risk' },
    { label: '> 1.6×',   band: 'stalled' },
  ];
  const grid: Record<PipelineStatus, Record<CadenceBand, number>> = {
    new: { on_track: 0, slowing: 0, at_risk: 0, stalled: 0 },
    outreach: { on_track: 0, slowing: 0, at_risk: 0, stalled: 0 },
    screening: { on_track: 0, slowing: 0, at_risk: 0, stalled: 0 },
    interview: { on_track: 0, slowing: 0, at_risk: 0, stalled: 0 },
    offer: { on_track: 0, slowing: 0, at_risk: 0, stalled: 0 },
    passed: { on_track: 0, slowing: 0, at_risk: 0, stalled: 0 },
  };
  for (const it of items) {
    if (!ACTIVE_STAGES.includes(it.stage)) continue;
    grid[it.stage][it.band] += 1;
  }
  let max = 1;
  for (const s of ACTIVE_STAGES) for (const b of CADENCE_BANDS) if (grid[s][b] > max) max = grid[s][b];

  return (
    <div className="overflow-hidden rounded-xl border border-white/10 bg-white/[0.02] p-4">
      <div className="mb-3 flex items-center justify-between">
        <div className="text-sm font-semibold text-white">Stage × age heatmap</div>
        <div className="text-[10px] text-white/45">Rows = stage · Cols = age vs SLA</div>
      </div>
      <table className="w-full table-fixed text-[12px]">
        <thead>
          <tr>
            <th className="px-2 py-1.5 text-left text-[10px] uppercase tracking-wider text-white/45">Stage</th>
            {buckets.map(b => (
              <th key={b.band} className="px-2 py-1.5 text-center text-[10px] uppercase tracking-wider text-white/45">
                <span className="inline-flex items-center gap-1">
                  <span className="h-1.5 w-1.5 rounded-full" style={{ background: BAND_HUE[b.band] }} />
                  {b.label}
                </span>
              </th>
            ))}
            <th className="px-2 py-1.5 text-right text-[10px] uppercase tracking-wider text-white/45">Total</th>
          </tr>
        </thead>
        <tbody>
          {ACTIVE_STAGES.map(s => {
            const total = CADENCE_BANDS.reduce((a, b) => a + grid[s][b], 0);
            return (
              <tr key={s} className="border-t border-white/5">
                <td className="px-2 py-1.5">
                  <span className="inline-flex items-center gap-2">
                    <span className="h-2 w-2 rounded-full" style={{ background: STAGE_HEX[s] }} />
                    {stageLabel(s)}
                  </span>
                </td>
                {buckets.map(b => {
                  const v = grid[s][b.band];
                  const intensity = v === 0 ? 0 : 0.1 + 0.6 * (v / max);
                  return (
                    <td key={b.band} className="px-2 py-1.5 text-center">
                      <div
                        className="cc-cad-heat-cell mx-auto inline-flex h-8 w-12 items-center justify-center rounded-md text-[12px] tabular-nums"
                        style={{
                          background: v === 0 ? 'rgba(255,255,255,0.025)' : `color-mix(in srgb, ${BAND_HUE[b.band]} ${(intensity * 100).toFixed(0)}%, transparent)`,
                          color: v === 0 ? 'rgba(255,255,255,0.35)' : '#fff',
                          border: `1px solid ${v === 0 ? 'rgba(255,255,255,0.06)' : `${BAND_HUE[b.band]}55`}`,
                        }}
                      >
                        {v}
                      </div>
                    </td>
                  );
                })}
                <td className="px-2 py-1.5 text-right tabular-nums text-white/65">{total}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function ForecastStrip({ byStage }: { byStage: StageRollup[] }) {
  const active = byStage.filter(s => s.count > 0);
  if (active.length === 0) return null;
  const total = active.reduce((a, s) => a + s.expectedExits7d, 0);
  return (
    <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4">
      <div className="mb-3 flex items-center justify-between">
        <div>
          <div className="text-sm font-semibold text-white">7-day exit forecast</div>
          <div className="text-[10px] text-white/45">Memoryless exponential hazard · λ = ln 2 / median</div>
        </div>
        <div className="text-right">
          <div className="text-2xl font-semibold tabular-nums text-white">{total.toFixed(1)}</div>
          <div className="text-[10px] text-white/45">expected exits this week</div>
        </div>
      </div>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-5">
        {active.map(s => {
          const hue = STAGE_HEX[s.stage];
          const pct = s.count > 0 ? (s.expectedExits7d / s.count) * 100 : 0;
          return (
            <div key={s.stage} className="rounded-lg border border-white/5 bg-white/[0.02] p-2.5">
              <div className="flex items-center justify-between">
                <span className="inline-flex items-center gap-1.5 text-[11px] text-white/75">
                  <span className="h-2 w-2 rounded-full" style={{ background: hue }} />
                  {stageLabel(s.stage)}
                </span>
                <span className="text-[10px] text-white/45 tabular-nums">{Math.round(pct)}%</span>
              </div>
              <div className="mt-1 flex items-baseline justify-between">
                <span className="text-lg font-semibold tabular-nums" style={{ color: hue }}>
                  {s.expectedExits7d.toFixed(1)}
                </span>
                <span className="text-[10px] text-white/45 tabular-nums">/ {s.count}</span>
              </div>
              <div className="mt-1 h-1 overflow-hidden rounded-full bg-white/5">
                <div className="h-full" style={{ width: `${Math.min(100, pct)}%`, background: hue }} />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function Recommendations({ recs }: { recs: string[] }) {
  if (recs.length === 0) return null;
  return (
    <div className="cc-cad-recs rounded-xl border border-white/10 bg-white/[0.02] p-4">
      <div className="mb-2 flex items-center gap-2">
        <span className="text-sm font-semibold text-white">This week&apos;s moves</span>
        <span className="rounded-full border border-violet-400/30 bg-violet-400/10 px-2 py-0.5 text-[9px] uppercase tracking-wider text-violet-200">
          Cadence
        </span>
      </div>
      <ul className="space-y-1.5">
        {recs.map((r, i) => (
          <li key={i} className="flex gap-2 text-[13px] text-white/85">
            <span className="text-violet-300">▸</span>
            <span dangerouslySetInnerHTML={{ __html: r.replace(/\*\*(.+?)\*\*/g, '<strong class="text-white">$1</strong>') }} />
          </li>
        ))}
      </ul>
    </div>
  );
}

// ---------- main ----------

export default function CadenceStudio() {
  const [roles, setRoles] = useState<Role[]>([]);
  const [ready, setReady] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const [copied, setCopied] = useState(false);
  const [showAll, setShowAll] = useState(false);
  const [stageFilter, setStageFilter] = useState<PipelineStatus | 'all'>('all');
  const [bandFilter, setBandFilter] = useState<CadenceBand | 'all'>('all');

  useEffect(() => {
    setRoles(listRoles());
    setReady(true);
  }, []);

  const summary: CadenceSummary = useMemo(() => {
    void refresh;
    const input = gatherCadenceInput(roles);
    return analyzeCadence({ candidates: input });
  }, [roles, refresh]);

  const filteredItems = useMemo(() => {
    return summary.items.filter(i =>
      (stageFilter === 'all' || i.stage === stageFilter) &&
      (bandFilter === 'all' || i.band === bandFilter),
    );
  }, [summary, stageFilter, bandFilter]);

  function handleNudge(key: string) {
    const [roleId, candIdStr] = key.split('|');
    const candId = Number(candIdStr);
    const role = roles.find(r => r.id === roleId);
    const entry = role?.shortlist.find(e => e.candidateId === candId);
    if (!entry) return;
    nudgeStage(roleId, candId, entry.status);
    setRefresh(x => x + 1);
  }

  function handleReset() {
    clearAllOverrides();
    setRefresh(x => x + 1);
  }

  async function handleCopy() {
    const md = buildCadenceBrief(summary);
    await copyToClipboard(md);
    setCopied(true);
    setTimeout(() => setCopied(false), 1400);
  }

  function handleDownload() {
    const dt = new Date().toISOString().slice(0, 10);
    downloadText(`cadence-${dt}.md`, buildCadenceBrief(summary));
  }

  if (!ready) {
    return (
      <main className="min-h-screen bg-gradient-to-b from-[#0b0b12] to-black text-white">
        <div className="mx-auto max-w-6xl px-4 py-10">
          <div className="rounded-xl border border-white/10 bg-white/[0.02] p-6 text-white/60">
            Loading cadence…
          </div>
        </div>
      </main>
    );
  }

  if (summary.totalActive === 0) {
    return (
      <main className="min-h-screen bg-gradient-to-b from-[#0b0b12] to-black text-white">
        <div className="mx-auto max-w-6xl px-4 py-10">
          <h1 className="text-3xl font-semibold">Cadence Studio</h1>
          <p className="mt-2 text-white/60">
            Pipeline velocity per candidate. Add candidates to a role&apos;s
            shortlist to see who&apos;s drifting past SLA.
          </p>
          <div className="mt-6 rounded-xl border border-dashed border-white/10 bg-white/[0.02] p-10 text-center">
            <p className="text-white/55">No active candidates yet.</p>
            <Link href="/" className="mt-3 inline-block rounded-lg border border-violet-400/30 bg-violet-400/10 px-4 py-2 text-sm text-violet-100 hover:bg-violet-400/20">
              Discover candidates →
            </Link>
          </div>
        </div>
      </main>
    );
  }

  const heroHue = healthHue(summary.healthScore);

  return (
    <main className="min-h-screen bg-gradient-to-b from-[#0b0b12] to-black text-white">
      <div className="mx-auto max-w-6xl space-y-6 px-4 py-8">
        {/* ---- title row ---- */}
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="bg-gradient-to-r from-rose-200 via-amber-200 to-emerald-200 bg-clip-text text-3xl font-semibold text-transparent">
              Cadence Studio
            </h1>
            <p className="mt-1 text-sm text-white/55">
              Per-candidate pipeline velocity, stage SLAs and a 7-day exit forecast.
              Forecast Studio answers <em>will I hire by start date</em>; Cadence answers
              <em> who&apos;s about to fall off this week</em>.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              onClick={handleCopy}
              className="rounded-lg border border-violet-400/30 bg-violet-400/10 px-3 py-1.5 text-xs text-violet-100 hover:bg-violet-400/20"
            >
              {copied ? 'Copied!' : 'Copy brief'}
            </button>
            <button
              onClick={handleDownload}
              className="rounded-lg border border-sky-400/30 bg-sky-400/10 px-3 py-1.5 text-xs text-sky-100 hover:bg-sky-400/20"
            >
              Download .md
            </button>
            <button
              onClick={handleReset}
              className="rounded-lg border border-white/10 bg-white/5 px-3 py-1.5 text-xs text-white/70 hover:bg-white/10"
              title="Clear all stage-timer overrides"
            >
              Reset timers
            </button>
          </div>
        </div>

        {/* ---- hero ---- */}
        <section
          className="cc-cad-hero rounded-2xl border border-white/10 bg-white/[0.025] p-5"
          style={{ ['--cad-accent' as keyof CSSProperties]: heroHue } as CSSProperties}
        >
          <div className="grid grid-cols-1 items-center gap-5 md:grid-cols-[160px_1fr_auto]">
            <HealthRing score={summary.healthScore} />
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              <Tile
                label="Active"
                value={summary.totalActive.toString()}
                detail={`across ${summary.byRole.length} ${summary.byRole.length === 1 ? 'role' : 'roles'}`}
                tone="sky"
              />
              <Tile
                label="On track"
                value={summary.onTrackCount.toString()}
                detail={`${Math.round((summary.onTrackCount / Math.max(1, summary.totalActive)) * 100)}% inside SLA`}
                tone="emerald"
              />
              <Tile
                label="At risk"
                value={summary.atRiskCount.toString()}
                detail="past SLA, < 1.6×"
                tone="orange"
              />
              <Tile
                label="Stalled"
                value={summary.stalledCount.toString()}
                detail="> 1.6× SLA"
                tone="rose"
              />
            </div>
            <div className="flex flex-col items-end gap-2 text-right">
              <div className="rounded-xl border border-white/10 bg-white/5 px-4 py-3">
                <div className="text-[10px] uppercase tracking-wider text-white/55">Projected exits</div>
                <div className="mt-1 text-3xl font-semibold tabular-nums text-white">
                  {summary.expectedExits7d.toFixed(1)}
                </div>
                <div className="text-[10px] text-white/45">in the next 7 days</div>
              </div>
              {summary.worstStage && (
                <div className="text-[11px] text-white/55">
                  Worst stage:{' '}
                  <span className="font-semibold text-white">{stageLabel(summary.worstStage)}</span>
                </div>
              )}
            </div>
          </div>
        </section>

        {/* ---- recommendations ---- */}
        <Recommendations recs={summary.recommendations} />

        {/* ---- stage swim lanes ---- */}
        <section>
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-white">Pipeline stages</h2>
            <div className="text-[10px] text-white/45">SLA priors mirrored from Forecast Studio</div>
          </div>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-5">
            {summary.byStage.map(s => (
              <StageCard key={s.stage} rollup={s} />
            ))}
          </div>
        </section>

        {/* ---- forecast strip ---- */}
        <ForecastStrip byStage={summary.byStage} />

        {/* ---- hot list ---- */}
        <section>
          <div className="mb-3 flex items-center justify-between">
            <div>
              <h2 className="text-sm font-semibold text-white">Today&apos;s hot list</h2>
              <p className="text-[11px] text-white/50">Top candidates by risk score · click ✓ Nudged after you reach out</p>
            </div>
            <div className="text-[10px] text-white/45">{summary.hotList.length} flagged</div>
          </div>
          <div className="grid gap-2">
            {summary.hotList.length === 0 ? (
              <div className="rounded-xl border border-dashed border-emerald-400/20 bg-emerald-400/5 p-4 text-center text-[12px] text-emerald-100">
                Pipeline is clean — nothing at risk this week.
              </div>
            ) : (
              summary.hotList.map(item => (
                <HotRow
                  key={`${item.roleId}|${item.candidateId}`}
                  item={item}
                  onNudge={handleNudge}
                />
              ))
            )}
          </div>
        </section>

        {/* ---- per-role grid ---- */}
        {summary.byRole.length > 0 && (
          <section>
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-sm font-semibold text-white">By role</h2>
              <div className="text-[10px] text-white/45">Sorted by health · ascending (worst first)</div>
            </div>
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
              {summary.byRole.map(r => (
                <RoleHealthCard key={r.roleId} role={r} summary={summary} />
              ))}
            </div>
          </section>
        )}

        {/* ---- heatmap ---- */}
        <StageHeatmap items={summary.items} />

        {/* ---- full list (collapsible) ---- */}
        <section>
          <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
            <div className="flex items-end gap-3">
              <h2 className="text-sm font-semibold text-white">All active candidates</h2>
              <span className="text-[11px] text-white/45">{filteredItems.length} / {summary.totalActive}</span>
            </div>
            <div className="flex items-center gap-2">
              <select
                value={stageFilter}
                onChange={e => setStageFilter(e.target.value as PipelineStatus | 'all')}
                className="rounded-md border border-white/10 bg-white/5 px-2 py-1 text-[11px] text-white/80"
              >
                <option value="all">All stages</option>
                {ACTIVE_STAGES.map(s => (
                  <option key={s} value={s}>{stageLabel(s)}</option>
                ))}
              </select>
              <select
                value={bandFilter}
                onChange={e => setBandFilter(e.target.value as CadenceBand | 'all')}
                className="rounded-md border border-white/10 bg-white/5 px-2 py-1 text-[11px] text-white/80"
              >
                <option value="all">All bands</option>
                {CADENCE_BANDS.map(b => (
                  <option key={b} value={b}>{BAND_LABEL[b]}</option>
                ))}
              </select>
              <button
                onClick={() => setShowAll(x => !x)}
                className="rounded-md border border-white/10 bg-white/5 px-2 py-1 text-[11px] text-white/80 hover:bg-white/10"
              >
                {showAll ? 'Collapse' : 'Expand'}
              </button>
            </div>
          </div>
          {showAll && (
            <div className="grid gap-2">
              {filteredItems
                .sort((a, b) => b.riskScore - a.riskScore)
                .map(item => (
                  <HotRow
                    key={`all|${item.roleId}|${item.candidateId}`}
                    item={item}
                    onNudge={handleNudge}
                  />
                ))}
              {filteredItems.length === 0 && (
                <div className="rounded-xl border border-dashed border-white/10 bg-white/[0.02] p-4 text-center text-[12px] text-white/50">
                  No candidates match these filters.
                </div>
              )}
            </div>
          )}
        </section>

        {/* ---- footer explainer ---- */}
        <details className="rounded-xl border border-white/10 bg-white/[0.02] p-4 text-[12px] text-white/70">
          <summary className="cursor-pointer text-sm font-semibold text-white">How cadence is computed</summary>
          <div className="mt-3 space-y-2">
            <p>
              For every shortlist entry, the engine computes a <em>stage age</em>
              (days since the candidate entered the current stage) and grades it
              against per-stage SLA priors. The bands are:
            </p>
            <ul className="ml-4 list-disc space-y-1 text-white/65">
              <li><strong className="text-emerald-200">On track</strong>: age ≤ 0.7× SLA</li>
              <li><strong className="text-amber-200">Slowing</strong>: 0.7×–1.0× SLA — approaching the line</li>
              <li><strong className="text-orange-200">At risk</strong>: 1.0×–1.6× SLA — needs a nudge today</li>
              <li><strong className="text-rose-200">Stalled</strong>: &gt; 1.6× SLA — close the loop or drop</li>
            </ul>
            <p>
              <code className="rounded bg-white/5 px-1.5 py-0.5">survive_7d = exp(−7·ln 2 / median)</code>{' '}
              gives a per-candidate probability of still sitting in the same stage
              next week (memoryless exponential hazard). Summed across a stage
              that&apos;s the projected weekly exit count.
            </p>
            <p>
              <code className="rounded bg-white/5 px-1.5 py-0.5">risk = 0.6 · overdue + 0.4 · staleness</code>{' '}
              prioritises the hot list. Stage SLAs and medians:
            </p>
            <div className="overflow-x-auto">
              <table className="w-full text-[11px] text-white/65">
                <thead>
                  <tr className="text-white/45">
                    <th className="px-2 py-1 text-left">Stage</th>
                    {ACTIVE_STAGES.map(s => (
                      <th key={s} className="px-2 py-1 text-right">{stageLabel(s)}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td className="px-2 py-1">SLA (days)</td>
                    {ACTIVE_STAGES.map(s => <td key={s} className="px-2 py-1 text-right tabular-nums">{STAGE_SLA_DAYS[s]}</td>)}
                  </tr>
                  <tr>
                    <td className="px-2 py-1">Median (days)</td>
                    {ACTIVE_STAGES.map(s => <td key={s} className="px-2 py-1 text-right tabular-nums">{STAGE_MEDIAN_DAYS[s]}</td>)}
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </details>
      </div>
    </main>
  );
}
