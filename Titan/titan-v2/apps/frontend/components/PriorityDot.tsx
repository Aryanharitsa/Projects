import type { CasePriority } from "../lib/api";

const COLOR: Record<CasePriority, string> = {
  critical: "#ef4444",
  high: "#fb923c",
  medium: "#fbbf24",
  low: "#22d3a8",
};

export default function PriorityDot({
  priority,
  size = 8,
  pulse = false,
}: {
  priority: CasePriority;
  size?: number;
  pulse?: boolean;
}) {
  const color = COLOR[priority];
  return (
    <span className="relative inline-flex" style={{ width: size, height: size }}>
      <span
        className="absolute inset-0 rounded-full"
        style={{ background: color, boxShadow: `0 0 0 2px ${color}30` }}
      />
      {pulse && (
        <span
          className="absolute inset-0 animate-pulseSoft rounded-full"
          style={{ background: `${color}66` }}
        />
      )}
    </span>
  );
}

export const PRIORITY_LABEL: Record<CasePriority, string> = {
  critical: "Critical",
  high: "High",
  medium: "Medium",
  low: "Low",
};

export const PRIORITY_COLORS = COLOR;
