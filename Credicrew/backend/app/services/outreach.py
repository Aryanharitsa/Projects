"""Deterministic outreach email composer.

Mirror of the frontend at `frontend/src/lib/outreach.ts`. Same templating
rules so the API and the in-browser modal produce identical drafts.

No LLM call; pure-string templating from the role's parsed plan, the JD
pitch line, and the candidate's match result.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass
class OutreachEmail:
    subject: str
    body: str


def first_name(full: str | None) -> str:
    if not full:
        return "there"
    return full.strip().split()[0] or "there"


def join_list(items: Iterable[str]) -> str:
    parts = [s for s in items if s]
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return f"{parts[0]} and {parts[1]}"
    return f"{', '.join(parts[:-1])}, and {parts[-1]}"


def title_case(s: str | None) -> str:
    return " ".join(w[:1].upper() + w[1:] for w in (s or "").split())


def extract_pitch(jd: str | None) -> str:
    """Pull the first sentence of the JD as a short pitch line."""
    if not jd:
        return ""
    trimmed = jd.strip()
    # First sentence terminator
    for term in (". ", ".\n", "! ", "!\n", "? ", "?\n"):
        idx = trimmed.find(term)
        if 0 < idx < 220:
            return trimmed[: idx + 1].strip()
    head = trimmed.split("\n", 1)[0]
    if len(head) > 220:
        return head[:217].rstrip() + "…"
    return head


def compose_email(
    *,
    role_name: str | None,
    plan_skills: list[str] | None,
    plan_location: str | None,
    plan_seniority: str | None,
    pitch: str | None,
    candidate_name: str | None,
    candidate_role: str | None,
    matched_skills: list[str] | None = None,
    score: int | None = None,
    sender: str | None = None,
) -> OutreachEmail:
    fn = first_name(candidate_name)
    role_title = role_name or (
        title_case(plan_seniority or "engineering") + " role"
    )
    matched = (matched_skills or [])[:3]
    pitch_line = (
        (pitch or "").strip()
        or f"we're hiring for {role_title.lower()} and your background looks like a strong fit"
    )

    if matched:
        subject = (
            f"Quick chat about a {role_title} role — your {matched[0]} work caught my eye"
        )
    else:
        subject = f"Quick chat about a {role_title} role at our team"

    if matched:
        skill_line = (
            f"Your work with {join_list(matched)} stood out — those are exactly "
            "the skills we need on day one."
        )
    else:
        skill_line = (
            f"Your background as a {candidate_role or 'engineer'} stood out across "
            "the candidates I reviewed."
        )

    if plan_location and plan_location != "remote":
        loc_line = (
            f"We're based in {title_case(plan_location)}, but happy to discuss "
            "remote / hybrid arrangements."
        )
    else:
        loc_line = "The role is remote-friendly across India."

    score_line = (
        f"(For context: against the spec for {role_title}, your profile lands at "
        f"{score}/100 with explainable reasons — happy to share the breakdown.)"
        if isinstance(score, int)
        else ""
    )

    lines = [
        f"Hi {fn},",
        "",
        f"I'm reaching out about a {role_title} opportunity — {pitch_line}",
        "",
        skill_line,
        loc_line,
        "",
        "Would you be open to a 20-minute intro call this week? Even if the timing "
        "isn't right, I'd love to keep in touch.",
        score_line,
        "",
        "Best,",
        sender or "— Hiring team",
    ]
    body = "\n".join(line for line in lines if line is not None)
    return OutreachEmail(subject=subject, body=body)
