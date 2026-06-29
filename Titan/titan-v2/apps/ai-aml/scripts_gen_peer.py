"""Generator for the bundled peer-lens demo portfolio.

Run from ``apps/ai-aml`` with ``python3 scripts_gen_peer.py`` to (re)create
``data/peer_portfolio.json``. Deterministic — seeded RNG so the bundled
fixture is reproducible byte-for-byte across hosts.

The portfolio is designed so that *every cohort* contains at least one
*planted* outlier the engine should catch on first run:

  * VASP/crypto cohort in BS — one wallet with 20× peer volume + heavy
    cross-border share (severe).
  * Export/import SMEs in SG — one with 4× cross-border + 6× cash share
    (outlier).
  * Retail in IN — one with weekend/night-heavy activity (drifting).
  * Wealth-mgmt in CH — one client with abnormally low tx_count +
    abnormally high p95 amount (severe).
  * Real-estate in AE — one customer with extreme cash share +
    counterparty concentration (severe).
  * Plus ~30 well-behaved customers that should land in ``aligned``.
"""

from __future__ import annotations

import json
import os
import random
from datetime import datetime, timedelta, timezone

NOW = datetime(2026, 6, 16, 12, 0, 0, tzinfo=timezone.utc)
random.seed(20260616)


def _ts(days_ago_min: int, days_ago_max: int, *, night: bool = False, weekend: bool = False) -> str:
    days_ago = random.uniform(days_ago_min, days_ago_max)
    dt = NOW - timedelta(days=days_ago)
    if night:
        dt = dt.replace(hour=random.choice([23, 0, 1, 2, 3, 4, 5]))
    if weekend and dt.weekday() < 5:
        offset = (5 - dt.weekday()) + random.randint(0, 1)
        dt = dt + timedelta(days=offset)
    return dt.isoformat()


def _customer(cid, name, industry, domicile, accounts=None):
    return {
        "customer_id": cid,
        "display_name": name,
        "industry": industry,
        "domicile": domicile,
        "accounts": accounts or [cid],
    }


def _make_txs(account, count, *, geo_pool, amount_low, amount_high,
              cross_border_pct=0.05, cash_pct=0.05, night_pct=0.05, weekend_pct=0.15,
              counterparty_pool=None, counterparty_concentration=0.0,
              days_back_low=0, days_back_high=30):
    txs = []
    cp_pool = counterparty_pool or [f"CP-{account}-{i:02d}" for i in range(1, 18)]
    for _ in range(count):
        is_cross = random.random() < cross_border_pct
        geo = random.choice([g for g in geo_pool if g != geo_pool[0]]) if is_cross else geo_pool[0]
        is_cash = random.random() < cash_pct
        is_night = random.random() < night_pct
        is_weekend = random.random() < weekend_pct
        if counterparty_concentration > 0 and random.random() < counterparty_concentration:
            cp = cp_pool[0]
        else:
            cp = random.choice(cp_pool)
        amt = round(random.uniform(amount_low, amount_high), 2)
        txs.append({
            "account_id": account,
            "counterparty": cp,
            "amount": amt,
            "timestamp": _ts(days_back_low, days_back_high, night=is_night, weekend=is_weekend),
            "channel": "cash" if is_cash else random.choice(["wire", "ach", "card", "online"]),
            "geo": geo,
        })
    return txs


# ---------------------------------------------------------------------------
# Cohort 1 — Export/import SMEs in SG
# ---------------------------------------------------------------------------

customers = []
transactions = []

EXPORT_BASE = {"geo_pool": ["SG", "MY", "ID", "PH", "VN", "AU"],
               "amount_low": 4_000, "amount_high": 60_000,
               "cross_border_pct": 0.25, "cash_pct": 0.04,
               "night_pct": 0.05, "weekend_pct": 0.16}

for i in range(8):
    cid = f"SGEX-{i:03d}"
    customers.append(_customer(cid, f"Lion Maritime SME #{i+1}", "export_import", "SG"))
    transactions += _make_txs(cid, random.randint(34, 56), **EXPORT_BASE)

# Outlier #1 — extreme cash + cross-border share
cid = "SGEX-901"
customers.append(_customer(cid, "Trident Exports Pte", "export_import", "SG"))
transactions += _make_txs(
    cid, 42,
    geo_pool=["SG", "RU", "IR", "MM"],
    amount_low=9_000, amount_high=85_000,
    cross_border_pct=0.85, cash_pct=0.45,
    night_pct=0.08, weekend_pct=0.18,
)

# Outlier #2 — abnormally high volume + counterparty concentration
cid = "SGEX-902"
customers.append(_customer(cid, "Aurelia Shell Limited", "export_import", "SG"))
transactions += _make_txs(
    cid, 70,
    geo_pool=["SG", "AE", "CY", "RU"],
    amount_low=18_000, amount_high=240_000,
    cross_border_pct=0.55, cash_pct=0.05,
    counterparty_pool=["AURELIA-PRIME-01", "AURELIA-PRIME-02"] + [f"CP-{i}" for i in range(15)],
    counterparty_concentration=0.78,
    night_pct=0.07, weekend_pct=0.18,
)

# ---------------------------------------------------------------------------
# Cohort 2 — Retail banking in IN
# ---------------------------------------------------------------------------

RETAIL_BASE = {"geo_pool": ["IN", "AE", "US", "SG"],
               "amount_low": 200, "amount_high": 8_000,
               "cross_border_pct": 0.04, "cash_pct": 0.18,
               "night_pct": 0.07, "weekend_pct": 0.22}

for i in range(10):
    cid = f"INRET-{i:03d}"
    customers.append(_customer(cid, f"Devraj Patel #{i+1}", "retail_banking", "IN"))
    transactions += _make_txs(cid, random.randint(22, 48), **RETAIL_BASE)

# Outlier — night/weekend heavy + cash heavy
cid = "INRET-901"
customers.append(_customer(cid, "Suresh Kumar Walk-in", "retail_banking", "IN"))
transactions += _make_txs(
    cid, 36,
    geo_pool=["IN", "AE", "TR", "RU"],
    amount_low=1_500, amount_high=22_000,
    cross_border_pct=0.22, cash_pct=0.62,
    night_pct=0.42, weekend_pct=0.55,
)

# ---------------------------------------------------------------------------
# Cohort 3 — VASP / crypto in BS (Bahamas)
# ---------------------------------------------------------------------------

VASP_BASE = {"geo_pool": ["BS", "US", "EU", "SG", "JP"],
             "amount_low": 12_000, "amount_high": 280_000,
             "cross_border_pct": 0.55, "cash_pct": 0.02,
             "night_pct": 0.30, "weekend_pct": 0.32}

for i in range(7):
    cid = f"BSVASP-{i:03d}"
    customers.append(_customer(cid, f"Atlantis VASP #{i+1}", "vasp_crypto", "BS"))
    transactions += _make_txs(cid, random.randint(34, 60), **VASP_BASE)

# Severe — 20× peer volume + IR/KP heavy
cid = "BSVASP-901"
customers.append(_customer(cid, "Crescent Maritime VASP", "vasp_crypto", "BS"))
transactions += _make_txs(
    cid, 95,
    geo_pool=["BS", "RU", "IR", "KP", "CY"],
    amount_low=180_000, amount_high=1_400_000,
    cross_border_pct=0.92, cash_pct=0.01,
    night_pct=0.40, weekend_pct=0.38,
)

# ---------------------------------------------------------------------------
# Cohort 4 — Wealth-management in CH (Switzerland)
# ---------------------------------------------------------------------------

WEALTH_BASE = {"geo_pool": ["CH", "DE", "FR", "GB", "US"],
               "amount_low": 80_000, "amount_high": 400_000,
               "cross_border_pct": 0.40, "cash_pct": 0.005,
               "night_pct": 0.04, "weekend_pct": 0.08}

for i in range(8):
    cid = f"CHWEA-{i:03d}"
    customers.append(_customer(cid, f"Helvetia Wealth Client #{i+1}", "wealth_mgmt", "CH"))
    transactions += _make_txs(cid, random.randint(12, 28), **WEALTH_BASE)

# Severe — low tx_count + extreme p95 amount
cid = "CHWEA-901"
customers.append(_customer(cid, "Pyongyang Horizon Trust", "wealth_mgmt", "CH"))
transactions += _make_txs(
    cid, 4,
    geo_pool=["CH", "RU", "IR", "AE"],
    amount_low=2_500_000, amount_high=4_800_000,
    cross_border_pct=0.95, cash_pct=0.0,
    night_pct=0.40, weekend_pct=0.45,
)

# ---------------------------------------------------------------------------
# Cohort 5 — Real estate in AE (Dubai)
# ---------------------------------------------------------------------------

REAL_BASE = {"geo_pool": ["AE", "IN", "RU", "GB", "PK"],
             "amount_low": 25_000, "amount_high": 220_000,
             "cross_border_pct": 0.30, "cash_pct": 0.06,
             "night_pct": 0.05, "weekend_pct": 0.20}

for i in range(7):
    cid = f"AEREA-{i:03d}"
    customers.append(_customer(cid, f"Burj Holdings Estate #{i+1}", "real_estate", "AE"))
    transactions += _make_txs(cid, random.randint(20, 38), **REAL_BASE)

# Severe — extreme cash + counterparty concentration
cid = "AEREA-901"
customers.append(_customer(cid, "Volkov-Baranov Properties", "real_estate", "AE"))
transactions += _make_txs(
    cid, 32,
    geo_pool=["AE", "RU", "BY", "TR"],
    amount_low=180_000, amount_high=750_000,
    cross_border_pct=0.80, cash_pct=0.58,
    counterparty_pool=["VOLKOV-PRIME-1", "VOLKOV-PRIME-2"] + [f"CP-{i}" for i in range(13)],
    counterparty_concentration=0.85,
    night_pct=0.18, weekend_pct=0.32,
)

# ---------------------------------------------------------------------------
# Cohort 6 — Manufacturing in DE (additional cohort, all aligned by design)
# ---------------------------------------------------------------------------

MFG_BASE = {"geo_pool": ["DE", "FR", "IT", "PL", "CZ"],
            "amount_low": 6_000, "amount_high": 75_000,
            "cross_border_pct": 0.18, "cash_pct": 0.02,
            "night_pct": 0.03, "weekend_pct": 0.06}

for i in range(8):
    cid = f"DEMFG-{i:03d}"
    customers.append(_customer(cid, f"Rheinland Werke GmbH #{i+1}", "manufacturing", "DE"))
    transactions += _make_txs(cid, random.randint(28, 46), **MFG_BASE)

# ---------------------------------------------------------------------------
# Persist
# ---------------------------------------------------------------------------

payload = {
    "$schema": "https://titan.local/peer/portfolio.v1",
    "name": "Peer Lens demo portfolio",
    "version": "1.0.0",
    "published": NOW.date().isoformat(),
    "description": (
        "Six-cohort synthetic portfolio with planted outliers in each peer "
        "group (cash-heavy export/import, structuring-pattern retail, "
        "high-volume VASP, low-count wealth client, cash-heavy real estate). "
        "All transaction timestamps are in the last 30 days."
    ),
    "customers": customers,
    "transactions": transactions,
}

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "peer_portfolio.json")
with open(OUT, "w") as fh:
    json.dump(payload, fh, indent=2)

print(f"wrote {OUT}: {len(customers)} customers, {len(transactions)} transactions")
