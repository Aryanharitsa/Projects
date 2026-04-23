export type Note = {
  id: string;
  title: string;
  body: string;
  tags: string[];
  createdAt: number;
  updatedAt: number;
};

export type Link = {
  source: string; // note id
  target: string; // note id or dangling title
  resolved: boolean;
};

export type GraphNode = {
  id: string;
  title: string;
  degree: number;
  dangling?: boolean;
};

export type GraphEdge = {
  source: string;
  target: string;
};
