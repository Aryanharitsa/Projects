"""TITAN AML typology classifier.

Day-30. Layers FATF / Wolfsberg-style money-laundering *typologies* on top
of the eight detectors in ``risk.py``. The detectors answer "what
suspicious patterns are present?". Typologies answer the next question
a compliance analyst always asks: **"…and which playbook does that
add up to?"**

The classifier is deliberately rule-based and deterministic — same
account report → same typology ranking, every time. Each typology
publishes:

* a stable ``code`` (``SMURF``, ``LAYER``, ``TBML``, ``MULE``,
  ``SANCEV``, ``INTEG``) so other surfaces (cases, network, SAR) can
  reference matches without depending on the display name;
* a ``confidence`` ∈ [0, 1] derived as a weighted sum of normalised
  detector intensities and structural bonuses, divided by the maximum
  attainable for that typology so a 1.00 means *every* contributor
  fired at its strongest expected level;
* a ranked list of ``evidence`` chips with the per-contributor share
  of the final confidence — analysts can trace why the playbook
  matched without re-running the engine;
* a ``narrative`` paragraph ready for SAR §3 ("Pattern of activity"),
  and a ``recommended_action`` sentence that pre-fills SAR §4;
* a ``severity_floor`` (``low`` / ``medium`` / ``high`` / ``critical``)
  used to upgrade the case priority when the typology is locked in.

The library lives entirely in this module — no external rules file —
so the auditor surface ``GET /aml/typologies`` is the source of truth
both for the engine and for downstream consumers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------

CONFIDENCE_FLOOR: float = 0.35
"""Below this, a typology is not reported. Keeps the badge surface honest:
weak matches stay out of the SAR narrative and the case sidebar."""

MAX_REPORTED: int = 3
"""Per-account cap. The top-N by confidence are returned; the rest are
discarded so the UI never has to deal with a wall of low-quality matches."""

ENGINE_VERSION: str = "titan-typology/0.1.0"
"""Bumped alongside ``risk_engine.rules_version`` whenever the library
changes shape. Frontend reads this off ``GET /aml/typologies`` to confirm
both sides agree on the definitions."""


# ---------------------------------------------------------------------------
# Severity ordering — typologies can promote the case priority by floor.
# ---------------------------------------------------------------------------

_SEVERITY_RANK: Dict[str, int] = {"low": 0, "medium": 1, "high": 2, "critical": 3}


def _severity_max(a: str, b: str) -> str:
    return a if _SEVERITY_RANK.get(a, 0) >= _SEVERITY_RANK.get(b, 0) else b


# ---------------------------------------------------------------------------
# Domain types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Contributor:
    """One driver of a typology's confidence — either a detector or a
    derived structural bonus. The label is what the UI chip shows.
    """

    key: str
    label: str
    kind: str  # "detector" | "structure" | "sanctions"
    weight: float


@dataclass(frozen=True)
class TypologyDef:
    """Declarative typology definition.

    All scoring is sum( contributor.weight × contributor.signal ) for
    contributors that fired, divided by sum(contributor.weight) — i.e.
    the confidence is the *fraction of expected evidence that actually
    showed up*. A perfect match scores 1.00.
    """

    code: str
    name: str
    summary: str
    icon: str  # short unicode glyph the frontend renders inside the badge
    accent: str  # hex hue used by the chip / ring on the frontend
    contributors: Tuple[_Contributor, ...]
    severity_floor: str
    narrative_template: str
    recommended_action: str

    @property
    def max_score(self) -> float:
        return sum(c.weight for c in self.contributors)


@dataclass
class TypologyMatch:
    code: str
    name: str
    summary: str
    icon: str
    accent: str
    confidence: float
    severity_floor: str
    evidence: List[Dict[str, Any]] = field(default_factory=list)
    narrative: str = ""
    recommended_action: str = ""
    contributing_factor_names: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "name": self.name,
            "summary": self.summary,
            "icon": self.icon,
            "accent": self.accent,
            "confidence": round(self.confidence, 3),
            "severity_floor": self.severity_floor,
            "evidence": self.evidence,
            "narrative": self.narrative,
            "recommended_action": self.recommended_action,
            "contributing_factors": self.contributing_factor_names,
        }


# ---------------------------------------------------------------------------
# Library — six typologies covering the most-cited FATF / Wolfsberg patterns.
# ---------------------------------------------------------------------------


_LIBRARY: Tuple[TypologyDef, ...] = (
    TypologyDef(
        code="SMURF",
        name="Smurfing / Structuring",
        summary=(
            "Many sub-threshold deposits aggregated into a single account "
            "to evade currency-transaction reporting."
        ),
        icon="◐",
        accent="#f59e0b",  # amber-500
        contributors=(
            _Contributor("structuring", "Sub-threshold deposit clusters", "detector", 1.00),
            _Contributor("fan_in", "Many distinct senders", "detector", 0.55),
            _Contributor("round_amount", "Repeated round-number values", "detector", 0.35),
            _Contributor("velocity_spike", "Burst in inbound velocity", "detector", 0.25),
        ),
        severity_floor="high",
        narrative_template=(
            "Subject {account_id} moved {flow_total} across "
            "{counterparty_count} distinct counterparties using "
            "sub-threshold transfer clusters consistent with "
            "currency-transaction-report (CTR) evasion. The largest "
            "grouping shows {struct_detail}."
        ),
        recommended_action=(
            "Freeze inbound aggregation pending source-of-funds review for "
            "each contributing counterparty; escalate to L2 if structured "
            "deposits resume within seven days of notice."
        ),
    ),
    TypologyDef(
        code="LAYER",
        name="Layering",
        summary=(
            "Sequential transfers through intermediate accounts intended to "
            "obscure the audit trail of origin funds."
        ),
        icon="↻",
        accent="#a855f7",  # violet-500
        contributors=(
            _Contributor("round_trip", "Closed flow cycle detected", "detector", 1.00),
            _Contributor("velocity_spike", "Coordinated transfer burst", "detector", 0.40),
            _Contributor("round_amount", "Identical round-leg amounts", "detector", 0.30),
            _Contributor("high_risk_geo", "Cross-border hops", "detector", 0.25),
        ),
        severity_floor="high",
        narrative_template=(
            "Subject {account_id} sits inside a closed flow loop: "
            "{cycle_detail}. The pattern is consistent with layering — "
            "value re-enters the subject account through intermediates "
            "rather than terminating in a destination of record."
        ),
        recommended_action=(
            "Trace each cycle leg back to its origin counterparty, request "
            "underlying invoice / trade documentation, and treat downstream "
            "transfers as proceeds until the loop is unwound."
        ),
    ),
    TypologyDef(
        code="TBML",
        name="Trade-Based ML",
        summary=(
            "Cross-border value transfers wrapped as trade flows; "
            "diversity of counterparties + elevated geographies + "
            "round-figure consideration."
        ),
        icon="◈",
        accent="#06b6d4",  # cyan-500
        contributors=(
            _Contributor("high_risk_geo", "FATF-grey counterparty geographies", "detector", 1.00),
            _Contributor("fan_out", "Many distinct cross-border recipients", "detector", 0.55),
            _Contributor("round_amount", "Round-figure invoice amounts", "detector", 0.40),
            _Contributor("sanctions_hit", "Sanctioned counterparty exposure", "detector", 0.35),
        ),
        severity_floor="high",
        narrative_template=(
            "Subject {account_id} dispatched {outbound_total} to "
            "{counterparty_count} counterparties spanning elevated-risk "
            "geographies ({geo_detail}). Round-figure consideration and "
            "absence of supporting documentation are consistent with "
            "trade-based money laundering."
        ),
        recommended_action=(
            "Request matching commercial invoices, shipping documents, and "
            "letter-of-credit references; verify quantities against "
            "customs-declared values before releasing further wires."
        ),
    ),
    TypologyDef(
        code="MULE",
        name="Mule Network",
        summary=(
            "Pass-through accounts that receive from many senders and "
            "immediately forward to many recipients with little retention."
        ),
        icon="◫",
        accent="#22c55e",  # emerald-500
        contributors=(
            _Contributor("fan_in", "Many distinct senders", "detector", 0.55),
            _Contributor("fan_out", "Many distinct recipients", "detector", 0.55),
            _Contributor("velocity_spike", "Pass-through velocity burst", "detector", 0.50),
            _Contributor("__retention__", "Low net retention (in ≈ out)", "structure", 0.50),
            _Contributor("structuring", "Sub-threshold inbound batching", "detector", 0.20),
        ),
        severity_floor="medium",
        narrative_template=(
            "Subject {account_id} acted as a pass-through node: "
            "₹{inbound_total} arrived across {counterparty_count} "
            "counterparties and ₹{outbound_total} departed within the same "
            "window, leaving net retention near zero. Pattern is consistent "
            "with a money-mule role inside a larger laundering ring."
        ),
        recommended_action=(
            "Freeze the account, request KYC re-verification, and request "
            "subject-interview disclosure of the third party operating the "
            "wallet. Cross-reference outbound recipients against the mule "
            "watchlist."
        ),
    ),
    TypologyDef(
        code="SANCEV",
        name="Sanctions Evasion",
        summary=(
            "Counterparty or subject name matches a sanctions watchlist; "
            "supporting cross-border / round-trip patterns aggravate."
        ),
        icon="⊘",
        accent="#f43f5e",  # rose-500
        contributors=(
            _Contributor("sanctions_hit", "Watchlist alias / name match", "detector", 1.00),
            _Contributor("__sanctions_strength__", "Match grade ≥ strong", "sanctions", 0.55),
            _Contributor("high_risk_geo", "Same-jurisdiction counterparty", "detector", 0.30),
            _Contributor("round_trip", "Layering around the matched name", "detector", 0.25),
        ),
        severity_floor="critical",
        narrative_template=(
            "Subject {account_id} transacted with one or more parties "
            "matching the bundled sanctions watchlist ({sanction_detail}). "
            "Pattern is consistent with sanctions-evasion intent."
        ),
        recommended_action=(
            "Block all further movement to/from the matched counterparty, "
            "freeze open value, and notify the designated authority within "
            "the regulatory reporting window."
        ),
    ),
    TypologyDef(
        code="INTEG",
        name="Integration",
        summary=(
            "Large round-number flows from a small set of counterparties — "
            "consistent with re-introducing laundered funds into the "
            "regulated economy via investment or real-asset purchase."
        ),
        icon="◇",
        accent="#0ea5e9",  # sky-500
        contributors=(
            _Contributor("round_amount", "Repeated large round transfers", "detector", 1.00),
            _Contributor("__low_counterparty_density__", "Low counterparty density", "structure", 0.55),
            _Contributor("velocity_spike", "Burst followed by quiet", "detector", 0.30),
            _Contributor("high_risk_geo", "Source geography elevated", "detector", 0.25),
        ),
        severity_floor="medium",
        narrative_template=(
            "Subject {account_id} received {inbound_total} concentrated in "
            "a small number of round-figure transfers ({integ_detail}). "
            "Pattern is consistent with the integration stage of a "
            "laundering cycle — proceeds re-entering the regulated economy."
        ),
        recommended_action=(
            "Verify ultimate beneficial ownership of the originating "
            "accounts and the destination asset (real estate, security, "
            "luxury good); confirm source-of-funds documentation before "
            "settlement closes."
        ),
    ),
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _factor_intensity(factor: Dict[str, Any]) -> float:
    """Intensity of a detector firing, on [0, 1].

    ``risk.Factor.points = intensity × weight``. We recover intensity as
    ``points / weight``; we clamp because the engine occasionally rounds
    to two decimals and we don't want a 1.001 sneaking into a confidence.
    """

    points = float(factor.get("points") or 0.0)
    weight = float(factor.get("weight") or 0.0)
    if weight <= 0.0 or points <= 0.0:
        return 0.0
    return max(0.0, min(1.0, points / weight))


def _factor_lookup(account_report: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for f in account_report.get("factors") or []:
        name = f.get("name")
        if isinstance(name, str):
            out[name] = f
    return out


def _retention_signal(account_report: Dict[str, Any]) -> float:
    """Returns 0..1 — high when inbound ≈ outbound and both non-trivial.

    Specifically: ``1 − |inbound − outbound| / max(inbound, outbound)``.
    A pure pass-through (inbound == outbound) scores 1.0; a deposit-only
    account scores 0.
    """

    inbound = float(account_report.get("inbound_total") or 0.0)
    outbound = float(account_report.get("outbound_total") or 0.0)
    larger = max(inbound, outbound)
    if larger <= 0.0:
        return 0.0
    # ignore tiny floats
    if larger < 1_000.0:
        return 0.0
    raw = 1.0 - abs(inbound - outbound) / larger
    # Compress the bottom: only count near-symmetric flows.
    return raw * raw  # squared response keeps weak matches from inflating MULE


def _sanctions_strength_signal(account_report: Dict[str, Any]) -> float:
    """Strongest sanctions similarity for this account, on [0, 1].

    A 0.65 match (the entry threshold) maps to 0.0; a perfect 1.0 maps to
    1.0; everything between scales linearly. This keeps SANCEV's strong-
    match bonus *additive on top of* the base ``sanctions_hit`` detector,
    rather than double-counting low matches.
    """

    hits = account_report.get("sanctions_hits") or []
    best = max((float(h.get("similarity") or 0.0) for h in hits), default=0.0)
    if best <= 0.65:
        return 0.0
    return max(0.0, min(1.0, (best - 0.65) / 0.35))


def _low_counterparty_density_signal(account_report: Dict[str, Any]) -> float:
    """Returns 1.0 when very few counterparties account for large value.

    Specifically: ``max(0, 1 − cp_count / 6)``. Three counterparties → 0.5;
    six counterparties → 0; one counterparty → ~0.83.
    """

    cp = float(account_report.get("counterparty_count") or 0)
    if cp <= 0.0:
        return 0.0
    return max(0.0, 1.0 - cp / 6.0)


def _evidence_for(
    contributor: _Contributor,
    signal: float,
    contribution: float,
    factor_detail: str = "",
) -> Dict[str, Any]:
    return {
        "key": contributor.key,
        "label": contributor.label,
        "kind": contributor.kind,
        "signal": round(signal, 3),
        "contribution": round(contribution, 3),
        "weight": round(contributor.weight, 3),
        "detail": factor_detail or "",
    }


def _structural_signal(key: str, account_report: Dict[str, Any]) -> float:
    if key == "__retention__":
        return _retention_signal(account_report)
    if key == "__sanctions_strength__":
        return _sanctions_strength_signal(account_report)
    if key == "__low_counterparty_density__":
        return _low_counterparty_density_signal(account_report)
    return 0.0


def _detail_for(name: str, factors: Dict[str, Dict[str, Any]]) -> str:
    f = factors.get(name)
    if not f:
        return ""
    return str(f.get("detail") or "")


def _format_inr(value: float) -> str:
    """Indian-numbering format used in the narrative (e.g. ₹12,34,567.00)."""

    if value <= 0:
        return "₹0"
    neg = value < 0
    v = abs(value)
    integer = int(v)
    fractional = f"{v - integer:.2f}".lstrip("0")  # ".00" or ".42"
    s = str(integer)
    # last 3, then groups of 2
    if len(s) <= 3:
        grouped = s
    else:
        head, tail = s[:-3], s[-3:]
        chunks: List[str] = [tail]
        while len(head) > 2:
            chunks.insert(0, head[-2:])
            head = head[:-2]
        if head:
            chunks.insert(0, head)
        grouped = ",".join(chunks)
    out = f"₹{grouped}{fractional}"
    return f"-{out}" if neg else out


def _geo_detail(factors: Dict[str, Dict[str, Any]]) -> str:
    """Pull the elevated-geography list out of the ``high_risk_geo`` factor's
    evidence rows. The detector emits ``{"geo": "RU", ...}`` per hit."""

    f = factors.get("high_risk_geo")
    if not f:
        return ""
    seen: List[str] = []
    for ev in f.get("evidence") or []:
        geo = (ev.get("geo") or "").upper()
        if geo and geo not in seen:
            seen.append(geo)
    if not seen:
        return ""
    return ", ".join(seen[:5])


def _sanction_detail(account_report: Dict[str, Any]) -> str:
    hits = account_report.get("sanctions_hits") or []
    names: List[str] = []
    for h in hits[:3]:
        nm = (h.get("matched_alias") or h.get("name") or h.get("party") or "").strip()
        sim = h.get("similarity")
        if not nm:
            continue
        if sim is not None:
            names.append(f"{nm} ({float(sim):.0%})")
        else:
            names.append(nm)
    return "; ".join(names) if names else "watchlist alias match"


def _integ_detail(account_report: Dict[str, Any], factors: Dict[str, Dict[str, Any]]) -> str:
    f = factors.get("round_amount")
    cp = int(account_report.get("counterparty_count") or 0)
    count = 0
    if f:
        for ev in f.get("evidence") or []:
            count += 1
    if count <= 0:
        count = max(1, int(f.get("points", 0) or 0))
    return f"{count} round transfer{'s' if count != 1 else ''} from {cp} source{'s' if cp != 1 else ''}"


# ---------------------------------------------------------------------------
# Core scorer
# ---------------------------------------------------------------------------


def _score_typology(
    type_def: TypologyDef, account_report: Dict[str, Any]
) -> Optional[TypologyMatch]:
    factors = _factor_lookup(account_report)
    contributions: List[Dict[str, Any]] = []
    raw_score = 0.0

    for c in type_def.contributors:
        if c.kind == "detector":
            f = factors.get(c.key)
            signal = _factor_intensity(f) if f else 0.0
            detail = _detail_for(c.key, factors) if signal > 0 else ""
        elif c.kind in ("structure", "sanctions"):
            signal = _structural_signal(c.key, account_report)
            detail = ""
        else:
            signal = 0.0
            detail = ""

        contribution = signal * c.weight
        if contribution > 0.0:
            contributions.append(
                _evidence_for(c, signal, contribution, factor_detail=detail)
            )
        raw_score += contribution

    if type_def.max_score <= 0.0:
        confidence = 0.0
    else:
        confidence = raw_score / type_def.max_score

    if confidence < CONFIDENCE_FLOOR:
        return None

    # Sort evidence by contribution descending — the UI renders top-first.
    contributions.sort(key=lambda e: e["contribution"], reverse=True)

    inbound = float(account_report.get("inbound_total") or 0.0)
    outbound = float(account_report.get("outbound_total") or 0.0)
    placeholders = {
        "account_id": account_report.get("account_id") or "(unknown)",
        "inbound_total": _format_inr(inbound),
        "outbound_total": _format_inr(outbound),
        "flow_total": _format_inr(max(inbound, outbound)),
        "counterparty_count": account_report.get("counterparty_count") or 0,
        "struct_detail": _detail_for("structuring", factors) or "sub-threshold deposit batching",
        "cycle_detail": _detail_for("round_trip", factors) or "a closed transfer loop",
        "geo_detail": _geo_detail(factors) or "FATF-grey jurisdictions",
        "sanction_detail": _sanction_detail(account_report),
        "integ_detail": _integ_detail(account_report, factors),
    }

    try:
        narrative = type_def.narrative_template.format(**placeholders)
    except (KeyError, IndexError):
        narrative = type_def.summary

    return TypologyMatch(
        code=type_def.code,
        name=type_def.name,
        summary=type_def.summary,
        icon=type_def.icon,
        accent=type_def.accent,
        confidence=confidence,
        severity_floor=type_def.severity_floor,
        evidence=contributions,
        narrative=narrative,
        recommended_action=type_def.recommended_action,
        contributing_factor_names=[
            c["label"] for c in contributions if c["kind"] == "detector"
        ],
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def classify(account_report: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Rank typology matches for one account report.

    Returns up to ``MAX_REPORTED`` dicts sorted by confidence descending.
    Always returns a list, never raises — a quiet account simply returns
    ``[]`` and the calling surface should treat that as *"no playbook
    fits — review on the factor evidence alone"*.
    """

    if not isinstance(account_report, dict):
        return []
    matches: List[TypologyMatch] = []
    for td in _LIBRARY:
        m = _score_typology(td, account_report)
        if m is not None:
            matches.append(m)
    matches.sort(key=lambda m: m.confidence, reverse=True)
    return [m.to_dict() for m in matches[:MAX_REPORTED]]


def top_typology(account_report: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Convenience: the single highest-confidence match, or ``None``."""

    matches = classify(account_report)
    return matches[0] if matches else None


def severity_for_priority(severity_floor: str, current_priority: str) -> str:
    """Promote a case priority if the typology severity demands it.

    Cases default to a priority derived from ``max(risk_score,
    sanctions_pct)``. When a critical-floor typology like SANCEV fires,
    the case should ride at critical even when the per-account score
    sits in the 60s.
    """

    return _severity_max(current_priority, severity_floor)


def get_library() -> Dict[str, Any]:
    """Auditor-facing dump. Exposes each typology's full contributor list,
    accent colour, and confidence formula in a self-describing payload."""

    return {
        "version": ENGINE_VERSION,
        "confidence_floor": CONFIDENCE_FLOOR,
        "max_reported": MAX_REPORTED,
        "typologies": [
            {
                "code": td.code,
                "name": td.name,
                "summary": td.summary,
                "icon": td.icon,
                "accent": td.accent,
                "severity_floor": td.severity_floor,
                "recommended_action": td.recommended_action,
                "contributors": [
                    {
                        "key": c.key,
                        "label": c.label,
                        "kind": c.kind,
                        "weight": c.weight,
                    }
                    for c in td.contributors
                ],
                "max_score": round(td.max_score, 3),
            }
            for td in _LIBRARY
        ],
    }


# ----- handy CLI for ad-hoc rendering, e.g. `python -m typology < report.json`
if __name__ == "__main__":  # pragma: no cover
    import json
    import sys

    payload = json.load(sys.stdin)
    print(json.dumps(classify(payload), indent=2))
