"use client";
import { useState } from "react";

type Tx = {
  account_id: string;
  counterparty: string;
  amount: number;
  timestamp: string;
  channel: string;
  geo?: string;
  meta?: Record<string, any>;
  subject?: string;
};

export default function AMLPage() {
  const [csv, setCsv] = useState(
`account_id,counterparty,amount,timestamp,channel,geo,subject
A1,C1,12000,2025-09-19T10:00:00Z,UPI,IN,0xf39f...
A1,C2,250000,2025-09-19T10:05:00Z,RTGS,IN,0xf39f...
B1,A1,5000,2025-09-19T11:00:00Z,NEFT,IN,0xabc...`
  );
  const [loading, setLoading] = useState(false);
  const [resp, setResp] = useState<any>(null);
  const [error, setError] = useState<string|null>(null);

  function parseCsv(text: string): Tx[] {
    const [header, ...rows] = text.trim().split(/\r?\n/);
    const cols = header.split(",");
    return rows.filter(Boolean).map(r => {
      const vals = r.split(",");
      const obj: any = {};
      cols.forEach((c, i) => obj[c] = vals[i]);
      obj.amount = Number(obj.amount);
      return obj as Tx;
    });
  }

  async function score() {
    try {
      setError(null); setLoading(true); setResp(null);
      const transactions = parseCsv(csv);
      const r = await fetch("http://localhost:8002/aml/score", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ transactions }),
      });
      if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
      const data = await r.json();
      setResp(data);
    } catch (e:any) {
      setError(e.message || "Error");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="grid gap-6 md:grid-cols-2">
      <div className="rounded-xl border bg-white p-4">
        <h1 className="text-lg font-medium mb-3">AML – Score transactions</h1>
        <textarea
          className="w-full h-64 rounded border p-2 font-mono text-sm"
          value={csv}
          onChange={(e) => setCsv(e.target.value)}
        />
        <div className="mt-3 flex items-center gap-3">
          <button
            onClick={score}
            disabled={loading}
            className="rounded bg-black px-4 py-2 text-white disabled:opacity-60"
          >
            {loading ? "Scoring..." : "Score"}
          </button>
          <a href="http://localhost:8002/docs" target="_blank" className="text-sm underline">
            Open Fintrace API
          </a>
        </div>
        {error && <p className="mt-3 text-sm text-red-600">{error}</p>}
      </div>

      <div className="rounded-xl border bg-white p-4">
        <h2 className="text-sm font-medium mb-2">Response</h2>
        <pre className="h-64 overflow-auto rounded bg-gray-100 p-3 text-xs">
{resp ? JSON.stringify(resp, null, 2) : "// submit to see JSON"}
        </pre>
      </div>
    </div>
  );
}
