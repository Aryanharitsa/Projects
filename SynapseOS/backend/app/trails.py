"""Trails — curated, replayable walks through the synapse graph.

A *trail* is an ordered list of `(note_id, caption)` steps. It's the
user explicitly showing their thinking: "here's how I walked from this
idea to that one, and what changed in my head along the way." The
graph view becomes a film strip — and trails are exportable as
Markdown, so a walk you took on Tuesday can become a public artifact
on Thursday.

This module is the read-side. ``store.py`` handles persistence; the
endpoints in ``main.py`` wire the two together. The interesting
behavior lives here:

- ``resolve``       — hydrate stored steps with live note title/snippet,
                       cluster info, and the strength of the synapse
                       (if any) that connects each step to the next.
- ``health_score``  — fraction of consecutive steps with a real synapse
                       at the current threshold. A "healthy" trail
                       walks along edges the graph would have drawn
                       anyway; a "leaping" trail jumps across gaps,
                       which is interesting in its own right.
- ``suggest_next``  — given a partial trail, return the best
                       not-yet-visited synapse neighbors of the tail
                       (with their strengths and titles) so the
                       builder UI can offer one-click extensions.
- ``to_markdown``   — pretty-printer for export.

No new persistence concepts here: trails are derived data over the
existing note + synapse substrate.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import community as community_mod
from . import store, synapse
from .embed import cosine


@dataclass
class ResolvedStep:
    note_id: int
    title: str
    snippet: str
    tags: list[str]
    caption: str
    exists: bool                # False if the note was deleted under the trail
    cluster_id: int | None
    cluster_name: str | None
    cluster_color: str | None
    strength_to_next: float | None  # cosine to next step, or None if last
    is_synapse_to_next: bool        # True iff strength_to_next >= threshold


@dataclass
class ResolvedTrail:
    id: int
    title: str
    description: str
    origin: str
    created_at: str
    updated_at: str
    steps: list[ResolvedStep]
    threshold: float
    top_k: int
    health: float                 # 0..1 — fraction of hops that ride a synapse
    total_strength: float         # sum of strength_to_next, ignoring None
    missing_count: int            # steps whose note was deleted
    clusters_touched: list[int]   # ordered, deduped


@dataclass
class TrailSummary:
    id: int
    title: str
    description: str
    origin: str
    created_at: str
    updated_at: str
    step_count: int
    health: float
    missing_count: int


@dataclass
class NextSuggestion:
    note_id: int
    title: str
    snippet: str
    tags: list[str]
    strength: float           # cosine to the tail of the trail
    cluster_id: int | None
    cluster_name: str | None
    cluster_color: str | None


# ----------------------------------------------------------------- helpers

def _snippet(body: str, limit: int = 220) -> str:
    body = (body or "").strip().replace("\n", " ")
    if len(body) <= limit:
        return body
    cut = body[:limit].rsplit(" ", 1)[0]
    return cut + "…"


def _cluster_view(
    threshold: float, top_k: int
) -> tuple[dict[int, int], dict[int, dict]]:
    """Compute `(node_id -> cluster_id, cluster_id -> {name,color})`.

    Returned shapes mirror what ``revisit.daily_brief`` consumes so we
    don't drift two different cluster lookups apart.
    """
    g = synapse.compute_graph(threshold=threshold, top_k=top_k)
    cmap = {n["id"]: int(n.get("community", 0) or 0) for n in g.nodes}
    notes_by_id = {n["id"]: n for n in g.nodes}
    built = community_mod.build_communities(cmap, notes_by_id)
    lookup: dict[int, dict] = {
        c.id: {"name": c.name, "color": c.color} for c in built
    }
    return cmap, lookup


# ----------------------------------------------------------------- public

def resolve(
    trail: dict,
    *,
    threshold: float = synapse.DEFAULT_THRESHOLD,
    top_k: int = synapse.DEFAULT_TOP_K,
) -> ResolvedTrail:
    """Hydrate a stored trail into a render-ready payload."""
    notes_by_id = {n["id"]: n for n in store.all_notes()}
    embeddings = dict(store.all_embeddings())
    cmap, cluster_lookup = _cluster_view(threshold, top_k)

    raw_steps: list[dict] = trail.get("steps", [])
    resolved: list[ResolvedStep] = []
    clusters_touched: list[int] = []
    seen_clusters: set[int] = set()

    for i, s in enumerate(raw_steps):
        nid = int(s["note_id"])
        caption = (s.get("caption") or "").strip()
        n = notes_by_id.get(nid)
        # Lookahead to compute strength_to_next eagerly.
        strength_to_next: float | None = None
        is_synapse_to_next = False
        if i + 1 < len(raw_steps):
            next_id = int(raw_steps[i + 1]["note_id"])
            va = embeddings.get(nid)
            vb = embeddings.get(next_id)
            if va is not None and vb is not None:
                strength_to_next = round(float(cosine(va, vb)), 4)
                is_synapse_to_next = strength_to_next >= threshold

        if n is None:
            resolved.append(
                ResolvedStep(
                    note_id=nid,
                    title="(deleted note)",
                    snippet="",
                    tags=[],
                    caption=caption,
                    exists=False,
                    cluster_id=None,
                    cluster_name=None,
                    cluster_color=None,
                    strength_to_next=strength_to_next,
                    is_synapse_to_next=is_synapse_to_next,
                )
            )
            continue

        cid = cmap.get(nid)
        cinfo = cluster_lookup.get(cid) if cid is not None else None
        if cid is not None and cid not in seen_clusters:
            clusters_touched.append(cid)
            seen_clusters.add(cid)

        resolved.append(
            ResolvedStep(
                note_id=nid,
                title=n["title"],
                snippet=_snippet(n["body"]),
                tags=list(n.get("tags") or []),
                caption=caption,
                exists=True,
                cluster_id=cid,
                cluster_name=(cinfo or {}).get("name"),
                cluster_color=(cinfo or {}).get("color"),
                strength_to_next=strength_to_next,
                is_synapse_to_next=is_synapse_to_next,
            )
        )

    hops = len(resolved) - 1
    synapse_hops = sum(1 for r in resolved[:-1] if r.is_synapse_to_next)
    health = (synapse_hops / hops) if hops > 0 else 1.0
    total_strength = round(
        sum(r.strength_to_next or 0.0 for r in resolved[:-1]), 4
    )
    missing = sum(1 for r in resolved if not r.exists)

    return ResolvedTrail(
        id=int(trail["id"]),
        title=trail.get("title") or "Untitled trail",
        description=trail.get("description") or "",
        origin=trail.get("origin") or "manual",
        created_at=trail.get("created_at") or "",
        updated_at=trail.get("updated_at") or "",
        steps=resolved,
        threshold=threshold,
        top_k=top_k,
        health=round(health, 4),
        total_strength=total_strength,
        missing_count=missing,
        clusters_touched=clusters_touched,
    )


def summarize(
    trail: dict,
    *,
    threshold: float = synapse.DEFAULT_THRESHOLD,
    top_k: int = synapse.DEFAULT_TOP_K,
) -> TrailSummary:
    """Cheap, list-view summary — avoids returning every step's body."""
    raw_steps: list[dict] = trail.get("steps", [])
    if not raw_steps:
        return TrailSummary(
            id=int(trail["id"]),
            title=trail.get("title") or "Untitled trail",
            description=trail.get("description") or "",
            origin=trail.get("origin") or "manual",
            created_at=trail.get("created_at") or "",
            updated_at=trail.get("updated_at") or "",
            step_count=0,
            health=1.0,
            missing_count=0,
        )

    embeddings = dict(store.all_embeddings())
    notes_by_id = {n["id"]: n for n in store.all_notes()}
    hops = len(raw_steps) - 1
    synapse_hops = 0
    missing = sum(1 for s in raw_steps if int(s["note_id"]) not in notes_by_id)
    for a, b in zip(raw_steps, raw_steps[1:]):
        va = embeddings.get(int(a["note_id"]))
        vb = embeddings.get(int(b["note_id"]))
        if va is None or vb is None:
            continue
        if cosine(va, vb) >= threshold:
            synapse_hops += 1
    health = (synapse_hops / hops) if hops > 0 else 1.0
    return TrailSummary(
        id=int(trail["id"]),
        title=trail.get("title") or "Untitled trail",
        description=trail.get("description") or "",
        origin=trail.get("origin") or "manual",
        created_at=trail.get("created_at") or "",
        updated_at=trail.get("updated_at") or "",
        step_count=len(raw_steps),
        health=round(health, 4),
        missing_count=missing,
    )


def suggest_next(
    trail: dict,
    *,
    k: int = 5,
    threshold: float = synapse.DEFAULT_THRESHOLD,
    top_k: int = synapse.DEFAULT_TOP_K,
) -> list[NextSuggestion]:
    """Best synapse neighbors of the tail that aren't already on the trail.

    Falls back to the *strongest* below-threshold candidates when no
    synapse neighbors remain, so the builder never shows an empty
    "what's next" panel as long as the graph has other notes.
    """
    raw_steps: list[dict] = trail.get("steps", [])
    if not raw_steps:
        # Empty trail — surface the highest-weight (most central) notes
        # as starting points instead of nothing.
        g = synapse.compute_graph(threshold=threshold, top_k=top_k)
        if not g.nodes:
            return []
        nodes_sorted = sorted(g.nodes, key=lambda n: n.get("weight", 0.0), reverse=True)
        cmap, cluster_lookup = _cluster_view(threshold, top_k)
        out: list[NextSuggestion] = []
        for n in nodes_sorted[:k]:
            cid = cmap.get(n["id"])
            cinfo = cluster_lookup.get(cid) if cid is not None else None
            out.append(
                NextSuggestion(
                    note_id=n["id"],
                    title=n["title"],
                    snippet=_snippet(n["body"]),
                    tags=list(n.get("tags") or []),
                    strength=0.0,
                    cluster_id=cid,
                    cluster_name=(cinfo or {}).get("name"),
                    cluster_color=(cinfo or {}).get("color"),
                )
            )
        return out

    tail_id = int(raw_steps[-1]["note_id"])
    visited = {int(s["note_id"]) for s in raw_steps}
    notes_by_id = {n["id"]: n for n in store.all_notes()}
    if tail_id not in notes_by_id:
        return []
    embeddings = dict(store.all_embeddings())
    if tail_id not in embeddings:
        return []
    vi = embeddings[tail_id]
    cmap, cluster_lookup = _cluster_view(threshold, top_k)

    scored: list[tuple[int, float]] = []
    for j, vj in embeddings.items():
        if j == tail_id or j in visited:
            continue
        s = float(cosine(vi, vj))
        if s > 0:
            scored.append((j, s))
    scored.sort(key=lambda x: x[1], reverse=True)
    # Prefer synapse-level candidates first; if we run out, fall back
    # to the strongest below-threshold ones so the panel keeps offering
    # something useful at any threshold setting.
    synapse_candidates = [c for c in scored if c[1] >= threshold]
    pool = synapse_candidates + [c for c in scored if c[1] < threshold]
    out: list[NextSuggestion] = []
    for nid, s in pool[:k]:
        n = notes_by_id[nid]
        cid = cmap.get(nid)
        cinfo = cluster_lookup.get(cid) if cid is not None else None
        out.append(
            NextSuggestion(
                note_id=nid,
                title=n["title"],
                snippet=_snippet(n["body"]),
                tags=list(n.get("tags") or []),
                strength=round(s, 4),
                cluster_id=cid,
                cluster_name=(cinfo or {}).get("name"),
                cluster_color=(cinfo or {}).get("color"),
            )
        )
    return out


def to_markdown(resolved: ResolvedTrail) -> str:
    """Render a resolved trail as a portable Markdown document.

    The export is deliberately self-contained — readers don't need to
    know SynapseOS exists to follow the walk. Synapse strengths are
    annotated in parentheses on each transition.
    """
    lines: list[str] = []
    lines.append(f"# {resolved.title}")
    lines.append("")
    if resolved.description:
        lines.append(f"> {resolved.description}")
        lines.append("")
    health_pct = int(round(resolved.health * 100))
    lines.append(
        f"*A SynapseOS trail · {len(resolved.steps)} steps · "
        f"{health_pct}% synapse-aligned · "
        f"τ={resolved.threshold:.2f}*"
    )
    lines.append("")
    for i, s in enumerate(resolved.steps, start=1):
        title = s.title.strip()
        lines.append(f"## {i}. {title}")
        meta_bits: list[str] = []
        if s.cluster_name:
            meta_bits.append(f"_{s.cluster_name}_")
        if s.tags:
            meta_bits.append(", ".join(f"`#{t}`" for t in s.tags))
        if meta_bits:
            lines.append(" · ".join(meta_bits))
            lines.append("")
        if s.caption:
            lines.append(f"> {s.caption}")
            lines.append("")
        if s.snippet:
            lines.append(s.snippet)
            lines.append("")
        if s.strength_to_next is not None:
            arrow = "→" if s.is_synapse_to_next else "⤳"
            lines.append(
                f"{arrow} *cosine to next step: {s.strength_to_next:.2f}"
                f"{' · synapse' if s.is_synapse_to_next else ' · leap'}*"
            )
            lines.append("")

    lines.append("---")
    lines.append("*Generated by SynapseOS · `synapse := cosine ≥ τ` · trails*")
    return "\n".join(lines) + "\n"
