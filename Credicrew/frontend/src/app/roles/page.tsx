'use client';
import { useEffect, useState } from 'react';
import Link from 'next/link';
import RoleCard from '@/components/RoleCard';
import { listRoles, type Role } from '@/lib/roles';

export default function RolesIndex() {
  const [roles, setRoles] = useState<Role[]>([]);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    setRoles(listRoles());
    setReady(true);
  }, []);

  return (
    <main className="min-h-screen bg-gradient-to-b from-[#0b0b12] to-black text-white">
      <div className="mx-auto max-w-6xl px-4 pb-24">
        <header className="flex items-center justify-between py-6">
          <div className="flex items-center gap-2">
            <Link href="/" className="flex items-center gap-2">
              <div className="grid h-8 w-8 place-items-center rounded-full bg-gradient-to-br from-indigo-400 to-violet-600 font-bold text-white">
                C
              </div>
              <div className="text-lg font-semibold">Credicrew</div>
            </Link>
          </div>
          <nav className="flex items-center gap-6 text-sm text-white/80">
            <Link href="/" className="hover:text-white">Discover</Link>
            <Link href="/roles" className="text-white">Roles</Link>
            <Link href="/pipeline" className="hover:text-white">Pipeline</Link>
            <Link href="/submit" className="hover:text-white">Submit</Link>
          </nav>
        </header>

        <section className="mt-2 flex flex-wrap items-end justify-between gap-4">
          <div>
            <h1 className="text-3xl font-semibold md:text-4xl">Roles</h1>
            <p className="mt-2 max-w-xl text-sm text-white/60">
              Save a job description, build a shortlist against it, and run the
              pipeline end-to-end. Each role keeps its own parsed plan and
              candidate statuses.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Link
              href="/roles/new"
              className="rounded-lg bg-indigo-500 px-4 py-2 text-sm font-medium text-black hover:bg-indigo-400"
            >
              + New role from JD
            </Link>
          </div>
        </section>

        {ready && roles.length === 0 && (
          <div className="mt-12 rounded-2xl border border-dashed border-white/10 bg-white/[0.02] p-10 text-center">
            <div className="mx-auto mb-4 grid h-14 w-14 place-items-center rounded-full bg-gradient-to-br from-indigo-400/20 to-violet-600/20">
              <span className="text-2xl">📌</span>
            </div>
            <h2 className="text-lg font-semibold">No roles yet</h2>
            <p className="mt-1 text-sm text-white/60">
              Paste a job description to spin up your first hiring loop.
            </p>
            <div className="mt-5 flex justify-center gap-3">
              <Link
                href="/roles/new"
                className="rounded-lg bg-indigo-500 px-4 py-2 text-sm font-medium text-black hover:bg-indigo-400"
              >
                Create role
              </Link>
              <Link
                href="/"
                className="rounded-lg border border-white/10 bg-white/5 px-4 py-2 text-sm text-white hover:bg-white/10"
              >
                Browse candidates
              </Link>
            </div>
          </div>
        )}

        {roles.length > 0 && (
          <div className="mt-8 grid gap-5 md:grid-cols-2 lg:grid-cols-3">
            {roles.map(r => (
              <RoleCard key={r.id} role={r} />
            ))}
          </div>
        )}
      </div>
    </main>
  );
}
