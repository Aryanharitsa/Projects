"""Convoy — Group Travel Consensus Reflow for WaySafe.

The question no other WaySafe surface answers
---------------------------------------------
Odyssey (Day 76) composes a trip *at planning time* for a single implied
traveller.  Nomad (Day 81) reflows what remains of that trip *live* as
signals move.  Both assume the trip is being lived by **one** person
with **one** risk profile.

Every WaySafe user we watched hit the same wall the moment they put
more than one seat in the trip:

  * A family of four — two adults, a 9-year-old, a 68-year-old parent
    with mild angina — plans a 4-day heritage loop.  Nomad wakes them
    on Day 2 with an escalating cluster on Day-3's corridor and
    recommends `TIME_SHIFT` — depart 3 h later, arrive after dark.
    That is a **fine** answer for the adults.  It is a **bad** answer
    for a 68-year-old who takes her heart medication at 21:00 and
    doesn't sit in an unfamiliar hotel foyer after dark, and it is a
    **worse** answer for the 9-year-old whose whole trip crumbles the
    moment his bedtime moves past 22:30.  Nomad's uplift number
    (+4.2 pts) said this was the trip-saving move.  For half the
    convoy it was actively harmful.

  * A tour operator running a 12-person retreat gets a `STOP_DROP`
    recommendation that drops the exact stop three of the twelve
    booked the trip for.  The math is right.  The move is wrong.

  * A friend group gets `REST_DAY` on the day one member has a
    non-refundable ticket.  Nomad had no idea that ticket existed
    because Nomad is a single-actor engine.

The problem is not that Nomad is wrong — Nomad is exactly right *for
the abstract single traveller it models*.  The problem is that
"the traveller" is a fiction the moment two or more people share
an itinerary.  Every real trip has a **convoy**: a set of members,
each with their own risk tolerance, curfew, mobility, and medical
context.  What is a +4.2 pt trip uplift for the mean of the convoy
is a −6 pt personal shortfall for its most vulnerable member.

Convoy is the composition Odyssey and Nomad were both missing.  It
takes:

  1. an Odyssey `TripReport` and a Nomad `NomadReflow` under current
     live signals — the reference plan + the strategy shortlist Nomad
     has already simulated end-to-end;
  2. a **convoy** — an ordered list of `Member`s, each carrying a
     `MemberProfile` (age band, mobility, risk tolerance, curfew hour,
     medical flags);
  3. optional **per-member day locks** (`{member_id: {day_index}}`) —
     days that member cannot afford to give up.  A lock hardens a
     day for that member so no strategy that touches it can pass
     consensus without a veto.

...and emits a `ConvoyReport` with:

  * **Per-member day views** — every upcoming day re-scored under
    each member's personal penalty stack (risk tolerance × risk
    pressure, curfew × arrival hour, mobility × stop density,
    medical × flag count).  The stay's baseline day-score never
    moves; the *personal* score is a downward deflection off it.
  * **Per-member trip composites** — each member gets an Odyssey-shape
    trip composite (`0.60·mean + 0.40·min`) computed against **their**
    day vector.  So we can say "for Aunt Mira this trip is Bumpy at 61,
    even though the convoy mean sits at Solid 74" in a single line.
  * **Strategy ballots** — every Nomad `ReflowStrategy` (including
    `STAY_COURSE`) is re-scored **per member** end-to-end.  Each
    ballot carries: `mean_uplift`, `worst_uplift`, `n_dissent`
    (members whose personal score drops), `n_veto` (vulnerable
    members whose personal score drops by ≥5 pts), and an
    `is_admissible` flag.
  * **Consensus strategy** — the admissible strategy that maximises
    `0.60·mean_uplift + 0.40·worst_uplift`.  When nothing clears the
    consensus floor (`CONSENSUS_FLOOR_PTS = 1.5`) or when every
    non-baseline candidate has ≥1 veto, `STAY_COURSE` wins by
    definition and the report says exactly why.
  * **Dissent matrix** — the (member × strategy) grid of personal
    uplifts, so the tour lead can *see* who each move helps and who
    it hurts.
  * **Personalised advisories** — one card per member, tailored to
    what changed for *that* member under the consensus strategy.
    A member whose personal Day-3 score dropped past their curfew
    hour gets a different line than a member whose Day-4 stop was
    dropped.
  * **Convoy verdict transition** — mean/worst convoy-level bands
    before vs. after the consensus move, in the same visual grammar
    Nomad uses (baseline → live → reflowed).

Pure-stdlib.  Zero new deps.  Deterministic — same inputs → same
output bytes.  Round-trips through `to_dict / to_json / to_markdown`
under the `waysafe.convoy.v1` envelope.

Lives at `tabs[21]` — the tab immediately after Nomad — because
Convoy is what a tour lead or family trip planner opens the moment
Nomad's single-actor recommendation lands and they realise they have
to socialise it across a group before they can act on it.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from odyssey import (
    OdysseyDay, DayReport, TripReport,
    MIN_DAY_WEIGHT, MEAN_DAY_WEIGHT,
    BAND_LADDER, _BAND_RANK,
    _band_for, _compose_day,
)
from nomad import (
    NomadReflow, NomadState, ReflowStrategy,
    SHORTFALL_TRIGGER_PTS,
)


# ============================================================ constants ==

# ---- Personalization weights ---------------------------------------------
# The per-member personal day penalty is a weighted sum of four channels.
# Weights sum to 1.0 by convention; the total penalty is expressed as a
# 0..40 pt downward deflection off the base day score. Cap keeps a
# personal day from collapsing past the CRITICAL floor purely from
# personalization — a fragile day for a vulnerable member should show up
# as Fragile, not Below-Zero.
W_RISK      = 0.35
W_CURFEW    = 0.20
W_MOBILITY  = 0.20
W_MEDICAL   = 0.25
MAX_PERSONAL_PENALTY_PTS = 40.0

# ---- Curfew scaling ----------------------------------------------------
# Every hour a day's estimated arrival slips past a member's curfew adds
# this many penalty points to the curfew channel (capped at 20 raw pts
# before weighting). 4 pts/h matches how Odyssey scales its own
# late-night stay penalty.
CURFEW_PENALTY_PER_HOUR = 4.0
CURFEW_RAW_CAP = 20.0

# ---- Mobility scaling --------------------------------------------------
# Convoy models mobility as {"low": 1.0, "moderate": 0.5, "high": 0.0}.
# The mobility channel is `factor × max(0, n_stops - MOBILITY_FREE_STOPS)
# × MOBILITY_PT_PER_STOP`, capped at 15 raw pts.
MOBILITY_FACTOR = {"low": 1.0, "moderate": 0.5, "high": 0.0}
MOBILITY_FREE_STOPS = 2
MOBILITY_PT_PER_STOP = 3.5
MOBILITY_RAW_CAP = 15.0

# ---- Medical channel ---------------------------------------------------
# Each medical flag adds a fixed penalty. Flags with an amplified score
# ("cardiac", "respiratory") count as 1.4×; "pregnancy" as 1.3×;
# everything else 1.0×.
MEDICAL_PT_PER_FLAG = 5.0
MEDICAL_HEAVY_FLAGS = {"cardiac", "respiratory"}
MEDICAL_MEDIUM_FLAGS = {"pregnancy"}
MEDICAL_RAW_CAP = 20.0

# ---- Vulnerability derivation ------------------------------------------
# Vulnerability V(m) ∈ [0, 0.85] is a derived scalar that drives the
# veto rule and the advisory-priority ordering. Higher V = more
# protection.
VULN_BASE = 0.0
VULN_PER_MEDICAL_FLAG = 0.20
VULN_SENIOR = 0.15
VULN_CHILD  = 0.10
VULN_LOW_MOBILITY = 0.10
VULN_LOW_RISK_TOLERANCE = 0.10   # applied when risk_tolerance <= 0.35
VULN_CAP = 0.85

# ---- Consensus rule ----------------------------------------------------
# A strategy needs to beat STAY_COURSE by this many convoy-uplift points
# to win consensus. Below this floor the recommendation stays at
# STAY_COURSE regardless of how many strategies were simulated.
CONSENSUS_FLOOR_PTS = 1.5

# Dissent tolerance: a strategy is admissible only if the count of
# members whose personal score DROPS under it is <= ceil(N / DISSENT_DIV).
# N = 6 → tolerated dissent = 2; N = 3 → tolerated dissent = 1.
DISSENT_DIV = 3

# Vulnerable-member veto: a member with V(m) >= VETO_VULN_FLOOR whose
# personal score falls by more than VETO_DROP_PTS under a strategy vetoes
# it. Vetoed strategies cannot become consensus regardless of mean
# uplift.
VETO_VULN_FLOOR = 0.35
VETO_DROP_PTS = 5.0

# Personal-score-drop threshold that counts as "dissent" (regardless of
# vulnerability). Anything smaller is noise around the strategy's own
# stochasticity budget.
DISSENT_DROP_PTS = 1.0

# Personal trip aggregate: same shape as Odyssey (`0.60·mean + 0.40·min`).
PERSONAL_MEAN_WEIGHT = MEAN_DAY_WEIGHT
PERSONAL_MIN_WEIGHT  = MIN_DAY_WEIGHT

# ---- Version ------------------------------------------------------------
VERSION = "waysafe.convoy.v1"
ENGINE_VERSION = "1.0.0"


# ============================================================== types ===

_AGE_BANDS = ("child", "teen", "adult", "senior")
_MOBILITY = ("low", "moderate", "high")
_KNOWN_MEDICAL = {
    "cardiac", "respiratory", "pregnancy", "diabetes",
    "mobility_aid", "medication", "cold_sensitivity", "allergy",
}


@dataclass(frozen=True)
class MemberProfile:
    """The individual risk stack for one convoy member.

    - `age_band` — coarse label. Drives the vulnerability derivation and
      the wording of member advisories ("nine-year-old" reads better
      than "member Rohit"), nothing else.
    - `mobility` — 3-level mobility floor. Feeds the mobility penalty
      channel. Wheelchair / walker riders should use "low".
    - `risk_tolerance ∈ [0, 1]` — 1.0 means "I've done solo overland
      travel through five countries this year, worst-case is fine"; 0.0
      means "I have never travelled without an itinerary". Feeds the
      risk-pressure channel: a low-tolerance member penalises risky
      days harder than a high-tolerance one.
    - `curfew_hour ∈ [17, 26]` — the wall-clock hour after which arriving
      at the stay costs personal score. 26 = "no curfew". A senior on
      21:00 medication sets curfew_hour=21; a nine-year-old on a
      22:30 bedtime sets curfew_hour=22 (integer floor is fine —
      partial hours smear through the CURFEW_PENALTY_PER_HOUR scale).
    - `medical_flags` — any subset of the known flag set. Unknown
      strings are silently kept but do not amplify.
    - `locked_day_indices` — day indices this member cannot afford to
      have altered (booked non-refundable, medical appointment,
      once-in-a-lifetime stop). Any strategy that drops or substitutes
      a stop on a locked day is not admissible for that member.
    """
    age_band: str = "adult"
    mobility: str = "high"
    risk_tolerance: float = 0.6
    curfew_hour: int = 24
    medical_flags: Tuple[str, ...] = ()
    locked_day_indices: Tuple[int, ...] = ()


@dataclass(frozen=True)
class Member:
    """A convoy member — a stable id + a display name + a profile."""
    id: str
    name: str
    profile: MemberProfile


@dataclass(frozen=True)
class Convoy:
    """The convoy on this trip. Members are ordered — the first member
    is treated as the *trip lead* for advisory phrasing only; consensus
    itself is symmetric across the convoy."""
    id: str
    name: str
    members: Tuple[Member, ...]


@dataclass
class MemberDayView:
    """One member's personal view of one day.

    `base_score` is the day's Odyssey/Nomad-composed score (unchanged
    across members). `personal_score` is that score deflected downward
    by the four penalty channels. `channels` decomposes the penalty for
    the UI ("this day cost Aunt Mira 6 pts on curfew and 4 pts on
    medical"). `arrival_hour_est` is the estimated wall-clock hour the
    day's transit lands the traveller back at the stay — used both for
    the curfew channel and the personalised advisory."""
    member_id: str
    day_index: int
    day_label: str
    base_score: int
    personal_score: int
    personal_band: str
    channels: Tuple[Tuple[str, float], ...]
    arrival_hour_est: float
    locked: bool


@dataclass
class PersonalTripReport:
    """One member's personal aggregate across a day-score vector."""
    member_id: str
    day_scores: Tuple[int, ...]
    trip_score: int
    trip_band: str
    mean_day: float
    min_day: int
    worst_day_index: int
    reason: str


@dataclass
class MemberVote:
    """One member's vote on one strategy — signed personal uplift vs
    STAY_COURSE, plus the dissent / veto verdicts."""
    member_id: str
    personal_score_baseline: int      # under STAY_COURSE
    personal_score_strategy: int      # under this strategy
    uplift: float                     # signed personal delta
    is_dissent: bool                  # uplift <= -DISSENT_DROP_PTS
    is_veto: bool                     # vulnerable member with heavy drop
    reason: str                       # one-line "why this vote"


@dataclass
class StrategyBallot:
    """A full ballot for one Nomad strategy across the convoy."""
    strategy_kind: str
    strategy_day_index: int
    strategy_label: str
    strategy_detail: str
    votes: Tuple[MemberVote, ...]
    mean_uplift: float
    worst_uplift: float
    n_dissent: int
    n_veto: int
    dissent_tolerance: int            # ceil(N / DISSENT_DIV)
    is_admissible: bool
    consensus_uplift: float           # 0.60·mean + 0.40·worst
    rank_hint: str                    # "consensus" | "dissent" | "veto" | "baseline"


@dataclass
class ConvoyReport:
    """The full convoy composition on top of a Nomad reflow."""
    convoy: Convoy
    now: datetime
    baseline_trip_score: int          # Odyssey / Nomad live baseline
    baseline_verdict: str
    # Per-member state under STAY_COURSE:
    member_day_views: Tuple[Tuple[MemberDayView, ...], ...]   # [member][day]
    member_personal_baselines: Tuple[PersonalTripReport, ...]
    convoy_mean_personal_baseline: float
    convoy_worst_personal_baseline: int
    convoy_baseline_band: str
    # Ballots across every ReflowStrategy in the Nomad reflow:
    ballots: Tuple[StrategyBallot, ...]
    consensus_ballot: StrategyBallot
    consensus_delta_mean: float       # convoy mean uplift under consensus
    consensus_delta_worst: float      # worst-member uplift under consensus
    consensus_final_mean: float       # mean personal trip score after consensus
    consensus_final_worst: int        # min personal trip score after consensus
    consensus_final_band: str
    # Dissent matrix in one flat structure the UI can eat directly:
    dissent_matrix: Tuple[Tuple[Any, ...], ...]  # rows aligned with ballots
    per_member_advisories: Tuple[Tuple[str, Tuple[str, ...]], ...]
    convoy_summary_lines: Tuple[str, ...]
    engine_version: str = ENGINE_VERSION


# ============================================================ helpers ===

def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _stable_seed(convoy: Convoy, kind: str) -> int:
    """Deterministic small int derived from the convoy id + a role tag.
    Used only where a stable tie-breaker across ties matters (so the
    same input bytes → same output bytes)."""
    src = f"{convoy.id}::{kind}".encode("utf-8", errors="ignore")
    return int(hashlib.sha256(src).hexdigest()[:8], 16)


def _vulnerability(m: MemberProfile) -> float:
    """Derive V(m) ∈ [0, VULN_CAP] from the profile.  Pure function of
    the profile — no randomness, no memoisation."""
    v = VULN_BASE
    v += len(m.medical_flags) * VULN_PER_MEDICAL_FLAG
    if m.age_band == "senior":
        v += VULN_SENIOR
    elif m.age_band == "child":
        v += VULN_CHILD
    if m.mobility == "low":
        v += VULN_LOW_MOBILITY
    if m.risk_tolerance <= 0.35:
        v += VULN_LOW_RISK_TOLERANCE
    return _clamp(v, 0.0, VULN_CAP)


# ================================================= personalization ==

def _arrival_hour_estimate(day: OdysseyDay, dr: DayReport) -> float:
    """Estimate the wall-clock hour the day's transit + stops land the
    traveller back at the stay. Odyssey does not persist this directly;
    we back it out from depart_hour + total_eta_min (transit only) plus
    sum(stop dwell_min). Cap at 27.5 (i.e. 03:30 next morning) so a
    pathological long-form day doesn't dwarf the curfew scale.
    """
    total_dwell_hr = sum(s.dwell_min for s in day.stops) / 60.0
    transit_hr = dr.total_eta_min / 60.0
    arrival = float(day.depart_hour) + transit_hr + total_dwell_hr
    return min(27.5, arrival)


def _risk_pressure(base_score: int) -> float:
    """0..100 measure of how much stress this day puts on a risk-averse
    member. Same shape Odyssey uses for its own risk bar (higher =
    more stress)."""
    return _clamp(100.0 - base_score, 0.0, 100.0)


def _channel_risk(profile: MemberProfile, base_score: int) -> float:
    """Risk-pressure channel: (1 - risk_tolerance) × risk_pressure(d),
    normalised to a max of 30 raw pts (so a 0-tolerance member on a
    0-score day peaks the channel at 30)."""
    pressure = _risk_pressure(base_score)
    raw = (1.0 - _clamp(profile.risk_tolerance, 0.0, 1.0)) * pressure * 0.30
    return _clamp(raw, 0.0, 30.0)


def _channel_curfew(profile: MemberProfile, arrival_hour: float) -> float:
    """Curfew channel: hours past curfew × CURFEW_PENALTY_PER_HOUR."""
    if profile.curfew_hour >= 26:
        return 0.0
    over = max(0.0, arrival_hour - float(profile.curfew_hour))
    raw = over * CURFEW_PENALTY_PER_HOUR
    return _clamp(raw, 0.0, CURFEW_RAW_CAP)


def _channel_mobility(profile: MemberProfile, n_stops: int) -> float:
    """Mobility channel: MOBILITY_FACTOR × excess stops × pt-per-stop."""
    factor = MOBILITY_FACTOR.get(profile.mobility, 0.0)
    excess = max(0, n_stops - MOBILITY_FREE_STOPS)
    raw = factor * excess * MOBILITY_PT_PER_STOP
    return _clamp(raw, 0.0, MOBILITY_RAW_CAP)


def _channel_medical(profile: MemberProfile) -> float:
    """Medical channel: fixed pts per flag with heavy/medium amplifiers."""
    if not profile.medical_flags:
        return 0.0
    total = 0.0
    for flag in profile.medical_flags:
        f = str(flag).lower()
        if f in MEDICAL_HEAVY_FLAGS:
            total += MEDICAL_PT_PER_FLAG * 1.4
        elif f in MEDICAL_MEDIUM_FLAGS:
            total += MEDICAL_PT_PER_FLAG * 1.3
        else:
            total += MEDICAL_PT_PER_FLAG
    return _clamp(total, 0.0, MEDICAL_RAW_CAP)


def _personal_day_score(
    member: Member,
    day: OdysseyDay,
    dr: DayReport,
) -> Tuple[int, Tuple[Tuple[str, float], ...], float]:
    """Return (personal_score, channels, arrival_hour_est).

    channels is a tuple of (channel_name, penalty_pts_after_weight)
    — one entry per active channel, dropped for zero-cost channels so
    the UI can render only what matters. Total penalty is capped at
    MAX_PERSONAL_PENALTY_PTS so a Bumpy day never collapses below the
    Critical floor purely from personalization."""
    p = member.profile
    arrival = _arrival_hour_estimate(day, dr)
    n_stops = len(day.stops)

    raw_risk     = _channel_risk(p, dr.day_score)
    raw_curfew   = _channel_curfew(p, arrival)
    raw_mobility = _channel_mobility(p, n_stops)
    raw_medical  = _channel_medical(p)

    wtd_risk     = raw_risk     * W_RISK
    wtd_curfew   = raw_curfew   * W_CURFEW
    wtd_mobility = raw_mobility * W_MOBILITY
    wtd_medical  = raw_medical  * W_MEDICAL

    total = wtd_risk + wtd_curfew + wtd_mobility + wtd_medical
    total = _clamp(total, 0.0, MAX_PERSONAL_PENALTY_PTS)

    personal = int(round(_clamp(dr.day_score - total, 0.0, 100.0)))

    channels: List[Tuple[str, float]] = []
    if wtd_risk >= 0.5:
        channels.append(("risk", round(wtd_risk, 2)))
    if wtd_curfew >= 0.5:
        channels.append(("curfew", round(wtd_curfew, 2)))
    if wtd_mobility >= 0.5:
        channels.append(("mobility", round(wtd_mobility, 2)))
    if wtd_medical >= 0.5:
        channels.append(("medical", round(wtd_medical, 2)))
    return personal, tuple(channels), arrival


# ================================================== personal trip agg ==

def _personal_composite(day_scores: Sequence[int]) -> int:
    """Odyssey's `0.60·mean + 0.40·min` composite, rounded and
    clamped 0..100. Duplicated locally to avoid importing nomad's
    private helper."""
    if not day_scores:
        return 0
    m = sum(day_scores) / len(day_scores)
    lo = min(day_scores)
    raw = PERSONAL_MEAN_WEIGHT * m + PERSONAL_MIN_WEIGHT * lo
    return max(0, min(100, int(round(raw))))


def _personal_trip_report(
    member: Member,
    day_scores: Sequence[int],
    day_labels: Sequence[str],
) -> PersonalTripReport:
    """Compose the personal trip aggregate for one member."""
    scores = tuple(int(s) for s in day_scores)
    if not scores:
        return PersonalTripReport(
            member_id=member.id, day_scores=tuple(),
            trip_score=0, trip_band="empty",
            mean_day=0.0, min_day=0, worst_day_index=-1,
            reason="empty trip",
        )
    ts = _personal_composite(scores)
    band, _hue = _band_for(ts)
    mean_day = sum(scores) / len(scores)
    min_day = min(scores)
    worst_idx = scores.index(min_day)
    worst_label = day_labels[worst_idx] if worst_idx < len(day_labels) else f"Day {worst_idx+1}"
    reason = (
        f"Personal composite {ts} ({band}); mean {mean_day:.0f}, worst {min_day} "
        f"on {worst_label}."
    )
    return PersonalTripReport(
        member_id=member.id, day_scores=scores,
        trip_score=ts, trip_band=band,
        mean_day=round(mean_day, 2), min_day=min_day,
        worst_day_index=worst_idx, reason=reason,
    )


# =========================================== strategy simulation ==

def _remaining_day_reports(
    trip: TripReport,
    reflow: NomadReflow,
) -> Tuple[List[DayReport], List[int], List[str], List[OdysseyDay]]:
    """Return the ordered (day_report, day_score, day_label, odyssey_day)
    quads used to build a member's day view under STAY_COURSE — i.e.
    live reports for upcoming days, baseline reports for the frozen past.
    """
    live_by_idx = {ld.day_index: ld for ld in reflow.live_days}
    day_reports: List[DayReport] = []
    scores: List[int] = []
    labels: List[str] = []
    odyssey_days: List[OdysseyDay] = []
    for i, baseline in enumerate(trip.days):
        if i in live_by_idx:
            day_reports.append(live_by_idx[i].live_report)
            scores.append(live_by_idx[i].live_score)
            labels.append(live_by_idx[i].day_label)
            odyssey_days.append(baseline.day)
        else:
            day_reports.append(baseline)
            scores.append(baseline.day_score)
            labels.append(baseline.day.label)
            odyssey_days.append(baseline.day)
    return day_reports, scores, labels, odyssey_days


def _simulate_strategy_day_scores(
    strategy: ReflowStrategy,
    trip: TripReport,
    reflow: NomadReflow,
    incidents: Sequence[Mapping],
    geofences: Mapping,
    pois: Sequence[Mapping],
) -> Tuple[List[int], List[OdysseyDay], List[DayReport], List[str]]:
    """Compose the modified remaining plan against live signals and
    return the full trip day-score vector under this strategy.  Days
    the strategy did not touch (i.e. before `state.current_day_idx`,
    or beyond the strategy's own reach) fall back to their live/baseline
    reports.

    Strategies published by nomad.compose_nomad_reflow carry the
    `modified_days` tuple — the ordered upcoming plan under that
    strategy.  We overlay them onto the frozen past days.
    """
    state = reflow.state
    first_upcoming = int(state.current_day_idx)
    n_days = len(trip.days)
    modified = list(strategy.modified_days)

    day_reports: List[DayReport] = []
    scores: List[int] = []
    labels: List[str] = []
    odyssey_days: List[OdysseyDay] = []

    # Past days: keep the frozen baseline.
    for i in range(first_upcoming):
        baseline = trip.days[i]
        day_reports.append(baseline)
        scores.append(baseline.day_score)
        labels.append(baseline.day.label)
        odyssey_days.append(baseline.day)

    if not modified:
        # SHORTEN with cutoff before first_upcoming — no upcoming days
        # left. Trip effectively ends here for scoring purposes.
        return scores, odyssey_days, day_reports, labels

    # Upcoming days: score each modified OdysseyDay end-to-end.
    for md in modified:
        dr = _compose_day(md, list(incidents), geofences or {"features": []}, list(pois))
        day_reports.append(dr)
        scores.append(dr.day_score)
        labels.append(md.label)
        odyssey_days.append(md)

    # Some strategies (SHORTEN) may return fewer modified days than the
    # remaining count. That's a valid outcome — the trip actually got
    # shorter — and downstream aggregators simply see fewer entries.
    return scores, odyssey_days, day_reports, labels


def _member_scores_over_plan(
    member: Member,
    odyssey_days: Sequence[OdysseyDay],
    day_reports: Sequence[DayReport],
) -> List[int]:
    """Return one member's per-day personal scores across a plan
    (odyssey_days aligned with day_reports)."""
    out: List[int] = []
    for od, dr in zip(odyssey_days, day_reports):
        personal, _channels, _arrival = _personal_day_score(member, od, dr)
        out.append(personal)
    return out


# =========================================== per-member day views ==

def _build_member_day_views(
    convoy: Convoy,
    odyssey_days: Sequence[OdysseyDay],
    day_reports: Sequence[DayReport],
    day_labels: Sequence[str],
) -> Tuple[Tuple[MemberDayView, ...], ...]:
    """For every (member, day) pair, compose a MemberDayView. Used only
    for the STAY_COURSE reference — the ballot pass computes per-strategy
    personal scores in-place without materialising all-day views.
    """
    per_member: List[Tuple[MemberDayView, ...]] = []
    for m in convoy.members:
        views: List[MemberDayView] = []
        for i, (od, dr) in enumerate(zip(odyssey_days, day_reports)):
            personal, channels, arrival = _personal_day_score(m, od, dr)
            band, _hue = _band_for(personal)
            locked = i in set(m.profile.locked_day_indices)
            views.append(MemberDayView(
                member_id=m.id, day_index=i,
                day_label=day_labels[i] if i < len(day_labels) else f"Day {i+1}",
                base_score=dr.day_score,
                personal_score=personal,
                personal_band=band,
                channels=channels,
                arrival_hour_est=round(arrival, 2),
                locked=locked,
            ))
        per_member.append(tuple(views))
    return tuple(per_member)


# ================================================ ballot voting ==

def _vote_reason(
    baseline: int, strategy: int, is_veto: bool, is_dissent: bool,
) -> str:
    """One-line "why this vote"."""
    delta = strategy - baseline
    if is_veto:
        return f"veto — personal −{abs(delta):.0f} on {baseline}→{strategy}"
    if is_dissent:
        return f"dissent — personal {delta:+d} ({baseline}→{strategy})"
    if delta >= 1:
        return f"supports — personal {delta:+d} ({baseline}→{strategy})"
    return f"holds — personal {delta:+d} ({baseline}→{strategy})"


def _ballot_for_strategy(
    strategy: ReflowStrategy,
    convoy: Convoy,
    per_member_baseline_scores: Sequence[int],
    strategy_odyssey_days: Sequence[OdysseyDay],
    strategy_day_reports: Sequence[DayReport],
    n_frozen_past_days: int,
    trip: TripReport,
) -> StrategyBallot:
    """Compose one ballot.

    `per_member_baseline_scores` is aligned with `convoy.members`: the
    personal_trip_score each member gets under STAY_COURSE.

    We rebuild each member's personal trip vector under `strategy` by
    running `_member_scores_over_plan` against the strategy's
    `modified_days` overlaid on the frozen past.
    """
    votes: List[MemberVote] = []
    n_dissent = 0
    n_veto = 0

    for m, base_ts in zip(convoy.members, per_member_baseline_scores):
        # Locked days that were touched by this strategy trigger an
        # automatic veto for the locked member.
        touches_locked = False
        touched_day_idx = strategy.day_index
        locked_set = set(m.profile.locked_day_indices)
        if touched_day_idx is not None and touched_day_idx >= 0:
            if touched_day_idx in locked_set:
                touches_locked = True
        if strategy.kind == "SHORTEN":
            for li in locked_set:
                if li >= (n_frozen_past_days + len(strategy_odyssey_days)):
                    touches_locked = True
                    break

        member_scores = _member_scores_over_plan(
            m, strategy_odyssey_days, strategy_day_reports,
        )
        # `member_scores` covers frozen past + modified upcoming already.
        strat_ts = _personal_composite(member_scores)
        uplift = float(strat_ts - base_ts)

        vulnerability = _vulnerability(m.profile)
        # Baseline STAY_COURSE never carries a veto (it *is* the baseline).
        if strategy.kind == "STAY_COURSE":
            is_veto = False
            is_dissent = False
        else:
            is_veto = (
                touches_locked
                or (vulnerability >= VETO_VULN_FLOOR and uplift <= -VETO_DROP_PTS)
            )
            is_dissent = uplift <= -DISSENT_DROP_PTS

        if is_dissent:
            n_dissent += 1
        if is_veto:
            n_veto += 1

        votes.append(MemberVote(
            member_id=m.id,
            personal_score_baseline=int(base_ts),
            personal_score_strategy=int(strat_ts),
            uplift=round(uplift, 2),
            is_dissent=is_dissent,
            is_veto=is_veto,
            reason=_vote_reason(int(base_ts), int(strat_ts), is_veto, is_dissent),
        ))

    n_members = max(1, len(convoy.members))
    dissent_tolerance = math.ceil(n_members / DISSENT_DIV)
    mean_uplift = sum(v.uplift for v in votes) / len(votes) if votes else 0.0
    worst_uplift = min((v.uplift for v in votes), default=0.0)
    consensus_uplift = (
        PERSONAL_MEAN_WEIGHT * mean_uplift + PERSONAL_MIN_WEIGHT * worst_uplift
    )
    is_admissible = (n_veto == 0) and (n_dissent <= dissent_tolerance)

    if strategy.kind == "STAY_COURSE":
        rank_hint = "baseline"
    elif n_veto > 0:
        rank_hint = "veto"
    elif not is_admissible:
        rank_hint = "dissent"
    else:
        rank_hint = "consensus"

    return StrategyBallot(
        strategy_kind=strategy.kind,
        strategy_day_index=strategy.day_index,
        strategy_label=strategy.label,
        strategy_detail=strategy.detail,
        votes=tuple(votes),
        mean_uplift=round(mean_uplift, 2),
        worst_uplift=round(worst_uplift, 2),
        n_dissent=n_dissent,
        n_veto=n_veto,
        dissent_tolerance=dissent_tolerance,
        is_admissible=is_admissible,
        consensus_uplift=round(consensus_uplift, 2),
        rank_hint=rank_hint,
    )


def _pick_consensus(ballots: Sequence[StrategyBallot]) -> StrategyBallot:
    """Pick the winner ballot.

    Rules:
      1. If any non-STAY_COURSE ballot is admissible AND
         consensus_uplift >= CONSENSUS_FLOOR_PTS, pick the one with
         the highest consensus_uplift.  Ties: kind alphabetical then
         day_index ascending — deterministic.
      2. Otherwise STAY_COURSE wins by definition.
    """
    stay_course = next(
        (b for b in ballots if b.strategy_kind == "STAY_COURSE"),
        None,
    )
    # Fall-through guardrail: if there is no STAY_COURSE ballot at all
    # (which should never happen because nomad always includes it),
    # fabricate a neutral one from the first ballot so the report is
    # still shape-valid.
    if stay_course is None:
        return ballots[0]

    candidates = [
        b for b in ballots
        if b.strategy_kind != "STAY_COURSE"
        and b.is_admissible
        and b.consensus_uplift >= CONSENSUS_FLOOR_PTS
    ]
    if not candidates:
        return stay_course
    candidates.sort(
        key=lambda b: (-b.consensus_uplift, b.strategy_kind, b.strategy_day_index)
    )
    return candidates[0]


# =========================================== per-member advisories ==

def _member_advisory(
    member: Member,
    baseline_view: Sequence[MemberDayView],
    baseline_personal: PersonalTripReport,
    consensus_ballot: StrategyBallot,
) -> Tuple[str, ...]:
    """Compose 1..3 short advisory lines tailored to `member` under the
    convoy's consensus decision. Priority order:

      1. Veto or dissent under consensus → explain what personally
         landed worse and offer an operational move.
      2. Consensus strategy is STAY_COURSE and the member's personal
         trip is Fragile/Critical → explain the worst personal day.
      3. Any personal day is Bumpy+ under STAY_COURSE → soft advisory
         for the worst day channel (curfew, medical, mobility).
      4. Otherwise → "held at Solid / no personalised action needed".
    """
    vote = next(
        (v for v in consensus_ballot.votes if v.member_id == member.id),
        None,
    )
    lines: List[str] = []

    if vote is not None and vote.is_veto:
        lines.append(
            f"⛔ {member.name} vetoed the consensus move "
            f"({consensus_ballot.strategy_kind}) — personal Δ {vote.uplift:+.0f} pts. "
            f"Fall back to STAY_COURSE for this member, or resolve the lock/veto "
            f"before adopting the move."
        )
    elif vote is not None and vote.is_dissent:
        lines.append(
            f"⚠️ {member.name} dissents on the consensus move — personal Δ "
            f"{vote.uplift:+.0f} pts. Discuss before adopting or split the day "
            f"so this member holds course while others take the move."
        )

    # Find their worst personal day and describe the dominant channel.
    if baseline_view:
        worst_view = min(baseline_view, key=lambda v: v.personal_score)
        if worst_view.channels:
            dom_ch, dom_pts = max(worst_view.channels, key=lambda t: t[1])
            worst_day = worst_view.day_label
            personal_score = worst_view.personal_score
            if dom_ch == "curfew":
                lines.append(
                    f"🕘 On {worst_day}, {member.name}'s arrival estimate "
                    f"({worst_view.arrival_hour_est:.1f}h) drifts past their "
                    f"{member.profile.curfew_hour}:00 curfew — personal score "
                    f"{personal_score}. Consider TIME_SHIFT −2 h or a REST_DAY "
                    f"as a personal override."
                )
            elif dom_ch == "medical":
                fl = ", ".join(member.profile.medical_flags) or "medical flag"
                lines.append(
                    f"🩺 {member.name}'s medical stack ({fl}) taxes {worst_day} "
                    f"— personal score {personal_score}. Verify the nearest "
                    f"hospital / pharmacy on the corridor before departing."
                )
            elif dom_ch == "mobility":
                lines.append(
                    f"🦽 {worst_day} carries {len(worst_view.channels)} stops "
                    f"on {member.profile.mobility} mobility — personal score "
                    f"{personal_score}. Drop the least-critical stop for "
                    f"{member.name} even if the convoy holds course."
                )
            elif dom_ch == "risk":
                lines.append(
                    f"🎯 {worst_day} sits above {member.name}'s risk-tolerance "
                    f"threshold (rt={member.profile.risk_tolerance:.2f}) "
                    f"— personal score {personal_score}. Consider a MODE_UPGRADE "
                    f"(cab over walk) on the transit leg."
                )

    if not lines:
        band = baseline_personal.trip_band
        if band in ("Serene", "Solid"):
            lines.append(
                f"✅ {member.name} rides the consensus cleanly — personal trip "
                f"{baseline_personal.trip_score} ({band}); no personalised move needed."
            )
        else:
            lines.append(
                f"🟠 {member.name}'s personal trip sits at {baseline_personal.trip_score} "
                f"({band}). No single channel dominates — carry a soft brief on "
                f"the corridor to the worst upcoming day."
            )
    return tuple(lines[:3])


def _convoy_summary_lines(
    convoy: Convoy,
    personal_baselines: Sequence[PersonalTripReport],
    consensus_ballot: StrategyBallot,
    consensus_final_mean: float,
    consensus_final_worst: int,
    consensus_final_band: str,
    baseline_verdict: str,
) -> Tuple[str, ...]:
    """Compose 3–5 convoy-level rollup lines for the top of the report."""
    lines: List[str] = []
    n = len(convoy.members)
    lines.append(
        f"{n}-member convoy · consensus verdict "
        f"**{consensus_ballot.strategy_kind}** "
        f"({consensus_ballot.consensus_uplift:+.1f} pts convoy-uplift)."
    )
    dissenters = [v for v in consensus_ballot.votes if v.is_dissent]
    vetoers = [v for v in consensus_ballot.votes if v.is_veto]
    if vetoers:
        by_id = {m.id: m.name for m in convoy.members}
        names = ", ".join(by_id.get(v.member_id, v.member_id) for v in vetoers)
        lines.append(f"⛔ **Vetoes**: {names}. The consensus falls back to STAY_COURSE.")
    elif dissenters:
        by_id = {m.id: m.name for m in convoy.members}
        names = ", ".join(by_id.get(v.member_id, v.member_id) for v in dissenters)
        lines.append(f"⚠️ **Dissenters**: {names}. Consensus still passes.")
    else:
        lines.append("✅ No dissenters, no vetoes — the convoy is aligned on the move.")

    worst = min(personal_baselines, key=lambda p: p.trip_score, default=None)
    if worst is not None:
        by_id = {m.id: m.name for m in convoy.members}
        worst_name = by_id.get(worst.member_id, worst.member_id)
        lines.append(
            f"Most-constrained member: **{worst_name}** at personal trip "
            f"{worst.trip_score} ({worst.trip_band})."
        )

    lines.append(
        f"Post-consensus convoy: mean personal **{consensus_final_mean:.0f}**, "
        f"worst-member **{consensus_final_worst}** ({consensus_final_band}) · "
        f"trip baseline verdict was {baseline_verdict}."
    )
    return tuple(lines[:5])


# ============================================== dissent matrix ==

def _build_dissent_matrix(
    convoy: Convoy,
    ballots: Sequence[StrategyBallot],
) -> Tuple[Tuple[Any, ...], ...]:
    """Rows = ballots; columns = (member_id, member_name, uplift,
    is_dissent, is_veto). Returned as tuples for a stable
    JSON-round-trippable shape."""
    by_id_to_name = {m.id: m.name for m in convoy.members}
    rows: List[Tuple[Any, ...]] = []
    for b in ballots:
        row_cells: List[Tuple[Any, ...]] = []
        for v in b.votes:
            row_cells.append((
                v.member_id,
                by_id_to_name.get(v.member_id, v.member_id),
                v.uplift,
                v.is_dissent,
                v.is_veto,
            ))
        rows.append((b.strategy_kind, b.strategy_day_index, tuple(row_cells)))
    return tuple(rows)


# ============================================== entrypoint ==

def compose_convoy_report(
    *,
    convoy: Convoy,
    trip: TripReport,
    reflow: NomadReflow,
    incidents: Iterable[Mapping] | None = None,
    geofences: Optional[Mapping] = None,
    pois: Iterable[Mapping] | None = None,
    now: Optional[datetime] = None,
) -> ConvoyReport:
    """Single entrypoint. Compose the group-consensus report.

    Deterministic — same input bytes → same output bytes.

    Empty-convoy guardrail: a zero-member convoy returns a report with
    an empty ballot vector and a summary line explaining why.
    Zero-day trip guardrail: falls through Nomad's own guardrail.
    """
    inc_list = list(incidents or [])
    poi_list = list(pois or [])
    geo = geofences or {"features": []}
    now = now or datetime.utcnow()

    if not convoy.members:
        stay_course = next(
            (s for s in reflow.strategies if s.kind == "STAY_COURSE"),
            reflow.strategies[0] if reflow.strategies else None,
        )
        empty_ballot = StrategyBallot(
            strategy_kind=(stay_course.kind if stay_course else "STAY_COURSE"),
            strategy_day_index=(stay_course.day_index if stay_course else -1),
            strategy_label=(stay_course.label if stay_course else "empty convoy"),
            strategy_detail="No convoy members — nothing to vote.",
            votes=tuple(),
            mean_uplift=0.0, worst_uplift=0.0,
            n_dissent=0, n_veto=0,
            dissent_tolerance=0,
            is_admissible=True,
            consensus_uplift=0.0,
            rank_hint="baseline",
        )
        return ConvoyReport(
            convoy=convoy, now=now,
            baseline_trip_score=int(reflow.live_trip_score),
            baseline_verdict=str(reflow.live_verdict),
            member_day_views=tuple(),
            member_personal_baselines=tuple(),
            convoy_mean_personal_baseline=0.0,
            convoy_worst_personal_baseline=0,
            convoy_baseline_band="empty",
            ballots=(empty_ballot,),
            consensus_ballot=empty_ballot,
            consensus_delta_mean=0.0, consensus_delta_worst=0.0,
            consensus_final_mean=0.0, consensus_final_worst=0,
            consensus_final_band="empty",
            dissent_matrix=tuple(),
            per_member_advisories=tuple(),
            convoy_summary_lines=(
                "Convoy is empty — add members to get a group consensus.",
            ),
        )

    # ---- Baseline (STAY_COURSE) per-member views + trip aggregates ----
    baseline_reports, baseline_scores, baseline_labels, baseline_odays = (
        _remaining_day_reports(trip, reflow)
    )
    member_views = _build_member_day_views(
        convoy, baseline_odays, baseline_reports, baseline_labels,
    )
    personal_baselines: List[PersonalTripReport] = []
    for m, mviews in zip(convoy.members, member_views):
        m_scores = [v.personal_score for v in mviews]
        personal_baselines.append(
            _personal_trip_report(m, m_scores, baseline_labels)
        )
    per_member_baseline_ts = [p.trip_score for p in personal_baselines]

    convoy_mean_baseline = (
        sum(per_member_baseline_ts) / len(per_member_baseline_ts)
        if per_member_baseline_ts else 0.0
    )
    convoy_worst_baseline = (
        min(per_member_baseline_ts) if per_member_baseline_ts else 0
    )
    convoy_baseline_composite = _personal_composite(per_member_baseline_ts)
    convoy_baseline_band, _hue = _band_for(convoy_baseline_composite)

    # ---- Ballots over every Nomad strategy -----------------------------
    n_frozen_past = int(reflow.state.current_day_idx)
    ballots: List[StrategyBallot] = []
    for strategy in reflow.strategies:
        # Simulate the strategy's full trip day vector, then feed it as
        # the "reports we score against" for every member.
        _s_scores, s_odays, s_reports, _s_labels = _simulate_strategy_day_scores(
            strategy, trip, reflow, inc_list, geo, poi_list,
        )
        ballot = _ballot_for_strategy(
            strategy=strategy,
            convoy=convoy,
            per_member_baseline_scores=per_member_baseline_ts,
            strategy_odyssey_days=s_odays,
            strategy_day_reports=s_reports,
            n_frozen_past_days=n_frozen_past,
            trip=trip,
        )
        ballots.append(ballot)

    # Rank hint uses consensus_uplift desc but keeps STAY_COURSE last
    # among tied ballots.
    ballots_sorted = sorted(
        ballots,
        key=lambda b: (-b.consensus_uplift, b.strategy_kind == "STAY_COURSE",
                       b.strategy_kind, b.strategy_day_index),
    )
    consensus = _pick_consensus(ballots_sorted)

    # ---- Post-consensus final scores ----------------------------------
    # Under the winning ballot, compute the resulting mean/worst personal
    # trip score across the convoy.
    if consensus.votes:
        final_scores = [v.personal_score_strategy for v in consensus.votes]
        consensus_final_mean = sum(final_scores) / len(final_scores)
        consensus_final_worst = min(final_scores)
        consensus_final_composite = _personal_composite(final_scores)
        consensus_final_band, _hue2 = _band_for(consensus_final_composite)
    else:
        consensus_final_mean = 0.0
        consensus_final_worst = 0
        consensus_final_band = "empty"

    consensus_delta_mean = consensus_final_mean - convoy_mean_baseline
    consensus_delta_worst = float(consensus_final_worst - convoy_worst_baseline)

    # ---- Per-member advisories ---------------------------------------
    advisories: List[Tuple[str, Tuple[str, ...]]] = []
    for m, mviews, mbase in zip(convoy.members, member_views, personal_baselines):
        lines = _member_advisory(m, mviews, mbase, consensus)
        advisories.append((m.id, lines))

    # ---- Convoy summary rollup ---------------------------------------
    summary = _convoy_summary_lines(
        convoy, personal_baselines, consensus,
        consensus_final_mean, consensus_final_worst,
        consensus_final_band, str(reflow.baseline_verdict),
    )

    # ---- Dissent matrix ---------------------------------------------
    dissent_matrix = _build_dissent_matrix(convoy, ballots_sorted)

    return ConvoyReport(
        convoy=convoy, now=now,
        baseline_trip_score=int(reflow.baseline_trip_score),
        baseline_verdict=str(reflow.baseline_verdict),
        member_day_views=member_views,
        member_personal_baselines=tuple(personal_baselines),
        convoy_mean_personal_baseline=round(convoy_mean_baseline, 2),
        convoy_worst_personal_baseline=int(convoy_worst_baseline),
        convoy_baseline_band=convoy_baseline_band,
        ballots=tuple(ballots_sorted),
        consensus_ballot=consensus,
        consensus_delta_mean=round(consensus_delta_mean, 2),
        consensus_delta_worst=round(consensus_delta_worst, 2),
        consensus_final_mean=round(consensus_final_mean, 2),
        consensus_final_worst=int(consensus_final_worst),
        consensus_final_band=consensus_final_band,
        dissent_matrix=dissent_matrix,
        per_member_advisories=tuple(advisories),
        convoy_summary_lines=summary,
    )


# ============================================== i/o ==

def _profile_to_dict(p: MemberProfile) -> dict:
    return {
        "age_band": p.age_band,
        "mobility": p.mobility,
        "risk_tolerance": round(float(p.risk_tolerance), 3),
        "curfew_hour": int(p.curfew_hour),
        "medical_flags": list(p.medical_flags),
        "locked_day_indices": list(p.locked_day_indices),
        "vulnerability": round(_vulnerability(p), 3),
    }


def _member_to_dict(m: Member) -> dict:
    return {"id": m.id, "name": m.name, "profile": _profile_to_dict(m.profile)}


def _view_to_dict(v: MemberDayView) -> dict:
    return {
        "member_id": v.member_id,
        "day_index": v.day_index,
        "day_label": v.day_label,
        "base_score": v.base_score,
        "personal_score": v.personal_score,
        "personal_band": v.personal_band,
        "channels": [{"name": n, "weighted_pts": p} for n, p in v.channels],
        "arrival_hour_est": v.arrival_hour_est,
        "locked": v.locked,
    }


def _personal_to_dict(p: PersonalTripReport) -> dict:
    return {
        "member_id": p.member_id,
        "day_scores": list(p.day_scores),
        "trip_score": p.trip_score,
        "trip_band": p.trip_band,
        "mean_day": p.mean_day,
        "min_day": p.min_day,
        "worst_day_index": p.worst_day_index,
        "reason": p.reason,
    }


def _vote_to_dict(v: MemberVote) -> dict:
    return {
        "member_id": v.member_id,
        "personal_score_baseline": v.personal_score_baseline,
        "personal_score_strategy": v.personal_score_strategy,
        "uplift": v.uplift,
        "is_dissent": v.is_dissent,
        "is_veto": v.is_veto,
        "reason": v.reason,
    }


def _ballot_to_dict(b: StrategyBallot) -> dict:
    return {
        "strategy_kind": b.strategy_kind,
        "strategy_day_index": b.strategy_day_index,
        "strategy_label": b.strategy_label,
        "strategy_detail": b.strategy_detail,
        "votes": [_vote_to_dict(v) for v in b.votes],
        "mean_uplift": b.mean_uplift,
        "worst_uplift": b.worst_uplift,
        "consensus_uplift": b.consensus_uplift,
        "n_dissent": b.n_dissent,
        "n_veto": b.n_veto,
        "dissent_tolerance": b.dissent_tolerance,
        "is_admissible": b.is_admissible,
        "rank_hint": b.rank_hint,
    }


def to_dict(report: ConvoyReport) -> dict:
    return {
        "version": VERSION,
        "engine_version": report.engine_version,
        "now": report.now.isoformat(),
        "convoy": {
            "id": report.convoy.id,
            "name": report.convoy.name,
            "members": [_member_to_dict(m) for m in report.convoy.members],
        },
        "baseline": {
            "trip_score": report.baseline_trip_score,
            "verdict": report.baseline_verdict,
        },
        "member_day_views": [
            [_view_to_dict(v) for v in row] for row in report.member_day_views
        ],
        "member_personal_baselines": [
            _personal_to_dict(p) for p in report.member_personal_baselines
        ],
        "convoy_personal_baseline": {
            "mean": report.convoy_mean_personal_baseline,
            "worst": report.convoy_worst_personal_baseline,
            "band": report.convoy_baseline_band,
        },
        "ballots": [_ballot_to_dict(b) for b in report.ballots],
        "consensus": {
            "ballot": _ballot_to_dict(report.consensus_ballot),
            "delta_mean": report.consensus_delta_mean,
            "delta_worst": report.consensus_delta_worst,
            "final_mean": report.consensus_final_mean,
            "final_worst": report.consensus_final_worst,
            "final_band": report.consensus_final_band,
        },
        "dissent_matrix": [
            {
                "strategy_kind": kind, "day_index": di,
                "cells": [
                    {
                        "member_id": mid, "member_name": name,
                        "uplift": up, "is_dissent": ds, "is_veto": vt,
                    }
                    for mid, name, up, ds, vt in cells
                ],
            }
            for kind, di, cells in report.dissent_matrix
        ],
        "per_member_advisories": [
            {"member_id": mid, "lines": list(lines)}
            for mid, lines in report.per_member_advisories
        ],
        "convoy_summary_lines": list(report.convoy_summary_lines),
    }


def to_json(report: ConvoyReport, *, indent: int = 2) -> str:
    return json.dumps(to_dict(report), indent=indent, default=str)


def to_markdown(report: ConvoyReport) -> str:
    """Human-readable Markdown reflow-and-consensus brief."""
    lines: List[str] = []
    lines.append(f"# Convoy consensus — {report.convoy.name}")
    lines.append("")
    lines.append(
        f"_{report.now.isoformat()} · {report.engine_version} · "
        f"{VERSION}_"
    )
    lines.append("")
    for s in report.convoy_summary_lines:
        lines.append(f"- {s}")
    lines.append("")
    lines.append("## Members")
    for m in report.convoy.members:
        v = round(_vulnerability(m.profile), 2)
        flags = ", ".join(m.profile.medical_flags) or "—"
        lines.append(
            f"- **{m.name}** · {m.profile.age_band} · mobility "
            f"{m.profile.mobility} · rt {m.profile.risk_tolerance:.2f} · "
            f"curfew {m.profile.curfew_hour}:00 · flags: {flags} · V={v}"
        )
    lines.append("")
    lines.append("## Personal trip scores under STAY_COURSE")
    for m, p in zip(report.convoy.members, report.member_personal_baselines):
        lines.append(
            f"- **{m.name}**: personal {p.trip_score} ({p.trip_band}) · "
            f"mean {p.mean_day:.0f} · min {p.min_day}"
        )
    lines.append("")
    lines.append("## Ballots")
    for b in report.ballots:
        lines.append(
            f"### {b.strategy_kind} (day {b.strategy_day_index+1})"
            if b.strategy_day_index >= 0 else f"### {b.strategy_kind}"
        )
        lines.append(f"_{b.strategy_label}_ — {b.strategy_detail}")
        lines.append(
            f"- mean uplift {b.mean_uplift:+.1f} · worst uplift {b.worst_uplift:+.1f} "
            f"· consensus uplift **{b.consensus_uplift:+.1f}** "
            f"· dissenters {b.n_dissent}/{b.dissent_tolerance} · vetoes {b.n_veto} "
            f"· {'admissible' if b.is_admissible else 'inadmissible'}"
        )
    lines.append("")
    lines.append(
        f"## Consensus: **{report.consensus_ballot.strategy_kind}** "
        f"({report.consensus_ballot.consensus_uplift:+.1f} pts)"
    )
    lines.append(
        f"- Post-consensus mean personal **{report.consensus_final_mean:.0f}**, "
        f"worst **{report.consensus_final_worst}** ({report.consensus_final_band})"
    )
    lines.append("")
    lines.append("## Personalised advisories")
    id_to_name = {m.id: m.name for m in report.convoy.members}
    for mid, lines_ in report.per_member_advisories:
        lines.append(f"### {id_to_name.get(mid, mid)}")
        for L in lines_:
            lines.append(f"- {L}")
    return "\n".join(lines)


# ============================================== convenience seeds ==

def default_seed_convoy(convoy_id: str = "convoy-default") -> Convoy:
    """Return a 4-member family convoy used when the UI has no prior
    convoy state. Deterministic — every seed identical across runs."""
    return Convoy(
        id=convoy_id,
        name="Family loop — 2 adults + child + senior",
        members=(
            Member(
                id="m1", name="Aarav",
                profile=MemberProfile(
                    age_band="adult", mobility="high",
                    risk_tolerance=0.75, curfew_hour=25,
                    medical_flags=(), locked_day_indices=(),
                ),
            ),
            Member(
                id="m2", name="Priya",
                profile=MemberProfile(
                    age_band="adult", mobility="high",
                    risk_tolerance=0.65, curfew_hour=24,
                    medical_flags=(), locked_day_indices=(),
                ),
            ),
            Member(
                id="m3", name="Rohan (9)",
                profile=MemberProfile(
                    age_band="child", mobility="high",
                    risk_tolerance=0.30, curfew_hour=22,
                    medical_flags=(), locked_day_indices=(),
                ),
            ),
            Member(
                id="m4", name="Aunt Mira",
                profile=MemberProfile(
                    age_band="senior", mobility="moderate",
                    risk_tolerance=0.35, curfew_hour=21,
                    medical_flags=("cardiac", "medication"),
                    locked_day_indices=(),
                ),
            ),
        ),
    )


def members_from_editor_rows(rows: Sequence[Mapping]) -> Tuple[Member, ...]:
    """Convert a list of dicts (as produced by st.data_editor) into a
    tuple of Members. Missing / malformed rows are silently dropped so
    a tour lead editing the roster doesn't blow up the compose call."""
    out: List[Member] = []
    for i, r in enumerate(rows):
        try:
            name = str(r.get("name", "")).strip()
            if not name:
                continue
            mid = str(r.get("id") or f"m{i+1}")
            age_band = str(r.get("age_band", "adult") or "adult").lower()
            mobility = str(r.get("mobility", "high") or "high").lower()
            rt = float(r.get("risk_tolerance", 0.6) or 0.6)
            curfew = int(r.get("curfew_hour", 24) or 24)
            flags_raw = r.get("medical_flags") or ""
            if isinstance(flags_raw, str):
                flags = tuple(
                    f.strip().lower() for f in flags_raw.split(",") if f.strip()
                )
            else:
                flags = tuple(str(f).strip().lower() for f in flags_raw if str(f).strip())
            locked_raw = r.get("locked_day_indices") or ""
            if isinstance(locked_raw, str):
                locked = tuple(
                    int(x.strip()) - 1 for x in locked_raw.split(",")
                    if x.strip().isdigit()
                )
            else:
                locked = tuple(int(x) for x in locked_raw if str(x).isdigit())
            profile = MemberProfile(
                age_band=age_band if age_band in _AGE_BANDS else "adult",
                mobility=mobility if mobility in _MOBILITY else "high",
                risk_tolerance=_clamp(rt, 0.0, 1.0),
                curfew_hour=int(_clamp(curfew, 17, 26)),
                medical_flags=flags,
                locked_day_indices=locked,
            )
            out.append(Member(id=mid, name=name, profile=profile))
        except Exception:
            continue
    return tuple(out)


__all__ = [
    "VERSION", "ENGINE_VERSION",
    "W_RISK", "W_CURFEW", "W_MOBILITY", "W_MEDICAL",
    "MAX_PERSONAL_PENALTY_PTS",
    "CONSENSUS_FLOOR_PTS", "DISSENT_DIV",
    "VETO_VULN_FLOOR", "VETO_DROP_PTS", "DISSENT_DROP_PTS",
    "MemberProfile", "Member", "Convoy",
    "MemberDayView", "PersonalTripReport",
    "MemberVote", "StrategyBallot", "ConvoyReport",
    "compose_convoy_report",
    "to_dict", "to_json", "to_markdown",
    "default_seed_convoy", "members_from_editor_rows",
]
