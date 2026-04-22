"""Per-model pricing table (USD per 1M tokens) and cost estimation.

Prices are list prices published by providers. Update freely — used only
for dev-facing cost estimates in the Arena / single-chat response and are
not guaranteed to match billed amounts (discounts, batching, caching, etc.).

Matching is prefix-based and case-insensitive, so `gpt-4o-2024-11-20`
still resolves via the `gpt-4o` entry. When no match is found we fall
back to a conservative default so the UI always has something to show.
"""
from __future__ import annotations

from typing import Dict, Tuple

# (input_per_1M, output_per_1M) in USD
_PRICES: Dict[str, Tuple[float, float]] = {
    # OpenAI
    "gpt-4.1":          (2.00, 8.00),
    "gpt-4.1-mini":     (0.40, 1.60),
    "gpt-4.1-nano":     (0.10, 0.40),
    "gpt-4.5":          (75.00, 150.00),
    "gpt-4o-mini":      (0.15, 0.60),
    "gpt-4o":           (2.50, 10.00),
    "gpt-4-turbo":      (10.00, 30.00),
    "gpt-4":            (30.00, 60.00),
    "gpt-3.5-turbo":    (0.50, 1.50),
    "o1-preview":       (15.00, 60.00),
    "o1-mini":          (3.00, 12.00),
    "o1":               (15.00, 60.00),
    "o3-mini":          (1.10, 4.40),
    "o3":               (2.00, 8.00),
    "o4-mini":          (1.10, 4.40),

    # Anthropic
    "claude-opus-4":            (15.00, 75.00),
    "claude-sonnet-4":          (3.00, 15.00),
    "claude-haiku-4":           (0.80, 4.00),
    "claude-3-5-sonnet":        (3.00, 15.00),
    "claude-3-5-haiku":         (0.80, 4.00),
    "claude-3-opus":            (15.00, 75.00),
    "claude-3-sonnet":          (3.00, 15.00),
    "claude-3-haiku":           (0.25, 1.25),

    # Google
    "gemini-2.0-flash":     (0.10, 0.40),
    "gemini-1.5-pro":       (1.25, 5.00),
    "gemini-1.5-flash":     (0.075, 0.30),
    "gemini-1.0-pro":       (0.50, 1.50),

    # Catch-all — used when no prefix matches
    "__default__":          (1.00, 3.00),
}


def _lookup(model: str) -> Tuple[float, float]:
    if not model:
        return _PRICES["__default__"]
    key = model.lower().strip()
    # Exact match first, then longest-prefix match.
    if key in _PRICES:
        return _PRICES[key]
    best = None
    best_len = 0
    for cand in _PRICES:
        if cand == "__default__":
            continue
        if key.startswith(cand) and len(cand) > best_len:
            best = cand
            best_len = len(cand)
    return _PRICES[best] if best else _PRICES["__default__"]


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Return estimated cost in USD for a single call."""
    pin, pout = _lookup(model or "")
    cost = (input_tokens or 0) * pin / 1_000_000 + (output_tokens or 0) * pout / 1_000_000
    return round(cost, 6)


def get_pricing_table() -> Dict[str, Dict[str, float]]:
    """Return a serializable view of the pricing table for the UI."""
    return {
        name: {"input_per_1m": pin, "output_per_1m": pout}
        for name, (pin, pout) in _PRICES.items()
        if name != "__default__"
    }
