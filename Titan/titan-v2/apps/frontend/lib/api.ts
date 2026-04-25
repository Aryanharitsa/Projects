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
};

export type Factor = {
  name: string;
  points: number;
  weight: number;
  detail: string;
  evidence?: any[];
};

export type AccountReport = {
  account_id: string;
  risk_score: number;
  band: "low" | "medium" | "high" | "critical";
  factors: Factor[];
  edges: { from: string; to: string; amount: number; timestamp: string; channel?: string }[];
  counterparty_count: number;
  inbound_total: number;
  outbound_total: number;
};

export type ScoreResponse = {
  ok: boolean;
  engine: string;
  accounts: AccountReport[];
  summary: {
    total_transactions: number;
    total_accounts: number;
    alerted: number;
    highest_score: number;
    average_score: number;
  };
  rules_version: string;
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

export async function score(transactions: Tx[]): Promise<ScoreResponse> {
  const r = await fetch(`${API_BASE}/aml/score`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ transactions }),
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
