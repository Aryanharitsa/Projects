"use client";

import { useMemo, useRef } from "react";
import { ConfusionPoint } from "../lib/api";

/** Precision / recall / Fβ / alert-rate plotted against the alert
 * threshold (0..100). Vertical guides mark the current operating point
 * and the Fβ-recommended cut; an interactive cursor lets the analyst
 * scrub the threshold and read every metric live. Pure inline SVG. */

const W = 720;
const H = 240;
const PAD = { l: 38, r: 14, t: 14, b: 30 };
const PLOT_W = W - PAD.l - PAD.r;
const PLOT_H = H - PAD.t - PAD.b;

type SeriesKey = "precision" | "recall" | "fbeta" | "alert_rate";

const SERIES: { key: SeriesKey; label: string; color: string; dash?: string }[] = [
  { key: "recall", label: "Recall", color: "#6E5BFF" },
  { key: "precision", label: "Precision", color: "#2DE1C2" },
  { key: "fbeta", label: "Fβ", color: "#FBBF24" },
  { key: "alert_rate", label: "Alert rate", color: "#64748B", dash: "4 3" },
];

const x = (t: number) => PAD.l + (t / 100) * PLOT_W;
const y = (v: number) => PAD.t + (1 - Math.max(0, Math.min(1, v))) * PLOT_H;

export default function MetricSweep({
  sweep,
  active,
  current,
  recommended,
  onScrub,
}: {
  sweep: ConfusionPoint[];
  active: number;
  current: number;
  recommended: number;
  onScrub?: (threshold: number) => void;
}) {
  const ref = useRef<SVGSVGElement>(null);

  const paths = useMemo(() => {
    const byKey: Record<SeriesKey, string> = {
      precision: "",
      recall: "",
      fbeta: "",
      alert_rate: "",
    };
    for (const s of SERIES) {
      byKey[s.key] = sweep
        .map((p, i) => `${i === 0 ? "M" : "L"}${x(p.threshold).toFixed(1)},${y(p[s.key]).toFixed(1)}`)
        .join(" ");
    }
    return byKey;
  }, [sweep]);

  const at = sweep[Math.max(0, Math.min(100, Math.round(active)))] ?? sweep[0];

  const handle = (e: React.MouseEvent<SVGSVGElement>) => {
    if (!onScrub || !ref.current) return;
    const rect = ref.current.getBoundingClientRect();
    const px = ((e.clientX - rect.left) / rect.width) * W;
    const t = Math.round(((px - PAD.l) / PLOT_W) * 100);
    onScrub(Math.max(0, Math.min(100, t)));
  };

  return (
    <div>
      <svg
        ref={ref}
        viewBox={`0 0 ${W} ${H}`}
        className="w-full cursor-crosshair select-none"
        onClick={handle}
        onMouseMove={(e) => e.buttons === 1 && handle(e)}
      >
        {/* y gridlines at 0/.25/.5/.75/1 */}
        {[0, 0.25, 0.5, 0.75, 1].map((g) => (
          <g key={g}>
            <line
              x1={PAD.l}
              x2={W - PAD.r}
              y1={y(g)}
              y2={y(g)}
              stroke="rgba(255,255,255,0.07)"
              strokeWidth={1}
            />
            <text x={PAD.l - 6} y={y(g) + 3} textAnchor="end" className="fill-white/35 text-[9px]">
              {g.toFixed(2)}
            </text>
          </g>
        ))}
        {/* x ticks */}
        {[0, 20, 40, 60, 80, 100].map((t) => (
          <text key={t} x={x(t)} y={H - 10} textAnchor="middle" className="fill-white/35 text-[9px]">
            {t}
          </text>
        ))}

        {/* current + recommended guides */}
        <Guide t={current} label="now" color="rgba(148,163,184,0.7)" />
        <Guide t={recommended} label="rec" color="rgba(45,225,194,0.85)" />

        {/* series */}
        {SERIES.map((s) => (
          <path
            key={s.key}
            d={paths[s.key]}
            fill="none"
            stroke={s.color}
            strokeWidth={2}
            strokeDasharray={s.dash}
            strokeLinejoin="round"
          />
        ))}

        {/* active cursor */}
        <line
          x1={x(active)}
          x2={x(active)}
          y1={PAD.t}
          y2={PAD.t + PLOT_H}
          stroke="rgba(255,255,255,0.55)"
          strokeWidth={1.5}
        />
        {SERIES.map((s) => (
          <circle key={s.key} cx={x(active)} cy={y(at[s.key])} r={3} fill={s.color} stroke="#070b14" strokeWidth={1.5} />
        ))}
      </svg>

      <div className="mt-2 flex flex-wrap items-center justify-between gap-x-5 gap-y-2 text-[11px]">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
          {SERIES.map((s) => (
            <span key={s.key} className="inline-flex items-center gap-1.5 text-white/65">
              <span
                className="inline-block h-2 w-3 rounded-full"
                style={{ background: s.color }}
              />
              {s.label}
            </span>
          ))}
        </div>
        <div className="font-mono text-white/55">
          @ cut <span className="text-white/85">{Math.round(active)}</span> · P{" "}
          {at.precision.toFixed(2)} · R {at.recall.toFixed(2)} · Fβ {at.fbeta.toFixed(2)} · alerts{" "}
          {(at.alert_rate * 100).toFixed(0)}%
        </div>
      </div>
    </div>
  );
}

function Guide({ t, label, color }: { t: number; label: string; color: string }) {
  return (
    <g>
      <line
        x1={x(t)}
        x2={x(t)}
        y1={PAD.t}
        y2={PAD.t + PLOT_H}
        stroke={color}
        strokeWidth={1}
        strokeDasharray="2 3"
      />
      <text x={x(t)} y={PAD.t + 9} textAnchor="middle" className="text-[9px]" fill={color}>
        {label}
      </text>
    </g>
  );
}
