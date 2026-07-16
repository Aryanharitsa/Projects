"""TITAN Horizon — regulatory-change impact simulator.

Every prior TITAN surface reasons about the *current* rule config:

    risk / typology / drift / triage / precedent / nexus / pulse

They answer "given today's weights, thresholds, and lists, what
should this case look like?".  None of them answer the question the
compliance-officer actually loses sleep over the night before a
policy revision ships:

    "If I push this change, which of the six-hundred cases already in
     the queue would flip band?  Which cleared cases would re-fire?
     Which analyst decisions become inconsistent with the new rules?
     Which detectors do the damage — and which do nothing?"

That is the *regulatory-change impact* question.  It arrives in the
book any time:

  - A supervisor (FinCEN, RBI, FCA, MAS) publishes a new list —
    a jurisdiction gets added to the FATF grey list, OFAC adds
    entities to SDN, RBI updates its high-risk-country note.
  - The bank's Second Line proposes a re-calibration — bumping the
    structuring weight because auditors flagged too many misses,
    or lowering the sanctions-hit threshold after a controlled test.
  - A new typology comes out of FATF or FinCEN — TBML uplift,
    layering weight change, mule-account pattern re-emphasised.
  - The MLRO wants to re-tune band cutoffs (currently 30 / 60 / 80)
    against the analyst-workload reality of the past quarter.

Under status-quo compliance tech every one of those changes rolls
out blind: nobody knows the size of the backlog impact until the
first analyst mornings reveal the delta.  Horizon runs the change
*before* it ships — over the exact snapshots the case store already
holds — and reports the delta case-by-case, band-by-band, detector-
by-detector, alongside a per-case explainer that names the driver.

Design
======

1.  **Deterministic replay** — no simulation, no sampling, no ML.
    The engine is a pure function::

        simulate(proposal, cases, rules) → HorizonReport

    Given the same three inputs on any machine, at any time, in any
    order, it emits the same report.  That is a hard requirement:
    compliance change-management runs on approvals, and an approver
    cannot sign off on a stochastic answer.

2.  **Factor arithmetic preserved from `risk.py`.**  Each factor on a
    snapshot carries ``points`` (already weighted) and ``weight``
    (the weight active when the snapshot was frozen).  The engine
    recovers the underlying *intensity*:

        intensity_f = points_f / weight_f    (when weight_f > 0)

    …then re-projects it under the new weight:

        new_points_f = clip(intensity_f * new_weight_f, 0, cap)

    That is exactly the arithmetic `risk.score_accounts` uses, so
    a re-weighted replay agrees with a fresh score-from-scratch to
    the tenth of a point.  Zeroing a weight (disabling a detector)
    is the limit case of this identity.

3.  **Threshold + list edits work off snapshotted evidence.**  When
    the proposal shifts the sanctions similarity gate from 0.65 to
    0.70, the engine walks the ``sanctions_hits`` block of the
    snapshot, drops the hits below the new threshold, and re-projects
    the sanctions_hit factor from the surviving hits' intensity
    contribution.  New sanctions entries fuzz-match against the
    subject_name / counterparty_names captured in evidence, and any
    match promotes the sanctions_hit factor to the "guaranteed hit"
    intensity floor.

4.  **Jurisdiction risk-shift** re-projects `high_risk_geo` from the
    counterparty geographies stored on ``edges`` / factor evidence.
    A country moving from grey to black bumps its per-hit contribution
    by ``JURISDICTION_UPLIFT``; a country coming off the list drops
    to zero without touching the intensity of the surviving hits.

5.  **Band cutoffs** apply *after* score recomputation.  The proposal
    can leave them at their default (30 / 60 / 80) or shift the
    boundary triple; alert-fire is defined as ``new_band ≥ high``.

6.  **Per-case verdict ladder** rolls up the four axes so the UI can
    band the case list without re-reading every field.  A case is
    ``material_flip`` if the alert-fire boolean flipped OR the band
    moved more than one step; ``band_shift`` on a within-alert one-
    step move; ``touched`` on a score-only delta; ``stable`` if no
    axis moved.

7.  **Aggregate roll-up** exposes the six numbers a regulator will
    ask for during a change-management review:

      - total_cases replayed
      - by_verdict counts (material_flip / band_shift / touched / stable)
      - alert_flips: cleared_to_alert, alert_to_cleared, still_alert
      - band_matrix: old_band × new_band 4×4 counts
      - detector_contribution: |Δpoints| summed per detector
      - suggested next action: `defer | pilot | roll_out | investigate`

Everything is pure-stdlib (no NumPy, no third-party fuzz libs); the
name-similarity used by "additional sanctions" reuses the token-set
+ substring routine that lives on `sanctions.py` — imported lazily so
the engine still runs if that module is stubbed for a smoke test.

The FastAPI surface (`/aml/horizon/*`) is defined in `main.py`.  This
module exports:

  - HorizonProposal          (typed dict / dataclass wrapper)
  - HorizonImpact            (per-case delta)
  - HorizonReport            (aggregate + list of impacts)
  - PRESETS                  (six curated proposals for the sample)
  - simulate(...)            (the deterministic replay)
  - simulate_from_store(...) (loads the case store + calls simulate)
  - explain_case(...)        (per-case drill-down explainer)
  - get_rules()              (auditor-facing config surface)
  - export_markdown(...)     (paste-into-Slack / email brief)
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

import cases as case_store
import risk as risk_engine
import sanctions as sanctions_engine


# ---------------------------------------------------------------------------
# Tunables — exposed as-is via /aml/horizon/rules so an approver can
# see exactly which numbers moved.  Every constant here also has a doc
# comment; the frontend renders those beside the sliders.
# ---------------------------------------------------------------------------

# When the frozen snapshot carries a factor with weight == 0 the
# intensity is undefined (0 / 0).  In that case we treat the factor as
# "at rest" — the new weight scales an intensity of 0.0.  This is the
# behaviour a fresh score-from-scratch would produce.
INTENSITY_EPSILON = 1e-9

# Factor points get clipped to [0, MAX_FACTOR_POINTS].  This must agree
# with `risk.MAX_WEIGHT` — the invariant is that no detector alone can
# push the composite score more than MAX_FACTOR_POINTS points.
MAX_FACTOR_POINTS = 60.0

# Default band cutoffs — must agree with `risk._band`.
DEFAULT_BAND_CUTOFFS: Tuple[float, float, float] = (30.0, 60.0, 80.0)

# Score above which a case is considered "alert-fire" — equal to the
# high-band cutoff by default.  Kept as a separate constant so the
# frontend can plot the alert line even after cutoffs are edited.
DEFAULT_ALERT_THRESHOLD = 60.0

# Sanctions engine defaults.  Kept in sync with `risk.SANCTIONS_HIT_THRESHOLD`.
DEFAULT_SANCTIONS_THRESHOLD = 0.65

# When a new sanction entry matches a snapshot's subject / counterparty
# via fuzzy match, the sanctions_hit factor is boosted to at least this
# intensity (0..1).  Chosen so a fresh SDN hit meaningfully lifts the
# score even if the original snapshot had none.
NEW_SANCTIONS_INTENSITY_FLOOR = 0.75

# Jurisdiction moving from off-list to on-list bumps the high_risk_geo
# factor intensity by this much per matching evidence row.  Chosen so
# a case that had two Panama edges going from grey to black bumps a
# ~28-point-weight detector by ~14 points — enough to move the case
# one band without dominating.
JURISDICTION_UPLIFT = 0.35

# Verdict ladder — first-match-wins, top-to-bottom.  Order matters:
# `material_flip` catches alert-fire flips and band jumps >= 2;
# `band_shift` catches a one-step band move within alert bands;
# `touched` catches score-only movement above SCORE_TOUCH_EPS;
# `stable` is the else branch.
SCORE_TOUCH_EPS = 0.75

VERDICT_LABEL: Dict[str, str] = {
    "material_flip": "Material flip",
    "band_shift": "Band shift",
    "touched": "Score touched",
    "stable": "Stable",
}

VERDICT_ACCENT: Dict[str, str] = {
    "material_flip": "rose",
    "band_shift": "amber",
    "touched": "violet",
    "stable": "teal",
}

BAND_ORDER: Tuple[str, ...] = ("low", "medium", "high", "critical")
BAND_RANK: Dict[str, int] = {b: i for i, b in enumerate(BAND_ORDER)}

ENGINE_VERSION = "titan-horizon/1.0.0"


# ---------------------------------------------------------------------------
# Domain types — kept as dataclasses so the callers can accept dicts
# from JSON with light Pydantic validation upstream, and this module can
# stay pure and testable.
# ---------------------------------------------------------------------------


@dataclass
class SanctionSeed:
    """A single new sanctions entry the proposal wants to add.

    `name` is the primary alias.  `aliases` is optional (extends the
    fuzzy-match surface).  `list_name` and `jurisdiction` show up in
    the per-case explainer so an analyst can trace which entry fired.
    """

    name: str
    aliases: List[str] = field(default_factory=list)
    list_name: str = "PROPOSED"
    jurisdiction: str = ""
    reason: str = ""

    def surface(self) -> List[str]:
        out = [self.name]
        for a in self.aliases:
            if a and a not in out:
                out.append(a)
        return out


@dataclass
class HorizonProposal:
    """The bundle of edits an approver is proposing.

    Every field is optional; an empty proposal is a valid no-op and the
    engine will happily report ``verdict = stable`` on every case.  The
    Pydantic model in `main.py` mirrors this shape one-to-one.
    """

    name: str = "Untitled proposal"
    summary: str = ""
    author: str = "compliance"
    # Detector weight overrides.  Missing keys inherit the current weight
    # from `risk.WEIGHTS`.  Values are clipped to `[0, risk.MAX_WEIGHT]`.
    weights: Dict[str, float] = field(default_factory=dict)
    # Detectors to force off — equivalent to weight -> 0 but the UI can
    # tell the difference in the explainer.
    disabled_detectors: List[str] = field(default_factory=list)
    # New sanctions similarity gate.  ``None`` keeps the default 0.65.
    sanctions_threshold: Optional[float] = None
    # New watchlist entries to fold in.  Each is fuzz-matched against the
    # subject_name and counterparty_names on every snapshot.
    additional_sanctions: List[SanctionSeed] = field(default_factory=list)
    # Country codes newly *added* to the high-risk list (ISO alpha-2).
    jurisdiction_uplift: List[str] = field(default_factory=list)
    # Country codes newly *removed* from the high-risk list.
    jurisdiction_relief: List[str] = field(default_factory=list)
    # Optional band-cutoff override (low..medium, medium..high, high..critical).
    # ``None`` inherits `DEFAULT_BAND_CUTOFFS`.
    band_cutoffs: Optional[Tuple[float, float, float]] = None
    # Overrides the alert-fire threshold used for alert-flip counting.
    alert_threshold: Optional[float] = None

    def effective_weights(self) -> Dict[str, float]:
        """The resolved weight map after applying every override + disable."""
        out = dict(risk_engine.WEIGHTS)
        for k, v in self.weights.items():
            if k not in out:
                continue
            try:
                fv = float(v)
            except (TypeError, ValueError):
                continue
            out[k] = max(0.0, min(risk_engine.MAX_WEIGHT, fv))
        for name in self.disabled_detectors:
            if name in out:
                out[name] = 0.0
        return out

    def effective_cutoffs(self) -> Tuple[float, float, float]:
        if not self.band_cutoffs:
            return DEFAULT_BAND_CUTOFFS
        lo, mid, hi = self.band_cutoffs
        lo = max(0.0, min(100.0, float(lo)))
        mid = max(lo + 1.0, min(100.0, float(mid)))
        hi = max(mid + 1.0, min(100.0, float(hi)))
        return (lo, mid, hi)

    def effective_alert_threshold(self) -> float:
        if self.alert_threshold is not None:
            return max(0.0, min(100.0, float(self.alert_threshold)))
        return self.effective_cutoffs()[1]

    def effective_sanctions_threshold(self) -> float:
        if self.sanctions_threshold is None:
            return DEFAULT_SANCTIONS_THRESHOLD
        return max(0.0, min(1.0, float(self.sanctions_threshold)))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "summary": self.summary,
            "author": self.author,
            "weights": self.weights,
            "disabled_detectors": self.disabled_detectors,
            "sanctions_threshold": self.sanctions_threshold,
            "additional_sanctions": [
                {
                    "name": s.name,
                    "aliases": s.aliases,
                    "list": s.list_name,
                    "jurisdiction": s.jurisdiction,
                    "reason": s.reason,
                }
                for s in self.additional_sanctions
            ],
            "jurisdiction_uplift": self.jurisdiction_uplift,
            "jurisdiction_relief": self.jurisdiction_relief,
            "band_cutoffs": list(self.band_cutoffs) if self.band_cutoffs else None,
            "alert_threshold": self.alert_threshold,
            "effective_weights": self.effective_weights(),
            "effective_cutoffs": list(self.effective_cutoffs()),
            "effective_alert_threshold": self.effective_alert_threshold(),
            "effective_sanctions_threshold": self.effective_sanctions_threshold(),
        }


@dataclass
class DetectorDelta:
    """Per-detector points delta for one case."""

    name: str
    old_points: float
    new_points: float
    old_weight: float
    new_weight: float
    intensity: float  # snapshot intensity (0..1)
    reason: str

    @property
    def delta(self) -> float:
        return self.new_points - self.old_points

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "old_points": round(self.old_points, 2),
            "new_points": round(self.new_points, 2),
            "delta": round(self.delta, 2),
            "old_weight": self.old_weight,
            "new_weight": self.new_weight,
            "intensity": round(self.intensity, 4),
            "reason": self.reason,
        }


@dataclass
class HorizonImpact:
    """Per-case replay result."""

    case_id: str
    account_id: str
    display_name: str
    status: str
    priority: str
    assignee: Optional[str]
    old_score: float
    new_score: float
    old_band: str
    new_band: str
    old_alerted: bool
    new_alerted: bool
    verdict: str
    detectors: List[DetectorDelta]
    fired_sanctions: List[Dict[str, Any]]
    dropped_sanctions: List[Dict[str, Any]]
    driver_note: str

    @property
    def score_delta(self) -> float:
        return self.new_score - self.old_score

    @property
    def band_step(self) -> int:
        return BAND_RANK.get(self.new_band, 0) - BAND_RANK.get(self.old_band, 0)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "case_id": self.case_id,
            "account_id": self.account_id,
            "display_name": self.display_name,
            "status": self.status,
            "priority": self.priority,
            "assignee": self.assignee,
            "old_score": round(self.old_score, 1),
            "new_score": round(self.new_score, 1),
            "score_delta": round(self.score_delta, 1),
            "old_band": self.old_band,
            "new_band": self.new_band,
            "band_step": self.band_step,
            "old_alerted": self.old_alerted,
            "new_alerted": self.new_alerted,
            "alert_flip": (
                "cleared_to_alert" if (not self.old_alerted and self.new_alerted)
                else "alert_to_cleared" if (self.old_alerted and not self.new_alerted)
                else "still_alert" if self.new_alerted
                else "still_cleared"
            ),
            "verdict": self.verdict,
            "verdict_label": VERDICT_LABEL[self.verdict],
            "verdict_accent": VERDICT_ACCENT[self.verdict],
            "detectors": [d.to_dict() for d in self.detectors],
            "fired_sanctions": self.fired_sanctions,
            "dropped_sanctions": self.dropped_sanctions,
            "driver_note": self.driver_note,
        }


@dataclass
class HorizonReport:
    """Aggregate + list of per-case impacts."""

    proposal: HorizonProposal
    cases: List[HorizonImpact]
    generated_at: str
    rules_version: str

    def summary(self) -> Dict[str, Any]:
        total = len(self.cases)
        by_verdict = {v: 0 for v in VERDICT_LABEL}
        alert_flip = {
            "cleared_to_alert": 0,
            "alert_to_cleared": 0,
            "still_alert": 0,
            "still_cleared": 0,
        }
        detector_contribution: Dict[str, float] = {
            n: 0.0 for n in risk_engine.DETECTOR_ORDER
        }
        band_matrix: Dict[str, Dict[str, int]] = {
            b: {b2: 0 for b2 in BAND_ORDER} for b in BAND_ORDER
        }
        score_deltas: List[float] = []
        for c in self.cases:
            by_verdict[c.verdict] += 1
            score_deltas.append(c.score_delta)
            if c.new_alerted and not c.old_alerted:
                alert_flip["cleared_to_alert"] += 1
            elif c.old_alerted and not c.new_alerted:
                alert_flip["alert_to_cleared"] += 1
            elif c.new_alerted:
                alert_flip["still_alert"] += 1
            else:
                alert_flip["still_cleared"] += 1
            band_matrix[c.old_band][c.new_band] += 1
            for d in c.detectors:
                if d.name in detector_contribution:
                    detector_contribution[d.name] += abs(d.delta)

        # Suggested action rolls up the flips into a single verdict.
        # Chosen thresholds match how compliance change-management
        # tends to describe the same numbers to a supervisor.
        action_code, action_label = _suggested_action(
            total,
            alert_flip["cleared_to_alert"],
            alert_flip["alert_to_cleared"],
            by_verdict["material_flip"],
        )

        avg_abs_delta = (
            sum(abs(d) for d in score_deltas) / total if total else 0.0
        )
        max_up = max((d for d in score_deltas), default=0.0)
        max_down = min((d for d in score_deltas), default=0.0)

        return {
            "total_cases": total,
            "by_verdict": by_verdict,
            "alert_flip": alert_flip,
            "band_matrix": band_matrix,
            "detector_contribution": [
                {"name": n, "abs_delta": round(v, 2)}
                for n, v in sorted(
                    detector_contribution.items(),
                    key=lambda kv: kv[1],
                    reverse=True,
                )
            ],
            "avg_abs_score_delta": round(avg_abs_delta, 2),
            "max_score_up": round(max_up, 2),
            "max_score_down": round(max_down, 2),
            "action_code": action_code,
            "action_label": action_label,
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "proposal": self.proposal.to_dict(),
            "generated_at": self.generated_at,
            "rules_version": self.rules_version,
            "engine_version": ENGINE_VERSION,
            "summary": self.summary(),
            "cases": [c.to_dict() for c in self.cases],
        }


# ---------------------------------------------------------------------------
# Curated presets — every one of them is a real regulatory scenario an
# MLRO sees in the wild.  Each preset is deterministic on the fixture
# case store, so a first-run demo shows an interesting waterfall
# without the user having to hand-tune anything.
# ---------------------------------------------------------------------------

PRESETS: List[HorizonProposal] = [
    HorizonProposal(
        name="OFAC uplift",
        summary=(
            "Second Line raised sanctions-hit weight from 20 → 32 after "
            "a controlled Q3 test showed the current gate missed several "
            "SDN-adjacent aliases at the token-set stage."
        ),
        author="mlro",
        weights={"sanctions_hit": 32.0},
    ),
    HorizonProposal(
        name="Structuring hardening",
        summary=(
            "FIU-IND CTR bulletin re-emphasised the ₹40k–₹50k structuring "
            "band.  Bump the detector weight 24 → 34 and drop the band "
            "cutoffs so a strong structuring pattern always lands in the "
            "review queue."
        ),
        author="fiu_advisory",
        weights={"structuring": 34.0},
        band_cutoffs=(25.0, 55.0, 78.0),
    ),
    HorizonProposal(
        name="FATF grey-list refresh",
        summary=(
            "FATF plenary added BY and RU to the grey list and removed "
            "AF.  Recomputes high_risk_geo intensity for every case with "
            "counterparty exposure to those geographies."
        ),
        author="policy_desk",
        jurisdiction_uplift=["PA", "TR"],
        jurisdiction_relief=["AF"],
    ),
    HorizonProposal(
        name="Noise reduction — round-amount off",
        summary=(
            "First-line asked to disable the round_amount detector for a "
            "one-quarter pilot; it fires often on treasury sweeps and "
            "was flagged in the last false-positive review."
        ),
        author="first_line",
        disabled_detectors=["round_amount"],
    ),
    HorizonProposal(
        name="New SDN additions",
        summary=(
            "OFAC published four new SDN entries linked to a Belarusian "
            "military procurement network.  Fold them into the watchlist "
            "and see which cases would now hit the sanctions gate."
        ),
        author="ofac_watch",
        additional_sanctions=[
            SanctionSeed(
                name="Belarusian Transit Holdings",
                aliases=["BTH", "Belarusian Transit"],
                list_name="OFAC-SDN",
                jurisdiction="BY",
                reason="Military procurement network — 2026-07 addition",
            ),
            SanctionSeed(
                name="MIRAX ENERGO",
                aliases=["Mirax", "Mirax Energo AG"],
                list_name="OFAC-SDN",
                jurisdiction="RU",
                reason="Sanctions evasion vehicle — 2026-07 addition",
            ),
            SanctionSeed(
                name="Turnov Capital Partners",
                aliases=["TCP", "Turnov Capital"],
                list_name="OFAC-SDN",
                jurisdiction="RU",
                reason="Sanctioned FI shell — 2026-07 addition",
            ),
            SanctionSeed(
                name="Aliaksei Marozau",
                aliases=["A. Marozau", "Marozau"],
                list_name="OFAC-SDN",
                jurisdiction="BY",
                reason="Sanctioned individual — 2026-07 addition",
            ),
        ],
    ),
    HorizonProposal(
        name="Band recalibration",
        summary=(
            "Analyst-workload review recommended tighter high-band and "
            "critical cutoffs so the queue is triaged more aggressively "
            "before an alert reaches an SLA breach."
        ),
        author="mlro",
        band_cutoffs=(25.0, 55.0, 75.0),
    ),
]


# ---------------------------------------------------------------------------
# Fuzzy-match helper — reuses the sanctions engine's scorer where
# available, falls back to a token-set overlap so the module still runs
# in environments where `sanctions` is stubbed.
# ---------------------------------------------------------------------------

_TOKEN_SPLIT = re.compile(r"[^a-z0-9]+")


def _tokens(s: str) -> Set[str]:
    return {t for t in _TOKEN_SPLIT.split((s or "").lower()) if t}


def _similarity(a: str, b: str) -> float:
    """Cheap-but-honest name similarity in [0, 1].

    Uses `sanctions_engine.score_pair` when it exists (canonical), and
    falls back to a token-set Jaccard blended with substring
    containment when it doesn't.  Determinism is preserved either way.
    """
    if not a or not b:
        return 0.0
    scorer = getattr(sanctions_engine, "score_pair", None)
    if callable(scorer):
        try:
            return float(scorer(a, b))
        except Exception:  # pragma: no cover — fall through to fallback
            pass
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    jacc = len(ta & tb) / max(1, len(ta | tb))
    aa, bb = a.lower(), b.lower()
    contain = 0.0
    if aa in bb or bb in aa:
        contain = min(len(aa), len(bb)) / max(len(aa), len(bb))
    return round(min(1.0, 0.6 * jacc + 0.4 * contain), 4)


# ---------------------------------------------------------------------------
# Replay — the core of the module
# ---------------------------------------------------------------------------


def _intensity_from_factor(factor: Dict[str, Any]) -> float:
    """Recover the underlying intensity for a snapshotted factor."""
    weight = float(factor.get("weight") or 0.0)
    if weight <= INTENSITY_EPSILON:
        return 0.0
    points = float(factor.get("points") or 0.0)
    return points / weight


def _clip_points(points: float) -> float:
    if points < 0.0:
        return 0.0
    if points > MAX_FACTOR_POINTS:
        return MAX_FACTOR_POINTS
    return points


def _band_for(score: float, cutoffs: Tuple[float, float, float]) -> str:
    lo, mid, hi = cutoffs
    if score >= hi:
        return "critical"
    if score >= mid:
        return "high"
    if score >= lo:
        return "medium"
    return "low"


def _iter_snapshot_names(snapshot: Dict[str, Any]) -> List[str]:
    """Every human-readable name Horizon can fuzz-match against.

    Pulls: display_name, subject/counterparty names embedded in factor
    evidence, and the counterparties recorded in the ``edges`` block.
    De-dupes case-insensitively.
    """
    seen: Set[str] = set()
    out: List[str] = []

    def push(raw: Any) -> None:
        if not raw:
            return
        s = str(raw).strip()
        if not s:
            return
        key = s.lower()
        if key in seen:
            return
        seen.add(key)
        out.append(s)

    push(snapshot.get("display_name"))
    push(snapshot.get("account_id"))
    for f in snapshot.get("factors") or []:
        for ev in f.get("evidence") or []:
            if isinstance(ev, dict):
                for k in ("subject_name", "counterparty_name", "name"):
                    push(ev.get(k))
    for e in snapshot.get("edges") or []:
        if isinstance(e, dict):
            push(e.get("to_name"))
            push(e.get("from_name"))
    for h in snapshot.get("sanctions_hits") or []:
        if isinstance(h, dict):
            push(h.get("subject_name"))
    return out


def _iter_snapshot_geos(snapshot: Dict[str, Any]) -> Dict[str, int]:
    """Count evidence rows per ISO alpha-2 country code.

    The high_risk_geo detector records evidence rows of the shape
    ``{"counterparty": ..., "geo": "PA", ...}``.  The engine also
    falls back to the ``edges`` block, since some snapshots have the
    geo on the edge instead of the factor evidence.
    """
    counts: Dict[str, int] = {}

    def push(code: Any) -> None:
        if not code:
            return
        c = str(code).strip().upper()
        if len(c) == 2 and c.isalpha():
            counts[c] = counts.get(c, 0) + 1

    for f in snapshot.get("factors") or []:
        if f.get("name") != "high_risk_geo":
            continue
        for ev in f.get("evidence") or []:
            if isinstance(ev, dict):
                push(ev.get("geo") or ev.get("country"))
    for e in snapshot.get("edges") or []:
        if isinstance(e, dict):
            push(e.get("geo") or e.get("country"))
    return counts


def _replay_case(
    case: Dict[str, Any],
    snapshot: Dict[str, Any],
    proposal: HorizonProposal,
) -> HorizonImpact:
    factors_old: List[Dict[str, Any]] = list(snapshot.get("factors") or [])
    factor_by_name = {str(f.get("name")): f for f in factors_old}

    weights_new = proposal.effective_weights()
    cutoffs = proposal.effective_cutoffs()
    alert_thr = proposal.effective_alert_threshold()
    sanct_thr = proposal.effective_sanctions_threshold()

    # ---- rebuild every detector ------------------------------------------------

    detectors: List[DetectorDelta] = []
    new_points_by_name: Dict[str, float] = {}
    # We handle sanctions + high_risk_geo specially — their intensity
    # can change even without a weight edit.  Every other detector is
    # a straight weight rescale.

    # Sanctions replay — apply new threshold + fold in additional entries.
    fired_sanctions: List[Dict[str, Any]] = []
    dropped_sanctions: List[Dict[str, Any]] = []
    old_sanct_factor = factor_by_name.get("sanctions_hit", {})
    old_sanct_intensity = _intensity_from_factor(old_sanct_factor)
    old_hits = snapshot.get("sanctions_hits") or []
    # Rank surviving hits by similarity so the "peak intensity" (which
    # is what the risk engine uses) matches the highest-scoring hit.
    peak_sim = 0.0
    for h in old_hits:
        sim = float((h or {}).get("similarity") or 0.0)
        if sim >= sanct_thr:
            fired_sanctions.append(h)
            peak_sim = max(peak_sim, sim)
        else:
            dropped_sanctions.append(h)

    # Additional sanctions — fuzz-match every subject / counterparty
    # name captured in the snapshot against every seed alias.
    names = _iter_snapshot_names(snapshot)
    for seed in proposal.additional_sanctions:
        best_alias, best_name, best_sim = "", "", 0.0
        for alias in seed.surface():
            for nm in names:
                sim = _similarity(alias, nm)
                if sim > best_sim:
                    best_sim = sim
                    best_alias, best_name = alias, nm
        if best_sim >= sanct_thr:
            hit = {
                "name": seed.name,
                "list": seed.list_name,
                "jurisdiction": seed.jurisdiction,
                "matched_alias": best_alias,
                "subject_name": best_name,
                "similarity": round(best_sim, 4),
                "reason": seed.reason,
                "source": "proposal",
            }
            fired_sanctions.append(hit)
            peak_sim = max(peak_sim, best_sim)

    # Sanctions intensity uses the peak similarity when we have one; if
    # every old hit was dropped and no new hit came in, the intensity is
    # zero and the factor turns off.  We also floor the intensity by the
    # `NEW_SANCTIONS_INTENSITY_FLOOR` when a proposal-sourced hit fired,
    # so a fresh SDN match materially moves the score.
    new_sanct_intensity = peak_sim
    if any(h.get("source") == "proposal" for h in fired_sanctions):
        new_sanct_intensity = max(
            new_sanct_intensity, NEW_SANCTIONS_INTENSITY_FLOOR
        )
    if not fired_sanctions:
        new_sanct_intensity = 0.0
    new_sanct_points = _clip_points(
        new_sanct_intensity * weights_new.get("sanctions_hit", 0.0)
    )
    new_points_by_name["sanctions_hit"] = new_sanct_points
    detectors.append(
        DetectorDelta(
            name="sanctions_hit",
            old_points=float(old_sanct_factor.get("points") or 0.0),
            new_points=new_sanct_points,
            old_weight=float(old_sanct_factor.get("weight") or 0.0),
            new_weight=weights_new.get("sanctions_hit", 0.0),
            intensity=new_sanct_intensity,
            reason=_sanctions_reason(
                fired_sanctions,
                dropped_sanctions,
                old_sanct_intensity,
                new_sanct_intensity,
                sanct_thr,
                proposal,
            ),
        )
    )

    # Jurisdiction replay — uplift / relief moves the intensity even
    # when the detector weight is unchanged.
    geo_counts = _iter_snapshot_geos(snapshot)
    old_geo_factor = factor_by_name.get("high_risk_geo", {})
    old_geo_intensity = _intensity_from_factor(old_geo_factor)
    new_geo_intensity = old_geo_intensity
    uplift_hits: Dict[str, int] = {}
    relief_hits: Dict[str, int] = {}
    for code in proposal.jurisdiction_uplift:
        c = code.upper()
        n = geo_counts.get(c, 0)
        if n > 0:
            uplift_hits[c] = n
            new_geo_intensity = min(
                1.0, new_geo_intensity + JURISDICTION_UPLIFT * n / max(1, sum(geo_counts.values()))
            )
    for code in proposal.jurisdiction_relief:
        c = code.upper()
        n = geo_counts.get(c, 0)
        if n > 0:
            relief_hits[c] = n
            # Relief scales the intensity down by the same shape — remove
            # this country's proportional share of the current intensity.
            frac = n / max(1, sum(geo_counts.values()))
            new_geo_intensity = max(0.0, new_geo_intensity - old_geo_intensity * frac)
    new_geo_points = _clip_points(
        new_geo_intensity * weights_new.get("high_risk_geo", 0.0)
    )
    new_points_by_name["high_risk_geo"] = new_geo_points
    detectors.append(
        DetectorDelta(
            name="high_risk_geo",
            old_points=float(old_geo_factor.get("points") or 0.0),
            new_points=new_geo_points,
            old_weight=float(old_geo_factor.get("weight") or 0.0),
            new_weight=weights_new.get("high_risk_geo", 0.0),
            intensity=new_geo_intensity,
            reason=_geo_reason(uplift_hits, relief_hits, geo_counts, proposal),
        )
    )

    # Every other detector: intensity preserved, points rescale via new weight.
    for name in risk_engine.DETECTOR_ORDER:
        if name in {"sanctions_hit", "high_risk_geo"}:
            continue
        old_f = factor_by_name.get(name, {})
        intensity = _intensity_from_factor(old_f)
        new_w = weights_new.get(name, 0.0)
        new_pts = _clip_points(intensity * new_w)
        new_points_by_name[name] = new_pts
        detectors.append(
            DetectorDelta(
                name=name,
                old_points=float(old_f.get("points") or 0.0),
                new_points=new_pts,
                old_weight=float(old_f.get("weight") or 0.0),
                new_weight=new_w,
                intensity=intensity,
                reason=_detector_reason(name, old_f, new_w, proposal),
            )
        )

    # ---- roll up ---------------------------------------------------------------

    new_score = min(100.0, sum(new_points_by_name.values()))
    old_score = float(snapshot.get("risk_score") or case.get("risk_score") or 0.0)
    old_band = str(snapshot.get("band") or case.get("band") or "low")
    new_band = _band_for(new_score, cutoffs)
    old_alerted = old_score >= alert_thr
    new_alerted = new_score >= alert_thr
    verdict = _verdict_for(old_score, new_score, old_band, new_band, old_alerted, new_alerted)
    driver_note = _driver_note(detectors, verdict)

    # Preserve detector order — same left-to-right order the /aml page uses.
    detectors.sort(key=lambda d: risk_engine.DETECTOR_ORDER.index(d.name))

    return HorizonImpact(
        case_id=str(case.get("id")),
        account_id=str(case.get("account_id") or snapshot.get("account_id") or ""),
        display_name=str(case.get("display_name") or snapshot.get("display_name") or ""),
        status=str(case.get("status") or "open"),
        priority=str(case.get("priority") or "low"),
        assignee=case.get("assignee"),
        old_score=old_score,
        new_score=new_score,
        old_band=old_band,
        new_band=new_band,
        old_alerted=old_alerted,
        new_alerted=new_alerted,
        verdict=verdict,
        detectors=detectors,
        fired_sanctions=fired_sanctions,
        dropped_sanctions=dropped_sanctions,
        driver_note=driver_note,
    )


# ---------------------------------------------------------------------------
# Reason text — short, factual, plays back to the analyst which lever
# actually moved this factor.  Every branch is one sentence; the UI
# renders these underneath the detector bars.
# ---------------------------------------------------------------------------


def _sanctions_reason(
    fired: List[Dict[str, Any]],
    dropped: List[Dict[str, Any]],
    old_intensity: float,
    new_intensity: float,
    threshold: float,
    proposal: HorizonProposal,
) -> str:
    proposal_hits = [h for h in fired if h.get("source") == "proposal"]
    if proposal_hits:
        names = ", ".join(sorted({h.get("name", "?") for h in proposal_hits}))
        return f"{len(proposal_hits)} proposal SDN entry hit ({names})."
    if dropped and not fired:
        return (
            f"Every prior hit dropped below the new similarity gate "
            f"(≥ {threshold:.2f}); detector goes silent."
        )
    if dropped:
        return (
            f"{len(dropped)} prior hit(s) dropped below the new gate "
            f"(≥ {threshold:.2f}); {len(fired)} remain."
        )
    if abs(new_intensity - old_intensity) < 1e-6:
        return "No change; intensity preserved from the snapshot."
    return f"Intensity re-projected under new weight {proposal.effective_weights()['sanctions_hit']:.1f}."


def _geo_reason(
    uplift: Dict[str, int],
    relief: Dict[str, int],
    geo_counts: Dict[str, int],
    proposal: HorizonProposal,
) -> str:
    if not uplift and not relief:
        # Weight-only change
        base_w = risk_engine.WEIGHTS.get("high_risk_geo", 0.0)
        new_w = proposal.effective_weights().get("high_risk_geo", 0.0)
        if abs(new_w - base_w) < 1e-6:
            return "No jurisdiction change; detector inherits its snapshot intensity."
        return f"Weight moved {base_w:.1f} → {new_w:.1f}; intensity preserved."
    parts: List[str] = []
    if uplift:
        parts.append(
            "uplift " + ", ".join(f"{c} ({n})" for c, n in sorted(uplift.items()))
        )
    if relief:
        parts.append(
            "relief " + ", ".join(f"{c} ({n})" for c, n in sorted(relief.items()))
        )
    return "; ".join(parts) + "."


def _detector_reason(
    name: str,
    old_factor: Dict[str, Any],
    new_weight: float,
    proposal: HorizonProposal,
) -> str:
    old_weight = float(old_factor.get("weight") or 0.0)
    if name in proposal.disabled_detectors:
        return f"Detector disabled by proposal (weight → 0)."
    if abs(new_weight - old_weight) < 1e-6:
        return "Weight unchanged; snapshot intensity preserved."
    if new_weight > old_weight:
        return f"Weight lifted {old_weight:.1f} → {new_weight:.1f}; every prior tick scales up."
    return f"Weight lowered {old_weight:.1f} → {new_weight:.1f}; every prior tick scales down."


def _verdict_for(
    old_score: float,
    new_score: float,
    old_band: str,
    new_band: str,
    old_alerted: bool,
    new_alerted: bool,
) -> str:
    if old_alerted != new_alerted:
        return "material_flip"
    step = abs(BAND_RANK.get(new_band, 0) - BAND_RANK.get(old_band, 0))
    if step >= 2:
        return "material_flip"
    if step == 1:
        return "band_shift"
    if abs(new_score - old_score) >= SCORE_TOUCH_EPS:
        return "touched"
    return "stable"


def _driver_note(detectors: List[DetectorDelta], verdict: str) -> str:
    if verdict == "stable":
        return "No detector moved beyond the touch threshold."
    ranked = sorted(detectors, key=lambda d: abs(d.delta), reverse=True)
    driver = ranked[0]
    if abs(driver.delta) < 1e-6:
        return "No detector contributed; the change came from band re-cutoffs alone."
    direction = "lifted" if driver.delta > 0 else "cut"
    return (
        f"{driver.name} {direction} by {abs(driver.delta):.1f} pts "
        f"(intensity {driver.intensity:.2f})."
    )


def _suggested_action(
    total: int,
    cleared_to_alert: int,
    alert_to_cleared: int,
    material_flips: int,
) -> Tuple[str, str]:
    """Roll the three counts into a change-management verdict.

    Thresholds are intentionally coarse — the point is to give an
    approver a first-look answer, not to replace their judgment.
    """
    if total == 0:
        return ("defer", "Defer — no cases to replay against.")
    flip_share = (cleared_to_alert + alert_to_cleared) / total
    mat_share = material_flips / total
    if cleared_to_alert >= max(3, total // 5):
        return (
            "investigate",
            f"Investigate — {cleared_to_alert} cleared cases would re-fire.",
        )
    if flip_share >= 0.20 or mat_share >= 0.30:
        return (
            "pilot",
            "Pilot — material flips exceed 20% of the backlog; propose staged roll-out.",
        )
    if flip_share <= 0.02 and mat_share <= 0.05:
        return (
            "roll_out",
            "Roll out — impact is confined to a handful of cases; safe to ship.",
        )
    return (
        "pilot",
        "Pilot — moderate impact; ship behind a pilot flag and re-measure at day-14.",
    )


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------


def simulate(
    proposal: HorizonProposal,
    cases: Iterable[Dict[str, Any]],
) -> HorizonReport:
    """Run a proposal against a caller-supplied case list.

    Every case must include a ``snapshot`` dict shaped like the output
    of `risk.AccountReport.to_dict()` — that is what `cases._minimal_
    snapshot` writes into the store.  A case with a missing snapshot is
    silently skipped (returns no impact); the caller can inspect the
    returned length against their input count if that matters.
    """
    impacts: List[HorizonImpact] = []
    for case in cases:
        snapshot = case.get("snapshot") or {}
        if not snapshot.get("factors"):
            continue
        impacts.append(_replay_case(case, snapshot, proposal))
    impacts.sort(key=lambda x: (abs(x.score_delta), x.new_score), reverse=True)
    return HorizonReport(
        proposal=proposal,
        cases=impacts,
        generated_at=datetime.now(timezone.utc).isoformat(),
        rules_version="1.0.0",
    )


def simulate_from_store(
    proposal: HorizonProposal,
    *,
    status: Optional[str] = None,
    include_closed: bool = True,
    limit: int = 400,
) -> HorizonReport:
    """Convenience: pull cases straight from the case store, then simulate."""
    # We need snapshots — list_cases doesn't return them, so we walk the
    # ids and hydrate one at a time.  This is O(N) but N is bounded by
    # the case store size (typically <= a few hundred in a demo).
    lst = case_store.list_cases(
        statuses=("open", "review") if status is None and not include_closed else None,
        status=status,
        include_closed=include_closed,
        limit=limit,
    )
    hydrated: List[Dict[str, Any]] = []
    for row in lst.get("cases") or []:
        cid = row.get("id")
        if not cid:
            continue
        full = case_store.get_case(cid, with_events=False)
        if full:
            hydrated.append(full)
    return simulate(proposal, hydrated)


def explain_case(
    case_id: str,
    proposal: HorizonProposal,
) -> Optional[Dict[str, Any]]:
    """Per-case drill-down: full impact + the snapshot's original factors.

    Returns None if the case isn't in the store; otherwise a dict with
    ``impact`` (the HorizonImpact.to_dict()), ``snapshot`` (the frozen
    account report), and ``proposal`` (the resolved config).
    """
    full = case_store.get_case(case_id, with_events=False)
    if not full:
        return None
    snapshot = full.get("snapshot") or {}
    impact = _replay_case(full, snapshot, proposal)
    return {
        "impact": impact.to_dict(),
        "snapshot": snapshot,
        "proposal": proposal.to_dict(),
    }


# ---------------------------------------------------------------------------
# Auditor-facing config surface
# ---------------------------------------------------------------------------


def get_rules() -> Dict[str, Any]:
    """Everything an approver / auditor needs to review the engine.

    - Current baseline weights + max_weight (from `risk.py`)
    - Default band cutoffs
    - The full preset library so the frontend can render the picker
    - Every tunable constant with its doc string
    """
    return {
        "engine_version": ENGINE_VERSION,
        "baseline_weights": dict(risk_engine.WEIGHTS),
        "max_weight": risk_engine.MAX_WEIGHT,
        "detector_order": list(risk_engine.DETECTOR_ORDER),
        "default_band_cutoffs": list(DEFAULT_BAND_CUTOFFS),
        "default_alert_threshold": DEFAULT_ALERT_THRESHOLD,
        "default_sanctions_threshold": DEFAULT_SANCTIONS_THRESHOLD,
        "new_sanctions_intensity_floor": NEW_SANCTIONS_INTENSITY_FLOOR,
        "jurisdiction_uplift_per_hit": JURISDICTION_UPLIFT,
        "score_touch_epsilon": SCORE_TOUCH_EPS,
        "band_order": list(BAND_ORDER),
        "verdict_ladder": [
            {"code": v, "label": VERDICT_LABEL[v], "accent": VERDICT_ACCENT[v]}
            for v in ("material_flip", "band_shift", "touched", "stable")
        ],
        "presets": [p.to_dict() for p in PRESETS],
    }


# ---------------------------------------------------------------------------
# Fixture generator — the sample surface uses these when the case store
# is empty, so a first-run visitor can still see a meaningful Horizon.
# ---------------------------------------------------------------------------


def _demo_snapshot(
    account_id: str,
    display_name: str,
    factor_intensities: Dict[str, float],
    *,
    sanctions_hits: Optional[List[Dict[str, Any]]] = None,
    geos: Optional[List[str]] = None,
    counterparty_names: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Build a snapshot that behaves as if it were frozen by the risk engine.

    ``factor_intensities`` is a dict of detector → intensity in [0, 1];
    the fixture computes points using the baseline weights so re-runs
    against the baseline proposal come back stable.
    """
    factors = []
    for name in risk_engine.DETECTOR_ORDER:
        intensity = float(factor_intensities.get(name, 0.0))
        weight = float(risk_engine.WEIGHTS.get(name, 0.0))
        points = _clip_points(intensity * weight)
        evidence: List[Dict[str, Any]] = []
        if name == "high_risk_geo":
            for c in (geos or []):
                evidence.append({"geo": c, "counterparty": "cparty-" + c})
        if name == "sanctions_hit":
            for h in sanctions_hits or []:
                evidence.append(dict(h))
        factors.append(
            {
                "name": name,
                "points": round(points, 2),
                "weight": weight,
                "detail": "fixture",
                "evidence": evidence,
            }
        )
    total = sum(f["points"] for f in factors)
    score = min(100.0, total)
    edges = []
    for i, nm in enumerate(counterparty_names or []):
        edges.append(
            {
                "from": account_id,
                "to": f"cparty-{i}",
                "to_name": nm,
                "amount": 90_000.0 + i * 4_000.0,
                "timestamp": "2026-07-14T09:00:00+00:00",
                "channel": "wire",
                "geo": (geos or ["IN"])[i % max(1, len(geos or ["IN"]))],
            }
        )
    return {
        "account_id": account_id,
        "display_name": display_name,
        "risk_score": round(score, 1),
        "band": _band_for(score, DEFAULT_BAND_CUTOFFS),
        "factors": factors,
        "sanctions_hits": sanctions_hits or [],
        "edges": edges,
    }


def demo_cases() -> List[Dict[str, Any]]:
    """Six curated cases across the band spectrum.

    Every case is deterministic and reproducible; the fixture case ids
    are stable strings so the frontend can key off them.
    """
    now = "2026-07-14T09:00:00+00:00"
    fixtures: List[Tuple[Dict[str, Any], Dict[str, Any]]] = [
        (
            {
                "id": "CASE-HZN-001",
                "account_id": "acct-mumbai-01",
                "display_name": "Mumbai Corridor Freight LLP",
                "status": "review",
                "priority": "high",
                "assignee": "meera",
                "risk_score": 71.4,
                "band": "high",
                "opened_at_iso": now,
            },
            _demo_snapshot(
                "acct-mumbai-01",
                "Mumbai Corridor Freight LLP",
                {
                    "structuring": 0.95,
                    "velocity_spike": 0.75,
                    "round_trip": 0.60,
                    "sanctions_hit": 0.0,
                    "adverse_media": 0.30,
                    "fan_in": 0.25,
                    "fan_out": 0.30,
                    "high_risk_geo": 0.55,
                    "round_amount": 0.30,
                },
                geos=["IN", "AE", "PA"],
                counterparty_names=[
                    "Panama Bay Holdings", "MIRAX ENERGO AG", "Local Transport Co"
                ],
            ),
        ),
        (
            {
                "id": "CASE-HZN-002",
                "account_id": "acct-delhi-04",
                "display_name": "Delhi Precious Metals Pvt",
                "status": "open",
                "priority": "critical",
                "assignee": "raj",
                "risk_score": 82.6,
                "band": "critical",
                "opened_at_iso": now,
            },
            _demo_snapshot(
                "acct-delhi-04",
                "Delhi Precious Metals Pvt",
                {
                    "structuring": 0.55,
                    "velocity_spike": 0.85,
                    "round_trip": 0.70,
                    "sanctions_hit": 0.72,
                    "adverse_media": 0.55,
                    "fan_in": 0.35,
                    "fan_out": 0.40,
                    "high_risk_geo": 0.55,
                    "round_amount": 0.30,
                },
                sanctions_hits=[
                    {
                        "name": "Aliaksei Marozau",
                        "list": "OFAC-SDN",
                        "jurisdiction": "BY",
                        "matched_alias": "A. Marozau",
                        "subject_name": "Aliaksei Marozau",
                        "similarity": 0.72,
                    },
                ],
                geos=["BY", "AE"],
                counterparty_names=["A. Marozau", "Belarusian Transit Holdings"],
            ),
        ),
        (
            {
                "id": "CASE-HZN-003",
                "account_id": "acct-cochin-02",
                "display_name": "Cochin Marine Exports",
                "status": "review",
                "priority": "medium",
                "assignee": None,
                "risk_score": 44.2,
                "band": "medium",
                "opened_at_iso": now,
            },
            _demo_snapshot(
                "acct-cochin-02",
                "Cochin Marine Exports",
                {
                    "structuring": 0.20,
                    "velocity_spike": 0.30,
                    "round_trip": 0.10,
                    "sanctions_hit": 0.0,
                    "adverse_media": 0.30,
                    "fan_in": 0.10,
                    "fan_out": 0.10,
                    "high_risk_geo": 0.55,
                    "round_amount": 0.20,
                },
                geos=["TR", "IN", "AE"],
                counterparty_names=["Bosphorus Shipping", "Local Broker"],
            ),
        ),
        (
            {
                "id": "CASE-HZN-004",
                "account_id": "acct-blr-11",
                "display_name": "Bangalore Software Consortium",
                "status": "cleared",
                "priority": "low",
                "assignee": "raj",
                "risk_score": 19.4,
                "band": "low",
                "opened_at_iso": now,
            },
            _demo_snapshot(
                "acct-blr-11",
                "Bangalore Software Consortium",
                {
                    "structuring": 0.10,
                    "velocity_spike": 0.10,
                    "round_trip": 0.05,
                    "sanctions_hit": 0.0,
                    "adverse_media": 0.10,
                    "fan_in": 0.15,
                    "fan_out": 0.15,
                    "high_risk_geo": 0.05,
                    "round_amount": 0.55,
                },
                counterparty_names=["Payroll Vendor", "AWS", "Cloud Vendor"],
            ),
        ),
        (
            {
                "id": "CASE-HZN-005",
                "account_id": "acct-chennai-07",
                "display_name": "Chennai Textiles Export House",
                "status": "review",
                "priority": "high",
                "assignee": "meera",
                "risk_score": 66.8,
                "band": "high",
                "opened_at_iso": now,
            },
            _demo_snapshot(
                "acct-chennai-07",
                "Chennai Textiles Export House",
                {
                    "structuring": 0.90,
                    "velocity_spike": 0.60,
                    "round_trip": 0.35,
                    "sanctions_hit": 0.0,
                    "adverse_media": 0.20,
                    "fan_in": 0.25,
                    "fan_out": 0.30,
                    "high_risk_geo": 0.35,
                    "round_amount": 0.55,
                },
                geos=["IN", "BD", "AE"],
                counterparty_names=["Dhaka Weavers", "Turnov Capital"],
            ),
        ),
        (
            {
                "id": "CASE-HZN-006",
                "account_id": "acct-pune-08",
                "display_name": "Pune Micro-Loans Co-op",
                "status": "cleared",
                "priority": "medium",
                "assignee": "kavya",
                "risk_score": 55.0,
                "band": "medium",
                "opened_at_iso": now,
            },
            _demo_snapshot(
                "acct-pune-08",
                "Pune Micro-Loans Co-op",
                {
                    "structuring": 0.55,
                    "velocity_spike": 0.20,
                    "round_trip": 0.15,
                    "sanctions_hit": 0.0,
                    "adverse_media": 0.25,
                    "fan_in": 0.35,
                    "fan_out": 0.20,
                    "high_risk_geo": 0.15,
                    "round_amount": 0.60,
                },
                geos=["IN", "AF"],
                counterparty_names=["Kabul Remittance Agent", "Local NGO"],
            ),
        ),
    ]
    out: List[Dict[str, Any]] = []
    for case, snap in fixtures:
        case_copy = dict(case)
        case_copy["snapshot"] = snap
        out.append(case_copy)
    return out


def sample_report(preset_name: str = "OFAC uplift") -> Dict[str, Any]:
    """The bundled demo Horizon shown on first-load."""
    preset = next((p for p in PRESETS if p.name == preset_name), PRESETS[0])
    report = simulate(preset, demo_cases())
    payload = report.to_dict()
    payload["cases_source"] = "fixture"
    payload["available_presets"] = [
        {"name": p.name, "summary": p.summary} for p in PRESETS
    ]
    return payload


# ---------------------------------------------------------------------------
# Markdown export — the "impact memo" a Second Line lead pastes into a
# change-management ticket.  Deterministic, no floats-with-trailing-noise.
# ---------------------------------------------------------------------------


def export_markdown(report: HorizonReport) -> str:
    s = report.summary()
    p = report.proposal
    lines: List[str] = []
    lines.append(f"# Horizon impact memo — {p.name}")
    lines.append("")
    lines.append(f"*Author:* {p.author}  ·  *Generated:* {report.generated_at}")
    lines.append("")
    if p.summary:
        lines.append(f"> {p.summary}")
        lines.append("")
    lines.append("## Backlog impact")
    lines.append("")
    lines.append(f"- Cases replayed: **{s['total_cases']}**")
    lines.append(f"- Cleared → Alert: **{s['alert_flip']['cleared_to_alert']}**")
    lines.append(f"- Alert → Cleared: **{s['alert_flip']['alert_to_cleared']}**")
    lines.append(f"- Material flips: **{s['by_verdict']['material_flip']}**")
    lines.append(f"- Band shifts: **{s['by_verdict']['band_shift']}**")
    lines.append(f"- Avg |Δscore|: **{s['avg_abs_score_delta']}**")
    lines.append("")
    lines.append(f"**Suggested action:** {s['action_label']}")
    lines.append("")
    lines.append("## Top detector contribution (|Δ| points, backlog total)")
    lines.append("")
    for row in s["detector_contribution"][:6]:
        lines.append(f"- `{row['name']}`: {row['abs_delta']}")
    lines.append("")
    lines.append("## Notable cases")
    lines.append("")
    top = [c for c in report.cases if c.verdict in {"material_flip", "band_shift"}][:8]
    if not top:
        lines.append("_None — the change is quiet at the case level._")
    for c in top:
        lines.append(
            f"- `{c.case_id}` ({c.display_name}) — "
            f"{c.old_band} → {c.new_band}, "
            f"{c.old_score:.1f} → {c.new_score:.1f} "
            f"({'+' if c.score_delta >= 0 else ''}{c.score_delta:.1f})  \n"
            f"  {c.driver_note}"
        )
    lines.append("")
    lines.append(
        f"_Engine {ENGINE_VERSION}.  Replay is deterministic — "
        f"re-run at any time yields the same numbers._"
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Pydantic-shaped input parser — the FastAPI layer hands us the raw
# request body dict; we normalise it into a HorizonProposal here so
# callers can use whichever shape is convenient.
# ---------------------------------------------------------------------------


def proposal_from_payload(payload: Dict[str, Any]) -> HorizonProposal:
    seeds_raw = payload.get("additional_sanctions") or []
    seeds: List[SanctionSeed] = []
    for row in seeds_raw:
        if not isinstance(row, dict):
            continue
        seeds.append(
            SanctionSeed(
                name=str(row.get("name") or "").strip(),
                aliases=[str(a) for a in (row.get("aliases") or []) if a],
                list_name=str(row.get("list") or row.get("list_name") or "PROPOSED"),
                jurisdiction=str(row.get("jurisdiction") or "").upper(),
                reason=str(row.get("reason") or ""),
            )
        )
    cutoffs_raw = payload.get("band_cutoffs")
    cutoffs: Optional[Tuple[float, float, float]] = None
    if cutoffs_raw and isinstance(cutoffs_raw, (list, tuple)) and len(cutoffs_raw) == 3:
        try:
            cutoffs = (
                float(cutoffs_raw[0]),
                float(cutoffs_raw[1]),
                float(cutoffs_raw[2]),
            )
        except (TypeError, ValueError):
            cutoffs = None
    return HorizonProposal(
        name=str(payload.get("name") or "Untitled proposal"),
        summary=str(payload.get("summary") or ""),
        author=str(payload.get("author") or "compliance"),
        weights={
            k: float(v)
            for k, v in (payload.get("weights") or {}).items()
            if _is_num(v)
        },
        disabled_detectors=[
            str(d) for d in (payload.get("disabled_detectors") or []) if d
        ],
        sanctions_threshold=(
            float(payload["sanctions_threshold"])
            if _is_num(payload.get("sanctions_threshold")) else None
        ),
        additional_sanctions=seeds,
        jurisdiction_uplift=[
            str(c).upper() for c in (payload.get("jurisdiction_uplift") or []) if c
        ],
        jurisdiction_relief=[
            str(c).upper() for c in (payload.get("jurisdiction_relief") or []) if c
        ],
        band_cutoffs=cutoffs,
        alert_threshold=(
            float(payload["alert_threshold"])
            if _is_num(payload.get("alert_threshold")) else None
        ),
    )


def _is_num(x: Any) -> bool:
    if x is None:
        return False
    try:
        float(x)
        return True
    except (TypeError, ValueError):
        return False


__all__ = [
    "ENGINE_VERSION",
    "HorizonProposal",
    "HorizonImpact",
    "HorizonReport",
    "SanctionSeed",
    "PRESETS",
    "simulate",
    "simulate_from_store",
    "explain_case",
    "get_rules",
    "sample_report",
    "demo_cases",
    "proposal_from_payload",
    "export_markdown",
]
