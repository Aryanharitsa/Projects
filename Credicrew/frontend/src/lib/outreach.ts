// Deterministic outreach email composer.
//
// No LLM call — pure-string templating from the candidate, the role's
// query plan, and the JD pitch line. Mirrored on the backend at
// app/services/outreach.py so the same email comes back from POST
// /outreach for programmatic / agentic clients.

import type { Candidate } from '@/data/candidates';
import type { MatchResult } from '@/lib/match';
import type { Role } from '@/lib/roles';

export type OutreachEmail = {
  subject: string;
  body: string;
};

function firstName(full: string): string {
  return (full || '').trim().split(/\s+/)[0] || 'there';
}

function joinList(items: string[]): string {
  if (items.length <= 1) return items[0] ?? '';
  if (items.length === 2) return `${items[0]} and ${items[1]}`;
  return `${items.slice(0, -1).join(', ')}, and ${items[items.length - 1]}`;
}

function titleCase(s: string): string {
  return s
    .split(/\s+/)
    .map(w => (w ? w[0].toUpperCase() + w.slice(1) : ''))
    .join(' ');
}

export type ComposeArgs = {
  role: Pick<Role, 'name' | 'plan' | 'pitch'>;
  candidate: Pick<Candidate, 'name' | 'role' | 'location'>;
  match?: MatchResult;
  sender?: string;
};

export function composeEmail(args: ComposeArgs): OutreachEmail {
  const { role, candidate, match, sender } = args;

  const fn = firstName(candidate.name);
  const roleTitle = role.name || titleCase(role.plan.seniority || 'engineering') + ' role';
  const matched = (match?.matchedSkills ?? []).slice(0, 3);
  const pitch =
    (role.pitch && role.pitch.trim()) ||
    `we're hiring for ${roleTitle.toLowerCase()} and your background looks like a strong fit`;

  const subject = matched.length
    ? `Quick chat about a ${roleTitle} role — your ${matched[0]} work caught my eye`
    : `Quick chat about a ${roleTitle} role at our team`;

  const skillLine = matched.length
    ? `Your work with ${joinList(matched)} stood out — those are exactly the skills we need on day one.`
    : `Your background as a ${candidate.role || 'engineer'} stood out across the candidates I reviewed.`;

  const locLine =
    role.plan.location && role.plan.location !== 'remote'
      ? `We're based in ${titleCase(role.plan.location)}, but happy to discuss remote / hybrid arrangements.`
      : `The role is remote-friendly across India.`;

  const score = match?.score;
  const scoreLine =
    typeof score === 'number'
      ? `(For context: against the spec for ${roleTitle}, your profile lands at ${score}/100 with explainable reasons — happy to share the breakdown.)`
      : '';

  const body = [
    `Hi ${fn},`,
    '',
    `I'm reaching out about a ${roleTitle} opportunity — ${pitch}`,
    '',
    skillLine,
    locLine,
    '',
    `Would you be open to a 20-minute intro call this week? Even if the timing isn't right, I'd love to keep in touch.`,
    scoreLine,
    '',
    `Best,`,
    sender || `— Hiring team`,
  ]
    .filter(line => line !== null && line !== undefined)
    .join('\n');

  return { subject, body };
}

export function toMailto(to: string | undefined, email: OutreachEmail): string {
  const params = new URLSearchParams();
  params.set('subject', email.subject);
  params.set('body', email.body);
  return `mailto:${to ?? ''}?${params.toString()}`;
}
