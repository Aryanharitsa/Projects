from pydantic import BaseModel, EmailStr

class CandidateCreate(BaseModel):
    name: str
    email: EmailStr
    skills: str | None = None

class CandidateOut(BaseModel):
    id: int
    name: str
    email: EmailStr
    skills: str | None = None

    class Config:
        from_attributes = True
