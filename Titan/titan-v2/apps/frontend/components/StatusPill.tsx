"use client";
import { useEffect, useState } from "react";
import { health } from "../lib/api";

export default function StatusPill() {
  const [state, setState] = useState<"checking" | "ok" | "down">("checking");
  const [block, setBlock] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function tick() {
      try {
        const h = await health();
        if (cancelled) return;
        setState(h?.chain?.connected ? "ok" : "down");
        setBlock(h?.chain?.block ?? null);
      } catch {
        if (!cancelled) setState("down");
      }
    }
    tick();
    const id = setInterval(tick, 7000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  const label =
    state === "checking" ? "checking…" :
    state === "ok" ? `chain · block ${block ?? "?"}` :
    "offline";
  const cls =
    state === "ok" ? "pill pill-ok" :
    state === "down" ? "pill pill-bad" :
    "pill";

  return (
    <span className={cls}>
      <span
        className={`inline-block h-1.5 w-1.5 rounded-full ${
          state === "ok" ? "bg-teal-400 animate-pulseSoft" :
          state === "down" ? "bg-rose-400" : "bg-white/40"
        }`}
      />
      {label}
    </span>
  );
}
