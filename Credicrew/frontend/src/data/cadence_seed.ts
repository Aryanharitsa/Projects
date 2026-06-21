// Cadence seed — synth stageChangedAt per shortlist entry.
//
// `ShortlistEntry` stores `addedAt` (pipeline arrival) but doesn't yet
// record `stageChangedAt` (last stage transition). Until that field is
// persisted by the rest of the app, we synthesise a deterministic stage
// age from the role+candidate+stage hash so the Cadence surface lights
// up with a realistic spread on first open.
//
// When the user clicks "✓ Reset to now" on a row in the surface, we
// persist an explicit `stageChangedAt = now` to localStorage; that
// override wins over the synthesised value. Resetting drops the override
// so the synth value comes back.

import type { PipelineStatus, Role } from '@/lib/roles';
import {
  synthStageAge,
  type CadenceCandidate,
  STAGE_MEDIAN_DAYS,
  fnv1aUnit,
} from '@/lib/cadence';
import { candidates } from '@/data/candidates';
import { matchCandidate } from '@/lib/match';

const KEY = 'credicrew:cadence-overrides:v1';

type StageOverride = {
  /** Timestamp at which the candidate entered the current stage. */
  changedAt: number;
  /** Stage the override is for — invalidated if the stage changes. */
  stage: PipelineStatus;
};

type OverrideMap = Record<string, StageOverride>;

const DAY_MS = 24 * 60 * 60 * 1000;

function read(): OverrideMap {
  if (typeof window === 'undefined') return {};
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return {};
    const obj = JSON.parse(raw);
    return obj && typeof obj === 'object' ? obj : {};
  } catch {
    return {};
  }
}

function write(map: OverrideMap): void {
  if (typeof window === 'undefined') return;
  localStorage.setItem(KEY, JSON.stringify(map));
}

function rowKey(roleId: string, candidateId: number): string {
  return `${roleId}|${candidateId}`;
}

/** Persist that this candidate just entered the given stage. */
export function nudgeStage(roleId: string, candidateId: number, stage: PipelineStatus): void {
  const map = read();
  map[rowKey(roleId, candidateId)] = { changedAt: Date.now(), stage };
  write(map);
}

/** Drop an override so the synthesised age comes back. */
export function resetOverride(roleId: string, candidateId: number): void {
  const map = read();
  delete map[rowKey(roleId, candidateId)];
  write(map);
}

export function clearAllOverrides(): void {
  if (typeof window === 'undefined') return;
  localStorage.removeItem(KEY);
}

/** Pull all CadenceCandidate rows from the user's roles + shortlists. */
export function gatherCadenceInput(roles: Role[]): CadenceCandidate[] {
  const overrides = read();
  const now = Date.now();
  const all: CadenceCandidate[] = [];
  for (const role of roles) {
    for (const entry of role.shortlist) {
      const c = candidates.find(x => x.id === entry.candidateId);
      const fallback = { id: entry.candidateId, name: `Candidate #${entry.candidateId}` };
      const cand = c ?? fallback;
      const match = matchCandidate(role.plan, cand);

      const ovKey = rowKey(role.id, entry.candidateId);
      const ov = overrides[ovKey];
      let stageAgeDays: number;
      if (entry.stageChangedAt) {
        // Real stage-change timestamp persisted by setStatus — most authoritative.
        stageAgeDays = +(((now - entry.stageChangedAt) / DAY_MS).toFixed(1));
      } else if (ov && ov.stage === entry.status) {
        // Cadence-surface "nudge" override.
        stageAgeDays = +(((now - ov.changedAt) / DAY_MS).toFixed(1));
      } else {
        // First-open synth so the surface lights up immediately.
        stageAgeDays = synthStageAge(role.id, entry.candidateId, entry.status);
      }

      const pipelineAgeDays = +(((now - entry.addedAt) / DAY_MS).toFixed(1));

      all.push({
        candidateId: entry.candidateId,
        candidateName: cand.name ?? `Candidate #${entry.candidateId}`,
        roleId: role.id,
        roleName: role.name,
        stage: entry.status,
        stageAgeDays,
        pipelineAgeDays: Math.max(stageAgeDays, pipelineAgeDays),
        matchScore: match.score,
        location: c?.location,
      });
    }
  }
  return all;
}

/** Surface helper: produce a stable random number per row for tooltips. */
export function rowSeed(roleId: string, candidateId: number): number {
  return fnv1aUnit(`${roleId}|${candidateId}|seed`);
}

export function rowMedianHint(stage: PipelineStatus): number {
  return STAGE_MEDIAN_DAYS[stage] ?? 5;
}
