"""Forecast Studio engine — Python mirror of frontend/src/lib/forecast.ts.

Takes the current funnel + conversion + velocity assumptions and runs a
Monte-Carlo simulation of every candidate's forward walk through the
funnel. Returns the probability of a hire by the target date, the
earliest-hire-date distribution, the bottleneck stage, a sensitivity
tornado, and concrete recommendations.

Pure functions. Deterministic for a given seed so the API returns
byte-identical numbers across calls with the same input. The same
algorithm runs in the browser, so any programmatic / agentic client sees
the same forecast the recruiter is staring at on the page.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


PROGRESSION = ["new", "outreach", "screening", "interview", "offer"]

STAGE_LABEL = {
    "new": "New",
    "outreach": "Outreach",
    "screening": "Screening",
    "interview": "Interview",
    "offer": "Offer",
}

DEFAULT_CONVERSION = {
    "new": 0.65,
    "outreach": 0.40,
    "screening": 0.60,
    "interview": 0.35,
    "offer": 0.70,
}

DEFAULT_VELOCITY = {
    "new": 2.0,
    "outreach": 4.0,
    "screening": 5.0,
    "interview": 8.0,
    "offer": 4.0,
}

DEFAULT_NOTICE_DAYS = 30
DEFAULT_DURATION_SIGMA = 0.45
DAY_MS = 86_400_000


# ---------- input dataclasses ----------


@dataclass
class ForecastAssumptions:
    conversion: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_CONVERSION))
    velocity: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_VELOCITY))
    notice_period_days: int = DEFAULT_NOTICE_DAYS
    duration_sigma: float = DEFAULT_DURATION_SIGMA


@dataclass
class ForecastInput:
    funnel: dict[str, int]
    target_date: str  # YYYY-MM-DD
    now: Optional[int] = None  # epoch ms
    assumptions: Optional[ForecastAssumptions] = None
    trials: int = 4000
    seed: Optional[int] = None


# ---------- RNG (mulberry32, matching the TS engine bit-for-bit) ----------


def _mulberry32(seed: int):
    state = [seed & 0xFFFFFFFF]

    def rng() -> float:
        state[0] = (state[0] + 0x6D2B79F5) & 0xFFFFFFFF
        t = state[0]
        t = ((t ^ (t >> 15)) * (t | 1)) & 0xFFFFFFFF
        t ^= (t + ((t ^ (t >> 7)) * (t | 61))) & 0xFFFFFFFF
        return ((t ^ (t >> 14)) & 0xFFFFFFFF) / 4294967296

    return rng


def _gauss(rng) -> float:
    u = rng()
    v = rng()
    if u < 1e-9:
        u = 1e-9
    return math.sqrt(-2 * math.log(u)) * math.cos(2 * math.pi * v)


def _log_normal_days(rng, median: float, sigma: float) -> float:
    if median <= 0:
        return 0.0
    return math.exp(math.log(median) + sigma * _gauss(rng))


def _clamp01(x: float) -> float:
    if x < 0:
        return 0.0
    if x > 1:
        return 1.0
    return x


def _seed_from_funnel(funnel: dict[str, int]) -> int:
    h = 0x811C9DC5
    for stage in PROGRESSION:
        h ^= (funnel.get(stage, 0) & 0xFF)
        h = (h * 0x01000193) & 0xFFFFFFFF
    return h or 1


def _iso_date(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")


def _parse_iso_day(iso: str) -> int:
    dt = datetime.strptime(iso, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


# ---------- core MC ----------


def _run_mc(
    funnel: dict[str, int],
    target_ms: int,
    now: int,
    assumptions: ForecastAssumptions,
    trials: int,
    seed: int,
) -> dict:
    rng = _mulberry32(seed)
    sorted_hire_dates: list[int] = []
    by_target = 0
    hire_sum = 0
    reaches = {k: 0 for k in PROGRESSION}
    hires = {k: 0 for k in PROGRESSION}

    for _trial in range(trials):
        earliest: Optional[int] = None
        trial_hires = 0
        for stage in PROGRESSION:
            count = funnel.get(stage, 0) or 0
            for _ in range(count):
                t_cur = now
                dropped = False
                start_idx = PROGRESSION.index(stage)
                for s in range(start_idx, len(PROGRESSION)):
                    st = PROGRESSION[s]
                    reaches[st] += 1
                    days = _log_normal_days(rng, assumptions.velocity[st], assumptions.duration_sigma)
                    t_cur += days * DAY_MS
                    if rng() >= _clamp01(assumptions.conversion[st]):
                        dropped = True
                        break
                if not dropped:
                    hire_ms = t_cur + assumptions.notice_period_days * DAY_MS
                    trial_hires += 1
                    hires[stage] += 1
                    if earliest is None or hire_ms < earliest:
                        earliest = hire_ms
        if earliest is not None:
            sorted_hire_dates.append(int(earliest))
            if earliest <= target_ms:
                by_target += 1
        hire_sum += trial_hires
    sorted_hire_dates.sort()
    return {
        "any_hire": len(sorted_hire_dates) / trials,
        "by_target_prob": by_target / trials,
        "sorted_hire_dates": sorted_hire_dates,
        "expected_hires": hire_sum / trials,
        "reaches": reaches,
        "hires": hires,
    }


def _percentile(sorted_list: list[int], p: float) -> Optional[int]:
    if not sorted_list:
        return None
    idx = min(len(sorted_list) - 1, max(0, math.floor(p * len(sorted_list))))
    return sorted_list[idx]


# ---------- public API ----------


def forecast_funnel(inp: ForecastInput) -> dict:
    now = inp.now if inp.now is not None else int(time.time() * 1000)
    trials = max(200, inp.trials)
    assumptions = inp.assumptions or ForecastAssumptions()
    funnel = {k: int(inp.funnel.get(k, 0) or 0) for k in PROGRESSION}
    target_ms = _parse_iso_day(inp.target_date)
    seed = inp.seed if inp.seed is not None else _seed_from_funnel(funnel)

    total = sum(funnel.values())
    if total == 0:
        return {
            "trials": trials,
            "targetDate": inp.target_date,
            "now": now,
            "probabilityByTarget": 0.0,
            "hireDate": {"p10": None, "p50": None, "p90": None, "anyHireProbability": 0.0},
            "expectedHires": 0.0,
            "funnel": [
                {"key": k, "here": 0, "expectedAdvancers": 0.0, "expectedHires": 0.0}
                for k in PROGRESSION
            ],
            "bottleneck": None,
            "sensitivity": [],
            "recommendations": [
                "No candidates in the pipeline yet — add a shortlist before forecasting.",
            ],
            "assumptions": _assumptions_payload(assumptions),
        }

    main = _run_mc(funnel, target_ms, now, assumptions, trials, seed)

    funnel_out = [
        {
            "key": k,
            "here": funnel[k],
            "expectedAdvancers": round(main["reaches"][k] / trials, 2),
            "expectedHires": round(main["hires"][k] / trials, 2),
        }
        for k in PROGRESSION
    ]

    bottleneck = None
    best_drop = 0.0
    for k in PROGRESSION:
        reach_mean = main["reaches"][k] / trials
        drop = reach_mean * (1 - _clamp01(assumptions.conversion[k]))
        if drop > best_drop:
            best_drop = drop
            bottleneck = k

    baseline = main["by_target_prob"]
    sens_trials = max(400, trials // 4)
    sensitivity: list[dict] = []

    for stage in PROGRESSION:
        cv = assumptions.conversion[stage]
        cv_plus = _clamp01(cv + 0.15)
        cv_minus = _clamp01(cv - 0.15)

        a_plus = ForecastAssumptions(
            conversion={**assumptions.conversion, stage: cv_plus},
            velocity=dict(assumptions.velocity),
            notice_period_days=assumptions.notice_period_days,
            duration_sigma=assumptions.duration_sigma,
        )
        a_minus = ForecastAssumptions(
            conversion={**assumptions.conversion, stage: cv_minus},
            velocity=dict(assumptions.velocity),
            notice_period_days=assumptions.notice_period_days,
            duration_sigma=assumptions.duration_sigma,
        )

        plus_p = _run_mc(funnel, target_ms, now, a_plus, sens_trials, seed ^ 0x9E3779B1)["by_target_prob"]
        minus_p = _run_mc(funnel, target_ms, now, a_minus, sens_trials, seed ^ 0x85EBCA77)["by_target_prob"]
        sensitivity.append({
            "lever": {"kind": "conversion", "stage": stage},
            "label": f"{STAGE_LABEL[stage]} conversion",
            "baseline": baseline,
            "upliftPlus": plus_p,
            "upliftMinus": minus_p,
            "delta": abs(plus_p - baseline) + abs(baseline - minus_p),
        })

        v = assumptions.velocity[stage]
        a_fast = ForecastAssumptions(
            conversion=dict(assumptions.conversion),
            velocity={**assumptions.velocity, stage: max(0.25, v * 0.7)},
            notice_period_days=assumptions.notice_period_days,
            duration_sigma=assumptions.duration_sigma,
        )
        a_slow = ForecastAssumptions(
            conversion=dict(assumptions.conversion),
            velocity={**assumptions.velocity, stage: v * 1.3},
            notice_period_days=assumptions.notice_period_days,
            duration_sigma=assumptions.duration_sigma,
        )
        fast_p = _run_mc(funnel, target_ms, now, a_fast, sens_trials, seed ^ 0xC2B2AE35)["by_target_prob"]
        slow_p = _run_mc(funnel, target_ms, now, a_slow, sens_trials, seed ^ 0x27D4EB2F)["by_target_prob"]
        sensitivity.append({
            "lever": {"kind": "velocity", "stage": stage},
            "label": f"{STAGE_LABEL[stage]} speed",
            "baseline": baseline,
            "upliftPlus": fast_p,
            "upliftMinus": slow_p,
            "delta": abs(fast_p - baseline) + abs(baseline - slow_p),
        })

    for stage in ("new", "outreach"):
        bump = {**funnel, stage: funnel[stage] + 5}
        cut = {**funnel, stage: max(0, funnel[stage] - 2)}
        plus_p = _run_mc(bump, target_ms, now, assumptions, sens_trials, seed ^ 0x165667B1)["by_target_prob"]
        minus_p = _run_mc(cut, target_ms, now, assumptions, sens_trials, seed ^ 0xD3A2646C)["by_target_prob"]
        sensitivity.append({
            "lever": {"kind": "add_candidates", "stage": stage},
            "label": f"Add 5 to {STAGE_LABEL[stage]}",
            "baseline": baseline,
            "upliftPlus": plus_p,
            "upliftMinus": minus_p,
            "delta": abs(plus_p - baseline) + abs(baseline - minus_p),
        })

    sensitivity.sort(key=lambda r: r["delta"], reverse=True)

    recs: list[str] = []
    p10_ms = _percentile(main["sorted_hire_dates"], 0.10)
    p50_ms = _percentile(main["sorted_hire_dates"], 0.50)
    p90_ms = _percentile(main["sorted_hire_dates"], 0.90)

    if baseline >= 0.75:
        recs.append(
            f"Strong shape — {round(baseline * 100)}% chance to close by "
            f"{inp.target_date}. Focus on keeping the top of the funnel warm."
        )
    elif baseline >= 0.4:
        recs.append(
            f"Tight but feasible — {round(baseline * 100)}% chance to close by "
            f"{inp.target_date}. Apply the top lever below to tip it past 75%."
        )
    elif baseline > 0:
        recs.append(
            f"At risk — only {round(baseline * 100)}% chance to close by "
            f"{inp.target_date}. Consider widening the funnel or moving the date."
        )
    else:
        recs.append(
            f"Almost certain to miss — pipeline can't realistically close by "
            f"{inp.target_date}. Push the target out or escalate sourcing."
        )

    if bottleneck:
        recs.append(
            f"The {STAGE_LABEL[bottleneck]} stage is your dropout cliff — "
            "tighten the bar earlier or coach the panel to convert more of them."
        )

    if sensitivity and sensitivity[0]["delta"] > 0.05:
        top = sensitivity[0]
        arrow = "+" if top["upliftPlus"] > top["upliftMinus"] else "-"
        swing = max(
            abs(top["upliftPlus"] - top["baseline"]),
            abs(top["baseline"] - top["upliftMinus"]),
        )
        recs.append(
            f"Biggest lever: {top['label']} — pushing it favourably moves "
            f"P(hire-by-target) by {arrow}{round(swing * 100)} points."
        )

    if p50_ms is not None:
        recs.append(
            f"Median earliest-hire date: {_iso_date(p50_ms)} "
            f"(P10 {_iso_date(p10_ms) if p10_ms is not None else '—'} · "
            f"P90 {_iso_date(p90_ms) if p90_ms is not None else '—'})."
        )

    return {
        "trials": trials,
        "targetDate": inp.target_date,
        "now": now,
        "probabilityByTarget": baseline,
        "hireDate": {
            "p10": _iso_date(p10_ms) if p10_ms is not None else None,
            "p50": _iso_date(p50_ms) if p50_ms is not None else None,
            "p90": _iso_date(p90_ms) if p90_ms is not None else None,
            "anyHireProbability": main["any_hire"],
        },
        "expectedHires": round(main["expected_hires"], 2),
        "funnel": funnel_out,
        "bottleneck": bottleneck,
        "sensitivity": sensitivity,
        "recommendations": recs,
        "assumptions": _assumptions_payload(assumptions),
    }


def _assumptions_payload(a: ForecastAssumptions) -> dict:
    return {
        "conversion": dict(a.conversion),
        "velocity": dict(a.velocity),
        "noticePeriodDays": a.notice_period_days,
        "durationSigma": a.duration_sigma,
    }
