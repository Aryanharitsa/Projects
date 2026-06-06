"""TITAN adverse-media screening engine.

Deterministic, dependency-free open-source intelligence (OSINT) layer
that scans entity names against a bundled corpus of negative-news
articles (`data/adverse_media.json`). Returns a composite risk score
0..100 per entity together with the exact articles that fired and a
component breakdown so an auditor can see *why* the score moved.

Why this exists
---------------
Sanctions screening answers a binary question against a *closed* list.
Real EDD also asks the open-world question: "what is the world saying
about this entity?" Adverse-media coverage of fraud, corruption,
sanctions-evasion, regulatory enforcement, or material litigation is
a tier-2 EDD signal that compliance teams use to escalate KYC reviews
even when no SDN hit exists.

Composite model
---------------
Per-article hit strength for an entity:

    hit_strength = similarity                 (0..1, fuzzy name match)
                  * category.severity         (0..1, e.g. money_laundering=1.0, litigation=0.5)
                  * source_tier.weight        (0..1, e.g. tier-1=1.0, tier-3=0.5)
                  * recency_decay             (0..1, exponential, half-life configurable)

    recency_decay = 0.5 ** (age_days / half_life_days)   default half_life=365

Per-entity aggregate:

    raw       = Σ top_K(hit_strength)         (K default 12)
    composite = 100 * (1 - exp(-raw / k))     (k default 2.5, saturating)

So one strong recent hit (sim≈0.9 × sev=1.0 × tier=1.0 × decay≈0.95 ≈ 0.85)
lands at ≈ 29; four strong hits ≈ 73; ten strong hits ≈ 96 — material
coverage saturates near 100 without ever crossing.

Grades:

    clear     <  15
    elevated  15 .. 39
    material  40 .. 69
    severe    >= 70

Name matching reuses the same physics as sanctions.py (token-set +
char-3gram + containment blend) so analysts see consistent similarity
arithmetic across both EDD surfaces — only the threshold floor is
relaxed (0.55 for adverse media vs 0.65 for sanctions) because media
coverage is fuzzier than a SDN list and false positives cost less than
missing a real adverse hit.
"""

from __future__ import annotations

import json
import math
import os
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Tunables — exposed via /aml/media/rules so callers can audit them.
# ---------------------------------------------------------------------------

W_TOKEN_SET = 0.55
W_NGRAM = 0.30
W_CONTAIN = 0.15
N_GRAM = 3

DEFAULT_SIMILARITY_FLOOR = 0.55     # don't include hits below this
DEFAULT_HALF_LIFE_DAYS = 365.0      # 1y → 0.50, 2y → 0.25, …
DEFAULT_TOP_K = 12                  # how many hits feed the composite
COMPOSITE_K = 2.5                   # saturating constant

GRADES: List[Tuple[float, str]] = [
    (70.0, "severe"),
    (40.0, "material"),
    (15.0, "elevated"),
    (0.0,  "clear"),
]

# Same name noise as sanctions, intentionally kept in sync.
STOPWORDS = {
    "the", "and", "of", "for", "co", "company", "ltd", "limited", "llc",
    "inc", "incorporated", "corp", "corporation", "gmbh", "ag", "sa", "sarl",
    "pjsc", "fze", "fzco", "fzc", "jsc", "pte", "plc", "pvt", "private",
    "holdings", "holding", "group", "trading", "international", "intl",
    "global", "bank", "banking", "finance", "financial", "industries",
    "sdn", "bhd", "as", "oao", "ojsc", "ooo", "kg", "kft", "spa", "srl",
}


# ---------------------------------------------------------------------------
# Domain
# ---------------------------------------------------------------------------

_DEFAULT_PATH = os.path.join(os.path.dirname(__file__), "data", "adverse_media.json")


@dataclass
class Article:
    id: str
    headline: str
    snippet: str
    url: str
    source: str
    source_tier: int
    published: str          # ISO date "YYYY-MM-DD"
    category: str
    entities_mentioned: List[str]
    published_dt: Optional[datetime] = None
    mentioned_index: List[Tuple[str, set, set, str]] = field(default_factory=list)
    # Normalised forms cached at load time so the matcher does zero
    # parsing per query: (raw, token_set, ngram_set, lowered_norm).

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "headline": self.headline,
            "snippet": self.snippet,
            "url": self.url,
            "source": self.source,
            "source_tier": self.source_tier,
            "published": self.published,
            "category": self.category,
            "entities_mentioned": self.entities_mentioned,
        }


_LOADED: Optional[Dict[str, Any]] = None
_INDEX: Optional[List[Article]] = None


# ---------------------------------------------------------------------------
# Normalisation + similarity (shared physics with sanctions.py)
# ---------------------------------------------------------------------------


def _normalize(s: str) -> str:
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _tokens(s: str) -> List[str]:
    n = _normalize(s)
    return [t for t in n.split(" ") if t and t not in STOPWORDS]


def _ngrams(s: str, n: int = N_GRAM) -> set:
    n_str = _normalize(s).replace(" ", "")
    if len(n_str) < n:
        return {n_str} if n_str else set()
    return {n_str[i : i + n] for i in range(len(n_str) - n + 1)}


def _jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def _token_set_ratio(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    base = _jaccard(a, b)
    soft_hits = 0
    for x in a:
        if x in b:
            continue
        for y in b:
            if len(x) >= 4 and len(y) >= 4 and (x.startswith(y[:4]) or y.startswith(x[:4])):
                soft_hits += 1
                break
    soft = soft_hits / max(len(a | b), 1)
    return min(1.0, base + 0.4 * soft)


def _containment(a_norm: str, b_norm: str) -> float:
    if not a_norm or not b_norm:
        return 0.0
    if a_norm in b_norm or b_norm in a_norm:
        return 1.0
    short, long = (a_norm, b_norm) if len(a_norm) <= len(b_norm) else (b_norm, a_norm)
    grams = {short[i : i + 4] for i in range(max(1, len(short) - 3))}
    if not grams:
        return 0.0
    hit = sum(1 for g in grams if g in long)
    return hit / len(grams)


def _similarity(query_norm: str, query_tokens: set, query_grams: set,
                mention_norm: str, mention_tokens: set, mention_grams: set) -> Tuple[float, Dict[str, float]]:
    ts = _token_set_ratio(query_tokens, mention_tokens)
    ng = _jaccard(query_grams, mention_grams)
    ct = _containment(query_norm, mention_norm)
    blended = W_TOKEN_SET * ts + W_NGRAM * ng + W_CONTAIN * ct
    return blended, {"token_set": round(ts, 4), "ngram": round(ng, 4),
                     "contain": round(ct, 4), "blended": round(blended, 4)}


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------


def _parse_date(raw: str) -> Optional[datetime]:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _load() -> Dict[str, Any]:
    global _LOADED, _INDEX
    if _LOADED is not None:
        return _LOADED
    path = os.getenv("TITAN_ADVERSE_MEDIA_PATH", _DEFAULT_PATH)
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    articles: List[Article] = []
    for a in raw["articles"]:
        art = Article(
            id=a["id"],
            headline=a["headline"],
            snippet=a.get("snippet", ""),
            url=a.get("url", ""),
            source=a.get("source", ""),
            source_tier=int(a.get("source_tier", 3)),
            published=a.get("published", ""),
            category=a.get("category", "litigation"),
            entities_mentioned=list(a.get("entities_mentioned", [])),
        )
        art.published_dt = _parse_date(art.published)
        art.mentioned_index = [
            (m, set(_tokens(m)), _ngrams(m), _normalize(m))
            for m in art.entities_mentioned
        ]
        articles.append(art)
    meta = {k: raw[k] for k in raw if k != "articles"}
    _LOADED = {"meta": meta, "articles": articles}
    _INDEX = articles
    return _LOADED


def _categories() -> Dict[str, Dict[str, Any]]:
    data = _load()
    return {c["key"]: c for c in data["meta"].get("categories", [])}


def _tiers() -> Dict[int, Dict[str, Any]]:
    data = _load()
    return {int(t["tier"]): t for t in data["meta"].get("tiers", [])}


def _tier_weight(tier: int) -> float:
    tiers = _tiers()
    if tier in tiers:
        try:
            return float(tiers[tier].get("weight", 0.5))
        except (TypeError, ValueError):
            pass
    # Sensible defaults if a future article uses an unknown tier.
    if tier <= 1:
        return 1.0
    if tier == 2:
        return 0.75
    return 0.5


def _category_severity(category: str) -> float:
    cats = _categories()
    if category in cats:
        try:
            return float(cats[category].get("severity", 0.5))
        except (TypeError, ValueError):
            pass
    return 0.5


def _category_accent(category: str) -> str:
    cats = _categories()
    return cats.get(category, {}).get("accent", "#94a3b8")


def _recency_decay(article: Article, *, now: datetime, half_life_days: float) -> float:
    if not article.published_dt or half_life_days <= 0:
        return 1.0
    age_days = max(0.0, (now - article.published_dt).total_seconds() / 86400.0)
    return 0.5 ** (age_days / half_life_days)


def _grade(composite: float) -> str:
    for floor, label in GRADES:
        if composite >= floor:
            return label
    return "clear"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_metadata() -> Dict[str, Any]:
    """Auditor-facing metadata about the loaded corpus + engine knobs."""
    data = _load()
    cats = _categories()
    tiers = _tiers()
    by_cat: Dict[str, int] = {}
    by_tier: Dict[str, int] = {}
    by_year: Dict[str, int] = {}
    for a in data["articles"]:
        by_cat[a.category] = by_cat.get(a.category, 0) + 1
        by_tier[str(a.source_tier)] = by_tier.get(str(a.source_tier), 0) + 1
        year = a.published[:4] if a.published else "unknown"
        by_year[year] = by_year.get(year, 0) + 1
    return {
        **data["meta"],
        "size": len(data["articles"]),
        "by_category": by_cat,
        "by_tier": by_tier,
        "by_year": dict(sorted(by_year.items())),
        "weights": {
            "token_set": W_TOKEN_SET,
            "ngram": W_NGRAM,
            "contain": W_CONTAIN,
            "ngram_n": N_GRAM,
        },
        "tuning": {
            "similarity_floor": DEFAULT_SIMILARITY_FLOOR,
            "half_life_days": DEFAULT_HALF_LIFE_DAYS,
            "top_k": DEFAULT_TOP_K,
            "composite_k": COMPOSITE_K,
        },
        "grades": [{"min": floor, "label": label} for floor, label in sorted(GRADES, key=lambda x: x[0])],
        "categories": list(cats.values()),
        "tiers": list(tiers.values()),
    }


def list_articles(
    *,
    category: Optional[str] = None,
    tier: Optional[int] = None,
    q: Optional[str] = None,
    limit: Optional[int] = 200,
) -> List[Dict[str, Any]]:
    """Browse the corpus with simple substring + filter semantics."""
    data = _load()
    qn = (q or "").strip().lower()
    out: List[Dict[str, Any]] = []
    for a in data["articles"]:
        if category and a.category != category:
            continue
        if tier is not None and a.source_tier != tier:
            continue
        if qn:
            hay = " ".join([a.headline, a.snippet, a.source, *a.entities_mentioned]).lower()
            if qn not in hay:
                continue
        out.append(a.to_dict())
    # Most recent first; falls back to id desc when no date.
    out.sort(key=lambda r: (r.get("published") or "", r.get("id") or ""), reverse=True)
    return out if limit is None else out[: max(1, limit)]


def get_article(article_id: str) -> Optional[Dict[str, Any]]:
    data = _load()
    for a in data["articles"]:
        if a.id == article_id:
            return {
                **a.to_dict(),
                "category_severity": _category_severity(a.category),
                "source_tier_weight": _tier_weight(a.source_tier),
                "category_accent": _category_accent(a.category),
            }
    return None


def screen_entity(
    name: str,
    *,
    jurisdiction: Optional[str] = None,
    similarity_floor: float = DEFAULT_SIMILARITY_FLOOR,
    half_life_days: float = DEFAULT_HALF_LIFE_DAYS,
    top_k: int = DEFAULT_TOP_K,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Screen `name` against the corpus; return scored hit list + composite."""
    _load()
    if not name or not name.strip():
        return _empty_report(name or "")

    assert _INDEX is not None
    now = now or datetime.now(timezone.utc)
    q_norm = _normalize(name)
    q_tokens = set(_tokens(name))
    q_grams = _ngrams(name)

    hits: List[Dict[str, Any]] = []
    for art in _INDEX:
        # Pick the best mention per article so one article with two mentions
        # doesn't double-count.
        best_sim, best_components, best_mention = 0.0, {}, ""
        for mention_raw, m_tokens, m_grams, m_norm in art.mentioned_index:
            sim, comp = _similarity(q_norm, q_tokens, q_grams, m_norm, m_tokens, m_grams)
            if sim > best_sim:
                best_sim, best_components, best_mention = sim, comp, mention_raw
        if best_sim < similarity_floor:
            continue
        decay = _recency_decay(art, now=now, half_life_days=half_life_days)
        sev = _category_severity(art.category)
        tier_w = _tier_weight(art.source_tier)
        hit_strength = best_sim * sev * tier_w * decay
        age_days = (
            (now - art.published_dt).total_seconds() / 86400.0
            if art.published_dt else None
        )
        hits.append({
            "article_id": art.id,
            "headline": art.headline,
            "snippet": art.snippet,
            "url": art.url,
            "source": art.source,
            "source_tier": art.source_tier,
            "source_tier_weight": round(tier_w, 4),
            "published": art.published,
            "category": art.category,
            "category_severity": round(sev, 4),
            "category_accent": _category_accent(art.category),
            "matched_mention": best_mention,
            "similarity": round(best_sim, 4),
            "components": best_components,
            "recency_decay": round(decay, 4),
            "age_days": round(age_days, 1) if age_days is not None else None,
            "hit_strength": round(hit_strength, 4),
        })

    hits.sort(key=lambda h: h["hit_strength"], reverse=True)

    if not hits:
        return _empty_report(name)

    top_hits = hits[: max(1, top_k)]
    raw = sum(h["hit_strength"] for h in top_hits)
    composite = 100.0 * (1.0 - math.exp(-raw / COMPOSITE_K))
    composite = max(0.0, min(100.0, composite))

    # Recency profile (4 buckets, all hits — not just top_k)
    bucket_days = [30, 90, 365]
    bucket_labels = ["last_30d", "last_90d", "last_year", "older"]
    buckets = {label: {"count": 0, "strength": 0.0} for label in bucket_labels}
    for h in hits:
        age = h["age_days"] if h["age_days"] is not None else 9999.0
        if age <= bucket_days[0]:
            label = bucket_labels[0]
        elif age <= bucket_days[1]:
            label = bucket_labels[1]
        elif age <= bucket_days[2]:
            label = bucket_labels[2]
        else:
            label = bucket_labels[3]
        buckets[label]["count"] += 1
        buckets[label]["strength"] = round(buckets[label]["strength"] + h["hit_strength"], 4)

    # Category rollup — sum hit_strength per category across all hits.
    cat_roll: Dict[str, Dict[str, Any]] = {}
    cats_meta = _categories()
    for h in hits:
        c = h["category"]
        slot = cat_roll.setdefault(c, {
            "category": c,
            "label": cats_meta.get(c, {}).get("label", c),
            "accent": cats_meta.get(c, {}).get("accent", "#94a3b8"),
            "severity": cats_meta.get(c, {}).get("severity", 0.5),
            "count": 0,
            "strength": 0.0,
        })
        slot["count"] += 1
        slot["strength"] = round(slot["strength"] + h["hit_strength"], 4)
    categories = sorted(cat_roll.values(), key=lambda r: r["strength"], reverse=True)

    # Source-tier rollup — useful for the UI's "tier-1 hits" headline chip.
    tier_roll: Dict[int, int] = {}
    for h in hits:
        tier_roll[h["source_tier"]] = tier_roll.get(h["source_tier"], 0) + 1

    return {
        "query": name,
        "normalized": q_norm,
        "jurisdiction": jurisdiction,
        "similarity_floor": similarity_floor,
        "half_life_days": half_life_days,
        "top_k": top_k,
        "composite": round(composite, 1),
        "grade": _grade(composite),
        "hit_count": len(hits),
        "raw_strength": round(raw, 4),
        "hits": hits,
        "top_hits": top_hits,
        "categories": categories,
        "recency": buckets,
        "tiers": {str(k): v for k, v in sorted(tier_roll.items())},
        "headline_hit": top_hits[0] if top_hits else None,
    }


def _empty_report(name: str) -> Dict[str, Any]:
    return {
        "query": name,
        "normalized": _normalize(name),
        "similarity_floor": DEFAULT_SIMILARITY_FLOOR,
        "half_life_days": DEFAULT_HALF_LIFE_DAYS,
        "top_k": DEFAULT_TOP_K,
        "composite": 0.0,
        "grade": "clear",
        "hit_count": 0,
        "raw_strength": 0.0,
        "hits": [],
        "top_hits": [],
        "categories": [],
        "recency": {
            "last_30d": {"count": 0, "strength": 0.0},
            "last_90d": {"count": 0, "strength": 0.0},
            "last_year": {"count": 0, "strength": 0.0},
            "older": {"count": 0, "strength": 0.0},
        },
        "tiers": {},
        "headline_hit": None,
    }


def screen_batch(
    names: Iterable[str],
    *,
    jurisdiction: Optional[str] = None,
    similarity_floor: float = DEFAULT_SIMILARITY_FLOOR,
    half_life_days: float = DEFAULT_HALF_LIFE_DAYS,
    top_k: int = DEFAULT_TOP_K,
    now: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    seen: set = set()
    for n in names:
        key = (n or "").strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(screen_entity(
            n,
            jurisdiction=jurisdiction,
            similarity_floor=similarity_floor,
            half_life_days=half_life_days,
            top_k=top_k,
            now=now,
        ))
    return out


def hits_for_account(
    account_names: Iterable[str],
    *,
    similarity_floor: float = DEFAULT_SIMILARITY_FLOOR,
    half_life_days: float = DEFAULT_HALF_LIFE_DAYS,
    top_k: int = DEFAULT_TOP_K,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Risk-engine convenience: feed account-side names → one rolled-up report.

    Returns `{composite, grade, hit_count, names_screened, per_name[]}`.
    `per_name` is the per-name screen_entity payload for evidence; the
    rollup composite is the **max** across names so one strong adverse
    hit anywhere in the account's name footprint dominates — same shape
    of intuition the analyst already has from sanctions screening.
    """
    seen: set = set()
    reports: List[Dict[str, Any]] = []
    for n in account_names:
        key = _normalize(n or "")
        if not key or key in seen:
            continue
        seen.add(key)
        r = screen_entity(
            n,
            similarity_floor=similarity_floor,
            half_life_days=half_life_days,
            top_k=top_k,
            now=now,
        )
        if r["hit_count"] > 0:
            reports.append(r)

    if not reports:
        return {
            "composite": 0.0,
            "grade": "clear",
            "hit_count": 0,
            "names_screened": len(seen),
            "per_name": [],
            "top_articles": [],
        }

    reports.sort(key=lambda r: r["composite"], reverse=True)
    top = reports[0]
    # Top articles overall — pull a deduped union across reports, sort by hit_strength.
    seen_articles: set = set()
    union: List[Dict[str, Any]] = []
    for r in reports:
        for h in r["hits"]:
            if h["article_id"] in seen_articles:
                continue
            seen_articles.add(h["article_id"])
            union.append({**h, "queried_name": r["query"]})
    union.sort(key=lambda h: h["hit_strength"], reverse=True)

    return {
        "composite": top["composite"],
        "grade": top["grade"],
        "hit_count": sum(r["hit_count"] for r in reports),
        "names_screened": len(seen),
        "per_name": [{
            "name": r["query"],
            "composite": r["composite"],
            "grade": r["grade"],
            "hit_count": r["hit_count"],
            "headline_hit": r["headline_hit"],
        } for r in reports],
        "top_articles": union[:5],
    }
