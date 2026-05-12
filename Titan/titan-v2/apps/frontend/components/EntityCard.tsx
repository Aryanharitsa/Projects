"use client";

import type { NetEntity } from "../lib/api";

const BAND_COLOR: Record<NetEntity["band"], string> = {
  low: "#22d3a8",
  medium: "#fbbf24",
  high: "#fb923c",
  critical: "#ef4444",
};

const FLAG_LABEL: Record<string, string> = {
  structuring: "STRUCT",
  velocity_spike: "VELO",
  round_trip: "CYCLE",
  sanctions: "SAN",
  sanctions_hit: "SAN-HIT",
  fan_in: "FAN-IN",
  fan_out: "FAN-OUT",
  high_risk_geo: "GEO",
  round_amount: "ROUND",
};

/** Sidebar row for a single resolved entity. Compact, click-to-select. */
export default function EntityCard({
  entity,
  selected,
  ablated,
  onClick,
  onAblateToggle,
}: {
  entity: NetEntity;
  selected: boolean;
  ablated: boolean;
  onClick: () => void;
  onAblateToggle: () => void;
}) {
  const color = BAND_COLOR[entity.band];
  const lift = entity.network_delta;
  const liftTone =
    Math.abs(lift) < 0.5
      ? "text-white/45"
      : lift > 0
      ? "text-amber-300"
      : "text-teal-300";

  return (
    <div
      className={`ws-net-row group relative ${
        selected ? "ws-net-row-sel" : ""
      } ${ablated ? "ws-net-row-ablated" : ""}`}
      onClick={onClick}
      role="button"
    >
      <div
        className="ws-net-ring"
        style={{
          background: `conic-gradient(${color} ${
            entity.network_risk * 3.6
          }deg, rgba(255,255,255,0.06) 0)`,
        }}
      >
        <div className="ws-net-ring-core">
          <span style={{ color }}>{Math.round(entity.network_risk)}</span>
        </div>
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5">
          <div className="truncate text-[13.5px] font-medium text-white/90">
            {entity.display_name}
          </div>
          {entity.is_aggregate && (
            <span className="ws-net-pill ws-net-pill-agg">
              ×{entity.member_count}
            </span>
          )}
          {entity.sanctioned && (
            <span className="ws-net-pill ws-net-pill-san">san</span>
          )}
        </div>
        <div className="mt-0.5 flex items-center gap-2 text-[11px] text-white/45">
          <span className="font-mono">{entity.id}</span>
          <span className="text-white/20">·</span>
          <span>{entity.band}</span>
          <span className="text-white/20">·</span>
          <span className={liftTone}>
            {lift > 0 ? `+${lift.toFixed(1)}` : lift.toFixed(1)}
          </span>
        </div>
        {entity.flags.length > 0 && (
          <div className="mt-1.5 flex flex-wrap gap-1">
            {entity.flags.slice(0, 4).map((f) => (
              <span key={f} className="ws-net-flag">
                {FLAG_LABEL[f] || f}
              </span>
            ))}
          </div>
        )}
      </div>
      <button
        className={`ws-net-ablate ${ablated ? "ws-net-ablate-on" : ""}`}
        onClick={(e) => {
          e.stopPropagation();
          onAblateToggle();
        }}
        title={ablated ? "Restore in counterfactual" : "Ablate in counterfactual"}
      >
        {ablated ? "✓" : "−"}
      </button>
    </div>
  );
}
