"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import MediaScoreRing, { gradeColor } from "../../components/MediaScoreRing";
import {
  MediaArticleSummary,
  MediaCategory,
  MediaCorpus,
  MediaGrade,
  MediaHit,
  MediaScreenResult,
  getMediaRules,
  listMediaArticles,
  screenMedia,
} from "../../lib/api";

const SAMPLE_NAMES = [
  "Trident Exports",
  "Aurelia Shell Limited",
  "Apex Trust Singapore",
  "Crescent Maritime",
  "Aliekseii Volkov-Baranov",
  "Devraj Industries",
  "Eastvale Capital",
  "Petrov Holdings",
];

const HALF_LIFE_PRESETS: { label: string; days: number }[] = [
  { label: "90d", days: 90 },
  { label: "180d", days: 180 },
  { label: "1y", days: 365 },
  { label: "2y", days: 730 },
];

type Tab = "screen" | "browse";

function fmtAge(days: number | null): string {
  if (days === null) return "";
  if (days < 30) return `${Math.round(days)}d ago`;
  if (days < 365) return `${Math.round(days / 30)}mo ago`;
  return `${(days / 365).toFixed(1)}y ago`;
}

function categoryByKey(corpus: MediaCorpus | null, key: string): MediaCategory | null {
  if (!corpus) return null;
  return corpus.categories.find((c) => c.key === key) || null;
}

function recencyLabel(key: string): string {
  switch (key) {
    case "last_30d": return "≤ 30d";
    case "last_90d": return "≤ 90d";
    case "last_year": return "≤ 1y";
    default: return "older";
  }
}

export default function MediaPage() {
  const [namesText, setNamesText] = useState(SAMPLE_NAMES.join("\n"));
  const [floor, setFloor] = useState(0.55);
  const [halfLife, setHalfLife] = useState(365);
  const [results, setResults] = useState<MediaScreenResult[] | null>(null);
  const [resultStats, setResultStats] = useState<{
    matched: number;
    by_grade: Record<string, number>;
  } | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("screen");
  const [activeName, setActiveName] = useState<string | null>(null);

  const [corpus, setCorpus] = useState<MediaCorpus | null>(null);
  const [articles, setArticles] = useState<MediaArticleSummary[]>([]);
  const [filterCat, setFilterCat] = useState<string | null>(null);
  const [filterTier, setFilterTier] = useState<number | null>(null);
  const [filterQ, setFilterQ] = useState("");
  const [articlesLoading, setArticlesLoading] = useState(true);

  useEffect(() => {
    let cancel = false;
    (async () => {
      try {
        const data = await getMediaRules();
        if (!cancel) setCorpus(data.corpus);
      } catch (e: any) {
        if (!cancel) setErr(e.message || "failed to load corpus metadata");
      }
    })();
    return () => {
      cancel = true;
    };
  }, []);

  const loadArticles = useCallback(async () => {
    setArticlesLoading(true);
    try {
      const data = await listMediaArticles({
        category: filterCat || undefined,
        tier: filterTier || undefined,
        q: filterQ || undefined,
        limit: 100,
      });
      setArticles(data.articles);
    } catch (e: any) {
      setErr(e.message || "failed to load articles");
    } finally {
      setArticlesLoading(false);
    }
  }, [filterCat, filterTier, filterQ]);

  useEffect(() => {
    const t = setTimeout(() => {
      loadArticles();
    }, 180);
    return () => clearTimeout(t);
  }, [loadArticles]);

  const names = useMemo(
    () => namesText.split(/\r?\n/).map((n) => n.trim()).filter(Boolean),
    [namesText],
  );

  const onScreen = useCallback(async () => {
    setErr(null);
    setLoading(true);
    setResults(null);
    setResultStats(null);
    try {
      const data = await screenMedia(names, {
        similarity_floor: floor,
        half_life_days: halfLife,
      });
      setResults(data.results);
      setResultStats({ matched: data.matched, by_grade: data.by_grade });
      if (data.results.length) setActiveName(data.results[0].query);
    } catch (e: any) {
      setErr(e.message || "screen failed");
    } finally {
      setLoading(false);
    }
  }, [names, floor, halfLife]);

  useEffect(() => {
    onScreen();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const active = results?.find((r) => r.query === activeName) || results?.[0] || null;

  const heroStats = useMemo(() => {
    if (!corpus) return null;
    const tier1 = Number(corpus.by_tier["1"] || 0);
    const total = corpus.size;
    return {
      total,
      tier1,
      tierPct: total ? Math.round((tier1 / total) * 100) : 0,
      categories: corpus.categories.length,
      years: Object.keys(corpus.by_year).length,
    };
  }, [corpus]);

  const screenStats = useMemo(() => {
    if (!results || !resultStats) return null;
    const counts = {
      severe: resultStats.by_grade["severe"] || 0,
      material: resultStats.by_grade["material"] || 0,
      elevated: resultStats.by_grade["elevated"] || 0,
      clear: resultStats.by_grade["clear"] || 0,
    };
    return {
      ...counts,
      matched: resultStats.matched,
      total: results.length,
    };
  }, [results, resultStats]);

  return (
    <div className="space-y-6">
      {/* Hero */}
      <section className="glass-strong ws-media-hero-grad relative overflow-hidden p-6 md:p-8">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div className="max-w-2xl">
            <div className="flex items-center gap-2">
              <span className="pill pill-ok">round 9 · day 45</span>
              <span className="pill">OSINT · tier-2 EDD</span>
            </div>
            <h1 className="mt-3 text-3xl font-semibold tracking-tight md:text-4xl">
              <span className="grad-text">Adverse Media</span> OSINT
            </h1>
            <p className="mt-3 text-[14px] leading-relaxed text-white/70">
              Sanctions answers a binary question against a closed list. Adverse media
              asks the open-world question — <span className="text-white/85">what is the world saying about this entity?</span>
              {" "}Composite ramps with category severity × source tier × recency × name match. Every score ships with the exact articles that fired and a per-component breakdown.
            </p>
          </div>
          {heroStats && (
            <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
              <HeroStat label="corpus" value={String(heroStats.total)} />
              <HeroStat label="categories" value={String(heroStats.categories)} />
              <HeroStat label="tier-1 share" value={`${heroStats.tierPct}%`} />
              <HeroStat label="half-life" value={`${halfLife}d`} />
            </div>
          )}
        </div>
      </section>

      {err && (
        <div className="glass border border-rose-400/30 bg-rose-500/10 px-4 py-2.5 text-[13px] text-rose-200">
          {err}
        </div>
      )}

      {/* Tabs */}
      <div className="flex items-center gap-2">
        <button
          className={`ws-media-tab ${tab === "screen" ? "ws-media-tab-active" : ""}`}
          onClick={() => setTab("screen")}
        >
          Screen entities
        </button>
        <button
          className={`ws-media-tab ${tab === "browse" ? "ws-media-tab-active" : ""}`}
          onClick={() => setTab("browse")}
        >
          Browse corpus
        </button>
        {tab === "screen" && screenStats && (
          <div className="ml-auto flex items-center gap-2 text-[11px] text-white/55">
            <span className="ws-media-pill ws-media-grade-severe">{screenStats.severe} severe</span>
            <span className="ws-media-pill ws-media-grade-material">{screenStats.material} material</span>
            <span className="ws-media-pill ws-media-grade-elevated">{screenStats.elevated} elevated</span>
            <span className="ws-media-pill ws-media-grade-clear">{screenStats.clear} clear</span>
          </div>
        )}
      </div>

      {tab === "screen" && (
        <section className="grid gap-6 lg:grid-cols-[360px_1fr]">
          {/* Left rail — screening controls */}
          <aside className="space-y-4">
            <div className="glass p-4">
              <label className="label">Entity names</label>
              <textarea
                className="input min-h-[200px] font-mono text-[12px]"
                value={namesText}
                onChange={(e) => setNamesText(e.target.value)}
                placeholder="One name per line"
                spellCheck={false}
              />
              <div className="mt-2 flex items-center justify-between text-[11px] text-white/45">
                <span>{names.length} name(s)</span>
                <button
                  className="text-teal-300/85 hover:text-teal-300"
                  onClick={() => setNamesText(SAMPLE_NAMES.join("\n"))}
                >
                  reset sample
                </button>
              </div>
            </div>

            <div className="glass p-4">
              <label className="label flex items-center justify-between">
                <span>Similarity floor</span>
                <span className="font-mono text-[12px] text-white/85">{floor.toFixed(2)}</span>
              </label>
              <input
                type="range"
                min={0.4}
                max={0.85}
                step={0.01}
                value={floor}
                onChange={(e) => setFloor(parseFloat(e.target.value))}
                className="w-full accent-teal-400"
              />
              <div className="mt-1 flex justify-between text-[10px] text-white/35">
                <span>permissive 0.40</span>
                <span>strict 0.85</span>
              </div>
            </div>

            <div className="glass p-4">
              <label className="label flex items-center justify-between">
                <span>Recency half-life</span>
                <span className="font-mono text-[12px] text-white/85">{halfLife}d</span>
              </label>
              <input
                type="range"
                min={30}
                max={1095}
                step={15}
                value={halfLife}
                onChange={(e) => setHalfLife(parseInt(e.target.value))}
                className="w-full accent-violet-400"
              />
              <div className="mt-2 flex flex-wrap gap-2">
                {HALF_LIFE_PRESETS.map((p) => (
                  <button
                    key={p.days}
                    className={`ws-media-filter-chip ${halfLife === p.days ? "ws-media-filter-chip-active" : ""}`}
                    onClick={() => setHalfLife(p.days)}
                  >
                    {p.label}
                  </button>
                ))}
              </div>
              <p className="mt-3 text-[10.5px] leading-relaxed text-white/40">
                Per-article recency = 0.5 ^ (age_days / half_life). Lower half-life punishes old coverage more sharply.
              </p>
            </div>

            <button
              className="btn-primary w-full"
              onClick={onScreen}
              disabled={loading || names.length === 0}
            >
              {loading ? "Screening…" : `Screen ${names.length} name${names.length === 1 ? "" : "s"}`}
            </button>
          </aside>

          {/* Results pane */}
          <div className="grid gap-5 lg:grid-cols-[1.05fr_1.45fr]">
            <div className="space-y-3">
              {!results && !loading && (
                <div className="ws-media-empty">
                  Enter party names and hit Screen.
                </div>
              )}
              {loading && (
                <div className="ws-media-empty">Scoring against {corpus?.size ?? "–"} articles…</div>
              )}
              {results &&
                results.map((r) => {
                  const isActive = (active?.query || "") === r.query;
                  const color = gradeColor(r.grade);
                  return (
                    <button
                      key={r.query}
                      type="button"
                      onClick={() => setActiveName(r.query)}
                      className="ws-media-card ws-media-hairline block w-full p-4 text-left"
                      style={
                        {
                          ["--media-accent" as any]: color,
                          outline: isActive ? `1px solid ${color}` : undefined,
                          outlineOffset: isActive ? "-1px" : undefined,
                        } as React.CSSProperties
                      }
                    >
                      <div className="flex items-center gap-3">
                        <MediaScoreRing
                          composite={r.composite}
                          grade={r.grade}
                          size={64}
                          thin
                        />
                        <div className="min-w-0 flex-1">
                          <div className="truncate text-[14.5px] font-semibold tracking-tight">
                            {r.query}
                          </div>
                          <div className="mt-0.5 text-[11.5px] text-white/55">
                            {r.hit_count} hit{r.hit_count === 1 ? "" : "s"}
                            {r.headline_hit && (
                              <span className="text-white/40">
                                {" · "}
                                {r.headline_hit.source} · {fmtAge(r.headline_hit.age_days)}
                              </span>
                            )}
                          </div>
                          {r.categories.length > 0 && (
                            <div className="mt-2 flex flex-wrap gap-1.5">
                              {r.categories.slice(0, 3).map((c) => (
                                <span
                                  key={c.category}
                                  className="ws-media-chip"
                                  style={{ ["--cat-accent" as any]: c.accent }}
                                >
                                  {c.label}
                                </span>
                              ))}
                            </div>
                          )}
                        </div>
                      </div>
                    </button>
                  );
                })}
            </div>

            {/* Detail */}
            <div>
              {active ? (
                <ResultDetail r={active} corpus={corpus} />
              ) : (
                <div className="ws-media-empty">No name selected.</div>
              )}
            </div>
          </div>
        </section>
      )}

      {tab === "browse" && (
        <section className="space-y-4">
          <div className="glass flex flex-wrap items-center gap-3 p-3">
            <input
              className="input max-w-md"
              placeholder="Search headlines, snippets, mentions…"
              value={filterQ}
              onChange={(e) => setFilterQ(e.target.value)}
            />
            <div className="flex flex-wrap gap-1.5">
              <button
                className={`ws-media-filter-chip ${filterCat === null ? "ws-media-filter-chip-active" : ""}`}
                onClick={() => setFilterCat(null)}
              >
                all categories
              </button>
              {corpus?.categories.map((c) => (
                <button
                  key={c.key}
                  className={`ws-media-filter-chip ${filterCat === c.key ? "ws-media-filter-chip-active" : ""}`}
                  style={{ ["--cat-accent" as any]: c.accent }}
                  onClick={() => setFilterCat(filterCat === c.key ? null : c.key)}
                >
                  {c.label} · {corpus.by_category[c.key] || 0}
                </button>
              ))}
            </div>
            <div className="flex gap-1.5">
              {[1, 2, 3].map((t) => (
                <button
                  key={t}
                  className={`ws-media-filter-chip ${filterTier === t ? "ws-media-filter-chip-active" : ""}`}
                  onClick={() => setFilterTier(filterTier === t ? null : t)}
                >
                  tier {t}
                </button>
              ))}
            </div>
            <div className="ml-auto text-[11.5px] text-white/45">
              {articlesLoading ? "loading…" : `${articles.length} article${articles.length === 1 ? "" : "s"}`}
            </div>
          </div>

          {articles.length === 0 && !articlesLoading ? (
            <div className="ws-media-empty">No articles match the current filters.</div>
          ) : (
            <div className="grid gap-3 md:grid-cols-2">
              {articles.map((a) => {
                const cat = categoryByKey(corpus, a.category);
                const accent = cat?.accent || "#94a3b8";
                return (
                  <article
                    key={a.id}
                    className="ws-media-article"
                    style={{ ["--cat-accent" as any]: accent } as React.CSSProperties}
                  >
                    <header className="flex items-start gap-2">
                      <span className="ws-media-article-dot mt-1.5" />
                      <div className="min-w-0 flex-1">
                        <h3 className="text-[14px] font-semibold leading-snug">
                          {a.headline}
                        </h3>
                        <div className="mt-1 flex flex-wrap items-center gap-2 text-[11px] text-white/45">
                          <span className={`ws-media-tier-badge ws-media-tier-${a.source_tier}`}>
                            T{a.source_tier}
                          </span>
                          <span>{a.source}</span>
                          <span>·</span>
                          <span>{a.published}</span>
                          <span
                            className="ws-media-chip"
                            style={{ ["--cat-accent" as any]: accent }}
                          >
                            {cat?.label || a.category}
                          </span>
                        </div>
                      </div>
                    </header>
                    <p className="text-[12.5px] leading-relaxed text-white/65">{a.snippet}</p>
                    {a.entities_mentioned.length > 0 && (
                      <div className="flex flex-wrap gap-1">
                        {a.entities_mentioned.slice(0, 4).map((m) => (
                          <span
                            key={m}
                            className="rounded-md border border-white/10 bg-white/[0.03] px-1.5 py-0.5 text-[10.5px] text-white/55"
                          >
                            {m}
                          </span>
                        ))}
                      </div>
                    )}
                  </article>
                );
              })}
            </div>
          )}
        </section>
      )}
    </div>
  );
}

function HeroStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-white/10 bg-black/20 px-3 py-2">
      <div className="text-[10px] uppercase tracking-wider text-white/40">{label}</div>
      <div className="mt-0.5 text-xl font-semibold tracking-tight grad-text">{value}</div>
    </div>
  );
}

function ResultDetail({
  r,
  corpus,
}: {
  r: MediaScreenResult;
  corpus: MediaCorpus | null;
}) {
  const accent = gradeColor(r.grade);
  const maxStrength = Math.max(
    1,
    ...r.categories.map((c) => c.strength),
    ...Object.values(r.recency).map((b) => b.strength),
  );
  const totalArticles = corpus?.size ?? 0;
  const matchedShare = totalArticles
    ? ((r.hit_count / totalArticles) * 100).toFixed(1)
    : "0.0";

  if (r.hit_count === 0) {
    return (
      <div
        className="ws-media-card p-6 text-center"
        style={{ ["--media-accent" as any]: accent } as React.CSSProperties}
      >
        <MediaScoreRing composite={0} grade="clear" size={96} />
        <div className="mt-4 text-[15px] font-semibold">No adverse hits</div>
        <p className="mt-2 text-[12.5px] text-white/55">
          {r.query} did not match any article above the {r.similarity_floor.toFixed(2)} similarity floor.
        </p>
      </div>
    );
  }

  return (
    <div
      className="ws-media-card ws-media-hairline space-y-4 p-5"
      style={{ ["--media-accent" as any]: accent } as React.CSSProperties}
    >
      {/* Headline */}
      <div className="flex items-start gap-4">
        <MediaScoreRing composite={r.composite} grade={r.grade} size={92} />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <h2 className="truncate text-[18px] font-semibold tracking-tight">{r.query}</h2>
            <span className={`ws-media-pill ws-media-grade-${r.grade}`}>{r.grade}</span>
          </div>
          <p className="mt-1.5 text-[12.5px] leading-relaxed text-white/60">
            {r.hit_count} adverse-media hit{r.hit_count === 1 ? "" : "s"} ({matchedShare}% of corpus) ·
            raw strength {r.raw_strength.toFixed(2)} · saturating composite{" "}
            <span className="font-mono" style={{ color: accent }}>
              {r.composite.toFixed(1)}/100
            </span>
          </p>
          <p className="mt-1 text-[11px] text-white/40">
            half-life {r.half_life_days}d · similarity floor {r.similarity_floor.toFixed(2)} · top-{r.top_k} feeds the composite
          </p>
        </div>
      </div>

      {/* Category rollup */}
      <div>
        <div className="mb-2 text-[10.5px] uppercase tracking-wider text-white/40">
          coverage categories
        </div>
        <div className="ws-media-catbar">
          {r.categories.slice(0, 6).map((c) => {
            const pct = (c.strength / maxStrength) * 100;
            return (
              <div key={c.category} className="ws-media-catbar-row">
                <span className="truncate text-white/75">{c.label}</span>
                <div className="ws-media-catbar-track">
                  <div
                    className="ws-media-catbar-fill"
                    style={{ width: `${pct}%`, ["--cat-accent" as any]: c.accent } as React.CSSProperties}
                  />
                </div>
                <span className="text-right font-mono text-[10.5px] text-white/55">
                  {c.count}
                </span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Recency */}
      <div>
        <div className="mb-2 text-[10.5px] uppercase tracking-wider text-white/40">
          recency profile
        </div>
        <div className="ws-media-recency">
          {(["last_30d", "last_90d", "last_year", "older"] as const).map((k) => {
            const bucket = r.recency[k];
            const active = bucket.count > 0;
            const widthPct = (bucket.strength / maxStrength) * 100;
            return (
              <div
                key={k}
                className={`ws-media-recency-cell ${active ? "ws-media-recency-cell-active" : ""}`}
              >
                <div className="text-[10px] uppercase tracking-wider text-white/40">
                  {recencyLabel(k)}
                </div>
                <div className="mt-1 text-[18px] font-semibold tracking-tight">
                  {bucket.count}
                </div>
                <div className="text-[10.5px] text-white/45">
                  Σ {bucket.strength.toFixed(2)}
                </div>
                {active && (
                  <div
                    className="ws-media-recency-bar"
                    style={{ width: `${Math.max(8, widthPct)}%` }}
                  />
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Top hits */}
      <div>
        <div className="mb-2 text-[10.5px] uppercase tracking-wider text-white/40">
          top hits — drives the composite
        </div>
        <div className="space-y-2.5">
          {r.top_hits.slice(0, 8).map((h) => (
            <HitCard key={h.article_id} hit={h} maxStrength={r.top_hits[0]?.hit_strength || 1} />
          ))}
        </div>
      </div>
    </div>
  );
}

function HitCard({ hit, maxStrength }: { hit: MediaHit; maxStrength: number }) {
  const pct = Math.max(2, (hit.hit_strength / maxStrength) * 100);
  return (
    <article
      className="ws-media-article"
      style={{ ["--cat-accent" as any]: hit.category_accent } as React.CSSProperties}
    >
      <header className="flex items-start gap-2">
        <span className="ws-media-article-dot mt-1.5" />
        <div className="min-w-0 flex-1">
          <h3 className="text-[13.5px] font-semibold leading-snug">{hit.headline}</h3>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-[11px] text-white/45">
            <span className={`ws-media-tier-badge ws-media-tier-${hit.source_tier}`}>T{hit.source_tier}</span>
            <span>{hit.source}</span>
            <span>·</span>
            <span>{hit.published}</span>
            <span>·</span>
            <span>{fmtAge(hit.age_days)}</span>
            <span className="ws-media-chip" style={{ ["--cat-accent" as any]: hit.category_accent }}>
              {hit.category.replaceAll("_", " ")}
            </span>
          </div>
        </div>
        <div className="text-right">
          <div className="font-mono text-[13px] text-white/85">{hit.hit_strength.toFixed(2)}</div>
          <div className="text-[10px] uppercase tracking-wider text-white/40">strength</div>
        </div>
      </header>
      <p className="text-[12px] leading-relaxed text-white/60">{hit.snippet}</p>
      <div className="grid gap-1">
        <div className="ws-media-strength-track">
          <div className="ws-media-strength-fill" style={{ width: `${pct}%` }} />
        </div>
        <div className="grid grid-cols-4 gap-2 text-[10.5px] text-white/45">
          <div title="Fuzzy name match">
            sim <span className="text-white/75">{(hit.similarity * 100).toFixed(0)}%</span>
          </div>
          <div title="Category severity">
            sev <span className="text-white/75">{(hit.category_severity * 100).toFixed(0)}%</span>
          </div>
          <div title="Source tier weight">
            src <span className="text-white/75">{(hit.source_tier_weight * 100).toFixed(0)}%</span>
          </div>
          <div title="Recency decay">
            rec <span className="text-white/75">{(hit.recency_decay * 100).toFixed(0)}%</span>
          </div>
        </div>
        <div className="text-[10.5px] text-white/40">
          matched “<span className="text-white/65">{hit.matched_mention}</span>”
        </div>
      </div>
    </article>
  );
}
