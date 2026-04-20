# 🧪 LLM Playground

A fast, opinionated, side-by-side playground for **OpenAI · Anthropic · Google ·
your custom August stack**. Compare what *Sonnet* says vs what *GPT-4o* says on
the same prompt — with latency, token, and **USD cost** all on screen.

> Built to be the tool I actually want at my desk when I'm picking which model
> to ship with: "same prompt, every lane, one click, one dashboard."

![UI Screenshot](Playground_img.png)

---

## ✨ What's inside

### 🟣 Playground — the single-model workbench
A stateful chat surface with role-by-role message editing, `temperature` /
`top-p` / `max_tokens` sliders, system-prompt injection, reasoning-effort
presets for `o1`/`o3`/`opus`, "run from here" branching, JSON import/export,
August custom-pipeline mode, and a Settings drawer for managing every provider
API key without touching `.env`.

### 🟦 Compare — one prompt, every model, in parallel  *(today's big move)*
A new route that fans the same prompt out across up to 6 (provider, model)
combinations **concurrently** via a threadpool on the backend, then renders
each response in its own card with:

- 👑 **Cheapest** and ⚡ **Fastest** winner badges auto-computed across runs.
- **Live cost calculation** per response — input × output tokens against a
  baked-in pricing table that covers every flagship model across the four
  providers. Also shown as a gradient bar chart so you can see the spread at
  a glance.
- **Latency comparison** as a second bar chart (fastest = shortest bar).
- **Token breakdown** (input · output · total) per card.
- Summary strip: success count, total cost, parallel wall-clock, winner model.
- **Example prompts** to seed interesting comparisons in one click.
- **Export JSON** — the full comparison (prompts, specs, results, summary)
  as a single file, so you can paste it into a PR description or a blog post.

### 💰 Honest pricing intelligence
A dedicated pricing module mirrored on both backend and frontend
(`services/pricing.py` / `lib/pricing.js`) with per-1M-token input/output
rates for every supported model, plus conservative per-provider fallbacks so
cost is never just `$0`.

---

## 🏗 Architecture

```
LLM_Playground/
├── llm_playground_backend/        # Flask + threadpool fan-out
│   └── src/
│       ├── main.py                # app factory, blueprint registration
│       ├── routes/
│       │   ├── llm.py             # single-model /chat, model list, params
│       │   ├── compare.py         # NEW · parallel /compare endpoint
│       │   └── keys.py            # .env-backed key management
│       ├── providers/             # OpenAI · Anthropic · Gemini · August
│       └── services/
│           └── pricing.py         # NEW · model → $/1M tokens table
│
└── llm_playground_frontend/       # React 19 + Vite + Tailwind v4
    └── src/
        ├── main.jsx               # router shell
        ├── components/
        │   ├── NavShell.jsx       # NEW · global dark nav w/ ambient gradients
        │   └── compare/
        │       └── RunCard.jsx    # NEW · per-model response panel
        ├── pages/
        │   └── Compare.jsx        # NEW · side-by-side comparison page
        ├── lib/
        │   └── pricing.js         # NEW · client-side cost estimator
        ├── services/api.js        # adds compareRun()
        └── App.jsx                # existing Playground page
```

---

## 🚀 Quickstart

```bash
# backend
cd LLM_Playground/llm_playground_backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python src/main.py                     # listens on :5050

# frontend (new terminal)
cd LLM_Playground/llm_playground_frontend
pnpm install    # or npm install
pnpm dev        # http://localhost:5173
```

Open the app, hit the **Compare** tab, pick your models, and click **Run All**.

### 🔐 API keys
Click the gear icon in the Playground header and paste in:

| Provider   | Env var                                   |
|------------|-------------------------------------------|
| OpenAI     | `OPENAI_API_KEY`                          |
| Anthropic  | `CLAUDE_API_KEY` / `ANTHROPIC_API_KEY`    |
| Google     | `GEMINI_API_KEY`                          |
| August     | `AUGUST_API_BASE_URL`, `AUGUST_API_KEY`   |

Everything is written to the backend `.env` with basic quoting, so you never
have to restart the server.

---

## 🔌 Compare API

```http
POST /api/compare
Content-Type: application/json

{
  "system_prompt": "You are a concise assistant.",
  "messages": [{ "role": "user", "content": "Explain self-attention in 80 words." }],
  "runs": [
    { "provider": "OpenAI",    "model": "gpt-4o-mini",
      "params": { "temperature": 0.7, "max_tokens": 600 } },
    { "provider": "Anthropic", "model": "claude-3-5-haiku-20241022",
      "params": { "temperature": 0.7, "max_tokens": 600 } },
    { "provider": "Google",    "model": "gemini-1.5-flash",
      "params": { "temperature": 0.7, "max_tokens": 600 } }
  ]
}
```

Response:

```json
{
  "success": true,
  "results": [
    {
      "provider": "OpenAI", "model": "gpt-4o-mini",
      "content": "Self-attention is...",
      "status": "success",
      "input_tokens": 23, "output_tokens": 142, "total_tokens": 165,
      "latency_sec": 1.31,
      "cost": {
        "input_rate_per_1m": 0.15, "output_rate_per_1m": 0.60,
        "input_cost_usd": 0.000003, "output_cost_usd": 0.000085,
        "total_cost_usd": 0.000088
      }
    }
  ],
  "summary": {
    "run_count": 3, "success_count": 3,
    "cheapest_index": 2, "fastest_index": 0,
    "total_cost_usd": 0.00041, "wall_clock_sec": 1.42
  }
}
```

Runs fan out concurrently — total wall clock ≈ the slowest lane, not the sum.

---

## 🛣 Roadmap

- Streaming responses for both single-model and compare lanes (SSE)
- Persisted prompt library with tags & search
- Human eval: thumbs-up/down on each lane, leaderboard across sessions
- Cost budgets & alerts when a run exceeds a threshold

---

## 👨‍💻 Author

Built with ❤️ by **Aryan D Haritsa** · PES University · AI / full-stack.
