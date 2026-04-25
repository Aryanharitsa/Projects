"""SAR (Suspicious Activity Report) draft generator.

Renders a compliance-officer-ready narrative + structured payload from
a `risk.AccountReport`-shaped dict. The output mirrors the shape of an
FIU-IND STR/CTR submission but is intentionally generic so it can be
adapted to FinCEN SAR or AUSTRAC SMR by swapping the template.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, List


def _bullet(factor: Dict[str, Any]) -> str:
    if factor.get("points", 0) <= 0:
        return ""
    return f"- **{factor['name']}** ({factor['points']:.1f}/{factor['weight']}): {factor['detail']}"


def _draft_id(account_id: str, ts: str) -> str:
    h = hashlib.sha256(f"{account_id}|{ts}".encode()).hexdigest()
    return "SAR-" + h[:10].upper()


def render_sar(account_report: Dict[str, Any], analyst: str = "TITAN-AUTOMATED") -> Dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    sar_id = _draft_id(account_report["account_id"], now)
    triggered = [f for f in account_report.get("factors", []) if f.get("points", 0) > 0]

    inbound = account_report.get("inbound_total", 0)
    outbound = account_report.get("outbound_total", 0)
    edges = account_report.get("edges", [])
    period_start = min((e["timestamp"] for e in edges), default=now)
    period_end = max((e["timestamp"] for e in edges), default=now)

    bullets = "\n".join(b for b in (_bullet(f) for f in triggered) if b)
    narrative = f"""# Suspicious Activity Report — Draft

**Reference**: `{sar_id}`
**Filed by (analyst)**: {analyst}
**Generated (UTC)**: {now}
**Subject account**: `{account_report['account_id']}`
**Risk score**: **{account_report['risk_score']}/100** ({account_report['band']})

## 1. Activity period
{period_start} → {period_end}

## 2. Aggregate flows
- Inbound (₹): **{inbound:,.2f}**
- Outbound (₹): **{outbound:,.2f}**
- Distinct counterparties: {account_report.get('counterparty_count', 0)}
- Transactions in scope: {len(edges)}

## 3. Triggered patterns
{bullets if bullets else '_(no individual patterns triggered above their thresholds)_'}

## 4. Recommended action
Escalate to compliance review; freeze outbound transfers above ₹10,00,000
pending KYC re-verification of subject and counterparties listed in §5.

## 5. Counterparty summary (top by value)
""" + _counterparty_table(edges, account_report["account_id"])

    return {
        "sar_id": sar_id,
        "filed_at": now,
        "analyst": analyst,
        "account_id": account_report["account_id"],
        "risk_score": account_report["risk_score"],
        "band": account_report["band"],
        "narrative_md": narrative,
        "structured": {
            "subject_account": account_report["account_id"],
            "period": {"start": period_start, "end": period_end},
            "totals": {"inbound": inbound, "outbound": outbound},
            "triggered_factors": triggered,
            "evidence": list(_collect_evidence(triggered)),
        },
    }


def _counterparty_table(edges: List[Dict[str, Any]], subject: str) -> str:
    agg: Dict[str, float] = {}
    for e in edges:
        other = e["to"] if e["from"] == subject else e["from"]
        agg[other] = agg.get(other, 0) + float(e.get("amount", 0))
    rows = sorted(agg.items(), key=lambda kv: kv[1], reverse=True)[:5]
    if not rows:
        return "_(none)_"
    lines = ["| Counterparty | Total (₹) |", "|---|---:|"]
    for name, total in rows:
        lines.append(f"| `{name}` | {total:,.2f} |")
    return "\n".join(lines)


def _collect_evidence(triggered: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for f in triggered:
        for ev in f.get("evidence", []) or []:
            out.append({"factor": f["name"], **ev})
    return out


# ----- handy CLI for ad-hoc rendering, e.g. `python -m sar < report.json`
if __name__ == "__main__":  # pragma: no cover
    import sys

    payload = json.load(sys.stdin)
    print(render_sar(payload)["narrative_md"])
