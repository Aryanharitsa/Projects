"""Peer parity engine — Python mirror of frontend/src/lib/peer_parity.ts.

Closes the loop between Decision Studio (interview composite) and Offer
Studio (comp dimensions). A proposed offer is audited against the team's
accepted peer offers by fitting `dim = a·composite + b` per dimension and
z-scoring the proposal against the residual stddev. Inversions (peers who
scored higher on composite yet would be paid less than the proposal) are
flagged regardless.

Pure functions; the storage layer (peers JSON) lives next to this in
``app/data/peers_store.py``.

Outputs are camelCase-friendly via ``as_dict`` helpers so the TS engine
and this engine emit byte-identical payloads.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable, Literal


DimKey = Literal["base", "equity", "sign_on", "target_bonus", "total_cash"]
Verdict = Literal["fair", "stretch", "drift", "inversion"]
DimStatus = Literal["in_band", "stretch", "severe"]


Z_STRETCH = 1.5
Z_SEVERE = 3.0
SIGMA_FLOOR_FRAC = 0.05


@dataclass
class PeerOffer:
    id: str
    candidate_name: str
    role_name: str
    seniority: str
    location: str
    composite: int | None
    base: float
    equity_pct: float
    sign_on: float
    target_bonus_pct: float
    accepted_at: str
    source: str = "seed"

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "candidateName": self.candidate_name,
            "roleName": self.role_name,
            "seniority": self.seniority,
            "location": self.location,
            "composite": self.composite,
            "base": self.base,
            "equityPct": self.equity_pct,
            "signOn": self.sign_on,
            "targetBonusPct": self.target_bonus_pct,
            "acceptedAt": self.accepted_at,
            "source": self.source,
        }


@dataclass
class ParityDimension:
    key: DimKey
    label: str
    proposed: float
    expected: float
    expected_low: float
    expected_high: float
    sigma: float
    z: float
    pct_delta: float
    status: DimStatus

    def as_dict(self) -> dict:
        return {
            "key": self.key,
            "label": self.label,
            "proposed": _r(self.proposed, 4),
            "expected": _r(self.expected, 4),
            "expectedLow": _r(self.expected_low, 4),
            "expectedHigh": _r(self.expected_high, 4),
            "sigma": _r(self.sigma, 4),
            "z": _r(self.z, 3),
            "pctDelta": _r(self.pct_delta, 4),
            "status": self.status,
        }


@dataclass
class Inversion:
    peer: PeerOffer
    composite_gap: float
    total_gap_pct: float

    def as_dict(self) -> dict:
        return {
            "peer": self.peer.as_dict(),
            "compositeGap": _r(self.composite_gap, 1),
            "totalGapPct": _r(self.total_gap_pct, 3),
        }


@dataclass
class ParityPeer:
    peer: PeerOffer
    delta_composite: float
    delta_base: float
    total_cash: float

    def as_dict(self) -> dict:
        return {
            "peer": self.peer.as_dict(),
            "deltaComposite": _r(self.delta_composite, 1),
            "deltaBase": _r(self.delta_base, 2),
            "totalCash": _r(self.total_cash, 2),
        }


@dataclass
class Regression:
    a: float
    b: float
    r2: float
    sigma: float
    n: int

    def as_dict(self) -> dict:
        return {
            "a": _r(self.a, 4),
            "b": _r(self.b, 4),
            "r2": _r(self.r2, 3),
            "sigma": _r(self.sigma, 3),
            "n": self.n,
        }


@dataclass
class PeerParityResult:
    verdict: Verdict
    drift_score: float
    out_of_band_count: int
    proposed: dict
    dims: list[ParityDimension] = field(default_factory=list)
    inversions: list[Inversion] = field(default_factory=list)
    nearest_peers: list[ParityPeer] = field(default_factory=list)
    scatter: list[dict] = field(default_factory=list)
    regression: Regression = field(default_factory=lambda: Regression(0.0, 0.0, -1.0, 0.0, 0))
    peer_count: int = 0
    suggestions: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    range: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "verdict": self.verdict,
            "driftScore": _r(self.drift_score, 2),
            "outOfBandCount": self.out_of_band_count,
            "proposed": self.proposed,
            "dims": [d.as_dict() for d in self.dims],
            "inversions": [i.as_dict() for i in self.inversions],
            "nearestPeers": [p.as_dict() for p in self.nearest_peers],
            "scatter": list(self.scatter),
            "regression": self.regression.as_dict(),
            "peerCount": self.peer_count,
            "suggestions": list(self.suggestions),
            "notes": list(self.notes),
            "range": dict(self.range),
        }


# ---------- helpers ----------


def _r(x: float, digits: int) -> float:
    return round(float(x), digits)


def _composite(p: PeerOffer) -> float:
    return 50.0 if p.composite is None else float(p.composite)


def _total_cash(base: float, sign_on: float, target_bonus_pct: float) -> float:
    return base + sign_on + base * (target_bonus_pct / 100.0)


def _z_status(z: float) -> DimStatus:
    az = abs(z)
    if az < Z_STRETCH:
        return "in_band"
    if az < Z_SEVERE:
        return "stretch"
    return "severe"


def _regress(xs: list[float], ys: list[float]) -> tuple[float, float, float, float]:
    """Return (a, b, r2, sigma_residual)."""
    n = len(xs)
    if n < 2:
        my = sum(ys) / n if n else 0.0
        return 0.0, my, -1.0, 0.0
    sx = sum(xs); sy = sum(ys)
    sxx = sum(x * x for x in xs)
    sxy = sum(xs[i] * ys[i] for i in range(n))
    denom = n * sxx - sx * sx
    if abs(denom) < 1e-9:
        my = sy / n
        res_sq = sum((y - my) ** 2 for y in ys)
        sigma = math.sqrt(res_sq / (n - 1)) if n > 1 else 0.0
        return 0.0, my, 0.0, sigma
    a = (n * sxy - sx * sy) / denom
    b = (sy - a * sx) / n
    res_sq = 0.0
    for i in range(n):
        e = ys[i] - (a * xs[i] + b)
        res_sq += e * e
    my = sy / n
    tot_sq = sum((y - my) ** 2 for y in ys)
    r2 = (1 - res_sq / tot_sq) if tot_sq > 1e-9 else 0.0
    sigma = math.sqrt(res_sq / (n - 1)) if n > 1 else 0.0
    return a, b, r2, sigma


def _apply_floor(sigma: float, ys_mean: float) -> float:
    return max(sigma, abs(ys_mean) * SIGMA_FLOOR_FRAC)


DIM_LABELS: dict[DimKey, str] = {
    "base": "Base salary",
    "equity": "Equity %",
    "sign_on": "Sign-on bonus",
    "target_bonus": "Target bonus %",
    "total_cash": "Total cash (yr 1)",
}


def _build_dim(
    key: DimKey,
    proposed_composite: float,
    proposed_value: float,
    composites: list[float],
    values: list[float],
) -> ParityDimension:
    a, b, _r2, sigma_raw = _regress(composites, values)
    mean_y = sum(values) / len(values) if values else 0.0
    sigma = _apply_floor(sigma_raw, mean_y)
    expected = a * proposed_composite + b
    z = (proposed_value - expected) / sigma if sigma > 1e-9 else 0.0
    denom = max(1.0, abs(expected))
    return ParityDimension(
        key=key,
        label=DIM_LABELS[key],
        proposed=proposed_value,
        expected=expected,
        expected_low=max(0.0, expected - sigma),
        expected_high=expected + sigma,
        sigma=sigma,
        z=z,
        pct_delta=(proposed_value - expected) / denom,
        status=_z_status(z),
    )


# ---------- public API ----------


def compute_peer_parity(
    *,
    composite: int | None,
    base: float,
    equity_pct: float,
    sign_on: float,
    target_bonus_pct: float,
    peers: Iterable[PeerOffer],
    candidate_name: str | None = None,
) -> PeerParityResult:
    peers_list = list(peers)
    proposed_composite = 50.0 if composite is None else float(composite)
    proposed_total = _total_cash(base, sign_on, target_bonus_pct)

    proposed = {
        "composite": proposed_composite,
        "base": _r(base, 2),
        "equity": _r(equity_pct, 4),
        "sign_on": _r(sign_on, 2),
        "target_bonus": _r(target_bonus_pct, 2),
        "total_cash": _r(proposed_total, 2),
    }

    notes: list[str] = []
    if not peers_list:
        notes.append("No peer offers in the pool yet — publish accepted offers to start the audit.")
    elif len(peers_list) < 3:
        word = "peer" if len(peers_list) == 1 else "peers"
        notes.append(f"Only {len(peers_list)} {word} in the pool — verdict is directional. Add more for a tighter audit.")

    composites = [_composite(p) for p in peers_list]
    base_a, base_b, base_r2, base_sigma_raw = _regress(composites, [p.base for p in peers_list])
    base_sigma = _apply_floor(
        base_sigma_raw,
        sum(p.base for p in peers_list) / len(peers_list) if peers_list else 0.0,
    )

    dim_defs: list[tuple[DimKey, float, list[float]]] = [
        ("base", base, [p.base for p in peers_list]),
        ("equity", equity_pct, [p.equity_pct for p in peers_list]),
        ("sign_on", sign_on, [p.sign_on for p in peers_list]),
        ("target_bonus", target_bonus_pct, [p.target_bonus_pct for p in peers_list]),
        ("total_cash", proposed_total, [_total_cash(p.base, p.sign_on, p.target_bonus_pct) for p in peers_list]),
    ]
    dims: list[ParityDimension] = []
    if len(peers_list) >= 2:
        for key, val, vals in dim_defs:
            dims.append(_build_dim(key, proposed_composite, val, composites, vals))
    else:
        # Too few peers — return placeholder bands centred on the mean
        # (or the proposed value, if pool empty) so the UI still renders.
        for key, val, vals in dim_defs:
            mean_y = sum(vals) / len(vals) if vals else val
            dims.append(ParityDimension(
                key=key,
                label=DIM_LABELS[key],
                proposed=val,
                expected=mean_y,
                expected_low=max(0.0, mean_y * 0.85),
                expected_high=mean_y * 1.15,
                sigma=0.0, z=0.0, pct_delta=0.0,
                status="in_band",
            ))

    # Inversions.
    inversions: list[Inversion] = []
    for p in peers_list:
        pc = _composite(p)
        if pc <= proposed_composite + 1:
            continue
        peer_total = _total_cash(p.base, p.sign_on, p.target_bonus_pct)
        if proposed_total > peer_total * 1.02:
            inversions.append(Inversion(
                peer=p,
                composite_gap=pc - proposed_composite,
                total_gap_pct=(proposed_total - peer_total) / max(1.0, peer_total),
            ))
    inversions.sort(key=lambda i: i.total_gap_pct, reverse=True)

    # Nearest peers.
    nearest = sorted(
        (ParityPeer(
            peer=p,
            delta_composite=_composite(p) - proposed_composite,
            delta_base=p.base - base,
            total_cash=_total_cash(p.base, p.sign_on, p.target_bonus_pct),
        ) for p in peers_list),
        key=lambda x: abs(x.delta_composite),
    )[:5]

    # Scatter.
    scatter: list[dict] = []
    for p in peers_list:
        scatter.append({
            "id": p.id, "name": p.candidate_name,
            "composite": _composite(p),
            "base": p.base,
            "total": _r(_total_cash(p.base, p.sign_on, p.target_bonus_pct), 2),
            "equity": p.equity_pct,
            "isProposed": False,
        })
    scatter.append({
        "id": "__proposed__", "name": candidate_name or "Proposed",
        "composite": proposed_composite, "base": base,
        "total": _r(proposed_total, 2), "equity": equity_pct,
        "isProposed": True,
    })

    # Range.
    all_comp = [s["composite"] for s in scatter]
    all_base = [s["base"] for s in scatter]
    if not peers_list:
        rng = {
            "compositeMin": max(0.0, proposed_composite - 20.0),
            "compositeMax": min(100.0, proposed_composite + 20.0),
            "baseMin": max(0.0, base * 0.6),
            "baseMax": base * 1.4,
        }
    else:
        rng = {
            "compositeMin": min(all_comp),
            "compositeMax": max(all_comp),
            "baseMin": min(all_base),
            "baseMax": max(all_base),
        }

    # Verdict.
    out_of_band = sum(1 for d in dims if d.status != "in_band")
    drift_score = max((abs(d.z) for d in dims), default=0.0)
    if len(peers_list) < 2:
        verdict: Verdict = "fair"
    elif inversions:
        verdict = "inversion"
    elif any(d.status == "severe" for d in dims) or out_of_band >= 3:
        verdict = "drift"
    elif out_of_band >= 1:
        verdict = "stretch"
    else:
        verdict = "fair"

    suggestions: list[str] = []
    if len(peers_list) >= 2:
        worst = max(dims, key=lambda d: abs(d.z))
        if abs(worst.z) > Z_STRETCH:
            direction = "down" if worst.z > 0 else "up"
            target = worst.expected + (1 if worst.z > 0 else -1) * Z_STRETCH * worst.sigma
            delta = target - worst.proposed
            suggestions.append(
                f"Bring {worst.label.lower()} {direction} to {_fmt_num(target, worst.key)} "
                f"(Δ {_fmt_delta(delta, worst.key)}) to land inside the ±1.5σ band."
            )
        for inv in inversions[:2]:
            peer_total = _total_cash(inv.peer.base, inv.peer.sign_on, inv.peer.target_bonus_pct)
            target_total = peer_total * 0.98
            drop = proposed_total - target_total
            suggestions.append(
                f"Cut total cash by ~₹{_r(drop, 1)} LPA to clear the inversion against "
                f"{inv.peer.candidate_name} (composite {_composite(inv.peer):.0f} vs {proposed_composite:.0f})."
            )
        if not suggestions:
            suggestions.append("All dimensions are inside the ±1.5σ band — offer reads fair against your team.")

    return PeerParityResult(
        verdict=verdict,
        drift_score=drift_score,
        out_of_band_count=out_of_band,
        proposed=proposed,
        dims=dims,
        inversions=inversions,
        nearest_peers=nearest,
        scatter=scatter,
        regression=Regression(a=base_a, b=base_b, r2=base_r2, sigma=base_sigma, n=len(peers_list)),
        peer_count=len(peers_list),
        suggestions=suggestions,
        notes=notes,
        range=rng,
    )


def _fmt_num(v: float, key: DimKey) -> str:
    if key == "equity":
        return f"{v:.3f}%"
    if key == "target_bonus":
        return f"{round(v)}%"
    return f"₹{round(v)} LPA"


def _fmt_delta(d: float, key: DimKey) -> str:
    s = "+" if d >= 0 else "-"
    a = abs(d)
    if key == "equity":
        return f"{s}{a:.3f} pp"
    if key == "target_bonus":
        return f"{s}{round(a)} pp"
    return f"{s}₹{round(a)} LPA"
