import type { CaseSla } from "../lib/api";

const TONE: Record<CaseSla, string> = {
  ok: "border-teal-400/30 bg-teal-500/10 text-teal-300",
  warn: "border-amber-400/35 bg-amber-500/10 text-amber-300",
  breach: "border-rose-400/40 bg-rose-500/10 text-rose-300",
};

const LABEL: Record<CaseSla, string> = {
  ok: "on-track",
  warn: "warning",
  breach: "breached",
};

export function fmtAge(hours: number): string {
  if (hours < 1) {
    const m = Math.max(1, Math.round(hours * 60));
    return `${m}m`;
  }
  if (hours < 24) {
    return `${hours.toFixed(1)}h`;
  }
  const d = Math.floor(hours / 24);
  const h = Math.round(hours - d * 24);
  return h > 0 ? `${d}d ${h}h` : `${d}d`;
}

export default function AgePill({
  hours,
  sla,
}: {
  hours: number;
  sla: CaseSla;
}) {
  return (
    <span
      title={`${LABEL[sla]} · ${hours.toFixed(1)}h since open`}
      className={`inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[10.5px] font-medium ${TONE[sla]}`}
    >
      <span
        className="inline-block h-1.5 w-1.5 rounded-full"
        style={{
          background:
            sla === "ok" ? "#22d3a8" : sla === "warn" ? "#fbbf24" : "#ef4444",
        }}
      />
      {fmtAge(hours)}
    </span>
  );
}
