# 🚦 WaySafe — Smart Tourism Safety

A Streamlit app that turns crowd-reported incidents, geofenced risk zones,
and help-POI density into a **live, explainable safety score** — *and now*
forecasts where hazards will be at any future hour, with a **risk-aware
A\* router** that can re-time your trip for safety.

> Not another dashboard. WaySafe scores where you are, *predicts* where
> you'll be, plans the safest path between the two — and tells you exactly
> *why* it scored, predicted, or detoured the way it did.

---

## ✨ What's inside

| | |
|---|---|
| 🧮 **Live Safety score** (`safety.py`) | Composite 0–100 from geofence hits, severity- & recency-weighted incidents within 3 km, late-night window, help-POI density. Every deduction is returned as a human-readable factor. |
| 🛣 **Risk-aware route planner** (`routing.py`) | Pure-Python A\* over a snapped lat/lon grid. Runs **fastest** (α=0) and **safest** (α=4.5) in parallel. Edge cost is `haversine_km · (1 + α · risk(midpoint))`. Returns length-weighted avg safety, min safety, and km of elevated-risk segments — so the comparison is honest. |
| 🔮 **Hazard Forecast** (`forecast.py`) | Empirical-Bayes spatiotemporal model — historical hazards binned by ½-km cell × DOW × hour, kernel-smoothed across the 3 × 3 time neighbourhood, Poisson-saturated to a 0–100 risk. Predicts category mix, confidence, 24-h risk curve, and the city's likeliest hotspots at any future moment. |
| ⏱ **Forecast-aware routing** | The A\* edge cost can swap to *forecast* risk at the time the traveler will reach each midpoint. A `find_best_departure` sweep then ranks ±2 h candidate departures and tells you "shift by 1 h for +9 safety pts." |
| 🔥 **Incident risk heatmap + Forecast heatmap** | Existing `pydeck` HeatmapLayer weighted by severity × recency × verified, plus a new **forecast-driven** heatmap that morphs as you slide the time picker. |
| 📱 **Tourist app** | Live score ring, **Plan Route** tab with dual map overlay + GPX downloads + Google-Maps deeplink, **Forecast** tab with 24-hour curve and best-departure recommendation, hazard report (photo → SHA-256 fingerprint), nearby broadcast alerts, one-tap SOS, trip-report PDF. |
| 🛰 **Authority dashboard** | Verified/pending/SOS KPIs, category breakdown, incidents-over-time, **next-24h forecast curve** + likely hotspots at the predicted peak, verify-and-broadcast workflow. |
| 🔐 **Merkle rollup auditor** | Hash every incident, build a Merkle root, and produce per-leaf proofs. Tamper-evident without a blockchain. |
| 🌙 **Offline-first** | Flip "Offline mode" — reports queue in an in-memory outbox and flush on `Sync`. |
| 🎨 **Dark-gradient theme** | Custom CSS, conic-gradient ring gauges, status pills, accent palettes for routing (cyan / amber / purple) and forecasting (purple → teal). |

---

## 🧠 How the score is computed

```text
safety = clamp(0, 100 − Σ penalties + Σ bonuses)
```

| Factor | Signal | Impact |
|---|---|---|
| Geofence hit | user point in any risk polygon | −25 |
| Recent incidents within 3 km | per-incident: `severity × recency × distance-falloff × verified×1.5 × 1.6`, capped at 55 | up to −55 |
| Late-night window | local hour ∈ [22, 05) | −8 |
| Help POIs within 2 km | hospital / police / clinic / fire / help-desk | up to +9 |

Recency decays with a **72-hour half-life**. Severity: landslide = 5, flooding = 4,
accident = 4, roadblock = 2, other = 2.

Bands: `Safe ≥ 80 · Caution ≥ 60 · High Risk ≥ 35 · Danger < 35`.

---

## 🔮 How the forecast is computed

WaySafe learns *where* and *when* hazards historically cluster, then asks
"what does that mean for **this** lat/lon at **that** time?"

For every historical incident, accumulate a weight

```
w = severity × verified_bump × recency_decay(t)
```

into the (cell, day-of-week, hour) bucket. Recency on the *training* set
decays with a 14-day half-life so old patterns fade. The expected
weighted count in a bucket is an **Empirical-Bayes** posterior against
a per-bucket city prior:

```
λ̂(c, t) = (k_{c,t} + α · π_t) / (1 + α)
       π_t = Σ_c k_{c,t} / N_cells
```

— so sparse cells *shrink* toward the city-wide rate at that hour
instead of getting a coin-flip estimate from one observation. Both the
observation and the prior are **kernel-smoothed** across the 3×3
neighbourhood of (DOW, hour) with a separable triangular kernel
(0.45 · 1.0 · 0.45 in hour, 0.35 · 1.0 · 0.35 in DOW), so the surface
is continuous and a single Saturday-22:00 incident bleeds softly into
neighbouring buckets.

Risk is Poisson-saturated:

```
risk = 1 − exp(−κ · λ̂)         κ = 0.85, α = 3.0
```

Confidence is a function of the cell's effective sample size at the
queried bucket: **high** ≥ 1.5 raw weight in-bucket, **medium** with
adjacent-bucket / cell-history support, **low** otherwise.

The category forecast is a cell-conditional mix of the historical
hazard categories, smoothed toward the global category prior so quiet
cells still get sensible guesses.

### Routing on top of the forecast

`plan_forecast_route` walks the same A\* grid but each edge is priced by

```
cost(u, v) = haversine_km(u, v) · (1 + α · [(1 − blend) · forecast_risk(mid, t_arrive_v)
                                           + blend       · point_risk(mid, now)])
```

— so geofences and *currently active* incidents still count, while the
historical pattern decides the bulk of the score. `t_arrive_v` is
derived from cumulative km at u + edge km, divided by an
average travel speed of 32 km/h. `find_best_departure` then sweeps
±2 h and ranks candidate start times by safety so the UI can recommend
"depart 60 min earlier for +9 safety pts."

---

## 🚀 Run it

```bash
git clone https://github.com/Aryanharitsa/Projects.git
cd Projects/WaySafe
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Open the app, pick a view in the sidebar, and try:

- `15.55, 73.76` (Baga–Calangute belt) at **Sat 22:00** → forecast lights up
  red (`risk ≈ 0.62`, expected category: accident)
- `15.49, 73.78` (Aguada cliffs) at **Wed 08:00** → landslide-dominated,
  `risk ≈ 0.77`
- **Plan Route** → Aguada → Panaji at *Sat 22:00* → click
  *Find best departure window* → shift to *Sun 00:00* for **+9 safety pts**
- Flip **Offline mode**, file a hazard, then **Sync**

---

## 📂 Layout

```
WaySafe/
├── app.py               # Streamlit UI — Tourist · Authority · Auditor
├── safety.py            # Score engine + point_risk for the planner + heatmap
├── routing.py           # A* planner — fastest / safest / forecast-aware + best-departure
├── forecast.py          # Empirical-Bayes spatiotemporal hazard predictor
├── theme.py             # Dark CSS, ring gauge, route cards, forecast widgets
├── utils.py             # haversine, point-in-polygon, SHA-256, Merkle
├── data/
│   ├── goa_geofences.geojson
│   ├── incidents.csv    # 38 hazard reports across 6 hotspot zones
│   ├── broadcasts.csv   # authority-issued alerts
│   ├── poi.csv          # hospitals, police, help desks
│   ├── sos.csv          # SOS activations
│   └── uploads/         # photo evidence (created on first report)
├── requirements.txt
└── README.md
```

---

## 🧪 Quick sanity check

```bash
python - <<'PY'
import csv, json
from datetime import datetime
from forecast import HazardForecaster
from routing import plan_forecast_route, find_best_departure

inc = list(csv.DictReader(open("data/incidents.csv")))
geo = json.load(open("data/goa_geofences.geojson"))
poi = list(csv.DictReader(open("data/poi.csv")))

f = HazardForecaster(inc, now=datetime(2026,5,2,12,0))

# Forecast at Baga at peak hour
print("Baga Sat 22:00:", round(f.risk_at(15.5485, 73.7705, datetime(2026,5,2,22,0)), 2))

# Best-departure for Aguada -> Panaji around Sat 22:00
windows = find_best_departure(
    (15.4925, 73.7747), (15.4990, 73.8275),
    f, datetime(2026,5,2,22,0),
    incidents=inc, geofences=geo, pois=poi,
    span_h=2, step_min=30,
)
best_t, best_r = windows[0]
print(f"Best window: {best_t.strftime('%a %H:%M')}  safety={best_r.avg_safety}")
PY
```

Expected output:

```
Baga Sat 22:00: 0.62
Best window: Sun 00:00  safety=81
```

---

## 🛣 Roadmap

- [x] Safety-weighted routing (OSRM / OpenRouteService) using the score as an edge penalty
- [x] Live-traffic overlay & **incident prediction** (empirical-Bayes spatiotemporal model — pure-Python, no XGBoost dep)
- [ ] Push-notification channel for broadcasts (Web Push / FCM)
- [ ] PostgreSQL + PostGIS backend to replace CSVs once scale demands it
- [ ] Anchor daily Merkle roots on-chain for immutable provenance

---

## 👨‍💻 Author

Aryan D Haritsa — PES University · AI, Full-Stack & Research Enthusiast
