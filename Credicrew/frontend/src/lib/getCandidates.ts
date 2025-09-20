import fs from 'node:fs/promises';
import path from 'node:path';
import { candidates as seeded } from '@/data/candidates';

export type Cand = {
  id: number;
  name: string;
  title: string;
  location: string;
  score: number;
  skills: string[];
};

export async function getAllCandidates(): Promise<Cand[]> {
  try {
    const file = path.join(process.cwd(), 'src', 'data', 'custom.json');
    const raw = await fs.readFile(file, 'utf8');
    const extra: Cand[] = JSON.parse(raw);
    return [...seeded, ...extra].sort((a,b) => b.score - a.score);
  } catch {
    return [...seeded];
  }
}
