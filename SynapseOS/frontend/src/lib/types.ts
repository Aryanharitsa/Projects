export type Note = {
  id: number;
  title: string;
  body: string;
  tags: string[];
  created_at: string;
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
