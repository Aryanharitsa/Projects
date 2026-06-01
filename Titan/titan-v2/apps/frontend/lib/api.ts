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

export type TypologyCode =
  | "SMURF"
  | "LAYER"
  | "TBML"
  | "MULE"
  | "SANCEV"
  | "INTEG";

export type TypologyEvidence = {
  key: string;
  label: string;
  kind: "detector" | "structure" | "sanctions";
  signal: number;
  contribution: number;
  weight: number;
  detail: string;
};

export type TypologyMatch = {
  code: TypologyCode;
  name: string;
  summary: string;
  icon: string;
  accent: string; // hex
  confidence: number; // 0..1
  severity_floor: "low" | "medium" | "high" | "critical";
  evidence: TypologyEvidence[];
  narrative: string;
  recommended_action: string;
  contributing_factors: string[];
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
  typologies?: TypologyMatch[];
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

// ---------------------------------------------------------------------------
// Typology library (round-6, day-30)
// ---------------------------------------------------------------------------

export type TypologyContributorMeta = {
  key: string;
  label: string;
  kind: "detector" | "structure" | "sanctions";
  weight: number;
};

export type TypologyLibraryEntry = {
  code: TypologyCode;
  name: string;
  summary: string;
  icon: string;
  accent: string;
  severity_floor: "low" | "medium" | "high" | "critical";
  recommended_action: string;
  contributors: TypologyContributorMeta[];
  max_score: number;
};

export type TypologyLibrary = {
  ok: boolean;
  engine: string;
  version: string;
  confidence_floor: number;
  max_reported: number;
  typologies: TypologyLibraryEntry[];
};

export async function getTypologyLibrary(): Promise<TypologyLibrary> {
  const r = await fetch(`${API_BASE}/aml/typologies`, { cache: "no-store" });
  return jsonOrThrow(r);
}

export async function classifyTypologies(account_report: AccountReport): Promise<{
  ok: boolean;
  engine: string;
  typology_engine: string;
  account_id: string;
  typologies: TypologyMatch[];
}> {
  const r = await fetch(`${API_BASE}/aml/typologies/classify`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ account_report }),
  });
  return jsonOrThrow(r);
}

// ---------------------------------------------------------------------------
// Model validation / backtest (round-7, day-35)
// ---------------------------------------------------------------------------

export type ConfusionPoint = {
  threshold: number;
  tp: number;
  fp: number;
  fn: number;
  tn: number;
  alerts: number;
  alert_rate: number;
  precision: number;
  recall: number;
  specificity: number;
  fpr: number;
  tpr: number;
  f1: number;
  fbeta: number;
  accuracy: number;
  balanced_accuracy: number;
  youden_j: number;
};

export type DetectorDiscrimination = {
  key: string;
  label: string;
  weight: number;
  auc: number;
  lift: number;
  mean_pos: number;
  mean_neg: number;
  fired_pos: number;
  fired_neg: number;
  n_pos: number;
  n_neg: number;
  strength: "strong" | "moderate" | "weak" | "noise";
  note: string;
};

export type BacktestAccount = {
  account_id: string;
  display_name: string;
  score: number;
  label: 0 | 1;
  predicted: 0 | 1;
  outcome: "tp" | "fp" | "fn" | "tn";
  intensities: Record<string, number>;
};

export type BacktestResult = {
  ok: boolean;
  engine: string;
  labels: {
    positives: string[];
    n_pos: number;
    n_neg: number;
    n_total: number;
    base_rate: number;
    mode: "dict" | "positive-list";
  };
  beta: number;
  operating_threshold: number;
  effective_weights: Record<string, number>;
  sanctions_threshold: number;
  metrics_at: {
    current: ConfusionPoint;
    recommended: ConfusionPoint;
    youden: ConfusionPoint;
  };
  roc: { auc: number; points: { fpr: number; tpr: number; threshold: number }[] };
  pr: {
    average_precision: number;
    points: { recall: number; precision: number; threshold: number }[];
  };
  sweep: ConfusionPoint[];
  detectors: DetectorDiscrimination[];
  accounts: BacktestAccount[];
  verdict: { grade: "strong" | "fair" | "marginal" | "poor"; headline: string; notes: string[] };
};

export async function getBacktestSample(): Promise<{
  ok: boolean;
  engine: string;
  transactions: Tx[];
  labels: string[];
  note: string;
}> {
  const r = await fetch(`${API_BASE}/aml/backtest/sample`, { cache: "no-store" });
  return jsonOrThrow(r);
}

export async function runBacktest(
  transactions: Tx[],
  labels: string[] | Record<string, boolean | number>,
  opts: {
    weights?: WeightOverrides;
    beta?: number;
    operating_threshold?: number;
    sanctions_threshold?: number;
  } = {},
): Promise<BacktestResult> {
  const body: any = { transactions, labels };
  if (opts.weights && Object.keys(opts.weights).length) body.weights = opts.weights;
  if (typeof opts.beta === "number") body.beta = opts.beta;
  if (typeof opts.operating_threshold === "number")
    body.operating_threshold = opts.operating_threshold;
  if (typeof opts.sanctions_threshold === "number")
    body.sanctions_threshold = opts.sanctions_threshold;
  const r = await fetch(`${API_BASE}/aml/backtest`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return jsonOrThrow(r);
}

// ---------------------------------------------------------------------------
// Behavioral drift (round-8, day-40)
// ---------------------------------------------------------------------------

export type DriftVerdict =
  | "stable"
  | "mild"
  | "drifting"
  | "erratic"
  | "transformed";

export type DriftDimensionKey =
  | "amount"
  | "hour"
  | "dow"
  | "direction"
  | "velocity"
  | "cparty_diversity"
  | "cparty_novelty"
  | "geo"
  | "round_rate"
  | "median_shift";

export type DriftDimension = {
  key: DriftDimensionKey;
  label: string;
  score: number;
  weight: number;
  contribution: number;
  baseline: Record<string, any>;
  current: Record<string, any>;
  detail: string;
};

export type DriftCounterparty = {
  counterparty: string;
  baseline_count: number;
  current_count: number;
  baseline_volume: number;
  current_volume: number;
  is_new: boolean;
  activity_lift: number | null;
  volume_lift: number | null;
};

export type DriftChangePoint = {
  detected: boolean;
  onset_iso: string | null;
  days_ago: number | null;
  rolling_ks: { day: string; ks: number; n: number }[];
};

export type DriftWindow = {
  tx_count: number;
  start_iso: string | null;
  end_iso: string | null;
  span_days: number;
  active_days: number;
  volume_total: number;
  median_amount: number;
  inflow_share: number;
  unique_counterparties: number;
};

export type DriftReport = {
  account_id: string;
  display_name: string;
  overall: number;
  verdict: DriftVerdict;
  headline: string;
  drivers: string[];
  narrative: string;
  baseline_window: DriftWindow;
  current_window: DriftWindow;
  dimensions: DriftDimension[];
  counterparties: DriftCounterparty[];
  change_point: DriftChangePoint;
  suggested_action: string;
};

export type DriftPortfolioSummary = {
  total_accounts: number;
  by_verdict: Record<DriftVerdict, number>;
  drifters: number;
  avg_overall: number;
  top_account_id: string | null;
  top_overall: number;
};

export type DriftResponse =
  | {
      ok: true;
      engine: string;
      scope: "single";
      account_id: string;
      split_mode: "explicit" | "fraction";
      baseline_fraction: number;
      split_at: string | null;
      report: DriftReport | null;
      reason: string | null;
    }
  | {
      ok: true;
      engine: string;
      scope: "portfolio";
      split_mode: "explicit" | "fraction";
      baseline_fraction: number;
      split_at: string | null;
      summary: DriftPortfolioSummary;
      reports: DriftReport[];
      skipped: { account_id: string; reason: string }[];
    };

export type DriftRules = {
  ok: boolean;
  engine: string;
  weights: Record<string, number>;
  bands: { floor: number; verdict: DriftVerdict }[];
  dim_labels: Record<string, string>;
  min_baseline_txs: number;
  min_current_txs: number;
  default_baseline_fraction: number;
  driver_floor: number;
  change_point_ks_floor: number;
};

export type DriftSample = {
  ok: boolean;
  engine: string;
  transactions: Tx[];
  highlight_account: string;
  recommended_split_at: string;
  note: string;
};

export async function getDriftRules(): Promise<DriftRules> {
  const r = await fetch(`${API_BASE}/aml/drift/rules`, { cache: "no-store" });
  return jsonOrThrow(r);
}

export async function getDriftSample(): Promise<DriftSample> {
  const r = await fetch(`${API_BASE}/aml/drift/sample`, { cache: "no-store" });
  return jsonOrThrow(r);
}

export async function runDrift(
  transactions: Tx[],
  opts: {
    account_id?: string;
    baseline_fraction?: number;
    split_at?: string;
  } = {},
): Promise<DriftResponse> {
  const body: any = { transactions };
  if (opts.account_id) body.account_id = opts.account_id;
  if (typeof opts.baseline_fraction === "number")
    body.baseline_fraction = opts.baseline_fraction;
  if (opts.split_at) body.split_at = opts.split_at;
  const r = await fetch(`${API_BASE}/aml/drift`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
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
  | "reopened"
  | "typology_assigned";

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
  typology_code: TypologyCode | null;
  typology_confidence: number | null;
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
  typologies?: TypologyMatch[];
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
  opts: {
    opened_by?: string;
    note?: string;
    transactions?: Tx[];
    weights?: WeightOverrides;
    sanctions_threshold?: number;
  } = {},
): Promise<{ ok: boolean; case: CaseSummary }> {
  const body: any = { account_report };
  if (opts.opened_by) body.opened_by = opts.opened_by;
  if (opts.note) body.note = opts.note;
  if (opts.transactions && opts.transactions.length) body.transactions = opts.transactions;
  if (opts.weights && Object.keys(opts.weights).length) body.weights = opts.weights;
  if (typeof opts.sanctions_threshold === "number")
    body.sanctions_threshold = opts.sanctions_threshold;
  const r = await fetch(`${API_BASE}/aml/cases/open`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return jsonOrThrow(r);
}

export async function bulkOpenCases(
  score_response: ScoreResponse,
  opts: {
    min_priority?: CasePriority;
    opened_by?: string;
    transactions?: Tx[];
    weights?: WeightOverrides;
    sanctions_threshold?: number;
  } = {},
): Promise<{
  ok: boolean;
  opened: CaseSummary[];
  skipped: any[];
  total_accounts: number;
  snapshotted?: number;
}> {
  const body: any = { score_response };
  if (opts.min_priority) body.min_priority = opts.min_priority;
  if (opts.opened_by) body.opened_by = opts.opened_by;
  if (opts.transactions && opts.transactions.length) body.transactions = opts.transactions;
  if (opts.weights && Object.keys(opts.weights).length) body.weights = opts.weights;
  if (typeof opts.sanctions_threshold === "number")
    body.sanctions_threshold = opts.sanctions_threshold;
  const r = await fetch(`${API_BASE}/aml/cases/bulk_open`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
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

// ---------------------------------------------------------------------------
// Case-aware network panel (day-25)
// ---------------------------------------------------------------------------

export type EntityAttributionMember = {
  member_id: string;
  baseline_score: number;
  band: "low" | "medium" | "high" | "critical";
};

export type EntityAttribution = {
  account_id: string;
  entity_id: string;
  display_name: string;
  members?: string[];
  is_aggregate?: boolean;
  per_member?: EntityAttributionMember[];
  baseline_score: number;
  baseline_band: "low" | "medium" | "high" | "critical";
  counterparties: AttributionContribution[];
};

export type CaseClearingPanel = {
  ablated_entity_id: string;
  subject_self_delta: NetworkDelta | null;
  peer_lifts: NetworkDelta[];
  summary: NetworkCounterfactual["summary"];
  txs_removed: number;
};

export type CaseNetworkPanel =
  | {
      ok: true;
      available: false;
      reason: string;
      account_id: string;
      case_id?: string;
    }
  | {
      ok: true;
      available: true;
      account_id: string;
      case_id?: string;
      subject: NetEntity;
      subgraph: {
        entities: NetEntity[];
        edges: NetEdge[];
        node_count: number;
        edge_count: number;
        truncated_nodes: boolean;
      };
      attribution: EntityAttribution;
      clearing: CaseClearingPanel;
      full_summary: NetworkAnalyze["summary"];
      params?: NetworkAnalyze["params"];
      snapshot_meta?: {
        tx_count: number;
        counterparty_count: number;
        created_at_iso: string;
      };
      source?: "client-supplied";
      engine: string;
    };

export async function getCaseNetwork(
  case_id: string,
  opts: { hops?: number } = {},
): Promise<CaseNetworkPanel> {
  const qs = new URLSearchParams();
  if (typeof opts.hops === "number") qs.set("hops", String(opts.hops));
  const url = qs.toString()
    ? `${API_BASE}/aml/cases/${case_id}/network?${qs.toString()}`
    : `${API_BASE}/aml/cases/${case_id}/network`;
  const r = await fetch(url, { cache: "no-store" });
  return jsonOrThrow(r);
}

export async function runCaseNetworkClearing(
  case_id: string,
  transactions: Tx[],
  opts: { hops?: number; weights?: WeightOverrides; sanctions_threshold?: number } = {},
): Promise<CaseNetworkPanel> {
  const body: any = { transactions };
  if (typeof opts.hops === "number") body.hops = opts.hops;
  if (opts.weights && Object.keys(opts.weights).length) body.weights = opts.weights;
  if (typeof opts.sanctions_threshold === "number")
    body.sanctions_threshold = opts.sanctions_threshold;
  const r = await fetch(`${API_BASE}/aml/cases/${case_id}/network/clearing`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return jsonOrThrow(r);
}
