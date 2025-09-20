export const PIPELINE_KEY = 'credicrew:pipeline';
export function getSavedIds(): number[] {
  if (typeof window === 'undefined') return [];
  try { return JSON.parse(localStorage.getItem(PIPELINE_KEY) || '[]'); } catch { return []; }
}
export function toggleSave(id: number): number[] {
  const current = new Set(getSavedIds());
  current.has(id) ? current.delete(id) : current.add(id);
  const arr = Array.from(current);
  localStorage.setItem(PIPELINE_KEY, JSON.stringify(arr));
  return arr;
}
export function isSaved(id: number): boolean {
  return getSavedIds().includes(id);
}
