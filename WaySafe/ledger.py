"""Ledger — Cumulative Equity Rebalance for WaySafe (Day 91).

The loop no other WaySafe surface closes
----------------------------------------
Convoy (Day 86) picks the fairest strategy for **one** decision.  Every
member gets a vote, vulnerable members carry a veto, and the winner is
the admissible strategy that maximises `0.60·mean_uplift +
0.40·worst_uplift` across the convoy — for *today*.

That is exactly right for one reflow.  It is quietly wrong across a
seven-day trip that reflows five times.

The pattern we watched on every real convoy:

  * Day 2 — Convoy picks `TIME_SHIFT` (+3.1 pt mean, −1.2 pt for Aunt
    Mira).  Admissible (no veto).  Mira absorbs the cost.
  * Day 3 — Convoy picks `MODE_UPGRADE` (+2.8 pt mean, −1.4 pt for
    Rohan and −0.9 pt for Mira).  Admissible.  Mira absorbs *again*.
  * Day 4 — Convoy picks `STOP_DROP` (+4.0 pt mean, −0.8 pt for Mira).
    Admissible.  By day-end of Day 4, Mira has been the *only* member
    whose personal-uplift line is red on every single day.  The convoy
    mean has gained +12 pt of trip score across the four days.  Mira
    has personally lost −7 pt.

Nothing on the Convoy surface *notices*.  Each ballot is scored in
isolation.  Convoy's job was to protect against a single crushing move,
and it did that; what Convoy cannot see is the *cumulative* effect of a
chain of individually-admissible-but-personally-negative moves piling
onto the same member.

Ledger closes that loop.

What Ledger does
----------------
Ledger consumes:

  1. A **history** — the chronological list of `LedgerEntry`s (one per
     convoy pick already executed on this trip: day_index,
     picked_strategy_kind, per-member personal uplifts recorded at pick
     time).  When the trip has just started, the history is empty and
     Ledger degrades to a pass-through overlay that endorses today's
     Convoy consensus without change.
  2. Today's `ConvoyReport` — the full ballot vector Convoy produced for
     the current reflow, plus its `consensus_ballot` pick.
  3. The current `Convoy` (member roster + profiles, so vulnerability
     weighting stays coherent across the history).

...and emits a `LedgerReport` with:

  * **Per-member cumulative debt** — a weighted running sum of *negative
    personal uplifts absorbed*.  Recent absorptions weight higher via a
    `W_ABSORPTION_DECAY = 0.85^age_days` recency window; vulnerable
    members' costs are amplified by `(1 + W_VULN_DEBT_MULT × V(m))` so
    a −2 pt day on Aunt Mira counts more than a −2 pt day on Aarav.
    Positive uplift days are recorded as *credit* (debt reduction) so
    a member who eats early-trip cost and gets compensated later trends
    toward zero.
  * **Debt distribution Gini coefficient** — the equity metric.  Gini = 0
    means every member holds the same debt (perfect equity).  Gini → 1
    means one member is holding all of it.  We surface it against a
    `GINI_LEVEL_TARGET = 0.20` threshold: above the target, the group
    is inequitable and Ledger will consider a rebalance override.
  * **Hot-member flags** — any member holding ≥ `DEBT_SHARE_HOT_FLOOR
    = 0.40` of total absorbed debt.  This is the "who's been quietly
    carrying it" signal a tour lead should never have to hand-compute.
  * **Rebalance projections** — every admissible ballot from Convoy is
    projected forward: what does the debt vector look like *after* this
    strategy?  Which candidate produces the lowest post-Gini?  What is
    the consensus_uplift trade compared to Convoy's original pick?
  * **Equity winner** — if any admissible non-baseline ballot both (a)
    reduces Gini by at least `REBALANCE_MIN_GINI_DELTA = 0.05` and (b)
    trades at most `EQUITY_TRADE_FLOOR_PTS = 2.0` pts of consensus
    uplift versus Convoy's original pick, Ledger *overrides* the
    consensus and returns the equity winner as the recommended pick.
    Otherwise Ledger returns Convoy's original consensus with a
    `rebalance_applied = False` flag and a plain-English reason ("debt
    already fair" / "no candidate cleared the equity trade floor" /
    "history too short — no rebalance signal yet").
  * **Per-member advisories** — tailored to each member's *cumulative*
    position, not their single-day position.  A member with a hot-flag
    gets a "your seat has absorbed 3 of the last 4 negative-uplift days
    — today's move is picked to lean toward you" line, and gets an
    action recommendation.  A member trending net-positive gets a "your
    seat has been the beneficiary; today's move continues to favour
    you, keep an eye on Rohan / Mira" line.
  * **Ledger append preview** — the next `LedgerEntry` that *would* be
    recorded if the tour lead adopts the recommended pick.  This is the
    row the frontend surfaces before the analyst hits Adopt.

Pure-stdlib.  Zero new deps.  Deterministic — same input bytes → same
output bytes.  Full round-trip through `to_dict / to_json /
to_markdown` under the `waysafe.ledger.v1` envelope.

Lives at `tabs[22]` — the tab immediately after Convoy — because
Ledger is what a tour lead opens the moment Convoy hands back a
consensus pick and they realise, three reflows in, that the same
member has been eating cost every time.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable, List, Mapping, Optional, Sequence, Tuple

from convoy import (
    Convoy, Member, MemberProfile,
    ConvoyReport, StrategyBallot, MemberVote,
    _vulnerability,
    VETO_VULN_FLOOR,
    CONSENSUS_FLOOR_PTS,
)


# ============================================================ constants ==

# ---- Debt aggregation --------------------------------------------------
# A negative personal uplift on day D counts as `abs(uplift)` debt units
# absorbed by that member. Positive uplift counts as *credit* — it
# subtracts from prior absorbed debt (floored at zero — a lucky member
# who scored +5 pts on every day of a Convoy vote does not go into
# "negative debt", they simply hold zero absorbed cost).
DEBT_MIN_FLOOR = 0.0

# Vulnerable members' absorbed costs amplify: a −2 pt day on Aunt Mira
# (V ≈ 0.55) counts as −2 × (1 + 0.60 × 0.55) = −2.66 debt units. Aarav
# (V ≈ 0.00) counts a −2 as exactly −2. This matches the moral
# intuition Convoy already codified — vulnerable members are given more
# weight in the *veto* rule; Ledger extends that weighting into
# *cumulative* accounting.
W_VULN_DEBT_MULT = 0.60

# Recency decay. A day-D absorption is weighted by W_DECAY^(today - D).
# W_DECAY = 0.85 means the most-recent absorption weighs 1.0, yesterday
# weighs 0.85, day-before-yesterday 0.72, etc. Older absorptions still
# matter but recent ones dominate the rebalance signal.
W_ABSORPTION_DECAY = 0.85

# History length beyond which extra days contribute at floor weight
# (0.05). Prevents the very long trip from being dominated purely by
# ancient absorptions.
DECAY_FLOOR_WEIGHT = 0.05
HISTORY_HORIZON_DAYS = 21

# ---- Equity metric ----------------------------------------------------
# Gini coefficient of the per-member absorbed-debt vector. A value of 0
# means perfect equity (everyone holds the same); a value near 1 means
# one member holds all the debt.
#
# GINI_LEVEL_TARGET is the threshold above which the convoy is deemed
# inequitable and Ledger considers a rebalance override.
GINI_LEVEL_TARGET = 0.20

# A single member holding this fraction or more of the total debt trips
# a `hot_flag` on their row. Independent of Gini — a two-member convoy
# can hit 0.40 without an inequitable Gini, and a large convoy can be
# above target Gini without any single member being over 0.40.
DEBT_SHARE_HOT_FLOOR = 0.40

# ---- Rebalance rule ---------------------------------------------------
# The equity override is a two-signal rule. Both signals reward moves
# that *lift the top-holder off the bottom of the pile*; either can
# trigger the override on its own.
#
#   Signal A — TOP-HOLDER debt reduction (absolute, in debt units).
#              This is the human-intuitive signal ("did Aunt Mira's
#              carrying-cost actually go down?"). Robust to the case
#              where the top holder already has ~100% share and a
#              rebalance won't move the Gini needle.
REBALANCE_MIN_TOP_DELTA = 0.50
#
#   Signal B — Gini improvement (concentration reduction). Fires when
#              the debt is spread across multiple members and a
#              strategy narrows the gap even if it doesn't touch the
#              top holder much.
REBALANCE_MIN_GINI_DELTA = 0.05
#
# In either case, consensus uplift is not sacrificed by more than this:
EQUITY_TRADE_FLOOR_PTS = 2.0

# When the history has fewer than this many entries, Ledger degrades to
# a pass-through — no rebalance signal is reliable off a single ballot.
MIN_HISTORY_FOR_REBALANCE = 2

# ---- Grade ladder for the equity report --------------------------------
# The convoy's current equity grade — surfaced as a colour band on the
# hero panel. Uses Gini + hot-count as inputs.
EQUITY_GRADE_LADDER = (
    ("equitable",   0.00, "teal",   "Debt is evenly distributed — no rebalance needed."),
    ("watch",       0.15, "indigo", "Slight lean toward one member — monitor next reflow."),
    ("tilted",      0.25, "amber",  "Debt is skewing — Ledger will bias next admissible pick."),
    ("inequitable", 0.40, "rose",   "One member is holding most of the cost — rebalance now."),
)

# ---- Version -----------------------------------------------------------
VERSION = "waysafe.ledger.v1"
ENGINE_VERSION = "1.0.0"


# ============================================================== types ===

@dataclass(frozen=True)
class LedgerEntry:
    """One executed convoy pick logged to the trip's equity ledger.

    - `day_index` — the trip-day the pick applied to.
    - `age_days` — how many days ago the pick was executed relative to
      the ledger's `now`. Used for the recency decay weight.
    - `strategy_kind` — the kind of the ballot the tour lead adopted
      (`TIME_SHIFT`, `MODE_UPGRADE`, …). `STAY_COURSE` entries have
      zero absorbed-uplift by definition but are logged so the trip's
      ledger reads chronologically.
    - `member_uplifts` — the personal uplift each member absorbed under
      the pick, keyed by `member_id`. Missing members are treated as
      zero (a member joined the convoy mid-trip and wasn't voting yet).
    """
    day_index: int
    age_days: int
    strategy_kind: str
    strategy_label: str
    member_uplifts: Mapping[str, float]


@dataclass
class MemberDebt:
    """Cumulative debt position for one member across the ledger."""
    member_id: str
    member_name: str
    vulnerability: float
    absorbed_debt: float          # weighted-sum of −min(uplift, 0)
    credited: float               # weighted-sum of +uplift (offset)
    net_debt: float               # max(0, absorbed_debt − credited)
    debt_share: float             # net_debt / total_net_debt (0 if all zero)
    hot_flag: bool                # debt_share >= DEBT_SHARE_HOT_FLOOR
    days_absorbed: int            # count of days with a negative uplift
    days_credited: int            # count of days with a positive uplift
    worst_single_absorption: float  # min uplift across the ledger
    trend_reason: str             # plain-English one-liner for the UI


@dataclass
class StrategyProjection:
    """One admissible ballot re-scored on the equity axis."""
    strategy_kind: str
    strategy_day_index: int
    strategy_label: str
    consensus_uplift: float       # from the underlying convoy ballot
    is_admissible: bool
    projected_gini: float         # debt-Gini AFTER adopting this pick
    projected_top_debt: float     # top holder's net debt AFTER adopting
    projected_hot_count: int      # hot-flag members AFTER adopting
    equity_delta_gini: float      # signed (current_gini − projected_gini)
    equity_delta_top: float       # signed (current_top − projected_top); +ve = improvement
    equity_delta_consensus: float # signed (this consensus_uplift − convoy_original.consensus_uplift)
    equity_score: float           # composite: 0.5·norm(Δtop) + 0.5·(Δgini). Higher = better.
    rebalance_pick: bool          # True iff Ledger picks this over Convoy's original
    reason: str


@dataclass
class RebalanceVerdict:
    """The final Ledger recommendation with a plain-English reason."""
    kind: str                      # "endorse" | "rebalance" | "pass_through"
    equity_winner_kind: str
    equity_winner_day_index: int
    equity_winner_label: str
    original_consensus_kind: str
    original_consensus_label: str
    consensus_uplift_delta: float  # signed
    gini_delta: float              # signed (positive = improvement)
    reason: str


@dataclass
class LedgerReport:
    """The full equity ledger report over the trip's convoy history."""
    convoy_id: str
    convoy_name: str
    now: datetime
    n_history_entries: int
    n_members: int
    total_absorbed_debt: float
    total_credited: float
    total_net_debt: float
    gini_current: float
    gini_target: float
    equity_grade: str
    equity_hue: str
    equity_grade_detail: str
    member_debts: Tuple[MemberDebt, ...]
    projections: Tuple[StrategyProjection, ...]
    verdict: RebalanceVerdict
    ledger_append_preview: LedgerEntry
    member_advisories: Tuple[Tuple[str, Tuple[str, ...]], ...]
    summary_lines: Tuple[str, ...]
    engine_version: str = ENGINE_VERSION


# ============================================================ helpers ===

def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _stable_ledger_id(convoy_id: str, now: datetime) -> str:
    payload = f"{convoy_id}|{now.isoformat(timespec='seconds')}"
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:10].upper()
    return f"LDG-{digest}"


def _decay_weight(age_days: int) -> float:
    """W_DECAY^age_days, floored at DECAY_FLOOR_WEIGHT."""
    if age_days <= 0:
        return 1.0
    if age_days > HISTORY_HORIZON_DAYS:
        return DECAY_FLOOR_WEIGHT
    w = W_ABSORPTION_DECAY ** float(age_days)
    return max(DECAY_FLOOR_WEIGHT, w)


def _vuln_amp(vulnerability: float) -> float:
    """Amplification factor for absorbed cost. 1.0 at V=0, up to
    1 + W_VULN_DEBT_MULT × VULN_CAP at V=VULN_CAP."""
    return 1.0 + W_VULN_DEBT_MULT * max(0.0, vulnerability)


def _gini(values: Sequence[float]) -> float:
    """Classic mean-absolute-difference Gini on a non-negative vector.
    Returns 0 for empty / all-zero / single-member inputs."""
    xs = [max(0.0, float(v)) for v in values]
    n = len(xs)
    if n <= 1:
        return 0.0
    s = sum(xs)
    if s <= 1e-9:
        return 0.0
    xs_sorted = sorted(xs)
    cum = 0.0
    for i, v in enumerate(xs_sorted, start=1):
        cum += i * v
    return (2.0 * cum) / (n * s) - (n + 1.0) / n


def _equity_grade(gini: float, hot_count: int) -> Tuple[str, str, str]:
    """Pick the grade tuple whose gini floor is the highest still ≤ input.
    Escalates one band up if any member is hot-flagged (single-member
    over-share can be worse than a mild Gini)."""
    grade = EQUITY_GRADE_LADDER[0]
    for tup in EQUITY_GRADE_LADDER:
        if gini >= tup[1]:
            grade = tup
    if hot_count >= 1:
        # Escalate one band if we're at 'equitable' or 'watch'.
        idx = EQUITY_GRADE_LADDER.index(grade)
        if idx < len(EQUITY_GRADE_LADDER) - 1 and idx < 2:
            grade = EQUITY_GRADE_LADDER[idx + 1]
    return grade[0], grade[2], grade[3]


# ============================================ debt aggregation ==

def _compute_member_debts(
    convoy: Convoy,
    history: Sequence[LedgerEntry],
) -> List[MemberDebt]:
    """Fold the history into per-member cumulative debt positions.

    Each member row carries:
      * `absorbed_debt` — weighted sum of vulnerability-amplified
        negative uplifts across the history.
      * `credited` — weighted sum of positive uplifts (offset only, not
        vulnerability-amplified; being a beneficiary is worth the same
        pt of relief to anyone).
      * `net_debt` — max(0, absorbed − credited).
    """
    rows: List[MemberDebt] = []
    per_member_abs = {m.id: 0.0 for m in convoy.members}
    per_member_cred = {m.id: 0.0 for m in convoy.members}
    per_member_absorb_days = {m.id: 0 for m in convoy.members}
    per_member_credit_days = {m.id: 0 for m in convoy.members}
    per_member_worst = {m.id: 0.0 for m in convoy.members}

    for entry in history:
        w = _decay_weight(entry.age_days)
        for m in convoy.members:
            up = float(entry.member_uplifts.get(m.id, 0.0))
            if up < 0:
                v = _vulnerability(m.profile)
                per_member_abs[m.id] += w * (-up) * _vuln_amp(v)
                per_member_absorb_days[m.id] += 1
                if up < per_member_worst[m.id]:
                    per_member_worst[m.id] = up
            elif up > 0:
                per_member_cred[m.id] += w * up
                per_member_credit_days[m.id] += 1

    net_by_member = {
        mid: max(DEBT_MIN_FLOOR, per_member_abs[mid] - per_member_cred[mid])
        for mid in per_member_abs
    }
    total_net = sum(net_by_member.values()) or 0.0

    for m in convoy.members:
        v = _vulnerability(m.profile)
        net = net_by_member[m.id]
        share = (net / total_net) if total_net > 1e-9 else 0.0
        hot = share >= DEBT_SHARE_HOT_FLOOR and net > 0.0
        rows.append(MemberDebt(
            member_id=m.id,
            member_name=m.name,
            vulnerability=round(v, 3),
            absorbed_debt=round(per_member_abs[m.id], 3),
            credited=round(per_member_cred[m.id], 3),
            net_debt=round(net, 3),
            debt_share=round(share, 3),
            hot_flag=bool(hot),
            days_absorbed=per_member_absorb_days[m.id],
            days_credited=per_member_credit_days[m.id],
            worst_single_absorption=round(per_member_worst[m.id], 2),
            trend_reason=_member_trend_reason(
                v, net, share, hot,
                per_member_absorb_days[m.id],
                per_member_credit_days[m.id],
            ),
        ))
    return rows


def _member_trend_reason(
    vulnerability: float,
    net_debt: float,
    debt_share: float,
    hot: bool,
    days_abs: int,
    days_cred: int,
) -> str:
    if hot:
        return (
            f"holding {debt_share*100:.0f}% of convoy debt across "
            f"{days_abs} negative-uplift day(s) — needs rebalance"
        )
    if net_debt <= 1e-6 and days_cred > days_abs:
        return f"net beneficiary — credited on {days_cred}/{days_cred+days_abs} entries"
    if net_debt <= 1e-6 and days_abs == 0 and days_cred == 0:
        return "no recorded exposure yet on this ledger"
    if debt_share >= 0.25:
        return (
            f"leaning cost — {debt_share*100:.0f}% share across "
            f"{days_abs} absorption(s)"
        )
    if vulnerability >= VETO_VULN_FLOOR and days_abs > 0:
        return (
            f"vulnerable member with {days_abs} absorption(s) — "
            f"monitor next reflow"
        )
    return f"steady — {days_abs} absorption(s), {days_cred} credit(s)"


# ============================================ strategy projection ==

def _project_after_pick(
    current_debts: Sequence[MemberDebt],
    convoy: Convoy,
    ballot: StrategyBallot,
) -> Tuple[List[float], int, float]:
    """Simulate the debt vector *after* adopting `ballot`.

    Adds the ballot's per-member uplift (age_days=0, weight 1.0) to the
    current cumulative debts, applying the same vulnerability and
    positive/negative accounting rules `_compute_member_debts` uses.
    Returns (projected_net_debt_vector_aligned_with_convoy_members,
    hot_count_after, top_debt_after).
    """
    vote_map = {v.member_id: v.uplift for v in ballot.votes}
    debt_by_id = {d.member_id: (d.absorbed_debt, d.credited) for d in current_debts}
    projected_net: List[float] = []
    hot_count = 0

    for m in convoy.members:
        abs_d, cred = debt_by_id.get(m.id, (0.0, 0.0))
        up = float(vote_map.get(m.id, 0.0))
        if up < 0:
            v = _vulnerability(m.profile)
            abs_d = abs_d + (-up) * _vuln_amp(v)  # weight 1.0 (age_days=0)
        elif up > 0:
            cred = cred + up
        net = max(DEBT_MIN_FLOOR, abs_d - cred)
        projected_net.append(net)

    total = sum(projected_net)
    top_debt = max(projected_net) if projected_net else 0.0
    if total > 1e-9:
        for net in projected_net:
            if (net / total) >= DEBT_SHARE_HOT_FLOOR and net > 0.0:
                hot_count += 1
    return projected_net, hot_count, top_debt


def _build_projections(
    convoy: Convoy,
    current_debts: Sequence[MemberDebt],
    convoy_report: ConvoyReport,
) -> List[StrategyProjection]:
    """One projection row per admissible ballot in the convoy report.

    Inadmissible ballots are still returned so the frontend can render
    them greyed out with a "veto" or "dissent" chip, but they are
    excluded from the equity-winner pool.
    """
    original = convoy_report.consensus_ballot
    projections: List[StrategyProjection] = []
    current_gini = _gini([d.net_debt for d in current_debts])
    current_top = max((d.net_debt for d in current_debts), default=0.0)
    # Normalise top-delta by the current top so a Δ of 1.0 out of 5.0 is
    # a 20% top-holder relief rather than an absolute unit — makes the
    # composite score comparable across convoys of different debt scales.
    top_norm = max(1.0, current_top)

    for b in convoy_report.ballots:
        projected_net, hot_count, top_debt = _project_after_pick(current_debts, convoy, b)
        proj_gini = _gini(projected_net)
        gini_delta = round(current_gini - proj_gini, 3)
        top_delta = round(current_top - top_debt, 3)
        cons_delta = round(b.consensus_uplift - original.consensus_uplift, 2)
        # Composite equity score in a common unit. Bounded ~[-1, +1].
        equity_score = 0.5 * (top_delta / top_norm) + 0.5 * gini_delta
        reason = _projection_reason(
            b, gini_delta, top_delta, cons_delta, b is original,
        )
        projections.append(StrategyProjection(
            strategy_kind=b.strategy_kind,
            strategy_day_index=b.strategy_day_index,
            strategy_label=b.strategy_label,
            consensus_uplift=b.consensus_uplift,
            is_admissible=b.is_admissible,
            projected_gini=round(proj_gini, 3),
            projected_top_debt=round(top_debt, 3),
            projected_hot_count=hot_count,
            equity_delta_gini=gini_delta,
            equity_delta_top=top_delta,
            equity_delta_consensus=cons_delta,
            equity_score=round(equity_score, 3),
            rebalance_pick=False,  # patched in _pick_equity_winner
            reason=reason,
        ))
    return projections


def _projection_reason(
    b: StrategyBallot,
    gini_delta: float,
    top_delta: float,
    cons_delta: float,
    is_original: bool,
) -> str:
    tag = "convoy pick" if is_original else b.strategy_kind
    if not b.is_admissible:
        if b.n_veto > 0:
            return f"{tag} — inadmissible ({b.n_veto} veto)"
        return f"{tag} — inadmissible ({b.n_dissent} dissent)"
    within_trade = cons_delta >= -EQUITY_TRADE_FLOOR_PTS
    a_ok = top_delta >= REBALANCE_MIN_TOP_DELTA
    b_ok = gini_delta >= REBALANCE_MIN_GINI_DELTA
    if within_trade and (a_ok or b_ok):
        parts = []
        if a_ok:
            parts.append(f"top holder −{top_delta:+.2f} debt")
        if b_ok:
            parts.append(f"Gini {gini_delta:+.2f}")
        return (
            f"{tag} — {'; '.join(parts)} for {cons_delta:+.1f} pt trade; "
            f"equity-favourable"
        )
    if top_delta > 0 or gini_delta > 0:
        return (
            f"{tag} — top {top_delta:+.2f}, Gini {gini_delta:+.2f}; "
            f"below rebalance floor"
        )
    return (
        f"{tag} — top {top_delta:+.2f}, Gini {gini_delta:+.2f}; "
        f"no equity improvement"
    )


def _pick_equity_winner(
    projections: List[StrategyProjection],
    convoy_report: ConvoyReport,
    current_gini: float,
    n_history: int,
) -> Tuple[StrategyProjection, RebalanceVerdict]:
    """Pick the equity winner and compose the rebalance verdict.

    Rules:
      * History too short → verdict "pass_through", winner = original.
      * No admissible non-baseline projection whose gini_delta and
        consensus trade both clear the thresholds → verdict "endorse",
        winner = original.
      * Otherwise the admissible candidate that MAXIMISES gini_delta
        wins. Ties: highest consensus_uplift, then lowest hot_count,
        then alphabetical strategy_kind (deterministic).
    """
    original = convoy_report.consensus_ballot
    orig_proj = next(
        (p for p in projections if p.strategy_kind == original.strategy_kind
         and p.strategy_day_index == original.strategy_day_index),
        projections[0],
    )

    if n_history < MIN_HISTORY_FOR_REBALANCE:
        orig_proj.rebalance_pick = True
        verdict = RebalanceVerdict(
            kind="pass_through",
            equity_winner_kind=original.strategy_kind,
            equity_winner_day_index=original.strategy_day_index,
            equity_winner_label=original.strategy_label,
            original_consensus_kind=original.strategy_kind,
            original_consensus_label=original.strategy_label,
            consensus_uplift_delta=0.0,
            gini_delta=0.0,
            reason=(
                f"History has {n_history} entry — Ledger endorses the Convoy "
                f"consensus until at least {MIN_HISTORY_FOR_REBALANCE} entries "
                f"are on the trip."
            ),
        )
        return orig_proj, verdict

    candidates = [
        p for p in projections
        if p.is_admissible
        and p.strategy_kind != "STAY_COURSE"
        and p.equity_delta_consensus >= -EQUITY_TRADE_FLOOR_PTS
        and (
            p.equity_delta_top >= REBALANCE_MIN_TOP_DELTA
            or p.equity_delta_gini >= REBALANCE_MIN_GINI_DELTA
        )
    ]
    if not candidates:
        orig_proj.rebalance_pick = True
        if current_gini < GINI_LEVEL_TARGET:
            reason = (
                f"Debt is equitable (Gini {current_gini:.2f} < "
                f"target {GINI_LEVEL_TARGET:.2f}) — Convoy consensus stands."
            )
        else:
            reason = (
                f"Debt is skewing (Gini {current_gini:.2f}) but no admissible "
                f"strategy cleared the {REBALANCE_MIN_TOP_DELTA:.2f}-unit "
                f"top-holder-relief floor OR the "
                f"{REBALANCE_MIN_GINI_DELTA:.2f} Gini-drop floor at "
                f"≤{EQUITY_TRADE_FLOOR_PTS:.1f} pt consensus trade. "
                f"Convoy consensus stands; watch next reflow."
            )
        verdict = RebalanceVerdict(
            kind="endorse",
            equity_winner_kind=original.strategy_kind,
            equity_winner_day_index=original.strategy_day_index,
            equity_winner_label=original.strategy_label,
            original_consensus_kind=original.strategy_kind,
            original_consensus_label=original.strategy_label,
            consensus_uplift_delta=0.0,
            gini_delta=0.0,
            reason=reason,
        )
        return orig_proj, verdict

    # Sort: max composite equity_score, tie-break by top-holder relief,
    # then consensus_uplift desc, then hot-count asc, then kind alpha.
    candidates.sort(
        key=lambda p: (
            -p.equity_score,
            -p.equity_delta_top,
            -p.consensus_uplift,
            p.projected_hot_count,
            p.strategy_kind,
        )
    )
    winner = candidates[0]

    if winner is orig_proj:
        winner.rebalance_pick = True
        verdict = RebalanceVerdict(
            kind="endorse",
            equity_winner_kind=winner.strategy_kind,
            equity_winner_day_index=winner.strategy_day_index,
            equity_winner_label=winner.strategy_label,
            original_consensus_kind=original.strategy_kind,
            original_consensus_label=original.strategy_label,
            consensus_uplift_delta=0.0,
            gini_delta=winner.equity_delta_gini,
            reason=(
                f"Convoy consensus is already the equity winner "
                f"(top-holder Δ {winner.equity_delta_top:+.2f}, "
                f"Gini Δ {winner.equity_delta_gini:+.2f})."
            ),
        )
        return winner, verdict

    winner.rebalance_pick = True
    verdict = RebalanceVerdict(
        kind="rebalance",
        equity_winner_kind=winner.strategy_kind,
        equity_winner_day_index=winner.strategy_day_index,
        equity_winner_label=winner.strategy_label,
        original_consensus_kind=original.strategy_kind,
        original_consensus_label=original.strategy_label,
        consensus_uplift_delta=winner.equity_delta_consensus,
        gini_delta=winner.equity_delta_gini,
        reason=(
            f"Ledger overrides Convoy consensus: switching "
            f"{original.strategy_kind} → {winner.strategy_kind} lifts the "
            f"top holder by {winner.equity_delta_top:+.2f} debt units "
            f"(Gini {winner.equity_delta_gini:+.2f}) for a "
            f"{winner.equity_delta_consensus:+.1f} pt consensus trade — a "
            f"fair swap given the accumulated debt distribution."
        ),
    )
    return winner, verdict


# ============================================ per-member advisories ==

def _member_advisories(
    convoy: Convoy,
    debts: Sequence[MemberDebt],
    verdict: RebalanceVerdict,
    convoy_report: ConvoyReport,
) -> List[Tuple[str, Tuple[str, ...]]]:
    """One advisory list per member — 1..3 lines, prioritized to the
    member's cumulative-debt position and today's rebalance direction."""
    winner_ballot = next(
        (b for b in convoy_report.ballots
         if b.strategy_kind == verdict.equity_winner_kind
         and b.strategy_day_index == verdict.equity_winner_day_index),
        convoy_report.consensus_ballot,
    )
    out: List[Tuple[str, Tuple[str, ...]]] = []
    for m, d in zip(convoy.members, debts):
        vote = next((v for v in winner_ballot.votes if v.member_id == m.id), None)
        lines: List[str] = []
        if d.hot_flag:
            lines.append(
                f"🎯 {m.name} — you're holding {d.debt_share*100:.0f}% of the convoy debt "
                f"({d.days_absorbed} absorption(s), worst {d.worst_single_absorption:+.1f} pt)."
            )
            if verdict.kind == "rebalance":
                lines.append(
                    f"↩️ Today's Ledger pick ({verdict.equity_winner_kind}) is "
                    f"picked to lean toward your seat. Personal Δ today: "
                    f"{(vote.uplift if vote else 0.0):+.1f} pt."
                )
            elif verdict.kind == "endorse":
                lines.append(
                    f"⚠️ No admissible alternative rebalanced today — "
                    f"Convoy consensus stands. Flag next reflow for review."
                )
            else:
                lines.append(
                    "History still short — Ledger cannot flip today's pick yet."
                )
        elif d.net_debt <= 1e-6 and d.days_credited > 0:
            lines.append(
                f"🌤 {m.name} — net beneficiary across "
                f"{d.days_credited} credit(s). Today's move continues to favour "
                f"you (Δ {(vote.uplift if vote else 0.0):+.1f} pt); "
                f"eyes on hot-flagged members."
            )
        elif d.days_absorbed == 0 and d.days_credited == 0:
            lines.append(
                f"🆕 {m.name} — no exposure on the ledger yet. Today is your "
                f"first vote on record."
            )
        elif d.debt_share >= 0.25:
            lines.append(
                f"⚖️ {m.name} — leaning cost ({d.debt_share*100:.0f}% share). "
                f"Today's pick Δ {(vote.uplift if vote else 0.0):+.1f} pt; "
                f"monitor for a rebalance next reflow."
            )
        else:
            lines.append(
                f"✅ {m.name} — steady on the ledger "
                f"({d.days_absorbed} absorption(s), {d.days_credited} credit(s)). "
                f"Today's pick Δ {(vote.uplift if vote else 0.0):+.1f} pt."
            )
        # Vulnerability-based coaching tail.
        if d.vulnerability >= VETO_VULN_FLOOR and not d.hot_flag and d.days_absorbed > 0:
            lines.append(
                f"🩺 Vulnerable-member watch — V(m) = {d.vulnerability:.2f}. "
                f"A single heavy absorption from this seat crosses veto "
                f"threshold; keep the running total near zero."
            )
        out.append((m.id, tuple(lines)))
    return out


# ============================================ summary lines ==

def _summary_lines(
    convoy: Convoy,
    debts: Sequence[MemberDebt],
    verdict: RebalanceVerdict,
    gini_current: float,
    equity_grade: str,
    n_history: int,
) -> Tuple[str, ...]:
    lines: List[str] = []
    n = len(convoy.members)
    total = sum(d.net_debt for d in debts)
    hot = [d for d in debts if d.hot_flag]
    lines.append(
        f"Ledger over {n_history} historical pick(s) across "
        f"{n} member(s) — total net debt {total:.2f}, Gini "
        f"{gini_current:.2f} ({equity_grade})."
    )
    if hot:
        who = ", ".join(f"{d.member_name} ({d.debt_share*100:.0f}%)" for d in hot)
        lines.append(
            f"Hot-flagged: {who}. Ledger biases the next admissible "
            f"strategy toward these seats."
        )
    else:
        lines.append("No hot-flagged members — debt distribution within tolerance.")
    if verdict.kind == "rebalance":
        lines.append(
            f"REBALANCE — {verdict.original_consensus_kind} → "
            f"{verdict.equity_winner_kind}. {verdict.reason}"
        )
    elif verdict.kind == "endorse":
        lines.append(f"ENDORSE — {verdict.reason}")
    else:
        lines.append(f"PASS-THROUGH — {verdict.reason}")
    if verdict.kind == "rebalance":
        lines.append(
            f"Trade: {verdict.consensus_uplift_delta:+.1f} pt consensus "
            f"for {verdict.gini_delta:+.2f} Gini improvement."
        )
    return tuple(lines)


# ============================================ append preview ==

def _append_preview(
    winner_ballot: StrategyBallot,
    today_day_index: int,
) -> LedgerEntry:
    """The row the ledger *would* get if the tour lead adopts the winner.
    age_days=0 by construction (it happens now)."""
    return LedgerEntry(
        day_index=today_day_index,
        age_days=0,
        strategy_kind=winner_ballot.strategy_kind,
        strategy_label=winner_ballot.strategy_label,
        member_uplifts={v.member_id: round(v.uplift, 2) for v in winner_ballot.votes},
    )


# ============================================ entrypoint ==

def compose_ledger_report(
    *,
    convoy: Convoy,
    convoy_report: ConvoyReport,
    history: Sequence[LedgerEntry] = (),
    today_day_index: Optional[int] = None,
    now: Optional[datetime] = None,
) -> LedgerReport:
    """Single entrypoint. Compose the cumulative-equity ledger report.

    Deterministic — same input bytes → same output bytes.

    Guardrails:
      * `convoy.members` empty → returns a minimal "no-members" report.
      * `history` empty → verdict = "pass_through", winner = Convoy's
        original consensus, single summary line explaining why.
      * `convoy_report.ballots` empty → falls back to a synthetic
        "no-ballots" report; verdict = "pass_through".
    """
    now = now or datetime.utcnow()
    hist_list: List[LedgerEntry] = list(history)

    if not convoy.members or not convoy_report.ballots:
        # Minimal shape-valid report.
        empty_entry = LedgerEntry(
            day_index=(today_day_index if today_day_index is not None else 0),
            age_days=0,
            strategy_kind=(
                convoy_report.consensus_ballot.strategy_kind
                if convoy_report.ballots else "STAY_COURSE"
            ),
            strategy_label=(
                convoy_report.consensus_ballot.strategy_label
                if convoy_report.ballots else "no ballots"
            ),
            member_uplifts={},
        )
        return LedgerReport(
            convoy_id=convoy.id,
            convoy_name=convoy.name,
            now=now,
            n_history_entries=len(hist_list),
            n_members=len(convoy.members),
            total_absorbed_debt=0.0,
            total_credited=0.0,
            total_net_debt=0.0,
            gini_current=0.0,
            gini_target=GINI_LEVEL_TARGET,
            equity_grade="equitable",
            equity_hue="teal",
            equity_grade_detail="No convoy or no ballots — nothing to rebalance.",
            member_debts=tuple(),
            projections=tuple(),
            verdict=RebalanceVerdict(
                kind="pass_through",
                equity_winner_kind=empty_entry.strategy_kind,
                equity_winner_day_index=empty_entry.day_index,
                equity_winner_label=empty_entry.strategy_label,
                original_consensus_kind=empty_entry.strategy_kind,
                original_consensus_label=empty_entry.strategy_label,
                consensus_uplift_delta=0.0,
                gini_delta=0.0,
                reason=(
                    "Convoy has no members or no ballots — Ledger has "
                    "nothing to rebalance."
                ),
            ),
            ledger_append_preview=empty_entry,
            member_advisories=tuple(),
            summary_lines=("Empty convoy or no ballots — Ledger inactive.",),
        )

    # ---- Per-member cumulative debts -----------------------------------
    debts = _compute_member_debts(convoy, hist_list)
    total_abs = sum(d.absorbed_debt for d in debts)
    total_cred = sum(d.credited for d in debts)
    total_net = sum(d.net_debt for d in debts)
    gini_current = _gini([d.net_debt for d in debts])

    # ---- Grade panel ---------------------------------------------------
    n_hot = sum(1 for d in debts if d.hot_flag)
    grade, hue, detail = _equity_grade(gini_current, n_hot)

    # ---- Strategy projections & equity winner ---------------------------
    projections = _build_projections(convoy, debts, convoy_report)
    winner_proj, verdict = _pick_equity_winner(
        projections, convoy_report, gini_current, len(hist_list),
    )

    # ---- Advisories & summary ------------------------------------------
    advisories = _member_advisories(convoy, debts, verdict, convoy_report)
    summary = _summary_lines(convoy, debts, verdict, gini_current, grade, len(hist_list))

    # ---- Append preview ------------------------------------------------
    winner_ballot = next(
        (b for b in convoy_report.ballots
         if b.strategy_kind == verdict.equity_winner_kind
         and b.strategy_day_index == verdict.equity_winner_day_index),
        convoy_report.consensus_ballot,
    )
    append_day = (
        today_day_index
        if today_day_index is not None
        else int(getattr(convoy_report, "now", now).toordinal() % 30)
    )
    append_preview = _append_preview(winner_ballot, append_day)

    return LedgerReport(
        convoy_id=convoy.id,
        convoy_name=convoy.name,
        now=now,
        n_history_entries=len(hist_list),
        n_members=len(convoy.members),
        total_absorbed_debt=round(total_abs, 3),
        total_credited=round(total_cred, 3),
        total_net_debt=round(total_net, 3),
        gini_current=round(gini_current, 3),
        gini_target=GINI_LEVEL_TARGET,
        equity_grade=grade,
        equity_hue=hue,
        equity_grade_detail=detail,
        member_debts=tuple(debts),
        projections=tuple(projections),
        verdict=verdict,
        ledger_append_preview=append_preview,
        member_advisories=tuple(advisories),
        summary_lines=summary,
    )


# ============================================ serialisation ==

def _entry_to_dict(e: LedgerEntry) -> dict:
    return {
        "day_index": int(e.day_index),
        "age_days": int(e.age_days),
        "strategy_kind": e.strategy_kind,
        "strategy_label": e.strategy_label,
        "member_uplifts": {str(k): round(float(v), 2) for k, v in e.member_uplifts.items()},
    }


def _debt_to_dict(d: MemberDebt) -> dict:
    return {
        "member_id": d.member_id,
        "member_name": d.member_name,
        "vulnerability": round(d.vulnerability, 3),
        "absorbed_debt": round(d.absorbed_debt, 3),
        "credited": round(d.credited, 3),
        "net_debt": round(d.net_debt, 3),
        "debt_share": round(d.debt_share, 3),
        "hot_flag": bool(d.hot_flag),
        "days_absorbed": int(d.days_absorbed),
        "days_credited": int(d.days_credited),
        "worst_single_absorption": round(d.worst_single_absorption, 2),
        "trend_reason": d.trend_reason,
    }


def _projection_to_dict(p: StrategyProjection) -> dict:
    return {
        "strategy_kind": p.strategy_kind,
        "strategy_day_index": int(p.strategy_day_index),
        "strategy_label": p.strategy_label,
        "consensus_uplift": round(p.consensus_uplift, 2),
        "is_admissible": bool(p.is_admissible),
        "projected_gini": round(p.projected_gini, 3),
        "projected_top_debt": round(p.projected_top_debt, 3),
        "projected_hot_count": int(p.projected_hot_count),
        "equity_delta_gini": round(p.equity_delta_gini, 3),
        "equity_delta_top": round(p.equity_delta_top, 3),
        "equity_delta_consensus": round(p.equity_delta_consensus, 2),
        "equity_score": round(p.equity_score, 3),
        "rebalance_pick": bool(p.rebalance_pick),
        "reason": p.reason,
    }


def _verdict_to_dict(v: RebalanceVerdict) -> dict:
    return {
        "kind": v.kind,
        "equity_winner_kind": v.equity_winner_kind,
        "equity_winner_day_index": int(v.equity_winner_day_index),
        "equity_winner_label": v.equity_winner_label,
        "original_consensus_kind": v.original_consensus_kind,
        "original_consensus_label": v.original_consensus_label,
        "consensus_uplift_delta": round(v.consensus_uplift_delta, 2),
        "gini_delta": round(v.gini_delta, 3),
        "reason": v.reason,
    }


def to_dict(report: LedgerReport) -> dict:
    return {
        "version": VERSION,
        "engine_version": report.engine_version,
        "ledger_id": _stable_ledger_id(report.convoy_id, report.now),
        "convoy_id": report.convoy_id,
        "convoy_name": report.convoy_name,
        "now": report.now.isoformat(),
        "n_history_entries": int(report.n_history_entries),
        "n_members": int(report.n_members),
        "total_absorbed_debt": round(report.total_absorbed_debt, 3),
        "total_credited": round(report.total_credited, 3),
        "total_net_debt": round(report.total_net_debt, 3),
        "gini_current": round(report.gini_current, 3),
        "gini_target": round(report.gini_target, 3),
        "equity_grade": report.equity_grade,
        "equity_hue": report.equity_hue,
        "equity_grade_detail": report.equity_grade_detail,
        "member_debts": [_debt_to_dict(d) for d in report.member_debts],
        "projections": [_projection_to_dict(p) for p in report.projections],
        "verdict": _verdict_to_dict(report.verdict),
        "ledger_append_preview": _entry_to_dict(report.ledger_append_preview),
        "member_advisories": [
            {"member_id": mid, "lines": list(lns)}
            for mid, lns in report.member_advisories
        ],
        "summary_lines": list(report.summary_lines),
        "constants": {
            "W_VULN_DEBT_MULT": W_VULN_DEBT_MULT,
            "W_ABSORPTION_DECAY": W_ABSORPTION_DECAY,
            "HISTORY_HORIZON_DAYS": HISTORY_HORIZON_DAYS,
            "GINI_LEVEL_TARGET": GINI_LEVEL_TARGET,
            "DEBT_SHARE_HOT_FLOOR": DEBT_SHARE_HOT_FLOOR,
            "REBALANCE_MIN_TOP_DELTA": REBALANCE_MIN_TOP_DELTA,
            "REBALANCE_MIN_GINI_DELTA": REBALANCE_MIN_GINI_DELTA,
            "EQUITY_TRADE_FLOOR_PTS": EQUITY_TRADE_FLOOR_PTS,
            "MIN_HISTORY_FOR_REBALANCE": MIN_HISTORY_FOR_REBALANCE,
        },
    }


def to_json(report: LedgerReport, *, indent: int = 2) -> str:
    return json.dumps(to_dict(report), indent=indent, ensure_ascii=False, sort_keys=True)


def to_markdown(report: LedgerReport) -> str:
    d = to_dict(report)
    lines: List[str] = []
    lines.append(f"# WaySafe Ledger — {d['convoy_name']}")
    lines.append("")
    lines.append(f"_id: `{d['ledger_id']}` · engine: `{d['engine_version']}`_")
    lines.append(f"_composed at {d['now']}Z_")
    lines.append("")
    lines.append(f"## Equity — {d['equity_grade'].upper()}")
    lines.append("")
    lines.append(
        f"- Gini: **{d['gini_current']:.2f}** (target ≤ {d['gini_target']:.2f})"
    )
    lines.append(
        f"- Net debt: **{d['total_net_debt']:.2f}** · absorbed "
        f"{d['total_absorbed_debt']:.2f} · credited {d['total_credited']:.2f}"
    )
    lines.append(f"- History entries: **{d['n_history_entries']}** across {d['n_members']} member(s)")
    lines.append(f"- {d['equity_grade_detail']}")
    lines.append("")
    lines.append("## Verdict")
    lines.append("")
    lines.append(f"- **{d['verdict']['kind'].upper()}** — {d['verdict']['reason']}")
    if d["verdict"]["kind"] == "rebalance":
        lines.append(
            f"- {d['verdict']['original_consensus_kind']} → "
            f"**{d['verdict']['equity_winner_kind']}**"
        )
        lines.append(
            f"- Trade: {d['verdict']['consensus_uplift_delta']:+.1f} pt consensus "
            f"for {d['verdict']['gini_delta']:+.2f} Gini"
        )
    lines.append("")
    lines.append("## Member Debts")
    lines.append("")
    lines.append("| Member | V(m) | Absorbed | Credited | Net | Share | Hot |")
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: | :---: |")
    for m in d["member_debts"]:
        hot = "🔥" if m["hot_flag"] else ""
        lines.append(
            f"| {m['member_name']} | {m['vulnerability']:.2f} | "
            f"{m['absorbed_debt']:.2f} | {m['credited']:.2f} | "
            f"{m['net_debt']:.2f} | {m['debt_share']*100:.0f}% | {hot} |"
        )
    lines.append("")
    lines.append("## Strategy Projections")
    lines.append("")
    lines.append("| Strategy | Consensus | Top→ | Δ Top | Gini→ | Δ Gini | Δ Consensus | Pick |")
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: | ---: | :---: |")
    for p in d["projections"]:
        pick = "🏆" if p["rebalance_pick"] else ""
        adm = "" if p["is_admissible"] else " (inadm.)"
        lines.append(
            f"| {p['strategy_kind']} @ day {p['strategy_day_index']}{adm} | "
            f"{p['consensus_uplift']:+.2f} | {p['projected_top_debt']:.2f} | "
            f"{p['equity_delta_top']:+.2f} | {p['projected_gini']:.2f} | "
            f"{p['equity_delta_gini']:+.2f} | {p['equity_delta_consensus']:+.1f} | {pick} |"
        )
    lines.append("")
    lines.append("## Per-Member Advisories")
    lines.append("")
    for grp in d["member_advisories"]:
        name = next(
            (m["member_name"] for m in d["member_debts"] if m["member_id"] == grp["member_id"]),
            grp["member_id"],
        )
        lines.append(f"### {name}")
        for L in grp["lines"]:
            lines.append(f"- {L}")
        lines.append("")
    lines.append("## Rollup")
    lines.append("")
    for L in d["summary_lines"]:
        lines.append(f"- {L}")
    return "\n".join(lines)


# ============================================ history helpers ==

def entry_from_convoy_pick(
    convoy_report: ConvoyReport,
    day_index: int,
    age_days: int,
    picked_ballot: Optional[StrategyBallot] = None,
) -> LedgerEntry:
    """Build a LedgerEntry from a past ConvoyReport pick.

    If `picked_ballot` is None, uses `convoy_report.consensus_ballot`.
    Handy for constructing the trip's history from prior stored
    ConvoyReports in the session (the tour lead pressed Adopt and we
    now want to remember what everybody absorbed under it).
    """
    b = picked_ballot or convoy_report.consensus_ballot
    return LedgerEntry(
        day_index=int(day_index),
        age_days=int(age_days),
        strategy_kind=b.strategy_kind,
        strategy_label=b.strategy_label,
        member_uplifts={v.member_id: round(v.uplift, 2) for v in b.votes},
    )


def entry_from_editor_row(row: Mapping, member_ids: Sequence[str]) -> Optional[LedgerEntry]:
    """Parse one row from the Streamlit data_editor into a LedgerEntry.

    Row shape: {day_index, age_days, strategy_kind, strategy_label,
    <member_id_1>: uplift, <member_id_2>: uplift, ...}
    Missing / malformed rows return None so the caller can filter.
    """
    try:
        day_index = int(row.get("day_index", 0) or 0)
        age_days = int(row.get("age_days", 0) or 0)
        kind = str(row.get("strategy_kind", "STAY_COURSE") or "STAY_COURSE").strip()
        if not kind:
            return None
        label = str(row.get("strategy_label", kind) or kind).strip() or kind
        uplifts = {}
        for mid in member_ids:
            raw = row.get(mid, 0.0)
            try:
                uplifts[mid] = round(float(raw or 0.0), 2)
            except (TypeError, ValueError):
                uplifts[mid] = 0.0
        return LedgerEntry(
            day_index=day_index,
            age_days=max(0, age_days),
            strategy_kind=kind,
            strategy_label=label,
            member_uplifts=uplifts,
        )
    except (TypeError, ValueError):
        return None


def default_seed_history(convoy: Convoy) -> Tuple[LedgerEntry, ...]:
    """A short, deterministic 3-entry history for the default 4-member
    family convoy — exercises the rebalance rule end-to-end.

    Storyline:
      * 3 days ago (age_days=3), Day-2 pick was TIME_SHIFT: adults +2.4,
        child +0.6, senior −2.1 (Aunt Mira absorbed).
      * 2 days ago (age_days=2), Day-3 pick was MODE_UPGRADE: adults
        +1.8, child −1.1 (Rohan absorbed), senior −1.9 (Mira absorbed
        again).
      * Yesterday (age_days=1), Day-4 pick was STOP_DROP: adults +2.1,
        child +0.4, senior −1.2 (Mira absorbed a third time).

    Result: Mira holds ~50% of the convoy debt with a hot_flag; Rohan
    holds ~20%; the adults are net-positive beneficiaries. Ledger will
    override any admissible strategy today that leans toward Mira.
    """
    mids = [m.id for m in convoy.members]
    if len(mids) < 4:
        # Fall back to zero-history when the convoy shape doesn't match.
        return tuple()
    m_adult1, m_adult2, m_child, m_senior = mids[0], mids[1], mids[2], mids[3]
    return (
        LedgerEntry(
            day_index=2, age_days=3,
            strategy_kind="TIME_SHIFT",
            strategy_label="Depart +3h to skip escalating cluster",
            member_uplifts={
                m_adult1: 2.4, m_adult2: 2.2, m_child: 0.6, m_senior: -2.1,
            },
        ),
        LedgerEntry(
            day_index=3, age_days=2,
            strategy_kind="MODE_UPGRADE",
            strategy_label="Switch to private cab on the corridor",
            member_uplifts={
                m_adult1: 1.8, m_adult2: 1.9, m_child: -1.1, m_senior: -1.9,
            },
        ),
        LedgerEntry(
            day_index=4, age_days=1,
            strategy_kind="STOP_DROP",
            strategy_label="Drop the sunset stop; keep the corridor short",
            member_uplifts={
                m_adult1: 2.1, m_adult2: 2.3, m_child: 0.4, m_senior: -1.2,
            },
        ),
    )


# ============================================ CLI smoke ==

def _demo() -> str:
    """Run the module standalone for a smoke check.

    Composes a synthetic ConvoyReport-shape via convoy.compose_convoy_report
    using the default seed convoy + a small fabricated Nomad reflow, then
    runs Ledger over the default seed history. Prints the markdown.
    """
    from odyssey import compose_odyssey, OdysseyDay, Stop
    from nomad import compose_nomad_reflow, NomadState

    convoy_obj = __import__("convoy").default_seed_convoy()

    days = (
        OdysseyDay(date="2025-01-01", label="Day 1 · Airport → Old Town",
                   stay_lat=12.97, stay_lon=77.59, stay_label="Central Inn",
                   stops=(Stop("Airport", 13.00, 77.50, 30),
                          Stop("Old Town", 12.97, 77.59, 90),),
                   depart_hour=10),
        OdysseyDay(date="2025-01-02", label="Day 2 · Old Town → Ruins",
                   stay_lat=12.97, stay_lon=77.59, stay_label="Central Inn",
                   stops=(Stop("Old Town", 12.97, 77.59, 30),
                          Stop("Waypoint", 13.02, 77.61, 30),
                          Stop("Ruins", 13.05, 77.62, 90),),
                   depart_hour=9),
        OdysseyDay(date="2025-01-03", label="Day 3 · Ruins → Lake",
                   stay_lat=12.97, stay_lon=77.59, stay_label="Central Inn",
                   stops=(Stop("Ruins", 13.05, 77.62, 30),
                          Stop("Lake", 13.10, 77.55, 90),),
                   depart_hour=9),
    )
    trip = compose_odyssey(days=days, incidents=(), geofences={"features": []}, pois=())
    reflow = compose_nomad_reflow(
        trip=trip,
        state=NomadState(current_day_idx=1, current_lat=12.97, current_lon=77.59),
        incidents=(), geofences={"features": []}, pois=(),
    )
    from convoy import compose_convoy_report
    convoy_report = compose_convoy_report(
        convoy=convoy_obj, trip=trip, reflow=reflow,
        incidents=(), geofences={"features": []}, pois=(),
    )
    history = default_seed_history(convoy_obj)
    report = compose_ledger_report(
        convoy=convoy_obj, convoy_report=convoy_report,
        history=history, today_day_index=5,
        now=datetime(2025, 1, 1, 12, 0, 0),
    )
    return to_markdown(report)


if __name__ == "__main__":  # pragma: no cover
    print(_demo())
