"""TITAN AML behavioral-drift engine — account-vs-self anomaly detection.

The existing risk engine catches *threshold breaches* — eight rules that
fire when behavior crosses a tunable line. That model misses the slow,
quiet failures every compliance team actually pays for:

* A *sleeper* account that lay dormant for months and then suddenly
  wakes up. Every individual transaction is small, in-policy, and
  triggers zero rules — but the account is now behaving like a
  completely different entity than it did six months ago.
* A *takeover*: the account holder hasn't changed, but the *operator*
  has. Same name, same wallet, completely different counterparty list,
  completely different hours of activity.
* A *mule-recruitment*: a legitimate account abruptly starts forwarding
  funds within minutes of receipt, where it used to hold a stable cash
  balance.

The unifying signal is **distribution drift**: the account's current
behavior no longer matches its own historical baseline. That's what
this module measures — deterministically, with no ML deps, using
classical two-sample distribution distances.

How it works
------------
For each account we split its transactions into a *baseline* window
(the longer, older period) and a *current* window (the recent period).
We summarise each window as a **behavioral fingerprint** across ten
axes:

* amount distribution           (Kolmogorov-Smirnov statistic)
* hour-of-day pattern           (Jensen-Shannon divergence, /ln(2))
* day-of-week pattern           (Jensen-Shannon, /ln(2))
* inflow/outflow direction      (absolute delta in ratio)
* velocity (tx / active day)    (log-ratio, scaled)
* counterparty diversity        (HHI concentration delta)
* counterparty novelty          (% of current counterparties never
                                 seen in the baseline)
* geographic mix                (total-variation distance)
* round-amount tendency         (rate delta)
* median ticket shift           (|log2| of medians, scaled)

Each axis produces a 0..1 sub-score where 0 = identical to baseline
and 1 = maximally different. The composite drift is a fixed weighted
sum (`WEIGHTS` below) clipped to [0, 1] and bucketed into a verdict
(`stable | mild | drifting | erratic | transformed`). The engine also
emits a plain-English narrative, a ranked list of "top drivers"
(which axes carry the bulk of the change), a per-counterparty
contribution table (who is new, who got disproportionately more
active), and a change-point estimate (the earliest day when a
rolling window of recent activity first diverged from the long
baseline by more than a small floor).

Pure function of (transactions, split, weights). Same input → same
report. Determinism is the whole point — analysts have to defend the
verdict to a regulator.
"""

from __future__ import annotations

import math
import statistics
from bisect import bisect_right
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import risk as risk_engine

ENGINE_VERSION = "titan-drift/1.0.0"


# ---------------------------------------------------------------------------
# Tunables — auditor-facing
# ---------------------------------------------------------------------------

DEFAULT_BASELINE_FRACTION = 0.7
MIN_BASELINE_TXS = 6
MIN_CURRENT_TXS = 3

# Composite weights. Sum to 1.0. Documented in README + /aml/drift/rules.
WEIGHTS: Dict[str, float] = {
    "amount":             0.18,
    "hour":               0.14,
    "dow":                0.10,
    "direction":          0.10,
    "velocity":           0.08,
    "cparty_diversity":   0.08,
    "cparty_novelty":     0.12,
    "geo":                0.08,
    "round_rate":         0.05,
    "median_shift":       0.07,
}
assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9, "drift WEIGHTS must sum to 1"

# Verdict bands (composite drift score → verdict).
BANDS: Tuple[Tuple[float, str], ...] = (
    (0.75, "transformed"),
    (0.55, "erratic"),
    (0.35, "drifting"),
    (0.18, "mild"),
    (0.00, "stable"),
)

# A driver is "primary" if its weighted contribution clears this share of
# the composite. Used to label top-drivers in the report.
DRIVER_FLOOR = 0.10

# Change-point: how big a rolling-window KS against the baseline must be
# to count as "drift onset".
CHANGE_POINT_KS_FLOOR = 0.30

# Friendly labels surfaced everywhere.
DIM_LABELS: Dict[str, str] = {
    "amount":            "Amount distribution",
    "hour":              "Hour-of-day pattern",
    "dow":               "Day-of-week pattern",
    "direction":         "Inflow/outflow balance",
    "velocity":          "Transaction velocity",
    "cparty_diversity":  "Counterparty concentration",
    "cparty_novelty":    "New counterparties",
    "geo":               "Geographic footprint",
    "round_rate":        "Round-amount tendency",
    "median_shift":      "Median ticket size",
}

DIM_ORDER: Tuple[str, ...] = (
    "amount",
    "hour",
    "dow",
    "direction",
    "velocity",
    "cparty_diversity",
    "cparty_novelty",
    "geo",
    "round_rate",
    "median_shift",
)


# ---------------------------------------------------------------------------
# Domain types
# ---------------------------------------------------------------------------


@dataclass
class _Tx:
    account_id: str
    counterparty: str
    amount: float
    timestamp: datetime
    role: str  # "out" if account is sender, "in" if receiver
    geo: str = ""


@dataclass
class DimensionDrift:
    key: str
    label: str
    score: float           # 0..1
    weight: float          # share of composite
    contribution: float    # score * weight (== share of composite explained)
    baseline_summary: Dict[str, Any]
    current_summary: Dict[str, Any]
    detail: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "score": round(self.score, 4),
            "weight": self.weight,
            "contribution": round(self.contribution, 4),
            "baseline": self.baseline_summary,
            "current": self.current_summary,
            "detail": self.detail,
        }


@dataclass
class CounterpartyContribution:
    counterparty: str
    baseline_count: int
    current_count: int
    baseline_volume: float
    current_volume: float
    is_new: bool
    activity_lift: float  # current_count / max(baseline_count, 1) - 1, or +inf for new
    volume_lift: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "counterparty": self.counterparty,
            "baseline_count": self.baseline_count,
            "current_count": self.current_count,
            "baseline_volume": round(self.baseline_volume, 2),
            "current_volume": round(self.current_volume, 2),
            "is_new": self.is_new,
            "activity_lift": round(self.activity_lift, 3) if math.isfinite(self.activity_lift) else None,
            "volume_lift": round(self.volume_lift, 3) if math.isfinite(self.volume_lift) else None,
        }


@dataclass
class ChangePoint:
    detected: bool
    onset_iso: Optional[str]
    days_ago: Optional[int]
    rolling_ks: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "detected": self.detected,
            "onset_iso": self.onset_iso,
            "days_ago": self.days_ago,
            "rolling_ks": self.rolling_ks,
        }


@dataclass
class AccountDrift:
    account_id: str
    display_name: str
    overall: float
    verdict: str
    headline: str
    drivers: List[str]
    narrative: str
    baseline_window: Dict[str, Any]
    current_window: Dict[str, Any]
    dimensions: List[DimensionDrift]
    counterparties: List[CounterpartyContribution]
    change_point: ChangePoint
    suggested_action: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "account_id": self.account_id,
            "display_name": self.display_name,
            "overall": round(self.overall, 4),
            "verdict": self.verdict,
            "headline": self.headline,
            "drivers": self.drivers,
            "narrative": self.narrative,
            "baseline_window": self.baseline_window,
            "current_window": self.current_window,
            "dimensions": [d.to_dict() for d in self.dimensions],
            "counterparties": [c.to_dict() for c in self.counterparties],
            "change_point": self.change_point.to_dict(),
            "suggested_action": self.suggested_action,
        }


# ---------------------------------------------------------------------------
# Stats primitives — pure stdlib, no numpy
# ---------------------------------------------------------------------------


def _ks_statistic(a: Sequence[float], b: Sequence[float]) -> float:
    """Two-sample Kolmogorov-Smirnov: sup |F_a(x) - F_b(x)|."""
    if not a or not b:
        return 0.0
    sa = sorted(a)
    sb = sorted(b)
    na, nb = len(sa), len(sb)
    pooled = sorted(set(sa) | set(sb))
    best = 0.0
    for x in pooled:
        fa = bisect_right(sa, x) / na
        fb = bisect_right(sb, x) / nb
        d = abs(fa - fb)
        if d > best:
            best = d
    return best


def _normalize_hist(counts: Sequence[float]) -> List[float]:
    total = sum(counts)
    if total <= 0:
        return [0.0] * len(counts)
    return [c / total for c in counts]


def _js_divergence(p: Sequence[float], q: Sequence[float]) -> float:
    """Symmetric Jensen-Shannon. Returns value in [0, ln 2]."""
    eps = 1e-12
    m = [0.5 * (pi + qi) for pi, qi in zip(p, q)]

    def _kl(x: Sequence[float], y: Sequence[float]) -> float:
        s = 0.0
        for xi, yi in zip(x, y):
            if xi > 0:
                s += xi * math.log((xi + eps) / (yi + eps))
        return s

    return 0.5 * _kl(p, m) + 0.5 * _kl(q, m)


def _js_normalized(p: Sequence[float], q: Sequence[float]) -> float:
    """Jensen-Shannon scaled to [0, 1] by dividing by ln 2."""
    return min(1.0, max(0.0, _js_divergence(p, q) / math.log(2)))


def _tvd(p: Sequence[float], q: Sequence[float]) -> float:
    """Total-variation distance. Value in [0, 1]."""
    return 0.5 * sum(abs(pi - qi) for pi, qi in zip(p, q))


def _herfindahl(counts: Sequence[float]) -> float:
    """HHI of a count distribution, in [0, 1]. 1 = perfectly concentrated."""
    total = sum(counts)
    if total <= 0:
        return 0.0
    return sum((c / total) ** 2 for c in counts)


def _clip01(x: float) -> float:
    if x < 0:
        return 0.0
    if x > 1:
        return 1.0
    return x


# ---------------------------------------------------------------------------
# Window assembly
# ---------------------------------------------------------------------------


def _parse_ts(raw: Any) -> datetime:
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
    s = (str(raw) if raw is not None else "").strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        dt = datetime.now(timezone.utc)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _normalise_account_txs(account_id: str, rows: Iterable[Dict[str, Any]]) -> List[_Tx]:
    out: List[_Tx] = []
    for r in rows:
        try:
            sender = str(r.get("account_id", "")).strip()
            recv = str(r.get("counterparty", "")).strip()
            amt = float(r.get("amount", 0) or 0)
            if not sender or not recv or amt <= 0:
                continue
            if sender == account_id:
                cp = recv
                role = "out"
            elif recv == account_id:
                cp = sender
                role = "in"
            else:
                continue
            out.append(
                _Tx(
                    account_id=account_id,
                    counterparty=cp,
                    amount=amt,
                    timestamp=_parse_ts(r.get("timestamp", "")),
                    role=role,
                    geo=str(r.get("geo", "") or "").upper(),
                )
            )
        except (TypeError, ValueError):
            continue
    out.sort(key=lambda t: t.timestamp)
    return out


def _split_window(
    txs: List[_Tx],
    *,
    baseline_fraction: float,
    split_at: Optional[datetime],
) -> Tuple[List[_Tx], List[_Tx]]:
    if not txs:
        return [], []
    if split_at is not None:
        base = [t for t in txs if t.timestamp < split_at]
        cur = [t for t in txs if t.timestamp >= split_at]
        return base, cur
    # Default: split at the timestamp that puts `baseline_fraction` of txs in
    # the baseline. Tie-break: include borderline tx in the baseline so the
    # current window stays strictly the recent slice.
    n = len(txs)
    cut = max(1, min(n - 1, int(round(n * baseline_fraction))))
    return txs[:cut], txs[cut:]


def _window_summary(txs: List[_Tx]) -> Dict[str, Any]:
    if not txs:
        return {
            "tx_count": 0,
            "start_iso": None,
            "end_iso": None,
            "span_days": 0.0,
            "active_days": 0,
            "volume_total": 0.0,
            "median_amount": 0.0,
            "inflow_share": 0.0,
            "unique_counterparties": 0,
        }
    start = txs[0].timestamp
    end = txs[-1].timestamp
    span = max((end - start).total_seconds() / 86400.0, 0.0)
    active_days = len({(t.timestamp.year, t.timestamp.month, t.timestamp.day) for t in txs})
    inflow = sum(t.amount for t in txs if t.role == "in")
    total = sum(t.amount for t in txs)
    return {
        "tx_count": len(txs),
        "start_iso": start.isoformat(),
        "end_iso": end.isoformat(),
        "span_days": round(span, 2),
        "active_days": active_days,
        "volume_total": round(total, 2),
        "median_amount": round(statistics.median(t.amount for t in txs), 2),
        "inflow_share": round(inflow / total, 4) if total > 0 else 0.0,
        "unique_counterparties": len({t.counterparty for t in txs}),
    }


# ---------------------------------------------------------------------------
# Per-dimension drift calculators
# ---------------------------------------------------------------------------


def _amount_drift(base: List[_Tx], cur: List[_Tx]) -> DimensionDrift:
    a = [t.amount for t in base]
    b = [t.amount for t in cur]
    score = _ks_statistic(a, b) if a and b else 0.0

    def _sum(amts: List[float]) -> Dict[str, Any]:
        if not amts:
            return {"n": 0}
        return {
            "n": len(amts),
            "min": round(min(amts), 2),
            "p25": round(_quantile(amts, 0.25), 2),
            "median": round(statistics.median(amts), 2),
            "p75": round(_quantile(amts, 0.75), 2),
            "max": round(max(amts), 2),
            "mean": round(sum(amts) / len(amts), 2),
        }

    detail = (
        f"KS = {score:.2f}; median {_safe_div(statistics.median(b) if b else 0.0, statistics.median(a) if a else 1.0):+.2f}× baseline"
        if a and b
        else "insufficient data"
    )
    return DimensionDrift(
        key="amount",
        label=DIM_LABELS["amount"],
        score=_clip01(score),
        weight=WEIGHTS["amount"],
        contribution=WEIGHTS["amount"] * _clip01(score),
        baseline_summary=_sum(a),
        current_summary=_sum(b),
        detail=detail,
    )


def _quantile(xs: List[float], q: float) -> float:
    if not xs:
        return 0.0
    s = sorted(xs)
    if len(s) == 1:
        return s[0]
    idx = q * (len(s) - 1)
    lo = int(math.floor(idx))
    hi = int(math.ceil(idx))
    if lo == hi:
        return s[lo]
    return s[lo] + (s[hi] - s[lo]) * (idx - lo)


def _safe_div(a: float, b: float) -> float:
    if not b:
        return 0.0 if a == 0 else float("inf")
    return a / b


def _hour_drift(base: List[_Tx], cur: List[_Tx]) -> DimensionDrift:
    def _hist(txs: List[_Tx]) -> List[float]:
        h = [0.0] * 24
        for t in txs:
            h[t.timestamp.hour] += 1
        return _normalize_hist(h)

    p = _hist(base)
    q = _hist(cur)
    score = _js_normalized(p, q) if base and cur else 0.0
    return DimensionDrift(
        key="hour",
        label=DIM_LABELS["hour"],
        score=_clip01(score),
        weight=WEIGHTS["hour"],
        contribution=WEIGHTS["hour"] * _clip01(score),
        baseline_summary={"histogram": [round(x, 4) for x in p]},
        current_summary={"histogram": [round(x, 4) for x in q]},
        detail=(
            f"JS = {score:.2f}; "
            f"baseline peak hour {p.index(max(p)) if base else '—'} → "
            f"current peak hour {q.index(max(q)) if cur else '—'}"
            if base and cur
            else "insufficient data"
        ),
    )


def _dow_drift(base: List[_Tx], cur: List[_Tx]) -> DimensionDrift:
    def _hist(txs: List[_Tx]) -> List[float]:
        h = [0.0] * 7
        for t in txs:
            h[t.timestamp.weekday()] += 1
        return _normalize_hist(h)

    p = _hist(base)
    q = _hist(cur)
    score = _js_normalized(p, q) if base and cur else 0.0
    return DimensionDrift(
        key="dow",
        label=DIM_LABELS["dow"],
        score=_clip01(score),
        weight=WEIGHTS["dow"],
        contribution=WEIGHTS["dow"] * _clip01(score),
        baseline_summary={"histogram": [round(x, 4) for x in p]},
        current_summary={"histogram": [round(x, 4) for x in q]},
        detail=f"JS = {score:.2f}",
    )


def _direction_drift(base: List[_Tx], cur: List[_Tx]) -> DimensionDrift:
    def _ratio(txs: List[_Tx]) -> float:
        total = sum(t.amount for t in txs)
        if total <= 0:
            return 0.0
        inflow = sum(t.amount for t in txs if t.role == "in")
        return inflow / total

    rb = _ratio(base)
    rc = _ratio(cur)
    # Map a 0..1 ratio delta into a heavier 0..1 score: a 30% swing
    # already feels material to an investigator. Cap at 1.0.
    raw = abs(rc - rb)
    score = _clip01(raw / 0.5)
    return DimensionDrift(
        key="direction",
        label=DIM_LABELS["direction"],
        score=score,
        weight=WEIGHTS["direction"],
        contribution=WEIGHTS["direction"] * score,
        baseline_summary={"inflow_share": round(rb, 4)},
        current_summary={"inflow_share": round(rc, 4)},
        detail=f"{int(round(rb*100))}% in → {int(round(rc*100))}% in (Δ {int(round((rc-rb)*100)):+d}pp)",
    )


def _velocity_drift(base: List[_Tx], cur: List[_Tx]) -> DimensionDrift:
    def _per_day(txs: List[_Tx]) -> float:
        if not txs:
            return 0.0
        days = len({(t.timestamp.year, t.timestamp.month, t.timestamp.day) for t in txs}) or 1
        return len(txs) / days

    vb = _per_day(base)
    vc = _per_day(cur)
    # Log-ratio, scaled. A 5x or 1/5x change saturates the score.
    if vb <= 0 and vc <= 0:
        score = 0.0
    elif vb <= 0 or vc <= 0:
        score = 1.0
    else:
        score = _clip01(abs(math.log(vc / vb)) / math.log(5))
    return DimensionDrift(
        key="velocity",
        label=DIM_LABELS["velocity"],
        score=score,
        weight=WEIGHTS["velocity"],
        contribution=WEIGHTS["velocity"] * score,
        baseline_summary={"tx_per_active_day": round(vb, 3)},
        current_summary={"tx_per_active_day": round(vc, 3)},
        detail=f"{vb:.1f}/day → {vc:.1f}/day",
    )


def _cparty_diversity_drift(base: List[_Tx], cur: List[_Tx]) -> DimensionDrift:
    def _counts(txs: List[_Tx]) -> Dict[str, int]:
        out: Dict[str, int] = defaultdict(int)
        for t in txs:
            out[t.counterparty] += 1
        return dict(out)

    cb = _counts(base)
    cc = _counts(cur)
    hb = _herfindahl(list(cb.values()))
    hc = _herfindahl(list(cc.values()))
    # HHI ranges [0,1]; treat absolute delta as the score directly.
    score = _clip01(abs(hc - hb))
    return DimensionDrift(
        key="cparty_diversity",
        label=DIM_LABELS["cparty_diversity"],
        score=score,
        weight=WEIGHTS["cparty_diversity"],
        contribution=WEIGHTS["cparty_diversity"] * score,
        baseline_summary={"unique": len(cb), "hhi": round(hb, 4)},
        current_summary={"unique": len(cc), "hhi": round(hc, 4)},
        detail=(
            f"HHI {hb:.2f} → {hc:.2f} "
            f"({len(cb)} → {len(cc)} unique counterparties)"
        ),
    )


def _cparty_novelty_drift(base: List[_Tx], cur: List[_Tx]) -> DimensionDrift:
    bset = {t.counterparty for t in base}
    if not cur:
        score = 0.0
        new_count = 0
        new_share = 0.0
    else:
        new = {t.counterparty for t in cur} - bset
        new_count = len(new)
        new_share = new_count / len({t.counterparty for t in cur}) if cur else 0.0
        score = _clip01(new_share)
    return DimensionDrift(
        key="cparty_novelty",
        label=DIM_LABELS["cparty_novelty"],
        score=score,
        weight=WEIGHTS["cparty_novelty"],
        contribution=WEIGHTS["cparty_novelty"] * score,
        baseline_summary={"unique": len(bset)},
        current_summary={"unique_new": new_count, "new_share": round(new_share, 4)},
        detail=f"{int(round(new_share*100))}% of current counterparties are new",
    )


def _geo_drift(base: List[_Tx], cur: List[_Tx]) -> DimensionDrift:
    def _mix(txs: List[_Tx]) -> Dict[str, float]:
        counts: Dict[str, int] = defaultdict(int)
        for t in txs:
            counts[t.geo or "—"] += 1
        total = sum(counts.values())
        return {k: v / total for k, v in counts.items()} if total else {}

    pb = _mix(base)
    pc = _mix(cur)
    keys = sorted(set(pb) | set(pc))
    p = [pb.get(k, 0.0) for k in keys]
    q = [pc.get(k, 0.0) for k in keys]
    score = _tvd(p, q) if keys else 0.0
    return DimensionDrift(
        key="geo",
        label=DIM_LABELS["geo"],
        score=_clip01(score),
        weight=WEIGHTS["geo"],
        contribution=WEIGHTS["geo"] * _clip01(score),
        baseline_summary={"mix": {k: round(v, 3) for k, v in pb.items()}},
        current_summary={"mix": {k: round(v, 3) for k, v in pc.items()}},
        detail=f"TVD = {score:.2f}",
    )


def _round_rate_drift(base: List[_Tx], cur: List[_Tx]) -> DimensionDrift:
    def _rate(txs: List[_Tx]) -> float:
        if not txs:
            return 0.0
        rounded = sum(1 for t in txs if t.amount >= 1_000 and (t.amount % 1_000) == 0)
        return rounded / len(txs)

    rb = _rate(base)
    rc = _rate(cur)
    raw = abs(rc - rb)
    score = _clip01(raw / 0.5)
    return DimensionDrift(
        key="round_rate",
        label=DIM_LABELS["round_rate"],
        score=score,
        weight=WEIGHTS["round_rate"],
        contribution=WEIGHTS["round_rate"] * score,
        baseline_summary={"round_rate": round(rb, 4)},
        current_summary={"round_rate": round(rc, 4)},
        detail=f"{int(round(rb*100))}% → {int(round(rc*100))}% round-amount transfers",
    )


def _median_shift_drift(base: List[_Tx], cur: List[_Tx]) -> DimensionDrift:
    if not base or not cur:
        return DimensionDrift(
            key="median_shift",
            label=DIM_LABELS["median_shift"],
            score=0.0,
            weight=WEIGHTS["median_shift"],
            contribution=0.0,
            baseline_summary={"median": 0.0},
            current_summary={"median": 0.0},
            detail="insufficient data",
        )
    mb = statistics.median(t.amount for t in base)
    mc = statistics.median(t.amount for t in cur)
    if mb <= 0 and mc <= 0:
        score = 0.0
    elif mb <= 0 or mc <= 0:
        score = 1.0
    else:
        score = _clip01(abs(math.log2(mc / mb)) / 3.0)  # 8x change saturates
    return DimensionDrift(
        key="median_shift",
        label=DIM_LABELS["median_shift"],
        score=score,
        weight=WEIGHTS["median_shift"],
        contribution=WEIGHTS["median_shift"] * score,
        baseline_summary={"median": round(mb, 2)},
        current_summary={"median": round(mc, 2)},
        detail=f"median {mb:.0f} → {mc:.0f} ({_safe_div(mc, mb):.2f}×)",
    )


_DRIFT_FUNCS = (
    _amount_drift,
    _hour_drift,
    _dow_drift,
    _direction_drift,
    _velocity_drift,
    _cparty_diversity_drift,
    _cparty_novelty_drift,
    _geo_drift,
    _round_rate_drift,
    _median_shift_drift,
)


# ---------------------------------------------------------------------------
# Counterparty + change-point views
# ---------------------------------------------------------------------------


def _counterparty_view(
    base: List[_Tx],
    cur: List[_Tx],
    *,
    limit: int = 8,
) -> List[CounterpartyContribution]:
    bc: Dict[str, List[float]] = defaultdict(list)
    cc: Dict[str, List[float]] = defaultdict(list)
    for t in base:
        bc[t.counterparty].append(t.amount)
    for t in cur:
        cc[t.counterparty].append(t.amount)

    rows: List[CounterpartyContribution] = []
    for cp in set(bc) | set(cc):
        bcount = len(bc.get(cp, []))
        ccount = len(cc.get(cp, []))
        bvol = sum(bc.get(cp, []))
        cvol = sum(cc.get(cp, []))
        is_new = bcount == 0
        if is_new:
            activity_lift = float("inf") if ccount else 0.0
            volume_lift = float("inf") if cvol else 0.0
        else:
            activity_lift = (ccount / max(bcount, 1)) - 1.0
            volume_lift = (cvol / max(bvol, 1e-9)) - 1.0
        rows.append(
            CounterpartyContribution(
                counterparty=cp,
                baseline_count=bcount,
                current_count=ccount,
                baseline_volume=bvol,
                current_volume=cvol,
                is_new=is_new,
                activity_lift=activity_lift,
                volume_lift=volume_lift,
            )
        )

    def _sort_key(r: CounterpartyContribution) -> Tuple[int, float, float]:
        # New counterparties rank first, then by current activity, then volume.
        return (
            0 if r.is_new else 1,
            -r.current_count,
            -r.current_volume,
        )

    rows.sort(key=_sort_key)
    return rows[:limit]


def _change_point(
    base: List[_Tx],
    cur: List[_Tx],
    *,
    window_size: int = 7,
) -> ChangePoint:
    """Walk the current window day-by-day; for each successive day, take the
    trailing `window_size`-day slice of recent activity and compare it back
    to the full baseline via KS on amounts. The earliest day with KS over
    the floor is reported as the onset of drift.
    """
    if not cur or not base:
        return ChangePoint(detected=False, onset_iso=None, days_ago=None, rolling_ks=[])

    base_amts = [t.amount for t in base]
    # Day buckets of the current window
    by_day: Dict[Tuple[int, int, int], List[_Tx]] = defaultdict(list)
    for t in cur:
        key = (t.timestamp.year, t.timestamp.month, t.timestamp.day)
        by_day[key].append(t)
    days = sorted(by_day.keys())

    rolling: List[Dict[str, Any]] = []
    onset: Optional[datetime] = None
    accumulated: List[_Tx] = []
    for day in days:
        accumulated.extend(by_day[day])
        # Trim to last window_size days of current activity
        cutoff = datetime(*day, tzinfo=timezone.utc) - timedelta(days=window_size)
        accumulated = [t for t in accumulated if t.timestamp >= cutoff]
        amts = [t.amount for t in accumulated]
        ks = _ks_statistic(base_amts, amts) if amts else 0.0
        day_iso = datetime(*day, tzinfo=timezone.utc).date().isoformat()
        rolling.append({"day": day_iso, "ks": round(ks, 4), "n": len(amts)})
        if onset is None and ks >= CHANGE_POINT_KS_FLOOR and len(amts) >= 3:
            onset = datetime(*day, tzinfo=timezone.utc)

    if onset is None:
        return ChangePoint(detected=False, onset_iso=None, days_ago=None, rolling_ks=rolling)

    latest = cur[-1].timestamp
    days_ago = int((latest - onset).total_seconds() // 86400)
    return ChangePoint(
        detected=True,
        onset_iso=onset.isoformat(),
        days_ago=max(0, days_ago),
        rolling_ks=rolling,
    )


# ---------------------------------------------------------------------------
# Verdict + narrative
# ---------------------------------------------------------------------------


def _verdict(score: float) -> str:
    for floor, name in BANDS:
        if score >= floor:
            return name
    return "stable"


def _suggested_action(verdict: str) -> str:
    return {
        "stable":      "no action — behavior matches baseline within tolerance.",
        "mild":        "monitor — schedule a routine review next cycle.",
        "drifting":    "review — flag for an analyst pass within 5 business days.",
        "erratic":     "escalate — promote to a case at medium priority.",
        "transformed": "escalate — promote to a case at high priority and confirm account holder identity.",
    }.get(verdict, "monitor")


def _headline(verdict: str, drivers: List[str]) -> str:
    name = {
        "stable":      "Behavior is stable",
        "mild":        "Mild drift detected",
        "drifting":    "Account is drifting from its baseline",
        "erratic":     "Account is behaving erratically",
        "transformed": "Behavioral identity break",
    }.get(verdict, "Behavior is stable")
    if not drivers:
        return name
    if len(drivers) == 1:
        return f"{name} — driven by {drivers[0].lower()}"
    return f"{name} — driven by {drivers[0].lower()} & {drivers[1].lower()}"


def _narrative(
    dims: List[DimensionDrift],
    cps: List[CounterpartyContribution],
    cp: ChangePoint,
    baseline_summary: Dict[str, Any],
    current_summary: Dict[str, Any],
) -> str:
    bits: List[str] = []
    # Top driver detail string (verbatim — the per-dim detail is already
    # tuned to read well).
    top = max(dims, key=lambda d: d.contribution) if dims else None
    if top and top.contribution > 0:
        bits.append(f"Top driver — {top.label.lower()}: {top.detail}.")

    novelty = next((d for d in dims if d.key == "cparty_novelty"), None)
    if novelty and novelty.score >= 0.4:
        new_cps = [c for c in cps if c.is_new]
        if new_cps:
            sample = ", ".join(c.counterparty for c in new_cps[:3])
            bits.append(
                f"{len(new_cps)} previously-unseen counterparties dominate the recent window ({sample})."
            )

    median = next((d for d in dims if d.key == "median_shift"), None)
    if median and median.score >= 0.5:
        bits.append(f"Median ticket {median.detail.split(';')[-1].strip() if ';' in median.detail else median.detail}.")

    direction = next((d for d in dims if d.key == "direction"), None)
    if direction and direction.score >= 0.4:
        bits.append(f"Inflow/outflow profile flipped ({direction.detail}).")

    if cp.detected and cp.days_ago is not None:
        bits.append(
            f"Rolling KS first crossed the {CHANGE_POINT_KS_FLOOR:.2f} floor ≈{cp.days_ago} days ago "
            f"({cp.onset_iso[:10] if cp.onset_iso else '—'})."
        )

    if not bits:
        bits.append(
            f"Current window ({current_summary.get('tx_count', 0)} txs over "
            f"{current_summary.get('span_days', 0)}d) is statistically indistinguishable "
            f"from the {baseline_summary.get('tx_count', 0)}-tx baseline."
        )
    return " ".join(bits)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_rules() -> Dict[str, Any]:
    """Auditor view of every tunable the engine exposes."""
    return {
        "engine": ENGINE_VERSION,
        "weights": WEIGHTS,
        "bands": [{"floor": f, "verdict": name} for f, name in BANDS],
        "dim_labels": DIM_LABELS,
        "min_baseline_txs": MIN_BASELINE_TXS,
        "min_current_txs": MIN_CURRENT_TXS,
        "default_baseline_fraction": DEFAULT_BASELINE_FRACTION,
        "driver_floor": DRIVER_FLOOR,
        "change_point_ks_floor": CHANGE_POINT_KS_FLOOR,
    }


def analyze_account(
    account_id: str,
    rows: Iterable[Dict[str, Any]],
    *,
    baseline_fraction: float = DEFAULT_BASELINE_FRACTION,
    split_at: Optional[str] = None,
    display_name: Optional[str] = None,
) -> Optional[AccountDrift]:
    """Compute a behavioral-drift report for one account.

    Returns None when there aren't enough transactions on either side of
    the split to make a meaningful comparison.
    """
    txs = _normalise_account_txs(account_id, rows)
    if len(txs) < MIN_BASELINE_TXS + MIN_CURRENT_TXS:
        return None

    sa = _parse_ts(split_at) if split_at else None
    base, cur = _split_window(txs, baseline_fraction=baseline_fraction, split_at=sa)
    if len(base) < MIN_BASELINE_TXS or len(cur) < MIN_CURRENT_TXS:
        return None

    dims = [fn(base, cur) for fn in _DRIFT_FUNCS]
    overall = _clip01(sum(d.contribution for d in dims))
    verdict = _verdict(overall)

    # Drivers: dimensions whose contribution clears the floor, sorted desc.
    sorted_dims = sorted(dims, key=lambda d: d.contribution, reverse=True)
    drivers = [d.label for d in sorted_dims if d.contribution >= DRIVER_FLOOR * overall and d.contribution > 0]
    drivers = drivers[:3]

    cps = _counterparty_view(base, cur)
    cp = _change_point(base, cur)

    bsum = _window_summary(base)
    csum = _window_summary(cur)

    return AccountDrift(
        account_id=account_id,
        display_name=display_name or risk_engine._name_for_party(account_id, [
            risk_engine.Tx(
                account_id=t.account_id,
                counterparty=t.counterparty,
                amount=t.amount,
                timestamp=t.timestamp,
                geo=t.geo,
            )
            for t in (base + cur)
        ]) or account_id,
        overall=overall,
        verdict=verdict,
        headline=_headline(verdict, drivers),
        drivers=drivers,
        narrative=_narrative(dims, cps, cp, bsum, csum),
        baseline_window=bsum,
        current_window=csum,
        dimensions=dims,
        counterparties=cps,
        change_point=cp,
        suggested_action=_suggested_action(verdict),
    )


def analyze(
    rows: Iterable[Dict[str, Any]],
    *,
    account_id: Optional[str] = None,
    baseline_fraction: float = DEFAULT_BASELINE_FRACTION,
    split_at: Optional[str] = None,
    min_total_txs: int = MIN_BASELINE_TXS + MIN_CURRENT_TXS,
) -> Dict[str, Any]:
    """Run drift over one account (when `account_id` is given) or over every
    account that meets the minimum-tx bar. Cross-account responses are
    sorted by overall drift desc so the worst-drifters land at the top.
    """
    rows = list(rows)
    if account_id:
        rep = analyze_account(
            account_id,
            rows,
            baseline_fraction=baseline_fraction,
            split_at=split_at,
        )
        return {
            "ok": True,
            "engine": ENGINE_VERSION,
            "scope": "single",
            "account_id": account_id,
            "split_mode": "explicit" if split_at else "fraction",
            "baseline_fraction": baseline_fraction,
            "split_at": split_at,
            "report": rep.to_dict() if rep else None,
            "reason": None if rep else "insufficient transactions for both windows",
        }

    # All-accounts pass
    parties: set[str] = set()
    for r in rows:
        if r.get("account_id"):
            parties.add(str(r["account_id"]).strip())
        if r.get("counterparty"):
            parties.add(str(r["counterparty"]).strip())

    reports: List[AccountDrift] = []
    skipped: List[Dict[str, Any]] = []
    for p in sorted(parties):
        rep = analyze_account(
            p,
            rows,
            baseline_fraction=baseline_fraction,
            split_at=split_at,
        )
        if rep is None:
            skipped.append({"account_id": p, "reason": "insufficient transactions"})
        else:
            reports.append(rep)

    reports.sort(key=lambda r: (-r.overall, r.account_id))
    summary = _portfolio_summary(reports)
    return {
        "ok": True,
        "engine": ENGINE_VERSION,
        "scope": "portfolio",
        "split_mode": "explicit" if split_at else "fraction",
        "baseline_fraction": baseline_fraction,
        "split_at": split_at,
        "summary": summary,
        "reports": [r.to_dict() for r in reports],
        "skipped": skipped,
    }


def _portfolio_summary(reports: List[AccountDrift]) -> Dict[str, Any]:
    counts = {"stable": 0, "mild": 0, "drifting": 0, "erratic": 0, "transformed": 0}
    for r in reports:
        counts[r.verdict] = counts.get(r.verdict, 0) + 1
    drifters = [r for r in reports if r.verdict in ("drifting", "erratic", "transformed")]
    avg_overall = (sum(r.overall for r in reports) / len(reports)) if reports else 0.0
    top = reports[0] if reports else None
    return {
        "total_accounts": len(reports),
        "by_verdict": counts,
        "drifters": len(drifters),
        "avg_overall": round(avg_overall, 4),
        "top_account_id": top.account_id if top else None,
        "top_overall": round(top.overall, 4) if top else 0.0,
    }


# ---------------------------------------------------------------------------
# Bundled demo dataset
# ---------------------------------------------------------------------------


def sample_dataset() -> Dict[str, Any]:
    """A deterministic three-account demo that exercises every verdict band.

    * `ACC-STABLE`    — small business; consistent counterparties, 9-5
                        hours, ₹10k–₹30k tickets. Should land `stable`.
    * `ACC-DRIFT`     — sleeper account; six months of light activity
                        followed by a sudden burst of new counterparties,
                        new hours, and round-amount transfers. Should
                        land `erratic`/`transformed`.
    * `ACC-MILD`      — same account holder, slightly larger tickets
                        recently as the business grew. Should land
                        `mild` or `stable`.
    """
    txs: List[Dict[str, Any]] = []

    def _at(ts_iso: str, account: str, cp: str, amt: float, *, role: str = "out", geo: str = "IN") -> None:
        a, b = (account, cp) if role == "out" else (cp, account)
        txs.append({
            "account_id": a,
            "counterparty": b,
            "subject_name": "Stable Traders Pvt Ltd" if account == "ACC-STABLE" else
                           "Anant Joshi" if account == "ACC-DRIFT" else
                           "Mehul & Co",
            "counterparty_name": cp,
            "amount": amt,
            "timestamp": ts_iso,
            "channel": "wire",
            "geo": geo,
        })

    # --- ACC-STABLE: six months of routine transfers, mid-morning hours
    base = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
    routine_cps = ["VENDOR-A", "VENDOR-B", "VENDOR-C", "VENDOR-D", "PAYROLL-1"]
    for w in range(24):
        day = base + timedelta(days=w * 7)
        for i, cp in enumerate(routine_cps):
            ts = (day + timedelta(hours=i, days=i % 5)).isoformat()
            amt = [12_500, 18_750, 9_400, 22_100, 15_000][i % 5] + (w % 4) * 350
            _at(ts, "ACC-STABLE", cp, amt, role="out" if i % 2 else "in")

    # --- ACC-MILD: same vibe, gentle growth in recent weeks
    base2 = datetime(2026, 1, 1, 11, 30, tzinfo=timezone.utc)
    for w in range(20):
        day = base2 + timedelta(days=w * 8)
        grow = 1.0 + (w / 30.0)
        for i, cp in enumerate(["CLIENT-X", "CLIENT-Y", "OFFICE-RENT"]):
            ts = (day + timedelta(hours=i)).isoformat()
            amt = [9_300, 11_400, 25_000][i] * grow
            _at(ts, "ACC-MILD", cp, amt, role="in" if i < 2 else "out")

    # --- ACC-DRIFT: 18 weeks of sleepy IN-flows, then a 9-day OUT-flow burst
    #     to brand-new counterparties at off-hours with round amounts. The
    #     baseline window dominates the timeline so the burst surfaces as
    #     drift no matter what split fraction the analyst picks.
    sleeper = datetime(2026, 1, 5, 14, 0, tzinfo=timezone.utc)
    for w in range(18):
        # Two routine inflows a week from a single friend, mid-afternoon.
        for i in range(2):
            ts = (sleeper + timedelta(days=w * 7 + i * 3)).isoformat()
            _at(ts, "ACC-DRIFT", "FRIEND-1", 4_500 + (w * 7 + i) * 18, role="in")
    burst_start = datetime(2026, 5, 18, 2, 30, tzinfo=timezone.utc)
    burst_cps = ["UNKNOWN-01", "UNKNOWN-02", "UNKNOWN-03"]
    for day_offset in range(9):
        for hour_offset, cp in enumerate(burst_cps):
            ts = (burst_start + timedelta(days=day_offset, hours=hour_offset)).isoformat()
            amt = 50_000 + (hour_offset * 25_000)  # 50k / 75k / 100k — all round
            _at(ts, "ACC-DRIFT", cp, amt, role="out", geo="AE" if hour_offset % 2 else "IN")

    return {
        "ok": True,
        "engine": ENGINE_VERSION,
        "transactions": txs,
        "highlight_account": "ACC-DRIFT",
        "recommended_split_at": "2026-05-17T00:00:00+00:00",
        "note": (
            "Three demo accounts: ACC-STABLE (routine), ACC-MILD (gentle growth), "
            "ACC-DRIFT (a sleeper that wakes up — sudden new counterparties, "
            "round amounts, off-hours transfers). Loaded with sensible defaults."
        ),
    }
