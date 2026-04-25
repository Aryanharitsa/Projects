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
| 3 | 2026-04-22 | **LLM_Playground** | Turned a generic single-provider playground into a real evaluation studio. New `backend/src/pricing.py` holds published $/1M-token rates with prefix-matching so dated model ids still resolve. New `POST /api/compare` fan-outs one prompt to up to 6 provider/model candidates in parallel via `ThreadPoolExecutor`, catching per-candidate errors so a missing key never kills siblings, and computes winners (fastest, cheapest, most verbose). `GET /api/pricing` exposes the table; `/chat` now returns `cost_usd` too. Frontend gains an **Arena** mode alongside Universal/August: coloured candidate roster in the sidebar, parallel results grid with headline tiles (models · succeeded · wall‑time · total $), per-card metric pills (latency/tokens/$), winner badges, one-click copy and JSON export. Fixed the mis-labeled "Deploy" header button (it was a download) → "Export". README rewritten around Arena with a full API-surface table. |
| 4 | 2026-04-24 | **SynapseOS** | Greenfield rebuild from a 12-byte README. Stood up the whole product: a personal second-brain OS where notes auto-link via embedding-based synapses. **Backend** (FastAPI + SQLite): `embed.py` is a zero-dep 512-d hashing-trick embedder (char 4-grams + word uni/bi-grams, L2-normalized); `synapse.py` computes the graph on the fly with a cosine threshold τ and top-K neighbor cap, plus Dijkstra-based path tracing over `1 − strength`; `store.py` persists notes with packed-float embeddings in SQLite; `seed.py` ships a 16-note demo graph with deliberate cross-cluster bridges. Seven HTTP endpoints: `/graph`, `/neighbors`, `/search`, `/path`, plus CRUD. **Frontend** (Next.js 14 + Tailwind + react-force-graph-2d): neon dark UI with animated grain, glow halos, and gradient edges. Three-pane layout — NoteComposer / SearchBar / PathFinder on the left, canvas graph in the center with degree-scaled nodes + weight-hued glow + animated particles along highlighted paths, Inspector on the right with neighbor strength bars. Semantic search, live graph refresh on note create/delete, and path tracing that highlights the chain in amber. README rewritten from stub to full vision + architecture diagram + API table + formula. |
| 5 | 2026-04-25 | **Titan** | Tore out a leaked 124 MB `fintrace/__MACOSX` archive and replaced the AML stub with a real, deterministic, explainable engine. New `apps/ai-aml/risk.py` ships seven named detectors (structuring, velocity_spike, round_trip cycles via DFS depth ≤4, fan_in, fan_out, high_risk_geo on FATF-style codes, round_amount), each contributing weight × saturating-intensity to a 0–100 score. New `sar.py` renders a markdown SAR draft + structured payload with evidence harvested from the firing factors. Gateway gained `GET /attest/{docHash}` and `GET /attestations/recent` (event-log replay) plus an AML pass-through so the frontend has one origin. **Frontend rebuild**: dark gradient + glassmorphism Tailwind theme, brand SVG logo, custom `ScoreRing` (conic-gradient), `FactorBars`, and a deterministic-layout `TxGraph` (no charting libs). Four routes — `/` hero + flow diagram, `/aml` drag-drop CSV → ranked accounts → factor bars + transaction graph + one-click SAR, `/kyc` PDF dropzone with animated 3-stage pipeline + on-chain receipt, `/attestations` hash search + auto-refreshing live `Attested` feed. Untracked Hardhat build outputs and added them to `.gitignore`. READMEs rewritten — `Titan/README.md` from 8 bytes to full pitch, `titan-v2/README.md` rebuilt around the new API table, formula, and route map. |

## Next pick

Next session should target the next project in the rotation list, wrapping
around. That means:

- After **Titan** → next is **WaySafe** (back to the start of the rotation
  for round 2).
