# TITAN — Trusted Identity & Transaction Authentication Network

> KYC + on-chain attestation + **explainable** AML risk scoring, in one
> deterministic pipeline. No ML black box, no third-party scorer.

The full implementation lives in [`./titan-v2`](./titan-v2). Open that
directory's README for the architecture, run instructions, and API surface.

## Why TITAN exists

Most "compliance-tech" demos either (a) wrap an opaque ML model that nobody
can audit, or (b) skip the on-chain piece and become yet another rules
sandbox. TITAN does the boring middle path well: every artefact has a
verifiable receipt, every alert has a reason, and the whole thing runs
locally on `docker compose up`.

```
PDF ──► sha256 ──► IPFS pin ──► AttestationRegistry.attest()
                                    │
                                    ▼
                              on-chain receipt
                                    ▲
                       Attestation Explorer (UI)
```

```
transactions.csv ─► 7 detectors ─► weighted score ─► band ─► SAR draft
```

## Design choices

- **Deterministic AML.** Same input → same output. No model weights to
  re-train, no probabilistic drift to explain to an auditor.
- **One-origin frontend.** The Next.js app talks only to the gateway
  (`:8000`). The gateway is the trust boundary; everything else is internal.
- **Doc hash, not document.** PDFs live in IPFS; only the digest is on
  chain. Revealing a document is opt-in and externally controlled.

## Quickstart

```bash
cd titan-v2/infra
cp env.example .env
docker compose up --build
# UI:    http://localhost:3000
# API:   http://localhost:8000/docs
# AML:   http://localhost:8002/docs
# Chain: http://localhost:8545
```
