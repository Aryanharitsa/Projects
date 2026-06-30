"""Compass — question-anchored lens & persistent research sessions.

Where every other SynapseOS surface is either *observational* (Atlas /
Pulse / Chronicle / Tensions / Echo / Synthesis) or *generative-writing*
(Spark, Atomize) — Compass is **generative-reading**.

The user pins one question they're actively researching. Compass
re-ranks the whole vault against that question, builds a coverage-
ordered reading queue, tracks which notes the user has actually
*engaged with for this question* (a per-question read marker, distinct
from the global ``last_seen_at``), grows a citation-stitched working
answer from those reads, and surfaces sub-themes plus the frontiers
that still need reading.

The chat surface answers one shot and forgets. A trail captures a path
you've already walked. Compass is the in-flight research session.

Physics
-------
1. **Relevance per note** = ``0.65·cosine + 0.25·lexical + 0.10·title``
   where:
     - ``cosine`` is dot of the question's hashed-trick embedding with
       the note's stored embedding (the same vector the synapse graph
       runs on, so the lens lives in the same space as the canvas).
     - ``lexical`` is a Jaccard of content-word sets between question
       and ``title + body`` — keeps relevance high on lexically-explicit
       matches that cosine alone would dilute.
     - ``title`` is a small bonus when ≥1 question content-word lands
       in the note title — title hits are disproportionately worth
       surfacing in a reading queue.
   Anything below ``RELEVANCE_FLOOR`` (0.10) is dropped from the lens.

2. **Best excerpt per note**. Body is sentence-split (same regex Echo
   uses), each sentence scored by word-overlap with the question, the
   highest-scoring sentence wins. Notes whose body has no qualifying
   sentence fall back to the first sentence so the card never renders
   empty.

3. **Information gain** = ``relevance · (read ? 0.30 : 1.00)``. A
   re-skim is worth something — you may re-engage to refresh — but
   priority drops sharply once a note is read so the queue actually
   moves forward.

4. **Coverage** = ``sum(relevance for read notes) / sum(relevance for
   all in-lens notes)``. Mass-weighted, not count-weighted: marking the
   top-1 most-relevant note read can take you from 0% → 35% if it
   dominates the relevance distribution. That's the right framing —
   you've answered the question, not "read 1/N notes".

5. **Working answer** = extractive stitch of the best excerpts from
   read notes, ordered by relevance, with ``[n]`` citations that the
   frontend resolves back to clickable note jumps. No LLM call — this
   surface is *honest* (every claim is verbatim from one of your
   notes) and *deterministic* (same reads ⇒ same answer).

6. **Sub-questions** = the top distinctive content-words across the
   lens's most-relevant slice (after stop-word + question-word filter),
   each carrying its own per-term coverage % so the user sees *which*
   sub-aspect they've already covered and which is still cold.

7. **Frontiers** = the top ``FRONTIERS_K`` un-read notes by info_gain.
   The "what to open next" panel — separate from the full queue so the
   user can decide quickly.

Pure stdlib. Re-uses ``embed.embed`` + ``embed.cosine`` so the lens
sits in the same vector space as the synapse graph.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable

from . import store
from .embed import cosine, embed

# ----------------------------------------------------------------- weights

W_COSINE = 0.65
W_LEXICAL = 0.25
W_TITLE = 0.10

# Notes below this composite relevance never enter the lens at all —
# saves the UI from rendering 30+ "barely-relevant" cards on every load.
# The frontiers panel and the coverage denominator both respect this
# floor so the math stays consistent. Tuned conservatively because the
# hash-trick embedder this project uses is itself conservative: real
# cosine numbers for "semantically related" pairs cluster around 0.10
# – 0.25, so the floor lives below that to keep the queue full enough
# to be useful but above pure noise (random word overlap).
RELEVANCE_FLOOR = 0.06

# Once a note is marked read for this question, its info_gain shrinks
# to 30% of its raw relevance. Not zero — you may revisit to refresh —
# but enough that the queue actually moves you toward un-read material.
READ_NOVELTY_FACTOR = 0.30

# How many candidates we surface in the frontiers panel ("next to
# read"). The full queue is unbounded; frontiers is the highlight reel.
FRONTIERS_K = 3

# Working-answer composition caps. Long answers stop being readable
# fast; we'd rather show fewer, higher-relevance fragments.
WORKING_ANSWER_MAX_CITATIONS = 6
WORKING_ANSWER_MAX_CHARS = 1400

# Sub-question term extraction. Compass tries to break the question
# into 3 distinctive sub-themes by counting content-words across the
# top-relevant slice (excluding the question's own words and a tiny
# stoplist) and picking the most informative N.
SUBQ_TOP_NOTES = 12
SUBQ_COUNT = 3
SUBQ_MIN_TERM_LEN = 5
SUBQ_MIN_OCCURRENCES = 2

# Title-hit bonus fires once if any question content-word appears in
# the note title (case-insensitive substring). We don't scale by hit
# count — that would let two-word matches dominate.

_WORD_RE = re.compile(r"[a-z0-9][a-z0-9'\-]*")
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"\(\[])")

# Reused across modules: a tiny function-word stoplist. Smaller than
# Echo's because we want sub-question terms to still emerge from short
# notes, and big stoplists drop too aggressively at small N.
_STOP: frozenset[str] = frozenset(
    """
    a about above after again against all also am an and any are as at be
    because been before being below between both but by can could did do does
    doing don down during each few for from further had has have having he
    her here hers herself him himself his how i if in into is it its itself
    just me more most my myself no nor not now of off on once only or other
    our ours ourselves out over own same she should so some such than that
    the their theirs them themselves then there these they this those
    through to too under until up very was we were what when where which
    while who whom why will with you your yours yourself yourselves
    """.split()
)


# ----------------------------------------------------------------- types


@dataclass
class LensNote:
    note_id: int
    title: str
    snippet: str          # the best-matching excerpt for this question
    tags: list[str]
    relevance: float      # composite 0..1
    info_gain: float      # relevance · novelty
    cosine: float
    lexical: float
    title_hit: bool
    read: bool
    read_at: str | None   # ISO, or None
    cluster_id: int | None = None
    cluster_name: str | None = None
    cluster_color: str | None = None


@dataclass
class Citation:
    """One ``[n]`` reference in the working answer."""

    ref: int              # 1-indexed citation marker
    note_id: int
    title: str
    excerpt: str          # the sentence we lifted, verbatim
    relevance: float


@dataclass
class Subquestion:
    """A distinctive sub-theme detected from the lens's relevant slice."""

    term: str
    note_count: int       # how many in-lens notes mention this term
    covered: int          # of those, how many the user has read
    coverage_pct: float   # covered / max(note_count, 1)
    sample_note_id: int   # a representative note for the term


@dataclass
class QuestionRow:
    """A persisted research question — what ``/compass/questions`` returns."""

    id: int
    text: str
    created_at: str
    archived_at: str | None
    last_read_at: str | None  # latest of any read_at for this question
    reads_count: int
    coverage_pct: float       # filled by the lens compute pass


@dataclass
class Lens:
    """The full computed view for one question. The frontend renders all of this."""

    question_id: int
    question_text: str
    created_at: str
    archived_at: str | None
    generated_at: str
    total_notes: int          # everything in the vault
    in_lens: int              # notes above RELEVANCE_FLOOR
    relevance_mass_total: float
    relevance_mass_read: float
    coverage_pct: float       # mass-weighted, 0..100
    notes: list[LensNote] = field(default_factory=list)
    frontiers: list[LensNote] = field(default_factory=list)
    subquestions: list[Subquestion] = field(default_factory=list)
    working_answer: str = ""
    citations: list[Citation] = field(default_factory=list)
    stats: dict = field(default_factory=dict)


# ----------------------------------------------------------------- helpers


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _content_words(text: str) -> list[str]:
    """Lowercased content words used for both lexical match and excerpts."""
    return [w for w in _WORD_RE.findall(text.lower()) if w not in _STOP]


def _content_word_set(text: str) -> frozenset[str]:
    return frozenset(_content_words(text))


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    if inter == 0:
        return 0.0
    return inter / len(a | b)


def _split_sentences(body: str) -> list[str]:
    """Split body into sentences. Tolerant of bullets / line-broken lists —
    each non-terminated line is its own sentence so list items don't fuse."""
    if not body or not body.strip():
        return []
    parts: list[str] = []
    for line in body.splitlines():
        line = line.strip()
        if not line:
            continue
        if not re.search(r"[.!?]", line):
            parts.append(line)
            continue
        for s in _SENT_SPLIT.split(line):
            s = s.strip()
            if s:
                parts.append(s)
    return parts


def _best_excerpt(body: str, q_words: frozenset[str]) -> str:
    """Pick the sentence whose content-word overlap with the question is
    highest. Ties broken by earlier position so the excerpt usually reads
    like an opener. Falls back to the first sentence if nothing overlaps,
    so cards never render with an empty quote."""
    sents = _split_sentences(body)
    if not sents:
        return body.strip()[:240]
    if not q_words:
        return sents[0][:240]
    best_idx = 0
    best_score = -1.0
    for i, s in enumerate(sents):
        sw = _content_word_set(s)
        if not sw:
            continue
        # Asymmetric: we care about how many of the question's words this
        # sentence covers, not the other way around. A long sentence with
        # one matching word still beats a short sentence with none.
        inter = len(q_words & sw)
        if inter == 0:
            continue
        score = inter / max(1, len(q_words))
        if score > best_score:
            best_score = score
            best_idx = i
    chosen = sents[best_idx].strip()
    if len(chosen) > 240:
        cut = chosen[:240].rsplit(" ", 1)[0]
        chosen = f"{cut}…"
    return chosen


def _snippet(body: str, max_chars: int = 200) -> str:
    text = body.strip().replace("\n\n", " · ").replace("\n", " ")
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars].rsplit(" ", 1)[0]
    return f"{cut}…"


def _title_hit(title: str, q_words: frozenset[str]) -> bool:
    if not q_words:
        return False
    title_words = _content_word_set(title)
    return bool(title_words & q_words)


# ----------------------------------------------------------------- main pass


def score_notes(
    *,
    question_text: str,
    notes: list[dict],
    embeddings: dict[int, tuple[float, ...]],
    cmap: dict[int, int] | None = None,
    community_lookup: dict[int, dict] | None = None,
    reads: dict[int, str] | None = None,
) -> list[LensNote]:
    """Compute the in-lens LensNote list, sorted by info_gain desc."""
    if not notes:
        return []

    cmap = cmap or {}
    community_lookup = community_lookup or {}
    reads = reads or {}

    q_text = question_text.strip()
    q_vec = embed(q_text)
    q_words = _content_word_set(q_text)

    out: list[LensNote] = []
    for n in notes:
        nid = n["id"]
        nv = embeddings.get(nid)
        if nv is None:
            continue
        cos = cosine(q_vec, nv)
        nw = _content_word_set(f"{n['title']} {n['body']}")
        lex = _jaccard(q_words, nw)
        th = _title_hit(n["title"], q_words)
        rel = (
            W_COSINE * max(0.0, cos)
            + W_LEXICAL * lex
            + (W_TITLE if th else 0.0)
        )
        if rel < RELEVANCE_FLOOR:
            continue
        read_at = reads.get(nid)
        is_read = read_at is not None
        info_gain = rel * (READ_NOVELTY_FACTOR if is_read else 1.0)
        cid = cmap.get(nid)
        comm = community_lookup.get(cid) if cid is not None else None
        out.append(
            LensNote(
                note_id=nid,
                title=n["title"],
                snippet=_best_excerpt(n["body"], q_words) or _snippet(n["body"]),
                tags=list(n.get("tags") or []),
                relevance=round(rel, 4),
                info_gain=round(info_gain, 4),
                cosine=round(max(0.0, cos), 4),
                lexical=round(lex, 4),
                title_hit=th,
                read=is_read,
                read_at=read_at,
                cluster_id=cid,
                cluster_name=comm["name"] if comm else None,
                cluster_color=comm["color"] if comm else None,
            )
        )

    out.sort(
        key=lambda ln: (
            ln.info_gain,
            ln.relevance,
            -ln.note_id,
        ),
        reverse=True,
    )
    return out


def working_answer(
    notes: list[LensNote],
    *,
    max_citations: int = WORKING_ANSWER_MAX_CITATIONS,
    max_chars: int = WORKING_ANSWER_MAX_CHARS,
) -> tuple[str, list[Citation]]:
    """Stitch a citation-anchored answer from the *read* lens notes.

    Returns ``(answer_text, citations)``. The answer references its
    sources as ``[1]``, ``[2]``, … in the order the excerpts appear;
    the citations list is parallel-indexed so the frontend can resolve
    a click on ``[2]`` back to a note jump.

    No LLM — this is extractive on purpose: every sentence is verbatim
    from one of your notes, every claim is auditable, and the same
    reads always produce the same answer.
    """
    read = [n for n in notes if n.read]
    if not read:
        return "", []
    # Already sorted by info_gain — but for the answer, we want
    # *relevance* order since info_gain dampens read notes and they're
    # all read here. Re-sort by raw relevance.
    read = sorted(read, key=lambda n: n.relevance, reverse=True)[:max_citations]

    citations: list[Citation] = []
    fragments: list[str] = []
    used_chars = 0
    for i, ln in enumerate(read, start=1):
        excerpt = ln.snippet.strip().rstrip(".") + "."
        marker = f"[{i}]"
        # Cite at the end of each fragment so the eye lands on the
        # source after reading the claim.
        line = f"{excerpt} {marker}"
        if used_chars + len(line) > max_chars and citations:
            break
        fragments.append(line)
        used_chars += len(line) + 1
        citations.append(
            Citation(
                ref=i,
                note_id=ln.note_id,
                title=ln.title,
                excerpt=excerpt,
                relevance=ln.relevance,
            )
        )
    return " ".join(fragments).strip(), citations


def detect_subquestions(
    notes: list[LensNote],
    question_text: str,
    notes_by_id: dict[int, dict],
) -> list[Subquestion]:
    """Mine distinctive sub-themes from the lens's relevant slice.

    We count content-word occurrences across the top ``SUBQ_TOP_NOTES``
    most-relevant notes, drop:
      * stopwords
      * words shorter than ``SUBQ_MIN_TERM_LEN`` (numbers / fragments)
      * the question's own content-words (they'd dominate trivially)
      * pure-digit tokens

    The top ``SUBQ_COUNT`` survivors become sub-questions, each carrying
    its own per-term coverage so the user sees which sub-aspect is
    already answered and which is still cold.
    """
    if not notes:
        return []
    pool = notes[:SUBQ_TOP_NOTES]
    q_words = _content_word_set(question_text)

    # Per-term: which note ids mention it (so we can compute coverage
    # against the user's reads for that term).
    notes_with_term: dict[str, list[int]] = {}
    for ln in pool:
        body = notes_by_id.get(ln.note_id, {}).get("body", "")
        nw = _content_word_set(f"{ln.title} {body}")
        for w in nw:
            if (
                len(w) < SUBQ_MIN_TERM_LEN
                or w.isdigit()
                or w in q_words
                or w in _STOP
            ):
                continue
            notes_with_term.setdefault(w, []).append(ln.note_id)

    # Surviving terms ranked by note frequency (with a tie-break that
    # prefers terms appearing in *more-relevant* notes, since high-
    # relevance notes are more likely to surface the real sub-themes).
    relevance_by_id = {ln.note_id: ln.relevance for ln in pool}
    candidates: list[tuple[int, float, str]] = []
    for term, ids in notes_with_term.items():
        if len(ids) < SUBQ_MIN_OCCURRENCES:
            continue
        ids_unique = sorted(set(ids))
        peak = max(relevance_by_id.get(i, 0.0) for i in ids_unique)
        candidates.append((len(ids_unique), peak, term))

    candidates.sort(reverse=True)

    read_set = {ln.note_id for ln in notes if ln.read}
    out: list[Subquestion] = []
    seen_stems: set[str] = set()
    for count, _peak, term in candidates:
        if len(out) >= SUBQ_COUNT:
            break
        # Cheap dedup: don't surface "system" if "systems" already won.
        stem = term[:5]
        if stem in seen_stems:
            continue
        seen_stems.add(stem)
        ids_unique = sorted(set(notes_with_term[term]))
        covered = sum(1 for i in ids_unique if i in read_set)
        sample = max(ids_unique, key=lambda i: relevance_by_id.get(i, 0.0))
        out.append(
            Subquestion(
                term=term,
                note_count=count,
                covered=covered,
                coverage_pct=round(100.0 * covered / max(count, 1), 1),
                sample_note_id=sample,
            )
        )
    return out


def build_lens(
    *,
    question_id: int,
    question_text: str,
    question_created_at: str,
    question_archived_at: str | None,
    notes: list[dict],
    embeddings: dict[int, tuple[float, ...]],
    cmap: dict[int, int] | None = None,
    community_lookup: dict[int, dict] | None = None,
    reads: dict[int, str] | None = None,
) -> Lens:
    """End-to-end lens compute. Pure function — caller does I/O."""
    notes_by_id = {n["id"]: n for n in notes}
    scored = score_notes(
        question_text=question_text,
        notes=notes,
        embeddings=embeddings,
        cmap=cmap,
        community_lookup=community_lookup,
        reads=reads,
    )

    mass_total = sum(ln.relevance for ln in scored)
    mass_read = sum(ln.relevance for ln in scored if ln.read)
    coverage_pct = round(100.0 * mass_read / mass_total, 1) if mass_total > 0 else 0.0

    frontiers = [ln for ln in scored if not ln.read][:FRONTIERS_K]
    subqs = detect_subquestions(scored, question_text, notes_by_id)
    answer, citations = working_answer(scored)

    stats = {
        "total_in_lens": len(scored),
        "read_in_lens": sum(1 for ln in scored if ln.read),
        "top_relevance": round(scored[0].relevance, 4) if scored else 0.0,
        "answered_subquestions": sum(1 for s in subqs if s.covered > 0),
        "frontiers_count": len(frontiers),
    }

    return Lens(
        question_id=question_id,
        question_text=question_text,
        created_at=question_created_at,
        archived_at=question_archived_at,
        generated_at=_now_iso(),
        total_notes=len(notes),
        in_lens=len(scored),
        relevance_mass_total=round(mass_total, 4),
        relevance_mass_read=round(mass_read, 4),
        coverage_pct=coverage_pct,
        notes=scored,
        frontiers=frontiers,
        subquestions=subqs,
        working_answer=answer,
        citations=citations,
        stats=stats,
    )


# ----------------------------------------------------------------- serializers


def _lens_note_dict(ln: LensNote) -> dict:
    return {
        "note_id": ln.note_id,
        "title": ln.title,
        "snippet": ln.snippet,
        "tags": ln.tags,
        "relevance": ln.relevance,
        "info_gain": ln.info_gain,
        "cosine": ln.cosine,
        "lexical": ln.lexical,
        "title_hit": ln.title_hit,
        "read": ln.read,
        "read_at": ln.read_at,
        "cluster_id": ln.cluster_id,
        "cluster_name": ln.cluster_name,
        "cluster_color": ln.cluster_color,
    }


def _citation_dict(c: Citation) -> dict:
    return {
        "ref": c.ref,
        "note_id": c.note_id,
        "title": c.title,
        "excerpt": c.excerpt,
        "relevance": c.relevance,
    }


def _subq_dict(s: Subquestion) -> dict:
    return {
        "term": s.term,
        "note_count": s.note_count,
        "covered": s.covered,
        "coverage_pct": s.coverage_pct,
        "sample_note_id": s.sample_note_id,
    }


def lens_to_dict(lens: Lens) -> dict:
    return {
        "question_id": lens.question_id,
        "question_text": lens.question_text,
        "created_at": lens.created_at,
        "archived_at": lens.archived_at,
        "generated_at": lens.generated_at,
        "total_notes": lens.total_notes,
        "in_lens": lens.in_lens,
        "relevance_mass_total": lens.relevance_mass_total,
        "relevance_mass_read": lens.relevance_mass_read,
        "coverage_pct": lens.coverage_pct,
        "notes": [_lens_note_dict(ln) for ln in lens.notes],
        "frontiers": [_lens_note_dict(ln) for ln in lens.frontiers],
        "subquestions": [_subq_dict(s) for s in lens.subquestions],
        "working_answer": lens.working_answer,
        "citations": [_citation_dict(c) for c in lens.citations],
        "stats": lens.stats,
    }


def question_row_to_dict(q: QuestionRow) -> dict:
    return {
        "id": q.id,
        "text": q.text,
        "created_at": q.created_at,
        "archived_at": q.archived_at,
        "last_read_at": q.last_read_at,
        "reads_count": q.reads_count,
        "coverage_pct": q.coverage_pct,
    }


# ----------------------------------------------------------------- markdown export


def to_markdown(lens: Lens) -> str:
    """Portable working-answer brief — paste-anywhere snapshot of the
    research session in its current state."""
    out: list[str] = []
    out.append(f"# Compass · {lens.question_text}\n")
    out.append(
        f"_{lens.in_lens} notes in lens · {lens.coverage_pct:.0f}% covered · "
        f"{lens.stats.get('read_in_lens', 0)}/{lens.in_lens} read · "
        f"generated {lens.generated_at}_\n"
    )

    if lens.working_answer:
        out.append("\n## Working answer\n")
        out.append(lens.working_answer + "\n")
        if lens.citations:
            out.append("\n### Sources\n")
            for c in lens.citations:
                out.append(
                    f"- **[{c.ref}]** {c.title} (#{c.note_id}) — "
                    f"_{c.relevance:.2f} relevance_"
                )
    else:
        out.append(
            "\n_No notes marked read for this question yet — open the "
            "frontiers below and mark them read as you go._\n"
        )

    if lens.subquestions:
        out.append("\n## Sub-themes\n")
        for s in lens.subquestions:
            out.append(
                f"- **{s.term}** — {s.covered}/{s.note_count} notes read "
                f"({s.coverage_pct:.0f}%)"
            )

    if lens.frontiers:
        out.append("\n## Frontiers — read next\n")
        for ln in lens.frontiers:
            out.append(f"\n### {ln.title} (#{ln.note_id})")
            out.append(
                f"_relevance {ln.relevance:.2f} · "
                f"{'title hit · ' if ln.title_hit else ''}"
                f"cos {ln.cosine:.2f} · lex {ln.lexical:.2f}_"
            )
            out.append(f"> {ln.snippet}")

    if lens.notes:
        out.append("\n## Full queue\n")
        for ln in lens.notes:
            tag = " · read" if ln.read else ""
            out.append(
                f"- **{ln.title}** (#{ln.note_id}) — relevance {ln.relevance:.2f}{tag}"
            )

    return "\n".join(out)


# ----------------------------------------------------------------- helpers used by main


def reads_count_total(reads: dict[int, str]) -> int:
    return sum(1 for v in reads.values() if v)


def last_read_at(reads: dict[int, str]) -> str | None:
    if not reads:
        return None
    return max(reads.values())


def truncate_question(text: str, *, max_chars: int = 280) -> str:
    """Cap question length for the row summary so the rail stays readable."""
    text = text.strip()
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars].rsplit(" ", 1)[0]
    return f"{cut}…"


__all__ = [
    "Lens",
    "LensNote",
    "Citation",
    "Subquestion",
    "QuestionRow",
    "build_lens",
    "score_notes",
    "working_answer",
    "detect_subquestions",
    "lens_to_dict",
    "question_row_to_dict",
    "to_markdown",
    "reads_count_total",
    "last_read_at",
    "truncate_question",
    "RELEVANCE_FLOOR",
    "READ_NOVELTY_FACTOR",
    "FRONTIERS_K",
]
