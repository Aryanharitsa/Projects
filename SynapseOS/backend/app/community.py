"""Community detection + cluster naming + orphan rescue.

The graph in `synapse.py` is the substrate. This module is what turns
"a hairball of edges" into "I can *see* my topical structure":

- ``detect_communities`` runs **label propagation** (LPA) over the
  current synapse graph. LPA is O(E) per pass, converges in handfuls of
  passes on graphs of this size, and produces sensible communities
  without any tuning knobs. We seed Python's ``random`` with a stable
  hash of the node-id set so the *same* graph yields the *same* coloring
  across reloads (otherwise the frontend palette would shuffle on every
  request, which is visually disorienting).

- ``name_communities`` derives a short human-readable label for each
  cluster from its members' titles + tags + bodies. We score every term
  by **distinctiveness** — a soft TF-IDF that rewards terms that are
  frequent inside the cluster *and* relatively rare outside it. The top
  scorer becomes the cluster name; the next two become "key terms."

- ``find_orphans`` surfaces notes that have zero synapses at the current
  threshold, *and* the strongest below-threshold candidate they could
  attach to if you nudged ``τ`` down. This is the "rescue" affordance —
  isolated thoughts shouldn't stay isolated by accident.

Palette assignment is deterministic — community 0 always gets the first
color, etc. — so reloads don't strobe.
"""

from __future__ import annotations

import random
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Iterable

# 12-color palette tuned against the dark UI. Order matters: small
# graphs only ever consume the first few, so the first colors should be
# the most distinct from each other.
PALETTE: tuple[str, ...] = (
    "#a855f7",  # violet
    "#22d3ee",  # cyan
    "#f472b6",  # pink
    "#a3e635",  # lime
    "#fbbf24",  # amber
    "#60a5fa",  # blue
    "#f87171",  # red
    "#34d399",  # emerald
    "#c084fc",  # plum
    "#fb923c",  # orange
    "#facc15",  # yellow
    "#94a3b8",  # slate (fallback / overflow)
)

# A tiny stop-word list. Intentionally small — we lean on the
# distinctiveness term in the scoring rather than aggressive filtering,
# which would hide useful domain words.
_STOP = frozenset(
    """a an the and or but of for to in on at by from with as is are was were be been being
    this that these those it its they them their there here we you i me my our your his her
    not no yes do does did so if then than else when while which who whom how what why where
    can could should would may might must will shall just only also more most less few many
    very too into onto out up down off over under between among per about across after before
    again any all some each every both either neither one two three first second new old same
    such other another own enough still even ever never always often sometimes maybe perhaps
    way ways thing things stuff way like really kinda sorta etc vs via per
    """.split()
)

_TOKEN_RE = re.compile(r"[a-z][a-z0-9\-]{2,}")


@dataclass
class Community:
    id: int
    name: str
    color: str
    size: int
    terms: list[str]
    member_ids: list[int]


@dataclass
class OrphanSuggestion:
    note_id: int
    title: str
    suggested_id: int | None
    suggested_title: str | None
    suggested_strength: float
    suggested_threshold: float


# --------------------------------------------------------------------- LPA


def detect_communities(
    node_ids: list[int],
    edges: Iterable[tuple[int, int, float]],
) -> dict[int, int]:
    """Greedy modularity maximization (Newman-style agglomerative).

    Why not plain LPA? Synapse graphs have *hub* notes that bridge
    multiple topics ("why this app exists" mentions ML + PKM + product
    in three sentences). LPA on such graphs collapses everything into
    one giant label. Modularity-greedy explicitly resists collapse by
    rewarding partitions whose intra-community edge density exceeds
    chance expectation under a random graph with the same degree
    sequence.

    Algorithm:
      1. Start with each node as its own community.
      2. Compute, for each edge, ``ΔQ`` of merging its endpoints'
         communities: ``ΔQ = 2(e_ab - a_a · a_b)`` per Newman 2004,
         where ``e_ab`` is the share of total edge weight between the
         two communities and ``a_x`` is the share of total weight
         touching community ``x``.
      3. Take the merge with the largest positive ``ΔQ``; recompute;
         repeat until no positive ``ΔQ`` exists.

    O(V·E) overall — trivial at our scale.

    - Singletons (no edges) stay their own community.
    - Community ids are dense small integers, ordered by descending
      size so id 0 is the largest cluster (the palette's primary slot).
    """
    edges_list = list(edges)
    if not edges_list or not node_ids:
        return {nid: i for i, nid in enumerate(node_ids)}

    # community-of-node and members-of-community, both mutated in place.
    comm: dict[int, int] = {nid: nid for nid in node_ids}
    members: dict[int, set[int]] = {nid: {nid} for nid in node_ids}

    # k_c: total edge weight incident to community c (each edge counted
    # once per endpoint, which is the standard convention so 2m below
    # works out). w_ab: edge weight between communities a and b.
    two_m = 2.0 * sum(s for _, _, s in edges_list)
    if two_m == 0:
        return {nid: i for i, nid in enumerate(node_ids)}

    k: dict[int, float] = defaultdict(float)
    for u, v, s in edges_list:
        k[comm[u]] += s
        k[comm[v]] += s

    # inter[a][b] = sum of edge weights between communities a and b
    # (a != b). Maintained symmetrically.
    inter: dict[int, dict[int, float]] = defaultdict(lambda: defaultdict(float))
    for u, v, s in edges_list:
        a, b = comm[u], comm[v]
        if a == b:
            continue
        inter[a][b] += s
        inter[b][a] += s

    while True:
        best_gain = 0.0
        best_pair: tuple[int, int] | None = None
        for a, neigh in inter.items():
            ka = k[a]
            for b, wab in neigh.items():
                if b <= a:  # symmetric, skip dupes
                    continue
                # ΔQ for merging a and b. (e_ab is wab/2m, a_x is k_x/2m;
                # the factor of 2 inside ΔQ cancels the doubled inter
                # storage we keep above for cheap lookups.)
                gain = (wab / two_m) - (ka * k[b]) / (two_m * two_m)
                if gain > best_gain:
                    best_gain = gain
                    best_pair = (a, b)
        if best_pair is None:
            break

        a, b = best_pair
        # Merge b into a.
        members[a].update(members.pop(b))
        for nid in members[a]:
            comm[nid] = a
        k[a] += k[b]
        del k[b]
        # Splice b's inter-edges into a's; drop b entirely.
        for c, wbc in list(inter[b].items()):
            if c == a:
                continue
            inter[a][c] += wbc
            inter[c][a] += wbc
            inter[c].pop(b, None)
        inter[a].pop(b, None)
        inter.pop(b, None)

    # Compress raw labels to dense ids ordered by community size.
    sizes = Counter(comm.values())
    by_size = [lab for lab, _ in sizes.most_common()]
    remap = {old: new for new, old in enumerate(by_size)}
    return {nid: remap[comm[nid]] for nid in node_ids}


# --------------------------------------------------------------- naming


def _terms(text: str) -> list[str]:
    return [t for t in _TOKEN_RE.findall(text.lower()) if t not in _STOP]


def name_communities(
    communities: dict[int, int],
    notes_by_id: dict[int, dict],
) -> dict[int, tuple[str, list[str]]]:
    """For each community id → (display_name, top_3_terms).

    Score(term, c) = tf(term, c) · ( tf(term, c) / max(1, total_tf(term)) )
                     · log(1 + |c|)

    The middle factor is a "distinctiveness" multiplier in [0, 1]: a
    term that lives entirely inside community ``c`` scores 1; a
    universally-used term scores ``1 / n_clusters``. The log size factor
    breaks ties in favor of larger clusters where the term has wider
    support, which matches human intuition about "what is this group
    about."
    """
    # Per-cluster term frequency
    cluster_tf: dict[int, Counter[str]] = defaultdict(Counter)
    global_tf: Counter[str] = Counter()
    cluster_size: Counter[int] = Counter()

    for nid, cid in communities.items():
        n = notes_by_id.get(nid)
        if not n:
            continue
        cluster_size[cid] += 1
        # Title gets weight 3 (more signal per token), tags weight 2,
        # body weight 1. This biases names toward concise topical hooks.
        for t in _terms(n["title"]):
            cluster_tf[cid][t] += 3
            global_tf[t] += 3
        for tag in n.get("tags", []):
            for t in _terms(tag):
                cluster_tf[cid][t] += 2
                global_tf[t] += 2
        for t in _terms(n["body"]):
            cluster_tf[cid][t] += 1
            global_tf[t] += 1

    import math

    out: dict[int, tuple[str, list[str]]] = {}
    for cid in cluster_tf:
        tf = cluster_tf[cid]
        if not tf:
            out[cid] = (f"Cluster {cid + 1}", [])
            continue
        scored: list[tuple[float, str]] = []
        for term, c in tf.items():
            distinct = c / max(1, global_tf[term])
            score = c * distinct * math.log(1 + cluster_size[cid])
            scored.append((score, term))
        scored.sort(key=lambda x: (-x[0], x[1]))
        ranked = [t for _, t in scored[:6]]
        # "Name" is the top distinctive term, title-cased; falls back to
        # cluster index when nothing scores positively (degenerate case).
        name = ranked[0].replace("-", " ").title() if ranked else f"Cluster {cid + 1}"
        terms = ranked[:3]
        out[cid] = (name, terms)
    return out


def color_for(community_id: int) -> str:
    if community_id < 0:
        return PALETTE[-1]
    return PALETTE[community_id % len(PALETTE)]


def build_communities(
    communities: dict[int, int],
    notes_by_id: dict[int, dict],
) -> list[Community]:
    """Assemble Community records ready for the API."""
    if not communities:
        return []
    members: dict[int, list[int]] = defaultdict(list)
    for nid, cid in communities.items():
        members[cid].append(nid)
    names = name_communities(communities, notes_by_id)

    out: list[Community] = []
    for cid in sorted(members.keys()):
        name, terms = names.get(cid, (f"Cluster {cid + 1}", []))
        out.append(
            Community(
                id=cid,
                name=name,
                color=color_for(cid),
                size=len(members[cid]),
                terms=terms,
                member_ids=sorted(members[cid]),
            )
        )
    return out


# ------------------------------------------------------------- orphans


def find_orphans(
    node_ids: list[int],
    edges: Iterable[tuple[int, int, float]],
    notes_by_id: dict[int, dict],
    embeddings: dict[int, tuple[float, ...]],
    cosine_fn,
    current_threshold: float,
) -> list[OrphanSuggestion]:
    """Notes with zero edges + their best below-threshold candidate.

    The "rescue" suggestion is the highest-cosine peer they have that
    *failed* the current threshold. We also surface the τ value that
    would attach them — exactly the candidate similarity, rounded down a
    hair so the user doesn't land on a knife-edge.
    """
    adj_count: Counter[int] = Counter()
    for u, v, _ in edges:
        adj_count[u] += 1
        adj_count[v] += 1

    out: list[OrphanSuggestion] = []
    for nid in node_ids:
        if adj_count[nid] > 0:
            continue
        n = notes_by_id.get(nid)
        if not n:
            continue
        vi = embeddings.get(nid)
        best_id: int | None = None
        best_strength = 0.0
        if vi is not None:
            for jid, vj in embeddings.items():
                if jid == nid:
                    continue
                s = cosine_fn(vi, vj)
                if s > best_strength:
                    best_strength = s
                    best_id = jid
        suggested_title = (
            notes_by_id[best_id]["title"] if best_id is not None and best_id in notes_by_id else None
        )
        # Drop τ a hair below the candidate so the edge actually fires
        # when the user adopts the suggestion. Floor at 0 just in case.
        nudged = max(0.0, round(best_strength - 0.005, 3))
        out.append(
            OrphanSuggestion(
                note_id=nid,
                title=n["title"],
                suggested_id=best_id,
                suggested_title=suggested_title,
                suggested_strength=round(best_strength, 4),
                suggested_threshold=nudged,
            )
        )
    # Order by "easiest to rescue first" — strongest near-miss at the top.
    out.sort(key=lambda o: o.suggested_strength, reverse=True)
    return out
