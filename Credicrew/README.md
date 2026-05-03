# Credicrew

Credicrew is a talent-discovery tool that doesn't stop at "here's a ranked
list." It runs the **whole hiring loop**: parse a JD, get an explainable
shortlist, track candidates through statuses, send a tailored outreach
email, and **run the interview** with a JD-tailored prep kit and a weighted
scorecard that lands on a hire/no-hire signal — all from a dark, fast,
single-page workspace.

The same scoring + email + interview logic runs in the browser (for instant
UI feedback) and on the FastAPI backend (for programmatic / agentic use),
so plans, drafts, and composite scores are byte-for-byte identical wherever
they're generated.

---

## What's new — Interview Kit (Day 12)

The hiring loop ended at *outreach* — when a candidate flipped to
`interview` status, the app went silent. Day 12 fills that gap with a
deterministic, JD-tailored Interview Kit.

- **Tailored question bank** — From the parsed JD plan, the engine picks
  prompts out of a 13-skill bank (React, Next.js, TypeScript, FastAPI,
  Python, Postgres, MongoDB, Redis, AWS, Docker, Kubernetes, PyTorch, LLM)
  and slots each into the natural stage (technical / system design),
  alongside a universal phone-screen / behavioral set. A typical
  back-end JD produces ~18 prompts across 4 stages.
- **Weighted rubric** — 4–7 dimensions: skill-driven dims (Frontend depth,
  Backend depth, Data systems, Cloud / infra, ML systems, Language craft)
  collapse duplicate skills (`react` + `next.js` both feed *Frontend
  depth*), with Σ-weight bumped per duplicate skill. Universal dims —
  *Communication · Ownership · Collaboration · System design* — round it
  out, plus a *Scope & influence* bonus dim for senior+ roles. Weights
  renormalise so they always sum to 1.
- **Composite + recommendation** — `Σ ((rating−1)/4) · weight · 100` over
  rated dims (weights renormalise across rated dims so a half-finished
  scorecard still produces a meaningful number). Bands: ≥80 strong-hire ·
  ≥65 lean-yes · ≥50 mixed · ≥35 lean-no · else no-hire.
- **Workspace UI** — `/roles/[id]/interview/[candidateId]`. Stage stepper
  with per-stage rated/total counts; expandable question cards with
  difficulty + signal pills + collapsible follow-ups; per-stage rubric
  sliders coloured by rating; per-stage signal log (strengths / concerns)
  with quick-add; live recommendation ring + composite breakdown bar
  chart; Markdown report export.
- **Role-detail integration** — every shortlist row now shows an
  `iv · <composite>` chip in the candidate's recommendation tone the
  moment any rating is filled in, plus an *Open / Start interview* button
  that drops into the workspace. A new **Export CSV** action ships the
  whole shortlist (incl. interview composite + recommendation) for ATS
  handoff — closing another roadmap item.

---

## What's new — Recruiter Workspace

Day 7 of the rotation moved Credicrew from "ranking page" to "hiring loop."

- **Roles** — Save a JD as a Role with its own parsed plan and shortlist.
  Edit the JD, rename the role, browse fresh matches, and add candidates
  with one click. Each role lives in your browser via localStorage.
- **Pipeline statuses** — Every shortlisted candidate moves through
  `New → Outreach → Screening → Interview → Offer / Passed` via a per-row
  status select. Per-status counts and a coloured pipeline strip show
  the funnel at a glance.
- **Outreach composer** — A deterministic email generator (no LLM call)
  that pulls in the candidate's first name, the matched skills, the JD's
  pitch line, the score, and the location stance. Edit, copy subject /
  body / both, or hand off to your mail client via `mailto:`.
- **Diversity widget** — Live composition view of the current pool:
  city donut (top 5 + "Other"), seniority bars, top skill frequencies.
  Renders both on Discover and inside each Role.
- **Shareable role links** — `Share link` on a role copies a URL that
  encodes the role name, JD, and shortlist into the URL hash. Recipients
  can preview before saving to their own workspace.

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
- Score bands: **strong** (≥80), **solid** (≥60), **weak** otherwise — shown
  as coloured dot counts in the results header and as a conic-gradient ring
  on each card.

### Scoring formula
Composite score in `[0, 1]`, scaled to 0–100:

| Factor      | Weight | What it measures                                  |
|-------------|-------:|---------------------------------------------------|
| Skills      | 0.55   | Fraction of requested skills the candidate has    |
| Seniority   | 0.20   | Exact match (1.0), known-but-different (0.3), unknown (0.6) |
| Location    | 0.15   | Exact / remote (1.0), hybrid (0.5), mismatch (0.0)|
| Baseline    | 0.10   | Flat floor so a blank query still ranks sensibly  |

### Roles & pipeline
- `/roles` — list of saved roles with a per-role pipeline strip and chips
  for the parsed plan.
- `/roles/new` — paste a JD, sample loader for a quick demo, live plan
  detection.
- `/roles/[id]` — JD editor, plan chips, **Matches** tab with the
  Diversity widget, **Shortlist** tab with status select + private notes,
  delete, share.
- `/roles/share` — preview and import a role from a `data=…` hash token.

### Outreach
- `composeEmail({ role, candidate, match })` produces `{ subject, body }`.
- Subject highlights the top matched skill when available.
- Body addresses the candidate by first name, names the matched skills,
  threads in the JD pitch line, addresses the location stance, and
  optionally cites the explainable score.
- Modal is editable and offers copy-to-clipboard for subject / body / both
  plus an `Open in mail app` mailto link.

### Discover (existing)
- Detected-plan chips show exactly which tokens the parser picked up.
- Min-score slider filters the deck live.
- "Save as role" button captures the current query as a Role.
- Each `CandidateCard` ring's colour matches the score band; matched
  skills are emerald chips, missing skills are rose strike-throughs.
- `MatchExplain` popover lists every factor's contribution in points.
- Per-card **Shortlist** picker drops a candidate into any saved role.

---

## Tech stack
- **Frontend:** Next.js 14 (App Router) · TypeScript · TailwindCSS
- **Backend:** FastAPI · Pydantic v2 · SQLAlchemy 2.0
- **Match + outreach engines:** pure functions, no external NLP / LLM deps —
  kept in lockstep between
  `frontend/src/lib/{match,outreach}.ts` and
  `backend/app/services/{match,outreach}.py`.

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

### `POST /outreach`
Compose a personalized outreach email. Either pass a `jd` (parsed
server-side) or pre-parsed `plan_*` fields.

```bash
curl -X POST http://127.0.0.1:8000/outreach \
  -H 'content-type: application/json' \
  -d '{
    "role_name": "Senior Backend Engineer",
    "jd": "Senior Backend Engineer (FastAPI + Postgres) in Bengaluru. Real-time risk engine.",
    "candidate": {
      "id": 1, "name": "A Patel", "role": "Senior Backend Engineer",
      "location": "Bengaluru", "tags": ["fastapi","postgres"]
    },
    "sender": "— Aryan, Founding Recruiter"
  }'
```

Response:
```json
{
  "subject": "Quick chat about a Senior Backend Engineer role — your fastapi work caught my eye",
  "body": "Hi A,\n\nI'm reaching out about a Senior Backend Engineer opportunity — …",
  "context": {
    "role_name": "Senior Backend Engineer",
    "matched_skills": ["fastapi", "postgres"],
    "score": 100,
    "plan": {"skills": ["fastapi","postgres"], "location": "bengaluru", "seniority": "senior"}
  }
}
```

### `POST /interview/plan`
Generate a tailored interview plan (rubric + question bank + empty stage
records) from a JD or pre-parsed plan.

```bash
curl -X POST http://127.0.0.1:8000/interview/plan \
  -H 'content-type: application/json' \
  -d '{"jd": "Senior backend engineer (FastAPI + Postgres) in Bengaluru"}'
```

Returns `{ rubric: [...], questions: [...], stages: [...] }`. Rubric
weights always sum to 1.

### `POST /interview/score`
Aggregate a filled-in scorecard to a composite + recommendation.

```bash
curl -X POST http://127.0.0.1:8000/interview/score \
  -H 'content-type: application/json' \
  -d '{
    "rubric": [{"key":"backend_depth","label":"Backend depth","description":"","weight":0.25,"source":"skill"},
               {"key":"data_systems","label":"Data systems","description":"","weight":0.25,"source":"skill"},
               {"key":"system_design_skill","label":"System design","description":"","weight":0.25,"source":"skill"},
               {"key":"communication","label":"Communication","description":"","weight":0.25,"source":"communication"}],
    "stages": [{"stage":"technical","status":"done","scores":[{"key":"backend_depth","rating":4},{"key":"data_systems","rating":4}]},
               {"stage":"behavioral","status":"done","scores":[{"key":"communication","rating":5}]}]
  }'
```

Returns `{ composite, recommendation, rated_count, total_count, per_dimension }`.

### Endpoint map

| Method | Path                  | Purpose                                                 |
|-------:|-----------------------|---------------------------------------------------------|
| GET    | `/health`             | liveness                                                |
| GET    | `/candidates`         | demo candidate listing                                  |
| GET    | `/roles`              | demo role listing                                       |
| POST   | `/match`              | rank candidates against a query (explainable)           |
| POST   | `/outreach`           | compose deterministic outreach email                    |
| POST   | `/interview/plan`     | tailored rubric + question bank from JD / plan          |
| POST   | `/interview/score`    | aggregate scorecard → composite + recommendation        |

---

## Project structure

```
Credicrew/
├── backend/
│   └── app/
│       ├── main.py                 # FastAPI + CORS + routers
│       ├── routers/
│       │   ├── match.py            # POST /match
│       │   ├── outreach.py         # POST /outreach
│       │   └── interview.py        # POST /interview/{plan,score}
│       └── services/
│           ├── match.py            # explainable engine
│           ├── outreach.py         # email composer
│           └── interview.py        # rubric · question bank · scorecard
├── frontend/
│   └── src/
│       ├── app/
│       │   ├── page.tsx            # Discover (search + composition + roles)
│       │   ├── pipeline/page.tsx   # Quick-saves
│       │   └── roles/
│       │       ├── page.tsx        # Roles list
│       │       ├── new/page.tsx    # New role from JD
│       │       ├── share/page.tsx  # Import a shared role
│       │       └── [id]/
│       │           ├── page.tsx    # Role detail (JD, matches, shortlist, CSV)
│       │           └── interview/[candidateId]/page.tsx  # Interview workspace
│       ├── components/
│       │   ├── CandidateCard.tsx
│       │   ├── DiversityCard.tsx
│       │   ├── InterviewStepper.tsx
│       │   ├── MatchExplain.tsx
│       │   ├── OutreachModal.tsx
│       │   ├── QuestionCard.tsx
│       │   ├── RecommendationRing.tsx
│       │   ├── RoleCard.tsx
│       │   ├── RubricSlider.tsx
│       │   └── StatusPill.tsx
│       └── lib/
│           ├── csv.ts              # tiny RFC-4180 writer + downloader
│           ├── interview.ts        # rubric · question bank · scorecard
│           ├── match.ts            # TS match engine (parity w/ backend)
│           ├── outreach.ts         # TS email composer (parity w/ backend)
│           ├── pipeline.ts         # quick-save ids
│           └── roles.ts            # roles + shortlist + share-link state
└── docs/
```

---

## Roadmap
- Server-persisted roles (Postgres) so they survive across browsers.
- LLM-assisted JD parsing for messy real-world specs (still fall back to
  the deterministic path).
- iCal export for an "Interview" status with proposed slots.
- ~~CSV export of a shortlist for ATS handoff.~~ ✅ Day 12.
- ~~Interview kit: tailored prompts, weighted rubric, scorecard, hire/no-hire signal.~~ ✅ Day 12.

---

## License
MIT © 2025 Credicrew
