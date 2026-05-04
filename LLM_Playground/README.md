# 🧪 LLM Playground

A side‑by‑side LLM evaluation studio. Run the **same prompt** against multiple
frontier models in parallel, score them with an LLM‑as‑judge, and keep
**every run** in a queryable, comparable history — all in one view.

Built with a Flask backend and a React + Tailwind + shadcn/ui frontend.

---

## 🆕 What's new — Run History

> Every Arena run is now persisted. Filter, star, tag, re‑run, and **diff**
> any two runs side‑by‑side.

After Arena, after Judge, the run lands in **History**: prompt, system prompt,
every candidate's response with metrics, the arena winners, and — if you
clicked Judge — the rubric, verdicts, leaderboard and judge metadata. The
History tab is now a 4th sidebar mode alongside Universal / August / Arena.

### What you can do

- **Browse** every run as a row in a scrollable list, with a 0‑100 conic
  ring (judge composite if scored, neutral bot otherwise), provider dot
  strip, prompt preview, success ratio, total $, time‑since.
- **Filter** instantly by free‑text search (prompt / system / model
  fingerprint), provider chips (OpenAI / Anthropic / Google), `judged only`
  toggle, `starred only` toggle.
- **Inspect** any run: replays the original Arena cards (responses, metric
  pills, fastest/cheapest/verbose badges) plus the judge leaderboard and
  per‑card score ring + rationale.
- **Star · Tag · Note** any run for later — stored on the row, not
  client‑side.
- **Compare two runs** side‑by‑side: hold ⌘ / Ctrl + click a second row to
  pin it as the diff partner. Get a headline banner (wall time · total $ ·
  successes · top score, each with a green/red Δ pill where lower‑is‑better
  is correctly flipped) and a per‑shared‑model row showing latency Δ /
  cost Δ / response‑length Δ / judge composite Δ.
- **Re‑run** any historical prompt with one click — it loads the prompt,
  system prompt, and full candidate roster back into Arena.
- **Stats banner** at the top: total runs · total successes / total calls ·
  total spend · judged count + avg top score · avg wall time, plus a
  *Top judge winners* ribbon ranking models by how often they came #1.

### Under the hood

A single SQLite table `runs` (`database/history.db`, gitignored) where the
heavyweight payload lives in a JSON `payload` column and **everything we
filter, sort, or aggregate on** is mirrored as an indexed scalar column
(`created_at`, `prompt_hash`, `n_candidates`, `n_success`,
`total_cost_usd`, `wall_latency`, `judged`, `judge_winner`,
`judge_top_score`, `tag`, `starred`). Fast under thousands of rows without
SQLite‑JSON1 indexing tax.

`/api/compare` writes a row at the end of every fan‑out; `/api/judge`
optionally accepts a `run_id` and retro‑attaches its verdict to the existing
row, so judging is a non‑destructive append.

The diff endpoint indexes both runs' `results` by `provider:model`,
intersects the keys, and returns shared / a‑only / b‑only model lists plus
per‑model deltas. `b - a` is the convention everywhere; the frontend
inverts the colour for *lower‑is‑better* metrics (latency, cost) so
**green up‑arrow always means "B improved over A"**.

---

## 🏛️ Round‑2 — LLM‑as‑Judge auto‑eval (still here)

> One prompt → N answers → an LLM judge scores them all.

Hit **Judge responses** after a run and another model scores every candidate
against a 5‑criterion rubric (Correctness · Completeness · Clarity ·
Conciseness · Format) on a 1‑5 scale. Per‑criterion bars, a 0‑100 weighted
composite, a one‑sentence rationale, a leaderboard, and a 🏅 *judge pick*
badge.

- **Editable rubric**: add/remove criteria, tweak weights live (auto‑renormalised).
- **Pick the judge**: any provider/model in your keychain.
- **Robust JSON extraction**: tolerates ```json fences, leading prose, missing
  candidates; clamps every score to the rubric range.
- **Cost & latency of judgement** shown next to the leaderboard.
- **Judge results auto‑persist** into history alongside the Arena run.

> Composite formula: `Σᵢ ((scoreᵢ − 1) / 4) · weightᵢ` × 100, where weights
> are renormalised to sum to 1 before scoring.

## ⚔️ Round‑1 — Arena mode (still here)

- **Parallel fan‑out** to OpenAI, Anthropic, Google (up to 6 candidates).
- **Per‑card metrics**: latency · total tokens · estimated **$ cost**.
- **Surface‑metric badges**: 🏆 fastest · 💰 cheapest · 📝 most verbose.
- **Headline tiles**: models tested, successes, wall‑clock runtime, total spend.
- **One‑click copy** per response.
- Shared system prompt + parameters across every candidate.

`/api/compare` runs each provider in a `ThreadPoolExecutor` and catches
per‑candidate errors so a missing API key never kills the siblings.

---

## 🚀 Everything else

- **Universal mode** — classic chat against a single provider/model with
  conversation editing, message toggling, duplicate, reorder, "run from
  here" branching, system prompt dialog, reasoning‑effort presets for
  o‑series / opus models, drag‑and‑drop JSON import.
- **August mode** — forward payloads to a custom `August` service
  (`pkey` / `pvariables`).
- **API key manager** — masked key status per provider, in‑app save
  writing to the backend `.env`.
- **Full debug panel** — provider, model, input/output/total tokens,
  latency, request id, status, timestamp, cost.
- **Cost estimate on every single‑chat call** (not just Arena).

## 🖼️ Screenshots

![UI Screenshot](Playground_img.png)

## ⚙️ Setup

```bash
# 1. Clone and enter
git clone https://github.com/Aryanharitsa/Projects.git
cd Projects/LLM_Playground

# 2. Backend
cd llm_playground_backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# create a .env with the keys you have (any subset works):
#   OPENAI_API_KEY=...
#   ANTHROPIC_API_KEY=...
#   GEMINI_API_KEY=...
#   AUGUST_API_BASE_URL=...    # optional
#   AUGUST_API_KEY=...         # optional
python src/main.py              # serves on :5050

# 3. Frontend (in a second terminal)
cd ../llm_playground_frontend
pnpm install                    # or npm install
pnpm dev                        # Vite on :5173
```

Open `http://localhost:5173`, pick **Arena** in the sidebar, add 2–6
candidates, type a prompt, hit **Run Arena** — then flip to **History** to
see it land.

## 🗺 API surface

| Method | Path                       | Purpose                                                |
|--------|----------------------------|--------------------------------------------------------|
| GET    | `/api/health`              | liveness probe                                         |
| GET    | `/api/providers`           | provider → availability + known models                 |
| GET    | `/api/models/:provider`    | model list (dynamic when provider supports listing)    |
| GET    | `/api/parameters/:prov`    | supported params + `supports_json_mode` / `…reasoning…` |
| GET    | `/api/pricing`             | per‑model input/output $/1M token table                |
| GET    | `/api/rubric`              | default judge rubric (criteria + weights)              |
| POST   | `/api/chat`                | single‑provider chat (returns `cost_usd` in debug)     |
| POST   | `/api/compare`             | **Arena** — parallel fan‑out, winners, total cost      |
| POST   | `/api/judge`               | **LLM‑as‑judge** — score Arena responses with rubric   |
| GET    | `/api/history`             | **paginated, filterable list of runs**                 |
| GET    | `/api/history/:run_id`     | full payload for one run (responses + judge)           |
| POST   | `/api/history/:run_id/meta`| set `tag` / `note` / `starred` on a run                |
| DELETE | `/api/history/:run_id`     | delete a run                                           |
| GET    | `/api/history/stats`       | aggregate metrics + top judge winners                  |
| POST   | `/api/history/diff`        | side‑by‑side diff of two runs                          |
| POST   | `/api/export`              | canonicalise a chat session as JSON                    |
| GET    | `/api/key-status`          | masked key presence per provider                       |
| POST   | `/api/save-keys`           | persist keys to `.env`                                 |

### `/api/history` query params

| Name      | Type   | Notes                                                        |
|-----------|--------|--------------------------------------------------------------|
| `q`       | string | substring match across prompt / system / model fingerprint   |
| `model`   | string | substring match in the comma‑joined model list               |
| `provider`| string | match runs that included this provider                       |
| `judged`  | bool   | `1` → only runs that were scored                             |
| `starred` | bool   | `1` → only starred runs                                      |
| `tag`     | string | exact tag match                                              |
| `since`   | float  | unix epoch lower bound                                       |
| `before`  | float  | unix epoch upper bound                                       |
| `limit`   | int    | default 50, max 500                                          |
| `offset`  | int    | row offset                                                   |

## 📂 Project structure

```
LLM_Playground/
├── llm_playground_backend/
│   └── src/
│       ├── main.py                  # Flask app + CORS + static host
│       ├── pricing.py               # per-model $/1M token table
│       ├── judge.py                 # rubric + LLM-as-judge engine + JSON parser
│       ├── history.py               # SQLite-backed run store + diff/stats engine
│       ├── routes/
│       │   ├── llm.py               # /chat, /compare, /judge, /history/*, /pricing, …
│       │   ├── keys.py              # /key-status, /save-keys
│       │   └── user.py
│       ├── providers/               # OpenAI / Anthropic / Gemini / August
│       └── models/
└── llm_playground_frontend/
    ├── src/
    │   ├── App.jsx                  # Universal + August + Arena + History modes
    │   ├── services/api.js          # typed client
    │   └── components/
    │       ├── HistoryPanel.jsx     # filters · run list · detail · compare-two-runs
    │       └── ui/                  # shadcn primitives
    └── vite.config.js
```

## 🛤 Roadmap

- Response streaming (SSE) with live tokens/sec per card
- Blind A/B voting → ELO leaderboard across saved runs
- Prompt library with diff'd versions
- ~~Auto‑eval rubrics (LLM‑as‑judge) with exportable scoring sheets~~ ✅ shipped
- ~~Persisted judged runs as a queryable history~~ ✅ shipped
- Multi‑judge consensus (run K judges, average scores, surface disagreement)
- Saved comparisons → permalinks (next move)

## 👨‍💻 Author

Built with ❤️ by Aryan D Haritsa · Student @ PES University · AI &
Full‑stack enthusiast.
