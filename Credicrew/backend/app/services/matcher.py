"""Explainable candidate ↔ JD matching.

The scorer is deliberately transparent: every component returns a
breakdown (skills, role, location, seniority, availability) so the UI can
show *why* a candidate ranks where they do. No LLM, no embeddings — just
clear, fast, deterministic heuristics that anyone can audit and tune.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Iterable

WORD = re.compile(r"[A-Za-z][A-Za-z0-9+#.\-]{1,}")

LOCATIONS = {
    "remote", "bengaluru", "bangalore", "mumbai", "pune", "delhi",
    "ncr", "hyderabad", "kolkata", "chennai", "gurgaon", "noida",
}

SENIORITY_WORDS = {
    "intern": 0, "junior": 1, "entry": 1, "associate": 2, "mid": 4,
    "senior": 6, "staff": 8, "principal": 10, "lead": 7,
}

STOPWORDS = {
    "the", "and", "or", "of", "with", "for", "a", "an", "to", "in", "on",
    "at", "is", "be", "you", "we", "our", "their", "this", "that",
    "strong", "experience", "working", "must", "should", "have", "has",
    "plus", "good", "great", "preferred", "required", "team", "teams",
    "candidate", "candidates", "role", "roles", "job", "work", "years",
    "year", "yrs", "yr", "as", "such", "will", "build", "building",
}


@dataclass
class Breakdown:
    skills: float
    role: float
    location: float
    seniority: float
    availability: float


@dataclass
class MatchResult:
    score: float
    breakdown: Breakdown
    matched_skills: list[str]
    missing_skills: list[str]
    reasons: list[str]


def tokenize(text: str) -> list[str]:
    return [w.lower() for w in WORD.findall(text or "")]


def extract_terms(jd: str) -> tuple[set[str], int, set[str]]:
    """Return (skill_terms, target_years, locations) extracted from a JD."""
    tokens = tokenize(jd)
    skills = {t for t in tokens if t not in STOPWORDS and len(t) > 1}
    locations = {t for t in tokens if t in LOCATIONS}

    target_years = 0
    m = re.search(r"(\d+)\s*\+?\s*(?:yrs?|years?)", jd or "", re.I)
    if m:
        target_years = int(m.group(1))
    else:
        for word, val in SENIORITY_WORDS.items():
            if re.search(rf"\b{word}\b", jd or "", re.I):
                target_years = max(target_years, val)
    return skills, target_years, locations


def score_candidate(
    jd: str,
    *,
    role: str,
    location: str,
    years: int,
    tags: Iterable[str],
    availability: str | None = None,
) -> MatchResult:
    jd_skills, target_years, jd_locations = extract_terms(jd)
    tags = list(tags)
    cand_tag_set = {t.lower() for t in tags}

    matched = sorted([t for t in tags if t.lower() in jd_skills])
    candidate_jd_skills = {s for s in jd_skills if s.isalpha() and len(s) > 2}
    missing = sorted([s for s in (candidate_jd_skills - cand_tag_set)])[:8]

    skills_score = min(50.0, 8.0 * len(matched)) if matched else 0.0

    role_terms = set(tokenize(role))
    role_score = min(15.0, 5.0 * len(role_terms & jd_skills))

    loc = (location or "").lower()
    if jd_locations:
        if any(l in loc for l in jd_locations):
            loc_score = 10.0
        elif "remote" in jd_locations or "remote" in loc:
            loc_score = 7.0
        else:
            loc_score = 0.0
    else:
        loc_score = 5.0

    if target_years:
        diff = abs(years - target_years)
        sen_score = max(0.0, 15.0 - diff * 2.5)
    else:
        sen_score = 8.0

    avail = (availability or "").lower()
    if "immediate" in avail:
        avail_score = 10.0
    elif "30" in avail:
        avail_score = 7.0
    elif "open" in avail:
        avail_score = 5.0
    elif "60" in avail:
        avail_score = 4.0
    else:
        avail_score = 3.0

    total = min(100.0, round(
        skills_score + role_score + loc_score + sen_score + avail_score, 1
    ))

    reasons: list[str] = []
    if matched:
        head = ", ".join(matched[:5])
        more = f" +{len(matched) - 5} more" if len(matched) > 5 else ""
        reasons.append(f"+{round(skills_score)} skill overlap ({head}{more})")
    if role_score:
        reasons.append(f"+{round(role_score)} role title alignment")
    if loc_score:
        reasons.append(f"+{round(loc_score)} location fit")
    if sen_score:
        target = f"~{target_years}y" if target_years else "any seniority"
        reasons.append(f"+{round(sen_score)} seniority ({years}y vs {target})")
    if avail_score:
        reasons.append(f"+{round(avail_score)} availability")

    return MatchResult(
        score=total,
        breakdown=Breakdown(
            skills=round(skills_score, 1),
            role=round(role_score, 1),
            location=round(loc_score, 1),
            seniority=round(sen_score, 1),
            availability=round(avail_score, 1),
        ),
        matched_skills=matched,
        missing_skills=missing,
        reasons=reasons,
    )


def to_dict(r: MatchResult) -> dict:
    return asdict(r)
