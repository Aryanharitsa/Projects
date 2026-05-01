"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import SimilarityRing, { GRADE_TINT } from "../../components/SimilarityRing";
import {
  ScreenResponse,
  ScreenResult,
  WatchlistEntry,
  WatchlistMeta,
  listWatchlist,
  screenSanctions,
} from "../../lib/api";

const SAMPLE_NAMES = [
  "Trident Exports",
  "Aurelia Shell Limited",
  "V. P. Ivansky",
  "Bharat Petroleum Corp.",
  "Crescent Maritime",
  "Indigo Peak Capital",
];

const JURISDICTIONS = [
  "", "RU", "IR", "KP", "SY", "BY", "AE", "MM", "CY", "IN",
];

export default function WatchlistPage() {
  const [namesText, setNamesText] = useState(SAMPLE_NAMES.join("\n"));
  const [juris, setJuris] = useState("");
  const [threshold, setThreshold] = useState(0.45);
  const [resp, setResp] = useState<ScreenResponse | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const [meta, setMeta] = useState<WatchlistMeta | null>(null);
  const [entries, setEntries] = useState<WatchlistEntry[]>([]);
  const [browseQ, setBrowseQ] = useState("");
  const [listLoading, setListLoading] = useState(true);

  // Load the bundled watchlist on mount.
  useEffect(() => {
    let cancel = false;
    (async () => {
      try {
        const data = await listWatchlist(50);
        if (!cancel) {
          setMeta(data.watchlist);
          setEntries(data.entries);
        }
      } catch (e: any) {
        if (!cancel) setErr(e.message || "Failed to load watchlist");
      } finally {
        if (!cancel) setListLoading(false);
      }
    })();
    return () => {
      cancel = true;
    };
  }, []);

  const names = useMemo(
    () =>
      namesText
        .split(/\r?\n/)
        .map((n) => n.trim())
        .filter(Boolean),
    [namesText],
  );

  const onScreen = useCallback(async () => {
    setErr(null);
    setLoading(true);
    setResp(null);
    try {
      const data = await screenSanctions(names, {
        jurisdiction: juris || undefined,
        threshold,
        topK: 5,
      });
      setResp(data);
    } catch (e: any) {
      setErr(e.message || "Screening failed");
    } finally {
      setLoading(false);
    }
  }, [names, juris, threshold]);

  const filteredEntries = useMemo(() => {
    if (!browseQ.trim()) return entries;
    const q = browseQ.toLowerCase();
    return entries.filter(
      (e) =>
        e.name.toLowerCase().includes(q) ||
        e.id.toLowerCase().includes(q) ||
        e.aliases.some((a) => a.toLowerCase().includes(q)) ||
        e.jurisdiction.toLowerCase().includes(q) ||
        e.list.toLowerCase().includes(q),
    );
  }, [entries, browseQ]);

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <span className="pill pill-ok">
            Watchlist · {meta ? meta.version : "loading"}
          </span>
          <h1 className="mt-2 text-2xl font-semibold tracking-tight md:text-3xl">
            Sanctions Screening
          </h1>
          <p className="mt-1 max-w-2xl text-[13.5px] text-white/60">
            Fuzzy-match names against the bundled OFAC/UN/EU/UK-style watchlist.
            Every score is a transparent blend of token-set, char-n-gram, and
            substring containment — click a match to see the components.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button className="btn" onClick={() => setNamesText(SAMPLE_NAMES.join("\n"))}>
            Reset sample
          </button>
          <button className="btn-primary" onClick={onScreen} disabled={loading || !names.length}>
            {loading ? "Screening…" : `Screen ${names.length}`}
          </button>
        </div>
      </header>

      {/* Stats strip from watchlist meta */}
      {meta && (
        <section className="grid grid-cols-2 gap-3 md:grid-cols-5">
          <Stat label="Entries" value={meta.size} />
          <Stat
            label="Lists"
            value={Object.keys(meta.by_list).length}
            sub={Object.entries(meta.by_list)
              .map(([k, v]) => `${k} ${v}`)
              .join(" · ")}
          />
          <Stat
            label="Jurisdictions"
            value={Object.keys(meta.by_jurisdiction).length}
          />
          <Stat
            label="Entities · Individuals"
            value={`${meta.by_type.entity ?? 0} · ${meta.by_type.individual ?? 0}`}
            mono
          />
          <Stat label="Issued" value={meta.issued ?? "—"} mono />
        </section>
      )}

      <section className="grid gap-5 lg:grid-cols-[1.1fr_1fr]">
        {/* Input */}
        <div className="glass p-4">
          <div className="mb-2 flex items-center justify-between">
            <span className="label !mb-0">Names · one per line</span>
            <span className="text-[11px] text-white/45">{names.length} queries</span>
          </div>
          <div className="dropzone rounded-xl">
            <textarea
              value={namesText}
              onChange={(e) => setNamesText(e.target.value)}
              spellCheck={false}
              className="scroll-thin h-56 w-full resize-none bg-transparent p-3 font-mono text-[12.5px] text-white/85 outline-none"
            />
          </div>

          <div className="mt-3 grid grid-cols-2 gap-3">
            <label className="block">
              <span className="label">Jurisdiction prior (optional)</span>
              <select
                value={juris}
                onChange={(e) => setJuris(e.target.value)}
                className="input"
              >
                {JURISDICTIONS.map((j) => (
                  <option key={j || "any"} value={j}>
                    {j || "any"}
                  </option>
                ))}
              </select>
            </label>
            <label className="block">
              <span className="label">
                Min similarity ·{" "}
                <span className="font-mono text-white/70">
                  {(threshold * 100).toFixed(0)}%
                </span>
              </span>
              <input
                type="range"
                min={0.3}
                max={0.95}
                step={0.05}
                value={threshold}
                onChange={(e) => setThreshold(Number(e.target.value))}
                className="w-full accent-teal-400"
              />
            </label>
          </div>

          {err && <p className="mt-3 text-[12px] text-rose-300">{err}</p>}
        </div>

        {/* Run summary */}
        <div className="glass p-5">
          <div className="label">Run summary</div>
          {!resp && (
            <div className="grid h-56 place-items-center text-center text-white/45">
              <div>
                <div className="text-3xl">⌖</div>
                <div className="mt-2 text-[13px]">Screen names to populate.</div>
              </div>
            </div>
          )}
          {resp && (
            <div className="grid grid-cols-3 gap-3">
              <Tile label="Queried" value={resp.queried} />
              <Tile label="Matched" value={resp.matched} warn={resp.matched > 0} />
              <Tile
                label="Hit-rate"
                value={
                  resp.queried
                    ? `${Math.round((resp.matched / resp.queried) * 100)}%`
                    : "—"
                }
                mono
              />
              {(["exact", "strong", "medium", "weak"] as const).map((g) => (
                <Tile
                  key={g}
                  label={g}
                  value={resp.by_grade[g] ?? 0}
                  warn={(resp.by_grade[g] ?? 0) > 0}
                />
              ))}
            </div>
          )}
        </div>
      </section>

      {/* Results grid */}
      {resp && (
        <section className="grid gap-4 md:grid-cols-2">
          {resp.results.map((r) => (
            <ResultCard key={r.query} result={r} />
          ))}
        </section>
      )}

      {/* Watchlist browser */}
      <section className="glass-strong p-5 md:p-6">
        <div className="flex flex-wrap items-baseline justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold">Watchlist · browse</h2>
            <p className="mt-1 text-[12.5px] text-white/55">
              The bundled, illustrative dataset. Production deployments plug in
              OFAC SDN, UN-1267, EU-CFSP, UK-OFSI, and FIU-IND feeds via the
              same loader.
            </p>
          </div>
          <input
            type="search"
            value={browseQ}
            onChange={(e) => setBrowseQ(e.target.value)}
            placeholder="Filter — name, alias, list, jurisdiction…"
            className="input w-full max-w-xs"
          />
        </div>

        <div className="mt-4 overflow-hidden rounded-xl border border-white/10">
          <div className="grid grid-cols-[1.6fr_1fr_0.7fr_0.6fr_0.6fr] gap-2 border-b border-white/10 bg-white/[0.04] px-3 py-2 text-[10.5px] uppercase tracking-wider text-white/45">
            <span>Entity / individual</span>
            <span>Aliases</span>
            <span>List</span>
            <span>Juris.</span>
            <span>Added</span>
          </div>
          <div className="scroll-thin max-h-[360px] divide-y divide-white/[0.06] overflow-y-auto">
            {listLoading && (
              <div className="px-3 py-4 text-[12.5px] text-white/45">
                Loading watchlist…
              </div>
            )}
            {!listLoading && filteredEntries.length === 0 && (
              <div className="px-3 py-4 text-[12.5px] text-white/45">
                No entries match “{browseQ}”.
              </div>
            )}
            {filteredEntries.map((e) => (
              <div
                key={e.id}
                className="grid grid-cols-[1.6fr_1fr_0.7fr_0.6fr_0.6fr] items-center gap-2 px-3 py-2.5 text-[12.5px] hover:bg-white/[0.03]"
              >
                <div>
                  <div className="font-medium tracking-tight text-white/90">
                    {e.name}
                  </div>
                  <div className="mt-0.5 font-mono text-[10.5px] text-white/40">
                    {e.id} · {e.type}
                  </div>
                </div>
                <div className="text-[12px] text-white/65">
                  {e.aliases.slice(0, 2).join(" · ")}
                  {e.aliases.length > 2 ? ` +${e.aliases.length - 2}` : ""}
                </div>
                <div className="font-mono text-[11px] text-white/65">{e.list}</div>
                <div className="font-mono text-[11px] text-white/65">{e.jurisdiction}</div>
                <div className="font-mono text-[11px] text-white/45">{e.added}</div>
              </div>
            ))}
          </div>
        </div>
        <div className="mt-3 text-[11px] text-white/45">
          Showing {filteredEntries.length} of {entries.length} loaded entries.
        </div>
      </section>
    </div>
  );
}

function ResultCard({ result }: { result: ScreenResult }) {
  const best = result.best;
  return (
    <div className="glass overflow-hidden p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="label">Query</div>
          <div className="truncate text-[14.5px] font-medium text-white/90">
            {result.query}
          </div>
          {result.normalized && (
            <div className="mt-0.5 font-mono text-[10.5px] text-white/35">
              {result.normalized}
            </div>
          )}
        </div>
        {best && (
          <SimilarityRing similarity={best.similarity} grade={best.grade} />
        )}
        {!best && <SimilarityRing similarity={0} grade="none" />}
      </div>

      {!best && (
        <div className="mt-3 rounded-lg border border-white/8 bg-white/[0.02] px-3 py-2 text-[12.5px] text-white/55">
          No watchlist match ≥ {(result.threshold * 100).toFixed(0)}%.
        </div>
      )}

      {best && (
        <>
          <div className="mt-4">
            <div className={`inline-flex items-center gap-2 rounded-lg border px-2.5 py-1 text-[11px] uppercase tracking-wider ${GRADE_TINT[best.grade]}`}>
              <span>{best.grade}</span>
              <span className="text-white/45">·</span>
              <span className="font-mono">{best.list}</span>
              <span className="text-white/45">·</span>
              <span className="font-mono">{best.jurisdiction}</span>
            </div>
            <div className="mt-2 text-[14px] font-semibold tracking-tight">
              {best.name}
            </div>
            <div className="mt-0.5 text-[12px] text-white/55">
              matched on “{best.matched_alias}”
            </div>
            <div className="mt-2 text-[12px] leading-relaxed text-white/65">
              {best.reason}
            </div>
            <div className="mt-2 font-mono text-[10.5px] text-white/40">
              {best.entity_id} · added {best.added}
            </div>
          </div>

          <div className="mt-3 grid grid-cols-3 gap-2 text-[11px]">
            <Component label="token-set" value={best.components.token_set} />
            <Component label="char-3gram" value={best.components.ngram} />
            <Component label="contain" value={best.components.contain} />
            {typeof best.components.jurisdiction_bonus === "number" && (
              <Component
                label="juris bonus"
                value={best.components.jurisdiction_bonus}
                accent
              />
            )}
            <Component label="blended" value={best.components.blended} accent />
          </div>

          {result.matches.length > 1 && (
            <div className="mt-3 border-t border-white/8 pt-3">
              <div className="label">Other candidates</div>
              <div className="space-y-1.5">
                {result.matches.slice(1).map((m) => (
                  <div
                    key={m.entity_id}
                    className="flex items-center justify-between gap-3 rounded-md border border-white/5 bg-white/[0.02] px-2.5 py-1.5 text-[11.5px]"
                  >
                    <span className="truncate text-white/75">{m.name}</span>
                    <span className="font-mono text-white/55">
                      {(m.similarity * 100).toFixed(0)}% · {m.grade}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function Stat({
  label,
  value,
  mono = false,
  sub,
}: {
  label: string;
  value: number | string;
  mono?: boolean;
  sub?: string;
}) {
  return (
    <div className="glass px-4 py-3">
      <div className="text-[11px] uppercase tracking-wider text-white/40">
        {label}
      </div>
      <div className={`mt-1 ${mono ? "font-mono text-[13px]" : "text-2xl font-semibold tracking-tight"}`}>
        {value}
      </div>
      {sub && (
        <div className="mt-1 truncate font-mono text-[10.5px] text-white/35">
          {sub}
        </div>
      )}
    </div>
  );
}

function Tile({
  label,
  value,
  warn = false,
  mono = false,
}: {
  label: string;
  value: number | string;
  warn?: boolean;
  mono?: boolean;
}) {
  return (
    <div className="rounded-xl border border-white/10 bg-black/25 p-3">
      <div className="text-[10.5px] uppercase tracking-wider text-white/45">
        {label}
      </div>
      <div
        className={`mt-1 ${mono ? "font-mono text-[12px]" : "text-xl font-semibold"} ${
          warn ? "text-amber-300" : "text-white"
        }`}
      >
        {value}
      </div>
    </div>
  );
}

function Component({
  label,
  value,
  accent = false,
}: {
  label: string;
  value: number;
  accent?: boolean;
}) {
  const pct = Math.max(0, Math.min(1, value));
  return (
    <div
      className={`rounded-md border px-2 py-1.5 ${
        accent ? "border-teal-400/35 bg-teal-500/[0.06]" : "border-white/8 bg-white/[0.02]"
      }`}
    >
      <div className="text-[10px] uppercase tracking-wider text-white/45">
        {label}
      </div>
      <div className="mt-0.5 flex items-baseline gap-1.5">
        <span
          className={`font-mono tabular-nums ${
            accent ? "text-teal-300" : "text-white/80"
          }`}
        >
          {value.toFixed(2)}
        </span>
        <div className="ml-auto h-1 w-10 overflow-hidden rounded-full bg-white/[0.07]">
          <div
            className="h-full rounded-full"
            style={{
              width: `${pct * 100}%`,
              background: accent
                ? "linear-gradient(90deg, #2DE1C2, #6E5BFF)"
                : "rgba(255,255,255,0.45)",
            }}
          />
        </div>
      </div>
    </div>
  );
}
