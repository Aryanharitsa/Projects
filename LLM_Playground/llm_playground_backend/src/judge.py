"""LLM-as-judge auto-evaluation for the Arena.

Given an Arena run (a user prompt + N candidate responses), this module asks a
single chosen "judge" model to score every candidate against a rubric. The
output is structured: per-criterion scores (1-5), a weighted composite (0-100),
a one-line rationale, and a leaderboard.

The judge prompt is deliberately strict about the JSON shape it must emit, and
``parse_judge_response`` is paranoid — it will accept either a top-level array
or an object with ``verdicts``, scrub ```json fences, and clamp every score to
the rubric range so a misbehaving judge can't poison the UI.

Costs and latency for the judge call are returned alongside the verdicts so
the frontend can show the price-of-judgement next to the Arena's own total.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

from src.pricing import estimate_cost


# --- Default rubric --------------------------------------------------------

# Each criterion: name, short description, weight. Weights are normalised at
# scoring time so users can edit them without doing the math.
DEFAULT_RUBRIC: List[Dict[str, Any]] = [
    {
        "name": "Correctness",
        "description": "Are the claims, code, or reasoning factually right and free of fabrication?",
        "weight": 0.35,
    },
    {
        "name": "Completeness",
        "description": "Does the response cover every part of what the prompt asks for?",
        "weight": 0.20,
    },
    {
        "name": "Clarity",
        "description": "Is it well-structured, easy to follow, and free of jargon-soup?",
        "weight": 0.15,
    },
    {
        "name": "Conciseness",
        "description": "No padding, repetition, or filler — every sentence earns its place.",
        "weight": 0.15,
    },
    {
        "name": "Format",
        "description": "Adheres to the prompt's requested format / tone / language.",
        "weight": 0.15,
    },
]

SCORE_MIN, SCORE_MAX = 1, 5


# --- Prompt construction ---------------------------------------------------

JUDGE_SYSTEM = (
    "You are an impartial, calibrated evaluator of LLM responses. "
    "You compare candidate answers against a fixed rubric and return ONLY "
    "valid JSON in the exact shape requested. You do not flatter, you do not "
    "hedge, and you do not add commentary outside the JSON. Lower scores are "
    "expected for genuinely weak answers; do not cluster everything at 4-5."
)


def _normalize_rubric(rubric: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """Validate the rubric and re-normalise weights to sum to 1.0."""
    items = rubric or DEFAULT_RUBRIC
    cleaned: List[Dict[str, Any]] = []
    for r in items:
        name = (r.get("name") or "").strip()
        if not name:
            continue
        weight = float(r.get("weight") or 0)
        if weight < 0:
            weight = 0.0
        cleaned.append({
            "name": name,
            "description": (r.get("description") or "").strip(),
            "weight": weight,
        })
    if not cleaned:
        cleaned = [dict(r) for r in DEFAULT_RUBRIC]

    total = sum(r["weight"] for r in cleaned)
    if total <= 0:
        share = 1.0 / len(cleaned)
        for r in cleaned:
            r["weight"] = share
    else:
        for r in cleaned:
            r["weight"] = r["weight"] / total
    return cleaned


def build_judge_prompt(
    user_prompt: str,
    candidates: List[Dict[str, Any]],
    rubric: List[Dict[str, Any]],
    system_prompt: str = "",
) -> str:
    """Build the body the judge LLM sees. Candidates are anonymised by index."""
    rubric_block = "\n".join(
        f"  {i+1}. **{r['name']}** ({int(round(r['weight']*100))}%): {r['description']}"
        for i, r in enumerate(rubric)
    )
    crit_keys = [r["name"] for r in rubric]

    cand_blocks = []
    for i, c in enumerate(candidates):
        body = (c.get("response") or "").strip()
        if not body:
            body = "(empty response)"
        cand_blocks.append(
            f"--- CANDIDATE_{i} ---\n"
            f"provider: {c.get('provider', '?')}\n"
            f"model:    {c.get('model', '?')}\n"
            f"response:\n{body}"
        )

    schema_example = {
        "verdicts": [
            {
                "candidate": 0,
                "scores": {k: 4 for k in crit_keys},
                "rationale": "One short sentence explaining the score.",
            }
        ]
    }

    sys_line = f"\n[Original system prompt sent to all candidates]\n{system_prompt}\n" if system_prompt else ""

    return (
        "You are scoring LLM answers to the same prompt.\n"
        f"\n[User prompt]\n{user_prompt}\n"
        f"{sys_line}"
        f"\n[Rubric — score each criterion {SCORE_MIN}-{SCORE_MAX}]\n{rubric_block}\n"
        f"\n[Candidates]\n" + "\n\n".join(cand_blocks) +
        "\n\n[Output schema]\n"
        "Return ONLY a JSON object of the shape below. The `scores` object MUST "
        f"contain exactly these keys: {json.dumps(crit_keys)}. "
        f"Each score is an integer in [{SCORE_MIN},{SCORE_MAX}]. "
        "The `rationale` is one sentence (≤ 30 words).\n\n"
        f"{json.dumps(schema_example, indent=2)}\n"
    )


# --- Response parsing ------------------------------------------------------

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def _extract_json(text: str) -> Optional[Any]:
    """Find the first parseable JSON block in ``text``.

    Tolerates ```json fences, leading prose, and stray characters around the
    object. Returns ``None`` if nothing parses.
    """
    if not text:
        return None
    # Try fenced block first.
    m = _JSON_FENCE_RE.search(text)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    # Fall back to first balanced { ... } or [ ... ] in the raw text.
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        while start != -1:
            depth = 0
            for i in range(start, len(text)):
                ch = text[i]
                if ch == opener:
                    depth += 1
                elif ch == closer:
                    depth -= 1
                    if depth == 0:
                        chunk = text[start:i+1]
                        try:
                            return json.loads(chunk)
                        except json.JSONDecodeError:
                            break
            start = text.find(opener, start + 1)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def parse_judge_response(
    text: str,
    candidates: List[Dict[str, Any]],
    rubric: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Turn the judge's free-text JSON into a clamped, indexed verdict list.

    Always returns one verdict per candidate, in the original order — fills in
    a sentinel zero-scored verdict for any candidate the judge skipped.
    """
    parsed = _extract_json(text)
    raw_verdicts: List[Dict[str, Any]] = []
    if isinstance(parsed, dict) and isinstance(parsed.get("verdicts"), list):
        raw_verdicts = parsed["verdicts"]
    elif isinstance(parsed, list):
        raw_verdicts = parsed

    crit_keys = [r["name"] for r in rubric]
    by_index: Dict[int, Dict[str, Any]] = {}
    for v in raw_verdicts:
        if not isinstance(v, dict):
            continue
        idx = v.get("candidate")
        if not isinstance(idx, int) or idx < 0 or idx >= len(candidates):
            continue
        scores_in = v.get("scores") or {}
        scores: Dict[str, int] = {}
        for k in crit_keys:
            raw = scores_in.get(k)
            try:
                n = int(round(float(raw)))
            except (TypeError, ValueError):
                n = SCORE_MIN
            scores[k] = max(SCORE_MIN, min(SCORE_MAX, n))
        by_index[idx] = {
            "scores": scores,
            "rationale": (v.get("rationale") or "").strip()[:280],
        }

    verdicts: List[Dict[str, Any]] = []
    for i, cand in enumerate(candidates):
        if i in by_index:
            v = by_index[i]
        else:
            # Judge dropped this candidate — sentinel mid-low scores so the
            # composite is meaningful but visibly degraded.
            v = {
                "scores": {k: SCORE_MIN for k in crit_keys},
                "rationale": "(judge did not return a verdict for this candidate)",
            }
        composite = _composite(v["scores"], rubric)
        verdicts.append({
            "candidate": i,
            "provider": cand.get("provider"),
            "model": cand.get("model"),
            "scores": v["scores"],
            "rationale": v["rationale"],
            "composite": composite,
        })
    return verdicts


def _composite(scores: Dict[str, int], rubric: List[Dict[str, Any]]) -> int:
    """Weighted composite scaled to 0-100."""
    if not rubric:
        return 0
    total = 0.0
    for r in rubric:
        s = scores.get(r["name"], SCORE_MIN)
        # Map [SCORE_MIN, SCORE_MAX] -> [0, 1]
        norm = (s - SCORE_MIN) / max(1, (SCORE_MAX - SCORE_MIN))
        total += norm * r["weight"]
    return int(round(total * 100))


# --- Orchestration --------------------------------------------------------

def judge_compare(
    user_prompt: str,
    system_prompt: str,
    candidates: List[Dict[str, Any]],
    judge_provider_name: str,
    judge_model: str,
    rubric: Optional[List[Dict[str, Any]]],
    provider_factory,
) -> Tuple[Dict[str, Any], int]:
    """Run the judge call and return ``(payload, http_status)``.

    ``candidates`` items must each carry ``{provider, model, response}``. The
    function tolerates non-success siblings — they're scored from their stub
    "(empty response)" body, so a failed candidate naturally lands at the
    bottom of the leaderboard.
    """
    if not candidates:
        return {"success": False, "error": "No candidates to judge"}, 400
    if not user_prompt:
        return {"success": False, "error": "No user prompt provided"}, 400

    norm_rubric = _normalize_rubric(rubric)

    try:
        judge_instance = provider_factory.create_provider(judge_provider_name)
    except Exception as e:
        return {"success": False, "error": f"Judge provider unavailable: {e}"}, 400
    if not judge_instance:
        return {"success": False, "error": f"Provider {judge_provider_name} not available"}, 400

    body = build_judge_prompt(user_prompt, candidates, norm_rubric, system_prompt)
    messages = [
        {"role": "system", "content": JUDGE_SYSTEM},
        {"role": "user",   "content": body},
    ]

    import time
    started = time.time()
    try:
        resp = judge_instance.make_request(judge_model, messages)
    except Exception as e:
        return {"success": False, "error": f"Judge call failed: {e}"}, 502
    elapsed = round(time.time() - started, 3)

    error = resp.get("error")
    if resp.get("status") != "success" or (isinstance(error, dict) and error):
        msg = error.get("message") if isinstance(error, dict) else (error or "Judge upstream error")
        return {"success": False, "error": msg}, 502

    raw_text = resp.get("content", "") or ""
    verdicts = parse_judge_response(raw_text, candidates, norm_rubric)

    leaderboard = sorted(
        [{"candidate": v["candidate"], "model": v["model"], "provider": v["provider"], "composite": v["composite"]}
         for v in verdicts],
        key=lambda v: -v["composite"],
    )
    winner_idx = leaderboard[0]["candidate"] if leaderboard else None

    in_tok = resp.get("input_tokens", 0) or 0
    out_tok = resp.get("output_tokens", 0) or 0

    return {
        "success": True,
        "rubric": norm_rubric,
        "verdicts": verdicts,
        "leaderboard": leaderboard,
        "winner": winner_idx,
        "judge": {
            "provider": judge_provider_name,
            "model": judge_model,
            "latency": elapsed,
            "input_tokens": in_tok,
            "output_tokens": out_tok,
            "total_tokens": in_tok + out_tok,
            "cost_usd": estimate_cost(judge_model, in_tok, out_tok),
        },
        "raw_judge_text": raw_text,
    }, 200
