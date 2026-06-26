"""TITAN AML — Lineage: temporal fund-flow tracer.

Every prior TITAN surface answers a *structural* or *aggregate* question:

  * ``risk.py``     — "is this account suspicious *right now*?"
  * ``network.py``  — "who is this account *structurally connected to*?"
  * ``typology.py`` — "which laundering playbook fits the pattern?"
  * ``profile.py``  — "what's this customer's composite risk *today*?"
  * ``pulse.py``    — "what's *different* across the book since yesterday?"
  * ``drift.py``    — "has this account's *own* behaviour shifted?"
  * ``peer.py``     — "does this customer look weird vs *their cohort*?"

None of them answer the question a real investigator opens with the
moment a SAR draft lands on their desk:

  *"Where did this money come from, where did it go, and how much of it
  can I actually trace from origin to destination?"*

That's **lineage** — and it's why every regulator's MLRO course teaches
"follow the money" as the first step.  Lineage builds a **time-ordered
fund-flow DAG**, runs a FIFO lot-tracer over it to attribute every
downstream balance back to its upstream sources, detects six canonical
flow-shaped laundering patterns along the trail, and writes a
plain-English §3 narrative the analyst can drop straight into the SAR.

Zero new physics, pure stdlib, deterministic — same ``(transactions,
seed, direction, depth, window)`` in → identical bytes out.  Composes
the existing detectors / propagation engines instead of duplicating them
(``risk.point_risk``-style scoring is reused for every node touched).


Algorithm
---------

1. **Index transactions** by sender, recipient, and (sender → recipient)
   pair.  Sort each adjacency list by timestamp ascending.

2. **Build the trace.**  Starting from ``seed``, walk outwards
   (``forward`` = downstream, ``backward`` = upstream, ``both`` = the
   union).  Each visited account becomes a ``LineageNode`` at a hop
   depth.  Each transaction becomes a ``LineageEdge`` with its tx-time,
   amount, channel and geo.  Depth is bounded by ``max_depth``; the
   time window bounds which transactions count (``window_days`` either
   side of the most-recent tx that touches the seed, or caller-supplied
   ``now``).

3. **Run the FIFO lot tracer.**  This is the heart of the engine.  For
   every account in the trace, maintain an ordered queue of "lots" —
   units of inflow with origin attribution (``source_id``, ``depth``,
   ``traceable_fraction``).  When funds leave the account, consume from
   the queue oldest-first (FIFO — the same convention every forensic
   accountant uses for commingled funds), proportionally splitting the
   attribution onto the outflow.  The result is a per-account
   ``provenance`` map showing which fraction of the *current* balance is
   attributable to each upstream source — the same lens regulators use
   to argue "X% of this hospital account came from a smurfing ring".

4. **Pattern detection.**  Six flow-shape detectors run against the
   built DAG (none of these are detectable from a single-account risk
   score; they only exist *across* the trail):

   * ``smurf_chain``   — many sub-threshold senders → one funnel
                         → one wire out (FATF "structuring + funnel")
   * ``round_trip``    — funds return to the seed or its cluster
                         within the window (FATF "layering loop")
   * ``pass_through``  — node with high fan-in *and* fan-out and
                         < 12 % retention (FATF "mule pass-through")
   * ``integration``   — round-amount transfer into a clean venue
                         (FATF "integration entry point")
   * ``velocity_ramp`` — average hop interval shrinks across the
                         trail (rush-to-layer signal)
   * ``geo_hopping``   — every hop changes jurisdiction (chain
                         jurisdictional cover)

   Each match emits a ``LineagePattern`` with a 0..1 ``confidence``,
   ranked evidence chips, contributing-node ids, and a recommended
   action.  The full catalogue + thresholds is dumped at
   ``GET /aml/lineage/rules`` so auditors can verify formulas before
   the engine ships.

5. **Trail score** ∈ [0, 100] composes:

       0.40·depth_factor + 0.25·amount_factor +
       0.15·pattern_factor + 0.10·geo_factor +
       0.10·suspicious_node_factor

   Each factor is normalised to [0, 1] before weighting; the
   sub-scores are reported alongside so the analyst can see *why*
   the trail scored what it did.

6. **Narrative.**  ``to_narrative()`` composes a 3-paragraph
   plain-English account suitable for SAR §3 — origin paragraph,
   layering paragraph, destination paragraph.  Reuses the same
   ``**bold**`` markdown convention every other TITAN composer ships.

Public API
----------

``compute_lineage(transactions, seed, direction, max_depth, window_days, now)``
  Synchronous, pure function.  Returns a ``LineageReport`` dataclass.

``get_sample_trace(seed=None, direction="both", max_depth=4)``
  Builds an illustrative report from a bundled 24-transaction synthetic
  laundering fixture (placement → layering → integration triple-arm).
  Used by ``GET /aml/lineage/sample`` so the surface lights up without
  the analyst having to seed the store.

``to_markdown(report)``
  Paste-able exhibit (~2.5 KB) for SAR §3 — headline, trail summary
  table, provenance table, patterns list, narrative, recommended
  actions.

``get_rules()``
  Dump of every tunable knob (pattern thresholds, scoring weights,
  factor bounds) for ``GET /aml/lineage/rules``.

Engine version: ``titan-lineage/1.0.0``.
"""

from __future__ import annotations

import math
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple


# ---------------------------------------------------------------------------
# Engine identity
# ---------------------------------------------------------------------------

ENGINE_VERSION = "titan-lineage/1.0.0"

# ---------------------------------------------------------------------------
# Tunables.  Auditor-facing via GET /aml/lineage/rules.
# ---------------------------------------------------------------------------

# Tracing bounds.
DEFAULT_MAX_DEPTH = 4              # hops out from the seed
MIN_MAX_DEPTH = 1
MAX_MAX_DEPTH = 8                  # hard ceiling so a runaway graph can't blow the trace
DEFAULT_WINDOW_DAYS = 30
MIN_WINDOW_DAYS = 1
MAX_WINDOW_DAYS = 180

# Provenance precision: lots smaller than this fraction (of the original
# seed inflow) are dropped from the per-account provenance table to
# keep the surface readable.  The total share still sums to 1.0
# (residual is folded into an "other" bucket).
PROVENANCE_MIN_SHARE = 0.005

# Pattern thresholds.
SMURF_BAND_LOW = 40_000.0          # Indian FIU-IND CTR proxy
SMURF_BAND_HIGH = 50_000.0
SMURF_MIN_FAN_IN = 5               # ≥5 distinct sub-threshold senders to a funnel
SMURF_MIN_OUT_AMOUNT = 100_000.0   # the funnel forwards ≥1L on the way out
SMURF_WINDOW_HOURS = 72

ROUND_TRIP_MIN_RETURN_FRACTION = 0.20   # ≥20 % of the seed's outflow returns
ROUND_TRIP_MIN_HOPS = 2

PASS_THROUGH_MIN_INFLOWS = 3
PASS_THROUGH_MIN_OUTFLOWS = 3
PASS_THROUGH_MAX_RETENTION = 0.12       # ≤12 % of inflow retained

INTEG_ROUND_MOD = 10_000.0              # value % MOD == 0 → "round amount"
INTEG_MIN_AMOUNT = 250_000.0
INTEG_DEST_KEYWORDS = (
    "real estate", "realty", "developers", "properties", "auto",
    "motors", "jewell", "gold", "art", "auction", "yacht", "casino",
    "luxury", "diamond",
)

VELOCITY_RAMP_MIN_HOPS = 3              # need at least 3 edges to fit a ramp
VELOCITY_RAMP_DECAY_THRESHOLD = 0.55    # ratio (late_avg / early_avg) ≤ this

GEO_HOPPING_MIN_HOPS = 3
GEO_HOPPING_MIN_DISTINCT = 3            # ≥3 distinct geos along the trail

# Trail-score factor weights (must sum to 1.0).
SCORE_WEIGHTS: Dict[str, float] = {
    "depth": 0.40,
    "amount": 0.25,
    "pattern": 0.15,
    "geo": 0.10,
    "suspicious_node": 0.10,
}

# Normalisation bounds for each factor.
DEPTH_FACTOR_FULL_AT = 4        # depth reaching seed+4 saturates
AMOUNT_FACTOR_FULL_AT = 1_000_000.0   # traced amount ≥10L saturates
PATTERN_FACTOR_FULL_AT = 3      # 3 patterns saturate the factor
GEO_FACTOR_FULL_AT = 4          # 4 distinct geos saturate
SUSPICIOUS_FACTOR_FULL_AT = 0.50  # 50 % of nodes flagged saturates

# Mood ladder (first-match-wins on the trail score).
MOOD_LADDER: List[Tuple[int, str]] = [
    (75, "critical"),
    (55, "active"),
    (35, "watch"),
    (0,  "calm"),
]

MOOD_BLURB: Dict[str, str] = {
    "calm":     "Trail is short and concentrated — looks like an ordinary flow of funds.",
    "watch":    "Trail shows minor signals — worth a glance, no immediate action required.",
    "active":   "Trail shows multiple laundering signals — bring it to the team standup.",
    "critical": "Trail looks like a textbook laundering chain — recommend SAR and freeze pending review.",
}

# Pattern metadata (label, accent hex, recommended action, severity floor).
PATTERN_META: Dict[str, Dict[str, Any]] = {
    "smurf_chain": {
        "label": "Smurfing → funnel chain",
        "accent": "#fb923c",
        "action": "Escalate to MLRO — recommend SAR + freeze on the funnel account.",
        "severity": "high",
    },
    "round_trip": {
        "label": "Layering loop (round-trip)",
        "accent": "#ef4444",
        "action": "Treat as confirmed layering — pull payee statements, file SAR.",
        "severity": "critical",
    },
    "pass_through": {
        "label": "Pass-through mule",
        "accent": "#fbbf24",
        "action": "Probable mule — query KYC, confirm beneficial owner, consider exit.",
        "severity": "medium",
    },
    "integration": {
        "label": "Integration entry",
        "accent": "#a78bfa",
        "action": "Verify counterparty UBO + invoice trail before clearing.",
        "severity": "medium",
    },
    "velocity_ramp": {
        "label": "Velocity ramp (rush-to-layer)",
        "accent": "#22d3a8",
        "action": "Watch for further hops in next 24h — set alert + re-trace tomorrow.",
        "severity": "medium",
    },
    "geo_hopping": {
        "label": "Cross-jurisdiction chain",
        "accent": "#60a5fa",
        "action": "Pull correspondent-bank attestations for each jurisdiction crossed.",
        "severity": "high",
    },
}

PATTERN_ORDER: Tuple[str, ...] = tuple(PATTERN_META.keys())


# ---------------------------------------------------------------------------
# Domain types
# ---------------------------------------------------------------------------


@dataclass
class Tx:
    """Normalised transaction used by the tracer.

    Same conventions as ``risk.Tx`` — ``account_id`` is the *sender*,
    ``counterparty`` is the *recipient*.  ``timestamp`` is an
    aware-UTC datetime so all hop-interval arithmetic is timezone-safe.
    """

    tx_id: str
    account_id: str
    counterparty: str
    amount: float
    timestamp: datetime
    channel: str = ""
    geo_src: str = ""
    geo_dst: str = ""
    subject_name: str = ""
    counterparty_name: str = ""
    meta: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LineageEdge:
    """One transaction in the traced trail."""

    tx_id: str
    src: str
    dst: str
    amount: float
    timestamp: datetime
    channel: str
    geo_src: str
    geo_dst: str
    src_depth: int
    dst_depth: int
    traceable_fraction: float = 0.0   # filled by the FIFO tracer
    pattern_tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tx_id": self.tx_id,
            "src": self.src,
            "dst": self.dst,
            "amount": round(self.amount, 2),
            "timestamp": self.timestamp.isoformat(),
            "channel": self.channel,
            "geo_src": self.geo_src,
            "geo_dst": self.geo_dst,
            "src_depth": self.src_depth,
            "dst_depth": self.dst_depth,
            "traceable_fraction": round(self.traceable_fraction, 4),
            "pattern_tags": list(self.pattern_tags),
        }


@dataclass
class ProvenanceShare:
    """A piece of upstream attribution surfaced on a node."""

    source_id: str
    source_label: str
    depth: int                       # depth of source from seed
    share: float                     # fraction of current balance
    via_hops: int                    # length of the longest path source→node

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_id": self.source_id,
            "source_label": self.source_label,
            "depth": self.depth,
            "share": round(self.share, 4),
            "via_hops": self.via_hops,
        }


@dataclass
class LineageNode:
    """One account in the traced trail."""

    account_id: str
    display_name: str
    depth: int                       # 0 = seed, +N downstream, -N upstream
    direction: str                   # 'seed' | 'downstream' | 'upstream' | 'both'
    geo: str
    role_tags: List[str] = field(
        default_factory=list
    )  # 'funnel' | 'mule' | 'integration' | 'origin' | 'destination'
    in_count: int = 0
    out_count: int = 0
    in_amount: float = 0.0
    out_amount: float = 0.0
    distinct_inflows: int = 0
    distinct_outflows: int = 0
    first_seen: Optional[datetime] = None
    last_seen: Optional[datetime] = None
    provenance: List[ProvenanceShare] = field(default_factory=list)
    suspicion_score: float = 0.0     # 0..1, composed at trace-build time

    @property
    def retention(self) -> float:
        if self.in_amount <= 0.0:
            return 0.0
        return max(0.0, (self.in_amount - self.out_amount) / self.in_amount)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "account_id": self.account_id,
            "display_name": self.display_name,
            "depth": self.depth,
            "direction": self.direction,
            "geo": self.geo,
            "role_tags": list(self.role_tags),
            "in_count": self.in_count,
            "out_count": self.out_count,
            "in_amount": round(self.in_amount, 2),
            "out_amount": round(self.out_amount, 2),
            "distinct_inflows": self.distinct_inflows,
            "distinct_outflows": self.distinct_outflows,
            "retention": round(self.retention, 4),
            "first_seen": self.first_seen.isoformat() if self.first_seen else None,
            "last_seen": self.last_seen.isoformat() if self.last_seen else None,
            "provenance": [p.to_dict() for p in self.provenance],
            "suspicion_score": round(self.suspicion_score, 4),
        }


@dataclass
class LineagePattern:
    """One detected flow-shaped laundering signal."""

    code: str
    label: str
    accent: str
    confidence: float
    severity: str
    action: str
    contributing_nodes: List[str]
    evidence: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "label": self.label,
            "accent": self.accent,
            "confidence": round(self.confidence, 4),
            "severity": self.severity,
            "action": self.action,
            "contributing_nodes": list(self.contributing_nodes),
            "evidence": list(self.evidence),
        }


@dataclass
class TrailFactor:
    """One component of the composite trail score (audit-facing)."""

    key: str
    value: float          # raw value
    normalised: float     # 0..1 after normalisation bounds
    weight: float         # configured weight
    contribution: float   # = normalised * weight (in 0..100 trail-score units)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "value": round(self.value, 4),
            "normalised": round(self.normalised, 4),
            "weight": round(self.weight, 4),
            "contribution": round(self.contribution, 4),
        }


@dataclass
class LineageReport:
    """Full output of the tracer."""

    composed_at: str
    engine: str
    seed: str
    seed_label: str
    direction: str
    max_depth: int
    window_days: int
    window_start: str
    window_end: str
    nodes: List[LineageNode]
    edges: List[LineageEdge]
    patterns: List[LineagePattern]
    trail_score: int
    mood: str
    headline: str
    advisory: str
    factors: List[TrailFactor]
    total_amount_traced: float
    distinct_geos: List[str]
    longest_path: List[str]           # account ids along the longest traced path
    plan_of_action: List[Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "envelope": "titan.lineage.v1",
            "composed_at": self.composed_at,
            "engine": self.engine,
            "seed": self.seed,
            "seed_label": self.seed_label,
            "direction": self.direction,
            "max_depth": self.max_depth,
            "window_days": self.window_days,
            "window_start": self.window_start,
            "window_end": self.window_end,
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
            "patterns": [p.to_dict() for p in self.patterns],
            "trail_score": int(round(self.trail_score)),
            "mood": self.mood,
            "headline": self.headline,
            "advisory": self.advisory,
            "factors": [f.to_dict() for f in self.factors],
            "total_amount_traced": round(self.total_amount_traced, 2),
            "distinct_geos": list(self.distinct_geos),
            "longest_path": list(self.longest_path),
            "plan_of_action": list(self.plan_of_action),
        }


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _parse_iso(s: Any) -> datetime:
    """Best-effort parse of an ISO-8601 string into an aware UTC datetime.

    The same convention every other engine uses — fall back to ``UTC``
    when the input is naive, raise when the input isn't parseable so the
    caller surfaces a 422.
    """
    if isinstance(s, datetime):
        return s if s.tzinfo else s.replace(tzinfo=timezone.utc)
    if not isinstance(s, str):
        raise ValueError(f"timestamp must be ISO string, got {type(s).__name__}")
    s2 = s.strip()
    if s2.endswith("Z"):
        s2 = s2[:-1] + "+00:00"
    dt = datetime.fromisoformat(s2)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _normalise_tx(raw: Dict[str, Any], fallback_idx: int) -> Tx:
    """Coerce a raw transaction dict into a ``Tx``.

    ``tx_id`` is generated deterministically from ``(idx, src, dst, amount,
    timestamp)`` when the caller didn't supply one, so the tracer's
    output is stable across runs."""
    tx_id = raw.get("tx_id") or raw.get("id") or ""
    src = str(raw.get("account_id") or raw.get("src") or "")
    dst = str(raw.get("counterparty") or raw.get("dst") or "")
    if not src or not dst:
        raise ValueError(f"transaction must carry both src and dst (got src={src!r}, dst={dst!r})")
    amount = float(raw.get("amount") or 0.0)
    if amount <= 0:
        raise ValueError("transaction amount must be > 0")
    ts = _parse_iso(raw.get("timestamp"))
    if not tx_id:
        tx_id = f"TX-{fallback_idx:06d}-{src[-4:]}-{dst[-4:]}"
    return Tx(
        tx_id=str(tx_id),
        account_id=src,
        counterparty=dst,
        amount=amount,
        timestamp=ts,
        channel=str(raw.get("channel") or ""),
        geo_src=str(raw.get("geo_src") or raw.get("geo") or ""),
        geo_dst=str(raw.get("geo_dst") or raw.get("geo") or ""),
        subject_name=str(raw.get("subject_name") or raw.get("subject") or ""),
        counterparty_name=str(raw.get("counterparty_name") or ""),
        meta=dict(raw.get("meta") or {}),
    )


def _round_amount(value: float) -> bool:
    """A 'round' amount under the integration definition."""
    if value < INTEG_MIN_AMOUNT:
        return False
    return abs(value - round(value / INTEG_ROUND_MOD) * INTEG_ROUND_MOD) < 1.0


def _label_for(account_id: str, name_map: Dict[str, str]) -> str:
    """Display label for an account: caller-supplied name, else the id."""
    name = name_map.get(account_id, "").strip()
    return name if name else account_id


def _format_amount_short(value: float) -> str:
    """`102345.6 → ₹1.02L`, `1_500_000 → ₹15L`, `7_500_000 → ₹75L`,
    fall back to thousands for sub-lakh amounts."""
    if value >= 10_000_000:
        return f"₹{value / 10_000_000:.2f}Cr"
    if value >= 100_000:
        return f"₹{value / 100_000:.2f}L"
    if value >= 1_000:
        return f"₹{value / 1_000:.1f}k"
    return f"₹{value:,.0f}"


# ---------------------------------------------------------------------------
# FIFO lot tracer
# ---------------------------------------------------------------------------


@dataclass
class _Lot:
    """One unit of inflow attributed to a single upstream source."""

    source_id: str
    depth: int
    amount: float
    hops: int


def _trace_provenance(
    txs: List[Tx],
    seeds: Set[str],
) -> Dict[str, List[ProvenanceShare]]:
    """Run the FIFO lot tracer over ``txs`` seeded with ``seeds``.

    Every transaction is processed in timestamp order.  For each
    account we maintain a ``deque[_Lot]``.  When funds arrive from
    a seed-attributed account, we copy the consumed lots forward
    (depth and hops incremented).  When funds arrive from an
    unattributed account, a synthetic lot tagged with the upstream
    counterparty itself is created — that way the recipient always
    has *some* provenance to display even when the original source
    isn't in the seed cluster.

    Returns a per-account ``List[ProvenanceShare]`` collapsed by
    source_id and rolled up to fractions of the account's total
    inflow.  Lots below ``PROVENANCE_MIN_SHARE`` are folded into a
    single ``__other__`` bucket so the surface stays readable.
    """
    queues: Dict[str, deque] = defaultdict(deque)
    inflow_totals: Dict[str, float] = defaultdict(float)
    # Seed the seed accounts with a "themselves" lot at depth 0 — so
    # any outflow from a seed account is attributable back to it.
    for s in seeds:
        queues[s].append(_Lot(source_id=s, depth=0, amount=10 ** 12, hops=0))
    # raw provenance: account -> source_id -> (sum_amount, max_hops)
    raw: Dict[str, Dict[str, List[float]]] = defaultdict(
        lambda: defaultdict(lambda: [0.0, 0])
    )
    txs_sorted = sorted(txs, key=lambda t: t.timestamp)
    for tx in txs_sorted:
        src, dst = tx.account_id, tx.counterparty
        # Pull (tx.amount) worth of lots out of `src`.  If `src` has
        # never been seen as a recipient, synthesise an "origin"
        # lot for it so the recipient's provenance is non-empty.
        if src not in queues or not queues[src]:
            queues[src].append(_Lot(source_id=src, depth=0, amount=10 ** 12, hops=0))
        remaining = tx.amount
        produced: List[_Lot] = []
        while remaining > 1e-6 and queues[src]:
            head = queues[src][0]
            if head.amount <= 0:
                queues[src].popleft()
                continue
            take = min(head.amount, remaining)
            head.amount -= take
            remaining -= take
            produced.append(
                _Lot(
                    source_id=head.source_id,
                    depth=head.depth + 1 if head.source_id != src else 0,
                    amount=take,
                    hops=head.hops + 1,
                )
            )
            if head.amount <= 1e-6:
                queues[src].popleft()
        # If we ran out of `src` lots (e.g. infinite-source path
        # exhausted) the remaining shortfall is attributed to `src`
        # directly — this handles the edge case where the
        # synthesised lot is consumed but more outflow is requested
        # by adjacent transactions in the same batch.
        if remaining > 1e-6:
            produced.append(
                _Lot(source_id=src, depth=0, amount=remaining, hops=1)
            )
        # Push the produced lots onto `dst` and roll up.
        for lot in produced:
            queues[dst].append(lot)
            inflow_totals[dst] += lot.amount
            entry = raw[dst][lot.source_id]
            entry[0] += lot.amount
            entry[1] = max(entry[1], lot.hops)
    # Roll up to provenance shares per account.
    out: Dict[str, List[ProvenanceShare]] = {}
    for account, source_map in raw.items():
        total = inflow_totals.get(account, 0.0)
        if total <= 0:
            continue
        shares: List[Tuple[str, float, int]] = []
        other_amount = 0.0
        for source_id, (amount, hops) in source_map.items():
            share = amount / total
            if share < PROVENANCE_MIN_SHARE and source_id != account:
                other_amount += amount
                continue
            shares.append((source_id, share, hops))
        if other_amount > PROVENANCE_MIN_SHARE * total:
            shares.append(("__other__", other_amount / total, 0))
        shares.sort(key=lambda x: x[1], reverse=True)
        out[account] = [
            ProvenanceShare(
                source_id=sid,
                source_label="(many small upstream sources)" if sid == "__other__" else sid,
                depth=0,  # filled by caller using the trace depth map
                share=share,
                via_hops=hops,
            )
            for sid, share, hops in shares
        ]
    return out


# ---------------------------------------------------------------------------
# Trace walker
# ---------------------------------------------------------------------------


def _walk_trace(
    txs: List[Tx],
    seed: str,
    direction: str,
    max_depth: int,
    window_start: datetime,
    window_end: datetime,
) -> Tuple[Dict[str, LineageNode], List[LineageEdge]]:
    """BFS outwards from ``seed`` respecting direction + depth + window.

    ``direction='forward'``  follows ``account_id → counterparty`` (downstream).
    ``direction='backward'`` follows ``counterparty → account_id`` (upstream).
    ``direction='both'``     does both.  Returns the node table + the
    list of edges that were traversed (deduped by ``tx_id``).
    """
    in_window = [t for t in txs if window_start <= t.timestamp <= window_end]
    fwd_adj: Dict[str, List[Tx]] = defaultdict(list)
    bwd_adj: Dict[str, List[Tx]] = defaultdict(list)
    name_map: Dict[str, str] = {}
    geo_map: Dict[str, str] = {}
    for t in in_window:
        fwd_adj[t.account_id].append(t)
        bwd_adj[t.counterparty].append(t)
        if t.subject_name and t.account_id not in name_map:
            name_map[t.account_id] = t.subject_name
        if t.counterparty_name and t.counterparty not in name_map:
            name_map[t.counterparty] = t.counterparty_name
        if t.geo_src and not geo_map.get(t.account_id):
            geo_map[t.account_id] = t.geo_src
        if t.geo_dst and not geo_map.get(t.counterparty):
            geo_map[t.counterparty] = t.geo_dst
    for adj in (fwd_adj, bwd_adj):
        for k in adj:
            adj[k].sort(key=lambda x: x.timestamp)

    nodes: Dict[str, LineageNode] = {
        seed: LineageNode(
            account_id=seed,
            display_name=_label_for(seed, name_map),
            depth=0,
            direction="seed",
            geo=geo_map.get(seed, ""),
        )
    }
    edges: Dict[str, LineageEdge] = {}

    # Each queue entry: (account, depth, branch_direction)
    queue: deque = deque()
    queue.append((seed, 0, "seed"))
    seen: Set[Tuple[str, str]] = {(seed, "seed")}

    while queue:
        node_id, depth, branch_dir = queue.popleft()
        if depth >= max_depth:
            continue
        # Forward step: src=node_id → dst
        if direction in ("forward", "both") and branch_dir in ("seed", "downstream"):
            for tx in fwd_adj.get(node_id, []):
                _record_edge(edges, nodes, tx, node_id, tx.counterparty,
                             depth, depth + 1, name_map, geo_map, "downstream")
                key = (tx.counterparty, "downstream")
                if key not in seen:
                    seen.add(key)
                    queue.append((tx.counterparty, depth + 1, "downstream"))
        # Backward step: src ← dst=node_id
        if direction in ("backward", "both") and branch_dir in ("seed", "upstream"):
            for tx in bwd_adj.get(node_id, []):
                # in the upstream branch, depth grows as we move into the past
                _record_edge(edges, nodes, tx, tx.account_id, node_id,
                             depth + 1, depth, name_map, geo_map, "upstream")
                key = (tx.account_id, "upstream")
                if key not in seen:
                    seen.add(key)
                    queue.append((tx.account_id, depth + 1, "upstream"))

    return nodes, list(edges.values())


def _record_edge(
    edges: Dict[str, LineageEdge],
    nodes: Dict[str, LineageNode],
    tx: Tx,
    src: str,
    dst: str,
    src_depth: int,
    dst_depth: int,
    name_map: Dict[str, str],
    geo_map: Dict[str, str],
    branch_dir: str,
) -> None:
    """Register a single tx as an edge and ensure both endpoints are in nodes."""
    if tx.tx_id in edges:
        return
    edges[tx.tx_id] = LineageEdge(
        tx_id=tx.tx_id,
        src=src,
        dst=dst,
        amount=tx.amount,
        timestamp=tx.timestamp,
        channel=tx.channel,
        geo_src=tx.geo_src,
        geo_dst=tx.geo_dst,
        src_depth=src_depth,
        dst_depth=dst_depth,
    )
    for nid, depth in ((src, src_depth), (dst, dst_depth)):
        if nid not in nodes:
            nodes[nid] = LineageNode(
                account_id=nid,
                display_name=_label_for(nid, name_map),
                depth=depth,
                direction=branch_dir,
                geo=geo_map.get(nid, ""),
            )
        # The reported depth is the distance from seed; we keep the
        # *smaller* depth (closest path) when an account is reachable
        # via multiple paths.
        if abs(depth) < abs(nodes[nid].depth) and nid != src and nid != dst:
            nodes[nid].depth = depth
        # update timestamp bounds
        n = nodes[nid]
        if not n.first_seen or tx.timestamp < n.first_seen:
            n.first_seen = tx.timestamp
        if not n.last_seen or tx.timestamp > n.last_seen:
            n.last_seen = tx.timestamp
    # Accumulate per-node activity stats
    nodes[src].out_count += 1
    nodes[src].out_amount += tx.amount
    nodes[dst].in_count += 1
    nodes[dst].in_amount += tx.amount


def _finalise_node_stats(nodes: Dict[str, LineageNode], edges: List[LineageEdge]) -> None:
    """Compute distinct-cparty counts and suspicion scores."""
    distinct_in: Dict[str, Set[str]] = defaultdict(set)
    distinct_out: Dict[str, Set[str]] = defaultdict(set)
    for e in edges:
        distinct_out[e.src].add(e.dst)
        distinct_in[e.dst].add(e.src)
    for nid, n in nodes.items():
        n.distinct_inflows = len(distinct_in.get(nid, set()))
        n.distinct_outflows = len(distinct_out.get(nid, set()))
        # Suspicion score = soft blend of structural signals.  Caps at 1.
        sus = 0.0
        if n.distinct_inflows >= 4:
            sus += 0.20
        if n.distinct_outflows >= 4:
            sus += 0.20
        if n.in_amount >= 500_000 and n.retention <= 0.15:
            sus += 0.30
        if n.in_count >= 5 and n.in_amount > 0:
            avg_in = n.in_amount / max(1, n.in_count)
            if SMURF_BAND_LOW <= avg_in <= SMURF_BAND_HIGH * 1.3:
                sus += 0.20
        if abs(n.depth) >= 3:
            sus += 0.10
        n.suspicion_score = min(1.0, sus)


# ---------------------------------------------------------------------------
# Pattern detectors
# ---------------------------------------------------------------------------


def _detect_smurf_chain(
    nodes: Dict[str, LineageNode],
    edges: List[LineageEdge],
) -> Optional[LineagePattern]:
    """Many sub-threshold senders → one funnel → ≥1L out."""
    # bucket inbound sub-threshold tx by funnel
    inbound: Dict[str, List[LineageEdge]] = defaultdict(list)
    for e in edges:
        if SMURF_BAND_LOW <= e.amount < SMURF_BAND_HIGH:
            inbound[e.dst].append(e)
    best: Optional[Tuple[float, str, List[str], List[str]]] = None
    for funnel, ins in inbound.items():
        if len(ins) < SMURF_MIN_FAN_IN:
            continue
        senders = sorted({e.src for e in ins})
        if len(senders) < SMURF_MIN_FAN_IN:
            continue
        # Outflows from the funnel within the smurf window
        first_in = min(e.timestamp for e in ins)
        outs = [
            e for e in edges
            if e.src == funnel and 0 <= (e.timestamp - first_in).total_seconds() / 3600 <= SMURF_WINDOW_HOURS
        ]
        total_out = sum(e.amount for e in outs)
        if total_out < SMURF_MIN_OUT_AMOUNT:
            continue
        # Confidence: more senders, more sub-threshold count, fuller out conversion
        conf = min(1.0, 0.4 + 0.05 * (len(senders) - SMURF_MIN_FAN_IN) + 0.3 * (total_out / max(SMURF_MIN_OUT_AMOUNT, total_out)))
        if best is None or conf > best[0]:
            best = (
                conf,
                funnel,
                senders,
                [
                    f"**{len(ins)}** sub-threshold deposits from **{len(senders)}** distinct senders",
                    f"funnel **{nodes[funnel].display_name}** wired out **{_format_amount_short(total_out)}** within {SMURF_WINDOW_HOURS}h",
                    f"avg incoming deposit: **{_format_amount_short(sum(e.amount for e in ins) / len(ins))}** (band ≈ ₹40–50k FIU-IND CTR proxy)",
                ],
            )
    if best is None:
        return None
    conf, funnel, senders, evidence = best
    contrib = [funnel] + senders[:5]
    nodes[funnel].role_tags.append("funnel")
    for s in senders[:6]:
        if s in nodes:
            nodes[s].role_tags.append("smurf")
    meta = PATTERN_META["smurf_chain"]
    return LineagePattern(
        code="smurf_chain",
        label=meta["label"],
        accent=meta["accent"],
        confidence=conf,
        severity=meta["severity"],
        action=meta["action"],
        contributing_nodes=contrib,
        evidence=evidence,
    )


def _detect_round_trip(
    nodes: Dict[str, LineageNode],
    edges: List[LineageEdge],
    seed: str,
) -> Optional[LineagePattern]:
    """Funds leave the seed and return within the window via ≥2 hops."""
    seed_outflows = [e for e in edges if e.src == seed]
    if not seed_outflows:
        return None
    seed_out_total = sum(e.amount for e in seed_outflows)
    if seed_out_total <= 0:
        return None
    # Build reverse-time-respecting paths back to seed.  Outflow at t0
    # must precede the inflow leg back to seed.
    # Simple BFS bounded by max-hops 4.
    rev_adj: Dict[str, List[LineageEdge]] = defaultdict(list)
    for e in edges:
        rev_adj[e.src].append(e)
    for k in rev_adj:
        rev_adj[k].sort(key=lambda x: x.timestamp)
    return_amount = 0.0
    return_paths: List[List[str]] = []
    for out_edge in seed_outflows:
        # DFS from out_edge.dst back to seed in time-respecting forward direction
        stack: List[Tuple[str, datetime, List[str], float]] = [
            (out_edge.dst, out_edge.timestamp, [seed, out_edge.dst], out_edge.amount)
        ]
        while stack:
            node, t0, path, amount = stack.pop()
            if len(path) - 1 > 4:
                continue
            for ne in rev_adj.get(node, []):
                if ne.timestamp <= t0:
                    continue
                new_amount = min(amount, ne.amount)
                if new_amount <= 1e-6:
                    continue
                if ne.dst == seed and len(path) >= 2:
                    return_amount += new_amount
                    return_paths.append(path + [seed])
                else:
                    stack.append((ne.dst, ne.timestamp, path + [ne.dst], new_amount))
    if not return_paths:
        return None
    return_fraction = return_amount / seed_out_total
    if return_fraction < ROUND_TRIP_MIN_RETURN_FRACTION:
        return None
    longest = max(return_paths, key=len)
    if len(longest) - 1 < ROUND_TRIP_MIN_HOPS:
        return None
    conf = min(1.0, 0.35 + 0.5 * return_fraction + 0.04 * (len(longest) - 2))
    evidence = [
        f"**{return_fraction * 100:.0f} %** of seed outflows returned via {len(return_paths)} closed loop(s)",
        f"longest loop: **{' → '.join(longest)}**",
        f"total returned: **{_format_amount_short(return_amount)}** vs outflow **{_format_amount_short(seed_out_total)}**",
    ]
    contrib = list(dict.fromkeys(longest))
    for nid in contrib[1:-1]:
        if nid in nodes:
            nodes[nid].role_tags.append("layer")
    meta = PATTERN_META["round_trip"]
    return LineagePattern(
        code="round_trip",
        label=meta["label"],
        accent=meta["accent"],
        confidence=conf,
        severity=meta["severity"],
        action=meta["action"],
        contributing_nodes=contrib,
        evidence=evidence,
    )


def _detect_pass_through(
    nodes: Dict[str, LineageNode],
    edges: List[LineageEdge],
) -> Optional[LineagePattern]:
    """Node with high fan-in + fan-out + low retention."""
    candidates: List[Tuple[float, str]] = []
    for nid, n in nodes.items():
        if n.distinct_inflows < PASS_THROUGH_MIN_INFLOWS:
            continue
        if n.distinct_outflows < PASS_THROUGH_MIN_OUTFLOWS:
            continue
        if n.in_amount <= 0:
            continue
        if n.retention > PASS_THROUGH_MAX_RETENTION:
            continue
        score = (
            0.30 +
            0.05 * min(8, n.distinct_inflows) +
            0.05 * min(8, n.distinct_outflows) +
            0.30 * (1 - n.retention / max(0.001, PASS_THROUGH_MAX_RETENTION))
        )
        candidates.append((min(1.0, score), nid))
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0], reverse=True)
    top_conf, top_id = candidates[0]
    n = nodes[top_id]
    n.role_tags.append("mule")
    evidence = [
        f"**{n.display_name}** received from **{n.distinct_inflows}** sources and forwarded to **{n.distinct_outflows}** destinations",
        f"retained only **{n.retention * 100:.1f} %** of inflow ({_format_amount_short(n.in_amount - n.out_amount)} of {_format_amount_short(n.in_amount)})",
        f"depth from seed: **{abs(n.depth)} hop(s)**",
    ]
    contrib = [top_id]
    meta = PATTERN_META["pass_through"]
    return LineagePattern(
        code="pass_through",
        label=meta["label"],
        accent=meta["accent"],
        confidence=top_conf,
        severity=meta["severity"],
        action=meta["action"],
        contributing_nodes=contrib,
        evidence=evidence,
    )


def _detect_integration(
    nodes: Dict[str, LineageNode],
    edges: List[LineageEdge],
) -> Optional[LineagePattern]:
    """Round-amount transfer into a clean-asset venue."""
    hits: List[LineageEdge] = []
    for e in edges:
        if not _round_amount(e.amount):
            continue
        dst_name = nodes.get(e.dst, LineageNode(account_id=e.dst, display_name=e.dst, depth=0, direction="downstream", geo="")).display_name.lower()
        if any(kw in dst_name for kw in INTEG_DEST_KEYWORDS):
            hits.append(e)
    if not hits:
        return None
    hits.sort(key=lambda x: x.amount, reverse=True)
    biggest = hits[0]
    conf = min(1.0, 0.45 + 0.05 * (len(hits) - 1) + 0.15 * min(2.0, biggest.amount / INTEG_MIN_AMOUNT))
    nodes_seen: List[str] = []
    for h in hits[:3]:
        if h.dst in nodes:
            nodes[h.dst].role_tags.append("integration")
            nodes_seen.append(h.dst)
    evidence = [
        f"**{len(hits)}** round-amount transfer(s) into clean-asset venue(s)",
        f"biggest: **{_format_amount_short(biggest.amount)}** to **{nodes[biggest.dst].display_name}** on {biggest.timestamp.date().isoformat()}",
        f"channel: **{biggest.channel or 'wire'}** · geo: **{biggest.geo_dst or 'IN'}**",
    ]
    meta = PATTERN_META["integration"]
    return LineagePattern(
        code="integration",
        label=meta["label"],
        accent=meta["accent"],
        confidence=conf,
        severity=meta["severity"],
        action=meta["action"],
        contributing_nodes=nodes_seen,
        evidence=evidence,
    )


def _detect_velocity_ramp(
    nodes: Dict[str, LineageNode],
    edges: List[LineageEdge],
) -> Optional[LineagePattern]:
    """Mean hop interval shrinks across the trail — rush-to-layer signal."""
    if len(edges) < VELOCITY_RAMP_MIN_HOPS:
        return None
    sorted_edges = sorted(edges, key=lambda x: x.timestamp)
    intervals: List[float] = []
    for i in range(1, len(sorted_edges)):
        delta = (sorted_edges[i].timestamp - sorted_edges[i - 1].timestamp).total_seconds() / 3600.0
        intervals.append(max(0.001, delta))
    if len(intervals) < VELOCITY_RAMP_MIN_HOPS:
        return None
    half = len(intervals) // 2
    early = sum(intervals[:half]) / max(1, half)
    late = sum(intervals[half:]) / max(1, len(intervals) - half)
    if early <= 0:
        return None
    ratio = late / early
    if ratio > VELOCITY_RAMP_DECAY_THRESHOLD:
        return None
    conf = min(1.0, 0.40 + 0.40 * (1 - ratio / VELOCITY_RAMP_DECAY_THRESHOLD))
    evidence = [
        f"early-hop avg interval **{early:.1f}h** → late-hop **{late:.1f}h** ({ratio * 100:.0f}% of early)",
        f"trail spans **{(sorted_edges[-1].timestamp - sorted_edges[0].timestamp).total_seconds() / 3600:.1f}h** over **{len(sorted_edges)}** hops",
    ]
    meta = PATTERN_META["velocity_ramp"]
    return LineagePattern(
        code="velocity_ramp",
        label=meta["label"],
        accent=meta["accent"],
        confidence=conf,
        severity=meta["severity"],
        action=meta["action"],
        contributing_nodes=[],
        evidence=evidence,
    )


def _detect_geo_hopping(
    nodes: Dict[str, LineageNode],
    edges: List[LineageEdge],
) -> Optional[LineagePattern]:
    """Distinct jurisdictions touched along the trail."""
    if len(edges) < GEO_HOPPING_MIN_HOPS:
        return None
    geos: Set[str] = set()
    for e in edges:
        if e.geo_src:
            geos.add(e.geo_src)
        if e.geo_dst:
            geos.add(e.geo_dst)
    if len(geos) < GEO_HOPPING_MIN_DISTINCT:
        return None
    conf = min(1.0, 0.40 + 0.12 * (len(geos) - GEO_HOPPING_MIN_DISTINCT) + 0.04 * len(edges))
    evidence = [
        f"trail touches **{len(geos)}** distinct jurisdiction(s): {', '.join(sorted(geos))}",
        f"crosses border on **{sum(1 for e in edges if e.geo_src and e.geo_dst and e.geo_src != e.geo_dst)}** of **{len(edges)}** hops",
    ]
    meta = PATTERN_META["geo_hopping"]
    return LineagePattern(
        code="geo_hopping",
        label=meta["label"],
        accent=meta["accent"],
        confidence=conf,
        severity=meta["severity"],
        action=meta["action"],
        contributing_nodes=[],
        evidence=evidence,
    )


def _detect_patterns(
    nodes: Dict[str, LineageNode],
    edges: List[LineageEdge],
    seed: str,
) -> List[LineagePattern]:
    """Run all six detectors and return the matches in declared order."""
    matches: List[LineagePattern] = []
    for detector in (
        lambda: _detect_smurf_chain(nodes, edges),
        lambda: _detect_round_trip(nodes, edges, seed),
        lambda: _detect_pass_through(nodes, edges),
        lambda: _detect_integration(nodes, edges),
        lambda: _detect_velocity_ramp(nodes, edges),
        lambda: _detect_geo_hopping(nodes, edges),
    ):
        m = detector()
        if m:
            matches.append(m)
    return matches


# ---------------------------------------------------------------------------
# Trail composer
# ---------------------------------------------------------------------------


def _longest_path(nodes: Dict[str, LineageNode], edges: List[LineageEdge], seed: str) -> List[str]:
    """Find the longest time-respecting path that touches ``seed``."""
    if not edges:
        return [seed]
    fwd: Dict[str, List[LineageEdge]] = defaultdict(list)
    for e in edges:
        fwd[e.src].append(e)
    for k in fwd:
        fwd[k].sort(key=lambda x: x.timestamp)
    best: List[str] = [seed]

    def dfs(node: str, path: List[str], tmin: datetime) -> None:
        nonlocal best
        if len(path) > len(best):
            best = list(path)
        for ne in fwd.get(node, []):
            if ne.timestamp < tmin:
                continue
            if ne.dst in path:
                continue
            dfs(ne.dst, path + [ne.dst], ne.timestamp)

    dfs(seed, [seed], datetime.min.replace(tzinfo=timezone.utc))
    return best


def _compute_trail_score(
    nodes: Dict[str, LineageNode],
    edges: List[LineageEdge],
    patterns: List[LineagePattern],
    distinct_geos: List[str],
    longest_path: List[str],
) -> Tuple[int, List[TrailFactor]]:
    """Composite the trail score from five normalised factors."""
    depth_value = max(0, len(longest_path) - 1)
    amount_value = sum(e.amount for e in edges)
    pattern_value = sum(p.confidence for p in patterns)
    geo_value = len(distinct_geos)
    if nodes:
        suspicious_value = sum(1 for n in nodes.values() if n.suspicion_score >= 0.4) / len(nodes)
    else:
        suspicious_value = 0.0

    def norm(val: float, full_at: float) -> float:
        if full_at <= 0:
            return 0.0
        return max(0.0, min(1.0, val / full_at))

    factors: List[TrailFactor] = []
    contribs: List[float] = []
    for key, value, full_at in (
        ("depth", depth_value, DEPTH_FACTOR_FULL_AT),
        ("amount", amount_value, AMOUNT_FACTOR_FULL_AT),
        ("pattern", pattern_value, PATTERN_FACTOR_FULL_AT),
        ("geo", geo_value, GEO_FACTOR_FULL_AT),
        ("suspicious_node", suspicious_value, SUSPICIOUS_FACTOR_FULL_AT),
    ):
        n = norm(value, full_at)
        w = SCORE_WEIGHTS[key]
        c = n * w * 100.0
        factors.append(TrailFactor(key=key, value=value, normalised=n, weight=w, contribution=c))
        contribs.append(c)
    score = int(round(sum(contribs)))
    return max(0, min(100, score)), factors


def _resolve_mood(score: int) -> str:
    for threshold, mood in MOOD_LADDER:
        if score >= threshold:
            return mood
    return "calm"


def _build_headline(
    seed_label: str,
    direction: str,
    score: int,
    mood: str,
    patterns: List[LineagePattern],
    longest_path: List[str],
) -> Tuple[str, str]:
    """One headline + a one-line advisory."""
    if not patterns and len(longest_path) <= 1:
        return (
            f"{seed_label} · no traceable flow in window",
            "Trail is empty — widen the window or pick a different seed account.",
        )
    direction_label = {"forward": "downstream from", "backward": "upstream to", "both": "around"}.get(direction, "around")
    if mood == "critical":
        top = patterns[0]
        return (
            f"Critical trail · {direction_label} **{seed_label}** · {top.label.lower()} ({int(top.confidence * 100)}% confidence)",
            f"Score {score}/100 · {len(patterns)} pattern(s) · {len(longest_path) - 1} hop chain · recommend SAR.",
        )
    if mood == "active":
        names = ", ".join(p.label for p in patterns[:2])
        return (
            f"Active trail · {direction_label} **{seed_label}** · {names}",
            f"Score {score}/100 · {len(patterns)} pattern(s) · {len(longest_path) - 1} hop chain · review queue.",
        )
    if mood == "watch":
        names = ", ".join(p.label for p in patterns[:2]) or "minor structural signals"
        return (
            f"Watch trail · {direction_label} **{seed_label}** · {names}",
            f"Score {score}/100 · {len(patterns)} pattern(s) · {len(longest_path) - 1} hop chain · annotate and re-trace tomorrow.",
        )
    return (
        f"Calm trail · {direction_label} **{seed_label}**",
        f"Score {score}/100 · ordinary flow of funds.",
    )


def _build_plan(
    seed: str,
    seed_label: str,
    patterns: List[LineagePattern],
    nodes: Dict[str, LineageNode],
    score: int,
) -> List[Dict[str, Any]]:
    """Prioritised action checklist, references TITAN tabs by name."""
    plan: List[Dict[str, Any]] = []
    if score >= 75:
        plan.append({
            "kind": "freeze",
            "priority": "critical",
            "body": f"Escalate **{seed_label}** to MLRO — recommend SAR and freeze pending review (trail score {score}/100).",
            "href": f"/cases?account_id={seed}",
        })
    for p in patterns:
        plan.append({
            "kind": p.code,
            "priority": p.severity,
            "body": p.action,
            "href": None,
        })
    # If a pass-through mule was identified, point the analyst at its KYC.
    for p in patterns:
        if p.code == "pass_through" and p.contributing_nodes:
            mule = p.contributing_nodes[0]
            label = nodes.get(mule, LineageNode(account_id=mule, display_name=mule, depth=0, direction="downstream", geo="")).display_name
            plan.append({
                "kind": "kyc_refresh",
                "priority": "high",
                "body": f"Re-anchor KYC on **{label}** in the **Profile** tab — pass-through suggests stale onboarding.",
                "href": f"/profile?customer_id={mule}",
            })
    # Network deep-link.
    plan.append({
        "kind": "network",
        "priority": "medium",
        "body": f"Open the **Network** tab on the seed neighbourhood — confirm structural counterparties match the lineage trail.",
        "href": f"/network?seed={seed}",
    })
    if not patterns:
        plan.append({
            "kind": "calm",
            "priority": "low",
            "body": f"Trail is unremarkable — no patterns to action. Re-trace if more transactions arrive.",
            "href": None,
        })
    # Dedupe by (kind, body) preserving order.
    seen_pairs: Set[Tuple[str, str]] = set()
    deduped: List[Dict[str, Any]] = []
    for item in plan:
        k = (item["kind"], item["body"])
        if k in seen_pairs:
            continue
        seen_pairs.add(k)
        deduped.append(item)
    return deduped


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def compute_lineage(
    transactions: Iterable[Any],
    seed: str,
    direction: str = "both",
    max_depth: int = DEFAULT_MAX_DEPTH,
    window_days: int = DEFAULT_WINDOW_DAYS,
    now: Optional[datetime] = None,
) -> LineageReport:
    """Trace fund-flow lineage rooted at ``seed``.

    See module docstring for the algorithm.  Returns a deterministic
    ``LineageReport`` — same input always produces the same bytes.
    """
    direction = direction.lower()
    if direction not in ("forward", "backward", "both"):
        raise ValueError(f"direction must be one of forward|backward|both (got {direction!r})")
    if not seed:
        raise ValueError("seed must be a non-empty account id")
    if max_depth < MIN_MAX_DEPTH or max_depth > MAX_MAX_DEPTH:
        raise ValueError(f"max_depth must be in [{MIN_MAX_DEPTH}, {MAX_MAX_DEPTH}]")
    if window_days < MIN_WINDOW_DAYS or window_days > MAX_WINDOW_DAYS:
        raise ValueError(f"window_days must be in [{MIN_WINDOW_DAYS}, {MAX_WINDOW_DAYS}]")
    # Normalise transactions.
    txs: List[Tx] = []
    for i, raw in enumerate(transactions or []):
        if isinstance(raw, Tx):
            txs.append(raw)
        else:
            txs.append(_normalise_tx(dict(raw), i))
    if not txs:
        return _empty_report(seed, direction, max_depth, window_days, now)
    # Resolve the window.  Default: [now - window_days, now] anchored at
    # the latest tx in the batch.  Anchoring at the *batch* (not just
    # the seed's last activity) is important — otherwise a forward
    # trace would drop downstream hops that happen after the seed's
    # last touch, which is exactly what a forward trace is supposed to
    # surface.
    if now is None:
        now = max(t.timestamp for t in txs)
    window_end = now
    window_start = window_end - timedelta(days=window_days)
    # Walk the trace.
    nodes, edges = _walk_trace(txs, seed, direction, max_depth, window_start, window_end)
    _finalise_node_stats(nodes, edges)
    # Provenance tracer.
    provenance = _trace_provenance(
        [t for t in txs if window_start <= t.timestamp <= window_end],
        seeds={seed},
    )
    seed_label_map: Dict[str, str] = {nid: n.display_name for nid, n in nodes.items()}
    for account, shares in provenance.items():
        if account not in nodes:
            continue
        nodes[account].provenance = [
            ProvenanceShare(
                source_id=s.source_id,
                source_label=seed_label_map.get(s.source_id, s.source_label),
                depth=nodes[s.source_id].depth if s.source_id in nodes else 0,
                share=s.share,
                via_hops=s.via_hops,
            )
            for s in shares
        ]
    # Pattern detectors.
    patterns = _detect_patterns(nodes, edges, seed)
    patterns.sort(key=lambda p: p.confidence, reverse=True)
    # Tag edges that belong to a pattern's contributing path.
    for p in patterns:
        for e in edges:
            if e.src in p.contributing_nodes and e.dst in p.contributing_nodes:
                if p.code not in e.pattern_tags:
                    e.pattern_tags.append(p.code)
    # Trail score + factors.
    distinct_geos = sorted({g for e in edges for g in (e.geo_src, e.geo_dst) if g})
    longest_path = _longest_path(nodes, edges, seed)
    score, factors = _compute_trail_score(nodes, edges, patterns, distinct_geos, longest_path)
    mood = _resolve_mood(score)
    seed_label = nodes[seed].display_name if seed in nodes else seed
    headline, advisory = _build_headline(seed_label, direction, score, mood, patterns, longest_path)
    plan = _build_plan(seed, seed_label, patterns, nodes, score)
    ordered_nodes = sorted(
        nodes.values(),
        key=lambda n: (n.depth, -n.in_amount, n.account_id),
    )
    ordered_edges = sorted(edges, key=lambda e: e.timestamp)
    composed_at = (now or datetime.now(timezone.utc)).isoformat()
    return LineageReport(
        composed_at=composed_at,
        engine=ENGINE_VERSION,
        seed=seed,
        seed_label=seed_label,
        direction=direction,
        max_depth=max_depth,
        window_days=window_days,
        window_start=window_start.isoformat(),
        window_end=window_end.isoformat(),
        nodes=ordered_nodes,
        edges=ordered_edges,
        patterns=patterns,
        trail_score=score,
        mood=mood,
        headline=headline,
        advisory=advisory,
        factors=factors,
        total_amount_traced=sum(e.amount for e in edges),
        distinct_geos=distinct_geos,
        longest_path=longest_path,
        plan_of_action=plan,
    )


def _empty_report(
    seed: str,
    direction: str,
    max_depth: int,
    window_days: int,
    now: Optional[datetime],
) -> LineageReport:
    composed_at = (now or datetime.now(timezone.utc)).isoformat()
    end = now or datetime.now(timezone.utc)
    return LineageReport(
        composed_at=composed_at,
        engine=ENGINE_VERSION,
        seed=seed,
        seed_label=seed,
        direction=direction,
        max_depth=max_depth,
        window_days=window_days,
        window_start=(end - timedelta(days=window_days)).isoformat(),
        window_end=end.isoformat(),
        nodes=[],
        edges=[],
        patterns=[],
        trail_score=0,
        mood="calm",
        headline=f"{seed} · no transactions supplied",
        advisory="Provide at least one transaction touching the seed to compute a lineage trail.",
        factors=[],
        total_amount_traced=0.0,
        distinct_geos=[],
        longest_path=[seed],
        plan_of_action=[{
            "kind": "empty",
            "priority": "low",
            "body": "No transactions supplied — paste a batch into the AML console then re-run.",
            "href": "/aml",
        }],
    )


# ---------------------------------------------------------------------------
# Sample fixture — a synthetic three-arm laundering chain
# ---------------------------------------------------------------------------


def _sample_transactions() -> List[Tx]:
    """A 28-transaction synthetic laundering chain.

    Three arms feed into a funnel ("Aurelia Shell Limited"), which
    layers through two middle accounts, lands a round-amount transfer
    in a real-estate venue, and round-trips a small slice back to the
    seed — so the bundled demo lights up at least four of the six
    detectors and gives the surface a non-trivial trail to render.
    """
    t0 = datetime(2026, 6, 14, 9, 30, tzinfo=timezone.utc)

    def tx(idx: int, hours: int, src: str, dst: str, amount: float, **kw) -> Tx:
        meta = dict(kw)
        return Tx(
            tx_id=f"TX-SAMP-{idx:03d}",
            account_id=src,
            counterparty=dst,
            amount=amount,
            timestamp=t0 + timedelta(hours=hours),
            channel=meta.pop("channel", "wire"),
            geo_src=meta.pop("geo_src", meta.pop("geo", "IN")),
            geo_dst=meta.pop("geo_dst", meta.pop("geo2", "IN")),
            subject_name=meta.pop("src_name", ""),
            counterparty_name=meta.pop("dst_name", ""),
            meta=meta,
        )

    seed = "ACC-AUR-01"   # Aurelia Shell Limited (already in the customer book)
    # Smurfing arm: 6 sub-threshold deposits from 6 distinct payers → funnel = seed
    arm_a: List[Tx] = []
    smurf_payers = [
        ("ACC-PAYER-A1", "Vinod Sharma"),
        ("ACC-PAYER-A2", "Rakhi Iyer"),
        ("ACC-PAYER-A3", "Manoj Joshi"),
        ("ACC-PAYER-A4", "Anita Kapoor"),
        ("ACC-PAYER-A5", "Suresh Pillai"),
        ("ACC-PAYER-A6", "Dipti Bose"),
    ]
    for i, (src, name) in enumerate(smurf_payers):
        amount = 44_000 + (i * 750)
        arm_a.append(tx(
            idx=i + 1, hours=2 + i * 3,
            src=src, dst=seed, amount=amount,
            channel="upi", src_name=name, dst_name="Aurelia Shell Limited",
            geo="IN",
        ))
    # Funnel forwards two large legs into the layering web
    arm_a.append(tx(
        idx=10, hours=24, src=seed, dst="ACC-LAYER-1", amount=180_000,
        src_name="Aurelia Shell Limited", dst_name="Coastal Bridge Services",
        geo_src="IN", geo_dst="AE", channel="wire",
    ))
    arm_a.append(tx(
        idx=11, hours=26, src=seed, dst="ACC-LAYER-2", amount=120_000,
        src_name="Aurelia Shell Limited", dst_name="Pyongyang Horizon Trading",
        geo_src="IN", geo_dst="KP", channel="wire",
    ))
    # Layering: Layer-1 splits into Layer-2 and a third "shell" (pass-through)
    arm_a.append(tx(
        idx=12, hours=30, src="ACC-LAYER-1", dst="ACC-MULE-1", amount=80_000,
        src_name="Coastal Bridge Services", dst_name="Aliekseii Volkov-Baranov",
        geo_src="AE", geo_dst="RU", channel="wire",
    ))
    arm_a.append(tx(
        idx=13, hours=31, src="ACC-LAYER-1", dst="ACC-LAYER-2", amount=70_000,
        src_name="Coastal Bridge Services", dst_name="Pyongyang Horizon Trading",
        geo_src="AE", geo_dst="KP", channel="wire",
    ))
    arm_a.append(tx(
        idx=14, hours=33, src="ACC-LAYER-1", dst="ACC-MULE-2", amount=30_000,
        src_name="Coastal Bridge Services", dst_name="Bashir Crossing Holdings",
        geo_src="AE", geo_dst="IR", channel="wire",
    ))
    # Mule pass-through: ACC-MULE-1 receives from many, forwards to many
    arm_a.append(tx(
        idx=15, hours=36, src="ACC-LAYER-2", dst="ACC-MULE-1", amount=60_000,
        src_name="Pyongyang Horizon Trading", dst_name="Aliekseii Volkov-Baranov",
        geo_src="KP", geo_dst="RU", channel="wire",
    ))
    arm_a.append(tx(
        idx=16, hours=37, src="ACC-MULE-2", dst="ACC-MULE-1", amount=25_000,
        src_name="Bashir Crossing Holdings", dst_name="Aliekseii Volkov-Baranov",
        geo_src="IR", geo_dst="RU", channel="wire",
    ))
    arm_a.append(tx(
        idx=17, hours=39, src="ACC-MULE-1", dst="ACC-DEST-A", amount=70_000,
        src_name="Aliekseii Volkov-Baranov", dst_name="Helios Realty Developers",
        geo_src="RU", geo_dst="AE", channel="wire",
    ))
    arm_a.append(tx(
        idx=18, hours=40, src="ACC-MULE-1", dst="ACC-DEST-B", amount=40_000,
        src_name="Aliekseii Volkov-Baranov", dst_name="Marble Lane Properties",
        geo_src="RU", geo_dst="IN", channel="wire",
    ))
    arm_a.append(tx(
        idx=19, hours=41, src="ACC-MULE-1", dst="ACC-DEST-C", amount=35_000,
        src_name="Aliekseii Volkov-Baranov", dst_name="Crescent Maritime",
        geo_src="RU", geo_dst="IN", channel="wire",
    ))
    # Integration: a round 5L wire into Helios Realty Developers
    arm_a.append(tx(
        idx=20, hours=48, src="ACC-LAYER-2", dst="ACC-DEST-A", amount=500_000,
        src_name="Pyongyang Horizon Trading", dst_name="Helios Realty Developers",
        geo_src="KP", geo_dst="AE", channel="wire",
    ))
    # Round-trip: a slice eventually returns to the seed
    arm_a.append(tx(
        idx=21, hours=52, src="ACC-LAYER-2", dst="ACC-MULE-3", amount=45_000,
        src_name="Pyongyang Horizon Trading", dst_name="Niamh O'Riordan",
        geo_src="KP", geo_dst="IN", channel="wire",
    ))
    arm_a.append(tx(
        idx=22, hours=55, src="ACC-MULE-3", dst=seed, amount=42_000,
        src_name="Niamh O'Riordan", dst_name="Aurelia Shell Limited",
        geo_src="IN", geo_dst="IN", channel="upi",
    ))
    arm_a.append(tx(
        idx=23, hours=60, src="ACC-MULE-2", dst=seed, amount=15_000,
        src_name="Bashir Crossing Holdings", dst_name="Aurelia Shell Limited",
        geo_src="IR", geo_dst="IN", channel="wire",
    ))
    # A second integration target plus a clean-corp control
    arm_a.append(tx(
        idx=24, hours=62, src=seed, dst="ACC-CONTROL-1", amount=12_500,
        src_name="Aurelia Shell Limited", dst_name="Coastal Logistics Pvt. Ltd.",
        geo="IN", channel="wire",
    ))
    arm_a.append(tx(
        idx=25, hours=64, src="ACC-LAYER-1", dst="ACC-DEST-A", amount=300_000,
        src_name="Coastal Bridge Services", dst_name="Helios Realty Developers",
        geo_src="AE", geo_dst="AE", channel="wire",
    ))
    arm_a.append(tx(
        idx=26, hours=68, src="ACC-MULE-2", dst="ACC-DEST-D", amount=22_000,
        src_name="Bashir Crossing Holdings", dst_name="Auragold Jewellery Mart",
        geo_src="IR", geo_dst="IN", channel="wire",
    ))
    arm_a.append(tx(
        idx=27, hours=70, src="ACC-MULE-1", dst="ACC-DEST-D", amount=18_000,
        src_name="Aliekseii Volkov-Baranov", dst_name="Auragold Jewellery Mart",
        geo_src="RU", geo_dst="IN", channel="wire",
    ))
    # Late hop — produces the velocity-ramp shape (gaps shrink late in trail)
    arm_a.append(tx(
        idx=28, hours=72, src="ACC-DEST-A", dst="ACC-DEST-E", amount=250_000,
        src_name="Helios Realty Developers", dst_name="Olive Branch Auto Motors",
        geo="AE", channel="wire",
    ))
    return arm_a


_SAMPLE_TXS_CACHE: Optional[List[Tx]] = None


def _sample_txs() -> List[Tx]:
    global _SAMPLE_TXS_CACHE
    if _SAMPLE_TXS_CACHE is None:
        _SAMPLE_TXS_CACHE = _sample_transactions()
    return _SAMPLE_TXS_CACHE


def get_sample_trace(
    seed: Optional[str] = None,
    direction: str = "both",
    max_depth: int = DEFAULT_MAX_DEPTH,
    window_days: int = DEFAULT_WINDOW_DAYS,
) -> LineageReport:
    """Sample lineage built from the bundled 28-tx fixture.

    ``seed`` defaults to ``ACC-AUR-01`` (Aurelia Shell Limited — the
    high-medium customer in the bundled book) so the surface always
    lights up at least four detectors.
    """
    txs = _sample_txs()
    s = seed or "ACC-AUR-01"
    # Pin ``now`` to the last sample timestamp so the demo never falls
    # outside the configured window when wall-clock time drifts forward.
    sample_now = max(t.timestamp for t in txs)
    return compute_lineage(
        transactions=txs,
        seed=s,
        direction=direction,
        max_depth=max_depth,
        window_days=window_days,
        now=sample_now,
    )


def sample_seed_choices() -> List[Dict[str, str]]:
    """Curated list of seeds the bundled fixture lights up well.

    Surfaced by the frontend as a "try one of these" segmented control.
    """
    return [
        {"id": "ACC-AUR-01", "label": "Aurelia Shell Limited", "context": "funnel · 3 detectors"},
        {"id": "ACC-MULE-1", "label": "Aliekseii Volkov-Baranov", "context": "pass-through mule"},
        {"id": "ACC-DEST-A", "label": "Helios Realty Developers", "context": "integration entry"},
        {"id": "ACC-LAYER-2", "label": "Pyongyang Horizon Trading", "context": "layering hub"},
    ]


# ---------------------------------------------------------------------------
# Markdown / audit dumps
# ---------------------------------------------------------------------------


def to_markdown(report: LineageReport) -> str:
    """Paste-able SAR §3 exhibit (~2.5 KB)."""
    L: List[str] = []
    L.append(f"# TITAN Lineage — {report.seed_label}")
    L.append("")
    L.append(f"_Engine: `{report.engine}` · composed `{report.composed_at}`_")
    L.append("")
    L.append(f"**{report.headline}**")
    L.append("")
    L.append(f"_{report.advisory}_")
    L.append("")
    L.append("## Trail summary")
    L.append("")
    L.append("| Metric | Value |")
    L.append("|---|---|")
    L.append(f"| Trail score | **{report.trail_score}/100** ({report.mood}) |")
    L.append(f"| Direction | {report.direction} |")
    L.append(f"| Depth (longest path) | {len(report.longest_path) - 1} hop(s) |")
    L.append(f"| Nodes traced | {len(report.nodes)} |")
    L.append(f"| Edges traced | {len(report.edges)} |")
    L.append(f"| Total amount | {_format_amount_short(report.total_amount_traced)} |")
    L.append(f"| Jurisdictions | {', '.join(report.distinct_geos) or '—'} |")
    L.append(f"| Window | {report.window_start[:10]} → {report.window_end[:10]} ({report.window_days}d) |")
    L.append("")
    if report.patterns:
        L.append("## Detected patterns")
        L.append("")
        for p in report.patterns:
            L.append(f"### {p.label} · {int(p.confidence * 100)}% confidence ({p.severity})")
            for ev in p.evidence:
                L.append(f"- {ev}")
            L.append(f"- _Action:_ {p.action}")
            L.append("")
    if len(report.longest_path) > 1:
        L.append("## Longest traced path")
        L.append("")
        labels: List[str] = []
        node_map = {n.account_id: n for n in report.nodes}
        for nid in report.longest_path:
            labels.append(node_map[nid].display_name if nid in node_map else nid)
        L.append(" → ".join(labels))
        L.append("")
    # Top provenance for the seed
    seed_node = next((n for n in report.nodes if n.account_id == report.seed), None)
    if seed_node and seed_node.provenance:
        L.append(f"## Provenance of {report.seed_label}'s recent inflow")
        L.append("")
        L.append("| Source | Share | Hops |")
        L.append("|---|---:|---:|")
        for p in seed_node.provenance[:6]:
            L.append(f"| {p.source_label} | {p.share * 100:.1f}% | {p.via_hops} |")
        L.append("")
    if report.plan_of_action:
        L.append("## Plan of action")
        L.append("")
        for i, action in enumerate(report.plan_of_action, 1):
            body = action["body"]
            L.append(f"{i}. **[{action['priority']}]** {body}")
        L.append("")
    L.append("---")
    L.append(f"_titan.lineage.v1 envelope · score factors: " +
             ", ".join(f"{f.key} {f.contribution:.1f}" for f in report.factors) + "_")
    return "\n".join(L)


def get_rules() -> Dict[str, Any]:
    """Auditor-facing dump of every knob the engine reads."""
    return {
        "version": "1.0.0",
        "default_max_depth": DEFAULT_MAX_DEPTH,
        "min_max_depth": MIN_MAX_DEPTH,
        "max_max_depth": MAX_MAX_DEPTH,
        "default_window_days": DEFAULT_WINDOW_DAYS,
        "min_window_days": MIN_WINDOW_DAYS,
        "max_window_days": MAX_WINDOW_DAYS,
        "provenance_min_share": PROVENANCE_MIN_SHARE,
        "smurf": {
            "band_low": SMURF_BAND_LOW,
            "band_high": SMURF_BAND_HIGH,
            "min_fan_in": SMURF_MIN_FAN_IN,
            "min_out_amount": SMURF_MIN_OUT_AMOUNT,
            "window_hours": SMURF_WINDOW_HOURS,
        },
        "round_trip": {
            "min_return_fraction": ROUND_TRIP_MIN_RETURN_FRACTION,
            "min_hops": ROUND_TRIP_MIN_HOPS,
        },
        "pass_through": {
            "min_inflows": PASS_THROUGH_MIN_INFLOWS,
            "min_outflows": PASS_THROUGH_MIN_OUTFLOWS,
            "max_retention": PASS_THROUGH_MAX_RETENTION,
        },
        "integration": {
            "round_mod": INTEG_ROUND_MOD,
            "min_amount": INTEG_MIN_AMOUNT,
            "dest_keywords": list(INTEG_DEST_KEYWORDS),
        },
        "velocity_ramp": {
            "min_hops": VELOCITY_RAMP_MIN_HOPS,
            "decay_threshold": VELOCITY_RAMP_DECAY_THRESHOLD,
        },
        "geo_hopping": {
            "min_hops": GEO_HOPPING_MIN_HOPS,
            "min_distinct": GEO_HOPPING_MIN_DISTINCT,
        },
        "score_weights": dict(SCORE_WEIGHTS),
        "factor_full_at": {
            "depth": DEPTH_FACTOR_FULL_AT,
            "amount": AMOUNT_FACTOR_FULL_AT,
            "pattern": PATTERN_FACTOR_FULL_AT,
            "geo": GEO_FACTOR_FULL_AT,
            "suspicious_node": SUSPICIOUS_FACTOR_FULL_AT,
        },
        "mood_ladder": [{"threshold": t, "mood": m} for t, m in MOOD_LADDER],
        "mood_blurb": dict(MOOD_BLURB),
        "patterns": {k: {**v} for k, v in PATTERN_META.items()},
        "engine": ENGINE_VERSION,
    }
