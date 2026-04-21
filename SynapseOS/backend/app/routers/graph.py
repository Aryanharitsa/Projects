from collections import defaultdict

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Note, Synapse
from app.schemas import GraphEdge, GraphNode, GraphOut

router = APIRouter(prefix="/graph", tags=["graph"])


@router.get("", response_model=GraphOut)
def get_graph(db: Session = Depends(get_db)):
    """Return the full synapse graph in a frontend-friendly shape."""
    notes = db.query(Note).all()
    edges = db.query(Synapse).all()

    degree = defaultdict(int)
    for e in edges:
        degree[e.source_id] += 1
        degree[e.target_id] += 1

    nodes = [
        GraphNode(
            id=n.id,
            title=n.title,
            tags=[t for t in n.tags.split() if t],
            size=degree.get(n.id, 0),
            created_at=n.created_at,
        )
        for n in notes
    ]

    graph_edges = [
        GraphEdge(source=e.source_id, target=e.target_id, strength=e.strength)
        for e in edges
    ]

    avg_degree = (2 * len(graph_edges) / len(nodes)) if nodes else 0.0
    avg_strength = (
        sum(e.strength for e in graph_edges) / len(graph_edges)
        if graph_edges else 0.0
    )

    stats = {
        "node_count": len(nodes),
        "edge_count": len(graph_edges),
        "avg_degree": round(avg_degree, 2),
        "avg_strength": round(avg_strength, 3),
        "max_degree": max((n.size for n in nodes), default=0),
    }

    return GraphOut(nodes=nodes, edges=graph_edges, stats=stats)
