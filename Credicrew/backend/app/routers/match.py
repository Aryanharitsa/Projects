from dataclasses import asdict

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.services.match import plan_query, rank

router = APIRouter(prefix="/match", tags=["match"])


class CandidateIn(BaseModel):
    id: int | None = None
    name: str | None = None
    role: str | None = None
    location: str | None = None
    headline: str | None = None
    tags: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)


class MatchRequest(BaseModel):
    query: str
    candidates: list[CandidateIn]


@router.post("")
def match(body: MatchRequest) -> dict:
    plan = plan_query(body.query)
    results = rank(plan, [c.model_dump() for c in body.candidates])
    return {"plan": asdict(plan), "results": results}
