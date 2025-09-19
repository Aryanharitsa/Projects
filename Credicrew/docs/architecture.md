# Architecture (MVP)

- Backend: FastAPI + SQLAlchemy + pgvector-ready Postgres
- Data: Local Docker Postgres for development
- Frontend/ML: Not included yet (stubs present)

Initial endpoint: GET /health -> {"status": "ok"}

Add models and routes incrementally:
- Companies, Users, Roles, Candidates
- Matching service with explainable scores
