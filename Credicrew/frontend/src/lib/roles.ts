// Recruiter Workspace — saved Roles with a candidate pipeline.
//
// A "Role" is a job spec the recruiter is sourcing for: a free-text JD,
// a parsed plan (skills/location/seniority), and a shortlist of candidates
// with statuses. Stored in localStorage (no auth here), mirrored into the
// URL hash for one-click sharing of an entire role.
//
// All pure data + helpers; the UI imports from here.

import type { QueryPlan } from '@/lib/match';
import { planQuery } from '@/lib/match';

export type PipelineStatus =
  | 'new'
  | 'outreach'
  | 'screening'
  | 'interview'
  | 'offer'
  | 'passed';

export const STATUSES: PipelineStatus[] = [
  'new',
  'outreach',
  'screening',
  'interview',
  'offer',
  'passed',
];

export const STATUS_LABEL: Record<PipelineStatus, string> = {
  new: 'New',
  outreach: 'Outreach',
  screening: 'Screening',
  interview: 'Interview',
  offer: 'Offer',
  passed: 'Passed',
};

export const STATUS_TONE: Record<PipelineStatus, string> = {
  new: 'sky',
  outreach: 'indigo',
  screening: 'violet',
  interview: 'amber',
  offer: 'emerald',
  passed: 'rose',
};

export type ShortlistEntry = {
  candidateId: number;
  status: PipelineStatus;
  addedAt: number;
  note?: string;
};

export type Role = {
  id: string;
  name: string;
  jd: string;
  plan: QueryPlan;
  pitch?: string;
  shortlist: ShortlistEntry[];
  createdAt: number;
  updatedAt: number;
};

const KEY = 'credicrew:roles:v1';

function rid(): string {
  // url-safe-ish, deterministic-ish
  const t = Date.now().toString(36);
  const r = Math.random().toString(36).slice(2, 8);
  return `r_${t}${r}`;
}

function read(): Role[] {
  if (typeof window === 'undefined') return [];
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return [];
    const list = JSON.parse(raw);
    return Array.isArray(list) ? list : [];
  } catch {
    return [];
  }
}

function write(roles: Role[]): void {
  if (typeof window === 'undefined') return;
  localStorage.setItem(KEY, JSON.stringify(roles));
}

export function listRoles(): Role[] {
  return read().sort((a, b) => b.updatedAt - a.updatedAt);
}

export function getRole(id: string): Role | null {
  return read().find(r => r.id === id) ?? null;
}

/** Pull the first sentence of the JD as a short pitch line. */
export function extractPitch(jd: string): string {
  if (!jd) return '';
  const trimmed = jd.trim();
  // Cut on first sentence terminator OR newline
  const m = trimmed.match(/^(.+?[.!?])\s/);
  const first = (m ? m[1] : trimmed.split(/\n/)[0] || trimmed).trim();
  return first.length > 220 ? `${first.slice(0, 217).trimEnd()}…` : first;
}

export function createRole(input: { name: string; jd: string }): Role {
  const now = Date.now();
  const role: Role = {
    id: rid(),
    name: input.name.trim() || 'Untitled role',
    jd: input.jd,
    plan: planQuery(input.jd),
    pitch: extractPitch(input.jd),
    shortlist: [],
    createdAt: now,
    updatedAt: now,
  };
  const next = [role, ...read()];
  write(next);
  return role;
}

export function updateRole(id: string, patch: Partial<Role>): Role | null {
  const list = read();
  const i = list.findIndex(r => r.id === id);
  if (i < 0) return null;
  const merged: Role = {
    ...list[i],
    ...patch,
    id: list[i].id,
    updatedAt: Date.now(),
  };
  // If JD changed, recompute plan + pitch.
  if (patch.jd !== undefined && patch.jd !== list[i].jd) {
    merged.plan = planQuery(merged.jd);
    merged.pitch = extractPitch(merged.jd);
  }
  list[i] = merged;
  write(list);
  return merged;
}

export function deleteRole(id: string): void {
  write(read().filter(r => r.id !== id));
}

export function addToShortlist(
  id: string,
  candidateId: number,
  status: PipelineStatus = 'new',
): Role | null {
  const role = getRole(id);
  if (!role) return null;
  if (role.shortlist.some(e => e.candidateId === candidateId)) return role;
  const entry: ShortlistEntry = {
    candidateId,
    status,
    addedAt: Date.now(),
  };
  return updateRole(id, { shortlist: [entry, ...role.shortlist] });
}

export function setStatus(
  id: string,
  candidateId: number,
  status: PipelineStatus,
): Role | null {
  const role = getRole(id);
  if (!role) return null;
  const next = role.shortlist.map(e =>
    e.candidateId === candidateId ? { ...e, status } : e,
  );
  return updateRole(id, { shortlist: next });
}

export function setNote(
  id: string,
  candidateId: number,
  note: string,
): Role | null {
  const role = getRole(id);
  if (!role) return null;
  const next = role.shortlist.map(e =>
    e.candidateId === candidateId ? { ...e, note } : e,
  );
  return updateRole(id, { shortlist: next });
}

export function removeFromShortlist(
  id: string,
  candidateId: number,
): Role | null {
  const role = getRole(id);
  if (!role) return null;
  const next = role.shortlist.filter(e => e.candidateId !== candidateId);
  return updateRole(id, { shortlist: next });
}

export type StatusCounts = Record<PipelineStatus, number>;

export function countByStatus(role: Role): StatusCounts {
  const acc: StatusCounts = {
    new: 0,
    outreach: 0,
    screening: 0,
    interview: 0,
    offer: 0,
    passed: 0,
  };
  for (const e of role.shortlist) acc[e.status] += 1;
  return acc;
}

// ---------- shareable URL state ----------

type SharePayload = {
  v: 1;
  name: string;
  jd: string;
  // candidate ids + status compactly
  s: [number, PipelineStatus][];
};

function b64urlEncode(s: string): string {
  if (typeof window === 'undefined') return '';
  return btoa(unescape(encodeURIComponent(s)))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '');
}

function b64urlDecode(s: string): string {
  if (typeof window === 'undefined') return '';
  const pad = s.length % 4 ? '='.repeat(4 - (s.length % 4)) : '';
  const norm = s.replace(/-/g, '+').replace(/_/g, '/') + pad;
  return decodeURIComponent(escape(atob(norm)));
}

export function encodeShare(role: Role): string {
  const payload: SharePayload = {
    v: 1,
    name: role.name,
    jd: role.jd,
    s: role.shortlist.map(e => [e.candidateId, e.status]),
  };
  return b64urlEncode(JSON.stringify(payload));
}

export function decodeShare(token: string): Omit<Role, 'id' | 'createdAt' | 'updatedAt'> | null {
  try {
    const raw = b64urlDecode(token);
    const obj = JSON.parse(raw) as SharePayload;
    if (obj.v !== 1) return null;
    return {
      name: obj.name,
      jd: obj.jd,
      plan: planQuery(obj.jd),
      pitch: extractPitch(obj.jd),
      shortlist: (obj.s || []).map(([candidateId, status]) => ({
        candidateId,
        status,
        addedAt: Date.now(),
      })),
    };
  } catch {
    return null;
  }
}

/** Save a decoded share payload as a new local Role. */
export function importShared(token: string): Role | null {
  const decoded = decodeShare(token);
  if (!decoded) return null;
  const now = Date.now();
  const role: Role = {
    id: rid(),
    name: decoded.name || 'Shared role',
    jd: decoded.jd,
    plan: decoded.plan,
    pitch: decoded.pitch,
    shortlist: decoded.shortlist,
    createdAt: now,
    updatedAt: now,
  };
  const next = [role, ...read()];
  write(next);
  return role;
}

export function buildShareUrl(role: Role): string {
  if (typeof window === 'undefined') return '';
  const token = encodeShare(role);
  const url = new URL(window.location.href);
  url.pathname = '/roles/share';
  url.search = '';
  url.hash = `data=${token}`;
  return url.toString();
}
