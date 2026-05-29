"use client";

import { ConfusionPoint } from "../lib/api";

/** 2×2 confusion matrix at a given threshold. Diagonal (correct) cells
 * glow teal/slate; the off-diagonal error cells glow rose (missed bad =
 * costliest) and amber (false alarm = workload). Counts are tabular. */

type Cell = {
  key: keyof Pick<ConfusionPoint, "tp" | "fp" | "fn" | "tn">;
  label: string;
  sub: string;
  tone: "teal" | "rose" | "amber" | "slate";
};

const CELLS: Cell[] = [
  { key: "tp", label: "True positive", sub: "caught a confirmed bad", tone: "teal" },
  { key: "fn", label: "False negative", sub: "missed a confirmed bad", tone: "rose" },
  { key: "fp", label: "False positive", sub: "flagged a benign account", tone: "amber" },
  { key: "tn", label: "True negative", sub: "cleared a benign account", tone: "slate" },
];

const TONE: Record<Cell["tone"], { ring: string; glow: string; text: string }> = {
  teal: { ring: "border-teal-400/40", glow: "rgba(45,225,194,0.16)", text: "text-teal-300" },
  rose: { ring: "border-rose-400/45", glow: "rgba(244,63,94,0.18)", text: "text-rose-300" },
  amber: { ring: "border-amber-400/40", glow: "rgba(251,191,36,0.16)", text: "text-amber-300" },
  slate: { ring: "border-white/12", glow: "rgba(148,163,184,0.10)", text: "text-white/70" },
};

export default function ConfusionMatrix({ point }: { point: ConfusionPoint }) {
  const total = point.tp + point.fp + point.fn + point.tn || 1;
  return (
    <div>
      <div className="grid grid-cols-[auto_1fr_1fr] gap-2 text-[10px] uppercase tracking-wider text-white/40">
        <span />
        <span className="text-center">Pred. suspicious</span>
        <span className="text-center">Pred. benign</span>
      </div>
      <div className="mt-1 grid grid-cols-[auto_1fr_1fr] gap-2">
        <RowLabel label="Actually bad" />
        <Box cell={CELLS[0]} point={point} total={total} />
        <Box cell={CELLS[1]} point={point} total={total} />
        <RowLabel label="Actually good" />
        <Box cell={CELLS[2]} point={point} total={total} />
        <Box cell={CELLS[3]} point={point} total={total} />
      </div>
    </div>
  );
}

function RowLabel({ label }: { label: string }) {
  return (
    <div className="flex items-center">
      <span className="w-[78px] text-right text-[10px] uppercase tracking-wider text-white/40">
        {label}
      </span>
    </div>
  );
}

function Box({
  cell,
  point,
  total,
}: {
  cell: Cell;
  point: ConfusionPoint;
  total: number;
}) {
  const tone = TONE[cell.tone];
  const value = point[cell.key];
  const pct = (value / total) * 100;
  return (
    <div
      className={`relative overflow-hidden rounded-xl border ${tone.ring} bg-black/30 p-3`}
      style={{ boxShadow: `inset 0 0 28px -8px ${tone.glow}` }}
    >
      <div className={`text-[22px] font-semibold leading-none tabular-nums ${tone.text}`}>
        {value}
      </div>
      <div className="mt-1 text-[11px] font-medium text-white/80">{cell.label}</div>
      <div className="text-[10.5px] text-white/45">{cell.sub}</div>
      <div className="mt-1 font-mono text-[10px] text-white/40">{pct.toFixed(0)}% of book</div>
    </div>
  );
}
