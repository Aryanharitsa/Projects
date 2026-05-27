"use client";

import { useMemo } from "react";
import { BacktestResult } from "../lib/api";

/** ROC curve (TPR vs FPR) with the area shaded, the chance diagonal as a
 * reference, and the operating points marked. AUC headline is the single
 * "how separable?" number model-risk reviewers anchor on. */

const S = 220;
const PAD = 26;
const PLOT = S - PAD - 8;

const px = (fpr: number) => PAD + fpr * PLOT;
const py = (tpr: number) => S - PAD - tpr * PLOT;

export default function RocCurve({
  roc,
  current,
  recommended,
}: {
  roc: BacktestResult["roc"];
  current: { fpr: number; tpr: number };
  recommended: { fpr: number; tpr: number };
}) {
  const { line, area } = useMemo(() => {
    // ROC points come ordered by threshold (descending FPR as threshold
    // rises); sort by fpr ascending for a clean monotone-ish curve.
    const pts = [...roc.points].sort((a, b) => a.fpr - b.fpr || a.tpr - b.tpr);
    const line = pts.map((p, i) => `${i === 0 ? "M" : "L"}${px(p.fpr).toFixed(1)},${py(p.tpr).toFixed(1)}`).join(" ");
    const area = `M${px(0).toFixed(1)},${py(0).toFixed(1)} ` + pts.map((p) => `L${px(p.fpr).toFixed(1)},${py(p.tpr).toFixed(1)}`).join(" ") + ` L${px(1).toFixed(1)},${py(0).toFixed(1)} Z`;
    return { line, area };
  }, [roc.points]);

  return (
    <div className="flex flex-col items-center">
      <svg viewBox={`0 0 ${S} ${S}`} className="w-full max-w-[240px]">
        <defs>
          <linearGradient id="rocFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="rgba(45,225,194,0.30)" />
            <stop offset="100%" stopColor="rgba(110,91,255,0.04)" />
          </linearGradient>
        </defs>
        {/* frame */}
        <rect x={PAD} y={S - PAD - PLOT} width={PLOT} height={PLOT} fill="none" stroke="rgba(255,255,255,0.10)" />
        {/* chance diagonal */}
        <line x1={px(0)} y1={py(0)} x2={px(1)} y2={py(1)} stroke="rgba(255,255,255,0.20)" strokeDasharray="3 3" />
        <path d={area} fill="url(#rocFill)" />
        <path d={line} fill="none" stroke="#2DE1C2" strokeWidth={2} strokeLinejoin="round" />
        {/* operating points */}
        <circle cx={px(current.fpr)} cy={py(current.tpr)} r={4} fill="#94A3B8" stroke="#070b14" strokeWidth={1.5} />
        <circle cx={px(recommended.fpr)} cy={py(recommended.tpr)} r={4} fill="#FBBF24" stroke="#070b14" strokeWidth={1.5} />
        {/* axis labels */}
        <text x={PAD + PLOT / 2} y={S - 6} textAnchor="middle" className="fill-white/40 text-[9px]">
          false positive rate
        </text>
        <text x={10} y={S - PAD - PLOT / 2} textAnchor="middle" transform={`rotate(-90 10 ${S - PAD - PLOT / 2})`} className="fill-white/40 text-[9px]">
          true positive rate
        </text>
      </svg>
      <div className="mt-1 flex items-center gap-4 text-[10.5px] text-white/55">
        <span className="inline-flex items-center gap-1.5">
          <span className="inline-block h-2 w-2 rounded-full bg-[#94A3B8]" /> now
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="inline-block h-2 w-2 rounded-full bg-[#FBBF24]" /> recommended
        </span>
      </div>
    </div>
  );
}
