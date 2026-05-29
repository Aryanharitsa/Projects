'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { useParams } from 'next/navigation';

import { candidates as ALL_CANDIDATES } from '@/data/candidates';
import { getRole, type Role } from '@/lib/roles';
import { buildRubric } from '@/lib/interview';
import {
  computeCalibration,
  buildCalibrationReport,
  ensurePanel,
  getPanel,
  setRating as setRatingLib,
  addInterviewer as addInterviewerLib,
  removeInterviewer as removeInterviewerLib,
  mergeRatings,
  savePanel,
  makeInterviewerId,
  ICC_BAND_LABEL,
  VERDICT_LABEL,
  VERDICT_KICKER,
  VERDICT_HUE,
  CAND_FLAG_LABEL,
  CAND_FLAG_TONE,
  type Panel,
  type RubricLite,
  type CalibrationResult,
} from '@/lib/calibration';
import { buildPanelSeed, seededRatings, type Archetype, type SeedCandidate } from '@/lib/panel_seed';
import CalibrationBias from '@/components/CalibrationBias';
import RankShiftChart from '@/components/RankShiftChart';
import AgreementGrid from '@/components/AgreementGrid';
import PanelDrawer from '@/components/PanelDrawer';

const TONE_RING: Record<string, string> = {
  rose: 'border-rose-400/30 bg-rose-400/10 text-rose-200',
  amber: 'border-amber-400/30 bg-amber-400/10 text-amber-200',
  sky: 'border-sky-400/30 bg-sky-400/10 text-sky-200',
  indigo: 'border-indigo-400/30 bg-indigo-400/10 text-indigo-200',
  emerald: 'border-emerald-400/30 bg-emerald-400/10 text-emerald-200',
  violet: 'border-violet-400/30 bg-violet-400/10 text-violet-200',
  slate: 'border-white/15 bg-white/5 text-white/65',
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

function downloadText(filename: string, body: string, type = 'text/plain') {
  const blob = new Blob([body], { type });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  setTimeout(() => { URL.revokeObjectURL(url); a.remove(); }, 0);
}

export default function CalibrationStudio() {
  const params = useParams<{ id: string }>();
  const id = params?.id;

  const [role, setRole] = useState<Role | null>(null);
  const [panel, setPanel] = useState<Panel | null>(null);
  const [ready, setReady] = useState(false);
  const [selected, setSelected] = useState<{ candidateId: number; dimKey: string } | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [copied, setCopied] = useState(false);

  // Shortlisted candidates resolved against the candidate DB.
  const candData = useMemo(() => {
    if (!role) return [];
    return role.shortlist
      .map(e => ALL_CANDIDATES.find(c => c.id === e.candidateId))
      .filter((c): c is NonNullable<typeof c> => !!c);
  }, [role]);

  const rubric: RubricLite[] = useMemo(() => {
    if (!role) return [];
    return buildRubric(role.plan).map(d => ({ key: d.key, label: d.label, weight: d.weight }));
  }, [role]);

  const seedCands: SeedCandidate[] = useMemo(
    () => candData.map(c => ({ id: c.id, name: c.name, score: c.score })),
    [candData],
  );

  useEffect(() => {
    if (!id) return;
    const r = getRole(id);
    setRole(r);
    setReady(true);
  }, [id]);

  // Seed / load the panel once the role + rubric are ready.
  useEffect(() => {
    if (!role || rubric.length === 0) return;
    if (seedCands.length === 0) { setPanel(getPanel(role.id)); return; }
    const p = ensurePanel(role.id, () => buildPanelSeed(role.id, seedCands, rubric));
    setPanel(p);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [role, rubric.length, seedCands.length]);

  const result: CalibrationResult | null = useMemo(() => {
    if (!role || !panel) return null;
    const lites = candData.map(c => ({ id: c.id, name: c.name, role: c.role, location: c.location }));
    return computeCalibration(panel, lites, rubric);
  }, [role, panel, candData, rubric]);

  // ---- handlers ----
  const onSetRating = (interviewerId: string, candidateId: number, dimKey: string, rating: number) => {
    if (!role) return;
    setPanel(setRatingLib(role.id, interviewerId, candidateId, dimKey, rating));
  };

  const onAddInterviewer = (name: string, title: string, archetype: Archetype) => {
    if (!role) return;
    const ivId = makeInterviewerId();
    addInterviewerLib(role.id, { id: ivId, name, title });
    const ratings = seededRatings(role.id, ivId, archetype, seedCands, rubric);
    setPanel(mergeRatings(role.id, ratings));
  };

  const onRemoveInterviewer = (interviewerId: string) => {
    if (!role) return;
    setPanel(removeInterviewerLib(role.id, interviewerId));
  };

  const onResetPanel = () => {
    if (!role) return;
    const fresh = buildPanelSeed(role.id, seedCands, rubric);
    savePanel(fresh);
    setPanel(fresh);
    setSelected(null);
  };

  const onCopyReport = async () => {
    if (!role || !result) return;
    await copyToClipboard(buildCalibrationReport(role.name, result));
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  const onExportReport = () => {
    if (!role || !result) return;
    const md = buildCalibrationReport(role.name, result);
    const safe = role.name.replace(/[^a-z0-9]+/gi, '_');
    downloadText(`calibration_${safe}.md`, md, 'text/markdown');
  };

  if (!ready) {
    return (
      <main className="min-h-screen bg-gradient-to-b from-[#0b0b12] to-black text-white">
        <div className="mx-auto max-w-6xl px-4 py-12 text-white/50">Loading…</div>
      </main>
    );
  }

  if (!role) {
    return (
      <main className="min-h-screen bg-gradient-to-b from-[#0b0b12] to-black text-white">
        <div className="mx-auto max-w-6xl px-4 py-12 text-center">
          <h1 className="text-2xl font-semibold">Role not found</h1>
          <Link href="/roles" className="mt-6 inline-block rounded-lg bg-indigo-500 px-4 py-2 text-sm font-medium text-black hover:bg-indigo-400">
            Back to roles
          </Link>
        </div>
      </main>
    );
  }

  const verdictHue = result ? VERDICT_HUE[result.verdict] : '#fff';

  return (
    <main className="min-h-screen bg-gradient-to-b from-[#0b0b12] to-black text-white">
      <div className="mx-auto max-w-6xl px-4 pb-24">
        <header className="flex items-center justify-between py-6">
          <Link href={`/roles/${role.id}`} className="text-sm text-white/60 hover:text-white">
            ← {role.name}
          </Link>
          <nav className="flex items-center gap-6 text-sm text-white/80">
            <Link href="/" className="hover:text-white">Discover</Link>
            <Link href="/roles" className="hover:text-white">Roles</Link>
            <Link href="/hq" className="hover:text-white">Command Center</Link>
          </nav>
        </header>

        {/* Title + actions */}
        <section className="mt-2 flex flex-wrap items-end justify-between gap-4">
          <div className="min-w-0 flex-1">
            <div className="text-[11px] uppercase tracking-wider text-fuchsia-300/80">
              Calibration Studio
            </div>
            <h1 className="mt-1 text-3xl font-semibold md:text-4xl">{role.name}</h1>
            <p className="mt-2 max-w-2xl text-sm text-white/60">
              Measure rater bias across the panel, score inter-rater reliability,
              and re-rank candidates with systematic leniency removed — so a hire
              isn&apos;t an accident of <em>who</em> happened to interview them.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <button
              onClick={() => setDrawerOpen(true)}
              className="rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-xs text-white hover:bg-white/10"
            >
              Manage panel
            </button>
            <button
              onClick={onCopyReport}
              disabled={!result || result.raters.length === 0}
              className="rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-xs text-white hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {copied ? 'Copied ✓' : 'Copy report'}
            </button>
            <button
              onClick={onExportReport}
              disabled={!result || result.raters.length === 0}
              className="rounded-lg bg-gradient-to-r from-fuchsia-400 to-sky-400 px-3 py-2 text-xs font-semibold text-black hover:opacity-95 disabled:cursor-not-allowed disabled:from-white/10 disabled:to-white/10 disabled:text-white/40"
            >
              Export report.md
            </button>
          </div>
        </section>

        {seedCands.length === 0 ? (
          <div className="mt-10 rounded-2xl border border-dashed border-white/10 bg-white/[0.02] p-10 text-center">
            <div className="text-lg font-semibold text-white">No candidates to calibrate yet</div>
            <p className="mx-auto mt-2 max-w-md text-sm text-white/55">
              Calibration needs a shortlist — add candidates to this role, then the
              studio seeds a panel and audits how consistently they were scored.
            </p>
            <Link
              href={`/roles/${role.id}`}
              className="mt-5 inline-block rounded-lg bg-gradient-to-r from-fuchsia-400 to-sky-400 px-4 py-2 text-sm font-semibold text-black hover:opacity-95"
            >
              Back to the role
            </Link>
          </div>
        ) : result ? (
          <>
            {/* Headline */}
            <section className="mt-6 grid gap-3 md:grid-cols-5">
              <div
                className="cc-cal-verdict rounded-xl border p-3 md:col-span-2"
                style={{ borderColor: `${verdictHue}55`, background: `${verdictHue}14` }}
              >
                <div className="text-[10px] uppercase tracking-wider text-white/55">Panel verdict</div>
                <div className="mt-1 text-lg font-semibold" style={{ color: verdictHue }}>
                  {VERDICT_LABEL[result.verdict].split(' · ')[0]}
                </div>
                <div className="mt-0.5 text-[11px] text-white/60">{VERDICT_KICKER[result.verdict]}</div>
              </div>
              <Tile
                label="Consensus index"
                value={result.consensusIndex === null ? '—' : `${(result.consensusIndex * 100).toFixed(0)}%`}
                detail="cell-level agreement"
                tone="sky"
              />
              <Tile
                label="Reliability (ICC)"
                value={result.icc === null ? '—' : result.icc.toFixed(2)}
                detail={
                  result.icc !== null && result.iccCalibrated !== null
                    ? `→ ${result.iccCalibrated.toFixed(2)} de-biased`
                    : (result.iccBand ? ICC_BAND_LABEL[result.iccBand] : 'needs overlap')
                }
                tone="violet"
              />
              <Tile
                label="Rank shifts"
                value={String(result.rankShiftCount)}
                detail={`${result.biasedRaters} biased rater${result.biasedRaters === 1 ? '' : 's'}`}
                tone={result.rankShiftCount > 0 ? 'amber' : 'emerald'}
              />
            </section>

            {/* Bias + Rank shift */}
            <section className="mt-6 grid gap-6 lg:grid-cols-2">
              <div>
                <div className="mb-3 text-[11px] uppercase tracking-wider text-white/45">
                  Interviewer calibration
                </div>
                <CalibrationBias raters={result.raters} />
              </div>
              <div>
                <div className="mb-3 text-[11px] uppercase tracking-wider text-white/45">
                  Ranking impact
                </div>
                <RankShiftChart candidates={result.candidates} />
              </div>
            </section>

            {/* Agreement grid */}
            <section className="mt-8">
              <AgreementGrid
                cells={result.cells}
                candidates={result.candidates.map(c => ({ id: c.candidateId, name: c.name }))}
                rubric={rubric}
                interviewers={panel?.interviewers ?? []}
                selected={selected}
                onSelectCell={(cid, dk) => setSelected({ candidateId: cid, dimKey: dk })}
                onSetRating={onSetRating}
              />
            </section>

            {/* Hot cells + suggestions */}
            <section className="mt-8 grid gap-6 lg:grid-cols-2">
              <div className="cc-cal-hot rounded-2xl border border-white/10 bg-white/[0.03] p-4">
                <div className="text-[11px] uppercase tracking-wider text-white/45">
                  Disagreement hot-cells
                </div>
                <div className="mt-1 text-[11px] text-white/55">
                  Biggest panel splits — discuss before deciding
                </div>
                <div className="mt-3 space-y-2">
                  {result.hotCells.length === 0 && (
                    <div className="text-sm text-white/45">No major splits — the panel broadly agrees per cell.</div>
                  )}
                  {result.hotCells.map(h => (
                    <button
                      key={`${h.candidateId}|${h.dimKey}`}
                      type="button"
                      onClick={() => setSelected({ candidateId: h.candidateId, dimKey: h.dimKey })}
                      className="cc-cal-hotrow flex w-full items-center justify-between gap-2 rounded-lg border border-white/8 bg-white/[0.02] px-3 py-2 text-left hover:bg-white/[0.05]"
                    >
                      <div className="min-w-0">
                        <div className="truncate text-[12px] text-white/85">
                          {h.candidateName} <span className="text-white/40">·</span> {h.dimLabel}
                        </div>
                        <div className="mt-0.5 flex flex-wrap gap-1">
                          {h.ratings.map(r => (
                            <span key={r.interviewerId} className="rounded-full border border-white/10 bg-white/5 px-1.5 py-0.5 text-[10px] text-white/65">
                              {r.name.split(' ')[0]} {r.rating}
                            </span>
                          ))}
                        </div>
                      </div>
                      <span className="shrink-0 rounded-full border border-rose-400/30 bg-rose-400/10 px-2 py-0.5 text-[10px] text-rose-200">
                        range {h.range}
                      </span>
                    </button>
                  ))}
                </div>
              </div>

              <div className="cc-cal-actions rounded-2xl border border-white/10 bg-white/[0.03] p-4">
                <div className="text-[11px] uppercase tracking-wider text-white/45">
                  Recommended actions
                </div>
                <ul className="mt-3 space-y-2">
                  {result.suggestions.map((s, i) => (
                    <li key={i} className="flex gap-2 text-[12px] text-white/80">
                      <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-fuchsia-300/70" />
                      <span>{s}</span>
                    </li>
                  ))}
                </ul>
                {result.notes.length > 0 && (
                  <div className="mt-3 space-y-1 border-t border-white/8 pt-3">
                    {result.notes.map((nt, i) => (
                      <div key={i} className="text-[11px] text-white/45">{nt}</div>
                    ))}
                  </div>
                )}
                {/* per-candidate flags summary */}
                {result.candidates.some(c => c.flags.length > 0) && (
                  <div className="mt-3 border-t border-white/8 pt-3">
                    <div className="text-[10px] uppercase tracking-wider text-white/40">Candidate flags</div>
                    <div className="mt-1.5 flex flex-wrap gap-1.5">
                      {result.candidates.flatMap(c =>
                        c.flags.map(f => (
                          <span
                            key={`${c.candidateId}-${f}`}
                            className={`rounded-full border px-2 py-0.5 text-[10px] ${TONE_RING[CAND_FLAG_TONE[f]]}`}
                          >
                            {c.name.split(' ')[0]}: {CAND_FLAG_LABEL[f]}
                          </span>
                        )),
                      )}
                    </div>
                  </div>
                )}
              </div>
            </section>
          </>
        ) : null}
      </div>

      <PanelDrawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        raters={result?.raters ?? []}
        onRemove={onRemoveInterviewer}
        onAdd={onAddInterviewer}
        onReset={onResetPanel}
      />
    </main>
  );
}

function Tile({ label, value, detail, tone }: { label: string; value: string; detail: string; tone: string }) {
  return (
    <div className={`cc-tile rounded-xl border p-3 ${TONE_RING[tone]}`}>
      <div className="text-[10px] uppercase tracking-wider opacity-70">{label}</div>
      <div className="mt-1 truncate text-lg font-semibold">{value}</div>
      <div className="mt-0.5 truncate text-[11px] opacity-65">{detail}</div>
    </div>
  );
}
