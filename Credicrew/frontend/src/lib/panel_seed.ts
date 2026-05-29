// Seed interview panel for a role. Generates a realistic 4-person panel
// with *deliberately* injected rater archetypes so the Calibration Studio
// lights up on first open: a lenient EM, a severe staff engineer, a
// well-calibrated senior, and a flat/central-tendency tech lead.
//
// Ratings are deterministic (hashed from role + interviewer + candidate +
// dimension) so re-seeding is idempotent and the studio is stable across
// reloads. The "true" ability per candidate is anchored on the candidate's
// match score so raw vs. de-biased rankings diverge in interesting ways.

import type {
  Panel,
  Interviewer,
  PanelRating,
  RubricLite,
} from '@/lib/calibration';

export type SeedCandidate = { id: number; name: string; score?: number };

export type Archetype = 'calibrated' | 'lenient' | 'severe' | 'flat';

export const ARCHETYPE_LABEL: Record<Archetype, string> = {
  calibrated: 'Calibrated',
  lenient: 'Lenient',
  severe: 'Severe',
  flat: 'Flat / central',
};

type ArchetypeProfile = { bias: number; compress: number };

const PROFILES: Record<Archetype, ArchetypeProfile> = {
  calibrated: { bias: 0, compress: 1.0 },
  lenient: { bias: 0.95, compress: 1.0 },
  severe: { bias: -1.25, compress: 1.0 },
  flat: { bias: 0, compress: 0.22 },
};

const NOISE = 0.6;            // ± rating noise band
const ABILITY_FLOOR = 2.0;   // mapped from the weakest match score
const ABILITY_SPAN = 2.8;    // mapped from the strongest match score

const SEED_PANEL: { slug: string; name: string; title: string; archetype: Archetype }[] = [
  { slug: 'meera', name: 'Meera Nair', title: 'Eng Manager', archetype: 'lenient' },
  { slug: 'arjun', name: 'Arjun Verma', title: 'Staff Engineer', archetype: 'severe' },
  { slug: 'sana', name: 'Sana Khan', title: 'Senior Engineer', archetype: 'calibrated' },
  { slug: 'dev', name: 'Dev Menon', title: 'Tech Lead', archetype: 'flat' },
];

/** Deterministic FNV-1a-ish string hash → float in [0, 1). */
function hash01(s: string): number {
  let h = 0x811c9dc5;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 0x01000193);
  }
  // to unsigned, then normalise
  return ((h >>> 0) % 100000) / 100000;
}

function clamp(x: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, x));
}

/** Candidate "true" ability (≈2.0–4.8) anchored on match score. */
function abilityOf(c: SeedCandidate): number {
  const score = typeof c.score === 'number' ? c.score : 80;
  return ABILITY_FLOOR + clamp((score - 70) / 26, 0, 1) * ABILITY_SPAN;
}

/** One rater's rating for one candidate × dimension (deterministic). */
function rate(
  roleId: string,
  interviewerId: string,
  archetype: Archetype,
  cand: SeedCandidate,
  dim: RubricLite,
): number {
  const profile = PROFILES[archetype];
  const truth = abilityOf(cand) + (hash01(`${roleId}|t|${cand.id}|${dim.key}`) - 0.5) * 1.0;
  const noise = (hash01(`${roleId}|n|${interviewerId}|${cand.id}|${dim.key}`) - 0.5) * NOISE;
  const compressed = 3 + (truth - 3) * profile.compress;
  return clamp(Math.round(compressed + profile.bias + noise), 1, 5);
}

/** Generate one interviewer's ratings across a given candidate set. */
export function seededRatings(
  roleId: string,
  interviewerId: string,
  archetype: Archetype,
  candidates: SeedCandidate[],
  rubric: RubricLite[],
): PanelRating[] {
  const out: PanelRating[] = [];
  for (const cand of candidates) {
    for (const dim of rubric) {
      out.push({
        interviewerId,
        candidateId: cand.id,
        dimKey: dim.key,
        rating: rate(roleId, interviewerId, archetype, cand, dim),
      });
    }
  }
  return out;
}

/** Build a fresh seeded panel for a role.
 *
 *  The panel is deliberately *unbalanced* — the realistic case, and the
 *  one where calibration actually changes the answer. Sana (calibrated) and
 *  Dev (flat) interview everyone and anchor the consensus; Meera (lenient)
 *  only sees the lower-scoring half and Arjun (severe) only sees the
 *  higher-scoring half. So the raw ranking *compresses* the real gap — the
 *  juniors are flattered, the seniors are marked down — and de-biasing
 *  pulls them back apart, reordering the boundary candidates. */
export function buildPanelSeed(
  roleId: string,
  candidates: SeedCandidate[],
  rubric: RubricLite[],
): Panel {
  const interviewers: Interviewer[] = SEED_PANEL.map(p => ({
    id: `${roleId}:${p.slug}`,
    name: p.name,
    title: p.title,
  }));
  const idBySlug = (slug: string) => `${roleId}:${slug}`;

  // Rank candidates weak → strong so the lenient/severe split is meaningful.
  const ranked = [...candidates].sort(
    (a, b) => (a.score ?? 80) - (b.score ?? 80) || a.id - b.id,
  );
  const m = ranked.length;
  const half = Math.floor(m / 2);
  const lowerHalf = new Set(ranked.slice(0, half).map(c => c.id));

  // Which archetype each seed slug carries.
  const archBySlug: Record<string, Archetype> = {
    meera: 'lenient', arjun: 'severe', sana: 'calibrated', dev: 'flat',
  };

  const ratings: PanelRating[] = [];
  for (const cand of candidates) {
    const inLower = lowerHalf.has(cand.id);
    for (const p of SEED_PANEL) {
      // Sana + Dev always rate; Meera only the lower half, Arjun only the
      // upper half. Tiny panels (m < 2) get the full panel on everyone.
      const rates =
        m < 2 ||
        p.slug === 'sana' || p.slug === 'dev' ||
        (p.slug === 'meera' && inLower) ||
        (p.slug === 'arjun' && !inLower);
      if (!rates) continue;
      const iid = idBySlug(p.slug);
      for (const dim of rubric) {
        ratings.push({
          interviewerId: iid,
          candidateId: cand.id,
          dimKey: dim.key,
          rating: rate(roleId, iid, archBySlug[p.slug], cand, dim),
        });
      }
    }
  }
  return { roleId, interviewers, ratings };
}
