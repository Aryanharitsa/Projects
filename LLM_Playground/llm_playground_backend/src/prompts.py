"""Prompt Library — versioned prompts linked back to Arena runs.

The playground had every ingredient for prompt iteration (Arena, Judge,
History, Vote) but no way to track *which version of the prompt* produced
which run. This module closes that loop.

Schema (shares ``history.db`` so a single backup captures everything):

* ``prompts``           — one row per logical prompt. Owns name, tags,
                          starred bit, and a ``current_version_id`` pointer
                          to the head of the version chain.
* ``prompt_versions``   — append-only chain of revisions. Each row carries
                          the full ``system_prompt`` + ``user_template`` at
                          that revision, a ``version_num`` monotonically
                          increasing within its prompt, a ``parent_version_id``
                          (lets us reconstruct branched edits), and an
                          author-supplied ``note``.
* ``runs.prompt_version_id`` — new nullable FK added in ``init_db`` via
                          ``ALTER TABLE`` (idempotent — schema migrations are
                          guarded by a ``PRAGMA table_info`` introspection).

The public surface is intentionally narrow (``create_prompt``,
``list_prompts``, ``get_prompt``, ``add_version``, ``set_prompt_meta``,
``delete_prompt``, ``link_run``, ``runs_for_version``, ``diff_versions``,
``stats``) so a future swap to Postgres is a one-day job.

Diffs use the stdlib ``difflib.unified_diff`` over the joined
``system_prompt + "\\n---\\n" + user_template`` text so a single diff hunk
covers both fields. The endpoint also surfaces per-version run metrics
(``n_runs``, ``avg_composite``, ``best_model``) so the UI can show *score
deltas* alongside *text deltas* — the whole point of versioning prompts.
"""
from __future__ import annotations

import difflib
import json
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from typing import Any, Dict, List, Optional, Tuple

from src import history  # share DB path + lock

_DB_LOCK = history._DB_LOCK  # noqa: SLF001 — deliberate cross-module sharing


@contextmanager
def _conn():
    with history._conn() as con:  # noqa: SLF001
        yield con


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS prompts (
    id                  TEXT PRIMARY KEY,
    name                TEXT NOT NULL,
    created_at          REAL NOT NULL,
    updated_at          REAL NOT NULL,
    current_version_id  TEXT,
    starred             INTEGER NOT NULL DEFAULT 0,
    tag                 TEXT,
    note                TEXT
);

CREATE TABLE IF NOT EXISTS prompt_versions (
    id                  TEXT PRIMARY KEY,
    prompt_id           TEXT NOT NULL,
    version_num         INTEGER NOT NULL,
    system_prompt       TEXT NOT NULL DEFAULT '',
    user_template       TEXT NOT NULL DEFAULT '',
    created_at          REAL NOT NULL,
    parent_version_id   TEXT,
    note                TEXT,
    FOREIGN KEY (prompt_id) REFERENCES prompts(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_prompts_updated     ON prompts(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_prompts_starred     ON prompts(starred);
CREATE INDEX IF NOT EXISTS idx_pversions_prompt    ON prompt_versions(prompt_id);
CREATE INDEX IF NOT EXISTS idx_pversions_created   ON prompt_versions(created_at DESC);
"""


def init_db() -> None:
    """Create tables on first run and migrate ``runs`` if needed.

    ``ALTER TABLE … ADD COLUMN`` is not idempotent in SQLite, so we probe
    ``PRAGMA table_info(runs)`` first. This keeps us migration-safe on every
    boot without dragging Alembic in.
    """
    with _DB_LOCK, _conn() as con:
        con.executescript(_SCHEMA)
        # Add the FK column to history's `runs` table if it isn't there yet.
        cols = {r[1] for r in con.execute("PRAGMA table_info(runs)").fetchall()}
        if "prompt_version_id" not in cols:
            try:
                con.execute("ALTER TABLE runs ADD COLUMN prompt_version_id TEXT")
            except sqlite3.OperationalError:
                pass  # racing booter beat us; harmless
            con.execute(
                "CREATE INDEX IF NOT EXISTS idx_runs_pversion "
                "ON runs(prompt_version_id)"
            )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> float:
    return time.time()


def _row_to_prompt(row: sqlite3.Row) -> Dict[str, Any]:
    return {
        "id":                 row["id"],
        "name":                row["name"],
        "created_at":          row["created_at"],
        "updated_at":          row["updated_at"],
        "current_version_id":  row["current_version_id"],
        "starred":             bool(row["starred"]),
        "tag":                 row["tag"],
        "note":                row["note"],
    }


def _row_to_version(row: sqlite3.Row) -> Dict[str, Any]:
    return {
        "id":                  row["id"],
        "prompt_id":           row["prompt_id"],
        "version_num":         int(row["version_num"]),
        "system_prompt":       row["system_prompt"] or "",
        "user_template":       row["user_template"] or "",
        "created_at":          row["created_at"],
        "parent_version_id":   row["parent_version_id"],
        "note":                row["note"] or "",
    }


def _version_stats(con: sqlite3.Connection, version_id: str) -> Dict[str, Any]:
    """Per-version run summary. Run rows pre-dating the FK column show 0."""
    row = con.execute(
        """SELECT COUNT(*)                                           AS n_runs,
                  COALESCE(AVG(judge_top_score), 0)                  AS avg_composite,
                  COALESCE(SUM(total_cost_usd), 0)                   AS total_cost,
                  MAX(created_at)                                    AS last_run_at,
                  COALESCE(SUM(judged), 0)                           AS n_judged
           FROM runs
           WHERE prompt_version_id = ?""",
        (version_id,),
    ).fetchone()
    n_judged = int(row["n_judged"]) if row["n_judged"] is not None else 0
    # judge_top_score is NULL on un-judged rows; AVG ignores NULLs so this is
    # already a "mean across judged runs", but expose 0 when none scored.
    avg_composite = float(row["avg_composite"] or 0.0) if n_judged else 0.0

    best_model: Optional[str] = None
    if n_judged:
        best = con.execute(
            """SELECT judge_winner AS m, COUNT(*) AS wins
               FROM runs
               WHERE prompt_version_id = ?
                 AND judged = 1
                 AND judge_winner IS NOT NULL
               GROUP BY judge_winner
               ORDER BY wins DESC, MAX(judge_top_score) DESC
               LIMIT 1""",
            (version_id,),
        ).fetchone()
        if best:
            best_model = best["m"]

    return {
        "n_runs":        int(row["n_runs"]),
        "n_judged":      n_judged,
        "avg_composite": round(avg_composite, 2),
        "total_cost":    round(float(row["total_cost"] or 0.0), 6),
        "last_run_at":   row["last_run_at"],
        "best_model":    best_model,
    }


# ---------------------------------------------------------------------------
# Public API — prompts
# ---------------------------------------------------------------------------

def create_prompt(
    *,
    name: str,
    system_prompt: str = "",
    user_template: str = "",
    note: str = "",
    tag: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a new prompt with its initial v1."""
    name = (name or "").strip() or "Untitled prompt"
    prompt_id = str(uuid.uuid4())
    version_id = str(uuid.uuid4())
    now = _now()
    with _DB_LOCK, _conn() as con:
        con.execute(
            """INSERT INTO prompts
               (id, name, created_at, updated_at, current_version_id,
                starred, tag, note)
               VALUES (?, ?, ?, ?, ?, 0, ?, '')""",
            (prompt_id, name, now, now, version_id, tag),
        )
        con.execute(
            """INSERT INTO prompt_versions
               (id, prompt_id, version_num, system_prompt, user_template,
                created_at, parent_version_id, note)
               VALUES (?, ?, 1, ?, ?, ?, NULL, ?)""",
            (version_id, prompt_id, system_prompt or "", user_template or "",
             now, note or ""),
        )
    return get_prompt(prompt_id) or {}


def list_prompts(
    *,
    q: Optional[str] = None,
    starred_only: bool = False,
    tag: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> Tuple[List[Dict[str, Any]], int]:
    """List prompts (newest activity first) with version/run summaries."""
    where: List[str] = []
    args: List[Any] = []
    if q:
        where.append("(name LIKE ? OR tag LIKE ?)")
        like = f"%{q}%"
        args += [like, like]
    if starred_only:
        where.append("starred = 1")
    if tag:
        where.append("tag = ?")
        args.append(tag)
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    limit = max(1, min(int(limit), 500))
    offset = max(0, int(offset))

    out: List[Dict[str, Any]] = []
    with _DB_LOCK, _conn() as con:
        total = con.execute(
            f"SELECT COUNT(*) AS c FROM prompts {where_sql}", args
        ).fetchone()["c"]
        rows = con.execute(
            f"""SELECT * FROM prompts {where_sql}
                ORDER BY updated_at DESC
                LIMIT ? OFFSET ?""",
            args + [limit, offset],
        ).fetchall()

        for r in rows:
            p = _row_to_prompt(r)
            # Cheap roll-up per prompt: version count + total runs across all
            # versions + avg composite across all judged runs of this prompt.
            agg = con.execute(
                """SELECT COUNT(*) AS n_versions FROM prompt_versions
                   WHERE prompt_id = ?""",
                (p["id"],),
            ).fetchone()
            p["n_versions"] = int(agg["n_versions"])

            run_agg = con.execute(
                """SELECT COUNT(*) AS n_runs,
                          COALESCE(SUM(judged), 0) AS n_judged,
                          COALESCE(AVG(judge_top_score), 0) AS avg_composite,
                          MAX(created_at) AS last_run_at
                   FROM runs
                   WHERE prompt_version_id IN (
                       SELECT id FROM prompt_versions WHERE prompt_id = ?
                   )""",
                (p["id"],),
            ).fetchone()
            n_judged = int(run_agg["n_judged"] or 0)
            p["n_runs"]        = int(run_agg["n_runs"] or 0)
            p["n_judged"]      = n_judged
            p["avg_composite"] = (
                round(float(run_agg["avg_composite"] or 0.0), 2) if n_judged else 0.0
            )
            p["last_run_at"]   = run_agg["last_run_at"]

            # Score-progression sparkline: judge_top_score per version,
            # ordered v1 → vN. Un-judged versions contribute None which the
            # UI plots as a gap.
            spark_rows = con.execute(
                """SELECT pv.version_num,
                          (SELECT AVG(r.judge_top_score)
                             FROM runs r
                             WHERE r.prompt_version_id = pv.id AND r.judged = 1
                          ) AS s
                   FROM prompt_versions pv
                   WHERE pv.prompt_id = ?
                   ORDER BY pv.version_num ASC""",
                (p["id"],),
            ).fetchall()
            p["score_spark"] = [
                {"v": int(sr["version_num"]),
                 "s": (round(float(sr["s"]), 2) if sr["s"] is not None else None)}
                for sr in spark_rows
            ]

            # Snippet preview of current head version for the card.
            head = con.execute(
                "SELECT system_prompt, user_template, version_num "
                "FROM prompt_versions WHERE id = ?",
                (p["current_version_id"],),
            ).fetchone()
            if head:
                p["current_version_num"] = int(head["version_num"])
                template_preview = (head["user_template"] or "")[:160]
                p["preview"] = template_preview or (head["system_prompt"] or "")[:160]
            else:
                p["current_version_num"] = 0
                p["preview"] = ""
            out.append(p)

    return out, int(total)


def get_prompt(prompt_id: str) -> Optional[Dict[str, Any]]:
    """Full prompt with every version + per-version run stats."""
    if not prompt_id:
        return None
    with _DB_LOCK, _conn() as con:
        row = con.execute("SELECT * FROM prompts WHERE id = ?", (prompt_id,)).fetchone()
        if not row:
            return None
        p = _row_to_prompt(row)
        rows = con.execute(
            """SELECT * FROM prompt_versions
               WHERE prompt_id = ?
               ORDER BY version_num ASC""",
            (prompt_id,),
        ).fetchall()
        versions: List[Dict[str, Any]] = []
        for vrow in rows:
            v = _row_to_version(vrow)
            v["stats"] = _version_stats(con, v["id"])
            versions.append(v)
        p["versions"] = versions
    return p


def add_version(
    prompt_id: str,
    *,
    system_prompt: str = "",
    user_template: str = "",
    note: str = "",
    parent_version_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Append a new revision and advance the prompt's head pointer.

    If the new content is *identical* to the current head, we return that
    head verbatim — refusing to litter the timeline with no-op versions
    (saves the user from accidental double-clicks).
    """
    with _DB_LOCK, _conn() as con:
        row = con.execute(
            "SELECT current_version_id FROM prompts WHERE id = ?", (prompt_id,)
        ).fetchone()
        if not row:
            return None
        current_id = row["current_version_id"]

        # No-op guard
        if current_id:
            curr = con.execute(
                "SELECT system_prompt, user_template FROM prompt_versions WHERE id = ?",
                (current_id,),
            ).fetchone()
            if curr and (curr["system_prompt"] or "") == (system_prompt or "") \
                   and (curr["user_template"] or "") == (user_template or ""):
                # Same content — bump `updated_at` so the prompt floats back
                # to the top of the list but don't create a sibling version.
                con.execute(
                    "UPDATE prompts SET updated_at = ? WHERE id = ?",
                    (_now(), prompt_id),
                )
                return _row_to_version(
                    con.execute(
                        "SELECT * FROM prompt_versions WHERE id = ?", (current_id,)
                    ).fetchone()
                )

        max_v = con.execute(
            "SELECT COALESCE(MAX(version_num), 0) AS m FROM prompt_versions WHERE prompt_id = ?",
            (prompt_id,),
        ).fetchone()["m"]
        next_v = int(max_v) + 1
        version_id = str(uuid.uuid4())
        now = _now()
        con.execute(
            """INSERT INTO prompt_versions
               (id, prompt_id, version_num, system_prompt, user_template,
                created_at, parent_version_id, note)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (version_id, prompt_id, next_v, system_prompt or "",
             user_template or "", now,
             parent_version_id or current_id, note or ""),
        )
        con.execute(
            "UPDATE prompts SET current_version_id = ?, updated_at = ? WHERE id = ?",
            (version_id, now, prompt_id),
        )
        v = _row_to_version(
            con.execute(
                "SELECT * FROM prompt_versions WHERE id = ?", (version_id,)
            ).fetchone()
        )
        v["stats"] = _version_stats(con, version_id)
        return v


def set_prompt_meta(
    prompt_id: str,
    *,
    name: Optional[str] = None,
    starred: Optional[bool] = None,
    tag: Optional[str] = None,
    note: Optional[str] = None,
) -> bool:
    sets: List[str] = []
    args: List[Any] = []
    if name is not None:
        cleaned = name.strip() or "Untitled prompt"
        sets.append("name = ?")
        args.append(cleaned)
    if starred is not None:
        sets.append("starred = ?")
        args.append(1 if starred else 0)
    if tag is not None:
        sets.append("tag = ?")
        args.append(tag.strip() or None)
    if note is not None:
        sets.append("note = ?")
        args.append(note)
    if not sets:
        return False
    sets.append("updated_at = ?")
    args.append(_now())
    args.append(prompt_id)
    with _DB_LOCK, _conn() as con:
        cur = con.execute(
            f"UPDATE prompts SET {', '.join(sets)} WHERE id = ?", args
        )
        return cur.rowcount > 0


def delete_prompt(prompt_id: str) -> bool:
    """Delete the prompt + its version chain. Runs keep their `prompt_version_id`
    pointing at now-dangling rows; that's deliberate — the audit trail of
    *which prompt produced this answer* shouldn't evaporate on cleanup."""
    with _DB_LOCK, _conn() as con:
        cur = con.execute("DELETE FROM prompts WHERE id = ?", (prompt_id,))
        if cur.rowcount > 0:
            con.execute(
                "DELETE FROM prompt_versions WHERE prompt_id = ?", (prompt_id,)
            )
            return True
        return False


def link_run(run_id: str, version_id: str) -> bool:
    """Attach an existing run row to a prompt version (called from /compare)."""
    if not run_id or not version_id:
        return False
    with _DB_LOCK, _conn() as con:
        # Validate version exists — silently skip if not, the run still saves.
        v = con.execute(
            "SELECT id FROM prompt_versions WHERE id = ?", (version_id,)
        ).fetchone()
        if not v:
            return False
        cur = con.execute(
            "UPDATE runs SET prompt_version_id = ? WHERE id = ?",
            (version_id, run_id),
        )
        if cur.rowcount > 0:
            # Bump prompt timestamp so the library list re-sorts after a run.
            con.execute(
                """UPDATE prompts SET updated_at = ?
                   WHERE id = (
                       SELECT prompt_id FROM prompt_versions WHERE id = ?
                   )""",
                (_now(), version_id),
            )
            return True
        return False


def runs_for_version(version_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    """List runs attached to a specific version. Mirrors the History row shape."""
    limit = max(1, min(int(limit), 500))
    with _DB_LOCK, _conn() as con:
        rows = con.execute(
            """SELECT * FROM runs
               WHERE prompt_version_id = ?
               ORDER BY created_at DESC
               LIMIT ?""",
            (version_id, limit),
        ).fetchall()
    return [history._row_to_summary(r) for r in rows]  # noqa: SLF001


# ---------------------------------------------------------------------------
# Diff
# ---------------------------------------------------------------------------

def _joined(v: Dict[str, Any]) -> str:
    """Single text blob for diffing — system + user template separated by a
    sentinel so a diff hunk shows whether the change is in system or template."""
    sys_p = v.get("system_prompt", "") or ""
    usr = v.get("user_template", "") or ""
    return f"## SYSTEM\n{sys_p}\n## USER\n{usr}\n"


def _line_stats(text_a: str, text_b: str) -> Dict[str, int]:
    """Cheap additions/deletions count via SequenceMatcher opcodes."""
    a_lines = text_a.splitlines()
    b_lines = text_b.splitlines()
    sm = difflib.SequenceMatcher(a=a_lines, b=b_lines, autojunk=False)
    add = del_ = 0
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "replace":
            del_ += (i2 - i1)
            add  += (j2 - j1)
        elif tag == "delete":
            del_ += (i2 - i1)
        elif tag == "insert":
            add += (j2 - j1)
    return {"added": add, "removed": del_, "similarity": round(sm.ratio(), 3)}


def diff_versions(a_id: str, b_id: str) -> Optional[Dict[str, Any]]:
    """Unified-diff two versions, plus per-version run stats so the UI can
    show *score delta* alongside *text delta*."""
    if not a_id or not b_id:
        return None
    with _DB_LOCK, _conn() as con:
        rows = con.execute(
            "SELECT * FROM prompt_versions WHERE id IN (?, ?)",
            (a_id, b_id),
        ).fetchall()
        if len(rows) < 2:
            # Either version missing (id might be malformed/dangling), or the
            # client passed the same id twice. Handle both with one error so
            # the frontend reports it uniformly.
            return None
        by_id = {r["id"]: r for r in rows}
        if a_id not in by_id or b_id not in by_id:
            return None
        a_row = by_id[a_id]
        b_row = by_id[b_id]
        a_v = _row_to_version(a_row)
        b_v = _row_to_version(b_row)
        a_v["stats"] = _version_stats(con, a_id)
        b_v["stats"] = _version_stats(con, b_id)

    a_text = _joined(a_v)
    b_text = _joined(b_v)
    a_lines = a_text.splitlines(keepends=False)
    b_lines = b_text.splitlines(keepends=False)
    raw_diff = list(
        difflib.unified_diff(
            a_lines, b_lines,
            fromfile=f"v{a_v['version_num']}",
            tofile=f"v{b_v['version_num']}",
            n=3,
            lineterm="",
        )
    )

    # Parse the unified diff into structured hunks the frontend can render
    # without re-parsing strings.
    hunks: List[Dict[str, Any]] = []
    cur: Optional[Dict[str, Any]] = None
    for line in raw_diff:
        if line.startswith("---") or line.startswith("+++"):
            continue
        if line.startswith("@@"):
            if cur:
                hunks.append(cur)
            cur = {"header": line, "lines": []}
            continue
        if cur is None:
            continue
        if line.startswith("+"):
            cur["lines"].append({"type": "add", "text": line[1:]})
        elif line.startswith("-"):
            cur["lines"].append({"type": "del", "text": line[1:]})
        else:
            cur["lines"].append({"type": "ctx", "text": line[1:] if line.startswith(" ") else line})
    if cur:
        hunks.append(cur)

    stats_sys  = _line_stats(a_v["system_prompt"], b_v["system_prompt"])
    stats_user = _line_stats(a_v["user_template"], b_v["user_template"])
    stats_all  = _line_stats(a_text, b_text)

    # Score delta — judged-runs-only mean. ``None`` on either side stays None.
    a_score = a_v["stats"].get("avg_composite") if a_v["stats"].get("n_judged") else None
    b_score = b_v["stats"].get("avg_composite") if b_v["stats"].get("n_judged") else None
    score_delta = (
        round(float(b_score) - float(a_score), 2)
        if a_score is not None and b_score is not None
        else None
    )

    return {
        "a": a_v,
        "b": b_v,
        "hunks": hunks,
        "raw":   "\n".join(raw_diff),
        "stats": {
            "system":   stats_sys,
            "template": stats_user,
            "overall":  stats_all,
        },
        "score_delta": score_delta,
    }


# ---------------------------------------------------------------------------
# Library-level stats (for the dashboard banner)
# ---------------------------------------------------------------------------

def stats() -> Dict[str, Any]:
    with _DB_LOCK, _conn() as con:
        p_count = con.execute("SELECT COUNT(*) AS c FROM prompts").fetchone()["c"]
        v_count = con.execute("SELECT COUNT(*) AS c FROM prompt_versions").fetchone()["c"]
        r_count = con.execute(
            "SELECT COUNT(*) AS c FROM runs WHERE prompt_version_id IS NOT NULL"
        ).fetchone()["c"]
        avg = con.execute(
            """SELECT COALESCE(AVG(judge_top_score), 0) AS s
               FROM runs
               WHERE prompt_version_id IS NOT NULL AND judged = 1"""
        ).fetchone()["s"]
        # Most-iterated prompts (rough proxy for "where am I focusing?")
        top_rows = con.execute(
            """SELECT p.id, p.name, COUNT(pv.id) AS n_versions
               FROM prompts p
               JOIN prompt_versions pv ON pv.prompt_id = p.id
               GROUP BY p.id
               ORDER BY n_versions DESC, p.updated_at DESC
               LIMIT 5"""
        ).fetchall()
    return {
        "n_prompts":     int(p_count),
        "n_versions":    int(v_count),
        "n_linked_runs": int(r_count),
        "avg_composite": round(float(avg or 0.0), 2),
        "top_iterated": [
            {"id": r["id"], "name": r["name"], "n_versions": int(r["n_versions"])}
            for r in top_rows
        ],
    }


# Initialise on import — main.py imports this module at boot, after history.
init_db()
