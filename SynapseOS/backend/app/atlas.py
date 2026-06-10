"""Atlas — executive cartography of your second brain.

Every other surface in SynapseOS looks at one cluster, one note, or one
pair at a time. Atlas zooms out. It reads every cluster the synapse graph
just produced and tells you what *state your knowledge graph is in*:
which topics are humming, which are cooling, which are still messy,
which are stagnating, and where the bridges you haven't drawn would pay
off the most.

The model is a quadrant chart. For each cluster we score two axes:

  * **cohesion**  ∈ [0, 1] — mean ``cosine(member, centroid)`` over the
    cluster. High = the topic actually hangs together; low = it's a
    merge of two half-topics that should be split.
  * **activity** ∈ [0, 1] — fraction of members touched (created or
    re-engaged) inside the configurable ``window_days``. High = you're
    actively developing the topic; low = it's been quiet.

Quadrants follow:

    cohesion ≥ mid · activity ≥ mid   →  **Stronghold**  (bread-and-butter)
    cohesion <  mid · activity ≥ mid   →  **Frontier**    (forming, still messy)
    cohesion ≥ mid · activity <  mid   →  **Vault**       (solid but cooling)
    cohesion <  mid · activity <  mid   →  **Drift**       (stale + unfocused)

We also compute, per cluster: growth velocity (new notes in the window),
internal density (intra-cluster edges / max possible), days since most
recent note + most recent re-engagement, and a "bridge potential" count
(notes elsewhere with cosine to this centroid ≥ ``BRIDGE_FLOOR`` that the
synapse graph hasn't linked yet — exactly the cross-pollination Synthesis
already surfaces, here in aggregate).

Out of those signals, ``_build_recommendations`` distills a prioritized,
human-readable to-do list: "Synthesize *X* while it's hot", "Cluster *Y*
may be two topics", "Vault *Z* hasn't been touched in 31d", "Consider
dissolving the *W* drift cluster", "Bridge into *V* — 3 candidates waiting".

Pure stdlib, deterministic, reuses the existing graph + community +
embedding pipeline; portable Markdown export.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone

from . import community as community_mod
from . import store, synapse
from .embed import cosine

DEFAULT_WINDOW_DAYS = 30

# A note in another cluster needs at least this cosine to the centroid to
# count as a bridge candidate. Mirrors synthesis.BRIDGE_FLOOR so the two
# panels agree about what counts as "semantically close enough."
BRIDGE_FLOOR = 0.16

# Quadrant thresholds — chosen to put the fold at the middle of each
# axis. Tuned against test corpora so a healthy second brain has ~half
# of its clusters above each line.
COHESION_MID = 0.5
ACTIVITY_MID = 0.4

_EPOCH = datetime.min.replace(tzinfo=timezone.utc)


@dataclass
class AtlasCluster:
    id: int
    name: str
    color: str
    size: int
    terms: list[str]
    cohesion: float
    internal_density: float
    activity: float
    growth_velocity: int
    last_touched_days: int | None
    newest_age_days: int
    mean_age_days: float
    bridge_count: int
    has_synapses: bool
    quadrant: str  # stronghold / frontier / vault / drift


@dataclass
class AtlasRecommendation:
    cluster_id: int
    cluster_name: str
    cluster_color: str
    kind: str  # synthesize / split / revisit / dissolve / bridge
    priority: float
    headline: str
    detail: str


@dataclass
class AtlasReport:
    window_days: int
    generated_at: str
    total_notes: int
    total_clusters: int
    clusters: list[AtlasCluster]
    recommendations: list[AtlasRecommendation]
    summary: dict


def _parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def _days_between(a: datetime, b: datetime) -> float:
    return max(0.0, (b - a).total_seconds() / 86400.0)


def _centroid(vecs: list[tuple[float, ...]]) -> tuple[float, ...]:
    """Mean-pool then L2-normalize so plain dot product is cosine."""
    if not vecs:
        return tuple()
    dim = len(vecs[0])
    acc = [0.0] * dim
    for v in vecs:
        for i, x in enumerate(v):
            acc[i] += x
    n = float(len(vecs))
    acc = [x / n for x in acc]
    norm = math.sqrt(sum(x * x for x in acc)) or 1.0
    return tuple(x / norm for x in acc)


def _classify(cohesion: float, activity: float) -> str:
    if cohesion >= COHESION_MID and activity >= ACTIVITY_MID:
        return "stronghold"
    if cohesion < COHESION_MID and activity >= ACTIVITY_MID:
        return "frontier"
    if cohesion >= COHESION_MID and activity < ACTIVITY_MID:
        return "vault"
    return "drift"


def compute_atlas(
    threshold: float | None = None,
    top_k: int | None = None,
    window_days: int = DEFAULT_WINDOW_DAYS,
) -> AtlasReport:
    """Build the full Atlas report at the given graph parameters."""
    th = synapse.DEFAULT_THRESHOLD if threshold is None else threshold
    tk = synapse.DEFAULT_TOP_K if top_k is None else top_k
    window_days = max(1, int(window_days))
    now = datetime.now(timezone.utc)

    g = synapse.compute_graph(threshold=th, top_k=tk)
    notes_by_id = {n["id"]: n for n in g.nodes}
    cmap = {n["id"]: n.get("community", 0) for n in g.nodes}
    built = community_mod.build_communities(cmap, notes_by_id)
    embeddings = dict(store.all_embeddings())
    last_seen = store.last_seen_map()

    # Pre-bucket the synapse edges by "intra-cluster" vs "crosses-cluster".
    # Intra count feeds internal_density; cross map lets us cheaply ask
    # "is this outside-cluster note already linked to any member?".
    intra_edges: dict[int, int] = {c.id: 0 for c in built}
    linked_outside: dict[int, set[int]] = {c.id: set() for c in built}
    for e in g.edges:
        u, v = e["source"], e["target"]
        cu, cv = cmap.get(u), cmap.get(v)
        if cu == cv and cu is not None:
            intra_edges[cu] = intra_edges.get(cu, 0) + 1
        else:
            if cu is not None and cv is not None:
                linked_outside.setdefault(cu, set()).add(v)
                linked_outside.setdefault(cv, set()).add(u)

    notes_lookup = {n["id"]: n for n in store.all_notes()}

    clusters_out: list[AtlasCluster] = []
    quadrant_counts = {"stronghold": 0, "frontier": 0, "vault": 0, "drift": 0}
    total_growth = 0
    total_cohesion = 0.0
    total_bridges = 0

    for c in built:
        member_ids = [
            m for m in c.member_ids
            if m in embeddings and m in notes_by_id and m in notes_lookup
        ]
        if not member_ids:
            continue

        centroid = _centroid([embeddings[m] for m in member_ids])
        centralities = [max(0.0, cosine(embeddings[m], centroid)) for m in member_ids]
        cohesion = round(sum(centralities) / len(member_ids), 4)

        n = len(member_ids)
        max_e = n * (n - 1) / 2 if n > 1 else 0
        internal_density = round(intra_edges.get(c.id, 0) / max_e, 4) if max_e else 0.0

        ages: list[float] = []
        recent_window = 0
        growth = 0
        last_touched_days: int | None = None
        most_recent_touch: datetime | None = None

        for m in member_ids:
            note = notes_lookup[m]
            created = _parse_iso(note["created_at"])
            touched = _parse_iso(last_seen.get(m))
            if created:
                age = _days_between(created, now)
                ages.append(age)
                if age <= window_days:
                    growth += 1
            event = max(
                created or _EPOCH,
                touched or _EPOCH,
            )
            if event != _EPOCH and _days_between(event, now) <= window_days:
                recent_window += 1
            if touched and (most_recent_touch is None or touched > most_recent_touch):
                most_recent_touch = touched

        if not ages:
            continue
        newest_age = min(ages)
        mean_age = sum(ages) / len(ages)
        activity = round(recent_window / len(member_ids), 4)
        if most_recent_touch is not None:
            last_touched_days = int(_days_between(most_recent_touch, now))

        # Bridge candidates: outside-cluster notes with cosine >= floor that
        # the synapse graph has not yet drawn to any member.
        member_set = set(member_ids)
        already_linked = linked_outside.get(c.id, set())
        bridges = 0
        for nid, vec in embeddings.items():
            if nid in member_set or nid in already_linked:
                continue
            if cosine(vec, centroid) >= BRIDGE_FLOOR:
                bridges += 1

        quadrant = _classify(cohesion, activity)
        quadrant_counts[quadrant] += 1
        total_growth += growth
        total_cohesion += cohesion
        total_bridges += bridges

        clusters_out.append(
            AtlasCluster(
                id=c.id,
                name=c.name,
                color=c.color,
                size=c.size,
                terms=list(c.terms),
                cohesion=cohesion,
                internal_density=internal_density,
                activity=activity,
                growth_velocity=growth,
                last_touched_days=last_touched_days,
                newest_age_days=int(round(newest_age)),
                mean_age_days=round(mean_age, 1),
                bridge_count=bridges,
                has_synapses=intra_edges.get(c.id, 0) > 0,
                quadrant=quadrant,
            )
        )

    recs = _build_recommendations(clusters_out, window_days)

    summary = {
        "stronghold_count": quadrant_counts["stronghold"],
        "frontier_count": quadrant_counts["frontier"],
        "vault_count": quadrant_counts["vault"],
        "drift_count": quadrant_counts["drift"],
        "mean_cohesion": (
            round(total_cohesion / len(clusters_out), 4) if clusters_out else 0.0
        ),
        "growth_velocity": total_growth,
        "bridge_potential": total_bridges,
    }

    return AtlasReport(
        window_days=window_days,
        generated_at=now.replace(microsecond=0).isoformat(),
        total_notes=len(notes_by_id),
        total_clusters=len(clusters_out),
        clusters=clusters_out,
        recommendations=recs,
        summary=summary,
    )


def _build_recommendations(
    clusters: list[AtlasCluster], window_days: int
) -> list[AtlasRecommendation]:
    """Distil the cluster vector into a prioritized actionable to-do list.

    Priority is a soft ranking, not a strict scoring — the UI just needs a
    consistent surfacing order. Ties are broken by cluster size so bigger
    topics float above smaller ones at the same priority band.
    """
    out: list[AtlasRecommendation] = []
    for c in clusters:
        # Frontier with growth → needs synthesis before the topic scatters.
        if c.quadrant == "frontier" and c.size >= 3 and c.growth_velocity >= 2:
            out.append(
                AtlasRecommendation(
                    cluster_id=c.id,
                    cluster_name=c.name,
                    cluster_color=c.color,
                    kind="synthesize",
                    priority=0.55 + 0.05 * min(c.growth_velocity, 4),
                    headline=f"Synthesize {c.name} while it's hot",
                    detail=(
                        f"{c.growth_velocity} new note"
                        f"{'s' if c.growth_velocity != 1 else ''} in the last "
                        f"{window_days}d, cohesion {c.cohesion:.2f}. A brief now "
                        f"will catch the topic before it scatters."
                    ),
                )
            )
        # Low cohesion + decent size → probably two half-topics fused.
        if c.cohesion < 0.3 and c.size >= 5:
            out.append(
                AtlasRecommendation(
                    cluster_id=c.id,
                    cluster_name=c.name,
                    cluster_color=c.color,
                    kind="split",
                    priority=0.72,
                    headline=f"{c.name} may be two topics",
                    detail=(
                        f"Cohesion {c.cohesion:.2f} across {c.size} notes — "
                        f"that's the shape of a cluster that fused two thinner "
                        f"topics. Re-tag the outliers or nudge τ up to split."
                    ),
                )
            )
        # Vault cooling
        if c.quadrant == "vault" and c.last_touched_days is not None and c.last_touched_days >= window_days:
            out.append(
                AtlasRecommendation(
                    cluster_id=c.id,
                    cluster_name=c.name,
                    cluster_color=c.color,
                    kind="revisit",
                    priority=0.30 + min(c.last_touched_days / 365.0, 0.25),
                    headline=f"{c.name} hasn't been touched in {c.last_touched_days}d",
                    detail=(
                        f"Solid cluster ({c.size} notes, cohesion {c.cohesion:.2f}) "
                        f"but cooling. A re-read might surface a fresh angle "
                        f"you've outgrown."
                    ),
                )
            )
        # Drift small + un-synapsed → either flesh out or absorb.
        if c.quadrant == "drift" and c.size <= 3 and not c.has_synapses:
            out.append(
                AtlasRecommendation(
                    cluster_id=c.id,
                    cluster_name=c.name,
                    cluster_color=c.color,
                    kind="dissolve",
                    priority=0.25,
                    headline=f"{c.name} is barely a cluster",
                    detail=(
                        f"{c.size} note{'s' if c.size != 1 else ''}, no internal "
                        f"synapses, cohesion {c.cohesion:.2f}. Either flesh it out "
                        f"or absorb the notes into a stronger topic."
                    ),
                )
            )
        # Bridges waiting to be drawn
        if c.bridge_count >= 2:
            out.append(
                AtlasRecommendation(
                    cluster_id=c.id,
                    cluster_name=c.name,
                    cluster_color=c.color,
                    kind="bridge",
                    priority=0.40 + 0.05 * min(c.bridge_count, 6),
                    headline=f"{c.bridge_count} potential bridges into {c.name}",
                    detail=(
                        f"There are {c.bridge_count} notes elsewhere that "
                        f"semantically belong near this cluster but aren't "
                        f"synapse-linked. Nudge τ down, or write a connecting note."
                    ),
                )
            )
    # Higher priority first; ties broken by larger clusters first.
    size_of = {c.id: c.size for c in clusters}
    out.sort(key=lambda r: (-r.priority, -size_of.get(r.cluster_id, 0), r.cluster_id))
    return out


_QUADRANT_LABEL = {
    "stronghold": "Strongholds",
    "frontier": "Frontiers",
    "vault": "Vaults",
    "drift": "Drift",
}


def to_markdown(r: AtlasReport) -> str:
    """Render the report as a portable Markdown brief."""
    out: list[str] = []
    out.append(f"# Atlas — {r.generated_at[:10]}")
    out.append("")
    out.append(
        f"_{r.total_notes} notes · {r.total_clusters} clusters · "
        f"window {r.window_days}d · mean cohesion "
        f"{r.summary.get('mean_cohesion', 0.0):.2f}_"
    )
    out.append("")
    out.append("| Quadrant | Count |")
    out.append("|---|---:|")
    out.append(f"| Strongholds | {r.summary.get('stronghold_count', 0)} |")
    out.append(f"| Frontiers | {r.summary.get('frontier_count', 0)} |")
    out.append(f"| Vaults | {r.summary.get('vault_count', 0)} |")
    out.append(f"| Drift | {r.summary.get('drift_count', 0)} |")
    out.append("")

    for q in ("stronghold", "frontier", "vault", "drift"):
        members = [c for c in r.clusters if c.quadrant == q]
        if not members:
            continue
        out.append(f"## {_QUADRANT_LABEL[q]}")
        out.append("")
        for c in sorted(members, key=lambda x: (-x.cohesion, -x.size)):
            line = (
                f"- **{c.name}** — {c.size} note"
                f"{'s' if c.size != 1 else ''} · cohesion {c.cohesion:.2f}"
                f" · activity {c.activity:.2f}"
            )
            if c.growth_velocity:
                line += f" · {c.growth_velocity} new in {r.window_days}d"
            if c.last_touched_days is not None:
                line += f" · last touched {c.last_touched_days}d ago"
            if c.bridge_count:
                line += f" · {c.bridge_count} bridge candidate{'s' if c.bridge_count != 1 else ''}"
            out.append(line)
        out.append("")

    if r.recommendations:
        out.append("## Recommendations")
        out.append("")
        for rec in r.recommendations:
            out.append(f"- **{rec.headline}** — {rec.detail}")
        out.append("")

    return "\n".join(out).rstrip() + "\n"


def serialize(r: AtlasReport) -> dict:
    return {
        "window_days": r.window_days,
        "generated_at": r.generated_at,
        "total_notes": r.total_notes,
        "total_clusters": r.total_clusters,
        "clusters": [
            {
                "id": c.id,
                "name": c.name,
                "color": c.color,
                "size": c.size,
                "terms": c.terms,
                "cohesion": c.cohesion,
                "internal_density": c.internal_density,
                "activity": c.activity,
                "growth_velocity": c.growth_velocity,
                "last_touched_days": c.last_touched_days,
                "newest_age_days": c.newest_age_days,
                "mean_age_days": c.mean_age_days,
                "bridge_count": c.bridge_count,
                "has_synapses": c.has_synapses,
                "quadrant": c.quadrant,
            }
            for c in r.clusters
        ],
        "recommendations": [
            {
                "cluster_id": rec.cluster_id,
                "cluster_name": rec.cluster_name,
                "cluster_color": rec.cluster_color,
                "kind": rec.kind,
                "priority": round(rec.priority, 4),
                "headline": rec.headline,
                "detail": rec.detail,
            }
            for rec in r.recommendations
        ],
        "summary": r.summary,
    }
