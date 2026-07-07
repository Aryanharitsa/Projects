"""Recall — active-recall quiz layer over the synapse graph.

Every other surface in SynapseOS is either **observational** (Atlas,
Pulse, Chronicle, Tensions, Echo, Synthesis, Compass) or
**generative-writing** (Spark, Distill). None of them ever *test* the
user. That leaves a quiet failure mode: a mature second brain becomes
read-only. You write a note, it lands in a cluster, it earns a synapse
or two, you glance at it in a Daily Brief — and you never test whether
the ideas actually live in your head.

Recall closes that loop. It hands you a session of `k` cards
deterministically drawn from the graph and grades your answer with a
lightweight SM-2 style scheduler. Three card types cover different
retrieval modes:

- ``cloze``    — the most distinctive noun-phrase in the body is masked;
                 you type the missing phrase. Tests factual recall of
                 what the note *says*.
- ``prompt``   — the title becomes the question, the body reveals the
                 answer. Tests conceptual recall of what the note *is
                 about*, independent of exact phrasing.
- ``neighbor`` — given a source note, pick which of four candidates the
                 graph considers its strongest synapse. Tests structural
                 recall — do you remember how ideas are wired together?

Card selection weights **hard-to-recall** notes highest (lowest ease),
then **overdue** notes, then **stale + central** notes as a Revisit-style
fallback. A per-cluster cap (`MAX_PER_CLUSTER = 2`) keeps a single hot
topic from monopolizing a session; the same guard rail Revisit uses.

The scheduler is SM-2 lite:

    grade=0 (again)  →  ease -= 0.20  (floor 1.30)  ·  interval *= 0.30  ·  streak = 0
    grade=1 (hard)   →  ease -= 0.05                ·  interval *= 1.20
    grade=2 (good)   →  ease unchanged              ·  interval *= ease
    grade=3 (easy)   →  ease += 0.15  (cap 3.00)    ·  interval *= ease · 1.30  ·  streak += 1

Fresh cards start at `ease=2.5`, `interval_hours=24`. Interval is capped
at 90 days so even easy notes cycle back at least quarterly. Every state
mutation flows through :func:`grade_card` and is persisted in the
``recall_state`` table so a session survives a browser reload and the
scheduler is honest across restarts.

Pure stdlib. No new deps.
"""

from __future__ import annotations

import hashlib
import math
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Iterable, Literal

from .store import _conn  # local project — same SQLite file, no fanout


# ---------------------------------------------------------------- config

DEFAULT_K = 6
MAX_K = 12
MAX_PER_CLUSTER = 2

# SM-2 tuning
DEFAULT_EASE = 2.5
MIN_EASE = 1.30
MAX_EASE = 3.00
DEFAULT_INTERVAL_HOURS = 24.0
MAX_INTERVAL_HOURS = 24.0 * 90  # cap at 90 days
GRADE_AGAIN, GRADE_HARD, GRADE_GOOD, GRADE_EASY = 0, 1, 2, 3

# Card selection weights (sum ≈ 1.0 for the primary trio; jitter is tiny).
W_DUE = 0.45
W_LOW_EASE = 0.25
W_STALE = 0.20
W_CENTRAL = 0.10
JITTER_SPREAD = 0.03

# Notes shorter than this don't have enough material to hide a cloze or
# support a meaningful reveal; we skip them entirely rather than write a
# card the user will justifiably resent.
MIN_BODY_CHARS = 60

# Below this many neighbors, we never issue a neighbor-choice card.
# Otherwise the distractors get too weak and the "correct" answer is
# obvious from centrality alone.
NEIGHBOR_MIN_GRAPH_NEIGHBORS = 3
NEIGHBOR_DISTRACTORS = 3  # 1 correct + 3 wrong = 4 options total

# Stopwords — small, focused; anything a cloze would embarrass itself on.
_STOP = frozenset(
    """
    a an the and or but so of to in on at by for from with without into
    onto is are was were be been being am has have had do does did will
    would could should may might must can shall this that these those
    it its it's their theirs there here when where why how what which
    who whom whose all any some no not nor if then else than as too
    very just also only own same such via per about above below over
    under against while during before after between within because
    since yet still like likely often sometimes never usually many
    more most much less least few fewer other another each every both
    either neither one two three you your yours we us our ours they
    them their theirs he him his she her hers me my mine i i've you're
    we're they're don't didn't hasn't haven't isn't aren't wasn't
    weren't won't wouldn't couldn't shouldn't
    """.split()
)


# --------------------------------------------------------------- schema

def init_recall_schema() -> None:
    """Idempotent schema init. Called from the FastAPI startup hook next
    to ``store.init_db`` so a fresh checkout starts with the right table
    without a manual migration step."""
    with _conn() as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS recall_state (
                note_id           INTEGER PRIMARY KEY,
                ease              REAL NOT NULL DEFAULT 2.5,
                interval_hours    REAL NOT NULL DEFAULT 24.0,
                next_due          TEXT NOT NULL,
                streak            INTEGER NOT NULL DEFAULT 0,
                reviews           INTEGER NOT NULL DEFAULT 0,
                lapses            INTEGER NOT NULL DEFAULT 0,
                last_grade        INTEGER,
                last_reviewed_at  TEXT
            )
            """
        )
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_recall_due ON recall_state(next_due)"
        )


# ------------------------------------------------------------ dataclasses

CardKind = Literal["cloze", "prompt", "neighbor"]


@dataclass
class NeighborChoice:
    note_id: int
    title: str
    is_correct: bool
    cluster_id: int | None = None
    cluster_color: str | None = None


@dataclass
class Card:
    id: str                  # `${kind}-${note_id}` — stable, session-scoped
    kind: CardKind
    note_id: int
    title: str
    cluster_id: int | None
    cluster_name: str | None
    cluster_color: str | None
    # cloze / prompt payload
    prompt_text: str         # what the user sees before reveal
    answer_text: str         # what the user sees after reveal (canonical)
    cloze_answer: str        # exact phrase, lowercase, for auto-grading
    body_before: str         # text preceding the masked phrase (cloze)
    body_after: str          # text following the masked phrase (cloze)
    body_snippet: str        # for prompt: sentence following the title cue
    # neighbor-choice payload
    choices: list[NeighborChoice]
    correct_choice_id: int | None
    # scheduler state at the time of session build
    ease: float
    interval_hours: float
    next_due: str
    streak: int
    reviews: int
    lapses: int
    days_overdue: float
    days_since_seen: float | None
    # rationale for the UI
    reasons: list[str] = field(default_factory=list)


@dataclass
class SessionOut:
    generated_at: str
    session_id: str
    total_notes: int
    eligible_notes: int
    k: int
    cards: list[Card]
    streak_days: int
    due_now: int
    stats: dict = field(default_factory=dict)


@dataclass
class GradeResult:
    note_id: int
    grade: int
    ease: float
    interval_hours: float
    next_due: str
    streak: int
    reviews: int
    lapses: int
    next_due_phrase: str


@dataclass
class ClusterMastery:
    cluster_id: int
    cluster_name: str
    cluster_color: str
    size: int
    reviewed: int
    known: int          # streak >= 2, reviewed at least once
    mastery: float      # known / size
    mean_ease: float
    due_now: int


@dataclass
class SummaryOut:
    generated_at: str
    total_notes: int
    reviewed_notes: int
    due_now: int
    streak_days: int
    mean_ease: float
    total_reviews: int
    mastery_overall: float
    clusters: list[ClusterMastery]


# ---------------------------------------------------------------- helpers

_ISO_TZ = timezone.utc


def _now(now: datetime | None = None) -> datetime:
    n = now or datetime.now(_ISO_TZ)
    if n.tzinfo is None:
        n = n.replace(tzinfo=_ISO_TZ)
    return n.replace(microsecond=0)


def _iso(d: datetime) -> str:
    return _now(d).isoformat()


def _parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=_ISO_TZ)
    return d


def _jitter(note_id: int, salt: str) -> float:
    h = hashlib.sha256(f"{note_id}|{salt}".encode("utf-8")).digest()
    return ((int.from_bytes(h[:8], "big") / 2**64) * 2.0 - 1.0) * JITTER_SPREAD


def _phrase_next_due(now: datetime, next_due: datetime) -> str:
    """Human-readable ``"in 2d 4h"`` / ``"due now"`` / ``"in 12m"``."""
    delta = next_due - now
    total = int(delta.total_seconds())
    if total <= 0:
        return "due now"
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    mins = rem // 60
    if days >= 1:
        return f"in {days}d {hours}h" if hours else f"in {days}d"
    if hours >= 1:
        return f"in {hours}h {mins}m" if mins else f"in {hours}h"
    if mins >= 1:
        return f"in {mins}m"
    return "in <1m"


def _sentences(body: str) -> list[str]:
    """Split on . ! ? preserving compact form. Cheap heuristic — good
    enough for note-length bodies; we don't need spaCy-quality
    tokenisation to make one masked phrase choice."""
    text = re.sub(r"\s+", " ", body.strip())
    if not text:
        return []
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'\-])", text)
    return [p.strip() for p in parts if p.strip()]


_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9\-]{2,}")
_NUM_RE = re.compile(r"^\d+$")


def _tokens(text: str) -> list[str]:
    return [t.lower() for t in _WORD_RE.findall(text)]


def _distinctive_terms(
    body: str,
    corpus_df: dict[str, int],
    n_docs: int,
) -> list[tuple[str, float]]:
    """Score noun-phrase-y candidates by TF · IDF flavour.

    We consider unigrams and bigrams. Stop-words / short tokens / pure
    digits are skipped. Distinct terms shipped canonical-cased from the
    first occurrence in the body so the masking looks right even when
    the token appears twice with different casing.

    Ranking bias: capitalized surface forms get a **1.6× nudge** (they
    read as concept phrases — "Louvain method", "Node embeddings", proper
    nouns — instead of straddling a noun-verb boundary like "graphs
    assigns"). Bigrams score by ``max(df_a, df_b)`` for IDF instead of
    ``min`` because we want *both* halves to carry signal — a rare word
    yoked to a common one shouldn't drag the score up on the common
    word's back. Common-verb heads are penalized outright so the top
    candidate reliably reads as a noun phrase."""
    # Preserve original casing per token — the first occurrence wins for
    # display, keeping "Kubernetes" / "OKR" recognisable after masking.
    original_case: dict[str, str] = {}
    lower_positions: list[str] = []
    for m in _WORD_RE.finditer(body):
        tok = m.group(0)
        low = tok.lower()
        if low not in original_case:
            original_case[low] = tok
        lower_positions.append(low)

    tf_uni: dict[str, int] = {}
    for tok in lower_positions:
        if tok in _STOP or len(tok) < 4 or _NUM_RE.match(tok):
            continue
        tf_uni[tok] = tf_uni.get(tok, 0) + 1

    tf_bi: dict[str, int] = {}
    for a, b in zip(lower_positions, lower_positions[1:]):
        if a in _STOP or b in _STOP:
            continue
        if len(a) < 3 or len(b) < 3 or _NUM_RE.match(a) or _NUM_RE.match(b):
            continue
        # A bigram whose head is a common English verb form usually
        # cuts across a natural noun-verb boundary — the resulting
        # cloze reads as "____" straddling a phrase break, which is
        # exactly what makes an SM-2 card feel arbitrary. Skip.
        if a in _COMMON_VERBS or b in _COMMON_VERBS:
            continue
        key = f"{a} {b}"
        tf_bi[key] = tf_bi.get(key, 0) + 1

    out: list[tuple[str, float]] = []
    n_docs_safe = max(1, n_docs)

    def _cap_bonus(surface: str) -> float:
        # Any capital letter after position 0 → strong concept signal
        # (proper noun, acronym, or a "The Louvain method"-style phrase
        # whose middle token stays capitalized). Position-0 capital
        # ("Modularity") is worth a mild bonus because it *may* be a
        # sentence starter, not a concept — but often it's both.
        stripped = surface.lstrip()
        if not stripped:
            return 1.0
        mid_cap = any(c.isupper() for c in stripped[1:])
        head_cap = stripped[0].isupper()
        if mid_cap:
            return 1.6
        if head_cap:
            return 1.15
        return 1.0

    for term, tf in tf_uni.items():
        df = max(1, corpus_df.get(term, 0))
        idf = math.log((n_docs_safe + 1.0) / df)
        surface = original_case.get(term, term)
        score = tf * idf * _cap_bonus(surface)
        out.append((surface, score))
    for term, tf in tf_bi.items():
        # Use max(df) so both halves must be rare for the bigram to
        # score. This prevents "graphs assigns" from scoring high on
        # the back of "assigns" when "graphs" is common.
        a, b = term.split(" ", 1)
        df_a = max(1, corpus_df.get(a, 0))
        df_b = max(1, corpus_df.get(b, 0))
        idf = math.log((n_docs_safe + 1.0) / max(df_a, df_b))
        # Rebuild the casing from the original-case unigram table so
        # "Louvain method" survives as capitalized.
        surface = " ".join(original_case.get(part, part) for part in (a, b))
        # Bigrams get a 1.25× intrinsic bonus (they carry more concept
        # per masked span) *and* the capitalization bonus, so a
        # capitalized bigram like "Louvain method" beats any unigram
        # unless the unigram is genuinely more distinctive.
        score = tf * idf * 1.25 * _cap_bonus(surface)
        out.append((surface, score))

    out.sort(key=lambda kv: kv[1], reverse=True)
    return out


# Common English verb heads that stitch two nouns together mid-sentence.
# Anything that would produce a "graphs assigns" / "method optimizes"
# style bigram — those aren't concept phrases, they're just adjacent
# tokens. Skipping them at bigram-construction time is cheaper than
# trying to re-rank after the fact.
_COMMON_VERBS = frozenset(
    """
    assigns assign assigned assigns is are was were be been being am has
    have had do does did will would could should may might must can
    shall optimizes optimize optimized converges converge converged
    maps map mapped treats treat treated produces produce produced
    creates create created makes make made yields yield yielded gives
    give gave uses use used includes include included has have adds
    add added forms form formed weights weight weighted returns return
    returned computes compute computed derives derive derived captures
    capture captured provides provide provided supports support supported
    """.split()
)


def _corpus_df(notes: Iterable[dict]) -> tuple[dict[str, int], int]:
    """Document-frequency table over the lowercased unigram vocabulary.
    Bigram DF is approximated by ``min(df_a, df_b)`` which keeps this
    O(N · body_length) with no bigram post-processing."""
    df: dict[str, int] = {}
    n = 0
    for n_row in notes:
        n += 1
        seen: set[str] = set()
        for tok in _tokens(f"{n_row.get('title', '')} {n_row.get('body', '')}"):
            if tok in _STOP or len(tok) < 4 or _NUM_RE.match(tok):
                continue
            if tok in seen:
                continue
            seen.add(tok)
            df[tok] = df.get(tok, 0) + 1
    return df, n


def _pick_cloze(
    note: dict,
    corpus_df: dict[str, int],
    n_docs: int,
) -> tuple[str, str, str] | None:
    """Return ``(before, phrase, after)`` for the highest-scoring
    distinctive phrase found in the body. Falls back to ``None`` when no
    candidate clears the "worth masking" bar — the caller falls through
    to a prompt-style card instead."""
    body = note.get("body", "").strip()
    if len(body) < MIN_BODY_CHARS:
        return None
    title_lower = note.get("title", "").lower()
    candidates = _distinctive_terms(body, corpus_df, n_docs)
    for phrase, _score in candidates:
        if not phrase:
            continue
        low = phrase.lower()
        # Don't mask phrases that are literally the title (the reveal
        # would be trivial with the title already on the card).
        if low == title_lower.strip().rstrip(".?!"):
            continue
        idx = body.lower().find(low)
        if idx < 0:
            continue
        before = body[:idx]
        after = body[idx + len(phrase):]
        # The surrounding context is what makes the mask solvable; we
        # require at least 40 chars of context in total (before+after)
        # AND at least 12 chars after the mask (a phrase at the tail of
        # a short body has no follow-through to anchor recall).
        # Note we don't demand much *before* — a leading article like
        # "The ___ optimizes modularity" is a fine cloze because the
        # verb+object tail is what anchors the mask.
        context_len = len(before.strip()) + len(after.strip())
        if context_len < 40 or len(after.strip()) < 12:
            continue
        return before, phrase, after
    return None


def _title_prompt(title: str) -> str:
    t = title.strip().rstrip(".?!")
    lower = t.lower()
    # Cheap templating — the *content* is the title; the wrapper just
    # frames it as a question so the card doesn't read like a
    # declarative sentence.
    if lower.startswith(("why", "what", "how", "when", "where", "who", "which")):
        return f"{t}?"
    if lower.startswith(("is ", "does ", "do ", "can ", "should ", "will ")):
        return f"{t}?"
    if len(t.split()) <= 4:
        return f"What is “{t}”?"
    return f"Explain in your own words: “{t}”."


def _make_neighbor_card(
    note: dict,
    correct_neighbor: dict,
    distractors: list[dict],
    cluster_lookup: dict[int, dict],
    cmap: dict[int, int],
    salt: str,
) -> list[NeighborChoice]:
    """Interleave the correct neighbor with the distractors in a
    deterministic pseudo-random order (session-salted so two loads of
    the same session look the same but two sessions differ)."""
    all_choices = [(correct_neighbor, True)]
    for d in distractors:
        all_choices.append((d, False))
    # Stable deterministic shuffle via SHA of the note id + choice id.
    def _key(item: tuple[dict, bool]) -> str:
        n = item[0]
        return hashlib.sha256(
            f"{salt}|{note['id']}|{n['id']}".encode("utf-8")
        ).hexdigest()

    all_choices.sort(key=_key)
    out: list[NeighborChoice] = []
    for pick, is_correct in all_choices:
        pid = int(pick["id"])
        cid = cmap.get(pid)
        cinfo = cluster_lookup.get(cid) if cid is not None else None
        out.append(
            NeighborChoice(
                note_id=pid,
                title=str(pick["title"])[:120],
                is_correct=is_correct,
                cluster_id=cid,
                cluster_color=(cinfo or {}).get("color"),
            )
        )
    return out


def _snippet(body: str, max_chars: int = 240) -> str:
    text = re.sub(r"\s+", " ", body.strip())
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars].rsplit(" ", 1)[0]
    return f"{cut}…"


# ------------------------------------------------------- state I/O

def _load_all_state() -> dict[int, dict]:
    with _conn() as con:
        rows = con.execute(
            "SELECT note_id, ease, interval_hours, next_due, streak, reviews, "
            "lapses, last_grade, last_reviewed_at FROM recall_state"
        ).fetchall()
        return {int(r["note_id"]): dict(r) for r in rows}


def _upsert_state(note_id: int, state: dict) -> None:
    with _conn() as con:
        con.execute(
            """
            INSERT INTO recall_state
                (note_id, ease, interval_hours, next_due, streak, reviews,
                 lapses, last_grade, last_reviewed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(note_id) DO UPDATE SET
                ease = excluded.ease,
                interval_hours = excluded.interval_hours,
                next_due = excluded.next_due,
                streak = excluded.streak,
                reviews = excluded.reviews,
                lapses = excluded.lapses,
                last_grade = excluded.last_grade,
                last_reviewed_at = excluded.last_reviewed_at
            """,
            (
                note_id,
                state["ease"],
                state["interval_hours"],
                state["next_due"],
                state["streak"],
                state["reviews"],
                state["lapses"],
                state["last_grade"],
                state["last_reviewed_at"],
            ),
        )


def _fresh_state(now: datetime) -> dict:
    return {
        "ease": DEFAULT_EASE,
        "interval_hours": DEFAULT_INTERVAL_HOURS,
        "next_due": _iso(now),
        "streak": 0,
        "reviews": 0,
        "lapses": 0,
        "last_grade": None,
        "last_reviewed_at": None,
    }


# ---------------------------------------------------- session builder

def _score_candidate(
    note: dict,
    state: dict | None,
    weights: dict[int, float],
    now: datetime,
    salt: str,
) -> float:
    """Composite priority score. Higher = surface sooner."""
    nid = int(note["id"])

    if state is None:
        due_component = 1.0  # never rehearsed → maximum urgency
        ease_component = 1.0
        stale = 1.0
    else:
        next_due = _parse_iso(state["next_due"]) or now
        overdue_hours = max(0.0, (now - next_due).total_seconds() / 3600.0)
        # Saturate at 7 days overdue — beyond that it's all the same.
        due_component = min(1.0, overdue_hours / (24.0 * 7))
        # Map ease → [0, 1] where MIN_EASE → 1 (hardest), MAX_EASE → 0.
        span = max(1e-6, MAX_EASE - MIN_EASE)
        ease_component = max(0.0, min(1.0, (MAX_EASE - state["ease"]) / span))
        # Staleness contribution — days since last review; capped at 21d.
        last = _parse_iso(state.get("last_reviewed_at"))
        days = (
            (now - last).total_seconds() / 86400.0
            if last is not None else 21.0
        )
        stale = max(0.0, min(1.0, days / 21.0))

    centrality = float(weights.get(nid, 0.0))
    score = (
        W_DUE * due_component
        + W_LOW_EASE * ease_component
        + W_STALE * stale
        + W_CENTRAL * centrality
    )
    return score + _jitter(nid, salt)


def _build_neighbor_index(
    node_ids: list[int],
    edges: list[tuple[int, int, float]],
) -> dict[int, list[tuple[int, float]]]:
    adj: dict[int, list[tuple[int, float]]] = {nid: [] for nid in node_ids}
    for u, v, s in edges:
        adj[u].append((v, s))
        adj[v].append((u, s))
    for nid in adj:
        adj[nid].sort(key=lambda kv: kv[1], reverse=True)
    return adj


def build_session(
    *,
    k: int,
    now: datetime,
    notes: list[dict],
    cmap: dict[int, int],
    community_lookup: dict[int, dict],
    weights: dict[int, float],
    graph_edges: list[tuple[int, int, float]],
    session_salt: str,
) -> SessionOut:
    """Assemble a session of ``k`` cards, deterministic under
    ``session_salt``. See module docstring for the selection order."""
    k = max(1, min(MAX_K, int(k)))
    if not notes:
        return SessionOut(
            generated_at=_iso(now),
            session_id=session_salt,
            total_notes=0,
            eligible_notes=0,
            k=0,
            cards=[],
            streak_days=0,
            due_now=0,
        )

    corpus_df, n_docs = _corpus_df(notes)
    state_by_id = _load_all_state()

    # Eligibility filter: skip notes with tiny bodies (nothing to mask,
    # nothing to prompt). This also keeps sessions from becoming a wall
    # of 20-char stubs on a fresh vault.
    eligible = [n for n in notes if len(n.get("body", "").strip()) >= 40]
    if not eligible:
        eligible = notes  # degrade gracefully — better a lo-fi card than none

    scored: list[tuple[float, dict]] = []
    for n in eligible:
        s = _score_candidate(n, state_by_id.get(int(n["id"])), weights, now, session_salt)
        scored.append((s, n))
    scored.sort(key=lambda kv: kv[0], reverse=True)

    adj = _build_neighbor_index([int(n["id"]) for n in notes], graph_edges)
    notes_by_id = {int(n["id"]): n for n in notes}

    picked: list[Card] = []
    per_cluster: dict[int | None, int] = {}
    seen_ids: set[int] = set()

    for _score, note in scored:
        if len(picked) >= k:
            break
        nid = int(note["id"])
        if nid in seen_ids:
            continue
        cid = cmap.get(nid)
        if per_cluster.get(cid, 0) >= MAX_PER_CLUSTER:
            continue

        card = _make_card(
            note=note,
            state=state_by_id.get(nid),
            cmap=cmap,
            community_lookup=community_lookup,
            corpus_df=corpus_df,
            n_docs=n_docs,
            adj=adj,
            notes_by_id=notes_by_id,
            now=now,
            session_salt=session_salt,
        )
        if card is None:
            continue
        picked.append(card)
        seen_ids.add(nid)
        per_cluster[cid] = per_cluster.get(cid, 0) + 1

    due_now = sum(
        1
        for st in state_by_id.values()
        if (_parse_iso(st["next_due"]) or now) <= now
    )
    streak_days = _current_streak(state_by_id, now)

    return SessionOut(
        generated_at=_iso(now),
        session_id=session_salt,
        total_notes=len(notes),
        eligible_notes=len(eligible),
        k=len(picked),
        cards=picked,
        streak_days=streak_days,
        due_now=due_now,
        stats={
            "reviewed_notes": sum(1 for s in state_by_id.values() if s["reviews"] > 0),
            "mean_ease": round(
                sum(s["ease"] for s in state_by_id.values()) / len(state_by_id)
                if state_by_id else DEFAULT_EASE,
                3,
            ),
            "cloze_count": sum(1 for c in picked if c.kind == "cloze"),
            "prompt_count": sum(1 for c in picked if c.kind == "prompt"),
            "neighbor_count": sum(1 for c in picked if c.kind == "neighbor"),
        },
    )


def _make_card(
    *,
    note: dict,
    state: dict | None,
    cmap: dict[int, int],
    community_lookup: dict[int, dict],
    corpus_df: dict[str, int],
    n_docs: int,
    adj: dict[int, list[tuple[int, float]]],
    notes_by_id: dict[int, dict],
    now: datetime,
    session_salt: str,
) -> Card | None:
    """Pick the strongest card type for ``note`` and materialize it.

    Preference: neighbor > cloze > prompt. Neighbor comes first because
    it's the only card type that exercises the *graph* rather than the
    note body — and the graph is the product."""
    nid = int(note["id"])
    cid = cmap.get(nid)
    cinfo = community_lookup.get(cid) if cid is not None else None
    cluster_name = (cinfo or {}).get("name")
    cluster_color = (cinfo or {}).get("color")

    # scheduler state at snapshot time
    st = state or _fresh_state(now)
    next_due_dt = _parse_iso(st["next_due"]) or now
    overdue = max(0.0, (now - next_due_dt).total_seconds() / 86400.0)
    last = _parse_iso(st.get("last_reviewed_at"))
    days_since_seen = (
        round((now - last).total_seconds() / 86400.0, 2)
        if last is not None else None
    )

    reasons: list[str] = []
    if state is None:
        reasons.append("never rehearsed")
    elif overdue > 0:
        reasons.append(f"overdue by {round(overdue, 1)}d")
    if state and state["ease"] <= MIN_EASE + 0.15:
        reasons.append("low ease — hard for you")
    if state and state["streak"] >= 3:
        reasons.append(f"streak {state['streak']}")

    # 1) Neighbor-choice card — cheapest to assemble, exercises the graph.
    neighbors = adj.get(nid, [])
    if len(neighbors) >= NEIGHBOR_MIN_GRAPH_NEIGHBORS:
        # Salt with the note+day so a repeat session on the same day looks
        # the same but the next day's session shuffles.
        seed = f"{session_salt}|neighbor|{nid}"
        correct_id, _corr_strength = neighbors[0]
        correct_note = notes_by_id.get(correct_id)
        # Pick distractors from *other* notes not currently adjacent.
        adj_ids = {n for n, _ in neighbors}
        adj_ids.add(nid)
        distractor_pool = [
            n for _id, n in notes_by_id.items()
            if _id not in adj_ids
        ]
        # Sort distractors by a stable pseudo-random key so the same
        # note+salt yields the same distractors.
        distractor_pool.sort(
            key=lambda n: hashlib.sha256(
                f"{seed}|{n['id']}".encode("utf-8")
            ).hexdigest()
        )
        # Prefer distractors from a *different* cluster than the source —
        # a same-cluster distractor is too plausibly "the correct answer".
        source_cid = cmap.get(nid)
        preferred: list[dict] = []
        fallback: list[dict] = []
        for cand in distractor_pool:
            if cmap.get(int(cand["id"])) != source_cid:
                preferred.append(cand)
            else:
                fallback.append(cand)
            if len(preferred) >= NEIGHBOR_DISTRACTORS:
                break
        distractors = (preferred + fallback)[:NEIGHBOR_DISTRACTORS]
        if correct_note is not None and len(distractors) == NEIGHBOR_DISTRACTORS:
            choices = _make_neighbor_card(
                note=note,
                correct_neighbor=correct_note,
                distractors=distractors,
                cluster_lookup=community_lookup,
                cmap=cmap,
                salt=session_salt,
            )
            return Card(
                id=f"neighbor-{nid}",
                kind="neighbor",
                note_id=nid,
                title=note["title"],
                cluster_id=cid,
                cluster_name=cluster_name,
                cluster_color=cluster_color,
                prompt_text=(
                    f"Which of these is the strongest synapse of "
                    f"“{note['title']}”?"
                ),
                answer_text=correct_note["title"],
                cloze_answer=str(correct_id),
                body_before="",
                body_after="",
                body_snippet=_snippet(note.get("body", "")),
                choices=choices,
                correct_choice_id=int(correct_id),
                ease=st["ease"],
                interval_hours=st["interval_hours"],
                next_due=st["next_due"],
                streak=st["streak"],
                reviews=st["reviews"],
                lapses=st["lapses"],
                days_overdue=round(overdue, 2),
                days_since_seen=days_since_seen,
                reasons=reasons,
            )

    # 2) Cloze card — mask the highest-scoring distinctive phrase.
    cloze = _pick_cloze(note, corpus_df, n_docs)
    if cloze is not None:
        before, phrase, after = cloze
        return Card(
            id=f"cloze-{nid}",
            kind="cloze",
            note_id=nid,
            title=note["title"],
            cluster_id=cid,
            cluster_name=cluster_name,
            cluster_color=cluster_color,
            prompt_text=note["title"],
            answer_text=phrase,
            cloze_answer=phrase.lower().strip(),
            body_before=before.strip(),
            body_after=after.strip(),
            body_snippet="",
            choices=[],
            correct_choice_id=None,
            ease=st["ease"],
            interval_hours=st["interval_hours"],
            next_due=st["next_due"],
            streak=st["streak"],
            reviews=st["reviews"],
            lapses=st["lapses"],
            days_overdue=round(overdue, 2),
            days_since_seen=days_since_seen,
            reasons=reasons,
        )

    # 3) Prompt card — title as question, body as reveal.
    if len(note.get("body", "").strip()) >= MIN_BODY_CHARS:
        return Card(
            id=f"prompt-{nid}",
            kind="prompt",
            note_id=nid,
            title=note["title"],
            cluster_id=cid,
            cluster_name=cluster_name,
            cluster_color=cluster_color,
            prompt_text=_title_prompt(note["title"]),
            answer_text=_snippet(note["body"], max_chars=520),
            cloze_answer="",
            body_before="",
            body_after="",
            body_snippet=_snippet(note.get("body", "")),
            choices=[],
            correct_choice_id=None,
            ease=st["ease"],
            interval_hours=st["interval_hours"],
            next_due=st["next_due"],
            streak=st["streak"],
            reviews=st["reviews"],
            lapses=st["lapses"],
            days_overdue=round(overdue, 2),
            days_since_seen=days_since_seen,
            reasons=reasons,
        )

    return None


# ---------------------------------------------------------- SM-2 grading

def grade_card(
    *,
    note_id: int,
    grade: int,
    now: datetime | None = None,
) -> GradeResult:
    """Apply an SM-2 lite update. Persists the new state. Grades outside
    [0, 3] are clamped."""
    grade = max(0, min(3, int(grade)))
    n = _now(now)

    with _conn() as con:
        row = con.execute(
            "SELECT * FROM recall_state WHERE note_id = ?", (note_id,)
        ).fetchone()

    if row is None:
        state = _fresh_state(n)
    else:
        state = dict(row)

    ease = float(state["ease"])
    interval_h = float(state["interval_hours"])
    streak = int(state["streak"])
    lapses = int(state["lapses"])
    reviews = int(state["reviews"]) + 1

    if grade == GRADE_AGAIN:
        ease = max(MIN_EASE, ease - 0.20)
        interval_h = max(1.0, interval_h * 0.30)
        streak = 0
        lapses += 1
    elif grade == GRADE_HARD:
        ease = max(MIN_EASE, ease - 0.05)
        interval_h = max(1.0, interval_h * 1.20)
    elif grade == GRADE_GOOD:
        interval_h = interval_h * ease
        streak += 1
    else:  # GRADE_EASY
        ease = min(MAX_EASE, ease + 0.15)
        interval_h = interval_h * ease * 1.30
        streak += 1

    interval_h = min(MAX_INTERVAL_HOURS, interval_h)
    next_due = n + timedelta(hours=interval_h)

    new_state = {
        "ease": round(ease, 4),
        "interval_hours": round(interval_h, 4),
        "next_due": _iso(next_due),
        "streak": streak,
        "reviews": reviews,
        "lapses": lapses,
        "last_grade": grade,
        "last_reviewed_at": _iso(n),
    }
    _upsert_state(note_id, new_state)

    return GradeResult(
        note_id=note_id,
        grade=grade,
        ease=new_state["ease"],
        interval_hours=new_state["interval_hours"],
        next_due=new_state["next_due"],
        streak=new_state["streak"],
        reviews=new_state["reviews"],
        lapses=new_state["lapses"],
        next_due_phrase=_phrase_next_due(n, next_due),
    )


# ------------------------------------------------ summary + streak

def _current_streak(state_by_id: dict[int, dict], now: datetime) -> int:
    """Longest run of consecutive days ending today where the user
    reviewed at least one card. Match Pulse's streak semantics so both
    surfaces agree on what "a day of studying" means."""
    if not state_by_id:
        return 0
    days: set[str] = set()
    for s in state_by_id.values():
        last = _parse_iso(s.get("last_reviewed_at"))
        if last is None:
            continue
        days.add(last.date().isoformat())
    if not days:
        return 0
    streak = 0
    cursor = now.date()
    while cursor.isoformat() in days:
        streak += 1
        cursor = cursor - timedelta(days=1)
    return streak


def build_summary(
    *,
    now: datetime,
    notes: list[dict],
    cmap: dict[int, int],
    community_lookup: dict[int, dict],
) -> SummaryOut:
    """Mastery report — how well the graph lives in your head."""
    state_by_id = _load_all_state()

    # Per-cluster tallies.
    by_cluster: dict[int, dict] = {}
    for n in notes:
        nid = int(n["id"])
        cid = cmap.get(nid)
        if cid is None:
            continue
        bucket = by_cluster.setdefault(
            cid,
            {
                "size": 0,
                "reviewed": 0,
                "known": 0,
                "ease_sum": 0.0,
                "ease_n": 0,
                "due_now": 0,
            },
        )
        bucket["size"] += 1
        st = state_by_id.get(nid)
        if st:
            if st["reviews"] > 0:
                bucket["reviewed"] += 1
                bucket["ease_sum"] += float(st["ease"])
                bucket["ease_n"] += 1
                if int(st["streak"]) >= 2:
                    bucket["known"] += 1
            next_due = _parse_iso(st["next_due"]) or now
            if next_due <= now:
                bucket["due_now"] += 1

    clusters: list[ClusterMastery] = []
    for cid, bucket in sorted(by_cluster.items()):
        cinfo = community_lookup.get(cid) or {}
        size = bucket["size"] or 1
        mastery = bucket["known"] / size
        clusters.append(
            ClusterMastery(
                cluster_id=cid,
                cluster_name=cinfo.get("name", f"Cluster {cid + 1}"),
                cluster_color=cinfo.get("color", "#a855f7"),
                size=bucket["size"],
                reviewed=bucket["reviewed"],
                known=bucket["known"],
                mastery=round(mastery, 3),
                mean_ease=round(
                    bucket["ease_sum"] / max(1, bucket["ease_n"]), 3
                ),
                due_now=bucket["due_now"],
            )
        )

    reviewed_notes = sum(1 for s in state_by_id.values() if s["reviews"] > 0)
    due_now = sum(
        1 for s in state_by_id.values()
        if (_parse_iso(s["next_due"]) or now) <= now
    )
    mean_ease = (
        sum(s["ease"] for s in state_by_id.values()) / len(state_by_id)
        if state_by_id else DEFAULT_EASE
    )
    total_reviews = sum(int(s["reviews"]) for s in state_by_id.values())
    total_notes = len(notes)
    known_all = sum(c.known for c in clusters)
    mastery_overall = known_all / max(1, total_notes)

    return SummaryOut(
        generated_at=_iso(now),
        total_notes=total_notes,
        reviewed_notes=reviewed_notes,
        due_now=due_now,
        streak_days=_current_streak(state_by_id, now),
        mean_ease=round(mean_ease, 3),
        total_reviews=total_reviews,
        mastery_overall=round(mastery_overall, 3),
        clusters=clusters,
    )


# ---------------------------------------------------- serialization

def serialize_card(c: Card) -> dict:
    return {
        "id": c.id,
        "kind": c.kind,
        "note_id": c.note_id,
        "title": c.title,
        "cluster_id": c.cluster_id,
        "cluster_name": c.cluster_name,
        "cluster_color": c.cluster_color,
        "prompt_text": c.prompt_text,
        "answer_text": c.answer_text,
        "cloze_answer": c.cloze_answer,
        "body_before": c.body_before,
        "body_after": c.body_after,
        "body_snippet": c.body_snippet,
        "choices": [
            {
                "note_id": ch.note_id,
                "title": ch.title,
                "is_correct": ch.is_correct,
                "cluster_id": ch.cluster_id,
                "cluster_color": ch.cluster_color,
            }
            for ch in c.choices
        ],
        "correct_choice_id": c.correct_choice_id,
        "ease": c.ease,
        "interval_hours": c.interval_hours,
        "next_due": c.next_due,
        "streak": c.streak,
        "reviews": c.reviews,
        "lapses": c.lapses,
        "days_overdue": c.days_overdue,
        "days_since_seen": c.days_since_seen,
        "reasons": c.reasons,
    }


def serialize_session(s: SessionOut) -> dict:
    return {
        "generated_at": s.generated_at,
        "session_id": s.session_id,
        "total_notes": s.total_notes,
        "eligible_notes": s.eligible_notes,
        "k": s.k,
        "cards": [serialize_card(c) for c in s.cards],
        "streak_days": s.streak_days,
        "due_now": s.due_now,
        "stats": s.stats,
    }


def serialize_grade(g: GradeResult) -> dict:
    return {
        "note_id": g.note_id,
        "grade": g.grade,
        "ease": g.ease,
        "interval_hours": g.interval_hours,
        "next_due": g.next_due,
        "streak": g.streak,
        "reviews": g.reviews,
        "lapses": g.lapses,
        "next_due_phrase": g.next_due_phrase,
    }


def serialize_summary(s: SummaryOut) -> dict:
    return {
        "generated_at": s.generated_at,
        "total_notes": s.total_notes,
        "reviewed_notes": s.reviewed_notes,
        "due_now": s.due_now,
        "streak_days": s.streak_days,
        "mean_ease": s.mean_ease,
        "total_reviews": s.total_reviews,
        "mastery_overall": s.mastery_overall,
        "clusters": [
            {
                "cluster_id": c.cluster_id,
                "cluster_name": c.cluster_name,
                "cluster_color": c.cluster_color,
                "size": c.size,
                "reviewed": c.reviewed,
                "known": c.known,
                "mastery": c.mastery,
                "mean_ease": c.mean_ease,
                "due_now": c.due_now,
            }
            for c in s.clusters
        ],
    }


# ------------------------------------------ auto-grading helpers (cloze)

def check_cloze_answer(user_answer: str, canonical: str) -> tuple[bool, float]:
    """Fuzzy string match for cloze auto-grading. Returns ``(is_correct,
    similarity)`` with similarity in ``[0, 1]``. Case-insensitive, ignores
    surrounding punctuation and whitespace.

    Uses a lightweight character-level Sørensen–Dice coefficient over
    bigrams. Good enough for typos and pluralisation; explicitly *not*
    stemming — a fresh library user would resent "manager" being counted
    correct for "management"."""
    a = _norm_cloze(user_answer)
    b = _norm_cloze(canonical)
    if not a or not b:
        return False, 0.0
    if a == b:
        return True, 1.0

    def _bigrams(s: str) -> set[str]:
        return {s[i:i + 2] for i in range(len(s) - 1)} or {s}

    ga, gb = _bigrams(a), _bigrams(b)
    inter = len(ga & gb)
    denom = (len(ga) + len(gb)) or 1
    dice = 2.0 * inter / denom
    return dice >= 0.72, dice


_PUNCT_RE = re.compile(r"[^A-Za-z0-9\s]")


def _norm_cloze(s: str) -> str:
    return _PUNCT_RE.sub(" ", (s or "").lower()).strip().replace("  ", " ")
