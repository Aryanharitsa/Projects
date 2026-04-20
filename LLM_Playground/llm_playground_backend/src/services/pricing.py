"""
Pricing table + cost calculator for LLM providers.

Prices are USD per 1,000,000 tokens (input / output). When a specific model
isn't listed we fall back to a conservative provider default so the playground
still returns a cost estimate rather than zero.

Keep this in rough sync with:
    frontend/src/lib/pricing.js
"""

from typing import Dict, Tuple

# (input $/1M, output $/1M)
_MODEL_PRICING: Dict[str, Tuple[float, float]] = {
    # ---- OpenAI ----
    "gpt-4o":               (2.50, 10.00),
    "gpt-4o-mini":          (0.15,  0.60),
    "gpt-4.1":              (2.00,  8.00),
    "gpt-4.1-mini":         (0.40,  1.60),
    "gpt-4.1-nano":         (0.10,  0.40),
    "gpt-4-turbo":          (10.00, 30.00),
    "gpt-4":                (30.00, 60.00),
    "gpt-3.5-turbo":        (0.50,  1.50),
    "o1-preview":           (15.00, 60.00),
    "o1-mini":              (3.00, 12.00),
    "o3-mini":              (1.10,  4.40),
    "o3":                   (2.00,  8.00),
    "o4-mini":              (1.10,  4.40),

    # ---- Anthropic ----
    "claude-3-5-sonnet-20241022": (3.00, 15.00),
    "claude-3-5-haiku-20241022":  (0.80,  4.00),
    "claude-3-opus-20240229":     (15.00, 75.00),
    "claude-3-sonnet-20240229":   (3.00, 15.00),
    "claude-3-haiku-20240307":    (0.25,  1.25),
    "claude-sonnet-4-6":          (3.00, 15.00),
    "claude-haiku-4-5-20251001":  (1.00,  5.00),
    "claude-opus-4-7":            (15.00, 75.00),

    # ---- Google ----
    "gemini-2.0-flash-exp": (0.10, 0.40),
    "gemini-1.5-pro":       (1.25, 5.00),
    "gemini-1.5-flash":     (0.075, 0.30),
    "gemini-1.0-pro":       (0.50, 1.50),
}

# Per-provider fallbacks used when model id is unknown.
_PROVIDER_FALLBACK: Dict[str, Tuple[float, float]] = {
    "openai":    (2.50, 10.00),
    "anthropic": (3.00, 15.00),
    "google":    (1.25,  5.00),
    "august":    (0.00,  0.00),
}


def get_rates(provider: str, model: str) -> Tuple[float, float]:
    """Return (input_rate, output_rate) per 1M tokens."""
    if model in _MODEL_PRICING:
        return _MODEL_PRICING[model]
    # prefix match — e.g. "gpt-4o-2024-08-06" should resolve to "gpt-4o"
    for known, rates in _MODEL_PRICING.items():
        if model.startswith(known):
            return rates
    return _PROVIDER_FALLBACK.get((provider or "").lower(), (0.0, 0.0))


def compute_cost(provider: str, model: str,
                 input_tokens: int, output_tokens: int) -> Dict[str, float]:
    """Compute cost in USD for a run. All values rounded to 6 decimals."""
    in_rate, out_rate = get_rates(provider, model)
    input_cost  = (input_tokens  / 1_000_000.0) * in_rate
    output_cost = (output_tokens / 1_000_000.0) * out_rate
    total = input_cost + output_cost
    return {
        "input_rate_per_1m":  round(in_rate,     4),
        "output_rate_per_1m": round(out_rate,    4),
        "input_cost_usd":     round(input_cost,  6),
        "output_cost_usd":    round(output_cost, 6),
        "total_cost_usd":     round(total,       6),
    }
