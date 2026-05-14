// Read-only Markdown preview rendered with a minimal home-grown renderer.
// Avoids pulling in a markdown lib for one screen — the offer letter shape is
// known (headings, paragraphs, single-pipe table, lists).

'use client';

import { useMemo } from 'react';

type Block =
  | { kind: 'h1'; text: string }
  | { kind: 'h2'; text: string }
  | { kind: 'p'; text: string }
  | { kind: 'list'; items: string[] }
  | { kind: 'table'; header: string[]; rows: string[][] };

function parse(md: string): Block[] {
  const lines = md.split('\n');
  const blocks: Block[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (line.startsWith('# ')) { blocks.push({ kind: 'h1', text: line.slice(2) }); i++; continue; }
    if (line.startsWith('## ')) { blocks.push({ kind: 'h2', text: line.slice(3) }); i++; continue; }
    if (/^\s*$/.test(line)) { i++; continue; }
    if (line.startsWith('| ') && lines[i + 1]?.match(/^\|?\s*-+\s*\|/)) {
      const header = line.split('|').slice(1, -1).map(s => s.trim());
      const rows: string[][] = [];
      i += 2;
      while (i < lines.length && lines[i].startsWith('| ')) {
        rows.push(lines[i].split('|').slice(1, -1).map(s => s.trim()));
        i++;
      }
      blocks.push({ kind: 'table', header, rows });
      continue;
    }
    if (line.startsWith('- ')) {
      const items: string[] = [];
      while (i < lines.length && lines[i].startsWith('- ')) {
        items.push(lines[i].slice(2));
        i++;
      }
      blocks.push({ kind: 'list', items });
      continue;
    }
    // Collect paragraph (single line, since the composer one-line-per-paragraph)
    blocks.push({ kind: 'p', text: line });
    i++;
  }
  return blocks;
}

function renderInline(t: string): React.ReactNode {
  const parts: React.ReactNode[] = [];
  const re = /\*\*([^*]+)\*\*|`([^`]+)`/g;
  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(t)) !== null) {
    if (m.index > last) parts.push(t.slice(last, m.index));
    if (m[1]) parts.push(<strong key={m.index}>{m[1]}</strong>);
    else if (m[2]) parts.push(<code key={m.index} className="rounded bg-white/8 px-1">{m[2]}</code>);
    last = re.lastIndex;
  }
  if (last < t.length) parts.push(t.slice(last));
  return parts;
}

export default function OfferLetterPreview({ markdown }: { markdown: string }) {
  const blocks = useMemo(() => parse(markdown), [markdown]);
  return (
    <article
      className="cc-letter rounded-2xl border border-white/10 bg-gradient-to-br from-white/[0.06] to-white/[0.02] p-6 text-[13px] leading-relaxed text-white/85 shadow-[0_0_40px_-12px_rgba(167,139,250,0.18)] md:p-8"
      data-print="letter"
    >
      {blocks.map((b, i) => {
        switch (b.kind) {
          case 'h1':
            return (
              <h1 key={i} className="border-b border-white/10 pb-3 text-2xl font-semibold tracking-tight text-white">
                {renderInline(b.text)}
              </h1>
            );
          case 'h2':
            return (
              <h2 key={i} className="mt-6 text-[11px] uppercase tracking-[0.18em] text-violet-300/80">
                {renderInline(b.text)}
              </h2>
            );
          case 'p':
            return (
              <p key={i} className="mt-3">
                {renderInline(b.text)}
              </p>
            );
          case 'list':
            return (
              <ul key={i} className="mt-2 list-disc space-y-1 pl-5">
                {b.items.map((it, j) => (
                  <li key={j}>{renderInline(it)}</li>
                ))}
              </ul>
            );
          case 'table':
            return (
              <table key={i} className="mt-3 w-full overflow-hidden rounded-lg border border-white/10 text-[12px]">
                <thead>
                  <tr className="bg-white/[0.04]">
                    {b.header.map((h, j) => (
                      <th key={j} className="px-3 py-2 text-left font-medium text-white/65">
                        {renderInline(h)}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {b.rows.map((row, r) => (
                    <tr key={r} className="border-t border-white/8">
                      {row.map((cell, c) => (
                        <td key={c} className={`px-3 py-2 ${c === 0 ? 'text-white/60' : 'text-white'}`}>
                          {renderInline(cell)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            );
        }
      })}
    </article>
  );
}
