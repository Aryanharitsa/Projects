import type {
  AtomCommit,
  AtomizeCommitResponse,
  AtomizeMode,
  AtomizeResponse,
  Brief,
  ChatMode,
  ChatResponse,
  ChatStatus,
  Community,
  Graph,
  Neighbor,
  Note,
  OrphanSuggestion,
  PathResult,
  SearchHit,
  Trail,
  TrailDraftStep,
  TrailOrigin,
  TrailSummary,
  TrailSuggestions,
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

  chatStatus: () => j<ChatStatus>(`/chat/status`),

  chat: (payload: {
    query: string;
    mode?: ChatMode;
    k_seed?: number;
    hops?: number;
    include_community_anchors?: boolean;
  }) =>
    j<ChatResponse>(`/chat`, {
      method: "POST",
      body: JSON.stringify({
        query: payload.query,
        mode: payload.mode ?? "auto",
        k_seed: payload.k_seed ?? 4,
        hops: payload.hops ?? 1,
        include_community_anchors: payload.include_community_anchors ?? true,
      }),
    }),

  brief: (opts?: { k?: number; date?: string }) => {
    const q = new URLSearchParams();
    if (opts?.k !== undefined) q.set("k", String(opts.k));
    if (opts?.date) q.set("date", opts.date);
    const qs = q.toString();
    return j<Brief>(`/brief${qs ? `?${qs}` : ""}`);
  },

  touchNote: (id: number) =>
    j<{ ok: boolean; note_id: number; last_seen_at: string | null }>(
      `/notes/${id}/touch`,
      { method: "POST" },
    ),

  listTrails: () => j<TrailSummary[]>(`/trails`),

  getTrail: (id: number) => j<Trail>(`/trails/${id}`),

  createTrail: (payload: {
    title: string;
    description?: string;
    steps?: TrailDraftStep[];
    origin?: TrailOrigin;
  }) =>
    j<Trail>(`/trails`, {
      method: "POST",
      body: JSON.stringify({
        title: payload.title,
        description: payload.description ?? "",
        steps: payload.steps ?? [],
        origin: payload.origin ?? "manual",
      }),
    }),

  updateTrail: (
    id: number,
    payload: { title?: string; description?: string; steps?: TrailDraftStep[] },
  ) =>
    j<Trail>(`/trails/${id}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),

  appendTrailStep: (id: number, payload: { note_id: number; caption?: string }) =>
    j<Trail>(`/trails/${id}/append`, {
      method: "POST",
      body: JSON.stringify({ note_id: payload.note_id, caption: payload.caption ?? "" }),
    }),

  deleteTrail: (id: number) => j<void>(`/trails/${id}`, { method: "DELETE" }),

  trailSuggestions: (id: number, k = 5) =>
    j<TrailSuggestions>(`/trails/${id}/suggest_next?k=${k}`),

  trailExportUrl: (id: number) => `${BASE}/trails/${id}/export.md`,

  atomize: (payload: { text: string; mode?: AtomizeMode }) =>
    j<AtomizeResponse>(`/atomize`, {
      method: "POST",
      body: JSON.stringify({
        text: payload.text,
        mode: payload.mode ?? "auto",
      }),
    }),

  atomizeCommit: (atoms: AtomCommit[]) =>
    j<AtomizeCommitResponse>(`/atomize/commit`, {
      method: "POST",
      body: JSON.stringify({ atoms }),
    }),
};
