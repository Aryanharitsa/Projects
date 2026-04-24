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
]


def main() -> None:
    store.init_db()
    if store.count() > 0:
        print(f"Seed skipped — {store.count()} notes already present.")
        return
    ids = store.bulk_add(SEED)
    print(f"Seeded {len(ids)} notes.")


if __name__ == "__main__":
    main()
