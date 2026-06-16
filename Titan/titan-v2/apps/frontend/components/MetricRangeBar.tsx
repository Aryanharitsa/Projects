"use client";

import type { PeerMetricEval } from "../lib/api";

function fmtValue(unit: PeerMetricEval["unit"], value: number): string {
  if (unit === "USD") {
    if (value >= 1_000_000) return `$${(value / 1_000_000).toFixed(2)}M`;
    if (value >= 1_000) return `$${(value / 1_000).toFixed(1)}K`;
    return `$${value.toFixed(0)}`;
  }
  if (unit === "%") return `${(value * 100).toFixed(0)}%`;
  if (value >= 1000) return value.toLocaleString();
  if (Number.isInteger(value)) return `${value}`;
  return value.toFixed(2);
}

// Renders a horizontal range bar:
//   min ────[ p25 ▓▓▓▓ median ▓▓▓▓ p75 ]──── max          ← cohort band
//                                       ▲ customer marker
export default function MetricRangeBar({ metric }: { metric: PeerMetricEval }) {
  const {
    value,
    cohort_min,
    cohort_max,
    cohort_p25,
    cohort_p75,
    cohort_median,
    z,
    gated_z,
    direction,
    extreme,
    accent,
    unit,
    label,
  } = metric;

  // Expand the range so the customer marker is always visible even when it
  // sits outside the cohort min/max envelope (which is the whole point of
  // an outlier).
  const valuesForRange = [cohort_min, cohort_max, value];
  const lo = Math.min(...valuesForRange);
  const hi = Math.max(...valuesForRange);
  const padding = (hi - lo) * 0.08 || 1;
  const rangeMin = lo - padding;
  const rangeMax = hi + padding;
  const span = rangeMax - rangeMin || 1;

  const pct = (v: number) => Math.max(0, Math.min(100, ((v - rangeMin) / span) * 100));

  const markerPct = pct(value);
  const medianPct = pct(cohort_median);
  const p25Pct = pct(cohort_p25);
  const p75Pct = pct(cohort_p75);
  const minPct = pct(cohort_min);
  const maxPct = pct(cohort_max);

  const zSign = z > 0 ? "+" : z < 0 ? "−" : "";
  const zColor = extreme ? "#ef4444" : gated_z > 1.5 ? "#fb923c" : "#94a3b8";

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between text-[11px]">
        <span className="text-white/65">
          <span
            className="mr-2 inline-block h-1.5 w-1.5 rounded-full align-middle"
            style={{ background: accent }}
          />
          {label}
          {direction === "high" && (
            <span className="ml-1.5 text-[9px] uppercase tracking-wider text-white/30">
              high-only
            </span>
          )}
        </span>
        <span className="font-mono text-white/90">
          {fmtValue(unit, value)}
          <span className="ml-2 text-[10px]" style={{ color: zColor }}>
            z={zSign}
            {Math.abs(z).toFixed(2)}
          </span>
        </span>
      </div>

      <div className="relative h-4 w-full rounded-md bg-white/[0.04]">
        {/* cohort full extent: min..max */}
        <div
          className="absolute top-1/2 h-0.5 -translate-y-1/2 rounded-full bg-white/15"
          style={{ left: `${minPct}%`, width: `${Math.max(0.5, maxPct - minPct)}%` }}
        />
        {/* IQR */}
        <div
          className="absolute top-1/2 h-2 -translate-y-1/2 rounded-md"
          style={{
            left: `${p25Pct}%`,
            width: `${Math.max(1.5, p75Pct - p25Pct)}%`,
            background: `${accent}33`,
            border: `1px solid ${accent}55`,
          }}
        />
        {/* median tick */}
        <div
          className="absolute top-1/2 h-3 w-0.5 -translate-y-1/2 rounded-full"
          style={{ left: `${medianPct}%`, background: "#e6edf6" }}
        />
        {/* customer marker */}
        <div
          className="absolute top-1/2 -translate-y-1/2"
          style={{
            left: `calc(${markerPct}% - 7px)`,
            width: 14,
            height: 14,
          }}
        >
          <div
            className="h-full w-full rounded-full"
            style={{
              background: zColor,
              boxShadow: `0 0 12px ${zColor}66, inset 0 0 0 2px rgba(7,11,20,0.85)`,
            }}
          />
        </div>
      </div>

      <div className="flex items-center justify-between text-[9.5px] text-white/35">
        <span>{fmtValue(unit, rangeMin)}</span>
        <span>cohort med {fmtValue(unit, cohort_median)}</span>
        <span>{fmtValue(unit, rangeMax)}</span>
      </div>
    </div>
  );
}
