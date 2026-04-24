# SynapseOS

> **Your second brain, as an OS.**
> Write notes. They link themselves. Traverse the graph.

SynapseOS is a personal knowledge system with a single opinionated idea:
**the graph is the product**. You write atomic thoughts; embeddings form
semantic "synapses" between them automatically; a force-directed graph
lets you *see* how your thinking connects.

No folders. No manual `[[backlinks]]`. No cloud lock-in. Runs on your
machine in a minute.

---

## Why this exists

Every PKM tool falls into one of two camps:

- **Obsidian / Logseq / Roam** — you do the linking yourself. Powerful, but
  friction-heavy; most notes end up orphaned.
- **Mem / Notion AI** — black-box "magic". Good demos, but you can't see
  or tune what the system is doing.

SynapseOS splits the difference. Links are automatic *and* inspectable.
You can see every synapse, why it exists (cosine similarity), and turn the
threshold up or down in real time.

---

## What's in the box

- **Auto-synapse formation** via cosine similarity on embeddings
  (`τ` threshold + top-*K* neighbor cap to keep the graph from turning
  into a hairball)
- **Interactive force-directed graph** with zoom, drag, selection,
  labels, and node glow proportional to centrality
- **Semantic search** — query your brain in plain English; results ranked
  by cosine, not keyword match
- **Path tracing** — "how is *X* related to *Y*?" Dijkstra over
  `weight = 1 − strength` finds the strongest chain of synapses,
  highlighted in the graph with animated particles
- **Inspector panel** — full note text, tags, degree, weight, and strongest
  neighbors at a click
- **Zero-dep embedder** — works offline; swap in OpenAI / sentence-transformers
  by replacing one function if you want
- **SQLite persistence** — one file, trivial backup, survives restarts

---

## Architecture

```
┌───────────────────────────────────────────────────────────────┐
│  Next.js 14 · App Router · Tailwind · react-force-graph-2d    │
│  ┌──────────────┬─────────────────────┬────────────────────┐  │
│  │ NoteComposer │       Graph         │     Inspector      │  │
│  │ SearchBar    │ (canvas, 60fps)     │ neighbors + body   │  │
│  │ PathFinder   │                     │                    │  │
│  └──────────────┴─────────────────────┴────────────────────┘  │
└───────────────────────────────┬───────────────────────────────┘
                                │ REST / JSON
                                ▼
┌───────────────────────────────────────────────────────────────┐
│  FastAPI · pydantic · uvicorn                                 │
│  ┌────────────┬────────────────┬───────────────────────────┐  │
│  │   main.py  │   synapse.py   │         store.py          │  │
│  │  (routes)  │  (graph build, │  (SQLite + packed vector  │  │
│  │            │   search, path)│   blobs, cached embeds)   │  │
│  └────────────┴────────────────┴───────────────────────────┘  │
│                    │                                           │
│                    ▼                                           │
│              embed.py — 512-d hashing-trick embedder           │
│           (char 4-grams + word uni/bi-grams → L2-norm)         │
└───────────────────────────────────────────────────────────────┘
```

### The synapse formula

For any two notes *a* and *b*, an edge `(a, b)` is drawn when:

```
cosine( embed(a), embed(b) ) ≥ τ       AND
b ∈ topK( nearest-by-cosine, of a )
```

- `τ` defaults to **0.14** — tuned on the seed graph; override per
  request via `?threshold=…`
- `topK` defaults to **5** — caps hub nodes; override via `?top_k=…`

**Node weight** (the glow / color) is the degree-normalized sum of
incoming edge strengths, scaled to `[0, 1]`. It's a "centrality hint,"
not true PageRank — cheap to compute and visually truthful.

**Path cost** between two notes is `Σ (1 − strength)` along the best
chain. Lower cost = stronger conceptual connection.

---

## API surface

| Method | Path                    | Purpose                                        |
|-------:|-------------------------|------------------------------------------------|
| `GET`  | `/health`               | `{ ok, notes: N }`                             |
| `POST` | `/notes`                | Create a note. `{ title, body, tags[] }`       |
| `GET`  | `/notes`                | List all notes                                 |
| `GET`  | `/notes/{id}`           | Single note                                    |
| `DEL`  | `/notes/{id}`           | Delete                                         |
| `GET`  | `/graph?threshold&top_k`| `{ nodes, edges, stats }` — ready for the UI   |
| `GET`  | `/neighbors/{id}`       | Adjacent notes + per-edge similarity           |
| `GET`  | `/search?q=…&limit=…`   | Cosine-ranked hits against all notes           |
| `GET`  | `/path?src=&dst=`       | Strongest-chain path between two notes         |

Interactive docs at `http://localhost:8000/docs`.

---

## Quick start

```bash
# 1. backend
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python seed.py                              # populate the demo graph
uvicorn app.main:app --reload --port 8000

# 2. frontend (in a second terminal)
cd frontend
cp .env.local.example .env.local            # defaults to http://localhost:8000
npm install
npm run dev                                 # http://localhost:3000
```

Visit `http://localhost:3000`. The demo graph has 16 seed notes across
ML, PKM, and engineering clusters. Add your own thoughts — watch the
synapses form.

---

## Roadmap

Incremental moves for future rotation days:

- [ ] Swap hashing-trick embedder for a real model (sentence-transformers
      via a `SYNAPSE_EMBEDDER=st` env var) while keeping the zero-dep one
      as the default
- [ ] Incremental graph updates over WebSocket — new notes appear live
- [ ] "Cluster view" — color nodes by Louvain community, not just weight
- [ ] Chat-with-your-graph: retrieval-augmented generation using the
      synapse neighborhood as the retriever
- [ ] Export to Markdown + JSON (with embeddings) for portability
- [ ] Desktop build via Tauri so the whole thing ships as a single app

---

## License

MIT — see the repo root.

Built by [@Aryanharitsa](https://github.com/Aryanharitsa).
Part of the [projects rotation](../PROJECT_ROTATION.md).
