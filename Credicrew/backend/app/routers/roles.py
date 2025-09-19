from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.role import Role
from app.schemas.role import RoleCreate, RoleOut

router = APIRouter(prefix="/roles", tags=["roles"])

@router.get("", response_model=list[RoleOut])
def list_roles(db: Session = Depends(get_db)):
    return db.query(Role).all()

@router.post("", response_model=RoleOut, status_code=201)
def create_role(payload: RoleCreate, db: Session = Depends(get_db)):
    role = Role(title=payload.title, company_id=payload.company_id)
    db.add(role)
    db.commit()
    db.refresh(role)
    return role
