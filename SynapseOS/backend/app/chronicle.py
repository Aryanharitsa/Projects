"""Chronicle — temporal narrative of how each topic evolved.

Every other SynapseOS surface looks at the graph as a *snapshot*. Atlas
asks "which clusters are humming or cooling right now"; Synthesis asks
"what does this cluster say"; Echo asks "where are the duplicates". None
of them ask the question Chronicle exists for:

    *How has my thinking on this topic changed over time?*

A maturing second brain is not just a bag of notes; it's a trail of belief
revision. The same cluster a year apart can be made of very different
sentences. Chronicle walks each cluster chronologically, carves it into
**chapters** by time, and turns the chapter-to-chapter movement of the
embedding centroid into a readable story: which terms emerged, which
faded, when the inflection happened, how much the topic drifted overall.

Deterministic
-------------
A pure function of ``(notes, embeddings, threshold, top_k, params)``. No
LLM calls, no randomness. The same store at the same parameters always
returns the same chronicle — safe to call from a header probe without
debounce.

Chapters
--------
We bin a cluster's notes into ``target_chapters`` contiguous time
windows. The first cut uses equal-time slicing (``[t_min, t_max]`` split
into N equal-duration bins) so a quiet stretch followed by a burst still
lands in its own chapter. Any chapter with fewer than
``MIN_CHAPTER_NOTES`` members is merged into its smaller neighbor —
that's the standard hierarchical "minimum-leaf" merge, and it keeps the
chapter count adaptive to actual writing cadence. Clusters with fewer
than ``MIN_CLUSTER_NOTES`` total or shorter than ``MIN_SPAN_DAYS`` are
filtered out (no story to tell).

Drift
-----
Per chapter we compute the centroid (mean-pool + L2-normalize). The
**drift velocity** between consecutive chapters is ``1 - cosine`` of
their centroids — angular distance in embedding space. The **total
drift** is the same metric end-to-end. The **pivot index** is the gap
with the largest single drift velocity; that's the inflection moment of
the topic.

Vocabulary movement
-------------------
A chapter-aware TF-IDF where IDF is computed *within* the cluster (one
"document" per chapter) lets us name each chapter by its own distinctive
voice without being drowned by the cluster-wide vocabulary. The
**emerged** terms list = top in last chapter that were absent (or rare)
in first; **faded** = top in first that vanished in last. Stop-words are
stripped using the same list as ``community.py`` for consistency.

Stability category
------------------
``calm`` (drift < 0.10), ``shifting`` (0.10–0.25), ``pivoting`` (≥ 0.25).
The thresholds are tuned against the seed corpus so a healthy cluster
where the same topic was steadily developed lands as ``shifting``, while
a cluster whose final notes have visibly different vocabulary lands as
``pivoting``.

All math is pure stdlib; reuses the existing community detection,
embedding pipeline, and centroid math from ``atlas.py``.
"""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone

from . import community as community_mod
from . import store, synapse
from .embed import cosine

# Defaults tuned on the seed corpus: aim for 3–4 chapters when the data
# supports it, while still working on smaller clusters.
DEFAULT_MAX_CHAPTERS = 4
DEFAULT_MIN_CHAPTER_NOTES = 2
DEFAULT_MIN_CLUSTER_NOTES = 4
DEFAULT_MIN_SPAN_DAYS = 1.0

# Drift bands (1 - cosine of first/last centroid). Picked so:
#   - calm  → still about the same thing
#   - shifting → noticeably developing, same topic family
#   - pivoting → vocabulary has visibly turned over
CALM_MAX = 0.10
SHIFTING_MAX = 0.25

# How many distinctive terms to surface per chapter and per emerged/faded
# delta. Six is enough to read like a real epoch label; fewer feels thin.
TERMS_PER_CHAPTER = 5
TERMS_DELTA = 6

_TOKEN_RE = re.compile(r"[a-z][a-z0-9\-]{2,}")
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"\(\[])")

# A tiny stop-word list — keep in sync with community.py so a chapter
# isn't named "with" while the cluster name is something meaningful.
_STOP = frozenset(
    """a an the and or but of for to in on at by from with as is are was were be been being
    this that these those it its they them their there here we you i me my our your his her
    not no yes do does did so if then than else when while which who whom how what why where
    can could should would may might must will shall just only also more most less few many
    very too into onto out up down off over under between among per about across after before
    again any all some each every both either neither one two three first second new old same
    such other another own enough still even ever never always often sometimes maybe perhaps
    way ways thing things stuff like really kinda sorta etc vs via per
    """.split()
)


@dataclass
class ChronicleChapter:
    index: int
    date_start: str
    date_end: str
    span_days: int
    count: int
    terms: list[str]
    anchor_id: int
    anchor_title: str
    anchor_sentence: str
    member_ids: list[int]
    drift_in: float  # 1 - cosine vs previous chapter centroid (0 for first)


@dataclass
class ChronicleCluster:
    cluster_id: int
    name: str
    color: str
    size: int
    chapter_count: int
    chapters: list[ChronicleChapter]
    total_drift: float
    peak_drift: float
    pivot_index: int | None  # gap index (between chapters[pivot_index] and pivot_index+1)
    stability: float  # 1 - total_drift, clamped [0, 1]
    category: str  # calm / shifting / pivoting
    span_days: int
    cadence_days: float  # mean days between consecutive notes in this cluster
    emerged_terms: list[str]
    faded_terms: list[str]
    headline: str


@dataclass
class ChronicleReport:
    generated_at: str
    total_notes: int
    total_clusters: int
    eligible_clusters: int
    target_chapters: int
    min_cluster_notes: int
    min_span_days: float
    clusters: list[ChronicleCluster]
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
    return (b - a).total_seconds() / 86400.0


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


def _tokens(text: str) -> list[str]:
    return [t for t in _TOKEN_RE.findall(text.lower()) if t not in _STOP]


def _first_sentence(body: str, max_len: int = 220) -> str:
    """Lift the first non-trivial sentence as the chapter's representative line.

    We split on terminal punctuation followed by a capital/quote/digit so
    that "Mr. Foo" inside a body doesn't shred the first sentence. If the
    note is a single fragment, we just return it (truncated)."""
    body = (body or "").strip()
    if not body:
        return ""
    parts = _SENT_SPLIT.split(body)
    for p in parts:
        s = p.strip()
        # Skip leading list markers / numbering so the bullet sentence
        # reads cleanly.
        s = re.sub(r"^[\-•\*\d\.\)\(]+\s+", "", s)
        if len(s) >= 30:
            if len(s) > max_len:
                return s[: max_len - 1].rstrip() + "…"
            return s
    s = parts[0].strip()
    if len(s) > max_len:
        return s[: max_len - 1].rstrip() + "…"
    return s


def _date_label(d: datetime) -> str:
    return d.strftime("%b %d %Y")


def _choose_target_chapters(size: int, max_chapters: int) -> int:
    """Heuristic: roughly 1 chapter per 3 notes, capped + floored."""
    if size < DEFAULT_MIN_CLUSTER_NOTES:
        return 0
    if size <= 4:
        return 2
    if size <= 8:
        return min(3, max_chapters)
    return min(max_chapters, max(3, size // 3))


def _bin_by_time(
    members: list[tuple[int, datetime]],
    target_chapters: int,
) -> list[list[int]]:
    """Equal-duration time bins over [t_min, t_max], returned as id lists.

    Equal-time (not equal-count) intentionally: a flurry of notes in week
    1 followed by a single note three months later should *not* land in
    the same chapter — that single late note IS its own chapter, and the
    chronicle should make the gap visible."""
    if not members:
        return []
    members = sorted(members, key=lambda x: x[1])
    if target_chapters <= 1 or len(members) <= 2:
        return [[nid for nid, _ in members]]

    t_min = members[0][1]
    t_max = members[-1][1]
    total = _days_between(t_min, t_max)
    if total <= 0:
        return [[nid for nid, _ in members]]

    bin_width = total / target_chapters
    bins: list[list[int]] = [[] for _ in range(target_chapters)]
    for nid, t in members:
        offset = _days_between(t_min, t)
        idx = min(target_chapters - 1, int(offset / bin_width)) if bin_width else 0
        bins[idx].append(nid)
    # Drop empty leading/trailing bins (rare but possible if all notes
    # cluster in the middle of the span).
    while bins and not bins[0]:
        bins.pop(0)
    while bins and not bins[-1]:
        bins.pop()
    return bins


def _merge_thin_chapters(
    bins: list[list[int]],
    min_size: int,
) -> list[list[int]]:
    """Merge any chapter < min_size into its smaller neighbor.

    Standard hierarchical leaf-merge: scan, find the thinnest under-size
    chapter, glue it to whichever neighbor is itself smaller (or the only
    neighbor, at edges), repeat until all chapters clear ``min_size`` or
    only one chapter remains. Stable and deterministic — ties favor
    merging *backwards* so the chronicle's tail stays clean."""
    if not bins:
        return bins
    chapters = [list(b) for b in bins if b]
    while len(chapters) > 1:
        # Find the smallest under-size chapter.
        under = [(i, len(c)) for i, c in enumerate(chapters) if len(c) < min_size]
        if not under:
            break
        under.sort(key=lambda x: (x[1], x[0]))
        idx = under[0][0]
        if idx == 0:
            chapters[1] = chapters[0] + chapters[1]
            chapters.pop(0)
        elif idx == len(chapters) - 1:
            chapters[idx - 1] = chapters[idx - 1] + chapters[idx]
            chapters.pop(idx)
        else:
            # Glue into smaller neighbor; ties prefer the prior one.
            left_size, right_size = len(chapters[idx - 1]), len(chapters[idx + 1])
            if left_size <= right_size:
                chapters[idx - 1] = chapters[idx - 1] + chapters[idx]
                chapters.pop(idx)
            else:
                chapters[idx + 1] = chapters[idx] + chapters[idx + 1]
                chapters.pop(idx)
    return chapters


def _term_freq(note: dict) -> Counter[str]:
    """Title weight 3, tags weight 2, body weight 1 — matches naming.py."""
    tf: Counter[str] = Counter()
    for t in _tokens(note.get("title", "")):
        tf[t] += 3
    for tag in note.get("tags", []):
        for t in _tokens(tag):
            tf[t] += 2
    for t in _tokens(note.get("body", "")):
        tf[t] += 1
    return tf


def _chapter_terms(
    chapter_tfs: list[Counter[str]],
    target_idx: int,
) -> list[str]:
    """Rank terms by within-cluster TF-IDF.

    The "document" is the chapter; the "corpus" is the other chapters in
    THIS cluster. IDF = log(1 + N/df). A term that lives only in this
    chapter scores highest; a term that lives in every chapter contributes
    nothing.
    """
    if not chapter_tfs:
        return []
    n = len(chapter_tfs)
    df: Counter[str] = Counter()
    for tf in chapter_tfs:
        for term in tf:
            df[term] += 1
    target = chapter_tfs[target_idx]
    scored: list[tuple[float, str]] = []
    for term, c in target.items():
        if df[term] == 0:
            continue
        idf = math.log(1.0 + n / df[term])
        scored.append((c * idf, term))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [t for _, t in scored[:TERMS_PER_CHAPTER]]


def _delta_terms(
    head_tf: Counter[str],
    tail_tf: Counter[str],
    *,
    direction: str,
) -> list[str]:
    """Top terms gained (``direction='emerged'``) or lost (``'faded'``).

    Score = (count in primary) − 0.5 · (count in opposite). The 0.5
    weight is a deliberate forgiveness factor: a term doesn't have to be
    *entirely* absent in the opposite epoch to count as emerged/faded,
    just much rarer there. Without that, ``emerged_terms`` is empty for
    any cluster where the vocabulary slowly mutated rather than
    catastrophically replaced.
    """
    if direction == "emerged":
        primary, opposite = tail_tf, head_tf
    else:
        primary, opposite = head_tf, tail_tf
    scored: list[tuple[float, str]] = []
    for term, c in primary.items():
        score = c - 0.5 * opposite.get(term, 0)
        if score <= 0:
            continue
        # Demand at least a tiny absolute presence — keep ranking
        # dominated by terms with real frequency in the primary epoch.
        if c < 2:
            continue
        scored.append((score, term))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [t for _, t in scored[:TERMS_DELTA]]


def _classify(drift: float) -> str:
    if drift < CALM_MAX:
        return "calm"
    if drift < SHIFTING_MAX:
        return "shifting"
    return "pivoting"


def _headline(
    name: str,
    category: str,
    chapter_count: int,
    span_days: int,
    emerged: list[str],
) -> str:
    """One-line summary the UI uses as the chronicle's badge sentence."""
    if category == "calm":
        return (
            f"{chapter_count} chapter{'s' if chapter_count != 1 else ''} "
            f"over {span_days}d — the topic has been steadily restated."
        )
    if category == "shifting":
        if emerged:
            return (
                f"{chapter_count} chapters · vocabulary now leans on "
                f"\"{emerged[0]}\" — gradual development."
            )
        return f"{chapter_count} chapters — gradual development of {name}."
    # pivoting
    if emerged:
        return (
            f"{chapter_count} chapters · pivoted toward "
            f"\"{emerged[0]}\" — the framing visibly changed."
        )
    return f"{chapter_count} chapters — the framing of {name} visibly changed."


# ----------------------------------------------------------------- core


def compute_chronicle(
    threshold: float | None = None,
    top_k: int | None = None,
    max_chapters: int = DEFAULT_MAX_CHAPTERS,
    min_chapter_notes: int = DEFAULT_MIN_CHAPTER_NOTES,
    min_cluster_notes: int = DEFAULT_MIN_CLUSTER_NOTES,
    min_span_days: float = DEFAULT_MIN_SPAN_DAYS,
) -> ChronicleReport:
    """Build the chronicle report over every eligible cluster."""
    th = synapse.DEFAULT_THRESHOLD if threshold is None else threshold
    tk = synapse.DEFAULT_TOP_K if top_k is None else top_k
    max_chapters = max(2, min(int(max_chapters), 8))
    min_chapter_notes = max(1, int(min_chapter_notes))
    min_cluster_notes = max(2, int(min_cluster_notes))
    min_span_days = max(0.0, float(min_span_days))
    now = datetime.now(timezone.utc)

    g = synapse.compute_graph(threshold=th, top_k=tk)
    notes_by_id = {n["id"]: n for n in g.nodes}
    cmap = {n["id"]: n.get("community", 0) for n in g.nodes}
    built = community_mod.build_communities(cmap, notes_by_id)
    embeddings = dict(store.all_embeddings())
    notes_lookup = {n["id"]: n for n in store.all_notes()}

    out_clusters: list[ChronicleCluster] = []
    drift_total = 0.0
    chapters_total = 0
    pivot_total = 0

    for c in built:
        member_ids = [
            m for m in c.member_ids
            if m in embeddings and m in notes_lookup
        ]
        if len(member_ids) < min_cluster_notes:
            continue

        # Pair each member with its created_at timestamp; skip notes whose
        # timestamp is unparseable (shouldn't happen at runtime but the
        # seed-test rigs occasionally mint partial rows).
        timed: list[tuple[int, datetime]] = []
        for m in member_ids:
            t = _parse_iso(notes_lookup[m].get("created_at"))
            if t is None:
                continue
            timed.append((m, t))
        if len(timed) < min_cluster_notes:
            continue
        timed.sort(key=lambda x: x[1])

        span = _days_between(timed[0][1], timed[-1][1])
        if span < min_span_days:
            continue

        target = _choose_target_chapters(len(timed), max_chapters)
        bins = _bin_by_time(timed, target)
        bins = _merge_thin_chapters(bins, min_chapter_notes)
        # If the merge collapses to a single chapter, there's no narrative
        # to tell — drop the cluster from the report.
        if len(bins) < 2:
            continue

        # Build chapter primitives: ids → vecs, tfs, dates, anchor.
        timestamps = {nid: t for nid, t in timed}
        chapter_dates: list[tuple[datetime, datetime]] = []
        chapter_centroids: list[tuple[float, ...]] = []
        chapter_tfs: list[Counter[str]] = []
        anchor_ids: list[int] = []

        for ids in bins:
            ids_sorted = sorted(ids, key=lambda nid: timestamps.get(nid, now))
            vecs = [embeddings[nid] for nid in ids_sorted]
            centroid = _centroid(vecs)
            chapter_centroids.append(centroid)
            tf: Counter[str] = Counter()
            for nid in ids_sorted:
                tf.update(_term_freq(notes_lookup[nid]))
            chapter_tfs.append(tf)
            # Anchor = highest cosine to centroid; tie-break by oldest.
            best_id, best_sim = ids_sorted[0], -2.0
            for nid in ids_sorted:
                s = cosine(embeddings[nid], centroid)
                if s > best_sim:
                    best_sim = s
                    best_id = nid
            anchor_ids.append(best_id)
            chapter_dates.append((
                timestamps[ids_sorted[0]],
                timestamps[ids_sorted[-1]],
            ))

        # Inter-chapter drift velocities + total + pivot.
        drifts_in: list[float] = [0.0]
        for i in range(1, len(chapter_centroids)):
            d = max(0.0, 1.0 - cosine(chapter_centroids[i - 1], chapter_centroids[i]))
            drifts_in.append(round(d, 4))
        total_drift = max(0.0, 1.0 - cosine(chapter_centroids[0], chapter_centroids[-1]))
        total_drift = round(total_drift, 4)
        peak_drift = max(drifts_in[1:]) if len(drifts_in) > 1 else 0.0
        pivot_index: int | None = None
        if len(drifts_in) > 1 and peak_drift > 0:
            pivot_index = max(range(1, len(drifts_in)), key=lambda i: drifts_in[i]) - 1

        category = _classify(total_drift)
        emerged = _delta_terms(chapter_tfs[0], chapter_tfs[-1], direction="emerged")
        faded = _delta_terms(chapter_tfs[0], chapter_tfs[-1], direction="faded")

        # Per-chapter terms (within-cluster TF-IDF) + anchor sentence.
        chapters_out: list[ChronicleChapter] = []
        for i, ids in enumerate(bins):
            terms = _chapter_terms(chapter_tfs, i)
            d_start, d_end = chapter_dates[i]
            anchor_id = anchor_ids[i]
            anchor_note = notes_lookup[anchor_id]
            chapters_out.append(
                ChronicleChapter(
                    index=i,
                    date_start=d_start.replace(microsecond=0).isoformat(),
                    date_end=d_end.replace(microsecond=0).isoformat(),
                    span_days=max(0, int(round(_days_between(d_start, d_end)))),
                    count=len(ids),
                    terms=terms,
                    anchor_id=anchor_id,
                    anchor_title=anchor_note.get("title", "(untitled)"),
                    anchor_sentence=_first_sentence(anchor_note.get("body", "")),
                    member_ids=sorted(ids),
                    drift_in=drifts_in[i],
                )
            )

        # Cadence over the cluster's whole span — mean days between
        # consecutive notes. We pin to 0.0 for a single-day burst so the
        # UI can format it as "same-day cadence".
        if len(timed) > 1 and span > 0:
            cadence = round(span / max(1, len(timed) - 1), 2)
        else:
            cadence = 0.0

        chronicle = ChronicleCluster(
            cluster_id=c.id,
            name=c.name,
            color=c.color,
            size=len(member_ids),
            chapter_count=len(chapters_out),
            chapters=chapters_out,
            total_drift=total_drift,
            peak_drift=round(peak_drift, 4),
            pivot_index=pivot_index,
            stability=round(max(0.0, min(1.0, 1.0 - total_drift)), 4),
            category=category,
            span_days=int(round(span)),
            cadence_days=cadence,
            emerged_terms=emerged,
            faded_terms=faded,
            headline=_headline(
                c.name, category, len(chapters_out), int(round(span)), emerged
            ),
        )
        out_clusters.append(chronicle)
        drift_total += total_drift
        chapters_total += len(chapters_out)
        if pivot_index is not None:
            pivot_total += 1

    # Rank clusters: more drift × more notes floats up first. The
    # logarithmic size factor stops a 30-note giant from monopolizing the
    # ranking when a 4-note cluster has dramatically pivoted.
    def _score(c: ChronicleCluster) -> float:
        return c.total_drift * math.log(2 + c.size)

    out_clusters.sort(key=lambda c: (-_score(c), c.cluster_id))

    # Library-wide rollup.
    n_eligible = len(out_clusters)
    most_pivoting = out_clusters[0].name if out_clusters else ""
    most_stable_name = ""
    if out_clusters:
        ms = min(out_clusters, key=lambda c: (c.total_drift, c.cluster_id))
        most_stable_name = ms.name
    by_cat = Counter(c.category for c in out_clusters)
    summary = {
        "calm_count": by_cat.get("calm", 0),
        "shifting_count": by_cat.get("shifting", 0),
        "pivoting_count": by_cat.get("pivoting", 0),
        "mean_drift": round(drift_total / n_eligible, 4) if n_eligible else 0.0,
        "total_chapters": chapters_total,
        "pivots_detected": pivot_total,
        "most_pivoting": most_pivoting,
        "most_stable": most_stable_name,
    }

    return ChronicleReport(
        generated_at=now.replace(microsecond=0).isoformat(),
        total_notes=len(notes_by_id),
        total_clusters=len(built),
        eligible_clusters=n_eligible,
        target_chapters=max_chapters,
        min_cluster_notes=min_cluster_notes,
        min_span_days=min_span_days,
        clusters=out_clusters,
        summary=summary,
    )


# --------------------------------------------------------------- export


def to_markdown(r: ChronicleReport) -> str:
    """Portable Markdown brief — one section per cluster, paste-anywhere."""
    out: list[str] = []
    out.append(f"# Chronicle — {r.generated_at[:10]}")
    out.append("")
    out.append(
        f"_{r.total_notes} notes · {r.eligible_clusters}/{r.total_clusters} "
        f"clusters have a story · mean drift "
        f"{r.summary.get('mean_drift', 0.0):.2f}_"
    )
    out.append("")
    out.append("| Category | Count |")
    out.append("|---|---:|")
    out.append(f"| Calm | {r.summary.get('calm_count', 0)} |")
    out.append(f"| Shifting | {r.summary.get('shifting_count', 0)} |")
    out.append(f"| Pivoting | {r.summary.get('pivoting_count', 0)} |")
    out.append("")

    for c in r.clusters:
        out.append(f"## {c.name}  ·  *{c.category}*")
        out.append("")
        out.append(
            f"_{c.size} notes · {c.chapter_count} chapters · "
            f"{c.span_days}d span · cadence {c.cadence_days:g}d/note · "
            f"drift {c.total_drift:.2f}_"
        )
        out.append("")
        out.append(f"> {c.headline}")
        out.append("")
        if c.emerged_terms or c.faded_terms:
            if c.emerged_terms:
                out.append(f"- **Emerged:** {', '.join(c.emerged_terms)}")
            if c.faded_terms:
                out.append(f"- **Faded:** {', '.join(c.faded_terms)}")
            out.append("")
        for ch in c.chapters:
            label_a = _date_label(_parse_iso(ch.date_start) or datetime.now(timezone.utc))
            label_b = _date_label(_parse_iso(ch.date_end) or datetime.now(timezone.utc))
            tag = (
                f" · drift in {ch.drift_in:.2f}"
                if ch.drift_in > 0
                else ""
            )
            out.append(
                f"### Chapter {ch.index + 1} · {label_a} → {label_b}  "
                f"({ch.count} note{'s' if ch.count != 1 else ''}{tag})"
            )
            if ch.terms:
                out.append(f"*{' · '.join(ch.terms)}*")
            out.append("")
            out.append(f"**Anchor — {ch.anchor_title}**")
            if ch.anchor_sentence:
                out.append(f"> {ch.anchor_sentence}")
            out.append("")
        if c.pivot_index is not None:
            p = c.chapters[c.pivot_index + 1]
            out.append(
                f"_Pivot: chapter {c.pivot_index + 1} → {c.pivot_index + 2} "
                f"({p.drift_in:.2f} drift)._"
            )
            out.append("")

    return "\n".join(out).rstrip() + "\n"


def serialize(r: ChronicleReport) -> dict:
    return {
        "generated_at": r.generated_at,
        "total_notes": r.total_notes,
        "total_clusters": r.total_clusters,
        "eligible_clusters": r.eligible_clusters,
        "target_chapters": r.target_chapters,
        "min_cluster_notes": r.min_cluster_notes,
        "min_span_days": r.min_span_days,
        "summary": r.summary,
        "clusters": [
            {
                "cluster_id": c.cluster_id,
                "name": c.name,
                "color": c.color,
                "size": c.size,
                "chapter_count": c.chapter_count,
                "total_drift": c.total_drift,
                "peak_drift": c.peak_drift,
                "pivot_index": c.pivot_index,
                "stability": c.stability,
                "category": c.category,
                "span_days": c.span_days,
                "cadence_days": c.cadence_days,
                "emerged_terms": c.emerged_terms,
                "faded_terms": c.faded_terms,
                "headline": c.headline,
                "chapters": [
                    {
                        "index": ch.index,
                        "date_start": ch.date_start,
                        "date_end": ch.date_end,
                        "span_days": ch.span_days,
                        "count": ch.count,
                        "terms": ch.terms,
                        "anchor_id": ch.anchor_id,
                        "anchor_title": ch.anchor_title,
                        "anchor_sentence": ch.anchor_sentence,
                        "member_ids": ch.member_ids,
                        "drift_in": ch.drift_in,
                    }
                    for ch in c.chapters
                ],
            }
            for c in r.clusters
        ],
    }
