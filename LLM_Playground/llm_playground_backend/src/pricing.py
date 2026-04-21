"""Per-model token pricing used by /api/compare for cost rollups.

USD per 1,000,000 tokens (input / output). These are published best-effort
rates and should be treated as estimates — surfaced to users with a
'pricing estimate' disclaimer in the UI.

Lookup is exact-key first, then longest-prefix match so dated model variants
(claude-3-5-sonnet-20241022, gemini-2.0-flash-exp, ...) resolve cleanly.
"""
from __future__ import annotations

from typing import Any, Dict, Optional


PRICING_TABLE: Dict[str, Dict[str, Dict[str, float]]] = {
    "openai": {
        "gpt-4o":              {"input": 2.50,  "output": 10.00},
        "gpt-4o-mini":         {"input": 0.15,  "output": 0.60},
        "gpt-4-turbo":         {"input": 10.00, "output": 30.00},
        "gpt-4-turbo-preview": {"input": 10.00, "output": 30.00},
        "gpt-4.1":             {"input": 2.00,  "output": 8.00},
        "gpt-4.5":             {"input": 5.00,  "output": 15.00},
        "gpt-4":               {"input": 30.00, "output": 60.00},
        "gpt-3.5-turbo":       {"input": 0.50,  "output": 1.50},
        "gpt-3.5-turbo-16k":   {"input": 3.00,  "output": 4.00},
        "o1-preview":          {"input": 15.00, "output": 60.00},
        "o1-mini":             {"input": 3.00,  "output": 12.00},
        "o3-preview":          {"input": 15.00, "output": 60.00},
        "o3-mini":             {"input": 1.10,  "output": 4.40},
    },
    "anthropic": {
        "claude-3-5-sonnet":   {"input": 3.00,  "output": 15.00},
        "claude-3-5-haiku":    {"input": 0.80,  "output": 4.00},
        "claude-3-opus":       {"input": 15.00, "output": 75.00},
        "claude-3-sonnet":     {"input": 3.00,  "output": 15.00},
        "claude-3-haiku":      {"input": 0.25,  "output": 1.25},
    },
    "google": {
        "gemini-2.0-flash":    {"input": 0.10,  "output": 0.40},
        "gemini-1.5-pro":      {"input": 1.25,  "output": 5.00},
        "gemini-1.5-flash":    {"input": 0.075, "output": 0.30},
        "gemini-1.0-pro":      {"input": 0.50,  "output": 1.50},
    },
}

# Allow callers to pass "gemini" as a synonym for "google".
PRICING_TABLE["gemini"] = PRICING_TABLE["google"]


def get_pricing(provider: str, model: str) -> Optional[Dict[str, float]]:
    """Return the {input, output} pricing dict for a provider/model or None."""
    table = PRICING_TABLE.get((provider or "").lower())
    if not table:
        return None
    if model in table:
        return table[model]
    prefixes = [k for k in table if model.startswith(k)]
    if prefixes:
        prefixes.sort(key=len, reverse=True)
        return table[prefixes[0]]
    return None


def compute_cost(provider: str, model: str, input_tokens: int, output_tokens: int) -> Optional[float]:
    """Return USD cost for a call, or None when pricing is unknown.

    None is distinct from 0.0 so the UI can render an em-dash instead of '$0'.
    """
    p = get_pricing(provider, model)
    if not p:
        return None
    cost = (input_tokens / 1_000_000.0) * p["input"] + (output_tokens / 1_000_000.0) * p["output"]
    return round(cost, 6)


def pricing_catalog() -> Dict[str, Any]:
    """Public catalog safe to ship to the frontend."""
    return {k: v for k, v in PRICING_TABLE.items() if k != "gemini"}
