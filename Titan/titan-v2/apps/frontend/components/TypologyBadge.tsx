"use client";

import type { TypologyCode, TypologyMatch } from "../lib/api";

/**
 * Hard-coded fallback accents per code so the badge can render without
 * a network round-trip to ``/aml/typologies``. Keep these in sync with
 * the engine library (`apps/ai-aml/typology.py`).
 */
const FALLBACK_ACCENTS: Record<TypologyCode, string> = {
  SMURF: "#f59e0b",
  LAYER: "#a855f7",
  TBML: "#06b6d4",
  MULE: "#22c55e",
  SANCEV: "#f43f5e",
  INTEG: "#0ea5e9",
};

const FALLBACK_ICONS: Record<TypologyCode, string> = {
  SMURF: "◐",
  LAYER: "↻",
  TBML: "◈",
  MULE: "◫",
  SANCEV: "⊘",
  INTEG: "◇",
};

const FALLBACK_NAMES: Record<TypologyCode, string> = {
  SMURF: "Smurfing / Structuring",
  LAYER: "Layering",
  TBML: "Trade-Based ML",
  MULE: "Mule Network",
  SANCEV: "Sanctions Evasion",
  INTEG: "Integration",
};

export function typologyAccent(code: TypologyCode | null | undefined): string {
  if (!code) return "#94a3b8";
  return FALLBACK_ACCENTS[code] ?? "#94a3b8";
}

export function typologyIcon(code: TypologyCode | null | undefined): string {
  if (!code) return "·";
  return FALLBACK_ICONS[code] ?? "·";
}

export function typologyName(code: TypologyCode | null | undefined): string {
  if (!code) return "";
  return FALLBACK_NAMES[code] ?? code;
}

/**
 * Compact in-row badge — icon + code + confidence ring.
 * Used in case-queue cards and AML console rows.
 */
export default function TypologyBadge({
  match,
  size = "sm",
  showName = false,
  onClick,
}: {
  match: Pick<TypologyMatch, "code" | "confidence"> & Partial<TypologyMatch>;
  size?: "xs" | "sm" | "md";
  showName?: boolean;
  onClick?: () => void;
}) {
  const accent = match.accent || typologyAccent(match.code);
  const icon = match.icon || typologyIcon(match.code);
  const name = match.name || typologyName(match.code);
  const conf = Math.max(0, Math.min(1, match.confidence ?? 0));
  const ringDeg = Math.round(conf * 360);

  const dims =
    size === "xs"
      ? { ring: 16, font: "text-[9px]", pad: "px-1.5 py-0.5 text-[10px] gap-1" }
      : size === "md"
        ? { ring: 26, font: "text-xs", pad: "px-2.5 py-1 text-[11px] gap-1.5" }
        : { ring: 20, font: "text-[10px]", pad: "px-2 py-1 text-[10px] gap-1.5" };

  const ringStyle: React.CSSProperties = {
    width: dims.ring,
    height: dims.ring,
    background: `conic-gradient(${accent} ${ringDeg}deg, ${accent}22 ${ringDeg}deg)`,
    borderRadius: "9999px",
  };
  const coreStyle: React.CSSProperties = {
    width: dims.ring - 4,
    height: dims.ring - 4,
    background: "rgba(15, 23, 42, 0.85)",
    color: accent,
  };

  const chipStyle: React.CSSProperties = {
    background: `${accent}1a`,
    border: `1px solid ${accent}55`,
    color: `${accent}`,
  };

  const Wrapper: any = onClick ? "button" : "span";

  return (
    <Wrapper
      className={`ws-typology-badge inline-flex items-center rounded-full ${dims.pad} font-medium leading-none transition hover:brightness-110`}
      style={chipStyle}
      onClick={onClick}
      title={`${name} — ${(conf * 100).toFixed(0)}% confidence`}
    >
      <span className="relative inline-flex items-center justify-center" style={ringStyle}>
        <span className="rounded-full inline-flex items-center justify-center" style={coreStyle}>
          <span className={`${dims.font} leading-none`}>{icon}</span>
        </span>
      </span>
      <span className="whitespace-nowrap tracking-wide" style={{ color: accent }}>
        {showName ? name : (match.code ?? "·")}
      </span>
      <span className="text-white/60 tabular-nums">
        {(conf * 100).toFixed(0)}%
      </span>
    </Wrapper>
  );
}
