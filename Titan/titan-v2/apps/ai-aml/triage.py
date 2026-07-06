"""TITAN Triage — false-positive suppression via cleared-case mining.

Every prior TITAN surface asks *"how severe is this alert?"*.  Compliance
teams also have the inverse operational question — *"how likely is this
alert to be noise?"* — because real AML book runs at a 90-95% false
positive rate.  Analysts drown in noise; the strongest gain isn't a
sharper detector, it's a *learned* suppression pass that says "we have
cleared this exact signature eight times, with zero SAR filings, in the
last quarter".

Triage is that pass.  It mines the case store's terminal history
(``cleared`` vs ``sar_filed``) — no ML training loop, no opaque model
— and computes, for any candidate alert, a Bayesian log-lift-blended
suppression score with named precedent chains that justify the verdict.

Every constant is exposed via ``get_rules()`` for auditor review;
every posterior is reproducible from the exact case IDs it cites.

Design
======

1.  **Signature.**  The K highest-firing factor names on the query
    alert (K = ``SIGNATURE_TOP_K``, default 4).  Factors with
    ``points ≤ 0`` never enter the signature — non-firing detectors
    aren't evidence of anything.  ``sanctions_hit`` is *never*
    treated as a noise signal (see rule 5): it stays in the signature
    for cross-referencing, but is excluded from the aggregate S sum
    on its own.

2.  **Combos.**  Every singleton in the signature *and* every
    unordered pair drawn from it.  A signature of ``{A, B, C, D}``
    produces 4 singletons + 6 pairs = 10 combos.  Pair combos are
    the interesting ones — real ops FPs cluster around specific
    factor *pairs* (round_amount + fan_in on a cash-desk teller,
    velocity_spike + high_risk_geo on a legitimate remitter).

3.  **Combo posterior (Beta-Bernoulli).**  For each combo *c* the
    engine counts, across every closed case:

        n_seen(c)    = closed cases whose signature ⊇ c
        n_cleared(c) = of those, disposition == cleared
        n_sar(c)     = of those, disposition == sar_filed

    Laplace-smoothed clearance probability:

        p_clear(c)   = (n_cleared(c) + α) / (n_seen(c) + 2α)     α = 0.5

    A single precedent never collapses the posterior to 100%.

4.  **Log-lift.**  Compared against the portfolio prior
    ``p_clear_prior = cleared_all / (cleared_all + sar_all)``:

        lift(c) = log2( p_clear(c) / p_clear_prior )

    A combo with ``lift > 0`` is a *noise indicator* — it clears at a
    higher-than-baseline rate.  ``lift < 0`` is a *signal indicator*.
    Symmetric around 0 → the aggregate is bias-free.

5.  **Aggregate suppression score.**

        w(c) = min(1, n_seen(c) / MIN_SUPPORT_STRONG)   # evidence weight
        S    = tanh( Σ w(c) · lift(c) / |combos_scored| )
        suppression = clamp( (S + 1) / 2, 0, 1 )

    The tanh keeps S ∈ (-1, +1) even when a single combo has extreme
    lift; the evidence weight discounts under-supported combos so
    they can't drive suppression by themselves.  The mean divisor
    keeps a signature with 10 combos from out-voting one with 3.

    **Sanctions veto.**  If the signature contains ``sanctions_hit``,
    the aggregate S is capped from *above* at
    ``SANCTIONS_S_CEILING`` (-0.2) — a sanctions-touching alert can
    never suppress, regardless of how many cleared cases share other
    factors.  Escalation (S ≤ ``S_ESCALATE``) is unaffected — the
    veto is upward-only, so a sanctions hit with SAR-heavy
    precedents still escalates.

6.  **Verdict ladder.**  Five explicit rungs plus one abstain:

        S ≥ +0.65 & max_supported_lift ≥ +1.5   → suppress_high_confidence
        +0.30 ≤ S < +0.65                        → suppress_review_lightly
        -0.30 < S < +0.30                        → no_prior_signal
        -0.65 ≤ S ≤ -0.30                        → elevate_review
        S < -0.65                                → escalate_critical
        No combo has n_seen ≥ MIN_SUPPORT_ANY    → insufficient_history

7.  **Evidence chains.**  Up to 3 cleared precedents and 3 SAR
    precedents whose signatures share ≥ 2 factors with the query
    signature — ranked by (# shared factors ↓, opened_at ↓).  Every
    recommendation cites concrete case IDs so an auditor can trace
    every point back to the source disposition.

Public API
==========

    rules() -> Dict
        Auditor-facing constants + verdict ladder + factor list.
    corpus_summary() -> Dict
        Portfolio-wide prior + per-factor stats + suppression matrix +
        top noise/signal combos.  Used by ``/aml/triage/profile``.
    candidates(limit=100) -> List[Dict]
        Open + review + escalated cases eligible as triage queries.
    triage_for_case(case_id) -> Dict
        Full per-case triage report.
    seed_sample_cases(force=False) -> Dict
        Bulk-seed a false-positive-rich supplementary corpus so the
        engine's mining has enough evidence for the demo.
    to_markdown(report) -> str
        Paste-able triage memo (for /aml/triage/export.md).

Everything is pure stdlib (json / math / re / hashlib / sqlite via the
case store); no new deps.  Determinism guarantee: same case store
snapshot → identical bytes returned, identical case IDs cited.
"""

from __future__ import annotations

import itertools
import json
import math
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

import cases as case_store


ENGINE_VERSION = "titan-triage/1.0.0"

# ---------------------------------------------------------------------------
# Constants — every one exposed via get_rules() for auditor review.
# ---------------------------------------------------------------------------

# Detectors, in the canonical order they appear in the AML risk engine.
DETECTORS: Tuple[str, ...] = (
    "structuring",
    "velocity_spike",
    "round_trip",
    "sanctions_hit",
    "adverse_media",
    "fan_in",
    "fan_out",
    "high_risk_geo",
    "round_amount",
)

# Display labels for the surface.
DETECTOR_LABEL: Dict[str, str] = {
    "structuring":    "Structuring",
    "velocity_spike": "Velocity spike",
    "round_trip":     "Round trip",
    "sanctions_hit":  "Sanctions hit",
    "adverse_media":  "Adverse media",
    "fan_in":         "Fan-in",
    "fan_out":        "Fan-out",
    "high_risk_geo":  "High-risk geo",
    "round_amount":   "Round amount",
}

# Signature = top-K firing factors.  K = 4 balances "big enough to
# form informative pairs" against "small enough to keep combinations
# tractable and support-heavy per combo".
SIGNATURE_TOP_K = 4

# Smoothing prior on the Beta-Bernoulli clearance posterior.  0.5 is
# the Jeffreys prior — mildly informative, symmetric.
LAPLACE_ALPHA = 0.5

# Combo must have this many precedents to reach full evidence weight
# ``w(c) = 1``; below it, weight scales linearly.
MIN_SUPPORT_STRONG = 5

# Combo must have at least this many precedents to be considered
# scored at all.  If NO combo clears this floor, the engine returns
# ``insufficient_history`` and never suppresses.
MIN_SUPPORT_ANY = 3

# Sanctions veto: a sanctions-touching signature can never suppress
# into noise territory, no matter how many cleared cases share other
# factors — S is capped from above at this ceiling so the verdict
# ladder can never place the alert above ``no_prior_signal``.
# Escalation is unaffected: a naturally-negative S propagates through
# unchanged (a sanctions hit with SAR-heavy precedents still escalates).
SANCTIONS_S_CEILING = -0.2

# Verdict thresholds on the aggregate ``S`` score.  Kept as
# module-level constants (not derived from the ladder table below)
# so an auditor's grep for a specific number lands on the exact
# constant that drives the decision.
S_SUPPRESS_HIGH   = 0.65
S_SUPPRESS_LIGHT  = 0.30
S_ELEVATE_REVIEW  = -0.30
S_ESCALATE        = -0.65

# For ``suppress_high_confidence`` we ALSO require at least one
# supported combo (n_seen ≥ MIN_SUPPORT_STRONG) with lift ≥ this
# value.  Prevents a wide but weakly-informative fan of combos from
# summing into an unjustified strong suppression.
MAX_LIFT_STRONG_MIN = 1.5

# Verdict ladder — machine code → (label, accent hex, hero-tone).
# Hero-tone controls which radial-gradient the /triage surface paints
# behind the recommendation banner.
_VERDICT_META: Tuple[Tuple[str, str, str, str], ...] = (
    ("suppress_high_confidence",
     "Suppress — high confidence noise",  "#22d3a8", "emerald"),
    ("suppress_review_lightly",
     "Suppress — lightweight review",     "#67e8f9", "cyan"),
    ("no_prior_signal",
     "No prior signal — proceed with judgment", "#94a3b8", "slate"),
    ("elevate_review",
     "Elevate — leans signal",             "#fbbf24", "amber"),
    ("escalate_critical",
     "Escalate — strong SAR precedent",   "#f43f5e", "rose"),
    ("insufficient_history",
     "Insufficient history — decide on merits", "#a855f7", "violet"),
)

_VERDICT_LABEL: Dict[str, str] = {c: lbl for c, lbl, _, _ in _VERDICT_META}
_VERDICT_ACCENT: Dict[str, str] = {c: accent for c, _, accent, _ in _VERDICT_META}
_VERDICT_TONE: Dict[str, str] = {c: tone for c, _, _, tone in _VERDICT_META}

# Maximum number of precedent cases returned per side (cleared / sar).
MAX_EVIDENCE_PER_SIDE = 3

# Every scored combo returned in the report; keeps payloads sane.
MAX_COMBO_ROWS = 24

# Top-N noise / signal combos surfaced in the portfolio profile.
PROFILE_TOP_COMBOS = 8


# ---------------------------------------------------------------------------
# Corpus loader — reuses case store's public API.
# ---------------------------------------------------------------------------


def _signature_from_snapshot(
    snapshot: Dict[str, Any], k: int = SIGNATURE_TOP_K,
) -> List[str]:
    """The K highest-firing factor names.  Ties broken by DETECTORS order."""
    factors = [
        f for f in (snapshot.get("factors") or [])
        if float(f.get("points") or 0.0) > 0.0
    ]
    order_index = {name: idx for idx, name in enumerate(DETECTORS)}
    factors.sort(
        key=lambda f: (
            -float(f.get("points") or 0.0),
            order_index.get(str(f.get("name") or ""), len(DETECTORS)),
        ),
    )
    seen: List[str] = []
    for f in factors:
        name = str(f.get("name") or "")
        if name and name in DETECTOR_LABEL and name not in seen:
            seen.append(name)
        if len(seen) >= k:
            break
    return seen


def _iso(ts: Optional[float]) -> Optional[str]:
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _load_closed_corpus() -> List[Dict[str, Any]]:
    """Every terminal case's row + snapshot-derived signature + disposition.

    ``list_cases`` returns rows without snapshots (queue-optimised);
    we page and refetch each terminal row.  For demo-scale (<5k cases)
    the trivial loop is fine; production would want batched IN queries
    on ``cases.snapshot_json`` and a materialised signature column.
    """
    out: List[Dict[str, Any]] = []
    seen: set[str] = set()
    offset = 0
    page = 500
    while True:
        chunk = case_store.list_cases(
            limit=page, offset=offset, include_closed=True,
        )
        rows = chunk.get("cases", [])
        if not rows:
            break
        for r in rows:
            cid = r.get("id")
            status = r.get("status")
            if not cid or cid in seen:
                continue
            seen.add(cid)
            if status not in ("cleared", "sar_filed"):
                continue
            full = case_store.get_case(cid, with_events=False)
            if not full:
                continue
            snap = full.get("snapshot") or {}
            signature = _signature_from_snapshot(snap)
            if not signature:
                # A closed case with no firing factors is uninformative
                # for combo mining — skip so the base rate isn't
                # distorted by empty signatures.
                continue
            out.append({
                "id": cid,
                "account_id": full.get("account_id") or "",
                "display_name": full.get("display_name") or "",
                "band": full.get("band") or "",
                "priority": full.get("priority") or "",
                "typology_code": full.get("typology_code"),
                "typology_confidence": full.get("typology_confidence"),
                "disposition": status,  # cleared | sar_filed
                "signature": signature,
                "signature_set": set(signature),
                "risk_score": float(full.get("risk_score") or 0.0),
                "opened_at": full.get("opened_at"),
                "closed_at": full.get("closed_at"),
                "summary": full.get("summary") or "",
            })
        if len(rows) < page:
            break
        offset += page
    return out


# ---------------------------------------------------------------------------
# Mining primitives — pure functions over the loaded corpus.
# ---------------------------------------------------------------------------


def _combo_key(combo: Iterable[str]) -> str:
    """Stable key for a combo — sorted, colon-joined."""
    return ":".join(sorted(combo))


def _combos_for_signature(signature: List[str]) -> List[Tuple[str, ...]]:
    """Singletons + all unordered pairs drawn from the signature."""
    combos: List[Tuple[str, ...]] = []
    for f in signature:
        combos.append((f,))
    for a, b in itertools.combinations(sorted(signature), 2):
        combos.append((a, b))
    return combos


def _prior_from_corpus(corpus: List[Dict[str, Any]]) -> Tuple[int, int, float]:
    """Return ``(cleared_all, sar_all, p_clear_prior)``.

    Falls back to 0.5 when no terminal cases exist so downstream
    log-lift stays finite; ``insufficient_history`` will fire anyway.
    """
    cleared_all = sum(1 for c in corpus if c["disposition"] == "cleared")
    sar_all     = sum(1 for c in corpus if c["disposition"] == "sar_filed")
    total       = cleared_all + sar_all
    if total == 0:
        return 0, 0, 0.5
    return cleared_all, sar_all, cleared_all / total


def _tally_combo(
    corpus: List[Dict[str, Any]], combo: Tuple[str, ...],
) -> Tuple[int, int]:
    """Return ``(n_cleared, n_sar)`` where ``signature ⊇ combo``."""
    needed = set(combo)
    n_c = n_s = 0
    for row in corpus:
        if not needed.issubset(row["signature_set"]):
            continue
        if row["disposition"] == "cleared":
            n_c += 1
        elif row["disposition"] == "sar_filed":
            n_s += 1
    return n_c, n_s


def _posterior_clear(n_cleared: int, n_sar: int) -> float:
    """Laplace-smoothed clearance posterior for one combo."""
    return (n_cleared + LAPLACE_ALPHA) / (n_cleared + n_sar + 2 * LAPLACE_ALPHA)


def _log_lift(p_clear: float, p_clear_prior: float) -> float:
    """log2 lift of a combo's clearance rate over the portfolio prior.

    Both probabilities live in (0, 1) thanks to Laplace smoothing so
    log2 is always finite.  A tiny epsilon on the prior guards against
    the pathological all-cleared or all-SAR portfolio (which triggers
    ``insufficient_history`` upstream anyway).
    """
    p_c = max(1e-6, min(1 - 1e-6, p_clear))
    p_prior = max(1e-6, min(1 - 1e-6, p_clear_prior))
    return math.log2(p_c / p_prior)


def _evidence_weight(n_seen: int) -> float:
    if MIN_SUPPORT_STRONG <= 0:
        return 1.0
    return min(1.0, n_seen / MIN_SUPPORT_STRONG)


# ---------------------------------------------------------------------------
# Verdict resolution.
# ---------------------------------------------------------------------------


def _resolve_verdict(
    s: float,
    max_supported_lift: float,
    has_sanctions: bool,
    scored_combos: int,
) -> Tuple[str, str]:
    """Return ``(verdict_code, verdict_reason)``.

    Reason is a single terse sentence the surface renders as the
    banner subtitle; the reason names the exact number that fired
    the rung so an auditor can grep back to the case.
    """
    if scored_combos == 0:
        return (
            "insufficient_history",
            "No scored factor combos have enough case-store history yet "
            "(need ≥ %d closed precedents per combo)." % MIN_SUPPORT_ANY,
        )

    # Sanctions veto: cap S from ABOVE so a sanctions-touching
    # signature can never reach suppression territory.  Escalation
    # (S ≤ S_ESCALATE) is unaffected — the veto is upward-only.
    effective_s = min(SANCTIONS_S_CEILING, s) if has_sanctions else s

    if effective_s >= S_SUPPRESS_HIGH and max_supported_lift >= MAX_LIFT_STRONG_MIN:
        return (
            "suppress_high_confidence",
            (
                "Aggregate log-lift %+.2f with at least one strongly "
                "supported combo (lift ≥ %+.2f) — near-identical "
                "signatures cleared far more often than baseline."
            ) % (effective_s, MAX_LIFT_STRONG_MIN),
        )
    if effective_s >= S_SUPPRESS_LIGHT:
        return (
            "suppress_review_lightly",
            (
                "Aggregate log-lift %+.2f — signature leans historically "
                "noisy, but evidence is not strong enough for a hard "
                "suppression."
            ) % effective_s,
        )
    if effective_s <= S_ESCALATE:
        return (
            "escalate_critical",
            (
                "Aggregate log-lift %+.2f — signature strongly overlaps "
                "prior SAR filings.  Escalate for L2 review before any "
                "suppression."
            ) % effective_s,
        )
    if effective_s <= S_ELEVATE_REVIEW:
        return (
            "elevate_review",
            (
                "Aggregate log-lift %+.2f — signature leans signal, but "
                "not decisive.  Full manual review recommended."
            ) % effective_s,
        )
    return (
        "no_prior_signal",
        (
            "Aggregate log-lift %+.2f — the case store does not lean this "
            "signature either way.  Judge on merits."
        ) % effective_s,
    )


# ---------------------------------------------------------------------------
# Public: per-case triage report.
# ---------------------------------------------------------------------------


def triage_for_case(case_id: str) -> Dict[str, Any]:
    """Compute a full triage report for ``case_id``.

    Raises ``KeyError`` if the case doesn't exist and ``ValueError``
    if the case has no firing factors (a signature-less alert can't
    be triaged against the disposition history).
    """
    full = case_store.get_case(case_id, with_events=False)
    if not full:
        raise KeyError(case_id)
    snap = full.get("snapshot") or {}
    query_signature = _signature_from_snapshot(snap)
    if not query_signature:
        raise ValueError(
            "case %s has no firing factors — Triage requires a non-empty "
            "signature." % case_id
        )
    query_sig_set = set(query_signature)

    corpus_all = _load_closed_corpus()
    # Never let the query's own row (if it's terminal) contaminate its
    # own posterior — leave-one-out is the honest computation.
    corpus = [c for c in corpus_all if c["id"] != case_id]
    cleared_all, sar_all, p_prior = _prior_from_corpus(corpus)

    combos = _combos_for_signature(query_signature)
    combo_rows: List[Dict[str, Any]] = []
    supported_lifts: List[float] = []
    weighted_sum = 0.0
    scored_combos = 0
    max_supported_lift = -math.inf

    for combo in combos:
        n_c, n_s = _tally_combo(corpus, combo)
        n_seen = n_c + n_s
        p_c = _posterior_clear(n_c, n_s)
        lift = _log_lift(p_c, p_prior)
        weight = _evidence_weight(n_seen)
        if n_seen >= MIN_SUPPORT_ANY:
            weighted_sum += weight * lift
            scored_combos += 1
            if n_seen >= MIN_SUPPORT_STRONG:
                supported_lifts.append(lift)
                if lift > max_supported_lift:
                    max_supported_lift = lift
        combo_rows.append({
            "combo": list(combo),
            "key": _combo_key(combo),
            "size": len(combo),
            "n_seen": n_seen,
            "n_cleared": n_c,
            "n_sar": n_s,
            "p_clear": round(p_c, 4),
            "lift": round(lift, 4),
            "weight": round(weight, 4),
            "supported": n_seen >= MIN_SUPPORT_ANY,
            "strongly_supported": n_seen >= MIN_SUPPORT_STRONG,
        })

    # Aggregate S.  Divide by scored_combos so a wide signature (10
    # combos) can't out-vote a narrow one (3 combos) purely on breadth.
    if scored_combos > 0:
        raw_s = weighted_sum / scored_combos
        s = math.tanh(raw_s)
    else:
        raw_s = 0.0
        s = 0.0

    has_sanctions = "sanctions_hit" in query_sig_set
    verdict_code, verdict_reason = _resolve_verdict(
        s=s,
        max_supported_lift=(max_supported_lift
                            if supported_lifts else -math.inf),
        has_sanctions=has_sanctions,
        scored_combos=scored_combos,
    )
    verdict_label = _VERDICT_LABEL[verdict_code]
    accent = _VERDICT_ACCENT[verdict_code]
    tone = _VERDICT_TONE[verdict_code]

    suppression = max(0.0, min(1.0, (s + 1.0) / 2.0))

    # Order combo rows: strongly-supported first, then by lift magnitude
    # descending so the surface always shows the loudest signals up top.
    combo_rows.sort(key=lambda r: (
        0 if r["strongly_supported"] else (1 if r["supported"] else 2),
        -abs(r["lift"]),
        -r["n_seen"],
    ))
    combo_rows = combo_rows[:MAX_COMBO_ROWS]

    # Evidence: precedents sharing ≥ 2 signature factors, split by
    # disposition.  Ranked by (# shared factors ↓, opened_at ↓).
    def _overlap(row: Dict[str, Any]) -> int:
        return len(query_sig_set & row["signature_set"])

    cleared_prec = [c for c in corpus if c["disposition"] == "cleared"
                    and _overlap(c) >= 2]
    sar_prec = [c for c in corpus if c["disposition"] == "sar_filed"
                and _overlap(c) >= 2]
    cleared_prec.sort(key=lambda c: (-_overlap(c), -(c["opened_at"] or 0.0)))
    sar_prec.sort(key=lambda c: (-_overlap(c), -(c["opened_at"] or 0.0)))

    def _precedent_dict(row: Dict[str, Any]) -> Dict[str, Any]:
        overlap = sorted(query_sig_set & row["signature_set"])
        return {
            "id": row["id"],
            "account_id": row["account_id"],
            "display_name": row["display_name"],
            "band": row["band"],
            "priority": row["priority"],
            "typology_code": row["typology_code"],
            "disposition": row["disposition"],
            "signature": row["signature"],
            "shared_factors": overlap,
            "risk_score": round(row["risk_score"], 1),
            "opened_at_iso": _iso(row["opened_at"]),
            "closed_at_iso": _iso(row["closed_at"]),
            "summary": row["summary"],
        }

    cleared_evidence = [_precedent_dict(r) for r in cleared_prec[:MAX_EVIDENCE_PER_SIDE]]
    sar_evidence     = [_precedent_dict(r) for r in sar_prec[:MAX_EVIDENCE_PER_SIDE]]

    query_top_factors = [
        {
            "name": f.get("name"),
            "label": DETECTOR_LABEL.get(str(f.get("name") or ""),
                                        str(f.get("name") or "")),
            "points": round(float(f.get("points") or 0.0), 2),
            "weight": float(f.get("weight") or 0.0),
        }
        for f in sorted(
            (snap.get("factors") or []),
            key=lambda f: -float(f.get("points") or 0.0),
        ) if float(f.get("points") or 0.0) > 0.0
    ][:6]

    return {
        "engine": ENGINE_VERSION,
        "query": {
            "case_id": case_id,
            "account_id": full.get("account_id") or "",
            "display_name": full.get("display_name") or "",
            "band": full.get("band") or "",
            "priority": full.get("priority") or "",
            "risk_score": round(float(full.get("risk_score") or 0.0), 1),
            "status": full.get("status"),
            "typology_code": full.get("typology_code"),
            "typology_confidence": full.get("typology_confidence"),
            "signature": query_signature,
            "signature_labels": [DETECTOR_LABEL.get(f, f)
                                 for f in query_signature],
            "top_factors": query_top_factors,
            "summary": full.get("summary") or "",
            "has_sanctions": has_sanctions,
            "opened_at_iso": _iso(full.get("opened_at")),
        },
        "corpus": {
            "closed_total": cleared_all + sar_all,
            "cleared_total": cleared_all,
            "sar_total": sar_all,
            "p_clear_prior": round(p_prior, 4),
        },
        "score": {
            "raw_sum": round(weighted_sum, 4),
            "raw_s": round(raw_s, 4),
            "s": round(s, 4),
            "suppression": round(suppression, 4),
            "scored_combos": scored_combos,
            "strongly_supported_combos": len(supported_lifts),
            "max_supported_lift": (round(max(supported_lifts), 4)
                                   if supported_lifts else None),
            "sanctions_veto_applied": (has_sanctions and s > SANCTIONS_S_CEILING),
        },
        "verdict": {
            "code": verdict_code,
            "label": verdict_label,
            "accent": accent,
            "tone": tone,
            "reason": verdict_reason,
        },
        "combos": combo_rows,
        "evidence": {
            "cleared": cleared_evidence,
            "sar_filed": sar_evidence,
        },
        "rules": get_rules(),
    }


# ---------------------------------------------------------------------------
# Public: portfolio-wide profile (used by /aml/triage/profile).
# ---------------------------------------------------------------------------


def corpus_summary() -> Dict[str, Any]:
    """Portfolio-wide suppression profile.

    Returns the base clearance rate, per-detector clearance stats, the
    9×9 factor-pair suppression matrix (both cells' clearance rate +
    support), and the top-N most noise-heavy and most signal-heavy
    combos.  Everything the /triage surface needs to paint the
    portfolio view before an analyst picks a query case.
    """
    corpus = _load_closed_corpus()
    cleared_all, sar_all, p_prior = _prior_from_corpus(corpus)
    total_terminal = cleared_all + sar_all

    # Per-detector single-factor stats.
    per_factor: List[Dict[str, Any]] = []
    for name in DETECTORS:
        n_c, n_s = _tally_combo(corpus, (name,))
        n_seen = n_c + n_s
        p_c = _posterior_clear(n_c, n_s)
        lift = _log_lift(p_c, p_prior)
        per_factor.append({
            "name": name,
            "label": DETECTOR_LABEL[name],
            "n_seen": n_seen,
            "n_cleared": n_c,
            "n_sar": n_s,
            "p_clear": round(p_c, 4),
            "lift": round(lift, 4),
            "supported": n_seen >= MIN_SUPPORT_ANY,
            "strongly_supported": n_seen >= MIN_SUPPORT_STRONG,
        })

    # 9×9 co-occurrence factor-pair matrix.  Symmetric — we compute
    # the upper triangle and mirror into the lower.  Diagonals are the
    # singleton stats (kept so the matrix reads as a single, coherent
    # heatmap).  Every cell carries its clearance rate + support
    # counts so the surface can render (rate) with hover-detail (n).
    matrix: List[List[Dict[str, Any]]] = []
    for a in DETECTORS:
        row: List[Dict[str, Any]] = []
        for b in DETECTORS:
            if a == b:
                n_c, n_s = _tally_combo(corpus, (a,))
            else:
                combo = (a, b) if a < b else (b, a)
                n_c, n_s = _tally_combo(corpus, combo)
            n_seen = n_c + n_s
            p_c = _posterior_clear(n_c, n_s) if n_seen > 0 else p_prior
            lift = _log_lift(p_c, p_prior) if n_seen > 0 else 0.0
            row.append({
                "a": a,
                "b": b,
                "n_seen": n_seen,
                "n_cleared": n_c,
                "n_sar": n_s,
                "p_clear": round(p_c, 4),
                "lift": round(lift, 4),
                "supported": n_seen >= MIN_SUPPORT_ANY,
            })
        matrix.append(row)

    # Top combos, both directions.  Only *pairs* — singletons are the
    # per-factor table's territory.  Only combos with n_seen ≥
    # MIN_SUPPORT_ANY reach the leaderboard.
    pair_rows: List[Dict[str, Any]] = []
    for a, b in itertools.combinations(DETECTORS, 2):
        n_c, n_s = _tally_combo(corpus, (a, b))
        n_seen = n_c + n_s
        if n_seen < MIN_SUPPORT_ANY:
            continue
        p_c = _posterior_clear(n_c, n_s)
        lift = _log_lift(p_c, p_prior)
        pair_rows.append({
            "combo": [a, b],
            "labels": [DETECTOR_LABEL[a], DETECTOR_LABEL[b]],
            "key": _combo_key((a, b)),
            "n_seen": n_seen,
            "n_cleared": n_c,
            "n_sar": n_s,
            "p_clear": round(p_c, 4),
            "lift": round(lift, 4),
            "strongly_supported": n_seen >= MIN_SUPPORT_STRONG,
        })

    top_noise = sorted(pair_rows, key=lambda r: -r["lift"])[:PROFILE_TOP_COMBOS]
    top_signal = sorted(pair_rows, key=lambda r: r["lift"])[:PROFILE_TOP_COMBOS]

    return {
        "engine": ENGINE_VERSION,
        "corpus": {
            "closed_total": total_terminal,
            "cleared_total": cleared_all,
            "sar_total": sar_all,
            "p_clear_prior": round(p_prior, 4),
        },
        "per_factor": per_factor,
        "matrix": matrix,
        "detectors": list(DETECTORS),
        "detector_labels": {k: v for k, v in DETECTOR_LABEL.items()},
        "top_noise_combos": top_noise,
        "top_signal_combos": top_signal,
    }


# ---------------------------------------------------------------------------
# Public: query candidates.
# ---------------------------------------------------------------------------


def candidates(limit: int = 100, include_closed: bool = False) -> List[Dict[str, Any]]:
    """Cases eligible as triage queries.

    By default only open/review/escalated — the ones an analyst is
    actually deciding on.  ``include_closed`` folds terminal cases
    into the list so an auditor can re-run triage after the fact.
    """
    rows = case_store.list_cases(
        limit=limit, include_closed=include_closed,
    ).get("cases", [])
    out: List[Dict[str, Any]] = []
    for r in rows:
        cid = r.get("id")
        if not cid:
            continue
        if not include_closed and r.get("status") in ("cleared", "sar_filed"):
            continue
        full = case_store.get_case(cid, with_events=False)
        if not full:
            continue
        snap = full.get("snapshot") or {}
        signature = _signature_from_snapshot(snap)
        if not signature:
            continue
        out.append({
            "id": cid,
            "account_id": full.get("account_id") or "",
            "display_name": full.get("display_name") or "",
            "band": full.get("band") or "",
            "priority": full.get("priority") or "",
            "status": full.get("status"),
            "typology_code": full.get("typology_code"),
            "typology_confidence": full.get("typology_confidence"),
            "risk_score": round(float(full.get("risk_score") or 0.0), 1),
            "signature": signature,
            "signature_labels": [DETECTOR_LABEL.get(f, f) for f in signature],
            "summary": full.get("summary") or "",
            "opened_at_iso": _iso(full.get("opened_at")),
            "has_sanctions": "sanctions_hit" in signature,
        })
    return out


# ---------------------------------------------------------------------------
# Sample-seed: FP-rich supplementary corpus.
# ---------------------------------------------------------------------------


# Every family here is a synthetic (factor combo, disposition, count)
# triple.  The intent is to give the miner enough evidence per combo
# to cross the MIN_SUPPORT_STRONG threshold so the /triage demo runs
# with visible lifts.  Factor points are set to values within the
# saturation curve of each detector so the miner's signature picks
# them up as top-K.  Combos are chosen to cover both the "cleared-
# heavy" (round_amount alone, fan_in alone) and "sar-heavy"
# (structuring + sanctions_hit, round_trip + high_risk_geo) ends of
# the spectrum.
_TRIAGE_SEED_FAMILIES: Tuple[Dict[str, Any], ...] = (
    {"family": "TRG-FP-round_amount-alone",
     "factors": [("round_amount", 12.0)],
     "band": "low",
     "cleared": 7, "sar": 0, "typology_code": None},
    {"family": "TRG-FP-fan_in-alone",
     "factors": [("fan_in", 14.0)],
     "band": "low",
     "cleared": 6, "sar": 0, "typology_code": None},
    {"family": "TRG-FP-round_amount-fan_in",
     "factors": [("round_amount", 14.0), ("fan_in", 12.0)],
     "band": "low",
     "cleared": 8, "sar": 1, "typology_code": None},
    {"family": "TRG-FP-velocity-high_risk_geo",
     "factors": [("velocity_spike", 20.0), ("high_risk_geo", 14.0)],
     "band": "medium",
     "cleared": 5, "sar": 1, "typology_code": None},
    {"family": "TRG-FP-round_amount-velocity",
     "factors": [("round_amount", 16.0), ("velocity_spike", 22.0)],
     "band": "medium",
     "cleared": 5, "sar": 1, "typology_code": None},
    {"family": "TRG-SIG-structuring-sanctions",
     "factors": [("structuring", 60.0), ("sanctions_hit", 55.0)],
     "band": "critical",
     "cleared": 0, "sar": 6, "typology_code": "SANCEV"},
    {"family": "TRG-SIG-round_trip-high_risk_geo",
     "factors": [("round_trip", 55.0), ("high_risk_geo", 42.0)],
     "band": "critical",
     "cleared": 1, "sar": 5, "typology_code": "LAYER"},
    {"family": "TRG-SIG-structuring-velocity",
     "factors": [("structuring", 58.0), ("velocity_spike", 48.0)],
     "band": "high",
     "cleared": 1, "sar": 5, "typology_code": "SMURF"},
    {"family": "TRG-SIG-adverse_media-sanctions",
     "factors": [("adverse_media", 55.0), ("sanctions_hit", 60.0)],
     "band": "critical",
     "cleared": 0, "sar": 5, "typology_code": "SANCEV"},
    {"family": "TRG-MID-fan_out-round_trip",
     "factors": [("fan_out", 25.0), ("round_trip", 32.0)],
     "band": "high",
     "cleared": 3, "sar": 4, "typology_code": "MULE"},
    {"family": "TRG-MID-fan_in-fan_out",
     "factors": [("fan_in", 30.0), ("fan_out", 30.0)],
     "band": "medium",
     "cleared": 4, "sar": 3, "typology_code": "MULE"},
    {"family": "TRG-FP-adverse_media-alone",
     "factors": [("adverse_media", 16.0)],
     "band": "low",
     "cleared": 5, "sar": 0, "typology_code": None},
)


def _seed_report(
    account_id: str,
    display_name: str,
    band: str,
    factors: List[Tuple[str, float]],
    typology_code: Optional[str],
) -> Dict[str, Any]:
    """Assemble a minimal account_report so ``open_case`` accepts it.

    We inline typology so ``open_case`` doesn't re-classify — that
    keeps the seeded case's snapshot deterministic (no dependency
    on the typology engine's tunables at seed time).
    """
    risk_score = min(96.0, sum(pts for _, pts in factors))
    fired = [
        {
            "name": name,
            "points": pts,
            "weight": pts,
            "detail": f"seeded for triage: {DETECTOR_LABEL.get(name, name)}",
            "evidence": [],
        }
        for name, pts in factors
    ]
    typologies: List[Dict[str, Any]] = []
    if typology_code:
        typologies = [{
            "code": typology_code,
            "name": {
                "SMURF": "Smurfing / Structuring",
                "LAYER": "Layering",
                "MULE":  "Mule Network",
                "SANCEV": "Sanctions Evasion",
                "TBML": "Trade-Based ML",
                "INTEG": "Integration",
            }.get(typology_code, typology_code),
            "confidence": 0.72,
            "severity_floor": {
                "SANCEV": "critical",
                "LAYER": "high",
                "SMURF": "high",
            }.get(typology_code, "medium"),
            "evidence": [],
            "narrative": "Seeded triage precedent — synthesised for FP mining demo.",
            "recommended_action": "Escalate for L2 review.",
            "contributing_factors": [n for n, _ in factors],
            "icon": "◆",
            "accent": "#f43f5e",
            "summary": "Seeded typology stamp for triage demo.",
        }]
    return {
        "account_id": account_id,
        "display_name": display_name,
        "risk_score": risk_score,
        "band": band,
        "factors": fired,
        "edges": [],
        "counterparty_count": 4,
        "inbound_total": 100000.0,
        "outbound_total": 80000.0,
        "sanctions_hits": [],
        "typologies": typologies,
    }


def seed_sample_cases(*, force: bool = False) -> Dict[str, Any]:
    """Populate the case store with the triage FP-rich supplementary
    corpus.  Skips if the store already carries ≥ 20 terminal cases
    (which — combined with the precedent seed — gives the miner more
    than enough per-combo support) unless ``force`` is set.

    Each seeded case is directly transitioned to its terminal
    disposition and back-dated so the mining reads a realistic
    "closed-in-the-past" distribution.
    """
    existing = case_store.stats()
    terminal_existing = (
        existing["by_status"].get("sar_filed", 0)
        + existing["by_status"].get("cleared", 0)
    )
    if not force and terminal_existing >= 20:
        return {
            "seeded": 0,
            "reason": "corpus already carries ≥ 20 terminal cases",
            "terminal_count": terminal_existing,
        }

    now = datetime.now(timezone.utc).timestamp()
    seeded = 0
    for fam in _TRIAGE_SEED_FAMILIES:
        for disposition, count in (("cleared", fam["cleared"]),
                                   ("sar_filed", fam["sar"])):
            for i in range(count):
                aid = f"{fam['family']}-{disposition[:1].upper()}-{i+1:02d}"
                display = f"{fam['family']} #{i+1}"
                report = _seed_report(
                    account_id=aid,
                    display_name=display,
                    band=fam["band"],
                    factors=fam["factors"],
                    typology_code=fam["typology_code"],
                )
                try:
                    case = case_store.open_case(
                        report,
                        opened_by="TRIAGE-SEED",
                        note=f"Seeded from {fam['family']} for /triage demo.",
                    )
                except Exception:
                    continue
                seeded += 1
                days_ago = 3 + (i + 1) * 2 + hash(fam["family"]) % 21
                opened_at = now - days_ago * 86400.0
                resolution_h = 6.0 + (i * 8.0) + (hash(aid) % 32)
                closed_at = opened_at + resolution_h * 3600.0
                _stamp_disposition(case["id"], disposition,
                                   opened_at=opened_at, closed_at=closed_at)
    return {
        "seeded": seeded,
        "families": [f["family"] for f in _TRIAGE_SEED_FAMILIES],
        "terminal_count_after": terminal_existing + seeded,
    }


def _stamp_disposition(
    case_id: str,
    disposition: str,
    *,
    opened_at: float,
    closed_at: float,
) -> None:
    """Wind the case through open→review→terminal and back-date the
    opened/closed timestamps so the miner reads it as a real
    closed-in-the-past precedent.  Mirrors precedent._stamp_disposition
    intentionally — same shape, same guarantees, own function so a
    change to one doesn't accidentally couple both engines.
    """
    if disposition not in ("cleared", "sar_filed"):
        return
    try:
        case_store.transition(case_id, to_status="review",
                              actor="TRIAGE-SEED", note="Seed transition")
        case_store.transition(case_id, to_status=disposition,
                              actor="TRIAGE-SEED", note="Seed disposition")
    except Exception:
        return
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
# Public: auditor-facing rules dump.
# ---------------------------------------------------------------------------


def get_rules() -> Dict[str, Any]:
    """Every constant driving the engine, in one place."""
    return {
        "engine": ENGINE_VERSION,
        "constants": {
            "signature_top_k": SIGNATURE_TOP_K,
            "laplace_alpha": LAPLACE_ALPHA,
            "min_support_strong": MIN_SUPPORT_STRONG,
            "min_support_any": MIN_SUPPORT_ANY,
            "sanctions_s_ceiling": SANCTIONS_S_CEILING,
            "s_suppress_high": S_SUPPRESS_HIGH,
            "s_suppress_light": S_SUPPRESS_LIGHT,
            "s_elevate_review": S_ELEVATE_REVIEW,
            "s_escalate": S_ESCALATE,
            "max_lift_strong_min": MAX_LIFT_STRONG_MIN,
            "max_evidence_per_side": MAX_EVIDENCE_PER_SIDE,
        },
        "detectors": [
            {"name": n, "label": DETECTOR_LABEL[n]} for n in DETECTORS
        ],
        "verdict_ladder": [
            {"code": code, "label": label, "accent": accent, "tone": tone}
            for code, label, accent, tone in _VERDICT_META
        ],
    }


# ---------------------------------------------------------------------------
# Markdown export — the pasteable triage memo.
# ---------------------------------------------------------------------------


def to_markdown(report: Dict[str, Any]) -> str:
    q = report["query"]
    v = report["verdict"]
    c = report["corpus"]
    s = report["score"]
    lines: List[str] = []
    lines.append(f"# Triage memo — {q['case_id']}")
    lines.append("")
    lines.append(
        f"**Query**: {q['display_name'] or q['account_id']} "
        f"(band: {q['band']}, priority: {q['priority']})"
    )
    if q.get("typology_code"):
        lines.append(f"**Typology**: {q['typology_code']}")
    if q.get("summary"):
        lines.append(f"**Summary**: {q['summary']}")
    lines.append("")
    lines.append(f"## Verdict — {v['label']}")
    lines.append("")
    lines.append(v["reason"])
    lines.append("")
    lines.append("## Aggregate")
    lines.append("")
    lines.append(
        f"- Corpus scanned: {c['closed_total']} closed case(s) "
        f"({c['cleared_total']} cleared · {c['sar_total']} SAR-filed)."
    )
    lines.append(
        f"- Portfolio prior clearance rate: {c['p_clear_prior'] * 100:.1f}%."
    )
    lines.append(
        f"- Aggregate log-lift S = {s['s']:+.3f}; "
        f"suppression score = {s['suppression'] * 100:.1f}%."
    )
    lines.append(
        f"- Scored combos: {s['scored_combos']} "
        f"(strongly supported: {s['strongly_supported_combos']})."
    )
    if s.get("sanctions_veto_applied"):
        lines.append(
            f"- **Sanctions veto applied** — a sanctions-touching "
            f"signature is capped at S ≤ {SANCTIONS_S_CEILING}; "
            "suppression is disallowed."
        )
    lines.append("")
    lines.append("## Query signature")
    lines.append("")
    for label in q["signature_labels"]:
        lines.append(f"- {label}")
    lines.append("")
    if report["combos"]:
        lines.append("## Top scored combos")
        lines.append("")
        lines.append("| Combo | Lift | Cleared / SAR | Support |")
        lines.append("|---|---:|:---:|---:|")
        for row in report["combos"][:10]:
            labels = " + ".join(
                DETECTOR_LABEL.get(f, f) for f in row["combo"]
            )
            lines.append(
                f"| {labels} | {row['lift']:+.2f} | "
                f"{row['n_cleared']} / {row['n_sar']} | {row['n_seen']} |"
            )
        lines.append("")
    if report["evidence"]["cleared"]:
        lines.append("## Cleared precedents (supporting suppression)")
        lines.append("")
        for e in report["evidence"]["cleared"]:
            shared = ", ".join(DETECTOR_LABEL.get(f, f)
                               for f in e["shared_factors"])
            lines.append(
                f"- `{e['id']}` — {e['display_name'] or e['account_id']} "
                f"({e['band']}) — shared: {shared}"
            )
        lines.append("")
    if report["evidence"]["sar_filed"]:
        lines.append("## SAR precedents (counter-evidence)")
        lines.append("")
        for e in report["evidence"]["sar_filed"]:
            shared = ", ".join(DETECTOR_LABEL.get(f, f)
                               for f in e["shared_factors"])
            lines.append(
                f"- `{e['id']}` — {e['display_name'] or e['account_id']} "
                f"({e['band']}) — shared: {shared}"
            )
        lines.append("")
    lines.append(f"_Engine: {ENGINE_VERSION} — deterministic, "
                 f"reproducible from the cited case IDs._")
    return "\n".join(lines)


__all__ = [
    "ENGINE_VERSION",
    "DETECTORS",
    "DETECTOR_LABEL",
    "SIGNATURE_TOP_K",
    "LAPLACE_ALPHA",
    "MIN_SUPPORT_STRONG",
    "MIN_SUPPORT_ANY",
    "SANCTIONS_S_CEILING",
    "S_SUPPRESS_HIGH",
    "S_SUPPRESS_LIGHT",
    "S_ELEVATE_REVIEW",
    "S_ESCALATE",
    "MAX_LIFT_STRONG_MIN",
    "get_rules",
    "corpus_summary",
    "candidates",
    "triage_for_case",
    "seed_sample_cases",
    "to_markdown",
]
