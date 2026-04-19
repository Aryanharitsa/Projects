"""Explainable match engine (Python mirror of frontend/src/lib/match.ts).

Given a free-text job query, score each candidate on skill coverage,
location, and seniority, returning a per-factor breakdown so the API
consumer can explain *why* the candidate matched.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from typing import Any, Iterable

ALIASES: dict[str, str] = {
    "reactjs": "react", "react.js": "react",
    "nextjs": "next.js",
    "nodejs": "node.js", "node": "node.js",
    "ts": "typescript",
    "js": "javascript",
    "py": "python",
    "postgresql": "postgres", "psql": "postgres",
    "fast api": "fastapi",
    "tailwindcss": "tailwind",
    "mongo": "mongodb",
    "k8s": "kubernetes",
    "golang": "go",
    "bangalore": "bengaluru",
}

SKILL_VOCAB: set[str] = {
    "react", "next.js", "vue", "svelte", "angular",
    "typescript", "javascript", "python", "go", "rust", "java", "kotlin", "swift",
    "fastapi", "flask", "django", "express", "nest.js", "spring",
    "postgres", "mysql", "mongodb", "redis", "kafka", "rabbitmq",
    "aws", "gcp", "azure", "docker", "kubernetes", "terraform",
    "graphql", "rest", "grpc",
    "tailwind", "css", "html", "sass",
    "node.js",
    "pandas", "numpy", "pytorch", "tensorflow", "scikit-learn", "ml", "nlp", "llm",
    "prisma", "sqlalchemy",
    "cypress", "jest", "playwright", "pytest",
}

LOCATION_VOCAB: set[str] = {
    "bengaluru", "mumbai", "delhi", "hyderabad", "chennai",
    "pune", "kolkata", "noida", "gurgaon", "ahmedabad", "kochi",
    "remote", "hybrid", "onsite",
}

SENIORITY = ("intern", "junior", "mid", "senior", "staff", "principal", "lead")

WEIGHTS = {"skill": 0.55, "loc": 0.15, "sen": 0.20, "base": 0.10}


@dataclass
class QueryPlan:
    text: str
    skills: list[str]
    location: str | None = None
    seniority: str | None = None


@dataclass
class MatchFactor:
    key: str
    label: str
    impact: int


@dataclass
class MatchResult:
    score: int
    matched_skills: list[str] = field(default_factory=list)
    missing_skills: list[str] = field(default_factory=list)
    seniority_wanted: str | None = None
    seniority_candidate: str | None = None
    seniority_match: bool = True
    location_wanted: str | None = None
    location_match: str = "full"
    factors: list[MatchFactor] = field(default_factory=list)


def _canon(token: str) -> str:
    t = re.sub(r"^[\W_]+|[\W_]+$", "", token.lower())
    return ALIASES.get(t, t)


def _tokens(text: str) -> list[str]:
    return [
        _canon(t)
        for t in re.split(r"\s+", re.sub(r"[()\[\]{},;/]", " ", text.lower()))
        if t
    ]


def extract_skills(text: str) -> list[str]:
    if not text:
        return []
    out: set[str] = set()
    for t in _tokens(text):
        if t in SKILL_VOCAB:
            out.add(t)
    lower = text.lower()
    for skill in SKILL_VOCAB:
        if ("." in skill or " " in skill) and skill in lower:
            out.add(skill)
    for phrase, target in ALIASES.items():
        if " " in phrase and phrase in lower and target in SKILL_VOCAB:
            out.add(target)
    return sorted(out)


def extract_location(text: str) -> str | None:
    if not text:
        return None
    m = re.search(r"\bin\s+([A-Za-z][A-Za-z\s]+?)(?:$|[.,;])", text, re.IGNORECASE)
    if m:
        loc = _canon(m.group(1).strip())
        if loc in LOCATION_VOCAB:
            return loc
    for t in _tokens(text):
        if t in LOCATION_VOCAB:
            return t
    return None


def extract_seniority(text: str) -> str | None:
    if not text:
        return None
    lower = text.lower()
    for s in SENIORITY:
        if re.search(rf"\b{s}\b", lower):
            return s
    return None


def plan_query(text: str) -> QueryPlan:
    return QueryPlan(
        text=text,
        skills=extract_skills(text),
        location=extract_location(text),
        seniority=extract_seniority(text),
    )


def match_candidate(plan: QueryPlan, c: dict[str, Any]) -> MatchResult:
    bag: set[str] = set()
    for src in (c.get("tags") or [], c.get("keywords") or [], (c.get("role") or "").split()):
        for t in src:
            ct = _canon(t)
            if ct:
                bag.add(ct)

    cand_loc_raw = (c.get("location") or "").split("(")[0]
    cand_loc = _canon(cand_loc_raw.strip())

    matched: list[str] = []
    missing: list[str] = []
    for s in plan.skills:
        (matched if s in bag else missing).append(s)
    skill_cov = 0.8 if not plan.skills else len(matched) / len(plan.skills)

    if not plan.location:
        loc_state = "full"
    elif cand_loc == plan.location or plan.location == "remote":
        loc_state = "full"
    elif cand_loc == "remote" or "hybrid" in cand_loc:
        loc_state = "partial"
    else:
        loc_state = "none"
    loc_score = {"full": 1.0, "partial": 0.5, "none": 0.0}[loc_state]

    cand_sen = extract_seniority(" ".join([c.get("role") or "", c.get("headline") or ""]))
    sen_match = plan.seniority == cand_sen if plan.seniority else True
    sen_score = (
        1.0 if not plan.seniority
        else 1.0 if sen_match
        else 0.3 if cand_sen
        else 0.6
    )

    raw = (
        WEIGHTS["skill"] * skill_cov
        + WEIGHTS["loc"] * loc_score
        + WEIGHTS["sen"] * sen_score
        + WEIGHTS["base"]
    )
    score = round(max(0.0, min(1.0, raw)) * 100)

    factors: list[MatchFactor] = [
        MatchFactor("base", "Baseline fit", round(WEIGHTS["base"] * 100)),
    ]
    if plan.skills:
        factors.append(MatchFactor(
            "skills",
            f"{len(matched)}/{len(plan.skills)} required skill{'' if len(plan.skills)==1 else 's'}",
            round(WEIGHTS["skill"] * 100 * skill_cov),
        ))
    else:
        factors.append(MatchFactor(
            "skills", "No specific skills requested",
            round(WEIGHTS["skill"] * 100 * skill_cov),
        ))
    if plan.location:
        label = (
            f"Location · {plan.location}" if loc_state == "full"
            else f"Location · {c.get('location') or cand_loc} (flex)" if loc_state == "partial"
            else f"Location · {c.get('location') or 'unknown'} (mismatch)"
        )
        factors.append(MatchFactor("location", label, round(WEIGHTS["loc"] * 100 * loc_score)))
    if plan.seniority:
        label = (
            f"Seniority · {plan.seniority}" if sen_match
            else f"Seniority · {cand_sen or 'unspecified'} (wanted {plan.seniority})"
        )
        factors.append(MatchFactor("seniority", label, round(WEIGHTS["sen"] * 100 * sen_score)))

    return MatchResult(
        score=score,
        matched_skills=matched,
        missing_skills=missing,
        seniority_wanted=plan.seniority,
        seniority_candidate=cand_sen,
        seniority_match=sen_match,
        location_wanted=plan.location,
        location_match=loc_state,
        factors=factors,
    )


def rank(plan: QueryPlan, candidates: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    results = []
    for c in candidates:
        r = match_candidate(plan, c)
        results.append({
            "candidate_id": c.get("id"),
            "name": c.get("name"),
            "match": {
                "score": r.score,
                "matched_skills": r.matched_skills,
                "missing_skills": r.missing_skills,
                "seniority": {
                    "wanted": r.seniority_wanted,
                    "candidate": r.seniority_candidate,
                    "match": r.seniority_match,
                },
                "location": {"wanted": r.location_wanted, "match": r.location_match},
                "factors": [asdict(f) for f in r.factors],
            },
        })
    results.sort(key=lambda x: -x["match"]["score"])
    return results
