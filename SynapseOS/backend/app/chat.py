"""Chat-with-your-graph — graph-aware RAG over the synapse graph.

Most "RAG over notes" stops at vector-search → stuff-into-prompt. SynapseOS
already builds a graph from those embeddings, so the retriever can do
something better:

    1. **Seed.**   Top-`k` semantic hits become anchor points.
    2. **Expand.** For each seed, fan out one hop along synapses (the
       same edges the user *sees* in the canvas), so adjacent thoughts
       come along even when their wording doesn't match the query.
    3. **Anchor.** Optionally include the highest-weight note in each
       seed's community as a "topic anchor" — useful for queries that
       sit at the edge of a cluster.
    4. **Answer.** Default extractive answer (zero-dep) builds a bullet
       list of the highest-overlap sentences from the citations, with
       inline ``[#N]`` markers. If ``SYNAPSE_LLM_KEY`` is set, we hand
       the same context to a small LLM with a strict citation contract.

The retrieval *traversal* is returned alongside the citations so the
frontend can highlight the exact synapses that contributed — RAG with
its receipts visible.
"""

from __future__ import annotations

import os
import re
import time
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from typing import Iterable, Literal

from . import community as community_mod
from . import store, synapse
from .embed import cosine, embed
from .llm import LLMResult, call_llm, llm_available, llm_provider_label

DEFAULT_K_SEED = 4
DEFAULT_HOPS = 1
# A second-tier threshold for synapse expansion: if the user's graph
# τ is high (sparse, opinionated graph) we still want neighborhood-RAG to
# pull *some* adjacent context, just don't go below this floor.
EXPANSION_FLOOR = 0.10
MAX_CITATIONS = 12
SNIPPET_CHARS = 220
DEFAULT_LLM_MODEL_ANTHROPIC = "claude-haiku-4-5-20251001"
DEFAULT_LLM_MODEL_OPENAI = "gpt-4o-mini"

Role = Literal["seed", "synapse", "community"]


@dataclass
class Citation:
    note_id: int
    title: str
    snippet: str
    score: float
    role: Role
    via_seed_id: int | None
    via_strength: float


@dataclass
class Expansion:
    src: int  # the seed (or community anchor)
    dst: int  # the retrieved note
    strength: float
    kind: Role


@dataclass
class Traversal:
    seeds: list[int] = field(default_factory=list)
    expansions: list[Expansion] = field(default_factory=list)


@dataclass
class ChatResult:
    query: str
    answer: str
    citations: list[Citation]
    traversal: Traversal
    model: str
    mode_used: Literal["extractive", "llm"]
    latency_ms: int
    llm_available: bool
    notice: str | None = None


# ----------------------------------------------------------- retrieval


def _snippet(body: str, query_terms: set[str], max_chars: int = SNIPPET_CHARS) -> str:
    """Pull a short snippet from `body`, biased toward sentences that
    overlap with the query. Falls back to the head of the note."""
    sentences = _split_sentences(body)
    if not sentences:
        return body[:max_chars].strip()

    if query_terms:
        scored = sorted(
            sentences,
            key=lambda s: -_term_hits(s, query_terms),
        )
        best = scored[0] if _term_hits(scored[0], query_terms) > 0 else sentences[0]
    else:
        best = sentences[0]

    if len(best) <= max_chars:
        return best.strip()
    # Try to cut at a word boundary.
    cut = best[:max_chars]
    sp = cut.rfind(" ")
    if sp > 60:
        cut = cut[:sp]
    return cut.strip() + "…"


def _split_sentences(body: str) -> list[str]:
    body = body.strip()
    if not body:
        return []
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z\"\(])", body)
    return [p.strip() for p in parts if p.strip()]


_QUERY_TOKEN = re.compile(r"[a-z][a-z0-9\-]{2,}")
_QUERY_STOP = frozenset(
    """what whats the a an of for to in on at by from with as is are was were be been being
    do does did how why when where which who whom this that these those it its they them
    their there here we you i me my our your his her not no yes can could should would may
    might must will shall just only also more most less few many very too into onto out up
    down off over under between among per about across after before again any all some each
    every both either neither one two three first second new old same such other another own
    enough still even ever never always often sometimes maybe perhaps way ways thing things
    stuff like really kinda sorta etc vs via per tell explain show find list summarize
    """.split()
)


def _query_terms(query: str) -> set[str]:
    toks = _QUERY_TOKEN.findall(query.lower())
    out: set[str] = set()
    for t in toks:
        if t in _QUERY_STOP:
            continue
        out.add(t)
        # Hyphenated tokens (e.g. "retrieval-augmented") rarely match
        # body prose verbatim; also index their unigram parts so a query
        # for "retrieval-augmented generation" still matches a note that
        # only says "retrieval".
        if "-" in t:
            for part in t.split("-"):
                if len(part) >= 3 and part not in _QUERY_STOP:
                    out.add(part)
    return out


def _term_hits(text: str, terms: set[str]) -> int:
    if not terms:
        return 0
    lower = text.lower()
    return sum(1 for t in terms if t in lower)


def retrieve(
    query: str,
    k_seed: int = DEFAULT_K_SEED,
    hops: int = DEFAULT_HOPS,
    threshold: float | None = None,
    top_k: int | None = None,
    include_community_anchors: bool = True,
) -> tuple[list[Citation], Traversal]:
    """Graph-aware retrieval. Returns (citations, traversal).

    `threshold` and `top_k` mirror `/graph` semantics — the retriever
    operates on the *same* synapse graph the user sees on the canvas, so
    citations always correspond to visible structure.
    """
    if not query.strip():
        return [], Traversal()

    th = synapse.DEFAULT_THRESHOLD if threshold is None else threshold
    tk = synapse.DEFAULT_TOP_K if top_k is None else top_k

    notes = store.all_notes()
    if not notes:
        return [], Traversal()
    notes_by_id = {n["id"]: n for n in notes}
    embeddings_list = store.all_embeddings()
    embeddings = dict(embeddings_list)

    qv = embed(query)
    qterms = _query_terms(query)

    # 1. Seeds — top-k semantic hits.
    semantic_scores: list[tuple[int, float]] = []
    for nid, vec in embeddings_list:
        s = cosine(qv, vec)
        if s > 0:
            semantic_scores.append((nid, s))
    semantic_scores.sort(key=lambda x: x[1], reverse=True)
    seed_pairs = semantic_scores[: max(1, k_seed)]
    seed_ids = [nid for nid, _ in seed_pairs]
    seed_score: dict[int, float] = dict(seed_pairs)

    # 2. Build (or reuse) the synapse graph at the same params the canvas
    # uses, so visualization aligns with retrieval.
    g = synapse.compute_graph(threshold=th, top_k=tk)
    adj: dict[int, list[tuple[int, float]]] = defaultdict(list)
    for e in g.edges:
        adj[e["source"]].append((e["target"], e["strength"]))
        adj[e["target"]].append((e["source"], e["strength"]))

    # 3. Expand `hops` along synapses from each seed.
    citations_by_id: dict[int, Citation] = {}
    expansions: list[Expansion] = []

    for sid in seed_ids:
        n = notes_by_id.get(sid)
        if n is None:
            continue
        citations_by_id[sid] = Citation(
            note_id=sid,
            title=n["title"],
            snippet=_snippet(n["body"], qterms),
            score=round(seed_score.get(sid, 0.0), 4),
            role="seed",
            via_seed_id=None,
            via_strength=0.0,
        )

    if hops > 0:
        # Cheap BFS-ish expansion. We only support hops ∈ {1, 2}; deeper
        # traversal dilutes relevance fast.
        frontier = list(seed_ids)
        carried_strength: dict[int, float] = {sid: 1.0 for sid in seed_ids}
        carried_via: dict[int, int] = {sid: sid for sid in seed_ids}

        for hop in range(min(hops, 2)):
            next_frontier: list[int] = []
            decay = 0.85 ** (hop + 1)
            for u in frontier:
                u_strength = carried_strength.get(u, 1.0)
                u_via = carried_via.get(u, u)
                neighbors = sorted(adj[u], key=lambda x: x[1], reverse=True)
                # Cap fan-out per node to keep retrieval focused.
                for v, s in neighbors[:tk]:
                    if v == u_via:
                        continue
                    if s < EXPANSION_FLOOR:
                        continue
                    edge_score = s * u_strength * decay
                    cand = notes_by_id.get(v)
                    if cand is None:
                        continue
                    sem_boost = max(0.0, cosine(qv, embeddings[v])) * 0.4
                    composite = round(edge_score + sem_boost, 4)
                    existing = citations_by_id.get(v)
                    if existing is None:
                        citations_by_id[v] = Citation(
                            note_id=v,
                            title=cand["title"],
                            snippet=_snippet(cand["body"], qterms),
                            score=composite,
                            role="synapse",
                            via_seed_id=u_via,
                            via_strength=round(s, 4),
                        )
                        expansions.append(
                            Expansion(src=u, dst=v, strength=round(s, 4), kind="synapse")
                        )
                        next_frontier.append(v)
                        carried_strength[v] = edge_score
                        carried_via[v] = u_via
                    elif existing.role != "seed" and composite > existing.score:
                        existing.score = composite
                        existing.via_seed_id = u_via
                        existing.via_strength = round(s, 4)
            frontier = next_frontier

    # 4. Community anchors — for each seed, pull the highest-weight note
    # in its community (if any) as a topic anchor. Good for "what's this
    # area of my notes about?" queries.
    if include_community_anchors:
        comm_map = {n["id"]: n.get("community") for n in g.nodes}
        weight_of = {n["id"]: n.get("weight", 0.0) for n in g.nodes}
        # group node ids by community
        by_comm: dict[int, list[int]] = defaultdict(list)
        for nid, cid in comm_map.items():
            if cid is None:
                continue
            by_comm[cid].append(nid)

        seen_comms: set[int] = set()
        for sid in seed_ids:
            cid = comm_map.get(sid)
            if cid is None or cid in seen_comms:
                continue
            seen_comms.add(cid)
            members = by_comm.get(cid, [])
            ranked = sorted(members, key=lambda nid: weight_of.get(nid, 0.0), reverse=True)
            for v in ranked[:1]:
                if v == sid or v in citations_by_id:
                    continue
                cand = notes_by_id.get(v)
                if cand is None:
                    continue
                anchor_score = round(0.30 * weight_of.get(v, 0.0) + 0.10, 4)
                citations_by_id[v] = Citation(
                    note_id=v,
                    title=cand["title"],
                    snippet=_snippet(cand["body"], qterms),
                    score=anchor_score,
                    role="community",
                    via_seed_id=sid,
                    via_strength=0.0,
                )
                expansions.append(
                    Expansion(src=sid, dst=v, strength=0.0, kind="community")
                )

    # Rank citations: seeds always come first by their semantic score,
    # then synapse hits, then community anchors. Cap at MAX_CITATIONS so
    # the prompt + UI stay tractable.
    role_rank = {"seed": 0, "synapse": 1, "community": 2}
    ranked = sorted(
        citations_by_id.values(),
        key=lambda c: (role_rank[c.role], -c.score),
    )[:MAX_CITATIONS]

    traversal = Traversal(
        seeds=seed_ids,
        expansions=[e for e in expansions if e.dst in {c.note_id for c in ranked}],
    )
    return ranked, traversal


# ----------------------------------------------------------- answering


def extractive_answer(query: str, citations: list[Citation]) -> str:
    """Bullet-list answer built from the highest-overlap sentences in the
    citations. Honest by construction: every claim points at a source."""
    if not citations:
        return "I couldn't find anything in your notes about that yet."

    qterms = _query_terms(query)
    if not qterms:
        # No salvageable terms — show the top-3 seeds' first sentence.
        lines = []
        for i, c in enumerate(citations[:3], start=1):
            head = _split_sentences(c.snippet)
            lines.append(f"- {head[0] if head else c.snippet} [#{i}]")
        return (
            f"Your strongest matches for *{query.strip()}* :\n\n"
            + "\n".join(lines)
        )

    # Score sentences across all citations.
    scored: list[tuple[float, int, str]] = []  # (score, citation_index, sentence)
    for idx, c in enumerate(citations):
        sentences = _split_sentences(c.snippet) or [c.snippet]
        for sent in sentences:
            hits = _term_hits(sent, qterms)
            if hits == 0:
                continue
            # Higher score for earlier citations (semantic seeds beat
            # neighbours), more hits, shorter sentences (denser).
            length_norm = 1.0 + (len(sent) / 400.0)
            score = (hits * 1.4) / length_norm + (1.0 / (idx + 1)) * 0.6
            scored.append((score, idx, sent))

    if not scored:
        # No sentence-level lexical match, but semantic retrieval still
        # surfaced these as the strongest neighbours. Show them honestly
        # rather than declaring failure.
        lines = []
        for i, c in enumerate(citations[:4], start=1):
            head = _split_sentences(c.snippet)
            first = head[0] if head else c.snippet
            lines.append(f"- **{c.title}** — {first.rstrip('.').rstrip()} [#{i}]")
        return (
            "Your notes don't talk about that query in those words, but the "
            "closest matches in your graph are:\n\n" + "\n".join(lines)
        )

    scored.sort(key=lambda x: -x[0])
    # Pick up to 5 sentences, one per citation when possible.
    seen_idx: set[int] = set()
    primary: list[tuple[int, str]] = []
    runners: list[tuple[int, str]] = []
    for _, idx, sent in scored:
        if idx not in seen_idx:
            primary.append((idx, sent))
            seen_idx.add(idx)
        else:
            runners.append((idx, sent))
        if len(primary) >= 5:
            break
    out_lines = [primary]  # at least the diversified bullets
    chosen = primary[:]
    if len(chosen) < 5:
        chosen += runners[: 5 - len(chosen)]

    bullets = []
    for idx, sent in chosen:
        bullets.append(f"- {sent.rstrip('.').rstrip()} [#{idx + 1}]")
    return "\n".join(bullets)


def _llm_prompt(query: str, citations: list[Citation]) -> tuple[str, str]:
    """Return (system, user) prompts with strict citation contract."""
    system = (
        "You are SynapseOS' graph-aware research assistant. You answer ONLY "
        "from the user's notes provided as numbered context blocks. Every "
        "factual claim MUST end with an inline citation in the form [#N] "
        "matching the note number. If the notes don't contain the answer, "
        "say so plainly — do not invent. Keep answers under 120 words and "
        "use short bullet points when listing items."
    )
    blocks = []
    for i, c in enumerate(citations, start=1):
        role_tag = {"seed": "match", "synapse": "neighbor", "community": "anchor"}[c.role]
        blocks.append(f"[#{i}] ({role_tag}) {c.title}\n{c.snippet}")
    user = (
        f"Question: {query.strip()}\n\n"
        f"Notes:\n\n" + "\n\n".join(blocks) +
        "\n\nAnswer with inline [#N] citations."
    )
    return system, user


def llm_answer(query: str, citations: list[Citation]) -> tuple[str, str] | None:
    """Call the configured LLM. Returns (text, model_label) or None on
    failure. Errors are swallowed — the caller falls back to extractive."""
    if not citations:
        return None
    provider = os.getenv("SYNAPSE_LLM_PROVIDER", "anthropic").lower()
    key = os.getenv("SYNAPSE_LLM_KEY")
    if not key:
        return None
    if provider == "anthropic":
        model = os.getenv("SYNAPSE_LLM_MODEL", DEFAULT_LLM_MODEL_ANTHROPIC)
    elif provider == "openai":
        model = os.getenv("SYNAPSE_LLM_MODEL", DEFAULT_LLM_MODEL_OPENAI)
    else:
        return None
    system, user = _llm_prompt(query, citations)
    res: LLMResult | None = call_llm(provider, key, model, system, user, max_tokens=320)
    if res is None or not res.text.strip():
        return None
    return res.text.strip(), f"{provider}/{model}"


def answer(
    query: str,
    mode: Literal["auto", "extractive", "llm"] = "auto",
    k_seed: int = DEFAULT_K_SEED,
    hops: int = DEFAULT_HOPS,
    threshold: float | None = None,
    top_k: int | None = None,
    include_community_anchors: bool = True,
) -> ChatResult:
    """Top-level entry point. Mode resolution:

    - ``extractive``: never call an LLM, even if a key is configured.
    - ``llm``: try the LLM; fall back to extractive on any failure (with
      a notice so the user knows).
    - ``auto`` *(default)*: use LLM if a key is configured, else extractive.
    """
    t0 = time.time()
    citations, traversal = retrieve(
        query=query,
        k_seed=k_seed,
        hops=hops,
        threshold=threshold,
        top_k=top_k,
        include_community_anchors=include_community_anchors,
    )
    have_key = llm_available()

    used: Literal["extractive", "llm"] = "extractive"
    model_label = "extractive"
    notice: str | None = None
    text = ""

    want_llm = (mode == "llm") or (mode == "auto" and have_key)

    if want_llm:
        result = llm_answer(query, citations)
        if result is not None:
            text, model_label = result
            used = "llm"
        else:
            used = "extractive"
            text = extractive_answer(query, citations)
            if mode == "llm":
                notice = (
                    "LLM unavailable or call failed — fell back to extractive. "
                    "Set SYNAPSE_LLM_KEY (and optionally SYNAPSE_LLM_PROVIDER, "
                    "SYNAPSE_LLM_MODEL)."
                )
    else:
        used = "extractive"
        text = extractive_answer(query, citations)
        model_label = "extractive"

    latency_ms = int((time.time() - t0) * 1000)
    return ChatResult(
        query=query.strip(),
        answer=text,
        citations=citations,
        traversal=traversal,
        model=model_label if used == "llm" else "extractive",
        mode_used=used,
        latency_ms=latency_ms,
        llm_available=have_key,
        notice=notice,
    )


def serialize(result: ChatResult) -> dict:
    """Plain-dict shape ready to ship over JSON / pydantic-validate."""
    return {
        "query": result.query,
        "answer": result.answer,
        "citations": [asdict(c) for c in result.citations],
        "traversal": {
            "seeds": result.traversal.seeds,
            "expansions": [asdict(e) for e in result.traversal.expansions],
        },
        "model": result.model,
        "mode_used": result.mode_used,
        "latency_ms": result.latency_ms,
        "llm_available": result.llm_available,
        "llm_provider": llm_provider_label() if result.llm_available else None,
        "notice": result.notice,
    }
