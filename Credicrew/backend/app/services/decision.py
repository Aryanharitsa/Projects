"""Decision Studio engine — Python mirror of frontend/src/lib/decision.ts.

Given a Role's parsed plan + a list of (candidate, match, optional
interview record) triples, produce calibrated per-candidate verdicts and
an aggregate ranking. Pure functions, no I/O, no dependencies beyond the
existing match + interview services.

Output shape mirrors the TS engine so a programmatic / agentic client gets
byte-identical verdicts whether it ran the engine in the browser or hit
the API.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable, Literal

from app.services.interview import (
    DIMENSION_DEFS,
    RubricDim,
    StageRecord,
    summarise as interview_summarise,
)
from app.services.match import MatchResult


Recommendation = Literal[
    "no_hire", "lean_no", "mixed", "lean_yes", "strong_hire",
]
RECOMMENDATIONS: tuple[Recommendation, ...] = (
    "no_hire", "lean_no", "mixed", "lean_yes", "strong_hire",
)
REC_LABEL: dict[Recommendation, str] = {
    "no_hire": "No hire",
    "lean_no": "Lean no",
    "mixed": "Mixed signal",
    "lean_yes": "Lean yes",
    "strong_hire": "Strong hire",
}

DecisionFlag = Literal[
    "low_confidence", "thin_data", "rubric_drift",
    "missing_key_dim", "high_variance", "no_interview", "unrated",
]
FLAG_LABEL: dict[DecisionFlag, str] = {
    "low_confidence": "Low confidence",
    "thin_data": "Thin data",
    "rubric_drift": "Rubric drift",
    "missing_key_dim": "Key dim unrated",
    "high_variance": "High variance",
    "no_interview": "No interview",
    "unrated": "Not yet rated",
}


@dataclass
class CandidateVerdict:
    candidate_id: int
    name: str
    role: str | None
    location: str | None
    match_score: int
    composite: int | None
    recommendation: Recommendation | None
    confidence: float
    hire_signal: int
    rated_count: int
    total_count: int
    variance: float
    ratings_by_dim: dict[str, int | None]
    flags: list[DecisionFlag]
    rank: int = 0
    top_strengths: list[str] = field(default_factory=list)
    top_concerns: list[str] = field(default_factory=list)


@dataclass
class DimStat:
    key: str
    label: str
    weight: float
    rated_fraction: float
    mean: float | None
    best_candidate_id: int | None
    best_rating: int | None
    spread: int


# ---------- helpers ----------

def _stdev(values: list[int]) -> float:
    if len(values) < 2:
        return 0.0
    m = sum(values) / len(values)
    v = sum((x - m) ** 2 for x in values) / len(values)
    return math.sqrt(v)


def _round2(x: float) -> float:
    return round(x * 100) / 100


# ---------- shapes ----------

@dataclass
class _InterviewLite:
    rubric: list[RubricDim]
    stages: list[StageRecord]


@dataclass
class CandidateInput:
    candidate_id: int
    name: str
    role: str | None
    location: str | None
    match: MatchResult
    interview: _InterviewLite | None


# ---------- per-candidate verdict ----------

def _compute_verdict(input: CandidateInput) -> CandidateVerdict:
    if input.interview is None:
        return CandidateVerdict(
            candidate_id=input.candidate_id,
            name=input.name,
            role=input.role,
            location=input.location,
            match_score=input.match.score,
            composite=None,
            recommendation=None,
            confidence=0.0,
            hire_signal=0,
            rated_count=0,
            total_count=0,
            variance=0.0,
            ratings_by_dim={},
            flags=["no_interview"],
        )

    rubric = input.interview.rubric
    stages = input.interview.stages
    summary = interview_summarise(rubric, stages)

    ratings_by_dim: dict[str, int | None] = {d.key: None for d in rubric}
    for st in stages:
        for sc in st.scores:
            r = sc.get("rating")
            if r is not None:
                ratings_by_dim[sc["key"]] = int(r)

    total_count = len(rubric)
    rated_count = summary.rated_count
    confidence = (rated_count / total_count) if total_count > 0 else 0.0
    composite = summary.composite if rated_count > 0 else None
    recommendation = summary.recommendation if rated_count > 0 else None

    hire_signal = (
        round(composite * math.sqrt(confidence))
        if composite is not None
        else 0
    )

    rated_values = [v for v in ratings_by_dim.values() if v is not None]
    variance = _stdev(rated_values)

    flags: list[DecisionFlag] = []
    if rated_count == 0:
        flags.append("unrated")
    else:
        if confidence < 0.35:
            flags.append("thin_data")
        elif confidence < 0.6:
            flags.append("low_confidence")

        # missing_key_dim
        top_dims = sorted(rubric, key=lambda d: -d.weight)[:3]
        if any(ratings_by_dim[d.key] is None for d in top_dims):
            flags.append("missing_key_dim")

        if variance >= 1.5:
            flags.append("high_variance")

        # rubric_drift
        stage_rated: dict[str, set[str]] = {}
        for st in stages:
            if st.status != "done":
                continue
            stage_rated[st.stage] = {sc["key"] for sc in st.scores if sc.get("rating") is not None}
        if len(stage_rated) >= 2:
            ever = set().union(*stage_rated.values())
            drifted = any(
                any(k not in s for s in stage_rated.values())
                and any(k in s for s in stage_rated.values())
                for k in ever
            )
            if drifted:
                flags.append("rubric_drift")

    label_by_key = {d.key: d.label for d in rubric}
    top_strengths: list[str] = []
    top_concerns: list[str] = []
    for k, r in ratings_by_dim.items():
        if r is None:
            continue
        if r >= 4:
            top_strengths.append(label_by_key.get(k, k))
        if r <= 2:
            top_concerns.append(label_by_key.get(k, k))

    return CandidateVerdict(
        candidate_id=input.candidate_id,
        name=input.name,
        role=input.role,
        location=input.location,
        match_score=input.match.score,
        composite=composite,
        recommendation=recommendation,
        confidence=_round2(confidence),
        hire_signal=hire_signal,
        rated_count=rated_count,
        total_count=total_count,
        variance=_round2(variance),
        ratings_by_dim=ratings_by_dim,
        flags=flags,
        top_strengths=top_strengths[:3],
        top_concerns=top_concerns[:3],
    )


# ---------- main ----------

@dataclass
class DecisionSummary:
    role_id: str
    verdicts: list[CandidateVerdict]
    rubric: list[RubricDim]
    dim_stats: list[DimStat]
    counts: dict[Recommendation, int]
    unrated_count: int
    top_hire_id: int | None
    next_round_ids: list[int]


def build_summary(role_id: str, inputs: Iterable[CandidateInput]) -> DecisionSummary:
    inputs = list(inputs)
    verdicts = [_compute_verdict(x) for x in inputs]

    verdicts.sort(key=lambda v: (
        -v.hire_signal,
        -(v.composite if v.composite is not None else -1),
        -v.match_score,
    ))
    for i, v in enumerate(verdicts):
        v.rank = i + 1

    # union rubric (first-seen wins)
    seen_keys: dict[str, RubricDim] = {}
    for x in inputs:
        if x.interview is None:
            continue
        for d in x.interview.rubric:
            if d.key not in seen_keys:
                seen_keys[d.key] = d
    rubric = list(seen_keys.values())

    # dim stats
    dim_stats: list[DimStat] = []
    for d in rubric:
        rated_vals: list[tuple[int, int]] = []  # (candidate_id, rating)
        candidates_with_dim = 0
        for v in verdicts:
            if d.key not in v.ratings_by_dim:
                continue
            candidates_with_dim += 1
            r = v.ratings_by_dim[d.key]
            if r is not None:
                rated_vals.append((v.candidate_id, r))
        n = len(rated_vals)
        mean: float | None = None
        best_id: int | None = None
        best_rating: int | None = None
        spread = 0
        if n > 0:
            mean = round(sum(r for _, r in rated_vals) / n * 100) / 100
            best_cid, best_rating = max(rated_vals, key=lambda t: t[1])
            best_id = best_cid
            ratings = [r for _, r in rated_vals]
            spread = max(ratings) - min(ratings)
        rated_fraction = (n / candidates_with_dim) if candidates_with_dim > 0 else 0.0
        dim_stats.append(DimStat(
            key=d.key, label=d.label, weight=d.weight,
            rated_fraction=_round2(rated_fraction),
            mean=mean,
            best_candidate_id=best_id, best_rating=best_rating,
            spread=spread,
        ))

    counts: dict[Recommendation, int] = {r: 0 for r in RECOMMENDATIONS}
    unrated_count = 0
    for v in verdicts:
        if v.recommendation is None:
            unrated_count += 1
        else:
            counts[v.recommendation] += 1

    top_hire_id: int | None = None
    for v in verdicts:
        if v.recommendation in ("strong_hire", "lean_yes"):
            top_hire_id = v.candidate_id
            break

    next_round_ids = [
        v.candidate_id for v in verdicts
        if (
            "no_interview" in v.flags
            or "unrated" in v.flags
            or "thin_data" in v.flags
        ) and v.match_score >= 60
    ][:5]

    return DecisionSummary(
        role_id=role_id,
        verdicts=verdicts,
        rubric=rubric,
        dim_stats=dim_stats,
        counts=counts,
        unrated_count=unrated_count,
        top_hire_id=top_hire_id,
        next_round_ids=next_round_ids,
    )


# ---------- markdown debrief ----------

def build_debrief(role_name: str, summary: DecisionSummary) -> str:
    lines: list[str] = []
    lines.append(f"# Hiring committee debrief — {role_name}")
    lines.append("")
    lines.append(
        f"{len(summary.verdicts)} candidate"
        f"{'' if len(summary.verdicts) == 1 else 's'} reviewed."
    )
    lines.append("")

    if summary.top_hire_id is not None:
        top = next(v for v in summary.verdicts if v.candidate_id == summary.top_hire_id)
        rec = REC_LABEL[top.recommendation] if top.recommendation else "—"
        lines.append(
            f"**Recommended hire:** {top.name} — {rec} · composite {top.composite} · signal {top.hire_signal}."
        )
    elif any(v.composite is not None for v in summary.verdicts):
        best = summary.verdicts[0]
        lines.append(
            f"**No clear hire yet.** Best candidate is {best.name} (signal {best.hire_signal})."
        )
    else:
        lines.append("**Pre-interview stage.** No scorecards have been submitted yet.")
    lines.append("")

    tally_parts: list[str] = []
    for tier in ("strong_hire", "lean_yes", "mixed", "lean_no", "no_hire"):
        if summary.counts[tier] > 0:
            tally_parts.append(f"{summary.counts[tier]} {REC_LABEL[tier]}")
    if summary.unrated_count > 0:
        tally_parts.append(f"{summary.unrated_count} not yet rated")
    if tally_parts:
        lines.append(f"**Tally:** {' · '.join(tally_parts)}.")
        lines.append("")

    lines.append("## Candidates")
    lines.append("")
    for v in summary.verdicts:
        lines.append(f"### {v.rank}. {v.name}{f' — {v.role}' if v.role else ''}")
        if v.recommendation:
            lines.append(
                f"- **Verdict:** {REC_LABEL[v.recommendation]} · composite {v.composite}"
                f" · signal {v.hire_signal} · confidence {v.confidence * 100:.0f}%"
                f" ({v.rated_count}/{v.total_count} dims rated)"
            )
        else:
            lines.append(f"- **Verdict:** Not rated yet · match {v.match_score}")
        if v.top_strengths:
            lines.append(f"- **Strengths:** {', '.join(v.top_strengths)}.")
        if v.top_concerns:
            lines.append(f"- **Concerns:** {', '.join(v.top_concerns)}.")
        if v.flags:
            lines.append(f"- **Flags:** {' · '.join(FLAG_LABEL[f] for f in v.flags)}.")
        lines.append("")

    if summary.next_round_ids:
        lines.append("## Next-round candidates (worth interviewing)")
        lines.append("")
        for cid in summary.next_round_ids:
            v = next(x for x in summary.verdicts if x.candidate_id == cid)
            lines.append(f"- {v.name}{f' — {v.role}' if v.role else ''} (match {v.match_score})")
        lines.append("")

    rated_dims = [d for d in summary.dim_stats if d.mean is not None]
    if rated_dims:
        lines.append("## Rubric signal across pool")
        lines.append("")
        for d in rated_dims:
            spread_part = f" · spread {d.spread}" if d.spread > 0 else ""
            lines.append(
                f"- **{d.label}:** mean {d.mean:.1f}/5"
                f" · {d.rated_fraction * 100:.0f}% coverage{spread_part}"
            )
        lines.append("")

    return "\n".join(lines)


# ---------- (de)serialization ----------

def verdict_as_dict(v: CandidateVerdict) -> dict:
    return {
        "candidate_id": v.candidate_id,
        "name": v.name,
        "role": v.role,
        "location": v.location,
        "match_score": v.match_score,
        "composite": v.composite,
        "recommendation": v.recommendation,
        "confidence": v.confidence,
        "hire_signal": v.hire_signal,
        "rated_count": v.rated_count,
        "total_count": v.total_count,
        "variance": v.variance,
        "ratings_by_dim": v.ratings_by_dim,
        "flags": list(v.flags),
        "rank": v.rank,
        "top_strengths": list(v.top_strengths),
        "top_concerns": list(v.top_concerns),
    }


def summary_as_dict(s: DecisionSummary) -> dict:
    return {
        "role_id": s.role_id,
        "verdicts": [verdict_as_dict(v) for v in s.verdicts],
        "rubric": [
            {"key": d.key, "label": d.label, "description": d.description,
             "weight": d.weight, "source": d.source}
            for d in s.rubric
        ],
        "dim_stats": [
            {"key": d.key, "label": d.label, "weight": d.weight,
             "rated_fraction": d.rated_fraction, "mean": d.mean,
             "best_candidate_id": d.best_candidate_id,
             "best_rating": d.best_rating, "spread": d.spread}
            for d in s.dim_stats
        ],
        "counts": dict(s.counts),
        "unrated_count": s.unrated_count,
        "top_hire_id": s.top_hire_id,
        "next_round_ids": list(s.next_round_ids),
    }


def rubric_from_payload(items: Iterable[dict]) -> list[RubricDim]:
    out: list[RubricDim] = []
    for it in items:
        key = it.get("key")
        if not key:
            continue
        defaults = DIMENSION_DEFS.get(key, {"label": key, "description": "", "source": "skill"})
        out.append(RubricDim(
            key=key,
            label=it.get("label", defaults.get("label", key)),
            description=it.get("description", defaults.get("description", "")),
            weight=float(it.get("weight", 0.0)),
            source=it.get("source", defaults.get("source", "skill")),
        ))
    return out


def stages_from_payload(rubric: list[RubricDim], items: Iterable[dict]) -> list[StageRecord]:
    valid = {d.key for d in rubric}
    out: list[StageRecord] = []
    for it in items:
        out.append(StageRecord(
            stage=it.get("stage"),  # type: ignore[arg-type]
            status=it.get("status", "planned"),
            scores=[
                {"key": s["key"], "rating": s.get("rating")}
                for s in it.get("scores", [])
                if s.get("key") in valid
            ],
            signals=list(it.get("signals", [])),
            notes=it.get("notes"),
        ))
    return out
