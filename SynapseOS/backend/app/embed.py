"""Zero-dependency semantic embedder.

Design goals
------------
- Works offline, no model download, no GPU, no extra deps.
- Deterministic: the same text always maps to the same vector.
- Good enough for cosine similarity on short-to-medium notes.

Approach
--------
Feature hashing (a.k.a. the "hashing trick") over character n-grams *and*
word uni/bigrams, combined with a signed-hash projection to `DIM`
dimensions, L2-normalized. This is the same family of technique that
powers classic text classifiers (Vowpal Wabbit) and holds up surprisingly
well for similarity-style retrieval when embeddings from a real model
aren't available.

If you later swap in a real embedding model (OpenAI, sentence-transformers,
etc.), keep the `embed()` signature: `str -> list[float]` of length `DIM`.
The synapse engine only relies on cosine similarity in that vector space.
"""

from __future__ import annotations

import hashlib
import math
import re
from functools import lru_cache

DIM = 512

_WORD_RE = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> list[str]:
    """Return a bag of string features: words, bigrams, and char 4-grams."""
    lower = text.lower()
    words = _WORD_RE.findall(lower)
    feats: list[str] = []
    # word unigrams
    feats.extend(f"w:{w}" for w in words)
    # word bigrams capture phrase-level signal
    feats.extend(f"b:{a}_{b}" for a, b in zip(words, words[1:]))
    # char 4-grams give us robustness to typos / morphology
    padded = f"  {lower}  "
    for i in range(len(padded) - 3):
        feats.append(f"c:{padded[i : i + 4]}")
    return feats


def _hash(token: str) -> tuple[int, int]:
    """Return (bucket, sign) via a stable SHA1 hash."""
    h = hashlib.sha1(token.encode("utf-8")).digest()
    # first 4 bytes → bucket, next byte bit 0 → sign
    bucket = int.from_bytes(h[:4], "big") % DIM
    sign = 1 if (h[4] & 1) else -1
    return bucket, sign


@lru_cache(maxsize=1024)
def embed(text: str) -> tuple[float, ...]:
    """Embed `text` into a unit-length vector of length `DIM`.

    Returned as a tuple so it's hashable for the LRU cache. Callers that
    need a list can do `list(embed(text))`.
    """
    if not text or not text.strip():
        return tuple(0.0 for _ in range(DIM))

    vec = [0.0] * DIM
    for tok in _tokens(text):
        bucket, sign = _hash(tok)
        vec[bucket] += sign

    norm = math.sqrt(sum(x * x for x in vec))
    if norm == 0:
        return tuple(vec)
    inv = 1.0 / norm
    return tuple(x * inv for x in vec)


def cosine(a: tuple[float, ...] | list[float], b: tuple[float, ...] | list[float]) -> float:
    """Cosine similarity on equal-length vectors. Returns in [-1, 1]."""
    if len(a) != len(b):
        raise ValueError("vector dim mismatch")
    return sum(x * y for x, y in zip(a, b))
