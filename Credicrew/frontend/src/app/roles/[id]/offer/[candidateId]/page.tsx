'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import { useParams } from 'next/navigation';

import { candidates } from '@/data/candidates';
import { matchCandidate } from '@/lib/match';
import { getRole, type Role } from '@/lib/roles';
import {
  listInterviewsForRole,
  summarise,
  type InterviewRecord,
  type ScorecardSummary,
} from '@/lib/interview';
import {
  bandPosition,
  benchmarkComp,
  buildOfferLetter,
  getOffer,
  saveOffer,
  suggestDraft,
  winProbability,
  type CompBenchmark,
  type OfferDraft,
  BAND_HUE,
  BAND_LABEL,
} from '@/lib/offer';
import { buildCalendar } from '@/lib/ics';
import CompLadder, { fmtMoney } from '@/components/CompLadder';
import WinProbabilityDial, { FactorBars } from '@/components/WinProbabilityDial';
import OfferLetterPreview from '@/components/OfferLetterPreview';

const TONE_RING: Record<string, string> = {
  rose: 'border-rose-400/30 bg-rose-400/10 text-rose-200',
  amber: 'border-amber-400/30 bg-amber-400/10 text-amber-200',
  sky: 'border-sky-400/30 bg-sky-400/10 text-sky-200',
  indigo: 'border-indigo-400/30 bg-indigo-400/10 text-indigo-200',
  emerald: 'border-emerald-400/30 bg-emerald-400/10 text-emerald-200',
  violet: 'border-violet-400/30 bg-violet-400/10 text-violet-200',
  teal: 'border-teal-400/30 bg-teal-400/10 text-teal-200',
  slate: 'border-white/15 bg-white/5 text-white/65',
};

function downloadText(filename: string, body: string, type = 'text/plain') {
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

function copy(s: string): Promise<void> {
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

function isoDateAfterDays(d: number): string {
  const dt = new Date();
  dt.setDate(dt.getDate() + d);
  return dt.toISOString().slice(0, 10);
}

function daysBetween(iso: string | undefined): number | undefined {
  if (!iso) return undefined;
  const dt = new Date(iso);
  if (isNaN(dt.getTime())) return undefined;
  return Math.max(0, Math.round((Date.now() - dt.getTime()) / (1000 * 60 * 60 * 24)));
}

export default function OfferStudio() {
  const params = useParams<{ id: string; candidateId: string }>();
  const roleId = params?.id;
  const candidateId = Number(params?.candidateId);

  const [role, setRole] = useState<Role | null>(null);
  const [ready, setReady] = useState(false);
  const [interview, setInterview] = useState<InterviewRecord | null>(null);
  const [draft, setDraft] = useState<OfferDraft | null>(null);
  const [companyName, setCompanyName] = useState('Your Company');
  const [hiringManager, setHiringManager] = useState('');
  const [copiedLetter, setCopiedLetter] = useState(false);
  const [savedFlash, setSavedFlash] = useState(false);
  const initRef = useRef(false);

  useEffect(() => {
    if (!roleId) return;
    const r = getRole(roleId);
    setRole(r);
    if (r) {
      const ivs = listInterviewsForRole(r.id);
      setInterview(ivs.find(x => x.candidateId === candidateId) ?? null);
    }
    setReady(true);
  }, [roleId, candidateId]);

  const candidate = useMemo(
    () => candidates.find(c => c.id === candidateId) ?? null,
    [candidateId],
  );

  const match = useMemo(() => {
    if (!role) return null;
    if (!candidate) {
      return matchCandidate(role.plan, { name: `Candidate #${candidateId}` });
    }
    return matchCandidate(role.plan, candidate);
  }, [role, candidate, candidateId]);

  const benchmark: CompBenchmark | null = useMemo(() => {
    if (!role || !match) return null;
    return benchmarkComp(role.plan, match.matchedSkills);
  }, [role, match]);

  // Load existing draft or generate suggestion
  useEffect(() => {
    if (initRef.current) return;
    if (!ready || !role || !benchmark) return;
    const saved = getOffer(role.id, candidateId);
    if (saved) {
      setDraft(saved);
    } else {
      setDraft({
        ...suggestDraft(benchmark),
        startDate: isoDateAfterDays(28),
        expiresOn: isoDateAfterDays(14),
      });
    }
    initRef.current = true;
  }, [ready, role, benchmark, candidateId]);

  // Persist on draft change (debounced via micro-task)
  useEffect(() => {
    if (!role || !draft) return;
    saveOffer(role.id, candidateId, draft);
    setSavedFlash(true);
    const t = window.setTimeout(() => setSavedFlash(false), 700);
    return () => window.clearTimeout(t);
  }, [role, draft, candidateId]);

  const interviewSummary: ScorecardSummary | null = useMemo(() => {
    if (!interview) return null;
    const s = summarise(interview);
    return s.ratedCount > 0 ? s : null;
  }, [interview]);

  const win = useMemo(() => {
    if (!benchmark || !draft || !match) return null;
    const status = role?.shortlist.find(e => e.candidateId === candidateId);
    return winProbability(draft, benchmark, {
      composite: interviewSummary?.composite ?? null,
      matchScore: match.score,
      matchedSkills: match.matchedSkills,
      daysSinceOutreach: status ? daysBetween(new Date(status.addedAt).toISOString()) : undefined,
      thinData: (() => {
        if (!interview) return false;
        const totalCount = interview.rubric.length;
        const ratedCount = interviewSummary?.ratedCount ?? 0;
        return totalCount > 0 ? ratedCount / totalCount < 0.35 : false;
      })(),
      lowConfidence: (() => {
        if (!interview) return false;
        const totalCount = interview.rubric.length;
        const ratedCount = interviewSummary?.ratedCount ?? 0;
        return totalCount > 0 && ratedCount / totalCount >= 0.35 && ratedCount / totalCount < 0.6;
      })(),
    });
  }, [benchmark, draft, match, interviewSummary, role, candidateId, interview]);

  const letterMd = useMemo(() => {
    if (!role || !draft || !benchmark || !candidate) return '';
    return buildOfferLetter({
      companyName,
      hiringManager: hiringManager || undefined,
      candidateName: candidate.name,
      roleName: role.name,
      location: role.plan.location ?? candidate.location ?? 'India',
      offer: draft,
      benchmark,
    });
  }, [role, draft, benchmark, candidate, companyName, hiringManager]);

  const onDownloadLetter = useCallback(() => {
    if (!role || !candidate) return;
    const safe = `${role.name}_${candidate.name}`.replace(/[^a-z0-9]+/gi, '_');
    downloadText(`offer_${safe}.md`, letterMd, 'text/markdown');
  }, [role, candidate, letterMd]);

  const onCopyLetter = useCallback(async () => {
    await copy(letterMd);
    setCopiedLetter(true);
    setTimeout(() => setCopiedLetter(false), 1500);
  }, [letterMd]);

  const onPrint = useCallback(() => {
    if (typeof window === 'undefined') return;
    window.print();
  }, []);

  const onDownloadExpiryIcs = useCallback(() => {
    if (!role || !candidate || !draft?.expiresOn || !benchmark) return;
    const expiresAt = new Date(draft.expiresOn + 'T17:00:00').getTime();
    const ics = buildCalendar([{
      startUtcMs: expiresAt,
      durationMin: 60,
      summary: `Offer expires — ${candidate.name} (${role.name})`,
      description: `${role.name} offer to ${candidate.name} expires today. Base ${
        fmtMoney(draft.base, benchmark.base.unit, benchmark.base.currency)
      }, equity ${draft.equityPct.toFixed(3)}%. Win probability: ${
        win ? Math.round(win.probability * 100) + '%' : 'n/a'
      }.`,
      location: role.plan.location ?? '',
      organizer: hiringManager ? { name: hiringManager } : undefined,
    }]);
    const safe = `${role.name}_${candidate.name}`.replace(/[^a-z0-9]+/gi, '_');
    downloadText(`offer_expiry_${safe}.ics`, ics, 'text/calendar; charset=utf-8');
  }, [role, candidate, draft, benchmark, win, hiringManager]);

  const onReset = useCallback(() => {
    if (!benchmark) return;
    setDraft({
      ...suggestDraft(benchmark),
      startDate: isoDateAfterDays(28),
      expiresOn: isoDateAfterDays(14),
    });
  }, [benchmark]);

  if (!ready) {
    return (
      <main className="min-h-screen bg-gradient-to-b from-[#0b0b12] to-black text-white">
        <div className="mx-auto max-w-6xl px-4 py-12 text-white/50">Loading…</div>
      </main>
    );
  }

  if (!role || !candidate) {
    return (
      <main className="min-h-screen bg-gradient-to-b from-[#0b0b12] to-black text-white">
        <div className="mx-auto max-w-6xl px-4 py-12 text-center">
          <h1 className="text-2xl font-semibold">Offer not available</h1>
          <p className="mt-2 text-white/55">{role ? 'Candidate' : 'Role'} not found.</p>
          <Link
            href={role ? `/roles/${role.id}` : '/roles'}
            className="mt-6 inline-block rounded-lg bg-indigo-500 px-4 py-2 text-sm font-medium text-black hover:bg-indigo-400"
          >
            Back
          </Link>
        </div>
      </main>
    );
  }

  if (!draft || !benchmark || !win || !match) return null;

  const pos = bandPosition(draft, benchmark);
  const equityValueRange = (() => {
    // Implied company valuation @ Series A signal: ₹40Cr / 0.18% senior P50.
    // (Just a stable scaling so the equity value is intelligible.)
    const anchorPct = Math.max(0.001, benchmark.equity.pct_p50);
    const anchorValueLPA = benchmark.base.p50 * 1.2;
    const equityLPA = (draft.equityPct / anchorPct) * anchorValueLPA;
    return equityLPA;
  })();

  const totalP50 = draft.base + (draft.base * draft.targetBonusPct / 100) + draft.signOn;

  return (
    <main className="min-h-screen bg-gradient-to-b from-[#0b0b12] to-black text-white">
      <div className="mx-auto max-w-6xl px-4 pb-24">
        <header className="flex items-center justify-between py-6">
          <Link
            href={`/roles/${role.id}/decision`}
            className="text-sm text-white/60 hover:text-white"
          >
            ← Decision Studio
          </Link>
          <nav className="flex items-center gap-6 text-sm text-white/80">
            <Link href={`/roles/${role.id}`} className="hover:text-white">Role</Link>
            <Link href="/roles" className="hover:text-white">Roles</Link>
            <Link href="/" className="hover:text-white">Discover</Link>
          </nav>
        </header>

        {/* Title row */}
        <section className="mt-2 flex flex-wrap items-end justify-between gap-4">
          <div className="min-w-0 flex-1">
            <div className="text-[11px] uppercase tracking-wider text-emerald-300/85">
              Offer Studio
            </div>
            <h1 className="mt-1 text-3xl font-semibold md:text-4xl">{candidate.name}</h1>
            <p className="mt-2 max-w-2xl text-sm text-white/60">
              Calibrated comp band, explainable win-probability simulator, and
              a print-ready offer letter — all one click away. Draft auto-saves
              as you tune sliders.
              {savedFlash && <span className="ml-2 text-[11px] text-emerald-300/85">saved ✓</span>}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2 print:hidden">
            <button
              onClick={onCopyLetter}
              className="rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-xs text-white hover:bg-white/10"
            >
              {copiedLetter ? 'Copied ✓' : 'Copy letter'}
            </button>
            <button
              onClick={onDownloadLetter}
              className="rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-xs text-white hover:bg-white/10"
            >
              Download .md
            </button>
            <button
              onClick={onDownloadExpiryIcs}
              disabled={!draft.expiresOn}
              className="rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-xs text-white hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-40"
              title={draft.expiresOn ? 'Calendar event for expiry' : 'Set an expiry first'}
            >
              .ics expiry
            </button>
            <button
              onClick={onPrint}
              className="rounded-lg bg-gradient-to-r from-emerald-400 to-violet-400 px-3 py-2 text-xs font-semibold text-black hover:opacity-95"
            >
              Print / PDF
            </button>
          </div>
        </section>

        {/* Headline tiles */}
        <section className="mt-6 grid gap-3 md:grid-cols-4">
          <Tile
            label="Accept probability"
            value={`${Math.round(win.probability * 100)}%`}
            detail={BAND_LABEL[win.band]}
            tone={win.band === 'lock' ? 'emerald' : win.band === 'likely' ? 'violet' : win.band === 'coin_flip' ? 'amber' : 'rose'}
          />
          <Tile
            label="Base salary"
            value={fmtMoney(draft.base, benchmark.base.unit, benchmark.base.currency)}
            detail={
              pos < 0
                ? 'below P25 — below market'
                : pos < 0.25
                ? 'P25 — entry of band'
                : pos < 0.55
                ? 'P50 — middle of band'
                : pos < 0.85
                ? 'P75 — top quartile'
                : pos <= 1
                ? 'P90 — top tail'
                : 'above P90 — premium'
            }
            tone="indigo"
          />
          <Tile
            label="Total comp (P50)"
            value={fmtMoney(totalP50, benchmark.base.unit, benchmark.base.currency)}
            detail={`base + ${draft.targetBonusPct.toFixed(0)}% bonus + sign-on`}
            tone="violet"
          />
          <Tile
            label="Equity grant"
            value={`${draft.equityPct.toFixed(3)}%`}
            detail={`≈ ${fmtMoney(equityValueRange, 'LPA', 'INR')} value-equivalent`}
            tone="teal"
          />
        </section>

        {/* Main 2-col */}
        <section className="mt-8 grid gap-6 lg:grid-cols-12 print:hidden">
          {/* LEFT — band ladder + sliders */}
          <div className="space-y-6 lg:col-span-5">
            <CompLadder benchmark={benchmark} offer={draft} />

            <div className="cc-controls rounded-2xl border border-white/10 bg-white/[0.03] p-5">
              <div className="flex items-center justify-between">
                <div>
                  <div className="text-[10px] uppercase tracking-wider text-white/45">
                    Tune the offer
                  </div>
                  <div className="text-base font-semibold">Live counterfactual</div>
                </div>
                <button
                  onClick={onReset}
                  className="rounded-md border border-white/10 bg-white/5 px-2 py-1 text-[10px] text-white/65 hover:bg-white/10"
                >
                  Reset to suggested
                </button>
              </div>

              <Slider
                label="Base salary"
                min={Math.round(benchmark.base.p25 * 0.7)}
                max={Math.round(benchmark.base.p90 * 1.15)}
                step={1}
                value={Math.round(draft.base)}
                fmt={v => fmtMoney(v, benchmark.base.unit, benchmark.base.currency)}
                onChange={v => setDraft({ ...draft, base: v })}
                markers={[
                  { v: benchmark.base.p25, label: 'P25' },
                  { v: benchmark.base.p50, label: 'P50' },
                  { v: benchmark.base.p75, label: 'P75' },
                  { v: benchmark.base.p90, label: 'P90' },
                ]}
              />
              <Slider
                label="Equity (% of company)"
                min={0}
                max={Math.max(0.05, benchmark.equity.pct_p75 * 1.5)}
                step={0.01}
                value={Math.round(draft.equityPct * 100) / 100}
                fmt={v => `${v.toFixed(2)}%`}
                onChange={v => setDraft({ ...draft, equityPct: Math.round(v * 1000) / 1000 })}
                markers={[
                  { v: benchmark.equity.pct_p25, label: 'P25' },
                  { v: benchmark.equity.pct_p50, label: 'P50' },
                  { v: benchmark.equity.pct_p75, label: 'P75' },
                ]}
              />
              <Slider
                label="Sign-on bonus"
                min={0}
                max={Math.round(benchmark.base.p50 * 0.25)}
                step={1}
                value={Math.round(draft.signOn)}
                fmt={v => fmtMoney(v, benchmark.base.unit, benchmark.base.currency)}
                onChange={v => setDraft({ ...draft, signOn: v })}
                markers={[
                  { v: benchmark.signOnSuggested, label: 'Suggested' },
                ]}
              />
              <Slider
                label="Target bonus %"
                min={0}
                max={30}
                step={1}
                value={Math.round(draft.targetBonusPct)}
                fmt={v => `${v}%`}
                onChange={v => setDraft({ ...draft, targetBonusPct: v })}
                markers={[
                  { v: benchmark.targetBonusPct, label: 'Market' },
                ]}
              />

              <div className="mt-4 grid grid-cols-2 gap-3">
                <LabeledInput
                  label="Start date"
                  type="date"
                  value={draft.startDate ?? ''}
                  onChange={v => setDraft({ ...draft, startDate: v || undefined })}
                />
                <LabeledInput
                  label="Offer expires"
                  type="date"
                  value={draft.expiresOn ?? ''}
                  onChange={v => setDraft({ ...draft, expiresOn: v || undefined })}
                />
                <LabeledInput
                  label="Vesting years"
                  type="number"
                  value={String(draft.vestingYears)}
                  onChange={v => setDraft({ ...draft, vestingYears: Math.max(1, Math.min(6, Number(v) || 4)) })}
                />
                <LabeledInput
                  label="Cliff (months)"
                  type="number"
                  value={String(draft.cliffMonths)}
                  onChange={v => setDraft({ ...draft, cliffMonths: Math.max(0, Math.min(24, Number(v) || 12)) })}
                />
                <LabeledInput
                  label="Company name"
                  type="text"
                  value={companyName}
                  onChange={v => setCompanyName(v)}
                />
                <LabeledInput
                  label="Hiring manager"
                  type="text"
                  value={hiringManager}
                  onChange={v => setHiringManager(v)}
                />
              </div>

              <div className="mt-3">
                <div className="mb-1 text-[10px] uppercase tracking-wider text-white/45">
                  Notes (appended to letter)
                </div>
                <textarea
                  className="w-full rounded-lg border border-white/10 bg-black/20 p-2 text-[12px] text-white outline-none focus:border-violet-400/40"
                  rows={3}
                  value={draft.notes ?? ''}
                  onChange={e => setDraft({ ...draft, notes: e.target.value })}
                  placeholder="Optional: relocation support, work-from-anywhere policy, etc."
                />
              </div>
            </div>
          </div>

          {/* RIGHT — dial + factor stack */}
          <div className="space-y-6 lg:col-span-7">
            <div
              className="rounded-2xl border border-white/10 bg-white/[0.03] p-5"
              style={{
                background:
                  'radial-gradient(at top right, rgba(167,139,250,0.07), transparent 60%), rgba(255,255,255,0.03)',
              }}
            >
              <div className="grid items-center gap-6 md:grid-cols-[260px_minmax(0,1fr)]">
                <WinProbabilityDial win={win} size={240} />
                <div>
                  <div className="text-[10px] uppercase tracking-wider text-white/45">
                    What&apos;s moving the dial
                  </div>
                  <FactorBars win={win} />
                  <div className="mt-3 text-[11px] text-white/55">
                    Logistic model — each factor adds to <code className="rounded bg-white/8 px-1 font-mono text-[10px]">logit</code>.
                    Final probability = σ(logit). Drag sliders to see the
                    factors recompute live.
                  </div>
                </div>
              </div>
            </div>

            <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-5">
              <div className="flex flex-wrap items-end justify-between gap-3">
                <div>
                  <div className="text-[10px] uppercase tracking-wider text-white/45">
                    Candidate signals
                  </div>
                  <div className="text-base font-semibold">
                    {candidate.role} · {candidate.location}
                  </div>
                </div>
                {interviewSummary && (
                  <div
                    className="rounded-lg border px-3 py-1.5 text-[11px]"
                    style={{
                      borderColor: `${BAND_HUE.likely}55`,
                      background: `${BAND_HUE.likely}10`,
                      color: BAND_HUE.likely,
                    }}
                  >
                    composite {interviewSummary.composite} · conf{' '}
                    {interview!.rubric.length > 0
                      ? Math.round((interviewSummary.ratedCount / interview!.rubric.length) * 100)
                      : 0}%
                  </div>
                )}
              </div>
              <div className="mt-3 flex flex-wrap gap-1.5">
                {match.matchedSkills.map(s => (
                  <span key={s} className="rounded-full border border-emerald-400/30 bg-emerald-400/10 px-2 py-0.5 text-[10px] text-emerald-200">
                    ✓ {s}
                  </span>
                ))}
                {match.missingSkills.map(s => (
                  <span key={s} className="rounded-full border border-rose-400/30 bg-rose-400/10 px-2 py-0.5 text-[10px] text-rose-200/70 line-through">
                    {s}
                  </span>
                ))}
              </div>
              <div className="mt-4 grid grid-cols-3 gap-2 text-[11px]">
                <SmallStat label="Match score" value={String(match.score)} />
                <SmallStat
                  label="Interview rated"
                  value={
                    interview
                      ? `${interviewSummary?.ratedCount ?? 0}/${interview.rubric.length}`
                      : '—'
                  }
                />
                <SmallStat
                  label="Days since shortlist"
                  value={(() => {
                    const e = role.shortlist.find(x => x.candidateId === candidateId);
                    if (!e) return '—';
                    return String(daysBetween(new Date(e.addedAt).toISOString()) ?? 0);
                  })()}
                />
              </div>
              {!interviewSummary && (
                <div className="mt-4 rounded-lg border border-dashed border-amber-400/30 bg-amber-400/5 px-3 py-2 text-[11px] text-amber-200/85">
                  No interview composite yet — win-probability uses match score and
                  signals only. Add ratings in the{' '}
                  <Link
                    href={`/roles/${role.id}/interview/${candidate.id}`}
                    className="underline hover:no-underline"
                  >
                    interview workspace
                  </Link>{' '}
                  for a tighter forecast.
                </div>
              )}
            </div>
          </div>
        </section>

        {/* Letter preview */}
        <section className="mt-10">
          <div className="mb-3 flex items-center justify-between print:hidden">
            <div>
              <div className="text-[11px] uppercase tracking-wider text-white/45">
                Print-ready letter
              </div>
              <div className="text-base font-semibold">Offer document preview</div>
            </div>
            <div className="text-[11px] text-white/45">
              Hit Print / PDF for a clean copy.
            </div>
          </div>
          <OfferLetterPreview markdown={letterMd} />
        </section>
      </div>
    </main>
  );
}

function Tile({
  label, value, detail, tone,
}: { label: string; value: string; detail: string; tone: string }) {
  return (
    <div className={`cc-tile rounded-xl border p-3 ${TONE_RING[tone] ?? TONE_RING.slate}`}>
      <div className="text-[10px] uppercase tracking-wider opacity-70">{label}</div>
      <div className="mt-1 truncate text-lg font-semibold">{value}</div>
      <div className="mt-0.5 truncate text-[11px] opacity-65">{detail}</div>
    </div>
  );
}

function SmallStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-white/10 bg-white/[0.03] px-2 py-1.5">
      <div className="text-[9px] uppercase tracking-wider text-white/45">{label}</div>
      <div className="mt-0.5 font-mono text-[12px] text-white">{value}</div>
    </div>
  );
}

type Marker = { v: number; label: string };

function Slider({
  label, min, max, step, value, fmt, onChange, markers,
}: {
  label: string; min: number; max: number; step: number; value: number;
  fmt: (v: number) => string; onChange: (v: number) => void;
  markers?: Marker[];
}) {
  const pct = (value - min) / (max - min) * 100;
  return (
    <div className="mt-4">
      <div className="mb-1 flex items-baseline justify-between">
        <label className="text-[10px] uppercase tracking-wider text-white/45">
          {label}
        </label>
        <span className="font-mono text-[12px] text-white">{fmt(value)}</span>
      </div>
      <div className="relative h-2.5 rounded-full bg-white/8">
        <div
          className="absolute top-0 h-full rounded-full bg-gradient-to-r from-indigo-400 to-emerald-400"
          style={{ width: `${Math.max(0, Math.min(100, pct))}%` }}
        />
        {markers?.map(m => {
          const mp = ((m.v - min) / (max - min)) * 100;
          if (mp < 0 || mp > 100) return null;
          return (
            <div
              key={m.label}
              className="absolute -bottom-3 -translate-x-1/2 text-[8px] text-white/45"
              style={{ left: `${mp}%` }}
            >
              <div className="mb-3 h-2 w-px bg-white/30" />
              <span className="absolute left-0 top-2 -translate-x-1/2 whitespace-nowrap">{m.label}</span>
            </div>
          );
        })}
        <input
          type="range"
          min={min}
          max={max}
          step={step}
          value={value}
          onChange={e => onChange(Number(e.target.value))}
          className="cc-range absolute left-0 right-0 top-0 h-full w-full cursor-pointer appearance-none bg-transparent"
        />
      </div>
    </div>
  );
}

function LabeledInput({
  label, value, onChange, type = 'text',
}: {
  label: string; value: string; onChange: (v: string) => void;
  type?: 'text' | 'date' | 'number';
}) {
  return (
    <label className="block">
      <div className="mb-1 text-[10px] uppercase tracking-wider text-white/45">{label}</div>
      <input
        type={type}
        value={value}
        onChange={e => onChange(e.target.value)}
        className="w-full rounded-md border border-white/10 bg-black/20 px-2 py-1.5 text-[12px] text-white outline-none focus:border-violet-400/40"
      />
    </label>
  );
}
