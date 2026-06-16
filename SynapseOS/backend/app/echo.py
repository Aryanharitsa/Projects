"""Echo — semantic de-duplication studio for your second brain.

Every other SynapseOS surface treats *similarity* as a virtue: synapses
draw it, communities cluster it, chat retrieves along it. Echo flips the
sign. The same property that powers all the good stuff is also a tax —
as your store grows you naturally restate the same thought in different
words, sometimes weeks apart, sometimes within the same sitting. Those
near-duplicates pollute the graph (hub nodes that shouldn't be hubs),
inflate cluster sizes, and make search noisier.

Echo finds the duplicates, shows you the overlap, and gives you a single
button to either:

  * **merge** the cluster down to one canonical note (preserving the
    unique sentences from each side and unioning tags), or
  * **mark distinct** so the pair never gets flagged again — captured in
    a tiny ``dedupe_skips`` table so the brief stays usable forever.

Determinism
-----------
A pure function of ``(notes, embeddings, threshold, skips)``. No LLM
calls, no randomness, no time-dependent decay. The same store at the
same threshold always produces the same brief — which makes Echo safe
to call from a header probe without a refresh button.

Clustering
----------
Single-linkage union-find over the pairs at-or-above ``threshold``. We
pick single-linkage on purpose: if A≈B and B≈C, then A and C belong in
the same merge candidate even if A and C only just miss the bar
themselves — the user is going to want to look at them together.
``MAX_CLUSTER_SIZE`` caps the result so a runaway hub can't pull twenty
notes into one merge UI.

Canonical pick
--------------
Inside each cluster we pick the note with the highest *centrality*
(sum of cosine to all other cluster members), tie-broken by longest
body, then by oldest id. That gives us "the one that already says most
of what the others say" — the natural target to merge *into*.

Merge body
----------
We sentence-split every note, normalize each sentence (lowercase,
collapse whitespace, strip leading bullets / numbering), and walk
canonical → others, keeping each sentence the first time we see its
normalized form. The output is canonical's sentences first (in their
original order), then any *new* sentences contributed by each other
note appended afterwards — so the merged note reads like the canonical
augmented with what the duplicates added, not a Frankenstein paragraph.

Wasted-chars estimate
---------------------
For each cluster we compute the chars you'd save by merging:
``sum(len(body) for body in cluster) − len(merged_body)``. It's a
back-of-the-envelope value; the UI uses it as a sortable badge, not as
a precise accounting figure.
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

from . import store, synapse
from .embed import cosine

# Pairs at-or-above this cosine count as candidate duplicates. Higher
# than the synapse threshold (0.14) because near-duplicate is a much
# stronger claim than near-related; tuned so the seed graph yields a
# handful of plausible echoes rather than tens.
DEFAULT_THRESHOLD = 0.72

# Hard cap on cluster size. A cluster of 12 near-duplicates is almost
# certainly a runaway hub (e.g. a meta note that links to everything);
# Echo would rather under-promise than dump an unreviewable wall of
# diffs into the modal.
MAX_CLUSTER_SIZE = 6

# Don't surface a cluster whose largest pairwise cosine is below this —
# saves the "well technically these are similar" cases from cluttering
# the brief at low thresholds.
MIN_PEAK_COSINE = 0.55

_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"\(\[])")
_LEADING_BULLET = re.compile(r"^[\s\-\*•–—\d\.\)]+")
_WHITESPACE = re.compile(r"\s+")
_WORD_RE = re.compile(r"[a-z][a-z\-']+")

# Tiny stop-word set: just the high-frequency function words. We strip
# these from the sentence-similarity comparison so "long blocks for deep
# work" and "long deep-work blocks are essential" register as the same
# sentence. Bigger stop lists hurt — they over-collapse short sentences.
_STOP: frozenset[str] = frozenset(
    """
    a an and are as at be been being but by can could do does did for from
    had has have he her his i if in into is it its me my no nor not of off
    on or our she should so some such than that the their them then there
    these they this those to was we were what when where which who will
    with you your yours yourself
    """.split()
)

# Two sentences register as the "same" if their content-word Jaccard
# clears this. High enough that genuinely different sentences don't
# collide; low enough that a re-phrasing of the same thought collapses.
SENT_DUP_JACCARD = 0.55

# Sentences shorter than this don't get fuzzy-matched — list bullets
# and one-word fragments alias too aggressively otherwise.
MIN_FUZZY_WORDS = 3


# --------------------------------------------------------------- skips

def _ensure_skips_table(con: sqlite3.Connection) -> None:
    """Create the per-pair "intentionally distinct" persistence table.

    Stored as a normalized ``(low, high)`` pair so we never insert the
    same pair twice in opposite order. ``reason`` is free-form text so
    users can write a justification ("these look alike but A is about
    deploy, B is about develop") that the UI surfaces later.
    """
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS dedupe_skips (
            a_id      INTEGER NOT NULL,
            b_id      INTEGER NOT NULL,
            reason    TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            PRIMARY KEY (a_id, b_id),
            CHECK (a_id < b_id)
        )
        """
    )


def _pair_key(a: int, b: int) -> tuple[int, int]:
    return (a, b) if a < b else (b, a)


def list_skips() -> list[dict]:
    with store._conn() as con:  # noqa: SLF001 — internal helper reuse
        _ensure_skips_table(con)
        rows = con.execute(
            "SELECT a_id, b_id, reason, created_at FROM dedupe_skips ORDER BY created_at DESC"
        ).fetchall()
        return [
            {
                "a_id": int(r["a_id"]),
                "b_id": int(r["b_id"]),
                "reason": r["reason"],
                "created_at": r["created_at"],
            }
            for r in rows
        ]


def add_skips(pairs: list[tuple[int, int]], reason: str = "") -> int:
    """Record one-or-many pairs as intentionally distinct. Returns count inserted."""
    if not pairs:
        return 0
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    inserted = 0
    with store._conn() as con:  # noqa: SLF001
        _ensure_skips_table(con)
        for a, b in pairs:
            a2, b2 = _pair_key(int(a), int(b))
            if a2 == b2:
                continue
            cur = con.execute(
                "INSERT OR IGNORE INTO dedupe_skips(a_id, b_id, reason, created_at) "
                "VALUES (?, ?, ?, ?)",
                (a2, b2, reason.strip(), now),
            )
            inserted += cur.rowcount
    return inserted


def remove_skip(a: int, b: int) -> bool:
    a2, b2 = _pair_key(int(a), int(b))
    with store._conn() as con:  # noqa: SLF001
        _ensure_skips_table(con)
        cur = con.execute(
            "DELETE FROM dedupe_skips WHERE a_id = ? AND b_id = ?", (a2, b2)
        )
        return cur.rowcount > 0


def _skip_set() -> set[tuple[int, int]]:
    with store._conn() as con:  # noqa: SLF001
        _ensure_skips_table(con)
        rows = con.execute("SELECT a_id, b_id FROM dedupe_skips").fetchall()
        return {(int(r["a_id"]), int(r["b_id"])) for r in rows}


# --------------------------------------------------------------- sentence utils

def _split_sentences(text: str) -> list[str]:
    """Split body into sentences, preserving original casing/punctuation.

    Tolerates bullets and numbered lists — each line that doesn't end
    with sentence-terminator punctuation gets treated as one "sentence"
    on its own so list items aren't fused.
    """
    if not text or not text.strip():
        return []
    parts: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        # If the line lacks any terminating punctuation, take it whole.
        if not re.search(r"[.!?]", line):
            parts.append(line)
            continue
        for s in _SENT_SPLIT.split(line):
            s = s.strip()
            if s:
                parts.append(s)
    return parts


def _normalize_sentence(s: str) -> str:
    """Reduce a sentence to its comparable form.

    Aggressive: lowercase, strip leading bullet / numbering, collapse
    whitespace, drop trailing punctuation. Two sentences that differ
    only in case, spacing, or list decoration collapse to the same key.
    """
    if not s:
        return ""
    s = _LEADING_BULLET.sub("", s.lower()).strip()
    s = _WHITESPACE.sub(" ", s)
    # Drop *trailing* punctuation only — internal punctuation can be
    # the difference between two real sentences.
    s = s.rstrip(".!?,;:\"'")
    return s


def _content_words(s: str) -> frozenset[str]:
    """The set of content (non-stop) words used for fuzzy matching."""
    return frozenset(w for w in _WORD_RE.findall(s.lower()) if w not in _STOP)


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    if inter == 0:
        return 0.0
    return inter / len(a | b)


def _build_sentence_buckets(
    sentences: list[tuple[int, str, frozenset[str]]],
) -> list[list[int]]:
    """Group ``(idx, _, words)`` triples into fuzzy-duplicate buckets.

    Greedy: walk in order, attach each sentence to the *first* existing
    bucket whose representative has Jaccard ≥ ``SENT_DUP_JACCARD``,
    otherwise start a new bucket. The frontend renders buckets as
    "appears in N notes" badges, so we want them stable & deterministic.
    """
    buckets: list[list[int]] = []
    bucket_words: list[frozenset[str]] = []
    for idx, _, words in sentences:
        attached = False
        if len(words) >= MIN_FUZZY_WORDS:
            for bi, bw in enumerate(bucket_words):
                if _jaccard(words, bw) >= SENT_DUP_JACCARD:
                    buckets[bi].append(idx)
                    # Union the bucket's signature so subsequent matches
                    # generalize correctly when several rephrasings hang
                    # off the same idea.
                    bucket_words[bi] = bw | words
                    attached = True
                    break
        if not attached:
            buckets.append([idx])
            bucket_words.append(words)
    return buckets


# --------------------------------------------------------------- clustering

def _union_find(n_ids: list[int], edges: list[tuple[int, int]]) -> dict[int, list[int]]:
    """Return ``{root: [members]}`` from union-find over ``edges``."""
    parent: dict[int, int] = {n: n for n in n_ids}

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for a, b in edges:
        if a in parent and b in parent:
            union(a, b)

    groups: dict[int, list[int]] = {}
    for n in n_ids:
        r = find(n)
        groups.setdefault(r, []).append(n)
    return groups


@dataclass
class EchoMember:
    note_id: int
    title: str
    body: str
    tags: list[str]
    created_at: str
    body_len: int
    is_canonical: bool
    centrality: float


@dataclass
class EchoSentence:
    text: str
    note_ids: list[int]      # notes whose body contains this sentence
    is_duplicate: bool       # appeared in >= 2 notes
    is_canonical_source: bool  # appeared first in the canonical note


@dataclass
class EchoPair:
    a_id: int
    b_id: int
    cosine: float


@dataclass
class EchoCluster:
    cluster_id: str          # stable ":"-joined sorted ids
    size: int
    redundancy: float        # mean pairwise cosine in [0, 1]
    peak_cosine: float       # max pairwise cosine
    wasted_chars: int        # back-of-envelope chars saved by merging
    chars_total: int
    chars_unique: int
    canonical_id: int
    members: list[EchoMember]
    pairs: list[EchoPair]
    merged_title: str
    merged_body: str
    merged_tags: list[str]
    sentences: list[EchoSentence]
    overlap_ratio: float     # share of sentences that appear in >= 2 notes


@dataclass
class EchoReport:
    threshold: float
    total_notes: int
    candidate_pairs: int
    cluster_count: int
    clusters: list[EchoCluster]
    skipped_pair_count: int
    stats: dict


# --------------------------------------------------------------- merge synth

def _merged_payload(
    members: list[dict],
    canonical_id: int,
) -> tuple[str, str, list[str], list[EchoSentence], int]:
    """Build the merged title, body, tags, sentence ledger, and unique char count.

    We collect every sentence across all members (canonical first),
    bucket them by content-word Jaccard so re-phrasings collapse, then
    emit one representative per bucket in canonical-first encounter
    order. ``EchoSentence.note_ids`` records every member whose body
    contributed to that bucket so the UI can paint "appears in N notes"
    badges with the right multiplicity.
    """
    canonical = next(m for m in members if m["id"] == canonical_id)
    others = [m for m in members if m["id"] != canonical_id]
    ordered = [canonical, *others]

    # Build a flat ordered list of (occurrence_index, note_id, original_text, word_set).
    # The occurrence index preserves canonical-first emission order so
    # the merged body reads like the canonical augmented by the rest.
    triples: list[tuple[int, int, str, frozenset[str]]] = []
    for m in ordered:
        for sent in _split_sentences(m["body"]):
            norm = _normalize_sentence(sent)
            if not norm:
                continue
            words = _content_words(norm)
            triples.append((len(triples), m["id"], sent, words))

    # Fuzzy-bucket by word Jaccard so rephrasings collapse. Each bucket
    # is an ordered list of occurrence-indices that all map to the
    # "same" sentence (under our threshold).
    fuzzy_input: list[tuple[int, str, frozenset[str]]] = [
        (idx, "", words) for idx, _, _, words in triples
    ]
    buckets = _build_sentence_buckets(fuzzy_input)
    # idx -> bucket id
    bucket_of: dict[int, int] = {}
    for bi, members_idx in enumerate(buckets):
        for idx in members_idx:
            bucket_of[idx] = bi

    # For each bucket, what notes contributed and which occurrence wins
    # as the "representative" text. Canonical wins if present, else the
    # first-seen occurrence.
    bucket_notes: dict[int, list[int]] = {bi: [] for bi in range(len(buckets))}
    bucket_rep_idx: dict[int, int] = {}
    for idx, nid, _text, _words in triples:
        bi = bucket_of[idx]
        if nid not in bucket_notes[bi]:
            bucket_notes[bi].append(nid)
        if bi not in bucket_rep_idx:
            bucket_rep_idx[bi] = idx
        else:
            # Prefer a canonical occurrence as the rep; otherwise keep
            # the longest version (more polished phrasing usually wins).
            rep_idx = bucket_rep_idx[bi]
            rep_nid = triples[rep_idx][1]
            if rep_nid != canonical_id and nid == canonical_id:
                bucket_rep_idx[bi] = idx
            elif (
                rep_nid != canonical_id
                and nid != canonical_id
                and len(triples[idx][2]) > len(triples[rep_idx][2])
            ):
                bucket_rep_idx[bi] = idx

    # Emit buckets in the order their first occurrence appeared (which
    # is canonical-first by construction).
    seen_buckets: set[int] = set()
    emitted: list[EchoSentence] = []
    body_chunks: list[str] = []
    for idx, _nid, _text, _words in triples:
        bi = bucket_of[idx]
        if bi in seen_buckets:
            continue
        seen_buckets.add(bi)
        rep_idx = bucket_rep_idx[bi]
        rep_text = triples[rep_idx][2]
        note_ids = sorted(bucket_notes[bi])
        first_idx_for_bucket = next(i for i in range(len(triples)) if bucket_of[i] == bi)
        is_canonical_source = triples[first_idx_for_bucket][1] == canonical_id
        emitted.append(
            EchoSentence(
                text=rep_text,
                note_ids=note_ids,
                is_duplicate=len(note_ids) > 1,
                is_canonical_source=is_canonical_source,
            )
        )
        body_chunks.append(rep_text)

    merged_body = " ".join(body_chunks).strip()
    chars_unique = len(merged_body)

    # Title: canonical's, but if any other member has a strictly longer
    # title with the canonical title as a substring, prefer that (a
    # later re-write of the same thought is usually more polished). If
    # titles all differ wildly we keep canonical's verbatim.
    merged_title = canonical["title"]
    for m in others:
        cand = m["title"]
        if (
            len(cand) > len(merged_title)
            and merged_title.lower() in cand.lower()
        ):
            merged_title = cand

    # Tags: union, preserve canonical-first order, cap to 8.
    merged_tags: list[str] = []
    seen_tags: set[str] = set()
    for m in ordered:
        for t in m.get("tags", []) or []:
            tag = t.strip().lower()
            if tag and tag not in seen_tags:
                seen_tags.add(tag)
                merged_tags.append(tag)
    merged_tags = merged_tags[:8]

    return merged_title, merged_body, merged_tags, emitted, chars_unique


# --------------------------------------------------------------- entry points

def find_clusters(
    *,
    threshold: float = DEFAULT_THRESHOLD,
    limit: int | None = None,
    include_skipped: bool = False,
) -> EchoReport:
    """Compute the de-duplication brief.

    ``include_skipped`` is mostly a debugging affordance — by default we
    respect the user's "mark distinct" history.
    """
    notes = store.all_notes()
    notes_by_id = {n["id"]: n for n in notes}
    if len(notes) < 2:
        return EchoReport(
            threshold=threshold,
            total_notes=len(notes),
            candidate_pairs=0,
            cluster_count=0,
            clusters=[],
            skipped_pair_count=0,
            stats={"notes": len(notes)},
        )

    embeddings = dict(store.all_embeddings())
    skips = set() if include_skipped else _skip_set()

    ids = sorted(notes_by_id.keys())
    pair_cosines: dict[tuple[int, int], float] = {}
    edges: list[tuple[int, int]] = []

    for i, a in enumerate(ids):
        va = embeddings.get(a)
        if va is None:
            continue
        for b in ids[i + 1 :]:
            if (a, b) in skips:
                continue
            vb = embeddings.get(b)
            if vb is None:
                continue
            c = cosine(va, vb)
            if c >= threshold:
                pair_cosines[(a, b)] = c
                edges.append((a, b))

    if not edges:
        return EchoReport(
            threshold=threshold,
            total_notes=len(notes),
            candidate_pairs=0,
            cluster_count=0,
            clusters=[],
            skipped_pair_count=len(skips),
            stats={"notes": len(notes), "pairs_above_threshold": 0},
        )

    groups = _union_find(ids, edges)
    clusters: list[EchoCluster] = []
    total_pairs = 0
    for root, members in groups.items():
        if len(members) < 2:
            continue
        if len(members) > MAX_CLUSTER_SIZE:
            # Trim to the most-central N members so the modal stays
            # actionable; the user can revisit the rest by lowering the
            # threshold or merging this subset first.
            members = _trim_runaway(members, pair_cosines, MAX_CLUSTER_SIZE)
        members_sorted = sorted(members)
        cluster_id = ":".join(str(m) for m in members_sorted)

        # Pairwise cosines just within this cluster.
        local_pairs: list[EchoPair] = []
        for i, a in enumerate(members_sorted):
            for b in members_sorted[i + 1 :]:
                c = pair_cosines.get((a, b))
                if c is None:
                    va, vb = embeddings.get(a), embeddings.get(b)
                    if va is None or vb is None:
                        continue
                    c = cosine(va, vb)
                local_pairs.append(EchoPair(a_id=a, b_id=b, cosine=round(c, 4)))
                total_pairs += 1
        if not local_pairs:
            continue
        peak = max(p.cosine for p in local_pairs)
        if peak < MIN_PEAK_COSINE:
            continue
        mean = sum(p.cosine for p in local_pairs) / len(local_pairs)

        # Centrality: for each note, sum of cosines with other members.
        centrality: dict[int, float] = {nid: 0.0 for nid in members_sorted}
        for p in local_pairs:
            centrality[p.a_id] += p.cosine
            centrality[p.b_id] += p.cosine

        # Canonical: highest centrality, tie-broken by longest body,
        # then by oldest id (lowest numeric id).
        canonical_id = max(
            members_sorted,
            key=lambda nid: (
                centrality[nid],
                len(notes_by_id[nid]["body"]),
                -nid,
            ),
        )

        member_dicts = [notes_by_id[nid] for nid in members_sorted]
        merged_title, merged_body, merged_tags, sentences, chars_unique = (
            _merged_payload(member_dicts, canonical_id)
        )
        chars_total = sum(len(notes_by_id[nid]["body"]) for nid in members_sorted)
        overlap_ratio = (
            sum(1 for s in sentences if s.is_duplicate) / len(sentences)
            if sentences
            else 0.0
        )

        clusters.append(
            EchoCluster(
                cluster_id=cluster_id,
                size=len(members_sorted),
                redundancy=round(mean, 4),
                peak_cosine=round(peak, 4),
                wasted_chars=max(chars_total - chars_unique, 0),
                chars_total=chars_total,
                chars_unique=chars_unique,
                canonical_id=canonical_id,
                members=[
                    EchoMember(
                        note_id=nid,
                        title=notes_by_id[nid]["title"],
                        body=notes_by_id[nid]["body"],
                        tags=notes_by_id[nid]["tags"],
                        created_at=notes_by_id[nid]["created_at"],
                        body_len=len(notes_by_id[nid]["body"]),
                        is_canonical=(nid == canonical_id),
                        centrality=round(centrality[nid], 4),
                    )
                    for nid in members_sorted
                ],
                pairs=local_pairs,
                merged_title=merged_title,
                merged_body=merged_body,
                merged_tags=merged_tags,
                sentences=sentences,
                overlap_ratio=round(overlap_ratio, 4),
            )
        )

    # Sort by wasted_chars desc, then redundancy desc — the biggest
    # win goes to the top so the user fixes the most impactful first.
    clusters.sort(key=lambda c: (c.wasted_chars, c.redundancy), reverse=True)
    if limit is not None:
        clusters = clusters[:limit]

    stats = {
        "notes": len(notes),
        "pairs_above_threshold": len(edges),
        "clusters": len(clusters),
        "wasted_chars_total": sum(c.wasted_chars for c in clusters),
        "biggest_redundancy": (
            max(c.redundancy for c in clusters) if clusters else 0.0
        ),
    }
    return EchoReport(
        threshold=threshold,
        total_notes=len(notes),
        candidate_pairs=len(edges),
        cluster_count=len(clusters),
        clusters=clusters,
        skipped_pair_count=len(skips),
        stats=stats,
    )


def _trim_runaway(
    members: list[int],
    pair_cosines: dict[tuple[int, int], float],
    cap: int,
) -> list[int]:
    """Keep the ``cap`` most-interconnected members and drop the long tail."""
    score: dict[int, float] = {m: 0.0 for m in members}
    for (a, b), c in pair_cosines.items():
        if a in score and b in score:
            score[a] += c
            score[b] += c
    keep = sorted(members, key=lambda m: score[m], reverse=True)[:cap]
    return sorted(keep)


def preview_merge(
    note_ids: list[int],
    *,
    canonical_id: int | None = None,
) -> EchoCluster:
    """Build a preview as if the supplied notes were one Echo cluster.

    The frontend lets the user pick a custom canonical or trim members
    out of a flagged cluster; this rebuilds the merge payload against
    that user choice without persisting anything.
    """
    if len(note_ids) < 2:
        raise ValueError("need at least 2 notes for a merge preview")
    notes_by_id = {n["id"]: n for n in store.all_notes() if n["id"] in set(note_ids)}
    missing = [nid for nid in note_ids if nid not in notes_by_id]
    if missing:
        raise LookupError(f"unknown note ids: {missing}")

    embeddings = dict(store.all_embeddings())
    members_sorted = sorted(notes_by_id.keys())

    local_pairs: list[EchoPair] = []
    for i, a in enumerate(members_sorted):
        for b in members_sorted[i + 1 :]:
            va, vb = embeddings.get(a), embeddings.get(b)
            if va is None or vb is None:
                continue
            c = cosine(va, vb)
            local_pairs.append(EchoPair(a_id=a, b_id=b, cosine=round(c, 4)))
    peak = max((p.cosine for p in local_pairs), default=0.0)
    mean = (
        sum(p.cosine for p in local_pairs) / len(local_pairs) if local_pairs else 0.0
    )
    centrality: dict[int, float] = {nid: 0.0 for nid in members_sorted}
    for p in local_pairs:
        centrality[p.a_id] += p.cosine
        centrality[p.b_id] += p.cosine

    if canonical_id is not None:
        if canonical_id not in notes_by_id:
            raise LookupError(f"canonical_id {canonical_id} not in members")
        canonical = canonical_id
    else:
        canonical = max(
            members_sorted,
            key=lambda nid: (
                centrality[nid],
                len(notes_by_id[nid]["body"]),
                -nid,
            ),
        )

    member_dicts = [notes_by_id[nid] for nid in members_sorted]
    merged_title, merged_body, merged_tags, sentences, chars_unique = (
        _merged_payload(member_dicts, canonical)
    )
    chars_total = sum(len(notes_by_id[nid]["body"]) for nid in members_sorted)
    overlap_ratio = (
        sum(1 for s in sentences if s.is_duplicate) / len(sentences)
        if sentences
        else 0.0
    )
    return EchoCluster(
        cluster_id=":".join(str(m) for m in members_sorted),
        size=len(members_sorted),
        redundancy=round(mean, 4),
        peak_cosine=round(peak, 4),
        wasted_chars=max(chars_total - chars_unique, 0),
        chars_total=chars_total,
        chars_unique=chars_unique,
        canonical_id=canonical,
        members=[
            EchoMember(
                note_id=nid,
                title=notes_by_id[nid]["title"],
                body=notes_by_id[nid]["body"],
                tags=notes_by_id[nid]["tags"],
                created_at=notes_by_id[nid]["created_at"],
                body_len=len(notes_by_id[nid]["body"]),
                is_canonical=(nid == canonical),
                centrality=round(centrality[nid], 4),
            )
            for nid in members_sorted
        ],
        pairs=local_pairs,
        merged_title=merged_title,
        merged_body=merged_body,
        merged_tags=merged_tags,
        sentences=sentences,
        overlap_ratio=round(overlap_ratio, 4),
    )


@dataclass
class MergeResult:
    merged_note_id: int
    merged_title: str
    deleted_ids: list[int]
    wasted_chars_recovered: int
    final_synapses: int


def merge_cluster(
    note_ids: list[int],
    *,
    canonical_id: int | None = None,
    title_override: str | None = None,
    body_override: str | None = None,
    tags_override: list[str] | None = None,
) -> MergeResult:
    """Execute the merge.

    The canonical note gets replaced in-place with the merged title /
    body / tags so any external references to its id keep resolving.
    Every other member is deleted. We recompute the graph afterwards
    only to report the new synapse count back to the UI; nothing about
    the merge itself depends on graph state.
    """
    if len(note_ids) < 2:
        raise ValueError("need at least 2 notes for a merge")
    preview = preview_merge(note_ids, canonical_id=canonical_id)
    final_title = (title_override or preview.merged_title).strip()
    final_body = (body_override or preview.merged_body).strip()
    final_tags = (
        tags_override
        if tags_override is not None
        else list(preview.merged_tags)
    )
    final_tags = [
        t for t in dict.fromkeys(tag.strip().lower() for tag in final_tags) if t
    ][:8]
    if not final_title:
        raise ValueError("merged title cannot be empty")
    if not final_body:
        raise ValueError("merged body cannot be empty")

    canonical = preview.canonical_id
    doomed = [m.note_id for m in preview.members if m.note_id != canonical]

    # Replace the canonical note in-place. We do it inside the same
    # connection block so the embedding cache stays consistent and the
    # delete-then-insert race window doesn't exist.
    from .embed import embed as _embed

    new_vec = _embed(f"{final_title}\n\n{final_body}")
    with store._conn() as con:  # noqa: SLF001
        con.execute(
            "UPDATE notes SET title = ?, body = ?, tags = ?, embedding = ? WHERE id = ?",
            (
                final_title,
                final_body,
                json.dumps(final_tags),
                store._pack(new_vec),  # noqa: SLF001
                canonical,
            ),
        )
        for nid in doomed:
            con.execute("DELETE FROM notes WHERE id = ?", (nid,))

    g = synapse.compute_graph()
    final_synapses = sum(
        1
        for e in g.edges
        if e["source"] == canonical or e["target"] == canonical
    )

    return MergeResult(
        merged_note_id=canonical,
        merged_title=final_title,
        deleted_ids=doomed,
        wasted_chars_recovered=preview.wasted_chars,
        final_synapses=final_synapses,
    )


# --------------------------------------------------------------- serializers

def _member_to_dict(m: EchoMember) -> dict:
    return {
        "note_id": m.note_id,
        "title": m.title,
        "body": m.body,
        "tags": m.tags,
        "created_at": m.created_at,
        "body_len": m.body_len,
        "is_canonical": m.is_canonical,
        "centrality": m.centrality,
    }


def _sentence_to_dict(s: EchoSentence) -> dict:
    return {
        "text": s.text,
        "note_ids": s.note_ids,
        "is_duplicate": s.is_duplicate,
        "is_canonical_source": s.is_canonical_source,
    }


def cluster_to_dict(c: EchoCluster) -> dict:
    return {
        "cluster_id": c.cluster_id,
        "size": c.size,
        "redundancy": c.redundancy,
        "peak_cosine": c.peak_cosine,
        "wasted_chars": c.wasted_chars,
        "chars_total": c.chars_total,
        "chars_unique": c.chars_unique,
        "canonical_id": c.canonical_id,
        "members": [_member_to_dict(m) for m in c.members],
        "pairs": [{"a_id": p.a_id, "b_id": p.b_id, "cosine": p.cosine} for p in c.pairs],
        "merged_title": c.merged_title,
        "merged_body": c.merged_body,
        "merged_tags": c.merged_tags,
        "sentences": [_sentence_to_dict(s) for s in c.sentences],
        "overlap_ratio": c.overlap_ratio,
    }


def report_to_dict(r: EchoReport) -> dict:
    return {
        "threshold": r.threshold,
        "total_notes": r.total_notes,
        "candidate_pairs": r.candidate_pairs,
        "cluster_count": r.cluster_count,
        "skipped_pair_count": r.skipped_pair_count,
        "clusters": [cluster_to_dict(c) for c in r.clusters],
        "stats": r.stats,
    }


# --------------------------------------------------------------- markdown export

def to_markdown(report: EchoReport) -> str:
    """Portable echo brief for paste-anywhere review."""
    out: list[str] = []
    out.append("# Echoes\n")
    out.append(
        f"_Threshold {report.threshold:.2f} · {report.cluster_count} cluster"
        f"{'' if report.cluster_count == 1 else 's'} · "
        f"{report.stats.get('wasted_chars_total', 0)} chars redundant_\n"
    )
    if not report.clusters:
        out.append("\n> No echoes detected at this threshold.\n")
        return "\n".join(out)
    for i, c in enumerate(report.clusters, start=1):
        out.append(f"\n## {i}. Cluster of {c.size} — {int(c.redundancy * 100)}% redundant\n")
        canonical = next(m for m in c.members if m.is_canonical)
        out.append(f"**Canonical**: _{canonical.title}_ (#{canonical.note_id})\n")
        out.append(
            f"_{c.wasted_chars} chars saved if merged · "
            f"{int(c.overlap_ratio * 100)}% sentence overlap · "
            f"peak cosine {c.peak_cosine:.2f}_\n"
        )
        for m in c.members:
            tag = " · canonical" if m.is_canonical else ""
            out.append(f"\n### #{m.note_id} — {m.title}{tag}\n")
            out.append(m.body + "\n")
        out.append("\n#### Suggested merged body\n")
        out.append(c.merged_body + "\n")
    return "\n".join(out)
