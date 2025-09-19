# Credicrew Monorepo
Credicrew is a talent intelligence platform. This repo hosts the API, web app, and ML bits.

## Run (API only for now)
python -m pip install -r backend/requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
# Visit: http://localhost:8000/health
