"""Pulse — what changed in your second brain over a window.

Atlas is the *snapshot* — every cluster, classified by where it sits on
the cohesion × activity quadrant *right now*. Chronicle is the
*biography* of a single cluster — how it evolved chapter by chapter.
Daily Brief is the *to-do* — pick five notes to re-engage with today.

Pulse fills the gap between those three. It is the **cross-cluster
time-windowed report**: across the whole graph, in the last *N* days,
what got written, where it landed, which synapses formed, which clusters
caught fire, which went silent, what vocabulary appeared and what fell
away. Open Pulse on a Friday afternoon and you can see your whole
week's worth of thinking on one screen.

The engine is pure stdlib + reuse of the existing graph/community
pipeline. Inputs:

  * ``window_days``   — the look-back horizon (default 7).
  * ``threshold/top_k`` — passed straight to ``synapse.compute_graph``.

Out of those it derives, deterministically:

  * **volume metrics** — notes added, words written (≈ chars / 5),
    revisits, current totals.
  * **streak** — longest run of consecutive days ending today with at
    least one note created.
  * **daily activity** — per-day bins of created vs revisited counts so
    the UI can render a sparkline.
  * **per-cluster pulse** — for every cluster: how many members are new
    in the window, how many were re-engaged, the share of the cluster
    that is new, the centroid drift between the pre-window and in-window
    halves (only if both halves are populated), a status (``born`` /
    ``emerging`` / ``hot`` / ``warm`` / ``dormant``), and a "what's new"
    term list pulled from the in-window members' own vocabulary.
  * **bridges born** — current synapses where the two ends sit in
    *different* clusters *and* at least one end is a new note. These
    are the cross-topical connections you just drew.
  * **hubs born** — new notes that already have ≥3 synapses. Instant
    centrality is rare and worth surfacing.
  * **vocab delta** — emerged terms (frequent in-window, rare prior)
    and faded terms (the inverse) computed across the whole graph, not
    just one cluster. Same forgiveness factor as Chronicle so a slow
    vocabulary shift still registers.
  * **recommendations** — a prioritized to-do list distilled from the
    above: synthesize hot clusters, name emerging clusters, revisit
    dormant ones, draw bridge-completing notes between fresh
    cross-cluster pairs.
  * **headline** — a one-sentence verdict on the window the UI can
    paste at the top.

Pure stdlib, deterministic, portable Markdown export.
"""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from . import community as community_mod
from . import store, synapse
from .embed import cosine

DEFAULT_WINDOW_DAYS = 7
WINDOW_MIN = 1
WINDOW_MAX = 365

# A new note needs at least this many synapses at the current
# (threshold, top_k) to count as a "hub born." Three is the smallest
# count that meaningfully exceeds the median degree on typical seed
# graphs — anything lower drowns the panel in noise.
HUB_MIN_DEGREE = 3

# Cap how many of each list we surface so the UI scales gracefully.
MAX_HUBS = 12
MAX_BRIDGES = 16
MAX_RECS = 14
MAX_VOCAB_TERMS = 8
MAX_NEW_TERMS_PER_CLUSTER = 5
MAX_HOT_TITLES = 5

# A term needs at least this many occurrences inside its primary epoch
# to count toward the vocab delta. Without the floor, single-mention
# typos creep into "emerged" lists on tiny graphs.
VOCAB_MIN_COUNT = 2

# Re-used from community.py / chronicle.py — keep the tokenizer aligned
# so cluster names and Pulse terms talk about the same words.
_TOKEN_RE = re.compile(r"[a-z][a-z0-9\-]{2,}")
_STOP = frozenset(
    """a an the and or but of for to in on at by from with as is are was were be been being
    this that these those it its they them their there here we you i me my our your his her
    not no yes do does did so if then than else when while which who whom how what why where
    can could should would may might must will shall just only also more most less few many
    very too into onto out up down off over under between among per about across after before
    again any all some each every both either neither one two three first second new old same
    such other another own enough still even ever never always often sometimes maybe perhaps
    way ways thing things stuff way like really kinda sorta etc vs via per
    """.split()
)

_EPOCH = datetime.min.replace(tzinfo=timezone.utc)


# --------------------------------------------------------------- data


@dataclass
class PulseClusterRow:
    cluster_id: int
    name: str
    color: str
    size: int
    new_count: int
    revisits_count: int
    share_new: float
    momentum: float
    centroid_drift: float | None
    status: str  # born / emerging / hot / warm / dormant
    last_touched_days: int | None
    new_terms: list[str]
    hot_titles: list[str]   # short list of new-note titles for tooltip / card body


@dataclass
class PulseBridge:
    source_id: int
    source_title: str
    target_id: int
    target_title: str
    source_cluster_id: int
    source_cluster_name: str
    source_cluster_color: str
    target_cluster_id: int
    target_cluster_name: str
    target_cluster_color: str
    strength: float
    source_is_new: bool
    target_is_new: bool


@dataclass
class PulseHub:
    note_id: int
    title: str
    snippet: str
    tags: list[str]
    degree: int
    weight: float
    cluster_id: int | None
    cluster_name: str | None
    cluster_color: str | None
    days_old: int


@dataclass
class PulseDay:
    date: str            # YYYY-MM-DD
    created: int
    revisited: int


@dataclass
class PulseRecommendation:
    kind: str            # synthesize / name / revisit / bridge / hub
    headline: str
    detail: str
    cluster_id: int | None
    cluster_name: str | None
    cluster_color: str | None
    note_id: int | None
    priority: float


@dataclass
class PulseReport:
    window_days: int
    generated_at: str
    window_start: str
    headline: str
    total_notes: int
    new_notes: int
    revisited_notes: int
    words_written: int
    streak_days: int
    synapses_total: int
    bridges_born: int
    hubs_born: int
    clusters_total: int
    clusters_hot: int
    clusters_emerging: int
    clusters_dormant: int
    activity: list[PulseDay]
    clusters: list[PulseClusterRow]
    bridges: list[PulseBridge]
    hubs: list[PulseHub]
    emerged_terms: list[str]
    faded_terms: list[str]
    recommendations: list[PulseRecommendation]
    summary: dict


# ----------------------------------------------------------- helpers


def _parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def _days_between(a: datetime, b: datetime) -> float:
    return max(0.0, (b - a).total_seconds() / 86400.0)


def _centroid(vecs: list[tuple[float, ...]]) -> tuple[float, ...] | None:
    """Mean-pool + L2 normalize so cosine is plain dot product."""
    if not vecs:
        return None
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


def _note_tokens(note: dict) -> list[str]:
    """Title gets weight-3 tokens, tags weight-2, body weight-1.

    Mirrors `community.name_communities` so the vocabulary delta speaks
    the same language as the cluster names the user already sees.
    """
    out: list[str] = []
    for t in _tokens(note.get("title", "")):
        out.extend([t] * 3)
    for tag in note.get("tags", []) or []:
        for t in _tokens(tag):
            out.extend([t] * 2)
    out.extend(_tokens(note.get("body", "")))
    return out


def _delta_terms(
    primary_tf: Counter[str],
    opposite_tf: Counter[str],
    *,
    limit: int,
) -> list[str]:
    """Top terms that are common in `primary` and rare in `opposite`.

    Score = count_primary − 0.5 · count_opposite. The 0.5 forgiveness
    factor lets a slowly mutating vocabulary still show up — without it,
    most small graphs hand back empty lists. Matches the rule
    `chronicle._delta_terms` uses for per-cluster chapters; doing the
    same thing here keeps the two surfaces visually consistent.
    """
    scored: list[tuple[float, str]] = []
    for term, c in primary_tf.items():
        if c < VOCAB_MIN_COUNT:
            continue
        score = c - 0.5 * opposite_tf.get(term, 0)
        if score <= 0:
            continue
        scored.append((score, term))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [t for _, t in scored[:limit]]


def _snippet(body: str, max_len: int = 140) -> str:
    """First sentence (or first ~max_len chars), trimmed."""
    body = (body or "").strip()
    if not body:
        return ""
    # Stop at the first sentence boundary if there is one inside the window.
    for end in (". ", "? ", "! ", "\n"):
        i = body.find(end)
        if 0 < i <= max_len:
            return body[: i + 1].strip()
    if len(body) <= max_len:
        return body
    return body[: max_len - 1].rstrip() + "…"


def _classify(
    new_count: int,
    members: int,
    revisits: int,
    share_new: float,
) -> str:
    if members == 0:
        return "dormant"
    if new_count >= members:
        return "born"
    if share_new >= 0.5 and new_count >= 2:
        return "emerging"
    if new_count >= 3:
        return "hot"
    if new_count >= 1 or revisits >= 1:
        return "warm"
    return "dormant"


def _streak(created_dates: list[str], today: datetime) -> int:
    """Longest run of consecutive days ending today (UTC) with ≥1 note."""
    days = {d for d in created_dates}
    if not days:
        return 0
    streak = 0
    cur = today
    # If the user hasn't written today yet, the streak still counts back
    # from yesterday so morning-of-day-N doesn't drop the badge.
    if cur.date().isoformat() not in days:
        cur = cur - timedelta(days=1)
    while cur.date().isoformat() in days:
        streak += 1
        cur = cur - timedelta(days=1)
    return streak


def _word_count(body: str) -> int:
    """Cheap heuristic — character count / 5 is the standard ‘word’ proxy
    that doesn't trip on punctuation or markdown. The UI prints this as
    a count, not a precise figure, so the heuristic is honest enough."""
    if not body:
        return 0
    return max(1, len(body) // 5)


# ------------------------------------------------------------- core


def compute_pulse(
    window_days: int = DEFAULT_WINDOW_DAYS,
    threshold: float | None = None,
    top_k: int | None = None,
) -> PulseReport:
    """Build the full Pulse report at the given window + graph params."""
    th = synapse.DEFAULT_THRESHOLD if threshold is None else threshold
    tk = synapse.DEFAULT_TOP_K if top_k is None else top_k
    window_days = max(WINDOW_MIN, min(WINDOW_MAX, int(window_days)))

    now = datetime.now(timezone.utc).replace(microsecond=0)
    window_start = now - timedelta(days=window_days)

    notes = store.all_notes()
    g = synapse.compute_graph(threshold=th, top_k=tk)
    notes_by_id = {n["id"]: n for n in g.nodes}
    cmap = {n["id"]: n.get("community", 0) for n in g.nodes}
    built = community_mod.build_communities(cmap, notes_by_id)
    embeddings = dict(store.all_embeddings())
    last_seen = store.last_seen_map()

    # Stable lookups + per-note metadata derived once.
    note_full: dict[int, dict] = {n["id"]: n for n in notes}
    note_created: dict[int, datetime | None] = {
        n["id"]: _parse_iso(n.get("created_at")) for n in notes
    }
    note_touched: dict[int, datetime | None] = {
        nid: _parse_iso(ts) for nid, ts in last_seen.items()
    }

    new_ids: set[int] = set()
    revisited_ids: set[int] = set()
    prior_ids: set[int] = set()
    created_day_counts: Counter[str] = Counter()
    revisited_day_counts: Counter[str] = Counter()
    last_touched_per_note: dict[int, datetime] = {}

    words_written = 0
    for n in notes:
        nid = n["id"]
        created = note_created.get(nid)
        touched = note_touched.get(nid)

        # Window membership — created OR touched count as "activity in window,"
        # but new vs revisited buckets are mutually exclusive.
        is_new = created is not None and created >= window_start
        is_revisit = (
            not is_new
            and touched is not None
            and touched >= window_start
        )
        if is_new:
            new_ids.add(nid)
            words_written += _word_count(n.get("body", ""))
        elif is_revisit:
            revisited_ids.add(nid)
        else:
            prior_ids.add(nid)

        if created is not None and created >= window_start:
            created_day_counts[created.date().isoformat()] += 1
        if touched is not None and touched >= window_start:
            revisited_day_counts[touched.date().isoformat()] += 1
        # Most-recent event per note feeds the cluster "last touched"
        # field — newest of (created, touched).
        most_recent = max(created or _EPOCH, touched or _EPOCH)
        if most_recent != _EPOCH:
            last_touched_per_note[nid] = most_recent

    # Activity sparkline: one entry per day across the window, oldest
    # first so the UI draws left-to-right time.
    activity: list[PulseDay] = []
    for i in range(window_days, -1, -1):
        day = (now - timedelta(days=i)).date().isoformat()
        activity.append(
            PulseDay(
                date=day,
                created=created_day_counts.get(day, 0),
                revisited=revisited_day_counts.get(day, 0),
            )
        )

    # Per-cluster pass.
    cluster_rows: list[PulseClusterRow] = []
    cluster_lookup: dict[int, PulseClusterRow] = {}
    for c in built:
        member_ids = [m for m in c.member_ids if m in note_full]
        if not member_ids:
            continue

        new_in = [m for m in member_ids if m in new_ids]
        rev_in = [m for m in member_ids if m in revisited_ids]
        prior_in = [m for m in member_ids if m in prior_ids]
        share_new = round(len(new_in) / len(member_ids), 4) if member_ids else 0.0

        # Centroid drift: only meaningful when both epochs are populated.
        # If the cluster is newborn or entirely pre-window we leave it
        # null so the UI can render "—" instead of a misleading 0.
        drift: float | None = None
        if len(prior_in) >= 2 and len(new_in) >= 2:
            cent_prior = _centroid(
                [embeddings[m] for m in prior_in if m in embeddings]
            )
            cent_new = _centroid(
                [embeddings[m] for m in new_in if m in embeddings]
            )
            if cent_prior is not None and cent_new is not None:
                drift = round(max(0.0, 1.0 - cosine(cent_prior, cent_new)), 4)

        # Status drives the badge color + the recommendation rules.
        status = _classify(len(new_in), len(member_ids), len(rev_in), share_new)

        # Momentum is a soft 0..1 blend the UI ranks by. We want it to
        # reward "actually moved in the window" over raw size — sharing
        # ratio dominates, revisits add a smaller signal, and a tiny
        # density term breaks ties between clusters with no in-window
        # activity in a way that favors structurally cohesive ones.
        density_proxy = min(1.0, len(member_ids) / max(1, len(notes)))
        momentum = round(
            min(
                1.0,
                0.55 * share_new
                + 0.25 * (len(rev_in) / max(1, len(member_ids)))
                + 0.20 * density_proxy,
            ),
            4,
        )

        # last_touched_days against now, across both created + touched.
        most_recent = _EPOCH
        for m in member_ids:
            mr = last_touched_per_note.get(m)
            if mr and mr > most_recent:
                most_recent = mr
        last_touched_days: int | None = (
            int(_days_between(most_recent, now)) if most_recent != _EPOCH else None
        )

        # "What's new" term list — score the in-window members' tokens
        # against the rest of the cluster so the panel surfaces what the
        # *new* notes are about, not the whole cluster's name.
        new_tf: Counter[str] = Counter()
        rest_tf: Counter[str] = Counter()
        for m in new_in:
            new_tf.update(_note_tokens(note_full[m]))
        for m in member_ids:
            if m in new_ids:
                continue
            rest_tf.update(_note_tokens(note_full[m]))
        new_terms = _delta_terms(new_tf, rest_tf, limit=MAX_NEW_TERMS_PER_CLUSTER)

        hot_titles: list[str] = []
        # Sort new titles by created_at desc so the most recent shows first.
        new_in_sorted = sorted(
            new_in,
            key=lambda m: note_created.get(m) or _EPOCH,
            reverse=True,
        )
        for m in new_in_sorted[:MAX_HOT_TITLES]:
            t = (note_full[m].get("title") or "").strip()
            if t:
                hot_titles.append(t)

        row = PulseClusterRow(
            cluster_id=c.id,
            name=c.name,
            color=c.color,
            size=len(member_ids),
            new_count=len(new_in),
            revisits_count=len(rev_in),
            share_new=share_new,
            momentum=momentum,
            centroid_drift=drift,
            status=status,
            last_touched_days=last_touched_days,
            new_terms=new_terms,
            hot_titles=hot_titles,
        )
        cluster_rows.append(row)
        cluster_lookup[c.id] = row

    # Order: hot/emerging/born first (momentum desc), dormant last.
    _STATUS_RANK = {"hot": 0, "emerging": 1, "born": 2, "warm": 3, "dormant": 4}
    cluster_rows.sort(
        key=lambda r: (_STATUS_RANK.get(r.status, 9), -r.momentum, -r.size, r.cluster_id)
    )

    # Bridges born — edges in the current graph whose endpoints sit in
    # different clusters AND at least one endpoint is a new note.
    bridges: list[PulseBridge] = []
    for e in g.edges:
        u, v = e["source"], e["target"]
        cu = cmap.get(u)
        cv = cmap.get(v)
        if cu is None or cv is None or cu == cv:
            continue
        if u not in new_ids and v not in new_ids:
            continue
        if u not in cluster_lookup or v not in cluster_lookup:
            continue
        cu_row = cluster_lookup[cu]
        cv_row = cluster_lookup[cv]
        bridges.append(
            PulseBridge(
                source_id=u,
                source_title=note_full.get(u, {}).get("title", ""),
                target_id=v,
                target_title=note_full.get(v, {}).get("title", ""),
                source_cluster_id=cu,
                source_cluster_name=cu_row.name,
                source_cluster_color=cu_row.color,
                target_cluster_id=cv,
                target_cluster_name=cv_row.name,
                target_cluster_color=cv_row.color,
                strength=float(e["strength"]),
                source_is_new=u in new_ids,
                target_is_new=v in new_ids,
            )
        )
    bridges.sort(key=lambda b: (-b.strength, b.source_id, b.target_id))
    bridges_total = len(bridges)
    bridges = bridges[:MAX_BRIDGES]

    # Hubs born — new notes whose current degree clears HUB_MIN_DEGREE.
    hubs: list[PulseHub] = []
    for n in g.nodes:
        nid = n["id"]
        if nid not in new_ids:
            continue
        deg = int(n.get("degree", 0))
        if deg < HUB_MIN_DEGREE:
            continue
        created = note_created.get(nid)
        days_old = int(_days_between(created, now)) if created else 0
        cid = cmap.get(nid)
        row = cluster_lookup.get(cid) if cid is not None else None
        hubs.append(
            PulseHub(
                note_id=nid,
                title=n.get("title", ""),
                snippet=_snippet(note_full.get(nid, {}).get("body", "")),
                tags=list(note_full.get(nid, {}).get("tags", []) or []),
                degree=deg,
                weight=float(n.get("weight", 0.0)),
                cluster_id=cid if row else None,
                cluster_name=row.name if row else None,
                cluster_color=row.color if row else None,
                days_old=days_old,
            )
        )
    hubs.sort(key=lambda h: (-h.degree, -h.weight, h.note_id))
    hubs_total = len(hubs)
    hubs = hubs[:MAX_HUBS]

    # Library-wide vocab delta.
    prior_tf: Counter[str] = Counter()
    new_tf: Counter[str] = Counter()
    for nid in prior_ids:
        prior_tf.update(_note_tokens(note_full[nid]))
    for nid in new_ids:
        new_tf.update(_note_tokens(note_full[nid]))
    emerged_terms = _delta_terms(new_tf, prior_tf, limit=MAX_VOCAB_TERMS)
    faded_terms = _delta_terms(prior_tf, new_tf, limit=MAX_VOCAB_TERMS)

    # Streak — uses created-day set, today included.
    created_days = [d for d in created_day_counts.keys()]
    # Extend streak window beyond the requested look-back: a 60-day streak
    # is interesting even when the user opened the 7-day Pulse.
    extra_notes = [
        c for c in (note_created.values()) if c is not None
    ]
    all_created_days = {c.date().isoformat() for c in extra_notes}
    streak = _streak(sorted(all_created_days), now)

    # Aggregate counts.
    clusters_hot = sum(1 for r in cluster_rows if r.status == "hot")
    clusters_emerging = sum(
        1 for r in cluster_rows if r.status in ("emerging", "born")
    )
    clusters_dormant = sum(1 for r in cluster_rows if r.status == "dormant")

    # Recommendations distil the same signals the cluster cards show
    # into a one-click action list. Priority is a soft rank, not a hard
    # score — the UI just needs a consistent surfacing order.
    recs = _build_recommendations(
        cluster_rows=cluster_rows,
        bridges=bridges,
        bridges_total=bridges_total,
        hubs=hubs,
        new_count=len(new_ids),
        revisited_count=len(revisited_ids),
        window_days=window_days,
    )

    # Headline — the single line the modal sub-header prints. We pick a
    # narrative that matches the dominant shape of the window: silence,
    # quiet maintenance, a hot streak, an emerging frontier, or a
    # cross-pollination week.
    headline = _build_headline(
        new_count=len(new_ids),
        revisited_count=len(revisited_ids),
        words_written=words_written,
        clusters_hot=clusters_hot,
        clusters_emerging=clusters_emerging,
        bridges_born=bridges_total,
        hubs_born=hubs_total,
        streak=streak,
        window_days=window_days,
    )

    summary = {
        "new_notes": len(new_ids),
        "revisited_notes": len(revisited_ids),
        "words_written": words_written,
        "streak_days": streak,
        "bridges_born": bridges_total,
        "hubs_born": hubs_total,
        "clusters_hot": clusters_hot,
        "clusters_emerging": clusters_emerging,
        "clusters_dormant": clusters_dormant,
        "synapses_total": int(g.stats.get("edges", 0)),
        "avg_degree": float(g.stats.get("avg_degree", 0.0)),
    }

    return PulseReport(
        window_days=window_days,
        generated_at=now.isoformat(),
        window_start=window_start.isoformat(),
        headline=headline,
        total_notes=len(notes),
        new_notes=len(new_ids),
        revisited_notes=len(revisited_ids),
        words_written=words_written,
        streak_days=streak,
        synapses_total=int(g.stats.get("edges", 0)),
        bridges_born=bridges_total,
        hubs_born=hubs_total,
        clusters_total=len(cluster_rows),
        clusters_hot=clusters_hot,
        clusters_emerging=clusters_emerging,
        clusters_dormant=clusters_dormant,
        activity=activity,
        clusters=cluster_rows,
        bridges=bridges,
        hubs=hubs,
        emerged_terms=emerged_terms,
        faded_terms=faded_terms,
        recommendations=recs,
        summary=summary,
    )


# ----------------------------------------------------- recommendations


def _build_recommendations(
    *,
    cluster_rows: list[PulseClusterRow],
    bridges: list[PulseBridge],
    bridges_total: int,
    hubs: list[PulseHub],
    new_count: int,
    revisited_count: int,
    window_days: int,
) -> list[PulseRecommendation]:
    """Turn the pulse signals into an ordered to-do list.

    Each kind has a deliberately different priority band so the UI's
    "top 5" view shows a healthy mix instead of five revisits in a row:

      synthesize  0.70+   — biggest payoff: catch a hot topic before it
                            scatters across the next week's notes.
      name        0.60    — the cluster doesn't have a meaningful label
                            yet because the new majority is unsettled.
      hub         0.50    — a new note grew structural importance fast;
                            worth a re-read while the context is fresh.
      bridge      0.40    — pairs that already wired; flag the highest-
                            strength fresh cross-cluster connection.
      revisit     0.20    — dormant cluster nudge; lowest band.
    """
    out: list[PulseRecommendation] = []

    for r in cluster_rows:
        if r.status == "hot" and r.new_count >= 3:
            out.append(
                PulseRecommendation(
                    kind="synthesize",
                    headline=f"Synthesize {r.name} — {r.new_count} new in {window_days}d",
                    detail=(
                        f"{r.new_count} new notes joined this cluster in the last "
                        f"{window_days}d. Lock the shape in with a brief before the "
                        f"topic scatters across next week's writing."
                    ),
                    cluster_id=r.cluster_id,
                    cluster_name=r.name,
                    cluster_color=r.color,
                    note_id=None,
                    priority=0.70 + 0.04 * min(r.new_count, 6),
                )
            )
        elif r.status == "emerging" and r.new_count >= 2:
            out.append(
                PulseRecommendation(
                    kind="name",
                    headline=f"{r.name} is forming — name & seed it",
                    detail=(
                        f"{int(r.share_new * 100)}% of this cluster is new. The "
                        f"label may still be provisional — synthesize once to "
                        f"set the framing."
                    ),
                    cluster_id=r.cluster_id,
                    cluster_name=r.name,
                    cluster_color=r.color,
                    note_id=None,
                    priority=0.60 + 0.05 * min(r.new_count, 4),
                )
            )
        elif r.status == "born" and r.new_count >= 2:
            out.append(
                PulseRecommendation(
                    kind="name",
                    headline=f"New cluster: {r.name}",
                    detail=(
                        f"{r.new_count} fresh notes formed a brand-new topic. "
                        f"Worth a synthesis pass so the name sticks."
                    ),
                    cluster_id=r.cluster_id,
                    cluster_name=r.name,
                    cluster_color=r.color,
                    note_id=None,
                    priority=0.65,
                )
            )
        elif (
            r.status == "dormant"
            and r.size >= 3
            and r.last_touched_days is not None
            and r.last_touched_days >= max(2 * window_days, 14)
        ):
            out.append(
                PulseRecommendation(
                    kind="revisit",
                    headline=f"{r.name} hasn't moved in {r.last_touched_days}d",
                    detail=(
                        f"{r.size} notes, untouched for {r.last_touched_days}d. "
                        f"Re-read or archive — silence past this point usually "
                        f"means the topic is done with you."
                    ),
                    cluster_id=r.cluster_id,
                    cluster_name=r.name,
                    cluster_color=r.color,
                    note_id=None,
                    priority=0.20 + min(0.15, r.last_touched_days / 600.0),
                )
            )

    for h in hubs[:5]:
        out.append(
            PulseRecommendation(
                kind="hub",
                headline=f"“{h.title}” became a hub — {h.degree} synapses",
                detail=(
                    f"A note you wrote {h.days_old}d ago already has "
                    f"{h.degree} synapses. Re-read while the context is "
                    f"fresh; chances are it's a hinge for the cluster."
                ),
                cluster_id=h.cluster_id,
                cluster_name=h.cluster_name,
                cluster_color=h.cluster_color,
                note_id=h.note_id,
                priority=0.50 + 0.02 * min(h.degree, 8),
            )
        )

    for b in bridges[:4]:
        out.append(
            PulseRecommendation(
                kind="bridge",
                headline=(
                    f"New bridge: {b.source_cluster_name} ↔ "
                    f"{b.target_cluster_name}"
                ),
                detail=(
                    f"“{b.source_title}” and “{b.target_title}” wired "
                    f"across clusters at cosine {b.strength:.2f}. Worth "
                    f"a connector note that spells out *why* the two "
                    f"topics belong together."
                ),
                cluster_id=b.source_cluster_id,
                cluster_name=b.source_cluster_name,
                cluster_color=b.source_cluster_color,
                note_id=b.source_id,
                priority=0.40 + min(0.10, b.strength / 3.0),
            )
        )

    # Stable order: priority desc, then kind alpha to break ties so the
    # UI doesn't jitter between identical signals.
    out.sort(key=lambda r: (-r.priority, r.kind, r.headline))
    return out[:MAX_RECS]


def _build_headline(
    *,
    new_count: int,
    revisited_count: int,
    words_written: int,
    clusters_hot: int,
    clusters_emerging: int,
    bridges_born: int,
    hubs_born: int,
    streak: int,
    window_days: int,
) -> str:
    """One-line narrative for the modal sub-header."""
    if new_count == 0 and revisited_count == 0:
        return (
            f"No new notes in the last {window_days}d. "
            f"Pulse will surface activity as soon as you write."
        )
    if new_count == 0 and revisited_count > 0:
        return (
            f"Quiet writing week — {revisited_count} re-engagement"
            f"{'s' if revisited_count != 1 else ''} but no new notes. "
            f"Reading is still thinking."
        )

    pieces: list[str] = [
        f"{new_count} new note{'s' if new_count != 1 else ''}",
        f"≈ {words_written:,} words",
    ]
    if revisited_count:
        pieces.append(
            f"{revisited_count} revisit{'s' if revisited_count != 1 else ''}"
        )
    if clusters_hot:
        pieces.append(
            f"{clusters_hot} cluster{'s' if clusters_hot != 1 else ''} hot"
        )
    elif clusters_emerging:
        pieces.append(
            f"{clusters_emerging} forming"
        )
    if bridges_born:
        pieces.append(
            f"{bridges_born} cross-cluster bridge"
            f"{'s' if bridges_born != 1 else ''}"
        )
    if hubs_born:
        pieces.append(f"{hubs_born} hub{'s' if hubs_born != 1 else ''} born")
    if streak >= 3:
        pieces.append(f"streak {streak}d")

    return " · ".join(pieces) + f"  (last {window_days}d)"


# ---------------------------------------------------------------- export


def to_markdown(r: PulseReport) -> str:
    """Render the report as a portable Markdown brief."""
    out: list[str] = []
    out.append(f"# Pulse — last {r.window_days}d  ·  {r.generated_at[:10]}")
    out.append("")
    out.append(f"_{r.headline}_")
    out.append("")
    out.append("| Metric | Count |")
    out.append("|---|---:|")
    out.append(f"| New notes | {r.new_notes} |")
    out.append(f"| Revisits | {r.revisited_notes} |")
    out.append(f"| Words written | {r.words_written:,} |")
    out.append(f"| Bridges born | {r.bridges_born} |")
    out.append(f"| Hubs born | {r.hubs_born} |")
    out.append(f"| Streak | {r.streak_days}d |")
    out.append(f"| Hot clusters | {r.clusters_hot} |")
    out.append(f"| Emerging clusters | {r.clusters_emerging} |")
    out.append(f"| Dormant clusters | {r.clusters_dormant} |")
    out.append("")

    if r.emerged_terms or r.faded_terms:
        out.append("## Vocabulary delta")
        out.append("")
        if r.emerged_terms:
            out.append(f"- **Emerged:** {', '.join(r.emerged_terms)}")
        if r.faded_terms:
            out.append(f"- **Faded:** {', '.join(r.faded_terms)}")
        out.append("")

    active = [c for c in r.clusters if c.status != "dormant"]
    if active:
        out.append("## Active clusters")
        out.append("")
        for c in active:
            extras: list[str] = [f"{c.new_count} new", f"{c.revisits_count} revisits"]
            if c.centroid_drift is not None:
                extras.append(f"drift {c.centroid_drift:.2f}")
            extras.append(f"share new {int(c.share_new * 100)}%")
            out.append(f"- **{c.name}** — *{c.status}* · " + " · ".join(extras))
            if c.new_terms:
                out.append(f"    - new vocabulary: {', '.join(c.new_terms)}")
            for t in c.hot_titles:
                out.append(f"    - · {t}")
        out.append("")

    if r.bridges:
        out.append("## Bridges born")
        out.append("")
        for b in r.bridges:
            out.append(
                f"- *{b.source_cluster_name}* ↔ *{b.target_cluster_name}* — "
                f"“{b.source_title}” ↔ “{b.target_title}” (cosine {b.strength:.2f})"
            )
        out.append("")

    if r.hubs:
        out.append("## Hubs born")
        out.append("")
        for h in r.hubs:
            cluster_tag = f" ({h.cluster_name})" if h.cluster_name else ""
            out.append(
                f"- **{h.title}**{cluster_tag} — {h.degree} synapses · "
                f"{h.days_old}d old"
            )
            if h.snippet:
                out.append(f"    > {h.snippet}")
        out.append("")

    if r.recommendations:
        out.append("## Recommendations")
        out.append("")
        for rec in r.recommendations:
            out.append(f"- **{rec.headline}** — {rec.detail}")
        out.append("")

    return "\n".join(out).rstrip() + "\n"


# ---------------------------------------------------------------- serialize


def serialize(r: PulseReport) -> dict:
    """Pure-dict form of the report for the JSON response."""
    return {
        "window_days": r.window_days,
        "generated_at": r.generated_at,
        "window_start": r.window_start,
        "headline": r.headline,
        "total_notes": r.total_notes,
        "new_notes": r.new_notes,
        "revisited_notes": r.revisited_notes,
        "words_written": r.words_written,
        "streak_days": r.streak_days,
        "synapses_total": r.synapses_total,
        "bridges_born": r.bridges_born,
        "hubs_born": r.hubs_born,
        "clusters_total": r.clusters_total,
        "clusters_hot": r.clusters_hot,
        "clusters_emerging": r.clusters_emerging,
        "clusters_dormant": r.clusters_dormant,
        "activity": [
            {"date": d.date, "created": d.created, "revisited": d.revisited}
            for d in r.activity
        ],
        "clusters": [
            {
                "cluster_id": c.cluster_id,
                "name": c.name,
                "color": c.color,
                "size": c.size,
                "new_count": c.new_count,
                "revisits_count": c.revisits_count,
                "share_new": c.share_new,
                "momentum": c.momentum,
                "centroid_drift": c.centroid_drift,
                "status": c.status,
                "last_touched_days": c.last_touched_days,
                "new_terms": c.new_terms,
                "hot_titles": c.hot_titles,
            }
            for c in r.clusters
        ],
        "bridges": [
            {
                "source_id": b.source_id,
                "source_title": b.source_title,
                "target_id": b.target_id,
                "target_title": b.target_title,
                "source_cluster_id": b.source_cluster_id,
                "source_cluster_name": b.source_cluster_name,
                "source_cluster_color": b.source_cluster_color,
                "target_cluster_id": b.target_cluster_id,
                "target_cluster_name": b.target_cluster_name,
                "target_cluster_color": b.target_cluster_color,
                "strength": round(b.strength, 4),
                "source_is_new": b.source_is_new,
                "target_is_new": b.target_is_new,
            }
            for b in r.bridges
        ],
        "hubs": [
            {
                "note_id": h.note_id,
                "title": h.title,
                "snippet": h.snippet,
                "tags": h.tags,
                "degree": h.degree,
                "weight": h.weight,
                "cluster_id": h.cluster_id,
                "cluster_name": h.cluster_name,
                "cluster_color": h.cluster_color,
                "days_old": h.days_old,
            }
            for h in r.hubs
        ],
        "emerged_terms": r.emerged_terms,
        "faded_terms": r.faded_terms,
        "recommendations": [
            {
                "kind": rec.kind,
                "headline": rec.headline,
                "detail": rec.detail,
                "cluster_id": rec.cluster_id,
                "cluster_name": rec.cluster_name,
                "cluster_color": rec.cluster_color,
                "note_id": rec.note_id,
                "priority": round(rec.priority, 4),
            }
            for rec in r.recommendations
        ],
        "summary": r.summary,
    }
