// Deterministic source attribution for the seed candidate set.
//
// The Channel Studio page (`/sources`) reads from the same role +
// shortlist pipeline every other surface uses. But the source channel
// isn't a property a recruiter explicitly enters today — it's something
// that should be persisted per candidate going forward. To make the
// surface useful on first open we attribute every candidate to a channel
// deterministically (a small hash on the candidate id), producing a
// realistic mix without storing anything new.
//
// Live edits — the user can change a channel for any shortlisted
// candidate in the page, and the override persists to localStorage.

import { CHANNELS, type Channel, type SourceAttribution } from '@/lib/sources';

// FNV-1a 32-bit on a string — deterministic, no external deps.
function fnv1a(s: string): number {
  let h = 0x811c9dc5;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 0x01000193);
  }
  return h >>> 0;
}

// Channel weights — tuned so the demo lights up every band (scale /
// steady / experiment / cut) at typical demo volumes (40–60 candidates).
// LinkedIn outreach + job_post + referral dominate (the realistic baseline);
// agency is rarer but produces high-quality + high-cost behaviour; campus
// + community + ai_sourcing are scarcer experiments; silver_medal is the
// smallest slice (only previous-runners-up).
const WEIGHTS: Array<[Channel, number]> = [
  ['linkedin_outreach', 28],
  ['referral', 18],
  ['job_post', 22],
  ['agency', 8],
  ['community', 8],
  ['university', 7],
  ['ai_sourcing', 6],
  ['silver_medal', 3],
];

const TOTAL = WEIGHTS.reduce((s, [, w]) => s + w, 0);

export function attributedChannel(candidateId: number): Channel {
  const h = fnv1a(`credicrew:src:${candidateId}`);
  const x = h % TOTAL;
  let cum = 0;
  for (const [ch, w] of WEIGHTS) {
    cum += w;
    if (x < cum) return ch;
  }
  return CHANNELS[0];
}

// Detail strings keyed by channel — light flavour text so the per-card
// "source" row in the page isn't blank.
const DETAILS: Record<Channel, string[]> = {
  linkedin_outreach: [
    'InMail template v3 — staff/EM segment',
    'LinkedIn — saved search "PyTorch + LLM"',
    'LinkedIn — recruiter outbound (Q2 campaign)',
    'LinkedIn — InMail v2 (Bengaluru backend)',
  ],
  referral: [
    'Referral — engineering team',
    'Referral — Aman P (staff)',
    'Referral — internal Slack #hiring',
    'Referral — design team',
  ],
  job_post: [
    'JD — Wellfound',
    'JD — company careers page',
    'JD — LinkedIn job post',
    'JD — Twitter/X #hiring',
  ],
  agency: [
    'Agency — TalentNorth',
    'Agency — HireWorks Bangalore',
    'Agency — Spotter (senior IC)',
  ],
  community: [
    'Community — IndiaFOSS 2026',
    'Community — PyConf Hyderabad',
    'Community — Cloud Native Bengaluru',
    'Community — TechWeek 2026 booth',
  ],
  university: [
    'University — IIIT-H campus drive',
    'University — BITS Pilani / GET',
    'University — IIT Bombay PhD pipeline',
  ],
  ai_sourcing: [
    'AI sourcing — GitHub signals',
    'AI sourcing — paper / arxiv scrape',
    'AI sourcing — Devfolio activity',
  ],
  silver_medal: [
    'Silver medal — previous backend req',
    'Silver medal — past offer-stage decline',
    'Silver medal — prior loop runner-up',
  ],
};

export function attributedDetail(candidateId: number, channel: Channel): string {
  const pool = DETAILS[channel];
  if (!pool || pool.length === 0) return '';
  const h = fnv1a(`credicrew:srcdet:${candidateId}`);
  return pool[h % pool.length];
}

export function attribute(candidateId: number): SourceAttribution {
  const channel = attributedChannel(candidateId);
  return {
    channel,
    detail: attributedDetail(candidateId, channel),
  };
}

// localStorage override layer — recruiters can re-tag a candidate's
// channel on the Channel Studio page and that change persists across
// reloads.
const KEY = 'credicrew:source-overrides:v1';

type Override = { channel?: Channel; detail?: string; costOverride?: number };

function readOverrides(): Record<string, Override> {
  if (typeof window === 'undefined') return {};
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    return typeof parsed === 'object' && parsed !== null ? parsed : {};
  } catch {
    return {};
  }
}

function writeOverrides(o: Record<string, Override>): void {
  if (typeof window === 'undefined') return;
  try {
    localStorage.setItem(KEY, JSON.stringify(o));
  } catch {
    /* quota / privacy mode — ignore */
  }
}

export function getSourceFor(candidateId: number): SourceAttribution {
  const base = attribute(candidateId);
  const ov = readOverrides()[String(candidateId)];
  if (!ov) return base;
  return {
    channel: ov.channel ?? base.channel,
    detail: ov.detail ?? base.detail,
    costOverride: ov.costOverride,
  };
}

export function setSourceChannel(candidateId: number, channel: Channel): void {
  const all = readOverrides();
  const key = String(candidateId);
  const cur = all[key] ?? {};
  all[key] = { ...cur, channel };
  writeOverrides(all);
}

export function clearSourceOverrides(): void {
  if (typeof window === 'undefined') return;
  try {
    localStorage.removeItem(KEY);
  } catch {
    /* ignore */
  }
}

// Per-channel cost-per-candidate override layer — separate key so the
// Channel Studio cost editor can tune defaults globally without poking
// individual candidates.
const COST_KEY = 'credicrew:source-costs:v1';

export function readChannelCosts(): Partial<Record<Channel, number>> {
  if (typeof window === 'undefined') return {};
  try {
    const raw = localStorage.getItem(COST_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    return typeof parsed === 'object' && parsed !== null ? parsed : {};
  } catch {
    return {};
  }
}

export function writeChannelCost(channel: Channel, cost: number): void {
  if (typeof window === 'undefined') return;
  const cur = readChannelCosts();
  cur[channel] = cost;
  try {
    localStorage.setItem(COST_KEY, JSON.stringify(cur));
  } catch {
    /* ignore */
  }
}

export function resetChannelCosts(): void {
  if (typeof window === 'undefined') return;
  try {
    localStorage.removeItem(COST_KEY);
  } catch {
    /* ignore */
  }
}
