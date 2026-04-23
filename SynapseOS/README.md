<div align="center">

# SynapseOS

**Your thoughts, connected.**

A local-first Personal Knowledge OS where every note is a synapse. Write in
Markdown, link with `[[double brackets]]`, and watch your ideas form a living
graph — instantly, in your browser, with no server.

<br />

`Next.js 14` · `TypeScript` · `Tailwind` · `d3-force` · `Zustand` · `100% local`

</div>

---

## Why another notes app?

Most tools treat notes as files in folders. SynapseOS treats them as
**neurons** — the value lives in the *edges* between ideas. A note without
links is a lonely soma; a linked note is a thought that can fire across your
whole vault.

This is a knowledge operating system for one person: no accounts, no cloud,
no lock-in. Your vault lives in your browser (localStorage). Open the tab,
start writing, the graph self-assembles.

## Features

- **Force-directed synapse graph** — built on `d3-force`, rendered on a
  retina-aware canvas. Pan, zoom (wheel), drag nodes, click to open. Active
  notes glow cyan; neighbors light up; ghost nodes (links to notes that
  don't exist yet) appear as dashed magenta rings — a visual invitation to
  create them.
- **Live wikilinks & backlinks** — type `[[Second Brain]]` and it resolves
  on the fly. The Connections panel shows **who links here** and
  **where this note points** every time you open a note.
- **Split-pane markdown** — edit on the left, beautifully rendered preview
  on the right. Wikilinks are clickable. Inline `#tags`, lists, quotes,
  fenced code, and GFM-ish formatting — all handled by a tiny custom
  renderer (zero remark/rehype deps).
- **⌘K command palette** — fuzzy-jump to any note, or type a new title and
  press enter to create it on the spot. Arrow keys navigate.
- **Keyboard-first** — `⌘K` palette · `⌘N` new note · `⌘G` toggle graph.
- **Local-first, private** — your vault lives in your browser. Nothing
  leaves the tab. Exportable by design.
- **Gorgeous dark UI** — deep void background, glass panels, animated
  synaptic accents in cyan/violet/magenta. Presentation matters.

## Screens

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Sidebar          │   Markdown editor + preview   │   Synapse graph    │
│  · search         │   ┌─────────────┬───────────┐ │                    │
│  · new note       │   │ # Welcome   │  Welcome  │ │     ◉ ─── ◉        │
│  · note list      │   │ [[Second..] │  to…      │ │    / ╲   / ╲       │
│  · ←backlinks     │   │             │           │ │   ◉   ◉─◉   ◉      │
│  · #tag chips     │   └─────────────┴───────────┘ │    ╲ / ╲ /         │
│                   │   Backlinks · Outbound        │     ◉───◉          │
└─────────────────────────────────────────────────────────────────────────┘
```

## Run it

```bash
cd SynapseOS/web
npm install
npm run dev
```

Then open [http://localhost:3000](http://localhost:3000). You'll land on a
marketing page; click **Launch SynapseOS** (or go to `/workspace`). The
vault is seeded with a handful of example notes so the graph is alive from
second one.

## Architecture

```
web/
├── app/
│   ├── page.tsx              # Landing — hero + feature grid
│   ├── workspace/page.tsx    # The workspace — 3-pane layout
│   ├── layout.tsx
│   └── globals.css           # Synaptic theme, prose styles, wikilink chrome
├── components/
│   ├── Sidebar.tsx           # Search, note list, stats
│   ├── NoteEditor.tsx        # Split editor + live preview
│   ├── BacklinksPanel.tsx    # Connections: backlinks / outbound
│   ├── GraphView.tsx         # Canvas-rendered d3-force synapse graph
│   ├── CommandPalette.tsx    # ⌘K fuzzy finder + note creator
│   └── HeroGraph.tsx         # Ambient hero animation
└── lib/
    ├── store.ts              # Zustand store, persisted to localStorage
    ├── wikilinks.ts          # [[link]] parser, backlink index, graph build
    ├── markdown.ts           # Tiny markdown renderer with wikilink hooks
    ├── seed.ts               # Opinionated starter notes
    └── types.ts
```

### The graph in one idea

```ts
// For every [[wikilink]] in a note body, emit an edge. Unresolved targets
// become "ghost" nodes — they appear in the graph as dashed magenta so
// missing ideas become visible opportunities.
const { nodes, edges } = buildGraph(notes);
```

The simulation preserves node positions across edits, so the graph feels
alive rather than reset-on-every-keystroke.

## Roadmap

Today (day 1 of this project's rotation) establishes the foundation:
**graph, editor, wikilinks, backlinks, palette, persistence.** Upcoming
rotations will add:

- [ ] AI synapse — auto-suggest links between semantically related notes
- [ ] Embeddings index + semantic search in the palette
- [ ] Daily-note template + journaling workflows
- [ ] Import/export: Markdown vault round-trip, Obsidian parity
- [ ] Publishable "garden" view — share a subgraph as a static site
- [ ] Collaborative vaults via CRDT sync (Yjs)
- [ ] Mobile-first capture PWA

## License

MIT
