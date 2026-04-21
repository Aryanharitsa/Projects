from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Note
from app.schemas import NoteIn, NoteOut
from app.services.synapse import rebuild_synapses

router = APIRouter(prefix="/notes", tags=["notes"])


@router.get("", response_model=List[NoteOut])
def list_notes(db: Session = Depends(get_db)):
    return db.query(Note).order_by(Note.updated_at.desc()).all()


@router.get("/{note_id}", response_model=NoteOut)
def get_note(note_id: int, db: Session = Depends(get_db)):
    note = db.get(Note, note_id)
    if not note:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Note not found")
    return note


@router.post("", response_model=NoteOut, status_code=status.HTTP_201_CREATED)
def create_note(payload: NoteIn, db: Session = Depends(get_db)):
    note = Note(title=payload.title.strip(),
                body=payload.body,
                tags=payload.tags.strip())
    db.add(note)
    db.commit()
    db.refresh(note)
    # Every write triggers a synapse rebuild. O(N²) but corpus is small.
    rebuild_synapses(db)
    return note


@router.put("/{note_id}", response_model=NoteOut)
def update_note(note_id: int, payload: NoteIn, db: Session = Depends(get_db)):
    note = db.get(Note, note_id)
    if not note:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Note not found")
    note.title = payload.title.strip()
    note.body = payload.body
    note.tags = payload.tags.strip()
    note.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(note)
    rebuild_synapses(db)
    return note


@router.delete("/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_note(note_id: int, db: Session = Depends(get_db)):
    note = db.get(Note, note_id)
    if not note:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Note not found")
    db.delete(note)
    db.commit()
    rebuild_synapses(db)


@router.post("/rebuild", status_code=status.HTTP_200_OK)
def rebuild(db: Session = Depends(get_db)):
    """Manual rebuild endpoint — useful after tweaking thresholds."""
    count = rebuild_synapses(db)
    return {"edges": count}
