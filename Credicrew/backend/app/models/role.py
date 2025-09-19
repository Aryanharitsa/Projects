from sqlalchemy import Column, Integer, String, ForeignKey
from app.db.base import Base

class Role(Base):
    __tablename__ = "roles"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=True)
