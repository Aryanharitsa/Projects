from sqlalchemy import Column, Integer, String
from app.db.base import Base

class Candidate(Base):
    __tablename__ = "candidates"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    email = Column(String(320), unique=True, nullable=False)
    # MVP: store skills as comma-separated text
    skills = Column(String, nullable=True)
