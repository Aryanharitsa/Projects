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


# --------------------------------------------------------------- tensions


class TensionSignalOut(BaseModel):
    kind: Literal["polarity", "antonym", "contrast", "title"]
    weight: float
    detail: str


class TensionEvidenceOut(BaseModel):
    note_id: int
    title: str
    sentence: str
    polarity: int


class TensionOut(BaseModel):
    a_id: int
    a_title: str
    b_id: int
    b_title: str
    cosine: float
    magnitude: float
    signals: list[TensionSignalOut]
    evidence: list[TensionEvidenceOut]
    bridge_title: str
    bridge_prompt: str
    bridge_tags: list[str]
    kind: Literal["internal", "cross"]
    cluster_a: int | None = None
    cluster_a_name: str | None = None
    cluster_a_color: str | None = None
    cluster_b: int | None = None
    cluster_b_name: str | None = None
    cluster_b_color: str | None = None


class TensionReportOut(BaseModel):
    threshold: float
    floor: float
    total_pairs_scanned: int
    candidate_count: int
    tension_count: int
    tensions: list[TensionOut]
    stats: dict


# ------------------------------------------------------------------ echo


class EchoMemberOut(BaseModel):
    note_id: int
    title: str
    body: str
    tags: list[str]
    created_at: str
    body_len: int
    is_canonical: bool
    centrality: float


class EchoPairOut(BaseModel):
    a_id: int
    b_id: int
    cosine: float


class EchoSentenceOut(BaseModel):
    text: str
    note_ids: list[int]
    is_duplicate: bool
    is_canonical_source: bool


class EchoClusterOut(BaseModel):
    cluster_id: str
    size: int
    redundancy: float
    peak_cosine: float
    wasted_chars: int
    chars_total: int
    chars_unique: int
    canonical_id: int
    members: list[EchoMemberOut]
    pairs: list[EchoPairOut]
    merged_title: str
    merged_body: str
    merged_tags: list[str]
    sentences: list[EchoSentenceOut]
    overlap_ratio: float


class EchoReportOut(BaseModel):
    threshold: float
    total_notes: int
    candidate_pairs: int
    cluster_count: int
    skipped_pair_count: int
    clusters: list[EchoClusterOut]
    stats: dict


class EchoPreviewRequest(BaseModel):
    note_ids: list[int] = Field(..., min_length=2, max_length=8)
    canonical_id: int | None = Field(default=None, ge=1)


class EchoMergeRequest(BaseModel):
    note_ids: list[int] = Field(..., min_length=2, max_length=8)
    canonical_id: int | None = Field(default=None, ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=140)
    body: str | None = Field(default=None, min_length=1, max_length=12000)
    tags: list[str] | None = None


class EchoMergeResult(BaseModel):
    merged_note_id: int
    merged_title: str
    deleted_ids: list[int]
    wasted_chars_recovered: int
    final_synapses: int


class EchoSkipRequest(BaseModel):
    pairs: list[tuple[int, int]] = Field(..., min_length=1, max_length=64)
    reason: str = Field(default="", max_length=400)


class EchoSkipResult(BaseModel):
    inserted: int
    total_skips: int


class EchoSkipEntry(BaseModel):
    a_id: int
    b_id: int
    reason: str
    created_at: str


# ----------------------------------------------------------------- atlas


class AtlasClusterOut(BaseModel):
    id: int
    name: str
    color: str
    size: int
    terms: list[str]
    cohesion: float
    internal_density: float
    activity: float
    growth_velocity: int
    last_touched_days: int | None = None
    newest_age_days: int
    mean_age_days: float
    bridge_count: int
    has_synapses: bool
    quadrant: Literal["stronghold", "frontier", "vault", "drift"]


class AtlasRecommendationOut(BaseModel):
    cluster_id: int
    cluster_name: str
    cluster_color: str
    kind: Literal["synthesize", "split", "revisit", "dissolve", "bridge"]
    priority: float
    headline: str
    detail: str


class AtlasReportOut(BaseModel):
    window_days: int
    generated_at: str
    total_notes: int
    total_clusters: int
    clusters: list[AtlasClusterOut]
    recommendations: list[AtlasRecommendationOut]
    summary: dict


# ------------------------------------------------------------- chronicle


class ChronicleChapterOut(BaseModel):
    index: int
    date_start: str
    date_end: str
    span_days: int
    count: int
    terms: list[str]
    anchor_id: int
    anchor_title: str
    anchor_sentence: str
    member_ids: list[int]
    drift_in: float


class ChronicleClusterOut(BaseModel):
    cluster_id: int
    name: str
    color: str
    size: int
    chapter_count: int
    total_drift: float
    peak_drift: float
    pivot_index: int | None = None
    stability: float
    category: Literal["calm", "shifting", "pivoting"]
    span_days: int
    cadence_days: float
    emerged_terms: list[str]
    faded_terms: list[str]
    headline: str
    chapters: list[ChronicleChapterOut]


class ChronicleReportOut(BaseModel):
    generated_at: str
    total_notes: int
    total_clusters: int
    eligible_clusters: int
    target_chapters: int
    min_cluster_notes: int
    min_span_days: float
    clusters: list[ChronicleClusterOut]
    summary: dict


# ----------------------------------------------------------------- pulse


class PulseDayOut(BaseModel):
    date: str
    created: int
    revisited: int


class PulseClusterOut(BaseModel):
    cluster_id: int
    name: str
    color: str
    size: int
    new_count: int
    revisits_count: int
    share_new: float
    momentum: float
    centroid_drift: float | None = None
    status: Literal["born", "emerging", "hot", "warm", "dormant"]
    last_touched_days: int | None = None
    new_terms: list[str]
    hot_titles: list[str]


class PulseBridgeOut(BaseModel):
    source_id: int
    source_title: str
    target_id: int
    target_title: str
    source_cluster_id: int
    source_cluster_name: str
    source_cluster_color: str
    target_cluster_id: int
    target_cluster_name: str
    target_cluster_color: str
    strength: float
    source_is_new: bool
    target_is_new: bool


class PulseHubOut(BaseModel):
    note_id: int
    title: str
    snippet: str
    tags: list[str]
    degree: int
    weight: float
    cluster_id: int | None = None
    cluster_name: str | None = None
    cluster_color: str | None = None
    days_old: int


class PulseRecommendationOut(BaseModel):
    kind: Literal["synthesize", "name", "revisit", "bridge", "hub"]
    headline: str
    detail: str
    cluster_id: int | None = None
    cluster_name: str | None = None
    cluster_color: str | None = None
    note_id: int | None = None
    priority: float


class PulseReportOut(BaseModel):
    window_days: int
    generated_at: str
    window_start: str
    headline: str
    total_notes: int
    new_notes: int
    revisited_notes: int
    words_written: int
    streak_days: int
    synapses_total: int
    bridges_born: int
    hubs_born: int
    clusters_total: int
    clusters_hot: int
    clusters_emerging: int
    clusters_dormant: int
    activity: list[PulseDayOut]
    clusters: list[PulseClusterOut]
    bridges: list[PulseBridgeOut]
    hubs: list[PulseHubOut]
    emerged_terms: list[str]
    faded_terms: list[str]
    recommendations: list[PulseRecommendationOut]
    summary: dict


# ----------------------------------------------------------------- spark


class SparkEvidenceOut(BaseModel):
    note_id: int
    title: str
    snippet: str
    cluster_id: int | None = None
    cluster_name: str | None = None
    cluster_color: str | None = None


class SparkPredictedSynapseOut(BaseModel):
    note_id: int
    title: str
    strength: float


class SparkOut(BaseModel):
    id: str
    kind: Literal["bridge", "distill", "counter", "frontier", "revive"]
    priority: float
    title: str
    body: str
    tags: list[str]
    rationale: str
    headline: str
    cited_evidence: list[SparkEvidenceOut]
    predicted_cluster_id: int | None = None
    predicted_cluster_name: str | None = None
    predicted_cluster_color: str | None = None
    predicted_cluster_strength: float
    predicted_synapses: list[SparkPredictedSynapseOut]
    expected_synapse_count: int
    bridge_cluster_a_id: int | None = None
    bridge_cluster_a_name: str | None = None
    bridge_cluster_a_color: str | None = None
    bridge_cluster_b_id: int | None = None
    bridge_cluster_b_name: str | None = None
    bridge_cluster_b_color: str | None = None
    bridge_centroid_cosine: float = 0.0


class SparkReportOut(BaseModel):
    generated_at: str
    total_notes: int
    total_clusters: int
    sparks: list[SparkOut]
    summary: dict


# --------------------------------------------------------------- compass


class CompassQuestionIn(BaseModel):
    text: str = Field(..., min_length=2, max_length=600)


class CompassQuestionSummary(BaseModel):
    id: int
    text: str
    created_at: str
    archived_at: str | None = None
    reads_count: int
    last_read_at: str | None = None
    coverage_pct: float


class CompassReadIn(BaseModel):
    note_id: int = Field(..., ge=1)


class LensNoteOut(BaseModel):
    note_id: int
    title: str
    snippet: str
    tags: list[str]
    relevance: float
    info_gain: float
    cosine: float
    lexical: float
    title_hit: bool
    read: bool
    read_at: str | None = None
    cluster_id: int | None = None
    cluster_name: str | None = None
    cluster_color: str | None = None


class CompassCitationOut(BaseModel):
    ref: int
    note_id: int
    title: str
    excerpt: str
    relevance: float


class CompassSubquestionOut(BaseModel):
    term: str
    note_count: int
    covered: int
    coverage_pct: float
    sample_note_id: int


class CompassLensOut(BaseModel):
    question_id: int
    question_text: str
    created_at: str
    archived_at: str | None = None
    generated_at: str
    total_notes: int
    in_lens: int
    relevance_mass_total: float
    relevance_mass_read: float
    coverage_pct: float
    notes: list[LensNoteOut]
    frontiers: list[LensNoteOut]
    subquestions: list[CompassSubquestionOut]
    working_answer: str
    citations: list[CompassCitationOut]
    stats: dict
