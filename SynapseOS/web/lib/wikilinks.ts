import type { GraphEdge, GraphNode, Link, Note } from "./types";

const WIKILINK_RE = /\[\[([^\]|]+?)(?:\|([^\]]+))?\]\]/g;
const TAG_RE = /(^|\s)#([a-zA-Z][\w-]{1,30})/g;

export function slugify(title: string): string {
  return title
    .trim()
    .toLowerCase()
    .replace(/[^\w\s-]/g, "")
    .replace(/\s+/g, "-")
    .slice(0, 80);
}

/** Extract wikilink titles from a body. Preserves order, deduplicated. */
export function extractWikilinks(body: string): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  WIKILINK_RE.lastIndex = 0;
  let m: RegExpExecArray | null;
  while ((m = WIKILINK_RE.exec(body))) {
    const target = m[1].trim();
    const key = target.toLowerCase();
    if (!seen.has(key)) {
      seen.add(key);
      out.push(target);
    }
  }
  return out;
}

/** Extract inline #tags from a body. */
export function extractTags(body: string): string[] {
  const seen = new Set<string>();
  TAG_RE.lastIndex = 0;
  let m: RegExpExecArray | null;
  while ((m = TAG_RE.exec(body))) {
    seen.add(m[2].toLowerCase());
  }
  return Array.from(seen);
}

/** Look up a note id by case-insensitive title. */
export function findByTitle(notes: Note[], title: string): Note | undefined {
  const t = title.trim().toLowerCase();
  return notes.find((n) => n.title.toLowerCase() === t);
}

/**
 * Build the full link graph across notes. Targets that don't resolve to a
 * real note are recorded as "dangling" with a synthetic id `dangling:<slug>`
 * so the synapse graph can still render them as ghost nodes — a visual
 * invitation to create the note.
 */
export function buildLinks(notes: Note[]): Link[] {
  const byTitle = new Map<string, string>();
  for (const n of notes) byTitle.set(n.title.toLowerCase(), n.id);

  const links: Link[] = [];
  for (const n of notes) {
    for (const target of extractWikilinks(n.body)) {
      const id = byTitle.get(target.toLowerCase());
      if (id) {
        links.push({ source: n.id, target: id, resolved: true });
      } else {
        links.push({
          source: n.id,
          target: `dangling:${slugify(target)}`,
          resolved: false,
        });
      }
    }
  }
  return links;
}

/** Notes that link TO a given note id. */
export function backlinksOf(noteId: string, notes: Note[]): Note[] {
  const target = notes.find((n) => n.id === noteId);
  if (!target) return [];
  const targetTitle = target.title.toLowerCase();
  return notes.filter((n) => {
    if (n.id === noteId) return false;
    return extractWikilinks(n.body).some(
      (t) => t.toLowerCase() === targetTitle,
    );
  });
}

/**
 * Flatten notes + links into graph primitives for d3-force. Dangling targets
 * are included as ghost nodes so the graph hints at future connections.
 */
export function buildGraph(notes: Note[]): {
  nodes: GraphNode[];
  edges: GraphEdge[];
} {
  const links = buildLinks(notes);
  const degree = new Map<string, number>();
  for (const l of links) {
    degree.set(l.source, (degree.get(l.source) ?? 0) + 1);
    degree.set(l.target, (degree.get(l.target) ?? 0) + 1);
  }

  const nodes: GraphNode[] = notes.map((n) => ({
    id: n.id,
    title: n.title,
    degree: degree.get(n.id) ?? 0,
  }));

  const seenDangling = new Set<string>();
  for (const l of links) {
    if (!l.resolved && !seenDangling.has(l.target)) {
      seenDangling.add(l.target);
      nodes.push({
        id: l.target,
        title: l.target.replace(/^dangling:/, "").replace(/-/g, " "),
        degree: degree.get(l.target) ?? 0,
        dangling: true,
      });
    }
  }

  const edges: GraphEdge[] = links.map((l) => ({
    source: l.source,
    target: l.target,
  }));

  return { nodes, edges };
}
