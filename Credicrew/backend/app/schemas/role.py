from pydantic import BaseModel

class RoleCreate(BaseModel):
    title: str
    company_id: int | None = None

class RoleOut(BaseModel):
    id: int
    title: str
    company_id: int | None = None

    class Config:
        from_attributes = True
