import React, { useEffect, useMemo, useState, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  TrendingUp,
  TrendingDown,
  Minus,
  RefreshCw,
  Trophy,
  DollarSign,
  Gauge,
  Zap,
  Crown,
  Sparkles,
  ScatterChart,
  Coins,
  ArrowUpDown,
  ClipboardCopy,
  Award,
  Activity,
} from "lucide-react";
import { toast } from "sonner";
import ApiService from "../services/api";

// ─── Formatting helpers ──────────────────────────────────────────────────────

const fmtCost = (c) => {
  if (c == null) return "—";
  if (c === 0) return "free";
  if (c < 0.001) return `$${(c * 1000).toFixed(3)}m`;
  return `$${Number(c).toFixed(4)}`;
};
const fmtMoney = (c) => (c == null ? "—" : `$${Number(c).toFixed(c < 1 ? 4 : 2)}`);
const fmtNum = (n, d = 0) => (n == null ? "—" : Number(n).toFixed(d));
const fmtQpd = (q) => {
  if (q == null) return "—";
  if (q >= 1000) return `${(q / 1000).toFixed(1)}k`;
  return Number(q).toFixed(0);
};
const fmtDay = (epoch) =>
  new Date(Number(epoch) * 1000).toLocaleDateString(undefined, { month: "short", day: "numeric" });

// Brand-ish provider hues, with a deterministic fallback for unknowns.
const PROVIDER_HUE = {
  OpenAI: "#10a37f",
  Anthropic: "#d97757",
  Google: "#4285f4",
  August: "#8b5cf6",
};
const hueFor = (provider) => {
  if (PROVIDER_HUE[provider]) return PROVIDER_HUE[provider];
  let h = 0;
  for (const ch of provider || "?") h = (h * 31 + ch.charCodeAt(0)) % 360;
  return `hsl(${h} 65% 50%)`;
};

// ─── Small reusable bits ───────────────────────────────────────────────────

const QualityRing = ({ value, size = 40 }) => {
  const has = value != null && !Number.isNaN(Number(value));
  const v = has ? Math.max(0, Math.min(100, Math.round(Number(value)))) : 0;
  const ringColor = has ? `hsl(${Math.round(v * 1.2)} 80% 48%)` : "#cbd5e1";
  return (
    <div
      className="relative inline-flex items-center justify-center shrink-0"
      style={{
        width: size,
        height: size,
        borderRadius: "9999px",
        background: has
          ? `conic-gradient(${ringColor} ${v * 3.6}deg, #e5e7eb ${v * 3.6}deg)`
          : "conic-gradient(#cbd5e1 0deg, #e5e7eb 0deg)",
      }}
      title={has ? `quality ${v}/100` : "no judged runs"}
    >
      <div
        className="rounded-full bg-white flex items-center justify-center font-semibold text-gray-800"
        style={{ width: size - 7, height: size - 7, fontSize: size > 38 ? 12 : 10 }}
      >
        {has ? v : "—"}
      </div>
    </div>
  );
};

const TrendChip = ({ pct }) => {
  if (pct == null)
    return (
      <span className="inline-flex items-center gap-0.5 text-[11px] text-gray-400">
        <Minus className="w-3 h-3" /> n/a
      </span>
    );
  const up = pct >= 0;
  // Spend going *up* is neutral-to-bad for a cost dashboard — paint it amber/rose.
  return (
    <span
      className={`inline-flex items-center gap-0.5 text-[11px] font-medium ${
        up ? "text-rose-500" : "text-emerald-600"
      }`}
    >
      {up ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
      {up ? "+" : ""}
      {pct}%
    </span>
  );
};

// ─── Efficiency frontier scatter ─────────────────────────────────────────────
// x = avg cost per response ($, log scale), y = judge composite (0-100).
// Frontier (non-dominated) models are joined by a line; dominated ones fade.
const FrontierChart = ({ frontier, scorecards, hovered, setHovered }) => {
  const W = 720;
  const H = 430;
  const padL = 56;
  const padR = 22;
  const padT = 22;
  const padB = 52;
  const plotW = W - padL - padR;
  const plotH = H - padT - padB;

  const cardByKey = useMemo(() => {
    const m = {};
    (scorecards || []).forEach((c) => (m[c.key] = c));
    return m;
  }, [scorecards]);

  const points = (frontier?.points || []).filter((p) => p.cost > 0 && p.quality != null);

  const scales = useMemo(() => {
    if (points.length === 0) return null;
    const logs = points.map((p) => Math.log10(p.cost));
    let lxMin = Math.min(...logs);
    let lxMax = Math.max(...logs);
    if (lxMax - lxMin < 0.15) {
      lxMin -= 0.3;
      lxMax += 0.3;
    } else {
      lxMin -= 0.12;
      lxMax += 0.12;
    }
    const qs = points.map((p) => p.quality);
    let qMin = Math.floor((Math.min(...qs) - 6) / 10) * 10;
    let qMax = Math.ceil((Math.max(...qs) + 3) / 10) * 10;
    qMin = Math.max(0, qMin);
    qMax = Math.min(100, Math.max(qMax, qMin + 20));
    return { lxMin, lxMax, qMin, qMax };
  }, [points]);

  if (!scales || points.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-64 text-gray-400 gap-2">
        <ScatterChart className="w-8 h-8" />
        <p className="text-sm">
          No models can be placed yet — the frontier needs at least one{" "}
          <span className="font-medium text-gray-600">judged</span> run with a known cost.
        </p>
        <p className="text-xs">
          Run an Arena fan-out, hit <span className="font-medium">Judge responses</span>, and they'll
          appear here.
        </p>
      </div>
    );
  }

  const { lxMin, lxMax, qMin, qMax } = scales;
  const sx = (cost) => padL + ((Math.log10(cost) - lxMin) / (lxMax - lxMin)) * plotW;
  const sy = (q) => padT + (1 - (q - qMin) / (qMax - qMin)) * plotH;
  const rOf = (appearances) =>
    Math.max(5, Math.min(15, 5 + Math.sqrt(appearances || 1) * 2.4));

  // X ticks at 5 evenly-spaced log positions; Y every 10.
  const xTicks = Array.from({ length: 5 }, (_, i) => {
    const lx = lxMin + ((lxMax - lxMin) * i) / 4;
    return Math.pow(10, lx);
  });
  const yTicks = [];
  for (let q = qMin; q <= qMax + 0.001; q += 10) yTicks.push(q);

  const frontierPts = (frontier.frontier || [])
    .map((k) => points.find((p) => p.key === k))
    .filter(Boolean)
    .sort((a, b) => a.cost - b.cost);

  const linePath = frontierPts.map((p) => `${sx(p.cost)},${sy(p.quality)}`).join(" ");
  const areaPath =
    frontierPts.length > 1
      ? `M ${sx(frontierPts[0].cost)},${sy(qMin)} ` +
        frontierPts.map((p) => `L ${sx(p.cost)},${sy(p.quality)}`).join(" ") +
        ` L ${sx(frontierPts[frontierPts.length - 1].cost)},${sy(qMin)} Z`
      : "";

  return (
    <div className="relative w-full">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ maxHeight: 460 }}>
        <defs>
          <linearGradient id="frontierArea" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#6366f1" stopOpacity="0.16" />
            <stop offset="1" stopColor="#6366f1" stopOpacity="0" />
          </linearGradient>
        </defs>

        {/* grid + y ticks */}
        {yTicks.map((q) => (
          <g key={`y${q}`}>
            <line x1={padL} y1={sy(q)} x2={W - padR} y2={sy(q)} stroke="#eef2f7" strokeWidth={1} />
            <text x={padL - 8} y={sy(q) + 3} textAnchor="end" fontSize="10" fill="#94a3b8">
              {q}
            </text>
          </g>
        ))}
        {/* x ticks */}
        {xTicks.map((c, i) => (
          <g key={`x${i}`}>
            <line x1={sx(c)} y1={padT} x2={sx(c)} y2={H - padB} stroke="#f5f7fa" strokeWidth={1} />
            <text x={sx(c)} y={H - padB + 16} textAnchor="middle" fontSize="10" fill="#94a3b8">
              {fmtCost(c)}
            </text>
          </g>
        ))}

        {/* axis labels */}
        <text
          x={padL + plotW / 2}
          y={H - 8}
          textAnchor="middle"
          fontSize="11"
          fill="#64748b"
          fontWeight="600"
        >
          cost per response →  (cheaper is better, log scale)
        </text>
        <text
          x={-(padT + plotH / 2)}
          y={15}
          textAnchor="middle"
          fontSize="11"
          fill="#64748b"
          fontWeight="600"
          transform="rotate(-90)"
        >
          ↑ quality (judge composite)
        </text>

        {/* frontier area + line */}
        {areaPath && <path d={areaPath} fill="url(#frontierArea)" />}
        {frontierPts.length > 1 && (
          <polyline
            points={linePath}
            fill="none"
            stroke="#6366f1"
            strokeWidth={2}
            strokeDasharray="2 0"
            strokeLinejoin="round"
            opacity={0.7}
          />
        )}

        {/* bubbles */}
        {points.map((p) => {
          const on = p.on_frontier;
          const isHover = hovered === p.key;
          const fill = hueFor(p.provider);
          return (
            <g
              key={p.key}
              style={{ cursor: "pointer" }}
              onMouseEnter={() => setHovered(p.key)}
              onMouseLeave={() => setHovered(null)}
            >
              <circle
                cx={sx(p.cost)}
                cy={sy(p.quality)}
                r={rOf(p.appearances) + (isHover ? 3 : 0)}
                fill={fill}
                fillOpacity={on ? 0.9 : 0.32}
                stroke={isHover ? "#1e293b" : on ? "#fff" : fill}
                strokeWidth={on ? 2 : 1}
              />
              {on && (
                <circle
                  cx={sx(p.cost)}
                  cy={sy(p.quality)}
                  r={rOf(p.appearances) + 4}
                  fill="none"
                  stroke={fill}
                  strokeWidth={1}
                  strokeOpacity={0.35}
                />
              )}
            </g>
          );
        })}
      </svg>

      {/* hover detail card pinned top-right of the plot */}
      {hovered && cardByKey[hovered] && (
        <div className="absolute top-2 right-3 bg-white/95 backdrop-blur border border-gray-200 rounded-lg shadow-lg px-3 py-2 text-xs max-w-[220px] pointer-events-none">
          <div className="flex items-center gap-1.5 font-semibold text-gray-800">
            <span
              className="inline-block w-2.5 h-2.5 rounded-full"
              style={{ background: hueFor(cardByKey[hovered].provider) }}
            />
            {cardByKey[hovered].model}
          </div>
          <div className="text-[10px] text-gray-400 mb-1">{cardByKey[hovered].provider}</div>
          <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 text-gray-600">
            <span>quality</span>
            <span className="text-right font-medium text-gray-800">
              {fmtNum(cardByKey[hovered].avg_composite, 1)}
            </span>
            <span>cost/resp</span>
            <span className="text-right font-medium text-gray-800">
              {fmtCost(cardByKey[hovered].avg_cost)}
            </span>
            <span>quality / $</span>
            <span className="text-right font-medium text-indigo-600">
              {fmtQpd(cardByKey[hovered].quality_per_dollar)}
            </span>
            <span>runs</span>
            <span className="text-right font-medium text-gray-800">
              {cardByKey[hovered].appearances}
            </span>
          </div>
          <div className="mt-1.5">
            {(frontier.points.find((p) => p.key === hovered) || {}).on_frontier ? (
              <span className="inline-flex items-center gap-1 text-emerald-600 font-medium">
                <Award className="w-3 h-3" /> on the efficient frontier
              </span>
            ) : (
              <span className="text-rose-500">
                dominated by{" "}
                {((frontier.points.find((p) => p.key === hovered) || {}).dominated_by || [])
                  .map((k) => (cardByKey[k] || {}).model || k)
                  .slice(0, 2)
                  .join(", ")}
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

// ─── Spend / quality timeline ────────────────────────────────────────────────
const SpendTimeline = ({ timeline }) => {
  if (!timeline || timeline.length === 0)
    return <div className="text-xs text-gray-400 italic py-6 text-center">no spend recorded yet</div>;
  const W = 720;
  const H = 150;
  const padL = 44;
  const padR = 16;
  const padT = 14;
  const padB = 26;
  const plotW = W - padL - padR;
  const plotH = H - padT - padB;
  const maxSpend = Math.max(...timeline.map((d) => d.spend), 1e-9);
  const n = timeline.length;
  const bw = Math.max(4, Math.min(40, (plotW / n) * 0.62));
  const cx = (i) => padL + (n === 1 ? plotW / 2 : (i / (n - 1)) * plotW);
  const scoreY = (s) => padT + (1 - s / 100) * plotH;

  const scored = timeline.map((d, i) => ({ ...d, i })).filter((d) => d.avg_top_score != null);

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ maxHeight: 170 }}>
      {/* spend bars */}
      {timeline.map((d, i) => {
        const h = (d.spend / maxSpend) * plotH;
        return (
          <g key={d.day}>
            <rect
              x={cx(i) - bw / 2}
              y={padT + plotH - h}
              width={bw}
              height={Math.max(0, h)}
              rx={2}
              fill="url(#spendGrad)"
            >
              <title>{`${fmtDay(d.day)} · ${fmtMoney(d.spend)} · ${d.runs} run${
                d.runs === 1 ? "" : "s"
              }`}</title>
            </rect>
            {(n <= 16 || i % Math.ceil(n / 12) === 0) && (
              <text x={cx(i)} y={H - 9} textAnchor="middle" fontSize="9" fill="#94a3b8">
                {fmtDay(d.day)}
              </text>
            )}
          </g>
        );
      })}
      {/* avg-quality line overlay */}
      {scored.length > 1 && (
        <polyline
          points={scored.map((d) => `${cx(d.i)},${scoreY(d.avg_top_score)}`).join(" ")}
          fill="none"
          stroke="#f59e0b"
          strokeWidth={1.8}
          strokeLinejoin="round"
        />
      )}
      {scored.map((d) => (
        <circle key={`s${d.day}`} cx={cx(d.i)} cy={scoreY(d.avg_top_score)} r={2.5} fill="#f59e0b">
          <title>{`avg top score ${d.avg_top_score}`}</title>
        </circle>
      ))}
      <defs>
        <linearGradient id="spendGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#6366f1" />
          <stop offset="1" stopColor="#a5b4fc" />
        </linearGradient>
      </defs>
    </svg>
  );
};

// ─── Sortable scorecard table ────────────────────────────────────────────────
const LOWER_BETTER = new Set(["avg_cost", "avg_latency"]);

const ScorecardTable = ({ scorecards, frontierKeys }) => {
  const [sortKey, setSortKey] = useState("quality_per_dollar");
  // `asc` tracks raw direction; first click on a column shows "best first".
  const [asc, setAsc] = useState(false);

  const sorted = useMemo(() => {
    const rows = [...(scorecards || [])];
    rows.sort((a, b) => {
      const av = a[sortKey];
      const bv = b[sortKey];
      if (av == null && bv == null) return 0;
      if (av == null) return 1; // nulls always sink
      if (bv == null) return -1;
      return asc ? av - bv : bv - av;
    });
    return rows;
  }, [scorecards, sortKey, asc]);

  const maxQpd = Math.max(...(scorecards || []).map((c) => c.quality_per_dollar || 0), 1);

  const head = (key, label, align = "right") => (
    <th
      className={`px-2 py-2 font-medium cursor-pointer select-none hover:text-gray-900 text-${align}`}
      onClick={() => {
        if (sortKey === key) setAsc((v) => !v);
        else {
          setSortKey(key);
          setAsc(LOWER_BETTER.has(key)); // best-first: ascending for cost/latency
        }
      }}
    >
      <span className="inline-flex items-center gap-1">
        {label}
        {sortKey === key && <ArrowUpDown className="w-3 h-3 text-indigo-500" />}
      </span>
    </th>
  );

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead className="text-gray-500 border-b border-gray-200">
          <tr>
            <th className="px-2 py-2 text-left font-medium">Model</th>
            {head("avg_composite", "Quality")}
            {head("avg_cost", "Cost/resp")}
            {head("quality_per_dollar", "Quality / $")}
            {head("avg_latency", "Latency")}
            {head("elo", "ELO")}
            {head("appearances", "Runs")}
          </tr>
        </thead>
        <tbody>
          {sorted.map((c) => {
            const onFrontier = frontierKeys.has(c.key);
            return (
              <tr
                key={c.key}
                className={`border-b border-gray-100 hover:bg-indigo-50/40 ${
                  onFrontier ? "bg-emerald-50/30" : ""
                }`}
              >
                <td className="px-2 py-2">
                  <div className="flex items-center gap-2">
                    <span
                      className="inline-block w-2.5 h-2.5 rounded-full shrink-0"
                      style={{ background: hueFor(c.provider) }}
                    />
                    <div className="min-w-0">
                      <div className="font-medium text-gray-800 truncate flex items-center gap-1">
                        {c.model}
                        {onFrontier && (
                          <Award className="w-3 h-3 text-emerald-500 shrink-0" />
                        )}
                      </div>
                      <div className="text-[10px] text-gray-400">{c.provider}</div>
                    </div>
                  </div>
                </td>
                <td className="px-2 py-2 text-right">
                  {c.avg_composite == null ? (
                    <span className="text-gray-300">un-judged</span>
                  ) : (
                    <span className="font-medium text-gray-800">{c.avg_composite}</span>
                  )}
                </td>
                <td className="px-2 py-2 text-right tabular-nums">{fmtCost(c.avg_cost)}</td>
                <td className="px-2 py-2 text-right">
                  {c.quality_per_dollar == null ? (
                    <span className="text-gray-300">—</span>
                  ) : (
                    <div className="flex items-center justify-end gap-1.5">
                      <div className="w-12 h-1.5 bg-gray-100 rounded-full overflow-hidden hidden sm:block">
                        <div
                          className="h-full bg-gradient-to-r from-indigo-400 to-violet-500"
                          style={{ width: `${(c.quality_per_dollar / maxQpd) * 100}%` }}
                        />
                      </div>
                      <span className="font-semibold text-indigo-600 tabular-nums w-9 text-right">
                        {fmtQpd(c.quality_per_dollar)}
                      </span>
                    </div>
                  )}
                </td>
                <td className="px-2 py-2 text-right tabular-nums text-gray-600">
                  {c.avg_latency == null ? "—" : `${c.avg_latency.toFixed(2)}s`}
                </td>
                <td className="px-2 py-2 text-right tabular-nums">
                  {c.elo == null ? (
                    <span className="text-gray-300">—</span>
                  ) : (
                    <span className="text-gray-700">
                      {Math.round(c.elo)}
                      <span className="text-[10px] text-gray-400"> · {c.elo_games}g</span>
                    </span>
                  )}
                </td>
                <td className="px-2 py-2 text-right tabular-nums text-gray-600">
                  {c.appearances}
                  {c.judge_wins > 0 && (
                    <span className="text-[10px] text-amber-500" title="judge wins">
                      {" "}
                      🏅{c.judge_wins}
                    </span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
};

// ─── Provider roll-up ────────────────────────────────────────────────────────
const ProviderRollup = ({ providers }) => {
  if (!providers || providers.length === 0)
    return <div className="text-xs text-gray-400 italic">no providers yet</div>;
  return (
    <div className="space-y-3">
      {providers.map((p) => (
        <div key={p.provider}>
          <div className="flex items-center justify-between text-xs mb-1">
            <span className="flex items-center gap-1.5 font-medium text-gray-700">
              <span
                className="inline-block w-2.5 h-2.5 rounded-full"
                style={{ background: hueFor(p.provider) }}
              />
              {p.provider}
              <span className="text-[10px] text-gray-400 font-normal">
                {p.models} model{p.models === 1 ? "" : "s"}
              </span>
            </span>
            <span className="text-gray-600 tabular-nums">
              {fmtMoney(p.spend)} · {p.spend_share}%
            </span>
          </div>
          <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
            <div
              className="h-full rounded-full"
              style={{ width: `${p.spend_share}%`, background: hueFor(p.provider) }}
            />
          </div>
          <div className="flex justify-between text-[10px] text-gray-400 mt-0.5">
            <span>{p.appearances} responses</span>
            <span>{p.avg_quality == null ? "un-judged" : `avg quality ${p.avg_quality}`}</span>
          </div>
        </div>
      ))}
    </div>
  );
};

// ─── KPI tile ────────────────────────────────────────────────────────────────
const KpiTile = ({ icon, label, value, sub, gradient }) => (
  <div className={`rounded-xl p-3 text-white shadow-sm bg-gradient-to-br ${gradient}`}>
    <div className="flex items-center gap-1.5 text-[11px] uppercase tracking-wider opacity-90">
      {React.createElement(icon, { className: "w-3.5 h-3.5" })}
      {label}
    </div>
    <div className="text-lg font-bold mt-1 leading-tight truncate">{value}</div>
    {sub && <div className="text-[11px] opacity-90 mt-0.5 truncate">{sub}</div>}
  </div>
);

// ─── Main panel ──────────────────────────────────────────────────────────────
export default function InsightsPanel() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [hovered, setHovered] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await ApiService.insights();
      if (res.success) setData(res);
    } catch (e) {
      toast.error(`Insights error: ${e.message}`);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const frontierKeys = useMemo(
    () => new Set(data?.frontier?.frontier || []),
    [data]
  );

  const copyBrief = () => {
    if (!data) return;
    const s = data.summary;
    const ref = (r) => (r ? `${r.provider}:${r.model}` : "—");
    const lines = [
      "# LLM Playground — Studio Insights",
      "",
      `- Total spend: ${fmtMoney(s.total_spend)} across ${s.n_runs} runs (${s.n_judged_runs} judged)`,
      `- Models evaluated: ${s.n_models}`,
      `- Best value: ${ref(s.best_value)} (${fmtQpd(s.best_value?.quality_per_dollar)} quality/$ at ${fmtCost(
        s.best_value?.avg_cost
      )})`,
      `- Top quality: ${ref(s.top_quality)} (${fmtNum(s.top_quality?.avg_composite, 1)})`,
      `- Cheapest: ${ref(s.cheapest)} (${fmtCost(s.cheapest?.avg_cost)})`,
      `- Spend last 7d: ${fmtMoney(s.spend_last_7d)} (${s.spend_trend_pct == null ? "n/a" : s.spend_trend_pct + "%"} vs prior)`,
      "",
      "## Efficient frontier (best quality-per-cost picks)",
      ...(data.frontier.frontier || []).map((k) => {
        const c = (data.scorecards || []).find((x) => x.key === k) || {};
        return `- ${k} — quality ${fmtNum(c.avg_composite, 1)}, ${fmtCost(c.avg_cost)}/resp, ${fmtQpd(
          c.quality_per_dollar
        )} q/$`;
      }),
    ];
    navigator.clipboard
      .writeText(lines.join("\n"))
      .then(() => toast.success("Insights brief copied"))
      .catch(() => toast.error("Copy failed"));
  };

  if (loading && !data) {
    return (
      <Card className="shadow-lg border-0 bg-white/60 backdrop-blur-sm">
        <CardContent className="flex flex-col items-center justify-center h-64 gap-3 text-gray-400">
          <RefreshCw className="w-6 h-6 animate-spin" />
          <p className="text-sm">Crunching your evaluation history…</p>
        </CardContent>
      </Card>
    );
  }

  const s = data?.summary || {};
  const empty = !data || s.n_runs === 0;

  return (
    <div className="space-y-4">
      <Card className="shadow-lg border-0 bg-white/60 backdrop-blur-sm">
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between flex-wrap gap-2">
            <CardTitle className="flex items-center gap-2 text-lg">
              <Gauge className="w-5 h-5 text-indigo-600" />
              Studio Insights
              <span className="text-xs font-normal text-gray-500">
                — which model is worth your money?
              </span>
            </CardTitle>
            <div className="flex items-center gap-2">
              <Button variant="outline" size="sm" onClick={copyBrief} disabled={empty}>
                <ClipboardCopy className="w-3.5 h-3.5 mr-1" /> Copy brief
              </Button>
              <Button variant="outline" size="sm" onClick={load}>
                <RefreshCw className={`w-3.5 h-3.5 mr-1 ${loading ? "animate-spin" : ""}`} /> Refresh
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {empty ? (
            <div className="flex flex-col items-center justify-center h-56 text-gray-400 gap-2">
              <Sparkles className="w-8 h-8" />
              <p className="text-sm font-medium text-gray-600">No runs to analyse yet</p>
              <p className="text-xs">
                Head to <span className="font-medium">Arena</span>, fan a prompt across a few models,
                and judge them — Insights builds itself from your history.
              </p>
            </div>
          ) : (
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
              <KpiTile
                icon={Coins}
                label="Total spend"
                value={fmtMoney(s.total_spend)}
                sub={`${s.n_runs} runs`}
                gradient="from-indigo-500 to-violet-600"
              />
              <KpiTile
                icon={Crown}
                label="Best value"
                value={s.best_value?.model || "—"}
                sub={s.best_value ? `${fmtQpd(s.best_value.quality_per_dollar)} q/$` : "judge a run"}
                gradient="from-emerald-500 to-teal-600"
              />
              <KpiTile
                icon={Trophy}
                label="Top quality"
                value={s.top_quality?.model || "—"}
                sub={s.top_quality ? `${fmtNum(s.top_quality.avg_composite, 1)} / 100` : "—"}
                gradient="from-amber-500 to-orange-600"
              />
              <KpiTile
                icon={DollarSign}
                label="Cheapest"
                value={s.cheapest?.model || "—"}
                sub={s.cheapest ? `${fmtCost(s.cheapest.avg_cost)}/resp` : "—"}
                gradient="from-sky-500 to-blue-600"
              />
              <KpiTile
                icon={Zap}
                label="Fastest"
                value={s.fastest?.model || "—"}
                sub={s.fastest?.avg_latency != null ? `${s.fastest.avg_latency.toFixed(2)}s` : "—"}
                gradient="from-fuchsia-500 to-pink-600"
              />
              <div className="rounded-xl p-3 shadow-sm bg-gradient-to-br from-slate-700 to-slate-900 text-white">
                <div className="flex items-center gap-1.5 text-[11px] uppercase tracking-wider opacity-90">
                  <Activity className="w-3.5 h-3.5" /> Spend 7d
                </div>
                <div className="text-lg font-bold mt-1 leading-tight">{fmtMoney(s.spend_last_7d)}</div>
                <div className="mt-0.5">
                  <TrendChip pct={s.spend_trend_pct} />
                </div>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {!empty && (
        <>
          <Card className="shadow-lg border-0 bg-white/70 backdrop-blur-sm">
            <CardHeader className="pb-2">
              <CardTitle className="flex items-center gap-2 text-base">
                <ScatterChart className="w-4 h-4 text-indigo-600" />
                Quality / Cost Efficiency Frontier
              </CardTitle>
              <p className="text-xs text-gray-500">
                Up-and-to-the-left wins: high quality, low cost. Models on the{" "}
                <span className="text-emerald-600 font-medium">frontier</span> are never dominated —
                the faded ones are strictly beaten on both axes by something else.{" "}
                {data.frontier.n_on_frontier}/{data.frontier.n_eligible} models are efficient.
              </p>
            </CardHeader>
            <CardContent>
              <FrontierChart
                frontier={data.frontier}
                scorecards={data.scorecards}
                hovered={hovered}
                setHovered={setHovered}
              />
              {/* provider legend */}
              <div className="flex items-center gap-4 flex-wrap mt-2 text-xs text-gray-500">
                {[...new Set((data.scorecards || []).map((c) => c.provider))].map((p) => (
                  <span key={p} className="inline-flex items-center gap-1.5">
                    <span
                      className="inline-block w-2.5 h-2.5 rounded-full"
                      style={{ background: hueFor(p) }}
                    />
                    {p}
                  </span>
                ))}
                <span className="inline-flex items-center gap-1 text-gray-400">
                  bubble size = # of runs
                </span>
              </div>
              {data.frontier.unplaced.length > 0 && (
                <p className="text-[11px] text-gray-400 mt-2">
                  {data.frontier.unplaced.length} model
                  {data.frontier.unplaced.length === 1 ? "" : "s"} not shown —{" "}
                  {data.frontier.unplaced.filter((u) => u.reason === "no_judge_score").length} need a
                  judge score, {data.frontier.unplaced.filter((u) => u.reason === "no_cost").length}{" "}
                  have no cost data.
                </p>
              )}
            </CardContent>
          </Card>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            <Card className="shadow-lg border-0 bg-white/70 backdrop-blur-sm lg:col-span-2">
              <CardHeader className="pb-2">
                <CardTitle className="flex items-center gap-2 text-base">
                  <Trophy className="w-4 h-4 text-amber-500" />
                  Model scorecards
                  <span className="text-xs font-normal text-gray-400">
                    — sortable · {data.scorecards.length} models
                  </span>
                </CardTitle>
              </CardHeader>
              <CardContent>
                <ScorecardTable scorecards={data.scorecards} frontierKeys={frontierKeys} />
              </CardContent>
            </Card>

            <Card className="shadow-lg border-0 bg-white/70 backdrop-blur-sm">
              <CardHeader className="pb-2">
                <CardTitle className="flex items-center gap-2 text-base">
                  <Coins className="w-4 h-4 text-indigo-600" />
                  Spend by provider
                </CardTitle>
              </CardHeader>
              <CardContent>
                <ProviderRollup providers={data.providers} />
              </CardContent>
            </Card>
          </div>

          <Card className="shadow-lg border-0 bg-white/70 backdrop-blur-sm">
            <CardHeader className="pb-2">
              <CardTitle className="flex items-center gap-2 text-base">
                <Activity className="w-4 h-4 text-indigo-600" />
                Spend & quality over time
                <span className="text-xs font-normal text-gray-400">
                  — bars: daily $ · line: avg top score
                </span>
              </CardTitle>
            </CardHeader>
            <CardContent>
              <SpendTimeline timeline={data.timeline} />
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
