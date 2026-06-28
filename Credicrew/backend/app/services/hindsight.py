"""Hindsight — Post-Hire Outcome Calibration & Rubric Tuner (Python mirror).

Same physics, same thresholds, same outputs as
``frontend/src/lib/hindsight.ts`` so a backend client (or an agent calling
``POST /hindsight/summary``) gets byte-identical calibration math for the
same fixture.

Engine in one paragraph
-----------------------
Every offer-status shortlist entry is treated as an accepted hire. Each
hire is paired with a post-hire outcome — either logged by the recruiter
(``source='real'``) or synthesised deterministically from the interview
composite + an FNV-1a hash of ``candidateId::roleId`` (``source='synthetic'``).
The engine then computes:

* **Pool-level calibration** — Pearson + Spearman correlation between
  composite and post-hire performance, plus a Brier score for the binary
  "good hire" predictor.
* **Per-dim predictive power** — for every rubric dim that was rated on
  at least one hire, Pearson(rating, performance) and Pearson(rating,
  tenureDays). Bucketed strong / moderate / weak / unknown.
* **Suggested rubric weights** — a 50/50 blend of normalised |r_perf|
  (evidence) and the current weight (intent), renormalised to sum to 1.
* **Surprise hires** — composite ≥ 80 with perf ≤ 2 (false positive) or
  composite ≤ 55 with perf ≥ 4 (false negative). These are the
  calibration teachers.
* **Tenure × recommendation band** — does the team's "strong hire"
  bucket actually stick longer?
* **Markdown brief** — the same headline + per-dim table + actions that
  the UI renders, ready for paste into a quarterly hiring review.
"""
from __future__ import annotations

import math
import time
from dataclasses import asdict, dataclass, field
from typing import Any

from app.services.match import MatchResult, QueryPlan, match_candidate, plan_query


# ---------- tunables (must match TS engine constants) ----------

PP_STRONG = 0.55
PP_MODERATE = 0.35
PP_WEAK = 0.10
FP_COMPOSITE_FLOOR = 80
FP_PERF_FLOOR = 2
FN_COMPOSITE_CEIL = 55
FN_PERF_FLOOR = 4
MIN_SAMPLES = 4
RETUNE_BLEND = 0.5
GOOD_HIRE_FLOOR = 4
TENURE_BASE_DAYS = 60
TENURE_PER_RATING_DAYS = 95
DAY_MS = 86_400_000


# ---------- pure math ----------

_FNV_OFFSET = 0x811C9DC5
_FNV_MASK = 0xFFFFFFFF


def fnv1a(s: str) -> int:
    h = _FNV_OFFSET
    for ch in s:
        h ^= ord(ch) & 0xFF
        h = (h + ((h << 1) + (h << 4) + (h << 7) + (h << 8) + (h << 24))) & _FNV_MASK
    return h


def pearson(xs: list[float], ys: list[float]) -> float:
    n = len(xs)
    if n < 2 or n != len(ys):
        return 0.0
    mx = sum(xs) / n
    my = sum(ys) / n
    num = 0.0
    dx2 = 0.0
    dy2 = 0.0
    for x, y in zip(xs, ys):
        dxv = x - mx
        dyv = y - my
        num += dxv * dyv
        dx2 += dxv * dxv
        dy2 += dyv * dyv
    denom = math.sqrt(dx2 * dy2)
    if denom == 0:
        return 0.0
    return num / denom


def _ranks(xs: list[float]) -> list[float]:
    idx = sorted(range(len(xs)), key=lambda i: xs[i])
    r = [0.0] * len(xs)
    i = 0
    while i < len(idx):
        j = i
        while j + 1 < len(idx) and xs[idx[j + 1]] == xs[idx[i]]:
            j += 1
        mean_rank = (i + j) / 2 + 1
        for k in range(i, j + 1):
            r[idx[k]] = mean_rank
        i = j + 1
    return r


def spearman(xs: list[float], ys: list[float]) -> float:
    if len(xs) != len(ys) or len(xs) < 2:
        return 0.0
    return pearson(_ranks(xs), _ranks(ys))


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def round2(v: float) -> float:
    return round(v * 100) / 100


def round3(v: float) -> float:
    return round(v * 1000) / 1000


# ---------- synthetic outcome seed ----------


def synthetic_outcome(
    candidate_id: int,
    role_id: str,
    hired_at_ms: float,
    composite: float,
    now_ms: float,
) -> dict[str, Any]:
    h = fnv1a(f"{candidate_id}::{role_id}::outcome")
    noise01 = (h % 10_000) / 10_000
    noise_centred = noise01 - 0.5
    base = composite / 25 + noise_centred * 1.7 + 0.7
    perf = int(clamp(round(base), 1, 5))

    jitter = (h >> 8) % 60
    tenure = round(TENURE_BASE_DAYS + perf * TENURE_PER_RATING_DAYS + jitter)
    days_since_hire = max(0, int((now_ms - hired_at_ms) / DAY_MS))
    tenure_days = min(tenure, max(7, days_since_hire))

    attrition_roll = ((h >> 16) % 100) / 100
    attrition_prob = 0.65 if perf <= 2 else 0.25 if perf == 3 else 0.08
    still_active = attrition_roll > attrition_prob

    return {
        "candidate_id": candidate_id,
        "role_id": role_id,
        "hired_at_ms": hired_at_ms,
        "performance": perf,
        "tenure_days": tenure_days,
        "still_active": still_active,
        "source": "synthetic",
    }


# ---------- types ----------


@dataclass
class HireRecord:
    candidate_id: int
    candidate_name: str
    role_id: str
    role_name: str
    hired_at_ms: float
    composite: int
    recommendation: str | None
    ratings: dict[str, int]
    rubric: list[dict[str, Any]]
    outcome: dict[str, Any]


@dataclass
class DimensionCalibration:
    key: str
    label: str
    current_weight: float
    r_performance: float
    r_tenure: float
    samples: int
    predictive_power: int
    suggested_weight: float
    weight_delta: float
    band: str


@dataclass
class CompositeBin:
    label: str
    floor: int
    count: int
    mean_performance: float
    mean_tenure_days: int
    good_rate: float


@dataclass
class SurpriseCase:
    candidate_id: int
    candidate_name: str
    role_id: str
    role_name: str
    composite: int
    performance: int
    tenure_days: int
    still_active: bool
    kind: str
    driver_key: str | None
    driver_label: str | None
    driver_rating: int | None
    why: str


@dataclass
class TenureBand:
    band: str
    mean_tenure_days: int
    mean_performance: float
    count: int


@dataclass
class RubricRecommendation:
    keep: list[dict[str, Any]] = field(default_factory=list)
    promote: list[dict[str, Any]] = field(default_factory=list)
    reduce: list[dict[str, Any]] = field(default_factory=list)
    drop: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class HindsightSummary:
    generated_at: int
    hires: list[HireRecord]
    hire_count: int
    real_count: int
    synthetic_count: int
    hit_rate: float
    mean_composite: int
    mean_performance: float
    mean_tenure_days: int
    attrition_rate: float
    pearson: float
    spearman: float
    brier_score: float
    per_dimension: list[DimensionCalibration]
    composite_bins: list[CompositeBin]
    surprise_cases: list[SurpriseCase]
    rubric_recommendation: RubricRecommendation
    tenure_by_band: list[TenureBand]
    calibration_band: str
    actions: list[str]


# ---------- helpers ----------


def _resolved_plan(role: dict[str, Any]) -> QueryPlan:
    plan = role.get("plan")
    if isinstance(plan, dict) and plan.get("skills") is not None:
        return QueryPlan(
            text=plan.get("text") or role.get("jd") or "",
            skills=list(plan.get("skills") or []),
            location=plan.get("location"),
            seniority=plan.get("seniority"),
        )
    text = role.get("jd") or (plan.get("text") if isinstance(plan, dict) else "") or ""
    return plan_query(text)


def _entry_field(e: dict[str, Any], snake: str, camel: str, default: Any = None) -> Any:
    if snake in e and e[snake] is not None:
        return e[snake]
    if camel in e and e[camel] is not None:
        return e[camel]
    return default


def _composite_from_interview(rec: dict[str, Any]) -> int | None:
    """Mirror frontend `summarise(record).composite` for a raw interview dict.

    Accepts both ``camelCase`` and ``snake_case`` keys.
    """
    rubric = rec.get("rubric") or []
    stages = rec.get("stages") or []
    if not rubric:
        return None

    latest: dict[str, int | None] = {}
    for d in rubric:
        key = d.get("key")
        if key:
            latest[key] = None

    for st in stages:
        for sc in st.get("scores") or []:
            r = sc.get("rating")
            key = sc.get("key")
            if r is not None and key in latest:
                try:
                    latest[key] = int(r)
                except (TypeError, ValueError):
                    pass

    rated_weight = sum(
        float(d.get("weight") or 0.0)
        for d in rubric
        if latest.get(d.get("key") or "") is not None
    )
    if rated_weight <= 0:
        return None

    composite = 0.0
    for d in rubric:
        key = d.get("key") or ""
        r = latest.get(key)
        if r is None:
            continue
        renorm = float(d.get("weight") or 0.0) / rated_weight
        norm = (r - 1) / 4.0
        composite += norm * renorm * 100
    return round(composite)


def _recommendation_from_composite(c: int) -> str:
    if c >= 80:
        return "strong_hire"
    if c >= 65:
        return "lean_yes"
    if c >= 50:
        return "mixed"
    if c >= 35:
        return "lean_no"
    return "no_hire"


# ---------- engine ----------


def _extract_hires(
    roles: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    interviews_by_key: dict[str, dict[str, Any]],
    outcome_overrides: dict[str, dict[str, Any]],
    now_ms: float,
) -> list[HireRecord]:
    by_id: dict[int, dict[str, Any]] = {int(c["id"]): c for c in candidates if "id" in c}
    plans: dict[str, QueryPlan] = {r["id"]: _resolved_plan(r) for r in roles}

    out: list[HireRecord] = []
    for role in roles:
        for e in role.get("shortlist") or []:
            if e.get("status") != "offer":
                continue
            cid = int(_entry_field(e, "candidate_id", "candidateId", 0))
            if cid == 0:
                continue
            cand = by_id.get(cid)
            if not cand:
                continue
            hired_at = float(
                _entry_field(e, "stage_changed_at", "stageChangedAt", 0)
                or _entry_field(e, "added_at", "addedAt", now_ms - 90 * DAY_MS)
            )

            iv_key = f"{role['id']}::{cid}"
            iv = interviews_by_key.get(iv_key)
            composite: int | None = None
            recommendation: str | None = None
            ratings: dict[str, int] = {}
            rubric: list[dict[str, Any]] = []

            if iv:
                rubric = iv.get("rubric") or []
                composite = _composite_from_interview(iv)
                if composite is not None:
                    recommendation = _recommendation_from_composite(composite)
                # Latest rating per dim
                latest: dict[str, int | None] = {}
                for d in rubric:
                    key = d.get("key")
                    if key:
                        latest[key] = None
                for st in iv.get("stages") or []:
                    for sc in st.get("scores") or []:
                        r = sc.get("rating")
                        key = sc.get("key")
                        if r is not None and key in latest:
                            try:
                                latest[key] = int(r)
                            except (TypeError, ValueError):
                                pass
                for k, v in latest.items():
                    if v is not None:
                        ratings[k] = v

            if composite is None:
                m: MatchResult = match_candidate(plans[role["id"]], cand)
                composite = round(0.55 * m.score + 0.45 * 70)

            override_key = f"{cid}::{role['id']}"
            outcome = outcome_overrides.get(override_key) or synthetic_outcome(
                cid, role["id"], hired_at, composite, now_ms,
            )

            out.append(
                HireRecord(
                    candidate_id=cid,
                    candidate_name=cand.get("name") or f"Candidate {cid}",
                    role_id=role["id"],
                    role_name=role.get("name") or "",
                    hired_at_ms=hired_at,
                    composite=composite,
                    recommendation=recommendation,
                    ratings=ratings,
                    rubric=rubric,
                    outcome=outcome,
                )
            )
    out.sort(key=lambda h: -h.hired_at_ms)
    return out


def _average_rubric_weights(hires: list[HireRecord]) -> dict[str, dict[str, Any]]:
    sums: dict[str, dict[str, Any]] = {}
    for h in hires:
        for d in h.rubric:
            k = d.get("key") or ""
            if not k:
                continue
            entry = sums.setdefault(k, {"sum": 0.0, "count": 0, "label": d.get("label") or k})
            entry["sum"] += float(d.get("weight") or 0.0)
            entry["count"] += 1
            entry["label"] = d.get("label") or entry["label"]
    out: dict[str, dict[str, Any]] = {}
    for k, v in sums.items():
        out[k] = {
            "weight": v["sum"] / v["count"] if v["count"] > 0 else 0.0,
            "label": v["label"],
        }
    return out


def _band(power: int, samples: int) -> str:
    if samples < MIN_SAMPLES:
        return "unknown"
    if power >= PP_STRONG * 100:
        return "strong"
    if power >= PP_MODERATE * 100:
        return "moderate"
    if power >= PP_WEAK * 100:
        return "weak"
    return "unknown"


def _per_dimension(hires: list[HireRecord]) -> list[DimensionCalibration]:
    avg = _average_rubric_weights(hires)
    buckets: dict[str, dict[str, list[float]]] = {}
    for h in hires:
        for k, r in h.ratings.items():
            b = buckets.setdefault(k, {"ratings": [], "perf": [], "tenure": []})
            b["ratings"].append(float(r))
            b["perf"].append(float(h.outcome["performance"]))
            b["tenure"].append(float(h.outcome["tenure_days"]))

    raw: list[DimensionCalibration] = []
    for k, b in buckets.items():
        meta = avg.get(k)
        if not meta:
            continue
        r_perf = pearson(b["ratings"], b["perf"])
        r_ten = pearson(b["ratings"], b["tenure"])
        pp = round(max(abs(r_perf), 0.6 * abs(r_ten)) * 100)
        raw.append(
            DimensionCalibration(
                key=k,
                label=meta["label"],
                current_weight=meta["weight"],
                r_performance=round3(r_perf),
                r_tenure=round3(r_ten),
                samples=len(b["ratings"]),
                predictive_power=pp,
                suggested_weight=meta["weight"],
                weight_delta=0.0,
                band=_band(pp, len(b["ratings"])),
            )
        )

    weights = [
        max(0.0, abs(d.r_performance)) if d.samples >= MIN_SAMPLES else 0.0
        for d in raw
    ]
    sw = sum(weights)
    if sw > 0:
        for i, d in enumerate(raw):
            observed = weights[i] / sw
            d.suggested_weight = RETUNE_BLEND * observed + (1 - RETUNE_BLEND) * d.current_weight
    s_sum = sum(d.suggested_weight for d in raw)
    if s_sum > 0:
        for d in raw:
            d.suggested_weight = round3(d.suggested_weight / s_sum)
            d.weight_delta = round3(d.suggested_weight - d.current_weight)

    raw.sort(key=lambda d: -d.predictive_power)
    return raw


def _composite_bins(hires: list[HireRecord]) -> list[CompositeBin]:
    bins: list[CompositeBin] = []
    for floor_v in range(0, 100, 10):
        ceil_v = floor_v + 9
        in_bin = [h for h in hires if floor_v <= h.composite <= ceil_v]
        if not in_bin:
            bins.append(CompositeBin(
                label=f"{floor_v}–{ceil_v}",
                floor=floor_v,
                count=0,
                mean_performance=0.0,
                mean_tenure_days=0,
                good_rate=0.0,
            ))
            continue
        perf = sum(h.outcome["performance"] for h in in_bin) / len(in_bin)
        tenure = sum(h.outcome["tenure_days"] for h in in_bin) / len(in_bin)
        good = sum(1 for h in in_bin if h.outcome["performance"] >= GOOD_HIRE_FLOOR) / len(in_bin)
        bins.append(CompositeBin(
            label=f"{floor_v}–{ceil_v}",
            floor=floor_v,
            count=len(in_bin),
            mean_performance=round2(perf),
            mean_tenure_days=round(tenure),
            good_rate=round2(good),
        ))
    return bins


def _explain_surprise(
    kind: str,
    composite: int,
    perf: int,
    tenure_days: int,
    active: bool,
    driver_label: str | None,
    driver_rating: int | None,
) -> str:
    if kind == "false_positive":
        tail = (
            f"still on the team but underperforming after {tenure_days}d."
            if active
            else f"left after {tenure_days}d."
        )
        if driver_label and driver_rating is not None:
            return f"Rated {driver_rating}/5 on {driver_label} at interview · landed at perf {perf}/5 — {tail}"
        return f"Composite {composite} predicted strong-hire · landed at perf {perf}/5 — {tail}"
    tail = (
        f"now performing at {perf}/5 after {tenure_days}d."
        if active
        else f"delivered {perf}/5 then moved on after {tenure_days}d."
    )
    if driver_label and driver_rating is not None:
        return f"Rated only {driver_rating}/5 on {driver_label} at interview but {tail}"
    return f"Composite {composite} predicted mixed · {tail}"


def _surprise_cases(hires: list[HireRecord]) -> list[SurpriseCase]:
    out: list[SurpriseCase] = []
    for h in hires:
        c = h.composite
        p = int(h.outcome["performance"])
        kind: str | None = None
        if c >= FP_COMPOSITE_FLOOR and p <= FP_PERF_FLOOR:
            kind = "false_positive"
        elif c <= FN_COMPOSITE_CEIL and p >= FN_PERF_FLOOR:
            kind = "false_negative"
        if kind is None:
            continue
        driver_key: str | None = None
        driver_label: str | None = None
        driver_rating: int | None = None
        best_delta = float("-inf")
        for d in h.rubric:
            key = d.get("key") or ""
            r = h.ratings.get(key)
            if r is None:
                continue
            delta = r if kind == "false_positive" else -r
            if delta > best_delta:
                best_delta = delta
                driver_key = key
                driver_label = d.get("label") or key
                driver_rating = r
        out.append(
            SurpriseCase(
                candidate_id=h.candidate_id,
                candidate_name=h.candidate_name,
                role_id=h.role_id,
                role_name=h.role_name,
                composite=c,
                performance=p,
                tenure_days=int(h.outcome["tenure_days"]),
                still_active=bool(h.outcome["still_active"]),
                kind=kind,
                driver_key=driver_key,
                driver_label=driver_label,
                driver_rating=driver_rating,
                why=_explain_surprise(
                    kind, c, p, int(h.outcome["tenure_days"]),
                    bool(h.outcome["still_active"]), driver_label, driver_rating,
                ),
            )
        )

    def _sort_key(c: SurpriseCase) -> tuple[int, float]:
        kind_rank = 0 if c.kind == "false_positive" else 1
        magnitude = -abs(c.composite - c.performance * 20)
        return (kind_rank, magnitude)

    out.sort(key=_sort_key)
    return out


def _rubric_recommendation(per_dim: list[DimensionCalibration]) -> RubricRecommendation:
    out = RubricRecommendation()
    for d in per_dim:
        delta = d.suggested_weight - d.current_weight
        if d.samples < MIN_SAMPLES:
            continue
        entry = {
            "key": d.key,
            "label": d.label,
            "current_weight": round3(d.current_weight),
            "suggested_weight": round3(d.suggested_weight),
            "delta": round3(delta),
        }
        if d.band == "strong" and delta >= 0.03:
            out.promote.append(entry)
        elif abs(delta) < 0.03 and d.band != "unknown":
            out.keep.append(entry)
        elif delta <= -0.03 and d.band != "unknown":
            out.reduce.append(entry)
        if abs(d.r_performance) < PP_WEAK and d.samples >= MIN_SAMPLES:
            out.drop.append({
                "key": d.key,
                "label": d.label,
                "r_performance": round3(d.r_performance),
                "samples": d.samples,
            })
    out.promote.sort(key=lambda r: -r["delta"])
    out.reduce.sort(key=lambda r: r["delta"])
    out.keep.sort(key=lambda r: -r["suggested_weight"])
    return out


def _tenure_by_band(hires: list[HireRecord]) -> list[TenureBand]:
    bands = ["strong_hire", "lean_yes", "mixed", "lean_no", "no_hire"]
    buckets: dict[str, dict[str, list[float]]] = {b: {"tenure": [], "perf": []} for b in bands}
    for h in hires:
        rec = h.recommendation or _recommendation_from_composite(h.composite)
        buck = buckets.get(rec)
        if not buck:
            continue
        buck["tenure"].append(float(h.outcome["tenure_days"]))
        buck["perf"].append(float(h.outcome["performance"]))
    out: list[TenureBand] = []
    for b in bands:
        buck = buckets[b]
        n = len(buck["tenure"])
        if n == 0:
            out.append(TenureBand(band=b, mean_tenure_days=0, mean_performance=0.0, count=0))
            continue
        mt = sum(buck["tenure"]) / n
        mp = sum(buck["perf"]) / n
        out.append(TenureBand(
            band=b,
            mean_tenure_days=round(mt),
            mean_performance=round2(mp),
            count=n,
        ))
    return out


def _brier(hires: list[HireRecord]) -> float:
    if not hires:
        return 0.0
    s = 0.0
    for h in hires:
        p = clamp(h.composite / 100.0, 0.0, 1.0)
        y = 1.0 if h.outcome["performance"] >= GOOD_HIRE_FLOOR else 0.0
        s += (p - y) ** 2
    return round3(s / len(hires))


def _calibration_band(pearson_v: float, hires: list[HireRecord]) -> str:
    if len(hires) < MIN_SAMPLES:
        return "unknown"
    if pearson_v >= 0.55:
        return "excellent"
    if pearson_v >= 0.35:
        return "good"
    if pearson_v >= 0.15:
        return "mixed"
    return "concerning"


def _action_list(s: HindsightSummary) -> list[str]:
    actions: list[str] = []
    if s.hire_count == 0:
        actions.append("No accepted offers yet — Hindsight lights up the moment your first hire lands.")
        return actions
    verdict_map = {
        "excellent": "rubric is calibrated — keep going.",
        "good": "rubric is mostly working — tighten weights below to lift further.",
        "mixed": "rubric is partially predictive — promote the strong dims, prune the noise.",
        "concerning": "rubric is not telling you who succeeds — re-weight aggressively or replace dims.",
        "unknown": "not enough hires to know — log post-hire outcomes monthly to grow the signal.",
    }
    actions.append(
        f"Pearson(composite, performance) = {s.pearson:.2f} · Brier = {s.brier_score:.2f} — "
        + verdict_map.get(s.calibration_band, "")
    )
    strongest = next((d for d in s.per_dimension if d.band == "strong"), None)
    if strongest:
        actions.append(
            f"Strongest signal: **{strongest.label}** (r={strongest.r_performance:.2f}, n={strongest.samples}) — protect the questions that exercise it."
        )
    weakest = next(
        (d for d in s.per_dimension if d.band == "weak" or (d.band == "unknown" and d.samples >= MIN_SAMPLES)),
        None,
    )
    if weakest and (strongest is None or weakest.key != strongest.key):
        actions.append(
            f"Weakest signal: **{weakest.label}** (r={weakest.r_performance:.2f}) — either replace the prompts or reduce its weight."
        )
    if s.rubric_recommendation.drop:
        names = ", ".join(d["label"] for d in s.rubric_recommendation.drop[:2])
        plural = "" if len(s.rubric_recommendation.drop) == 1 else "s"
        actions.append(f"Drop candidate dim{plural}: {names} — |r| stays below {PP_WEAK} across hires.")
    fps = sum(1 for c in s.surprise_cases if c.kind == "false_positive")
    fns = sum(1 for c in s.surprise_cases if c.kind == "false_negative")
    if fps > 0 and fns > 0:
        actions.append(
            f"Surprise pool: {fps} false positive{'' if fps == 1 else 's'}, "
            f"{fns} false negative{'' if fns == 1 else 's'} — your calibration teachers."
        )
    elif fps > 0:
        actions.append(
            f"{fps} hire{'' if fps == 1 else 's'} predicted strong but underperformed — review the panel that scored them."
        )
    elif fns > 0:
        actions.append(
            f"{fns} mid-composite hire{'' if fns == 1 else 's'} delivered strongly — your bar may be too high."
        )
    if s.attrition_rate >= 0.20:
        actions.append(
            f"Attrition is {s.attrition_rate*100:.0f}% — investigate post-hire onboarding before tuning the rubric further."
        )
    return actions


def analyze_hindsight(
    roles: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    interviews: list[dict[str, Any]] | None = None,
    outcomes: list[dict[str, Any]] | None = None,
    now_ms: int | None = None,
) -> HindsightSummary:
    now = float(now_ms if now_ms is not None else int(time.time() * 1000))

    interviews_by_key: dict[str, dict[str, Any]] = {}
    for iv in interviews or []:
        rid = iv.get("role_id") or iv.get("roleId")
        cid = iv.get("candidate_id") or iv.get("candidateId")
        if rid is None or cid is None:
            continue
        interviews_by_key[f"{rid}::{int(cid)}"] = iv

    outcome_overrides: dict[str, dict[str, Any]] = {}
    for o in outcomes or []:
        cid = o.get("candidate_id") or o.get("candidateId")
        rid = o.get("role_id") or o.get("roleId")
        if cid is None or rid is None:
            continue
        # Normalise to snake_case fields the engine reads.
        normalised = {
            "candidate_id": int(cid),
            "role_id": str(rid),
            "hired_at_ms": float(o.get("hired_at_ms") or o.get("hiredAtMs") or 0),
            "performance": int(o.get("performance") or 3),
            "tenure_days": int(o.get("tenure_days") or o.get("tenureDays") or 0),
            "still_active": bool(o.get("still_active", o.get("stillActive", True))),
            "note": o.get("note"),
            "source": str(o.get("source") or "real"),
        }
        outcome_overrides[f"{cid}::{rid}"] = normalised

    hires = _extract_hires(roles, candidates, interviews_by_key, outcome_overrides, now)
    hire_count = len(hires)
    real_count = sum(1 for h in hires if h.outcome.get("source") == "real")
    synth_count = hire_count - real_count

    comp_arr = [float(h.composite) for h in hires]
    perf_arr = [float(h.outcome["performance"]) for h in hires]
    tenure_arr = [float(h.outcome["tenure_days"]) for h in hires]

    hit_rate = (
        round2(sum(1 for h in hires if h.outcome["performance"] >= GOOD_HIRE_FLOOR) / hire_count)
        if hire_count > 0
        else 0.0
    )
    mean_composite = round(sum(comp_arr) / hire_count) if hire_count > 0 else 0
    mean_performance = round2(sum(perf_arr) / hire_count) if hire_count > 0 else 0.0
    mean_tenure_days = round(sum(tenure_arr) / hire_count) if hire_count > 0 else 0
    attrition_rate = (
        round2(sum(1 for h in hires if not h.outcome["still_active"]) / hire_count)
        if hire_count > 0
        else 0.0
    )
    p = round3(pearson(comp_arr, perf_arr))
    sp = round3(spearman(comp_arr, perf_arr))
    br = _brier(hires)

    per_dim = _per_dimension(hires)
    bins = _composite_bins(hires)
    surprises = _surprise_cases(hires)
    rec = _rubric_recommendation(per_dim)
    tbb = _tenure_by_band(hires)
    cal_band = _calibration_band(p, hires)

    summary = HindsightSummary(
        generated_at=int(now),
        hires=hires,
        hire_count=hire_count,
        real_count=real_count,
        synthetic_count=synth_count,
        hit_rate=hit_rate,
        mean_composite=mean_composite,
        mean_performance=mean_performance,
        mean_tenure_days=mean_tenure_days,
        attrition_rate=attrition_rate,
        pearson=p,
        spearman=sp,
        brier_score=br,
        per_dimension=per_dim,
        composite_bins=bins,
        surprise_cases=surprises,
        rubric_recommendation=rec,
        tenure_by_band=tbb,
        calibration_band=cal_band,
        actions=[],
    )
    summary.actions = _action_list(summary)
    return summary


# ---------- markdown brief ----------


def _as_pct(v: float) -> str:
    return f"{round(v * 100)}%"


def build_brief(s: HindsightSummary) -> str:
    lines: list[str] = []
    lines.append("# Hindsight — Post-Hire Calibration Brief")
    lines.append("")
    plural = "" if s.hire_count == 1 else "s"
    iso = time.strftime("%Y-%m-%d", time.gmtime(s.generated_at / 1000))
    lines.append(
        f"*{iso} · {s.hire_count} hire{plural} reviewed "
        f"({s.real_count} real outcomes, {s.synthetic_count} synthesised)*"
    )
    lines.append("")
    lines.append("## Headline")
    lines.append(f"- **Calibration band:** {s.calibration_band}")
    lines.append(f"- **Hit rate (perf ≥ 4):** {_as_pct(s.hit_rate)}")
    lines.append(f"- **Mean composite → mean performance:** {s.mean_composite} → {s.mean_performance:.2f}/5")
    lines.append(
        f"- **Pearson r:** {s.pearson:.2f} · **Spearman:** {s.spearman:.2f} · **Brier:** {s.brier_score:.2f}"
    )
    lines.append(
        f"- **Attrition rate:** {_as_pct(s.attrition_rate)} · **Mean tenure:** {s.mean_tenure_days}d"
    )
    lines.append("")
    if s.actions:
        lines.append("## Actions")
        for a in s.actions:
            lines.append(f"- {a}")
        lines.append("")
    if s.per_dimension:
        lines.append("## Rubric dimensions ranked by predictive power")
        lines.append("")
        lines.append("| Dimension | n | r(perf) | r(tenure) | Power | Current → Suggested | Δ |")
        lines.append("|---|---:|---:|---:|---:|---:|---:|")
        for d in s.per_dimension:
            sign = (f"+{d.weight_delta:.3f}" if d.weight_delta > 0 else f"{d.weight_delta:.3f}")
            lines.append(
                f"| {d.label} | {d.samples} | {d.r_performance:.2f} | {d.r_tenure:.2f} | "
                f"{d.predictive_power} | {d.current_weight:.3f} → {d.suggested_weight:.3f} | {sign} |"
            )
        lines.append("")
    if s.rubric_recommendation.promote:
        lines.append("## Promote")
        for r in s.rubric_recommendation.promote:
            lines.append(f"- **{r['label']}** → +{r['delta']:.3f} (suggested {r['suggested_weight']:.3f})")
        lines.append("")
    if s.rubric_recommendation.reduce:
        lines.append("## Reduce")
        for r in s.rubric_recommendation.reduce:
            lines.append(f"- **{r['label']}** → {r['delta']:.3f} (suggested {r['suggested_weight']:.3f})")
        lines.append("")
    if s.rubric_recommendation.drop:
        lines.append("## Drop candidates")
        for r in s.rubric_recommendation.drop:
            lines.append(f"- **{r['label']}** — r={r['r_performance']:.2f} over n={r['samples']}")
        lines.append("")
    if s.surprise_cases:
        lines.append("## Surprise hires")
        for c in s.surprise_cases[:6]:
            tag = "FP" if c.kind == "false_positive" else "FN"
            lines.append(
                f"- **[{tag}] {c.candidate_name}** ({c.role_name}) · composite {c.composite} · "
                f"perf {c.performance}/5 — {c.why}"
            )
        lines.append("")
    if any(b.count > 0 for b in s.composite_bins):
        lines.append("## Calibration curve")
        lines.append("")
        lines.append("| Composite | n | mean perf | good rate | mean tenure (d) |")
        lines.append("|---|---:|---:|---:|---:|")
        for b in s.composite_bins:
            if b.count == 0:
                continue
            lines.append(
                f"| {b.label} | {b.count} | {b.mean_performance:.2f} | {_as_pct(b.good_rate)} | {b.mean_tenure_days} |"
            )
    return "\n".join(lines)


def summary_to_dict(s: HindsightSummary) -> dict[str, Any]:
    return {
        "generated_at": s.generated_at,
        "hires": [asdict(h) for h in s.hires],
        "hire_count": s.hire_count,
        "real_count": s.real_count,
        "synthetic_count": s.synthetic_count,
        "hit_rate": s.hit_rate,
        "mean_composite": s.mean_composite,
        "mean_performance": s.mean_performance,
        "mean_tenure_days": s.mean_tenure_days,
        "attrition_rate": s.attrition_rate,
        "pearson": s.pearson,
        "spearman": s.spearman,
        "brier_score": s.brier_score,
        "per_dimension": [asdict(d) for d in s.per_dimension],
        "composite_bins": [asdict(b) for b in s.composite_bins],
        "surprise_cases": [asdict(c) for c in s.surprise_cases],
        "rubric_recommendation": asdict(s.rubric_recommendation),
        "tenure_by_band": [asdict(t) for t in s.tenure_by_band],
        "calibration_band": s.calibration_band,
        "actions": s.actions,
    }


__all__ = [
    "PP_STRONG",
    "PP_MODERATE",
    "PP_WEAK",
    "FP_COMPOSITE_FLOOR",
    "FP_PERF_FLOOR",
    "FN_COMPOSITE_CEIL",
    "FN_PERF_FLOOR",
    "MIN_SAMPLES",
    "RETUNE_BLEND",
    "GOOD_HIRE_FLOOR",
    "analyze_hindsight",
    "build_brief",
    "fnv1a",
    "pearson",
    "spearman",
    "summary_to_dict",
    "synthetic_outcome",
]

