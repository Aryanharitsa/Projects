"""TITAN AML — Precedent.

Day-70 (round-15). The *retrieval* lens every prior TITAN surface had
left to the analyst.  ``risk`` fires threshold rules, ``typology`` names
the playbook, ``network`` finds cross-account links, ``lineage`` follows
value through time, ``pulse`` compares this week to last, ``profile``
composes the FATF-10 customer risk view, ``drift`` catches account-vs-
self change, ``peer`` catches customer-vs-cohort outlier.  None of them
answer the *very first* question an analyst asks when a new case lands
on their queue:

    "Have we seen a case like this before, and how did it end?"

Precedent is that answer.  Given an open case, it retrieves the ``k``
most similar historical cases from the SQLite case store, aggregates
their dispositions into a **Bayesian disposition prior** (Laplace
smoothing so a single precedent doesn't produce a 100% posterior),
computes the **median time-to-resolution** across those precedents, and
emits an actionable **recommendation verdict** — one of
``file_sar_probable`` / ``expedite_clearance`` / ``novel_investigate``
/ ``insufficient_precedent`` — grounded in cited case IDs.

Design principles
-----------------
* **Pure stdlib.** No numpy, no sklearn.  All feature vectors and
  cosine sums are hand-rolled so the module drops into the same
  ai-aml image with zero new dependencies.
* **Case-store-first.** Reads directly from the ``cases`` SQLite table
  (via ``cases.get_case`` / ``cases.list_cases`` / a private helper for
  bulk snapshot loading) — no separate index or embedding store.  The
  case snapshot *is* the source of truth for a case's features.
* **Deterministic.** Given the same case store and the same query
  case, the retrieval and the disposition prior are byte-identical.
  Regulators do not tolerate "the model was retrained overnight".
* **Explainable at every step.**  Each returned precedent ships a
  ``drivers`` breakdown listing which feature axes contributed the
  most to its similarity score, plus a ``deltas`` list of the axes
  that most distinguish it from the query.  The recommendation carries
  a `rationale` string that names the precedent IDs it leans on.

Feature vector
--------------
The 19-dimensional vector is composed of four blocks with per-block
weights that sum to 1:

    factor_block  (9 dims, weight 0.55)  — normalized firing intensity
                                            of each of the nine risk
                                            detectors (structuring …
                                            adverse_media).
    typology_block(6 dims, weight 0.20)  — one-hot of primary typology
                                            code with confidence used
                                            as the "on" value.
    amount_block  (2 dims, weight 0.10)  — log10-scaled inbound and
                                            outbound totals, clipped
                                            to [0, 1] against a fleet
                                            reference (10^8 = 1.0).
    posture_block (2 dims, weight 0.15)  — band ordinal ∈ [0.25, 1.0]
                                            and a sanctions-presence
                                            gate ∈ {0, 1}.

Similarity is a per-block weighted cosine between the query vector
and each candidate vector.  Cosine on a block-weighted vector keeps
the intuition ("orientation, not magnitude") while letting us tune
which axes matter most without touching the metric.

Disposition prior
-----------------
Precedents are partitioned by their terminal status: ``sar_filed`` vs
``cleared`` (open / review / escalated are treated as "in flight" and
excluded from the prior).  With Laplace smoothing (α = 0.5 per class)
the posterior probability of SAR is

    P(sar | precedents) = (n_sar + 0.5) / (n_sar + n_cleared + 1.0)

So a single precedent doesn't force a 100% posterior — it moves us
from the base rate (50/50) partway toward its label.

Time-to-resolution is the median hours between ``opened_at`` and
``closed_at`` across terminal precedents; open precedents contribute
their age as a *lower bound* to a separate ``in_flight_median_hours``
tile.

Recommendation ladder
---------------------
Given ``n`` terminal precedents, top-1 similarity ``s*``, and posterior
``p``:

    n ≥ 3, s* ≥ 0.75, p ≥ 0.65    → file_sar_probable   (accent rose)
    n ≥ 3, s* ≥ 0.75, p ≤ 0.25    → expedite_clearance  (accent emerald)
    n ≥ 3, 0.25 < p < 0.65        → weigh_evidence      (accent amber)
    n <  3 or  s* < 0.55          → insufficient_precedent (accent slate)
    n ≥ 3, s* ≥ 0.55, p ∈ (0.65,) → novel_investigate   (accent violet)

The frontend recolours the panel by the recommendation accent so the
verdict is legible at a glance.
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

import cases as case_store
import risk as risk_engine


# ---------------------------------------------------------------------------
# Tunables — mirror shape of the other engines so /aml/precedent/rules can
# expose every knob for auditor review.
# ---------------------------------------------------------------------------

ENGINE_VERSION: str = "titan-precedent/0.1.0"

DEFAULT_K: int = 8
"""Default number of nearest precedents to return."""

MAX_K: int = 24
"""Hard ceiling on ``k`` so a caller can't ask for the entire store."""

MIN_SIM_FLOOR: float = 0.50
"""Precedents below this similarity are dropped from the panel.
Keeps the surface honest — a bag of half-related cases is worse than
"insufficient precedent".  0.50 is roughly "half the weighted vector
overlaps": below that, calling the case a "precedent" is a stretch."""

TOP1_SUPPORT_STRONG: float = 0.75
"""Top-1 similarity above this qualifies for a directional recommendation."""

TOP1_SUPPORT_MIN: float = 0.55
"""Below this the recommendation collapses to ``insufficient_precedent``
regardless of posterior probability."""

MIN_TERMINAL_FOR_PRIOR: int = 3
"""Bayesian prior needs at least this many terminal precedents to be
reported as directional; otherwise we surface it as a hint only."""

POSTERIOR_HIGH: float = 0.65
"""Above this the recommendation leans SAR."""

POSTERIOR_LOW: float = 0.25
"""Below this the recommendation leans cleared."""

# Block weights — sum to 1.0.
FACTOR_BLOCK_WEIGHT: float = 0.55
TYPOLOGY_BLOCK_WEIGHT: float = 0.20
AMOUNT_BLOCK_WEIGHT: float = 0.10
POSTURE_BLOCK_WEIGHT: float = 0.15
_BLOCK_WEIGHTS: Tuple[Tuple[str, float], ...] = (
    ("factor", FACTOR_BLOCK_WEIGHT),
    ("typology", TYPOLOGY_BLOCK_WEIGHT),
    ("amount", AMOUNT_BLOCK_WEIGHT),
    ("posture", POSTURE_BLOCK_WEIGHT),
)

# Nine detectors, in the canonical order the risk engine publishes them.
_DETECTORS: Tuple[str, ...] = risk_engine.DETECTOR_ORDER

_TYPOLOGY_CODES: Tuple[str, ...] = (
    "SMURF", "LAYER", "TBML", "MULE", "SANCEV", "INTEG",
)

# Log10 reference — an account moving 1e8 (10 crore INR) taps the ceiling.
_AMOUNT_LOG_CEIL: float = 8.0

_BAND_ORDINAL: Dict[str, float] = {
    "low": 0.25, "medium": 0.5, "high": 0.75, "critical": 1.0,
}


# ---------------------------------------------------------------------------
# Domain types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _FeatureVec:
    """Block-partitioned feature vector.

    Storing each block as its own tuple lets the cosine kernel walk them
    with the block weights above, so we get "weighted cosine over four
    blocks" without allocating a padded flat vector.
    """

    factor: Tuple[float, ...]     # 9
    typology: Tuple[float, ...]   # 6
    amount: Tuple[float, ...]     # 2
    posture: Tuple[float, ...]    # 2


@dataclass
class _CaseFingerprint:
    """Cached (features, meta) pair for one case in the store.

    ``meta`` carries everything the panel wants to render without a
    second SQLite hop: id, status, band, priority, top typology, event
    counts, opened/closed timestamps.  The engine loads the *whole
    corpus* into memory once per request; even a store with 100k rows
    is under 30MB of fingerprints, so this is fine.
    """

    case_id: str
    features: _FeatureVec
    meta: Dict[str, Any]


@dataclass
class PrecedentMatch:
    case_id: str
    account_id: str
    similarity: float
    status: str
    disposition: str          # sar_filed | cleared | in_flight
    band: str
    priority: str
    typology_code: Optional[str]
    typology_name: Optional[str]
    opened_at_iso: Optional[str]
    closed_at_iso: Optional[str]
    resolution_hours: Optional[float]
    summary: str
    top_factors: List[str] = field(default_factory=list)
    drivers: List[Dict[str, Any]] = field(default_factory=list)
    deltas: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "case_id": self.case_id,
            "account_id": self.account_id,
            "similarity": round(self.similarity, 4),
            "status": self.status,
            "disposition": self.disposition,
            "band": self.band,
            "priority": self.priority,
            "typology_code": self.typology_code,
            "typology_name": self.typology_name,
            "opened_at_iso": self.opened_at_iso,
            "closed_at_iso": self.closed_at_iso,
            "resolution_hours": (
                round(self.resolution_hours, 2)
                if self.resolution_hours is not None else None
            ),
            "summary": self.summary,
            "top_factors": list(self.top_factors),
            "drivers": self.drivers,
            "deltas": self.deltas,
        }


@dataclass
class PrecedentReport:
    query_case_id: str
    query_account_id: str
    query_display_name: str
    query_summary: str
    query_status: str
    query_priority: str
    query_band: str
    query_typology_code: Optional[str]
    query_typology_name: Optional[str]
    corpus_size: int
    considered: int
    matches: List[PrecedentMatch] = field(default_factory=list)
    disposition_counts: Dict[str, int] = field(default_factory=dict)
    posterior: Dict[str, float] = field(default_factory=dict)
    median_resolution_hours: Optional[float] = None
    p95_resolution_hours: Optional[float] = None
    in_flight_median_hours: Optional[float] = None
    recommendation_code: str = "insufficient_precedent"
    recommendation_label: str = "Insufficient precedent"
    recommendation_accent: str = "#94a3b8"
    recommendation_rationale: str = ""
    engine: str = ENGINE_VERSION
    generated_at_iso: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": {
                "case_id": self.query_case_id,
                "account_id": self.query_account_id,
                "display_name": self.query_display_name,
                "summary": self.query_summary,
                "status": self.query_status,
                "priority": self.query_priority,
                "band": self.query_band,
                "typology_code": self.query_typology_code,
                "typology_name": self.query_typology_name,
            },
            "corpus_size": self.corpus_size,
            "considered": self.considered,
            "matches": [m.to_dict() for m in self.matches],
            "disposition_counts": dict(self.disposition_counts),
            "posterior": {k: round(v, 4) for k, v in self.posterior.items()},
            "median_resolution_hours": (
                round(self.median_resolution_hours, 2)
                if self.median_resolution_hours is not None else None
            ),
            "p95_resolution_hours": (
                round(self.p95_resolution_hours, 2)
                if self.p95_resolution_hours is not None else None
            ),
            "in_flight_median_hours": (
                round(self.in_flight_median_hours, 2)
                if self.in_flight_median_hours is not None else None
            ),
            "recommendation": {
                "code": self.recommendation_code,
                "label": self.recommendation_label,
                "accent": self.recommendation_accent,
                "rationale": self.recommendation_rationale,
            },
            "engine": self.engine,
            "generated_at_iso": self.generated_at_iso,
            "rules": get_rules(),
        }


# ---------------------------------------------------------------------------
# Feature extraction
# ---------------------------------------------------------------------------


def _factor_vector(snapshot: Dict[str, Any]) -> Tuple[float, ...]:
    """Extract per-detector firing intensities ∈ [0, 1].

    We normalise each factor's ``points`` against its rule weight so a
    detector at its ceiling registers 1.0 and a partial hit registers
    proportionally.  Missing detectors register 0.0.  This keeps two
    accounts with the same *shape* of firings comparable even when
    absolute scores differ.
    """

    by_name: Dict[str, Tuple[float, float]] = {}
    for factor in (snapshot.get("factors") or []):
        name = str(factor.get("name") or "")
        pts = float(factor.get("points") or 0.0)
        weight = float(factor.get("weight") or 0.0)
        by_name[name] = (pts, weight)

    vec: List[float] = []
    for name in _DETECTORS:
        pts, weight = by_name.get(name, (0.0, 0.0))
        if weight <= 0.0:
            # Fall back to the engine's static weight so a legacy snapshot
            # without weight metadata still normalises correctly.
            weight = float(risk_engine.WEIGHTS.get(name) or 0.0)
        if weight <= 0.0:
            vec.append(0.0)
            continue
        intensity = pts / weight
        # Guard against detectors that overshot their weight (the engine
        # occasionally does when a factor caps at MAX_WEIGHT but the
        # per-detector weight is smaller).
        vec.append(max(0.0, min(1.0, intensity)))
    return tuple(vec)


def _typology_vector(row: Dict[str, Any]) -> Tuple[float, ...]:
    """One-hot the primary typology with confidence as the "on" value."""

    code = row.get("typology_code")
    conf = float(row.get("typology_confidence") or 0.0)
    if code not in _TYPOLOGY_CODES:
        return tuple(0.0 for _ in _TYPOLOGY_CODES)
    return tuple(conf if c == code else 0.0 for c in _TYPOLOGY_CODES)


def _amount_vector(snapshot: Dict[str, Any]) -> Tuple[float, ...]:
    """Log-scaled inbound / outbound totals normalised to [0, 1]."""

    def scale(v: Any) -> float:
        try:
            x = float(v or 0.0)
        except (TypeError, ValueError):
            return 0.0
        if x <= 0.0:
            return 0.0
        # log10 + 1 so a 10-rupee transaction registers positively;
        # bump onto the [0, 1] range against the crore-scale ceiling.
        raw = math.log10(x + 1.0)
        return max(0.0, min(1.0, raw / _AMOUNT_LOG_CEIL))

    inbound = scale(snapshot.get("inbound_total"))
    outbound = scale(snapshot.get("outbound_total"))
    return (inbound, outbound)


def _posture_vector(row: Dict[str, Any], snapshot: Dict[str, Any]) -> Tuple[float, ...]:
    """Band ordinal + sanctions-presence gate."""

    band = str(row.get("band") or "low").lower()
    band_val = _BAND_ORDINAL.get(band, 0.25)
    hits = snapshot.get("sanctions_hits") or []
    sanction_flag = 1.0 if hits else 0.0
    return (band_val, sanction_flag)


def _feature_vector(row: Dict[str, Any]) -> _FeatureVec:
    """Compose the four-block feature vector from a case row + snapshot."""

    snap = row.get("snapshot") or {}
    return _FeatureVec(
        factor=_factor_vector(snap),
        typology=_typology_vector(row),
        amount=_amount_vector(snap),
        posture=_posture_vector(row, snap),
    )


# ---------------------------------------------------------------------------
# Similarity kernel — block-weighted cosine.
# ---------------------------------------------------------------------------


def _cosine(a: Tuple[float, ...], b: Tuple[float, ...]) -> float:
    """Standard cosine similarity with a defensive fallback for the
    all-zeros case.  Two accounts with no firing factors are treated as
    *neutrally* similar (0.0) rather than perfectly similar (1.0) —
    otherwise every quiet baseline pair would poison the retrieval.
    """

    if len(a) != len(b):
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na <= 0.0 or nb <= 0.0:
        # Neither vector fired — no signal, no penalty.
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))


def _similarity(query: _FeatureVec, cand: _FeatureVec) -> Tuple[float, List[Dict[str, Any]]]:
    """Block-weighted cosine.  Returns the similarity ∈ [0, 1] and a
    per-block breakdown so the UI can render which axes drove the match.
    """

    breakdown: List[Dict[str, Any]] = []
    total = 0.0
    for name, weight in _BLOCK_WEIGHTS:
        q = getattr(query, name)
        c = getattr(cand, name)
        cos = _cosine(q, c)
        # Rescale block cosine into [0, 1] — cosine on nonneg vectors is
        # already there, but we clamp defensively for float slop.
        cos = max(0.0, min(1.0, cos))
        contribution = weight * cos
        total += contribution
        breakdown.append({
            "block": name,
            "weight": round(weight, 4),
            "cosine": round(cos, 4),
            "contribution": round(contribution, 4),
        })
    return max(0.0, min(1.0, total)), breakdown


def _deltas(query: _FeatureVec, cand: _FeatureVec) -> List[Dict[str, Any]]:
    """Per-axis absolute deltas, sorted by magnitude descending.

    Used by the panel's "vs precedent" diff view — the analyst sees at
    a glance which factor firings or typology confidences distinguish
    the query from its precedent, not just how similar they are overall.
    Only the top-6 axes are surfaced so the panel stays compact.
    """

    axes: List[Tuple[str, float, float, float]] = []
    for i, name in enumerate(_DETECTORS):
        axes.append((f"factor:{name}", query.factor[i], cand.factor[i],
                     query.factor[i] - cand.factor[i]))
    for i, code in enumerate(_TYPOLOGY_CODES):
        axes.append((f"typology:{code}", query.typology[i], cand.typology[i],
                     query.typology[i] - cand.typology[i]))
    axes.append(("amount:inbound", query.amount[0], cand.amount[0],
                 query.amount[0] - cand.amount[0]))
    axes.append(("amount:outbound", query.amount[1], cand.amount[1],
                 query.amount[1] - cand.amount[1]))
    axes.append(("posture:band", query.posture[0], cand.posture[0],
                 query.posture[0] - cand.posture[0]))
    axes.append(("posture:sanctions", query.posture[1], cand.posture[1],
                 query.posture[1] - cand.posture[1]))
    axes.sort(key=lambda t: abs(t[3]), reverse=True)
    return [
        {
            "axis": axis,
            "query": round(q, 3),
            "candidate": round(c, 3),
            "delta": round(d, 3),
        }
        for axis, q, c, d in axes[:6]
        if abs(d) > 0.02  # drop near-identical axes so the panel isn't noisy
    ]


# ---------------------------------------------------------------------------
# Corpus loader
# ---------------------------------------------------------------------------


def _iso(ts: Optional[float]) -> Optional[str]:
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _load_full_row(case_id: str) -> Optional[Dict[str, Any]]:
    """Fetch a case row *with* its snapshot deserialised.

    Reuses ``cases.get_case`` (which honours the store's threading lock)
    but drops the event list — precedent retrieval doesn't need it and
    the events can be sizeable for old cases.
    """

    row = case_store.get_case(case_id, with_events=False)
    return row


def _load_corpus(exclude: Optional[str] = None) -> List[_CaseFingerprint]:
    """Load every case's fingerprint from the store.

    The case store's ``list_cases`` returns rows *without* snapshots
    (deliberate — the queue polls it every few seconds), so we page
    through and re-fetch each row's snapshot.  For a 100k-case store
    this would want a batched query; for demo-scale (< 5k cases) the
    simple loop is fine and the total time is dominated by the
    fingerprint math, not IO.
    """

    fingerprints: List[_CaseFingerprint] = []
    offset = 0
    page = 500
    seen: set[str] = set()
    while True:
        chunk = case_store.list_cases(limit=page, offset=offset, include_closed=True)
        rows = chunk.get("cases", [])
        if not rows:
            break
        for r in rows:
            cid = r.get("id")
            if not cid or cid in seen:
                continue
            seen.add(cid)
            if exclude and cid == exclude:
                continue
            full = _load_full_row(cid)
            if not full:
                continue
            try:
                vec = _feature_vector(full)
            except Exception:
                # A malformed snapshot shouldn't kill the entire corpus load.
                continue
            snap = full.get("snapshot") or {}
            meta = {
                "id": full["id"],
                "account_id": full.get("account_id"),
                "display_name": full.get("display_name") or "",
                "status": full.get("status"),
                "priority": full.get("priority"),
                "band": full.get("band"),
                "opened_at": full.get("opened_at"),
                "closed_at": full.get("closed_at"),
                "typology_code": full.get("typology_code"),
                "typology_confidence": full.get("typology_confidence"),
                "summary": full.get("summary") or "",
                "top_factors": _top_factor_names(snap),
                "factor_intensities": vec.factor,
            }
            fingerprints.append(_CaseFingerprint(
                case_id=full["id"],
                features=vec,
                meta=meta,
            ))
        if len(rows) < page:
            break
        offset += page
    return fingerprints


def _top_factor_names(snapshot: Dict[str, Any], n: int = 3) -> List[str]:
    factors = [
        f for f in (snapshot.get("factors") or [])
        if float(f.get("points") or 0.0) > 0.0
    ]
    factors.sort(key=lambda f: float(f.get("points") or 0.0), reverse=True)
    out: List[str] = []
    for f in factors[:n]:
        name = f.get("name")
        if name:
            out.append(str(name))
    return out


def _typology_name_for(code: Optional[str]) -> Optional[str]:
    if not code:
        return None
    try:
        import typology as typology_engine
        for t in typology_engine.library():  # type: ignore[attr-defined]
            if t.get("code") == code:
                return t.get("name")
    except Exception:
        pass
    _FALLBACK = {
        "SMURF": "Smurfing / Structuring",
        "LAYER": "Layering",
        "TBML": "Trade-Based ML",
        "MULE": "Mule Network",
        "SANCEV": "Sanctions Evasion",
        "INTEG": "Integration",
    }
    return _FALLBACK.get(code)


# ---------------------------------------------------------------------------
# Posterior + resolution stats
# ---------------------------------------------------------------------------


def _classify_disposition(status: str) -> str:
    if status == "sar_filed":
        return "sar_filed"
    if status == "cleared":
        return "cleared"
    return "in_flight"


def _median(values: List[float]) -> Optional[float]:
    if not values:
        return None
    xs = sorted(values)
    m = len(xs) // 2
    if len(xs) % 2 == 1:
        return xs[m]
    return (xs[m - 1] + xs[m]) / 2.0


def _percentile(values: List[float], pct: float) -> Optional[float]:
    """Type-7 percentile (numpy's default)."""

    if not values:
        return None
    xs = sorted(values)
    if len(xs) == 1:
        return xs[0]
    k = (len(xs) - 1) * (pct / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return xs[int(k)]
    return xs[f] + (xs[c] - xs[f]) * (k - f)


def _bayes_posterior(sar: int, cleared: int, alpha: float = 0.5) -> Dict[str, float]:
    """Two-class Laplace-smoothed posterior."""

    n = sar + cleared
    p_sar = (sar + alpha) / (n + 2 * alpha)
    p_cleared = (cleared + alpha) / (n + 2 * alpha)
    return {"sar_filed": p_sar, "cleared": p_cleared}


def _resolution_hours(opened_at: Optional[float], closed_at: Optional[float]) -> Optional[float]:
    if opened_at is None or closed_at is None:
        return None
    return (closed_at - opened_at) / 3600.0


def _age_hours(opened_at: Optional[float]) -> Optional[float]:
    if opened_at is None:
        return None
    now = datetime.now(timezone.utc).timestamp()
    return (now - opened_at) / 3600.0


# ---------------------------------------------------------------------------
# Recommendation ladder
# ---------------------------------------------------------------------------


_REC_LABELS: Dict[str, Tuple[str, str]] = {
    "file_sar_probable": ("File SAR — precedents lean escalation", "#f43f5e"),
    "expedite_clearance": ("Expedite clearance — precedents lean benign", "#22d3a8"),
    "weigh_evidence": ("Weigh evidence — precedents are mixed", "#fbbf24"),
    "novel_investigate": ("Novel pattern — investigate on merits", "#a855f7"),
    "insufficient_precedent": ("Insufficient precedent — treat as new", "#94a3b8"),
}


def _recommendation(
    matches: List[PrecedentMatch],
    posterior: Dict[str, float],
    terminal_count: int,
) -> Tuple[str, str, str, str]:
    """Return (code, label, accent, rationale)."""

    if not matches:
        code = "insufficient_precedent"
        label, accent = _REC_LABELS[code]
        return code, label, accent, "No prior cases exceed the similarity floor."

    top = matches[0]
    s_star = top.similarity
    p_sar = posterior.get("sar_filed", 0.5)

    if terminal_count < MIN_TERMINAL_FOR_PRIOR or s_star < TOP1_SUPPORT_MIN:
        code = "insufficient_precedent"
        label, accent = _REC_LABELS[code]
        rationale = (
            f"{terminal_count} terminal precedent(s); top-1 similarity "
            f"{s_star:.0%} — below the {int(TOP1_SUPPORT_MIN * 100)}% "
            f"support floor."
        )
        return code, label, accent, rationale

    top_ids = ", ".join(m.case_id for m in matches[:3])
    if s_star >= TOP1_SUPPORT_STRONG and p_sar >= POSTERIOR_HIGH:
        code = "file_sar_probable"
        label, accent = _REC_LABELS[code]
        rationale = (
            f"{terminal_count} terminal precedents; posterior P(SAR)="
            f"{p_sar:.0%}. Leaning on {top_ids}."
        )
        return code, label, accent, rationale

    if s_star >= TOP1_SUPPORT_STRONG and p_sar <= POSTERIOR_LOW:
        code = "expedite_clearance"
        label, accent = _REC_LABELS[code]
        rationale = (
            f"{terminal_count} terminal precedents; posterior P(SAR)="
            f"{p_sar:.0%}. Leaning on {top_ids}."
        )
        return code, label, accent, rationale

    if s_star >= TOP1_SUPPORT_STRONG and POSTERIOR_LOW < p_sar < POSTERIOR_HIGH:
        code = "weigh_evidence"
        label, accent = _REC_LABELS[code]
        rationale = (
            f"{terminal_count} terminal precedents split near "
            f"{p_sar:.0%} SAR; the top precedents ({top_ids}) do not "
            f"converge on a clear disposition."
        )
        return code, label, accent, rationale

    # Support present but not strong — treat as novel and let the analyst drive.
    code = "novel_investigate"
    label, accent = _REC_LABELS[code]
    rationale = (
        f"Top-1 similarity {s_star:.0%} — related but not identical to "
        f"{top_ids}. Investigate on the case's own merits."
    )
    return code, label, accent, rationale


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def compute_for_case(
    case_id: str,
    *,
    k: int = DEFAULT_K,
    min_sim: float = MIN_SIM_FLOOR,
) -> PrecedentReport:
    """Retrieve k nearest precedents for one case + aggregate stats."""

    if k <= 0:
        raise ValueError("k must be positive")
    if k > MAX_K:
        k = MAX_K
    if not (0.0 <= min_sim <= 1.0):
        raise ValueError("min_sim must be in [0, 1]")

    query_row = _load_full_row(case_id)
    if not query_row:
        raise KeyError(case_id)

    query_vec = _feature_vector(query_row)
    corpus = _load_corpus(exclude=case_id)

    scored: List[Tuple[float, List[Dict[str, Any]], _CaseFingerprint]] = []
    for fp in corpus:
        sim, breakdown = _similarity(query_vec, fp.features)
        if sim < min_sim:
            continue
        scored.append((sim, breakdown, fp))
    scored.sort(key=lambda t: t[0], reverse=True)
    top = scored[:k]

    matches: List[PrecedentMatch] = []
    for sim, breakdown, fp in top:
        meta = fp.meta
        drivers = [b for b in breakdown if b["contribution"] > 0.005]
        drivers.sort(key=lambda b: b["contribution"], reverse=True)
        deltas = _deltas(query_vec, fp.features)
        matches.append(PrecedentMatch(
            case_id=fp.case_id,
            account_id=str(meta.get("account_id") or ""),
            similarity=sim,
            status=str(meta.get("status") or "open"),
            disposition=_classify_disposition(str(meta.get("status") or "open")),
            band=str(meta.get("band") or "low"),
            priority=str(meta.get("priority") or "medium"),
            typology_code=meta.get("typology_code"),
            typology_name=_typology_name_for(meta.get("typology_code")),
            opened_at_iso=_iso(meta.get("opened_at")),
            closed_at_iso=_iso(meta.get("closed_at")),
            resolution_hours=_resolution_hours(
                meta.get("opened_at"), meta.get("closed_at"),
            ),
            summary=str(meta.get("summary") or ""),
            top_factors=list(meta.get("top_factors") or []),
            drivers=drivers,
            deltas=deltas,
        ))

    dispo_counts: Dict[str, int] = {"sar_filed": 0, "cleared": 0, "in_flight": 0}
    terminal_res: List[float] = []
    in_flight_ages: List[float] = []
    for m in matches:
        dispo_counts[m.disposition] = dispo_counts.get(m.disposition, 0) + 1
        if m.disposition in ("sar_filed", "cleared") and m.resolution_hours is not None:
            terminal_res.append(m.resolution_hours)
        elif m.disposition == "in_flight":
            age = None
            for _, __, fp in top:
                if fp.case_id == m.case_id:
                    age = _age_hours(fp.meta.get("opened_at"))
                    break
            if age is not None:
                in_flight_ages.append(age)

    posterior = _bayes_posterior(
        dispo_counts.get("sar_filed", 0), dispo_counts.get("cleared", 0),
    )
    terminal_count = dispo_counts.get("sar_filed", 0) + dispo_counts.get("cleared", 0)
    rec_code, rec_label, rec_accent, rec_rationale = _recommendation(
        matches, posterior, terminal_count,
    )

    q_snap = query_row.get("snapshot") or {}
    report = PrecedentReport(
        query_case_id=query_row["id"],
        query_account_id=str(query_row.get("account_id") or ""),
        query_display_name=str(query_row.get("display_name") or ""),
        query_summary=str(query_row.get("summary") or ""),
        query_status=str(query_row.get("status") or "open"),
        query_priority=str(query_row.get("priority") or "medium"),
        query_band=str(query_row.get("band") or "low"),
        query_typology_code=query_row.get("typology_code"),
        query_typology_name=_typology_name_for(query_row.get("typology_code")),
        corpus_size=len(corpus),
        considered=len(scored),
        matches=matches,
        disposition_counts=dispo_counts,
        posterior=posterior,
        median_resolution_hours=_median(terminal_res),
        p95_resolution_hours=_percentile(terminal_res, 95.0),
        in_flight_median_hours=_median(in_flight_ages),
        recommendation_code=rec_code,
        recommendation_label=rec_label,
        recommendation_accent=rec_accent,
        recommendation_rationale=rec_rationale,
        generated_at_iso=datetime.now(timezone.utc).isoformat(),
    )
    # Silence unused variable warning for the snapshot — retained so a
    # future extension (e.g. narrative fragments) has a hook.
    _ = q_snap
    return report


def list_query_candidates(
    *,
    limit: int = 100,
    include_closed: bool = False,
) -> List[Dict[str, Any]]:
    """Cases suitable as a Precedent *query*.

    The panel drives off the open/review queue by default: closed cases
    are usually more interesting as precedents than as queries.  The
    ``include_closed`` flag lets an auditor pull a closed case up to
    see who its precedents were at the time.
    """

    chunk = case_store.list_cases(
        limit=limit, include_closed=include_closed,
    )
    out: List[Dict[str, Any]] = []
    for c in chunk.get("cases", []):
        out.append({
            "case_id": c.get("id"),
            "account_id": c.get("account_id"),
            "display_name": c.get("display_name") or c.get("account_id") or "",
            "status": c.get("status"),
            "priority": c.get("priority"),
            "band": c.get("band"),
            "opened_at_iso": c.get("opened_at_iso"),
            "typology_code": c.get("typology_code"),
            "summary": c.get("summary") or "",
        })
    return out


# ---------------------------------------------------------------------------
# Sample seeding — so a fresh install has something to render.
# ---------------------------------------------------------------------------


def _sample_account_report(
    *,
    account_id: str,
    display_name: str,
    band: str,
    typology_code: Optional[str],
    inbound: float,
    outbound: float,
    firing: Dict[str, float],
    typology_confidence: float = 0.6,
    sanction_hits: int = 0,
) -> Dict[str, Any]:
    """Build a minimal /aml/score-shaped account report for seeding."""

    factors: List[Dict[str, Any]] = []
    for name in _DETECTORS:
        weight = risk_engine.WEIGHTS.get(name, 0.0)
        intensity = firing.get(name, 0.0)
        pts = round(min(intensity, 1.0) * weight, 2)
        factors.append({
            "name": name,
            "weight": weight,
            "points": pts,
            "detail": f"seed intensity {intensity:.2f}",
            "evidence": [],
        })
    risk_score = round(sum(f["points"] for f in factors), 2)
    typologies: List[Dict[str, Any]] = []
    if typology_code:
        typologies = [{
            "code": typology_code,
            "name": _typology_name_for(typology_code) or typology_code,
            "confidence": typology_confidence,
            "severity_floor": (
                "critical" if typology_code == "SANCEV"
                else "high" if typology_code in ("SMURF", "LAYER", "TBML")
                else "medium"
            ),
        }]
    return {
        "account_id": account_id,
        "display_name": display_name,
        "risk_score": risk_score,
        "band": band,
        "factors": factors,
        "sanctions_hits": [
            {"similarity": 0.82, "grade": "strong", "entity_id": f"SEED-{i}"}
            for i in range(sanction_hits)
        ],
        "adverse_media": None,
        "edges": [],
        "counterparty_count": 8,
        "inbound_total": inbound,
        "outbound_total": outbound,
        "typologies": typologies,
    }


# Blueprints describing "similarity families" — batches of cases with the
# same rough shape so retrieval finds real neighbours.  Two SMURF cases
# with different amounts should retrieve each other; the SANCEV cluster
# should have a clear 100% SAR-file rate; MULE cluster is mixed.
# Family blueprints chosen for two properties:
# 1. Cross-family cosine over the factor block stays below the 0.50
#    similarity floor — a SMURF query should not routinely retrieve a
#    MULE precedent, because their firing shapes barely overlap
#    (structuring/fan_in vs fan_in/fan_out/velocity is only ~0.29 cos).
# 2. Within-family disposition mix is intentionally skewed so the demo
#    exercises each rung of the recommendation ladder:
#      SMURF, LAYER, SANCEV   → strongly SAR-filed → file_sar_probable
#      TBML                   → mixed 3/2          → weigh_evidence
#      MULE                   → strongly cleared   → expedite_clearance
#      Baseline               → all cleared        → expedite_clearance
_SEED_FAMILIES: Tuple[Dict[str, Any], ...] = (
    {
        "family": "SMURF-heavy",
        "typology_code": "SMURF",
        "band": "high",
        "firing": {"structuring": 0.95, "fan_in": 0.55, "round_amount": 0.55},
        "amount_range": (800_000.0, 3_500_000.0),
        "outbound_multiplier": 0.15,
        "sanction_hits": 0,
        "labels": ["sar_filed", "sar_filed", "sar_filed", "sar_filed", "cleared"],
    },
    {
        "family": "LAYER-cycle",
        "typology_code": "LAYER",
        "band": "high",
        "firing": {"round_trip": 0.90, "velocity_spike": 0.45, "high_risk_geo": 0.50},
        "amount_range": (400_000.0, 1_800_000.0),
        "outbound_multiplier": 0.98,
        "sanction_hits": 0,
        "labels": ["sar_filed", "sar_filed", "sar_filed", "cleared", "sar_filed"],
    },
    {
        "family": "MULE-passthrough",
        "typology_code": "MULE",
        "band": "medium",
        "firing": {"fan_in": 0.75, "fan_out": 0.80, "velocity_spike": 0.60},
        "amount_range": (150_000.0, 900_000.0),
        "outbound_multiplier": 0.95,
        "sanction_hits": 0,
        "labels": ["cleared", "cleared", "cleared", "cleared", "sar_filed"],
    },
    {
        "family": "TBML-cross-border",
        "typology_code": "TBML",
        "band": "high",
        "firing": {"high_risk_geo": 0.85, "fan_out": 0.65, "round_amount": 0.55,
                   "sanctions_hit": 0.30},
        "amount_range": (2_000_000.0, 9_500_000.0),
        "outbound_multiplier": 1.0,
        "sanction_hits": 0,
        "labels": ["sar_filed", "cleared", "sar_filed", "cleared", "sar_filed"],
    },
    {
        "family": "SANCEV-watchlist",
        "typology_code": "SANCEV",
        "band": "critical",
        "firing": {"sanctions_hit": 0.95, "high_risk_geo": 0.65, "round_trip": 0.40},
        "amount_range": (600_000.0, 4_500_000.0),
        "outbound_multiplier": 1.0,
        "sanction_hits": 2,
        "labels": ["sar_filed", "sar_filed", "sar_filed", "sar_filed", "sar_filed"],
    },
    {
        "family": "Baseline-quiet",
        "typology_code": None,
        "band": "low",
        "firing": {"velocity_spike": 0.20},
        "amount_range": (50_000.0, 300_000.0),
        "outbound_multiplier": 1.0,
        "sanction_hits": 0,
        "labels": ["cleared", "cleared", "cleared", "cleared", "cleared"],
    },
)


def seed_sample_cases(*, force: bool = False) -> Dict[str, Any]:
    """Populate the case store with the sample precedent portfolio.

    Skips if the store already has ≥ 8 terminal cases (which is enough
    to produce a meaningful precedent panel) unless ``force`` is set.
    """

    existing = case_store.stats()
    terminal_existing = (
        existing["by_status"].get("sar_filed", 0)
        + existing["by_status"].get("cleared", 0)
    )
    if not force and terminal_existing >= 8:
        return {
            "seeded": 0,
            "reason": "corpus already has ≥ 8 terminal cases",
            "terminal_count": terminal_existing,
        }

    now = datetime.now(timezone.utc).timestamp()
    seeded = 0
    for fam in _SEED_FAMILIES:
        lo, hi = fam["amount_range"]
        step = (hi - lo) / max(len(fam["labels"]), 1)
        for i, label in enumerate(fam["labels"]):
            inbound = lo + step * i
            outbound = inbound * fam["outbound_multiplier"]
            aid = f"PRECEDENT-{fam['family'][:4].upper()}-{i+1:02d}"
            display = f"{fam['family']} example #{i+1}"
            report = _sample_account_report(
                account_id=aid,
                display_name=display,
                band=fam["band"],
                typology_code=fam["typology_code"],
                inbound=inbound,
                outbound=outbound,
                firing=fam["firing"],
                sanction_hits=fam["sanction_hits"],
            )
            try:
                case = case_store.open_case(
                    report,
                    opened_by="PRECEDENT-SEED",
                    note=f"Seeded from {fam['family']} family for /precedent demo.",
                )
            except Exception:
                continue
            seeded += 1
            # Wind the clock backward on the opened-at + closed-at so the
            # precedent panel has realistic ages (7-45 days old, resolved
            # inside 8-96h).
            days_ago = 7 + (i + 1) * 3 + hash(fam["family"]) % 14
            opened_at = now - days_ago * 86400.0
            resolution_h = 12.0 + (i * 20.0) + (hash(aid) % 40)
            closed_at = opened_at + resolution_h * 3600.0
            _stamp_disposition(case["id"], label, opened_at=opened_at, closed_at=closed_at)
    return {
        "seeded": seeded,
        "families": [f["family"] for f in _SEED_FAMILIES],
        "terminal_count_after": terminal_existing + seeded,
    }


def _stamp_disposition(
    case_id: str,
    disposition: str,
    *,
    opened_at: float,
    closed_at: float,
) -> None:
    """Transition a seeded case directly to a terminal state and
    back-date its opened_at / closed_at so the report shows realistic
    ages.  Uses the case store's public API for the transition, then a
    single UPDATE to shift timestamps — the store treats the operation
    as an audit-anchored replay, which is fine for seed data.
    """

    if disposition not in ("sar_filed", "cleared"):
        return
    # Move: open → review → terminal.
    try:
        case_store.transition(case_id, to_status="review", actor="PRECEDENT-SEED",
                              note="Seed transition")
        case_store.transition(case_id, to_status=disposition, actor="PRECEDENT-SEED",
                              note="Seed disposition")
    except Exception:
        return
    # Back-date so the panel shows spread-out precedents.
    import sqlite3
    db_path = case_store.DB_PATH
    if not os.path.exists(db_path):
        return
    try:
        conn = sqlite3.connect(db_path, timeout=8.0)
        try:
            conn.execute(
                "UPDATE cases SET opened_at=?, last_event_at=?, closed_at=? WHERE id=?",
                (opened_at, closed_at, closed_at, case_id),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        return


# ---------------------------------------------------------------------------
# Auditor surface
# ---------------------------------------------------------------------------


def get_rules() -> Dict[str, Any]:
    """Full tunable + block-weight dump so /aml/precedent/rules is the
    single source of truth for how the engine composes similarity.
    """

    return {
        "engine": ENGINE_VERSION,
        "defaults": {
            "k": DEFAULT_K,
            "max_k": MAX_K,
            "min_similarity": MIN_SIM_FLOOR,
            "top1_support_strong": TOP1_SUPPORT_STRONG,
            "top1_support_min": TOP1_SUPPORT_MIN,
            "min_terminal_for_prior": MIN_TERMINAL_FOR_PRIOR,
            "posterior_high": POSTERIOR_HIGH,
            "posterior_low": POSTERIOR_LOW,
        },
        "blocks": [
            {"block": name, "weight": weight, "size": _block_size(name)}
            for name, weight in _BLOCK_WEIGHTS
        ],
        "detectors": list(_DETECTORS),
        "typologies": list(_TYPOLOGY_CODES),
        "recommendations": [
            {"code": code, "label": label, "accent": accent}
            for code, (label, accent) in _REC_LABELS.items()
        ],
    }


def _block_size(name: str) -> int:
    return {
        "factor": len(_DETECTORS),
        "typology": len(_TYPOLOGY_CODES),
        "amount": 2,
        "posture": 2,
    }.get(name, 0)


# ---------------------------------------------------------------------------
# Markdown export — pasteable analyst memo.
# ---------------------------------------------------------------------------


def to_markdown(report: PrecedentReport) -> str:
    lines: List[str] = []
    lines.append(f"# Precedent memo — {report.query_case_id}")
    lines.append("")
    lines.append(
        f"**Query**: {report.query_display_name or report.query_account_id} "
        f"(band: {report.query_band}, priority: {report.query_priority})"
    )
    if report.query_typology_name:
        lines.append(f"**Typology**: {report.query_typology_name}")
    lines.append(f"**Summary**: {report.query_summary}")
    lines.append("")
    lines.append(f"## Recommendation: {report.recommendation_label}")
    lines.append("")
    lines.append(report.recommendation_rationale)
    lines.append("")
    lines.append("## Aggregate")
    lines.append("")
    lines.append(
        f"- Corpus scanned: {report.corpus_size} case(s); "
        f"{report.considered} met the {int(MIN_SIM_FLOOR * 100)}% similarity floor."
    )
    lines.append(
        "- Disposition mix: "
        + ", ".join(
            f"{k}={v}" for k, v in report.disposition_counts.items() if v
        )
        or "- Disposition mix: none"
    )
    if report.posterior:
        lines.append(
            f"- Posterior (Laplace-smoothed): "
            f"SAR = {report.posterior.get('sar_filed', 0.0):.0%}, "
            f"cleared = {report.posterior.get('cleared', 0.0):.0%}"
        )
    if report.median_resolution_hours is not None:
        lines.append(
            f"- Median time-to-resolution across terminal precedents: "
            f"{report.median_resolution_hours:.1f}h"
        )
    lines.append("")
    lines.append("## Top precedents")
    lines.append("")
    if not report.matches:
        lines.append("_No precedent above the similarity floor._")
    for m in report.matches:
        lines.append(
            f"- **{m.case_id}** — {m.similarity:.0%} similar · "
            f"{m.disposition} · {m.band} · "
            f"{m.typology_name or 'no typology'}"
        )
        if m.top_factors:
            lines.append(f"  - Top factors: {', '.join(m.top_factors)}")
    lines.append("")
    lines.append(f"_Engine {report.engine} · generated {report.generated_at_iso}_")
    return "\n".join(lines)


__all__ = [
    "ENGINE_VERSION",
    "DEFAULT_K",
    "MAX_K",
    "MIN_SIM_FLOOR",
    "PrecedentMatch",
    "PrecedentReport",
    "compute_for_case",
    "list_query_candidates",
    "seed_sample_cases",
    "get_rules",
    "to_markdown",
]
