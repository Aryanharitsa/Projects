"""Pydantic request/response models.

Kept minimal on purpose — the engine is the interesting part, not the API
surface. The `Node` / `Edge` / `Graph` shapes are stable and the frontend
depends on them verbatim.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class NoteIn(BaseModel):
    title: str = Field(..., min_length=1, max_length=140)
    body: str = Field(..., min_length=1, max_length=8000)
    tags: list[str] = Field(default_factory=list)


class NoteOut(BaseModel):
    id: int
    title: str
    body: str
    tags: list[str]
    created_at: str  # ISO8601


class Node(BaseModel):
    id: int
    title: str
    body: str
    tags: list[str]
    degree: int
    # visual hint for the frontend: 0..1 importance score
    weight: float


class Edge(BaseModel):
    source: int
    target: int
    strength: float  # cosine similarity in [0, 1]
    kind: Literal["synapse"] = "synapse"


class Graph(BaseModel):
    nodes: list[Node]
    edges: list[Edge]
    stats: dict[str, float]


class Neighbor(BaseModel):
    node: Node
    strength: float


class SearchHit(BaseModel):
    node: Node
    score: float


class PathStep(BaseModel):
    node: Node
    strength: float  # strength of the edge that led here (0 for origin)


class PathResult(BaseModel):
    found: bool
    path: list[PathStep]
    cost: float  # sum of (1 - strength) across path edges; lower = stronger
