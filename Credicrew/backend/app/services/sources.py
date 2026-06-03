"""Sourcing Intelligence — Python mirror of frontend/src/lib/sources.ts.

Attributes every shortlisted candidate to a *channel* (LinkedIn outreach,
employee referral, job post, agency, community, university, AI sourcing,
silver medal) and rolls the existing pipeline + interview + offer + accept-
probability signals back up to per-channel ROI.

Output is camelCase-friendly so the TS engine and this engine emit
byte-identical payloads for the same input.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

CHANNELS = [
    "linkedin_outreach",
    "referral",
    "job_post",
    "agency",
    "community",
    "university",
    "ai_sourcing",
    "silver_medal",
]

CHANNEL_LABEL = {
    "linkedin_outreach": "LinkedIn outreach",
    "referral": "Employee referral",
    "job_post": "Job post (inbound)",
    "agency": "Recruiter agency",
    "community": "Community / event",
    "university": "University pipeline",
    "ai_sourcing": "AI sourcing",
    "silver_medal": "Silver medal",
}

CHANNEL_BLURB = {
    "linkedin_outreach": "Cold outbound to passive candidates on LinkedIn.",
    "referral": "Employees nominate someone in their network.",
    "job_post": "Direct applications to a posted JD.",
    "agency": "External recruiter delivers a shortlist for a fee.",
    "community": "Talent met at meetups, conferences, hackathons, Slack.",
    "university": "New-grad / intern channel from campus partners.",
    "ai_sourcing": "Auto-scraped candidates from public engineering signal.",
    "silver_medal": "Strong previous-loop runner-ups recycled into a new req.",
}

DEFAULT_COST_PER_CANDIDATE = {
    "linkedin_outreach": 4.0,
    "referral": 8.0,
    "job_post": 1.0,
    "agency": 60.0,
    "community": 2.0,
    "university": 3.0,
    "ai_sourcing": 2.0,
    "silver_medal": 1.0,
}

STAGE_KEYS = ["new", "outreach", "screening", "interview", "offer"]
STAGE_RANK = {"new": 0, "outreach": 1, "screening": 2, "interview": 3, "offer": 4, "passed": -1}

BAND_LABEL = {
    "scale": "Scale — double down",
    "steady": "Steady — keep running",
    "experiment": "Experiment — needs more data",
    "cut": "Cut — reallocate budget",
}

DAY_MS = 86_400_000


@dataclass
class SourceAttribution:
    channel: str
    detail: Optional[str] = None
    cost_override: Optional[float] = None


@dataclass
class SourceCandidate:
    candidate_id: int
    name: str
    role_id: str
    role_name: str
    status: str
    added_at: int
    match_score: float
    composite: Optional[float]
    confidence: float
    source: SourceAttribution
    win_probability: Optional[float] = None
    has_offer: bool = False
    location: Optional[str] = None


@dataclass
class SourceInput:
    candidates: list[SourceCandidate] = field(default_factory=list)
    cost_overrides: dict[str, float] = field(default_factory=dict)
    now: Optional[int] = None


# ---------- math helpers ----------


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _safe_mean(xs: list[float]) -> Optional[float]:
    if not xs:
        return None
    return sum(xs) / len(xs)


def _round1(x: float) -> float:
    return round(float(x), 1)


def _round2(x: float) -> float:
    return round(float(x), 2)


def _conversion_to_score(c: float) -> float:
    return _clip(100.0 * (1.0 - math.exp(-12.0 * c)), 0.0, 100.0)


def _speed_to_score(mean_days: Optional[float]) -> float:
    if mean_days is None:
        return 60.0
    return _clip(120.0 - 2.5 * mean_days, 0.0, 100.0)


def _cost_to_score(cost_per_offer: Optional[float], cost_per_interview: Optional[float]) -> float:
    cpo = cost_per_offer
    if cpo is None and cost_per_interview is not None:
        cpo = cost_per_interview * 3.0
    if cpo is None:
        return 55.0
    return _clip(100.0 - 0.085 * cpo, 0.0, 100.0)


def _band_for(roi: float, count: int) -> str:
    if count < 4:
        return "experiment"
    if roi >= 70:
        return "scale"
    if roi >= 50:
        return "steady"
    if roi >= 35:
        return "experiment"
    return "cut"


def _shannon_norm(counts: list[int]) -> float:
    n = len(counts)
    if n <= 1:
        return 0.0
    total = sum(counts)
    if total <= 0:
        return 0.0
    h = 0.0
    for c in counts:
        if c <= 0:
            continue
        p = c / total
        h -= p * math.log(p)
    return h / math.log(n)


def _top_n_cells(items: dict[str, int], n: int, total: int) -> list[dict]:
    arr = sorted(
        [(label, count) for label, count in items.items() if count > 0],
        key=lambda x: -x[1],
    )[:n]
    return [
        {"label": label, "count": count, "share": (count / total if total > 0 else 0.0)}
        for label, count in arr
    ]


# ---------- per-channel recommendation ----------


def _recommend_for(channel: str, s: dict) -> str:
    label = CHANNEL_LABEL.get(channel, channel)
    if s["count"] < 4:
        return f"Too few candidates ({s['count']}) — keep testing {label.lower()} before judging it."
    if s["band"] == "cut":
        if s["cost_score"] < 35 and s["cost_per_offer"] is not None:
            return (
                f"Cost-per-offer ₹{round(s['cost_per_offer'])}k is too high — "
                f"pause {label.lower()} unless quality lifts."
            )
        if s["conversion_score"] < 25:
            return (
                f"Pipeline reaches offer only {s['conversion_score']:.0f} on the conversion dial — "
                "stop investing until top-of-funnel quality improves."
            )
        return "ROI lags every other channel — cut spend and reallocate."
    if s["band"] == "scale":
        if s["quality_score"] >= 75 and s["conversion_score"] >= 65:
            return "Highest-quality + highest-converting channel — double InMail seats / referral bonuses here this quarter."
        return "Above-bar on every dial — scale this channel hard."
    if s["band"] == "steady":
        if s["conversion_score"] < 50:
            return "Solid quality but mid conversion — sharpen the first-touch message before adding volume."
        if s["speed_score"] < 50 and s["mean_days_to_offer"] is not None:
            return f"Quality is fine but cycle time is {round(s['mean_days_to_offer'])} days — fast-track the screening hand-off."
        return "Reliable baseline — keep at current volume."
    return f"Promising but thin — invest in {label.lower()} for one more quarter before deciding."


# ---------- main entry ----------


def analyze_sources(input_: SourceInput) -> dict:
    now = input_.now if input_.now is not None else 0
    overrides = input_.cost_overrides or {}

    buckets: dict[str, list[SourceCandidate]] = {ch: [] for ch in CHANNELS}
    for c in input_.candidates:
        if c.source.channel in buckets:
            buckets[c.source.channel].append(c)

    by_channel: list[dict] = []

    for ch in CHANNELS:
        arr = buckets[ch]
        count = len(arr)
        if count == 0:
            continue

        reached = {k: 0 for k in STAGE_KEYS}
        here = {k: 0 for k in STAGE_KEYS}
        active = 0
        total_days_to_offer = 0.0
        offer_count = 0
        interviewed_count = 0
        composites: list[float] = []
        win_probs: list[float] = []
        matches: list[float] = []
        loc_counts: dict[str, int] = {}

        for c in arr:
            matches.append(c.match_score)
            rank = STAGE_RANK.get(c.status, -1)
            if c.status != "passed":
                active += 1
            if rank >= 0:
                if c.status in here:
                    here[c.status] += 1
                for r in range(0, min(rank, 4) + 1):
                    reached[STAGE_KEYS[r]] += 1
            if c.composite is not None:
                composites.append(c.composite)
                interviewed_count += 1
            if c.has_offer and c.win_probability is not None:
                win_probs.append(c.win_probability)
            if c.status == "offer" or (c.has_offer and c.status != "passed"):
                offer_count += 1
                if now:
                    days = (now - c.added_at) / DAY_MS
                    if 0 <= days <= 180:
                        total_days_to_offer += days
            loc = c.location or "Unknown"
            loc_counts[loc] = loc_counts.get(loc, 0) + 1

        conv = {
            "new": None,
            "outreach": (reached["outreach"] / reached["new"]) if reached["new"] > 0 else None,
            "screening": (reached["screening"] / reached["outreach"]) if reached["outreach"] > 0 else None,
            "interview": (reached["interview"] / reached["screening"]) if reached["screening"] > 0 else None,
            "offer": (reached["offer"] / reached["interview"]) if reached["interview"] > 0 else None,
        }

        mean_match = _safe_mean(matches) or 0.0
        mean_composite = _safe_mean(composites)
        mean_win_prob = _safe_mean(win_probs)
        mean_days_to_offer = (total_days_to_offer / offer_count) if offer_count > 0 and now else None

        cost_per_cand = overrides.get(ch, DEFAULT_COST_PER_CANDIDATE[ch])
        total_spend = count * cost_per_cand
        cost_per_interview = (total_spend / interviewed_count) if interviewed_count > 0 else None
        cost_per_offer = (total_spend / offer_count) if offer_count > 0 else None

        base_q = 0.4 * mean_match
        comp_q = 0.4 * mean_composite if mean_composite is not None else 0.0
        win_q = 20.0 * mean_win_prob if mean_win_prob is not None else 0.0
        if mean_composite is None and mean_win_prob is None:
            quality_score = mean_match
        elif mean_composite is None:
            quality_score = (base_q + win_q) / 0.6
        elif mean_win_prob is None:
            quality_score = (base_q + comp_q) / 0.8
        else:
            quality_score = base_q + comp_q + win_q
        quality_score = _clip(quality_score, 0.0, 100.0)

        conversion_score = _conversion_to_score(reached["offer"] / count)
        speed_score = _speed_to_score(mean_days_to_offer)
        cost_score = _cost_to_score(cost_per_offer, cost_per_interview)

        roi = _clip(
            0.4 * quality_score
            + 0.3 * conversion_score
            + 0.2 * cost_score
            + 0.1 * speed_score,
            0.0,
            100.0,
        )
        band = _band_for(roi, count)
        top_locations = _top_n_cells(loc_counts, 3, count)

        rec_input = {
            "band": band,
            "quality_score": quality_score,
            "conversion_score": conversion_score,
            "cost_score": cost_score,
            "speed_score": speed_score,
            "mean_composite": mean_composite,
            "offer_count": offer_count,
            "count": count,
            "cost_per_offer": cost_per_offer,
            "mean_days_to_offer": mean_days_to_offer,
        }
        recommendation = _recommend_for(ch, rec_input)

        by_channel.append({
            "channel": ch,
            "label": CHANNEL_LABEL[ch],
            "count": count,
            "active": active,
            "reached": reached,
            "conversion": conv,
            "meanMatchScore": _round1(mean_match),
            "meanComposite": None if mean_composite is None else _round1(mean_composite),
            "meanWinProb": None if mean_win_prob is None else _round2(mean_win_prob),
            "meanDaysToOffer": None if mean_days_to_offer is None else _round1(mean_days_to_offer),
            "costPerCandidate": _round1(cost_per_cand),
            "totalSpend": _round1(total_spend),
            "costPerInterview": None if cost_per_interview is None else _round1(cost_per_interview),
            "costPerOffer": None if cost_per_offer is None else _round1(cost_per_offer),
            "qualityScore": _round1(quality_score),
            "conversionScore": _round1(conversion_score),
            "costScore": _round1(cost_score),
            "speedScore": _round1(speed_score),
            "roi": _round1(roi),
            "band": band,
            "topLocations": top_locations,
            "recommendation": recommendation,
        })

    ranked = sorted(by_channel, key=lambda m: -m["roi"])
    eligible = [m for m in ranked if m["count"] >= 4]
    best_channel = eligible[0]["channel"] if eligible else None
    worst_channel = eligible[-1]["channel"] if eligible else None

    total_candidates = sum(m["count"] for m in by_channel)
    total_active = sum(m["active"] for m in by_channel)
    total_spend = _round1(sum(m["totalSpend"] for m in by_channel))
    total_offers = sum(m["reached"]["offer"] for m in by_channel)
    total_interviewed = sum(m["reached"]["interview"] for m in by_channel)
    cost_per_interview = _round1(total_spend / total_interviewed) if total_interviewed > 0 else None
    cost_per_offer = _round1(total_spend / total_offers) if total_offers > 0 else None
    diversification = _round2(_shannon_norm([m["count"] for m in by_channel]))

    recommendations = _build_recommendations(by_channel, ranked)

    return {
        "byChannel": ranked,
        "totalCandidates": total_candidates,
        "totalActive": total_active,
        "totalSpend": total_spend,
        "totalOffers": total_offers,
        "totalInterviewed": total_interviewed,
        "costPerInterview": cost_per_interview,
        "costPerOffer": cost_per_offer,
        "bestChannel": best_channel,
        "worstChannel": (worst_channel if worst_channel != best_channel else None),
        "diversification": diversification,
        "recommendations": recommendations,
    }


def _build_recommendations(all_: list[dict], ranked: list[dict]) -> list[dict]:
    recs: list[dict] = []

    scaleable = [m for m in ranked if m["band"] == "scale"]
    for m in scaleable[:1]:
        offer_pct = round(100 * m["reached"]["offer"] / max(1, m["count"]))
        recs.append({
            "channel": m["channel"],
            "band": m["band"],
            "title": f"Scale {m['label']}",
            "detail": (
                f"ROI {m['roi']:.0f} · {m['count']} candidates · quality {m['qualityScore']:.0f} · "
                f"{m['reached']['offer']} reached offer ({offer_pct}%). {m['recommendation']}"
            ),
        })

    cuts = [m for m in ranked if m["band"] == "cut"]
    for m in cuts[:1]:
        cpo = "—" if m["costPerOffer"] is None else f"₹{round(m['costPerOffer'])}k"
        recs.append({
            "channel": m["channel"],
            "band": m["band"],
            "title": f"Cut {m['label']}",
            "detail": (
                f"ROI {m['roi']:.0f} · {m['count']} candidates · cost-per-offer {cpo}. "
                f"{m['recommendation']}"
            ),
        })

    total_active = sum(m["active"] for m in all_)
    if total_active >= 12:
        top = sorted(all_, key=lambda m: -m["active"])[0] if all_ else None
        if top and top["active"] / total_active > 0.55:
            pct = round(100 * top["active"] / total_active)
            recs.append({
                "channel": top["channel"],
                "band": "experiment",
                "title": "Diversify channel mix",
                "detail": (
                    f"{top['label']} accounts for {pct}% of the active pipeline "
                    f"({top['active']} of {total_active}). A single-channel pipeline is fragile — "
                    "open a parallel experiment in another channel this week."
                ),
            })

    promising = [m for m in ranked if m["band"] == "experiment" and m["qualityScore"] >= 70 and m["count"] >= 2]
    for m in promising[:1]:
        recs.append({
            "channel": m["channel"],
            "band": m["band"],
            "title": f"Promote {m['label']} to a tracked experiment",
            "detail": (
                f"Only {m['count']} candidates but mean quality is {m['qualityScore']:.0f} — "
                "commit to 10 more touches and re-evaluate next month."
            ),
        })

    return recs


# ---------- markdown brief ----------


def build_source_brief(summary: dict, title: Optional[str] = None) -> str:
    L: list[str] = []
    L.append(f"# {title or 'Sourcing Intelligence — Channel Studio brief'}")
    L.append("")
    L.append(
        f"**Pipeline**: {summary['totalActive']} active · {summary['totalCandidates']} total · "
        f"{summary['totalInterviewed']} interviewed · {summary['totalOffers']} reached offer."
    )
    cpi = summary["costPerInterview"]
    cpo = summary["costPerOffer"]
    L.append(
        f"**Spend**: ₹{round(summary['totalSpend'])}k total · "
        + ("—" if cpi is None else f"₹{round(cpi)}k/interview · ")
        + ("—" if cpo is None else f"₹{round(cpo)}k/offer")
    )
    L.append(f"**Diversification**: {round(summary['diversification'] * 100)}/100 normalised channel entropy.")
    if summary.get("bestChannel"):
        m = next((x for x in summary["byChannel"] if x["channel"] == summary["bestChannel"]), None)
        if m:
            L.append(f"**Best channel**: {m['label']} — ROI {m['roi']:.0f} · {m['count']} candidates.")
    if summary.get("worstChannel") and summary["worstChannel"] != summary.get("bestChannel"):
        m = next((x for x in summary["byChannel"] if x["channel"] == summary["worstChannel"]), None)
        if m:
            L.append(f"**Worst channel**: {m['label']} — ROI {m['roi']:.0f} · {m['count']} candidates.")
    L.append("")

    if summary.get("recommendations"):
        L.append("## Recommendations")
        for r in summary["recommendations"]:
            L.append(f"- **{r['title']}** — {r['detail']}")
        L.append("")

    L.append("## Per-channel breakdown")
    L.append("")
    L.append("| Channel | Count | Quality | Conv→Offer | Cost/offer (₹k) | ROI | Band |")
    L.append("|---|---:|---:|---:|---:|---:|---|")
    for m in summary["byChannel"]:
        conv = (f"{round(100 * m['reached']['offer'] / m['count'])}%" if m["count"] > 0 else "—")
        cpo_v = "—" if m["costPerOffer"] is None else f"{round(m['costPerOffer'])}"
        L.append(
            f"| {m['label']} | {m['count']} | {m['qualityScore']:.0f} | {conv} | {cpo_v} | "
            f"{m['roi']:.0f} | {BAND_LABEL[m['band']]} |"
        )
    L.append("")
    return "\n".join(L)
