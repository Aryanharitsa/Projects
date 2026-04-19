# Credicrew

Credicrew is a talent-discovery tool that doesn't just list candidates — it **explains
why each one matches a role**. Type a job description in plain English and every
candidate gets a 0–100 match score with a per-factor breakdown (skills covered,
location fit, seniority alignment).

The same match logic runs in the browser (for instant UI feedback) and on the
FastAPI backend (for programmatic / agentic use), keeping the explanations
identical wherever scoring happens.

---

## Features

### Explainable matching
- Free-text query parsing: extracts **skills**, **location**, and **seniority**
  from natural prose (`"Senior backend (FastAPI + Postgres) in Bengaluru"` →
  skills `fastapi, postgres`, location `bengaluru`, seniority `senior`).
- Alias normalization: `reactjs → react`, `nodejs → node.js`,
  `bangalore → bengaluru`, `k8s → kubernetes`, etc.
- Per-candidate breakdown: matched skills, missing skills, location state
  (`full` / `partial` / `none`), seniority match.
- Score bands: **strong** (≥80), **solid** (≥60), **weak** otherwise — shown as
  coloured dot counts in the results header and as a conic-gradient ring on
  each card.

### Scoring formula
Composite score in `[0, 1]`, scaled to 0–100:

| Factor      | Weight | What it measures                                  |
|-------------|-------:|---------------------------------------------------|
| Skills      | 0.55   | Fraction of requested skills the candidate has    |
| Seniority   | 0.20   | Exact match (1.0), known-but-different (0.3), unknown (0.6) |
| Location    | 0.15   | Exact / remote (1.0), hybrid (0.5), mismatch (0.0)|
| Baseline    | 0.10   | Flat floor so a blank query still ranks sensibly  |

### Discover page
- Detected-plan chips show exactly which tokens the parser picked up.
- Min-score slider filters the deck live.
- Each `CandidateCard` ring's colour matches the score band; matched skills are
  emerald chips, missing skills are rose strike-throughs.
- `MatchExplain` popover lists every factor's contribution in points.

### Pipeline
- Save / unsave candidates (localStorage-backed).
- CV pages, candidate submission form — unchanged from the base app.

---

## Tech stack
- **Frontend:** Next.js 14 (App Router) · TypeScript · TailwindCSS
- **Backend:** FastAPI · Pydantic v2 · SQLAlchemy 2.0
- **Match engine:** pure functions, no external NLP deps — kept in lockstep
  between `frontend/src/lib/match.ts` and `backend/app/services/match.py`

---

## Getting started

```bash
# Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload   # http://127.0.0.1:8000

# Frontend (new shell)
cd frontend
npm install
npm run dev                     # http://localhost:3000
```

---

## API

### `POST /match`
Rank an arbitrary list of candidates against a natural-language query.

```bash
curl -X POST http://127.0.0.1:8000/match \
  -H 'content-type: application/json' \
  -d '{
    "query": "Senior backend (FastAPI + Postgres) in Bengaluru",
    "candidates": [
      {"id": 1, "name": "A Patel", "role": "Senior Backend Engineer",
       "location": "Bengaluru", "tags": ["fastapi","postgres"], "keywords": []},
      {"id": 2, "name": "B Kumar", "role": "Frontend Engineer",
       "location": "Remote (India)", "tags": ["react","typescript"], "keywords": []}
    ]
  }'
```

Response:
```json
{
  "plan": {"text": "...", "skills": ["fastapi","postgres"],
           "location": "bengaluru", "seniority": "senior"},
  "results": [
    {"candidate_id": 1, "name": "A Patel",
     "match": {"score": 100, "matched_skills": ["fastapi","postgres"],
               "missing_skills": [], "seniority": {...}, "location": {...},
               "factors": [...]}},
    {"candidate_id": 2, "name": "B Kumar", "match": {"score": 30, ...}}
  ]
}
```

The same breakdown powers the UI via `frontend/src/lib/match.ts`, so client and
server always agree on the explanation.

---

## Project structure

```
Credicrew/
├── backend/
│   └── app/
│       ├── main.py              # FastAPI app + CORS + routers
│       ├── routers/match.py     # POST /match
│       └── services/match.py    # Python match engine
├── frontend/
│   └── src/
│       ├── app/page.tsx         # Discover page
│       ├── components/
│       │   ├── CandidateCard.tsx
│       │   └── MatchExplain.tsx
│       └── lib/match.ts         # TS match engine (parity w/ backend)
└── docs/
```

---

## License
MIT © 2025 Credicrew
