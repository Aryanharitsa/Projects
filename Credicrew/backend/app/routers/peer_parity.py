"""Peer Parity HTTP surface.

* ``POST /peer-parity/check`` — audit a proposed offer against a list of
  peer offers. Returns the verdict + per-dim parity bars + inversions +
  scatter data + suggestions.
* ``GET /peer-parity/peers?team=ID`` — list peers in an in-memory team pool.
* ``POST /peer-parity/peers?team=ID`` — append a peer offer to the pool.
* ``DELETE /peer-parity/peers/{peer_id}?team=ID`` — remove one.

The team pool is held in process memory only — it's intended as a
demo-friendly store for the parity engine; production callers will hand
peers in directly via ``POST /peer-parity/check``.
"""
from __future__ import annotations

from threading import RLock
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from app.services.peer_parity import (
    PeerOffer,
    compute_peer_parity,
)


router = APIRouter(prefix="/peer-parity", tags=["peer-parity"])

# In-memory team pool keyed by team_id ("default" if not supplied).
_POOL: dict[str, list[PeerOffer]] = {}
_LOCK = RLock()


class PeerIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    candidate_name: str = Field(alias="candidateName")
    role_name: str = Field(default="", alias="roleName")
    seniority: str = "mid"
    location: str = "unknown"
    composite: Optional[int] = None
    base: float
    equity_pct: float = Field(default=0.0, alias="equityPct")
    sign_on: float = Field(default=0.0, alias="signOn")
    target_bonus_pct: float = Field(default=0.0, alias="targetBonusPct")
    accepted_at: str = Field(default="", alias="acceptedAt")
    source: str = "manual"


def _to_offer(p: PeerIn) -> PeerOffer:
    return PeerOffer(
        id=p.id, candidate_name=p.candidate_name, role_name=p.role_name,
        seniority=p.seniority, location=p.location.lower(),
        composite=p.composite, base=p.base, equity_pct=p.equity_pct,
        sign_on=p.sign_on, target_bonus_pct=p.target_bonus_pct,
        accepted_at=p.accepted_at, source=p.source,
    )


class CheckRequest(BaseModel):
    composite: Optional[int] = None
    base: float
    equity_pct: float = Field(default=0.0, alias="equityPct")
    sign_on: float = Field(default=0.0, alias="signOn")
    target_bonus_pct: float = Field(default=0.0, alias="targetBonusPct")
    candidate_name: Optional[str] = Field(default=None, alias="candidateName")
    peers: list[PeerIn] = Field(default_factory=list)

    model_config = ConfigDict(populate_by_name=True)


@router.post("/check")
def check(body: CheckRequest) -> dict:
    peers = [_to_offer(p) for p in body.peers]
    result = compute_peer_parity(
        composite=body.composite,
        base=body.base,
        equity_pct=body.equity_pct,
        sign_on=body.sign_on,
        target_bonus_pct=body.target_bonus_pct,
        peers=peers,
        candidate_name=body.candidate_name,
    )
    return result.as_dict()


@router.get("/peers")
def list_peers(team: str = Query(default="default", min_length=1)) -> dict:
    with _LOCK:
        peers = list(_POOL.get(team, []))
    return {"team": team, "peers": [p.as_dict() for p in peers], "count": len(peers)}


@router.post("/peers")
def add_peer(body: PeerIn, team: str = Query(default="default", min_length=1)) -> dict:
    offer = _to_offer(body)
    with _LOCK:
        pool = list(_POOL.get(team, []))
        pool = [p for p in pool if p.id != offer.id]
        pool.append(offer)
        pool.sort(key=lambda p: p.accepted_at or "", reverse=True)
        _POOL[team] = pool
    return {"team": team, "peer": offer.as_dict(), "count": len(_POOL[team])}


@router.delete("/peers/{peer_id}")
def remove_peer(peer_id: str, team: str = Query(default="default", min_length=1)) -> dict:
    with _LOCK:
        pool = list(_POOL.get(team, []))
        before = len(pool)
        pool = [p for p in pool if p.id != peer_id]
        _POOL[team] = pool
    if before == len(pool):
        raise HTTPException(status_code=404, detail=f"peer {peer_id} not found in team {team}")
    return {"team": team, "removed": peer_id, "count": len(_POOL[team])}


class CheckTeamRequest(BaseModel):
    composite: Optional[int] = None
    base: float
    equity_pct: float = Field(default=0.0, alias="equityPct")
    sign_on: float = Field(default=0.0, alias="signOn")
    target_bonus_pct: float = Field(default=0.0, alias="targetBonusPct")
    candidate_name: Optional[str] = Field(default=None, alias="candidateName")

    model_config = ConfigDict(populate_by_name=True)


@router.post("/check_team")
def check_team(
    body: CheckTeamRequest,
    team: str = Query(default="default", min_length=1),
) -> dict:
    """Same as /check but pulls peers from the in-memory team pool."""
    with _LOCK:
        peers = list(_POOL.get(team, []))
    result = compute_peer_parity(
        composite=body.composite,
        base=body.base,
        equity_pct=body.equity_pct,
        sign_on=body.sign_on,
        target_bonus_pct=body.target_bonus_pct,
        peers=peers,
        candidate_name=body.candidate_name,
    )
    out = result.as_dict()
    out["team"] = team
    return out


# Test-friendly hook so unit tests can reset the in-memory pool.
def _reset_pool() -> None:
    with _LOCK:
        _POOL.clear()
