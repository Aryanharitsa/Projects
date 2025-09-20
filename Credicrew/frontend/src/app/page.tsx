// src/app/page.tsx
"use client";

import { useEffect, useMemo, useState } from "react";
import { API_BASE } from "@/lib/config";

type Health = { status: string };

type Candidate = {
  id: string;
  name: string;
  title: string;
  location: string;
  skills: string[];
  score: number; // 0–100
};

const seed: Candidate[] = [
  { id: "1", name: "Ananya Rao", title: "Frontend Engineer", location: "Bengaluru", skills: ["React", "Next.js", "Tailwind"], score: 92 },
  { id: "2", name: "Karthik Menon", title: "Data Engineer", location: "Hyderabad", skills: ["Python", "Airflow", "SQL"], score: 88 },
  { id: "3", name: "Riya Shah", title: "ML Engineer", location: "Pune", skills: ["PyTorch", "Transformers", "LLMs"], score: 85 },
];

export default function Home() {
  const [health, setHealth] = useState<Health | null>(null);
  const [q, setQ] = useState("");
  const [minScore, setMinScore] = useState(70);

  useEffect(() => {
    // ping backend
    fetch(`${API_BASE}/health`)
      .then(r => r.json())
      .then(setHealth)
      .catch(() => setHealth(null));
  }, []);

  const results = useMemo(() => {
    const term = q.trim().toLowerCase();
    return seed
      .filter(c => c.score >= minScore)
      .filter(c =>
        term
          ? [c.name, c.title, c.location, ...c.skills].some(v => v.toLowerCase().includes(term))
          : true
      )
      .sort((a, b) => b.score - a.score);
  }, [q, minScore]);

  return (
    <main className="min-h-screen">
      {/* Header */}
      <header className="sticky top-0 z-10 border-b bg-white/70 backdrop-blur">
        <div className="mx-auto max-w-6xl px-4 py-3 flex items-center justify-between">
          <div className="font-semibold tracking-tight">Credicrew</div>
          <div className="text-sm text-neutral-500">
            API:{" "}
            <span className={health?.status === "ok" ? "text-emerald-600" : "text-red-600"}>
              {health?.status ?? "offline"}
            </span>
          </div>
        </div>
      </header>

      {/* Hero + Search */}
      <section className="mx-auto max-w-6xl px-4 py-14">
        <div className="mx-auto max-w-2xl text-center">
          <h1 className="text-4xl font-bold tracking-tight">Find great talent—fast</h1>
          <p className="mt-3 text-neutral-600">
            Describe who you’re looking for and tune results with simple controls.
          </p>
        </div>

        <div className="mx-auto mt-8 max-w-3xl rounded-2xl border p-4 shadow-sm">
          <div className="flex gap-3">
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="e.g. Next.js frontend in Bengaluru with Tailwind"
              className="flex-1 rounded-lg border px-4 py-2 outline-none focus:ring-2 focus:ring-neutral-900"
            />
            <button
              onClick={() => setQ(q)}
              className="rounded-lg border bg-neutral-900 px-4 py-2 text-white hover:bg-neutral-800"
            >
              Search
            </button>
          </div>

          <div className="mt-4 flex items-center gap-3">
            <label className="text-sm text-neutral-600">Min score</label>
            <input
              type="range"
              min={0}
              max={100}
              value={minScore}
              onChange={(e) => setMinScore(parseInt(e.target.value, 10))}
              className="w-56"
            />
            <span className="text-sm font-medium">{minScore}</span>
          </div>
        </div>
      </section>

      {/* Results */}
      <section className="mx-auto max-w-6xl px-4 pb-16">
        <div className="mb-3 text-sm text-neutral-500">
          Showing {results.length} of {seed.filter(s => s.score >= minScore).length}
        </div>

        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {results.map((c) => (
            <article key={c.id} className="rounded-2xl border p-4 shadow-sm hover:shadow-md transition">
              <div className="flex items-center justify-between">
                <h3 className="text-lg font-semibold">{c.name}</h3>
                <span className="rounded-full border px-2 py-0.5 text-xs font-medium">
                  {c.score}
                </span>
              </div>
              <p className="mt-1 text-sm text-neutral-600">{c.title} • {c.location}</p>
              <div className="mt-3 flex flex-wrap gap-2">
                {c.skills.map(s => (
                  <span key={s} className="rounded-full bg-neutral-100 px-2.5 py-1 text-xs">
                    {s}
                  </span>
                ))}
              </div>
              <button
                className="mt-4 w-full rounded-lg border bg-neutral-900 px-3 py-2 text-sm text-white hover:bg-neutral-800"
                onClick={() => alert(`(Demo) Message sent to ${c.name}`)}
              >
                Quick outreach
              </button>
            </article>
          ))}
        </div>
      </section>

      <footer className="border-t py-8 text-center text-sm text-neutral-500">
        © {new Date().getFullYear()} Credicrew
      </footer>
    </main>
  );
}
