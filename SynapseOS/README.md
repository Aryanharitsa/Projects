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
- **Synthesis — read your clusters, don't just see them.** The topic
  palette tells you *that* a cluster exists and what it's called.
  Synthesis tells you what it *says*. Click ❍ on any cluster and get a
  briefing built straight from its member notes: a **cited synthesis
  paragraph** (the most representative sentences, stitched into prose,
  ordered by how central each source is to the topic), the **key
  claims**, the **open threads** you haven't resolved (member notes
  phrased as questions + under-developed stubs), and the **bridges** —
  notes elsewhere in your graph that are semantically close to this
  topic but that the synapse graph hasn't linked yet. A **cohesion**
  score says how tightly the topic actually holds together. Every
  sentence and claim links back to its source note; **⤓ md** exports the
  whole brief as portable Markdown. Extractive + deterministic by
  default; optional LLM polish (`SYNAPSE_LLM_KEY`) rewrites the synthesis
  under a strict citation contract, falling back silently on any error.
- **Tensions — where your second brain disagrees with itself.**
  Synthesis surfaces what a cluster *says*; Tensions surfaces where
  your graph *contradicts itself*. For every pair of semantically-close
  notes whose stances diverge — opposing valence ("good · works · ship"
  vs "bad · breaks · overrated"), an antonym pair (simple/complex,
  fast/slow, overrated/underrated), both-sided contrast cues, or a
  title clash ("Against folders" vs "Why folders work") — the panel
  shows the conflict with one quote per side as proof, a magnitude
  meter, and a **⤴ Reconcile** button that pre-fills the composer with
  an auto-generated bridge note draft. Tabs split internal (same
  cluster, where you expected agreement) from cross (philosophical
  disagreement between topics). The header badge tells you how many
  unresolved contradictions your second brain is currently carrying.
  Pure stdlib · deterministic · portable Markdown export.
- **Atlas — a cartographer's view of your second brain.**
  Every other surface looks at one cluster, one pair, one note. Atlas
  zooms out and reads the whole map. It plots every cluster on a
  **cohesion × activity** quadrant chart and classifies each into one of
  four shapes: **Strongholds** (high cohesion + high activity — your
  bread-and-butter), **Frontiers** (still forming, actively growing — the
  topics where you're currently thinking hardest), **Vaults** (tight but
  cooling — solid clusters that haven't been touched in a while), and
  **Drift** (stale and unfocused — refactor candidates). Each cluster
  ships with its size, internal density, growth velocity over a
  configurable window (7/30/90/180d), days-since-touched, and a count of
  **bridge candidates** — notes elsewhere with cosine ≥ 0.16 to this
  cluster's centroid that the synapse graph hasn't drawn yet. A
  prioritized **recommendations** panel translates those signals into
  one-click moves: "*Synthesize X while it's hot*", "*Y may be two
  topics*", "*Z hasn't been touched in 31d*", "*3 potential bridges into
  W*". Click a bubble to inspect a cluster; click ✦ to jump straight into
  Synthesis; click ⊙ to isolate it on the canvas. Pure stdlib,
  deterministic, exportable to portable Markdown.
- **Pulse — what changed in your second brain this week.**
  Atlas is the snapshot of *where* every cluster sits right now.
  Chronicle is the biography of *one* cluster, chapter by chapter.
  Daily Brief is *today's* revisit picks. **Pulse fills the gap between
  them — the cross-cluster, time-windowed diff.** Pick a window
  (1d / 7d / 30d / 90d) and Pulse reads the whole graph as a story:
  **new notes** written, ≈ **words shipped**, **revisits**, a
  consecutive-day **writing streak**, the current
  **synapse / hub / bridge** counts, and a daily activity
  **sparkline** that splits creation vs revisits. Per cluster: a
  **status badge** (``born`` if every member is in-window · ``hot``
  if ≥ 3 new · ``emerging`` if the new majority crossed 50% · ``warm``
  for minor moves · ``dormant`` for silence), a **momentum bar**,
  **share-new %**, **centroid drift** between the pre-window and
  in-window halves (when both are populated — same `1 − cosine` move
  Chronicle uses), the **new vocabulary** the latest notes pulled in
  scored against the rest of the cluster, and the in-window note
  titles. **Bridges born** lists every fresh cross-cluster synapse
  whose two ends sit in *different* communities and where at least
  one end is a new note — the cross-pollination you just drew. **Hubs
  born** lists new notes that already pull ≥ 3 synapses (instant
  centrality is rare and worth surfacing). A library-wide **vocabulary
  delta** prints emerged vs faded terms across the whole graph using
  the same forgiveness factor as Chronicle so a slowly-mutating
  lexicon still registers. A prioritized **recommendations** panel
  distils the signals into one-click moves: *synthesize a hot cluster
  before it scatters*, *name an emerging one*, *re-read a brand-new
  hub*, *write a connector note for a fresh bridge*, *revisit a
  long-dormant cluster*. Pure stdlib, deterministic, portable
  Markdown export. Header badge counts new notes + bridges in the
  last 7d so the surface signals when there's a story to read.
- **Chronicle — watch your topics evolve.**
  Every other surface in SynapseOS is a snapshot of *right now*. Chronicle
  is the only one that asks *how has your thinking on this topic changed
  over time?* For every eligible cluster (≥ 4 notes, non-zero time span),
  it sorts members chronologically and carves them into **equal-time
  chapters** (3–6 by default, configurable; thin chapters are merged
  hierarchically into their smaller neighbor so the chapter count is
  adaptive to your actual writing cadence). Per chapter you get the
  **date range**, an **anchor note** (highest cosine to chapter centroid)
  + its first sentence, and a chapter-aware **TF-IDF** ranking that names
  each chapter by its own distinctive voice without being drowned by the
  cluster-wide vocabulary. Inter-chapter **drift velocity** = `1 −
  cosine(centroid_i, centroid_{i+1})` — angular distance in embedding
  space; the **pivot** is the inter-chapter gap with the largest velocity
  (the inflection moment). Cluster-level **total drift** = start-to-end
  cosine distance; categorizes as **calm** (< 0.10), **shifting**
  (0.10–0.25), or **pivoting** (≥ 0.25). The vocabulary delta panel
  surfaces **emerged** terms (top in the last chapter that were rare or
  absent at the start) and **faded** terms (the inverse) so the prose
  movement is explicit, not vibes. A horizontal **drift bar** per cluster
  reads the shape at a glance — chapter widths proportional to note count,
  pivot chapter highlighted. One-click jumps into **Synthesis** (read the
  whole cluster) or canvas isolation (see just this cluster's nodes), and
  any anchor opens its source note. Pure stdlib, deterministic, exportable
  to portable Markdown. Header badge counts pivoting clusters.
- **Echoes — collapse the duplicates your second brain quietly accrued.**
  Every other SynapseOS surface treats similarity as a virtue. Echoes
  flips the sign. Pairs above a tunable cosine `τ` (default 0.72) form
  single-linkage **dedup clusters**; each cluster reports its
  **redundancy %**, the **chars you'd recover by merging**, the
  auto-picked **canonical "merge-into" target** (highest centrality +
  longest body), and a **sentence-level overlap ledger**. The modal
  paints duplicate phrases in cyan inside each member's body
  (substring-matched against fuzzy-bucketed sentence groups, so
  re-phrasings collapse — Jaccard ≥ 0.55 over content words). A live
  **merge preview** rebuilds server-side whenever you flip canonical,
  drop a member, or edit the title/body — the resulting merge replaces
  the canonical note **in-place** (id preserved so external links
  resolve) and deletes the duplicates. A **Mark distinct** button
  persists `(a, b)` pairs to a `dedupe_skips` table so a "no, those two
  are different" decision sticks forever. Header badge counts active
  clusters; deterministic; portable Markdown export.
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
- **Distill — paste anything, ship atoms.** PKM has one cold-start
  problem: an empty graph. Distill kills it. Paste an article, a meeting
  transcript, a Slack thread, or your own braindump — the segmenter
  splits it on headings, blank lines, and sentence boundaries, then
  proposes one *atomic note* per fragment with a tight title, distinctive
  tags, the **cluster it would join**, and the **3 strongest synapses it
  would form** against your existing graph. **You see all of this before
  any save.** Edit titles inline, prune tags, drop atoms you don't want,
  then commit in one click. The page flashes
  `N atoms added · M synapses formed` and the graph refreshes. Optional
  LLM mode (`SYNAPSE_LLM_KEY`) polishes titles and tags; falls back
  silently to the heuristic on any error.
- **Trails — show your thinking, replayable.** Save an investigation as
  an ordered walk through your notes ("here's how I got from
  *embeddings as memory* to *vector DBs are just indexes*"), with an
  optional caption per stop. The canvas dims everything outside the
  trail and overlays an amber polyline through the stops — solid where
  the walk rides a real synapse at the current τ, dashed where it
  *leaps* across a gap. Press **▶ play** for an auto-advancing
  film-strip view of your own reasoning; hit **⤓ markdown** to export
  a self-contained portable artifact. Build a trail by hand, or seed
  one from a `PathFinder` result with one click. Every step shows
  cluster, tags, caption, snippet, and the cosine strength to the
  next stop.
- **Daily Brief — your second brain, on a rotation.** Spaced-revisit
  engine surfaces ~5 notes per day you should re-engage with: stale
  hub notes, orphans the graph forgot, and a forced cross-cluster
  pick so the brief never gets stuck in one topic. Each card carries
  a one-line auto-generated **journal prompt** ("How does *X* connect
  to *Y* in the *embeddings* cluster?") and **bridge suggestions** —
  notes from other clusters with strong cosine to the pick that the
  synapse graph hasn't linked yet. Idempotent per day, varies per
  day via deterministic jitter, marks notes as seen so they decay
  out of the rotation.
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
│  · DailyBrief · Distill · TrailPlayer · Synthesis · Tensions · Echo · Atlas · Chronicle · Pulse modals │
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
│       │           │              │              │            │           │
│       ▼           ▼              ▼              ▼            ▼           │
│  atomize.py    embed.py — 512-d   revisit.py — trails.py    llm.py       │
│  (distill:     hashing-trick      daily brief  (resolve +   stdlib HTTP  │
│   segment +    embedder           (staleness · suggest_next· to provider │
│   title +      (L2-normalized)     centrality·  markdown   APIs)         │
│   tags +                           orphan ·     export)                  │
│   cluster +                        diversity)   synthesis.py             │
│   neighbor                                      (centroid · cohesion ·   │
│   preview)                                       cited overview · claims ·│
│                                                  open threads · bridges) │
│                                                 tensions.py              │
│                                                 (polarity · antonyms ·   │
│                                                  contrast · title-clash ·│
│                                                  bridge-prompt + md export) │
│                                                 echo.py                  │
│                                                 (single-linkage dedup ·  │
│                                                  fuzzy sentence buckets ·│
│                                                  in-place merge + skips) │
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

### Distill

The atomic-notes problem: people *know* their PKM should be a swarm of
small, citable claims, but writing them by hand is friction-heavy, so the
graph stays empty and gets abandoned. Distill closes the gap.

**Pipeline (all pure, zero-deps, deterministic):**

```
1. SEGMENT   blank lines + markdown headings + bullet runs split first;
             oversized paragraphs sentence-split on `[.!?]` followed
             by capital / quote / paren; tiny final fragments fold
             backward unless they're heading-led.
2. TITLE     heading-lift > first-sentence > word-bounded trim @ 80
             chars, with clause-boundary preference at `: ` / ` — ` /
             `; ` / `, ` for long openers.
3. TAGS      TF-IDF-flavored distinctiveness: tf · log(1 + n_atoms/df)
             across 1- and 2-grams of the input. Top bigram + top-2
             unigrams, slugified, deduped, stopworded, max 3.
4. CLUSTER   embed atom · cosine against each community's centroid ·
             best match ≥ 0.18 wins. Reported as `cluster_id + name +
             color + % match` so the card pre-shows the landing.
5. NEIGHBORS embed atom · cosine against every existing note · top 3
             at ≥ τ become the predicted incoming synapses; total
             count above τ becomes the "expected_synapses" badge.
6. (OPT) LLM heuristic title/tags get a JSON-output refine pass to
             tighter copy. Any error → fallback to heuristic, silently.
```

**Per atom, the preview card shows:**

- Editable title (heading-lifted or sentence-derived)
- Editable body (paragraph or sentence-packed)
- Editable tag chips (click to remove, type to add, cap 5)
- Cluster pill — color + name + cosine % match, or "no cluster yet"
- Up to 3 **predicted synapse chips** — click to peek at the existing
  note in the inspector (so you can decide *before* committing whether
  to split / merge / drop)
- A red **"will be an orphan"** warning when no neighbors ≥ τ
- **`✨ llm-refined`** badge when an atom's title/tags went through the
  LLM (the rest of the metadata is always heuristic)
- Drop / restore — toggleable so you can prune without retyping

**Commit** persists the surviving atoms in order, recomputes the graph
once, and reports per-atom plus aggregate `synapses_formed` so the page
flash is honest. Atoms that landed orphaned are immediately picked up by
the Orphan Rescue panel.

### Trails

A trail is an ordered list of `(note_id, caption)` steps. It's the
user explicitly *showing their thinking*: a syllabus, an investigation,
a derivation. Trails persist in their own SQLite table — the notes
themselves stay untouched — and resolve at read time against the live
synapse graph, so a trail's "health" reflects the current τ.

```
health(trail) = (# consecutive steps that ride a synapse) / hops
```

A 100% trail is a synapse-walk — every step rides an edge the canvas
would have drawn anyway. A 0% trail is a leap-walk — the user is
asserting a connection the embedding model doesn't see. Both are
useful annotations; neither is "wrong".

Each step exposes:

- **`strength_to_next`** — raw cosine to the following step, even if
  it's a leap. The player renders a colored bar so the reader can
  feel which transitions are tight vs. loose.
- **`is_synapse_to_next`** — `strength_to_next >= τ`. Used to pick
  the overlay style (solid amber vs. dashed pink).
- **Cluster + color** — picked up from the live graph so the player
  card matches the canvas palette without an extra join.

The **builder** suggests the tail's strongest synapse neighbors as
one-click next steps. Empty-trail draft? It surfaces the highest-
weight (most central) notes as starting points so you never face a
blank canvas. The **player** auto-advances every 4.2 s in play mode
and supports `← / → / space` for keyboard nav.

**Markdown export** (`GET /trails/{id}/export.md`) renders each stop
as a `## N. Title` block with cluster, tags, caption, snippet, and a
`→ cosine 0.42 · synapse` (or `⤳ … · leap`) annotation between stops.
The export is portable — readers don't need to know SynapseOS exists.

### Daily Brief

Every PKM tool fails the same way: notes get written once, never re-read.
The brief fights that with a small composite scorer:

```
score(note) =   0.55 · staleness(days_since_touched)
              + 0.25 · centrality(degree, weight)
              + 0.30 · is_orphan
              − 0.20 · same_cluster_picks_already_chosen
              + jitter( note_id × YYYY-MM-DD )    ∈ [-0.05, +0.05]
```

- **Staleness** is a piecewise curve: 0 below a day, linear ramp 0→1
  across days 1–14, holds at 1.0 through day 60, decays gently to 0.65
  by day 180. Very old notes still surface — just less urgently than
  freshly-stale ones, so the brief never gets stuck on a single
  forgotten note.
- **Centrality** is `0.55·degree_norm + 0.45·weight` — both already
  computed by the synapse graph, so the brief reuses the
  user-visible "this is a hub" signal.
- **Orphan bonus** is flat: isolated notes need attention before the
  threshold drifts and they become invisible.
- **Diversity penalty** kicks in greedily as we build the top-K so a
  hot topic can't monopolize the day's picks.
- **Jitter** is keyed by `(note_id, YYYY-MM-DD)` so the brief is
  idempotent within a day and reshuffles tie-breaks across days
  without dragging the scoring physics into randomness.

Each pick carries:

- A short **journal prompt** templated from the note's title and its
  cluster's name + top distinctive term ("How does *X* connect to *Y*
  in the *embeddings* cluster?"). Orphans get a different template
  ("Where does *X* belong?").
- Up to **2 cross-cluster bridge suggestions** — notes from *other*
  clusters with cosine ≥ 0.20 to the pick. Same-cluster neighbors
  already light up in the synapse view; the interesting suggestion is
  the one that *could* bridge clusters but doesn't yet.
- A **"mark seen"** affordance that updates `last_seen_at` so the
  staleness term decays for the next brief.

Pure stdlib — no new Python deps.

```
SYNAPSE_LLM_PROVIDER  anthropic | openai      (default: anthropic)
SYNAPSE_LLM_KEY       your provider key       (omit to keep extractive only)
SYNAPSE_LLM_MODEL     model id                (default: claude-haiku-4-5-20251001
                                                or gpt-4o-mini)
```

Zero new Python deps — `urllib.request` does the HTTP.

### Synthesis

Clustering (Day 9) made your topics *visible* and *named*. But a violet
blob labelled "embeddings" still isn't knowledge — you have to open each
member note to learn what it says. Synthesis turns a cluster into a
readable brief, all extractively and deterministically:

```
1. CENTROID    mean of member embeddings, L2-normalized → the topic's
               "center of mass" in vector space.
2. COHESION    mean cosine(member, centroid) ∈ [0,1] — how tightly the
               topic actually holds together. Low cohesion ⇒ the cluster
               is two half-topics waiting to split.
3. HARVEST     split every member body into sentences; score each by
               cosine(sentence, centroid) + 0.04·key_term_hits
               + 0.02·source_centrality.
4. SELECT      pick the top sentences with MMR-style dedup (drop any whose
               cosine to an already-picked sentence > 0.86), preferring
               one sentence per distinct note so the brief spreads across
               the cluster. Top 3 → overview, next 5 → key claims.
5. COMPOSE     order the overview sentences by their source note's
               centrality and stitch into prose; every sentence keeps an
               inline [#N] citation to the Sources list.
6. THREADS     member notes phrased as questions (title or body ends in
               "?") + under-developed members (thin body, or zero
               intra-cluster synapses) → "open threads."
7. BRIDGES     notes in *other* clusters with cosine(note, centroid) ≥
               0.16 that the synapse graph hasn't linked to any member —
               cross-pollination the graph is one τ-nudge from drawing.
```

Sources are numbered by centrality so `[#N]` is a stable, clickable
reference. **Cohesion** reuses the same embeddings the canvas already
holds; nothing is recomputed twice. The **markdown export**
(`GET /digest/export.md`) renders the whole brief — synthesis, claims,
threads, bridges, sources — as a portable artifact that reads stand-alone
outside SynapseOS.

**Optional LLM mode.** When `SYNAPSE_LLM_KEY` is set the overview is
rewritten by a small LLM under a strict contract ("use ONLY the numbered
sources, every sentence ends with `[#N]`, 2–3 sentences, ≤80 words"). We
*reject* any LLM answer that drops its citations and fall back to the
extractive overview — synthesis never silently loses its receipts.

Pure stdlib for the default path — no new Python deps.

### Tensions

Every other surface in SynapseOS reveals what *agrees*: clusters bind
related notes together, synapses draw the strongest links, Synthesis
paraphrases the consensus inside a cluster. None of them surface where
your graph **disagrees with itself**. A note that says
*"boring tech wins"* sitting next to one that says *"that framework was
a mistake"* is a **tension** — a place where your beliefs haven't been
reconciled — and that's the highest-value PKM signal nobody else exposes.

Click **⟷ tensions** in the header. Each row pairs two
semantically-close notes whose stances disagree, named with a magnitude
meter and a one-quote-per-side proof of the conflict. The **Reconcile**
button pre-fills the composer with a bridge note draft so the
disagreement turns into the next atomic note in one click.

For any pair `(a, b)` we declare a tension when ``cosine(a, b) ≥ floor``
(default `0.18`) **and** at least one detector fires:

```
polarity   one note leans positive (good · best · ship · wins · works ·
           scale · …), the other negative (bad · worst · breaks · fails ·
           overrated · slow · …). Negation flips local valence so
           "not bad" reads positive, "not great" negative. Fires when
           sign(pol_a) ≠ sign(pol_b) and both magnitudes ≥ 1.

antonym    a polar antonym pair appears one per side
           (simple/complex, fast/slow, overrated/underrated,
           robust/brittle, …). Two pairs saturates the signal —
           contradictions aren't additive past a point.

contrast   explicit contrast cues ("but", "however", "although",
           "actually", …) appear on BOTH sides. One side's hedge is
           just writing; both sides' is each qualifying the other.

title      title-form contention: "Against X" vs a title sharing X's
           topic words, or opposite-polarity titles with a shared
           non-stopword topic token. Light stemming (folder ≈ folders)
           so the most common plural doesn't hide the obvious pair.
```

```
magnitude = clip(cosine(a, b) · (1 + Σ signal weights),  0, 1)
```

A **title-clash bypass** lets unambiguous "Against X" pairs surface even
below the cosine floor — the hashing-trick embedder isn't a transformer
and shouldn't override a deterministic linguistic signal.

Each tension carries:

- **kind** — `internal` (same cluster — where you expected agreement
  and got conflict) or `cross` (philosophical disagreement between
  topics). The brief tabs split on this.
- **evidence** — one quote per side, the most-polarized sentence in
  each note in the direction of that note's own stance. The UI shows it
  with a `↑`/`↓` arrow tinted lime/rose.
- **bridge** — an auto-generated `(title, prompt, tags)` triple. Hit
  **⤴ Reconcile** and the NoteComposer fills with it; commit and the
  graph rewires.
- **markdown export** (`GET /tensions/export.md`) — the whole brief
  as a portable artifact, sectioned by `internal`/`cross`, every quote
  and signal preserved.

Pure stdlib, deterministic, pure function of `(notes, embeddings, floor,
limit)`. The O(N²) pair scan precomputes per-note polarity, word set,
and best evidence sentence once before the loop so each pair is
constant-time.

---

## Echoes — collapse the duplicates your second brain quietly accrued

Every other surface in SynapseOS treats *similarity* as a virtue:
synapses draw it, communities cluster it, Synthesis paraphrases the
consensus inside one. **Echo flips the sign.** The same property that
powers all the good stuff is also a tax — as your store grows you
naturally restate the same insight in different words, weeks apart.
Those near-duplicates pollute the graph (hub nodes that shouldn't be
hubs), inflate cluster sizes, and make search noisier.

Click **⌬ echoes** in the header. The modal lists every near-duplicate
cluster with a redundancy bar, recoverable-chars badge, and pairwise
cosine ladder. For each cluster:

```
threshold   pairs with cosine ≥ τ (default 0.72) form edges; union-find
            yields connected components of size ≥ 2. Single-linkage is
            intentional — if A≈B and B≈C, you want A and C in the same
            merge UI even if A and C only just miss the bar themselves.

canonical   the member with highest centrality (sum of cosine to the
            rest of the cluster), tie-broken by longest body then
            oldest id. That's "the one that already says most of what
            the others say" — the natural merge target.

sentences   every sentence across every member is fuzzy-bucketed by
            content-word Jaccard (≥ 0.55, stop-words stripped) so
            rephrasings collapse. Each bucket's representative becomes
            one sentence in the merged body; ``note_ids`` records every
            member that contributed so the UI can paint
            "appears in 3 notes" badges.

merged_body canonical's sentences first (in original order), then any
            *new* sentences contributed by each other member appended
            afterwards. The output reads like the canonical augmented
            with what the duplicates added — not a Frankenstein
            paragraph.
```

The **live merge preview** rebuilds server-side every time you flip the
canonical, drop a member out of the merge, or edit the title/body, so
the recoverable-char count and merged-tag union always reflect what
*Merge* would actually persist. **Merge** replaces the canonical note
**in-place** — its id is preserved so any external bookmarks keep
resolving — and deletes the other duplicates.

**Mark distinct** persists every pair in the cluster to a
`dedupe_skips` table; subsequent `/echo` calls filter them out forever,
so a "no, those two are different" decision sticks. `DELETE /echo/skip`
forgets a single skip if you change your mind.

Pure stdlib, deterministic, pure function of `(notes, embeddings,
threshold, skips)`. Cheap enough that the header probe runs on every
graph refresh — so the badge always reflects "your second brain has N
duplicate clusters waiting to be merged" without forcing a modal load.

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
| `GET`  | `/brief?k=&date=`            | Today's revisit picks: `{ date, k, total_notes, picks: [ { note_id, title, snippet, score, reasons[], prompt, connections[], cluster_*, days_since_seen, is_orphan } ], stats }`. `date` defaults to today UTC. |
| `POST` | `/notes/{id}/touch`          | Mark a note as just re-engaged with; refreshes `last_seen_at`. `{ ok, note_id, last_seen_at }` |
| `GET`  | `/trails`                    | List trails (title, step count, health badge, no bodies)                          |
| `POST` | `/trails`                    | Create. Body: `{ title, description?, steps: [{ note_id, caption? }], origin? }` |
| `GET`  | `/trails/{id}?threshold&top_k` | Resolve: steps with title, snippet, tags, caption, cluster, strength_to_next   |
| `PATCH`| `/trails/{id}`               | Partial update: any of `{ title?, description?, steps? }`. Full step replace.   |
| `POST` | `/trails/{id}/append`        | Append one step. `{ note_id, caption? }`                                         |
| `DEL`  | `/trails/{id}`               | Delete the trail. Notes are untouched.                                            |
| `GET`  | `/trails/{id}/suggest_next?k=`| Top synapse neighbors of the tail that aren't already on the trail              |
| `GET`  | `/trails/{id}/export.md`     | Self-contained Markdown export with cosine-annotated transitions                  |
| `POST` | `/atomize?threshold&top_k`   | Distill long-form text into atomic-note previews (no save). Body: `{ text, mode? }`. Returns `{ atoms: [{ temp_id, title, body, tags, char_count, cluster_id/name/color, cluster_strength, neighbors[], expected_synapses, llm_refined }], total_chars, mode_used, llm_available, llm_provider, notice? }` |
| `POST` | `/atomize/commit?threshold&top_k` | Bulk insert edited atoms. Body: `{ atoms: [{ title, body, tags[] }] }` (1–64). Returns `{ created: [{ note_id, title, synapses }], synapses_formed }` |
| `GET`  | `/digest?cluster_id=&threshold&top_k&mode` | Topic synthesis for one cluster: `{ name, color, size, terms[], cohesion, overview, claims[], open_threads[], bridges[], sources[], mode_used, llm_available, notice? }`. `mode` ∈ `auto/extractive/llm`. |
| `GET`  | `/digest/export.md?cluster_id=…` | Self-contained Markdown brief for one cluster (synthesis · claims · open threads · bridges · sources). |
| `GET`  | `/tensions?floor=&limit=&threshold=&top_k=` | Detected contradictions: `{ threshold, floor, total_pairs_scanned, candidate_count, tension_count, tensions: [ { a_id, a_title, b_id, b_title, cosine, magnitude, signals: [{ kind, weight, detail }], evidence: [{ note_id, title, sentence, polarity }], bridge_title, bridge_prompt, bridge_tags[], kind: "internal"\|"cross", cluster_a/b/_name/_color } ], stats }`. |
| `GET`  | `/tensions/export.md?floor=&limit=` | Tensions brief as portable Markdown, sectioned by `internal` / `cross` with both quotes and the bridge prompt per tension. |
| `GET`  | `/echo?threshold=&limit=`    | Near-duplicate clusters: `{ threshold, total_notes, candidate_pairs, cluster_count, skipped_pair_count, clusters: [ { cluster_id, size, redundancy, peak_cosine, wasted_chars, chars_total/unique, canonical_id, members[], pairs[], merged_title, merged_body, merged_tags[], sentences: [{ text, note_ids[], is_duplicate, is_canonical_source }], overlap_ratio } ], stats }`. |
| `POST` | `/echo/preview`              | Live merge preview for `{ note_ids[], canonical_id? }` — recomputed when the user flips the canonical or drops a member. No DB writes. |
| `POST` | `/echo/merge`                | Collapse the cluster: replace canonical in-place (id preserved), delete the duplicates. Body: `{ note_ids[], canonical_id?, title?, body?, tags? }`. Returns `{ merged_note_id, merged_title, deleted_ids[], wasted_chars_recovered, final_synapses }`. |
| `POST` | `/echo/skip`                 | Mark `(a, b)` pair(s) as intentionally distinct. Body: `{ pairs: [[a,b], …], reason? }`. Persisted to `dedupe_skips`; subsequent `/echo` calls filter them out forever. |
| `GET`  | `/echo/skips`                | List all currently-skipped pairs.                                                 |
| `DEL`  | `/echo/skip?a=&b=`           | Forget a single skip so the pair can resurface in the dedup brief.                |
| `GET`  | `/echo/export.md?threshold=&limit=` | The dedup brief as portable Markdown — one section per cluster with all bodies + the suggested merged body. |

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
- [x] **Daily Brief** — spaced-revisit picks with journal prompts and
      cross-cluster bridge suggestions, idempotent per day *(shipped)*
- [x] **Trails** — curated, replayable walks through the graph with
      auto-suggested next steps, dashed-leap overlay, and portable
      Markdown export *(shipped)*
- [x] **Distill** — atomize pasted long-form text into preview cards
      with title/tag/cluster/neighbor predictions and bulk commit
      *(shipped)*
- [x] **Synthesis** — auto-written, cited topic briefings per cluster
      (synthesis prose · key claims · open threads · cross-cluster
      bridges · cohesion score · portable Markdown export) *(shipped)*
- [x] **Atlas** — executive cartography over every cluster: cohesion ×
      activity quadrant chart (Strongholds · Frontiers · Vaults · Drift),
      per-cluster metrics, prioritized recommendations, portable Markdown
      export *(shipped)*
- [x] **Chronicle** — temporal narrative of how each cluster evolved:
      equal-time chapters with within-cluster TF-IDF chapter names,
      per-chapter anchor + sentence, inter-chapter drift velocity, pivot
      detection, emerged/faded vocabulary deltas, calm/shifting/pivoting
      categorization, portable Markdown export *(shipped)*
- [x] **Pulse** — cross-cluster, time-windowed diff of the whole graph:
      headline + metrics (new notes · words · revisits · streak),
      daily activity sparkline (created vs revisited), per-cluster
      status (born / hot / emerging / warm / dormant) with momentum bar,
      share-new, centroid drift, new-vocabulary chips and hot titles,
      cross-cluster bridges born, hubs born (new notes with degree ≥ 3),
      library-wide vocabulary delta, prioritized recommendations,
      portable Markdown export *(shipped)*
- [ ] Export to Markdown + JSON (with embeddings) for portability
- [ ] Desktop build via Tauri so the whole thing ships as a single app

---

## License

MIT — see the repo root.

Built by [@Aryanharitsa](https://github.com/Aryanharitsa).
Part of the [projects rotation](../PROJECT_ROTATION.md).
