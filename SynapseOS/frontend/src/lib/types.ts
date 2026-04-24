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
