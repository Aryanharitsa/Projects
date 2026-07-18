'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import type { CSSProperties } from 'react';

import { candidates as CANDIDATES } from '@/data/candidates';
import { matchCandidate } from '@/lib/match';
import {
  listRoles,
  type Role,
} from '@/lib/roles';
import {
  getInterview,
  summarise,
  buildRubric,
  type Recommendation,
} from '@/lib/interview';
import {
  benchmarkComp,
  getOffer,
  winProbability,
} from '@/lib/offer';
import {
  buildPortfolio,
  type PortfolioCandidate,
  type PortfolioInput,
  type PortfolioRole,
} from '@/lib/portfolio';
import {
  computeCalibration,
  ensurePanel,
  getPanel,
  type CalibrationResult,
  type CandidateLite,
  type RubricLite,
} from '@/lib/calibration';
import {
  buildPanelSeed,
  type SeedCandidate,
} from '@/lib/panel_seed';
import {
  analyzeHindsight,
  interviewsByKey,
  listOutcomes,
  type HireOutcome,
} from '@/lib/hindsight';
import {
  computePeerParity,
  ensureSeeded,
  type PeerParityResult,
} from '@/lib/peer_parity';
import { buildSeed as buildPeerSeed } from '@/lib/peer_seed';
import {
  analyzePortfolio,
  analyzeRole,
  type RoleVerdict,
  type VerdictCandidate,
} from '@/lib/verdict';
import {
  analyzeSources,
  type SourceCandidate,
  type SourceInput,
} from '@/lib/sources';
import {
  getSourceFor,
  readChannelCosts,
} from '@/data/sources_seed';
import {
  analyzeCompass,
  AXES,
  AXIS_HEX,
  AXIS_BLURB,
  BAND_HEX,
  BAND_LABEL,
  buildCompassBrief,
  radarAxisAnchors,
  radarPolygonPoints,
  type CompassAxis,
  type CompassBand,
  type CompassSummary,
} from '@/lib/compass';

// ---------- utilities ----------

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
  a.remove();
  URL.revokeObjectURL(url);
}

// ---------- input gatherers ----------

function gatherPortfolioInput(roles: Role[]): PortfolioInput {
  const pRoles: PortfolioRole[] = roles.map(role => {
    const cands: PortfolioCandidate[] = role.shortlist.map(entry => {
      const c = CANDIDATES.find(x => x.id === entry.candidateId);
      const fallback = { id: entry.candidateId, name: `Candidate #${entry.candidateId}` };
      const cand = c ?? fallback;
      const match = matchCandidate(role.plan, cand);
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

function gatherCalibrationInputs(roles: Role[]): CalibrationResult[] {
  const out: CalibrationResult[] = [];
  for (const role of roles) {
    const shortlisted = role.shortlist.slice(0, 8);
    if (shortlisted.length === 0) continue;
    const candData = shortlisted
      .map(e => CANDIDATES.find(c => c.id === e.candidateId))
      .filter((c): c is (typeof CANDIDATES)[number] => Boolean(c));
    if (candData.length === 0) continue;
    const rubric: RubricLite[] = buildRubric(role.plan).map(d => ({
      key: d.key,
      label: d.label,
      weight: d.weight,
    }));
    if (rubric.length === 0) continue;
    const seedCands: SeedCandidate[] = candData.map(c => ({
      id: c.id,
      name: c.name,
      score: c.score,
    }));
    const panel =
      getPanel(role.id) ??
      ensurePanel(role.id, () => buildPanelSeed(role.id, seedCands, rubric));
    const lites: CandidateLite[] = candData.map(c => ({
      id: c.id,
      name: c.name,
      role: c.role,
      location: c.location,
    }));
    out.push(computeCalibration(panel, lites, rubric));
  }
  return out;
}

function gatherParityInputs(roles: Role[]): PeerParityResult[] {
  const out: PeerParityResult[] = [];
  for (const role of roles) {
    // Take the highest-composite candidate with a drafted offer per role.
    let best: {
      composite: number | null;
      base: number;
      equityPct: number;
      signOn: number;
      targetBonusPct: number;
      candidateName?: string;
    } | null = null;
    let bestKey = -1;
    for (const entry of role.shortlist) {
      const draft = getOffer(role.id, entry.candidateId);
      if (!draft) continue;
      const ir = getInterview(role.id, entry.candidateId);
      let composite: number | null = null;
      if (ir) {
        const s = summarise(ir);
        composite = s.ratedCount > 0 ? s.composite : null;
      }
      const cand = CANDIDATES.find(c => c.id === entry.candidateId);
      const key = composite ?? draft.base;
      if (key > bestKey) {
        bestKey = key;
        best = {
          composite,
          base: draft.base,
          equityPct: draft.equityPct,
          signOn: draft.signOn,
          targetBonusPct: draft.targetBonusPct,
          candidateName: cand?.name,
        };
      }
    }
    if (!best) continue;
    const peers = ensureSeeded(role.id, buildPeerSeed);
    if (peers.length === 0) continue;
    out.push(computePeerParity(best, peers));
  }
  return out;
}

function gatherVerdictInput(roles: Role[]) {
  const candMap = new Map<number, VerdictCandidate>();
  for (const c of CANDIDATES) candMap.set(c.id, c);
  const roleVerdicts: RoleVerdict[] = roles.map(role => {
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
  return analyzePortfolio(roleVerdicts);
}

function gatherSourceInput(roles: Role[]): SourceInput {
  const all: SourceCandidate[] = [];
  for (const role of roles) {
    for (const entry of role.shortlist) {
      const c = CANDIDATES.find(x => x.id === entry.candidateId);
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
      const attribution = getSourceFor(entry.candidateId);
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
        source: attribution,
        winProbability: winProb,
        hasOffer: !!draft,
        location: c?.location,
      });
    }
  }
  return { candidates: all, costOverrides: readChannelCosts() };
}

// ---------- visual atoms ----------

function CompositeRing({
  value,
  band,
  size = 220,
}: {
  value: number | null;
  band: CompassBand;
  size?: number;
}) {
  const hue = BAND_HEX[band];
  const pct = value === null ? 0 : Math.max(0, Math.min(100, value));
  return (
    <div
      className="relative grid place-items-center rounded-full"
      style={{
        width: size,
        height: size,
        background: `conic-gradient(${hue} ${pct}%, rgba(255,255,255,0.06) 0)`,
        boxShadow: `0 0 60px ${hue}22`,
      }}
    >
      <div
        className="absolute rounded-full bg-[#0b0b12]"
        style={{ inset: 8 }}
      />
      <div className="relative flex flex-col items-center leading-none">
        <span
          className="text-6xl font-semibold tabular-nums"
          style={{ color: hue }}
        >
          {value === null ? '—' : Math.round(value)}
        </span>
        <span className="mt-2 text-[10px] uppercase tracking-[0.25em] text-white/50">
          Loop Health
        </span>
        <span
          className="mt-1 rounded-full border px-2 py-[2px] text-[10px] font-medium uppercase tracking-widest"
          style={{
            borderColor: `${hue}55`,
            background: `${hue}15`,
            color: hue,
          }}
        >
          {BAND_LABEL[band]}
        </span>
      </div>
    </div>
  );
}

function RadarChart({ summary }: { summary: CompassSummary }) {
  const size = 340;
  const cx = size / 2;
  const cy = size / 2;
  const r = 128;
  const n = AXES.length;

  const scores = AXES.map(a => summary.axes[a].score);
  const polygon = radarPolygonPoints(scores, cx, cy, r);
  const labels = radarAxisAnchors(n, cx, cy, r);

  const grid = [0.25, 0.5, 0.75, 1].map((t, i) => (
    <polygon
      key={i}
      points={radarPolygonPoints(
        Array.from({ length: n }, () => 100 * t),
        cx,
        cy,
        r,
      )}
      fill="none"
      stroke="rgba(255,255,255,0.08)"
      strokeWidth={1}
    />
  ));

  const spokes = Array.from({ length: n }, (_, i) => {
    const theta = -Math.PI / 2 + (i * 2 * Math.PI) / n;
    const x2 = cx + Math.cos(theta) * r;
    const y2 = cy + Math.sin(theta) * r;
    return (
      <line
        key={i}
        x1={cx}
        y1={cy}
        x2={x2}
        y2={y2}
        stroke="rgba(255,255,255,0.06)"
        strokeWidth={1}
      />
    );
  });

  const points = AXES.map((axis, i) => {
    const s = scores[i];
    const t = s === null ? 0.05 : Math.max(0.02, s / 100);
    const theta = -Math.PI / 2 + (i * 2 * Math.PI) / n;
    const x = cx + Math.cos(theta) * r * t;
    const y = cy + Math.sin(theta) * r * t;
    return (
      <circle
        key={axis}
        cx={x}
        cy={y}
        r={5}
        fill={AXIS_HEX[axis]}
        stroke="#0b0b12"
        strokeWidth={2}
      />
    );
  });

  return (
    <svg viewBox={`0 0 ${size} ${size}`} className="mx-auto block h-[340px] w-[340px] max-w-full">
      <defs>
        <radialGradient id="radar-fill" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="#a78bfa" stopOpacity="0.35" />
          <stop offset="100%" stopColor="#38bdf8" stopOpacity="0.1" />
        </radialGradient>
      </defs>
      {grid}
      {spokes}
      <polygon
        points={polygon}
        fill="url(#radar-fill)"
        stroke="#a78bfa"
        strokeWidth={1.5}
        strokeOpacity={0.9}
      />
      {points}
      {labels.map((pos, i) => {
        const axis = AXES[i];
        const s = summary.axes[axis];
        return (
          <g key={axis}>
            <text
              x={pos.x}
              y={pos.y - 4}
              fill="#e2e8f0"
              fontSize={11}
              fontWeight={600}
              textAnchor={pos.anchor}
            >
              {s.label}
            </text>
            <text
              x={pos.x}
              y={pos.y + 10}
              fill={AXIS_HEX[axis]}
              fontSize={10}
              fontWeight={700}
              textAnchor={pos.anchor}
            >
              {s.score === null ? '—' : `${s.score}/100`}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

function AxisTile({
  axis,
  compass,
}: {
  axis: CompassAxis;
  compass: CompassSummary;
}) {
  const a = compass.axes[axis];
  const hue = a.score === null ? BAND_HEX.unknown : AXIS_HEX[axis];
  const pct = a.score === null ? 0 : a.score;
  const isWeakest = compass.weakest === axis && a.score !== null;
  const isStrongest = compass.strongest === axis && a.score !== null;
  return (
    <Link
      href={a.cta.href}
      className="group relative flex flex-col gap-3 rounded-2xl border border-white/8 bg-gradient-to-br from-white/4 to-white/2 p-5 transition hover:border-white/15 hover:bg-white/6"
      style={{
        boxShadow: isWeakest
          ? `0 0 0 1px ${BAND_HEX.critical}40 inset`
          : isStrongest
            ? `0 0 0 1px ${BAND_HEX.strong}30 inset`
            : undefined,
      }}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2">
          <span
            className="grid h-8 w-8 place-items-center rounded-full text-[11px] font-semibold uppercase tracking-wider"
            style={{
              background: `${hue}18`,
              color: hue,
              border: `1px solid ${hue}30`,
            }}
          >
            {a.label.slice(0, 2)}
          </span>
          <div>
            <div className="text-[13px] font-semibold text-white">{a.label}</div>
            <div className="text-[10px] uppercase tracking-widest text-white/45">
              {BAND_LABEL[a.band]}
            </div>
          </div>
        </div>
        <div
          className="grid h-14 w-14 place-items-center rounded-full"
          style={{
            background: `conic-gradient(${hue} ${pct}%, rgba(255,255,255,0.06) 0)`,
          }}
        >
          <div
            className="absolute rounded-full bg-[#0b0b12]"
            style={{ width: 44, height: 44 }}
          />
          <span
            className="relative text-sm font-semibold tabular-nums"
            style={{ color: hue }}
          >
            {a.score === null ? '—' : a.score}
          </span>
        </div>
      </div>

      <div className="text-[13px] font-medium text-white/85">{a.headline}</div>

      <ul className="mt-1 space-y-1 text-[11.5px] text-white/60">
        {a.drivers.map((d, i) => (
          <li key={i} className="flex gap-2">
            <span className="mt-[6px] inline-block h-1 w-1 flex-none rounded-full bg-white/40" />
            <span className="leading-snug">{d}</span>
          </li>
        ))}
      </ul>

      <div className="mt-auto flex items-center justify-between text-[11px] text-white/40">
        <span>{AXIS_BLURB[axis]}</span>
        <span
          className="ml-3 flex flex-none items-center gap-1 text-white/70 transition group-hover:text-white"
          style={{ color: hue }}
        >
          {a.cta.label} →
        </span>
      </div>

      {(isWeakest || isStrongest) && (
        <span
          className="absolute -top-2 right-4 rounded-full px-2 py-[2px] text-[9px] font-bold uppercase tracking-widest"
          style={{
            background: isWeakest ? BAND_HEX.critical : BAND_HEX.strong,
            color: '#0b0b12',
          }}
        >
          {isWeakest ? 'Weakest' : 'Strongest'}
        </span>
      )}
    </Link>
  );
}

function AdviceCard({ compass }: { compass: CompassSummary }) {
  if (compass.advice.length === 0) {
    return (
      <div className="rounded-2xl border border-emerald-400/20 bg-emerald-400/5 p-5 text-[13px] text-emerald-100">
        <div className="text-[10px] uppercase tracking-[0.25em] text-emerald-200/80">
          No recommended moves
        </div>
        <div className="mt-2 font-semibold">The loop is running clean.</div>
        <div className="mt-1 text-emerald-100/70">
          Every axis with data is in the stable or strong band. Keep pushing the top of funnel.
        </div>
      </div>
    );
  }
  return (
    <div className="rounded-2xl border border-white/8 bg-gradient-to-br from-rose-500/8 via-amber-500/5 to-transparent p-5">
      <div className="text-[10px] uppercase tracking-[0.25em] text-white/50">
        Recommended moves
      </div>
      <ul className="mt-3 space-y-3">
        {compass.advice.map(a => (
          <li
            key={a.axis}
            className="flex flex-col gap-1 rounded-xl border border-white/6 bg-white/3 p-3"
          >
            <div className="flex items-center justify-between">
              <div className="text-[13px] font-semibold text-white">
                {a.headline}
              </div>
              <span
                className="rounded-full px-2 py-[2px] text-[9px] font-bold uppercase tracking-widest"
                style={{
                  background:
                    a.severity === 'high'
                      ? BAND_HEX.critical
                      : a.severity === 'medium'
                        ? BAND_HEX.warning
                        : BAND_HEX.stable,
                  color: '#0b0b12',
                }}
              >
                {a.severity}
              </span>
            </div>
            <div className="text-[12px] text-white/70">{a.detail}</div>
            <Link
              href={a.cta.href}
              className="mt-1 self-start text-[12px] font-semibold"
              style={{ color: AXIS_HEX[a.axis] }}
            >
              {a.cta.label} →
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}

// ---------- page ----------

export default function CompassPage() {
  const [roles, setRoles] = useState<Role[]>([]);
  const [outcomes, setOutcomes] = useState<HireOutcome[]>([]);
  const [hydrated, setHydrated] = useState(false);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    setRoles(listRoles());
    setOutcomes(listOutcomes());
    setHydrated(true);
    const onFocus = () => {
      setRoles(listRoles());
      setOutcomes(listOutcomes());
    };
    window.addEventListener('focus', onFocus);
    return () => window.removeEventListener('focus', onFocus);
  }, []);

  const summary = useMemo<CompassSummary | null>(() => {
    if (!hydrated || roles.length === 0) return null;
    const portfolio = buildPortfolio(gatherPortfolioInput(roles));
    const calibration = gatherCalibrationInputs(roles);
    const parity = gatherParityInputs(roles);
    const verdict = gatherVerdictInput(roles);
    const sources = analyzeSources(gatherSourceInput(roles));
    const ivKeys = interviewsByKey(roles);
    const overrides = new Map<string, HireOutcome>();
    for (const o of outcomes) overrides.set(`${o.candidateId}::${o.roleId}`, o);
    const hindsight = analyzeHindsight(roles, CANDIDATES, overrides, {
      interviewsByKey: ivKeys,
    });
    return analyzeCompass({
      portfolio,
      calibration,
      hindsight,
      parity,
      verdict,
      sources,
    });
  }, [hydrated, roles, outcomes]);

  const gradientStyle: CSSProperties = {
    background: `radial-gradient(1200px 400px at 50% -10%, ${
      summary ? BAND_HEX[summary.band] : '#a78bfa'
    }22, transparent)`,
  };

  const onCopyBrief = async () => {
    if (!summary) return;
    await copyToClipboard(buildCompassBrief(summary));
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  const onDownloadBrief = () => {
    if (!summary) return;
    downloadText('compass_brief.md', buildCompassBrief(summary));
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
              style={{ background: summary ? BAND_HEX[summary.band] : '#a78bfa' }}
            />
            Loop Health Radar
            <span className="ml-2 rounded-full bg-gradient-to-br from-emerald-400 via-cyan-400 to-indigo-400 px-2 py-[1px] text-[9px] font-bold uppercase tracking-widest text-neutral-950">
              NEW
            </span>
          </div>
          <h1 className="mt-2 text-3xl font-semibold tracking-tight sm:text-4xl">
            Compass —{' '}
            <span
              style={{ color: summary ? BAND_HEX[summary.band] : '#a78bfa' }}
            >
              is the whole loop healthy?
            </span>
          </h1>
          <p className="mt-2 max-w-3xl text-[13px] text-white/60">
            Every prior surface answers a <em>local</em> question — this role&apos;s
            funnel, this candidate&apos;s ranking, this offer&apos;s parity. Compass
            sits above all of them and gives you one number, one weakest axis, and
            one recommended move for the whole hiring machine. Six axes, each
            earned by an upstream engine, each with a deep-link back to its
            source.
          </p>
        </div>
      </div>

      {!hydrated ? (
        <div className="mx-auto max-w-6xl px-4 py-16 text-center text-sm text-white/50">
          Loading…
        </div>
      ) : roles.length === 0 ? (
        <div className="mx-auto max-w-6xl px-4 py-16">
          <div className="rounded-3xl border border-white/8 bg-white/3 p-8 text-center">
            <div className="text-[10px] uppercase tracking-[0.25em] text-white/45">
              No roles yet
            </div>
            <div className="mt-3 text-lg font-semibold">
              Create a role to light up the loop.
            </div>
            <p className="mt-2 text-[13px] text-white/60">
              Compass reads from every upstream surface — funnel, calibration,
              hindsight, parity, verdict, sources. Create a role, shortlist a
              candidate, and the radar populates axis by axis.
            </p>
            <Link
              href="/roles"
              className="mt-6 inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/10 px-4 py-2 text-[12px] font-medium text-white transition hover:bg-white/15"
            >
              Open Roles →
            </Link>
          </div>
        </div>
      ) : summary ? (
        <div className="mx-auto max-w-6xl px-4 py-8">
          {/* Hero — composite ring + radar */}
          <section className="grid gap-6 rounded-3xl border border-white/8 bg-gradient-to-br from-white/3 to-white/2 p-6 sm:grid-cols-[auto_1fr]">
            <div className="grid place-items-center">
              <CompositeRing value={summary.composite} band={summary.band} />
            </div>
            <div className="grid gap-4">
              <RadarChart summary={summary} />
              <div className="grid grid-cols-2 gap-2 text-[11px] text-white/60 sm:grid-cols-4">
                <StatChip
                  label="Axes with data"
                  value={`${
                    Object.values(summary.axes).filter(a => a.score !== null).length
                  }/${AXES.length}`}
                />
                <StatChip
                  label="Coverage"
                  value={`${Math.round(summary.coverage * 100)}%`}
                />
                <StatChip
                  label="Weakest"
                  value={
                    summary.weakest
                      ? summary.axes[summary.weakest].label
                      : '—'
                  }
                />
                <StatChip
                  label="Strongest"
                  value={
                    summary.strongest
                      ? summary.axes[summary.strongest].label
                      : '—'
                  }
                />
              </div>
              <div className="flex flex-wrap gap-2">
                <button
                  onClick={onCopyBrief}
                  className="rounded-full border border-white/15 bg-white/5 px-3 py-1.5 text-[12px] font-medium text-white/80 transition hover:bg-white/10"
                >
                  {copied ? 'Copied ✓' : 'Copy brief'}
                </button>
                <button
                  onClick={onDownloadBrief}
                  className="rounded-full border border-white/15 bg-white/5 px-3 py-1.5 text-[12px] font-medium text-white/80 transition hover:bg-white/10"
                >
                  Download .md
                </button>
                <Link
                  href="/hq"
                  className="rounded-full border border-white/15 bg-white/5 px-3 py-1.5 text-[12px] font-medium text-white/80 transition hover:bg-white/10"
                >
                  Command Center →
                </Link>
              </div>
            </div>
          </section>

          {/* Axis tile grid */}
          <section className="mt-8">
            <div className="mb-3 flex items-baseline justify-between">
              <h2 className="text-[13px] uppercase tracking-[0.25em] text-white/55">
                Axis breakdown
              </h2>
              <span className="text-[11px] text-white/40">
                click a tile to open its source surface
              </span>
            </div>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {AXES.map(axis => (
                <AxisTile key={axis} axis={axis} compass={summary} />
              ))}
            </div>
          </section>

          {/* Advice + notes */}
          <section className="mt-8 grid gap-4 lg:grid-cols-[2fr_1fr]">
            <AdviceCard compass={summary} />
            <div className="rounded-2xl border border-white/8 bg-white/3 p-5">
              <div className="text-[10px] uppercase tracking-[0.25em] text-white/50">
                Notes
              </div>
              {summary.notes.length === 0 ? (
                <div className="mt-2 text-[12px] text-white/50">
                  Full coverage · no exclusions.
                </div>
              ) : (
                <ul className="mt-2 space-y-1.5 text-[12px] text-white/65">
                  {summary.notes.map((n, i) => (
                    <li key={i} className="flex gap-2">
                      <span className="mt-[6px] inline-block h-1 w-1 flex-none rounded-full bg-white/40" />
                      <span className="leading-snug">{n}</span>
                    </li>
                  ))}
                </ul>
              )}
              <div className="mt-4 border-t border-white/8 pt-3 text-[10px] uppercase tracking-widest text-white/40">
                Generated {new Date(summary.generatedAt).toLocaleString()}
              </div>
            </div>
          </section>

          {/* Methodology */}
          <section className="mt-8 rounded-2xl border border-white/6 bg-white/2 p-5 text-[12px] text-white/65">
            <div className="text-[10px] uppercase tracking-[0.25em] text-white/50">
              How Compass scores
            </div>
            <p className="mt-2 leading-relaxed">
              Each axis is derived from the surface that already computes it:
              <b> Funnel</b> from Portfolio, <b> Calibration</b> from Panel ICC,
              <b> Predictiveness</b> from Hindsight&apos;s Pearson, <b> Parity</b>{' '}
              from the peer regression&apos;s z-drift, <b> Signal</b> from
              Verdict&apos;s signalHealth, <b> Channel</b> from Sources&apos; ROI.
              The composite is a weighted mean over axes with data — a fresh
              workspace with no hires won&apos;t crash to 20/100 just because
              Hindsight is empty. Weights: funnel 20 · calibration 15 ·
              predictiveness 15 · parity 10 · signal 15 · channel 10. Band cut-offs
              are <span style={{ color: BAND_HEX.strong }}>75+ strong</span>,{' '}
              <span style={{ color: BAND_HEX.stable }}>55+ stable</span>,{' '}
              <span style={{ color: BAND_HEX.warning }}>35+ warning</span>, else{' '}
              <span style={{ color: BAND_HEX.critical }}>critical</span>.
            </p>
          </section>
        </div>
      ) : (
        <div className="mx-auto max-w-6xl px-4 py-16 text-center text-sm text-white/50">
          Preparing radar…
        </div>
      )}
    </main>
  );
}

function StatChip({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-0.5 rounded-lg border border-white/8 bg-white/3 px-3 py-2">
      <div className="text-[9px] uppercase tracking-widest text-white/45">
        {label}
      </div>
      <div className="text-[13px] font-semibold text-white/90">{value}</div>
    </div>
  );
}
