Minimal working API for the Credicrew project. Frontend and ML can be added later.

Minimal working API for the Credicrew project. Frontend and ML can be added later.

1) Create a venv and install deps
   python3 -m venv Credicrew/backend/.venv
   source Credicrew/backend/.venv/bin/activate
   python -m pip install -r Credicrew/backend/requirements.txt

2) Configure env
   cp Credicrew/.env.example Credicrew/.env

3) Start Postgres (Docker)
   docker run --name credicrew-pg -d -p 5432:5432 \
     -e POSTGRES_DB=credicrew -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=postgres \
     ankane/pgvector:0.5.1

4) Run the API
   cd Credicrew/backend
   source .venv/bin/activate
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

5) Health check
   curl http://localhost:8000/health


## Project Structure

Credicrew/
  backend/        FastAPI app (health endpoint)
  docs/           Documentation
  ml/             Notebooks and pipelines (placeholder)
  .env.example    Example environment file
  .gitignore

## Next
- Add endpoints for roles, candidates, matching
- Add seed scripts and tests
