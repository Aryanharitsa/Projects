import Link from "next/link";
import type { CaseSummary, CaseStatus } from "../lib/api";
import PriorityDot from "./PriorityDot";
import AgePill from "./AgePill";
import TypologyBadge from "./TypologyBadge";

const STATUS_TONE: Record<CaseStatus, string> = {
  open: "border-violet-400/30 bg-violet-500/10 text-violet-300",
  review: "border-teal-400/30 bg-teal-500/10 text-teal-300",
  cleared: "border-white/15 bg-white/[0.04] text-white/55",
  escalated: "border-amber-400/35 bg-amber-500/10 text-amber-300",
  sar_filed: "border-emerald-400/35 bg-emerald-500/10 text-emerald-300",
};

const STATUS_LABEL: Record<CaseStatus, string> = {
  open: "open",
  review: "in review",
  cleared: "cleared",
  escalated: "escalated",
  sar_filed: "SAR filed",
};

function ScoreBadge({ score, priority }: { score: number; priority: string }) {
  const color =
    priority === "critical"
      ? "#ef4444"
      : priority === "high"
      ? "#fb923c"
      : priority === "medium"
      ? "#fbbf24"
      : "#22d3a8";
  const pct = Math.max(0, Math.min(100, score));
  const ring = `conic-gradient(${color} ${pct * 3.6}deg, rgba(255,255,255,0.06) 0)`;
  return (
    <div
      className="relative grid place-items-center rounded-full"
      style={{ width: 44, height: 44, background: ring }}
    >
      <div
        className="absolute inset-[4px] rounded-full"
        style={{ background: "rgba(7,11,20,0.92)" }}
      />
      <span
        className="relative text-[12.5px] font-semibold tabular-nums"
        style={{ color }}
      >
        {score.toFixed(0)}
      </span>
    </div>
  );
}

export default function CaseCard({ c }: { c: CaseSummary }) {
  return (
    <Link
      href={`/cases/${c.id}`}
      className="ws-case-card group flex flex-col gap-2.5 transition hover:-translate-y-0.5"
    >
      <div className="flex items-center gap-2.5">
        <PriorityDot priority={c.priority} pulse={c.priority === "critical" && c.status !== "cleared" && c.status !== "sar_filed"} />
        <span className="font-mono text-[10.5px] text-white/45">{c.id}</span>
        <span className="ml-auto">
          <AgePill hours={c.age_hours} sla={c.sla} />
        </span>
      </div>

      <div className="flex items-center gap-3">
        <ScoreBadge score={c.alert_score} priority={c.priority} />
        <div className="min-w-0 flex-1">
          <div className="truncate font-mono text-[12.5px] text-white/85">
            {c.account_id}
          </div>
          {c.display_name && (
            <div className="truncate text-[11px] text-white/55">
              {c.display_name}
            </div>
          )}
        </div>
      </div>

      <p className="line-clamp-2 text-[11.5px] leading-snug text-white/65">
        {c.summary}
      </p>

      <div className="flex flex-wrap items-center gap-1.5 pt-1">
        <span
          className={`inline-flex rounded-md border px-1.5 py-0.5 text-[10px] uppercase tracking-wider ${STATUS_TONE[c.status]}`}
        >
          {STATUS_LABEL[c.status]}
        </span>
        {c.typology_code && (
          <TypologyBadge
            match={{
              code: c.typology_code,
              confidence: c.typology_confidence ?? 0,
            }}
            size="xs"
          />
        )}
        {c.sanctions_count > 0 && (
          <span className="inline-flex rounded-md border border-rose-400/35 bg-rose-500/10 px-1.5 py-0.5 text-[10px] uppercase tracking-wider text-rose-300">
            {c.sanctions_count} sanctions
          </span>
        )}
        {c.fired_count > 0 && (
          <span className="inline-flex rounded-md border border-white/10 bg-white/[0.04] px-1.5 py-0.5 text-[10px] text-white/55">
            {c.fired_count} factor{c.fired_count !== 1 ? "s" : ""}
          </span>
        )}
        {c.assignee ? (
          <span className="ml-auto inline-flex items-center gap-1.5 rounded-md border border-white/10 bg-white/[0.04] px-1.5 py-0.5 text-[10.5px] text-white/70">
            <Avatar name={c.assignee} />
            {c.assignee}
          </span>
        ) : (
          <span className="ml-auto text-[10.5px] uppercase tracking-wider text-white/35">
            unassigned
          </span>
        )}
      </div>
    </Link>
  );
}

export function Avatar({ name, size = 14 }: { name: string; size?: number }) {
  const initials = name
    .split(/[\s_-]+/)
    .filter(Boolean)
    .map((p) => p[0]?.toUpperCase() ?? "")
    .join("")
    .slice(0, 2) || "?";
  // Hash-derived hue so the same name always gets the same colour.
  let h = 0;
  for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) | 0;
  const hue = Math.abs(h) % 360;
  return (
    <span
      className="inline-grid place-items-center rounded-full font-semibold text-[8.5px]"
      style={{
        width: size,
        height: size,
        background: `hsl(${hue}deg 65% 32%)`,
        color: `hsl(${hue}deg 80% 88%)`,
      }}
      aria-hidden
    >
      {initials}
    </span>
  );
}
