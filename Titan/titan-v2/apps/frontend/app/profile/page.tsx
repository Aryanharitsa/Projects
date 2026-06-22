"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import FactorWheel from "../../components/FactorWheel";
import HistoryStrip from "../../components/HistoryStrip";
import ProfileRing, { bucketColor } from "../../components/ProfileRing";
import RefreshTimeline from "../../components/RefreshTimeline";
import {
  Profile,
  ProfileBucket,
  ProfileFactor,
  ProfileHistoryEntry,
  ProfileModifier,
  ProfilePortfolio,
  ProfilePortfolioStats,
  ProfileRefreshLabel,
  ProfileRules,
  clearProfileOverride,
  getProfile,
  getProfileRules,
  listProfiles,
  seedProfiles,
  setProfileOverride,
} from "../../lib/api";

type Tab = "customer" | "portfolio";
const BUCKETS: ProfileBucket[] = ["critical", "high", "medium", "low"];
const REFRESH_LABELS: ProfileRefreshLabel[] = ["overdue", "due_soon", "current", "unscheduled"];

function fmtDt(iso: string | null | undefined) {
  if (!iso) return "—";
  try {
    return new Date(iso).toISOString().slice(0, 10);
  } catch {
    return "—";
  }
}

function bucketAccent(b: ProfileBucket) {
  return {
    low: "rgba(34,211,168,0.18)",
    medium: "rgba(251,191,36,0.20)",
    high: "rgba(251,146,60,0.22)",
    critical: "rgba(239,68,68,0.25)",
  }[b];
}

export default function ProfilePage() {
  const [tab, setTab] = useState<Tab>("customer");
  const [rules, setRules] = useState<ProfileRules | null>(null);
  const [portfolio, setPortfolio] = useState<ProfilePortfolio | null>(null);
  const [stats, setStats] = useState<ProfilePortfolioStats | null>(null);
  const [active, setActive] = useState<Profile | null>(null);
  const [search, setSearch] = useState("");
  const [bucketFilter, setBucketFilter] = useState<ProfileBucket | null>(null);
  const [refreshFilter, setRefreshFilter] = useState<ProfileRefreshLabel | null>(null);
  const [loading, setLoading] = useState(true);
  const [seeding, setSeeding] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const refreshPortfolio = useCallback(async () => {
    setErr(null);
    try {
      const data = await listProfiles({
        bucket: bucketFilter || undefined,
        refresh_label: refreshFilter || undefined,
        q: search.trim() || undefined,
        limit: 200,
      });
      setPortfolio(data);
      setStats(data.stats);
      return data;
    } catch (e: any) {
      setErr(e.message || "failed to load portfolio");
      return null;
    }
  }, [bucketFilter, refreshFilter, search]);

  useEffect(() => {
    let cancel = false;
    (async () => {
      setLoading(true);
      try {
        const [r] = await Promise.all([getProfileRules()]);
        if (cancel) return;
        setRules(r);
        const data = await refreshPortfolio();
        if (cancel) return;
        if (data && data.profiles.length) {
          // Land on the highest-risk profile by default.
          const sorted = [...data.profiles].sort((a, b) => b.composite - a.composite);
          const full = await getProfile(sorted[0].customer.customer_id);
          if (!cancel) setActive(full.profile);
        } else if (data && data.total === 0) {
          // Empty store → auto-seed the bundled book on first load.
          await seedProfiles(false);
          const reloaded = await refreshPortfolio();
          if (reloaded && reloaded.profiles.length) {
            const sorted = [...reloaded.profiles].sort((a, b) => b.composite - a.composite);
            const full = await getProfile(sorted[0].customer.customer_id);
            if (!cancel) setActive(full.profile);
          }
        }
      } catch (e: any) {
        if (!cancel) setErr(e.message || "failed to initialise");
      } finally {
        if (!cancel) setLoading(false);
      }
    })();
    return () => {
      cancel = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    refreshPortfolio();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bucketFilter, refreshFilter]);

  // Debounced search
  useEffect(() => {
    const t = setTimeout(() => {
      refreshPortfolio();
    }, 220);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search]);

  const selectCustomer = useCallback(async (id: string) => {
    setErr(null);
    try {
      const r = await getProfile(id);
      setActive(r.profile);
      setTab("customer");
    } catch (e: any) {
      setErr(e.message || "failed to load customer");
    }
  }, []);

  const reseed = useCallback(async () => {
    setSeeding(true);
    setErr(null);
    try {
      const r = await seedProfiles(true);
      const reloaded = await refreshPortfolio();
      if (reloaded?.profiles.length) {
        const top = reloaded.profiles[0];
        const full = await getProfile(top.customer.customer_id);
        setActive(full.profile);
      }
    } catch (e: any) {
      setErr(e.message || "reseed failed");
    } finally {
      setSeeding(false);
    }
  }, [refreshPortfolio]);

  return (
    <div className="space-y-6">
      <HeroBanner stats={stats} loading={loading} onReseed={reseed} seeding={seeding} />

      {err && (
        <div className="glass border border-rose-400/30 bg-rose-500/10 px-4 py-2.5 text-[13px] text-rose-200">
          {err}
        </div>
      )}

      <TabBar tab={tab} setTab={setTab} />

      {tab === "customer" ? (
        <div className="grid gap-6 lg:grid-cols-[300px_1fr]">
          <PortfolioRail
            portfolio={portfolio}
            active={active}
            onSelect={selectCustomer}
            search={search}
            setSearch={setSearch}
            bucketFilter={bucketFilter}
            setBucketFilter={setBucketFilter}
            refreshFilter={refreshFilter}
            setRefreshFilter={setRefreshFilter}
          />
          {active ? (
            <CustomerView
              profile={active}
              rules={rules}
              onUpdated={(p) => {
                setActive(p);
                refreshPortfolio();
              }}
            />
          ) : (
            <div className="glass p-8 text-center text-white/55">
              {loading ? "Loading…" : "Pick a customer from the rail to see the full profile."}
            </div>
          )}
        </div>
      ) : (
        <PortfolioView
          stats={stats}
          portfolio={portfolio}
          onSelect={selectCustomer}
          rules={rules}
        />
      )}
    </div>
  );
}

// =========================================================================
// Hero banner — stats strip
// =========================================================================
function HeroBanner({
  stats,
  loading,
  onReseed,
  seeding,
}: {
  stats: ProfilePortfolioStats | null;
  loading: boolean;
  onReseed: () => void;
  seeding: boolean;
}) {
  const tiles = stats
    ? [
        { label: "customers", value: String(stats.total), tone: "violet" },
        { label: "average composite", value: stats.average_composite.toFixed(0), tone: "violet" },
        { label: "high or critical", value: String(stats.by_bucket.high + stats.by_bucket.critical), tone: "amber" },
        { label: "overdue refresh", value: String(stats.overdue_count), tone: "rose" },
        { label: "due within 30d", value: String(stats.due_within_30d), tone: "amber" },
        { label: "highest composite", value: stats.highest_composite.toFixed(0), tone: "violet" },
      ]
    : [];
  return (
    <section className="glass-strong ws-crp-hero relative overflow-hidden p-6 md:p-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="max-w-2xl">
          <div className="flex flex-wrap items-center gap-2">
            <span className="pill pill-ok">round 10 · day 50</span>
            <span className="pill">FATF · risk-based approach</span>
            <span className="pill">CDD · KYC refresh</span>
          </div>
          <h1 className="mt-3 text-3xl font-semibold tracking-tight md:text-4xl">
            <span className="grad-text">Customer Risk Profile</span>
          </h1>
          <p className="mt-3 max-w-2xl text-[14px] leading-relaxed text-white/70">
            Every TITAN surface (AML, sanctions, adverse media, typology, drift, network) condensed into{" "}
            <span className="text-white/85">one composite per customer</span>, the regulator-aligned bucket,
            an FATF-aligned KYC refresh schedule, and an analyst-override audit trail. This is the
            number compliance teams maintain to satisfy Recommendation 10 (CDD / risk-based approach).
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button className="btn-ghost" onClick={onReseed} disabled={seeding}>
            {seeding ? "Reseeding…" : "Reseed sample book"}
          </button>
        </div>
      </div>
      <div className="mt-6 grid grid-cols-2 gap-3 md:grid-cols-6">
        {tiles.map((t) => (
          <div key={t.label} className="glass px-3.5 py-3">
            <div className="text-[10.5px] uppercase tracking-[0.18em] text-white/40">
              {t.label}
            </div>
            <div className="mt-1 text-2xl font-semibold tracking-tight grad-text">
              {loading ? "…" : t.value}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function TabBar({ tab, setTab }: { tab: Tab; setTab: (t: Tab) => void }) {
  return (
    <div className="flex items-center gap-2">
      <button
        className={`ws-media-tab ${tab === "customer" ? "ws-media-tab-active" : ""}`}
        onClick={() => setTab("customer")}
      >
        Customer view
      </button>
      <button
        className={`ws-media-tab ${tab === "portfolio" ? "ws-media-tab-active" : ""}`}
        onClick={() => setTab("portfolio")}
      >
        Portfolio overview
      </button>
    </div>
  );
}

// =========================================================================
// Left rail — searchable, filterable customer list
// =========================================================================
function PortfolioRail({
  portfolio,
  active,
  onSelect,
  search,
  setSearch,
  bucketFilter,
  setBucketFilter,
  refreshFilter,
  setRefreshFilter,
}: {
  portfolio: ProfilePortfolio | null;
  active: Profile | null;
  onSelect: (id: string) => void;
  search: string;
  setSearch: (s: string) => void;
  bucketFilter: ProfileBucket | null;
  setBucketFilter: (b: ProfileBucket | null) => void;
  refreshFilter: ProfileRefreshLabel | null;
  setRefreshFilter: (r: ProfileRefreshLabel | null) => void;
}) {
  const rows = portfolio?.profiles ?? [];
  return (
    <aside className="glass p-3 lg:sticky lg:top-4 lg:h-[calc(100vh-32px)] lg:overflow-y-auto scroll-thin">
      <div className="space-y-3">
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search customers…"
          className="w-full rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2 text-[13px] text-white placeholder:text-white/40 focus:border-violet-400/45 focus:outline-none"
        />
        <div className="space-y-1.5">
          <div className="text-[10px] uppercase tracking-[0.18em] text-white/40">Bucket</div>
          <div className="flex flex-wrap gap-1.5">
            <button
              className={`ws-media-filter-chip ${bucketFilter === null ? "ws-media-filter-chip-active" : ""}`}
              onClick={() => setBucketFilter(null)}
              style={{ "--cat-accent": "#6E5BFF" } as any}
            >
              all
            </button>
            {BUCKETS.map((b) => (
              <button
                key={b}
                className={`ws-media-filter-chip ${bucketFilter === b ? "ws-media-filter-chip-active" : ""}`}
                onClick={() => setBucketFilter(bucketFilter === b ? null : b)}
                style={{ "--cat-accent": bucketColor(b) } as any}
              >
                {b}
              </button>
            ))}
          </div>
        </div>
        <div className="space-y-1.5">
          <div className="text-[10px] uppercase tracking-[0.18em] text-white/40">Refresh</div>
          <div className="flex flex-wrap gap-1.5">
            <button
              className={`ws-media-filter-chip ${refreshFilter === null ? "ws-media-filter-chip-active" : ""}`}
              onClick={() => setRefreshFilter(null)}
              style={{ "--cat-accent": "#6E5BFF" } as any}
            >
              all
            </button>
            {REFRESH_LABELS.map((r) => (
              <button
                key={r}
                className={`ws-media-filter-chip ${refreshFilter === r ? "ws-media-filter-chip-active" : ""}`}
                onClick={() => setRefreshFilter(refreshFilter === r ? null : r)}
                style={{ "--cat-accent": r === "overdue" ? "#ef4444" : r === "due_soon" ? "#fbbf24" : "#5eead4" } as any}
              >
                {r}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="mt-3 space-y-1.5">
        {rows.length === 0 ? (
          <div className="ws-media-empty">No customers match.</div>
        ) : (
          rows.map((p) => {
            const isActive = active?.customer.customer_id === p.customer.customer_id;
            return (
              <button
                key={p.customer.customer_id}
                onClick={() => onSelect(p.customer.customer_id)}
                className={`group w-full rounded-xl border px-2.5 py-2 text-left transition ${
                  isActive
                    ? "border-violet-400/45 bg-violet-500/10"
                    : "border-white/8 bg-white/[0.018] hover:border-white/16 hover:bg-white/[0.04]"
                }`}
              >
                <div className="flex items-center gap-2">
                  <div
                    className="h-7 w-7 shrink-0 rounded-full"
                    style={{
                      background: `conic-gradient(${bucketColor(p.bucket)} ${p.composite * 3.6}deg, rgba(255,255,255,0.05) 0)`,
                    }}
                  >
                    <div className="m-[3px] grid h-[20px] w-[20px] place-items-center rounded-full bg-[#070b14] text-[9.5px] font-semibold tracking-tight" style={{ color: bucketColor(p.bucket) }}>
                      {Math.round(p.composite)}
                    </div>
                  </div>
                  <div className="flex-1 truncate">
                    <div className="truncate text-[12.5px] font-medium text-white/95">
                      {p.customer.display_name || p.customer.customer_id}
                    </div>
                    <div className="flex items-center gap-1.5 text-[10.5px] text-white/45">
                      <span>{p.customer.customer_id}</span>
                      {p.customer.domicile && (
                        <span className="rounded bg-white/5 px-1 text-[9.5px] tracking-wider text-white/55">
                          {p.customer.domicile}
                        </span>
                      )}
                      {p.refresh.label === "overdue" && (
                        <span className="text-[#fda4af]">overdue</span>
                      )}
                      {p.refresh.label === "due_soon" && (
                        <span className="text-[#fcd34d]">due</span>
                      )}
                    </div>
                  </div>
                </div>
              </button>
            );
          })
        )}
      </div>
    </aside>
  );
}

// =========================================================================
// Customer view — the big detail panel
// =========================================================================
function CustomerView({
  profile,
  rules,
  onUpdated,
}: {
  profile: Profile;
  rules: ProfileRules | null;
  onUpdated: (p: Profile) => void;
}) {
  const [overrideOpen, setOverrideOpen] = useState(false);
  const [pending, setPending] = useState(false);
  const bucketInterval = rules?.refresh_days?.[profile.bucket];

  const onSetOverride = async (
    locked_bucket: ProfileBucket,
    justification: string,
    actor: string,
  ) => {
    setPending(true);
    try {
      const r = await setProfileOverride(profile.customer.customer_id, {
        locked_bucket,
        justification,
        actor,
      });
      onUpdated(r.profile);
      setOverrideOpen(false);
    } finally {
      setPending(false);
    }
  };

  const onClearOverride = async () => {
    setPending(true);
    try {
      const r = await clearProfileOverride(profile.customer.customer_id, {
        actor: "TITAN-ANALYST",
        note: "Override cleared from customer view.",
      });
      onUpdated(r.profile);
    } finally {
      setPending(false);
    }
  };

  return (
    <div className="space-y-5">
      <HeroCustomer profile={profile} bucketInterval={bucketInterval} onOverride={() => setOverrideOpen(true)} onClearOverride={onClearOverride} pending={pending} />

      <div className="grid gap-5 lg:grid-cols-[1.1fr_1fr]">
        <FactorPanel factors={profile.factors} modifiers={profile.modifiers} modifierTotal={profile.modifier_total} />
        <FactorWheelPanel factors={profile.factors} />
      </div>

      <EvidencePanel profile={profile} />

      <HistoryPanel history={profile.history || []} />

      {overrideOpen && (
        <OverrideDialog
          profile={profile}
          onClose={() => setOverrideOpen(false)}
          onSubmit={onSetOverride}
          pending={pending}
        />
      )}
    </div>
  );
}

function HeroCustomer({
  profile,
  bucketInterval,
  onOverride,
  onClearOverride,
  pending,
}: {
  profile: Profile;
  bucketInterval?: number;
  onOverride: () => void;
  onClearOverride: () => void;
  pending: boolean;
}) {
  const c = profile.customer;
  return (
    <section className="glass relative overflow-hidden p-6">
      <div className="grid gap-5 md:grid-cols-[180px_1fr_auto] md:items-center">
        <div className="flex justify-center md:justify-start">
          <ProfileRing
            composite={profile.composite}
            engine_composite={profile.engine_composite}
            bucket={profile.bucket}
            size={156}
          />
        </div>

        <div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[11px] uppercase tracking-[0.20em]" style={{ color: bucketColor(profile.bucket) }}>
              {profile.bucket}
            </span>
            <span className="pill">{c.customer_type || "individual"}</span>
            {c.domicile && <span className="pill">{c.domicile}</span>}
            {c.pep && <span className="pill" style={{ borderColor: "#a78bfa55", color: "#c4b5fd" }}>PEP</span>}
            {profile.override && (
              <span className="pill" style={{ borderColor: "#a78bfa55", color: "#c4b5fd" }}>
                override active
              </span>
            )}
          </div>
          <h2 className="mt-2 text-2xl font-semibold tracking-tight md:text-[26px]">
            {c.display_name || c.customer_id}
          </h2>
          <div className="text-[12.5px] text-white/55">
            {c.customer_id}
            {c.products && c.products.length > 0 && (
              <span className="ml-2">· {c.products.join(" · ")}</span>
            )}
          </div>
          <p className="mt-3 max-w-2xl text-[13.5px] leading-relaxed text-white/75">
            {profile.narrative}
          </p>

          <div className="mt-4 max-w-xl">
            <RefreshTimeline
              anchor={profile.kyc_anchor}
              due={profile.kyc_due}
              refresh={profile.refresh}
              bucketInterval={bucketInterval}
            />
          </div>
        </div>

        <div className="flex flex-col items-stretch gap-2 md:w-[180px]">
          <button className="btn-primary" onClick={onOverride} disabled={pending}>
            Set override
          </button>
          {profile.override && (
            <button className="btn-ghost" onClick={onClearOverride} disabled={pending}>
              Clear override
            </button>
          )}
        </div>
      </div>

      {profile.override && (
        <div className="mt-5 rounded-xl border border-violet-400/30 bg-violet-500/[0.08] p-4">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <div className="text-[11px] uppercase tracking-[0.18em] text-violet-200">
              Analyst override
            </div>
            <div className="text-[11px] text-white/45">
              {fmtDt(profile.override.set_at)} · {profile.override.actor}
            </div>
          </div>
          <div className="mt-1.5 text-[14px] text-white/85">
            Locked to <span className="font-medium" style={{ color: bucketColor(profile.override.locked_bucket as ProfileBucket) }}>
              {profile.override.locked_bucket}
            </span> · engine rates <span className="text-white/55">
              {profile.engine_bucket} ({profile.engine_composite.toFixed(0)})
            </span>
          </div>
          <p className="mt-2 text-[12.5px] leading-relaxed text-white/65">
            {profile.override.justification}
          </p>
        </div>
      )}
    </section>
  );
}

// =========================================================================
// Factor breakdown bars + modifiers
// =========================================================================
function FactorPanel({
  factors,
  modifiers,
  modifierTotal,
}: {
  factors: ProfileFactor[];
  modifiers: ProfileModifier[];
  modifierTotal: number;
}) {
  return (
    <section className="glass p-5">
      <div className="flex items-baseline justify-between">
        <h3 className="text-[15px] font-semibold tracking-tight">Surface contributions</h3>
        <div className="text-[11px] uppercase tracking-[0.18em] text-white/40">weight × intensity</div>
      </div>
      <div className="mt-3 space-y-2.5">
        {factors.map((f) => (
          <FactorRow key={f.key} factor={f} />
        ))}
      </div>

      {modifiers.length > 0 && (
        <div className="mt-5 border-t border-white/8 pt-4">
          <div className="flex items-baseline justify-between">
            <h4 className="text-[13px] font-medium text-white/85">Modifiers</h4>
            <div className="text-[11px] text-white/55">+ {modifierTotal.toFixed(1)} pts</div>
          </div>
          <div className="mt-2 space-y-1.5">
            {modifiers.map((m) => (
              <div
                key={m.key}
                className="flex items-center justify-between gap-2 rounded-lg border border-white/8 bg-white/[0.02] px-3 py-1.5"
              >
                <div>
                  <div className="text-[12.5px] text-white/85">{m.label}</div>
                  <div className="text-[11px] text-white/45">{m.detail}</div>
                </div>
                <div className="text-[12.5px] font-semibold text-violet-300">
                  +{m.points.toFixed(1)}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}

function FactorRow({ factor }: { factor: ProfileFactor }) {
  const wPct = (factor.weight / 28) * 100;
  const filledPct = Math.max(0, Math.min(100, factor.intensity * 100));
  return (
    <div className="rounded-xl border border-white/8 bg-white/[0.018] px-3 py-2.5">
      <div className="flex items-baseline justify-between">
        <div className="flex items-center gap-2">
          <span
            className="inline-block h-2.5 w-2.5 rounded-full"
            style={{ background: factor.accent, boxShadow: `0 0 0 2px ${factor.accent}22` }}
          />
          <span className="text-[13px] font-medium text-white/90">{factor.label}</span>
        </div>
        <div className="text-[11.5px] text-white/55">
          <span style={{ color: factor.accent }}>{factor.points.toFixed(1)}</span>
          <span className="ml-1.5 text-white/35">/ {factor.weight.toFixed(0)} max</span>
        </div>
      </div>
      <div className="mt-1.5 text-[11.5px] text-white/55">{factor.detail}</div>
      <div className="relative mt-2 h-2 rounded-full bg-white/[0.04]" style={{ width: `${wPct}%` }}>
        <div
          className="absolute inset-y-0 left-0 rounded-full"
          style={{
            width: `${filledPct}%`,
            background: `linear-gradient(90deg, ${factor.accent}77, ${factor.accent})`,
            transition: "width 250ms",
          }}
        />
      </div>
    </div>
  );
}

function FactorWheelPanel({ factors }: { factors: ProfileFactor[] }) {
  return (
    <section className="glass p-5">
      <div className="flex items-baseline justify-between">
        <h3 className="text-[15px] font-semibold tracking-tight">Risk signature</h3>
        <div className="text-[11px] uppercase tracking-[0.18em] text-white/40">six-axis fingerprint</div>
      </div>
      <div className="mt-2 aspect-square w-full max-w-[420px]">
        <FactorWheel factors={factors} size={420} />
      </div>
      <div className="mt-2 text-[12px] leading-relaxed text-white/55">
        Each spoke's <em>length</em> is the surface's weight; the filled polygon
        traces what percentage of that weight is currently firing. A wide-and-even
        polygon = compound risk; a long single spoke = a single dominant signal.
      </div>
    </section>
  );
}

// =========================================================================
// Evidence drill-down — collapses what each surface knows
// =========================================================================
function EvidencePanel({ profile }: { profile: Profile }) {
  const items = profile.factors.filter((f) => f.intensity > 0 || Object.keys(f.evidence || {}).length > 0);
  if (!items.length) {
    return null;
  }
  return (
    <section className="glass p-5">
      <div className="flex items-baseline justify-between">
        <h3 className="text-[15px] font-semibold tracking-tight">Evidence trail</h3>
        <div className="text-[11px] uppercase tracking-[0.18em] text-white/40">per-surface drill-down</div>
      </div>
      <div className="mt-3 grid gap-2.5 md:grid-cols-2">
        {items.map((f) => (
          <EvidenceCard key={f.key} factor={f} />
        ))}
      </div>
    </section>
  );
}

function EvidenceCard({ factor }: { factor: ProfileFactor }) {
  const ev = factor.evidence || {};
  const rows: { k: string; v: string }[] = [];

  if (factor.key === "transaction") {
    if ("risk_score" in ev) rows.push({ k: "risk score", v: `${ev.risk_score} (${ev.band || "—"})` });
    if ("fired_count" in ev) rows.push({ k: "firing detectors", v: String(ev.fired_count) });
    if (Array.isArray(ev.top_accounts) && ev.top_accounts.length) {
      const t = ev.top_accounts[0];
      rows.push({ k: "top account", v: `${t.account_id} → ${t.risk_score}` });
    }
  } else if (factor.key === "sanctions") {
    if ("best_similarity" in ev) {
      rows.push({ k: "best similarity", v: `${((ev.best_similarity || 0) * 100).toFixed(0)}%` });
    }
    if ("best_grade" in ev) rows.push({ k: "best grade", v: String(ev.best_grade) });
    if (Array.isArray(ev.hits) && ev.hits.length) {
      const h = ev.hits[0];
      rows.push({ k: "matched", v: `${h.matched} · ${h.list || "?"}` });
    }
  } else if (factor.key === "media") {
    if ("composite" in ev) rows.push({ k: "composite", v: `${ev.composite} (${ev.grade || "—"})` });
    if ("hit_count" in ev) rows.push({ k: "articles", v: String(ev.hit_count) });
    if (Array.isArray(ev.top_articles) && ev.top_articles.length) {
      rows.push({ k: "headline", v: ev.top_articles[0].headline });
    }
  } else if (factor.key === "typology") {
    if ("code" in ev) rows.push({ k: "playbook", v: `${ev.code} — ${ev.name || ""}` });
    if ("confidence" in ev) rows.push({ k: "confidence", v: `${((ev.confidence || 0) * 100).toFixed(0)}%` });
    if ("severity_floor" in ev) rows.push({ k: "severity floor", v: String(ev.severity_floor) });
  } else if (factor.key === "drift") {
    if ("overall" in ev) rows.push({ k: "overall", v: `${(Number(ev.overall) || 0).toFixed(2)} (${ev.verdict || "—"})` });
    if (ev.onset_iso) rows.push({ k: "onset", v: String(ev.onset_iso).slice(0, 10) });
    if (Array.isArray(ev.top_drivers) && ev.top_drivers.length) {
      rows.push({ k: "top driver", v: ev.top_drivers[0].label });
    }
  } else if (factor.key === "network") {
    if ("solo_risk" in ev) rows.push({ k: "solo risk", v: String(ev.solo_risk) });
    if ("network_risk" in ev) rows.push({ k: "network risk", v: String(ev.network_risk) });
    if ("lift" in ev) rows.push({ k: "lift", v: `+${ev.lift}` });
    if ("peer_count" in ev) rows.push({ k: "peers", v: String(ev.peer_count) });
  }

  if (!rows.length) {
    rows.push({ k: "status", v: factor.intensity > 0 ? "evidence present" : "no signal" });
  }

  return (
    <div className="rounded-xl border border-white/8 bg-white/[0.018] p-3.5">
      <div className="flex items-baseline justify-between">
        <div className="flex items-center gap-2">
          <span
            className="inline-block h-2.5 w-2.5 rounded-full"
            style={{ background: factor.accent, boxShadow: `0 0 0 2px ${factor.accent}22` }}
          />
          <div className="text-[13px] font-medium text-white/90">{factor.label}</div>
        </div>
        <div className="text-[11px] text-white/45">{(factor.intensity * 100).toFixed(0)}%</div>
      </div>
      <div className="mt-2 space-y-1">
        {rows.map((r, i) => (
          <div key={i} className="flex items-baseline justify-between text-[12px]">
            <div className="text-white/45">{r.k}</div>
            <div className="ml-3 truncate text-right text-white/85">{r.v}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

// =========================================================================
// History strip
// =========================================================================
function HistoryPanel({ history }: { history: ProfileHistoryEntry[] }) {
  return (
    <section className="glass p-5">
      <div className="flex items-baseline justify-between">
        <h3 className="text-[15px] font-semibold tracking-tight">Composite history</h3>
        <div className="text-[11px] uppercase tracking-[0.18em] text-white/40">audit trail</div>
      </div>
      <div className="mt-3">
        <HistoryStrip history={history} />
      </div>
      <Legend />
      {history.length > 0 && (
        <div className="mt-3 max-h-[200px] overflow-y-auto scroll-thin border-t border-white/8 pt-3">
          <table className="w-full text-[12px]">
            <thead className="text-[10.5px] uppercase tracking-[0.16em] text-white/40">
              <tr>
                <th className="pb-1.5 text-left">When</th>
                <th className="pb-1.5 text-left">Kind</th>
                <th className="pb-1.5 text-right">Composite</th>
                <th className="pb-1.5 text-left">Bucket</th>
                <th className="pb-1.5 text-left">Actor</th>
                <th className="pb-1.5 text-left">Note</th>
              </tr>
            </thead>
            <tbody className="text-white/75">
              {history.map((h) => (
                <tr key={h.id} className="border-t border-white/5">
                  <td className="py-1.5">{fmtDt(h.refreshed_at)}</td>
                  <td className="py-1.5">
                    <span className="rounded-full border border-white/10 bg-white/[0.04] px-1.5 py-0.5 text-[10.5px] uppercase tracking-wider text-white/65">
                      {h.refresh_kind}
                    </span>
                  </td>
                  <td className="py-1.5 text-right">{h.composite.toFixed(1)}</td>
                  <td className="py-1.5">
                    <span className="rounded-full px-1.5 py-0.5 text-[10.5px]" style={{ background: bucketAccent(h.bucket), color: bucketColor(h.bucket) }}>
                      {h.bucket}
                    </span>
                  </td>
                  <td className="py-1.5 text-white/65">{h.actor || "—"}</td>
                  <td className="py-1.5 text-white/55 truncate max-w-[280px]">{h.note || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function Legend() {
  return (
    <div className="mt-2 flex flex-wrap items-center gap-3 text-[10.5px] text-white/55">
      <span className="inline-flex items-center gap-1.5">
        <span className="h-1.5 w-3 rounded-full bg-violet-400" /> composite
      </span>
      <span className="inline-flex items-center gap-1.5">
        <span className="h-1.5 w-3 rounded-full border border-white/30" style={{ borderStyle: "dashed" }} /> engine
      </span>
      <span className="inline-flex items-center gap-1.5">
        <span className="h-2 w-2 rounded-full ring-2 ring-violet-400/60 bg-violet-300" /> override
      </span>
    </div>
  );
}

// =========================================================================
// Override dialog
// =========================================================================
function OverrideDialog({
  profile,
  onClose,
  onSubmit,
  pending,
}: {
  profile: Profile;
  onClose: () => void;
  onSubmit: (b: ProfileBucket, j: string, actor: string) => void;
  pending: boolean;
}) {
  const [locked, setLocked] = useState<ProfileBucket>(
    profile.override?.locked_bucket || profile.bucket,
  );
  const [justification, setJustification] = useState(
    profile.override?.justification || "",
  );
  const [actor, setActor] = useState(profile.override?.actor || "TITAN-ANALYST");

  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-black/70 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="glass-strong w-full max-w-lg p-5"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-baseline justify-between">
          <h3 className="text-[15px] font-semibold tracking-tight">Analyst risk override</h3>
          <button
            className="text-white/55 hover:text-white"
            onClick={onClose}
            aria-label="Close"
          >
            ✕
          </button>
        </div>
        <p className="mt-1 text-[12px] text-white/55">
          Pin <span className="text-white/85">{profile.customer.display_name || profile.customer.customer_id}</span> to a specific bucket. The engine composite remains visible alongside the override.
        </p>

        <div className="mt-4 space-y-3">
          <div>
            <div className="text-[10.5px] uppercase tracking-[0.18em] text-white/45">Locked bucket</div>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {BUCKETS.map((b) => (
                <button
                  key={b}
                  type="button"
                  className={`ws-media-filter-chip ${locked === b ? "ws-media-filter-chip-active" : ""}`}
                  onClick={() => setLocked(b)}
                  style={{ "--cat-accent": bucketColor(b) } as any}
                >
                  {b}
                </button>
              ))}
            </div>
          </div>
          <div>
            <div className="text-[10.5px] uppercase tracking-[0.18em] text-white/45">Justification (required)</div>
            <textarea
              className="mt-1.5 w-full resize-none rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2 text-[13px] text-white placeholder:text-white/35 focus:border-violet-400/45 focus:outline-none"
              rows={4}
              maxLength={600}
              value={justification}
              onChange={(e) => setJustification(e.target.value)}
              placeholder="Document the rationale — what evidence supports raising or lowering the bucket?"
            />
            <div className="mt-1 text-right text-[10.5px] text-white/35">
              {justification.length} / 600
            </div>
          </div>
          <div>
            <div className="text-[10.5px] uppercase tracking-[0.18em] text-white/45">Actor</div>
            <input
              type="text"
              className="mt-1.5 w-full rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2 text-[13px] text-white placeholder:text-white/35 focus:border-violet-400/45 focus:outline-none"
              value={actor}
              onChange={(e) => setActor(e.target.value)}
            />
          </div>
        </div>

        <div className="mt-5 flex justify-end gap-2">
          <button className="btn-ghost" onClick={onClose} disabled={pending}>
            Cancel
          </button>
          <button
            className="btn-primary"
            onClick={() => onSubmit(locked, justification, actor || "TITAN-ANALYST")}
            disabled={pending || justification.trim().length < 4}
          >
            {pending ? "Saving…" : "Apply override"}
          </button>
        </div>
      </div>
    </div>
  );
}

// =========================================================================
// Portfolio overview tab
// =========================================================================
function PortfolioView({
  stats,
  portfolio,
  onSelect,
  rules,
}: {
  stats: ProfilePortfolioStats | null;
  portfolio: ProfilePortfolio | null;
  onSelect: (id: string) => void;
  rules: ProfileRules | null;
}) {
  if (!stats || !portfolio) {
    return <div className="glass p-8 text-center text-white/55">Loading…</div>;
  }
  const total = stats.total || 1;
  const buckets: ProfileBucket[] = ["low", "medium", "high", "critical"];

  return (
    <div className="grid gap-5 lg:grid-cols-[1fr_1fr]">
      <section className="glass p-5">
        <h3 className="text-[15px] font-semibold tracking-tight">Bucket distribution</h3>
        <div className="text-[11px] text-white/45">share of customer book by bucket</div>
        <div className="mt-4 space-y-2.5">
          {buckets.map((b) => {
            const count = stats.by_bucket[b] || 0;
            const pct = (count / total) * 100;
            return (
              <div key={b}>
                <div className="flex items-baseline justify-between text-[12px]">
                  <div className="flex items-center gap-1.5">
                    <span
                      className="inline-block h-2.5 w-2.5 rounded-full"
                      style={{ background: bucketColor(b) }}
                    />
                    <span className="capitalize text-white/85">{b}</span>
                    <span className="text-white/45">
                      · refresh every {rules?.refresh_days?.[b] || "—"}d
                    </span>
                  </div>
                  <div className="text-white/75">
                    {count}
                    <span className="ml-2 text-white/45">{pct.toFixed(0)}%</span>
                  </div>
                </div>
                <div className="mt-1 h-2 rounded-full bg-white/[0.04]">
                  <div
                    className="h-full rounded-full"
                    style={{
                      width: `${pct}%`,
                      background: `linear-gradient(90deg, ${bucketColor(b)}99, ${bucketColor(b)})`,
                      transition: "width 250ms",
                    }}
                  />
                </div>
              </div>
            );
          })}
        </div>
      </section>

      <section className="glass p-5">
        <h3 className="text-[15px] font-semibold tracking-tight">KYC refresh state</h3>
        <div className="text-[11px] text-white/45">CDD cycle hygiene</div>
        <div className="mt-4 space-y-2.5">
          {REFRESH_LABELS.map((r) => {
            const count = stats.by_refresh[r] || 0;
            const pct = (count / total) * 100;
            const tone =
              r === "overdue" ? "#ef4444" :
              r === "due_soon" ? "#fbbf24" :
              r === "current" ? "#22d3a8" : "#94a3b8";
            return (
              <div key={r}>
                <div className="flex items-baseline justify-between text-[12px]">
                  <div className="flex items-center gap-1.5">
                    <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: tone }} />
                    <span className="capitalize text-white/85">{r.replace("_", " ")}</span>
                  </div>
                  <div className="text-white/75">{count}</div>
                </div>
                <div className="mt-1 h-2 rounded-full bg-white/[0.04]">
                  <div
                    className="h-full rounded-full"
                    style={{
                      width: `${pct}%`,
                      background: `linear-gradient(90deg, ${tone}99, ${tone})`,
                    }}
                  />
                </div>
              </div>
            );
          })}
        </div>
      </section>

      <section className="glass p-5 lg:col-span-2">
        <div className="flex items-baseline justify-between">
          <div>
            <h3 className="text-[15px] font-semibold tracking-tight">Domicile breakdown</h3>
            <div className="text-[11px] text-white/45">where the book sits</div>
          </div>
        </div>
        <div className="mt-3 flex flex-wrap gap-1.5">
          {Object.entries(stats.by_domicile).map(([dom, count]) => (
            <div key={dom} className="ws-media-chip" style={{ "--cat-accent": "#6E5BFF" } as any}>
              {dom}
              <span className="ml-1 text-white/55">× {count}</span>
            </div>
          ))}
        </div>
      </section>

      <section className="glass p-5 lg:col-span-2">
        <h3 className="text-[15px] font-semibold tracking-tight">Top of book</h3>
        <div className="text-[11px] text-white/45">highest-composite customers</div>
        <div className="mt-3 grid gap-2 md:grid-cols-2">
          {[...portfolio.profiles].sort((a, b) => b.composite - a.composite).slice(0, 8).map((p) => (
            <button
              key={p.customer.customer_id}
              onClick={() => onSelect(p.customer.customer_id)}
              className="ws-net-row text-left"
            >
              <div className="flex items-center gap-3 px-3 py-2.5">
                <div
                  className="h-9 w-9 shrink-0 rounded-full"
                  style={{
                    background: `conic-gradient(${bucketColor(p.bucket)} ${p.composite * 3.6}deg, rgba(255,255,255,0.05) 0)`,
                  }}
                >
                  <div
                    className="m-1 grid h-[28px] w-[28px] place-items-center rounded-full bg-[#070b14] text-[11px] font-semibold"
                    style={{ color: bucketColor(p.bucket) }}
                  >
                    {Math.round(p.composite)}
                  </div>
                </div>
                <div className="flex-1">
                  <div className="text-[13px] font-medium text-white/95">
                    {p.customer.display_name || p.customer.customer_id}
                  </div>
                  <div className="text-[11px] text-white/45">
                    {p.customer.customer_id}
                    {p.customer.domicile && <span className="ml-2">{p.customer.domicile}</span>}
                    <span className="ml-2 capitalize" style={{ color: bucketColor(p.bucket) }}>
                      {p.bucket}
                    </span>
                  </div>
                </div>
                <div className="text-[11px]" style={{ color:
                  p.refresh.label === "overdue" ? "#fda4af"
                  : p.refresh.label === "due_soon" ? "#fcd34d"
                  : "rgba(255,255,255,0.45)" }}>
                  {p.refresh.label}
                </div>
              </div>
            </button>
          ))}
        </div>
      </section>
    </div>
  );
}
