export type Note = {
  id: number;
  title: string;
  body: string;
  tags: string[];
  created_at: string;
  last_seen_at?: string | null;
};

export type GraphNode = {
  id: number;
  title: string;
  body: string;
  tags: string[];
  degree: number;
  weight: number;
  community?: number | null;
  community_color?: string | null;
};

export type GraphEdge = {
  source: number;
  target: number;
  strength: number;
  kind: "synapse";
};

export type GraphStats = {
  nodes: number;
  edges: number;
  avg_degree: number;
  threshold: number;
  top_k: number;
  communities?: number;
};

export type Community = {
  id: number;
  name: string;
  color: string;
  size: number;
  terms: string[];
  member_ids: number[];
};

export type OrphanSuggestion = {
  note_id: number;
  title: string;
  suggested_id: number | null;
  suggested_title: string | null;
  suggested_strength: number;
  suggested_threshold: number;
};

export type Graph = {
  nodes: GraphNode[];
  edges: GraphEdge[];
  stats: GraphStats;
};

export type Neighbor = {
  node: GraphNode;
  strength: number;
};

export type SearchHit = {
  node: GraphNode;
  score: number;
};

export type PathStep = {
  node: GraphNode;
  strength: number;
};

export type PathResult = {
  found: boolean;
  path: PathStep[];
  cost: number;
};

export type ChatRole = "seed" | "synapse" | "community";

export type ChatCitation = {
  note_id: number;
  title: string;
  snippet: string;
  score: number;
  role: ChatRole;
  via_seed_id: number | null;
  via_strength: number;
};

export type ChatExpansion = {
  src: number;
  dst: number;
  strength: number;
  kind: ChatRole;
};

export type ChatTraversal = {
  seeds: number[];
  expansions: ChatExpansion[];
};

export type ChatMode = "auto" | "extractive" | "llm";

export type ChatResponse = {
  query: string;
  answer: string;
  citations: ChatCitation[];
  traversal: ChatTraversal;
  model: string;
  mode_used: "extractive" | "llm";
  latency_ms: number;
  llm_available: boolean;
  llm_provider: string | null;
  notice: string | null;
};

export type ChatStatus = {
  llm_available: boolean;
  llm_provider: string | null;
  extractive_available: boolean;
};

export type ChatTurn = {
  id: string;       // local-only uuid for keys
  query: string;
  response: ChatResponse;
};

export type BriefReasonKind = "stale" | "central" | "orphan" | "diverse";

export type BriefReason = {
  kind: BriefReasonKind;
  text: string;
  weight: number;
};

export type BriefConnection = {
  note_id: number;
  title: string;
  strength: number;
  cluster_id: number | null;
  cluster_name: string | null;
};

export type BriefPick = {
  note_id: number;
  title: string;
  snippet: string;
  tags: string[];
  score: number;
  reasons: BriefReason[];
  prompt: string;
  connections: BriefConnection[];
  cluster_id: number | null;
  cluster_name: string | null;
  cluster_color: string | null;
  days_since_seen: number | null;
  is_orphan: boolean;
};

export type Brief = {
  date: string;          // YYYY-MM-DD
  k: number;
  total_notes: number;
  picks: BriefPick[];
  stats: { considered?: number; orphan_count?: number; clusters_touched?: number };
};

// ----------------------------------------------------------------- trails

export type TrailOrigin = "manual" | "path" | "chat";

export type TrailStep = {
  note_id: number;
  title: string;
  snippet: string;
  tags: string[];
  caption: string;
  exists: boolean;
  cluster_id: number | null;
  cluster_name: string | null;
  cluster_color: string | null;
  strength_to_next: number | null;
  is_synapse_to_next: boolean;
};

export type Trail = {
  id: number;
  title: string;
  description: string;
  origin: TrailOrigin;
  created_at: string;
  updated_at: string;
  threshold: number;
  top_k: number;
  health: number;            // 0..1
  total_strength: number;
  missing_count: number;
  clusters_touched: number[];
  steps: TrailStep[];
};

export type TrailSummary = {
  id: number;
  title: string;
  description: string;
  origin: TrailOrigin;
  created_at: string;
  updated_at: string;
  step_count: number;
  health: number;
  missing_count: number;
};

export type TrailSuggestion = {
  note_id: number;
  title: string;
  snippet: string;
  tags: string[];
  strength: number;
  cluster_id: number | null;
  cluster_name: string | null;
  cluster_color: string | null;
};

export type TrailSuggestions = {
  trail_id: number;
  threshold: number;
  suggestions: TrailSuggestion[];
};

export type TrailDraftStep = { note_id: number; caption: string };

// --------------------------------------------------------------- distill

export type AtomNeighbor = {
  note_id: number;
  title: string;
  strength: number;
  cluster_id?: number | null;
  cluster_color?: string | null;
};

export type AtomPreview = {
  temp_id: string;
  title: string;
  body: string;
  tags: string[];
  char_count: number;
  cluster_id: number | null;
  cluster_name: string | null;
  cluster_color: string | null;
  cluster_strength: number;
  neighbors: AtomNeighbor[];
  expected_synapses: number;
  llm_refined: boolean;
};

export type AtomizeMode = "auto" | "heuristic" | "llm";

export type AtomizeResponse = {
  atoms: AtomPreview[];
  total_chars: number;
  mode_used: "heuristic" | "llm";
  llm_available: boolean;
  llm_provider: string | null;
  notice: string | null;
};

export type AtomCommit = { title: string; body: string; tags: string[] };

export type AtomCommitResult = { note_id: number; title: string; synapses: number };

export type AtomizeCommitResponse = {
  created: AtomCommitResult[];
  synapses_formed: number;
};

// --------------------------------------------------------------- synthesis

export type DigestSource = {
  ref: number;
  note_id: number;
  title: string;
  centrality: number;
};

export type DigestClaim = {
  text: string;
  note_id: number;
  ref: number;
};

export type OpenThread = {
  note_id: number;
  title: string;
  text: string;
  kind: "question" | "underdeveloped";
};

export type DigestBridge = {
  note_id: number;
  title: string;
  cluster_id: number;
  cluster_name: string;
  cluster_color: string;
  strength: number;
};

export type ClusterDigest = {
  cluster_id: number;
  name: string;
  color: string;
  size: number;
  terms: string[];
  cohesion: number;
  overview: string;
  claims: DigestClaim[];
  open_threads: OpenThread[];
  bridges: DigestBridge[];
  sources: DigestSource[];
  mode_used: "extractive" | "llm";
  llm_available: boolean;
  llm_provider: string | null;
  notice: string | null;
};

// --------------------------------------------------------------- tensions

export type TensionSignalKind = "polarity" | "antonym" | "contrast" | "title";

export type TensionSignal = {
  kind: TensionSignalKind;
  weight: number;
  detail: string;
};

export type TensionEvidence = {
  note_id: number;
  title: string;
  sentence: string;
  polarity: number;
};

export type TensionKind = "internal" | "cross";

export type Tension = {
  a_id: number;
  a_title: string;
  b_id: number;
  b_title: string;
  cosine: number;
  magnitude: number;
  signals: TensionSignal[];
  evidence: TensionEvidence[];
  bridge_title: string;
  bridge_prompt: string;
  bridge_tags: string[];
  kind: TensionKind;
  cluster_a: number | null;
  cluster_a_name: string | null;
  cluster_a_color: string | null;
  cluster_b: number | null;
  cluster_b_name: string | null;
  cluster_b_color: string | null;
};

export type TensionReport = {
  threshold: number;
  floor: number;
  total_pairs_scanned: number;
  candidate_count: number;
  tension_count: number;
  tensions: Tension[];
  stats: {
    notes?: number;
    candidate_pairs?: number;
    internal?: number;
    cross?: number;
    top_magnitude?: number;
  };
};

export type NoteDraft = {
  title: string;
  body: string;
  tags: string[];
};
