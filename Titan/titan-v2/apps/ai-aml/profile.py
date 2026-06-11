"""TITAN Customer Risk Profile (CRP) engine.

Round-10, day-50. The missing executive-grade layer that fuses every other
surface in this repo (AML, sanctions, adverse media, typology, drift,
network) into a single composite **per customer**, with a clear regulatory
bucket, an FATF-aligned KYC refresh schedule, an audit-trailed analyst
override, and a portfolio-wide rollup.

Why this exists
---------------
Per-account risk scoring catches one account at a time. Sanctions screening
answers a binary against a closed list. Adverse-media answers the open-world
question. Typology names the playbook. Drift catches account-vs-self
behaviour. Network catches the picture. None of them produce the **one
number an MLRO / Chief Compliance Officer is required to maintain by FATF
Rec. 10 (CDD / risk-based approach), EU 6AMLD, BSA/FFIEC, and FIU-IND
master directions:** the composite *customer-level* risk rating.

That rating drives:

1. The **KYC refresh cadence** — high-risk customers must be reviewed more
   often (default 90d/180d/365d/720d by bucket).
2. The **product gating** — onboarding new high-value products requires
   a fresh review for `high`/`critical` customers.
3. The **regulator-facing summary** — when a regulator inspects a bank
   today, the FIRST thing they ask is "show me your customer book sliced
   by risk bucket, broken down by domicile and product, and the override
   audit trail for any analyst-adjusted ratings".

The CRP engine is that view. It is a pure-function composite (same
inputs → same composite, every byte) plus a thin SQLite store that
persists the latest profile per customer with a full append-only history.

Composite formula
-----------------
Each surface contributes a 0..1 intensity * a fixed weight. The blend is
deterministic; weights are exposed via ``GET /aml/profile/rules`` so
auditors can verify the formula before the engine ships.

    composite = clip(
          W.transaction       * transaction_intensity     # from AML risk_score
        + W.sanctions         * sanctions_intensity       # best similarity
        + W.media             * media_intensity           # composite / 100
        + W.typology          * typology_intensity        # confidence × severity
        + W.drift             * drift_intensity           # overall drift
        + W.network           * network_lift_intensity    # network − solo
        + geo_modifier                                    # +5 if domicile ∈ FATF
        + pep_modifier                                    # +8 if PEP
        + product_modifier                                # +n for high-risk product mix
        , 0, 100)

Default weights (sum to 100 before modifiers):

    transaction 28 · sanctions 22 · media 16 · typology 12 · drift 12 · network 10

Modifiers are *additive bumps*, not multipliers, so the analyst can read
them off the breakdown as separate rows. Bumps cap at +20 total.

Buckets (FATF-aligned)
----------------------
    low      <  30   refresh every 720 days  (2y)
    medium   30 .. 59 refresh every 365 days  (1y)
    high     60 .. 79 refresh every 180 days  (6mo)
    critical >= 80   refresh every  90 days  (1q)

A customer override (analyst-supplied) can pin a higher bucket
explicitly; the *displayed* composite still shows the engine's number
alongside the override so the override is auditable and reversible.

KYC refresh status
------------------
    current     anchor + interval > now + 30d        teal
    due_soon    next due within 30d                  amber
    overdue     anchor + interval < now              rose

Storage
-------
Two SQLite tables (initialised at import time, idempotent migrations):

    customer_profiles    (customer_id PK, …)
    profile_history      (id PK AUTOINC, customer_id, …)

The DB lives at ``apps/ai-aml/data/profiles.sqlite3``. Per-deployment,
gitignored, WAL mode.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import sqlite3
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

import drift as drift_engine
import media as media_engine
import network as network_engine
import risk as risk_engine
import sanctions as sanctions_engine


ENGINE_VERSION = "titan-profile/1.0.0"
RULES_VERSION = "1.0.0"


# ---------------------------------------------------------------------------
# Tunables — exposed via GET /aml/profile/rules so callers can audit them.
# ---------------------------------------------------------------------------

WEIGHTS: Dict[str, float] = {
    "transaction": 28.0,
    "sanctions": 22.0,
    "media": 16.0,
    "typology": 12.0,
    "drift": 12.0,
    "network": 10.0,
}

SURFACE_ORDER: Tuple[str, ...] = (
    "transaction",
    "sanctions",
    "media",
    "typology",
    "drift",
    "network",
)

# Bucket thresholds (FATF risk-based-approach aligned).
BUCKETS: List[Tuple[float, str]] = [
    (80.0, "critical"),
    (60.0, "high"),
    (30.0, "medium"),
    (0.0, "low"),
]

# Refresh cadence in days, per bucket.
REFRESH_DAYS: Dict[str, int] = {
    "low": 720,
    "medium": 365,
    "high": 180,
    "critical": 90,
}

# How many days before due → "due_soon".
DUE_SOON_DAYS = 30

# Modifier bumps (additive; capped at MODIFIER_CAP total).
GEO_MODIFIER = 5.0
PEP_MODIFIER = 8.0
HIGH_RISK_PRODUCT_MODIFIER = 4.0   # per high-risk product, capped below
MODIFIER_CAP = 20.0

# Typology severity multipliers — fold severity_floor into the contribution.
TYPOLOGY_SEVERITY_MULT: Dict[str, float] = {
    "critical": 1.00,
    "high":     0.85,
    "medium":   0.65,
    "low":      0.40,
}

# Surface accents (kept consistent with the rest of the UI palette).
SURFACE_META: Dict[str, Dict[str, Any]] = {
    "transaction": {"label": "Transaction risk", "accent": "#6E5BFF",
                    "source": "/aml/score", "icon": "tx"},
    "sanctions":   {"label": "Sanctions exposure", "accent": "#ef4444",
                    "source": "/aml/sanctions/screen", "icon": "san"},
    "media":       {"label": "Adverse media",     "accent": "#f97316",
                    "source": "/aml/media/screen", "icon": "media"},
    "typology":    {"label": "Typology assignment", "accent": "#a78bfa",
                    "source": "/aml/typologies", "icon": "typ"},
    "drift":       {"label": "Behavioral drift",   "accent": "#fb923c",
                    "source": "/aml/drift", "icon": "drift"},
    "network":     {"label": "Network exposure",   "accent": "#2DE1C2",
                    "source": "/aml/network/analyze", "icon": "net"},
}

BUCKET_META: Dict[str, Dict[str, Any]] = {
    "low":      {"accent": "#22d3a8", "blurb": "Routine monitoring. No additional action.",
                 "action": "Continue baseline transaction monitoring; refresh KYC at the next scheduled cycle."},
    "medium":   {"accent": "#fbbf24", "blurb": "Standard CDD with periodic review.",
                 "action": "Quarterly transaction review; flag for analyst attention if behaviour shifts."},
    "high":     {"accent": "#fb923c", "blurb": "Enhanced Due Diligence (EDD) required.",
                 "action": "Run EDD cycle: source-of-funds, beneficial ownership refresh, adverse-media re-screen. Senior compliance sign-off."},
    "critical": {"accent": "#ef4444", "blurb": "Immediate review. Consider product gating.",
                 "action": "Freeze new-product onboarding pending MLRO review. Escalate to senior compliance and prepare evidence package for the FIU."},
}

# FATF/EU-style high-risk jurisdictions for the geo modifier — kept in
# sync with risk.py::HIGH_RISK_GEOS so an account in `RU` gets the same
# bump from both surfaces. Live deployments swap this list at runtime
# via TITAN_PROFILE_GEO_LIST (one ISO-2 per line).
HIGH_RISK_GEOS: set = set(risk_engine.HIGH_RISK_GEOS)

# Products with an industry-standard high-risk profile (FATF / EBA / FFIEC):
HIGH_RISK_PRODUCTS: set = {
    "private_banking", "correspondent_banking", "trade_finance",
    "crypto", "money_service_business", "casino", "precious_metals",
}


# ---------------------------------------------------------------------------
# Domain types
# ---------------------------------------------------------------------------


@dataclass
class FactorContribution:
    """One surface's contribution to the composite. ``intensity`` is the
    0..1 input from that surface; ``points = intensity * weight``."""

    key: str
    label: str
    accent: str
    weight: float
    intensity: float
    points: float
    detail: str
    evidence: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "accent": self.accent,
            "weight": round(self.weight, 2),
            "intensity": round(self.intensity, 4),
            "points": round(self.points, 2),
            "detail": self.detail,
            "evidence": self.evidence,
        }


@dataclass
class Modifier:
    key: str
    label: str
    points: float
    detail: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "points": round(self.points, 2),
            "detail": self.detail,
        }


# ---------------------------------------------------------------------------
# Helpers — bucket / refresh / time
# ---------------------------------------------------------------------------


def bucket_for(composite: float) -> str:
    for floor, label in BUCKETS:
        if composite >= floor:
            return label
    return "low"


def refresh_due_iso(anchor_iso: str, bucket: str) -> Optional[str]:
    """`anchor + REFRESH_DAYS[bucket]`, ISO-formatted."""
    if not anchor_iso:
        return None
    try:
        anchor = datetime.fromisoformat(anchor_iso.replace("Z", "+00:00"))
    except ValueError:
        return None
    if anchor.tzinfo is None:
        anchor = anchor.replace(tzinfo=timezone.utc)
    due = anchor + timedelta(days=REFRESH_DAYS.get(bucket, 365))
    return due.isoformat()


def refresh_status(due_iso: Optional[str], *, now: Optional[datetime] = None) -> Dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    if not due_iso:
        return {"label": "unscheduled", "days_to_due": None, "tone": "muted"}
    try:
        due = datetime.fromisoformat(due_iso.replace("Z", "+00:00"))
    except ValueError:
        return {"label": "unscheduled", "days_to_due": None, "tone": "muted"}
    if due.tzinfo is None:
        due = due.replace(tzinfo=timezone.utc)
    delta_days = (due - now).total_seconds() / 86400.0
    if delta_days < 0:
        return {"label": "overdue", "days_to_due": round(delta_days, 1), "tone": "rose"}
    if delta_days <= DUE_SOON_DAYS:
        return {"label": "due_soon", "days_to_due": round(delta_days, 1), "tone": "amber"}
    return {"label": "current", "days_to_due": round(delta_days, 1), "tone": "teal"}


# ---------------------------------------------------------------------------
# Surface intensity adapters — each turns a per-surface payload into a
# normalised 0..1 intensity + an evidence blob the UI can render.
# ---------------------------------------------------------------------------


def _transaction_intensity(evidence: Dict[str, Any]) -> Tuple[float, str, Dict[str, Any]]:
    """`evidence.transaction = {risk_score, band, accounts: [{account_id,
    risk_score, band, fired_count, …}, …]}` OR a raw /aml/score response."""
    if not evidence:
        return 0.0, "No transaction evidence supplied.", {}

    # Accept either the rolled-up shape or a /aml/score response directly.
    accounts: List[Dict[str, Any]] = []
    if isinstance(evidence.get("accounts"), list):
        accounts = evidence["accounts"]
    elif isinstance(evidence.get("ranked"), list):
        accounts = evidence["ranked"]
    headline_risk = float(evidence.get("risk_score") or 0.0)
    if not headline_risk and accounts:
        headline_risk = max((float(a.get("risk_score") or 0) for a in accounts), default=0.0)

    intensity = max(0.0, min(1.0, headline_risk / 100.0))
    band = evidence.get("band") or risk_engine._band(headline_risk) if headline_risk else "low"
    fired = sum(int(a.get("fired_count") or 0) for a in accounts)

    detail = (
        f"Max account risk {headline_risk:.0f} ({band})"
        + (f" · {fired} firing detectors across {len(accounts)} account(s)" if accounts else "")
        + "."
    )
    return intensity, detail, {
        "risk_score": round(headline_risk, 1),
        "band": band,
        "account_count": len(accounts),
        "fired_count": fired,
        "top_accounts": [
            {
                "account_id": a.get("account_id"),
                "risk_score": round(float(a.get("risk_score") or 0), 1),
                "band": a.get("band"),
            }
            for a in sorted(accounts, key=lambda a: float(a.get("risk_score") or 0), reverse=True)[:5]
        ],
    }


def _sanctions_intensity(evidence: Dict[str, Any]) -> Tuple[float, str, Dict[str, Any]]:
    """`evidence.sanctions = {results: [{best: {similarity, grade, name, …}}, …]}`
    or `{best_similarity, best_grade, hit_count}`. Intensity = best similarity."""
    if not evidence:
        return 0.0, "No sanctions screen on file.", {}

    best_sim = float(evidence.get("best_similarity") or 0.0)
    best_grade = evidence.get("best_grade") or "none"
    hits: List[Dict[str, Any]] = []

    results = evidence.get("results")
    if isinstance(results, list):
        for r in results:
            best = r.get("best") or {}
            if not best:
                continue
            sim = float(best.get("similarity") or 0.0)
            if sim > best_sim:
                best_sim = sim
                best_grade = best.get("grade") or best_grade
            hits.append({
                "queried_name": r.get("query") or r.get("queried_name"),
                "matched": best.get("name"),
                "matched_alias": best.get("matched_alias"),
                "list": best.get("list"),
                "jurisdiction": best.get("jurisdiction"),
                "similarity": round(sim, 4),
                "grade": best.get("grade"),
            })

    # Below the entry threshold → no real contribution.
    floor = float(evidence.get("hit_floor") or risk_engine.SANCTIONS_HIT_THRESHOLD)
    if best_sim < floor:
        return 0.0, (
            f"No watchlist hit ≥{floor:.0%} (best {best_sim:.0%})."
            if best_sim > 0 else "No watchlist hit."
        ), {"best_similarity": round(best_sim, 4), "hits": hits}

    intensity = max(0.0, min(1.0, (best_sim - floor) / max(1.0 - floor, 1e-6)))
    # Anchor strong/exact at ≥0.85 intensity so the bucket promotion is decisive.
    if best_grade in ("strong", "exact"):
        intensity = max(intensity, 0.85)

    detail = (
        f"Best alias hit {best_sim:.0%} ({best_grade}) across {len(hits)} screen(s)."
    )
    return intensity, detail, {
        "best_similarity": round(best_sim, 4),
        "best_grade": best_grade,
        "hit_floor": floor,
        "hit_count": len(hits),
        "hits": hits[:6],
    }


def _media_intensity(evidence: Dict[str, Any]) -> Tuple[float, str, Dict[str, Any]]:
    """`evidence.media = {composite, grade, hit_count, top_articles[]}` OR
    a raw screen_batch result list."""
    if not evidence:
        return 0.0, "No adverse-media screen on file.", {}

    composite = float(evidence.get("composite") or 0.0)
    grade = evidence.get("grade") or "clear"
    hit_count = int(evidence.get("hit_count") or 0)
    top_articles = evidence.get("top_articles") or []

    if not composite and isinstance(evidence.get("results"), list):
        results = evidence["results"]
        composite = max((float(r.get("composite") or 0) for r in results), default=0.0)
        grade = next(
            (r["grade"] for r in results if float(r.get("composite") or 0) == composite),
            "clear",
        )
        hit_count = sum(int(r.get("hit_count") or 0) for r in results)
        # Top three articles by hit_strength across all results.
        merged: List[Dict[str, Any]] = []
        for r in results:
            for h in r.get("top_hits") or []:
                merged.append({**h, "queried_name": r.get("query")})
        merged.sort(key=lambda h: float(h.get("hit_strength") or 0), reverse=True)
        top_articles = merged[:3]

    intensity = max(0.0, min(1.0, composite / 100.0))
    detail = (
        f"Composite {composite:.0f} / 100 ({grade}); {hit_count} adverse article(s)."
        if hit_count else "No adverse coverage matched."
    )
    return intensity, detail, {
        "composite": round(composite, 1),
        "grade": grade,
        "hit_count": hit_count,
        "top_articles": top_articles[:3],
    }


def _typology_intensity(evidence: Dict[str, Any]) -> Tuple[float, str, Dict[str, Any]]:
    """`evidence.typology = {code, confidence, severity_floor, …}` OR a list
    of matches (we take the top one)."""
    if not evidence:
        return 0.0, "No typology assignment.", {}

    matches = evidence.get("matches")
    if isinstance(matches, list) and matches:
        top = matches[0]
    elif "code" in evidence:
        top = evidence
        matches = [evidence]
    else:
        return 0.0, "No typology assignment.", {}

    confidence = float(top.get("confidence") or 0.0)
    severity = top.get("severity_floor") or "low"
    mult = TYPOLOGY_SEVERITY_MULT.get(severity, 0.5)
    intensity = max(0.0, min(1.0, confidence * mult))
    detail = (
        f"{top.get('code')} ({top.get('name', '')}) @ {confidence*100:.0f}% "
        f"confidence · severity floor {severity}."
    )
    return intensity, detail, {
        "code": top.get("code"),
        "name": top.get("name"),
        "confidence": round(confidence, 4),
        "severity_floor": severity,
        "accent": top.get("accent"),
        "summary": top.get("summary"),
        "runners_up": [
            {"code": m.get("code"), "confidence": round(float(m.get("confidence") or 0), 4)}
            for m in matches[1:3]
        ] if isinstance(matches, list) else [],
    }


def _drift_intensity(evidence: Dict[str, Any]) -> Tuple[float, str, Dict[str, Any]]:
    """`evidence.drift = {overall, verdict, change_point: {onset_iso}, …}`."""
    if not evidence:
        return 0.0, "No drift report on file.", {}

    overall = float(evidence.get("overall") or 0.0)
    verdict = evidence.get("verdict") or "stable"
    onset = (evidence.get("change_point") or {}).get("onset_iso") or evidence.get("onset_iso")
    drivers = evidence.get("drivers") or []
    intensity = max(0.0, min(1.0, overall))
    detail = (
        f"Behaviour {verdict} (overall {overall:.2f})"
        + (f" · onset {onset[:10]}." if onset else ".")
    )
    return intensity, detail, {
        "overall": round(overall, 4),
        "verdict": verdict,
        "onset_iso": onset,
        "top_drivers": drivers[:3],
    }


def _network_intensity(evidence: Dict[str, Any]) -> Tuple[float, str, Dict[str, Any]]:
    """`evidence.network = {solo_risk, network_risk, peer_lifts, …}`. The
    intensity is the *lift* — how much the network raised the solo
    score — clipped to 0..1, so a clean account heavily linked to a
    sanctioned one is a real CRP signal."""
    if not evidence:
        return 0.0, "No network analysis on file.", {}

    solo = float(evidence.get("solo_risk") or evidence.get("risk_score") or 0.0)
    net_risk = float(evidence.get("network_risk") or 0.0)
    lift = max(0.0, net_risk - solo)
    intensity = max(0.0, min(1.0, lift / 40.0))   # 40 points of lift saturates
    peer_lifts = evidence.get("peer_lifts") or []
    detail = (
        f"Network risk {net_risk:.0f} vs solo {solo:.0f} (lift +{lift:.0f})."
    )
    return intensity, detail, {
        "solo_risk": round(solo, 1),
        "network_risk": round(net_risk, 1),
        "lift": round(lift, 1),
        "peer_count": int(evidence.get("peer_count") or 0),
        "peer_lifts": peer_lifts[:5],
    }


_SURFACE_ADAPTERS = {
    "transaction": _transaction_intensity,
    "sanctions":   _sanctions_intensity,
    "media":       _media_intensity,
    "typology":    _typology_intensity,
    "drift":       _drift_intensity,
    "network":     _network_intensity,
}


# ---------------------------------------------------------------------------
# Modifier resolution
# ---------------------------------------------------------------------------


def _resolve_modifiers(customer: Dict[str, Any]) -> List[Modifier]:
    mods: List[Modifier] = []
    domicile = (customer.get("domicile") or "").upper()
    if domicile in HIGH_RISK_GEOS:
        mods.append(Modifier(
            key="geo",
            label=f"High-risk domicile · {domicile}",
            points=GEO_MODIFIER,
            detail=f"Customer domicile {domicile} appears on the FATF grey/black-list.",
        ))
    if customer.get("pep"):
        mods.append(Modifier(
            key="pep",
            label="Politically Exposed Person",
            points=PEP_MODIFIER,
            detail="Customer flagged as PEP — enhanced scrutiny is required.",
        ))
    products = customer.get("products") or []
    high_risk = [p for p in products if p in HIGH_RISK_PRODUCTS]
    if high_risk:
        bump = min(HIGH_RISK_PRODUCT_MODIFIER * len(high_risk), 12.0)
        mods.append(Modifier(
            key="product",
            label="High-risk product mix",
            points=bump,
            detail="Holds " + ", ".join(high_risk) + ".",
        ))
    # Cap the total bump so modifiers never dominate the composite.
    total = sum(m.points for m in mods)
    if total > MODIFIER_CAP:
        scale = MODIFIER_CAP / total
        for m in mods:
            m.points = round(m.points * scale, 2)
    return mods


# ---------------------------------------------------------------------------
# Resolve weights with optional caller override (same shape as risk.py).
# ---------------------------------------------------------------------------


def _resolve_weights(override: Optional[Dict[str, Any]]) -> Dict[str, float]:
    weights = dict(WEIGHTS)
    if not override:
        return weights
    for key, val in override.items():
        if key not in weights:
            continue
        try:
            v = float(val)
        except (TypeError, ValueError):
            continue
        weights[key] = max(0.0, min(60.0, v))
    return weights


# ---------------------------------------------------------------------------
# Headline narrative — auto-generated executive summary.
# ---------------------------------------------------------------------------


def _build_narrative(
    customer: Dict[str, Any],
    composite: float,
    bucket: str,
    factors: List[FactorContribution],
    modifiers: List[Modifier],
    override: Optional[Dict[str, Any]],
) -> str:
    name = customer.get("display_name") or customer.get("customer_id") or "Customer"
    top_factor = max(factors, key=lambda f: f.points, default=None)
    pieces: List[str] = []
    pieces.append(
        f"{name} sits at composite **{composite:.0f}** / 100 "
        f"({bucket}) on the TITAN risk-based-approach scale."
    )
    if top_factor and top_factor.points >= 4.0:
        pieces.append(
            f"The dominant signal is **{top_factor.label.lower()}** "
            f"({top_factor.points:.1f} pts, {top_factor.intensity*100:.0f}% of its weight)."
        )
    if modifiers:
        pieces.append(
            "Modifiers add "
            + ", ".join(f"+{m.points:.0f} for {m.label.lower()}" for m in modifiers)
            + "."
        )
    if override:
        pieces.append(
            f"Analyst override locks the rating at **{override.get('locked_bucket','—')}** — "
            f"{override.get('justification', '')[:160].rstrip()}"
        )
    action = BUCKET_META.get(bucket, {}).get("action", "")
    if action:
        pieces.append(action)
    return " ".join(pieces)


# ---------------------------------------------------------------------------
# Core composite — pure function, deterministic.
# ---------------------------------------------------------------------------


def compute_profile(
    customer: Dict[str, Any],
    evidence: Optional[Dict[str, Any]] = None,
    *,
    weights_override: Optional[Dict[str, Any]] = None,
    override: Optional[Dict[str, Any]] = None,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Compute the customer risk profile from the supplied evidence dict.

    Parameters
    ----------
    customer : dict
        ``{customer_id, display_name?, customer_type?, domicile?, pep?,
           products?, kyc_anchor?}``
    evidence : dict, optional
        ``{transaction?, sanctions?, media?, typology?, drift?, network?}``
        — each key's value is the per-surface payload (see the adapter
        functions above for the accepted shapes). Missing keys mean
        "no signal from this surface" (intensity 0).
    weights_override : dict, optional
        Per-surface weight overrides (same shape as ``WEIGHTS``).
    override : dict, optional
        Analyst override — ``{locked_bucket, justification, expires_iso?,
        actor?}`` — pins the surfaced bucket while still computing and
        showing the engine's underlying composite.
    now : datetime, optional
        Override clock (for testing / replay).
    """

    if not isinstance(customer, dict) or not customer.get("customer_id"):
        raise ValueError("customer.customer_id is required")
    evidence = evidence or {}
    now = now or datetime.now(timezone.utc)
    weights = _resolve_weights(weights_override)

    factors: List[FactorContribution] = []
    for key in SURFACE_ORDER:
        adapter = _SURFACE_ADAPTERS[key]
        intensity, detail, ev = adapter(evidence.get(key) or {})
        weight = weights[key]
        points = intensity * weight
        meta = SURFACE_META[key]
        factors.append(FactorContribution(
            key=key,
            label=meta["label"],
            accent=meta["accent"],
            weight=weight,
            intensity=intensity,
            points=points,
            detail=detail,
            evidence=ev,
        ))

    modifiers = _resolve_modifiers(customer)

    raw = sum(f.points for f in factors) + sum(m.points for m in modifiers)
    composite = max(0.0, min(100.0, raw))
    engine_bucket = bucket_for(composite)

    # Analyst override: can pin a bucket. The engine composite is preserved
    # in `engine_composite` so the audit log captures both numbers.
    surfaced_bucket = engine_bucket
    surfaced_composite = composite
    if override and override.get("locked_bucket"):
        locked = str(override["locked_bucket"]).lower()
        if locked in REFRESH_DAYS:
            surfaced_bucket = locked
            # If the override is *more conservative* (higher bucket), raise
            # the surfaced composite to the bottom of that bucket so the
            # ring + bar look honest. We never *lower* the displayed score.
            band_floors = {label: floor for floor, label in BUCKETS}
            min_for_bucket = band_floors.get(locked, 0.0)
            if surfaced_composite < min_for_bucket:
                surfaced_composite = max(surfaced_composite, min_for_bucket + 1.0)

    kyc_anchor = customer.get("kyc_anchor") or _now_iso(now=now)
    kyc_due = refresh_due_iso(kyc_anchor, surfaced_bucket)
    refresh = refresh_status(kyc_due, now=now)

    narrative = _build_narrative(
        customer, surfaced_composite, surfaced_bucket, factors, modifiers, override,
    )
    bucket_meta = BUCKET_META.get(surfaced_bucket, BUCKET_META["low"])

    return {
        "engine": ENGINE_VERSION,
        "rules_version": RULES_VERSION,
        "computed_at": now.isoformat(),
        "customer": {
            "customer_id": customer["customer_id"],
            "display_name": customer.get("display_name") or customer["customer_id"],
            "customer_type": customer.get("customer_type") or "individual",
            "domicile": (customer.get("domicile") or "").upper() or None,
            "pep": bool(customer.get("pep")),
            "products": list(customer.get("products") or []),
            "kyc_anchor": kyc_anchor,
        },
        "engine_composite": round(composite, 1),
        "engine_bucket": engine_bucket,
        "composite": round(surfaced_composite, 1),
        "bucket": surfaced_bucket,
        "bucket_accent": bucket_meta["accent"],
        "bucket_blurb": bucket_meta["blurb"],
        "recommended_action": bucket_meta["action"],
        "factors": [f.to_dict() for f in factors],
        "modifiers": [m.to_dict() for m in modifiers],
        "modifier_total": round(sum(m.points for m in modifiers), 2),
        "weights": weights,
        "kyc_anchor": kyc_anchor,
        "kyc_due": kyc_due,
        "refresh": refresh,
        "narrative": narrative,
        "override": override or None,
    }


def _now_iso(*, now: Optional[datetime] = None) -> str:
    return (now or datetime.now(timezone.utc)).isoformat()


# ---------------------------------------------------------------------------
# Aggregator — when the caller has raw transactions instead of a pre-built
# evidence dict, this runs the relevant engines and returns the same payload
# shape ``compute_profile`` expects. Pure function of `(customer, transactions)`.
# ---------------------------------------------------------------------------


def build_evidence(
    customer: Dict[str, Any],
    transactions: Optional[List[Dict[str, Any]]] = None,
    *,
    sanctions_threshold: float = risk_engine.SANCTIONS_HIT_THRESHOLD,
) -> Dict[str, Any]:
    """Run every engine across the supplied transactions and return the
    consolidated `evidence` blob.

    The customer's `accounts` field (a list of account_ids the customer
    owns) scopes which accounts feed which surface. If absent, every
    account in the batch is treated as the customer's footprint.
    """

    evidence: Dict[str, Any] = {}
    if not transactions:
        return evidence

    owned: set = set(map(str, customer.get("accounts") or []))
    # Run the AML scorer once over the whole batch — most surfaces ride
    # off this single pass.
    score_resp = risk_engine.score_accounts(transactions, sanctions_threshold=sanctions_threshold)
    accounts = score_resp.get("accounts", [])
    if owned:
        accounts = [a for a in accounts if a.get("account_id") in owned]
    elif accounts:
        # Default scope: pick the top-scored single account so the
        # surface contributions are about *one* customer, not the book.
        accounts = sorted(accounts, key=lambda a: float(a.get("risk_score") or 0), reverse=True)[:1]

    if accounts:
        top = accounts[0]
        evidence["transaction"] = {
            "risk_score": top.get("risk_score"),
            "band": top.get("band"),
            "accounts": [
                {
                    "account_id": a.get("account_id"),
                    "risk_score": a.get("risk_score"),
                    "band": a.get("band"),
                    "fired_count": sum(1 for f in a.get("factors", []) if (f.get("points") or 0) > 0),
                }
                for a in accounts
            ],
        }

        # Sanctions evidence — roll up the per-account hits.
        sanc_results: List[Dict[str, Any]] = []
        best_sim = 0.0
        best_grade = "none"
        for a in accounts:
            for h in a.get("sanctions_hits") or []:
                sanc_results.append({
                    "query": h.get("queried_name") or h.get("queried_party"),
                    "best": h,
                })
                if float(h.get("similarity") or 0) > best_sim:
                    best_sim = float(h.get("similarity") or 0)
                    best_grade = h.get("grade") or best_grade
        if sanc_results:
            evidence["sanctions"] = {
                "best_similarity": best_sim,
                "best_grade": best_grade,
                "hit_floor": sanctions_threshold,
                "hit_count": len(sanc_results),
                "results": sanc_results,
            }

        # Media — the AML risk engine already runs media.hits_for_account
        # per account; the rolled-up report lives on `adverse_media`.
        media_reports = [a.get("adverse_media") for a in accounts if a.get("adverse_media")]
        if media_reports:
            best = max(media_reports, key=lambda r: float(r.get("composite") or 0))
            evidence["media"] = best

        # Typology — top match across owned accounts.
        all_matches: List[Dict[str, Any]] = []
        for a in accounts:
            all_matches.extend(a.get("typologies") or [])
        if all_matches:
            all_matches.sort(key=lambda m: float(m.get("confidence") or 0), reverse=True)
            evidence["typology"] = {"matches": all_matches}

    # Drift — run on the top owned account (or the highest scorer).
    drift_targets = [a.get("account_id") for a in accounts[:1] if a.get("account_id")]
    for acct_id in drift_targets:
        try:
            drift_resp = drift_engine.analyze(transactions, account_id=acct_id)
        except Exception:
            drift_resp = None
        if drift_resp and drift_resp.get("scope") == "single":
            r = drift_resp.get("report") or drift_resp
            evidence["drift"] = {
                "overall": r.get("overall"),
                "verdict": r.get("verdict"),
                "change_point": r.get("change_point"),
                "drivers": [
                    {"key": d.get("key"), "label": d.get("label"),
                     "score": d.get("score"), "contribution": d.get("contribution")}
                    for d in (r.get("dimensions") or [])[:5]
                ],
            }
        break

    # Network — run the propagation pipeline; lift = network − solo for the owned account.
    if accounts:
        try:
            net = network_engine.analyze(transactions)
        except Exception:
            net = None
        if net:
            owned_id = accounts[0].get("account_id")
            ents = net.get("entities") or []
            ent = next(
                (
                    e for e in ents
                    if owned_id in (e.get("members") or [])
                    or e.get("id") == owned_id
                    or e.get("entity_id") == owned_id
                ),
                None,
            )
            if ent:
                evidence["network"] = {
                    "solo_risk": ent.get("solo_risk") or accounts[0].get("risk_score"),
                    "network_risk": ent.get("network_risk"),
                    "peer_count": len(ent.get("counterparties") or []),
                }
    return evidence


# ---------------------------------------------------------------------------
# Persistence — SQLite. Two tables, idempotent migration, WAL mode.
# ---------------------------------------------------------------------------

_HERE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get(
    "TITAN_PROFILES_DB_PATH",
    os.path.join(_HERE, "data", "profiles.sqlite3"),
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS customer_profiles (
    customer_id      TEXT PRIMARY KEY,
    display_name     TEXT,
    customer_type    TEXT,
    domicile         TEXT,
    pep              INTEGER NOT NULL DEFAULT 0,
    products_json    TEXT,
    kyc_anchor       TEXT,
    composite        REAL NOT NULL,
    engine_composite REAL NOT NULL,
    bucket           TEXT NOT NULL,
    engine_bucket    TEXT NOT NULL,
    kyc_due          TEXT,
    refresh_label    TEXT,
    factors_json     TEXT NOT NULL,
    modifiers_json   TEXT NOT NULL,
    evidence_json    TEXT,
    override_json    TEXT,
    narrative        TEXT,
    last_refreshed_at REAL NOT NULL,
    refreshed_by     TEXT
);

CREATE INDEX IF NOT EXISTS idx_profiles_bucket    ON customer_profiles(bucket);
CREATE INDEX IF NOT EXISTS idx_profiles_refresh   ON customer_profiles(last_refreshed_at DESC);
CREATE INDEX IF NOT EXISTS idx_profiles_due       ON customer_profiles(kyc_due);

CREATE TABLE IF NOT EXISTS profile_history (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id      TEXT NOT NULL REFERENCES customer_profiles(customer_id) ON DELETE CASCADE,
    composite        REAL NOT NULL,
    engine_composite REAL NOT NULL,
    bucket           TEXT NOT NULL,
    refresh_kind     TEXT NOT NULL,  -- refresh | override | clear_override | seed
    override_json    TEXT,
    actor            TEXT,
    note             TEXT,
    refreshed_at     REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_history_customer ON profile_history(customer_id, refreshed_at DESC);
"""

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


def _profile_to_row(profile: Dict[str, Any], *, refreshed_by: str) -> Dict[str, Any]:
    customer = profile["customer"]
    return {
        "customer_id":      customer["customer_id"],
        "display_name":     customer.get("display_name"),
        "customer_type":    customer.get("customer_type"),
        "domicile":         customer.get("domicile"),
        "pep":              1 if customer.get("pep") else 0,
        "products_json":    json.dumps(customer.get("products") or []),
        "kyc_anchor":       profile.get("kyc_anchor"),
        "composite":        float(profile["composite"]),
        "engine_composite": float(profile["engine_composite"]),
        "bucket":           profile["bucket"],
        "engine_bucket":    profile["engine_bucket"],
        "kyc_due":          profile.get("kyc_due"),
        "refresh_label":    (profile.get("refresh") or {}).get("label"),
        "factors_json":     json.dumps(profile.get("factors") or []),
        "modifiers_json":   json.dumps(profile.get("modifiers") or []),
        "evidence_json":    json.dumps(profile.get("evidence") or {}),
        "override_json":    json.dumps(profile.get("override")) if profile.get("override") else None,
        "narrative":        profile.get("narrative"),
        "last_refreshed_at": _epoch(profile.get("computed_at")),
        "refreshed_by":     refreshed_by,
    }


def _epoch(iso: Optional[str]) -> float:
    if not iso:
        return datetime.now(timezone.utc).timestamp()
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return datetime.now(timezone.utc).timestamp()


def upsert_profile(
    customer: Dict[str, Any],
    evidence: Optional[Dict[str, Any]] = None,
    *,
    weights_override: Optional[Dict[str, Any]] = None,
    refreshed_by: str = "TITAN-AUTOMATED",
    refresh_kind: str = "refresh",
    note: Optional[str] = None,
    keep_override: bool = True,
) -> Dict[str, Any]:
    """Compute + persist + append a history row. Returns the persisted profile."""

    override = None
    if keep_override:
        existing = get_profile(customer["customer_id"])
        if existing and existing.get("override"):
            ov = existing["override"]
            expires = ov.get("expires_iso")
            if expires:
                try:
                    if datetime.fromisoformat(expires.replace("Z", "+00:00")) < datetime.now(timezone.utc):
                        ov = None
                except ValueError:
                    pass
            override = ov

    profile = compute_profile(
        customer, evidence=evidence,
        weights_override=weights_override, override=override,
    )
    profile["evidence"] = evidence or {}
    row = _profile_to_row(profile, refreshed_by=refreshed_by)
    cols = ", ".join(row.keys())
    placeholders = ", ".join("?" for _ in row)
    update_cols = ", ".join(f"{k}=excluded.{k}" for k in row.keys() if k != "customer_id")
    sql = (
        f"INSERT INTO customer_profiles ({cols}) VALUES ({placeholders}) "
        f"ON CONFLICT(customer_id) DO UPDATE SET {update_cols}"
    )
    conn = _connect()
    try:
        conn.execute(sql, list(row.values()))
        conn.execute(
            "INSERT INTO profile_history "
            "(customer_id, composite, engine_composite, bucket, refresh_kind, override_json, actor, note, refreshed_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                row["customer_id"], row["composite"], row["engine_composite"], row["bucket"],
                refresh_kind, row["override_json"], refreshed_by, note,
                row["last_refreshed_at"],
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return get_profile(row["customer_id"]) or profile


def get_profile(customer_id: str, *, with_history: bool = True) -> Optional[Dict[str, Any]]:
    conn = _connect()
    try:
        r = conn.execute(
            "SELECT * FROM customer_profiles WHERE customer_id = ?", (customer_id,),
        ).fetchone()
        if not r:
            return None
        out = _row_to_profile(dict(r))
        if with_history:
            hist = conn.execute(
                "SELECT id, composite, engine_composite, bucket, refresh_kind, override_json, actor, note, refreshed_at "
                "FROM profile_history WHERE customer_id = ? ORDER BY refreshed_at DESC LIMIT 64",
                (customer_id,),
            ).fetchall()
            out["history"] = [
                {
                    "id": h["id"],
                    "composite": round(float(h["composite"]), 1),
                    "engine_composite": round(float(h["engine_composite"]), 1),
                    "bucket": h["bucket"],
                    "refresh_kind": h["refresh_kind"],
                    "override": json.loads(h["override_json"]) if h["override_json"] else None,
                    "actor": h["actor"],
                    "note": h["note"],
                    "refreshed_at": datetime.fromtimestamp(h["refreshed_at"], tz=timezone.utc).isoformat(),
                }
                for h in hist
            ]
        return out
    finally:
        conn.close()


def _row_to_profile(row: Dict[str, Any]) -> Dict[str, Any]:
    factors = json.loads(row.get("factors_json") or "[]")
    modifiers = json.loads(row.get("modifiers_json") or "[]")
    evidence = json.loads(row.get("evidence_json") or "{}")
    override = json.loads(row.get("override_json")) if row.get("override_json") else None
    kyc_due = row.get("kyc_due")
    refresh = refresh_status(kyc_due)
    bucket = row["bucket"]
    return {
        "engine": ENGINE_VERSION,
        "rules_version": RULES_VERSION,
        "computed_at": datetime.fromtimestamp(row["last_refreshed_at"], tz=timezone.utc).isoformat(),
        "customer": {
            "customer_id":   row["customer_id"],
            "display_name":  row.get("display_name"),
            "customer_type": row.get("customer_type"),
            "domicile":      row.get("domicile"),
            "pep":           bool(row.get("pep")),
            "products":      json.loads(row.get("products_json") or "[]"),
            "kyc_anchor":    row.get("kyc_anchor"),
        },
        "engine_composite": round(float(row["engine_composite"]), 1),
        "engine_bucket":    row.get("engine_bucket") or bucket,
        "composite":        round(float(row["composite"]), 1),
        "bucket":           bucket,
        "bucket_accent":    BUCKET_META.get(bucket, {}).get("accent", "#94a3b8"),
        "bucket_blurb":     BUCKET_META.get(bucket, {}).get("blurb", ""),
        "recommended_action": BUCKET_META.get(bucket, {}).get("action", ""),
        "factors":          factors,
        "modifiers":        modifiers,
        "modifier_total":   round(sum(float(m.get("points") or 0) for m in modifiers), 2),
        "weights":          dict(WEIGHTS),
        "kyc_anchor":       row.get("kyc_anchor"),
        "kyc_due":          kyc_due,
        "refresh":          refresh,
        "narrative":        row.get("narrative"),
        "evidence":         evidence,
        "override":         override,
        "refreshed_by":     row.get("refreshed_by"),
    }


def list_profiles(
    *,
    bucket: Optional[str] = None,
    refresh_label: Optional[str] = None,
    domicile: Optional[str] = None,
    q: Optional[str] = None,
    limit: int = 200,
    offset: int = 0,
) -> Dict[str, Any]:
    where: List[str] = []
    params: List[Any] = []
    if bucket:
        where.append("bucket = ?")
        params.append(bucket)
    if refresh_label:
        where.append("refresh_label = ?")
        params.append(refresh_label)
    if domicile:
        where.append("domicile = ?")
        params.append(domicile.upper())
    if q:
        where.append("(LOWER(display_name) LIKE ? OR LOWER(customer_id) LIKE ?)")
        params.extend([f"%{q.lower()}%", f"%{q.lower()}%"])
    where_clause = ("WHERE " + " AND ".join(where)) if where else ""
    conn = _connect()
    try:
        total = conn.execute(f"SELECT COUNT(*) FROM customer_profiles {where_clause}", params).fetchone()[0]
        rows = conn.execute(
            f"SELECT * FROM customer_profiles {where_clause} "
            f"ORDER BY composite DESC LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()
        rebuilt: List[Dict[str, Any]] = []
        for r in rows:
            d = dict(r)
            # Refresh the live status — anchor is persisted but `current/due_soon/overdue`
            # is now-relative.
            d["refresh_label"] = refresh_status(d.get("kyc_due")).get("label") or d.get("refresh_label")
            rebuilt.append(_row_to_profile(d))
        return {"total": total, "count": len(rebuilt), "limit": limit, "offset": offset, "profiles": rebuilt}
    finally:
        conn.close()


def set_override(
    customer_id: str,
    *,
    locked_bucket: str,
    justification: str,
    actor: str,
    expires_iso: Optional[str] = None,
) -> Dict[str, Any]:
    locked = (locked_bucket or "").lower()
    if locked not in REFRESH_DAYS:
        raise ValueError(f"locked_bucket must be one of {list(REFRESH_DAYS)}")
    if not (justification or "").strip():
        raise ValueError("justification is required")
    profile = get_profile(customer_id)
    if not profile:
        raise KeyError("customer not found")
    override = {
        "locked_bucket": locked,
        "justification": justification.strip(),
        "actor": actor,
        "set_at": datetime.now(timezone.utc).isoformat(),
        "expires_iso": expires_iso,
    }
    profile["override"] = override
    customer = profile["customer"]
    evidence = profile.get("evidence") or {}
    recomputed = compute_profile(
        customer,
        evidence=evidence,
        override=override,
    )
    recomputed["evidence"] = evidence
    row = _profile_to_row(recomputed, refreshed_by=actor)
    conn = _connect()
    try:
        cols = ", ".join(row.keys())
        placeholders = ", ".join("?" for _ in row)
        update_cols = ", ".join(f"{k}=excluded.{k}" for k in row.keys() if k != "customer_id")
        conn.execute(
            f"INSERT INTO customer_profiles ({cols}) VALUES ({placeholders}) "
            f"ON CONFLICT(customer_id) DO UPDATE SET {update_cols}",
            list(row.values()),
        )
        conn.execute(
            "INSERT INTO profile_history "
            "(customer_id, composite, engine_composite, bucket, refresh_kind, override_json, actor, note, refreshed_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                customer_id, row["composite"], row["engine_composite"], row["bucket"],
                "override", row["override_json"], actor, justification.strip()[:300],
                row["last_refreshed_at"],
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return get_profile(customer_id) or recomputed


def clear_override(customer_id: str, *, actor: str, note: Optional[str] = None) -> Dict[str, Any]:
    profile = get_profile(customer_id)
    if not profile:
        raise KeyError("customer not found")
    if not profile.get("override"):
        return profile
    customer = profile["customer"]
    evidence = profile.get("evidence") or {}
    recomputed = compute_profile(customer, evidence=evidence)
    recomputed["evidence"] = evidence
    row = _profile_to_row(recomputed, refreshed_by=actor)
    conn = _connect()
    try:
        cols = ", ".join(row.keys())
        placeholders = ", ".join("?" for _ in row)
        update_cols = ", ".join(f"{k}=excluded.{k}" for k in row.keys() if k != "customer_id")
        conn.execute(
            f"INSERT INTO customer_profiles ({cols}) VALUES ({placeholders}) "
            f"ON CONFLICT(customer_id) DO UPDATE SET {update_cols}",
            list(row.values()),
        )
        conn.execute(
            "INSERT INTO profile_history "
            "(customer_id, composite, engine_composite, bucket, refresh_kind, override_json, actor, note, refreshed_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                customer_id, row["composite"], row["engine_composite"], row["bucket"],
                "clear_override", None, actor, note,
                row["last_refreshed_at"],
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return get_profile(customer_id) or recomputed


def portfolio_stats() -> Dict[str, Any]:
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT bucket, refresh_label, composite, domicile, kyc_due FROM customer_profiles"
        ).fetchall()
    finally:
        conn.close()
    if not rows:
        return {
            "total": 0,
            "by_bucket": {b: 0 for b in ("low", "medium", "high", "critical")},
            "by_refresh": {"current": 0, "due_soon": 0, "overdue": 0, "unscheduled": 0},
            "by_domicile": {},
            "average_composite": 0.0,
            "highest_composite": 0.0,
            "due_within_30d": 0,
            "overdue_count": 0,
        }
    now = datetime.now(timezone.utc)
    by_bucket: Dict[str, int] = {"low": 0, "medium": 0, "high": 0, "critical": 0}
    by_refresh: Dict[str, int] = {"current": 0, "due_soon": 0, "overdue": 0, "unscheduled": 0}
    by_domicile: Dict[str, int] = {}
    composites: List[float] = []
    due_within: int = 0
    overdue: int = 0
    for r in rows:
        b = r["bucket"] or "low"
        by_bucket[b] = by_bucket.get(b, 0) + 1
        status = refresh_status(r["kyc_due"], now=now)
        label = status.get("label") or "unscheduled"
        by_refresh[label] = by_refresh.get(label, 0) + 1
        if label == "due_soon":
            due_within += 1
        if label == "overdue":
            overdue += 1
        dom = (r["domicile"] or "").upper() or "—"
        by_domicile[dom] = by_domicile.get(dom, 0) + 1
        composites.append(float(r["composite"] or 0))
    avg = sum(composites) / len(composites) if composites else 0.0
    return {
        "total": len(rows),
        "by_bucket": by_bucket,
        "by_refresh": by_refresh,
        "by_domicile": dict(sorted(by_domicile.items(), key=lambda kv: -kv[1])),
        "average_composite": round(avg, 1),
        "highest_composite": round(max(composites), 1) if composites else 0.0,
        "due_within_30d": due_within,
        "overdue_count": overdue,
    }


def delete_profile(customer_id: str) -> bool:
    conn = _connect()
    try:
        cur = conn.execute("DELETE FROM customer_profiles WHERE customer_id = ?", (customer_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Rules / sample
# ---------------------------------------------------------------------------


def get_rules() -> Dict[str, Any]:
    return {
        "version": RULES_VERSION,
        "engine": ENGINE_VERSION,
        "weights": dict(WEIGHTS),
        "surface_order": list(SURFACE_ORDER),
        "surfaces": [
            {"key": k, **SURFACE_META[k], "weight": WEIGHTS[k]}
            for k in SURFACE_ORDER
        ],
        "buckets": [
            {"label": label, "min": floor, "max": (
                BUCKETS[i - 1][0] - 0.1 if i > 0 else 100.0
            )}
            for i, (floor, label) in enumerate(sorted(BUCKETS, key=lambda x: x[0]))
        ],
        "bucket_meta": BUCKET_META,
        "refresh_days": dict(REFRESH_DAYS),
        "due_soon_days": DUE_SOON_DAYS,
        "modifiers": {
            "geo_modifier": GEO_MODIFIER,
            "pep_modifier": PEP_MODIFIER,
            "high_risk_product_modifier": HIGH_RISK_PRODUCT_MODIFIER,
            "modifier_cap": MODIFIER_CAP,
            "high_risk_geos": sorted(HIGH_RISK_GEOS),
            "high_risk_products": sorted(HIGH_RISK_PRODUCTS),
        },
        "typology_severity_multipliers": dict(TYPOLOGY_SEVERITY_MULT),
    }


_SAMPLE_PATH = os.path.join(_HERE, "data", "customers.json")


def get_sample() -> Dict[str, Any]:
    with open(_SAMPLE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def seed_sample(*, force: bool = False) -> Dict[str, Any]:
    """Persist the bundled customer book into the SQLite store. Idempotent:
    if a customer_id already exists and ``force=False``, it's skipped.

    Returns a count payload the API can echo back to the analyst.
    """
    sample = get_sample()
    created, refreshed, skipped = 0, 0, 0
    for entry in sample.get("customers", []):
        cid = entry["customer"]["customer_id"]
        if not force and get_profile(cid, with_history=False):
            skipped += 1
            continue
        existed = get_profile(cid, with_history=False) is not None
        upsert_profile(
            entry["customer"],
            evidence=entry.get("evidence") or {},
            refreshed_by=entry.get("refreshed_by") or "TITAN-SEED",
            refresh_kind="seed",
            note="Seeded from bundled customer book.",
            keep_override=False,
        )
        if existed:
            refreshed += 1
        else:
            created += 1
    return {
        "ok": True,
        "created": created,
        "refreshed": refreshed,
        "skipped": skipped,
        "total_in_sample": len(sample.get("customers", [])),
    }
