"""Spark — the first generative surface in SynapseOS.

Every other surface in this app **describes** what's already in your
second brain. Atlas reads the quadrant chart. Pulse reads the diff.
Chronicle reads the temporal arc. Tensions reads the contradictions.
Echoes reads the duplicates. They are all *observational*.

Spark inverts that. It reads the *holes* and proposes the next note that
would fill each one — title + opener + tags + cited evidence + predicted
cluster + predicted synapse count — so the canvas in front of you stops
being a snapshot of where your thinking has been and starts becoming a
queue of where it could go next. Click *commit* on a spark and the
NoteComposer pre-fills with the draft; you skim, edit, and save.

Five spark kinds, each tuned to a specific graph pathology
-----------------------------------------------------------

- **bridge** — two clusters whose centroids sit close in embedding space
  but whose members are never connected by a synapse. Drafts a
  "X meets Y" connector note quoting one anchor sentence from each side.

- **distill** — a cluster with enough cohesion to be a real topic but
  no single member dominant enough to act as its anchor (weight-of-max
  below ``DISTILL_HUB_CEILING``). Drafts a synthesis-style "What X
  really is" note that stitches the leading sentences of the three
  highest-centrality members.

- **counter** — a hub note whose surrounding cluster vocabulary has no
  detectable negation signal (no "but", "however", "against", "wrong",
  no antonyms over a small known map). Drafts an "Against …" piece
  that opens with the hub's leading claim and frames the inversion.

- **frontier** — terms that show up only in the *newest* member of a
  cluster (within ``FRONTIER_WINDOW_DAYS``) and don't appear anywhere
  else in your graph. These are concepts you've named once and haven't
  developed. Drafts a tight definition-note for the term.

- **revive** — a vault cluster (cohesion ≥ ``REVIVE_COHESION_FLOOR``,
  activity < ``REVIVE_ACTIVITY_CEILING``, last touch ≥
  ``REVIVE_DORMANT_DAYS``). Drafts a reflective "Returning to X" note
  framed around the cluster's distinctive vocabulary and a tasteful
  prompt list.

Every spark also carries:

- **predicted_cluster** — best-matching community centroid for the
  drafted body (so the user sees, before saving, where the note will
  land on the graph).
- **predicted_synapses** — the top-3 existing notes the draft would
  synapse to *if* it were committed, computed by embedding the draft
  body + title and running the same cosine + top-K cap the live
  synapse engine uses.
- **rationale** — one sentence on why this gap is worth filling now.

Pure-stdlib, deterministic, reuses the existing graph/community/embed
stack. Optional LLM polish via ``SYNAPSE_LLM_KEY`` rewrites titles +
openers under a strict citation contract; falls back silently on any
error. Portable Markdown export so the whole spark queue is paste-into
anywhere.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone

from . import community as community_mod
from . import store, synapse
from .embed import DIM, cosine, embed

# ---------------------------------------------------------------- knobs

DEFAULT_LIMIT = 12
"""Max number of sparks returned across all kinds."""

DEFAULT_PER_KIND = 4
"""Soft cap per kind so one pathology doesn't drown the queue."""

# Bridge: centroid cosine has to be this high before we propose a
# bridge — below this the two topics genuinely don't overlap and a
# bridge note would be forced. Calibrated above the synapse default τ
# so we are only proposing bridges for cluster pairs that are *near
# each other in embedding space* but where the per-note top-K cap kept
# them off the graph.
BRIDGE_CENTROID_FLOOR = 0.18

# When two clusters DO have cross-synapses already, we can still propose
# a bridge if the link is fragile: the strongest cross-edge is below
# this floor. Otherwise the bridge spark would just compete with an
# already-drawn, solid synapse.
BRIDGE_THIN_LINK_STRONG_FLOOR = 0.22
# Centroid affinity required to upgrade a thin-link pair into a bridge
# suggestion — slightly higher than the unlinked floor so we don't
# spam the queue with every weak cross-link.
BRIDGE_THIN_LINK_CENTROID = 0.20

# Distill: a cluster qualifies for a distill if its strongest member's
# normalized weight is below this and it has at least DISTILL_MIN_SIZE
# notes. The signal: many related notes, no central one to anchor them.
DISTILL_HUB_CEILING = 0.55
DISTILL_MIN_SIZE = 4
# Secondary distill trigger — large clusters with low cohesion are
# clearly two-half-topics fused and benefit from a synthesis even when
# they nominally have a hub.
DISTILL_LARGE_SIZE = 6
DISTILL_LARGE_COHESION_CEILING = 0.45

# Counter: a hub note is a candidate if its weight is at or above this
# and the cluster vocabulary lacks any negation marker.
COUNTER_HUB_WEIGHT = 0.45

# Frontier: how recent a "newest member" must be to count as a frontier
# observation. Anything newer than this is still in formation.
FRONTIER_WINDOW_DAYS = 30
# A frontier term must appear at least this many times in the newest
# note's body. 1 is the practical floor — atomic notes are short, so
# requiring 2+ occurrences ends up only matching prose padding.
FRONTIER_MIN_OCCURRENCES = 1
# Minimum character length — short tokens are almost always filler.
# Calibrated against the seed: 6+ catches concept-shaped words ("hashing",
# "modularity", "vault") while suppressing common-English noise.
FRONTIER_MIN_LEN = 6
# Don't propose more than this many frontier sparks per cluster — one
# fresh idea per topic is enough; more dilutes the queue.
FRONTIER_PER_CLUSTER = 1

# Revive: a vault is one that hits all three. Tuned against the seed.
REVIVE_COHESION_FLOOR = 0.45
REVIVE_ACTIVITY_CEILING = 0.20
REVIVE_DORMANT_DAYS = 30

# Predicted-synapse top-K + threshold. Mirrors synapse defaults so what
# the spark advertises matches what the live graph would draw.
PREDICTED_TOP_K = 5
PREDICTED_THRESHOLD = synapse.DEFAULT_THRESHOLD

# Tag budgets.
MAX_TAGS = 4
TAG_MAX_CHARS = 24

SPARK_KINDS = ("bridge", "distill", "counter", "frontier", "revive")

# Strong stance lexicon — if any of these appear in a cluster body, we
# treat that cluster as already carrying an opposing-stance note and
# skip the counter spark. Kept tight on purpose: prose connectors like
# "but" / "however" / "though" appear in essentially every natural
# paragraph and would suppress every counter spark if included.
_NEGATION_MARKERS = frozenset(
    """against anti contra rebuttal rebut refute debunk overrated
    broken flawed failure fallacy myth mistaken misguided wrong-headed
    counter-argument counterargument disagree disagreement oppose opposition
    rejection skeptical skepticism critique unsound
    """.split()
)

# A small antonym map used to detect "stance diversity" inside a cluster
# title list. If the cluster already has both halves of any pair as
# notable terms, no counter is generated.
_ANTONYM_PAIRS: tuple[tuple[str, str], ...] = (
    ("simple", "complex"),
    ("fast", "slow"),
    ("cheap", "expensive"),
    ("centralized", "decentralized"),
    ("monolith", "microservices"),
    ("synchronous", "async"),
    ("typed", "untyped"),
    ("static", "dynamic"),
    ("client", "server"),
    ("strict", "loose"),
    ("optimistic", "pessimistic"),
    ("offline", "online"),
    ("good", "bad"),
    ("for", "against"),
)

_STOP = frozenset(
    """a an the and or but of for to in on at by from with as is are was were be been being
    this that these those it its they them their there here we you i me my our your his her
    not no yes do does did so if then than else when while which who whom how what why where
    can could should would may might must will shall just only also more most less few many
    very too into onto out up down off over under between among per about across after before
    again any all some each every both either neither one two three first second new old same
    such other another own enough still even ever never always often sometimes maybe perhaps
    way ways thing things stuff like really kinda sorta etc via vs per think thought thinking
    use using used make made making get got getting see seen seeing find found going go went
    take taken taking come came coming want wanted know known said say says saying
    notes note view look looks looking much many lot lots quietly never always usually
    something anything everything someone anyone everyone really actually basically
    pretty whole almost nearly mostly rather quite fairly somewhat slightly hardly
    quickly easily simply clearly obviously certainly probably possibly
    being doing having seeming feeling looking running working making giving taking
    today yesterday tomorrow currently recently lately later soon often sometimes
    case cases mind set sets place places sense form forms part parts kind kinds
    person people friend friends life lives world worlds
    instead useful simple important special particular common possible available
    similar different several various general specific certain entire whole exact
    actual current recent latest typical normal usual standard regular ordinary
    extra additional further another remaining whatever whichever anything everything
    multiple single double triple complete entire partial relevant related related-to
    overall combined nearby surrounding above below within without across throughout
    along around inside outside besides except include including includes excluded
    application applications context contexts situation situations example examples
    """.split()
)

_TOKEN_RE = re.compile(r"[a-z][a-z0-9\-]{2,}")
_SENTENCE_END_RE = re.compile(r"([\.!\?])\s+(?=[A-Z\(\[\"'“‘])")
_EPOCH = datetime.min.replace(tzinfo=timezone.utc)


# --------------------------------------------------------------- types


@dataclass
class PredictedSynapse:
    note_id: int
    title: str
    strength: float


@dataclass
class CitedEvidence:
    note_id: int
    title: str
    snippet: str
    cluster_id: int | None = None
    cluster_name: str | None = None
    cluster_color: str | None = None


@dataclass
class Spark:
    id: str
    kind: str  # bridge / distill / counter / frontier / revive
    priority: float
    title: str
    body: str
    tags: list[str]
    rationale: str
    headline: str  # one-line label used by the UI's filter chips
    cited_evidence: list[CitedEvidence] = field(default_factory=list)
    predicted_cluster_id: int | None = None
    predicted_cluster_name: str | None = None
    predicted_cluster_color: str | None = None
    predicted_cluster_strength: float = 0.0
    predicted_synapses: list[PredictedSynapse] = field(default_factory=list)
    expected_synapse_count: int = 0
    # bridge sparks carry the (a, b) cluster ids for the UI's bridge tag.
    bridge_cluster_a_id: int | None = None
    bridge_cluster_a_name: str | None = None
    bridge_cluster_a_color: str | None = None
    bridge_cluster_b_id: int | None = None
    bridge_cluster_b_name: str | None = None
    bridge_cluster_b_color: str | None = None
    # cosine between bridge centroids (bridge sparks only).
    bridge_centroid_cosine: float = 0.0


@dataclass
class SparkReport:
    generated_at: str
    total_notes: int
    total_clusters: int
    sparks: list[Spark]
    summary: dict


# --------------------------------------------------------------- helpers


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
    if not vecs:
        return tuple(0.0 for _ in range(DIM))
    dim = len(vecs[0])
    acc = [0.0] * dim
    for v in vecs:
        for i, x in enumerate(v):
            acc[i] += x
    n = float(len(vecs))
    acc = [x / n for x in acc]
    norm = math.sqrt(sum(x * x for x in acc)) or 1.0
    return tuple(x / norm for x in acc)


def _slugify(term: str) -> str:
    out = re.sub(r"[^a-z0-9\-]+", "-", term.lower()).strip("-")
    return out[:TAG_MAX_CHARS]


def _terms(text: str) -> list[str]:
    return [t for t in _TOKEN_RE.findall(text.lower()) if t not in _STOP]


def _first_sentence(text: str, *, max_chars: int = 220) -> str:
    """First reasonable sentence of a body, with a soft length cap."""
    if not text:
        return ""
    body = text.strip()
    # Strip leading markdown headings / bullets.
    body = re.sub(r"^\s{0,3}(#{1,6}\s+|[-*+•]\s+|\d+\.\s+)", "", body)
    parts = _SENTENCE_END_RE.split(body, maxsplit=1)
    if not parts:
        return body[:max_chars]
    first = parts[0]
    if len(parts) >= 2:
        # parts[1] is the punctuation that ended the first sentence
        first = first + parts[1]
    first = first.strip()
    if len(first) > max_chars:
        cut = first.rfind(" ", 0, max_chars - 1)
        first = first[: cut if cut > 80 else max_chars - 1].rstrip(",;:") + "…"
    return first


def _stable_id(parts: list[str]) -> str:
    """Deterministic spark id so reloads return stable cards.

    Bridge ids contain the sorted cluster pair; distill/counter/revive
    use the cluster id; frontier uses cluster id + term. The 12-char
    hex is plenty of room for our scale and stays readable in logs.
    """
    h = hashlib.sha1("|".join(parts).encode("utf-8")).digest()
    return h[:6].hex()


def _distinctive_terms(
    text: str,
    universe_tf: Counter,
    *,
    limit: int = 5,
) -> list[str]:
    """TF-IDF-ish term ranking using `universe_tf` as the IDF backdrop."""
    local = Counter(_terms(text))
    if not local:
        return []
    scored: list[tuple[float, str]] = []
    for term, c in local.items():
        denom = max(1, universe_tf.get(term, 1))
        score = c * (c / denom) * math.log(1 + len(term))
        scored.append((score, term))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [t for _, t in scored[:limit]]


def _build_tags(seed_terms: list[str], cluster_terms: list[str]) -> list[str]:
    """Merge a draft's distinctive terms with the cluster's terms, dedup,
    slugify, cap at MAX_TAGS. Cluster terms always come first because
    they are the topical anchor."""
    seen: set[str] = set()
    out: list[str] = []
    for t in cluster_terms + seed_terms:
        s = _slugify(t)
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
        if len(out) >= MAX_TAGS:
            break
    return out


# ----------------------------------------------------------- prediction


def _predict_synapses(
    draft_vec: tuple[float, ...],
    embeddings: dict[int, tuple[float, ...]],
    notes_lookup: dict[int, dict],
    *,
    threshold: float = PREDICTED_THRESHOLD,
    top_k: int = PREDICTED_TOP_K,
    exclude_ids: set[int] | None = None,
) -> list[PredictedSynapse]:
    """Run the same cosine + top-K cap the synapse engine uses against
    a hypothetical draft vector. Used to advertise "this note will
    form N synapses if you save it" — the user sees concrete plumbing
    before they commit."""
    exclude_ids = exclude_ids or set()
    sims: list[tuple[int, float]] = []
    for nid, v in embeddings.items():
        if nid in exclude_ids:
            continue
        s = cosine(draft_vec, v)
        if s >= threshold:
            sims.append((nid, round(s, 4)))
    sims.sort(key=lambda x: x[1], reverse=True)
    out: list[PredictedSynapse] = []
    for nid, s in sims[:top_k]:
        n = notes_lookup.get(nid)
        if not n:
            continue
        out.append(PredictedSynapse(note_id=nid, title=n.get("title", "?"), strength=s))
    return out


def _predict_cluster(
    draft_vec: tuple[float, ...],
    centroids: dict[int, tuple[float, ...]],
    community_meta: dict[int, dict],
) -> tuple[int | None, str | None, str | None, float]:
    """Return the cluster the drafted note would most likely join."""
    best_id: int | None = None
    best_score = -2.0
    for cid, c in centroids.items():
        s = cosine(draft_vec, c)
        if s > best_score:
            best_score = s
            best_id = cid
    if best_id is None or best_score <= 0:
        return None, None, None, 0.0
    meta = community_meta.get(best_id, {})
    return (
        best_id,
        meta.get("name"),
        meta.get("color"),
        round(max(0.0, best_score), 4),
    )


# --------------------------------------------------------------- engine


def compute_sparks(
    threshold: float | None = None,
    top_k: int | None = None,
    limit: int = DEFAULT_LIMIT,
    per_kind: int = DEFAULT_PER_KIND,
    kinds: list[str] | None = None,
) -> SparkReport:
    """Build the full spark queue at the given graph parameters.

    `kinds` filters to a subset (e.g. `["bridge"]`) when the UI wants
    a single tab; the default is all five.
    """
    th = synapse.DEFAULT_THRESHOLD if threshold is None else threshold
    tk = synapse.DEFAULT_TOP_K if top_k is None else top_k
    kinds = kinds or list(SPARK_KINDS)
    kinds = [k for k in kinds if k in SPARK_KINDS]
    if not kinds:
        kinds = list(SPARK_KINDS)
    per_kind = max(1, min(per_kind, 20))

    now = datetime.now(timezone.utc)
    notes = store.all_notes()
    notes_lookup = {n["id"]: n for n in notes}
    embeddings = dict(store.all_embeddings())
    last_seen = store.last_seen_map()

    g = synapse.compute_graph(threshold=th, top_k=tk)
    notes_by_id = {n["id"]: n for n in g.nodes}
    weights = {n["id"]: float(n.get("weight", 0.0)) for n in g.nodes}
    cmap = {n["id"]: n.get("community", 0) for n in g.nodes}
    built = community_mod.build_communities(cmap, notes_by_id)
    community_meta: dict[int, dict] = {
        c.id: {"name": c.name, "color": c.color, "size": c.size, "terms": list(c.terms)}
        for c in built
    }

    # Pre-compute per-cluster centroid + member centrality + age + bodies.
    centroids: dict[int, tuple[float, ...]] = {}
    cluster_members: dict[int, list[int]] = {}
    cluster_centralities: dict[int, dict[int, float]] = {}
    cluster_age: dict[int, dict] = {}
    cluster_text: dict[int, str] = {}
    cluster_global_tf: Counter = Counter()
    universe_tf: Counter = Counter()
    for cid, c in community_meta.items():
        member_ids = [
            m for m in c["terms"] if False
        ]  # silence — we just want the keys init
    # actually compute:
    for c in built:
        members = [m for m in c.member_ids if m in embeddings and m in notes_lookup]
        if not members:
            continue
        cluster_members[c.id] = members
        cent = _centroid([embeddings[m] for m in members])
        centroids[c.id] = cent
        centralities = {m: max(0.0, cosine(embeddings[m], cent)) for m in members}
        cluster_centralities[c.id] = centralities

        # Age window per cluster — used by frontier + revive.
        member_ages: list[float] = []
        most_recent_touch: datetime | None = None
        newest_note_id: int | None = None
        newest_age: float = float("inf")
        for m in members:
            note = notes_lookup[m]
            created = _parse_iso(note["created_at"])
            touched = _parse_iso(last_seen.get(m))
            if created:
                age = _days_between(created, now)
                member_ages.append(age)
                if age < newest_age:
                    newest_age = age
                    newest_note_id = m
            if touched and (most_recent_touch is None or touched > most_recent_touch):
                most_recent_touch = touched

        cluster_age[c.id] = {
            "ages": member_ages,
            "newest_note_id": newest_note_id,
            "newest_age_days": newest_age if member_ages else None,
            "mean_age_days": sum(member_ages) / len(member_ages) if member_ages else None,
            "last_touched_days": (
                int(_days_between(most_recent_touch, now)) if most_recent_touch else None
            ),
        }

        # Concat cluster body for vocabulary work.
        body = " \n ".join(
            f"{notes_lookup[m].get('title', '')}\n{notes_lookup[m].get('body', '')}"
            for m in members
        )
        cluster_text[c.id] = body
        for t in _terms(body):
            cluster_global_tf[t] += 1

    # Universe TF: every note body counts once per term occurrence so
    # the distinctiveness denominator is consistent across spark types.
    for n in notes:
        for t in _terms(f"{n.get('title', '')}\n{n.get('body', '')}"):
            universe_tf[t] += 1

    sparks: list[Spark] = []
    if "bridge" in kinds:
        sparks.extend(
            _bridge_sparks(
                built=built,
                cluster_members=cluster_members,
                centroids=centroids,
                cluster_centralities=cluster_centralities,
                community_meta=community_meta,
                embeddings=embeddings,
                notes_lookup=notes_lookup,
                universe_tf=universe_tf,
                edges=g.edges,
                per_kind=per_kind,
            )
        )
    if "distill" in kinds:
        sparks.extend(
            _distill_sparks(
                cluster_members=cluster_members,
                cluster_centralities=cluster_centralities,
                community_meta=community_meta,
                centroids=centroids,
                weights=weights,
                embeddings=embeddings,
                notes_lookup=notes_lookup,
                universe_tf=universe_tf,
                per_kind=per_kind,
            )
        )
    if "counter" in kinds:
        sparks.extend(
            _counter_sparks(
                cluster_members=cluster_members,
                cluster_centralities=cluster_centralities,
                community_meta=community_meta,
                centroids=centroids,
                weights=weights,
                embeddings=embeddings,
                notes_lookup=notes_lookup,
                cluster_text=cluster_text,
                universe_tf=universe_tf,
                per_kind=per_kind,
            )
        )
    if "frontier" in kinds:
        sparks.extend(
            _frontier_sparks(
                cluster_members=cluster_members,
                community_meta=community_meta,
                centroids=centroids,
                embeddings=embeddings,
                notes_lookup=notes_lookup,
                cluster_age=cluster_age,
                cluster_global_tf=cluster_global_tf,
                universe_tf=universe_tf,
                per_kind=per_kind,
            )
        )
    if "revive" in kinds:
        sparks.extend(
            _revive_sparks(
                cluster_members=cluster_members,
                cluster_centralities=cluster_centralities,
                community_meta=community_meta,
                centroids=centroids,
                embeddings=embeddings,
                notes_lookup=notes_lookup,
                cluster_age=cluster_age,
                universe_tf=universe_tf,
                per_kind=per_kind,
            )
        )

    # Score predicted synapses per spark + drop sparks that would form
    # zero synapses (those are usually outside the graph's gravity well
    # and won't add value).
    enriched: list[Spark] = []
    for sp in sparks:
        draft_vec = embed(f"{sp.title}\n\n{sp.body}")
        excl = {ev.note_id for ev in sp.cited_evidence}
        preds = _predict_synapses(
            draft_vec, embeddings, notes_lookup, exclude_ids=excl
        )
        sp.predicted_synapses = preds
        sp.expected_synapse_count = len(preds)
        cid, cname, ccolor, cstrength = _predict_cluster(
            draft_vec, centroids, community_meta
        )
        sp.predicted_cluster_id = cid
        sp.predicted_cluster_name = cname
        sp.predicted_cluster_color = ccolor
        sp.predicted_cluster_strength = cstrength
        # Re-rank: priority gets a small bump from predicted-synapse
        # count so sparks that will actually land on the graph float
        # above dryer ones.
        sp.priority = round(sp.priority + 0.04 * min(sp.expected_synapse_count, 5), 4)
        enriched.append(sp)

    # Stable global ordering: highest priority first; ties broken by
    # kind order then by id so the queue is deterministic.
    kind_rank = {k: i for i, k in enumerate(SPARK_KINDS)}
    enriched.sort(
        key=lambda s: (-s.priority, kind_rank.get(s.kind, 99), s.id)
    )
    enriched = enriched[:limit]

    summary = {
        "bridge_count": sum(1 for s in enriched if s.kind == "bridge"),
        "distill_count": sum(1 for s in enriched if s.kind == "distill"),
        "counter_count": sum(1 for s in enriched if s.kind == "counter"),
        "frontier_count": sum(1 for s in enriched if s.kind == "frontier"),
        "revive_count": sum(1 for s in enriched if s.kind == "revive"),
        "mean_predicted_synapses": (
            round(sum(s.expected_synapse_count for s in enriched) / len(enriched), 2)
            if enriched
            else 0.0
        ),
        "highest_priority": round(enriched[0].priority, 4) if enriched else 0.0,
    }

    return SparkReport(
        generated_at=now.replace(microsecond=0).isoformat(),
        total_notes=len(notes),
        total_clusters=len(built),
        sparks=enriched,
        summary=summary,
    )


# --------------------------------------------------------------- bridge


def _bridge_sparks(
    *,
    built,
    cluster_members: dict[int, list[int]],
    centroids: dict[int, tuple[float, ...]],
    cluster_centralities: dict[int, dict[int, float]],
    community_meta: dict[int, dict],
    embeddings: dict[int, tuple[float, ...]],
    notes_lookup: dict[int, dict],
    universe_tf: Counter,
    edges: list[dict],
    per_kind: int,
) -> list[Spark]:
    if len(centroids) < 2:
        return []

    # Pre-compute "how strongly are cluster A and B already connected?"
    # We count cross-cluster edges and track the strongest cross-link
    # so we can distinguish "well-bridged" (skip) from "thin link"
    # (still worth a connector note).
    cross_edges: dict[tuple[int, int], list[float]] = defaultdict(list)
    member_to_cluster: dict[int, int] = {}
    for cid, members in cluster_members.items():
        for m in members:
            member_to_cluster[m] = cid
    for e in edges:
        a = member_to_cluster.get(e["source"])
        b = member_to_cluster.get(e["target"])
        if a is None or b is None or a == b:
            continue
        pair = (a, b) if a < b else (b, a)
        cross_edges[pair].append(float(e.get("strength", 0.0)))

    candidates: list[tuple[float, int, int]] = []
    cluster_ids = sorted(centroids.keys())
    for i, a in enumerate(cluster_ids):
        for b in cluster_ids[i + 1 :]:
            sim = cosine(centroids[a], centroids[b])
            pair = (a, b)
            edges_here = cross_edges.get(pair, [])
            if not edges_here:
                # No synapse between the two clusters at all. Floor at
                # BRIDGE_CENTROID_FLOOR — below this they don't really
                # overlap and a forced bridge would feel synthetic.
                if sim < BRIDGE_CENTROID_FLOOR:
                    continue
                candidates.append((sim + 0.05, a, b))  # priority bonus for no-link
                continue
            # Thin-link path: the strongest cross-synapse between the
            # two clusters is below BRIDGE_THIN_LINK_STRONG_FLOOR — a
            # real but fragile bridge that a connector note would
            # substantially reinforce.
            if (
                max(edges_here) < BRIDGE_THIN_LINK_STRONG_FLOOR
                and sim >= BRIDGE_THIN_LINK_CENTROID
            ):
                candidates.append((sim, a, b))
    candidates.sort(key=lambda x: x[0], reverse=True)
    candidates = candidates[:per_kind]

    sparks: list[Spark] = []
    for sim, a, b in candidates:
        meta_a = community_meta[a]
        meta_b = community_meta[b]
        cent_a = cluster_centralities[a]
        cent_b = cluster_centralities[b]
        # Pick the highest-centrality member of each side as the anchor.
        anchor_a = max(cluster_members[a], key=lambda m: cent_a.get(m, 0.0))
        anchor_b = max(cluster_members[b], key=lambda m: cent_b.get(m, 0.0))
        na = notes_lookup[anchor_a]
        nb = notes_lookup[anchor_b]
        sentence_a = _first_sentence(na.get("body", ""))
        sentence_b = _first_sentence(nb.get("body", ""))
        title = f"{meta_a['name']} ↔ {meta_b['name']}"
        body = (
            f"Bridge — connecting **{meta_a['name']}** and **{meta_b['name']}** "
            f"(centroid cosine {sim:.2f}).\n\n"
            f"From {meta_a['name']} side, anchored by *{na.get('title', '?')}*: "
            f"\"{sentence_a}\"\n\n"
            f"From {meta_b['name']} side, anchored by *{nb.get('title', '?')}*: "
            f"\"{sentence_b}\"\n\n"
            f"The two topics aren't yet connected by a synapse, but their "
            f"centroids overlap enough that one connecting thought would form "
            f"a real edge. Open question: what is the *one* idea you hold that "
            f"belongs to both?"
        )
        tag_seed = _distinctive_terms(
            f"{na.get('body', '')} {nb.get('body', '')}", universe_tf, limit=4
        )
        tags = _build_tags(
            tag_seed,
            list(dict.fromkeys(meta_a.get("terms", []) + meta_b.get("terms", []))),
        )
        sparks.append(
            Spark(
                id=_stable_id(["bridge", str(min(a, b)), str(max(a, b))]),
                kind="bridge",
                priority=round(0.55 + 0.25 * min((sim - BRIDGE_CENTROID_FLOOR) * 4, 1.0), 4),
                title=title,
                body=body,
                tags=tags,
                rationale=(
                    f"{meta_a['name']} and {meta_b['name']} sit close in "
                    f"embedding space but have no synapse — a connecting note "
                    f"would form an edge and open cross-cluster traffic."
                ),
                headline=f"Bridge {meta_a['name']} ↔ {meta_b['name']}",
                cited_evidence=[
                    CitedEvidence(
                        note_id=anchor_a,
                        title=na.get("title", "?"),
                        snippet=sentence_a,
                        cluster_id=a,
                        cluster_name=meta_a.get("name"),
                        cluster_color=meta_a.get("color"),
                    ),
                    CitedEvidence(
                        note_id=anchor_b,
                        title=nb.get("title", "?"),
                        snippet=sentence_b,
                        cluster_id=b,
                        cluster_name=meta_b.get("name"),
                        cluster_color=meta_b.get("color"),
                    ),
                ],
                bridge_cluster_a_id=a,
                bridge_cluster_a_name=meta_a.get("name"),
                bridge_cluster_a_color=meta_a.get("color"),
                bridge_cluster_b_id=b,
                bridge_cluster_b_name=meta_b.get("name"),
                bridge_cluster_b_color=meta_b.get("color"),
                bridge_centroid_cosine=round(sim, 4),
            )
        )
    return sparks


# -------------------------------------------------------------- distill


def _distill_sparks(
    *,
    cluster_members: dict[int, list[int]],
    cluster_centralities: dict[int, dict[int, float]],
    community_meta: dict[int, dict],
    centroids: dict[int, tuple[float, ...]],
    weights: dict[int, float],
    embeddings: dict[int, tuple[float, ...]],
    notes_lookup: dict[int, dict],
    universe_tf: Counter,
    per_kind: int,
) -> list[Spark]:
    candidates: list[tuple[float, int]] = []
    for cid, members in cluster_members.items():
        if len(members) < DISTILL_MIN_SIZE:
            continue
        max_weight = max((weights.get(m, 0.0) for m in members), default=0.0)
        centrality = cluster_centralities.get(cid, {})
        mean_cent = (
            sum(centrality.get(m, 0.0) for m in members) / len(members)
            if members
            else 0.0
        )
        # Primary trigger — un-anchored cluster.
        un_anchored = max_weight < DISTILL_HUB_CEILING
        # Secondary trigger — large + low-cohesion cluster that's begging
        # to be split *or* unified by a synthesis note.
        large_loose = (
            len(members) >= DISTILL_LARGE_SIZE
            and mean_cent < DISTILL_LARGE_COHESION_CEILING
        )
        if not (un_anchored or large_loose):
            continue
        # Use mean centrality as a tie-breaker: tighter clusters are
        # better distill targets because the synthesis sentence will
        # actually be coherent. For large_loose we want size to dominate.
        if un_anchored:
            score = mean_cent * math.log(1 + len(members))
        else:
            score = math.log(1 + len(members)) * (1.0 - mean_cent)
        candidates.append((score, cid))

    candidates.sort(key=lambda x: x[0], reverse=True)
    candidates = candidates[:per_kind]
    sparks: list[Spark] = []
    for score, cid in candidates:
        members = cluster_members[cid]
        centrality = cluster_centralities[cid]
        meta = community_meta[cid]
        top_members = sorted(
            members, key=lambda m: centrality.get(m, 0.0), reverse=True
        )[:3]
        cited: list[CitedEvidence] = []
        sentences: list[str] = []
        for m in top_members:
            note = notes_lookup[m]
            sent = _first_sentence(note.get("body", ""))
            sentences.append(f"- {sent} *(from “{note.get('title', '?')}”)*")
            cited.append(
                CitedEvidence(
                    note_id=m,
                    title=note.get("title", "?"),
                    snippet=sent,
                    cluster_id=cid,
                    cluster_name=meta.get("name"),
                    cluster_color=meta.get("color"),
                )
            )
        title = f"What {meta['name']} really is"
        body = (
            f"Distill — {len(members)} notes form a real {meta['name']} "
            f"cluster but none of them act as the anchor. The clearest "
            f"three observations so far:\n\n"
            + "\n".join(sentences)
            + (
                f"\n\nA single synthesis sentence would pull the cluster "
                f"into focus and become the note everything else here "
                f"points at. Distinctive terms in the cluster: "
                f"{', '.join(meta.get('terms', [])[:5])}."
            )
        )
        tag_seed = _distinctive_terms(
            "\n".join(
                f"{notes_lookup[m].get('title', '')}\n{notes_lookup[m].get('body', '')}"
                for m in top_members
            ),
            universe_tf,
            limit=4,
        )
        tags = _build_tags(tag_seed, meta.get("terms", []))
        sparks.append(
            Spark(
                id=_stable_id(["distill", str(cid)]),
                kind="distill",
                priority=round(0.50 + 0.20 * min(score, 1.0), 4),
                title=title,
                body=body,
                tags=tags,
                rationale=(
                    f"{meta['name']} has {len(members)} notes but no central "
                    f"hub note — writing a synthesis would anchor the cluster."
                ),
                headline=f"Anchor {meta['name']}",
                cited_evidence=cited,
            )
        )
    return sparks


# --------------------------------------------------------------- counter


def _has_negation(text: str) -> bool:
    tokens = _terms(text)
    if any(t in _NEGATION_MARKERS for t in tokens):
        return True
    token_set = set(tokens)
    for a, b in _ANTONYM_PAIRS:
        if a in token_set and b in token_set:
            return True
    return False


def _counter_sparks(
    *,
    cluster_members: dict[int, list[int]],
    cluster_centralities: dict[int, dict[int, float]],
    community_meta: dict[int, dict],
    centroids: dict[int, tuple[float, ...]],
    weights: dict[int, float],
    embeddings: dict[int, tuple[float, ...]],
    notes_lookup: dict[int, dict],
    cluster_text: dict[int, str],
    universe_tf: Counter,
    per_kind: int,
) -> list[Spark]:
    candidates: list[tuple[float, int, int]] = []  # (weight, cluster_id, hub_id)
    for cid, members in cluster_members.items():
        if len(members) < 3:
            continue
        if _has_negation(cluster_text.get(cid, "")):
            continue
        # Hub = highest-weight member in this cluster.
        hub = max(members, key=lambda m: weights.get(m, 0.0))
        w = weights.get(hub, 0.0)
        if w < COUNTER_HUB_WEIGHT:
            continue
        candidates.append((w, cid, hub))

    candidates.sort(key=lambda x: x[0], reverse=True)
    candidates = candidates[:per_kind]
    sparks: list[Spark] = []
    for w, cid, hub in candidates:
        meta = community_meta[cid]
        note = notes_lookup[hub]
        sent = _first_sentence(note.get("body", ""))
        title = f"Against {note.get('title', meta['name'])}"
        body = (
            f"Counter — *{note.get('title', '?')}* anchors **{meta['name']}** "
            f"with weight {w:.2f} but no opposing-stance note exists in "
            f"this cluster.\n\n"
            f"Their claim: \"{sent}\"\n\n"
            f"Where could this break? Cost they're not paying. Constraint "
            f"they're assuming away. Edge case they haven't met. Counter-"
            f"example from a different domain. Adversarial framing where "
            f"their advice fails. A second voice — even a half-formed one "
            f"— would let the cluster carry its own dialectic."
        )
        cited = [
            CitedEvidence(
                note_id=hub,
                title=note.get("title", "?"),
                snippet=sent,
                cluster_id=cid,
                cluster_name=meta.get("name"),
                cluster_color=meta.get("color"),
            )
        ]
        tag_seed = _distinctive_terms(note.get("body", ""), universe_tf, limit=3)
        tags = _build_tags(
            ["counter"] + tag_seed, meta.get("terms", [])
        )
        sparks.append(
            Spark(
                id=_stable_id(["counter", str(cid), str(hub)]),
                kind="counter",
                priority=round(0.45 + 0.30 * min(w, 1.0), 4),
                title=title,
                body=body,
                tags=tags,
                rationale=(
                    f"Hub note '{note.get('title', '?')}' anchors "
                    f"{meta['name']} but the cluster has no opposing "
                    f"voice — an explicit counter strengthens the topic."
                ),
                headline=f"Counter {meta['name']}",
                cited_evidence=cited,
            )
        )
    return sparks


# -------------------------------------------------------------- frontier


def _frontier_sparks(
    *,
    cluster_members: dict[int, list[int]],
    community_meta: dict[int, dict],
    centroids: dict[int, tuple[float, ...]],
    embeddings: dict[int, tuple[float, ...]],
    notes_lookup: dict[int, dict],
    cluster_age: dict[int, dict],
    cluster_global_tf: Counter,
    universe_tf: Counter,
    per_kind: int,
) -> list[Spark]:
    candidates: list[tuple[float, int, int, str]] = []
    for cid, age in cluster_age.items():
        nid = age.get("newest_note_id")
        if nid is None:
            continue
        days = age.get("newest_age_days")
        if days is None or days > FRONTIER_WINDOW_DAYS:
            continue
        if len(cluster_members.get(cid, [])) < 2:
            continue
        note = notes_lookup.get(nid)
        if not note:
            continue
        # Frontier term = appears in this note >= FRONTIER_MIN_OCCURRENCES
        # AND appears nowhere else in the entire library.
        local_counts = Counter(_terms(f"{note.get('title', '')} {note.get('body', '')}"))
        per_cluster = 0
        for term, count in local_counts.most_common(50):
            if per_cluster >= FRONTIER_PER_CLUSTER:
                break
            if count < FRONTIER_MIN_OCCURRENCES:
                continue
            if universe_tf.get(term, 0) > count:
                # Appears in other notes too — not a frontier observation.
                continue
            if len(term) < FRONTIER_MIN_LEN:
                continue
            # Skip stopwordy fragments and pure-numeric tokens that
            # squeaked through (years, percentages, etc).
            if term in _STOP or term.isdigit():
                continue
            # Skip terms that are *just* a stop fragment glued to a
            # bigram piece — common in early-cluster filler.
            if term.replace("-", "").isdigit():
                continue
            # Skip adverbs ending in -ly; concept-shaped tokens almost
            # never carry an -ly ending and the false positives
            # ("comfortably", "quietly") are pure filler.
            if term.endswith("ly") and len(term) <= 12:
                continue
            # Recency bonus: fresher notes get higher priority.
            recency = max(0.0, 1.0 - (days / FRONTIER_WINDOW_DAYS))
            # Distinctiveness bonus: longer/more-specific terms win.
            specificity = min(1.0, (len(term) - 4) * 0.15)
            score = recency * math.log(1 + count) * (1.0 + specificity)
            candidates.append((score, cid, nid, term))
            per_cluster += 1

    candidates.sort(key=lambda x: x[0], reverse=True)
    candidates = candidates[:per_kind]
    sparks: list[Spark] = []
    for score, cid, nid, term in candidates:
        meta = community_meta[cid]
        note = notes_lookup[nid]
        sent = _first_sentence(note.get("body", ""))
        title = f"On “{term}”"
        body = (
            f"Frontier — the term **{term}** appears in *{note.get('title', '?')}* "
            f"({meta['name']} cluster) but nowhere else in your second "
            f"brain. That's a concept you've named once and haven't "
            f"developed.\n\n"
            f"Original context: \"{sent}\"\n\n"
            f"A focused definition-note would let the term anchor its "
            f"own neighborhood. What does it mean precisely? What is it "
            f"*not*? Where else in your thinking does it apply once you "
            f"give it a vocabulary?"
        )
        cited = [
            CitedEvidence(
                note_id=nid,
                title=note.get("title", "?"),
                snippet=sent,
                cluster_id=cid,
                cluster_name=meta.get("name"),
                cluster_color=meta.get("color"),
            )
        ]
        tag_seed = _distinctive_terms(note.get("body", ""), universe_tf, limit=3)
        tags = _build_tags([term] + tag_seed, meta.get("terms", []))
        sparks.append(
            Spark(
                id=_stable_id(["frontier", str(cid), term]),
                kind="frontier",
                priority=round(0.40 + 0.25 * min(score, 1.0), 4),
                title=title,
                body=body,
                tags=tags,
                rationale=(
                    f"'{term}' is a frontier concept — surfaces in one note "
                    f"({meta['name']} cluster) and nowhere else."
                ),
                headline=f"Define '{term}'",
                cited_evidence=cited,
            )
        )
    return sparks


# --------------------------------------------------------------- revive


def _revive_sparks(
    *,
    cluster_members: dict[int, list[int]],
    cluster_centralities: dict[int, dict[int, float]],
    community_meta: dict[int, dict],
    centroids: dict[int, tuple[float, ...]],
    embeddings: dict[int, tuple[float, ...]],
    notes_lookup: dict[int, dict],
    cluster_age: dict[int, dict],
    universe_tf: Counter,
    per_kind: int,
) -> list[Spark]:
    candidates: list[tuple[float, int, int]] = []  # (dormancy_days, cluster_id, anchor_id)
    for cid, members in cluster_members.items():
        if len(members) < 3:
            continue
        centrality = cluster_centralities.get(cid, {})
        if not centrality:
            continue
        cohesion = sum(centrality.values()) / max(1, len(centrality))
        if cohesion < REVIVE_COHESION_FLOOR:
            continue
        age = cluster_age.get(cid, {})
        # Activity = share of members touched/created within REVIVE_DORMANT_DAYS.
        recent = 0
        for m in members:
            note = notes_lookup[m]
            created = _parse_iso(note.get("created_at"))
            touched = _parse_iso(store.last_seen_map().get(m))
            event = max(created or _EPOCH, touched or _EPOCH)
            if event != _EPOCH:
                days = _days_between(event, datetime.now(timezone.utc))
                if days <= REVIVE_DORMANT_DAYS:
                    recent += 1
        activity = recent / len(members)
        if activity > REVIVE_ACTIVITY_CEILING:
            continue
        # Dormancy bonus: the longer it's been quiet, the higher priority.
        dormant_days = age.get("last_touched_days")
        if dormant_days is None or dormant_days < REVIVE_DORMANT_DAYS:
            continue
        anchor = max(members, key=lambda m: centrality.get(m, 0.0))
        candidates.append((dormant_days, cid, anchor))

    candidates.sort(key=lambda x: x[0], reverse=True)
    candidates = candidates[:per_kind]
    sparks: list[Spark] = []
    for dormant_days, cid, anchor in candidates:
        meta = community_meta[cid]
        members = cluster_members[cid]
        note = notes_lookup[anchor]
        sent = _first_sentence(note.get("body", ""))
        title = f"Returning to {meta['name']}"
        body = (
            f"Revive — {meta['name']} has been dormant for {dormant_days}d "
            f"but holds {len(members)} cohesive notes. The anchor still "
            f"reads cleanly:\n\n"
            f"\"{sent}\" *(from “{note.get('title', '?')}”)*\n\n"
            f"Re-read the cluster with fresh eyes. What do you now believe "
            f"differently? What experience since then either confirmed or "
            f"complicated this position? A short re-entry note keeps the "
            f"topic alive without forcing a full rebuild."
        )
        cited = [
            CitedEvidence(
                note_id=anchor,
                title=note.get("title", "?"),
                snippet=sent,
                cluster_id=cid,
                cluster_name=meta.get("name"),
                cluster_color=meta.get("color"),
            )
        ]
        tag_seed = _distinctive_terms(note.get("body", ""), universe_tf, limit=3)
        tags = _build_tags(["revisit"] + tag_seed, meta.get("terms", []))
        sparks.append(
            Spark(
                id=_stable_id(["revive", str(cid)]),
                kind="revive",
                priority=round(0.35 + 0.20 * min(dormant_days / 180.0, 1.0), 4),
                title=title,
                body=body,
                tags=tags,
                rationale=(
                    f"{meta['name']} cohesive but cooled "
                    f"({dormant_days}d dormant) — a small re-entry keeps "
                    f"the topic alive."
                ),
                headline=f"Revive {meta['name']}",
                cited_evidence=cited,
            )
        )
    return sparks


# ------------------------------------------------------------ markdown


_KIND_LABEL = {
    "bridge": "Bridge",
    "distill": "Distill",
    "counter": "Counter",
    "frontier": "Frontier",
    "revive": "Revive",
}


def to_markdown(r: SparkReport) -> str:
    out: list[str] = []
    out.append(f"# Spark — {r.generated_at[:10]}")
    out.append("")
    out.append(
        f"_{r.total_notes} notes · {r.total_clusters} clusters · "
        f"{len(r.sparks)} sparks queued · mean predicted synapses "
        f"{r.summary.get('mean_predicted_synapses', 0.0):.2f}_"
    )
    out.append("")
    out.append("| Kind | Count |")
    out.append("|---|---:|")
    for kind in SPARK_KINDS:
        out.append(f"| {_KIND_LABEL[kind]} | {r.summary.get(kind + '_count', 0)} |")
    out.append("")

    for kind in SPARK_KINDS:
        members = [s for s in r.sparks if s.kind == kind]
        if not members:
            continue
        out.append(f"## {_KIND_LABEL[kind]} sparks")
        out.append("")
        for sp in members:
            out.append(f"### {sp.title}")
            out.append("")
            out.append(f"_{sp.rationale}_")
            out.append("")
            out.append(sp.body)
            out.append("")
            if sp.tags:
                out.append(f"**Tags**: {', '.join('`' + t + '`' for t in sp.tags)}")
                out.append("")
            if sp.predicted_cluster_name:
                out.append(
                    f"**Predicted cluster**: {sp.predicted_cluster_name} "
                    f"(strength {sp.predicted_cluster_strength:.2f}, "
                    f"{sp.expected_synapse_count} predicted synapse"
                    f"{'s' if sp.expected_synapse_count != 1 else ''})"
                )
                out.append("")
            if sp.predicted_synapses:
                out.append("**Would synapse to**:")
                for p in sp.predicted_synapses:
                    out.append(f"- {p.title} (cosine {p.strength:.2f})")
                out.append("")
            if sp.cited_evidence:
                out.append("**Cites**:")
                for ev in sp.cited_evidence:
                    cluster_bit = (
                        f" — _{ev.cluster_name}_" if ev.cluster_name else ""
                    )
                    out.append(f"- *{ev.title}*{cluster_bit}: {ev.snippet}")
                out.append("")
    return "\n".join(out).rstrip() + "\n"


# ----------------------------------------------------------- serializer


def _evidence_to_dict(ev: CitedEvidence) -> dict:
    return {
        "note_id": ev.note_id,
        "title": ev.title,
        "snippet": ev.snippet,
        "cluster_id": ev.cluster_id,
        "cluster_name": ev.cluster_name,
        "cluster_color": ev.cluster_color,
    }


def _predicted_to_dict(p: PredictedSynapse) -> dict:
    return {"note_id": p.note_id, "title": p.title, "strength": p.strength}


def spark_to_dict(sp: Spark) -> dict:
    return {
        "id": sp.id,
        "kind": sp.kind,
        "priority": round(sp.priority, 4),
        "title": sp.title,
        "body": sp.body,
        "tags": sp.tags,
        "rationale": sp.rationale,
        "headline": sp.headline,
        "cited_evidence": [_evidence_to_dict(e) for e in sp.cited_evidence],
        "predicted_cluster_id": sp.predicted_cluster_id,
        "predicted_cluster_name": sp.predicted_cluster_name,
        "predicted_cluster_color": sp.predicted_cluster_color,
        "predicted_cluster_strength": sp.predicted_cluster_strength,
        "predicted_synapses": [_predicted_to_dict(p) for p in sp.predicted_synapses],
        "expected_synapse_count": sp.expected_synapse_count,
        "bridge_cluster_a_id": sp.bridge_cluster_a_id,
        "bridge_cluster_a_name": sp.bridge_cluster_a_name,
        "bridge_cluster_a_color": sp.bridge_cluster_a_color,
        "bridge_cluster_b_id": sp.bridge_cluster_b_id,
        "bridge_cluster_b_name": sp.bridge_cluster_b_name,
        "bridge_cluster_b_color": sp.bridge_cluster_b_color,
        "bridge_centroid_cosine": sp.bridge_centroid_cosine,
    }


def serialize(r: SparkReport) -> dict:
    return {
        "generated_at": r.generated_at,
        "total_notes": r.total_notes,
        "total_clusters": r.total_clusters,
        "sparks": [spark_to_dict(s) for s in r.sparks],
        "summary": r.summary,
    }
