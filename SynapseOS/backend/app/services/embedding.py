"""
Zero-dependency TF-IDF embedding + cosine similarity.

We deliberately avoid calling out to OpenAI / sentence-transformers for the
v0 synapse engine so the project works out of the box on any machine with
no API key and no GPU. The math is standard and the results are genuinely
useful for short- to medium-length personal notes.

A future day can plug in a richer `Embedder` implementation — any object
with `.encode(str) -> Sequence[float]` works with `cosine_sim`.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Dict, Iterable, List, Sequence, Tuple

# A compact English stopword list. Not as big as sklearn's, but enough
# to make TF-IDF behave well on personal notes.
_STOPWORDS = frozenset("""
a an and or but the this that these those is are was were be been being
am do does did have has had having i we you he she it they them us our
your their his her my mine yours theirs ours on in at to from by for of
as with without within into onto about over under up down after before
again against all any both each few more most other own same so some such
than too very can will just would should could may might must shall here
there when where why how what which who whom whose not no nor only also
then if because while during between through until about
""".split())


_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_\-']{1,}")


def tokenize(text: str) -> List[str]:
    """Lowercase, extract alphabetic-initial tokens, drop stopwords."""
    return [
        tok for tok in (m.group(0).lower() for m in _TOKEN_RE.finditer(text))
        if tok not in _STOPWORDS and len(tok) > 1
    ]


def build_idf(corpus: Sequence[Sequence[str]]) -> Dict[str, float]:
    """Inverse document frequency, smoothed (Laplace)."""
    N = len(corpus)
    df: Counter = Counter()
    for doc in corpus:
        for term in set(doc):
            df[term] += 1
    return {
        term: math.log((1 + N) / (1 + count)) + 1.0
        for term, count in df.items()
    }


def tfidf_vector(tokens: Sequence[str], idf: Dict[str, float]) -> Dict[str, float]:
    """L2-normalized TF-IDF vector keyed by term."""
    if not tokens:
        return {}
    tf = Counter(tokens)
    total = float(len(tokens))
    vec = {
        term: (count / total) * idf.get(term, 1.0)
        for term, count in tf.items()
        if term in idf  # drop OOV terms so cosine is well-defined
    }
    norm = math.sqrt(sum(v * v for v in vec.values()))
    if norm == 0:
        return vec
    return {k: v / norm for k, v in vec.items()}


def cosine_sim(a: Dict[str, float], b: Dict[str, float]) -> float:
    """Cosine similarity of two sparse L2-normalized vectors."""
    if not a or not b:
        return 0.0
    # iterate over the smaller dict for speed
    if len(b) < len(a):
        a, b = b, a
    return sum(v * b.get(k, 0.0) for k, v in a.items())


def pairwise_similarities(
    documents: Iterable[Tuple[int, str]],
    *,
    min_strength: float = 0.08,
    top_k: int | None = None,
) -> List[Tuple[int, int, float]]:
    """Return list of (source_id, target_id, strength) for notes with cosine
    similarity above `min_strength`. If `top_k` is set, each note keeps at
    most top_k strongest outgoing neighbours (before canonicalization)."""
    docs = list(documents)
    tokens = [(nid, tokenize(text)) for nid, text in docs]
    idf = build_idf([toks for _, toks in tokens])
    vectors = {nid: tfidf_vector(toks, idf) for nid, toks in tokens}

    ids = [nid for nid, _ in tokens]
    edges: List[Tuple[int, int, float]] = []

    for i, src in enumerate(ids):
        sims: List[Tuple[int, float]] = []
        for j, tgt in enumerate(ids):
            if i == j:
                continue
            s = cosine_sim(vectors[src], vectors[tgt])
            if s >= min_strength:
                sims.append((tgt, s))
        sims.sort(key=lambda x: x[1], reverse=True)
        if top_k is not None:
            sims = sims[:top_k]
        for tgt, s in sims:
            # canonicalize direction to dedupe
            a, b = (src, tgt) if src < tgt else (tgt, src)
            edges.append((a, b, round(s, 4)))

    # dedupe canonical pairs, keep max strength if duplicated
    seen: Dict[Tuple[int, int], float] = {}
    for a, b, s in edges:
        key = (a, b)
        if s > seen.get(key, 0.0):
            seen[key] = s
    return [(a, b, s) for (a, b), s in seen.items()]
