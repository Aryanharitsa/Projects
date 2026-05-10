# 🧪 LLM Playground

A side‑by‑side LLM evaluation studio. Run the **same prompt** against multiple
frontier models in parallel, score them with an LLM‑as‑judge, **vote on them
yourself**, and keep **every run** in a queryable, comparable history — all
in one view.

Built with a Flask backend and a React + Tailwind + shadcn/ui frontend.

---

## 🆕 What's new — Personal Chatbot Arena (blind A/B voting → ELO)

> Round‑4. Your own LMSYS‑style arena, fed by your own runs.

A new **Vote** mode samples pairs from your run history with provider/model
labels hidden, you pick a winner (A · B · Tie · Both bad), and an
**ELO replay** keeps a live leaderboard. Cast a few votes and you'll see:

- A 🥇/🥈/🥉 leaderboard with rating, games, W/L/T, win-rate, and the last
  8 results as a colour-coded form strip.
- A **head-to-head matrix** (top 8 models, hue-graded win rate per cell).
- A **judge ↔ human agreement** card — for every decisive vote on a judged
  run, did your pick match the LLM judge's #1? Per-model agreement %
  included.
- A **recent votes feed** with one-click undo (the leaderboard is replayed
  every call, so undo is exact).
- Keyboard shortcuts: **`1`** A wins · **`2`** B wins · **`=`** Tie ·
  **`0`** Both bad · **`N`** next pair.

### How the math works

```
expected_a = 1 / (1 + 10^((rating_b - rating_a) / 400))
rating_a' = rating_a + K · (score_a - expected_a)
```

* `K = 24` (FIDE-blitz default · env-tunable via `LLM_ELO_K`).
* `prior = 1500` (env-tunable via `LLM_ELO_PRIOR`).
* **Tie** → score 0.5 / 0.5.
* **Both bad** → no rating change (no signal in either direction).
* The leaderboard **replays the entire vote log** on every call — so deleting
  a misclick rewinds it cleanly, and changing K reshapes the ranking
  without losing data.

### Pair sampling

`GET /api/arena/pair` walks the most recent runs (newest first), enumerates
every cross-pair within each, and biases towards **under-played** match-ups
so a power-user voter doesn't get the same pair twice in a row. The
provider/model identities never reach the client until the vote is cast —
the response surfaces them under `_truth` which the panel keeps in
component state.

### History → Vote deeplink

Every History row with ≥ 2 successful candidates now shows a **Vote**
button. Clicking it pins the Vote panel to that specific run, samples a
pair *from inside it*, and cycles to a fresh pair from the same run on
"Next" — making it easy to triple-vote a single arena run when you want
high-confidence ELO movement.

---

## 🏛️ Run History (still here · Round 3)

> Every Arena run is persisted. Filter, star, tag, re‑run, and **diff**
> any two runs side‑by‑side.

After Arena, after Judge, the run lands in **History**: prompt, system prompt,
every candidate's response with metrics, the arena winners, and — if you
clicked Judge — the rubric, verdicts, leaderboard and judge metadata.
Filter by free-text search, provider chips, judged-only, starred-only.
Hold ⌘/Ctrl + click a second row to pin it as a diff partner.

A single SQLite table `runs` (`database/history.db`, gitignored) where the
heavyweight payload lives in a JSON `payload` column and **everything we
filter, sort, or aggregate on** is mirrored as an indexed scalar column.
The Vote module's `votes` table piggy-backs on the same DB file so a single
backup captures everything.

---

## 🏛️ LLM‑as‑Judge auto‑eval (still here · Round 2)

> One prompt → N answers → an LLM judge scores them all.

Hit **Judge responses** after a run and another model scores every candidate
against a 5‑criterion rubric (Correctness · Completeness · Clarity ·
Conciseness · Format) on a 1‑5 scale. Per‑criterion bars, a 0‑100 weighted
composite, a one‑sentence rationale, a leaderboard, and a 🏅 *judge pick*
badge. Editable rubric, paranoid JSON extraction, judge cost & latency
tracked, results auto-persisted into history.

> Composite formula: `Σᵢ ((scoreᵢ − 1) / 4) · weightᵢ` × 100, where weights
> are renormalised to sum to 1 before scoring.

## ⚔️ Arena mode (still here · Round 1)

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
#   LLM_ELO_K=24               # optional (default)
#   LLM_ELO_PRIOR=1500         # optional (default)
python src/main.py              # serves on :5050

# 3. Frontend (in a second terminal)
cd ../llm_playground_frontend
pnpm install                    # or npm install --legacy-peer-deps
pnpm dev                        # Vite on :5173
```

Open `http://localhost:5173`, pick **Arena**, fan out a prompt, then flip
to **Vote** and start judging blind. **History** persists everything.

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
| GET    | `/api/history`             | paginated, filterable list of runs                     |
| GET    | `/api/history/:run_id`     | full payload for one run (responses + judge)           |
| POST   | `/api/history/:run_id/meta`| set `tag` / `note` / `starred` on a run                |
| DELETE | `/api/history/:run_id`     | delete a run                                           |
| GET    | `/api/history/stats`       | aggregate metrics + top judge winners                  |
| POST   | `/api/history/diff`        | side‑by‑side diff of two runs                          |
| GET    | `/api/arena/pair`          | **blind A/B pair** sampled from history                |
| POST   | `/api/arena/vote`          | record a vote — returns the updated leaderboard         |
| DELETE | `/api/arena/vote/:id`      | undo a vote (rewinds the ELO replay)                   |
| GET    | `/api/arena/leaderboard`   | ELO leaderboard (k / prior / since / min_games params) |
| GET    | `/api/arena/matrix`        | head‑to‑head wins matrix for top‑N                     |
| GET    | `/api/arena/agreement`     | judge ↔ human agreement % + per‑model breakdown        |
| GET    | `/api/arena/recent`        | recent votes feed                                      |
| GET    | `/api/arena/stats`         | top‑of‑page voting stats                               |
| POST   | `/api/export`              | canonicalise a chat session as JSON                    |
| GET    | `/api/key-status`          | masked key presence per provider                       |
| POST   | `/api/save-keys`           | persist keys to `.env`                                 |

### `/api/arena/pair` query params

| Name        | Type   | Notes                                                       |
|-------------|--------|-------------------------------------------------------------|
| `run_id`    | string | sample within a specific run (deeplink from History)        |
| `exclude_a` | string | model key already shown as A (de-dup refresh)               |
| `exclude_b` | string | model key already shown as B                                |

### `/api/arena/leaderboard` query params

| Name        | Type   | Notes                                                       |
|-------------|--------|-------------------------------------------------------------|
| `k`         | float  | K-factor override (default 24, env `LLM_ELO_K`)             |
| `prior`     | float  | initial rating (default 1500, env `LLM_ELO_PRIOR`)          |
| `since`     | float  | unix epoch lower bound on votes                             |
| `min_games` | int    | drop models with fewer than this many votes                 |

## 📂 Project structure

```
LLM_Playground/
├── llm_playground_backend/
│   └── src/
│       ├── main.py                  # Flask app + CORS + static host
│       ├── pricing.py               # per-model $/1M token table
│       ├── judge.py                 # rubric + LLM-as-judge engine + JSON parser
│       ├── history.py               # SQLite-backed run store + diff/stats engine
│       ├── vote_arena.py            # ⬅ NEW · ELO replay + pair sampler + agreement
│       ├── routes/
│       │   ├── llm.py               # /chat, /compare, /judge, /history/*, /arena/*, /pricing, …
│       │   ├── keys.py              # /key-status, /save-keys
│       │   └── user.py
│       ├── providers/               # OpenAI / Anthropic / Gemini / August
│       └── models/
└── llm_playground_frontend/
    ├── src/
    │   ├── App.jsx                  # Universal + August + Arena + History + Vote modes
    │   ├── services/api.js          # typed client (incl. arena*)
    │   └── components/
    │       ├── HistoryPanel.jsx     # filters · run list · detail · compare-two-runs
    │       ├── VotePanel.jsx        # ⬅ NEW · blind compare + leaderboard + matrix + agreement
    │       └── ui/                  # shadcn primitives
    └── vite.config.js
```

## 🛤 Roadmap

- Response streaming (SSE) with live tokens/sec per card
- ~~Blind A/B voting → ELO leaderboard across saved runs~~ ✅ shipped
- Prompt library with diff'd versions
- ~~Auto‑eval rubrics (LLM‑as‑judge) with exportable scoring sheets~~ ✅ shipped
- ~~Persisted judged runs as a queryable history~~ ✅ shipped
- Multi‑judge consensus (run K judges, average scores, surface disagreement)
- Saved comparisons → permalinks
- Vote-driven prompt regeneration ("which prompts move ELO most?")

## 👨‍💻 Author

Built with ❤️ by Aryan D Haritsa · Student @ PES University · AI &
Full‑stack enthusiast.
