"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  PulseAction,
  PulseCustomer,
  PulseMood,
  PulseReport,
  PulseRules,
  ProfileBucket,
  getPulse,
  getPulseRules,
  getPulseSample,
  pulseExportUrl,
} from "../../lib/api";

type WindowChoice = 1 | 7 | 14 | 30;
const WINDOW_CHOICES: WindowChoice[] = [1, 7, 14, 30];

const MOOD_BG: Record<PulseMood, string> = {
  calm:     "radial-gradient(120% 100% at 50% 0%, rgba(34,211,168,0.18) 0%, rgba(7,11,20,0) 65%)",
  watch:    "radial-gradient(120% 100% at 50% 0%, rgba(251,191,36,0.20) 0%, rgba(7,11,20,0) 65%)",
  active:   "radial-gradient(120% 100% at 50% 0%, rgba(251,146,60,0.22) 0%, rgba(7,11,20,0) 65%)",
  critical: "radial-gradient(120% 100% at 50% 0%, rgba(239,68,68,0.26) 0%, rgba(7,11,20,0) 65%)",
};

const BUCKET_HUE: Record<ProfileBucket, string> = {
  low: "#22d3a8",
  medium: "#fbbf24",
  high: "#fb923c",
  critical: "#ef4444",
};

const PRIORITY_HUE: Record<string, string> = {
  critical: "#ef4444",
  high: "#fb923c",
  medium: "#fbbf24",
  low: "#94a3b8",
};

function fmtDayLabel(iso: string) {
  try {
    const d = new Date(iso);
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
  } catch {
    return iso;
  }
}

function fmtPctDelta(d: number | null | undefined) {
  if (d === null || d === undefined || Math.abs(d) < 0.05) return "→ ±0";
  const arrow = d > 0 ? "▲" : "▼";
  return `${arrow} ${d > 0 ? "+" : "−"}${Math.abs(d).toFixed(0)}`;
}

function escapeHtml(s: string) {
  return s.replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c] || c));
}

function renderInlineMarkdown(text: string): string {
  return escapeHtml(text).replace(
    /\*\*(.+?)\*\*/g,
    '<strong class="text-white">$1</strong>',
  );
}

export default function PulsePage() {
  const [report, setReport] = useState<PulseReport | null>(null);
  const [rules, setRules] = useState<PulseRules | null>(null);
  const [windowDays, setWindowDays] = useState<WindowChoice>(1);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async (wd: WindowChoice) => {
    setErr(null);
    setRefreshing(true);
    try {
      const r = await getPulse(wd).catch(() => null);
      if (r && r.portfolio_size > 0) {
        setReport(r);
      } else {
        // Fallback to the rich sample if /aml/pulse returns 0 customers.
        const s = await getPulseSample(wd);
        setReport({ ...s, source: "sample" } as PulseReport);
      }
    } catch (e: any) {
      setErr(e.message || "failed to load pulse");
    } finally {
      setRefreshing(false);
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    (async () => {
      try {
        const r = await getPulseRules();
        setRules(r);
      } catch {}
      load(windowDays);
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    load(windowDays);
  }, [windowDays, load]);

  if (loading && !report) {
    return (
      <div className="glass p-10 text-center text-white/60">
        Loading Pulse — composing morning brief…
      </div>
    );
  }

  if (!report) {
    return (
      <div className="glass border border-rose-400/30 bg-rose-500/10 px-4 py-3 text-[13px] text-rose-200">
        {err || "Could not load Pulse."}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <Hero report={report} />

      <WindowBar
        windowDays={windowDays}
        setWindowDays={setWindowDays}
        refreshing={refreshing}
        source={report.source}
        onExport={() => {
          window.open(
            pulseExportUrl({ window_days: windowDays, source: report.source || "auto" }),
            "_blank",
          );
        }}
      />

      {err && (
        <div className="glass border border-rose-400/30 bg-rose-500/10 px-4 py-2.5 text-[13px] text-rose-200">
          {err}
        </div>
      )}

      <StatStrip report={report} />

      <div className="grid gap-6 lg:grid-cols-[1fr_360px]">
        <SparklineCard report={report} />
        <BucketDriftCard report={report} />
      </div>

      <BiggestMoversCard movers={report.biggest_movers} />

      <div className="grid gap-6 lg:grid-cols-[1fr_1fr]">
        <ChangeLogCard lines={report.change_log} />
        <PlanOfDayCard actions={report.plan_of_day} />
      </div>

      <CustomerGridCard customers={report.customers} />

      <HistogramCard report={report} />

      <ExplainerFooter rules={rules} />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Hero — mood ring + headline + advisory
// ---------------------------------------------------------------------------

function Hero({ report }: { report: PulseReport }) {
  const ringPct = Math.max(8, Math.min(100, report.movers_count * 18 + (report.open_breaches ? 25 : 0)));
  const mood = report.mood;
  const accent = report.mood_accent;
  const dial = `conic-gradient(${accent} ${ringPct * 3.6}deg, rgba(255,255,255,0.06) 0)`;

  return (
    <section
      className="glass-strong relative overflow-hidden p-6 md:p-8"
      style={{ background: MOOD_BG[mood] }}
    >
      <div className="grid items-center gap-6 md:grid-cols-[180px_1fr]">
        <div className="relative grid place-items-center" style={{ width: 168, height: 168 }}>
          {/* Outer breathing ring */}
          <div
            className="absolute inset-0 rounded-full"
            style={{ background: dial, animation: "pulse-breathe 4.5s ease-in-out infinite" }}
          />
          <div
            className="absolute inset-[7px] rounded-full"
            style={{ background: "rgba(7,11,20,0.92)" }}
          />
          {/* ECG heartbeat polyline */}
          <svg
            viewBox="0 0 64 24"
            className="relative z-10"
            style={{ width: 112, height: 38 }}
            aria-hidden
          >
            <path
              d="M2,12 L14,12 L18,4 L24,20 L30,8 L36,16 L42,12 L62,12"
              fill="none"
              stroke={accent}
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
            <circle cx="62" cy="12" r="1.5" fill={accent} />
          </svg>
          <div className="absolute bottom-3 left-0 right-0 text-center text-[10px] uppercase tracking-[0.22em]"
               style={{ color: accent }}>
            pulse
          </div>
        </div>

        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <span
              className="rounded-full border px-3 py-1 text-[11px] font-semibold uppercase tracking-wider"
              style={{
                color: accent,
                borderColor: `${accent}66`,
                background: `${accent}1a`,
              }}
            >
              {report.mood_label}
            </span>
            {report.source === "sample" && (
              <span className="pill pill-warn !text-[10px]">sample mode</span>
            )}
            <span className="text-[11px] text-white/40">
              window {report.window_days}d · {report.portfolio_size} customer(s) ·
              composed {new Date(report.computed_at).toLocaleString()}
            </span>
          </div>
          <h1 className="text-[26px] font-semibold leading-tight tracking-tight text-white md:text-[30px]">
            {report.headline}
          </h1>
          <p className="text-[14px] text-white/65">{report.advisory}</p>
          <p className="text-[12px] text-white/40">{report.mood_blurb}</p>
        </div>
      </div>

    </section>
  );
}

// ---------------------------------------------------------------------------
// Window picker bar
// ---------------------------------------------------------------------------

function WindowBar({
  windowDays,
  setWindowDays,
  refreshing,
  source,
  onExport,
}: {
  windowDays: WindowChoice;
  setWindowDays: (w: WindowChoice) => void;
  refreshing: boolean;
  source?: "live" | "sample";
  onExport: () => void;
}) {
  return (
    <div className="glass flex flex-wrap items-center justify-between gap-3 px-4 py-2.5">
      <div className="flex items-center gap-2">
        <span className="text-[11px] uppercase tracking-wider text-white/45">lookback</span>
        <div className="flex items-center gap-1 rounded-xl border border-white/10 bg-black/30 p-0.5">
          {WINDOW_CHOICES.map((w) => (
            <button
              key={w}
              onClick={() => setWindowDays(w)}
              className={[
                "rounded-lg px-3 py-1 text-[12px] font-medium transition",
                w === windowDays
                  ? "bg-white/10 text-white"
                  : "text-white/55 hover:bg-white/[0.05] hover:text-white/85",
              ].join(" ")}
            >
              {w}d
            </button>
          ))}
        </div>
        {refreshing && (
          <span className="text-[11px] text-white/40">recomputing…</span>
        )}
        {source && (
          <span className="text-[10px] uppercase tracking-[0.18em] text-white/35">
            · source: {source}
          </span>
        )}
      </div>
      <div className="flex items-center gap-2">
        <button onClick={onExport} className="btn !py-1.5 !text-[12px]">
          ⤓ Markdown brief
        </button>
        <Link href="/profile" className="btn-ghost !py-1.5 !text-[12px]">
          → Profile tab
        </Link>
        <Link href="/cases" className="btn-ghost !py-1.5 !text-[12px]">
          → Cases tab
        </Link>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Stat strip — vital signs
// ---------------------------------------------------------------------------

function StatStrip({ report }: { report: PulseReport }) {
  const tiles: { label: string; value: string; sub?: string; hue: string }[] = [
    {
      label: "New cases",
      value: String(report.new_cases_total),
      sub: `${report.new_cases_critical} critical`,
      hue: report.new_cases_critical ? "#ef4444" : report.new_cases_total ? "#fb923c" : "#94a3b8",
    },
    {
      label: "Open cases",
      value: String(report.open_cases_total),
      hue: "#a78bfa",
    },
    {
      label: "SLA breaches",
      value: String(report.open_breaches),
      sub: report.open_breaches ? "triage first" : "all clear",
      hue: report.open_breaches ? "#ef4444" : "#22d3a8",
    },
    {
      label: "Movers",
      value: String(report.movers_count),
      sub: `from ${report.portfolio_size}`,
      hue: report.movers_count ? "#fb923c" : "#94a3b8",
    },
    {
      label: "KYC overdue",
      value: String(report.refresh_overdue),
      sub: `${report.refresh_due_soon} due ≤30d`,
      hue: report.refresh_overdue ? "#fb923c" : "#22d3a8",
    },
    {
      label: "Portfolio",
      value: String(report.portfolio_size),
      sub: "customers tracked",
      hue: "#2DE1C2",
    },
  ];
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
      {tiles.map((t) => (
        <div
          key={t.label}
          className="glass relative overflow-hidden p-3"
          style={{
            boxShadow: `inset 0 1px 0 0 rgba(255,255,255,0.04), inset 4px 0 0 0 ${t.hue}`,
          }}
        >
          <div className="text-[10px] uppercase tracking-[0.18em] text-white/50">{t.label}</div>
          <div className="mt-1 text-[24px] font-semibold tracking-tight text-white">{t.value}</div>
          {t.sub && (
            <div className="text-[11px] text-white/50">{t.sub}</div>
          )}
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sparkline — per-day case opens
// ---------------------------------------------------------------------------

function SparklineCard({ report }: { report: PulseReport }) {
  const data = report.activity_sparkline;
  const maxVal = Math.max(1, ...data.map((d) => Math.max(d.new_cases, d.sla_breaches)));
  const W = 640;
  const H = 140;
  const PAD = { l: 28, r: 12, t: 14, b: 22 };
  const innerW = W - PAD.l - PAD.r;
  const innerH = H - PAD.t - PAD.b;
  const stepX = data.length > 1 ? innerW / (data.length - 1) : innerW;
  const pts = data.map((d, i) => {
    const x = PAD.l + (data.length === 1 ? innerW / 2 : i * stepX);
    const y = PAD.t + innerH - (d.new_cases / maxVal) * innerH;
    return { x, y, ...d };
  });
  const breachPts = data.map((d, i) => {
    const x = PAD.l + (data.length === 1 ? innerW / 2 : i * stepX);
    const y = PAD.t + innerH - (d.sla_breaches / maxVal) * innerH;
    return { x, y, ...d };
  });
  const linePath = pts.map((p, i) => `${i === 0 ? "M" : "L"} ${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(" ");
  const fillPath = pts.length
    ? `M ${pts[0].x.toFixed(1)} ${(PAD.t + innerH).toFixed(1)} ` +
      pts.map((p) => `L ${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(" ") +
      ` L ${pts[pts.length - 1].x.toFixed(1)} ${(PAD.t + innerH).toFixed(1)} Z`
    : "";

  return (
    <div className="glass p-5">
      <div className="mb-3 flex items-baseline justify-between">
        <div>
          <h3 className="text-[13px] font-semibold uppercase tracking-wider text-white/70">
            Daily activity
          </h3>
          <p className="text-[11px] text-white/45">
            Cases opened per day across the window · breach overlay in rose
          </p>
        </div>
        <div className="flex items-center gap-3 text-[10px] uppercase tracking-wider text-white/40">
          <span className="flex items-center gap-1.5">
            <span className="inline-block h-2 w-3 rounded-sm" style={{ background: "#2DE1C2" }} />
            new cases
          </span>
          <span className="flex items-center gap-1.5">
            <span className="inline-block h-2 w-3 rounded-sm" style={{ background: "#ef4444" }} />
            breaches
          </span>
        </div>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" preserveAspectRatio="none">
        <defs>
          <linearGradient id="pulse-line-fill" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor="#2DE1C2" stopOpacity="0.32" />
            <stop offset="100%" stopColor="#2DE1C2" stopOpacity="0" />
          </linearGradient>
        </defs>
        {/* Y axis grid */}
        {[0, 0.5, 1].map((t) => (
          <line
            key={t}
            x1={PAD.l}
            x2={W - PAD.r}
            y1={PAD.t + innerH * (1 - t)}
            y2={PAD.t + innerH * (1 - t)}
            stroke="rgba(255,255,255,0.05)"
            strokeDasharray="2 3"
          />
        ))}
        <text x={PAD.l - 4} y={PAD.t + 6} className="text-[8px]" textAnchor="end" fill="rgba(255,255,255,0.4)">
          {maxVal}
        </text>
        <text x={PAD.l - 4} y={PAD.t + innerH} className="text-[8px]" textAnchor="end" fill="rgba(255,255,255,0.35)">
          0
        </text>

        {/* Area + line for cases */}
        {fillPath && <path d={fillPath} fill="url(#pulse-line-fill)" />}
        {linePath && (
          <path d={linePath} fill="none" stroke="#2DE1C2" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        )}
        {pts.map((p, i) => (
          <g key={`p-${i}`}>
            <circle cx={p.x} cy={p.y} r={3} fill="#2DE1C2" />
            {p.new_cases > 0 && (
              <text
                x={p.x}
                y={p.y - 6}
                textAnchor="middle"
                fill="#2DE1C2"
                className="text-[9px]"
                style={{ filter: "drop-shadow(0 0 4px rgba(45,225,194,0.4))" }}
              >
                {p.new_cases}
              </text>
            )}
          </g>
        ))}
        {/* Breach overlay */}
        {breachPts.map((p, i) =>
          p.sla_breaches > 0 ? (
            <g key={`b-${i}`}>
              <line
                x1={p.x}
                x2={p.x}
                y1={p.y}
                y2={PAD.t + innerH}
                stroke="#ef4444"
                strokeWidth="2"
                strokeOpacity="0.55"
              />
              <circle cx={p.x} cy={p.y} r={3.2} fill="#ef4444" />
            </g>
          ) : null,
        )}

        {/* X axis labels */}
        {pts.map((p, i) => {
          const isEdge = i === 0 || i === pts.length - 1;
          const isMid = Math.abs(i - Math.floor(pts.length / 2)) < 0.5;
          if (!isEdge && !isMid && pts.length > 4) return null;
          return (
            <text
              key={`x-${i}`}
              x={p.x}
              y={H - 6}
              textAnchor="middle"
              fill="rgba(255,255,255,0.45)"
              className="text-[9px]"
            >
              {fmtDayLabel(p.date)}
            </text>
          );
        })}
      </svg>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Bucket drift — before/after horizontal bars
// ---------------------------------------------------------------------------

function BucketDriftCard({ report }: { report: PulseReport }) {
  const buckets: ProfileBucket[] = ["critical", "high", "medium", "low"];
  const total = Math.max(1, report.portfolio_size);
  return (
    <div className="glass p-5">
      <h3 className="mb-1 text-[13px] font-semibold uppercase tracking-wider text-white/70">
        Bucket drift
      </h3>
      <p className="mb-4 text-[11px] text-white/45">
        Where the book sat at window-start vs now · Δ shows net moves
      </p>
      <div className="space-y-3">
        {buckets.map((b) => {
          const now = report.by_bucket[b] || 0;
          const prior = report.by_bucket_prior[b] || 0;
          const delta = report.bucket_drift[b] || 0;
          const widthNow = (now / total) * 100;
          const widthPrior = (prior / total) * 100;
          const hue = BUCKET_HUE[b];
          const sign = delta > 0 ? "+" : "";
          return (
            <div key={b}>
              <div className="mb-1 flex items-center justify-between text-[11px]">
                <span className="capitalize" style={{ color: hue }}>{b}</span>
                <span className="text-white/60">
                  {prior} → <span className="text-white">{now}</span>
                  {delta !== 0 && (
                    <span className="ml-2 font-mono" style={{ color: delta > 0 ? hue : "rgba(255,255,255,0.5)" }}>
                      ({sign}{delta})
                    </span>
                  )}
                </span>
              </div>
              <div className="relative h-3 overflow-hidden rounded-full bg-black/40">
                {/* Prior — dotted thin bar */}
                <div
                  className="absolute left-0 top-0 h-full"
                  style={{
                    width: `${widthPrior}%`,
                    background: `repeating-linear-gradient(90deg, ${hue}55 0 4px, transparent 4px 8px)`,
                    opacity: 0.6,
                  }}
                />
                {/* Now — solid bar overlay */}
                <div
                  className="absolute left-0 top-0 h-full rounded-r-full"
                  style={{
                    width: `${widthNow}%`,
                    background: `linear-gradient(90deg, ${hue} 0%, ${hue}aa 100%)`,
                    boxShadow: `inset 0 1px 0 rgba(255,255,255,0.18)`,
                  }}
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Biggest movers — horizontally scrolling row of cards
// ---------------------------------------------------------------------------

function BiggestMoversCard({ movers }: { movers: PulseCustomer[] }) {
  if (!movers.length) {
    return (
      <div className="glass p-5">
        <h3 className="text-[13px] font-semibold uppercase tracking-wider text-white/70">
          Biggest movers
        </h3>
        <p className="mt-1 text-[12px] text-white/45">
          Nobody moved enough to surface — a quiet morning.
        </p>
      </div>
    );
  }
  return (
    <div className="glass p-5">
      <div className="mb-3 flex items-baseline justify-between">
        <div>
          <h3 className="text-[13px] font-semibold uppercase tracking-wider text-white/70">
            Biggest movers
          </h3>
          <p className="text-[11px] text-white/45">
            Ranked by deterministic signal: delta · bucket shift · fresh cases · breaches · KYC overdue
          </p>
        </div>
        <span className="text-[10px] uppercase tracking-wider text-white/35">
          {movers.length} surfaced
        </span>
      </div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {movers.map((m) => (
          <MoverCard key={m.customer_id} mover={m} />
        ))}
      </div>
    </div>
  );
}

function MoverCard({ mover }: { mover: PulseCustomer }) {
  const hue = mover.bucket_accent || BUCKET_HUE[mover.bucket] || "#94a3b8";
  const compositePct = Math.max(2, Math.min(100, mover.composite));
  const ring = `conic-gradient(${hue} ${compositePct * 3.6}deg, rgba(255,255,255,0.06) 0)`;
  const delta = mover.composite_delta;
  const deltaColor = delta == null ? "rgba(255,255,255,0.6)" : delta > 0 ? hue : "#22d3a8";
  return (
    <Link
      href={`/profile?customer_id=${encodeURIComponent(mover.customer_id)}`}
      className="glass group block cursor-pointer p-4 transition hover:border-white/20 hover:bg-white/[0.05]"
      style={{ boxShadow: `inset 4px 0 0 0 ${hue}` }}
    >
      <div className="flex items-start gap-4">
        <div
          className="relative grid place-items-center rounded-full"
          style={{ width: 76, height: 76, background: ring }}
        >
          <div
            className="absolute inset-[5px] rounded-full"
            style={{ background: "rgba(7,11,20,0.9)" }}
          />
          <div className="relative text-center leading-none">
            <div className="text-[16px] font-semibold" style={{ color: hue }}>
              {mover.composite.toFixed(0)}
            </div>
            <div className="mt-0.5 text-[8px] uppercase tracking-[0.18em] text-white/55">
              {mover.bucket}
            </div>
          </div>
        </div>
        <div className="min-w-0 flex-1 space-y-1">
          <div className="truncate text-[14px] font-medium text-white" title={mover.display_name}>
            {mover.display_name}
          </div>
          <div className="flex flex-wrap items-center gap-1.5 text-[10px] text-white/55">
            {mover.domicile && (
              <span className="rounded border border-white/10 bg-white/[0.04] px-1.5 py-0.5 uppercase tracking-wider">
                {mover.domicile}
              </span>
            )}
            {mover.pep && (
              <span className="rounded border border-rose-300/30 bg-rose-500/10 px-1.5 py-0.5 uppercase tracking-wider text-rose-200">
                PEP
              </span>
            )}
            {mover.refresh_label === "overdue" && (
              <span className="rounded border border-rose-300/30 bg-rose-500/10 px-1.5 py-0.5 uppercase tracking-wider text-rose-200">
                KYC overdue
              </span>
            )}
            {mover.refresh_label === "due_soon" && (
              <span className="rounded border border-amber-300/30 bg-amber-500/10 px-1.5 py-0.5 uppercase tracking-wider text-amber-200">
                KYC due
              </span>
            )}
          </div>
          <div className="text-[12px] text-white/70" style={{ minHeight: 18 }}>
            {mover.headline}
          </div>
          <div className="flex items-center gap-2 text-[11px] font-mono text-white/55">
            {mover.composite_prior !== null && (
              <span>{mover.composite_prior.toFixed(0)}→{mover.composite.toFixed(0)}</span>
            )}
            <span style={{ color: deltaColor }}>{fmtPctDelta(delta)}</span>
            {mover.band_shift_direction === "up" && mover.bucket_prior && (
              <span className="rounded bg-white/[0.05] px-1.5 py-0.5 text-white/60">
                {mover.bucket_prior} →{" "}
                <span style={{ color: hue }}>{mover.bucket}</span>
              </span>
            )}
          </div>
          {mover.change_lines.length > 0 && (
            <ul className="mt-1 space-y-0.5 text-[11px] text-white/55">
              {mover.change_lines.slice(0, 2).map((line, i) => (
                <li
                  key={i}
                  dangerouslySetInnerHTML={{ __html: renderInlineMarkdown(line) }}
                />
              ))}
            </ul>
          )}
        </div>
      </div>
    </Link>
  );
}

// ---------------------------------------------------------------------------
// Change log
// ---------------------------------------------------------------------------

function ChangeLogCard({ lines }: { lines: string[] }) {
  return (
    <div className="glass p-5">
      <h3 className="mb-1 text-[13px] font-semibold uppercase tracking-wider text-white/70">
        What changed
      </h3>
      <p className="mb-3 text-[11px] text-white/45">
        Composed from per-customer deltas, ranked by signal · capped at 10 bullets
      </p>
      {lines.length === 0 ? (
        <div className="text-[12px] text-white/45">
          No material changes in this window — quiet morning.
        </div>
      ) : (
        <ol className="space-y-2">
          {lines.map((line, i) => (
            <li key={i} className="flex gap-3 text-[12px] text-white/75">
              <span className="grid h-5 w-5 shrink-0 place-items-center rounded-full bg-white/[0.06] text-[10px] text-white/55">
                {i + 1}
              </span>
              <span
                className="flex-1"
                dangerouslySetInnerHTML={{ __html: renderInlineMarkdown(line) }}
              />
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Plan of day
// ---------------------------------------------------------------------------

function PlanOfDayCard({ actions }: { actions: PulseAction[] }) {
  return (
    <div className="glass p-5">
      <h3 className="mb-1 text-[13px] font-semibold uppercase tracking-wider text-white/70">
        Plan of day
      </h3>
      <p className="mb-3 text-[11px] text-white/45">
        Prioritised checklist · names the TITAN tab each action lives in
      </p>
      <ol className="space-y-2.5">
        {actions.map((a, i) => {
          const hue = PRIORITY_HUE[a.priority] || "#94a3b8";
          const body = (
            <span
              className="flex-1 text-[12px] text-white/80"
              dangerouslySetInnerHTML={{ __html: renderInlineMarkdown(a.body) }}
            />
          );
          const row = (
            <div
              className="flex items-start gap-3 rounded-xl border border-white/5 bg-white/[0.02] p-3 transition hover:border-white/15 hover:bg-white/[0.05]"
              style={{ boxShadow: `inset 3px 0 0 0 ${hue}` }}
            >
              <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full font-mono text-[11px]"
                    style={{ color: hue, background: `${hue}1f` }}>
                {i + 1}
              </span>
              <div className="min-w-0 flex-1">
                {body}
                <div className="mt-1 flex items-center gap-2 text-[10px] uppercase tracking-wider text-white/40">
                  <span style={{ color: hue }}>{a.priority}</span>
                  <span>· {a.kind}</span>
                </div>
              </div>
            </div>
          );
          return a.href ? (
            <li key={i}>
              <Link href={a.href}>{row}</Link>
            </li>
          ) : (
            <li key={i}>{row}</li>
          );
        })}
      </ol>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Customer grid — every customer, sortable by signal
// ---------------------------------------------------------------------------

function CustomerGridCard({ customers }: { customers: PulseCustomer[] }) {
  const [sort, setSort] = useState<"signal" | "composite" | "delta">("signal");
  const sorted = useMemo(() => {
    const arr = [...customers];
    arr.sort((a, b) => {
      if (sort === "composite") return b.composite - a.composite;
      if (sort === "delta") {
        const da = a.composite_delta ?? 0;
        const db = b.composite_delta ?? 0;
        return db - da;
      }
      return b.signal - a.signal;
    });
    return arr;
  }, [customers, sort]);

  return (
    <div className="glass p-5">
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <h3 className="text-[13px] font-semibold uppercase tracking-wider text-white/70">
            Customer roster
          </h3>
          <p className="text-[11px] text-white/45">
            Every customer in the brief · click to open their full profile
          </p>
        </div>
        <div className="flex items-center gap-1 rounded-xl border border-white/10 bg-black/30 p-0.5 text-[11px]">
          {(["signal", "composite", "delta"] as const).map((s) => (
            <button
              key={s}
              onClick={() => setSort(s)}
              className={[
                "rounded-lg px-2.5 py-1 transition",
                s === sort
                  ? "bg-white/10 text-white"
                  : "text-white/55 hover:bg-white/[0.05] hover:text-white/85",
              ].join(" ")}
            >
              {s}
            </button>
          ))}
        </div>
      </div>
      <div className="overflow-hidden rounded-xl border border-white/5">
        <table className="w-full table-fixed text-[12px]">
          <thead className="bg-white/[0.03] text-[10px] uppercase tracking-wider text-white/45">
            <tr>
              <th className="w-[26%] px-3 py-2 text-left">Customer</th>
              <th className="w-[10%] px-3 py-2 text-right">Composite</th>
              <th className="w-[10%] px-3 py-2 text-right">Δ</th>
              <th className="w-[12%] px-3 py-2 text-left">Bucket</th>
              <th className="w-[12%] px-3 py-2 text-left">KYC</th>
              <th className="w-[14%] px-3 py-2 text-left">Cases</th>
              <th className="w-[16%] px-3 py-2 text-right">Signal</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((c, i) => {
              const hue = c.bucket_accent || BUCKET_HUE[c.bucket];
              return (
                <tr
                  key={c.customer_id}
                  className={[
                    "border-t border-white/5 transition hover:bg-white/[0.03]",
                    c.is_biggest_mover ? "bg-white/[0.02]" : "",
                  ].join(" ")}
                >
                  <td className="px-3 py-2">
                    <Link
                      href={`/profile?customer_id=${encodeURIComponent(c.customer_id)}`}
                      className="block"
                    >
                      <div className="truncate font-medium text-white">{c.display_name}</div>
                      <div className="truncate text-[10px] text-white/40">
                        {c.customer_id}
                        {c.domicile ? ` · ${c.domicile}` : ""}
                        {c.pep ? " · PEP" : ""}
                      </div>
                    </Link>
                  </td>
                  <td className="px-3 py-2 text-right font-mono text-white/85">
                    {c.composite.toFixed(0)}
                  </td>
                  <td className="px-3 py-2 text-right font-mono"
                      style={{ color: c.composite_delta != null && c.composite_delta > 0 ? hue : (c.composite_delta != null && c.composite_delta < 0 ? "#22d3a8" : "rgba(255,255,255,0.4)") }}>
                    {c.composite_delta == null ? "—" : fmtPctDelta(c.composite_delta)}
                  </td>
                  <td className="px-3 py-2">
                    <span
                      className="rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-wider"
                      style={{
                        color: hue,
                        borderColor: `${hue}55`,
                        background: `${hue}14`,
                      }}
                    >
                      {c.bucket}
                    </span>
                    {c.band_shift_direction === "up" && c.bucket_prior && (
                      <span className="ml-1 text-[10px] text-white/45">
                        ↑ from {c.bucket_prior}
                      </span>
                    )}
                  </td>
                  <td className="px-3 py-2">
                    <span
                      className={[
                        "text-[11px]",
                        c.refresh_label === "overdue"
                          ? "text-rose-300"
                          : c.refresh_label === "due_soon"
                          ? "text-amber-300"
                          : "text-teal-300/80",
                      ].join(" ")}
                    >
                      {c.refresh_label}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-[11px] text-white/70">
                    {c.open_case_count} open
                    {c.open_breach_count > 0 && (
                      <span className="ml-1.5 rounded bg-rose-500/15 px-1 text-[10px] text-rose-300">
                        {c.open_breach_count} breach
                      </span>
                    )}
                    {c.new_case_count > 0 && (
                      <span className="ml-1.5 text-[10px] text-amber-300">+{c.new_case_count} new</span>
                    )}
                  </td>
                  <td className="px-3 py-2 text-right font-mono text-white/65">
                    {c.signal.toFixed(1)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Histogram — composite distribution
// ---------------------------------------------------------------------------

function HistogramCard({ report }: { report: PulseReport }) {
  const max = Math.max(1, ...report.score_histogram.map((b) => b.count));
  return (
    <div className="glass p-5">
      <h3 className="mb-1 text-[13px] font-semibold uppercase tracking-wider text-white/70">
        Composite distribution
      </h3>
      <p className="mb-3 text-[11px] text-white/45">
        Where the {report.portfolio_size}-customer book sits across the FATF-RBA composite scale
      </p>
      <div className="flex h-32 items-end gap-1">
        {report.score_histogram.map((b) => {
          const h = (b.count / max) * 100;
          const bucket: ProfileBucket =
            b.min >= 80 ? "critical" : b.min >= 60 ? "high" : b.min >= 30 ? "medium" : "low";
          const hue = BUCKET_HUE[bucket];
          return (
            <div key={b.label} className="flex flex-1 flex-col items-center justify-end">
              <div className="text-[10px] font-mono text-white/50" style={{ minHeight: 12 }}>
                {b.count > 0 ? b.count : ""}
              </div>
              <div
                className="w-full rounded-t-md"
                style={{
                  height: `${Math.max(4, h)}%`,
                  background: `linear-gradient(180deg, ${hue} 0%, ${hue}33 100%)`,
                  opacity: b.count === 0 ? 0.18 : 1,
                  boxShadow: b.count > 0 ? `inset 0 1px 0 rgba(255,255,255,0.18)` : "none",
                }}
              />
              <div className="mt-1 text-[9px] text-white/35">{b.label}</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Explainer footer
// ---------------------------------------------------------------------------

function ExplainerFooter({ rules }: { rules: PulseRules | null }) {
  return (
    <div className="glass p-5 text-[11px] text-white/55">
      <h3 className="mb-2 text-[12px] font-semibold uppercase tracking-wider text-white/70">
        How Pulse reasons
      </h3>
      <p className="mb-2">
        Pulse is a deterministic <em>composer</em> — no engine of its own, no ML weights to retrain.
        It reads every customer's persisted Customer Risk Profile, the case-store's open cases &
        SLA breaches, and computes a signed delta against the last history row from before the
        window. Every customer is then ranked by a weighted "signal" formula.
      </p>
      {rules && (
        <p className="font-mono text-[10px] text-white/40">
          mood: {rules.mood_order.join(" → ")} · window {rules.min_window_days}…
          {rules.max_window_days}d · composite-floor {rules.composite_delta_floor} pts ·
          critical-floor {rules.critical_composite_floor} pts ·
          signal: {Object.entries(rules.signal_weights).map(([k, v]) => `${k} ${v}`).join(" · ")} ·
          engine {rules.engine}
        </p>
      )}
    </div>
  );
}
