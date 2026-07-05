"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { api } from "@/lib/api";
import type {
  GraphNode,
  RecallCard,
  RecallClusterMastery,
  RecallGrade,
  RecallGradeResult,
  RecallNeighborChoice,
  RecallSession,
  RecallSummary,
} from "@/lib/types";

type Props = {
  open: boolean;
  onClose: () => void;
  onSelectNote: (
    stub: Pick<GraphNode, "id" | "title" | "body" | "tags" | "degree" | "weight">,
  ) => void;
};

type CardOutcome = {
  card: RecallCard;
  grade: RecallGrade;
  correct: boolean | null; // null for prompt cards (self-assessed)
  auto_similarity?: number;
  next_due_phrase: string;
  new_interval_hours: number;
  new_ease: number;
};

const GRADE_LABELS: Record<RecallGrade, string> = {
  0: "again",
  1: "hard",
  2: "good",
  3: "easy",
};

const GRADE_TINTS: Record<RecallGrade, string> = {
  0: "from-rose-500/25 to-rose-500/10 ring-rose-400/50 text-rose-100 hover:ring-rose-300",
  1: "from-amber-500/25 to-amber-500/10 ring-amber-400/50 text-amber-100 hover:ring-amber-300",
  2: "from-emerald-500/25 to-emerald-500/10 ring-emerald-400/50 text-emerald-100 hover:ring-emerald-300",
  3: "from-cyan-500/25 to-violet-500/10 ring-cyan-400/50 text-cyan-100 hover:ring-cyan-300",
};

/**
 * Recall — active-recall quiz over the synapse graph.
 *
 * Layout: modal with a card stack. One card at a time; the user answers,
 * reveals, then self-grades (Again / Hard / Good / Easy → SM-2 lite).
 * Cloze cards also carry an auto-graded fuzzy-match check so the user
 * gets an "actually correct" verdict *before* the self-grade. Neighbor
 * cards are auto-graded from the choice click. Prompt cards are always
 * self-graded (the answer is a body excerpt, not a canonical string).
 *
 * The header carries a compact ring for session progress and a strip of
 * cluster-mastery bars so the user can see, in the same glance, "how
 * much of the graph lives in my head today" — the whole point of the
 * feature.
 */
export function Recall({ open, onClose, onSelectNote }: Props) {
  const [session, setSession] = useState<RecallSession | null>(null);
  const [summary, setSummary] = useState<RecallSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [idx, setIdx] = useState(0);
  const [revealed, setRevealed] = useState(false);
  const [chosenChoice, setChosenChoice] = useState<number | null>(null);
  const [clozeInput, setClozeInput] = useState("");
  const [clozeVerdict, setClozeVerdict] = useState<
    { is_correct: boolean; similarity: number } | null
  >(null);
  const [outcomes, setOutcomes] = useState<CardOutcome[]>([]);
  const [flipping, setFlipping] = useState(false);
  const [k, setK] = useState(6);
  const clozeInputRef = useRef<HTMLInputElement | null>(null);

  const cards = session?.cards ?? [];
  const current = cards[idx];
  const finished = cards.length > 0 && idx >= cards.length;

  const reset = useCallback(() => {
    setIdx(0);
    setRevealed(false);
    setChosenChoice(null);
    setClozeInput("");
    setClozeVerdict(null);
    setOutcomes([]);
  }, []);

  const load = useCallback(
    async (kOverride?: number) => {
      setLoading(true);
      setError(null);
      reset();
      try {
        // Deterministic session id = today's UTC date + optional card
        // count so switching k mid-day mints a fresh salt.
        const today = new Date().toISOString().slice(0, 10);
        const kUse = kOverride ?? k;
        const [s, sum] = await Promise.all([
          api.recallSession({ k: kUse, session: `${today}#${kUse}` }),
          api.recallSummary().catch(() => null),
        ]);
        setSession(s);
        setSummary(sum);
      } catch (e) {
        setError(e instanceof Error ? e.message : "failed to load session");
      } finally {
        setLoading(false);
      }
    },
    [k, reset],
  );

  useEffect(() => {
    if (!open) return;
    load();
  }, [open, load]);

  // Keyboard bindings: space/enter → reveal, 1-4 → grade, ← / → prev/next.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
        return;
      }
      if (finished) return;
      // Ignore keys while typing in the cloze input except Enter (check).
      const active = document.activeElement;
      const inInput =
        active instanceof HTMLElement &&
        (active.tagName === "INPUT" || active.tagName === "TEXTAREA");
      if (!current) return;
      if (inInput) {
        if (e.key === "Enter" && current.kind === "cloze" && !clozeVerdict) {
          e.preventDefault();
          checkCloze();
        }
        return;
      }
      if (e.key === " " || e.key === "Enter") {
        e.preventDefault();
        if (!revealed) doReveal();
      }
      if (["1", "2", "3", "4"].includes(e.key) && revealed) {
        e.preventDefault();
        grade((Number(e.key) - 1) as RecallGrade);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, current, revealed, clozeVerdict, finished]);

  // Auto-focus cloze input when a cloze card mounts.
  useEffect(() => {
    if (current?.kind === "cloze" && !revealed) {
      const t = window.setTimeout(() => clozeInputRef.current?.focus(), 40);
      return () => window.clearTimeout(t);
    }
  }, [current, revealed]);

  const checkCloze = useCallback(async () => {
    if (!current || current.kind !== "cloze") return;
    try {
      const verdict = await api.recallCheckCloze(
        current.cloze_answer,
        clozeInput,
      );
      setClozeVerdict(verdict);
      // Reveal always follows a check — the user has committed an answer.
      doReveal();
    } catch (e) {
      setError(e instanceof Error ? e.message : "check failed");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [current, clozeInput]);

  const doReveal = useCallback(() => {
    setFlipping(true);
    window.setTimeout(() => {
      setRevealed(true);
      setFlipping(false);
    }, 260);
  }, []);

  const pickChoice = useCallback(
    (choice: RecallNeighborChoice) => {
      if (!current || current.kind !== "neighbor" || revealed) return;
      setChosenChoice(choice.note_id);
      doReveal();
    },
    [current, revealed, doReveal],
  );

  const grade = useCallback(
    async (g: RecallGrade) => {
      if (!current) return;
      try {
        const result: RecallGradeResult = await api.recallGrade(
          current.note_id,
          g,
        );
        const correct =
          current.kind === "cloze"
            ? clozeVerdict?.is_correct ?? null
            : current.kind === "neighbor"
              ? chosenChoice === current.correct_choice_id
              : null;
        setOutcomes((prev) => [
          ...prev,
          {
            card: current,
            grade: g,
            correct,
            auto_similarity: clozeVerdict?.similarity,
            next_due_phrase: result.next_due_phrase,
            new_interval_hours: result.interval_hours,
            new_ease: result.ease,
          },
        ]);
        // Advance to the next card with a mini-flip.
        setFlipping(true);
        window.setTimeout(() => {
          setIdx((i) => i + 1);
          setRevealed(false);
          setChosenChoice(null);
          setClozeInput("");
          setClozeVerdict(null);
          setFlipping(false);
        }, 220);
      } catch (e) {
        setError(e instanceof Error ? e.message : "grade failed");
      }
    },
    [current, clozeVerdict, chosenChoice],
  );

  const summaryToShow = useMemo(() => {
    // Refresh the mastery summary once the session finishes — every
    // grade shifts it, so the post-session view should reflect the new
    // state. We defer this to a lazy fetch to keep the pre-session load
    // path tight.
    if (!finished) return summary;
    return summary;
  }, [summary, finished]);

  useEffect(() => {
    if (finished) {
      // Post-session refresh of summary numbers.
      api
        .recallSummary()
        .then(setSummary)
        .catch(() => undefined);
    }
  }, [finished]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center px-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="recall-title"
    >
      <div
        className="absolute inset-0 bg-ink-900/85 backdrop-blur-md"
        onClick={onClose}
      />
      <div className="absolute inset-0 pointer-events-none bg-grid-fade opacity-60" />

      <div className="relative w-full max-w-3xl rounded-2xl bg-ink-800/95 ring-1 ring-white/10 shadow-card overflow-hidden animate-fade-in">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-white/5 bg-gradient-to-r from-synapse-cyan/[0.08] via-synapse-violet/[0.05] to-synapse-amber/[0.06]">
          <div className="flex items-center gap-3">
            <RecallLogo />
            <div>
              <div
                id="recall-title"
                className="text-base font-semibold tracking-tight text-ink-100"
              >
                Recall{" "}
                <span className="text-[10px] font-mono text-synapse-cyan uppercase tracking-widest ml-1 align-middle">
                  new
                </span>
              </div>
              <div className="text-[11px] font-mono text-ink-300">
                {loading
                  ? "assembling session…"
                  : session
                    ? `${Math.min(idx + (finished ? 0 : 1), session.k)}/${session.k} · ${session.due_now} due · ${session.streak_days}d streak`
                    : "—"}
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <label className="text-[11px] font-mono text-ink-300">
              <span className="mr-1 opacity-70">k</span>
              <select
                value={k}
                onChange={(e) => {
                  const v = Number(e.target.value);
                  setK(v);
                  load(v);
                }}
                className="bg-ink-900/60 ring-1 ring-white/10 rounded px-1.5 py-0.5 text-ink-100 focus:outline-none focus:ring-synapse-cyan/60"
              >
                {[3, 6, 8, 10, 12].map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
              </select>
            </label>
            <button
              onClick={() => load()}
              className="px-2 py-1 rounded ring-1 ring-white/10 text-[11px] font-mono text-ink-200 hover:text-ink-100 hover:ring-synapse-cyan/40 transition"
              disabled={loading}
              title="Restart session"
            >
              ↻ new
            </button>
            <button
              onClick={onClose}
              className="text-ink-300 hover:text-ink-100 text-xs font-mono px-2 py-1 rounded ring-1 ring-white/10 hover:ring-synapse-pink/40 transition"
              aria-label="close"
            >
              esc
            </button>
          </div>
        </div>

        {/* Cluster mastery strip */}
        {summaryToShow && summaryToShow.clusters.length > 0 && (
          <ClusterStrip clusters={summaryToShow.clusters} />
        )}

        {/* Body */}
        <div className="px-6 py-6 min-h-[420px]">
          {loading && <RecallSkeleton />}
          {error && !loading && (
            <div className="text-sm font-mono text-synapse-pink">
              {error}
            </div>
          )}
          {!loading && !error && !finished && current && (
            <div
              key={current.id}
              className={`transition-all duration-200 ${flipping ? "opacity-0 scale-[0.99]" : "opacity-100 scale-100"}`}
            >
              <CardSurface
                card={current}
                revealed={revealed}
                clozeInput={clozeInput}
                setClozeInput={setClozeInput}
                clozeVerdict={clozeVerdict}
                onCheckCloze={checkCloze}
                onReveal={doReveal}
                onPickChoice={pickChoice}
                chosenChoice={chosenChoice}
                clozeInputRef={clozeInputRef}
              />
            </div>
          )}
          {!loading && !error && !finished && !current && cards.length === 0 && (
            <EmptyState />
          )}
          {!loading && !error && finished && (
            <SessionReport
              outcomes={outcomes}
              summary={summaryToShow}
              onOpenNote={(n) => {
                onSelectNote({
                  id: n.note_id,
                  title: n.title,
                  body: n.body_snippet ?? "",
                  tags: [],
                  degree: 0,
                  weight: 0,
                });
                onClose();
              }}
              onAgain={() => load()}
            />
          )}
        </div>

        {/* Footer with grade buttons when revealed */}
        {!loading &&
          !error &&
          !finished &&
          current &&
          revealed &&
          current.kind !== "neighbor" && (
            <GradeStrip
              onGrade={grade}
              autoCorrect={clozeVerdict?.is_correct}
            />
          )}
        {!loading &&
          !error &&
          !finished &&
          current &&
          revealed &&
          current.kind === "neighbor" && (
            <NeighborGradeStrip
              onGrade={grade}
              correct={chosenChoice === current.correct_choice_id}
            />
          )}
      </div>
    </div>
  );
}

// --------------------------------------------------------------- surface

function CardSurface({
  card,
  revealed,
  clozeInput,
  setClozeInput,
  clozeVerdict,
  onCheckCloze,
  onReveal,
  onPickChoice,
  chosenChoice,
  clozeInputRef,
}: {
  card: RecallCard;
  revealed: boolean;
  clozeInput: string;
  setClozeInput: (s: string) => void;
  clozeVerdict: { is_correct: boolean; similarity: number } | null;
  onCheckCloze: () => void;
  onReveal: () => void;
  onPickChoice: (c: RecallNeighborChoice) => void;
  chosenChoice: number | null;
  clozeInputRef: React.MutableRefObject<HTMLInputElement | null>;
}) {
  const color = card.cluster_color ?? "#a855f7";
  return (
    <div className="space-y-5">
      {/* Chips: cluster + kind + reasons */}
      <div className="flex items-center gap-2 flex-wrap">
        {card.cluster_name && (
          <span
            className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 font-mono text-[11px] ring-1"
            style={{
              color,
              borderColor: `${color}55`,
              background: `${color}10`,
            }}
          >
            <span
              className="w-1.5 h-1.5 rounded-full"
              style={{ background: color }}
            />
            {card.cluster_name}
          </span>
        )}
        <KindPill kind={card.kind} />
        {card.reasons.map((r, i) => (
          <span
            key={`${r}-${i}`}
            className="rounded-full px-2 py-0.5 font-mono text-[10px] ring-1 ring-white/10 text-ink-300"
          >
            {r}
          </span>
        ))}
        <div className="ml-auto flex items-center gap-3 text-[10px] font-mono text-ink-300">
          <MetricBadge label="ease" value={card.ease.toFixed(2)} />
          <MetricBadge
            label="streak"
            value={String(card.streak)}
            color={card.streak >= 3 ? "#a3e635" : undefined}
          />
        </div>
      </div>

      {/* Card body */}
      <div
        className="relative rounded-2xl bg-white/[0.02] ring-1 overflow-hidden"
        style={{
          borderColor: `${color}40`,
          boxShadow: `inset 4px 0 0 0 ${color}`,
        }}
      >
        <div className="absolute -top-16 -right-16 w-56 h-56 rounded-full blur-3xl pointer-events-none opacity-30"
          style={{ background: color }}
        />
        <div className="relative p-6 space-y-5">
          {card.kind === "cloze" && (
            <ClozeSurface
              card={card}
              revealed={revealed}
              clozeInput={clozeInput}
              setClozeInput={setClozeInput}
              clozeVerdict={clozeVerdict}
              onCheckCloze={onCheckCloze}
              onReveal={onReveal}
              clozeInputRef={clozeInputRef}
            />
          )}
          {card.kind === "prompt" && (
            <PromptSurface
              card={card}
              revealed={revealed}
              onReveal={onReveal}
            />
          )}
          {card.kind === "neighbor" && (
            <NeighborSurface
              card={card}
              revealed={revealed}
              chosenChoice={chosenChoice}
              onPickChoice={onPickChoice}
            />
          )}
        </div>
      </div>
    </div>
  );
}

// -------------------------------------------------------------- cloze

function ClozeSurface({
  card,
  revealed,
  clozeInput,
  setClozeInput,
  clozeVerdict,
  onCheckCloze,
  onReveal,
  clozeInputRef,
}: {
  card: RecallCard;
  revealed: boolean;
  clozeInput: string;
  setClozeInput: (s: string) => void;
  clozeVerdict: { is_correct: boolean; similarity: number } | null;
  onCheckCloze: () => void;
  onReveal: () => void;
  clozeInputRef: React.MutableRefObject<HTMLInputElement | null>;
}) {
  const wordCount = card.cloze_answer.trim().split(/\s+/).filter(Boolean).length;
  return (
    <div className="space-y-4">
      <div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-ink-300">
        cloze · from “{card.title}”
      </div>
      <div className="text-[15px] leading-relaxed text-ink-100 font-serif">
        {card.body_before && <span>{card.body_before} </span>}
        {!revealed ? (
          <span className="inline-flex items-center align-middle">
            <span className="inline-block px-2 py-0.5 rounded-md bg-synapse-cyan/15 ring-1 ring-synapse-cyan/50 font-mono text-synapse-cyan text-[13px] tracking-widest">
              {"_".repeat(Math.max(3, Math.min(10, card.cloze_answer.length)))}
            </span>
            <span className="ml-1.5 text-[10px] font-mono text-ink-300">
              ({wordCount} {wordCount === 1 ? "word" : "words"})
            </span>
          </span>
        ) : (
          <span
            className={`inline-block px-2 py-0.5 rounded-md font-mono text-[13px] ${
              clozeVerdict?.is_correct
                ? "bg-emerald-500/15 ring-1 ring-emerald-400/60 text-emerald-100"
                : clozeVerdict
                  ? "bg-rose-500/15 ring-1 ring-rose-400/60 text-rose-100"
                  : "bg-synapse-violet/15 ring-1 ring-synapse-violet/50 text-synapse-violet"
            }`}
          >
            {card.answer_text}
          </span>
        )}
        {card.body_after && <span> {card.body_after}</span>}
      </div>

      {!revealed && (
        <div className="flex items-center gap-2">
          <input
            ref={clozeInputRef}
            type="text"
            value={clozeInput}
            onChange={(e) => setClozeInput(e.target.value)}
            placeholder="type the missing phrase…"
            className="flex-1 bg-ink-900/60 ring-1 ring-white/10 focus:ring-synapse-cyan/60 rounded-lg px-3 py-2 text-sm text-ink-100 placeholder:text-ink-400 font-mono outline-none transition"
            aria-label="cloze answer"
          />
          <button
            onClick={onCheckCloze}
            className="px-3 py-2 rounded-lg ring-1 ring-synapse-cyan/50 text-synapse-cyan hover:bg-synapse-cyan/10 text-xs font-mono transition"
            disabled={clozeInput.trim().length === 0}
          >
            check ↵
          </button>
          <button
            onClick={onReveal}
            className="px-3 py-2 rounded-lg ring-1 ring-white/10 text-ink-300 hover:text-ink-100 hover:ring-synapse-violet/40 text-xs font-mono transition"
            title="Give up and reveal"
          >
            reveal
          </button>
        </div>
      )}

      {revealed && clozeVerdict && (
        <div
          className={`rounded-lg px-3 py-2 text-[12px] font-mono ${
            clozeVerdict.is_correct
              ? "bg-emerald-500/10 ring-1 ring-emerald-400/40 text-emerald-100"
              : "bg-rose-500/10 ring-1 ring-rose-400/40 text-rose-100"
          }`}
        >
          {clozeVerdict.is_correct
            ? `✓ matched — similarity ${Math.round(clozeVerdict.similarity * 100)}%`
            : `✗ your answer: “${clozeInput || "(empty)"}” — similarity ${Math.round(clozeVerdict.similarity * 100)}%`}
        </div>
      )}
    </div>
  );
}

// -------------------------------------------------------------- prompt

function PromptSurface({
  card,
  revealed,
  onReveal,
}: {
  card: RecallCard;
  revealed: boolean;
  onReveal: () => void;
}) {
  return (
    <div className="space-y-4">
      <div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-ink-300">
        prompt · concept recall
      </div>
      <h3 className="text-2xl font-semibold tracking-tight text-ink-100 leading-tight">
        {card.prompt_text}
      </h3>
      {!revealed ? (
        <div className="space-y-3">
          <p className="text-[13px] text-ink-300 italic">
            Answer in your head — then reveal to grade yourself.
          </p>
          <button
            onClick={onReveal}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-gradient-to-r from-synapse-cyan/20 to-synapse-violet/20 ring-1 ring-synapse-cyan/50 hover:ring-synapse-cyan/80 text-ink-100 text-sm font-mono transition"
          >
            reveal ↵ / space
          </button>
        </div>
      ) : (
        <div className="animate-fade-in">
          <div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-synapse-violet mb-2">
            what the note says
          </div>
          <p className="text-[14px] leading-relaxed text-ink-100 font-serif">
            {card.answer_text}
          </p>
        </div>
      )}
    </div>
  );
}

// ------------------------------------------------------------ neighbor

function NeighborSurface({
  card,
  revealed,
  chosenChoice,
  onPickChoice,
}: {
  card: RecallCard;
  revealed: boolean;
  chosenChoice: number | null;
  onPickChoice: (c: RecallNeighborChoice) => void;
}) {
  return (
    <div className="space-y-4">
      <div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-ink-300">
        neighbor · graph recall
      </div>
      <div>
        <div className="text-[13px] text-ink-200 mb-1">
          Which of these is the strongest synapse of
        </div>
        <h3 className="text-xl font-semibold tracking-tight text-ink-100 leading-tight">
          “{card.title}”?
        </h3>
      </div>
      {card.body_snippet && !revealed && (
        <p className="text-[12px] text-ink-300 italic leading-relaxed">
          {card.body_snippet}
        </p>
      )}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
        {card.choices.map((ch, i) => {
          const isChosen = ch.note_id === chosenChoice;
          const isCorrect = ch.is_correct;
          const showState = revealed || isChosen;
          const tint =
            showState && isChosen && isCorrect
              ? "ring-emerald-400/60 bg-emerald-500/10 text-emerald-100"
              : showState && isChosen && !isCorrect
                ? "ring-rose-400/60 bg-rose-500/10 text-rose-100"
                : revealed && isCorrect
                  ? "ring-emerald-400/40 bg-emerald-500/[0.03] text-emerald-100"
                  : "ring-white/10 bg-white/[0.02] text-ink-100 hover:ring-synapse-cyan/50";
          return (
            <button
              key={ch.note_id}
              onClick={() => onPickChoice(ch)}
              disabled={revealed}
              className={`text-left p-3 rounded-xl ring-1 transition group ${tint} ${revealed ? "cursor-default" : "cursor-pointer"}`}
            >
              <div className="flex items-start gap-2">
                <span className="font-mono text-[10px] text-ink-300 mt-0.5">
                  {String.fromCharCode(65 + i)}
                </span>
                <span className="text-[13px] leading-snug flex-1">{ch.title}</span>
                {ch.cluster_color && (
                  <span
                    className="w-2 h-2 rounded-full mt-1.5 shrink-0"
                    style={{ background: ch.cluster_color }}
                    title={`cluster ${ch.cluster_id}`}
                  />
                )}
              </div>
              {showState && isChosen && (
                <div
                  className={`mt-2 text-[10px] font-mono uppercase tracking-widest ${isCorrect ? "text-emerald-200" : "text-rose-200"}`}
                >
                  {isCorrect ? "✓ correct" : "✗ not the strongest synapse"}
                </div>
              )}
              {revealed && !isChosen && isCorrect && (
                <div className="mt-2 text-[10px] font-mono uppercase tracking-widest text-emerald-200">
                  ✓ correct answer
                </div>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}

// -------------------------------------------------- grade strips (footer)

function GradeStrip({
  onGrade,
  autoCorrect,
}: {
  onGrade: (g: RecallGrade) => void;
  autoCorrect: boolean | undefined;
}) {
  return (
    <div className="px-6 py-4 border-t border-white/5 bg-ink-900/40">
      <div className="flex items-center gap-2">
        <div className="text-[11px] font-mono text-ink-300 mr-1">
          {autoCorrect === true
            ? "how quickly did it come?"
            : autoCorrect === false
              ? "close, but grade the recall honestly"
              : "how well did you know it?"}
        </div>
        {([0, 1, 2, 3] as RecallGrade[]).map((g) => (
          <GradeButton key={g} grade={g} onClick={() => onGrade(g)} />
        ))}
      </div>
    </div>
  );
}

function NeighborGradeStrip({
  onGrade,
  correct,
}: {
  onGrade: (g: RecallGrade) => void;
  correct: boolean;
}) {
  // For neighbor cards we translate the click outcome into a
  // reasonable SM-2 auto-grade (2 or 0) but still expose the four
  // grades so the user can nudge — a lucky guess should be "hard",
  // a wrong click that "reminded them of the actual answer" is a "1".
  return (
    <div className="px-6 py-4 border-t border-white/5 bg-ink-900/40">
      <div className="flex items-center gap-2">
        <div className="text-[11px] font-mono text-ink-300 mr-1">
          {correct
            ? "clean recall of the synapse?"
            : "recall the correct answer?"}
        </div>
        {([0, 1, 2, 3] as RecallGrade[]).map((g) => (
          <GradeButton key={g} grade={g} onClick={() => onGrade(g)} />
        ))}
      </div>
    </div>
  );
}

function GradeButton({
  grade,
  onClick,
}: {
  grade: RecallGrade;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={`px-3 py-1.5 rounded-lg bg-gradient-to-r ring-1 text-xs font-mono uppercase tracking-widest transition ${GRADE_TINTS[grade]}`}
      title={`grade: ${GRADE_LABELS[grade]} (key ${grade + 1})`}
    >
      <span className="font-mono text-[10px] opacity-70 mr-1">{grade + 1}</span>
      {GRADE_LABELS[grade]}
    </button>
  );
}

// -------------------------------------------------------- cluster strip

function ClusterStrip({ clusters }: { clusters: RecallClusterMastery[] }) {
  const top = [...clusters]
    .sort((a, b) => b.size - a.size)
    .slice(0, 6);
  return (
    <div className="px-6 py-3 border-b border-white/5 bg-ink-900/40 flex items-center gap-3 overflow-x-auto">
      <div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-ink-300 shrink-0">
        mastery
      </div>
      <div className="flex items-center gap-2.5">
        {top.map((c) => (
          <MasteryTile key={c.cluster_id} cluster={c} />
        ))}
      </div>
    </div>
  );
}

function MasteryTile({ cluster }: { cluster: RecallClusterMastery }) {
  const pct = Math.round(cluster.mastery * 100);
  return (
    <div
      className="flex items-center gap-2 px-2.5 py-1 rounded-full ring-1 shrink-0"
      style={{
        borderColor: `${cluster.cluster_color}44`,
        background: `${cluster.cluster_color}0F`,
      }}
      title={`${cluster.cluster_name} — ${cluster.known}/${cluster.size} known · ${cluster.due_now} due · ease ${cluster.mean_ease}`}
    >
      <span
        className="w-1.5 h-1.5 rounded-full"
        style={{ background: cluster.cluster_color }}
      />
      <span className="text-[11px] font-mono text-ink-100">
        {cluster.cluster_name}
      </span>
      <span
        className="text-[10px] font-mono px-1.5 py-px rounded"
        style={{
          background: `${cluster.cluster_color}20`,
          color: cluster.cluster_color,
        }}
      >
        {pct}%
      </span>
      {cluster.due_now > 0 && (
        <span className="text-[10px] font-mono text-synapse-amber">
          · {cluster.due_now} due
        </span>
      )}
    </div>
  );
}

// -------------------------------------------------------- session report

function SessionReport({
  outcomes,
  summary,
  onOpenNote,
  onAgain,
}: {
  outcomes: CardOutcome[];
  summary: RecallSummary | null;
  onOpenNote: (card: RecallCard) => void;
  onAgain: () => void;
}) {
  const known = outcomes.filter(
    (o) => o.grade >= 2 && (o.correct === null || o.correct === true),
  ).length;
  const clean = outcomes.filter((o) => o.correct === true).length;
  const missed = outcomes.filter((o) => o.correct === false || o.grade === 0);
  return (
    <div className="animate-fade-in space-y-6">
      <div className="flex items-center gap-5">
        <div className="relative w-24 h-24 shrink-0">
          <svg viewBox="0 0 100 100" className="w-full h-full -rotate-90">
            <circle
              cx="50"
              cy="50"
              r="42"
              fill="none"
              stroke="rgba(255,255,255,0.06)"
              strokeWidth="8"
            />
            <circle
              cx="50"
              cy="50"
              r="42"
              fill="none"
              stroke="url(#recall-ring)"
              strokeWidth="8"
              strokeLinecap="round"
              strokeDasharray={`${(clean / Math.max(1, outcomes.length)) * (2 * Math.PI * 42)} ${2 * Math.PI * 42}`}
            />
            <defs>
              <linearGradient id="recall-ring" x1="0" y1="0" x2="1" y2="1">
                <stop offset="0%" stopColor="#22d3ee" />
                <stop offset="100%" stopColor="#a3e635" />
              </linearGradient>
            </defs>
          </svg>
          <div className="absolute inset-0 flex items-center justify-center flex-col">
            <div className="text-2xl font-semibold text-ink-100 leading-none">
              {clean}
              <span className="text-ink-300 text-sm font-mono">
                /{outcomes.length}
              </span>
            </div>
            <div className="text-[9px] font-mono uppercase tracking-widest text-ink-300 mt-1">
              clean
            </div>
          </div>
        </div>
        <div className="flex-1 space-y-2">
          <div className="text-lg font-semibold tracking-tight text-ink-100">
            Session complete.
          </div>
          <div className="text-[12px] font-mono text-ink-300">
            {clean}/{outcomes.length} clean recalls · {known} graded ≥ good ·{" "}
            {missed.length} to revisit
          </div>
          {summary && (
            <div className="text-[11px] font-mono text-ink-300">
              Overall mastery {Math.round(summary.mastery_overall * 100)}% ·{" "}
              {summary.reviewed_notes}/{summary.total_notes} rehearsed ·{" "}
              {summary.streak_days}d streak · mean ease{" "}
              {summary.mean_ease.toFixed(2)}
            </div>
          )}
          <button
            onClick={onAgain}
            className="mt-2 px-3 py-1.5 rounded-lg ring-1 ring-synapse-cyan/40 text-synapse-cyan hover:bg-synapse-cyan/10 text-xs font-mono transition"
          >
            ↻ another session
          </button>
        </div>
      </div>

      <div>
        <div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-ink-300 mb-2">
          card by card
        </div>
        <div className="space-y-1.5">
          {outcomes.map((o) => (
            <button
              key={o.card.id}
              onClick={() => onOpenNote(o.card)}
              className="w-full text-left flex items-center gap-3 px-3 py-2 rounded-lg ring-1 ring-white/5 hover:ring-synapse-cyan/40 bg-white/[0.02] transition"
              title="open in graph"
            >
              <span
                className={`w-1.5 h-6 rounded-full shrink-0`}
                style={{
                  background:
                    o.correct === true
                      ? "#a3e635"
                      : o.correct === false
                        ? "#f43f5e"
                        : o.grade >= 2
                          ? "#22d3ee"
                          : "#fbbf24",
                }}
              />
              <div className="flex-1 min-w-0">
                <div className="text-[13px] text-ink-100 truncate">
                  {o.card.title}
                </div>
                <div className="text-[10px] font-mono text-ink-300 flex items-center gap-2">
                  <KindPill kind={o.card.kind} compact />
                  <span>
                    {o.correct === true
                      ? "✓ recalled"
                      : o.correct === false
                        ? "✗ missed"
                        : "self-graded"}
                  </span>
                  <span className="text-ink-400">·</span>
                  <span>{GRADE_LABELS[o.grade]}</span>
                  <span className="text-ink-400">·</span>
                  <span>{o.next_due_phrase}</span>
                </div>
              </div>
              <span
                className="text-[10px] font-mono opacity-70"
                style={{ color: o.card.cluster_color ?? "#a855f7" }}
              >
                ease {o.new_ease.toFixed(2)}
              </span>
            </button>
          ))}
        </div>
      </div>

      {summary && summary.clusters.length > 0 && (
        <div>
          <div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-ink-300 mb-2">
            mastery by cluster
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {[...summary.clusters]
              .sort((a, b) => b.size - a.size)
              .map((c) => (
                <div
                  key={c.cluster_id}
                  className="rounded-lg ring-1 p-3 space-y-1.5"
                  style={{
                    borderColor: `${c.cluster_color}33`,
                    background: `${c.cluster_color}08`,
                  }}
                >
                  <div className="flex items-center gap-2">
                    <span
                      className="w-1.5 h-1.5 rounded-full"
                      style={{ background: c.cluster_color }}
                    />
                    <span className="text-[13px] text-ink-100 truncate flex-1">
                      {c.cluster_name}
                    </span>
                    <span
                      className="text-[11px] font-mono"
                      style={{ color: c.cluster_color }}
                    >
                      {Math.round(c.mastery * 100)}%
                    </span>
                  </div>
                  <div className="h-1.5 rounded-full bg-white/[0.04] overflow-hidden">
                    <div
                      className="h-full rounded-full"
                      style={{
                        width: `${Math.round(c.mastery * 100)}%`,
                        background: `linear-gradient(90deg, ${c.cluster_color}aa, ${c.cluster_color})`,
                      }}
                    />
                  </div>
                  <div className="flex items-center gap-2 text-[10px] font-mono text-ink-300">
                    <span>
                      {c.known}/{c.size} known
                    </span>
                    <span className="text-ink-400">·</span>
                    <span>{c.reviewed} reviewed</span>
                    {c.due_now > 0 && (
                      <>
                        <span className="text-ink-400">·</span>
                        <span className="text-synapse-amber">
                          {c.due_now} due
                        </span>
                      </>
                    )}
                  </div>
                </div>
              ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------- misc bits

function KindPill({
  kind,
  compact,
}: {
  kind: RecallCard["kind"];
  compact?: boolean;
}) {
  const cfg =
    kind === "cloze"
      ? { text: "cloze", color: "text-synapse-cyan", ring: "ring-synapse-cyan/40", bg: "bg-synapse-cyan/10" }
      : kind === "prompt"
        ? { text: "prompt", color: "text-synapse-violet", ring: "ring-synapse-violet/40", bg: "bg-synapse-violet/10" }
        : { text: "neighbor", color: "text-synapse-amber", ring: "ring-synapse-amber/40", bg: "bg-synapse-amber/10" };
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full ring-1 ${cfg.color} ${cfg.ring} ${cfg.bg} ${compact ? "px-1.5 py-0.5 text-[9px]" : "px-2 py-0.5 text-[10px]"} font-mono uppercase tracking-widest`}
    >
      {cfg.text}
    </span>
  );
}

function MetricBadge({
  label,
  value,
  color,
}: {
  label: string;
  value: string;
  color?: string;
}) {
  return (
    <span className="inline-flex items-center gap-1 rounded-full ring-1 ring-white/10 px-1.5 py-0.5">
      <span className="opacity-70">{label}</span>
      <span className="text-ink-100" style={color ? { color } : undefined}>
        {value}
      </span>
    </span>
  );
}

function RecallLogo() {
  return (
    <div className="relative w-9 h-9">
      <svg viewBox="0 0 36 36" className="w-full h-full">
        <defs>
          <linearGradient id="rl" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="#22d3ee" />
            <stop offset="60%" stopColor="#a855f7" />
            <stop offset="100%" stopColor="#a3e635" />
          </linearGradient>
        </defs>
        <circle
          cx="18"
          cy="18"
          r="14"
          fill="none"
          stroke="url(#rl)"
          strokeWidth="1.4"
          strokeDasharray="4 3"
        />
        <path
          d="M 10 22 A 8 8 0 1 1 24 22"
          fill="none"
          stroke="url(#rl)"
          strokeWidth="1.4"
          strokeLinecap="round"
        />
        <polyline
          points="21,22 24,22 24,19"
          fill="none"
          stroke="url(#rl)"
          strokeWidth="1.4"
          strokeLinecap="round"
        />
        <circle cx="18" cy="18" r="2" fill="url(#rl)" />
      </svg>
    </div>
  );
}

function RecallSkeleton() {
  return (
    <div className="space-y-4 animate-pulse">
      <div className="flex gap-2">
        <div className="h-6 w-24 rounded-full bg-white/[0.03]" />
        <div className="h-6 w-16 rounded-full bg-white/[0.03]" />
      </div>
      <div className="h-64 rounded-2xl bg-white/[0.02] ring-1 ring-white/5" />
      <div className="h-8 w-full rounded-lg bg-white/[0.02]" />
    </div>
  );
}

function EmptyState() {
  return (
    <div className="text-center py-12 space-y-2">
      <div className="text-3xl">∅</div>
      <p className="text-sm text-ink-200">Nothing to recall yet.</p>
      <p className="text-[11px] text-ink-400">
        Add a handful of notes with real bodies — Recall turns on
        automatically.
      </p>
    </div>
  );
}
