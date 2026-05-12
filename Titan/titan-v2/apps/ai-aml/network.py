"""TITAN AML network intelligence.

Per-account scoring (`risk.py`) answers "is this account suspicious?". This
module answers the question regulators actually ask in a real investigation:
"who is this account *connected* to, and what does the picture look like once
we follow the money?"

It does three things, no ML:

1. **Entity resolution.** Cluster account ids + counterparty ids that
   are very likely the *same* real-world entity. Two signals, OR-combined
   via Union-Find:

       a) Name similarity ≥ NAME_TAU. Reuses sanctions.py's
          normalize / token-set / char-3gram primitives so the matcher is
          identical to the watchlist one — same audit semantics.
       b) Counterparty fingerprint Jaccard ≥ COUNTERPARTY_TAU. Two parties
          that transact with substantially overlapping sets of other
          parties are likely the same hand.

2. **Risk propagation.** A modified PageRank biased toward the seed risk
   vector — `r ← (1−α)·seed + α · Wᵀ · r`. The seed is per-entity
   max(account risk_score) / 100. W is the row-normalized money-flow
   matrix. Converges in ≤20 iterations on demo data; we cap at 30 and
   tol=1e-5 anyway. The result is `network_risk ∈ [0, 100]` per entity
   that absorbs neighborhood signal: a clean account heavily linked to a
   sanctioned one ends up amber, not green.

3. **Counterfactual analysis.** Ablate a set of entities (drop every
   transaction touching them), rerun risk.py + propagation, return per
   entity score deltas. This is the answer to "what if we knew Entity-X
   was a mule and removed it — does the rest of the picture clear?"

There's also a per-account **attribution** call: leave-one-counterparty-out
rerun to rank which counterparties contribute the most lift to an account's
risk score. That's the explainable-AI surface auditors want.

All outputs are deterministic — same input → same coords, same scores,
same clusters. The frontend can render the graph as soon as it gets the
response; no client-side simulation, no flickering.
"""

from __future__ import annotations

import hashlib
import math
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

import risk as risk_engine
import sanctions as sanctions_engine

# ---------------------------------------------------------------------------
# Tunables. Exposed via /aml/network/rules so auditors can verify them.
# ---------------------------------------------------------------------------

# Entity resolution thresholds.
NAME_TAU = 0.78          # combined fuzzy-name similarity for "same entity"
COUNTERPARTY_TAU = 0.55  # Jaccard of shared counterparties for "same hand"
NAME_MIN_TOKENS = 2      # don't merge on a single-token match (too noisy)

# Propagation parameters.
PR_ALPHA = 0.70   # how much to absorb from neighborhood per iteration
PR_MAX_ITER = 30
PR_TOL = 1e-5

# Layout (deterministic Fruchterman-Reingold variant).
LAYOUT_ITER = 80
LAYOUT_SIZE = 1000.0       # virtual canvas
LAYOUT_REPULSE = 4200.0    # k² in F-R
LAYOUT_ATTRACT = 1.0       # spring stiffness multiplier
LAYOUT_GRAVITY = 0.04      # pull toward centre per node (keeps disconnects in frame)
LAYOUT_COOL = 0.95

# Display caps.
MAX_NODES = 80         # truncate to top-N by combined activity + risk
MAX_EDGES = 200
ATTRIB_MAX_REPORT = 8  # how many top contributors to surface per account


# ---------------------------------------------------------------------------
# Union-Find
# ---------------------------------------------------------------------------


class _UF:
    def __init__(self, items: Iterable[str]) -> None:
        self.p: Dict[str, str] = {x: x for x in items}
        self.r: Dict[str, int] = {x: 0 for x in self.p}

    def find(self, x: str) -> str:
        # iterative for safety on long chains
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        if self.r[ra] < self.r[rb]:
            ra, rb = rb, ra
        self.p[rb] = ra
        if self.r[ra] == self.r[rb]:
            self.r[ra] += 1

    def groups(self) -> Dict[str, List[str]]:
        out: Dict[str, List[str]] = defaultdict(list)
        for x in self.p:
            out[self.find(x)].append(x)
        return out


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _txs_from_rows(rows: Iterable[Dict[str, Any]]) -> List[risk_engine.Tx]:
    return risk_engine.normalize(rows)


def _display_name_for(party: str, txs: List[risk_engine.Tx]) -> str:
    """Pick a stable, prefer-named label for a party id.

    Reuses the same prefer-name rule the existing risk.py uses, but
    materialised here because the function in risk.py is private.
    """
    for t in txs:
        if t.account_id == party and t.subject_name:
            return t.subject_name
        if t.counterparty == party and t.counterparty_name:
            return t.counterparty_name
    return party


def _combined_name_similarity(a: str, b: str) -> float:
    """Token-set + 3-gram blend; same building blocks as sanctions.py.

    We don't reuse `sanctions.screen` because it scores against the
    *watchlist*, not arbitrary pairs. The blend math is identical:
    similarity = 0.55·token_set + 0.30·3gram + 0.15·containment.
    """
    a_norm = sanctions_engine._normalize(a)
    b_norm = sanctions_engine._normalize(b)
    if not a_norm or not b_norm:
        return 0.0
    a_tok = set(sanctions_engine._tokens(a))
    b_tok = set(sanctions_engine._tokens(b))
    if len(a_tok) < NAME_MIN_TOKENS and len(b_tok) < NAME_MIN_TOKENS:
        # both single-token names — require an exact normalised match
        return 1.0 if a_norm == b_norm else 0.0
    token = sanctions_engine._token_set_ratio(a_tok, b_tok)
    gram = sanctions_engine._jaccard(
        sanctions_engine._ngrams(a),
        sanctions_engine._ngrams(b),
    )
    contain = sanctions_engine._containment(a_norm, b_norm)
    return (
        sanctions_engine.W_TOKEN_SET * token
        + sanctions_engine.W_NGRAM * gram
        + sanctions_engine.W_CONTAIN * contain
    )


def _stable_seed(s: str) -> float:
    """Deterministic [0, 1) seed from a string, for layout init."""
    h = hashlib.sha256(s.encode("utf-8")).digest()
    return int.from_bytes(h[:8], "big") / 2**64


# ---------------------------------------------------------------------------
# Entity resolution
# ---------------------------------------------------------------------------


@dataclass
class Entity:
    id: str                 # stable id derived from the lowest-sorted member
    members: List[str]      # account / counterparty ids in this cluster
    display_name: str
    is_aggregate: bool
    risk_score: float = 0.0  # max of any contained account's risk_score
    band: str = "low"
    sanctioned: bool = False
    flags: List[str] = field(default_factory=list)
    inbound_total: float = 0.0
    outbound_total: float = 0.0
    member_count: int = 0
    network_risk: float = 0.0   # after propagation, in [0, 100]
    network_delta: float = 0.0  # network_risk - risk_score
    x: float = 0.0              # layout coord, virtual canvas
    y: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "members": list(self.members),
            "display_name": self.display_name,
            "is_aggregate": self.is_aggregate,
            "risk_score": round(self.risk_score, 1),
            "network_risk": round(self.network_risk, 1),
            "network_delta": round(self.network_delta, 1),
            "band": self.band,
            "sanctioned": self.sanctioned,
            "flags": list(self.flags),
            "inbound_total": round(self.inbound_total, 2),
            "outbound_total": round(self.outbound_total, 2),
            "member_count": self.member_count,
            "x": round(self.x, 2),
            "y": round(self.y, 2),
        }


def resolve_entities(
    txs: List[risk_engine.Tx],
    *,
    name_tau: float = NAME_TAU,
    counterparty_tau: float = COUNTERPARTY_TAU,
) -> Tuple[Dict[str, str], Dict[str, List[str]]]:
    """Compute entity clusters from a transaction list.

    Returns
    -------
    party_to_cluster : dict
        Maps every party id to its cluster id (the canonical member,
        lexicographically smallest in the cluster — deterministic).
    cluster_members : dict
        Maps each cluster id to its sorted member list.
    """
    parties: Set[str] = set()
    name_for: Dict[str, str] = {}
    counterparties_of: Dict[str, Set[str]] = defaultdict(set)
    for t in txs:
        parties.add(t.account_id)
        parties.add(t.counterparty)
        if t.subject_name:
            name_for.setdefault(t.account_id, t.subject_name)
        if t.counterparty_name:
            name_for.setdefault(t.counterparty, t.counterparty_name)
        counterparties_of[t.account_id].add(t.counterparty)
        counterparties_of[t.counterparty].add(t.account_id)

    parties_sorted = sorted(parties)
    uf = _UF(parties_sorted)

    # Pass 1 — name-based merges. O(N²) over named parties only, which is
    # fine because in demo + production datasets the named-party share is
    # small (most counterparties are bare ids).
    named = [p for p in parties_sorted if name_for.get(p)]
    for i in range(len(named)):
        for j in range(i + 1, len(named)):
            sim = _combined_name_similarity(name_for[named[i]], name_for[named[j]])
            if sim >= name_tau:
                uf.union(named[i], named[j])

    # Pass 2 — behavioural merges. Two parties whose counterparty sets
    # overlap heavily are likely the same hand. We require both sets to
    # have at least 3 members so a single shared counterparty doesn't
    # collapse the graph.
    candidates = [
        p for p in parties_sorted if len(counterparties_of[p]) >= 3
    ]
    for i in range(len(candidates)):
        ci = counterparties_of[candidates[i]] - {candidates[i]}
        for j in range(i + 1, len(candidates)):
            cj = counterparties_of[candidates[j]] - {candidates[j]}
            if not ci or not cj:
                continue
            inter = len(ci & cj)
            union = len(ci | cj)
            if union and inter / union >= counterparty_tau and inter >= 3:
                uf.union(candidates[i], candidates[j])

    grouped = uf.groups()
    party_to_cluster: Dict[str, str] = {}
    cluster_members: Dict[str, List[str]] = {}
    for _, members in grouped.items():
        members_sorted = sorted(members)
        cid = members_sorted[0]
        cluster_members[cid] = members_sorted
        for m in members_sorted:
            party_to_cluster[m] = cid
    return party_to_cluster, cluster_members


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------


@dataclass
class Edge:
    src: str
    dst: str
    amount_total: float
    tx_count: int
    last_ts: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "src": self.src,
            "dst": self.dst,
            "amount": round(self.amount_total, 2),
            "tx_count": self.tx_count,
            "last_ts": self.last_ts,
        }


def _build_entities(
    score_resp: Dict[str, Any],
    txs: List[risk_engine.Tx],
    party_to_cluster: Dict[str, str],
    cluster_members: Dict[str, List[str]],
) -> Dict[str, Entity]:
    """Materialise an Entity per cluster, attaching score / flow totals."""
    by_acct: Dict[str, Dict[str, Any]] = {
        a["account_id"]: a for a in score_resp.get("accounts", [])
    }
    entities: Dict[str, Entity] = {}
    for cid, members in cluster_members.items():
        is_agg = len(members) > 1
        # Risk score for the cluster = max of any contained account.
        # (Sum would double-count behaviour we've explicitly resolved as
        # one entity.)
        max_risk = 0.0
        any_sanction = False
        flag_set: Set[str] = set()
        for m in members:
            rep = by_acct.get(m)
            if not rep:
                continue
            if rep["risk_score"] > max_risk:
                max_risk = rep["risk_score"]
            if rep.get("sanctions_hits"):
                any_sanction = True
                flag_set.add("sanctions")
            for f in rep.get("factors", []):
                if f.get("points", 0) > 0:
                    flag_set.add(f["name"])
        # Flow totals — aggregate over members.
        inbound = sum(
            t.amount for t in txs if party_to_cluster.get(t.counterparty) == cid
            and party_to_cluster.get(t.account_id) != cid  # exclude intra-cluster
        )
        outbound = sum(
            t.amount for t in txs if party_to_cluster.get(t.account_id) == cid
            and party_to_cluster.get(t.counterparty) != cid
        )
        display = _display_name_for(members[0], txs)
        if is_agg and display == members[0]:
            display = f"{members[0]} + {len(members) - 1}"
        ent = Entity(
            id=cid,
            members=members,
            display_name=display,
            is_aggregate=is_agg,
            risk_score=max_risk,
            band=risk_engine._band(max_risk),
            sanctioned=any_sanction,
            flags=sorted(flag_set),
            inbound_total=inbound,
            outbound_total=outbound,
            member_count=len(members),
        )
        entities[cid] = ent
    return entities


def _build_edges(
    txs: List[risk_engine.Tx],
    party_to_cluster: Dict[str, str],
) -> List[Edge]:
    bucket: Dict[Tuple[str, str], Edge] = {}
    for t in txs:
        s = party_to_cluster[t.account_id]
        d = party_to_cluster[t.counterparty]
        if s == d:
            continue  # ignore self-loops after entity resolution
        key = (s, d)
        ts = t.timestamp.isoformat()
        cur = bucket.get(key)
        if cur is None:
            bucket[key] = Edge(s, d, t.amount, 1, ts)
        else:
            cur.amount_total += t.amount
            cur.tx_count += 1
            if ts > cur.last_ts:
                cur.last_ts = ts
    edges = list(bucket.values())
    # Sort by amount desc so the truncation cap retains the most-significant.
    edges.sort(key=lambda e: e.amount_total, reverse=True)
    return edges


def _truncate(
    entities: Dict[str, Entity],
    edges: List[Edge],
) -> Tuple[Dict[str, Entity], List[Edge]]:
    """Cap to MAX_NODES + MAX_EDGES to keep the UI lively even on big inputs.

    Selection is a weighted ranking: top by risk_score primarily, then by
    activity (inbound + outbound). Sanctioned entities are pinned.
    """
    if len(entities) <= MAX_NODES and len(edges) <= MAX_EDGES:
        return entities, edges
    ranked = sorted(
        entities.values(),
        key=lambda e: (
            -1 if e.sanctioned else 0,
            -e.risk_score,
            -(e.inbound_total + e.outbound_total),
        ),
    )
    keep_ids = {e.id for e in ranked[:MAX_NODES]}
    kept_entities = {k: v for k, v in entities.items() if k in keep_ids}
    kept_edges = [e for e in edges if e.src in keep_ids and e.dst in keep_ids][:MAX_EDGES]
    return kept_entities, kept_edges


# ---------------------------------------------------------------------------
# Risk propagation
# ---------------------------------------------------------------------------


def propagate_risk(
    entities: Dict[str, Entity],
    edges: List[Edge],
    *,
    alpha: float = PR_ALPHA,
    max_iter: int = PR_MAX_ITER,
    tol: float = PR_TOL,
) -> Dict[str, float]:
    """PageRank-style biased iteration.

    Math
    ----
    Let s be the L1-normalised seed-risk vector (s_i = entity.risk_score / Σ).
    Let W be the row-stochastic money-flow adjacency: W[i, j] = amount(i→j) /
    Σ_k amount(i→k).
    Then we iterate r ← (1 − α)·s + α · Wᵀ · r until ‖Δ‖₁ < tol.

    The fixed point is a left eigenvector of (1 − α) s ⊕ α Wᵀ — equivalent
    to a personalised PageRank rooted at the seed. We return a 0..100
    score: `final = risk_score * 0.55 + 100 * (r̂ / max(r̂)) * 0.45`.
    The 55/45 blend keeps the per-account score visible while letting
    the network signal lift "clean by themselves but suspicious by company"
    nodes — exactly the inversion the feature is meant to expose.
    """
    if not entities:
        return {}
    ids = sorted(entities.keys())
    idx = {nid: i for i, nid in enumerate(ids)}
    n = len(ids)

    # Seed vector. If everyone is clean, fall back to uniform so the
    # propagation has *something* to spread.
    seed = [entities[nid].risk_score for nid in ids]
    if sum(seed) <= 0:
        seed = [1.0] * n
    s_sum = sum(seed)
    s = [v / s_sum for v in seed]

    # Row-stochastic adjacency from money flow. Dangling nodes (no outflow)
    # teleport to the seed each iteration (standard PageRank dead-end fix).
    out_w: List[Dict[int, float]] = [dict() for _ in range(n)]
    row_sum = [0.0] * n
    for e in edges:
        si, di = idx[e.src], idx[e.dst]
        w = max(0.0, e.amount_total)
        out_w[si][di] = out_w[si].get(di, 0.0) + w
        row_sum[si] += w
    for i in range(n):
        if row_sum[i] > 0:
            inv = 1.0 / row_sum[i]
            for j in out_w[i]:
                out_w[i][j] *= inv

    r = list(s)
    for _ in range(max_iter):
        # nxt = α · Wᵀ · r + (1 − α) · s + α · (sum_of_dangling_r) · s
        nxt = [0.0] * n
        dangle = 0.0
        for i in range(n):
            if row_sum[i] == 0:
                dangle += r[i]
                continue
            for j, w in out_w[i].items():
                nxt[j] += alpha * w * r[i]
        teleport = (1.0 - alpha) + alpha * dangle
        for j in range(n):
            nxt[j] += teleport * s[j]
        # Normalise to keep the sum at 1 (cancels rounding drift).
        z = sum(nxt) or 1.0
        nxt = [v / z for v in nxt]
        delta = sum(abs(nxt[i] - r[i]) for i in range(n))
        r = nxt
        if delta < tol:
            break

    rmax = max(r) or 1.0
    out: Dict[str, float] = {}
    for i, nid in enumerate(ids):
        propagated = 100.0 * (r[i] / rmax)
        blended = 0.55 * entities[nid].risk_score + 0.45 * propagated
        out[nid] = max(0.0, min(100.0, blended))
    return out


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------


def _layout(entities: Dict[str, Entity], edges: List[Edge]) -> None:
    """Deterministic Fruchterman-Reingold variant.

    Init from a hash-seeded golden-ratio spiral so layouts are stable
    *and* visually pleasant before the first force step runs. Mutates
    `entities[i].x / .y` in place.
    """
    n = len(entities)
    if n == 0:
        return
    ids = sorted(entities.keys())
    centre = LAYOUT_SIZE / 2

    # Spiral init
    golden = math.pi * (3.0 - math.sqrt(5.0))
    for i, nid in enumerate(ids):
        # rotate seed by SHA hash so reproducible but distinct per dataset
        jitter = _stable_seed(nid) * 0.5
        radius = math.sqrt((i + 0.5) / n) * (LAYOUT_SIZE * 0.42)
        theta = i * golden + jitter * math.pi * 2
        entities[nid].x = centre + radius * math.cos(theta)
        entities[nid].y = centre + radius * math.sin(theta)

    if n == 1:
        return

    # Build adj for attraction
    pairs: List[Tuple[str, str, float]] = []
    max_w = 1.0
    for e in edges:
        if e.src in entities and e.dst in entities:
            pairs.append((e.src, e.dst, e.amount_total))
            if e.amount_total > max_w:
                max_w = e.amount_total

    k = LAYOUT_REPULSE  # already squared in repulsion formula
    temp = LAYOUT_SIZE / 8.0

    for _ in range(LAYOUT_ITER):
        disp: Dict[str, Tuple[float, float]] = {nid: (0.0, 0.0) for nid in ids}
        # Repulsion (O(n²); cap MAX_NODES keeps this trivial).
        for i, a in enumerate(ids):
            ax, ay = entities[a].x, entities[a].y
            dax, day = disp[a]
            for j in range(i + 1, n):
                b = ids[j]
                bx, by = entities[b].x, entities[b].y
                dx = ax - bx
                dy = ay - by
                d2 = dx * dx + dy * dy
                if d2 < 1.0:
                    d2 = 1.0
                f = k / d2
                dax += dx * f
                day += dy * f
                disp[b] = (disp[b][0] - dx * f, disp[b][1] - dy * f)
            disp[a] = (dax, day)

        # Attraction along weighted edges
        for u, v, w in pairs:
            ax, ay = entities[u].x, entities[u].y
            bx, by = entities[v].x, entities[v].y
            dx = ax - bx
            dy = ay - by
            d = math.sqrt(dx * dx + dy * dy) or 1.0
            f = LAYOUT_ATTRACT * (d * d) / k * (0.4 + 0.6 * (w / max_w))
            ux, uy = disp[u]
            vx, vy = disp[v]
            disp[u] = (ux - dx / d * f, uy - dy / d * f)
            disp[v] = (vx + dx / d * f, vy + dy / d * f)

        # Gravity toward centre to keep the whole graph in frame.
        for nid in ids:
            ex, ey = entities[nid].x, entities[nid].y
            ux, uy = disp[nid]
            disp[nid] = (ux + (centre - ex) * LAYOUT_GRAVITY,
                         uy + (centre - ey) * LAYOUT_GRAVITY)

        # Apply with cooling.
        for nid in ids:
            ux, uy = disp[nid]
            mag = math.sqrt(ux * ux + uy * uy) or 1.0
            step = min(mag, temp)
            entities[nid].x += ux / mag * step
            entities[nid].y += uy / mag * step
            # Clamp to canvas with a small margin
            entities[nid].x = max(40, min(LAYOUT_SIZE - 40, entities[nid].x))
            entities[nid].y = max(40, min(LAYOUT_SIZE - 40, entities[nid].y))
        temp *= LAYOUT_COOL


# ---------------------------------------------------------------------------
# Public API — analyse
# ---------------------------------------------------------------------------


def _score_or_passthrough(
    rows: List[Dict[str, Any]],
    score_response: Optional[Dict[str, Any]],
    weights: Optional[Dict[str, float]],
    sanctions_threshold: Optional[float],
) -> Dict[str, Any]:
    """If the caller already has a /aml/score response, accept it.
    Otherwise score afresh — handy when the frontend wants to call
    /aml/network/analyze on raw CSV without a separate scoring step.
    """
    if score_response and score_response.get("accounts"):
        return score_response
    threshold = (
        sanctions_threshold
        if sanctions_threshold is not None
        else risk_engine.SANCTIONS_HIT_THRESHOLD
    )
    return risk_engine.score_accounts(
        rows,
        weights_override=weights,
        sanctions_threshold=threshold,
    )


def analyze(
    rows: List[Dict[str, Any]],
    *,
    score_response: Optional[Dict[str, Any]] = None,
    weights: Optional[Dict[str, float]] = None,
    sanctions_threshold: Optional[float] = None,
    name_tau: float = NAME_TAU,
    counterparty_tau: float = COUNTERPARTY_TAU,
) -> Dict[str, Any]:
    """End-to-end network analysis: resolve → graph → propagate → layout.

    Returns
    -------
    A dict shaped for the /network frontend:

        {
          entities: [...],            # 0..MAX_NODES, pre-laid-out
          edges: [...],               # 0..MAX_EDGES
          summary: {
              total_parties, total_clusters, multi_member_clusters,
              avg_network_lift, top_lift_entity_id,
              top_central_entity_id, density, components
          },
          score_response: { ... }     # echoes the per-account score
        }
    """
    if not rows:
        return {
            "entities": [],
            "edges": [],
            "summary": {
                "total_parties": 0, "total_clusters": 0,
                "multi_member_clusters": 0, "avg_network_lift": 0.0,
                "top_lift_entity_id": None, "top_central_entity_id": None,
                "density": 0.0, "components": 0,
            },
            "score_response": _score_or_passthrough(rows, score_response, weights, sanctions_threshold),
        }
    score_resp = _score_or_passthrough(rows, score_response, weights, sanctions_threshold)
    txs = _txs_from_rows(rows)
    p2c, members = resolve_entities(txs, name_tau=name_tau, counterparty_tau=counterparty_tau)
    entities = _build_entities(score_resp, txs, p2c, members)
    edges = _build_edges(txs, p2c)
    entities, edges = _truncate(entities, edges)

    # Propagation, then write back into the entity records.
    propagated = propagate_risk(entities, edges)
    for nid, val in propagated.items():
        ent = entities[nid]
        ent.network_risk = val
        ent.network_delta = val - ent.risk_score
        ent.band = risk_engine._band(val)

    _layout(entities, edges)

    # Summary stats
    n = len(entities)
    multi = sum(1 for e in entities.values() if e.is_aggregate)
    avg_lift = (
        sum(e.network_delta for e in entities.values()) / n if n else 0.0
    )
    top_lift_eid: Optional[str] = None
    top_lift = -1e9
    for e in entities.values():
        if e.network_delta > top_lift:
            top_lift = e.network_delta
            top_lift_eid = e.id
    top_central_eid: Optional[str] = None
    top_central = -1.0
    for e in entities.values():
        score = e.network_risk + (e.inbound_total + e.outbound_total) / 1e7
        if score > top_central:
            top_central = score
            top_central_eid = e.id
    density = 0.0 if n < 2 else len(edges) / (n * (n - 1))

    return {
        "entities": [e.to_dict() for e in sorted(
            entities.values(),
            key=lambda x: (-x.network_risk, -x.risk_score),
        )],
        "edges": [e.to_dict() for e in edges],
        "summary": {
            "total_parties": sum(len(m) for m in members.values()),
            "total_clusters": len(members),
            "multi_member_clusters": multi,
            "avg_network_lift": round(avg_lift, 2),
            "top_lift_entity_id": top_lift_eid,
            "top_central_entity_id": top_central_eid,
            "density": round(density, 4),
            "components": _component_count(entities, edges),
        },
        "score_response": score_resp,
        "params": {
            "name_tau": name_tau,
            "counterparty_tau": counterparty_tau,
            "pr_alpha": PR_ALPHA,
            "layout_size": LAYOUT_SIZE,
        },
        "engine": "titan-network/0.1.0",
    }


def _component_count(entities: Dict[str, Entity], edges: List[Edge]) -> int:
    """Weak connected components via Union-Find on the truncated graph."""
    if not entities:
        return 0
    uf = _UF(entities.keys())
    for e in edges:
        if e.src in entities and e.dst in entities:
            uf.union(e.src, e.dst)
    seen: Set[str] = set()
    for nid in entities:
        seen.add(uf.find(nid))
    return len(seen)


# ---------------------------------------------------------------------------
# Counterfactual — ablate entities, rescore, return deltas
# ---------------------------------------------------------------------------


def counterfactual(
    rows: List[Dict[str, Any]],
    ablate_entity_ids: List[str],
    *,
    baseline: Optional[Dict[str, Any]] = None,
    weights: Optional[Dict[str, float]] = None,
    sanctions_threshold: Optional[float] = None,
) -> Dict[str, Any]:
    """Drop every transaction touching any party in `ablate_entity_ids`
    (resolved through the cluster map), rescore from scratch, propagate,
    and return per-entity deltas vs the baseline.

    The baseline can be passed in to avoid redoing the full analyse —
    the frontend can keep the original on hand and just send the ablation.
    """
    base = baseline or analyze(
        rows, weights=weights, sanctions_threshold=sanctions_threshold,
    )
    base_entities = {e["id"]: e for e in base.get("entities", [])}
    # Build a quick reverse map of party → cluster from the baseline so
    # the caller's ablate ids (cluster ids) translate into party ids.
    party_to_cluster: Dict[str, str] = {}
    for e in base.get("entities", []):
        for m in e.get("members", []):
            party_to_cluster[m] = e["id"]
    ablate_parties = {
        p for p, c in party_to_cluster.items() if c in set(ablate_entity_ids)
    }
    kept = [
        r for r in rows
        if r.get("account_id") not in ablate_parties
        and r.get("counterparty") not in ablate_parties
    ]
    after = analyze(
        kept,
        weights=weights,
        sanctions_threshold=sanctions_threshold,
    )

    after_entities = {e["id"]: e for e in after.get("entities", [])}
    deltas: List[Dict[str, Any]] = []
    surviving_ids = set(base_entities.keys()) & set(after_entities.keys())
    for eid in surviving_ids:
        b = base_entities[eid]
        a = after_entities[eid]
        deltas.append({
            "entity_id": eid,
            "display_name": b["display_name"],
            "risk_before": b["risk_score"],
            "risk_after": a["risk_score"],
            "risk_delta": round(a["risk_score"] - b["risk_score"], 2),
            "network_before": b["network_risk"],
            "network_after": a["network_risk"],
            "network_delta": round(a["network_risk"] - b["network_risk"], 2),
        })
    deltas.sort(key=lambda d: d["network_delta"])  # biggest drops first

    network_avg_before = (
        sum(e["network_risk"] for e in base_entities.values()) / len(base_entities)
        if base_entities else 0.0
    )
    network_avg_after = (
        sum(e["network_risk"] for e in after_entities.values()) / len(after_entities)
        if after_entities else 0.0
    )
    return {
        "ablated": sorted(ablate_entity_ids),
        "removed_parties": sorted(ablate_parties),
        "txs_removed": len(rows) - len(kept),
        "deltas": deltas,
        "summary": {
            "network_avg_before": round(network_avg_before, 2),
            "network_avg_after": round(network_avg_after, 2),
            "network_avg_change": round(network_avg_after - network_avg_before, 2),
            "alerted_before": sum(
                1 for e in base_entities.values() if e["network_risk"] >= 60
            ),
            "alerted_after": sum(
                1 for e in after_entities.values() if e["network_risk"] >= 60
            ),
        },
        "before": base["summary"],
        "after": after["summary"],
        "engine": "titan-network/0.1.0",
    }


# ---------------------------------------------------------------------------
# Attribution — per-account leave-one-counterparty-out
# ---------------------------------------------------------------------------


def attribution(
    rows: List[Dict[str, Any]],
    account_id: str,
    *,
    weights: Optional[Dict[str, float]] = None,
    sanctions_threshold: Optional[float] = None,
    max_report: int = ATTRIB_MAX_REPORT,
) -> Dict[str, Any]:
    """For one account, rank which counterparties contribute the most lift
    to its risk score. We compute the baseline once, then for each
    counterparty drop *all* transactions between the account and that
    counterparty and rescore. The drop in `risk_score` is the lift.

    This is the simplest possible SHAP-style explanation: marginal
    contribution under a leave-one-out coalition. No sampling, no
    approximation, fully auditable.
    """
    baseline = _score_or_passthrough(rows, None, weights, sanctions_threshold)
    base_account = next(
        (a for a in baseline.get("accounts", []) if a["account_id"] == account_id),
        None,
    )
    if not base_account:
        return {
            "account_id": account_id,
            "baseline_score": 0.0,
            "counterparties": [],
            "note": "account not found in baseline",
        }
    baseline_score = base_account["risk_score"]
    related = [
        r for r in rows
        if r.get("account_id") == account_id or r.get("counterparty") == account_id
    ]
    counterparties: Set[str] = {
        (r["counterparty"] if r["account_id"] == account_id else r["account_id"])
        for r in related
    }
    contributions: List[Dict[str, Any]] = []
    for cp in counterparties:
        kept = [
            r for r in rows
            if not (
                (r.get("account_id") == account_id and r.get("counterparty") == cp)
                or (r.get("account_id") == cp and r.get("counterparty") == account_id)
            )
        ]
        cf_resp = risk_engine.score_accounts(
            kept,
            weights_override=weights,
            sanctions_threshold=(
                sanctions_threshold
                if sanctions_threshold is not None
                else risk_engine.SANCTIONS_HIT_THRESHOLD
            ),
        )
        cf_acct = next(
            (a for a in cf_resp.get("accounts", []) if a["account_id"] == account_id),
            None,
        )
        cf_score = cf_acct["risk_score"] if cf_acct else 0.0
        # How many txs we just removed, what was the total value.
        removed = [
            r for r in related
            if (r.get("account_id") == account_id and r.get("counterparty") == cp)
            or (r.get("account_id") == cp and r.get("counterparty") == account_id)
        ]
        contributions.append({
            "counterparty": cp,
            "tx_count": len(removed),
            "amount_total": round(sum(float(r.get("amount", 0) or 0) for r in removed), 2),
            "score_with": baseline_score,
            "score_without": cf_score,
            "lift": round(baseline_score - cf_score, 2),
        })
    contributions.sort(key=lambda c: c["lift"], reverse=True)
    return {
        "account_id": account_id,
        "display_name": base_account.get("display_name") or account_id,
        "baseline_score": baseline_score,
        "baseline_band": base_account["band"],
        "counterparties": contributions[:max_report],
        "engine": "titan-network/0.1.0",
    }


# ---------------------------------------------------------------------------
# Surface-level rules dump (mirrors risk.get_rules)
# ---------------------------------------------------------------------------


def get_rules() -> Dict[str, Any]:
    return {
        "version": "titan-network/0.1.0",
        "entity_resolution": {
            "name_tau": NAME_TAU,
            "counterparty_tau": COUNTERPARTY_TAU,
            "name_min_tokens": NAME_MIN_TOKENS,
        },
        "propagation": {
            "alpha": PR_ALPHA,
            "max_iter": PR_MAX_ITER,
            "tol": PR_TOL,
            "blend": {"per_account": 0.55, "network": 0.45},
        },
        "layout": {
            "size": LAYOUT_SIZE,
            "iterations": LAYOUT_ITER,
        },
        "caps": {"max_nodes": MAX_NODES, "max_edges": MAX_EDGES},
    }
