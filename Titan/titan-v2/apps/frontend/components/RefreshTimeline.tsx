import type { ProfileRefresh } from "../lib/api";

/** KYC refresh schedule visualisation.
 *
 * Three pegs on a single horizontal rail:
 *
 *     anchor (KYC done) ── today ── next due
 *
 * The progress-bar fill colour reflects refresh status:
 *   current  → teal      (today < due − 30d)
 *   due_soon → amber     (today ∈ [due − 30d, due])
 *   overdue  → rose      (today > due)
 *
 * Numbers are short on purpose — the eye reads the bar first, the text
 * only confirms.
 */
export default function RefreshTimeline({
  anchor,
  due,
  refresh,
  bucketInterval,
}: {
  anchor: string | null;
  due: string | null;
  refresh: ProfileRefresh;
  bucketInterval?: number;
}) {
  const anchorDt = anchor ? new Date(anchor) : null;
  const dueDt = due ? new Date(due) : null;
  const now = new Date();
  let pct = 0;
  if (anchorDt && dueDt) {
    const total = dueDt.getTime() - anchorDt.getTime();
    const elapsed = Math.max(0, now.getTime() - anchorDt.getTime());
    pct = total > 0 ? Math.min(100, (elapsed / total) * 100) : 100;
  }

  const tone = refresh.tone || "muted";
  const toneFill: Record<string, string> = {
    teal: "linear-gradient(90deg, rgba(34,211,168,0.85), rgba(34,211,168,0.30))",
    amber: "linear-gradient(90deg, rgba(251,191,36,0.85), rgba(251,191,36,0.30))",
    rose: "linear-gradient(90deg, rgba(239,68,68,0.85), rgba(239,68,68,0.30))",
    muted: "linear-gradient(90deg, rgba(255,255,255,0.30), rgba(255,255,255,0.10))",
  };
  const toneText: Record<string, string> = {
    teal: "#5eead4",
    amber: "#fcd34d",
    rose: "#fda4af",
    muted: "rgba(255,255,255,0.55)",
  };

  return (
    <div className="space-y-3">
      <div className="flex items-baseline justify-between">
        <div className="text-[11px] uppercase tracking-[0.18em] text-white/45">
          KYC refresh cycle
        </div>
        <div className="text-[11px]" style={{ color: toneText[tone] }}>
          {refresh.label}
          {refresh.days_to_due !== null && (
            <span className="ml-1.5 text-white/55">
              ({Math.abs(refresh.days_to_due).toFixed(0)}d
              {refresh.days_to_due < 0 ? " overdue" : " to due"})
            </span>
          )}
        </div>
      </div>

      <div className="relative h-3 rounded-full border border-white/10 bg-white/[0.03] overflow-hidden">
        {/* Fill */}
        <div
          className="absolute inset-y-0 left-0 rounded-full"
          style={{
            width: `${pct}%`,
            background: toneFill[tone],
            transition: "width 250ms",
          }}
        />
        {/* "today" marker */}
        <div
          className="absolute top-[-2px] bottom-[-2px] w-px"
          style={{
            left: `${pct}%`,
            background:
              "linear-gradient(180deg, rgba(255,255,255,0.85), rgba(255,255,255,0.30))",
            boxShadow: "0 0 6px rgba(255,255,255,0.45)",
          }}
        />
      </div>

      <div className="grid grid-cols-3 text-[11px]">
        <div>
          <div className="text-white/40">Anchor</div>
          <div className="text-white/85">
            {anchorDt ? anchorDt.toISOString().slice(0, 10) : "—"}
          </div>
        </div>
        <div className="text-center">
          <div className="text-white/40">Today</div>
          <div className="text-white/85">{now.toISOString().slice(0, 10)}</div>
        </div>
        <div className="text-right">
          <div className="text-white/40">
            Next due
            {bucketInterval && (
              <span className="ml-1 text-white/30">· {bucketInterval}d</span>
            )}
          </div>
          <div className="text-white/85">
            {dueDt ? dueDt.toISOString().slice(0, 10) : "—"}
          </div>
        </div>
      </div>
    </div>
  );
}
