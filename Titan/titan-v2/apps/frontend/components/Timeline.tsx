import type { CaseEvent, CaseEventType } from "../lib/api";
import { Avatar } from "./CaseCard";
import TypologyBadge from "./TypologyBadge";

const TONE: Record<CaseEventType, { dot: string; pill: string; label: string }> = {
  opened: {
    dot: "#2DE1C2",
    pill: "border-teal-400/35 bg-teal-500/10 text-teal-300",
    label: "Opened",
  },
  assigned: {
    dot: "#8B7CFF",
    pill: "border-violet-400/35 bg-violet-500/10 text-violet-300",
    label: "Assigned",
  },
  note: {
    dot: "#94a3b8",
    pill: "border-white/12 bg-white/[0.05] text-white/65",
    label: "Note",
  },
  status: {
    dot: "#fbbf24",
    pill: "border-amber-400/35 bg-amber-500/10 text-amber-300",
    label: "Status",
  },
  sar: {
    dot: "#10b981",
    pill: "border-emerald-400/35 bg-emerald-500/10 text-emerald-300",
    label: "SAR",
  },
  reopened: {
    dot: "#fb923c",
    pill: "border-orange-400/35 bg-orange-500/10 text-orange-300",
    label: "Reopened",
  },
  typology_assigned: {
    dot: "#a855f7",
    pill: "border-violet-400/35 bg-violet-500/10 text-violet-300",
    label: "Typology",
  },
};

function fmtRel(iso: string): string {
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return iso;
  const diff = Date.now() - t;
  const m = Math.floor(diff / 60_000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.floor(h / 24);
  if (d < 14) return `${d}d ago`;
  return new Date(t).toLocaleDateString();
}

export default function Timeline({ events }: { events: CaseEvent[] }) {
  if (!events?.length) {
    return (
      <div className="rounded-xl border border-white/10 bg-black/20 p-4 text-[12.5px] text-white/55">
        No events yet.
      </div>
    );
  }
  return (
    <ol className="ws-timeline relative">
      {events.map((e, idx) => {
        const tone = TONE[e.type] ?? TONE.note;
        const isLast = idx === events.length - 1;
        return (
          <li key={e.id} className="ws-timeline-item">
            {!isLast && <span className="ws-timeline-rail" aria-hidden />}
            <span
              className="ws-timeline-dot"
              style={{ background: tone.dot, boxShadow: `0 0 0 3px ${tone.dot}33` }}
            />
            <div className="flex-1">
              <div className="flex flex-wrap items-baseline gap-2">
                <span
                  className={`inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[10px] uppercase tracking-wider ${tone.pill}`}
                >
                  {tone.label}
                </span>
                {e.from_status && e.to_status && (
                  <span className="font-mono text-[10.5px] text-white/45">
                    {e.from_status} → {e.to_status}
                  </span>
                )}
                <span className="ml-auto text-[10.5px] text-white/45">
                  <span title={e.created_at_iso}>{fmtRel(e.created_at_iso)}</span>
                </span>
              </div>
              <div className="mt-1.5 flex items-center gap-2 text-[11.5px] text-white/65">
                <Avatar name={e.actor} size={14} />
                <span>{e.actor}</span>
              </div>
              {e.body && (
                <div className="mt-1 whitespace-pre-wrap text-[12.5px] leading-snug text-white/85">
                  {e.body}
                </div>
              )}
              {e.type === "sar" && e.payload?.sar_id && (
                <div className="mt-1.5 inline-flex items-center gap-2 rounded-md border border-emerald-400/30 bg-emerald-500/10 px-2 py-0.5 font-mono text-[10.5px] text-emerald-300">
                  📄 {e.payload.sar_id}
                </div>
              )}
              {e.type === "typology_assigned" && e.payload?.code && (
                <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                  <TypologyBadge
                    match={{
                      code: e.payload.code,
                      confidence: e.payload.confidence ?? 0,
                    }}
                    size="xs"
                    showName
                  />
                  {Array.isArray(e.payload.runners_up) &&
                    e.payload.runners_up.length > 0 && (
                      <span className="text-[10px] text-white/40">
                        +{e.payload.runners_up.length} runner
                        {e.payload.runners_up.length === 1 ? "" : "s"}-up
                      </span>
                    )}
                </div>
              )}
              {e.type === "assigned" && e.payload && (
                <div className="mt-1 text-[11px] text-white/45">
                  {e.payload.from ? (
                    <>
                      {e.payload.from}{" "}
                      <span className="text-white/30">→</span>{" "}
                      {e.payload.to ?? "—"}
                    </>
                  ) : (
                    <>{e.payload.to ?? "—"}</>
                  )}
                </div>
              )}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
