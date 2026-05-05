"""Minimal stdlib-only LLM client.

The project's central promise is "zero deps, runs on your machine in a
minute." Pulling in `anthropic` or `openai` for one HTTP call would
break that. So this module ships a tiny pair of `urllib`-based clients
covering Anthropic Messages and OpenAI-compatible Chat Completions.

Resolution order for credentials:

    SYNAPSE_LLM_PROVIDER ∈ {anthropic, openai}        default: anthropic
    SYNAPSE_LLM_KEY                                   required to enable LLM mode
    SYNAPSE_LLM_MODEL                                 provider default if unset

Errors are deliberately *not* raised: a 5xx, a network timeout, or a
malformed response just yields ``None`` and the caller falls back to the
extractive answerer. We never let LLM availability gate the product.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass

DEFAULT_TIMEOUT_SEC = 25.0


@dataclass
class LLMResult:
    text: str
    raw: dict


def llm_available() -> bool:
    return bool(os.getenv("SYNAPSE_LLM_KEY"))


def llm_provider_label() -> str:
    provider = os.getenv("SYNAPSE_LLM_PROVIDER", "anthropic").lower()
    model = os.getenv("SYNAPSE_LLM_MODEL")
    if model:
        return f"{provider}/{model}"
    return provider


def call_llm(
    provider: str,
    key: str,
    model: str,
    system: str,
    user: str,
    max_tokens: int = 320,
    temperature: float = 0.2,
    timeout: float = DEFAULT_TIMEOUT_SEC,
) -> LLMResult | None:
    provider = (provider or "").lower().strip()
    try:
        if provider == "anthropic":
            return _call_anthropic(key, model, system, user, max_tokens, temperature, timeout)
        if provider == "openai":
            return _call_openai(key, model, system, user, max_tokens, temperature, timeout)
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return None
    return None


def _post_json(url: str, body: dict, headers: dict, timeout: float) -> dict | None:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = resp.read().decode("utf-8", errors="replace")
            return json.loads(payload)
    except urllib.error.HTTPError as e:
        # Best-effort: surface the body for debugging in stderr but don't
        # raise — we want graceful degradation.
        try:
            _ = e.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        return None
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        return None


def _call_anthropic(
    key: str,
    model: str,
    system: str,
    user: str,
    max_tokens: int,
    temperature: float,
    timeout: float,
) -> LLMResult | None:
    body = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }
    headers = {
        "Content-Type": "application/json",
        "x-api-key": key,
        "anthropic-version": "2023-06-01",
    }
    raw = _post_json("https://api.anthropic.com/v1/messages", body, headers, timeout)
    if not raw:
        return None
    # Response shape: { content: [{type:'text', text:'...'}, ...] }
    parts = raw.get("content") or []
    text_parts: list[str] = []
    for p in parts:
        if isinstance(p, dict) and p.get("type") == "text" and p.get("text"):
            text_parts.append(str(p["text"]))
    text = "\n".join(text_parts).strip()
    if not text:
        return None
    return LLMResult(text=text, raw=raw)


def _call_openai(
    key: str,
    model: str,
    system: str,
    user: str,
    max_tokens: int,
    temperature: float,
    timeout: float,
) -> LLMResult | None:
    body = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {key}",
    }
    raw = _post_json(
        "https://api.openai.com/v1/chat/completions", body, headers, timeout
    )
    if not raw:
        return None
    choices = raw.get("choices") or []
    if not choices:
        return None
    msg = (choices[0] or {}).get("message") or {}
    text = (msg.get("content") or "").strip()
    if not text:
        return None
    return LLMResult(text=text, raw=raw)
