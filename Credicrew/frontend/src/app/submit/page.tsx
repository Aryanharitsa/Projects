'use client';
import { useState } from 'react';
import Link from 'next/link';

export default function Submit() {
  const [form, setForm] = useState({
    name: '', title: '', location: '', score: 75, skills: ''
  });
  const [status, setStatus] = useState<'idle'|'saving'|'ok'|'err'>('idle');

  const onChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target;
    setForm(f => ({ ...f, [name]: name === 'score' ? Number(value) : value }));
  };

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setStatus('saving');
    try {
      const res = await fetch('/api/candidates', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...form,
          skills: form.skills, // comma separated -> API parses
        }),
      });
      if (res.ok) { setStatus('ok'); }
      else { setStatus('err'); }
    } catch { setStatus('err'); }
  };

  return (
    <main className="mx-auto max-w-2xl px-4 py-10">
      <div className="mb-6">
        <h1 className="text-2xl font-semibold">Submit a candidate</h1>
        <p className="mt-1 text-sm text-neutral-400">Add a profile—appears instantly in Discover.</p>
      </div>

      <form onSubmit={onSubmit} className="space-y-4 rounded-2xl border border-neutral-800 bg-neutral-900 p-6">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <label className="text-sm">
            <span className="mb-1 block text-neutral-300">Name *</span>
            <input name="name" required value={form.name} onChange={onChange}
              className="w-full rounded-lg border border-neutral-700 bg-neutral-950 px-3 py-2 outline-none focus:border-indigo-500" />
          </label>
          <label className="text-sm">
            <span className="mb-1 block text-neutral-300">Title *</span>
            <input name="title" required value={form.title} onChange={onChange}
              className="w-full rounded-lg border border-neutral-700 bg-neutral-950 px-3 py-2 outline-none focus:border-indigo-500" />
          </label>
          <label className="text-sm">
            <span className="mb-1 block text-neutral-300">Location</span>
            <input name="location" value={form.location} onChange={onChange}
              className="w-full rounded-lg border border-neutral-700 bg-neutral-950 px-3 py-2 outline-none focus:border-indigo-500" />
          </label>
          <label className="text-sm">
            <span className="mb-1 block text-neutral-300">Score (0–100)</span>
            <input type="number" name="score" min="0" max="100" value={form.score} onChange={onChange}
              className="w-full rounded-lg border border-neutral-700 bg-neutral-950 px-3 py-2 outline-none focus:border-indigo-500" />
          </label>
        </div>

        <label className="block text-sm">
          <span className="mb-1 block text-neutral-300">Skills (comma separated)</span>
          <input name="skills" value={form.skills} onChange={onChange}
            placeholder="React, Next.js, Tailwind"
            className="w-full rounded-lg border border-neutral-700 bg-neutral-950 px-3 py-2 outline-none focus:border-indigo-500" />
        </label>

        <div className="flex items-center gap-3 pt-2">
          <button
            type="submit"
            disabled={status === 'saving'}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-60"
          >
            {status === 'saving' ? 'Saving…' : 'Submit'}
          </button>
          <Link href="/" className="text-sm text-neutral-300 underline">Back to Discover</Link>
          {status === 'ok' && <span className="text-sm text-emerald-400">Saved. Check Discover!</span>}
          {status === 'err' && <span className="text-sm text-rose-400">Failed to save.</span>}
        </div>
      </form>
    </main>
  );
}
