'use client';
import { useEffect, useMemo, useState } from 'react';
import type { Candidate } from '@/data/candidates';
import type { MatchResult } from '@/lib/match';
import type { Role } from '@/lib/roles';
import { composeEmail, toMailto } from '@/lib/outreach';

type Props = {
  open: boolean;
  onClose: () => void;
  candidate: Candidate;
  match?: MatchResult;
  role?: Pick<Role, 'name' | 'plan' | 'pitch'> | null;
};

export default function OutreachModal({
  open,
  onClose,
  candidate,
  match,
  role,
}: Props) {
  const fallbackRole = useMemo(
    () => ({
      name: candidate.role || 'Engineering role',
      plan: { text: '', skills: [], location: undefined, seniority: undefined },
      pitch: undefined,
    }),
    [candidate.role],
  );

  const initial = useMemo(
    () => composeEmail({ role: role ?? fallbackRole, candidate, match }),
    [role, fallbackRole, candidate, match],
  );

  const [subject, setSubject] = useState(initial.subject);
  const [body, setBody] = useState(initial.body);
  const [copied, setCopied] = useState<'subject' | 'body' | 'both' | null>(null);

  useEffect(() => {
    if (open) {
      setSubject(initial.subject);
      setBody(initial.body);
      setCopied(null);
    }
  }, [open, initial.subject, initial.body]);

  if (!open) return null;

  const copy = async (kind: 'subject' | 'body' | 'both') => {
    try {
      const text =
        kind === 'subject' ? subject : kind === 'body' ? body : `${subject}\n\n${body}`;
      await navigator.clipboard.writeText(text);
      setCopied(kind);
      setTimeout(() => setCopied(null), 1400);
    } catch {
      /* no-op */
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-black/70 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="w-full max-w-2xl rounded-2xl border border-white/10 bg-neutral-950 p-6 shadow-2xl"
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="text-[11px] uppercase tracking-wider text-indigo-300">
              Outreach draft
            </div>
            <h2 className="mt-1 text-lg font-semibold text-white">
              {candidate.name}
              <span className="ml-2 text-sm font-normal text-white/50">
                {candidate.role}
              </span>
            </h2>
            {role?.name && (
              <div className="mt-0.5 text-xs text-white/60">
                For role: <span className="text-white/80">{role.name}</span>
              </div>
            )}
          </div>
          <button
            onClick={onClose}
            className="rounded-md p-1.5 text-white/50 hover:bg-white/10 hover:text-white"
            aria-label="Close"
          >
            ✕
          </button>
        </div>

        <div className="mt-4 space-y-3">
          <label className="block text-[11px] uppercase tracking-wider text-white/50">
            Subject
          </label>
          <input
            value={subject}
            onChange={e => setSubject(e.target.value)}
            className="w-full rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-sm text-white focus:border-indigo-400/60 focus:outline-none"
          />

          <label className="mt-2 block text-[11px] uppercase tracking-wider text-white/50">
            Body
          </label>
          <textarea
            value={body}
            onChange={e => setBody(e.target.value)}
            rows={11}
            className="w-full rounded-lg border border-white/10 bg-black/30 px-3 py-2 font-mono text-[13px] leading-relaxed text-white focus:border-indigo-400/60 focus:outline-none"
          />
        </div>

        <div className="mt-5 flex flex-wrap items-center gap-2">
          <button
            onClick={() => copy('both')}
            className="rounded-lg bg-indigo-500 px-3 py-1.5 text-xs font-medium text-black hover:bg-indigo-400"
          >
            {copied === 'both' ? 'Copied ✓' : 'Copy email'}
          </button>
          <button
            onClick={() => copy('subject')}
            className="rounded-lg border border-white/10 bg-white/5 px-3 py-1.5 text-xs text-white hover:bg-white/10"
          >
            {copied === 'subject' ? 'Copied ✓' : 'Copy subject'}
          </button>
          <button
            onClick={() => copy('body')}
            className="rounded-lg border border-white/10 bg-white/5 px-3 py-1.5 text-xs text-white hover:bg-white/10"
          >
            {copied === 'body' ? 'Copied ✓' : 'Copy body'}
          </button>
          <a
            href={toMailto(undefined, { subject, body })}
            className="ml-auto rounded-lg border border-white/10 bg-white/5 px-3 py-1.5 text-xs text-white hover:bg-white/10"
          >
            Open in mail app
          </a>
        </div>

        <div className="mt-4 border-t border-white/5 pt-3 text-[11px] text-white/40">
          Generated deterministically from the role spec and the explainable
          match — no LLM call, fully editable.
        </div>
      </div>
    </div>
  );
}
