from datetime import datetime
from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.db import Base


class Note(Base):
    """A single thought / note. Each note becomes a node in the synapse graph."""
    __tablename__ = "notes"

    id         = Column(Integer, primary_key=True)
    title      = Column(String(200), nullable=False)
    body       = Column(Text, nullable=False, default="")
    tags       = Column(String(400), nullable=False, default="")   # space-separated
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow,
                        onupdate=datetime.utcnow, nullable=False)

    # outgoing edges (this note → other note)
    synapses_out = relationship(
        "Synapse",
        foreign_keys="Synapse.source_id",
        back_populates="source",
        cascade="all, delete-orphan",
    )
    # incoming edges (other note → this note)
    synapses_in = relationship(
        "Synapse",
        foreign_keys="Synapse.target_id",
        back_populates="target",
        cascade="all, delete-orphan",
    )


class Synapse(Base):
    """A weighted edge between two notes. Direction is symmetric in meaning
    but we store a canonical (source_id < target_id) form to avoid duplicates."""
    __tablename__ = "synapses"

    id        = Column(Integer, primary_key=True)
    source_id = Column(Integer, ForeignKey("notes.id", ondelete="CASCADE"),
                       nullable=False, index=True)
    target_id = Column(Integer, ForeignKey("notes.id", ondelete="CASCADE"),
                       nullable=False, index=True)
    strength  = Column(Float, nullable=False, default=0.0)

    source = relationship("Note", foreign_keys=[source_id],
                          back_populates="synapses_out")
    target = relationship("Note", foreign_keys=[target_id],
                          back_populates="synapses_in")
