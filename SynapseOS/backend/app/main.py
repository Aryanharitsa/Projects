"""SynapseOS HTTP API.

Minimal FastAPI surface:

    POST /notes              -> create, returns NoteOut
    GET  /notes              -> list all
    GET  /notes/{id}         -> single
    DELETE /notes/{id}       -> remove
    GET  /graph              -> full synapse graph { nodes, edges, stats }
    GET  /neighbors/{id}     -> adjacent notes + similarity
    GET  /search?q=...       -> cosine ranking against all notes
    GET  /path?src=&dst=     -> strongest-chain path between two notes
    GET  /communities        -> labeled clusters with auto-derived names
    GET  /orphans            -> isolated notes + best-candidate rescues
    GET  /health             -> { ok: true, notes: N }

The point of the API is to be boring and obvious. The interesting behavior
lives in `synapse.py` and `community.py`.
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware

from . import community, schemas, store, synapse
from .embed import cosine

app = FastAPI(
    title="SynapseOS",
    version="0.1.0",
    description=(
        "Second-brain OS. Notes auto-link via embedding-based synapses; "
        "query and traverse the graph through a small, honest API."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup() -> None:
    store.init_db()


@app.get("/health")
def health() -> dict:
    return {"ok": True, "notes": store.count()}


@app.post("/notes", response_model=schemas.NoteOut, status_code=201)
def create_note(note: schemas.NoteIn) -> dict:
    nid = store.add_note(note.title, note.body, note.tags)
    created = store.get_note(nid)
    assert created is not None
    return created


@app.get("/notes", response_model=list[schemas.NoteOut])
def list_notes() -> list[dict]:
    return store.all_notes()


@app.get("/notes/{note_id}", response_model=schemas.NoteOut)
def get_note(note_id: int) -> dict:
    n = store.get_note(note_id)
    if not n:
        raise HTTPException(404, "note not found")
    return n


@app.delete("/notes/{note_id}")
def delete_note(note_id: int) -> Response:
    if not store.delete_note(note_id):
        raise HTTPException(404, "note not found")
    return Response(status_code=204)


@app.get("/graph", response_model=schemas.Graph)
def graph(
    threshold: float = Query(synapse.DEFAULT_THRESHOLD, ge=0.0, le=1.0),
    top_k: int = Query(synapse.DEFAULT_TOP_K, ge=1, le=20),
) -> dict:
    g = synapse.compute_graph(threshold=threshold, top_k=top_k)
    return {"nodes": g.nodes, "edges": g.edges, "stats": g.stats}


@app.get("/neighbors/{note_id}", response_model=list[schemas.Neighbor])
def neighbors(
    note_id: int,
    threshold: float = Query(synapse.DEFAULT_THRESHOLD, ge=0.0, le=1.0),
    top_k: int = Query(synapse.DEFAULT_TOP_K, ge=1, le=20),
) -> list[dict]:
    if store.get_note(note_id) is None:
        raise HTTPException(404, "note not found")
    return synapse.neighbors_of_note(note_id, threshold=threshold, top_k=top_k)


@app.get("/search", response_model=list[schemas.SearchHit])
def search(q: str = Query(..., min_length=1), limit: int = Query(8, ge=1, le=50)) -> list[dict]:
    return synapse.search(q, limit=limit)


@app.get("/path", response_model=schemas.PathResult)
def path(
    src: int = Query(..., ge=1),
    dst: int = Query(..., ge=1),
    threshold: float = Query(synapse.DEFAULT_THRESHOLD, ge=0.0, le=1.0),
    top_k: int = Query(synapse.DEFAULT_TOP_K, ge=1, le=20),
) -> dict:
    return synapse.shortest_path(src, dst, threshold=threshold, top_k=top_k)


@app.get("/communities", response_model=list[schemas.CommunityOut])
def communities(
    threshold: float = Query(synapse.DEFAULT_THRESHOLD, ge=0.0, le=1.0),
    top_k: int = Query(synapse.DEFAULT_TOP_K, ge=1, le=20),
) -> list[dict]:
    """Auto-derived clusters with names and key terms.

    The clustering reuses whatever ``/graph`` would have computed at the
    same ``(threshold, top_k)`` so the frontend's palette stays in sync
    with the rendered graph.
    """
    g = synapse.compute_graph(threshold=threshold, top_k=top_k)
    cmap = {n["id"]: n.get("community", 0) for n in g.nodes}
    notes_by_id = {n["id"]: n for n in g.nodes}
    built = community.build_communities(cmap, notes_by_id)
    return [
        {
            "id": c.id,
            "name": c.name,
            "color": c.color,
            "size": c.size,
            "terms": c.terms,
            "member_ids": c.member_ids,
        }
        for c in built
    ]


@app.get("/orphans", response_model=list[schemas.OrphanOut])
def orphans(
    threshold: float = Query(synapse.DEFAULT_THRESHOLD, ge=0.0, le=1.0),
    top_k: int = Query(synapse.DEFAULT_TOP_K, ge=1, le=20),
) -> list[dict]:
    """Notes with no synapses + their best below-threshold candidate.

    Returned order: strongest near-miss first, so the user can rescue
    the easiest cases with a tiny ``τ`` nudge.
    """
    g = synapse.compute_graph(threshold=threshold, top_k=top_k)
    notes_by_id = {n["id"]: n for n in g.nodes}
    embeddings = dict(store.all_embeddings())
    raw_edges = [(e["source"], e["target"], e["strength"]) for e in g.edges]
    suggestions = community.find_orphans(
        node_ids=list(notes_by_id.keys()),
        edges=raw_edges,
        notes_by_id=notes_by_id,
        embeddings=embeddings,
        cosine_fn=cosine,
        current_threshold=threshold,
    )
    return [
        {
            "note_id": s.note_id,
            "title": s.title,
            "suggested_id": s.suggested_id,
            "suggested_title": s.suggested_title,
            "suggested_strength": s.suggested_strength,
            "suggested_threshold": s.suggested_threshold,
        }
        for s in suggestions
    ]
