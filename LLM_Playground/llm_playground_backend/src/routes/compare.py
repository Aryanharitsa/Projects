"""LLM Bench — parallel multi-model compare endpoint.

POST /api/compare runs one prompt across N targets concurrently, times each
call, and rolls up cost via src.pricing. Each provider is called via its
HTTP API directly so results are consistent regardless of the per-provider
`make_request` signature drift in src/providers/*.
"""
from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any, Dict, List

import requests
from flask import Blueprint, jsonify, request

from src.pricing import compute_cost, get_pricing, pricing_catalog

compare_bp = Blueprint("compare", __name__)


def _openai_call(model: str, system: str, messages: List[Dict[str, str]], params: Dict[str, Any]) -> Dict[str, Any]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")
    body_messages: List[Dict[str, str]] = []
    if system:
        body_messages.append({"role": "system", "content": system})
    body_messages.extend(messages)
    payload: Dict[str, Any] = {"model": model, "messages": body_messages}
    if "temperature" in params: payload["temperature"] = params["temperature"]
    if "top_p" in params: payload["top_p"] = params["top_p"]
    if "max_tokens" in params: payload["max_tokens"] = int(params["max_tokens"])
    r = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=90,
    )
    data = r.json()
    if r.status_code != 200:
        raise RuntimeError(data.get("error", {}).get("message") or f"HTTP {r.status_code}")
    choice = data["choices"][0]["message"].get("content", "") or ""
    usage = data.get("usage", {}) or {}
    return {
        "content": choice,
        "input_tokens": int(usage.get("prompt_tokens", 0) or 0),
        "output_tokens": int(usage.get("completion_tokens", 0) or 0),
        "model_version": data.get("model", model),
    }


def _anthropic_call(model: str, system: str, messages: List[Dict[str, str]], params: Dict[str, Any]) -> Dict[str, Any]:
    api_key = os.getenv("ANTHROPIC_API_KEY") or os.getenv("CLAUDE_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY (or CLAUDE_API_KEY) is not set")
    payload: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_tokens": int(params.get("max_tokens", 1024)),
    }
    if system:
        payload["system"] = system
    if "temperature" in params: payload["temperature"] = params["temperature"]
    if "top_p" in params: payload["top_p"] = params["top_p"]
    r = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=90,
    )
    data = r.json()
    if r.status_code != 200:
        raise RuntimeError(data.get("error", {}).get("message") or f"HTTP {r.status_code}")
    blocks = data.get("content") or []
    content = blocks[0].get("text", "") if blocks else ""
    usage = data.get("usage", {}) or {}
    return {
        "content": content,
        "input_tokens": int(usage.get("input_tokens", 0) or 0),
        "output_tokens": int(usage.get("output_tokens", 0) or 0),
        "model_version": data.get("model", model),
    }


def _gemini_call(model: str, system: str, messages: List[Dict[str, str]], params: Dict[str, Any]) -> Dict[str, Any]:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set")
    contents = []
    for m in messages:
        role = "user" if m.get("role") == "user" else "model"
        contents.append({"role": role, "parts": [{"text": m.get("content", "")}]})
    payload: Dict[str, Any] = {"contents": contents}
    if system:
        payload["systemInstruction"] = {"parts": [{"text": system}]}
    gc: Dict[str, Any] = {}
    if "temperature" in params: gc["temperature"] = params["temperature"]
    if "top_p" in params: gc["topP"] = params["top_p"]
    if "max_tokens" in params: gc["maxOutputTokens"] = int(params["max_tokens"])
    if gc:
        payload["generationConfig"] = gc
    r = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        params={"key": api_key},
        json=payload,
        timeout=90,
    )
    data = r.json()
    if r.status_code != 200:
        raise RuntimeError(data.get("error", {}).get("message") or f"HTTP {r.status_code}")
    content = ""
    cand = (data.get("candidates") or [{}])[0]
    parts = (cand.get("content") or {}).get("parts") or []
    if parts:
        content = parts[0].get("text", "")
    usage = data.get("usageMetadata") or {}
    return {
        "content": content,
        "input_tokens": int(usage.get("promptTokenCount", 0) or 0),
        "output_tokens": int(usage.get("candidatesTokenCount", 0) or 0),
        "model_version": model,
    }


_DISPATCH = {
    "openai": _openai_call,
    "anthropic": _anthropic_call,
    "google": _gemini_call,
    "gemini": _gemini_call,
}


def _run_one(spec: Dict[str, str], system: str, messages: List[Dict[str, str]], params: Dict[str, Any]) -> Dict[str, Any]:
    provider_label = spec.get("provider", "")
    provider_key = provider_label.lower()
    model = spec.get("model", "")
    pricing = get_pricing(provider_key, model)
    fn = _DISPATCH.get(provider_key)
    if fn is None:
        return {
            "provider": provider_label,
            "model": model,
            "status": "error",
            "error": f"Unsupported provider: {provider_label}",
            "content": "",
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "latency_s": 0.0,
            "cost_usd": None,
            "pricing": pricing,
        }
    started = time.perf_counter()
    try:
        out = fn(model, system, messages, params)
        elapsed = round(time.perf_counter() - started, 3)
        in_tok = out["input_tokens"]
        out_tok = out["output_tokens"]
        return {
            "provider": provider_label,
            "model": model,
            "status": "success",
            "error": None,
            "content": out["content"],
            "input_tokens": in_tok,
            "output_tokens": out_tok,
            "total_tokens": in_tok + out_tok,
            "latency_s": elapsed,
            "cost_usd": compute_cost(provider_key, model, in_tok, out_tok),
            "pricing": pricing,
            "model_version": out.get("model_version", model),
        }
    except Exception as exc:
        return {
            "provider": provider_label,
            "model": model,
            "status": "error",
            "error": str(exc),
            "content": "",
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "latency_s": round(time.perf_counter() - started, 3),
            "cost_usd": None,
            "pricing": pricing,
        }


@compare_bp.route("/compare", methods=["POST"])
def compare():
    data = request.get_json(silent=True) or {}
    prompt = (data.get("prompt") or "").strip()
    system = (data.get("system_prompt") or "").strip()
    targets: List[Dict[str, str]] = data.get("models") or []
    params: Dict[str, Any] = data.get("params") or {}

    if not prompt:
        return jsonify({"success": False, "error": "Field 'prompt' is required"}), 400
    if not isinstance(targets, list) or not targets:
        return jsonify({"success": False, "error": "Field 'models' must list at least one target"}), 400
    if len(targets) > 8:
        return jsonify({"success": False, "error": "Up to 8 models per benchmark"}), 400

    messages = [{"role": "user", "content": prompt}]
    started_at = datetime.utcnow().isoformat()
    wall_start = time.perf_counter()

    ordered: List[Any] = [None] * len(targets)
    with ThreadPoolExecutor(max_workers=min(8, len(targets))) as ex:
        futures = {ex.submit(_run_one, t, system, messages, params): i for i, t in enumerate(targets)}
        for fut in as_completed(futures):
            ordered[futures[fut]] = fut.result()

    results: List[Dict[str, Any]] = [r for r in ordered if r is not None]
    wall_elapsed = round(time.perf_counter() - wall_start, 3)

    successful = [r for r in results if r["status"] == "success"]
    summary: Dict[str, Any] = {}
    if successful:
        fastest = min(successful, key=lambda r: r["latency_s"])
        priced = [r for r in successful if r["cost_usd"] is not None]
        cheapest = min(priced, key=lambda r: r["cost_usd"]) if priced else None
        longest = max(successful, key=lambda r: r["output_tokens"])
        summary = {
            "fastest": {"provider": fastest["provider"], "model": fastest["model"], "latency_s": fastest["latency_s"]},
            "cheapest": (
                {"provider": cheapest["provider"], "model": cheapest["model"], "cost_usd": cheapest["cost_usd"]}
                if cheapest else None
            ),
            "most_output": {
                "provider": longest["provider"],
                "model": longest["model"],
                "output_tokens": longest["output_tokens"],
            },
            "total_cost_usd": round(sum((r["cost_usd"] or 0.0) for r in successful), 6),
            "wall_seconds": wall_elapsed,
            "success_count": len(successful),
            "error_count": len(results) - len(successful),
        }

    return jsonify({
        "success": True,
        "started_at": started_at,
        "wall_seconds": wall_elapsed,
        "results": results,
        "summary": summary,
    })


@compare_bp.route("/pricing", methods=["GET"])
def pricing():
    return jsonify({"success": True, "table": pricing_catalog()})
