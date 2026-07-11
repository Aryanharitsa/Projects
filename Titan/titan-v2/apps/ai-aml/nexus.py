"""TITAN Nexus — beneficial ownership discovery + sanctioned/PEP reach.

Every prior TITAN surface reasons about *transactional* risk — is this
account structuring, is this alert noise, is this cluster propagating
sanctions signal.  Ownership is the other half of the compliance book:
the corporate-transparency question of *who really owns and controls
this legal entity*, once you unwind the holding companies, the nominee
directors, and the offshore chain.

Regulator context — this is not academic:

- FinCEN Corporate Transparency Act (in-force 2024) mandates reporting
  any individual with **≥ 25% beneficial ownership** or "substantial
  control" of a reporting company.
- OFAC **50 % Rule**: a company owned 50% or more (aggregated across
  paths) by one or more blocked persons is itself blocked, whether or
  not it appears on the SDN list.
- EU 6AMLD retains the 25% BO threshold and adds nominee-chain
  disclosure.
- FATF Recommendation 24 (Nov-2024 update) explicitly requires
  competent authorities to see the *layered* structure and identify
  the natural persons at the top.

Nexus is the surface that answers all four in one deterministic pass.

Design
======

1.  **Graph model.**

        Entity:  entity_id, name, entity_type (individual | corporation
                 | trust | foundation | spv | partnership),
                 jurisdiction, sanctioned, pep, shell_indicators
                 (holding_only, no_employees, thin_capital, recent_
                 incorporation, nominee_directors, mail_drop_address),
                 incorporation_year.
        Edge:    parent_id, child_id, pct (0.0 … 1.0), edge_type
                 (voting | economic | nominee | trustee | founder),
                 acquired_on.

    Cycles are legal in reality (mutual-holding companies), so the
    engine tolerates them but treats a repeated node in a walk as a
    zero-weight extension.

2.  **Effective control.**

    For each (root, target) pair the engine sums the products of edge
    percentages across *every* simple path from ``root`` down to
    ``target``:

        eff(root, target) = Σ_paths Π_edges pct_e

    A person owning 60% of A which owns 40% of T contributes 0.24 on
    that path; if the same person also owns 30% of B which owns 20% of
    T, the two paths sum to 0.24 + 0.06 = 0.30.  This is the standard
    beneficial-ownership arithmetic every regulator expects.

3.  **UBO ladder — FinCEN 25 % + Substantial Control.**

        eff ≥ 0.25                              → beneficial_owner
        substantial_control flag on the edge    → beneficial_owner
        0.10 ≤ eff < 0.25                       → screening_required
        eff < 0.10                              → de_minimis

    Only *individuals* (natural persons) can be UBOs — corporate
    controllers get labelled ``corporate_owner`` and the traversal
    continues upstream.

4.  **Sanctions reach — OFAC 50 % rule.**

    For each sanctioned root S and each reachable target T:

        eff(S, T) ≥ 0.50   → BLOCKED_REACH (target inherits SDN status)
        eff(S, T) ≥ 0.25   → REPORTABLE_REACH (SAR-worthy, EDD required)
        eff(S, T) > 0      → EXPOSED_LINK    (reportable if aggregated)

    Aggregation across multiple sanctioned roots follows the OFAC
    "aggregate across all blocked persons" rule — if S1 owns 30% and
    S2 owns 25%, the aggregate 55% blocks the target even though
    neither alone would.

5.  **PEP reach — enhanced due diligence pass.**

    Same arithmetic; softer thresholds:

        eff(PEP, T) ≥ 0.25   → EDD_REQUIRED
        eff(PEP, T) ≥ 0.10   → PEP_LINKED
        eff(PEP, T) > 0      → PEP_NEXUS

    Politically-exposed-person control never blocks per se, but it
    always flips the risk grade of downstream entities.

6.  **Opacity score.**

    Composite [0, 100] per target — same-input reproducible:

        opacity = clamp( 100 · (
            0.22 · f(chain_depth)
          + 0.20 · shell_share
          + 0.18 · offshore_share
          + 0.14 · nominee_share
          + 0.10 · dispersal            # 1 - 1/(1 + n_controllers/12)
          + 0.10 · cycle_penalty        # 1 if any cycle touches target
          + 0.06 · thinness             # thin_capital indicator share
        ), 0, 100 )

    Every band is exposed in ``get_rules()``.

7.  **Verdict ladder.**  Five rungs for the surface:

        blocked_by_sanctions        one root has ≥ 50 % aggregate
        sanctions_exposed           any sanctioned nexus ≥ 25 %
        pep_edd_required            any PEP nexus ≥ 25 %
        opaque_structure            opacity ≥ 62 or missing UBO
        transparent_structure       otherwise

Public API
==========

    get_rules()                         → auditor constants
    analyze(entities, edges, targets)   → full ownership report
    sample()                            → bundled portfolio report
    entity_report(entity_id)            → per-entity UBO breakdown
    reach_report(root_id)               → downstream reach of a controller
    to_markdown(report)                 → paste-able ownership memo

Everything is pure stdlib.  Determinism guarantee: identical
(entities, edges) → identical bytes returned, identical path IDs,
identical opacity scores.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple


ENGINE_VERSION = "titan-nexus/1.0.0"


# ---------------------------------------------------------------------------
# Constants — every one exposed via get_rules() for auditor review.
# ---------------------------------------------------------------------------

UBO_THRESHOLD = 0.25            # FinCEN CTA + EU 6AMLD
UBO_SCREEN_THRESHOLD = 0.10     # secondary "we want to see who this is"

OFAC_BLOCK_THRESHOLD = 0.50     # OFAC 50 % rule (aggregate)
OFAC_REPORT_THRESHOLD = 0.25    # SAR-worthy exposure

PEP_EDD_THRESHOLD = 0.25        # enhanced due diligence
PEP_LINK_THRESHOLD = 0.10       # softer disclosure

# Traversal safety — the deepest recorded holding chain in the Panama
# Papers dataset was 11.  16 is a comfortable margin above that.
MAX_TRAVERSAL_DEPTH = 16
MAX_PATHS_PER_TARGET = 512      # protects against combinatorial fanout

# Opacity weights (must sum to 1.0).
OPACITY_WEIGHTS: Dict[str, float] = {
    "depth":     0.22,
    "shell":     0.20,
    "offshore":  0.18,
    "nominee":   0.14,
    "dispersal": 0.10,
    "cycle":     0.10,
    "thinness":  0.06,
}
OPACITY_BLOCKED_BAND = 55       # opacity ≥ this → verdict.opaque_structure

# Jurisdiction risk (mirrors the FATF grey / high-risk lists +
# opaque-corporate reputations).  Kept small and explicit; every value
# is auditable.
JURISDICTION_RISK: Dict[str, float] = {
    "US-DE": 0.35, "US-WY": 0.35, "US-NV": 0.35, "US-NY": 0.15,
    "GB": 0.15, "IE": 0.20, "NL": 0.25, "LU": 0.55, "CH": 0.30,
    "SG": 0.20, "HK": 0.35, "AE": 0.55, "MT": 0.55, "CY": 0.65,
    "BVI": 0.85, "KY": 0.85, "BM": 0.75, "PA": 0.80, "BS": 0.80,
    "IM": 0.60, "JE": 0.55, "GG": 0.55, "MU": 0.65, "SC": 0.75,
    "MC": 0.55, "LI": 0.60, "AD": 0.55, "MH": 0.85, "VU": 0.80,
    "IR": 1.00, "KP": 1.00, "MM": 0.95, "SY": 1.00, "RU": 0.85,
    "CN": 0.40, "DE": 0.15, "FR": 0.15, "JP": 0.15, "CA": 0.15,
    "AU": 0.15, "IN": 0.25, "BR": 0.30, "ZA": 0.30, "MX": 0.35,
}
DEFAULT_JURISDICTION_RISK = 0.30


VERDICT_LABEL: Dict[str, str] = {
    "blocked_by_sanctions":    "Blocked — OFAC 50% aggregate",
    "sanctions_exposed":       "Sanctions exposed",
    "pep_edd_required":        "PEP — enhanced due diligence",
    "opaque_structure":        "Opaque structure",
    "transparent_structure":   "Transparent structure",
}
VERDICT_TONE: Dict[str, str] = {
    "blocked_by_sanctions":    "critical",
    "sanctions_exposed":       "critical",
    "pep_edd_required":        "warn",
    "opaque_structure":        "watch",
    "transparent_structure":   "ok",
}


ENTITY_KINDS: Tuple[str, ...] = (
    "individual", "corporation", "trust", "foundation", "spv",
    "partnership",
)
EDGE_TYPES: Tuple[str, ...] = (
    "voting", "economic", "nominee", "trustee", "founder", "control",
)
SHELL_INDICATORS: Tuple[str, ...] = (
    "holding_only", "no_employees", "thin_capital",
    "recent_incorporation", "nominee_directors", "mail_drop_address",
)


# ---------------------------------------------------------------------------
# Bundled sample portfolio — five distinct topologies chosen to exercise
# every branch of the engine.  Every entity/edge in the sample is
# fictional but shaped like the real fact-patterns in Panama & Paradise
# Papers.
# ---------------------------------------------------------------------------

def _sample_entities() -> List[Dict[str, Any]]:
    return [
        # -- Topology 1: Diamond just-below-UBO (24% via two paths) ------
        {"id": "NX-P-001", "name": "Aisha Rahman", "kind": "individual",
         "jurisdiction": "GB", "sanctioned": False, "pep": False,
         "role": "Founder — Meridian Holdings"},
        {"id": "NX-C-001", "name": "Meridian Holdings Ltd", "kind": "corporation",
         "jurisdiction": "GB", "sanctioned": False, "pep": False,
         "incorporation_year": 2011,
         "shell_indicators": []},
        {"id": "NX-C-002", "name": "Meridian Ventures I LP", "kind": "partnership",
         "jurisdiction": "US-DE", "sanctioned": False, "pep": False,
         "incorporation_year": 2013,
         "shell_indicators": ["holding_only"]},
        {"id": "NX-C-003", "name": "Meridian Ventures II LP", "kind": "partnership",
         "jurisdiction": "US-DE", "sanctioned": False, "pep": False,
         "incorporation_year": 2013,
         "shell_indicators": ["holding_only"]},
        {"id": "NX-C-004", "name": "Kairos Robotics Inc.", "kind": "corporation",
         "jurisdiction": "US-DE", "sanctioned": False, "pep": False,
         "incorporation_year": 2018,
         "shell_indicators": []},

        # -- Topology 2: OFAC 50% cascade ------------------------------
        {"id": "NX-P-010", "name": "Aleksei Volkov [SDN 2024-08]", "kind": "individual",
         "jurisdiction": "RU", "sanctioned": True, "pep": False,
         "sanctions_list": "OFAC-SDN", "listed_on": "2024-08-14",
         "role": "Blocked person"},
        {"id": "NX-C-010", "name": "Nord Cypress Holdings Ltd", "kind": "corporation",
         "jurisdiction": "CY", "sanctioned": False, "pep": False,
         "incorporation_year": 2019,
         "shell_indicators": ["holding_only", "no_employees",
                              "nominee_directors"]},
        {"id": "NX-C-011", "name": "Rotterdam Trade B.V.", "kind": "corporation",
         "jurisdiction": "NL", "sanctioned": False, "pep": False,
         "incorporation_year": 2020,
         "shell_indicators": ["holding_only", "thin_capital"]},
        {"id": "NX-C-012", "name": "Aegean Chartering Corp", "kind": "corporation",
         "jurisdiction": "MH", "sanctioned": False, "pep": False,
         "incorporation_year": 2021,
         "shell_indicators": ["mail_drop_address", "no_employees"]},

        # -- Topology 3: Hidden PEP via BVI shell ----------------------
        {"id": "NX-P-020", "name": "Hon. Josephine Amara (Minister of Energy)",
         "kind": "individual", "jurisdiction": "NG", "sanctioned": False,
         "pep": True, "pep_position": "Cabinet Minister",
         "role": "PEP — controlling stake"},
        {"id": "NX-C-020", "name": "Silvercrest (BVI) Ltd", "kind": "corporation",
         "jurisdiction": "BVI", "sanctioned": False, "pep": False,
         "incorporation_year": 2022,
         "shell_indicators": ["holding_only", "no_employees",
                              "nominee_directors", "recent_incorporation"]},
        {"id": "NX-C-021", "name": "Wildwood Petroleum LLC", "kind": "corporation",
         "jurisdiction": "US-DE", "sanctioned": False, "pep": False,
         "incorporation_year": 2023,
         "shell_indicators": ["thin_capital", "recent_incorporation"]},

        # -- Topology 4: Four-way clean UBO split (all 25%) ------------
        {"id": "NX-P-030", "name": "Chen Wei", "kind": "individual",
         "jurisdiction": "SG", "sanctioned": False, "pep": False},
        {"id": "NX-P-031", "name": "Maria Santos", "kind": "individual",
         "jurisdiction": "PT", "sanctioned": False, "pep": False},
        {"id": "NX-P-032", "name": "David Okonkwo", "kind": "individual",
         "jurisdiction": "GB", "sanctioned": False, "pep": False},
        {"id": "NX-P-033", "name": "Fatima Al-Zahra", "kind": "individual",
         "jurisdiction": "AE", "sanctioned": False, "pep": False},
        {"id": "NX-C-030", "name": "Ternary Systems Pte", "kind": "corporation",
         "jurisdiction": "SG", "sanctioned": False, "pep": False,
         "incorporation_year": 2015,
         "shell_indicators": []},

        # -- Topology 5: Shell chain across five offshore jurisdictions
        {"id": "NX-P-040", "name": "Ricardo Silva", "kind": "individual",
         "jurisdiction": "BR", "sanctioned": False, "pep": False},
        {"id": "NX-C-040", "name": "Isla Trust", "kind": "trust",
         "jurisdiction": "KY", "sanctioned": False, "pep": False,
         "incorporation_year": 2016,
         "shell_indicators": ["holding_only"]},
        {"id": "NX-C-041", "name": "Isla Nominees (Panama)", "kind": "corporation",
         "jurisdiction": "PA", "sanctioned": False, "pep": False,
         "incorporation_year": 2016,
         "shell_indicators": ["holding_only", "nominee_directors",
                              "no_employees"]},
        {"id": "NX-C-042", "name": "Nuvem Holdings (Bermuda) Ltd",
         "kind": "corporation", "jurisdiction": "BM", "sanctioned": False,
         "pep": False, "incorporation_year": 2017,
         "shell_indicators": ["holding_only", "mail_drop_address"]},
        {"id": "NX-C-043", "name": "Nuvem Malta Foundation", "kind": "foundation",
         "jurisdiction": "MT", "sanctioned": False, "pep": False,
         "incorporation_year": 2017,
         "shell_indicators": ["nominee_directors"]},
        {"id": "NX-C-044", "name": "Nuvem BVI Ltd", "kind": "corporation",
         "jurisdiction": "BVI", "sanctioned": False, "pep": False,
         "incorporation_year": 2018,
         "shell_indicators": ["holding_only", "no_employees",
                              "nominee_directors"]},
        {"id": "NX-C-045", "name": "Copacabana Media SA", "kind": "corporation",
         "jurisdiction": "BR", "sanctioned": False, "pep": False,
         "incorporation_year": 2019,
         "shell_indicators": []},

        # -- Topology 6: Mutual-holding cycle (round-trip) -------------
        {"id": "NX-C-050", "name": "Twin Rivers Alpha Ltd", "kind": "corporation",
         "jurisdiction": "CY", "sanctioned": False, "pep": False,
         "incorporation_year": 2018,
         "shell_indicators": ["holding_only"]},
        {"id": "NX-C-051", "name": "Twin Rivers Beta Ltd", "kind": "corporation",
         "jurisdiction": "CY", "sanctioned": False, "pep": False,
         "incorporation_year": 2018,
         "shell_indicators": ["holding_only"]},
        {"id": "NX-P-050", "name": "Ivan Petrov", "kind": "individual",
         "jurisdiction": "CY", "sanctioned": False, "pep": False},

        # -- Topology 7: Substantial-control officer (edge_type=control)
        {"id": "NX-P-060", "name": "Ekaterina Vasilyeva", "kind": "individual",
         "jurisdiction": "GB", "sanctioned": False, "pep": False,
         "role": "CEO — substantial control"},
        {"id": "NX-C-060", "name": "Halcyon Data Systems plc", "kind": "corporation",
         "jurisdiction": "GB", "sanctioned": False, "pep": False,
         "incorporation_year": 2014,
         "shell_indicators": []},
    ]


def _sample_edges() -> List[Dict[str, Any]]:
    return [
        # Topology 1 — diamond just-below-UBO (24% via two 30%*40% paths)
        {"parent": "NX-P-001", "child": "NX-C-001", "pct": 1.00, "type": "voting"},
        {"parent": "NX-C-001", "child": "NX-C-002", "pct": 0.30, "type": "voting"},
        {"parent": "NX-C-001", "child": "NX-C-003", "pct": 0.30, "type": "voting"},
        {"parent": "NX-C-002", "child": "NX-C-004", "pct": 0.40, "type": "economic"},
        {"parent": "NX-C-003", "child": "NX-C-004", "pct": 0.40, "type": "economic"},

        # Topology 2 — OFAC cascade (0.80 * 0.70 * 0.60 = 33.6%)
        {"parent": "NX-P-010", "child": "NX-C-010", "pct": 0.80, "type": "voting"},
        {"parent": "NX-C-010", "child": "NX-C-011", "pct": 0.70, "type": "voting"},
        {"parent": "NX-C-011", "child": "NX-C-012", "pct": 0.60, "type": "voting"},

        # Topology 3 — hidden PEP (0.35 * 1.00 = 35%)
        {"parent": "NX-P-020", "child": "NX-C-020", "pct": 0.35, "type": "voting"},
        {"parent": "NX-C-020", "child": "NX-C-021", "pct": 1.00, "type": "voting"},

        # Topology 4 — four-way clean 25%
        {"parent": "NX-P-030", "child": "NX-C-030", "pct": 0.25, "type": "voting"},
        {"parent": "NX-P-031", "child": "NX-C-030", "pct": 0.25, "type": "voting"},
        {"parent": "NX-P-032", "child": "NX-C-030", "pct": 0.25, "type": "voting"},
        {"parent": "NX-P-033", "child": "NX-C-030", "pct": 0.25, "type": "voting"},

        # Topology 5 — five-layer shell chain, Ricardo behind everything
        {"parent": "NX-P-040", "child": "NX-C-040", "pct": 1.00, "type": "founder"},
        {"parent": "NX-C-040", "child": "NX-C-041", "pct": 1.00, "type": "trustee"},
        {"parent": "NX-C-041", "child": "NX-C-042", "pct": 1.00, "type": "voting"},
        {"parent": "NX-C-042", "child": "NX-C-043", "pct": 1.00, "type": "founder"},
        {"parent": "NX-C-043", "child": "NX-C-044", "pct": 1.00, "type": "voting"},
        {"parent": "NX-C-044", "child": "NX-C-045", "pct": 0.60, "type": "voting"},

        # Topology 6 — mutual-holding cycle
        {"parent": "NX-P-050", "child": "NX-C-050", "pct": 0.40, "type": "voting"},
        {"parent": "NX-C-050", "child": "NX-C-051", "pct": 0.55, "type": "voting"},
        {"parent": "NX-C-051", "child": "NX-C-050", "pct": 0.30, "type": "voting"},

        # Topology 7 — substantial-control officer, tiny economic stake
        {"parent": "NX-P-060", "child": "NX-C-060", "pct": 0.02, "type": "control"},
    ]


def _default_targets() -> List[str]:
    """Which entities each surface highlights by default."""
    return [
        "NX-C-004",   # diamond target — right at the UBO edge
        "NX-C-012",   # OFAC cascade end
        "NX-C-021",   # hidden PEP end
        "NX-C-030",   # four-way UBO split
        "NX-C-045",   # deep shell chain end
        "NX-C-050",   # cyclic
        "NX-C-060",   # substantial-control officer
    ]


# ---------------------------------------------------------------------------
# Internal graph representation
# ---------------------------------------------------------------------------


@dataclass
class _Entity:
    id: str
    name: str
    kind: str
    jurisdiction: str
    sanctioned: bool = False
    pep: bool = False
    role: Optional[str] = None
    pep_position: Optional[str] = None
    sanctions_list: Optional[str] = None
    listed_on: Optional[str] = None
    incorporation_year: Optional[int] = None
    shell_indicators: List[str] = field(default_factory=list)


@dataclass
class _Edge:
    parent: str
    child: str
    pct: float
    type: str = "voting"
    acquired_on: Optional[str] = None


@dataclass
class _Graph:
    entities: Dict[str, _Entity]
    edges: List[_Edge]
    parents_of: Dict[str, List[_Edge]] = field(default_factory=dict)
    children_of: Dict[str, List[_Edge]] = field(default_factory=dict)

    @classmethod
    def build(cls, entities_in: Iterable[Dict[str, Any]],
              edges_in: Iterable[Dict[str, Any]]) -> "_Graph":
        entities: Dict[str, _Entity] = {}
        for raw in entities_in:
            eid = str(raw["id"]).strip()
            if not eid:
                continue
            kind = str(raw.get("kind", "corporation")).strip().lower()
            if kind not in ENTITY_KINDS:
                kind = "corporation"
            shell = [s for s in raw.get("shell_indicators", []) or []
                     if s in SHELL_INDICATORS]
            entities[eid] = _Entity(
                id=eid,
                name=str(raw.get("name") or eid),
                kind=kind,
                jurisdiction=str(raw.get("jurisdiction") or "").strip().upper()[:6],
                sanctioned=bool(raw.get("sanctioned")),
                pep=bool(raw.get("pep")),
                role=raw.get("role"),
                pep_position=raw.get("pep_position"),
                sanctions_list=raw.get("sanctions_list"),
                listed_on=raw.get("listed_on"),
                incorporation_year=(
                    int(raw["incorporation_year"])
                    if raw.get("incorporation_year") not in (None, "") else None
                ),
                shell_indicators=shell,
            )
        edges: List[_Edge] = []
        parents_of: Dict[str, List[_Edge]] = {eid: [] for eid in entities}
        children_of: Dict[str, List[_Edge]] = {eid: [] for eid in entities}
        for raw in edges_in:
            p = str(raw.get("parent") or "").strip()
            c = str(raw.get("child") or "").strip()
            if p not in entities or c not in entities or p == c:
                continue
            try:
                pct = float(raw.get("pct", 0.0))
            except (TypeError, ValueError):
                continue
            if pct <= 0 or pct > 1.0:
                continue
            etype = str(raw.get("type") or "voting").strip().lower()
            if etype not in EDGE_TYPES:
                etype = "voting"
            edge = _Edge(parent=p, child=c, pct=round(pct, 6), type=etype,
                         acquired_on=raw.get("acquired_on"))
            edges.append(edge)
            parents_of[c].append(edge)
            children_of[p].append(edge)
        # Deterministic iteration order — sort every adjacency list.
        for lst in parents_of.values():
            lst.sort(key=lambda e: (e.parent, -e.pct))
        for lst in children_of.values():
            lst.sort(key=lambda e: (e.child, -e.pct))
        return cls(entities=entities, edges=edges,
                   parents_of=parents_of, children_of=children_of)


# ---------------------------------------------------------------------------
# Effective control — depth-first path enumeration with cycle guard.
# ---------------------------------------------------------------------------


def _paths_up(graph: _Graph, target: str) -> List[Dict[str, Any]]:
    """Every simple path from any root down to ``target``, with the
    cumulative product weight.  Roots = nodes with no parents."""
    out: List[Dict[str, Any]] = []

    def walk(node: str, chain: List[str], edges: List[_Edge], weight: float,
             seen: Set[str]) -> None:
        if len(out) >= MAX_PATHS_PER_TARGET:
            return
        parents = graph.parents_of.get(node, [])
        if not parents:
            # root — but only emit if the chain has length ≥ 1 (skip trivial)
            if edges:
                out.append({
                    "root": node,
                    "target": target,
                    "chain": [node] + list(reversed(chain[:-1])) + [target],
                    "weight": round(weight, 8),
                    "depth": len(edges),
                    "edges": [
                        {"parent": e.parent, "child": e.child,
                         "pct": e.pct, "type": e.type}
                        for e in reversed(edges)
                    ],
                })
            return
        for edge in parents:
            if edge.parent in seen or len(edges) >= MAX_TRAVERSAL_DEPTH:
                continue
            seen.add(edge.parent)
            walk(edge.parent, chain + [edge.parent], edges + [edge],
                 weight * edge.pct, seen)
            seen.remove(edge.parent)

    walk(target, [target], [], 1.0, {target})
    out.sort(key=lambda p: (-p["weight"], p["depth"], p["root"]))
    return out


def _paths_down(graph: _Graph, root: str) -> List[Dict[str, Any]]:
    """Every simple downstream path from ``root`` — for reach analysis."""
    out: List[Dict[str, Any]] = []

    def walk(node: str, chain: List[str], edges: List[_Edge], weight: float,
             seen: Set[str]) -> None:
        if len(out) >= MAX_PATHS_PER_TARGET:
            return
        children = graph.children_of.get(node, [])
        for edge in children:
            if edge.child in seen or len(edges) >= MAX_TRAVERSAL_DEPTH:
                continue
            new_weight = weight * edge.pct
            new_chain = chain + [edge.child]
            new_edges = edges + [edge]
            out.append({
                "root": root,
                "target": edge.child,
                "chain": list(new_chain),
                "weight": round(new_weight, 8),
                "depth": len(new_edges),
                "edges": [
                    {"parent": e.parent, "child": e.child,
                     "pct": e.pct, "type": e.type}
                    for e in new_edges
                ],
            })
            seen.add(edge.child)
            walk(edge.child, new_chain, new_edges, new_weight, seen)
            seen.remove(edge.child)

    walk(root, [root], [], 1.0, {root})
    out.sort(key=lambda p: (-p["weight"], p["depth"]))
    return out


def _detect_cycles(graph: _Graph) -> List[List[str]]:
    """Every simple directed cycle in the ownership graph.  Small
    graphs only — capped at 32 cycles."""
    out: List[List[str]] = []
    WHITE, GREY, BLACK = 0, 1, 2
    color: Dict[str, int] = {eid: WHITE for eid in graph.entities}
    stack: List[str] = []

    def dfs(node: str) -> None:
        if len(out) >= 32:
            return
        color[node] = GREY
        stack.append(node)
        for edge in graph.children_of.get(node, []):
            if len(out) >= 32:
                break
            nxt = edge.child
            if color[nxt] == GREY:
                # cycle — extract the loop from stack
                if nxt in stack:
                    idx = stack.index(nxt)
                    loop = stack[idx:] + [nxt]
                    # canonicalise starting at min id
                    m = min(range(len(loop) - 1),
                            key=lambda i: loop[i])
                    canon = loop[m:-1] + loop[:m] + [loop[m]]
                    if canon not in out:
                        out.append(canon)
            elif color[nxt] == WHITE:
                dfs(nxt)
        stack.pop()
        color[node] = BLACK

    for eid in sorted(graph.entities.keys()):
        if color[eid] == WHITE:
            dfs(eid)
    return out


# ---------------------------------------------------------------------------
# Aggregation — sum path weights per (controller, target) pair.
# ---------------------------------------------------------------------------


def _aggregate_controllers(paths: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Sum path weights by root; ranked descending."""
    by_root: Dict[str, Dict[str, Any]] = {}
    for p in paths:
        row = by_root.setdefault(p["root"], {
            "root": p["root"], "aggregate": 0.0, "path_count": 0,
            "max_path_weight": 0.0, "shortest_depth": 10**6,
            "paths": [],
        })
        row["aggregate"] += p["weight"]
        row["path_count"] += 1
        if p["weight"] > row["max_path_weight"]:
            row["max_path_weight"] = p["weight"]
        if p["depth"] < row["shortest_depth"]:
            row["shortest_depth"] = p["depth"]
        row["paths"].append(p)
    for row in by_root.values():
        row["aggregate"] = round(min(1.0, row["aggregate"]), 6)
        row["max_path_weight"] = round(row["max_path_weight"], 6)
        row["paths"].sort(key=lambda p: (-p["weight"], p["depth"]))
        row["paths"] = row["paths"][:6]  # cap for surface
    return sorted(by_root.values(),
                  key=lambda r: (-r["aggregate"], r["shortest_depth"]))


def _classify_ubo(agg: float, is_individual: bool,
                  substantial: bool) -> Dict[str, Any]:
    if substantial:
        return {"code": "beneficial_owner",
                "reason": "Substantial-control officer flag",
                "threshold": None}
    if agg >= UBO_THRESHOLD:
        return {"code": "beneficial_owner",
                "reason": f"aggregate {agg*100:.1f}% ≥ 25% FinCEN threshold",
                "threshold": UBO_THRESHOLD}
    if agg >= UBO_SCREEN_THRESHOLD:
        return {"code": "screening_required",
                "reason": f"aggregate {agg*100:.1f}% ≥ 10% — verify identity",
                "threshold": UBO_SCREEN_THRESHOLD}
    if not is_individual:
        return {"code": "corporate_owner",
                "reason": "corporate controller — traverse upstream",
                "threshold": None}
    return {"code": "de_minimis",
            "reason": f"aggregate {agg*100:.2f}% below screening floor",
            "threshold": None}


# ---------------------------------------------------------------------------
# Opacity — per-target composite [0, 100] from the seven components.
# ---------------------------------------------------------------------------


def _opacity(target: str, graph: _Graph, paths: List[Dict[str, Any]],
             controllers: List[Dict[str, Any]],
             cycles: List[List[str]]) -> Dict[str, Any]:
    if not paths and target not in graph.entities:
        return {"score": 0, "components": {}, "band": "clean"}
    depths = [p["depth"] for p in paths] or [0]
    max_depth = max(depths)
    depth_score = min(1.0, max_depth / 6.0)

    # Traverse every node touched in any path + the target itself.
    touched: Set[str] = {target}
    for p in paths:
        touched.update(p["chain"])
    inter_nodes = [graph.entities[n] for n in touched
                   if n in graph.entities and n != target]

    def _share(pred) -> float:
        if not inter_nodes:
            return 0.0
        return sum(1 for e in inter_nodes if pred(e)) / len(inter_nodes)

    shell_share = _share(
        lambda e: any(ind in e.shell_indicators
                      for ind in ("holding_only", "no_employees",
                                  "mail_drop_address")))
    offshore_share = _share(
        lambda e: _jurisdiction_risk(e.jurisdiction) >= 0.60)
    nominee_share = _share(
        lambda e: "nominee_directors" in e.shell_indicators
                  or _edge_type_touches(graph, e.id, "nominee")
                  or _edge_type_touches(graph, e.id, "trustee"))
    thin_share = _share(lambda e: "thin_capital" in e.shell_indicators)

    n_controllers = len(controllers)
    dispersal = 1.0 - 1.0 / (1.0 + n_controllers / 12.0)

    cycle_hit = any(target in cyc or any(n in cyc for n in touched)
                    for cyc in cycles)
    cycle_penalty = 1.0 if cycle_hit else 0.0

    components = {
        "depth":     round(depth_score, 4),
        "shell":     round(shell_share, 4),
        "offshore":  round(offshore_share, 4),
        "nominee":   round(nominee_share, 4),
        "dispersal": round(dispersal, 4),
        "cycle":     cycle_penalty,
        "thinness":  round(thin_share, 4),
    }
    weighted = sum(OPACITY_WEIGHTS[k] * v for k, v in components.items())
    score = int(round(max(0.0, min(100.0, weighted * 100.0))))
    if score >= 78:
        band = "opaque"
    elif score >= OPACITY_BLOCKED_BAND:
        band = "layered"
    elif score >= 30:
        band = "moderate"
    else:
        band = "clean"
    return {"score": score, "band": band, "components": components,
            "max_depth": max_depth}


def _jurisdiction_risk(code: str) -> float:
    if not code:
        return DEFAULT_JURISDICTION_RISK
    return JURISDICTION_RISK.get(code, DEFAULT_JURISDICTION_RISK)


def _edge_type_touches(graph: _Graph, node: str, etype: str) -> bool:
    for e in graph.parents_of.get(node, []):
        if e.type == etype:
            return True
    for e in graph.children_of.get(node, []):
        if e.type == etype:
            return True
    return False


# ---------------------------------------------------------------------------
# Per-target report — the core object every surface renders.
# ---------------------------------------------------------------------------


def _target_report(target: str, graph: _Graph,
                   cycles: List[List[str]]) -> Dict[str, Any]:
    ent = graph.entities.get(target)
    if ent is None:
        raise KeyError(f"entity not found: {target}")

    paths = _paths_up(graph, target)
    controllers = _aggregate_controllers(paths)

    # Enrich controllers with entity metadata + UBO classification.
    for row in controllers:
        eid = row["root"]
        parent_ent = graph.entities.get(eid)
        if parent_ent is None:
            continue
        # Substantial-control override: any direct edge with type=control
        # marks the individual as UBO regardless of pct.
        substantial = any(
            e.type == "control" and e.parent == eid and e.pct < UBO_THRESHOLD
            for e in graph.parents_of.get(target, [])
        )
        cls = _classify_ubo(
            row["aggregate"],
            is_individual=(parent_ent.kind == "individual"),
            substantial=substantial and parent_ent.kind == "individual",
        )
        row["ubo"] = cls
        row["name"] = parent_ent.name
        row["kind"] = parent_ent.kind
        row["jurisdiction"] = parent_ent.jurisdiction
        row["sanctioned"] = parent_ent.sanctioned
        row["pep"] = parent_ent.pep
        row["role"] = parent_ent.role
        row["pep_position"] = parent_ent.pep_position
        row["sanctions_list"] = parent_ent.sanctions_list
        row["substantial_control"] = substantial and parent_ent.kind == "individual"

    ubos = [c for c in controllers
            if c.get("ubo", {}).get("code") == "beneficial_owner"
            and c.get("kind") == "individual"]

    # Sanctions reach — aggregate blocked persons.
    sanctioned_agg = 0.0
    sanctioned_hits: List[Dict[str, Any]] = []
    for c in controllers:
        if c.get("sanctioned"):
            sanctioned_agg += c["aggregate"]
            code = "BLOCKED_REACH" if c["aggregate"] >= OFAC_BLOCK_THRESHOLD \
                else "REPORTABLE_REACH" if c["aggregate"] >= OFAC_REPORT_THRESHOLD \
                else "EXPOSED_LINK"
            sanctioned_hits.append({**c, "reach_code": code})
    sanctioned_agg = round(min(1.0, sanctioned_agg), 6)

    pep_hits: List[Dict[str, Any]] = []
    for c in controllers:
        if c.get("pep"):
            code = "EDD_REQUIRED" if c["aggregate"] >= PEP_EDD_THRESHOLD \
                else "PEP_LINKED" if c["aggregate"] >= PEP_LINK_THRESHOLD \
                else "PEP_NEXUS"
            pep_hits.append({**c, "reach_code": code})

    opacity = _opacity(target, graph, paths, controllers, cycles)

    # ---- verdict ladder ------------------------------------------------
    if sanctioned_agg >= OFAC_BLOCK_THRESHOLD or \
       any(h["reach_code"] == "BLOCKED_REACH" for h in sanctioned_hits):
        verdict = "blocked_by_sanctions"
        reason = (f"OFAC 50% rule: aggregate sanctioned control "
                  f"{sanctioned_agg*100:.1f}%.")
    elif sanctioned_hits and any(
            h["reach_code"] == "REPORTABLE_REACH" for h in sanctioned_hits):
        verdict = "sanctions_exposed"
        reason = (f"Sanctioned nexus of "
                  f"{max(h['aggregate'] for h in sanctioned_hits)*100:.1f}% — "
                  f"SAR-worthy, EDD required.")
    elif any(h["reach_code"] == "EDD_REQUIRED" for h in pep_hits):
        verdict = "pep_edd_required"
        reason = "Politically-exposed-person control ≥ 25% — EDD required."
    elif opacity["score"] >= OPACITY_BLOCKED_BAND or (
            paths and not ubos):
        verdict = "opaque_structure"
        reason = (
            f"Opacity {opacity['score']} — no clean UBO found."
            if not ubos else
            f"Opacity {opacity['score']} — layered chain requires review."
        )
    else:
        verdict = "transparent_structure"
        reason = (f"{len(ubos)} UBO(s) identified; opacity {opacity['score']}."
                  if ubos else
                  "No controllers on record; entity treated as founder-owned.")

    return {
        "target": {
            "id": ent.id,
            "name": ent.name,
            "kind": ent.kind,
            "jurisdiction": ent.jurisdiction,
            "jurisdiction_risk": round(_jurisdiction_risk(ent.jurisdiction), 3),
            "incorporation_year": ent.incorporation_year,
            "shell_indicators": ent.shell_indicators,
        },
        "controllers": controllers,
        "ubos": [{"id": u["root"], "name": u["name"],
                  "aggregate": u["aggregate"],
                  "kind": u["kind"], "jurisdiction": u["jurisdiction"],
                  "sanctioned": u["sanctioned"], "pep": u["pep"],
                  "substantial_control": u.get("substantial_control", False)}
                 for u in ubos],
        "sanctions": {
            "aggregate": sanctioned_agg,
            "verdict": (
                "BLOCKED" if sanctioned_agg >= OFAC_BLOCK_THRESHOLD else
                "REPORTABLE" if sanctioned_agg >= OFAC_REPORT_THRESHOLD else
                "EXPOSED" if sanctioned_hits else "CLEAN"
            ),
            "hits": sanctioned_hits,
        },
        "pep": {
            "count": len(pep_hits),
            "max_aggregate": (
                max((h["aggregate"] for h in pep_hits), default=0.0)
            ),
            "hits": pep_hits,
        },
        "opacity": opacity,
        "path_count": len(paths),
        "verdict": {
            "code": verdict,
            "label": VERDICT_LABEL[verdict],
            "tone": VERDICT_TONE[verdict],
            "reason": reason,
        },
        "cycles_touching": [cyc for cyc in cycles if target in cyc],
    }


# ---------------------------------------------------------------------------
# Portfolio-level rollups
# ---------------------------------------------------------------------------


def _portfolio_stats(reports: List[Dict[str, Any]],
                     graph: _Graph) -> Dict[str, Any]:
    verdict_hist: Dict[str, int] = {v: 0 for v in VERDICT_LABEL}
    for r in reports:
        verdict_hist[r["verdict"]["code"]] += 1
    opacity_avg = (
        round(sum(r["opacity"]["score"] for r in reports) / len(reports), 1)
        if reports else 0.0
    )
    sanctioned_hits = sum(1 for r in reports
                          if r["sanctions"]["verdict"] != "CLEAN")
    pep_hits = sum(1 for r in reports if r["pep"]["count"] > 0)
    n_entities = len(graph.entities)
    n_edges = len(graph.edges)
    n_individuals = sum(1 for e in graph.entities.values()
                        if e.kind == "individual")
    n_offshore = sum(
        1 for e in graph.entities.values()
        if _jurisdiction_risk(e.jurisdiction) >= 0.60
    )
    n_shell = sum(
        1 for e in graph.entities.values() if e.shell_indicators
    )
    return {
        "entities":      n_entities,
        "edges":         n_edges,
        "individuals":   n_individuals,
        "offshore":      n_offshore,
        "shell_flagged": n_shell,
        "targets":       len(reports),
        "verdict_hist":  verdict_hist,
        "opacity_avg":   opacity_avg,
        "sanctioned_hits": sanctioned_hits,
        "pep_hits":      pep_hits,
    }


def _corpus_hash(entities: List[Dict[str, Any]],
                 edges: List[Dict[str, Any]]) -> str:
    """Deterministic fingerprint over the input corpus — for
    cache-keying + reproducibility on the frontend."""
    m = hashlib.sha256()
    for e in sorted(entities, key=lambda x: str(x.get("id", ""))):
        m.update(json.dumps(e, sort_keys=True, default=str).encode())
    for e in sorted(edges, key=lambda x: (str(x.get("parent", "")),
                                          str(x.get("child", "")))):
        m.update(json.dumps(e, sort_keys=True, default=str).encode())
    return m.hexdigest()[:16]


# ---------------------------------------------------------------------------
# Public entry-points
# ---------------------------------------------------------------------------


def get_rules() -> Dict[str, Any]:
    return {
        "engine": ENGINE_VERSION,
        "thresholds": {
            "ubo": UBO_THRESHOLD,
            "ubo_screen": UBO_SCREEN_THRESHOLD,
            "ofac_block": OFAC_BLOCK_THRESHOLD,
            "ofac_report": OFAC_REPORT_THRESHOLD,
            "pep_edd": PEP_EDD_THRESHOLD,
            "pep_link": PEP_LINK_THRESHOLD,
            "opacity_opaque_band": OPACITY_BLOCKED_BAND,
        },
        "traversal": {
            "max_depth": MAX_TRAVERSAL_DEPTH,
            "max_paths_per_target": MAX_PATHS_PER_TARGET,
        },
        "opacity_weights": OPACITY_WEIGHTS,
        "jurisdiction_risk": JURISDICTION_RISK,
        "default_jurisdiction_risk": DEFAULT_JURISDICTION_RISK,
        "verdict_ladder": [
            {"code": k, "label": VERDICT_LABEL[k], "tone": VERDICT_TONE[k]}
            for k in ("transparent_structure", "opaque_structure",
                      "pep_edd_required", "sanctions_exposed",
                      "blocked_by_sanctions")
        ],
        "entity_kinds": list(ENTITY_KINDS),
        "edge_types": list(EDGE_TYPES),
        "shell_indicators": list(SHELL_INDICATORS),
    }


def analyze(entities: Iterable[Dict[str, Any]],
            edges: Iterable[Dict[str, Any]],
            targets: Optional[Iterable[str]] = None) -> Dict[str, Any]:
    ent_list = list(entities)
    edge_list = list(edges)
    graph = _Graph.build(ent_list, edge_list)
    if not graph.entities:
        raise ValueError("no entities supplied")

    # Auto-pick targets when none supplied: every entity that has parents
    # (i.e. someone owns it), capped for surface sanity.
    if targets is None:
        target_ids = [eid for eid in graph.entities
                      if graph.parents_of.get(eid)]
    else:
        target_ids = [t for t in targets if t in graph.entities]
    target_ids = sorted(set(target_ids))

    cycles = _detect_cycles(graph)
    reports = [_target_report(t, graph, cycles) for t in target_ids]

    # Corpus-wide highlight — the single target with the worst verdict.
    verdict_rank = {
        "blocked_by_sanctions": 5, "sanctions_exposed": 4,
        "pep_edd_required": 3, "opaque_structure": 2,
        "transparent_structure": 1,
    }
    highlight = None
    if reports:
        highlight = max(reports, key=lambda r: (
            verdict_rank.get(r["verdict"]["code"], 0),
            r["opacity"]["score"],
        ))

    return {
        "engine": ENGINE_VERSION,
        "corpus_hash": _corpus_hash(ent_list, edge_list),
        "portfolio": _portfolio_stats(reports, graph),
        "reports": reports,
        "highlight_target_id": highlight["target"]["id"] if highlight else None,
        "cycles": cycles,
        "rules": get_rules(),
    }


def sample() -> Dict[str, Any]:
    return analyze(
        entities=_sample_entities(),
        edges=_sample_edges(),
        targets=_default_targets(),
    )


def entity_report(entity_id: str) -> Dict[str, Any]:
    """Convenience wrapper — analyse the bundled sample against a single
    target.  For caller-supplied graphs use ``analyze``."""
    ent_list = _sample_entities()
    edge_list = _sample_edges()
    graph = _Graph.build(ent_list, edge_list)
    if entity_id not in graph.entities:
        raise KeyError(f"entity not found: {entity_id}")
    cycles = _detect_cycles(graph)
    return {
        "engine": ENGINE_VERSION,
        "corpus_hash": _corpus_hash(ent_list, edge_list),
        "report": _target_report(entity_id, graph, cycles),
        "rules": get_rules(),
    }


def reach_report(root_id: str) -> Dict[str, Any]:
    """Every downstream entity reachable from ``root_id`` — for
    sanctioned/PEP reach visualisation."""
    ent_list = _sample_entities()
    edge_list = _sample_edges()
    graph = _Graph.build(ent_list, edge_list)
    if root_id not in graph.entities:
        raise KeyError(f"entity not found: {root_id}")
    paths = _paths_down(graph, root_id)

    # Aggregate downstream weight per target.
    by_target: Dict[str, Dict[str, Any]] = {}
    for p in paths:
        row = by_target.setdefault(p["target"], {
            "target": p["target"],
            "aggregate": 0.0,
            "shortest_depth": 10**6,
            "path_count": 0,
            "paths": [],
        })
        row["aggregate"] += p["weight"]
        row["path_count"] += 1
        if p["depth"] < row["shortest_depth"]:
            row["shortest_depth"] = p["depth"]
        row["paths"].append(p)
    for row in by_target.values():
        row["aggregate"] = round(min(1.0, row["aggregate"]), 6)
        row["paths"].sort(key=lambda p: (-p["weight"], p["depth"]))
        row["paths"] = row["paths"][:4]
        ent = graph.entities.get(row["target"])
        if ent:
            row["name"] = ent.name
            row["kind"] = ent.kind
            row["jurisdiction"] = ent.jurisdiction
            row["sanctioned"] = ent.sanctioned
            row["pep"] = ent.pep

    reach_rows = sorted(by_target.values(),
                        key=lambda r: (-r["aggregate"], r["shortest_depth"]))

    root_ent = graph.entities[root_id]
    root_kind = "sanctioned" if root_ent.sanctioned else \
                "pep" if root_ent.pep else "controller"
    thresholds = (
        {"block": OFAC_BLOCK_THRESHOLD, "report": OFAC_REPORT_THRESHOLD}
        if root_ent.sanctioned else
        {"block": None, "report": PEP_EDD_THRESHOLD}
    )
    counts = {
        "blocked": sum(1 for r in reach_rows
                       if r["aggregate"] >= OFAC_BLOCK_THRESHOLD),
        "reportable": sum(1 for r in reach_rows
                          if OFAC_REPORT_THRESHOLD <= r["aggregate"]
                          < OFAC_BLOCK_THRESHOLD),
        "exposed": sum(1 for r in reach_rows
                       if 0 < r["aggregate"] < OFAC_REPORT_THRESHOLD),
    }
    return {
        "engine": ENGINE_VERSION,
        "corpus_hash": _corpus_hash(ent_list, edge_list),
        "root": {
            "id": root_ent.id,
            "name": root_ent.name,
            "kind": root_ent.kind,
            "jurisdiction": root_ent.jurisdiction,
            "sanctioned": root_ent.sanctioned,
            "pep": root_ent.pep,
            "role": root_ent.role,
            "pep_position": root_ent.pep_position,
            "sanctions_list": root_ent.sanctions_list,
            "listed_on": root_ent.listed_on,
        },
        "root_kind": root_kind,
        "thresholds": thresholds,
        "reach": reach_rows,
        "counts": counts,
    }


def controller_candidates() -> List[Dict[str, Any]]:
    """Every sanctioned / PEP / substantial-control natural person in
    the bundled corpus — for the ``reach`` surface's picker."""
    ent_list = _sample_entities()
    edge_list = _sample_edges()
    graph = _Graph.build(ent_list, edge_list)
    out: List[Dict[str, Any]] = []
    for eid, ent in graph.entities.items():
        if not (ent.sanctioned or ent.pep or ent.role):
            continue
        # only surface actual controllers (roots with downstream reach)
        if not graph.children_of.get(eid):
            continue
        out.append({
            "id": ent.id,
            "name": ent.name,
            "kind": ent.kind,
            "jurisdiction": ent.jurisdiction,
            "sanctioned": ent.sanctioned,
            "pep": ent.pep,
            "role": ent.role,
            "sanctions_list": ent.sanctions_list,
            "pep_position": ent.pep_position,
            "child_count": len(graph.children_of.get(eid, [])),
        })
    out.sort(key=lambda r: (not r["sanctioned"], not r["pep"], r["name"]))
    return out


# ---------------------------------------------------------------------------
# Markdown memo — the paste-into-case-note deliverable.
# ---------------------------------------------------------------------------


def to_markdown(report: Dict[str, Any]) -> str:
    if "report" in report:
        r = report["report"]
    else:
        r = report
    ent = r["target"]
    lines: List[str] = []
    lines.append(f"# Beneficial Ownership Memo — {ent['name']}")
    lines.append("")
    lines.append(f"- **Entity ID:** `{ent['id']}`")
    lines.append(f"- **Kind:** {ent['kind']} · **Jurisdiction:** "
                 f"{ent['jurisdiction']} "
                 f"(risk {ent['jurisdiction_risk']:.2f})")
    if ent.get("incorporation_year"):
        lines.append(f"- **Incorporated:** {ent['incorporation_year']}")
    if ent.get("shell_indicators"):
        lines.append("- **Shell indicators:** "
                     + ", ".join(ent["shell_indicators"]))
    lines.append(f"- **Verdict:** {r['verdict']['label']} — "
                 f"{r['verdict']['reason']}")
    lines.append(f"- **Opacity:** {r['opacity']['score']} "
                 f"({r['opacity']['band']}) · "
                 f"max chain depth {r['opacity'].get('max_depth', 0)}")
    lines.append("")
    lines.append("## Beneficial owners")
    lines.append("")
    if r["ubos"]:
        lines.append("| Controller | Kind | Jurisdiction | Aggregate | Flags |")
        lines.append("|---|---|---|---:|---|")
        for u in r["ubos"]:
            flags = []
            if u["sanctioned"]:
                flags.append("SANCTIONED")
            if u["pep"]:
                flags.append("PEP")
            if u.get("substantial_control"):
                flags.append("SUBSTANTIAL_CONTROL")
            lines.append(
                f"| {u['name']} | {u['kind']} | {u['jurisdiction']} | "
                f"{u['aggregate']*100:.1f}% | {', '.join(flags) or '—'} |"
            )
    else:
        lines.append("_No natural person meets the 25% aggregate threshold._")
    lines.append("")
    lines.append("## Sanctions reach (OFAC 50% rule)")
    lines.append("")
    lines.append(f"- **Aggregate blocked control:** "
                 f"{r['sanctions']['aggregate']*100:.1f}% — "
                 f"**{r['sanctions']['verdict']}**")
    for h in r["sanctions"]["hits"][:5]:
        lines.append(
            f"  - `{h['root']}` — {h['name']} — {h['aggregate']*100:.1f}% "
            f"({h['reach_code']})"
        )
    if r["pep"]["count"]:
        lines.append("")
        lines.append("## PEP nexus")
        lines.append("")
        for h in r["pep"]["hits"][:5]:
            lines.append(
                f"- `{h['root']}` — {h['name']} — "
                f"{h['aggregate']*100:.1f}% ({h['reach_code']})"
            )
    lines.append("")
    lines.append("## Ownership paths (top 6)")
    lines.append("")
    lines.append("| # | Root | Chain | Depth | Weight |")
    lines.append("|---:|---|---|---:|---:|")
    all_paths: List[Dict[str, Any]] = []
    for c in r["controllers"]:
        for p in c["paths"]:
            all_paths.append({"controller": c["name"], **p})
    all_paths.sort(key=lambda p: (-p["weight"], p["depth"]))
    for i, p in enumerate(all_paths[:6], 1):
        chain = " → ".join(p["chain"])
        lines.append(f"| {i} | {p['controller']} | {chain} | "
                     f"{p['depth']} | {p['weight']*100:.2f}% |")
    lines.append("")
    lines.append("## Opacity components")
    lines.append("")
    lines.append("| Component | Weight | Value |")
    lines.append("|---|---:|---:|")
    for k, v in r["opacity"]["components"].items():
        lines.append(f"| {k} | {OPACITY_WEIGHTS[k]:.2f} | {v:.3f} |")
    lines.append("")
    if r["cycles_touching"]:
        lines.append("## Cycles detected")
        lines.append("")
        for cyc in r["cycles_touching"]:
            lines.append(f"- {' → '.join(cyc)}")
        lines.append("")
    lines.append(f"_Engine: {ENGINE_VERSION} — deterministic, "
                 f"reproducible from the cited paths._")
    return "\n".join(lines)


__all__ = [
    "ENGINE_VERSION",
    "UBO_THRESHOLD",
    "UBO_SCREEN_THRESHOLD",
    "OFAC_BLOCK_THRESHOLD",
    "OFAC_REPORT_THRESHOLD",
    "PEP_EDD_THRESHOLD",
    "PEP_LINK_THRESHOLD",
    "OPACITY_WEIGHTS",
    "OPACITY_BLOCKED_BAND",
    "MAX_TRAVERSAL_DEPTH",
    "MAX_PATHS_PER_TARGET",
    "JURISDICTION_RISK",
    "DEFAULT_JURISDICTION_RISK",
    "VERDICT_LABEL",
    "VERDICT_TONE",
    "ENTITY_KINDS",
    "EDGE_TYPES",
    "SHELL_INDICATORS",
    "get_rules",
    "analyze",
    "sample",
    "entity_report",
    "reach_report",
    "controller_candidates",
    "to_markdown",
]
