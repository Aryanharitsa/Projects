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
    last_seen_at: str | None = None  # ISO8601, set by POST /notes/{id}/touch


class Node(BaseModel):
    id: int
    title: str
    body: str
    tags: list[str]
    degree: int
    # visual hint for the frontend: 0..1 importance score
    weight: float
    # Community membership (label-propagation cluster id) and the
    # palette color the frontend should paint this node with. Optional
    # because non-graph endpoints (search, neighbors) construct lighter
    # Node payloads without the cluster pass.
    community: int | None = None
    community_color: str | None = None


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


class CommunityOut(BaseModel):
    id: int
    name: str
    color: str
    size: int
    terms: list[str]
    member_ids: list[int]


class OrphanOut(BaseModel):
    note_id: int
    title: str
    suggested_id: int | None
    suggested_title: str | None
    suggested_strength: float
    suggested_threshold: float


class ChatRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    mode: Literal["auto", "extractive", "llm"] = "auto"
    k_seed: int = Field(default=4, ge=1, le=12)
    hops: int = Field(default=1, ge=0, le=2)
    threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    top_k: int | None = Field(default=None, ge=1, le=20)
    include_community_anchors: bool = True


class ChatCitation(BaseModel):
    note_id: int
    title: str
    snippet: str
    score: float
    role: Literal["seed", "synapse", "community"]
    via_seed_id: int | None = None
    via_strength: float = 0.0


class ChatExpansion(BaseModel):
    src: int
    dst: int
    strength: float
    kind: Literal["seed", "synapse", "community"]


class ChatTraversal(BaseModel):
    seeds: list[int]
    expansions: list[ChatExpansion]


class ChatOut(BaseModel):
    query: str
    answer: str
    citations: list[ChatCitation]
    traversal: ChatTraversal
    model: str
    mode_used: Literal["extractive", "llm"]
    latency_ms: int
    llm_available: bool
    llm_provider: str | None = None
    notice: str | None = None


# ------------------------------------------------------- daily brief


class BriefReason(BaseModel):
    kind: Literal["stale", "central", "orphan", "diverse"]
    text: str
    weight: float


class BriefConnection(BaseModel):
    note_id: int
    title: str
    strength: float
    cluster_id: int | None = None
    cluster_name: str | None = None


class BriefPickOut(BaseModel):
    note_id: int
    title: str
    snippet: str
    tags: list[str]
    score: float
    reasons: list[BriefReason]
    prompt: str
    connections: list[BriefConnection]
    cluster_id: int | None = None
    cluster_name: str | None = None
    cluster_color: str | None = None
    days_since_seen: int | None = None
    is_orphan: bool = False


class BriefOut(BaseModel):
    date: str
    k: int
    total_notes: int
    picks: list[BriefPickOut]
    stats: dict
