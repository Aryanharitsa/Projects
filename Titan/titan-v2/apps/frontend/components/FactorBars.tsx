import type { Factor } from "../lib/api";

const PRETTY: Record<string, string> = {
  structuring: "Structuring",
  velocity_spike: "Velocity Spike",
  round_trip: "Round-Trip Cycle",
  sanctions_hit: "Sanctions Hit",
  fan_in: "Fan-in",
  fan_out: "Fan-out",
  high_risk_geo: "High-Risk Geo",
  round_amount: "Round Amounts",
};

export default function FactorBars({ factors }: { factors: Factor[] }) {
  return (
    <div className="space-y-2.5">
      {factors.map((f) => {
        const pct = (f.points / f.weight) * 100;
        const fired = f.points > 0;
        return (
          <div key={f.name}>
            <div className="flex items-baseline justify-between">
              <span
                className={`text-[12px] font-medium ${
                  fired ? "text-white/90" : "text-white/40"
                }`}
              >
                {PRETTY[f.name] ?? f.name}
              </span>
              <span
                className={`font-mono text-[11px] tabular-nums ${
                  fired ? "text-teal-400" : "text-white/30"
                }`}
              >
                {f.points.toFixed(1)} / {f.weight}
              </span>
            </div>
            <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-white/[0.06]">
              <div
                className="h-full rounded-full"
                style={{
                  width: `${Math.min(100, Math.max(0, pct))}%`,
                  background: fired
                    ? "linear-gradient(90deg, #2DE1C2, #6E5BFF)"
                    : "rgba(255,255,255,0.12)",
                }}
              />
            </div>
            {fired && (
              <p className="mt-1 text-[11px] leading-snug text-white/55">
                {f.detail}
              </p>
            )}
          </div>
        );
      })}
    </div>
  );
}
