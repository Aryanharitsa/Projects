from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class NoteIn(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    body:  str = ""
    tags:  str = ""


class NoteOut(BaseModel):
    id: int
    title: str
    body: str
    tags: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class SynapseOut(BaseModel):
    source_id: int
    target_id: int
    strength: float


class GraphNode(BaseModel):
    id: int
    title: str
    tags: List[str]
    size: int           # degree centrality (# of synapses)
    created_at: datetime


class GraphEdge(BaseModel):
    source: int
    target: int
    strength: float


class GraphOut(BaseModel):
    nodes: List[GraphNode]
    edges: List[GraphEdge]
    stats: dict
