"""Prompt Surgeon — Section-Level Ablation & Attribution.

Every prior quality surface in the playground perturbs *something* about the
call and measures the impact:

* **Adversary** changes the *input* — typos, structural shuffles, injections.
* **Showdown** changes the *prompt* — champion vs challenger.
* **Drift** changes nothing — fires the same call N times, measures spread.
* **Optimizer** *rewrites* the whole prompt and reports whether the rewrite
  beats the original.

None of them answers the question every engineer who has shipped an LLM
feature for more than a quarter ends up asking when the system prompt is
two thousand tokens long and the team can't remember why half the bullets
are even there: *which paragraphs in this prompt are actually doing the
work, and which ones can I delete without anyone noticing?*

That question is not vanity — it is the difference between a 2000-token
prompt that costs $3 / 1k calls and a 900-token prompt that scores the
same and costs $1.40 / 1k calls. On a feature pulling 50k calls a day the
delta is the difference between a $4.5k and a $2.1k AWS invoice for the
same product. Surgeon is the surface that measures it.

Given a system prompt, Surgeon parses it into **sections** (markdown
headings, numbered/bulleted lists, blank-line-separated paragraphs, or
sentence groups for prose-blob prompts), then for each section issues
``n_replays`` parallel calls with that section **removed** and compares
the scores to a baseline run of the original prompt. Per section it
returns:

* **Load** — ``baseline_score − ablated_score`` (0-100 scale). The bigger
  the drop in quality when the section is gone, the more load-bearing it
  was. Negative load means *quality went up* without the section — i.e.
  the section was hurting you.
* **Band** — ``critical (≥15) · supporting (5–15) · dead-weight (<5
  positive) · harmful (negative)``.
* **Token estimate** — bytes-based approximation (≈4 chars/token, matches
  the rest of the playground), used to compute the savings of dropping
  the section from the live prompt.
* **Sample diff** — the medoid response from the ablated batch, so the
  user can see *what kind of answer* the model gives when the section is
  gone (cosmetic reword? hallucination? refusal?).

The engine then assembles a **lean prompt** — the original minus every
section banded ``dead-weight`` or ``harmful`` — and reports:

* The trimmed prompt verbatim, ready to paste.
* Tokens saved (`original_tokens − lean_tokens`).
* Percentage of the original kept.
* Composite-load delta vs the original baseline.
* Projected **monthly $ savings** at a user-configurable call rate.

The whole loop runs in ``dryrun`` mode without API keys — deterministic
synthetic responses with controlled per-section "true load" (seeded from
section content + index hash) — so the demo lights up the moment the
page loads.

Public surface (deliberately narrow):
``create_surgeon``, ``list_surgeons``, ``get_surgeon``, ``delete_surgeon``,
``run_surgeon``, ``seed_demo``, ``stats``, ``defaults``,
``parse_sections``.
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
from typing import Any, Dict, List, Optional, Tuple

from src import history
from src.pricing import estimate_cost

_DB_LOCK = history._DB_LOCK  # noqa: SLF001 — share the cross-table sqlite lock


@contextmanager
def _conn():
    with history._conn() as con:  # noqa: SLF001
        yield con


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS surgeon_runs (
    id                 TEXT PRIMARY KEY,
    name               TEXT NOT NULL,
    description        TEXT,
    system_prompt      TEXT NOT NULL,
    user_prompt        TEXT NOT NULL,
    candidate_provider TEXT,
    candidate_model    TEXT,
    temperature        REAL NOT NULL DEFAULT 0.4,
    top_p              REAL NOT NULL DEFAULT 1.0,
    n_replays          INTEGER NOT NULL DEFAULT 3,
    monthly_calls      INTEGER NOT NULL DEFAULT 50000,
    status             TEXT NOT NULL,
    baseline_score     REAL,
    lean_score         REAL,
    composite_load     REAL,
    total_sections     INTEGER,
    critical_count     INTEGER,
    supporting_count   INTEGER,
    dead_weight_count  INTEGER,
    harmful_count      INTEGER,
    original_tokens    INTEGER,
    lean_tokens        INTEGER,
    tokens_saved       INTEGER,
    monthly_savings    REAL,
    total_cost         REAL DEFAULT 0,
    duration           REAL DEFAULT 0,
    dryrun             INTEGER NOT NULL DEFAULT 1,
    summary_json       TEXT,
    created_at         TEXT NOT NULL,
    updated_at         TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS surgeon_sections (
    id              TEXT PRIMARY KEY,
    surgeon_id      TEXT NOT NULL,
    section_index   INTEGER NOT NULL,
    kind            TEXT NOT NULL,
    title           TEXT,
    content         TEXT NOT NULL,
    tokens          INTEGER NOT NULL,
    baseline_score  REAL,
    ablated_score   REAL,
    load_score      REAL,
    band            TEXT,
    medoid_sample   TEXT,
    rationale       TEXT,
    created_at      TEXT NOT NULL,
    FOREIGN KEY (surgeon_id) REFERENCES surgeon_runs(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_surgeon_sections_run
    ON surgeon_sections(surgeon_id, section_index);
"""


def init_db() -> None:
    with _DB_LOCK, _conn() as con:
        con.executescript(_SCHEMA)


# ---------------------------------------------------------------------------
# Defaults / bands
# ---------------------------------------------------------------------------

DEFAULT_N_REPLAYS = 3
MIN_N_REPLAYS = 1
MAX_N_REPLAYS = 8
DEFAULT_TEMPERATURE = 0.4
DEFAULT_TOP_P = 1.0
DEFAULT_MONTHLY_CALLS = 50_000

# Band thresholds on 0-100 load scale.
LOAD_CRITICAL = 15.0
LOAD_SUPPORTING = 5.0
LOAD_HARMFUL = -2.0

# Per-million pricing used in the dryrun savings projection so the demo
# still surfaces a meaningful dollar figure without provider keys.
DRYRUN_PRICE_PER_MTOK = 2.50


def _band_for(load: float) -> str:
    if load is None:
        return "unknown"
    if load >= LOAD_CRITICAL:
        return "critical"
    if load >= LOAD_SUPPORTING:
        return "supporting"
    if load > LOAD_HARMFUL:
        return "dead-weight"
    return "harmful"


def defaults() -> Dict[str, Any]:
    return {
        "n_replays": {"default": DEFAULT_N_REPLAYS, "min": MIN_N_REPLAYS, "max": MAX_N_REPLAYS},
        "temperature": {"default": DEFAULT_TEMPERATURE, "min": 0.0, "max": 2.0, "step": 0.05},
        "top_p": {"default": DEFAULT_TOP_P, "min": 0.0, "max": 1.0, "step": 0.05},
        "monthly_calls": {"default": DEFAULT_MONTHLY_CALLS, "min": 100, "max": 10_000_000},
        "bands": {
            "critical": {"min": LOAD_CRITICAL, "color": "rose"},
            "supporting": {"min": LOAD_SUPPORTING, "max": LOAD_CRITICAL, "color": "amber"},
            "dead-weight": {"min": LOAD_HARMFUL, "max": LOAD_SUPPORTING, "color": "slate"},
            "harmful": {"max": LOAD_HARMFUL, "color": "violet"},
        },
        "scoring": {
            "axes": ["coverage", "fidelity", "format"],
            "weights": {"coverage": 0.50, "fidelity": 0.30, "format": 0.20},
            "scale": "0-100",
        },
        "section_parser": [
            "markdown headings (# / ##)",
            "numbered or bulleted lists (3+ items → each item is its own section)",
            "blank-line-separated paragraphs",
            "sentence groups (~3 sentences) for prose-blob prompts",
        ],
    }


# ---------------------------------------------------------------------------
# Section parser
# ---------------------------------------------------------------------------

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$")
_LIST_RE = re.compile(r"^\s{0,3}(?:[-*•]|\d+\.)\s+(.+)$")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"'`(\[])")


def _token_estimate(text: str) -> int:
    """Cheap byte-based token estimate — ~4 chars/token, matches the rest
    of the playground's pricing/usage approximations."""
    s = text or ""
    return max(1, math.ceil(len(s) / 4))


def _slug(text: str, limit: int = 60) -> str:
    s = re.sub(r"\s+", " ", (text or "").strip())
    if len(s) <= limit:
        return s
    return s[: limit - 1].rstrip() + "…"


def _split_paragraphs(text: str) -> List[str]:
    blocks: List[str] = []
    current: List[str] = []
    for line in text.splitlines():
        if line.strip() == "":
            if current:
                blocks.append("\n".join(current))
                current = []
        else:
            current.append(line)
    if current:
        blocks.append("\n".join(current))
    return blocks


def _is_list_block(lines: List[str]) -> bool:
    if not lines:
        return False
    hits = sum(1 for ln in lines if _LIST_RE.match(ln))
    return hits >= 3 and hits / len(lines) >= 0.6


def parse_sections(prompt: str) -> List[Dict[str, Any]]:
    """Split ``prompt`` into ablatable sections.

    Heuristics (priority order):
        1. Markdown headings (`# Header`) open a new section that owns
           every line up to the next heading.
        2. Inside a non-heading block, if the block is 3+ list items,
           every item becomes its own section.
        3. Otherwise the block is a paragraph section.
        4. If the whole prompt parses to one giant paragraph, split it
           into sentence groups of ~3 sentences each.

    Each section is a dict ``{index, kind, title, content, tokens}`` ready
    to feed into the ablation loop.
    """
    text = (prompt or "").rstrip()
    if not text.strip():
        return []

    # --- Pass 1: walk by lines, group into raw blocks honoring headings.
    raw_blocks: List[Tuple[str, str, List[str]]] = []  # (kind, title, lines)
    current_lines: List[str] = []
    current_title: Optional[str] = None

    def flush(kind_hint: Optional[str] = None) -> None:
        nonlocal current_lines, current_title
        if not current_lines and not (current_title is not None):
            return
        title = current_title or ""
        lines = current_lines[:]
        kind = kind_hint or ("heading-block" if title else "paragraph")
        raw_blocks.append((kind, title, lines))
        current_lines = []
        current_title = None

    for line in text.splitlines():
        m = _HEADING_RE.match(line.rstrip())
        if m:
            flush()
            current_title = m.group(2).strip()
            current_lines = []
            continue
        current_lines.append(line)
    flush()

    # --- Pass 2: expand heading-blocks; split list blocks into per-item.
    sections: List[Dict[str, Any]] = []
    seq = 0

    def push(kind: str, title: str, content: str) -> None:
        nonlocal seq
        body = content.rstrip()
        if not body.strip() and not title.strip():
            return
        sections.append({
            "index": seq,
            "kind": kind,
            "title": title or _slug(body),
            "content": content,
            "tokens": _token_estimate((title + "\n" + content) if title else content),
        })
        seq += 1

    for kind, title, lines in raw_blocks:
        # Within the block, separate paragraphs by blank lines.
        sub_blocks: List[List[str]] = [[]]
        for ln in lines:
            if ln.strip() == "":
                if sub_blocks[-1]:
                    sub_blocks.append([])
            else:
                sub_blocks[-1].append(ln)
        sub_blocks = [b for b in sub_blocks if b]

        # Heading with no body — still a section (the heading itself).
        if not sub_blocks and title:
            push("heading", title, "")
            continue

        # If the entire heading-block is a single list, hoist it.
        flat_lines = [ln for sb in sub_blocks for ln in sb]
        if title and _is_list_block(flat_lines):
            for ln in flat_lines:
                m = _LIST_RE.match(ln)
                if not m:
                    continue
                item = m.group(1).strip()
                push("list-item", f"{title} → {_slug(item, 40)}", item)
            continue

        # Per-sub-block: list, paragraph, or sentence-group fallback.
        for sb_idx, sb in enumerate(sub_blocks):
            sub_title = title if (title and sb_idx == 0) else ""
            if _is_list_block(sb):
                for ln in sb:
                    m = _LIST_RE.match(ln)
                    if not m:
                        continue
                    item = m.group(1).strip()
                    push("list-item", _slug(item, 60), item)
                continue
            block_text = "\n".join(sb).strip()
            if not block_text:
                continue
            push("paragraph", sub_title or _slug(block_text), block_text)

    # --- Sentence-group fallback for prose-blob prompts.
    if len(sections) <= 1 and len(text) > 240:
        sentences = [s.strip() for s in _SENTENCE_SPLIT_RE.split(text) if s.strip()]
        if len(sentences) >= 3:
            sections = []
            seq = 0
            chunk: List[str] = []
            for sent in sentences:
                chunk.append(sent)
                if len(chunk) == 3:
                    body = " ".join(chunk)
                    push("sentence-group", _slug(body), body)
                    chunk = []
            if chunk:
                body = " ".join(chunk)
                push("sentence-group", _slug(body), body)

    return sections


def assemble_without(sections: List[Dict[str, Any]], drop_index: int) -> str:
    """Reassemble the prompt from ``sections`` while skipping
    ``sections[drop_index]``. The format is consistent with how
    ``parse_sections`` reads — headings preserved, list items glued back
    into one block per neighbour, paragraphs separated by blank lines."""
    parts: List[str] = []
    for sec in sections:
        if sec["index"] == drop_index:
            continue
        kind = sec["kind"]
        if kind == "heading":
            parts.append(f"## {sec['title']}")
        elif kind == "list-item":
            parts.append(f"- {sec['content']}")
        elif kind == "heading-block":
            if sec.get("title"):
                parts.append(f"## {sec['title']}\n\n{sec['content']}")
            else:
                parts.append(sec["content"])
        else:
            parts.append(sec["content"])
    return "\n\n".join(p for p in parts if p)


def assemble_lean(sections: List[Dict[str, Any]], dropped: List[int]) -> str:
    drop_set = set(dropped)
    parts: List[str] = []
    for sec in sections:
        if sec["index"] in drop_set:
            continue
        kind = sec["kind"]
        if kind == "heading":
            parts.append(f"## {sec['title']}")
        elif kind == "list-item":
            parts.append(f"- {sec['content']}")
        else:
            parts.append(sec["content"])
    return "\n\n".join(p for p in parts if p)


# ---------------------------------------------------------------------------
# Scoring (response → composite 0-100)
# ---------------------------------------------------------------------------

_WORD_RE = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> List[str]:
    return _WORD_RE.findall((text or "").lower())


def _coverage_score(response: str, expected_keywords: List[str]) -> float:
    if not expected_keywords:
        return 60.0
    words = set(_tokens(response))
    hits = sum(1 for kw in expected_keywords if kw.lower() in words)
    pct = hits / len(expected_keywords)
    # Map 0-1 → 20-100 with a kind floor so an empty response still scores
    # measurably below a half-coverage answer.
    return round(20.0 + pct * 80.0, 2)


def _fidelity_score(response: str, baseline: str) -> float:
    if not baseline:
        # No baseline → just reward non-emptiness.
        return 50.0 if (response or "").strip() else 0.0
    a = set(_tokens(response))
    b = set(_tokens(baseline))
    if not a and not b:
        return 100.0
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return round(100.0 * inter / union, 2)


def _format_score(response: str) -> float:
    """Cheap structural-conformance proxy — rewards responses that don't
    collapse to a one-liner and aren't unbounded ramble."""
    text = (response or "").strip()
    if not text:
        return 0.0
    tok = _token_estimate(text)
    # Sweet spot: 60-400 tokens.
    if tok < 20:
        return 30.0
    if tok < 60:
        return 60.0
    if tok <= 400:
        return 95.0
    if tok <= 800:
        return 75.0
    return 50.0


def composite_score(
    response: str,
    *,
    expected_keywords: List[str],
    baseline: str,
) -> float:
    cov = _coverage_score(response, expected_keywords)
    fid = _fidelity_score(response, baseline)
    fmt = _format_score(response)
    return round(0.50 * cov + 0.30 * fid + 0.20 * fmt, 2)


# ---------------------------------------------------------------------------
# Replay execution (live + dryrun)
# ---------------------------------------------------------------------------

def _seed_hash(*parts: str) -> bytes:
    return hashlib.sha1("||".join(parts).encode()).digest()


def _section_true_load(system_prompt: str, section_content: str, section_index: int) -> float:
    """Deterministic synthetic "true load" for a section in dryrun mode.

    Buckets six ways so the demo always shows the full band spectrum:
    critical / strong-supporting / weak-supporting / dead-weight /
    mild-harmful / strong-harmful — and the buckets are seeded from the
    section content + index, so the same prompt always paints the same
    chart on every page load."""
    h = _seed_hash("surgeon-load", system_prompt[:128] or "?", section_content[:96] or "?", str(section_index))
    raw = int.from_bytes(h[:2], "big") % 100  # 0-99
    # Distribute roughly: 20% critical, 30% supporting, 35% dead, 15% harmful.
    if raw < 20:
        magnitude = 18.0 + (h[2] / 255.0) * 18.0  # 18-36
        return round(magnitude, 2)
    if raw < 50:
        magnitude = 6.0 + (h[2] / 255.0) * 8.5  # 6-14.5
        return round(magnitude, 2)
    if raw < 85:
        magnitude = -1.5 + (h[2] / 255.0) * 6.0  # -1.5 to 4.5
        return round(magnitude, 2)
    magnitude = -10.0 + (h[2] / 255.0) * 7.5  # -10 to -2.5
    return round(magnitude, 2)


def _dry_response(seed: bytes, length_target: int, theme: str) -> str:
    """Deterministic-ish synthetic answer body for dryrun mode."""
    pieces = [
        "Here is a structured response.",
        f"Topic: {theme}.",
        "First, we consider the key constraints in the request.",
        "Second, we outline a concrete approach with checkpoints.",
        "Third, we list the assumptions made along the way.",
        "Fourth, we describe the expected output and how to validate it.",
        "Finally, we surface the open questions a reviewer should answer.",
        "The trade-offs depend on latency, cost, and accuracy targets.",
        "We avoid speculative claims and ground each step in the prompt.",
        "Sources: prompt, prior conversation, and standard practice.",
    ]
    # Pick a deterministic subset.
    n_sentences = max(3, min(len(pieces), 3 + (seed[0] % 6)))
    out = " ".join(pieces[i % len(pieces)] for i in range(n_sentences))
    # Length-control trim/pad relative to ``length_target`` tokens.
    desired_chars = max(80, length_target * 4)
    if len(out) > desired_chars:
        out = out[:desired_chars].rstrip() + "…"
    elif len(out) < desired_chars - 200:
        out = out + " " + " ".join(["Additional context is included."] * 4)
    return out


def _live_call(
    *,
    provider_factory,
    system_prompt: str,
    user_prompt: str,
    provider: str,
    model: str,
    temperature: float,
    top_p: float,
) -> Dict[str, Any]:
    inst = provider_factory.create_provider(provider)
    if not inst:
        return {"status": "error", "error": f"provider {provider} not available", "response": "", "latency": 0.0,
                "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0}
    started = time.time()
    try:
        params = {"temperature": temperature, "top_p": top_p, "max_tokens": 600}
        resp = inst.chat(
            model=model,
            messages=[{"role": "user", "content": user_prompt}],
            system_prompt=system_prompt or "",
            params=params,
        )
        text = ""
        if isinstance(resp, dict):
            text = resp.get("response") or resp.get("content") or ""
            in_tok = int(resp.get("input_tokens", 0) or 0)
            out_tok = int(resp.get("output_tokens", 0) or 0)
        else:
            text = str(resp or "")
            in_tok = _token_estimate(system_prompt + user_prompt)
            out_tok = _token_estimate(text)
        latency = round(time.time() - started, 3)
        return {
            "status": "success" if text.strip() else "error",
            "error": None if text.strip() else "empty response",
            "response": text,
            "latency": latency,
            "input_tokens": in_tok or _token_estimate(system_prompt + user_prompt),
            "output_tokens": out_tok or _token_estimate(text),
            "cost_usd": round(float(estimate_cost(model, in_tok, out_tok) or 0.0), 6),
        }
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error": str(exc), "response": "", "latency": 0.0,
                "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0}


def _batch_responses(
    *,
    system_prompt: str,
    user_prompt: str,
    candidate_provider: str,
    candidate_model: str,
    temperature: float,
    top_p: float,
    n_replays: int,
    dryrun: bool,
    provider_factory,
    section_seed: str,
) -> List[Dict[str, Any]]:
    if dryrun:
        results: List[Dict[str, Any]] = []
        for i in range(n_replays):
            seed = _seed_hash("surgeon-resp", section_seed, str(i), str(temperature))
            length_target = 80 + (seed[1] % 180)
            body = _dry_response(seed, length_target, theme=section_seed[:40] or "the request")
            in_tok = _token_estimate(system_prompt + user_prompt)
            out_tok = _token_estimate(body)
            latency = 0.30 + (seed[2] / 255.0) * 0.7
            results.append({
                "replay_index": i,
                "status": "success",
                "response": body,
                "latency": round(latency, 3),
                "input_tokens": in_tok,
                "output_tokens": out_tok,
                "cost_usd": round(float(estimate_cost(candidate_model or "dryrun/echo", in_tok, out_tok) or 0.0), 6),
                "error": None,
            })
        return results

    # Live mode — fan out across the thread pool.
    out: List[Dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=min(n_replays, 6)) as pool:
        futures = {
            pool.submit(
                _live_call,
                provider_factory=provider_factory,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                provider=candidate_provider,
                model=candidate_model,
                temperature=temperature,
                top_p=top_p,
            ): i
            for i in range(n_replays)
        }
        for fut in as_completed(futures):
            i = futures[fut]
            try:
                res = fut.result()
            except Exception as exc:  # noqa: BLE001
                res = {"status": "error", "error": str(exc), "response": "", "latency": 0.0,
                       "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0}
            res["replay_index"] = i
            out.append(res)
    out.sort(key=lambda r: r["replay_index"])
    return out


# ---------------------------------------------------------------------------
# Persistence — CRUD on surgeon_runs + surgeon_sections
# ---------------------------------------------------------------------------

def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _clip_int(v: Any, lo: int, hi: int, default: int) -> int:
    try:
        n = int(v)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, n))


def _clip_float(v: Any, lo: float, hi: float, default: float) -> float:
    try:
        n = float(v)
    except (TypeError, ValueError):
        return default
    if math.isnan(n) or math.isinf(n):
        return default
    return max(lo, min(hi, n))


def _row_to_run(row: sqlite3.Row) -> Dict[str, Any]:
    summary: Dict[str, Any] = {}
    if row["summary_json"]:
        try:
            summary = json.loads(row["summary_json"])
        except (TypeError, ValueError, json.JSONDecodeError):
            summary = {}
    return {
        "id": row["id"],
        "name": row["name"],
        "description": row["description"] or "",
        "system_prompt": row["system_prompt"],
        "user_prompt": row["user_prompt"],
        "candidate_provider": row["candidate_provider"] or "",
        "candidate_model": row["candidate_model"] or "",
        "temperature": float(row["temperature"]),
        "top_p": float(row["top_p"]),
        "n_replays": int(row["n_replays"]),
        "monthly_calls": int(row["monthly_calls"]),
        "status": row["status"],
        "baseline_score": float(row["baseline_score"]) if row["baseline_score"] is not None else None,
        "lean_score": float(row["lean_score"]) if row["lean_score"] is not None else None,
        "composite_load": float(row["composite_load"]) if row["composite_load"] is not None else None,
        "total_sections": int(row["total_sections"] or 0),
        "critical_count": int(row["critical_count"] or 0),
        "supporting_count": int(row["supporting_count"] or 0),
        "dead_weight_count": int(row["dead_weight_count"] or 0),
        "harmful_count": int(row["harmful_count"] or 0),
        "original_tokens": int(row["original_tokens"] or 0),
        "lean_tokens": int(row["lean_tokens"] or 0),
        "tokens_saved": int(row["tokens_saved"] or 0),
        "monthly_savings": float(row["monthly_savings"] or 0),
        "total_cost": float(row["total_cost"] or 0),
        "duration": float(row["duration"] or 0),
        "dryrun": bool(row["dryrun"]),
        "summary": summary,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _row_to_section(row: sqlite3.Row) -> Dict[str, Any]:
    return {
        "id": row["id"],
        "section_index": int(row["section_index"]),
        "kind": row["kind"],
        "title": row["title"] or "",
        "content": row["content"],
        "tokens": int(row["tokens"]),
        "baseline_score": float(row["baseline_score"]) if row["baseline_score"] is not None else None,
        "ablated_score": float(row["ablated_score"]) if row["ablated_score"] is not None else None,
        "load_score": float(row["load_score"]) if row["load_score"] is not None else None,
        "band": row["band"] or "unknown",
        "medoid_sample": row["medoid_sample"] or "",
        "rationale": row["rationale"] or "",
        "created_at": row["created_at"],
    }


def create_surgeon(
    *,
    name: str,
    description: str = "",
    system_prompt: str,
    user_prompt: str,
    candidate_provider: str = "",
    candidate_model: str = "",
    temperature: Any = DEFAULT_TEMPERATURE,
    top_p: Any = DEFAULT_TOP_P,
    n_replays: Any = DEFAULT_N_REPLAYS,
    monthly_calls: Any = DEFAULT_MONTHLY_CALLS,
    dryrun: bool = False,
) -> Dict[str, Any]:
    init_db()
    if not name.strip():
        raise ValueError("name required")
    if not (system_prompt or "").strip():
        raise ValueError("system_prompt required — Surgeon needs a prompt to slice")
    if not user_prompt.strip():
        raise ValueError("user_prompt required")
    temperature = _clip_float(temperature, 0.0, 2.0, DEFAULT_TEMPERATURE)
    top_p = _clip_float(top_p, 0.0, 1.0, DEFAULT_TOP_P)
    n_replays = _clip_int(n_replays, MIN_N_REPLAYS, MAX_N_REPLAYS, DEFAULT_N_REPLAYS)
    monthly_calls = _clip_int(monthly_calls, 100, 10_000_000, DEFAULT_MONTHLY_CALLS)
    run_id = uuid.uuid4().hex[:12]
    now = _now()
    with _DB_LOCK, _conn() as con:
        con.execute(
            """
            INSERT INTO surgeon_runs (
                id, name, description, system_prompt, user_prompt,
                candidate_provider, candidate_model, temperature, top_p,
                n_replays, monthly_calls, status, dryrun, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'queued', ?, ?, ?)
            """,
            (
                run_id, name.strip(), description.strip(), system_prompt, user_prompt.strip(),
                candidate_provider.strip(), candidate_model.strip(), temperature, top_p,
                n_replays, monthly_calls, 1 if dryrun else 0, now, now,
            ),
        )
    return get_surgeon(run_id) or {}


def list_surgeons(
    *,
    q: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> Tuple[List[Dict[str, Any]], int]:
    init_db()
    where: List[str] = []
    args: List[Any] = []
    if q:
        where.append("(name LIKE ? OR description LIKE ?)")
        like = f"%{q}%"
        args.extend([like, like])
    if status:
        where.append("status = ?")
        args.append(status)
    sql_where = ("WHERE " + " AND ".join(where)) if where else ""
    with _DB_LOCK, _conn() as con:
        total = con.execute(f"SELECT COUNT(*) FROM surgeon_runs {sql_where}", args).fetchone()[0]
        rows = con.execute(
            f"SELECT * FROM surgeon_runs {sql_where} ORDER BY updated_at DESC LIMIT ? OFFSET ?",
            args + [int(limit), int(offset)],
        ).fetchall()
    return [_row_to_run(r) for r in rows], int(total)


def get_surgeon(run_id: str, *, with_sections: bool = True) -> Optional[Dict[str, Any]]:
    init_db()
    with _DB_LOCK, _conn() as con:
        row = con.execute("SELECT * FROM surgeon_runs WHERE id = ?", (run_id,)).fetchone()
        if not row:
            return None
        run = _row_to_run(row)
        if with_sections:
            srows = con.execute(
                "SELECT * FROM surgeon_sections WHERE surgeon_id = ? ORDER BY section_index ASC",
                (run_id,),
            ).fetchall()
            run["sections"] = [_row_to_section(r) for r in srows]
    return run


def delete_surgeon(run_id: str) -> bool:
    init_db()
    with _DB_LOCK, _conn() as con:
        cur = con.execute("DELETE FROM surgeon_runs WHERE id = ?", (run_id,))
        con.execute("DELETE FROM surgeon_sections WHERE surgeon_id = ?", (run_id,))
        return cur.rowcount > 0


def stats() -> Dict[str, Any]:
    init_db()
    with _DB_LOCK, _conn() as con:
        total = con.execute("SELECT COUNT(*) FROM surgeon_runs").fetchone()[0]
        completed = con.execute(
            "SELECT COUNT(*) FROM surgeon_runs WHERE status='succeeded'"
        ).fetchone()[0]
        agg = con.execute(
            """SELECT AVG(baseline_score), AVG(lean_score), AVG(tokens_saved),
                      AVG(monthly_savings), SUM(tokens_saved)
                 FROM surgeon_runs WHERE status='succeeded'"""
        ).fetchone()
        last_row = con.execute(
            "SELECT id, name, updated_at FROM surgeon_runs ORDER BY updated_at DESC LIMIT 1"
        ).fetchone()
    return {
        "total_runs": int(total or 0),
        "completed_runs": int(completed or 0),
        "avg_baseline_score": round(float(agg[0]), 2) if agg and agg[0] is not None else None,
        "avg_lean_score": round(float(agg[1]), 2) if agg and agg[1] is not None else None,
        "avg_tokens_saved": round(float(agg[2]), 0) if agg and agg[2] is not None else None,
        "avg_monthly_savings": round(float(agg[3]), 2) if agg and agg[3] is not None else None,
        "total_tokens_saved": int(agg[4] or 0) if agg else 0,
        "last_run": dict(last_row) if last_row else None,
    }


# ---------------------------------------------------------------------------
# Engine — score baseline, ablate each section, derive lean prompt
# ---------------------------------------------------------------------------

_STOP = {
    "the", "and", "for", "with", "that", "this", "from", "your", "you",
    "are", "was", "were", "have", "has", "had", "but", "not", "any",
    "all", "can", "will", "may", "into", "out", "over", "under", "into",
    "should", "would", "could", "must", "also", "more", "than", "then",
    "they", "them", "their", "our", "its", "his", "her",
}


def _keywords_from(prompt: str, k: int = 12) -> List[str]:
    """Pull the most frequent non-stop content words from ``prompt`` as a
    proxy for what a faithful answer ought to mention."""
    freq: Dict[str, int] = {}
    for w in _tokens(prompt):
        if len(w) < 4 or w in _STOP:
            continue
        freq[w] = freq.get(w, 0) + 1
    return [w for w, _ in sorted(freq.items(), key=lambda kv: -kv[1])[:k]]


def _medoid(samples: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    succ = [s for s in samples if s["status"] == "success" and (s.get("response") or "").strip()]
    if not succ:
        return None
    if len(succ) == 1:
        return succ[0]
    sims: List[Tuple[int, float]] = []
    sets = [set(_tokens(s["response"])) for s in succ]
    for i in range(len(succ)):
        total = 0.0
        for j in range(len(succ)):
            if i == j:
                continue
            a, b = sets[i], sets[j]
            if not a and not b:
                total += 1.0
            elif not a or not b:
                total += 0.0
            else:
                total += len(a & b) / len(a | b)
        sims.append((i, total / max(1, len(succ) - 1)))
    sims.sort(key=lambda kv: -kv[1])
    return succ[sims[0][0]]


def _mean(values: List[float]) -> Optional[float]:
    vs = [float(v) for v in values if v is not None]
    if not vs:
        return None
    return sum(vs) / len(vs)


def run_surgeon(
    surgeon_id: str,
    *,
    provider_factory,
    confirm_live: bool = False,
) -> Tuple[Dict[str, Any], int]:
    """Walk the prompt, ablate each section, score, persist, return."""
    init_db()
    run = get_surgeon(surgeon_id, with_sections=False)
    if not run:
        return {"success": False, "error": "surgeon run not found"}, 404
    if run["status"] == "running":
        return {"success": False, "error": "surgeon run already running"}, 400
    if not run["dryrun"] and not confirm_live:
        return {
            "success": False,
            "error": "live surgeon run: pass confirm_live=true (this will spend API credits)",
        }, 400

    # Wipe prior sections — a run is re-runnable in place.
    with _DB_LOCK, _conn() as con:
        con.execute("DELETE FROM surgeon_sections WHERE surgeon_id = ?", (surgeon_id,))
        con.execute(
            "UPDATE surgeon_runs SET status='running', updated_at=? WHERE id=?",
            (_now(), surgeon_id),
        )

    started = time.time()
    system_prompt = run["system_prompt"]
    user_prompt = run["user_prompt"]
    sections = parse_sections(system_prompt)
    if not sections:
        with _DB_LOCK, _conn() as con:
            con.execute(
                "UPDATE surgeon_runs SET status='failed', updated_at=? WHERE id=?",
                (_now(), surgeon_id),
            )
        return {"success": False, "error": "could not parse any sections from system_prompt"}, 400

    expected_keywords = _keywords_from(system_prompt + "\n" + user_prompt, k=12)

    # --- Baseline batch.
    baseline_samples = _batch_responses(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        candidate_provider=run["candidate_provider"],
        candidate_model=run["candidate_model"],
        temperature=run["temperature"],
        top_p=run["top_p"],
        n_replays=run["n_replays"],
        dryrun=run["dryrun"],
        provider_factory=provider_factory,
        section_seed="baseline",
    )
    baseline_medoid = _medoid(baseline_samples)
    baseline_text = (baseline_medoid or {}).get("response", "")
    baseline_scores = [
        composite_score(s["response"], expected_keywords=expected_keywords, baseline=baseline_text)
        for s in baseline_samples if s["status"] == "success"
    ]
    baseline_score = round(_mean(baseline_scores) or 0.0, 2)
    total_cost = sum(float(s.get("cost_usd") or 0) for s in baseline_samples)

    # --- Per-section ablation.
    section_records: List[Dict[str, Any]] = []
    for sec in sections:
        ablated_prompt = assemble_without(sections, sec["index"])
        if run["dryrun"]:
            # Use deterministic per-section true-load to synthesize ablated
            # score; replays come from the same batch generator so the UI
            # still gets concrete medoid text it can render.
            samples = _batch_responses(
                system_prompt=ablated_prompt,
                user_prompt=user_prompt,
                candidate_provider=run["candidate_provider"],
                candidate_model=run["candidate_model"],
                temperature=run["temperature"],
                top_p=run["top_p"],
                n_replays=run["n_replays"],
                dryrun=True,
                provider_factory=provider_factory,
                section_seed=f"sec-{sec['index']}-{(sec['title'] or '')[:40]}",
            )
            true_load = _section_true_load(system_prompt, sec["content"], sec["index"])
            ablated_score = max(0.0, min(100.0, baseline_score - true_load))
        else:
            samples = _batch_responses(
                system_prompt=ablated_prompt,
                user_prompt=user_prompt,
                candidate_provider=run["candidate_provider"],
                candidate_model=run["candidate_model"],
                temperature=run["temperature"],
                top_p=run["top_p"],
                n_replays=run["n_replays"],
                dryrun=False,
                provider_factory=provider_factory,
                section_seed=f"sec-{sec['index']}",
            )
            scores = [
                composite_score(s["response"], expected_keywords=expected_keywords, baseline=baseline_text)
                for s in samples if s["status"] == "success"
            ]
            ablated_score = round(_mean(scores) or 0.0, 2)

        total_cost += sum(float(s.get("cost_usd") or 0) for s in samples)
        load = round(baseline_score - ablated_score, 2)
        band = _band_for(load)
        medoid = _medoid(samples)
        medoid_text = (medoid or {}).get("response", "") if medoid else ""
        # Trim medoid for storage — full bodies live in history, not here.
        if len(medoid_text) > 600:
            medoid_text = medoid_text[:597].rstrip() + "…"
        rationale = _explain(sec, load, band)
        section_records.append({
            "section": sec,
            "baseline_score": baseline_score,
            "ablated_score": ablated_score,
            "load_score": load,
            "band": band,
            "medoid_sample": medoid_text,
            "rationale": rationale,
        })

    # --- Derive lean prompt: drop everything banded dead-weight / harmful.
    dropped = [r["section"]["index"] for r in section_records if r["band"] in ("dead-weight", "harmful")]
    lean_prompt = assemble_lean(sections, dropped)
    original_tokens = _token_estimate(system_prompt)
    lean_tokens = _token_estimate(lean_prompt) if lean_prompt else 0
    tokens_saved = max(0, original_tokens - lean_tokens)

    # Lean-prompt projected score = baseline minus net load of all dropped
    # sections. (Dropping a harmful section *adds* to the projected score.)
    composite_load = round(sum(r["load_score"] for r in section_records if r["band"] in ("dead-weight", "harmful")), 2)
    lean_score = round(max(0.0, min(100.0, baseline_score - composite_load)), 2)

    monthly_savings = round(
        (tokens_saved * run["monthly_calls"] / 1_000_000.0) * DRYRUN_PRICE_PER_MTOK,
        2,
    )

    # --- Persist sections + roll-up.
    band_counts = {"critical": 0, "supporting": 0, "dead-weight": 0, "harmful": 0}
    now = _now()
    with _DB_LOCK, _conn() as con:
        for rec in section_records:
            sec = rec["section"]
            band_counts[rec["band"]] = band_counts.get(rec["band"], 0) + 1
            con.execute(
                """
                INSERT INTO surgeon_sections (
                    id, surgeon_id, section_index, kind, title, content, tokens,
                    baseline_score, ablated_score, load_score, band,
                    medoid_sample, rationale, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    uuid.uuid4().hex[:12], surgeon_id, sec["index"], sec["kind"],
                    sec["title"], sec["content"], sec["tokens"],
                    rec["baseline_score"], rec["ablated_score"], rec["load_score"], rec["band"],
                    rec["medoid_sample"], rec["rationale"], now,
                ),
            )

    summary = {
        "lean_prompt": lean_prompt,
        "dropped_indices": dropped,
        "kept_indices": [s["index"] for s in sections if s["index"] not in dropped],
        "expected_keywords": expected_keywords,
        "baseline_medoid": (baseline_text[:600] + ("…" if len(baseline_text) > 600 else "")) if baseline_text else "",
        "actions": _action_list(section_records, baseline_score, lean_score, tokens_saved),
        "section_count": len(sections),
        "pct_kept": round(100.0 * lean_tokens / original_tokens, 1) if original_tokens else 0.0,
    }
    duration = round(time.time() - started, 3)
    with _DB_LOCK, _conn() as con:
        con.execute(
            """
            UPDATE surgeon_runs SET
                status='succeeded',
                baseline_score=?, lean_score=?, composite_load=?,
                total_sections=?, critical_count=?, supporting_count=?,
                dead_weight_count=?, harmful_count=?,
                original_tokens=?, lean_tokens=?, tokens_saved=?, monthly_savings=?,
                total_cost=?, duration=?, summary_json=?, updated_at=?
            WHERE id=?
            """,
            (
                baseline_score, lean_score, composite_load,
                len(sections), band_counts["critical"], band_counts["supporting"],
                band_counts["dead-weight"], band_counts["harmful"],
                original_tokens, lean_tokens, tokens_saved, monthly_savings,
                round(total_cost, 6), duration, json.dumps(summary), now, surgeon_id,
            ),
        )

    return {"success": True, "surgeon": get_surgeon(surgeon_id)}, 200


# ---------------------------------------------------------------------------
# Explanation text generators
# ---------------------------------------------------------------------------

def _explain(section: Dict[str, Any], load: float, band: str) -> str:
    kind_label = {
        "heading": "heading",
        "heading-block": "section",
        "list-item": "bullet",
        "paragraph": "paragraph",
        "sentence-group": "sentence group",
    }.get(section["kind"], "section")
    if band == "critical":
        return (
            f"Removing this {kind_label} dropped quality by {load:.0f} pts — "
            "load-bearing, keep verbatim."
        )
    if band == "supporting":
        return (
            f"This {kind_label} contributes ~{load:.0f} pts of quality — "
            "useful but the prompt survives a careful rewrite."
        )
    if band == "dead-weight":
        if load >= 0:
            return (
                f"Quality barely moved ({load:+.1f} pts) when this {kind_label} "
                "was removed — safe to drop."
            )
        return (
            f"Removing it cost {abs(load):.1f} pts — within noise, treat as "
            "deletable."
        )
    return (
        f"Quality went *up* by {abs(load):.1f} pts without this {kind_label} — "
        "the section is actively hurting your responses. Delete it."
    )


def _action_list(
    records: List[Dict[str, Any]],
    baseline: float,
    lean: float,
    tokens_saved: int,
) -> List[str]:
    actions: List[str] = []
    critical = [r for r in records if r["band"] == "critical"]
    harmful = [r for r in records if r["band"] == "harmful"]
    dead = [r for r in records if r["band"] == "dead-weight"]
    if critical:
        top = max(critical, key=lambda r: r["load_score"])
        actions.append(
            f"**Lock in** the most load-bearing section: *{top['section']['title']}* "
            f"({top['load_score']:.0f}-pt drop when removed)."
        )
    if harmful:
        worst = min(harmful, key=lambda r: r["load_score"])
        actions.append(
            f"**Delete** *{worst['section']['title']}* — removing it raises quality by "
            f"{abs(worst['load_score']):.1f} pts."
        )
    if dead:
        actions.append(
            f"**Drop {len(dead)} dead-weight {'section' if len(dead) == 1 else 'sections'}** "
            f"for ~{tokens_saved} tokens off every call with no measurable quality cost."
        )
    if not actions:
        actions.append("Prompt is lean — no sections fell into the drop band.")
    if lean and lean > baseline + 1:
        actions.append(
            f"Projected lean score **{lean:.0f} > baseline {baseline:.0f}** — "
            "the trim actually nets you quality, not just dollars."
        )
    return actions


# ---------------------------------------------------------------------------
# Seed demo — preloads a believable bloated prompt so the page lights up.
# ---------------------------------------------------------------------------

_DEMO_SYSTEM_PROMPT = """# Customer Support Agent

You are a helpful customer support agent for Acme Corp, a SaaS analytics platform serving mid-market B2B customers in the $10M-$100M ARR range. Be warm, professional, and proactive. Always greet the customer by name when you have it.

## Tone and voice

Be friendly but not chatty. Avoid emojis unless the customer uses them first. Use the customer's own vocabulary — if they call a dashboard a "report", call it a report. Mirror their formality level.

## Account context

Look up the customer's account tier (Starter / Growth / Enterprise) before responding. Different tiers have different SLAs:
- Starter: 24-hour response window, community-supported integrations only
- Growth: 4-hour response window, supported integrations include Stripe, Salesforce, HubSpot
- Enterprise: 1-hour response window, all integrations + custom connectors + dedicated CSM

## Knowledge boundaries

If you don't know the answer, say so. Don't fabricate features that don't exist. Don't speculate about the roadmap. Don't make pricing commitments. Don't promise refunds — escalate to a human agent.

## Escalation criteria

Escalate to a human when:
1. The customer asks for a refund of more than $500
2. The customer mentions legal action, GDPR, HIPAA, SOC2, or compliance
3. The customer is visibly frustrated (uses caps, exclamation points, or words like "unacceptable", "ridiculous", "cancel")
4. The issue requires data deletion, account merger, or schema migration
5. The customer asks to speak to a manager

## Common workflows

For password reset: send them to acme.com/reset, do not handle the reset yourself.

For billing questions: pull the latest invoice from Stripe, summarize the charge, and offer to walk through line items if useful.

For integration setup: link the relevant doc from docs.acme.com, then offer a 15-minute screen-share if Growth or Enterprise tier.

For feature requests: thank them, log the request in our PM tool, and tell them we'll notify them if it ships. Do not commit to a date.

## Closing

Always end with "Is there anything else I can help with?" Always include a ticket number at the bottom of the reply. Always sign off as "— Acme Support".

## Misc reminders

Remember to be helpful. Remember to be empathetic. Remember to be polite. Be the kind of support agent you'd want to talk to. Always do your best. Keep responses concise but thorough. Provide value in every interaction. Treat every customer as if they were your only customer.

## Final note

This prompt was last updated on 2024-08-12 by the support team. If you see anything outdated, flag it. The team meets every Tuesday at 10am PT to review prompt changes.
"""

_DEMO_USER_PROMPT = (
    "Hi — I'm Sarah from Northwind. Our Stripe integration stopped pulling new "
    "transactions yesterday around 3pm. We're on Growth. Can you help?"
)


def seed_demo() -> Dict[str, Any]:
    init_db()
    run = create_surgeon(
        name="Acme Support Prompt — bloat audit",
        description="Sample Surgeon run: a 600-token customer-support system prompt with several visibly-bolted-on sections.",
        system_prompt=_DEMO_SYSTEM_PROMPT,
        user_prompt=_DEMO_USER_PROMPT,
        candidate_provider="OpenAI",
        candidate_model="gpt-4o-mini",
        temperature=0.4,
        n_replays=3,
        monthly_calls=50_000,
        dryrun=True,
    )
    # Execute synchronously so the UI sees a finished run when the demo loads.
    from src.providers.provider_factory import ProviderFactory  # local import to avoid cycle
    payload, _ = run_surgeon(run["id"], provider_factory=ProviderFactory(), confirm_live=False)
    return payload.get("surgeon") or run
