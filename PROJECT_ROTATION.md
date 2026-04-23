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
| 4 | 2026-04-23 | **SynapseOS** | Founded the project (it was a one-line README). Positioned as a local-first Personal Knowledge OS — "your thoughts, connected." Scaffolded a Next.js 14 + TS + Tailwind app under `SynapseOS/web`. Core domain: `lib/wikilinks.ts` parses `[[links]]` + `#tags`, builds a full link graph with unresolved targets promoted to "ghost" nodes; `lib/store.ts` is a Zustand store persisted to localStorage with create/open-or-create/update/delete + command-palette state; `lib/markdown.ts` is a tiny purpose-built renderer that turns inline wikilinks into clickable chrome without pulling in remark/rehype. UI: three-pane workspace (`Sidebar` with search+stats+backlink counters · `NoteEditor` with edit/split/read modes · `BacklinksPanel` showing inbound/outbound with dashed-magenta ghosts · `GraphView` — retina-aware canvas force-sim with pan/zoom/drag, active-node glow, neighbor highlighting, grid paper backdrop, degree-weighted labels). Added `⌘K` `CommandPalette` with fuzzy ranking and inline "create" flow; `⌘N` new note, `⌘G` toggle graph. Marketing landing page with animated `HeroGraph` constellation, gradient hero, feature grid. Seeded 7 interconnected starter notes so the graph lights up on first run. README rewritten to pitch the vision + architecture. |

## Next pick

Next session should target the next project in the rotation list, wrapping
around. That means:

- After **SynapseOS** → next is **Titan**.
