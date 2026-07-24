"""Curtain — PII / Secret Redaction & Egress Policy Studio (Day 93).

Round 20 for LLM_Playground. Every prior surface answered *quality* (Arena,
Rubrics, Judge, Suites), *robustness* (Adversary, Drift, Surgeon), *cost /
routing* (Frontier, Relay), *guarding against adversarial input* (Sentinel),
or *saving repeated calls* (Cache).

None of them ask the one question every LLM-powered product gets asked in
week two of production: **what personal or confidential data are we shipping
to third-party providers, and are we shipping it back to the user in the
response too?**

Curtain is the deterministic, two-sided data-egress studio for that.

Given a prompt (or a whole workload), Curtain:

* scans it for 14 canonical entities (email · phone · SSN · credit card w/
  Luhn · IBAN w/ mod-97 · IPv4 · UUID · OpenAI/Anthropic/AWS keys · generic
  high-entropy secret · JWT · URL-with-token · date-of-birth · MAC address ·
  geo coord · person name),
* applies a per-entity redaction strategy (mask · tag · hash · pseudonymize ·
  drop), preserving order so the model still sees a well-formed prompt,
* runs the redacted text through your model (out of scope for this engine —
  the frontend passes the response back in),
* re-scans the response for those same entities and flags any that were
  **not** in the original input (a "leak" — the model regurgitated
  training-data PII or fabricated new PII into the answer),
* rehydrates any pseudonym-tagged spans back to the originals so downstream
  code gets the intended values.

On top of the scanner it ships:

* a **policy compiler** that ranks 3 canonical policies (strict / balanced /
  permissive), each carrying a stable ``policy_id`` from the rule hash so a
  CI check can pin its compliance to a specific byte-identical policy,
* a **traffic simulator** projecting monthly leaked-entity counts, dollar-
  weighted breach exposure, and a compliance verdict (GDPR / HIPAA / PCI
  lean) from a workload sample,
* an **entity histogram**, a per-provider exposure map (which model provider
  a redacted-vs-raw prompt actually reaches), and a per-strategy
  effectiveness matrix (14 × 5 = 70 cells).

Zero third-party deps, zero persistence, pure functions — same request body
always yields the same response body byte-for-byte, which means the demo
lights up on first page load without any provider credentials and stays
byte-identical across refreshes.

Public surface: ``defaults``, ``list_entities``, ``list_strategies``,
``list_workloads``, ``load_workload``, ``scan_text``, ``redact_text``,
``rehydrate_text``, ``scan_output``, ``simulate_traffic``,
``recommend_policies``, ``compile_policy``, ``policy_markdown``,
``seed_demo``.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


ENGINE_VERSION = "curtain/1.0.0"

# ─── Entity catalog ─────────────────────────────────────────────────────────
# Each entity carries: id, human name, hue (Tailwind), severity 1..5,
# regulation family (gdpr/hipaa/pci/secret/pii), $ per-record breach cost
# (industry-report averages, sanitised), and a compiled pattern.
# Severity is used to weight the composite exposure risk; breach cost drives
# the monthly $-exposure forecast.
#
# Patterns are intentionally strict — false positives here are worse than
# false negatives, because a false positive corrupts the prompt the model
# actually sees. Where a pattern is loose (person_name), we mark it low-
# severity so the balanced/permissive policy leaves it alone.

_ENTITY_META: List[Dict[str, Any]] = [
    {
        "id": "EMAIL",
        "name": "Email address",
        "hue": "sky",
        "severity": 3,
        "family": "pii",
        "breach_cost_usd": 0.65,
        "example": "leia@rebellion.org",
    },
    {
        "id": "PHONE",
        "name": "Phone number",
        "hue": "cyan",
        "severity": 3,
        "family": "pii",
        "breach_cost_usd": 0.40,
        "example": "+91 98765 43210",
    },
    {
        "id": "SSN",
        "name": "US Social Security Number",
        "hue": "rose",
        "severity": 5,
        "family": "pii",
        "breach_cost_usd": 12.50,
        "example": "123-45-6789",
    },
    {
        "id": "CREDIT_CARD",
        "name": "Credit card (Luhn-valid)",
        "hue": "amber",
        "severity": 5,
        "family": "pci",
        "breach_cost_usd": 18.00,
        "example": "4111 1111 1111 1111",
    },
    {
        "id": "IBAN",
        "name": "IBAN (mod-97-valid)",
        "hue": "orange",
        "severity": 4,
        "family": "pci",
        "breach_cost_usd": 6.75,
        "example": "DE89 3704 0044 0532 0130 00",
    },
    {
        "id": "IPV4",
        "name": "IPv4 address",
        "hue": "emerald",
        "severity": 2,
        "family": "pii",
        "breach_cost_usd": 0.10,
        "example": "192.168.1.42",
    },
    {
        "id": "UUID",
        "name": "UUID / trace id",
        "hue": "teal",
        "severity": 1,
        "family": "pii",
        "breach_cost_usd": 0.05,
        "example": "550e8400-e29b-41d4-a716-446655440000",
    },
    {
        "id": "API_KEY_OPENAI",
        "name": "OpenAI-family API key",
        "hue": "violet",
        "severity": 5,
        "family": "secret",
        "breach_cost_usd": 26.00,
        "example": "sk-XxXxXxXxXxXxXxXxXxXxXxXxXxXxXxXxXxXxXxXx",
    },
    {
        "id": "API_KEY_ANTHROPIC",
        "name": "Anthropic API key",
        "hue": "fuchsia",
        "severity": 5,
        "family": "secret",
        "breach_cost_usd": 26.00,
        "example": "sk-ant-api03-XxXxXxXxXxXxXxXxXxXxXxXxXxXxXxXxXxXxXxXxXxXxXxXxXxXxXxXxXxXxXxXxXxXxXxXxXxXx",
    },
    {
        "id": "API_KEY_AWS",
        "name": "AWS access-key ID",
        "hue": "yellow",
        "severity": 5,
        "family": "secret",
        "breach_cost_usd": 34.00,
        "example": "AKIAIOSFODNN7EXAMPLE",
    },
    {
        "id": "API_KEY_GENERIC",
        "name": "High-entropy secret",
        "hue": "purple",
        "severity": 4,
        "family": "secret",
        "breach_cost_usd": 8.00,
        "example": "gho_ABCDEFGHIJKLMNOPQRSTUVWXYZ012345",
    },
    {
        "id": "JWT",
        "name": "JSON Web Token",
        "hue": "indigo",
        "severity": 4,
        "family": "secret",
        "breach_cost_usd": 5.20,
        "example": "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c",
    },
    {
        "id": "URL_WITH_TOKEN",
        "name": "URL with token in query",
        "hue": "lime",
        "severity": 4,
        "family": "secret",
        "breach_cost_usd": 3.90,
        "example": "https://api.example.com/v1?token=deadbeefcafe",
    },
    {
        "id": "DOB",
        "name": "Date of birth",
        "hue": "pink",
        "severity": 3,
        "family": "hipaa",
        "breach_cost_usd": 1.20,
        "example": "12/03/1988",
    },
    {
        "id": "MAC_ADDR",
        "name": "MAC address",
        "hue": "slate",
        "severity": 2,
        "family": "pii",
        "breach_cost_usd": 0.15,
        "example": "3c:22:fb:d7:e8:19",
    },
    {
        "id": "GEO_COORD",
        "name": "Geo coordinate pair",
        "hue": "blue",
        "severity": 2,
        "family": "pii",
        "breach_cost_usd": 0.35,
        "example": "12.9716, 77.5946",
    },
    {
        "id": "PERSON_NAME",
        "name": "Person name (title + given)",
        "hue": "stone",
        "severity": 1,
        "family": "pii",
        "breach_cost_usd": 0.20,
        "example": "Dr. Chandra Reddy",
    },
]

# Compile once; order matters — earlier entries win overlap ties when
# severities are equal (which they aren't often; PERSON_NAME is last).
_PATTERNS: List[Tuple[str, re.Pattern]] = [
    ("API_KEY_OPENAI", re.compile(r"\bsk(?!-ant-)[A-Za-z0-9_-]{20,}\b")),
    ("API_KEY_ANTHROPIC", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b")),
    ("API_KEY_AWS", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("JWT", re.compile(r"\beyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\b")),
    ("API_KEY_GENERIC", re.compile(
        r"\b(?:ghp|gho|ghu|ghs|glpat|xoxb|xoxa|xoxp)_[A-Za-z0-9_]{20,}\b"
    )),
    ("URL_WITH_TOKEN", re.compile(
        r"https?://[^\s]*?[?&](?:token|api[_-]?key|access[_-]?token|password|secret)=[^\s&]+"
    )),
    ("EMAIL", re.compile(r"\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}\b")),
    ("IBAN", re.compile(r"\b[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]{2,4}){3,7}\b")),
    ("CREDIT_CARD", re.compile(
        r"\b(?:\d[ -]?){13,19}\b"
    )),
    ("SSN", re.compile(r"\b(?!000|666|9\d{2})\d{3}[-\s]?(?!00)\d{2}[-\s]?(?!0000)\d{4}\b")),
    # PHONE: require a leading '+' (E.164), a US-style parenthesised area code,
    # or at least two separators between digit groups. This kills the false-
    # positive where a naked run of digits inside a UUID matched.
    ("PHONE", re.compile(
        r"(?:"
        r"\+\d{1,3}[\s.\-]?\d{2,5}(?:[\s.\-]?\d{2,5}){1,3}"
        r"|\(\d{2,4}\)\s?\d{2,5}[\s.\-]?\d{3,5}"
        r"|\b\d{2,4}[\s.\-]\d{3,5}[\s.\-]\d{3,5}\b"
        r")"
    )),
    ("UUID", re.compile(
        r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
    )),
    ("MAC_ADDR", re.compile(r"\b(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}\b")),
    ("IPV4", re.compile(
        r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d?\d)\b"
    )),
    ("DOB", re.compile(
        r"\b(?:0[1-9]|[12]\d|3[01])[/.-](?:0[1-9]|1[0-2])[/.-](?:19|20)\d{2}\b"
    )),
    ("GEO_COORD", re.compile(
        r"[-+]?(?:[1-8]?\d(?:\.\d{2,7})|90(?:\.0{2,7}))\s*,\s*[-+]?(?:180(?:\.0{2,7})|(?:1[0-7]\d|[1-9]?\d)(?:\.\d{2,7}))"
    )),
    ("PERSON_NAME", re.compile(
        r"\b(?:Mr|Mrs|Ms|Dr|Prof|Sir|Madam|Capt|Col|Sgt|Rev)\.?\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2}\b"
    )),
]

_ENTITY_INDEX: Dict[str, Dict[str, Any]] = {e["id"]: e for e in _ENTITY_META}


# ─── Strategy catalog ───────────────────────────────────────────────────────
STRATEGIES: List[Dict[str, Any]] = [
    {
        "id": "mask",
        "name": "Mask",
        "hue": "slate",
        "description": (
            "Replace each character with a heavy shade block (▓). Preserves "
            "length so downstream token counters stay honest. Not reversible."
        ),
        "reversible": False,
        "utility_loss": 0.85,
    },
    {
        "id": "tag",
        "name": "Tag",
        "hue": "sky",
        "description": (
            "Replace with a numbered semantic tag like [EMAIL_1]. The model "
            "still knows an email was there, and downstream code can "
            "reference it by tag."
        ),
        "reversible": True,
        "utility_loss": 0.30,
    },
    {
        "id": "hash",
        "name": "Hash",
        "hue": "violet",
        "description": (
            "Replace with the 10-char prefix of SHA-256(entity+salt). Same "
            "input always yields the same hash — safe for joins and audit "
            "logs but not for user-facing output."
        ),
        "reversible": False,
        "utility_loss": 0.55,
    },
    {
        "id": "pseudonymize",
        "name": "Pseudonymize",
        "hue": "emerald",
        "description": (
            "Replace with a plausible fake of the same shape (email→email, "
            "phone→phone) drawn deterministically from a hand-crafted pool. "
            "Reversible via the mapping returned in the scan payload."
        ),
        "reversible": True,
        "utility_loss": 0.10,
    },
    {
        "id": "drop",
        "name": "Drop",
        "hue": "rose",
        "description": (
            "Silently remove the span. Highest privacy, highest utility loss. "
            "Use for credentials that must never reach any third party."
        ),
        "reversible": False,
        "utility_loss": 1.00,
    },
]
STRATEGY_INDEX: Dict[str, Dict[str, Any]] = {s["id"]: s for s in STRATEGIES}


# ─── Default per-entity policies ────────────────────────────────────────────
# Three canonical policies. `strict` is the CI default for compliance-heavy
# workloads; `permissive` is for internal debugging where PII can flow but
# credentials must not; `balanced` is the middle path most teams ship.
POLICY_PRESETS: Dict[str, Dict[str, str]] = {
    "strict": {
        "EMAIL": "pseudonymize",
        "PHONE": "pseudonymize",
        "SSN": "drop",
        "CREDIT_CARD": "drop",
        "IBAN": "drop",
        "IPV4": "hash",
        "UUID": "hash",
        "API_KEY_OPENAI": "drop",
        "API_KEY_ANTHROPIC": "drop",
        "API_KEY_AWS": "drop",
        "API_KEY_GENERIC": "drop",
        "JWT": "drop",
        "URL_WITH_TOKEN": "drop",
        "DOB": "pseudonymize",
        "MAC_ADDR": "hash",
        "GEO_COORD": "mask",
        "PERSON_NAME": "pseudonymize",
    },
    "balanced": {
        "EMAIL": "pseudonymize",
        "PHONE": "mask",
        "SSN": "drop",
        "CREDIT_CARD": "drop",
        "IBAN": "mask",
        "IPV4": "tag",
        "UUID": "tag",
        "API_KEY_OPENAI": "drop",
        "API_KEY_ANTHROPIC": "drop",
        "API_KEY_AWS": "drop",
        "API_KEY_GENERIC": "drop",
        "JWT": "drop",
        "URL_WITH_TOKEN": "drop",
        "DOB": "tag",
        "MAC_ADDR": "tag",
        "GEO_COORD": "tag",
        "PERSON_NAME": "tag",
    },
    "permissive": {
        "EMAIL": "tag",
        "PHONE": "tag",
        "SSN": "mask",
        "CREDIT_CARD": "mask",
        "IBAN": "tag",
        "IPV4": "tag",
        "UUID": "tag",
        "API_KEY_OPENAI": "drop",
        "API_KEY_ANTHROPIC": "drop",
        "API_KEY_AWS": "drop",
        "API_KEY_GENERIC": "hash",
        "JWT": "hash",
        "URL_WITH_TOKEN": "mask",
        "DOB": "tag",
        "MAC_ADDR": "tag",
        "GEO_COORD": "tag",
        "PERSON_NAME": "tag",
    },
}

POLICY_HUES = {
    "strict":     "emerald",
    "balanced":   "sky",
    "permissive": "amber",
}

# Pool of plausible replacement values for pseudonymize, chosen so that a
# downstream model sees a well-formed prompt but never real data. Deterministic
# per-entity via SHA-256 index modulo pool length.
_PSEUDO_POOL: Dict[str, List[str]] = {
    "EMAIL": [
        "leia@rebellion.org", "einstein@princeton.edu", "curie@radium.fr",
        "ramanujan@trinity.uk", "hopper@navy.mil", "turing@bletchley.uk",
        "lovelace@analytical.co", "feynman@caltech.edu",
    ],
    "PHONE": [
        "+91 98111 22334", "+1 415 555 0132", "+44 7700 900456",
        "+81 90 5555 4321", "+49 30 5555 8899", "+61 4 5555 7788",
    ],
    "SSN": [
        "555-01-2345", "555-04-8765", "555-07-3344",
    ],
    "CREDIT_CARD": [
        "4111 1111 1111 1111", "5555 5555 5555 4444", "3782 8224 6310 005",
    ],
    "IBAN": [
        "DE89 3704 0044 0532 0130 00", "GB33 BUKB 2020 1555 5555 55",
    ],
    "IPV4": ["192.0.2.10", "198.51.100.42", "203.0.113.7"],
    "UUID": ["00000000-0000-4000-8000-000000000001",
              "00000000-0000-4000-8000-000000000002"],
    "API_KEY_OPENAI":    ["sk-0000000000000000000000000000000000000000"],
    "API_KEY_ANTHROPIC": ["sk-ant-api03-0000000000000000000000000000000000000000000000000000000000000000000000"],
    "API_KEY_AWS":       ["AKIA0000000000000000"],
    "API_KEY_GENERIC":   ["ghp_0000000000000000000000000000000000"],
    "JWT": ["eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIwIn0.0000000000000000000000000000000000000000000"],
    "URL_WITH_TOKEN": ["https://example.com/v1?token=REDACTED"],
    "DOB": ["01/01/1970", "15/06/1985", "22/11/2001"],
    "MAC_ADDR": ["00:11:22:33:44:55", "aa:bb:cc:dd:ee:ff"],
    "GEO_COORD": ["0.0000, 0.0000", "12.9716, 77.5946"],
    "PERSON_NAME": ["Dr. Aditi Rao", "Mr. Kai Nakamura", "Ms. Ana Ribeiro",
                     "Prof. Elena Volkov", "Sir Otis Bramble"],
}


# ─── Configuration defaults ─────────────────────────────────────────────────
DEFAULT_POLICY = "balanced"
DEFAULT_MONTHLY_REQUESTS = 100_000
DEFAULT_SALT = "curtain"


# ─── Small helpers ──────────────────────────────────────────────────────────
_ZW_RE = re.compile(r"[​-‏‪-‮⁠﻿]")


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "")
    text = _ZW_RE.sub("", text)
    return text


def _sha8(s: str, salt: str = DEFAULT_SALT) -> str:
    return hashlib.sha256((salt + "::" + s).encode("utf-8")).hexdigest()[:10]


def _luhn_ok(digits: str) -> bool:
    digits = re.sub(r"[^\d]", "", digits)
    if not (13 <= len(digits) <= 19):
        return False
    s = 0
    for i, ch in enumerate(reversed(digits)):
        n = int(ch)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        s += n
    return s % 10 == 0


def _iban_ok(iban: str) -> bool:
    iban = re.sub(r"[\s]", "", iban).upper()
    if len(iban) < 15 or len(iban) > 34:
        return False
    if not re.match(r"^[A-Z]{2}\d{2}[A-Z0-9]+$", iban):
        return False
    rearranged = iban[4:] + iban[:4]
    num = "".join(str(ord(c) - 55) if c.isalpha() else c for c in rearranged)
    try:
        return int(num) % 97 == 1
    except ValueError:
        return False


def _valid_span(entity_id: str, raw: str) -> bool:
    """Second-pass validator to kill false positives on numeric-heavy regexes."""
    if entity_id == "CREDIT_CARD":
        return _luhn_ok(raw)
    if entity_id == "IBAN":
        return _iban_ok(raw)
    if entity_id == "PHONE":
        digits = re.sub(r"[^\d]", "", raw)
        return 8 <= len(digits) <= 15
    return True


# ─── Scanner core ───────────────────────────────────────────────────────────
def _find_spans(text: str) -> List[Dict[str, Any]]:
    """Return non-overlapping spans, longest+higher-severity winning ties.

    Each span: {entity_id, start, end, raw, severity}.
    """
    text = _normalize(text)
    candidates: List[Dict[str, Any]] = []
    for entity_id, pat in _PATTERNS:
        meta = _ENTITY_INDEX[entity_id]
        for m in pat.finditer(text):
            raw = m.group(0)
            if not _valid_span(entity_id, raw):
                continue
            candidates.append({
                "entity_id": entity_id,
                "start": m.start(),
                "end": m.end(),
                "raw": raw,
                "severity": meta["severity"],
            })
    # Longest-first (a structured 36-char UUID should always beat a 10-char
    # digit-run PHONE fragment inside it), tie-break by severity then position.
    candidates.sort(key=lambda s: (-(s["end"] - s["start"]), -s["severity"], s["start"]))
    accepted: List[Dict[str, Any]] = []
    for c in candidates:
        overlap = False
        for a in accepted:
            if not (c["end"] <= a["start"] or c["start"] >= a["end"]):
                overlap = True
                break
        if not overlap:
            accepted.append(c)
    accepted.sort(key=lambda s: s["start"])
    return accepted


def scan_text(text: str) -> Dict[str, Any]:
    """Public scanner. Returns spans + entity histogram + exposure score."""
    text = _normalize(text)
    spans = _find_spans(text)
    hist: Dict[str, int] = {}
    for s in spans:
        hist[s["entity_id"]] = hist.get(s["entity_id"], 0) + 1
    exposure = 0.0
    for eid, count in hist.items():
        meta = _ENTITY_INDEX[eid]
        # Diminishing-return contribution — first hit of severity 5 already
        # tips the exposure; multiple hits saturate.
        exposure += meta["severity"] * (1 - math.pow(0.55, count))
    exposure = min(100.0, exposure * 10.0)
    band = _band_for(exposure)
    return {
        "text_length": len(text),
        "spans": spans,
        "histogram": hist,
        "exposure_score": round(exposure, 2),
        "exposure_band": band,
        "unique_entities": len(hist),
        "total_hits": len(spans),
    }


def _band_for(exposure: float) -> str:
    if exposure >= 70: return "critical"
    if exposure >= 45: return "high"
    if exposure >= 20: return "moderate"
    if exposure > 0:   return "low"
    return "clean"


# ─── Redaction / pseudonymization ───────────────────────────────────────────
def _pseudo_for(entity_id: str, raw: str, salt: str = DEFAULT_SALT) -> str:
    pool = _PSEUDO_POOL.get(entity_id, [])
    if not pool:
        return f"[{entity_id}]"
    h = int(hashlib.sha256((salt + "::pseudo::" + raw).encode("utf-8")).hexdigest(), 16)
    return pool[h % len(pool)]


def _apply_strategy(entity_id: str, raw: str, strategy: str, tag_idx: int,
                    salt: str) -> str:
    if strategy == "mask":
        # Preserve length; replace alphanumerics with ▓, keep separators.
        return "".join("▓" if ch.isalnum() else ch for ch in raw)
    if strategy == "tag":
        return f"[{entity_id}_{tag_idx}]"
    if strategy == "hash":
        return f"[{entity_id}#{_sha8(raw, salt)}]"
    if strategy == "pseudonymize":
        return _pseudo_for(entity_id, raw, salt)
    if strategy == "drop":
        return ""
    return raw


def redact_text(text: str, policy: Optional[Dict[str, str]] = None,
                salt: str = DEFAULT_SALT) -> Dict[str, Any]:
    """Redact text under a policy. Returns {redacted, spans, mapping, delta}.

    ``mapping`` is a list of {tag, entity_id, raw} pairs; only present for
    reversible strategies (tag, pseudonymize). Callers can pass this to
    ``rehydrate_text`` to restore the originals after the model call.
    """
    text = _normalize(text)
    policy = policy or POLICY_PRESETS[DEFAULT_POLICY]
    spans = _find_spans(text)

    # Per-entity counter for tag numbering
    counters: Dict[str, int] = {}
    mapping: List[Dict[str, Any]] = []
    out: List[str] = []
    cursor = 0
    for s in spans:
        strategy = policy.get(s["entity_id"], "tag")
        counters[s["entity_id"]] = counters.get(s["entity_id"], 0) + 1
        idx = counters[s["entity_id"]]
        out.append(text[cursor:s["start"]])
        redacted = _apply_strategy(s["entity_id"], s["raw"], strategy, idx, salt)
        out.append(redacted)
        s = dict(s)
        s["strategy"] = strategy
        s["redacted"] = redacted
        s["tag_index"] = idx
        # Only reversible strategies get a mapping entry
        if strategy in ("tag", "pseudonymize"):
            mapping.append({
                "tag": redacted if strategy == "tag" else _tag_key(s["entity_id"], idx),
                "placeholder": redacted,
                "entity_id": s["entity_id"],
                "raw": s["raw"],
                "strategy": strategy,
            })
        cursor = s["end"]
    out.append(text[cursor:])
    redacted_text = "".join(out)

    delta_chars = len(redacted_text) - len(text)
    return {
        "original": text,
        "redacted": redacted_text,
        "spans": spans,
        "mapping": mapping,
        "delta_chars": delta_chars,
        "policy": policy,
        "salt": salt,
        "counters": counters,
    }


def _tag_key(entity_id: str, idx: int) -> str:
    return f"[{entity_id}_{idx}]"


def rehydrate_text(text: str, mapping: Sequence[Dict[str, Any]]) -> str:
    """Reverse tag/pseudonym placeholders in a model response back to originals."""
    if not text:
        return text
    out = text
    # Sort placeholders longest-first so [EMAIL_10] doesn't get eaten by [EMAIL_1]
    for m in sorted(mapping, key=lambda x: -len(x.get("placeholder") or "")):
        placeholder = m.get("placeholder")
        raw = m.get("raw")
        if placeholder and raw and placeholder in out:
            out = out.replace(placeholder, raw)
    return out


def scan_output(output_text: str, input_scan: Optional[Dict[str, Any]] = None
                ) -> Dict[str, Any]:
    """Two-sided scan: find entities in the *response* the model returned.

    Anything that wasn't in the input is flagged as a *leak candidate* — the
    model either regurgitated training-data PII or fabricated new sensitive-
    looking data into the answer.
    """
    scan = scan_text(output_text)
    input_raws: set[str] = set()
    if input_scan and input_scan.get("spans"):
        for s in input_scan["spans"]:
            input_raws.add(s["raw"])
    leaks: List[Dict[str, Any]] = []
    for s in scan["spans"]:
        if s["raw"] not in input_raws:
            leaks.append(s)
    leak_score = 0.0
    for l in leaks:
        meta = _ENTITY_INDEX[l["entity_id"]]
        leak_score += meta["severity"] * 6.0
    leak_score = min(100.0, leak_score)
    return {
        **scan,
        "leaks": leaks,
        "leak_count": len(leaks),
        "leak_score": round(leak_score, 2),
        "leak_band": _band_for(leak_score),
    }


# ─── Policy compiler ────────────────────────────────────────────────────────
def _policy_id(policy: Dict[str, str], salt: str = DEFAULT_SALT) -> str:
    blob = json.dumps({"policy": policy, "v": ENGINE_VERSION, "salt": salt},
                       sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def _policy_stats(policy: Dict[str, str]) -> Dict[str, Any]:
    """Aggregate stats over a policy: reversibility %, expected utility loss,
    per-strategy count, per-family coverage."""
    n = len(policy)
    strategy_hist: Dict[str, int] = {}
    utility_sum = 0.0
    reversible_sum = 0
    family_cov: Dict[str, Dict[str, int]] = {}
    for eid, strat in policy.items():
        meta = _ENTITY_INDEX.get(eid)
        s_meta = STRATEGY_INDEX.get(strat)
        if not meta or not s_meta: continue
        strategy_hist[strat] = strategy_hist.get(strat, 0) + 1
        utility_sum += s_meta["utility_loss"] * (meta["severity"] / 5.0)
        if s_meta["reversible"]:
            reversible_sum += 1
        fam = meta["family"]
        family_cov.setdefault(fam, {"total": 0, "protected": 0})
        family_cov[fam]["total"] += 1
        if strat != "tag":  # tag = still visible in shape; count as "seen"
            family_cov[fam]["protected"] += 1
    return {
        "reversibility_pct": round(reversible_sum / max(1, n) * 100, 1),
        "utility_loss": round(utility_sum / max(1, n), 3),
        "strategy_histogram": strategy_hist,
        "family_coverage": family_cov,
    }


def compile_policy(policy: Dict[str, str],
                   salt: str = DEFAULT_SALT,
                   sample_text: Optional[str] = None) -> Dict[str, Any]:
    """Compile a per-entity policy into a shippable, byte-stable JSON blob.

    Includes a deterministic ``policy_id`` (sha256 prefix), per-strategy
    aggregate stats, and (optionally) a sample_pipeline preview showing what
    the compiled policy would do to a given piece of text.
    """
    # Fill missing entities with tag (safe default — visible to model as
    # shape, non-reversible-ly nothing).
    full_policy = {eid: policy.get(eid, "tag") for eid in _ENTITY_INDEX}
    pid = _policy_id(full_policy, salt)
    stats = _policy_stats(full_policy)
    result: Dict[str, Any] = {
        "policy_id": pid,
        "policy": full_policy,
        "salt": salt,
        "engine_version": ENGINE_VERSION,
        "stats": stats,
    }
    if sample_text:
        red = redact_text(sample_text, full_policy, salt)
        result["sample_preview"] = {
            "original_head": red["original"][:200],
            "redacted_head": red["redacted"][:200],
            "spans_seen": len(red["spans"]),
            "delta_chars": red["delta_chars"],
        }
    return result


def policy_markdown(compiled: Dict[str, Any]) -> str:
    """Emit a compliance-friendly markdown summary of a compiled policy."""
    p = compiled["policy"]
    stats = compiled["stats"]
    lines: List[str] = []
    lines.append(f"# Curtain policy `{compiled['policy_id']}`")
    lines.append("")
    lines.append(f"Engine `{compiled['engine_version']}` · salt `{compiled['salt']}`")
    lines.append("")
    lines.append(f"- **Reversibility**: {stats['reversibility_pct']}% of entities")
    lines.append(f"- **Utility loss** (severity-weighted): {stats['utility_loss']}")
    lines.append("")
    lines.append("## Per-entity strategy")
    lines.append("")
    lines.append("| Entity | Family | Severity | Strategy | Reversible |")
    lines.append("|---|---|---:|---|---|")
    for eid, strat in p.items():
        meta = _ENTITY_INDEX[eid]
        s_meta = STRATEGY_INDEX.get(strat, {})
        lines.append(
            f"| {eid} | {meta['family']} | {meta['severity']} | {strat} | "
            f"{'yes' if s_meta.get('reversible') else 'no'} |"
        )
    lines.append("")
    lines.append("## Family coverage")
    lines.append("")
    lines.append("| Family | Protected / Total |")
    lines.append("|---|---:|")
    for fam, cov in stats["family_coverage"].items():
        lines.append(f"| {fam} | {cov['protected']} / {cov['total']} |")
    return "\n".join(lines)


# Per-strategy residual leak factor from the perspective of the third-party
# provider (0 = provider learns nothing about the value, 1 = full leak).
# - drop:         removed entirely             → 0
# - mask:         value replaced with ▓        → 0
# - hash:         opaque 10-char digest        → 0.05 (rainbow-table risk)
# - pseudonymize: plausible fake same shape    → 0.05 (schema tell)
# - tag:          [EMAIL_1] placeholder        → 0.25 (schema + count visible)
_RESIDUAL_LEAK: Dict[str, float] = {
    "drop":         0.00,
    "mask":         0.00,
    "hash":         0.05,
    "pseudonymize": 0.05,
    "tag":          0.25,
}


# ─── Traffic simulator ─────────────────────────────────────────────────────
def simulate_traffic(workload: Sequence[str],
                     policy: Dict[str, str],
                     monthly_requests: int = DEFAULT_MONTHLY_REQUESTS,
                     salt: str = DEFAULT_SALT) -> Dict[str, Any]:
    """Simulate a monthly traffic footprint under a policy.

    Returns entity mix, monthly leaked-entity forecast (pre/post redaction),
    dollar-weighted breach exposure, and a compliance verdict lean.
    """
    n = max(1, len(workload))
    hist_pre: Dict[str, int] = {}
    hist_post: Dict[str, int] = {}
    breach_pre = 0.0
    breach_post = 0.0
    exposure_scores: List[float] = []
    for text in workload:
        scan = scan_text(text)
        exposure_scores.append(scan["exposure_score"])
        for s in scan["spans"]:
            eid = s["entity_id"]
            hist_pre[eid] = hist_pre.get(eid, 0) + 1
            breach_pre += _ENTITY_INDEX[eid]["breach_cost_usd"]
            strat = policy.get(eid, "tag")
            residual = _RESIDUAL_LEAK.get(strat, 0.25)
            if residual >= 0.20:      # anything the provider can still count
                hist_post[eid] = hist_post.get(eid, 0) + 1
            breach_post += _ENTITY_INDEX[eid]["breach_cost_usd"] * residual
    per_month_scale = monthly_requests / n
    return {
        "sample_size": n,
        "avg_exposure_score": round(sum(exposure_scores) / n, 2) if exposure_scores else 0.0,
        "max_exposure_score": max(exposure_scores) if exposure_scores else 0.0,
        "entities_pre":  {k: round(v * per_month_scale, 0) for k, v in hist_pre.items()},
        "entities_post": {k: round(v * per_month_scale, 0) for k, v in hist_post.items()},
        "breach_exposure_pre_usd":  round(breach_pre * per_month_scale, 2),
        "breach_exposure_post_usd": round(breach_post * per_month_scale, 2),
        "reduction_pct": round(
            (1 - breach_post / breach_pre) * 100, 1
        ) if breach_pre > 0 else 0.0,
        "compliance_verdict": _compliance_verdict(hist_pre, hist_post, policy),
    }


def _compliance_verdict(pre: Dict[str, int], post: Dict[str, int],
                        policy: Dict[str, str]) -> Dict[str, Any]:
    """Rough lean on GDPR / HIPAA / PCI posture. Not legal advice."""
    fam_pre: Dict[str, int] = {}
    fam_post: Dict[str, int] = {}
    for eid, c in pre.items():
        fam_pre[_ENTITY_INDEX[eid]["family"]] = fam_pre.get(_ENTITY_INDEX[eid]["family"], 0) + c
    for eid, c in post.items():
        fam_post[_ENTITY_INDEX[eid]["family"]] = fam_post.get(_ENTITY_INDEX[eid]["family"], 0) + c
    def _lean(family: str, gdpr_weight: float = 1.0) -> str:
        pre_c = fam_pre.get(family, 0)
        post_c = fam_post.get(family, 0)
        if pre_c == 0: return "clean"
        drop = 1 - (post_c / pre_c)
        if drop >= 0.9: return "compliant"
        if drop >= 0.6: return "borderline"
        return "non_compliant"
    return {
        "gdpr":  _lean("pii", 1.0),
        "hipaa": _lean("hipaa", 1.5),
        "pci":   _lean("pci", 2.0),
        "secret": _lean("secret", 2.0),
    }


# ─── Policy recommender ─────────────────────────────────────────────────────
def recommend_policies(workload: Sequence[str],
                       monthly_requests: int = DEFAULT_MONTHLY_REQUESTS,
                       salt: str = DEFAULT_SALT) -> List[Dict[str, Any]]:
    """Return the 3 canonical policies scored against the given workload."""
    results: List[Dict[str, Any]] = []
    for pid in ("strict", "balanced", "permissive"):
        policy = POLICY_PRESETS[pid]
        sim = simulate_traffic(workload, policy, monthly_requests, salt)
        compiled = compile_policy(policy, salt)
        results.append({
            "preset": pid,
            "hue": POLICY_HUES[pid],
            "policy_id": compiled["policy_id"],
            "stats": compiled["stats"],
            "simulation": sim,
            "score": _policy_score(pid, sim, compiled),
        })
    return results


def _policy_score(preset: str, sim: Dict[str, Any], compiled: Dict[str, Any]) -> float:
    """Composite score for the recommender: 60% reduction, 40% utility.

    strict prioritises reduction; permissive prioritises utility; balanced is
    the balanced mean.
    """
    reduction = sim.get("reduction_pct", 0.0) / 100.0
    utility = 1.0 - compiled["stats"]["utility_loss"]
    if preset == "strict":
        return round(0.75 * reduction + 0.25 * utility, 4)
    if preset == "permissive":
        return round(0.30 * reduction + 0.70 * utility, 4)
    return round(0.55 * reduction + 0.45 * utility, 4)


# ─── Seed / defaults / listing ──────────────────────────────────────────────
_SEED_WORKLOAD: List[str] = [
    # Realistic customer-support prompt with an email + phone + ticket UUID.
    "Hi, my order ref 550e8400-e29b-41d4-a716-446655440000 hasn't shipped. "
    "Reach me at leia@rebellion.org or +91 98765 43210 — I'll be at "
    "12.9716, 77.5946 today.",
    # Dev debugging prompt with a secret and JWT that must never egress.
    "curl -H 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c' "
    "-H 'x-api-key: sk-XxXxXxXxXxXxXxXxXxXxXxXxXxXxXxXxXxXxXxXx' "
    "https://api.example.com/v1/user/42?token=deadbeefcafe",
    # Healthcare intake — DOB + name + patient MRN-ish UUID.
    "Patient Dr. Chandra Reddy, dob 12/03/1988, MRN "
    "550e8400-e29b-41d4-a716-446655440111, presented with...",
    # Finance ticket — credit card + SSN. Both critical.
    "Please refund transaction on card 4111 1111 1111 1111 for SSN 123-45-6789.",
    # Devops prompt — IPs + MAC + AWS key.
    "Instance 192.168.1.42 (mac 3c:22:fb:d7:e8:19) failed to assume "
    "role AKIAIOSFODNN7EXAMPLE from 198.51.100.42.",
    # Product feedback — mostly clean, a stray email.
    "Loving the new dashboard! One thing — the KPI cards feel a bit dense. "
    "You can email me back at hopper@navy.mil.",
    # RAG-style prompt with an IBAN.
    "Summarize this invoice: bill to Mr. Kai Nakamura, IBAN DE89 3704 0044 0532 0130 00, due 22/11/2025.",
    # Support ticket — phone only, low severity.
    "My WiFi keeps disconnecting. Call me at 415-555-0132.",
]


def load_workload(name: str = "default") -> List[str]:
    return list(_SEED_WORKLOAD)


def list_workloads() -> List[Dict[str, Any]]:
    return [{
        "id": "default",
        "name": "Support + dev + healthcare + finance mix",
        "size": len(_SEED_WORKLOAD),
        "description": (
            "8-prompt seed mix covering the four families Curtain protects — "
            "PII, PCI, HIPAA, secrets — with realistic paraphrases and one "
            "clean baseline row."
        ),
    }]


def list_entities() -> List[Dict[str, Any]]:
    return list(_ENTITY_META)


def list_strategies() -> List[Dict[str, Any]]:
    return list(STRATEGIES)


def defaults() -> Dict[str, Any]:
    return {
        "engine_version": ENGINE_VERSION,
        "monthly_requests": DEFAULT_MONTHLY_REQUESTS,
        "salt": DEFAULT_SALT,
        "presets": list(POLICY_PRESETS.keys()),
        "default_preset": DEFAULT_POLICY,
        "policy_hues": POLICY_HUES,
    }


def seed_demo() -> Dict[str, Any]:
    """One-call demo payload for the frontend on first paint."""
    workload = load_workload()
    scans = [scan_text(t) for t in workload]
    recs = recommend_policies(workload)
    balanced = POLICY_PRESETS["balanced"]
    sample = workload[0]
    redacted = redact_text(sample, balanced)
    compiled = compile_policy(balanced, sample_text=sample)
    # Fake a downstream model response for the two-sided demo.
    demo_output = (
        "Thanks — the ticket is on its way. If you need help you can also "
        "email newton@apple.com (this address wasn't in your message)."
    )
    output_scan = scan_output(demo_output, input_scan=scans[0])
    return {
        "engine_version": ENGINE_VERSION,
        "workload": workload,
        "input_scans": scans,
        "recommendations": recs,
        "sample_redaction": redacted,
        "sample_compile": compiled,
        "sample_output_scan": output_scan,
        "entities": list_entities(),
        "strategies": list_strategies(),
        "policy_presets": {k: dict(v) for k, v in POLICY_PRESETS.items()},
    }


__all__ = [
    "ENGINE_VERSION",
    "defaults",
    "list_entities",
    "list_strategies",
    "list_workloads",
    "load_workload",
    "scan_text",
    "redact_text",
    "rehydrate_text",
    "scan_output",
    "simulate_traffic",
    "recommend_policies",
    "compile_policy",
    "policy_markdown",
    "seed_demo",
    "POLICY_PRESETS",
]
