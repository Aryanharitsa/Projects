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
