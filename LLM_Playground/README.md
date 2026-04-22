# 🧪 LLM Playground

A side‑by‑side LLM evaluation studio. Run the **same prompt** against
multiple frontier models in parallel and see who wins on **speed**,
**cost**, and **content** — all in one view.

Built with a Flask backend and a React + Tailwind + shadcn/ui frontend.

---

## ✨ What's new — Arena mode

> Send one prompt, get N answers, pick a winner.

- **Parallel fan‑out** to any combination of OpenAI, Anthropic and Google
  models (up to 6 candidates).
- **Per‑card metrics**: latency · total tokens · estimated **$ cost**
  (pricing table tracked in `backend/src/pricing.py`).
- **Automatic winner badges**: 🏆 fastest · 💰 cheapest · 📝 most verbose.
- **Headline tiles**: models tested, successes, wall‑clock runtime, total spend.
- **One‑click copy** per response, or **export the full comparison** as JSON.
- Shared system prompt + parameters, so every candidate sees identical
  instructions.

Under the hood this is a new `POST /api/compare` endpoint that runs each
provider in a `ThreadPoolExecutor`, catches per‑candidate errors so a
missing API key never kills the siblings, and decorates the response with
the pricing estimates from the shared cost module.

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
candidates, type a prompt, hit **Run Arena**.

## 🗺 API surface

| Method | Path                   | Purpose                                                |
|--------|------------------------|--------------------------------------------------------|
| GET    | `/api/health`          | liveness probe                                         |
| GET    | `/api/providers`       | provider → availability + known models                 |
| GET    | `/api/models/:provider`| model list (dynamic when provider supports listing)    |
| GET    | `/api/parameters/:prov`| supported params + `supports_json_mode` / `…reasoning…` |
| GET    | `/api/pricing`         | per‑model input/output $/1M token table                |
| POST   | `/api/chat`            | single‑provider chat (returns `cost_usd` in debug)     |
| POST   | `/api/compare`         | **Arena** — parallel fan‑out, winners, total cost      |
| POST   | `/api/export`          | canonicalise a chat session as JSON                    |
| GET    | `/api/key-status`      | masked key presence per provider                       |
| POST   | `/api/save-keys`       | persist keys to `.env`                                 |

## 📂 Project structure

```
LLM_Playground/
├── llm_playground_backend/
│   └── src/
│       ├── main.py                  # Flask app + CORS + static host
│       ├── pricing.py               # per-model $/1M token table
│       ├── routes/
│       │   ├── llm.py               # /chat, /compare, /pricing, /models, /export
│       │   ├── keys.py              # /key-status, /save-keys
│       │   └── user.py
│       ├── providers/               # OpenAI / Anthropic / Gemini / August
│       └── models/
└── llm_playground_frontend/
    ├── src/
    │   ├── App.jsx                  # Universal + August + Arena modes
    │   ├── services/api.js          # typed client, compare + pricing
    │   └── components/ui/           # shadcn primitives
    └── vite.config.js
```

## 🛤 Roadmap

- Response streaming (SSE) with live tokens/sec per card
- Blind A/B voting → ELO leaderboard across saved runs
- Prompt library with diff'd versions
- Auto‑eval rubrics (LLM‑as‑judge) with exportable scoring sheets

## 👨‍💻 Author

Built with ❤️ by Aryan D Haritsa · Student @ PES University · AI &
Full‑stack enthusiast.
