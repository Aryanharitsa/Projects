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

## Next pick

Next session should target the project directly before today's in the rotation
list, wrapping around. That means:

- After **WaySafe** → next is **Credicrew** (restart top of list).
