'use client';
import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { decodeShare, importShared } from '@/lib/roles';

export default function SharedRole() {
  const router = useRouter();
  const [status, setStatus] = useState<'reading' | 'invalid' | 'preview'>('reading');
  const [token, setToken] = useState<string>('');
  const [preview, setPreview] = useState<{ name: string; jd: string; n: number } | null>(null);

  useEffect(() => {
    const hash = (typeof window !== 'undefined' ? window.location.hash : '') || '';
    const m = hash.match(/data=([^&]+)/);
    if (!m) {
      setStatus('invalid');
      return;
    }
    const t = m[1];
    setToken(t);
    const decoded = decodeShare(t);
    if (!decoded) {
      setStatus('invalid');
      return;
    }
    setPreview({
      name: decoded.name,
      jd: decoded.jd,
      n: decoded.shortlist.length,
    });
    setStatus('preview');
  }, []);

  const accept = () => {
    if (!token) return;
    const role = importShared(token);
    if (role) router.push(`/roles/${role.id}`);
  };

  return (
    <main className="min-h-screen bg-gradient-to-b from-[#0b0b12] to-black text-white">
      <div className="mx-auto max-w-2xl px-4 pb-24">
        <header className="flex items-center justify-between py-6">
          <Link href="/" className="flex items-center gap-2">
            <div className="grid h-8 w-8 place-items-center rounded-full bg-gradient-to-br from-indigo-400 to-violet-600 font-bold text-white">
              C
            </div>
            <div className="text-lg font-semibold">Credicrew</div>
          </Link>
          <Link href="/roles" className="text-sm text-white/60 hover:text-white">
            My roles
          </Link>
        </header>

        <h1 className="mt-2 text-3xl font-semibold md:text-4xl">Shared role</h1>

        {status === 'reading' && (
          <p className="mt-6 text-sm text-white/60">Reading link…</p>
        )}

        {status === 'invalid' && (
          <div className="mt-6 rounded-2xl border border-rose-400/20 bg-rose-500/5 p-6">
            <h2 className="text-lg font-semibold text-rose-200">Invalid link</h2>
            <p className="mt-1 text-sm text-white/70">
              The share token is missing or corrupt. Ask the sender to copy the
              link again.
            </p>
            <Link
              href="/roles"
              className="mt-4 inline-block rounded-lg bg-indigo-500 px-3 py-2 text-xs font-medium text-black hover:bg-indigo-400"
            >
              Go to my roles
            </Link>
          </div>
        )}

        {status === 'preview' && preview && (
          <div className="mt-6 rounded-2xl border border-white/10 bg-white/[0.04] p-6">
            <div className="text-[11px] uppercase tracking-wider text-white/50">
              Preview
            </div>
            <h2 className="mt-1 text-xl font-semibold">{preview.name}</h2>
            <p className="mt-1 text-xs text-white/60">
              {preview.n} candidate{preview.n === 1 ? '' : 's'} on the shortlist
            </p>
            <pre className="mt-4 max-h-64 overflow-y-auto whitespace-pre-wrap rounded-lg border border-white/10 bg-black/30 p-3 font-sans text-sm text-white/80">
              {preview.jd || '(empty job description)'}
            </pre>
            <div className="mt-5 flex items-center gap-3">
              <button
                onClick={accept}
                className="rounded-lg bg-indigo-500 px-4 py-2 text-sm font-medium text-black hover:bg-indigo-400"
              >
                Save to my roles
              </button>
              <Link
                href="/roles"
                className="rounded-lg border border-white/10 bg-white/5 px-4 py-2 text-sm text-white hover:bg-white/10"
              >
                Skip
              </Link>
            </div>
          </div>
        )}
      </div>
    </main>
  );
}
