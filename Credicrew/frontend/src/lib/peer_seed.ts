// Seed peer pool for a freshly-created role. Each role gets its own copy
// (cloned with unique ids) so deletions in one role don't leak across.
//
// The seed represents a realistic India-engineering team: a mix of
// senior/staff/principal hires across Bengaluru/Mumbai/Pune over the
// past 18 months. Numbers are realistic enough to make the regression
// meaningful — base trends up with composite, equity ladder follows
// seniority, sign-ons average ~10% of base.

import type { PeerOffer } from '@/lib/peer_parity';
import { makePeerId } from '@/lib/peer_parity';

const TEMPLATE: Omit<PeerOffer, 'id'>[] = [
  {
    candidateName: 'Aarav Mehta',
    roleName: 'Senior Backend Engineer',
    seniority: 'senior',
    location: 'bengaluru',
    composite: 78,
    base: 52,
    equityPct: 0.18,
    signOn: 5,
    targetBonusPct: 12,
    acceptedAt: '2024-11-12',
    source: 'seed',
  },
  {
    candidateName: 'Priya Subramanian',
    roleName: 'Senior Backend Engineer',
    seniority: 'senior',
    location: 'bengaluru',
    composite: 72,
    base: 48,
    equityPct: 0.16,
    signOn: 4,
    targetBonusPct: 12,
    acceptedAt: '2025-01-22',
    source: 'seed',
  },
  {
    candidateName: 'Karan Bhatia',
    roleName: 'Staff Engineer · Platform',
    seniority: 'staff',
    location: 'bengaluru',
    composite: 84,
    base: 86,
    equityPct: 0.42,
    signOn: 7,
    targetBonusPct: 15,
    acceptedAt: '2025-03-04',
    source: 'seed',
  },
  {
    candidateName: 'Riya Kapoor',
    roleName: 'Senior Frontend Engineer',
    seniority: 'senior',
    location: 'mumbai',
    composite: 75,
    base: 54,
    equityPct: 0.17,
    signOn: 5,
    targetBonusPct: 12,
    acceptedAt: '2025-04-18',
    source: 'seed',
  },
  {
    candidateName: 'Vivaan Iyer',
    roleName: 'Staff Engineer · Data',
    seniority: 'staff',
    location: 'bengaluru',
    composite: 81,
    base: 82,
    equityPct: 0.38,
    signOn: 8,
    targetBonusPct: 15,
    acceptedAt: '2025-06-09',
    source: 'seed',
  },
  {
    candidateName: 'Ishaan Pillai',
    roleName: 'Senior Backend Engineer',
    seniority: 'senior',
    location: 'pune',
    composite: 70,
    base: 44,
    equityPct: 0.14,
    signOn: 3,
    targetBonusPct: 10,
    acceptedAt: '2025-08-15',
    source: 'seed',
  },
  {
    candidateName: 'Nayantara Joshi',
    roleName: 'Principal Engineer · Infra',
    seniority: 'principal',
    location: 'bengaluru',
    composite: 89,
    base: 138,
    equityPct: 0.92,
    signOn: 12,
    targetBonusPct: 18,
    acceptedAt: '2025-10-02',
    source: 'seed',
  },
  {
    candidateName: 'Mihir Rao',
    roleName: 'Mid Backend Engineer',
    seniority: 'mid',
    location: 'bengaluru',
    composite: 65,
    base: 28,
    equityPct: 0.07,
    signOn: 2,
    targetBonusPct: 8,
    acceptedAt: '2025-12-11',
    source: 'seed',
  },
];

/** Build a fresh seed list (with unique ids) for a given role. */
export function buildSeed(): PeerOffer[] {
  return TEMPLATE.map(t => ({ ...t, id: makePeerId() }));
}
