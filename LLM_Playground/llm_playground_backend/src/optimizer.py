"""Optimizer Studio — automated prompt evolution against a rubric.

Every other surface in the playground *evaluates* prompts (Arena fans them
out, Suites batches them across cases, Rubrics judges them); none of them
*improves* them. Optimizer closes that loop: given a base prompt + a set of
test cases + a Rubrics rubric to judge against, it evolves the prompt across
generations and surfaces the winners.

Design choices:

* **Mutations are deterministic.**  ``apply_mutation(prompt, kind, ctx)`` is a
  pure function — same input, same output. Reproducibility is sacred when a
  user wants to compare two runs side-by-side. LLM-driven rewrites (would be
  non-deterministic without seeding) live behind a separate flag for v2.
* **Scoring composes the existing rubric engine.** Every variant's response
  to every test case is judged by ``rubrics.judge_with_rubric`` so the
  composite math, anchor handling, and judgement log all stay consistent.
* **Live scoring is optional.** When no API key is set (or the user wants a
  fast preview), ``score_response_dryrun`` returns a deterministic 0-100
  composite from cheap heuristics (length sanity, keyword overlap with the
  case's expected answer if provided, structural cues) so the UI works
  end-to-end without spending money.
* **State is one table per concept.** ``optimizations`` (the run header
  with test cases inline), ``opt_variants`` (every candidate prompt with
  parent + mutation + per-case results), ``opt_generations`` (one row per
  generation snapshot so the lineage view can replay history). Same DB as
  ``rubrics`` / ``history`` so a single backup captures everything.
* **Synchronous orchestration.** Each generation is run in one HTTP call.
  Returns the freshly-computed variants and the new champion. Long-poll
  patterns and websockets are out of scope for v1 — generations are 4-8
  variants × 2-6 test cases, comfortably under a request timeout for the
  models we wire to.

Public surface (kept narrow):
``create_optimization``, ``list_optimizations``, ``get_optimization``,
``delete_optimization``, ``advance_generation``, ``promote_variant``,
``preview_mutations``, ``stats``, ``MUTATIONS``.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from typing import Any, Callable, Dict, List, Optional, Tuple

from src import history, rubrics
from src.pricing import estimate_cost

_DB_LOCK = history._DB_LOCK  # noqa: SLF001 — share the cross-table lock


@contextmanager
def _conn():
    with history._conn() as con:  # noqa: SLF001
        yield con


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS optimizations (
    id                 TEXT PRIMARY KEY,
    name               TEXT NOT NULL,
    description        TEXT,
    base_prompt        TEXT NOT NULL,
    rubric_id          TEXT,
    rubric_revision    INTEGER,
    judge_provider     TEXT,
    judge_model        TEXT,
    candidate_provider TEXT,
    candidate_model    TEXT,
    test_cases_json    TEXT NOT NULL,   -- list of {input, expected?, weight?}
    strategy_json      TEXT NOT NULL,   -- mutation pool + population + elite
    status             TEXT NOT NULL,   -- draft|running|complete|failed
    generations_done   INTEGER NOT NULL DEFAULT 0,
    target_generations INTEGER NOT NULL DEFAULT 4,
    champion_variant   TEXT,
    best_composite     REAL,
    base_composite     REAL,
    total_cost         REAL NOT NULL DEFAULT 0,
    dryrun             INTEGER NOT NULL DEFAULT 0,
    created_at         REAL NOT NULL,
    updated_at         REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS opt_variants (
    id              TEXT PRIMARY KEY,
    optimization_id TEXT NOT NULL,
    generation      INTEGER NOT NULL,
    parent_id       TEXT,
    prompt          TEXT NOT NULL,
    prompt_hash     TEXT NOT NULL,
    mutation_kind   TEXT NOT NULL,
    mutation_note   TEXT,
    avg_composite   REAL,
    min_composite   REAL,
    max_composite   REAL,
    cost_usd        REAL NOT NULL DEFAULT 0,
    latency         REAL NOT NULL DEFAULT 0,
    runs_json       TEXT,             -- per-case run rollup
    status          TEXT NOT NULL,     -- pending|complete|failed|champion
    error           TEXT,
    is_champion     INTEGER NOT NULL DEFAULT 0,
    is_elite        INTEGER NOT NULL DEFAULT 0,
    created_at      REAL NOT NULL,
    FOREIGN KEY (optimization_id) REFERENCES optimizations(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS opt_generations (
    id              TEXT PRIMARY KEY,
    optimization_id TEXT NOT NULL,
    generation      INTEGER NOT NULL,
    n_variants      INTEGER NOT NULL,
    best_composite  REAL,
    avg_composite   REAL,
    cost_usd        REAL NOT NULL DEFAULT 0,
    duration        REAL NOT NULL DEFAULT 0,
    champion_variant TEXT,
    note            TEXT,
    created_at      REAL NOT NULL,
    FOREIGN KEY (optimization_id) REFERENCES optimizations(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_opt_updated     ON optimizations(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_opt_status      ON optimizations(status);
CREATE INDEX IF NOT EXISTS idx_optv_opt_gen    ON opt_variants(optimization_id, generation);
CREATE INDEX IF NOT EXISTS idx_optv_score      ON opt_variants(optimization_id, avg_composite DESC);
CREATE INDEX IF NOT EXISTS idx_optg_opt        ON opt_generations(optimization_id, generation);
"""


def init_db() -> None:
    with _DB_LOCK, _conn() as con:
        con.executescript(_SCHEMA)


def _now() -> float:
    return time.time()


# ---------------------------------------------------------------------------
# Mutations
# ---------------------------------------------------------------------------
# Each mutation is a deterministic transform: ``(prompt, ctx) -> (new_prompt, note)``.
# ``ctx`` carries the optimization's test cases + parent metadata for any
# mutation that wants them (e.g. ``add_few_shot`` reads ``ctx["cases"]``).

_PERSONA_DOMAINS = {
    "code": "senior staff engineer with deep code review experience",
    "rag":  "rigorous research assistant who cites every claim from provided context",
    "support": "empathetic customer support specialist with five years on the front line",
    "creative": "accomplished editor who values voice, surprise, and economy of language",
    "general": "expert who explains complex ideas precisely and without hedging",
}


def _detect_domain(prompt: str) -> str:
    low = (prompt or "").lower()
    if any(k in low for k in ("code", "function", "bug", "compile", "refactor", "javascript", "python", "typescript")):
        return "code"
    if any(k in low for k in ("context", "passage", "document", "according to", "cite", "source")):
        return "rag"
    if any(k in low for k in ("customer", "ticket", "refund", "support", "user complain")):
        return "support"
    if any(k in low for k in ("story", "poem", "draft", "voice", "narrative", "character")):
        return "creative"
    return "general"


def _strip_leading_role(prompt: str) -> str:
    """Drop a leading 'You are ...' line so we don't stack roles redundantly."""
    lines = prompt.strip().splitlines()
    if lines and re.match(r"^(you are|act as)\b", lines[0].strip(), re.I):
        return "\n".join(lines[1:]).lstrip()
    return prompt


def _ensure_blank_line(text: str) -> str:
    return text if text.endswith("\n\n") else (text + ("\n\n" if not text.endswith("\n") else "\n"))


# Each entry: (kind, label, blurb, applicator)

def _mut_add_role(prompt: str, ctx: Dict[str, Any]) -> Tuple[str, str]:
    domain = _detect_domain(prompt)
    persona = _PERSONA_DOMAINS.get(domain, _PERSONA_DOMAINS["general"])
    body = _strip_leading_role(prompt)
    new = f"You are a {persona}.\n\n{body}"
    return new, f"Prepended an expert {domain} persona."


def _mut_step_by_step(prompt: str, ctx: Dict[str, Any]) -> Tuple[str, str]:
    if "step by step" in prompt.lower() or "step-by-step" in prompt.lower():
        return prompt, "step-by-step already present — left as-is"
    suffix = (
        "\n\nThink step by step before answering. First, restate what is being "
        "asked in your own words. Then reason through it. Finally, give a "
        "concise final answer on its own line, prefixed with 'Final answer:'."
    )
    return prompt.rstrip() + suffix, "Added explicit step-by-step + 'Final answer:' format."


def _mut_add_constraints(prompt: str, ctx: Dict[str, Any]) -> Tuple[str, str]:
    bullet = (
        "\n\nConstraints:\n"
        "- Be concise. Aim for under 180 words unless asked otherwise.\n"
        "- Lead with the answer, then justify.\n"
        "- If information is missing, state what you would need rather than guess."
    )
    return prompt.rstrip() + bullet, "Added length / structure / uncertainty constraints."


def _mut_few_shot(prompt: str, ctx: Dict[str, Any]) -> Tuple[str, str]:
    cases = [c for c in (ctx.get("cases") or []) if (c.get("expected") or "").strip()]
    if not cases:
        return prompt, "No expected outputs available — few-shot mutation skipped"
    pick = cases[:2]
    blocks = []
    for c in pick:
        cin = (c.get("input") or "").strip()
        cexp = (c.get("expected") or "").strip()
        if not cin or not cexp:
            continue
        blocks.append(f"Input: {cin}\nOutput: {cexp}")
    if not blocks:
        return prompt, "No usable examples — few-shot mutation skipped"
    section = "\n\nHere are examples of the expected format:\n\n" + "\n\n".join(blocks)
    section += "\n\nNow respond in the same format to the new input."
    return prompt.rstrip() + section, f"Added {len(blocks)} few-shot example(s) from test cases."


def _mut_simplify(prompt: str, ctx: Dict[str, Any]) -> Tuple[str, str]:
    """Shorten verbose prompts: drop adverbs, hedges, and duplicate sentences."""
    text = prompt.strip()
    # Drop common filler phrases.
    for phrase in (
        "Please ", "please ", "kindly ", "Kindly ", "if possible ", "in any way ",
        " just ", " really ", " very ", " basically ", " literally ",
    ):
        text = text.replace(phrase, " ")
    # Dedupe sentences.
    seen = set()
    out: List[str] = []
    for sent in re.split(r"(?<=[.!?])\s+", text):
        norm = sent.strip().lower()
        if not norm or norm in seen:
            continue
        seen.add(norm)
        out.append(sent.strip())
    new = re.sub(r"\s+", " ", " ".join(out)).strip()
    if new == prompt.strip():
        return prompt, "Nothing to simplify"
    return new, f"Simplified — {len(prompt)} → {len(new)} chars."


def _mut_structure_sections(prompt: str, ctx: Dict[str, Any]) -> Tuple[str, str]:
    body = _strip_leading_role(prompt).strip()
    framed = (
        "## Task\n"
        f"{body}\n\n"
        "## Context\n"
        "Use only the information provided in the user's message. Do not invent facts.\n\n"
        "## Output format\n"
        "Plain prose, no markdown headings in the answer itself. Maximum 200 words.\n"
    )
    return framed, "Restructured into Task / Context / Output-format sections."


def _mut_safety_check(prompt: str, ctx: Dict[str, Any]) -> Tuple[str, str]:
    suffix = (
        "\n\nBefore returning your answer, verify:\n"
        "1. Did you answer the actual question, not a related one?\n"
        "2. Are any factual claims you make actually supported?\n"
        "3. Is your answer the appropriate length for the question?\n"
        "If any check fails, revise before responding."
    )
    return prompt.rstrip() + suffix, "Added self-verification checklist."


def _mut_negative_constraints(prompt: str, ctx: Dict[str, Any]) -> Tuple[str, str]:
    suffix = (
        "\n\nDo NOT:\n"
        "- Apologise or use filler ('I'd be happy to', 'Certainly!').\n"
        "- Repeat the question back in your answer.\n"
        "- Use markdown headings unless explicitly asked.\n"
        "- Hedge with phrases like 'it depends' without then explaining what it depends on."
    )
    return prompt.rstrip() + suffix, "Added explicit anti-patterns (no filler / hedging / repeat)."


def _mut_anchor_guidance(prompt: str, ctx: Dict[str, Any]) -> Tuple[str, str]:
    """Inject the rubric's high-anchor descriptions directly into the prompt."""
    dims = ctx.get("rubric_dimensions") or []
    if not dims:
        return prompt, "No rubric dimensions visible — anchor guidance skipped"
    bullets = []
    for d in dims[:4]:
        top = (d.get("anchors") or {}).get("10", "").strip()
        if not top:
            continue
        bullets.append(f"- **{d.get('name')}**: {top}")
    if not bullets:
        return prompt, "Rubric anchors empty — guidance skipped"
    section = "\n\nThe ideal response satisfies all of these:\n" + "\n".join(bullets)
    return prompt.rstrip() + section, f"Surfaced {len(bullets)} rubric high-anchor target(s) in-prompt."


def _mut_grounding(prompt: str, ctx: Dict[str, Any]) -> Tuple[str, str]:
    suffix = (
        "\n\nBase every claim in your answer on facts you can defend. If you are "
        "uncertain about something, mark it with [uncertain] inline rather than "
        "omitting it or asserting it as fact."
    )
    return prompt.rstrip() + suffix, "Added grounding + [uncertain] tagging rule."


def _mut_one_shot_inverse(prompt: str, ctx: Dict[str, Any]) -> Tuple[str, str]:
    """Show the model what a *bad* answer looks like so it avoids that shape."""
    suffix = (
        "\n\nA poor answer to this prompt would be vague, hedged, or restate the "
        "question without progressing it. Do not produce that shape — answer "
        "the question directly and substantively."
    )
    return prompt.rstrip() + suffix, "Added a 'don't do this' antipattern target."


_MUTATION_REGISTRY: Dict[str, Dict[str, Any]] = {
    "add_role": {
        "label": "Add expert role",
        "blurb": "Prepend a domain-tuned persona so the model adopts the right voice.",
        "fn": _mut_add_role,
        "tag": "framing",
    },
    "step_by_step": {
        "label": "Force step-by-step",
        "blurb": "Append explicit reasoning steps + a 'Final answer:' line.",
        "fn": _mut_step_by_step,
        "tag": "reasoning",
    },
    "add_constraints": {
        "label": "Add length & structure constraints",
        "blurb": "Cap length, lead with answer, encourage uncertainty disclosure.",
        "fn": _mut_add_constraints,
        "tag": "format",
    },
    "few_shot": {
        "label": "Inject few-shot examples",
        "blurb": "Pull 1-2 test cases that have expected outputs and embed them.",
        "fn": _mut_few_shot,
        "tag": "calibration",
    },
    "simplify": {
        "label": "Simplify & deduplicate",
        "blurb": "Strip filler, hedges, and duplicate sentences.",
        "fn": _mut_simplify,
        "tag": "cleanup",
    },
    "structure_sections": {
        "label": "Section-frame (Task/Context/Output)",
        "blurb": "Restructure into explicit Task / Context / Output-format blocks.",
        "fn": _mut_structure_sections,
        "tag": "framing",
    },
    "safety_check": {
        "label": "Self-verification checklist",
        "blurb": "Add a pre-flight 3-point check the model runs before answering.",
        "fn": _mut_safety_check,
        "tag": "reasoning",
    },
    "negative_constraints": {
        "label": "Anti-patterns (no filler / no hedging)",
        "blurb": "Tell the model what NOT to do — common LLM failure modes.",
        "fn": _mut_negative_constraints,
        "tag": "format",
    },
    "anchor_guidance": {
        "label": "Inject rubric high-anchors",
        "blurb": "Show the model the rubric's 10/10 descriptions verbatim.",
        "fn": _mut_anchor_guidance,
        "tag": "calibration",
    },
    "grounding": {
        "label": "Grounding + [uncertain] tags",
        "blurb": "Demand defensible claims; tag low-confidence parts inline.",
        "fn": _mut_grounding,
        "tag": "reasoning",
    },
    "one_shot_inverse": {
        "label": "Antipattern callout",
        "blurb": "Describe what a bad answer looks like so the model avoids it.",
        "fn": _mut_one_shot_inverse,
        "tag": "framing",
    },
}


def mutation_catalog() -> List[Dict[str, Any]]:
    return [
        {
            "kind": kind,
            "label": meta["label"],
            "blurb": meta["blurb"],
            "tag": meta["tag"],
        }
        for kind, meta in _MUTATION_REGISTRY.items()
    ]


MUTATIONS = mutation_catalog()


def apply_mutation(prompt: str, kind: str, ctx: Optional[Dict[str, Any]] = None) -> Tuple[str, str]:
    meta = _MUTATION_REGISTRY.get(kind)
    if not meta:
        return prompt, f"unknown mutation '{kind}'"
    try:
        return meta["fn"](prompt, ctx or {})
    except Exception as exc:  # noqa: BLE001
        return prompt, f"mutation '{kind}' failed: {exc}"


def preview_all_mutations(prompt: str, ctx: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Render every mutation against ``prompt`` — drives the Setup-tab preview pane."""
    out = []
    for kind, meta in _MUTATION_REGISTRY.items():
        new, note = apply_mutation(prompt, kind, ctx)
        changed = (new.strip() != prompt.strip())
        out.append({
            "kind": kind,
            "label": meta["label"],
            "blurb": meta["blurb"],
            "tag": meta["tag"],
            "note": note,
            "prompt": new,
            "delta_chars": len(new) - len(prompt),
            "changed": changed,
        })
    return out


# ---------------------------------------------------------------------------
# Dry-run scoring — used when no API key is configured.
# ---------------------------------------------------------------------------

_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "to", "of", "in", "on", "for",
    "with", "as", "by", "is", "are", "was", "were", "be", "been", "being",
    "this", "that", "these", "those", "it", "its", "if", "then", "than",
    "so", "do", "does", "did", "have", "has", "had", "you", "your", "yours",
    "we", "us", "our", "they", "them", "their", "i", "me", "my",
}


def _tokens(text: str) -> List[str]:
    return [t for t in re.findall(r"[a-z0-9]+", (text or "").lower()) if t not in _STOPWORDS]


def score_response_dryrun(
    *,
    prompt: str,
    case_input: str,
    case_expected: str,
    response: str,
    dimensions: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Deterministic, cheap, key-free scoring used when ``dryrun=True``.

    The math: per dimension, blend (a) keyword overlap with expected_output,
    (b) presence of formatting cues the prompt added (e.g. "Final answer:"),
    (c) a length sanity proxy. We then run the same composite math the live
    judge uses so the UI gets consistent 0-100 numbers.
    """
    resp = (response or "").strip()
    exp = (case_expected or "").strip()
    in_tokens = set(_tokens(case_input))
    resp_tokens = set(_tokens(resp))
    exp_tokens = set(_tokens(exp))

    overlap_exp = (
        len(resp_tokens & exp_tokens) / max(1, len(exp_tokens))
        if exp_tokens else 0.0
    )
    overlap_in = (
        len(resp_tokens & in_tokens) / max(1, len(in_tokens))
        if in_tokens else 0.0
    )
    length_score = 0.0
    if resp:
        rlen = len(resp)
        # Ideal 100-800 chars; saturates outside.
        if rlen < 50:
            length_score = max(0.0, rlen / 50.0)
        elif rlen <= 800:
            length_score = 1.0
        else:
            length_score = max(0.3, 1.0 - (rlen - 800) / 2400.0)
    format_score = 0.0
    cues = [
        "final answer:", "task:", "output:", "context:",
        "you are", "[uncertain]", "**",
    ]
    if resp and any(c in resp.lower() for c in cues):
        format_score = 0.8
    elif resp:
        format_score = 0.4

    base = 0.55 * (overlap_exp or overlap_in) + 0.20 * length_score + 0.25 * format_score
    # Tiny deterministic per-dim jitter so all dims aren't identical.
    h = hashlib.md5((prompt + "|" + (case_input or "") + "|" + (resp or "")).encode()).digest()
    dim_verdicts: List[Dict[str, Any]] = []
    composite = 0.0
    for i, d in enumerate(dimensions):
        jitter = (h[i % len(h)] / 255.0 - 0.5) * 0.15
        per_dim = max(0.0, min(1.0, base + jitter))
        score = int(round(per_dim * 10))
        weight = int(d.get("weight") or 0)
        composite += (score / 10.0) * (weight / 100.0)
        dim_verdicts.append({
            "name": d["name"],
            "weight": weight,
            "score": score,
            "max_score": 10,
            "rationale": "Heuristic score: keyword overlap + length + structural cues (dry-run; no judge LLM was called).",
            "contribution": round((score / 10.0) * weight, 2),
        })
    return {
        "composite": round(composite * 100.0, 2),
        "scores": {d["name"]: dv["score"] for d, dv in zip(dimensions, dim_verdicts)},
        "rationales": {d["name"]: dv["rationale"] for d, dv in zip(dimensions, dim_verdicts)},
        "summary": "Dry-run heuristic score — install API keys for real judging.",
        "dim_verdicts": dim_verdicts,
        "parsed_ok": True,
    }


def _dryrun_response(prompt: str, case_input: str, mutation_kind: str) -> str:
    """Synthesize a plausible response in dry-run mode.

    We blend prompt-driven format cues (so format-aware scoring fires on the
    right variants) with light overlap on the case input, so different
    mutations actually produce different scores.
    """
    base = f"Considering '{case_input or 'the request'}', the answer is straightforward. "
    extras = []
    low = (prompt or "").lower()
    if "step by step" in low or "step-by-step" in low:
        extras.append("First, identify the goal. Next, work through the constraints. Final answer: see above.")
    if "final answer:" in low:
        extras.append("Final answer: per the steps above.")
    if "task:" in low or "## task" in low:
        extras.append("Task addressed. Context: from the input. Output format respected.")
    if "do not" in low or "no filler" in low:
        # respond more concisely
        base = base.replace("the answer is straightforward.", "the answer follows directly.")
    if "[uncertain]" in low:
        extras.append("This part is [uncertain].")
    if "ideal response" in low:
        extras.append("(Targeting the rubric's high-anchor.)")
    return base + " " + " ".join(extras)


# ---------------------------------------------------------------------------
# Live scoring via the existing provider + rubric pipeline.
# ---------------------------------------------------------------------------

def _score_variant_live(
    *,
    variant_prompt: str,
    cases: List[Dict[str, Any]],
    candidate_provider: str,
    candidate_model: str,
    judge_provider: str,
    judge_model: str,
    rubric_id: str,
    revision_num: Optional[int],
    provider_factory,
    parallel: int = 3,
) -> Dict[str, Any]:
    """Run ``variant_prompt`` against every case, judge each response."""
    if not candidate_provider or not candidate_model:
        return {"error": "candidate_provider and candidate_model are required in live mode"}
    if not judge_provider or not judge_model or not rubric_id:
        return {"error": "judge_provider, judge_model, and rubric_id are required in live mode"}

    try:
        cand = provider_factory.create_provider(candidate_provider)
    except Exception as exc:  # noqa: BLE001
        return {"error": f"candidate provider unavailable: {exc}"}
    if not cand:
        return {"error": f"candidate provider '{candidate_provider}' not available"}

    def _run_one(idx_case: Tuple[int, Dict[str, Any]]) -> Dict[str, Any]:
        idx, case = idx_case
        case_input = (case.get("input") or "").strip()
        case_expected = (case.get("expected") or "").strip()
        messages = [
            {"role": "system", "content": variant_prompt},
            {"role": "user", "content": case_input or "(no input)"},
        ]
        t0 = time.time()
        try:
            resp = cand.make_request(candidate_model, messages)
        except Exception as exc:  # noqa: BLE001
            return {
                "case_index": idx,
                "input": case_input,
                "expected": case_expected,
                "response": "",
                "composite": None,
                "cost_usd": 0.0,
                "latency": round(time.time() - t0, 3),
                "error": f"candidate call failed: {exc}",
            }
        err = resp.get("error")
        if resp.get("status") != "success" or (isinstance(err, dict) and err):
            msg = err.get("message") if isinstance(err, dict) else (err or "candidate upstream error")
            return {
                "case_index": idx,
                "input": case_input,
                "expected": case_expected,
                "response": "",
                "composite": None,
                "cost_usd": 0.0,
                "latency": round(time.time() - t0, 3),
                "error": msg,
            }
        content = (resp.get("content") or "").strip()
        in_tok = int(resp.get("input_tokens") or 0)
        out_tok = int(resp.get("output_tokens") or 0)
        cand_cost = float(estimate_cost(candidate_model, in_tok, out_tok) or 0.0)
        cand_latency = round(time.time() - t0, 3)
        # Judge
        try:
            jpayload, jstatus = rubrics.judge_with_rubric(
                rubric_id,
                user_prompt=case_input or "(no input)",
                response=content,
                judge_provider=judge_provider,
                judge_model=judge_model,
                system_prompt=variant_prompt,
                candidate_provider=candidate_provider,
                candidate_model=candidate_model,
                note=f"optimizer: case {idx}",
                provider_factory=provider_factory,
                persist=False,
                revision_num=revision_num,
            )
        except Exception as exc:  # noqa: BLE001
            return {
                "case_index": idx,
                "input": case_input,
                "expected": case_expected,
                "response": content,
                "composite": None,
                "cost_usd": cand_cost,
                "latency": cand_latency,
                "error": f"judge failed: {exc}",
            }
        if not jpayload.get("success"):
            return {
                "case_index": idx,
                "input": case_input,
                "expected": case_expected,
                "response": content,
                "composite": None,
                "cost_usd": cand_cost,
                "latency": cand_latency,
                "error": jpayload.get("error") or "judge returned no verdict",
            }
        return {
            "case_index": idx,
            "input": case_input,
            "expected": case_expected,
            "response": content,
            "composite": jpayload.get("composite"),
            "dim_verdicts": jpayload.get("dim_verdicts", []),
            "summary": jpayload.get("summary", ""),
            "cost_usd": cand_cost + float((jpayload.get("judge") or {}).get("cost_usd") or 0.0),
            "latency": cand_latency + float((jpayload.get("judge") or {}).get("latency") or 0.0),
            "input_tokens": in_tok,
            "output_tokens": out_tok,
            "parsed_ok": jpayload.get("parsed_ok", True),
        }

    runs: List[Dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max(1, min(parallel, 8))) as pool:
        futures = [pool.submit(_run_one, (i, c)) for i, c in enumerate(cases)]
        for fut in as_completed(futures):
            runs.append(fut.result())
    runs.sort(key=lambda r: r["case_index"])
    return _rollup_runs(runs)


def _score_variant_dryrun(
    *,
    variant_prompt: str,
    cases: List[Dict[str, Any]],
    dimensions: List[Dict[str, Any]],
    mutation_kind: str,
) -> Dict[str, Any]:
    runs: List[Dict[str, Any]] = []
    for idx, case in enumerate(cases):
        case_input = (case.get("input") or "").strip()
        case_expected = (case.get("expected") or "").strip()
        response = _dryrun_response(variant_prompt, case_input, mutation_kind)
        scored = score_response_dryrun(
            prompt=variant_prompt,
            case_input=case_input,
            case_expected=case_expected,
            response=response,
            dimensions=dimensions,
        )
        runs.append({
            "case_index": idx,
            "input": case_input,
            "expected": case_expected,
            "response": response,
            "composite": scored["composite"],
            "dim_verdicts": scored["dim_verdicts"],
            "summary": scored["summary"],
            "cost_usd": 0.0,
            "latency": 0.0,
            "input_tokens": 0,
            "output_tokens": 0,
            "parsed_ok": True,
        })
    return _rollup_runs(runs)


def _rollup_runs(runs: List[Dict[str, Any]]) -> Dict[str, Any]:
    composites = [r["composite"] for r in runs if r.get("composite") is not None]
    if not composites:
        return {
            "runs": runs,
            "avg_composite": None,
            "min_composite": None,
            "max_composite": None,
            "cost_usd": sum(float(r.get("cost_usd") or 0) for r in runs),
            "latency": sum(float(r.get("latency") or 0) for r in runs),
            "n_complete": 0,
            "n_total": len(runs),
        }
    return {
        "runs": runs,
        "avg_composite": round(sum(composites) / len(composites), 2),
        "min_composite": round(min(composites), 2),
        "max_composite": round(max(composites), 2),
        "cost_usd": round(sum(float(r.get("cost_usd") or 0) for r in runs), 6),
        "latency": round(sum(float(r.get("latency") or 0) for r in runs), 3),
        "n_complete": len(composites),
        "n_total": len(runs),
    }


# ---------------------------------------------------------------------------
# Optimization CRUD
# ---------------------------------------------------------------------------

def _row_to_opt(row: sqlite3.Row) -> Dict[str, Any]:
    try:
        cases = json.loads(row["test_cases_json"])
    except (TypeError, ValueError, json.JSONDecodeError):
        cases = []
    try:
        strat = json.loads(row["strategy_json"])
    except (TypeError, ValueError, json.JSONDecodeError):
        strat = {}
    return {
        "id": row["id"],
        "name": row["name"],
        "description": row["description"] or "",
        "base_prompt": row["base_prompt"],
        "rubric_id": row["rubric_id"] or "",
        "rubric_revision": row["rubric_revision"],
        "judge_provider": row["judge_provider"] or "",
        "judge_model": row["judge_model"] or "",
        "candidate_provider": row["candidate_provider"] or "",
        "candidate_model": row["candidate_model"] or "",
        "test_cases": cases,
        "strategy": strat,
        "status": row["status"],
        "generations_done": int(row["generations_done"] or 0),
        "target_generations": int(row["target_generations"] or 0),
        "champion_variant": row["champion_variant"] or "",
        "best_composite": row["best_composite"],
        "base_composite": row["base_composite"],
        "total_cost": float(row["total_cost"] or 0),
        "dryrun": bool(row["dryrun"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _row_to_variant(row: sqlite3.Row) -> Dict[str, Any]:
    try:
        runs = json.loads(row["runs_json"]) if row["runs_json"] else []
    except (TypeError, ValueError, json.JSONDecodeError):
        runs = []
    return {
        "id": row["id"],
        "optimization_id": row["optimization_id"],
        "generation": int(row["generation"]),
        "parent_id": row["parent_id"] or "",
        "prompt": row["prompt"],
        "prompt_hash": row["prompt_hash"],
        "mutation_kind": row["mutation_kind"],
        "mutation_note": row["mutation_note"] or "",
        "avg_composite": row["avg_composite"],
        "min_composite": row["min_composite"],
        "max_composite": row["max_composite"],
        "cost_usd": float(row["cost_usd"] or 0),
        "latency": float(row["latency"] or 0),
        "runs": runs,
        "status": row["status"],
        "error": row["error"] or "",
        "is_champion": bool(row["is_champion"]),
        "is_elite": bool(row["is_elite"]),
        "created_at": row["created_at"],
    }


def _row_to_generation(row: sqlite3.Row) -> Dict[str, Any]:
    return {
        "id": row["id"],
        "optimization_id": row["optimization_id"],
        "generation": int(row["generation"]),
        "n_variants": int(row["n_variants"]),
        "best_composite": row["best_composite"],
        "avg_composite": row["avg_composite"],
        "cost_usd": float(row["cost_usd"] or 0),
        "duration": float(row["duration"] or 0),
        "champion_variant": row["champion_variant"] or "",
        "note": row["note"] or "",
        "created_at": row["created_at"],
    }


_DEFAULT_STRATEGY = {
    "population": 4,
    "elite": 1,
    "mutations": [
        "add_role", "step_by_step", "add_constraints",
        "structure_sections", "few_shot", "anchor_guidance",
    ],
}


def _normalise_strategy(strategy: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    s = dict(_DEFAULT_STRATEGY)
    if isinstance(strategy, dict):
        if isinstance(strategy.get("population"), int):
            s["population"] = max(1, min(12, int(strategy["population"])))
        if isinstance(strategy.get("elite"), int):
            s["elite"] = max(0, min(s["population"], int(strategy["elite"])))
        if isinstance(strategy.get("mutations"), list):
            kept = [m for m in strategy["mutations"] if m in _MUTATION_REGISTRY]
            if kept:
                s["mutations"] = kept
    return s


def _normalise_cases(cases: Any) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not isinstance(cases, list):
        return out
    for c in cases:
        if not isinstance(c, dict):
            continue
        inp = (c.get("input") or "").strip()
        if not inp:
            continue
        out.append({
            "input": inp[:2000],
            "expected": (c.get("expected") or "").strip()[:2000],
            "weight": float(c.get("weight") or 1.0),
        })
    return out[:20]


def create_optimization(
    *,
    name: str,
    base_prompt: str,
    description: str = "",
    rubric_id: str = "",
    rubric_revision: Optional[int] = None,
    judge_provider: str = "",
    judge_model: str = "",
    candidate_provider: str = "",
    candidate_model: str = "",
    test_cases: List[Dict[str, Any]],
    target_generations: int = 3,
    strategy: Optional[Dict[str, Any]] = None,
    dryrun: bool = False,
) -> Dict[str, Any]:
    init_db()
    name = (name or "").strip()
    if not name:
        raise ValueError("name is required")
    base = (base_prompt or "").strip()
    if not base:
        raise ValueError("base_prompt is required")
    cases = _normalise_cases(test_cases)
    if not cases:
        raise ValueError("at least one non-empty test case is required")
    strat = _normalise_strategy(strategy)
    target = max(1, min(8, int(target_generations or 1)))
    oid = uuid.uuid4().hex
    now = _now()
    with _DB_LOCK, _conn() as con:
        con.execute(
            """INSERT INTO optimizations
                 (id, name, description, base_prompt,
                  rubric_id, rubric_revision,
                  judge_provider, judge_model,
                  candidate_provider, candidate_model,
                  test_cases_json, strategy_json,
                  status, generations_done, target_generations,
                  champion_variant, best_composite, base_composite,
                  total_cost, dryrun,
                  created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'draft', 0, ?, NULL, NULL, NULL, 0, ?, ?, ?)""",
            (oid, name, description.strip(), base,
             rubric_id or None, rubric_revision,
             judge_provider or None, judge_model or None,
             candidate_provider or None, candidate_model or None,
             json.dumps(cases), json.dumps(strat),
             target, 1 if dryrun else 0, now, now),
        )
    return get_optimization(oid) or {}


def list_optimizations(
    *,
    q: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> Tuple[List[Dict[str, Any]], int]:
    init_db()
    clauses: List[str] = []
    params: List[Any] = []
    if q:
        clauses.append("(LOWER(name) LIKE ? OR LOWER(description) LIKE ?)")
        like = f"%{q.lower().strip()}%"
        params.extend([like, like])
    if status:
        clauses.append("status = ?")
        params.append(status)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    with _DB_LOCK, _conn() as con:
        total = con.execute(f"SELECT COUNT(*) AS c FROM optimizations {where}", params).fetchone()["c"]
        rows = con.execute(
            f"""SELECT * FROM optimizations
                {where}
                ORDER BY updated_at DESC
                LIMIT ? OFFSET ?""",
            (*params, int(limit), int(offset)),
        ).fetchall()
        out: List[Dict[str, Any]] = []
        for row in rows:
            opt = _row_to_opt(row)
            opt["n_variants"] = int(con.execute(
                "SELECT COUNT(*) AS c FROM opt_variants WHERE optimization_id = ?",
                (opt["id"],),
            ).fetchone()["c"])
            out.append(opt)
        return out, int(total)


def get_optimization(opt_id: str) -> Optional[Dict[str, Any]]:
    init_db()
    with _DB_LOCK, _conn() as con:
        row = con.execute("SELECT * FROM optimizations WHERE id = ?", (opt_id,)).fetchone()
        if not row:
            return None
        opt = _row_to_opt(row)
        vrows = con.execute(
            "SELECT * FROM opt_variants WHERE optimization_id = ? ORDER BY generation ASC, avg_composite DESC NULLS LAST",
            (opt_id,),
        ).fetchall()
        opt["variants"] = [_row_to_variant(r) for r in vrows]
        grows = con.execute(
            "SELECT * FROM opt_generations WHERE optimization_id = ? ORDER BY generation ASC",
            (opt_id,),
        ).fetchall()
        opt["generations"] = [_row_to_generation(r) for r in grows]
        # Convenience rollups
        opt["n_variants"] = len(opt["variants"])
        completed = [v for v in opt["variants"] if v.get("avg_composite") is not None]
        if completed:
            best = max(completed, key=lambda v: v["avg_composite"])
            opt["best_variant_id"] = best["id"]
        else:
            opt["best_variant_id"] = ""
        return opt


def delete_optimization(opt_id: str) -> bool:
    init_db()
    with _DB_LOCK, _conn() as con:
        con.execute("DELETE FROM opt_variants WHERE optimization_id = ?", (opt_id,))
        con.execute("DELETE FROM opt_generations WHERE optimization_id = ?", (opt_id,))
        cur = con.execute("DELETE FROM optimizations WHERE id = ?", (opt_id,))
        return cur.rowcount > 0


def promote_variant(opt_id: str, variant_id: str) -> Optional[Dict[str, Any]]:
    """Mark a variant as the champion (canonical 'use this' pick)."""
    init_db()
    with _DB_LOCK, _conn() as con:
        v = con.execute(
            "SELECT * FROM opt_variants WHERE id = ? AND optimization_id = ?",
            (variant_id, opt_id),
        ).fetchone()
        if not v:
            return None
        con.execute(
            "UPDATE opt_variants SET is_champion = 0 WHERE optimization_id = ?",
            (opt_id,),
        )
        con.execute(
            "UPDATE opt_variants SET is_champion = 1, status = 'champion' WHERE id = ?",
            (variant_id,),
        )
        con.execute(
            """UPDATE optimizations
               SET champion_variant = ?, best_composite = ?, updated_at = ?
               WHERE id = ?""",
            (variant_id, v["avg_composite"], _now(), opt_id),
        )
    return get_optimization(opt_id)


# ---------------------------------------------------------------------------
# Generation orchestrator — this is the heart of the engine.
# ---------------------------------------------------------------------------

def _seed_population(
    base_prompt: str,
    base_avg: Optional[float],
    base_variant_id: str,
    cases: List[Dict[str, Any]],
    rubric_dims: List[Dict[str, Any]],
    strategy: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Generation 1: apply every chosen mutation directly to the base prompt."""
    mutations = strategy["mutations"]
    plan = []
    for i in range(strategy["population"]):
        kind = mutations[i % len(mutations)]
        new, note = apply_mutation(base_prompt, kind, {
            "cases": cases,
            "rubric_dimensions": rubric_dims,
        })
        plan.append({
            "prompt": new,
            "mutation_kind": kind,
            "mutation_note": note,
            "parent_id": base_variant_id,
        })
    return plan


def _evolve_population(
    *,
    elites: List[Dict[str, Any]],
    base_prompt: str,
    cases: List[Dict[str, Any]],
    rubric_dims: List[Dict[str, Any]],
    strategy: Dict[str, Any],
    used_hashes: set,
) -> List[Dict[str, Any]]:
    """Subsequent generations: mutate the elites, fill remaining slots with
    mutations of the base or other survivors. Deterministic: order of
    (parent × mutation) pairings is fixed by the elite scores so a re-run of
    the same opt is reproducible."""
    mutations = strategy["mutations"]
    pop_size = strategy["population"]
    plan: List[Dict[str, Any]] = []
    pool = elites or []
    if not pool:
        # Fallback to the base prompt if every elite somehow failed.
        pool = [{"id": "", "prompt": base_prompt, "avg_composite": 0}]
    i = 0
    while len(plan) < pop_size and i < pop_size * 4:
        parent = pool[i % len(pool)]
        kind = mutations[(i // len(pool)) % len(mutations)]
        new, note = apply_mutation(parent["prompt"], kind, {
            "cases": cases,
            "rubric_dimensions": rubric_dims,
        })
        # Avoid emitting the exact same prompt twice — falls back to a different
        # mutation kind if the chosen one was a no-op for this parent.
        h = hashlib.sha1(new.strip().encode()).hexdigest()[:16]
        if h in used_hashes:
            i += 1
            continue
        used_hashes.add(h)
        plan.append({
            "prompt": new,
            "mutation_kind": kind,
            "mutation_note": note,
            "parent_id": parent.get("id", ""),
        })
        i += 1
    return plan


def advance_generation(
    opt_id: str,
    *,
    provider_factory,
    parallel: int = 3,
) -> Tuple[Dict[str, Any], int]:
    """Run *one* generation of evolution and persist results.

    Steps:
      1. If gen 0 hasn't happened, score the base prompt (it becomes the
         champion to beat).
      2. Build the next population from elite survivors + mutations.
      3. Score each new variant (live or dry-run depending on opt.dryrun).
      4. Persist variants + a generation snapshot row.
      5. Mark the top variant as the new champion if it beats prior best.
    """
    init_db()
    opt = get_optimization(opt_id)
    if not opt:
        return {"success": False, "error": "optimization not found"}, 404
    if opt["status"] == "complete":
        return {"success": False, "error": "optimization already complete"}, 400
    if opt["generations_done"] >= opt["target_generations"]:
        return {"success": False, "error": "no generations remaining"}, 400

    # Load rubric dims for in-prompt anchor mutation + scoring (live).
    rubric_dims: List[Dict[str, Any]] = []
    if opt["rubric_id"]:
        rb = rubrics.get_rubric(opt["rubric_id"], include_revisions=False, recent_judgements=0)
        if rb:
            rubric_dims = rb.get("dimensions") or []

    # Dry-run mode still needs *some* dimensions to score against — fall back
    # to a generic 4-dim rubric so the heuristic scorer has shape to fill.
    if opt["dryrun"] and not rubric_dims:
        rubric_dims = [
            {"name": "Relevance", "weight": 30, "anchors": {}},
            {"name": "Completeness", "weight": 30, "anchors": {}},
            {"name": "Clarity", "weight": 20, "anchors": {}},
            {"name": "Conciseness", "weight": 20, "anchors": {}},
        ]

    cases = opt["test_cases"]
    strategy = opt["strategy"]
    next_gen = int(opt["generations_done"]) + 1
    is_first = (next_gen == 1)
    base_variant_id = ""
    base_composite = opt.get("base_composite")

    started_total = time.time()

    # Step 1 — score the base prompt on generation 1 if we haven't yet.
    if is_first:
        base_score = _score_variant(
            opt=opt,
            variant_prompt=opt["base_prompt"],
            mutation_kind="base",
            cases=cases,
            rubric_dims=rubric_dims,
            provider_factory=provider_factory,
            parallel=parallel,
        )
        base_variant_id = _persist_variant(
            opt_id=opt_id,
            generation=0,
            parent_id="",
            prompt=opt["base_prompt"],
            mutation_kind="base",
            mutation_note="Baseline — your original prompt.",
            score=base_score,
        )
        base_composite = base_score.get("avg_composite")
        # Update opt base_composite
        with _DB_LOCK, _conn() as con:
            con.execute(
                "UPDATE optimizations SET base_composite = ?, status = 'running', updated_at = ? WHERE id = ?",
                (base_composite, _now(), opt_id),
            )
    else:
        # Find the base variant id so children point at it for lineage.
        with _DB_LOCK, _conn() as con:
            row = con.execute(
                "SELECT id FROM opt_variants WHERE optimization_id = ? AND generation = 0 LIMIT 1",
                (opt_id,),
            ).fetchone()
            if row:
                base_variant_id = row["id"]

    # Step 2 — select elites for breeding.
    elites = _select_elites(opt_id, strategy["elite"])

    # Track hashes already in play to avoid duplicate prompts.
    with _DB_LOCK, _conn() as con:
        used_rows = con.execute(
            "SELECT prompt_hash FROM opt_variants WHERE optimization_id = ?",
            (opt_id,),
        ).fetchall()
        used_hashes = {r["prompt_hash"] for r in used_rows}

    if is_first:
        plan = _seed_population(
            opt["base_prompt"],
            base_composite,
            base_variant_id,
            cases,
            rubric_dims,
            strategy,
        )
    else:
        plan = _evolve_population(
            elites=elites,
            base_prompt=opt["base_prompt"],
            cases=cases,
            rubric_dims=rubric_dims,
            strategy=strategy,
            used_hashes=used_hashes,
        )

    # Step 3 — score each variant in the plan.
    persisted_variants: List[Dict[str, Any]] = []
    total_cost = 0.0
    for item in plan:
        score = _score_variant(
            opt=opt,
            variant_prompt=item["prompt"],
            mutation_kind=item["mutation_kind"],
            cases=cases,
            rubric_dims=rubric_dims,
            provider_factory=provider_factory,
            parallel=parallel,
        )
        vid = _persist_variant(
            opt_id=opt_id,
            generation=next_gen,
            parent_id=item.get("parent_id") or base_variant_id,
            prompt=item["prompt"],
            mutation_kind=item["mutation_kind"],
            mutation_note=item["mutation_note"],
            score=score,
        )
        total_cost += float(score.get("cost_usd") or 0.0)
        with _DB_LOCK, _conn() as con:
            row = con.execute("SELECT * FROM opt_variants WHERE id = ?", (vid,)).fetchone()
            persisted_variants.append(_row_to_variant(row))

    # Step 4 — record the generation snapshot.
    duration = round(time.time() - started_total, 3)
    completed = [v for v in persisted_variants if v.get("avg_composite") is not None]
    best = max(completed, key=lambda v: v["avg_composite"]) if completed else None
    avg_gen = (
        round(sum(v["avg_composite"] for v in completed) / len(completed), 2)
        if completed else None
    )
    gen_id = uuid.uuid4().hex
    note = f"Generation {next_gen}: {len(persisted_variants)} variants scored."
    with _DB_LOCK, _conn() as con:
        con.execute(
            """INSERT INTO opt_generations
                 (id, optimization_id, generation, n_variants,
                  best_composite, avg_composite, cost_usd, duration,
                  champion_variant, note, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (gen_id, opt_id, next_gen, len(persisted_variants),
             best["avg_composite"] if best else None,
             avg_gen, total_cost, duration,
             best["id"] if best else None, note, _now()),
        )
        # Step 5 — promote new champion if better than current best.
        cur_best = opt.get("best_composite")
        new_best = cur_best
        new_champ = opt.get("champion_variant") or ""
        if best and (cur_best is None or best["avg_composite"] > float(cur_best)):
            new_best = best["avg_composite"]
            new_champ = best["id"]
            con.execute(
                "UPDATE opt_variants SET is_champion = 0 WHERE optimization_id = ?",
                (opt_id,),
            )
            con.execute(
                "UPDATE opt_variants SET is_champion = 1 WHERE id = ?",
                (best["id"],),
            )
        next_status = "complete" if next_gen >= opt["target_generations"] else "running"
        con.execute(
            """UPDATE optimizations
               SET generations_done = ?, champion_variant = ?, best_composite = ?,
                   total_cost = total_cost + ?, status = ?, updated_at = ?
               WHERE id = ?""",
            (next_gen, new_champ, new_best, total_cost, next_status, _now(), opt_id),
        )

    return {
        "success": True,
        "optimization": get_optimization(opt_id),
        "generation": next_gen,
        "variants_added": len(persisted_variants),
        "best_in_generation": best["avg_composite"] if best else None,
        "gen_cost": round(total_cost, 6),
        "duration": duration,
    }, 200


def _select_elites(opt_id: str, k: int) -> List[Dict[str, Any]]:
    """Pick the top-k variants from any prior generation (including base)."""
    if k <= 0:
        return []
    init_db()
    with _DB_LOCK, _conn() as con:
        rows = con.execute(
            """SELECT * FROM opt_variants
               WHERE optimization_id = ? AND avg_composite IS NOT NULL
               ORDER BY avg_composite DESC, created_at ASC
               LIMIT ?""",
            (opt_id, int(k)),
        ).fetchall()
        for r in rows:
            con.execute(
                "UPDATE opt_variants SET is_elite = 1 WHERE id = ?",
                (r["id"],),
            )
    return [_row_to_variant(r) for r in rows]


def _persist_variant(
    *,
    opt_id: str,
    generation: int,
    parent_id: str,
    prompt: str,
    mutation_kind: str,
    mutation_note: str,
    score: Dict[str, Any],
) -> str:
    vid = uuid.uuid4().hex
    now = _now()
    prompt_hash = hashlib.sha1(prompt.strip().encode()).hexdigest()[:16]
    status = "complete" if score.get("n_complete", 0) > 0 else "failed"
    error = score.get("error") or ""
    runs_json = json.dumps(score.get("runs") or [])
    with _DB_LOCK, _conn() as con:
        con.execute(
            """INSERT INTO opt_variants
                 (id, optimization_id, generation, parent_id,
                  prompt, prompt_hash, mutation_kind, mutation_note,
                  avg_composite, min_composite, max_composite,
                  cost_usd, latency, runs_json,
                  status, error, is_champion, is_elite, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, ?)""",
            (vid, opt_id, int(generation), parent_id or None,
             prompt, prompt_hash, mutation_kind, mutation_note or "",
             score.get("avg_composite"), score.get("min_composite"), score.get("max_composite"),
             score.get("cost_usd", 0.0), score.get("latency", 0.0), runs_json,
             status, error, now),
        )
    return vid


def _score_variant(
    *,
    opt: Dict[str, Any],
    variant_prompt: str,
    mutation_kind: str,
    cases: List[Dict[str, Any]],
    rubric_dims: List[Dict[str, Any]],
    provider_factory,
    parallel: int,
) -> Dict[str, Any]:
    if opt["dryrun"]:
        return _score_variant_dryrun(
            variant_prompt=variant_prompt,
            cases=cases,
            dimensions=rubric_dims,
            mutation_kind=mutation_kind,
        )
    return _score_variant_live(
        variant_prompt=variant_prompt,
        cases=cases,
        candidate_provider=opt["candidate_provider"],
        candidate_model=opt["candidate_model"],
        judge_provider=opt["judge_provider"],
        judge_model=opt["judge_model"],
        rubric_id=opt["rubric_id"],
        revision_num=opt["rubric_revision"],
        provider_factory=provider_factory,
        parallel=parallel,
    )


# ---------------------------------------------------------------------------
# Stats banner
# ---------------------------------------------------------------------------

def stats() -> Dict[str, Any]:
    init_db()
    with _DB_LOCK, _conn() as con:
        n_opt = int(con.execute("SELECT COUNT(*) AS c FROM optimizations").fetchone()["c"])
        n_running = int(con.execute(
            "SELECT COUNT(*) AS c FROM optimizations WHERE status = 'running'"
        ).fetchone()["c"])
        n_complete = int(con.execute(
            "SELECT COUNT(*) AS c FROM optimizations WHERE status = 'complete'"
        ).fetchone()["c"])
        n_variants = int(con.execute("SELECT COUNT(*) AS c FROM opt_variants").fetchone()["c"])
        total_cost = round(float(con.execute(
            "SELECT COALESCE(SUM(total_cost), 0) AS s FROM optimizations"
        ).fetchone()["s"]), 4)
        # Biggest lift any optimization achieved
        lift_row = con.execute(
            """SELECT id, name, base_composite, best_composite,
                      (best_composite - base_composite) AS lift
               FROM optimizations
               WHERE base_composite IS NOT NULL AND best_composite IS NOT NULL
               ORDER BY lift DESC NULLS LAST
               LIMIT 1"""
        ).fetchone()
        biggest_lift = None
        if lift_row and lift_row["lift"] is not None:
            biggest_lift = {
                "optimization_id": lift_row["id"],
                "name": lift_row["name"],
                "base": round(float(lift_row["base_composite"]), 2),
                "best": round(float(lift_row["best_composite"]), 2),
                "lift": round(float(lift_row["lift"]), 2),
            }
        # Most-used mutation across champions (proxy for "what's working")
        mut_rows = con.execute(
            """SELECT mutation_kind, COUNT(*) AS uses, AVG(avg_composite) AS avg_comp
               FROM opt_variants
               WHERE avg_composite IS NOT NULL AND mutation_kind != 'base'
               GROUP BY mutation_kind
               ORDER BY avg_comp DESC NULLS LAST
               LIMIT 5"""
        ).fetchall()
        top_mutations = [
            {
                "kind": r["mutation_kind"],
                "uses": int(r["uses"]),
                "avg_composite": round(float(r["avg_comp"]), 2) if r["avg_comp"] is not None else None,
            }
            for r in mut_rows
        ]
        # Recent activity
        recent_rows = con.execute(
            """SELECT id, name, status, best_composite, base_composite, updated_at
               FROM optimizations
               ORDER BY updated_at DESC
               LIMIT 6"""
        ).fetchall()
        recent = [
            {
                "id": r["id"],
                "name": r["name"],
                "status": r["status"],
                "best": r["best_composite"],
                "base": r["base_composite"],
                "lift": (round(float(r["best_composite"] - r["base_composite"]), 2)
                         if r["best_composite"] is not None and r["base_composite"] is not None else None),
                "updated_at": r["updated_at"],
            }
            for r in recent_rows
        ]
    return {
        "n_optimizations": n_opt,
        "n_running": n_running,
        "n_complete": n_complete,
        "n_variants": n_variants,
        "total_cost": total_cost,
        "biggest_lift": biggest_lift,
        "top_mutations": top_mutations,
        "recent": recent,
        "mutation_catalog": mutation_catalog(),
    }


# ---------------------------------------------------------------------------
# Seed — provides an instant Day-1 demo when the user clicks "Seed demo"
# ---------------------------------------------------------------------------

_SEED_NAME = "Customer email triage (demo)"


def seed_demo() -> Optional[Dict[str, Any]]:
    """Idempotently seed a single demo optimization. Returns the row."""
    init_db()
    with _DB_LOCK, _conn() as con:
        existing = con.execute(
            "SELECT id FROM optimizations WHERE name = ?", (_SEED_NAME,),
        ).fetchone()
        if existing:
            return get_optimization(existing["id"])
    cases = [
        {
            "input": "I've been charged twice for last month's subscription. Can you fix this?",
            "expected": "Acknowledge the duplicate charge, confirm a refund will be issued within 5-7 business days, ask for the order ID if needed.",
        },
        {
            "input": "Your app keeps crashing when I try to upload an image bigger than 5MB.",
            "expected": "Confirm the limit, apologize for the crash, suggest a workaround (compress / smaller file), promise to escalate the crash.",
        },
        {
            "input": "I want to cancel my account immediately. I'm done.",
            "expected": "Acknowledge the request without arguing, confirm cancellation can happen now, ask if there's anything that would change their mind only once and gracefully.",
        },
    ]
    base_prompt = (
        "Reply to this customer support email. Be helpful and friendly. "
        "Resolve their issue if you can."
    )
    return create_optimization(
        name=_SEED_NAME,
        description="Show me how Optimizer evolves a generic support prompt into a high-quality one.",
        base_prompt=base_prompt,
        rubric_id="",  # dry-run, no real rubric needed
        rubric_revision=None,
        judge_provider="",
        judge_model="",
        candidate_provider="",
        candidate_model="",
        test_cases=cases,
        target_generations=3,
        strategy={
            "population": 5,
            "elite": 2,
            "mutations": [
                "add_role", "step_by_step", "add_constraints",
                "structure_sections", "negative_constraints",
            ],
        },
        dryrun=True,
    )
