// USD per 1,000,000 tokens. Kept roughly in sync with
// backend/src/services/pricing.py. Used for optimistic cost display
// before the backend's authoritative number comes back.
const MODEL_PRICING = {
  // OpenAI
  "gpt-4o":                       [2.50, 10.00],
  "gpt-4o-mini":                  [0.15,  0.60],
  "gpt-4.1":                      [2.00,  8.00],
  "gpt-4.1-mini":                 [0.40,  1.60],
  "gpt-4.1-nano":                 [0.10,  0.40],
  "gpt-4-turbo":                  [10.00, 30.00],
  "gpt-4":                        [30.00, 60.00],
  "gpt-3.5-turbo":                [0.50,  1.50],
  "o1-preview":                   [15.00, 60.00],
  "o1-mini":                      [3.00, 12.00],
  "o3-mini":                      [1.10,  4.40],
  "o3":                           [2.00,  8.00],
  "o4-mini":                      [1.10,  4.40],
  // Anthropic
  "claude-3-5-sonnet-20241022":   [3.00, 15.00],
  "claude-3-5-haiku-20241022":    [0.80,  4.00],
  "claude-3-opus-20240229":       [15.00, 75.00],
  "claude-3-sonnet-20240229":     [3.00, 15.00],
  "claude-3-haiku-20240307":      [0.25,  1.25],
  "claude-sonnet-4-6":            [3.00, 15.00],
  "claude-haiku-4-5-20251001":    [1.00,  5.00],
  "claude-opus-4-7":              [15.00, 75.00],
  // Google
  "gemini-2.0-flash-exp":         [0.10, 0.40],
  "gemini-1.5-pro":               [1.25, 5.00],
  "gemini-1.5-flash":             [0.075, 0.30],
  "gemini-1.0-pro":               [0.50, 1.50],
};

const PROVIDER_FALLBACK = {
  openai:    [2.50, 10.00],
  anthropic: [3.00, 15.00],
  google:    [1.25,  5.00],
  august:    [0.00,  0.00],
};

export function getRates(provider, model) {
  if (model && MODEL_PRICING[model]) return MODEL_PRICING[model];
  if (model) {
    for (const [known, rates] of Object.entries(MODEL_PRICING)) {
      if (model.startsWith(known)) return rates;
    }
  }
  return PROVIDER_FALLBACK[(provider || "").toLowerCase()] ?? [0, 0];
}

export function estimateCost(provider, model, inputTokens, outputTokens) {
  const [inR, outR] = getRates(provider, model);
  const inputCost  = (inputTokens  / 1_000_000) * inR;
  const outputCost = (outputTokens / 1_000_000) * outR;
  return {
    input_rate_per_1m:  inR,
    output_rate_per_1m: outR,
    input_cost_usd:     inputCost,
    output_cost_usd:    outputCost,
    total_cost_usd:     inputCost + outputCost,
  };
}

export function formatUsd(x) {
  if (x == null || Number.isNaN(x)) return "—";
  if (x === 0) return "$0";
  if (x < 0.0001)  return `$${x.toExponential(2)}`;
  if (x < 0.01)    return `$${x.toFixed(5)}`;
  if (x < 1)      return `$${x.toFixed(4)}`;
  return `$${x.toFixed(3)}`;
}
