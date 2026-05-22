"use client";

import { useMemo, useState } from "react";
import type { TypologyMatch } from "../lib/api";
import TypologyBadge, { typologyAccent } from "./TypologyBadge";

/**
 * Full typology breakdown for the case detail / AML console drawer.
 * Shows the top-N matches with a tab bar, the primary's confidence
 * dial, the contributing-evidence bar list, the narrative, and the
 * recommended action — everything the analyst needs to verify a
 * typology before locking it into a SAR draft.
 */
export default function TypologyPanel({
  matches,
  caption,
  className,
}: {
  matches: TypologyMatch[];
  caption?: string;
  className?: string;
}) {
  const [activeIdx, setActiveIdx] = useState(0);
  const active = matches[activeIdx];

  if (!matches || matches.length === 0) {
    return (
      <div
        className={`ws-typology-panel ws-typology-panel-empty rounded-xl border border-white/10 bg-slate-950/40 p-4 text-sm text-slate-400 ${className || ""}`}
      >
        <div className="font-medium text-slate-300 mb-1">No typology matched</div>
        <div className="text-xs text-slate-400">
          No FATF / Wolfsberg playbook fit above the 35% confidence floor for
          this account. Review per-factor evidence below — the case may still
          warrant escalation on individual detectors alone.
        </div>
      </div>
    );
  }

  return (
    <div
      className={`ws-typology-panel rounded-xl border border-white/10 bg-slate-950/60 p-4 ${className || ""}`}
      style={{
        background: `radial-gradient(circle at top right, ${active?.accent || "#94a3b8"}14, transparent 55%), radial-gradient(circle at bottom left, ${matches[1]?.accent || "transparent"}10, transparent 50%), rgba(15, 23, 42, 0.65)`,
      }}
    >
      <div className="flex items-center justify-between mb-3">
        <div>
          <div className="text-[10px] uppercase tracking-[0.18em] text-slate-400">
            Laundering typology
          </div>
          <div className="text-xs text-slate-500 mt-0.5">
            {caption || `${matches.length} match${matches.length === 1 ? "" : "es"} above 35% confidence floor`}
          </div>
        </div>
        {matches.length > 1 && (
          <div className="inline-flex bg-slate-900/70 border border-white/10 rounded-full p-0.5 gap-0.5">
            {matches.map((m, i) => (
              <button
                key={m.code}
                onClick={() => setActiveIdx(i)}
                className="px-2.5 py-1 rounded-full text-[10px] font-medium transition"
                style={
                  i === activeIdx
                    ? {
                        background: `${m.accent}22`,
                        color: m.accent,
                        boxShadow: `0 0 0 1px ${m.accent}55`,
                      }
                    : { color: "rgba(148, 163, 184, 0.7)" }
                }
              >
                {m.code}
              </button>
            ))}
          </div>
        )}
      </div>

      {active && <TypologyPanelInner match={active} />}
    </div>
  );
}

function TypologyPanelInner({ match }: { match: TypologyMatch }) {
  const accent = match.accent || typologyAccent(match.code);
  const conf = Math.max(0, Math.min(1, match.confidence));
  const confDeg = Math.round(conf * 360);
  const maxContribution = useMemo(
    () =>
      Math.max(
        0.0001,
        ...match.evidence.map((e) => e.weight)
      ),
    [match.evidence]
  );

  return (
    <div className="space-y-4">
      {/* Hero row: ring + name + code + summary */}
      <div className="flex items-start gap-4">
        <div
          className="ws-typology-ring relative flex items-center justify-center shrink-0"
          style={{
            width: 76,
            height: 76,
            borderRadius: "9999px",
            background: `conic-gradient(${accent} ${confDeg}deg, ${accent}1f ${confDeg}deg)`,
            boxShadow: `0 0 24px ${accent}33`,
          }}
        >
          <div
            className="flex flex-col items-center justify-center rounded-full"
            style={{
              width: 62,
              height: 62,
              background: "rgba(2, 6, 23, 0.92)",
              color: accent,
            }}
          >
            <span className="text-2xl leading-none">{match.icon}</span>
            <span className="text-[10px] uppercase mt-0.5 tabular-nums tracking-wide">
              {(conf * 100).toFixed(0)}%
            </span>
          </div>
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-0.5 flex-wrap">
            <span className="text-base font-semibold text-white">{match.name}</span>
            <span
              className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-mono"
              style={{
                color: accent,
                background: `${accent}1c`,
                border: `1px solid ${accent}44`,
              }}
            >
              {match.code}
            </span>
            <SeverityChip severity={match.severity_floor} />
          </div>
          <div className="text-xs text-slate-400 leading-relaxed">{match.summary}</div>
        </div>
      </div>

      {/* Contributing evidence bars */}
      <div>
        <div className="text-[10px] uppercase tracking-[0.18em] text-slate-400 mb-2">
          Contributing evidence
        </div>
        {match.evidence.length === 0 ? (
          <div className="text-xs text-slate-500 italic">No contributors above zero.</div>
        ) : (
          <ul className="space-y-1.5">
            {match.evidence.map((ev) => {
              const widthPct = Math.min(100, (ev.contribution / maxContribution) * 100);
              const signalPct = Math.round(ev.signal * 100);
              return (
                <li
                  key={ev.key}
                  className="ws-typology-evidence-row grid items-center gap-2"
                  style={{ gridTemplateColumns: "1fr 80px 50px" }}
                >
                  <div className="min-w-0">
                    <div className="text-xs text-slate-200 truncate">{ev.label}</div>
                    {ev.detail && (
                      <div className="text-[10px] text-slate-500 truncate">{ev.detail}</div>
                    )}
                  </div>
                  <div className="relative h-2.5 rounded-full bg-slate-800/80 overflow-hidden">
                    <div
                      className="absolute inset-y-0 left-0 rounded-full"
                      style={{
                        width: `${widthPct}%`,
                        background: `linear-gradient(90deg, ${accent}, ${accent}aa)`,
                      }}
                    />
                  </div>
                  <div
                    className="text-right text-[10px] tabular-nums"
                    style={{ color: accent }}
                  >
                    {signalPct}%
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      {/* Narrative */}
      <div>
        <div className="text-[10px] uppercase tracking-[0.18em] text-slate-400 mb-1.5">
          Auto-generated narrative
        </div>
        <p className="text-sm text-slate-200 leading-relaxed italic border-l-2 pl-3"
          style={{ borderColor: `${accent}66` }}
        >
          {match.narrative || match.summary}
        </p>
      </div>

      {/* Recommended action */}
      <div>
        <div className="text-[10px] uppercase tracking-[0.18em] text-slate-400 mb-1.5">
          Recommended action
        </div>
        <div
          className="text-xs text-slate-200 leading-relaxed rounded-lg p-2.5"
          style={{
            background: `${accent}12`,
            border: `1px solid ${accent}33`,
          }}
        >
          {match.recommended_action}
        </div>
      </div>
    </div>
  );
}

function SeverityChip({
  severity,
}: {
  severity: "low" | "medium" | "high" | "critical";
}) {
  const tone =
    severity === "critical"
      ? { bg: "#ef444422", color: "#fca5a5", label: "critical floor" }
      : severity === "high"
        ? { bg: "#fb923c22", color: "#fdba74", label: "high floor" }
        : severity === "medium"
          ? { bg: "#fbbf2422", color: "#fcd34d", label: "medium floor" }
          : { bg: "#22d3a822", color: "#5eead4", label: "low floor" };
  return (
    <span
      className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px]"
      style={{ background: tone.bg, color: tone.color }}
    >
      {tone.label}
    </span>
  );
}

/** Re-export for callers that just need the badge alongside the panel. */
export { TypologyBadge };
