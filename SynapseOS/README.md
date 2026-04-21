# 🧠 SynapseOS

**A neural second brain.** Write your notes. SynapseOS embeds them, measures how
similar each one is to every other, and auto-draws a weighted **synapse graph**
that you can literally see grow as you think.

> Think of it as what Obsidian's graph view *wanted* to be: no manual
> `[[wikilinks]]`, no folder tax. Just vectors, cosine similarity, and a
> canvas-rendered force-directed layout that feels alive.

---

## ✨ What it does today (v0.1)

### 🔗 Auto-synapses
Every note is tokenised, cleaned of stopwords, and turned into an L2-normalised
**TF-IDF** vector. Pairwise cosine similarity gives each note its `top-k`
nearest neighbours; anything above a cutoff becomes a weighted edge in the
graph. Every create / update / delete triggers a full rewire — on a personal
corpus (hundreds of notes) this stays sub-100ms because the vectors are sparse.

### 🧭 Graph-first UX
The central canvas is a live d3-force simulation where **cluster = topic**:

- Node radius scales with degree (popular ideas look big).
- Edge thickness & opacity scale with synapse strength.
- Hover a node → neighbourhood highlights, everything else dims.
- Click → right panel becomes an Inspector with the closest neighbours
  (sorted by strength) and a jump-to button for each.

### ✍️ Capture → rewire → done
Click *Capture thought*, write it, hit save. The whole graph rewires and the
new node snaps into place in its true cluster — no link discipline required.

### 💯 Zero onboarding
No API keys. No OpenAI dependency. No GPU. The synapse engine is 100 %
stdlib Python. `pip install`, `pnpm dev`, done — the first-run graph is
already seeded with ten interconnected example notes so you can see how it
feels before writing a word.

---

## 🏗 Architecture

```
SynapseOS/
├── backend/                  # FastAPI + SQLite + zero-dep synapse engine
│   ├── requirements.txt      # fastapi · sqlalchemy · pydantic
│   ├── run.sh                # one-command dev server
│   └── app/
│       ├── main.py           # FastAPI app, CORS, startup seed
│       ├── db.py             # SQLAlchemy engine & session
│       ├── models.py         # Note · Synapse
│       ├── schemas.py        # Pydantic IO
│       ├── seed.py           # seeds 10 example notes on first boot
│       ├── routers/
│       │   ├── notes.py      # CRUD + /notes/rebuild
│       │   └── graph.py      # /graph  → nodes, edges, stats
│       └── services/
│           ├── embedding.py  # tokenise · TF-IDF · cosine
│           └── synapse.py    # wipe & recompute all edges
│
└── frontend/                 # React 19 + Vite + Tailwind v4
    ├── package.json
    ├── vite.config.js        # /api proxy → :8000
    └── src/
        ├── main.jsx
        ├── App.jsx           # nav shell
        ├── index.css         # ambient gradient backdrop
        ├── lib/
        │   └── api.js        # tiny typed fetch wrapper
        ├── pages/
        │   ├── Landing.jsx   # hero, neural glyph, feature grid
        │   └── Brain.jsx     # 3-pane workspace
        └── components/
            ├── SynapseGraph.jsx   # canvas · d3-force · glow & bloom
            └── NoteEditor.jsx     # capture / edit / delete
```

---

## 🚀 Quickstart

```bash
# 1. backend (term 1)
cd SynapseOS/backend
bash run.sh                 # → http://localhost:8000
# The first boot seeds ten example notes and computes the initial graph.

# 2. frontend (term 2)
cd SynapseOS/frontend
pnpm install                # or npm / yarn
pnpm dev                    # → http://localhost:5173
```

Open http://localhost:5173 → click **Open the Brain**.

---

## 🔌 API

All routes live under `/api`.

```http
GET    /api/notes              # list, newest-updated first
GET    /api/notes/{id}         # single note
POST   /api/notes              # create (auto-rebuilds synapses)
PUT    /api/notes/{id}         # update (auto-rebuilds synapses)
DELETE /api/notes/{id}         # delete (auto-rebuilds synapses)
POST   /api/notes/rebuild      # manual rewire
GET    /api/graph              # { nodes, edges, stats }
GET    /api/health
```

`GET /api/graph` returns:

```json
{
  "nodes": [
    { "id": 1, "title": "...", "tags": ["ml", "math"], "size": 4,
      "created_at": "2026-04-21T..." }
  ],
  "edges": [
    { "source": 1, "target": 2, "strength": 0.42 }
  ],
  "stats": {
    "node_count": 10, "edge_count": 17,
    "avg_degree": 3.4, "avg_strength": 0.186, "max_degree": 6
  }
}
```

---

## 🧮 Why TF-IDF (for now)?

On short-to-medium personal notes, TF-IDF often **beats** off-the-shelf
sentence embeddings for *topical* similarity — embeddings pull in
tonal/stylistic noise that isn't what you want when the goal is "do these
two notes share subject matter?". Plus: zero dependencies, no GPU, no API
key, works on a Raspberry Pi.

The embedder interface (`app/services/embedding.py`) is deliberately
minimal — any object with `.encode(text) -> Sequence[float]` can be swapped
in. A future day will plug in local `sentence-transformers` or an OpenAI
embeddings provider behind the exact same shape.

---

## 🛣 Roadmap

- [ ] Pluggable embedders — local `sentence-transformers`, OpenAI, Voyage.
- [ ] Per-edge explanations ("these two share the terms *attention* and
      *rotary*").
- [ ] Incremental synapse updates (don't rebuild from scratch on every edit).
- [ ] Chat-with-your-brain mode: RAG over selected cluster.
- [ ] Markdown rendering + code-fence support in the editor.
- [ ] Export / import as a JSON vault.

---

## 👨‍💻 Author

Built with ❤️ by **Aryan D Haritsa** · PES University · AI / full-stack.
