"use client";

import { useEffect, useState } from "react";
import { casesStats } from "../lib/api";

/** Tiny live-count chip shown next to the "Cases" nav link.
 *
 * Pulses red when there's at least one critical/high case waiting, amber when
 * SLA breaches exist, otherwise a quiet white count. Hidden when zero so the
 * nav stays calm in the empty state.
 */
export default function CasesNavPill() {
  const [open, setOpen] = useState<number | null>(null);
  const [breach, setBreach] = useState<number>(0);
  const [critical, setCritical] = useState<number>(0);

  useEffect(() => {
    let cancelled = false;
    async function tick() {
      try {
        const s = await casesStats();
        if (cancelled) return;
        setOpen(s.open_total);
        setBreach(s.by_sla?.breach ?? 0);
        setCritical(s.by_priority?.critical ?? 0);
      } catch {
        if (!cancelled) setOpen(null);
      }
    }
    tick();
    const id = setInterval(tick, 12_000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  if (open === null || open <= 0) return null;

  const tone =
    critical > 0
      ? "border-rose-400/45 bg-rose-500/15 text-rose-200"
      : breach > 0
      ? "border-amber-400/45 bg-amber-500/15 text-amber-200"
      : "border-white/15 bg-white/[0.06] text-white/80";

  return (
    <span
      className={`inline-flex min-w-[18px] items-center justify-center rounded-full border px-1.5 py-0 text-[10.5px] font-semibold ${tone}`}
      title={`${open} open · ${critical} critical · ${breach} breached`}
    >
      {open}
    </span>
  );
}
