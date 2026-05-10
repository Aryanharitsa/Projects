import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Trophy,
  Swords,
  Crown,
  Flame,
  Award,
  Sparkles,
  RefreshCcw,
  Undo2,
  Hash,
  Bot,
  Scale,
  Eye,
  EyeOff,
  TrendingUp,
  TrendingDown,
  Minus,
  ArrowRight,
  ChevronRight,
  Zap,
  XCircle,
  HandshakeIcon,
} from "lucide-react";
import { toast } from "sonner";
import ApiService from "../services/api";

// ─── visual helpers ─────────────────────────────────────────────────────────

const PROVIDER_DOT = {
  OpenAI:    "bg-emerald-500",
  Anthropic: "bg-amber-500",
  Google:    "bg-sky-500",
  August:    "bg-fuchsia-500",
};

const PROVIDER_GRADIENT = {
  OpenAI:    "from-emerald-500/20 to-emerald-500/5 border-emerald-500/30",
  Anthropic: "from-amber-500/20 to-amber-500/5 border-amber-500/30",
  Google:    "from-sky-500/20 to-sky-500/5 border-sky-500/30",
  August:    "from-fuchsia-500/20 to-fuchsia-500/5 border-fuchsia-500/30",
};

const PROVIDER_TEXT = {
  OpenAI:    "text-emerald-700",
  Anthropic: "text-amber-700",
  Google:    "text-sky-700",
  August:    "text-fuchsia-700",
};

const SIDE_TONE = {
  a: { ring: "ring-indigo-500", border: "border-indigo-300", grad: "from-indigo-50 to-violet-50",
       letter: "bg-gradient-to-br from-indigo-600 to-violet-600 text-white" },
  b: { ring: "ring-rose-500", border: "border-rose-300", grad: "from-rose-50 to-orange-50",
       letter: "bg-gradient-to-br from-rose-600 to-orange-500 text-white" },
};

const fmtRel = (epoch) => {
  if (!epoch) return "—";
  const d = new Date(Number(epoch) * 1000);
  const diff = (Date.now() - d.getTime()) / 1000;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  if (diff < 86400 * 7) return `${Math.floor(diff / 86400)}d ago`;
  return d.toLocaleDateString();
};

const fmtCost = (c) =>
  c == null ? "—" : c < 0.0001 ? `$${(c * 1000).toFixed(3)}m` : `$${Number(c).toFixed(4)}`;

const fmtLat = (l) => (l == null ? "—" : `${Number(l).toFixed(2)}s`);

// Hue ramp 0–100 (red → amber → emerald). Used for win-rate / agreement /
// rating-percentile fills.
const ramp = (v) => {
  const clamped = Math.max(0, Math.min(100, v));
  const hue = Math.round(clamped * 1.2); // 0→0(red), 100→120(emerald)
  return `hsl(${hue} 75% 45%)`;
};

// Conic-gradient ring for compact rating/win-rate displays.
const Ring = ({ value = 0, size = 44, label, accent }) => {
  const v = Math.max(0, Math.min(100, Math.round(value || 0)));
  const color = accent || ramp(v);
  return (
    <div
      className="relative inline-flex items-center justify-center shrink-0"
      style={{
        width: size, height: size, borderRadius: "9999px",
        background: `conic-gradient(${color} ${v * 3.6}deg, #e5e7eb ${v * 3.6}deg)`,
      }}
    >
      <div
        className="bg-white flex items-center justify-center"
        style={{ width: size - 8, height: size - 8, borderRadius: "9999px" }}
      >
        <span className="text-[11px] font-bold tabular-nums" style={{ color }}>
          {label != null ? label : v}
        </span>
      </div>
    </div>
  );
};

// Recent-form pill — last 8 results, newest first.
const FormStrip = ({ form }) => {
  if (!form || !form.length) return <span className="text-[10px] text-gray-400">—</span>;
  const tone = (c) => {
    if (c === "W") return "bg-emerald-500 text-white";
    if (c === "L") return "bg-rose-500 text-white";
    if (c === "T") return "bg-amber-400 text-amber-900";
    return "bg-gray-300 text-gray-700"; // both_bad
  };
  return (
    <div className="inline-flex gap-0.5">
      {form.map((c, i) => (
        <span
          key={i}
          className={`inline-flex items-center justify-center text-[9px] font-bold w-4 h-4 rounded ${tone(c)}`}
          title={c === "W" ? "win" : c === "L" ? "loss" : c === "T" ? "tie" : "both bad"}
        >
          {c}
        </span>
      ))}
    </div>
  );
};

const Pill = ({ children, className = "" }) => (
  <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium ${className}`}>
    {children}
  </span>
);

const StatTile = ({ label, value, accent = "from-blue-50 to-indigo-50 border-blue-100 text-blue-900", icon, hint }) => (
  <div className={`p-3 rounded-lg bg-gradient-to-br ${accent} border`}>
    <div className="text-[11px] uppercase tracking-wide font-semibold opacity-75 flex items-center gap-1">
      {icon}
      {label}
    </div>
    <div className="text-xl font-bold tabular-nums leading-tight">{value}</div>
    {hint && <div className="text-[10px] opacity-70">{hint}</div>}
  </div>
);

// ─── side-by-side blind compare ─────────────────────────────────────────────

const BlindResponse = ({ side, payload, revealed, truth, vote, busy, onPick }) => {
  const tone = SIDE_TONE[side];
  const provider = revealed ? truth?.split(":", 1)[0] : null;
  const model = revealed ? truth?.split(":")?.slice(1).join(":") : null;
  const isWinner = revealed && (
    (side === "a" && vote === "a") || (side === "b" && vote === "b")
  );
  const isLoser = revealed && !isWinner && vote !== "tie" && vote !== "both_bad";

  return (
    <div
      className={`relative rounded-xl border bg-white shadow-sm transition-all ${
        revealed
          ? isWinner
            ? "ring-2 ring-emerald-500 border-emerald-300 shadow-md"
            : isLoser
              ? "opacity-60"
              : "ring-1 ring-amber-300 border-amber-200"
          : `hover:shadow-md hover:-translate-y-0.5 ${tone.border}`
      }`}
    >
      {/* Header */}
      <div className={`flex items-center justify-between gap-2 px-4 py-3 rounded-t-xl bg-gradient-to-r ${tone.grad} border-b ${tone.border}`}>
        <div className="flex items-center gap-2">
          <span className={`inline-flex items-center justify-center w-9 h-9 rounded-full text-base font-black shadow-sm ${tone.letter}`}>
            {side === "a" ? "A" : "B"}
          </span>
          {revealed ? (
            <div className="flex items-center gap-2">
              <span className={`w-2 h-2 rounded-full ${PROVIDER_DOT[provider] || "bg-gray-400"}`} />
              <div>
                <div className={`text-xs font-semibold ${PROVIDER_TEXT[provider] || "text-gray-700"}`}>{provider}</div>
                <div className="text-[11px] text-gray-700 font-mono leading-tight">{model}</div>
              </div>
            </div>
          ) : (
            <div className="text-xs font-semibold text-gray-600 inline-flex items-center gap-1">
              <EyeOff className="w-3 h-3" />
              hidden until you vote
            </div>
          )}
        </div>
        {revealed && isWinner && (
          <Pill className="bg-emerald-500 text-white">
            <Crown className="w-3 h-3" /> your pick
          </Pill>
        )}
        {revealed && isLoser && (
          <Pill className="bg-gray-200 text-gray-700">runner-up</Pill>
        )}
      </div>

      {/* Body */}
      <ScrollArea className="max-h-72">
        <div className="px-4 py-3">
          <pre className="whitespace-pre-wrap break-words font-sans text-sm leading-relaxed text-gray-800 m-0">
            {payload?.response || ""}
          </pre>
        </div>
      </ScrollArea>

      {/* Metric row */}
      <div className="px-4 py-2 border-t bg-gray-50 rounded-b-xl flex flex-wrap gap-2 items-center text-[11px] text-gray-600">
        <span className="inline-flex items-center gap-1"><Hash className="w-3 h-3" />{payload?.response_chars} chars</span>
        <span className="inline-flex items-center gap-1">⏱ {fmtLat(payload?.latency)}</span>
        <span className="inline-flex items-center gap-1">{fmtCost(payload?.cost_usd)}</span>
        {payload?.total_tokens != null && (
          <span className="inline-flex items-center gap-1">↯ {payload.total_tokens} tok</span>
        )}
        {!revealed && (
          <Button
            size="sm"
            variant={side === "a" ? "default" : "outline"}
            disabled={busy}
            onClick={() => onPick(side)}
            className={`ml-auto h-7 px-3 ${
              side === "a"
                ? "bg-gradient-to-r from-indigo-600 to-violet-600 hover:from-indigo-700 hover:to-violet-700 text-white shadow"
                : "bg-gradient-to-r from-rose-600 to-orange-500 hover:from-rose-700 hover:to-orange-600 text-white border-0 shadow"
            }`}
          >
            {side === "a" ? "👈" : "👉"} {side.toUpperCase()} wins
            <span className="ml-1 text-[10px] opacity-80">[{side === "a" ? "1" : "2"}]</span>
          </Button>
        )}
      </div>
    </div>
  );
};

// ─── pair-matrix heatmap ────────────────────────────────────────────────────

const Matrix = ({ matrix }) => {
  const models = matrix?.models || [];
  const cells = matrix?.cells || [];
  if (models.length < 2) {
    return (
      <div className="p-4 text-center text-sm text-gray-500 border border-dashed rounded-lg">
        Need at least 2 models on the leaderboard to draw the head-to-head matrix.
      </div>
    );
  }
  // Map (a,b) → cell for fast lookup, then mirror.
  const map = new Map();
  cells.forEach(c => map.set(`${c.a}|${c.b}`, c));
  const lookup = (rowKey, colKey) => {
    if (rowKey === colKey) return null;
    const direct = map.get(`${rowKey}|${colKey}`);
    if (direct) return { wr: direct.win_rate_a, total: direct.total };
    const flipped = map.get(`${colKey}|${rowKey}`);
    if (!flipped) return { wr: null, total: 0 };
    const wr = flipped.win_rate_a == null ? null : (100 - flipped.win_rate_a);
    return { wr, total: flipped.total };
  };
  const shortLabel = (key) => {
    const [, m] = key.split(":", 2);
    return m && m.length > 14 ? m.slice(0, 14) + "…" : (m || key);
  };
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-[11px]">
        <thead>
          <tr>
            <th className="p-1 text-right text-gray-500"></th>
            {models.map(k => (
              <th key={k} className="p-1 text-center font-medium text-gray-700" title={k}>
                <span className={`w-1.5 h-1.5 rounded-full inline-block mr-1 ${PROVIDER_DOT[k.split(":",1)[0]] || "bg-gray-400"}`} />
                {shortLabel(k)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {models.map(rowKey => (
            <tr key={rowKey}>
              <th className="p-1 pr-2 text-right font-medium text-gray-700 text-[11px] whitespace-nowrap" title={rowKey}>
                <span className={`w-1.5 h-1.5 rounded-full inline-block mr-1 ${PROVIDER_DOT[rowKey.split(":",1)[0]] || "bg-gray-400"}`} />
                {shortLabel(rowKey)}
              </th>
              {models.map(colKey => {
                if (rowKey === colKey) {
                  return (
                    <td key={colKey} className="p-1 text-center bg-gray-50 text-gray-300">—</td>
                  );
                }
                const { wr, total } = lookup(rowKey, colKey);
                if (wr == null) {
                  return (
                    <td key={colKey} className="p-1 text-center text-gray-300 border border-gray-100">·</td>
                  );
                }
                const color = ramp(wr);
                return (
                  <td
                    key={colKey}
                    className="p-0 text-center border border-white"
                    style={{
                      background: `linear-gradient(135deg, ${color}66, ${color}22)`,
                      color,
                    }}
                    title={`${rowKey} vs ${colKey} — ${wr.toFixed(1)}% win rate (${total} games)`}
                  >
                    <div className="px-2 py-1 font-bold tabular-nums">{wr.toFixed(0)}%</div>
                    <div className="text-[9px] text-gray-600">{total}g</div>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

// ─── leaderboard row ────────────────────────────────────────────────────────

const RankRibbon = ({ rank }) => {
  if (rank === 1) return <span className="text-base">🥇</span>;
  if (rank === 2) return <span className="text-base">🥈</span>;
  if (rank === 3) return <span className="text-base">🥉</span>;
  return <span className="text-[11px] font-bold text-gray-500 w-5 text-center">#{rank}</span>;
};

const LeaderboardRow = ({ row, deltaRating, prior = 1500 }) => {
  // Visualise rating relative to the prior — anchor 0 ELO above prior at 0%
  // and +250 ELO at 100% (ELO of 1750 = clear top-tier in a small voting pool).
  const ratingPct = Math.max(0, Math.min(100, ((row.rating - prior + 50) / 300) * 100));
  const provider = row.provider;
  return (
    <div className="grid grid-cols-12 gap-2 items-center px-3 py-2 rounded-lg border border-gray-200 bg-white hover:shadow-sm transition-shadow">
      <div className="col-span-1 flex items-center justify-center"><RankRibbon rank={row.rank} /></div>
      <div className="col-span-4 flex items-center gap-2 min-w-0">
        <span className={`w-2 h-2 rounded-full shrink-0 ${PROVIDER_DOT[provider] || "bg-gray-400"}`} />
        <div className="min-w-0">
          <div className={`text-xs font-bold truncate ${PROVIDER_TEXT[provider] || "text-gray-700"}`}>{provider}</div>
          <div className="text-[11px] text-gray-700 font-mono truncate">{row.model}</div>
        </div>
      </div>
      <div className="col-span-2 text-center">
        <div className="text-base font-bold tabular-nums">{row.rating.toFixed(0)}</div>
        {deltaRating != null && (
          <div className={`text-[10px] tabular-nums ${deltaRating > 0 ? "text-emerald-600" : deltaRating < 0 ? "text-rose-600" : "text-gray-500"}`}>
            {deltaRating > 0 ? "+" : ""}{deltaRating.toFixed(1)}
          </div>
        )}
        <div className="h-1.5 mt-1 rounded-full bg-gray-100 overflow-hidden">
          <div
            className="h-full bg-gradient-to-r from-indigo-500 via-violet-500 to-fuchsia-500"
            style={{ width: `${ratingPct}%` }}
          />
        </div>
      </div>
      <div className="col-span-2 text-center text-[11px] tabular-nums">
        <div className="font-medium">{row.games}</div>
        <div className="text-gray-500">{row.wins}W · {row.losses}L · {row.ties}T</div>
      </div>
      <div className="col-span-1 text-center">
        <span className="text-xs font-bold tabular-nums" style={{ color: ramp(row.win_rate) }}>
          {row.win_rate.toFixed(0)}%
        </span>
      </div>
      <div className="col-span-2 flex items-center justify-end pr-1">
        <FormStrip form={row.recent_form} />
      </div>
    </div>
  );
};

// ─── recent feed entry ──────────────────────────────────────────────────────

const RecentVoteRow = ({ v, onUndo }) => {
  const winner = v.winner;
  const tag = winner === "tie" ? "tie" : winner === "both_bad" ? "both bad" :
              `${winner === "a" ? "A" : "B"} won`;
  const tagTone =
    winner === "a" ? "bg-indigo-100 text-indigo-700" :
    winner === "b" ? "bg-rose-100 text-rose-700" :
    winner === "tie" ? "bg-amber-100 text-amber-700" :
    "bg-gray-200 text-gray-600";
  const judgeMatch = (winner === "a" || winner === "b") && v.judge_winner &&
    ((winner === "a" && v.judge_winner === v.model_a) || (winner === "b" && v.judge_winner === v.model_b));
  return (
    <div className="px-3 py-2 rounded-md border border-gray-200 bg-white text-[11px] flex items-center gap-2">
      <Pill className={tagTone}>{tag}</Pill>
      <span className="text-gray-700 font-mono truncate flex-1" title={`${v.model_a} vs ${v.model_b}`}>
        <span className="text-indigo-700">{v.model_a.split(":")[1]?.slice(0, 16) || v.model_a}</span>
        <span className="text-gray-400 mx-1">vs</span>
        <span className="text-rose-700">{v.model_b.split(":")[1]?.slice(0, 16) || v.model_b}</span>
      </span>
      {v.judge_winner && (
        <Pill className={judgeMatch ? "bg-emerald-100 text-emerald-700" : "bg-orange-100 text-orange-700"}>
          {judgeMatch ? "✓ judge agree" : "✗ judge disagree"}
        </Pill>
      )}
      <span className="text-gray-500 text-[10px] whitespace-nowrap">{fmtRel(v.created_at)}</span>
      <Button
        size="sm"
        variant="ghost"
        className="h-6 px-1.5 text-gray-400 hover:text-rose-600"
        onClick={() => onUndo(v.id)}
        title="Undo this vote"
      >
        <Undo2 className="w-3 h-3" />
      </Button>
    </div>
  );
};

// ─── main panel ────────────────────────────────────────────────────────────

export default function VotePanel({ initialRunId, onClearInitialRunId }) {
  const [pair, setPair] = useState(null);
  const [pairLoading, setPairLoading] = useState(false);
  const [pairError, setPairError] = useState(null);

  const [vote, setVote] = useState(null);             // 'a' | 'b' | 'tie' | 'both_bad'
  const [revealed, setRevealed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [lastVoteId, setLastVoteId] = useState(null);

  const [leaderboard, setLeaderboard] = useState([]);
  const [meta, setMeta] = useState({ k: 24, prior: 1500, n_votes: 0, n_models: 0 });
  const [matrix, setMatrix] = useState(null);
  const [agreement, setAgreement] = useState(null);
  const [recent, setRecent] = useState([]);
  const [stats, setStats] = useState(null);

  const [showResponses, setShowResponses] = useState(true);
  const [voter, setVoter] = useState(() => {
    try { return localStorage.getItem("llm_arena_voter") || ""; } catch { return ""; }
  });
  const [stickyRunId, setStickyRunId] = useState(initialRunId || null);

  // Cache leaderboard before vote so we can derive ΔELO chips after.
  const beforeRatingsRef = useRef({});

  // ── fetchers ────────────────────────────────────────────────────────────
  const fetchPair = useCallback(async (overrideRunId = null) => {
    setPairLoading(true);
    setPairError(null);
    setVote(null);
    setRevealed(false);
    setLastVoteId(null);
    try {
      const res = await ApiService.arenaPair({ runId: overrideRunId ?? stickyRunId ?? undefined });
      if (!res.success) throw new Error(res.error || "could not sample a pair");
      setPair(res.pair);
    } catch (e) {
      setPair(null);
      setPairError(e.message || "failed to sample a pair");
    } finally {
      setPairLoading(false);
    }
  }, [stickyRunId]);

  const fetchSidebar = useCallback(async () => {
    try {
      const [lb, mtx, ag, rec, st] = await Promise.all([
        ApiService.arenaLeaderboard(),
        ApiService.arenaMatrix({ topN: 8 }),
        ApiService.arenaAgreement(),
        ApiService.arenaRecent({ limit: 12 }),
        ApiService.arenaStats(),
      ]);
      setLeaderboard(lb.leaderboard || []);
      setMeta(lb.meta || {});
      setMatrix(mtx.matrix || null);
      setAgreement(ag.agreement || null);
      setRecent(rec.votes || []);
      setStats(st.stats || null);
    } catch (e) {
      // Non-fatal — just keep prior values.
      console.warn("sidebar refresh failed:", e);
    }
  }, []);

  // Initial + reactive load.
  useEffect(() => { fetchPair(); }, [fetchPair]);
  useEffect(() => { fetchSidebar(); }, [fetchSidebar]);

  // ── reveal + vote handler ───────────────────────────────────────────────

  // Snapshot the leaderboard before submitting a vote so we can compute Δ.
  const snapshotRatings = useCallback(() => {
    const snap = {};
    leaderboard.forEach(r => { snap[r.key] = r.rating; });
    beforeRatingsRef.current = snap;
  }, [leaderboard]);

  const submitVote = useCallback(async (winner) => {
    if (!pair || busy) return;
    setBusy(true);
    snapshotRatings();
    const truth = pair._truth || {};
    try {
      const res = await ApiService.arenaVote({
        run_id:        pair.run_id,
        model_a:       truth.a,
        model_b:       truth.b,
        winner,
        voter:         voter || null,
        judge_winner:  pair.judge_winner || null,
        prompt_hash:   pair.prompt_hash || null,
        prompt_preview: (pair.prompt || "").slice(0, 200),
        latency_a:     pair.a?.latency,
        latency_b:     pair.b?.latency,
        cost_a:        pair.a?.cost_usd,
        cost_b:        pair.b?.cost_usd,
      });
      if (!res.success) throw new Error(res.error || "vote failed");
      setVote(winner);
      setRevealed(true);
      setLastVoteId(res.vote_id);
      setLeaderboard(res.leaderboard || []);
      setMeta(res.meta || {});
      // Refresh secondary panels in the background so the head-to-head matrix
      // and recent feed catch the new row.
      fetchSidebar();
      const tag = winner === "tie" ? "Tie recorded" :
                  winner === "both_bad" ? "Marked both bad — no rating change" :
                  `${truth[winner]?.split(":")[1] || winner.toUpperCase()} wins`;
      toast.success(tag);
    } catch (e) {
      toast.error(`Vote failed: ${e.message}`);
    } finally {
      setBusy(false);
    }
  }, [pair, busy, voter, snapshotRatings, fetchSidebar]);

  const undoLast = useCallback(async () => {
    if (!lastVoteId) return;
    try {
      await ApiService.arenaUndo(lastVoteId);
      toast.success("Vote undone");
      setLastVoteId(null);
      setRevealed(false);
      setVote(null);
      fetchSidebar();
      fetchPair();
    } catch (e) {
      toast.error(`Undo failed: ${e.message}`);
    }
  }, [lastVoteId, fetchPair, fetchSidebar]);

  const undoFromRecent = useCallback(async (vid) => {
    try {
      await ApiService.arenaUndo(vid);
      toast.success("Vote undone");
      if (vid === lastVoteId) {
        setLastVoteId(null);
      }
      fetchSidebar();
    } catch (e) {
      toast.error(`Undo failed: ${e.message}`);
    }
  }, [lastVoteId, fetchSidebar]);

  // Persist voter handle.
  useEffect(() => {
    try {
      if (voter) localStorage.setItem("llm_arena_voter", voter);
      else localStorage.removeItem("llm_arena_voter");
    } catch { /* ignore */ }
  }, [voter]);

  // Keyboard shortcuts: 1 = A, 2 = B, = = Tie, 0 = Both bad, n = next pair.
  useEffect(() => {
    const onKey = (e) => {
      if (e.target?.tagName === "INPUT" || e.target?.tagName === "TEXTAREA") return;
      if (busy || !pair) return;
      if (revealed) {
        if (e.key === "n" || e.key === "N") fetchPair();
        return;
      }
      if (e.key === "1") submitVote("a");
      else if (e.key === "2") submitVote("b");
      else if (e.key === "=" || e.key === "+") submitVote("tie");
      else if (e.key === "0") submitVote("both_bad");
      else if (e.key === "n" || e.key === "N") fetchPair();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [busy, pair, revealed, submitVote, fetchPair]);

  // ── derived ─────────────────────────────────────────────────────────────

  const truth = pair?._truth || {};
  const beforeMap = beforeRatingsRef.current || {};
  const deltaFor = (key) => {
    const before = beforeMap[key];
    const row = leaderboard.find(r => r.key === key);
    if (!row || before == null) return null;
    return row.rating - before;
  };

  const totalRated = useMemo(() => stats?.n_votes ?? meta?.n_votes ?? 0, [stats, meta]);

  const reveal = (key) => {
    const [provider, ...rest] = (key || "").split(":");
    return { provider, model: rest.join(":") };
  };

  // Top of leaderboard for the headline crown.
  const champion = leaderboard[0];

  // Clear deeplink so subsequent navigations don't keep replaying the same run.
  useEffect(() => {
    if (initialRunId && pair?.run_id === initialRunId) {
      onClearInitialRunId && onClearInitialRunId();
    }
  }, [initialRunId, pair, onClearInitialRunId]);

  // ── render ──────────────────────────────────────────────────────────────

  return (
    <Card className="shadow-lg border-0 bg-white/60 backdrop-blur-sm">
      <CardHeader className="pb-4">
        <div className="flex items-center justify-between flex-wrap gap-3">
          <CardTitle className="flex items-center gap-2 text-lg">
            <Trophy className="w-5 h-5 text-amber-500" />
            Personal Chatbot Arena
            <span className="text-[10px] uppercase tracking-wider bg-gradient-to-r from-amber-500 to-rose-500 text-white px-1.5 py-0.5 rounded">new</span>
            <span className="text-xs font-normal text-gray-500">— blind A/B vote · ELO leaderboard</span>
          </CardTitle>
          <div className="flex items-center gap-2 flex-wrap">
            <Input
              value={voter}
              onChange={e => setVoter(e.target.value)}
              placeholder="Your handle (optional)"
              className="h-8 w-44 text-sm"
            />
            {stickyRunId && (
              <Pill className="bg-violet-100 text-violet-700">
                pinned to run {stickyRunId.slice(0, 6)}
                <button
                  className="hover:text-violet-900 ml-1"
                  onClick={() => { setStickyRunId(null); fetchPair(null); }}
                  aria-label="clear pinned run"
                >
                  <XCircle className="w-3 h-3" />
                </button>
              </Pill>
            )}
            <div className="flex items-center gap-1.5 text-xs text-gray-600">
              <Switch checked={showResponses} onCheckedChange={setShowResponses} className="scale-75" />
              {showResponses ? <Eye className="w-3.5 h-3.5" /> : <EyeOff className="w-3.5 h-3.5" />}
              read while voting
            </div>
            <Button onClick={() => fetchPair(null)} size="sm" variant="outline" className="gap-1">
              <RefreshCcw className="w-3.5 h-3.5" />
              Next pair
            </Button>
          </div>
        </div>
      </CardHeader>

      <CardContent className="space-y-6">
        {/* Stats banner */}
        <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
          <StatTile
            label="votes"
            value={stats?.n_votes ?? "—"}
            accent="from-amber-50 to-orange-50 border-amber-100 text-amber-900"
            icon={<Sparkles className="w-3 h-3" />}
            hint={stats?.n_voters ? `${stats.n_voters} voter${stats.n_voters === 1 ? "" : "s"}` : "no voters yet"}
          />
          <StatTile
            label="models"
            value={meta?.n_models ?? "—"}
            accent="from-indigo-50 to-violet-50 border-indigo-100 text-indigo-900"
            icon={<Bot className="w-3 h-3" />}
            hint={`${stats?.n_pairs ?? 0} unique pairs`}
          />
          <StatTile
            label="champion"
            value={champion ? champion.model : "—"}
            accent="from-emerald-50 to-teal-50 border-emerald-100 text-emerald-900"
            icon={<Crown className="w-3 h-3" />}
            hint={champion ? `${champion.rating.toFixed(0)} ELO · ${champion.games}g` : "needs ≥1 vote"}
          />
          <StatTile
            label="judge agreement"
            value={agreement?.agree_pct == null ? "—" : `${agreement.agree_pct}%`}
            accent="from-violet-50 to-fuchsia-50 border-violet-100 text-violet-900"
            icon={<Scale className="w-3 h-3" />}
            hint={agreement ? `${agreement.agree}/${agreement.n_decisive} decisive` : "no judged data"}
          />
          <StatTile
            label="ELO settings"
            value={`K=${meta?.k ?? 24}`}
            accent="from-sky-50 to-cyan-50 border-sky-100 text-sky-900"
            icon={<Zap className="w-3 h-3" />}
            hint={`prior ${meta?.prior ?? 1500}`}
          />
        </div>

        {/* Vote stage */}
        <div>
          {pairLoading && (
            <div className="rounded-xl border border-dashed bg-white p-8 text-center text-gray-500 text-sm">
              <RefreshCcw className="w-5 h-5 inline-block animate-spin mr-1" /> sampling pair…
            </div>
          )}
          {!pairLoading && pairError && (
            <div className="rounded-xl border border-rose-200 bg-rose-50 p-6 text-center">
              <div className="font-semibold text-rose-700 mb-1">{pairError}</div>
              <div className="text-xs text-rose-600 mb-3">Run an Arena (sidebar → Arena) and come back.</div>
              <Button size="sm" onClick={() => fetchPair(null)} variant="outline">
                <RefreshCcw className="w-3.5 h-3.5 mr-1" /> Try again
              </Button>
            </div>
          )}
          {!pairLoading && pair && (
            <div className="space-y-4">
              {/* Prompt header */}
              <div className="rounded-xl border bg-gradient-to-r from-slate-50 to-zinc-50 p-4">
                <div className="text-[10px] uppercase tracking-wide text-gray-500 mb-1 flex items-center gap-1">
                  <Hash className="w-3 h-3" /> prompt being judged
                  {pair.judge_winner && (
                    <span className="ml-2">
                      <Pill className="bg-violet-100 text-violet-700">
                        <Scale className="w-3 h-3" /> judge picked {pair.judge_winner.split(":")[1]?.slice(0, 24) || pair.judge_winner}
                      </Pill>
                    </span>
                  )}
                </div>
                <div className="text-sm text-gray-800 line-clamp-2 break-words">{pair.prompt || <i className="text-gray-400">no prompt</i>}</div>
                {pair.system_prompt ? (
                  <div className="text-[11px] text-gray-500 mt-1 line-clamp-1">
                    <span className="font-semibold mr-1">system:</span>{pair.system_prompt}
                  </div>
                ) : null}
              </div>

              {/* The two responses */}
              {showResponses && (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <BlindResponse
                    side="a"
                    payload={pair.a}
                    revealed={revealed}
                    truth={truth.a}
                    vote={vote}
                    busy={busy}
                    onPick={submitVote}
                  />
                  <BlindResponse
                    side="b"
                    payload={pair.b}
                    revealed={revealed}
                    truth={truth.b}
                    vote={vote}
                    busy={busy}
                    onPick={submitVote}
                  />
                </div>
              )}

              {/* Vote bar */}
              <div className="rounded-xl border bg-white p-3 flex flex-wrap items-center justify-center gap-2">
                {!revealed ? (
                  <>
                    <Button
                      size="default"
                      onClick={() => submitVote("a")}
                      disabled={busy}
                      className="bg-gradient-to-r from-indigo-600 to-violet-600 hover:from-indigo-700 hover:to-violet-700 text-white shadow gap-1"
                    >
                      <ArrowRight className="w-4 h-4 -scale-x-100" />
                      A wins <kbd className="ml-1 text-[10px] opacity-80 px-1 rounded bg-white/20">1</kbd>
                    </Button>
                    <Button
                      size="default"
                      onClick={() => submitVote("b")}
                      disabled={busy}
                      className="bg-gradient-to-r from-rose-600 to-orange-500 hover:from-rose-700 hover:to-orange-600 text-white shadow gap-1"
                    >
                      <ArrowRight className="w-4 h-4" />
                      B wins <kbd className="ml-1 text-[10px] opacity-80 px-1 rounded bg-white/20">2</kbd>
                    </Button>
                    <Button
                      size="default"
                      variant="outline"
                      onClick={() => submitVote("tie")}
                      disabled={busy}
                      className="gap-1 border-amber-300 text-amber-700 hover:bg-amber-50"
                    >
                      <HandshakeIcon className="w-4 h-4" />
                      Tie <kbd className="ml-1 text-[10px] opacity-80 px-1 rounded bg-amber-100">=</kbd>
                    </Button>
                    <Button
                      size="default"
                      variant="outline"
                      onClick={() => submitVote("both_bad")}
                      disabled={busy}
                      className="gap-1 border-gray-300 text-gray-600 hover:bg-gray-50"
                    >
                      <XCircle className="w-4 h-4" />
                      Both bad <kbd className="ml-1 text-[10px] opacity-80 px-1 rounded bg-gray-200">0</kbd>
                    </Button>
                    <Button
                      size="default"
                      variant="ghost"
                      onClick={() => fetchPair(null)}
                      disabled={busy}
                      className="text-gray-500 ml-auto"
                    >
                      Skip <kbd className="ml-1 text-[10px] opacity-80 px-1 rounded bg-gray-100">N</kbd>
                    </Button>
                  </>
                ) : (
                  <div className="w-full flex items-center justify-between gap-2 flex-wrap">
                    <div className="flex items-center gap-2 text-sm text-gray-700">
                      <Sparkles className="w-4 h-4 text-amber-500" />
                      Recorded.
                      {(vote === "a" || vote === "b") && deltaFor(truth[vote]) != null && (
                        <Pill className="bg-emerald-100 text-emerald-800">
                          <TrendingUp className="w-3 h-3" />
                          {truth[vote].split(":")[1]?.slice(0,18) || truth[vote]}
                          <span className="font-mono">+{deltaFor(truth[vote]).toFixed(1)}</span> ELO
                        </Pill>
                      )}
                      {(vote === "a" || vote === "b") && (
                        <Pill className="bg-rose-100 text-rose-800">
                          <TrendingDown className="w-3 h-3" />
                          {truth[vote === "a" ? "b" : "a"].split(":")[1]?.slice(0,18) || truth[vote === "a" ? "b" : "a"]}
                          {(() => {
                            const d = deltaFor(truth[vote === "a" ? "b" : "a"]);
                            return d == null ? <span className="font-mono">—</span>
                              : <span className="font-mono">{d > 0 ? "+" : ""}{d.toFixed(1)}</span>;
                          })()} ELO
                        </Pill>
                      )}
                      {vote === "tie" && (
                        <Pill className="bg-amber-100 text-amber-700">tie · half-point each</Pill>
                      )}
                      {vote === "both_bad" && (
                        <Pill className="bg-gray-200 text-gray-700">both bad · no rating change</Pill>
                      )}
                    </div>
                    <div className="flex items-center gap-2">
                      {lastVoteId && (
                        <Button size="sm" variant="ghost" onClick={undoLast} className="text-gray-500 hover:text-rose-600">
                          <Undo2 className="w-4 h-4 mr-1" /> Undo
                        </Button>
                      )}
                      <Button
                        size="sm"
                        onClick={() => fetchPair(null)}
                        className="bg-gradient-to-r from-amber-500 to-rose-500 hover:from-amber-600 hover:to-rose-600 text-white"
                      >
                        Next pair <kbd className="ml-1 text-[10px] opacity-80 px-1 rounded bg-white/20">N</kbd>
                      </Button>
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Leaderboard + sidebar grid */}
        <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
          <div className="xl:col-span-2 space-y-4">
            <Card className="border-0 bg-white shadow-sm">
              <CardHeader className="pb-3">
                <CardTitle className="text-sm flex items-center justify-between">
                  <span className="inline-flex items-center gap-2">
                    <Trophy className="w-4 h-4 text-amber-500" />
                    ELO Leaderboard
                  </span>
                  <span className="text-[11px] text-gray-500 font-normal">
                    {leaderboard.length} model{leaderboard.length === 1 ? "" : "s"} · {meta?.n_votes ?? 0} vote{meta?.n_votes === 1 ? "" : "s"}
                  </span>
                </CardTitle>
              </CardHeader>
              <CardContent className="pt-0 space-y-2">
                {leaderboard.length === 0 ? (
                  <div className="rounded-lg border border-dashed bg-white p-6 text-center text-sm text-gray-500">
                    Cast your first vote — the leaderboard fills in immediately.
                  </div>
                ) : (
                  <>
                    <div className="grid grid-cols-12 gap-2 px-3 text-[10px] uppercase tracking-wide text-gray-400 font-semibold">
                      <div className="col-span-1 text-center">#</div>
                      <div className="col-span-4">model</div>
                      <div className="col-span-2 text-center">rating</div>
                      <div className="col-span-2 text-center">games</div>
                      <div className="col-span-1 text-center">wr</div>
                      <div className="col-span-2 text-right pr-1">last 8</div>
                    </div>
                    {leaderboard.map(row => (
                      <LeaderboardRow
                        key={row.key}
                        row={row}
                        prior={meta?.prior}
                        deltaRating={deltaFor(row.key)}
                      />
                    ))}
                  </>
                )}
              </CardContent>
            </Card>

            {/* Head-to-head matrix */}
            <Card className="border-0 bg-white shadow-sm">
              <CardHeader className="pb-3">
                <CardTitle className="text-sm inline-flex items-center gap-2">
                  <Swords className="w-4 h-4 text-rose-500" />
                  Head-to-head matrix
                  <span className="text-[11px] text-gray-500 font-normal">
                    row's win rate vs. column · top 8
                  </span>
                </CardTitle>
              </CardHeader>
              <CardContent className="pt-0">
                <Matrix matrix={matrix} />
              </CardContent>
            </Card>
          </div>

          <div className="space-y-4">
            {/* Agreement card */}
            <Card className="border-0 bg-gradient-to-br from-violet-50 to-fuchsia-50 shadow-sm">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm inline-flex items-center gap-2">
                  <Scale className="w-4 h-4 text-violet-600" />
                  Judge ↔ human agreement
                </CardTitle>
              </CardHeader>
              <CardContent className="pt-0">
                {!agreement || !agreement.n_decisive ? (
                  <div className="text-xs text-gray-600">
                    Cast votes on judged runs to populate this metric. The
                    judge's #1 pick is compared against your A / B choice on
                    every decisive vote.
                  </div>
                ) : (
                  <div className="space-y-3">
                    <div className="flex items-center gap-3">
                      <Ring value={agreement.agree_pct ?? 0} size={56} accent={ramp(agreement.agree_pct ?? 0)} label={`${agreement.agree_pct}%`} />
                      <div>
                        <div className="text-xs font-semibold text-violet-900">{agreement.agree} / {agreement.n_decisive} decisive votes match the judge</div>
                        <div className="text-[11px] text-violet-700">total considered: {agreement.n}</div>
                      </div>
                    </div>
                    {agreement.per_model.length > 0 && (
                      <div className="space-y-1">
                        <div className="text-[10px] uppercase tracking-wide text-violet-800/80 font-semibold">per-model agreement (when judge picked it)</div>
                        {agreement.per_model.slice(0, 5).map(row => (
                          <div key={row.key} className="text-[11px] flex items-center gap-2">
                            <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${PROVIDER_DOT[row.provider] || "bg-gray-400"}`} />
                            <span className="font-mono truncate flex-1">{row.model}</span>
                            <span className="text-violet-900 tabular-nums">{row.agree}/{row.n}</span>
                            <span className="font-bold tabular-nums" style={{ color: ramp(row.agree_pct) }}>{row.agree_pct}%</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Recent feed */}
            <Card className="border-0 bg-white shadow-sm">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm inline-flex items-center gap-2">
                  <Flame className="w-4 h-4 text-orange-500" />
                  Recent votes
                </CardTitle>
              </CardHeader>
              <CardContent className="pt-0 space-y-1.5">
                {recent.length === 0 ? (
                  <div className="text-xs text-gray-500">No votes yet — be the first.</div>
                ) : (
                  recent.map(v => <RecentVoteRow key={v.id} v={v} onUndo={undoFromRecent} />)
                )}
              </CardContent>
            </Card>

            {/* Help card */}
            <Card className="border-0 bg-gradient-to-br from-amber-50 to-rose-50 shadow-sm">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm inline-flex items-center gap-2">
                  <Award className="w-4 h-4 text-amber-600" />
                  How it works
                </CardTitle>
              </CardHeader>
              <CardContent className="pt-0 text-[12px] text-amber-900 space-y-1.5">
                <div>• Each pair is sampled from a real Arena run; provider/model are hidden until you vote.</div>
                <div>• Wins/losses feed an <span className="font-semibold">ELO replay</span> with K={meta?.k ?? 24}, prior {meta?.prior ?? 1500}.</div>
                <div>• <span className="font-semibold">Both bad</span> records the no-info case (no rating change).</div>
                <div>• Shortcuts: <kbd className="px-1 bg-white rounded">1</kbd>/<kbd className="px-1 bg-white rounded">2</kbd>/<kbd className="px-1 bg-white rounded">=</kbd>/<kbd className="px-1 bg-white rounded">0</kbd>/<kbd className="px-1 bg-white rounded">N</kbd>.</div>
              </CardContent>
            </Card>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
