'use client';

import { useEffect, useMemo, useState, type CSSProperties } from 'react';
import Link from 'next/link';

import { candidates } from '@/data/candidates';
import { matchCandidate } from '@/lib/match';
import {
  listRoles,
  STATUS_LABEL,
  STATUS_TONE,
  type Role,
} from '@/lib/roles';
import {
  getInterview,
  summarise,
} from '@/lib/interview';
import {
  benchmarkComp,
  getOffer,
  winProbability,
} from '@/lib/offer';
import {
  analyzeSources,
  BAND_HUE,
  BAND_LABEL,
  BAND_TONE,
  buildSourceBrief,
  CHANNELS,
  CHANNEL_BLURB,
  CHANNEL_LABEL,
  DEFAULT_COST_PER_CANDIDATE,
  type Channel,
  type ChannelMetrics,
  type SourceCandidate,
  type SourceInput,
  type SourceSummary,
} from '@/lib/sources';
import {
  getSourceFor,
  readChannelCosts,
  resetChannelCosts,
  setSourceChannel,
  writeChannelCost,
} from '@/data/sources_seed';

// ---------- helpers ----------

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

function fmtRupees(k: number | null): string {
  if (k === null) return '—';
  if (k >= 1000) return `₹${(k / 1000).toFixed(1)}M`;
  return `₹${Math.round(k)}k`;
}

// ---------- gather input from every role's shortlist ----------

function gatherInput(roles: Role[], overrideRefreshKey: number): SourceInput {
  void overrideRefreshKey; // refresh trigger; consumed by getSourceFor reads
  const all: SourceCandidate[] = [];
  for (const role of roles) {
    for (const entry of role.shortlist) {
      const c = candidates.find(x => x.id === entry.candidateId);
      const fallback = { id: entry.candidateId, name: `Candidate #${entry.candidateId}` };
      const cand = c ?? fallback;
      const match = matchCandidate(role.plan, cand);

      const ir = getInterview(role.id, entry.candidateId);
      let composite: number | null = null;
      let confidence = 0;
      if (ir) {
        const s = summarise(ir);
        confidence = s.totalCount > 0 ? s.ratedCount / s.totalCount : 0;
        composite = s.ratedCount > 0 ? s.composite : null;
      }

      const draft = getOffer(role.id, entry.candidateId);
      let winProb: number | undefined;
      if (draft) {
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

      all.push({
        candidateId: entry.candidateId,
        name: cand.name ?? `Candidate #${entry.candidateId}`,
        roleId: role.id,
        roleName: role.name,
        status: entry.status,
        addedAt: entry.addedAt,
        matchScore: match.score,
        composite,
        confidence,
        source: getSourceFor(entry.candidateId),
        winProbability: winProb,
        hasOffer: !!draft,
        location: c?.location,
      });
    }
  }
  return { candidates: all, costOverrides: readChannelCosts() };
}

// ---------- UI atoms ----------

function ROIRing({ value, hue, size = 116, caption }: {
  value: number; hue: string; size?: number; caption?: string;
}) {
  const pct = Math.max(0, Math.min(100, value));
  return (
    <div
      className="cc-src-ring relative grid place-items-center rounded-full"
      style={{
        width: size, height: size,
        background: `conic-gradient(${hue} ${pct}%, rgba(255,255,255,0.06) 0)`,
      }}
    >
      <div className="absolute rounded-full bg-[#0b0b12]" style={{ inset: 4 }} />
      <div className="relative flex flex-col items-center leading-none">
        <span className="text-3xl font-semibold tabular-nums" style={{ color: hue }}>
          {Math.round(value)}
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
    <div className={`cc-src-tile rounded-xl border p-3 ${TONE_RING[tone]}`}>
      <div className="text-[10px] uppercase tracking-wider opacity-70">{label}</div>
      <div className="mt-1 truncate text-xl font-semibold tabular-nums">{value}</div>
      {detail && <div className="mt-0.5 truncate text-[11px] opacity-65">{detail}</div>}
    </div>
  );
}

function Bar({ value, hue, label }: { value: number; hue: string; label: string }) {
  const pct = Math.max(0, Math.min(100, value));
  return (
    <div>
      <div className="flex items-center justify-between text-[10px] uppercase tracking-wider text-white/55">
        <span>{label}</span>
        <span className="tabular-nums">{pct.toFixed(0)}</span>
      </div>
      <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-white/5">
        <div className="h-full rounded-full transition-all" style={{ width: `${pct}%`, background: hue }} />
      </div>
    </div>
  );
}

function FunnelStrip({ metrics }: { metrics: ChannelMetrics }) {
  const stages: { key: 'new' | 'outreach' | 'screening' | 'interview' | 'offer'; tone: string; label: string }[] = [
    { key: 'new', tone: 'sky', label: 'New' },
    { key: 'outreach', tone: 'indigo', label: 'Outreach' },
    { key: 'screening', tone: 'violet', label: 'Screening' },
    { key: 'interview', tone: 'amber', label: 'Interview' },
    { key: 'offer', tone: 'emerald', label: 'Offer' },
  ];
  const max = Math.max(1, metrics.reached.new);
  return (
    <div className="grid grid-cols-5 gap-1.5">
      {stages.map(s => {
        const hue = STATUS_HEX[s.tone];
        const reached = metrics.reached[s.key] ?? 0;
        const conv = metrics.conversion[s.key];
        const pct = (reached / max) * 100;
        return (
          <div
            key={s.key}
            className="cc-src-funnel-cell rounded-md border border-white/5 bg-white/[0.02] p-2"
            title={`${s.label}: reached ${reached}${conv !== null ? ` · ${Math.round((conv ?? 0) * 100)}% from prev` : ''}`}
          >
            <div className="text-[9px] uppercase tracking-wider text-white/50">{s.label}</div>
            <div className="mt-0.5 flex items-baseline gap-1">
              <span className="text-base font-semibold tabular-nums" style={{ color: hue }}>{reached}</span>
              {conv !== null && (
                <span className="text-[10px] text-white/45 tabular-nums">{Math.round((conv ?? 0) * 100)}%</span>
              )}
            </div>
            <div className="mt-1 h-1 overflow-hidden rounded-full bg-white/5">
              <div className="h-full" style={{ width: `${pct}%`, background: hue }} />
            </div>
          </div>
        );
      })}
    </div>
  );
}

function MixDonut({ metrics, size = 132 }: { metrics: ChannelMetrics[]; size?: number }) {
  const total = metrics.reduce((s, m) => s + m.count, 0);
  if (total === 0) {
    return <div className="grid h-[132px] w-[132px] place-items-center rounded-full border border-white/10 text-xs text-white/40">No data</div>;
  }
  // Build conic-gradient ranges
  const palette = ['#818cf8', '#34d399', '#facc15', '#fb7185', '#a78bfa', '#38bdf8', '#f472b6', '#22d3ee'];
  let acc = 0;
  const stops: string[] = [];
  metrics.forEach((m, i) => {
    const start = (acc / total) * 100;
    acc += m.count;
    const end = (acc / total) * 100;
    stops.push(`${palette[i % palette.length]} ${start}% ${end}%`);
  });
  return (
    <div className="relative grid place-items-center rounded-full"
      style={{
        width: size, height: size,
        background: `conic-gradient(${stops.join(', ')})`,
      }}
    >
      <div className="absolute rounded-full bg-[#0b0b12]" style={{ inset: 8 }} />
      <div className="relative flex flex-col items-center leading-none">
        <span className="text-2xl font-semibold tabular-nums">{total}</span>
        <span className="mt-0.5 text-[9px] uppercase tracking-wider text-white/45">candidates</span>
      </div>
    </div>
  );
}

function ChannelPill({ channel, tone }: { channel: Channel; tone?: string }) {
  const cls = tone ? TONE_RING[tone] : TONE_RING.slate;
  return (
    <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] ${cls}`}>
      {CHANNEL_LABEL[channel]}
    </span>
  );
}

// ---------- main page ----------

export default function ChannelStudio() {
  const [roles, setRoles] = useState<Role[]>([]);
  const [ready, setReady] = useState(false);
  const [overrideRefresh, setOverrideRefresh] = useState(0);
  const [copied, setCopied] = useState(false);
  const [editingCosts, setEditingCosts] = useState(false);
  const [drawerChannel, setDrawerChannel] = useState<Channel | null>(null);

  useEffect(() => {
    setRoles(listRoles());
    setReady(true);
    const onFocus = () => setRoles(listRoles());
    window.addEventListener('focus', onFocus);
    return () => window.removeEventListener('focus', onFocus);
  }, []);

  const input = useMemo(() => gatherInput(roles, overrideRefresh), [roles, overrideRefresh]);
  const summary: SourceSummary = useMemo(() => analyzeSources(input), [input]);

  const onCopy = async () => {
    await copyToClipboard(buildSourceBrief(summary));
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };
  const onDownload = () => {
    const stamp = new Date().toISOString().slice(0, 10).replace(/-/g, '');
    downloadText(`credicrew_channels_${stamp}.md`, buildSourceBrief(summary));
  };

  const hasData = summary.totalCandidates > 0;
  const best = summary.bestChannel
    ? summary.byChannel.find(m => m.channel === summary.bestChannel) ?? null
    : null;
  const worst = summary.worstChannel && summary.worstChannel !== summary.bestChannel
    ? summary.byChannel.find(m => m.channel === summary.worstChannel) ?? null
    : null;

  // Active candidates by channel — used by the channel drawer.
  const channelCandidates = useMemo(() => {
    if (!drawerChannel) return [] as SourceCandidate[];
    return input.candidates.filter(c => c.source.channel === drawerChannel);
  }, [drawerChannel, input.candidates]);

  return (
    <main className="min-h-screen bg-gradient-to-b from-[#0b0b12] to-black text-white">
      <div className="mx-auto max-w-6xl px-4 pb-24">
        <header className="flex items-center justify-between py-6">
          <div>
            <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.18em] text-violet-300/80">
              <span>Day 42</span><span className="opacity-40">·</span><span>Channel Studio</span>
            </div>
            <h1 className="mt-1 text-3xl font-semibold">Sourcing Intelligence</h1>
            <p className="mt-1 text-sm text-white/65">
              Every other surface analyses what happens after a candidate is in pipeline. This one tells you
              where to spend your next hour of outreach.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setEditingCosts(true)}
              className="rounded-lg border border-white/10 bg-white/[0.04] px-3 py-1.5 text-xs text-white/80 hover:bg-white/[0.07]"
            >
              Edit channel costs
            </button>
            <button
              onClick={onCopy}
              className="rounded-lg border border-white/10 bg-white/[0.04] px-3 py-1.5 text-xs text-white/80 hover:bg-white/[0.07]"
            >
              {copied ? 'Copied ✓' : 'Copy brief'}
            </button>
            <button
              onClick={onDownload}
              className="rounded-lg border border-violet-400/30 bg-violet-400/10 px-3 py-1.5 text-xs text-violet-100 hover:bg-violet-400/15"
            >
              Download .md
            </button>
          </div>
        </header>

        {!ready ? (
          <div className="rounded-xl border border-white/10 bg-white/[0.03] p-6 text-sm text-white/70">
            Loading…
          </div>
        ) : !hasData ? (
          <div className="rounded-xl border border-white/10 bg-white/[0.03] p-8 text-sm text-white/70">
            <p className="text-white/90">No candidates in any role&apos;s shortlist yet.</p>
            <p className="mt-1">
              Open <Link href="/" className="underline decoration-violet-300/40 hover:text-violet-200">Discover</Link> and shortlist a few candidates, or
              save a JD as a <Link href="/roles/new" className="underline decoration-violet-300/40 hover:text-violet-200">role</Link>, then come back.
              Channel attribution and ROI scoring will light up the moment there&apos;s data.
            </p>
          </div>
        ) : (
          <>
            {/* ---------- HERO ---------- */}
            <section className="cc-src-hero relative mb-6 overflow-hidden rounded-2xl border border-white/10 bg-white/[0.03] p-5">
              <div className="grid items-center gap-5 md:grid-cols-[auto_1fr]">
                <div className="flex items-center gap-5">
                  <MixDonut metrics={summary.byChannel} />
                  <div>
                    <div className="text-[10px] uppercase tracking-wider text-white/55">Pipeline mix</div>
                    <div className="mt-1 grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
                      {summary.byChannel.slice(0, 6).map((m, i) => {
                        const palette = ['#818cf8', '#34d399', '#facc15', '#fb7185', '#a78bfa', '#38bdf8', '#f472b6', '#22d3ee'];
                        return (
                          <div key={m.channel} className="flex items-center gap-1.5">
                            <span className="inline-block h-2 w-2 rounded-full" style={{ background: palette[i % palette.length] }} />
                            <span className="text-white/75">{m.label}</span>
                            <span className="ml-auto tabular-nums text-white/55">{m.count}</span>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                  <Tile
                    label="Active pipeline"
                    value={String(summary.totalActive)}
                    detail={`${summary.totalCandidates} touched total`}
                    tone="sky"
                  />
                  <Tile
                    label="Reached offer"
                    value={String(summary.totalOffers)}
                    detail={`${summary.totalInterviewed} interviewed`}
                    tone="emerald"
                  />
                  <Tile
                    label="Total spend"
                    value={fmtRupees(summary.totalSpend)}
                    detail={
                      summary.costPerOffer !== null
                        ? `${fmtRupees(summary.costPerOffer)} / offer`
                        : 'no offers yet'
                    }
                    tone="violet"
                  />
                  <Tile
                    label="Diversification"
                    value={`${Math.round(summary.diversification * 100)}`}
                    detail={summary.diversification < 0.5 ? 'concentration risk' : 'healthy mix'}
                    tone={summary.diversification < 0.5 ? 'amber' : 'sky'}
                  />
                </div>
              </div>
            </section>

            {/* ---------- BEST / WORST / RECS ---------- */}
            <section className="mb-6 grid gap-3 md:grid-cols-3">
              {best && (
                <div
                  className="cc-src-best rounded-2xl border bg-white/[0.03] p-4"
                  style={{ borderColor: 'rgba(52,211,153,0.30)' }}
                >
                  <div className="flex items-center justify-between">
                    <div className="text-[10px] uppercase tracking-wider text-emerald-200/80">Best channel</div>
                    <ChannelPill channel={best.channel} tone={BAND_TONE[best.band]} />
                  </div>
                  <div className="mt-2 flex items-center gap-3">
                    <ROIRing value={best.roi} hue={BAND_HUE[best.band]} size={90} caption="ROI" />
                    <div>
                      <div className="text-base font-semibold">{best.label}</div>
                      <div className="text-xs text-white/60">{best.count} candidates · {best.reached.offer} reached offer</div>
                      <div className="mt-1 text-[11px] text-white/55">{best.recommendation}</div>
                    </div>
                  </div>
                </div>
              )}
              {worst && (
                <div
                  className="cc-src-worst rounded-2xl border bg-white/[0.03] p-4"
                  style={{ borderColor: 'rgba(244,63,94,0.30)' }}
                >
                  <div className="flex items-center justify-between">
                    <div className="text-[10px] uppercase tracking-wider text-rose-200/80">Reallocate from</div>
                    <ChannelPill channel={worst.channel} tone={BAND_TONE[worst.band]} />
                  </div>
                  <div className="mt-2 flex items-center gap-3">
                    <ROIRing value={worst.roi} hue={BAND_HUE[worst.band]} size={90} caption="ROI" />
                    <div>
                      <div className="text-base font-semibold">{worst.label}</div>
                      <div className="text-xs text-white/60">{worst.count} candidates · cost {fmtRupees(worst.costPerOffer)}/offer</div>
                      <div className="mt-1 text-[11px] text-white/55">{worst.recommendation}</div>
                    </div>
                  </div>
                </div>
              )}
              <div className="cc-src-recs rounded-2xl border border-white/10 bg-white/[0.03] p-4">
                <div className="flex items-center justify-between">
                  <div className="text-[10px] uppercase tracking-wider text-white/55">This week&apos;s moves</div>
                  <span className="text-[10px] text-white/40 tabular-nums">{summary.recommendations.length}</span>
                </div>
                {summary.recommendations.length === 0 ? (
                  <div className="mt-3 text-xs text-white/55">No standout moves yet — channels are within normal bands.</div>
                ) : (
                  <ul className="mt-2 space-y-2">
                    {summary.recommendations.map((r, i) => (
                      <li key={i} className="rounded-md border border-white/5 bg-white/[0.02] p-2">
                        <div className="flex items-center gap-1.5">
                          <span
                            className="inline-block h-1.5 w-1.5 rounded-full"
                            style={{ background: BAND_HUE[r.band] }}
                          />
                          <span className="text-[12px] font-medium">{r.title}</span>
                        </div>
                        <div className="mt-0.5 text-[11px] leading-snug text-white/65">{r.detail}</div>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </section>

            {/* ---------- PER-CHANNEL CARDS ---------- */}
            <section className="space-y-3">
              {summary.byChannel.map(m => (
                <article
                  key={m.channel}
                  className="cc-src-card relative overflow-hidden rounded-2xl border border-white/10 bg-white/[0.03] p-4"
                  style={{ '--src-accent': BAND_HUE[m.band] } as CSSProperties}
                >
                  <div className="grid items-start gap-4 md:grid-cols-[auto_1fr_280px]">
                    <button
                      onClick={() => setDrawerChannel(m.channel)}
                      className="block"
                      aria-label={`Open ${m.label}`}
                    >
                      <ROIRing value={m.roi} hue={BAND_HUE[m.band]} caption="ROI" />
                    </button>

                    <div>
                      <div className="flex flex-wrap items-baseline gap-2">
                        <h2 className="text-lg font-semibold">{m.label}</h2>
                        <span
                          className="rounded-full px-2 py-0.5 text-[10px] uppercase tracking-wider"
                          style={{
                            color: BAND_HUE[m.band],
                            background: `color-mix(in srgb, ${BAND_HUE[m.band]} 14%, transparent)`,
                            border: `1px solid color-mix(in srgb, ${BAND_HUE[m.band]} 35%, transparent)`,
                          }}
                        >
                          {BAND_LABEL[m.band]}
                        </span>
                        <span className="text-xs text-white/55">
                          {m.count} candidate{m.count === 1 ? '' : 's'} · {m.active} active
                        </span>
                      </div>
                      <p className="mt-1 text-xs text-white/55">{CHANNEL_BLURB[m.channel]}</p>

                      <div className="mt-3"><FunnelStrip metrics={m} /></div>

                      <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
                        <Bar value={m.qualityScore} hue="#34d399" label="Quality" />
                        <Bar value={m.conversionScore} hue="#38bdf8" label="Conversion" />
                        <Bar value={m.costScore} hue="#a78bfa" label="Cost efficiency" />
                        <Bar value={m.speedScore} hue="#facc15" label="Speed" />
                      </div>

                      <p className="mt-3 text-[12px] leading-snug text-white/70">{m.recommendation}</p>
                    </div>

                    <div className="rounded-xl border border-white/10 bg-white/[0.02] p-3 text-[11px] text-white/70">
                      <div className="grid grid-cols-2 gap-y-2 gap-x-3 tabular-nums">
                        <div>
                          <div className="text-[9px] uppercase tracking-wider text-white/45">Mean match</div>
                          <div className="text-sm text-white/85">{m.meanMatchScore.toFixed(0)}</div>
                        </div>
                        <div>
                          <div className="text-[9px] uppercase tracking-wider text-white/45">Mean composite</div>
                          <div className="text-sm text-white/85">{m.meanComposite === null ? '—' : m.meanComposite.toFixed(0)}</div>
                        </div>
                        <div>
                          <div className="text-[9px] uppercase tracking-wider text-white/45">Days→offer</div>
                          <div className="text-sm text-white/85">{m.meanDaysToOffer === null ? '—' : `${m.meanDaysToOffer.toFixed(0)}d`}</div>
                        </div>
                        <div>
                          <div className="text-[9px] uppercase tracking-wider text-white/45">Accept odds</div>
                          <div className="text-sm text-white/85">{m.meanWinProb === null ? '—' : `${Math.round(m.meanWinProb * 100)}%`}</div>
                        </div>
                        <div className="col-span-2 mt-1 border-t border-white/5 pt-2">
                          <div className="text-[9px] uppercase tracking-wider text-white/45">Spend</div>
                          <div className="text-sm text-white/85">
                            {fmtRupees(m.totalSpend)} <span className="text-white/45">({fmtRupees(m.costPerCandidate)}/touch)</span>
                          </div>
                          <div className="mt-1 text-[10px] text-white/55">
                            {m.costPerInterview === null ? '—/interview' : `${fmtRupees(m.costPerInterview)}/interview`}
                            <span className="px-1 opacity-40">·</span>
                            {m.costPerOffer === null ? '—/offer' : `${fmtRupees(m.costPerOffer)}/offer`}
                          </div>
                        </div>
                      </div>
                      {m.topLocations && m.topLocations.length > 0 && (
                        <div className="mt-3 border-t border-white/5 pt-2">
                          <div className="text-[9px] uppercase tracking-wider text-white/45">Top locations</div>
                          <div className="mt-1 flex flex-wrap gap-1">
                            {m.topLocations.map(loc => (
                              <span key={loc.label} className="rounded-full border border-white/10 bg-white/[0.03] px-1.5 py-0.5 text-[10px] text-white/75">
                                {loc.label} <span className="text-white/40">·</span> {loc.count}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                  <div
                    className="pointer-events-none absolute inset-x-0 top-0 h-px"
                    style={{ background: `linear-gradient(90deg, transparent, ${BAND_HUE[m.band]}55, transparent)` }}
                  />
                </article>
              ))}
            </section>

            {/* ---------- CHANNEL × STAGE HEATMAP ---------- */}
            <section className="mt-6">
              <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-4">
                <div className="flex items-center justify-between">
                  <div>
                    <h2 className="text-base font-semibold">Channel × stage heatmap</h2>
                    <p className="text-xs text-white/55">Where every channel&apos;s pipeline is sitting right now.</p>
                  </div>
                  <div className="text-[10px] uppercase tracking-wider text-white/45">Counts (here)</div>
                </div>
                <div className="mt-3 overflow-x-auto">
                  <table className="w-full min-w-[640px] border-separate border-spacing-1 text-xs">
                    <thead>
                      <tr className="text-white/55">
                        <th className="text-left font-normal">Channel</th>
                        {(['new', 'outreach', 'screening', 'interview', 'offer'] as const).map(k => (
                          <th key={k} className="font-normal capitalize">{k}</th>
                        ))}
                        <th className="font-normal">ROI</th>
                      </tr>
                    </thead>
                    <tbody>
                      {summary.byChannel.map(m => {
                        const stageOrder = ['new', 'outreach', 'screening', 'interview', 'offer'] as const;
                        const maxHere = Math.max(1, ...stageOrder.map((k, i) => {
                          const nextKey = stageOrder[i + 1];
                          return m.reached[k] - (nextKey ? m.reached[nextKey] : 0);
                        }));
                        return (
                          <tr key={m.channel}>
                            <td className="rounded-md bg-white/[0.02] px-2 py-1 text-white/80">{m.label}</td>
                            {stageOrder.map((k, i, arr) => {
                              const nextKey = arr[i + 1];
                              const here = m.reached[k] - (nextKey ? m.reached[nextKey] : 0);
                              const intensity = Math.min(1, here / maxHere);
                              const tone = STATUS_TONE[k];
                              const hue = STATUS_HEX[tone];
                              return (
                                <td
                                  key={k}
                                  className="cc-src-heat rounded-md text-center tabular-nums"
                                  style={{
                                    background: `color-mix(in srgb, ${hue} ${intensity * 30 + 4}%, transparent)`,
                                    color: intensity > 0.5 ? '#0b0b12' : 'white',
                                  }}
                                >
                                  {here}
                                </td>
                              );
                            })}
                            <td
                              className="rounded-md text-center font-semibold tabular-nums"
                              style={{ color: BAND_HUE[m.band], background: `color-mix(in srgb, ${BAND_HUE[m.band]} 12%, transparent)` }}
                            >
                              {m.roi.toFixed(0)}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            </section>
          </>
        )}
      </div>

      {/* ---------- COST EDITOR DRAWER ---------- */}
      {editingCosts && (
        <div
          className="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm"
          onClick={() => setEditingCosts(false)}
        >
          <aside
            className="cc-src-drawer absolute right-0 top-0 h-full w-full max-w-md overflow-y-auto border-l border-white/10 bg-[#0e0e16] p-4"
            onClick={e => e.stopPropagation()}
          >
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-base font-semibold">Channel cost editor</h2>
                <p className="text-xs text-white/55">Override ₹/candidate-touched per channel. Persists locally.</p>
              </div>
              <button onClick={() => setEditingCosts(false)} className="rounded-md border border-white/10 px-2 py-1 text-xs text-white/70 hover:bg-white/5">Close</button>
            </div>
            <div className="mt-4 space-y-2">
              {CHANNELS.map(ch => {
                const stored = readChannelCosts()[ch];
                const current = stored ?? DEFAULT_COST_PER_CANDIDATE[ch];
                return (
                  <label key={ch} className="block rounded-lg border border-white/10 bg-white/[0.02] p-3">
                    <div className="flex items-center justify-between">
                      <span className="text-sm text-white/85">{CHANNEL_LABEL[ch]}</span>
                      <span className="text-[10px] text-white/45">default {DEFAULT_COST_PER_CANDIDATE[ch]}k</span>
                    </div>
                    <p className="mt-0.5 text-[11px] text-white/55">{CHANNEL_BLURB[ch]}</p>
                    <div className="mt-2 flex items-center gap-2">
                      <input
                        type="number"
                        step="0.5"
                        min={0}
                        defaultValue={current}
                        onBlur={e => {
                          const v = Number(e.currentTarget.value);
                          if (!Number.isNaN(v) && v >= 0) {
                            writeChannelCost(ch, v);
                            setOverrideRefresh(x => x + 1);
                          }
                        }}
                        className="w-28 rounded-md border border-white/10 bg-white/[0.04] px-2 py-1 text-sm tabular-nums text-white"
                      />
                      <span className="text-xs text-white/55">₹k / candidate</span>
                    </div>
                  </label>
                );
              })}
              <button
                onClick={() => {
                  resetChannelCosts();
                  setOverrideRefresh(x => x + 1);
                }}
                className="mt-2 w-full rounded-md border border-white/10 bg-white/[0.04] px-3 py-2 text-xs text-white/75 hover:bg-white/[0.07]"
              >
                Reset all to defaults
              </button>
            </div>
          </aside>
        </div>
      )}

      {/* ---------- PER-CHANNEL CANDIDATE DRAWER ---------- */}
      {drawerChannel && (
        <div
          className="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm"
          onClick={() => setDrawerChannel(null)}
        >
          <aside
            className="cc-src-drawer absolute right-0 top-0 h-full w-full max-w-lg overflow-y-auto border-l border-white/10 bg-[#0e0e16] p-4"
            onClick={e => e.stopPropagation()}
          >
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-base font-semibold">{CHANNEL_LABEL[drawerChannel]}</h2>
                <p className="text-xs text-white/55">{CHANNEL_BLURB[drawerChannel]}</p>
              </div>
              <button onClick={() => setDrawerChannel(null)} className="rounded-md border border-white/10 px-2 py-1 text-xs text-white/70 hover:bg-white/5">Close</button>
            </div>
            <div className="mt-3 text-[11px] text-white/55">
              Re-attribute a candidate to a different channel below. Updates are local-only.
            </div>
            <ul className="mt-2 space-y-1.5">
              {channelCandidates.map(c => (
                <li key={`${c.roleId}:${c.candidateId}`} className="rounded-lg border border-white/10 bg-white/[0.02] p-2">
                  <div className="flex items-center justify-between gap-2">
                    <div className="min-w-0">
                      <div className="truncate text-sm text-white/85">{c.name}</div>
                      <div className="truncate text-[11px] text-white/55">
                        {c.roleName} · <span className="text-white/45">{STATUS_LABEL[c.status]}</span>
                        {c.location ? ` · ${c.location}` : ''}
                      </div>
                      {c.source.detail && (
                        <div className="mt-0.5 truncate text-[10px] italic text-white/40">{c.source.detail}</div>
                      )}
                    </div>
                    <select
                      defaultValue={c.source.channel}
                      onChange={e => {
                        setSourceChannel(c.candidateId, e.currentTarget.value as Channel);
                        setOverrideRefresh(x => x + 1);
                      }}
                      className="rounded-md border border-white/10 bg-[#0b0b12] px-2 py-1 text-xs text-white/85"
                    >
                      {CHANNELS.map(ch => (
                        <option key={ch} value={ch}>{CHANNEL_LABEL[ch]}</option>
                      ))}
                    </select>
                  </div>
                </li>
              ))}
              {channelCandidates.length === 0 && (
                <li className="rounded-md border border-white/5 bg-white/[0.02] p-3 text-xs text-white/55">
                  No candidates currently attributed here.
                </li>
              )}
            </ul>
          </aside>
        </div>
      )}
    </main>
  );
}
