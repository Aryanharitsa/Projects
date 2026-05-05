"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "@/lib/api";
import type {
  ChatCitation,
  ChatMode,
  ChatResponse,
  ChatRole,
  ChatStatus,
  ChatTurn,
  GraphNode,
} from "@/lib/types";

type Props = {
  nodes: GraphNode[];
  onCitationClick: (node: GraphNode) => void;
  onTraversalChange: (turn: ChatTurn | null) => void;
};

const ROLE_TONE: Record<
  ChatRole,
  { label: string; ring: string; text: string; bg: string; icon: string }
> = {
  seed: {
    label: "match",
    ring: "ring-synapse-cyan/40",
    text: "text-synapse-cyan",
    bg: "bg-synapse-cyan/10",
    icon: "◎",
  },
  synapse: {
    label: "synapse",
    ring: "ring-synapse-violet/40",
    text: "text-synapse-violet",
    bg: "bg-synapse-violet/10",
    icon: "↝",
  },
  community: {
    label: "anchor",
    ring: "ring-synapse-pink/40",
    text: "text-synapse-pink",
    bg: "bg-synapse-pink/10",
    icon: "★",
  },
};

const SUGGESTIONS = [
  "what's my view on PKM?",
  "how does retrieval-augmented generation work?",
  "summarize my engineering principles",
  "what's the case for the graph as the product?",
];

export function ChatPanel({ nodes, onCitationClick, onTraversalChange }: Props) {
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState<ChatMode>("auto");
  const [hops, setHops] = useState<0 | 1 | 2>(1);
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<ChatStatus | null>(null);
  const transcriptRef = useRef<HTMLDivElement>(null);
  const taRef = useRef<HTMLTextAreaElement>(null);

  const nodeById = useMemo(() => {
    const m = new Map<number, GraphNode>();
    for (const n of nodes) m.set(n.id, n);
    return m;
  }, [nodes]);

  useEffect(() => {
    api.chatStatus().then(setStatus).catch(() => setStatus(null));
  }, []);

  useEffect(() => {
    // Always scroll the latest answer into view.
    transcriptRef.current?.scrollTo({
      top: transcriptRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [turns.length, busy]);

  async function ask(prompt?: string) {
    const q = (prompt ?? query).trim();
    if (!q || busy) return;
    setError(null);
    setBusy(true);
    try {
      const response = await api.chat({ query: q, mode, hops });
      const turn: ChatTurn = { id: crypto.randomUUID(), query: q, response };
      setTurns((prev) => [...prev, turn]);
      onTraversalChange(turn);
      setQuery("");
      // Re-focus for fast follow-up.
      requestAnimationFrame(() => taRef.current?.focus());
    } catch (e) {
      setError(e instanceof Error ? e.message : "chat failed");
    } finally {
      setBusy(false);
    }
  }

  function clearTranscript() {
    setTurns([]);
    onTraversalChange(null);
  }

  function handleCitation(c: ChatCitation) {
    const n = nodeById.get(c.note_id);
    if (n) onCitationClick(n);
  }

  return (
    <div className="rounded-xl bg-ink-800/60 ring-1 ring-white/5 shadow-card p-4 flex flex-col gap-3 animate-fade-in">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold uppercase tracking-[0.16em] text-ink-200">
            ask the graph
          </span>
          {status?.llm_available ? (
            <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-synapse-amber/10 text-synapse-amber ring-1 ring-synapse-amber/20">
              LLM ready
            </span>
          ) : (
            <span
              className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-white/5 text-ink-300 ring-1 ring-white/10"
              title="set SYNAPSE_LLM_KEY to enable LLM mode"
            >
              extractive
            </span>
          )}
        </div>
        {turns.length > 0 && (
          <button
            onClick={clearTranscript}
            className="text-[10px] text-ink-300 hover:text-ink-100 font-mono"
          >
            clear
          </button>
        )}
      </div>

      <div
        ref={transcriptRef}
        className="overflow-y-auto pr-1 max-h-[40vh] min-h-[60px] flex flex-col gap-3"
      >
        {turns.length === 0 && !busy ? (
          <EmptyState
            onPick={(s) => {
              setQuery(s);
              ask(s);
            }}
          />
        ) : (
          turns.map((t) => (
            <Turn
              key={t.id}
              turn={t}
              onCitationClick={handleCitation}
              onReplay={() => onTraversalChange(t)}
            />
          ))
        )}
        {busy && <ThinkingRow query={query} />}
      </div>

      <div className="flex flex-col gap-2 pt-1 border-t border-white/5">
        <textarea
          ref={taRef}
          rows={2}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              ask();
            }
          }}
          placeholder="ask in plain English — citations come from your notes"
          className="w-full resize-none bg-ink-900/60 ring-1 ring-white/5 rounded-lg px-3 py-2 text-sm text-ink-100 placeholder:text-ink-400 focus-ring"
        />

        <div className="flex items-center gap-2 flex-wrap">
          <ModeChip
            label="auto"
            active={mode === "auto"}
            onClick={() => setMode("auto")}
          />
          <ModeChip
            label="extractive"
            active={mode === "extractive"}
            onClick={() => setMode("extractive")}
          />
          <ModeChip
            label="LLM"
            active={mode === "llm"}
            onClick={() => setMode("llm")}
            disabled={!status?.llm_available}
            title={
              status?.llm_available
                ? "force LLM mode"
                : "set SYNAPSE_LLM_KEY in the backend to enable"
            }
          />

          <div className="ml-auto flex items-center gap-1 text-[10px] font-mono text-ink-300">
            <span>hops</span>
            {[0, 1, 2].map((h) => (
              <button
                key={h}
                onClick={() => setHops(h as 0 | 1 | 2)}
                className={`w-6 h-6 rounded ${
                  hops === h
                    ? "bg-synapse-violet/20 text-synapse-violet ring-1 ring-synapse-violet/40"
                    : "bg-white/[0.02] text-ink-300 ring-1 ring-white/5 hover:text-ink-100"
                }`}
              >
                {h}
              </button>
            ))}
          </div>

          <button
            onClick={() => ask()}
            disabled={busy || !query.trim()}
            className="rounded-lg px-3 py-1.5 text-xs font-medium text-ink-900 bg-gradient-to-r from-synapse-violet to-synapse-cyan disabled:opacity-40 hover:brightness-110 transition"
          >
            {busy ? "thinking…" : "ask"}
          </button>
        </div>

        {error && (
          <p className="text-xs text-synapse-pink font-mono">
            {error} — is the backend running?
          </p>
        )}
      </div>
    </div>
  );
}

function EmptyState({ onPick }: { onPick: (s: string) => void }) {
  return (
    <div className="text-xs text-ink-300 leading-relaxed space-y-2">
      <p>
        Ask anything about your notes. The retriever seeds with semantic
        search, then expands one hop along your synapses — every citation
        comes with provenance, and the traversal lights up on the graph.
      </p>
      <div className="flex flex-wrap gap-1.5 pt-1">
        {SUGGESTIONS.map((s) => (
          <button
            key={s}
            onClick={() => onPick(s)}
            className="text-[11px] px-2 py-1 rounded bg-white/[0.025] text-ink-200 ring-1 ring-white/5 hover:bg-white/[0.06] hover:text-ink-100 transition"
          >
            {s}
          </button>
        ))}
      </div>
    </div>
  );
}

function ThinkingRow({ query }: { query: string }) {
  return (
    <div className="rounded-lg bg-white/[0.02] ring-1 ring-white/5 p-3 text-xs text-ink-300 animate-fade-in">
      <div className="flex items-center gap-2 mb-1">
        <span className="inline-block w-2 h-2 rounded-full bg-synapse-cyan animate-pulse-slow" />
        <span className="font-mono uppercase tracking-[0.16em] text-[10px]">
          retrieving
        </span>
        {query && (
          <span className="text-ink-200 truncate flex-1">“{query}”</span>
        )}
      </div>
      <ShimmerBar />
    </div>
  );
}

function ShimmerBar() {
  return (
    <div className="relative h-1.5 w-full overflow-hidden rounded-full bg-white/5">
      <span
        className="absolute inset-y-0 -left-1/3 w-1/3 bg-gradient-to-r from-transparent via-synapse-violet/60 to-transparent"
        style={{ animation: "ws-shimmer 1.4s linear infinite" }}
      />
    </div>
  );
}

type TurnProps = {
  turn: ChatTurn;
  onCitationClick: (c: ChatCitation) => void;
  onReplay: () => void;
};

function Turn({ turn, onCitationClick, onReplay }: TurnProps) {
  const { response: r } = turn;
  const seedCount = r.citations.filter((c) => c.role === "seed").length;
  const synCount = r.citations.filter((c) => c.role === "synapse").length;
  const anchorCount = r.citations.filter((c) => c.role === "community").length;

  return (
    <div className="rounded-lg bg-white/[0.018] ring-1 ring-white/5 p-3 space-y-2.5 animate-fade-in">
      <div className="flex items-start gap-2">
        <span className="mt-1 inline-block w-1 self-stretch rounded-full bg-gradient-to-b from-synapse-violet to-synapse-cyan" />
        <div className="flex-1 min-w-0">
          <div className="text-[11px] font-mono text-ink-300 truncate">
            you asked
          </div>
          <div className="text-sm text-ink-100 leading-snug">{turn.query}</div>
        </div>
        <button
          onClick={onReplay}
          title="replay this traversal on the graph"
          className="text-[10px] font-mono text-ink-300 hover:text-ink-100 px-1.5 py-0.5 rounded ring-1 ring-white/5"
        >
          replay
        </button>
      </div>

      <AnswerBody answer={r.answer} citations={r.citations} onCite={onCitationClick} />

      <div className="flex items-center gap-2 flex-wrap text-[10px] font-mono text-ink-300">
        <Pill tone={r.mode_used === "llm" ? "amber" : "slate"}>
          {r.mode_used === "llm" ? r.model : "extractive"}
        </Pill>
        <Pill tone="cyan">{seedCount} seed</Pill>
        {synCount > 0 && <Pill tone="violet">{synCount} synapse</Pill>}
        {anchorCount > 0 && <Pill tone="pink">{anchorCount} anchor</Pill>}
        <span className="text-ink-400">·</span>
        <span>{r.latency_ms} ms</span>
        <span className="text-ink-400">·</span>
        <span>
          {r.traversal.expansions.length} edge
          {r.traversal.expansions.length === 1 ? "" : "s"} traced
        </span>
      </div>

      {r.notice && (
        <p className="text-[11px] text-synapse-amber/90 leading-relaxed">
          {r.notice}
        </p>
      )}

      <div className="space-y-1">
        <div className="text-[10px] font-mono uppercase tracking-[0.16em] text-ink-300">
          citations
        </div>
        <ul className="space-y-1.5">
          {r.citations.map((c, i) => (
            <CitationRow
              key={`${c.note_id}-${c.role}-${i}`}
              n={i + 1}
              c={c}
              onClick={() => onCitationClick(c)}
            />
          ))}
        </ul>
      </div>
    </div>
  );
}

function AnswerBody({
  answer,
  citations,
  onCite,
}: {
  answer: string;
  citations: ChatCitation[];
  onCite: (c: ChatCitation) => void;
}) {
  // Split on paragraph breaks but keep markdown-light: render bullet
  // lines specially; convert inline [#N] markers into clickable chips.
  const lines = answer.split(/\n+/).filter((l) => l.trim().length > 0);

  return (
    <div className="text-sm text-ink-100 leading-relaxed space-y-1.5">
      {lines.map((line, i) => {
        const isBullet = /^[-*]\s+/.test(line);
        const content = isBullet ? line.replace(/^[-*]\s+/, "") : line;
        return (
          <div
            key={i}
            className={isBullet ? "flex gap-2" : ""}
          >
            {isBullet && (
              <span className="text-synapse-violet mt-1 select-none">•</span>
            )}
            <span className="flex-1">{renderInlineCites(content, citations, onCite)}</span>
          </div>
        );
      })}
    </div>
  );
}

function renderInlineCites(
  text: string,
  citations: ChatCitation[],
  onCite: (c: ChatCitation) => void,
) {
  const parts: Array<string | JSX.Element> = [];
  const re = /\[#(\d+)\]/g;
  let last = 0;
  let m: RegExpExecArray | null;
  let key = 0;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) parts.push(renderBold(text.slice(last, m.index), key++));
    const n = Number(m[1]);
    const c = citations[n - 1];
    if (c) {
      parts.push(
        <button
          key={`c${key++}`}
          onClick={(e) => {
            e.preventDefault();
            onCite(c);
          }}
          className="inline-flex items-center justify-center min-w-[22px] h-[18px] mx-0.5 rounded text-[10px] font-mono align-middle bg-synapse-violet/12 text-synapse-violet ring-1 ring-synapse-violet/30 hover:bg-synapse-violet/25 hover:text-ink-100 transition"
          title={`${c.title} (${c.role})`}
        >
          {n}
        </button>,
      );
    } else {
      parts.push(`[#${n}]`);
    }
    last = re.lastIndex;
  }
  if (last < text.length) parts.push(renderBold(text.slice(last), key++));
  return parts;
}

function renderBold(text: string, k: number) {
  // Tiny **bold** rendering — the extractive answerer emits **title** in a
  // few of its fallback paths. Avoid pulling in a full markdown lib.
  if (!text.includes("**")) return <span key={`t${k}`}>{text}</span>;
  const out: Array<string | JSX.Element> = [];
  const re = /\*\*([^*]+)\*\*/g;
  let last = 0;
  let m: RegExpExecArray | null;
  let i = 0;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) out.push(text.slice(last, m.index));
    out.push(
      <strong key={`b${k}-${i++}`} className="text-ink-100 font-semibold">
        {m[1]}
      </strong>,
    );
    last = re.lastIndex;
  }
  if (last < text.length) out.push(text.slice(last));
  return <span key={`t${k}`}>{out}</span>;
}

function CitationRow({
  n,
  c,
  onClick,
}: {
  n: number;
  c: ChatCitation;
  onClick: () => void;
}) {
  const tone = ROLE_TONE[c.role];
  return (
    <li>
      <button
        onClick={onClick}
        className="w-full text-left flex items-start gap-2 rounded-lg px-2 py-1.5 hover:bg-white/[0.04] transition group"
      >
        <span
          className={`flex-shrink-0 w-5 h-5 mt-0.5 inline-flex items-center justify-center rounded text-[10px] font-mono ${tone.bg} ${tone.text} ring-1 ${tone.ring}`}
        >
          {n}
        </span>
        <span className="flex-1 min-w-0">
          <span className="flex items-center gap-1.5">
            <span className="text-sm text-ink-100 truncate group-hover:text-white">
              {c.title}
            </span>
            <span
              className={`text-[9px] font-mono uppercase tracking-[0.12em] px-1 py-px rounded ${tone.bg} ${tone.text} ring-1 ${tone.ring}`}
              title={
                c.role === "seed"
                  ? "matched semantically against your query"
                  : c.role === "synapse"
                  ? "reached via a synapse from a seed match"
                  : "topic anchor: highest-weight note in the seed's community"
              }
            >
              {tone.icon} {tone.label}
            </span>
          </span>
          <span className="block text-[11px] text-ink-300 leading-snug mt-0.5 line-clamp-2">
            {c.snippet}
          </span>
          {c.role !== "seed" && c.via_seed_id != null && (
            <span className="block text-[10px] font-mono text-ink-400 mt-0.5">
              via #{c.via_seed_id}
              {c.via_strength > 0 && ` · ${(c.via_strength * 100).toFixed(0)}%`}
            </span>
          )}
        </span>
        <span className="text-[10px] font-mono text-ink-300 mt-1 flex-shrink-0">
          {(c.score * 100).toFixed(0)}%
        </span>
      </button>
    </li>
  );
}

function ModeChip({
  label,
  active,
  onClick,
  disabled,
  title,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
  disabled?: boolean;
  title?: string;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      title={title}
      className={`text-[10px] font-mono px-2 py-1 rounded ring-1 transition ${
        active
          ? "bg-synapse-violet/15 text-synapse-violet ring-synapse-violet/40"
          : "bg-white/[0.02] text-ink-300 ring-white/5 hover:text-ink-100"
      } disabled:opacity-40 disabled:cursor-not-allowed`}
    >
      {label}
    </button>
  );
}

function Pill({
  tone,
  children,
}: {
  tone: "violet" | "cyan" | "amber" | "pink" | "slate";
  children: React.ReactNode;
}) {
  const cls =
    {
      violet: "bg-synapse-violet/10 text-synapse-violet ring-synapse-violet/30",
      cyan: "bg-synapse-cyan/10 text-synapse-cyan ring-synapse-cyan/30",
      amber: "bg-synapse-amber/10 text-synapse-amber ring-synapse-amber/30",
      pink: "bg-synapse-pink/10 text-synapse-pink ring-synapse-pink/30",
      slate: "bg-white/[0.04] text-ink-300 ring-white/10",
    }[tone];
  return (
    <span className={`px-1.5 py-0.5 rounded ring-1 ${cls}`}>{children}</span>
  );
}

export type { ChatTurn };
