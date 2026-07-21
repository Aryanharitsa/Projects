"""TITAN Codex — evidence-cited SAR narrative composer (round-19, day-90).

Every prior TITAN surface produces a *number* or a *ranking*.  Codex is
the surface that turns those into the paragraph a compliance officer
actually has to file with FinCEN / FIU-IND / AUSTRAC — with every claim
addressable back to the specific piece of evidence that supports it.

The existing ``sar.py`` module renders a one-shot markdown template.
That is enough for a first draft but does not:

    1. Assemble the FinCEN 5W + How + Action narrative structure
       (Who / What / When / Where / Why / How / Action) — the shape
       every regulator's guidance actually asks for.
    2. Cite every sentence back to *typed* evidence (transaction,
       factor, typology, sanctions hit, jurisdiction, counterparty) so
       an auditor can trace the paragraph to the underlying data.
    3. Score the draft against a filing-quality checklist that catches
       the six or seven mistakes that get SARs bounced back to the
       analyst — missing period, unnamed subject, no counterparty
       reference, no recommended action, and so on.
    4. Apply a deterministic redaction pass that masks account /
       counterparty identifiers without dropping the evidence links.
    5. Ship the whole thing as a machine-readable structured payload
       *and* a paste-into-your-case-note markdown export.

Design rules — kept identical to every other TITAN engine:

    * Deterministic.  Same account report + same options → same output.
      No LLM calls, no probabilistic drift.
    * Explainable.  Every quality check exposes its ``weight``, its
      ``passed`` bool, and a plain-English ``detail`` + ``hint``.
    * Auditor-facing.  ``get_rules()`` returns every constant the
      engine touches — checklist definitions, section prompts, grade
      cutoffs, evidence-kind vocabulary.
    * Frontend-friendly.  Sections are pre-decomposed into blocks
      (paragraphs, bullet lists, tables) that a UI can render as
      cards without re-parsing markdown.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Constants — every knob the engine touches lives here (never in code paths).
# ---------------------------------------------------------------------------

ENGINE_VERSION = "titan-codex/1.0.0"

# Typology confidence floor below which the primary typology is *not*
# considered "cited" (matches the sar.py 35% gate).
TYPOLOGY_CONFIDENCE_FLOOR = 0.35

# Only factors whose points exceed this are cited as "triggered".
FACTOR_POINT_FLOOR = 0.01

# Cap on how many representative transactions we cite inline per section.
MAX_TRANSACTIONS_CITED = 5
MAX_COUNTERPARTIES_CITED = 5
MAX_TYPOLOGY_EVIDENCE = 5

# Grade ladder — [(min_score, grade)].  First match wins.
GRADE_LADDER: List[Tuple[float, str]] = [
    (90.0, "publish_ready"),
    (75.0, "acceptable"),
    (55.0, "needs_work"),
    (0.0, "unfilable"),
]

# Verdict mood → chip colour / action code, for the frontend badge.
GRADE_META: Dict[str, Dict[str, str]] = {
    "publish_ready": {
        "label": "Publish-ready",
        "accent": "#22d3a8",
        "action": "file",
        "detail": "Meets every material FinCEN 5W checklist; safe to submit as-is.",
    },
    "acceptable": {
        "label": "Acceptable",
        "accent": "#a5b4fc",
        "action": "review",
        "detail": "Passes the material checks; second-analyst review recommended before filing.",
    },
    "needs_work": {
        "label": "Needs work",
        "accent": "#fbbf24",
        "action": "revise",
        "detail": "One or more required sections is under-supported; add evidence before filing.",
    },
    "unfilable": {
        "label": "Unfilable",
        "accent": "#f43f5e",
        "action": "block",
        "detail": "Missing critical narrative elements; do not submit.",
    },
}

# ---------------------------------------------------------------------------
# Data model.
# ---------------------------------------------------------------------------


@dataclass
class Citation:
    """One evidence link inside a narrative sentence.

    ``kind`` is one of a small, closed vocabulary so the frontend can
    render kind-specific chips (a transaction chip → tooltip with amount
    and timestamp; a factor chip → tooltip with points and detail).
    """

    kind: str  # transaction | factor | typology | sanctions | media | counterparty | period | band | totals | geo | channel | subject
    ref: str
    label: str
    detail: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {"kind": self.kind, "ref": self.ref, "label": self.label, "detail": self.detail}


@dataclass
class NarrativeBlock:
    """One paragraph / list / table inside a narrative section.

    A block is the smallest addressable unit in the narrative — every
    citation in the section is anchored to exactly one block.
    """

    text: str
    citations: List[Citation] = field(default_factory=list)
    kind: str = "para"  # para | bullet_list | table
    items: List[str] = field(default_factory=list)
    columns: List[str] = field(default_factory=list)
    rows: List[List[str]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "citations": [c.to_dict() for c in self.citations],
            "kind": self.kind,
            "items": list(self.items),
            "columns": list(self.columns),
            "rows": [list(r) for r in self.rows],
        }


@dataclass
class NarrativeSection:
    id: str  # who | what | when | where | why | how | action
    number: int
    title: str
    prompt: str
    blocks: List[NarrativeBlock] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "number": self.number,
            "title": self.title,
            "prompt": self.prompt,
            "blocks": [b.to_dict() for b in self.blocks],
            "citation_count": sum(len(b.citations) for b in self.blocks),
            "word_count": sum(len(_words(b.text)) + sum(len(_words(i)) for i in b.items) for b in self.blocks),
        }


@dataclass
class QualityCheck:
    id: str
    section: str  # section id it belongs to, or "global"
    label: str
    passed: bool
    weight: float
    detail: str
    hint: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "section": self.section,
            "label": self.label,
            "passed": self.passed,
            "weight": self.weight,
            "detail": self.detail,
            "hint": self.hint,
        }


@dataclass
class Quality:
    score: float
    grade: str
    passed: int
    failed: int
    checks: List[QualityCheck]
    missing_evidence_kinds: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        meta = GRADE_META[self.grade]
        return {
            "score": round(self.score, 1),
            "grade": self.grade,
            "grade_label": meta["label"],
            "grade_accent": meta["accent"],
            "grade_action": meta["action"],
            "grade_detail": meta["detail"],
            "passed": self.passed,
            "failed": self.failed,
            "checks": [c.to_dict() for c in self.checks],
            "missing_evidence_kinds": list(self.missing_evidence_kinds),
        }


# ---------------------------------------------------------------------------
# Section prompts — the FinCEN 5W skeleton every regulator's guidance
# reduces to.  Kept as data (not string-format code) so the frontend can
# display the prompt beside the section as an inline coach.
# ---------------------------------------------------------------------------

SECTION_SPECS: List[Tuple[str, int, str, str]] = [
    ("who", 1, "1. Subject",
     "Who is the subject of the report — account identifier, display name if any, "
     "and immediate counterparty circle?"),
    ("what", 2, "2. Suspicious activity",
     "What is the pattern being reported — laundering typology name, contributing "
     "detectors, and the specific behaviours that fired?"),
    ("when", 3, "3. Activity period",
     "When did the activity occur — start / end timestamps, burst pattern, and "
     "the number of transactions in scope?"),
    ("where", 4, "4. Jurisdictions & channels",
     "Where — the geographic footprint of the flows (jurisdictions, high-risk "
     "geos) and the channels used (wire, cash, card, crypto)."),
    ("why", 5, "5. Why suspicious",
     "Why the activity crosses the alerting threshold — composite risk score, "
     "band, and per-factor contributions ranked by points."),
    ("how", 6, "6. Mechanism & counterparties",
     "How the money moved — top counterparties by value, structuring / round-trip "
     "flow if any, and any sanctions / adverse-media hits on the parties."),
    ("action", 7, "7. Recommended action",
     "Recommended next step for the compliance function — freeze, escalate, "
     "file, pending KYC re-verification, etc."),
]


# ---------------------------------------------------------------------------
# Compose — the main entry point.
# ---------------------------------------------------------------------------


def compose(
    account_report: Dict[str, Any],
    analyst: str = "TITAN-AUTOMATED",
    redact: bool = False,
    include_zero_factors: bool = False,
) -> Dict[str, Any]:
    """Compose a fully cited narrative for one account report.

    Parameters
    ----------
    account_report:
        A dict shaped like ``risk.AccountReport.to_dict()``.  Missing
        keys are tolerated — the composer will emit ``_not_captured``
        placeholders that the quality checklist will flag.
    analyst:
        Name / handle stamped on the draft.  Free-form.
    redact:
        If true, subject and counterparty identifiers in the narrative
        are masked to the last four chars (``ACC-1234`` → ``···1234``).
        Citations retain their raw refs so the audit trail is intact.
    include_zero_factors:
        If true, factors with zero points are also listed under §5 for
        completeness (useful for training / QA).  Defaults false.
    """
    now = _iso_now()
    account_id = str(account_report.get("account_id") or "")
    if not account_id:
        raise ValueError("account_report.account_id is required")

    band = str(account_report.get("band") or "unknown")
    risk_score = float(account_report.get("risk_score") or 0.0)
    display_name = str(account_report.get("display_name") or "").strip()
    edges: List[Dict[str, Any]] = list(account_report.get("edges") or [])
    factors: List[Dict[str, Any]] = list(account_report.get("factors") or [])
    typologies: List[Dict[str, Any]] = list(account_report.get("typologies") or [])
    sanctions_hits: List[Dict[str, Any]] = list(account_report.get("sanctions_hits") or [])
    adverse_media = account_report.get("adverse_media") or None

    inbound = float(account_report.get("inbound_total") or 0.0)
    outbound = float(account_report.get("outbound_total") or 0.0)
    cparty_count = int(account_report.get("counterparty_count") or 0)

    period_start, period_end = _edge_period(edges)
    burst = _peak_burst(edges)
    geo_summary = _geo_summary(edges)
    channel_summary = _channel_summary(edges)
    top_cparties = _top_counterparties(edges, account_id)
    triggered_factors = [
        f for f in factors if float(f.get("points", 0.0)) > FACTOR_POINT_FLOOR
    ]

    sections: List[NarrativeSection] = []
    sections.append(_section_who(
        account_id=account_id,
        display_name=display_name,
        cparty_count=cparty_count,
        top_cparties=top_cparties,
        redact=redact,
    ))
    sections.append(_section_what(
        account_id=account_id,
        typologies=typologies,
        triggered_factors=triggered_factors,
    ))
    sections.append(_section_when(
        period_start=period_start,
        period_end=period_end,
        edges=edges,
        burst=burst,
    ))
    sections.append(_section_where(
        geo_summary=geo_summary,
        channel_summary=channel_summary,
    ))
    sections.append(_section_why(
        account_id=account_id,
        risk_score=risk_score,
        band=band,
        factors=factors,
        include_zero=include_zero_factors,
    ))
    sections.append(_section_how(
        account_id=account_id,
        edges=edges,
        inbound=inbound,
        outbound=outbound,
        top_cparties=top_cparties,
        sanctions_hits=sanctions_hits,
        adverse_media=adverse_media,
        redact=redact,
    ))
    sections.append(_section_action(
        typologies=typologies,
    ))

    quality = _score_quality(
        sections=sections,
        account_report=account_report,
        redact=redact,
    )

    evidence_index = _build_evidence_index(sections)

    codex_id = _draft_id(account_id, now)
    return {
        "codex_id": codex_id,
        "engine": ENGINE_VERSION,
        "generated_at": now,
        "analyst": analyst,
        "account_id": account_id,
        "display_name": display_name,
        "risk_score": round(risk_score, 1),
        "band": band,
        "redacted": bool(redact),
        "sections": [s.to_dict() for s in sections],
        "quality": quality.to_dict(),
        "evidence_index": [c.to_dict() for c in evidence_index],
        "totals": {
            "inbound": round(inbound, 2),
            "outbound": round(outbound, 2),
            "counterparty_count": cparty_count,
            "transactions_in_scope": len(edges),
        },
        "period": {"start": period_start, "end": period_end},
    }


# ---------------------------------------------------------------------------
# Section builders — one function per section id.  Each returns a
# fully-populated NarrativeSection.  Kept small and boring so the shape
# of the narrative reads directly off the code.
# ---------------------------------------------------------------------------


def _section_who(
    *,
    account_id: str,
    display_name: str,
    cparty_count: int,
    top_cparties: List[Tuple[str, float]],
    redact: bool,
) -> NarrativeSection:
    sec = _blank_section("who")
    subject_ref = _redact_id(account_id) if redact else account_id
    name_clause = f", trading as *{display_name}*" if display_name else ""
    sec.blocks.append(NarrativeBlock(
        text=(
            f"The subject of this report is account `{subject_ref}`{name_clause}. "
            f"During the reporting window the account transacted with **{cparty_count}** "
            f"distinct counterparties."
        ),
        citations=[
            Citation(kind="subject", ref=account_id,
                     label=f"Subject account {subject_ref}",
                     detail=display_name or ""),
            Citation(kind="totals", ref="counterparty_count",
                     label=f"{cparty_count} distinct counterparties",
                     detail=""),
        ],
    ))
    if top_cparties:
        preview = ", ".join(
            (_redact_id(name) if redact else name) for name, _ in top_cparties[:3]
        )
        sec.blocks.append(NarrativeBlock(
            text=(
                f"Immediate circle (top-3 by value): {preview}. "
                f"See §6 for the full counterparty table."
            ),
            citations=[
                Citation(kind="counterparty", ref=name,
                         label=(_redact_id(name) if redact else name),
                         detail=f"aggregate ₹{value:,.0f}")
                for name, value in top_cparties[:3]
            ],
        ))
    return sec


def _section_what(
    *,
    account_id: str,
    typologies: List[Dict[str, Any]],
    triggered_factors: List[Dict[str, Any]],
) -> NarrativeSection:
    sec = _blank_section("what")
    if typologies:
        top = typologies[0]
        conf = float(top.get("confidence") or 0.0)
        conf_pct = f"{conf * 100:.0f}%"
        top_name = top.get("name") or "(unnamed typology)"
        top_code = top.get("code") or ""
        primary_ok = conf >= TYPOLOGY_CONFIDENCE_FLOOR
        primary_line = (
            f"The pattern most closely fits the **{top_name}** laundering typology "
            f"(`{top_code}`, confidence {conf_pct})."
            if primary_ok else
            f"No laundering typology exceeded the {int(TYPOLOGY_CONFIDENCE_FLOOR * 100)}% "
            f"confidence floor; the strongest fit was {top_name} at {conf_pct}. "
            f"Per-detector evidence in §5 remains the substantive support."
        )
        sec.blocks.append(NarrativeBlock(
            text=primary_line,
            citations=[
                Citation(kind="typology", ref=str(top_code or top_name),
                         label=f"{top_name} · {conf_pct}",
                         detail=top.get("narrative") or ""),
            ],
        ))
        evidence = list(top.get("evidence") or [])[:MAX_TYPOLOGY_EVIDENCE]
        if evidence:
            sec.blocks.append(NarrativeBlock(
                text="Contributing evidence supporting the typology fit:",
                kind="bullet_list",
                items=[
                    f"{(ev.get('label') or ev.get('key') or 'evidence')}"
                    f" (signal {float(ev.get('signal') or 0.0) * 100:.0f}%)"
                    + (f" — {ev['detail']}" if ev.get("detail") else "")
                    for ev in evidence
                ],
                citations=[
                    Citation(kind="typology", ref=str(top_code or top_name),
                             label=str(ev.get("label") or ev.get("key") or "evidence"),
                             detail=str(ev.get("detail") or ""))
                    for ev in evidence
                ],
            ))
        runners = typologies[1:]
        if runners:
            sec.blocks.append(NarrativeBlock(
                text=(
                    "Runner-up typology fits (below the primary but retained for "
                    "future correlation): "
                    + ", ".join(
                        f"{t.get('name')} ({float(t.get('confidence') or 0.0) * 100:.0f}%)"
                        for t in runners[:4]
                    ) + "."
                ),
                citations=[
                    Citation(kind="typology", ref=str(t.get("code") or t.get("name") or ""),
                             label=f"{t.get('name')} ({float(t.get('confidence') or 0.0) * 100:.0f}%)")
                    for t in runners[:4]
                ],
            ))
    else:
        sec.blocks.append(NarrativeBlock(
            text=(
                "The classifier returned no typology fit above the confidence "
                "floor; treat per-detector evidence in §5 as the primary support."
            ),
            citations=[],
        ))

    if triggered_factors:
        top_factor_names = [
            f.get("name") or "(unnamed)"
            for f in sorted(
                triggered_factors,
                key=lambda f: float(f.get("points", 0.0)),
                reverse=True,
            )[:3]
        ]
        sec.blocks.append(NarrativeBlock(
            text=(
                f"Detectors that fired in support: "
                f"{', '.join(_titleize(n) for n in top_factor_names)}."
            ),
            citations=[
                Citation(kind="factor", ref=str(f.get("name") or ""),
                         label=_titleize(str(f.get("name") or "")),
                         detail=str(f.get("detail") or ""))
                for f in sorted(
                    triggered_factors,
                    key=lambda f: float(f.get("points", 0.0)),
                    reverse=True,
                )[:3]
            ],
        ))
    return sec


def _section_when(
    *,
    period_start: str,
    period_end: str,
    edges: List[Dict[str, Any]],
    burst: Optional[Dict[str, Any]],
) -> NarrativeSection:
    sec = _blank_section("when")
    if period_start and period_end:
        span_days = _period_span_days(period_start, period_end)
        span_line = (
            f"same-day activity" if span_days == 0
            else f"a {span_days}-day window"
        )
        sec.blocks.append(NarrativeBlock(
            text=(
                f"The reported activity spans **{span_line}**, "
                f"from `{period_start}` to `{period_end}`, comprising "
                f"**{len(edges)}** in-scope transactions."
            ),
            citations=[
                Citation(kind="period", ref="start", label=period_start),
                Citation(kind="period", ref="end", label=period_end),
                Citation(kind="totals", ref="transaction_count",
                         label=f"{len(edges)} transactions"),
            ],
        ))
    else:
        sec.blocks.append(NarrativeBlock(
            text=(
                "No timestamped edges accompanied this report; the activity "
                "period is _not captured_ and should be added before filing."
            ),
            citations=[],
        ))
    if burst:
        sec.blocks.append(NarrativeBlock(
            text=(
                f"Peak burst: **{burst['count']}** transactions on `{burst['date']}`, "
                f"aggregating ₹{burst['value']:,.0f}."
            ),
            citations=[
                Citation(kind="period", ref=burst["date"],
                         label=f"Peak day {burst['date']}",
                         detail=f"{burst['count']} tx / ₹{burst['value']:,.0f}"),
            ],
        ))
    return sec


def _section_where(
    *,
    geo_summary: List[Tuple[str, int, float]],
    channel_summary: List[Tuple[str, int, float]],
) -> NarrativeSection:
    sec = _blank_section("where")
    if geo_summary:
        preview = ", ".join(
            f"{g} ({int(v)} tx / ₹{val:,.0f})" for g, v, val in geo_summary[:4]
        )
        sec.blocks.append(NarrativeBlock(
            text=f"Jurisdictional footprint: {preview}.",
            citations=[
                Citation(kind="geo", ref=g, label=g,
                         detail=f"{int(v)} tx / ₹{val:,.0f}")
                for g, v, val in geo_summary[:6]
            ],
        ))
    else:
        sec.blocks.append(NarrativeBlock(
            text=(
                "No geographic tags were present on the in-scope transactions; "
                "jurisdictional analysis is limited."
            ),
            citations=[],
        ))
    if channel_summary:
        preview = ", ".join(
            f"{c} ({int(v)} tx)" for c, v, _ in channel_summary[:4]
        )
        sec.blocks.append(NarrativeBlock(
            text=f"Channel mix: {preview}.",
            citations=[
                Citation(kind="channel", ref=c, label=c,
                         detail=f"{int(v)} tx / ₹{val:,.0f}")
                for c, v, val in channel_summary[:6]
            ],
        ))
    return sec


def _section_why(
    *,
    account_id: str,
    risk_score: float,
    band: str,
    factors: List[Dict[str, Any]],
    include_zero: bool,
) -> NarrativeSection:
    sec = _blank_section("why")
    sec.blocks.append(NarrativeBlock(
        text=(
            f"The account carries a composite risk score of "
            f"**{risk_score:.1f} / 100** ({band}). "
            "The score is the sum of per-detector contributions, each "
            "individually explainable — every point is attributable to "
            "at least one rule."
        ),
        citations=[
            Citation(kind="band", ref=band,
                     label=f"{band.upper()} risk",
                     detail=f"{risk_score:.1f}/100"),
        ],
    ))
    ranked = sorted(
        factors,
        key=lambda f: float(f.get("points", 0.0)),
        reverse=True,
    )
    contributing = [
        f for f in ranked
        if include_zero or float(f.get("points", 0.0)) > FACTOR_POINT_FLOOR
    ]
    if contributing:
        columns = ["#", "Detector", "Points", "Weight", "Detail"]
        rows: List[List[str]] = []
        citations: List[Citation] = []
        for i, f in enumerate(contributing[:12], start=1):
            name = str(f.get("name") or "")
            points = float(f.get("points", 0.0))
            weight = float(f.get("weight", 0.0))
            detail = str(f.get("detail") or "")
            rows.append([
                str(i),
                _titleize(name),
                f"{points:.2f}",
                f"{weight:.1f}",
                detail,
            ])
            citations.append(Citation(
                kind="factor",
                ref=name,
                label=_titleize(name),
                detail=f"{points:.2f}/{weight:.1f} — {detail}",
            ))
        sec.blocks.append(NarrativeBlock(
            text="Per-detector contribution (ranked by points):",
            kind="table",
            columns=columns,
            rows=rows,
            citations=citations,
        ))
    else:
        sec.blocks.append(NarrativeBlock(
            text=(
                "No detector produced non-zero points.  This should not have "
                "reached a case; review the alert-generation upstream."
            ),
            citations=[],
        ))
    return sec


def _section_how(
    *,
    account_id: str,
    edges: List[Dict[str, Any]],
    inbound: float,
    outbound: float,
    top_cparties: List[Tuple[str, float]],
    sanctions_hits: List[Dict[str, Any]],
    adverse_media: Optional[Dict[str, Any]],
    redact: bool,
) -> NarrativeSection:
    sec = _blank_section("how")
    net = outbound - inbound
    net_desc = (
        f"net-outflow of ₹{net:,.0f}" if net > 0
        else f"net-inflow of ₹{-net:,.0f}" if net < 0
        else "balanced in-and-out"
    )
    sec.blocks.append(NarrativeBlock(
        text=(
            f"Aggregate flow: inbound ₹{inbound:,.2f} vs outbound "
            f"₹{outbound:,.2f} ({net_desc}). See the counterparty and "
            f"transaction extracts below for the mechanism."
        ),
        citations=[
            Citation(kind="totals", ref="inbound",
                     label=f"₹{inbound:,.0f} in",
                     detail=""),
            Citation(kind="totals", ref="outbound",
                     label=f"₹{outbound:,.0f} out",
                     detail=""),
        ],
    ))
    if top_cparties:
        columns = ["Rank", "Counterparty", "Aggregate ₹"]
        rows = [
            [
                str(i),
                _redact_id(name) if redact else name,
                f"{value:,.2f}",
            ]
            for i, (name, value) in enumerate(top_cparties[:MAX_COUNTERPARTIES_CITED], start=1)
        ]
        sec.blocks.append(NarrativeBlock(
            text="Top counterparties by transacted value:",
            kind="table",
            columns=columns,
            rows=rows,
            citations=[
                Citation(kind="counterparty", ref=name,
                         label=(_redact_id(name) if redact else name),
                         detail=f"aggregate ₹{value:,.0f}")
                for name, value in top_cparties[:MAX_COUNTERPARTIES_CITED]
            ],
        ))
    representative = _representative_transactions(edges, account_id)
    if representative:
        columns = ["Timestamp", "Direction", "Counterparty", "Channel", "Amount ₹"]
        rows: List[List[str]] = []
        cites: List[Citation] = []
        for e in representative:
            other = e["to"] if e["from"] == account_id else e["from"]
            direction = "OUT" if e["from"] == account_id else "IN"
            ts = str(e.get("timestamp") or "")
            channel = str(e.get("channel") or "").strip() or "—"
            amt = float(e.get("amount", 0.0))
            other_disp = _redact_id(other) if redact else other
            rows.append([ts, direction, other_disp, channel, f"{amt:,.2f}"])
            cites.append(Citation(
                kind="transaction",
                ref=f"{ts}|{direction}|{other}|{amt}",
                label=f"{direction} ₹{amt:,.0f} @ {ts}",
                detail=f"cparty {other_disp} · {channel}",
            ))
        sec.blocks.append(NarrativeBlock(
            text="Representative transactions cited in evidence:",
            kind="table",
            columns=columns,
            rows=rows,
            citations=cites,
        ))
    if sanctions_hits:
        preview = ", ".join(
            f"{h.get('name')} ({h.get('list') or 'watchlist'})"
            for h in sanctions_hits[:4]
        )
        sec.blocks.append(NarrativeBlock(
            text=(
                f"Sanctions overlay: **{len(sanctions_hits)}** watchlist "
                f"hits attached to the case — {preview}."
            ),
            citations=[
                Citation(kind="sanctions", ref=str(h.get("entity_id") or h.get("name") or ""),
                         label=f"{h.get('name')} · {h.get('list') or 'watchlist'}",
                         detail=(h.get("reason") or ""))
                for h in sanctions_hits[:6]
            ],
        ))
    else:
        sec.blocks.append(NarrativeBlock(
            text="No watchlist hits were attached to the case snapshot.",
            citations=[],
        ))
    if isinstance(adverse_media, dict) and adverse_media.get("hit_count", 0):
        sec.blocks.append(NarrativeBlock(
            text=(
                f"Adverse-media signal: **{adverse_media.get('grade') or 'unknown'}** "
                f"({adverse_media.get('hit_count')} article hit(s))."
            ),
            citations=[
                Citation(kind="media", ref=str(adverse_media.get("grade") or "media"),
                         label=f"Adverse media {adverse_media.get('grade')}",
                         detail=str(adverse_media.get("summary") or "")),
            ],
        ))
    return sec


def _section_action(
    *,
    typologies: List[Dict[str, Any]],
) -> NarrativeSection:
    sec = _blank_section("action")
    top = typologies[0] if typologies else None
    recommended = (
        (top.get("recommended_action") if top else None) or
        "Escalate to compliance review; freeze outbound transfers above "
        "₹10,00,000 pending KYC re-verification of subject and counterparties."
    )
    sec.blocks.append(NarrativeBlock(
        text=recommended,
        citations=[
            Citation(kind="typology", ref=str((top or {}).get("code") or "default"),
                     label="Recommended action",
                     detail=str((top or {}).get("name") or "default policy")),
        ] if top else [],
    ))
    return sec


# ---------------------------------------------------------------------------
# Quality checklist.
# ---------------------------------------------------------------------------


def _score_quality(
    *,
    sections: List[NarrativeSection],
    account_report: Dict[str, Any],
    redact: bool,
) -> Quality:
    by_id: Dict[str, NarrativeSection] = {s.id: s for s in sections}
    all_citations: List[Citation] = [
        c for s in sections for b in s.blocks for c in b.citations
    ]
    kinds_present = {c.kind for c in all_citations}

    def section_has(kind: str, sec_id: str) -> bool:
        s = by_id.get(sec_id)
        if not s:
            return False
        for b in s.blocks:
            if any(c.kind == kind for c in b.citations):
                return True
        return False

    def section_text(sec_id: str) -> str:
        s = by_id.get(sec_id)
        if not s:
            return ""
        parts: List[str] = []
        for b in s.blocks:
            parts.append(b.text)
            parts.extend(b.items)
        return " \n".join(parts)

    typologies = list(account_report.get("typologies") or [])
    factors = list(account_report.get("factors") or [])
    triggered_factors = [
        f for f in factors if float(f.get("points", 0.0)) > FACTOR_POINT_FLOOR
    ]
    edges = list(account_report.get("edges") or [])
    inbound = float(account_report.get("inbound_total") or 0.0)
    outbound = float(account_report.get("outbound_total") or 0.0)
    sanctions_hits = list(account_report.get("sanctions_hits") or [])
    account_id = str(account_report.get("account_id") or "")
    period_start, period_end = _edge_period(edges)

    checks: List[QualityCheck] = []

    checks.append(QualityCheck(
        id="subject_named",
        section="who",
        label="Subject is identified",
        weight=10.0,
        passed=bool(account_id) and section_has("subject", "who"),
        detail=(
            f"Subject account `{_redact_id(account_id) if redact else account_id}` cited."
            if account_id else "No subject account on the report."
        ),
        hint="Every SAR must name its subject; add or repair the account_id.",
    ))

    checks.append(QualityCheck(
        id="period_bounded",
        section="when",
        label="Activity period is bounded",
        weight=10.0,
        passed=bool(period_start and period_end and period_start != period_end),
        detail=(
            f"Period `{period_start}` → `{period_end}`."
            if period_start and period_end else
            "No timestamped edges — activity window is _not captured_."
        ),
        hint="Add at least two timestamped transactions so the window is well-defined.",
    ))

    checks.append(QualityCheck(
        id="amounts_present",
        section="how",
        label="Aggregate flows cited",
        weight=8.0,
        passed=(inbound + outbound) > 0 and section_has("totals", "how"),
        detail=f"Inbound ₹{inbound:,.0f}, outbound ₹{outbound:,.0f}.",
        hint="Ensure §6 lists inbound and outbound totals with amounts.",
    ))

    primary_ok = bool(typologies) and float(typologies[0].get("confidence") or 0.0) >= TYPOLOGY_CONFIDENCE_FLOOR
    checks.append(QualityCheck(
        id="primary_typology",
        section="what",
        label="Primary typology cited",
        weight=10.0,
        passed=primary_ok and section_has("typology", "what"),
        detail=(
            f"Primary: {typologies[0].get('name')} "
            f"({float(typologies[0].get('confidence') or 0.0) * 100:.0f}%)."
            if typologies else "No typology available."
        ),
        hint=(
            f"No typology above the {int(TYPOLOGY_CONFIDENCE_FLOOR * 100)}% "
            "confidence floor; rely on §5 factor evidence or re-triage."
        ) if not primary_ok else "",
    ))

    checks.append(QualityCheck(
        id="factors_named",
        section="why",
        label="At least one detector cited by name",
        weight=10.0,
        passed=bool(triggered_factors) and section_has("factor", "why"),
        detail=(
            f"{len(triggered_factors)} detector(s) triggered."
            if triggered_factors else
            "No detector produced points; the case should not have reached filing."
        ),
        hint="If no detector fired, re-open triage before drafting.",
    ))

    # ≥3 representative transactions cited by amount+timestamp anywhere.
    tx_citations = [c for c in all_citations if c.kind == "transaction"]
    checks.append(QualityCheck(
        id="specific_edges",
        section="how",
        label="≥3 representative transactions cited",
        weight=12.0,
        passed=len(tx_citations) >= 3,
        detail=f"{len(tx_citations)} transaction(s) cited inline.",
        hint="Include at least three specific transactions so the mechanism is checkable.",
    ))

    checks.append(QualityCheck(
        id="counterparty_named",
        section="how",
        label="At least one counterparty cited",
        weight=8.0,
        passed=section_has("counterparty", "how") or section_has("counterparty", "who"),
        detail=(
            "Counterparties surfaced in §1 and §6."
            if section_has("counterparty", "how") else
            "No counterparty cited — check the edge list on the report."
        ),
        hint="Cite at least the highest-value counterparty by name / ref.",
    ))

    geo_ok = section_has("geo", "where") or section_has("channel", "where")
    checks.append(QualityCheck(
        id="geo_declared",
        section="where",
        label="Jurisdictions or channels declared",
        weight=6.0,
        passed=geo_ok,
        detail=(
            "Geography and/or channel mix is stated in §4."
            if geo_ok else
            "No jurisdiction or channel tags on the transactions; §4 is thin."
        ),
        hint="Tag geo / channel on the source transactions to strengthen §4.",
    ))

    sanctions_ok = bool(sanctions_hits) or "No watchlist hits" in section_text("how")
    checks.append(QualityCheck(
        id="sanctions_screened",
        section="how",
        label="Sanctions screening is declared (hit or clean)",
        weight=8.0,
        passed=sanctions_ok,
        detail=(
            f"{len(sanctions_hits)} sanctions hit(s) declared."
            if sanctions_hits else
            "Sanctions screening result stated as clean."
        ),
        hint="Declare sanctions screening even when the result is negative.",
    ))

    action_text = section_text("action").strip()
    checks.append(QualityCheck(
        id="action_stated",
        section="action",
        label="Recommended action is stated",
        weight=8.0,
        passed=len(action_text) >= 25,
        detail=(
            f"Action section is {len(action_text)} chars."
            if action_text else "Action section is empty."
        ),
        hint="Every SAR must recommend a next step for the compliance function.",
    ))

    full_text = "\n".join(section_text(s.id) for s in sections)
    placeholder = bool(re.search(r"\bTBD\b|\bTODO\b|\[FILL[^\]]*\]|_not captured_", full_text, re.IGNORECASE))
    checks.append(QualityCheck(
        id="no_placeholder",
        section="global",
        label="No placeholders / unresolved TODOs",
        weight=5.0,
        passed=not placeholder,
        detail=(
            "No placeholder strings detected."
            if not placeholder else
            "Placeholder strings present — resolve TBD / TODO / _not captured_ before filing."
        ),
        hint="Fill or delete every TBD / TODO / [FILL] token before filing.",
    ))

    checks.append(QualityCheck(
        id="redaction_applied",
        section="global",
        label="Identifier redaction rules applied",
        weight=5.0,
        passed=(not redact) or _redaction_looks_applied(full_text, account_id),
        detail=(
            "Redaction disabled — verbatim identifiers retained."
            if not redact else
            "Redaction applied to subject and counterparty identifiers."
        ),
        hint="Toggle redaction on for external distribution.",
    ))

    total_weight = sum(c.weight for c in checks) or 1.0
    passed_weight = sum(c.weight for c in checks if c.passed)
    score = 100.0 * passed_weight / total_weight
    passed = sum(1 for c in checks if c.passed)
    failed = sum(1 for c in checks if not c.passed)
    grade = _grade_for(score)

    expected_kinds = {
        "subject", "typology", "factor", "transaction", "counterparty",
        "period", "band", "totals",
    }
    missing = sorted(expected_kinds - kinds_present)

    return Quality(
        score=score,
        grade=grade,
        passed=passed,
        failed=failed,
        checks=checks,
        missing_evidence_kinds=missing,
    )


# ---------------------------------------------------------------------------
# Markdown export — the paste-into-a-case-note view.
# ---------------------------------------------------------------------------


def to_markdown(codex: Dict[str, Any]) -> str:
    """Render a composed codex payload as GitHub-flavoured markdown."""
    lines: List[str] = []
    lines.append(f"# Suspicious Activity Report — Draft")
    lines.append("")
    lines.append(f"- **Reference**: `{codex['codex_id']}`")
    lines.append(f"- **Filed by (analyst)**: {codex['analyst']}")
    lines.append(f"- **Generated (UTC)**: {codex['generated_at']}")
    subject_disp = codex["account_id"]
    if codex.get("redacted"):
        subject_disp = _redact_id(subject_disp)
    lines.append(f"- **Subject account**: `{subject_disp}`")
    lines.append(
        f"- **Risk score**: **{codex['risk_score']}/100** ({codex['band']})"
    )
    quality = codex["quality"]
    lines.append(
        f"- **Draft quality**: **{quality['grade_label']}** "
        f"({quality['score']}/100 · {quality['passed']} pass / {quality['failed']} fail)"
    )
    lines.append("")

    for section in codex["sections"]:
        lines.append(f"## {section['title']}")
        lines.append(f"> _{section['prompt']}_")
        lines.append("")
        for block in section["blocks"]:
            if block["kind"] == "para" and block.get("text"):
                lines.append(block["text"])
                lines.append("")
            elif block["kind"] == "bullet_list":
                if block.get("text"):
                    lines.append(block["text"])
                    lines.append("")
                for item in block.get("items", []):
                    lines.append(f"- {item}")
                lines.append("")
            elif block["kind"] == "table":
                if block.get("text"):
                    lines.append(block["text"])
                    lines.append("")
                cols = block.get("columns") or []
                if cols:
                    lines.append("| " + " | ".join(cols) + " |")
                    lines.append("| " + " | ".join("---" for _ in cols) + " |")
                    for row in block.get("rows", []):
                        lines.append("| " + " | ".join(str(x) for x in row) + " |")
                    lines.append("")

    lines.append("## Draft-quality checklist")
    lines.append("")
    lines.append("| Check | Weight | Result |")
    lines.append("| --- | ---: | --- |")
    for c in quality["checks"]:
        mark = "✅" if c["passed"] else "❌"
        lines.append(f"| {c['label']} | {c['weight']:.1f} | {mark} {c['detail']} |")
    lines.append("")
    if quality.get("missing_evidence_kinds"):
        lines.append(
            "**Missing evidence kinds**: "
            + ", ".join(f"`{k}`" for k in quality["missing_evidence_kinds"])
        )
        lines.append("")
    lines.append(
        f"_Engine: `{codex['engine']}`.  Every citation traces back to the "
        f"underlying account report — see the ``evidence_index`` field of the "
        f"structured payload for the full addressable list._"
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Rules dump + sample builder.
# ---------------------------------------------------------------------------


def get_rules() -> Dict[str, Any]:
    return {
        "engine": ENGINE_VERSION,
        "typology_confidence_floor": TYPOLOGY_CONFIDENCE_FLOOR,
        "factor_point_floor": FACTOR_POINT_FLOOR,
        "max_transactions_cited": MAX_TRANSACTIONS_CITED,
        "max_counterparties_cited": MAX_COUNTERPARTIES_CITED,
        "max_typology_evidence": MAX_TYPOLOGY_EVIDENCE,
        "grade_ladder": [
            {"min_score": min_score, "grade": grade, **GRADE_META[grade]}
            for min_score, grade in GRADE_LADDER
        ],
        "sections": [
            {"id": sid, "number": n, "title": t, "prompt": p}
            for sid, n, t, p in SECTION_SPECS
        ],
        "evidence_kinds": [
            {"kind": k, "label": lbl}
            for k, lbl in [
                ("subject", "Subject account"),
                ("counterparty", "Counterparty"),
                ("transaction", "Transaction"),
                ("factor", "Detector / factor"),
                ("typology", "Laundering typology"),
                ("sanctions", "Sanctions hit"),
                ("media", "Adverse media"),
                ("period", "Time bound"),
                ("geo", "Jurisdiction"),
                ("channel", "Channel"),
                ("totals", "Aggregate totals"),
                ("band", "Risk band"),
            ]
        ],
        "checks": [
            {"id": cid, "label": lbl, "weight": w, "section": sec}
            for cid, sec, lbl, w in CHECK_CATALOG
        ],
    }


# Mirror of the checks emitted by _score_quality, exposed via get_rules()
# so the frontend can render the checklist skeleton before a compose call.
CHECK_CATALOG: List[Tuple[str, str, str, float]] = [
    ("subject_named", "who", "Subject is identified", 10.0),
    ("period_bounded", "when", "Activity period is bounded", 10.0),
    ("amounts_present", "how", "Aggregate flows cited", 8.0),
    ("primary_typology", "what", "Primary typology cited", 10.0),
    ("factors_named", "why", "At least one detector cited by name", 10.0),
    ("specific_edges", "how", "≥3 representative transactions cited", 12.0),
    ("counterparty_named", "how", "At least one counterparty cited", 8.0),
    ("geo_declared", "where", "Jurisdictions or channels declared", 6.0),
    ("sanctions_screened", "how", "Sanctions screening is declared (hit or clean)", 8.0),
    ("action_stated", "action", "Recommended action is stated", 8.0),
    ("no_placeholder", "global", "No placeholders / unresolved TODOs", 5.0),
    ("redaction_applied", "global", "Identifier redaction rules applied", 5.0),
]


def sample() -> Dict[str, Any]:
    """A bundled, self-contained demo account report + composed codex.

    Chosen to exercise every section — non-trivial typology fit, three
    named counterparties, multi-day burst, multi-jurisdiction mix, one
    watchlist hit, and a recommended action.  No external deps.
    """
    account_report = {
        "account_id": "ACC-DEMO-42",
        "display_name": "Nirvana Trading Co. (sole prop.)",
        "risk_score": 74.4,
        "band": "high",
        "counterparty_count": 8,
        "inbound_total": 4_820_000.0,
        "outbound_total": 4_712_500.0,
        "factors": [
            {"name": "structuring", "points": 18.0, "weight": 20.0,
             "detail": "12 deposits of ₹1.9-2.0L within 90 minutes on 2025-05-14.",
             "evidence": [{"key": "cluster_9", "label": "Sub-₹2L cluster (12 tx)",
                           "signal": 0.82, "detail": "z-score 3.1 vs cohort"}]},
            {"name": "round_trip", "points": 12.0, "weight": 15.0,
             "detail": "Two 3-hop cycles ACC-DEMO-42 → ACC-B1 → ACC-B2 → ACC-DEMO-42."},
            {"name": "velocity_spike", "points": 8.5, "weight": 10.0,
             "detail": "3× baseline daily volume on 2025-05-14."},
            {"name": "sanctions_hit", "points": 15.0, "weight": 20.0,
             "detail": "Counterparty ACC-C3 matched SDN entry (strong)."},
            {"name": "high_risk_geo", "points": 6.0, "weight": 10.0,
             "detail": "18% of value routed via IR / KP legs."},
            {"name": "fan_out", "points": 4.0, "weight": 8.0,
             "detail": "Rapid dispersal to 5 counterparties within 24h."},
            {"name": "adverse_media", "points": 0.0, "weight": 6.0, "detail": "No hits."},
            {"name": "round_amount", "points": 0.0, "weight": 4.0, "detail": "No hits."},
            {"name": "fan_in", "points": 0.0, "weight": 8.0, "detail": "No hits."},
        ],
        "edges": [
            {"from": "ACC-A1", "to": "ACC-DEMO-42", "amount": 195_000.0,
             "timestamp": "2025-05-14T09:12:00Z", "channel": "IMPS", "geo": "IN"},
            {"from": "ACC-A1", "to": "ACC-DEMO-42", "amount": 195_000.0,
             "timestamp": "2025-05-14T09:31:00Z", "channel": "IMPS", "geo": "IN"},
            {"from": "ACC-A2", "to": "ACC-DEMO-42", "amount": 199_500.0,
             "timestamp": "2025-05-14T09:44:00Z", "channel": "IMPS", "geo": "IN"},
            {"from": "ACC-A2", "to": "ACC-DEMO-42", "amount": 199_500.0,
             "timestamp": "2025-05-14T09:58:00Z", "channel": "IMPS", "geo": "IN"},
            {"from": "ACC-A3", "to": "ACC-DEMO-42", "amount": 189_000.0,
             "timestamp": "2025-05-14T10:12:00Z", "channel": "IMPS", "geo": "IN"},
            {"from": "ACC-DEMO-42", "to": "ACC-B1", "amount": 1_200_000.0,
             "timestamp": "2025-05-14T11:07:00Z", "channel": "RTGS", "geo": "IN"},
            {"from": "ACC-DEMO-42", "to": "ACC-C3", "amount": 850_000.0,
             "timestamp": "2025-05-14T12:33:00Z", "channel": "SWIFT", "geo": "AE"},
            {"from": "ACC-B1", "to": "ACC-B2", "amount": 1_150_000.0,
             "timestamp": "2025-05-14T13:44:00Z", "channel": "NEFT", "geo": "IN"},
            {"from": "ACC-B2", "to": "ACC-DEMO-42", "amount": 1_100_000.0,
             "timestamp": "2025-05-14T15:02:00Z", "channel": "NEFT", "geo": "IN"},
            {"from": "ACC-DEMO-42", "to": "ACC-D4", "amount": 620_000.0,
             "timestamp": "2025-05-15T09:33:00Z", "channel": "SWIFT", "geo": "IR"},
            {"from": "ACC-DEMO-42", "to": "ACC-E5", "amount": 445_000.0,
             "timestamp": "2025-05-16T11:15:00Z", "channel": "SWIFT", "geo": "KP"},
        ],
        "sanctions_hits": [
            {
                "entity_id": "SDN-9932",
                "name": "Kian Petro FZE",
                "type": "entity",
                "matched_alias": "Kian Petro",
                "alias_index": 1,
                "jurisdiction": "AE",
                "list": "OFAC-SDN",
                "reason": "IRGC procurement network — designated 2019.",
                "similarity": 0.91,
                "grade": "strong",
                "components": {"token_set": 0.92, "ngram": 0.9, "contain": 1.0, "blended": 0.91,
                               "jurisdiction_bonus": 0.05},
                "queried_name": "Kian Petro FZE",
                "queried_party": "ACC-C3",
                "queried_role": "counterparty",
            }
        ],
        "typologies": [
            {
                "code": "SMURF",
                "name": "Structuring / Smurfing",
                "confidence": 0.78,
                "severity_floor": "high",
                "narrative": (
                    "Aggregate cash-equivalent inbound at 12 tx of ₹1.9–2.0L in "
                    "under 90 minutes, layered outbound to two shell counterparties, "
                    "one leg to a SDN-designated FZE."
                ),
                "recommended_action": (
                    "Freeze outbound transfers above ₹10,00,000. File within 30 days. "
                    "Initiate KYC re-verification of ACC-C3 counterparty relationship. "
                    "Cross-reference with Nexus for beneficial owner overlap."
                ),
                "evidence": [
                    {"key": "sub_threshold_burst", "label": "12 sub-₹2L deposits < 90min",
                     "signal": 0.86, "detail": "z-score 3.1"},
                    {"key": "same_day_layer", "label": "Same-day layering B1→B2→self",
                     "signal": 0.71, "detail": "3-hop cycle · 97% amount retained"},
                    {"key": "sdn_leg", "label": "SDN leg on outbound",
                     "signal": 0.68, "detail": "AE · OFAC-SDN Kian Petro FZE"},
                ],
            },
            {
                "code": "LAYER",
                "name": "Layering (cycle)",
                "confidence": 0.55,
                "severity_floor": "high",
                "narrative": "Two 3-hop cycles B1→B2→self; retention ratio 92-97%.",
                "recommended_action": "Attach network map to case; escalate to Tier-2 review.",
                "evidence": [
                    {"key": "cycle_hop_3", "label": "3-hop return-to-self",
                     "signal": 0.72, "detail": "2 cycles · avg 5.5h dwell"},
                ],
            },
        ],
        "adverse_media": None,
    }

    codex = compose(account_report, analyst="analyst-4319", redact=False)
    return {
        "account_report": account_report,
        "codex": codex,
        "codex_redacted": compose(account_report, analyst="analyst-4319", redact=True),
    }


# ---------------------------------------------------------------------------
# Internal utilities.
# ---------------------------------------------------------------------------


def _blank_section(sec_id: str) -> NarrativeSection:
    for sid, num, title, prompt in SECTION_SPECS:
        if sid == sec_id:
            return NarrativeSection(id=sid, number=num, title=title, prompt=prompt)
    raise KeyError(f"unknown section id: {sec_id}")


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _draft_id(account_id: str, ts: str) -> str:
    h = hashlib.sha256(f"{account_id}|{ts}".encode()).hexdigest()
    return "CDX-" + h[:10].upper()


def _titleize(name: str) -> str:
    return name.replace("_", " ").title() if name else ""


_WORD = re.compile(r"[A-Za-z0-9]+")


def _words(text: str) -> List[str]:
    return _WORD.findall(text or "")


def _edge_period(edges: Iterable[Dict[str, Any]]) -> Tuple[str, str]:
    stamps = [str(e.get("timestamp") or "") for e in edges if e.get("timestamp")]
    if not stamps:
        return "", ""
    stamps.sort()
    return stamps[0], stamps[-1]


def _period_span_days(start: str, end: str) -> int:
    try:
        a = datetime.fromisoformat(start.replace("Z", "+00:00"))
        b = datetime.fromisoformat(end.replace("Z", "+00:00"))
    except ValueError:
        return 0
    delta = (b - a).days
    return max(0, int(delta))


def _peak_burst(edges: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not edges:
        return None
    by_day: Dict[str, List[Dict[str, Any]]] = {}
    for e in edges:
        ts = str(e.get("timestamp") or "")
        day = ts[:10]  # YYYY-MM-DD prefix — good enough for a burst chip
        by_day.setdefault(day, []).append(e)
    if not by_day:
        return None
    peak_day, peak_edges = max(by_day.items(), key=lambda kv: len(kv[1]))
    if len(peak_edges) < 3:
        return None
    total = sum(float(e.get("amount", 0.0)) for e in peak_edges)
    return {"date": peak_day, "count": len(peak_edges), "value": total}


def _top_counterparties(edges: List[Dict[str, Any]], subject: str) -> List[Tuple[str, float]]:
    agg: Dict[str, float] = {}
    for e in edges:
        other = e["to"] if e.get("from") == subject else e.get("from")
        if not other:
            continue
        agg[other] = agg.get(other, 0.0) + float(e.get("amount", 0.0))
    return sorted(agg.items(), key=lambda kv: kv[1], reverse=True)


def _representative_transactions(
    edges: List[Dict[str, Any]], subject: str
) -> List[Dict[str, Any]]:
    """Pick up to N transactions that best support the mechanism narrative.

    We pick: the two largest edges, plus the earliest and latest edges,
    plus one mid-window edge — deduped and capped.
    """
    if not edges:
        return []
    sorted_amt = sorted(edges, key=lambda e: -float(e.get("amount", 0.0)))
    sorted_time = sorted(edges, key=lambda e: str(e.get("timestamp") or ""))
    picks: List[Dict[str, Any]] = []
    seen: set = set()

    def _key(e: Dict[str, Any]) -> Tuple[str, str, str, float]:
        return (
            str(e.get("timestamp") or ""),
            str(e.get("from") or ""),
            str(e.get("to") or ""),
            float(e.get("amount", 0.0)),
        )

    for src in (
        sorted_amt[:2]
        + [sorted_time[0], sorted_time[-1]]
        + ([sorted_time[len(sorted_time) // 2]] if len(sorted_time) >= 3 else [])
    ):
        k = _key(src)
        if k in seen:
            continue
        seen.add(k)
        picks.append(src)
        if len(picks) >= MAX_TRANSACTIONS_CITED:
            break
    return picks


def _geo_summary(edges: List[Dict[str, Any]]) -> List[Tuple[str, int, float]]:
    agg: Dict[str, List[float]] = {}
    for e in edges:
        geo = (str(e.get("geo") or "").strip() or "UNKNOWN").upper()
        agg.setdefault(geo, []).append(float(e.get("amount", 0.0)))
    return sorted(
        [(g, len(v), sum(v)) for g, v in agg.items()],
        key=lambda t: t[2],
        reverse=True,
    )


def _channel_summary(edges: List[Dict[str, Any]]) -> List[Tuple[str, int, float]]:
    agg: Dict[str, List[float]] = {}
    for e in edges:
        ch = str(e.get("channel") or "").strip() or "UNKNOWN"
        agg.setdefault(ch, []).append(float(e.get("amount", 0.0)))
    return sorted(
        [(c, len(v), sum(v)) for c, v in agg.items()],
        key=lambda t: t[1],
        reverse=True,
    )


def _redact_id(ref: str) -> str:
    if not ref:
        return ref
    tail = ref[-4:] if len(ref) > 4 else ref
    return f"···{tail}"


_ACC_PATTERN = re.compile(r"[A-Z]{2,}-[A-Za-z0-9]+")


def _redaction_looks_applied(narrative_text: str, subject_id: str) -> bool:
    """Heuristic — if `redact` was requested, the subject id should not
    appear verbatim in the narrative text.

    Not a security control; a QA nudge only.  Callers wanting a
    guaranteed-redacted output should re-run compose() with redact=True.
    """
    if not subject_id:
        return True
    if subject_id in narrative_text:
        return False
    # Any long account-shaped literal is suspicious.
    for match in _ACC_PATTERN.findall(narrative_text or ""):
        if len(match) >= 8:
            return False
    return True


def _grade_for(score: float) -> str:
    for min_score, grade in GRADE_LADDER:
        if score >= min_score:
            return grade
    return GRADE_LADDER[-1][1]


def _build_evidence_index(sections: List[NarrativeSection]) -> List[Citation]:
    """Return every citation, deduped by (kind, ref).

    The order preserves first-appearance so the UI can render an
    inspector that reads top-to-bottom of the narrative.
    """
    seen: set = set()
    out: List[Citation] = []
    for s in sections:
        for b in s.blocks:
            for c in b.citations:
                key = (c.kind, c.ref)
                if key in seen:
                    continue
                seen.add(key)
                out.append(c)
    return out


# ---------------------------------------------------------------------------
# Ad-hoc CLI: ``python -m codex < report.json`` renders the markdown.
# ---------------------------------------------------------------------------

if __name__ == "__main__":  # pragma: no cover
    import json
    import sys

    payload = json.load(sys.stdin)
    print(to_markdown(compose(payload)))
