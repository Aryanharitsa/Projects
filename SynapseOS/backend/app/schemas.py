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


# ----------------------------------------------------------------- trails


class TrailStepIn(BaseModel):
    note_id: int = Field(..., ge=1)
    caption: str = Field(default="", max_length=400)


class TrailIn(BaseModel):
    title: str = Field(..., min_length=1, max_length=140)
    description: str = Field(default="", max_length=1000)
    steps: list[TrailStepIn] = Field(default_factory=list)
    origin: Literal["manual", "path", "chat"] = "manual"


class TrailPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=140)
    description: str | None = Field(default=None, max_length=1000)
    steps: list[TrailStepIn] | None = None


class TrailAppend(BaseModel):
    note_id: int = Field(..., ge=1)
    caption: str = Field(default="", max_length=400)


class TrailStepOut(BaseModel):
    note_id: int
    title: str
    snippet: str
    tags: list[str]
    caption: str
    exists: bool
    cluster_id: int | None = None
    cluster_name: str | None = None
    cluster_color: str | None = None
    strength_to_next: float | None = None
    is_synapse_to_next: bool = False


class TrailOut(BaseModel):
    id: int
    title: str
    description: str
    origin: str
    created_at: str
    updated_at: str
    threshold: float
    top_k: int
    health: float
    total_strength: float
    missing_count: int
    clusters_touched: list[int]
    steps: list[TrailStepOut]


class TrailSummaryOut(BaseModel):
    id: int
    title: str
    description: str
    origin: str
    created_at: str
    updated_at: str
    step_count: int
    health: float
    missing_count: int


class TrailSuggestionOut(BaseModel):
    note_id: int
    title: str
    snippet: str
    tags: list[str]
    strength: float
    cluster_id: int | None = None
    cluster_name: str | None = None
    cluster_color: str | None = None


class TrailSuggestionsOut(BaseModel):
    trail_id: int
    threshold: float
    suggestions: list[TrailSuggestionOut]


# --------------------------------------------------------------- distill


class AtomizeRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=120_000)
    mode: Literal["auto", "heuristic", "llm"] = "auto"


class AtomNeighborOut(BaseModel):
    note_id: int
    title: str
    strength: float
    cluster_id: int | None = None
    cluster_color: str | None = None


class AtomPreviewOut(BaseModel):
    temp_id: str
    title: str
    body: str
    tags: list[str]
    char_count: int
    cluster_id: int | None = None
    cluster_name: str | None = None
    cluster_color: str | None = None
    cluster_strength: float
    neighbors: list[AtomNeighborOut]
    expected_synapses: int
    llm_refined: bool = False


class AtomizeOut(BaseModel):
    atoms: list[AtomPreviewOut]
    total_chars: int
    mode_used: Literal["heuristic", "llm"]
    llm_available: bool
    llm_provider: str | None = None
    notice: str | None = None


class AtomCommitIn(BaseModel):
    title: str = Field(..., min_length=1, max_length=140)
    body: str = Field(..., min_length=1, max_length=8000)
    tags: list[str] = Field(default_factory=list)


class AtomizeCommitRequest(BaseModel):
    atoms: list[AtomCommitIn] = Field(..., min_length=1, max_length=64)


class AtomCommitResult(BaseModel):
    note_id: int
    title: str
    synapses: int


class AtomizeCommitOut(BaseModel):
    created: list[AtomCommitResult]
    synapses_formed: int  # total new edges introduced by the bulk insert


# --------------------------------------------------------------- synthesis


class DigestSourceOut(BaseModel):
    ref: int
    note_id: int
    title: str
    centrality: float


class DigestClaimOut(BaseModel):
    text: str
    note_id: int
    ref: int


class OpenThreadOut(BaseModel):
    note_id: int
    title: str
    text: str
    kind: Literal["question", "underdeveloped"]


class BridgeOut(BaseModel):
    note_id: int
    title: str
    cluster_id: int
    cluster_name: str
    cluster_color: str
    strength: float


class ClusterDigestOut(BaseModel):
    cluster_id: int
    name: str
    color: str
    size: int
    terms: list[str]
    cohesion: float
    overview: str
    claims: list[DigestClaimOut]
    open_threads: list[OpenThreadOut]
    bridges: list[BridgeOut]
    sources: list[DigestSourceOut]
    mode_used: Literal["extractive", "llm"]
    llm_available: bool
    llm_provider: str | None = None
    notice: str | None = None
