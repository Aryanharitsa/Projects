import type {
  AtlasReport,
  AtomCommit,
  AtomizeCommitResponse,
  AtomizeMode,
  AtomizeResponse,
  Brief,
  ChatMode,
  ChatResponse,
  ChatStatus,
  ClusterDigest,
  Community,
  EchoCluster,
  EchoMergeResult,
  EchoReport,
  EchoSkipEntry,
  Graph,
  Neighbor,
  Note,
  OrphanSuggestion,
  PathResult,
  SearchHit,
  TensionReport,
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

  digest: (clusterId: number, opts?: { mode?: ChatMode }) => {
    const q = new URLSearchParams({ cluster_id: String(clusterId) });
    if (opts?.mode) q.set("mode", opts.mode);
    return j<ClusterDigest>(`/digest?${q.toString()}`);
  },

  digestExportUrl: (clusterId: number) =>
    `${BASE}/digest/export.md?cluster_id=${clusterId}`,

  tensions: (opts?: { floor?: number; limit?: number; threshold?: number; topK?: number }) => {
    const q = new URLSearchParams();
    if (opts?.floor !== undefined) q.set("floor", String(opts.floor));
    if (opts?.limit !== undefined) q.set("limit", String(opts.limit));
    if (opts?.threshold !== undefined) q.set("threshold", String(opts.threshold));
    if (opts?.topK !== undefined) q.set("top_k", String(opts.topK));
    const qs = q.toString();
    return j<TensionReport>(`/tensions${qs ? `?${qs}` : ""}`);
  },

  tensionsExportUrl: (opts?: { floor?: number; limit?: number }) => {
    const q = new URLSearchParams();
    if (opts?.floor !== undefined) q.set("floor", String(opts.floor));
    if (opts?.limit !== undefined) q.set("limit", String(opts.limit));
    const qs = q.toString();
    return `${BASE}/tensions/export.md${qs ? `?${qs}` : ""}`;
  },

  echo: (opts?: { threshold?: number; limit?: number }) => {
    const q = new URLSearchParams();
    if (opts?.threshold !== undefined) q.set("threshold", String(opts.threshold));
    if (opts?.limit !== undefined) q.set("limit", String(opts.limit));
    const qs = q.toString();
    return j<EchoReport>(`/echo${qs ? `?${qs}` : ""}`);
  },

  echoPreview: (payload: { note_ids: number[]; canonical_id?: number | null }) =>
    j<EchoCluster>(`/echo/preview`, {
      method: "POST",
      body: JSON.stringify({
        note_ids: payload.note_ids,
        canonical_id: payload.canonical_id ?? null,
      }),
    }),

  echoMerge: (payload: {
    note_ids: number[];
    canonical_id?: number | null;
    title?: string;
    body?: string;
    tags?: string[];
  }) =>
    j<EchoMergeResult>(`/echo/merge`, {
      method: "POST",
      body: JSON.stringify({
        note_ids: payload.note_ids,
        canonical_id: payload.canonical_id ?? null,
        title: payload.title,
        body: payload.body,
        tags: payload.tags,
      }),
    }),

  echoSkip: (payload: { pairs: [number, number][]; reason?: string }) =>
    j<{ inserted: number; total_skips: number }>(`/echo/skip`, {
      method: "POST",
      body: JSON.stringify({ pairs: payload.pairs, reason: payload.reason ?? "" }),
    }),

  echoSkips: () => j<EchoSkipEntry[]>(`/echo/skips`),

  echoUnskip: (a: number, b: number) =>
    j<void>(`/echo/skip?a=${a}&b=${b}`, { method: "DELETE" }),

  echoExportUrl: (opts?: { threshold?: number; limit?: number }) => {
    const q = new URLSearchParams();
    if (opts?.threshold !== undefined) q.set("threshold", String(opts.threshold));
    if (opts?.limit !== undefined) q.set("limit", String(opts.limit));
    const qs = q.toString();
    return `${BASE}/echo/export.md${qs ? `?${qs}` : ""}`;
  },

  atlas: (opts?: { threshold?: number; topK?: number; windowDays?: number }) => {
    const q = new URLSearchParams();
    if (opts?.threshold !== undefined) q.set("threshold", String(opts.threshold));
    if (opts?.topK !== undefined) q.set("top_k", String(opts.topK));
    if (opts?.windowDays !== undefined)
      q.set("window_days", String(opts.windowDays));
    const qs = q.toString();
    return j<AtlasReport>(`/atlas${qs ? `?${qs}` : ""}`);
  },

  atlasExportUrl: (opts?: { windowDays?: number }) => {
    const q = new URLSearchParams();
    if (opts?.windowDays !== undefined)
      q.set("window_days", String(opts.windowDays));
    const qs = q.toString();
    return `${BASE}/atlas/export.md${qs ? `?${qs}` : ""}`;
  },
};
