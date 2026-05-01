"""TITAN AML risk engine.

Deterministic, explainable, no ML dependencies. Composes per-account
risk scores from eight pattern detectors, each contributing a weighted
sub-score plus a human-readable reason. Total score is clipped to 0-100.

Detectors
---------
- structuring       Multiple sub-threshold deposits within a short window.
- velocity_spike    Recent volume vs trailing baseline.
- round_trip        Closed cycles in the transfer graph (length 2..4).
- fan_in            One account with abnormally many distinct senders.
- fan_out           One account with abnormally many distinct recipients.
- high_risk_geo     Counterparty geographies on the FATF grey/black list.
- round_amount      Unusual concentration of "rounded" large transfers.
- sanctions_hit     Subject or counterparty name matches the watchlist.

The scorer is purely a function: same input + same weight overrides →
same output. That makes it auditable for compliance review and lets the
frontend run a what-if simulator client-side without breaking determinism.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

import sanctions as sanctions_engine


# ---------------------------------------------------------------------------
# Tunables. Production deployments override these via /aml/rules.
# ---------------------------------------------------------------------------

WEIGHTS: Dict[str, float] = {
    "structuring": 26.0,
    "velocity_spike": 16.0,
    "round_trip": 20.0,
    "sanctions_hit": 22.0,
    "fan_in": 8.0,
    "fan_out": 8.0,
    "high_risk_geo": 6.0,
    "round_amount": 4.0,
}

DETECTOR_ORDER: Tuple[str, ...] = (
    "structuring",
    "velocity_spike",
    "round_trip",
    "sanctions_hit",
    "fan_in",
    "fan_out",
    "high_risk_geo",
    "round_amount",
)

# Cap a single detector at 0..MAX_WEIGHT so the what-if simulator can't
# pin one factor to 100% and reduce the rest to noise.
MAX_WEIGHT = 60.0
SANCTIONS_HIT_THRESHOLD = 0.65  # similarity gate for hits_for_account

# Indian FIU-IND CTR threshold proxy: treat structuring as multiple
# deposits in [STRUCT_BAND_LOW, STRUCT_BAND_HIGH) within a 24h window.
STRUCT_BAND_LOW = 40_000.0
STRUCT_BAND_HIGH = 50_000.0
STRUCT_WINDOW_HOURS = 24
STRUCT_MIN_COUNT = 3

VELOCITY_RECENT_HOURS = 1
VELOCITY_BASELINE_HOURS = 24 * 30  # 30 day trailing window
VELOCITY_SPIKE_RATIO = 5.0  # recent rate >= 5x baseline rate

CYCLE_MAX_DEPTH = 4
CYCLE_MIN_VALUE = 50_000.0  # only cycles where every leg >= this matter

FAN_DEGREE_HIGH = 8

# ISO-3166 alpha-2 codes treated as elevated risk for demo. Real systems
# pull from the FATF grey-/black-list feed.
HIGH_RISK_GEOS: Set[str] = {"KP", "IR", "MM", "SY", "AF", "RU", "BY"}

ROUND_AMOUNT_MIN = 100_000.0
ROUND_AMOUNT_MOD = 10_000.0  # value % MOD == 0 → "rounded"
ROUND_AMOUNT_MIN_COUNT = 3


# ---------------------------------------------------------------------------
# Domain types
# ---------------------------------------------------------------------------


@dataclass
class Tx:
    """Normalized transaction.

    timestamp is parsed once into an aware UTC datetime so all downstream
    arithmetic is timezone-safe.
    """

    account_id: str
    counterparty: str
    amount: float
    timestamp: datetime
    channel: str = ""
    geo: str = ""
    subject: str = ""
    subject_name: str = ""
    counterparty_name: str = ""
    meta: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Factor:
    name: str
    points: float
    weight: float
    detail: str
    evidence: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "points": round(self.points, 2),
            "weight": self.weight,
            "detail": self.detail,
            "evidence": self.evidence,
        }


@dataclass
class AccountReport:
    account_id: str
    risk_score: float
    band: str  # low | medium | high | critical
    factors: List[Factor]
    edges: List[Dict[str, Any]]
    counterparty_count: int
    inbound_total: float
    outbound_total: float
    sanctions_hits: List[Dict[str, Any]] = field(default_factory=list)
    display_name: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "account_id": self.account_id,
            "display_name": self.display_name,
            "risk_score": round(self.risk_score, 1),
            "band": self.band,
            "factors": [f.to_dict() for f in self.factors],
            "edges": self.edges,
            "counterparty_count": self.counterparty_count,
            "inbound_total": round(self.inbound_total, 2),
            "outbound_total": round(self.outbound_total, 2),
            "sanctions_hits": self.sanctions_hits,
        }


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def _parse_ts(raw: str) -> datetime:
    """Lenient ISO-8601 parse that accepts trailing Z."""
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
    s = (raw or "").strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        dt = datetime.now(timezone.utc)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def normalize(rows: Iterable[Dict[str, Any]]) -> List[Tx]:
    out: List[Tx] = []
    for r in rows:
        try:
            tx = Tx(
                account_id=str(r.get("account_id", "")).strip(),
                counterparty=str(r.get("counterparty", "")).strip(),
                amount=float(r.get("amount", 0) or 0),
                timestamp=_parse_ts(r.get("timestamp", "")),
                channel=str(r.get("channel", "") or ""),
                geo=str(r.get("geo", "") or "").upper(),
                subject=str(r.get("subject", "") or ""),
                subject_name=str(r.get("subject_name", "") or "").strip(),
                counterparty_name=str(r.get("counterparty_name", "") or "").strip(),
                meta=r.get("meta") or {},
            )
            if tx.account_id and tx.counterparty and tx.amount > 0:
                out.append(tx)
        except (TypeError, ValueError):
            continue
    return out


# ---------------------------------------------------------------------------
# Detectors. Each returns a Factor with `points` already weighted.
# ---------------------------------------------------------------------------


def _detect_structuring(account: str, txs: List[Tx], *, weight: float) -> Factor:
    band_hits = [
        t for t in txs
        if t.account_id == account
        and STRUCT_BAND_LOW <= t.amount < STRUCT_BAND_HIGH
    ]
    band_hits.sort(key=lambda t: t.timestamp)
    # Sliding window: count max sub-threshold transfers within
    # STRUCT_WINDOW_HOURS. O(n) two-pointer.
    j = 0
    best = 0
    best_window: List[Tx] = []
    for i in range(len(band_hits)):
        while (band_hits[i].timestamp - band_hits[j].timestamp).total_seconds() > STRUCT_WINDOW_HOURS * 3600:
            j += 1
        win = i - j + 1
        if win > best:
            best = win
            best_window = band_hits[j : i + 1]

    if best < STRUCT_MIN_COUNT:
        return Factor(
            name="structuring",
            points=0.0,
            weight=weight,
            detail=f"No sub-threshold clustering ({best}/{STRUCT_MIN_COUNT} hits).",
        )
    # Saturating curve: 3 hits ≈ 0.7, 6 hits ≈ 1.0.
    intensity = min(1.0, (best - STRUCT_MIN_COUNT + 1) / 4.0 + 0.5)
    return Factor(
        name="structuring",
        points=intensity * weight,
        weight=weight,
        detail=(
            f"{best} transfers in [{int(STRUCT_BAND_LOW):,}, "
            f"{int(STRUCT_BAND_HIGH):,}) within {STRUCT_WINDOW_HOURS}h "
            "— classic CTR-evasion signal."
        ),
        evidence=[
            {
                "amount": t.amount,
                "timestamp": t.timestamp.isoformat(),
                "counterparty": t.counterparty,
                "channel": t.channel,
            }
            for t in best_window
        ],
    )


def _detect_velocity(account: str, txs: List[Tx], *, weight: float) -> Factor:
    if not txs:
        return Factor("velocity_spike", 0.0, weight, "No activity.")
    latest = max(t.timestamp for t in txs)
    recent_cut = latest.timestamp() - VELOCITY_RECENT_HOURS * 3600
    base_cut = latest.timestamp() - VELOCITY_BASELINE_HOURS * 3600

    recent = [t for t in txs if t.account_id == account and t.timestamp.timestamp() >= recent_cut]
    baseline = [
        t for t in txs
        if t.account_id == account
        and base_cut <= t.timestamp.timestamp() < recent_cut
    ]
    recent_rate = sum(t.amount for t in recent) / max(VELOCITY_RECENT_HOURS, 1)
    baseline_rate = sum(t.amount for t in baseline) / max(VELOCITY_BASELINE_HOURS, 1)

    if baseline_rate <= 0 and recent_rate <= 0:
        return Factor("velocity_spike", 0.0, weight, "No activity.")
    if baseline_rate <= 0:
        # New account or first activity → mild flag, not full weight.
        return Factor(
            name="velocity_spike",
            points=0.4 * weight,
            weight=weight,
            detail=f"First-seen burst: ₹{recent_rate:,.0f}/h with no prior baseline.",
            evidence=[{"recent_rate_per_hour": recent_rate}],
        )

    ratio = recent_rate / baseline_rate
    if ratio < VELOCITY_SPIKE_RATIO:
        return Factor(
            name="velocity_spike",
            points=0.0,
            weight=weight,
            detail=f"Within baseline ({ratio:.1f}× recent vs trailing).",
        )
    intensity = min(1.0, (ratio / VELOCITY_SPIKE_RATIO) / 4.0 + 0.6)
    return Factor(
        name="velocity_spike",
        points=intensity * weight,
        weight=weight,
        detail=f"Recent volume {ratio:.1f}× the 30d baseline rate.",
        evidence=[
            {"recent_rate_per_hour": recent_rate, "baseline_rate_per_hour": baseline_rate}
        ],
    )


def _detect_round_trip(
    account: str,
    edges: List[Tuple[str, str, float, datetime]],
    *,
    weight: float,
) -> Factor:
    """DFS up to depth CYCLE_MAX_DEPTH from `account` looking for cycles
    where every leg >= CYCLE_MIN_VALUE. Treats the graph as directed.
    """
    adj: Dict[str, List[Tuple[str, float, datetime]]] = defaultdict(list)
    for src, dst, amt, ts in edges:
        if amt >= CYCLE_MIN_VALUE:
            adj[src].append((dst, amt, ts))

    cycles: List[List[Dict[str, Any]]] = []
    path: List[Tuple[str, float, datetime]] = []

    def dfs(node: str, depth: int) -> None:
        if depth > CYCLE_MAX_DEPTH:
            return
        for nxt, amt, ts in adj.get(node, ()):
            leg = (nxt, amt, ts)
            if nxt == account and depth >= 1:
                cycles.append(
                    [
                        {"from": account, "to": path[0][0] if path else nxt,
                         "amount": (path[0][1] if path else amt),
                         "timestamp": (path[0][2].isoformat() if path else ts.isoformat())},
                        *[
                            {"from": p_src, "to": p_dst, "amount": p_amt, "timestamp": p_ts.isoformat()}
                            for (p_src, (p_dst, p_amt, p_ts)) in zip([account] + [s[0] for s in path[:-1]], path)
                        ],
                        {"from": node, "to": nxt, "amount": amt, "timestamp": ts.isoformat()},
                    ]
                )
                continue
            if any(s[0] == nxt for s in path):
                continue  # avoid revisiting non-origin nodes
            path.append(leg)
            dfs(nxt, depth + 1)
            path.pop()

    dfs(account, 0)
    if not cycles:
        return Factor("round_trip", 0.0, weight, "No closed-loop transfers found.")
    intensity = min(1.0, len(cycles) / 3.0 + 0.4)
    return Factor(
        name="round_trip",
        points=intensity * weight,
        weight=weight,
        detail=(
            f"{len(cycles)} closed cycle(s) of length ≤{CYCLE_MAX_DEPTH} "
            f"with every leg ≥ ₹{int(CYCLE_MIN_VALUE):,}."
        ),
        evidence=[{"cycle": c} for c in cycles[:3]],
    )


def _detect_fan(
    account: str, txs: List[Tx], *, w_in: float, w_out: float
) -> Tuple[Factor, Factor]:
    in_set = {t.account_id for t in txs if t.counterparty == account}
    out_set = {t.counterparty for t in txs if t.account_id == account}

    def make(name: str, degree: int, weight: float) -> Factor:
        if degree < FAN_DEGREE_HIGH:
            return Factor(name, 0.0, weight, f"Degree {degree} within normal range.")
        intensity = min(1.0, (degree - FAN_DEGREE_HIGH) / 8.0 + 0.5)
        return Factor(
            name=name,
            points=intensity * weight,
            weight=weight,
            detail=f"{name.replace('_',' ').title()} degree {degree} ≥ {FAN_DEGREE_HIGH}.",
            evidence=[{"degree": degree}],
        )

    return make("fan_in", len(in_set), w_in), make("fan_out", len(out_set), w_out)


def _detect_geo(account: str, txs: List[Tx], *, weight: float) -> Factor:
    flagged = [
        t for t in txs
        if (t.account_id == account or t.counterparty == account)
        and t.geo in HIGH_RISK_GEOS
    ]
    if not flagged:
        return Factor("high_risk_geo", 0.0, weight, "No counterparties in elevated-risk jurisdictions.")
    intensity = min(1.0, len(flagged) / 5.0 + 0.5)
    return Factor(
        name="high_risk_geo",
        points=intensity * weight,
        weight=weight,
        detail=f"{len(flagged)} transfer(s) touching elevated-risk geos: "
        + ",".join(sorted({t.geo for t in flagged})),
        evidence=[{"timestamp": t.timestamp.isoformat(), "amount": t.amount, "geo": t.geo} for t in flagged[:5]],
    )


def _name_for_party(party_id: str, txs: List[Tx]) -> str:
    """Pick the most-frequent display name observed for `party_id`. We
    look at both subject_name (when party is the account) and
    counterparty_name (when party is the counterparty) and pick the
    longest variant on the most common normalized form. Falls back to
    the id itself if no name was provided.
    """
    counts: Dict[str, int] = {}
    longest: Dict[str, str] = {}
    for t in txs:
        if t.account_id == party_id and t.subject_name:
            key = t.subject_name.lower().strip()
            counts[key] = counts.get(key, 0) + 1
            if len(t.subject_name) > len(longest.get(key, "")):
                longest[key] = t.subject_name
        if t.counterparty == party_id and t.counterparty_name:
            key = t.counterparty_name.lower().strip()
            counts[key] = counts.get(key, 0) + 1
            if len(t.counterparty_name) > len(longest.get(key, "")):
                longest[key] = t.counterparty_name
    if not counts:
        return ""
    best_key = max(counts.items(), key=lambda kv: kv[1])[0]
    return longest.get(best_key, "")


def _detect_sanctions(
    account: str,
    txs: List[Tx],
    *,
    weight: float,
    threshold: float = SANCTIONS_HIT_THRESHOLD,
) -> Tuple[Factor, List[Dict[str, Any]]]:
    """Screen the account's name plus every counterparty's name against
    the bundled watchlist. Intensity scales with the *strongest* match —
    one solid hit is enough to drive the factor toward full weight.
    """
    name_for: Dict[str, str] = {}
    geo_for: Dict[str, str] = {}
    for t in txs:
        if t.account_id == account:
            if t.subject_name and account not in name_for:
                name_for[account] = t.subject_name
            if t.counterparty_name and t.counterparty not in name_for:
                name_for[t.counterparty] = t.counterparty_name
            if t.geo and t.counterparty not in geo_for:
                geo_for[t.counterparty] = t.geo
        elif t.counterparty == account:
            if t.subject_name and t.account_id not in name_for:
                name_for[t.account_id] = t.subject_name
            if t.counterparty_name and account not in name_for:
                name_for[account] = t.counterparty_name
            if t.geo and t.account_id not in geo_for:
                geo_for[t.account_id] = t.geo

    if not name_for:
        return (
            Factor(
                name="sanctions_hit",
                points=0.0,
                weight=weight,
                detail="No party names supplied — screen by adding subject_name / counterparty_name columns.",
            ),
            [],
        )

    hits: List[Dict[str, Any]] = []
    seen_ids: Set[str] = set()
    for party_id, raw_name in name_for.items():
        result = sanctions_engine.screen(
            raw_name,
            jurisdiction=geo_for.get(party_id),
            threshold=threshold,
            top_k=1,
        )
        best = result.get("best")
        if not best:
            continue
        # Dedupe per watchlist entity — only keep the strongest hit.
        eid = best["entity_id"]
        existing = next((h for h in hits if h["entity_id"] == eid), None)
        if existing and existing["similarity"] >= best["similarity"]:
            continue
        if existing:
            hits.remove(existing)
        seen_ids.add(eid)
        hits.append(
            {
                "queried_name": raw_name,
                "queried_party": party_id,
                "queried_role": "subject" if party_id == account else "counterparty",
                **best,
            }
        )

    if not hits:
        return (
            Factor(
                name="sanctions_hit",
                points=0.0,
                weight=weight,
                detail=f"No watchlist match ≥ {threshold:.0%} similarity across {len(name_for)} parties.",
            ),
            [],
        )

    hits.sort(key=lambda h: h["similarity"], reverse=True)
    strongest = hits[0]["similarity"]
    # Intensity floor at 0.55 for a passing hit so a weak match still
    # registers visibly; ceil at 1.0. Each *additional* hit adds 0.10.
    intensity = min(1.0, max(0.55, strongest) + 0.10 * (len(hits) - 1))
    detail = (
        f"{len(hits)} watchlist match(es); strongest "
        f"{strongest:.0%} on '{hits[0]['matched_alias']}' ({hits[0]['list']})."
    )
    return (
        Factor(
            name="sanctions_hit",
            points=intensity * weight,
            weight=weight,
            detail=detail,
            evidence=[
                {
                    "entity_id": h["entity_id"],
                    "name": h["name"],
                    "matched_alias": h["matched_alias"],
                    "queried_name": h["queried_name"],
                    "similarity": h["similarity"],
                    "list": h["list"],
                    "jurisdiction": h["jurisdiction"],
                    "grade": h["grade"],
                }
                for h in hits[:5]
            ],
        ),
        hits,
    )


def _detect_round_amount(account: str, txs: List[Tx], *, weight: float) -> Factor:
    big_round = [
        t for t in txs
        if t.account_id == account
        and t.amount >= ROUND_AMOUNT_MIN
        and (t.amount % ROUND_AMOUNT_MOD == 0)
    ]
    if len(big_round) < ROUND_AMOUNT_MIN_COUNT:
        return Factor("round_amount", 0.0, weight, f"{len(big_round)} large rounded transfers.")
    intensity = min(1.0, len(big_round) / 6.0 + 0.5)
    return Factor(
        name="round_amount",
        points=intensity * weight,
        weight=weight,
        detail=f"{len(big_round)} large transfers that are perfect multiples of ₹{int(ROUND_AMOUNT_MOD):,}.",
        evidence=[{"amount": t.amount, "timestamp": t.timestamp.isoformat()} for t in big_round[:5]],
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _band(score: float) -> str:
    if score >= 80:
        return "critical"
    if score >= 60:
        return "high"
    if score >= 30:
        return "medium"
    return "low"


def _resolve_weights(override: Optional[Dict[str, Any]]) -> Dict[str, float]:
    """Merge a partial override over the defaults; clamp each entry into
    ``[0, MAX_WEIGHT]`` so the simulator can't push one factor far enough
    to dominate the rest. Unknown detector names are silently dropped.
    """
    out = dict(WEIGHTS)
    if not override:
        return out
    for name, raw in override.items():
        if name not in WEIGHTS:
            continue
        try:
            v = float(raw)
        except (TypeError, ValueError):
            continue
        out[name] = max(0.0, min(MAX_WEIGHT, v))
    return out


def score_accounts(
    rows: Iterable[Dict[str, Any]],
    weights_override: Optional[Dict[str, Any]] = None,
    sanctions_threshold: float = SANCTIONS_HIT_THRESHOLD,
) -> Dict[str, Any]:
    txs = normalize(rows)
    if not txs:
        return {
            "accounts": [],
            "summary": {"total_transactions": 0, "alerted": 0},
            "effective_weights": _resolve_weights(weights_override),
            "rules_version": "1.1.0",
        }

    weights = _resolve_weights(weights_override)

    accounts: Set[str] = set()
    for t in txs:
        accounts.add(t.account_id)
        accounts.add(t.counterparty)

    edges_full: List[Tuple[str, str, float, datetime]] = [
        (t.account_id, t.counterparty, t.amount, t.timestamp) for t in txs
    ]

    reports: List[AccountReport] = []
    for acct in sorted(accounts):
        related = [t for t in txs if t.account_id == acct or t.counterparty == acct]
        if not related:
            continue
        f_struct = _detect_structuring(acct, related, weight=weights["structuring"])
        f_vel = _detect_velocity(acct, related, weight=weights["velocity_spike"])
        f_cycle = _detect_round_trip(acct, edges_full, weight=weights["round_trip"])
        f_sanction, sanction_hits = _detect_sanctions(
            acct,
            related,
            weight=weights["sanctions_hit"],
            threshold=sanctions_threshold,
        )
        f_fan_in, f_fan_out = _detect_fan(
            acct, related, w_in=weights["fan_in"], w_out=weights["fan_out"]
        )
        f_geo = _detect_geo(acct, related, weight=weights["high_risk_geo"])
        f_round = _detect_round_amount(acct, related, weight=weights["round_amount"])

        factor_map = {
            "structuring": f_struct,
            "velocity_spike": f_vel,
            "round_trip": f_cycle,
            "sanctions_hit": f_sanction,
            "fan_in": f_fan_in,
            "fan_out": f_fan_out,
            "high_risk_geo": f_geo,
            "round_amount": f_round,
        }
        factors = [factor_map[name] for name in DETECTOR_ORDER]
        score = min(100.0, sum(f.points for f in factors))

        edges_for_acct = [
            {
                "from": t.account_id,
                "to": t.counterparty,
                "amount": t.amount,
                "timestamp": t.timestamp.isoformat(),
                "channel": t.channel,
            }
            for t in related
        ]
        reports.append(
            AccountReport(
                account_id=acct,
                display_name=_name_for_party(acct, related),
                risk_score=score,
                band=_band(score),
                factors=factors,
                edges=edges_for_acct,
                counterparty_count=len(
                    {t.counterparty for t in related if t.account_id == acct}
                    | {t.account_id for t in related if t.counterparty == acct}
                ),
                inbound_total=sum(t.amount for t in related if t.counterparty == acct),
                outbound_total=sum(t.amount for t in related if t.account_id == acct),
                sanctions_hits=sanction_hits,
            )
        )

    reports.sort(key=lambda r: r.risk_score, reverse=True)
    alerted = [r for r in reports if r.risk_score >= 60]
    sanction_alerts = [r for r in reports if r.sanctions_hits]

    return {
        "accounts": [r.to_dict() for r in reports],
        "summary": {
            "total_transactions": len(txs),
            "total_accounts": len(reports),
            "alerted": len(alerted),
            "sanctions_alerted": len(sanction_alerts),
            "highest_score": round(reports[0].risk_score, 1) if reports else 0,
            "average_score": round(sum(r.risk_score for r in reports) / len(reports), 1) if reports else 0,
        },
        "effective_weights": weights,
        "sanctions_threshold": sanctions_threshold,
        "rules_version": "1.1.0",
    }


def get_rules() -> Dict[str, Any]:
    """Expose the rule set so the frontend can render a Rules page and so
    auditors can verify what the engine is actually doing.
    """
    return {
        "version": "1.1.0",
        "weights": WEIGHTS,
        "max_weight": MAX_WEIGHT,
        "detectors": list(DETECTOR_ORDER),
        "thresholds": {
            "structuring": {
                "band": [STRUCT_BAND_LOW, STRUCT_BAND_HIGH],
                "window_hours": STRUCT_WINDOW_HOURS,
                "min_count": STRUCT_MIN_COUNT,
            },
            "velocity_spike": {
                "recent_hours": VELOCITY_RECENT_HOURS,
                "baseline_hours": VELOCITY_BASELINE_HOURS,
                "spike_ratio": VELOCITY_SPIKE_RATIO,
            },
            "round_trip": {
                "max_depth": CYCLE_MAX_DEPTH,
                "min_value": CYCLE_MIN_VALUE,
            },
            "sanctions_hit": {
                "similarity_threshold": SANCTIONS_HIT_THRESHOLD,
                "watchlist": sanctions_engine.get_metadata(),
            },
            "fan": {"degree_high": FAN_DEGREE_HIGH},
            "high_risk_geo": sorted(HIGH_RISK_GEOS),
            "round_amount": {
                "min": ROUND_AMOUNT_MIN,
                "modulus": ROUND_AMOUNT_MOD,
                "min_count": ROUND_AMOUNT_MIN_COUNT,
            },
        },
        "bands": [
            {"label": "low", "min": 0, "max": 29},
            {"label": "medium", "min": 30, "max": 59},
            {"label": "high", "min": 60, "max": 79},
            {"label": "critical", "min": 80, "max": 100},
        ],
    }
