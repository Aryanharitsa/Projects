"""TITAN sanctions screening engine.

Deterministic, dependency-free fuzzy matcher over a packaged demo
watchlist (`data/sanctions.json`). Returns a similarity score per candidate
together with a transparent component breakdown so an auditor can see
exactly *why* the matcher fired.

The score is a weighted blend of three classical signals:

    similarity = 0.55 · token_set_ratio
               + 0.30 · char_ngram_overlap     (n=3)
               + 0.15 · containment_bonus      (substring either way)

Each signal is in [0, 1], so the blended score is in [0, 1] too. We also
emit a small jurisdiction prior — counterparty geos that match the listed
entity's jurisdiction get a +0.05 bump (capped at 1.0). The matcher walks
both the canonical name and every alias, returns the strongest hit, and
records which alias produced it.

Match grades (purely advisory; the AML detector decides what to do):

    weak     0.45 ≤ s < 0.65
    medium   0.65 ≤ s < 0.80
    strong   0.80 ≤ s < 0.92
    exact    s ≥ 0.92
"""

from __future__ import annotations

import json
import os
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


# ---------------------------------------------------------------------------
# Tunables — exposed via /aml/sanctions/list so callers can audit them.
# ---------------------------------------------------------------------------

W_TOKEN_SET = 0.55
W_NGRAM = 0.30
W_CONTAIN = 0.15
N_GRAM = 3
JURISDICTION_BONUS = 0.05

GRADES: List[Tuple[float, str]] = [
    (0.92, "exact"),
    (0.80, "strong"),
    (0.65, "medium"),
    (0.45, "weak"),
]

# Token noise that adds zero discriminative value but inflates Jaccard.
STOPWORDS = {
    "the", "and", "of", "for", "co", "company", "ltd", "limited", "llc",
    "inc", "incorporated", "corp", "corporation", "gmbh", "ag", "sa", "sarl",
    "pjsc", "fze", "fzco", "fzc", "jsc", "pte", "plc", "pvt", "private",
    "holdings", "holding", "group", "trading", "international", "intl",
    "global", "bank", "banking", "finance", "financial", "industries",
    "sdn", "bhd", "as", "oao", "ojsc", "ooo", "kg", "kft", "spa", "srl",
}


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

_DEFAULT_PATH = os.path.join(os.path.dirname(__file__), "data", "sanctions.json")


@dataclass
class Entity:
    id: str
    name: str
    type: str
    aliases: List[str]
    jurisdiction: str
    list_: str
    added: str
    reason: str

    @property
    def all_names(self) -> List[str]:
        # canonical first; matcher will return the *index* of the strongest
        # hit so we can surface which form fired.
        return [self.name, *self.aliases]


_LOADED: Optional[Dict[str, Any]] = None
_INDEXED: Optional[List[Tuple[Entity, List[str], List[set], List[set]]]] = None


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


def _load() -> Dict[str, Any]:
    global _LOADED, _INDEXED
    if _LOADED is not None:
        return _LOADED
    path = os.getenv("TITAN_WATCHLIST_PATH", _DEFAULT_PATH)
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    entities: List[Entity] = []
    for e in raw["entries"]:
        entities.append(
            Entity(
                id=e["id"],
                name=e["name"],
                type=e.get("type", "entity"),
                aliases=list(e.get("aliases", [])),
                jurisdiction=e.get("jurisdiction", ""),
                list_=e.get("list", ""),
                added=e.get("added", ""),
                reason=e.get("reason", ""),
            )
        )
    indexed: List[Tuple[Entity, List[str], List[set], List[set]]] = []
    for ent in entities:
        names = ent.all_names
        norms = [_normalize(n) for n in names]
        token_sets = [set(_tokens(n)) for n in names]
        gram_sets = [_ngrams(n) for n in names]
        indexed.append((ent, norms, token_sets, gram_sets))
    _LOADED = {"meta": {k: raw[k] for k in raw if k != "entries"}, "entities": entities}
    _INDEXED = indexed
    return _LOADED


def get_metadata() -> Dict[str, Any]:
    """Return the watchlist meta (version / source / note / counts)."""
    data = _load()
    counts_by_list: Dict[str, int] = {}
    counts_by_juris: Dict[str, int] = {}
    counts_by_type = {"entity": 0, "individual": 0}
    for e in data["entities"]:
        counts_by_list[e.list_] = counts_by_list.get(e.list_, 0) + 1
        counts_by_juris[e.jurisdiction] = counts_by_juris.get(e.jurisdiction, 0) + 1
        counts_by_type[e.type] = counts_by_type.get(e.type, 0) + 1
    return {
        **data["meta"],
        "weights": {
            "token_set": W_TOKEN_SET,
            "ngram": W_NGRAM,
            "contain": W_CONTAIN,
            "ngram_n": N_GRAM,
            "jurisdiction_bonus": JURISDICTION_BONUS,
        },
        "grades": [{"min": min_, "label": label} for min_, label in GRADES],
        "size": len(data["entities"]),
        "by_list": counts_by_list,
        "by_jurisdiction": counts_by_juris,
        "by_type": counts_by_type,
    }


def list_entries(limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """Return the entries as serialisable dicts (capped at `limit`)."""
    data = _load()
    rows = [
        {
            "id": e.id,
            "name": e.name,
            "type": e.type,
            "aliases": e.aliases,
            "jurisdiction": e.jurisdiction,
            "list": e.list_,
            "added": e.added,
            "reason": e.reason,
        }
        for e in data["entities"]
    ]
    return rows if limit is None else rows[:limit]


# ---------------------------------------------------------------------------
# Similarity components
# ---------------------------------------------------------------------------


def _jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def _token_set_ratio(a: set, b: set) -> float:
    """Jaccard of tokens, but soft-matched on prefix collisions so that
    ``volkov`` and ``volkov-baranov`` overlap. Symmetric.
    """
    if not a or not b:
        return 0.0
    base = _jaccard(a, b)
    # Soft-prefix bonus: count tokens in a that share a >=4-char prefix
    # with anything in b (and vice versa). Capped so it can't dominate.
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
    """1.0 if either string is a substring of the other (after normalisation),
    else a length-weighted partial-overlap on the longest common 4-char run.
    """
    if not a_norm or not b_norm:
        return 0.0
    if a_norm in b_norm or b_norm in a_norm:
        return 1.0
    # Greedy LCS-of-4grams; cheap stand-in for a full LCS that avoids any
    # external deps. Returns coverage of the shorter string.
    short, long = (a_norm, b_norm) if len(a_norm) <= len(b_norm) else (b_norm, a_norm)
    grams = {short[i : i + 4] for i in range(max(1, len(short) - 3))}
    if not grams:
        return 0.0
    hit = sum(1 for g in grams if g in long)
    return hit / len(grams)


def _grade(score: float) -> str:
    for floor, label in GRADES:
        if score >= floor:
            return label
    return "none"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def screen(
    name: str,
    *,
    jurisdiction: Optional[str] = None,
    threshold: float = 0.45,
    top_k: int = 5,
) -> Dict[str, Any]:
    """Score `name` against the loaded watchlist; return ranked candidates.

    `jurisdiction` (optional ISO-3166-α2) lets callers nudge candidates with
    a matching jurisdiction up by +JURISDICTION_BONUS (post-blend, capped).
    """
    _load()
    if not name or not name.strip():
        return {"query": name or "", "matches": [], "best": None, "graded": "none"}

    q_norm = _normalize(name)
    q_tokens = set(_tokens(name))
    q_grams = _ngrams(name)
    q_juris = (jurisdiction or "").upper().strip()

    candidates: List[Dict[str, Any]] = []
    assert _INDEXED is not None
    for ent, norms, token_sets, gram_sets in _INDEXED:
        # Score every alias; keep the strongest.
        best_idx, best_score, best_components = 0, 0.0, {}
        for i, (n_norm, t_set, g_set) in enumerate(zip(norms, token_sets, gram_sets)):
            ts = _token_set_ratio(q_tokens, t_set)
            ng = _jaccard(q_grams, g_set)
            ct = _containment(q_norm, n_norm)
            blended = W_TOKEN_SET * ts + W_NGRAM * ng + W_CONTAIN * ct
            if blended > best_score:
                best_score = blended
                best_idx = i
                best_components = {
                    "token_set": round(ts, 4),
                    "ngram": round(ng, 4),
                    "contain": round(ct, 4),
                    "blended": round(blended, 4),
                }
        # Jurisdiction prior (post-blend).
        juris_bonus = 0.0
        if q_juris and ent.jurisdiction.upper() == q_juris:
            juris_bonus = JURISDICTION_BONUS
            best_score = min(1.0, best_score + juris_bonus)
            best_components["jurisdiction_bonus"] = juris_bonus

        if best_score >= threshold:
            matched_form = ent.all_names[best_idx]
            candidates.append(
                {
                    "entity_id": ent.id,
                    "name": ent.name,
                    "type": ent.type,
                    "matched_alias": matched_form,
                    "alias_index": best_idx,
                    "jurisdiction": ent.jurisdiction,
                    "list": ent.list_,
                    "added": ent.added,
                    "reason": ent.reason,
                    "similarity": round(best_score, 4),
                    "grade": _grade(best_score),
                    "components": best_components,
                }
            )

    candidates.sort(key=lambda c: c["similarity"], reverse=True)
    candidates = candidates[: max(1, top_k)]
    best = candidates[0] if candidates else None

    return {
        "query": name,
        "normalized": q_norm,
        "threshold": threshold,
        "matches": candidates,
        "best": best,
        "graded": best["grade"] if best else "none",
    }


def screen_many(
    names: Iterable[str],
    *,
    jurisdiction: Optional[str] = None,
    threshold: float = 0.45,
    top_k: int = 3,
) -> List[Dict[str, Any]]:
    """Screen a batch of names; one result per query, in input order."""
    return [
        screen(n, jurisdiction=jurisdiction, threshold=threshold, top_k=top_k)
        for n in names
    ]


def hits_for_account(
    account_names: Iterable[str],
    *,
    jurisdiction: Optional[str] = None,
    threshold: float = 0.65,
) -> List[Dict[str, Any]]:
    """Screen a deduped, normalised set of names. Returns one result per
    name where similarity ≥ threshold, sorted by similarity desc.

    The AML detector calls this with the union of the account's own name +
    every counterparty name; threshold defaults to 0.65 ("medium" grade)
    so that weak coincidental overlaps don't push an otherwise clean
    account into a higher band.
    """
    seen_norm: Dict[str, str] = {}
    for n in account_names:
        nn = _normalize(n or "")
        if nn and nn not in seen_norm:
            seen_norm[nn] = n
    out: List[Dict[str, Any]] = []
    for raw in seen_norm.values():
        r = screen(raw, jurisdiction=jurisdiction, threshold=threshold, top_k=1)
        if r["best"]:
            out.append({"queried_name": raw, **r["best"]})
    out.sort(key=lambda h: h["similarity"], reverse=True)
    return out
