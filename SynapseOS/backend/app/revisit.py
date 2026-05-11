"""Daily Brief — a spaced-revisit engine for a second brain.

The PKM failure mode this addresses is universal: notes get written
once, never reread. ``revisit.py`` resurfaces notes you *should*
re-engage with, biased by:

- **Staleness.** How long since you last touched the note. A piecewise
  curve climbs through the first two weeks, holds, then gently decays
  for very-old notes (still surface them — just less urgently than
  freshly-stale ones).
- **Centrality.** Hub notes carry more of the second brain's structure;
  surface them more often than peripheral ones.
- **Orphan urgency.** Isolated notes get a flat bonus — they need
  attention before the threshold drifts and they become invisible.
- **Cluster diversity.** Greedy per-cluster cap so a single hot topic
  can't monopolize the brief.
- **Stable jitter.** ±0.05 noise seeded by ``(note_id, date)`` so two
  loads of the same day's brief return the same picks, and two
  different days don't.

The brief also synthesizes a one-line **journal prompt** per pick
(uses the note's cluster name + key terms when available) and surfaces
**connection suggestions** — notes from *other* clusters with strong
cosine similarity to the pick, so the user is nudged to bridge
clusters instead of doomscrolling inside one.

Pure stdlib. No new deps.
"""

from __future__ import annotations

import hashlib
import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Iterable

# Weights for the composite revisit score (these sum loosely to 1 when
# every term fires; the orphan bonus is additive on top of staleness +
# centrality which is intentional — orphans are special).
W_STALENESS = 0.55
W_CENTRALITY = 0.25
ORPHAN_BONUS = 0.30
CLUSTER_PENALTY_PER_PICK = 0.20  # subtract per same-cluster pick already chosen
JITTER_SPREAD = 0.05

# Staleness curve breakpoints (in days).
STALE_FLOOR_DAYS = 1     # below this, staleness = 0
STALE_RAMP_END = 14      # by this, staleness = 1
STALE_HOLD_END = 60      # hold at 1 through this point
STALE_DECAY_END = 180    # gentle decay floor
STALE_DECAY_FLOOR = 0.65

# For brand-new-but-never-seen notes (created_at exists, last_seen_at
# is null), we treat "days since touched" as days-since-created.
# Users routinely write a note then never re-read it; we still want
# those to start aging immediately.

# Suggestions floor — connection suggestions below this cosine are
# noise and we'd rather show nothing.
CONNECTION_FLOOR = 0.20
MAX_CONNECTIONS_PER_PICK = 2

# How many days *of brief output* we want to feel different from each
# other. The jitter is keyed by (note_id, YYYY-MM-DD), and that key
# changes every day. No carry-over state required.


@dataclass
class Reason:
    kind: str       # "stale" | "central" | "orphan" | "diverse"
    text: str       # short human-readable phrase, lowercase
    weight: float   # how much this contributed to the pick's score


@dataclass
class Connection:
    note_id: int
    title: str
    strength: float
    cluster_id: int | None = None
    cluster_name: str | None = None


@dataclass
class BriefPick:
    note_id: int
    title: str
    snippet: str
    tags: list[str]
    score: float
    reasons: list[Reason]
    prompt: str
    connections: list[Connection]
    cluster_id: int | None = None
    cluster_name: str | None = None
    cluster_color: str | None = None
    days_since_seen: int | None = None  # None = never touched
    is_orphan: bool = False


@dataclass
class Brief:
    date: str       # YYYY-MM-DD
    k: int
    total_notes: int
    picks: list[BriefPick] = field(default_factory=list)
    stats: dict = field(default_factory=dict)


# ----------------------------------------------------------- helpers


def _parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def _days_between(then: datetime | None, now: datetime) -> float | None:
    if then is None:
        return None
    if then.tzinfo is None:
        then = then.replace(tzinfo=timezone.utc)
    delta = now - then
    return max(0.0, delta.total_seconds() / 86400.0)


def staleness(days: float | None) -> float:
    """Piecewise staleness curve. ``days`` is days-since-last-touched
    (or days-since-creation if never touched)."""
    if days is None:
        return 1.0  # never touched at all → max staleness
    if days <= STALE_FLOOR_DAYS:
        # 0 → 0 over the first day. Smooth start so a 23-hour gap is
        # close to 0 and a 25-hour gap is close to the ramp.
        return 0.0
    if days <= STALE_RAMP_END:
        # Linear ramp 0 → 1 across (1, 14].
        return (days - STALE_FLOOR_DAYS) / (STALE_RAMP_END - STALE_FLOOR_DAYS)
    if days <= STALE_HOLD_END:
        return 1.0
    if days <= STALE_DECAY_END:
        # Linear decay from 1.0 to STALE_DECAY_FLOOR across (60, 180].
        span = STALE_DECAY_END - STALE_HOLD_END
        return 1.0 - (1.0 - STALE_DECAY_FLOOR) * (days - STALE_HOLD_END) / span
    return STALE_DECAY_FLOOR


def _jitter(note_id: int, date_key: str) -> float:
    """Deterministic noise in [-JITTER_SPREAD, +JITTER_SPREAD] keyed by
    (note_id, date). Same brief reload → same picks; next day → fresh
    ordering at the tie-breaker level without changing the underlying
    physics."""
    h = hashlib.sha256(f"{note_id}|{date_key}".encode("utf-8")).digest()
    # First 8 bytes → uint64, fold into [-1, 1].
    raw = int.from_bytes(h[:8], "big") / 2**64
    return (raw * 2.0 - 1.0) * JITTER_SPREAD


def _snippet(body: str, max_chars: int = 220) -> str:
    text = body.strip().replace("\n\n", " · ").replace("\n", " ")
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars].rsplit(" ", 1)[0]
    return f"{cut}…"


def _normalize(values: dict[int, float]) -> dict[int, float]:
    if not values:
        return values
    mx = max(values.values()) or 1.0
    return {k: (v / mx) for k, v in values.items()}


def _prompt_for(
    title: str,
    cluster_name: str | None,
    cluster_terms: list[str],
    is_orphan: bool,
    days: float | None,
) -> str:
    """One-line journal prompt. Cheap templates — the *content* is the
    note title and cluster terms; the template just frames it."""
    title_clean = title.strip().rstrip(".?!")
    if is_orphan:
        return f"Where does \"{title_clean}\" belong? What earlier note should connect to it?"
    if days is None and not cluster_name:
        return f"Re-read \"{title_clean}\". What part of it still holds up?"
    if cluster_name and cluster_terms:
        term = next((t for t in cluster_terms if t.lower() not in title_clean.lower()), cluster_terms[0])
        return (
            f"How does \"{title_clean}\" connect to {term} in the "
            f"{cluster_name} cluster?"
        )
    if cluster_name:
        return f"Does \"{title_clean}\" still capture what {cluster_name} means to you?"
    if days is not None and days >= STALE_HOLD_END:
        return f"You wrote this {int(days)} days ago: \"{title_clean}\". What would you change today?"
    return f"What's one thing you'd add to \"{title_clean}\" right now?"


def _reason_phrase_for_stale(days: float | None) -> str:
    if days is None:
        return "you've never re-read it"
    d = int(days)
    if d <= 1:
        return "fresh — touched within a day"
    if d < 7:
        return f"{d} day{'s' if d != 1 else ''} since touched"
    if d < 30:
        return f"{d} days since touched"
    if d < 90:
        weeks = d // 7
        return f"{weeks} weeks since touched"
    months = max(1, d // 30)
    return f"{months} month{'s' if months != 1 else ''} since touched"


# ------------------------------------------------------- main entry


def daily_brief(
    *,
    date: str,
    k: int,
    now: datetime,
    notes: list[dict],
    cmap: dict[int, int],
    community_lookup: dict[int, dict],
    degrees: dict[int, int],
    weights: dict[int, float],
    orphans: set[int],
    embeddings: dict[int, tuple[float, ...]],
    cosine_fn: Callable[[Iterable[float], Iterable[float]], float],
) -> Brief:
    """Compute today's brief. Pure function — no I/O.

    Caller assembles every input from store + synapse + community
    (which is the existing pipeline used by ``/graph`` and
    ``/communities``) so we don't duplicate that machinery here.
    """
    if not notes:
        return Brief(date=date, k=k, total_notes=0, picks=[], stats={"considered": 0})

    notes_by_id = {n["id"]: n for n in notes}
    max_degree = max(degrees.values()) if degrees else 1
    # Normalize centrality components into [0, 1].
    deg_norm = {nid: (degrees.get(nid, 0) / max_degree if max_degree else 0.0) for nid in notes_by_id}

    # Compute per-note staleness and base score.
    scored: list[tuple[float, dict, dict, float | None]] = []
    for n in notes:
        nid = n["id"]
        # When-last-touched: fall back to created_at so brand-new-but-
        # never-revisited notes start aging immediately.
        seen = _parse_iso(n.get("last_seen_at"))
        created = _parse_iso(n.get("created_at"))
        ref = seen or created
        days = _days_between(ref, now)

        stale = staleness(days)
        centrality = 0.55 * deg_norm.get(nid, 0.0) + 0.45 * weights.get(nid, 0.0)
        orphan = nid in orphans
        bonus = ORPHAN_BONUS if orphan else 0.0
        jitter = _jitter(nid, date)

        base = W_STALENESS * stale + W_CENTRALITY * centrality + bonus + jitter
        components = {
            "stale": stale,
            "centrality": centrality,
            "orphan": 1.0 if orphan else 0.0,
            "jitter": jitter,
        }
        scored.append((base, n, components, days))

    # Sort by base score descending, then drift in cluster diversity
    # greedily: pick the highest-scoring note whose cluster hasn't
    # already taken k_per_cluster picks. Once budget is exhausted, we
    # still allow further picks but with a -CLUSTER_PENALTY_PER_PICK
    # for each prior same-cluster pick so the ordering still respects
    # the original score for tightly-themed graphs.
    scored.sort(key=lambda t: t[0], reverse=True)

    picks: list[BriefPick] = []
    cluster_count: dict[int, int] = defaultdict(int)
    used: set[int] = set()

    # First pass: pure greedy with diversification penalty.
    while len(picks) < k and len(used) < len(scored):
        best: tuple[float, dict, dict, float | None] | None = None
        for base, n, comps, days in scored:
            if n["id"] in used:
                continue
            cid = cmap.get(n["id"])
            penalty = CLUSTER_PENALTY_PER_PICK * cluster_count.get(cid, 0) if cid is not None else 0.0
            effective = base - penalty
            if best is None or effective > best[0]:
                best = (effective, n, comps, days)
        if best is None:
            break
        eff_score, n, comps, days = best
        nid = n["id"]
        cid = cmap.get(nid)
        comm = community_lookup.get(cid) if cid is not None else None
        cluster_name = comm["name"] if comm else None
        cluster_color = comm["color"] if comm else None
        cluster_terms = comm["terms"] if comm else []
        is_orphan = nid in orphans

        # Reasons: ordered by contribution descending so the chip strip
        # reads "the dominant reason first".
        reason_pool: list[Reason] = []
        if comps["stale"] > 0.05:
            reason_pool.append(
                Reason(
                    kind="stale",
                    text=_reason_phrase_for_stale(days),
                    weight=round(W_STALENESS * comps["stale"], 4),
                )
            )
        if comps["centrality"] > 0.18:
            phrase = "hub note" if comps["centrality"] > 0.55 else "well-connected"
            reason_pool.append(
                Reason(
                    kind="central",
                    text=phrase,
                    weight=round(W_CENTRALITY * comps["centrality"], 4),
                )
            )
        if is_orphan:
            reason_pool.append(
                Reason(kind="orphan", text="orphan — no synapses yet", weight=round(ORPHAN_BONUS, 4))
            )
        if cid is not None and cluster_count.get(cid, 0) > 0:
            reason_pool.append(
                Reason(kind="diverse", text=f"deepens {cluster_name or 'cluster'}", weight=0.0)
            )
        # If absolutely nothing fires (shouldn't happen often), give a
        # generic reason so the UI never renders an empty chip strip.
        if not reason_pool:
            reason_pool.append(Reason(kind="stale", text="quiet note", weight=0.0))
        reason_pool.sort(key=lambda r: r.weight, reverse=True)

        prompt = _prompt_for(
            title=n["title"],
            cluster_name=cluster_name,
            cluster_terms=cluster_terms,
            is_orphan=is_orphan,
            days=days,
        )

        connections = _connection_suggestions(
            note_id=nid,
            cmap=cmap,
            community_lookup=community_lookup,
            embeddings=embeddings,
            notes_by_id=notes_by_id,
            cosine_fn=cosine_fn,
        )

        picks.append(
            BriefPick(
                note_id=nid,
                title=n["title"],
                snippet=_snippet(n["body"]),
                tags=list(n.get("tags") or []),
                score=round(eff_score, 4),
                reasons=reason_pool,
                prompt=prompt,
                connections=connections,
                cluster_id=cid,
                cluster_name=cluster_name,
                cluster_color=cluster_color,
                days_since_seen=None if days is None else int(days),
                is_orphan=is_orphan,
            )
        )
        used.add(nid)
        if cid is not None:
            cluster_count[cid] += 1

    stats = {
        "considered": len(notes),
        "orphan_count": len(orphans),
        "clusters_touched": len(cluster_count),
    }
    return Brief(date=date, k=k, total_notes=len(notes), picks=picks, stats=stats)


def _connection_suggestions(
    *,
    note_id: int,
    cmap: dict[int, int],
    community_lookup: dict[int, dict],
    embeddings: dict[int, tuple[float, ...]],
    notes_by_id: dict[int, dict],
    cosine_fn: Callable[[Iterable[float], Iterable[float]], float],
) -> list[Connection]:
    """Top notes from *other* clusters with strong cosine similarity.

    Why cross-cluster? Same-cluster neighbors already light up in the
    synapse view and the Inspector — that's not new information. The
    interesting suggestion is the note that *could* bridge clusters but
    doesn't yet (its cosine survives the floor but doesn't pass τ /
    top-K through the graph).
    """
    vi = embeddings.get(note_id)
    if vi is None:
        return []
    own_cluster = cmap.get(note_id)
    candidates: list[tuple[float, int]] = []
    for jid, vj in embeddings.items():
        if jid == note_id:
            continue
        jc = cmap.get(jid)
        # Cross-cluster preference: same-cluster needs a high bar to
        # qualify (the user already sees those). Other-cluster gets a
        # lower bar so we surface bridges.
        s = cosine_fn(vi, vj)
        if s < CONNECTION_FLOOR:
            continue
        if jc == own_cluster and s < CONNECTION_FLOOR + 0.10:
            continue
        candidates.append((s, jid))
    candidates.sort(reverse=True)

    out: list[Connection] = []
    seen_clusters: set[int] = set()
    for s, jid in candidates:
        if len(out) >= MAX_CONNECTIONS_PER_PICK:
            break
        n = notes_by_id.get(jid)
        if not n:
            continue
        jc = cmap.get(jid)
        # Don't show two suggestions from the same cluster — push
        # diversity here too.
        if jc is not None and jc in seen_clusters:
            continue
        comm = community_lookup.get(jc) if jc is not None else None
        out.append(
            Connection(
                note_id=jid,
                title=n["title"],
                strength=round(s, 4),
                cluster_id=jc,
                cluster_name=comm["name"] if comm else None,
            )
        )
        if jc is not None:
            seen_clusters.add(jc)
    return out


def today_key(now: datetime | None = None) -> str:
    """Stable UTC ``YYYY-MM-DD`` key used to seed brief jitter and
    cache the day's brief on the client."""
    n = now or datetime.now(timezone.utc)
    if n.tzinfo is None:
        n = n.replace(tzinfo=timezone.utc)
    return n.astimezone(timezone.utc).strftime("%Y-%m-%d")
