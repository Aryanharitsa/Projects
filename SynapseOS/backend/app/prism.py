"""Prism — perspective explorer for your second brain.

Every SynapseOS surface so far pulls one axis through the vault. Compass
pins a *question* and grows an answer. Synthesis *paraphrases the
consensus* inside one cluster. Tensions finds *contradictory pairs* of
notes. Chronicle tells the *biography of a single cluster*. Pulse says
*what changed this week*.

None of them ask the interrogative question a serious reader asks about
a specific idea: **"Turn this over — what does my whole vault look like
if I read it through the skeptic's eyes? The empiricist's? The
historian's? The systems-thinker's? Where is my thinking on this deep,
and where does it have a hole?"**

Prism is that interrogation. You hand it a target — a specific *note*,
a *cluster centroid*, or an ad-hoc *query* — and it re-projects the
entire vault through eight canonical perspectives:

    skeptic         · challenges, qualifications, "unless" cases
    empiricist      · measurements, benchmarks, evidence, data
    historian       · precedent, prior work, what came before
    futurist        · projections, next steps, "will" statements
    practitioner    · in-production, shipped, day-to-day usage
    contrarian      · opposite hypothesis, unpopular takes
    systems         · feedback loops, coupling, emergent effects
    first_principles· from-scratch, definitional, foundational

For every lens Prism ranks every note in the vault by a *lens-weighted
relevance score*:

    score(n | lens, target) = cosine(embed(n), embed(target))
                              × ( 1 + λ · lexicon_density(n, lens) )
                              × recency_bonus(n)
                              − novelty_penalty_across_lenses(n)

The lens-lexicon multiplier is the interesting part. Each lens carries
a small hand-curated bag of stance words (skeptic: "however",
"actually", "unless"; empiricist: "measured", "benchmark", "n=";
historian: "previously", "originally", "used to"; …). A note that talks
about the *target* AND uses that lens's vocabulary rises to the top of
that lens. A note that's semantically close but neutral in vocabulary
gets pushed toward the more neutral lenses.

A single per-lens *coverage* number in [0, 1] tells you how well the
vault covers that perspective on this target:

    coverage(lens) = mean( score of top-K picks for lens ) · gate

    gate = 0.0  if the top pick has cosine < FLOOR_SIM
                or lexicon_density == 0  (nothing in the vault
                actually *phrases* things this way)
         = 1.0  otherwise

The **weakest lens** (lowest coverage) is a hole in your thinking —
Prism emits a Spark-shaped suggestion prompting you to fill it. The
**strongest lens** tells you the shape of your existing thinking. The
**composite stance** aggregates the stance flags across lenses into a
one-line summary — "you interrogate this idea empirically but you
haven't stress-tested it skeptically."

Everything below is pure stdlib. Deterministic — same vault + same
target + same knobs → byte-identical PrismReport. Same design contract
as every other engine in this repo.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone

from . import community as community_mod
from . import store, synapse
from .embed import cosine, embed

# ------------------------------------------------------------ defaults

DEFAULT_TOP_K_PER_LENS = 3
MIN_TOP_K_PER_LENS = 1
MAX_TOP_K_PER_LENS = 8

# Below this cosine to the target, a note isn't "about" the target — no
# amount of lens-lexicon can rescue it. Chosen slightly above the default
# synapse threshold so Prism draws from the connected part of the graph,
# not from random distant paragraphs.
DEFAULT_FLOOR_SIM = 0.16
MIN_FLOOR_SIM = 0.0
MAX_FLOOR_SIM = 0.90

# λ in `1 + λ · lexicon_density` — controls how much the lens vocabulary
# amplifies the raw cosine. Kept modest so a cosine-strong note doesn't
# get outranked by a cosine-weak note that happens to sprinkle "however"
# ten times.
LEXICON_WEIGHT = 1.75

# Recency bonus — a note touched or created in the last RECENCY_HALF_DAYS
# gets up to `1 + RECENCY_BONUS_MAX` multiplier, decaying exponentially.
# Small on purpose; the point of Prism is depth, not recency.
RECENCY_BONUS_MAX = 0.12
RECENCY_HALF_DAYS = 14.0

# Across-lenses diversification — the same note appearing as top-1 in
# every lens is uninformative. Each subsequent lens that would top-1 a
# note that already top-1'd elsewhere loses NOVELTY_PENALTY per prior
# top-1 hit. Applied *after* per-lens scoring so it only breaks ties
# between roughly-comparable candidates.
NOVELTY_PENALTY = 0.06

# Minimum characters for a sentence to be quotable. Fragments and list
# bullets aren't useful evidence.
MIN_QUOTE_CHARS = 24
MAX_QUOTE_CHARS = 260

# The four lens families used by the composite roll-up.
LENS_FAMILY: dict[str, str] = {
    "skeptic": "critical",
    "empiricist": "empirical",
    "historian": "narrative",
    "futurist": "generative",
    "practitioner": "empirical",
    "contrarian": "critical",
    "systems": "empirical",
    "first_principles": "generative",
}

_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"\(\[])")
_WORD_RE = re.compile(r"[a-z][a-z0-9\-]+")


# --------------------------------------------------------------- lenses


@dataclass(frozen=True)
class LensSpec:
    """The static description of a perspective."""

    id: str
    label: str
    color: str  # css color name used by the frontend palette
    icon: str  # single glyph
    tagline: str
    vocab: frozenset[str]
    family: str


# The vocabulary lists are deliberately small (30-45 tokens each) and
# hand-curated — a long bag-of-words overfires on every paragraph while
# a tight one only trips on the rhetorical fingerprint that lens actually
# leaves in prose. Ordered roughly by strength of signal within each lens.
LENSES: dict[str, LensSpec] = {
    "skeptic": LensSpec(
        id="skeptic",
        label="Skeptic",
        color="rose",
        icon="?",
        tagline="challenges, qualifications, unless-cases",
        vocab=frozenset(
            """
            however but unless except although actually really doubt doubtful
            questionable suspicious sceptical skeptical concern concerns caveat
            caveats risk risks pitfall pitfalls trade-off tradeoff downside
            fragile brittle misleading exaggerated overrated overclaim overclaimed
            wrong incorrect mistaken flawed weak overlook overlooked oversimplified
            hidden footnote overhead overheads worship worshipping myth myths
            landfill trap traps bloat bloated leaky leak messy leaks
            actually-not sacred-cow rarely nearly-never seldom questionably
            not-really problem problematic worse harmful careful
            """.split()
        ),
        family="critical",
    ),
    "empiricist": LensSpec(
        id="empiricist",
        label="Empiricist",
        color="sky",
        icon="σ",
        tagline="measurements, benchmarks, evidence",
        vocab=frozenset(
            """
            measured measurement measure measures benchmark benchmarks bench
            data evidence experiment experiments study studies sample samples
            statistically significant significantly p-value dataset test tests
            tested testing observed observation observations metric metrics
            baseline baselines reproduce reproducible replicate replicated
            numerical quantitative profiling profiler percentile median mean
            stddev variance histogram latency throughput rps qps
            catch catches caught bug bugs bugs-you actual-bugs unit-test
            integration integration-test integration-tests real-db count
            counting counted number numbers show shows shown proof proven
            fast-integration users-actually-hit bugs-users
            """.split()
        ),
        family="empirical",
    ),
    "historian": LensSpec(
        id="historian",
        label="Historian",
        color="amber",
        icon="⏳",
        tagline="precedent, prior work, what came before",
        vocab=frozenset(
            """
            previously historically earlier before originally traditionally
            precedent legacy inherited established classic older ancient
            already existed existed pre-existing predecessor predecessors
            old-school past retrospective retrospectively lineage roots
            origin origins parent evolved evolution deprecated obsolete
            outdated dated used-to used-for did-use has-been have-been
            decade decades century centuries insight luhmann zettelkasten
            zettel folders folder-tree tags-were tradition tradition-of
            long-standing time-tested battle-tested worked-for
            """.split()
        ),
        family="narrative",
    ),
    "futurist": LensSpec(
        id="futurist",
        label="Futurist",
        color="violet",
        icon="→",
        tagline="projections, next steps, what will happen",
        vocab=frozenset(
            """
            will future upcoming next later eventually someday soon coming
            projected forecast forecasted prediction predict predicts predicted
            trend trends trending expected emerging emergent tomorrow
            beyond horizon roadmap ahead approach approaches next-decade
            10x scale-out scale-up prospective plan planned planning imminent
            bet betting shipping-soon wins winning eventual eventually
            long-term long-run compounding compound compounds returns
            grow grows growing growth become becomes becoming
            """.split()
        ),
        family="generative",
    ),
    "practitioner": LensSpec(
        id="practitioner",
        label="Practitioner",
        color="emerald",
        icon="⚙",
        tagline="shipped, in-production, day-to-day usage",
        vocab=frozenset(
            """
            shipped ships shipping production prod deployed deployment
            on-call oncall incident postmortem post-mortem outage p1 sev1
            sev0 sla slo runbook rollback rollout gradual canary staging
            staging-env pilot pilots piloted live in-production at-scale
            workflow workflows daily-driver day-to-day team teams engineer
            engineers real-world in-the-wild actual customer customers
            user users usage usable concrete pragmatic ship deploy configuration
            configure config production-fits fits one-machine single-tenant
            perfectly-fine boring right-choice reads writes
            """.split()
        ),
        family="empirical",
    ),
    "contrarian": LensSpec(
        id="contrarian",
        label="Contrarian",
        color="fuchsia",
        icon="⇄",
        tagline="opposite hypothesis, unpopular takes",
        vocab=frozenset(
            """
            contrary opposite reverse counter counterargument counterexample
            despite anyway paradoxically unpopular unfashionable disagree
            disagrees against anti anti-pattern hot-take heretical heretic
            heresy overrated underrated actually-wrong misconception myth
            debunk debunked cliche contrarian devils-advocate
            not-the-way inversion invert inverse instead-of orthodoxy
            challenge challenges challenger dissent worship folder-worship
            hierarchy-worship boring-wins boring anti-shiny
            splits-the-difference splits difference nobody-does
            """.split()
        ),
        family="critical",
    ),
    "systems": LensSpec(
        id="systems",
        label="Systems",
        color="cyan",
        icon="⇌",
        tagline="feedback, coupling, emergent effects",
        vocab=frozenset(
            """
            feedback loop loops loopback coupling coupled decoupled decouple
            downstream upstream cascade cascading knock-on
            second-order emergent emergence network networks
            networked interaction interactions interact interacts interacted
            equilibrium equilibria non-linear nonlinear tipping-point regime
            regime-shift externality externalities incentive incentives
            skin-in-the-game systems system-level ecosystem ecosystems
            self-reinforcing self-organizing complex-adaptive
            compound compounds compounding chain domino flywheel network-effect
            index-is-the-product structure structures organizing organize
            substrate substrates re-encounter primary secondary
            builds-on foundation-for connects-to
            """.split()
        ),
        family="empirical",
    ),
    "first_principles": LensSpec(
        id="first_principles",
        label="First-Principles",
        color="lime",
        icon="◉",
        tagline="from-scratch, definitional, foundational",
        vocab=frozenset(
            """
            fundamentally fundamental essentially essential essence at-its-root
            at-root at-heart by-definition definitionally
            definition definitions from-scratch axiom
            axiomatic axioms atomic irreducible reduce reduces reduced
            underlying underlie underlies underlain root-cause because-then
            derive derived derivation why-does why-do the-actual physics
            physical-limit information-theoretic pigeonhole primitive primitives
            invariant invariants necessary sufficient
            foundation foundations foundational core root cheap-proxy proxy
            substrate substrates cosine coordinates prose one-idea one-idea-each
            self-contained one-sentence single-sentence quietly-running
            everything-else builds-on
            """.split()
        ),
        family="generative",
    ),
}

_LENS_ORDER: tuple[str, ...] = tuple(LENSES.keys())


# ---------------------------------------------------------- data models


@dataclass
class Pick:
    note_id: int
    title: str
    body: str
    tags: list[str]
    cluster_id: int | None
    cluster_color: str | None
    similarity: float
    lexicon_score: float
    score: float
    quote: str
    is_top: bool = False


@dataclass
class LensResult:
    id: str
    label: str
    color: str
    icon: str
    tagline: str
    family: str
    picks: list[Pick]
    coverage: float  # 0..1
    stance: str  # reinforce · challenge · neutral · thin
    weakness: str | None  # human-readable reason, or None if strong


@dataclass
class Target:
    kind: str  # note · cluster · query
    id: int | None
    label: str
    excerpt: str
    cluster_id: int | None
    cluster_color: str | None


@dataclass
class PrismReport:
    target: Target
    lenses: list[LensResult]
    weakest_lens: str | None
    strongest_lens: str | None
    stance_distribution: dict[str, float]
    dominant_family: str | None
    spark_suggestion: str | None
    prism_id: str
    config: dict = field(default_factory=dict)
    stats: dict = field(default_factory=dict)


# ------------------------------------------------------- utility helpers


def _tokens(text: str) -> list[str]:
    return _WORD_RE.findall(text.lower())


def _sentences(text: str) -> list[str]:
    text = (text or "").strip()
    if not text:
        return []
    raw = _SENT_SPLIT.split(text)
    return [s.strip() for s in raw if len(s.strip()) >= MIN_QUOTE_CHARS]


def _iso_to_dt(iso: str | None) -> datetime | None:
    if not iso:
        return None
    try:
        s = iso.replace("Z", "+00:00")
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def _recency_multiplier(created_at: str | None, seen_at: str | None) -> float:
    """1.0 + RECENCY_BONUS_MAX * exp(-days/half-life) on the freshest of
    created_at / last_seen_at. Notes with no timestamp fall through as 1.0.
    """
    now = datetime.now(timezone.utc)
    freshest: datetime | None = None
    for iso in (seen_at, created_at):
        dt = _iso_to_dt(iso)
        if dt is None:
            continue
        if freshest is None or dt > freshest:
            freshest = dt
    if freshest is None:
        return 1.0
    delta_days = max(0.0, (now - freshest).total_seconds() / 86400.0)
    decay = math.exp(-delta_days / RECENCY_HALF_DAYS)
    return 1.0 + RECENCY_BONUS_MAX * decay


def _lexicon_density(text: str, vocab: frozenset[str]) -> float:
    """Fraction of tokens in the note that hit the lens vocabulary,
    capped to [0, 0.5] and scaled to [0, 1] so a note with 20% lens
    vocabulary saturates the multiplier. Empty text → 0.
    """
    toks = _tokens(text)
    if not toks:
        return 0.0
    hits = sum(1 for t in toks if t in vocab)
    raw = hits / len(toks)
    return min(1.0, raw / 0.5)


def _sentence_lexicon_score(sentence: str, vocab: frozenset[str]) -> float:
    toks = _tokens(sentence)
    if not toks:
        return 0.0
    hits = sum(1 for t in toks if t in vocab)
    return hits / max(1.0, math.sqrt(len(toks)))  # length-normalised


def _pick_quote(body: str, title: str, vocab: frozenset[str]) -> str:
    """Return the sentence in `body` with the strongest lens-lexicon
    density; falls back to the first quotable sentence, then to a body
    excerpt, then to the title. Trimmed to MAX_QUOTE_CHARS.
    """
    sents = _sentences(body)
    best_score = 0.0
    best_sent: str | None = None
    for s in sents:
        sc = _sentence_lexicon_score(s, vocab)
        if sc > best_score:
            best_score = sc
            best_sent = s
    if best_sent is None and sents:
        best_sent = sents[0]
    if best_sent is None:
        b = (body or "").strip()
        best_sent = b[:MAX_QUOTE_CHARS].rstrip() or title
    if len(best_sent) > MAX_QUOTE_CHARS:
        best_sent = best_sent[: MAX_QUOTE_CHARS - 1].rstrip() + "…"
    return best_sent


def _stance_for_lens(
    lens_id: str,
    top_pick_sim: float,
    top_pick_lex: float,
    avg_sim: float,
) -> str:
    """Roll up a lens's picks into a coarse stance token.

    - **thin**:      no supporting evidence at all (nothing above floor).
    - **challenge**: the lens is inherently critical (skeptic /
                     contrarian) and it *did* find evidence.
    - **reinforce**: the lens is inherently supportive (empiricist,
                     practitioner, systems, historian, first_principles)
                     and it found strong-cosine evidence.
    - **neutral**:   evidence exists but at a weaker cosine — the vault
                     touches this angle without settling it.

    The stance is a coarse label, not a truth-value; the lens *color*
    already tells the reader the direction, and stance is the
    engagement level.
    """
    if top_pick_sim <= 0.0 and top_pick_lex <= 0.0:
        return "thin"
    family = LENS_FAMILY.get(lens_id, "empirical")
    if family == "critical":
        return "challenge" if avg_sim >= 0.20 else "neutral"
    if avg_sim >= 0.34 and top_pick_lex >= 0.15:
        return "reinforce"
    if avg_sim >= 0.20:
        return "neutral"
    return "thin"


def _prism_id(
    target: Target, lens_ids: tuple[str, ...], top_k: int, floor: float
) -> str:
    """Stable short id derived from target + config — refreshing with the
    same inputs returns the same id, so the UI can dedupe."""
    h = hashlib.sha256()
    h.update(f"{target.kind}|{target.id}|{target.label}|".encode("utf-8"))
    h.update("|".join(lens_ids).encode("utf-8"))
    h.update(f"|k={top_k}|f={floor:.3f}".encode("utf-8"))
    return h.hexdigest()[:12]


# --------------------------------------------------------- target loaders


def _target_from_note(note_id: int) -> tuple[Target, tuple[float, ...]] | None:
    """Load a note as a Prism target. Returns (Target, embedding) or None
    when the note doesn't exist."""
    n = store.get_note(note_id)
    if not n:
        return None
    excerpt = (n["body"] or "").strip().replace("\n", " ")
    excerpt = excerpt[:220].rstrip()
    if excerpt != n["body"].strip():
        excerpt += "…"
    # Community context for the note — we need the freshly computed graph
    # so cluster colors line up with everything else in the UI.
    g = synapse.compute_graph()
    cluster_id: int | None = None
    cluster_color: str | None = None
    for node in g.nodes:
        if node["id"] == note_id:
            cluster_id = node.get("community")
            cluster_color = node.get("community_color")
            break
    tgt = Target(
        kind="note",
        id=note_id,
        label=n["title"],
        excerpt=excerpt,
        cluster_id=cluster_id,
        cluster_color=cluster_color,
    )
    vec = embed(f"{n['title']}\n\n{n['body']}")
    return tgt, vec


def _target_from_cluster(cluster_id: int) -> tuple[Target, tuple[float, ...]] | None:
    """Load a cluster centroid as a Prism target. The label is the
    community's auto-derived name; the excerpt is the top-3 terms."""
    g = synapse.compute_graph()
    cmap = {node["id"]: node.get("community") for node in g.nodes}
    notes = {n["id"]: n for n in store.all_notes()}
    member_ids = [nid for nid, cid in cmap.items() if cid == cluster_id]
    if not member_ids:
        return None
    names = community_mod.name_communities(
        {nid: cluster_id for nid in member_ids}, notes
    )
    name, terms = names.get(cluster_id, (f"Cluster {cluster_id + 1}", []))
    color = community_mod.color_for(cluster_id)

    # Centroid via mean of member embeddings, L2-normalised.
    all_emb = dict(store.all_embeddings())
    dim = None
    acc: list[float] | None = None
    count = 0
    for nid in member_ids:
        v = all_emb.get(nid)
        if not v:
            continue
        if acc is None:
            dim = len(v)
            acc = [0.0] * dim
        for i in range(dim or 0):
            acc[i] += v[i]
        count += 1
    if not acc or count == 0:
        return None
    norm = math.sqrt(sum(x * x for x in acc))
    if norm == 0.0:
        return None
    inv = 1.0 / norm
    centroid = tuple(x * inv for x in acc)

    excerpt = " · ".join(terms) if terms else f"{count} notes"
    tgt = Target(
        kind="cluster",
        id=cluster_id,
        label=name,
        excerpt=excerpt,
        cluster_id=cluster_id,
        cluster_color=color,
    )
    return tgt, centroid


def _target_from_query(query: str) -> tuple[Target, tuple[float, ...]]:
    q = query.strip()
    label = q[:80] + ("…" if len(q) > 80 else "")
    excerpt = q[:220] + ("…" if len(q) > 220 else "")
    tgt = Target(
        kind="query",
        id=None,
        label=label,
        excerpt=excerpt,
        cluster_id=None,
        cluster_color=None,
    )
    return tgt, embed(q)


# ------------------------------------------------------- core computation


def compute_prism(
    *,
    target_kind: str,
    target_id: int | None = None,
    query: str | None = None,
    top_k_per_lens: int = DEFAULT_TOP_K_PER_LENS,
    floor_sim: float = DEFAULT_FLOOR_SIM,
    lens_ids: list[str] | None = None,
) -> PrismReport:
    """Compute the Prism report for the given target.

    Raises ``ValueError`` on invalid inputs so callers can 400 cleanly.
    """
    top_k_per_lens = max(MIN_TOP_K_PER_LENS, min(MAX_TOP_K_PER_LENS, top_k_per_lens))
    floor_sim = max(MIN_FLOOR_SIM, min(MAX_FLOOR_SIM, floor_sim))

    if target_kind == "note":
        if target_id is None:
            raise ValueError("target_kind=note requires target_id")
        loaded = _target_from_note(target_id)
        if not loaded:
            raise ValueError(f"note {target_id} not found")
        target, tvec = loaded
    elif target_kind == "cluster":
        if target_id is None:
            raise ValueError("target_kind=cluster requires target_id (cluster id)")
        loaded = _target_from_cluster(target_id)
        if not loaded:
            raise ValueError(f"cluster {target_id} not found or empty")
        target, tvec = loaded
    elif target_kind == "query":
        if not query or not query.strip():
            raise ValueError("target_kind=query requires a non-empty query")
        target, tvec = _target_from_query(query)
    else:
        raise ValueError(
            f"target_kind must be one of: note, cluster, query (got {target_kind!r})"
        )

    active_lens_ids = tuple(_LENS_ORDER)
    if lens_ids:
        wanted = [lid for lid in lens_ids if lid in LENSES]
        if wanted:
            active_lens_ids = tuple(wanted)

    notes = store.all_notes()
    if not notes:
        return _empty_report(target, active_lens_ids, top_k_per_lens, floor_sim)

    # Skip the target note itself when the target is a note — a note
    # is trivially its own top pick and that's uninteresting.
    exclude_id: int | None = target.id if target.kind == "note" else None

    # Pre-compute the base signals for every candidate note.
    all_emb = dict(store.all_embeddings())
    notes_by_id = {n["id"]: n for n in notes}
    g = synapse.compute_graph()
    node_by_id = {n["id"]: n for n in g.nodes}

    @dataclass
    class _Base:
        note: dict
        sim: float
        recency: float

    bases: list[_Base] = []
    for n in notes:
        nid = n["id"]
        if exclude_id is not None and nid == exclude_id:
            continue
        v = all_emb.get(nid)
        if not v:
            continue
        sim = cosine(tvec, v)
        if sim < floor_sim:
            continue
        bases.append(
            _Base(note=n, sim=sim, recency=_recency_multiplier(
                n.get("created_at"), n.get("last_seen_at")
            ))
        )

    # Per-lens ranking.
    lens_results: list[LensResult] = []
    top_taken: Counter[int] = Counter()

    for lens_id in active_lens_ids:
        spec = LENSES[lens_id]
        scored: list[tuple[float, float, float, int]] = []
        for b in bases:
            note = b.note
            text = f"{note['title']} {note['title']} {note['title']} {note['body']} {' '.join(note.get('tags', []))}"
            lex = _lexicon_density(text, spec.vocab)
            lens_multiplier = 1.0 + LEXICON_WEIGHT * lex
            raw = b.sim * lens_multiplier * b.recency
            # Novelty penalty applied AFTER the raw score so the ranking
            # only diversifies among close-scored candidates.
            penalty = NOVELTY_PENALTY * top_taken.get(note["id"], 0)
            final = raw - penalty
            scored.append((final, b.sim, lex, note["id"]))

        scored.sort(key=lambda t: (-t[0], -t[1], t[3]))
        top_slice = scored[:top_k_per_lens]

        picks: list[Pick] = []
        for i, (final, sim, lex, nid) in enumerate(top_slice):
            note = notes_by_id[nid]
            node = node_by_id.get(nid, {})
            picks.append(
                Pick(
                    note_id=nid,
                    title=note["title"],
                    body=note["body"],
                    tags=list(note.get("tags", [])),
                    cluster_id=node.get("community"),
                    cluster_color=node.get("community_color"),
                    similarity=round(sim, 4),
                    lexicon_score=round(lex, 4),
                    score=round(final, 4),
                    quote=_pick_quote(note["body"], note["title"], spec.vocab),
                    is_top=(i == 0),
                )
            )
            if i == 0:
                top_taken[nid] += 1

        # Coverage: mean of picks' final scores, gated on nontrivial
        # cosine + nontrivial lexicon of the top pick.
        if not picks:
            coverage = 0.0
            stance = "thin"
            weakness = "no note passed the similarity floor"
        else:
            mean_final = sum(p.score for p in picks) / len(picks)
            top_sim = picks[0].similarity
            top_lex = picks[0].lexicon_score
            avg_sim = sum(p.similarity for p in picks) / len(picks)
            gate = 1.0 if (top_sim >= floor_sim and top_lex > 0.0) else 0.0
            coverage = round(max(0.0, min(1.0, mean_final * gate)), 4)
            stance = _stance_for_lens(lens_id, top_sim, top_lex, avg_sim)
            if coverage < 0.05:
                weakness = "vault has no vocabulary for this lens"
            elif coverage < 0.15:
                weakness = "thin — only weak lens-vocabulary hits"
            elif avg_sim < 0.24:
                weakness = "picks are semantically loose"
            else:
                weakness = None

        lens_results.append(
            LensResult(
                id=spec.id,
                label=spec.label,
                color=spec.color,
                icon=spec.icon,
                tagline=spec.tagline,
                family=spec.family,
                picks=picks,
                coverage=coverage,
                stance=stance,
                weakness=weakness,
            )
        )

    # Roll-ups: weakest / strongest lens, stance distribution, dominant
    # family. Ignore "thin" lenses when picking the strongest so an
    # accidentally-off-topic lens can't hijack the summary.
    non_thin = [r for r in lens_results if r.stance != "thin"]
    strongest = max(non_thin, key=lambda r: r.coverage).id if non_thin else None
    # Weakest lens is the lens with the *lowest* coverage among all
    # requested lenses — including thin lenses, because that's where
    # your thinking is missing.
    weakest = min(lens_results, key=lambda r: r.coverage).id if lens_results else None

    stance_counts: Counter[str] = Counter(r.stance for r in lens_results)
    n_lenses = max(1, len(lens_results))
    stance_distribution = {
        s: round(stance_counts.get(s, 0) / n_lenses, 4)
        for s in ("reinforce", "challenge", "neutral", "thin")
    }

    family_weight: Counter[str] = Counter()
    for r in lens_results:
        family_weight[r.family] += r.coverage
    dominant_family = (
        max(family_weight.items(), key=lambda kv: kv[1])[0]
        if family_weight and max(family_weight.values()) > 0
        else None
    )

    spark_suggestion = _spark_prompt(target, weakest, lens_results)

    stats = {
        "candidates_considered": len(bases),
        "total_notes": len(notes),
        "lenses_computed": len(lens_results),
        "notes_appearing": len({p.note_id for r in lens_results for p in r.picks}),
    }

    config = {
        "top_k_per_lens": top_k_per_lens,
        "floor_sim": floor_sim,
        "lens_ids": list(active_lens_ids),
        "lexicon_weight": LEXICON_WEIGHT,
        "recency_bonus_max": RECENCY_BONUS_MAX,
        "novelty_penalty": NOVELTY_PENALTY,
    }

    return PrismReport(
        target=target,
        lenses=lens_results,
        weakest_lens=weakest,
        strongest_lens=strongest,
        stance_distribution=stance_distribution,
        dominant_family=dominant_family,
        spark_suggestion=spark_suggestion,
        prism_id=_prism_id(target, active_lens_ids, top_k_per_lens, floor_sim),
        config=config,
        stats=stats,
    )


def _empty_report(
    target: Target,
    lens_ids: tuple[str, ...],
    top_k: int,
    floor: float,
) -> PrismReport:
    lenses = []
    for lid in lens_ids:
        spec = LENSES[lid]
        lenses.append(
            LensResult(
                id=spec.id,
                label=spec.label,
                color=spec.color,
                icon=spec.icon,
                tagline=spec.tagline,
                family=spec.family,
                picks=[],
                coverage=0.0,
                stance="thin",
                weakness="vault is empty",
            )
        )
    return PrismReport(
        target=target,
        lenses=lenses,
        weakest_lens=lenses[0].id if lenses else None,
        strongest_lens=None,
        stance_distribution={"reinforce": 0.0, "challenge": 0.0, "neutral": 0.0, "thin": 1.0},
        dominant_family=None,
        spark_suggestion=None,
        prism_id=_prism_id(target, lens_ids, top_k, floor),
        config={
            "top_k_per_lens": top_k,
            "floor_sim": floor,
            "lens_ids": list(lens_ids),
            "lexicon_weight": LEXICON_WEIGHT,
            "recency_bonus_max": RECENCY_BONUS_MAX,
            "novelty_penalty": NOVELTY_PENALTY,
        },
        stats={
            "candidates_considered": 0,
            "total_notes": 0,
            "lenses_computed": len(lenses),
            "notes_appearing": 0,
        },
    )


# ------------------------------------------------------ spark suggestion


_LENS_SPARK_TEMPLATES: dict[str, str] = {
    "skeptic": "Write the strongest objection to “{label}” — the caveat you keep sidestepping.",
    "empiricist": "Draft the measurement that would settle “{label}” — what number, on what dataset, at what threshold.",
    "historian": "Trace where “{label}” came from — the predecessor idea, when it stopped being novel, what it replaced.",
    "futurist": "Project “{label}” three years out — what breaks, what generalizes, what looks quaint.",
    "practitioner": "Describe how you'd actually ship “{label}” next quarter — the rollout, the runbook, the failure mode.",
    "contrarian": "Argue the opposite of “{label}” — assume the consensus is exactly wrong and defend that.",
    "systems": "Map the second-order effects of “{label}” — the feedback loop it kicks off, the coupling it creates.",
    "first_principles": "Rebuild “{label}” from the axioms up — the definition, the necessary conditions, the sufficient ones.",
}


def _spark_prompt(
    target: Target, weakest: str | None, lenses: list[LensResult]
) -> str | None:
    if not weakest or target.kind == "query" and not target.label:
        return None
    template = _LENS_SPARK_TEMPLATES.get(weakest)
    if not template:
        return None
    return template.format(label=target.label)


# ----------------------------------------------------------- serializer


def serialize(report: PrismReport) -> dict:
    """API-shaped dict — mirrors the Pydantic schema in schemas.py."""
    return {
        "target": {
            "kind": report.target.kind,
            "id": report.target.id,
            "label": report.target.label,
            "excerpt": report.target.excerpt,
            "cluster_id": report.target.cluster_id,
            "cluster_color": report.target.cluster_color,
        },
        "lenses": [
            {
                "id": r.id,
                "label": r.label,
                "color": r.color,
                "icon": r.icon,
                "tagline": r.tagline,
                "family": r.family,
                "coverage": r.coverage,
                "stance": r.stance,
                "weakness": r.weakness,
                "picks": [
                    {
                        "note_id": p.note_id,
                        "title": p.title,
                        "cluster_id": p.cluster_id,
                        "cluster_color": p.cluster_color,
                        "similarity": p.similarity,
                        "lexicon_score": p.lexicon_score,
                        "score": p.score,
                        "quote": p.quote,
                        "tags": p.tags,
                        "is_top": p.is_top,
                    }
                    for p in r.picks
                ],
            }
            for r in report.lenses
        ],
        "weakest_lens": report.weakest_lens,
        "strongest_lens": report.strongest_lens,
        "stance_distribution": report.stance_distribution,
        "dominant_family": report.dominant_family,
        "spark_suggestion": report.spark_suggestion,
        "prism_id": report.prism_id,
        "config": report.config,
        "stats": report.stats,
    }


def list_lens_specs() -> list[dict]:
    """Static lens catalog for the frontend picker."""
    return [
        {
            "id": s.id,
            "label": s.label,
            "color": s.color,
            "icon": s.icon,
            "tagline": s.tagline,
            "family": s.family,
            "vocab_size": len(s.vocab),
        }
        for s in LENSES.values()
    ]


# ---------------------------------------------------------- markdown export


_STANCE_LABEL = {
    "reinforce": "reinforces",
    "challenge": "challenges",
    "neutral": "grazes",
    "thin": "no evidence",
}


def to_markdown(report: PrismReport) -> str:
    """Paste-anywhere summary — target, composite, per-lens picks with
    quotes. Idempotent for the same report."""
    lines: list[str] = []
    lines.append(f"# Prism · {report.target.label}")
    lines.append("")
    kind = report.target.kind
    if kind == "note":
        lines.append(f"_Note #{report.target.id}_")
    elif kind == "cluster":
        lines.append(f"_Cluster #{report.target.id}_")
    else:
        lines.append("_Ad-hoc query_")
    if report.target.excerpt:
        lines.append("")
        lines.append(f"> {report.target.excerpt}")
    lines.append("")
    lines.append(f"**prism_id:** `{report.prism_id}`")
    lines.append("")

    lines.append("## Composite")
    dist = report.stance_distribution
    lines.append(
        f"- reinforce **{int(dist.get('reinforce', 0) * 100)}%** · "
        f"challenge **{int(dist.get('challenge', 0) * 100)}%** · "
        f"neutral **{int(dist.get('neutral', 0) * 100)}%** · "
        f"thin **{int(dist.get('thin', 0) * 100)}%**"
    )
    if report.strongest_lens:
        strong = next(
            (l for l in report.lenses if l.id == report.strongest_lens), None
        )
        if strong:
            lines.append(
                f"- strongest lens: **{strong.label}** (coverage {strong.coverage:.2f})"
            )
    if report.weakest_lens:
        weak = next(
            (l for l in report.lenses if l.id == report.weakest_lens), None
        )
        if weak:
            lines.append(
                f"- weakest lens: **{weak.label}** (coverage {weak.coverage:.2f})"
            )
    if report.dominant_family:
        lines.append(f"- dominant family: **{report.dominant_family}**")
    if report.spark_suggestion:
        lines.append("")
        lines.append(f"> **Spark:** {report.spark_suggestion}")
    lines.append("")

    lines.append("## Lenses")
    for r in report.lenses:
        stance_label = _STANCE_LABEL.get(r.stance, r.stance)
        lines.append(f"### {r.label} — {r.icon} ({stance_label} · coverage {r.coverage:.2f})")
        lines.append(f"_{r.tagline}_")
        if r.weakness:
            lines.append(f"- weakness: {r.weakness}")
        if not r.picks:
            lines.append("- (no picks)")
        for p in r.picks:
            marker = "★" if p.is_top else "·"
            lines.append(
                f"- {marker} **{p.title}** — sim {p.similarity:.2f} · lex {p.lexicon_score:.2f}"
            )
            lines.append(f"  > {p.quote}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
