"""Calibration engine — Python mirror of frontend/src/lib/calibration.ts.

Models an interview *panel* (interviewers × candidates × rubric dims) and
measures three things the single-rater scorecard can't:

  1. per-interviewer bias — leniency (mean deviation from consensus),
     spread (central-tendency), and agreement with the panel;
  2. panel reliability — a variance-based consensus index plus ICC(1);
  3. whether removing systematic rater bias changes the ranking
     (raw vs. de-biased composites + rank shifts).

Pure functions, stdlib only. Output is camelCase via ``as_dict`` so the TS
engine and this engine emit byte-identical verdicts.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal, Optional


RaterFlag = Literal["lenient", "severe", "flat", "contrarian"]
RaterBand = Literal["calibrated", "lenient", "severe"]
CandFlag = Literal["single_rater", "high_disagreement", "thin"]
ICCBand = Literal["excellent", "good", "fair", "poor", "unreliable"]
Verdict = Literal["calibrated", "minor_drift", "needs_calibration", "unreliable"]

LENIENCY_THRESHOLD = 0.4
FLAT_SPREAD = 0.5
CONTRARIAN_CORR = 0.2
HOT_RANGE = 2
MAX_CELL_VAR = 4

ICC_BAND_LABEL: dict[ICCBand, str] = {
    "excellent": "Excellent",
    "good": "Good",
    "fair": "Fair",
    "poor": "Poor",
    "unreliable": "Unreliable",
}
RATER_FLAG_LABEL: dict[RaterFlag, str] = {
    "lenient": "Lenient",
    "severe": "Severe",
    "flat": "Flat / central",
    "contrarian": "Off-consensus",
}
CAND_FLAG_LABEL: dict[CandFlag, str] = {
    "single_rater": "Single-rater dim",
    "high_disagreement": "Panel split",
    "thin": "Thin coverage",
}
VERDICT_LABEL: dict[Verdict, str] = {
    "calibrated": "Calibrated · panel agrees",
    "minor_drift": "Minor drift · one rater off",
    "needs_calibration": "Needs calibration · biased raters",
    "unreliable": "Unreliable · not enough overlap",
}


# ---------- input shapes ----------

@dataclass
class Interviewer:
    id: str
    name: str
    title: Optional[str] = None


@dataclass
class PanelRating:
    interviewer_id: str
    candidate_id: int
    dim_key: str
    rating: float


@dataclass
class CandidateLite:
    id: int
    name: str
    role: Optional[str] = None
    location: Optional[str] = None


@dataclass
class RubricLite:
    key: str
    label: str
    weight: float


# ---------- output shapes ----------

@dataclass
class RaterStat:
    interviewer_id: str
    name: str
    title: Optional[str]
    leniency: float
    spread: float
    consensus_corr: Optional[float]
    count: int
    band: RaterBand
    flags: list[RaterFlag]

    def as_dict(self) -> dict:
        return {
            "interviewerId": self.interviewer_id,
            "name": self.name,
            "title": self.title,
            "leniency": _r(self.leniency, 3),
            "spread": _r(self.spread, 3),
            "consensusCorr": None if self.consensus_corr is None else _r(self.consensus_corr, 3),
            "count": self.count,
            "band": self.band,
            "flags": self.flags,
        }


@dataclass
class CandidateScore:
    candidate_id: int
    name: str
    role: Optional[str]
    location: Optional[str]
    raw_composite: Optional[int]
    calibrated_composite: Optional[int]
    delta: int
    raw_rank: int
    calibrated_rank: int
    rank_shift: int
    confidence: float
    rated_dims: int
    total_dims: int
    consensus: Optional[float]
    flags: list[CandFlag]

    def as_dict(self) -> dict:
        return {
            "candidateId": self.candidate_id,
            "name": self.name,
            "role": self.role,
            "location": self.location,
            "rawComposite": self.raw_composite,
            "calibratedComposite": self.calibrated_composite,
            "delta": self.delta,
            "rawRank": self.raw_rank,
            "calibratedRank": self.calibrated_rank,
            "rankShift": self.rank_shift,
            "confidence": _r(self.confidence, 3),
            "ratedDims": self.rated_dims,
            "totalDims": self.total_dims,
            "consensus": None if self.consensus is None else _r(self.consensus, 3),
            "flags": self.flags,
        }


@dataclass
class CellRating:
    interviewer_id: str
    name: str
    rating: float

    def as_dict(self) -> dict:
        return {"interviewerId": self.interviewer_id, "name": self.name, "rating": self.rating}


@dataclass
class CellInfo:
    candidate_id: int
    candidate_name: str
    dim_key: str
    dim_label: str
    ratings: list[CellRating]
    mean: float
    spread: float
    range: float
    n: int
    agreement: Optional[float]

    def as_dict(self) -> dict:
        return {
            "candidateId": self.candidate_id,
            "candidateName": self.candidate_name,
            "dimKey": self.dim_key,
            "dimLabel": self.dim_label,
            "ratings": [r.as_dict() for r in self.ratings],
            "mean": _r(self.mean, 3),
            "spread": _r(self.spread, 3),
            "range": self.range,
            "n": self.n,
            "agreement": None if self.agreement is None else _r(self.agreement, 3),
        }


@dataclass
class CalibrationResult:
    role_id: str
    raters: list[RaterStat]
    candidates: list[CandidateScore]
    cells: list[CellInfo]
    hot_cells: list[CellInfo]
    consensus_index: Optional[float]
    icc: Optional[float]
    icc_band: Optional[ICCBand]
    icc_calibrated: Optional[float]
    icc_calibrated_band: Optional[ICCBand]
    rank_shift_count: int
    single_rater_cells: int
    multi_rated_cells: int
    biased_raters: int
    grand_mean: float
    verdict: Verdict
    rubric: list[RubricLite]
    suggestions: list[str]
    notes: list[str]
    generated_at: int

    def as_dict(self) -> dict:
        return {
            "roleId": self.role_id,
            "raters": [r.as_dict() for r in self.raters],
            "candidates": [c.as_dict() for c in self.candidates],
            "cells": [c.as_dict() for c in self.cells],
            "hotCells": [c.as_dict() for c in self.hot_cells],
            "consensusIndex": None if self.consensus_index is None else _r(self.consensus_index, 3),
            "icc": None if self.icc is None else _r(self.icc, 3),
            "iccBand": self.icc_band,
            "iccCalibrated": None if self.icc_calibrated is None else _r(self.icc_calibrated, 3),
            "iccCalibratedBand": self.icc_calibrated_band,
            "rankShiftCount": self.rank_shift_count,
            "singleRaterCells": self.single_rater_cells,
            "multiRatedCells": self.multi_rated_cells,
            "biasedRaters": self.biased_raters,
            "grandMean": _r(self.grand_mean, 3),
            "verdict": self.verdict,
            "rubric": [{"key": d.key, "label": d.label, "weight": d.weight} for d in self.rubric],
            "suggestions": self.suggestions,
            "notes": self.notes,
            "generatedAt": self.generated_at,
        }


# ---------- math helpers ----------

def _r(x: float, digits: int) -> float:
    f = 10 ** digits
    return math.floor(x * f + 0.5) / f if x >= 0 else -math.floor(-x * f + 0.5) / f


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _pvar(xs: list[float]) -> float:
    if not xs:
        return 0.0
    m = _mean(xs)
    return sum((x - m) ** 2 for x in xs) / len(xs)


def _pstd(xs: list[float]) -> float:
    return math.sqrt(_pvar(xs))


def _pearson(xs: list[float], ys: list[float]) -> Optional[float]:
    n = len(xs)
    if n < 2 or len(ys) != n:
        return None
    sx = sum(xs)
    sy = sum(ys)
    sxx = sum(x * x for x in xs)
    syy = sum(y * y for y in ys)
    sxy = sum(xs[i] * ys[i] for i in range(n))
    cov = n * sxy - sx * sy
    vx = n * sxx - sx * sx
    vy = n * syy - sy * sy
    if vx <= 1e-9 or vy <= 1e-9:
        return None
    return cov / math.sqrt(vx * vy)


def _icc_one_way(groups: list[list[float]]) -> Optional[float]:
    """ICC(1), unbalanced one-way random effects. Targets are
    candidate×dimension cells; measurements are the raters in that cell."""
    valid = [g for g in groups if len(g) >= 1]
    k = len(valid)
    if k < 2:
        return None
    N = sum(len(g) for g in valid)
    if N <= k:
        return None
    all_vals = [x for g in valid for x in g]
    grand = _mean(all_vals)
    ssb = 0.0
    ssw = 0.0
    sum_ni2 = 0.0
    for g in valid:
        gm = _mean(g)
        ssb += len(g) * (gm - grand) ** 2
        ssw += sum((x - gm) ** 2 for x in g)
        sum_ni2 += len(g) * len(g)
    msb = ssb / (k - 1)
    msw = ssw / (N - k)
    k0 = (N - sum_ni2 / N) / (k - 1)
    denom = msb + (k0 - 1) * msw
    if abs(denom) < 1e-9:
        return None
    return (msb - msw) / denom


def _icc_band(icc: Optional[float]) -> Optional[ICCBand]:
    if icc is None:
        return None
    if icc >= 0.75:
        return "excellent"
    if icc >= 0.6:
        return "good"
    if icc >= 0.4:
        return "fair"
    if icc >= 0.2:
        return "poor"
    return "unreliable"


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


# ---------- main ----------

def compute_calibration(
    role_id: str,
    interviewers: list[Interviewer],
    ratings: list[PanelRating],
    candidates: list[CandidateLite],
    rubric: list[RubricLite],
    generated_at: int = 0,
) -> CalibrationResult:
    iv_by_id = {iv.id: iv for iv in interviewers}
    cand_by_id = {c.id: c for c in candidates}
    dim_by_key = {d.key: d for d in rubric}

    valid = [
        r for r in ratings
        if r.interviewer_id in iv_by_id
        and r.candidate_id in cand_by_id
        and r.dim_key in dim_by_key
        and isinstance(r.rating, (int, float))
    ]

    def cell_key(cid: int, dk: str) -> str:
        return f"{cid}|{dk}"

    by_cell: dict[str, list[tuple[str, float]]] = {}
    by_rater: dict[str, list[tuple[str, float]]] = {}
    for r in valid:
        ck = cell_key(r.candidate_id, r.dim_key)
        by_cell.setdefault(ck, []).append((r.interviewer_id, r.rating))
        by_rater.setdefault(r.interviewer_id, []).append((ck, r.rating))

    cell_mean = {ck: _mean([x[1] for x in rs]) for ck, rs in by_cell.items()}
    grand_mean = _mean([r.rating for r in valid]) if valid else 0.0
    name_by_id = {iv.id: iv.name for iv in interviewers}

    # ---- per-rater stats ----
    raters: list[RaterStat] = []
    leniency_by_id: dict[str, float] = {}
    for iv in interviewers:
        own = by_rater.get(iv.id, [])
        own_ratings = [o[1] for o in own]
        consensus_for_own = [cell_mean.get(o[0], o[1]) for o in own]
        leniency = _mean([o[1] - cell_mean.get(o[0], o[1]) for o in own]) if own else 0.0
        spread = _pstd(own_ratings)
        corr = _pearson(own_ratings, consensus_for_own)

        flags: list[RaterFlag] = []
        if leniency >= LENIENCY_THRESHOLD:
            flags.append("lenient")
        if leniency <= -LENIENCY_THRESHOLD:
            flags.append("severe")
        if len(own) >= 3 and spread < FLAT_SPREAD:
            flags.append("flat")
        if corr is not None and corr < CONTRARIAN_CORR:
            flags.append("contrarian")

        band: RaterBand = (
            "lenient" if leniency >= LENIENCY_THRESHOLD
            else "severe" if leniency <= -LENIENCY_THRESHOLD
            else "calibrated"
        )
        leniency_by_id[iv.id] = _r(leniency, 3)
        raters.append(RaterStat(
            interviewer_id=iv.id, name=iv.name, title=iv.title,
            leniency=_r(leniency, 3), spread=_r(spread, 3),
            consensus_corr=None if corr is None else _r(corr, 3),
            count=len(own), band=band, flags=flags,
        ))

    # ---- cells ----
    cells: list[CellInfo] = []
    for cand in candidates:
        for dim in rubric:
            ck = cell_key(cand.id, dim.key)
            rs = by_cell.get(ck)
            if not rs:
                continue
            vals = [x[1] for x in rs]
            v = _pvar(vals)
            n = len(vals)
            cell_ratings = sorted(
                [CellRating(iid, name_by_id.get(iid, iid), rat) for iid, rat in rs],
                key=lambda cr: cr.name,
            )
            cells.append(CellInfo(
                candidate_id=cand.id, candidate_name=cand.name,
                dim_key=dim.key, dim_label=dim.label,
                ratings=cell_ratings,
                mean=_mean(vals), spread=_pstd(vals),
                range=max(vals) - min(vals), n=n,
                agreement=_r(_clamp(1 - v / MAX_CELL_VAR, 0, 1), 3) if n >= 2 else None,
            ))

    multi_rated = [c for c in cells if c.n >= 2]
    single_rater_cells = sum(1 for c in cells if c.n == 1)
    multi_rated_cells = len(multi_rated)
    consensus_index = (
        _r(_mean([c.agreement for c in multi_rated]), 3) if multi_rated else None
    )

    # ---- per-candidate composites ----
    def composite(mean_by_dim: dict[str, float]) -> tuple[Optional[int], int]:
        total_w = 0.0
        rated = 0
        for dim in rubric:
            if dim.key in mean_by_dim:
                total_w += dim.weight
                rated += 1
        if rated == 0 or total_w <= 0:
            return None, 0
        acc = 0.0
        for dim in rubric:
            if dim.key not in mean_by_dim:
                continue
            norm = (_clamp(mean_by_dim[dim.key], 1, 5) - 1) / 4
            acc += norm * (dim.weight / total_w) * 100
        return int(math.floor(acc + 0.5)), rated

    pre: list[dict] = []
    for cand in candidates:
        raw_by_dim: dict[str, float] = {}
        cal_by_dim: dict[str, float] = {}
        has_single = False
        cand_agreements: list[float] = []
        for dim in rubric:
            ck = cell_key(cand.id, dim.key)
            rs = by_cell.get(ck)
            if not rs:
                continue
            raw_by_dim[dim.key] = _mean([x[1] for x in rs])
            adj = [rat - leniency_by_id.get(iid, 0.0) for iid, rat in rs]
            cal_by_dim[dim.key] = _mean(adj)
            if len(rs) == 1:
                has_single = True
            cell = next(
                (c for c in cells if c.candidate_id == cand.id and c.dim_key == dim.key),
                None,
            )
            if cell and cell.agreement is not None:
                cand_agreements.append(cell.agreement)
        raw_val, raw_rated = composite(raw_by_dim)
        cal_val, _ = composite(cal_by_dim)
        total_dims = len(rubric)
        confidence = raw_rated / total_dims if total_dims else 0.0
        consensus = _r(_mean(cand_agreements), 3) if cand_agreements else None

        flags: list[CandFlag] = []
        if has_single:
            flags.append("single_rater")
        if consensus is not None and consensus < 0.5:
            flags.append("high_disagreement")
        if confidence < 0.5:
            flags.append("thin")

        pre.append({
            "candidate_id": cand.id, "name": cand.name,
            "role": cand.role, "location": cand.location,
            "raw_composite": raw_val, "calibrated_composite": cal_val,
            "confidence": confidence, "rated_dims": raw_rated,
            "total_dims": total_dims, "consensus": consensus, "flags": flags,
        })

    def rank_by(key: str) -> dict[int, int]:
        def sort_key(p: dict):
            v = p[key]
            # nulls last; higher composite first; tie-break candidate id asc
            return (0 if v is not None else 1, -(v if v is not None else 0), p["candidate_id"])
        ordered = sorted(pre, key=sort_key)
        return {p["candidate_id"]: i + 1 for i, p in enumerate(ordered)}

    raw_ranks = rank_by("raw_composite")
    cal_ranks = rank_by("calibrated_composite")

    candidate_scores: list[CandidateScore] = []
    for p in pre:
        raw_rank = raw_ranks.get(p["candidate_id"], 0)
        cal_rank = cal_ranks.get(p["candidate_id"], 0)
        rc, cc = p["raw_composite"], p["calibrated_composite"]
        delta = 0 if rc is None or cc is None else cc - rc
        candidate_scores.append(CandidateScore(
            candidate_id=p["candidate_id"], name=p["name"],
            role=p["role"], location=p["location"],
            raw_composite=rc, calibrated_composite=cc, delta=delta,
            raw_rank=raw_rank, calibrated_rank=cal_rank,
            rank_shift=raw_rank - cal_rank,
            confidence=p["confidence"], rated_dims=p["rated_dims"],
            total_dims=p["total_dims"], consensus=p["consensus"],
            flags=p["flags"],
        ))
    candidate_scores.sort(key=lambda c: c.calibrated_rank)
    rank_shift_count = sum(1 for c in candidate_scores if c.rank_shift != 0)

    # ---- ICC over multi-rated cells (unbalanced one-way) ----
    icc_groups = [[r.rating for r in c.ratings] for c in multi_rated]
    raw_icc = _icc_one_way(icc_groups)
    icc: Optional[float] = None if raw_icc is None else _r(raw_icc, 3)
    icc_band = _icc_band(icc)
    cal_groups = [
        [r.rating - leniency_by_id.get(r.interviewer_id, 0.0) for r in c.ratings]
        for c in multi_rated
    ]
    raw_icc_cal = _icc_one_way(cal_groups)
    icc_calibrated: Optional[float] = None if raw_icc_cal is None else _r(raw_icc_cal, 3)
    icc_calibrated_band = _icc_band(icc_calibrated)

    # ---- hot cells ----
    hot_cells = sorted(
        [c for c in multi_rated if c.range >= HOT_RANGE],
        key=lambda c: (-c.range, -c.spread),
    )[:8]

    biased_raters = sum(
        1 for r in raters if "lenient" in r.flags or "severe" in r.flags
    )

    # ---- verdict ----
    ci = consensus_index or 0.0
    if multi_rated_cells == 0:
        verdict: Verdict = "unreliable"
    elif ci >= 0.8 and biased_raters == 0 and (icc is None or icc >= 0.6):
        verdict = "calibrated"
    elif ci >= 0.62 and biased_raters <= 1:
        verdict = "minor_drift"
    elif ci >= 0.45:
        verdict = "needs_calibration"
    else:
        verdict = "unreliable"

    # ---- notes ----
    notes: list[str] = []
    if len(interviewers) < 2:
        notes.append("Add at least two interviewers per candidate so agreement can be measured.")
    if multi_rated_cells == 0 and len(interviewers) >= 2:
        notes.append("No candidate-dimension was scored by more than one interviewer yet — overlap the panel to measure agreement.")
    if icc is None and multi_rated_cells > 0:
        notes.append("Not enough overlapping ratings for a reliability (ICC) estimate — overlap more raters per cell.")
    rated_cands = len({r.candidate_id for r in valid})
    if 0 < rated_cands < 3:
        plural = "" if rated_cands == 1 else "s"
        notes.append(f"Only {rated_cands} candidate{plural} scored — reliability and rank shifts are directional until more are added.")

    # ---- suggestions ----
    suggestions: list[str] = []
    for r in raters:
        if "lenient" in r.flags:
            suggestions.append(f"{r.name} rates +{_r(r.leniency, 2):.2f} above consensus on average — recalibrate or weight their scores down.")
        elif "severe" in r.flags:
            suggestions.append(f"{r.name} rates {_r(r.leniency, 2):.2f} below consensus on average — recalibrate or weight their scores up.")
    for r in raters:
        if "flat" in r.flags:
            suggestions.append(f"{r.name}'s ratings barely vary (spread {_r(r.spread, 2):.2f}) — push the middle apart with anchored rubric examples.")
    for r in raters:
        if "contrarian" in r.flags and "lenient" not in r.flags and "severe" not in r.flags:
            suggestions.append(f"{r.name} correlates only {_r(r.consensus_corr or 0.0, 2):.2f} with the panel — pair-review before trusting solo verdicts.")

    raw_top = min(candidate_scores, key=lambda c: c.raw_rank, default=None)
    cal_top = min(candidate_scores, key=lambda c: c.calibrated_rank, default=None)
    if raw_top and cal_top and raw_top.candidate_id != cal_top.candidate_id:
        suggestions.append(f"De-biasing flips the top pick from {raw_top.name} to {cal_top.name} — the lead was a rater-bias artefact.")
    elif rank_shift_count > 0:
        plural = "" if rank_shift_count == 1 else "s"
        suggestions.append(f"Removing rater bias reorders {rank_shift_count} candidate{plural} — review the moved rows before deciding.")
    if hot_cells:
        h = hot_cells[0]
        spread = "/".join(str(int(x.rating)) if float(x.rating).is_integer() else str(x.rating) for x in h.ratings)
        suggestions.append(f"Biggest split: {h.candidate_name} on {h.dim_label} ({spread}) — discuss this dimension before locking a decision.")
    if icc is not None and icc_band:
        if icc_calibrated is not None and icc_calibrated_band and icc_calibrated - icc >= 0.1:
            suggestions.append(f"Reliability is ICC {_r(icc, 2):.2f} ({ICC_BAND_LABEL[icc_band].lower()}) raw, but {_r(icc_calibrated, 2):.2f} ({ICC_BAND_LABEL[icc_calibrated_band].lower()}) once rater bias is removed — calibration recovers the panel's signal.")
        else:
            tail = "the ranking is trustworthy." if icc >= 0.6 else "individual scorecards carry real noise; lean on the panel mean."
            suggestions.append(f"Panel reliability ICC = {_r(icc, 2):.2f} ({ICC_BAND_LABEL[icc_band].lower()}) — {tail}")
    if not suggestions and multi_rated_cells > 0:
        suggestions.append("Panel is well-calibrated — interviewers agree and no systematic rater bias detected.")

    return CalibrationResult(
        role_id=role_id, raters=raters, candidates=candidate_scores,
        cells=cells, hot_cells=hot_cells,
        consensus_index=consensus_index, icc=icc, icc_band=icc_band,
        icc_calibrated=icc_calibrated, icc_calibrated_band=icc_calibrated_band,
        rank_shift_count=rank_shift_count,
        single_rater_cells=single_rater_cells,
        multi_rated_cells=multi_rated_cells, biased_raters=biased_raters,
        grand_mean=grand_mean, verdict=verdict, rubric=rubric,
        suggestions=suggestions, notes=notes, generated_at=generated_at,
    )
