"""Rubrics Studio — first-class, versioned judge rubrics with anchor-driven scoring.

The existing ``judge.py`` accepts an inline rubric (``[{name, description, weight}]``)
and emits one composite per candidate. That works for casual "score this 1-5"
flows, but a real evaluation workflow needs:

* **Persistence** — name, save, search, star rubrics the way Library treats
  prompts. Eval Suites can then reference a rubric by id instead of pasting
  JSON.
* **Versioning** — every meaningful edit to dimensions or anchors creates a
  new revision (append-only, like ``prompt_versions``), so you can compare
  judgements before and after a rubric tweak — or restore an older revision.
* **Per-dimension anchors** — domain rubrics ("Groundedness", "Tone safety",
  "Code correctness") only work when each dimension carries its own 0/5/10
  *anchor descriptions*. The judge prompt then renders those anchors so the
  LLM scores against an explicit yardstick, not its own intuition.
* **Per-dimension rationale** — the judge returns ``{score, rationale}`` per
  dimension, not a single composite + one line. The composite is computed
  *server-side* from the per-dimension scores and the rubric weights so a
  misbehaving judge can't poison the math.
* **A judgement log** — every "Test this rubric" call is persisted with the
  prompt, response, dim scores, latency, and cost, so the stats endpoint can
  surface usage, top-models-per-rubric, and dim-score distributions.

Schema lives in the same SQLite DB as ``history`` / ``prompts`` / ``evals``,
so a single backup captures everything. Tables are guarded with
``CREATE IF NOT EXISTS`` so cold start is free.

Public surface (intentionally narrow so a future Postgres swap is one day):
``create_rubric``, ``list_rubrics``, ``get_rubric``, ``set_rubric_meta``,
``update_rubric``, ``delete_rubric``, ``get_revision``, ``restore_revision``,
``judge_with_rubric``, ``list_judgements``, ``delete_judgement``, ``stats``,
``seed_rubrics``.
"""
from __future__ import annotations

import json
import re
import sqlite3
import time
import uuid
from contextlib import contextmanager
from typing import Any, Dict, List, Optional, Tuple

from src import history  # share DB path + lock
from src.pricing import estimate_cost

_DB_LOCK = history._DB_LOCK  # noqa: SLF001 — deliberate cross-module sharing


@contextmanager
def _conn():
    with history._conn() as con:  # noqa: SLF001
        yield con


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

SCORE_MIN, SCORE_MAX = 0, 10  # per-dimension score scale
ANCHOR_LEVELS = ("0", "5", "10")  # the levels we render to the judge

_SCHEMA = """
CREATE TABLE IF NOT EXISTS rubrics (
    id                   TEXT PRIMARY KEY,
    name                 TEXT NOT NULL,
    description          TEXT,
    tag                  TEXT,
    starred              INTEGER NOT NULL DEFAULT 0,
    current_revision_num INTEGER NOT NULL DEFAULT 1,
    created_at           REAL NOT NULL,
    updated_at           REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS rubric_revisions (
    id                TEXT PRIMARY KEY,
    rubric_id         TEXT NOT NULL,
    revision_num      INTEGER NOT NULL,
    dimensions_json   TEXT NOT NULL,
    judge_addendum    TEXT,
    note              TEXT,
    parent_revision   INTEGER,
    created_at        REAL NOT NULL,
    FOREIGN KEY (rubric_id) REFERENCES rubrics(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS rubric_judgements (
    id                TEXT PRIMARY KEY,
    rubric_id         TEXT NOT NULL,
    revision_num      INTEGER NOT NULL,
    judge_provider    TEXT NOT NULL,
    judge_model       TEXT NOT NULL,
    candidate_provider TEXT,
    candidate_model    TEXT,
    user_prompt       TEXT NOT NULL,
    system_prompt     TEXT,
    response          TEXT NOT NULL,
    composite         REAL,
    dim_scores_json   TEXT NOT NULL,
    summary           TEXT,
    raw_judge_text    TEXT,
    latency           REAL NOT NULL DEFAULT 0,
    cost_usd          REAL NOT NULL DEFAULT 0,
    input_tokens      INTEGER NOT NULL DEFAULT 0,
    output_tokens     INTEGER NOT NULL DEFAULT 0,
    note              TEXT,
    created_at        REAL NOT NULL,
    FOREIGN KEY (rubric_id) REFERENCES rubrics(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_rubrics_updated      ON rubrics(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_rubrics_starred      ON rubrics(starred);
CREATE INDEX IF NOT EXISTS idx_rubric_revs_rubric   ON rubric_revisions(rubric_id, revision_num DESC);
CREATE INDEX IF NOT EXISTS idx_rubric_judg_rubric   ON rubric_judgements(rubric_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_rubric_judg_model    ON rubric_judgements(candidate_provider, candidate_model);
"""


def init_db() -> None:
    """Create tables on first run. Idempotent."""
    with _DB_LOCK, _conn() as con:
        con.executescript(_SCHEMA)


def _now() -> float:
    return time.time()


# ---------------------------------------------------------------------------
# Dimension validation & weight normalisation
# ---------------------------------------------------------------------------

def _coerce_anchor_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _normalise_dimensions(
    dimensions: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Validate dimensions and re-normalise weights to sum to 100 (integers).

    Strategy: keep declared weights, scale them to sum-to-100 with the largest
    remainder method so the UI sees clean integers and the composite math is
    deterministic.
    """
    if not isinstance(dimensions, list) or not dimensions:
        raise ValueError("rubric must have at least one dimension")
    cleaned: List[Dict[str, Any]] = []
    for raw in dimensions:
        if not isinstance(raw, dict):
            continue
        name = (raw.get("name") or "").strip()
        if not name:
            continue
        desc = (raw.get("description") or "").strip()
        try:
            weight = float(raw.get("weight", 0) or 0)
        except (TypeError, ValueError):
            weight = 0.0
        if weight < 0:
            weight = 0.0
        anchors_in = raw.get("anchors") or {}
        anchors: Dict[str, str] = {}
        for level in ANCHOR_LEVELS:
            anchors[level] = _coerce_anchor_text(anchors_in.get(level))
        cleaned.append({
            "name": name[:80],
            "description": desc[:480],
            "weight": weight,
            "anchors": anchors,
        })
    if not cleaned:
        raise ValueError("rubric must have at least one named dimension")

    # Re-pack weights to integer percents summing to 100 via largest remainder.
    total = sum(d["weight"] for d in cleaned)
    if total <= 0:
        share = 100.0 / len(cleaned)
        for d in cleaned:
            d["weight"] = share

    scaled = [(d, d["weight"] * 100.0 / sum(x["weight"] for x in cleaned)) for d in cleaned]
    floors = [(d, s, int(s)) for d, s in scaled]
    remainder = 100 - sum(f[2] for f in floors)
    # Distribute leftover percentage points to dimensions with the largest
    # fractional part (most "deserving" of an upgrade).
    ranked = sorted(range(len(floors)), key=lambda i: -(floors[i][1] - floors[i][2]))
    weights = [f[2] for f in floors]
    for i in ranked[: max(0, remainder)]:
        weights[i] += 1
    for d, w in zip(cleaned, weights):
        d["weight"] = int(w)
    return cleaned


def _composite(scores: Dict[str, Any], dimensions: List[Dict[str, Any]]) -> float:
    """Weighted 0-100 composite from per-dimension scores (0-10) and rubric weights."""
    if not dimensions:
        return 0.0
    total = 0.0
    for d in dimensions:
        try:
            raw = float(scores.get(d["name"], 0) or 0)
        except (TypeError, ValueError):
            raw = 0.0
        clipped = max(SCORE_MIN, min(SCORE_MAX, raw))
        # 0-10 → 0-1 → weighted contribution, then ×100 at the end
        total += (clipped / SCORE_MAX) * (d["weight"] / 100.0)
    return round(total * 100.0, 2)


def _dims_signature(dimensions: List[Dict[str, Any]], addendum: str) -> str:
    """Deterministic signature used to detect whether a save changes the rubric.

    Used by ``update_rubric`` so a metadata-only save (e.g. star toggle) doesn't
    create a new revision.
    """
    payload = {
        "dims": [
            {
                "name": d["name"],
                "description": d["description"],
                "weight": d["weight"],
                "anchors": dict(d["anchors"]),
            }
            for d in dimensions
        ],
        "addendum": (addendum or "").strip(),
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

def _row_to_rubric(row: sqlite3.Row) -> Dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "description": row["description"] or "",
        "tag": row["tag"] or "",
        "starred": bool(row["starred"]),
        "current_revision_num": int(row["current_revision_num"] or 1),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _row_to_revision(row: sqlite3.Row) -> Dict[str, Any]:
    try:
        dims = json.loads(row["dimensions_json"])
    except (TypeError, ValueError, json.JSONDecodeError):
        dims = []
    return {
        "id": row["id"],
        "rubric_id": row["rubric_id"],
        "revision_num": int(row["revision_num"]),
        "dimensions": dims,
        "judge_addendum": row["judge_addendum"] or "",
        "note": row["note"] or "",
        "parent_revision": row["parent_revision"],
        "created_at": row["created_at"],
    }


def _row_to_judgement(row: sqlite3.Row) -> Dict[str, Any]:
    try:
        dim_scores = json.loads(row["dim_scores_json"])
    except (TypeError, ValueError, json.JSONDecodeError):
        dim_scores = []
    return {
        "id": row["id"],
        "rubric_id": row["rubric_id"],
        "revision_num": int(row["revision_num"]),
        "judge_provider": row["judge_provider"],
        "judge_model": row["judge_model"],
        "candidate_provider": row["candidate_provider"] or "",
        "candidate_model": row["candidate_model"] or "",
        "user_prompt": row["user_prompt"],
        "system_prompt": row["system_prompt"] or "",
        "response": row["response"],
        "composite": row["composite"],
        "dim_scores": dim_scores,
        "summary": row["summary"] or "",
        "latency": row["latency"],
        "cost_usd": row["cost_usd"],
        "input_tokens": int(row["input_tokens"] or 0),
        "output_tokens": int(row["output_tokens"] or 0),
        "note": row["note"] or "",
        "created_at": row["created_at"],
    }


def create_rubric(
    *,
    name: str,
    description: str = "",
    tag: str = "",
    dimensions: List[Dict[str, Any]],
    judge_addendum: str = "",
    note: str = "",
) -> Dict[str, Any]:
    init_db()
    name = (name or "").strip()
    if not name:
        raise ValueError("name is required")
    norm = _normalise_dimensions(dimensions)
    rid = uuid.uuid4().hex
    revid = uuid.uuid4().hex
    now = _now()
    with _DB_LOCK, _conn() as con:
        con.execute(
            """INSERT INTO rubrics (id, name, description, tag, starred,
                                    current_revision_num, created_at, updated_at)
               VALUES (?, ?, ?, ?, 0, 1, ?, ?)""",
            (rid, name, description.strip(), (tag or "").strip(), now, now),
        )
        con.execute(
            """INSERT INTO rubric_revisions
                 (id, rubric_id, revision_num, dimensions_json,
                  judge_addendum, note, parent_revision, created_at)
               VALUES (?, ?, 1, ?, ?, ?, NULL, ?)""",
            (revid, rid, json.dumps(norm),
             (judge_addendum or "").strip(),
             (note or "").strip(), now),
        )
    return get_rubric(rid) or {}


def list_rubrics(
    *,
    q: Optional[str] = None,
    tag: Optional[str] = None,
    starred_only: bool = False,
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
    if tag:
        clauses.append("LOWER(tag) = ?")
        params.append(tag.lower().strip())
    if starred_only:
        clauses.append("starred = 1")
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    with _DB_LOCK, _conn() as con:
        total = con.execute(f"SELECT COUNT(*) AS c FROM rubrics {where}", params).fetchone()["c"]
        rows = con.execute(
            f"""SELECT * FROM rubrics
                {where}
                ORDER BY starred DESC, updated_at DESC
                LIMIT ? OFFSET ?""",
            (*params, int(limit), int(offset)),
        ).fetchall()
        rubrics: List[Dict[str, Any]] = []
        for row in rows:
            r = _row_to_rubric(row)
            # Attach revision summary (dim count, n_judgements) — keeps the list
            # informative without a second round-trip.
            rev = con.execute(
                """SELECT dimensions_json FROM rubric_revisions
                   WHERE rubric_id = ? AND revision_num = ?""",
                (r["id"], r["current_revision_num"]),
            ).fetchone()
            try:
                dims = json.loads(rev["dimensions_json"]) if rev else []
            except (TypeError, ValueError, json.JSONDecodeError):
                dims = []
            r["n_dimensions"] = len(dims)
            r["dimension_names"] = [d.get("name") for d in dims if d.get("name")]
            r["n_judgements"] = int(con.execute(
                "SELECT COUNT(*) AS c FROM rubric_judgements WHERE rubric_id = ?",
                (r["id"],),
            ).fetchone()["c"])
            r["avg_composite"] = _avg_composite(con, r["id"])
            rubrics.append(r)
        return rubrics, int(total)


def _avg_composite(con: sqlite3.Connection, rubric_id: str) -> Optional[float]:
    row = con.execute(
        """SELECT AVG(composite) AS avg
           FROM rubric_judgements
           WHERE rubric_id = ? AND composite IS NOT NULL""",
        (rubric_id,),
    ).fetchone()
    return round(float(row["avg"]), 2) if row and row["avg"] is not None else None


def get_rubric(rubric_id: str, *, include_revisions: bool = True,
                recent_judgements: int = 8) -> Optional[Dict[str, Any]]:
    init_db()
    with _DB_LOCK, _conn() as con:
        row = con.execute("SELECT * FROM rubrics WHERE id = ?", (rubric_id,)).fetchone()
        if not row:
            return None
        rubric = _row_to_rubric(row)
        # Current revision
        cur = con.execute(
            """SELECT * FROM rubric_revisions
               WHERE rubric_id = ? AND revision_num = ?""",
            (rubric_id, rubric["current_revision_num"]),
        ).fetchone()
        if cur:
            rev = _row_to_revision(cur)
            rubric["dimensions"] = rev["dimensions"]
            rubric["judge_addendum"] = rev["judge_addendum"]
            rubric["current_revision"] = rev
        else:
            rubric["dimensions"] = []
            rubric["judge_addendum"] = ""
        # All revisions
        if include_revisions:
            revs = con.execute(
                """SELECT * FROM rubric_revisions
                   WHERE rubric_id = ?
                   ORDER BY revision_num DESC""",
                (rubric_id,),
            ).fetchall()
            rubric["revisions"] = [_row_to_revision(r) for r in revs]
        # Aggregates
        rubric["n_judgements"] = int(con.execute(
            "SELECT COUNT(*) AS c FROM rubric_judgements WHERE rubric_id = ?",
            (rubric_id,),
        ).fetchone()["c"])
        rubric["avg_composite"] = _avg_composite(con, rubric_id)
        rubric["total_cost"] = round(float(con.execute(
            "SELECT COALESCE(SUM(cost_usd), 0) AS s FROM rubric_judgements WHERE rubric_id = ?",
            (rubric_id,),
        ).fetchone()["s"]), 4)
        if recent_judgements and recent_judgements > 0:
            jr = con.execute(
                """SELECT * FROM rubric_judgements
                   WHERE rubric_id = ?
                   ORDER BY created_at DESC
                   LIMIT ?""",
                (rubric_id, int(recent_judgements)),
            ).fetchall()
            rubric["recent_judgements"] = [_row_to_judgement(r) for r in jr]
        else:
            rubric["recent_judgements"] = []
        return rubric


def set_rubric_meta(
    rubric_id: str,
    *,
    name: Optional[str] = None,
    description: Optional[str] = None,
    tag: Optional[str] = None,
    starred: Optional[bool] = None,
) -> bool:
    init_db()
    fields: List[str] = []
    params: List[Any] = []
    if name is not None:
        n = name.strip()
        if not n:
            return False
        fields.append("name = ?")
        params.append(n)
    if description is not None:
        fields.append("description = ?")
        params.append(description.strip())
    if tag is not None:
        fields.append("tag = ?")
        params.append(tag.strip())
    if starred is not None:
        fields.append("starred = ?")
        params.append(1 if starred else 0)
    if not fields:
        return False
    fields.append("updated_at = ?")
    params.append(_now())
    params.append(rubric_id)
    with _DB_LOCK, _conn() as con:
        cur = con.execute(
            f"UPDATE rubrics SET {', '.join(fields)} WHERE id = ?",
            params,
        )
        return cur.rowcount > 0


def update_rubric(
    rubric_id: str,
    *,
    dimensions: List[Dict[str, Any]],
    judge_addendum: str = "",
    change_note: str = "",
) -> Optional[Dict[str, Any]]:
    """Create a new revision iff dimensions or addendum actually changed.

    Returns the full rubric on success, ``None`` if the rubric doesn't exist,
    and the unchanged rubric (with no new revision) if the payload is identical
    to the current revision. The current revision pointer always moves forward.
    """
    init_db()
    norm = _normalise_dimensions(dimensions)
    new_sig = _dims_signature(norm, judge_addendum)
    with _DB_LOCK, _conn() as con:
        row = con.execute(
            "SELECT * FROM rubrics WHERE id = ?", (rubric_id,),
        ).fetchone()
        if not row:
            return None
        cur_rev = con.execute(
            """SELECT * FROM rubric_revisions
               WHERE rubric_id = ? AND revision_num = ?""",
            (rubric_id, int(row["current_revision_num"])),
        ).fetchone()
        cur_sig = None
        if cur_rev:
            try:
                cur_dims = json.loads(cur_rev["dimensions_json"])
            except (TypeError, ValueError, json.JSONDecodeError):
                cur_dims = []
            cur_sig = _dims_signature(cur_dims, cur_rev["judge_addendum"] or "")
        is_noop = cur_sig == new_sig and not change_note
        if not is_noop:
            next_num = int(row["current_revision_num"]) + 1
            revid = uuid.uuid4().hex
            now = _now()
            con.execute(
                """INSERT INTO rubric_revisions
                     (id, rubric_id, revision_num, dimensions_json,
                      judge_addendum, note, parent_revision, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (revid, rubric_id, next_num, json.dumps(norm),
                 (judge_addendum or "").strip(),
                 (change_note or "").strip(),
                 int(row["current_revision_num"]), now),
            )
            con.execute(
                "UPDATE rubrics SET current_revision_num = ?, updated_at = ? WHERE id = ?",
                (next_num, now, rubric_id),
            )
    # `get_rubric` reacquires the lock — call it AFTER the with-block to avoid
    # deadlocking on the non-reentrant ``threading.Lock``.
    return get_rubric(rubric_id)


def restore_revision(rubric_id: str, revision_num: int, *, note: str = "") -> Optional[Dict[str, Any]]:
    """Copy the chosen historical revision forward as a new current revision."""
    init_db()
    with _DB_LOCK, _conn() as con:
        row = con.execute("SELECT * FROM rubrics WHERE id = ?", (rubric_id,)).fetchone()
        if not row:
            return None
        target = con.execute(
            "SELECT * FROM rubric_revisions WHERE rubric_id = ? AND revision_num = ?",
            (rubric_id, int(revision_num)),
        ).fetchone()
        if not target:
            return None
        next_num = int(row["current_revision_num"]) + 1
        now = _now()
        revid = uuid.uuid4().hex
        con.execute(
            """INSERT INTO rubric_revisions
                 (id, rubric_id, revision_num, dimensions_json,
                  judge_addendum, note, parent_revision, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (revid, rubric_id, next_num, target["dimensions_json"],
             target["judge_addendum"] or "",
             (note or f"Restored from r{revision_num}").strip(),
             int(target["revision_num"]), now),
        )
        con.execute(
            "UPDATE rubrics SET current_revision_num = ?, updated_at = ? WHERE id = ?",
            (next_num, now, rubric_id),
        )
    return get_rubric(rubric_id)


def get_revision(rubric_id: str, revision_num: int) -> Optional[Dict[str, Any]]:
    init_db()
    with _DB_LOCK, _conn() as con:
        row = con.execute(
            "SELECT * FROM rubric_revisions WHERE rubric_id = ? AND revision_num = ?",
            (rubric_id, int(revision_num)),
        ).fetchone()
        return _row_to_revision(row) if row else None


def delete_rubric(rubric_id: str) -> bool:
    init_db()
    with _DB_LOCK, _conn() as con:
        # Defensive: ensure child rows go even if PRAGMA foreign_keys is off.
        con.execute("DELETE FROM rubric_judgements WHERE rubric_id = ?", (rubric_id,))
        con.execute("DELETE FROM rubric_revisions WHERE rubric_id = ?", (rubric_id,))
        cur = con.execute("DELETE FROM rubrics WHERE id = ?", (rubric_id,))
        return cur.rowcount > 0


def list_judgements(
    rubric_id: str,
    *,
    limit: int = 50,
    offset: int = 0,
) -> Tuple[List[Dict[str, Any]], int]:
    init_db()
    with _DB_LOCK, _conn() as con:
        total = con.execute(
            "SELECT COUNT(*) AS c FROM rubric_judgements WHERE rubric_id = ?",
            (rubric_id,),
        ).fetchone()["c"]
        rows = con.execute(
            """SELECT * FROM rubric_judgements
               WHERE rubric_id = ?
               ORDER BY created_at DESC
               LIMIT ? OFFSET ?""",
            (rubric_id, int(limit), int(offset)),
        ).fetchall()
        return [_row_to_judgement(r) for r in rows], int(total)


def delete_judgement(judgement_id: str) -> bool:
    init_db()
    with _DB_LOCK, _conn() as con:
        cur = con.execute("DELETE FROM rubric_judgements WHERE id = ?", (judgement_id,))
        return cur.rowcount > 0


# ---------------------------------------------------------------------------
# Judging engine
# ---------------------------------------------------------------------------

_JUDGE_SYSTEM = (
    "You are a calibrated, anchor-driven LLM-as-judge. You score the "
    "*single* response provided against the supplied rubric. For each "
    "dimension you award an integer score from 0 to 10 by matching the "
    "response to the closest anchor description. Use the FULL 0-10 range — "
    "a mediocre response should land near 5, a refusal or off-topic answer "
    "should land near 0-2. Return ONLY valid JSON in the exact shape "
    "specified. Do not flatter, do not hedge, do not add commentary outside "
    "the JSON."
)

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def _extract_json(text: str) -> Optional[Any]:
    if not text:
        return None
    m = _JSON_FENCE_RE.search(text)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
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
                        chunk = text[start:i + 1]
                        try:
                            return json.loads(chunk)
                        except json.JSONDecodeError:
                            break
            start = text.find(opener, start + 1)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def build_rubric_judge_prompt(
    *,
    user_prompt: str,
    system_prompt: str,
    response: str,
    dimensions: List[Dict[str, Any]],
    judge_addendum: str = "",
    candidate_label: str = "",
) -> str:
    """Render the body the judge LLM sees, anchors included."""
    body_blocks = []
    for i, d in enumerate(dimensions, start=1):
        anchors = d.get("anchors") or {}
        anchor_lines = []
        for lvl in ANCHOR_LEVELS:
            txt = (anchors.get(lvl) or "").strip()
            if txt:
                anchor_lines.append(f"     - **{lvl}**: {txt}")
        anchor_blob = "\n".join(anchor_lines) if anchor_lines else "     (no anchor — use your best calibration)"
        body_blocks.append(
            f"  {i}. **{d['name']}** ({d['weight']}%): {d.get('description') or '(no description)'}\n"
            f"     anchors:\n{anchor_blob}"
        )
    dims_block = "\n".join(body_blocks)
    dim_names = [d["name"] for d in dimensions]
    schema_example = {
        "scores": {k: 7 for k in dim_names},
        "rationales": {k: "one short sentence" for k in dim_names},
        "summary": "one sentence describing the overall verdict",
    }

    sys_line = f"\n[Original system prompt used by the candidate]\n{system_prompt}\n" if system_prompt else ""
    cand_line = f"\n[Candidate]\n{candidate_label}\n" if candidate_label else ""
    addendum = f"\n[Judging guidance]\n{judge_addendum}\n" if (judge_addendum or "").strip() else ""

    resp_body = (response or "").strip() or "(empty response)"

    return (
        f"You are scoring a single LLM answer against an explicit rubric.\n"
        f"{cand_line}"
        f"\n[User prompt]\n{user_prompt}\n"
        f"{sys_line}"
        f"{addendum}"
        f"\n[Rubric — each dimension scored 0-10 against the anchors below]\n{dims_block}\n"
        f"\n[Response]\n{resp_body}\n"
        f"\n[Output schema]\n"
        f"Return ONLY a JSON object of the shape below. The `scores` object MUST contain "
        f"exactly these keys: {json.dumps(dim_names)}. Each score is an integer in [0, 10]. "
        f"The `rationales` object uses the same keys; each value is one sentence (≤30 words). "
        f"`summary` is a single sentence verdict.\n\n"
        f"{json.dumps(schema_example, indent=2)}\n"
    )


def parse_rubric_response(
    text: str,
    dimensions: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Parse the judge's raw text into ``{scores, rationales, summary, parsed_ok}``.

    Always returns a populated payload — missing keys are filled with score 0 and
    a "(judge did not return a verdict)" rationale so downstream code is safe.
    """
    dim_names = [d["name"] for d in dimensions]
    scores: Dict[str, int] = {k: 0 for k in dim_names}
    rationales: Dict[str, str] = {k: "(judge did not return a verdict)" for k in dim_names}
    summary = ""
    parsed_ok = False

    parsed = _extract_json(text)
    if isinstance(parsed, dict):
        parsed_ok = True
        scores_in = parsed.get("scores") or {}
        rats_in = parsed.get("rationales") or {}
        # Tolerate case-insensitive keys.
        scores_lookup = {str(k).strip().lower(): v for k, v in (scores_in.items() if isinstance(scores_in, dict) else [])}
        rats_lookup = {str(k).strip().lower(): v for k, v in (rats_in.items() if isinstance(rats_in, dict) else [])}
        for name in dim_names:
            key = name.strip().lower()
            raw = scores_lookup.get(key)
            try:
                n = int(round(float(raw)))
            except (TypeError, ValueError):
                n = SCORE_MIN
            scores[name] = max(SCORE_MIN, min(SCORE_MAX, n))
            rationale = rats_lookup.get(key)
            if isinstance(rationale, str) and rationale.strip():
                rationales[name] = rationale.strip()[:280]
        summary_text = parsed.get("summary")
        if isinstance(summary_text, str):
            summary = summary_text.strip()[:480]
    return {
        "scores": scores,
        "rationales": rationales,
        "summary": summary,
        "parsed_ok": parsed_ok,
    }


def judge_with_rubric(
    rubric_id: str,
    *,
    user_prompt: str,
    response: str,
    judge_provider: str,
    judge_model: str,
    system_prompt: str = "",
    candidate_provider: str = "",
    candidate_model: str = "",
    note: str = "",
    provider_factory,
    persist: bool = True,
    revision_num: Optional[int] = None,
) -> Tuple[Dict[str, Any], int]:
    """Score ``response`` against ``rubric`` using a chosen judge model.

    Returns ``(payload, http_status)``. The payload always includes the
    per-dim scores, rationales, summary, the *server-computed* composite,
    judge metrics (latency, cost, tokens), and the judgement id when persisted.
    """
    init_db()
    if not (user_prompt or "").strip():
        return {"success": False, "error": "user_prompt is required"}, 400
    if not (response or "").strip():
        return {"success": False, "error": "response is required"}, 400
    if not judge_provider or not judge_model:
        return {"success": False, "error": "judge_provider and judge_model are required"}, 400

    rubric = get_rubric(rubric_id, include_revisions=False, recent_judgements=0)
    if not rubric:
        return {"success": False, "error": "rubric not found"}, 404

    if revision_num is not None and int(revision_num) != int(rubric["current_revision_num"]):
        rev = get_revision(rubric_id, int(revision_num))
        if not rev:
            return {"success": False, "error": "revision not found"}, 404
        dimensions = rev["dimensions"]
        addendum = rev["judge_addendum"]
        used_rev = int(rev["revision_num"])
    else:
        dimensions = rubric.get("dimensions") or []
        addendum = rubric.get("judge_addendum") or ""
        used_rev = int(rubric["current_revision_num"])

    if not dimensions:
        return {"success": False, "error": "rubric has no dimensions"}, 400

    try:
        judge_instance = provider_factory.create_provider(judge_provider)
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "error": f"judge provider unavailable: {exc}"}, 400
    if not judge_instance:
        return {"success": False, "error": f"provider {judge_provider} not available"}, 400

    cand_label = ""
    if candidate_provider or candidate_model:
        cand_label = f"{candidate_provider or '?'}:{candidate_model or '?'}"

    body = build_rubric_judge_prompt(
        user_prompt=user_prompt,
        system_prompt=system_prompt or "",
        response=response,
        dimensions=dimensions,
        judge_addendum=addendum or "",
        candidate_label=cand_label,
    )
    messages = [
        {"role": "system", "content": _JUDGE_SYSTEM},
        {"role": "user", "content": body},
    ]

    started = time.time()
    try:
        resp = judge_instance.make_request(judge_model, messages)
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "error": f"judge call failed: {exc}"}, 502
    elapsed = round(time.time() - started, 3)

    err = resp.get("error")
    if resp.get("status") != "success" or (isinstance(err, dict) and err):
        msg = err.get("message") if isinstance(err, dict) else (err or "judge upstream error")
        return {"success": False, "error": msg}, 502

    raw_text = resp.get("content", "") or ""
    parsed = parse_rubric_response(raw_text, dimensions)
    composite = _composite(parsed["scores"], dimensions)

    in_tok = int(resp.get("input_tokens", 0) or 0)
    out_tok = int(resp.get("output_tokens", 0) or 0)
    cost = float(estimate_cost(judge_model, in_tok, out_tok) or 0.0)

    # Compose per-dim verdict structure for the UI: easier to render than two
    # parallel dicts.
    dim_verdicts: List[Dict[str, Any]] = []
    for d in dimensions:
        name = d["name"]
        score = int(parsed["scores"].get(name, 0))
        weight = int(d.get("weight") or 0)
        rationale = parsed["rationales"].get(name, "")
        dim_verdicts.append({
            "name": name,
            "weight": weight,
            "score": score,
            "max_score": SCORE_MAX,
            "rationale": rationale,
            "contribution": round((score / SCORE_MAX) * weight, 2),  # 0-weight
        })

    judgement_id = uuid.uuid4().hex
    payload = {
        "success": True,
        "id": judgement_id if persist else None,
        "rubric_id": rubric_id,
        "rubric_name": rubric["name"],
        "revision_num": used_rev,
        "composite": composite,
        "scores": parsed["scores"],
        "rationales": parsed["rationales"],
        "summary": parsed["summary"],
        "parsed_ok": parsed["parsed_ok"],
        "dim_verdicts": dim_verdicts,
        "dimensions": dimensions,
        "judge": {
            "provider": judge_provider,
            "model": judge_model,
            "latency": elapsed,
            "input_tokens": in_tok,
            "output_tokens": out_tok,
            "total_tokens": in_tok + out_tok,
            "cost_usd": cost,
        },
        "candidate": {
            "provider": candidate_provider or "",
            "model": candidate_model or "",
        },
        "raw_judge_text": raw_text,
    }

    if persist:
        with _DB_LOCK, _conn() as con:
            con.execute(
                """INSERT INTO rubric_judgements
                     (id, rubric_id, revision_num, judge_provider, judge_model,
                      candidate_provider, candidate_model,
                      user_prompt, system_prompt, response,
                      composite, dim_scores_json, summary, raw_judge_text,
                      latency, cost_usd, input_tokens, output_tokens,
                      note, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (judgement_id, rubric_id, used_rev, judge_provider, judge_model,
                 candidate_provider or None, candidate_model or None,
                 user_prompt, system_prompt or "", response,
                 composite, json.dumps(dim_verdicts),
                 parsed["summary"], raw_text,
                 elapsed, cost, in_tok, out_tok,
                 (note or "").strip(), _now()),
            )

    return payload, 200


# ---------------------------------------------------------------------------
# Stats — portfolio rollup for the UI banner
# ---------------------------------------------------------------------------

def stats() -> Dict[str, Any]:
    init_db()
    with _DB_LOCK, _conn() as con:
        n_rubrics = int(con.execute("SELECT COUNT(*) AS c FROM rubrics").fetchone()["c"])
        n_starred = int(con.execute("SELECT COUNT(*) AS c FROM rubrics WHERE starred = 1").fetchone()["c"])
        n_judgements = int(con.execute("SELECT COUNT(*) AS c FROM rubric_judgements").fetchone()["c"])
        total_cost = round(float(con.execute(
            "SELECT COALESCE(SUM(cost_usd), 0) AS s FROM rubric_judgements"
        ).fetchone()["s"]), 4)
        avg_composite = con.execute(
            "SELECT AVG(composite) AS a FROM rubric_judgements WHERE composite IS NOT NULL"
        ).fetchone()["a"]
        avg_composite = round(float(avg_composite), 2) if avg_composite is not None else None

        # Top rubric by usage.
        top_rubric_row = con.execute("""
            SELECT r.id, r.name, COUNT(rj.id) AS uses,
                   AVG(rj.composite) AS avg_comp
            FROM rubrics r
            LEFT JOIN rubric_judgements rj ON rj.rubric_id = r.id
            GROUP BY r.id, r.name
            HAVING uses > 0
            ORDER BY uses DESC, avg_comp DESC
            LIMIT 1
        """).fetchone()
        top_rubric = None
        if top_rubric_row:
            top_rubric = {
                "id": top_rubric_row["id"],
                "name": top_rubric_row["name"],
                "uses": int(top_rubric_row["uses"]),
                "avg_composite": round(float(top_rubric_row["avg_comp"]), 2) if top_rubric_row["avg_comp"] is not None else None,
            }

        # Best model across all rubrics (candidate side, min 3 judgements).
        best_model_row = con.execute("""
            SELECT candidate_provider, candidate_model,
                   COUNT(*) AS n,
                   AVG(composite) AS avg_comp
            FROM rubric_judgements
            WHERE candidate_model IS NOT NULL
              AND candidate_model <> ''
              AND composite IS NOT NULL
            GROUP BY candidate_provider, candidate_model
            HAVING n >= 3
            ORDER BY avg_comp DESC, n DESC
            LIMIT 1
        """).fetchone()
        best_model = None
        if best_model_row:
            best_model = {
                "provider": best_model_row["candidate_provider"] or "",
                "model": best_model_row["candidate_model"] or "",
                "n_judgements": int(best_model_row["n"]),
                "avg_composite": round(float(best_model_row["avg_comp"]), 2),
            }

        # Top judges (which judge model do you reach for most).
        judge_rows = con.execute("""
            SELECT judge_provider, judge_model,
                   COUNT(*) AS n,
                   AVG(composite) AS avg_comp,
                   AVG(latency) AS avg_lat,
                   SUM(cost_usd) AS total_cost
            FROM rubric_judgements
            GROUP BY judge_provider, judge_model
            ORDER BY n DESC
            LIMIT 5
        """).fetchall()
        top_judges = [
            {
                "provider": r["judge_provider"],
                "model": r["judge_model"],
                "n_uses": int(r["n"]),
                "avg_composite": round(float(r["avg_comp"]), 2) if r["avg_comp"] is not None else None,
                "avg_latency": round(float(r["avg_lat"]), 3) if r["avg_lat"] is not None else None,
                "total_cost": round(float(r["total_cost"] or 0), 4),
            }
            for r in judge_rows
        ]

        # Recent activity for the strip.
        recent_rows = con.execute("""
            SELECT rj.id, rj.rubric_id, rj.candidate_provider, rj.candidate_model,
                   rj.judge_provider, rj.judge_model, rj.composite, rj.created_at,
                   r.name AS rubric_name
            FROM rubric_judgements rj
            LEFT JOIN rubrics r ON r.id = rj.rubric_id
            ORDER BY rj.created_at DESC
            LIMIT 8
        """).fetchall()
        recent = [
            {
                "id": r["id"],
                "rubric_id": r["rubric_id"],
                "rubric_name": r["rubric_name"] or "(deleted)",
                "candidate_provider": r["candidate_provider"] or "",
                "candidate_model": r["candidate_model"] or "",
                "judge_provider": r["judge_provider"] or "",
                "judge_model": r["judge_model"] or "",
                "composite": r["composite"],
                "created_at": r["created_at"],
            }
            for r in recent_rows
        ]

        return {
            "n_rubrics": n_rubrics,
            "n_starred": n_starred,
            "n_judgements": n_judgements,
            "total_cost": total_cost,
            "avg_composite": avg_composite,
            "top_rubric": top_rubric,
            "best_model": best_model,
            "top_judges": top_judges,
            "recent": recent,
        }


# ---------------------------------------------------------------------------
# Seed — first-launch starter rubrics so the UI is never empty
# ---------------------------------------------------------------------------

_SEED_DEFS: List[Dict[str, Any]] = [
    {
        "name": "Code Review",
        "description": "Domain rubric for evaluating code answers. Heavy weight on correctness, paid attention to idiomatic style and edge-case handling.",
        "tag": "code",
        "judge_addendum": (
            "Treat code that does not run, does not compile, or fails the stated "
            "task as a correctness failure (score ≤ 3 on Correctness). Reward "
            "answers that proactively call out edge cases (empty input, "
            "overflow, concurrency) even when the prompt didn't ask."
        ),
        "dimensions": [
            {
                "name": "Correctness",
                "description": "Does the code do exactly what the prompt asked, with no bugs or fabrications?",
                "weight": 40,
                "anchors": {
                    "0": "Doesn't compile / runs but produces wrong output / hallucinated APIs.",
                    "5": "Compiles and handles the happy path but misses obvious edge cases.",
                    "10": "Passes happy path AND named edge cases; logic provably correct.",
                },
            },
            {
                "name": "Idiomatic",
                "description": "Uses the language's standard idioms, naming, and patterns.",
                "weight": 20,
                "anchors": {
                    "0": "Reads like a transliteration from another language; ignores stdlib.",
                    "5": "Functional but uses awkward patterns; mixes styles.",
                    "10": "Reads like senior code in this language — clean, idiomatic, conventional.",
                },
            },
            {
                "name": "Edge Cases",
                "description": "Handles empty, null, malformed, oversized, and adversarial inputs.",
                "weight": 20,
                "anchors": {
                    "0": "Crashes / silently corrupts on any non-happy-path input.",
                    "5": "Handles the obvious nil/empty case but ignores adversarial input.",
                    "10": "Explicit guards for empty, malformed, oversized, and concurrent inputs.",
                },
            },
            {
                "name": "Readability",
                "description": "Names, structure, and density a teammate can scan in 10 seconds.",
                "weight": 20,
                "anchors": {
                    "0": "Single-letter names, no structure, dead code, magic numbers everywhere.",
                    "5": "Decent names, some structure, one or two hard-to-follow blocks.",
                    "10": "Self-documenting names; intent visible in 10 seconds without comments.",
                },
            },
        ],
    },
    {
        "name": "RAG Faithfulness",
        "description": "Retrieval-augmented answer evaluation. Penalises any claim not grounded in the provided context.",
        "tag": "rag",
        "judge_addendum": (
            "Groundedness is the most severe failure mode here. A confidently "
            "stated fact that is *not* in the provided context should drop "
            "Groundedness to 0-2, even if the rest of the answer is excellent. "
            "Reward explicit citations and admissions of uncertainty."
        ),
        "dimensions": [
            {
                "name": "Groundedness",
                "description": "Every claim is verifiable from the provided retrieval context — no hallucinations.",
                "weight": 40,
                "anchors": {
                    "0": "Multiple confident claims absent from the context.",
                    "5": "Mostly grounded; one or two minor unsupported claims.",
                    "10": "Every claim explicitly traceable to a passage in the context.",
                },
            },
            {
                "name": "Relevance",
                "description": "Answer addresses the user's actual question, not adjacent topics.",
                "weight": 25,
                "anchors": {
                    "0": "Off-topic or tangential.",
                    "5": "Addresses the question but with significant detours.",
                    "10": "Bullseye — answers the question and only the question.",
                },
            },
            {
                "name": "Citation",
                "description": "Cites the source passage(s) so a reader can verify each claim.",
                "weight": 20,
                "anchors": {
                    "0": "No citations or made-up references.",
                    "5": "Some citations, but the mapping to specific claims is unclear.",
                    "10": "Each claim cites the specific passage that supports it.",
                },
            },
            {
                "name": "Calibration",
                "description": "Confidence matches evidence; admits gaps in the context.",
                "weight": 15,
                "anchors": {
                    "0": "Confident assertions on topics the context doesn't cover.",
                    "5": "Generally calibrated but over-claims in places.",
                    "10": "Explicitly notes what the context covers vs. what it doesn't.",
                },
            },
        ],
    },
    {
        "name": "Customer Support",
        "description": "For evaluating support replies. Heavy weight on tone safety and resolution clarity.",
        "tag": "support",
        "judge_addendum": (
            "Any reply that blames the customer, contains a snark or sarcasm, "
            "or fails to acknowledge their stated frustration is a Tone "
            "failure (≤ 3). Concrete next steps and a clear resolution path "
            "matter more than apologies."
        ),
        "dimensions": [
            {
                "name": "Tone",
                "description": "Professional, empathetic, never blames the customer.",
                "weight": 30,
                "anchors": {
                    "0": "Blames the customer, sarcastic, or robotic.",
                    "5": "Polite but transactional; doesn't acknowledge frustration.",
                    "10": "Warm, professional, explicitly acknowledges the issue.",
                },
            },
            {
                "name": "Resolution",
                "description": "Provides a concrete path to fix the customer's problem.",
                "weight": 30,
                "anchors": {
                    "0": "No actionable next step.",
                    "5": "Generic next step ('please try again').",
                    "10": "Specific, ordered next steps with what to expect at each.",
                },
            },
            {
                "name": "Accuracy",
                "description": "Statements about the product / policy / refund are factually correct.",
                "weight": 25,
                "anchors": {
                    "0": "Contains incorrect policy or product claims.",
                    "5": "Mostly accurate, one or two vague claims.",
                    "10": "Every product / policy claim is precise and correct.",
                },
            },
            {
                "name": "Brevity",
                "description": "Respects the customer's time — no padding or repetition.",
                "weight": 15,
                "anchors": {
                    "0": "Wall of text with apology / fluff loops.",
                    "5": "A few extraneous paragraphs; could be 30% shorter.",
                    "10": "Tight — every sentence advances the resolution.",
                },
            },
        ],
    },
    {
        "name": "Creative Writing",
        "description": "For evaluating short-form creative prose. Voice and surprise matter more than information density.",
        "tag": "creative",
        "judge_addendum": (
            "Penalise generic, AI-flavoured prose — the kind that smells like "
            "training data. Reward a distinct voice, a memorable image, a "
            "structural choice that surprised you, or a line you'd actually "
            "quote. Information density is not a virtue here."
        ),
        "dimensions": [
            {
                "name": "Voice",
                "description": "A distinct narrative voice that feels written by *somebody*.",
                "weight": 30,
                "anchors": {
                    "0": "Generic LLM voice; could have been any model on any prompt.",
                    "5": "Some character, but slips into safe corporate prose.",
                    "10": "Distinct, consistent voice from first line to last.",
                },
            },
            {
                "name": "Imagery",
                "description": "Concrete, surprising sensory detail; metaphors that earn their place.",
                "weight": 25,
                "anchors": {
                    "0": "Generic adjectives; nothing visual or sensory.",
                    "5": "Some image-rich moments, mixed with abstractions.",
                    "10": "Multiple memorable images; metaphors illuminate, don't decorate.",
                },
            },
            {
                "name": "Structure",
                "description": "Shape — beginning, middle, end. Choices about what to withhold and when.",
                "weight": 25,
                "anchors": {
                    "0": "Bag of sentences; no narrative arc or rhythm.",
                    "5": "Linear and competent but no structural surprise.",
                    "10": "Earned shape; one or more structural choices you notice.",
                },
            },
            {
                "name": "Restraint",
                "description": "Trusts the reader; resists explaining, summarising, or moralising.",
                "weight": 20,
                "anchors": {
                    "0": "Tells me what to feel; explains its own metaphors.",
                    "5": "Mostly trusts the reader; one or two telling moments.",
                    "10": "Implies; never explains. Endings land without commentary.",
                },
            },
        ],
    },
]


def seed_rubrics() -> List[Dict[str, Any]]:
    """Idempotently insert the four starter rubrics.

    Existing rubrics with the same name are left alone (so a re-seed doesn't
    clobber a user-edited copy). Returns the *full* current list of rubrics
    matching the seed names, so the UI can immediately render them.
    """
    init_db()
    created: List[Dict[str, Any]] = []
    with _DB_LOCK, _conn() as con:
        existing_names = {row["name"] for row in con.execute("SELECT name FROM rubrics").fetchall()}
    for spec in _SEED_DEFS:
        if spec["name"] in existing_names:
            continue
        r = create_rubric(
            name=spec["name"],
            description=spec["description"],
            tag=spec.get("tag", ""),
            dimensions=spec["dimensions"],
            judge_addendum=spec.get("judge_addendum", ""),
            note="Seeded — starter rubric",
        )
        # Star the first seed so the UI immediately surfaces something.
        if spec["name"] == "Code Review":
            set_rubric_meta(r["id"], starred=True)
        created.append(r)
    # Always return the canonical seeded set (whether we just made it or it
    # already existed) so the UI can deeplink to one.
    with _DB_LOCK, _conn() as con:
        rows = con.execute(
            """SELECT * FROM rubrics
               WHERE name IN ({})
               ORDER BY created_at""".format(",".join("?" * len(_SEED_DEFS))),
            tuple(spec["name"] for spec in _SEED_DEFS),
        ).fetchall()
        seeds = [_row_to_rubric(r) for r in rows]
    return seeds
