from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.services.match import plan_query, match_candidate
from app.services.outreach import compose_email, extract_pitch

router = APIRouter(prefix="/outreach", tags=["outreach"])


class CandidateIn(BaseModel):
    id: int | None = None
    name: str | None = None
    role: str | None = None
    location: str | None = None
    headline: str | None = None
    tags: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)


class OutreachRequest(BaseModel):
    """Request shape for composing an outreach email.

    Either provide a `jd` (free-text job description, parsed server-side)
    or pre-parsed `plan_skills` / `plan_location` / `plan_seniority`.
    """
    role_name: str | None = None
    jd: str | None = None
    plan_skills: list[str] | None = None
    plan_location: str | None = None
    plan_seniority: str | None = None
    pitch: str | None = None
    candidate: CandidateIn
    sender: str | None = None


@router.post("")
def outreach(body: OutreachRequest) -> dict:
    skills = body.plan_skills
    loc = body.plan_location
    sen = body.plan_seniority
    pitch = body.pitch

    if body.jd:
        plan = plan_query(body.jd)
        skills = skills or plan.skills
        loc = loc or plan.location
        sen = sen or plan.seniority
        pitch = pitch or extract_pitch(body.jd)

    matched: list[str] = []
    score: int | None = None
    if skills:
        # Reuse the explainable engine to surface the matched skills + score.
        from app.services.match import QueryPlan

        plan_obj = QueryPlan(text="", skills=skills, location=loc, seniority=sen)
        result = match_candidate(plan_obj, body.candidate.model_dump())
        matched = result.matched_skills
        score = result.score

    email = compose_email(
        role_name=body.role_name,
        plan_skills=skills,
        plan_location=loc,
        plan_seniority=sen,
        pitch=pitch,
        candidate_name=body.candidate.name,
        candidate_role=body.candidate.role,
        matched_skills=matched,
        score=score,
        sender=body.sender,
    )

    return {
        "subject": email.subject,
        "body": email.body,
        "context": {
            "role_name": body.role_name,
            "matched_skills": matched,
            "score": score,
            "plan": {"skills": skills, "location": loc, "seniority": sen},
        },
    }
