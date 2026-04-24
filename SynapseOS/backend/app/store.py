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
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                title      TEXT NOT NULL,
                body       TEXT NOT NULL,
                tags       TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL,
                embedding  BLOB NOT NULL
            )
            """
        )
        con.execute("CREATE INDEX IF NOT EXISTS idx_notes_created ON notes(created_at)")


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
    return {
        "id": row["id"],
        "title": row["title"],
        "body": row["body"],
        "tags": json.loads(row["tags"]),
        "created_at": row["created_at"],
    }


def bulk_add(items: Iterable[tuple[str, str, list[str]]]) -> list[int]:
    return [add_note(t, b, g) for (t, b, g) in items]
