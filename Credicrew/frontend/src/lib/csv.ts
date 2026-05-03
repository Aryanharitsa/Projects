// Small, dependency-free CSV writer. Just enough quoting to survive
// commas, quotes, and newlines inside cells (RFC 4180 minus the BOM).

export function csvCell(v: unknown): string {
  if (v === null || v === undefined) return '';
  const s = typeof v === 'string' ? v : Array.isArray(v) ? v.join('; ') : String(v);
  if (/[",\n\r]/.test(s)) return `"${s.replace(/"/g, '""')}"`;
  return s;
}

export function csvRow(cells: unknown[]): string {
  return cells.map(csvCell).join(',');
}

export function toCsv(headers: string[], rows: unknown[][]): string {
  const out: string[] = [csvRow(headers)];
  for (const r of rows) out.push(csvRow(r));
  // Trailing newline keeps editors happy.
  return out.join('\n') + '\n';
}

/** Trigger a download of `text` as a file. Browser-only. */
export function downloadFile(filename: string, text: string, mime = 'text/csv;charset=utf-8'): void {
  if (typeof window === 'undefined') return;
  const blob = new Blob([text], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.style.display = 'none';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
