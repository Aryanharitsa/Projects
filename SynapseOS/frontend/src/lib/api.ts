import type {
  AtlasReport,
  AtomCommit,
  ChronicleReport,
  AtomizeCommitResponse,
  AtomizeMode,
  AtomizeResponse,
  Brief,
  ChatMode,
  ChatResponse,
  ChatStatus,
  ClusterDigest,
  Community,
  CompassLens,
  CompassQuestionSummary,
  EchoCluster,
  EchoMergeResult,
  EchoReport,
  EchoSkipEntry,
  Graph,
  Neighbor,
  Note,
  OrphanSuggestion,
  PathResult,
  PrismComputeInput,
  PrismLensSpec,
  PrismReport,
  PulseReport,
  RecallClozeCheck,
  RecallGrade,
  RecallGradeResult,
  RecallSession,
  RecallSummary,
  SearchHit,
  SignalDelta,
  SignalReport,
  SparkKind,
  SparkReport,
  TensionReport,
  Trail,
  TrailDraftStep,
  TrailOrigin,
  TrailSummary,
  TrailSuggestions,
  VaultImportMode,
  VaultImportSummary,
  VaultSnapshot,
  VaultStats,
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

  chronicle: (opts?: {
    threshold?: number;
    topK?: number;
    maxChapters?: number;
    minClusterNotes?: number;
    minSpanDays?: number;
  }) => {
    const q = new URLSearchParams();
    if (opts?.threshold !== undefined) q.set("threshold", String(opts.threshold));
    if (opts?.topK !== undefined) q.set("top_k", String(opts.topK));
    if (opts?.maxChapters !== undefined)
      q.set("max_chapters", String(opts.maxChapters));
    if (opts?.minClusterNotes !== undefined)
      q.set("min_cluster_notes", String(opts.minClusterNotes));
    if (opts?.minSpanDays !== undefined)
      q.set("min_span_days", String(opts.minSpanDays));
    const qs = q.toString();
    return j<ChronicleReport>(`/chronicle${qs ? `?${qs}` : ""}`);
  },

  chronicleExportUrl: (opts?: {
    maxChapters?: number;
    minClusterNotes?: number;
    minSpanDays?: number;
  }) => {
    const q = new URLSearchParams();
    if (opts?.maxChapters !== undefined)
      q.set("max_chapters", String(opts.maxChapters));
    if (opts?.minClusterNotes !== undefined)
      q.set("min_cluster_notes", String(opts.minClusterNotes));
    if (opts?.minSpanDays !== undefined)
      q.set("min_span_days", String(opts.minSpanDays));
    const qs = q.toString();
    return `${BASE}/chronicle/export.md${qs ? `?${qs}` : ""}`;
  },

  pulse: (opts?: { windowDays?: number; threshold?: number; topK?: number }) => {
    const q = new URLSearchParams();
    if (opts?.windowDays !== undefined)
      q.set("window_days", String(opts.windowDays));
    if (opts?.threshold !== undefined) q.set("threshold", String(opts.threshold));
    if (opts?.topK !== undefined) q.set("top_k", String(opts.topK));
    const qs = q.toString();
    return j<PulseReport>(`/pulse${qs ? `?${qs}` : ""}`);
  },

  pulseExportUrl: (opts?: { windowDays?: number }) => {
    const q = new URLSearchParams();
    if (opts?.windowDays !== undefined)
      q.set("window_days", String(opts.windowDays));
    const qs = q.toString();
    return `${BASE}/pulse/export.md${qs ? `?${qs}` : ""}`;
  },

  spark: (opts?: {
    threshold?: number;
    topK?: number;
    limit?: number;
    perKind?: number;
    kinds?: SparkKind[];
  }) => {
    const q = new URLSearchParams();
    if (opts?.threshold !== undefined) q.set("threshold", String(opts.threshold));
    if (opts?.topK !== undefined) q.set("top_k", String(opts.topK));
    if (opts?.limit !== undefined) q.set("limit", String(opts.limit));
    if (opts?.perKind !== undefined) q.set("per_kind", String(opts.perKind));
    if (opts?.kinds && opts.kinds.length > 0)
      q.set("kinds", opts.kinds.join(","));
    const qs = q.toString();
    return j<SparkReport>(`/spark${qs ? `?${qs}` : ""}`);
  },

  sparkExportUrl: (opts?: {
    limit?: number;
    perKind?: number;
    kinds?: SparkKind[];
  }) => {
    const q = new URLSearchParams();
    if (opts?.limit !== undefined) q.set("limit", String(opts.limit));
    if (opts?.perKind !== undefined) q.set("per_kind", String(opts.perKind));
    if (opts?.kinds && opts.kinds.length > 0)
      q.set("kinds", opts.kinds.join(","));
    const qs = q.toString();
    return `${BASE}/spark/export.md${qs ? `?${qs}` : ""}`;
  },

  compassQuestions: () =>
    j<CompassQuestionSummary[]>(`/compass/questions`),

  compassCreate: (text: string) =>
    j<CompassLens>(`/compass/questions`, {
      method: "POST",
      body: JSON.stringify({ text }),
    }),

  compassLens: (id: number) =>
    j<CompassLens>(`/compass/questions/${id}`),

  compassMarkRead: (id: number, noteId: number) =>
    j<CompassLens>(`/compass/questions/${id}/read`, {
      method: "POST",
      body: JSON.stringify({ note_id: noteId }),
    }),

  compassUnmarkRead: (id: number, noteId: number) =>
    j<CompassLens>(`/compass/questions/${id}/read/${noteId}`, {
      method: "DELETE",
    }),

  compassDelete: (id: number) =>
    j<void>(`/compass/questions/${id}`, { method: "DELETE" }),

  compassExportUrl: (id: number) =>
    `${BASE}/compass/questions/${id}/export.md`,

  recallSession: (opts?: {
    k?: number;
    threshold?: number;
    topK?: number;
    session?: string;
  }) => {
    const q = new URLSearchParams();
    if (opts?.k !== undefined) q.set("k", String(opts.k));
    if (opts?.threshold !== undefined) q.set("threshold", String(opts.threshold));
    if (opts?.topK !== undefined) q.set("top_k", String(opts.topK));
    if (opts?.session) q.set("session", opts.session);
    const qs = q.toString();
    return j<RecallSession>(`/recall/session${qs ? `?${qs}` : ""}`);
  },

  recallGrade: (noteId: number, grade: RecallGrade) =>
    j<RecallGradeResult>(`/recall/grade`, {
      method: "POST",
      body: JSON.stringify({ note_id: noteId, grade }),
    }),

  recallSummary: () => j<RecallSummary>(`/recall/summary`),

  recallCheckCloze: (canonical: string, userAnswer: string) =>
    j<RecallClozeCheck>(`/recall/check-cloze`, {
      method: "POST",
      body: JSON.stringify({ canonical, user_answer: userAnswer }),
    }),

  signalList: () => j<SignalReport>(`/signal`),

  signalWatch: (questionId: number) =>
    j<SignalDelta>(`/signal/watch`, {
      method: "POST",
      body: JSON.stringify({ question_id: questionId }),
    }),

  signalUnwatch: (questionId: number) =>
    j<void>(`/signal/watch/${questionId}`, { method: "DELETE" }),

  signalRefresh: (questionId: number) =>
    j<SignalDelta>(`/signal/watch/${questionId}/refresh`, { method: "POST" }),

  signalGet: (questionId: number) =>
    j<SignalDelta>(`/signal/watch/${questionId}`),

  signalPinnedIds: () =>
    j<{ question_ids: number[] }>(`/signal/pinned_ids`),

  signalExportUrl: () => `${BASE}/signal/export.md`,

  // ---------------------------------------------------------------- vault

  vaultStats: () => j<VaultStats>(`/vault/stats`),

  vaultExportJsonUrl: (opts?: {
    includeEmbeddings?: boolean;
    includeCompassReads?: boolean;
    includeTrails?: boolean;
    includeSignal?: boolean;
  }) => {
    const q = new URLSearchParams();
    if (opts?.includeEmbeddings !== undefined)
      q.set("include_embeddings", String(opts.includeEmbeddings));
    if (opts?.includeCompassReads !== undefined)
      q.set("include_compass_reads", String(opts.includeCompassReads));
    if (opts?.includeTrails !== undefined)
      q.set("include_trails", String(opts.includeTrails));
    if (opts?.includeSignal !== undefined)
      q.set("include_signal", String(opts.includeSignal));
    const qs = q.toString();
    return `${BASE}/vault/export.json${qs ? `?${qs}` : ""}`;
  },

  vaultExportZipUrl: (opts?: {
    includeEmbeddings?: boolean;
    includeCompassReads?: boolean;
    includeTrails?: boolean;
    includeSignal?: boolean;
  }) => {
    const q = new URLSearchParams();
    if (opts?.includeEmbeddings !== undefined)
      q.set("include_embeddings", String(opts.includeEmbeddings));
    if (opts?.includeCompassReads !== undefined)
      q.set("include_compass_reads", String(opts.includeCompassReads));
    if (opts?.includeTrails !== undefined)
      q.set("include_trails", String(opts.includeTrails));
    if (opts?.includeSignal !== undefined)
      q.set("include_signal", String(opts.includeSignal));
    const qs = q.toString();
    return `${BASE}/vault/export.md.zip${qs ? `?${qs}` : ""}`;
  },

  vaultPreview: (payload: unknown) =>
    j<VaultImportSummary>(`/vault/preview`, {
      method: "POST",
      body: JSON.stringify({ mode: "preview", payload }),
    }),

  vaultImport: (mode: VaultImportMode, payload: unknown) =>
    j<VaultImportSummary>(`/vault/import`, {
      method: "POST",
      body: JSON.stringify({ mode, payload }),
    }),

  vaultSnapshots: () => j<VaultSnapshot[]>(`/vault/snapshots`),

  vaultCreateSnapshot: (label: string) =>
    j<VaultSnapshot>(`/vault/snapshots`, {
      method: "POST",
      body: JSON.stringify({ label }),
    }),

  vaultRestoreSnapshot: (id: number) =>
    j<VaultImportSummary>(`/vault/snapshots/${id}/restore`, { method: "POST" }),

  vaultDeleteSnapshot: (id: number) =>
    j<void>(`/vault/snapshots/${id}`, { method: "DELETE" }),

  // ---------------------------------------------------------------- prism

  prismLenses: () => j<PrismLensSpec[]>(`/prism/lenses`),

  prismCompute: (payload: PrismComputeInput) =>
    j<PrismReport>(`/prism/compute`, {
      method: "POST",
      body: JSON.stringify({
        target_kind: payload.target_kind,
        target_id: payload.target_id ?? null,
        query: payload.query ?? null,
        top_k_per_lens: payload.top_k_per_lens ?? 3,
        floor_sim: payload.floor_sim ?? 0.16,
        lens_ids: payload.lens_ids ?? null,
      }),
    }),

  prismExportMd: async (payload: PrismComputeInput): Promise<string> => {
    const res = await fetch(`${BASE}/prism/export.md`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      cache: "no-store",
      body: JSON.stringify({
        target_kind: payload.target_kind,
        target_id: payload.target_id ?? null,
        query: payload.query ?? null,
        top_k_per_lens: payload.top_k_per_lens ?? 3,
        floor_sim: payload.floor_sim ?? 0.16,
        lens_ids: payload.lens_ids ?? null,
      }),
    });
    if (!res.ok) {
      const text = await res.text().catch(() => "");
      throw new Error(`${res.status} ${res.statusText}: ${text}`);
    }
    return res.text();
  },
};
