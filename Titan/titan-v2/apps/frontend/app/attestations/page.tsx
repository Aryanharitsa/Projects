"use client";

import { useCallback, useEffect, useState } from "react";
import { Attestation, lookupAttestation, recentAttestations } from "../../lib/api";

export default function AttestationsPage() {
  const [hash, setHash] = useState("");
  const [result, setResult] = useState<Attestation | null>(null);
  const [recent, setRecent] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const refreshRecent = useCallback(async () => {
    try {
      setRecent(await recentAttestations(15));
    } catch {
      // chain may be offline; surface only when nothing renders
    }
  }, []);

  useEffect(() => {
    refreshRecent();
    const id = setInterval(refreshRecent, 12000);
    // pre-fill ?hash=… from KYC redirect
    const params = new URLSearchParams(window.location.search);
    const h = params.get("hash");
    if (h) {
      setHash(h);
      lookup(h);
    }
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const lookup = useCallback(async (h?: string) => {
    const target = (h ?? hash).trim();
    if (!target) return;
    setErr(null);
    setResult(null);
    setLoading(true);
    try {
      const r = await lookupAttestation(target);
      setResult(r);
    } catch (e: any) {
      setErr(e.message || "Lookup failed");
    } finally {
      setLoading(false);
    }
  }, [hash]);

  return (
    <div className="space-y-6">
      <header>
        <span className="pill pill-ok">on-chain · live</span>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight md:text-3xl">
          Attestation Explorer
        </h1>
        <p className="mt-1 max-w-2xl text-[13.5px] text-white/60">
          Verify any document hash against the AttestationRegistry contract.
          Recent attestations stream in below — auto-refreshing every 12s.
        </p>
      </header>

      {/* Search */}
      <section className="glass p-5">
        <div className="label">Document hash</div>
        <div className="flex gap-2">
          <input
            className="input flex-1 font-mono"
            placeholder="0x…"
            value={hash}
            onChange={(e) => setHash(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && lookup()}
          />
          <button className="btn-primary" onClick={() => lookup()} disabled={loading}>
            {loading ? "Looking up…" : "Look up"}
          </button>
        </div>
        {err && <p className="mt-3 text-[12px] text-rose-300">{err}</p>}

        {result && (
          <div
            className={`mt-5 rounded-xl border p-4 ${
              result.found
                ? "border-teal-400/30 bg-teal-500/[0.05]"
                : "border-rose-400/30 bg-rose-500/[0.05]"
            }`}
          >
            <div
              className={`text-[12px] uppercase tracking-wider ${
                result.found ? "text-teal-400" : "text-rose-300"
              }`}
            >
              {result.found ? "Verified · attested on chain" : "Not found"}
            </div>
            <div className="mt-3 grid gap-3 md:grid-cols-2">
              <KV k="subject" v={result.subject} mono />
              <KV k="verifierId" v={result.verifierId} />
              <KV k="timestamp" v={result.timestampIso || "—"} />
              <KV k="block" v={result.blockNumber ? String(result.blockNumber) : "—"} mono />
              <KV k="txHash" v={result.txHash || "—"} mono className="md:col-span-2" />
              <KV k="docHash" v={result.docHash} mono className="md:col-span-2" />
            </div>
          </div>
        )}
      </section>

      {/* Recent feed */}
      <section className="glass p-5">
        <div className="flex items-center justify-between">
          <div className="label">Recent attestations</div>
          <button className="text-[12px] text-teal-400 hover:underline" onClick={refreshRecent}>
            Refresh
          </button>
        </div>

        {recent.length === 0 ? (
          <div className="grid h-32 place-items-center text-center text-white/45">
            <div>
              <div className="text-2xl">∅</div>
              <div className="mt-1 text-[12.5px]">
                No attestations yet — run a KYC verification to seed one.
              </div>
            </div>
          </div>
        ) : (
          <div className="scroll-thin max-h-96 overflow-auto rounded-xl border border-white/10">
            <table className="w-full text-left text-[12px]">
              <thead className="bg-white/[0.04] text-[10.5px] uppercase tracking-wider text-white/45">
                <tr>
                  <th className="px-3 py-2">Block</th>
                  <th className="px-3 py-2">Subject</th>
                  <th className="px-3 py-2">Verifier</th>
                  <th className="px-3 py-2">Doc hash</th>
                  <th className="px-3 py-2">When</th>
                </tr>
              </thead>
              <tbody>
                {recent.map((r) => (
                  <tr
                    key={r.txHash}
                    className="cursor-pointer border-t border-white/5 transition hover:bg-white/[0.04]"
                    onClick={() => {
                      setHash(r.docHash);
                      lookup(r.docHash);
                    }}
                  >
                    <td className="px-3 py-2 font-mono text-white/70">{r.blockNumber}</td>
                    <td className="px-3 py-2 font-mono text-white/85">
                      {r.subject.slice(0, 6)}…{r.subject.slice(-4)}
                    </td>
                    <td className="px-3 py-2 text-white/75">{r.verifierId}</td>
                    <td className="px-3 py-2 font-mono text-white/60">
                      {r.docHash.slice(0, 12)}…
                    </td>
                    <td className="px-3 py-2 text-white/55">{r.timestampIso}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}

function KV({
  k,
  v,
  mono,
  className = "",
}: {
  k: string;
  v: string;
  mono?: boolean;
  className?: string;
}) {
  return (
    <div className={`flex items-center justify-between gap-3 ${className}`}>
      <span className="text-[11px] uppercase tracking-wider text-white/40">{k}</span>
      <span
        className={`flex-1 truncate text-right ${mono ? "font-mono" : ""} text-[12.5px] text-white/85`}
        title={v}
      >
        {v}
      </span>
    </div>
  );
}
