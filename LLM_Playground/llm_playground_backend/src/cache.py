"""Cache — Semantic Response Cache Studio (Day 88).

Every prior LLM_Playground surface answered *quality* (Arena, Rubrics, Judge,
Suites), *robustness* (Adversary, Drift, Surgeon), *cost/model pick*
(Frontier), *routing* (Relay), or *guarding* (Sentinel). None of them ask the
one question every production LLM deployment gets asked in the second week:
**how much of this traffic could a cache answer for free?**

Production LLM apps show 25-70% semantic repetition — the same intent phrased
differently. A semantic response cache maps *paraphrases* to the same cached
answer, dropping cost + latency by a large factor. But the design is a
knife-edge: too loose and stale/off-topic answers leak; too tight and the
cache is empty.

Cache is the deterministic studio for tuning that knife-edge.

Given a workload (a stream of prompts) and a policy shape (similarity
threshold, capacity, TTL, eviction policy), Cache simulates the cache
against the workload and reports:

* hit-rate, escape-rate, evictions
* cost saved vs. always-miss baseline ($/mo at user-supplied volume)
* p50 / p95 latency delta (hit ~ 2 ms, miss ~ 500 ms)
* quality-risk (% of hits whose similarity was below the "safe" bar of 0.90)
* per-cluster hit distribution (which intents dominate savings)

It sweeps the full **4 policies × 8 thresholds** grid in one call, ships a
**threshold sensitivity curve** (hit-rate + quality-risk), and returns three
shippable recommendations:

  - **conservative**  — highest quality preservation (high threshold, LFU)
  - **balanced**      — highest savings under a quality-risk ceiling
  - **aggressive**    — highest savings regardless of quality risk

Semantic clustering (single-link at the chosen threshold) surfaces which
prompt families dominate the workload, complete with cluster representatives
and per-cluster potential savings.

The engine is stateless — no DB. Every response is a pure function of
(workload, config), which means the demo lights up on first page load
without any API credentials and stays byte-identical across refreshes.

Public surface: ``defaults``, ``list_policies``, ``list_workloads``,
``load_workload``, ``simulate_cache``, ``sweep_thresholds``,
``sweep_policies``, ``recommend_configs``, ``cluster_workload``,
``compile_cache``, ``cache_markdown``, ``seed_demo``.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


ENGINE_VERSION = "cache/1.0.0"

# ─── Embedding config ───────────────────────────────────────────────────────
EMBED_DIM = 128
# Bag-of-tokens hashing embedding: for each token, hash it into 1 of EMBED_DIM
# buckets and add 1 (with a small +0.5 to bigrams so paraphrases with the same
# unigrams but different word order still separate a little). L2-normalized.
_STOPWORDS = frozenset("""
a an the of and or but if while when whom whose that this those these to for
from in on at by with as is are was were be been being do does did doing
have has had having i you he she it we they me him her us them my your his
their our its who what why how which where there here so than then just
can could should would may might will shall not no yes about into over under
between among against within without through
""".split())
_TOKEN_RE = re.compile(r"[a-zA-Z0-9']+")

# ─── Cache config defaults ──────────────────────────────────────────────────
DEFAULT_THRESHOLD = 0.88
DEFAULT_CAPACITY = 512
DEFAULT_TTL_SECONDS = 60 * 60 * 24 * 7  # one week
DEFAULT_POLICY = "lru"
DEFAULT_MONTHLY_REQUESTS = 100_000

# Costs of a miss vs a hit (per-call). Values reflect a mid-tier chat model
# (GPT-4o-mini class) with ~250 tokens out at $0.60 / 1M output.
DEFAULT_MISS_COST_USD = 0.0025
DEFAULT_HIT_COST_USD = 0.0000075  # tiny — just an embedding lookup + I/O
DEFAULT_MISS_LATENCY_MS = 620.0
DEFAULT_HIT_LATENCY_MS = 4.0

# A hit is *quality-safe* if similarity >= this bar; hits below count as
# "quality-risk" — cached answer might miss intent nuance. The bar is
# calibrated for the hashing embedder; production embedders (bge-small,
# text-embedding-3-small) can safely push this up toward 0.92.
SAFE_SIMILARITY_BAR = 0.85

# Threshold sensitivity curve — 8 canonical points that cover the interesting
# regime. Below 0.6 all hits are hallucinated; above 0.98 the cache never
# fires.
THRESHOLD_SWEEP = (0.65, 0.75, 0.82, 0.86, 0.88, 0.90, 0.93, 0.96)

# Policy catalog.
POLICY_ORDER = ("lru", "lfu", "fifo", "sdiv")
POLICY_META: Dict[str, Dict[str, Any]] = {
    "lru": {
        "id": "lru",
        "name": "LRU — Least Recently Used",
        "hue": "sky",
        "description": (
            "Evict the entry whose last hit is oldest. Standard for chat-like "
            "workloads where a recent intent will keep recurring."
        ),
        "strengths": ["recency-biased traffic", "session workloads"],
        "weaknesses": ["one-shot bursts flush out popular entries"],
    },
    "lfu": {
        "id": "lfu",
        "name": "LFU — Least Frequently Used",
        "hue": "emerald",
        "description": (
            "Evict the entry with the fewest total hits. Best when the "
            "workload has a stable head — a small set of intents dominates."
        ),
        "strengths": ["long-tail with a stable head", "FAQ / knowledge bases"],
        "weaknesses": ["new hot intents are slow to displace stale ones"],
    },
    "fifo": {
        "id": "fifo",
        "name": "FIFO — First In, First Out",
        "hue": "amber",
        "description": (
            "Evict the entry inserted longest ago. Simplest possible policy, "
            "predictable but wastes cache on cold entries."
        ),
        "strengths": ["predictable retention", "zero bookkeeping"],
        "weaknesses": ["ignores popularity entirely"],
    },
    "sdiv": {
        "id": "sdiv",
        "name": "SDIV — Semantic Diversity",
        "hue": "fuchsia",
        "description": (
            "Evict the entry most similar to others (highest average cosine "
            "distance to peers). Preserves semantic coverage — favours a "
            "broad map over a deep count."
        ),
        "strengths": ["diverse workloads", "small capacities"],
        "weaknesses": ["compute-heavier per eviction (O(n))"],
    },
}


# ─── Text preprocessing + hashing embedding ─────────────────────────────────
def _normalize(text: str) -> str:
    """Unicode NFKC-fold, lowercase, collapse whitespace, strip punctuation."""
    if not text:
        return ""
    t = unicodedata.normalize("NFKC", text).lower()
    return re.sub(r"\s+", " ", t).strip()


def _tokens(text: str) -> List[str]:
    """Yield tokens (unigrams) with stopwords / very-short tokens removed."""
    normalized = _normalize(text)
    out: List[str] = []
    for tok in _TOKEN_RE.findall(normalized):
        if len(tok) < 2:
            continue
        if tok in _STOPWORDS:
            continue
        out.append(tok)
    return out


def _bucket(token: str) -> int:
    """Hash a token into 1 of EMBED_DIM buckets (SHA-1, deterministic)."""
    h = hashlib.sha1(token.encode("utf-8")).digest()
    return int.from_bytes(h[:4], "big") % EMBED_DIM


def embed(text: str) -> Tuple[float, ...]:
    """Hashing bag-of-tokens embedding with bigram boost, L2 normalized.

    Fully deterministic and offline — no external model required. The point is
    to give the simulator a plausible similarity space to reason about, not to
    replace a real embedding model.
    """
    vec = [0.0] * EMBED_DIM
    toks = _tokens(text)
    if not toks:
        return tuple(vec)
    for tok in toks:
        vec[_bucket(tok)] += 1.0
    # Bigram boost — helps paraphrases with same unigrams but different order.
    for a, b in zip(toks, toks[1:]):
        vec[_bucket(a + "_" + b)] += 0.55
    norm = math.sqrt(sum(v * v for v in vec))
    if norm == 0:
        return tuple(vec)
    return tuple(v / norm for v in vec)


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    """Cosine similarity in [0, 1] (vectors are pre-normalised)."""
    if not a or not b:
        return 0.0
    return max(0.0, min(1.0, sum(x * y for x, y in zip(a, b))))


# ─── Cache simulator core ───────────────────────────────────────────────────
class _CacheEntry:
    __slots__ = (
        "key_id",
        "prompt",
        "vec",
        "insert_order",
        "last_hit_step",
        "hit_count",
        "cost_per_miss",
        "latency_per_miss",
    )

    def __init__(
        self,
        key_id: int,
        prompt: str,
        vec: Tuple[float, ...],
        insert_order: int,
        last_hit_step: int,
        cost_per_miss: float,
        latency_per_miss: float,
    ) -> None:
        self.key_id = key_id
        self.prompt = prompt
        self.vec = vec
        self.insert_order = insert_order
        self.last_hit_step = last_hit_step
        self.hit_count = 0
        self.cost_per_miss = cost_per_miss
        self.latency_per_miss = latency_per_miss


def _pick_evict_lru(entries: List[_CacheEntry]) -> int:
    """Index of entry with smallest last_hit_step (oldest hit)."""
    return min(range(len(entries)), key=lambda i: entries[i].last_hit_step)


def _pick_evict_lfu(entries: List[_CacheEntry]) -> int:
    """Index of entry with smallest hit_count; ties break by oldest insertion."""
    return min(
        range(len(entries)),
        key=lambda i: (entries[i].hit_count, entries[i].insert_order),
    )


def _pick_evict_fifo(entries: List[_CacheEntry]) -> int:
    return min(range(len(entries)), key=lambda i: entries[i].insert_order)


def _pick_evict_sdiv(entries: List[_CacheEntry]) -> int:
    """Evict the entry with highest average cosine similarity to peers.

    That's the entry contributing least to *semantic diversity*: another
    cached entry is close enough to serve the same intent.
    """
    if len(entries) <= 1:
        return 0
    best_idx = 0
    best_score = -1.0
    n = len(entries)
    for i in range(n):
        total = 0.0
        for j in range(n):
            if i == j:
                continue
            total += cosine(entries[i].vec, entries[j].vec)
        avg = total / (n - 1)
        if avg > best_score:
            best_score = avg
            best_idx = i
    return best_idx


_EVICT_FUNCS = {
    "lru": _pick_evict_lru,
    "lfu": _pick_evict_lfu,
    "fifo": _pick_evict_fifo,
    "sdiv": _pick_evict_sdiv,
}


def _percentile(values: Sequence[float], q: float) -> float:
    if not values:
        return 0.0
    xs = sorted(values)
    if len(xs) == 1:
        return xs[0]
    pos = q * (len(xs) - 1)
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return xs[lo]
    frac = pos - lo
    return xs[lo] * (1 - frac) + xs[hi] * frac


def simulate_cache(
    workload: Sequence[Dict[str, Any]],
    threshold: float = DEFAULT_THRESHOLD,
    capacity: int = DEFAULT_CAPACITY,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
    policy: str = DEFAULT_POLICY,
    miss_cost_usd: float = DEFAULT_MISS_COST_USD,
    hit_cost_usd: float = DEFAULT_HIT_COST_USD,
    miss_latency_ms: float = DEFAULT_MISS_LATENCY_MS,
    hit_latency_ms: float = DEFAULT_HIT_LATENCY_MS,
) -> Dict[str, Any]:
    """Simulate the cache against a workload and return per-request telemetry.

    A workload item is ``{prompt, timestamp?, intent?}``. Timestamps are
    optional — if absent, requests are treated as evenly spaced 1s apart.
    """
    threshold = max(0.0, min(1.0, float(threshold)))
    capacity = max(1, int(capacity))
    ttl_seconds = max(1, int(ttl_seconds))
    policy = policy if policy in _EVICT_FUNCS else DEFAULT_POLICY
    evict_fn = _EVICT_FUNCS[policy]

    entries: List[_CacheEntry] = []
    trace: List[Dict[str, Any]] = []
    hit_similarities: List[float] = []
    latencies: List[float] = []
    hit_costs: List[float] = []
    miss_costs: List[float] = []
    evictions = 0
    hits = 0
    misses = 0
    quality_risky_hits = 0
    ttl_evictions = 0
    per_intent: Dict[str, Dict[str, int]] = {}

    for step, item in enumerate(workload):
        prompt = str(item.get("prompt") or "")
        if not prompt.strip():
            continue
        intent = str(item.get("intent") or "")
        ts = int(item.get("timestamp", step))

        # Expire TTL-stale entries first.
        if ttl_seconds:
            fresh: List[_CacheEntry] = []
            for e in entries:
                if ts - e.last_hit_step > ttl_seconds:
                    ttl_evictions += 1
                    continue
                fresh.append(e)
            entries = fresh

        vec = embed(prompt)
        best_idx = -1
        best_sim = 0.0
        for i, e in enumerate(entries):
            sim = cosine(vec, e.vec)
            if sim > best_sim:
                best_sim = sim
                best_idx = i

        intent_key = intent or "(untagged)"
        stats = per_intent.setdefault(intent_key, {"hits": 0, "misses": 0, "total": 0})
        stats["total"] += 1

        if best_idx >= 0 and best_sim >= threshold:
            hits += 1
            stats["hits"] += 1
            e = entries[best_idx]
            e.hit_count += 1
            e.last_hit_step = ts
            hit_similarities.append(best_sim)
            hit_costs.append(hit_cost_usd)
            latencies.append(hit_latency_ms)
            if best_sim < SAFE_SIMILARITY_BAR:
                quality_risky_hits += 1
            trace.append({
                "step": step,
                "outcome": "hit",
                "similarity": round(best_sim, 4),
                "matched_prompt": e.prompt[:80],
                "cost_usd": round(hit_cost_usd, 8),
                "latency_ms": round(hit_latency_ms, 2),
                "intent": intent_key,
            })
            continue

        # Miss — insert and evict if needed.
        misses += 1
        stats["misses"] += 1
        latencies.append(miss_latency_ms)
        miss_costs.append(miss_cost_usd)
        entry = _CacheEntry(
            key_id=step,
            prompt=prompt,
            vec=vec,
            insert_order=step,
            last_hit_step=ts,
            cost_per_miss=miss_cost_usd,
            latency_per_miss=miss_latency_ms,
        )
        if len(entries) >= capacity:
            victim = evict_fn(entries)
            entries.pop(victim)
            evictions += 1
        entries.append(entry)
        trace.append({
            "step": step,
            "outcome": "miss",
            "similarity": round(best_sim, 4),
            "cost_usd": round(miss_cost_usd, 8),
            "latency_ms": round(miss_latency_ms, 2),
            "intent": intent_key,
        })

    total = hits + misses
    baseline_cost = total * miss_cost_usd
    baseline_latency_total = total * miss_latency_ms
    actual_cost = sum(hit_costs) + sum(miss_costs)
    actual_latency_total = sum(latencies)

    hit_rate = hits / total if total else 0.0
    savings_pct = 1 - (actual_cost / baseline_cost) if baseline_cost else 0.0
    latency_reduction_pct = (
        1 - (actual_latency_total / baseline_latency_total)
        if baseline_latency_total else 0.0
    )
    quality_risk_pct = quality_risky_hits / hits if hits else 0.0

    top_intents = sorted(
        (
            {
                "intent": key,
                "hits": v["hits"],
                "misses": v["misses"],
                "total": v["total"],
                "hit_rate": round(v["hits"] / v["total"], 4) if v["total"] else 0.0,
            }
            for key, v in per_intent.items()
        ),
        key=lambda r: -r["total"],
    )

    return {
        "engine": ENGINE_VERSION,
        "policy": policy,
        "threshold": round(threshold, 4),
        "capacity": capacity,
        "ttl_seconds": ttl_seconds,
        "totals": {
            "requests": total,
            "hits": hits,
            "misses": misses,
            "evictions": evictions,
            "ttl_evictions": ttl_evictions,
            "quality_risky_hits": quality_risky_hits,
        },
        "rates": {
            "hit_rate": round(hit_rate, 4),
            "miss_rate": round(1 - hit_rate, 4) if total else 0.0,
            "quality_risk_pct": round(quality_risk_pct, 4),
        },
        "cost": {
            "baseline_usd": round(baseline_cost, 6),
            "actual_usd": round(actual_cost, 6),
            "savings_usd": round(baseline_cost - actual_cost, 6),
            "savings_pct": round(savings_pct, 4),
            "cost_per_request_baseline": round(miss_cost_usd, 8),
            "cost_per_request_actual": round(actual_cost / total, 8) if total else 0.0,
        },
        "latency_ms": {
            "avg": round(actual_latency_total / total, 2) if total else 0.0,
            "avg_baseline": round(miss_latency_ms, 2),
            "p50": round(_percentile(latencies, 0.5), 2),
            "p95": round(_percentile(latencies, 0.95), 2),
            "reduction_pct": round(latency_reduction_pct, 4),
        },
        "similarity": {
            "avg_hit": round(sum(hit_similarities) / len(hit_similarities), 4)
            if hit_similarities else 0.0,
            "p50_hit": round(_percentile(hit_similarities, 0.5), 4),
            "p05_hit": round(_percentile(hit_similarities, 0.05), 4),
        },
        "top_intents": top_intents[:16],
        "trace_tail": trace[-24:],
        "final_cache_size": len(entries),
    }


# ─── Sweeps & recommendations ───────────────────────────────────────────────
def sweep_thresholds(
    workload: Sequence[Dict[str, Any]],
    policy: str = DEFAULT_POLICY,
    capacity: int = DEFAULT_CAPACITY,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
    thresholds: Sequence[float] = THRESHOLD_SWEEP,
) -> Dict[str, Any]:
    """Run the simulator at every threshold in ``thresholds`` and return a curve.

    The curve is what you plot to *see* the trade-off between hit-rate and
    quality-risk before you pick a threshold.
    """
    points: List[Dict[str, Any]] = []
    for t in thresholds:
        sim = simulate_cache(
            workload,
            threshold=t,
            capacity=capacity,
            ttl_seconds=ttl_seconds,
            policy=policy,
        )
        points.append({
            "threshold": round(float(t), 4),
            "hit_rate": sim["rates"]["hit_rate"],
            "savings_pct": sim["cost"]["savings_pct"],
            "quality_risk_pct": sim["rates"]["quality_risk_pct"],
            "avg_latency_ms": sim["latency_ms"]["avg"],
            "evictions": sim["totals"]["evictions"],
            "cache_size": sim["final_cache_size"],
        })
    return {
        "engine": ENGINE_VERSION,
        "policy": policy,
        "capacity": capacity,
        "ttl_seconds": ttl_seconds,
        "points": points,
    }


def sweep_policies(
    workload: Sequence[Dict[str, Any]],
    capacity: int = DEFAULT_CAPACITY,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
    thresholds: Sequence[float] = THRESHOLD_SWEEP,
) -> Dict[str, Any]:
    """Run every (policy, threshold) pair — the 4×N decision grid."""
    grid: Dict[str, List[Dict[str, Any]]] = {}
    for policy in POLICY_ORDER:
        pts = sweep_thresholds(
            workload,
            policy=policy,
            capacity=capacity,
            ttl_seconds=ttl_seconds,
            thresholds=thresholds,
        )["points"]
        grid[policy] = pts
    return {
        "engine": ENGINE_VERSION,
        "policies": list(POLICY_ORDER),
        "thresholds": [round(float(t), 4) for t in thresholds],
        "capacity": capacity,
        "ttl_seconds": ttl_seconds,
        "grid": grid,
    }


def _pick_best(
    candidates: List[Dict[str, Any]],
    key_fn,
    filter_fn=None,
) -> Optional[Dict[str, Any]]:
    pool = [c for c in candidates if (filter_fn is None or filter_fn(c))]
    if not pool:
        return None
    return max(pool, key=key_fn)


def recommend_configs(
    workload: Sequence[Dict[str, Any]],
    capacity: int = DEFAULT_CAPACITY,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
    monthly_requests: int = DEFAULT_MONTHLY_REQUESTS,
    quality_risk_ceiling: float = 0.08,
    thresholds: Sequence[float] = THRESHOLD_SWEEP,
    miss_cost_usd: float = DEFAULT_MISS_COST_USD,
    hit_cost_usd: float = DEFAULT_HIT_COST_USD,
) -> Dict[str, Any]:
    """Three canonical picks off the (policy × threshold) grid.

    * **conservative** — highest hit-rate whose quality-risk stays under 3 %,
      biased to LFU (frequency preservation matters most in FAQ-shape).
    * **balanced**     — highest savings under the caller-supplied
      ``quality_risk_ceiling``.
    * **aggressive**   — highest savings regardless of quality risk (SDIV
      diversity-eviction wins here because it maximises cache coverage).
    """
    candidates: List[Dict[str, Any]] = []
    for policy in POLICY_ORDER:
        for t in thresholds:
            sim = simulate_cache(
                workload,
                threshold=t,
                capacity=capacity,
                ttl_seconds=ttl_seconds,
                policy=policy,
                miss_cost_usd=miss_cost_usd,
                hit_cost_usd=hit_cost_usd,
            )
            unit_savings_usd = sim["cost"]["savings_usd"] / max(1, sim["totals"]["requests"])
            monthly_savings = unit_savings_usd * monthly_requests
            monthly_cost = (
                sim["cost"]["cost_per_request_actual"] * monthly_requests
            )
            candidates.append({
                "policy": policy,
                "threshold": round(float(t), 4),
                "hit_rate": sim["rates"]["hit_rate"],
                "savings_pct": sim["cost"]["savings_pct"],
                "quality_risk_pct": sim["rates"]["quality_risk_pct"],
                "avg_latency_ms": sim["latency_ms"]["avg"],
                "monthly_savings_usd": round(monthly_savings, 4),
                "monthly_cost_usd": round(monthly_cost, 4),
                "monthly_baseline_usd": round(
                    miss_cost_usd * monthly_requests, 4
                ),
                "evictions": sim["totals"]["evictions"],
                "cache_size": sim["final_cache_size"],
            })

    conservative = _pick_best(
        candidates,
        key_fn=lambda c: (c["hit_rate"], -c["quality_risk_pct"]),
        filter_fn=lambda c: c["quality_risk_pct"] <= 0.03,
    ) or _pick_best(
        candidates,
        key_fn=lambda c: -c["quality_risk_pct"],
    )
    balanced = _pick_best(
        candidates,
        key_fn=lambda c: c["monthly_savings_usd"],
        filter_fn=lambda c: c["quality_risk_pct"] <= quality_risk_ceiling,
    ) or _pick_best(
        candidates,
        key_fn=lambda c: c["monthly_savings_usd"],
    )
    aggressive = _pick_best(
        candidates,
        key_fn=lambda c: c["monthly_savings_usd"],
    )

    picks: Dict[str, Any] = {}
    for name, chosen, blurb in (
        (
            "conservative",
            conservative,
            "Cache only near-identical paraphrases. Highest quality safety.",
        ),
        (
            "balanced",
            balanced,
            "Cheapest shape whose quality-risk stays under the ceiling.",
        ),
        (
            "aggressive",
            aggressive,
            "Maximum savings — accepts a wider quality-risk window.",
        ),
    ):
        if not chosen:
            picks[name] = None
            continue
        picks[name] = {
            **chosen,
            "recipe_id": _recipe_id(chosen),
            "blurb": blurb,
        }

    return {
        "engine": ENGINE_VERSION,
        "monthly_requests": monthly_requests,
        "quality_risk_ceiling": quality_risk_ceiling,
        "picks": picks,
        "candidates": candidates,
    }


def _recipe_id(pick: Dict[str, Any]) -> str:
    seed = json.dumps(
        {
            "policy": pick.get("policy"),
            "threshold": round(float(pick.get("threshold", 0.0)), 4),
        },
        sort_keys=True,
    )
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:12]


# ─── Semantic clustering ────────────────────────────────────────────────────
def cluster_workload(
    workload: Sequence[Dict[str, Any]],
    threshold: float = DEFAULT_THRESHOLD,
    max_prompts: int = 400,
) -> Dict[str, Any]:
    """Single-link agglomerative clustering: two prompts merge if cos >= threshold.

    Returns each cluster's representative (first prompt), member count, potential
    hit share, and the intents observed in the cluster. Useful for eyeballing
    *which* intents dominate your workload and would benefit most from caching.
    """
    threshold = max(0.0, min(1.0, float(threshold)))
    prompts = list(workload)[:max_prompts]
    n = len(prompts)
    if n == 0:
        return {
            "engine": ENGINE_VERSION,
            "threshold": round(threshold, 4),
            "clusters": [],
            "cluster_count": 0,
        }

    vecs = [embed(str(p.get("prompt") or "")) for p in prompts]
    parents = list(range(n))

    def find(x: int) -> int:
        while parents[x] != x:
            parents[x] = parents[parents[x]]
            x = parents[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parents[ra] = rb

    for i in range(n):
        for j in range(i + 1, n):
            if cosine(vecs[i], vecs[j]) >= threshold:
                union(i, j)

    groups: Dict[int, List[int]] = {}
    for i in range(n):
        r = find(i)
        groups.setdefault(r, []).append(i)

    total_points = float(n)
    clusters = []
    for root, members in groups.items():
        first_idx = min(members)
        rep = prompts[first_idx]
        intents = sorted({
            str(prompts[i].get("intent") or "") for i in members
            if prompts[i].get("intent")
        })
        clusters.append({
            "cluster_id": f"c{root:03d}",
            "size": len(members),
            "share_pct": round(len(members) / total_points, 4),
            "representative": str(rep.get("prompt") or "")[:180],
            "intents": intents,
            "member_indexes": members[:12],
        })
    clusters.sort(key=lambda c: -c["size"])
    singletons = sum(1 for c in clusters if c["size"] == 1)

    if clusters:
        head_share = sum(c["share_pct"] for c in clusters[: max(1, len(clusters) // 5)])
    else:
        head_share = 0.0

    return {
        "engine": ENGINE_VERSION,
        "threshold": round(threshold, 4),
        "prompt_count": n,
        "cluster_count": len(clusters),
        "singleton_count": singletons,
        "head_share_pct": round(head_share, 4),
        "clusters": clusters,
    }


# ─── Cache compiler (drop-in JSON for middleware) ───────────────────────────
def compile_cache(
    policy: str,
    threshold: float,
    capacity: int = DEFAULT_CAPACITY,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
    monthly_requests: int = DEFAULT_MONTHLY_REQUESTS,
    quality_risk_ceiling: float = 0.08,
    workload: Optional[Sequence[Dict[str, Any]]] = None,
    miss_cost_usd: float = DEFAULT_MISS_COST_USD,
    hit_cost_usd: float = DEFAULT_HIT_COST_USD,
) -> Dict[str, Any]:
    """Emit a JSON cache config a middleware layer can enforce byte-for-byte.

    If ``workload`` is provided the compiler also fires a simulation so the
    caller sees the expected block ("this shape would have saved X / mo on
    that workload").
    """
    policy = policy if policy in POLICY_ORDER else DEFAULT_POLICY
    threshold = max(0.0, min(1.0, float(threshold)))
    capacity = max(1, int(capacity))
    ttl_seconds = max(1, int(ttl_seconds))

    seed = json.dumps(
        {
            "policy": policy,
            "threshold": round(threshold, 4),
            "capacity": capacity,
            "ttl_seconds": ttl_seconds,
            "quality_risk_ceiling": quality_risk_ceiling,
        },
        sort_keys=True,
    )
    cache_id = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]

    expected: Optional[Dict[str, Any]] = None
    if workload is not None:
        sim = simulate_cache(
            workload,
            threshold=threshold,
            capacity=capacity,
            ttl_seconds=ttl_seconds,
            policy=policy,
            miss_cost_usd=miss_cost_usd,
            hit_cost_usd=hit_cost_usd,
        )
        unit_savings_usd = sim["cost"]["savings_usd"] / max(1, sim["totals"]["requests"])
        expected = {
            "hit_rate": sim["rates"]["hit_rate"],
            "quality_risk_pct": sim["rates"]["quality_risk_pct"],
            "avg_latency_ms": sim["latency_ms"]["avg"],
            "monthly_savings_usd": round(unit_savings_usd * monthly_requests, 4),
            "monthly_cost_usd": round(
                sim["cost"]["cost_per_request_actual"] * monthly_requests, 4
            ),
            "monthly_baseline_usd": round(miss_cost_usd * monthly_requests, 4),
        }

    return {
        "engine": ENGINE_VERSION,
        "cache_id": cache_id,
        "policy": policy,
        "policy_name": POLICY_META[policy]["name"],
        "threshold": round(threshold, 4),
        "capacity": capacity,
        "ttl_seconds": ttl_seconds,
        "quality_risk_ceiling": quality_risk_ceiling,
        "safe_similarity_bar": SAFE_SIMILARITY_BAR,
        "embedding": {
            "kind": "hashing-bag-of-tokens-bigram",
            "dim": EMBED_DIM,
            "notes": (
                "Swap for production embeddings (OpenAI text-embedding-3-small "
                "at 1536 dim or open-source bge-small at 384) — the simulator "
                "ratios carry over."
            ),
        },
        "pipeline": [
            {"step": 1, "action": "normalize", "notes": "NFKC, lowercase, whitespace collapse"},
            {"step": 2, "action": "embed", "notes": f"vector({EMBED_DIM})"},
            {"step": 3, "action": "search", "notes": f"cosine >= {threshold:.2f}"},
            {"step": 4, "action": "policy", "notes": f"{POLICY_META[policy]['name']}"},
            {"step": 5, "action": "ttl_sweep", "notes": f"expire > {ttl_seconds}s"},
            {"step": 6, "action": "capacity_bound", "notes": f"max {capacity} entries"},
        ],
        "expected": expected,
    }


def cache_markdown(config: Dict[str, Any]) -> str:
    """Human-readable single-page cache spec — paste into a runbook."""
    lines: List[str] = []
    lines.append(f"# Semantic Cache · `{config.get('cache_id', '')}`")
    lines.append("")
    lines.append(f"**Engine:** `{config.get('engine', '')}`  ")
    lines.append(f"**Policy:** {config.get('policy_name', '')}  ")
    lines.append(f"**Similarity threshold:** {config.get('threshold', 0):.4f}  ")
    lines.append(f"**Capacity:** {config.get('capacity', 0)}  ")
    lines.append(f"**TTL:** {config.get('ttl_seconds', 0)} seconds  ")
    lines.append(f"**Quality-risk ceiling:** {config.get('quality_risk_ceiling', 0):.2%}  ")
    lines.append(f"**Safe similarity bar:** {config.get('safe_similarity_bar', 0):.2f}  ")
    lines.append("")
    lines.append("## Pipeline")
    lines.append("")
    for step in config.get("pipeline", []):
        lines.append(
            f"{step['step']}. **{step['action']}** — {step['notes']}"
        )
    exp = config.get("expected")
    if exp:
        lines.append("")
        lines.append("## Expected on the reference workload")
        lines.append("")
        lines.append(f"- **Hit rate:** {exp['hit_rate']:.2%}")
        lines.append(f"- **Quality risk:** {exp['quality_risk_pct']:.2%}")
        lines.append(f"- **Avg latency:** {exp['avg_latency_ms']:.1f} ms")
        lines.append(f"- **Monthly savings:** ${exp['monthly_savings_usd']:.2f}")
        lines.append(f"- **Monthly cost:** ${exp['monthly_cost_usd']:.2f}")
        lines.append(f"- **Monthly baseline:** ${exp['monthly_baseline_usd']:.2f}")
    return "\n".join(lines).strip() + "\n"


# ─── Introspection ──────────────────────────────────────────────────────────
def list_policies() -> List[Dict[str, Any]]:
    return [POLICY_META[p] for p in POLICY_ORDER]


def defaults() -> Dict[str, Any]:
    return {
        "engine": ENGINE_VERSION,
        "threshold": DEFAULT_THRESHOLD,
        "capacity": DEFAULT_CAPACITY,
        "ttl_seconds": DEFAULT_TTL_SECONDS,
        "policy": DEFAULT_POLICY,
        "monthly_requests": DEFAULT_MONTHLY_REQUESTS,
        "miss_cost_usd": DEFAULT_MISS_COST_USD,
        "hit_cost_usd": DEFAULT_HIT_COST_USD,
        "miss_latency_ms": DEFAULT_MISS_LATENCY_MS,
        "hit_latency_ms": DEFAULT_HIT_LATENCY_MS,
        "safe_similarity_bar": SAFE_SIMILARITY_BAR,
        "threshold_sweep": list(THRESHOLD_SWEEP),
        "policies": list(POLICY_ORDER),
    }


# ─── Seed workloads (realistic paraphrase distributions) ────────────────────
# Each workload is a list of {prompt, intent} pairs. The generators build a
# roughly Zipf-distributed traffic stream from a small canonical intent set.

# Small, deterministic perturbations that a real user would introduce across
# retries: typos, punctuation drift, filler words, and casing changes. Applied
# per-copy so no two rows in the workload are identical — the threshold curve
# then actually shows the intent/paraphrase trade-off it's meant to.
_PERTURB_FILLERS = (
    ("", ""),
    ("please ", ""),
    ("hi, ", ""),
    ("", " thanks"),
    ("hey ", ""),
    ("", " asap"),
    ("quick q: ", ""),
    ("", " (urgent)"),
    ("", " today"),
)
_PERTURB_SWAPS = (
    ("password", "passwd"),
    ("refund", "money back"),
    ("please", "pls"),
    ("cancel", "kill"),
    ("update", "change"),
    ("invoice", "receipt"),
    ("email", "mail"),
    ("account", "profile"),
    ("regex", "regexp"),
    ("connection", "conn"),
    ("configuration", "config"),
    ("subscription", "plan"),
)


def _perturb(text: str, copy_index: int) -> str:
    """Deterministic per-copy perturbation — no RNG, so runs stay stable."""
    if copy_index <= 0:
        return text
    filler_prefix, filler_suffix = _PERTURB_FILLERS[copy_index % len(_PERTURB_FILLERS)]
    swap_from, swap_to = _PERTURB_SWAPS[copy_index % len(_PERTURB_SWAPS)]
    body = text.replace(swap_from, swap_to)
    if copy_index % 3 == 0:
        body = body.replace("?", "")
    if copy_index % 4 == 0:
        body = body.replace(" ", "  ", 1)  # accidental double-space
    return f"{filler_prefix}{body}{filler_suffix}".strip()


def _repeat_with_paraphrases(intent: str, paraphrases: List[str], counts: List[int]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for template, n in zip(paraphrases, counts):
        for i in range(n):
            out.append({"prompt": _perturb(template, i), "intent": intent})
    return out


def _interleave(streams: List[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """Deterministic Zipf-ish interleave — no RNG so results are stable."""
    pointers = [0] * len(streams)
    out: List[Dict[str, Any]] = []
    total = sum(len(s) for s in streams)
    step = 0
    while len(out) < total:
        # Choose the stream whose remaining share is largest so head streams
        # get denser mid-workload representation.
        best = -1
        best_score = -1.0
        for i, s in enumerate(streams):
            remaining = len(s) - pointers[i]
            if remaining <= 0:
                continue
            # Weight by original size / (visits + 1) — favours long streams
            # early, then rotates evenly.
            score = len(s) / (pointers[i] + 1)
            if score > best_score:
                best_score = score
                best = i
        if best < 0:
            break
        item = dict(streams[best][pointers[best]])
        item["timestamp"] = step
        out.append(item)
        pointers[best] += 1
        step += 1
    return out


def _workload_customer_support() -> List[Dict[str, Any]]:
    intents = [
        ("refund_status", [
            "where is my refund?",
            "hey, my refund hasn't arrived. any update?",
            "still waiting on the money to hit my card — any status?",
            "wheres the refund at",
            "refund status pls",
        ], [12, 8, 6, 5, 3]),
        ("reset_password", [
            "how do I reset my password?",
            "i forgot my password, help",
            "cant login, need to reset password",
            "password reset link not working",
        ], [10, 7, 6, 4]),
        ("cancel_subscription", [
            "please cancel my subscription",
            "how do I stop my monthly plan?",
            "want to cancel my membership",
            "unsubscribe me please",
        ], [8, 6, 5, 3]),
        ("shipping_delay", [
            "my package hasn't arrived",
            "why is shipping so slow",
            "order still hasn't shipped, been 5 days",
            "package late",
        ], [7, 6, 4, 3]),
        ("update_email", [
            "how do I change my email address?",
            "need to update the email on my account",
            "change account email please",
        ], [5, 4, 3]),
        ("invoice_copy", [
            "can I get a copy of my invoice",
            "please resend the invoice for last month",
            "invoice download link broken",
        ], [4, 3, 2]),
        ("bug_report_ui", [
            "the button on the checkout page isnt working",
            "add-to-cart button broken",
            "checkout page freezes when i click pay",
        ], [3, 3, 2]),
        ("gift_card", [
            "how do I redeem a gift card?",
            "gift card code not accepted",
        ], [3, 2]),
    ]
    streams = [
        _repeat_with_paraphrases(name, p, c) for name, p, c in intents
    ]
    return _interleave(streams)


def _workload_rag_qa() -> List[Dict[str, Any]]:
    intents = [
        ("pricing_free_tier", [
            "what's included in the free tier?",
            "free plan limits?",
            "how much can i do on the free tier",
            "does the free plan include api access",
        ], [10, 8, 6, 4]),
        ("saml_setup", [
            "how do I set up SAML SSO?",
            "SAML SSO configuration steps",
            "single sign on with okta",
            "connect our IdP to your platform",
        ], [8, 6, 5, 3]),
        ("data_retention", [
            "how long is data retained?",
            "what's the data retention policy",
            "data deletion schedule",
        ], [6, 5, 3]),
        ("rate_limits", [
            "what are the API rate limits?",
            "how many requests per minute?",
            "429 error keeps happening, what are the rate limits",
        ], [7, 5, 3]),
        ("gdpr_compliance", [
            "are you GDPR compliant?",
            "how do you handle EU data requests",
            "dpa available?",
        ], [5, 4, 3]),
        ("regions_available", [
            "which regions is your service deployed in?",
            "is there an EU region?",
            "asia pacific hosting?",
        ], [4, 3, 2]),
        ("model_list", [
            "which models do you support?",
            "list of supported providers",
            "do you have anthropic support?",
        ], [3, 3, 2]),
    ]
    streams = [
        _repeat_with_paraphrases(name, p, c) for name, p, c in intents
    ]
    return _interleave(streams)


def _workload_code_help() -> List[Dict[str, Any]]:
    intents = [
        ("nullptr_bug", [
            "why am I getting a null pointer exception here?",
            "NPE keeps firing on this line",
            "getting null pointer even after checking",
        ], [8, 6, 4]),
        ("regex_help", [
            "how do I write a regex that matches an email?",
            "email address regex please",
            "regex to validate emails",
        ], [7, 5, 3]),
        ("sql_join_fix", [
            "why is my LEFT JOIN returning duplicates?",
            "join gives me too many rows",
            "sql query returning multiple copies",
        ], [6, 5, 3]),
        ("git_conflict", [
            "how do I resolve a git merge conflict?",
            "merge conflict on main, help",
            "git rebase conflicts, how to fix",
        ], [6, 4, 3]),
        ("react_state_stale", [
            "React state is stale in my useEffect",
            "useEffect closure captures old state",
            "useState value not updating in effect",
        ], [5, 4, 3]),
        ("docker_port", [
            "docker container not exposing port",
            "port mapping not working with docker run",
        ], [4, 3]),
        ("python_venv", [
            "how do I create a python virtual env?",
            "python venv setup steps",
        ], [3, 2]),
    ]
    streams = [
        _repeat_with_paraphrases(name, p, c) for name, p, c in intents
    ]
    return _interleave(streams)


_WORKLOAD_BUILDERS = {
    "customer_support": {
        "id": "customer_support",
        "name": "Customer Support Chatbot",
        "description": (
            "~80 messages across 8 canonical intents (refund_status, "
            "reset_password, cancel_subscription, …). High paraphrase density, "
            "long tail thin."
        ),
        "builder": _workload_customer_support,
    },
    "rag_qa": {
        "id": "rag_qa",
        "name": "RAG FAQ Bot",
        "description": (
            "~75 messages across 7 knowledge-base intents (pricing, SAML, data "
            "retention, …). Heavier head, fewer paraphrase families."
        ),
        "builder": _workload_rag_qa,
    },
    "code_help": {
        "id": "code_help",
        "name": "Developer Code Help",
        "description": (
            "~60 messages across 7 debug patterns (null pointer, regex, SQL "
            "joins, git conflict, …). Broadest lexical diversity."
        ),
        "builder": _workload_code_help,
    },
}


def list_workloads() -> List[Dict[str, Any]]:
    out = []
    for meta in _WORKLOAD_BUILDERS.values():
        wl = meta["builder"]()
        out.append({
            "id": meta["id"],
            "name": meta["name"],
            "description": meta["description"],
            "size": len(wl),
            "distinct_intents": len({item["intent"] for item in wl}),
            "sample": [item["prompt"] for item in wl[:6]],
        })
    return out


def load_workload(workload_id: str) -> List[Dict[str, Any]]:
    meta = _WORKLOAD_BUILDERS.get(workload_id)
    if not meta:
        raise ValueError(f"unknown workload_id: {workload_id!r}")
    return meta["builder"]()


# ─── First-load seed bundle ─────────────────────────────────────────────────
def seed_demo() -> Dict[str, Any]:
    """Deterministic first-load bundle — same input every request."""
    workload = load_workload("customer_support")
    picks = recommend_configs(
        workload,
        capacity=DEFAULT_CAPACITY,
        ttl_seconds=DEFAULT_TTL_SECONDS,
        monthly_requests=DEFAULT_MONTHLY_REQUESTS,
    )
    balanced = picks["picks"].get("balanced") or {}
    threshold = balanced.get("threshold", DEFAULT_THRESHOLD)
    policy = balanced.get("policy", DEFAULT_POLICY)
    sim = simulate_cache(
        workload,
        threshold=threshold,
        capacity=DEFAULT_CAPACITY,
        ttl_seconds=DEFAULT_TTL_SECONDS,
        policy=policy,
    )
    curve = sweep_thresholds(workload, policy=policy)
    grid = sweep_policies(workload)
    clusters = cluster_workload(workload, threshold=threshold)
    config = compile_cache(
        policy,
        threshold,
        capacity=DEFAULT_CAPACITY,
        ttl_seconds=DEFAULT_TTL_SECONDS,
        monthly_requests=DEFAULT_MONTHLY_REQUESTS,
        workload=workload,
    )
    return {
        "engine": ENGINE_VERSION,
        "workload_id": "customer_support",
        "workload_size": len(workload),
        "workloads": list_workloads(),
        "policies": list_policies(),
        "defaults": defaults(),
        "recommendations": picks,
        "simulation": sim,
        "threshold_curve": curve,
        "policy_grid": grid,
        "clusters": clusters,
        "compiled": config,
        "markdown": cache_markdown(config),
    }
