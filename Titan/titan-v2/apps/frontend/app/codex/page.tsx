"use client";

/*
 * Codex — TITAN's evidence-cited SAR narrative composer (round-19, day-90).
 *
 * Every prior TITAN surface answers "what is the risk here?".  Codex
 * answers the question the compliance officer actually has to file:
 * "what does the paragraph you're about to submit to FinCEN look like,
 *  and does it pass the filing-quality checklist?"
 *
 * Layout — hand-rolled SVG + CSS, zero charting libs:
 *
 *   1. Hero — grade-tinted radial banner, subject chip, band chip,
 *      quality-grade chip, generated-at strip.
 *   2. Toolbar — analyst input, redact toggle, load-case-id lookup,
 *      copy / download markdown, jump-to-section chips.
 *   3. Aggregate tiles — quality score, sections filled, evidence
 *      citations, transactions in scope, inbound / outbound.
 *   4. Three-column grid:
 *        LEFT: evidence library grouped by kind (chips) — hover /
 *              click highlights every citation of that kind in the
 *              narrative.
 *        CENTER: narrative cards, one per section — each with prompt,
 *              paragraph blocks, bullet lists, and inline citation
 *              chips.  Section header shows word count + citation count.
 *        RIGHT: quality checklist — score arc, grade chip, checks
 *              grouped by section with pass/fail, hints for the fails,
 *              and a missing-evidence-kinds strip.
 *   5. Markdown preview — collapsible full-render.
 *   6. Rules footer — engine version + grade ladder + section
 *      vocabulary chips.
 */

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import {
  codexExportUrl,
  composeCodex,
  getCodexRules,
  getCodexSample,
  CodexBlock,
  CodexCitation,
  CodexEvidenceKind,
  CodexNarrative,
  CodexQualityGrade,
  CodexRules,
  CodexSection,
} from "../../lib/api";

// ---------------------------------------------------------------------------
// Palette — grade drives hero tint & score-arc; evidence kind drives chip
// colour so a reader can eye-glance a paragraph and see what it's cited off.
// ---------------------------------------------------------------------------

const GRADE_ACCENT: Record<CodexQualityGrade, string> = {
  publish_ready: "#22d3a8",
  acceptable: "#a5b4fc",
  needs_work: "#fbbf24",
  unfilable: "#f43f5e",
};

const GRADE_BG: Record<CodexQualityGrade, string> = {
  publish_ready:
    "radial-gradient(130% 100% at 50% -10%, rgba(34,211,168,0.22) 0%, rgba(7,11,20,0) 65%)",
  acceptable:
    "radial-gradient(130% 100% at 50% -10%, rgba(165,180,252,0.22) 0%, rgba(7,11,20,0) 65%)",
  needs_work:
    "radial-gradient(130% 100% at 50% -10%, rgba(251,191,36,0.22) 0%, rgba(7,11,20,0) 65%)",
  unfilable:
    "radial-gradient(130% 100% at 50% -10%, rgba(244,63,94,0.24) 0%, rgba(7,11,20,0) 65%)",
};

const BAND_ACCENT: Record<string, string> = {
  low: "#22d3a8",
  medium: "#a5b4fc",
  high: "#fbbf24",
  critical: "#f43f5e",
};

const KIND_ACCENT: Record<string, string> = {
  subject: "#2DE1C2",
  counterparty: "#8B7CFF",
  transaction: "#67e8f9",
  factor: "#fbbf24",
  typology: "#a855f7",
  sanctions: "#f43f5e",
  media: "#fb7185",
  period: "#94a3b8",
  geo: "#38bdf8",
  channel: "#c084fc",
  totals: "#5eead4",
  band: "#f97316",
};

const KIND_LABEL: Record<string, string> = {
  subject: "Subject",
  counterparty: "Counterparty",
  transaction: "Transaction",
  factor: "Detector",
  typology: "Typology",
  sanctions: "Sanctions",
  media: "Adverse media",
  period: "Time bound",
  geo: "Jurisdiction",
  channel: "Channel",
  totals: "Totals",
  band: "Risk band",
};

const SECTION_ORDER = ["who", "what", "when", "where", "why", "how", "action"];

const fmt0 = (n: number) => n.toLocaleString(undefined, { maximumFractionDigits: 0 });
const fmt1 = (n: number) => n.toFixed(1);

function accentFor(kind: string): string {
  return KIND_ACCENT[kind] || "#94a3b8";
}

function kindLabelFor(kind: string): string {
  return KIND_LABEL[kind] || kind;
}

// ---------------------------------------------------------------------------
// Score arc — hand-rolled SVG conic ring used in the checklist panel.
// ---------------------------------------------------------------------------

function ScoreArc({
  score,
  grade,
  size = 168,
}: {
  score: number;
  grade: CodexQualityGrade;
  size?: number;
}) {
  const r = size / 2 - 12;
  const cx = size / 2;
  const cy = size / 2;
  const circ = 2 * Math.PI * r;
  const clamped = Math.max(0, Math.min(100, score));
  const dash = (clamped / 100) * circ;
  const accent = GRADE_ACCENT[grade] || "#94a3b8";
  return (
    <svg viewBox={`0 0 ${size} ${size}`} width={size} height={size}>
      <defs>
        <linearGradient id="codex-arc" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor={accent} stopOpacity="0.9" />
          <stop offset="1" stopColor={accent} stopOpacity="0.5" />
        </linearGradient>
      </defs>
      <circle
        cx={cx}
        cy={cy}
        r={r}
        stroke="rgba(255,255,255,0.08)"
        strokeWidth={10}
        fill="none"
      />
      <circle
        cx={cx}
        cy={cy}
        r={r}
        stroke="url(#codex-arc)"
        strokeWidth={12}
        strokeLinecap="round"
        fill="none"
        strokeDasharray={`${dash} ${circ - dash}`}
        transform={`rotate(-90 ${cx} ${cy})`}
      />
      <text
        x={cx}
        y={cy - 4}
        textAnchor="middle"
        style={{ fontSize: 30, fontWeight: 700 }}
        className="fill-white"
      >
        {fmt1(clamped)}
      </text>
      <text
        x={cx}
        y={cy + 18}
        textAnchor="middle"
        style={{ fontSize: 11, letterSpacing: "0.14em" }}
        className="fill-white/50 uppercase"
      >
        Quality / 100
      </text>
    </svg>
  );
}

// ---------------------------------------------------------------------------
// Citation chip — kind-tinted inline pill.  Adds `data-cite` so hover on
// the evidence panel can highlight matching chips in the narrative.
// ---------------------------------------------------------------------------

function CitationChip({
  citation,
  activeKind,
  onFocus,
}: {
  citation: CodexCitation;
  activeKind: string | null;
  onFocus: (kind: string) => void;
}) {
  const accent = accentFor(citation.kind);
  const dim = !!activeKind && activeKind !== citation.kind;
  return (
    <span
      data-cite-kind={citation.kind}
      data-cite-ref={citation.ref}
      onMouseEnter={() => onFocus(citation.kind)}
      onMouseLeave={() => onFocus("")}
      title={
        (citation.detail || "").length
          ? `${kindLabelFor(citation.kind)} · ${citation.detail}`
          : kindLabelFor(citation.kind)
      }
      className={
        "ml-1 inline-flex items-center gap-1 rounded-md border px-1.5 py-[1px] text-[10.5px] font-mono transition " +
        (dim ? "opacity-30" : "opacity-100")
      }
      style={{
        borderColor: `${accent}55`,
        background: `${accent}18`,
        color: accent,
      }}
    >
      <span
        aria-hidden
        className="inline-block h-1.5 w-1.5 rounded-full"
        style={{ background: accent }}
      />
      {citation.label}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Block renderer — paragraph / bullet list / table, each with citation chips
// spread inline at the end.  The chips carry the semantics; the paragraph
// text stays clean prose.
// ---------------------------------------------------------------------------

function NarrativeBlockView({
  block,
  activeKind,
  onFocus,
}: {
  block: CodexBlock;
  activeKind: string | null;
  onFocus: (kind: string) => void;
}) {
  const chips = block.citations.map((c, i) => (
    <CitationChip
      key={`${c.kind}:${c.ref}:${i}`}
      citation={c}
      activeKind={activeKind}
      onFocus={onFocus}
    />
  ));
  if (block.kind === "table") {
    return (
      <div className="space-y-2">
        {block.text ? (
          <p className="text-[13.5px] leading-relaxed text-white/80">
            {block.text}
          </p>
        ) : null}
        <div className="overflow-x-auto scroll-thin">
          <table className="min-w-full border-separate border-spacing-0 text-[12.5px]">
            <thead>
              <tr>
                {block.columns.map((c) => (
                  <th
                    key={c}
                    className="sticky top-0 z-10 bg-white/[0.06] px-2 py-1.5 text-left text-[10.5px] font-semibold uppercase tracking-wider text-white/60"
                  >
                    {c}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {block.rows.map((row, ri) => (
                <tr key={ri} className="odd:bg-white/[0.02]">
                  {row.map((cell, ci) => (
                    <td
                      key={ci}
                      className="px-2 py-1.5 align-top text-white/85"
                    >
                      {cell}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {chips.length ? (
          <div className="flex flex-wrap items-center gap-1">
            <span className="text-[10.5px] uppercase tracking-widest text-white/40">
              cited:
            </span>
            {chips}
          </div>
        ) : null}
      </div>
    );
  }
  if (block.kind === "bullet_list") {
    return (
      <div className="space-y-2">
        {block.text ? (
          <p className="text-[13.5px] leading-relaxed text-white/80">
            {block.text}
          </p>
        ) : null}
        <ul className="ml-4 list-disc space-y-1 text-[13px] text-white/78">
          {block.items.map((item, i) => (
            <li key={i} dangerouslySetInnerHTML={{ __html: mdInline(item) }} />
          ))}
        </ul>
        {chips.length ? (
          <div className="flex flex-wrap items-center gap-1">
            <span className="text-[10.5px] uppercase tracking-widest text-white/40">
              cited:
            </span>
            {chips}
          </div>
        ) : null}
      </div>
    );
  }
  return (
    <p className="text-[14px] leading-relaxed text-white/85">
      <span dangerouslySetInnerHTML={{ __html: mdInline(block.text) }} />
      {chips}
    </p>
  );
}

// Minimal markdown inliner: `code` and **bold** and *italic* — enough for
// the composer's known-shape blocks, deliberately not a general parser.
function mdInline(s: string): string {
  return (s || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/`([^`]+)`/g, '<code class="rounded bg-white/[0.06] px-1 py-[1px] font-mono text-[12px] text-teal-300">$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong class="text-white">$1</strong>')
    .replace(/\*([^*]+)\*/g, '<em class="text-white/80">$1</em>');
}

// ---------------------------------------------------------------------------
// Section card — one per narrative section, with a section-anchor id so the
// jump-chips in the toolbar scroll to it.
// ---------------------------------------------------------------------------

function SectionCard({
  section,
  activeKind,
  onFocus,
}: {
  section: CodexSection;
  activeKind: string | null;
  onFocus: (kind: string) => void;
}) {
  return (
    <section
      id={`codex-section-${section.id}`}
      className="glass scroll-mt-24 p-5"
    >
      <header className="mb-4 flex items-baseline justify-between border-b border-white/5 pb-3">
        <div>
          <div className="text-[10.5px] uppercase tracking-[0.2em] text-white/45">
            Section {section.number} · {section.id}
          </div>
          <h3 className="mt-0.5 text-lg font-semibold tracking-tight text-white">
            {section.title.replace(/^\d+\.\s*/, "")}
          </h3>
          <p className="mt-1 text-[12px] italic text-white/45">
            {section.prompt}
          </p>
        </div>
        <div className="flex flex-col items-end gap-1 text-[11px] text-white/50">
          <span>{section.word_count} words</span>
          <span>{section.citation_count} citations</span>
        </div>
      </header>
      <div className="space-y-4">
        {section.blocks.length ? (
          section.blocks.map((b, i) => (
            <NarrativeBlockView
              key={i}
              block={b}
              activeKind={activeKind}
              onFocus={onFocus}
            />
          ))
        ) : (
          <p className="text-[13px] italic text-white/45">
            _no content composed for this section — the report was missing
            supporting evidence._
          </p>
        )}
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Evidence library — grouped by kind, chips clickable to focus the narrative.
// ---------------------------------------------------------------------------

function EvidenceLibrary({
  citations,
  activeKind,
  onFocus,
}: {
  citations: CodexCitation[];
  activeKind: string | null;
  onFocus: (kind: string) => void;
}) {
  const grouped = useMemo(() => {
    const map = new Map<string, CodexCitation[]>();
    for (const c of citations) {
      const arr = map.get(c.kind) || [];
      arr.push(c);
      map.set(c.kind, arr);
    }
    return Array.from(map.entries()).sort(
      (a, b) => b[1].length - a[1].length
    );
  }, [citations]);
  return (
    <aside className="glass sticky top-6 max-h-[calc(100vh-3rem)] overflow-y-auto scroll-thin p-4">
      <header className="mb-3 flex items-baseline justify-between border-b border-white/5 pb-2">
        <h4 className="text-[13px] font-semibold tracking-tight text-white">
          Evidence library
        </h4>
        <span className="text-[10.5px] uppercase tracking-widest text-white/40">
          {citations.length} items
        </span>
      </header>
      <p className="mb-3 text-[11.5px] leading-relaxed text-white/50">
        Hover any chip below to highlight every place it&apos;s cited in
        the narrative on the right.
      </p>
      <div className="space-y-3">
        {grouped.map(([kind, items]) => {
          const accent = accentFor(kind);
          const dim = !!activeKind && activeKind !== kind;
          return (
            <div
              key={kind}
              onMouseEnter={() => onFocus(kind)}
              onMouseLeave={() => onFocus("")}
              className={
                "rounded-xl border p-2 transition " +
                (dim ? "opacity-40" : "opacity-100")
              }
              style={{
                borderColor: `${accent}30`,
                background: `${accent}0d`,
              }}
            >
              <div className="mb-1.5 flex items-baseline justify-between">
                <span
                  className="text-[11.5px] font-semibold uppercase tracking-wider"
                  style={{ color: accent }}
                >
                  {kindLabelFor(kind)}
                </span>
                <span className="text-[10.5px] text-white/45">
                  ×{items.length}
                </span>
              </div>
              <ul className="flex flex-wrap gap-1">
                {items.slice(0, 12).map((c, i) => (
                  <li
                    key={`${c.ref}:${i}`}
                    title={c.detail || c.label}
                    className="max-w-full truncate rounded-md border px-1.5 py-[1px] font-mono text-[10.5px]"
                    style={{
                      borderColor: `${accent}55`,
                      color: accent,
                    }}
                  >
                    {c.label}
                  </li>
                ))}
                {items.length > 12 ? (
                  <li className="text-[10.5px] text-white/45">
                    …+{items.length - 12}
                  </li>
                ) : null}
              </ul>
            </div>
          );
        })}
      </div>
    </aside>
  );
}

// ---------------------------------------------------------------------------
// Quality panel — score arc, grade chip, per-section pass/fail, missing kinds.
// ---------------------------------------------------------------------------

function QualityPanel({
  codex,
  onJumpToSection,
}: {
  codex: CodexNarrative;
  onJumpToSection: (id: string) => void;
}) {
  const q = codex.quality;
  const grouped = useMemo(() => {
    const map = new Map<string, typeof q.checks>();
    for (const c of q.checks) {
      const arr = map.get(c.section) || [];
      arr.push(c);
      map.set(c.section, arr);
    }
    return Array.from(map.entries()).sort(
      ([a], [b]) =>
        SECTION_ORDER.indexOf(a) - SECTION_ORDER.indexOf(b) ||
        a.localeCompare(b)
    );
  }, [q.checks]);
  return (
    <aside className="glass sticky top-6 max-h-[calc(100vh-3rem)] overflow-y-auto scroll-thin p-4">
      <header className="mb-3 flex items-baseline justify-between border-b border-white/5 pb-2">
        <h4 className="text-[13px] font-semibold tracking-tight text-white">
          FinCEN 5W checklist
        </h4>
        <span className="pill" style={{ borderColor: `${GRADE_ACCENT[q.grade]}55`, color: GRADE_ACCENT[q.grade] }}>
          {q.grade_label}
        </span>
      </header>
      <div className="flex justify-center">
        <ScoreArc score={q.score} grade={q.grade} />
      </div>
      <p className="mt-2 text-center text-[12px] leading-relaxed text-white/60">
        {q.grade_detail}
      </p>
      <div className="mt-4 grid grid-cols-2 gap-2 text-center text-[11px]">
        <div className="rounded-lg border border-teal-400/30 bg-teal-500/[0.06] py-2">
          <div className="font-mono text-lg text-teal-300">{q.passed}</div>
          <div className="uppercase tracking-widest text-white/50">Passed</div>
        </div>
        <div className="rounded-lg border border-rose-400/30 bg-rose-500/[0.06] py-2">
          <div className="font-mono text-lg text-rose-300">{q.failed}</div>
          <div className="uppercase tracking-widest text-white/50">Failed</div>
        </div>
      </div>
      <div className="mt-4 space-y-3">
        {grouped.map(([sectionId, checks]) => {
          const sec = codex.sections.find((s) => s.id === sectionId);
          return (
            <div key={sectionId} className="rounded-xl border border-white/10 p-2.5">
              <div className="mb-2 flex items-baseline justify-between">
                <button
                  onClick={() => sec && onJumpToSection(sec.id)}
                  className="text-[11.5px] font-semibold uppercase tracking-wider text-white/75 hover:text-teal-300"
                  disabled={!sec}
                >
                  {sec ? sec.title : sectionId.toUpperCase()}
                </button>
                <span className="text-[10.5px] text-white/40">
                  {checks.filter((c) => c.passed).length}/{checks.length}
                </span>
              </div>
              <ul className="space-y-1.5">
                {checks.map((c) => (
                  <li
                    key={c.id}
                    className="flex items-start gap-2 rounded-md px-1.5 py-1"
                    style={{
                      background: c.passed
                        ? "rgba(34,211,168,0.06)"
                        : "rgba(244,63,94,0.07)",
                    }}
                  >
                    <span
                      className="mt-0.5 inline-flex h-4 w-4 flex-shrink-0 items-center justify-center rounded-full text-[10px] font-bold"
                      style={{
                        background: c.passed ? "#22d3a8" : "#f43f5e",
                        color: "#070b14",
                      }}
                    >
                      {c.passed ? "✓" : "!"}
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="text-[12.5px] leading-tight text-white/85">
                        {c.label}{" "}
                        <span className="text-[10.5px] text-white/40">
                          ({c.weight.toFixed(1)})
                        </span>
                      </div>
                      <div className="mt-0.5 text-[11px] leading-snug text-white/55">
                        {c.detail}
                      </div>
                      {!c.passed && c.hint ? (
                        <div className="mt-0.5 text-[11px] leading-snug text-amber-200/80">
                          → {c.hint}
                        </div>
                      ) : null}
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          );
        })}
      </div>
      {q.missing_evidence_kinds.length ? (
        <div className="mt-4 rounded-xl border border-amber-400/25 bg-amber-500/[0.06] p-2.5">
          <div className="mb-1 text-[10.5px] font-semibold uppercase tracking-widest text-amber-300/85">
            Missing evidence kinds
          </div>
          <div className="flex flex-wrap gap-1">
            {q.missing_evidence_kinds.map((k) => (
              <span
                key={k}
                className="rounded-md border border-amber-400/40 bg-amber-500/[0.08] px-1.5 py-[1px] font-mono text-[10.5px] text-amber-200"
              >
                {kindLabelFor(k)}
              </span>
            ))}
          </div>
        </div>
      ) : null}
    </aside>
  );
}

// ---------------------------------------------------------------------------
// Main page.
// ---------------------------------------------------------------------------

export default function CodexPage() {
  const [rules, setRules] = useState<CodexRules | null>(null);
  const [codex, setCodex] = useState<CodexNarrative | null>(null);
  const [sourceLabel, setSourceLabel] = useState<string>("bundled sample");
  const [accountReport, setAccountReport] = useState<Record<string, unknown> | null>(null);
  const [analyst, setAnalyst] = useState<string>("analyst-4319");
  const [redact, setRedact] = useState<boolean>(false);
  const [caseId, setCaseId] = useState<string>("");
  const [loading, setLoading] = useState<boolean>(false);
  const [err, setErr] = useState<string | null>(null);
  const [activeKind, setActiveKind] = useState<string | null>(null);
  const [showMarkdown, setShowMarkdown] = useState<boolean>(false);
  const [copyState, setCopyState] = useState<"idle" | "copied">("idle");
  const [markdown, setMarkdown] = useState<string>("");
  const [loadingMd, setLoadingMd] = useState<boolean>(false);

  const focus = useCallback((kind: string) => {
    setActiveKind(kind && kind.length ? kind : null);
  }, []);

  const jumpToSection = useCallback((id: string) => {
    const el = document.getElementById(`codex-section-${id}`);
    if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
  }, []);

  useEffect(() => {
    getCodexRules().then(setRules).catch((e) => setErr(String(e)));
    getCodexSample()
      .then((s) => {
        setCodex(redact ? s.codex_redacted : s.codex);
        setAccountReport(s.account_report);
        setSourceLabel("bundled sample");
      })
      .catch((e) => setErr(String(e)));
    // sample fetch on mount only; subsequent redact toggle re-composes below
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Re-compose locally when analyst / redact / include-zero flips.  We keep
  // the account_report cached client-side so a toggle is instant, no fetch.
  const recompose = useCallback(
    async (report: Record<string, unknown> | null) => {
      if (!report) return;
      setLoading(true);
      setErr(null);
      try {
        const r = await composeCodex(report, { analyst, redact });
        setCodex(r.codex);
      } catch (e) {
        setErr(String(e));
      } finally {
        setLoading(false);
      }
    },
    [analyst, redact]
  );

  useEffect(() => {
    if (accountReport) recompose(accountReport);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [analyst, redact]);

  const loadCase = useCallback(async () => {
    const trimmed = caseId.trim();
    if (!trimmed) return;
    setLoading(true);
    setErr(null);
    try {
      const qs = new URLSearchParams();
      qs.set("analyst", analyst);
      qs.set("redact", redact ? "true" : "false");
      const r = await fetch(
        `/aml/codex/case/${encodeURIComponent(trimmed)}?${qs.toString()}`
      ).catch(() => null);
      // The frontend proxies through the gateway on same origin only in prod.
      // In `next dev`, hit the API_BASE directly.
      const finalR =
        r && r.ok
          ? r
          : await fetch(
              `${process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000"}/aml/codex/case/${encodeURIComponent(trimmed)}?${qs.toString()}`
            );
      if (!finalR.ok) throw new Error(await finalR.text());
      const body = await finalR.json();
      setCodex(body.codex);
      setAccountReport(null); // case snapshots aren't caller-owned
      setSourceLabel(`case ${trimmed}`);
    } catch (e) {
      setErr(String(e));
    } finally {
      setLoading(false);
    }
  }, [caseId, analyst, redact]);

  const loadMarkdown = useCallback(async () => {
    if (!codex) return;
    setLoadingMd(true);
    try {
      const url = codexExportUrl({
        redact,
        analyst,
        case_id: sourceLabel.startsWith("case ")
          ? sourceLabel.replace("case ", "")
          : undefined,
      });
      const r = await fetch(url);
      const text = await r.text();
      setMarkdown(text);
      setShowMarkdown(true);
    } finally {
      setLoadingMd(false);
    }
  }, [codex, sourceLabel, analyst, redact]);

  const copyMarkdown = useCallback(async () => {
    if (!markdown) await loadMarkdown();
    try {
      await navigator.clipboard.writeText(markdown || "");
      setCopyState("copied");
      setTimeout(() => setCopyState("idle"), 1400);
    } catch {
      /* clipboard unavailable — user can use Download */
    }
  }, [markdown, loadMarkdown]);

  const heroBg = codex ? GRADE_BG[codex.quality.grade] : GRADE_BG.acceptable;
  const heroAccent = codex ? GRADE_ACCENT[codex.quality.grade] : "#a5b4fc";
  const bandAccent = codex ? BAND_ACCENT[codex.band] || "#94a3b8" : "#94a3b8";

  return (
    <div className="space-y-6">
      {/* Hero */}
      <section
        className="glass-strong relative overflow-hidden p-6 md:p-8"
        style={{ backgroundImage: heroBg }}
      >
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <span className="pill">round-19 · day-90</span>
            <h1 className="mt-3 text-3xl font-semibold leading-tight tracking-tight md:text-4xl">
              <span className="grad-text">Codex</span> — evidence-cited SAR
              narrative composer.
            </h1>
            <p className="mt-2 max-w-3xl text-[14px] leading-relaxed text-white/70">
              Every sentence links back to the specific piece of evidence that
              supports it — transaction, factor, typology, sanctions hit,
              jurisdiction, counterparty. FinCEN 5W skeleton. Deterministic —
              same input, same paragraph, every time.
            </p>
          </div>
          {codex ? (
            <div
              className="flex min-w-[220px] flex-col items-start gap-2 rounded-2xl border p-4 text-left"
              style={{
                borderColor: `${heroAccent}55`,
                background: `${heroAccent}12`,
              }}
            >
              <span
                className="text-[10.5px] uppercase tracking-[0.2em]"
                style={{ color: heroAccent }}
              >
                Draft quality
              </span>
              <div className="flex items-baseline gap-2">
                <span
                  className="font-mono text-4xl font-bold"
                  style={{ color: heroAccent }}
                >
                  {fmt1(codex.quality.score)}
                </span>
                <span className="text-[13px] text-white/60">/ 100</span>
              </div>
              <span
                className="pill"
                style={{
                  borderColor: `${heroAccent}55`,
                  color: heroAccent,
                }}
              >
                {codex.quality.grade_label}
              </span>
              <span className="text-[11px] text-white/55">
                {codex.quality.passed}/{codex.quality.checks.length} checks
                passed
              </span>
            </div>
          ) : null}
        </div>
        {codex ? (
          <div className="mt-6 flex flex-wrap items-center gap-2 text-[12px]">
            <span
              className="rounded-lg border px-2.5 py-1 font-mono"
              style={{
                borderColor: `${bandAccent}50`,
                color: bandAccent,
                background: `${bandAccent}12`,
              }}
            >
              {codex.band.toUpperCase()} · {fmt1(codex.risk_score)}/100
            </span>
            <span className="rounded-lg border border-white/10 bg-black/20 px-2.5 py-1 font-mono text-white/70">
              Subject `{codex.account_id}`
              {codex.display_name ? (
                <span className="ml-1 text-white/45">
                  · {codex.display_name}
                </span>
              ) : null}
            </span>
            <span className="rounded-lg border border-white/10 bg-black/20 px-2.5 py-1 font-mono text-white/60">
              CDX id `{codex.codex_id}`
            </span>
            <span className="rounded-lg border border-white/10 bg-black/20 px-2.5 py-1 font-mono text-white/60">
              analyst {codex.analyst}
            </span>
            <span className="rounded-lg border border-white/10 bg-black/20 px-2.5 py-1 font-mono text-white/50">
              generated {codex.generated_at}
            </span>
            <span className="rounded-lg border border-white/10 bg-black/20 px-2.5 py-1 font-mono text-white/50">
              source · {sourceLabel}
            </span>
            {codex.redacted ? (
              <span className="pill pill-warn">redacted</span>
            ) : null}
          </div>
        ) : null}
      </section>

      {/* Toolbar */}
      <section className="glass flex flex-wrap items-end gap-3 p-4">
        <div className="flex-1 min-w-[180px]">
          <label className="label">Analyst</label>
          <input
            className="input"
            value={analyst}
            onChange={(e) => setAnalyst(e.target.value)}
            placeholder="handle or ID"
          />
        </div>
        <div className="flex-1 min-w-[200px]">
          <label className="label">Load from case</label>
          <div className="flex gap-2">
            <input
              className="input"
              value={caseId}
              onChange={(e) => setCaseId(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && loadCase()}
              placeholder="CASE-XXXXXXXX"
            />
            <button
              className="btn"
              onClick={loadCase}
              disabled={!caseId.trim() || loading}
            >
              {loading ? "…" : "Load"}
            </button>
          </div>
        </div>
        <label className="mt-6 inline-flex items-center gap-2 rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-white/80 cursor-pointer">
          <input
            type="checkbox"
            checked={redact}
            onChange={(e) => setRedact(e.target.checked)}
            className="h-4 w-4 accent-teal-400"
          />
          Redact identifiers
        </label>
        <button
          className="btn mt-6"
          onClick={loadMarkdown}
          disabled={!codex || loadingMd}
        >
          {loadingMd ? "…" : showMarkdown ? "Refresh markdown" : "Preview markdown"}
        </button>
        <button
          className="btn mt-6"
          onClick={copyMarkdown}
          disabled={!codex}
        >
          {copyState === "copied" ? "Copied ✓" : "Copy .md"}
        </button>
        <a
          className="btn-primary mt-6"
          href={codexExportUrl({
            redact,
            analyst,
            case_id: sourceLabel.startsWith("case ")
              ? sourceLabel.replace("case ", "")
              : undefined,
          })}
          target="_blank"
          rel="noreferrer"
        >
          Download .md
          <span aria-hidden>↗</span>
        </a>
      </section>

      {err ? (
        <div className="glass border-rose-400/30 bg-rose-500/[0.06] p-4 text-[13px] text-rose-200">
          {err}
        </div>
      ) : null}

      {/* Aggregate tiles */}
      {codex ? (
        <section className="grid grid-cols-2 gap-3 md:grid-cols-4 lg:grid-cols-6">
          <StatTile
            label="Sections composed"
            value={String(codex.sections.length)}
          />
          <StatTile
            label="Citations placed"
            value={fmt0(
              codex.sections.reduce((n, s) => n + s.citation_count, 0)
            )}
          />
          <StatTile
            label="Total words"
            value={fmt0(codex.sections.reduce((n, s) => n + s.word_count, 0))}
          />
          <StatTile
            label="Transactions"
            value={fmt0(codex.totals.transactions_in_scope)}
          />
          <StatTile
            label="Inbound ₹"
            value={fmt0(codex.totals.inbound)}
          />
          <StatTile
            label="Outbound ₹"
            value={fmt0(codex.totals.outbound)}
          />
        </section>
      ) : null}

      {/* Section jump chips */}
      {codex ? (
        <section className="glass flex flex-wrap items-center gap-2 p-3">
          <span className="text-[10.5px] uppercase tracking-widest text-white/50">
            Jump to
          </span>
          {codex.sections.map((s) => (
            <button
              key={s.id}
              onClick={() => jumpToSection(s.id)}
              className="rounded-lg border border-white/10 bg-white/[0.03] px-2.5 py-1 text-[12px] text-white/75 transition hover:border-teal-400/40 hover:text-teal-300"
            >
              §{s.number} {s.title.replace(/^\d+\.\s*/, "")}
            </button>
          ))}
        </section>
      ) : null}

      {/* Three-column composition grid */}
      {codex ? (
        <section className="grid gap-4 lg:grid-cols-[260px_minmax(0,1fr)_320px]">
          <EvidenceLibrary
            citations={codex.evidence_index}
            activeKind={activeKind}
            onFocus={focus}
          />
          <div className="min-w-0 space-y-4">
            {codex.sections.map((s) => (
              <SectionCard
                key={s.id}
                section={s}
                activeKind={activeKind}
                onFocus={focus}
              />
            ))}
          </div>
          <QualityPanel codex={codex} onJumpToSection={jumpToSection} />
        </section>
      ) : (
        <section className="glass p-8 text-center text-white/50">
          {err ? "Failed to load Codex sample." : "Composing…"}
        </section>
      )}

      {/* Markdown preview */}
      {showMarkdown && markdown ? (
        <section className="glass p-5">
          <header className="mb-3 flex items-baseline justify-between border-b border-white/5 pb-2">
            <h3 className="text-[13px] font-semibold uppercase tracking-wider text-white/70">
              Markdown preview
            </h3>
            <button
              className="btn-ghost text-[11.5px]"
              onClick={() => setShowMarkdown(false)}
            >
              Collapse
            </button>
          </header>
          <pre className="scroll-thin max-h-[70vh] overflow-auto whitespace-pre-wrap break-words rounded-lg bg-black/40 p-4 font-mono text-[12.5px] leading-relaxed text-white/85">
            {markdown}
          </pre>
        </section>
      ) : null}

      {/* Rules footer */}
      {rules ? (
        <section className="glass p-5 text-[12px] text-white/60">
          <header className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
            <h3 className="text-[13px] font-semibold uppercase tracking-wider text-white/70">
              Engine ({rules.engine})
            </h3>
            <div className="flex flex-wrap items-center gap-2 text-[10.5px] uppercase tracking-widest text-white/50">
              {rules.grade_ladder.map((g) => (
                <span
                  key={g.grade}
                  className="rounded-md border px-1.5 py-[1px] font-mono"
                  style={{
                    borderColor: `${g.accent}55`,
                    color: g.accent,
                    background: `${g.accent}12`,
                  }}
                >
                  ≥{g.min_score.toFixed(0)} · {g.label}
                </span>
              ))}
            </div>
          </header>
          <div className="grid gap-4 md:grid-cols-2">
            <div>
              <div className="mb-1 text-[10.5px] uppercase tracking-widest text-white/45">
                Section prompts
              </div>
              <ul className="space-y-1">
                {rules.sections.map((s) => (
                  <li key={s.id} className="leading-snug">
                    <span className="mr-1 font-mono text-white/80">
                      §{s.number}
                    </span>
                    <span className="text-white/70">
                      {s.title.replace(/^\d+\.\s*/, "")}
                    </span>
                    <span className="ml-2 text-white/45">— {s.prompt}</span>
                  </li>
                ))}
              </ul>
            </div>
            <div>
              <div className="mb-1 text-[10.5px] uppercase tracking-widest text-white/45">
                Evidence kind vocabulary
              </div>
              <div className="flex flex-wrap gap-1.5">
                {rules.evidence_kinds.map((k) => (
                  <span
                    key={k.kind}
                    className="rounded-md border px-2 py-[1px] font-mono text-[10.5px]"
                    style={{
                      borderColor: `${accentFor(k.kind)}45`,
                      color: accentFor(k.kind),
                      background: `${accentFor(k.kind)}10`,
                    }}
                  >
                    {k.label}
                  </span>
                ))}
              </div>
              <div className="mt-3 text-[11px] text-white/50">
                Typology-fit floor {(rules.typology_confidence_floor * 100).toFixed(0)}
                % · min {rules.max_transactions_cited} tx cited · Grade weighted
                across {rules.checks.length} checks · every check exposes its
                weight, its pass/fail, and its remediation hint.
              </div>
            </div>
          </div>
          <div className="mt-4 flex items-baseline justify-between border-t border-white/5 pt-3">
            <Link
              href="/cases"
              className="text-[11.5px] text-teal-300 hover:text-teal-200"
            >
              → open the case queue and load one into Codex
            </Link>
            <Link
              href="/aml"
              className="text-[11.5px] text-teal-300 hover:text-teal-200"
            >
              ↩ back to AML console
            </Link>
          </div>
        </section>
      ) : null}
    </div>
  );
}

function StatTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="glass px-4 py-3">
      <div className="text-[10.5px] uppercase tracking-widest text-white/45">
        {label}
      </div>
      <div className="mt-1 text-2xl font-semibold tracking-tight grad-text">
        {value}
      </div>
    </div>
  );
}
