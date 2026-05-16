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
    POST /chat               -> graph-aware RAG: answer + citations + traversal
    GET  /chat/status        -> reports whether an LLM key is configured
    GET  /health             -> { ok: true, notes: N }

The point of the API is to be boring and obvious. The interesting behavior
lives in `synapse.py` and `community.py`.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware

from . import chat as chat_engine
from . import community, revisit, schemas, store, synapse, trails
from .embed import cosine
from .llm import llm_available, llm_provider_label

app = FastAPI(
    title="SynapseOS",
    version="0.2.0",
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


@app.get("/chat/status")
def chat_status() -> dict:
    """Lightweight probe so the frontend can label LLM mode honestly."""
    return {
        "llm_available": llm_available(),
        "llm_provider": llm_provider_label() if llm_available() else None,
        "extractive_available": True,
    }


@app.get("/brief", response_model=schemas.BriefOut)
def brief(
    k: int = Query(5, ge=1, le=12),
    date: str | None = Query(None, description="YYYY-MM-DD; defaults to today UTC"),
    threshold: float = Query(synapse.DEFAULT_THRESHOLD, ge=0.0, le=1.0),
    top_k: int = Query(synapse.DEFAULT_TOP_K, ge=1, le=20),
) -> dict:
    """Today's spaced-revisit picks + journal prompts + bridge suggestions.

    The brief is *idempotent within a day*: reloading the page returns
    the same picks. The day-key seeds a tiny per-note jitter so tie
    breaks differ across days without dragging the scoring physics into
    randomness.
    """
    if store.count() == 0:
        return {"date": revisit.today_key(), "k": k, "total_notes": 0, "picks": [], "stats": {}}

    now = datetime.now(timezone.utc)
    date_key = date or revisit.today_key(now)

    notes = store.all_notes()
    g = synapse.compute_graph(threshold=threshold, top_k=top_k)
    cmap = {n["id"]: n.get("community", 0) for n in g.nodes}
    notes_for_community = {n["id"]: n for n in g.nodes}
    built_communities = community.build_communities(cmap, notes_for_community)
    community_lookup = {
        c.id: {"name": c.name, "color": c.color, "terms": list(c.terms)}
        for c in built_communities
    }
    degrees = {n["id"]: int(n.get("degree", 0)) for n in g.nodes}
    weights = {n["id"]: float(n.get("weight", 0.0)) for n in g.nodes}

    # Orphans = nodes with zero degree at the current (threshold, top_k).
    orphans: set[int] = {nid for nid, d in degrees.items() if d == 0}

    embeddings = dict(store.all_embeddings())

    b = revisit.daily_brief(
        date=date_key,
        k=k,
        now=now,
        notes=notes,
        cmap=cmap,
        community_lookup=community_lookup,
        degrees=degrees,
        weights=weights,
        orphans=orphans,
        embeddings=embeddings,
        cosine_fn=cosine,
    )

    return {
        "date": b.date,
        "k": b.k,
        "total_notes": b.total_notes,
        "picks": [
            {
                "note_id": p.note_id,
                "title": p.title,
                "snippet": p.snippet,
                "tags": p.tags,
                "score": p.score,
                "reasons": [
                    {"kind": r.kind, "text": r.text, "weight": r.weight}
                    for r in p.reasons
                ],
                "prompt": p.prompt,
                "connections": [
                    {
                        "note_id": c.note_id,
                        "title": c.title,
                        "strength": c.strength,
                        "cluster_id": c.cluster_id,
                        "cluster_name": c.cluster_name,
                    }
                    for c in p.connections
                ],
                "cluster_id": p.cluster_id,
                "cluster_name": p.cluster_name,
                "cluster_color": p.cluster_color,
                "days_since_seen": p.days_since_seen,
                "is_orphan": p.is_orphan,
            }
            for p in b.picks
        ],
        "stats": b.stats,
    }


@app.post("/notes/{note_id}/touch")
def touch_note(note_id: int) -> dict:
    """Record that the user just re-engaged with this note.

    Idempotent — repeated taps just refresh the timestamp. Returns the
    new ``last_seen_at`` so the frontend can update local state without
    a round-trip back through ``/notes/{id}``.
    """
    if not store.touch_note(note_id):
        raise HTTPException(404, "note not found")
    n = store.get_note(note_id)
    assert n is not None
    return {"ok": True, "note_id": note_id, "last_seen_at": n.get("last_seen_at")}


# ------------------------------------------------------------ trails

def _step_dict(s: schemas.TrailStepIn) -> dict:
    return {"note_id": int(s.note_id), "caption": s.caption}


def _resolved_to_dict(r: trails.ResolvedTrail) -> dict:
    return {
        "id": r.id,
        "title": r.title,
        "description": r.description,
        "origin": r.origin,
        "created_at": r.created_at,
        "updated_at": r.updated_at,
        "threshold": r.threshold,
        "top_k": r.top_k,
        "health": r.health,
        "total_strength": r.total_strength,
        "missing_count": r.missing_count,
        "clusters_touched": r.clusters_touched,
        "steps": [
            {
                "note_id": s.note_id,
                "title": s.title,
                "snippet": s.snippet,
                "tags": s.tags,
                "caption": s.caption,
                "exists": s.exists,
                "cluster_id": s.cluster_id,
                "cluster_name": s.cluster_name,
                "cluster_color": s.cluster_color,
                "strength_to_next": s.strength_to_next,
                "is_synapse_to_next": s.is_synapse_to_next,
            }
            for s in r.steps
        ],
    }


def _validate_step_ids(steps: list[schemas.TrailStepIn]) -> None:
    if not steps:
        return
    note_ids = {int(s.note_id) for s in steps}
    existing = {n["id"] for n in store.all_notes()}
    missing = sorted(note_ids - existing)
    if missing:
        raise HTTPException(
            400, f"unknown note ids: {missing[:5]}{' ...' if len(missing) > 5 else ''}"
        )


@app.get("/trails", response_model=list[schemas.TrailSummaryOut])
def trails_list(
    threshold: float = Query(synapse.DEFAULT_THRESHOLD, ge=0.0, le=1.0),
    top_k: int = Query(synapse.DEFAULT_TOP_K, ge=1, le=20),
) -> list[dict]:
    """Cheap list view — title, step count, health badge, no bodies."""
    out: list[dict] = []
    for t in store.list_trails():
        s = trails.summarize(t, threshold=threshold, top_k=top_k)
        out.append(
            {
                "id": s.id,
                "title": s.title,
                "description": s.description,
                "origin": s.origin,
                "created_at": s.created_at,
                "updated_at": s.updated_at,
                "step_count": s.step_count,
                "health": s.health,
                "missing_count": s.missing_count,
            }
        )
    return out


@app.post("/trails", response_model=schemas.TrailOut, status_code=201)
def trails_create(
    req: schemas.TrailIn,
    threshold: float = Query(synapse.DEFAULT_THRESHOLD, ge=0.0, le=1.0),
    top_k: int = Query(synapse.DEFAULT_TOP_K, ge=1, le=20),
) -> dict:
    _validate_step_ids(req.steps)
    tid = store.add_trail(
        title=req.title,
        description=req.description,
        steps=[_step_dict(s) for s in req.steps],
        origin=req.origin,
    )
    t = store.get_trail(tid)
    assert t is not None
    return _resolved_to_dict(trails.resolve(t, threshold=threshold, top_k=top_k))


@app.get("/trails/{trail_id}", response_model=schemas.TrailOut)
def trails_get(
    trail_id: int,
    threshold: float = Query(synapse.DEFAULT_THRESHOLD, ge=0.0, le=1.0),
    top_k: int = Query(synapse.DEFAULT_TOP_K, ge=1, le=20),
) -> dict:
    t = store.get_trail(trail_id)
    if not t:
        raise HTTPException(404, "trail not found")
    return _resolved_to_dict(trails.resolve(t, threshold=threshold, top_k=top_k))


@app.patch("/trails/{trail_id}", response_model=schemas.TrailOut)
def trails_patch(
    trail_id: int,
    req: schemas.TrailPatch,
    threshold: float = Query(synapse.DEFAULT_THRESHOLD, ge=0.0, le=1.0),
    top_k: int = Query(synapse.DEFAULT_TOP_K, ge=1, le=20),
) -> dict:
    if req.steps is not None:
        _validate_step_ids(req.steps)
    ok = store.update_trail(
        trail_id,
        title=req.title,
        description=req.description,
        steps=[_step_dict(s) for s in req.steps] if req.steps is not None else None,
    )
    if not ok:
        raise HTTPException(404, "trail not found")
    t = store.get_trail(trail_id)
    assert t is not None
    return _resolved_to_dict(trails.resolve(t, threshold=threshold, top_k=top_k))


@app.post("/trails/{trail_id}/append", response_model=schemas.TrailOut)
def trails_append(
    trail_id: int,
    req: schemas.TrailAppend,
    threshold: float = Query(synapse.DEFAULT_THRESHOLD, ge=0.0, le=1.0),
    top_k: int = Query(synapse.DEFAULT_TOP_K, ge=1, le=20),
) -> dict:
    if store.get_note(req.note_id) is None:
        raise HTTPException(400, f"unknown note id: {req.note_id}")
    if not store.append_trail_step(trail_id, req.note_id, req.caption):
        raise HTTPException(404, "trail not found")
    t = store.get_trail(trail_id)
    assert t is not None
    return _resolved_to_dict(trails.resolve(t, threshold=threshold, top_k=top_k))


@app.delete("/trails/{trail_id}")
def trails_delete(trail_id: int) -> Response:
    if not store.delete_trail(trail_id):
        raise HTTPException(404, "trail not found")
    return Response(status_code=204)


@app.get("/trails/{trail_id}/suggest_next", response_model=schemas.TrailSuggestionsOut)
def trails_suggest(
    trail_id: int,
    k: int = Query(5, ge=1, le=12),
    threshold: float = Query(synapse.DEFAULT_THRESHOLD, ge=0.0, le=1.0),
    top_k: int = Query(synapse.DEFAULT_TOP_K, ge=1, le=20),
) -> dict:
    t = store.get_trail(trail_id)
    if not t:
        raise HTTPException(404, "trail not found")
    sugs = trails.suggest_next(t, k=k, threshold=threshold, top_k=top_k)
    return {
        "trail_id": trail_id,
        "threshold": threshold,
        "suggestions": [
            {
                "note_id": s.note_id,
                "title": s.title,
                "snippet": s.snippet,
                "tags": s.tags,
                "strength": s.strength,
                "cluster_id": s.cluster_id,
                "cluster_name": s.cluster_name,
                "cluster_color": s.cluster_color,
            }
            for s in sugs
        ],
    }


@app.get("/trails/{trail_id}/export.md")
def trails_export(
    trail_id: int,
    threshold: float = Query(synapse.DEFAULT_THRESHOLD, ge=0.0, le=1.0),
    top_k: int = Query(synapse.DEFAULT_TOP_K, ge=1, le=20),
) -> Response:
    t = store.get_trail(trail_id)
    if not t:
        raise HTTPException(404, "trail not found")
    resolved = trails.resolve(t, threshold=threshold, top_k=top_k)
    md = trails.to_markdown(resolved)
    safe_title = "".join(c if c.isalnum() else "-" for c in resolved.title).strip("-").lower() or "trail"
    return Response(
        content=md,
        media_type="text/markdown; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{safe_title}.md"'
        },
    )


@app.post("/chat", response_model=schemas.ChatOut)
def chat(req: schemas.ChatRequest) -> dict:
    """Graph-aware RAG over the synapse graph.

    The retriever seeds with semantic search, expands one hop along the
    same synapses the canvas renders, and (optionally) tacks on a
    high-weight anchor from each seed's community. Default ``mode=auto``
    uses an LLM if ``SYNAPSE_LLM_KEY`` is set, else extractive.
    """
    if store.count() == 0:
        raise HTTPException(400, "no notes yet — add a few before asking")
    result = chat_engine.answer(
        query=req.query,
        mode=req.mode,
        k_seed=req.k_seed,
        hops=req.hops,
        threshold=req.threshold,
        top_k=req.top_k,
        include_community_anchors=req.include_community_anchors,
    )
    return chat_engine.serialize(result)
