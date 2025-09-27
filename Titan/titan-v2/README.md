# TITAN — Trusted Identity & Transaction Authentication Network

**KYC + AML in one pipeline (MVP).**  
- **KYC:** PAN PDF → OCR stub → IPFS pin → on-chain **AttestationRegistry** (doc hash + verifier + timestamp).  
- **AML:** Rule engine + FinTrace-ready model hook → risk-scored alerts with explanations → SAR draft for high-risk.

## Quickstart
```bash
cd infra
cp env.example .env  # optional — defaults work for local
docker compose up --build
```
Open **http://localhost:3000** for the UI.

**Services**
- Frontend: http://localhost:3000
- API Gateway: http://localhost:8000
- KYC Service: http://localhost:8001
- AML Service: http://localhost:8002
- IPFS Gateway: http://localhost:8080
- Hardhat Node: http://localhost:8545

## FinTrace Integration
Replace the model placeholder in `apps/ai-aml/main.py` with your FinTrace scorer. Keep the response shape intact.

## Security & Privacy (MVP)
- Only the **document hash** is written on-chain; PDFs live in IPFS.
- No PII in logs. RBAC/DB arrive in Phase 2.

## Roadmap
- Phase 2: DB persistence (Cases, Alerts), SHAP explanations, sanctions feed.
- Phase 3: ZK circuits for attestations, graph ML, OAuth.
