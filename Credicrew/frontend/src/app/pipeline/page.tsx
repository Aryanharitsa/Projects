'use client';
import { useEffect, useState } from 'react';
import Link from 'next/link';
import { candidates } from '@/data/candidates';
import CandidateCard from '@/components/CandidateCard';
import { getSavedIds } from '@/lib/pipeline';
import { listRoles, type Role } from '@/lib/roles';

export default function Pipeline() {
  const [ids, setIds] = useState<number[]>([]);
  const [roles, setRoles] = useState<Role[]>([]);

  useEffect(() => {
    setIds(getSavedIds());
    setRoles(listRoles());
  }, []);

  const saved = candidates.filter(c => ids.includes(c.id));

  return (
    <main className="min-h-screen bg-gradient-to-b from-[#0b0b12] to-black text-white">
      <div className="mx-auto max-w-6xl px-4 pb-24">
        <header className="flex items-center justify-between py-6">
          <Link href="/" className="flex items-center gap-2">
            <div className="grid h-8 w-8 place-items-center rounded-full bg-gradient-to-br from-indigo-400 to-violet-600 font-bold text-white">
              C
            </div>
            <div className="text-lg font-semibold">Credicrew</div>
          </Link>
          <nav className="flex items-center gap-6 text-sm text-white/80">
            <Link href="/" className="hover:text-white">Discover</Link>
            <Link href="/roles" className="hover:text-white">Roles</Link>
            <Link href="/pipeline" className="text-white">Pipeline</Link>
            <Link href="/submit" className="hover:text-white">Submit</Link>
          </nav>
        </header>

        <h1 className="text-2xl font-semibold md:text-3xl">Pipeline</h1>
        <p className="mt-2 text-white/60">
          Quick-saves from Discover. For tracked statuses & per-role pipelines,
          use{' '}
          <Link href="/roles" className="text-indigo-300 hover:underline">
            Roles
          </Link>
          .
        </p>

        {saved.length === 0 ? (
          <div className="mt-10 rounded-2xl border border-dashed border-white/10 bg-white/[0.02] p-10 text-center">
            <p className="text-white/60">
              Nothing here yet. Go to{' '}
              <Link href="/" className="text-indigo-300 hover:underline">
                Discover
              </Link>{' '}
              and click <span className="text-white">Save</span> on a candidate.
            </p>
          </div>
        ) : (
          <div className="mt-8 grid gap-5 md:grid-cols-2 lg:grid-cols-3">
            {saved.map(c => (
              <CandidateCard key={c.id} c={c} roles={roles} />
            ))}
          </div>
        )}
      </div>
    </main>
  );
}
