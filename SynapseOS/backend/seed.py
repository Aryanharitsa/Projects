"""Seed a demo knowledge graph so the UI is never empty on first run.

Notes were chosen to form several tight clusters (ML infra, product,
reading) with a few deliberate cross-topic bridges. That makes the
force-directed layout pop visually and gives the `/path` endpoint
something interesting to traverse.

Usage:
    python -m backend.seed           # from the repo root
    python seed.py                   # from backend/
"""

from __future__ import annotations

import os
import sys

# Allow running as a script from either the repo root or backend/.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app import store  # noqa: E402

SEED: list[tuple[str, str, list[str]]] = [
    # --- ML / infra cluster ---
    (
        "Embeddings as memory",
        "Vector embeddings turn prose into coordinates. Cosine similarity "
        "between those coordinates is a cheap proxy for semantic relatedness. "
        "This is the substrate every second-brain tool is secretly running on.",
        ["ml", "embeddings", "foundations"],
    ),
    (
        "Hashing trick for features",
        "Feature hashing maps an unbounded token space into a fixed-size "
        "vector via a hash function + signed projection. Vowpal Wabbit used "
        "this for classifiers; it also works as a zero-dep text embedder.",
        ["ml", "embeddings", "tricks"],
    ),
    (
        "Retrieval-augmented generation",
        "RAG is embeddings + a prompt template. Fetch top-k relevant chunks "
        "by cosine similarity, stuff them into context, let the model "
        "answer. The hard part isn't the model — it's chunking well.",
        ["ml", "llm", "retrieval"],
    ),
    (
        "Chunking strategies",
        "Fixed windows miss structure; sentence splits lose cross-sentence "
        "context. A good default is recursive splits on headings then "
        "paragraphs, with a small overlap. Measure recall, not vibes.",
        ["ml", "retrieval", "engineering"],
    ),
    (
        "Vector databases are just indexes",
        "Pinecone, Qdrant, pgvector — under the hood they're all ANN "
        "indexes (HNSW, IVF) with a thin API. For <10k vectors, a flat "
        "in-memory numpy scan beats them on latency and setup cost.",
        ["ml", "infra", "retrieval"],
    ),
    # --- product / knowledge-work cluster ---
    (
        "Second brain, not second inbox",
        "A knowledge system that only intakes but never resurfaces is a "
        "landfill. The unit of value is the re-encounter: seeing the right "
        "note at the moment you need it, without asking.",
        ["product", "pkm"],
    ),
    (
        "Zettelkasten in one sentence",
        "One idea per note, atomic and self-contained, with links — not "
        "folders — as the primary organizing structure. Luhmann's insight "
        "was that the index is the product.",
        ["pkm", "writing"],
    ),
    (
        "Against the folder",
        "Folders force a single hierarchy on knowledge that has many "
        "natural parents. Tags help. Links help more. Automatic links "
        "from semantic similarity help most.",
        ["pkm", "product"],
    ),
    (
        "Graph view as a UI, not a toy",
        "Most graph views are eye candy. A useful one answers questions: "
        "what's central, what's orphaned, what connects these two "
        "thoughts. Layout and filtering do the real work.",
        ["pkm", "design", "visualization"],
    ),
    (
        "Spaced repetition for ideas",
        "Anki works for facts; ideas need a different cadence. Resurface "
        "a note when a new note semantically neighbors it — the system "
        "interrupts you only when the context is alive.",
        ["pkm", "learning"],
    ),
    # --- engineering craft cluster ---
    (
        "Boring technology wins",
        "Every exotic dependency is a future migration. Postgres, SQLite, "
        "a plain HTTP API — the compounding returns of familiar tools "
        "beat the instant dopamine of a shiny framework.",
        ["engineering", "philosophy"],
    ),
    (
        "The test pyramid is overrated",
        "Fast integration tests against a real DB catch the bugs users "
        "actually hit. Unit tests catch bugs you wrote five minutes ago. "
        "Balance both; don't worship the shape.",
        ["engineering", "testing"],
    ),
    (
        "SQLite is underrated",
        "A single file, zero configuration, faster than you think for "
        "reads, perfectly fine for single-tenant writes. If your app "
        "fits on one machine, it probably fits in SQLite.",
        ["engineering", "infra"],
    ),
    (
        "Force-directed layouts",
        "Fruchterman-Reingold: attractive forces along edges, repulsive "
        "forces between all node pairs, cooling schedule. d3-force is "
        "the web's default; performance tanks past ~5k nodes without "
        "Barnes-Hut.",
        ["visualization", "algorithms"],
    ),
    # --- bridges (intentional cross-cluster notes) ---
    (
        "Why this app exists",
        "Every PKM tool either makes you link by hand (Obsidian) or hides "
        "the graph behind AI magic (Mem). SynapseOS splits the difference: "
        "automatic synapses from embeddings, but the graph is the product.",
        ["product", "pkm", "ml"],
    ),
    (
        "Design debt compounds faster than tech debt",
        "You can refactor a backend in an afternoon. You cannot refactor "
        "the shape of a feature your users have built workflows around. "
        "Decide the graph UI now.",
        ["engineering", "design", "product"],
    ),
    # --- tensions (intentional contradictions so the Tensions tab lights
    # up on first run — pair-mates already exist above) ---
    (
        "Unit tests are underrated",
        "Unit tests are fast, simple, and the right tool when you want "
        "feedback in milliseconds. They are essential and central to a "
        "healthy codebase — write more of them, not fewer.",
        ["engineering", "testing"],
    ),
    (
        "Why folders work",
        "Folders are simple and robust. They are durable, easy to grok, and "
        "have worked for decades. Tags get messy fast and are overrated "
        "for personal knowledge that fits in one hierarchy.",
        ["pkm", "product"],
    ),
    # --- echoes (deliberate near-duplicates so the Echo tab lights up
    # on first run; redundant restatements of the same idea are exactly
    # the PKM hygiene problem Echo exists to solve) ---
    (
        "Cosine similarity is the substrate",
        "Vector embeddings turn prose into coordinates and cosine similarity "
        "between those coordinates is a cheap proxy for semantic relatedness. "
        "Most second-brain tools are quietly running on this substrate. "
        "It's the foundation everything else builds on.",
        ["ml", "embeddings"],
    ),
    (
        "SQLite is enough",
        "A single file with zero configuration, much faster than people think "
        "for reads, and perfectly fine for single-tenant writes. If your "
        "application fits comfortably on one machine, it almost certainly "
        "fits in SQLite. The boring choice is the right one.",
        ["engineering", "infra", "boring"],
    ),
    (
        "Atomic notes, one idea each",
        "One idea per note, atomic and self-contained, with links instead of "
        "folders as the primary organizing structure. The index is the "
        "product — that was Luhmann's real insight, and Zettelkasten in a "
        "single sentence.",
        ["pkm", "writing"],
    ),
]


# --- Synthetic staggered timestamps so the Chronicle surface has a real
# story to tell on first run. Each note is placed on a deterministic
# offset (days before "today" at seed time) — clusters share a temporal
# arc (early/middle/late), and a couple of notes are deliberately moved
# late so the Chronicle clearly shows vocabulary that emerged later.
# Offset = days before now; lower numbers = more recent.
_TIMELINE_OFFSETS: dict[str, int] = {
    # ML / infra: ramp up across the window, with the late notes leaning
    # on RAG / chunking — "the framing visibly changed" pivots.
    "Embeddings as memory": 92,
    "Hashing trick for features": 88,
    "Vector databases are just indexes": 71,
    "Retrieval-augmented generation": 24,
    "Chunking strategies": 12,
    # Product / PKM: early on "second inbox", middle "atomic notes",
    # late "graph view as a UI".
    "Second brain, not second inbox": 84,
    "Zettelkasten in one sentence": 73,
    "Against the folder": 59,
    "Spaced repetition for ideas": 31,
    "Graph view as a UI, not a toy": 9,
    # Engineering craft: spread evenly.
    "Boring technology wins": 80,
    "The test pyramid is overrated": 64,
    "SQLite is underrated": 45,
    "Force-directed layouts": 18,
    # Bridges + tensions written later as the project matured.
    "Why this app exists": 39,
    "Design debt compounds faster than tech debt": 21,
    "Unit tests are underrated": 17,
    "Why folders work": 28,
    # Echoes deliberately written close to (but distinct from) their
    # originals so Echo + Chronicle disagree usefully.
    "Cosine similarity is the substrate": 6,
    "SQLite is enough": 14,
    "Atomic notes, one idea each": 4,
}


def _stagger_created_at() -> None:
    """Backdate each note's ``created_at`` per ``_TIMELINE_OFFSETS``.

    The bulk insert stamps everything with the same "now"; we rewrite
    each row's timestamp to a synthetic offset so Chronicle has a real
    temporal arc to chronicle. Notes not in the offset map get a stable
    fallback (60d ago) so the demo never crashes on a new seed entry the
    author forgot to wire into ``_TIMELINE_OFFSETS``.
    """
    from datetime import datetime, timedelta, timezone

    from backend.app.store import _conn  # noqa: WPS437 — internal helper, intentional reuse.

    now = datetime.now(timezone.utc).replace(microsecond=0)
    with _conn() as con:
        rows = con.execute("SELECT id, title FROM notes").fetchall()
        for row in rows:
            offset = _TIMELINE_OFFSETS.get(row["title"], 60)
            stamp = (now - timedelta(days=offset)).isoformat()
            con.execute(
                "UPDATE notes SET created_at = ? WHERE id = ?",
                (stamp, int(row["id"])),
            )


def main() -> None:
    store.init_db()
    if store.count() > 0:
        print(f"Seed skipped — {store.count()} notes already present.")
        return
    ids = store.bulk_add(SEED)
    _stagger_created_at()
    print(f"Seeded {len(ids)} notes (staggered across a ~90d synthetic window).")


if __name__ == "__main__":
    main()
