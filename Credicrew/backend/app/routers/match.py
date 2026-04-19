from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.matcher import score_candidate, to_dict

router = APIRouter(prefix="/match", tags=["match"])


class CandidatePayload(BaseModel):
    id: int | None = None
    name: str
    role: str
    location: str = ""
    years: int = 0
    tags: list[str] = []
    availability: str | None = None


class MatchRequest(BaseModel):
    jd: str = Field(..., min_length=4, description="Free-text job description")
    candidates: list[CandidatePayload]
    top_k: int = 25


class CandidateMatch(BaseModel):
    candidate: CandidatePayload
    score: float
    breakdown: dict
    matched_skills: list[str]
    missing_skills: list[str]
    reasons: list[str]


class MatchResponse(BaseModel):
    count: int
    results: list[CandidateMatch]


@router.post("", response_model=MatchResponse)
def rank(req: MatchRequest) -> MatchResponse:
    if not req.candidates:
        raise HTTPException(status_code=400, detail="No candidates provided")
    scored: list[CandidateMatch] = []
    for c in req.candidates:
        r = score_candidate(
            req.jd,
            role=c.role,
            location=c.location,
            years=c.years,
            tags=c.tags,
            availability=c.availability,
        )
        scored.append(CandidateMatch(candidate=c, **to_dict(r)))
    scored.sort(key=lambda x: x.score, reverse=True)
    return MatchResponse(count=len(scored), results=scored[: req.top_k])
