"""Synapse formation + graph queries.

Given the current set of notes, we compute a *synapse graph* on the fly:

    edge(u, v) exists   iff   cosine(emb(u), emb(v)) >= THRESHOLD
                               AND v is in u's top-K nearest neighbors

The top-K cap prevents one "hub" note from pulling in dozens of weak edges
and gives the force-directed layout something tractable to render. The
threshold keeps low-signal pairs off the board entirely.

Node weight is degree-normalized PageRank-flavored: it's the sum of
incoming edge strengths, normalized to [0, 1]. That maps naturally to a
"how central is this thought?" visual cue in the frontend.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from heapq import heappop, heappush

from . import community, store
from .embed import cosine, embed

# Defaults chosen to look good on the seed graph; `/graph` accepts
# overrides so you can tune live.
DEFAULT_THRESHOLD = 0.14
DEFAULT_TOP_K = 5


@dataclass
class ComputedGraph:
    nodes: list[dict]
    edges: list[dict]
    stats: dict[str, float]


def _neighbors_of(
    embeddings: list[tuple[int, tuple[float, ...]]],
    threshold: float,
    top_k: int,
) -> dict[int, list[tuple[int, float]]]:
    """For each note id, return [(neighbor_id, similarity)] sorted desc."""
    by_id = dict(embeddings)
    ids = list(by_id.keys())
    out: dict[int, list[tuple[int, float]]] = {}
    for i in ids:
        sims: list[tuple[int, float]] = []
        vi = by_id[i]
        for j in ids:
            if j == i:
                continue
            s = cosine(vi, by_id[j])
            if s >= threshold:
                sims.append((j, s))
        sims.sort(key=lambda x: x[1], reverse=True)
        out[i] = sims[:top_k]
    return out


def compute_graph(
    threshold: float = DEFAULT_THRESHOLD,
    top_k: int = DEFAULT_TOP_K,
) -> ComputedGraph:
    notes = store.all_notes()
    if not notes:
        return ComputedGraph(
            nodes=[],
            edges=[],
            stats={"nodes": 0, "edges": 0, "avg_degree": 0.0, "communities": 0},
        )

    embeddings = store.all_embeddings()
    neighbors = _neighbors_of(embeddings, threshold, top_k)

    # Deduplicate undirected edges. Keep the stronger side.
    undirected: dict[tuple[int, int], float] = {}
    for u, nbrs in neighbors.items():
        for v, s in nbrs:
            key = (u, v) if u < v else (v, u)
            if s > undirected.get(key, 0.0):
                undirected[key] = s

    degree: dict[int, int] = defaultdict(int)
    pull: dict[int, float] = defaultdict(float)
    for (u, v), s in undirected.items():
        degree[u] += 1
        degree[v] += 1
        pull[u] += s
        pull[v] += s

    max_pull = max(pull.values()) if pull else 1.0
    max_pull = max_pull or 1.0

    # Community detection runs over the materialized undirected edges.
    node_ids = [n["id"] for n in notes]
    raw_edges = [(u, v, s) for (u, v), s in undirected.items()]
    cmap = community.detect_communities(node_ids, raw_edges)

    nodes_out = []
    for n in notes:
        nid = n["id"]
        cid = cmap.get(nid, 0)
        nodes_out.append(
            {
                "id": nid,
                "title": n["title"],
                "body": n["body"],
                "tags": n["tags"],
                "degree": degree.get(nid, 0),
                "weight": round(pull.get(nid, 0.0) / max_pull, 4),
                "community": cid,
                "community_color": community.color_for(cid),
            }
        )

    edges_out = [
        {"source": u, "target": v, "strength": round(s, 4), "kind": "synapse"}
        for (u, v), s in sorted(undirected.items(), key=lambda kv: kv[1], reverse=True)
    ]

    avg_degree = (2 * len(edges_out) / len(nodes_out)) if nodes_out else 0.0
    n_communities = len(set(cmap.values())) if cmap else 0
    stats = {
        "nodes": len(nodes_out),
        "edges": len(edges_out),
        "avg_degree": round(avg_degree, 2),
        "threshold": threshold,
        "top_k": top_k,
        "communities": n_communities,
    }
    return ComputedGraph(nodes=nodes_out, edges=edges_out, stats=stats)


def neighbors_of_note(
    note_id: int,
    threshold: float = DEFAULT_THRESHOLD,
    top_k: int = DEFAULT_TOP_K,
) -> list[dict]:
    """Return neighbors of a single note with their similarity scores."""
    notes = {n["id"]: n for n in store.all_notes()}
    if note_id not in notes:
        return []
    embeddings = dict(store.all_embeddings())
    vi = embeddings[note_id]

    sims = []
    for j, vj in embeddings.items():
        if j == note_id:
            continue
        s = cosine(vi, vj)
        if s >= threshold:
            sims.append((j, s))
    sims.sort(key=lambda x: x[1], reverse=True)

    out = []
    for nid, s in sims[:top_k]:
        n = notes[nid]
        out.append(
            {
                "node": {
                    "id": n["id"],
                    "title": n["title"],
                    "body": n["body"],
                    "tags": n["tags"],
                    "degree": 0,
                    "weight": 0.0,
                },
                "strength": round(s, 4),
            }
        )
    return out


def search(query: str, limit: int = 8) -> list[dict]:
    """Rank all notes by cosine similarity to the query string."""
    if not query.strip():
        return []
    qv = embed(query)
    notes = {n["id"]: n for n in store.all_notes()}
    embeddings = store.all_embeddings()
    scored = []
    for nid, v in embeddings:
        s = cosine(qv, v)
        if s <= 0:
            continue
        n = notes[nid]
        scored.append(
            {
                "node": {
                    "id": n["id"],
                    "title": n["title"],
                    "body": n["body"],
                    "tags": n["tags"],
                    "degree": 0,
                    "weight": 0.0,
                },
                "score": round(s, 4),
            }
        )
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:limit]


def shortest_path(
    src_id: int,
    dst_id: int,
    threshold: float = DEFAULT_THRESHOLD,
    top_k: int = DEFAULT_TOP_K,
) -> dict:
    """Dijkstra on the synapse graph with weight = (1 - strength).

    Returns a path from `src_id` to `dst_id` along the strongest chain of
    synapses. Useful for "how is X related to Y?" questions.
    """
    notes = {n["id"]: n for n in store.all_notes()}
    if src_id not in notes or dst_id not in notes:
        return {"found": False, "path": [], "cost": 0.0}

    graph = compute_graph(threshold=threshold, top_k=top_k)
    adj: dict[int, list[tuple[int, float]]] = defaultdict(list)
    for e in graph.edges:
        adj[e["source"]].append((e["target"], e["strength"]))
        adj[e["target"]].append((e["source"], e["strength"]))

    dist: dict[int, float] = {src_id: 0.0}
    prev: dict[int, tuple[int, float]] = {}
    pq: list[tuple[float, int]] = [(0.0, src_id)]
    visited: set[int] = set()

    while pq:
        d, u = heappop(pq)
        if u in visited:
            continue
        visited.add(u)
        if u == dst_id:
            break
        for v, s in adj[u]:
            if v in visited:
                continue
            nd = d + (1.0 - s)
            if nd < dist.get(v, float("inf")):
                dist[v] = nd
                prev[v] = (u, s)
                heappush(pq, (nd, v))

    if dst_id not in dist:
        return {"found": False, "path": [], "cost": 0.0}

    # Reconstruct path: for each node, record the strength of the edge
    # that led INTO it from its predecessor. The src node carries 0.0.
    chain: list[tuple[int, float]] = []
    cur = dst_id
    while cur in prev:
        p, s = prev[cur]
        chain.append((cur, s))
        cur = p
    chain.append((cur, 0.0))  # src
    chain.reverse()

    path_steps = []
    for nid, s in chain:
        n = notes[nid]
        path_steps.append(
            {
                "node": {
                    "id": n["id"],
                    "title": n["title"],
                    "body": n["body"],
                    "tags": n["tags"],
                    "degree": 0,
                    "weight": 0.0,
                },
                "strength": round(s, 4),
            }
        )
    return {"found": True, "path": path_steps, "cost": round(dist[dst_id], 4)}
