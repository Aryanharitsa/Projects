"""Synthesis — auto-written topic briefings per cluster.

Day 9 made clusters *visible* and *named*. But a colored blob with a
one-word label still isn't knowledge — you still have to open every member
note to learn what the topic actually *says*. Synthesis closes that gap:
it turns a cluster into a readable, citable, exportable brief.

For a cluster ``c`` we compute, all extractively and deterministically:

  * **centroid** — the mean of the member embeddings (the topic's
    "center of mass"), L2-normalized so plain dot-product is cosine.
  * **cohesion** — mean ``cosine(member, centroid)`` ∈ [0, 1]. How tightly
    the cluster actually holds together. A loose cluster is a merge of two
    half-topics waiting to be split; a tight one is a real idea.
  * **overview** — the 2–3 most *representative* sentences across all
    members (highest cosine to the centroid, nudged by key-term coverage),
    stitched into prose and ordered by their source note's centrality.
    Each sentence keeps an inline ``[#N]`` citation to its source note.
  * **key claims** — the next-strongest representative sentences,
    diversified one-per-note, each cited.
  * **open threads** — member notes phrased as questions, plus
    *under-developed* members (thin body or zero intra-cluster synapses):
    the parts of the topic you haven't resolved or connected yet.
  * **bridges** — notes in *other* clusters with high cosine to this
    centroid that the synapse graph hasn't linked. Cross-pollination the
    graph is one τ-nudge away from drawing.

Everything above is pure stdlib. When ``SYNAPSE_LLM_KEY`` is set, the
overview is rewritten by a small LLM under a strict ``[#N]`` citation
contract; any failure silently falls back to the extractive overview, so
LLM availability never gates the feature.
"""

from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass, field

from . import community as community_mod
from . import store, synapse
from .embed import DIM, cosine, embed
from .llm import call_llm, llm_available, llm_provider_label

# Sentences shorter than this are fragments / list bullets — too thin to
# stand alone as a claim, so they're skipped during harvest.
MIN_SENTENCE_CHARS = 30
MAX_OVERVIEW_SENTENCES = 3
MAX_CLAIMS = 5
MAX_OPEN_THREADS = 4
MAX_BRIDGES = 4
# A note in another cluster needs at least this cosine to the centroid to
# count as a bridge candidate. Below it the "near-miss" is just noise.
BRIDGE_FLOOR = 0.16
# Two sentences whose embeddings exceed this cosine are near-duplicates;
# we keep only the higher-scoring one so the brief never repeats itself.
DEDUP_SIM = 0.86
# Bodies under this length are "under-developed" — a stub thought that the
# cluster would benefit from you fleshing out.
UNDERDEVELOPED_BODY_CHARS = 140

DEFAULT_LLM_MODEL_ANTHROPIC = "claude-haiku-4-5-20251001"
DEFAULT_LLM_MODEL_OPENAI = "gpt-4o-mini"

_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"\(])")
_TERM_TOKEN = re.compile(r"[a-z][a-z0-9\-]{2,}")


@dataclass
class DigestSource:
    ref: int  # 1-based citation index, stable for [#N] references
    note_id: int
    title: str
    centrality: float  # cosine to centroid, 0..1


@dataclass
class DigestClaim:
    text: str
    note_id: int
    ref: int


@dataclass
class OpenThread:
    note_id: int
    title: str
    text: str
    kind: str  # "question" | "underdeveloped"


@dataclass
class Bridge:
    note_id: int
    title: str
    cluster_id: int
    cluster_name: str
    cluster_color: str
    strength: float  # cosine to this cluster's centroid


@dataclass
class ClusterDigest:
    cluster_id: int
    name: str
    color: str
    size: int
    terms: list[str]
    cohesion: float
    overview: str
    claims: list[DigestClaim] = field(default_factory=list)
    open_threads: list[OpenThread] = field(default_factory=list)
    bridges: list[Bridge] = field(default_factory=list)
    sources: list[DigestSource] = field(default_factory=list)
    mode_used: str = "extractive"
    llm_available: bool = False
    llm_provider: str | None = None
    notice: str | None = None


# ----------------------------------------------------------------- helpers


def _split_sentences(body: str) -> list[str]:
    body = (body or "").strip()
    if not body:
        return []
    return [p.strip() for p in _SENT_SPLIT.split(body) if p.strip()]


def _centroid(vecs: list[tuple[float, ...]]) -> tuple[float, ...]:
    """Mean of `vecs`, L2-normalized. Empty → zero vector."""
    if not vecs:
        return tuple(0.0 for _ in range(DIM))
    dim = len(vecs[0])
    acc = [0.0] * dim
    for v in vecs:
        for i, x in enumerate(v):
            acc[i] += x
    n = float(len(vecs))
    mean = [x / n for x in acc]
    norm = math.sqrt(sum(x * x for x in mean))
    if norm == 0:
        return tuple(mean)
    inv = 1.0 / norm
    return tuple(x * inv for x in mean)


def _key_terms(name: str, terms: list[str]) -> set[str]:
    out: set[str] = set()
    for chunk in [name, *terms]:
        out.update(_TERM_TOKEN.findall((chunk or "").lower()))
    return out


def _ensure_period(text: str) -> str:
    text = text.rstrip()
    if text and text[-1] not in ".!?":
        return text + "."
    return text


def _select_sentences(
    cands: list[tuple[float, int, str, tuple[float, ...]]],
    limit: int,
    used_vecs: list[tuple[float, ...]],
    exclude: set[str],
) -> list[tuple[int, str, tuple[float, ...]]]:
    """Pick up to `limit` sentences, preferring distinct source notes and
    skipping near-duplicates of anything already chosen.

    Two passes: the first takes one sentence per not-yet-seen note so the
    selection spreads across the cluster; the second backfills from the
    leftovers when there aren't enough distinct notes.
    """
    chosen: list[tuple[int, str, tuple[float, ...]]] = []
    chosen_notes: set[int] = set()
    chosen_sents: set[str] = set()

    def _is_dup(sv: tuple[float, ...]) -> bool:
        return any(cosine(sv, uv) > DEDUP_SIM for uv in used_vecs)

    for _, m, s, sv in cands:
        if len(chosen) >= limit:
            break
        if s in exclude or s in chosen_sents or m in chosen_notes or _is_dup(sv):
            continue
        chosen.append((m, s, sv))
        chosen_notes.add(m)
        chosen_sents.add(s)
        used_vecs.append(sv)

    if len(chosen) < limit:
        for _, m, s, sv in cands:
            if len(chosen) >= limit:
                break
            if s in exclude or s in chosen_sents or _is_dup(sv):
                continue
            chosen.append((m, s, sv))
            chosen_sents.add(s)
            used_vecs.append(sv)

    return chosen


# ----------------------------------------------------------------- engine


def cluster_digest(
    cluster_id: int,
    threshold: float | None = None,
    top_k: int | None = None,
    mode: str = "auto",
) -> ClusterDigest | None:
    """Build a topic briefing for one cluster. Returns ``None`` if the
    cluster id doesn't exist at the given ``(threshold, top_k)``."""
    th = synapse.DEFAULT_THRESHOLD if threshold is None else threshold
    tk = synapse.DEFAULT_TOP_K if top_k is None else top_k

    g = synapse.compute_graph(threshold=th, top_k=tk)
    nodes_by_id = {n["id"]: n for n in g.nodes}
    cmap = {n["id"]: n.get("community", 0) for n in g.nodes}
    built = community_mod.build_communities(cmap, nodes_by_id)
    comm = next((c for c in built if c.id == cluster_id), None)
    if comm is None:
        return None

    embeddings = dict(store.all_embeddings())
    member_ids = [m for m in comm.member_ids if m in embeddings and m in nodes_by_id]
    if not member_ids:
        return None
    member_set = set(member_ids)

    centroid = _centroid([embeddings[m] for m in member_ids])
    centrality = {m: max(0.0, cosine(embeddings[m], centroid)) for m in member_ids}
    cohesion = round(sum(centrality.values()) / len(member_ids), 4)

    # Sources, ordered most-central first; ref number is the citation key.
    ordered = sorted(member_ids, key=lambda m: (-centrality[m], m))
    ref_of = {m: i + 1 for i, m in enumerate(ordered)}
    sources = [
        DigestSource(
            ref=ref_of[m],
            note_id=m,
            title=nodes_by_id[m]["title"],
            centrality=round(centrality[m], 4),
        )
        for m in ordered
    ]

    key_terms = _key_terms(comm.name, comm.terms)

    # Harvest candidate sentences across all members.
    cands: list[tuple[float, int, str, tuple[float, ...]]] = []
    for m in member_ids:
        body = nodes_by_id[m]["body"]
        for s in _split_sentences(body):
            if len(s) < MIN_SENTENCE_CHARS:
                continue
            sv = embed(s)
            rep = max(0.0, cosine(sv, centroid))
            term_hits = sum(1 for t in key_terms if t in s.lower())
            score = rep + 0.04 * term_hits + 0.02 * centrality[m]
            cands.append((score, m, s, sv))
    cands.sort(key=lambda x: (-x[0], x[1]))

    used_vecs: list[tuple[float, ...]] = []
    overview_pick = _select_sentences(cands, MAX_OVERVIEW_SENTENCES, used_vecs, exclude=set())
    overview_sents = {s for _, s, _ in overview_pick}
    claim_pick = _select_sentences(cands, MAX_CLAIMS, used_vecs, exclude=overview_sents)

    # Overview prose: order picked sentences by source centrality so it
    # reads from the topic's most-central thought outward.
    overview = _compose_overview(overview_pick, centrality, ref_of, nodes_by_id)

    claims = [
        DigestClaim(text=_ensure_period(s), note_id=m, ref=ref_of[m])
        for m, s, _ in claim_pick
    ]

    open_threads = _open_threads(member_ids, ordered, nodes_by_id, g.edges, member_set)
    bridges = _bridges(member_set, centroid, embeddings, nodes_by_id, cmap, built, g.edges)

    digest = ClusterDigest(
        cluster_id=cluster_id,
        name=comm.name,
        color=comm.color,
        size=comm.size,
        terms=list(comm.terms),
        cohesion=cohesion,
        overview=overview,
        claims=claims,
        open_threads=open_threads,
        bridges=bridges,
        sources=sources,
        mode_used="extractive",
        llm_available=llm_available(),
        llm_provider=llm_provider_label() if llm_available() else None,
        notice=None,
    )

    _maybe_llm_overview(digest, mode)
    return digest


def _compose_overview(
    picked: list[tuple[int, str, tuple[float, ...]]],
    centrality: dict[int, float],
    ref_of: dict[int, int],
    nodes_by_id: dict[int, dict],
) -> str:
    if not picked:
        # No sentence cleared the floor (e.g. every member is a stub).
        # Fall back to the most-central note's opening line so the brief
        # still says something honest.
        if ref_of:
            top = min(ref_of, key=lambda m: ref_of[m])
            body = (nodes_by_id[top]["body"] or "").strip()
            head = body[:200].rstrip()
            if head:
                return f"{_ensure_period(head)} [#{ref_of[top]}]"
        return ""
    ordered = sorted(picked, key=lambda c: (-centrality.get(c[0], 0.0), ref_of.get(c[0], 0)))
    parts = [f"{_ensure_period(s)} [#{ref_of[m]}]" for m, s, _ in ordered]
    return " ".join(parts)


def _open_threads(
    member_ids: list[int],
    ordered: list[int],
    nodes_by_id: dict[int, dict],
    edges: list[dict],
    member_set: set[int],
) -> list[OpenThread]:
    # Intra-cluster degree: edges with *both* endpoints inside the cluster.
    intra: dict[int, int] = {m: 0 for m in member_ids}
    for e in edges:
        u, v = e["source"], e["target"]
        if u in member_set and v in member_set:
            intra[u] = intra.get(u, 0) + 1
            intra[v] = intra.get(v, 0) + 1

    threads: list[OpenThread] = []
    claimed: set[int] = set()

    # Pass 1: explicit questions (title or body).
    for m in ordered:
        if len(threads) >= MAX_OPEN_THREADS:
            break
        note = nodes_by_id[m]
        title = note["title"]
        if title.rstrip().endswith("?"):
            threads.append(OpenThread(m, title, title, "question"))
            claimed.add(m)
            continue
        q = next(
            (s for s in _split_sentences(note["body"]) if s.rstrip().endswith("?") and len(s) >= 12),
            None,
        )
        if q:
            threads.append(OpenThread(m, title, q, "question"))
            claimed.add(m)

    # Pass 2: under-developed members (thin body or zero intra-cluster links).
    for m in ordered:
        if len(threads) >= MAX_OPEN_THREADS:
            break
        if m in claimed:
            continue
        note = nodes_by_id[m]
        body = (note["body"] or "").strip()
        thin = len(body) < UNDERDEVELOPED_BODY_CHARS
        unlinked = intra.get(m, 0) == 0 and len(member_ids) > 1
        if thin or unlinked:
            snippet = body[:160].rstrip()
            if len(body) > 160:
                snippet += "…"
            threads.append(OpenThread(m, note["title"], snippet or note["title"], "underdeveloped"))
            claimed.add(m)

    return threads


def _bridges(
    member_set: set[int],
    centroid: tuple[float, ...],
    embeddings: dict[int, tuple[float, ...]],
    nodes_by_id: dict[int, dict],
    cmap: dict[int, int],
    built: list[community_mod.Community],
    edges: list[dict],
) -> list[Bridge]:
    name_of = {c.id: c.name for c in built}
    # Notes already synapse-linked to the cluster aren't "bridges to draw"
    # — the graph already drew them.
    linked: set[int] = set()
    for e in edges:
        u, v = e["source"], e["target"]
        if u in member_set and v not in member_set:
            linked.add(v)
        elif v in member_set and u not in member_set:
            linked.add(u)

    out: list[Bridge] = []
    for nid, vec in embeddings.items():
        if nid in member_set or nid in linked or nid not in nodes_by_id:
            continue
        s = cosine(vec, centroid)
        if s < BRIDGE_FLOOR:
            continue
        ocid = cmap.get(nid, 0)
        out.append(
            Bridge(
                note_id=nid,
                title=nodes_by_id[nid]["title"],
                cluster_id=ocid,
                cluster_name=name_of.get(ocid, f"Cluster {ocid + 1}"),
                cluster_color=community_mod.color_for(ocid),
                strength=round(s, 4),
            )
        )
    out.sort(key=lambda b: b.strength, reverse=True)
    return out[:MAX_BRIDGES]


# ----------------------------------------------------------------- llm


def _maybe_llm_overview(digest: ClusterDigest, mode: str) -> None:
    """Rewrite the extractive overview with an LLM under a strict citation
    contract. Mutates `digest` in place. Any failure is swallowed and the
    extractive overview is kept."""
    want_llm = mode == "llm" or (mode == "auto" and llm_available())
    if not want_llm:
        return
    if not llm_available():
        if mode == "llm":
            digest.notice = (
                "LLM mode requested but no SYNAPSE_LLM_KEY configured — used extractive synthesis."
            )
        return
    if not digest.sources:
        return

    provider = os.getenv("SYNAPSE_LLM_PROVIDER", "anthropic").lower()
    key = os.getenv("SYNAPSE_LLM_KEY", "")
    model = os.getenv(
        "SYNAPSE_LLM_MODEL",
        DEFAULT_LLM_MODEL_ANTHROPIC if provider == "anthropic" else DEFAULT_LLM_MODEL_OPENAI,
    )
    system = (
        "You are SynapseOS' topic synthesizer. You write a tight synthesis of "
        "one cluster of a user's notes, using ONLY the numbered source "
        "material provided. Every sentence MUST end with an inline citation "
        "in the form [#N] matching a source number. Do not invent facts or "
        "cite numbers that don't appear. Write 2-3 sentences, under 80 words, "
        "plain declarative prose — no preamble, no bullet points."
    )
    lines = [f"Topic: {digest.name}"]
    if digest.terms:
        lines.append("Key terms: " + ", ".join(digest.terms))
    lines.append("\nSource material (cite by [#N]):")
    # Feed each source its strongest harvested sentence (falling back to the
    # title) so the model rewrites grounded material rather than free-associating.
    claim_by_ref = {c.ref: c.text for c in digest.claims}
    for src in digest.sources[:8]:
        sent = claim_by_ref.get(src.ref, src.title)
        lines.append(f"[#{src.ref}] {src.title} — {sent}")
    user = "\n".join(lines) + "\n\nWrite the synthesis now, with [#N] citations."

    res = call_llm(provider, key, model, system, user, max_tokens=240)
    if res is None or not res.text.strip():
        if mode == "llm":
            digest.notice = "LLM call failed — used extractive synthesis instead."
        return
    text = res.text.strip()
    # Keep the model honest: it must cite at least one real source ref.
    refs = {int(x) for x in re.findall(r"\[#(\d+)\]", text)}
    valid = {s.ref for s in digest.sources}
    if not refs or not (refs & valid):
        if mode == "llm":
            digest.notice = "LLM answer dropped its citations — used extractive synthesis instead."
        return
    digest.overview = text
    digest.mode_used = "llm"


# ----------------------------------------------------------------- export


def to_markdown(d: ClusterDigest) -> str:
    """Self-contained Markdown brief. Citations map to the Sources list at
    the bottom, so the export reads stand-alone outside SynapseOS."""
    pct = lambda x: f"{round(x * 100)}%"  # noqa: E731
    lines: list[str] = []
    lines.append(f"# {d.name} — topic synthesis")
    meta = f"{d.size} note{'s' if d.size != 1 else ''} · cohesion {pct(d.cohesion)}"
    if d.terms:
        meta += " · " + " · ".join(d.terms)
    lines.append(f"\n_{meta}_\n")

    if d.overview:
        lines.append("## Synthesis\n")
        lines.append(d.overview + "\n")

    if d.claims:
        lines.append("## Key claims\n")
        for c in d.claims:
            lines.append(f"- {c.text} [#{c.ref}]")
        lines.append("")

    if d.open_threads:
        lines.append("## Open threads\n")
        for t in d.open_threads:
            glyph = "?" if t.kind == "question" else "○"
            lines.append(f"- ({glyph}) {t.text} — *{t.title}*")
        lines.append("")

    if d.bridges:
        lines.append("## Bridges to other topics\n")
        for b in d.bridges:
            lines.append(f"- {b.title} → **{b.cluster_name}** · cosine {pct(b.strength)}")
        lines.append("")

    if d.sources:
        lines.append("## Sources\n")
        for s in d.sources:
            lines.append(f"{s.ref}. {s.title} ({pct(s.centrality)} central)")
        lines.append("")

    lines.append("---")
    lines.append("_Generated by SynapseOS · Synthesis._")
    return "\n".join(lines)


def serialize(d: ClusterDigest) -> dict:
    return {
        "cluster_id": d.cluster_id,
        "name": d.name,
        "color": d.color,
        "size": d.size,
        "terms": d.terms,
        "cohesion": d.cohesion,
        "overview": d.overview,
        "claims": [{"text": c.text, "note_id": c.note_id, "ref": c.ref} for c in d.claims],
        "open_threads": [
            {"note_id": t.note_id, "title": t.title, "text": t.text, "kind": t.kind}
            for t in d.open_threads
        ],
        "bridges": [
            {
                "note_id": b.note_id,
                "title": b.title,
                "cluster_id": b.cluster_id,
                "cluster_name": b.cluster_name,
                "cluster_color": b.cluster_color,
                "strength": b.strength,
            }
            for b in d.bridges
        ],
        "sources": [
            {"ref": s.ref, "note_id": s.note_id, "title": s.title, "centrality": s.centrality}
            for s in d.sources
        ],
        "mode_used": d.mode_used,
        "llm_available": d.llm_available,
        "llm_provider": d.llm_provider,
        "notice": d.notice,
    }
