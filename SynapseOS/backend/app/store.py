"""SQLite-backed persistence for notes + cached embeddings.

We store the embedding vector alongside each note as a blob of packed
floats. Synapses (edges) are *not* materialized — they're recomputed from
embeddings on every `/graph` request. That keeps the write path cheap and
lets us tune the similarity threshold at read time without a migration.
For a single-user second-brain with O(10^3) notes this is comfortably fast.
"""

from __future__ import annotations

import json
import sqlite3
import struct
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .embed import DIM, embed

_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "synapse.db"


def _iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _pack(vec: tuple[float, ...] | list[float]) -> bytes:
    return struct.pack(f"{DIM}f", *vec)


def _unpack(blob: bytes) -> tuple[float, ...]:
    return struct.unpack(f"{DIM}f", blob)


@contextmanager
def _conn():
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(_DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    finally:
        con.close()


def init_db() -> None:
    with _conn() as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS notes (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                title        TEXT NOT NULL,
                body         TEXT NOT NULL,
                tags         TEXT NOT NULL DEFAULT '[]',
                created_at   TEXT NOT NULL,
                embedding    BLOB NOT NULL,
                last_seen_at TEXT
            )
            """
        )
        con.execute("CREATE INDEX IF NOT EXISTS idx_notes_created ON notes(created_at)")
        # Lightweight migration for installs predating the `last_seen_at`
        # column. `ALTER TABLE … ADD COLUMN` is idempotent only if we
        # gate on schema inspection; PRAGMA + check-and-add keeps repeat
        # startups cheap.
        cols = {row["name"] for row in con.execute("PRAGMA table_info(notes)").fetchall()}
        if "last_seen_at" not in cols:
            con.execute("ALTER TABLE notes ADD COLUMN last_seen_at TEXT")

        # Trails: curated, replayable walks through the synapse graph.
        # `steps` is a JSON array of `{note_id, caption}` dicts; we store
        # it as TEXT so the order is preserved without an additional
        # join table. Reads are O(trail_size) which is fine — trails are
        # human-curated and rarely exceed a couple dozen steps.
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS trails (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                title      TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                steps      TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                origin     TEXT NOT NULL DEFAULT 'manual'
            )
            """
        )
        con.execute("CREATE INDEX IF NOT EXISTS idx_trails_updated ON trails(updated_at)")

        # Compass: persistent research-session questions + per-question
        # read markers. ``compass_reads`` is its own table (not a flag
        # on ``notes``) because a single note can be "read for question
        # A" but "still cold for question B" — coverage is per-question
        # state, not global. ``ON DELETE CASCADE`` against ``notes``
        # would be ideal but SQLite needs the FK pragma flipped on per
        # connection; we instead clean up dangling rows lazily on read
        # via ``reads_for`` which joins against ``notes``.
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS compass_questions (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                text         TEXT NOT NULL,
                created_at   TEXT NOT NULL,
                archived_at  TEXT
            )
            """
        )
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_compass_q_created "
            "ON compass_questions(created_at)"
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS compass_reads (
                question_id  INTEGER NOT NULL,
                note_id      INTEGER NOT NULL,
                read_at      TEXT NOT NULL,
                PRIMARY KEY (question_id, note_id)
            )
            """
        )
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_compass_reads_q "
            "ON compass_reads(question_id)"
        )

        # Signal: persistent watches over Compass questions. ``UNIQUE
        # (question_id)`` enforces the one-watch-per-question invariant
        # so re-pinning refreshes rather than duplicates. The snapshot
        # is stored as a JSON blob — this table is read once and diffed
        # in Python, so column-level indexing isn't worth the write cost.
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS signal_watches (
                id                 INTEGER PRIMARY KEY AUTOINCREMENT,
                question_id        INTEGER NOT NULL UNIQUE,
                snapshot           TEXT NOT NULL,
                pinned_at          TEXT NOT NULL,
                last_refreshed_at  TEXT
            )
            """
        )
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_signal_watches_pinned "
            "ON signal_watches(pinned_at)"
        )


def add_note(title: str, body: str, tags: list[str]) -> int:
    vec = embed(f"{title}\n\n{body}")
    with _conn() as con:
        cur = con.execute(
            "INSERT INTO notes(title, body, tags, created_at, embedding) VALUES (?, ?, ?, ?, ?)",
            (title.strip(), body.strip(), json.dumps(tags), _iso_now(), _pack(vec)),
        )
        return int(cur.lastrowid)


def delete_note(note_id: int) -> bool:
    with _conn() as con:
        cur = con.execute("DELETE FROM notes WHERE id = ?", (note_id,))
        return cur.rowcount > 0


def get_note(note_id: int) -> dict | None:
    with _conn() as con:
        row = con.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
        return _row_to_note(row) if row else None


def all_notes() -> list[dict]:
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM notes ORDER BY created_at ASC, id ASC"
        ).fetchall()
        return [_row_to_note(r) for r in rows]


def touch_note(note_id: int, *, when: str | None = None) -> bool:
    """Record that the user just looked at this note.

    Used by the Daily Brief flow so the revisit scorer can decay the
    staleness term for recently-surfaced notes. Returns ``False`` if the
    note doesn't exist so the caller can 404 cleanly.
    """
    ts = when or _iso_now()
    with _conn() as con:
        cur = con.execute(
            "UPDATE notes SET last_seen_at = ? WHERE id = ?", (ts, note_id)
        )
        return cur.rowcount > 0


def last_seen_map() -> dict[int, str | None]:
    """`{ note_id: iso_string | None }` for every note in the store."""
    with _conn() as con:
        rows = con.execute("SELECT id, last_seen_at FROM notes").fetchall()
        return {int(r["id"]): r["last_seen_at"] for r in rows}


def all_embeddings() -> list[tuple[int, tuple[float, ...]]]:
    with _conn() as con:
        rows = con.execute("SELECT id, embedding FROM notes").fetchall()
        return [(r["id"], _unpack(r["embedding"])) for r in rows]


def count() -> int:
    with _conn() as con:
        (n,) = con.execute("SELECT COUNT(*) FROM notes").fetchone()
        return int(n)


def reset() -> None:
    with _conn() as con:
        con.execute("DELETE FROM notes")
        con.execute("DELETE FROM sqlite_sequence WHERE name='notes'")


def _row_to_note(row: sqlite3.Row) -> dict:
    # last_seen_at is read defensively: SQLite Row's keys() is cheap, and
    # tolerating its absence keeps the loader compatible with seed-test
    # rigs that mock notes without going through `init_db`.
    last_seen = row["last_seen_at"] if "last_seen_at" in row.keys() else None
    return {
        "id": row["id"],
        "title": row["title"],
        "body": row["body"],
        "tags": json.loads(row["tags"]),
        "created_at": row["created_at"],
        "last_seen_at": last_seen,
    }


def bulk_add(items: Iterable[tuple[str, str, list[str]]]) -> list[int]:
    return [add_note(t, b, g) for (t, b, g) in items]


# ---------------------------------------------------------------- trails

def _normalize_steps(steps: list[dict]) -> list[dict]:
    """Clean + de-duplicate consecutive repeats. Empty captions allowed."""
    out: list[dict] = []
    last_id: int | None = None
    for s in steps or []:
        nid = int(s.get("note_id"))
        cap = (s.get("caption") or "").strip()
        if nid == last_id:
            # Collapse accidental double-clicks. Keep the newer caption if
            # the older one was empty so the user's intent isn't lost.
            if cap and not out[-1].get("caption"):
                out[-1]["caption"] = cap
            continue
        out.append({"note_id": nid, "caption": cap})
        last_id = nid
    return out


def _row_to_trail(row: sqlite3.Row) -> dict:
    return {
        "id": int(row["id"]),
        "title": row["title"],
        "description": row["description"],
        "steps": json.loads(row["steps"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "origin": row["origin"],
    }


def add_trail(
    title: str,
    description: str,
    steps: list[dict],
    origin: str = "manual",
) -> int:
    now = _iso_now()
    payload = json.dumps(_normalize_steps(steps))
    with _conn() as con:
        cur = con.execute(
            "INSERT INTO trails(title, description, steps, created_at, updated_at, origin) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (title.strip() or "Untitled trail", description.strip(), payload, now, now, origin),
        )
        return int(cur.lastrowid)


def list_trails() -> list[dict]:
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM trails ORDER BY updated_at DESC, id DESC"
        ).fetchall()
        return [_row_to_trail(r) for r in rows]


def get_trail(trail_id: int) -> dict | None:
    with _conn() as con:
        row = con.execute("SELECT * FROM trails WHERE id = ?", (trail_id,)).fetchone()
        return _row_to_trail(row) if row else None


def update_trail(
    trail_id: int,
    *,
    title: str | None = None,
    description: str | None = None,
    steps: list[dict] | None = None,
) -> bool:
    """Partial update. Returns False if the trail doesn't exist."""
    with _conn() as con:
        row = con.execute("SELECT * FROM trails WHERE id = ?", (trail_id,)).fetchone()
        if not row:
            return False
        new_title = (title.strip() if title is not None else row["title"]) or "Untitled trail"
        new_desc = description.strip() if description is not None else row["description"]
        new_steps = (
            json.dumps(_normalize_steps(steps))
            if steps is not None
            else row["steps"]
        )
        con.execute(
            "UPDATE trails SET title=?, description=?, steps=?, updated_at=? WHERE id=?",
            (new_title, new_desc, new_steps, _iso_now(), trail_id),
        )
        return True


def append_trail_step(trail_id: int, note_id: int, caption: str = "") -> bool:
    with _conn() as con:
        row = con.execute("SELECT steps FROM trails WHERE id = ?", (trail_id,)).fetchone()
        if not row:
            return False
        steps = json.loads(row["steps"])
        steps.append({"note_id": int(note_id), "caption": (caption or "").strip()})
        con.execute(
            "UPDATE trails SET steps=?, updated_at=? WHERE id=?",
            (json.dumps(_normalize_steps(steps)), _iso_now(), trail_id),
        )
        return True


def delete_trail(trail_id: int) -> bool:
    with _conn() as con:
        cur = con.execute("DELETE FROM trails WHERE id = ?", (trail_id,))
        return cur.rowcount > 0


def trails_count() -> int:
    with _conn() as con:
        (n,) = con.execute("SELECT COUNT(*) FROM trails").fetchone()
        return int(n)


# ---------------------------------------------------------------- compass

def add_question(text: str) -> int:
    """Persist a new research question. Returns its id."""
    with _conn() as con:
        cur = con.execute(
            "INSERT INTO compass_questions(text, created_at) VALUES (?, ?)",
            (text.strip(), _iso_now()),
        )
        return int(cur.lastrowid)


def list_questions(*, include_archived: bool = False) -> list[dict]:
    """List questions newest-first. Each row carries ``reads_count`` and
    ``last_read_at`` already aggregated so the rail can render without a
    second query per question."""
    with _conn() as con:
        rows = con.execute(
            """
            SELECT q.id, q.text, q.created_at, q.archived_at,
                   COUNT(r.note_id) AS reads_count,
                   MAX(r.read_at) AS last_read_at
            FROM compass_questions q
            LEFT JOIN compass_reads r ON r.question_id = q.id
            GROUP BY q.id
            ORDER BY q.created_at DESC, q.id DESC
            """
        ).fetchall()
        out: list[dict] = []
        for r in rows:
            archived = r["archived_at"]
            if archived and not include_archived:
                continue
            out.append(
                {
                    "id": int(r["id"]),
                    "text": r["text"],
                    "created_at": r["created_at"],
                    "archived_at": archived,
                    "reads_count": int(r["reads_count"] or 0),
                    "last_read_at": r["last_read_at"],
                }
            )
        return out


def get_question(qid: int) -> dict | None:
    with _conn() as con:
        row = con.execute(
            "SELECT id, text, created_at, archived_at "
            "FROM compass_questions WHERE id = ?",
            (qid,),
        ).fetchone()
        if not row:
            return None
        return {
            "id": int(row["id"]),
            "text": row["text"],
            "created_at": row["created_at"],
            "archived_at": row["archived_at"],
        }


def archive_question(qid: int) -> bool:
    with _conn() as con:
        cur = con.execute(
            "UPDATE compass_questions SET archived_at = ? "
            "WHERE id = ? AND archived_at IS NULL",
            (_iso_now(), qid),
        )
        if cur.rowcount > 0:
            return True
        # Hard-delete the reads + the row so a re-create starts clean.
        exists = con.execute(
            "SELECT 1 FROM compass_questions WHERE id = ?", (qid,)
        ).fetchone()
        if not exists:
            return False
        # Already archived; treat as no-op success.
        return True


def delete_question(qid: int) -> bool:
    """Hard-delete a question and all of its read markers."""
    with _conn() as con:
        cur = con.execute("DELETE FROM compass_questions WHERE id = ?", (qid,))
        con.execute("DELETE FROM compass_reads WHERE question_id = ?", (qid,))
        return cur.rowcount > 0


def mark_read(qid: int, note_id: int, *, when: str | None = None) -> bool:
    """Record that the user engaged with ``note_id`` for ``qid``.

    Idempotent on the primary key — re-marking refreshes the ``read_at``
    timestamp. Returns ``False`` if either the question or the note has
    been deleted (so the caller can 404 cleanly without a second probe).
    """
    ts = when or _iso_now()
    with _conn() as con:
        q_exists = con.execute(
            "SELECT 1 FROM compass_questions WHERE id = ?", (qid,)
        ).fetchone()
        if not q_exists:
            return False
        n_exists = con.execute(
            "SELECT 1 FROM notes WHERE id = ?", (note_id,)
        ).fetchone()
        if not n_exists:
            return False
        con.execute(
            """
            INSERT INTO compass_reads(question_id, note_id, read_at)
            VALUES (?, ?, ?)
            ON CONFLICT(question_id, note_id) DO UPDATE SET read_at = excluded.read_at
            """,
            (qid, note_id, ts),
        )
        return True


def unmark_read(qid: int, note_id: int) -> bool:
    with _conn() as con:
        cur = con.execute(
            "DELETE FROM compass_reads WHERE question_id = ? AND note_id = ?",
            (qid, note_id),
        )
        return cur.rowcount > 0


def reads_for(qid: int) -> dict[int, str]:
    """Return ``{note_id: read_at}`` for this question, filtered to notes
    that still exist (lazy cleanup of dangling rows from deleted notes)."""
    with _conn() as con:
        rows = con.execute(
            """
            SELECT r.note_id, r.read_at
            FROM compass_reads r
            JOIN notes n ON n.id = r.note_id
            WHERE r.question_id = ?
            """,
            (qid,),
        ).fetchall()
        return {int(r["note_id"]): r["read_at"] for r in rows}


def questions_count() -> int:
    with _conn() as con:
        (n,) = con.execute(
            "SELECT COUNT(*) FROM compass_questions WHERE archived_at IS NULL"
        ).fetchone()
        return int(n)


# ---------------------------------------------------------------- signal


def upsert_signal_watch(qid: int, snapshot_json: str) -> dict:
    """Create or refresh a watch on ``qid``. Idempotent per question:
    a second call updates the snapshot in-place and stamps
    ``last_refreshed_at`` so the delta viewer treats it as a re-baseline.

    Returns the row shape ``{question_id, snapshot, pinned_at,
    last_refreshed_at}`` — pinned_at is only set on first pin and never
    moves; refresh advances ``last_refreshed_at`` only.
    """
    now = _iso_now()
    with _conn() as con:
        existing = con.execute(
            "SELECT id, pinned_at FROM signal_watches WHERE question_id = ?",
            (qid,),
        ).fetchone()
        if existing:
            con.execute(
                "UPDATE signal_watches SET snapshot = ?, last_refreshed_at = ? "
                "WHERE question_id = ?",
                (snapshot_json, now, qid),
            )
            pinned_at = existing["pinned_at"]
            last_refreshed_at = now
        else:
            con.execute(
                "INSERT INTO signal_watches(question_id, snapshot, pinned_at, "
                "last_refreshed_at) VALUES (?, ?, ?, NULL)",
                (qid, snapshot_json, now),
            )
            pinned_at = now
            last_refreshed_at = None
        return {
            "question_id": qid,
            "snapshot": snapshot_json,
            "pinned_at": pinned_at,
            "last_refreshed_at": last_refreshed_at,
        }


def delete_signal_watch(qid: int) -> bool:
    with _conn() as con:
        cur = con.execute(
            "DELETE FROM signal_watches WHERE question_id = ?", (qid,)
        )
        return cur.rowcount > 0


def get_signal_watch(qid: int) -> dict | None:
    with _conn() as con:
        row = con.execute(
            "SELECT question_id, snapshot, pinned_at, last_refreshed_at "
            "FROM signal_watches WHERE question_id = ?",
            (qid,),
        ).fetchone()
        if not row:
            return None
        return {
            "question_id": int(row["question_id"]),
            "snapshot": row["snapshot"],
            "pinned_at": row["pinned_at"],
            "last_refreshed_at": row["last_refreshed_at"],
        }


def list_signal_watches() -> list[dict]:
    """Return every active watch. Joins against ``compass_questions`` so
    we silently drop watches whose underlying question was deleted — a
    hard-delete of the question is the correct signal that the watch is
    dead too, and forcing the caller to filter is boilerplate.
    """
    with _conn() as con:
        rows = con.execute(
            """
            SELECT w.question_id, w.snapshot, w.pinned_at, w.last_refreshed_at,
                   q.text AS question_text, q.created_at AS q_created_at,
                   q.archived_at AS q_archived_at
            FROM signal_watches w
            JOIN compass_questions q ON q.id = w.question_id
            ORDER BY w.pinned_at DESC
            """
        ).fetchall()
        return [
            {
                "question_id": int(r["question_id"]),
                "snapshot": r["snapshot"],
                "pinned_at": r["pinned_at"],
                "last_refreshed_at": r["last_refreshed_at"],
                "question_text": r["question_text"],
                "question_created_at": r["q_created_at"],
                "question_archived_at": r["q_archived_at"],
            }
            for r in rows
        ]


def signal_watched_question_ids() -> set[int]:
    """Cheap probe used by rails that need to know which Compass
    questions are currently pinned (e.g. to render the pin/unpin toggle
    without loading the full snapshot)."""
    with _conn() as con:
        rows = con.execute(
            "SELECT question_id FROM signal_watches"
        ).fetchall()
        return {int(r["question_id"]) for r in rows}


def signal_watches_count() -> int:
    with _conn() as con:
        (n,) = con.execute("SELECT COUNT(*) FROM signal_watches").fetchone()
        return int(n)
