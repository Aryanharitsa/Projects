# SynapseOS

> **Watch your brain organize itself.**
> Notes auto-link via embedding-based synapses. Clusters and their names
> emerge automatically. Isolated thoughts surface as rescuable orphans.

SynapseOS is a personal knowledge system with one opinionated idea:
**the graph is the product**. You write atomic thoughts; embeddings form
semantic synapses between them; a force-directed graph lets you *see*
how your thinking connects — *and* hands you the topical structure of
your second brain on a plate.

No folders. No manual `[[backlinks]]`. No cloud lock-in. Runs on your
machine in a minute.

---

## Why this exists

Every PKM tool falls into one of two camps:

- **Obsidian / Logseq / Roam** — you do the linking yourself. Powerful,
  but friction-heavy; most notes end up orphaned.
- **Mem / Notion AI** — black-box "magic". Good demos, but you can't
  see or tune what the system is doing.

SynapseOS splits the difference. Links are automatic *and* inspectable.
You can see every synapse, why it exists (cosine similarity), tune the
threshold live, and watch your topical clusters discover themselves.

---

## What's in the box

- **Auto-synapse formation** via cosine similarity on embeddings
  (`τ` threshold + top-*K* neighbor cap to keep the graph from turning
  into a hairball).
- **Topic palette — auto-derived clusters with auto-derived names.**
  Greedy modularity (Newman-style) partitions the synapse graph; a
  TF-IDF-style "distinctiveness" score names each cluster from its own
  members' words. Click a topic to *isolate* it in the canvas.
- **Orphan rescue.** Notes with no synapses surface in their own panel
  alongside their strongest near-miss neighbor and the exact `τ` value
  that would attach them. Lower the threshold, or refine the note —
  no thought stays isolated by accident.
- **Chat with your graph.** Ask anything in plain English. Retrieval
  *uses the synapse graph*: top-*k* semantic seeds → 1-hop fan-out
  along the same edges the canvas renders → optional community anchor
  per seed. Every answer cites notes inline (`[#1]`, `[#2]`, …) and the
  exact synapses that contributed light up cyan on the canvas.
  **Default mode is extractive (zero-dep). Optional LLM mode** when
  `SYNAPSE_LLM_KEY` is set — same citation contract.
- **Interactive force-directed graph** with zoom, drag, selection,
  community-coloured nodes, weight-haloed edges, and labels that fade
  in at zoom.
- **Semantic search** — query your brain in plain English; results
  ranked by cosine, not keyword match.
- **Path tracing** — "how is *X* related to *Y*?" Dijkstra over
  `weight = 1 − strength` finds the strongest chain of synapses,
  highlighted in the graph with animated particles.
- **Inspector panel** — full note text, tags, degree, weight, and
  strongest neighbors at a click.
- **Zero-dep embedder** — works offline; swap in OpenAI /
  sentence-transformers by replacing one function.
- **SQLite persistence** — one file, trivial backup, survives restarts.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│  Next.js 14 · App Router · Tailwind · react-force-graph-2d               │
│  ┌──────────────┬─────────────────────┬─────────────────────────────┐    │
│  │ NoteComposer │       Graph         │       ChatPanel             │    │
│  │ SearchBar    │ canvas, 60fps       │  ask/transcript/citations   │    │
│  │ TopicPalette │ community colors    │  · cyan retrieval overlay   │    │
│  │ OrphanRescue │ + isolation overlay │       Inspector             │    │
│  │ PathFinder   │ + chat traversal    │  neighbors + body           │    │
│  └──────────────┴─────────────────────┴─────────────────────────────┘    │
└─────────────────────────────────┬────────────────────────────────────────┘
                                  │ REST / JSON
                                  ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  FastAPI · pydantic · uvicorn                                            │
│  ┌──────────┬─────────────┬─────────────┬──────────────┬──────────────┐  │
│  │ main.py  │ synapse.py  │ community.py│   chat.py    │   store.py   │  │
│  │ (routes) │ (graph,     │(greedy mod. │ (graph-aware │  (SQLite +   │  │
│  │          │  search,    │ + names +   │  RAG +       │   packed     │  │
│  │          │  path)      │  orphans)   │  extractive) │   vectors)   │  │
│  └──────────┴─────────────┴─────────────┴──────────────┴──────────────┘  │
│                   │                              │                       │
│                   ▼                              ▼                       │
│         embed.py — 512-d hashing-trick    llm.py — stdlib HTTP           │
│         embedder (L2-normalized)          to Anthropic / OpenAI          │
└──────────────────────────────────────────────────────────────────────────┘
```

### The synapse formula

For any two notes *a* and *b*, an edge `(a, b)` is drawn when:

```
cosine( embed(a), embed(b) ) ≥ τ      AND
b ∈ topK( nearest-by-cosine, of a )
```

- `τ` defaults to **0.14** — tuned on the seed graph; override per
  request via `?threshold=…`
- `topK` defaults to **5** — caps hub nodes; override via `?top_k=…`

**Node weight** (the glow / inner ring) is the degree-normalized sum of
incoming edge strengths, scaled to `[0, 1]`. It's a "centrality hint,"
not true PageRank — cheap to compute and visually truthful.

**Path cost** between two notes is `Σ (1 − strength)` along the best
chain. Lower cost = stronger conceptual connection.

### Community detection

Communities are computed by **greedy modularity** (Newman 2004). Start
with each node in its own community; repeatedly merge the pair whose
merge yields the largest positive `ΔQ`:

```
ΔQ(a, b) = (e_ab / m) − (k_a · k_b) / (2m)²
```

where `e_ab` is the total edge weight between communities `a` and `b`,
`k_x` is the total weight incident to community `x`, and `m` is the
total edge weight. We chose modularity-greedy over plain LPA because
synapse graphs have *hub* notes that bridge multiple topics — LPA on
such graphs collapses everything into one giant label.

### Cluster naming

For each cluster `c` and term `t` (lowercased word, ≥ 3 chars, not in a
small stop-list):

```
score(t, c) = tf(t, c) · ( tf(t, c) / total_tf(t) ) · log(1 + |c|)
```

The middle factor is a "distinctiveness" multiplier in `[0, 1]`: terms
that live almost entirely inside cluster `c` score near 1; universal
terms score `1 / n_clusters`. Title tokens get 3× weight, tags 2×, body
1×. Top-1 becomes the cluster's display name; top-3 are the "key terms"
rendered as chips in the topic palette.

### Orphan rescue

A note is an *orphan* if it has zero edges in the current graph at
`(τ, top_k)`. For each orphan we scan all other notes by cosine and
report the strongest peer along with `nudged_τ = max(0, sim − 0.005)` —
exactly the threshold that would attach them.

### Chat with your graph

Most "RAG over notes" stops at vector search → stuff into prompt.
SynapseOS *already* builds a graph from those embeddings, so the
retriever does something better:

```
1. SEED      top-k cosine hits against the query           ─→ "match"
2. EXPAND    1-hop along each seed's synapses (the same    ─→ "synapse"
             edges the canvas renders), capped by top_k
3. ANCHOR    optionally include the highest-weight note    ─→ "anchor"
             in each seed's community (cluster anchor)
4. ANSWER    extractive (default) or LLM, with strict
             inline [#N] citations for every claim
```

Each retrieved note carries provenance: a `role` of `seed` / `synapse`
/ `community`, the seed it was reached from, and the synapse strength
along the way. The `traversal` returned alongside the answer maps
1-to-1 to edges in the live graph, so the **canvas paints exactly the
synapses that contributed** in cyan, with animated particles and a
halo around participating nodes.

**Composite score for synapse hits** (so adjacent thoughts beat random
neighbours):

```
score = (s · s_seed · 0.85^hop) + 0.4 · cosine(query, neighbour)
```

where `s` is the synapse strength along the expansion edge and
`s_seed` is `1.0` for direct seeds. We cap fan-out per node to `top_k`
and reject any edge below a `0.10` floor so retrieval stays focused.

**Default extractive answer.** No API keys, no network. We score every
sentence in the citations by `(query-term hits · 1.4) / length_norm
+ 0.6 / (citation_rank + 1)` and pick up to 5, one per citation when
possible. If nothing overlaps lexically, we fall back to a "your
strongest matches were…" summary so the answer stays honest about its
floor.

**Optional LLM mode.** Set `SYNAPSE_LLM_KEY` and the same context goes
to a small LLM under a strict citation contract ("answer ONLY from
these notes, cite inline as `[#N]`, say so plainly if missing"). On
network/LLM failure we silently fall back to extractive with a notice.

```
SYNAPSE_LLM_PROVIDER  anthropic | openai      (default: anthropic)
SYNAPSE_LLM_KEY       your provider key       (omit to keep extractive only)
SYNAPSE_LLM_MODEL     model id                (default: claude-haiku-4-5-20251001
                                                or gpt-4o-mini)
```

Zero new Python deps — `urllib.request` does the HTTP.

---

## API surface

| Method | Path                         | Purpose                                              |
|-------:|------------------------------|------------------------------------------------------|
| `GET`  | `/health`                    | `{ ok, notes: N }`                                   |
| `POST` | `/notes`                     | Create a note. `{ title, body, tags[] }`             |
| `GET`  | `/notes`                     | List all notes                                       |
| `GET`  | `/notes/{id}`                | Single note                                          |
| `DEL`  | `/notes/{id}`                | Delete                                               |
| `GET`  | `/graph?threshold&top_k`     | `{ nodes (with community + color), edges, stats }`   |
| `GET`  | `/neighbors/{id}`            | Adjacent notes + per-edge similarity                 |
| `GET`  | `/search?q=…&limit=…`        | Cosine-ranked hits against all notes                 |
| `GET`  | `/path?src=&dst=`            | Strongest-chain path between two notes               |
| `GET`  | `/communities?threshold…`    | Auto-named clusters: `[ { id, name, color, size, terms[], member_ids[] } ]` |
| `GET`  | `/orphans?threshold…`        | Isolated notes + best below-threshold candidate      |
| `GET`  | `/chat/status`               | `{ llm_available, llm_provider, extractive_available }` |
| `POST` | `/chat`                      | Graph-aware RAG. Body: `{ query, mode?, k_seed?, hops?, include_community_anchors? }`. Response: `{ answer, citations[], traversal: { seeds, expansions }, model, mode_used, latency_ms, llm_available, notice? }` |

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

Visit `http://localhost:3000`. The demo graph has 16 seed notes that
cluster into a handful of topical regions (embeddings, design,
retrieval) with a deliberately bridging "Why this app exists" note.
Click a cluster in the **Topic Palette** to isolate it. **Ask the
graph** — type a question in the chat panel and watch the cited
synapses light up cyan on the canvas. Add your own thoughts — watch
the synapses form and the topic palette refresh in real time.

### Optional: enable LLM mode

```bash
export SYNAPSE_LLM_KEY=sk-ant-…              # or sk-… for openai
export SYNAPSE_LLM_PROVIDER=anthropic        # or openai
# export SYNAPSE_LLM_MODEL=claude-haiku-4-5-20251001
uvicorn app.main:app --reload --port 8000
```

The `/chat/status` endpoint reports availability; the chat panel UI
flips its "extractive" pill to "LLM ready" automatically.

---

## Roadmap

Incremental moves for future rotation days:

- [ ] Swap hashing-trick embedder for a real model (sentence-transformers
      via a `SYNAPSE_EMBEDDER=st` env var) while keeping the zero-dep one
      as the default
- [ ] Incremental graph updates over WebSocket — new notes appear live
- [x] **Cluster view** — color nodes by community, surface auto-derived
      cluster names, allow click-to-isolate *(shipped)*
- [x] **Orphan rescue** — surface isolated notes + the threshold that
      would attach them *(shipped)*
- [x] **Chat-with-your-graph** — graph-aware RAG over synapse + community
      neighborhood, with cited citations and a live traversal overlay
      *(shipped)*
- [ ] Export to Markdown + JSON (with embeddings) for portability
- [ ] Desktop build via Tauri so the whole thing ships as a single app

---

## License

MIT — see the repo root.

Built by [@Aryanharitsa](https://github.com/Aryanharitsa).
Part of the [projects rotation](../PROJECT_ROTATION.md).
