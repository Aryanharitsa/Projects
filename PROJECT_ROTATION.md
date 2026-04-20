# Project Rotation Log

Daily rotation across the 5 projects in this repo. Each day, one project
receives a "significant incremental move" — a coherent feature, polish pass,
or architectural step forward.

## Rotation order

1. Credicrew
2. LLM_Playground
3. SynapseOS
4. Titan
5. WaySafe

## Log

| Day | Date (UTC) | Project | Move |
|----:|---|---|---|
| 1 | 2026-04-19 | **WaySafe** | Built real Safety Intelligence engine (`safety.py`) — composite 0–100 score using geofences, recency- & severity-weighted incident proximity, late-night penalty, help-POI bonus. Added `pydeck` HeatmapLayer weighted by severity×recency×verified. New `theme.py` with dark gradient, brand header, and animated score-ring card. Authority dashboard gained category & time-series breakdowns. README rewritten to match reality. |
| 2 | 2026-04-19 | **Credicrew** | Shipped the explainable match engine the architecture doc promised but nobody had built. New `frontend/src/lib/match.ts` parses free-text queries into skills/location/seniority, scores each candidate on weighted factors (skills 0.55 · seniority 0.20 · location 0.15 · base 0.10), and returns a per-factor breakdown. Mirrored in `backend/app/services/match.py` with a new `POST /match` router so client and server always agree. Discover page now shows detected-plan chips, band counts, matched/missing skill chips, and a conic-gradient score ring per card. Added `MatchExplain` popover. Removed three stray duplicate files. README rewritten around the new feature. |
| 3 | 2026-04-20 | **LLM_Playground** | Shipped **Compare Mode** — the killer side-by-side feature the playground was missing. New Flask blueprint `routes/compare.py` fans out one prompt to up to 6 (provider, model, params) lanes concurrently via `ThreadPoolExecutor`, returning per-run tokens, latency and USD cost plus a summary with `cheapest_index` / `fastest_index` / `wall_clock_sec`. Pricing intelligence lives in a new `services/pricing.py` (mirrored on the client as `lib/pricing.js`) with per-1M-token rates for every OpenAI/Anthropic/Gemini flagship. Wrapped the React app in a `BrowserRouter` with a new gradient `NavShell` and a brand-new `pages/Compare.jsx`: responsive grid of `RunCard` panels with cheapest/fastest badges, cost & latency bar charts, token breakdown, example-prompt chips, and one-click JSON export. README rewritten around the new feature. |

## Next pick

Next session should target the next project in the rotation list, wrapping
around. That means:

- After **LLM_Playground** → next is **SynapseOS**.
