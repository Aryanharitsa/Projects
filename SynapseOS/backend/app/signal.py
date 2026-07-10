"""Signal — persistent watches over Compass research questions.

Compass answers *"what does my vault say right now?"* — you pin one
question, mark reads, watch a citation-stitched working answer grow. It
is the *in-flight* research surface. But real research isn't in-flight
for a single sitting; it's a thread you drop and pick up over days or
weeks. The moment you close Compass the question falls off the radar,
and re-opening it days later gives you *no* signal about what the vault
has learned in between — you have to remember your prior state and diff
by eye.

**Signal fixes that.** Pin a Compass question as a signal and the
current lens is snapshotted verbatim — coverage, in-lens set, read
set, citation set, per-subquestion progress, working-answer text. Every
time you view Signal, the lens is recomputed *now* and diffed against
that snapshot. You see, per pinned question:

- Coverage delta (mass-weighted, not count-weighted — mirrors Compass).
- Notes that **joined** the lens since pin (new writes shifted the
  relevance floor above ``RELEVANCE_FLOOR`` for these notes).
- Notes that **left** the lens (deleted, or dropped below floor after
  a subsequent edit).
- Notes you've **newly read** for this question since pin — the
  operational "what you actually did" delta.
- **Citations added / removed** — the working answer's evidence set
  churned; this is the highest-signal delta because it means the
  answer itself changed.
- Per-subquestion **coverage_pct delta** — which sub-aspect is now
  better-answered than at pin time.
- ``working_answer_changed`` — hash comparison of the extractive stitch.

The **status** is a single-word roll-up so a rail can rank at a glance:

- ``new``       — pinned less than an hour ago; nothing to diff yet.
- ``grown``     — coverage moved up ≥ ``GROWN_DELTA`` **or** at least one
                  new citation entered the working answer **or** at
                  least one new note joined the lens.
- ``shrunk``    — coverage moved down ≥ ``GROWN_DELTA``, or lens lost
                  more notes than it gained.
- ``fresh``     — user just refreshed (re-snapshotted); shows current
                  state as baseline with zero deltas.
- ``stable``    — nothing above thresholds.

**Refresh** re-snapshots the current lens — the "mark as read" of the
watch, so the next visit shows only what's changed *since your last
review of the delta*.

Persistence lives in ``signal_watches`` (id, question_id UNIQUE,
snapshot JSON, pinned_at, last_refreshed_at). One watch per question:
re-watching an already-watched question refreshes the snapshot rather
than creating a duplicate row. The join against ``compass_questions``
is cleaned up lazily on list so a deleted question drops its watch
silently.

Pure stdlib; the entire delta computation is a couple of set diffs and
one hash comparison. No LLM. Deterministic — same (snapshot, current
lens) → same delta.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Iterable

from . import compass as compass_engine

# ---------------------------------------------------------------- knobs

# Coverage delta magnitude (percentage points) at which a signal is
# classified ``grown`` / ``shrunk``. Below this the rail reports
# ``stable`` — small drifts from cluster re-embedding shouldn't
# masquerade as real research progress.
GROWN_DELTA = 3.0

# How long after pinning a signal reads as ``new`` (during which we don't
# bother diffing — snapshot IS current). One hour is enough that a user
# who pins → immediately reads three notes → refreshes doesn't see a
# noise "grown" verdict from their own two-minute session; it's the
# next day's delta that carries information.
NEW_WINDOW_SECONDS = 3600

# Cap on how many joined/left/new-read notes we include in the delta
# payload. The counts stay honest; only the enumerated list is capped.
LIST_CAP = 12


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts)
    except ValueError:
        return None


def _hash_answer(text: str) -> str:
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------- types


@dataclass
class LensNoteSummary:
    """Lean per-note shape used in every delta list. Full LensNote is
    heavier than the rail needs — a title / cluster tint / one-line
    excerpt is all Signal ever renders."""

    note_id: int
    title: str
    snippet: str
    relevance: float
    cluster_id: int | None = None
    cluster_name: str | None = None
    cluster_color: str | None = None


@dataclass
class SubqDelta:
    """Per-subquestion progress since pin."""

    term: str
    note_count_now: int
    note_count_pinned: int
    covered_now: int
    covered_pinned: int
    coverage_pct_now: float
    coverage_pct_pinned: float
    coverage_pct_delta: float
    sample_note_id: int


@dataclass
class CitationDelta:
    """One added / removed citation."""

    note_id: int
    title: str
    excerpt: str
    relevance: float


@dataclass
class SignalSnapshot:
    """Pin-state of a Compass lens. Small enough to JSON-blob per row."""

    coverage_pct: float
    in_lens_count: int
    in_lens_note_ids: list[int]
    read_note_ids: list[int]
    citation_note_ids: list[int]
    citations: list[dict]        # {note_id, title, excerpt, relevance}
    subquestions: list[dict]     # {term, note_count, covered, coverage_pct, sample_note_id}
    working_answer_hash: str
    generated_at: str            # ISO — when this snapshot was taken

    def to_json(self) -> str:
        return json.dumps(asdict(self), separators=(",", ":"), sort_keys=True)

    @classmethod
    def from_json(cls, raw: str) -> "SignalSnapshot":
        d = json.loads(raw)
        return cls(
            coverage_pct=float(d.get("coverage_pct", 0.0)),
            in_lens_count=int(d.get("in_lens_count", 0)),
            in_lens_note_ids=list(d.get("in_lens_note_ids", [])),
            read_note_ids=list(d.get("read_note_ids", [])),
            citation_note_ids=list(d.get("citation_note_ids", [])),
            citations=list(d.get("citations", [])),
            subquestions=list(d.get("subquestions", [])),
            working_answer_hash=str(d.get("working_answer_hash", "")),
            generated_at=str(d.get("generated_at", "")),
        )


@dataclass
class SignalDelta:
    """The full computed diff shown per pinned question."""

    question_id: int
    question_text: str
    pinned_at: str
    last_refreshed_at: str | None
    generated_at: str
    coverage_now: float
    coverage_pinned: float
    coverage_delta: float
    in_lens_now: int
    in_lens_pinned: int
    reads_new_count: int
    reads_new: list[LensNoteSummary]
    joined_since_count: int
    joined_since: list[LensNoteSummary]
    left_since_count: int
    left_since: list[LensNoteSummary]
    citations_added: list[CitationDelta]
    citations_removed: list[CitationDelta]
    subquestion_progress: list[SubqDelta]
    working_answer_changed: bool
    working_answer: str
    status: str
    headline: str
    stats: dict = field(default_factory=dict)


# ---------------------------------------------------------------- snapshot


def snapshot_from_lens(lens: compass_engine.Lens) -> SignalSnapshot:
    """Distill a full lens down to the shape we persist for diffing."""
    citation_note_ids = [c.note_id for c in lens.citations]
    return SignalSnapshot(
        coverage_pct=lens.coverage_pct,
        in_lens_count=lens.in_lens,
        in_lens_note_ids=[ln.note_id for ln in lens.notes],
        read_note_ids=[ln.note_id for ln in lens.notes if ln.read],
        citation_note_ids=citation_note_ids,
        citations=[
            {
                "note_id": c.note_id,
                "title": c.title,
                "excerpt": c.excerpt,
                "relevance": c.relevance,
            }
            for c in lens.citations
        ],
        subquestions=[
            {
                "term": s.term,
                "note_count": s.note_count,
                "covered": s.covered,
                "coverage_pct": s.coverage_pct,
                "sample_note_id": s.sample_note_id,
            }
            for s in lens.subquestions
        ],
        working_answer_hash=_hash_answer(lens.working_answer),
        generated_at=lens.generated_at,
    )


# ---------------------------------------------------------------- diff


def _lens_note_to_summary(ln: compass_engine.LensNote) -> LensNoteSummary:
    return LensNoteSummary(
        note_id=ln.note_id,
        title=ln.title,
        snippet=ln.snippet,
        relevance=ln.relevance,
        cluster_id=ln.cluster_id,
        cluster_name=ln.cluster_name,
        cluster_color=ln.cluster_color,
    )


def compute_delta(
    *,
    question_id: int,
    question_text: str,
    pinned_at: str,
    last_refreshed_at: str | None,
    snapshot: SignalSnapshot,
    current: compass_engine.Lens,
) -> SignalDelta:
    """Diff ``current`` against ``snapshot`` and classify."""
    now_lens_ids = {ln.note_id for ln in current.notes}
    now_read_ids = {ln.note_id for ln in current.notes if ln.read}
    pinned_lens_ids = set(snapshot.in_lens_note_ids)
    pinned_read_ids = set(snapshot.read_note_ids)

    joined_ids = now_lens_ids - pinned_lens_ids
    left_ids = pinned_lens_ids - now_lens_ids
    new_reads_ids = now_read_ids - pinned_read_ids

    # Rank enumerated lists by current-lens relevance so the cap surfaces
    # the most-relevant deltas — a joined note at the tail of the queue
    # is worth less than one at the head.
    current_by_id = {ln.note_id: ln for ln in current.notes}
    def _rank(nid: int) -> float:
        ln = current_by_id.get(nid)
        return ln.relevance if ln else 0.0

    joined_sorted = sorted(joined_ids, key=_rank, reverse=True)
    left_sorted = sorted(left_ids)  # left the lens → no current relevance to rank on
    new_reads_sorted = sorted(new_reads_ids, key=_rank, reverse=True)

    joined_summaries: list[LensNoteSummary] = []
    for nid in joined_sorted[:LIST_CAP]:
        ln = current_by_id.get(nid)
        if ln is not None:
            joined_summaries.append(_lens_note_to_summary(ln))

    # For notes that left the lens, look up the snapshot citations for a
    # title if we happen to have one; otherwise omit (best-effort — the
    # note may have been deleted).
    snapshot_titles: dict[int, str] = {}
    for c in snapshot.citations:
        snapshot_titles[int(c["note_id"])] = str(c["title"])

    left_summaries: list[LensNoteSummary] = []
    for nid in left_sorted[:LIST_CAP]:
        title = snapshot_titles.get(nid) or f"note #{nid}"
        left_summaries.append(
            LensNoteSummary(
                note_id=nid,
                title=title,
                snippet="",
                relevance=0.0,
            )
        )

    new_reads_summaries: list[LensNoteSummary] = []
    for nid in new_reads_sorted[:LIST_CAP]:
        ln = current_by_id.get(nid)
        if ln is not None:
            new_reads_summaries.append(_lens_note_to_summary(ln))

    # Citation churn — a citation is identified by note_id (the extractive
    # stitch may pick a different sentence, but the source is the source).
    pinned_cite_ids = set(snapshot.citation_note_ids)
    now_cite_ids = {c.note_id for c in current.citations}

    added_ids = now_cite_ids - pinned_cite_ids
    removed_ids = pinned_cite_ids - now_cite_ids

    citations_added: list[CitationDelta] = []
    for c in current.citations:
        if c.note_id in added_ids:
            citations_added.append(
                CitationDelta(
                    note_id=c.note_id,
                    title=c.title,
                    excerpt=c.excerpt,
                    relevance=c.relevance,
                )
            )

    citations_removed: list[CitationDelta] = []
    pinned_by_note = {int(c["note_id"]): c for c in snapshot.citations}
    for nid in sorted(removed_ids):
        c = pinned_by_note.get(nid)
        if c is not None:
            citations_removed.append(
                CitationDelta(
                    note_id=int(c["note_id"]),
                    title=str(c["title"]),
                    excerpt=str(c["excerpt"]),
                    relevance=float(c["relevance"]),
                )
            )

    # Subquestion progress — per-term. We match on term string; a term
    # can be added, removed, or shifted in coverage.
    pinned_subq_by_term = {str(s["term"]): s for s in snapshot.subquestions}
    now_subq_by_term = {s.term: s for s in current.subquestions}
    term_union = set(pinned_subq_by_term) | set(now_subq_by_term)

    subq_progress: list[SubqDelta] = []
    for term in term_union:
        p = pinned_subq_by_term.get(term)
        n = now_subq_by_term.get(term)
        p_cov = float(p["coverage_pct"]) if p else 0.0
        n_cov = n.coverage_pct if n else 0.0
        p_covered = int(p["covered"]) if p else 0
        n_covered = n.covered if n else 0
        p_notes = int(p["note_count"]) if p else 0
        n_notes = n.note_count if n else 0
        sample_id = n.sample_note_id if n else int(p["sample_note_id"]) if p else 0
        subq_progress.append(
            SubqDelta(
                term=term,
                note_count_now=n_notes,
                note_count_pinned=p_notes,
                covered_now=n_covered,
                covered_pinned=p_covered,
                coverage_pct_now=n_cov,
                coverage_pct_pinned=p_cov,
                coverage_pct_delta=round(n_cov - p_cov, 1),
                sample_note_id=sample_id,
            )
        )

    # Only surface subquestions that actually moved OR are net new / lost,
    # sorted by absolute movement first (biggest deltas at the top), then
    # by current coverage descending. Keeps the rail focused on signal.
    def _subq_key(s: SubqDelta) -> tuple:
        churn = abs(s.coverage_pct_delta) + (10.0 if s.note_count_pinned == 0 else 0.0)
        return (-churn, -s.coverage_pct_now)

    subq_progress = [
        s for s in subq_progress
        if abs(s.coverage_pct_delta) >= 0.5
        or s.note_count_pinned == 0
        or s.note_count_now == 0
    ]
    subq_progress.sort(key=_subq_key)

    coverage_delta = round(current.coverage_pct - snapshot.coverage_pct, 1)
    now_answer_hash = _hash_answer(current.working_answer)
    answer_changed = now_answer_hash != snapshot.working_answer_hash

    # ---- status classification -------------------------------------
    pinned_dt = _parse_iso(last_refreshed_at) or _parse_iso(pinned_at)
    now = datetime.now(timezone.utc)
    age = (now - pinned_dt).total_seconds() if pinned_dt else float("inf")

    if age < NEW_WINDOW_SECONDS:
        status = "new"
    elif coverage_delta >= GROWN_DELTA or citations_added or joined_ids:
        status = "grown"
    elif coverage_delta <= -GROWN_DELTA or len(left_ids) > len(joined_ids):
        status = "shrunk"
    else:
        status = "stable"

    # Headline — one sentence a rail can render without expansion.
    headline = _build_headline(
        coverage_delta=coverage_delta,
        joined=len(joined_ids),
        left=len(left_ids),
        new_reads=len(new_reads_ids),
        added_citations=len(citations_added),
        removed_citations=len(citations_removed),
        answer_changed=answer_changed,
        status=status,
    )

    stats = {
        "joined_ids_count": len(joined_ids),
        "left_ids_count": len(left_ids),
        "new_reads_count": len(new_reads_ids),
        "citations_added_count": len(citations_added),
        "citations_removed_count": len(citations_removed),
        "subquestion_moves": len(subq_progress),
        "top_relevance_now": current.stats.get("top_relevance", 0.0),
    }

    return SignalDelta(
        question_id=question_id,
        question_text=question_text,
        pinned_at=pinned_at,
        last_refreshed_at=last_refreshed_at,
        generated_at=current.generated_at,
        coverage_now=current.coverage_pct,
        coverage_pinned=snapshot.coverage_pct,
        coverage_delta=coverage_delta,
        in_lens_now=current.in_lens,
        in_lens_pinned=snapshot.in_lens_count,
        reads_new_count=len(new_reads_ids),
        reads_new=new_reads_summaries,
        joined_since_count=len(joined_ids),
        joined_since=joined_summaries,
        left_since_count=len(left_ids),
        left_since=left_summaries,
        citations_added=citations_added,
        citations_removed=citations_removed,
        subquestion_progress=subq_progress,
        working_answer_changed=answer_changed,
        working_answer=current.working_answer,
        status=status,
        headline=headline,
        stats=stats,
    )


def _build_headline(
    *,
    coverage_delta: float,
    joined: int,
    left: int,
    new_reads: int,
    added_citations: int,
    removed_citations: int,
    answer_changed: bool,
    status: str,
) -> str:
    """One-sentence rail summary. Order of concerns: coverage first
    (highest signal), then citation churn (answer moved), then lens
    membership, then reads."""
    if status == "new":
        return "Just pinned — snapshot is your baseline. Come back after you write more."

    parts: list[str] = []

    if coverage_delta > 0.5:
        parts.append(f"coverage +{coverage_delta:.1f} pts")
    elif coverage_delta < -0.5:
        parts.append(f"coverage {coverage_delta:.1f} pts")

    if added_citations and removed_citations:
        parts.append(f"{added_citations} new / {removed_citations} dropped citation(s)")
    elif added_citations:
        parts.append(f"+{added_citations} citation{'s' if added_citations != 1 else ''}")
    elif removed_citations:
        parts.append(f"-{removed_citations} citation{'s' if removed_citations != 1 else ''}")
    elif answer_changed:
        parts.append("working answer rewired")

    if joined:
        parts.append(f"{joined} note{'s' if joined != 1 else ''} joined lens")
    if left:
        parts.append(f"{left} left lens")
    if new_reads:
        parts.append(f"you read {new_reads}")

    if not parts:
        return "No movement since pin — quiet on this thread."
    return " · ".join(parts)


# ---------------------------------------------------------------- serializers


def _summary_dict(s: LensNoteSummary) -> dict:
    return {
        "note_id": s.note_id,
        "title": s.title,
        "snippet": s.snippet,
        "relevance": s.relevance,
        "cluster_id": s.cluster_id,
        "cluster_name": s.cluster_name,
        "cluster_color": s.cluster_color,
    }


def _citation_delta_dict(c: CitationDelta) -> dict:
    return {
        "note_id": c.note_id,
        "title": c.title,
        "excerpt": c.excerpt,
        "relevance": c.relevance,
    }


def _subq_delta_dict(s: SubqDelta) -> dict:
    return {
        "term": s.term,
        "note_count_now": s.note_count_now,
        "note_count_pinned": s.note_count_pinned,
        "covered_now": s.covered_now,
        "covered_pinned": s.covered_pinned,
        "coverage_pct_now": s.coverage_pct_now,
        "coverage_pct_pinned": s.coverage_pct_pinned,
        "coverage_pct_delta": s.coverage_pct_delta,
        "sample_note_id": s.sample_note_id,
    }


def delta_to_dict(d: SignalDelta) -> dict:
    return {
        "question_id": d.question_id,
        "question_text": d.question_text,
        "pinned_at": d.pinned_at,
        "last_refreshed_at": d.last_refreshed_at,
        "generated_at": d.generated_at,
        "coverage_now": d.coverage_now,
        "coverage_pinned": d.coverage_pinned,
        "coverage_delta": d.coverage_delta,
        "in_lens_now": d.in_lens_now,
        "in_lens_pinned": d.in_lens_pinned,
        "reads_new_count": d.reads_new_count,
        "reads_new": [_summary_dict(s) for s in d.reads_new],
        "joined_since_count": d.joined_since_count,
        "joined_since": [_summary_dict(s) for s in d.joined_since],
        "left_since_count": d.left_since_count,
        "left_since": [_summary_dict(s) for s in d.left_since],
        "citations_added": [_citation_delta_dict(c) for c in d.citations_added],
        "citations_removed": [_citation_delta_dict(c) for c in d.citations_removed],
        "subquestion_progress": [_subq_delta_dict(s) for s in d.subquestion_progress],
        "working_answer_changed": d.working_answer_changed,
        "working_answer": d.working_answer,
        "status": d.status,
        "headline": d.headline,
        "stats": d.stats,
    }


# ---------------------------------------------------------------- rank


def rank_deltas(deltas: list[SignalDelta]) -> list[SignalDelta]:
    """Order the signal rail: movers to the top, quiet to the bottom.

    Sort key (desc): (status_priority, absolute coverage delta, citation
    churn, joined-count, recency of pin). ``new`` ranks below ``grown`` /
    ``shrunk`` — a fresh pin has nothing for the user to act on yet."""
    priority = {"grown": 3, "shrunk": 2, "stable": 1, "new": 0, "fresh": 0}

    def _key(d: SignalDelta) -> tuple:
        churn = len(d.citations_added) + len(d.citations_removed)
        return (
            priority.get(d.status, 0),
            abs(d.coverage_delta),
            churn,
            d.joined_since_count,
            d.pinned_at,
        )

    return sorted(deltas, key=_key, reverse=True)


# ---------------------------------------------------------------- markdown


def to_markdown(deltas: list[SignalDelta]) -> str:
    """Portable rail export — a paste-anywhere snapshot of every pinned
    question's current-vs-baseline delta."""
    out: list[str] = []
    out.append("# Signal · watched research threads\n")
    out.append(f"_{len(deltas)} pinned · generated {_now_iso()}_\n")
    if not deltas:
        out.append("\n_No pinned questions. Pin a Compass question to watch it._\n")
        return "\n".join(out)

    for d in deltas:
        out.append(f"\n## {d.question_text}")
        out.append(f"_pinned {d.pinned_at} · status **{d.status}**_")
        out.append("")
        out.append(f"- {d.headline}")
        out.append(
            f"- Coverage: {d.coverage_now:.1f}% "
            f"(was {d.coverage_pinned:.1f}%, Δ {d.coverage_delta:+.1f})"
        )
        out.append(
            f"- Lens: {d.in_lens_now} notes now / {d.in_lens_pinned} at pin · "
            f"joined {d.joined_since_count} · left {d.left_since_count}"
        )
        if d.citations_added:
            out.append("\n**New citations**")
            for c in d.citations_added:
                out.append(f"- **{c.title}** (#{c.note_id}) — _{c.excerpt}_")
        if d.citations_removed:
            out.append("\n**Dropped citations**")
            for c in d.citations_removed:
                out.append(f"- ~~{c.title}~~ (#{c.note_id})")
        if d.subquestion_progress:
            out.append("\n**Sub-questions that moved**")
            for s in d.subquestion_progress[:8]:
                arrow = "↑" if s.coverage_pct_delta > 0 else ("↓" if s.coverage_pct_delta < 0 else "•")
                out.append(
                    f"- {arrow} **{s.term}** — {s.coverage_pct_now:.0f}% "
                    f"(was {s.coverage_pct_pinned:.0f}%, Δ {s.coverage_pct_delta:+.1f})"
                )
    return "\n".join(out) + "\n"
