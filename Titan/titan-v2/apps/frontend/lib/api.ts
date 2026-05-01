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
