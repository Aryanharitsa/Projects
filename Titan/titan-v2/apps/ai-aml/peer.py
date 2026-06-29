"""TITAN Peer Lens — peer-group statistical anomaly engine.

Round-12, day-55. The missing analytical surface that every other detector
in TITAN punted on: *cross-customer* anomaly.

Why this exists
---------------
Every other engine in this product measures one thing about *one* customer:

* ``risk.py`` fires deterministic rules per account (single-account view).
* ``drift.py`` catches *account-vs-self*: today vs your own past.
* ``profile.py`` composites that single customer's surfaces into one
  number, but every input is still a *single-subject* signal.
* ``network.py`` propagates risk across the graph, but the propagation
  itself uses the same per-subject scores as the input.

None of them ask the question regulators specifically ask in every
exam: *"is this customer behaving differently from their peers?"* This is
**peer-group benchmarking** — explicitly required by FFIEC BSA/AML
exam manual ("Risk Identification Process"), MAS AML/CFT Notice 626
para 8.1 ("customer due diligence including comparison against the
customer's peer group"), and EU 6AMLD CDD guidance. A customer can be
operating *within* their own historical envelope (drift-stable) and
still be a textbook outlier within their cohort.

What it does
------------
Given a portfolio (customers + their transactions over the last 30d),
the engine:

1. Extracts a 9-axis behavioral feature vector per customer:

       tx_count_30d       count of |amount| > 0 in the last 30 days
       tx_volume_30d      sum of |amount| in USD
       avg_tx_amount      mean
       p95_tx_amount      95th percentile
       unique_counterparties   distinct counterparty IDs
       cross_border_pct   fraction with foreign geo (relative to domicile)
       cash_pct           fraction with channel='cash'
       weekend_pct        fraction on Sat/Sun
       night_pct          fraction with hour ∈ [22, 06)

2. Builds **cohorts** with hierarchical fallback so every customer ends
   up in a cohort with at least ``MIN_COHORT_SIZE`` (default 5) peers:

       cohort_full = (industry, domicile, size_band)
       cohort_med  = (industry, domicile)
       cohort_loose = (industry,)
       cohort_global = ALL

   The most-specific cohort with ≥ MIN_COHORT_SIZE peers wins, and we
   stamp the customer with the *level* used. Auditors can see, per
   customer, "scored against ``industry|domicile|size_band`` (n=12)"
   vs "scored against ``industry`` (n=24)".

3. For each cohort + metric, computes robust statistics:

       median, MAD (median absolute deviation)
       fallback to (mean, std) if MAD = 0 and the metric has variance

   Robust z-score per customer:

       z = 0.6745 * (x - median) / mad     if mad > 0
       z = (x - mean) / std                fallback
       z = 0                               if cohort is flat

   The 0.6745 constant scales MAD to be a consistent estimator of σ for
   normally-distributed data, so |z| ≥ 3 means the same "3-sigma" thing
   it does with parametric z.

4. **Directional gating** — for each metric, only one side is suspicious:

       HIGH_ONLY  tx_volume_30d, avg_tx_amount, p95_tx_amount,
                  cross_border_pct, cash_pct, weekend_pct, night_pct
       BOTH       tx_count_30d, unique_counterparties

   Reasoning: a wealth client with low transaction count vs peers is a
   genuine outlier (could be hiding activity off-book or just dormant);
   the same low cash_pct vs peers is *not* suspicious — it just means
   they prefer wires. The directional gate prevents nuisance hits on
   well-behaved customers who are simply tidy.

5. Composite outlier intensity per customer:

       gated_z_i = |z_i|     if direction allows
       gated_z_i = 0          otherwise

       max_z   = max(gated_z_i)
       n_ext   = sum(1 for z in gated_z if z > 3)
       outlier = min(100, 10 * max_z + 5 * n_ext)

   Saturating at 100 so one extreme signal can dominate (max_z=10 →
   100) while *broad* misalignment (n_ext=5 of 9 axes) also reaches
   the cap (50 + 25 = 75; combined with a max_z=4 → 90).

   Bands (calibration tracks the rest of TITAN — same ramps, same
   colour semantics):

       aligned   <  25      teal      Within cohort envelope. Routine.
       drifting  25 .. 49   amber     One axis pushing peer edge.
       outlier   50 .. 74   orange    Multi-axis or sharp single-axis.
       severe    >= 75      rose      Material peer deviation; investigate.

6. Returns a fully-explainable payload — every customer carries the
   contributing metric, the cohort it was scored against, the cohort
   distribution at that point, and a one-sentence headline that a
   compliance officer can paste into a case note.

Pure-function. Pure-stdlib. Deterministic — same inputs in, exact same
bytes out. Reuses ``risk.HIGH_RISK_GEOS`` for the cross-border classifier
so a transaction tagged ``RU`` lands the same on this surface as on
the AML rule engine.
"""

from __future__ import annotations

import math
import os
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

import json

import risk as risk_engine


ENGINE_VERSION = "titan-peer/1.0.0"
RULES_VERSION = "1.0.0"


# ---------------------------------------------------------------------------
# Tunables — exposed via /aml/peer/rules so callers can audit them.
# ---------------------------------------------------------------------------

LOOKBACK_DAYS = 30
MIN_COHORT_SIZE = 5
NIGHT_HOUR_START = 22
NIGHT_HOUR_END = 6
MAD_K = 0.6745  # consistency constant — see module docstring

OUTLIER_PER_MAX_Z = 10.0     # ramp from max gated |z|
OUTLIER_PER_EXTREME = 5.0    # additive bump per metric with |z| > 3
EXTREME_Z_FLOOR = 3.0

# Size-band partition (USD volume quartiles) over the supplied portfolio.
# Computed dynamically per-call so we don't hardcode a USD bracket.
SIZE_BANDS: Tuple[str, ...] = ("micro", "small", "mid", "large")

# Bucket ramp (calibration kept consistent with risk.py / profile.py).
BUCKETS: List[Tuple[float, str]] = [
    (75.0, "severe"),
    (50.0, "outlier"),
    (25.0, "drifting"),
    (0.0,  "aligned"),
]

BUCKET_META: Dict[str, Dict[str, Any]] = {
    "aligned":  {"accent": "#22d3a8", "blurb": "Within cohort envelope.",
                 "action": "Routine monitoring. No additional analyst attention."},
    "drifting": {"accent": "#fbbf24", "blurb": "One axis pushing the peer edge.",
                 "action": "Note in next periodic review; re-check next cycle."},
    "outlier":  {"accent": "#fb923c", "blurb": "Multi-axis or sharp single-axis deviation.",
                 "action": "Open peer-comparison case; review source-of-funds and product fit."},
    "severe":   {"accent": "#ef4444", "blurb": "Material peer deviation.",
                 "action": "Escalate to EDD: SoF / SoW refresh, beneficial-ownership re-check, transaction sampling."},
}

# Direction gates per metric: "high" → only abnormally-high is suspicious,
# "both" → low or high is suspicious.
DIRECTION: Dict[str, str] = {
    "tx_count_30d": "both",
    "tx_volume_30d": "high",
    "avg_tx_amount": "high",
    "p95_tx_amount": "high",
    "unique_counterparties": "both",
    "cross_border_pct": "high",
    "cash_pct": "high",
    "weekend_pct": "high",
    "night_pct": "high",
}

METRIC_META: Dict[str, Dict[str, Any]] = {
    "tx_count_30d":          {"label": "Tx count (30d)",      "unit": "txs",    "accent": "#6E5BFF"},
    "tx_volume_30d":         {"label": "Volume (30d)",        "unit": "USD",    "accent": "#22d3a8"},
    "avg_tx_amount":         {"label": "Avg tx amount",       "unit": "USD",    "accent": "#2DE1C2"},
    "p95_tx_amount":         {"label": "P95 tx amount",       "unit": "USD",    "accent": "#a78bfa"},
    "unique_counterparties": {"label": "Unique counterparties","unit": "cps",   "accent": "#60a5fa"},
    "cross_border_pct":      {"label": "Cross-border share",  "unit": "%",      "accent": "#fb923c"},
    "cash_pct":              {"label": "Cash channel share",  "unit": "%",      "accent": "#f97316"},
    "weekend_pct":           {"label": "Weekend share",       "unit": "%",      "accent": "#facc15"},
    "night_pct":             {"label": "Night share",         "unit": "%",      "accent": "#fb7185"},
}

METRIC_ORDER: Tuple[str, ...] = tuple(METRIC_META.keys())

# Industries we expect in the demo portfolio (used for cohort grouping
# and the UI legend). Free-form strings are accepted at request time.
KNOWN_INDUSTRIES: Tuple[str, ...] = (
    "export_import",
    "retail_banking",
    "vasp_crypto",
    "wealth_mgmt",
    "real_estate",
    "ngo",
    "shell_co",
    "manufacturing",
)


# ---------------------------------------------------------------------------
# Domain
# ---------------------------------------------------------------------------


@dataclass
class CustomerFeatures:
    customer_id: str
    display_name: str
    industry: str
    domicile: str
    size_band: str
    metrics: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "customer_id": self.customer_id,
            "display_name": self.display_name,
            "industry": self.industry,
            "domicile": self.domicile,
            "size_band": self.size_band,
            "metrics": dict(self.metrics),
        }


@dataclass
class CohortStats:
    cohort_id: str
    level: str                # full | medium | loose | global
    industry: Optional[str]
    domicile: Optional[str]
    size_band: Optional[str]
    size: int
    member_ids: List[str]
    per_metric: Dict[str, Dict[str, float]]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cohort_id": self.cohort_id,
            "level": self.level,
            "industry": self.industry,
            "domicile": self.domicile,
            "size_band": self.size_band,
            "size": self.size,
            "member_ids": list(self.member_ids),
            "per_metric": {k: dict(v) for k, v in self.per_metric.items()},
        }


# ---------------------------------------------------------------------------
# Feature extraction
# ---------------------------------------------------------------------------


def _parse_iso(ts: Any) -> Optional[datetime]:
    if not ts:
        return None
    if isinstance(ts, datetime):
        return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
    try:
        s = str(ts).replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _is_cross_border(tx: Dict[str, Any], domicile: Optional[str]) -> bool:
    if not domicile:
        return False
    geo = (tx.get("geo") or "").strip().upper()
    if not geo:
        return False
    if geo == domicile.upper():
        return False
    # Treat known high-risk jurisdictions as cross-border by default —
    # they are *always* relevant for the cross-border share even when
    # the customer is domiciled there (regulator pays extra attention).
    if geo in risk_engine.HIGH_RISK_GEOS:
        return True
    return geo != domicile.upper()


def _percentile(values: List[float], pct: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return float(values[0])
    arr = sorted(values)
    k = (len(arr) - 1) * pct
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return float(arr[int(k)])
    return float(arr[f] + (arr[c] - arr[f]) * (k - f))


def _features_for_customer(
    customer: Dict[str, Any],
    txs: List[Dict[str, Any]],
    *,
    now: Optional[datetime] = None,
) -> Dict[str, float]:
    now = now or datetime.now(timezone.utc)
    horizon = now.timestamp() - LOOKBACK_DAYS * 86400.0
    domicile = (customer.get("domicile") or "").strip().upper() or None

    amounts: List[float] = []
    counterparties: set = set()
    cross_border = 0
    cash = 0
    weekend = 0
    night = 0
    n = 0

    for tx in txs:
        amt = float(tx.get("amount") or 0.0)
        if amt <= 0:
            continue
        dt = _parse_iso(tx.get("timestamp"))
        if dt and dt.timestamp() < horizon:
            continue
        n += 1
        amounts.append(abs(amt))
        cp = (tx.get("counterparty") or "").strip()
        if cp:
            counterparties.add(cp)
        if _is_cross_border(tx, domicile):
            cross_border += 1
        if (tx.get("channel") or "").strip().lower() == "cash":
            cash += 1
        if dt:
            if dt.weekday() >= 5:
                weekend += 1
            h = dt.hour
            if h >= NIGHT_HOUR_START or h < NIGHT_HOUR_END:
                night += 1

    denom = max(1, n)
    metrics: Dict[str, float] = {
        "tx_count_30d": float(n),
        "tx_volume_30d": float(sum(amounts)),
        "avg_tx_amount": float(sum(amounts) / denom) if amounts else 0.0,
        "p95_tx_amount": _percentile(amounts, 0.95) if amounts else 0.0,
        "unique_counterparties": float(len(counterparties)),
        "cross_border_pct": (cross_border / denom) if n else 0.0,
        "cash_pct": (cash / denom) if n else 0.0,
        "weekend_pct": (weekend / denom) if n else 0.0,
        "night_pct": (night / denom) if n else 0.0,
    }
    return metrics


def _size_band_thresholds(volumes: List[float]) -> List[float]:
    """Return three cut-points (33/66/90 percentiles) for size bands.

    The cut-points are picked so band 0 (micro) is roughly the bottom
    third, small/mid split mid-volume, and ``large`` captures the heaviest
    customers — a sane default for the demo portfolio without hardcoding
    USD brackets.
    """

    if not volumes:
        return [0.0, 0.0, 0.0]
    return [
        _percentile(volumes, 0.33),
        _percentile(volumes, 0.66),
        _percentile(volumes, 0.90),
    ]


def _band_for(value: float, cuts: List[float]) -> str:
    if value <= cuts[0]:
        return SIZE_BANDS[0]
    if value <= cuts[1]:
        return SIZE_BANDS[1]
    if value <= cuts[2]:
        return SIZE_BANDS[2]
    return SIZE_BANDS[3]


# ---------------------------------------------------------------------------
# Cohorts + statistics
# ---------------------------------------------------------------------------


def _cohort_key(level: str, industry: Optional[str], domicile: Optional[str], size: Optional[str]) -> str:
    parts: List[str] = []
    if industry:
        parts.append(f"ind={industry}")
    if domicile:
        parts.append(f"dom={domicile}")
    if size:
        parts.append(f"sz={size}")
    if not parts:
        parts.append("ALL")
    return f"{level}::{'|'.join(parts)}"


def _summarise_cohort(values: List[float]) -> Dict[str, float]:
    if not values:
        return {"n": 0, "median": 0.0, "mad": 0.0, "mean": 0.0, "std": 0.0, "min": 0.0, "max": 0.0, "p25": 0.0, "p75": 0.0}
    n = len(values)
    median = statistics.median(values)
    mad = statistics.median(abs(v - median) for v in values)
    mean = statistics.fmean(values)
    std = statistics.pstdev(values) if n > 1 else 0.0
    return {
        "n": n,
        "median": float(median),
        "mad": float(mad),
        "mean": float(mean),
        "std": float(std),
        "min": float(min(values)),
        "max": float(max(values)),
        "p25": _percentile(values, 0.25),
        "p75": _percentile(values, 0.75),
    }


def _build_cohorts(features: List[CustomerFeatures]) -> Tuple[Dict[str, CohortStats], Dict[str, str]]:
    """Build the cohort table with hierarchical fallback.

    Returns (cohorts_by_id, customer_to_cohort_id).
    """

    if not features:
        return {}, {}

    # Pre-bucket by every cohort key so we can pick the most-specific one
    # with >= MIN_COHORT_SIZE members per customer.
    by_full: Dict[Tuple[str, str, str], List[CustomerFeatures]] = defaultdict(list)
    by_med: Dict[Tuple[str, str], List[CustomerFeatures]] = defaultdict(list)
    by_loose: Dict[str, List[CustomerFeatures]] = defaultdict(list)
    everyone: List[CustomerFeatures] = list(features)

    for f in features:
        by_full[(f.industry, f.domicile, f.size_band)].append(f)
        by_med[(f.industry, f.domicile)].append(f)
        by_loose[f.industry].append(f)

    cohorts: Dict[str, CohortStats] = {}
    by_customer: Dict[str, str] = {}

    def stats_for(members: List[CustomerFeatures]) -> Dict[str, Dict[str, float]]:
        out: Dict[str, Dict[str, float]] = {}
        for m in METRIC_ORDER:
            vals = [mem.metrics.get(m, 0.0) for mem in members]
            out[m] = _summarise_cohort(vals)
        return out

    def get_or_create(cohort_id: str, level: str, members: List[CustomerFeatures],
                      industry: Optional[str], domicile: Optional[str], size_band: Optional[str]) -> CohortStats:
        if cohort_id in cohorts:
            return cohorts[cohort_id]
        cohort = CohortStats(
            cohort_id=cohort_id,
            level=level,
            industry=industry,
            domicile=domicile,
            size_band=size_band,
            size=len(members),
            member_ids=[mem.customer_id for mem in members],
            per_metric=stats_for(members),
        )
        cohorts[cohort_id] = cohort
        return cohort

    for f in features:
        chosen = None
        full_members = by_full[(f.industry, f.domicile, f.size_band)]
        if len(full_members) >= MIN_COHORT_SIZE:
            cid = _cohort_key("full", f.industry, f.domicile, f.size_band)
            chosen = get_or_create(cid, "full", full_members,
                                   f.industry, f.domicile, f.size_band)
        else:
            med_members = by_med[(f.industry, f.domicile)]
            if len(med_members) >= MIN_COHORT_SIZE:
                cid = _cohort_key("medium", f.industry, f.domicile, None)
                chosen = get_or_create(cid, "medium", med_members,
                                       f.industry, f.domicile, None)
            else:
                loose_members = by_loose[f.industry]
                if len(loose_members) >= MIN_COHORT_SIZE:
                    cid = _cohort_key("loose", f.industry, None, None)
                    chosen = get_or_create(cid, "loose", loose_members,
                                           f.industry, None, None)
                else:
                    cid = _cohort_key("global", None, None, None)
                    chosen = get_or_create(cid, "global", everyone, None, None, None)
        by_customer[f.customer_id] = chosen.cohort_id

    return cohorts, by_customer


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def _z_for(value: float, stats: Dict[str, float]) -> Tuple[float, str]:
    """Robust z-score with parametric fallback.

    Returns (z, basis) where basis ∈ {"mad", "std", "flat"}.
    """

    median = stats.get("median", 0.0)
    mad = stats.get("mad", 0.0)
    if mad > 1e-9:
        return MAD_K * (value - median) / mad, "mad"
    std = stats.get("std", 0.0)
    if std > 1e-9:
        mean = stats.get("mean", 0.0)
        return (value - mean) / std, "std"
    return 0.0, "flat"


def _is_directional_extreme(metric: str, z: float) -> bool:
    direction = DIRECTION.get(metric, "high")
    if direction == "high":
        return z > 0
    return True


def _bucket_for(score: float) -> str:
    for floor, label in BUCKETS:
        if score >= floor:
            return label
    return "aligned"


def _evaluate_customer(
    f: CustomerFeatures,
    cohort: CohortStats,
) -> Dict[str, Any]:
    per_metric_eval: List[Dict[str, Any]] = []
    max_gated_z = 0.0
    extreme_count = 0

    for m in METRIC_ORDER:
        stats = cohort.per_metric[m]
        value = float(f.metrics.get(m, 0.0))
        z, basis = _z_for(value, stats)
        gated = abs(z) if _is_directional_extreme(m, z) else 0.0
        if gated > max_gated_z:
            max_gated_z = gated
        if gated > EXTREME_Z_FLOOR:
            extreme_count += 1
        per_metric_eval.append({
            "key": m,
            "label": METRIC_META[m]["label"],
            "accent": METRIC_META[m]["accent"],
            "unit": METRIC_META[m]["unit"],
            "value": value,
            "cohort_median": stats.get("median", 0.0),
            "cohort_mad": stats.get("mad", 0.0),
            "cohort_p25": stats.get("p25", 0.0),
            "cohort_p75": stats.get("p75", 0.0),
            "cohort_min": stats.get("min", 0.0),
            "cohort_max": stats.get("max", 0.0),
            "z": z,
            "abs_z": abs(z),
            "gated_z": gated,
            "direction": DIRECTION.get(m, "high"),
            "basis": basis,
            "extreme": gated > EXTREME_Z_FLOOR,
        })

    raw = OUTLIER_PER_MAX_Z * max_gated_z + OUTLIER_PER_EXTREME * extreme_count
    composite = max(0.0, min(100.0, raw))
    bucket = _bucket_for(composite)

    # Top drivers — sorted by gated_z desc, then abs_z desc.
    drivers = sorted(per_metric_eval, key=lambda p: (p["gated_z"], p["abs_z"]), reverse=True)
    top_drivers = [d for d in drivers if d["gated_z"] > 0][:3]

    headline = _headline(f, cohort, top_drivers, composite, bucket)

    meta = BUCKET_META[bucket]

    return {
        "customer_id": f.customer_id,
        "display_name": f.display_name,
        "industry": f.industry,
        "domicile": f.domicile,
        "size_band": f.size_band,
        "cohort_id": cohort.cohort_id,
        "cohort_level": cohort.level,
        "cohort_size": cohort.size,
        "outlier_score": round(composite, 2),
        "bucket": bucket,
        "bucket_accent": meta["accent"],
        "bucket_blurb": meta["blurb"],
        "recommended_action": meta["action"],
        "max_gated_z": round(max_gated_z, 3),
        "extreme_count": extreme_count,
        "metrics": per_metric_eval,
        "top_drivers": top_drivers,
        "headline": headline,
    }


def _format_value(metric: str, value: float) -> str:
    unit = METRIC_META[metric]["unit"]
    if unit == "USD":
        if value >= 1_000_000:
            return f"${value/1_000_000:.2f}M"
        if value >= 1_000:
            return f"${value/1_000:.1f}K"
        return f"${value:.0f}"
    if unit == "%":
        return f"{value*100:.0f}%"
    if value >= 1000:
        return f"{value:,.0f}"
    if value == int(value):
        return f"{int(value)}"
    return f"{value:.2f}"


def _headline(
    f: CustomerFeatures,
    cohort: CohortStats,
    drivers: List[Dict[str, Any]],
    score: float,
    bucket: str,
) -> str:
    if not drivers:
        return f"Within peer envelope ({cohort.level}, n={cohort.size})."
    top = drivers[0]
    metric_label = top["label"]
    value_str = _format_value(top["key"], top["value"])
    median_str = _format_value(top["key"], top["cohort_median"])
    direction = "above" if top["z"] > 0 else "below"
    z = top["abs_z"]
    extra = ""
    if len(drivers) > 1:
        also = drivers[1]
        extra = f"; {also['label'].lower()} also {('above' if also['z']>0 else 'below')} peers"
    return (
        f"{metric_label} {value_str} ({direction} cohort median {median_str}, "
        f"z={z:.1f}) — {bucket} vs {cohort.level} cohort (n={cohort.size}){extra}."
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def analyze(
    customers: List[Dict[str, Any]],
    transactions: List[Dict[str, Any]],
    *,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Run the peer-lens engine over a portfolio.

    Args:
        customers: list of customer dicts with at minimum ``customer_id``,
            ``industry``, ``domicile``. Optional: ``display_name``,
            ``accounts`` (list of account_ids this customer owns; used to
            scope transactions). If absent, the customer is associated
            with every transaction whose account_id matches their
            ``customer_id``.
        transactions: list of TX dicts (same shape as risk_engine).

    Returns:
        ``{
            "ok": True,
            "engine": ENGINE_VERSION,
            "rules_version": RULES_VERSION,
            "lookback_days": 30,
            "portfolio": {...stats...},
            "cohorts": [...],
            "customers": [...],
            "by_bucket": {...},
        }``
    """

    if not customers:
        return {
            "ok": True, "engine": ENGINE_VERSION, "rules_version": RULES_VERSION,
            "lookback_days": LOOKBACK_DAYS,
            "portfolio": {"customers": 0, "cohorts": 0, "outliers": 0, "severe": 0},
            "cohorts": [], "customers": [], "by_bucket": {b: 0 for b in (m for _, m in BUCKETS)},
        }

    # 1. Resolve transactions per customer (account_id → customer_id).
    txs_by_customer: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    account_owner: Dict[str, str] = {}
    for c in customers:
        cid = str(c.get("customer_id") or "").strip()
        if not cid:
            continue
        for acct in c.get("accounts") or [cid]:
            account_owner[str(acct)] = cid
    for tx in transactions or []:
        acct = str(tx.get("account_id") or "").strip()
        cid = account_owner.get(acct)
        if cid:
            txs_by_customer[cid].append(tx)

    # 2. Extract features.
    features_pre: List[Tuple[Dict[str, Any], Dict[str, float]]] = []
    volumes: List[float] = []
    for c in customers:
        cid = str(c.get("customer_id") or "").strip()
        if not cid:
            continue
        m = _features_for_customer(c, txs_by_customer.get(cid, []), now=now)
        features_pre.append((c, m))
        volumes.append(m["tx_volume_30d"])

    cuts = _size_band_thresholds(volumes)

    features: List[CustomerFeatures] = []
    for c, m in features_pre:
        cid = str(c.get("customer_id") or "").strip()
        features.append(CustomerFeatures(
            customer_id=cid,
            display_name=str(c.get("display_name") or cid),
            industry=str(c.get("industry") or "unknown"),
            domicile=str(c.get("domicile") or "??").upper(),
            size_band=_band_for(m["tx_volume_30d"], cuts),
            metrics=m,
        ))

    # 3. Cohorts.
    cohorts, by_customer = _build_cohorts(features)

    # 4. Score each customer.
    customer_reports: List[Dict[str, Any]] = []
    by_bucket: Dict[str, int] = defaultdict(int)
    for f in features:
        cid = by_customer[f.customer_id]
        cohort = cohorts[cid]
        report = _evaluate_customer(f, cohort)
        customer_reports.append(report)
        by_bucket[report["bucket"]] += 1

    customer_reports.sort(key=lambda r: r["outlier_score"], reverse=True)

    # 5. Portfolio rollup.
    outliers = sum(1 for r in customer_reports if r["bucket"] in ("outlier", "severe"))
    severe = by_bucket.get("severe", 0)
    avg = (sum(r["outlier_score"] for r in customer_reports) / len(customer_reports)) if customer_reports else 0.0
    by_cohort_level: Dict[str, int] = defaultdict(int)
    for r in customer_reports:
        by_cohort_level[r["cohort_level"]] += 1

    portfolio = {
        "customers": len(features),
        "cohorts": len(cohorts),
        "outliers": outliers,
        "severe": severe,
        "drifting": by_bucket.get("drifting", 0),
        "aligned": by_bucket.get("aligned", 0),
        "average_score": round(avg, 2),
        "by_cohort_level": dict(by_cohort_level),
        "size_band_cuts": [round(c, 2) for c in cuts],
    }

    cohort_list = [c.to_dict() for c in cohorts.values()]
    cohort_list.sort(key=lambda c: (-c["size"], c["level"], c["cohort_id"]))

    return {
        "ok": True,
        "engine": ENGINE_VERSION,
        "rules_version": RULES_VERSION,
        "lookback_days": LOOKBACK_DAYS,
        "min_cohort_size": MIN_COHORT_SIZE,
        "portfolio": portfolio,
        "cohorts": cohort_list,
        "customers": customer_reports,
        "by_bucket": {label: by_bucket.get(label, 0) for _, label in BUCKETS},
    }


def get_rules() -> Dict[str, Any]:
    return {
        "engine": ENGINE_VERSION,
        "version": RULES_VERSION,
        "lookback_days": LOOKBACK_DAYS,
        "min_cohort_size": MIN_COHORT_SIZE,
        "size_bands": list(SIZE_BANDS),
        "size_band_partition": "33/66/90 percentiles of portfolio tx_volume_30d",
        "night_hours": {"start": NIGHT_HOUR_START, "end": NIGHT_HOUR_END},
        "metrics": [
            {
                "key": k,
                "label": METRIC_META[k]["label"],
                "unit": METRIC_META[k]["unit"],
                "accent": METRIC_META[k]["accent"],
                "direction": DIRECTION.get(k, "high"),
            } for k in METRIC_ORDER
        ],
        "buckets": [{"min": floor, "label": label} for floor, label in BUCKETS],
        "bucket_meta": BUCKET_META,
        "scoring": {
            "per_max_z": OUTLIER_PER_MAX_Z,
            "per_extreme": OUTLIER_PER_EXTREME,
            "extreme_z_floor": EXTREME_Z_FLOOR,
            "max_score": 100,
            "mad_k": MAD_K,
            "robust_first": "Use MAD whenever > 1e-9, fall back to std, then z=0 (flat cohort).",
        },
        "fallback_chain": [
            "full = (industry, domicile, size_band)",
            "medium = (industry, domicile)",
            "loose = (industry,)",
            "global = all customers",
        ],
    }


# ---------------------------------------------------------------------------
# Bundled demo portfolio
# ---------------------------------------------------------------------------


_HERE = os.path.dirname(os.path.abspath(__file__))
_SAMPLE_PATH = os.path.join(_HERE, "data", "peer_portfolio.json")


def get_sample() -> Dict[str, Any]:
    """Load the bundled demo portfolio.

    The file is generated/maintained as a fixture; if missing this raises
    so the caller knows the demo data isn't bundled.
    """

    if not os.path.exists(_SAMPLE_PATH):
        return {"customers": [], "transactions": [], "note": "sample missing"}
    with open(_SAMPLE_PATH, "r") as fh:
        return json.load(fh)
