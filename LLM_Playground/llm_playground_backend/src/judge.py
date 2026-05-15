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


# --- Multi-judge consensus -------------------------------------------------
#
# A single judge has known biases — self-preference, training-set leakage,
# format prejudice, "long answers must be better." The consensus engine fans
# out the *same* judge prompt to K different judges in parallel, then folds
# their verdicts into:
#
#   * per-candidate mean / std / min / max composite (with confidence bar)
#   * per-criterion mean and std across judges
#   * "winner_votes" — how many judges put this candidate at #1
#   * inter-judge agreement: Fleiss' kappa per-criterion + overall, plus the
#     mean per-candidate composite std as a fast "panel disagreement" signal
#   * per-judge agreement-with-panel flag (did your top pick match the
#     panel's mean-top pick?)
#
# Fan-out is via ThreadPoolExecutor — like /compare — so wall time is the
# slowest judge, not the sum. Failing judges are caught and surfaced under
# `judges_failed`; the consensus is computed from successful judges only,
# so a missing key never kills the panel.


def _stddev(xs: List[float]) -> float:
    """Sample standard deviation. Returns 0.0 for n < 2."""
    if len(xs) < 2:
        return 0.0
    mean = sum(xs) / len(xs)
    return (sum((x - mean) ** 2 for x in xs) / (len(xs) - 1)) ** 0.5


def _fleiss_kappa(matrix: List[List[int]], n_raters: int) -> Optional[float]:
    """Fleiss' kappa over a categorical rating matrix.

    ``matrix[i][j]`` = count of raters who placed item ``i`` in category ``j``.
    Assumes a constant number of raters per item. Returns ``None`` when the
    statistic is undefined (e.g. all raters in one category → P_e == 1).
    """
    N = len(matrix)
    if N == 0 or n_raters < 2 or not matrix[0]:
        return None
    K = len(matrix[0])
    n = n_raters
    # Per-item agreement.
    P_i = [(sum(c * c for c in row) - n) / (n * (n - 1)) for row in matrix]
    P_bar = sum(P_i) / N
    # Category marginals.
    p_j = [sum(matrix[i][j] for i in range(N)) / (N * n) for j in range(K)]
    P_e = sum(p * p for p in p_j)
    if abs(1 - P_e) < 1e-9:
        return None
    return round((P_bar - P_e) / (1 - P_e), 3)


def _aggregate_verdicts(
    judge_results: List[Dict[str, Any]],
    candidates: List[Dict[str, Any]],
    rubric: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Fold K per-judge verdict lists into one consensus list (one entry per
    candidate)."""
    crit_keys = [r["name"] for r in rubric]

    # Count how many judges put each candidate at #1.
    winner_count = {i: 0 for i in range(len(candidates))}
    for jr in judge_results:
        verdicts = jr.get("verdicts") or []
        if not verdicts:
            continue
        top = max(verdicts, key=lambda v: v["composite"])
        winner_count[top["candidate"]] = winner_count.get(top["candidate"], 0) + 1

    out: List[Dict[str, Any]] = []
    for i, cand in enumerate(candidates):
        composites: List[float] = []
        per_crit: Dict[str, List[int]] = {k: [] for k in crit_keys}
        rationales: List[Dict[str, str]] = []
        for jr in judge_results:
            verdicts = jr.get("verdicts") or []
            v = verdicts[i] if i < len(verdicts) else None
            if not v:
                continue
            composites.append(v["composite"])
            for k in crit_keys:
                per_crit[k].append(int(v["scores"].get(k, SCORE_MIN)))
            if v.get("rationale"):
                rationales.append({
                    "judge": f"{jr['provider']} · {jr['model']}",
                    "provider": jr["provider"],
                    "model": jr["model"],
                    "composite": v["composite"],
                    "text": v["rationale"],
                })

        out.append({
            "candidate": i,
            "provider": cand.get("provider"),
            "model": cand.get("model"),
            "composite_mean": round(sum(composites) / len(composites), 1) if composites else 0,
            "composite_std":  round(_stddev(composites), 1),
            "composite_min":  int(min(composites)) if composites else 0,
            "composite_max":  int(max(composites)) if composites else 0,
            "composite_values": [int(c) for c in composites],
            "per_criterion": {
                k: {
                    "mean":  round(sum(per_crit[k]) / len(per_crit[k]), 2) if per_crit[k] else 0,
                    "std":   round(_stddev(per_crit[k]), 2),
                    "votes": per_crit[k],
                }
                for k in crit_keys
            },
            "rationales":   rationales,
            "winner_votes": winner_count.get(i, 0),
            "n_judges":     len(composites),
        })
    return out


def _compute_agreement(
    judge_results: List[Dict[str, Any]],
    rubric: List[Dict[str, Any]],
    n_candidates: int,
) -> Dict[str, Any]:
    """Inter-judge agreement: Fleiss' kappa per-criterion + overall, plus
    panel-level disagreement (mean composite std) and per-judge flags."""
    crit_keys = [r["name"] for r in rubric]
    n_judges = len(judge_results)
    if n_judges < 2 or n_candidates == 0:
        return {"per_criterion": {}, "overall": {"fleiss_kappa": None}, "per_judge": []}

    cats = SCORE_MAX - SCORE_MIN + 1

    per_criterion: Dict[str, Dict[str, Any]] = {}
    for k in crit_keys:
        matrix = [[0] * cats for _ in range(n_candidates)]
        for jr in judge_results:
            verdicts = jr.get("verdicts") or []
            for i in range(min(n_candidates, len(verdicts))):
                s = verdicts[i]["scores"].get(k, SCORE_MIN)
                idx = max(0, min(cats - 1, int(s) - SCORE_MIN))
                matrix[i][idx] += 1
        kappa = _fleiss_kappa(matrix, n_judges)
        per_criterion[k] = {"fleiss_kappa": kappa}

    # Composite std per candidate (averaged → panel disagreement signal).
    composites_per_cand: List[List[float]] = [[] for _ in range(n_candidates)]
    for jr in judge_results:
        for i, v in enumerate(jr.get("verdicts") or []):
            if i < n_candidates:
                composites_per_cand[i].append(v["composite"])
    avg_std = (
        sum(_stddev(cs) for cs in composites_per_cand) / max(1, len(composites_per_cand))
    )

    # Panel mean → winner.
    panel_means = [
        sum(cs) / len(cs) if cs else 0.0 for cs in composites_per_cand
    ]
    panel_winner = panel_means.index(max(panel_means)) if panel_means else None

    per_judge: List[Dict[str, Any]] = []
    for jr in judge_results:
        verdicts = jr.get("verdicts") or []
        if not verdicts:
            continue
        their_top = max(verdicts, key=lambda v: v["composite"])
        per_judge.append({
            "provider":            jr["provider"],
            "model":               jr["model"],
            "judge":               f"{jr['provider']} · {jr['model']}",
            "their_top":           their_top["candidate"],
            "their_top_score":     their_top["composite"],
            "agrees_with_panel":   their_top["candidate"] == panel_winner,
        })

    kappas = [v["fleiss_kappa"] for v in per_criterion.values() if v["fleiss_kappa"] is not None]
    overall_kappa = round(sum(kappas) / len(kappas), 3) if kappas else None

    return {
        "per_criterion": per_criterion,
        "overall": {
            "fleiss_kappa":       overall_kappa,
            "mean_composite_std": round(avg_std, 1),
            "panel_winner":       panel_winner,
            "n_judges":           n_judges,
        },
        "per_judge": per_judge,
    }


def judge_consensus_compare(
    user_prompt: str,
    system_prompt: str,
    candidates: List[Dict[str, Any]],
    judges: List[Dict[str, str]],
    rubric: Optional[List[Dict[str, Any]]],
    provider_factory,
) -> Tuple[Dict[str, Any], int]:
    """Fan out the same judge prompt to K judges in parallel, aggregate verdicts,
    compute inter-judge agreement.

    ``judges``: list of ``{"provider": "...", "model": "..."}`` entries. Need ≥ 2.
    """
    if not candidates:
        return {"success": False, "error": "No candidates to judge"}, 400
    if not user_prompt:
        return {"success": False, "error": "No user prompt provided"}, 400
    if not judges or len(judges) < 2:
        return {"success": False, "error": "Need at least 2 judges for consensus"}, 400

    norm_rubric = _normalize_rubric(rubric)

    # The judge prompt is identical for every judge — build it once.
    body = build_judge_prompt(user_prompt, candidates, norm_rubric, system_prompt)
    messages = [
        {"role": "system", "content": JUDGE_SYSTEM},
        {"role": "user",   "content": body},
    ]

    import time as _t
    from concurrent.futures import ThreadPoolExecutor

    def _one_judge(j: Dict[str, str]) -> Dict[str, Any]:
        provider_name = (j.get("provider") or "").strip()
        model = (j.get("model") or "").strip()
        if not provider_name or not model:
            return {"success": False, "provider": provider_name, "model": model,
                    "error": "missing provider or model"}
        try:
            inst = provider_factory.create_provider(provider_name)
        except Exception as e:  # noqa: BLE001
            return {"success": False, "provider": provider_name, "model": model,
                    "error": f"provider unavailable: {e}"}
        if not inst:
            return {"success": False, "provider": provider_name, "model": model,
                    "error": f"provider {provider_name} not available"}
        t0 = _t.time()
        try:
            resp = inst.make_request(model, messages)
        except Exception as e:  # noqa: BLE001
            return {"success": False, "provider": provider_name, "model": model,
                    "error": str(e), "latency": round(_t.time() - t0, 3)}
        elapsed = round(_t.time() - t0, 3)
        if resp.get("status") != "success":
            err = resp.get("error")
            msg = err.get("message") if isinstance(err, dict) else (err or "judge upstream error")
            return {"success": False, "provider": provider_name, "model": model,
                    "error": msg, "latency": elapsed}
        raw = resp.get("content", "") or ""
        verdicts = parse_judge_response(raw, candidates, norm_rubric)
        in_tok = resp.get("input_tokens", 0) or 0
        out_tok = resp.get("output_tokens", 0) or 0
        return {
            "success":       True,
            "provider":      provider_name,
            "model":         model,
            "verdicts":      verdicts,
            "latency":       elapsed,
            "input_tokens":  in_tok,
            "output_tokens": out_tok,
            "total_tokens":  in_tok + out_tok,
            "cost_usd":      estimate_cost(model, in_tok, out_tok),
        }

    with ThreadPoolExecutor(max_workers=min(len(judges), 6)) as pool:
        results = list(pool.map(_one_judge, judges))

    ok = [r for r in results if r.get("success")]
    failed = [r for r in results if not r.get("success")]

    if not ok:
        return {
            "success": False,
            "error":   "All judges failed",
            "judges_failed": failed,
        }, 502

    consensus = _aggregate_verdicts(ok, candidates, norm_rubric)
    agreement = _compute_agreement(ok, norm_rubric, len(candidates))

    leaderboard = sorted(
        [
            {
                "candidate":       v["candidate"],
                "model":           v["model"],
                "provider":        v["provider"],
                "composite_mean":  v["composite_mean"],
                "composite_std":   v["composite_std"],
                "composite_min":   v["composite_min"],
                "composite_max":   v["composite_max"],
                "winner_votes":    v["winner_votes"],
                "n_judges":        v["n_judges"],
            }
            for v in consensus
        ],
        key=lambda v: (-v["composite_mean"], -v["winner_votes"]),
    )
    winner_idx = leaderboard[0]["candidate"] if leaderboard else None

    return {
        "success":   True,
        "rubric":    norm_rubric,
        "consensus": consensus,
        "leaderboard": leaderboard,
        "winner":      winner_idx,
        "agreement":   agreement,
        "judges": [
            {
                "provider":      r["provider"],
                "model":         r["model"],
                "latency":       r["latency"],
                "input_tokens":  r["input_tokens"],
                "output_tokens": r["output_tokens"],
                "total_tokens":  r["total_tokens"],
                "cost_usd":      r["cost_usd"],
                "verdicts":      r["verdicts"],
            }
            for r in ok
        ],
        "judges_failed": failed,
        "panel_meta": {
            "n_judges":           len(ok),
            "n_failed":           len(failed),
            "max_latency":        max((r.get("latency") or 0) for r in ok),
            "total_cost_usd":     sum((r.get("cost_usd") or 0) for r in ok),
            "total_input_tokens": sum((r.get("input_tokens") or 0) for r in ok),
            "total_output_tokens": sum((r.get("output_tokens") or 0) for r in ok),
        },
    }, 200
