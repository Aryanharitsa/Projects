"""Offer Studio engine — Python mirror of frontend/src/lib/offer.ts.

Three concerns:

  1. Deterministic compensation benchmarking (P25/P50/P75/P90 base bands,
     equity bands, sign-on, target bonus) derived from the parsed JD plan
     and the candidate's matched-skill set.
  2. An explainable logistic win-probability model — every factor is
     reported with its contribution so the recruiter can reason about
     slider moves.
  3. A Markdown offer-letter composer.

Pure functions; no I/O. Output shape mirrors the TS engine.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal


Currency = Literal["INR", "USD"]
Unit = Literal["LPA", "annual"]
Band = Literal["long_shot", "uphill", "coin_flip", "likely", "lock"]


SENIORITY_BASE_INR_P50: dict[str, float] = {
    "intern": 6,
    "junior": 14,
    "mid": 26,
    "senior": 48,
    "staff": 82,
    "principal": 135,
    "lead": 70,
}
SENIORITY_BONUS_PCT: dict[str, float] = {
    "intern": 0, "junior": 5, "mid": 8, "senior": 12,
    "staff": 15, "principal": 18, "lead": 12,
}
SENIORITY_EQUITY_PCT: dict[str, tuple[float, float, float]] = {
    "intern": (0, 0, 0),
    "junior": (0.01, 0.02, 0.04),
    "mid": (0.04, 0.07, 0.12),
    "senior": (0.10, 0.18, 0.30),
    "staff": (0.25, 0.40, 0.65),
    "principal": (0.50, 0.90, 1.40),
    "lead": (0.18, 0.30, 0.50),
}
CITY_MULT: dict[str, float] = {
    "bengaluru": 1.00, "mumbai": 1.05, "delhi": 0.96, "gurgaon": 0.96,
    "noida": 0.94, "hyderabad": 0.95, "pune": 0.92, "chennai": 0.90,
    "kolkata": 0.82, "ahmedabad": 0.80, "kochi": 0.78,
    "remote": 0.95, "hybrid": 0.97, "onsite": 1.00,
}
RARE_SKILLS = {
    "rust", "kubernetes", "terraform", "pytorch", "kafka", "llm",
    "grpc", "pulsar", "wasm",
}
MODERN_SKILLS = {
    "typescript", "fastapi", "next.js", "gcp", "aws", "mongodb", "postgres",
    "react", "svelte", "go", "graphql", "redis",
}


@dataclass
class CompBand:
    p25: int
    p50: int
    p75: int
    p90: int
    currency: Currency = "INR"
    unit: Unit = "LPA"

    def as_dict(self) -> dict:
        return {
            "p25": self.p25, "p50": self.p50, "p75": self.p75, "p90": self.p90,
            "currency": self.currency, "unit": self.unit,
        }


@dataclass
class EquityBand:
    pct_p25: float
    pct_p50: float
    pct_p75: float

    def as_dict(self) -> dict:
        return {
            "pct_p25": self.pct_p25,
            "pct_p50": self.pct_p50,
            "pct_p75": self.pct_p75,
        }


@dataclass
class CompBenchmark:
    base: CompBand
    equity: EquityBand
    target_bonus_pct: float
    sign_on_suggested: int
    seniority: str
    location: str
    citymult: float
    skill_premium: float
    rationale: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "base": self.base.as_dict(),
            "equity": self.equity.as_dict(),
            "targetBonusPct": self.target_bonus_pct,
            "signOnSuggested": self.sign_on_suggested,
            "seniority": self.seniority,
            "location": self.location,
            "citymult": self.citymult,
            "skillPremium": self.skill_premium,
            "rationale": list(self.rationale),
        }


@dataclass
class OfferDraft:
    base: float
    equity_pct: float
    target_bonus_pct: float
    sign_on: float
    vesting_years: int = 4
    cliff_months: int = 12
    start_date: str | None = None
    expires_on: str | None = None
    notes: str | None = None

    def as_dict(self) -> dict:
        return {
            "base": self.base,
            "equityPct": self.equity_pct,
            "targetBonusPct": self.target_bonus_pct,
            "signOn": self.sign_on,
            "vestingYears": self.vesting_years,
            "cliffMonths": self.cliff_months,
            "startDate": self.start_date,
            "expiresOn": self.expires_on,
            "notes": self.notes,
        }


@dataclass
class WinFactor:
    key: str
    label: str
    delta: float

    def as_dict(self) -> dict:
        return {"key": self.key, "label": self.label, "delta": self.delta}


@dataclass
class WinProbability:
    probability: float
    logit: float
    band: Band
    factors: list[WinFactor]

    def as_dict(self) -> dict:
        return {
            "probability": self.probability,
            "logit": self.logit,
            "band": self.band,
            "factors": [f.as_dict() for f in self.factors],
        }


# ---------- comp ----------

def citymult(location: str | None) -> tuple[float, str]:
    if not location:
        return 0.90, "unknown"
    k = location.lower().strip()
    if k in CITY_MULT:
        return CITY_MULT[k], k
    return 0.90, k


def skill_premium(matched: list[str]) -> tuple[float, list[str], list[str]]:
    rare = [s for s in matched if s in RARE_SKILLS]
    modern = [s for s in matched if s in MODERN_SKILLS and s not in RARE_SKILLS]
    raw = len(rare) * 0.04 + len(modern) * 0.015
    return round(min(0.20, raw), 3), rare, modern


def _band_spread(p50: float) -> tuple[int, int, int]:
    return (
        int(round(p50 * 0.82)),
        int(round(p50 * 1.18)),
        int(round(p50 * 1.36)),
    )


def benchmark_comp(
    seniority: str | None,
    location: str | None,
    matched_skills: list[str],
    currency: Currency = "INR",
) -> CompBenchmark:
    sen_key = seniority if (seniority or "") in SENIORITY_BASE_INR_P50 else "mid"
    base_p50_anchor = SENIORITY_BASE_INR_P50[sen_key]
    cmult, ckey = citymult(location)
    premium, rare, modern = skill_premium(matched_skills)
    p50 = int(round(base_p50_anchor * cmult * (1 + premium)))
    p25, p75, p90 = _band_spread(p50)
    eq_p25, eq_p50, eq_p75 = SENIORITY_EQUITY_PCT[sen_key]
    bonus = SENIORITY_BONUS_PCT[sen_key]
    sign_on_suggested = max(0, min(
        int(round(p50 * 0.12)),
        int(round((p75 - p50) * 0.5)),
    ))

    rationale: list[str] = [
        f"Seniority anchor: {sen_key} → P50 {base_p50_anchor} LPA (Bengaluru-normalised).",
        f"Location multiplier ({ckey}): ×{cmult:.2f}.",
    ]
    if rare:
        rationale.append(f"Rare-skill premium: {', '.join(rare)} → +{len(rare) * 4}%.")
    if modern:
        rationale.append(f"Modern-stack premium: {', '.join(modern)} → +{len(modern) * 1.5:.1f}%.")
    if not rare and not modern:
        rationale.append(f"No skill premium ({len(matched_skills)} matched).")
    rationale.append("Suggested sign-on covers ~50% of the P50→P75 gap.")

    return CompBenchmark(
        base=CompBand(p25=p25, p50=p50, p75=p75, p90=p90, currency=currency, unit="LPA"),
        equity=EquityBand(pct_p25=eq_p25, pct_p50=eq_p50, pct_p75=eq_p75),
        target_bonus_pct=bonus,
        sign_on_suggested=sign_on_suggested,
        seniority=sen_key,
        location=ckey,
        citymult=cmult,
        skill_premium=premium,
        rationale=rationale,
    )


def suggest_draft(b: CompBenchmark) -> OfferDraft:
    return OfferDraft(
        base=b.base.p50,
        equity_pct=b.equity.pct_p50,
        target_bonus_pct=b.target_bonus_pct,
        sign_on=b.sign_on_suggested,
    )


def band_position(o: OfferDraft, b: CompBenchmark) -> float:
    span = b.base.p90 - b.base.p25
    if span <= 0:
        return 0.5
    return (o.base - b.base.p25) / span


# ---------- win probability ----------

def _sigmoid(x: float) -> float:
    if x > 16:
        return 1.0
    if x < -16:
        return 0.0
    return 1.0 / (1.0 + math.exp(-x))


def _band_for(p: float) -> Band:
    if p >= 0.85:
        return "lock"
    if p >= 0.65:
        return "likely"
    if p >= 0.45:
        return "coin_flip"
    if p >= 0.25:
        return "uphill"
    return "long_shot"


def win_probability(
    offer: OfferDraft,
    benchmark: CompBenchmark,
    *,
    composite: int | None,
    match_score: int,
    matched_skills: list[str],
    days_since_outreach: int | None = None,
    thin_data: bool = False,
    low_confidence: bool = False,
) -> WinProbability:
    factors: list[WinFactor] = []
    factors.append(WinFactor("baseline", "Baseline conversion", -0.6))

    base_ratio = offer.base / max(1, benchmark.base.p50) - 1
    factors.append(WinFactor(
        "base_pull",
        f"Base vs P50 ({base_ratio * 100:.0f}%)",
        round(3.5 * base_ratio, 2),
    ))

    eq_p50 = max(0.001, benchmark.equity.pct_p50)
    eq_ratio = offer.equity_pct / eq_p50 - 1
    factors.append(WinFactor(
        "equity_pull",
        f"Equity vs P50 ({eq_ratio * 100:.0f}%)",
        round(0.8 * eq_ratio, 2),
    ))

    sign_on_ratio = offer.sign_on / max(1, offer.base)
    if sign_on_ratio > 0:
        factors.append(WinFactor(
            "signon",
            f"Sign-on ({sign_on_ratio * 100:.0f}% of base)",
            round(1.8 * sign_on_ratio, 2),
        ))

    bonus_delta = (offer.target_bonus_pct - benchmark.target_bonus_pct) / 100
    if abs(bonus_delta) > 0.005:
        factors.append(WinFactor(
            "bonus",
            f"Target bonus ({bonus_delta * 100:.0f}pp vs market)",
            round(1.2 * bonus_delta, 2),
        ))

    _, rare, _ = skill_premium(matched_skills)
    composite_demand = 0.45 if (composite is not None and composite >= 80) else 0.0
    demand = len(rare) * 0.18 + composite_demand
    if demand > 0:
        label = (
            f"External demand ({len(rare)} rare skill{'s' if len(rare) != 1 else ''}"
            f"{' · top tier' if composite_demand else ''})"
            if rare else "External demand (top tier candidate)"
        )
        factors.append(WinFactor("demand", label, round(-demand, 2)))

    if composite is not None:
        credibility = (composite - 60) / 100
        factors.append(WinFactor(
            "credibility",
            f"Pitch credibility (composite {composite})",
            round(0.4 * credibility, 2),
        ))

    if days_since_outreach is not None:
        decay = -max(0, days_since_outreach - 7) / 7 * 0.2
        if decay < 0:
            factors.append(WinFactor(
                "momentum",
                f"Outreach momentum ({days_since_outreach}d old)",
                round(decay, 2),
            ))

    if thin_data:
        factors.append(WinFactor("thin_data", "Thin interview data", -0.5))
    elif low_confidence:
        factors.append(WinFactor("low_confidence", "Low interview confidence", -0.25))

    match_pull = (match_score - 60) / 200
    if abs(match_pull) > 0.01:
        factors.append(WinFactor(
            "match", f"Match score {match_score}", round(match_pull, 2),
        ))

    logit = sum(f.delta for f in factors)
    prob = _sigmoid(logit)

    non_base = sorted(
        (f for f in factors if f.key != "baseline"),
        key=lambda f: abs(f.delta),
        reverse=True,
    )
    baseline = next(f for f in factors if f.key == "baseline")
    return WinProbability(
        probability=prob,
        logit=round(logit, 3),
        band=_band_for(prob),
        factors=non_base + [baseline],
    )


# ---------- offer letter ----------

def _fmt(n: float, unit: Unit, currency: Currency) -> str:
    if currency == "USD":
        return f"${int(n):,} {unit}"
    if unit == "LPA":
        return f"₹{_inr_fmt(int(n))} LPA"
    return f"₹{_inr_fmt(int(n))} / yr"


def _inr_fmt(n: int) -> str:
    """Indian numbering system thousands separator (1,23,456)."""
    s = str(abs(n))
    if len(s) <= 3:
        return ("-" if n < 0 else "") + s
    head, tail = s[:-3], s[-3:]
    pairs = []
    while len(head) > 2:
        pairs.insert(0, head[-2:])
        head = head[:-2]
    if head:
        pairs.insert(0, head)
    return ("-" if n < 0 else "") + ",".join(pairs) + "," + tail


def _describe_band_position(pos: float) -> str:
    if pos < 0:
        return "below P25 — below market"
    if pos < 0.25:
        return "P25 — entry of band"
    if pos < 0.55:
        return "P50 — middle of band"
    if pos < 0.85:
        return "P75 — top quartile"
    if pos <= 1:
        return "P90 — top tail"
    return "above P90 — premium"


def build_offer_letter(
    *,
    company_name: str,
    hiring_manager: str | None,
    candidate_name: str,
    role_name: str,
    location: str,
    offer: OfferDraft,
    benchmark: CompBenchmark,
) -> str:
    lines: list[str] = []
    lines.append(f"# Offer of Employment — {role_name}")
    lines.append("")
    lines.append(f"**{company_name}**")
    if hiring_manager:
        lines.append(f"Hiring manager: {hiring_manager}")
    lines.append("")
    first = candidate_name.split()[0] if candidate_name else "there"
    lines.append(f"Dear {first},")
    lines.append("")
    lines.append(
        f"We're delighted to extend an offer for the role of **{role_name}** at "
        f"{company_name}, based in {location}. Below are the proposed terms — "
        f"please review and respond by {offer.expires_on or 'the agreed date'}."
    )
    lines.append("")
    lines.append("## Compensation")
    lines.append("")
    lines.append("| Item | Value |")
    lines.append("|---|---|")
    lines.append(f"| Base salary | {_fmt(offer.base, benchmark.base.unit, benchmark.base.currency)} |")
    lines.append(f"| Target performance bonus | {offer.target_bonus_pct:.0f}% of base |")
    if offer.sign_on > 0:
        lines.append(
            f"| Sign-on bonus | "
            f"{_fmt(offer.sign_on, benchmark.base.unit, benchmark.base.currency)} (paid on join) |"
        )
    lines.append(f"| Equity grant | {offer.equity_pct:.3f}% of fully-diluted capitalisation |")
    lines.append(
        f"| Vesting | {offer.vesting_years} years, {offer.cliff_months}-month cliff, monthly thereafter |"
    )
    if offer.start_date:
        lines.append(f"| Proposed start date | {offer.start_date} |")
    lines.append("")
    lines.append("## Benchmarking note")
    lines.append("")
    pos = band_position(offer, benchmark)
    lines.append(
        f"This package sits at the **{_describe_band_position(pos)}** of the "
        f"{benchmark.seniority} band for {benchmark.location}."
    )
    lines.append(
        f"(Band: P25 {_fmt(benchmark.base.p25, benchmark.base.unit, benchmark.base.currency)} · "
        f"P50 {_fmt(benchmark.base.p50, benchmark.base.unit, benchmark.base.currency)} · "
        f"P75 {_fmt(benchmark.base.p75, benchmark.base.unit, benchmark.base.currency)} · "
        f"P90 {_fmt(benchmark.base.p90, benchmark.base.unit, benchmark.base.currency)}.)"
    )
    lines.append("")
    if offer.notes and offer.notes.strip():
        lines.append("## Notes")
        lines.append("")
        lines.append(offer.notes.strip())
        lines.append("")
    lines.append("## Next steps")
    lines.append("")
    lines.append(
        "Reply to this email with any questions; once confirmed, we'll send the "
        "formal employment contract along with onboarding documentation. We're "
        "looking forward to working with you."
    )
    lines.append("")
    lines.append("Warm regards,")
    lines.append(hiring_manager or f"The {company_name} team")
    return "\n".join(lines)
