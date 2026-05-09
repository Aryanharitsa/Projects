"""Interview Kit HTTP surface.

Two endpoints:

* `POST /interview/plan` — given a JD (or pre-parsed plan) returns the
  rubric + question bank + empty stage records.
* `POST /interview/score` — given a rubric + stage records (with ratings),
  returns a composite + recommendation + per-dimension breakdown.
"""
from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.services.match import QueryPlan, plan_query
from app.services.interview import (
    RubricDim, build_plan, plan_as_dict, stages_from_payload,
    summarise, summary_as_dict,
)
from app.services.ics import Slot, build_calendar

router = APIRouter(prefix="/interview", tags=["interview"])


class PlanRequest(BaseModel):
    jd: str | None = None
    plan_skills: list[str] | None = None
    plan_location: str | None = None
    plan_seniority: str | None = None


@router.post("/plan")
def plan(body: PlanRequest) -> dict:
    if body.jd:
        qp = plan_query(body.jd)
    else:
        qp = QueryPlan(
            text="",
            skills=body.plan_skills or [],
            location=body.plan_location,
            seniority=body.plan_seniority,
        )
    return plan_as_dict(build_plan(qp))


class RubricIn(BaseModel):
    key: str
    label: str
    description: str = ""
    weight: float = 0.0
    source: str = "skill"


class StageIn(BaseModel):
    stage: str
    status: str = "planned"
    scores: list[dict] = Field(default_factory=list)
    signals: list[dict] = Field(default_factory=list)
    notes: str | None = None


class ScoreRequest(BaseModel):
    rubric: list[RubricIn]
    stages: list[StageIn]


@router.post("/score")
def score(body: ScoreRequest) -> dict:
    rubric = [
        RubricDim(
            key=r.key, label=r.label, description=r.description,
            weight=r.weight, source=r.source,
        )
        for r in body.rubric
    ]
    stages = stages_from_payload(rubric, [s.model_dump() for s in body.stages])
    return summary_as_dict(summarise(rubric, stages))


# ---------- iCal scheduling ----------

class _Attendee(BaseModel):
    email: str
    name: str | None = None


class _SlotIn(BaseModel):
    start_utc_ms: int
    duration_min: int = 60
    summary: str
    description: str | None = None
    location: str | None = None
    organizer_email: str | None = None
    organizer_name: str | None = None
    attendees: list[_Attendee] = Field(default_factory=list)
    uid: str | None = None


class IcsRequest(BaseModel):
    slots: list[_SlotIn]
    filename: str | None = None


@router.post("/ics")
def ics(body: IcsRequest) -> Response:
    """Build a single VCALENDAR with N VEVENTs and stream it back as
    text/calendar so the browser will offer to save it as a .ics file."""
    slots = [
        Slot(
            start_utc_ms=s.start_utc_ms,
            duration_min=s.duration_min,
            summary=s.summary,
            description=s.description,
            location=s.location,
            organizer_email=s.organizer_email,
            organizer_name=s.organizer_name,
            attendees=[a.model_dump(exclude_none=True) for a in s.attendees],
            uid=s.uid,
        )
        for s in body.slots
    ]
    body_text = build_calendar(slots)
    name = (body.filename or "interview").replace("/", "_") or "interview"
    if not name.endswith(".ics"):
        name = f"{name}.ics"
    return Response(
        content=body_text,
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )
