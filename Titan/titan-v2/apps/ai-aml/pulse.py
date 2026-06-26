"""TITAN Pulse — the compliance officer's morning brief.

Round-13, day-60. Pulse is the *temporal-delta* lens TITAN was missing —
every prior surface up to Day 55 is a snapshot of *right now*:

* ``risk`` and ``typology`` score one batch
* ``profile`` composites every per-customer surface into one number
* ``cases`` queues alerts for triage
* ``network`` propagates risk across counterparties
* ``peer`` scores cohort outliers
* ``drift`` catches *account-vs-self* movement
* ``media`` / ``sanctions`` answer screen-time questions

None of them answer the question an MLRO actually opens Monday with:
*"across my whole customer book, what's different since yesterday, and
what should I look at FIRST before lunch?"*. Pulse is that brief — a
**composer** with no engine of its own: it reads the persisted
``profile_history`` table for each customer's prior composite, reads
the ``cases`` store for fresh openings + SLA breaches, computes per-customer
deltas, ranks customers by a deterministic "signal" formula, drafts a
plain-English change-log + plan-of-day, and ships a markdown brief that
pastes into Slack/email.

Pure-function: same `(profiles, cases, now, window_days)` in → identical
bytes out. No ML, no probabilistic drift to explain to a regulator. Every
threshold lives in the constants block below and is exposed via
``GET /aml/pulse/rules`` so auditors can sanity-check the engine before it
ships.

The rotation deliberately ships the same "Pulse" surface across three
projects (WaySafe Day 56 → SynapseOS Day 59 → TITAN Day 60). Different
domains, same vital-signs metaphor: a single hero card that tells you the
mood, the biggest mover, what changed, and what to do about it.

Composition
-----------
For every customer in the portfolio we look up their persisted profile
(from ``profile.list_profiles``) and the most recent history row from
*before* the window (``profile_history.refreshed_at < window_start``).
That gives a clean signed delta without needing a separate prior snapshot:

    composite_delta = composite_now − composite_prior
    band_shift      = (bucket_prior → bucket_now)  iff different
    refresh_status  = current / due_soon / overdue (recomputed live)

For cases we filter ``opened_at >= window_start`` for "fresh" cases and
``status NOT IN (cleared, sar_filed) AND sla == 'breach'`` for breaches.
A customer's case lift is the count of their owned accounts' open cases
that are at or above ``CASE_FRESH_PRIORITY`` (default "high").

Per-customer signal (used to rank the "biggest movers" panel):

    signal = abs(composite_delta) * 1.0
           + (bucket_upgraded) * 8
           + (new_cases_critical) * 6
           + (new_cases_high)     * 4
           + (open_breaches)      * 5
           + (refresh_overdue)    * 3
           + (composite_now >= 80) * 4    # critical floor bump

Mood ladder — first-match-wins across the *entire* portfolio:

    critical  any customer crossed INTO `critical` bucket
              OR any case SLA == breach
              OR any composite_now >= 90
    active    any band-shift up
              OR new_cases >= 3
              OR >= 2 customers up by >= 10 composite pts
    watch     any composite up by >= 5
              OR any new high/critical case
              OR refresh_overdue >= 1
    calm      otherwise

Headline: a one-line narrative composed from the dominant shape.

Plan-of-day: deterministic, prioritised checklist that *names* the other
TITAN tabs to open ("Cases", "Profile", "Sanctions", "Media") so the
brief stays operationally useful even when the analyst hasn't memorised
the URL structure.

Daily activity sparkline: per-day case-open counts across the window,
oldest-first so the UI draws left-to-right time.

Exports
-------
``serialize() -> dict`` returns a stable ``titan.pulse.v1`` envelope.
``to_markdown()`` returns a WhatsApp/email-shaped brief (headline,
key-metrics table, change-log, biggest movers, plan-of-day).

This module is import-safe: it depends only on ``profile`` and ``cases``
which are already initialised by ``main.py`` at module load.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

import cases as case_store
import profile as profile_engine


ENGINE_VERSION = "titan-pulse/1.0.0"
RULES_VERSION = "1.0.0"


# ---------------------------------------------------------------------------
# Tunables — exposed via GET /aml/pulse/rules so auditors can read them off.
# ---------------------------------------------------------------------------

DEFAULT_WINDOW_DAYS = 1
MAX_WINDOW_DAYS = 30
MIN_WINDOW_DAYS = 1

# A customer counts as a "mover" once their composite shifts by this much
# in the lookback window — keeps the panel from filling with noise from
# trivial recomputes.
COMPOSITE_DELTA_FLOOR = 5.0

# How many bullets the change-log and plan-of-day each cap at — both
# narratives intentionally truncate so the brief stays paste-able.
CHANGE_LOG_CAP = 10
PLAN_OF_DAY_CAP = 8
TOP_MOVERS_CAP = 6

# Mood-ladder thresholds.
CRITICAL_COMPOSITE_FLOOR = 90.0
ACTIVE_BIG_SHIFT_FLOOR = 10.0
ACTIVE_BIG_SHIFT_MIN_CUSTOMERS = 2
ACTIVE_NEW_CASES_FLOOR = 3
WATCH_SHIFT_FLOOR = 5.0

# Cases at or above this priority count as "fresh material" for plan-of-day.
FRESH_CASE_PRIORITIES = ("critical", "high")

# Signal weights (used to rank "biggest movers").
SIGNAL_WEIGHTS: Dict[str, float] = {
    "abs_delta":         1.0,
    "bucket_upgraded":   8.0,
    "new_case_critical": 6.0,
    "new_case_high":     4.0,
    "open_breach":       5.0,
    "refresh_overdue":   3.0,
    "critical_floor":    4.0,
}

# Mood metadata — colour + headline accent shared with the frontend's
# `.pulse-mood-*` classes.
MOOD_META: Dict[str, Dict[str, Any]] = {
    "calm":     {"accent": "#22d3a8", "label": "Calm morning",
                 "blurb":  "Portfolio quiet — routine monitoring."},
    "watch":    {"accent": "#fbbf24", "label": "Watch",
                 "blurb":  "Movement detected — skim the brief."},
    "active":   {"accent": "#fb923c", "label": "Active morning",
                 "blurb":  "Real movement — plan-of-day matters."},
    "critical": {"accent": "#ef4444", "label": "Critical morning",
                 "blurb":  "Escalations on deck — work the brief now."},
}

# Ordered list so callers can iterate severity ASC.
MOOD_ORDER: Tuple[str, ...] = ("calm", "watch", "active", "critical")


BUCKET_RANK: Dict[str, int] = {"low": 0, "medium": 1, "high": 2, "critical": 3}


# ---------------------------------------------------------------------------
# Domain types
# ---------------------------------------------------------------------------


@dataclass
class CustomerPulse:
    """One customer's signed delta vs the window-start snapshot."""

    customer_id: str
    display_name: str
    domicile: Optional[str]
    bucket: str
    bucket_prior: Optional[str]
    bucket_accent: str
    composite: float
    composite_prior: Optional[float]
    composite_delta: Optional[float]
    refresh_label: str
    refresh_days_to_due: Optional[float]
    open_case_count: int
    new_case_count: int
    new_case_critical: int
    new_case_high: int
    open_breach_count: int
    pep: bool
    products: List[str]
    headline: str
    change_lines: List[str]
    signal: float
    band_shift_direction: str  # "up" | "down" | "" — set when bucket changed
    is_biggest_mover: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "customer_id": self.customer_id,
            "display_name": self.display_name,
            "domicile": self.domicile,
            "bucket": self.bucket,
            "bucket_prior": self.bucket_prior,
            "bucket_accent": self.bucket_accent,
            "composite": round(self.composite, 1),
            "composite_prior": round(self.composite_prior, 1) if self.composite_prior is not None else None,
            "composite_delta": round(self.composite_delta, 1) if self.composite_delta is not None else None,
            "refresh_label": self.refresh_label,
            "refresh_days_to_due": (
                round(self.refresh_days_to_due, 1) if self.refresh_days_to_due is not None else None
            ),
            "open_case_count": self.open_case_count,
            "new_case_count": self.new_case_count,
            "new_case_critical": self.new_case_critical,
            "new_case_high": self.new_case_high,
            "open_breach_count": self.open_breach_count,
            "pep": self.pep,
            "products": list(self.products),
            "headline": self.headline,
            "change_lines": list(self.change_lines),
            "signal": round(self.signal, 2),
            "band_shift_direction": self.band_shift_direction,
            "is_biggest_mover": self.is_biggest_mover,
        }


@dataclass
class PulseAction:
    """One bullet of plan-of-day."""

    kind: str       # case · profile · sanctions · media · refresh · escalate
    priority: str   # critical · high · medium · low
    body: str
    customer_id: Optional[str] = None
    href: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "priority": self.priority,
            "body": self.body,
            "customer_id": self.customer_id,
            "href": self.href,
        }


@dataclass
class PulseReport:
    engine: str
    rules_version: str
    computed_at: str
    window_days: int
    window_start: str
    now: str
    mood: str
    mood_accent: str
    mood_label: str
    mood_blurb: str
    headline: str
    advisory: str
    portfolio_size: int
    movers_count: int
    new_cases_total: int
    new_cases_critical: int
    open_breaches: int
    open_cases_total: int
    refresh_overdue: int
    refresh_due_soon: int
    by_bucket: Dict[str, int]
    by_bucket_prior: Dict[str, int]
    bucket_drift: Dict[str, int]              # bucket -> signed delta vs window-start
    activity_sparkline: List[Dict[str, Any]]  # [{date, new_cases, sla_breaches}]
    score_histogram: List[Dict[str, Any]]     # 10-bucket histogram across composites
    biggest_movers: List[CustomerPulse]
    change_log: List[str]
    plan_of_day: List[PulseAction]
    customers: List[CustomerPulse]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema": "titan.pulse.v1",
            "engine": self.engine,
            "rules_version": self.rules_version,
            "computed_at": self.computed_at,
            "window_days": self.window_days,
            "window_start": self.window_start,
            "now": self.now,
            "mood": self.mood,
            "mood_accent": self.mood_accent,
            "mood_label": self.mood_label,
            "mood_blurb": self.mood_blurb,
            "headline": self.headline,
            "advisory": self.advisory,
            "portfolio_size": self.portfolio_size,
            "movers_count": self.movers_count,
            "new_cases_total": self.new_cases_total,
            "new_cases_critical": self.new_cases_critical,
            "open_breaches": self.open_breaches,
            "open_cases_total": self.open_cases_total,
            "refresh_overdue": self.refresh_overdue,
            "refresh_due_soon": self.refresh_due_soon,
            "by_bucket": dict(self.by_bucket),
            "by_bucket_prior": dict(self.by_bucket_prior),
            "bucket_drift": dict(self.bucket_drift),
            "activity_sparkline": list(self.activity_sparkline),
            "score_histogram": list(self.score_histogram),
            "biggest_movers": [c.to_dict() for c in self.biggest_movers],
            "change_log": list(self.change_log),
            "plan_of_day": [a.to_dict() for a in self.plan_of_day],
            "customers": [c.to_dict() for c in self.customers],
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_iso(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _epoch(dt: Optional[datetime]) -> Optional[float]:
    return dt.timestamp() if dt else None


def _format_pts_delta(delta: Optional[float]) -> str:
    if delta is None or abs(delta) < 0.05:
        return "→ ±0"
    arrow = "▲" if delta > 0 else "▼"
    return f"{arrow} {delta:+.0f}".replace("+", "+").replace("-", "−")


def _bucket_emoji(bucket: str) -> str:
    return {
        "low": "🟢",
        "medium": "🟡",
        "high": "🟠",
        "critical": "🔴",
    }.get(bucket, "•")


def _prior_history_row(history: Iterable[Dict[str, Any]], cutoff: datetime) -> Optional[Dict[str, Any]]:
    """Return the most recent history row whose ``refreshed_at`` is strictly
    before ``cutoff``. ``history`` is expected DESC by time (the shape
    ``profile.get_profile`` ships). We scan linearly because the slice
    is small (capped at 64 rows per customer)."""
    for h in history or []:
        ts = _parse_iso(h.get("refreshed_at"))
        if ts and ts < cutoff:
            return h
    return None


# ---------------------------------------------------------------------------
# Per-customer signal + narrative
# ---------------------------------------------------------------------------


def _build_customer_pulse(
    profile: Dict[str, Any],
    *,
    cases_for_customer: List[Dict[str, Any]],
    window_start: datetime,
    now: datetime,
    sample_prior_overrides: Optional[Dict[str, Any]] = None,
) -> CustomerPulse:
    """Compose one customer's pulse from their current profile + history +
    case-store rows.

    ``sample_prior_overrides`` is used by the sample/demo endpoints — when
    the bundled fixture wants to *simulate* a prior composite without
    seeding fake history rows, the caller supplies ``{composite_prior,
    bucket_prior}`` and we treat that as the window-start snapshot.
    """

    customer = profile.get("customer") or {}
    cid = customer.get("customer_id") or profile.get("customer_id") or ""
    name = customer.get("display_name") or cid
    domicile = (customer.get("domicile") or None)

    bucket = profile.get("bucket") or "low"
    bucket_accent = profile.get("bucket_accent") or "#94a3b8"
    composite = float(profile.get("composite") or 0.0)

    # Prior composite — either from history (real data) or from override (fixture).
    composite_prior: Optional[float] = None
    bucket_prior: Optional[str] = None
    if sample_prior_overrides:
        if "composite_prior" in sample_prior_overrides:
            composite_prior = float(sample_prior_overrides["composite_prior"])
        if "bucket_prior" in sample_prior_overrides:
            bucket_prior = str(sample_prior_overrides["bucket_prior"])
    if composite_prior is None:
        prior = _prior_history_row(profile.get("history") or [], window_start)
        if prior:
            composite_prior = float(prior.get("composite") or 0.0)
            bucket_prior = prior.get("bucket")

    composite_delta: Optional[float] = None
    if composite_prior is not None:
        composite_delta = composite - composite_prior

    refresh = profile.get("refresh") or {}
    refresh_label = refresh.get("label") or "unscheduled"
    refresh_days = refresh.get("days_to_due")

    # Bucket up/down direction — only set when buckets differ.
    band_shift_direction = ""
    if bucket_prior and bucket_prior != bucket:
        rank_now = BUCKET_RANK.get(bucket, 0)
        rank_prior = BUCKET_RANK.get(bucket_prior, 0)
        band_shift_direction = "up" if rank_now > rank_prior else "down"

    # Case lift across the customer's accounts.
    open_case_count = 0
    new_case_count = 0
    new_case_critical = 0
    new_case_high = 0
    open_breach_count = 0
    window_start_epoch = window_start.timestamp()
    for c in cases_for_customer or []:
        status = c.get("status") or ""
        priority = c.get("priority") or "low"
        if status not in ("cleared", "sar_filed"):
            open_case_count += 1
            if c.get("sla") == "breach":
                open_breach_count += 1
        opened_at = c.get("opened_at") or 0.0
        if float(opened_at) >= window_start_epoch:
            new_case_count += 1
            if priority == "critical":
                new_case_critical += 1
            elif priority == "high":
                new_case_high += 1

    pep = bool(customer.get("pep"))
    products = list(customer.get("products") or [])

    # Signal — used to rank movers; deterministic; weights live in SIGNAL_WEIGHTS.
    bucket_upgraded = 1.0 if band_shift_direction == "up" else 0.0
    refresh_overdue = 1.0 if refresh_label == "overdue" else 0.0
    critical_floor = 1.0 if composite >= CRITICAL_COMPOSITE_FLOOR else 0.0
    abs_delta = abs(composite_delta) if composite_delta is not None else 0.0
    signal = (
        SIGNAL_WEIGHTS["abs_delta"] * abs_delta
        + SIGNAL_WEIGHTS["bucket_upgraded"] * bucket_upgraded
        + SIGNAL_WEIGHTS["new_case_critical"] * new_case_critical
        + SIGNAL_WEIGHTS["new_case_high"] * new_case_high
        + SIGNAL_WEIGHTS["open_breach"] * open_breach_count
        + SIGNAL_WEIGHTS["refresh_overdue"] * refresh_overdue
        + SIGNAL_WEIGHTS["critical_floor"] * critical_floor
    )

    # Per-customer change lines — render the deltas as compact one-liners.
    lines: List[str] = []
    if band_shift_direction == "up":
        lines.append(
            f"Bucket shifted **{bucket_prior} → {bucket}** — escalate within the FATF-RBA refresh window."
        )
    elif band_shift_direction == "down":
        lines.append(
            f"Bucket relaxed **{bucket_prior} → {bucket}** — record the rationale on the case timeline."
        )
    if composite_delta is not None and abs(composite_delta) >= COMPOSITE_DELTA_FLOOR:
        verb = "rose" if composite_delta > 0 else "eased"
        lines.append(
            f"Composite {verb} **{abs(composite_delta):.0f} pts** ({composite_prior:.0f} → {composite:.0f})."
        )
    if new_case_critical:
        lines.append(f"**{new_case_critical} new critical case(s)** opened in the window.")
    if new_case_high and not new_case_critical:
        lines.append(f"**{new_case_high} new high-priority case(s)** opened in the window.")
    if open_breach_count:
        lines.append(f"**{open_breach_count} open case(s) breaching SLA** — triage first.")
    if refresh_label == "overdue":
        lines.append("KYC refresh **overdue** — open the Profile tab and re-anchor.")
    if not lines and composite >= CRITICAL_COMPOSITE_FLOOR:
        lines.append(
            f"Composite sits at **{composite:.0f}/100** (critical) — no movement, but the floor itself demands a re-read."
        )

    # Per-customer headline — one short sentence the UI surfaces on the card.
    head_bits: List[str] = []
    if band_shift_direction == "up":
        head_bits.append(f"Escalated to {bucket}")
    if composite_delta is not None and abs(composite_delta) >= COMPOSITE_DELTA_FLOOR:
        head_bits.append(f"{'+' if composite_delta > 0 else '−'}{abs(composite_delta):.0f} pts")
    if new_case_critical or new_case_high:
        n = new_case_critical + new_case_high
        head_bits.append(f"{n} fresh case(s)")
    if open_breach_count:
        head_bits.append(f"{open_breach_count} breach(es)")
    if refresh_label == "overdue":
        head_bits.append("KYC overdue")
    if not head_bits:
        if composite >= CRITICAL_COMPOSITE_FLOOR:
            head_bits.append(f"Critical floor · {composite:.0f}/100")
        else:
            head_bits.append("No movement")
    headline = " · ".join(head_bits)

    return CustomerPulse(
        customer_id=cid,
        display_name=name,
        domicile=domicile,
        bucket=bucket,
        bucket_prior=bucket_prior,
        bucket_accent=bucket_accent,
        composite=composite,
        composite_prior=composite_prior,
        composite_delta=composite_delta,
        refresh_label=refresh_label,
        refresh_days_to_due=refresh_days,
        open_case_count=open_case_count,
        new_case_count=new_case_count,
        new_case_critical=new_case_critical,
        new_case_high=new_case_high,
        open_breach_count=open_breach_count,
        pep=pep,
        products=products,
        headline=headline,
        change_lines=lines,
        signal=signal,
        band_shift_direction=band_shift_direction,
    )


# ---------------------------------------------------------------------------
# Mood ladder + headline composer
# ---------------------------------------------------------------------------


def _resolve_mood(pulses: List[CustomerPulse]) -> str:
    """First-match-wins mood ladder."""
    if not pulses:
        return "calm"
    crossed_critical = any(
        p.band_shift_direction == "up" and p.bucket == "critical" for p in pulses
    )
    any_breach = any(p.open_breach_count > 0 for p in pulses)
    any_critical_floor = any(p.composite >= CRITICAL_COMPOSITE_FLOOR for p in pulses)
    if crossed_critical or any_breach or any_critical_floor:
        return "critical"

    any_up_shift = any(p.band_shift_direction == "up" for p in pulses)
    total_new_cases = sum(p.new_case_count for p in pulses)
    big_shifters = sum(
        1 for p in pulses
        if p.composite_delta is not None and p.composite_delta >= ACTIVE_BIG_SHIFT_FLOOR
    )
    if (
        any_up_shift
        or total_new_cases >= ACTIVE_NEW_CASES_FLOOR
        or big_shifters >= ACTIVE_BIG_SHIFT_MIN_CUSTOMERS
    ):
        return "active"

    any_watch_shift = any(
        p.composite_delta is not None and p.composite_delta >= WATCH_SHIFT_FLOOR
        for p in pulses
    )
    any_fresh_hi = any(p.new_case_critical or p.new_case_high for p in pulses)
    any_overdue = any(p.refresh_label == "overdue" for p in pulses)
    if any_watch_shift or any_fresh_hi or any_overdue:
        return "watch"
    return "calm"


def _build_headline(
    pulses: List[CustomerPulse],
    *,
    mood: str,
    window_days: int,
    new_cases_total: int,
    breaches: int,
    movers: List[CustomerPulse],
) -> Tuple[str, str]:
    """Return ``(headline, advisory)``. The headline is the phone-banner
    style one-liner; the advisory is the second line below it."""

    if not pulses:
        return (
            "Empty portfolio — Pulse will surface activity once the book is seeded.",
            "Seed the bundled customer book from /profile to bring Pulse to life.",
        )

    mood_label = MOOD_META[mood]["label"]
    top = movers[0] if movers else None
    if not top:
        return (
            f"{mood_label} · no material movement across {len(pulses)} customer(s) in the last {window_days}d.",
            MOOD_META[mood]["blurb"],
        )

    parts: List[str] = [f"{mood_label}"]
    parts.append(f"{top.display_name}")
    if top.band_shift_direction == "up":
        parts.append(f"escalated to {top.bucket}")
    elif top.composite_delta is not None and abs(top.composite_delta) >= COMPOSITE_DELTA_FLOOR:
        sign = "+" if top.composite_delta > 0 else "−"
        parts.append(f"{sign}{abs(top.composite_delta):.0f} pts")
    elif top.composite >= CRITICAL_COMPOSITE_FLOOR:
        parts.append(f"sits at {top.composite:.0f} composite")
    else:
        parts.append("is the day's biggest mover")
    headline = " · ".join(parts)

    bits: List[str] = []
    if new_cases_total:
        bits.append(f"{new_cases_total} new case(s)")
    if breaches:
        bits.append(f"{breaches} SLA breach(es)")
    if len(movers) > 1:
        bits.append(f"{len(movers)} customer(s) moving")
    if not bits:
        bits.append(MOOD_META[mood]["blurb"])
    advisory = " · ".join(bits)
    return headline, advisory


# ---------------------------------------------------------------------------
# Change log + plan of day
# ---------------------------------------------------------------------------


def _build_change_log(
    pulses: List[CustomerPulse],
    *,
    window_days: int,
) -> List[str]:
    """Rank per-customer change-lines by their parent's signal and the
    line's own kind. Cap at ``CHANGE_LOG_CAP``."""
    log: List[Tuple[float, str]] = []
    for p in pulses:
        for line in p.change_lines:
            line_signal = p.signal
            if line.startswith("Bucket shifted"):
                line_signal += 6
            elif line.startswith("**"):
                line_signal += 1.5
            log.append((line_signal, f"**{p.display_name}** — {line}"))
    log.sort(key=lambda kv: kv[0], reverse=True)
    return [ln for _, ln in log[:CHANGE_LOG_CAP]]


def _build_plan_of_day(
    pulses: List[CustomerPulse],
    *,
    window_days: int,
    mood: str,
) -> List[PulseAction]:
    """Prioritised action list. Each action references a TITAN tab by name
    so the brief works even without memorising URLs."""

    actions: List[PulseAction] = []

    # 1. Breaches always lead.
    breaches = [p for p in pulses if p.open_breach_count > 0]
    breaches.sort(key=lambda p: (-p.open_breach_count, -p.signal))
    for p in breaches[:3]:
        actions.append(PulseAction(
            kind="case",
            priority="critical",
            body=(
                f"Triage **{p.open_breach_count} breach case(s)** for **{p.display_name}** "
                f"in the **Cases** tab — SLA clock has run out."
            ),
            customer_id=p.customer_id,
            href=f"/cases?account_id={p.customer_id}",
        ))

    # 2. Customers who crossed INTO critical.
    crossed = [p for p in pulses if p.band_shift_direction == "up" and p.bucket == "critical"]
    crossed.sort(key=lambda p: -p.signal)
    for p in crossed[:3]:
        actions.append(PulseAction(
            kind="escalate",
            priority="critical",
            body=(
                f"Escalate **{p.display_name}** — crossed into **critical** "
                f"(from {p.bucket_prior or 'low'}). Freeze new-product onboarding pending MLRO review."
            ),
            customer_id=p.customer_id,
            href=f"/profile?customer_id={p.customer_id}",
        ))

    # 3. New critical/high cases (excluding ones already covered by breaches above).
    seen = {p.customer_id for p in breaches} | {p.customer_id for p in crossed}
    fresh = [
        p for p in pulses
        if (p.new_case_critical or p.new_case_high) and p.customer_id not in seen
    ]
    fresh.sort(key=lambda p: (-p.new_case_critical, -p.new_case_high, -p.signal))
    for p in fresh[:3]:
        actions.append(PulseAction(
            kind="case",
            priority="high",
            body=(
                f"Review **{p.new_case_critical + p.new_case_high} fresh case(s)** "
                f"for **{p.display_name}** in the **Cases** tab."
            ),
            customer_id=p.customer_id,
            href=f"/cases?account_id={p.customer_id}",
        ))

    # 4. Refresh-overdue tail.
    overdue = [p for p in pulses if p.refresh_label == "overdue"]
    overdue.sort(key=lambda p: (p.refresh_days_to_due or 0, -p.signal))
    for p in overdue[:2]:
        days = p.refresh_days_to_due or 0
        actions.append(PulseAction(
            kind="refresh",
            priority="medium",
            body=(
                f"Re-anchor **{p.display_name}** in the **Profile** tab — "
                f"KYC overdue by {abs(days):.0f}d."
            ),
            customer_id=p.customer_id,
            href=f"/profile?customer_id={p.customer_id}",
        ))

    # 5. Composite movers — at most one "watch the rest" line.
    movers = [
        p for p in pulses
        if p.composite_delta is not None
        and abs(p.composite_delta) >= COMPOSITE_DELTA_FLOOR
        and p.customer_id not in seen
        and not any(a.customer_id == p.customer_id for a in actions)
    ]
    movers.sort(key=lambda p: -p.signal)
    if movers:
        names = ", ".join(p.display_name for p in movers[:3])
        actions.append(PulseAction(
            kind="profile",
            priority="medium",
            body=(
                f"Open the **Profile** tab for **{names}** — composite "
                f"shifted by ≥ {COMPOSITE_DELTA_FLOOR:.0f} pts in the window."
            ),
            customer_id=movers[0].customer_id,
            href=f"/profile?customer_id={movers[0].customer_id}",
        ))

    # 6. Fallback — calm morning.
    if not actions:
        actions.append(PulseAction(
            kind="profile",
            priority="low",
            body=(
                "Portfolio quiet — skim the **Profile** tab for any due-soon "
                "KYC refreshes and call it a clean morning."
            ),
        ))

    return actions[:PLAN_OF_DAY_CAP]


# ---------------------------------------------------------------------------
# Sparkline + histogram
# ---------------------------------------------------------------------------


def _activity_sparkline(
    cases: List[Dict[str, Any]],
    *,
    window_start: datetime,
    now: datetime,
) -> List[Dict[str, Any]]:
    """Per-day case-open counts across the window, oldest-first."""
    days = max(1, int((now - window_start).total_seconds() // 86400) + 1)
    days = min(days, MAX_WINDOW_DAYS + 1)
    buckets: List[Dict[str, Any]] = []
    for offset in range(days - 1, -1, -1):
        day_start = (now - timedelta(days=offset)).replace(
            hour=0, minute=0, second=0, microsecond=0,
        )
        day_end = day_start + timedelta(days=1)
        new_cases = 0
        sla_breaches = 0
        for c in cases:
            ts = c.get("opened_at") or 0
            if day_start.timestamp() <= float(ts) < day_end.timestamp():
                new_cases += 1
            if c.get("status") not in ("cleared", "sar_filed") and c.get("sla") == "breach":
                # SLA breach on its opened day for the purposes of the sparkline
                # — we don't track per-day breach transitions and the
                # interpretation "breach incurred on the same day" is good enough.
                if day_start.timestamp() <= float(ts) < day_end.timestamp():
                    sla_breaches += 1
        buckets.append({
            "date": day_start.date().isoformat(),
            "new_cases": new_cases,
            "sla_breaches": sla_breaches,
        })
    return buckets


def _score_histogram(pulses: List[CustomerPulse]) -> List[Dict[str, Any]]:
    """10-bucket histogram of current composites — used by the chart."""
    buckets = [{"min": i * 10, "max": (i + 1) * 10 - 0.01, "count": 0, "label": f"{i*10}–{(i+1)*10}"}
               for i in range(10)]
    for p in pulses:
        idx = min(9, max(0, int(p.composite // 10)))
        buckets[idx]["count"] += 1
    return buckets


# ---------------------------------------------------------------------------
# Core composer — pure function. The boundary fetchers below call this.
# ---------------------------------------------------------------------------


def compute_pulse(
    profiles: List[Dict[str, Any]],
    *,
    cases_index: Dict[str, List[Dict[str, Any]]],
    all_cases: List[Dict[str, Any]],
    window_days: int = DEFAULT_WINDOW_DAYS,
    now: Optional[datetime] = None,
    sample_priors: Optional[Dict[str, Dict[str, Any]]] = None,
) -> PulseReport:
    """Pure function. ``profiles`` is the full profile list (each with its
    ``history`` array attached). ``cases_index`` maps customer_id → list of
    case rows owned by any of the customer's accounts. ``all_cases`` is the
    flat list used to derive the activity sparkline.

    ``sample_priors`` — when present (used by the bundled demo endpoint),
    maps customer_id → ``{composite_prior, bucket_prior}`` so the brief
    can be rich even on a freshly-seeded store with no prior history.
    """

    now = now or datetime.now(timezone.utc)
    window_days = max(MIN_WINDOW_DAYS, min(MAX_WINDOW_DAYS, int(window_days)))
    window_start = now - timedelta(days=window_days)

    pulses: List[CustomerPulse] = []
    by_bucket: Dict[str, int] = {b: 0 for b in BUCKET_RANK}
    by_bucket_prior: Dict[str, int] = {b: 0 for b in BUCKET_RANK}
    for p in profiles:
        cid = (p.get("customer") or {}).get("customer_id") or p.get("customer_id") or ""
        cust_cases = cases_index.get(cid, [])
        override = (sample_priors or {}).get(cid)
        cp = _build_customer_pulse(
            p,
            cases_for_customer=cust_cases,
            window_start=window_start,
            now=now,
            sample_prior_overrides=override,
        )
        pulses.append(cp)
        by_bucket[cp.bucket] = by_bucket.get(cp.bucket, 0) + 1
        prior_b = cp.bucket_prior or cp.bucket
        by_bucket_prior[prior_b] = by_bucket_prior.get(prior_b, 0) + 1

    bucket_drift: Dict[str, int] = {
        b: by_bucket.get(b, 0) - by_bucket_prior.get(b, 0) for b in BUCKET_RANK
    }

    # Rank movers by signal — only keep customers with non-trivial signal.
    movers = sorted(
        [p for p in pulses if p.signal >= 1.0 or p.open_breach_count > 0],
        key=lambda p: -p.signal,
    )[:TOP_MOVERS_CAP]
    for m in movers:
        m.is_biggest_mover = True

    mood = _resolve_mood(pulses)

    new_cases_total = sum(p.new_case_count for p in pulses)
    new_cases_critical = sum(p.new_case_critical for p in pulses)
    open_breaches = sum(p.open_breach_count for p in pulses)
    open_cases_total = sum(p.open_case_count for p in pulses)
    refresh_overdue = sum(1 for p in pulses if p.refresh_label == "overdue")
    refresh_due_soon = sum(1 for p in pulses if p.refresh_label == "due_soon")

    headline, advisory = _build_headline(
        pulses, mood=mood, window_days=window_days,
        new_cases_total=new_cases_total, breaches=open_breaches, movers=movers,
    )
    change_log = _build_change_log(pulses, window_days=window_days)
    plan_of_day = _build_plan_of_day(pulses, window_days=window_days, mood=mood)
    sparkline = _activity_sparkline(all_cases, window_start=window_start, now=now)
    histogram = _score_histogram(pulses)

    return PulseReport(
        engine=ENGINE_VERSION,
        rules_version=RULES_VERSION,
        computed_at=now.isoformat(),
        window_days=window_days,
        window_start=window_start.isoformat(),
        now=now.isoformat(),
        mood=mood,
        mood_accent=MOOD_META[mood]["accent"],
        mood_label=MOOD_META[mood]["label"],
        mood_blurb=MOOD_META[mood]["blurb"],
        headline=headline,
        advisory=advisory,
        portfolio_size=len(pulses),
        movers_count=len(movers),
        new_cases_total=new_cases_total,
        new_cases_critical=new_cases_critical,
        open_breaches=open_breaches,
        open_cases_total=open_cases_total,
        refresh_overdue=refresh_overdue,
        refresh_due_soon=refresh_due_soon,
        by_bucket=by_bucket,
        by_bucket_prior=by_bucket_prior,
        bucket_drift=bucket_drift,
        activity_sparkline=sparkline,
        score_histogram=histogram,
        biggest_movers=movers,
        change_log=change_log,
        plan_of_day=plan_of_day,
        customers=pulses,
    )


# ---------------------------------------------------------------------------
# Boundary — fetches the inputs and calls compute_pulse. The pure function
# above is what tests target; this is what the HTTP route calls.
# ---------------------------------------------------------------------------


def _index_cases_by_customer(
    cases: List[Dict[str, Any]],
    accounts_by_customer: Dict[str, List[str]],
) -> Dict[str, List[Dict[str, Any]]]:
    """Each customer "owns" a set of accounts (declared on the profile);
    a case targets one account; we bucket cases under their owning customer."""
    owner_of: Dict[str, str] = {}
    for cid, accts in accounts_by_customer.items():
        for a in accts:
            if a:
                owner_of[a] = cid
    out: Dict[str, List[Dict[str, Any]]] = {cid: [] for cid in accounts_by_customer}
    for c in cases:
        aid = c.get("account_id")
        owner = owner_of.get(aid)
        if owner:
            out.setdefault(owner, []).append(c)
    return out


def build_live(
    *,
    window_days: int = DEFAULT_WINDOW_DAYS,
    now: Optional[datetime] = None,
) -> PulseReport:
    """Live mode — reads the persisted profile + cases stores."""
    portfolio = profile_engine.list_profiles(limit=1000)
    profiles = portfolio.get("profiles", [])
    # ``list_profiles`` returns row-shaped dicts without ``history``; we
    # have to hydrate per customer to read prior composites.
    hydrated: List[Dict[str, Any]] = []
    accounts_by_customer: Dict[str, List[str]] = {}
    for p in profiles:
        cid = (p.get("customer") or {}).get("customer_id")
        if not cid:
            continue
        full = profile_engine.get_profile(cid, with_history=True) or p
        hydrated.append(full)
        # Accounts live in the evidence blob; fall back to empty list.
        accts: List[str] = []
        ev = full.get("evidence") or {}
        for a in (ev.get("transaction") or {}).get("accounts") or []:
            if a.get("account_id"):
                accts.append(str(a["account_id"]))
        # Some fixtures carry accounts on the customer block itself.
        for a in (full.get("customer") or {}).get("accounts") or []:
            if a:
                accts.append(str(a))
        accounts_by_customer[cid] = sorted(set(accts))

    case_listing = case_store.list_cases(limit=1000, include_closed=True)
    all_cases = case_listing.get("cases", [])
    cases_index = _index_cases_by_customer(all_cases, accounts_by_customer)
    return compute_pulse(
        hydrated,
        cases_index=cases_index,
        all_cases=all_cases,
        window_days=window_days,
        now=now,
    )


# ---------------------------------------------------------------------------
# Sample — produces a vivid Pulse without depending on persisted state.
# This is what the demo / first-load uses. Deterministic.
# ---------------------------------------------------------------------------


def get_sample_pulse(window_days: int = DEFAULT_WINDOW_DAYS) -> PulseReport:
    """Build a pulse from the bundled customer book *plus* a deterministic
    synthetic "yesterday" snapshot so the brief is rich even on a fresh
    install. Pure: same inputs in, identical bytes out."""

    sample = profile_engine.get_sample()
    customers = sample.get("customers", [])

    # Anchor "now" deterministically — a fixed instant so the sample
    # endpoint produces stable bytes across days (CI-stable). The window
    # math still works because we synthesise prior_composites directly.
    now = datetime.fromisoformat("2026-06-21T09:00:00+00:00")

    # Build the live-shaped profile dicts from the bundled fixture by
    # running compute_profile directly (no DB writes). Each entry gets a
    # synthetic "yesterday composite" for the demo — chosen so the
    # bundled CUST-* fixture lights up Pulse with realistic movement.
    sample_priors: Dict[str, Dict[str, Any]] = {}
    profiles: List[Dict[str, Any]] = []
    accounts_by_customer: Dict[str, List[str]] = {}
    for entry in customers:
        cust = entry["customer"]
        evidence = entry.get("evidence") or {}
        prof = profile_engine.compute_profile(cust, evidence=evidence, now=now)
        prof["evidence"] = evidence
        profiles.append(prof)
        cid = cust["customer_id"]
        accounts_by_customer[cid] = list(cust.get("accounts") or [])

        # Synthesise a prior composite — back off by a deterministic delta
        # that depends on the customer's domicile + risk products so the
        # brief shows movement without random noise.
        base = float(prof["composite"])
        domicile = (cust.get("domicile") or "").upper()
        pep = bool(cust.get("pep"))
        risky_products = sum(
            1 for p in (cust.get("products") or [])
            if p in profile_engine.HIGH_RISK_PRODUCTS
        )
        # High-risk customers in the fixture get a clear *upward* drift so
        # the morning-brief reads like a real escalation; low-risk
        # customers either ease slightly or hold steady.
        if base >= 80 or domicile in profile_engine.HIGH_RISK_GEOS or pep:
            backoff = 18.0 + 2.0 * risky_products
        elif base >= 60:
            backoff = 11.0
        elif base >= 40:
            backoff = 6.5
        else:
            backoff = -1.5  # eased slightly (composite went up since yesterday by 1.5)
        prior_composite = max(0.0, min(100.0, base - backoff))
        prior_bucket = profile_engine.bucket_for(prior_composite)
        sample_priors[cid] = {
            "composite_prior": round(prior_composite, 1),
            "bucket_prior": prior_bucket,
        }

    # Synthetic cases for the sparkline + breach panel. We seed one
    # critical case for the highest-composite customer, one breach for
    # the next-highest, and one fresh-high case on a third. The IDs are
    # stable, the timestamps are anchored to ``now`` so the sparkline
    # always shows the same shape.
    sorted_profiles = sorted(profiles, key=lambda p: -float(p["composite"]))
    fake_cases: List[Dict[str, Any]] = []
    if sorted_profiles:
        top = sorted_profiles[0]
        top_cid = top["customer"]["customer_id"]
        top_acct = (accounts_by_customer.get(top_cid) or [None])[0]
        if top_acct:
            fake_cases.append({
                "id": f"PULSE-DEMO-{top_cid}",
                "account_id": top_acct,
                "display_name": top["customer"].get("display_name"),
                "status": "open",
                "priority": "critical",
                "alert_score": 88.0,
                "sla": "ok",
                "opened_at": (now - timedelta(hours=6)).timestamp(),
                "summary": "Auto-opened from /aml/score — multiple firing detectors.",
            })
    if len(sorted_profiles) >= 2:
        runner = sorted_profiles[1]
        runner_cid = runner["customer"]["customer_id"]
        runner_acct = (accounts_by_customer.get(runner_cid) or [None])[0]
        if runner_acct:
            fake_cases.append({
                "id": f"PULSE-DEMO-{runner_cid}",
                "account_id": runner_acct,
                "display_name": runner["customer"].get("display_name"),
                "status": "review",
                "priority": "high",
                "alert_score": 72.0,
                "sla": "breach",
                "opened_at": (now - timedelta(hours=80)).timestamp(),
                "summary": "Awaiting analyst review past 72h SLA.",
            })
    if len(sorted_profiles) >= 3:
        third = sorted_profiles[2]
        third_cid = third["customer"]["customer_id"]
        third_acct = (accounts_by_customer.get(third_cid) or [None])[0]
        if third_acct:
            fake_cases.append({
                "id": f"PULSE-DEMO-{third_cid}",
                "account_id": third_acct,
                "display_name": third["customer"].get("display_name"),
                "status": "open",
                "priority": "high",
                "alert_score": 64.0,
                "sla": "ok",
                "opened_at": (now - timedelta(hours=18)).timestamp(),
                "summary": "Fresh high-priority case opened in the window.",
            })

    cases_index = _index_cases_by_customer(fake_cases, accounts_by_customer)
    return compute_pulse(
        profiles,
        cases_index=cases_index,
        all_cases=fake_cases,
        window_days=window_days,
        now=now,
        sample_priors=sample_priors,
    )


# ---------------------------------------------------------------------------
# Markdown export — paste-able into Slack / email.
# ---------------------------------------------------------------------------


def to_markdown(report: PulseReport) -> str:
    lines: List[str] = []
    lines.append(f"# TITAN Pulse — {report.mood_label}")
    lines.append("")
    lines.append(f"> {report.headline}")
    lines.append("")
    lines.append(f"_{report.advisory}_")
    lines.append("")
    lines.append(f"**Window:** {report.window_days}d · **Portfolio:** {report.portfolio_size} customer(s)")
    lines.append("")
    lines.append("## Vital signs")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|---|---|")
    lines.append(f"| New cases | {report.new_cases_total} ({report.new_cases_critical} critical) |")
    lines.append(f"| Open cases | {report.open_cases_total} |")
    lines.append(f"| SLA breaches | {report.open_breaches} |")
    lines.append(f"| KYC overdue | {report.refresh_overdue} |")
    lines.append(f"| KYC due ≤ 30d | {report.refresh_due_soon} |")
    lines.append(f"| Movers | {report.movers_count} |")
    lines.append("")
    lines.append("## Bucket distribution")
    lines.append("")
    lines.append("| Bucket | Now | Prior | Δ |")
    lines.append("|---|---:|---:|---:|")
    for b in ("critical", "high", "medium", "low"):
        now_n = report.by_bucket.get(b, 0)
        pr_n = report.by_bucket_prior.get(b, 0)
        delta = now_n - pr_n
        sign = "+" if delta > 0 else ""
        lines.append(f"| {_bucket_emoji(b)} {b} | {now_n} | {pr_n} | {sign}{delta} |")
    lines.append("")
    if report.biggest_movers:
        lines.append("## Biggest movers")
        lines.append("")
        for p in report.biggest_movers:
            delta_str = (
                f" ({p.composite_prior:.0f} → {p.composite:.0f}, "
                f"{_format_pts_delta(p.composite_delta)})"
                if p.composite_delta is not None else ""
            )
            shift_str = (
                f" · bucket {p.bucket_prior} → {p.bucket}"
                if p.band_shift_direction else ""
            )
            cases_str = (
                f" · {p.new_case_critical + p.new_case_high} fresh case(s)"
                if (p.new_case_critical or p.new_case_high) else ""
            )
            breach_str = f" · {p.open_breach_count} breach(es)" if p.open_breach_count else ""
            lines.append(f"- **{p.display_name}** — {p.bucket}{delta_str}{shift_str}{cases_str}{breach_str}")
        lines.append("")
    if report.change_log:
        lines.append("## What changed in the last window")
        lines.append("")
        for ln in report.change_log:
            lines.append(f"- {ln}")
        lines.append("")
    if report.plan_of_day:
        lines.append("## Plan of day")
        lines.append("")
        for i, a in enumerate(report.plan_of_day, 1):
            lines.append(f"{i}. **[{a.priority}]** {a.body}")
        lines.append("")
    lines.append(f"_{report.engine} · rules v{report.rules_version} · {report.computed_at}_")
    return "\n".join(lines).rstrip() + "\n"


# ---------------------------------------------------------------------------
# Rules / metadata — what /aml/pulse/rules ships.
# ---------------------------------------------------------------------------


def get_rules() -> Dict[str, Any]:
    return {
        "version": RULES_VERSION,
        "engine": ENGINE_VERSION,
        "default_window_days": DEFAULT_WINDOW_DAYS,
        "min_window_days": MIN_WINDOW_DAYS,
        "max_window_days": MAX_WINDOW_DAYS,
        "composite_delta_floor": COMPOSITE_DELTA_FLOOR,
        "critical_composite_floor": CRITICAL_COMPOSITE_FLOOR,
        "active_big_shift_floor": ACTIVE_BIG_SHIFT_FLOOR,
        "active_big_shift_min_customers": ACTIVE_BIG_SHIFT_MIN_CUSTOMERS,
        "active_new_cases_floor": ACTIVE_NEW_CASES_FLOOR,
        "watch_shift_floor": WATCH_SHIFT_FLOOR,
        "change_log_cap": CHANGE_LOG_CAP,
        "plan_of_day_cap": PLAN_OF_DAY_CAP,
        "top_movers_cap": TOP_MOVERS_CAP,
        "signal_weights": dict(SIGNAL_WEIGHTS),
        "mood_order": list(MOOD_ORDER),
        "mood_meta": MOOD_META,
        "fresh_case_priorities": list(FRESH_CASE_PRIORITIES),
    }
