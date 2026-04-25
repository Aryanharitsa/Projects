# TITAN v2

**Trusted Identity & Transaction Authentication Network.**
Document-grade KYC + on-chain attestation + a deterministic, explainable AML
risk engine — wrapped in a single dark-themed Next.js console.

> Day-5 of the project rotation rebuilt this from a thin "fintrace-shim"
> demo into a self-contained, runnable product. The repo is ~124 MB lighter
> and the AML scorer no longer depends on any external ML code: every score
> is a sum of named, weighted detector contributions.

---

## What it does

| Stage | Endpoint | Notes |
|---|---|---|
| KYC ingest | `POST /kyc/verify` | PDF → SHA-256 → IPFS pin (Kubo) → on-chain attest |
| Attestation lookup | `GET  /attest/{docHash}` | Reads `AttestationRegistry.attestations[hash]` |
| Recent attestations | `GET  /attestations/recent` | Replays `Attested` events for the explorer feed |
| AML score | `POST /aml/score` | 7 detectors → 0..100 risk per account |
| AML rules | `GET  /aml/rules` | Auditor-facing dump of weights / thresholds |
| SAR draft | `POST /aml/sar` | Markdown narrative + structured payload |

The Next.js frontend at `:3000` is the human surface. It only talks to the
gateway at `:8000`, which fans out to `ai-ocr` (8001), `ai-aml` (8002), and
the Hardhat chain (8545).

---

## Risk engine, in detail

```
score(acct) = clip( Σ wᵢ · iᵢ(acct, txs) , 0..100 )
```

| Detector | Weight | Fires when … |
|---|---:|---|
| `structuring`     | 28 | ≥3 transfers in `[40k, 50k)` within 24h (CTR-evasion proxy) |
| `velocity_spike`  | 18 | recent 1h volume ≥ 5× the trailing 30d baseline rate |
| `round_trip`      | 22 | a closed cycle of length ≤4 with every leg ≥ ₹50 000 |
| `fan_in`          | 10 | distinct senders ≥ 8 |
| `fan_out`         | 10 | distinct recipients ≥ 8 |
| `high_risk_geo`   |  8 | counterparty geo ∈ FATF-style watchlist |
| `round_amount`    |  4 | ≥3 transfers ≥ ₹100 000 that are perfect ₹10 000 multiples |

Each contribution is `intensity ∈ [0,1] × weight`. Intensity uses saturating
curves so the score plateaus instead of running away on pathological inputs.
Bands: `low <30 · medium <60 · high <80 · critical`.

The full rule set is exposed at `GET /aml/rules` — drop it into a compliance
review and you have a contract you can sign.

---

## Frontend

| Route | Purpose |
|---|---|
| `/` | Dashboard hero + flow diagram + 3 feature cards + "how it fits" |
| `/aml` | Drag-drop CSV → ranked accounts, factor bars, transaction graph, SAR draft |
| `/kyc` | PDF dropzone, animated 3-stage pipeline, on-chain receipt with deep-link to explorer |
| `/attestations` | Search by `docHash`, live `Attested` event feed, click-through to detail |

Built with Next.js 14 + Tailwind + a small set of inline SVG components
(`ScoreRing`, `FactorBars`, `TxGraph`). No charting libs.

---

## Quickstart

```bash
cd infra
cp env.example .env       # optional — defaults work for local
docker compose up --build
```

Services:

- Frontend: <http://localhost:3000>
- API gateway: <http://localhost:8000/docs>
- AML engine: <http://localhost:8002/docs>
- IPFS gateway: <http://localhost:8080>
- Hardhat node: <http://localhost:8545>

The Hardhat dev account
`0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266` is preloaded with funds; the
gateway uses the well-known dev private key to sign attestation transactions.
**Don't reuse that key outside local dev.**

---

## Sanity check (no Docker)

```bash
cd apps/ai-aml
pip install -r requirements.txt
uvicorn main:app --port 8002
# in another shell:
curl -s -X POST localhost:8002/aml/score \
  -H 'Content-Type: application/json' \
  -d "$(python -c 'import csv,json,sys; rows=list(csv.DictReader(open(\"../../datasets/samples/transactions.csv\"))); [r.update(amount=float(r[\"amount\"])) for r in rows]; print(json.dumps({\"transactions\": rows}))')" \
  | python -m json.tool | head -40
```

Or just open the **AML console** in the browser — it ships with the same
sample preloaded.

---

## Layout

```
apps/
  api/         FastAPI gateway — KYC ingest, attestation lookup, AML pass-through
  ai-ocr/      PAN PDF stub — sha256 + IPFS pin
  ai-aml/      Risk engine + SAR generator (no ML deps)
  frontend/    Next.js 14 console (dark theme, glass UI)
blockchain/
  contracts/   AttestationRegistry.sol
  scripts/     deploy.ts
infra/         docker-compose for the whole stack
datasets/      sample inputs
```

## Roadmap

- **Phase 2** — DB persistence (Postgres) for cases & alerts; SHAP-style
  feature attributions layered on top of the rule engine; sanctions feed.
- **Phase 3** — Zero-knowledge attestation circuits (prove "I am attested
  by V" without revealing the docHash); GraphQL subgraph for the explorer;
  OAuth.
