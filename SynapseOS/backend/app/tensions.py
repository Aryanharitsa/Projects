"""Tensions — surface contradictions and conflicts in your second brain.

Every prior surface in SynapseOS reveals what *agrees*: clusters bind
related notes together, synapses draw the strongest semantic links, and
Synthesis paraphrases the consensus inside a cluster. None of them tells
you when your own graph disagrees with itself — and that's the highest-
value PKM signal nobody else surfaces. A note that says "boring tech
wins" sitting alongside a note that says "the framework was a mistake"
is a *tension* — a place where your beliefs haven't been reconciled.
Find those and you turn a passive archive into a thinking partner.

For any two notes ``a, b`` we declare a tension when:

  * **They're talking about the same thing** — ``cosine(a, b) ≥ FLOOR``.
    Otherwise an angry rant about TypeScript and a happy ode to gardens
    aren't a contradiction; they're unrelated.

  * **AND at least one of these contradiction signals fires** with
    nontrivial weight:

      ``polarity``  — opposing valence: one note leans positive
                       (good · best · ship · wins · works · scale · …),
                       the other negative (bad · worst · breaks · fails ·
                       overrated · slow · …).

      ``antonym``   — a pair of polar antonyms each appears in one note
                       (simple/complex, fast/slow, right/wrong,
                       overrated/underrated, robust/brittle, …).

      ``contrast``  — explicit contrast cues (but, however, although,
                       instead, rather, actually) appear at non-trivial
                       density. A contrast cue alongside semantic overlap
                       is the linguistic fingerprint of "yes-but".

      ``title``     — title-form contention: "Against X" vs "Why X",
                       opposite polarity in the titles, or shared topic
                       words with opposite-signed valences.

The pair score combines them multiplicatively over cosine so that
*unrelated* notes can't accidentally score high just by having "but" in
one of them, and *closely related* notes with strong contradiction cues
rise to the top. The strongest tensions are within a single cluster
(``kind="internal"``) — that's where you'd expect agreement and instead
get conflict; cross-cluster tensions (``kind="cross"``) are more
philosophical disagreements between adjacent topics.

For every tension we also harvest one **evidence sentence per side** —
the most-polarized sentence in each note in the direction of that
note's overall stance — so the brief shows the concrete quotes that
prove the conflict. A deterministic ``bridge_prompt`` ("when does A
apply, and when does B?") is rendered into a one-click Reconcile button:
the user gets a NoteComposer pre-filled with the prompt and a
suggested title, lands on the canvas as a new bridge atom, and the
graph rewires.

Everything below is pure stdlib, deterministic, and a pure function of
``(notes, embeddings, threshold, top_k)``.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from . import community as community_mod
from . import store, synapse
from .embed import cosine, embed

# A pair below this cosine is "talking about different things" — no
# tension, just unrelated noise. Tuned slightly above the default
# synapse threshold so tensions are pulled from the *connected* part of
# your graph, not from random pairs that just happen to share a buzzword.
DEFAULT_FLOOR = 0.18

# Max tensions returned by /tensions. The UI groups by kind and lets the
# user expand, so a tight default keeps the brief readable.
DEFAULT_LIMIT = 20

# Sentences shorter than this aren't useful as evidence — they're list
# bullets or fragments.
MIN_EVIDENCE_CHARS = 24

_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"\(])")
_WORD_RE = re.compile(r"[a-z][a-z\-]+")

# Valence lexicons. Deliberately small + hand-picked — a long auto-lexicon
# overfires on every paragraph; a tight one only flags real stance words.
POSITIVE: frozenset[str] = frozenset(
    """
    good great best better win wins beats beat ship ships works working work
    fast simple right succeed succeeds successful scale scales recommend
    prefer preferred lasting durable robust solid strong valuable useful
    essential important vital central powerful productive efficient elegant
    cheap correct safe pragmatic battle-tested mature dependable trusted
    proven readable maintainable boring obvious learnable beloved adored
    """.split()
)

NEGATIVE: frozenset[str] = frozenset(
    """
    bad worst worse breaks broken slow overrated wrong fails failed failing
    hard complex miss falls fragile brittle costly painful expensive useless
    dangerous harmful weak problematic flawed regret mistake doom dies kills
    nightmare antifeature ugly hack hacky leaky bloated bloat overkill
    suspicious unreliable risky unmaintainable rotting rotten antipattern
    deprecated worthless brittle confusing wasteful
    """.split()
)

# Antonym pairs — when one appears in note A and the other in note B,
# that's a textbook contradiction signal *if* the notes are also
# semantically close. Pair order doesn't matter (we check both ways).
ANTONYM_PAIRS: tuple[tuple[str, str], ...] = (
    ("simple", "complex"),
    ("simple", "complicated"),
    ("fast", "slow"),
    ("right", "wrong"),
    ("win", "lose"),
    ("wins", "loses"),
    ("ship", "skip"),
    ("agree", "disagree"),
    ("best", "worst"),
    ("good", "bad"),
    ("overrated", "underrated"),
    ("works", "breaks"),
    ("succeed", "fail"),
    ("more", "less"),
    ("strong", "weak"),
    ("important", "trivial"),
    ("central", "orphan"),
    ("robust", "brittle"),
    ("safe", "risky"),
    ("hard", "easy"),
    ("efficient", "wasteful"),
    ("essential", "optional"),
    ("durable", "fragile"),
    ("boring", "exciting"),
    ("readable", "obscure"),
    ("rich", "poor"),
    ("mature", "immature"),
    ("first", "last"),
    ("more", "fewer"),
    ("scale", "fail"),
    ("solid", "shaky"),
)

CONTRAST_MARKERS: frozenset[str] = frozenset(
    """
    but however although yet instead rather actually really notwithstanding
    nonetheless conversely whereas though
    """.split()
)

# A "stance phrase" — the title shape of an explicitly opposed take.
_AGAINST_RE = re.compile(r"^\s*against\b", re.I)

# Title-overlap stopwords. Sharing 'the' is not a shared topic — we want
# real content words to confirm the two titles are about the same thing.
_TITLE_STOP: frozenset[str] = frozenset(
    """
    the a an of and or but to in on at by from with as is are was were be
    been being it its their our your my his her this that these those for
    not no yes if then so when while which who whom how what why where do
    does did can could should would may might must will shall just only
    also more most less why how
    """.split()
)


@dataclass
class TensionSignal:
    kind: str  # "polarity" | "antonym" | "contrast" | "title"
    weight: float  # 0..1 contribution to the tension score
    detail: str  # human-readable explanation, used in the UI chips


@dataclass
class TensionEvidence:
    note_id: int
    title: str
    sentence: str
    polarity: int  # signed — matches the sentence's own stance


@dataclass
class Tension:
    a_id: int
    a_title: str
    b_id: int
    b_title: str
    cosine: float
    magnitude: float  # 0..1 normalized tension score
    signals: list[TensionSignal] = field(default_factory=list)
    evidence: list[TensionEvidence] = field(default_factory=list)
    bridge_title: str = ""
    bridge_prompt: str = ""
    bridge_tags: list[str] = field(default_factory=list)
    kind: str = "cross"  # "internal" | "cross"
    cluster_a: int | None = None
    cluster_a_name: str | None = None
    cluster_a_color: str | None = None
    cluster_b: int | None = None
    cluster_b_name: str | None = None
    cluster_b_color: str | None = None


@dataclass
class TensionReport:
    threshold: float
    floor: float
    total_pairs_scanned: int
    candidate_count: int  # pairs above floor
    tension_count: int
    tensions: list[Tension] = field(default_factory=list)
    stats: dict[str, float | int] = field(default_factory=dict)


# ----------------------------------------------------------------- helpers


def _split_sentences(body: str) -> list[str]:
    body = (body or "").strip()
    if not body:
        return []
    return [p.strip() for p in _SENT_SPLIT.split(body) if p.strip()]


def _ensure_period(text: str) -> str:
    text = text.rstrip()
    if text and text[-1] not in ".!?":
        return text + "."
    return text


def _words(text: str) -> list[str]:
    return _WORD_RE.findall(text.lower())


def _word_set(text: str) -> set[str]:
    return set(_words(text))


def _stem(word: str) -> str:
    """Light singular/plural collapse so 'folder' ≈ 'folders'.

    Just strips a trailing ``s`` on words ≥ 4 chars and a trailing
    ``es`` on words ≥ 5 chars. Not a full stemmer — we don't need to
    handle irregular forms here, only the most common plural that breaks
    title-overlap detection.
    """
    if len(word) >= 5 and word.endswith("es"):
        return word[:-2]
    if len(word) >= 4 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def _stem_set(text: str) -> set[str]:
    return {_stem(w) for w in _words(text)}


def _polarity(text: str) -> tuple[int, int, int]:
    """Return ``(pos_hits, neg_hits, signed)`` for ``text``.

    ``signed = pos - neg``. Negation flips local valence — a "not bad"
    counts as positive, "not great" as negative — by walking word-by-word
    and inverting the next valence token after any of {not, no, never,
    without}. That's a coarse fix but stops the obvious false positives
    where "not broken" lights up the negative lexicon.
    """
    toks = _words(text)
    pos = neg = 0
    flip = False
    for t in toks:
        if t in {"not", "no", "never", "without", "barely", "hardly"}:
            flip = True
            continue
        if t in POSITIVE:
            if flip:
                neg += 1
            else:
                pos += 1
            flip = False
            continue
        if t in NEGATIVE:
            if flip:
                pos += 1
            else:
                neg += 1
            flip = False
            continue
        # Negation window is one content word — long-distance flips are
        # too noisy without a parser.
        flip = False
    return pos, neg, pos - neg


def _most_polarized_sentence(body: str, want_sign: int) -> tuple[str | None, int]:
    """Pick the sentence whose polarity leans hardest in ``want_sign``.

    Returns ``(sentence, polarity)`` or ``(None, 0)`` if no sentence is
    long enough or polarized enough. ``want_sign`` is +1 (find the most
    positive) or -1 (find the most negative); both directions return the
    same field so the UI can paint a consistent +/- pill.
    """
    best_sent: str | None = None
    best_score = 0  # in want_sign direction
    best_pol = 0
    for s in _split_sentences(body):
        if len(s) < MIN_EVIDENCE_CHARS:
            continue
        _, _, signed = _polarity(s)
        score = signed * want_sign
        if score > best_score:
            best_score = score
            best_sent = s
            best_pol = signed
    return best_sent, best_pol


def _antonym_hits(words_a: set[str], words_b: set[str]) -> list[tuple[str, str]]:
    hits: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for x, y in ANTONYM_PAIRS:
        if (x in words_a and y in words_b) or (y in words_a and x in words_b):
            key = (x, y) if x < y else (y, x)
            if key in seen:
                continue
            seen.add(key)
            hits.append(key)
    return hits


def _contrast_density(text: str) -> int:
    toks = _words(text)
    return sum(1 for t in toks if t in CONTRAST_MARKERS)


def _title_contention(a_title: str, b_title: str) -> tuple[bool, str]:
    """Detect title-form contention. Returns ``(fires, detail)``.

    Two patterns:
      * "Against X" vs anything sharing a token with X → explicit opposition.
      * Opposite polarity in the two titles AND non-trivial overlap of
        non-stopword tokens → "Boring tech wins" vs "The framework was a
        mistake".

    Overlap uses ``_stem_set`` so "folder" ≈ "folders" — the original
    set-intersection broke on the most common plural and missed obvious
    pairs like "Against the folder" vs "Why folders work".
    """
    a_l = a_title.strip().lower()
    b_l = b_title.strip().lower()
    a_against = bool(_AGAINST_RE.match(a_l))
    b_against = bool(_AGAINST_RE.match(b_l))
    if a_against ^ b_against:
        anti = a_l if a_against else b_l
        pro = b_l if a_against else a_l
        anti_tokens = _stem_set(anti) - {"against"} - _TITLE_STOP
        pro_tokens = _stem_set(pro) - _TITLE_STOP
        overlap = anti_tokens & pro_tokens
        if overlap:
            head = sorted(overlap)[0]
            return True, f"'against {head}' vs '{pro.strip()}'"

    pa = _polarity(a_title)[2]
    pb = _polarity(b_title)[2]
    if pa * pb < 0:
        a_tokens = _stem_set(a_title) - _TITLE_STOP
        b_tokens = _stem_set(b_title) - _TITLE_STOP
        # Ignore polarity tokens (also stemmed) when checking overlap so
        # the "shared topic" is something *other* than the disagreement.
        polar = {_stem(w) for w in (POSITIVE | NEGATIVE)}
        overlap = (a_tokens & b_tokens) - polar
        if overlap:
            return True, f"opposite stance · shared topic '{sorted(overlap)[0]}'"
    return False, ""


def _bridge_for(
    a_title: str,
    b_title: str,
    signals: list[TensionSignal],
    a_tags: list[str],
    b_tags: list[str],
) -> tuple[str, str, list[str]]:
    """Generate a one-click reconciliation suggestion.

    Returns ``(suggested_title, body_prompt, suggested_tags)``. The
    title is short enough to commit as-is; the body is a writing prompt
    that names both sides so the user can finish it in 30 seconds.
    """
    kinds = {s.kind for s in signals}
    if "antonym" in kinds:
        title = f"When {a_title.lower().rstrip('.')} vs when {b_title.lower().rstrip('.')}"
    elif "title" in kinds or "polarity" in kinds:
        title = f"Reconciling: {a_title} ↔ {b_title}"
    else:
        title = f"Bridge: {a_title} & {b_title}"
    # Cap the title so the composer doesn't reject it on length.
    if len(title) > 140:
        title = title[:137] + "…"

    if "antonym" in kinds:
        prompt = (
            f"'{a_title}' and '{b_title}' read as opposites. Pin down the "
            f"conditions under which each applies. When does the first "
            f"win? When does the second? What's the variable that decides?"
        )
    elif "polarity" in kinds:
        prompt = (
            f"'{a_title}' and '{b_title}' take opposite stances on the same "
            f"thing. What's the context that makes each one right? Write "
            f"the synthesis that lets both be true at once."
        )
    elif "title" in kinds:
        prompt = (
            f"These two titles disagree on the surface. Are they actually "
            f"opposed, or are they answering different questions? Write "
            f"the underlying distinction."
        )
    else:
        prompt = (
            f"'{a_title}' and '{b_title}' are close cousins with a contrast "
            f"undertone. What's the unifying principle that explains both?"
        )

    # Merge + dedupe tags from both sides, cap so the composer accepts
    # them without complaint.
    merged: list[str] = []
    for t in a_tags + b_tags:
        if t and t not in merged:
            merged.append(t)
    return title, prompt, merged[:4]


def _signal_weight_sum(signals: list[TensionSignal]) -> float:
    return sum(s.weight for s in signals)


# ----------------------------------------------------------------- engine


def detect_pair(
    a: dict,
    b: dict,
    *,
    cosine_ab: float,
    a_pol: tuple[int, int, int],
    b_pol: tuple[int, int, int],
    a_words: set[str],
    b_words: set[str],
) -> list[TensionSignal]:
    """Run every signal detector against ``(a, b)`` and return the firers.

    The cosine threshold is checked by the caller; this function assumes
    the pair is semantically close enough to bother looking. Each signal
    returns a 0..1 weight; the caller multiplies the *sum* into the
    cosine to produce the magnitude.
    """
    sigs: list[TensionSignal] = []

    # 1. Polarity divergence — opposite-signed stances with non-trivial
    #    magnitude on each side. ``span / 6`` clips around the typical
    #    range (a polarity of ±3 is already a strong note).
    _, _, sa = a_pol
    _, _, sb = b_pol
    if sa * sb < 0 and min(abs(sa), abs(sb)) >= 1:
        span = abs(sa) + abs(sb)
        weight = min(1.0, span / 6.0)
        sigs.append(
            TensionSignal(
                kind="polarity",
                weight=round(weight, 3),
                detail=f"{_arrow(sa)} vs {_arrow(sb)} stance ({sa:+d} / {sb:+d})",
            )
        )

    # 2. Antonym co-occurrence — one pair contributes 0.5, two pairs
    #    saturate the signal. Two unrelated antonyms aren't twice as
    #    contradictory as one.
    ant = _antonym_hits(a_words, b_words)
    if ant:
        weight = min(1.0, 0.5 + 0.25 * (len(ant) - 1))
        pretty = ", ".join(f"{x}↔{y}" for x, y in ant[:3])
        sigs.append(
            TensionSignal(
                kind="antonym",
                weight=round(weight, 3),
                detail=pretty,
            )
        )

    # 3. Contrast markers — only fire when they appear in BOTH notes.
    #    A "but" on one side is just writing; a "but" on both means each
    #    is qualifying the other's frame.
    ca = _contrast_density(a["body"]) + _contrast_density(a["title"])
    cb = _contrast_density(b["body"]) + _contrast_density(b["title"])
    if ca >= 1 and cb >= 1:
        weight = min(1.0, 0.3 + 0.15 * (min(ca, cb) - 1))
        sigs.append(
            TensionSignal(
                kind="contrast",
                weight=round(weight, 3),
                detail=f"contrast cues both sides ({ca}/{cb})",
            )
        )

    # 4. Title contention — a direct surface signal. Light weight by
    #    itself; pairs nicely with polarity to crown the headline pair.
    fires, detail = _title_contention(a["title"], b["title"])
    if fires:
        sigs.append(
            TensionSignal(
                kind="title",
                weight=0.45,
                detail=detail,
            )
        )

    return sigs


def _arrow(signed: int) -> str:
    if signed > 0:
        return "↑"
    if signed < 0:
        return "↓"
    return "·"


def find_tensions(
    threshold: float | None = None,
    top_k: int | None = None,
    *,
    floor: float = DEFAULT_FLOOR,
    limit: int = DEFAULT_LIMIT,
) -> TensionReport:
    """Scan every note pair for contradictions.

    Pure function of the current note set. The graph (and clusters) are
    computed at ``(threshold, top_k)`` so the report's cluster
    annotations match whatever the canvas is rendering, but the
    detection itself doesn't depend on synapse edges — a tension can
    exist between two notes the graph hasn't linked, which is one of the
    most interesting kinds.
    """
    th = synapse.DEFAULT_THRESHOLD if threshold is None else threshold
    tk = synapse.DEFAULT_TOP_K if top_k is None else top_k

    notes = store.all_notes()
    if len(notes) < 2:
        return TensionReport(
            threshold=th,
            floor=floor,
            total_pairs_scanned=0,
            candidate_count=0,
            tension_count=0,
            stats={"notes": len(notes)},
        )

    embeddings = dict(store.all_embeddings())
    # Cluster annotations — used to flag internal vs cross-cluster.
    g = synapse.compute_graph(threshold=th, top_k=tk)
    nodes_by_id = {n["id"]: n for n in g.nodes}
    cmap = {n["id"]: n.get("community", 0) for n in g.nodes}
    built = community_mod.build_communities(cmap, nodes_by_id)
    cluster_name = {c.id: c.name for c in built}
    cluster_color = {c.id: c.color for c in built}

    # Per-note precompute: polarity, word set, evidence sentences for
    # each direction. O(N) before the O(N²) pair scan.
    pol: dict[int, tuple[int, int, int]] = {}
    words: dict[int, set[str]] = {}
    pos_evidence: dict[int, tuple[str | None, int]] = {}
    neg_evidence: dict[int, tuple[str | None, int]] = {}
    for n in notes:
        text = f"{n['title']}\n{n['body']}"
        pol[n["id"]] = _polarity(text)
        words[n["id"]] = _word_set(text)
        pos_evidence[n["id"]] = _most_polarized_sentence(n["body"], +1)
        neg_evidence[n["id"]] = _most_polarized_sentence(n["body"], -1)

    note_ids = [n["id"] for n in notes]
    by_id = {n["id"]: n for n in notes}

    total_pairs = 0
    candidates = 0
    tensions: list[Tension] = []
    for i in range(len(note_ids)):
        a_id = note_ids[i]
        a = by_id[a_id]
        va = embeddings.get(a_id)
        if va is None:
            continue
        for j in range(i + 1, len(note_ids)):
            b_id = note_ids[j]
            total_pairs += 1
            vb = embeddings.get(b_id)
            if vb is None:
                continue
            sim = cosine(va, vb)
            # Title-form contention is a deterministic linguistic
            # signal — an "Against X" title paired with a "Why X works"
            # title is contention regardless of what the hashing-trick
            # embedder thinks. Let those bypass the floor so the brief
            # never misses the obvious cases.
            title_fires, _ = _title_contention(a["title"], by_id[b_id]["title"])
            if sim < floor and not title_fires:
                continue
            candidates += 1
            sigs = detect_pair(
                a, by_id[b_id],
                cosine_ab=sim,
                a_pol=pol[a_id], b_pol=pol[b_id],
                a_words=words[a_id], b_words=words[b_id],
            )
            if not sigs:
                continue
            sig_sum = _signal_weight_sum(sigs)
            # Multiplicative score: cosine sets the ceiling, signals
            # scale within it. Floor of 1.0 means a pure-cosine pair
            # with one signal is at least matched against a "near-miss"
            # cosine pair with stacked signals.
            magnitude = sim * min(2.0, 1.0 + sig_sum)
            magnitude = min(1.0, magnitude)

            # Pick evidence: each side gets the sentence whose stance
            # matches *its* overall polarity sign. If a side has no
            # polarized sentence (e.g. the contradiction is structural),
            # fall back to the opening sentence of the body.
            ev = _gather_evidence(a, by_id[b_id], pol, pos_evidence, neg_evidence)

            ca = cmap.get(a_id)
            cb = cmap.get(b_id)
            kind = "internal" if (ca is not None and ca == cb) else "cross"

            bridge_title, bridge_prompt, bridge_tags = _bridge_for(
                a["title"], by_id[b_id]["title"],
                sigs, a["tags"], by_id[b_id]["tags"],
            )

            tensions.append(
                Tension(
                    a_id=a_id, a_title=a["title"],
                    b_id=b_id, b_title=by_id[b_id]["title"],
                    cosine=round(sim, 4),
                    magnitude=round(magnitude, 4),
                    signals=sigs,
                    evidence=ev,
                    bridge_title=bridge_title,
                    bridge_prompt=bridge_prompt,
                    bridge_tags=bridge_tags,
                    kind=kind,
                    cluster_a=ca,
                    cluster_a_name=cluster_name.get(ca) if ca is not None else None,
                    cluster_a_color=cluster_color.get(ca) if ca is not None else None,
                    cluster_b=cb,
                    cluster_b_name=cluster_name.get(cb) if cb is not None else None,
                    cluster_b_color=cluster_color.get(cb) if cb is not None else None,
                )
            )

    tensions.sort(key=lambda t: (-t.magnitude, -t.cosine, t.a_id, t.b_id))
    if limit > 0:
        tensions = tensions[:limit]

    internal_count = sum(1 for t in tensions if t.kind == "internal")
    cross_count = len(tensions) - internal_count
    stats: dict[str, float | int] = {
        "notes": len(notes),
        "candidate_pairs": candidates,
        "internal": internal_count,
        "cross": cross_count,
        "top_magnitude": tensions[0].magnitude if tensions else 0.0,
    }

    return TensionReport(
        threshold=th,
        floor=floor,
        total_pairs_scanned=total_pairs,
        candidate_count=candidates,
        tension_count=len(tensions),
        tensions=tensions,
        stats=stats,
    )


def _gather_evidence(
    a: dict,
    b: dict,
    pol: dict[int, tuple[int, int, int]],
    pos_evidence: dict[int, tuple[str | None, int]],
    neg_evidence: dict[int, tuple[str | None, int]],
) -> list[TensionEvidence]:
    """One quote per side, leaning in *that* note's own stance direction.

    If a side has no polarized sentence (e.g. it's a neutral framing
    note opposite a polar one), we fall back to the opening sentence so
    the UI still shows something concrete from each side.
    """
    out: list[TensionEvidence] = []
    for note in (a, b):
        sa_pos = pol[note["id"]][2]
        want = +1 if sa_pos >= 0 else -1
        sent, p = pos_evidence[note["id"]] if want > 0 else neg_evidence[note["id"]]
        if sent is None:
            # Try the *opposite* direction — a neutral overall note may
            # still contain a single polarized claim worth showing.
            sent, p = neg_evidence[note["id"]] if want > 0 else pos_evidence[note["id"]]
        if sent is None:
            sents = _split_sentences(note["body"])
            sent = sents[0] if sents else (note["body"] or "").strip()[:200]
            p = 0
        out.append(
            TensionEvidence(
                note_id=note["id"],
                title=note["title"],
                sentence=_ensure_period(sent or note["title"]),
                polarity=int(p),
            )
        )
    return out


# ----------------------------------------------------------------- export


def to_markdown(report: TensionReport) -> str:
    """Self-contained Markdown brief of all detected tensions.

    The export reads stand-alone outside SynapseOS — every quote
    attributed to its note title, every signal named, every bridge
    prompt included so the user can pick it back up in Notion / their
    journal / anywhere.
    """
    lines: list[str] = []
    lines.append("# Tensions — where your second brain disagrees with itself")
    n = report.tension_count
    lines.append(
        f"\n_{n} tension{'s' if n != 1 else ''} across {report.candidate_count} "
        f"semantically-close pairs (cosine ≥ {report.floor})._\n"
    )
    if n == 0:
        lines.append("Your graph is in harmony — no contradictions surfaced at the current floor.")
        lines.append("\n---\n_Generated by SynapseOS · Tensions._")
        return "\n".join(lines)

    by_kind: dict[str, list[Tension]] = {"internal": [], "cross": []}
    for t in report.tensions:
        by_kind.setdefault(t.kind, []).append(t)

    if by_kind["internal"]:
        lines.append(f"## Inside a cluster ({len(by_kind['internal'])})\n")
        for t in by_kind["internal"]:
            lines.extend(_tension_md(t))
    if by_kind["cross"]:
        lines.append(f"## Across clusters ({len(by_kind['cross'])})\n")
        for t in by_kind["cross"]:
            lines.extend(_tension_md(t))

    lines.append("---")
    lines.append("_Generated by SynapseOS · Tensions._")
    return "\n".join(lines)


def _tension_md(t: Tension) -> list[str]:
    pct = lambda x: f"{round(x * 100)}%"  # noqa: E731
    lines: list[str] = []
    lines.append(f"### {t.a_title}  ⟷  {t.b_title}")
    cluster_a = t.cluster_a_name or "—"
    cluster_b = t.cluster_b_name or "—"
    lines.append(
        f"_magnitude {pct(t.magnitude)} · cosine {pct(t.cosine)} · {cluster_a} vs {cluster_b}_"
    )
    if t.signals:
        sig_line = " · ".join(f"**{s.kind}** {s.detail}" for s in t.signals)
        lines.append(f"\nSignals: {sig_line}")
    if t.evidence:
        lines.append("")
        for ev in t.evidence:
            sign = "↑" if ev.polarity > 0 else ("↓" if ev.polarity < 0 else "·")
            lines.append(f"> {sign} *{ev.title}* — {ev.sentence}")
    if t.bridge_prompt:
        lines.append(f"\n**Reconcile:** {t.bridge_prompt}")
    lines.append("")
    return lines


def serialize_signal(s: TensionSignal) -> dict:
    return {"kind": s.kind, "weight": s.weight, "detail": s.detail}


def serialize_evidence(e: TensionEvidence) -> dict:
    return {
        "note_id": e.note_id,
        "title": e.title,
        "sentence": e.sentence,
        "polarity": e.polarity,
    }


def serialize_tension(t: Tension) -> dict:
    return {
        "a_id": t.a_id,
        "a_title": t.a_title,
        "b_id": t.b_id,
        "b_title": t.b_title,
        "cosine": t.cosine,
        "magnitude": t.magnitude,
        "signals": [serialize_signal(s) for s in t.signals],
        "evidence": [serialize_evidence(e) for e in t.evidence],
        "bridge_title": t.bridge_title,
        "bridge_prompt": t.bridge_prompt,
        "bridge_tags": t.bridge_tags,
        "kind": t.kind,
        "cluster_a": t.cluster_a,
        "cluster_a_name": t.cluster_a_name,
        "cluster_a_color": t.cluster_a_color,
        "cluster_b": t.cluster_b,
        "cluster_b_name": t.cluster_b_name,
        "cluster_b_color": t.cluster_b_color,
    }


def serialize(report: TensionReport) -> dict:
    return {
        "threshold": report.threshold,
        "floor": report.floor,
        "total_pairs_scanned": report.total_pairs_scanned,
        "candidate_count": report.candidate_count,
        "tension_count": report.tension_count,
        "tensions": [serialize_tension(t) for t in report.tensions],
        "stats": report.stats,
    }
