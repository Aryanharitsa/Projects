"""TITAN AML case management.

Turns alert-shaped account reports into actionable cases that an analyst
walks through a real workflow:

    open → review → (cleared | escalated | sar_filed)
      ↑                                ↓
      └──────────  reopen  ────────────┘

Persistence is plain ``sqlite3`` — one process-wide lock, idempotent
schema bootstrap at import time, JSON columns for the snapshot payloads
that don't need to be queried (factors, sanctions hits, edges) and
indexed scalar mirrors for everything we filter on (priority, status,
assignee, age).

The store is intentionally append-only for *evidence* and *events* —
the timeline is the audit trail. Status changes don't mutate prior
events; they emit new ones. That keeps the case auditable end-to-end
without a separate journal table.

Design notes
------------
- A case is opened from a frozen snapshot of the score response. If the
  raw transactions change later, the case still reflects what the
  analyst saw at triage time — which is what regulators care about.
- Priority is computed from the snapshot once at open-time and re-derived
  on transition; we don't trust callers to set it.
- SLA breach is a derived property (now − opened_at vs threshold).
- The `auto_open` flow: ``bulk_open_from_score`` walks a /aml/score
  response and opens one case per account whose band is at or above
  ``min_band``. Existing OPEN cases are not duplicated for the same
  account in the same calendar day (idempotency key).

This module is import-safe: the SQLite file lives at
``apps/ai-aml/data/cases.sqlite3`` and is created on first call.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_HERE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get(
    "TITAN_CASES_DB_PATH",
    os.path.join(_HERE, "data", "cases.sqlite3"),
)

# Workflow vocabulary — kept short on purpose. UI labels live in the
# frontend; this module ships only canonical machine values.
STATUSES: Tuple[str, ...] = (
    "open",
    "review",
    "cleared",
    "escalated",
    "sar_filed",
)
TERMINAL_STATUSES: Tuple[str, ...] = ("cleared", "sar_filed")

# Each transition is allowed from a defined set of "from" states so the
# graph stays inspectable. ``reopen`` collapses any terminal back to
# ``review`` so the analyst can resume work.
TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    "review": ("open",),
    "cleared": ("open", "review", "escalated"),
    "escalated": ("open", "review"),
    "sar_filed": ("open", "review", "escalated"),
    "reopen": ("cleared", "escalated", "sar_filed"),
}

PRIORITIES: Tuple[str, ...] = ("critical", "high", "medium", "low")

# Priority bands by composite alert score. ``alert_score`` is
# max(risk_score, sanctions_intensity*100) — sanctions hits force
# critical even on otherwise quiet accounts.
def _priority_for(alert_score: float) -> str:
    if alert_score >= 80:
        return "critical"
    if alert_score >= 60:
        return "high"
    if alert_score >= 30:
        return "medium"
    return "low"


# SLA windows in hours. Tweak via env if a deployment has stricter
# regulatory clocks (FIU-IND is 7 days for STRs, but in-house triage
# wants something tighter; defaults match a typical L1/L2 ops cadence).
SLA_WARN_HOURS = float(os.environ.get("TITAN_CASE_SLA_WARN_HOURS", "24"))
SLA_BREACH_HOURS = float(os.environ.get("TITAN_CASE_SLA_BREACH_HOURS", "72"))


# ---------------------------------------------------------------------------
# Schema bootstrap
# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS cases (
    id              TEXT PRIMARY KEY,
    account_id      TEXT NOT NULL,
    display_name    TEXT,
    status          TEXT NOT NULL,
    priority        TEXT NOT NULL,
    risk_score      REAL NOT NULL,
    band            TEXT NOT NULL,
    alert_score     REAL NOT NULL,
    sanctions_count INTEGER NOT NULL DEFAULT 0,
    fired_count     INTEGER NOT NULL DEFAULT 0,
    assignee        TEXT,
    opened_by       TEXT NOT NULL,
    opened_at       REAL NOT NULL,
    last_event_at   REAL NOT NULL,
    closed_at       REAL,
    sar_id          TEXT,
    sar_filed_at    REAL,
    snapshot_json   TEXT NOT NULL,
    summary         TEXT
);

CREATE INDEX IF NOT EXISTS idx_cases_status   ON cases(status);
CREATE INDEX IF NOT EXISTS idx_cases_priority ON cases(priority);
CREATE INDEX IF NOT EXISTS idx_cases_assignee ON cases(assignee);
CREATE INDEX IF NOT EXISTS idx_cases_opened   ON cases(opened_at DESC);
CREATE INDEX IF NOT EXISTS idx_cases_account  ON cases(account_id);

CREATE TABLE IF NOT EXISTS case_events (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id       TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    type          TEXT NOT NULL,        -- opened | assigned | note | status | sar | reopened
    actor         TEXT NOT NULL,
    body          TEXT,
    from_status   TEXT,
    to_status     TEXT,
    payload_json  TEXT,
    created_at    REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_case_events_case
    ON case_events(case_id, created_at);

CREATE TABLE IF NOT EXISTS case_transactions (
    case_id           TEXT PRIMARY KEY REFERENCES cases(id) ON DELETE CASCADE,
    transactions_json TEXT NOT NULL,
    tx_count          INTEGER NOT NULL DEFAULT 0,
    counterparty_count INTEGER NOT NULL DEFAULT 0,
    weights_json      TEXT,
    sanctions_threshold REAL,
    created_at        REAL NOT NULL
);
"""

# Cap per-case transaction snapshots so a noisy account with thousands of
# hits doesn't bloat the SQLite row. We always keep 1-hop neighbourhood
# (transactions touching the subject *or* its direct counterparties) and
# truncate by recency when over budget. The cap is high enough that the
# subgraph re-analysis still produces a stable propagated picture.
CASE_TX_SNAPSHOT_CAP = int(os.environ.get("TITAN_CASE_TX_SNAPSHOT_CAP", "1500"))


_lock = threading.Lock()
_initialized = False


def _connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=8.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def _init_db() -> None:
    global _initialized
    if _initialized:
        return
    with _lock:
        if _initialized:
            return
        conn = _connect()
        try:
            conn.executescript(_SCHEMA)
            conn.commit()
        finally:
            conn.close()
        _initialized = True


_init_db()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now() -> float:
    return datetime.now(timezone.utc).timestamp()


def _iso(ts: Optional[float]) -> Optional[str]:
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _new_id(account_id: str, ts: float) -> str:
    h = hashlib.sha256(f"{account_id}|{ts}|{uuid.uuid4()}".encode()).hexdigest()
    return "CASE-" + h[:10].upper()


def _alert_score(account_report: Dict[str, Any]) -> float:
    """Composite triage score: max of risk and the strongest sanctions hit.

    Sanctions hits ride a separate axis — a score of 18 on the AML side
    plus a 0.95 sanctions match should still be critical, because the
    sanctions axis dominates the workflow even when transaction patterns
    look quiet.
    """
    rs = float(account_report.get("risk_score") or 0.0)
    hits = account_report.get("sanctions_hits") or []
    sanc_pct = max((float(h.get("similarity") or 0.0) * 100.0 for h in hits), default=0.0)
    return max(rs, sanc_pct)


def _summarise(account_report: Dict[str, Any]) -> str:
    """One-line, human-readable case summary used in queue cards."""
    factors = [f for f in (account_report.get("factors") or []) if (f.get("points") or 0) > 0]
    factors.sort(key=lambda f: f.get("points") or 0, reverse=True)
    top_names = [f.get("name") for f in factors[:3] if f.get("name")]
    hits = account_report.get("sanctions_hits") or []
    parts: List[str] = []
    if top_names:
        parts.append(", ".join(top_names))
    if hits:
        parts.append(f"{len(hits)} sanctions hit{'s' if len(hits) != 1 else ''}")
    if not parts:
        parts.append("no factors fired")
    return " · ".join(parts)


def _row_to_case(row: sqlite3.Row, *, with_snapshot: bool = False) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "id": row["id"],
        "account_id": row["account_id"],
        "display_name": row["display_name"] or "",
        "status": row["status"],
        "priority": row["priority"],
        "risk_score": row["risk_score"],
        "band": row["band"],
        "alert_score": row["alert_score"],
        "sanctions_count": row["sanctions_count"],
        "fired_count": row["fired_count"],
        "assignee": row["assignee"],
        "opened_by": row["opened_by"],
        "opened_at": row["opened_at"],
        "opened_at_iso": _iso(row["opened_at"]),
        "last_event_at": row["last_event_at"],
        "last_event_at_iso": _iso(row["last_event_at"]),
        "closed_at": row["closed_at"],
        "closed_at_iso": _iso(row["closed_at"]),
        "sar_id": row["sar_id"],
        "sar_filed_at": row["sar_filed_at"],
        "sar_filed_at_iso": _iso(row["sar_filed_at"]),
        "summary": row["summary"] or "",
        "age_hours": _age_hours(row["opened_at"], row["closed_at"]),
        "sla": _sla_state(row["opened_at"], row["closed_at"]),
    }
    if with_snapshot:
        try:
            out["snapshot"] = json.loads(row["snapshot_json"]) if row["snapshot_json"] else {}
        except (TypeError, json.JSONDecodeError):
            out["snapshot"] = {}
    return out


def _age_hours(opened_at: float, closed_at: Optional[float]) -> float:
    end = closed_at if closed_at else _now()
    return round((end - opened_at) / 3600.0, 2)


def _sla_state(opened_at: float, closed_at: Optional[float]) -> str:
    """ok | warn | breach. Closed cases keep their last live state so
    auditors can see whether closure beat the clock.
    """
    age = _age_hours(opened_at, closed_at)
    if age >= SLA_BREACH_HOURS:
        return "breach"
    if age >= SLA_WARN_HOURS:
        return "warn"
    return "ok"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def open_case(
    account_report: Dict[str, Any],
    *,
    opened_by: str = "TITAN-AUTOMATED",
    note: Optional[str] = None,
    transactions: Optional[List[Dict[str, Any]]] = None,
    weights: Optional[Dict[str, float]] = None,
    sanctions_threshold: Optional[float] = None,
) -> Dict[str, Any]:
    """Open a fresh case from a frozen account report snapshot.

    If ``transactions`` is supplied, the 1-hop neighbourhood around
    ``account_id`` is snapshotted into the ``case_transactions`` table so
    the case detail's network panel can re-run analysis later without the
    caller having to re-supply the original batch.
    """
    if "account_id" not in account_report:
        raise ValueError("account_report.account_id required")

    now = _now()
    aid = str(account_report["account_id"])

    # Idempotency per (account_id, calendar UTC day, OPEN/REVIEW). If an
    # active case exists for this account today, return it instead of
    # creating a duplicate. Closed cases are always allowed to re-open
    # as new cases (the workflow resets).
    existing = _existing_active_case(aid, now)
    if existing:
        # If the caller now has transactions and the existing case didn't
        # capture them, upgrade the snapshot — useful when the AML console
        # re-promotes the same account with the input CSV attached.
        if transactions and not _has_tx_snapshot(existing["id"]):
            try:
                _save_tx_snapshot(
                    existing["id"], aid, transactions,
                    weights=weights, sanctions_threshold=sanctions_threshold,
                )
            except Exception:
                pass
        return existing

    alert = _alert_score(account_report)
    priority = _priority_for(alert)
    summary = _summarise(account_report)
    factors = account_report.get("factors") or []
    fired = sum(1 for f in factors if (f.get("points") or 0) > 0)
    hits = account_report.get("sanctions_hits") or []

    cid = _new_id(aid, now)
    snapshot_json = json.dumps(_minimal_snapshot(account_report), separators=(",", ":"))

    with _lock:
        conn = _connect()
        try:
            conn.execute(
                """
                INSERT INTO cases (
                    id, account_id, display_name, status, priority,
                    risk_score, band, alert_score, sanctions_count, fired_count,
                    assignee, opened_by, opened_at, last_event_at,
                    snapshot_json, summary
                )
                VALUES (?, ?, ?, 'open', ?,
                        ?, ?, ?, ?, ?,
                        NULL, ?, ?, ?,
                        ?, ?)
                """,
                (
                    cid, aid, account_report.get("display_name") or "", priority,
                    float(account_report.get("risk_score") or 0.0),
                    str(account_report.get("band") or "low"),
                    alert, len(hits), fired,
                    opened_by, now, now,
                    snapshot_json, summary,
                ),
            )
            _emit_event(
                conn, cid, "opened", opened_by,
                body=note or f"Auto-opened from snapshot at {priority} priority.",
                payload={"alert_score": alert, "priority": priority, "fired": fired,
                         "sanctions_count": len(hits)},
                ts=now,
            )
            conn.commit()
            case = _row_to_case(conn.execute("SELECT * FROM cases WHERE id=?", (cid,)).fetchone())
        finally:
            conn.close()

    # Snapshot transactions outside the open() transaction — failures
    # here are non-fatal (the case is still openable, the network panel
    # just degrades to a "no transactions snapshotted" state).
    if transactions:
        try:
            _save_tx_snapshot(
                cid, aid, transactions,
                weights=weights, sanctions_threshold=sanctions_threshold,
            )
        except Exception:
            pass
    return case


def bulk_open_from_score(
    score_response: Dict[str, Any],
    *,
    min_priority: str = "medium",
    opened_by: str = "TITAN-AUTOMATED",
    transactions: Optional[List[Dict[str, Any]]] = None,
    weights: Optional[Dict[str, float]] = None,
    sanctions_threshold: Optional[float] = None,
) -> Dict[str, Any]:
    """Walk a /aml/score response, open one case per qualifying account.

    `min_priority` filters by the *case priority* (derived from
    alert_score), not the raw band — so a sanctions hit on a low-risk
    account still surfaces.

    If ``transactions`` is supplied, each opened case persists a
    1-hop-neighbourhood snapshot of that batch so the case-detail
    network panel can run analysis without re-supplying the input.
    """
    accounts = score_response.get("accounts") or []
    threshold = PRIORITIES.index(min_priority) if min_priority in PRIORITIES else 2
    opened: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    snapshotted = 0
    for acc in accounts:
        alert = _alert_score(acc)
        prio = _priority_for(alert)
        if PRIORITIES.index(prio) > threshold:
            skipped.append({"account_id": acc.get("account_id"), "reason": "below_threshold",
                            "priority": prio})
            continue
        case = open_case(
            acc, opened_by=opened_by,
            transactions=transactions,
            weights=weights,
            sanctions_threshold=sanctions_threshold,
        )
        opened.append(case)
        if transactions:
            snapshotted += 1
    return {
        "opened": opened,
        "skipped": skipped,
        "total_accounts": len(accounts),
        "min_priority": min_priority,
        "snapshotted": snapshotted,
    }


def list_cases(
    *,
    status: Optional[str] = None,
    statuses: Optional[Iterable[str]] = None,
    priority: Optional[str] = None,
    assignee: Optional[str] = None,
    account_id: Optional[str] = None,
    q: Optional[str] = None,
    sla: Optional[str] = None,
    limit: int = 200,
    offset: int = 0,
    include_closed: bool = True,
) -> Dict[str, Any]:
    """Query the case queue. All filters AND together."""
    sql = ["SELECT * FROM cases WHERE 1=1"]
    args: List[Any] = []
    if status:
        sql.append("AND status = ?"); args.append(status)
    elif statuses:
        st = list(statuses)
        if st:
            sql.append("AND status IN (" + ",".join(["?"] * len(st)) + ")")
            args.extend(st)
    if not include_closed:
        sql.append("AND status NOT IN ('cleared','sar_filed')")
    if priority:
        sql.append("AND priority = ?"); args.append(priority)
    if assignee:
        if assignee == "__unassigned__":
            sql.append("AND (assignee IS NULL OR assignee = '')")
        else:
            sql.append("AND assignee = ?"); args.append(assignee)
    if account_id:
        sql.append("AND account_id = ?"); args.append(account_id)
    if q:
        like = f"%{q.lower()}%"
        sql.append("AND (LOWER(account_id) LIKE ? OR LOWER(display_name) LIKE ? OR LOWER(summary) LIKE ?)")
        args.extend([like, like, like])

    sql.append(
        "ORDER BY "
        "CASE priority WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END, "
        "opened_at ASC "
        "LIMIT ? OFFSET ?"
    )
    args.extend([limit, offset])

    conn = _connect()
    try:
        rows = conn.execute(" ".join(sql), args).fetchall()
        cases = [_row_to_case(r) for r in rows]
    finally:
        conn.close()

    if sla:
        cases = [c for c in cases if c["sla"] == sla]

    return {"cases": cases, "count": len(cases), "limit": limit, "offset": offset}


def get_case(case_id: str, *, with_events: bool = True) -> Optional[Dict[str, Any]]:
    conn = _connect()
    try:
        row = conn.execute("SELECT * FROM cases WHERE id=?", (case_id,)).fetchone()
        if not row:
            return None
        case = _row_to_case(row, with_snapshot=True)
        if with_events:
            ev = conn.execute(
                "SELECT * FROM case_events WHERE case_id=? ORDER BY created_at ASC, id ASC",
                (case_id,),
            ).fetchall()
            case["events"] = [_event_to_dict(e) for e in ev]
        return case
    finally:
        conn.close()


def transition(
    case_id: str,
    *,
    to_status: str,
    actor: str,
    note: Optional[str] = None,
) -> Dict[str, Any]:
    """Move a case along the workflow graph."""
    if to_status not in (set(STATUSES) | {"reopen"}):
        raise ValueError(f"unknown status: {to_status}")

    conn = _connect()
    try:
        with _lock:
            row = conn.execute("SELECT * FROM cases WHERE id=?", (case_id,)).fetchone()
            if not row:
                raise KeyError(case_id)
            current = row["status"]

            if to_status == "reopen":
                if current not in TRANSITIONS["reopen"]:
                    raise ValueError(f"cannot reopen from {current}")
                next_status = "review"
                ev_type = "reopened"
            else:
                allowed = TRANSITIONS.get(to_status, ())
                if current == to_status:
                    raise ValueError(f"already {to_status}")
                if current not in allowed:
                    raise ValueError(f"cannot transition {current} → {to_status}")
                next_status = to_status
                ev_type = "status"

            now = _now()
            closed_at = now if next_status in TERMINAL_STATUSES else None
            # If we're reopening from a terminal, clear the closure stamp.
            clear_closed = current in TERMINAL_STATUSES and next_status not in TERMINAL_STATUSES

            conn.execute(
                """
                UPDATE cases
                   SET status = ?, last_event_at = ?,
                       closed_at = CASE
                           WHEN ? IS NOT NULL THEN ?
                           WHEN ? = 1 THEN NULL
                           ELSE closed_at
                       END
                 WHERE id = ?
                """,
                (next_status, now, closed_at, closed_at, 1 if clear_closed else 0, case_id),
            )
            _emit_event(
                conn, case_id, ev_type, actor,
                body=note,
                from_status=current,
                to_status=next_status,
                ts=now,
            )
            conn.commit()
            row = conn.execute("SELECT * FROM cases WHERE id=?", (case_id,)).fetchone()
            return _row_to_case(row)
    finally:
        conn.close()


def assign(case_id: str, *, assignee: str, actor: str) -> Dict[str, Any]:
    assignee_clean = (assignee or "").strip()
    conn = _connect()
    try:
        with _lock:
            row = conn.execute("SELECT * FROM cases WHERE id=?", (case_id,)).fetchone()
            if not row:
                raise KeyError(case_id)
            previous = row["assignee"]
            now = _now()
            conn.execute(
                "UPDATE cases SET assignee=?, last_event_at=? WHERE id=?",
                (assignee_clean or None, now, case_id),
            )
            _emit_event(
                conn, case_id, "assigned", actor,
                body=(f"Assigned to {assignee_clean}" if assignee_clean
                      else f"Unassigned (was {previous or '—'})"),
                payload={"from": previous, "to": assignee_clean or None},
                ts=now,
            )
            conn.commit()
            return _row_to_case(conn.execute("SELECT * FROM cases WHERE id=?", (case_id,)).fetchone())
    finally:
        conn.close()


def add_note(case_id: str, *, actor: str, body: str) -> Dict[str, Any]:
    body = (body or "").strip()
    if not body:
        raise ValueError("note body is empty")
    conn = _connect()
    try:
        with _lock:
            row = conn.execute("SELECT * FROM cases WHERE id=?", (case_id,)).fetchone()
            if not row:
                raise KeyError(case_id)
            now = _now()
            conn.execute("UPDATE cases SET last_event_at=? WHERE id=?", (now, case_id))
            event = _emit_event(conn, case_id, "note", actor, body=body, ts=now)
            conn.commit()
            return event
    finally:
        conn.close()


def attach_sar(case_id: str, *, sar: Dict[str, Any], actor: str) -> Dict[str, Any]:
    """Attach a SAR draft and transition to ``sar_filed``.

    The SAR's ``narrative_md`` and ``structured`` payload are stored on
    the latest event so the case detail can render the report inline.
    """
    if "sar_id" not in sar:
        raise ValueError("sar.sar_id required")

    conn = _connect()
    try:
        with _lock:
            row = conn.execute("SELECT * FROM cases WHERE id=?", (case_id,)).fetchone()
            if not row:
                raise KeyError(case_id)
            current = row["status"]
            if current not in TRANSITIONS["sar_filed"]:
                raise ValueError(f"cannot file SAR from {current}")
            now = _now()
            conn.execute(
                "UPDATE cases SET status='sar_filed', sar_id=?, sar_filed_at=?, "
                "closed_at=?, last_event_at=? WHERE id=?",
                (sar["sar_id"], now, now, now, case_id),
            )
            _emit_event(
                conn, case_id, "sar", actor,
                body=f"SAR draft {sar['sar_id']} filed.",
                from_status=current, to_status="sar_filed",
                payload={
                    "sar_id": sar["sar_id"],
                    "narrative_md": sar.get("narrative_md"),
                    "filed_at": sar.get("filed_at"),
                    "analyst": sar.get("analyst"),
                },
                ts=now,
            )
            conn.commit()
            return _row_to_case(
                conn.execute("SELECT * FROM cases WHERE id=?", (case_id,)).fetchone()
            )
    finally:
        conn.close()


def delete_case(case_id: str) -> bool:
    conn = _connect()
    try:
        with _lock:
            conn.execute("DELETE FROM case_transactions WHERE case_id=?", (case_id,))
            cur = conn.execute("DELETE FROM cases WHERE id=?", (case_id,))
            conn.commit()
            return cur.rowcount > 0
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Transaction snapshots — feed the case-detail network panel
# ---------------------------------------------------------------------------


def _has_tx_snapshot(case_id: str) -> bool:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT 1 FROM case_transactions WHERE case_id=?", (case_id,),
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def _slice_neighbourhood(
    account_id: str,
    transactions: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Keep transactions touching ``account_id`` or any of its 1-hop
    counterparties. Truncate by recency (lexicographic ISO timestamp) when
    over ``CASE_TX_SNAPSHOT_CAP`` so noisy accounts don't blow up storage.
    """
    aid = str(account_id)
    direct: Set[str] = {aid}
    # First pass: find direct counterparties.
    for r in transactions:
        if str(r.get("account_id")) == aid:
            cp = r.get("counterparty")
            if cp is not None:
                direct.add(str(cp))
        elif str(r.get("counterparty")) == aid:
            cp = r.get("account_id")
            if cp is not None:
                direct.add(str(cp))
    # Second pass: any tx where both endpoints are in the direct set OR
    # one endpoint is the subject.
    kept: List[Dict[str, Any]] = []
    for r in transactions:
        a = str(r.get("account_id") or "")
        b = str(r.get("counterparty") or "")
        if a == aid or b == aid:
            kept.append(r)
        elif a in direct and b in direct:
            kept.append(r)
    if len(kept) <= CASE_TX_SNAPSHOT_CAP:
        return kept
    # Most-recent-first truncation. Falls back to original order if
    # timestamps are missing/unparseable.
    def _key(row: Dict[str, Any]) -> str:
        return str(row.get("timestamp") or "")
    kept.sort(key=_key, reverse=True)
    return kept[:CASE_TX_SNAPSHOT_CAP]


def _save_tx_snapshot(
    case_id: str,
    account_id: str,
    transactions: List[Dict[str, Any]],
    *,
    weights: Optional[Dict[str, float]] = None,
    sanctions_threshold: Optional[float] = None,
) -> Dict[str, Any]:
    sliced = _slice_neighbourhood(account_id, transactions or [])
    cps: Set[str] = set()
    for r in sliced:
        for k in ("account_id", "counterparty"):
            v = r.get(k)
            if v is not None:
                cps.add(str(v))
    payload = json.dumps(sliced, separators=(",", ":"))
    weights_json = json.dumps(weights, separators=(",", ":")) if weights else None
    with _lock:
        conn = _connect()
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO case_transactions
                    (case_id, transactions_json, tx_count, counterparty_count,
                     weights_json, sanctions_threshold, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (case_id, payload, len(sliced), len(cps),
                 weights_json, sanctions_threshold, _now()),
            )
            conn.commit()
        finally:
            conn.close()
    return {
        "case_id": case_id,
        "tx_count": len(sliced),
        "counterparty_count": len(cps),
    }


def get_case_transactions(case_id: str) -> Optional[Dict[str, Any]]:
    """Return the persisted neighbourhood snapshot, or None if absent."""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT * FROM case_transactions WHERE case_id=?", (case_id,),
        ).fetchone()
        if not row:
            return None
        try:
            txs = json.loads(row["transactions_json"]) if row["transactions_json"] else []
        except json.JSONDecodeError:
            txs = []
        try:
            wts = json.loads(row["weights_json"]) if row["weights_json"] else None
        except json.JSONDecodeError:
            wts = None
        return {
            "case_id": row["case_id"],
            "transactions": txs,
            "tx_count": row["tx_count"],
            "counterparty_count": row["counterparty_count"],
            "weights": wts,
            "sanctions_threshold": row["sanctions_threshold"],
            "created_at": row["created_at"],
            "created_at_iso": _iso(row["created_at"]),
        }
    finally:
        conn.close()


def stats() -> Dict[str, Any]:
    """Dashboard tiles + per-priority + assignee throughput."""
    conn = _connect()
    try:
        rows = conn.execute("SELECT * FROM cases").fetchall()
    finally:
        conn.close()

    by_status: Dict[str, int] = {s: 0 for s in STATUSES}
    by_priority: Dict[str, int] = {p: 0 for p in PRIORITIES}
    by_sla: Dict[str, int] = {"ok": 0, "warn": 0, "breach": 0}
    by_assignee: Dict[str, int] = {}
    open_total = 0
    closed_total = 0
    age_sum = 0.0
    open_count_for_age = 0

    for r in rows:
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1
        by_priority[r["priority"]] = by_priority.get(r["priority"], 0) + 1
        if r["status"] in TERMINAL_STATUSES:
            closed_total += 1
        else:
            open_total += 1
            sla = _sla_state(r["opened_at"], r["closed_at"])
            by_sla[sla] = by_sla.get(sla, 0) + 1
            age_sum += _age_hours(r["opened_at"], r["closed_at"])
            open_count_for_age += 1
        if r["assignee"]:
            by_assignee[r["assignee"]] = by_assignee.get(r["assignee"], 0) + 1

    avg_age = round(age_sum / open_count_for_age, 2) if open_count_for_age else 0.0
    return {
        "total": len(rows),
        "open_total": open_total,
        "closed_total": closed_total,
        "by_status": by_status,
        "by_priority": by_priority,
        "by_sla": by_sla,
        "avg_open_age_hours": avg_age,
        "by_assignee": by_assignee,
        "sla_thresholds": {"warn_hours": SLA_WARN_HOURS, "breach_hours": SLA_BREACH_HOURS},
    }


def assignees() -> List[str]:
    """Distinct list of assignees observed in the store (for filter UI)."""
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT DISTINCT assignee FROM cases WHERE assignee IS NOT NULL AND assignee <> '' "
            "ORDER BY assignee ASC"
        ).fetchall()
        return [r["assignee"] for r in rows]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _emit_event(
    conn: sqlite3.Connection,
    case_id: str,
    type_: str,
    actor: str,
    *,
    body: Optional[str] = None,
    from_status: Optional[str] = None,
    to_status: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
    ts: Optional[float] = None,
) -> Dict[str, Any]:
    now = ts if ts is not None else _now()
    payload_json = json.dumps(payload, separators=(",", ":")) if payload else None
    cur = conn.execute(
        """
        INSERT INTO case_events (case_id, type, actor, body, from_status, to_status, payload_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (case_id, type_, actor, body, from_status, to_status, payload_json, now),
    )
    return {
        "id": cur.lastrowid,
        "case_id": case_id,
        "type": type_,
        "actor": actor,
        "body": body,
        "from_status": from_status,
        "to_status": to_status,
        "payload": payload,
        "created_at": now,
        "created_at_iso": _iso(now),
    }


def _event_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    payload = None
    if row["payload_json"]:
        try:
            payload = json.loads(row["payload_json"])
        except json.JSONDecodeError:
            payload = None
    return {
        "id": row["id"],
        "case_id": row["case_id"],
        "type": row["type"],
        "actor": row["actor"],
        "body": row["body"],
        "from_status": row["from_status"],
        "to_status": row["to_status"],
        "payload": payload,
        "created_at": row["created_at"],
        "created_at_iso": _iso(row["created_at"]),
    }


def _existing_active_case(account_id: str, ts: float) -> Optional[Dict[str, Any]]:
    """Return the most recent OPEN/REVIEW case for an account opened today.

    Sliding window is calendar UTC day. If a case was already opened
    automatically earlier in the day, we return it untouched — the
    operator can promote a duplicate manually if they really need to.
    """
    day_start = datetime.fromtimestamp(ts, tz=timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    ).timestamp()
    conn = _connect()
    try:
        row = conn.execute(
            """
            SELECT * FROM cases
             WHERE account_id = ?
               AND status IN ('open','review','escalated')
               AND opened_at >= ?
             ORDER BY opened_at DESC LIMIT 1
            """,
            (account_id, day_start),
        ).fetchone()
        return _row_to_case(row) if row else None
    finally:
        conn.close()


def _minimal_snapshot(account_report: Dict[str, Any]) -> Dict[str, Any]:
    """Trim the snapshot to what the case detail needs.

    Keeps factors (with evidence), sanctions_hits, edges (capped at 64
    rows so a noisy account doesn't blow up the row), and totals. Drops
    nothing else — the snapshot *is* the audit trail of what triage saw.
    """
    edges = list(account_report.get("edges") or [])[:64]
    return {
        "account_id": account_report.get("account_id"),
        "display_name": account_report.get("display_name"),
        "risk_score": account_report.get("risk_score"),
        "band": account_report.get("band"),
        "factors": account_report.get("factors") or [],
        "sanctions_hits": account_report.get("sanctions_hits") or [],
        "edges": edges,
        "counterparty_count": account_report.get("counterparty_count"),
        "inbound_total": account_report.get("inbound_total"),
        "outbound_total": account_report.get("outbound_total"),
    }


__all__ = [
    "STATUSES", "TERMINAL_STATUSES", "TRANSITIONS", "PRIORITIES",
    "SLA_WARN_HOURS", "SLA_BREACH_HOURS", "CASE_TX_SNAPSHOT_CAP",
    "open_case", "bulk_open_from_score", "list_cases", "get_case",
    "transition", "assign", "add_note", "attach_sar", "delete_case",
    "stats", "assignees", "get_case_transactions",
]
