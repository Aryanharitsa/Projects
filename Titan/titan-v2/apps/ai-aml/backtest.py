"""TITAN AML model-validation / backtest engine.

Every prior surface *measures* one batch at a time. None of them answer
the question a model-risk-management reviewer (SR 11-7 / FFIEC) asks
first: **is the detection model any good?** A scorer that flags everyone
has perfect recall and is useless; one that flags no-one is "accurate"
on a low base-rate book and equally useless. You only know by replaying
the engine against a *labelled* set of confirmed outcomes and reading
the trade-off.

This module does exactly that, deterministically and with no ML deps:

1. Score the labelled transaction set with `risk.score_accounts`
   (honouring a candidate `weights` override — so a tuning hypothesis
   from the what-if simulator can be validated, not just admired).
2. Sweep the alert threshold 0..100 and, at each cut, compute the full
   confusion matrix + precision / recall / specificity / F1 / Fβ /
   alert-rate. Compliance teams weight recall over precision (a missed
   launderer costs far more than an extra review), so the default
   `beta = 2.0` and the recommended operating point maximises Fβ.
3. Rank-based ROC AUC (Mann-Whitney) and average precision — single
   numbers for "how separable are good from bad by score?".
4. **Per-detector discrimination**: each detector's own single-feature
   AUC over the positive vs negative populations. This is the part that
   pays for itself — it tells you which rules carry the signal and which
   are noise you can down-weight, closing the loop with the what-if
   simulator.

Pure function of (transactions, labels, weights): same input → same
report, every time. That is what makes it admissible as model evidence.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

import risk as risk_engine

ENGINE_VERSION = "titan-backtest/1.0.0"

# The production decision that actually matters is "do we open a case?".
# The case workflow promotes at medium priority and above — alert_score
# >= 30 — so 30 is the implicit operating point the backtest benchmarks
# against (the "high" band at 60 is a display tier, not the alert cut).
DEFAULT_OPERATING_THRESHOLD = 30.0
DEFAULT_BETA = 2.0

# Single-feature AUC tiers for the per-detector verdict.
_STRENGTH_TIERS: Tuple[Tuple[float, str], ...] = (
    (0.78, "strong"),
    (0.66, "moderate"),
    (0.56, "weak"),
    (0.0, "noise"),
)

DETECTOR_LABELS: Dict[str, str] = {
    "structuring": "Structuring",
    "velocity_spike": "Velocity spike",
    "round_trip": "Round-trip cycle",
    "sanctions_hit": "Sanctions hit",
    "adverse_media": "Adverse media",
    "fan_in": "Fan-in",
    "fan_out": "Fan-out",
    "high_risk_geo": "High-risk geo",
    "round_amount": "Round amounts",
}


# ---------------------------------------------------------------------------
# Record assembly
# ---------------------------------------------------------------------------


class _Record:
    __slots__ = ("account_id", "display_name", "score", "label", "intensities")

    def __init__(
        self,
        account_id: str,
        display_name: str,
        score: float,
        label: int,
        intensities: Dict[str, float],
    ) -> None:
        self.account_id = account_id
        self.display_name = display_name
        self.score = score
        self.label = label
        self.intensities = intensities


def _normalize_labels(labels: Any) -> Tuple[Set[str], Optional[Set[str]]]:
    """Accept either a list of positive ids, or a dict of id -> truthy.

    Returns ``(positives, explicit_negatives_or_None)``. When labels is a
    dict, ids mapped to a falsy value become *explicit negatives* and
    everything unlabelled is dropped from the scored population so the
    evaluation only covers adjudicated accounts. A plain list means
    "these are the known-bad; treat every other scored account as good"
    — the realistic confirmed-SAR setup.
    """

    if isinstance(labels, dict):
        positives = {str(k) for k, v in labels.items() if _truthy(v)}
        negatives = {str(k) for k, v in labels.items() if not _truthy(v)}
        return positives, negatives
    positives = {str(x) for x in (labels or [])}
    return positives, None


def _truthy(v: Any) -> bool:
    if isinstance(v, str):
        return v.strip().lower() in {"1", "true", "yes", "y", "positive", "suspicious", "bad"}
    return bool(v)


def _intensities(report: Dict[str, Any]) -> Dict[str, float]:
    out: Dict[str, float] = {}
    for f in report.get("factors", []):
        weight = f.get("weight") or 0.0
        points = f.get("points") or 0.0
        out[f.get("name", "")] = (points / weight) if weight else 0.0
    return out


# ---------------------------------------------------------------------------
# Statistics primitives (all deterministic, stdlib only)
# ---------------------------------------------------------------------------


def _auc(pos: Sequence[float], neg: Sequence[float]) -> float:
    """Rank-based AUROC via the Mann-Whitney U statistic, ties at 0.5.

    AUC = P(score(random positive) > score(random negative)). 0.5 is a
    coin flip; 1.0 is perfect separation. Computed exactly over all
    pos×neg pairs (the sets are small here), so no sampling, no seed.
    """

    if not pos or not neg:
        return 0.5
    wins = 0.0
    for p in pos:
        for n in neg:
            if p > n:
                wins += 1.0
            elif p == n:
                wins += 0.5
    return wins / (len(pos) * len(neg))


def _confusion(records: List[_Record], threshold: float, beta: float) -> Dict[str, Any]:
    tp = fp = fn = tn = 0
    for r in records:
        predicted = r.score >= threshold
        if predicted and r.label:
            tp += 1
        elif predicted and not r.label:
            fp += 1
        elif not predicted and r.label:
            fn += 1
        else:
            tn += 1

    total = tp + fp + fn + tn
    alerts = tp + fp
    precision = tp / alerts if alerts else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    specificity = tn / (tn + fp) if (tn + fp) else 0.0
    fpr = fp / (fp + tn) if (fp + tn) else 0.0
    b2 = beta * beta
    denom = b2 * precision + recall
    fbeta = (1 + b2) * precision * recall / denom if denom else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    accuracy = (tp + tn) / total if total else 0.0
    balanced = (recall + specificity) / 2.0
    return {
        "threshold": round(threshold, 2),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "alerts": alerts,
        "alert_rate": round(alerts / total, 4) if total else 0.0,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "specificity": round(specificity, 4),
        "fpr": round(fpr, 4),
        "tpr": round(recall, 4),
        "f1": round(f1, 4),
        "fbeta": round(fbeta, 4),
        "accuracy": round(accuracy, 4),
        "balanced_accuracy": round(balanced, 4),
        "youden_j": round(recall + specificity - 1.0, 4),
    }


def _average_precision(sweep: List[Dict[str, Any]]) -> float:
    """Area under the PR curve, integrated over the threshold sweep.

    The sweep is ascending in threshold (recall *decreasing*); walking it
    from the high-recall end and summing precision × Δrecall gives the
    standard step-wise AP, robust to the curve being non-monotonic.
    """

    ordered = sorted(sweep, key=lambda p: p["recall"])
    ap = 0.0
    prev_recall = 0.0
    for pt in ordered:
        d = pt["recall"] - prev_recall
        if d > 0:
            ap += d * pt["precision"]
        prev_recall = pt["recall"]
    return round(ap, 4)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def backtest(
    transactions: Iterable[Dict[str, Any]],
    labels: Any,
    *,
    weights: Optional[Dict[str, Any]] = None,
    beta: float = DEFAULT_BETA,
    operating_threshold: float = DEFAULT_OPERATING_THRESHOLD,
    sanctions_threshold: float = risk_engine.SANCTIONS_HIT_THRESHOLD,
) -> Dict[str, Any]:
    rows = list(transactions)
    scored = risk_engine.score_accounts(
        rows,
        weights_override=weights,
        sanctions_threshold=sanctions_threshold,
    )
    positives, explicit_neg = _normalize_labels(labels)

    records: List[_Record] = []
    for acct in scored["accounts"]:
        aid = acct["account_id"]
        is_pos = aid in positives
        # Dict-style labels restrict the population to adjudicated ids only.
        if explicit_neg is not None and not is_pos and aid not in explicit_neg:
            continue
        records.append(
            _Record(
                account_id=aid,
                display_name=acct.get("display_name", ""),
                score=float(acct.get("risk_score", 0.0)),
                label=1 if is_pos else 0,
                intensities=_intensities(acct),
            )
        )

    n_pos = sum(1 for r in records if r.label)
    n_neg = len(records) - n_pos
    base_rate = round(n_pos / len(records), 4) if records else 0.0

    beta = max(0.1, float(beta))
    sweep = [_confusion(records, float(t), beta) for t in range(0, 101)]

    pos_scores = [r.score for r in records if r.label]
    neg_scores = [r.score for r in records if not r.label]
    roc_auc = round(_auc(pos_scores, neg_scores), 4)
    average_precision = _average_precision(sweep)

    # Recommended operating point: maximise Fβ. Ties broken toward higher
    # recall, then a lower alert burden, then the lower threshold.
    recommended = max(
        sweep,
        key=lambda p: (p["fbeta"], p["recall"], -p["alert_rate"], -p["threshold"]),
    )
    youden = max(sweep, key=lambda p: (p["youden_j"], -p["threshold"]))
    current = _confusion(records, float(operating_threshold), beta)

    detectors = _detector_discrimination(records)

    rec_thr = recommended["threshold"]
    accounts_out = sorted(
        (
            {
                "account_id": r.account_id,
                "display_name": r.display_name,
                "score": round(r.score, 1),
                "label": r.label,
                "predicted": 1 if r.score >= rec_thr else 0,
                "outcome": _outcome(r.score >= rec_thr, bool(r.label)),
                "intensities": {k: round(v, 3) for k, v in r.intensities.items()},
            }
            for r in records
        ),
        key=lambda a: a["score"],
        reverse=True,
    )

    return {
        "engine": ENGINE_VERSION,
        "labels": {
            "positives": sorted(positives),
            "n_pos": n_pos,
            "n_neg": n_neg,
            "n_total": len(records),
            "base_rate": base_rate,
            "mode": "dict" if explicit_neg is not None else "positive-list",
        },
        "beta": round(beta, 2),
        "operating_threshold": round(float(operating_threshold), 1),
        "effective_weights": scored.get("effective_weights", {}),
        "sanctions_threshold": sanctions_threshold,
        "metrics_at": {
            "current": current,
            "recommended": recommended,
            "youden": youden,
        },
        "roc": {
            "auc": roc_auc,
            "points": [
                {"fpr": p["fpr"], "tpr": p["tpr"], "threshold": p["threshold"]}
                for p in sweep
            ],
        },
        "pr": {
            "average_precision": average_precision,
            "points": [
                {"recall": p["recall"], "precision": p["precision"], "threshold": p["threshold"]}
                for p in sweep
            ],
        },
        "sweep": sweep,
        "detectors": detectors,
        "accounts": accounts_out,
        "verdict": _verdict(roc_auc, recommended, current, detectors),
    }


def _outcome(predicted: bool, label: bool) -> str:
    if predicted and label:
        return "tp"
    if predicted and not label:
        return "fp"
    if not predicted and label:
        return "fn"
    return "tn"


def _detector_discrimination(records: List[_Record]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    pos = [r for r in records if r.label]
    neg = [r for r in records if not r.label]
    for key in risk_engine.DETECTOR_ORDER:
        pv = [r.intensities.get(key, 0.0) for r in pos]
        nv = [r.intensities.get(key, 0.0) for r in neg]
        auc = _auc(pv, nv)
        mean_pos = sum(pv) / len(pv) if pv else 0.0
        mean_neg = sum(nv) / len(nv) if nv else 0.0
        fired_pos = sum(1 for v in pv if v > 0.01)
        fired_neg = sum(1 for v in nv if v > 0.01)
        strength = next(label for cut, label in _STRENGTH_TIERS if auc >= cut)
        out.append(
            {
                "key": key,
                "label": DETECTOR_LABELS.get(key, key),
                "weight": risk_engine.WEIGHTS.get(key, 0.0),
                "auc": round(auc, 4),
                "lift": round(mean_pos - mean_neg, 4),
                "mean_pos": round(mean_pos, 4),
                "mean_neg": round(mean_neg, 4),
                "fired_pos": fired_pos,
                "fired_neg": fired_neg,
                "n_pos": len(pv),
                "n_neg": len(nv),
                "strength": strength,
                "note": _detector_note(strength, auc, fired_neg, len(nv)),
            }
        )
    out.sort(key=lambda d: d["auc"], reverse=True)
    return out


def _detector_note(strength: str, auc: float, fired_neg: int, n_neg: int) -> str:
    if strength == "strong":
        return "Clean separator — carries the model."
    if strength == "moderate":
        return "Useful signal; confirm it is not double-counting a stronger rule."
    if strength == "weak":
        if fired_neg and n_neg and fired_neg / n_neg >= 0.25:
            return "Fires on benign accounts too — a false-positive driver; consider down-weighting."
        return "Marginal separation; low contribution to the verdict."
    return "Near-random on this set — likely noise. Down-weight or gate behind another rule."


def _verdict(
    roc_auc: float,
    recommended: Dict[str, Any],
    current: Dict[str, Any],
    detectors: List[Dict[str, Any]],
) -> Dict[str, Any]:
    if roc_auc >= 0.85:
        grade, headline = "strong", "Model separates suspicious from benign well."
    elif roc_auc >= 0.7:
        grade, headline = "fair", "Model has real signal but leaves money on the table."
    elif roc_auc >= 0.6:
        grade, headline = "marginal", "Model is barely better than the base rate."
    else:
        grade, headline = "poor", "Model is close to random on this labelled set."

    notes: List[str] = []
    if recommended["threshold"] < current["threshold"] and recommended["recall"] > current["recall"]:
        notes.append(
            f"Lowering the alert cut to {recommended['threshold']:.0f} lifts recall "
            f"from {current['recall']:.0%} to {recommended['recall']:.0%} "
            f"(alert rate {current['alert_rate']:.0%} → {recommended['alert_rate']:.0%})."
        )
    elif recommended["threshold"] > current["threshold"]:
        notes.append(
            f"Raising the alert cut to {recommended['threshold']:.0f} trims false "
            f"positives while holding {recommended['recall']:.0%} recall."
        )
    weak = [d["label"] for d in detectors if d["strength"] in {"weak", "noise"}]
    if weak:
        notes.append("Low-signal detectors on this set: " + ", ".join(weak) + ".")
    if current["fn"]:
        notes.append(
            f"{current['fn']} known-suspicious account(s) slip under the current cut."
        )
    return {"grade": grade, "headline": headline, "notes": notes}


# ---------------------------------------------------------------------------
# Bundled labelled validation set — one-click demo, fully deterministic.
# A realistic spread: confirmed-bad accounts across five typologies, a
# book of benign retail flows, plus two hard cases (a benign business that
# trips the weak round-amount rule = a false-positive trap, and a subtle
# launderer that scores under the band = a recall miss).
# ---------------------------------------------------------------------------

_SAMPLE_TX: List[Dict[str, Any]] = [
    # --- A1 smurfing: 4 sub-threshold deposits in one day (TP) -----------
    {"account_id": "A1", "counterparty": "M1", "amount": 45000, "timestamp": "2026-04-20T09:00:00Z", "channel": "UPI", "geo": "IN", "subject_name": "Lakshmi Holdings Pvt Ltd", "counterparty_name": "Trident Exports"},
    {"account_id": "A1", "counterparty": "M2", "amount": 47500, "timestamp": "2026-04-20T11:00:00Z", "channel": "UPI", "geo": "IN", "subject_name": "Lakshmi Holdings Pvt Ltd", "counterparty_name": "Sundar Logistics"},
    {"account_id": "A1", "counterparty": "M3", "amount": 49000, "timestamp": "2026-04-20T15:00:00Z", "channel": "UPI", "geo": "IN", "subject_name": "Lakshmi Holdings Pvt Ltd", "counterparty_name": "Meridian Traders"},
    {"account_id": "A1", "counterparty": "M4", "amount": 48500, "timestamp": "2026-04-20T20:00:00Z", "channel": "UPI", "geo": "IN", "subject_name": "Lakshmi Holdings Pvt Ltd", "counterparty_name": "Orbit Supplies"},
    # --- A2 -> B -> C -> A2 layering cycle, all legs large (TP x3) --------
    {"account_id": "A2", "counterparty": "B", "amount": 500000, "timestamp": "2026-04-21T10:00:00Z", "channel": "RTGS", "geo": "IN", "subject_name": "Rohit Mehta Trading", "counterparty_name": "Aurelia Shell Limited"},
    {"account_id": "B", "counterparty": "C", "amount": 480000, "timestamp": "2026-04-21T11:00:00Z", "channel": "RTGS", "geo": "IN", "subject_name": "Aurelia Shell Limited", "counterparty_name": "Crescent Maritime"},
    {"account_id": "C", "counterparty": "A2", "amount": 460000, "timestamp": "2026-04-21T12:00:00Z", "channel": "RTGS", "geo": "IN", "subject_name": "Crescent Maritime", "counterparty_name": "Rohit Mehta Trading"},
    # --- A3 sanctions + high-risk geo (TP) -------------------------------
    {"account_id": "A3", "counterparty": "X", "amount": 120000, "timestamp": "2026-04-22T10:00:00Z", "channel": "SWIFT", "geo": "KP", "subject_name": "Devraj Industries", "counterparty_name": "Pyongyang Horizon"},
    {"account_id": "A3", "counterparty": "X2", "amount": 95000, "timestamp": "2026-04-22T13:00:00Z", "channel": "SWIFT", "geo": "KP", "subject_name": "Devraj Industries", "counterparty_name": "Pyongyang Horizon"},
    # --- A5 TBML: cross-border round-figure SWIFT (TP) -------------------
    {"account_id": "A5", "counterparty": "Q", "amount": 250000, "timestamp": "2026-04-23T08:00:00Z", "channel": "SWIFT", "geo": "RU", "subject_name": "Northern Steel Co", "counterparty_name": "Argentum Horizon GmbH"},
    {"account_id": "A5", "counterparty": "R", "amount": 180000, "timestamp": "2026-04-23T08:30:00Z", "channel": "SWIFT", "geo": "AE", "subject_name": "Northern Steel Co", "counterparty_name": "Golden Oryx Trading"},
    {"account_id": "A5", "counterparty": "S", "amount": 200000, "timestamp": "2026-04-23T09:00:00Z", "channel": "SWIFT", "geo": "IR", "subject_name": "Northern Steel Co", "counterparty_name": "Caspian Freight"},
    # --- MULE high fan-in + fan-out pass-through (TP) --------------------
    {"account_id": "S1", "counterparty": "MULE", "amount": 60000, "timestamp": "2026-04-24T09:00:00Z", "channel": "UPI", "geo": "IN", "counterparty_name": "Quick Pass Services"},
    {"account_id": "S2", "counterparty": "MULE", "amount": 62000, "timestamp": "2026-04-24T09:10:00Z", "channel": "UPI", "geo": "IN", "counterparty_name": "Quick Pass Services"},
    {"account_id": "S3", "counterparty": "MULE", "amount": 58000, "timestamp": "2026-04-24T09:20:00Z", "channel": "UPI", "geo": "IN", "counterparty_name": "Quick Pass Services"},
    {"account_id": "S4", "counterparty": "MULE", "amount": 61000, "timestamp": "2026-04-24T09:30:00Z", "channel": "UPI", "geo": "IN", "counterparty_name": "Quick Pass Services"},
    {"account_id": "S5", "counterparty": "MULE", "amount": 59000, "timestamp": "2026-04-24T09:40:00Z", "channel": "UPI", "geo": "IN", "counterparty_name": "Quick Pass Services"},
    {"account_id": "S6", "counterparty": "MULE", "amount": 57000, "timestamp": "2026-04-24T09:50:00Z", "channel": "UPI", "geo": "IN", "counterparty_name": "Quick Pass Services"},
    {"account_id": "S7", "counterparty": "MULE", "amount": 63000, "timestamp": "2026-04-24T10:00:00Z", "channel": "UPI", "geo": "IN", "counterparty_name": "Quick Pass Services"},
    {"account_id": "S8", "counterparty": "MULE", "amount": 60000, "timestamp": "2026-04-24T10:10:00Z", "channel": "UPI", "geo": "IN", "counterparty_name": "Quick Pass Services"},
    {"account_id": "MULE", "counterparty": "D1", "amount": 58000, "timestamp": "2026-04-24T11:00:00Z", "channel": "UPI", "geo": "IN", "subject_name": "Quick Pass Services", "counterparty_name": "Payout One"},
    {"account_id": "MULE", "counterparty": "D2", "amount": 59000, "timestamp": "2026-04-24T11:05:00Z", "channel": "UPI", "geo": "IN", "subject_name": "Quick Pass Services", "counterparty_name": "Payout Two"},
    {"account_id": "MULE", "counterparty": "D3", "amount": 60000, "timestamp": "2026-04-24T11:10:00Z", "channel": "UPI", "geo": "IN", "subject_name": "Quick Pass Services", "counterparty_name": "Payout Three"},
    {"account_id": "MULE", "counterparty": "D4", "amount": 57000, "timestamp": "2026-04-24T11:15:00Z", "channel": "UPI", "geo": "IN", "subject_name": "Quick Pass Services", "counterparty_name": "Payout Four"},
    {"account_id": "MULE", "counterparty": "D5", "amount": 61000, "timestamp": "2026-04-24T11:20:00Z", "channel": "UPI", "geo": "IN", "subject_name": "Quick Pass Services", "counterparty_name": "Payout Five"},
    {"account_id": "MULE", "counterparty": "D6", "amount": 58000, "timestamp": "2026-04-24T11:25:00Z", "channel": "UPI", "geo": "IN", "subject_name": "Quick Pass Services", "counterparty_name": "Payout Six"},
    {"account_id": "MULE", "counterparty": "D7", "amount": 59000, "timestamp": "2026-04-24T11:30:00Z", "channel": "UPI", "geo": "IN", "subject_name": "Quick Pass Services", "counterparty_name": "Payout Seven"},
    {"account_id": "MULE", "counterparty": "D8", "amount": 60000, "timestamp": "2026-04-24T11:35:00Z", "channel": "UPI", "geo": "IN", "subject_name": "Quick Pass Services", "counterparty_name": "Payout Eight"},
    # --- FN1 subtle launderer: only 2 sub-threshold deposits, under the
    #     STRUCT_MIN_COUNT=3 gate, so the engine scores it low (recall miss)
    {"account_id": "FN1", "counterparty": "Z1", "amount": 46000, "timestamp": "2026-04-25T10:00:00Z", "channel": "UPI", "geo": "IN", "subject_name": "Halcyon Imports", "counterparty_name": "Vendor A"},
    {"account_id": "FN1", "counterparty": "Z2", "amount": 47000, "timestamp": "2026-04-25T18:00:00Z", "channel": "UPI", "geo": "IN", "subject_name": "Halcyon Imports", "counterparty_name": "Vendor B"},
    # --- FP1 benign business: 3 large round-figure payroll runs (the weak
    #     round_amount rule fires, but it is legitimate = false-positive trap)
    {"account_id": "FP1", "counterparty": "PAY", "amount": 300000, "timestamp": "2026-03-01T10:00:00Z", "channel": "RTGS", "geo": "IN", "subject_name": "Sterling Manufacturing", "counterparty_name": "Payroll Bureau"},
    {"account_id": "FP1", "counterparty": "PAY", "amount": 300000, "timestamp": "2026-04-01T10:00:00Z", "channel": "RTGS", "geo": "IN", "subject_name": "Sterling Manufacturing", "counterparty_name": "Payroll Bureau"},
    {"account_id": "FP1", "counterparty": "PAY", "amount": 300000, "timestamp": "2026-05-01T10:00:00Z", "channel": "RTGS", "geo": "IN", "subject_name": "Sterling Manufacturing", "counterparty_name": "Payroll Bureau"},
    # --- Benign retail accounts: ordinary low-value flows (true negatives)
    {"account_id": "N1", "counterparty": "Shop1", "amount": 2500, "timestamp": "2026-04-10T10:00:00Z", "channel": "UPI", "geo": "IN", "subject_name": "Anil Kumar", "counterparty_name": "Grocery Mart"},
    {"account_id": "N1", "counterparty": "Shop2", "amount": 1800, "timestamp": "2026-04-12T14:00:00Z", "channel": "UPI", "geo": "IN", "subject_name": "Anil Kumar", "counterparty_name": "Fuel Stop"},
    {"account_id": "N2", "counterparty": "Shop3", "amount": 8200, "timestamp": "2026-04-11T09:00:00Z", "channel": "UPI", "geo": "IN", "subject_name": "Priya Nair", "counterparty_name": "Pharmacy"},
    {"account_id": "N2", "counterparty": "N1", "amount": 3000, "timestamp": "2026-04-13T19:00:00Z", "channel": "UPI", "geo": "IN", "subject_name": "Priya Nair", "counterparty_name": "Anil Kumar"},
    {"account_id": "N3", "counterparty": "Shop4", "amount": 15000, "timestamp": "2026-04-14T11:00:00Z", "channel": "IMPS", "geo": "IN", "subject_name": "Karthik Rao", "counterparty_name": "Electronics Hub"},
    {"account_id": "N4", "counterparty": "Shop5", "amount": 4200, "timestamp": "2026-04-15T16:00:00Z", "channel": "UPI", "geo": "IN", "subject_name": "Sneha Iyer", "counterparty_name": "Cafe Latte"},
    {"account_id": "N5", "counterparty": "Shop6", "amount": 9800, "timestamp": "2026-04-16T12:00:00Z", "channel": "IMPS", "geo": "IN", "subject_name": "Mohan Das", "counterparty_name": "Apparel Co"},
    {"account_id": "N6", "counterparty": "Shop7", "amount": 6500, "timestamp": "2026-04-17T13:00:00Z", "channel": "UPI", "geo": "IN", "subject_name": "Geeta Verma", "counterparty_name": "Bookstore"},
    {"account_id": "N7", "counterparty": "N3", "amount": 12000, "timestamp": "2026-04-18T10:00:00Z", "channel": "IMPS", "geo": "IN", "subject_name": "Ravi Shankar", "counterparty_name": "Karthik Rao"},
    {"account_id": "N8", "counterparty": "Shop8", "amount": 5400, "timestamp": "2026-04-19T15:00:00Z", "channel": "UPI", "geo": "IN", "subject_name": "Divya Menon", "counterparty_name": "Salon"},
]

# Confirmed-suspicious accounts (the ground truth). FN1 is genuinely bad
# but deliberately under-detected; FP1 is genuinely benign though it trips
# a rule. Everything else scored is a true negative.
_SAMPLE_POSITIVES: List[str] = ["A1", "A2", "B", "C", "A3", "A5", "MULE", "FN1"]


def get_sample() -> Dict[str, Any]:
    """The bundled labelled validation set, for the one-click demo."""

    return {
        "transactions": [dict(t) for t in _SAMPLE_TX],
        "labels": list(_SAMPLE_POSITIVES),
        "note": (
            "Confirmed-bad accounts span five typologies (smurfing, layering, "
            "sanctions, TBML, mule). FN1 is a deliberately under-detected "
            "launderer and FP1 a benign payroll account that trips the weak "
            "round-amount rule — so the confusion matrix and per-detector AUC "
            "are both non-trivial."
        ),
    }
