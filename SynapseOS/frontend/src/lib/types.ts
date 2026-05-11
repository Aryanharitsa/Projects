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
