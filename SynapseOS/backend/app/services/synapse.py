"""Rebuild the synapse graph from all notes. Cheap on small/medium corpora
(the full recompute is O(N²) cosine). If the corpus grows large we can swap
in an ANN index, but that's an exercise for another day."""

from sqlalchemy.orm import Session

from app.models import Note, Synapse
from app.services.embedding import pairwise_similarities


def rebuild_synapses(db: Session, *, min_strength: float = 0.08,
                     top_k: int | None = 6) -> int:
    """Wipe & recompute all synapse edges. Returns edge count."""
    notes = db.query(Note).all()
    documents = [
        (n.id, f"{n.title}\n{n.tags}\n{n.body}")
        for n in notes
    ]

    edges = pairwise_similarities(documents,
                                  min_strength=min_strength, top_k=top_k)

    db.query(Synapse).delete()
    for src, tgt, strength in edges:
        db.add(Synapse(source_id=src, target_id=tgt, strength=strength))
    db.commit()
    return len(edges)
