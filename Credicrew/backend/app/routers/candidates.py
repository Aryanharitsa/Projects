from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.candidate import Candidate
from app.schemas.candidate import CandidateCreate, CandidateOut

router = APIRouter(prefix="/candidates", tags=["candidates"])

@router.get("", response_model=list[CandidateOut])
def list_candidates(db: Session = Depends(get_db)):
    return db.query(Candidate).all()

@router.post("", response_model=CandidateOut, status_code=201)
def create_candidate(payload: CandidateCreate, db: Session = Depends(get_db)):
    c = Candidate(name=payload.name, email=payload.email, skills=payload.skills)
    db.add(c)
    db.commit()
    db.refresh(c)
    return c
