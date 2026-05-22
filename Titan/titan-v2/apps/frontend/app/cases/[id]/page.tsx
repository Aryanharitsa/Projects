"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import AgePill from "../../../components/AgePill";
import { Avatar } from "../../../components/CaseCard";
import CaseNetworkPanel from "../../../components/CaseNetworkPanel";
import FactorBars from "../../../components/FactorBars";
import PriorityDot, { PRIORITY_LABEL } from "../../../components/PriorityDot";
import ScoreRing from "../../../components/ScoreRing";
import SimilarityRing, { GRADE_TINT } from "../../../components/SimilarityRing";
import Timeline from "../../../components/Timeline";
import TxGraph from "../../../components/TxGraph";
import TypologyPanel from "../../../components/TypologyPanel";
import TypologyBadge from "../../../components/TypologyBadge";
import {
  CaseDetail,
  CaseStatus,
  assignCase,
  deleteCase,
  fileSarOnCase,
  getCase,
  noteCase,
  transitionCase,
} from "../../../lib/api";

const STATUS_OPTIONS: { value: CaseStatus; label: string }[] = [
  { value: "open", label: "Open" },
  { value: "review", label: "Review" },
  { value: "escalated", label: "Escalated" },
  { value: "cleared", label: "Cleared" },
  { value: "sar_filed", label: "SAR filed" },
];

const TERMINAL: CaseStatus[] = ["cleared", "sar_filed"];

// Allowed forward transitions per current status (the "+ reopen" exit
// is rendered separately when the case is terminal).
const FORWARD_FROM: Record<CaseStatus, CaseStatus[]> = {
  open: ["review", "escalated", "cleared", "sar_filed"],
  review: ["escalated", "cleared", "sar_filed"],
  escalated: ["cleared", "sar_filed"],
  cleared: [],
  sar_filed: [],
};

export default function CaseDetailPage() {
  const router = useRouter();
  const params = useParams<{ id: string }>();
  const id = params?.id || "";

  const [c, setC] = useState<CaseDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [actor, setActor] = useState<string>("");
  const [noteBody, setNoteBody] = useState("");
  const [assignVal, setAssignVal] = useState("");
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [sarBusy, setSarBusy] = useState(false);
  const [openSar, setOpenSar] = useState(false);

  // Persist analyst handle locally so subsequent actions are pre-filled.
  useEffect(() => {
    if (typeof window === "undefined") return;
    const saved = window.localStorage.getItem("titan:analyst");
    if (saved) setActor(saved);
  }, []);
  useEffect(() => {
    if (typeof window === "undefined") return;
    if (actor) window.localStorage.setItem("titan:analyst", actor);
  }, [actor]);

  const refresh = useCallback(async () => {
    if (!id) return;
    setLoading(true);
    setErr(null);
    try {
      const out = await getCase(id);
      setC(out.case);
      setAssignVal(out.case.assignee ?? "");
    } catch (e: any) {
      setErr(e.message || "Failed to load case");
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const sarEvent = useMemo(
    () => c?.events.find((e) => e.type === "sar"),
    [c],
  );
  const sarMd: string | null = sarEvent?.payload?.narrative_md ?? null;

  const fired = useMemo(
    () => (c?.snapshot.factors ?? []).filter((f) => (f.points ?? 0) > 0),
    [c],
  );

  const onTransition = useCallback(
    async (to: CaseStatus | "reopen", note?: string) => {
      if (!c || !actor.trim()) {
        setErr("Set your analyst handle before transitioning.");
        return;
      }
      setBusyAction(to);
      setErr(null);
      try {
        const out = await transitionCase(c.id, to, { actor, note });
        // Re-fetch full detail to pull events too.
        if (out.ok) await refresh();
      } catch (e: any) {
        setErr(e.message || "Transition failed");
      } finally {
        setBusyAction(null);
      }
    },
    [c, actor, refresh],
  );

  const onAssign = useCallback(async () => {
    if (!c || !actor.trim()) {
      setErr("Set your analyst handle first.");
      return;
    }
    setBusyAction("assign");
    setErr(null);
    try {
      await assignCase(c.id, assignVal.trim(), actor);
      await refresh();
    } catch (e: any) {
      setErr(e.message || "Assign failed");
    } finally {
      setBusyAction(null);
    }
  }, [c, actor, assignVal, refresh]);

  const onAddNote = useCallback(async () => {
    if (!c || !actor.trim() || !noteBody.trim()) return;
    setBusyAction("note");
    setErr(null);
    try {
      await noteCase(c.id, noteBody.trim(), actor);
      setNoteBody("");
      await refresh();
    } catch (e: any) {
      setErr(e.message || "Note failed");
    } finally {
      setBusyAction(null);
    }
  }, [c, actor, noteBody, refresh]);

  const onFileSar = useCallback(async () => {
    if (!c || !actor.trim()) {
      setErr("Set your analyst handle first.");
      return;
    }
    setSarBusy(true);
    setErr(null);
    try {
      await fileSarOnCase(c.id, { actor, analyst: actor });
      await refresh();
      setOpenSar(true);
    } catch (e: any) {
      setErr(e.message || "SAR generation failed");
    } finally {
      setSarBusy(false);
    }
  }, [c, actor, refresh]);

  const onDelete = useCallback(async () => {
    if (!c) return;
    if (!confirm(`Delete ${c.id}? This is irreversible.`)) return;
    setBusyAction("delete");
    try {
      await deleteCase(c.id);
      router.push("/cases");
    } catch (e: any) {
      setErr(e.message || "Delete failed");
      setBusyAction(null);
    }
  }, [c, router]);

  if (loading && !c) {
    return (
      <div className="grid place-items-center py-24 text-white/55">
        Loading case…
      </div>
    );
  }
  if (!c) {
    return (
      <div className="glass space-y-3 p-8 text-center">
        <div className="text-3xl">∅</div>
        <h2 className="text-xl font-semibold tracking-tight">Case not found.</h2>
        {err && <p className="text-rose-300 text-[12.5px]">{err}</p>}
        <Link href="/cases" className="btn">Back to queue</Link>
      </div>
    );
  }

  const isClosed = TERMINAL.includes(c.status);
  const forward = FORWARD_FROM[c.status];

  return (
    <div className="space-y-6">
      <nav className="flex items-center justify-between gap-3">
        <Link href="/cases" className="btn-ghost">
          ← Back to queue
        </Link>
        <span className="font-mono text-[11px] text-white/40">{c.id}</span>
      </nav>

      {/* Header */}
      <header className="glass-strong p-5 md:p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="flex flex-wrap items-center gap-4">
            <ScoreRing score={c.alert_score} band={c.band} size={92} />
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <PriorityDot priority={c.priority} />
                <span className="text-[11.5px] font-semibold uppercase tracking-wider text-white/85">
                  {PRIORITY_LABEL[c.priority]} priority
                </span>
                <span className="font-mono text-[10.5px] text-white/45">·</span>
                <AgePill hours={c.age_hours} sla={c.sla} />
                {c.typology_code && (
                  <>
                    <span className="font-mono text-[10.5px] text-white/45">·</span>
                    <TypologyBadge
                      match={{
                        code: c.typology_code,
                        confidence: c.typology_confidence ?? 0,
                      }}
                      size="sm"
                      showName
                    />
                  </>
                )}
              </div>
              <h1 className="mt-1.5 font-mono text-xl text-white/90 md:text-2xl">
                {c.account_id}
              </h1>
              {c.display_name && (
                <div className="mt-0.5 text-[13px] text-white/65">
                  {c.display_name}
                </div>
              )}
              <div className="mt-2 flex flex-wrap items-center gap-2 text-[11.5px] text-white/55">
                <span className={`pill ${
                  c.status === "open" ? "" :
                  c.status === "review" ? "pill-ok" :
                  c.status === "escalated" ? "pill-warn" :
                  c.status === "sar_filed" ? "pill-ok" :
                  "pill"
                }`}>
                  {c.status.replace("_", " ")}
                </span>
                <span>opened {timeAgo(c.opened_at_iso)}</span>
                <span className="text-white/30">·</span>
                <span>by {c.opened_by}</span>
                {c.assignee && (
                  <>
                    <span className="text-white/30">·</span>
                    <span className="inline-flex items-center gap-1.5">
                      <Avatar name={c.assignee} size={14} />
                      <span>assigned to {c.assignee}</span>
                    </span>
                  </>
                )}
                {c.sar_id && (
                  <>
                    <span className="text-white/30">·</span>
                    <span className="font-mono text-emerald-300">{c.sar_id}</span>
                  </>
                )}
              </div>
            </div>
          </div>

          <div className="flex flex-wrap items-end gap-2">
            <div>
              <div className="label">Acting as</div>
              <input
                value={actor}
                onChange={(e) => setActor(e.target.value)}
                placeholder="analyst handle"
                className="input min-w-[180px]"
              />
            </div>
          </div>
        </div>

        {/* Status workflow */}
        <div className="mt-5 flex flex-wrap items-center gap-2">
          {isClosed ? (
            <button
              className="btn"
              onClick={() => onTransition("reopen", "Reopening for further review.")}
              disabled={busyAction !== null || !actor.trim()}
            >
              Reopen case
            </button>
          ) : (
            forward.map((to) => (
              <button
                key={to}
                className={
                  to === "sar_filed"
                    ? "btn-primary"
                    : to === "cleared"
                    ? "btn"
                    : "btn"
                }
                onClick={() => {
                  if (to === "sar_filed") onFileSar();
                  else onTransition(to);
                }}
                disabled={busyAction !== null || !actor.trim()}
              >
                {to === "sar_filed" ? "Generate + file SAR" :
                  to === "review" ? "Mark in review" :
                  to === "escalated" ? "Escalate to L2" :
                  to === "cleared" ? "Clear (no action)" :
                  to.replace("_", " ")}
              </button>
            ))
          )}
          <span className="ml-auto" />
          <button
            className="btn-ghost text-rose-300/85 hover:bg-rose-500/[0.08]"
            onClick={onDelete}
            disabled={busyAction !== null}
            title="Hard delete (admin demo only)"
          >
            Delete
          </button>
        </div>

        {!actor.trim() && (
          <p className="mt-3 text-[11.5px] text-amber-300/85">
            Set an analyst handle (above right) before transitioning, assigning,
            or noting — every action is recorded with the actor's name on the audit
            trail.
          </p>
        )}
      </header>

      {err && (
        <div className="glass border-rose-400/30 bg-rose-500/[0.06] p-3 text-[12.5px] text-rose-300">
          {err}
        </div>
      )}

      {/* Main grid: evidence (left) + timeline + actions (right) */}
      <section className="grid gap-5 lg:grid-cols-[1.1fr_1fr]">
        {/* Left: evidence */}
        <div className="space-y-5">
          <div className="glass p-5">
            <div className="flex items-baseline justify-between">
              <h2 className="text-[15px] font-semibold tracking-tight">
                Evidence snapshot
              </h2>
              <span className="font-mono text-[10.5px] text-white/40">
                frozen at open · {fired.length} factor{fired.length !== 1 ? "s" : ""} fired
              </span>
            </div>
            <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
              <SmallStat
                label="Risk score"
                value={c.risk_score.toFixed(0)}
              />
              <SmallStat
                label="Sanctions hits"
                value={c.sanctions_count}
                tone={c.sanctions_count > 0 ? "rose" : "neutral"}
              />
              <SmallStat
                label="Counterparties"
                value={c.snapshot.counterparty_count ?? "—"}
              />
              <SmallStat
                label="Net flow"
                value={`${shortMoney(c.snapshot.outbound_total)} out`}
              />
            </div>
            <div className="mt-5 grid gap-5 md:grid-cols-2">
              <div className="rounded-xl border border-white/10 bg-black/20 p-4">
                <div className="label">Factor breakdown</div>
                <FactorBars factors={c.snapshot.factors} />
              </div>
              <div className="rounded-xl border border-white/10 bg-black/20 p-4">
                <div className="label">Transaction graph</div>
                <TxGraph
                  edges={(c.snapshot.edges ?? []).map((e) => ({
                    from: e.from,
                    to: e.to,
                    amount: e.amount,
                  }))}
                  highlight={c.account_id}
                />
                <div className="mt-2 text-[11px] text-white/45">
                  Highlighted node = subject account. Edges scale with transfer
                  size.
                </div>
              </div>
            </div>
          </div>

          {c.snapshot.typologies && c.snapshot.typologies.length > 0 && (
            <TypologyPanel
              matches={c.snapshot.typologies}
              caption={
                c.typology_code
                  ? `Primary playbook locked at open · ${c.typology_code}`
                  : undefined
              }
            />
          )}

          <CaseNetworkPanel
            caseId={c.id}
            accountId={c.account_id}
          />

          {c.snapshot.sanctions_hits.length > 0 && (
            <div className="rounded-2xl border border-rose-400/25 bg-rose-500/[0.04] p-4">
              <div className="flex items-baseline justify-between">
                <div className="label !mb-0 text-rose-300">
                  Sanctions hits · {c.snapshot.sanctions_hits.length}
                </div>
                <span className="font-mono text-[11px] text-white/45">
                  frozen at triage
                </span>
              </div>
              <div className="mt-3 grid gap-3 md:grid-cols-2">
                {c.snapshot.sanctions_hits.map((h, i) => (
                  <div
                    key={i}
                    className="flex items-start gap-3 rounded-xl border border-white/10 bg-black/30 p-3"
                  >
                    <SimilarityRing similarity={h.similarity} grade={h.grade} size={62} />
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span
                          className={`inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-[10px] uppercase tracking-wider ${GRADE_TINT[h.grade]}`}
                        >
                          {h.grade}
                        </span>
                        <span className="font-mono text-[10.5px] text-white/55">
                          {h.list} · {h.jurisdiction}
                        </span>
                        <span className="rounded-md border border-white/10 bg-white/[0.04] px-1.5 py-0.5 font-mono text-[10px] text-white/55">
                          {h.queried_role}
                        </span>
                      </div>
                      <div className="mt-1.5 truncate text-[13px] font-semibold tracking-tight">
                        {h.name}
                      </div>
                      <div className="mt-0.5 truncate text-[11.5px] text-white/55">
                        “{h.queried_name}” → matched on “{h.matched_alias}”
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* SAR */}
          {sarMd && (
            <div className="rounded-2xl border border-emerald-400/25 bg-emerald-500/[0.04] p-4">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <div className="label !mb-0 text-emerald-300">
                    SAR draft · {c.sar_id}
                  </div>
                  <div className="mt-0.5 text-[11px] text-white/55">
                    Filed {timeAgo(c.sar_filed_at_iso)} by{" "}
                    {sarEvent?.actor ?? "analyst"}
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    className="btn-ghost"
                    onClick={() => navigator.clipboard.writeText(sarMd)}
                  >
                    Copy markdown
                  </button>
                  <button
                    className="btn"
                    onClick={() => setOpenSar((v) => !v)}
                  >
                    {openSar ? "Collapse" : "View report"}
                  </button>
                </div>
              </div>
              {openSar && (
                <pre className="scroll-thin mt-3 max-h-[420px] overflow-auto whitespace-pre-wrap rounded-lg bg-black/40 p-3 font-mono text-[12px] text-white/85">
                  {sarMd}
                </pre>
              )}
            </div>
          )}
        </div>

        {/* Right: workflow + timeline + composer */}
        <aside className="space-y-5">
          <div className="glass p-5">
            <div className="label">Assignment</div>
            <div className="flex items-center gap-2">
              <input
                value={assignVal}
                onChange={(e) => setAssignVal(e.target.value)}
                placeholder="analyst handle (e.g. alice)"
                className="input flex-1"
              />
              <button
                className="btn-primary"
                onClick={onAssign}
                disabled={
                  busyAction !== null ||
                  !actor.trim() ||
                  (assignVal.trim() === (c.assignee ?? "").trim())
                }
              >
                {busyAction === "assign"
                  ? "Saving…"
                  : assignVal.trim() === ""
                  ? "Unassign"
                  : "Assign"}
              </button>
            </div>
            {c.assignee && (
              <div className="mt-2 inline-flex items-center gap-2 text-[11.5px] text-white/65">
                <Avatar name={c.assignee} size={14} />
                <span>currently {c.assignee}</span>
              </div>
            )}
          </div>

          <div className="glass p-5">
            <div className="label">Add note to timeline</div>
            <div className="ws-composer space-y-2">
              <textarea
                value={noteBody}
                onChange={(e) => setNoteBody(e.target.value)}
                placeholder="What did you find? What's the next step?"
                rows={3}
                className="input"
              />
              <div className="flex items-center justify-between">
                <div className="text-[10.5px] text-white/40">
                  {noteBody.trim().length} chars · recorded with your handle
                </div>
                <button
                  className="btn-primary"
                  onClick={onAddNote}
                  disabled={
                    !noteBody.trim() || !actor.trim() || busyAction !== null
                  }
                >
                  {busyAction === "note" ? "Saving…" : "Append note"}
                </button>
              </div>
            </div>
          </div>

          <div className="glass p-5">
            <div className="flex items-baseline justify-between">
              <h2 className="text-[15px] font-semibold tracking-tight">
                Timeline
              </h2>
              <span className="font-mono text-[10.5px] text-white/40">
                {c.events.length} events
              </span>
            </div>
            <div className="mt-4">
              <Timeline events={c.events} />
            </div>
          </div>
        </aside>
      </section>

      {/* Footer hint to the queue */}
      <footer className="text-center text-[11px] text-white/40">
        case shape: <span className="font-mono">{c.id}</span> ·
        priority derived from{" "}
        <span className="font-mono">max(risk_score, sanctions·100)</span> ·
        SLA warn ≥{" "}
        <span className="font-mono">{(c.age_hours).toFixed(1)}h</span> against
        deployment thresholds.
      </footer>

      {sarBusy && (
        <div className="fixed bottom-6 right-6 glass-strong px-4 py-3 text-[12.5px] text-emerald-300">
          Generating SAR…
        </div>
      )}
    </div>
  );
}

function SmallStat({
  label,
  value,
  tone = "neutral",
}: {
  label: string;
  value: number | string;
  tone?: "neutral" | "rose";
}) {
  return (
    <div className="rounded-xl border border-white/10 bg-black/25 p-3">
      <div className="text-[10.5px] uppercase tracking-wider text-white/45">
        {label}
      </div>
      <div
        className={`mt-1 text-xl font-semibold tabular-nums ${
          tone === "rose" ? "text-rose-300" : "text-white"
        }`}
      >
        {value}
      </div>
    </div>
  );
}

function shortMoney(v: number | undefined): string {
  if (v == null || isNaN(v as number)) return "—";
  const n = v as number;
  if (Math.abs(n) >= 1e7) return `₹${(n / 1e7).toFixed(1)}cr`;
  if (Math.abs(n) >= 1e5) return `₹${(n / 1e5).toFixed(1)}L`;
  if (Math.abs(n) >= 1e3) return `₹${(n / 1e3).toFixed(1)}k`;
  return `₹${n.toFixed(0)}`;
}

function timeAgo(iso: string | null | undefined): string {
  if (!iso) return "—";
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return iso;
  const diff = Date.now() - t;
  const m = Math.floor(diff / 60_000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.floor(h / 24);
  if (d < 14) return `${d}d ago`;
  return new Date(t).toLocaleDateString();
}
