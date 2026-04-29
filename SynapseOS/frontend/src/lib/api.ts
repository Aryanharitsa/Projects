import type {
  Community,
  Graph,
  Neighbor,
  Note,
  OrphanSuggestion,
  PathResult,
  SearchHit,
} from "./types";

const BASE =
  process.env.NEXT_PUBLIC_API_BASE?.replace(/\/$/, "") ?? "http://localhost:8000";

async function j<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    cache: "no-store",
    ...init,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText}: ${text || path}`);
  }
  // DELETE returns 204 No Content
  if (res.status === 204) return undefined as unknown as T;
  return (await res.json()) as T;
}

export const api = {
  health: () => j<{ ok: boolean; notes: number }>(`/health`),

  listNotes: () => j<Note[]>(`/notes`),

  createNote: (payload: { title: string; body: string; tags: string[] }) =>
    j<Note>(`/notes`, { method: "POST", body: JSON.stringify(payload) }),

  deleteNote: (id: number) => j<void>(`/notes/${id}`, { method: "DELETE" }),

  graph: (opts?: { threshold?: number; topK?: number }) => {
    const q = new URLSearchParams();
    if (opts?.threshold !== undefined) q.set("threshold", String(opts.threshold));
    if (opts?.topK !== undefined) q.set("top_k", String(opts.topK));
    const qs = q.toString();
    return j<Graph>(`/graph${qs ? `?${qs}` : ""}`);
  },

  neighbors: (id: number) => j<Neighbor[]>(`/neighbors/${id}`),

  search: (q: string, limit = 8) =>
    j<SearchHit[]>(`/search?q=${encodeURIComponent(q)}&limit=${limit}`),

  path: (src: number, dst: number) =>
    j<PathResult>(`/path?src=${src}&dst=${dst}`),

  communities: (opts?: { threshold?: number; topK?: number }) => {
    const q = new URLSearchParams();
    if (opts?.threshold !== undefined) q.set("threshold", String(opts.threshold));
    if (opts?.topK !== undefined) q.set("top_k", String(opts.topK));
    const qs = q.toString();
    return j<Community[]>(`/communities${qs ? `?${qs}` : ""}`);
  },

  orphans: (opts?: { threshold?: number; topK?: number }) => {
    const q = new URLSearchParams();
    if (opts?.threshold !== undefined) q.set("threshold", String(opts.threshold));
    if (opts?.topK !== undefined) q.set("top_k", String(opts.topK));
    const qs = q.toString();
    return j<OrphanSuggestion[]>(`/orphans${qs ? `?${qs}` : ""}`);
  },
};
