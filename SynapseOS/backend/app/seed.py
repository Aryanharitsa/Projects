"""Seed the database with example notes so the graph is populated on
first run. Idempotent — skips seeding if any notes already exist."""

from app.db import SessionLocal, Base, engine
from app.models import Note
from app.services.synapse import rebuild_synapses

SEED_NOTES = [
    {
        "title": "Attention is permutation-equivariant",
        "tags": "ml transformer math",
        "body": (
            "Self-attention treats the sequence as a set; positional "
            "information has to be injected separately. This is why "
            "positional encodings or rotary embeddings matter — without "
            "them, a transformer literally cannot tell the order of tokens."
        ),
    },
    {
        "title": "Rotary positional embeddings",
        "tags": "ml transformer math",
        "body": (
            "RoPE rotates query/key pairs in a 2D plane as a function of "
            "position. The dot product of rotated q·k depends only on the "
            "relative offset, which is why RoPE generalises to longer "
            "contexts than learned absolute encodings."
        ),
    },
    {
        "title": "SQLite is a library, not a server",
        "tags": "databases sqlite engineering",
        "body": (
            "Embedded means the DB runs inside your process. No network "
            "hop, no authentication dance. For a single-tenant personal "
            "tool like SynapseOS, SQLite outperforms Postgres on both "
            "latency and operational cost."
        ),
    },
    {
        "title": "TF-IDF still slaps for short documents",
        "tags": "nlp retrieval search",
        "body": (
            "For personal notes (a few paragraphs each), a well-tuned "
            "TF-IDF vectoriser often beats off-the-shelf sentence "
            "embeddings on topical similarity. Embeddings pull in "
            "tonal/stylistic noise that isn't what you want here."
        ),
    },
    {
        "title": "Cosine similarity as an inner product",
        "tags": "math retrieval nlp",
        "body": (
            "Cosine similarity between L2-normalised vectors is just the "
            "dot product. That's why approximate nearest-neighbour "
            "indexes (FAISS, hnswlib) can use inner-product search under "
            "the hood when the vectors are pre-normalised."
        ),
    },
    {
        "title": "Zettelkasten beats folders",
        "tags": "pkm notes zettelkasten",
        "body": (
            "Folders force a single hierarchy onto ideas that don't have "
            "one. A Zettelkasten lets every note live in many contexts at "
            "once via links. SynapseOS extends this by auto-linking notes "
            "the moment they share enough vocabulary."
        ),
    },
    {
        "title": "Graph views are a discovery tool, not decoration",
        "tags": "pkm viz graph",
        "body": (
            "A well-designed knowledge graph surfaces the weak ties — "
            "notes you didn't realise were related. That's where new "
            "ideas come from: joining two islands that already existed in "
            "your head but weren't explicitly connected."
        ),
    },
    {
        "title": "Force-directed layout in one paragraph",
        "tags": "graph viz d3 math",
        "body": (
            "Each node repels every other node (Coulomb). Each edge pulls "
            "its endpoints together (Hooke). Add a mild gravity to the "
            "center and the system converges to a layout where strongly "
            "connected clusters sit close and weakly connected ones drift."
        ),
    },
    {
        "title": "FastAPI's dependency injection is quietly great",
        "tags": "python fastapi web engineering",
        "body": (
            "`Depends(get_db)` composes like a monad. You can stack auth, "
            "db, tenant resolution, and feature-flag reads without turning "
            "routes into a middleware tangle. It's the best argument for "
            "FastAPI over Flask on new projects."
        ),
    },
    {
        "title": "A good personal tool has zero onboarding",
        "tags": "product design engineering",
        "body": (
            "If the tool needs an API key to show you something useful, "
            "you've already lost most people. SynapseOS ships with seeded "
            "notes and a zero-dep embedder so the first-run graph is "
            "already beautiful."
        ),
    },
]


def seed() -> dict:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        existing = db.query(Note).count()
        if existing:
            return {"skipped": True, "existing": existing}

        for n in SEED_NOTES:
            db.add(Note(title=n["title"], body=n["body"], tags=n["tags"]))
        db.commit()

        edge_count = rebuild_synapses(db)
        return {"skipped": False, "notes": len(SEED_NOTES), "edges": edge_count}
    finally:
        db.close()


if __name__ == "__main__":
    print(seed())
