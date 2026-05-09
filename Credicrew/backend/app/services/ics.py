"""Minimal RFC 5545 iCalendar generator — Python mirror of frontend/src/lib/ics.ts.

Generates a single VCALENDAR with N VEVENTs. Honors the bits that matter
in practice (CRLF terminators, UTC Z-suffixed DTSTART/DTEND, line-folding
at 75 octets per RFC §3.1, escaping of `\\`, `\\n`, `,`, `;` in TEXT
properties, stable per-slot UIDs).

No external deps.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable

PRODID = "-//Credicrew//Decision Studio 0.5//EN"


@dataclass
class Slot:
    start_utc_ms: int
    duration_min: int = 60
    summary: str = "Interview"
    description: str | None = None
    location: str | None = None
    organizer_email: str | None = None
    organizer_name: str | None = None
    attendees: list[dict] = field(default_factory=list)
    uid: str | None = None


def _format_utc(epoch_ms: int) -> str:
    d = datetime.fromtimestamp(epoch_ms / 1000.0, tz=timezone.utc)
    return d.strftime("%Y%m%dT%H%M%SZ")


def _escape(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
             .replace("\n", "\\n")
             .replace(",", "\\,")
             .replace(";", "\\;")
    )


def _fold(line: str) -> str:
    if len(line) <= 75:
        return line
    out: list[str] = []
    i = 0
    while i < len(line):
        if i == 0:
            out.append(line[i:i + 75])
            i += 75
        else:
            out.append(" " + line[i:i + 74])
            i += 74
    return "\r\n".join(out)


def _default_uid(slot: Slot) -> str:
    h = 0
    for ch in slot.summary:
        h = ((h << 5) - h + ord(ch)) & 0xFFFFFFFF
    return f"credicrew-{slot.start_utc_ms}-{format(h, 'x')}@credicrew.local"


def _build_event(slot: Slot, dtstamp: str) -> list[str]:
    dtstart = _format_utc(slot.start_utc_ms)
    dtend = _format_utc(slot.start_utc_ms + slot.duration_min * 60_000)
    uid = slot.uid or _default_uid(slot)
    lines: list[str] = ["BEGIN:VEVENT"]
    lines.append(f"UID:{_escape(uid)}")
    lines.append(f"DTSTAMP:{dtstamp}")
    lines.append(f"DTSTART:{dtstart}")
    lines.append(f"DTEND:{dtend}")
    lines.append(f"SUMMARY:{_escape(slot.summary)}")
    if slot.description:
        lines.append(f"DESCRIPTION:{_escape(slot.description)}")
    if slot.location:
        lines.append(f"LOCATION:{_escape(slot.location)}")
    if slot.organizer_email:
        cn = f";CN={_escape(slot.organizer_name)}" if slot.organizer_name else ""
        lines.append(f"ORGANIZER{cn}:mailto:{slot.organizer_email}")
    for a in slot.attendees:
        email = a.get("email")
        if not email:
            continue
        cn = f";CN={_escape(a['name'])}" if a.get("name") else ""
        lines.append(f"ATTENDEE{cn};ROLE=REQ-PARTICIPANT;RSVP=TRUE:mailto:{email}")
    lines.append("STATUS:CONFIRMED")
    lines.append("END:VEVENT")
    return lines


def build_calendar(slots: Iterable[Slot]) -> str:
    dtstamp = _format_utc(int(datetime.now(timezone.utc).timestamp() * 1000))
    lines: list[str] = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{PRODID}",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
    ]
    for s in slots:
        lines.extend(_build_event(s, dtstamp))
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(l) for l in lines) + "\r\n"
