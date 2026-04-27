'use client';
import { useMemo, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { createRole } from '@/lib/roles';
import { planQuery } from '@/lib/match';

const SAMPLE = `Senior Backend Engineer (FastAPI + Postgres) in Bengaluru.

We're building the data plane for a real-time risk engine — sub-100ms
scoring across millions of transactions. You'll own the FastAPI services,
shape the Postgres schema, and partner with the ML team on feature
extraction.

Must have: FastAPI, Postgres, Python. Nice to have: Redis, Kafka.`;

export default function NewRole() {
  const router = useRouter();
  const [name, setName] = useState('');
  const [jd, setJd] = useState('');

  const plan = useMemo(() => planQuery(jd), [jd]);
  const isActive =
    jd.trim().length > 0 && (plan.skills.length > 0 || plan.location || plan.seniority);

  const submit = () => {
    if (!jd.trim()) return;
    const finalName =
      name.trim() ||
      (plan.seniority ? plan.seniority[0].toUpperCase() + plan.seniority.slice(1) + ' ' : '') +
        (plan.skills[0] ? plan.skills[0].toUpperCase() + ' role' : 'Engineering role');
    const role = createRole({ name: finalName, jd });
    router.push(`/roles/${role.id}`);
  };

  return (
    <main className="min-h-screen bg-gradient-to-b from-[#0b0b12] to-black text-white">
      <div className="mx-auto max-w-3xl px-4 pb-24">
        <header className="flex items-center justify-between py-6">
          <Link href="/roles" className="text-sm text-white/60 hover:text-white">
            ← Roles
          </Link>
          <Link href="/" className="text-sm text-white/60 hover:text-white">
            Discover
          </Link>
        </header>

        <h1 className="text-3xl font-semibold md:text-4xl">New role</h1>
        <p className="mt-2 text-sm text-white/60">
          Paste the job description. We&apos;ll parse skills, location, and seniority,
          and seed your shortlist.
        </p>

        <div className="mt-8 space-y-4">
          <div>
            <label className="block text-[11px] uppercase tracking-wider text-white/50">
              Role name (optional)
            </label>
            <input
              value={name}
              onChange={e => setName(e.target.value)}
              placeholder='e.g. "Senior Backend Engineer"'
              className="mt-1 w-full rounded-lg border border-white/10 bg-black/30 px-4 py-3 text-sm text-white placeholder-white/40 focus:border-indigo-400/60 focus:outline-none"
            />
          </div>

          <div>
            <div className="flex items-center justify-between">
              <label className="block text-[11px] uppercase tracking-wider text-white/50">
                Job description
              </label>
              <button
                type="button"
                onClick={() => setJd(SAMPLE)}
                className="text-[11px] text-indigo-300 hover:text-indigo-200"
              >
                Use sample
              </button>
            </div>
            <textarea
              value={jd}
              onChange={e => setJd(e.target.value)}
              rows={12}
              placeholder="Paste the full JD here…"
              className="mt-1 w-full rounded-lg border border-white/10 bg-black/30 px-4 py-3 text-sm text-white placeholder-white/40 focus:border-indigo-400/60 focus:outline-none"
            />
          </div>

          {isActive && (
            <div className="rounded-xl border border-white/10 bg-white/[0.04] p-4">
              <div className="text-[11px] uppercase tracking-wider text-white/50">
                Detected plan
              </div>
              <div className="mt-2 flex flex-wrap gap-2">
                {plan.seniority && (
                  <span className="rounded-full border border-indigo-400/30 bg-indigo-400/10 px-2 py-0.5 text-[11px] text-indigo-200">
                    {plan.seniority}
                  </span>
                )}
                {plan.skills.map(s => (
                  <span
                    key={s}
                    className="rounded-full border border-emerald-400/30 bg-emerald-400/10 px-2 py-0.5 text-[11px] text-emerald-200"
                  >
                    {s}
                  </span>
                ))}
                {plan.location && (
                  <span className="rounded-full border border-amber-400/30 bg-amber-400/10 px-2 py-0.5 text-[11px] text-amber-200">
                    📍 {plan.location}
                  </span>
                )}
                {plan.skills.length === 0 && !plan.location && !plan.seniority && (
                  <span className="text-xs text-white/40">
                    Nothing detected — add concrete skills for better matches.
                  </span>
                )}
              </div>
            </div>
          )}

          <div className="flex items-center gap-3 pt-2">
            <button
              onClick={submit}
              disabled={!jd.trim()}
              className="rounded-lg bg-indigo-500 px-4 py-2 text-sm font-medium text-black hover:bg-indigo-400 disabled:cursor-not-allowed disabled:opacity-40"
            >
              Create role
            </button>
            <Link
              href="/roles"
              className="rounded-lg border border-white/10 bg-white/5 px-4 py-2 text-sm text-white hover:bg-white/10"
            >
              Cancel
            </Link>
          </div>
        </div>
      </div>
    </main>
  );
}
