"""Distill long-form text into atomic notes.

The PKM cold-start problem is brutal: you install a beautiful graph-based
note system, then stare at an empty canvas because writing atomic notes
by hand is *work*. Most users abandon at this step.

Distill closes the gap. Paste anything — an article, a meeting transcript,
a long Slack thread, your own braindump — and this module proposes a list
of atomic notes ready to land in the graph: each one carries a predicted
title, distinctive tags, the cluster it would join, and the strongest
neighbors it would synapse to. The user edits in-place and commits.

Pipeline
--------

1. **Segment**. Hard splits on blank lines, markdown headings, and bullet
   markers. Inside long paragraphs we secondary-split on sentence
   boundaries so a wall-of-text paragraph becomes a handful of atoms
   instead of one bloated note. Anything below ``MIN_ATOM_CHARS`` is
   merged forward into the next atom.

2. **Title**. If the atom opens with a markdown heading we lift it
   verbatim. Otherwise we pick the first sentence and trim it to a
   reasonable headline length (~80 chars); if the first sentence is too
   long, we fall back to the leading-noun-phrase.

3. **Tags**. We score every candidate 1- and 2-gram by
   ``tf · log(1 + N_atoms / df)`` against the *rest of the input*. The
   highest-scoring 2-gram (if any survives stopwording) plus the top-2
   distinctive unigrams become tags, slugified.

4. **Cluster + neighbors**. Embed the atom, compare against current
   community centroids (best ≥ ``CLUSTER_HINT_TAU`` wins) and against
   every existing note (top-3 with cosine ≥ ``threshold`` become the
   predicted incoming synapses). The user sees, *before saving*, which
   notes this atom will link to and which cluster it will join.

Everything here is pure, zero-deps, deterministic, and runs in O(atoms
· N_notes) — comfortable for the typical paste of a 5,000-word article.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass

from .embed import DIM, cosine, embed

# Atom-size thresholds. These are tuned for the typical pasted input
# (article, transcript, long-form notes); they're not user-facing because
# the heuristic survives reasonable variations and the user can always
# delete or merge atoms in the preview UI.
MIN_ATOM_CHARS = 80
MAX_ATOM_CHARS = 900
TARGET_ATOM_CHARS = 480

# When attaching a predicted cluster, require a meaningful centroid match.
# 0.18 is intentionally below the synapse default τ (0.14) so atoms that
# *would* form synapses to a cluster's members surface a cluster hint
# even before their first edge fires.
CLUSTER_HINT_TAU = 0.18

# Per-atom neighbor preview. 3 is enough to communicate "this will land
# here" without overwhelming the card.
MAX_NEIGHBOR_PREVIEW = 3

# Title length budget after trimming. Keeps cards visually balanced.
TITLE_MAX_CHARS = 80

# Slug constraints for tags.
TAG_MAX_CHARS = 24


# A pragmatic stop-word list. Mirrors community.py's choice — small
# enough that domain terms survive, big enough to kill the obvious noise.
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
    """.split()
)

_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9\-']{1,}")
_SENTENCE_END_RE = re.compile(r"([\.!\?])\s+(?=[A-Z\(\[\"'“‘])")
_HEADING_RE = re.compile(r"^\s{0,3}(#{1,6})\s+(.*?)\s*$")
_BULLET_RE = re.compile(r"^\s*([-*+•]|\d+\.)\s+")


@dataclass
class AtomPreview:
    """One proposed note before the user has accepted it.

    ``temp_id`` is a stable per-request identifier so the frontend can
    diff edits without us needing to persist a draft.
    """

    temp_id: str
    title: str
    body: str
    tags: list[str]
    char_count: int
    cluster_id: int | None
    cluster_name: str | None
    cluster_color: str | None
    cluster_strength: float
    neighbors: list[dict]
    expected_synapses: int


@dataclass
class AtomCommit:
    """What the caller posts back after editing in the preview UI."""

    title: str
    body: str
    tags: list[str]


# ------------------------------------------------------------ segmentation


def _normalize_text(text: str) -> str:
    # Collapse Windows / Mac line endings; strip BOM; cap a single
    # paragraph break at 2 newlines so our blank-line splitter is happy.
    out = text.replace("\r\n", "\n").replace("\r", "\n").lstrip("﻿")
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip()


def _split_paragraphs(text: str) -> list[str]:
    """Hard split on blank lines + markdown headings + bullet runs.

    A markdown heading always starts a new atom even when adjacent to its
    body, because headings are usually titles in disguise. A run of
    bullets is treated as one atom (so the user gets a coherent list note
    rather than one-line orphans) — *unless* a bullet is very long, in
    which case the next stage splits it on sentences.
    """
    text = _normalize_text(text)
    if not text:
        return []

    paragraphs: list[str] = []
    current: list[str] = []
    in_bullets = False

    def _flush():
        if current:
            chunk = "\n".join(current).strip()
            if chunk:
                paragraphs.append(chunk)
            current.clear()

    for line in text.split("\n"):
        stripped = line.strip()
        # Blank line — paragraph break.
        if not stripped:
            _flush()
            in_bullets = False
            continue
        # Heading — always its own paragraph (heading + any inline body).
        if _HEADING_RE.match(line):
            _flush()
            in_bullets = False
            current.append(line)
            _flush()
            continue
        # Bullet run boundary — flush the previous non-bullet paragraph
        # so the list stays together, but join bullets into one atom.
        if _BULLET_RE.match(line):
            if not in_bullets:
                _flush()
            in_bullets = True
            current.append(line)
            continue
        if in_bullets:
            # Continuation of a bullet (indented) gets folded in.
            if line.startswith((" ", "\t")):
                current.append(line)
                continue
            _flush()
            in_bullets = False
        current.append(line)

    _flush()
    return paragraphs


def _split_sentences(paragraph: str, *, always: bool = False) -> list[str]:
    """Naive sentence splitter that respects abbreviations passably.

    We split on ``[.!?] + whitespace + capital`` so common abbreviations
    (``e.g.``, ``Dr.``, ``vs.``) don't trigger a break. For our purposes —
    handing the segmenter "is this too long to be one atom?" — naive is
    fine. The user can merge in the UI if we over-split.

    ``always=True`` forces sentence-level output even for short paragraphs;
    the title-picker uses it because we want the first *sentence* to be
    the headline, not the first *paragraph*.
    """
    if not paragraph.strip():
        return []
    # Don't sentence-split tiny paragraphs by default (the segmenter
    # only cares about the long-paragraph case). Title-picking opts in.
    if not always and len(paragraph) <= TARGET_ATOM_CHARS:
        return [paragraph.strip()]

    parts = _SENTENCE_END_RE.split(paragraph)
    if len(parts) <= 1:
        return [paragraph.strip()]
    # Re-stitch the punctuation back onto the preceding sentence.
    sentences: list[str] = []
    buf: list[str] = []
    for i, p in enumerate(parts):
        if i % 2 == 0:
            buf.append(p)
        else:
            buf.append(p)
            sentences.append("".join(buf).strip())
            buf = []
    if buf:
        sentences.append("".join(buf).strip())
    return [s for s in sentences if s]


def _merge_to_atoms(paragraphs: list[str]) -> list[str]:
    """Glue tiny fragments forward, split monsters via sentence joins.

    Atom boundaries respect markdown headings: a heading *always* starts
    a new atom (and forces a flush of pending). Without this rule, a
    paste like "# A / short body / # B / short body" would fuse into
    one giant atom because each paragraph is below MIN_ATOM_CHARS.
    """
    if not paragraphs:
        return []

    atoms: list[str] = []
    pending: str = ""

    def _flush_pending():
        nonlocal pending
        if pending.strip():
            atoms.append(pending.strip())
        pending = ""

    def _is_heading(p: str) -> bool:
        first = p.lstrip().splitlines()[0] if p.strip() else ""
        return bool(_HEADING_RE.match(first))

    for p in paragraphs:
        # Oversized paragraph: re-pack sentences into ~TARGET_ATOM_CHARS chunks.
        if len(p) > MAX_ATOM_CHARS:
            _flush_pending()
            sentences = _split_sentences(p)
            buf: list[str] = []
            buf_len = 0
            for s in sentences:
                if buf_len + len(s) > TARGET_ATOM_CHARS and buf:
                    atoms.append(" ".join(buf).strip())
                    buf = []
                    buf_len = 0
                buf.append(s)
                buf_len += len(s) + 1
            if buf:
                atoms.append(" ".join(buf).strip())
            continue

        # Heading boundary: every heading starts a new atom.
        if _is_heading(p):
            _flush_pending()
            pending = p
            continue

        # Standard-sized paragraph. Glue into pending if pending fits and
        # the pending isn't a stand-alone heading-led section that's
        # ready to ship as soon as it has a body.
        if pending and len(pending) + len(p) + 2 <= MAX_ATOM_CHARS:
            pending = f"{pending}\n\n{p}"
        else:
            _flush_pending()
            pending = p

        if len(pending) >= MIN_ATOM_CHARS:
            _flush_pending()

    _flush_pending()

    # Final pass: if the *last* atom is below MIN_ATOM_CHARS and we have
    # a previous atom, fold it backward so we don't ship a stub — but
    # not when the last atom is a heading-led section (that's a valid
    # short standalone, e.g. "## Conclusion / Ship it.").
    if len(atoms) >= 2 and len(atoms[-1]) < MIN_ATOM_CHARS:
        first_line = atoms[-1].lstrip().splitlines()[0]
        if not _HEADING_RE.match(first_line):
            atoms[-2] = f"{atoms[-2]}\n\n{atoms[-1]}"
            atoms.pop()

    return atoms


# ------------------------------------------------------------ title


def _pick_title(atom: str) -> str:
    """Pick a 3-12 word title for an atom.

    Strategy: heading lift > first sentence > first 80 chars. We strip
    trailing punctuation and surrounding quotes/markdown so the card
    reads cleanly.
    """
    first_line = atom.lstrip().splitlines()[0] if atom.strip() else ""
    m = _HEADING_RE.match(first_line)
    if m:
        return _clean_title(m.group(2))

    # Lift the first non-bullet, non-quote sentence.
    cleaned = re.sub(r"^[\s>*\-•]+", "", first_line)
    sentences = _split_sentences(atom, always=True)
    if sentences:
        cleaned = re.sub(r"^[\s>*\-•]+", "", sentences[0])
    if not cleaned:
        cleaned = atom.strip()

    if len(cleaned) <= TITLE_MAX_CHARS:
        return _clean_title(cleaned)

    # Try to break on a clause: colon, em-dash, semicolon, comma.
    for sep in (": ", " — ", " – ", "; ", ", "):
        idx = cleaned.find(sep)
        if 16 <= idx <= TITLE_MAX_CHARS:
            return _clean_title(cleaned[:idx])

    # Fall back to a word-bounded trim.
    trimmed = cleaned[:TITLE_MAX_CHARS]
    last_space = trimmed.rfind(" ")
    if last_space > 24:
        trimmed = trimmed[:last_space]
    return _clean_title(trimmed + "…")


def _clean_title(s: str) -> str:
    s = s.strip()
    # Strip surrounding markdown emphasis, smart quotes, hard punctuation.
    s = re.sub(r"^[\*_`\"'\(\[\{]+", "", s)
    s = re.sub(r"[\*_`\"'\)\]\}]+$", "", s)
    s = re.sub(r"\s+", " ", s)
    s = s.rstrip(".,;:!?— -")
    if not s:
        s = "Untitled atom"
    return s


# ------------------------------------------------------------ tags


def _tag_candidates(atom: str) -> list[tuple[str, str]]:
    """Yield (display, slug) for the n-gram candidates of one atom."""
    tokens = [t.lower() for t in _WORD_RE.findall(atom)]
    out: list[tuple[str, str]] = []
    seen: set[str] = set()

    def _push(display: str, slug: str):
        if slug in seen:
            return
        seen.add(slug)
        out.append((display, slug))

    # Unigrams (skip stops + short tokens + pure-digit tokens).
    for t in tokens:
        if t in _STOP or len(t) < 4 or t.isdigit():
            continue
        slug = _slugify(t)
        if slug:
            _push(t, slug)
    # Bigrams (skip if either side is a stopword).
    for a, b in zip(tokens, tokens[1:]):
        if a in _STOP or b in _STOP:
            continue
        if len(a) < 3 or len(b) < 3:
            continue
        display = f"{a} {b}"
        slug = _slugify(f"{a}-{b}")
        if slug:
            _push(display, slug)
    return out


def _slugify(s: str) -> str:
    s = s.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:TAG_MAX_CHARS]


def _score_tags(
    atom_idx: int,
    atom_text: str,
    df_unigrams: Counter,
    df_bigrams: Counter,
    n_atoms: int,
) -> list[str]:
    """TF-IDF-flavored distinctiveness scorer.

    A term scores well when it shows up *inside this atom* and seldom in
    the others. We take the top distinctive bigram (if any) plus two top
    unigrams, slugify, and dedupe — so a tag like ``embedding`` never
    competes with ``embeddings`` for the same slot once normalized.
    """
    candidates = _tag_candidates(atom_text)
    if not candidates:
        return []

    tf_uni: Counter = Counter()
    tf_bi: Counter = Counter()
    for display, slug in candidates:
        if " " in display:
            tf_bi[slug] += 1
        else:
            tf_uni[slug] += 1

    import math

    def _score(slug: str, tf: int, df: int) -> float:
        idf = math.log(1.0 + n_atoms / max(df, 1))
        return tf * idf

    scored: list[tuple[float, str, str, bool]] = []
    for display, slug in candidates:
        is_bi = " " in display
        tf = tf_bi[slug] if is_bi else tf_uni[slug]
        df = df_bigrams[slug] if is_bi else df_unigrams[slug]
        s = _score(slug, tf, df)
        # Bigrams get a small bonus when they fire — multi-word tags are
        # more informative than the unigrams they decompose into.
        if is_bi:
            s *= 1.15
        scored.append((s, display, slug, is_bi))

    scored.sort(key=lambda x: x[0], reverse=True)

    out: list[str] = []
    seen_slugs: set[str] = set()
    # Take up to one bigram first, then unigrams, capped at 3.
    bi_taken = 0
    for _, display, slug, is_bi in scored:
        if slug in seen_slugs:
            continue
        if is_bi and bi_taken >= 1:
            continue
        out.append(slug)
        seen_slugs.add(slug)
        if is_bi:
            bi_taken += 1
        if len(out) >= 3:
            break

    return out


# ------------------------------------------------------------ centroid + neighbors


def _community_centroids(
    embeddings: dict[int, tuple[float, ...]],
    communities: list,
) -> dict[int, tuple[tuple[float, ...], int]]:
    """Map cluster_id → (unit-normalized centroid, member_count).

    Centroids are computed only over members with embeddings; clusters
    that share no embedding-bearing members get skipped silently.
    """
    out: dict[int, tuple[tuple[float, ...], int]] = {}
    for c in communities:
        vec = [0.0] * DIM
        n = 0
        for mid in c.member_ids:
            v = embeddings.get(mid)
            if v is None:
                continue
            for i in range(DIM):
                vec[i] += v[i]
            n += 1
        if n == 0:
            continue
        # L2 normalize so cosine is dot product.
        norm = sum(x * x for x in vec) ** 0.5
        if norm == 0:
            continue
        inv = 1.0 / norm
        out[c.id] = (tuple(x * inv for x in vec), n)
    return out


def _predict_cluster(
    atom_vec: tuple[float, ...],
    centroids: dict[int, tuple[tuple[float, ...], int]],
    cluster_lookup: dict[int, dict],
) -> tuple[int | None, str | None, str | None, float]:
    """Best-matching cluster + cosine, or (None, …, 0.0) if below tau."""
    best_id: int | None = None
    best_s = 0.0
    for cid, (centroid, _n) in centroids.items():
        s = cosine(atom_vec, centroid)
        if s > best_s:
            best_s = s
            best_id = cid
    if best_id is None or best_s < CLUSTER_HINT_TAU:
        return (None, None, None, round(best_s, 4))
    meta = cluster_lookup.get(best_id, {})
    return (best_id, meta.get("name"), meta.get("color"), round(best_s, 4))


def _neighbor_preview(
    atom_vec: tuple[float, ...],
    embeddings: dict[int, tuple[float, ...]],
    notes_by_id: dict[int, dict],
    threshold: float,
) -> list[dict]:
    """Top-K notes the atom would synapse to at the current threshold."""
    scored: list[tuple[float, int]] = []
    for nid, v in embeddings.items():
        s = cosine(atom_vec, v)
        if s >= threshold:
            scored.append((s, nid))
    scored.sort(reverse=True)
    out: list[dict] = []
    for s, nid in scored[:MAX_NEIGHBOR_PREVIEW]:
        n = notes_by_id.get(nid)
        if not n:
            continue
        out.append(
            {
                "note_id": nid,
                "title": n["title"],
                "strength": round(s, 4),
                "cluster_id": n.get("community"),
                "cluster_color": n.get("community_color"),
            }
        )
    return out


def _all_neighbors_count(
    atom_vec: tuple[float, ...],
    embeddings: dict[int, tuple[float, ...]],
    threshold: float,
) -> int:
    return sum(1 for v in embeddings.values() if cosine(atom_vec, v) >= threshold)


# ------------------------------------------------------------ public API


def distill(
    text: str,
    *,
    threshold: float,
    notes_by_id: dict[int, dict],
    embeddings: dict[int, tuple[float, ...]],
    communities: list,
) -> list[AtomPreview]:
    """Segment + enrich. Returns ready-to-edit atom previews.

    Pure function — no DB writes. The caller's job is to take the user's
    edited atoms back via ``commit`` (handled by ``main.py``'s router).
    """
    paragraphs = _split_paragraphs(text)
    raw_atoms = _merge_to_atoms(paragraphs)
    if not raw_atoms:
        return []

    # Document-frequency for the tag scorer.
    df_uni: Counter = Counter()
    df_bi: Counter = Counter()
    per_atom_candidates: list[list[tuple[str, str]]] = []
    for atom in raw_atoms:
        cands = _tag_candidates(atom)
        per_atom_candidates.append(cands)
        seen_uni: set[str] = set()
        seen_bi: set[str] = set()
        for display, slug in cands:
            if " " in display:
                if slug not in seen_bi:
                    df_bi[slug] += 1
                    seen_bi.add(slug)
            else:
                if slug not in seen_uni:
                    df_uni[slug] += 1
                    seen_uni.add(slug)

    cluster_lookup = {
        c.id: {"name": c.name, "color": c.color, "terms": list(c.terms)}
        for c in communities
    }
    centroids = _community_centroids(embeddings, communities)

    out: list[AtomPreview] = []
    for idx, atom in enumerate(raw_atoms):
        # Stripping markdown heading prefix from the body keeps the
        # saved note clean — the heading already lives in the title.
        body = atom
        first_line = body.lstrip().splitlines()[0] if body.strip() else ""
        if _HEADING_RE.match(first_line):
            rest = body.split("\n", 1)
            body = rest[1].strip() if len(rest) > 1 else ""
            if not body:
                # Heading with no body — keep the heading text as the body
                # so the note isn't empty.
                body = _HEADING_RE.match(first_line).group(2).strip()  # type: ignore[union-attr]

        title = _pick_title(atom)
        tags = _score_tags(idx, atom, df_uni, df_bi, len(raw_atoms))

        atom_vec = embed(f"{title}\n\n{body}")
        cluster_id, cluster_name, cluster_color, cluster_strength = _predict_cluster(
            atom_vec, centroids, cluster_lookup
        )
        neighbors = _neighbor_preview(atom_vec, embeddings, notes_by_id, threshold)
        expected = _all_neighbors_count(atom_vec, embeddings, threshold)

        out.append(
            AtomPreview(
                temp_id=f"atom_{idx}",
                title=title,
                body=body,
                tags=tags,
                char_count=len(body),
                cluster_id=cluster_id,
                cluster_name=cluster_name,
                cluster_color=cluster_color,
                cluster_strength=cluster_strength,
                neighbors=neighbors,
                expected_synapses=expected,
            )
        )

    return out


def llm_refine_title(
    body: str,
    *,
    provider: str,
    key: str,
    model: str,
) -> tuple[str, list[str]] | None:
    """Optional LLM polish: tighter title + 2-3 tags.

    Calls ``llm.call_llm`` with a strict JSON-output prompt. Any error
    (network, parse, malformed JSON) yields ``None`` and the caller keeps
    the heuristic output. The product is fully usable without this path
    — it's only here so users with a key get nicer card-front copy.
    """
    from . import llm as _llm
    import json

    system = (
        "You write tight note titles and tags for a personal knowledge "
        "graph. Output ONLY a JSON object with keys `title` (string, 3-9 "
        "words, no trailing punctuation) and `tags` (array of 2-3 short "
        "lowercase slugs, single or two words, no #). No prose."
    )
    user = f"Note body:\n\n{body[:1400]}"
    result = _llm.call_llm(provider, key, model, system, user, max_tokens=120, temperature=0.2)
    if not result:
        return None
    raw = result.text.strip()
    # Tolerate markdown code-fences around the JSON.
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    try:
        obj = json.loads(raw)
    except Exception:
        return None
    title = str(obj.get("title") or "").strip()
    tags_in = obj.get("tags") or []
    if not title or not isinstance(tags_in, list):
        return None
    cleaned_tags: list[str] = []
    for t in tags_in:
        if not isinstance(t, str):
            continue
        slug = _slugify(t.lstrip("#"))
        if slug and slug not in cleaned_tags:
            cleaned_tags.append(slug)
        if len(cleaned_tags) >= 3:
            break
    return (_clean_title(title), cleaned_tags)
