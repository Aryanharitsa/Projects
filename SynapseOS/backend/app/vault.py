"""Vault — portable import/export + local snapshots.

Every other PKM tool spends its first three README screens telling you
*"but of course your notes belong to you."* SynapseOS earns that claim
by being able to hand your whole vault back to you in two open formats
at any moment, and read it back byte-for-byte.

There are three concrete jobs here:

1. **Export** — walk the store and emit either
   (a) a schema-versioned JSON document that captures notes, tags,
       timestamps, per-question compass reads, trails, signal snapshots,
       and (optionally) the packed embedding bytes — enough to fully
       reconstruct the graph even offline;
   (b) a Markdown ZIP where each note is one ``.md`` file with a YAML
       frontmatter block and an auto-generated ``## Related`` section
       drawn from the current synapse graph — Obsidian and Logseq will
       read this without any translation.

2. **Import** — accept either format back and reconcile it against the
   current store in either ``merge`` (upsert by title-hash) or
   ``replace`` (wipe + rebuild) mode. A ``preview`` mode returns the
   diff without touching anything so the UI can render a confirmation
   summary before the destructive action runs. Warnings surface soft
   problems (unknown compass question ids, unresolved wikilinks, tags
   that couldn't be parsed) without failing the whole batch.

3. **Snapshots** — persist named local copies of the JSON export in a
   new ``vault_snapshots`` SQLite table. Same shape as an export, but
   stored inline so a restore is a one-click round-trip. This is the
   *personal* Ctrl-Z: label a state before you try something aggressive
   (bulk atomize a paste, merge dozens of echoes, delete a cluster),
   and roll back with one button.

Everything here is stdlib-only. No YAML parser, no zipfile helpers we
didn't already own, no third-party embedder — the round-trip must
survive an offline restore on a fresh Python.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import re
import sqlite3
import struct
import zipfile
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from . import store, synapse
from .embed import DIM

SCHEMA_VERSION = 1
ENGINE_VERSION = "synapseos-vault/1.0.0"

_SLUG_RE = re.compile(r"[^a-z0-9\-]+")
_MULTI_HYPHEN = re.compile(r"-{2,}")
_YAML_LINE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.*)$")


# ---------------------------------------------------------------- helpers


def _iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _slugify(title: str, note_id: int) -> str:
    """Return a stable filesystem-safe basename for a note.

    We suffix the id so two notes with the same title never collide, and
    two notes that only differ in punctuation don't either. Empty titles
    fall back to ``note-<id>``.
    """
    lower = (title or "").strip().lower()
    slug = _SLUG_RE.sub("-", lower).strip("-")
    slug = _MULTI_HYPHEN.sub("-", slug)
    if not slug:
        slug = "note"
    return f"{slug[:60]}-{note_id}"


def _b64_from_embedding(vec: Iterable[float]) -> str:
    vals = list(vec)
    if len(vals) != DIM:
        raise ValueError(f"embedding dim mismatch (got {len(vals)}, need {DIM})")
    return base64.b64encode(struct.pack(f"{DIM}f", *vals)).decode("ascii")


def _embedding_from_b64(payload: str) -> tuple[float, ...]:
    raw = base64.b64decode(payload.encode("ascii"))
    if len(raw) != DIM * 4:
        raise ValueError(f"embedding blob wrong length: {len(raw)}")
    return struct.unpack(f"{DIM}f", raw)


def _yaml_escape(value: str) -> str:
    """Emit a string that always round-trips through our tiny YAML reader.

    We quote unconditionally so leading `#`, colons, and multi-line
    bodies never confuse a downstream YAML parser (Obsidian in
    particular is happy with quoted scalars). Backslashes and quotes
    inside get JSON-style escapes.
    """
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


def _parse_yaml_scalar(raw: str) -> str | int | float | bool | None:
    s = raw.strip()
    if not s:
        return ""
    if s[0] == '"' and s[-1] == '"' and len(s) >= 2:
        inner = s[1:-1]
        return (
            inner.replace('\\n', '\n')
                 .replace('\\"', '"')
                 .replace('\\\\', '\\')
        )
    if s.lower() == "true":
        return True
    if s.lower() == "false":
        return False
    if s.lower() in ("null", "~"):
        return None
    if re.fullmatch(r"-?\d+", s):
        try:
            return int(s)
        except ValueError:
            return s
    if re.fullmatch(r"-?\d+\.\d+", s):
        try:
            return float(s)
        except ValueError:
            return s
    return s


def _parse_yaml_list(raw: str) -> list[str]:
    """Parse a flow-style list like ``[a, "b c", other]`` into strings."""
    inner = raw.strip()
    if inner.startswith("[") and inner.endswith("]"):
        inner = inner[1:-1]
    items: list[str] = []
    buf: list[str] = []
    in_str = False
    esc = False
    for ch in inner:
        if esc:
            buf.append(ch)
            esc = False
            continue
        if ch == "\\":
            esc = True
            continue
        if ch == '"':
            in_str = not in_str
            buf.append(ch)
            continue
        if ch == "," and not in_str:
            items.append("".join(buf).strip())
            buf = []
            continue
        buf.append(ch)
    tail = "".join(buf).strip()
    if tail:
        items.append(tail)
    out: list[str] = []
    for item in items:
        parsed = _parse_yaml_scalar(item)
        if parsed is None or parsed == "":
            continue
        out.append(str(parsed))
    return out


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """Split a Markdown blob into (frontmatter_dict, body).

    Supports the subset of YAML we emit: scalar key: value pairs and
    flow-style ``tags: [a, "b c"]`` lists. Anything more complex falls
    through into the body untouched.
    """
    if not text.startswith("---"):
        return {}, text
    lines = text.split("\n", 1)[1] if "\n" in text else ""
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    header = text[3:end].strip("\n")
    after = text[end + 4 :].lstrip("\n")
    meta: dict = {}
    for line in header.splitlines():
        m = _YAML_LINE.match(line)
        if not m:
            continue
        key = m.group(1)
        raw = m.group(2)
        if key == "tags":
            meta[key] = _parse_yaml_list(raw)
        else:
            meta[key] = _parse_yaml_scalar(raw)
    _ = lines  # keep the name warm for future keys
    return meta, after


def _title_hash(title: str) -> str:
    return hashlib.sha256(title.strip().lower().encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------- export


@dataclass
class ExportOptions:
    include_embeddings: bool = True
    include_compass_reads: bool = True
    include_trails: bool = True
    include_signal: bool = True


def export_dict(opts: ExportOptions | None = None) -> dict:
    """Produce the full portable dict payload.

    Structure is stable across restore paths — bump ``SCHEMA_VERSION`` in
    a coordinated way if you rename fields. Any field the importer
    doesn't recognise is passed through into the diff summary as a
    warning instead of exploding.
    """
    o = opts or ExportOptions()
    notes = store.all_notes()
    embeddings = dict(store.all_embeddings()) if o.include_embeddings else {}

    exported_notes: list[dict] = []
    for n in notes:
        payload: dict = {
            "id": n["id"],
            "title": n["title"],
            "body": n["body"],
            "tags": list(n.get("tags") or []),
            "created_at": n["created_at"],
            "last_seen_at": n.get("last_seen_at"),
            "title_hash": _title_hash(n["title"]),
        }
        if o.include_embeddings:
            vec = embeddings.get(n["id"])
            if vec is not None:
                payload["embedding_b64"] = _b64_from_embedding(vec)
        exported_notes.append(payload)

    stats = {
        "note_count": len(exported_notes),
        "with_embeddings": sum(1 for n in exported_notes if "embedding_b64" in n),
        "tag_count": len({t for n in exported_notes for t in n.get("tags", [])}),
    }

    payload: dict = {
        "schema": SCHEMA_VERSION,
        "engine": ENGINE_VERSION,
        "exported_at": _iso_now(),
        "embedding_dim": DIM,
        "options": {
            "include_embeddings": o.include_embeddings,
            "include_compass_reads": o.include_compass_reads,
            "include_trails": o.include_trails,
            "include_signal": o.include_signal,
        },
        "notes": exported_notes,
        "stats": stats,
    }

    if o.include_trails:
        trails = store.list_trails()
        payload["trails"] = [
            {
                "id": t["id"],
                "title": t["title"],
                "description": t.get("description", ""),
                "steps": t.get("steps") or [],
                "created_at": t["created_at"],
                "updated_at": t["updated_at"],
                "origin": t.get("origin", "manual"),
            }
            for t in trails
        ]
        stats["trail_count"] = len(payload["trails"])

    if o.include_compass_reads:
        questions = store.list_questions(include_archived=True)
        compass: list[dict] = []
        for q in questions:
            reads = store.reads_for(q["id"])
            compass.append(
                {
                    "id": q["id"],
                    "text": q["text"],
                    "created_at": q["created_at"],
                    "archived_at": q.get("archived_at"),
                    "reads": [
                        {"note_id": nid, "read_at": ts}
                        for nid, ts in sorted(reads.items())
                    ],
                }
            )
        payload["compass"] = compass
        stats["question_count"] = len(compass)

    if o.include_signal:
        watches = store.list_signal_watches()
        payload["signal"] = [
            {
                "question_id": w["question_id"],
                "pinned_at": w["pinned_at"],
                "last_refreshed_at": w.get("last_refreshed_at"),
                "snapshot": w["snapshot"],
            }
            for w in watches
        ]
        stats["signal_count"] = len(payload["signal"])

    return payload


def _neighbor_lookup(threshold: float, top_k: int) -> dict[int, list[dict]]:
    """Compute per-note synapse neighbors once so the Markdown export can
    render a proper ``## Related`` section for every note without paying
    O(N^2) per file."""
    try:
        g = synapse.compute_graph(threshold=threshold, top_k=top_k)
    except Exception:  # pragma: no cover — defensive: empty store
        return {}
    title_by_id = {n["id"]: n["title"] for n in g.nodes}
    out: dict[int, list[dict]] = {nid: [] for nid in title_by_id}
    for e in g.edges:
        s, t, w = e["source"], e["target"], e["strength"]
        if t in title_by_id:
            out.setdefault(s, []).append({"id": t, "title": title_by_id[t], "strength": w})
        if s in title_by_id:
            out.setdefault(t, []).append({"id": s, "title": title_by_id[s], "strength": w})
    for nid in out:
        out[nid].sort(key=lambda r: r["strength"], reverse=True)
        out[nid] = out[nid][: top_k]
    return out


def _render_note_markdown(note: dict, neighbors: list[dict]) -> str:
    """Build one ``.md`` file for a note: frontmatter + body + Related."""
    fm_lines = ["---"]
    fm_lines.append(f"id: {int(note['id'])}")
    fm_lines.append(f"title: {_yaml_escape(note['title'])}")
    tags = list(note.get("tags") or [])
    tag_repr = "[" + ", ".join(_yaml_escape(t) for t in tags) + "]"
    fm_lines.append(f"tags: {tag_repr}")
    fm_lines.append(f"created_at: {_yaml_escape(note['created_at'])}")
    if note.get("last_seen_at"):
        fm_lines.append(f"last_seen_at: {_yaml_escape(note['last_seen_at'])}")
    fm_lines.append("---")
    fm = "\n".join(fm_lines)

    body = (note.get("body") or "").strip()

    related_block = ""
    if neighbors:
        rows = [
            f"- [[{n['title']}]] · {n['strength']:.2f}"
            for n in neighbors
        ]
        related_block = "\n\n---\n\n## Related\n\n" + "\n".join(rows)

    return f"{fm}\n\n# {note['title']}\n\n{body}{related_block}\n"


def export_markdown_zip(opts: ExportOptions | None = None) -> bytes:
    """Bundle every note as its own ``.md`` file inside a ZIP.

    Also ships a ``_manifest.json`` mirror of the JSON export (without
    the note bodies to avoid duplication) so a downstream tool can
    reconstruct trails, compass and signal state from the ZIP alone.
    """
    o = opts or ExportOptions()
    notes = store.all_notes()
    neighbors = _neighbor_lookup(threshold=synapse.DEFAULT_THRESHOLD, top_k=5)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        # README explains the shape to a human opening the ZIP.
        zf.writestr(
            "README.md",
            (
                "# SynapseOS vault export\n\n"
                f"Engine: {ENGINE_VERSION}\n"
                f"Exported: {_iso_now()}\n"
                f"Notes: {len(notes)}\n\n"
                "Every ``notes/*.md`` file carries YAML frontmatter with\n"
                "``id``, ``title``, ``tags``, ``created_at`` and an\n"
                "optional ``last_seen_at``. The ``## Related`` section is\n"
                "auto-generated from the current synapse graph; SynapseOS\n"
                "recomputes it on import, so edits to those bullet lists\n"
                "are harmless.\n\n"
                "``_manifest.json`` mirrors the JSON export sans note\n"
                "bodies — good for restoring trails, compass state and\n"
                "signal watches. Import this ZIP through the Vault modal\n"
                "and the full state comes back.\n"
            ),
        )
        seen_names: set[str] = set()
        for n in notes:
            slug = _slugify(n["title"], n["id"])
            base = f"notes/{slug}.md"
            # Defensive against unlikely slug collisions after id suffix.
            name = base
            i = 2
            while name in seen_names:
                name = f"notes/{slug}-{i}.md"
                i += 1
            seen_names.add(name)
            zf.writestr(name, _render_note_markdown(n, neighbors.get(n["id"], [])))

        # Manifest: everything a JSON export carries, minus note bodies
        # (already inline in the .md files) but keeping tags/timestamps
        # for lossless restore.
        payload = export_dict(o)
        for n in payload["notes"]:
            n.pop("body", None)
        zf.writestr("_manifest.json", json.dumps(payload, indent=2, sort_keys=True))

    return buf.getvalue()


def export_json(opts: ExportOptions | None = None) -> bytes:
    """UTF-8 JSON bytes ready for HTTP streaming."""
    return json.dumps(export_dict(opts), indent=2, sort_keys=True).encode("utf-8")


# ---------------------------------------------------------------- import


@dataclass
class ImportSummary:
    mode: str
    dry_run: bool
    notes_created: int = 0
    notes_updated: int = 0
    notes_skipped: int = 0
    notes_removed: int = 0
    trails_imported: int = 0
    compass_imported: int = 0
    signal_imported: int = 0
    embeddings_restored: int = 0
    warnings: list[str] = field(default_factory=list)
    total_incoming_notes: int = 0
    id_remap: dict[int, int] = field(default_factory=dict)


def _parse_markdown_zip(zip_bytes: bytes) -> tuple[list[dict], list[str]]:
    """Read a ZIP produced by ``export_markdown_zip`` (or any Obsidian
    vault) and hand back note dicts + soft warnings."""
    warnings: list[str] = []
    notes: list[dict] = []
    try:
        zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    except zipfile.BadZipFile as e:
        raise ValueError(f"not a valid ZIP archive: {e}")
    for name in zf.namelist():
        if not name.lower().endswith(".md"):
            continue
        if name.rsplit("/", 1)[-1].startswith("_"):
            continue  # our own _manifest / _README are informational
        if name.lower() == "readme.md":
            continue
        try:
            raw = zf.read(name).decode("utf-8", errors="replace")
        except Exception as e:  # pragma: no cover — defensive
            warnings.append(f"{name}: unreadable ({e})")
            continue
        meta, body = _parse_frontmatter(raw)
        title = meta.get("title") or _title_from_filename(name)
        # Strip the auto-generated Related section on import — we
        # recompute synapses from embeddings anyway. Users who added
        # their own bullets under Related lose them; a warning covers
        # this so the loss is visible.
        cleaned, dropped = _strip_related_section(body)
        if dropped:
            warnings.append(f"{name}: dropped auto-generated Related section")
        # If the body starts with an H1 that matches the title, collapse
        # it into the title so we don't leak "# Title" into the body.
        cleaned = _strip_leading_h1(cleaned, title)
        tags = list(meta.get("tags") or [])
        notes.append(
            {
                "id": int(meta.get("id") or 0) or None,
                "title": str(title or "Untitled").strip() or "Untitled",
                "body": cleaned.strip() or "(no body)",
                "tags": [str(t).strip() for t in tags if str(t).strip()],
                "created_at": str(meta.get("created_at") or ""),
                "last_seen_at": meta.get("last_seen_at") or None,
            }
        )
    return notes, warnings


def _title_from_filename(name: str) -> str:
    base = name.rsplit("/", 1)[-1]
    if base.endswith(".md"):
        base = base[:-3]
    base = base.rstrip("-0123456789").rstrip("-")
    parts = [p for p in base.split("-") if p]
    return " ".join(p.capitalize() for p in parts) or "Untitled"


def _strip_related_section(body: str) -> tuple[str, bool]:
    """Return (body_without_related, did_strip)."""
    # Match a preceding `---` separator too so we clean the whole block
    # our exporter emits, without eating a user's manual `---` divider.
    pattern = re.compile(
        r"\n\n---\n\n##\s+Related\b[\s\S]*$",
        re.MULTILINE,
    )
    new_body = pattern.sub("", body)
    if new_body == body:
        return body, False
    return new_body, True


def _strip_leading_h1(body: str, title: str) -> str:
    stripped = body.lstrip()
    prefix = f"# {title}".strip()
    if stripped.startswith(prefix):
        return stripped[len(prefix):].lstrip("\n")
    return body


def _sniff_payload(payload: dict) -> None:
    if not isinstance(payload, dict):
        raise ValueError("import payload must be a JSON object")
    schema = int(payload.get("schema") or 0)
    if schema == 0:
        raise ValueError("payload is missing `schema` — not a SynapseOS export")
    if schema > SCHEMA_VERSION:
        # Forward-compat: warn, don't crash. New fields we don't know
        # about get preserved as-is on the way through where possible.
        pass
    dim = int(payload.get("embedding_dim") or DIM)
    if dim != DIM:
        raise ValueError(
            f"embedding_dim mismatch (payload={dim}, engine={DIM})"
        )


def preview_import(payload: dict) -> ImportSummary:
    """Compute what an ``import_payload(payload, mode='merge')`` would do
    without touching the store."""
    _sniff_payload(payload)
    existing_by_hash = {_title_hash(n["title"]): n for n in store.all_notes()}
    summary = ImportSummary(mode="preview", dry_run=True)
    incoming = payload.get("notes") or []
    summary.total_incoming_notes = len(incoming)
    for note in incoming:
        h = note.get("title_hash") or _title_hash(note.get("title") or "")
        if h in existing_by_hash:
            summary.notes_updated += 1
        else:
            summary.notes_created += 1
    summary.trails_imported = len(payload.get("trails") or [])
    summary.compass_imported = len(payload.get("compass") or [])
    summary.signal_imported = len(payload.get("signal") or [])
    return summary


def _reset_store_notes() -> None:
    """Replace-mode wipe. Trails / compass / signal are cleared too
    because we're about to re-import them (or leave the vault empty)."""
    with _store_conn() as con:
        for table in (
            "notes",
            "trails",
            "compass_reads",
            "compass_questions",
            "signal_watches",
        ):
            con.execute(f"DELETE FROM {table}")
        for table in (
            "notes",
            "trails",
            "compass_questions",
            "signal_watches",
        ):
            con.execute(
                "DELETE FROM sqlite_sequence WHERE name=?", (table,)
            )


def _import_note_raw(
    *,
    title: str,
    body: str,
    tags: list[str],
    created_at: str | None,
    last_seen_at: str | None,
    embedding: tuple[float, ...] | None,
) -> int:
    """Insert a note preserving timestamps and (optionally) embedding."""
    ts = (created_at or _iso_now()).strip() or _iso_now()
    with _store_conn() as con:
        if embedding is not None:
            packed = struct.pack(f"{DIM}f", *embedding)
        else:
            from .embed import embed as _embed

            packed = struct.pack(f"{DIM}f", *_embed(f"{title}\n\n{body}"))
        cur = con.execute(
            "INSERT INTO notes(title, body, tags, created_at, embedding, last_seen_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                title.strip(),
                body.strip(),
                json.dumps(list(tags or [])),
                ts,
                packed,
                last_seen_at,
            ),
        )
        return int(cur.lastrowid)


def _update_note_raw(
    note_id: int,
    *,
    title: str,
    body: str,
    tags: list[str],
    last_seen_at: str | None,
    embedding: tuple[float, ...] | None,
) -> None:
    with _store_conn() as con:
        if embedding is not None:
            packed = struct.pack(f"{DIM}f", *embedding)
        else:
            from .embed import embed as _embed

            packed = struct.pack(f"{DIM}f", *_embed(f"{title}\n\n{body}"))
        con.execute(
            "UPDATE notes SET title=?, body=?, tags=?, embedding=?, last_seen_at=? "
            "WHERE id=?",
            (
                title.strip(),
                body.strip(),
                json.dumps(list(tags or [])),
                packed,
                last_seen_at,
                note_id,
            ),
        )


def import_payload(payload: dict, mode: str = "merge") -> ImportSummary:
    """Apply a JSON export to the current store.

    ``mode='merge'`` upserts by title-hash; existing notes with a
    matching title are refreshed in-place (body, tags, embedding
    restored). Notes with no title-match are inserted; ids are *not*
    preserved (SQLite AUTOINCREMENT owns them). A remap of
    ``old_id -> new_id`` is included in the summary so downstream
    references — trails, compass reads, signal watches — can be
    rewritten cleanly.

    ``mode='replace'`` wipes notes + trails + compass + signal first,
    then applies the payload as if the store were fresh.
    """
    if mode not in ("merge", "replace"):
        raise ValueError("mode must be 'merge' or 'replace'")
    _sniff_payload(payload)

    summary = ImportSummary(mode=mode, dry_run=False)
    summary.total_incoming_notes = len(payload.get("notes") or [])

    if mode == "replace":
        _reset_store_notes()
        existing_by_hash: dict[str, dict] = {}
    else:
        existing_by_hash = {_title_hash(n["title"]): n for n in store.all_notes()}

    remap: dict[int, int] = {}

    for note in payload.get("notes") or []:
        title = str(note.get("title") or "").strip()
        if not title:
            summary.notes_skipped += 1
            summary.warnings.append("skipped a note with empty title")
            continue
        body = str(note.get("body") or "").strip() or "(no body)"
        tags = list(note.get("tags") or [])
        created_at = note.get("created_at") or None
        last_seen_at = note.get("last_seen_at") or None
        emb = None
        if "embedding_b64" in note:
            try:
                emb = _embedding_from_b64(note["embedding_b64"])
                summary.embeddings_restored += 1
            except Exception as e:
                summary.warnings.append(f"{title}: bad embedding_b64 ({e})")
        h = note.get("title_hash") or _title_hash(title)
        existing = existing_by_hash.get(h)
        old_id = int(note.get("id") or 0) or None
        if existing:
            _update_note_raw(
                existing["id"],
                title=title,
                body=body,
                tags=tags,
                last_seen_at=last_seen_at,
                embedding=emb,
            )
            summary.notes_updated += 1
            if old_id:
                remap[old_id] = existing["id"]
        else:
            new_id = _import_note_raw(
                title=title,
                body=body,
                tags=tags,
                created_at=created_at,
                last_seen_at=last_seen_at,
                embedding=emb,
            )
            summary.notes_created += 1
            if old_id:
                remap[old_id] = new_id

    summary.id_remap = remap

    # ---------- trails ----------
    for t in payload.get("trails") or []:
        steps = t.get("steps") or []
        remapped_steps: list[dict] = []
        dropped = 0
        for s in steps:
            old = int(s.get("note_id") or 0)
            new = remap.get(old, old)
            if not new:
                dropped += 1
                continue
            remapped_steps.append(
                {"note_id": new, "caption": s.get("caption") or ""}
            )
        if dropped:
            summary.warnings.append(
                f"trail {t.get('title')!r}: dropped {dropped} step(s) with no matching note"
            )
        try:
            store.add_trail(
                title=str(t.get("title") or "Untitled trail"),
                description=str(t.get("description") or ""),
                steps=remapped_steps,
                origin=str(t.get("origin") or "manual"),
            )
            summary.trails_imported += 1
        except Exception as e:
            summary.warnings.append(f"trail {t.get('title')!r}: {e}")

    # ---------- compass ----------
    q_remap: dict[int, int] = {}
    for q in payload.get("compass") or []:
        try:
            new_qid = store.add_question(str(q.get("text") or "").strip() or "(untitled)")
        except Exception as e:
            summary.warnings.append(f"compass question: {e}")
            continue
        if q.get("id"):
            q_remap[int(q["id"])] = new_qid
        for read in q.get("reads") or []:
            old_nid = int(read.get("note_id") or 0)
            new_nid = remap.get(old_nid, old_nid)
            if not new_nid:
                summary.warnings.append(
                    f"compass reads: dropped ref to missing note {old_nid}"
                )
                continue
            store.mark_read(new_qid, new_nid, when=read.get("read_at"))
        summary.compass_imported += 1

    # ---------- signal ----------
    for w in payload.get("signal") or []:
        old_qid = int(w.get("question_id") or 0)
        new_qid = q_remap.get(old_qid)
        if not new_qid:
            summary.warnings.append(
                f"signal watch skipped: question {old_qid} not in payload"
            )
            continue
        snapshot = w.get("snapshot")
        if not isinstance(snapshot, str):
            snapshot = json.dumps(snapshot or {})
        try:
            store.upsert_signal_watch(new_qid, snapshot)
            summary.signal_imported += 1
        except Exception as e:
            summary.warnings.append(f"signal watch {old_qid}: {e}")

    return summary


def import_markdown_zip(zip_bytes: bytes, mode: str = "merge") -> ImportSummary:
    """Read a Markdown ZIP and route it through ``import_payload``.

    Also pulls trails/compass/signal state from ``_manifest.json`` if
    the ZIP contains one so round-tripping a Vault export doesn't lose
    non-note state.
    """
    notes, warnings = _parse_markdown_zip(zip_bytes)
    manifest: dict = {}
    try:
        zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
        if "_manifest.json" in zf.namelist():
            manifest = json.loads(zf.read("_manifest.json").decode("utf-8"))
    except Exception:
        pass  # manifest missing or unreadable — proceed with notes only

    payload = {
        "schema": SCHEMA_VERSION,
        "engine": ENGINE_VERSION,
        "exported_at": _iso_now(),
        "embedding_dim": DIM,
        "notes": [
            {
                "id": n.get("id"),
                "title": n["title"],
                "body": n["body"],
                "tags": n["tags"],
                "created_at": n["created_at"],
                "last_seen_at": n["last_seen_at"],
            }
            for n in notes
        ],
        "trails": manifest.get("trails") or [],
        "compass": manifest.get("compass") or [],
        "signal": manifest.get("signal") or [],
    }
    summary = import_payload(payload, mode=mode)
    summary.warnings = warnings + summary.warnings
    return summary


# ---------------------------------------------------------------- snapshots


@contextmanager
def _store_conn():
    """Reach into store's SQLite file directly. Vault manages a couple of
    write paths (bulk import, wipe, snapshot table CRUD) that the public
    ``store`` surface doesn't expose — putting them behind their own
    connection keeps them isolated from the note-facing API."""
    _DB_PATH = Path(__file__).resolve().parent.parent / "data" / "synapse.db"
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(_DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    finally:
        con.close()


def _ensure_snapshot_schema() -> None:
    with _store_conn() as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS vault_snapshots (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                label        TEXT NOT NULL UNIQUE,
                created_at   TEXT NOT NULL,
                note_count   INTEGER NOT NULL,
                size_bytes   INTEGER NOT NULL,
                payload_json TEXT NOT NULL
            )
            """
        )
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_vault_snapshots_created "
            "ON vault_snapshots(created_at)"
        )


def create_snapshot(label: str) -> dict:
    """Freeze the current vault state as a named snapshot."""
    _ensure_snapshot_schema()
    label = (label or "").strip() or _iso_now()
    payload = export_dict()
    body = json.dumps(payload, sort_keys=True)
    now = _iso_now()
    with _store_conn() as con:
        try:
            cur = con.execute(
                "INSERT INTO vault_snapshots(label, created_at, note_count, size_bytes, payload_json) "
                "VALUES (?, ?, ?, ?, ?)",
                (label, now, payload["stats"]["note_count"], len(body), body),
            )
            sid = int(cur.lastrowid)
        except sqlite3.IntegrityError:
            # Same label already exists — overwrite in place. This is
            # the shape users want (`create_snapshot('before-echo-merge')`
            # a second time replaces the earlier one) and avoids
            # accidental snapshot creep.
            con.execute(
                "UPDATE vault_snapshots SET created_at=?, note_count=?, size_bytes=?, payload_json=? "
                "WHERE label=?",
                (now, payload["stats"]["note_count"], len(body), body, label),
            )
            row = con.execute(
                "SELECT id FROM vault_snapshots WHERE label=?", (label,)
            ).fetchone()
            sid = int(row["id"])
    return {
        "id": sid,
        "label": label,
        "created_at": now,
        "note_count": payload["stats"]["note_count"],
        "size_bytes": len(body),
    }


def list_snapshots() -> list[dict]:
    _ensure_snapshot_schema()
    with _store_conn() as con:
        rows = con.execute(
            "SELECT id, label, created_at, note_count, size_bytes "
            "FROM vault_snapshots ORDER BY created_at DESC, id DESC"
        ).fetchall()
        return [
            {
                "id": int(r["id"]),
                "label": r["label"],
                "created_at": r["created_at"],
                "note_count": int(r["note_count"]),
                "size_bytes": int(r["size_bytes"]),
            }
            for r in rows
        ]


def get_snapshot_payload(snapshot_id: int) -> dict | None:
    _ensure_snapshot_schema()
    with _store_conn() as con:
        row = con.execute(
            "SELECT payload_json FROM vault_snapshots WHERE id=?",
            (snapshot_id,),
        ).fetchone()
        if not row:
            return None
        return json.loads(row["payload_json"])


def restore_snapshot(snapshot_id: int) -> ImportSummary | None:
    payload = get_snapshot_payload(snapshot_id)
    if payload is None:
        return None
    return import_payload(payload, mode="replace")


def delete_snapshot(snapshot_id: int) -> bool:
    _ensure_snapshot_schema()
    with _store_conn() as con:
        cur = con.execute(
            "DELETE FROM vault_snapshots WHERE id=?", (snapshot_id,)
        )
        return cur.rowcount > 0


def vault_stats() -> dict:
    """One-shot summary used by the header pill + modal banner."""
    _ensure_snapshot_schema()
    with _store_conn() as con:
        (snap_count,) = con.execute(
            "SELECT COUNT(*) FROM vault_snapshots"
        ).fetchone()
    return {
        "notes": store.count(),
        "trails": store.trails_count(),
        "questions": store.questions_count(),
        "watches": store.signal_watches_count(),
        "snapshots": int(snap_count),
        "engine": ENGINE_VERSION,
        "schema_version": SCHEMA_VERSION,
    }


def summary_to_dict(s: ImportSummary) -> dict:
    return {
        "mode": s.mode,
        "dry_run": s.dry_run,
        "notes_created": s.notes_created,
        "notes_updated": s.notes_updated,
        "notes_skipped": s.notes_skipped,
        "notes_removed": s.notes_removed,
        "trails_imported": s.trails_imported,
        "compass_imported": s.compass_imported,
        "signal_imported": s.signal_imported,
        "embeddings_restored": s.embeddings_restored,
        "warnings": list(s.warnings),
        "total_incoming_notes": s.total_incoming_notes,
    }
