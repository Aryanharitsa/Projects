"""
POST /api/compare
Run the same prompt against N (provider, model, params) combinations in
parallel, and return one unified payload with latency, tokens, and cost per
run — so the frontend can render a side-by-side comparison grid.

Request body:
{
  "system_prompt": "...",
  "messages": [{"role": "user", "content": "..."}, ...],
  "runs": [
    { "provider": "OpenAI",    "model": "gpt-4o-mini",
      "params": {"temperature": 0.7, "max_tokens": 500} },
    { "provider": "Anthropic", "model": "claude-3-5-haiku-20241022",
      "params": {"temperature": 0.7, "max_tokens": 500} }
  ]
}

Response body:
{
  "success": true,
  "results": [
    {
      "provider": "OpenAI",
      "model": "gpt-4o-mini",
      "content": "...",
      "status": "success",
      "error": null,
      "input_tokens": 23,
      "output_tokens": 147,
      "total_tokens": 170,
      "latency_sec": 1.31,
      "cost": { "input_cost_usd": ..., "output_cost_usd": ..., "total_cost_usd": ..., ... },
      "timestamp": "...",
      "request_id": "..."
    }, ...
  ],
  "summary": {
    "cheapest_index": 1, "fastest_index": 0,
    "total_cost_usd": 0.0034, "wall_clock_sec": 1.42
  }
}
"""

import os
import uuid
import traceback
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List

import requests
from flask import Blueprint, current_app, jsonify, request

from src.providers.provider_factory import ProviderFactory
from src.services.pricing import compute_cost

compare_bp = Blueprint("compare", __name__)

provider_factory = ProviderFactory()


def _run_single(run_spec: Dict[str, Any],
                base_messages: List[Dict[str, Any]],
                system_prompt: str) -> Dict[str, Any]:
    """Execute one run. Never raise — always return a structured result."""
    provider_name = run_spec.get("provider", "")
    model         = run_spec.get("model", "")
    request_id    = str(uuid.uuid4())
    start         = datetime.now()

    try:
        provider = provider_factory.create_provider(provider_name)
        if not provider:
            raise ValueError(f"Provider {provider_name} not available")

        messages = list(base_messages)
        if system_prompt:
            messages = [{"role": "system", "content": system_prompt}] + messages

        raw = provider.make_request(model, messages)
        elapsed = (datetime.now() - start).total_seconds()

        content       = raw.get("content", "") or ""
        input_tokens  = int(raw.get("input_tokens", 0) or 0)
        output_tokens = int(raw.get("output_tokens", 0) or 0)
        status        = raw.get("status", "success") if content else "error"
        error         = raw.get("error")
        if isinstance(error, dict):
            error = error.get("message")

        cost = compute_cost(provider_name, model, input_tokens, output_tokens)

        return {
            "provider":      provider_name,
            "model":         model,
            "content":       content,
            "status":        status,
            "error":         error,
            "input_tokens":  input_tokens,
            "output_tokens": output_tokens,
            "total_tokens":  input_tokens + output_tokens,
            "latency_sec":   round(elapsed, 3),
            "cost":          cost,
            "timestamp":     datetime.utcnow().isoformat(),
            "request_id":    request_id,
            "model_version": raw.get("model_version", model),
        }

    except Exception as exc:
        elapsed = (datetime.now() - start).total_seconds()
        current_app.logger.error(
            "compare run failed for %s/%s: %s", provider_name, model, exc)
        return {
            "provider":      provider_name,
            "model":         model,
            "content":       "",
            "status":        "error",
            "error":         str(exc),
            "input_tokens":  0,
            "output_tokens": 0,
            "total_tokens":  0,
            "latency_sec":   round(elapsed, 3),
            "cost":          compute_cost(provider_name, model, 0, 0),
            "timestamp":     datetime.utcnow().isoformat(),
            "request_id":    request_id,
            "model_version": model,
        }


@compare_bp.route("/compare", methods=["POST"])
def compare():
    data = request.get_json(silent=True) or {}
    runs: List[Dict[str, Any]] = data.get("runs") or []
    if not runs:
        return jsonify({"success": False,
                        "error": "At least one run is required"}), 400
    if len(runs) > 6:
        return jsonify({"success": False,
                        "error": "Max 6 runs per comparison"}), 400

    messages      = data.get("messages", []) or []
    system_prompt = data.get("system_prompt", "") or ""

    wall_start = datetime.now()
    results: List[Dict[str, Any]] = [None] * len(runs)  # type: ignore

    try:
        with ThreadPoolExecutor(max_workers=min(6, len(runs))) as pool:
            futures = {
                pool.submit(_run_single, spec, messages, system_prompt): i
                for i, spec in enumerate(runs)
            }
            for fut in as_completed(futures):
                i = futures[fut]
                results[i] = fut.result()
    except Exception:
        return jsonify({"success": False,
                        "error": traceback.format_exc()}), 500

    wall_clock = (datetime.now() - wall_start).total_seconds()

    successful = [r for r in results if r["status"] == "success"]
    summary = {
        "run_count":      len(results),
        "success_count":  len(successful),
        "total_cost_usd": round(sum(r["cost"]["total_cost_usd"]
                                    for r in results), 6),
        "wall_clock_sec": round(wall_clock, 3),
        "cheapest_index": (
            min(range(len(successful)),
                key=lambda i: successful[i]["cost"]["total_cost_usd"])
            if successful else None
        ),
        "fastest_index": (
            min(range(len(successful)),
                key=lambda i: successful[i]["latency_sec"])
            if successful else None
        ),
    }
    # remap summary indices from the successful subset back to the full list
    if summary["cheapest_index"] is not None:
        target = successful[summary["cheapest_index"]]["request_id"]
        summary["cheapest_index"] = next(
            i for i, r in enumerate(results) if r["request_id"] == target)
    if summary["fastest_index"] is not None:
        target = successful[summary["fastest_index"]]["request_id"]
        summary["fastest_index"] = next(
            i for i, r in enumerate(results) if r["request_id"] == target)

    return jsonify({"success": True, "results": results, "summary": summary})
