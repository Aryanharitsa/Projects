// Single source of truth for the gateway base URL. Reads NEXT_PUBLIC_API_BASE
// at build time (set by docker-compose) and falls back to localhost for `next
// dev`. AML calls go through the gateway, not the AML service directly, so the
// frontend has one origin to talk to.

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

export type Tx = {
  account_id: string;
  counterparty: string;
  amount: number;
  timestamp: string;
  channel?: string;
  geo?: string;
  subject?: string;
  subject_name?: string;
  counterparty_name?: string;
};

export type Factor = {
  name: string;
  points: number;
  weight: number;
  detail: string;
  evidence?: any[];
};

export type SanctionsHit = {
  entity_id: string;
  name: string;
  type: "entity" | "individual";
  matched_alias: string;
  alias_index: number;
  jurisdiction: string;
  list: string;
  added: string;
  reason: string;
  similarity: number;
  grade: "exact" | "strong" | "medium" | "weak" | "none";
  components: {
    token_set: number;
    ngram: number;
    contain: number;
    blended: number;
    jurisdiction_bonus?: number;
  };
  queried_name?: string;
  queried_party?: string;
  queried_role?: "subject" | "counterparty";
};

export type AccountReport = {
  account_id: string;
  display_name?: string;
  risk_score: number;
  band: "low" | "medium" | "high" | "critical";
  factors: Factor[];
  edges: { from: string; to: string; amount: number; timestamp: string; channel?: string }[];
  counterparty_count: number;
  inbound_total: number;
  outbound_total: number;
  sanctions_hits: SanctionsHit[];
};

export type WeightOverrides = Partial<Record<
  | "structuring"
  | "velocity_spike"
  | "round_trip"
  | "sanctions_hit"
  | "fan_in"
  | "fan_out"
  | "high_risk_geo"
  | "round_amount",
  number
>>;

export type ScoreResponse = {
  ok: boolean;
  engine: string;
  accounts: AccountReport[];
  summary: {
    total_transactions: number;
    total_accounts: number;
    alerted: number;
    sanctions_alerted?: number;
    highest_score: number;
    average_score: number;
  };
  effective_weights: Record<string, number>;
  sanctions_threshold: number;
  rules_version: string;
};

export type ScreenResult = {
  query: string;
  normalized?: string;
  threshold: number;
  matches: SanctionsHit[];
  best: SanctionsHit | null;
  graded: "exact" | "strong" | "medium" | "weak" | "none";
};

export type ScreenResponse = {
  ok: boolean;
  engine: string;
  watchlist: WatchlistMeta;
  queried: number;
  matched: number;
  by_grade: Record<string, number>;
  results: ScreenResult[];
};

export type WatchlistMeta = {
  version: string;
  source?: string;
  note?: string;
  issued?: string;
  size: number;
  by_list: Record<string, number>;
  by_jurisdiction: Record<string, number>;
  by_type: Record<string, number>;
  weights: {
    token_set: number;
    ngram: number;
    contain: number;
    ngram_n: number;
    jurisdiction_bonus: number;
  };
  grades: { min: number; label: string }[];
};

export type WatchlistEntry = {
  id: string;
  name: string;
  type: "entity" | "individual";
  aliases: string[];
  jurisdiction: string;
  list: string;
  added: string;
  reason: string;
};

export type Attestation = {
  docHash: string;
  subject: string;
  verifierId: string;
  timestamp: number;
  timestampIso: string;
  found: boolean;
  blockNumber?: number | null;
  txHash?: string | null;
};

async function jsonOrThrow(r: Response) {
  if (!r.ok) {
    let detail = `${r.status} ${r.statusText}`;
    try {
      const body = await r.json();
      if (body?.detail) detail = body.detail;
    } catch {}
    throw new Error(detail);
  }
  return r.json();
}

export async function health() {
  const r = await fetch(`${API_BASE}/healthz`, { cache: "no-store" });
  return jsonOrThrow(r);
}

export async function score(
  transactions: Tx[],
  opts: { weights?: WeightOverrides; sanctionsThreshold?: number } = {},
): Promise<ScoreResponse> {
  const body: any = { transactions };
  if (opts.weights && Object.keys(opts.weights).length) body.weights = opts.weights;
  if (typeof opts.sanctionsThreshold === "number")
    body.sanctions_threshold = opts.sanctionsThreshold;
  const r = await fetch(`${API_BASE}/aml/score`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return jsonOrThrow(r);
}

export async function screenSanctions(
  names: string[],
  opts: { jurisdiction?: string; threshold?: number; topK?: number } = {},
): Promise<ScreenResponse> {
  const body: any = { names };
  if (opts.jurisdiction) body.jurisdiction = opts.jurisdiction;
  if (typeof opts.threshold === "number") body.threshold = opts.threshold;
  if (typeof opts.topK === "number") body.top_k = opts.topK;
  const r = await fetch(`${API_BASE}/aml/sanctions/screen`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return jsonOrThrow(r);
}

export async function listWatchlist(
  limit = 50,
): Promise<{ ok: boolean; watchlist: WatchlistMeta; entries: WatchlistEntry[] }> {
  const r = await fetch(`${API_BASE}/aml/sanctions/list?limit=${limit}`, {
    cache: "no-store",
  });
  return jsonOrThrow(r);
}

export async function generateSar(account_report: AccountReport, analyst = "TITAN-AUTOMATED") {
  const r = await fetch(`${API_BASE}/aml/sar`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ account_report, analyst }),
  });
  return jsonOrThrow(r);
}

export async function getRules() {
  const r = await fetch(`${API_BASE}/aml/rules`, { cache: "no-store" });
  return jsonOrThrow(r);
}

export async function uploadKyc(file: File, subject: string, verifier = "VERIFIER-1") {
  const fd = new FormData();
  fd.append("file", file);
  fd.append("subject_wallet", subject);
  fd.append("verifier_id", verifier);
  const r = await fetch(`${API_BASE}/kyc/verify`, { method: "POST", body: fd });
  return jsonOrThrow(r);
}

export async function lookupAttestation(docHash: string): Promise<Attestation> {
  const r = await fetch(`${API_BASE}/attest/${docHash}`, { cache: "no-store" });
  return jsonOrThrow(r);
}

export async function recentAttestations(limit = 25) {
  const r = await fetch(`${API_BASE}/attestations/recent?limit=${limit}`, { cache: "no-store" });
  return jsonOrThrow(r);
}

// ---------------------------------------------------------------------------
// Case management (round-3, day-15)
// ---------------------------------------------------------------------------

export type CaseStatus =
  | "open"
  | "review"
  | "cleared"
  | "escalated"
  | "sar_filed";

export type CasePriority = "critical" | "high" | "medium" | "low";

export type CaseSla = "ok" | "warn" | "breach";

export type CaseEventType =
  | "opened"
  | "assigned"
  | "note"
  | "status"
  | "sar"
  | "reopened";

export type CaseEvent = {
  id: number;
  case_id: string;
  type: CaseEventType;
  actor: string;
  body: string | null;
  from_status: CaseStatus | null;
  to_status: CaseStatus | null;
  payload: any;
  created_at: number;
  created_at_iso: string;
};

export type CaseSummary = {
  id: string;
  account_id: string;
  display_name: string;
  status: CaseStatus;
  priority: CasePriority;
  risk_score: number;
  band: "low" | "medium" | "high" | "critical";
  alert_score: number;
  sanctions_count: number;
  fired_count: number;
  assignee: string | null;
  opened_by: string;
  opened_at: number;
  opened_at_iso: string;
  last_event_at: number;
  last_event_at_iso: string;
  closed_at: number | null;
  closed_at_iso: string | null;
  sar_id: string | null;
  sar_filed_at: number | null;
  sar_filed_at_iso: string | null;
  summary: string;
  age_hours: number;
  sla: CaseSla;
};

export type CaseSnapshot = {
  account_id: string;
  display_name?: string;
  risk_score: number;
  band: "low" | "medium" | "high" | "critical";
  factors: Factor[];
  sanctions_hits: SanctionsHit[];
  edges: { from: string; to: string; amount: number; timestamp?: string; channel?: string }[];
  counterparty_count: number;
  inbound_total: number;
  outbound_total: number;
};

export type CaseDetail = CaseSummary & {
  snapshot: CaseSnapshot;
  events: CaseEvent[];
};

export type CaseStats = {
  ok: boolean;
  engine: string;
  total: number;
  open_total: number;
  closed_total: number;
  by_status: Record<CaseStatus, number>;
  by_priority: Record<CasePriority, number>;
  by_sla: Record<CaseSla, number>;
  avg_open_age_hours: number;
  by_assignee: Record<string, number>;
  sla_thresholds: { warn_hours: number; breach_hours: number };
};

export type ListCasesFilters = {
  status?: CaseStatus;
  priority?: CasePriority;
  assignee?: string;
  account_id?: string;
  q?: string;
  sla?: CaseSla;
  include_closed?: boolean;
  limit?: number;
  offset?: number;
};

export async function listCases(
  f: ListCasesFilters = {},
): Promise<{ cases: CaseSummary[]; count: number; limit: number; offset: number }> {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(f)) {
    if (v === undefined || v === null || v === "") continue;
    qs.set(k, String(v));
  }
  const r = await fetch(`${API_BASE}/aml/cases?${qs.toString()}`, { cache: "no-store" });
  return jsonOrThrow(r);
}

export async function getCase(id: string): Promise<{ ok: boolean; case: CaseDetail }> {
  const r = await fetch(`${API_BASE}/aml/cases/${id}`, { cache: "no-store" });
  return jsonOrThrow(r);
}

export async function casesStats(): Promise<CaseStats> {
  const r = await fetch(`${API_BASE}/aml/cases/stats`, { cache: "no-store" });
  return jsonOrThrow(r);
}

export async function casesAssignees(): Promise<{ ok: boolean; assignees: string[] }> {
  const r = await fetch(`${API_BASE}/aml/cases/assignees`, { cache: "no-store" });
  return jsonOrThrow(r);
}

export async function openCase(
  account_report: AccountReport,
  opts: { opened_by?: string; note?: string } = {},
): Promise<{ ok: boolean; case: CaseSummary }> {
  const body: any = { account_report };
  if (opts.opened_by) body.opened_by = opts.opened_by;
  if (opts.note) body.note = opts.note;
  const r = await fetch(`${API_BASE}/aml/cases/open`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return jsonOrThrow(r);
}

export async function bulkOpenCases(
  score_response: ScoreResponse,
  opts: { min_priority?: CasePriority; opened_by?: string } = {},
): Promise<{ ok: boolean; opened: CaseSummary[]; skipped: any[]; total_accounts: number }> {
  const r = await fetch(`${API_BASE}/aml/cases/bulk_open`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ score_response, ...opts }),
  });
  return jsonOrThrow(r);
}

export async function transitionCase(
  id: string,
  to_status: CaseStatus | "reopen",
  opts: { actor?: string; note?: string } = {},
): Promise<{ ok: boolean; case: CaseSummary }> {
  const r = await fetch(`${API_BASE}/aml/cases/${id}/transition`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      to_status,
      actor: opts.actor || "TITAN-ANALYST",
      note: opts.note,
    }),
  });
  return jsonOrThrow(r);
}

export async function assignCase(
  id: string,
  assignee: string,
  actor = "TITAN-ANALYST",
): Promise<{ ok: boolean; case: CaseSummary }> {
  const r = await fetch(`${API_BASE}/aml/cases/${id}/assign`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ assignee, actor }),
  });
  return jsonOrThrow(r);
}

export async function noteCase(
  id: string,
  body: string,
  actor = "TITAN-ANALYST",
): Promise<{ ok: boolean; event: CaseEvent }> {
  const r = await fetch(`${API_BASE}/aml/cases/${id}/note`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ body, actor }),
  });
  return jsonOrThrow(r);
}

export async function fileSarOnCase(
  id: string,
  opts: { actor?: string; analyst?: string; note?: string } = {},
): Promise<{ ok: boolean; case: CaseSummary; sar: { sar_id: string; narrative_md: string; filed_at: string } }> {
  const r = await fetch(`${API_BASE}/aml/cases/${id}/sar`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      actor: opts.actor || "TITAN-ANALYST",
      analyst: opts.analyst,
      note: opts.note,
    }),
  });
  return jsonOrThrow(r);
}

export async function deleteCase(id: string): Promise<{ ok: boolean }> {
  const r = await fetch(`${API_BASE}/aml/cases/${id}`, { method: "DELETE" });
  return jsonOrThrow(r);
}

// ---------------------------------------------------------------------------
// Network intelligence (day-20)
// ---------------------------------------------------------------------------

export type NetEntity = {
  id: string;
  members: string[];
  display_name: string;
  is_aggregate: boolean;
  risk_score: number;
  network_risk: number;
  network_delta: number;
  band: "low" | "medium" | "high" | "critical";
  sanctioned: boolean;
  flags: string[];
  inbound_total: number;
  outbound_total: number;
  member_count: number;
  x: number;
  y: number;
};

export type NetEdge = {
  src: string;
  dst: string;
  amount: number;
  tx_count: number;
  last_ts: string;
};

export type NetworkAnalyze = {
  ok: boolean;
  entities: NetEntity[];
  edges: NetEdge[];
  summary: {
    total_parties: number;
    total_clusters: number;
    multi_member_clusters: number;
    avg_network_lift: number;
    top_lift_entity_id: string | null;
    top_central_entity_id: string | null;
    density: number;
    components: number;
  };
  score_response: ScoreResponse;
  params: { name_tau: number; counterparty_tau: number; pr_alpha: number; layout_size: number };
  engine: string;
};

export type NetworkDelta = {
  entity_id: string;
  display_name: string;
  risk_before: number;
  risk_after: number;
  risk_delta: number;
  network_before: number;
  network_after: number;
  network_delta: number;
};

export type NetworkCounterfactual = {
  ok: boolean;
  ablated: string[];
  removed_parties: string[];
  txs_removed: number;
  deltas: NetworkDelta[];
  summary: {
    network_avg_before: number;
    network_avg_after: number;
    network_avg_change: number;
    alerted_before: number;
    alerted_after: number;
  };
};

export type AttributionContribution = {
  counterparty: string;
  tx_count: number;
  amount_total: number;
  score_with: number;
  score_without: number;
  lift: number;
};

export type NetworkAttribution = {
  ok: boolean;
  account_id: string;
  display_name: string;
  baseline_score: number;
  baseline_band: "low" | "medium" | "high" | "critical";
  counterparties: AttributionContribution[];
};

export async function analyzeNetwork(
  transactions: Tx[],
  opts: {
    weights?: WeightOverrides;
    sanctions_threshold?: number;
    name_tau?: number;
    counterparty_tau?: number;
    score_response?: ScoreResponse;
  } = {},
): Promise<NetworkAnalyze> {
  const r = await fetch(`${API_BASE}/aml/network/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ transactions, ...opts }),
  });
  return jsonOrThrow(r);
}

export async function counterfactualNetwork(
  transactions: Tx[],
  ablate: string[],
  opts: { weights?: WeightOverrides; sanctions_threshold?: number } = {},
): Promise<NetworkCounterfactual> {
  const r = await fetch(`${API_BASE}/aml/network/counterfactual`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ transactions, ablate, ...opts }),
  });
  return jsonOrThrow(r);
}

export async function attributionNetwork(
  transactions: Tx[],
  account_id: string,
  opts: { weights?: WeightOverrides; sanctions_threshold?: number; max_report?: number } = {},
): Promise<NetworkAttribution> {
  const r = await fetch(`${API_BASE}/aml/network/attribution`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ transactions, account_id, ...opts }),
  });
  return jsonOrThrow(r);
}
